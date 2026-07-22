#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# ForgeAI Ecosystem — Unified Setup Script
# ═══════════════════════════════════════════════════════════════
# "Sab ek saath, sab ek ke liye"
#
# This script sets up all interconnected projects in one go.
# Usage: ./setup_ecosystem.sh [--skip-python] [--skip-node] [--dev]
# ═══════════════════════════════════════════════════════════════

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_PYTHON=false
SKIP_NODE=false
DEV_MODE=false

for arg in "$@"; do
    case $arg in
        --skip-python)
            SKIP_PYTHON=true
            shift
            ;;
        --skip-node)
            SKIP_NODE=true
            shift
            ;;
        --dev)
            DEV_MODE=true
            shift
            ;;
    esac
done

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     FORGEAI ECOSYSTEM — Unified Setup                       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create shared directories
echo -e "${GREEN}[1/6] Creating shared directories...${NC}"
mkdir -p ~/.forgeai/{models,adapters,data,logs,configs}
mkdir -p ~/.forgeai/models/{qlora,grpo,sdft}
mkdir -p ~/.forgeai/data/{signals,replay,foundational}

# Create unified config
cat > ~/.forgeai/config.json << 'EOF'
{
  "version": "2.0.0",
  "ecosystem": {
    "core_engine": "PythonAI",
    "agent_framework": "hermes-agent",
    "cli_interface": "open-claude",
    "dashboard": "Rudra-bots"
  },
  "paths": {
    "models": "~/.forgeai/models",
    "adapters": "~/.forgeai/adapters",
    "data": "~/.forgeai/data",
    "logs": "~/.forgeai/logs",
    "signals_db": "~/.forgeai/signals.db"
  },
  "inference": {
    "backend": "ollama",
    "url": "http://localhost:11434",
    "model": "qwen2.5-coder:7b",
    "fallback": ["openai", "anthropic"]
  },
  "training": {
    "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "lora_rank": 16,
    "learning_rate": 2e-4,
    "sdft_ratios": {
      "current": 0.70,
      "previous": 0.20,
      "foundational": 0.10
    }
  },
  "agents": {
    "orchestrator": "hermes-agent",
    "skills_path": "~/.forgeai/skills"
  }
}
EOF

echo -e "${GREEN}[2/6] Setting up PythonAI (Core Engine)...${NC}"
if [ "$SKIP_PYTHON" = false ]; then
    cd "$SCRIPT_DIR/PythonAI"
    
    # Create venv if not exists
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    
    source .venv/bin/activate
    
    # Install dependencies
    pip install -r requirements.txt
    
    if [ "$DEV_MODE" = true ]; then
        pip install -r requirements-dev.txt
    fi
    
    # Install optional Unsloth for 2x faster training
    if command -v nvidia-smi &> /dev/null; then
        echo -e "${YELLOW}NVIDIA GPU detected. Installing Unsloth for 2x faster training...${NC}"
        pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    fi
    
    # Install tree-sitter for cAST
    pip install tree-sitter tree-sitter-python
    
    # Create data directories
    mkdir -p data/{signals,replay,foundational,checkpoints}
    
    echo -e "${GREEN}✓ PythonAI setup complete${NC}"
fi

echo -e "${GREEN}[3/6] Setting up hermes-agent (Agent Framework)...${NC}"
if [ "$SKIP_PYTHON" = false ]; then
    cd "$SCRIPT_DIR/hermes-agent-main"
    
    # Create venv if not exists
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    
    source .venv/bin/activate
    
    # Install in editable mode
    pip install -e .
    
    # Copy skills to shared location
    mkdir -p ~/.forgeai/skills
    if [ -d "skills" ]; then
        cp -r skills/* ~/.forgeai/skills/ 2>/dev/null || true
    fi
    
    echo -e "${GREEN}✓ hermes-agent setup complete${NC}"
fi

echo -e "${GREEN}[4/6] Setting up open-claude (CLI Interface)...${NC}"
if [ "$SKIP_NODE" = false ]; then
    cd "$SCRIPT_DIR/open-claude-main"
    
    # Install dependencies
    npm install
    
    # Build
    npm run build
    
    # Link globally
    npm link
    
    echo -e "${GREEN}✓ open-claude setup complete${NC}"
fi

echo -e "${GREEN}[5/6] Setting up Rudra-bots (Dashboard)...${NC}"
if [ "$SKIP_NODE" = false ]; then
    cd "$SCRIPT_DIR/Rudra-bots-main"
    
    # Install dependencies
    npm install
    
    echo -e "${GREEN}✓ Rudra-bots setup complete${NC}"
fi

echo -e "${GREEN}[6/6] Creating integration bridges...${NC}"

# Create PythonAI ↔ Hermes-Agent bridge
cat > "$SCRIPT_DIR/PythonAI/src/integration/hermes_bridge.py" << 'PYEOF'
"""
Hermes-Agent Bridge — Connect PythonAI to hermes-agent framework
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

HERMES_PATH = Path.home() / ".." / "hermes-agent-main"
FORGEAI_CONFIG = Path.home() / ".forgeai" / "config.json"


def get_hermes_agent():
    """Get Hermes agent instance for multi-agent orchestration."""
    try:
        from hermes.agent import Agent
        from hermes.skills import SkillRegistry
        
        agent = Agent(config_path=FORGEAI_CONFIG)
        return agent
    except ImportError:
        print("Warning: hermes-agent not installed. Run: pip install -e hermes-agent-main")
        return None


def register_forgeai_skills():
    """Register ForgeAI skills with Hermes."""
    skills_dir = Path.home() / ".forgeai" / "skills"
    if not skills_dir.exists():
        return
    
    for skill_file in skills_dir.glob("*.py"):
        # Dynamic skill loading
        pass


def call_hermes_agent(task: str, context: Optional[dict] = None) -> dict:
    """Send a task to Hermes agent for multi-agent processing."""
    if context is None:
        context = {}
    
    # Add ForgeAI context
    context["forgeai"] = {
        "rag_available": True,
        "training_available": True,
        "capture_available": True,
    }
    
    # Call hermes via subprocess or direct import
    result = subprocess.run(
        ["python", "-m", "hermes", "execute", task, json.dumps(context)],
        capture_output=True,
        text=True,
        cwd=HERMES_PATH,
    )
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": result.stderr, "output": result.stdout}
PYEOF

mkdir -p "$SCRIPT_DIR/PythonAI/src/integration"

# Create PythonAI ↔ Open-Claude bridge
cat > "$SCRIPT_DIR/PythonAI/src/integration/open_claude_bridge.py" << 'PYEOF'
"""
Open-Claude Bridge — Connect PythonAI to open-claude CLI
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

OPEN_CLAUDE_PATH = Path.home() / ".." / "open-claude-main"


def get_open_claude_version() -> str:
    """Get open-claude version."""
    try:
        result = subprocess.run(
            ["open-claude", "--version"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        return "not installed"


def send_to_cli(command: str, args: Optional[dict] = None) -> str:
    """Send a command to open-claude CLI."""
    if args is None:
        args = {}
    
    cmd = ["open-claude", command]
    for key, value in args.items():
        cmd.extend([f"--{key}", str(value)])
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    
    return result.stdout


def get_cli_status() -> dict:
    """Get open-claude status."""
    return {
        "installed": get_open_claude_version() != "not installed",
        "version": get_open_claude_version(),
        "path": str(OPEN_CLAUDE_PATH),
    }
PYEOF

# Create PythonAI ↔ Rudra-bots bridge
cat > "$SCRIPT_DIR/PythonAI/src/integration/rudra_bots_bridge.py" << 'PYEOF'
"""
Rudra-bots Bridge — Connect PythonAI to Rudra-bots dashboard
"""

import json
import requests
from pathlib import Path
from typing import Any, Optional, Dict

RUDRA_BOTS_URL = "http://localhost:3000"


def send_metrics(metrics: Dict[str, Any]):
    """Send training metrics to Rudra-bots dashboard."""
    try:
        response = requests.post(
            f"{RUDRA_BOTS_URL}/api/metrics",
            json=metrics,
            timeout=5,
        )
        return response.status_code == 200
    except requests.ConnectionError:
        print("Warning: Rudra-bots dashboard not running")
        return False


def send_acceptance_rate(date: str, rate: float, accepts: int, rejects: int):
    """Send acceptance rate data to dashboard."""
    return send_metrics({
        "type": "acceptance_rate",
        "date": date,
        "rate": rate,
        "accepts": accepts,
        "rejects": rejects,
    })


def send_training_run(run_data: Dict[str, Any]):
    """Send training run data to dashboard."""
    return send_metrics({
        "type": "training_run",
        **run_data,
    })


def get_dashboard_status() -> dict:
    """Check if Rudra-bots dashboard is running."""
    try:
        response = requests.get(f"{RUDRA_BOTS_URL}/api/health", timeout=5)
        return {"running": response.status_code == 200}
    except requests.ConnectionError:
        return {"running": False}
PYEOF

echo -e "${GREEN}✓ Integration bridges created${NC}"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     FORGEAI ECOSYSTEM SETUP COMPLETE                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo ""
echo "  1. Start Ollama (for inference):"
echo -e "     ${YELLOW}ollama serve &${NC}"
echo ""
echo "  2. Pull a code model:"
echo -e "     ${YELLOW}ollama pull qwen2.5-coder:7b${NC}"
echo ""
echo "  3. Start Hermes-Agent:"
echo -e "     ${YELLOW}cd hermes-agent-main && python hermes_bootstrap.py${NC}"
echo ""
echo "  4. Start Rudra-bots Dashboard:"
echo -e "     ${YELLOW}cd Rudra-bots-main && npm run dev${NC}"
echo ""
echo "  5. Use open-claude CLI:"
echo -e "     ${YELLOW}open-claude${NC}"
echo ""
echo -e "${GREEN}Config file: ${YELLOW}~/.forgeai/config.json${NC}"
echo -e "${GREEN}Data directory: ${YELLOW}~/.forgeai/data/${NC}"
echo -e "${GREEN}Models directory: ${YELLOW}~/.forgeai/models/${NC}"
echo ""