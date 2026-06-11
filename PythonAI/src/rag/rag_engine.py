from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ollama
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.rag.cast_chunker import CastChunker, CodeChunk
from src.rag.knowledge_graph import KnowledgeGraph
from src.rag.models import DEFAULT_MODEL, list_configured_models, list_ollama_models, resolve_model
from src.rag.reasoning import ReasoningEngine
from src.rag.verifier import AnswerVerifier

ROOT = Path(__file__).resolve().parent.parent.parent

# ═══════════════════════════════
# CONFIG
# ═══════════════════════════════
CHUNKS_FILE = ROOT / "data" / "raw" / "raw_chunks_godmode.json"
DB_PATH = ROOT / "python_brain_godmode"

# Directories to scan with cAST structural chunking during --rebuild
CODE_DIRS = [
    ROOT / "src",
]

SYSTEM_PROMPT = """You are PYTHON MASTER, a Python-specialist assistant for offline RAG.

Core mission:
- Deliver correct, practical Python guidance using retrieved context first.
- Cover Python 2.7 through 3.16 differences when relevant.
- Provide runnable code examples by default.
- Prefer safe, maintainable, Pythonic solutions.

Reasoning and quality policy:
- Think internally, but do not reveal private chain-of-thought.
- If information is uncertain or missing, state assumptions clearly.
- Never invent APIs, versions, or benchmark claims.
- When trade-offs exist, compare options and recommend one.

Answer contract:
1) Start with a direct answer.
2) Add version notes when behavior differs across Python versions.
3) Provide at least one runnable Python code block unless user asks otherwise.
4) Add brief pitfalls/common mistakes.
5) Add one performance or reliability tip when relevant.

Formatting:
- Keep answers concise but complete.
- Use bullet points for decisions and trade-offs.
- Keep code self-contained where possible.
- When citing sources, use [1], [2] etc. to reference the source documents listed at the end.
"""

USER_PROMPT_TEMPLATE = """PYTHON DOCUMENTATION CONTEXT:
{context}

QUESTION:
{question}

Execution mode:
- Your code may be executed after generation for validation.

Instructions:
- Prioritize retrieved context when it is relevant.
- If the question is ambiguous, state assumptions briefly and proceed.
- Mention Python version differences only when they matter.
- Include practical, production-friendly code.
- When referencing sources, use the citation numbers in brackets [1], [2] etc.

Output structure:
1. Direct Answer
2. Version Notes (if applicable)
3. Code (python fenced block)
4. Pitfalls
5. Performance/Reliability Tip
"""

# ═══════════════════════════════
# LIGHTWEIGHT BM25 IMPLEMENTATION
# ═══════════════════════════════

class SimpleBM25:
    """Lightweight BM25Okapi scorer — no external dependency needed."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.tokenized_corpus: list[list[str]] = [self._tokenize(doc) for doc in corpus]

        # Compute document frequency (df) and average document length (avgdl)
        self.df: Counter[str] = Counter()
        self.doc_lengths: list[int] = []
        for tokens in self.tokenized_corpus:
            self.df.update(set(tokens))
            self.doc_lengths.append(len(tokens))

        n_docs = len(self.tokenized_corpus)
        self.avgdl = sum(self.doc_lengths) / n_docs if n_docs > 0 else 0.0
        self.n_docs = n_docs

        # Pre-compute IDF
        self.idf: dict[str, float] = {}
        for term, freq in self.df.items():
            self.idf[term] = math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple word tokenizer — lowercase, split on non-alpha."""
        return re.findall(r"[a-z0-9_]+", text.lower())

    def get_scores(self, query: str) -> list[float]:
        """Return BM25 scores for each document in the corpus."""
        query_tokens = self._tokenize(query)
        scores = [0.0] * self.n_docs

        for term in query_tokens:
            if term not in self.idf:
                continue
            idf = self.idf[term]
            for i, tokens in enumerate(self.tokenized_corpus):
                term_freq = tokens.count(term)
                if term_freq == 0:
                    continue
                numerator = idf * term_freq * (self.k1 + 1)
                denominator = term_freq + self.k1 * (1 - self.b + self.b * self.doc_lengths[i] / self.avgdl)
                scores[i] += numerator / denominator

        return scores


# ═══════════════════════════════
# MMR (MAXIMUM MARGINAL RELEVANCE)
# ═══════════════════════════════

def mmr_rerank(
    docs: list[dict[str, Any]],
    query_embedding: list[float],
    lambda_: float = 0.7,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """Re-rank documents using Maximum Marginal Relevance for diversity.

    lambda_ controls the trade-off: higher = more relevance-focused,
    lower = more diversity-focused.
    """
    if not docs:
        return []

    selected: list[dict[str, Any]] = []
    remaining = list(range(len(docs)))

    # Compute similarity matrix (dense embeddings for diversity)
    # Fall back to score-based diversity if no embeddings
    for _ in range(min(top_k, len(docs))):
        if not remaining:
            break

        best_score = -float("inf")
        best_idx = -1

        for idx in remaining:
            relevance = docs[idx].get("score", 0.0)

            # Diversity penalty: max similarity to already selected
            diversity_penalty = 0.0
            for sel in selected:
                sim = _cosine_sim(
                    docs[idx].get("embedding", []),
                    sel.get("embedding", []),
                )
                diversity_penalty = max(diversity_penalty, sim)

            mmr_score = lambda_ * relevance - (1 - lambda_) * diversity_penalty

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx >= 0:
            selected.append(docs[best_idx])
            remaining.remove(best_idx)

    return selected


def _to_plain_list(v: Any) -> list[float]:
    """Convert a numpy array or other iterable to a plain Python list."""
    if hasattr(v, "tolist"):
        return v.tolist()
    return list(v)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ═══════════════════════════════
# QUERY EXPANSION
# ═══════════════════════════════

def expand_query(question: str, model: str = DEFAULT_MODEL) -> list[str]:
    """Generate related queries using Ollama for broader retrieval."""
    expansion_prompt = (
        f"You are a Python documentation search assistant. Given a user's question, "
        f"generate 2 alternative phrasings or related questions that might help find "
        f"better documentation results. Keep each query concise (under 15 words). "
        f"Return them as a short numbered list, one per line.\n\n"
        f"Original question: {question}"
    )

    try:
        response = ollama.generate(
            model=model,
            prompt=expansion_prompt,
            options={"temperature": 0.3, "num_predict": 128},
        )
        text = response.get("response", "")
        queries = re.findall(r"^\d+[.)\-]\s+(.+)", text, re.MULTILINE)
        queries = [q.strip() for q in queries if q.strip()]
        return [question] + queries[:2]
    except Exception:
        return [question]




# ═══════════════════════════════
# HYBRID SEARCH (DENSE + BM25)
# ═══════════════════════════════

@dataclass
class SearchResult:
    title: str
    version: str
    category: str
    text: str
    score: float
    rank: int = 0
    citation_num: int = 0
    embedding: list[float] = field(default_factory=list)


def hybrid_search(
    question: str,
    collection: Any,
    embedder: SentenceTransformer,
    bm25: SimpleBM25 | None = None,
    corpus_texts: list[str] | None = None,
    kg: KnowledgeGraph | None = None,
    top_k: int = 8,
    use_mmr: bool = False,
    mmr_lambda: float = 0.7,
    version_filter: str = "",
    category_filter: str = "",
) -> list[dict[str, Any]]:
    """Dense + BM25 + KG hybrid search with optional MMR and metadata filtering."""

    # 1. Dense search
    q_emb = embedder.encode([question]).tolist()
    include_fields = ["documents", "metadatas", "distances"]
    if use_mmr:
        include_fields.append("embeddings")

    results = collection.query(
        query_embeddings=q_emb,
        n_results=top_k,
        include=include_fields,
    )

    dense_docs: dict[str, dict[str, Any]] = {}

    for i in range(len(results["documents"][0])):
        score = 1 - results["distances"][0][i]
        title = results["metadatas"][0][i].get("title", "")
        version = results["metadatas"][0][i].get("version", "")
        category = results["metadatas"][0][i].get("category", "")

        # Metadata filtering
        if version_filter and version != version_filter:
            continue
        if category_filter and category != category_filter:
            continue

        if title not in dense_docs and score > 0.15:
            dense_docs[title] = {
                "title": title,
                "version": version,
                "category": category,
                "text": results["documents"][0][i],
                "score": score,
                "embedding": _to_plain_list(results.get("embeddings", [[], []])[0][i]) if results.get("embeddings") else [],
            }

    # 2. BM25 search (if available)
    bm25_docs: dict[str, dict[str, Any]] = {}
    if bm25 is not None and corpus_texts is not None:
        bm25_scores = bm25.get_scores(question)
        # Get top BM25 results and match to corpus
        scored_indices = sorted(
            enumerate(bm25_scores), key=lambda x: x[1], reverse=True
        )[:top_k]

        for idx, bm25_score in scored_indices:
            if bm25_score <= 0:
                continue
            # Try to match the BM25 document to a chroma document
            # We use the bm25_text from the corpus_texts which corresponds
            # to actual chroma documents
            bm25_text = corpus_texts[idx] if idx < len(corpus_texts) else ""
            if not bm25_text:
                continue

            # Find matching dense doc or add as new
            # Check if this text is similar to any dense doc title
            first_line = bm25_text.split("\n")[0] if bm25_text else ""
            title_match = re.match(r"Title:\s*(.+)", first_line)
            bm25_title = title_match.group(1) if title_match else ""

            if bm25_title and bm25_title in dense_docs:
                # Already in dense results — boost its score via RRF
                pass
            elif bm25_title and bm25_title not in dense_docs:
                # New result from BM25 only
                # Try to find metadata from chroma
                meta_match = re.search(r"Version:\s*Python\s*(\S+)", bm25_text)
                cat_match = re.search(r"Category:\s*(\S+)", bm25_text)
                bm25_version = meta_match.group(1) if meta_match else ""
                bm25_category = cat_match.group(1) if cat_match else ""

                # Metadata filtering for BM25 results too
                if version_filter and bm25_version != version_filter:
                    continue
                if category_filter and bm25_category != category_filter:
                    continue

                bm25_docs[bm25_title] = {
                    "title": bm25_title,
                    "version": bm25_version,
                    "category": bm25_category,
                    "text": bm25_text,
                    "score": bm25_score * 0.3,  # Normalize BM25 scores
                    "embedding": [],
                }

    # 2.5 Knowledge Graph Search (Triple-Hybrid)
    kg_docs: dict[str, dict[str, Any]] = {}
    if kg is not None:
        kg_results = kg.query(question, hops=2, max_results=top_k)
        for r in kg_results:
            title = r["title"]
            if title not in dense_docs and title not in bm25_docs:
                text = r.get("text_preview", "")
                if corpus_texts:
                    for ct in corpus_texts:
                        if ct.startswith(f"Title: {title}\n"):
                            text = ct
                            break
                r_version = r.get("version", "")
                r_category = r.get("category", "")
                if version_filter and r_version != version_filter:
                    continue
                if category_filter and r_category != category_filter:
                    continue
                kg_docs[title] = {
                    "title": title,
                    "version": r_version,
                    "category": r_category,
                    "text": text,
                    "score": r["score"],
                    "embedding": [],
                }

    # 3. Reciprocal Rank Fusion (RRF)
    all_titles = list(dense_docs.keys()) + [t for t in bm25_docs if t not in dense_docs] + [t for t in kg_docs if t not in dense_docs and t not in bm25_docs]
    rrf_scores: dict[str, float] = {}

    for rank, title in enumerate(dense_docs.keys()):
        rrf_scores[title] = rrf_scores.get(title, 0) + 1.0 / (60 + rank)

    for rank, title in enumerate(bm25_docs.keys()):
        if title not in dense_docs:
            rrf_scores[title] = rrf_scores.get(title, 0) + 1.0 / (60 + rank)

    for rank, title in enumerate(kg_docs.keys()):
        if title not in dense_docs and title not in bm25_docs:
            rrf_scores[title] = rrf_scores.get(title, 0) + 1.0 / (60 + rank)

    # Merge all docs with RRF scores
    merged: list[dict[str, Any]] = []
    for title in all_titles:
        doc = dense_docs.get(title) or bm25_docs.get(title) or kg_docs.get(title)
        if doc:
            doc["score"] = rrf_scores.get(title, doc["score"])
            merged.append(doc)

    merged.sort(key=lambda x: x["score"], reverse=True)

    # 4. Apply MMR if requested
    if use_mmr and merged:
        merged = mmr_rerank(merged, q_emb[0], lambda_=mmr_lambda, top_k=top_k)

    # Add citation numbers
    for i, doc in enumerate(merged):
        doc["citation_num"] = i + 1
        doc["rank"] = i + 1

    return merged[:6]


# ═══════════════════════════════
# SMART ANSWER GENERATOR
# ═══════════════════════════════

def format_sources(docs: list[dict[str, Any]]) -> str:
    """Format source documents with citation numbers."""
    if not docs:
        return ""
    lines = ["\n[Docs] Sources:"]
    for d in docs:
        cat = d.get("category", "")
        ver = f"v{d['version']}" if d.get("version") else ""
        citation = f"[{d.get('citation_num', 0)}]"
        lines.append(f"  {citation} {d['title'][:50]:50s} {ver:8s} ({cat})")
    return "\n".join(lines)


def get_answer(
    question: str,
    collection: Any,
    embedder: SentenceTransformer,
    history: list[dict[str, str]],
    bm25: SimpleBM25 | None = None,
    corpus_texts: list[str] | None = None,
    kg: KnowledgeGraph | None = None,
    use_query_expansion: bool = False,
    use_mmr: bool = False,
    mmr_lambda: float = 0.7,
    no_exec: bool = False,
    exec_timeout: int = 5,
    version_filter: str = "",
    category_filter: str = "",
    model: str = DEFAULT_MODEL,
) -> tuple[str, list[dict[str, Any]]]:
    """Generate answer with optional query expansion, hybrid search, and MMR."""

    # Query expansion: run multiple queries and merge results
    queries = expand_query(question, model=model) if use_query_expansion else [question]
    all_docs: dict[str, dict[str, Any]] = {}

    for q in queries[:3]:
        docs = hybrid_search(
            q, collection, embedder, bm25, corpus_texts, kg=kg,
            use_mmr=use_mmr, mmr_lambda=mmr_lambda,
            version_filter=version_filter, category_filter=category_filter,
        )
        for doc in docs:
            title = doc["title"]
            if title not in all_docs or doc["score"] > all_docs[title]["score"]:
                all_docs[title] = doc

    docs = sorted(all_docs.values(), key=lambda x: x["score"], reverse=True)[:6]
    # Re-assign citation numbers after merge
    for i, doc in enumerate(docs):
        doc["citation_num"] = i + 1
        doc["rank"] = i + 1

    # Build context with citations
    if docs:
        context_parts: list[str] = []
        for d in docs:
            citation = f"[{d['citation_num']}]"
            part = f"{citation} > {d['title']}"
            if d["version"]:
                part += f" (Python {d['version']})"
            part += f"\n{d['text'][:1500]}"
            context_parts.append(part)
        context = "\n\n---\n\n".join(context_parts)
    else:
        context = "Use your built-in Python knowledge."

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-10:])

    # ── Phase 2: Reasoning Engine ──
    reasoning_engine = ReasoningEngine(model=model)
    plan_text = ""
    if reasoning_engine.requires_reasoning(question):
        print("\n[Reasoning] Complex query detected. Generating plan...")
        plan_text = reasoning_engine.generate_plan(question, context)
        print(f"  -> Plan: {plan_text.replace(chr(10), ' | ')[:150]}...")

        prompt_with_plan = f"{USER_PROMPT_TEMPLATE.format(context=context, question=question)}\n\nREASONING PLAN:\n{plan_text}"
        messages.append({"role": "user", "content": prompt_with_plan})
    else:
        messages.append({
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(context=context, question=question),
        })

    print(f"\n{'='*55}")
    print(f"[AI] PYTHON MASTER (model: {model}):")
    print(f"{'─'*55}")

    response = ollama.chat(
        model=model,
        messages=messages,
        stream=True,
        options={
            "temperature": 0.3,
            "num_ctx": 512,
            "num_predict": 2048,
            "repeat_penalty": 1.1,
        },
    )

    full = ""
    for chunk in response:
        text = chunk["message"]["content"]
        print(text, end="", flush=True)
        full += text

    print(f"\n{'─'*55}")

    # ── Phase 2: Reflection & Verification ──
    verifier = AnswerVerifier(model=model)

    # Optional reflection step
    if plan_text:
        print("\n[Reasoning] Reflecting on answer...")
        reflection = reasoning_engine.reflect_and_correct(question, full)
        if "LGTM" not in reflection:
            print(f"  [Reflection] Suggested correction: {reflection[:100]}...")

    if not no_exec:
        print("\n[Verify] Validating answer...")
        code_ver = verifier.verify_code(full, timeout=exec_timeout)
        if code_ver["blocks_checked"] > 0:
            if code_ver["all_passed"]:
                print(f"  [OK] Code execution: All {code_ver['blocks_checked']} block(s) passed.")
            else:
                print("  [WARN] Code execution: Errors found in blocks.")
                for d in code_ver["details"]:
                    if d["status"] == "error":
                        print(f"    - {d['output'][:80]}")
        else:
            print("  [OK] Code execution: No code blocks to check.")

        print("  [Verify] Checking facts against context...")
        fact_ver = verifier.verify_facts(question, full, context)
        if fact_ver.get("hallucinations_found"):
            print(f"  [WARN] Fact check: Hallucinations detected! {fact_ver.get('explanation')}")
        else:
            print("  [OK] Fact check: Passed.")

        conf = verifier.compute_confidence(code_ver, fact_ver)
        print(f"  [Confidence Score] {conf * 100:.0f}%")

        # ── Phase 4: Constitutional Core ──
        try:
            from src.rag.constitution import ConstitutionalCheck
            constitution = ConstitutionalCheck()
            violations = constitution.validate_all(full, code_ver, fact_ver)
            if violations:
                print("\n  [CONSTITUTION] Response violated principles:")
                for v in violations:
                    print(f"    - {v}")
            else:
                print("\n  [CONSTITUTION] Passed all core value checks.")
        except ImportError:
            pass
    # Show sources with citations
    if docs:
        print(format_sources(docs))

    print(f"{'='*55}\n")
    return full, docs


# ═══════════════════════════════
# DATABASE BUILD
# ═══════════════════════════════

def _code_chunks_to_rag_format(chunks: list[CodeChunk]) -> list[dict[str, Any]]:
    """Convert cAST CodeChunk objects to RAG build_db dict format."""
    result: list[dict[str, Any]] = []
    for c in chunks:
        # Build a semantic title from chunk metadata
        title_parts = [c.name]
        if c.parent_class:
            title_parts.insert(0, c.parent_class)
        title = ".".join(title_parts)
        file_name = Path(c.filepath).name
        full_title = f"{c.chunk_type}: {title} ({file_name})"

        # Unique ID based on file path + location
        chunk_id = f"cast_{abs(hash(f'{c.filepath}:{c.name}:{c.start_line}:{c.end_line}'))}"

        result.append({
            "id": chunk_id,
            "text": c.to_embedding_text(),
            "type": c.chunk_type,
            "title": full_title,
            "version": "",
            "category": "code",
        })
    return result


def build_db(chunks_file: Path) -> tuple[Any, SentenceTransformer, SimpleBM25 | None, list[str], KnowledgeGraph]:
    import chromadb

    print(f"\n[Data] Loading: {chunks_file}")

    with open(chunks_file, encoding="utf-8") as f:
        chunks = json.load(f)

    skip = {"font", "image_png", "image_jpg", "image_gif", "static", "css"}
    valid = [
        c for c in chunks
        if len(c.get("text", "")) > 80 and c.get("type", "") not in skip
    ]

    print(f"[OK] Valid chunks: {len(valid):,}")

    # ── cAST code chunking (structural AST-aware chunking for Python files) ──
    print("[cAST] Chunking source code files with structural awareness...")
    chunker = CastChunker(language="python")
    all_code_chunks: list[dict[str, Any]] = []
    for code_dir in CODE_DIRS:
        if code_dir.exists():
            try:
                raw_chunks = chunker.chunk_directory(code_dir, extensions=[".py"])
                rag_chunks = _code_chunks_to_rag_format(raw_chunks)
                all_code_chunks.extend(rag_chunks)
                print(f"  [cAST] {code_dir}: {len(rag_chunks)} chunks")
            except Exception as e:
                print(f"  [cAST] Error chunking {code_dir}: {e}")
    code_valid = [
        c for c in all_code_chunks
        if len(c.get("text", "")) > 80
    ]
    print(f"[cAST] Code chunks after filtering: {len(code_valid):,}")
    valid.extend(code_valid)
    print("\n[Build] Building GOD MODE database...")

    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=str(DB_PATH))

    try:
        client.delete_collection("python_godmode")
    except Exception:
        pass

    collection = client.create_collection(
        name="python_godmode", metadata={"hnsw:space": "cosine"}
    )

    batch_size = 1024  # Increased for 100x speed
    corpus_texts: list[str] = []

    for i in tqdm(range(0, len(valid), batch_size), desc="Embedding"):
        batch = valid[i : i + batch_size]
        texts = [
            f"Title: {c.get('title','')}\n"
            f"Version: Python {c.get('version','')}\n"
            f"Category: {c.get('category','')}\n"
            f"Type: {c.get('type','')}\n\n"
            f"{c.get('text','')[:2000]}"
            for c in batch
        ]
        ids = [
            str(abs(hash(c.get("id", f"{i}_{j}"))))[:20]
            for j, c in enumerate(batch)
        ]
        # Larger batch encoding
        embs = embedder.encode(texts, batch_size=256, show_progress_bar=False).tolist()
        collection.add(
            documents=texts,
            embeddings=embs,
            ids=ids,
            metadatas=[
                {
                    "title": c.get("title", "")[:100],
                    "version": str(c.get("version", "")),
                    "category": c.get("category", ""),
                    "type": c.get("type", ""),
                }
                for c in batch
            ],
        )
        corpus_texts.extend(texts)

    # Build BM25 index
    print("[Index] Building BM25 keyword index...")
    bm25 = SimpleBM25(corpus_texts)

    # Build Knowledge Graph
    print("[KG] Building Knowledge Graph...")
    kg = KnowledgeGraph()
    kg.build_from_chunks(valid)
    kg.save()

    print(f"[OK] GOD MODE DB ready! {collection.count():,} chunks, BM25 & KG active")
    return collection, embedder, bm25, corpus_texts, kg


def load_db(chunks_file: Path) -> tuple[Any, SentenceTransformer, SimpleBM25 | None, list[str], KnowledgeGraph]:
    import chromadb

    print("[OK] Loading GOD MODE database...")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_collection("python_godmode")

    # Load corpus texts for BM25 from the collection
    count = collection.count()
    print(f"[Docs] Total knowledge: {count:,} chunks")
    print("[Index] Rebuilding BM25 index from stored documents...")

    corpus_texts: list[str] = []
    batch_size = 100
    for i in range(0, count, batch_size):
        batch = collection.get(
            limit=batch_size,
            offset=i,
            include=["documents"],
        )
        if batch and batch.get("documents"):
            corpus_texts.extend(batch["documents"])

    bm25 = SimpleBM25(corpus_texts) if corpus_texts else None
    print(f"[Index] BM25 index ready ({len(corpus_texts)} documents)")

    kg = KnowledgeGraph()
    if kg.load():
        print("[KG] Knowledge Graph loaded successfully")
    else:
        print("[KG] Building new Knowledge Graph from chunks...")
        try:
            with open(chunks_file, encoding="utf-8") as f:
                raw_chunks = json.load(f)
            kg.build_from_chunks(raw_chunks)
            kg.save()
        except Exception as e:
            print(f"[KG] Error building graph: {e}")

    return collection, embedder, bm25, corpus_texts, kg


# ═══════════════════════════════
# STATS
# ═══════════════════════════════

def print_stats(collection: Any, chunks_file: Path) -> None:
    """Print database statistics."""
    count = collection.count()
    print("\n[Stats] RAG Database Statistics")
    print(f"{'='*55}")
    print(f"  Chunks in DB : {count:,}")
    print(f"  Source file  : {chunks_file.name}")

    # Sample metadata
    sample = collection.get(limit=count, include=["metadatas"])
    if sample and sample.get("metadatas"):
        metadatas = sample["metadatas"]
        versions = Counter(m.get("version", "") for m in metadatas)
        categories = Counter(m.get("category", "") for m in metadatas)
        types = Counter(m.get("type", "") for m in metadatas)

        print("\n  Versions:")
        for ver, cnt in versions.most_common(10):
            print(f"    Python {ver or '(none)'}: {cnt:,}")
        print("\n  Categories (top 10):")
        for cat, cnt in categories.most_common(10):
            print(f"    {cat}: {cnt:,}")
        print("\n  Types (top 10):")
        for t, cnt in types.most_common(10):
            print(f"    {t}: {cnt:,}")
    print(f"{'='*55}\n")


# ═══════════════════════════════
# MAIN
# ═══════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Python RAG assistant backed by Ollama.")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model to use (default: {DEFAULT_MODEL}). Use 'list' to see available models.")
    parser.add_argument("--question", default="", help="Ask one question and exit.")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild database on startup.")
    parser.add_argument("--stats", action="store_true", help="Show database statistics and exit.")
    parser.add_argument("--no-exec", action="store_true", help="Skip code execution verification.")
    parser.add_argument("--exec-timeout", type=int, default=5, help="Timeout in seconds for code execution.")
    parser.add_argument("--query-expansion", action="store_true", help="Enable query expansion for broader search.")
    parser.add_argument("--mmr", action="store_true", help="Enable MMR diversity re-ranking.")
    parser.add_argument("--mmr-lambda", type=float, default=0.7, help="MMR lambda (higher = more relevance-focused).")
    parser.add_argument("--version", default="", help="Filter results by Python version (e.g., 3.10).")
    parser.add_argument("--category", default="", help="Filter results by category (e.g., library, howto).")
    parser.add_argument("--list-models", action="store_true",
                        help="List available Ollama models and exit.")
    return parser.parse_args()


# ═══════════════════════════════
# CODE EXECUTION & EXTRACTION
# ═══════════════════════════════

def execute_code(code: str, timeout: int = 5) -> tuple[str | None, str | None]:
    """Execute Python code safely with a timeout and return (stdout, stderr).

    Checks for dangerous patterns before execution.
    """
    dangerous_patterns = [
        "import os",
        "import subprocess",
        "import shutil",
        "import socket",
        "import ctypes",
        "eval(",
        "exec(",
        "__import__(",
        "open(",
    ]

    for pattern in dangerous_patterns:
        if pattern in code:
            return None, "Skipped (safety)"

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip() or None
        return stdout or None, stderr
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)


def extract_code_blocks(text: str) -> list[str]:
    """Extract all Python fenced code blocks from a text string."""
    pattern = r"```python\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [block.strip() for block in matches]


def load_or_build_db(force_rebuild: bool = False) -> tuple[Any, SentenceTransformer, SimpleBM25 | None, list[str], KnowledgeGraph, Path]:

    chunks_file = (
        ROOT / "data" / "raw" / "raw_chunks_godmode.json"
        if (ROOT / "data" / "raw" / "raw_chunks_godmode.json").exists()
        else ROOT / "data" / "raw" / "raw_chunks.json"
    )

    # If DB doesn't exist or rebuild requested, build fresh
    if not DB_PATH.exists() or force_rebuild:
        return *build_db(chunks_file), chunks_file

    return *load_db(chunks_file), chunks_file


def save_conversation(history: list[dict[str, str]], export_md: bool = False) -> Path | None:
    """Save conversation to a timestamped JSON file (and optionally Markdown)."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    save_path = ROOT / "data" / "conversations"
    save_path.mkdir(parents=True, exist_ok=True)

    filepath = save_path / f"conversation_{timestamp}.json"
    filepath.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Saved] Conversation saved: {filepath}")

    if export_md:
        md_path = save_path / f"conversation_{timestamp}.md"
        export_conversation_markdown(history, md_path)
        print(f"[Saved] Markdown export: {md_path}")

    return filepath


def export_conversation_markdown(
    history: list[dict[str, str]],
    output_path: Path | None = None,
    docs: list[dict[str, Any]] | None = None,
) -> str:
    """Export a conversation as formatted Markdown with citations."""
    if output_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = ROOT / "data" / "conversations" / f"conversation_{timestamp}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# PythonAI RAG Conversation",
        "",
        f"*Exported: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "---",
        "",
    ]

    # Collect all citations from docs across the conversation
    all_citations: list[dict[str, Any]] = []
    seen_citations: set[str] = set()

    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        entry_docs = entry.get("docs", [])

        if role == "user":
            lines.append("## 👤 Question")
            lines.append("")
            lines.append(content)
            lines.append("")
        elif role == "assistant":
            lines.append("## 🤖 Answer")
            lines.append("")
            lines.append(content)
            lines.append("")

            # Add per-answer source citations
            if entry_docs:
                lines.append("### 📚 Sources Cited")
                lines.append("")
                for d in entry_docs:
                    num = d.get("citation_num", 0)
                    title = d.get("title", "Untitled")
                    ver = d.get("version", "")
                    cat = d.get("category", "")
                    text_snippet = d.get("text", "")[:300]
                    lines.append(f"**[{num}]** {title} _(Python {ver}, {cat})_")
                    if text_snippet:
                        lines.append(f"> {text_snippet.replace(chr(10), ' ')}")
                    lines.append("")

                    # Track for global citations
                    cite_key = f"{title}:{ver}"
                    if cite_key not in seen_citations:
                        seen_citations.add(cite_key)
                        all_citations.append(d)

            lines.append("---")
            lines.append("")

    # Also accept docs passed directly
    if docs and not any("docs" in e for e in history):
        lines.append("## 📚 All Sources")
        lines.append("")
        for d in docs:
            num = d.get("citation_num", 0)
            title = d.get("title", "Untitled")
            ver = d.get("version", "")
            cat = d.get("category", "")
            text_snippet = d.get("text", "")[:400]
            lines.append(f"**[{num}]** {title} _(Python {ver}, {cat})_")
            if text_snippet:
                lines.append(f"> {text_snippet.replace(chr(10), ' ')}")
            lines.append("")

    # Global reference section
    if all_citations:
        lines.append("## 📖 Reference Index")
        lines.append("")
        for d in all_citations:
            num = d.get("citation_num", 0)
            title = d.get("title", "Untitled")
            ver = d.get("version", "")
            cat = d.get("category", "")
            lines.append(f"- **[{num}]** {title} — v{ver}, {cat}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)


def list_conversations() -> list[dict[str, Any]]:
    """List all saved conversations with metadata."""
    conv_dir = ROOT / "data" / "conversations"
    if not conv_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for f in sorted(conv_dir.glob("conversation_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            num_messages = len(data) if isinstance(data, list) else 0
            user_msgs = sum(1 for m in (data if isinstance(data, list) else []) if isinstance(m, dict) and m.get("role") == "user")
            timestamp = f.stem.replace("conversation_", "")
            # First user message as summary
            first_user = ""
            if isinstance(data, list):
                for m in data:
                    if isinstance(m, dict) and m.get("role") == "user":
                        first_user = m.get("content", "")[:100]
                        break
            results.append({
                "file": f.name,
                "path": str(f),
                "timestamp": timestamp,
                "messages": num_messages,
                "questions": user_msgs,
                "summary": first_user,
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        except Exception:
            continue

    return results


def search_conversations(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Full-text search across all saved conversations."""
    conv_dir = ROOT / "data" / "conversations"
    if not conv_dir.exists():
        return []

    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    for f in sorted(conv_dir.glob("conversation_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue

            match_count = 0
            snippets: list[str] = []

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content", "")
                role = msg.get("role", "")
                if query_lower in content.lower():
                    match_count += 1
                    # Extract snippet around the match
                    idx = content.lower().find(query_lower)
                    start = max(0, idx - 60)
                    end = min(len(content), idx + len(query) + 60)
                    snippet = content[start:end].replace("\n", " ")
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(content):
                        snippet = snippet + "..."
                    snippets.append(f"[{role}] {snippet}")

            if match_count > 0:
                first_user = ""
                for msg in data:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        first_user = msg.get("content", "")[:80]
                        break
                results.append({
                    "file": f.name,
                    "timestamp": f.stem.replace("conversation_", ""),
                    "summary": first_user,
                    "matches": match_count,
                    "snippets": snippets[:3],
                })

        except Exception:
            continue

    results.sort(key=lambda x: x["matches"], reverse=True)
    return results[:max_results]


def show_model_info(model: str = DEFAULT_MODEL) -> None:
    """Display model information."""
    try:
        model_info = ollama.show(model=model)
        print(f"\n[Info] Model: {model}")
        if isinstance(model_info, dict):
            for key in ["modelfile", "template", "parameters"]:
                if key in model_info:
                    val = model_info[key]
                    if isinstance(val, str):
                        print(f"  {key}: {val[:200]}")
        print()
    except Exception as e:
        print(f"  Could not fetch model info: {e}")


def main() -> None:

    args = parse_args()

    # Resolve model with fallback
    available_ollama = list_ollama_models()
    selected_model = resolve_model(args.model, available=available_ollama)

    if selected_model != args.model:
        print(f"[WARN] Model '{args.model}' not available. Using '{selected_model}' instead.")

    # List models mode
    if args.list_models:
        print("\n[Models] Available Ollama models:")
        configured = list_configured_models()
        if available_ollama:
            print("\n  Locally available:")
            for m in available_ollama:
                print(f"    - {m}")
        else:
            print("\n  No models found in local Ollama. Run 'ollama pull <model>' first.")
        print(f"\n  Default model: {DEFAULT_MODEL}")
        print()
        return

    print(f"""
╔══════════════════════════════════════════╗
║   [PYTHON] PYTHON MASTER — GOD MODE AI   ║
║     Model: {selected_model:30s}║
║     Powered by: Qwen2.5-Coder + RAG     ║
║     Hybrid Search: Dense + BM25         ║
╚══════════════════════════════════════════╝""")

    collection, embedder, bm25, corpus_texts, kg, chunks_file = load_or_build_db(force_rebuild=args.rebuild)

    # Stats mode
    if args.stats:
        print_stats(collection, chunks_file)
        return

    # Filters summary
    filter_parts = []
    if args.version:
        filter_parts.append(f"version={args.version}")
    if args.category:
        filter_parts.append(f"category={args.category}")
    filters_str = f" [{', '.join(filter_parts)}]" if filter_parts else ""

    # Single question mode
    if args.question.strip():
        get_answer(
            args.question.strip(), collection, embedder, [],
            bm25=bm25, corpus_texts=corpus_texts, kg=kg,
            use_query_expansion=args.query_expansion,
            use_mmr=args.mmr, mmr_lambda=args.mmr_lambda,
            no_exec=args.no_exec, exec_timeout=args.exec_timeout,
            version_filter=args.version, category_filter=args.category,
            model=selected_model,
        )
        return

    print("""
Commands:
  'rebuild'     → Rebuild database
  'expand'      → Download extra data (PEPs, libraries)
  'clear'       → Reset conversation
  'search N'    → Show top N search results (default: 6)
  /save         → Save conversation to JSON file
  /export       → Save conversation as Markdown
  /list         → List all saved conversations
  /search <q>   → Search saved conversations
  /explain      → Explain last answer in more detail
  /model        → Show model information
  /stats        → Show database statistics
  'quit'        → Exit
  /help         → Show this help
""")

    history: list[dict[str, str]] = []
    last_answer: str = ""
    last_docs: list[dict[str, Any]] = []
    search_count: int = 6

    while True:
        try:
            q = input("You: ").strip()
        except KeyboardInterrupt:
            print("\n[Bye] Goodbye!")
            break

        if not q:
            continue

        # --- Built-in commands ---
        if q == "quit":
            print("[Bye] Goodbye!")
            break
        elif q == "clear":
            history = []
            last_answer = ""
            last_docs = []
            print("[Reset] Conversation cleared!\n")
        elif q == "rebuild":
            collection, embedder, bm25, corpus_texts, kg = build_db(chunks_file)
        elif q == "expand":
            print("[Download] Running data collector...")
            os.system(f'"{sys.executable}" -m src.data.collector')
            collection, embedder, bm25, corpus_texts, kg = build_db(
                ROOT / "data" / "raw" / "raw_chunks_godmode.json"
            )

        # --- Slash commands ---
        elif q == "/help":
            print("""
  Commands:
    rebuild        → Rebuild database
    expand         → Download extra data
    clear          → Reset conversation
    search N       → Show top N search results
    /save          → Save conversation to JSON file
    /export        → Save conversation as Markdown
    /list          → List all saved conversations
    /search <q>    → Search saved conversations
    /explain       → Explain last answer in more detail
    /model         → Show model information
    /stats         → Show database statistics
    quit           → Exit
""")
        elif q == "/save":
            save_conversation(history, export_md=False)
        elif q == "/export":
            path = save_conversation(history, export_md=True)
        elif q == "/list":
            convs = list_conversations()
            if not convs:
                print("[Empty] No saved conversations found.\n")
            else:
                print(f"\n[Conversations] ({len(convs)} saved)")
                print(f"{'='*60}")
                for i, c in enumerate(convs, 1):
                    print(f"  {i:2d}. {c['file']}")
                    print(f"      Summary: {c['summary'][:60] or '(empty)'}")
                    print(f"      Messages: {c['messages']} | Questions: {c['questions']} | Size: {c['size_kb']} KB")
                print()
        elif q.startswith("/search "):
            query = q[8:].strip()
            if not query:
                print("Usage: /search <query>\n")
            else:
                convs = search_conversations(query, max_results=8)
                if not convs:
                    print(f"[No results] No conversations matched \"{query}\"\n")
                else:
                    print(f"\n[Search] \"{query}\" — {len(convs)} conversation(s) matched")
                    print(f"{'='*60}")
                    for c in convs:
                        print(f"  [{c['timestamp']}] {c['file']}")
                        print(f"      Matches: {c['matches']} | Summary: {c['summary'][:60] or '(empty)'}")
                        for s in c['snippets'][:2]:
                            print(f"      -> {s[:120]}")
                    print()
        elif q == "/explain":
            if not last_answer:
                print("No previous answer to explain. Ask a question first.\n")
            else:
                explain_prompt = (
                    f"Please explain the following answer in more detail, "
                    f"covering the underlying concepts and rationale:\n\n{last_answer[-2000:]}"
                )
                get_answer(
                    explain_prompt, collection, embedder, history[-4:],
                    bm25=bm25, corpus_texts=corpus_texts, kg=kg,
                    no_exec=True,
                    version_filter=args.version, category_filter=args.category,
                    model=selected_model,
                )
        elif q == "/model":
            show_model_info(model=selected_model)
        elif q == "/stats":
            print_stats(collection, chunks_file)

        # --- Search count ---
        elif q.startswith("search "):
            try:
                search_count = max(1, int(q.split()[1]))
                print(f"[Stats] Search results count set to {search_count}\n")
            except (IndexError, ValueError):
                print("Usage: search N  (e.g., search 10)\n")

        # --- Normal question ---
        else:
            # Context warning
            if not history:
                pass  # Fresh conversation, no warning needed
            elif len(last_answer) < 50 and history:
                print("  (Previous answer was short — context may be limited)\n")

            answer, docs = get_answer(
                q, collection, embedder, history,
                bm25=bm25, corpus_texts=corpus_texts, kg=kg,
                use_query_expansion=args.query_expansion,
                use_mmr=args.mmr, mmr_lambda=args.mmr_lambda,
                no_exec=args.no_exec, exec_timeout=args.exec_timeout,
                version_filter=args.version, category_filter=args.category,
                model=selected_model,
            )
            last_answer = answer
            last_docs = docs
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": answer})
            if len(history) > 20:
                history = history[-20:]


if __name__ == "__main__":
    main()
