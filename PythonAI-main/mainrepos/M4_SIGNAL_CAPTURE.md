# MODULE M4 — SIGNAL CAPTURE SYSTEM
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for verifying and wiring the
signal-capture system on Windows 11. This is module 4 of 13. Unlike most
other modules, this one is largely already built — your job is closer to a
rigorous audit than new construction. Treat "verify it's actually as
complete as it looks" as the primary task, not a formality.
</role>

<mission_context>
The entire self-improving premise of ForgeAI depends on this module: every
time a developer accepts or rejects a suggestion, that signal is what
eventually retrains the model. If this module is subtly broken, the product
never actually improves, no matter how good the rest of the system is.
</mission_context>

<verified_facts>
`PythonAI/src/learning/capture_engine.py` exists and, confirmed by direct
inspection, defines these methods on its main class:
`to_dict`, `from_dict`, `capture_accept`, `capture_reject`, `capture_edit`,
`capture_test_result`, `capture_pr_merge`, `store_training_run`,
`get_training_runs`, `get_signals`, `get_training_data`,
`get_acceptance_rate`, `get_statistics`, `export_for_training`.

Read the exact parameter signatures of `capture_accept` and `capture_reject`
directly before calling them — do not assume parameter names from this list
alone.

The storage backend is a local SQLite database, expected to encrypt at
rest. Confirm the exact default path by reading the class's `__init__`
rather than assuming a specific location.
</verified_facts>

<environment>
Windows 11. SQLite file paths and any encryption-key handling should use
Windows-appropriate user data locations (do not hardcode a Unix-style home
directory path).
</environment>

<task>
1. Read `capture_engine.py` in full and produce a short written summary, in
   your own words, of exactly what each of the 14 methods listed above does
   and what it expects as input — this is the grounding step, do it before
   anything else.
2. Instantiate the capture engine and confirm it creates its database file
   on first use without error.
3. Generate a batch of realistic synthetic signals — a mix of accepts and
   rejects, using genuinely varied prompt/completion pairs, not repeated
   identical ones — enough to exercise `get_statistics`,
   `get_acceptance_rate`, and `export_for_training` meaningfully.
4. Confirm `export_for_training` returns data in a shape that a training
   script could plausibly consume directly — report the actual shape you
   observe.
5. Check whether module M7's API server already exposes an endpoint that
   calls into this capture engine. If it does, verify it end to end. If it
   does not, add the minimal endpoint needed — a way to log a signal and a
   way to read back current statistics — using the existing capture engine
   methods, not new storage logic of your own.
</task>

<constraints>
Do not modify the storage schema or the encryption approach unless you find
a genuine defect, not a stylistic preference. This module's job is
verification and wiring, not redesign.
</constraints>

<reasoning_process>
Before generating synthetic test signals, think about what a realistic
week of a single developer's usage actually looks like — varied prompts,
a plausible accept rate (not 100%, not 0%), varied latency — rather than
mechanically identical repeated entries, since a lazy test set can hide
real bugs in aggregation logic.
</reasoning_process>

<success_criteria>
- Database file created automatically on first use
- Statistics and acceptance rate reflect the actual synthetic signals
  generated, verified by manual arithmetic check, not just "it returned a number"
- `export_for_training` output shape documented precisely
- A working path exists from a real signal event through to the API layer
- No signal data (actual code content) is exposed anywhere in a raw,
  unhashed form beyond what the existing schema already stores
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [signals stored, acceptance rate, exported pair count]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M5]
</output_format>

<if_blocked>
If the API endpoint for signals genuinely does not exist yet in module M7's
server file, build only the minimal version needed to prove the pipeline
works end to end, and flag it explicitly as a stub for M7 to properly own
and expand.
</if_blocked>
