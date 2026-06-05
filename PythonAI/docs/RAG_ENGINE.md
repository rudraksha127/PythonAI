# 🔍 RAG Engine — Offline Python Specialist Assistant

## Overview

A fully offline Retrieval-Augmented Generation (RAG) system that combines Chroma vector database (13K+ embedded Python documentation chunks) with Ollama's `qwen2.5-coder:14b` model for intelligent Python Q&A.

```
┌──────────┐    ┌───────────┐    ┌──────────────┐    ┌─────────┐
│ Question  │───▶│ Hybrid    │───▶│ Context      │───▶│ Ollama  │
│           │    │ Search    │    │ + Prompt     │    │ Qwen    │
└──────────┘    └───────────┘    └──────────────┘    └──┬──────┘
                                                        │
                                                        ▼
                                               ┌──────────────┐
                                               │ Code Verifier│
                                               │ (auto-exec)  │
                                               └──────────────┘
```

---

## 📝 Prompt to Continue (RAG Engine Enhancements)

```
Copy-paste into Codebuff to continue:

Enhance the RAG engine. Here's what I need:

### 1. Better Search (src/rag/rag_engine.py)
- Add BM25 keyword search alongside dense embedding for true hybrid search
- Add metadata filtering: `--version 3.10` only searches Python 3.10 docs
- Add category filter: `--category debugging` limits search to error patterns
- Show search result snippets with highlighted matched terms

### 2. RAG Quality Improvements
- Add MMR (Maximum Marginal Relevance) to diversify search results
- Add re-ranking step using cross-encoder model for better result ordering
- Add query expansion (generate 2-3 related queries, merge results)
- Add citation numbers in output (e.g., [1], [2]) linked to sources

### 3. Interactive Mode Features
- Add /save command to export conversation to markdown file
- Add /model command to switch between different Ollama models
- Add /explain command to show which docs were retrieved and why
- Add context window limit warning when conversation is too long
- Add search result count display (e.g., "Found 5 relevant docs")

### 4. Code Execution Safety
- Add a configurable sandbox mode using a temporary directory
- Add execution timeout option via --exec-timeout CLI arg
- Add option to disable code execution entirely (--no-exec)
- Add output size limit to prevent huge outputs

### 5. Database Management
- Add --rebuild CLI flag for easy database rebuild
- Add --stats CLI flag to show database statistics (chunks by version/category)
- Add incremental update support (append new chunks without full rebuild)
- Add export/import database as JSON for portability
```

---

## 🧩 RAG Components

| Module | File | Purpose |
|--------|------|---------|
| Engine | `src/rag/rag_engine.py` | Main RAG: hybrid search, answer generation, code verification |
| Prober | `src/rag/prober.py` | Probe Ollama + AirLLM models |

## 🚀 Commands

```powershell
# Start interactive RAG session
python -m src.rag.rag_engine

# Ask one question and exit
python -m src.rag.rag_engine --question "How do async generators work?"

# Probe Ollama model
python -m src.cli probe --num-ctx 512

# Ask via CLI
python -m src.cli ask "Explain Python context managers"
```

## 📍 Database

| Resource | Path | Description |
|----------|------|-------------|
| Vector DB | `python_brain_godmode/` | Chroma persistent client (~13K chunks) |
| Embedder | `all-MiniLM-L6-v2` | SentenceTransformer model |
| LLM | `qwen2.5-coder:14b` (Ollama) | Local LLM for answer generation |

## 🛠️ Interactive Commands

| Command | Action |
|---------|--------|
| `rebuild` | Rebuild vector database from scratch |
| `expand` | Download extra data (PEPs, libraries) |
| `clear` | Reset conversation history |
| `quit` | Exit |

---

## ✅ Status

[ ] Not started  
[ ] In progress  
[ ] Completed  
