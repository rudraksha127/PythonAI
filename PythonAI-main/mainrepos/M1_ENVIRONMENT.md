# MODULE M1 — ENVIRONMENT SETUP
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for bringing a partially-recovered
Python and TypeScript monorepo to a fully working local development state on
a Windows 11 machine. This is module 1 of 13 in a sequenced rebuild. Nothing
in modules 2 through 13 can be verified until this module is genuinely,
testably complete — treat this as the highest-leverage work in the project.
</role>

<mission_context>
The project (ForgeAI / INDRA, repo: rudraksha127/PythonAI) lost its local
data and working environment to a laptop failure. The GitHub repository
itself is intact: roughly 157 Python files, two VS Code extensions, a
Next.js dashboard, a separate Electron/Vite companion app, and an existing
test suite. Your job is not to rebuild the code — it is to get the code
that already exists actually running.
</mission_context>

<verified_facts>
- Clone with submodules: the outer repository contains an inner `PythonAI/`
  submodule holding `src/`, `tests/`, `vscode-extension/`, and `tools/`, plus
  sibling top-level folders `dashboard/` and `Rudra-bots-main/` at the outer
  repo root. Five submodules were confirmed uninitialized on a prior clone.
- `requirements.txt` at the inner `PythonAI/` root already lists the full
  intended dependency set, including `outlines`, `chromadb`, `lightrag-hku`,
  `mem0ai`, `crewai`, and `dspy-ai`.
- `.env.example` exists and is the authoritative list of every environment
  variable the codebase reads. Do not invent variable names not present there.
- `src/config.py` defines the real default model as `qwen2.5-coder:7b`
  (inference) and `Qwen/Qwen2.5-Coder-7B-Instruct` (training base) — confirm
  these are still current before assuming any other model size or name.
  Embeddings default to `sentence-transformers/all-MiniLM-L6-v2`, run
  locally, not through Ollama.
  Model overrides come from the `FORGEAI_MODEL` and `FORGEAI_BASE_MODEL`
  environment variables — read `src/config.py` in full for anything else it
  expects.
- A prior import check found 12 of 15 core modules importing cleanly; the 3
  failures were a missing `sentence-transformers` package and a torch
  shared-library path issue — both environment problems, not code problems.
- 64 `test_*.py` files exist in the inner repo's `tests/` folder. Treat any
  previously-reported pass count as stale — get a fresh number yourself.
- CRITICAL: this repository uses Git LFS. A plain `git clone`, even with
  submodules, leaves every LFS-tracked file as a small text pointer (a few
  hundred bytes containing an oid and a size) instead of its real content.
  This was confirmed directly: `data/training/training_dataset.json`
  currently checks out as a 133-byte pointer file whose own content states
  its real size is 41,516,938 bytes (~41.5MB) — the actual training dataset
  is not lost, it is sitting in LFS storage and has simply never been pulled.
  Do not treat any LFS-tracked file as missing or in need of regeneration
  until you have confirmed, after a real LFS pull, that it is still absent.
</verified_facts>

<environment>
Target OS: Windows 11. Do not assume WSL is available unless you detect it
directly. Use PowerShell-native approaches for anything that would
traditionally be Unix-only (background/daemon processes, scheduled tasks,
environment variable handling). If a pip install fails due to an
externally-managed environment or a conflicting pre-installed package,
diagnose and resolve it properly — do not silently drop the package from
the install.
</environment>

<task>
1. Clone the repository with submodules initialized. Confirm every expected
   top-level folder is present and note the actual directory layout you find,
   since later modules will reference paths relative to it.
2. Install Git LFS if it is not already present on the machine, then run
   the LFS pull for this repository specifically. Afterward, re-check every
   file that looked suspiciously small or empty in a first pass — several
   are almost certainly real, substantial files that were only pointer
   stubs before this step. Report file sizes before and after for anything
   you initially suspected was missing.
3. Install every dependency in `requirements.txt`. For any package that
   fails, read the actual error before choosing a fix — a missing package
   and a version conflict look similar in a summary but need different fixes.
4. Create a real `.env` from `.env.example`. Do not fabricate values for API
   keys or secrets. List clearly, in your final report, exactly which keys
   the founder must supply himself, and proceed as far as possible without them.
5. Install Ollama for Windows and pull whatever model `src/config.py`
   currently specifies as default — confirm the exact name from the file
   itself rather than trusting a cached assumption.
6. Re-run an import check across every top-level module under `src/`, not
   just the 15 previously checked — you may find others.
7. Run the existing test suite and report an exact, current pass count.
</task>

<constraints>
Reuse and preserve every file that already imports and runs correctly.
Fix only what is actually broken. If a fix would require touching more than
the specific missing dependency or broken import, stop and report it as a
scoped blocker for a later module rather than expanding this module's scope.
</constraints>

<reasoning_process>
Before installing anything, read `requirements.txt` and `.env.example` in
full — both are short and both are authoritative. Before "fixing" an import
error, read the actual traceback line by line rather than pattern-matching
on the module name in the error message.
</reasoning_process>

<success_criteria>
- Fresh clone contains all expected folders, submodules initialized
- Every module under `src/` imports without error
- `.env` exists with every variable from `.env.example` present
- Ollama installed; the model named in `src/config.py` is pulled and shows
  in `ollama list`
- Test suite run produces an exact, current pass/fail count
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [imports passing X/Y — tests passing X/Y]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M2]
</output_format>

<if_blocked>
If a specific dependency cannot be resolved after two genuinely different
fix attempts, stop retrying variations of the same approach. Report the
exact error, exactly what was tried, and continue with any other subtask in
this module that does not depend on it.
</if_blocked>
