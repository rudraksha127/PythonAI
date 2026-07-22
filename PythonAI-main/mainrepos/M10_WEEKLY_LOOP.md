# MODULE M10 — WEEKLY SELF-IMPROVING LOOP
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for closing the self-improvement
loop on Windows 11. This is module 10 of 13. Modules 4 (signal capture) and
5 (training pipeline) must already be complete, since this module's entire
job is connecting them on a schedule.
</role>

<mission_context>
This is the module that makes the word "self-improving" in the project's
name literally true instead of aspirational. Everything else in the project
can be perfect and the system will still be static without this loop
actually running unattended.
</mission_context>

<verified_facts>
`PythonAI/src/learning/daemon.py` exists, confirmed by direct inspection to
be 83 lines. In its current state it runs a loop that calls, in order:
`src.data.d_drive_collector` (with `--all --so-pages 2 --github-pages 1`),
`src.data.ingestor`, `src.learning.doc_watcher`'s `watch_docs` function, and
begins a Stack Overflow sync step. It does not currently collect signals
from the capture engine, does not currently trigger training, and does not
currently perform any model quality check or rollback — those are genuine
gaps, not misunderstandings on your part if you find them still missing.

Sibling files confirmed present in `src/learning/`: `so_sync.py`,
`git_hooks.py`, `forge_dashboard.py`, `error_patterns.py`,
`capture_engine.py`, `doc_watcher.py`, `conv_learner.py`, and `self_eval.py`.
`self_eval.py` defines a `SelfEvaluator`-style interface intended for
running a benchmark and tracking quality trend over time — read it directly
to confirm its exact method names before calling it.
</verified_facts>

<environment>
Windows 11 has no native cron. Use Windows Task Scheduler, or a Python
scheduling library already present in the dependency set, for anything
meant to run on a recurring schedule (weekly retraining, daily doc checks)
rather than assuming a Unix cron job will exist.
</environment>

<task>
1. Read `daemon.py` fully and confirm the gap described above still exists
   — specifically, that no step currently collects signals via
   `capture_engine.py`, triggers module 5's training pipeline, or performs
   a before/after quality comparison.
2. Extend the daemon to add a signal-collection step using the capture
   engine's existing `get_signals` and `export_for_training` methods.
3. Add a decision point: only trigger training if enough new signal data has
   accumulated since the last run — do not train on every cycle regardless
   of whether there's new data worth learning from.
4. Wire in a call to `self_eval.py`'s evaluator both before and after any
   retraining, and add an explicit rollback path — if the new model
   performs meaningfully worse than the previous one, the previous model
   must remain the one actually in use, and this decision must be logged,
   not silent.
5. Set this up to run on a genuine weekly schedule using Windows-appropriate
   scheduling, not just as a script that has to be run manually.
6. Do a full dry run of one complete cycle and report exactly what happened
   at each step.
</task>

<constraints>
Extend `daemon.py` and reuse `capture_engine.py`, module 5's training
entrypoint, and `self_eval.py` as they already exist. Do not build a
separate scheduling system that duplicates what `daemon.py` already
partially does.
</constraints>

<reasoning_process>
Before adding the rollback logic, think through the failure mode it exists
to prevent: a retrained model that is silently worse shipping to the
founder without anyone noticing until real usage suffers. Design the
before/after comparison and the rollback trigger with that specific
failure in mind, not as a generic afterthought.
</reasoning_process>

<success_criteria>
- Signal collection step added and confirmed to pull real data from the
  capture engine
- Training is only triggered when a genuine, reasoned threshold of new
  signal data is met
- Before/after quality comparison runs on every retraining cycle
- A working rollback exists and was actually tested — deliberately trigger
  a "worse model" scenario and confirm the system correctly keeps the
  previous model
- A full dry-run cycle completes and is reported step by step
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [dry run steps completed, rollback test result]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M11 and M12]
</output_format>

<if_blocked>
If the training trigger threshold is genuinely unclear from context, choose
a conservative, clearly-stated default (state the exact number and why),
rather than leaving the threshold undefined or arbitrarily low.
</if_blocked>
