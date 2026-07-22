from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ═══════════════════════════════════════
# LRU RESULT CACHE
# ═══════════════════════════════════════


class LRUCache:
    """Thread-safe LRU cache for task results."""

    def __init__(self, maxsize: int = 1000):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    @staticmethod
    def make_key(task_type: str, prompt: str, metadata: dict[str, Any] | None = None) -> str:
        """Create a deterministic cache key from task inputs."""
        raw = f"{task_type}:::{prompt}"
        if metadata:
            raw += f":::{json.dumps(metadata, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()


# ═══════════════════════════════════════
# PRIORITY QUEUE
# ═══════════════════════════════════════


@dataclass(order=True)
class PrioritizedTask:
    task: Any = field(compare=False)
    priority: int = 0
    timestamp: float = field(default_factory=time.time)


class PriorityQueue:
    """Simple priority queue for tasks. Lower number = higher priority."""

    def __init__(self) -> None:
        self._items: list[PrioritizedTask] = []
        self._lock = threading.RLock()

    def push(self, task: Any, priority: int = 5) -> None:
        with self._lock:
            import heapq

            heapq.heappush(self._items, PrioritizedTask(priority=priority, task=task))

    def pop(self) -> Any | None:
        with self._lock:
            import heapq

            if not self._items:
                return None
            return heapq.heappop(self._items).task

    def peek(self) -> Any | None:
        with self._lock:
            if not self._items:
                return None
            return self._items[0].task

    def size(self) -> int:
        with self._lock:
            return len(self._items)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._items) == 0


# ═══════════════════════════════════════
# QUALITY SCORING
# ═══════════════════════════════════════


def score_output_quality(output: str) -> dict[str, Any]:
    """Score the quality of a generated output on multiple dimensions."""
    score = 0
    reasons: list[str] = []

    if not output:
        return {"total": 0, "details": {"length": 0}, "reasons": ["empty output"]}

    # Length quality
    if len(output) >= 200:
        score += 25
        reasons.append("detailed output")
    elif len(output) >= 100:
        score += 15
        reasons.append("moderate length")
    else:
        score += 5
        reasons.append("short output")

    # Code presence
    if "```" in output:
        score += 25
        reasons.append("contains code")
        if "```python" in output:
            score += 5
            reasons.append("python code block")

    # Structure indicators
    if any(marker in output.lower() for marker in ("step 1", "step 2", "first", "second", "finally")):
        score += 15
        reasons.append("structured reasoning")

    # Depth indicators
    if any(token in output.lower() for token in ("because", "therefore", "however", "consequently")):
        score += 10
        reasons.append("causal reasoning")

    if any(token in output.lower() for token in ("pitfall", "warning", "caveat", "gotcha", "common mistake")):
        score += 10
        reasons.append("pitfalls coverage")

    if any(token in output.lower() for token in ("performance", "optimize", "fast", "slow", "trade-off")):
        score += 10
        reasons.append("performance insight")

    return {
        "total": min(score, 100),
        "details": {
            "length": len(output),
            "has_code": "```" in output,
            "has_python_code": "```python" in output,
            "has_steps": any(m in output.lower() for m in ("step 1", "step 2", "first", "second")),
        },
        "reasons": reasons,
    }


# ═══════════════════════════════════════
# COST ESTIMATION
# ═══════════════════════════════════════


def estimate_api_cost(text: str, provider: str = "groq") -> dict[str, Any]:
    """Estimate API cost for generating/processing text.

    Uses approximate per-token costs for common providers.
    Cost per million tokens (input/output):
    """
    # Approximate costs per 1M tokens (input / output)
    provider_costs: dict[str, tuple[float, float]] = {
        "groq": (0.15, 0.60),
        "cerebras": (0.10, 0.40),
        "sambanova": (0.10, 0.40),
        "together": (0.50, 1.50),
        "openrouter": (0.15, 0.60),
        "huggingface": (0.20, 0.80),
        "mistral": (0.50, 1.50),
        "fireworks": (0.20, 0.80),
        "novita": (0.30, 1.00),
        "deepinfra": (0.20, 0.80),
    }

    # Rough estimate: 4 chars ≈ 1 token
    est_tokens = max(1, len(text) // 4)
    cost_per_million = provider_costs.get(provider, (0.20, 0.80))

    return {
        "estimated_tokens": est_tokens,
        "input_cost": round(est_tokens * cost_per_million[0] / 1_000_000, 6),
        "output_cost": round(est_tokens * cost_per_million[1] / 1_000_000, 6),
        "provider": provider,
        "note": "Estimates are approximate. Actual costs may vary.",
    }


# CORE DATA TYPES


@dataclass(frozen=True)
class GenerationTask:
    task_id: str
    task_type: str
    prompt: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    timeout: float = 0.0


@dataclass
class TaskResult:
    task_id: str
    task_type: str
    success: bool
    data: dict[str, Any]
    error: str = ""
    attempts: int = 1
    duration: float = 0.0
    worker_name: str = ""


class RetryStrategy(Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


# TASK DECOMPOSER


class TaskDecomposer:
    """Split a chunk into a dependency-aware task graph."""

    def decompose(self, chunk: dict[str, Any], prompts: dict[str, str]) -> list[GenerationTask]:
        has_code = bool(chunk.get("codes"))
        tasks: list[GenerationTask] = []

        for task_type, prompt in prompts.items():
            dependencies: tuple[str, ...] = ()

            if task_type in {"expert", "interview", "project", "cross_domain", "judgment", "multi_agent"}:
                dependencies = ("reasoning",)
            if task_type in {"error_fix", "code_review"}:
                dependencies = ("basic",)
            if task_type == "version":
                dependencies = ("basic",)
            if task_type in {"error_fix", "code_review"} and not has_code:
                continue

            tasks.append(
                GenerationTask(
                    task_id=f"{chunk.get('id', chunk.get('title', 'chunk'))}:{task_type}",
                    task_type=task_type,
                    prompt=prompt,
                    dependencies=dependencies,
                    metadata={
                        "title": chunk.get("title", ""),
                        "version": chunk.get("version", ""),
                        "category": chunk.get("category", ""),
                    },
                )
            )

        return tasks


# MCP TOOL SYSTEM


@dataclass
class MCPTool:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"


class MCPRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters, "version": t.version}
            for t in self._tools.values()
        ]

    def call_tool(self, name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"MCP tool '{name}' not found. Available: {list(self._tools.keys())}")
        return tool.handler(**kwargs)


# SWARM MONITOR / STATS


@dataclass
class SwarmStats:
    total_tasks: int = 0
    completed: int = 0
    failed: int = 0
    total_retries: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    by_type: dict[str, dict[str, Any]] = field(default_factory=dict)
    worker_usage: dict[str, int] = field(default_factory=dict)

    def report(self) -> str:
        lines = [
            "[STATS] Swarm Execution Report",
            "=" * 55,
            f"  Total tasks : {self.total_tasks}",
            f"  Completed   : {self.completed}",
            f"  Failed      : {self.failed}",
            f"  Retries     : {self.total_retries}",
            f"  Total time  : {self.total_duration:.2f}s",
            f"  Avg/task    : {self.avg_duration:.2f}s",
        ]
        if self.by_type:
            lines.append("  By Type:")
            for tt, info in sorted(self.by_type.items()):
                lines.append(
                    f"    {tt:15s}: {info['count']:3d} tasks, {info['failed']:2d} failed, avg {info['avg_duration']:.2f}s"
                )
        if self.worker_usage:
            lines.append("  Workers:")
            for w, c in sorted(self.worker_usage.items()):
                lines.append(f"    {w}: {c} tasks")
        lines.append("=" * 55)
        return "\n".join(lines)


class SwarmMonitor:
    def __init__(self) -> None:
        self.results: list[TaskResult] = []
        self.start_time: float = 0.0

    def start(self) -> None:
        self.start_time = time.time()
        self.results.clear()

    def record(self, result: TaskResult) -> None:
        self.results.append(result)

    def stats(self) -> SwarmStats:
        elapsed = time.time() - self.start_time
        total = len(self.results)
        completed = sum(1 for r in self.results if r.success)
        failed = total - completed
        retries = sum(r.attempts - 1 for r in self.results)
        durations = [r.duration for r in self.results]

        by_type: dict[str, dict[str, Any]] = {}
        worker_usage: dict[str, int] = {}

        for r in self.results:
            if r.task_type not in by_type:
                by_type[r.task_type] = {"count": 0, "failed": 0, "durations": []}
            by_type[r.task_type]["count"] += 1
            by_type[r.task_type]["durations"].append(r.duration)
            if not r.success:
                by_type[r.task_type]["failed"] += 1
            if r.worker_name:
                worker_usage[r.worker_name] = worker_usage.get(r.worker_name, 0) + 1

        for info in by_type.values():
            durs = info.pop("durations", [])
            info["avg_duration"] = sum(durs) / len(durs) if durs else 0.0

        return SwarmStats(
            total_tasks=total,
            completed=completed,
            failed=failed,
            total_retries=retries,
            total_duration=elapsed,
            avg_duration=sum(durations) / len(durations) if durations else 0.0,
            by_type=by_type,
            worker_usage=worker_usage,
        )


# AGENT SWARM (ENHANCED)


class AgentSwarm:
    """Execute independent tasks in parallel while honoring dependencies.
    Enhanced with retry logic, MCP tool integration, monitoring, caching,
    priority queue, quality scoring, and cost estimation."""

    def __init__(
        self,
        max_workers: int = 4,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        retry_delay: float = 0.5,
        mcp_registry: MCPRegistry | None = None,
        cache_enabled: bool = True,
        cache_maxsize: int = 1000,
        priority_enabled: bool = True,
    ):
        self.max_workers = max(1, max_workers)
        self.retry_strategy = retry_strategy
        self.retry_delay = retry_delay
        self.mcp = mcp_registry or MCPRegistry()
        if not mcp_registry:
            try:
                from src.tools import ALL_TOOLS

                for tool in ALL_TOOLS:
                    self.mcp.register(tool)
            except ImportError:
                pass
        self.monitor = SwarmMonitor()
        self.cache = LRUCache(maxsize=cache_maxsize) if cache_enabled else None
        self.priority_queue = PriorityQueue() if priority_enabled else None
        self._cache_hits = 0
        self._cache_misses = 0

    def _compute_delay(self, attempt: int) -> float:
        if self.retry_strategy == RetryStrategy.FIXED:
            return self.retry_delay
        elif self.retry_strategy == RetryStrategy.LINEAR:
            return self.retry_delay * attempt
        else:
            return self.retry_delay * (2 ** (attempt - 1))

    def _run_with_retry(
        self, task: GenerationTask, worker: Callable[[GenerationTask], dict[str, Any]], worker_name: str = ""
    ) -> TaskResult:
        max_attempts = max(1, task.max_retries + 1)
        last_error = ""
        start = time.time()

        for attempt in range(1, max_attempts + 1):
            try:
                if task.timeout > 0:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        result = pool.submit(worker, task).result(timeout=task.timeout)
                else:
                    result = worker(task)

                return TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=True,
                    data=result,
                    attempts=attempt,
                    duration=time.time() - start,
                    worker_name=worker_name,
                )

            except Exception as exc:
                last_error = str(exc)
                if attempt < max_attempts:
                    time.sleep(self._compute_delay(attempt))

        return TaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            success=False,
            data={},
            error=last_error,
            attempts=max_attempts,
            duration=time.time() - start,
            worker_name=worker_name,
        )

    def execute(
        self,
        tasks: list[GenerationTask],
        worker: Callable[[GenerationTask], dict[str, Any]],
        worker_name: str = "default",
    ) -> dict[str, dict[str, Any]]:
        self.monitor.start()
        pending = {task.task_id: task for task in tasks}
        completed: set[str] = set()
        results: dict[str, dict[str, Any]] = {}

        while pending:
            ready = [task for task in pending.values() if set(task.dependencies).issubset(completed)]
            if not ready:
                ready = list(pending.values())

            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(ready))) as executor:
                future_map = {executor.submit(self._run_with_retry, task, worker, worker_name): task for task in ready}
                for future in as_completed(future_map):
                    task = future_map[future]
                    task_result = future.result()
                    self.monitor.record(task_result)

                    if task_result.success:
                        results[task.task_id] = task_result.data
                    else:
                        results[task.task_id] = {
                            "task_type": task.task_type,
                            "pairs": [],
                            "error": task_result.error,
                            "_attempts": task_result.attempts,
                        }

                    completed.add(task.task_id)
                    pending.pop(task.task_id, None)

        return results

    def execute_with_priority(
        self,
        tasks: list[GenerationTask],
        worker: Callable[[GenerationTask], dict[str, Any]],
        worker_name: str = "default",
        priorities: dict[str, int] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Execute tasks with priority ordering. Lower number = higher priority."""
        priorities = priorities or {}
        self.monitor.start()
        completed: set[str] = set()
        results: dict[str, dict[str, Any]] = {}

        for task in tasks:
            prio = priorities.get(task.task_type, 5)
            if self.priority_queue:
                self.priority_queue.push(task, priority=prio)
            else:
                self.priority_queue = PriorityQueue()
                self.priority_queue.push(task, priority=prio)

        pending = {task.task_id: task for task in tasks}

        while pending:
            ready = [task for task in pending.values() if set(task.dependencies).issubset(completed)]
            if not ready:
                ready = list(pending.values())

            # Sort by priority within ready set
            ready.sort(key=lambda t: priorities.get(t.task_type, 5))

            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(ready))) as executor:
                future_map = {executor.submit(self._run_with_cache, task, worker, worker_name): task for task in ready}
                for future in as_completed(future_map):
                    task = future_map[future]
                    task_result = future.result()
                    self.monitor.record(task_result)

                    if task_result.success:
                        results[task.task_id] = task_result.data
                    else:
                        results[task.task_id] = {
                            "task_type": task.task_type,
                            "pairs": [],
                            "error": task_result.error,
                            "_attempts": task_result.attempts,
                        }

                    completed.add(task.task_id)
                    pending.pop(task.task_id, None)

        return results

    def _run_with_cache(
        self, task: GenerationTask, worker: Callable[[GenerationTask], dict[str, Any]], worker_name: str
    ) -> TaskResult:
        """Run a task with cache lookup if caching is enabled."""
        if self.cache is not None:
            cache_key = LRUCache.make_key(task.task_type, task.prompt, task.metadata)
            cached = self.cache.get(cache_key)
            if cached is not None:
                self._cache_hits += 1
                return TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=True,
                    data=cached,
                    attempts=1,
                    duration=0.0,
                    worker_name=f"{worker_name}[cached]",
                )
            self._cache_misses += 1

            result = self._run_with_retry(task, worker, worker_name)
            if result.success:
                self.cache.put(cache_key, result.data)
            return result

        return self._run_with_retry(task, worker, worker_name)

    def execute_monitored(
        self,
        tasks: list[GenerationTask],
        worker: Callable[[GenerationTask], dict[str, Any]],
        worker_name: str = "default",
    ) -> tuple[dict[str, dict[str, Any]], SwarmStats]:
        results = self.execute(tasks, worker, worker_name)
        return results, self.monitor.stats()

    def cache_stats(self) -> dict[str, Any]:
        """Return cache hit/miss statistics."""
        total = self._cache_hits + self._cache_misses
        return {
            "enabled": self.cache is not None,
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": round(self._cache_hits / total, 3) if total > 0 else 0.0,
            "size": self.cache.size() if self.cache else 0,
        }


# ═══════════════════════════════════════
# AGENT ROUTER
# ═══════════════════════════════════════


class AgentRouter:
    """Routes questions to specialized agents."""

    def __init__(self):
        # Map of question categories to agent types
        self.routes = {
            "debug": ["debug", "code", "retrieval"],
            "performance": ["performance", "code"],
            "architecture": ["orchestrator", "docs", "retrieval"],
            "how-to": ["code", "teacher", "retrieval"],
            "version": ["docs", "retrieval"],
            "general": ["orchestrator", "retrieval"],
        }

    def classify_and_route(self, question: str) -> list[str]:
        q_lower = question.lower()
        if any(w in q_lower for w in ["error", "bug", "fix", "fail", "exception", "traceback"]):
            return self.routes["debug"]
        if any(w in q_lower for w in ["slow", "fast", "optimize", "profile", "memory", "speed"]):
            return self.routes["performance"]
        if any(w in q_lower for w in ["architecture", "design", "structure", "pattern", "system"]):
            return self.routes["architecture"]
        if any(w in q_lower for w in ["how to", "implement", "build", "create", "write"]):
            return self.routes["how-to"]
        if any(w in q_lower for w in ["python 2", "python 3", "changed in", "new in", "deprecated"]):
            return self.routes["version"]

        return self.routes["general"]


def execute_agents(question: str, swarm: AgentSwarm, workers: dict[str, Callable]) -> dict[str, Any]:
    """Execute specialized agents based on question routing."""
    router = AgentRouter()
    agents_to_run = router.classify_and_route(question)

    tasks = []
    for i, agent_type in enumerate(agents_to_run):
        if agent_type in workers:
            tasks.append(
                GenerationTask(task_id=f"agent_{agent_type}_{i}", task_type=agent_type, prompt=question, timeout=30.0)
            )

    def dispatcher(task: GenerationTask) -> dict[str, Any]:
        agent_func = workers.get(task.task_type)
        if agent_func:
            return agent_func(task)
        return {"output": f"No agent found for {task.task_type}"}

    # Simple execution (in parallel)
    results = swarm.execute(tasks, dispatcher)

    # Synthesize results
    synthesis = {}
    for task_id, res_data in results.items():
        if not res_data.get("error"):
            synthesis[res_data.get("task_type", res_data.get("task_type", "unknown"))] = res_data.get(
                "output", res_data
            )
        else:
            synthesis[res_data.get("task_type", "unknown")] = f"[Error]: {res_data.get('error')}"

    return synthesis
