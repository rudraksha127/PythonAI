#!/usr/bin/env python3
"""
ForgeAI — Master Orchestration Script
======================================

Single entry point for all ForgeAI operations across the ecosystem.

Usage:
    python forgeai.py capture stats          # View capture statistics
    python forgeai.py rag index ./src        # Index codebase with cAST
    python forgeai.py train --sdft           # Train with SDFT
    python forgeai.py train --grpo           # Train with GRPO
    python forgeai.py train --now            # Immediate training trigger
    python forgeai.py agent "fix the bug"    # Run agent
    python forgeai.py dashboard              # Start dashboard
    python forgeai.py config show            # Show configuration
    python forgeai.py config init            # Initialize config
    python forgeai.py install                # Interactive setup wizard
    python forgeai.py start                  # Start server daemon
    python forgeai.py status                 # Health check dashboard
    python forgeai.py index ./project        # RAG indexing trigger
    python forgeai.py template list          # List prompt templates
    python forgeai.py analytics report       # Usage analytics report
    python forgeai.py stats                  # View metrics

Research Foundation: MIT SEAL · cAST · GRPO · SDFT · Unsloth · vLLM
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


# ── Path Setup ────────────────────────────────────────────────────
# Ensure PythonAI/ is on sys.path so `from src.*` imports resolve
# regardless of which directory the user runs forgeai.py from.
_forgeai_root = Path(__file__).resolve().parent
_pythonai_src = _forgeai_root / "PythonAI"
if _pythonai_src.is_dir() and str(_pythonai_src) not in sys.path:
    sys.path.insert(0, str(_pythonai_src))
# ─────────────────────────────────────────────────────────────────


def cmd_capture(args):
    """Capture engine commands."""
    from src.learning.capture_engine import CaptureEngine

    engine = CaptureEngine()

    if args.action == "stats":
        stats = engine.get_statistics()
        print(json.dumps(stats, indent=2))
    elif args.action == "export":
        count = engine.export_for_training(args.output, args.format)
        print(f"Exported {count} training examples to {args.output}")
    elif args.action == "rate":
        rates = engine.get_acceptance_rate(args.days)
        for r in rates:
            print(
                f"{r['date']}: {r['acceptance_rate']:.1f}% ({r['accepts']}A/{r['rejects']}R/{r['edits']}E)"
            )


def cmd_rag(args):
    """RAG engine commands."""
    from src.rag.cast_chunker import CastChunker

    chunker = CastChunker()

    if args.action == "index":
        path = Path(args.path)
        if path.is_file():
            chunks = chunker.chunk_file(path)
        elif path.is_dir():
            chunks = chunker.chunk_directory(path)
        else:
            print(f"Error: {path} not found")
            sys.exit(1)

        if args.output:
            import json

            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump([c.to_dict() for c in chunks], f, indent=2)
            print(f"Wrote {len(chunks)} chunks to {args.output}")
        else:
            for chunk in chunks:
                print(f"[{chunk.chunk_type}] {chunk.name} ({chunk.token_count} tokens)")
            print(f"\nTotal: {len(chunks)} chunks")


def cmd_train(args):
    """Training commands."""
    from src.config import get_config

    config = get_config()

    # ── Immediate training trigger ──
    if args.now:
        print("🚀 Triggering immediate training run...")
        import requests as req

        try:
            resp = req.post(
                "http://localhost:7337/api/training/trigger",
                json={},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Training triggered: {data.get('run_id', 'unknown')}")
                print(f"   Status: {data.get('status', 'unknown')}")
            elif resp.status_code == 409:
                print("⚠️  Training run already in progress.")
            else:
                print(f"❌ Server error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"❌ Could not reach server: {e}")
            print("   Make sure the server is running (forgeai.py start)")
        return

    # ── Schedule config ──
    if args.schedule:
        import requests as req
        from src.api.server import FORGEAI_SCHEDULER_CRON

        try:
            data = {}
            if args.schedule in ("enable", "disable"):
                data["enabled"] = args.schedule == "enable"
            elif args.schedule:
                data["cron"] = args.schedule

            resp = req.put(
                "http://localhost:7337/api/training/schedule",
                json=data,
                timeout=5,
            )
            if resp.status_code == 200:
                result = resp.json()
                print(f"✅ Schedule updated:")
                print(f"   Enabled: {result['enabled']}")
                print(f"   Cron: {result['cron']}")
                print(f"   Next run: {result['next_run']}")
            else:
                print(f"❌ Update failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"❌ Could not reach server: {e}")
        return

    # ── Status / Show ──
    if args.show:
        import requests as req

        try:
            resp = req.get(
                "http://localhost:7337/api/training/schedule", timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                print(f"📅 Training Schedule:")
                print(f"   Enabled: {data.get('enabled', '?')}")
                print(f"   Cron: {data.get('cron', '?')}")
                print(f"   Description: {data.get('description', '?')}")
                print(f"   Last run: {data.get('last_run', 'never')}")
                print(f"   Next run: {data.get('next_run', '?')}")
                print(f"   Total runs: {data.get('total_runs', 0)}")
            else:
                print(f"❌ Error: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"❌ Could not reach server: {e}")
        return

    # ── Existing SDFT / GRPO commands ──
    if args.sdft:
        print("Starting SDFT training...")
        from src.training.sdft_trainer import SDFTTrainer

        trainer = SDFTTrainer(
            model_name=config.training.base_model,
            lora_rank=config.training.lora_rank,
            learning_rate=config.training.learning_rate,
        )

        if args.data:
            import json

            examples = []
            with open(args.data) as f:
                for line in f:
                    if line.strip():
                        try:
                            examples.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            print(f"Loaded {len(examples)} training examples")
        else:
            print("No training data specified. Use --data <file>")
            sys.exit(1)

        if args.replay:
            trainer.replay_buffer.load_from_disk(
                args.replay,
                args.foundational or (Path(args.replay).parent / "foundational.jsonl"),
            )

        metrics = trainer.train(
            current_examples=[],
            output_dir=args.output or "checkpoints/forge_model",
            num_epochs=args.epochs,
            batch_size=config.training.batch_size,
        )

        print(json.dumps(metrics, indent=2))

    elif args.grpo:
        print("Starting GRPO training...")
        from src.training.grpo_trainer import GRPOTrainer, GRPOPair

        trainer = GRPOTrainer(
            model_name=args.model or config.training.base_model,
            lora_rank=config.training.lora_rank,
            learning_rate=config.training.grpo_learning_rate,
            kl_coef=config.training.grpo_kl_coef,
        )

        if args.data:
            import json

            pairs = []
            with open(args.data) as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            pairs.append(GRPOPair.from_dict(data))
                        except (json.JSONDecodeError, KeyError):
                            pass
            print(f"Loaded {len(pairs)} GRPO pairs")

            metrics = trainer.train(
                pairs=pairs,
                output_dir=args.output or "checkpoints/forge_grpo",
                num_epochs=args.epochs,
                batch_size=config.training.batch_size,
            )
            print(json.dumps(metrics, indent=2))
        else:
            print("No training data specified. Use --data <pairs.jsonl>")
            sys.exit(1)


def cmd_agent(args):
    """Agent commands."""
    print(f"Agent mode: {args.task}")
    print("Connecting to Hermes-Agent...")

    try:
        from src.integration.hermes_bridge import call_hermes_agent

        result = call_hermes_agent(args.task)
        print(json.dumps(result, indent=2))
    except ImportError:
        print("Warning: hermes-agent not installed")
        print("Install with: pip install -e hermes-agent-main")


def cmd_config(args):
    """Configuration commands."""
    from src.config import ForgeAIConfig, get_config

    if args.action == "show":
        config = get_config()
        print(json.dumps(config.to_dict(), indent=2))
    elif args.action == "init":
        config = ForgeAIConfig()
        config.save()
        print(f"Configuration saved to ~/.forgeai/config.json")
        print(json.dumps(config.to_dict(), indent=2))
    elif args.action == "paths":
        config = get_config()
        print("ForgeAI Paths:")
        print(f"  Models: {config.expand_path(config.paths.models_dir)}")
        print(f"  Data: {config.expand_path(config.paths.data_dir)}")
        print(f"  Signals DB: {config.expand_path(config.capture.db_path)}")
        print(f"  Logs: {config.expand_path(config.paths.logs_dir)}")


def cmd_review(args):
    """Code review commands."""
    from src.review import GitAnalyzer, ReviewEngine, ReviewRequest

    if args.action == "code":
        if not args.file:
            print("Error: --file <path> is required for code review")
            sys.exit(1)

        path = Path(args.file)
        if not path.exists():
            print(f"Error: File not found: {path}")
            sys.exit(1)

        code = path.read_text(encoding="utf-8")
        lang = args.language or GitAnalyzer.detect_language(args.file)

        print(f"\nReviewing {args.file} ({lang})...")
        print("=" * 60)

        engine = ReviewEngine()
        request = ReviewRequest(code=code, language=lang, file_path=args.file)
        result = engine.review_code(request)

        print(f"\nScore: {result.score}/10")
        print(f"Summary: {result.summary}")
        print()

        if result.issues:
            print(f"Issues ({len(result.issues)}):")
            for i, issue in enumerate(result.issues, 1):
                loc = f"L{issue.line}" if issue.line else ""
                print(f"  {i}. [{issue.severity.upper()}] [{issue.category}] {loc}")
                print(f"     {issue.message}")
                if issue.suggestion:
                    print(f"     -> {issue.suggestion}")
                print()

        if result.strengths:
            print("Strengths:")
            for s in result.strengths:
                print(f"  + {s}")
            print()

        if result.suggestions:
            print("Suggestions:")
            for s in result.suggestions:
                print(f"  -> {s}")
            print()

    elif args.action == "git":
        repo = args.repo or Path.cwd()
        print(f"\nAnalyzing git changes in {repo}...")
        print("=" * 60)

        analyzer = GitAnalyzer(repo_path=repo)

        if args.commit:
            changes = analyzer.get_diff(commit_range=args.commit)
        elif args.staged:
            changes = analyzer.get_diff(staged=True)
        else:
            changes = analyzer.get_uncommitted_changes()

        if not changes:
            print("No changes to review.")
            return

        print(f"\nFound {len(changes)} changed files")
        for c in changes:
            print(f"  {c.change_type:10s} {c.file_path} ({c.language})")

        engine = ReviewEngine()
        result = engine.review_git_changes(analyzer, changes)

        print(f"\nOverall Score: {result.overall_score}/10")
        print(f"Total Issues: {result.total_issues}")
        print(f"  Critical: {result.critical_count}")
        print(f"  Errors: {result.error_count}")
        print(f"\n{result.summary}")
        print()

        for review in result.reviews:
            if review.issues:
                print(f"\n{'─' * 50}")
                print(f"File: {review.file_path} (Score: {review.score}/10)")
                for issue in review.issues[:10]:
                    loc = f"L{issue.line}" if issue.line else ""
                    print(f"  [{issue.severity.upper()}] {loc}: {issue.message[:100]}")
                if len(review.issues) > 10:
                    print(f"  ... and {len(review.issues) - 10} more issues")

        if args.output:
            import json

            output_data = {
                "overall_score": result.overall_score,
                "total_issues": result.total_issues,
                "critical_count": result.critical_count,
                "summary": result.summary,
                "reviews": [
                    {
                        "file_path": r.file_path,
                        "score": r.score,
                        "summary": r.summary,
                        "issues": [i.model_dump() if hasattr(i, "model_dump") else i.__dict__ for i in r.issues],
                        "strengths": r.strengths,
                    }
                    for r in result.reviews
                ],
            }
            Path(args.output).write_text(json.dumps(output_data, indent=2), encoding="utf-8")
            print(f"\nResults saved to: {args.output}")


def cmd_battle(args):
    """Model Battle Arena commands."""
    from src.battle import BattleConfig, BattleEngine, BattleRequest

    if args.interactive or not args.prompt:
        print("\n🔥 Model Battle Arena - Interactive Mode")
        print("=" * 60)
        print("Enter prompts to compare across providers. Type 'exit' to quit.\n")

        engine = BattleEngine()

        try:
            from src.core.providers import ProviderRouter
            router = ProviderRouter()
            providers = router.get_available_providers()
            print("Available providers:")
            for p in providers:
                print(f"  {p.id:15s} - {p.label}")
            print()
        except ImportError:
            pass

        while True:
            try:
                prompt = input("Prompt: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Bye] Exiting battle mode.")
                break
            if not prompt or prompt.lower() in ("exit", "quit"):
                break

            if args.providers and args.models:
                configs = [
                    BattleConfig(provider=p, model=m)
                    for p, m in zip(args.providers, args.models or args.providers)
                ]
            else:
                configs = []

            req = BattleRequest(
                prompt=prompt,
                system_prompt=args.system or None,
                providers=configs,
                auto_select=args.auto or not configs,
                auto_count=args.count,
            )

            result = engine.run_battle(req)
            _print_battle_result(result)

        return

    # Single prompt mode
    engine = BattleEngine()

    if args.providers and args.models:
        configs = []
        for i, p in enumerate(args.providers):
            m = args.models[i] if i < len(args.models) else args.models[0]
            configs.append(BattleConfig(
                provider=p,
                model=m,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            ))
        seen = set()
        unique_configs = []
        for c in configs:
            key = (c.provider, c.model)
            if key not in seen:
                seen.add(key)
                unique_configs.append(c)
        configs = unique_configs
    else:
        configs = []

    req = BattleRequest(
        prompt=args.prompt,
        system_prompt=args.system or None,
        providers=configs,
        auto_select=args.auto or not configs,
        auto_count=args.count,
    )

    result = engine.run_battle(req)
    _print_battle_result(result)


def _print_battle_result(result):
    """Print battle results in a formatted table."""
    print(f"\n{'=' * 70}")
    print(f"🔥 MODEL BATTLE RESULTS")
    print(f"{'=' * 70}")
    print(f"Prompt: {result.prompt[:80]}..." if len(result.prompt) > 80 else f"Prompt: {result.prompt}")
    print(f"Total time: {result.total_latency_ms:.0f}ms")
    print()

    print(f"{'Provider':20s} {'Model':20s} {'Latency':12s} {'Input':8s} {'Output':8s} {'Cost':12s} {'Status'}")
    print(f"{'-' * 20} {'-' * 20} {'-' * 12} {'-' * 8} {'-' * 8} {'-' * 12} {'-' * 8}")

    for r in result.results:
        status = "OK" if not r.error else "ERR"
        latency = f"{r.latency_ms:.0f}ms" if not r.error else "-"
        cost = f"${r.cost_usd:.6f}" if not r.error else "-"
        inp = str(r.token_count_input) if not r.error else "-"
        out = str(r.token_count_output) if not r.error else "-"
        label = r.label[:19]
        model = r.model[:19]
        print(f"{label:20s} {model:20s} {latency:12s} {inp:8s} {out:8s} {cost:12s} {status:8s}")

    if result.winner:
        print(f"\n🏆 Winner: {result.winner}")

    for r in result.results:
        if r.label == result.winner and r.content:
            print(f"\n{'─' * 70}")
            print(f"WINNER RESPONSE ({r.label}):")
            print(f"{'─' * 70}")
            print(r.content[:2000])
            if len(r.content) > 2000:
                print(f"\n... (response truncated, {len(r.content)} total chars)")
            break

    print()


def cmd_dashboard(args):
    """Dashboard commands."""
    print("Starting ForgeAI Dashboard...")
    print("Opening web interface at http://localhost:8501")

    try:
        from src.webui.app import run_dashboard
        run_dashboard()
    except ImportError:
        print("Dashboard not available. Install streamlit: pip install streamlit")


def cmd_install(args):
    """Interactive setup wizard."""
    print("\n🔧 ForgeAI Setup Wizard")
    print("=" * 60)
    print("This wizard will help you configure ForgeAI for first use.\n")

    # Step 1: Check Python
    import sys as _sys
    py_ver = f"{_sys.version_info.major}.{_sys.version_info.minor}"
    print(f"[1/5] ✅ Python {py_ver} detected")

    # Step 2: Check config
    from src.config import ForgeAIConfig
    config_path = Path.home() / ".forgeai" / "config.json"
    if config_path.exists():
        print(f"[2/5] ✅ Configuration found at {config_path}")
        try:
            config = ForgeAIConfig.load()
            print(f"       Base model: {config.training.base_model}")
        except Exception:
            print(f"[2/5] ⚠️  Config file exists but may be invalid. Run 'forgeai.py config init'")
    else:
        print(f"[2/5] 🔧 Creating default configuration...")
        config = ForgeAIConfig()
        config.save()
        print(f"       Created: {config_path}")

    # Step 3: Check dependencies
    missing = []
    try:
        import fastapi  # noqa: F401
    except ImportError:
        missing.append("fastapi")
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    try:
        import chromadb  # noqa: F401
    except ImportError:
        missing.append("chromadb")

    if missing:
        print(f"[3/5] ⚠️  Missing packages: {', '.join(missing)}")
        print(f"       Install: pip install {' '.join(missing)}")
    else:
        print(f"[3/5] ✅ Core dependencies satisfied")

    # Step 4: Check server
    import requests as req
    try:
        resp = req.get("http://localhost:7337/health", timeout=3)
        if resp.status_code == 200:
            print(f"[4/5] ✅ Server is running on http://localhost:7337")
        else:
            print(f"[4/5] ⚠️  Server responded with status {resp.status_code}")
    except Exception:
        print(f"[4/5] ⚠️  Server is not running")
        print(f"       Start with: forgeai.py start")

    # Step 5: Summary
    print(f"\n[5/5] ✅ Setup check complete!")
    print(f"\n{'=' * 60}")
    print("Next steps:")
    print(f"  - Start server:  python forgeai.py start")
    print(f"  - Open dashboard: python forgeai.py dashboard")
    print(f"  - Index a project: python forgeai.py index /path/to/project")
    print(f"  - View status:   python forgeai.py status")
    print(f"{'=' * 60}\n")


def cmd_start(args):
    """Start server daemon."""
    import subprocess
    import os

    print("🚀 Starting ForgeAI server...")

    # Build command
    host = args.host or "0.0.0.0"
    port = args.port or 7337
    workers = args.workers or 1

    cmd = [
        sys.executable, "-m", "uvicorn",
        "src.api.server:app",
        "--host", str(host),
        "--port", str(port),
        "--workers", str(workers),
        "--log-level", "info",
    ]

    if args.reload:
        cmd.append("--reload")

    print(f"   Host: {host}:{port}")
    print(f"   Workers: {workers}")
    print(f"   Docs: http://localhost:{port}/docs")
    print(f"   Press Ctrl+C to stop\n")

    # Run in foreground unless --detach
    if args.detach:
        import subprocess as sp
        log_file = Path.home() / ".forgeai" / "server.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, "w") as f:
            process = sp.Popen(
                cmd,
                stdout=f,
                stderr=sp.STDOUT,
                stdin=sp.DEVNULL,
                start_new_session=True,
            )
        print(f"✅ Server started (PID: {process.pid})")
        print(f"   Logs: {log_file}")
        print(f"   Stop: kill {process.pid}")
    else:
        os.execvp(sys.executable, cmd)


def cmd_status(args):
    """Health check dashboard."""
    import requests as req

    server_url = f"http://{args.host or 'localhost'}:{args.port or 7337}"

    print("\n🔍 ForgeAI Status")
    print("=" * 60)

    # Health check
    try:
        resp = req.get(f"{server_url}/health", timeout=5)
        if resp.status_code == 200:
            health = resp.json()
            uptime = health.get("uptime_human", health.get("uptime_seconds", "?"))
            print(f"✅ Server Status: {health.get('status', 'healthy').upper()}")
            print(f"   Version: {health.get('version', '?')}")
            print(f"   Uptime: {uptime}")
            print(f"   Components:")

            for name, comp in health.get("components", {}).items():
                icon = "✅" if comp.get("status") == "ok" else "⚠️"
                print(f"     {icon} {name}: {comp.get('message', '?')}")

            api = health.get("api", {})
            print(f"\n   API Requests: {api.get('total_requests', 0)}")
            print(f"   Error Rate: {api.get('error_rate', 0)}%")
        else:
            print(f"❌ Server error: {resp.status_code}")
            print(f"   Response: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Server not reachable: {e}")
        print(f"   Start with: python forgeai.py start")

    # Metrics
    try:
        resp = req.get(f"{server_url}/metrics", timeout=5)
        if resp.status_code == 200:
            metrics = resp.json()
            providers = metrics.get("providers", {})
            rag = metrics.get("rag", {})
            training = metrics.get("training", {})

            print(f"\n📊 Metrics:")
            if providers.get("total_calls", 0) > 0:
                print(f"   Provider calls: {providers['total_calls']}")
                print(f"   Total cost: ${providers.get('total_cost', 0):.4f}")
            if rag.get("total_queries", 0) > 0:
                print(f"   RAG queries: {rag['total_queries']}")
                print(f"   RAG p95 latency: {rag.get('p95_latency_ms', 0)}ms")
            print(f"   Training runs: {training.get('total_runs', 0)}")
    except Exception:
        pass

    # Projects
    try:
        resp = req.get(f"{server_url}/api/projects", timeout=5)
        if resp.status_code == 200:
            projects = resp.json()
            print(f"\n📁 Projects ({len(projects)}):")
            for p in projects:
                langs = ", ".join(p.get("languages", [])[:3])
                print(f"   - {p['name']} ({langs})")
    except Exception:
        pass

    # Schedule
    try:
        resp = req.get(f"{server_url}/api/training/schedule", timeout=5)
        if resp.status_code == 200:
            sched = resp.json()
            print(f"\n📅 Training Schedule:")
            print(f"   Enabled: {sched.get('enabled', '?')}")
            print(f"   Cron: {sched.get('cron', '?')}")
            print(f"   Next run: {sched.get('next_run', 'N/A')}")
            print(f"   Total runs: {sched.get('total_runs', 0)}")
    except Exception:
        pass

    print()


def cmd_index(args):
    """RAG indexing trigger - index a project for retrieval."""
    import requests as req

    path = args.path or Path.cwd()
    project_name = args.name or Path(path).name

    server_url = f"http://{args.host or 'localhost'}:{args.port or 7337}"

    print(f"📚 Indexing project: {project_name}")
    print(f"   Path: {path}")
    print(f"   Force reindex: {args.force}")
    print()

    # Register project first
    try:
        resp = req.post(
            f"{server_url}/api/projects",
            json={
                "name": project_name,
                "repo_path": str(Path(path).resolve()),
                "languages": [],
            },
            timeout=10,
        )
        if resp.status_code == 201:
            project = resp.json()
            print(f"✅ Project registered: {project['id']}")
        elif resp.status_code == 409:
            print("⚠️  Project already exists")
        else:
            print(f"⚠️  Project registration: {resp.status_code}")
    except Exception as e:
        print(f"⚠️  Could not register project: {e}")

    # Trigger indexing
    try:
        resp = req.post(
            f"{server_url}/api/rag/index",
            json={
                "project_id": project_name,
                "repo_path": str(Path(path).resolve()),
                "force_reindex": args.force,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Indexing started: {data.get('job_id', '?')}")
            print(f"   Status: {data.get('status', '?')}")
        else:
            print(f"❌ Indexing failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Could not start indexing: {e}")
        print("   Make sure the server is running.")


def cmd_template(args):
    """Prompt template management."""
    from src.templates import get_template_manager

    manager = get_template_manager()

    if args.action == "list":
        templates = manager.list(include_inactive=args.all)
        if not templates:
            print("No templates found.")
            return
        print(f"\n📋 Prompt Templates ({len(templates)}):")
        print(f"{'ID':8s} {'Name':25s} {'Category':15s} {'Version':8s} {'Active'}")
        print(f"{'-' * 60}")
        for t in templates:
            active = "✅" if t.is_active else "❌"
            print(f"{t.id[:8]:8s} {t.name[:24]:25s} {t.category[:14]:15s} {t.version:8d} {active}")

    elif args.action == "show":
        tmpl = manager.get(args.template) or manager.get_by_name(args.template)
        if not tmpl:
            print(f"Template not found: {args.template}")
            return
        print(f"\n📄 Template: {tmpl.name}")
        print(f"{'─' * 60}")
        print(f"ID: {tmpl.id}")
        print(f"Category: {tmpl.category}")
        print(f"Version: {tmpl.version}")
        print(f"Variables: {', '.join(tmpl.variables)}")
        print(f"Tags: {', '.join(tmpl.tags)}")
        print(f"\nContent:\n{tmpl.content}")

    elif args.action == "create":
        if not args.name or not args.content:
            print("Error: --name and --content are required")
            sys.exit(1)
        tmpl = manager.create(
            name=args.name,
            content=args.content,
            description=args.description or "",
            category=args.category or "general",
            tags=args.tags.split(",") if args.tags else [],
        )
        print(f"✅ Template created: {tmpl.id}")

    elif args.action == "delete":
        if manager.delete(args.template):
            print(f"✅ Template deleted: {args.template}")
        else:
            print(f"Template not found: {args.template}")

    elif args.action == "render":
        if not args.variables:
            print("Error: --variables required (key=value pairs)")
            sys.exit(1)
        kwargs = {}
        for kv in args.variables:
            if "=" in kv:
                k, v = kv.split("=", 1)
                kwargs[k] = v
        try:
            result = manager.render(args.template, **kwargs)
            print(f"\n📄 Rendered Template:\n{'─' * 60}\n{result}\n{'─' * 60}")
        except ValueError as e:
            print(f"❌ {e}")


def cmd_analytics(args):
    """Usage analytics commands."""
    from src.analytics import get_tracker

    tracker = get_tracker()

    if args.action == "report":
        report = tracker.get_report(days=args.days)
        totals = report["totals"]

        print(f"\n📊 Usage Report (Last {args.days} days)")
        print("=" * 60)
        print(f"Total calls: {totals['total_calls']}")
        print(f"Total tokens: {totals['total_tokens']:,}")
        print(f"  Prompt: {totals['total_prompt_tokens']:,}")
        print(f"  Completion: {totals['total_completion_tokens']:,}")
        print(f"Total cost: ${totals['total_cost']:.4f}")
        print(f"Avg latency: {totals['avg_latency_ms']:.0f}ms")

        if report["per_provider"]:
            print(f"\nPer Provider:")
            for p in report["per_provider"]:
                print(f"  {p['provider']:15s}: {p['calls']:5d} calls, ${p['cost']:.4f}")

        if report["per_user"]:
            print(f"\nPer User:")
            for u in report["per_user"]:
                print(f"  {u['user_id']:15s}: {u['calls']:5d} calls, ${u['cost']:.4f}")

    elif args.action == "cost":
        summary = tracker.get_cost_summary(days=args.days)
        print(f"\n💰 Cost Summary (Last {args.days} days)")
        print("=" * 60)
        print(f"Total cost: ${summary['total_cost']:.4f}")
        print(f"Total calls: {summary['total_calls']}")
        print(f"Avg cost/call: ${summary['avg_cost_per_call']:.6f}")

        if summary["provider_costs"]:
            print(f"\nBy Provider:")
            for p in summary["provider_costs"]:
                print(f"  {p['provider']:15s}: ${p['cost']:.4f} ({p['calls']} calls)")


def cmd_stats(args):
    """View server metrics."""
    import requests as req

    server_url = f"http://{args.host or 'localhost'}:{args.port or 7337}"

    try:
        resp = req.get(f"{server_url}/metrics", timeout=5)
        if resp.status_code != 200:
            print(f"❌ Server error: {resp.status_code}")
            return
        metrics = resp.json()

        print(f"\n📊 ForgeAI Metrics")
        print("=" * 60)

        # Server
        srv = metrics.get("server", {})
        print(f"Uptime: {srv.get('uptime_human', '?')}")

        # API
        api = metrics.get("api", {})
        print(f"\nAPI Requests: {api.get('total_requests', 0)}")
        print(f"Error Rate: {api.get('overall_error_rate', 0)}%")

        for ep in api.get("endpoints", [])[:5]:
            print(f"  {ep['method']:6s} {ep['path']:30s} {ep['count']:5d} req  ({ep['avg_latency_ms']:.0f}ms avg)")

        # Providers
        prov = metrics.get("providers", {})
        if prov.get("total_calls", 0) > 0:
            print(f"\nProvider Calls: {prov['total_calls']}")
            print(f"Total Cost: ${prov.get('total_cost', 0):.4f}")
            for p in prov.get("providers", []):
                print(f"  {p['provider']:15s}: {p['calls']:5d} calls  {p['error_rate']:.0f}% err  ${p['total_cost']:.4f}")

        # RAG
        rag = metrics.get("rag", {})
        if rag.get("total_queries", 0) > 0:
            print(f"\nRAG Queries: {rag['total_queries']}")
            print(f"RAG p95: {rag.get('p95_latency_ms', 0)}ms")

        # Training
        training = metrics.get("training", {})
        print(f"\nTraining Runs: {training.get('total_runs', 0)}")
        print(f"Success Rate: {training.get('success_rate', 0)}%")

        print()

    except Exception as e:
        print(f"❌ Could not connect: {e}")
        print("   Make sure the server is running.")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (exported for testing)."""
    parser = argparse.ArgumentParser(
        description="ForgeAI — Self-Improving Developer AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s capture stats                    # View capture statistics
  %(prog)s rag index ./src --output chunks.json
  %(prog)s train --sdft --data training.jsonl --replay replay.jsonl
  %(prog)s train --grpo --data pairs.jsonl
  %(prog)s train --now                      # Immediate training trigger
  %(prog)s train --schedule "0 3 * * 0"     # Set cron schedule
  %(prog)s agent "fix the authentication bug"
  %(prog)s config show
  %(prog)s config init
  %(prog)s install                          # Interactive setup wizard
  %(prog)s start                            # Start server daemon
  %(prog)s status                           # Health check dashboard
  %(prog)s index ./project                  # RAG indexing trigger
  %(prog)s template list                    # List prompt templates
  %(prog)s template render my-template key=value
  %(prog)s analytics report                 # Usage analytics report
  %(prog)s stats                            # View metrics
  %(prog)s --completion bash                # Generate bash completion
  %(prog)s --completion zsh                 # Generate zsh completion
  %(prog)s --completion fish                # Generate fish completion

Research: MIT SEAL · cAST (EMNLP 2025) · GRPO (DeepSeek 2025) · SDFT (MIT 2026)
        """,
    )
    parser.add_argument(
        "--completion",
        choices=["bash", "zsh", "fish"],
        default=None,
        help="Print shell tab-completion script and exit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── Capture ──
    capture_parser = subparsers.add_parser("capture", help="Capture engine commands")
    capture_parser.add_argument("action", choices=["stats", "export", "rate"], help="Action")
    capture_parser.add_argument("--output", "-o", help="Output file")
    capture_parser.add_argument("--format", default="jsonl", choices=["jsonl", "json"])
    capture_parser.add_argument("--days", type=int, default=7)
    capture_parser.set_defaults(func=cmd_capture)

    # ── RAG ──
    rag_parser = subparsers.add_parser("rag", help="RAG engine commands")
    rag_parser.add_argument("action", choices=["index", "search"], help="Action")
    rag_parser.add_argument("path", nargs="?", help="File or directory to index")
    rag_parser.add_argument("--output", "-o", help="Output file")
    rag_parser.set_defaults(func=cmd_rag)

    # ── Train ──
    train_parser = subparsers.add_parser("train", help="Training commands")
    train_parser.add_argument("--sdft", action="store_true", help="Use SDFT training")
    train_parser.add_argument("--grpo", action="store_true", help="Use GRPO training")
    train_parser.add_argument("--now", action="store_true", help="Trigger immediate training via server")
    train_parser.add_argument("--schedule", nargs="?", const="show", default=None,
                              help="Show or update training schedule (e.g. '0 3 * * 0' or 'enable'/'disable')")
    train_parser.add_argument("--show", action="store_true", help="Show current schedule")
    train_parser.add_argument("--data", help="Training data file (JSONL)")
    train_parser.add_argument("--replay", help="Replay buffer file")
    train_parser.add_argument("--foundational", help="Foundational examples file")
    train_parser.add_argument("--output", help="Output directory")
    train_parser.add_argument("--model", help="Base model")
    train_parser.add_argument("--epochs", type=int, default=1)
    train_parser.set_defaults(func=cmd_train)

    # ── Agent ──
    agent_parser = subparsers.add_parser("agent", help="Run AI agent")
    agent_parser.add_argument("task", help="Task description")
    agent_parser.set_defaults(func=cmd_agent)

    # ── Config ──
    config_parser = subparsers.add_parser("config", help="Configuration commands")
    config_parser.add_argument("action", choices=["show", "init", "paths"], help="Action")
    config_parser.set_defaults(func=cmd_config)

    # ── Review ──
    review_parser = subparsers.add_parser("review", help="Code review commands")
    review_sub = review_parser.add_subparsers(dest="action", required=True)

    review_code = review_sub.add_parser("code", help="Review a code file")
    review_code.add_argument("--file", "-f", required=True, help="Path to the code file")
    review_code.add_argument("--language", "-l", default="", help="Language (auto-detected from extension)")
    review_code.set_defaults(func=cmd_review)

    review_git = review_sub.add_parser("git", help="Review git changes")
    review_git.add_argument("--repo", "-r", default="", help="Repository path (default: current dir)")
    review_git.add_argument("--commit", "-c", default="", help="Commit range (e.g. HEAD~3..HEAD)")
    review_git.add_argument("--staged", action="store_true", help="Review staged changes only")
    review_git.add_argument("--output", "-o", default="", help="Save results to JSON file")
    review_git.set_defaults(func=cmd_review)

    # ── Battle ──
    battle_parser = subparsers.add_parser("battle", help="Model Battle Arena - compare LLM providers")
    battle_parser.add_argument("prompt", nargs="?", default="", help="Prompt to send to all providers")
    battle_parser.add_argument("--providers", "-p", nargs="*", default=[], help="Provider IDs")
    battle_parser.add_argument("--models", "-m", nargs="*", default=[], help="Model IDs")
    battle_parser.add_argument("--auto", action="store_true", help="Auto-select top providers")
    battle_parser.add_argument("--count", "-n", type=int, default=3, help="Number of providers for auto-select")
    battle_parser.add_argument("--system", "-s", default="", help="System prompt")
    battle_parser.add_argument("--temperature", "-t", type=float, default=0.7, help="Temperature")
    battle_parser.add_argument("--max-tokens", type=int, default=1024, help="Max tokens per response")
    battle_parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    battle_parser.set_defaults(func=cmd_battle)

    # ── Dashboard ──
    dashboard_parser = subparsers.add_parser("dashboard", help="Start dashboard")
    dashboard_parser.set_defaults(func=cmd_dashboard)

    # ── Install (NEW) ──
    install_parser = subparsers.add_parser("install", help="Interactive setup wizard")
    install_parser.set_defaults(func=cmd_install)

    # ── Start (NEW) ──
    start_parser = subparsers.add_parser("start", help="Start server daemon")
    start_parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    start_parser.add_argument("--port", type=int, default=7337, help="Port number")
    start_parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    start_parser.add_argument("--reload", action="store_true", help="Auto-reload on file changes")
    start_parser.add_argument("--detach", action="store_true", help="Run in background")
    start_parser.set_defaults(func=cmd_start)

    # ── Status (NEW) ──
    status_parser = subparsers.add_parser("status", help="Health check dashboard")
    status_parser.add_argument("--host", default="localhost", help="Server host")
    status_parser.add_argument("--port", type=int, default=7337, help="Server port")
    status_parser.set_defaults(func=cmd_status)

    # ── Index (NEW) ──
    index_parser = subparsers.add_parser("index", help="Index a project for RAG retrieval")
    index_parser.add_argument("path", nargs="?", help="Project path to index (default: current dir)")
    index_parser.add_argument("--name", "-n", help="Project name (default: directory name)")
    index_parser.add_argument("--force", "-f", action="store_true", help="Force reindex")
    index_parser.add_argument("--host", default="localhost", help="Server host")
    index_parser.add_argument("--port", type=int, default=7337, help="Server port")
    index_parser.set_defaults(func=cmd_index)

    # ── Template (NEW) ──
    template_parser = subparsers.add_parser("template", help="Manage prompt templates")
    template_sub = template_parser.add_subparsers(dest="action", required=True)

    template_list = template_sub.add_parser("list", help="List all templates")
    template_list.add_argument("--all", "-a", action="store_true", help="Include inactive")
    template_list.set_defaults(func=cmd_template)

    template_show = template_sub.add_parser("show", help="Show template details")
    template_show.add_argument("template", help="Template ID or name")
    template_show.set_defaults(func=cmd_template)

    template_create = template_sub.add_parser("create", help="Create a new template")
    template_create.add_argument("--name", "-n", required=True, help="Template name")
    template_create.add_argument("--content", "-c", required=True, help="Template content with {{variables}}")
    template_create.add_argument("--description", "-d", help="Template description")
    template_create.add_argument("--category", default="general", help="Template category")
    template_create.add_argument("--tags", help="Comma-separated tags")
    template_create.set_defaults(func=cmd_template)

    template_delete = template_sub.add_parser("delete", help="Delete a template")
    template_delete.add_argument("template", help="Template ID or name")
    template_delete.set_defaults(func=cmd_template)

    template_render = template_sub.add_parser("render", help="Render a template with variables")
    template_render.add_argument("template", help="Template ID or name")
    template_render.add_argument("--variables", "-v", nargs="+", required=True, help="key=value pairs")
    template_render.set_defaults(func=cmd_template)

    # ── Analytics (NEW) ──
    analytics_parser = subparsers.add_parser("analytics", help="Usage analytics")
    analytics_sub = analytics_parser.add_subparsers(dest="action", required=True)

    analytics_report = analytics_sub.add_parser("report", help="Usage report")
    analytics_report.add_argument("--days", type=int, default=7, help="Days to report")
    analytics_report.set_defaults(func=cmd_analytics)

    analytics_cost = analytics_sub.add_parser("cost", help="Cost summary")
    analytics_cost.add_argument("--days", type=int, default=30, help="Days to summarize")
    analytics_cost.set_defaults(func=cmd_analytics)

    # ── Stats (NEW) ──
    stats_parser = subparsers.add_parser("stats", help="View server metrics")
    stats_parser.add_argument("--host", default="localhost", help="Server host")
    stats_parser.add_argument("--port", type=int, default=7337, help="Server port")
    stats_parser.set_defaults(func=cmd_stats)

    return parser


def main():
    parser = build_parser()

    # ── Auto-Complete Mode ──
    try:
        from src.completion import handle_auto_complete
        handle_auto_complete(parser)
    except ImportError:
        pass

    # ── Handle --completion ──
    if "--completion" in sys.argv:
        try:
            idx = sys.argv.index("--completion")
            if idx + 1 < len(sys.argv):
                shell = sys.argv[idx + 1]
                from src.completion import print_completion
                script = print_completion(parser, shell, sys.argv[0])
                print(script)
                sys.exit(0)
        except (ValueError, ImportError) as e:
            print(f"Completion script generation failed: {e}", file=sys.stderr)
            sys.exit(1)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
