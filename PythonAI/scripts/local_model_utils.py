"""
Thin wrapper — re-exports from src/utils/models.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.models import (  # noqa: F401
    ROOT,
    CommandResult,
    audit_project,
    choose_training_base,
    cleanup_dry_run,
    dataset_profile,
    discover_qwen_hf_candidates,
    hardware_profile,
    list_hf_cached_models,
    list_ollama_models,
    project_python,
    save_json,
)
