"""
Data Ingestor for PythonAI OMNISCIENT
Ingests scraped JSON data from D: drive into the Chroma DB and Knowledge Graph without wiping existing data.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import chromadb

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.rag_engine import DB_PATH, CHUNKS_FILE
from src.rag.knowledge_graph import KnowledgeGraph

D_DRIVE_BASE = Path("D:/PythonAI_Data")
SO_DIR = D_DRIVE_BASE / "stackoverflow"
GITHUB_DIR = D_DRIVE_BASE / "github_code"


def parse_so_data() -> list[dict[str, Any]]:
    """Parse Stack Overflow data into generic chunks."""
    chunks = []
    if not SO_DIR.exists():
        return chunks

    for f in SO_DIR.glob("so_top_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for q in data:
                body = q.get("body", "")
                import re
                # Strip basic HTML tags
                body_clean = re.sub(r"<[^>]+>", "", body)
                chunks.append({
                    "id": f"so_q_{q.get('question_id')}",
                    "title": q.get("title", ""),
                    "text": body_clean,
                    "type": "so_question",
                    "category": "qa",
                    "tags": q.get("tags", []),
                })
        except Exception as e:
            print(f"Error reading {f}: {e}")

    for f in SO_DIR.glob("so_answers_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for a in data:
                body = a.get("body", "")
                import re
                body_clean = re.sub(r"<[^>]+>", "", body)
                chunks.append({
                    "id": f"so_a_{a.get('answer_id')}",
                    "title": f"Answer to {a.get('question_id')}",
                    "text": body_clean,
                    "type": "so_answer",
                    "category": "qa",
                })
        except Exception as e:
            print(f"Error reading {f}: {e}")

    return chunks


def parse_github_data() -> list[dict[str, Any]]:
    """Parse GitHub repos into generic chunks."""
    chunks = []
    if not GITHUB_DIR.exists():
        return chunks

    for f in GITHUB_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for r in data:
                desc = r.get("description") or ""
                chunks.append({
                    "id": f"gh_{r.get('name')}",
                    "title": r.get("name", ""),
                    "text": f"{r.get('name')}: {desc}",
                    "type": "github_repo",
                    "category": "repository",
                    "topics": r.get("topics", []),
                })
        except Exception as e:
            print(f"Error reading {f}: {e}")

    return chunks


def ingest_data() -> None:
    print("\n[Ingest] Parsing data from D: drive...")
    so_chunks = parse_so_data()
    gh_chunks = parse_github_data()
    all_new_chunks = so_chunks + gh_chunks

    print(f"  [+] Found {len(so_chunks)} SO chunks and {len(gh_chunks)} GitHub chunks.")

    if not all_new_chunks:
        print("  [!] No new data to ingest.")
        return

    # Update cleaned_chunks.json
    print(f"\n[Ingest] Updating master chunk list: {CHUNKS_FILE}")
    existing_chunks = []
    if CHUNKS_FILE.exists():
        try:
            existing_chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing_chunks = []
    
    # Filter out duplicates by ID
    existing_ids = {c.get("id") for c in existing_chunks if "id" in c}
    new_unique = [c for c in all_new_chunks if c.get("id") not in existing_ids]

    if not new_unique:
        print("  [!] All chunks already exist in database.")
        return

    print(f"  [+] Adding {len(new_unique)} new unique chunks.")
    existing_chunks.extend(new_unique)
    CHUNKS_FILE.write_text(json.dumps(existing_chunks, ensure_ascii=False), encoding="utf-8")

    # Ingest to Chroma
    print(f"\n[Ingest] Vectorizing into ChromaDB...")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_or_create_collection(
        name="python_godmode", metadata={"hnsw:space": "cosine"}
    )

    batch_size = 50
    for i in tqdm(range(0, len(new_unique), batch_size), desc="Embedding"):
        batch = new_unique[i : i + batch_size]
        texts = [
            f"Title: {c.get('title','')}\n"
            f"Type: {c.get('type','')}\n"
            f"Category: {c.get('category','')}\n\n"
            f"{c.get('text','')[:2000]}"
            for c in batch
        ]
        ids = [c.get("id") for c in batch]
        # fallback for missing ID
        ids = [str(abs(hash(t)))[:20] if not i else i for i, t in zip(ids, texts)]

        embs = embedder.encode(texts, batch_size=16, show_progress_bar=False).tolist()
        collection.add(
            documents=texts,
            embeddings=embs,
            ids=ids,
            metadatas=[
                {
                    "title": c.get("title", ""),
                    "type": c.get("type", "unknown"),
                    "category": c.get("category", "unknown")
                }
                for c in batch
            ],
        )

    # Ingest to KG
    print(f"\n[Ingest] Adding relationships to Knowledge Graph...")
    kg = KnowledgeGraph()
    try:
        kg.load()
    except Exception:
        pass

    kg.build_from_chunks(new_unique)
    kg.save()
    print(f"  [+] Knowledge Graph updated: {len(kg.graph.nodes)} nodes, {len(kg.graph.edges)} edges.")
    print("\n[DONE] Ingestion complete.")


if __name__ == "__main__":
    ingest_data()
