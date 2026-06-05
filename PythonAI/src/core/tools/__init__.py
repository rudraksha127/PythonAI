"""
PythonAI Core Tools — Individual Tool Implementations
======================================================
Inspired by Claude Code's tool implementations (BashTool, FileReadTool, etc.).
"""

from .bash_tool import BashTool
from .file_read_tool import FileReadTool
from .file_write_tool import FileWriteTool
from .file_edit_tool import FileEditTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool
from .web_fetch_tool import WebFetchTool
from .web_search_tool import WebSearchTool

# All tools in a single list for easy registration
ALL_CORE_TOOLS = [
    BashTool,
    FileReadTool,
    FileWriteTool,
    FileEditTool,
    GlobTool,
    GrepTool,
    WebFetchTool,
    WebSearchTool,
]


def register_all_tools(registry) -> None:
    """Register all core tools with the given registry."""
    for tool in ALL_CORE_TOOLS:
        registry.register(tool)


__all__ = [
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "GlobTool",
    "GrepTool",
    "WebFetchTool",
    "WebSearchTool",
    "ALL_CORE_TOOLS",
    "register_all_tools",
]
