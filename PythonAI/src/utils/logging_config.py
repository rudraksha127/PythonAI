"""
Centralized Logging Configuration for PythonAI
═══════════════════════════════════════════════

Provides structured logging with:
- Console output with color coding (via Rich if available)
- File rotation (10MB per file, keep 5 backups)
- Configurable per-module log levels
- Request ID correlation for API requests

Usage:
    from src.utils.logging_config import setup_logging
    setup_logging()  # Call once at application startup
    logger = logging.getLogger("pythonai.rag")
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Default log directory
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

_initialized = False

# Per-module levels (env var override supported, e.g. PYTHONAI_LOG_RAG=DEBUG)
_MODULE_LEVELS: dict[str, str] = {
    "pythonai.api": "INFO",
    "pythonai.rag": "INFO",
    "pythonai.training": "INFO",
    "pythonai.data": "INFO",
    "pythonai.agents": "INFO",
    "pythonai.core": "INFO",
    "pythonai.utils": "WARNING",
}


def _resolve_level(module: str) -> str:
    """Resolve log level from env var or default."""
    env_key = f"PYTHONAI_LOG_{module.split('.')[-1].upper()}"
    return os.environ.get(env_key, _MODULE_LEVELS.get(module, "INFO"))


def setup_logging(
    level: str | None = None,
    log_dir: str | Path | None = None,
    file_logging: bool = True,
    console_logging: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """
    Initialize the logging subsystem for PythonAI.

    Args:
        level: Global log level (default: INFO). Overridden by env PYTHONAI_LOG_LEVEL.
        log_dir: Directory for log files (default: project_root/logs).
        file_logging: Enable file-based logging with rotation.
        console_logging: Enable console (stderr) logging.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated log files to keep.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root_level = level or os.environ.get("PYTHONAI_LOG_LEVEL", "INFO")

    root = logging.getLogger("pythonai")
    root.setLevel(root_level)

    # Clear existing handlers to avoid duplicates
    root.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    # ── Console handler ──
    if console_logging:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(root_level)
        console.setFormatter(formatter)
        root.addHandler(console)

    # ── File handler with rotation ──
    if file_logging:
        log_path = Path(log_dir) if log_dir else _LOG_DIR
        log_path.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path / "pythonai.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(root_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        # Separate error log
        error_handler = RotatingFileHandler(
            log_path / "pythonai_error.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root.addHandler(error_handler)

    # ── Per-module levels ──
    for module, default_lvl in _MODULE_LEVELS.items():
        mod_logger = logging.getLogger(module)
        mod_logger.setLevel(_resolve_level(module))

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    root.info(f"Logging initialized (level={root_level}, file_logging={file_logging})")
