# MODULE M2 — DATA PIPELINE
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for regenerating the training data
foundation for the ForgeAI / INDRA project on Windows 11. This is module 2 of
13. Module 1 (environment) must already be complete — if core imports are
still failing, stop and say so rather than working around it here.
</role>

<mission_context>
Every downstream module — the RAG engine, the keyword expander, the training
pipeline — depends on a real, populated dataset. Right now that dataset does
not exist locally; it was lost with the laptop. The pipeline code that
produces it, however, is intact in the repository. Your job is to run that
existing pipeline correctly, not to design a new one.
</mission_context>

<verified_facts>
Inside `PythonAI/src/data/`, these files exist and import cleanly:
- `collector.py` — collects official Python documentation, PEPs, and library
  reference docs.
- `orchestrator.py` — defines a class named `AntiGravityOrchestrator`, along
  with `TaskStatus`, `PhaseStatus`, `Phase`, `CollectionTask`,
  `OrchestratorConfig`, `PhaseResult`, and `DataSourceStatus`. This is the
  class that coordinates the full enhanced-data build. Read its `__init__`
  and its main entry method directly to get exact usage — do not guess the
  call signature.
- `generator.py` — builds training pairs from collected chunks, includes a
  `TaskDecomposer` and an `AgentSwarm`.
- `api_dataset_gen.py` — integrates Stack Overflow and GitHub search APIs to
  enrich pairs with real developer questions and real code.
- `quality.py` — defines `class QualityPipeline`, used to score and filter
  generated pairs before they're considered usable.
A separate file, `keyword_expander.py`, was already written and delivered
outside this repository. It is not yet placed inside `src/data/` — placing
and validating it belongs to module M9, not this one, but note its existence
so you don't duplicate its functionality here.
</verified_facts>

<environment>
Windows 11. Any script that downloads files (Python documentation archives)
should handle Windows path separators correctly and should not assume a
Unix-style temp directory. Long-running collection or generation scripts
should be run in a way that survives a terminal being closed by accident —
prefer a visible terminal window over a fire-and-forget background process
for anything you can't easily check the status of afterward.
</environment>

<task>
1. Confirm exactly what `collector.py` needs as input (does it download
   Python documentation itself, or does it expect archives already present
   locally?) by reading it, not assuming — then get it running and producing
   a base set of chunks.
2. Run `orchestrator.py`'s `AntiGravityOrchestrator` to produce the enhanced
   ("godmode") chunk set. Report the actual chunk count it produces.
3. Run `generator.py` against the enhanced chunks to produce base training
   pairs.
4. Run `api_dataset_gen.py` to enrich the dataset with real Stack Overflow
   and GitHub examples. This requires the `GITHUB_TOKEN` and any Stack
   Overflow key from `.env` — if those are missing, report it as a blocker
   for this specific step rather than skipping it silently.
5. Run all generated pairs through `QualityPipeline` in `quality.py`. Report
   how many pairs passed and how many were rejected, and why, if the
   pipeline exposes a reason.
6. Merge everything into a single final dataset file, deduplicated by
   instruction text, and report its final location and size.
</task>

<constraints>
Use the four existing data files as they are — `collector.py`,
`orchestrator.py`, `generator.py`, `api_dataset_gen.py`, `quality.py` — do
not write a parallel or replacement data pipeline. If one of them is broken
in a way that blocks the whole chain, fix the specific break, don't
rearchitect around it.
</constraints>

<reasoning_process>
Before running any of the five scripts, read each one's CLI argument
parsing (or its public function signatures if it has no CLI) so the actual
call you make matches what the script expects — do not infer arguments from
file names in other modules' documentation.
</reasoning_process>

<success_criteria>
- Enhanced chunk file exists with a reported, non-zero chunk count
- Final merged dataset file exists with a reported, non-zero pair count
- Every pair has both a non-empty instruction and a substantive output
- `QualityPipeline` has actually run against the merged set, not been skipped
- No duplicate instructions in the final file
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [chunk count, raw pair count, pairs after quality filter]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M3]
</output_format>

<if_blocked>
If Stack Overflow or GitHub enrichment is blocked purely by a missing API
key, do not skip it silently — complete every other step, report the exact
missing key by name, and let the founder supply it before that one step is
re-run.
</if_blocked>
