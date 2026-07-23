# 00 — PROMPT ENGINEERING FRAMEWORK
## Why every file in this folder is built the way it is
## Read this once. Every other file will then make sense at a glance.

---

## THE CORE PROBLEM

"Fix the RAG module" is not a prompt, it is a wish. Handed to any coding agent
— Anti-Gravity, Claude Code, Cursor, anything — a vague instruction forces the
agent to guess: at your architecture, your naming conventions, which files are
safe to touch, what "done" means. Every guess is a place a bug can hide.

Every technique below exists to remove one specific kind of guess. This is not
folklore — it reflects how Anthropic documents Claude's actual behavior, and it
generalizes to any frontier coding agent because the failure modes (hallucinated
APIs, silent scope creep, confidently-wrong fixes) are the same across models.

---

## THE 9 TECHNIQUES

### 1. Role assignment
The first line of every prompt gives the agent an explicit identity and scope —
not "help me" but "you are the engineering agent responsible for X, this is
module N of 13, nothing downstream can be tested until this is genuinely done."
An agent told exactly what it owns behaves more carefully than one given an
open-ended request. Scope stated up front is scope the agent won't quietly expand.

### 2. XML-tagged structure
Every prompt is broken into labeled sections: `<role>`, `<mission_context>`,
`<verified_facts>`, `<environment>`, `<task>`, `<constraints>`,
`<reasoning_process>`, `<success_criteria>`, `<output_format>`, `<if_blocked>`.
Models trained on Claude specifically parse tagged sections more reliably than
a wall of prose — nothing from the "facts" section gets mistaken for an
instruction, nothing from "constraints" gets treated as optional. For prompts
this dense, structure is not decoration, it is what keeps 800 words legible.

### 3. Verified grounding, not assumptions
Every fact inside `<verified_facts>` in these files was pulled by directly
reading the actual repository minutes before writing the prompt — real file
names, real function names, real line counts, real default values. This
matters more than it sounds like it should: an agent grounded in specifics
has almost nothing left to invent. Anything not explicitly verified is marked
as such, with an instruction to confirm it by reading the file first rather
than assuming. This single habit is what separates "the agent hallucinated a
function that doesn't exist" from "the agent used the one that's actually there."

One concrete example from building this exact set of files: an earlier pass
assumed the local model was a 14B variant. Re-reading `config.py` directly
showed the real default is 7B, with the training base model also spec'd as
7B — a meaningfully different (and for this hardware, more realistic) fact
that a plausible-sounding assumption would have silently gotten wrong. That
correction is only in these files because grounding was treated as
non-negotiable, not because 14B was an unreasonable guess.

### 4. Explicit environment constraints
Windows 11 is stated directly in every file that touches installation, paths,
or background processes. Nothing Unix-only (cron, nohup, bash-only syntax) is
assumed to be available. The agent is told to resolve the correct Windows
tooling itself for the stated goal, rather than being handed commands that
might silently be wrong for the platform.

### 5. Reasoning before action
Every `<reasoning_process>` section asks the agent to think through what
already exists and what the smallest correct change is, before writing
anything. This is the single biggest lever against two opposite failure
modes: rewriting code that already works, and bolting on a fix without
understanding why the existing code was structured the way it was.

### 6. Positive framing over prohibition lists
Instructions say "reuse the existing `CaptureEngine` class" rather than a long
list of "don't rewrite this, don't touch that, don't invent new patterns."
Direct positive instructions are followed more reliably than negative ones —
telling a model what to do leaves less room for a technically-compliant but
unhelpful workaround.

### 7. An explicit "out"
Every file states exactly what to do when the agent is uncertain or blocked:
stop, report the specific blocker, move to the next independent subtask.
Without this instruction, agents tend to produce a confident-sounding fix
rather than surface genuine uncertainty — this is one line of instruction
that prevents most silent failures.

### 8. Testable success criteria
Every module ends with a checklist that can be verified by running something,
not by opinion. "Feels done" is banned. "10 out of 10 benchmark questions
return a non-empty, sourced answer" is not.

### 9. A fixed output format
Every file ends with the exact shape of status report expected back. Across
13 modules and many working sessions, this is what turns daily updates into
something scannable in ten seconds, instead of thirteen different report styles.

---

## THE SKELETON

Copy this shape for any future module you write yourself once these 13 are done:

```
<role>            Who the agent is, and which module this is out of how many
<mission_context> One or two lines: why this module matters to the larger goal
<verified_facts>  Real specifics pulled from the actual codebase, nothing invented
<environment>     OS and tooling constraints stated explicitly
<task>            Numbered objectives, most important first
<constraints>      What to preserve, framed as what TO do
<reasoning_process> The thinking steps to walk through before acting
<success_criteria> A checklist verifiable by running something
<output_format>    The exact status report shape expected back
<if_blocked>       What counts as a blocker, and what to do about it
```

---

## HOW TO USE THESE FILES

One module, one session. Paste that module's entire file into Anti-Gravity (or
whichever agentic coding tool) as the task. Do not paste multiple modules at
once — each is scoped to be a complete, independently testable unit of work,
and combining them defeats the "reasoning before action" step by giving the
agent too much surface area to reason about at once.

Work through them in the order given in the roadmap file. Later modules assume
earlier ones are actually done, not just started.

---

## THE 13 MODULES, IN ORDER

```
M1  — Environment setup                 (foundation, blocks everything)
M2  — Data pipeline                     (needs M1)
M3  — RAG engine                        (needs M1, M2)
M4  — Signal capture                    (independent, can run parallel to M2/M3)
M5  — Training pipeline (Kaggle)        (needs M2, M4)
M6  — Inference / provider registry     (needs M1)
M7  — API server                        (needs M1, M3, M4, M6)
M8  — Agents                            (needs M6)
M9  — Keyword expander                  (needs M2, M3)
M10 — Weekly self-improving loop        (needs M4, M5)
M11 — VS Code extension                 (needs M7)
M12 — Dashboard                         (needs M7)
M13 — Deployment                        (needs all of the above)
```
