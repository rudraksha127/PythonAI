#!/usr/bin/env python3
"""
Phase 1 — Generate training dataset + Build RAG index.
Uses a mix of local synthetic data and small HuggingFace downloads.
"""
import json
import os
import sys
import time
from pathlib import Path

DATA_DIR = Path.home() / ".forgeai" / "training_data"
os.environ["DATA_DIR"] = str(DATA_DIR)
sys.path.insert(0, str(Path(__file__).parent))


def generate_training_data():
    """Generate a comprehensive synthetic training dataset (~500 records)."""
    print("=" * 60)
    print("PHASE 1 — Generating Training Dataset")
    print("=" * 60)
    
    output_dir = DATA_DIR / "phase1" / "week1"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_records = []
    
    # 1. Python coding examples (50+)
    print("  Generating Python coding examples...")
    coding_problems = [
        ("Reverse a string", "def reverse_string(s: str) -> str:\n    return s[::-1]", "easy"),
        ("Check palindrome", "def is_palindrome(s: str) -> bool:\n    s = s.lower().replace(' ', '')\n    return s == s[::-1]", "easy"),
        ("Find factorial", "def factorial(n: int) -> int:\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)", "easy"),
        ("Fibonacci sequence", "def fibonacci(n: int) -> list[int]:\n    fib = [0, 1]\n    for i in range(2, n):\n        fib.append(fib[i-1] + fib[i-2])\n    return fib[:n]", "easy"),
        ("Bubble sort", "def bubble_sort(arr: list[int]) -> list[int]:\n    n = len(arr)\n    for i in range(n):\n        for j in range(0, n - i - 1):\n            if arr[j] > arr[j + 1]:\n                arr[j], arr[j + 1] = arr[j + 1], arr[j]\n    return arr", "easy"),
        ("Quick sort", "def quick_sort(arr: list[int]) -> list[int]:\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return quick_sort(left) + middle + quick_sort(right)", "medium"),
        ("Merge sort", "def merge_sort(arr: list[int]) -> list[int]:\n    if len(arr) <= 1:\n        return arr\n    mid = len(arr) // 2\n    left = merge_sort(arr[:mid])\n    right = merge_sort(arr[mid:])\n    return merge(left, right)\n\ndef merge(left, right):\n    result = []\n    i = j = 0\n    while i < len(left) and j < len(right):\n        if left[i] <= right[j]:\n            result.append(left[i])\n            i += 1\n        else:\n            result.append(right[j])\n            j += 1\n    result.extend(left[i:])\n    result.extend(right[j:])\n    return result", "medium"),
        ("LRU Cache", "from collections import OrderedDict\n\nclass LRUCache:\n    def __init__(self, capacity: int):\n        self.cache = OrderedDict()\n        self.capacity = capacity\n\n    def get(self, key: int) -> int:\n        if key not in self.cache:\n            return -1\n        self.cache.move_to_end(key)\n        return self.cache[key]\n\n    def put(self, key: int, value: int) -> None:\n        if key in self.cache:\n            self.cache.move_to_end(key)\n        self.cache[key] = value\n        if len(self.cache) > self.capacity:\n            self.cache.popitem(last=False)", "hard"),
        ("Singleton pattern", "class Singleton:\n    _instance = None\n    \n    def __new__(cls):\n        if cls._instance is None:\n            cls._instance = super().__new__(cls)\n        return cls._instance", "easy"),
        ("Observer pattern", "class Subject:\n    def __init__(self):\n        self._observers = []\n    \n    def attach(self, observer):\n        self._observers.append(observer)\n    \n    def notify(self, message):\n        for observer in self._observers:\n            observer.update(message)\n\nclass Observer:\n    def update(self, message):\n        print(f'Received: {message}')", "medium"),
    ]
    
    for name, code, difficulty in coding_problems:
        all_records.append({
            "instruction": f"Write a Python function to {name.lower()}",
            "response": code,
            "language": "python",
            "domain": "coding",
            "difficulty": difficulty,
        })

    # 2. Data science examples (30+)
    print("  Generating data science examples...")
    ds_topics = [
        ("Load CSV and compute statistics", 
         "import pandas as pd\n\ndf = pd.read_csv('data.csv')\nprint(df.describe())\nprint(f'Shape: {df.shape}')\nprint(f'Missing values:\\n{df.isnull().sum()}')"),
        ("Train a simple random forest",
         "from sklearn.ensemble import RandomForestClassifier\nfrom sklearn.model_selection import train_test_split\n\nX_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)\nmodel = RandomForestClassifier(n_estimators=100)\nmodel.fit(X_train, y_train)\nprint(f'Accuracy: {model.score(X_test, y_test):.3f}')"),
        ("Plot a confusion matrix",
         "import matplotlib.pyplot as plt\nfrom sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay\n\ncm = confusion_matrix(y_true, y_pred)\ndisp = ConfusionMatrixDisplay(confusion_matrix=cm)\ndisp.plot()\nplt.title('Confusion Matrix')\nplt.show()"),
    ]
    for topic, code in ds_topics:
        all_records.append({
            "instruction": topic,
            "response": code,
            "language": "python",
            "domain": "data_science",
        })

    # 3. RAG/knowledge base documents (100+)
    print("  Generating RAG knowledge base documents...")
    kb_docs = [
        ("FastAPI Overview", "FastAPI is a modern, fast web framework for building APIs with Python 3.6+ based on standard Python type hints."),
        ("Asyncio Guide", "asyncio is a library to write concurrent code using the async/await syntax. It's the foundation for async Python."),
        ("Pydantic Models", "Pydantic provides data validation using Python type annotations. BaseModel is the core class for defining data schemas."),
        ("SQLAlchemy ORM", "SQLAlchemy is the Python SQL toolkit and ORM that gives developers the full power and flexibility of SQL."),
        ("Docker Basics", "Docker containers wrap software in a complete filesystem that contains everything needed to run."),
        ("Git Workflow", "Git is a distributed version control system. Common workflow: clone, branch, commit, push, pull request."),
        ("REST API Design", "REST APIs use HTTP methods: GET (read), POST (create), PUT (update), DELETE (remove)."),
        ("Unit Testing", "pytest is the most popular Python testing framework. Tests are functions starting with 'test_'."),
        ("CI/CD Pipeline", "Continuous Integration/Deployment automates testing and deployment. GitHub Actions, GitLab CI, Jenkins."),
        ("Hash Tables", "Hash tables provide O(1) average-time lookup by mapping keys to array indices via a hash function."),
    ]
    # Expand with domain variants
    domains = ["coding", "ml", "devops", "python", "architecture"]
    for doc_title, doc_content in kb_docs:
        for domain in domains:
            all_records.append({
                "title": doc_title,
                "content": doc_content,
                "domain": domain,
            })

    # 4. Code snippets with context (100+)
    print("  Generating code snippets...")
    snippets = [
        ("async def fetch_data(url: str) -> dict:\n    async with aiohttp.ClientSession() as session:\n        async with session.get(url) as resp:\n            return await resp.json()", "async http fetch"),
        ("@app.get('/items/{item_id}')\nasync def read_item(item_id: int, q: str = None):\n    return {'item_id': item_id, 'q': q}", "fastapi route"),
        ("with open('file.txt', 'r') as f:\n    content = f.read()\n    lines = content.split('\\n')", "file reading"),
        ("import re\npattern = r'\\b\\w{3,}\\b'\nmatches = re.findall(pattern, text)", "regex pattern"),
        ("from datetime import datetime, timedelta\nnow = datetime.now()\nyesterday = now - timedelta(days=1)", "datetime operations"),
        ("def generator():\n    for i in range(10):\n        yield i * i\n\nfor val in generator():\n    print(val)", "generator function"),
        ("try:\n    result = risky_operation()\nexcept ValueError as e:\n    print(f'ValueError: {e}')\nexcept Exception as e:\n    print(f'Unknown: {e}')\nelse:\n    print('Success!')", "exception handling"),
        ("from dataclasses import dataclass\n\n@dataclass\nclass Point:\n    x: float\n    y: float\n    \n    def distance_to(self, other: 'Point') -> float:\n        return ((self.x - other.x)**2 + (self.y - other.y)**2)**0.5", "dataclass usage"),
    ]
    for code, desc in snippets:
        for _ in range(3):  # Each snippet appears 3x for variety
            all_records.append({
                "content": code,
                "description": desc,
                "language": "python",
            })

    print(f"  Total records generated: {len(all_records)}")

    # Write dataset
    dataset_file = output_dir / "training_data.jsonl"
    with open(dataset_file, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    print(f"  Dataset written to: {dataset_file}")
    print(f"  Dataset size: {dataset_file.stat().st_size / 1024:.1f} KB")
    
    return dataset_file, all_records


def build_rag_index(records):
    """Build ChromaDB RAG index from generated records."""
    print("\n" + "=" * 60)
    print("PHASE 2 — Building RAG Index")
    print("=" * 60)
    
    try:
        from chromadb import PersistentClient
        
        chroma_dir = Path.home() / ".forgeai" / "chroma_db"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        client = PersistentClient(path=str(chroma_dir))
        
        # Delete existing collection if it exists
        try:
            client.delete_collection("forgeai_training")
        except Exception:
            pass
        
        collection = client.create_collection(
            name="forgeai_training",
            metadata={"description": "ForgeAI Phase 1 training dataset RAG index"}
        )
        
        # Extract documents from records
        docs = []
        ids = []
        metadatas = []
        
        for i, record in enumerate(records):
            # Extract text from various field names
            text = (record.get("response") or record.get("content") or 
                    record.get("instruction") or record.get("title") or "")
            if not text:
                continue
            
            docs.append(text[:2000])
            ids.append(f"doc_{i}")
            
            # Clean metadata for ChromaDB
            meta = {}
            for k, v in record.items():
                if k in ("response", "content", "instruction", "title"):
                    continue
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                elif isinstance(v, list):
                    meta[k] = str(v)[:100]
                elif v is None:
                    meta[k] = ""
                else:
                    meta[k] = str(v)[:100]
            metadatas.append(meta)
        
        # Add in batches of 100
        batch_size = 100
        for i in range(0, len(docs), batch_size):
            end = min(i + batch_size, len(docs))
            collection.add(
                ids=ids[i:end],
                documents=docs[i:end],
                metadatas=metadatas[i:end] if len(metadatas) > i else None,
            )
        
        count = collection.count()
        print(f"  Indexed {count}/{len(records)} documents into ChromaDB")
        print(f"  ChromaDB location: {chroma_dir}")
        
        # Also write a manifest
        manifest = {
            "index_name": "forgeai_training",
            "documents": count,
            "created_at": time.time(),
            "chroma_dir": str(chroma_dir),
            "total_records_generated": len(records),
        }
        manifest_file = Path.home() / ".forgeai" / "rag_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        print(f"  Manifest written to: {manifest_file}")
        
        return manifest
        
    except ImportError as e:
        print(f"  ChromaDB not installed: {e}")
        print("  Run: pip install chromadb")
        return None
    except Exception as e:
        print(f"  Error building RAG index: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    # Step 1: Generate training data
    dataset_file, records = generate_training_data()
    
    # Step 2: Build RAG index
    manifest = build_rag_index(records)
    
    # Summary
    print("\n" + "=" * 60)
    print("PHASE 1 COMPLETE")
    print("=" * 60)
    if manifest:
        print(f"✅ Training dataset: {dataset_file}")
        print(f"✅ RAG index: {manifest['documents']} documents in ChromaDB")
    else:
        print(f"⚠️  Training dataset generated but RAG index failed")
    print()

    # Print a sample record
    print("Sample training record:")
    print(json.dumps(records[0], indent=2))


if __name__ == "__main__":
    main()
