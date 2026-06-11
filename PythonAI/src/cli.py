from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from src.auth import check_auth, interactive_login, logout
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
    watch = getattr(args, "watch", False)
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
    if getattr(args, "json_output", False):
        info = {
            "python": str(python_exe),
            "project_files": audit["total_files"],
            "project_mb": audit["total_mb"],
            "cleanup_targets": cleanup["candidate_count"],
            "cleanup_mb": cleanup["recoverable_mb"],
            "dataset_rows": dataset["rows"],
            "dataset_avg_chars": dataset["length_avg"],
            "cuda": hardware.get("cuda_available"),
            "gpu": hardware.get("gpu_name"),
            "ram_gb": hardware.get("ram_gb"),
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

    if getattr(args, "verbose", False):
        print("  Largest files:")
        for f in audit.get("largest_files", [])[:5]:
            print(f"    {f['path']}: {f['bytes'] / 1024:.1f} KB")
        print("  By extension:")
        for ext, info in list(audit.get("by_extension", {}).items())[:8]:
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
    cmd = [
        str(project_python()),
        "-m",
        "src.training.run",
        "--mode",
        args.mode,
        "--max-steps",
        str(args.max_steps),
        "--max-examples",
        str(args.max_examples),
        "--max-length",
        str(args.max_length),
        "--output-dir",
        args.output_dir,
        "--dataset-path",
        args.dataset_path,
    ]
    if getattr(args, "unsloth", False):
        cmd.append("--unsloth")
    if args.skip_train:
        cmd.append("--skip-train")
    return run(cmd)


@requires_auth
def evaluate(args: argparse.Namespace) -> int:
    return run(
        [
            str(project_python()),
            "-m",
            "src.training.evaluator",
            "--adapter-path",
            args.adapter_path,
            "--output-json",
            args.output_json,
        ]
    )


def probe(args: argparse.Namespace) -> int:
    return run(
        [
            str(project_python()),
            "-m",
            "src.rag.prober",
            "--ollama-model",
            args.ollama_model,
            "--num-ctx",
            str(args.num_ctx),
            "--prompt",
            args.prompt,
        ]
    )


@requires_auth
def ask(args: argparse.Namespace) -> int:
    if args.agents:
        # Route through the swarm orchestrator
        from src.agents import ALL_AGENTS
        from src.utils.swarm import AgentSwarm, execute_agents

        print("\n[AgentSwarm] Routing question through specialist agents...")
        swarm = AgentSwarm()
        results = execute_agents(args.question, swarm, ALL_AGENTS)

        print("\n[AI] SWARM RESULTS:")
        print(f"{'=' * 55}")
        for agent_name, output in results.items():
            print(f"[{agent_name.upper()}]:\n{output}\n")
        print(f"{'=' * 55}")
        return 0

    # == Phase 6: Agentic Orchestration mode (--orchestrate) ===
    if getattr(args, "orchestrate", False):
        from src.core.agents import AgentOrchestrator
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        registry = get_registry()
        try:
            register_all_tools(registry)
        except Exception:
            pass

        print(f"  Provider: {args.model or 'auto'}")
        print()

        orchestrator = AgentOrchestrator(
            registry=registry,
            on_stream=lambda text: print(text, end="", flush=True),
            verbose=True,
        )

        if args.question:
            orchestrator.run(args.question)
            print(f"\n{'=' * 55}")
            print(orchestrator.summary())
            print(f"{'=' * 55}\n")
        else:
            # Interactive mode
            print("Entering agentic orchestration mode. Type 'exit' to quit.\n")
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
                orchestrator.run(q)
                print(orchestrator.summary())
        return 0

    # == Tool-calling mode (--tools) ===========================
    if getattr(args, "tools", False):
        from src.core.executor import ToolCallingEngine
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        # Register tools on first use
        registry = get_registry()
        try:
            register_all_tools(registry)
        except Exception:
            pass  # Tools already registered

        print("\n[Tools] Tool-Calling Mode (engine ready)")
        print(f"{'=' * 55}")
        print(f"  Provider  : {args.model or 'auto'}")
        print(f"  Tools     : {registry.total_count} registered")
        print(f"{'=' * 55}\n")

        engine = ToolCallingEngine(
            provider="auto",
            model=args.model or "",
            registry=registry,
            on_stream=lambda text: print(text, end="", flush=True),
        )

        if args.question:
            engine.run(args.question)
            print(f"\n{'=' * 55}")
            print(f"[Stats] {engine.get_stats_report()}")
            print(f"{'=' * 55}\n")
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

                engine.run(q)
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
    print("\n[Tools] Registered Tools")
    print(f"{'=' * 55}")

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
        "-m",
        "src.data.augmenter",
        "--model",
        args.model,
        "--limit",
        str(args.limit),
        "--offset",
        str(args.offset),
        "--num-ctx",
        str(args.num_ctx),
        "--num-predict",
        str(args.num_predict),
        "--pairs-per-chunk",
        str(args.pairs_per_chunk),
        "--output",
        args.output,
    ]
    if args.merge:
        command.append("--merge")
    if args.dry_run:
        command.append("--dry-run")
    return run(command)


def merge_data(args: argparse.Namespace) -> int:
    return run(
        [
            str(project_python()),
            "-m",
            "src.data.merger",
            "--base",
            args.base,
            "--add",
            args.add,
            "--output",
            args.output,
        ]
    )


def generate_api(args: argparse.Namespace) -> int:
    cmd = [
        str(project_python()),
        "-m",
        "src.data.api_dataset_gen",
        "--workers",
        str(args.workers),
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
        "-m",
        "src.rag.knowledge_graph",
        args.action,
    ]
    if args.query_text:
        cmd.append(args.query_text)
    if args.hops != 2:
        cmd.extend(["--hops", str(args.hops)])
    if args.max_results != 10:
        cmd.extend(["--max-results", str(args.max_results)])
    return run(cmd)


def cast_cmd(args: argparse.Namespace) -> int:
    """
    cAST: AST-aware code chunking for RAG (EMNLP 2025).

    Chunks source code files into semantically complete units
    (functions, classes, import blocks) by parsing the AST,
    rather than splitting by arbitrary line counts.
    """

    path = Path(args.path)
    if not path.exists():
        print(f"[Error] Path not found: {path}")
        return 1

    if args.mode == "index":
        # Index mode: chunk + embed into ChromaDB
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            from src.rag.cast_chunker import CastChunker
            from src.rag.rag_engine import DB_PATH

            print(f"[cAST] Indexing {path} into code-aware RAG database...")
            chunker = CastChunker(language=args.language)

            if path.is_file():
                raw_chunks = chunker.chunk_file(path)
            elif path.is_dir():
                raw_chunks = chunker.chunk_directory(path)
            else:
                print(f"[Error] Unknown path type: {path}")
                return 1

            if not raw_chunks:
                print("[cAST] No code chunks produced.")
                return 0

            print(f"[cAST] {len(raw_chunks)} semantic chunks produced")

            # Embed and index into ChromaDB
            embedder = SentenceTransformer("all-MiniLM-L6-v2")
            client = chromadb.PersistentClient(path=str(DB_PATH))

            try:
                collection = client.get_collection("python_godmode")
            except Exception:
                collection = client.create_collection(
                    name="python_godmode",
                    metadata={"hnsw:space": "cosine"},
                )

            batch_size = 50
            added = 0
            for i in range(0, len(raw_chunks), batch_size):
                batch = raw_chunks[i : i + batch_size]
                texts = [c.to_embedding_text() for c in batch]
                ids = [f"cAST_{abs(hash(c.content)) % 10**12}" for c in batch]
                metadatas = [
                    {
                        "title": c.name or c.chunk_type,
                        "type": c.chunk_type,
                        "language": c.language,
                        "filepath": str(c.filepath)[:200],
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "source": "cAST_chunker",
                        "category": f"code_{c.chunk_type}",
                    }
                    for c in batch
                ]
                embs = embedder.encode(texts, batch_size=16, show_progress_bar=False).tolist()
                collection.add(documents=texts, embeddings=embs, ids=ids, metadatas=metadatas)
                added += len(batch)

            total = collection.count()
            print(f"[cAST] Indexed {added} chunks into RAG DB ({total:,} total)")

            if args.stats:
                print(f"\n{'=' * 50}")
                print("cAST Indexing Statistics")
                print(f"{'=' * 50}")
                print(f"Path          : {path}")
                print(f"Language      : {args.language}")
                print(f"Chunks        : {len(raw_chunks)}")
                types = {}
                for c in raw_chunks:
                    t = c.chunk_type
                    types[t] = types.get(t, 0) + 1
                for t, count in sorted(types.items(), key=lambda x: -x[1]):
                    print(f"  {t}: {count}")
                avg_len = sum(len(c.content) for c in raw_chunks) / len(raw_chunks) if raw_chunks else 0
                print(f"Avg chunk len : {avg_len:.0f} chars")
                print(f"{'=' * 50}\n")

        except ImportError as e:
            print(f"[Error] Missing dependency: {e}")
            print("  Install: pip install sentence-transformers chromadb")
            return 1

        return 0

    # Default mode: chunk only (CLI output)
    return run(
        [
            str(project_python()),
            "-m",
            "src.rag.cast_chunker",
            str(path),
            "--language",
            args.language,
        ]
        + (["--output", args.output] if args.output else [])
        + (["--stats"] if args.stats else [])
    )


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
            "-m",
            "streamlit",
            "run",
            str(ROOT / "src" / "webui" / "app.py"),
            "--server.port",
            str(args.port),
            "--browser.gatherUsageStats",
            "false",
        ]
        sp.Popen(cmd, creationflags=creationflags, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        print(f"[Daemon] Web UI started at http://localhost:{args.port}")
        return 0

    return run(
        [
            str(project_python()),
            "-m",
            "streamlit",
            "run",
            str(ROOT / "src" / "webui" / "app.py"),
            "--server.port",
            str(args.port),
            "--browser.gatherUsageStats",
            "false",
        ]
    )


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
            ts = c["timestamp"]
            ts_display = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}" if len(ts) >= 14 else ts
            print(f"  {c['file']}")
            print(f"      {ts_display}  |  {c['messages']} msgs  |  {c['size_kb']} KB")
            print(f'      "{c["summary"][:70] or "(empty)"}"')
            print()
        return 0

    if args.action == "search" and args.query:
        results = search_conversations(args.query, max_results=10)
        if not results:
            print(f'[No results] No conversations matched "{args.query}"')
            return 0
        print(f'[Search] "{args.query}" — {len(results)} conversation(s) matched')
        print("=" * 60)
        for r in results:
            print(f"  [{r['timestamp']}] {r['file']}")
            print(f"      Matches: {r['matches']} | Summary: {r['summary'][:60] or '(empty)'}")
            for s in r["snippets"][:2]:
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
    from src.data.hf_collector import HF_DATASETS, print_stats
    from src.data.hf_collector import run as hf_run

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
        print(
            "[WARN] No chunks were collected. Check your internet connection or try --list to see available datasets."
        )
        return 1
    print(f"Done. {total:,} chunks collected.")
    return 0


def serve_cmd(args: argparse.Namespace) -> int:
    """Start the PythonAI FastAPI server via uvicorn."""
    port = args.port
    host = args.host

    print(f"[Serve] Starting PythonAI FastAPI server on {host}:{port}...\n")
    print("  Endpoints:")
    print("    POST /ask          Ask a Python question")
    print("    POST /chat         Chat with history")
    print("    GET  /health       Health check")
    print("    GET  /stats        Database statistics")
    print("    GET  /docs         Interactive API docs (Swagger UI)\n")

    try:
        import uvicorn
    except ImportError:
        print("[FAIL] uvicorn is not installed. Run: pip install uvicorn")
        return 1

    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        log_level="info",
    )
    return 0


def dashboard_cmd(args: argparse.Namespace) -> int:
    """Open the live OMNISCIENT AI dashboard."""
    import subprocess as sp

    dashboard_path = ROOT / "dashboard.html"
    if not dashboard_path.exists():
        print(f"[Error] Dashboard not found at: {dashboard_path}")
        return 1
    print("[Dashboard] Opening live visualization...")
    sp.Popen(["cmd", "/c", "start", str(dashboard_path)], shell=True)
    return 0


def forge_cmd(args: argparse.Namespace) -> int:
    """
    ForgeAI: Acceptance rate tracking & dashboard (MIT SEAL architecture).

    Generates interactive HTML dashboards from CaptureEngine signal data,
    showing acceptance rate curves, signal breakdown, and training history.
    """
    import json

    from src.learning.capture_engine import CaptureEngine
    from src.learning.forge_dashboard import generate_dashboard

    if args.action == "dashboard":
        generate_dashboard(
            output_path=args.output,
            weeks=args.weeks,
            demo=args.demo,
        )
        if args.open:
            import webbrowser

            path = Path(args.output).resolve()
            webbrowser.open(f"file:///{path}")
            print(f"[ForgeAI] Opened dashboard: {path}")
        return 0

    elif args.action == "stats":
        engine = CaptureEngine()
        stats = engine.get_statistics()
        print(json.dumps(stats, indent=2, default=str))

        # Also show daily rate for last 7 days
        rates = engine.get_acceptance_rate(days=7)
        if rates:
            print("\nLast 7 days acceptance rate:")
            print(f"  {'Date':14s} {'Rate':8s} {'Accept':8s} {'Reject':8s} {'Edit':8s}")
            print(f"  {'-' * 14} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8}")
            for r in rates:
                print(
                    f"  {r['date']:14s} {r['acceptance_rate']:6.1f}%  {r['accepts']:5d}   {r['rejects']:5d}   {r['edits']:5d}"
                )
        else:
            print("\n  No recent data. Use CaptureEngine to start collecting signals.")
        return 0

    return 1


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


def grpo_cmd(args: argparse.Namespace) -> int:
    """
    GRPO: Group Relative Policy Optimization training (DeepSeek-R1 2025).

    Trains a policy model using accept/reject pairs with PPO-style clipped
    surrogate objectives and group-relative advantages. No reward model needed.
    """
    if args.action == "train":
        import json

        from src.training.grpo_trainer import GRPOPair, GRPOTrainer

        # Load pairs
        pairs_path = Path(args.data)
        if not pairs_path.exists():
            print(f"[Error] GRPO pairs file not found: {pairs_path}")
            return 1

        pairs = []
        with open(pairs_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        pairs.append(GRPOPair.from_dict(data))
                    except json.JSONDecodeError:
                        pass

        print(f"Loaded {len(pairs)} GRPO pairs from {pairs_path}")

        if not pairs:
            print("[Error] No valid GRPO pairs found.")
            return 1

        trainer = GRPOTrainer(
            model_name=args.model,
            lora_rank=args.lora_rank,
            learning_rate=args.lr,
            kl_coef=args.kl_coef,
            epsilon=args.epsilon,
        )

        metrics = trainer.train(
            pairs=pairs,
            output_dir=args.output,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
        )
        print(json.dumps(metrics, indent=2))
        return 0

    elif args.action == "export-pairs":
        """Export GRPO pairs from CaptureEngine DB."""
        import json

        from src.learning.capture_engine import CaptureEngine, SignalType
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        db_path = Path(args.db).expanduser()
        if not db_path.exists():
            print(f"[Error] CaptureEngine DB not found: {db_path}")
            return 1

        engine = CaptureEngine(db_path=db_path)

        accepts = engine.get_signals(signal_type=SignalType.ACCEPT, limit=args.max_pairs)
        rejects = engine.get_signals(signal_type=SignalType.REJECT, limit=args.max_pairs)
        edits = engine.get_signals(signal_type=SignalType.EDIT, limit=args.max_pairs)

        pairs = create_grpo_pairs_from_signals(
            accept_signals=[s.to_dict() for s in accepts],
            reject_signals=[s.to_dict() for s in rejects],
            edit_signals=[s.to_dict() for s in edits],
        )

        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair.to_dict()) + "\n")

        print(f"Exported {len(pairs)} GRPO pairs to {output_path}")
        print(f"  Source: {len(accepts)} accepts, {len(rejects)} rejects, {len(edits)} edits")
        return 0

    elif args.action == "stats":
        """Show training runs with acceptance rate deltas."""
        import json
        from datetime import datetime

        from src.learning.capture_engine import CaptureEngine

        db_path = Path(args.db).expanduser()
        if not db_path.exists():
            print(f"[Error] CaptureEngine DB not found: {db_path}")
            print("  Tip: Run 'python -m src.cli train --capture-db <path>' to start recording training runs.")
            return 1

        engine = CaptureEngine(db_path=db_path)
        runs = engine.get_training_runs(limit=args.limit)

        if not runs:
            print(f"[Empty] No training runs found in {db_path}")
            print("  Run 'python -m src.cli train --capture-db <path>' after some signal data is collected.")
            return 0

        if getattr(args, "json", False):
            print(json.dumps(runs, indent=2, default=str))
            return 0

        # Table header
        print("\n[GRPO] Recent Training Runs")
        print(f"{'=' * 80}")
        print(
            f"  {'Run ID':12s} {'Date':14s} {'Model':20s} {'Signals':>8s} {'Loss':>8s} {'Rate Before':>12s} {'Rate After':>11s} {'Change':>6s}"
        )
        print(f"  {'-' * 12} {'-' * 14} {'-' * 20} {'-' * 8} {'-' * 8} {'-' * 12} {'-' * 11} {'-' * 6}")

        for r in runs:
            ts = datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M")
            model = r["model_name"][:18] + ".." if len(r["model_name"]) > 20 else r["model_name"]
            loss = f"{r['train_loss']:.4f}" if r["train_loss"] else "-"
            rate_before = f"{r['acceptance_rate_before']:.1%}"
            rate_after = f"{r['acceptance_rate_after']:.1%}"
            delta = r["acceptance_delta"]
            delta_str = f"{delta:+.1%}"
            # Color-like indicator: green for positive, red for negative
            delta_indicator = "[+]" if delta > 0 else ("[-]" if delta < 0 else "[=]")

            print(
                f"  {r['run_id'][:10]:12s} {ts:14s} {model:20s} {r['signals_used']:8d} {loss:>8s} {rate_before:>12s} {rate_after:>11s} {delta_indicator} {delta_str:>4s}"
            )

        # Summary
        total_runs = len(runs)
        positive_deltas = sum(1 for r in runs if r["acceptance_delta"] > 0)
        negative_deltas = sum(1 for r in runs if r["acceptance_delta"] < 0)
        print(f"\n  Summary: {total_runs} runs | {positive_deltas} improved [+] | {negative_deltas} regressed [-]")
        print()
        return 0

    elif args.action == "create-pairs":
        """Create GRPO pairs directly from manual inputs (for testing)."""
        import json

        from src.training.grpo_trainer import GRPOPair, create_grpo_pairs_from_signals

        # Read accept, reject, edit JSONL files
        accept_signals = []
        reject_signals = []
        edit_signals = []

        if args.accepts:
            acc_path = Path(args.accepts)
            if acc_path.exists():
                with open(acc_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            accept_signals.append(json.loads(line))

        if args.rejects:
            rej_path = Path(args.rejects)
            if rej_path.exists():
                with open(rej_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            reject_signals.append(json.loads(line))

        if args.edits:
            edit_path = Path(args.edits)
            if edit_path.exists():
                with open(edit_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            edit_signals.append(json.loads(line))

        pairs = create_grpo_pairs_from_signals(
            accept_signals=accept_signals,
            reject_signals=reject_signals,
            edit_signals=edit_signals,
        )

        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair.to_dict()) + "\n")

        print(
            f"Created {len(pairs)} GRPO pairs from {len(accept_signals)} accepts, {len(reject_signals)} rejects, {len(edit_signals)} edits"
        )
        print(f"Output: {output_path}")
        return 0

    return 1


# ============================================
# Discovery Engine Commands
# ============================================


def discovery_cmd(args: argparse.Namespace) -> int:
    """Discovery Engine — automated dataset discovery."""
    from src.data.discovery import (
        PriorityRanker,
        auto_discover,
        check_for_new_papers,
        discover_github_repos,
        discover_government_data,
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
        print_ranking(scored[: args.top_n])

        # Summary
        tiers = {}
        for s in scored:
            tiers[s.priority] = tiers.get(s.priority, 0) + 1
        print("\nSummary by priority tier:")
        for tier in ("critical", "high", "medium", "low"):
            if tier in tiers:
                print(f"  {tier:10s}: {tiers[tier]}")
        return 0

    return 1


# ============================================
# Training Commands
# ============================================


def training_cmd(args: argparse.Namespace) -> int:
    """Enhanced training pipeline management."""
    from src.training.checkpoint_manager import CheckpointManager, format_meta
    from src.training.config import (
        TrainingConfig,
        production_config,
        quick_config,
        qwen_config,
        smoke_config,
    )

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

            print("\nFull config (JSON):")
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


# ============================================
# Phase 1 Data Collection Commands
# ============================================


def phase1_cmd(args: argparse.Namespace) -> int:
    """Phase 1 data collection commands."""
    from src.data.downloader import BASE_DATA_DIR, DownloadOrchestrator
    from src.data.metadata import MetadataManager
    from src.data.phase1 import generate_phase1_datasets, phase1_stats
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
        print("[Phase1] Collection Status")
        print(f"  Total datasets : {stats['total_datasets']}")
        print("  By status:")
        for status, count in sorted(stats["by_status"].items()):
            print(f"    {status:20s}: {count}")
        print("  By phase:")
        for phase, count in sorted(stats["by_phase"].items()):
            pp = pipeline["phases"].get(f"phase_{phase}", {})
            ready = pp.get("ready", 0)
            pct = pp.get("progress_pct", 0)
            print(f"    Phase {phase}: {count} datasets ({ready} ready, {pct}%)")
        print(f"  Ready records  : {stats['ready_records']:,}")
        print(f"  Ready size     : {stats['ready_gb']} GB")
        if stats.get("errors"):
            print(f"  Errors ({len(stats['errors'])}):")
            for err in stats["errors"][:5]:
                print(f"    - {err['id']}: {err['error'][:100]}")
        print()
        # Week-by-week breakdown
        for w in range(1, 5):
            wp = mgr.week_progress(1, w)
            if wp["total"] > 0:
                print(f"  Week {w}: {wp['done']}/{wp['total']} done ({wp['progress_pct']}%)")
        return 0

    if args.action == "stats":
        stats = phase1_stats()
        print("Phase 1 — Foundation Data Collection")
        print(f"  Total datasets    : {stats['total_datasets']}")
        print(f"  Estimated records : {stats['estimated_total_records']:,}")
        print(f"  Estimated size    : {stats['estimated_total_gb']} GB")
        print()
        print("  By Week:")
        for w, c in sorted(stats["by_week"].items()):
            print(f"    Week {w}: {c} datasets")
        print()
        print("  By Domain:")
        for d, c in sorted(stats["by_domain"].items()):
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
        print(f"{'=' * 40} {'=' * 16} {'=' * 8} {'=' * 12} {'=' * 8}")
        for r in records:
            lang_str = ",".join(r.languages)[:8]
            rec_str = f"{r.actual_record_count:,}" if r.actual_record_count > 0 else "-"
            gb_str = f"{r.size_mb / 1024:.1f}" if r.actual_size_bytes > 0 else "-"
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
            for stage_name, stage_data in stats.get("stages", {}).items():
                if isinstance(stage_data, dict):
                    removed = stage_data.get("removed", 0)
                    if removed:
                        print(f"    {stage_name}: removed {removed}")
            print(f"  Elapsed: {stats.get('elapsed_seconds', '?')}s")
        return 0

    return 1


def learn_cmd(args: argparse.Namespace) -> int:
    """Learning Engine CLI hooks."""
    from src.utils.models import project_python

    if args.action == "daemon":
        return run([str(project_python()), "-m", "src.learning.daemon", "--interval", str(args.interval)])

    if args.action == "sync-so":
        return run(
            [
                str(project_python()),
                "-c",
                "from src.learning.so_sync import sync_stackoverflow; print(sync_stackoverflow(pages=1))",
            ]
        )

    if args.action == "eval":
        return run(
            [
                str(project_python()),
                "-c",
                "from src.learning.self_eval import run_self_evaluation; print(run_self_evaluation(sample_size=10))",
            ]
        )

    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (exported for testing)."""
    parser = argparse.ArgumentParser(
        description="One-command entrypoint for the PythonAI project.",
        epilog="Run 'python -m src.cli <command> --help' for command-specific help.",
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument(
        "--completion", choices=["bash", "zsh", "fish"], default=None, help="Print shell tab-completion script and exit"
    )
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
    train_parser.add_argument(
        "--unsloth", action="store_true", help="Use Unsloth for 2x faster QLoRA training (70%% less VRAM)"
    )
    train_parser.add_argument("--skip-train", action="store_true")
    train_parser.add_argument("--no-auth", action="store_true", help="Skip authentication check")
    train_parser.add_argument(
        "--viz",
        action="store_true",
        help="Save comprehensive training visualization (dashboard, LR, throughput, HTML, JSON)",
    )
    train_parser.set_defaults(func=train)

    login_parser = sub.add_parser("login", help="Login, logout, or check auth status.")
    login_parser.add_argument(
        "action",
        nargs="?",
        choices=["login", "logout", "check"],
        default="login",
        help="Action to perform (default: login)",
    )
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
    ask_parser.add_argument("--agents", action="store_true", help="Enable multi-agent execution (legacy swarm)")
    ask_parser.add_argument(
        "--orchestrate", action="store_true", help="Enable Phase 6 agentic orchestration (plan, delegate, synthesize)"
    )
    ask_parser.add_argument(
        "--tools", action="store_true", help="Use tool-calling mode (bash, read, write, edit, glob, grep, web)"
    )
    ask_parser.add_argument("--no-auth", action="store_true", help="Skip authentication check")
    ask_parser.add_argument("--rebuild", action="store_true", help="Force rebuild database")
    ask_parser.add_argument("--stats", action="store_true", help="Show database statistics")
    ask_parser.add_argument("--no-exec", action="store_true", help="Skip code execution verification")
    ask_parser.add_argument("--exec-timeout", type=int, default=0, help="Code execution timeout in seconds")
    ask_parser.add_argument("--query-expansion", action="store_true", help="Enable query expansion")
    ask_parser.add_argument("--mmr", action="store_true", help="Enable MMR diversity re-ranking")
    ask_parser.add_argument("--version", default="", help="Filter by Python version (e.g., 3.10)")
    ask_parser.add_argument(
        "--model", default="", help="Model to use (default: auto). E.g. --model gpt-4o or --model qwen2.5-coder:14b"
    )
    ask_parser.add_argument("--list-models", action="store_true", help="List available Ollama models and exit")
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
    webui_parser.add_argument(
        "--daemon", action="store_true", help="Run in daemon/background mode (Windows: start new window)"
    )
    webui_parser.set_defaults(func=webui_run)

    learn_parser = sub.add_parser("learn", help="Run learning module tasks (daemon, sync-so, eval).")
    learn_sub = learn_parser.add_subparsers(dest="action", required=True)

    learn_daemon = learn_sub.add_parser("daemon", help="Run autonomous learning daemon in foreground.")
    learn_daemon.add_argument("--interval", type=int, default=24, help="Run interval in hours")

    learn_sub.add_parser("sync-so", help="Sync trending StackOverflow Q&A manually.")
    learn_sub.add_parser("eval", help="Run self-evaluation on RAG answers.")
    learn_parser.set_defaults(func=learn_cmd)

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
    hf_parser.add_argument(
        "--datasets", nargs="*", help="Datasets to download (default: all). Use --list to see options."
    )
    hf_parser.add_argument(
        "--max-rows",
        type=int,
        default=25000,
        help="Max rows per dataset (default: 25000). Use --max-rows -1 for all rows.",
    )
    hf_parser.add_argument("--output", default="data/raw/raw_chunks_hf.json", help="Output path for combined chunks")
    hf_parser.add_argument("--list", action="store_true", help="List available HuggingFace datasets and exit")
    hf_parser.add_argument("--stats", action="store_true", help="Show statistics about previously collected HF data")
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
    export_parser.add_argument(
        "--adapter-path", default="checkpoints/local_auto_model", help="Path to adapter directory"
    )
    export_parser.add_argument(
        "--format", choices=["gguf", "onnx"], default="gguf", help="Export format (default: gguf)"
    )
    export_parser.set_defaults(func=export_cmd)

    gen_api_parser = sub.add_parser("generate-api", help="Generate dataset from SO + GitHub APIs.")
    gen_api_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    gen_api_parser.add_argument("--limit", type=int, default=0, help="Limit number of chunks to process")
    gen_api_parser.add_argument("--so-only", action="store_true", help="Only mine Stack Overflow")
    gen_api_parser.add_argument("--github-only", action="store_true", help="Only mine GitHub")
    gen_api_parser.add_argument("--no-llm", action="store_true", help="Skip LLM enrichment")
    gen_api_parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    gen_api_parser.set_defaults(func=generate_api)

    # == cAST Chunking =========================================
    cast_parser = sub.add_parser("cast", help="cAST: AST-aware code chunking for RAG (EMNLP 2025).")
    cast_parser.add_argument("path", help="File or directory to chunk")
    cast_parser.add_argument("--output", "-o", default="", help="Output JSON file (default: stdout)")
    cast_parser.add_argument("--language", "-l", default="python", help="Language (default: python)")
    cast_parser.add_argument("--stats", action="store_true", help="Print chunking statistics")
    cast_parser.add_argument(
        "--mode",
        choices=["chunk", "index"],
        default="chunk",
        help="'chunk' = just chunk code, 'index' = chunk + index into ChromaDB",
    )
    cast_parser.set_defaults(func=cast_cmd)

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

    # == GRPO Commands ==========================================
    grpo_parser = sub.add_parser("grpo", help="GRPO: Group Relative Policy Optimization (DeepSeek-R1 2025).")
    grpo_sub = grpo_parser.add_subparsers(dest="action", required=True)

    grpo_train = grpo_sub.add_parser("train", help="Run GRPO training from accept/reject pairs")
    grpo_train.add_argument("--model", required=True, help="Base model or SFT-trained model path")
    grpo_train.add_argument("--data", required=True, help="GRPO pairs file (JSONL)")
    grpo_train.add_argument("--output", default="checkpoints/grpo", help="Output directory")
    grpo_train.add_argument("--epochs", type=int, default=1)
    grpo_train.add_argument("--batch-size", type=int, default=4)
    grpo_train.add_argument("--lr", type=float, default=1e-5)
    grpo_train.add_argument("--kl-coef", type=float, default=0.04, help="KL penalty coefficient")
    grpo_train.add_argument("--epsilon", type=float, default=0.2, help="PPO clipping range")
    grpo_train.add_argument("--lora-rank", type=int, default=16)
    grpo_train.set_defaults(func=grpo_cmd)

    grpo_export = grpo_sub.add_parser("export-pairs", help="Export GRPO pairs from CaptureEngine DB")
    grpo_export.add_argument("--db", default="~/.forgeai/signals.db", help="CaptureEngine DB path")
    grpo_export.add_argument("--output", "-o", default="grpo_pairs.jsonl", help="Output JSONL file")
    grpo_export.add_argument("--max-pairs", type=int, default=10000, help="Max pairs to export")
    grpo_export.set_defaults(func=grpo_cmd)

    grpo_create = grpo_sub.add_parser("create-pairs", help="Create GRPO pairs from accept/reject/edit signal files")
    grpo_create.add_argument("--accepts", help="JSONL file of accept signals")
    grpo_create.add_argument("--rejects", help="JSONL file of reject signals")
    grpo_create.add_argument("--edits", help="JSONL file of edit signals")
    grpo_create.add_argument("--output", "-o", default="grpo_pairs.jsonl", help="Output JSONL file")
    grpo_create.set_defaults(func=grpo_cmd)

    grpo_stats = grpo_sub.add_parser(
        "stats", help="Show training runs with acceptance rate deltas from CaptureEngine DB"
    )
    grpo_stats.add_argument("--db", default="~/.forgeai/signals.db", help="CaptureEngine DB path")
    grpo_stats.add_argument("--limit", "-n", type=int, default=10, help="Number of recent runs to show")
    grpo_stats.add_argument("--json", action="store_true", help="Output as JSON")
    grpo_stats.set_defaults(func=grpo_cmd)

    # == ForgeAI Commands ========================================
    forge_parser = sub.add_parser("forge", help="ForgeAI: Acceptance rate tracking & dashboard.")
    forge_sub = forge_parser.add_subparsers(dest="action", required=True)

    f_dash = forge_sub.add_parser("dashboard", help="Generate acceptance rate dashboard HTML")
    f_dash.add_argument("--output", "-o", default="forge_dashboard.html", help="Output HTML file")
    f_dash.add_argument("--weeks", "-w", type=int, default=12, help="Weeks of data to show")
    f_dash.add_argument("--demo", action="store_true", help="Use synthetic demo data")
    f_dash.add_argument("--open", action="store_true", help="Open in browser after generating")
    f_dash.set_defaults(func=forge_cmd)

    f_stats = forge_sub.add_parser("stats", help="Show capture statistics")
    f_stats.set_defaults(func=forge_cmd)

    dash_parser = sub.add_parser("dashboard", help="Open live OMNISCIENT AI dashboard.")
    dash_parser.set_defaults(func=dashboard_cmd)

    collect_parser = sub.add_parser("collect-data", help="Collect data to D: drive.")
    collect_parser.add_argument("--all", action="store_true", help="Run all collection tasks")
    collect_parser.add_argument("--setup", action="store_true", help="Setup directories only")
    collect_parser.add_argument("--source", choices=["so", "github", "copy", "report"], help="Specific source")
    collect_parser.add_argument("--so-pages", type=int, default=5, help="SO pages (default: 5)")
    collect_parser.add_argument("--github-pages", type=int, default=3, help="GitHub pages (default: 3)")
    collect_parser.set_defaults(func=collect_data_cmd)

    # == Discovery Engine ========================================
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
    d_gov.add_argument(
        "--keywords",
        nargs="*",
        default=["machine learning", "AI", "education", "health", "agriculture"],
        help="Search keywords",
    )
    d_gov.add_argument("--gov-limit", type=int, default=30, help="Max results")
    d_gov.set_defaults(func=discovery_cmd)

    d_github = discovery_sub.add_parser("github", help="Scan trending GitHub repos")
    d_github.add_argument("--languages", nargs="*", default=["Python", "Jupyter Notebook"], help="Languages to scan")
    d_github.add_argument("--github-limit", type=int, default=20, help="Max repos per language")
    d_github.set_defaults(func=discovery_cmd)

    d_rank = discovery_sub.add_parser("rank", help="Score and rank registered datasets")
    d_rank.add_argument("--top-n", type=int, default=20, help="Number of top results")
    d_rank.set_defaults(func=discovery_cmd)

    # == Training Management =====================================
    training_parser = sub.add_parser("training", help="Training configuration and checkpoint management.")
    training_sub = training_parser.add_subparsers(dest="action", required=True)

    t_config = training_sub.add_parser("config", help="Show / generate / save training configs")
    t_config.add_argument(
        "--preset",
        choices=["default", "smoke", "quick", "qwen", "production", "custom"],
        default="default",
        help="Config preset",
    )
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
    t_ckpt.add_argument(
        "--sort-by", choices=["created_at", "step", "eval_loss", "train_loss"], default="created_at", help="Sort field"
    )
    t_ckpt.add_argument("--ascending", action="store_true", help="Sort ascending")
    t_ckpt.add_argument("--limit", type=int, default=20, help="Max results")
    t_ckpt.add_argument("--model-filter", default="", help="Filter by base model name")
    t_ckpt.add_argument("--tag-filter", default="", help="Filter by tag")
    t_ckpt.add_argument("--keep-best", type=int, default=3, help="Keep N best checkpoints")
    t_ckpt.add_argument("--keep-last", type=int, default=5, help="Keep N most recent checkpoints")
    t_ckpt.add_argument("--max-age", type=int, default=90, help="Max age in days")
    t_ckpt.add_argument("--dry-run", action="store_true", help="Dry-run mode for clean")
    t_ckpt.set_defaults(func=training_cmd)

    # == Phase 1 Data Collection =================================
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

    # == Provider Commands (Phase 2) =============================
    provider_parser = sub.add_parser("provider", help="Manage provider selection and routing.")
    provider_sub = provider_parser.add_subparsers(dest="action", required=True)

    p_list = provider_sub.add_parser("list", help="List all available providers")
    p_list.set_defaults(func=provider_cmd)

    p_current = provider_sub.add_parser("current", help="Show current provider selection")
    p_current.set_defaults(func=provider_cmd)

    p_switch = provider_sub.add_parser("switch", help="Switch to a different provider")
    p_switch.add_argument("provider", help="Provider ID (e.g., openai, deepseek, gemini, ollama)")
    p_switch.add_argument("--model", default="", help="Specific model to use")
    p_switch.add_argument("--base-url", default="", help="Custom base URL")
    p_switch.add_argument(
        "--strategy",
        choices=["auto", "fastest", "cheapest", "best_quality", "local_only"],
        default="auto",
        help="Routing strategy",
    )
    p_switch.add_argument(
        "--goal", choices=["coding", "latency", "balanced"], default="coding", help="Optimization goal"
    )
    p_switch.set_defaults(func=provider_cmd)

    p_reset = provider_sub.add_parser("reset", help="Reset provider to auto-select")
    p_reset.set_defaults(func=provider_cmd)

    p_discover = provider_sub.add_parser("discover", help="Discover local Ollama models and endpoints")
    p_discover.set_defaults(func=provider_cmd)

    # == MCP Commands (Phase 4) ==================================
    mcp_parser = sub.add_parser("mcp", help="Manage MCP server connections and tools.")
    mcp_sub = mcp_parser.add_subparsers(dest="action", required=True)

    mcp_list = mcp_sub.add_parser("list", help="List configured MCP servers")
    mcp_list.add_argument("--connected", action="store_true", help="Show only connected servers")
    mcp_list.set_defaults(func=mcp_cmd)

    mcp_add = mcp_sub.add_parser("add", help="Add an MCP server configuration")
    mcp_add.add_argument("name", help="Server name")
    mcp_add.add_argument("--command", default="", help="Stdio command (e.g., npx)")
    mcp_add.add_argument(
        "--args", default="", help='Command arguments as a single quoted string, e.g. --args "-y @anthropic/mcp-fetch"'
    )
    mcp_add.add_argument("--url", default="", help="SSE/HTTP URL (for remote servers)")
    mcp_add.add_argument("--type", choices=["stdio", "sse", "http"], default="stdio", help="Transport type")
    mcp_add.add_argument("--scope", choices=["project", "local", "user"], default="local", help="Config scope")
    mcp_add.set_defaults(func=mcp_cmd)

    mcp_remove = mcp_sub.add_parser("remove", help="Remove an MCP server configuration")
    mcp_remove.add_argument("name", help="Server name to remove")
    mcp_remove.set_defaults(func=mcp_cmd)

    mcp_connect = mcp_sub.add_parser("connect", help="Connect to all MCP servers and show tools")
    mcp_connect.add_argument("--server", default="", help="Connect to a specific server")
    mcp_connect.set_defaults(func=mcp_cmd)

    mcp_discover = mcp_sub.add_parser("discover", help="Discover MCP config files and env settings")
    mcp_discover.set_defaults(func=mcp_cmd)

    mcp_start = mcp_sub.add_parser("start", help="Start PythonAI as an MCP server (for external tools)")
    mcp_start.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="Transport type")
    mcp_start.add_argument("--port", type=int, default=8766, help="Port for SSE mode")
    mcp_start.add_argument("--host", default="127.0.0.1", help="Host for SSE mode")
    mcp_start.set_defaults(func=mcp_cmd)

    # == Models Command ==========================================
    models_parser = sub.add_parser("models", help="List known models and their capabilities.")
    models_parser.add_argument("--provider", default="", help="Filter by provider (e.g., openai, deepseek, ollama)")
    models_parser.set_defaults(func=models_cmd)

    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


# ============================================
# Provider Commands (Phase 2)
# ============================================


def provider_cmd(args: argparse.Namespace) -> int:
    """Manage provider selection and routing."""
    from src.core.providers import (
        ProfileManager,
        ProviderDiscovery,
        ProviderRouter,
    )

    router = ProviderRouter()
    profile_mgr = ProfileManager()

    if args.action == "list":
        statuses = router.get_provider_status()
        print("\n[Provider] Available Providers")
        print(f"{'=' * 60}")
        print(f"  {'ID':14s} {'Status':10s} {'Default Model':30s}")
        print(f"  {'=' * 14} {'=' * 10} {'=' * 30}")
        for s in statuses:
            status_str = "[OK]" if s["available"] else "[--]"
            print(f"  {s['id']:14s} {status_str:10s} {s['default_model']:30s}")
        print()
        return 0

    if args.action == "current":
        current = profile_mgr.get_current()
        print("\n[Provider] Current Selection")
        print(f"{'=' * 50}")
        print(f"  Provider : {current['provider']}")
        print(f"  Model    : {current['model'] or '(default)'}")
        print(f"  Label    : {current['label']}")
        if current.get("base_url"):
            print(f"  Base URL : {current['base_url']}")
        print(f"  Strategy : {current.get('strategy', 'auto')}")
        print(f"  Saved    : {current.get('is_saved', False)}")
        print()

        # Show route result
        result = router.route(
            provider=current["provider"],
            model=current["model"],
        )
        if result.error:
            print(f"  [!] {result.error}")
        else:
            print("  Active Route:")
            print(f"    Provider: {result.provider}")
            print(f"    Model   : {result.model}")
            print(f"    API     : {result.base_url}")
            print(f"    Key     : {'...' + result.api_key[-4:] if result.api_key else 'N/A'}")
            print(f"    Type    : {result.api_type}")
        print()
        return 0

    if args.action == "switch":
        provider = args.provider
        if not provider:
            print("[Error] Please specify a provider. Use: python -m src.cli provider switch <provider>")
            return 1

        # Check provider exists
        provider_info = None
        from src.core.providers import get_registry

        provider_info = get_registry().get_provider(provider)

        if not provider_info:
            print(f"[Error] Unknown provider '{provider}'. Use 'python -m src.cli provider list' to see available.")
            return 1

        # Check key availability
        if provider_info.requires_key and not router.has_key(provider):
            print(f"[!] No API key found for '{provider}'. Set {provider_info.env_key} env var or use:")
            print(f"    python -m src.cli apikeys set {provider} <your-key>")
            return 1

        # Save profile
        profile = profile_mgr.set_provider(
            provider=provider,
            model=args.model or "",
            base_url=args.base_url or "",
            strategy=args.strategy or "auto",
            goal=args.goal or "coding",
        )
        print(f"[OK] Switched to provider: {profile.label} ({profile.provider})")
        if profile.model:
            print(f"     Model: {profile.model}")
        print(f"     Saved to: {profile_mgr.profile_path}")
        print()
        print("  Next: Run 'python -m src.cli ask \"your question\" --tools' to use with tools")
        print("        Or run 'python -m src.cli ask \"your question\"' for RAG mode")
        return 0

    if args.action == "reset":
        profile_mgr.delete()
        print("[OK] Provider profile cleared. Will auto-select provider on next run.")
        return 0

    if args.action == "discover":
        discovery = ProviderDiscovery()
        print("[Provider] Discovering local models...")
        print()

        # Ollama
        ollama = discovery.discover_ollama()
        if ollama:
            print(f"  Ollama Models ({len(ollama)}):")
            for m in ollama:
                print(f"    - {m['name']}")
            print()
        else:
            print("  Ollama: Not found or no models installed.")
            print()

        # Local endpoints
        endpoints = discovery.detect_local_endpoints()
        if endpoints:
            print(f"  Local Endpoints ({len(endpoints)}):")
            for ep in endpoints:
                print(f"    - {ep['label']}: {ep['base_url']}")
            print()

        # Available cloud providers
        statuses = router.get_provider_status()
        cloud = [s for s in statuses if not s["is_local"] and s["available"]]
        if cloud:
            print(f"  Cloud Providers with keys ({len(cloud)}):")
            for s in cloud:
                print(f"    - {s['label']} ({s['id']}): {s['default_model']}")
            print()

        return 0

    return 1


# ============================================
# MCP Commands (Phase 4)
# ============================================


def mcp_cmd(args: argparse.Namespace) -> int:
    """Manage MCP server connections, configs, and tools."""
    from src.core.mcp import (
        HTTPConfig,
        MCPClient,
        MCPConfigManager,
        MCPScope,
        SSEConfig,
        StdioConfig,
        discover_mcp_servers,
        find_mcp_json_files,
    )
    from src.core.registry import get_registry

    if args.action == "list":
        config_mgr = MCPConfigManager()
        summary = config_mgr.summary()

        print(f"\n[MCP] Configured Servers ({summary['total']})")
        print(f"{'=' * 60}")

        if not summary["servers"]:
            print("  No MCP servers configured.")
            print("  Run 'python -m src.cli mcp add <name> --command <cmd>' to add one.")
        else:
            for s in summary["servers"]:
                print(f"  {s['name']:25s} {s['type']:25s} [{s['scope']}]")

        # Show global config files
        json_files = find_mcp_json_files()
        if json_files:
            print("\n  Config files:")
            for f in json_files:
                print(f"    {f}")
        print()
        return 0

    if args.action == "discover":
        print("\n[MCP] Discovery")
        print(f"{'=' * 60}")

        # Config files
        json_files = find_mcp_json_files()
        if json_files:
            print("\n  Config files found:")
            for f in json_files:
                size = f.stat().st_size
                print(f"    - {f} ({size} bytes)")
        else:
            print("\n  No .mcp.json or mcp.json config files found.")

        # Env vars
        import os

        env_servers = {}
        for key in os.environ:
            if key.startswith("PYTHONAI_MCP_") and key.endswith("_COMMAND"):
                name = key[len("PYTHONAI_MCP_") : -len("_COMMAND")].lower()
                env_servers[name] = os.environ[key]

        if env_servers:
            print(f"\n  Environment-defined servers ({len(env_servers)}):")
            for name, cmd in env_servers.items():
                print(f"    - {name}: {cmd}")

        # Registered servers from config
        config_mgr = MCPConfigManager()
        servers = config_mgr.get_servers()
        if servers:
            print(f"\n  Registered servers ({len(servers)}):")
            for name in servers:
                print(f"    - {name}")
        print()
        return 0

    if args.action == "add":
        name = args.name
        transport_type = args.type or "stdio"

        if transport_type == "stdio":
            if not args.command:
                print("[Error] --command is required for stdio servers")
                return 1
            # Split args string using shlex to handle quoted strings
            # e.g. --args "-y @server/name C:\Program Files\dir"
            # preserves "C:\Program Files\dir" as a single arg
            args_list = shlex.split(args.args) if args.args else []
            config = StdioConfig(command=args.command, args=args_list)
        elif transport_type == "sse":
            if not args.url:
                print("[Error] --url is required for SSE servers")
                return 1
            config = SSEConfig(url=args.url)
        elif transport_type == "http":
            if not args.url:
                print("[Error] --url is required for HTTP servers")
                return 1
            config = HTTPConfig(url=args.url)
        else:
            print(f"[Error] Unsupported transport: {transport_type}")
            return 1

        scope_map = {
            "project": MCPScope.PROJECT,
            "local": MCPScope.LOCAL,
            "user": MCPScope.USER,
        }
        scope = scope_map.get(args.scope or "local", MCPScope.LOCAL)

        config_mgr = MCPConfigManager()
        config_mgr.add(name, config, scope)

        print(f"[OK] MCP server '{name}' added ({transport_type}, scope: {scope.value})")
        print(f"  Run 'python -m src.cli mcp connect --server {name}' to connect")
        return 0

    if args.action == "remove":
        name = args.name
        config_mgr = MCPConfigManager()
        if config_mgr.remove(name):
            print(f"[OK] MCP server '{name}' removed")
        else:
            print(f"[Error] MCP server '{name}' not found")
            return 1
        return 0

    if args.action == "connect":
        if args.server:
            server_name = args.server
            config_mgr = MCPConfigManager()
            config = config_mgr.get(server_name)
            if not config:
                print(f"[Error] Server '{server_name}' not found in config")
                print("  Run 'python -m src.cli mcp discover' to see available servers")
                return 1

            print(f"\n[MCP] Connecting to '{server_name}'...")

            from src.core.mcp import MCPClient

            client = MCPClient()
            connection = client.connect(config, server_name)

            if connection.state.name == "CONNECTED":
                print("  [OK] Connected!")
                print(f"  Tools: {len(connection.tools)}")
                print(f"  Resources: {len(connection.resources)}")
                print()

                if connection.tools:
                    print(f"  {'Tool Name':45s} {'Description'}")
                    print(f"  {'=' * 45} {'=' * 40}")
                    for t in connection.tools:
                        desc = t.description[:50] + "..." if len(t.description) > 50 else t.description
                        print(f"  {t.name:45s} {desc}")

                # Register tools in registry
                from src.core.registry import get_registry

                registry = get_registry()
                count = registry.register_mcp_server(connection)
                print(f"\n  Registered {count} MCP tools in PythonAI registry")
                print(f"  Total tools: {registry.total_count}")
            else:
                print(f"  [FAIL] {connection.error}")
            print()
        else:
            print("\n[MCP] Connecting to all configured servers...")
            connections = discover_mcp_servers()

            connected = 0
            total_tools = 0
            for name, conn in connections.items():
                if conn.state.name == "CONNECTED":
                    connected += 1
                    total_tools += len(conn.tools)
                    # Register tools
                    from src.core.registry import get_registry

                    get_registry().register_mcp_server(conn)
                    print(f"  [OK] {name}: {len(conn.tools)} tools, {len(conn.resources)} resources")
                else:
                    print(f"  [--] {name}: {conn.error or 'failed'}")

            print(f"\n  Connected: {connected}/{len(connections)}")
            print(f"  Total MCP tools registered: {total_tools}")
            print()
        return 0

    if args.action == "start":
        """Start PythonAI as an MCP server."""
        from src.core.mcp import MCPServer, start_mcp_server
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        # Make sure built-in tools are registered
        registry = get_registry()
        try:
            register_all_tools(registry)
        except Exception:
            pass

        # Create the MCP server with tool discovery function
        def get_tools_list():
            registry = get_registry()
            return [t.to_dict() for t in registry.list_all()]

        server = MCPServer(
            name="pythonai",
            version="2.0.0",
            get_tools_fn=get_tools_list,
        )

        print(f"\n[MCP] Starting PythonAI MCP server ({args.transport})...")
        print(f"  Tools available: {len(get_tools_list())}")

        if args.transport == "sse":
            print(f"  SSE endpoint: http://{args.host}:{args.port}/sse")
            print(f"  Message endpoint: http://{args.host}:{args.port}/message")
            print("  Press Ctrl+C to stop\n")
        else:
            print("  Stdio mode — reading from stdin, writing to stdout")
            print("  Use with: claude mcp add pythonai -- python -m src.cli mcp start")
            print()

        start_mcp_server(
            server,
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
        return 0

    return 1


def models_cmd(args: argparse.Namespace) -> int:
    """List available models."""
    from src.core.providers import get_registry

    registry = get_registry()
    provider = args.provider
    models = registry.list_models(provider=provider if provider else None)

    if provider:
        models = [m for m in models if m.provider == provider]
        if not models:
            print(f"[Models] No models found for provider '{provider}'")
            return 1

    print(f"\n[Models] Known Models ({len(models)})")
    print(f"{'=' * 70}")
    print(f"  {'Model ID':30s} {'Provider':12s} {'Context':10s} {'Capabilities'}")
    print(f"  {'=' * 30} {'=' * 12} {'=' * 10} {'=' * 20}")

    for m in models:
        caps = []
        if m.capabilities.vision:
            caps.append("vision")
        if m.capabilities.reasoning:
            caps.append("reasoning")
        if "coding" in m.classification:
            caps.append("coding")
        cap_str = ", ".join(caps) if caps else "chat"

        ctx = f"{m.context_window:,}"
        default_mark = " [D]" if m.default_model else ""
        print(f"  {m.id:30s} {m.provider:12s} {ctx:10s} {cap_str}{default_mark}")

    print()
    print("  [D] = Default model for provider")
    print()
    return 0


def main() -> None:
    from src.utils.logging_config import setup_logging

    setup_logging()

    args = parse_args()

    # Handle --version
    if getattr(args, "version", False):
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
    if getattr(args, "completion", None):
        shell = args.completion
        if shell == "bash":
            print("""_PythonAICompletion()
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
complete -F _PythonAICompletion pythonai""")
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
            print(
                '''complete -c python -m src.cli -f -a "status train login eval probe ask clean dataset augment merge webui apikeys hf-collect conv serve export"'''
            )
        return

    if not hasattr(args, "func"):
        parser = build_parser()
        parser.print_help()
        return

    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
