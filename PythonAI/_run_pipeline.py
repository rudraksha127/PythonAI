#!/usr/bin/env python3
"""
Run the ForgeAI data pipeline — Phase 1 (limited scope).
Produces a training dataset at DATA_DIR and then builds the RAG index.

Steps:
  1. Set DATA_DIR to a writable location
  2. Run massive engine for one pass with limited sources (arXiv + Wikipedia + GitHub)
  3. After pipeline completes, build RAG index from the generated data
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Set data directory
DATA_DIR = Path.home() / ".forgeai" / "training_data"
os.environ["DATA_DIR"] = str(DATA_DIR)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ---- Phase 1: Run data pipeline ----

async def run_pipeline():
    """Run the data pipeline with limited scope for fast execution."""
    from src.data.massive_engine import MassiveWorkerEngine

    async def log(**kw):
        print(f"  [{kw.get('level', 'info').upper()}] {kw.get('msg', '')}")

    async def progress(**kw):
        total = kw.get("total_collected", 0)
        source = kw.get("source", "")
        print(f"  📊 Records: {total:,} (source: {source})")

    print("=" * 60)
    print("PHASE 1 — Data Pipeline")
    print("=" * 60)
    print(f"Output dir: {DATA_DIR}")
    print()

    # Create engine with limited concurrency for local use
    engine = MassiveWorkerEngine(
        max_concurrent=50,
        log_callback=log,
        progress_callback=progress,
    )

    # Run one pass through ALL sources
    print("Running pipeline pass (this fetches from external APIs)...")
    start = time.time()

    stats = await engine.run_pass()

    elapsed = time.time() - start
    print(f"\nPipeline pass complete in {elapsed:.1f}s")
    print(f"  Sources total:      {stats['sources_total']}")
    print(f"  Sources with data:  {stats['sources_with_data']}")
    print(f"  Records collected:  {stats['total_collected']:,}")
    print(f"  Errors:             {stats['total_errors']}")
    print(f"  Concurrency:        {stats['effective_concurrency']}")

    await engine.close()
    return stats


# ---- Phase 2: Generate a synthetic local dataset if pipeline produced little/no data ----

def generate_synthetic_dataset():
    """Generate a minimal synthetic dataset for local training/testing."""
    print("\n" + "=" * 60)
    print("Generating synthetic training dataset")
    print("=" * 60)

    output_dir = DATA_DIR / "synthetic" / "phase1"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Python coding examples
    python_examples = [
        {"instruction": "Write a function to reverse a linked list",
         "response": "def reverse_linked_list(head):\n    prev = None\n    current = head\n    while current:\n        next_node = current.next\n        current.next = prev\n        prev = current\n        current = next_node\n    return prev",
         "language": "python", "domain": "coding"},
        {"instruction": "Implement binary search",
         "response": "def binary_search(arr, target):\n    left, right = 0, len(arr) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
         "language": "python", "domain": "coding"},
        {"instruction": "Create a Python decorator to measure execution time",
         "response": "import time\nfrom functools import wraps\n\ndef timer(func):\n    @wraps(func)\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        elapsed = time.time() - start\n        print(f'{func.__name__} took {elapsed:.4f}s')\n        return result\n    return wrapper",
         "language": "python", "domain": "coding"},
    ]

    # RAG/documentation examples
    rag_examples = [
        {"title": "Getting Started with FastAPI",
         "content": "FastAPI is a modern web framework for building APIs with Python. It uses Pydantic for data validation and ASGI for async support. Install with: pip install fastapi uvicorn",
         "domain": "documentation"},
        {"title": "Python Async/Await Guide",
         "content": "Async/await in Python allows concurrent execution using asyncio. Use 'async def' to define coroutines and 'await' to call them. Run with asyncio.run().",
         "domain": "documentation"},
        {"title": "Understanding RAG (Retrieval Augmented Generation)",
         "content": "RAG combines retrieval from a knowledge base with LLM generation. Documents are chunked, embedded, and stored in a vector DB. At query time, relevant chunks are retrieved and fed to the LLM as context.",
         "domain": "ml"},
    ]

    # Write synthetic coding dataset
    coding_file = output_dir / "python_coding.jsonl"
    with open(coding_file, "w", encoding="utf-8") as f:
        for ex in python_examples:
            f.write(json.dumps(ex) + "\n")
    print(f"  Wrote {len(python_examples)} coding examples to {coding_file}")

    # Write synthetic RAG dataset
    rag_file = output_dir / "rag_docs.jsonl"
    with open(rag_file, "w", encoding="utf-8") as f:
        for ex in rag_examples:
            f.write(json.dumps(ex) + "\n")
    print(f"  Wrote {len(rag_examples)} RAG docs to {rag_file}")

    return coding_file, rag_file


# ---- Phase 3: Build RAG index from the generated data ----

def build_rag_index():
    """Build a RAG index from the generated dataset using ChromaDB."""
    print("\n" + "=" * 60)
    print("Building RAG Index")
    print("=" * 60)

    # Discover all JSONL files in the data directory
    jsonl_files = list(DATA_DIR.rglob("*.jsonl"))
    print(f"Found {len(jsonl_files)} JSONL files in {DATA_DIR}")

    # Load all content
    all_docs = []
    for filepath in jsonl_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            doc = json.loads(line)
                            # Extract text content
                            text = doc.get("content") or doc.get("text") or doc.get("response") or doc.get("abstract") or doc.get("instruction", "")
                            if text:
                                all_docs.append({
                                    "text": text[:2000],
                                    "source": str(filepath.relative_to(DATA_DIR)),
                                    "metadata": {k: v for k, v in doc.items() if k not in ("text", "content", "response")},
                                })
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"  Warning: Could not read {filepath}: {e}")

    print(f"  Total documents loaded: {len(all_docs)}")

    if not all_docs:
        print("  No documents to index!")
        return None

    # Build ChromaDB index
    try:
        from chromadb import PersistentClient
        
        chroma_dir = Path.home() / ".forgeai" / "chroma_db"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        client = PersistentClient(path=str(chroma_dir))
        collection = client.get_or_create_collection(
            name="forgeai_training",
            metadata={"description": "ForgeAI training dataset RAG index"}
        )
        
        # Add documents in batches
        batch_size = 100
        for i in range(0, len(all_docs), batch_size):
            batch = all_docs[i:i+batch_size]
            ids = [f"doc_{i+j}" for j in range(len(batch))]
            texts = [d["text"] for d in batch]
            metadatas = [d["metadata"] for d in batch]
            
            # Ensure metadata values are strings, ints, or floats (Chromadb requirement)
            clean_metadatas = []
            for m in metadatas:
                clean = {}
                for k, v in m.items():
                    if isinstance(v, (str, int, float, bool)):
                        clean[k] = v
                    elif isinstance(v, list):
                        clean[k] = str(v)[:200]
                    elif v is None:
                        clean[k] = ""
                    else:
                        clean[k] = str(v)[:200]
                clean_metadatas.append(clean)
            
            collection.add(
                ids=ids,
                documents=texts,
                metadatas=clean_metadatas,
            )
        
        count = collection.count()
        print(f"  Indexed {count} documents into ChromaDB at {chroma_dir}")
        return {"chroma_dir": str(chroma_dir), "documents": count}
    
    except ImportError:
        print("  ChromaDB not installed. Run: pip install chromadb")
        return None
    except Exception as e:
        print(f"  Error building ChromaDB index: {e}")
        import traceback
        traceback.print_exc()
        return None


# ---- Main ----

async def main():
    # Step 1: Run the data pipeline
    try:
        stats = await run_pipeline()
        total_records = stats.get("total_collected", 0)
    except Exception as e:
        print(f"\nPipeline error (non-fatal): {e}")
        total_records = 0

    # Step 2: If pipeline produced little data, generate synthetic
    if total_records < 10:
        print("\nPipeline produced minimal data. Generating synthetic dataset...")
        generate_synthetic_dataset()

    # Step 3: Build RAG index
    result = build_rag_index()
    
    print("\n" + "=" * 60)
    if result:
        print(f"✅ RAG index built successfully: {result['documents']} documents")
    else:
        print("⚠️  RAG index could not be built. Check dependencies.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
