"""
PythonAI Web UI — Agent Swarm Workspace
========================================
Interactive workspace to plan, execute, and monitor the multi-agent swarm
(AgentOrchestrator, Coder, Researcher, and Reviewer sub-agents) in real-time.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.agents import AgentOrchestrator  # noqa: E402
from src.core.providers import ProfileManager  # noqa: E402
from src.core.providers import get_registry as get_model_registry  # noqa: E402
from src.core.registry import get_registry as get_tool_registry  # noqa: E402
from src.core.tools import register_all_tools  # noqa: E402
from src.data.apikeys import active_providers  # noqa: E402

# Import utils — support both package and script contexts
try:
    from ..utils import inject_dashboard_css  # noqa: E402  # noqa: E402
except ImportError:
    from src.webui.utils import inject_dashboard_css


# ════════════════════════════════════════
# SESSION STATE DEFAULTS
# ════════════════════════════════════════


def init_workspace_state() -> None:
    """Initialize session state defaults for the agent workspace."""
    defaults = {
        "workspace_prompt": "",
        "workspace_running": False,
        "workspace_logs": [],
        "workspace_plan": [],
        "workspace_synthesis": "",
        "workspace_summary": "",
        "workspace_results": {},
        "workspace_total_tools": 0,
        "workspace_elapsed_time": 0.0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render() -> None:
    """Render the main Agent Swarm Workspace page."""
    inject_dashboard_css()
    init_workspace_state()

    # Custom styling for Workspace page
    st.markdown(
        """
        <style>
        .agent-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
            color: #fff;
            text-transform: uppercase;
        }
        .badge-coder { background-color: #2b8a3e; }
        .badge-researcher { background-color: #1c7ed6; }
        .badge-reviewer { background-color: #d6336c; }
        .badge-mcp { background-color: #e8590c; }
        .badge-orchestrator { background-color: #7048e8; }

        .plan-step-card {
            background: rgba(28, 28, 40, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 0.8rem 1rem;
            margin-bottom: 0.5rem;
        }
        .step-pending { border-left: 4px solid #868e96; }
        .step-running { border-left: 4px solid #1c7ed6; }
        .step-done { border-left: 4px solid #2b8a3e; }
        .step-failed { border-left: 4px solid #fa5252; }

        .synthesis-card {
            background: rgba(20, 20, 30, 0.85);
            border: 1px solid rgba(0, 210, 255, 0.2);
            border-radius: 12px;
            padding: 1.5rem;
            margin-top: 1.5rem;
            box-shadow: 0 4px 25px rgba(0, 210, 255, 0.05);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="main-header">'
        "<h1>🔮 Agent Swarm Workspace</h1>"
        '<p class="subtitle">Orchestrate a swarm of specialized AI agents working together to solve complex tasks</p>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="divider-custom" />', unsafe_allow_html=True)

    # ── Sidebar Config ──
    _render_sidebar_config()

    # ── Main Area Layout ──
    left_col, right_col = st.columns([7, 5])

    with left_col:
        st.markdown("### 🎯 Dispatch Swarm Goal")
        st.markdown(
            "Enter a complex task that requires planning, code implementation, researching, reviewing, or external tool execution."
        )

        prompt_input = st.text_area(
            "What do you want the Swarm to do?",
            placeholder="e.g., Search the files in this directory for active API keys, review the codebase, and write a summary report of any security issues.",
            height=120,
            key="workspace_prompt_input",
            disabled=st.session_state.workspace_running,
        )

        col1, col2 = st.columns(2)
        with col1:
            start_btn = st.button(
                "🚀 Run Swarm",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.workspace_running or not prompt_input.strip(),
            )
        with col2:
            clear_btn = st.button(
                "🧹 Clear Results",
                type="secondary",
                use_container_width=True,
                disabled=st.session_state.workspace_running,
            )

        if clear_btn:
            st.session_state.workspace_logs = []
            st.session_state.workspace_plan = []
            st.session_state.workspace_synthesis = ""
            st.session_state.workspace_summary = ""
            st.session_state.workspace_results = {}
            st.session_state.workspace_elapsed_time = 0.0
            st.rerun()

        # Handle Execution
        if start_btn and prompt_input.strip():
            st.session_state.workspace_running = True
            st.session_state.workspace_logs = []
            st.session_state.workspace_plan = []
            st.session_state.workspace_synthesis = ""
            st.session_state.workspace_summary = ""
            st.session_state.workspace_results = {}
            st.session_state.workspace_elapsed_time = 0.0
            st.rerun()

        if st.session_state.workspace_running:
            _execute_swarm(prompt_input.strip())

        # Render Final Synthesis if available
        if st.session_state.workspace_synthesis:
            st.markdown('<div class="synthesis-card">', unsafe_allow_html=True)
            st.markdown("### 👑 Synthesized Solution")
            st.markdown(st.session_state.workspace_synthesis)
            st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
        # Show dynamic Plan Checklist
        st.markdown("### 📋 Swarm Plan & Status")
        if st.session_state.workspace_plan:
            for step in st.session_state.workspace_plan:
                if step.status == "pending":
                    cls = "step-pending"
                    status_lbl = "⏳ Pending"
                elif step.status == "running":
                    cls = "step-running"
                    status_lbl = "⚡ Running..."
                elif step.status == "done":
                    cls = "step-done"
                    status_lbl = "✅ Completed"
                else:
                    cls = "step-failed"
                    status_lbl = "❌ Failed"

                agent_cls = "badge-orchestrator"
                if "coder" in step.agent_name.lower():
                    agent_cls = "badge-coder"
                elif "research" in step.agent_name.lower():
                    agent_cls = "badge-researcher"
                elif "review" in step.agent_name.lower():
                    agent_cls = "badge-reviewer"
                elif "mcp" in step.agent_name.lower():
                    agent_cls = "badge-mcp"

                st.markdown(
                    f"""<div class="plan-step-card {cls}">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span class="agent-badge {agent_cls}">{step.agent_name}</span>
                        <span style="font-size:0.8rem;font-weight:600;">{status_lbl}</span>
                    </div>
                    <div style="margin-top:0.4rem;font-size:0.9rem;">{step.task}</div>
                    {f'<div style="font-size:0.75rem;color:rgba(255,255,255,0.4);margin-top:0.2rem;">Depends on: {", ".join(step.depends_on)}</div>' if step.depends_on else ""}
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No active swarm goal dispatched. Trigger 'Run Swarm' to see the planned steps.")

        # Show agent results / stats
        if st.session_state.workspace_summary:
            st.markdown("### 📊 Agent Swarm Stats")
            with st.expander("Show Execution Summary", expanded=True):
                st.code(st.session_state.workspace_summary)


def _render_sidebar_config() -> None:
    """Render the configuration options inside the sidebar."""
    with st.sidebar:
        st.markdown("### ⚙️ Swarm Configuration")

        # Provider routing profile setup
        profile_mgr = ProfileManager()
        current_profile = profile_mgr.load()

        st.markdown("**LLM Provider & Model**")
        available = active_providers()

        # Build selection list
        options = ["auto"] + sorted(available)
        current_prov = current_profile.provider if current_profile else "auto"
        if current_prov not in options:
            options.append(current_prov)

        selected_prov = st.selectbox(
            "Routing Profile",
            options=options,
            index=options.index(current_prov) if current_prov in options else 0,
            help="Select the LLM provider to route planning and agent tasks to, or 'auto' for dynamic capability routing.",
        )

        selected_model = ""
        if selected_prov != "auto":
            # List known models for this provider
            model_reg = get_model_registry()
            provider_models = [m.id for m in model_reg.list_models(selected_prov)]

            # Fetch default model if known
            default_model = ""
            p_desc = model_reg.get_provider(selected_prov)
            if p_desc:
                default_model = p_desc.default_model

            if default_model and default_model not in provider_models:
                provider_models.insert(0, default_model)

            current_model = (
                current_profile.model if current_profile and current_profile.provider == selected_prov else ""
            )
            if current_model and current_model not in provider_models:
                provider_models.insert(0, current_model)

            selected_model = st.selectbox(
                "Model",
                options=provider_models,
                index=provider_models.index(current_model) if current_model in provider_models else 0,
            )

        # Strategy and goal configuration
        current_strategy = current_profile.strategy if current_profile else "auto"
        strategy_options = ["auto", "cost", "speed", "quality"]
        selected_strategy = st.selectbox(
            "Routing Strategy",
            options=strategy_options,
            index=strategy_options.index(current_strategy) if current_strategy in strategy_options else 0,
        )

        current_goal = current_profile.goal if current_profile else "coding"
        goal_options = ["coding", "latency", "balanced"]
        selected_goal = st.selectbox(
            "Routing Goal",
            options=goal_options,
            index=goal_options.index(current_goal) if current_goal in goal_options else 0,
        )

        if st.button("Save Profile Settings", use_container_width=True):
            profile_mgr.set_provider(
                provider=selected_prov,
                model=selected_model,
                strategy=selected_strategy,
                goal=selected_goal,
            )
            st.toast("Profile settings updated successfully!", icon="✅")
            st.rerun()

        st.divider()

        st.markdown("**Swarm Tunables**")
        max_concurrent = st.slider("Max Concurrent Agents", 1, 8, value=4)
        max_steps = st.slider("Max Agent Steps", 5, 20, value=10)
        max_tool_calls = st.slider("Max Tool Calls per Agent", 1, 10, value=4)
        verbose = st.checkbox("Verbose Logging", value=True)

        st.session_state["swarm_max_concurrent"] = max_concurrent
        st.session_state["swarm_max_steps"] = max_steps
        st.session_state["swarm_max_tool_calls"] = max_tool_calls
        st.session_state["swarm_verbose"] = verbose


def _execute_swarm(prompt: str) -> None:
    """Execute the AgentOrchestrator in a background thread and stream progress."""
    # Ensure tool registry is loaded and tools are registered
    tool_reg = get_tool_registry()
    try:
        register_all_tools(tool_reg)
    except Exception:
        pass

    # Create thread-safe queue
    log_queue = queue.Queue()

    def on_stream(msg: str) -> None:
        log_queue.put(msg)

    # Instantiate Orchestrator
    orchestrator = AgentOrchestrator(
        registry=tool_reg,
        on_stream=on_stream,
        max_concurrent=st.session_state.get("swarm_max_concurrent", 4),
        verbose=st.session_state.get("swarm_verbose", True),
    )

    # Tweak default agent parameters to match UI tunables
    for agent in orchestrator._swarm.agents.values():
        agent.max_steps = st.session_state.get("swarm_max_steps", 10)
        agent.max_tool_calls = st.session_state.get("swarm_max_tool_calls", 4)

    # Thread container to store outputs
    outputs = {"synthesis": "", "summary": "", "plan": [], "error": "", "success": False}
    start_time = time.time()

    def run_wrapper() -> None:
        try:
            # First planning phase
            orchestrator.plan_task(prompt)
            outputs["plan"] = list(orchestrator.plan)

            # Execution phase
            synthesis = orchestrator.run(prompt)
            outputs["synthesis"] = synthesis
            outputs["summary"] = orchestrator.summary()
            outputs["plan"] = list(orchestrator.plan)
            outputs["success"] = True
        except Exception as e:
            import traceback

            outputs["error"] = f"Execution error: {e}\n{traceback.format_exc()}"
            outputs["success"] = False

    # Start Orchestrator Thread
    orch_thread = threading.Thread(target=run_wrapper, name="OrchestratorThread")
    orch_thread.start()

    # Create UI status container for streaming logs
    status_container = st.status("🔮 Orchestrating Agent Swarm...", expanded=True)
    st.empty()

    # Loop while thread runs
    while orch_thread.is_alive():
        # Drain queue logs
        while not log_queue.empty():
            try:
                log_msg = log_queue.get_nowait()
                st.session_state.workspace_logs.append(log_msg)
                status_container.write(log_msg)
            except queue.Empty:
                break

        # Dynamically update the plan state
        if orchestrator.plan:
            st.session_state.workspace_plan = list(orchestrator.plan)

        time.sleep(0.1)

    # Final drain of logs
    while not log_queue.empty():
        try:
            log_msg = log_queue.get_nowait()
            st.session_state.workspace_logs.append(log_msg)
            status_container.write(log_msg)
        except queue.Empty:
            break

    # Record elapsed time
    elapsed = time.time() - start_time
    st.session_state.workspace_elapsed_time = elapsed

    # Finalize execution state
    st.session_state.workspace_running = False

    if outputs["success"]:
        st.session_state.workspace_synthesis = outputs["synthesis"]
        st.session_state.workspace_summary = outputs["summary"]
        st.session_state.workspace_plan = outputs["plan"]
        status_container.update(
            label=f"✅ Swarm completed task in {elapsed:.1f}s!",
            state="complete",
            expanded=False,
        )
        st.balloons()
    else:
        status_container.update(label="❌ Swarm execution failed!", state="error", expanded=True)
        st.error(outputs["error"])
        st.session_state.workspace_synthesis = (
            "Failed to synthesize a solution due to errors. Check execution logs above."
        )
        st.session_state.workspace_summary = "Failed."

    # Rerun to cleanly draw the final synthesis outside the active runner loop
    st.rerun()
