# Changelog

## [2.1.0] — Phase 10: UI & Final Polish (COMPLETE)

### Changed
- **`progress_dashboard.html`** — Updated all 10 phases to 100% complete status
- **`CHANGELOG.md`** — Finalized full 10-phase roadmap documentation

### Removed
- Unused reference directories: `archive/`, `claude-code-source-main/`, `openclaude-main/`, `superview.sh-main/`, `python_brain_godmode/`, `colab_export/`, `extra_data/`
- Stale root files: `unicode_log.txt`, `requirements_god_mode.txt`
- Moved `test_mcp_server.py`, `test_tool_system.py` into `tests/`

---

## [2.0.1] — Phase 9: Deployment & Serving (FastAPI Migration)

### Added
- **`src/api/server.py`** (new) — Production-grade FastAPI server with:
  - `POST /ask` — Single-question RAG endpoint
  - `POST /chat` — Multi-turn chat with history
  - `GET /health` — Health check with version info
  - `GET /stats` — Database statistics
  - `GET /docs` — Auto-generated Swagger UI documentation
  - CORS middleware, Pydantic request validation, structured error handling
- **`src/api/__init__.py`** — Package export for `app`

### Changed
- **`src/cli.py`** — `serve_cmd()` refactored from 150-line `BaseHTTPRequestHandler` to 25-line `uvicorn` launcher

### Removed
- Old inline HTTP server code (BaseHTTPRequestHandler, RAGHandler class) from `cli.py`

---

## [2.0.0] — Phase 8: Training & Fine-Tuning (Verified Complete)

### Status
- Full LoRA/PEFT training pipeline in `src/training/` (trainer, evaluator, checkpoint manager, comparison, viz)
- Dataset assembly pipeline via `scripts/forge_pipeline/` (7-step forge workflow)
- CLI integration: `train`, `eval`, `dataset`, `augment`, `merge` commands all functional

### Changed
- **Root directory cleanup**: Moved `forge_step*.py` scripts to `scripts/forge_pipeline/`
- **Root directory cleanup**: Moved `code_stats_summary.py`, `fast_code_stats.py` to `scripts/utils/`

---

## [Unreleased] — Phase 7: LLM-Based Planning & Synthesis

### Added
- **`src/core/agents/orchestrator.py`** — Added LLM-based intelligent planning and synthesis:
  - `_call_planning_llm()` — encapsulating lightweight text-generation calls to the LLM
  - `_plan_task_llm()` — intelligent JSON-schema based task decomposition
  - `_synthesize_llm()` — intelligent synthesis of sub-agent outputs
- **`tests/test_orchestrator_llm_planning.py`** (new) — ~25 new tests for success, parse-failure, missing-LLM and fallback scenarios
- Maintained total backwards compatibility: robust keyword/concatenation fallbacks hit when the LLM is unavailable or errors out.

## [Archived] — Phase 6: Agent System Polish

### Added
- **`src/core/agents/orchestrator.py`** (535 lines, new) — MCP connection lifecycle management:
  - `cleanup()` — idempotent, exception-safe MCP connection teardown
  - `__del__()` — safety-net destructor calling `cleanup()`
  - `__enter__()` / `__exit__()` — context manager for `with` statement support
  - `_auto_connect_mcp()` — `cleanup()` runs before `try` block (safe on import failure)
  - `run()` — calls `cleanup()` at Phase 4 before returning synthesis
  - `plan_task()` — keyword-based agent planning (researcher → coder → reviewer → mcp)

- **`src/core/agents/sub_agent.py`** (574 lines, new) — Agent tool-call limits and retry system:
  - `max_tool_calls: int = 4` — explicit `__init__` parameter enforced in `run()` loop
  - `max_retries: int = MAX_LLM_RETRIES (2)` — retry with exponential backoff
  - Safety check: when `tool_calls >= max_tool_calls`, forces final LLM call without tools
  - Retry loop in `_call_llm`: `range(max_retries + 1)` with `RETRY_DELAY_SECONDS * (2 ** attempt)` backoff
  - `_last_llm_error` — instance variable capturing actual API error details (incl. `error_detail`)
  - `SubAgentResult.error` now contains the real error message instead of generic "LLM call returned empty"
  - 4 classmethods (coding, research, mcp, review) — thread `max_tool_calls` and `max_retries` via kwargs
  - 4 system prompts with "IMPORTANT: After 2-3 tool calls, stop..." instructions
  - `_build_system_prompt()` — handles both `InputSchema` objects and raw dicts (MCP)

- **`tests/test_orchestrator_cleanup.py`** (511 lines, 31 tests, new) — Orchestrator cleanup tests:
  - 9 test classes: NoMCP, Idempotent, WithMCPClient, AutoConnect, RunCalls, Destructor, ContextManager, MultipleInstances, Integration

- **`tests/test_sub_agent_max_tool_calls.py`** (564 lines, 28 tests, new) — Agent limit & retry tests:
  - 7 test classes: Defaults, SafetyCheck, EdgeCases, ClassmethodThreading, SystemPrompts, MaxRetries, SafetyNetMessage

### Changed
- **`src/core/tool.py`** (+31/-7) — MCP schema compatibility:
  - `to_openai_tool()` — handles both `dict` (MCP) and `InputSchema` (regular)
  - `_unbind(fn)` helper — unwraps bound methods from dynamically-created tool classes

- **`src/core/providers/mistral_provider.py`** (1 line) — Null `tool_calls` fix:
  - `message.get("tool_calls", [])` → `message.get("tool_calls") or []`
  - Fixes: API returning `"tool_calls": null` returns `None` instead of `[]`

- **`src/core/providers/deepseek_provider.py`** (1 line) — Same null `tool_calls` fix

- **`src/core/providers/openai_provider.py`** (1 line) — Same null `tool_calls` fix

- **`src/cli.py`** — `--orchestrate` mode with `AgentOrchestrator` integration, separator characters `─` → `=`, import refactoring

### Fixed
- MCP `dict` vs `InputSchema` collision — added `hasattr`/`isinstance` guards
- MCP connections leaked on orchestrator reuse — `cleanup()` + `self._mcp_client` reference
- `cleanup()` never ran on import failure — moved before `try` block
- `mcp_agent`/`review_agent` silently ignored `max_retries` kwarg — added `kwargs.get()` extraction
- Duplicate `max_retries` keyword in `mcp_agent` — removed duplicate line
- API returning `"tool_calls": null` → provider code got `None` instead of `[]` — `.get("tool_calls") or []` in 3 providers
- API error details (`error_detail`) were dropped — `_last_llm_error` now captures and surfaces full error
- `run()` returned generic "LLM call returned empty" — now includes actual error from `_last_llm_error`
- "No available providers" path referenced removed local `last_error` — changed to `self._last_llm_error`

### Tests
- **317/317 passing** (0 failed, 9 skipped pre-existing)
- Unit + integration suites both clean
