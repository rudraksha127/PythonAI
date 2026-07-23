# MODULE M7 — API SERVER
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for bringing the FastAPI backend
to a fully working state on Windows 11. This is module 7 of 13. Modules 1,
3, 4, and 6 must already be complete — this module is the integration point
that exposes all of them together.
</role>

<mission_context>
This server is what the VS Code extension (module 11) and the dashboard
(module 12) both talk to. If it is not solid here, every problem in it
becomes a confusing problem two modules downstream instead of a clear one
right here.
</mission_context>

<verified_facts>
`PythonAI/src/api/server.py` is confirmed, by direct inspection, to be
roughly 2,700 lines, to start `uvicorn` bound to `127.0.0.1` on port
`7337` (not 8000 — do not assume the common default), and to define
approximately 44 route handlers across REST and WebSocket endpoints,
covering at minimum: health and stats, RAG search and indexing, memory
add/search, agent chat, direct ask/chat, training status and triggers, and
SEAL cycle status. Read the file directly to get the exact current route
list and their exact request/response shapes — do not assume any specific
route's exact path or payload without checking.
</verified_facts>

<environment>
Windows 11. Running the server persistently for testing should use a
visible terminal window or Windows' own process management rather than a
Unix-style background-and-forget pattern, so failures are actually seen.
</environment>

<task>
1. Start the server and confirm it binds successfully on port 7337.
2. Enumerate every route the file actually defines — produce a real,
   current list, not a copy of what's described above, since that
   description is a snapshot from an earlier inspection, not a guarantee
   of the current state.
3. Exercise the health/stats endpoints, the RAG search endpoint (using
   module 3's now-working engine), the direct ask/chat endpoints, and the
   signal endpoint (using module 4's capture engine) — confirm each returns
   a sensible response, not just a 200 status.
4. For any route that returns a 500 error, read the actual server-side
   traceback and fix the specific cause — do not paper over an error by
   catching and swallowing the exception.
5. Confirm a WebSocket connection to the events endpoint succeeds and can
   receive at least one message.
6. Confirm CORS is configured to allow the dashboard's local origin —
   check what's actually configured before assuming it's missing or present.
</task>

<constraints>
Extend the existing server file — do not create a second, parallel API
server. If a needed endpoint is genuinely missing (not just misconfigured),
add it using the same patterns already established elsewhere in the file
for consistency.
</constraints>

<reasoning_process>
Before touching any route, reproduce its failure directly with a real
request and read the actual error, rather than inferring the cause from
the route's name or from how a similar-looking route elsewhere behaves.
</reasoning_process>

<success_criteria>
- Server starts cleanly on port 7337
- A complete, current route inventory is documented
- Health, RAG search, chat/ask, and signal endpoints all return correct,
  non-error responses
- No unhandled 500 errors remain across the tested routes
- WebSocket endpoint accepts a connection and delivers at least one message
- CORS allows the dashboard's local origin
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [routes tested X/total, 500 errors before/after fix]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M8 and M11]
</output_format>

<if_blocked>
If a route's failure traces back to a module that isn't actually complete
yet (for example, RAG search failing because module 3's index was never
built), report that as the true root cause rather than patching the
symptom inside the API layer.
</if_blocked>
