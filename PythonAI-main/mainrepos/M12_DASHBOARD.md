# MODULE M12 — DASHBOARD
## Paste this entire file into Anti-Gravity as the task. One module per session.

<role>
You are the engineering agent responsible for bringing both frontend
surfaces — the Next.js dashboard and the separate companion desktop app —
to a working state on Windows 11. This is module 12 of 13. Module 7 (API
server) must already be complete and running on port 7337.
</role>

<mission_context>
This is where every metric the rest of the system produces — acceptance
rate, retrieval quality, training progress — becomes something the founder
can actually look at, rather than numbers buried in log files.
</mission_context>

<verified_facts>
Two genuinely separate frontends exist, in different locations, built
differently — do not conflate them:
- The outer repository root's `dashboard/` folder is a Next.js app (uses
  the app router, confirmed by an `src/app/` folder) with roughly 60 `.tsx`
  files, including `LiveEventFeed.tsx`, `SignalPatternAnalysis.tsx`,
  `ImprovementHeatmap.tsx`, `LightRagMetrics.tsx`, `RoiCalculator.tsx`,
  `ArchitectureFlow.tsx`, and `TtsStatus.tsx`.
- The outer repository root's `Rudra-bots-main/` folder is a separate,
  Vite-based React app under its own `ui/` subfolder, with
  `pages/Dashboard.tsx`, `pages/Settings.tsx`, `pages/ForgeAI.tsx`, and
  components including `ChatArea.tsx`, `BrainModal.tsx`, `Sidebar.tsx`, and
  `ThemeModal.tsx`. It is a separate desktop-style companion app, not a
  duplicate of the Next.js dashboard.
</verified_facts>

<environment>
Windows 11. Both are Node-based projects — confirm the actual dev script in
each `package.json` before running, since a Vite app and a Next.js app use
different commands and may not share a default port.
</environment>

<platforms_available>
A Supabase connector is available for backend, auth, and realtime data —
module 13 owns the actual database setup, but if this module's work
surfaces a need for a specific table or realtime channel, note it precisely
for module 13 rather than improvising local-only state as a permanent fix.
A Figma connector is available if a component's visual design needs a
reference spec before implementation. A Lovable connector is available for
generating or repairing individual React components from a clear
description — if a component below turns out to be genuinely broken rather
than just unwired, this may be faster and more reliable than a manual
rewrite, and can be flagged back to the founder as a candidate for it.
</platforms_available>

<task>
1. Get the Next.js dashboard running locally and confirm its real dev
   server port from its own configuration.
2. For each of the seven named components above, open it in the browser
   and determine, specifically, whether it is broken (throws an error,
   renders nothing) or simply unwired (renders fine, but is pointed at the
   wrong API URL or an endpoint that doesn't exist yet). These require
   different fixes — diagnose before touching code.
3. Locate wherever the dashboard's API base URL is configured and confirm
   it points at `127.0.0.1:7337` — module 7's confirmed actual port.
4. Fix unwired components by correcting their API calls to match module 7's
   real, current endpoints. For any component that is genuinely broken
   rather than unwired, note it specifically rather than attempting a
   partial fix that leaves it fragile.
5. Get the separate `Rudra-bots-main/ui/` app running and confirm its
   `ForgeAI`-related page also correctly targets port 7337.
6. Confirm no browser console errors remain on either app's main pages
   after your fixes.
</task>

<constraints>
Wire existing components to the existing API rather than rewriting them
from scratch as a first resort. Reach for a full component rebuild only
after confirming the component is actually broken, not merely disconnected.
</constraints>

<reasoning_process>
Before fixing any component, open the browser's network tab and actually
observe what request it sends and what comes back — a blank or erroring
component very often means a working component pointed at the wrong URL,
and that is a one-line fix, not a rewrite.
</reasoning_process>

<success_criteria>
- Next.js dashboard runs and all seven named components render without
  console errors
- Every component's data source is confirmed to be module 7's real API,
  not a stale or hardcoded mock
- `Rudra-bots-main/ui/` runs independently and its ForgeAI page correctly
  targets the same API
- A precise list exists of any component found genuinely broken rather
  than just unwired, for the founder's attention
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [components working X/7, console errors before/after]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M13]
</output_format>

<if_blocked>
If a component needs backend data that doesn't exist anywhere yet (not a
wiring problem, a genuinely missing data source), state precisely what
data it needs so module 13's database setup can account for it, rather
than inventing placeholder data that looks real but isn't.
</if_blocked>
