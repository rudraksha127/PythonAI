# MODULE M13 — DEPLOYMENT AND CLOUD BACKEND
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for productionizing the full
stack on Windows 11 and wiring the cloud backend. This is module 13 of 13
— the last module, and it depends on every previous one being genuinely
complete, not just started.
</role>

<mission_context>
Everything up to this point has proven the pieces work individually. This
module proves they work together, reliably, in a form that could survive
being handed to a real external user without the founder standing next to
them fixing things live.
</mission_context>

<verified_facts>
`docker-compose.yml` at the inner `PythonAI/` root already defines real
services, confirmed by direct inspection: `pythonai-api`, `pythonai-webui`,
`pythonai-godmode`, `pythonai-checkpoints`, and `pythonai-data`. Do not
assume generic service names — use these exact ones, and read the file to
understand what each is actually responsible for before changing anything.

`PythonAI/src/cloud/` exists with nine files: `auth.py`, `config.py`,
`tiers.py`, `supabase_client.py`, `realtime.py`, `status.py`, `db.py`,
`stripe_billing.py`, and `__init__.py` — meaning Supabase-backed auth,
tiered subscriptions, realtime sync, and Stripe billing are already
designed for, not something to design from scratch here.

`.gitignore` confirms `data/raw/`, `data/processed/`, and `*.gguf` are
intentionally untracked — this is why they were lost with the laptop and
not recoverable from git history; treat this as expected, not a defect
to fix.
</verified_facts>

<environment>
Windows 11 with Docker Desktop. Confirm Docker Desktop is running (not just
installed) before attempting any compose commands, since a common Windows
failure mode is Docker Desktop being installed but not started.
</environment>

<platforms_available>
A Supabase connector is available. Use it to actually create the tables
`src/cloud/db.py` and `supabase_client.py` expect, rather than guessing a
schema — read what those two files query and insert before defining any
table structure, so the schema matches what the code already assumes
rather than the reverse.
</platforms_available>

<task>
1. Read `docker-compose.yml` fully and understand what each of the five
   named services actually does and how they depend on each other.
2. Confirm Docker Desktop is running, then bring the stack up and confirm
   every service reaches a healthy state, not just a running one.
3. Read `src/cloud/db.py` and `supabase_client.py` to determine the exact
   tables and columns the code expects, then create a real Supabase project
   and those exact tables — schema driven by what the code needs, not by a
   generic guess at what a "users" or "signals" table should look like.
4. Confirm `auth.py` can register and authenticate a test user against the
   real Supabase project.
5. Confirm `realtime.py` actually delivers a live update to a subscribed
   client when new data is written — this is what module 12's dashboard
   depends on for its live views.
6. Produce a single install script or clearly ordered set of steps that
   would let a fresh Windows 11 machine go from "nothing installed" to
   "stack running" — this becomes the actual onboarding path for future
   users, so it needs to be genuinely followable, not just a summary of
   what you personally did.
7. Run one complete, real end-to-end system test: ask a real question
   through the running stack, confirm a real answer comes back with
   sources, log a real signal, and confirm the dashboard reflects it.
</task>

<constraints>
Use the existing `docker-compose.yml` services and `src/cloud/` modules as
the foundation. Extend rather than replace — if a service is misconfigured,
fix the configuration; if a cloud module is incomplete, complete it against
its existing interface.
</constraints>

<reasoning_process>
Before defining any Supabase table, read the actual query and insert calls
in `db.py` and `supabase_client.py` line by line — the code is the
specification for the schema here, not the other way around.
</reasoning_process>

<success_criteria>
- All five Docker services reach a healthy state
- Supabase tables exist and match exactly what the existing code queries
- Test user registration and authentication succeed against the real project
- A realtime update is confirmed to reach a subscribed client
- A genuinely followable fresh-machine setup path exists, tested by
  actually following it yourself if possible
- One full end-to-end system test passes: question in, sourced answer out,
  signal logged, dashboard reflects it
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [services healthy X/5, end-to-end test result]
BLOCKED: [exact blocker, or "none"]
NEXT: [the project is feature-complete for its first real external user —
       state what the very first thing to do with a real user should be]
</output_format>

<if_blocked>
If Docker Desktop resource limits on a 16GB Windows machine cause services
to fail under load, report the exact resource constraint hit rather than
silently reducing the service set to make the stack appear to run.
</if_blocked>
