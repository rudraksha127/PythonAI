# 🚀 Project Setup & Deployment Guide

## Overview

PythonAI is a local Python specialist AI project. This guide covers setup from scratch, deployment options, and production considerations.

---

## 📝 Prompt to Continue (Deployment & DevOps)

```
Copy-paste into Codebuff to continue:

Set up deployment infrastructure. Here's what I need:

### 1. Environment Setup Automation
- Create setup.sh/setup.ps1 script that:
  - Creates virtual environment
  - Installs dependencies from requirements.txt
  - Installs Ollama if not present
  - Pulls qwen2.5-coder:14b model
  - Runs initial data collection
  - Builds the RAG database
- Add --quick flag that skips data collection (assumes cached data)

### 2. Docker Support
- Create Dockerfile with:
  - Python 3.11+ base image
  - All dependencies pre-installed
  - Ollama installation
  - Volume mounts for checkpoints and data
- Create docker-compose.yml with:
  - pythonai service (RAG + CLI)
  - ollama service
  - Shared network and volumes
- Add .dockerignore file

### 3. CI/CD Pipeline
- Create .github/workflows/test.yml for:
  - Python 3.11, 3.12, 3.13 matrix
  - Linting (ruff/flake8)
  - Type checking (mypy/pyright)
  - Unit tests (pytest)
  - Smoke training test (2 steps, 4 examples)
- Create .github/workflows/build.yml for Docker image build

### 4. Production Considerations
- Add health check endpoint for Docker deployments
- Add graceful shutdown handler (SIGTERM → save state → exit)
- Add log rotation and structured logging (JSON format)
- Add configuration via environment variables with .env file support
- Add --daemon mode for running RAG engine as background service

### 5. Documentation & Onboarding
- Create CONTRIBUTING.md with:
  - Development setup guide
  - Code style guide
  - PR process
- Create API_REFERENCE.md with:
  - All CLI commands documented
  - All Python modules documented
  - Example workflows
```

---

## 🔧 Local Setup

```powershell
# 1. Clone & enter project
git clone <repo-url>
cd PythonAI

# 2. Create virtual environment
python -m venv .venv

# 3. Activate
.\.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Ollama (if not installed)
# Download from: https://ollama.com/download

# 6. Pull Qwen model
ollama pull qwen2.5-coder:14b

# 7. Check project status
python -m src.cli status
```

## 📦 Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| torch | 2.11.0 | Deep learning framework |
| transformers | 5.8.0 | HF model loading/training |
| peft | 0.19.1 | PEFT/LoRA fine-tuning |
| datasets | 4.8.5 | Dataset handling |
| accelerate | 1.13.0 | Multi-device training |
| safetensors | 0.7.0 | Safe model weights |
| chromadb | 1.5.9 | Vector database |
| sentence-transformers | 5.4.1 | Text embeddings |
| ollama | 0.6.2 | Local LLM client |
| requests | 2.33.1 | HTTP requests |
| beautifulsoup4 | * | HTML parsing |
| tqdm | 4.67.3 | Progress bars |
| psutil | 7.2.2 | System monitoring |

## 💻 Legacy Wrappers

Root-level `.py` files still work for backward compatibility:

```powershell
.\.venv\Scripts\python.exe scripts/python_ai.py status
.\.venv\Scripts\python.exe scripts/python_ai.py train --mode smoke
```

---

## ✅ Status

[ ] Not started  
[ ] In progress  
[ ] Completed  
