"""PythonAI Compact System — 3-Tier Message Compaction.

Inspired by Claude Code's compaction architecture:
- micro_compact: Time-based + count-based pre-request cleanup
- auto_compact: Token threshold compaction with circuit breaker
- reactive_compact: On 413 response, compact and retry
"""

from .micro_compact import microcompact_messages
from .auto_compact import auto_compact_if_needed, get_auto_compact_threshold
from .reactive_compact import reactive_compact_if_needed

__all__ = [
    "microcompact_messages",
    "auto_compact_if_needed",
    "get_auto_compact_threshold",
    "reactive_compact_if_needed",
]
