from typing import Any

from src.utils.llm import generate_with_provider
from src.utils.swarm import GenerationTask

DEBUG_SYSTEM_PROMPT = """You are the Debug Agent — a ruthless code reviewer.
Your job:
1. Find ALL bugs, edge cases, and potential crashes
2. Check for security vulnerabilities (injection, path traversal, etc.)
3. Verify logic correctness and type safety
4. Return the FIXED code with comments explaining each fix
If the code is perfect, say "LGTM ✓" and return it unchanged."""

def run_debug_agent(task: GenerationTask) -> dict[str, Any]:
    prompt = f"Review this code carefully:\n\n{task.prompt}"
    try:
        # Use Mistral for debugging (strong at code analysis)
        response = generate_with_provider(
            prompt,
            provider="mistral",
            system_prompt=DEBUG_SYSTEM_PROMPT,
        )
        return {"output": response}
    except Exception as e:
        return {"output": f"[Debug Agent failed]: {e}"}
