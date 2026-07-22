# ⚡ FORGEAI ECOSYSTEM — Unified Project Architecture

## "Ek AI toh sab AI — Sab ek saath, sab ek ke liye"

This document maps the complete ForgeAI ecosystem — all projects interconnected into one cohesive system.

---

## 📁 Project Overview

```
Today 1 June/
│
├── PythonAI/                          ← CORE ENGINE (ForgeAI Brain)
│   ├── src/
│   │   ├── agents/                    ← AI Agents (code, debug, docs, teacher)
│   │   ├── rag/                       ← RAG Engine (cAST chunking, knowledge graph)
│   │   ├── learning/                  ← Self-Improvement (capture engine, SDFT)
│   │   ├── training/                  ← Training Pipeline (GRPO, QLoRA, Unsloth)
│   │   ├── core/                      ← Core Engine (tools, MCP, providers)
│   │   ├── api/                       ← REST API Server
│   │   ├── webui/                     ← Web Dashboard
│   │   └── utils/                     ← Utilities (sandbox, validation, metrics)
│   ├── tests/                         ← Test Suite
│   ├── docs/                          ← Documentation
│   └── vscode-extension/              ← VS Code Extension
│
├── hermes-agent-main/                 ← AGENT FRAMEWORK (Multi-agent orchestration)
│   ├── agent/                         ← Agent Core (planning, execution)
│   ├── skills/                        ← Agent Skills (reusable capabilities)
│   ├── tools/                         ← Agent Tools (file ops, shell, git)
│   ├── plugins/                       ← Plugin System
│   ├── web/                           ← Web UI (GrapesJS-based)
│   └── mcp_serve.py                   ← MCP Server
│
├── open-claude-main/                  ← CLI INTERFACE (Terminal AI assistant)
│   ├── src/                           ← TypeScript CLI
│   ├── bin/                           ← Executables
│   ├── vscode-extension/              ← VS Code Extension
│   └── python/                        ← Python Bridge
│
├── Rudra-bots-main/                   ← UI/DASHBOARD (Odysseus Interface)
│   ├── src/                           ← React Frontend
│   ├── core/                          ← Backend Core
│   ├── routes/                        ← API Routes
│   ├── services/                      ← Microservices
│   └── mcp_servers/                   ← MCP Server Instances
│
├── Claude_Code_npm-main/              ← REFERENCE ARCHITECTURE (Claude Code clone)
│   ├── src/                           ← TypeScript Source
│   ├── tools/                         ← Tool Definitions
│   └── components/                    ← UI Components
│
├── superview-sh-main/                 ← COMPETITOR INTELLIGENCE
│   └── claude-code-skills/            ← Skill Templates
│
└── FORGEAI_ECOSYSTEM.md               ← THIS FILE
```

---

## 🔗 Project Interconnections

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FORGEAI ECOSYSTEM FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │  VS Code     │    │   Terminal   │    │    Web       │                  │
│  │  Extension   │───▶│   CLI        │───▶│   Dashboard  │                  │
│  │ (open-claude)│    │ (open-claude)│    │  (Rudra-bots)│                  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                   │                          │
│         ▼                   ▼                   ▼                          │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │              HERMES-AGENT (Multi-Agent Orchestrator)         │          │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │          │
│  │  │ Planner │  │Executor │  │ Monitor │  │ Skill   │        │          │
│  │  │ Agent   │  │ Agent   │  │ Agent   │  │ Manager │        │          │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │          │
│  └───────┼────────────┼────────────┼────────────┼──────────────┘          │
│          │            │            │            │                          │
│          ▼            ▼            ▼            ▼                          │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │              PYTHONAI (Core Engine)                          │          │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │          │
│  │  │  RAG    │  │ Agents  │  │Training │  │ Capture │        │          │
│  │  │ Engine  │  │ System  │  │ Pipeline│  │ Engine  │        │          │
│  │  │ (cAST)  │  │(code,    │  │(QLoRA,  │  │(signals)│        │          │
│  │  │         │  │debug,    │  │GRPO,    │  │         │        │          │
│  │  │         │  │teacher)  │  │SDFT)    │  │         │        │          │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │          │
│  └─────────────────────────────────────────────────────────────┘          │
│                              │                                            │
│                              ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │              MCP SERVERS (Tool Distribution)                 │          │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │          │
│  │  │ File    │  │ Git     │  │ LSP     │  │ Custom  │        │          │
│  │  │ Ops     │  │ Tools   │  │ Server  │  │ Tools   │        │          │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │          │
│  └─────────────────────────────────────────────────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Unified Architecture

### Layer 1: User Interfaces
| Project | Component | Purpose |
|---------|-----------|---------|
| open-claude | VS Code Extension | IDE integration |
| open-claude | Terminal CLI | Command-line interface |
| Rudra-bots | Web Dashboard | Visual analytics |

### Layer 2: Agent Orchestration
| Project | Component | Purpose |
|---------|-----------|---------|
| hermes-agent | Agent Core | Planning & execution |
| hermes-agent | Skills | Reusable capabilities |
| hermes-agent | MCP Server | Tool distribution |

### Layer 3: Core Engine (PythonAI)
| Component | Purpose | Research Backing |
|-----------|---------|------------------|
| RAG Engine | cAST chunking, retrieval | EMNLP 2025 |
| Agents | Code, debug, docs, teacher | Multi-agent systems |
| Training | QLoRA, GRPO, SDFT | NeurIPS 2025, MIT 2026 |
| Capture Engine | Signal collection | MIT SEAL |

### Layer 4: Infrastructure
| Component | Purpose |
|-----------|---------|
| MCP Servers | Standardized tool protocol |
| API Server | REST endpoints |
| WebUI | Real-time dashboard |

---

## 🔄 Integration Points

### 1. PythonAI ↔ Hermes-Agent
```python
# PythonAI provides:
- RAG retrieval for context
- Training data from capture engine
- Fine-tuned model adapters

# Hermes-Agent provides:
- Multi-agent orchestration
- Skill management
- MCP tool distribution
```

### 2. PythonAI ↔ Open-Claude
```python
# PythonAI provides:
- Core AI capabilities
- Model inference
- Training pipeline

# Open-Claude provides:
- CLI interface
- VS Code extension
- User interaction handling
```

### 3. PythonAI ↔ Rudra-bots
```python
# PythonAI provides:
- Analytics data
- Training metrics
- Acceptance rates

# Rudra-bots provides:
- Web dashboard (Odysseus UI)
- Real-time visualization
- User management
```

---

## 📊 Data Flow

### Signal Collection → Training → Deployment

```
1. CAPTURE (PythonAI Capture Engine)
   └── Developer accepts/rejects code
   └── Signal stored in encrypted SQLite

2. PROCESS (PythonAI RAG Engine)
   └── cAST chunking of codebase
   └── Multi-view embedding
   └── Knowledge graph update

3. TRAIN (PythonAI Training Pipeline)
   └── SDFT mixing (70/20/10)
   └── QLoRA fine-tuning (Unsloth 2x speed)
   └── GRPO optimization (verifiable rewards)

4. DEPLOY (Hermes-Agent MCP)
   └── New adapter loaded
   └── Model served via MCP
   └── Available to all interfaces

5. VISUALIZE (Rudra-bots Dashboard)
   └── Acceptance rate charts
   └── Training metrics
   └── Team analytics
```

---

## 🚀 Quick Start

### 1. Install Core Engine (PythonAI)
```bash
cd PythonAI
pip install -r requirements.txt
python -m src.rag.cast_chunker /path/to/project --stats
```

### 2. Start Hermes-Agent
```bash
cd hermes-agent-main
pip install -e .
python hermes_bootstrap.py
```

### 3. Launch Web Dashboard
```bash
cd Rudra-bots-main
npm install
npm run dev
```

### 4. Use CLI Interface
```bash
cd open-claude-main
npm install
npm run build
./bin/open-claude
```

---

## 📈 Project Status

| Project | Status | Role |
|---------|--------|------|
| PythonAI | ✅ Complete | Core Engine |
| hermes-agent | ✅ Available | Agent Framework |
| open-claude | ✅ Available | CLI Interface |
| Rudra-bots | ✅ Available | Web Dashboard |
| Claude_Code_npm | 📚 Reference | Architecture Guide |
| superview-sh | 🔍 Intel | Competitor Analysis |

---

## 🎯 Next Steps

1. **Unify Configuration** — Single config file for all projects
2. **Shared Authentication** — JWT tokens across ecosystem
3. **Unified Logging** — Centralized log aggregation
4. **Cross-Project RPC** — gRPC communication layer
5. **Plugin Marketplace** — Shared skill/extension store

---

*Built by Rudraksha | Bhopal → World | 2026*
*ForgeAI Ecosystem v1.0*