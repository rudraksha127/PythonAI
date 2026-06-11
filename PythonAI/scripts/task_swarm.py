"""
Thin wrapper - re-exports from src/utils/swarm.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.swarm import AgentSwarm, GenerationTask, TaskDecomposer  # noqa: F401
