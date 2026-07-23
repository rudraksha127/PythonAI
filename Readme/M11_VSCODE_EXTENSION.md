# MODULE M11 — VS CODE EXTENSION
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for building and wiring both VS
Code extensions on Windows 11. This is module 11 of 13. Module 7 (API
server) must already be complete and running on port 7337.
</role>

<mission_context>
This is where the whole system becomes something the founder actually
experiences while writing code, rather than something that only exists as
backend services. It's also the only module whose real-world usage
directly produces the signal data module 4 and module 10 depend on — a
broken extension doesn't just fail on its own, it starves the entire
self-improvement loop of real data.
</mission_context>

<verified_facts>
Two separate VS Code extensions exist, confirmed present, each with its own
`package.json`:
- `PythonAI/vscode-extension/` — the main chat and inline completion extension
- `PythonAI/tools/vscode-forgeai-capture/` — the signal-capture extension,
  intended to log accept and reject events (for example, on Tab versus Esc)
Read each `package.json`'s actual `scripts` section directly to get the
real build commands — do not assume a generic `npm run build` or
`npm run compile` without confirming the script name exists.
</verified_facts>

<environment>
Windows 11, native (not WSL) VS Code. Extension packaging with `vsce` and
extension installation via the `code` CLI both work natively on Windows,
but confirm the `code` command is on PATH before relying on it — VS Code's
Windows installer does not always add it automatically.
</environment>

<task>
1. Read both `package.json` files fully and identify the real build script
   for each — do not guess the script name.
2. Install dependencies and build both extensions, resolving any
   TypeScript compilation errors that surface.
3. In the main extension, locate wherever it constructs the backend URL it
   talks to, and confirm it points at `127.0.0.1:7337` — module 7's
   confirmed actual port — not a different default. Correct it if it points
   elsewhere.
4. In the signal-capture extension, confirm precisely which editor events
   it currently listens for, and confirm what endpoint it posts to when an
   accept or reject happens. Wire it to module 7's actual signal endpoint
   if it currently points elsewhere or doesn't exist yet.
5. Package both as installable `.vsix` files and install them into VS Code.
6. Manually exercise the full loop once: open a Python file, trigger a
   completion, accept it, and confirm — by querying module 7's stats
   endpoint directly — that a real signal was recorded as a result.
</task>

<constraints>
Extend both existing extensions as they are. Do not create a third,
simplified extension from scratch — if something in either extension is
broken, fix that specific thing.
</constraints>

<reasoning_process>
Before declaring the signal loop "working," verify it with the actual
stats endpoint, not just by trusting that a network request was sent
without error — a request can succeed at the network level while still
writing malformed data that the capture engine silently drops.
</reasoning_process>

<success_criteria>
- Both extensions build without TypeScript errors
- Both install into VS Code without error
- Main extension correctly targets port 7337
- A real, manually-triggered accept event is confirmed, via the stats
  endpoint, to have actually been recorded
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [both extensions build Y/N, signal test confirmed Y/N]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M12]
</output_format>

<if_blocked>
If the `code` CLI is not available on PATH, report the exact Windows fix
needed (locating VS Code's bin folder and adding it to PATH, or installing
via the .vsix through the Extensions view directly) rather than silently
skipping the install step.
</if_blocked>
