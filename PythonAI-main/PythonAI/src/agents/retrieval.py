from typing import Any

from src.utils.llm import generate_parallel
from src.utils.swarm import GenerationTask

RETRIEVAL_SYSTEM_PROMPT = """You are the Retrieval Agent — a knowledge extraction specialist.
Your job:
1. Search and retrieve relevant information from context/documents
2. Rank results by relevance and recency
3. Synthesize information from multiple sources
4. Cite your sources precisely
Always be factual. If unsure, say "I need more context" rather than guessing."""


def run_retrieval_agent(task: GenerationTask) -> dict[str, Any]:
    prompt = f"Search and retrieve information for: {task.prompt}"
    try:
        # Race multiple providers for fastest retrieval
        response = generate_parallel(
            prompt,
            providers=["groq", "cerebras", "sambanova"],
            system_prompt=RETRIEVAL_SYSTEM_PROMPT,
        )
        return {"output": response}
    except Exception as e:
        return {"output": f"[Retrieval Agent failed]: {e}"}
