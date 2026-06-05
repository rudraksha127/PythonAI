import subprocess
import sys

def execute_code(code_str: str, timeout: int = 5) -> tuple[str | None, str | None]:
    dangerous = ["import os", "import sys", "subprocess", "eval(", "exec("]
    if any(d in code_str for d in dangerous):
        return None, "Skipped (safety)"

    try:
        result = subprocess.run(
            [sys.executable, "-c", code_str],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip(), None
        else:
            return None, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return None, "Execution timed out"
    except Exception:
        return None, "Execution failed"
