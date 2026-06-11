from typing import Any

from src.utils.llm import generate_with_provider
from src.utils.swarm import GenerationTask

TEACHER_SYSTEM_PROMPT = """You are the Teacher Agent — a patient Python educator.
Your job:
1. Explain concepts from first principles, step by step
2. Use analogies and real-world examples
3. Build understanding progressively (beginner → advanced)
4. Include interactive exercises when possible
5. Use Hindi + English (Hinglish) if the user writes in Hindi
Format: Use headers, bullet points, and code examples."""

def run_teacher_agent(task: GenerationTask) -> dict[str, Any]:
    prompt = f"Teach: {task.prompt}"
    try:
        response = generate_with_provider(
            prompt,
            provider="auto",
            system_prompt=TEACHER_SYSTEM_PROMPT,
        )
        return {"output": response}
    except Exception as e:
        return {"output": f"[Teacher Agent failed]: {e}"}
