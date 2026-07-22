# FORGEAI — IMPLEMENTATION PLAN
## Week-by-Week Execution | God Mode Ultra Pro Max | June 2026
## "Ship. Measure. Improve. Repeat."

---

## THE IRON LAW OF EXECUTION

> "Ek hafte mein ek working feature. Koi perfect code nahi — working code. Koi beautiful architecture nahi — deployed architecture."

Every Friday: Ship something. Every Monday: Measure it. Every Sunday: Train the model.

---

## PHASE 0: FOUNDATION (Month 1-3)
### Goal: Working capture → training → improvement loop. Your own data proving it works.

---

### WEEK 1: THE CAPTURE ENGINE

**Goal:** VS Code extension captures accept events and writes to SQLite.

**Day 1-2: FastAPI Server Scaffold**
```bash
# Setup
mkdir forgeai && cd forgeai
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn pydantic aiosqlite python-jose

# Create server/main.py
# Create server/routers/events.py  
# Create server/db/local_db.py (SQLite with sqlcipher)
# Run: uvicorn server.main:app --port 7337

# Test: curl -X POST localhost:7337/api/events -d '{"test": true}'
```

**Day 3-4: VS Code Extension**
```bash
# Setup
npm install -g @vscode/vsce yo generator-code
yo code  # Select TypeScript, name: forgeai-extension
cd forgeai-extension

# Create src/eventCapture.ts
# Listen to: vscode.window.onDidChangeTextEditorSelection
# Intercept Tab accept by detecting completion item acceptance
# WebSocket client: ws://localhost:7337/ws/events

npm run compile && code --install-extension forgeai-*.vsix
```

**Day 5: SQLite Schema**
```sql
-- Create tables from TRD schema
-- Test: 10 manual accepts → check SQLite DB has 10 rows
-- Test: check timing <10ms per write
```

**Day 6-7: Integration Test**
```
Open VS Code → Use any AI extension suggestion → Accept it
→ Check SQLite has row
→ Status bar shows "+1 ✓"
✅ Week 1 DONE
```

**Deliverable:** VS Code extension capturing real events to encrypted SQLite.

---

### WEEK 2: TRAINING PIPELINE INTEGRATION

**Goal:** Events from SQLite → QLoRA training → new adapter.

**Day 1-2: Data Pipeline**
```python
# Create server/services/training/data_pipeline.py
# Query SQLite: events not in any training batch
# Format into instruction template
# Save as JSONL training file

# Test with synthetic data (100 fake events)
# Output: training_data.jsonl
```

**Day 3-4: Unsloth Training Integration**
```python
# pip install unsloth unsloth_zoo
# Create server/services/training/phase1_qlora.py

from unsloth import FastLanguageModel, UnslothTrainer

def run_qlora_training(training_data_path: str, project_id: str) -> str:
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
        max_seq_length=4096,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=32,
        target_modules=["q_proj","v_proj","k_proj","o_proj","gate_proj","up_proj","down_proj"]
    )
    # Train with UnslothTrainer
    # Save adapter to /adapters/project_id/v1.safetensors
    return adapter_path

# Run on your own accept events (even 20 is enough for testing)
# Check: adapter file exists, loss decreased, run took <60 minutes
```

**Day 5: SDFT Replay Buffer**
```python
# Create server/services/training/sdft_buffer.py
# Implement: 70/20/10 batch composition
# Test: 100 current + 50 replay + 20 anchor = correct ratios
```

**Day 6-7: Adapter Loading Test**
```bash
# Load new adapter in Ollama
# Create Modelfile: FROM qwen2.5-coder:14b \n ADAPTER /path/to/adapter
# ollama create forgeai-v1 -f Modelfile
# ollama run forgeai-v1 "Complete this Python code: def authenticate..."
# Does it suggest patterns from your training data? Y/N
```

**Deliverable:** Manual trigger → training → new adapter → loading in Ollama.

---

### WEEK 3: cAST RAG ENGINE

**Goal:** Codebase indexed with AST-aware chunking. Retrieval working.

**Day 1-2: Tree-sitter + cAST Chunker**
```python
pip install tree-sitter tree-sitter-python tree-sitter-typescript

# Create server/services/rag/cast_chunker.py
# Implement: parse file → traverse AST → extract semantic nodes
# Support: Python, TypeScript, JavaScript first

# Test on your own project:
# python -c "from cast_chunker import chunk; chunks = chunk('main.py', 'python'); print(len(chunks))"
# Verify: functions are complete, not split at line 100
```

**Day 3: Multi-view Embedder**
```python
pip install sentence-transformers chromadb

# Create server/services/rag/embedder.py
# Use: all-MiniLM-L6-v2 locally (fast, free)
# Or: voyage-code-2 API (better for code, $0.06/1M tokens)
# Test: embed one chunk, verify shape
```

**Day 4-5: Hybrid Retrieval**
```python
pip install rank-bm25

# Create server/services/rag/hybrid_retrieval.py
# BM25 index: tokenize all chunks, save pkl
# ChromaDB: store embeddings
# RRF fusion: combine scores
# API endpoint: POST /api/rag/search {query, project_id}

# Test: query "authentication function" → see relevant chunks returned
```

**Day 6: Indexing Pipeline**
```python
# Create server/services/rag/indexer.py
# Full index: walk all files → cAST chunk → embed → store
# Run on your real project (1000-5000 files)
# Check: <30 seconds for 5000 files (parallel processing)
```

**Day 7: Integration with Agent**
```python
# Inject RAG chunks into agent prompt
# Before: model gets only user message
# After: model gets [CONTEXT: top-10 chunks] + user message
# Test: ask about a specific function in your codebase
# Does it know about it now? Compare with/without RAG
```

**Deliverable:** RAG search working on real codebase. Context-aware suggestions.

---

### WEEK 4: BASIC DASHBOARD

**Goal:** See acceptance rate chart. See training history. Working.

**Day 1-2: Next.js Setup**
```bash
npx create-next-app@latest dashboard --typescript --tailwind --app
cd dashboard
npx shadcn-ui@latest init
npm install recharts @tanstack/react-query zustand
```

**Day 3-4: Core Pages**
```typescript
// /app/(app)/dashboard/page.tsx
// Components needed:
// - MetricCard (acceptance rate, delta, total runs)
// - AcceptanceRateChart (Recharts AreaChart, 12 weeks)
// - RecentRunsList (table, 5 rows)
// - TodaySignalsCounter (live via polling)

// API integration:
// GET localhost:7337/api/metrics/acceptance-rate?project_id=X&weeks=12
// GET localhost:7337/api/training/status?project_id=X
```

**Day 5: Training Monitor Page**
```typescript
// /app/(app)/training/page.tsx
// Live progress bar (WebSocket to localhost:7337/ws/training-progress)
// History table: date, status, examples, improvement
// Force Training Run button
```

**Day 6-7: VS Code Sidebar**
```typescript
// Update extension: sidebar webview showing mini-dashboard
// Acceptance rate number (big)
// Today's signals count
// Last training result
// "Open Dashboard" link → opens browser
```

**Deliverable:** Dashboard running on localhost:3000. Real data from your SQLite.

---

### WEEK 5: DOGFOODING — USE IT YOURSELF

**Goal:** You use ForgeAI for your own projects for 1 full week. Collect 200+ events.

Every day:
- Open VS Code with ForgeAI extension active
- Work on any project
- Accept and reject suggestions normally
- Check dashboard at end of day

Friday: Run training manually → see if suggestions are better.

**What to measure:**
- Week 1 acceptance rate (baseline, from your first 3 days before training)
- Week 1 post-training acceptance rate
- Delta: even +5% is real proof
- Write this down. This is your case study.

**Bug fixes expected this week:**
- Extension not reconnecting after server restart → fix WS auto-reconnect
- Training fails on certain token lengths → add max_length truncation
- RAG returning irrelevant results → tune RRF weights, add metadata filtering

---

### WEEK 6: FIRST 5 BETA USERS

**Goal:** 5 developers using ForgeAI on their projects.

**Day 1: Install Script**
```bash
#!/bin/bash
# forgeai-install.sh
# 1. Check Python 3.12, Ollama installed
# 2. pip install forgeai-server
# 3. forgeai init (interactive setup)
# 4. VS Code extension: code --install-extension forgeai.vsix
# 5. forgeai start
echo "ForgeAI installed. Open VS Code and start coding."
```

**Day 2-3: Documentation**
Write minimal docs:
- README.md (GitHub): 2-minute setup, screenshot of acceptance rate chart
- TROUBLESHOOTING.md: Top 5 install issues and fixes
- CONTRIBUTING.md: How to report bugs

**Day 4: Recruit Beta Users**
Post in:
- Dev.to: "Building an AI coding assistant that fine-tunes on your code. Looking for 5 beta testers."
- Reddit r/programming: Same post
- Discord: Relevant programming servers
- Twitter: Same

**Day 5-7: Onboard Beta Users**
- 1-on-1 calls if needed (Google Meet, 30 min)
- Set up their ForgeAI, watch them use it
- Note every confusion, every bug, every "why doesn't it..."
- Add them to private Discord channel

**Deliverable:** 5 developers actively using ForgeAI.

---

### WEEK 7-8: STABILIZE + FIRST CASE STUDY

**Goal:** Fix beta user bugs. Collect first real case study data.

**Week 7: Bug Fix Sprint**
Prioritize: Every bug that prevents a beta user from completing their first training run.

Common expected issues:
- Windows path handling (backslash vs forward slash)
- Ollama model not found (wrong model name format)
- VS Code extension not detecting accept events from some AI extensions
- Training OOM on 8GB GPU (add gradient checkpointing fallback)

**Week 8: First Case Study**
- Talk to beta user with best results (highest acceptance rate improvement)
- Get exact numbers: Week 1 rate, Week 4 rate, delta
- Write a 500-word blog post: "How X developer's acceptance rate went from 31% to 54% in 3 weeks"
- Include: real chart screenshot, their quote, methodology
- Publish: dev.to, LinkedIn, Twitter
- Submit to Hacker News: "Show HN: ForgeAI — AI coding assistant that actually fine-tunes on your code"

---

### WEEK 9-12: GROWTH PHASE

**Week 9: Product Hunt Preparation**
- Make a 90-second demo video (Loom, with voiceover)
  Show: install → extension active → accept 10 suggestions → training runs → chart improves → better suggestions
- Create screenshots of every key screen
- Write Product Hunt tagline: "The AI coding assistant that gets smarter from your code — real model weights, not just prompts"
- Find 3 Product Hunt hunters who will post for you

**Week 10: Pricing Goes Live**
- Set up Stripe: Free, Go ($9), Team ($49) tiers
- Implement tier gating in ForgeAI server:
  Free: agent works, training disabled
  Go: weekly training enabled
  Team: 5 dev limit, daily training
- Test all payment flows end-to-end

**Week 11: Product Hunt Launch**
- Launch day: Tuesday
- Ask all beta users, Discord members to upvote
- Reply to every comment on PH within 15 minutes
- Post on Twitter throughout the day
- Target: Top 5 of the day

**Week 12: Assess + Plan Month 3**
- Revenue: how many paid subscribers?
- If >20 paid → continue scaling
- If <10 paid → talk to every user, understand why
- Fix the most common objection before Month 3

---

## PHASE 1: PROOF (Month 3-6)

### Month 3: GRPO Training Layer
**Week 13-14: OpenRLHF Integration**
```python
pip install openrlhf

# Create server/services/training/phase2_grpo.py
# 2-GRPO: pair (accepted, rejected) per step
# Reward: acceptance_signal × test_pass_signal
# Run after QLoRA adapter as additional RL step
```

**Week 15-16: Test Signal Integration**
```python
# server/services/capture/signal_enhancer.py
# Git hook: .git/hooks/post-commit
# After commit: run test suite → capture pass/fail per changed function
# Weight accepted suggestions by test_pass_rate
# This is RLVR — verifiable reward, no reward model needed
```

### Month 4: Code Knowledge Graph
**Week 17-18: NetworkX Graph Builder**
```python
# server/services/rag/code_graph.py
# Tree-sitter: extract all function calls, imports, class hierarchies
# Build NetworkX directed graph
# API: POST /api/rag/graph-query {start_node, relationship, depth}
# Test: "What calls authenticate_user?" → correct callers returned
```

**Week 19-20: Graph-Enhanced RAG**
```python
# hybrid_retrieval.py: add graph traversal as third retrieval signal
# If query contains identifier → graph lookup → combine with BM25 + dense
# Evaluate: does context quality improve? (manual + BLEU on held-out set)
```

### Month 5: JetBrains Extension + Test-Time Scaling
**Week 21-22: JetBrains Plugin**
```kotlin
// JetBrains Platform SDK (Kotlin)
// Identical to VS Code extension: capture accepts/rejects
// WebSocket to same localhost:7337 server
// Publish: JetBrains Marketplace
// Target: IntelliJ IDEA, PyCharm, WebStorm
```

**Week 23-24: PDR+RTV Test-Time Scaling**
```python
# server/services/agent/test_time_scaling.py
# Complexity classifier: fast/balanced/powerful
# Hard tasks (>0.7): generate N=5 rollouts → RTV select → PDR refine
# Test: does hard task quality improve? (acceptance rate on agent suggestions)
```

### Month 6: Skills Marketplace Beta
**Week 25-26: Marketplace Backend**
```python
# Supabase table: marketplace_adapters
# API: GET /marketplace/adapters, POST /marketplace/adapters/:id/download
# Sanitization scanner: check adapter for PII, proprietary patterns
# S3 storage for adapter files (Cloudflare R2 — cheaper)
```

**Week 27-28: Marketplace Frontend + First Enterprise Deal**
```typescript
// /app/(app)/skills/page.tsx
// Browse, filter, install adapters
// Upload flow with sanitization feedback
// Earn credits integration (Stripe credits system)

// Enterprise: reach out to 20 fintech/healthcare CTOs
// Demo: privacy, compliance, real acceptance rate data
// Target: 1 signed pilot agreement
```

---

## PHASE 2: PLATFORM (Month 7-12)

### Month 7: SEAL Dual-Loop
```python
# server/services/training/phase3_seal.py
# Inner loop: SFT on self-generated curriculum
# Outer loop: RL reward = downstream acceptance rate
# Self-edit generator: model creates training instructions for itself
# Most technically complex feature — allocate 4 weeks
```

### Month 8: Multi-Team Enterprise Dashboard
```typescript
// New route: /enterprise/teams
// Team creation, developer invitation
// Per-team model metrics
// Centralized audit logs
// SSO: SAML 2.0 integration
```

### Month 9: Series A Preparation
- Update pitch deck with real metrics (acceptance rate data from 200+ teams)
- ARR at this point target: $100K+ (proves product-market fit)
- Hire: 1 developer (ML/Python, focus on training pipeline)
- Hire: 1 customer success (focus on enterprise pilots)
- Begin Series A outreach: YC-affiliated VCs, developer-tool focused funds

### Month 10-11: Scale Features
- Neovim extension (community contribution + ForgeAI support)
- Zed editor extension
- GitHub Actions integration (agent in CI/CD)
- Advanced analytics (Team+ dashboard)
- NVIDIA NIM backend support

### Month 12: Series A Close + Empire Begins
- Close Series A ($2-5M)
- Hire team to 8 people
- Launch in US market (paid marketing begins)
- NVIDIA partnership conversations begin
- $360K ARR target (milestone for Series A close)

---

## TECH DEBT SCHEDULE

**Allowed to skip initially (fix before Series A):**
- Automated testing (write tests Month 3+)
- CI/CD pipeline (set up Month 2)
- Proper error handling (Month 2)
- Documentation (write as you build, Month 1+)

**Never skip:**
- Encryption of SQLite (Day 1 — it's a security product)
- Privacy isolation between projects (Day 1)
- Rollback mechanism for adapters (Week 2)
- HTTPS for cloud API (Day 1)

---

## WEEKLY CADENCE (EVERY WEEK, FOREVER)

**Monday:**
- Review last week's metrics (acceptance rate, sign-ups, revenue, bugs)
- Write 3 goals for this week (no more)

**Tuesday-Thursday:**
- Build. Ship. Nothing else.

**Friday:**
- Ship the feature (even if rough)
- Write 1 tweet about what you built
- Update changelog

**Saturday:**
- Rest OR write 1 blog post / case study

**Sunday:**
- Model trains automatically (2 AM)
- Review training results on Monday morning

---

## COST TRACKER — MONTH BY MONTH

| Month | Infrastructure | Tools | Total |
|-------|---------------|-------|-------|
| 1 | Vercel $0 + Railway $5 + Supabase $0 | - | $5 |
| 2 | Same | Stripe (% of rev) | $5-20 |
| 3 | Same | Resend $20 | $25-40 |
| 4 | Vercel Pro $20 + Railway $10 | PostHog $0 | $30-50 |
| 6 | Same + Cloudflare R2 $5 | Sentry $0 | $35-55 |
| 9 | Railway $30 + Vercel Pro | - | $50-70 |
| 12 | $80-150 (scale with users) | Sentry $26 | $100-200 |

**Year 1 total infra cost estimate: $800-1,500**
**Year 1 revenue target: $130K ARR ($10,850 MRR)**
**Net margin Year 1: >99% (almost zero cost)**

---

## MILESTONE CHECKLIST

**Month 1:**
- [ ] VS Code extension capturing events
- [ ] SQLite encrypted and working
- [ ] Training pipeline (Unsloth QLoRA) running manually
- [ ] cAST RAG indexing working
- [ ] Basic dashboard showing acceptance rate

**Month 2:**
- [ ] 5 beta users onboard
- [ ] First training run on beta user's data
- [ ] First case study data collected
- [ ] Hacker News Show HN post

**Month 3:**
- [ ] Product Hunt launch
- [ ] First 20 paid users
- [ ] GRPO training layer (Phase 2) working
- [ ] MRR: $500+

**Month 6:**
- [ ] 200 teams active
- [ ] First enterprise pilot signed
- [ ] Skills Marketplace beta
- [ ] Test-time scaling live
- [ ] MRR: $8,000+

**Month 9:**
- [ ] 800 teams active
- [ ] 3 enterprise deals
- [ ] JetBrains extension published
- [ ] MRR: $20,000+

**Month 12:**
- [ ] 2,000+ teams
- [ ] 10 enterprise deals
- [ ] SEAL dual-loop (Phase 3) live
- [ ] Series A closed or bootstrapped to profitability
- [ ] MRR: $30,000+ ($360K ARR)

---

## THE SINGLE MOST IMPORTANT THING

**Week 1, Day 1: Open VS Code. Install hello-world extension. See it activate.**

Everything in this document traces back to that one moment. The entire empire starts with a TypeScript file that prints "ForgeAI activated" in the VS Code console.

Then Day 2: Make it capture one event.
Then Day 3: Write that event to a file.
Then Week 2: Make that file become training data.
Then Week 3: See the model improve.

That is the only plan that matters right now.

**Ab ja. Build karo.**

---

*ForgeAI Implementation Plan v3.0*
*Rudraksha | June 2026*
*"From Bhopal to the world — one training run at a time."*
