"""
OpenJarvis Bridge — Connect PythonAI to the OpenJarvis Agent Framework
========================================================================

Merges OpenJarvis's 40+ tools and 20+ agent types into PythonAI's core,
giving the PythonAI executor access to OpenJarvis's rich tool ecosystem
(calculator, web_search, file_read, memory_store/retrieve, code_interpreter,
shell_exec, git, browser, think, llm, etc.) and autonomous agent types
(Orchestrator, Operative, MonitorOperative, DeepResearch, etc.).

Architecture:
  PythonAI ToolCallingEngine
       │
       ├──OpenJarvisToolAdapter──▶ OpenJarvis BaseTool instances
       │     (wraps OJ tools as PythonAI Tool objects, auto-discovers
       │      from OJ's ToolRegistry)
       │
       ├──OpenJarvisAgentWrapper──▶ OpenJarvis agent classes
       │     (wraps OJ agents as PythonAI callable functions,
       │      compatible with PythonAI's ALL_AGENTS dict)
       │
       └──build_oj_engine()──────▶ ToolCallingEngine with OJ tools
             (pre-configured engine with all OJ tools registered)

Usage:
    from src.integration.openjarvis_bridge import (
        is_openjarvis_available,
        discover_oj_tools,
        register_oj_tools,
        build_oj_adapter,
        build_oj_engine,
        get_oj_agents,
        get_oj_status,
    )

    # Check availability
    if is_openjarvis_available():
        # Register all OJ tools into PythonAI's ToolRegistry
        count = register_oj_tools()
        print(f"Registered {count} OpenJarvis tools")

        # Build an engine with OJ tools
        engine = build_oj_engine()
        result = engine.run("Hello from OpenJarvis + PythonAI!")

        # Get OJ agent functions compatible with PythonAI's ALL_AGENTS
        agents = get_oj_agents()
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from src.core.registry import ToolRegistry, get_registry
from src.core.tool import (
    InputSchema,
    Parameter,
    PermissionDecision,
    PermissionResult,
    Tool,
    ToolResult,
    ToolUseContext,
)

logger = logging.getLogger("forgeai.integration.openjarvis")

# ═══════════════════════════════════════
#  Availability Detection
# ═══════════════════════════════════════

_OPENJARVIS_AVAILABLE: bool | None = None
_OPENJARVIS_VERSION: str = ""


def _ensure_openjarvis_path() -> bool:
    """Add OpenJarvis to sys.path if not already there, return success."""
    global _OPENJARVIS_AVAILABLE

    # Already checked and available
    if _OPENJARVIS_AVAILABLE is True:
        return True

    # Already checked and not available — avoid repeated lookups
    if _OPENJARVIS_AVAILABLE is False:
        return False

    # Try direct import first
    try:
        import openjarvis  # noqa: F401

        _OPENJARVIS_AVAILABLE = True
        return True
    except ImportError:
        pass

    # Try finding the OpenJarvis package relative to the project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        project_root / "OpenJarvis" / "src",
        project_root / "OpenJarvis",
        Path.cwd() / "OpenJarvis" / "src",
        Path.cwd() / "OpenJarvis",
    ]

    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
        try:
            import openjarvis  # noqa: F401

            _OPENJARVIS_AVAILABLE = True
            return True
        except ImportError:
            # Remove from path if it didn't help
            if resolved in sys.path:
                sys.path.remove(resolved)

    _OPENJARVIS_AVAILABLE = False
    return False


def is_openjarvis_available() -> bool:
    """Check if the OpenJarvis package can be imported and used."""
    if not _ensure_openjarvis_path():
        return False

    try:
        import openjarvis

        global _OPENJARVIS_VERSION
        _OPENJARVIS_VERSION = getattr(openjarvis, "__version__", "unknown")
        return True
    except ImportError:
        return False


def get_openjarvis_version() -> str:
    """Return the detected OpenJarvis version string."""
    if is_openjarvis_available():
        return _OPENJARVIS_VERSION
    return "not available"


# ═══════════════════════════════════════
#  Tool Discovery & Adapter
# ═══════════════════════════════════════

_OPENJARVIS_TOOL_NAMES: list[str] = []


def _list_openjarvis_tools() -> list[tuple[str, str]]:
    """Discover all registered OpenJarvis tools with descriptions.

    Returns list of (tool_name, description) tuples.
    """
    if not is_openjarvis_available():
        return []

    try:
        from openjarvis.core.registry import ToolRegistry
        import openjarvis.tools  # noqa: F401

        tools = []
        for key in ToolRegistry.keys():
            try:
                entry = ToolRegistry.get(key)
                # Try to get a description
                desc = ""
                if hasattr(entry, "spec"):  # It's a class
                    try:
                        spec = entry.spec
                        desc = getattr(spec, "description", "")
                    except (TypeError, Exception):
                        desc = ""
                elif callable(entry):
                    desc = getattr(entry, "__doc__", "") or ""

                tools.append((str(key), str(desc)[:100]))
            except Exception:
                continue

        global _OPENJARVIS_TOOL_NAMES
        _OPENJARVIS_TOOL_NAMES = [t[0] for t in tools]
        return tools
    except Exception as e:
        logger.warning(f"Failed to discover OpenJarvis tools: {e}")
        return []


def _oj_params_to_input_schema(parameters: dict[str, Any]) -> InputSchema:
    """Convert OpenJarvis JSON Schema parameters dict to PythonAI InputSchema."""
    props = parameters.get("properties", {})
    required_params = set(parameters.get("required", []))

    params: dict[str, Parameter] = {}
    for name, prop in props.items():
        param_type = prop.get("type", "string")
        description = prop.get("description", "")
        is_required = name in required_params
        enum = prop.get("enum")

        params[name] = Parameter(
            type=param_type,
            description=description,
            required=is_required,
            enum=enum,
            items=prop.get("items"),
            default=prop.get("default"),
        )

    return InputSchema(**params)


def _discover_oj_tool_instances() -> list[Any]:
    """Instantiate all available OpenJarvis tools.

    Returns list of instantiated BaseTool objects.
    """
    if not is_openjarvis_available():
        return []

    try:
        from openjarvis.mcp.server import MCPServer

        # MCPServer._auto_discover_tools() instantiates all built-in tools
        mcp = MCPServer()
        return mcp.get_tools()
    except Exception as e:
        logger.warning(f"Failed to auto-discover OJ tools via MCPServer: {e}")

    # Fallback: try direct instantiation of known tools
    tools = []
    known_tool_classes = [
        "openjarvis.tools.calculator.CalculatorTool",
        "openjarvis.tools.web_search.WebSearchTool",
        "openjarvis.tools.file_read.FileReadTool",
        "openjarvis.tools.think.ThinkTool",
        "openjarvis.tools.llm_tool.LLMTool",
        "openjarvis.tools.retrieval.RetrievalTool",
        "openjarvis.tools.knowledge_search.KnowledgeSearchTool",
        "openjarvis.tools.memory_manage.MemoryManageTool",
        "openjarvis.tools.shell_exec.ShellExecTool",
        "openjarvis.tools.git_tool.GitTool",
        "openjarvis.tools.code_interpreter.CodeInterpreterTool",
        "openjarvis.tools.browser.BrowserTool",
        "openjarvis.tools.text_to_speech.TextToSpeechTool",
        "openjarvis.tools.storage_tools.MemoryStoreTool",
        "openjarvis.tools.storage_tools.MemoryRetrieveTool",
        "openjarvis.tools.storage_tools.MemorySearchTool",
        "openjarvis.tools.storage_tools.MemoryIndexTool",
    ]

    for class_path in known_tool_classes:
        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            instance = cls()
            tools.append(instance)
        except Exception:
            continue

    return tools


class _OpenJarvisToolAdapter(Tool):
    """Adapter that wraps an OpenJarvis BaseTool as a PythonAI Tool.

    Translates between the two tool interfaces so OpenJarvis tools
    can be used seamlessly in PythonAI's ToolCallingEngine.
    """

    def __init__(self, oj_tool: Any):
        self._oj_tool = oj_tool
        spec = oj_tool.spec

        name = spec.name
        description = spec.description or f"OpenJarvis tool: {spec.name}"

        super().__init__(name, description)

        self._input_schema = _oj_params_to_input_schema(spec.parameters)
        self._readonly = spec.metadata.get("readOnlyHint", False) if isinstance(spec.metadata, dict) else False
        self._concurrency_safe = self._readonly
        self._destructive = spec.metadata.get("destructiveHint", False) if isinstance(spec.metadata, dict) else False
        self._oj_spec = spec
        self._category = spec.category

    def input_schema(self) -> InputSchema:
        return self._input_schema

    def call(self, input_data: dict[str, Any], context: ToolUseContext) -> ToolResult:
        """Execute the OpenJarvis tool and convert result to PythonAI ToolResult."""
        from openjarvis.core.types import ToolResult as OJToolResult

        try:
            result: OJToolResult = self._oj_tool.execute(**input_data)
            return ToolResult(
                data=result.content,
                error=None if result.success else f"Tool returned error: {result.content[:200]}",
            )
        except Exception as e:
            return ToolResult(
                data="",
                error=f"Tool execution failed: {e}",
            )

    def is_readonly(self, input_data: dict[str, Any] | None = None) -> bool:
        return self._readonly

    def is_concurrency_safe(self, input_data: dict[str, Any] | None = None) -> bool:
        return self._concurrency_safe

    def is_destructive(self, input_data: dict[str, Any] | None = None) -> bool:
        return self._destructive

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI tool calling format — pass through OJ's native schema."""
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": self._oj_spec.parameters,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["category"] = self._category
        base["source"] = "openjarvis"
        # Override with native OJ schema to avoid information loss
        base["input_schema"] = self._oj_spec.parameters
        return base


def discover_oj_tools() -> list[dict[str, Any]]:
    """Discover and return metadata for all available OpenJarvis tools.

    Returns:
        List of tool metadata dicts with name, description, category.
    """
    metadata = []
    for name, desc in _list_openjarvis_tools():
        metadata.append({
            "name": name,
            "description": desc[:100],
            "source": "openjarvis",
        })
    return metadata


def build_oj_tool_adapters() -> list[_OpenJarvisToolAdapter]:
    """Instantiate all OpenJarvis tools and wrap them as PythonAI Tool adapters.

    Returns:
        List of Tool instances wrapping OpenJarvis tools.
    """
    if not is_openjarvis_available():
        logger.warning("OpenJarvis not available — cannot build tool adapters")
        return []

    instances = _discover_oj_tool_instances()
    adapters = []

    for inst in instances:
        try:
            adapter = _OpenJarvisToolAdapter(inst)
            adapters.append(adapter)
            logger.debug(f"Adapted OJ tool: {inst.spec.name}")
        except Exception as e:
            logger.debug(f"Failed to adapt OJ tool {getattr(inst, 'tool_id', '?')}: {e}")

    return adapters


def register_oj_tools(registry: ToolRegistry | None = None) -> int:
    """Register all discovered OpenJarvis tools into PythonAI's ToolRegistry.

    Args:
        registry: Specific registry to register into (default: global singleton).

    Returns:
        Number of tools successfully registered.
    """
    if not is_openjarvis_available():
        logger.info("OpenJarvis not available — skipping tool registration")
        return 0

    r = registry or get_registry()
    adapters = build_oj_tool_adapters()
    count = 0

    for adapter in adapters:
        try:
            r.register(adapter)
            count += 1
        except Exception as e:
            logger.debug(f"Failed to register OJ tool '{adapter.name}': {e}")

    if count > 0:
        logger.info(f"Registered {count} OpenJarvis tools into PythonAI ToolRegistry")
    return count


# ═══════════════════════════════════════
#  Agent Bridge — Wrap OJ Agents
# ═══════════════════════════════════════

_OPENJARVIS_AGENT_NAMES: list[str] = []


def _list_openjarvis_agents() -> list[tuple[str, str]]:
    """Discover registered OJ agent types with descriptions.

    Returns list of (agent_name, description) tuples.
    """
    if not is_openjarvis_available():
        return []

    try:
        import openjarvis.agents  # noqa: F401
        from openjarvis.core.registry import AgentRegistry

        agents = []
        for key in AgentRegistry.keys():
            try:
                cls = AgentRegistry.get(key)
                desc = getattr(cls, "__doc__", "") or getattr(cls, "agent_id", "") or ""
                agents.append((str(key), str(desc).strip()[:100]))
            except Exception:
                continue

        global _OPENJARVIS_AGENT_NAMES
        _OPENJARVIS_AGENT_NAMES = [a[0] for a in agents]
        return agents
    except Exception as e:
        logger.warning(f"Failed to discover OpenJarvis agents: {e}")
        return []


def discover_oj_agents() -> list[dict[str, Any]]:
    """Discover and return metadata for all available OpenJarvis agent types.

    Returns:
        List of agent metadata dicts.
    """
    metadata = []
    for name, desc in _list_openjarvis_agents():
        metadata.append({
            "name": name,
            "description": desc[:100],
            "source": "openjarvis",
        })
    return metadata


def create_oj_agent_callable(agent_name: str) -> Any:
    """Create a callable function that runs an OpenJarvis agent.

    The returned function matches PythonAI's agent signature:
        fn(task: GenerationTask, session_id: str = "default") -> dict[str, Any]

    This allows OJ agents to be registered into PythonAI's ALL_AGENTS dict.

    Args:
        agent_name: The registered OJ agent type name (e.g. "orchestrator",
                   "operative", "simple", "deep_research", "monitor_operative").

    Returns:
        A callable function compatible with PythonAI's agent system.
    """
    if not is_openjarvis_available():
        raise ImportError("OpenJarvis is not available")

    try:
        import openjarvis.agents  # noqa: F401
        from openjarvis.core.registry import AgentRegistry

        if not AgentRegistry.contains(agent_name):
            available = ", ".join(AgentRegistry.keys())
            raise ValueError(f"Unknown OJ agent: '{agent_name}'. Available: {available}")

        agent_cls = AgentRegistry.get(agent_name)

        def _run_oj_agent(task: Any, session_id: str = "default") -> dict[str, Any]:
            """Run the OpenJarvis agent with the given task."""
            try:
                from openjarvis.sdk import Jarvis

                # Instantiate Jarvis SDK
                with Jarvis() as jarvis:
                    # Build tools if the agent accepts them
                    agent_kwargs: dict[str, Any] = {}
                    if getattr(agent_cls, "accepts_tools", False):
                        from openjarvis.mcp.server import MCPServer

                        mcp = MCPServer()
                        agent_kwargs["tools"] = mcp.get_tools()

                    # Run the agent
                    result = jarvis.ask_full(
                        str(task.prompt if hasattr(task, "prompt") else task),
                        agent=agent_name,
                        **agent_kwargs,
                    )
                    return {"output": result.get("content", ""), "turns": result.get("turns", 0)}

            except Exception as e:
                logger.error(f"OJ agent '{agent_name}' failed: {e}")
                return {"output": f"[OpenJarvis Agent '{agent_name}' failed]: {e}", "turns": 0}

        _run_oj_agent.__name__ = f"run_openjarvis_{agent_name}"
        _run_oj_agent.__doc__ = f"Run the OpenJarvis '{agent_name}' agent via the bridge."

        return _run_oj_agent

    except Exception as e:
        raise ImportError(f"Failed to create OJ agent callable: {e}")


def get_oj_agents() -> dict[str, Any]:
    """Get a dict of OpenJarvis agent callables compatible with PythonAI's ALL_AGENTS.

    Returns:
        Dict mapping agent names to callable functions:
        {"oj_orchestrator": <callable>, "oj_operative": <callable>, ...}
    """
    agents: dict[str, Any] = {}
    for name, _ in _list_openjarvis_agents():
        try:
            agents[f"oj_{name}"] = create_oj_agent_callable(name)
        except Exception as e:
            logger.debug(f"Failed to create agent callable for '{name}': {e}")
    return agents


# ═══════════════════════════════════════
#  Consolidated Engine Builder
# ═══════════════════════════════════════

def build_oj_engine(
    model: str = "",
    max_tool_rounds: int = 25,
    register_tools: bool = True,
) -> Any:
    """Build a PythonAI ToolCallingEngine pre-configured with OJ tools.

    Args:
        model: Default model to use (empty = auto-detect).
        max_tool_rounds: Maximum tool-calling loop iterations.
        register_tools: If True, registers OJ tools into the global registry.

    Returns:
        Configured ToolCallingEngine instance.
    """
    from src.core.executor import ToolCallingEngine

    if register_tools:
        register_oj_tools()

    return ToolCallingEngine(
        model=model,
        max_tool_rounds=max_tool_rounds,
    )


# ═══════════════════════════════════════
#  Ecosystem Manager Integration
# ═══════════════════════════════════════


def get_oj_status() -> dict[str, Any]:
    """Get comprehensive OpenJarvis status for the ecosystem dashboard.

    Returns:
        Dict with installation status, version, tools, agents.
    """
    if not is_openjarvis_available():
        return {
            "available": False,
            "version": "not available",
            "tools": [],
            "agents": [],
            "error": "OpenJarvis package not installed",
        }

    return {
        "available": True,
        "version": _OPENJARVIS_VERSION,
        "tools": [{"name": n, "description": d} for n, d in _list_openjarvis_tools()],
        "agents": [{"name": n, "description": d} for n, d in _list_openjarvis_agents()],
        "tool_count": len(_OPENJARVIS_TOOL_NAMES),
        "agent_count": len(_OPENJARVIS_AGENT_NAMES),
    }


def auto_register() -> int:
    """Auto-register all OpenJarvis capabilities into PythonAI.

    Called during ecosystem initialization. Registers tools and
    returns the count.

    Returns:
        Number of tools registered.
    """
    return register_oj_tools()


# ═══════════════════════════════════════
#  CLI Helper
# ═══════════════════════════════════════

if __name__ == "__main__":
    """CLI entry point for testing OpenJarvis integration."""
    import json

    available = is_openjarvis_available()
    print(f"OpenJarvis available: {available}")

    if available:
        print(f"Version: {get_openjarvis_version()}")
        tools = discover_oj_tools()
        print(f"\nDiscovered {len(tools)} tools:")
        for t in tools:
            print(f"  - {t['name']}: {t['description'][:60]}")

        agents = discover_oj_agents()
        print(f"\nDiscovered {len(agents)} agents:")
        for a in agents:
            print(f"  - {a['name']}: {a['description'][:60]}")

        count = register_oj_tools()
        print(f"\nRegistered {count} tools into PythonAI ToolRegistry")

        status = get_oj_status()
        print(f"\nFull status:\n{json.dumps(status, indent=2, default=str)}")
    else:
        print("Install OpenJarvis to use the bridge.")
