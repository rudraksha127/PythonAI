# MODULE M3 — RAG ENGINE
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for bringing the RAG (retrieval and
answering) engine to a working, end-to-end state on Windows 11. This is
module 3 of 13. Modules 1 (environment) and 2 (data pipeline) must already be
genuinely complete — if the final dataset file from module 2 does not exist
yet, stop and say so.
</role>

<mission_context>
This module is the core product experience: a question goes in, a grounded,
sourced, verified answer comes out. Everything else in the project — the
agents, the VS Code extension, the dashboard — is ultimately a surface on top
of what this module produces. It needs to actually work before anything is
built on top of it.
</mission_context>

<verified_facts>
`PythonAI/src/rag/rag_engine.py` exists and defines, confirmed by direct
inspection:
- `class SimpleBM25` — sparse/keyword retrieval component
- `def hybrid_search(...)` — combines dense and sparse retrieval
- `def mmr_rerank(...)` — diversity-aware reranking of results
- `def expand_query(question, model=...)` — query expansion before retrieval
- `class SearchResult` — the result object type returned by search
- `def format_sources(docs)` — formats retrieved sources for display
- `def get_answer(...)` — the main end-to-end entry point: question in,
  answer out
- `def build_db(chunks_file)` — builds a fresh index from a chunks file
- `def load_db(chunks_file)` — loads an existing index
- `def execute_code(code, timeout=5)` — runs code in a sandbox and returns
  output and error separately
- `def print_stats(collection, chunks_file)` and `def parse_args()` also exist

Sibling files in the same folder include `cast_chunker.py`,
`knowledge_graph.py`, `lightrag_wrapper.py`, `verifier.py`, `reasoning.py`,
and `constitution.py` — read each briefly to understand how `get_answer`
actually uses them before assuming their role from the file name alone.

Embeddings are `sentence-transformers/all-MiniLM-L6-v2`, confirmed in
`src/config.py`, run locally — this module does not depend on Ollama for
embeddings, only for the generation model itself.
</verified_facts>

<environment>
Windows 11. Building a vector index from ~14,000+ chunks is CPU and memory
intensive on a 16GB machine with no dedicated GPU — if you observe the
process becoming unresponsive, consider whether batching the build reduces
peak memory rather than assuming more RAM is the only fix.
</environment>

<task>
1. Use `build_db` to construct a fresh index from module 2's final dataset
   file. Report the resulting document count.
2. Use `load_db` and `hybrid_search` directly to confirm retrieval quality
   on a handful of your own test queries about Python before testing the
   full answer pipeline — isolate retrieval quality from generation quality.
3. Use `get_answer` end to end and confirm it returns a response, source
   attribution, and something resembling a confidence signal.
4. Use `execute_code` directly to confirm it correctly reports success for
   valid Python and correctly reports an error for invalid Python — this is
   the verification layer the whole product's trust claim depends on.
5. Design and run a benchmark of 10 real, varied Python questions spanning
   at least: async/await, the GIL, decorators, a recent language-version
   change, and memory management. For each, record whether a substantive
   answer came back, how long it took, and how many sources were cited.
6. Report the benchmark results as a table, not a summary sentence.
</task>

<constraints>
Use `rag_engine.py`'s existing public functions as your interface — do not
build a parallel retrieval or answering path. If `get_answer` is missing a
capability you'd expect (such as confidence scoring), check
`constitution.py` and `verifier.py` first, since that responsibility may
already live there rather than in `rag_engine.py` itself.
</constraints>

<reasoning_process>
Before writing your 10 benchmark questions, briefly consider what would
actually distinguish a genuinely good local Python assistant from a
mediocre one — favor questions with version-specific or commonly-confused
answers over generic ones, since those are where retrieval quality actually
matters.
</reasoning_process>

<success_criteria>
- Index built with a reported, non-zero document count
- `hybrid_search` returns results a Python developer would judge relevant
  for at least 4 of 5 manual test queries
- 9 or more of the 10 benchmark questions return a substantive, sourced answer
- `execute_code` correctly distinguishes passing and failing code
- Average benchmark response time is reported as an exact number
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [index doc count — benchmark X/10 — avg response time]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M6, then M7]
</output_format>

<if_blocked>
If average response time is far outside what feels usable on this hardware,
report the actual number and a hypothesis for the bottleneck rather than
silently reducing the benchmark's difficulty to make the number look better.
</if_blocked>
