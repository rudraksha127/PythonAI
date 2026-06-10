"""
Continuous RAG Pipeline Indexer
================================
Scans collected JSONL data files from the anti-gravity data pipeline and
incrementally indexes them into ChromaDB + BM25 + KnowledgeGraph.

Key features:
  - State tracking: remembers which files + line counts have been indexed
  - Incremental: only indexes new files and new lines appended to existing files
  - Multi-source: handles OpenAlex, arXiv, HuggingFace, synthetic data formats
  - Smart chunking: splits long texts into overlapping chunks
  - Progress reporting: yields progress tuples for live server broadcasting
  - Batch embedding: processes 50 chunks at a time for efficiency

Usage:
    from src.rag.pipeline_indexer import RAGPipelineIndexer
    
    indexer = RAGPipelineIndexer()
    
    # Full index pass (scan all files)
    stats = await indexer.index_all()
    
    # Or run continuously
    async for progress in indexer.watch_and_index():
        print(f"Indexed: {progress}")
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import asyncio
from typing import Any, AsyncIterator, Callable

from loguru import logger

# Heavy imports are lazy (imported inside methods that use them)
# - sentence_transformers → _get_embedder()
# - chromadb             → _get_collection()
# - src.rag.knowledge_graph → _rebuild_post_index()

# ── Config ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "python_brain_godmode"
STATE_FILE = DB_PATH / "pipeline_index_state.json"
COLLECTION_NAME = "python_godmode"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 1000        # Max chars per chunk
CHUNK_OVERLAP = 200      # Overlap between chunks
BATCH_SIZE = 50           # Embedding batch size
MAX_TEXT_LENGTH = 100000  # Truncate texts longer than this before chunking
MAX_CHUNKS = 200          # Safety: don't create more than this per document


# ═══════════════════════════════════════════════
# CHUNK UTILITIES
# ═══════════════════════════════════════════════

def _make_chunk_id(source: str, doc_id: str, chunk_idx: int) -> str:
    """Create a stable unique chunk ID."""
    raw = f"{source}:{doc_id}:{chunk_idx}"
    return hashlib.md5(raw.encode()).hexdigest()[:24]


def _chunk_text(text: str, title: str = "", chunk_size: int = CHUNK_SIZE,
                overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split long text into overlapping chunks at sentence/paragraph boundaries."""
    # Truncate absurdly long texts
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        logger.debug(f"Text truncated from {len(text)} to {MAX_TEXT_LENGTH} chars")

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    safety = 0
    while start < len(text) and safety < MAX_CHUNKS:
        safety += 1
        end = min(start + chunk_size, len(text))

        # Try to break at a paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para = text.rfind("\n\n", start + chunk_size // 2, end)
            if para > start:
                end = para + 2  # Include the break
            else:
                # Look for sentence end
                sent = max(
                    text.rfind(". ", start + chunk_size // 2, end),
                    text.rfind("! ", start + chunk_size // 2, end),
                    text.rfind("? ", start + chunk_size // 2, end),
                    text.rfind("\n", start + chunk_size // 2, end),
                )
                if sent > start:
                    end = sent + 2

        chunks.append(text[start:end].strip())
        start = end - overlap

    return chunks


def _format_chunk_text(title: str, chunk_text: str, source: str,
                       category: str, extra: str = "") -> str:
    """Format a chunk with metadata prefix for embedding/search."""
    parts = [f"Title: {title[:100]}"]
    if source:
        parts.append(f"Source: {source}")
    if category:
        parts.append(f"Category: {category}")
    if extra:
        parts.append(extra)
    parts.append("")
    parts.append(chunk_text)
    return "\n".join(parts)


# ═══════════════════════════════════════════════
# SOURCE PARSERS
# ═══════════════════════════════════════════════

def _parse_lines(source_type: str, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Parse JSONL lines into standardised chunk dictionaries.

    Each output chunk has:
      - id:        unique chunk ID
      - title:     document title
      - text:      document body
      - source:    source name
      - category:  content category
      - type:      chunk type
    """
    chunks: list[dict[str, Any]] = []

    for line in lines:
        try:
            chunks.extend(_parse_single(source_type, line))
        except Exception as e:
            logger.debug(f"Parse error in {source_type}: {e}")
            continue

    return chunks


def _parse_preformatted(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Pass-through parser for chunks that are already perfectly formatted."""
    return [record]

def _parse_single(source_type: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a single record from a given source type into zero or more chunks."""
    if source_type in ("zip_docs", "pypi"):
        return _parse_preformatted(record)
    elif source_type == "openalex":
        return _parse_openalex(record)
    elif source_type == "arxiv":
        return _parse_arxiv(record)
    elif source_type == "huggingface":
        return _parse_huggingface(record)
    elif source_type in ("synthetic", "parallel_llm"):
        return _parse_synthetic(record)
    else:
        return _parse_generic(record)

def _parse_openalex(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse an OpenAlex research paper record."""
    doc_id = record.get("id", "")
    title = (record.get("title") or "").strip()
    abstract = (record.get("abstract") or "").strip()
    year = record.get("year", "")
    citations = record.get("citations", 0)

    # Combine title + abstract into searchable text
    full_text = f"{title}\n\n{abstract}" if title and abstract else (title or abstract)
    if not full_text:
        return []

    chunks = []
    text_chunks = _chunk_text(full_text, title)
    for i, chunk_text in enumerate(text_chunks):
        extra = f"Year: {year} | Citations: {citations}" if year else ""
        chunks.append({
            "id": _make_chunk_id("openalex", doc_id or title, i),
            "title": title[:200] or f"OpenAlex Paper ({year})",
            "text": _format_chunk_text(title, chunk_text, "OpenAlex", "research_paper", extra),
            "source": "openalex",
            "category": "research_paper",
            "type": "openalex_work",
            "year": year,
            "citations": citations,
        })
    return chunks


def _parse_arxiv(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse an arXiv paper record."""
    doc_id = record.get("id", "")
    title = (record.get("title") or "").strip()
    abstract = (record.get("abstract") or "").strip()
    categories = (record.get("categories") or "")
    created = (record.get("created") or "")

    full_text = f"{title}\n\n{abstract}" if title and abstract else (title or abstract)
    if not full_text:
        return []

    category_clean = categories.split()[0] if categories else "cs"
    chunks = []
    text_chunks = _chunk_text(full_text, title)
    for i, chunk_text in enumerate(text_chunks):
        extra = f"Categories: {categories}" if categories else ""
        if created:
            extra += f" | Created: {created}" if extra else f"Created: {created}"
        chunks.append({
            "id": _make_chunk_id("arxiv", doc_id or title, i),
            "title": title[:200] or f"arXiv Paper ({category_clean})",
            "text": _format_chunk_text(title, chunk_text, "arXiv", "research_paper", extra),
            "source": "arxiv",
            "category": "research_paper",
            "type": f"arxiv_{category_clean}",
        })
    return chunks


def _parse_huggingface(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a HuggingFace dataset record."""
    # HF records vary widely; extract text fields intelligently
    title = (record.get("title") or record.get("name") or "").strip()
    text = (record.get("text") or record.get("content") or
            record.get("body") or record.get("description") or json.dumps(record, ensure_ascii=False)).strip()

    if not text:
        return []

    if len(text) > 200:
        chunks = []
        text_chunks = _chunk_text(text, title)
        for i, chunk_text in enumerate(text_chunks):
            chunks.append({
                "id": _make_chunk_id("huggingface", title or str(hash(text))[:12], i),
                "title": title[:200] or "HF Dataset Record",
                "text": _format_chunk_text(title or "Dataset", chunk_text, "HuggingFace", "dataset"),
                "source": "huggingface",
                "category": "dataset",
                "type": "hf_record",
            })
        return chunks

    return [{
        "id": _make_chunk_id("huggingface", title or str(hash(text))[:12], 0),
        "title": title[:200] or "HF Dataset Record",
        "text": _format_chunk_text(title or "Dataset", text, "HuggingFace", "dataset"),
        "source": "huggingface",
        "category": "dataset",
        "type": "hf_record",
    }]


def _parse_synthetic(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a synthetic training data record."""
    task_type = record.get("task_type", "generic")
    instruction = (record.get("instruction") or "").strip()
    output = (record.get("output") or "").strip()

    if not instruction or not output:
        return []

    # Store instruction as the searchable document, output as additional metadata
    full_text = f"Task: {instruction}\n\nOutput: {output}"
    chunks = []
    text_chunks = _chunk_text(full_text, instruction)
    for i, chunk_text in enumerate(text_chunks):
        chunks.append({
            "id": _make_chunk_id("synthetic", task_type + instruction[:40], i),
            "title": f"[Synthetic] {instruction[:120]}",
            "text": _format_chunk_text(instruction, chunk_text, "Synthetic", task_type),
            "source": "synthetic",
            "category": task_type,
            "type": "synthetic",
        })
    return chunks


def _parse_generic(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Generic parser for unknown data formats — extract text fields heuristically."""
    title = (record.get("title") or record.get("name") or record.get("id") or "").strip()
    text_fields = []
    for key in ("text", "content", "body", "description", "abstract",
                "output", "response", "answer", "code", "prompt", "instruction"):
        val = record.get(key)
        if val and isinstance(val, str) and len(val) > 20:
            text_fields.append(f"{key.capitalize()}: {val.strip()}")

    full_text = "\n\n".join(text_fields) if text_fields else json.dumps(record, ensure_ascii=False)[:2000]
    if not full_text:
        return []

    chunk_texts = _chunk_text(full_text, title)
    chunks = []
    for i, ct in enumerate(chunk_texts):
        chunks.append({
            "id": _make_chunk_id("generic", title or str(hash(full_text))[:12], i),
            "title": title[:200] or "Unknown Record",
            "text": _format_chunk_text(title or "Document", ct, "unknown", "unknown"),
            "source": "unknown",
            "category": "unknown",
            "type": "generic",
        })
    return chunks


# ═══════════════════════════════════════════════
# STATE TRACKING
# ═══════════════════════════════════════════════

class IndexState:
    """Tracks which files have been indexed to enable incremental indexing."""

    def __init__(self, state_path: Path = STATE_FILE):
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save(self) -> None:
        self.state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_file_state(self, file_path: str) -> dict[str, Any]:
        return self._state.get(file_path, {"lines": 0, "mtime": 0, "chunks": 0})

    def mark_indexed(self, file_path: str, lines_indexed: int,
                     chunks_added: int, mtime: float) -> None:
        self._state[file_path] = {
            "lines": lines_indexed,
            "mtime": mtime,
            "chunks": self._state.get(file_path, {}).get("chunks", 0) + chunks_added,
        }
        self.save()

    def needs_update(self, file_path: str, current_lines: int, current_mtime: float) -> bool:
        state = self.get_file_state(file_path)
        if state["mtime"] == 0:
            return True  # New file
        if current_mtime > state["mtime"]:
            return True  # Modified
        if current_lines > state["lines"]:
            return True  # Appended to
        if state["lines"] == 0 and current_lines > 0:
            return True  # Previously empty, now has data
        return False

    def reset(self, file_path: str | None = None) -> None:
        if file_path:
            self._state.pop(file_path, None)
        else:
            self._state.clear()
        self.save()


# ═══════════════════════════════════════════════
# PIPELINE INDEXER
# ═══════════════════════════════════════════════

class RAGPipelineIndexer:
    """
    Scans JSONL data files and incrementally indexes them into the RAG stack.

    Usage:
        indexer = RAGPipelineIndexer(data_dir="D:/PythonAI_Data/anti_gravity_data")

        # Single pass
        stats = await indexer.index_all()

        # Continuous (yields progress tuples)
        async for progress in indexer.watch_and_index(interval=60):
            print(progress)
    """

    def __init__(
        self,
        data_dir: str | Path = "D:/PythonAI_Data/anti_gravity_data",
        db_path: str | Path = DB_PATH,
        collection_name: str = COLLECTION_NAME,
        progress_callback: Callable | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        self.collection_name = collection_name
        self.progress_callback = progress_callback

        # Embedder (lazy-loaded — type imported inside _get_embedder)
        self._embedder: object | None = None
        # ChromaDB client (lazy-loaded)
        self._client = None
        self._collection = None
        # Index state tracker
        self.state = IndexState()

        # Accumulated stats
        self.stats = {
            "files_scanned": 0,
            "files_indexed": 0,
            "lines_indexed": 0,
            "chunks_indexed": 0,
            "errors": 0,
            "total_chunks": 0,
            "total_files": 0,
        }

        # Source type detection by filename prefix
        self.source_map = {
            "machine_learning": "openalex",
            "artificial_intelligence": "openalex",
            "neural_network": "openalex",
            "natural_language_processing": "openalex",
            "computer_vision": "openalex",
            "quantum_computing": "openalex",
            "reasoning_chains": "synthetic",
            "code_with_tests": "synthetic",
            "tool_use_agents": "synthetic",
            "hindi_bilingual": "synthetic",
            "scientific_qa": "synthetic",
            "creative_writing": "synthetic",
            "data_analysis": "synthetic",
            "system_design": "synthetic",
            "zip_docs_chunks": "zip_docs",
            "pypi_knowledge_base": "pypi",
        }

    # ── Lazy init ──────────────────────────

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            logger.info("[RAG] Loading embedding model...")
            self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedder

    def _get_collection(self):
        """Get or create the ChromaDB collection."""
        if self._collection is not None:
            return self._collection

        import chromadb
        self._client = chromadb.PersistentClient(path=str(self.db_path))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        count = self._collection.count()
        logger.info(f"[RAG] ChromaDB collection '{self.collection_name}': {count:,} existing chunks")
        return self._collection

    # ── File scanning ──────────────────────

    def _detect_source_type(self, file_path: Path) -> str:
        """Detect source type from filename."""
        stem = file_path.stem
        for prefix, source in self.source_map.items():
            if stem.startswith(prefix):
                return source
        # Detect from parent directory
        parent = file_path.parent.name
        if parent in ("openalex", "arxiv", "huggingface", "synthetic"):
            return parent
        return "unknown"

    def _scan_files(self) -> list[Path]:
        """Find all JSONL files in the data directory."""
        if not self.data_dir.exists():
            logger.warning(f"[RAG] Data directory not found: {self.data_dir}")
            return []

        files = sorted(self.data_dir.rglob("*.jsonl"))
        logger.info(f"[RAG] Found {len(files)} JSONL files in {self.data_dir}")
        return files

    # ── Indexing pipeline ──────────────────

    async def index_all(self) -> dict[str, Any]:
        """
        Scan all JSONL files and index any new/modified content.

        Returns stats dictionary.
        """
        files = self._scan_files()
        self.stats["files_scanned"] = len(files)

        for file_path in files:
            await self._index_file(file_path)

        # Rebuild BM25 + KG after all new chunks are added
        if self.stats["chunks_indexed"] > 0:
            await self._rebuild_post_index()

        return dict(self.stats)

    async def index_file(self, file_path: str | Path) -> dict[str, Any]:
        """Index a single file by path. Returns per-file stats."""
        return await self._index_file(Path(file_path))

    async def _index_file(self, file_path: Path) -> dict[str, Any]:
        """Index a single file. Returns per-file stats."""
        file_stats = {
            "file": str(file_path),
            "new_lines": 0,
            "new_chunks": 0,
            "error": None,
        }

        try:
            # Check if file exists and has content
            if not file_path.exists() or file_path.stat().st_size == 0:
                return file_stats

            current_mtime = file_path.stat().st_mtime
            source_type = self._detect_source_type(file_path)

            # Read all lines
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = [line.strip() for line in f if line.strip()]

            total_lines = len(all_lines)
            file_state = self.state.get_file_state(str(file_path))
            already_indexed = file_state["lines"]

            # Determine which lines are new
            if total_lines <= already_indexed:
                return file_stats  # Already fully indexed

            new_lines = all_lines[already_indexed:]
            if not new_lines:
                return file_stats

            # Parse new lines into chunks
            parsed = []
            for line in new_lines:
                try:
                    record = json.loads(line)
                    parsed.append(record)
                except json.JSONDecodeError:
                    continue

            if not parsed:
                return file_stats

            chunks = _parse_lines(source_type, parsed)
            if not chunks:
                return file_stats

            # Index into ChromaDB
            await self._index_chunks(chunks, source_type)

            # Update state
            chunks_count = len(chunks)
            self.state.mark_indexed(
                str(file_path),
                total_lines,
                chunks_count,
                current_mtime,
            )

            file_stats["new_lines"] = len(new_lines)
            file_stats["new_chunks"] = chunks_count

            self.stats["files_indexed"] += 1
            self.stats["lines_indexed"] += len(new_lines)
            self.stats["chunks_indexed"] += chunks_count
            self.stats["total_chunks"] = self.stats.get("total_chunks", 0) + chunks_count

            source_label = file_path.parent.name
            logger.info(f"[RAG] ✓ {source_label}/{file_path.name}: "
                        f"{len(new_lines)} new lines → {chunks_count} chunks")

        except Exception as e:
            file_stats["error"] = str(e)[:200]
            self.stats["errors"] += 1
            logger.error(f"[RAG] ✗ Error indexing {file_path.name}: {e}")

        return file_stats

    # ── ChromaDB indexing ──────────────────

    async def _index_chunks(self, chunks: list[dict[str, Any]],
                            source_type: str) -> None:
        """Embed and add chunks to ChromaDB in batches."""
        if not chunks:
            return

        collection = self._get_collection()
        embedder = self._get_embedder()
        batch_size = BATCH_SIZE

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            texts = [c["text"] for c in batch]
            ids = [c["id"] for c in batch]
            metadatas = [
                {
                    "title": c.get("title", "")[:200],
                    "source": c.get("source", source_type),
                    "category": c.get("category", "unknown"),
                    "type": c.get("type", source_type),
                }
                for c in batch
            ]

            try:
                embeddings = embedder.encode(
                    texts,
                    batch_size=16,
                    show_progress_bar=False,
                ).tolist()

                collection.add(
                    documents=texts,
                    embeddings=embeddings,
                    ids=ids,
                    metadatas=metadatas,
                )
            except Exception as e:
                logger.error(f"[RAG] Embedding batch failed: {e}")
                # Try one by one for partial success
                for j, text in enumerate(texts):
                    try:
                        emb = embedder.encode([text]).tolist()[0]
                        collection.add(
                            documents=[text],
                            embeddings=[emb],
                            ids=[ids[j]],
                            metadatas=[metadatas[j]],
                        )
                    except Exception as e2:
                        logger.debug(f"[RAG] Skipping chunk {ids[j]}: {e2}")

            # Progress callback (for live server streaming)
            if self.progress_callback:
                try:
                    await self.progress_callback({
                        "phase": "RAG Pipeline Indexing",
                        "source": source_type,
                        "indexed": min(i + batch_size, len(chunks)),
                        "total": len(chunks),
                    })
                except Exception:
                    pass

    # ── Post-index rebuild (BM25 + KG) ─────

    async def _rebuild_post_index(self) -> None:
        """
        After all files are scanned, rebuild BM25 and update KnowledgeGraph.
        Runs as a background task.
        """
        collection = self._get_collection()
        logger.info("[RAG] Post-index: rebuilding BM25 & updating KnowledgeGraph...")

        # Load all documents from ChromaDB
        try:
            count = collection.count()
            all_docs: list[str] = []
            batch_size = 200

            for offset in range(0, count, batch_size):
                batch = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                if batch and batch.get("documents"):
                    all_docs.extend(batch["documents"])

            logger.info(f"[RAG] Loaded {len(all_docs)} documents for BM25 rebuild")

            # Rebuild BM25 in the existing rag_engine
            if all_docs:
                from src.rag.rag_engine import SimpleBM25
                bm25_path = DB_PATH / "bm25_index.pkl"
                bm25 = SimpleBM25(all_docs)
                try:
                    import pickle
                    bm25_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(bm25_path, "wb") as f:
                        pickle.dump(bm25, f)
                    logger.info(f"[RAG] BM25 index saved ({len(all_docs)} docs)")
                except Exception as e:
                    logger.warning(f"[RAG] Could not persist BM25: {e}")

            # Update KnowledgeGraph incrementally
            try:
                from src.rag.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph()
                kg.load()

                # Build chunk dictionaries from documents for KG update
                kg_chunks = []
                for offset in range(0, count, batch_size):
                    batch = collection.get(
                        limit=batch_size,
                        offset=offset,
                        include=["documents", "metadatas"],
                    )
                    if not batch or not batch.get("documents"):
                        continue
                    for doc, meta in zip(batch["documents"], batch["metadatas"]):
                        kg_chunks.append({
                            "id": meta.get("title", "")[:24] or "unknown",
                            "title": meta.get("title", ""),
                            "text": doc,
                            "category": meta.get("category", "unknown"),
                            "type": meta.get("type", "unknown"),
                            "version": "",
                        })

                if kg_chunks:
                    kg.build_from_chunks(kg_chunks)
                    kg.save()
                    logger.info(f"[RAG] KnowledgeGraph updated: "
                                f"{kg.graph.number_of_nodes()} nodes, "
                                f"{kg.graph.number_of_edges()} edges")
            except Exception as e:
                logger.warning(f"[RAG] KG update skipped: {e}")

        except Exception as e:
            logger.error(f"[RAG] Post-index rebuild error: {e}")

    # ── Continuous watching ────────────────

    async def watch_and_index(self, interval: int = 60) -> AsyncIterator[dict[str, Any]]:
        """
        Continuously scan for new/modified files and index them.

        Yields progress dictionaries after each scan cycle.
        """
        while True:
            stats = await self.index_all()
            yield stats
            await asyncio.sleep(interval)

    # ── Reset ──────────────────────────────

    def reset_state(self, file_path: str | None = None) -> None:
        """Reset index state for a file or all files."""
        self.state.reset(file_path)
        logger.info(f"[RAG] Index state reset for {'all files' if file_path is None else file_path}")


# ═══════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG Pipeline Indexer")
    parser.add_argument("--dir", default="D:/PythonAI_Data/anti_gravity_data",
                        help="Data directory to scan")
    parser.add_argument("--reset", action="store_true",
                        help="Reset all index state and re-index from scratch")
    parser.add_argument("--stats", action="store_true",
                        help="Show current index state and exit")
    args = parser.parse_args()

    async def cli():
        indexer = RAGPipelineIndexer(data_dir=args.dir)

        if args.reset:
            indexer.reset_state()
            print("[RAG] State reset. Re-indexing all files...")

        if args.stats:
            print(f"[RAG] Index state:")
            state = indexer.state._state
            if not state:
                print("  No files indexed yet.")
            else:
                for fpath, fstate in sorted(state.items()):
                    print(f"  {fpath}")
                    print(f"    Lines: {fstate.get('lines', 0)}, "
                          f"Chunks: {fstate.get('chunks', 0)}, "
                          f"Mtime: {fstate.get('mtime', 0)}")
            return

        print(f"[RAG] Starting index pass on: {args.dir}")
        stats = await indexer.index_all()
        print(f"\n[RAG] Index complete:")
        print(f"  Files scanned:  {stats['files_scanned']}")
        print(f"  Files indexed:  {stats['files_indexed']}")
        print(f"  Lines indexed:  {stats['lines_indexed']}")
        print(f"  Chunks indexed: {stats['chunks_indexed']}")
        print(f"  Errors:         {stats['errors']}")
        print(f"  Total chunks:   {stats.get('total_chunks', 0)}")

    asyncio.run(cli())
