# MODULE M8 — AGENTS
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for verifying and wiring the
specialized agent layer on Windows 11. This is module 8 of 13. Module 6
(provider registry) must already be complete, since every agent here
depends on it to actually reach a language model.
</role>

<mission_context>
This layer is what turns a single generic chat endpoint into task-specific
behavior — a debugging question should get debugging-shaped help, a
"teach me this" question should get a different kind of answer than a
"write this for me" question. The routing between them is as important as
the agents themselves.
</mission_context>

<verified_facts>
Two distinct agent locations exist and are both real, confirmed by direct
inspection — do not conflate them:
- `PythonAI/src/agents/` contains seven task-specific files:
  `code.py`, `debug.py`, `docs.py`, `performance.py`, `retrieval.py`,
  `teacher.py`, and `orchestrator.py`.
- `PythonAI/src/core/agents/` contains a separate, lower-level layer:
  `swarm.py`, `sub_agent.py`, and its own `orchestrator.py`. Read both
  orchestrator files and determine how they relate to each other — one may
  be a higher-level wrapper around the other, or they may serve different
  purposes entirely. Do not assume without checking.
</verified_facts>

<environment>
Windows 11. No environment-specific concerns beyond earlier modules — this
is primarily a code and integration verification task.
</environment>

<task>
1. Read all seven files in `src/agents/` and both orchestrator files, and
   produce a short written summary of what each agent actually does and
   what makes it distinct from the others.
2. Test each of the seven task-specific agents individually with a
   realistic prompt matched to its purpose, and confirm each returns
   substantive, non-empty output.
3. Test the routing logic — send a handful of varied queries that should
   clearly map to different agents (a "write me a function" style query, a
   "there's a bug here" style query, a "explain this like I'm new to it"
   style query) and confirm each one actually reaches the agent you'd
   expect it to.
4. Check whether `src/api/server.py`'s agent-facing endpoint (from module 7)
   actually calls into this orchestration layer, or bypasses it. Wire it
   properly if it doesn't already.
5. Report response times for each agent — some route through multiple
   providers in parallel and may be meaningfully slower or faster than
   others; this is useful information, not just a pass/fail signal.
</task>

<constraints>
Use the existing seven agents and both orchestrators as they are. If
routing logic is incomplete rather than absent, extend it using the same
pattern it already follows rather than introducing a new routing mechanism.
</constraints>

<reasoning_process>
Before concluding routing is "broken" for a given query, consider whether
the query itself was genuinely unambiguous — a vague test query routing
inconsistently may reflect the query, not a defect in the routing logic.
</reasoning_process>

<success_criteria>
- All seven agents individually produce substantive output on a matched query
- Routing correctly selects the expected agent for at least 4 of 5 clearly-
  worded test queries
- The API's agent endpoint is confirmed to actually invoke this layer
- Response times are reported per agent, not just as one aggregate number
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [agents working X/7, routing accuracy X/5, response times]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M9]
</output_format>

<if_blocked>
If an agent fails purely because no provider is available for it (a
module 6 issue resurfacing here), report it as a module 6 dependency
issue rather than attempting a local workaround inside the agent file.
</if_blocked>
