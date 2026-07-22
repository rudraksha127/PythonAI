from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.auth.decorators import requires_auth
from src.cli.common import ROOT, project_python, run


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
