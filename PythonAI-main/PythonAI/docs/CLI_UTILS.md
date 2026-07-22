# 🖥️ CLI & Utilities — Project Management Tools

## Overview

A unified CLI (`python -m src.cli`) that orchestrates all project operations — training, evaluation, probing, asking, augmenting, merging, cleanup, and status reporting.

---

## 📝 Prompt to Continue (CLI & Utils Enhancements)

```
Copy-paste into Codebuff to continue:

Enhance the CLI and utilities. Here's what I need:

### 1. CLI Enhancements (src/cli.py)
- Add --version flag to show project version
- Add --verbose/-v mode with debug logging
- Add tab-completion support
- Add --json flag to output results as JSON (for scripting)
- Add --no-color flag for non-TTY environments
- Add tabular output format for list commands

### 2. New CLI Commands
- Add serve subcommand: start a local HTTP API server for the RAG engine
- Add export subcommand: export trained model to ONNX/GGUF format
- Add compare subcommand: compare two adapter outputs side by side
- Add schedule subcommand: run training on a cron-like schedule
- Add info subcommand: detailed info about a specific checkpoint

### 3. Better Status Command
- Add disk usage trend (compare with last check)
- Add dataset quality score (avg instruction length, code coverage %)
- Show recommended next action based on project state
- Add --watch flag to auto-refresh status every 5 seconds

### 4. Utilities (src/utils/)
- Add config file (project-wide settings in ~/.pythonai/config.json)
- Add logging system with file rotation
- Add telemetry opt-in (anonymous usage stats)
- Add dependency checker (verify all packages are up to date)
- Add cache manager (clear HF cache, Ollama cache)

### 5. Project Cleanup (src/utils/cleanup.py)
- Add --dry-run as default (require --apply to actually delete)
- Add interactive mode that asks before each deletion
- Add age-based filtering (only delete files older than N days)
- Add protection for recently modified files
- Add summary report of what was cleaned
```

---

## 🧩 CLI Commands

| Command | Description |
|---------|-------------|
| `status` | Show project, dataset, hardware, and model state |
| `train` | Run local training (modes: auto, smoke, qwen) |
| `eval` | Evaluate saved PEFT adapter |
| `probe` | Probe local Ollama model |
| `ask` | Ask the offline RAG assistant |
| `clean` | Dry-run or apply cleanup |
| `dataset` | Show dataset profile |
| `augment` | Generate extra SFT rows with local Ollama |
| `merge` | Merge extra SFT rows into deduped dataset |

## 🧩 Utility Modules

| Module | File | Purpose |
|--------|------|---------|
| Models | `src/utils/models.py` | Hardware, dataset, project audit, model discovery |
| Swarm | `src/utils/swarm.py` | Parallel task executor (TaskDecomposer + AgentSwarm) |
| Cleanup | `src/utils/cleanup.py` | Safe project cleanup (pycache, checkpoints, etc.) |

## 🚀 CLI Usage

```powershell
# Project status
python -m src.cli status

# Train model
python -m src.cli train --mode auto --max-steps 8

# Evaluate adapter
python -m src.cli eval

# Probe Ollama
python -m src.cli probe --num-ctx 512

# Ask RAG
python -m src.cli ask "Explain Python decorators"

# Augment dataset
python -m src.cli augment --dry-run

# Clean project
python -m src.cli clean
python -m src.cli clean --apply
```

---

## ✅ Status

[ ] Not started  
[ ] In progress  
[ ] Completed  
