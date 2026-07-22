"""
Learning loops module — Developer signal capture, self-evaluation, and autonomous daemon.

Modules:
  capture_engine — Encrypted local SQLite store for accept/reject/edit signals (MIT SEAL)
  daemon         — Autonomous learning daemon: data collection → signal extraction → training trigger
  self_eval      — RAG quality self-evaluation runner
  doc_watcher    — Python documentation update monitor
  so_sync        — StackOverflow trending Q&A syncer
  git_hooks      — Git hook integration for PR merge signals
"""

from src.learning.capture_engine import (
    CaptureEngine,
    SignalType,
    TrainingSignal,
)
from src.learning.daemon import main as daemon_main

__all__ = [
    "CaptureEngine",
    "SignalType",
    "TrainingSignal",
    "daemon_main",
]
