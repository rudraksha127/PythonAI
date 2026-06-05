from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from src.auth import interactive_login, logout, check_auth
from src.auth.config import AuthConfig
from src.auth.decorators import requires_auth
from src.data.apikeys import ALL_PROVIDERS
from src.utils.models import (
    ROOT,
    audit_project,
    cleanup_dry_run,
    dataset_profile,
    discover_qwen_hf_candidates,
    hardware_profile,
    list_hf_cached_models,
    list_ollama_models,
    project_python,
)


VERSION = "2.0.0"


def run(command: list[str]) -> int:
    print(" ".join(command))
    return subprocess.call(command, cwd=ROOT)


def status(args: argparse.Namespace) -> int:
    python_exe = project_python()
    audit = audit_project()
    cleanup = cleanup_dry_run()
    dataset = dataset_profile()
    hardware = hardware_profile(python_exe)
    ollama_models = list_ollama_models()
    hf_models = list_hf_cached_models()
    qwen_hf = discover_qwen_hf_candidates()

    adapter = ROOT / "checkpoints" / "local_auto_model" / "adapter_model.safetensors"
    rag_db = ROOT / "python_brain_godmode" / "chroma.sqlite3"

    # Watch mode
    watch = getattr(args, 'watch', False)
    if watch:
        import time
        try:
            while True:
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] PythonAI Status (--watch, Ctrl+C to stop)")
                print("=" * 72)
                print(f"Project files: {audit['total_files']} ({audit['total_mb']} MB)")
                print(f"Dataset      : {dataset['rows']} rows, avg {dataset['length_avg']} chars")
                print(f"Adapter      : {'ready' if adapter.exists() else 'missing'}")
                print(f"RAG DB       : {'ready' if rag_db.exists() else 'missing'}")
                print(f"RAM          : {hardware.get('ram_gb')} GB")
                time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("\n[Bye] Exiting watch mode.")
            return 0

    # JSON mode
    if getattr(args, 'json_output', False):
        info = {
            "python": str(python_exe),
            "project_files": audit['total_files'],
            "project_mb": audit['total_mb'],
            "cleanup_targets": cleanup['candidate_count'],
            "cleanup_mb": cleanup['recoverable_mb'],
            "dataset_rows": dataset['rows'],
            "dataset_avg_chars": dataset['length_avg'],
            "cuda": hardware.get('cuda_available'),
            "gpu": hardware.get('gpu_name'),
            "ram_gb": hardware.get('ram_gb'),
            "ollama_models": ollama_models,
            "hf_models": hf_models,
            "qwen_candidates": qwen_hf,
            "adapter_ready": adapter.exists(),
            "rag_db_ready": rag_db.exists(),
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    # Standard mode
    print(f"PythonAI v{VERSION} — Status")
    print("=" * 72)
    print(f"Python       : {python_exe}")
    print(f"Project files: {audit['total_files']} ({audit['total_mb']} MB, excluding .venv/.git)")

    if getattr(args, 'verbose', False):
        print(f"  Largest files:")
        for f in audit.get('largest_files', [])[:5]:
            print(f"    {f['path']}: {f['bytes'] / 1024:.1f} KB")
        print(f"  By extension:")
        for ext, info in list(audit.get('by_extension', {}).items())[:8]:
            print(f"    {ext or '(none)':10s}: {info['files']:4d} files, {info['bytes'] / 1024:.1f} KB")

    print(f"Cleanup      : {cleanup['candidate_count']} targets, {cleanup['recoverable_mb']} MB")
    print(f"Dataset      : {dataset['rows']} rows, avg {dataset['length_avg']} chars")
    print(f"CUDA         : {hardware.get('cuda_available')} ({hardware.get('gpu_name')})")
    print(f"RAM          : {hardware.get('ram_gb')} GB")
    print(f"Ollama       : {ollama_models or 'none'}")
    print(f"HF cache     : {hf_models or 'none'}")
    print(f"HF Qwen      : {qwen_hf or 'none'}")
    print(f"Adapter      : {'ready' if adapter.exists() else 'missing'}")
    print(f"RAG DB       : {'ready' if rag_db.exists() else 'missing'}")

    if not qwen_hf:
        print("\nNext real-training step: prepare/download an HF-format Qwen model, then run:")
        print(r"  .\.venv\Scripts\python.exe -m src.training.run --mode qwen --max-steps 50")
    return 0


def login_cmd(args: argparse.Namespace) -> int:
    """Handle login, logout, and check subcommands."""
    config = AuthConfig()

    if args.action == "check":
        status = check_auth(config)
        if status["authenticated"]:
            print(f"[OK] Logged in as: {status['username']}")
            print(f"   Since: {status['logged_in_at']}")
        else:
            print("[FAIL] Not logged in.")
            print("Run:  python -m src.cli login")
        return 0

    if args.action == "logout":
        result = logout(config)
        print(f"[Bye] {result['message']}")
        return 0

    if args.action == "login":
        result = interactive_login(config)
        if result["success"]:
            print(f"[OK] Logged in as: {result['username']}")
        else:
            print(f"[FAIL] Login failed: {result['error']}")
            return 1
        return 0

    return 1


@requires_auth
def train(args: argparse.Namespace) -> int:
    return run([
        str(project_python()),
        "-m", "src.training.run",
        "--mode", args.mode,
        "--max-steps", str(args.max_steps),
        "--max-examples", str(args.max_examples),
        "--max-length", str(args.max_length),
        "--output-dir", args.output_dir,
        "--dataset-path", args.dataset_path,
    ] + (["--skip-train"] if args.skip_train else []))


@requires_auth
def evaluate(args: argparse.Namespace) -> int:
    return run([
        str(project_python()),
        "-m", "src.training.evaluator",
        "--adapter-path", args.adapter_path,
        "--output-json", args.output_json,
    ])


def probe(args: argparse.Namespace) -> int:
    return run([
        str(project_python()),
        "-m", "src.rag.prober",
        "--ollama-model", args.ollama_model,
        "--num-ctx", str(args.num_ctx),
        "--prompt", args.prompt,
    ])


@requires_auth
def ask(args: argparse.Namespace) -> int:
    if args.agents:
        # Route through the swarm orchestrator
        from src.utils.swarm import AgentSwarm, execute_agents
        from src.agents import ALL_AGENTS
        
        print(f"\n[AgentSwarm] Routing question through specialist agents...")
        swarm = AgentSwarm()
        results = execute_agents(args.question, swarm, ALL_AGENTS)
        
        print(f"\n[AI] SWARM RESULTS:")
        print(f"{'─'*55}")
        for agent_name, output in results.items():
            print(f"[{agent_name.upper()}]:\n{output}\n")
        print(f"{'─'*55}")
        return 0
    
    # ── NEW: Tool-calling mode (--tools) ───────────────────────
    if getattr(args, 'tools', False):
        from src.core.engine import ToolCallingEngine
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        # Register tools on first use
        registry = get_registry()
        try:
            register_all_core_tools(registry)
        except Exception:
            pass  # Tools already registered

        print(f"\n[Tools] Tool-Calling Mode (engine ready)")
        print(f"{'='*55}")
        print(f"  Provider  : {args.model or 'auto'}")
        print(f"  Tools     : {registry.total_count} registered")
        print(f"{'─'*55}\n")

        engine = ToolCallingEngine(
            provider="auto",
            model=args.model or "",
            registry=registry,
            on_stream=lambda text: print(text, end="", flush=True),
        )

        if args.question:
            response = engine.run(args.question)
            print(f"\n{'─'*55}")
            print(f"[Stats] {engine.get_stats_report()}")
            print(f"{'='*55}\n")
        else:
            # Interactive mode
            print("Entering interactive tool-calling mode. Type 'exit' to quit.\n")
            while True:
                try:
                    q = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n[Bye] Goodbye!")
                    break
                if not q or q.lower() in ("exit", "quit", "/exit"):
                    break
                if q.lower() == "/tools":
                    for t in registry.list_all():
                        print(f"  - {t.name}: {t.description}")
                    continue
                if q.lower() == "/stats":
                    print(engine.get_stats_report())
                    continue
                if q.lower() == "/clear":
                    engine.reset()
                    print("[Reset] Conversation cleared!")
                    continue

                response = engine.run(q)
                print()
        return 0
    
    cmd = [str(project_python()), "-m", "src.rag.rag_engine"]
    if args.question:
        cmd.extend(["--question", args.question])
    if args.rebuild:
        cmd.append("--rebuild")
    if args.stats:
        cmd.append("--stats")
    if args.no_exec:
        cmd.append("--no-exec")
    if args.exec_timeout > 0:
        cmd.extend(["--exec-timeout", str(args.exec_timeout)])
    if args.query_expansion:
        cmd.append("--query-expansion")
    if args.mmr:
        cmd.append("--mmr")
    if args.version:
        cmd.extend(["--version", args.version])
    if args.category:
        cmd.extend(["--category", args.category])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.list_models:
        cmd.append("--list-models")
    return run(cmd)

def tools_cmd(args: argparse.Namespace) -> int:
    from src.tools import ALL_TOOLS as MCP_TOOLS
    
    # Show both old MCP tools and new Core tools
    print(f"\n[Tools] Registered Tools")
    print(f"{'='*55}")
    
    print(f"\n  MCP Tools ({len(MCP_TOOLS)}):")
    for t in MCP_TOOLS:
        print(f"    - {t.name}: {t.description}")
    
    # Show new Core tools if available
    try:
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools
        registry = get_registry()
        try:
            register_all_tools(registry)
        except Exception:
            pass
        if registry.total_count > 0:
            print(f"\n  Core Tools ({registry.total_count}):")
            for t in registry.list_all():
                ro = " [RO]" if t.is_readonly() else ""
                print(f"    - {t.name}: {t.description}{ro}")
    except ImportError:
        pass
    
    print()
    return 0


def clean(args: argparse.Namespace) -> int:
    command = [str(project_python()), "-m", "src.utils.cleanup"]
    if args.apply:
        command.append("--apply")
    return run(command)


def dataset_info(args: argparse.Namespace) -> int:
    profile = dataset_profile(ROOT / args.path)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


def augment(args: argparse.Namespace) -> int:
    command = [
        str(project_python()),
        "-m", "src.data.augmenter",
        "--model", args.model,
        "--limit", str(args.limit),
        "--offset", str(args.offset),
        "--num-ctx", str(args.num_ctx),
        "--num-predict", str(args.num_predict),
        "--pairs-per-chunk", str(args.pairs_per_chunk),
        "--output", args.output,
    ]
    if args.merge:
        command.append("--merge")
    if args.dry_run:
        command.append("--dry-run")
    return run(command)


def merge_data(args: argparse.Namespace) -> int:
    return run([
        str(project_python()),
        "-m", "src.data.merger",
        "--base", args.base,
        "--add", args.add,
        "--output", args.output,
    ])


def generate_api(args: argparse.Namespace) -> int:
    cmd = [
        str(project_python()),
        "-m", "src.data.api_dataset_gen",
        "--workers", str(args.workers),
    ]
    if args.resume:
        cmd.append("--resume")
    if args.limit > 0:
        cmd.extend(["--limit", str(args.limit)])
    if args.so_only:
        cmd.append("--so-only")
    if args.github_only:
        cmd.append("--github-only")
    if args.no_llm:
        cmd.append("--no-llm")
    return run(cmd)


def graph_cmd(args: argparse.Namespace) -> int:
    cmd = [
        str(project_python()),
        "-m", "src.rag.knowledge_graph",
        args.action,
    ]
    if args.query_text:
        cmd.append(args.query_text)
    if args.hops != 2:
        cmd.extend(["--hops", str(args.hops)])
    if args.max_results != 10:
        cmd.extend(["--max-results", str(args.max_results)])
    return run(cmd)



def apikeys_cmd(args: argparse.Namespace) -> int:
    """Manage API keys for dataset generation."""
    from src.data.apikeys import (
        ALL_PROVIDERS,
        PROVIDER_LABELS,
        active_providers,
        delete_key,
        export_dotenv,
        list_keys,
        set_key,
    )

    if args.action == "list":
        keys = list_keys(masked=not args.show_keys)
        print("[API Keys]")
        print("=" * 60)
        active = set(active_providers())
        for prov in sorted(keys):
            label = PROVIDER_LABELS.get(prov, prov)
            icon = "[OK]" if prov in active else ""
            print(f"  {label:14s}  {keys[prov]:30s}  {icon}")
        print(f"\nActive providers: {len(active)} / {len(ALL_PROVIDERS)}")
        print("Tip:  python -m src.cli apikeys set <provider> <key>")
        return 0

    if args.action == "set":
        result = set_key(args.provider, args.key)
        if result["success"]:
            print(f"[OK] Key saved for '{result['provider']}' (env var: {result['env_var']})")
        else:
            print(f"[FAIL] {result['error']}")
            return 1
        return 0

    if args.action == "delete":
        result = delete_key(args.provider)
        if result["success"]:
            print(f"[OK] Key deleted for '{result['provider']}'")
        else:
            print(f"[FAIL] {result['error']}")
            return 1
        return 0

    if args.action == "export":
        result = export_dotenv(args.path)
        if result["success"]:
            print(f"[OK] Exported {result['count']} keys to {result['path']}")
        else:
            print(f"[FAIL] {result['error']}")
            return 1
        return 0

    return 1


def webui_run(args: argparse.Namespace) -> int:
    """Launch the Streamlit Web UI."""
    if args.daemon:
        import subprocess as sp
        print(f"[Daemon] Starting Web UI on port {args.port} in background...")
        creationflags = 0
        if sys.platform == "win32":
            creationflags = sp.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        else:
            # On Unix, fork and detach
            pid = os.fork()
            if pid > 0:
                print(f"[Daemon] PID: {pid}")
                print(f"[Daemon] Web UI starting at http://localhost:{args.port}")
                return 0
        cmd = [
            str(project_python()),
            "-m", "streamlit", "run",
            str(ROOT / "src" / "webui" / "app.py"),
            "--server.port", str(args.port),
            "--browser.gatherUsageStats", "false",
        ]
        sp.Popen(cmd, creationflags=creationflags, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        print(f"[Daemon] Web UI started at http://localhost:{args.port}")
        return 0

    return run([
        str(project_python()),
        "-m", "streamlit", "run",
        str(ROOT / "src" / "webui" / "app.py"),
        "--server.port", str(args.port),
        "--browser.gatherUsageStats", "false",
    ])


def conv_cmd(args: argparse.Namespace) -> int:
    """List, search, or export saved conversations."""
    from src.rag.rag_engine import (
        export_conversation_markdown,
        list_conversations,
        search_conversations,
    )

    if args.action == "list":
        convs = list_conversations()
        if not convs:
            print("[Empty] No saved conversations found.")
            return 0
        print(f"[Conversations] ({len(convs)} saved)")
        print("=" * 60)
        for c in convs:
            ts = c['timestamp']
            ts_display = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}" if len(ts) >= 14 else ts
            print(f"  {c['file']}")
            print(f"      {ts_display}  |  {c['messages']} msgs  |  {c['size_kb']} KB")
            print(f"      \"{c['summary'][:70] or '(empty)'}\"")
            print()
        return 0

    if args.action == "search" and args.query:
        results = search_conversations(args.query, max_results=10)
        if not results:
            print(f"[No results] No conversations matched \"{args.query}\"")
            return 0
        print(f"[Search] \"{args.query}\" — {len(results)} conversation(s) matched")
        print("=" * 60)
        for r in results:
            print(f"  [{r['timestamp']}] {r['file']}")
            print(f"      Matches: {r['matches']} | Summary: {r['summary'][:60] or '(empty)'}")
            for s in r['snippets'][:2]:
                print(f"      -> {s[:130]}")
            print()
        return 0

    if args.action == "export":
        import json
        from pathlib import Path

        conv_dir = ROOT / "data" / "conversations"
        if not conv_dir.exists():
            print("[Empty] No saved conversations found.")
            return 0

        # Find the conversation file
        target_file = None
        if args.file:
            target_path = conv_dir / args.file
            if target_path.exists():
                target_file = target_path
            else:
                print(f"[Error] Conversation file not found: {args.file}")
                return 1
        else:
            # Use the most recent conversation
            json_files = sorted(conv_dir.glob("conversation_*.json"), reverse=True)
            if not json_files:
                print("[Empty] No saved conversations found.")
                return 0
            target_file = json_files[0]

        # Load the conversation
        history = json.loads(target_file.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            print("[Error] Invalid conversation file format.")
            return 1

        # Export as markdown
        output_path = target_file.with_suffix(".md")
        if args.output:
            output_path = Path(args.output)

        result = export_conversation_markdown(history, output_path)
        print(f"[OK] Exported conversation to: {result}")
        print(f"     File: {target_file.name}")
        print(f"     Messages: {len(history)}")
        return 0

    return 1


def hf_collect(args: argparse.Namespace) -> int:
    """Download Python code SFT datasets from HuggingFace."""
    from src.data.hf_collector import HF_DATASETS, run as hf_run, print_stats

    if args.list:
        print("[HuggingFace Datasets Available]")
        print("=" * 60)
        for key, info in HF_DATASETS.items():
            print(f"  {key:35s} {info['description']}")
            print(f"  {'':35s} Path: {info['path']}")
            print()
        return 0

    if args.stats:
        print_stats(args.output)
        return 0

    datasets = args.datasets if args.datasets else None
    result = hf_run(datasets=datasets, max_rows=args.max_rows, output=args.output)
    total = result.get("total", 0)
    if total == 0:
        print("[WARN] No chunks were collected. Check your internet connection or try --list to see available datasets.")
        return 1
    print(f"Done. {total:,} chunks collected.")
    return 0


def serve_cmd(args: argparse.Namespace) -> int:
    """Start a lightweight HTTP API server for the RAG assistant."""
    port = args.port
    host = args.host

    print(f"[Serve] Starting PythonAI HTTP API on {host}:{port}...\n")
    print(f"  Endpoints:")
    print(f"    POST /ask          Ask a Python question")
    print(f"    POST /chat         Chat with history")
    print(f"    GET  /health       Health check")
    print(f"    GET  /stats        Database statistics\n")

    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    import urllib.parse

    # Lazy-load RAG db once and cache it
    _db = None

    def get_db():
        nonlocal _db
        if _db is None:
            from src.rag.rag_engine import load_or_build_db
            _db = load_or_build_db()
        return _db

    class RAGHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/health":
                self._json({"status": "ok", "version": VERSION})
            elif parsed.path == "/stats":
                try:
                    coll, emb, bm, corp, cfile = get_db()
                    self._json({
                        "status": "ok",
                        "chunks": coll.count(),
                        "db_path": str(cfile),
                    })
                except Exception as e:
                    self._json({"status": "error", "message": str(e)}, 500)
            else:
                self._json({"error": "Not found"}, 404)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json({"error": "Invalid JSON"}, 400)
                return

            if parsed.path == "/ask":
                question = data.get("question", "")
                if not question:
                    self._json({"error": "Missing 'question' field"}, 400)
                    return
                try:
                    coll, embedder, bm25, corpus, cfile = get_db()
                    model = data.get("model", "")
                    from src.rag.rag_engine import get_answer, DEFAULT_MODEL
                    from src.rag.models import resolve_model, list_ollama_models
                    available = list_ollama_models()
                    selected = resolve_model(model or DEFAULT_MODEL, available=available)
                    answer, docs = get_answer(
                        question, coll, embedder, [],
                        bm25=bm25, corpus_texts=corpus,
                        use_query_expansion=data.get("query_expansion", False),
                        use_mmr=data.get("mmr", False),
                        mmr_lambda=data.get("mmr_lambda", 0.7),
                        no_exec=True,
                        model=selected,
                    )
                    self._json({
                        "answer": answer,
                        "sources": [
                            {"title": d["title"], "version": d.get("version", ""), "category": d.get("category", "")}
                            for d in docs
                        ],
                        "model": selected,
                    })
                except Exception as e:
                    self._json({"error": str(e)}, 500)

            elif parsed.path == "/chat":
                question = data.get("question", "")
                history = data.get("history", [])
                if not question:
                    self._json({"error": "Missing 'question' field"}, 400)
                    return
                try:
                    coll, embedder, bm25, corpus, cfile = get_db()
                    model = data.get("model", "")
                    from src.rag.rag_engine import get_answer, DEFAULT_MODEL
                    from src.rag.models import resolve_model, list_ollama_models
                    available = list_ollama_models()
                    selected = resolve_model(model or DEFAULT_MODEL, available=available)
                    answer, docs = get_answer(
                        question, coll, embedder, history[-10:],
                        bm25=bm25, corpus_texts=corpus,
                        use_query_expansion=data.get("query_expansion", False),
                        use_mmr=data.get("mmr", False),
                        mmr_lambda=data.get("mmr_lambda", 0.7),
                        no_exec=True,
                        model=selected,
                    )
                    self._json({
                        "answer": answer,
                        "sources": [
                            {"title": d["title"], "version": d.get("version", ""), "category": d.get("category", "")}
                            for d in docs
                        ],
                        "model": selected,
                    })
                except Exception as e:
                    self._json({"error": str(e)}, 500)
            else:
                self._json({"error": "Not found"}, 404)

        def _json(self, data: dict, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

        def log_message(self, format, *args):
            print(f"[HTTP] {args[0]} {args[1]} {args[2]}")

        def do_OPTIONS(self):
            """Handle CORS preflight requests."""
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

    server = HTTPServer((host, port), RAGHandler)
    print(f"[OK] Server running at http://{host}:{port}")
    print("     Press Ctrl+C to stop.\n")

    # Graceful shutdown
    def shutdown(sig, frame):
        print("\n[Shutdown] Stopping server...")
        server.shutdown()
        print("[Bye] Server stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    server.serve_forever()
    return 0


def dashboard_cmd(args: argparse.Namespace) -> int:
    """Open the live OMNISCIENT AI dashboard."""
    import subprocess as sp
    dashboard_path = ROOT / "dashboard.html"
    if not dashboard_path.exists():
        print(f"[Error] Dashboard not found at: {dashboard_path}")
        return 1
    print(f"[Dashboard] Opening live visualization...")
    sp.Popen(["cmd", "/c", "start", str(dashboard_path)], shell=True)
    return 0


def collect_data_cmd(args: argparse.Namespace) -> int:
    """Collect data and store on D: drive."""
    cmd = [str(project_python()), "-m", "src.data.d_drive_collector"]
    if args.all:
        cmd.append("--all")
    if args.setup:
        cmd.append("--setup")
    if args.source:
        cmd.extend(["--source", args.source])
    cmd.extend(["--so-pages", str(args.so_pages)])
    cmd.extend(["--github-pages", str(args.github_pages)])
    return run(cmd)


def export_cmd(args: argparse.Namespace) -> int:
    """Export adapter to GGUF / ONNX format."""
    from src.utils.models import project_python

    adapter_path = Path(args.adapter_path)
    if not adapter_path.exists():
        print(f"[Error] Adapter path not found: {adapter_path}")
        return 1
    if not (adapter_path / "adapter_config.json").exists():
        print(f"[Error] No adapter_config.json found in {adapter_path}")
        return 1

    print(f"[Export] Exporting adapter from: {adapter_path}")
    print()

    if args.format == "gguf":
        print("  GGUF export guide:")
        print("  1. Merge LoRA weights into base model:")
        print(f"     python -m transformers-cli merge --peft {adapter_path} --output ./merged_model")
        print("  2. Convert to GGUF:")
        print("     git clone https://github.com/ggerganov/llama.cpp")
        print("     python llama.cpp/convert.py ./merged_model --outfile model.gguf")
        print()
        print(f"  Output would be: {adapter_path.parent / (adapter_path.name + '.gguf')}")

    elif args.format == "onnx":
        print("  ONNX export guide:")
        print("  1. Install optimum:")
        print("     pip install optimum[onnxruntime]")
        print("  2. Export:")
        print(f"     optimum-cli export onnx --model {adapter_path} ./onnx_output")
        print()
        print(f"  Output would be: {adapter_path.parent / 'onnx_output'}")

    else:
        print(f"  Unknown format: {args.format}")
        print("  Supported formats: gguf, onnx")
        return 1

    print()
    print("[Tip] For production deployment, consider using:")
    print("  - llama.cpp for GGUF (CPU/GPU inference)")
    print("  - ONNX Runtime for cross-platform deployment")
    print("  - vLLM for high-throughput serving")
    return 0



# ════════════════════════════════════════════
# Discovery Engine Commands
# ════════════════════════════════════════════

def discovery_cmd(args: argparse.Namespace) -> int:
    """Discovery Engine — automated dataset discovery."""
    from src.data.discovery import (
        auto_discover,
        check_for_new_papers,
        discover_government_data,
        discover_github_repos,
        extract_datasets_from_papers,
        PriorityRanker,
        print_ranking,
    )
    from src.data.metadata import MetadataManager

    if args.action == "scan":
        print("[Discovery] Scanning all sources for new datasets...\n")
        results = auto_discover(
            hf_limit=args.hf_limit,
            arxiv_limit=args.arxiv_limit,
            gov_limit=args.gov_limit,
            github_limit=args.github_limit,
            top_n=args.top_n,
            verbose=args.verbose,
        )
        print()
        print_ranking(results)
        print(f"\nTotal ranked: {len(results)}")

        # Offer to register top results
        if args.register and results:
            mgr = MetadataManager()
            records = [s.record for s in results if s.priority in ("critical", "high")]
            if records:
                mgr.register_many(records)
                print(f"\nRegistered {len(records)} high-priority datasets to metadata registry.")
        return 0

    if args.action == "papers":
        print("[Discovery] Checking arXiv for new papers...")
        records = check_for_new_papers(
            categories=args.categories or None,
            max_results=args.arxiv_limit,
            verbose=True,
        )
        if not records:
            print("  No papers found (or arXiv API unavailable).")
        return 0

    if args.action == "gov":
        print("[Discovery] Searching government data portals...")
        records = discover_government_data(
            keywords=args.keywords or None,
            limit=args.gov_limit,
            verbose=True,
        )
        if not records:
            print("  No datasets found (or portal unavailable).")
        return 0

    if args.action == "github":
        print("[Discovery] Scanning trending GitHub repos...")
        records = discover_github_repos(
            languages=args.languages or None,
            limit=args.github_limit,
            verbose=True,
        )
        if not records:
            print("  No repos found (or GitHub API unavailable).")
        return 0

    if args.action == "rank":
        """Score and rank already-registered datasets."""
        mgr = MetadataManager()
        records = mgr.all()
        if not records:
            print("[Discovery] No datasets in registry. Run 'python -m src.cli data init' first.")
            return 1

        ranker = PriorityRanker()
        scored = ranker.score(records)
        print(f"[Discovery] Ranking {len(records)} registered datasets:\n")
        print_ranking(scored[:args.top_n])

        # Summary
        tiers = {}
        for s in scored:
            tiers[s.priority] = tiers.get(s.priority, 0) + 1
        print(f"\nSummary by priority tier:")
        for tier in ("critical", "high", "medium", "low"):
            if tier in tiers:
                print(f"  {tier:10s}: {tiers[tier]}")
        return 0

    return 1


# ════════════════════════════════════════════
# Training Commands
# ════════════════════════════════════════════

def training_cmd(args: argparse.Namespace) -> int:
    """Enhanced training pipeline management."""
    from src.training.config import (
        TrainingConfig,
        smoke_config,
        quick_config,
        qwen_config,
        production_config,
    )
    from src.training.checkpoint_manager import CheckpointManager, format_meta

    if args.action == "config":
        """Show / generate / save training configs."""
        if args.preset == "smoke":
            cfg = smoke_config()
        elif args.preset == "quick":
            cfg = quick_config()
        elif args.preset == "qwen":
            cfg = qwen_config()
        elif args.preset == "production":
            cfg = production_config()
        elif args.preset == "custom" and args.config_file:
            cfg = TrainingConfig.from_file(args.config_file)
        else:
            cfg = TrainingConfig()

        if args.save:
            path = cfg.to_json(args.save)
            print(f"[Training] Config saved to: {path}")
            return 0

        if args.json:
            import json
            print(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2))
            return 0

        print("[Training] Configuration Summary")
        print("=" * 50)
        print(cfg.summary)
        if args.all:
            import json
            print(f"\nFull config (JSON):")
            print(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.action == "checkpoints":
        """List / inspect / clean training checkpoints."""
        mgr = CheckpointManager(base_dir=args.checkpoint_dir)

        if args.checkpoint_list:
            checkpoints = mgr.list(
                sort_by=args.sort_by,
                reverse=not args.ascending,
                max_results=args.limit,
                model_filter=args.model_filter,
                tag_filter=args.tag_filter,
            )
            if not checkpoints:
                print("[Checkpoints] No checkpoints found.")
                return 0
            print(f"[Checkpoints] {len(checkpoints)} found")
            print(mgr.compare([c.name for c in checkpoints[:20]]))
            return 0

        if args.checkpoint_show:
            meta = mgr.get(args.checkpoint_show)
            if not meta:
                print(f"[Checkpoints] '{args.checkpoint_show}' not found.")
                return 1
            print("[Checkpoint]")
            print(format_meta(meta))
            return 0

        if args.checkpoint_delete:
            mgr.delete(args.checkpoint_delete)
            return 0

        if args.checkpoint_best:
            best = mgr.find_best(model_filter=args.model_filter)
            if best:
                print("[Best Checkpoint]")
                print(format_meta(best))
            else:
                print("[Checkpoints] No checkpoints with eval loss found.")
            return 0

        if args.checkpoint_clean:
            deleted = mgr.clean(
                keep_best=args.keep_best,
                keep_last=args.keep_last,
                max_age_days=args.max_age,
                dry_run=args.dry_run,
            )
            if not deleted:
                print("[Checkpoints] Nothing to clean.")
            else:
                print(f"[Checkpoints] Cleaned {len(deleted)} checkpoints.")
            return 0

        # Default: list all
        checkpoints = mgr.list(max_results=20)
        if not checkpoints:
            print("[Checkpoints] No checkpoints found.")
        else:
            print(mgr.compare([c.name for c in checkpoints]))
        return 0

    return 1


# ════════════════════════════════════════════
# Phase 1 Data Collection Commands
# ════════════════════════════════════════════

def phase1_cmd(args: argparse.Namespace) -> int:
    """Phase 1 data collection commands."""
    from src.data.metadata import MetadataManager
    from src.data.phase1 import generate_phase1_datasets, phase1_stats
    from src.data.downloader import DownloadOrchestrator, BASE_DATA_DIR
    from src.data.quality import QualityPipeline

    if args.action == "init":
        mgr = MetadataManager()
        records = generate_phase1_datasets()
        mgr.register_many(records)
        stats = mgr.summary()
        print(f"[Phase1] Initialized metadata registry with {stats['total_datasets']} datasets over 4 weeks")
        for phase in range(1, 5):
            ds = mgr.list_by_phase(phase)
            ready = sum(1 for d in ds if d.is_ready)
            print(f"  Phase {phase}: {len(ds)} datasets ({ready} ready)")
        print(f"  Estimated total records: {stats['estimated_records']:,}")
        print(f"  Registry path: {mgr.storage_path}")
        print(f"  Data directory: {BASE_DATA_DIR}")
        print()
        print("  Next: Run 'python -m src.cli data phase1 status' to see collection status.")
        print("        Run 'python -m src.cli data phase1 download --week 1' to start downloading.")
        return 0

    if args.action == "status":
        mgr = MetadataManager()
        stats = mgr.summary()
        pipeline = mgr.pipeline_status()
        print(f"[Phase1] Collection Status")
        print(f"  Total datasets : {stats['total_datasets']}")
        print(f"  By status:")
        for status, count in sorted(stats['by_status'].items()):
            print(f"    {status:20s}: {count}")
        print(f"  By phase:")
        for phase, count in sorted(stats['by_phase'].items()):
            pp = pipeline['phases'].get(f'phase_{phase}', {})
            ready = pp.get('ready', 0)
            pct = pp.get('progress_pct', 0)
            print(f"    Phase {phase}: {count} datasets ({ready} ready, {pct}%)")
        print(f"  Ready records  : {stats['ready_records']:,}")
        print(f"  Ready size     : {stats['ready_gb']} GB")
        if stats.get('errors'):
            print(f"  Errors ({len(stats['errors'])}):")
            for err in stats['errors'][:5]:
                print(f"    - {err['id']}: {err['error'][:100]}")
        print()
        # Week-by-week breakdown
        for w in range(1, 5):
            wp = mgr.week_progress(1, w)
            if wp['total'] > 0:
                print(f"  Week {w}: {wp['done']}/{wp['total']} done ({wp['progress_pct']}%)")
        return 0

    if args.action == "stats":
        stats = phase1_stats()
        print(f"Phase 1 — Foundation Data Collection")
        print(f"  Total datasets    : {stats['total_datasets']}")
        print(f"  Estimated records : {stats['estimated_total_records']:,}")
        print(f"  Estimated size    : {stats['estimated_total_gb']} GB")
        print()
        print("  By Week:")
        for w, c in sorted(stats['by_week'].items()):
            print(f"    Week {w}: {c} datasets")
        print()
        print("  By Domain:")
        for d, c in sorted(stats['by_domain'].items()):
            print(f"    {d}: {c} datasets")
        return 0

    if args.action == "list":
        mgr = MetadataManager()
        if args.week:
            records = mgr.list_by_week(1, args.week)
        elif args.status:
            records = mgr.list_by_status(args.status)
        elif args.domain:
            from src.data.metadata import DataDomain
            records = mgr.list_by_domain(DataDomain(args.domain))
        else:
            records = mgr.list_by_phase(1)
        
        print(f"{'ID':40s} {'Status':16s} {'Lang':8s} {'Records':>12s} {'GB':>8s}")
        print(f"{'─'*40} {'─'*16} {'─'*8} {'─'*12} {'─'*8}")
        for r in records:
            lang_str = ",".join(r.languages)[:8]
            rec_str = f"{r.actual_record_count:,}" if r.actual_record_count > 0 else "-"
            gb_str = f"{r.size_mb/1024:.1f}" if r.actual_size_bytes > 0 else "-"
            print(f"{r.id:40s} {r.status.value:16s} {lang_str:8s} {rec_str:>12s} {gb_str:>8s}")
        print(f"\nTotal: {len(records)} datasets")
        return 0

    if args.action == "download":
        import asyncio
        mgr = MetadataManager()
        
        orch = DownloadOrchestrator(
            metadata_mgr=mgr,
            max_concurrent=args.workers,
            log_callback=lambda msg: print(msg),
        )
        
        async def run_downloads():
            try:
                if args.dataset:
                    results = [await orch.download_one(args.dataset)]
                elif args.week:
                    results = await orch.download_week(1, args.week)
                else:
                    results = await orch.download_all_phase(1)
            finally:
                await orch.close()
            return results
        
        results = asyncio.run(run_downloads())
        
        success = sum(1 for r in results if "error" not in r)
        failed = sum(1 for r in results if "error" in r)
        total_records = sum(r.get("records", 0) for r in results if "error" not in r)
        
        print(f"\n[Download Complete] {success} succeeded, {failed} failed, {total_records:,} records")
        for r in results:
            if "error" in r:
                print(f"  ✗ {r['dataset_id']}: {r['error'][:80]}")
            else:
                records = r.get("records", 0)
                print(f"  ✓ {r['dataset_id']}: {records:,} records")
        return 0 if failed == 0 else 1

    if args.action == "quality":
        from pathlib import Path
        mgr = MetadataManager()
        dataset_ids = args.datasets if args.datasets else [d.id for d in mgr.list_by_status("downloaded")]
        
        qp = QualityPipeline(
            min_text_length=args.min_length,
            quality_threshold=args.threshold,
            metadata_mgr=mgr,
        )
        
        for did in dataset_ids:
            record = mgr.get(did)
            if not record:
                print(f"[Error] Dataset '{did}' not found")
                continue
            
            if not args.input_dir:
                import os as os_mod
                data_dir = os_mod.environ.get("DATA_DIR", "D:/PythonAI_Data")
                dataset_path = Path(data_dir) / record.output_subdir / f"{did}.jsonl"
            else:
                dataset_path = Path(args.input_dir) / f"{did}.jsonl"
            
            if not dataset_path.exists():
                print(f"[Skip] {did}: data file not found at {dataset_path}")
                continue
            
            print(f"[Quality] Running pipeline on {did}...")
            stats = qp.run_file(dataset_path, did)
            if "error" in stats:
                print(f"  Error: {stats['error']}")
                continue
            
            print(f"  Input: {stats['total_input']:,} records")
            print(f"  Output: {stats['total_output']:,} records")
            print(f"  Filtered: {stats['filtered_pct']}%")
            print(f"  Avg quality score: {stats.get('avg_quality_score', 'N/A')}")
            for stage_name, stage_data in stats.get('stages', {}).items():
                if isinstance(stage_data, dict):
                    removed = stage_data.get('removed', 0)
                    if removed:
                        print(f"    {stage_name}: removed {removed}")
            print(f"  Elapsed: {stats.get('elapsed_seconds', '?')}s")
        return 0

    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (exported for testing)."""
    parser = argparse.ArgumentParser(
        description="One-command entrypoint for the PythonAI project.",
        epilog="Run 'python -m src.cli <command> --help' for command-specific help.",
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument("--completion", choices=["bash", "zsh", "fish"], default=None,
                        help="Print shell tab-completion script and exit")
    sub = parser.add_subparsers(dest="command")

    status_parser = sub.add_parser("status", help="Show project, dataset, hardware, and model state.")
    status_parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    status_parser.add_argument("--verbose", action="store_true", help="Show extended details")
    status_parser.add_argument("--watch", action="store_true", help="Watch mode — continuously print status")
    status_parser.add_argument("--watch-interval", type=int, default=5, help="Watch mode refresh interval (seconds)")
    status_parser.set_defaults(func=status)

    train_parser = sub.add_parser("train", help="Run local training.")
    train_parser.add_argument("--mode", choices=["auto", "smoke", "qwen"], default="auto")
    train_parser.add_argument("--max-steps", type=int, default=8)
    train_parser.add_argument("--max-examples", type=int, default=128)
    train_parser.add_argument("--max-length", type=int, default=384)
    train_parser.add_argument("--output-dir", default="checkpoints/local_auto_model")
    train_parser.add_argument("--dataset-path", default="data/training/training_dataset.json")
    train_parser.add_argument("--skip-train", action="store_true")
    train_parser.add_argument("--no-auth", action="store_true", help="Skip authentication check")
    train_parser.add_argument("--viz", action="store_true", help="Save comprehensive training visualization (dashboard, LR, throughput, HTML, JSON)")
    train_parser.set_defaults(func=train)

    login_parser = sub.add_parser("login", help="Login, logout, or check auth status.")
    login_parser.add_argument("action", nargs="?", choices=["login", "logout", "check"], default="login",
                              help="Action to perform (default: login)")
    login_parser.set_defaults(func=login_cmd)

    eval_parser = sub.add_parser("eval", help="Evaluate saved PEFT adapter.")
    eval_parser.add_argument("--adapter-path", default="checkpoints/local_auto_model")
    eval_parser.add_argument("--output-json", default="checkpoints/local_eval_outputs.json")
    eval_parser.add_argument("--no-auth", action="store_true", help="Skip authentication check")
    eval_parser.set_defaults(func=evaluate)

    probe_parser = sub.add_parser("probe", help="Probe local Ollama Qwen.")
    probe_parser.add_argument("--ollama-model", default="qwen2.5-coder:14b")
    probe_parser.add_argument("--num-ctx", type=int, default=512)
    probe_parser.add_argument(
        "--prompt",
        default="Explain Python context managers in 5 lines with one runnable code example.",
    )
    probe_parser.set_defaults(func=probe)

    ask_parser = sub.add_parser("ask", help="Ask the offline RAG assistant or use tool-calling mode.")
    ask_parser.add_argument("question", nargs="?", default="")
    ask_parser.add_argument("--agents", action="store_true", help="Enable multi-agent execution")
    ask_parser.add_argument("--tools", action="store_true", help="Use tool-calling mode (bash, read, write, edit, glob, grep, web)")
    ask_parser.add_argument("--no-auth", action="store_true", help="Skip authentication check")
    ask_parser.add_argument("--rebuild", action="store_true", help="Force rebuild database")
    ask_parser.add_argument("--stats", action="store_true", help="Show database statistics")
    ask_parser.add_argument("--no-exec", action="store_true", help="Skip code execution verification")
    ask_parser.add_argument("--exec-timeout", type=int, default=0, help="Code execution timeout in seconds")
    ask_parser.add_argument("--query-expansion", action="store_true", help="Enable query expansion")
    ask_parser.add_argument("--mmr", action="store_true", help="Enable MMR diversity re-ranking")
    ask_parser.add_argument("--version", default="", help="Filter by Python version (e.g., 3.10)")
    ask_parser.add_argument("--model", default="",
                            help="Model to use (default: auto). E.g. --model gpt-4o or --model qwen2.5-coder:14b")
    ask_parser.add_argument("--list-models", action="store_true",
                            help="List available Ollama models and exit")
    ask_parser.add_argument("--category", default="", help="Filter by category (e.g., library, howto)")
    ask_parser.set_defaults(func=ask)

    clean_parser = sub.add_parser("clean", help="Dry-run or apply cleanup.")
    clean_parser.add_argument("--apply", action="store_true")
    clean_parser.set_defaults(func=clean)

    data_parser = sub.add_parser("dataset", help="Show dataset profile.")
    data_parser.add_argument("--path", default="data/training/training_dataset.json")
    data_parser.set_defaults(func=dataset_info)

    augment_parser = sub.add_parser("augment", help="Generate extra SFT rows with local Ollama.")
    augment_parser.add_argument("--model", default="qwen2.5-coder:14b")
    augment_parser.add_argument("--limit", type=int, default=3)
    augment_parser.add_argument("--offset", type=int, default=0)
    augment_parser.add_argument("--num-ctx", type=int, default=512)
    augment_parser.add_argument("--num-predict", type=int, default=500)
    augment_parser.add_argument("--pairs-per-chunk", type=int, default=1)
    augment_parser.add_argument("--output", default="data/training/training_dataset_augmented.json")
    augment_parser.add_argument("--merge", action="store_true")
    augment_parser.add_argument("--dry-run", action="store_true")
    augment_parser.set_defaults(func=augment)

    merge_parser = sub.add_parser("merge", help="Merge extra SFT rows into a deduped dataset.")
    merge_parser.add_argument("--base", default="data/training/training_dataset.json")
    merge_parser.add_argument("--add", required=True)
    merge_parser.add_argument("--output", default="data/training/training_dataset_augmented.json")
    merge_parser.set_defaults(func=merge_data)

    webui_parser = sub.add_parser("webui", help="Launch the Streamlit Web UI for the RAG assistant.")
    webui_parser.add_argument("--port", type=int, default=8501, help="Port to run the Web UI on (default: 8501)")
    webui_parser.add_argument("--daemon", action="store_true", help="Run in daemon/background mode (Windows: start new window)")
    webui_parser.set_defaults(func=webui_run)

    apikeys_parser = sub.add_parser("apikeys", help="Manage API keys for dataset generation.")
    apikeys_sub = apikeys_parser.add_subparsers(dest="action", required=True)

    apikeys_list = apikeys_sub.add_parser("list", help="List all providers and their key status.")
    apikeys_list.add_argument("--show-keys", action="store_true", help="Show full keys (not masked)")
    apikeys_list.set_defaults(func=apikeys_cmd)

    apikeys_set = apikeys_sub.add_parser("set", help="Store an API key for a provider.")
    apikeys_set.add_argument("provider", help=f"Provider name. Valid: {list(ALL_PROVIDERS.keys())}")
    apikeys_set.add_argument("key", help="API key value")
    apikeys_set.set_defaults(func=apikeys_cmd)

    apikeys_delete = apikeys_sub.add_parser("delete", help="Delete a stored API key.")
    apikeys_delete.add_argument("provider", help="Provider name to delete key for")
    apikeys_delete.set_defaults(func=apikeys_cmd)

    apikeys_export = apikeys_sub.add_parser("export", help="Export stored keys to a .env file.")
    apikeys_export.add_argument("--path", default="", help="Destination path (default: project-root/.env)")
    apikeys_export.set_defaults(func=apikeys_cmd)

    hf_parser = sub.add_parser("hf-collect", help="Download Python code datasets from HuggingFace.")
    hf_parser.add_argument("--datasets", nargs="*",
                           help="Datasets to download (default: all). Use --list to see options.")
    hf_parser.add_argument("--max-rows", type=int, default=25000,
                           help="Max rows per dataset (default: 25000). Use --max-rows -1 for all rows.")
    hf_parser.add_argument("--output", default="data/raw/raw_chunks_hf.json",
                           help="Output path for combined chunks")
    hf_parser.add_argument("--list", action="store_true",
                           help="List available HuggingFace datasets and exit")
    hf_parser.add_argument("--stats", action="store_true",
                           help="Show statistics about previously collected HF data")
    hf_parser.set_defaults(func=hf_collect)

    conv_parser = sub.add_parser("conv", help="List, search, or export saved conversations.")
    conv_sub = conv_parser.add_subparsers(dest="action", required=True)
    conv_list = conv_sub.add_parser("list", help="List all saved conversations")
    conv_list.set_defaults(func=conv_cmd)
    conv_search = conv_sub.add_parser("search", help="Search saved conversations")
    conv_search.add_argument("query", help="Search query")
    conv_search.set_defaults(func=conv_cmd)
    conv_export = conv_sub.add_parser("export", help="Export a conversation as Markdown with citations")
    conv_export.add_argument("--file", default="", help="Conversation filename (default: most recent)")
    conv_export.add_argument("--output", default="", help="Output markdown path (default: same dir as source)")
    conv_export.set_defaults(func=conv_cmd)

    serve_parser = sub.add_parser("serve", help="Start a lightweight HTTP API server for the RAG assistant.")
    serve_parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    serve_parser.set_defaults(func=serve_cmd)

    export_parser = sub.add_parser("export", help="Export a trained adapter to GGUF or ONNX format.")
    export_parser.add_argument("--adapter-path", default="checkpoints/local_auto_model",
                               help="Path to adapter directory")
    export_parser.add_argument("--format", choices=["gguf", "onnx"], default="gguf",
                               help="Export format (default: gguf)")
    export_parser.set_defaults(func=export_cmd)

    gen_api_parser = sub.add_parser("generate-api", help="Generate dataset from SO + GitHub APIs.")
    gen_api_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    gen_api_parser.add_argument("--limit", type=int, default=0, help="Limit number of chunks to process")
    gen_api_parser.add_argument("--so-only", action="store_true", help="Only mine Stack Overflow")
    gen_api_parser.add_argument("--github-only", action="store_true", help="Only mine GitHub")
    gen_api_parser.add_argument("--no-llm", action="store_true", help="Skip LLM enrichment")
    gen_api_parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    gen_api_parser.set_defaults(func=generate_api)

    graph_parser = sub.add_parser("graph", help="Manage the knowledge graph.")
    graph_sub = graph_parser.add_subparsers(dest="action", required=True)
    graph_build = graph_sub.add_parser("build", help="Build graph from raw chunks")
    graph_build.set_defaults(func=graph_cmd)
    graph_stats = graph_sub.add_parser("stats", help="Show graph stats")
    graph_stats.set_defaults(func=graph_cmd)
    graph_query = graph_sub.add_parser("query", help="Query the graph")
    graph_query.add_argument("query_text", help="Text to query")
    graph_query.add_argument("--hops", type=int, default=2)
    graph_query.add_argument("--max-results", type=int, default=10)
    graph_query.set_defaults(func=graph_cmd)

    tools_parser = sub.add_parser("tools", help="Manage and list MCP tools.")
    tools_sub = tools_parser.add_subparsers(dest="action", required=True)
    tools_list = tools_sub.add_parser("list", help="List registered tools")
    tools_list.add_argument("--verbose", action="store_true", help="Show parameters")
    tools_list.set_defaults(func=tools_cmd)

    dash_parser = sub.add_parser("dashboard", help="Open live OMNISCIENT AI dashboard.")
    dash_parser.set_defaults(func=dashboard_cmd)

    collect_parser = sub.add_parser("collect-data", help="Collect data to D: drive.")
    collect_parser.add_argument("--all", action="store_true", help="Run all collection tasks")
    collect_parser.add_argument("--setup", action="store_true", help="Setup directories only")
    collect_parser.add_argument("--source", choices=["so", "github", "copy", "report"], help="Specific source")
    collect_parser.add_argument("--so-pages", type=int, default=5, help="SO pages (default: 5)")
    collect_parser.add_argument("--github-pages", type=int, default=3, help="GitHub pages (default: 3)")
    collect_parser.set_defaults(func=collect_data_cmd)

    # ── Discovery Engine ────────────────────────────────────────
    discovery_parser = sub.add_parser("discovery", help="Automated dataset discovery engine.")
    discovery_sub = discovery_parser.add_subparsers(dest="action", required=True)

    d_scan = discovery_sub.add_parser("scan", help="Run all discovery scanners and rank results")
    d_scan.add_argument("--hf-limit", type=int, default=50, help="Max HF datasets to scan")
    d_scan.add_argument("--arxiv-limit", type=int, default=20, help="Max arXiv papers")
    d_scan.add_argument("--gov-limit", type=int, default=30, help="Max gov datasets")
    d_scan.add_argument("--github-limit", type=int, default=20, help="Max GitHub repos")
    d_scan.add_argument("--top-n", type=int, default=20, help="Number of top results")
    d_scan.add_argument("--verbose", action="store_true", help="Show progress")
    d_scan.add_argument("--register", action="store_true", help="Auto-register high-priority results")
    d_scan.set_defaults(func=discovery_cmd)

    d_papers = discovery_sub.add_parser("papers", help="Check arXiv for new papers")
    d_papers.add_argument("--categories", nargs="*", default=["cs.AI", "cs.LG", "cs.CL"], help="arXiv categories")
    d_papers.add_argument("--arxiv-limit", type=int, default=20, help="Max results")
    d_papers.set_defaults(func=discovery_cmd)

    d_gov = discovery_sub.add_parser("gov", help="Search government data portals")
    d_gov.add_argument("--keywords", nargs="*", default=["machine learning", "AI", "education", "health", "agriculture"], help="Search keywords")
    d_gov.add_argument("--gov-limit", type=int, default=30, help="Max results")
    d_gov.set_defaults(func=discovery_cmd)

    d_github = discovery_sub.add_parser("github", help="Scan trending GitHub repos")
    d_github.add_argument("--languages", nargs="*", default=["Python", "Jupyter Notebook"], help="Languages to scan")
    d_github.add_argument("--github-limit", type=int, default=20, help="Max repos per language")
    d_github.set_defaults(func=discovery_cmd)

    d_rank = discovery_sub.add_parser("rank", help="Score and rank registered datasets")
    d_rank.add_argument("--top-n", type=int, default=20, help="Number of top results")
    d_rank.set_defaults(func=discovery_cmd)

    # ── Training Management ─────────────────────────────────────
    training_parser = sub.add_parser("training", help="Training configuration and checkpoint management.")
    training_sub = training_parser.add_subparsers(dest="action", required=True)

    t_config = training_sub.add_parser("config", help="Show / generate / save training configs")
    t_config.add_argument("--preset", choices=["default", "smoke", "quick", "qwen", "production", "custom"], default="default", help="Config preset")
    t_config.add_argument("--config-file", default="", help="Path to config file (for --preset custom)")
    t_config.add_argument("--json", action="store_true", help="Output as JSON")
    t_config.add_argument("--save", default="", help="Save config to file path")
    t_config.add_argument("--all", action="store_true", help="Show full config (all fields)")
    t_config.set_defaults(func=training_cmd)

    t_ckpt = training_sub.add_parser("checkpoints", help="List / inspect / clean checkpoints")
    t_ckpt.add_argument("--checkpoint-dir", default="checkpoints", help="Base checkpoint directory")
    t_ckpt.add_argument("--list", dest="checkpoint_list", action="store_true", help="List checkpoints")
    t_ckpt.add_argument("--show", dest="checkpoint_show", default="", help="Show checkpoint details")
    t_ckpt.add_argument("--delete", dest="checkpoint_delete", default="", help="Delete a checkpoint")
    t_ckpt.add_argument("--best", dest="checkpoint_best", action="store_true", help="Show best checkpoint by eval loss")
    t_ckpt.add_argument("--clean", dest="checkpoint_clean", action="store_true", help="Clean old checkpoints")
    t_ckpt.add_argument("--sort-by", choices=["created_at", "step", "eval_loss", "train_loss"], default="created_at", help="Sort field")
    t_ckpt.add_argument("--ascending", action="store_true", help="Sort ascending")
    t_ckpt.add_argument("--limit", type=int, default=20, help="Max results")
    t_ckpt.add_argument("--model-filter", default="", help="Filter by base model name")
    t_ckpt.add_argument("--tag-filter", default="", help="Filter by tag")
    t_ckpt.add_argument("--keep-best", type=int, default=3, help="Keep N best checkpoints")
    t_ckpt.add_argument("--keep-last", type=int, default=5, help="Keep N most recent checkpoints")
    t_ckpt.add_argument("--max-age", type=int, default=90, help="Max age in days")
    t_ckpt.add_argument("--dry-run", action="store_true", help="Dry-run mode for clean")
    t_ckpt.set_defaults(func=training_cmd)

    # ── Phase 1 Data Collection ─────────────────────────────────
    phase1_parser = sub.add_parser("data", help="Phase 1-4 data collection commands.")
    phase1_sub = phase1_parser.add_subparsers(dest="action", required=True)

    p1_init = phase1_sub.add_parser("init", help="Initialize metadata registry with Phase 1 datasets")
    p1_init.set_defaults(func=phase1_cmd)

    p1_status = phase1_sub.add_parser("status", help="Show Phase 1 collection status")
    p1_status.set_defaults(func=phase1_cmd)

    p1_stats = phase1_sub.add_parser("stats", help="Phase 1 estimated statistics (all datasets)")
    p1_stats.set_defaults(func=phase1_cmd)

    p1_list = phase1_sub.add_parser("list", help="List Phase 1 datasets")
    p1_list.add_argument("--week", type=int, choices=[1, 2, 3, 4], help="Filter by week")
    p1_list.add_argument("--status", help="Filter by status (e.g., pending, downloaded, ready)")
    p1_list.add_argument("--domain", help="Filter by domain (e.g., foundation_text, code, instruction)")
    p1_list.set_defaults(func=phase1_cmd)

    p1_dl = phase1_sub.add_parser("download", help="Download Phase 1 datasets")
    p1_dl.add_argument("--week", type=int, choices=[1, 2, 3, 4], help="Week to download (default: all weeks)")
    p1_dl.add_argument("--dataset", help="Single dataset ID to download")
    p1_dl.add_argument("--workers", type=int, default=4, help="Max concurrent downloads")
    p1_dl.set_defaults(func=phase1_cmd)

    p1_qual = phase1_sub.add_parser("quality", help="Run quality checks on downloaded datasets")
    p1_qual.add_argument("datasets", nargs="*", help="Dataset IDs to check (default: all downloaded)")
    p1_qual.add_argument("--input-dir", default="", help="Directory containing dataset JSONL files")
    p1_qual.add_argument("--min-length", type=int, default=50, help="Minimum text length (default: 50)")
    p1_qual.add_argument("--threshold", type=float, default=0.5, help="Quality threshold 0-1 (default: 0.5)")
    p1_qual.set_defaults(func=phase1_cmd)

    phase1_parser.set_defaults(func=phase1_cmd)

    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def main() -> None:
    args = parse_args()

    # Handle --version
    if getattr(args, 'version', False):
        print(f"PythonAI v{VERSION}")
        print(f"Project: {ROOT}")
        print(f"Python: {sys.version.split()[0]}")
        print()
        from src.utils.models import hardware_profile, project_python
        hw = hardware_profile(project_python())
        print(f"CUDA: {hw.get('cuda_available')} ({hw.get('gpu_name')})")
        print(f"RAM: {hw.get('ram_gb')} GB")
        return

    # Handle --completion
    if getattr(args, 'completion', None):
        shell = args.completion
        if shell == "bash":
            print('''_PythonAICompletion()
{
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    COMMANDS="status train login eval probe ask clean dataset augment merge webui apikeys hf-collect conv serve export generate-api graph tools"
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${COMMANDS}" -- ${cur}) )
    fi
    return 0
}
complete -F _PythonAICompletion python -m src.cli
complete -F _PythonAICompletion pythonai''')
        elif shell == "zsh":
            print('''#compdef _pythonai python -m src.cli
_pythonai() {
    local -a commands
    commands=(
        "status:Show project status"
        "train:Run local training"
        "login:Login/Logout/Check auth"
        "eval:Evaluate adapter"
        "probe:Probe Ollama model"
        "ask:Ask RAG assistant"
        "clean:Clean project"
        "dataset:Show dataset profile"
        "augment:Augment dataset"
        "merge:Merge datasets"
        "webui:Launch Web UI"
        "apikeys:Manage API keys"
        "hf-collect:Collect HF datasets"
        "conv:Manage conversations"
        "serve:HTTP API server"
        "export:Export adapter"
    )
    _describe -t commands "PythonAI commands" commands
}
_pythonai "$@"''')
        elif shell == "fish":
            print('''complete -c python -m src.cli -f -a "status train login eval probe ask clean dataset augment merge webui apikeys hf-collect conv serve export"''')
        return

    if not hasattr(args, 'func'):
        parser = build_parser()
        parser.print_help()
        return

    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
