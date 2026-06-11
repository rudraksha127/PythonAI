from typing import Any

from src.utils.llm import generate_parallel
from src.utils.swarm import GenerationTask

CODE_SYSTEM_PROMPT = """You are the Code Agent — an elite Python specialist.
Your responses must include:
1. Clean, production-ready code with type hints
2. Docstrings for every function/class
3. Error handling and edge cases
4. Performance considerations
Never explain what you're about to do — just write the code."""

def run_code_agent(task: GenerationTask) -> dict[str, Any]:
    prompt = f"Task: {task.prompt}"
    try:
        # PARALLEL MODE: Race Cerebras, Groq, SambaNova — fastest wins
        response = generate_parallel(
            prompt,
            providers=["cerebras", "groq", "sambanova"],
            system_prompt=CODE_SYSTEM_PROMPT,
        )
        return {"output": response}
    except Exception as e:
        return {"output": f"[Code Agent failed]: {e}"}
