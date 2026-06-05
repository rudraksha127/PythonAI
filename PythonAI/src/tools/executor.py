from __future__ import annotations

import ast
from typing import Any
from src.utils.sandbox import execute_code
from src.utils.swarm import MCPTool

def handle_execute_code(code: str, timeout: int = 5) -> dict[str, Any]:
    """Execute Python code in a secure sandbox."""
    # Enhanced validation: Check if it parses
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"success": False, "error": f"SyntaxError: {e}"}

    output, error = execute_code(code, timeout=timeout)
    if error:
        return {"success": False, "error": error}
    return {"success": True, "output": output}

python_executor_tool = MCPTool(
    name="python_executor",
    description="Execute Python code in a safe sandbox, capturing output and errors.",
    handler=handle_execute_code,
    parameters={
        "code": {"type": "string", "description": "The Python code to execute"},
        "timeout": {"type": "integer", "description": "Execution timeout in seconds", "default": 5}
    }
)
