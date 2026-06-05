from typing import Any
from src.utils.swarm import GenerationTask
from src.utils.llm import generate_with_provider

DOCS_SYSTEM_PROMPT = """You are the Documentation Agent.
Your job:
1. Explain APIs, libraries, and Python concepts with clear examples
2. Include official documentation links when possible
3. Show real code usage, not pseudo-code
4. Mention version-specific behavior (Python 3.10+ vs 3.8, etc.)
Format: Markdown with code blocks."""

def run_docs_agent(task: GenerationTask) -> dict[str, Any]:
    prompt = f"Explain: {task.prompt}"
    try:
        response = generate_with_provider(
            prompt,
            provider="openrouter",
            system_prompt=DOCS_SYSTEM_PROMPT,
        )
        return {"output": response}
    except Exception as e:
        return {"output": f"[Docs Agent failed]: {e}"}
