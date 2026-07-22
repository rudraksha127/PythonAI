"""
PythonAI Monolithic CLI Compatibility Wrapper
=============================================
Delegates to modular command implementations under src.cli.
"""
from src.cli.ask_cmd import ask, cast_cmd, conv_cmd, graph_cmd, probe
from src.cli.auth_cmd import apikeys_cmd, login_cmd
from src.cli.common import VERSION, run
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
from src.cli.misc_cmd import clean, forge_cmd, learn_cmd, status
from src.cli.parser import build_parser, main, parse_args
from src.cli.provider_cmd import models_cmd, provider_cmd
from src.cli.serve_cmd import dashboard_cmd, serve_cmd, webui_run
from src.cli.train_cmd import evaluate, export_cmd, grpo_cmd, train, training_cmd

__all__ = [
    "VERSION",
    "main",
    "parse_args",
    "build_parser",
    "run",
    "status",
    "login_cmd",
    "train",
    "evaluate",
    "probe",
    "ask",
    "tools_cmd",
    "clean",
    "dataset_info",
    "augment",
    "merge_data",
    "generate_api",
    "graph_cmd",
    "cast_cmd",
    "apikeys_cmd",
    "webui_run",
    "conv_cmd",
    "hf_collect",
    "serve_cmd",
    "dashboard_cmd",
    "forge_cmd",
    "collect_data_cmd",
    "export_cmd",
    "grpo_cmd",
    "discovery_cmd",
    "training_cmd",
    "phase1_cmd",
    "learn_cmd",
    "provider_cmd",
    "mcp_cmd",
    "models_cmd",
]

if __name__ == "__main__":
    main()
