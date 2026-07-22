# MODULE M9 — KEYWORD EXPANDER
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for placing, validating, and
adapting the keyword-expansion module on Windows 11. This is module 9 of
13. Modules 2 (data pipeline) and 3 (RAG engine) must already be complete.
</role>

<mission_context>
This is the feature that lets the founder type a single word or phrase and
have the system generate a full spread of questions, real answers, and
training-ready pairs about it — the mechanism by which the model's
knowledge can be deliberately deepened on demand, rather than only growing
from whatever documentation happened to be collected.
</mission_context>

<verified_facts>
A file named `keyword_expander.py` was already written and delivered
separately from this repository — it is not yet present inside
`PythonAI/src/data/`. It was designed to auto-detect a topic's domain from
a bare keyword, build a set of questions scaled by a requested "depth,"
optionally pull real context from Stack Overflow and GitHub search, generate
answers through the existing provider layer, score them with the existing
`QualityPipeline` from `quality.py`, and checkpoint its progress so a long
run can be resumed. Treat this description as the design intent, not a
guarantee that it matches the current state of the repository it needs to
plug into — module 2 and module 6 may have changed function signatures it
was written against.
</verified_facts>

<environment>
Windows 11. File paths inside the script should be checked for Windows
compatibility. Long keyword-expansion runs that call external APIs should
be resumable if interrupted, and should not silently lose progress on a
Windows sleep/wake cycle.
</environment>

<task>
1. Place `keyword_expander.py` into `src/data/`.
2. Before running it, cross-check every internal import and function call
   it makes against the actual current signatures in `quality.py`,
   `generator.py`, and the provider layer from module 6 — fix any mismatch
   you find rather than assuming the file is already correct.
3. Run it in a dry, no-generation mode first (if it supports one) on a
   single well-understood keyword, and confirm the questions it produces
   look genuinely useful before spending any API calls generating real
   answers for them.
4. Run it for real on a small, deliberately varied set of keywords —
   include at least one clearly Python-specific term, one general
   programming concept, and one topic outside programming entirely — and
   confirm its domain auto-detection behaves sensibly for all three.
5. Confirm generated pairs pass through `QualityPipeline` and that
   low-quality pairs are actually being rejected, not silently kept.
6. Merge the keyword-generated pairs into the same final dataset location
   module 2 produced, deduplicated against what's already there.
</task>

<constraints>
Adapt the script to match the current codebase's real interfaces rather
than changing the current codebase to match the script's assumptions —
the script is the newer, less-tested piece here.
</constraints>

<reasoning_process>
Before running the full keyword set, verify on a single keyword end to end
that the entire chain works — domain detection, question generation,
external API enrichment if configured, answer generation, and quality
scoring — since a mid-chain failure discovered after a large batch run
wastes both time and API quota.
</reasoning_process>

<success_criteria>
- Script placed and all internal calls confirmed to match current signatures
- Domain auto-detection behaves sensibly across at least three distinct
  keyword types
- Generated pairs are actually filtered by quality score, with rejected
  pairs distinguishable from accepted ones in the output
- Keyword-generated pairs successfully merged into the shared dataset file
  without duplicating existing entries
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [keywords tested, pairs generated, pairs passing quality filter]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M10]
</output_format>

<if_blocked>
If a mismatch between the script and the current codebase is more than a
small signature fix — for example, if `QualityPipeline`'s interface has
changed shape entirely — report the mismatch precisely rather than
quietly forcing compatibility with a fragile patch.
</if_blocked>
