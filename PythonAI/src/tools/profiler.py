from __future__ import annotations

import ast
from typing import Any

from src.utils.sandbox import execute_code
from src.utils.swarm import MCPTool


def handle_profiler(code: str, timeout: int = 10) -> dict[str, Any]:
    """Run code with cProfile and return the output."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"success": False, "error": f"SyntaxError: {e}"}

    # Wrap the user's code in a cProfile run
    wrapped_code = f"""
import cProfile
import pstats
import io

pr = cProfile.Profile()
pr.enable()

# --- User Code ---
{code}
# --- End User Code ---

pr.disable()
s = io.StringIO()
sortby = pstats.SortKey.CUMULATIVE
ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
ps.print_stats(15) # Top 15 slowest calls
print(s.getvalue())
"""

    output, error = execute_code(wrapped_code, timeout=timeout)
    if error:
        return {"success": False, "error": error}
    return {"success": True, "output": output}

profiler_tool = MCPTool(
    name="profiler",
    description="Run Python code through cProfile to identify performance bottlenecks and slow function calls.",
    handler=handle_profiler,
    parameters={
        "code": {"type": "string", "description": "The Python code to profile"},
        "timeout": {"type": "integer", "description": "Execution timeout in seconds", "default": 10}
    }
)
