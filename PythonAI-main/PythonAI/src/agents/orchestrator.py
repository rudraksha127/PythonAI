from typing import Any

from loguru import logger

# Import specific agents to allow collaboration
from src.agents.code import run_code_agent
from src.agents.debug import run_debug_agent
from src.utils.llm import generate_parallel
from src.utils.memory import AgentMemory
from src.utils.swarm import GenerationTask

# Global memory instance
memory = AgentMemory()

ORCHESTRATOR_SYSTEM_PROMPT = """You are the Orchestrator Agent for the Anti-Gravity God Mode AI system.
You are the central brain that routes tasks to specialized agents.
When answering directly:
1. Be comprehensive but concise
2. Always verify facts against your knowledge
3. If a task involves code, delegate to Code Agent first, then verify with Debug Agent
4. Support Hinglish (Hindi + English) if the user writes in Hindi"""


def run_orchestrator_agent(task: GenerationTask, session_id: str = "default") -> dict[str, Any]:
    # Search memory for past context
    past_context = memory.search_memory(session_id, task.prompt)
    context_str = "\n".join(past_context)

    # 1. Routing decision
    prompt_lower = task.prompt.lower()
    is_coding_task = any(
        kw in prompt_lower
        for kw in [
            "code",
            "function",
            "script",
            "bug",
            "implement",
            "class",
            "def ",
            "import",
            "write a",
            "build a",
            "create a program",
            "fix this",
        ]
    )

    if is_coding_task:
        logger.info("[Orchestrator] Routing to Code Agent (parallel race)...")
        code_result = run_code_agent(task).get("output", "")

        logger.info("[Orchestrator] Code generated. Routing to Debug Agent for verification...")
        verify_task = GenerationTask(
            prompt=f"Review and fix any potential issues in this code. "
            f"If perfect, just return the code with 'LGTM ✓'.\n"
            f"Code:\n{code_result}\n\nOriginal Request: {task.prompt}"
        )
        final_result = run_debug_agent(verify_task).get("output", "")

        response = f"**[Orchestrator Verified Output]**\n\n{final_result}"
    else:
        # Standard processing — use parallel for speed
        prompt = f"Task: {task.prompt}"
        if context_str:
            prompt = f"Relevant past context:\n{context_str}\n\n{prompt}"

        try:
            response = generate_parallel(
                prompt,
                system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
            )
        except Exception as e:
            response = f"[Orchestrator Agent failed]: {e}"

    # Save interaction to memory
    memory.add_memory(session_id, "user", task.prompt)
    memory.add_memory(session_id, "orchestrator", response)

    return {"output": response}
