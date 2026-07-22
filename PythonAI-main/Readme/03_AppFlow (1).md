# FORGEAI — APP FLOW DOCUMENT
## Complete User Journey Maps | God Mode Ultra Pro Max | June 2026

---

## FLOW 1: FIRST-TIME USER JOURNEY (Onboarding)

```
[LANDING PAGE]
     │
     ├─ User clicks "Install in 5 minutes" → [SIGNUP PAGE]
     │
[SIGNUP PAGE]
     │
     ├─ Option A: Email + Password → Email verification → [ONBOARDING WIZARD]
     └─ Option B: GitHub OAuth → Auto-verified → [ONBOARDING WIZARD]

[ONBOARDING WIZARD — 4 Steps]
     │
     ├─ STEP 1: VS Code Extension
     │     Shows "Install Extension" button
     │     → Opens VS Code Marketplace (forgeai.install)
     │     Extension install detected via WebSocket ping
     │     ✅ Auto-advance to Step 2
     │     ❌ Manual "I installed it" button fallback
     │
     ├─ STEP 2: Connect Inference Backend
     │     Option A: Ollama (recommended for beginners)
     │       → Show: ollama pull qwen2.5-coder:14b command
     │       → Test connection button → localhost:11434/api/tags
     │       ✅ Models detected → show list → select model → next
     │       ❌ Not found → Troubleshoot modal (firewall, port issues)
     │     Option B: API Key (OpenAI/Anthropic/Groq)
     │       → Paste API key → test → next
     │     Option C: vLLM / SGLang (advanced)
     │       → Enter endpoint URL → test → next
     │
     ├─ STEP 3: Add First Project
     │     Input: Project name
     │     Input: Repository path (local folder browser OR GitHub URL)
     │     Auto-detect: Languages, framework (from package.json/requirements.txt)
     │     RAG indexing: "Indexing your codebase..." progress bar
     │     → Tree-sitter AST chunking runs in background
     │     → ChromaDB populated with cAST chunks
     │     ✅ Indexing complete (show files count, chunk count) → Step 4
     │
     └─ STEP 4: Training Preferences
           Schedule: Weekly (default) / Daily / Manual
           GPU: Auto-detect (show detected GPU + estimated training time)
           Base model: Confirm selected model
           "Start Training Mode" toggle (ON by default)
           → Click "Go to Dashboard" → [MAIN DASHBOARD]

[MAIN DASHBOARD — First Visit]
     │
     ├─ Welcome card: "Your model has 0 training examples so far"
     ├─ Acceptance Rate chart: Empty state with "Accept suggestions to begin"
     ├─ "Quick Start" tooltip sequence (5 tips, dismissable)
     └─ Agent chat panel is highlighted → "Try asking ForgeAI something"
```

---

## FLOW 2: DAILY DEVELOPER WORKFLOW

```
[DEVELOPER OPENS VS CODE]
     │
     ├─ ForgeAI extension auto-connects to local server
     ├─ Status bar shows: "ForgeAI ● Connected | Model: qwen2.5-14b+adapter_v12"
     │
     ├─ Developer writes code normally
     │
[SUGGESTION APPEARS]
     │
     ├─ Source: Tab completion (inline) OR Chat (@ForgeAI in sidebar)
     │
     ├─ Developer evaluates suggestion
     │     │
     │     ├─ ACCEPT (Tab key / click Accept):
     │     │     → VS Code extension captures event
     │     │     → WebSocket POST to localhost:7337/ws/events
     │     │     → Payload: {type:'accept', context, suggestion, file, lang}
     │     │     → SQLite write: <10ms, no UI impact
     │     │     → Status bar briefly shows: "+1 training signal ✓"
     │     │     → Counter in sidebar increments
     │     │
     │     ├─ REJECT (Escape / click Reject):
     │     │     → Capture: {type:'reject', context, suggestion, file, lang}
     │     │     → SQLite write as negative example
     │     │     → Status bar: "-1 (negative signal)"
     │     │
     │     └─ EDIT THEN ACCEPT:
     │           → Developer modifies suggestion before accepting
     │           → edit_distance computed between original and accepted
     │           → Weight = 1.0 - (edit_distance / suggestion_length)
     │           → High edit = lower training weight
     │           → Low edit = high quality match = higher weight
     │
[AGENT CHAT FLOW — Complex Task]
     │
     ├─ Developer types in ForgeAI Chat panel: "@ForgeAI refactor this service"
     │
     ├─ Complexity Classifier evaluates:
     │     → Simple (score < 0.4): Fast 7B model, no test-time scaling
     │     → Medium (0.4-0.7): 14B model with RAG context
     │     → Hard (> 0.7, Month 6+): 14B + PDR+RTV test-time scaling
     │
     ├─ RAG lookup triggered:
     │     → Hybrid search (BM25 + dense) on project ChromaDB
     │     → Graph query: related functions, dependencies
     │     → Top-10 chunks injected into context
     │
     ├─ Agent generates response (streaming):
     │     → Tokens stream to chat panel in real-time
     │     → Code blocks show with copy/apply buttons
     │
     ├─ Developer clicks "Apply to file":
     │     → Code written to file
     │     → Accept event captured (weight: 1.5x, agent response)
     │
     └─ Developer clicks "Reject":
           → Negative signal captured
           → "What was wrong?" optional feedback (tag-based, not typing)
           → Tags: [wrong_pattern, wrong_library, off_context, style_mismatch]
           → These tags become richer training signal
```

---

## FLOW 3: WEEKLY TRAINING RUN (Automated, Background)

```
[SUNDAY 2:00 AM — CRON TRIGGER]
     │
     ├─ APScheduler fires training job
     ├─ Pre-check: GPU available? Events > MIN_EXAMPLES (default: 50)?
     │     → If no GPU: queue for cloud training (Enterprise) or skip
     │     → If < 50 events: skip, notify on Monday morning
     │
     ├─ DATA PIPELINE:
     │     Step 1: Fetch week's events from SQLite
     │       → Filter: weight > 0.3, not in previous batch
     │       → Positive examples: accepted events
     │       → Negative examples: rejected events (for GRPO Phase 2)
     │
     │     Step 2: Preprocessing
     │       → Format: instruction-following template
     │       → "Context: {code_before}\nComplete: {code_after}\nAnswer: {accepted}"
     │       → Deduplication: cosine similarity >0.95 = deduplicate
     │
     │     Step 3: Synthetic Augmentation (Ollama local call)
     │       → Each positive example → 3 variations (different naming, ordering)
     │       → Rejected examples → boundary cases
     │       → 200 events → ~800 training pairs
     │
     │     Step 4: SDFT Batch Composition
     │       → Current week: 70% of batch
     │       → Replay buffer (previous runs): 20%
     │       → Anchor set (Month 1 examples): 10%
     │
     ├─ TRAINING (Unsloth QLoRA, Phase 1):
     │     → Load base model (quantized, 4-bit)
     │     → Load previous adapter (warm start)
     │     → Run training: 200 steps max
     │     → Save new adapter to /adapters/project_id/v{n}.safetensors
     │     → WebSocket broadcast to dashboard: progress updates every 10 steps
     │
     ├─ EVALUATION:
     │     → Load new adapter
     │     → Run on held-out test set (10% of examples, never trained on)
     │     → Compute: BLEU score, simulated acceptance rate
     │     → Compare vs previous adapter metrics
     │
     ├─ DECISION:
     │     → Improvement ≥ 0: Deploy new adapter
     │     → Improvement < -10% acceptance rate: Rollback (restore previous adapter)
     │     → In between: Deploy with warning flag
     │
     ├─ DEPLOYMENT:
     │     → Symlink: /adapters/project_id/current → new adapter
     │     → Ollama/vLLM notified to reload adapter
     │     → SQLite: training_runs row updated with results
     │
     └─ NOTIFICATION (Monday 8 AM):
           → Dashboard notification: "Training complete: +8% acceptance rate"
           → Email (opt-in): Weekly model health report
           → VS Code status bar update: Model v{n} loaded
```

---

## FLOW 4: DASHBOARD NAVIGATION FLOWS

```
[MAIN DASHBOARD — /dashboard]
     │
     ├─ Click "Acceptance Rate Chart" → EXPAND CHART
     │     → Full-page chart with: weekly bars, trend line, training run markers
     │     → Hover over training run marker → show: examples count, improvement delta
     │     → Export as PNG / CSV
     │
     ├─ Click "View Training Runs" → [TRAINING MONITOR]
     │     → List of all runs: date, status, examples, duration, improvement
     │     → Click any run → DETAIL VIEW:
     │           Loss curve chart
     │           Before/after acceptance rate
     │           BLEU score trend
     │           "Rollback to this adapter" button (with confirmation)
     │
     ├─ Click "Force Training Run" → CONFIRMATION MODAL
     │     → "Run training now using X examples from the past N days"
     │     → GPU check: estimated time shown
     │     → Confirm → training queued → redirect to Training Monitor
     │
     ├─ Click "Agent Chat" → [AGENT INTERFACE]
     │     → Full-page Monaco editor on left
     │     → ForgeAI chat on right
     │     → Project file tree in left sidebar
     │     → Model selector dropdown (fast/balanced/powerful)
     │     → Training signal counter in top bar
     │
     ├─ Click "Skills Marketplace" → [MARKETPLACE]
     │     → Browse adapters: filter by language, domain, price
     │     → Click adapter card → DETAIL:
     │           Description, languages, benchmark improvement
     │           "Compose with my model" button
     │           → Merge adapter with team's trained adapter
     │           → Show estimated improvement on team's codebase
     │     → "Upload my adapter" → sanitization flow
     │
     └─ Click "Settings" → [SETTINGS]
           Tabs: Model, Training, Team, Billing, Privacy, Advanced
```

---

## FLOW 5: ENTERPRISE ONBOARDING

```
[ENTERPRISE CONTACT FORM]
     │
     ├─ Fill: company, team size, compliance requirements, tech stack
     ├─ Schedule: 30-min call with founder (Calendly embed)
     │
[ENTERPRISE CALL]
     │
     ├─ Pilot proposal sent: 3-month pilot, 1 team, free
     ├─ Docker compose package sent
     │
[ENTERPRISE SETUP]
     │
     ├─ IT team: docker-compose up -d
     ├─ Admin creates teams, invites developers
     ├─ SSO connected (SAML/OIDC)
     ├─ Audit log forwarding configured (syslog/webhook)
     │
[3-MONTH PILOT]
     │
     ├─ Week 4: First training run complete
     ├─ Month 2: Acceptance rate improvement visible in dashboard
     ├─ Month 3: ROI report generated ($ value)
     │
[CONTRACT CONVERSION]
     │
     ├─ Pilot review call: show ROI data
     ├─ Contract: annual, with SLA terms
     └─ Expansion: more teams, higher developer count
```

---

## FLOW 6: ERROR STATES & RECOVERY

```
ERROR: Training run failed
     → Toast: "Training failed: out of GPU memory"
     → Action button: "Reduce batch size" → auto-configure smaller settings
     → Action button: "View error log"
     → Previous adapter still active — no quality degradation

ERROR: Ollama not running
     → VS Code status bar: "ForgeAI ⚠ Inference offline"
     → Click → modal: "Ollama is not running. Run: ollama serve"
     → Auto-retry every 30 seconds
     → When back online: "Connected ✓" notification

ERROR: RAG indexing failed on file
     → Non-blocking: indexing continues for other files
     → Dashboard shows: "12 files skipped (parse errors)"
     → Download error report → shows which files and why

ERROR: Low training data
     → Sunday cron: <50 examples → skip run
     → Dashboard card: "Need 50+ accepts to train (currently X)"
     → Tip: "Enable Training Mode in VS Code for more signals"

ERROR: Adapter rollback triggered
     → Automatic: if acceptance rate drops >10%
     → Dashboard alert: "Model rolled back to v{n-1} — quality guard triggered"
     → Training run marked as 'rolled_back' with reason
     → Next run: uses larger replay buffer to stabilize

ERROR: Auth token expired
     → API returns 401
     → Frontend: silent token refresh via refresh token
     → If refresh fails: redirect to login with "Session expired" message
```

---

## FLOW 7: SKILLS MARKETPLACE — ADAPTER UPLOAD

```
[DEVELOPER CLICKS "UPLOAD MY ADAPTER"]
     │
     ├─ Step 1: SELECT ADAPTER FILE
     │     → File picker: accepts .safetensors, .bin, .gguf
     │     → Auto-detect: base model, LoRA config
     │
     ├─ Step 2: SANITIZATION SCAN (automated)
     │     → Upload to ForgeAI secure sandbox
     │     → Scan for: company-specific variable names, PII, API keys, proprietary code patterns
     │     → If clean: ✅ pass → Step 3
     │     → If flagged: ❌ show what was found → developer must provide cleaned adapter
     │
     ├─ Step 3: METADATA
     │     → Name, description, domain tags, language tags
     │     → Benchmark: "How much did this improve acceptance rate?"
     │       → Upload chart screenshot (optional) OR enter number manually
     │     → Pricing: Free / Paid ($0 to $49)
     │
     ├─ Step 4: REVIEW & PUBLISH
     │     → ForgeAI team reviews within 48 hours
     │     → Email: "Adapter approved" → published
     │     → Earnings: credited as subscription credits
     │
     └─ [PUBLISHED ADAPTER PAGE]
           → Shows installs count, ratings, community reviews
           → Revenue dashboard: total earned, pending, paid out
```

---

## COMPLETE PAGE LIST WITH ROUTES

```
PUBLIC PAGES (forgeai.dev):
  /                    Landing page
  /how-it-works        Technical explanation
  /pricing             Tier comparison + ROI calculator
  /research            Papers backing ForgeAI
  /case-studies        Real team results
  /blog                Technical content
  /docs                Documentation (Algolia search)
  /docs/quickstart     5-minute install guide
  /docs/configuration  Full config reference
  /docs/training       Training deep dive
  /docs/api            API reference
  /docs/enterprise     Enterprise deployment guide
  /about               Founder story
  /changelog           Version history
  /signup              Registration
  /login               Login
  /forgot-password     Password reset

ONBOARDING (forgeai.dev/onboarding):
  /onboarding/extension     Step 1: Install VS Code extension
  /onboarding/model         Step 2: Connect inference backend
  /onboarding/project       Step 3: Add first project
  /onboarding/preferences   Step 4: Training setup
  /onboarding/complete      Success + go to dashboard

APP PAGES (app.forgeai.dev):
  /dashboard              Main overview
  /agent                  Full-page agent chat + editor
  /training               Training monitor + history
  /projects               Project management
  /projects/:id           Project detail + settings
  /skills                 Marketplace browse
  /skills/:id             Adapter detail
  /skills/upload          Adapter upload flow
  /analytics              Team analytics (Team+)
  /settings               Account settings
  /settings/model         Model configuration
  /settings/training      Training preferences
  /settings/team          Team member management
  /settings/billing       Plan + invoices
  /settings/security      API keys, sessions
  /settings/enterprise    SSO, audit logs, compliance (Enterprise)
  /onboarding             Re-run onboarding
```
