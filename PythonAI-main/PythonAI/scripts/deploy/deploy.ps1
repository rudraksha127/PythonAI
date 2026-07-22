# PythonAI — Windows Deployment Script (PowerShell)
# Run:  powershell -ExecutionPolicy Bypass -File deploy.ps1

param(
    [switch]$Setup,
    [switch]$Docker,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV = Join-Path $ROOT ".venv"

function Show-Help {
    Write-Host @"
PythonAI Deployment Script — PowerShell

Usage:
  .\deploy.ps1 -Setup       # Create venv, install deps, init data
  .\deploy.ps1 -Docker      # Build and run with Docker Compose
  .\deploy.ps1 -Help        # Show this help

Setup steps:
  1. Creates Python virtual environment in .venv/
  2. Installs all pip dependencies
  3. Verifies requirements
  4. Shows next steps
"@
}

function Invoke-Setup {
    Write-Host "=== PythonAI Setup ===" -ForegroundColor Cyan

    # Step 1: Create virtual environment
    if (-not (Test-Path $VENV)) {
        Write-Host "[1/4] Creating virtual environment..." -ForegroundColor Yellow
        python -m venv $VENV
    } else {
        Write-Host "[1/4] Virtual environment exists, skipping." -ForegroundColor Green
    }

    $python = Join-Path $VENV "Scripts\python.exe"
    $pip = Join-Path $VENV "Scripts\pip.exe"

    # Step 2: Install dependencies
    Write-Host "[2/4] Installing dependencies..." -ForegroundColor Yellow
    & $pip install --upgrade pip
    & $pip install -r (Join-Path $ROOT "requirements.txt")

    # Step 3: Verify installation
    Write-Host "[3/4] Verifying installation..." -ForegroundColor Yellow
    & $python -c "import torch; import transformers; import chromadb; import ollama; import sentence_transformers; print('All core imports OK')"

    # Step 4: Show next steps
    Write-Host "[4/4] Setup complete!" -ForegroundColor Green
    Write-Host @"

Next steps:
  1. Ensure Ollama is running:        ollama serve
  2. Pull the RAG model:              ollama pull qwen2.5-coder:14b
  3. Run the assistant:               & .\.venv\Scripts\python.exe -m src.rag.rag_engine
  4. Or use the CLI:                  & .\.venv\Scripts\python.exe -m src.cli status

Quick start:
  .\.venv\Scripts\python.exe -m src.cli ask "Explain Python decorators"

Docker deployment:
  .\deploy.ps1 -Docker
"@
}

function Invoke-DockerDeploy {
    Write-Host "=== PythonAI Docker Deployment ===" -ForegroundColor Cyan

    # Check Docker
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "Docker is not installed. Please install Docker Desktop first."
        exit 1
    }

    Write-Host "[1/3] Building Docker images..." -ForegroundColor Yellow
    docker compose build

    Write-Host "[2/3] Starting services..." -ForegroundColor Yellow
    docker compose up -d

    Write-Host "[3/3] Services started!" -ForegroundColor Green
    Write-Host @"

Services:
  - Ollama API:  http://localhost:11434
  - PythonAI:    docker compose exec pythonai python -m src.cli status
  - Web UI:      http://localhost:8501

Pull a model first:
  docker compose exec ollama ollama pull qwen2.5-coder:14b

Then ask a question:
  docker compose exec pythonai python -m src.cli ask "Explain Python decorators"

Open the Web UI in your browser:
  http://localhost:8501

Stop:
  docker compose down
"@
}

# ─── Main ───
if ($Help) {
    Show-Help
    exit 0
}

if ($Setup) {
    Invoke-Setup
    exit 0
}

if ($Docker) {
    Invoke-DockerDeploy
    exit 0
}

# Default: show help
Show-Help
