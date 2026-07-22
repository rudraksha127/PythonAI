# PythonAI — Complete Project Knowledge Base 🐍🤖

> **Purpose**: This file is the single source of truth for the PythonAI project. When you return to this project after a break, read this file first to understand everything — what's built, what's planned, conventions, architecture, and next steps.

---

## 📋 Project Overview

**PythonAI** is a local-first Python specialist AI assistant with offline RAG (Retrieval-Augmented Generation), PEFT/LoRA fine-tuning, data pipeline, authentication, agent swarm, and CLI — all running locally via **Ollama** + **ChromaDB**.

| Aspect | Detail |
|--------|--------|
| **Language** | Python 3.12+ |
| **Model** | `qwen2.5-coder:14b` (default, switchable via `--model` flag) |
| **RAG DB** | ChromaDB (~13,843 chunks + HF datasets) + BM25 keyword index |
| **Training** | PEFT/LoRA via HuggingFace Transformers |
| **Status** | **99 tests — all passing** ✅ |
| **Auth** | Optional password-based (PBKDF2 + SHA-256) |
| **API Keys** | 10 providers — stored in ~/.pythonai/apikeys.json |
| **Deploy** | Docker Compose (PythonAI + Ollama + Web UI on port 8501) + GitHub Actions CI |

---

## 🏗️ System Architecture

```
                    ┌─────────────────────────────────┐
                    │        CLI (src/cli.py)         │
                    │  argparse entrypoint with auth  │
                    └──────┬──────┬──────┬──────┬────┘
                           │      │      │      │
              ┌────────────┘      │      │      └────────────┐
              ▼                   ▼      ▼                   ▼
     ┌──────────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────────┐
     │  Auth System │   │ RAG Engine │   │ Data Pipeline│   │  Training    │
     │ src/auth/    │   │src/rag/    │   │ src/data/    │   │ src/training/│
     │ Password +   │   │ ChromaDB + │   │ Collect →    │   │ PEFT/LoRA    │
     │ Token +      │   │ Ollama +   │   │ Generate →   │   │ HuggingFace  │
     │ Decorator    │   │ BM25 + MMR │   │ Augment →    │   │ QLoRA + Eval │
     └──────┬───────┘   └──────┬─────┘   └──────┬───────┘   └──────┬───────┘
            │                  │                │                  │
            └──────────────────┴────────────────┴──────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Agent Swarm       │
                    │ src/utils/swarm.py  │
                    │ Parallel execution  │
                    │ MCP tools + Retry   │
                    └─────────────────────┘
```

### Data Flow

```
Scrape → raw_chunks_godmode.json → ChromaDB (embeddings) + BM25 index
                                      │
                User Question ────────┤
                                      │
                                      ▼
                           Hybrid Search (Dense + BM25)
                           → RRF Merge → (optional MMR)
                                      │
                                      ▼
                           Ollama qwen2.5-coder:14b
                           → Answer generation
                           → Code execution verification
                           → Citation formatting
```

### Training Pipeline Flow

```
Collect data → Clean chunks → Generate Q&A pairs → Format dataset
→ Load base model → Apply LoRA → Train (HuggingFace Trainer)
→ Save adapter → Evaluate (BLEU, interactive)
```

---

## 📁 File Structure

```
C:\Users\lucky_vv7fub\OneDrive\Desktop\PythonAI\
│
├── src/                          # Main source package
│   ├── cli.py                    # CLI entrypoint (argparse, apikeys command)
│   ├── auth/                     # 🔐 Authentication
│   │   ├── __init__.py           #   Public API exports
│   │   ├── auth.py               #   Password hashing, token gen, login/logout
│   │   ├── config.py             #   Config file manager (~/.pythonai/config.json)
│   │   └── decorators.py         #   @requires_auth decorator
│   ├── data/                     # 📊 Data pipeline + API keys
│   │   ├── __init__.py
│   │   ├── apikeys.py           #   🔑 API key management (CRUD, .env export)
│   │   ├── hf_collector.py      #   🤗 HuggingFace dataset downloader (Python code SFT)
│   │   ├── collector.py          #   Scrape PEPs, library docs, release notes, Python docs
│   │   ├── generator.py          #   Parallel API dataset generator (10 APIs)
│   │   ├── augmenter.py          #   Local Ollama augmentation
│   │   └── merger.py             #   Dedup merge with conflict resolution
│   ├── training/                 # 🔧 Training pipeline
│   │   ├── __init__.py
│   │   ├── trainer.py            #   PEFT/LoRA trainer (HuggingFace)
│   │   ├── run.py                #   Full audit + training runner
│   │   ├── pipeline.py           #   Collect → Clean → Generate → Train
│   │   └── evaluator.py          #   Batch/interactive evaluation + BLEU
│   ├── rag/                      # 🧠 RAG engine
│   │   ├── __init__.py
│   │   ├── models.py             #   🔀 Ollama model registry (list, resolve, manage)
│   │   ├── rag_engine.py         #   Offline RAG with hybrid search, MMR, citations
│   │   └── prober.py             #   Ollama + AirLLM probe
│   └── utils/                    # Shared utilities
│       ├── __init__.py
│       ├── models.py             #   Hardware, dataset, project audit utils
│       ├── swarm.py              #   🐝 Agent swarm (parallel, retry, MCP)
│       └── cleanup.py            #   Safe project cleanup
│
├── data/                         # Data files
│   ├── raw/ (planned)            #   raw_chunks.json, raw_chunks_godmode.json
│   ├── processed/ (planned)      #   cleaned_chunks.json, analysis_report.json
│   ├── training/                 #   training_dataset.json (1,024 SFT examples)
│   └── conversations/ (planned)  #   Saved conversation histories
│
├── checkpoints/                  # Trained adapter checkpoints
│   ├── local_auto_model/         #   Latest auto-trained adapter
│   ├── full_pipeline_model/      #   Pipeline-trained adapter
│   ├── augmented_smoke_model/    #   Augmented smoke test adapter
│   └── *.json                    #   Training plans & eval outputs
│
├── python_brain_godmode/         # ChromaDB vector database
├── .github/                      # GitHub Actions CI
│   └── workflows/
│       └── ci.yml                #   CI pipeline: pytest + smoke test
├── tests/                        # Unit tests (90 tests)
│   ├── __init__.py
│   ├── test_auth.py              #   24 tests
│   ├── test_swarm.py             #   2 tests
│   ├── test_rag.py               #   42 tests (incl. expand_query, execute_code)
│   ├── test_e2e_cli.py           #   5 tests (CLI parsing)
│   ├── test_e2e_data.py          #   4 tests (data pipeline)
│   ├── test_e2e_training.py      #   4 tests (training pipeline)
│   ├── test_e2e_integration.py   #   1 test (cross-stage)
│   ├── test_smoke_e2e.py         #   7 tests (E2E stage runner)
│   └── run_smoke_rag.py          #   Two-phase smoke test (pytest + real Ollama)
│
├── docs/                         # Documentation
├── *.py                          # Root-level wrappers (legacy compat)
├── Dockerfile                    # Docker multi-stage build
├── docker-compose.yml            # Docker Compose (PythonAI + Ollama)
├── deploy.ps1                    # Windows deployment script
├── deploy.sh                     # Linux/macOS deployment script
│
├── PYTHONAI_KNOWLEDGE_BASE.md    # ← THIS FILE — project knowledge base
├── README.md                     # User-facing documentation
├── CONTRIBUTING.md               # Contributor guidelines
├── LOCAL_TRAINING_RUNBOOK.md     # Training runbook
├── GOD_MODE_SCRAPER_PROMPT.md    # Data scraping master prompt
├── SENIOR_AI_ENGINEER_TRAINING_PROMPT.md  # Training master prompt
└── requirements.txt              # Python dependencies
```

---

## 🧩 Subsystem Details

### 1. Auth System (`src/auth/`)

**Files**: `auth.py`, `config.py`, `decorators.py`

**Features**:
- **PBKDF2-SHA256** password hashing (100K iterations) with random 16-byte salt
- **Cryptographically secure tokens** via `secrets.token_urlsafe(32)`
- **Config file**: `~/.pythonai/config.json` (stores hashed password, token, username)
- **Auto-registration**: First login creates account automatically
- **`@requires_auth` decorator**: Drop-in protection for CLI commands
- **`--no-auth` flag**: Bypass for development

**Key Functions**:
- `hash_password(password: str) -> str` — returns `salt$hash`
- `verify_password(password: str, stored: str) -> bool`
- `generate_token() -> str` — 43-char base64 token
- `login(username, password, config) -> dict` — returns `{success, username, token}`
- `logout(config) -> dict`
- `check_auth(config) -> dict` — returns `{authenticated, username, logged_in_at}`
- `interactive_login(config) -> dict` — CLI prompt-based login

**Config File** (`~/.pythonai/config.json`):
```json
{
  "password": "salt$hash",
  "token": "base64-43-chars",
  "username": "user",
  "logged_in_at": "2025-01-01T00:00:00"
}
```

**Tests** (`tests/test_auth.py`): 24 tests covering hashing, tokens, config file, login flow, decorator.

---

### 2. RAG Engine (`src/rag/rag_engine.py`)

**The core AI assistant — offline, local-only RAG system.**

**Components**:
- **ChromaDB** vector database with `all-MiniLM-L6-v2` embeddings
- **`SimpleBM25`** — lightweight BM25Okapi implementation (no external dependency)
- **Hybrid Search** — Dense embeddings + BM25 keyword → RRF merge
- **MMR** (Maximum Marginal Relevance) — diversity re-ranking to avoid redundancy
- **Query Expansion** — Ollama generates alternative phrasings (ollama_responded check)
- **Banner**: ASCII-safe output with `---` separators (Windows `cp437` compatible)
- **Code Execution** — `subprocess.run` validates generated Python code (safety-checked)
- **Citation Formatting** — `[1]`, `[2]` linked to source documents
- **Interactive Mode** — conversation history, slash commands (`/save`, `/explain`, `/model`, `/stats`)

**Key Functions**:

| Function | Purpose |
|----------|---------|
| `load_or_build_db(force_rebuild)` | Loads ChromaDB or builds fresh |
| `load_db()` | Loads existing ChromaDB + rebuilds BM25 index |
| `build_db(chunks_file)` | Creates ChromaDB from scratch, embeds all chunks |
| `hybrid_search(question, ...)` | Dense + BM25 search with optional MMR + filters |
| `mmr_rerank(docs, query_emb, lambda_, top_k)` | Diversity re-ranking |
| `expand_query(question)` | Ollama generates related queries |
| `get_answer(question, ...)` | Full answer pipeline: search → Ollama → code verify → cite |
| `execute_code(code_str, timeout)` | Safety-checked Python code execution |
| `format_sources(docs)` | Formats source citations |
| `print_stats(collection)` | DB statistics (versions, categories, types) |
| `save_conversation(history)` | Saves to `data/conversations/` |
| `show_model_info()` | Ollama model details |

**CLI Flags**:
```
--model "qwen2.5-coder:14b"  Ollama model to use (default: qwen2.5-coder:14b)
--list-models                  List available Ollama models and exit
--question "..."      Ask one question and exit
--rebuild             Force rebuild database
--stats               Show database statistics
--no-exec             Skip code execution verification
--exec-timeout N      Code execution timeout
--query-expansion     Enable query expansion
--mmr                 Enable MMR diversity
--mmr-lambda 0.7      MMR trade-off (higher = more relevance)
--version 3.10        Filter by Python version
--category library    Filter by category
```

**Database Stats**: ~13,843 chunks across Python versions 3.10–3.13, 20+ library docs, 800 PEPs, error patterns.

**Tests** (`tests/test_rag.py`): 42 tests covering SimpleBM25 (12), HybridSearch (10), CosineSim (8), expand_query (3), execute_code (6), extract_code_blocks (2), format_sources (1), load_or_build_db (1), save_conversation (1).

**Known Issues**:
- ChromaDB returns numpy arrays for embeddings when MMR is requested → fixed with `_to_plain_list()` helper
- 14B model is slow on CPU-only machines (can timeout at 5 min)
- Windows terminal Unicode issue with emoji/box-drawing chars (solved via `PYTHONIOENCODING=utf-8`)

---

### 3. Data Pipeline (`src/data/`)

#### Collector (`collector.py`)
- **PEPs 1-799**: Scrapes from `peps.python.org`
- **20+ Library docs**: numpy, pandas, flask, fastapi, django, pytest, etc.
- **Release notes**: Python 3.10, 3.11, 3.12, 3.13
- **Error patterns**: 6 pre-built common error troubleshooting guides
- **Python Tutorial**: All pages from `docs.python.org/3/tutorial/`
- **Python Library Reference**: All module pages from `docs.python.org/3/library/`
- **Python HOWTOs**: All guides from `docs.python.org/3/howto/`
- **Python FAQs**: All FAQ pages from `docs.python.org/3/faq/`
- **Python Language Reference**: All pages from `docs.python.org/3/reference/`
- **Python Glossary**: The complete glossary from `docs.python.org/3/glossary.html`
- **Generic crawler**: `_crawl_index_page()` helper — fetches index page, discovers all sub-page links, downloads each page
- **Code extraction**: Extracts code blocks from `<pre>` tags for each page
- **Cache system**: 24-48h TTL timestamp-based cache (`extra_data/collector_cache.json`)
- **Output**: `data/raw/raw_chunks_godmode.json`

#### Generator (`generator.py`)
- **10 API providers**: Groq, Cerebras, SambaNova, Together, OpenRouter, HuggingFace, Mistral, Fireworks, Novita, DeepInfra
- **12 prompt types**: basic, reasoning, beginner, expert, interview, project, version, security, performance, testing, error_fix, code_review
- **Checkpoint resume**: `--resume` flag, saves checkpoints every 200 chunks
- **Quality scoring**: Auto-filters low-quality pairs (< 60 score)
- **Dedup**: MD5 hash-based deduplication across runs
- **Agent swarm**: Uses `TaskDecomposer` + `AgentSwarm` for dependency-aware generation
- **Output**: `data/training/python_ultra_dataset_FINAL.json`

#### HF Dataset Collector (`hf_collector.py`) — NEW

**Downloads high-quality Python code SFT datasets directly from HuggingFace.**

**Supported Datasets**:
| Key | Dataset | Description | Est. Size |
|-----|---------|-------------|:---------:|
| `glaive_code_assistant` | `glaiveai/glaive-code-assistant-v2` | Multi-language code instruction pairs | ~120K |
| `instructional_code_search` | `Nan-Do/instructional-code-search-net-python` | Python instruction tuning from CodeSearchNet | ~25K |
| `code_search_net_python` | `code_search_net` (Python) | Python functions with docstrings | ~450K |

**Converters**: Each row is converted to standard chunk format with `id`, `title`, `text`, `type: hf_dataset`, `category`, and `codes` fields.

**Features**:
- **Caching**: Per-dataset cache files in `extra_data/hf_datasets/` with 7-day TTL
- **Default row limit**: 25,000 rows per dataset to prevent memory overload (use `--max-rows -1` for all)
- **Statistics**: `--stats` flag prints category distribution, code ratio, avg text length
- **Per-dataset control**: `--datasets glaive_code_assistant instructional_code_search` to pick specific datasets
- **Output**: `data/raw/raw_chunks_hf.json` (combined) + per-dataset cache files

**CLI Commands**:
```powershell
python -m src.cli hf-collect                          # Download all datasets (25K rows each)
python -m src.cli hf-collect --list                   # List available datasets
python -m src.cli hf-collect --stats                  # Show collection statistics
python -m src.cli hf-collect --max-rows 50000         # Increase per-dataset limit
python -m src.cli hf-collect --datasets glaive_code_assistant  # Single dataset
python -m src.cli hf-collect --max-rows -1            # Download all rows
```

#### Augmenter (`augmenter.py`)
- **Local Ollama generation**: Uses local model to generate additional SFT pairs
- **Multi-model support**: Comma-separated `--model` rotates models
- **Placeholder validation**: Rejects rows with `[your_key]`, `[insert]`, etc.
- **Quality stats**: `--stats` flag prints avg lengths, code ratio, top categories
- **Merge mode**: `--merge` deduplicates into base dataset
- **Dry-run**: `--dry-run` shows first prompt without calling Ollama

#### Merger (`merger.py`)
- **SHA-256 based dedup**: `instruction\n---\noutput` hash
- **Conflict resolution**: `--keep-old` flag (default: keep longer output)
- **Stats-only mode**: `--stats-only` prints distribution without saving
- **Distribution display**: Categories, versions, types with percentages

---

### 4. Training Pipeline (`src/training/`)

#### Trainer (`trainer.py`)
- **PEFT/LoRA**: HuggingFace `peft.LoraConfig` + `get_peft_model`
- **QLoRA 4-bit**: BitsAndBytes NF4 quantization (requires CUDA)
- **Target modules**: Auto-detects based on model type (gpt2 → `c_attn`, qwen/llama → `q_proj,k_proj,v_proj,o_proj`)
- **Throughput callback**: Logs tokens/sec during training
- **Training curves**: `--save-training-curves` saves loss curve as PNG
- **Gradient clipping**: `--gradient-clip` configurable max norm
- **AirLLM compatibility**: Falls back gracefully when CUDA unavailable

#### Runner (`run.py`)
- **Full audit**: Project files, dataset profile, hardware detection
- **Model selection**: Auto mode picks CPU-safe or Qwen based on CUDA
- **WandB logging**: `--wandb` flag
- **Early stopping**: `--early-stopping-patience N`
- **LR scheduler**: cosine, linear, constant
- **Auto-resume**: `--auto-resume` finds latest checkpoint
- **Output**: `checkpoints/local_training_plan.json`

#### Pipeline (`pipeline.py`)
- End-to-end: Collect → Clean → Generate → Train
- Skip flags: `--skip-collection`, `--skip-generation`
- Timing report per stage

#### Evaluator (`evaluator.py`)
- Batch evaluation: `--batch` mode for faster inference
- Interactive mode: `--interactive` for manual testing
- BLEU scoring: Simple 1-gram precision metric
- 3 default test prompts

**Important Model Boundary**: `qwen2.5-coder:14b` (Ollama) is for inference/RAG only. For PEFT training, use HF-format models like `sshleifer/tiny-gpt2` (CPU) or `Qwen/Qwen2.5-Coder-0.5B-Instruct` (CUDA).

---

### 5. Agent Swarm (`src/utils/swarm.py`)

**Parallel task executor with dependency resolution, retry logic, and monitoring.**

**Classes**:
- **`GenerationTask`**: Task with id, type, prompt, dependencies, retries, timeout
- **`TaskResult`**: Result with success, data, error, attempts, duration
- **`TaskDecomposer`**: Splits chunks into dependency-aware task graphs
- **`MCPTool` / `MCPRegistry`**: Model Context Protocol tool system
- **`SwarmMonitor` / `SwarmStats`**: Execution metrics (durations, failures, by-type, worker usage)
- **`AgentSwarm`**: Core executor with:
  - ThreadPoolExecutor for parallel execution
  - Dependency graph resolution (tasks wait for prerequisites)
  - Retry strategies: `FIXED`, `LINEAR`, `EXPONENTIAL`
  - Per-task timeout with isolated thread pool
  - Monitored execution with stats report

**Retry Strategies**:
- FIXED: `retry_delay` seconds between attempts
- LINEAR: `retry_delay * attempt` seconds
- EXPONENTIAL: `retry_delay * 2^(attempt-1)` seconds

**Tests** (`tests/test_swarm.py`): 2 tests covering dependency resolution and parallel execution.

---

### 6. API Key Management (`src/data/apikeys.py`)

**Central API key management for dataset generation.** Stores keys in `~/.pythonai/apikeys.json` with restricted file permissions (owner-only read/write).

**Supported Providers** (10): Groq, Cerebras, SambaNova, Together AI, OpenRouter, HuggingFace, Mistral AI, Fireworks AI, Novita AI, DeepInfra

**Key Resolution Priority**:
1. Stored file (`~/.pythonai/apikeys.json`)
2. Environment variable (e.g. `GROQ_API_KEY`)

**Key Functions**:

| Function | Purpose |
|----------|---------|
| `get_keys()` | Returns dict of all stored keys |
| `get_key(provider)` | Single provider's stored key |
| `set_key(provider, key)` | Store/update a key |
| `delete_key(provider)` | Remove a stored key |
| `list_keys(masked=True)` | Show all providers with masked keys |
| `active_providers()` | Providers with valid stored keys |
| `export_dotenv(path)` | Export keys to `.env` file |
| `resolve_key(provider)` | Stored > env var resolution |
| `resolve_all()` | All providers resolved (stored > env var) |

**CLI Commands**:
```powershell
python -m src.cli apikeys list                          # List masked keys
python -m src.cli apikeys list --show-keys              # Show full keys
python -m src.cli apikeys set groq gsk_xxxxx           # Store a key
python -m src.cli apikeys delete groq                   # Remove a key
python -m src.cli apikeys export                        # Export to .env
python -m src.cli apikeys export --path .env.prod       # Custom path
```

**Generator Integration**: `generator.py` now uses `resolve_all()` instead of only `os.getenv()`, so keys set via the CLI or Web UI are automatically picked up. Output shows `[stored]` vs `[env]` source for each active API.

---

### 7. Web UI (`src/webui/app.py`)

**Streamlit-based web interface with two pages: RAG Chat + Dataset Generator.**

**Features**:

**RAG Chat Page**:
- Chat interface with `st.chat_message` + `st.chat_input`
- Sidebar config: Query expansion, MMR + lambda slider, code execution settings, version/category filters
- Expandable source citations with `[1]`, `[2]` labels
- In-app DB statistics, conversation save, one-click DB rebuild
- Cached DB via `@st.cache_resource`

**Dataset Generation Page**:
- API Key Management form: Set (masked input), Delete, Export to `.env`
- Real-time key status table showing all 10 providers with masked keys and active status
- Dataset generation controls: max chunks, output filename, data types selection
- Generation launched via subprocess with live log display
- Results summary with type breakdown

**Launch Commands**:
```powershell
# Via CLI (recommended)
python -m src.cli webui
python -m src.cli webui --port 8501

# Direct Streamlit
streamlit run src/webui/app.py
```

**Architecture**:
- `src/webui/` package with `__init__.py` and `app.py`
- Sidebar navigation via `st.radio` switching between pages
- RAG mode: Uses `load_or_build_db()` + `get_answer()` with cached DB
- Dataset mode: API key management + `subprocess`-based generator runner

---

### 8. CLI (`src/cli.py`)

**Central entrypoint via `python -m src.cli`**.

**Architecture**: Uses `argparse` with `add_subparsers`. Each command has a dedicated handler function. The `build_parser()` function is exported for testing.

**Commands**:

| Command | Auth Required | Description |
|---------|:---:|-------------|
| `status` | No | Project, dataset, hardware, model audit |
| `status --json` | No | Machine-readable JSON |
| `status --verbose` | No | Extended details |
| `login` | No | Login (auto-register), check, logout |
| `train` | Yes | Run local training (`--no-auth` to bypass) |
| `eval` | Yes | Evaluate adapter |
| `probe` | No | Ollama probe |
| `ask` | Yes | RAG assistant (`--model`, `--list-models`, `--no-auth`) |
| `clean` | No | Dry-run or apply cleanup |
| `dataset` | No | Dataset profile |
| `augment` | No | Ollama dataset augmentation |
| `merge` | No | Merge datasets |
| `webui` | No | Launch Streamlit Web UI |
| `apikeys list` | No | List API keys (masked or full) |
| `apikeys set` | No | Store an API key for a provider |
| `apikeys delete` | No | Delete a stored API key |
| `apikeys export` | No | Export stored keys to `.env` file |
| `hf-collect` | No | Download Python code datasets from HuggingFace |
| `hf-collect --list` | No | List available HuggingFace datasets |
| `hf-collect --stats` | No | Show HF dataset collection statistics |
| `hf-collect --datasets ...` | No | Download specific datasets only |
| `hf-collect --max-rows N` | No | Limit rows per dataset (default: 25K) |

**Auth decorator**: `@requires_auth` checks `--no-auth` flag first, then validates config.

---

### 8. Utilities (`src/utils/`)

#### `models.py` — Shared utilities
- `ROOT`: Project root path resolution
- `project_python()`: Detects `.venv/Scripts/python.exe` or falls back to `sys.executable`
- `audit_project()`: File count, sizes, extensions, largest files
- `cleanup_dry_run()`: Finds deletable caches/artifacts
- `dataset_profile()`: Dataset row stats, categories, versions, lengths
- `hardware_profile()`: Python version, RAM, CUDA/GPU info via `torch` + `psutil`
- `list_ollama_models()`: Parses `ollama list` output
- `list_hf_cached_models()`: Scans HuggingFace cache dir
- `discover_qwen_hf_candidates()`: Finds Qwen models from env vars, HF cache, local files
- `choose_training_base()`: Auto-selects base model based on mode + hardware

#### `cleanup.py` — Safe cleanup
- Standard targets: `__pycache__`, `.sixth`, checkpoint files, etc.
- `--apply` flag: Dry-run by default
- Path safety: Validates targets are inside project root
- Size reporting: Shows recoverable space per target

---

## 🧪 Tests

**Total: 99 tests — all passing** ✅

| Test File | Tests | Coverage |
|-----------|:-----:|----------|
| `tests/test_auth.py` | 24 | Auth system (hashing, tokens, config, login, decorator) |
| `tests/test_swarm.py` | 2 | Swarm task decomposition & execution |
| `tests/test_rag.py` | 51 | SimpleBM25, HybridSearch, CosineSim, MMR, expand_query, execute_code, format_sources, load_or_build_db, mmr_rerank
| `tests/test_e2e_data.py` | 4 | Data pipeline: prompts, chunk validation, dedup/merge, quality stats |
| `tests/test_e2e_training.py` | 4 | Training: Example objects, callbacks, BLEU |
| `tests/test_e2e_cli.py` | 5 | CLI argument parsing for all subcommands |
| `tests/test_e2e_integration.py` | 1 | Cross-stage integration flow |
| `tests/test_smoke_e2e.py` | 7 | E2E runner (imports from individual files, runs with summary) |
| `tests/run_smoke_rag.py` | N/A | Two-phase smoke test runner (pytest + real Ollama RAG query) |

**Test Conventions**:
- Pure pytest functions (not unittest classes, except test_auth.py and test_swarm.py which mix)
- Descriptive names: `test_<unit>_<scenario>`
- `tmp_path` fixture for filesystem tests
- `MockCollection`, `MockEmbedder` classes for RAG mocking
- `_FakeTrainingArgs`, `_FakeState` for training mocking
- `_mock_ollama_generate` context manager for mocking Ollama
- `@contextmanager` for safe mock setup/teardown

**Run Commands**:
```powershell
# All tests
python -m pytest tests/ -v

# Specific file
python -m pytest tests/test_rag.py -v

# Specific test
python -m pytest tests/test_rag.py::test_expand_query_basic -v

# Smoke test (real Ollama)
python tests/run_smoke_rag.py --timeout 600

# Smoke test (pytest only)
python tests/run_smoke_rag.py --skip-rag

# E2E stage runner
python tests/test_smoke_e2e.py
```

---

## 🔧 Key Conventions & Patterns

### Code Style
- `from __future__ import annotations` at top of every module
- Type hints on ALL function signatures
- `snake_case` functions/variables, `PascalCase` classes
- `dict[str, Any]` return type with `"success": bool` for API functions
- Docstrings: `"""Triple double-quote"""` — one-line for simple, Args/Returns sections for complex

### Imports (order, blank-line separated)
```
from __future__ import annotations

# Standard library
import json, os, sys, time
from pathlib import Path
from typing import Any

# Third-party
import ollama, pytest, torch

# Local
from src.auth import login
from src.rag.rag_engine import SimpleBM25
```

### File Organization
- One primary class/concern per file in `src/<subsystem>/`
- Public API exported from `src/<subsystem>/__init__.py`
- Tests in `tests/test_<module>.py`
- Root-level `*.py` files are thin wrappers (legacy compat)

### Return Patterns
```python
# API functions return dict with success key
def login(username: str, password: str) -> dict[str, Any]:
    if not valid:
        return {"success": False, "error": "Invalid credentials."}
    return {"success": True, "username": username, "token": token}

# Pure functions return typed values
def compute_bleu(reference: str, candidate: str) -> float: ...
```

### Path Resolution
```python
ROOT = Path(__file__).resolve().parent.parent.parent  # src/utils/ -> project root
```

---

## ✅ What's Complete

- [x] **Auth system**: Password hashing, tokens, config, decorator, login/logout/check — 24 tests
- [x] **RAG engine**: ChromaDB, BM25, hybrid search, MMR, query expansion, code execution, citations — 30 tests
- [x] **Data pipeline**: Collector (PEPs, libraries, releases), Generator (10 APIs, 12 types), Augmenter, Merger
- [x] **Training pipeline**: PEFT/LoRA, QLoRA, callbacks, evaluation (batch/interactive/BLEU)
- [x] **Agent swarm**: Parallel execution, dependency resolution, retry, MCP, monitoring — 2 tests
- [x] **CLI**: All commands with auth protection, argparse, help text
- [x] **Smoke tests**: E2E pipeline (7 stages) + standalone RAG smoker (pytest + real Ollama)
- [x] **README**: Project docs, badges, architecture diagram (Mermaid), CLI reference
- [x] **CONTRIBUTING.md**: Dev setup, code style, test conventions, PR checklist
- [x] **Documentation**: Training runbook, scraping prompt, training prompt
- [x] **Docker**: Dockerfile + docker-compose.yml + deploy scripts (ps1, sh)
- [x] **Project cleanup**: Safe cleanup script with dry-run mode
- [x] **Project status**: `python -m src.cli status` with JSON/verbose modes

---

## 📋 What's Planned / TODO

- [x] **MMR tests**: 9 dedicated unit tests for `mmr_rerank()` — empty docs, lambda extremes, diversity selection, top_k limits, no-embedding fallback
- [x] **Windows Unicode fix**: Replaced all emojis with ASCII-safe `[TAG]` alternatives in `rag_engine.py` (24) and `cli.py` (5)
- [x] **Parallel test execution**: Added `pytest-xdist` to `requirements.txt` + `-n auto` flag in CI workflow
- [x] **Full test suite**: All **99 tests passing** ✅ (was 90)

### High Priority
- [x] ~~**Run full smoke test suite with real Ollama**: `python tests/run_smoke_rag.py --timeout 600`~~ ✅ Done — Both phases passed (90 pytest + Ollama RAG responded correctly)

### Medium Priority
- [ ] **Better training dataset**: Scale from 1,024 to 10,000+ SFT examples
- [ ] **Real HF-model training**: Download and train with Qwen2.5-Coder-0.5B-Instruct
- [x] ~~**MMR tests**: Dedicated tests for `mmr_rerank()` with mock data~~ ✅ Done (+9 tests)
- [x] ~~**Windows Unicode fix**: Emoji replaced with ASCII-safe `[TAG]` in RAG + CLI~~ ✅ Done
- [x] ~~**Parallel test execution**: pytest-xdist added to CI~~ ✅ Done
- [x] ~~**Web UI**: Simple Gradio/Streamlit frontend for the RAG assistant~~ ✅ Done (Streamlit) — see `src/webui/app.py` + `python -m src.cli webui`
- [x] ~~**HuggingFace dataset collector**: `src/data/hf_collector.py` downloads glaive, code_search_net, instructional datasets~~ ✅ Done
- [x] ~~**Comprehensive Python doc scraping**: Tutorial, Library Ref, HOWTOs, FAQs, Language Reference, Glossary~~ ✅ Done
- [x] ~~**CLI `hf-collect` command**: List, download, stats for HF datasets~~ ✅ Done

### Low Priority / Nice-to-Have
- [x] **Multi-model RAG**: `--model` flag for CLI, model dropdown in Web UI, fallback logic — see `src/rag/models.py`
- [x] **Docker Web UI**: Web UI served via Docker Compose as a separate service on port 8501
- [ ] **Conversation search**: Search through saved conversations in `data/conversations/`
- [ ] **Export RAG answers**: Save answers as markdown files with proper citation formatting
- [ ] **Training visualization**: Better loss curve plots, metric dashboards
- [ ] **Model comparison**: Side-by-side evaluation of different adapters

---

## 🐛 Known Bugs & Issues

### Fixed
- ~~**MMR numpy array crash**: ChromaDB returns numpy arrays → `_cosine_sim`'s `if not a` check fails~~ ✅ Fixed with `_to_plain_list()` helper
- ~~**Windows Unicode crash**: Subprocess output with emoji/box-drawing chars crashes on cp437/cp850 terminals~~ ✅ Fixed with `PYTHONIOENCODING=utf-8` + `encoding="utf-8"` in subprocess calls
- ~~**RAG engine Unicode output**: RAG engine prints emoji/box-drawing chars directly, causing `UnicodeEncodeError` on Windows~~ ✅ Fixed in smoke test runner with `PYTHONIOENCODING=utf-8` + `encoding="utf-8"` subprocess env

### Still Open
- **14B model slow**: `qwen2.5-coder:14b` takes 30-300s per query on CPU-only machines
- **Training dataset quality**: Some auto-generated examples have garbage `****************************` titles (from scraped reStructuredText docs)
- **No CUDA**: Current machine is CPU-only — QLoRA training and larger models are very slow
- **BM25 index rebuild**: Loads all documents from ChromaDB on every startup (can be slow with large DB)

---

## 🚀 Quick Commands Reference

```powershell
# ===== STATUS & INFO =====
python -m src.cli status                            # Project status
python -m src.cli status --json                     # JSON output
python -m src.cli status --verbose                  # Extended details
python -m src.rag.rag_engine --stats                # RAG DB statistics

# ===== AUTH =====
python -m src.cli login                             # Login / register
python -m src.cli login check                       # Check auth status
python -m src.cli login logout                      # Logout

# ===== RAG ASSISTANT =====
python -m src.cli ask "What's a decorator?"         # Ask with auth
python -m src.cli ask --no-auth "Explain lists"     # Ask without auth
python -m src.cli ask --query-expansion --mmr "async vs sync"
python -m src.cli ask --no-exec "How to delete files?"
python -m src.cli ask --stats                       # DB stats
python -m src.cli ask --rebuild --no-auth           # Rebuild DB

# ===== DATA PIPELINE =====
python -m src.data.collector                        # Scrape new data (PEPs, docs, tutorial, etc.)
python -m src.cli hf-collect                        # Download Python code datasets from HuggingFace
python -m src.cli hf-collect --list                 # List available HuggingFace datasets
python -m src.cli hf-collect --stats                # Show HF collection statistics
python -m src.data.augmenter --limit 10 --merge     # Augment + merge
python -m src.data.merger --stats-only --base data/training/training_dataset.json
python -m src.cli dataset                           # Dataset profile

# ===== TRAINING =====
python -m src.training.run --mode auto --max-steps 8
python -m src.training.run --mode qwen --wandb --lr-scheduler-type cosine
python -m src.cli train --mode auto --max-steps 8 --no-auth

# ===== EVALUATION =====
python -m src.training.evaluator --adapter-path checkpoints/local_auto_model
python -m src.training.evaluator --adapter-path checkpoints/local_auto_model --interactive
python -m src.cli eval --adapter-path checkpoints/local_auto_model

# ===== WEB UI =====
python -m src.cli webui                             # Launch Streamlit Web UI (port 8501)
streamlit run src/webui/app.py                      # Direct Streamlit launch

# ===== API KEYS =====
python -m src.cli apikeys list                      # List masked API keys
python -m src.cli apikeys list --show-keys          # Show full keys
python -m src.cli apikeys set groq gsk_xxxxx       # Store an API key
python -m src.cli apikeys delete groq               # Remove a stored key
python -m src.cli apikeys export                    # Export to .env file

# ===== SMOKE TESTS =====
python -m pytest tests/ -v                          # All 99 tests
python tests/run_smoke_rag.py --timeout 600         # Full smoke (pytest + Ollama)
python tests/run_smoke_rag.py --skip-rag            # pytest only

# ===== CLEANUP =====
python -m src.utils.cleanup                         # Dry run
python -m src.utils.cleanup --apply                 # Delete targets
python -m src.cli clean                             # Via CLI
python -m src.cli clean --apply

# ===== DOCKER =====
docker compose build && docker compose up -d
docker compose exec pythonai python -m src.cli ask "How do I use pathlib?"
docker compose exec ollama ollama pull qwen2.5-coder:14b   # Pull model first
docker compose exec pythonai python -m src.cli apikeys set grog YOUR_KEY  # Set API keys (persisted via volume)
# Open http://localhost:8501 in your browser for the Web UI
docker compose down

# ===== OLLAMA =====
python -m src.rag.prober                            # Probe Ollama
python -m src.cli probe --num-ctx 512
```

---

## 📦 Dependencies

**Key packages** (from `requirements.txt`):
- `torch==2.11.0` — Deep learning framework
- `transformers==5.8.0` — HuggingFace transformers
- `peft==0.19.1` — PEFT/LoRA
- `accelerate==1.13.0` — Training acceleration
- `chromadb==1.5.9` — Vector database
- `sentence-transformers==5.4.1` — Embeddings
- `ollama==0.6.2` — Local LLM client
- `datasets==4.8.5` — HuggingFace datasets
- `pandas==3.0.3` — Data manipulation
- `requests==2.33.1` — HTTP requests
- `psutil==7.2.2` — System monitoring
- `tqdm==4.67.3` — Progress bars
- `safetensors==0.7.0` — Safe tensor storage
- `airllm==2.11.0` — AirLLM inference

---

> **Last Updated**: 2025-05-25
> **Next actions for AI**: When given a new task, check this file first for context. After making changes, update this file to reflect the new state.
