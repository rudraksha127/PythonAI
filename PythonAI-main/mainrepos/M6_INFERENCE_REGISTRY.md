# MODULE M6 — INFERENCE / PROVIDER REGISTRY
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for diagnosing and fixing the LLM
provider registry on Windows 11. This is module 6 of 13. This module is a
focused diagnostic task, not a rebuild — treat scope discipline as the main
skill being exercised here.
</role>

<mission_context>
Every module that calls an LLM — the agents, the RAG engine's generation
step, the keyword expander — routes through this registry. If it silently
returns an empty provider list, everything downstream either crashes or
falls back to a hardcoded default without anyone noticing why.
</mission_context>

<verified_facts>
`PythonAI/src/core/providers/registry.py`, confirmed by direct inspection:
- At module level, `ALL_PROVIDERS: list[ProviderDescriptor] = []` and
  `ALL_MODELS: list[ModelDescriptor] = []` are both initialized empty.
- Elsewhere in the same file, there is already lazy-load logic that
  reassigns `ALL_PROVIDERS = _default_registry.list_providers()` and the
  equivalent for `ALL_MODELS` — meaning population logic already exists,
  the open question is whether and when it actually triggers.
- A `ProviderRouter` class exists with a `route` method, a
  `get_racing_providers` method, and an internal `_route_auto` method.
- `src/utils/llm.py` provides a `generate_parallel` function intended to
  race multiple providers and return the fastest usable result.
- Individual provider implementations exist as separate files in the same
  folder, including an Ollama provider.
Do not assume this is simply "an empty list that needs manual entries
written" — read the surrounding function that performs the lazy reassignment
first, since the actual defect may be that nothing ever calls it, not that
the registration logic itself is missing.
</verified_facts>

<environment>
Windows 11. No environment-specific concerns beyond module M1's general
setup — this is a pure code diagnostic task.
</environment>

<task>
1. Read the full `registry.py` file, specifically the function containing
   the lazy-load reassignment, and determine precisely what triggers it —
   is it called on first access, on import, only inside a specific method,
   or not reliably called at all?
2. Confirm the actual root cause with a direct, repeatable test: import the
   registry module fresh, then check whether providers are populated before
   and after calling whatever function is supposed to trigger population.
3. Fix the root cause you find — this may be as small as ensuring the
   trigger function is actually called where it's needed, or it may require
   completing an incomplete registration path. Do not rewrite the class
   structure unless the diagnosis genuinely requires it.
4. Confirm which providers become available depends on which API keys exist
   in `.env` — report exactly which providers are usable given the current
   environment, and which are defined but missing a key.
5. Test `generate_parallel` with at least two genuinely different providers
   (one local via Ollama, one cloud) and confirm it returns a result from
   whichever responds first.
6. Test the Ollama provider in isolation, since it requires no API key and
   should work regardless of what else is configured.
</task>

<constraints>
Fix the actual root cause of the empty list. Do not work around it by
hardcoding a provider list somewhere else in the codebase that calls into
the registry — that would leave the real defect in place for the next
person to hit again.
</constraints>

<reasoning_process>
Before writing any fix, form a specific hypothesis about why the list is
empty at the point it's being read — module-import timing, a missing
function call, or an exception being silently swallowed somewhere in the
registration path — and confirm that specific hypothesis with a test before
changing code to address it.
</reasoning_process>

<success_criteria>
- Root cause of the empty provider list is identified and stated precisely,
  not just worked around
- After the fix, a fresh import shows a non-empty, correct provider list
- At least one local (Ollama) and one cloud provider both work end to end
- `generate_parallel` correctly returns a result when racing two providers
- Report clearly states which providers are usable given the current `.env`
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [providers registered, providers actually usable given current keys]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M7]
</output_format>

<if_blocked>
If the root cause turns out to require an architectural change bigger than
a targeted fix, stop before making that change, describe the tradeoff
clearly, and let the founder decide rather than unilaterally restructuring
a module other code depends on.
</if_blocked>
