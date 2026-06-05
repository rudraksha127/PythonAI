# PythonAI 🐍🤖

Local Python specialist AI project with three working pieces:

- **Data collection & generation** — Python docs scraped, SFT dataset built
- **PEFT/LoRA training** — Fine-tune models locally with hardware detection
- **Offline RAG** — Chroma vector DB + Ollama `qwen2.5-coder:14b`

Plus additional systems: **authentication**, **agent swarm**, **deployment**.

---

## 🏷️ Project Status

| Badge | Status |
|-------|--------|
| 🧪 Tests | **63 tests — all passing** ✅ |
| 🐍 Python | 3.12+ |
| 🏠 Local | Fully offline-capable (no cloud API required) |
| 📦 Model | `qwen2.5-coder:14b` (Ollama) |
| 🗄️ RAG DB | ~13K vectors (Chroma + BM25) |

---

## 📁 Project Structure

```
PythonAI/
├── src/                    # Main source package
│   ├── cli.py              # CLI entrypoint (status, train, eval, ask, login, ...)
│   ├── auth/               # 🔐 Authentication system
│   │   ├── auth.py         #   Password hashing, token generation, login/logout
│   │   ├── config.py       #   Config file manager (~/.pythonai/config.json)
│   │   └── decorators.py   #   @requires_auth decorator for protected commands
│   ├── data/               # 📊 Data pipeline
│   │   ├── collector.py    #   Scrape Python PEPs + library docs + release notes + error patterns
│   │   ├── generator.py    #   Parallel API dataset generator with checkpoint resume
│   │   ├── augmenter.py    #   Augment dataset via local Ollama (multi-model support)
│   │   └── merger.py       #   Dedupe merge with conflict resolution
│   ├── training/           # 🔧 Training pipeline
│   │   ├── trainer.py      #   PEFT/LoRA trainer (HuggingFace) with QLoRA, gradient clipping, throughput logging
│   │   ├── run.py          #   Full audit + training runner (wandb, early stopping, lr scheduler)
│   │   ├── pipeline.py     #   Collect -> Clean -> Generate -> Train (with skip flags, timing)
│   │   └── evaluator.py    #   Evaluate PEFT adapters (batch, interactive, BLEU scoring)
│   ├── rag/                # 🧠 RAG engine
│   │   ├── rag_engine.py   #   Offline RAG with BM25 hybrid search, MMR, query expansion, citations
│   │   └── prober.py       #   Probe Ollama + AirLLM
│   └── utils/              # Shared utilities
│       ├── models.py       #   Hardware, dataset, project audit utils
│       ├── swarm.py        #   🐝 Agent swarm with retry logic, MCP tools, monitoring
│       └── cleanup.py      #   Safe project cleanup
├── data/                   # Data files
│   ├── raw/                #   Raw scraped chunks
│   ├── processed/          #   Cleaned chunks + analysis reports
│   └── training/           #   SFT training datasets
├── checkpoints/            # Trained adapter checkpoints
├── python_brain_godmode/   # Chroma vector database
├── Dockerfile              # 🚀 Docker multi-stage build
├── docker-compose.yml      # Docker Compose (PythonAI + Ollama)
├── deploy.ps1              # Windows deployment script
├── deploy.sh               # Unix deployment script
├── tests/                  # Unit tests (26+ tests)
├── docs/                   # Documentation
└── *.py                    # Root-level wrappers (legacy compat)
```

---

## 🔐 Auth System

Protect sensitive commands (`train`, `eval`, `ask`) with password-based authentication.

### Features
- **Password hashing**: SHA-256 with PBKDF2 (100K iterations) + random salt
- **Token-based sessions**: Cryptographically secure tokens stored in `~/.pythonai/config.json`
- **Auto-registration**: First-time login creates account automatically
- **Secure config**: File permissions restricted to owner-only on supported OS
- **`@requires_auth` decorator**: Drop-in protection for any CLI command
- **`--no-auth` flag**: Skip auth for local/development use

### Usage

```powershell
# Login (first time creates account, subsequent times verifies password)
python -m src.cli login

# Check auth status
python -m src.cli login check

# Logout
python -m src.cli login logout

# Protected commands check auth automatically:
python -m src.cli train --mode auto --max-steps 8   # prompts login if needed
python -m src.cli ask "..."                          # prompts login if needed

# Skip auth check (development):
python -m src.cli train --no-auth --mode auto --max-steps 8
```

### Programmatic Usage

```python
from src.auth import hash_password, verify_password, login, logout, check_auth, AuthConfig

config = AuthConfig()
result = login("alice", "secure_password", config)
# => {"success": True, "username": "alice", "token": "..."}

status = check_auth(config)
# => {"authenticated": True, "username": "alice", "logged_in_at": "..."}

logout(config)
```

---

## 🧠 RAG Assistant

Offline Python RAG assistant powered by **ChromaDB** + **Ollama** with **hybrid search** (dense embeddings + BM25 keyword).

### Features
- **Dense search**: SentenceTransformer embeddings for semantic similarity
- **BM25 keyword search**: Lightweight BM25 implementation (no external dep) for exact term matching
- **Reciprocal Rank Fusion (RRF)**: Merges dense + BM25 results for best recall
- **MMR diversity re-ranking**: Maximum Marginal Relevance to avoid redundant results
- **Query expansion**: Auto-generates related queries via Ollama for broader retrieval
- **Citation numbers**: Sources labeled `[1]`, `[2]` linked to context docs
- **Code execution verification**: Safely runs generated Python code to validate correctness
- **Interactive mode**: Conversation history with rich commands

### Usage

```powershell
# Start interactive RAG session
python -m src.rag.rag_engine

# Single question (exit after answer)
python -m src.rag.rag_engine --question "How do async generators work?"

# With query expansion (broader search)
python -m src.rag.rag_engine --question "Explain decorators" --query-expansion

# With MMR diversity
python -m src.rag.rag_engine --question "Context managers" --mmr

# Show database statistics
python -m src.rag.rag_engine --stats

# Filter by Python version
python -m src.rag.rag_engine --question "What's new?" --version 3.13

# Rebuild database from scratch
python -m src.rag.rag_engine --rebuild --stats

# Via CLI entrypoint
python -m src.cli ask "Explain Python context managers"
python -m src.cli ask --stats
python -m src.cli ask --query-expansion --mmr "List comprehensions vs generator expressions"

# Disable code execution for safety
python -m src.cli ask --no-exec "How to delete all files?"
```

### Interactive Mode Commands

| Command | Description |
|---------|-------------|
| `rebuild` | Rebuild vector database from source data |
| `expand` | Download extra data (PEPs, libraries) |
| `clear` | Reset conversation history |
| `search N` | Show top N search results (default: 6) |
| `/save` | Save conversation to timestamped JSON file |
| `/explain` | Deep-dive explanation of last answer |
| `/model` | Show Ollama model info (parameters, modelfile) |
| `/stats` | Show database statistics |
| `/help` | Show command help |
| `quit` | Exit |

### RAG CLI Flags

| Flag | Description |
|------|-------------|
| `--rebuild` | Force rebuild of ChromaDB on startup |
| `--stats` | Show database statistics and exit |
| `--no-exec` | Skip code execution verification |
| `--exec-timeout N` | Code execution timeout in seconds |
| `--query-expansion` | Enable query expansion for broader search |
| `--mmr` | Enable MMR diversity re-ranking |
| `--mmr-lambda 0.7` | MMR diversity vs relevance trade-off |
| `--version 3.10` | Filter by Python version |
| `--category library` | Filter by category |

---

## 📊 Data Pipeline

### Collector (`src/data/collector.py`)
Scrapes Python documentation from multiple sources:
- **Python PEPs** (1-799) from `peps.python.org`
- **Library docs**: 20+ libraries (numpy, pandas, flask, fastapi, django, etc.)
- **Release notes**: Python 3.10 through 3.13 What's New
- **Error patterns**: Pre-built common error troubleshooting guides
- **Timestamp cache**: Avoids re-downloading unchanged sources (48h TTL)

```powershell
python -m src.data.collector
```

### Generator (`src/data/generator.py`)
Generates SFT training data via parallel API calls:
- **10+ prompt types**: basic, reasoning, expert, interview, project, cross_domain, judgment, multi_agent, error_fix, code_review, security, performance, testing
- **Checkpoint resume**: `--resume` flag resumes from last saved batch
- **Dependency-aware task graph**: Complex tasks wait for simpler prerequisites
- **Parallel workers**: Configurable concurrency via `AgentSwarm`

```powershell
python -m src.data.generator --resume
python -m src.data.generator --skip-swarm  # sequential mode
```

### Augmenter (`src/data/augmenter.py`)
Enhances datasets with Ollama-generated content:
- **Multi-model support**: Comma-separated `--model qwen2.5-coder:14b,deepseek-coder:6.7b` rotates models
- **Shuffle**: `--shuffle` flag shuffles selected chunks
- **Placeholder validation**: Detects unsubstituted placeholders like `[your_key]`
- **Quality stats**: `--stats` flag prints quality metrics (average lengths, placeholder counts)
- **Dry-run mode**: Preview without writing

```powershell
python -m src.data.augmenter --limit 10 --merge
python -m src.data.augmenter --model qwen2.5-coder:14b --shuffle --stats
python -m src.data.augmenter --dry-run
```

### Merger (`src/data/merger.py`)
Deduplicates and merges datasets:
- **Conflict resolution**: When duplicates conflict, keeps longer output by default
- **`--keep-old`**: Prefer original entries over new ones
- **`--stats-only`**: Print distribution without saving
- **Distribution display**: Shows categories, versions, and types

```powershell
python -m src.data.merger --base data/training/training_dataset.json --add data/training/training_dataset_augmented.json
python -m src.data.merger --stats-only --base data/training/training_dataset.json
```

---

## 🔧 Training Pipeline

### Runner (`src/training/run.py`)
Full audit + training orchestrator:
- **WandB logging**: `--wandb` flag enables Weights & Biases tracking
- **Early stopping**: `--early-stopping` with patience and threshold
- **Learning rate scheduler**: `--lr-scheduler-type` (cosine, linear, constant)
- **Training curves**: `--save-training-curves` saves loss curve JSON
- **Auto-resume**: `--auto-resume` finds and continues from latest checkpoint
- **QLoRA 4-bit**: `--load-in-4bit` enables 4-bit quantization (NF4)
- **Gradient clipping**: `--gradient-clip` for stable training
- **Dataset versioning**: `--dataset-version` labels training runs

```powershell
python -m src.training.run --mode auto --max-steps 8
python -m src.training.run --mode qwen --wandb --early-stopping --lr-scheduler-type cosine
python -m src.training.run --mode auto --load-in-4bit --gradient-clip 1.0 --auto-resume
```

### Trainer (`src/training/trainer.py`)
PEFT/LoRA trainer with HuggingFace:
- **Throughput callback**: Logs tokens-per-second during training
- **Training curves**: Captures loss curves for post-training visualization
- **QLoRA support**: 4-bit NF4 quantization via BitsAndBytesConfig
- **Gradient clipping**: Configurable max gradient norm
- **Target modules**: Auto-detects attention modules (q_proj, k_proj, v_proj, o_proj)
- **AirLLM compatibility**: Falls back gracefully when CUDA unavailable

```powershell
python -m src.training.trainer --base-model sshleifer/tiny-gpt2
```

### Evaluator (`src/training/evaluator.py`)
Evaluate trained adapters:
- **Batch evaluation**: `--batch` mode for automated testing
- **Interactive mode**: `--interactive` for manual prompt testing
- **BLEU scoring**: `compute_bleu()` for simple n-gram precision metric
- **Configurable prompts**: `--num-prompts` for sample count

```powershell
python -m src.training.evaluator --adapter-path checkpoints/local_auto_model
python -m src.training.evaluator --adapter-path checkpoints/local_auto_model --interactive
python -m src.training.evaluator --batch --num-prompts 20
```

### Pipeline (`src/training/pipeline.py`)
End-to-end orchestration:
- **Skip flags**: `--skip-collection`, `--skip-generation` for partial runs
- **Dataset versioning**: `--dataset-version` to tag the run
- **Timing report**: Prints elapsed time for each stage

```powershell
# Full pipeline
python -m src.training.pipeline --max-examples 256

# Resume from training (skip data collection + generation)
python -m src.training.pipeline --skip-collection --skip-generation --max-examples 256
```

---

## 🐝 Agent Swarm

Parallel task executor with dependency resolution, retry logic, and monitoring.

### Features
- **Dependency-aware execution**: Tasks wait for prerequisites before starting
- **Retry with backoff**: Exponential, linear, or fixed delay strategies
- **Timeout per task**: Individual task timeout with ThreadPoolExecutor isolation
- **MCP tool system**: Model Context Protocol registry for extensible tools
- **SwarmMonitor/SwarmStats**: Comprehensive execution metrics (durations, failures, by-type breakdown, worker usage)

### Usage

```python
from src.utils.swarm import AgentSwarm, GenerationTask, MCPRegistry, MCPTool

# Create swarm with retry
swarm = AgentSwarm(max_workers=4, retry_strategy="exponential", retry_delay=0.5)

# Define tasks with dependencies
tasks = [
    GenerationTask(task_id="task_1", task_type="basic", prompt="Explain lists"),
    GenerationTask(task_id="task_2", task_type="advanced", prompt="Explain decorators",
                   dependencies=("task_1",)),
]

# Execute with retry monitoring
results, stats = swarm.execute_monitored(tasks, worker_fn)
print(stats.report())
```

### MCP Tool Registry

```python
from src.utils.swarm import MCPRegistry, MCPTool

registry = MCPRegistry()
registry.register(MCPTool(
    name="code_formatter",
    description="Format Python code with black",
    handler=lambda code: __import__("black").format_str(code, mode=__import__("black").Mode()),
))
result = registry.call_tool("code_formatter", code="x=1")
```

---

## 🖥️ CLI Commands Reference

```powershell
# Project status
python -m src.cli status                                    # Standard output
python -m src.cli status --json                             # JSON output
python -m src.cli status --verbose                          # Extended details (large files, extensions)

# Authentication
python -m src.cli login                                     # Login (first time = auto-register)
python -m src.cli login check                               # Check auth status
python -m src.cli login logout                              # Logout

# Training
python -m src.cli train --mode auto --max-steps 8           # Train with auto-detection
python -m src.cli train --mode auto --no-auth               # Train without auth check

# Evaluation
python -m src.cli eval --adapter-path checkpoints/local_auto_model

# Probe Ollama
python -m src.cli probe --num-ctx 512

# RAG Assistant
python -m src.cli ask "Explain Python context managers"     # Ask a question
python -m src.cli ask --stats                               # Show RAG DB stats
python -m src.cli ask --query-expansion --mmr "List vs tuple"  # Advanced search
python -m src.cli ask --no-exec "How to delete files?"      # Safety mode
python -m src.cli ask --version 3.13 --category library     # Filtered search
python -m src.cli ask --rebuild --no-auth                   # Rebuild DB (no auth)

# Data pipeline
python -m src.cli augment --dry-run                         # Preview augmentation
python -m src.cli augment --limit 5 --pairs-per-chunk 1 --merge  # Run and merge
python -m src.cli merge --add data/training/training_dataset_augmented.json  # Merge datasets
python -m src.cli dataset                                   # Show dataset profile

# Cleanup
python -m src.cli clean                                     # Dry-run cleanup
python -m src.cli clean --apply                             # Apply cleanup
```

---

## 🚀 Deployment

### Docker Deployment

```powershell
# Build and run with Docker Compose
docker compose build
docker compose up -d

# Pull the RAG model
docker compose exec ollama ollama pull qwen2.5-coder:14b

# Ask a question
docker compose exec pythonai python -m src.cli ask "Explain Python decorators"

# Run interactively
docker compose exec -it pythonai python -m src.rag.rag_engine

# Stop
docker compose down
```

### Windows (PowerShell)

```powershell
# Setup environment
.\deploy.ps1 -Setup

# Docker deployment
.\deploy.ps1 -Docker
```

### Unix (Linux/macOS)

```bash
# Setup environment
bash deploy.sh setup

# Docker deployment
bash deploy.sh docker
```

### Manual Setup

```powershell
# Create virtual environment
python -m venv .venv

# Install dependencies
.\.venv\Scripts\pip install -r requirements.txt

# Ensure Ollama is running and pull model
ollama serve
ollama pull qwen2.5-coder:14b

# Run the assistant
.\.venv\Scripts\python -m src.rag.rag_engine
```

---

## 🧪 Tests

```powershell
# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_swarm.py -v
```

**Current test coverage: 63 tests, all passing** ✅

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_auth.py` | 24 | Auth system (hashing, tokens, config, login, decorators) |
| `tests/test_swarm.py` | 2 | Swarm task execution |
| `tests/test_rag.py` | 30 | RAG engine (SimpleBM25, hybrid_search, cosine_sim, MMR) |
| `tests/test_smoke_e2e.py` | 7 | End-to-end pipeline smoke test (auth, data, training, RAG, swarm, CLI) |

---

## 📋 Status

```powershell
python -m src.cli status
python -m src.cli status --json    # Machine-readable output
```

- **Dataset**: `data/training/training_dataset.json` — 1,024 SFT examples
- **RAG DB**: `python_brain_godmode/` — ~13K embedded chunks (BM25 + dense)
- **Adapters**: `checkpoints/local_auto_model/`, `checkpoints/full_pipeline_model/`
- **Local LLM**: Ollama `qwen2.5-coder:14b`
- **Auth**: Optional password-based authentication (SHA-256 + PBKDF2)
- **CUDA**: Not detected (CPU-only — Qwen used for inference/RAG)

For detailed training notes, see `LOCAL_TRAINING_RUNBOOK.md`.
