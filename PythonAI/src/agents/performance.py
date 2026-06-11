from typing import Any

from src.utils.llm import generate_with_provider
from src.utils.swarm import GenerationTask

PERF_SYSTEM_PROMPT = """You are the Performance Agent — a Python optimization expert.
Your job:
1. Profile code and identify bottlenecks
2. Suggest algorithmic improvements (O(n²) → O(n log n), etc.)
3. Recommend asyncio, multiprocessing, or caching where appropriate
4. Provide before/after benchmarks
5. Use tools like cProfile, timeit, memory_profiler patterns
Always quantify improvements with numbers."""

def run_performance_agent(task: GenerationTask) -> dict[str, Any]:
    prompt = f"Analyze and optimize:\n\n{task.prompt}"
    try:
        response = generate_with_provider(
            prompt,
            provider="auto",
            system_prompt=PERF_SYSTEM_PROMPT,
        )
        return {"output": response}
    except Exception as e:
        return {"output": f"[Performance Agent failed]: {e}"}
