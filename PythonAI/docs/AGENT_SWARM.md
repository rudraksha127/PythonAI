# 🐝 Agent Swarm — Multi-API Parallel Task Execution

## Overview

A parallel task execution system that distributes generation work across 10+ free/cheap AI APIs (Groq, Cerebras, SambaNova, Together, OpenRouter, etc.) with dependency-aware scheduling.

```
                    ┌─────────┐
                    │ Chunk   │
                    └────┬────┘
                         │
              ┌──────────┴──────────┐
              │ TaskDecomposer      │
              │ (10 prompt types)   │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │ AgentSwarm          │
              │ (parallel executor) │
              └──┬───┬───┬───┬─────┘
                 │   │   │   │
          ┌──────┘   │   │   └──────┐
          ▼          ▼   ▼          ▼
      ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
      │ Groq │  │Together│  │Mistral│  │  ...  │
      └──────┘  └──────┘  └──────┘  └──────┘
```

---

## 📝 Prompt to Continue (Agent Swarm Enhancements)

```
Copy-paste into Codebuff to continue:

Enhance the agent swarm system. Here's what I need:

### 1. AgentSwarm Improvements (src/utils/swarm.py)
- Add retry logic with exponential backoff for failed tasks (max 3 retries)
- Add task timeout per individual task (not just per chunk)
- Add progress tracking with ETA per task type
- Add result caching to avoid regenerating identical prompts
- Add priority queue support (high priority tasks execute first)

### 2. New Capabilities
- Add MCP tool integration — let agents call external tools during generation
- Add multi-step agent workflows (research → draft → review → finalize)
- Add agent specialization by API (assign code-review tasks to best API)
- Add RAG-assisted generation (agents can query vector DB for context)

### 3. Monitoring & Observability
- Add per-API success/failure rate tracking
- Add cost estimation (token usage × API pricing)
- Add real-time dashboard in terminal
- Log all API responses to disk for debugging

### 4. Quality Assurance
- Add cross-API consistency checks (same prompt → different APIs → compare)
- Add automated quality scoring with configurable thresholds
- Add human review queue (export low-quality pairs for manual review)
- Add automatic re-generation for pairs below quality threshold
```

---

## 🧩 Swarm Components

| Module | File | Purpose |
|--------|------|---------|
| TaskDecomposer | `src/utils/swarm.py` | Split chunks into dependency-aware tasks |
| AgentSwarm | `src/utils/swarm.py` | Parallel task executor with thread pool |
| Dataset Gen | `src/data/generator.py` | Uses swarm to generate SFT pairs across APIs |

## ⚡ Supported APIs

| API | Model | Key Env Var |
|-----|-------|-------------|
| Groq | Llama 3.3 70B | `GROQ_API_KEY` |
| Cerebras | Llama 3.3 70B | `CEREBRAS_API_KEY` |
| SambaNova | Llama 3.3 70B | `SAMBANOVA_API_KEY` |
| Together | Llama 3.3 70B | `TOGETHER_API_KEY` |
| OpenRouter | Llama 3.3 70B (free) | `OPENROUTER_API_KEY` |
| HuggingFace | Qwen 2.5 72B | `HF_TOKEN` |
| Mistral | Mistral Large | `MISTRAL_API_KEY` |
| Fireworks | Llama 3.3 70B | `FIREWORKS_API_KEY` |
| Novita | Llama 3.3 70B | `NOVITA_API_KEY` |
| DeepInfra | Llama 3.3 70B | `DEEPINFRA_API_KEY` |

## 📌 10 Data Types Generated

| Type | Description |
|------|-------------|
| `basic` | Practical Q&A pairs |
| `reasoning` | Deep reasoning / step-by-step |
| `error_fix` | Bug scenarios + fixes |
| `expert` | Advanced internals + edge cases |
| `interview` | Technical interview Q&A |
| `project` | Complete mini-projects |
| `cross_domain` | Cross-field connections |
| `judgment` | Decision-making trade-offs |
| `multi_agent` | Multi-agent collaboration |
| `version` | Python version-specific behavior |

---

## ✅ Status

[ ] Not started  
[ ] In progress  
[ ] Completed  
