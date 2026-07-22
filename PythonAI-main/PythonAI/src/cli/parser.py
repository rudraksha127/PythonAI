from __future__ import annotations

import argparse
import sys

from src.cli.ask_cmd import ask, cast_cmd, conv_cmd, graph_cmd, probe
from src.cli.auth_cmd import apikeys_cmd, login_cmd
from src.cli.common import ROOT, VERSION
from src.data.apikeys import ALL_PROVIDERS
from src.cli.data_cmd import (
    augment,
    collect_data_cmd,
    dataset_info,
    discovery_cmd,
    generate_api,
    hf_collect,
    merge_data,
    phase1_cmd,
)
from src.cli.mcp_cmd import mcp_cmd, tools_cmd
from src.cli.misc_cmd import clean, forge_cmd, learn_cmd, recommend_cmd, status
from src.cli.provider_cmd import models_cmd, provider_cmd
from src.cli.serve_cmd import dashboard_cmd, serve_cmd, webui_run
from src.cli.train_cmd import evaluate, export_cmd, grpo_cmd, train, training_cmd


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

    rec_parser = sub.add_parser("recommend", help="Search and recommend PyPI packages (from 853,111 package index).")
    rec_parser.add_argument("query", help="Keyword or problem description (e.g. 'web scraping', 'langfuse')")
    rec_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    rec_parser.set_defaults(func=recommend_cmd)

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

    models_parser = sub.add_parser("models", help="List known models and their capabilities.")
    models_parser.add_argument("--provider", default="", help="Filter by provider (e.g., openai, deepseek, ollama)")
    models_parser.set_defaults(func=models_cmd)

    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def main() -> None:
    from src.utils.logging_config import setup_logging

    setup_logging()

    args = parse_args()

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
