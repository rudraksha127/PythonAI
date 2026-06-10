"""
Streamlit Web UI for the PythonAI RAG Assistant + Dataset Generator.

Usage:
    streamlit run src/webui/app.py
    python -m src.cli webui
"""

from __future__ import annotations

import io
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.apikeys import (
    ALL_PROVIDERS,
    PROVIDER_LABELS,
    active_providers,
    delete_key,
    export_dotenv,
    get_key,
    list_keys,
    set_key,
)
from src.rag.models import (
    DEFAULT_MODEL,
    get_model_info,
    is_model_available,
    list_configured_models,
    list_ollama_models,
    resolve_model,
)
from src.rag.rag_engine import (
    CHUNKS_FILE,
    DB_PATH,
    get_answer,
    load_or_build_db,
    print_stats,
    save_conversation,
)


# ════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════

st.set_page_config(
    page_title="PythonAI",
    page_icon="[PYTHON]",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──

st.markdown(
    """
<style>
/* Main chat area */
.chat-container {
    max-width: 900px;
    margin: 0 auto;
}
.stChatMessage {
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.8rem;
}
[data-testid="stChatMessageContent"] p {
    margin-bottom: 0.5rem;
    line-height: 1.6;
}
[data-testid="stChatMessageContent"] code {
    border-radius: 6px;
    padding: 0.15em 0.4em;
    font-size: 0.9em;
}
[data-testid="stChatMessageContent"] pre {
    border-radius: 8px;
    padding: 1rem;
    margin: 0.8rem 0;
    border: 1px solid rgba(128,128,128,0.2);
}
/* Sidebar navigation */
.sidebar-nav {
    margin-bottom: 1rem;
}
/* Header */
.main-header {
    text-align: center;
    padding: 0.5rem 0 1rem 0;
}
.main-header h1 {
    font-size: 2.2rem;
    margin-bottom: 0.2rem;
}
.main-header .subtitle {
    color: #888;
    font-size: 0.95rem;
}
/* Stats box */
.stats-box {
    font-family: "SF Mono", "Consolas", monospace;
    font-size: 0.85rem;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid rgba(128,128,128,0.2);
    white-space: pre-wrap;
}
/* Divider */
.divider-custom {
    margin: 0.5rem 0 1rem 0;
    border: none;
    border-top: 1px solid rgba(128,128,128,0.15);
}
/* API key table */
.key-table {
    font-family: "SF Mono", "Consolas", monospace;
    font-size: 0.85rem;
}
.key-ok { color: #0c0; }
.key-missing { color: #888; }
/* Gen status */
.gen-progress {
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid rgba(128,128,128,0.2);
    margin: 1rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)


# ════════════════════════════════════════
# SESSION STATE DEFAULTS
# ════════════════════════════════════════

_RAG_DEFAULTS: dict[str, Any] = {
    "history": [],
    "last_answer": "",
    "last_docs": [],
    "db_ready": False,
    "show_stats": False,
    "stats_output": "",
    "collection": None,
    "embedder": None,
    "bm25": None,
    "corpus_texts": None,
    "chunks_file": None,
    "rag_model": DEFAULT_MODEL,
    "model_info": get_model_info(DEFAULT_MODEL),
}

_GEN_DEFAULTS: dict[str, Any] = {
    "gen_running": False,
    "gen_done": False,
    "gen_progress": {},
    "gen_results": "",
    "gen_output_file": "",
    "gen_pairs_count": 0,
}

_UI_DEFAULTS: dict[str, Any] = {
    "page": "RAG Chat",
    "api_key_message": "",
    "gen_log": [],
}

for key, val in {**_RAG_DEFAULTS, **_GEN_DEFAULTS, **_UI_DEFAULTS}.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ════════════════════════════════════════
# CACHED DB RESOURCE (RAG)
# ════════════════════════════════════════

@st.cache_resource(show_spinner="[OK] Loading RAG database...")
def init_db(force_rebuild: bool = False) -> tuple[Any, Any, Any, list[str], Path]:
    return load_or_build_db(force_rebuild=force_rebuild)


# ════════════════════════════════════════
# GENERATOR WORKER
# ════════════════════════════════════════

def _run_generation(max_chunks: int, data_types: list[str], output_name: str) -> dict[str, Any]:
    """Run dataset generation via a subprocess and return results.

    Using subprocess avoids fragile monkey-patching of generator internals
    and keeps the Streamlit UI responsive via captured stdout.
    """
    import subprocess
    import json

    log: list[str] = []

    def _log(msg: str) -> None:
        log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        st.session_state.gen_log = log

    try:
        _log("Checking API keys...")
        from src.data.apikeys import resolve_all
        resolved = resolve_all()
        if not resolved:
            _log("[FAIL] No API keys found. Set keys via CLI or Web UI first.")
            return {"success": False, "error": "No API keys", "log": log}

        _log(f"Active APIs: {list(resolved.keys())}")

        # Build a script that runs the generator and prints JSON result at the end
        script = (
            "import sys, json\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))\n"
            "from src.data.apikeys import resolve_all\n"
            "resolved = resolve_all()\n"
            "if not resolved:\n"
            "    print(json.dumps({'success': False, 'error': 'No keys'}))\n"
            "    sys.exit(1)\n"
            "import src.data.generator as gen\n"
            f"gen.KEYS.update(resolved)\n"
            f"gen.OUTPUT = ROOT / 'data' / 'training' / '{output_name}'\n"
            "try:\n"
            "    gen.main()\n"
            "    print(json.dumps({'success': True, 'output': str(gen.OUTPUT)}))\n"
            "except SystemExit as e:\n"
            "    if e.code != 0:\n"
            "        print(json.dumps({'success': False, 'error': str(e)}))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'success': False, 'error': str(e)}))\n"
        )

        _log("Launching generator (this may take several minutes)...")
        result = subprocess.run(
            ["python", "-c", script],
            cwd=str(ROOT.parent if ROOT.name == "PythonAI" else ROOT),
            capture_output=True, text=True, timeout=3600,
        )

        # Parse the last JSON line from stdout
        output_lines = result.stdout.strip().split("\n")
        result_json = {}
        for line in reversed(output_lines):
            try:
                result_json = json.loads(line)
                break
            except (json.JSONDecodeError, ValueError):
                continue

        # Log all output
        for line in output_lines:
            _log(line)
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                _log(f"[STDERR] {line}")

        if result_json.get("success"):
            output_path = result_json.get("output", f"data/training/{output_name}")
            _log(f"[OK] Generation complete! Output: {output_path}")
            return {
                "success": True,
                "output": output_path,
                "log": log,
                "pairs": result_json.get("pairs", 0),
                "elapsed_min": result_json.get("elapsed_min", 0),
            }
        else:
            return {"success": False, "error": result_json.get("error", "Unknown"), "log": log}

    except subprocess.TimeoutExpired:
        _log("[FAIL] Generation timed out after 60 minutes.")
        return {"success": False, "error": "Timeout", "log": log}
    except Exception as exc:
        _log(f"[FAIL] {exc}")
        import traceback
        _log(traceback.format_exc())
        return {"success": False, "error": str(exc), "log": log}


# ════════════════════════════════════════
# SIDEBAR — NAVIGATION
# ════════════════════════════════════════

with st.sidebar:
    st.markdown("## [PYTHON] PythonAI")
    st.divider()

    # ── Navigation ──
    pages = ["RAG Chat", "Agent Workspace", "Dataset Generation", "Dashboard Home", "Tool System", "Provider Routing", "MCP Servers", "ForgeAI Dashboard"]
    page = st.radio(
        "Navigation",
        pages,
        index=pages.index(st.session_state.page) if st.session_state.page in pages else 0,
        key="page",
        label_visibility="collapsed",
    )

    st.divider()

    # ── Contextual sidebar content ──
    if page == "RAG Chat":
        # Model selection
        st.markdown("### Model")
        configured = list_configured_models()
        available_in_ollama = list_ollama_models()

        model_names = list(configured.keys())
        current_model = st.session_state.get("rag_model", DEFAULT_MODEL)

        if current_model not in model_names:
            model_names.insert(0, current_model)

        selected_model = st.selectbox(
            "Ollama Model",
            options=model_names,
            index=model_names.index(current_model) if current_model in model_names else 0,
            format_func=lambda m: f"{m}  [OK]" if m in available_in_ollama else f"{m}  (not pulled)",
            key="model_selector",
            label_visibility="collapsed",
        )

        if selected_model != current_model:
            st.session_state.rag_model = selected_model
            st.session_state.model_info = get_model_info(selected_model)
            if selected_model not in available_in_ollama:
                st.warning(f"Model '{selected_model}' not found in Ollama. Run: ollama pull {selected_model}")
            st.rerun()

        if st.session_state.get("model_info"):
            st.caption(st.session_state.model_info.get("description", ""))

        st.divider()
        st.caption("**Search:** Hybrid (Dense + BM25)")

        st.markdown("### Settings")

        use_qe = st.checkbox(
            "Query Expansion", value=False,
            help="Generate alternative phrasings for broader document retrieval.",
        )
        use_mmr = st.checkbox(
            "MMR Diversity", value=False,
            help="Maximum Marginal Relevance — avoid redundant results.",
        )
        mmr_lambda = st.slider(
            "MMR Lambda", 0.0, 1.0, 0.7, 0.05,
            help="Higher = more relevance-focused; lower = more diversity-focused.",
            disabled=not use_mmr,
        )
        no_exec = st.checkbox(
            "Skip Code Execution", value=False,
            help="Do not verify generated code examples.",
        )
        exec_timeout = st.number_input("Exec Timeout (s)", 1, 30, 5)
        version_filter = st.text_input("Python Version", "", placeholder="e.g. 3.10")
        category_filter = st.text_input("Category", "", placeholder="e.g. library, howto")

        st.divider()
        st.markdown("### Actions")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Rebuild DB", use_container_width=True):
                st.cache_resource.clear()
                for key in ("db_ready", "collection", "embedder", "bm25", "corpus_texts", "chunks_file"):
                    st.session_state[key] = None if key != "db_ready" else False
                st.rerun()
        with col2:
            if st.button("View Stats", use_container_width=True):
                st.session_state.show_stats = True
                st.rerun()

        if st.button("Clear Chat", use_container_width=True, type="secondary"):
            st.session_state.history = []
            st.session_state.last_answer = ""
            st.session_state.last_docs = []
            st.rerun()

        st.divider()
        st.markdown("### Database")
        if DB_PATH.exists():
            st.success("Database ready")
        else:
            st.warning("DB not found — will build on first query")

        if st.session_state.history:
            if st.button("Save Conversation", use_container_width=True):
                save_conversation(st.session_state.history)
                st.toast("Conversation saved!", icon="[OK]")

    elif page == "Dataset Generation":
        st.caption("Manage API keys and generate SFT training datasets.")

        # ── API Key quick status ──
        st.markdown("### API Key Status")
        active_set = set(active_providers())
        for prov in sorted(ALL_PROVIDERS):
            label = PROVIDER_LABELS.get(prov, prov)
            if prov in active_set:
                st.markdown(f"- [OK] **{label}**")
            else:
                st.markdown(f"-  **{label}**")


# ════════════════════════════════════════
# DYNAMIC PAGE ROUTING
# ════════════════════════════════════════

if page == "Dashboard Home":
    from src.webui.views.dashboard_home import render as render_home
    render_home()

elif page == "Agent Workspace":
    from src.webui.views.agent_workspace import render as render_agent_workspace
    render_agent_workspace()

elif page == "Tool System":
    from src.webui.views.tools_dashboard import render as render_tools
    render_tools()

elif page == "Provider Routing":
    from src.webui.views.providers_dashboard import render as render_providers
    render_providers()

elif page == "MCP Servers":
    from src.webui.views.mcp_dashboard import render as render_mcp
    render_mcp()

elif page == "ForgeAI Dashboard":
    from src.webui.views.forge_dashboard import render as render_forge
    render_forge()

elif page == "RAG Chat":

    st.markdown(
        '<div class="main-header">'
        "<h1>[PYTHON] PythonAI — RAG Assistant</h1>"
        f'<p class="subtitle">Powered by <strong>{st.session_state.get("rag_model", DEFAULT_MODEL)}</strong> · '
        "Hybrid Search (Dense + BM25) · Offline</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="divider-custom" />', unsafe_allow_html=True)

    # Stats display
    if st.session_state.show_stats:
        with st.spinner("Loading database statistics..."):
            try:
                coll, emb, bm, corp, cfile = init_db()
                buf = io.StringIO()
                old_out = sys.stdout
                sys.stdout = buf
                print_stats(coll, cfile)
                sys.stdout = old_out
                st.session_state.stats_output = buf.getvalue()
            except Exception as exc:
                st.error(f"Failed to load stats: {exc}")
                st.session_state.stats_output = ""
        st.session_state.show_stats = False

    if st.session_state.stats_output:
        with st.expander("Database Statistics", expanded=True):
            st.markdown(
                f'<div class="stats-box">{st.session_state.stats_output}</div>',
                unsafe_allow_html=True,
            )
        if st.button("Close Stats"):
            st.session_state.stats_output = ""
            st.rerun()

    # DB initialization
    if not st.session_state.db_ready:
        try:
            with st.spinner("[OK] Initializing RAG database (first load may take a moment)..."):
                coll, emb, bm, corp, cfile = init_db()
            st.session_state.collection = coll
            st.session_state.embedder = emb
            st.session_state.bm25 = bm
            st.session_state.corpus_texts = corp
            st.session_state.chunks_file = cfile
            st.session_state.db_ready = True
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to initialize database: {exc}")
            st.info(
                "Make sure Ollama is running and the ChromaDB database exists. "
                "Try running `python -m src.rag.rag_engine --rebuild` from the terminal first."
            )
            st.stop()

    # Chat messages
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("docs"):
                    with st.expander("Sources", expanded=False):
                        for doc in msg["docs"]:
                            title = doc.get("title", "Untitled")
                            ver = doc.get("version", "?")
                            cat = doc.get("category", "?")
                            num = doc.get("citation_num", "?")
                            text = doc.get("text", "")
                            snippet = text[:350] + "..." if len(text) > 350 else text
                            st.markdown(f"**[{num}]** {title}  _— v{ver}, {cat}_")
                            st.caption(snippet)

    # Chat input
    if prompt := st.chat_input("Ask a Python question..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.history.append({"role": "user", "content": prompt})

        ctx_history = [
            m for m in st.session_state.history[:-1]
            if m["role"] in ("user", "assistant")
        ][-20:]

        with st.chat_message("assistant"):
            rag_model = st.session_state.get("rag_model", DEFAULT_MODEL)
            with st.spinner(f"Thinking... (model: {rag_model})"):
                try:
                    answer, docs = get_answer(
                        prompt,
                        st.session_state.collection,
                        st.session_state.embedder,
                        ctx_history,
                        bm25=st.session_state.bm25,
                        corpus_texts=st.session_state.corpus_texts,
                        use_query_expansion=use_qe,
                        use_mmr=use_mmr,
                        mmr_lambda=mmr_lambda,
                        no_exec=no_exec,
                        exec_timeout=exec_timeout,
                        version_filter=version_filter,
                        category_filter=category_filter,
                        model=rag_model,
                    )

                    st.markdown(answer)

                    if docs:
                        with st.expander("Sources", expanded=True):
                            for doc in docs:
                                title = doc.get("title", "Untitled")
                                ver = doc.get("version", "?")
                                cat = doc.get("category", "?")
                                num = doc.get("citation_num", "?")
                                text = doc.get("text", "")
                                snippet = text[:350] + "..." if len(text) > 350 else text
                                st.markdown(f"**[{num}]** {title}  _— v{ver}, {cat}_")
                                st.caption(snippet)

                    st.session_state.last_answer = answer
                    st.session_state.last_docs = docs
                    st.session_state.history.append(
                        {"role": "assistant", "content": answer, "docs": docs}
                    )
                    st.rerun()

                except Exception as exc:
                    st.error(f"Error generating answer: {exc}")
                    import traceback
                    st.code(traceback.format_exc())

    # Welcome hint
    if not st.session_state.history:
        st.info(
            "**Welcome!** Ask any Python question to start.\n\n"
            "Examples:\n"
            "- *What is the difference between a list and a tuple?*\n"
            "- *How do async/await work in Python?*\n"
            "- *Explain decorators with a code example*"
        )


# ════════════════════════════════════════
# MAIN AREA — DATASET GENERATION
# ════════════════════════════════════════

elif page == "Dataset Generation":

    st.markdown(
        '<div class="main-header">'
        "<h1>[PYTHON] PythonAI — Dataset Generator</h1>"
        "<p class=\"subtitle\">Generate SFT training data using 10+ API providers</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="divider-custom" />', unsafe_allow_html=True)

    # ── API Key Management Section ──
    with st.expander("API Key Management", expanded=True):
        st.markdown("Set, view, or delete API keys for your preferred providers.")

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("**Set API Key**")
            set_prov = st.selectbox(
                "Provider",
                options=sorted(ALL_PROVIDERS.keys()),
                format_func=lambda p: PROVIDER_LABELS.get(p, p),
                key="set_provider",
                label_visibility="collapsed",
            )
            set_key_val = st.text_input(
                "API Key",
                type="password",
                placeholder=f"Enter {PROVIDER_LABELS.get(set_prov, set_prov)} API key...",
                key="set_key_input",
                label_visibility="collapsed",
            )
            if st.button("Save Key", use_container_width=True, type="primary"):
                if set_key_val:
                    result = set_key(set_prov, set_key_val)
                    if result["success"]:
                        st.session_state.api_key_message = f"[OK] Key saved for '{result['provider']}'"
                        st.rerun()
                    else:
                        st.error(result["error"])
                else:
                    st.warning("Enter an API key first.")

            if st.session_state.api_key_message:
                st.success(st.session_state.api_key_message)

        with col_right:
            st.markdown("**Delete / Export Keys**")
            del_prov = st.selectbox(
                "Delete key for",
                options=sorted(ALL_PROVIDERS.keys()),
                format_func=lambda p: PROVIDER_LABELS.get(p, p),
                key="del_provider",
                label_visibility="collapsed",
            )
            if st.button("Delete Key", use_container_width=True):
                result = delete_key(del_prov)
                if result["success"]:
                    st.success(f"Key deleted for '{del_prov}'")
                else:
                    st.warning(result["error"])

            if st.button("Export to .env", use_container_width=True):
                result = export_dotenv()
                if result["success"]:
                    st.success(f"Exported {result['count']} keys to {result['path']}")
                else:
                    st.warning(result["error"])

        # Key status table
        st.markdown("---")
        st.markdown("**Current Key Status**")
        keys_info = list_keys(masked=True)
        active_set = set(active_providers())
        cols = st.columns([1, 2, 1])
        with cols[0]:
            st.markdown("**Provider**")
        with cols[1]:
            st.markdown("**Key Status**")
        with cols[2]:
            st.markdown("**Active**")

        for prov in sorted(keys_info):
            label = PROVIDER_LABELS.get(prov, prov)
            is_active = prov in active_set
            status = keys_info[prov]
            with cols[0]:
                st.markdown(f"`{label}`")
            with cols[1]:
                st.markdown(f"`{status}`")
            with cols[2]:
                st.markdown("[OK]" if is_active else "")

    # ── Dataset Generator Section ──
    st.markdown("---")
    st.markdown("### Generate Dataset")

    if not active_providers():
        st.warning(
            "No API keys configured! Set at least one key above or via CLI:\n\n"
            "  `python -m src.cli apikeys set groq YOUR_KEY`"
        )

    gen_col1, gen_col2 = st.columns([1, 1])

    with gen_col1:
        max_chunks = st.number_input(
            "Max Chunks", min_value=1, max_value=10000, value=10,
            help="Number of documentation chunks to process. Start with 10 for testing.",
        )
        output_name = st.text_input(
            "Output Filename",
            value="webui_generated_dataset.json",
            help="Filename in data/training/ directory.",
        )

    with gen_col2:
        data_types = st.multiselect(
            "Data Types",
            options=[
                "basic", "reasoning", "error_fix", "expert",
                "interview", "project", "version",
                "security", "performance", "testing",
            ],
            default=["basic", "reasoning", "expert"],
            help="Types of Q&A pairs to generate.",
        )

        st.markdown("")  # spacer
        st.markdown("")  # spacer

        gen_disabled = st.session_state.gen_running or not active_providers()
        if st.button(
            "Start Generation",
            type="primary",
            use_container_width=True,
            disabled=gen_disabled,
        ):
            st.session_state.gen_running = True
            st.session_state.gen_done = False
            st.session_state.gen_log = []
            st.rerun()

    # ── Generation progress / log ──
    if st.session_state.gen_running or st.session_state.gen_done:
        st.markdown("---")
        st.markdown("### Generation Progress")

        log_container = st.container()

        if st.session_state.gen_running and not st.session_state.gen_done:
            # Run generation in foreground (Streamlit handles this fine for quick runs)
            with st.spinner("Generating dataset — this may take several minutes..."):
                result = _run_generation(
                    max_chunks=int(max_chunks),
                    data_types=data_types,
                    output_name=output_name,
                )

            st.session_state.gen_running = False
            st.session_state.gen_done = True
            st.session_state.gen_results = result

            if result["success"]:
                st.balloons()
                st.success(
                    f"**Dataset generated!** "
                    f"{result['pairs']} pairs saved to `{result['output']}` "
                    f"in {result['elapsed_min']:.1f} min."
                )
            else:
                st.error(f"Generation failed: {result.get('error', 'Unknown error')}")

            st.rerun()

        # Display log
        if st.session_state.gen_log:
            with log_container:
                for line in st.session_state.gen_log:
                    st.code(line)

        # Show results
        if st.session_state.gen_done:
            result = st.session_state.gen_results
            if isinstance(result, dict) and result.get("success"):
                st.success(
                    f"[OK] **{result['pairs']} pairs** generated in "
                    f"**{result['elapsed_min']:.1f} min**"
                )
                st.markdown(f"**Output:** `{result['output']}`")

                if result.get("type_stats"):
                    st.markdown("**Breakdown by type:**")
                    for t, n in sorted(result["type_stats"].items(), key=lambda x: -x[1]):
                        st.markdown(f"- `{t}`: {n}")

            # Reset button
            if st.button("Clear Results", use_container_width=True):
                st.session_state.gen_running = False
                st.session_state.gen_done = False
                st.session_state.gen_log = []
                st.session_state.gen_results = ""
                st.rerun()
