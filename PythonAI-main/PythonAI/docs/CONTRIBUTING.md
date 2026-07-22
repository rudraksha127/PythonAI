# Contributing to PythonAI 🐍🤖

Thank you for your interest in contributing! This document covers the development workflow, code conventions, testing practices, and review process for the PythonAI project.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Development Setup](#development-setup)
3. [Code Style & Conventions](#code-style--conventions)
4. [Adding a New Feature](#adding-a-new-feature)
5. [Running Tests](#running-tests)
6. [Code Review Process](#code-review-process)
7. [Documentation Guidelines](#documentation-guidelines)
8. [Pull Request Checklist](#pull-request-checklist)

---

## Project Overview

PythonAI is a modular Python project with these key subsystems:

| Subsystem | Location | Purpose |
|-----------|----------|---------|
| **Auth** | `src/auth/` | Password-based auth with token sessions, `@requires_auth` decorator |
| **Data Pipeline** | `src/data/` | Scraping, generating, augmenting, and merging SFT datasets |
| **Training** | `src/training/` | PEFT/LoRA fine-tuning with HuggingFace, QLoRA, BLEU eval |
| **RAG Engine** | `src/rag/` | Offline RAG with ChromaDB, BM25 hybrid search, MMR, query expansion |
| **Agent Swarm** | `src/utils/swarm.py` | Parallel task executor with MCP tools, retry, monitoring |
| **CLI** | `src/cli.py` | Central entrypoint (argparse) dispatching to all subsystems |

Each subsystem has a clear public API that can be imported from its module or called via `python -m src.<subsystem>`.

---

## Development Setup

### Prerequisites

- **Python 3.12+**
- **Ollama** (for RAG inference and dataset augmentation)
- **Git**

### Environment

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### Verify Setup

```powershell
# Run all tests — should pass
python -m pytest tests/ -v

# Check CLI works
python -m src.cli status
```

---

## Code Style & Conventions

### Python

- **Type hints required**: Every function must have typed parameters and return annotations.
- **`from __future__ import annotations`**: Add this import to the top of every module for PEP 604 union syntax.
- **Naming**:
  - `snake_case` for functions, methods, variables
  - `PascalCase` for classes
  - `_leading_underscore` for internal/private functions (not exported in `__init__.py`)
  - `SCREAMING_SNAKE_CASE` for constants
- **Docstrings**: Use `"""Triple double-quote docstrings"""`. One-line for simple functions, multi-line with Args/Returns sections for complex ones.

```python
from __future__ import annotations

def compute_bleu(reference: str, candidate: str) -> float:
    \"\"\"Compute a simple BLEU score between reference and candidate text.\"\"\"
    # ... implementation
```

### File Organization

- One primary class/concern per file.
- Internal helpers can share a file if closely related.
- Tests go in `tests/test_<module>.py`.
- All public API symbols should be importable from the package `__init__.py`.

### Imports

Group imports in this order, separated by a blank line:

1. `from __future__ import annotations`
2. Standard library (`os`, `sys`, `json`, `pathlib`, `typing`, etc.)
3. Third-party (`pytest`, `ollama`, `torch`, etc.)
4. Local application (`src.auth`, `src.rag.rag_engine`, etc.)

```python
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import ollama
import pytest

from src.auth.auth import hash_password, login
```

### Return Patterns

- **API functions** return `dict[str, Any]` with a `"success": bool` key:
  ```python
  def login(username: str, password: str) -> dict[str, Any]:
      if not valid:
          return {"success": False, "error": "Invalid credentials."}
      return {"success": True, "username": username, "token": token}
  ```
- **Pure computation** functions return typed values directly (`float`, `str`, `list[dict[str, Any]]`).
- **Internal helpers** can use exceptions for control flow; public API should catch and convert to dict results.

---

## Adding a New Feature

Follow this step-by-step process when adding a new feature:

### Step 1: Understand the codebase

Before writing code, read the relevant existing files to understand conventions:

- Read the module you're extending (e.g., `src/training/trainer.py`)
- Check the module's `__init__.py` for public exports
- Look at existing tests for the same module (e.g., `tests/test_trainer.py`)
- Check `src/cli.py` if your feature needs a CLI subcommand

### Step 2: Write the implementation

- Place new modules in the appropriate `src/<subsystem>/` directory
- Export public symbols from `src/<subsystem>/__init__.py`
- Keep backward compatibility: don't change existing function signatures without updating all callers
- Add comprehensive type hints and docstrings

### Step 3: Register in CLI (if applicable)

If your feature needs CLI access:

1. Add a subcommand in `src/cli.py`'s `build_parser()` function
2. Add a handler function with `@requires_auth` if it modifies data
3. Add `--no-auth` flag for development bypass
4. Export `build_parser()` for testing (already done)

### Step 4: Write tests

See [Running Tests](#running-tests) below for detailed test expectations.

### Step 5: Update README

- Add a new section under the appropriate heading
- Include CLI usage examples
- Add programmatic API examples
- Update the test count table

### Step 6: Run full test suite

```powershell
python -m pytest tests/ -v
```

All existing tests must still pass.

---

## Running Tests

### Test Framework

We use **pytest** (not `unittest` — though legacy tests exist and are supported).

### Test File Naming

- `tests/test_<module>.py` for module-level tests
- `tests/test_smoke_e2e.py` for end-to-end integration tests

### Test Standards

Each test file should be:

1. **Self-contained**: Use fixtures, mocks, or in-memory data — no external service dependencies
2. **Pure functions**: Tests are plain functions (not classes, unless using `unittest.TestCase` for legacy)
3. **Descriptive names**: `test_<unit>_<scenario>` format
   ```python
   def test_hash_and_verify() -> None: ...
   def test_empty_query_returns_zero_scores() -> None: ...
   def test_relogin_wrong_password_fails() -> None: ...
   ```

### What to Test

| System | What to test | What to mock |
|--------|-------------|--------------|
| **Auth** | Hashing, tokens, config RW, login flow, decorator | Filesystem (use `tmp_path` fixture) |
| **Data** | Prompt building, chunk validation, dedup/merge, stats | Filesystem, API calls |
| **Training** | Callbacks, dataset construction, BLEU scoring | Model weights, GPU |
| **RAG** | BM25 scoring, cosine sim, MMR, citation formatting | ChromaDB, SentenceTransformer |
| **Swarm** | Task decomposition, parallel execution, MCP registry, monitoring | Worker functions |
| **CLI** | Argument parsing for all subcommands and flags | None (pure parsing) |

### Mocking Strategy

- Use **unittest.mock** (`from unittest.mock import patch`) for function-level mocking
- Create lightweight **fake classes** that implement the same interface as the real dependency
- Examples in the codebase:
  - `MockCollection` in `tests/test_rag.py` — mimics ChromaDB collection
  - `MockEmbedder` in `tests/test_rag.py` — mimics SentenceTransformer
  - `_FakeTrainingArgs`, `_FakeState` in `tests/test_smoke_e2e.py` — mimics HuggingFace objects

```python
class MockCollection:
    \"\"\"A mock chromadb Collection that returns predetermined results.\"\"\"

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def query(self, **kwargs: Any) -> dict[str, list[Any]]:
        # Return shaped data matching real chromadb response format
        ...
```

### Running Specific Tests

```powershell
# Single test file
python -m pytest tests/test_rag.py -v

# Single test function
python -m pytest tests/test_rag.py::TestSimpleBM25::test_corpus_empty -v

# Smoke test only
python -m pytest tests/test_smoke_e2e.py -v

# All tests
python -m pytest tests/ -v
```

### Smoke Test

The end-to-end smoke test (`tests/test_smoke_e2e.py`) exercises all 7 pipeline stages with mock data. Run this before any PR:

```powershell
python -m pytest tests/test_smoke_e2e.py -v
```

It covers: auth → data → training → RAG → swarm → CLI → integration flow.

---

## Code Review Process

### Review Checklist

Every PR goes through this checklist:

**Correctness**
- [ ] Does the code do what it claims?
- [ ] Are edge cases handled (empty input, None, type mismatches)?
- [ ] Are error states returned gracefully (not raw exceptions to the user)?

**Style**
- [ ] Type hints on all function signatures
- [ ] `from __future__ import annotations` present
- [ ] No unused imports or variables
- [ ] Functions are focused (one thing, well)
- [ ] Docstrings present for public API functions

**Testing**
- [ ] New code has corresponding tests
- [ ] Tests use mocks, not external services
- [ ] All existing tests still pass
- [ ] Smoke test passes

**Integration**
- [ ] `build_parser()` updated if CLI subcommand added/changed
- [ ] `__init__.py` exports updated if new public symbols added
- [ ] README updated if user-facing behavior changed
- [ ] Backward compatible (or breaking changes documented)

### Review Tools

We use automated code review via `code-reviewer-deepseek-flash` on significant changes. This checks:

- API signature consistency between source and tests
- Unused imports and dead code
- Correctness of mocking
- Alignment with project conventions

### Before Requesting Review

```powershell
# 1. Run all tests
python -m pytest tests/ -v

# 2. Verify all imports work
python -c "from src.cli import build_parser; from src.auth import login; from src.utils.swarm import AgentSwarm; from src.rag.rag_engine import SimpleBM25; print('OK')"

# 3. Run smoke test
python -m pytest tests/test_smoke_e2e.py -v

# 4. Check for unused variables/files
# (manually review your diff)
```

---

## Documentation Guidelines

### Docstrings

Public functions and classes require docstrings:

```python
def hybrid_search(
    question: str,
    collection: Any,
    embedder: SentenceTransformer,
    bm25: SimpleBM25 | None = None,
    ...
) -> list[dict[str, Any]]:
    \"\"\"Dense + BM25 hybrid search with optional MMR and metadata filtering.

    Args:
        question: The user's question string.
        collection: ChromaDB collection with embedded documents.
        embedder: SentenceTransformer model for query encoding.
        bm25: Optional BM25 scorer for keyword matching.
        ...
    Returns:
        List of result dicts with keys: title, version, category, text, score, rank, citation_num.
    \"\"\"
```

### README Updates

When adding a new feature, update the README:

1. Add a section under the appropriate subsystem heading
2. Include CLI usage examples with ` ```powershell ` blocks
3. Include programmatic API examples with ` ```python ` blocks
4. Update the test count table at the bottom
5. Update the project structure tree if new files were added

### Inline Comments

- Comment **why**, not what — the code should be self-documenting for the *what*
- Use `#` for single-line comments
- Use sections with `# ──── ────` separators for organizing long modules (see `rag_engine.py`)

---

## Pull Request Checklist

Before submitting a pull request, ensure:

- [ ] All tests pass (`python -m pytest tests/ -v`)
- [ ] Smoke test passes (`python -m pytest tests/test_smoke_e2e.py -v`)
- [ ] Type hints on all new/changed functions
- [ ] `from __future__ import annotations` present
- [ ] Docstrings on public API
- [ ] No unused imports or dead code
- [ ] CLI `build_parser()` updated if needed
- [ ] `__init__.py` exports updated if needed
- [ ] README updated with new feature documentation
- [ ] README test count updated
- [ ] Backward compatible (or breaking changes documented)
- [ ] Tests cover edge cases (empty, error, boundary conditions)

---

Thank you for contributing! 🚀
