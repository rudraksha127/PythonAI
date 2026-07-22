# FORGEAI — BACKEND SCHEMA & ARCHITECTURE
## Complete System Design | God Mode Ultra Pro Max | June 2026

---

## 1. SYSTEM TOPOLOGY

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DEVELOPER MACHINE                            │
│                                                                      │
│  ┌─────────────────┐   ┌──────────────────────────────────────────┐  │
│  │  VS Code Ext.   │   │         FORGEAI LOCAL PROCESS             │  │
│  │  (TypeScript)   │   │                                          │  │
│  │                 │   │  ┌───────────────────────────────────┐   │  │
│  │  - Intercepts   │   │  │    FastAPI Server (port 7337)     │   │  │
│  │    accepts       │──WS──│    - REST API endpoints           │   │  │
│  │  - Sends events │   │  │    - WebSocket hub                │   │  │
│  │  - Shows status │   │  │    - Auth middleware               │   │  │
│  │                 │   │  └───────┬───────────────────────────┘   │  │
│  └─────────────────┘   │          │                               │  │
│                        │  ┌───────┼─────────────────────────┐     │  │
│  ┌─────────────────┐   │  │       │     CORE MODULES        │     │  │
│  │  Browser        │   │  │  ┌────▼───┐  ┌──────────┐       │     │  │
│  │  Dashboard      │──HTTP  │ Capture │  │  RAG v2  │       │     │  │
│  │  (localhost     │   │  │  │ Module │  │  Engine  │       │     │  │
│  │   :3000) OR     │   │  │  └────┬───┘  └────┬─────┘       │     │  │
│  │  app.forgeai.dev│   │  │       │           │             │     │  │
│  └─────────────────┘   │  │  ┌────▼───────────▼─────────┐   │     │  │
│                        │  │  │   SQLite (encrypted)     │   │     │  │
│  ┌─────────────────┐   │  │  │   events.db              │   │     │  │
│  │  CLI / Terminal │   │  │  │   ChromaDB (vector store) │   │     │  │
│  │  Agent          │──HTTP  │   NetworkX (code graph)   │   │     │  │
│  └─────────────────┘   │  │  └──────────────────────────┘   │     │  │
│                        │  │                                  │     │  │
│                        │  │  ┌──────────────────────────┐   │     │  │
│                        │  │  │   TRAINING SCHEDULER     │   │     │  │
│                        │  │  │   (APScheduler cron)     │   │     │  │
│                        │  │  │   ┌──────────────────┐   │   │     │  │
│                        │  │  │   │  Unsloth QLoRA   │   │   │     │  │
│                        │  │  │   │  OpenRLHF GRPO   │   │   │     │  │
│                        │  │  │   │  SEAL Dual-Loop  │   │   │     │  │
│                        │  │  │   └──────────────────┘   │   │     │  │
│                        │  │  └──────────────────────────┘   │     │  │
│                        │  │                                  │     │  │
│                        │  │  ┌──────────────────────────┐   │     │  │
│                        │  │  │   INFERENCE ENGINE        │   │     │  │
│                        │  │  │   Ollama:11434            │   │     │  │
│                        │  │  │   vLLM:8000 (optional)    │   │     │  │
│                        │  │  │   SGLang:8001 (optional)  │   │     │  │
│                        │  │  └──────────────────────────┘   │     │  │
│                        │  └─────────────────────────────────┘     │  │
│                        └──────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────┘
                                     │ HTTPS (auth + metrics only)
                                     ▼
                        ┌────────────────────────┐
                        │   FORGEAI CLOUD (minimal)│
                        │   api.forgeai.dev        │
                        │                         │
                        │   - Supabase (auth + DB) │
                        │   - Stripe (billing)     │
                        │   - Vercel (dashboard)   │
                        │   - Resend (email)       │
                        │   - PostHog (analytics)  │
                        └────────────────────────┘
```

---

## 2. FASTAPI SERVER — COMPLETE MODULE STRUCTURE

```
forgeai/
├── server/
│   ├── main.py                    # FastAPI app init, lifespan, CORS
│   ├── config.py                  # Settings via pydantic-settings
│   ├── auth.py                    # Local JWT auth, keychain integration
│   │
│   ├── routers/
│   │   ├── events.py              # POST /api/events
│   │   ├── metrics.py             # GET /api/metrics/*
│   │   ├── training.py            # GET/POST /api/training/*
│   │   ├── agent.py               # POST /api/agent/chat (SSE streaming)
│   │   ├── rag.py                 # POST /api/rag/search, /api/rag/index
│   │   ├── projects.py            # CRUD /api/projects
│   │   └── websocket.py           # WS /ws/events, /ws/training-progress
│   │
│   ├── services/
│   │   ├── capture/
│   │   │   ├── capture_service.py      # Event write, weight calculation
│   │   │   └── signal_enhancer.py     # Git hook, test result enrichment
│   │   │
│   │   ├── rag/
│   │   │   ├── cast_chunker.py         # cAST via tree-sitter
│   │   │   ├── embedder.py             # Multi-view embeddings
│   │   │   ├── hybrid_retrieval.py     # BM25 + dense + RRF fusion
│   │   │   ├── code_graph.py           # Call/import graph builder
│   │   │   ├── indexer.py              # Full + incremental indexing
│   │   │   └── agentic_rag.py          # Multi-hop retrieval (LangGraph)
│   │   │
│   │   ├── training/
│   │   │   ├── scheduler.py            # APScheduler cron management
│   │   │   ├── data_pipeline.py        # Events → training pairs
│   │   │   ├── augmentor.py            # Synthetic augmentation (Ollama)
│   │   │   ├── sdft_buffer.py          # Replay buffer for SDFT
│   │   │   ├── phase1_qlora.py         # Unsloth QLoRA training
│   │   │   ├── phase2_grpo.py          # OpenRLHF GRPO training
│   │   │   ├── phase3_seal.py          # SEAL dual-loop training
│   │   │   ├── evaluator.py            # BLEU, acceptance simulation
│   │   │   ├── adapter_manager.py      # Save, load, rollback adapters
│   │   │   └── rollback_guard.py       # Auto-rollback quality check
│   │   │
│   │   ├── agent/
│   │   │   ├── agent_loop.py           # ReAct + memory loop
│   │   │   ├── tool_registry.py        # 40+ tools registry
│   │   │   ├── tools/
│   │   │   │   ├── file_tools.py       # read, write, edit, list
│   │   │   │   ├── shell_tools.py      # bash, command execution
│   │   │   │   ├── git_tools.py        # status, diff, commit, PR
│   │   │   │   ├── search_tools.py     # grep, semantic, symbol
│   │   │   │   ├── test_tools.py       # run, watch, coverage
│   │   │   │   ├── rag_tools.py        # context search, graph query
│   │   │   │   └── training_tools.py   # status, trigger, metrics
│   │   │   ├── router.py               # Task complexity classifier
│   │   │   ├── test_time_scaling.py    # PDR+RTV (Month 6)
│   │   │   └── memory.py               # Cross-session Hermes memory
│   │   │
│   │   └── inference/
│   │       ├── inference_manager.py    # Provider detection + routing
│   │       ├── ollama_client.py        # Ollama API client
│   │       ├── vllm_client.py          # vLLM API client
│   │       ├── sglang_client.py        # SGLang API client
│   │       └── openai_compat.py        # Generic OpenAI-compatible
│   │
│   ├── models/                        # Pydantic models (request/response)
│   │   ├── events.py
│   │   ├── training.py
│   │   ├── projects.py
│   │   └── agent.py
│   │
│   └── db/
│       ├── local_db.py                # SQLite + sqlcipher connection
│       ├── migrations/                # Alembic migrations
│       └── repositories/
│           ├── events_repo.py
│           ├── training_repo.py
│           └── projects_repo.py
│
├── cli/
│   ├── main.py                        # Click CLI entry point
│   ├── commands/
│   │   ├── start.py                   # forgeai start (start server)
│   │   ├── status.py                  # forgeai status
│   │   ├── train.py                   # forgeai train --now
│   │   ├── index.py                   # forgeai index /path/to/repo
│   │   └── config.py                  # forgeai config set key value
│   └── installer.py                   # forgeai install (setup wizard)
│
├── extension/                         # VS Code extension (TypeScript)
│   ├── src/
│   │   ├── extension.ts               # Activation, command registration
│   │   ├── eventCapture.ts            # Accept/reject event interceptor
│   │   ├── wsClient.ts                # WebSocket client to local server
│   │   ├── statusBar.ts               # Status bar item management
│   │   ├── sidebarProvider.ts         # Sidebar webview panel
│   │   └── commands/
│   │       ├── openDashboard.ts
│   │       ├── openAgentChat.ts
│   │       └── forceTraining.ts
│   └── package.json
│
└── dashboard/                         # Next.js app
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                   # Landing page
    │   ├── (auth)/
    │   │   ├── login/
    │   │   └── signup/
    │   ├── onboarding/
    │   │   └── [step]/
    │   └── (app)/
    │       ├── layout.tsx             # Sidebar layout
    │       ├── dashboard/
    │       ├── agent/
    │       ├── training/
    │       ├── projects/
    │       ├── skills/
    │       ├── analytics/
    │       └── settings/
    ├── components/
    │   ├── ui/                        # shadcn/ui components
    │   ├── charts/                    # Recharts wrappers
    │   ├── agent/                     # Chat components
    │   ├── training/                  # Training monitor
    │   └── marketplace/               # Skills components
    └── lib/
        ├── api.ts                     # API client (React Query)
        ├── ws.ts                      # WebSocket connection
        └── store.ts                   # Zustand global state
```

---

## 3. DATA FLOW DIAGRAMS

### 3.1 Accept Event Flow

```
VS Code Extension (TypeScript)
  │  
  │  onAcceptEvent() triggered
  │  Payload built: {type, file, lang, context, suggestion, accepted}
  │
  ▼  WebSocket send to ws://localhost:7337/ws/events
FastAPI WebSocket Handler
  │
  │  Validate payload (Pydantic model)
  │  Compute weight (edit distance, event type)
  │
  ▼  Write to SQLite (async, <5ms)
events table (encrypted SQLite)
  │
  │  ACK sent back to extension: {event_id, captured: true}
  │
  ▼  Status bar update: "+1 ✓" animation
Extension status bar
  │
  └─ (background) Acceptance rate counter updated in memory
     Dashboard WebSocket broadcast: {today_accepts: N}
```

### 3.2 Training Pipeline Flow

```
APScheduler Cron (Sunday 2:00 AM)
  │
  ├─ Check: GPU available? (nvidia-smi / metal check)
  ├─ Check: events count >= MIN_EXAMPLES (50)?
  │
  ▼
data_pipeline.py
  │
  ├─ Fetch events: SELECT * FROM events WHERE training_batch_id IS NULL
  ├─ Classify: positive (accept), negative (reject)
  ├─ Format: instruction template
  │   "### Context:\n{context_before}\n### Complete:\n{context_after}\n### Answer:\n{accepted}"
  ├─ Deduplicate: cosine similarity > 0.95 → drop duplicate
  │
  ▼
augmentor.py (Ollama local call)
  │
  ├─ For each positive example:
  │   Prompt Ollama: "Generate 3 variations of this code completion"
  │   Get 3 synthetic examples
  ├─ Total: N events → 3N-5N training pairs
  │
  ▼
sdft_buffer.py
  │
  ├─ Load replay buffer (previous 2 weeks of examples)
  ├─ Compose batch: 70% current + 20% replay + 10% anchor
  │
  ▼
phase1_qlora.py (Unsloth)
  │
  ├─ Load base model (4-bit QLoRA)
  ├─ Load previous adapter (warm start)
  ├─ Train: UnslothTrainer.train()
  │   - Broadcast progress via WebSocket every 10 steps
  │   - Log loss, learning_rate, step to SQLite
  ├─ Save adapter: /adapters/{project_id}/v{n}.safetensors
  │
  ▼
evaluator.py
  │
  ├─ Load new adapter
  ├─ Run on held-out test set (10%)
  ├─ Compute: BLEU, simulated acceptance rate
  │
  ▼
rollback_guard.py
  │
  ├─ If new_rate < previous_rate - 10%:
  │   → Mark run as 'rolled_back'
  │   → symlink: current → previous adapter
  │   → Notify dashboard: "Rollback triggered"
  ├─ Else:
  │   → symlink: current → new adapter
  │   → Notify Ollama/vLLM to reload
  │   → Update training_runs table: status='completed'
  │   → WebSocket broadcast to dashboard: TrainingComplete event
  │
  ▼
adapter_manager.py
  │
  └─ Archive: /adapters/{project_id}/history/v{n-3}.tar.gz (keep 3)
     Update projects table: current_adapter_path, current_adapter_version
```

### 3.3 RAG Indexing Flow

```
User adds project / git commit hook fires
  │
  ▼
indexer.py
  │
  ├─ Determine: full reindex OR incremental (git diff --name-only)
  ├─ Get file list (respects .gitignore, .forgeignore)
  │
  ▼
cast_chunker.py (per file)
  │
  ├─ Detect language (tree-sitter)
  ├─ Parse AST: tree-sitter parser.parse(code)
  ├─ Traverse AST: find semantic nodes (function, class, method)
  ├─ Chunk: each semantic node = one chunk
  ├─ Metadata: {file_path, node_type, start_line, end_line, language}
  │
  ▼
embedder.py (per chunk)
  │
  ├─ View A embedding: embed(chunk.code_text)
  ├─ View B embedding: embed(chunk.docstring + chunk.comments)
  ├─ View C embedding: embed(chunk.signature + chunk.type_hints)
  ├─ Model: voyage-code-2 (best code embeddings) OR CodeBERT (local)
  │
  ▼
ChromaDB (local)
  │
  ├─ Collection: {project_id}_code
  ├─ Documents: chunk.code_text
  ├─ Embeddings: [view_a, view_b, view_c] stored
  ├─ Metadata: {file_path, node_type, language, start_line, end_line}
  │
  ▼
code_graph.py (parallel with ChromaDB)
  │
  ├─ Build call graph: function → function (via AST call sites)
  ├─ Build import graph: module → module (via import statements)
  ├─ Build inheritance graph: class → class (via class definitions)
  ├─ Storage: NetworkX graph serialized to /graphs/{project_id}.pkl
  │
  ▼
BM25 Index (parallel)
  │
  ├─ Tokenize all chunks (word tokens + code tokens)
  ├─ Build rank_bm25 index
  ├─ Serialize: /bm25/{project_id}.pkl
  │
  ▼
Indexing complete
  │
  └─ Update projects table: rag_indexed_at = NOW()
     Broadcast to dashboard: IndexingComplete event
```

### 3.4 Hybrid Retrieval Flow

```
Query: "How does authenticate_user work?"
  │
  ▼
hybrid_retrieval.py
  │
  ├─ Strategy selector:
  │   Contains "how does X work" → agentic mode (Month 6)
  │   Contains function/variable name → graph + hybrid
  │   General query → hybrid BM25 + dense
  │
  ├─ BM25 retrieval:
  │   bm25_index.get_scores(tokenize(query))
  │   Top-20 chunks by BM25 score
  │
  ├─ Dense retrieval:
  │   query_embedding = embedder.embed(query)
  │   chroma.query(query_embeddings=[query_embedding], n_results=20)
  │   Top-20 chunks by cosine similarity
  │
  ├─ Graph traversal (if function name detected):
  │   Extract function name from query: "authenticate_user"
  │   NetworkX: G.neighbors("authenticate_user") → callers
  │   NetworkX: G["authenticate_user"].keys() → callees
  │   Retrieve those function chunks from ChromaDB
  │
  ├─ Reciprocal Rank Fusion:
  │   score(d) = Σ 1/(k + rank_i(d)) for all retrieval methods
  │   k = 60 (standard RRF constant)
  │   Sort by fused score
  │
  └─ Return top-10 chunks with metadata
     These injected into LLM context window
```

---

## 4. INFERENCE PIPELINE ARCHITECTURE

```
REQUEST: "Complete this code: def process_payment(amount..."
  │
  ▼
inference_manager.py
  │
  ├─ Mode selection (user/auto):
  │   fast: 7B model, no RAG, no scaling → latency priority
  │   balanced: 14B + RAG → quality + speed balance
  │   powerful: 14B + RAG + test-time scaling → quality priority
  │
  ├─ RAG retrieval (if balanced/powerful):
  │   hybrid_retrieval.query("process_payment context...")
  │   Top-10 chunks → formatted as [CONTEXT] in prompt
  │
  ├─ Adapter injection:
  │   Ollama: Modelfile ADAPTER pointing to current adapter
  │   vLLM: --lora-modules flag at server start
  │   SGLang: adapter merge on startup
  │
  ▼
Inference call (streaming):
  │
  ├─ Prompt assembled:
  │   [SYSTEM]: ForgeAI system prompt (team conventions from adapter)
  │   [CONTEXT]: Top-10 RAG chunks
  │   [HISTORY]: Last 5 conversation turns
  │   [USER]: Current request
  │
  ├─ Standard path: Single LLM call, stream tokens to client
  │
  └─ Test-time scaling path (Month 6, hard tasks only):
      PDR+RTV:
        Generate N=5 rollouts in parallel
        Summarize each rollout to compact representation
        Recursive Tournament Voting: compare pairs, select winner
        PDR refine: condition new rollout on winner summary, iterate 2x
        Return refined response
        Latency: 3-5x single pass (acceptable for complex tasks)
```

---

## 5. COMPLETE ENVIRONMENT CONFIGURATION

```toml
# forgeai.config.toml (user's machine)

[server]
host = "127.0.0.1"
port = 7337
log_level = "info"
max_concurrent_requests = 10

[database]
path = "~/.forgeai/events.db"
encryption_key_source = "keychain"  # "keychain" | "env" | "file"
backup_interval_hours = 24

[inference]
default_backend = "ollama"          # "ollama" | "vllm" | "sglang" | "openai"
ollama_url = "http://localhost:11434"
vllm_url = "http://localhost:8000"
sglang_url = "http://localhost:8001"
openai_api_base = "https://api.openai.com/v1"
streaming = true
timeout_seconds = 120

[inference.routing]
fast_model = "qwen2.5-coder:7b-instruct-q4_K_M"
balanced_model = "qwen2.5-coder:14b-instruct-q4_K_M"
powerful_model = "qwen2.5-coder:32b-instruct-q4_K_M"
complexity_threshold_fast = 0.4
complexity_threshold_balanced = 0.7

[training]
schedule = "weekly"                 # "daily" | "weekly" | "manual"
schedule_time = "02:00"
schedule_day = "sunday"
min_examples = 50
max_examples_per_run = 5000
max_duration_minutes = 90
phase = 1                           # 1=QLoRA, 2=GRPO, 3=SEAL
synthetic_augmentation = true
augmentation_factor = 4

[training.qlora]
lora_r = 16
lora_alpha = 32
learning_rate = 2e-4
max_steps = 200
batch_size = 2
gradient_accumulation = 4
optimizer = "adamw_8bit"
quantization = "nf4"

[training.sdft]
enabled = true
current_week_ratio = 0.70
replay_buffer_ratio = 0.20
anchor_set_ratio = 0.10
replay_buffer_weeks = 2

[training.rollback]
enabled = true
threshold_drop = 0.10               # 10% acceptance rate drop triggers rollback

[rag]
embedding_model = "voyage-code-2"   # or "all-MiniLM-L6-v2" for local
chunking_strategy = "cast"          # "cast" | "line" | "token"
max_chunk_tokens = 512
retrieval_k = 10
hybrid_bm25_weight = 0.5
hybrid_dense_weight = 0.5
graph_enabled = true
incremental_indexing = true

[adapters]
storage_path = "~/.forgeai/adapters"
keep_history = 5                    # Number of old adapters to keep

[privacy]
telemetry_enabled = false           # opt-in, default off
raw_code_transmission = false       # always false, not configurable
```

---

## 6. SECURITY IMPLEMENTATION DETAIL

```python
# auth.py — Local JWT authentication

from keyring import get_password, set_password
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import sqlcipher3

SERVICE_NAME = "forgeai-local"

def get_encryption_key() -> bytes:
    """Retrieve or generate AES-256 encryption key from OS keychain."""
    key = get_password(SERVICE_NAME, "db_encryption_key")
    if not key:
        # Generate new key on first run
        machine_id = get_machine_uuid()
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                          salt=machine_id.encode(), iterations=480000)
        key = base64.b64encode(kdf.derive(secrets.token_bytes(32))).decode()
        set_password(SERVICE_NAME, "db_encryption_key", key)
    return base64.b64decode(key)

def get_local_jwt_secret() -> str:
    """Per-machine JWT secret for local API auth."""
    secret = get_password(SERVICE_NAME, "jwt_secret")
    if not secret:
        secret = secrets.token_hex(32)
        set_password(SERVICE_NAME, "jwt_secret", secret)
    return secret

def create_db_connection():
    """SQLite connection with sqlcipher encryption."""
    key = get_encryption_key()
    conn = sqlcipher3.connect(DB_PATH)
    conn.execute(f"PRAGMA key='{key.hex()}'")
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=64000")
    return conn
```

---

## 7. DEPLOYMENT CONFIGURATIONS

### 7.1 Developer (Standard) — docker-compose.yml

```yaml
version: '3.9'
services:
  forgeai:
    image: forgeai/server:latest
    ports:
      - "127.0.0.1:7337:7337"
    volumes:
      - ~/.forgeai:/home/forgeai/.forgeai
      - ./repos:/repos:ro    # project repos mounted read-only
    environment:
      - FORGEAI_TIER=go
      - INFERENCE_BACKEND=ollama
      - OLLAMA_URL=http://host.docker.internal:11434
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
```

### 7.2 Enterprise — docker-compose.enterprise.yml

```yaml
version: '3.9'
services:
  forgeai-server:
    image: forgeai/server:enterprise
    ports:
      - "0.0.0.0:7337:7337"    # Accessible on LAN
    volumes:
      - /data/forgeai:/home/forgeai/.forgeai
      - /repos:/repos:ro
    environment:
      - FORGEAI_TIER=enterprise
      - DATABASE_URL=postgresql://forgeai:${DB_PASSWORD}@postgres:5432/forgeai
      - SSO_ENABLED=true
      - SAML_METADATA_URL=${SAML_URL}
      - AUDIT_LOG_WEBHOOK=${AUDIT_WEBHOOK_URL}
    depends_on:
      - postgres
      - redis
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=forgeai
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}

  forgeai-dashboard:
    image: forgeai/dashboard:enterprise
    ports:
      - "0.0.0.0:3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://forgeai-server:7337
      - NEXTAUTH_SECRET=${NEXTAUTH_SECRET}

volumes:
  postgres_data:
```

---

## 8. MONITORING & OBSERVABILITY

```
Local monitoring (always on):
  - Server health: GET /health → {status, uptime, inference_connected, db_ok}
  - Training monitor: WebSocket /ws/training-progress
  - Performance logs: ~/.forgeai/logs/server.log (rotating, 7 days)

Dashboard metrics (computed locally):
  - Acceptance rate per week (from events table)
  - Training run history (from training_runs table)
  - Suggestions per day (from events table, aggregated)

Enterprise monitoring:
  - Prometheus metrics endpoint: GET /metrics (optional)
  - Sentry error reporting (self-hosted Sentry option)
  - Audit log forwarding via webhook to SIEM systems
  - Health check endpoint for load balancer: GET /healthz

Cloud telemetry (opt-in, no code):
  - Weekly aggregated metrics: {acceptance_rate, training_runs, developers_active}
  - No file paths, no code, no suggestions, no completions
  - PostHog product analytics: page views, feature usage counts
```
