# MODULE M14 — MASSIVE AUTONOMOUS KNOWLEDGE ACQUISITION
## Paste this entire file into Anti-Gravity as the task. One module per session.
## Read the note below before assuming this needs to be built from scratch.

<role>
You are the engineering agent responsible for activating, completing, and
extending an already-substantially-built massive-scale autonomous data
acquisition system on Windows 11. This is module 14, layered on top of
module 2 (data pipeline) and feeding module 10 (weekly self-improving
loop). Your primary job is audit and completion, not new architecture —
a very large system already exists here, and building a second one beside
it would be a serious mistake.
</role>

<mission_context>
The founder's goal is a system that continuously, on its own, discovers and
absorbs knowledge — Python itself, its library ecosystem, real code,
documentation, and research — without needing a human to hand it one
keyword or one source at a time forever. That ambition is not aspirational
here: it is already substantially designed in the codebase, and your job is
to find out precisely how much of it actually runs, then complete the rest.
</mission_context>

<verified_facts>
`PythonAI/src/data/massive_config.py` (confirmed, 2192 lines) defines a
function `generate_all_configs()` that assembles what its own docstring
calls "ALL 1600+ source configurations," built from 18 category-generator
functions, confirmed by direct inspection to include approximately:
arXiv (210, across cs.*, and other categories), PubMed (95), CrossRef
(100), Semantic Scholar (80), GitHub (450 — 30 topics across 15
languages), Stack Exchange (50 sites), OpenAlex (100), Wikipedia (100),
DOAJ (50), Reddit (50), RSS/HackerNews (40), PyPI (200 packages),
OpenLibrary/Gutenberg (30, open-access books), plus smaller categories
covering preprints, World Bank, ClinicalTrials, FRED, and Wikidata. Each
generated source config carries its own rate limit, output directory,
batch size, and a `max_records` ceiling (seen defaulting to 50,000 per
source in the config-builder helper) — this is not an unbounded firehose,
it is a large but deliberately rate- and volume-bounded system.

`PythonAI/src/data/massive_engine.py` (confirmed, 1816 lines, self-
described in its own header as "MASSIVE WORKER ENGINE v2.0") is the
execution engine for those configs — its own documentation claims TCP
connection pooling, dynamic concurrency scaling, batched JSONL writes, and
per-source state persistence so an interrupted run resumes rather than
restarting.

`PythonAI/src/data/discovery/` contains six files confirmed present:
`github_trending.py`, `arxiv_rss_watcher.py`, `gov_portal_crawler.py`,
`hf_catalog_scanner.py`, `paper_dataset_extractor.py`, and
`priority_ranker.py`. The last of these defines a `PriorityRanker` class
and a `ScoredDataset` type — this is very likely the exact mechanism needed
to rank discovered candidates by real signal (relevance, popularity,
quality) rather than processing everything in arbitrary order. Read it in
full before assuming a new ranking mechanism is needed.

`massive_config.py` sets `BASE_DATA_DIR` from a `DATA_DIR` environment
variable, defaulting to `D:/PythonAI_Data` — the founder already designed
around offloading large-scale collection to a secondary drive, consistent
with `src/data/d_drive_collector.py`, a separate, simpler collector also
present in the same folder. Confirm whether these two are meant to work
together, or whether one superseded the other, by checking for real
overlap in what they each write and where.

This repository uses Git LFS (see module M1) — several state and output
files may currently be small pointer stubs rather than real content until
M1's LFS pull step has actually run. Confirm this before treating any file
in this system as empty.
</verified_facts>

<environment>
Windows 11, with a secondary `D:` drive assumed available by the existing
configuration default. If no `D:` drive exists on this specific machine,
do not silently fail — determine the actual available drives and either
use an equivalent large-capacity path or make the target directory
explicitly configurable, since `massive_config.py` already reads it from
an environment variable rather than hardcoding it, which suggests this was
anticipated.
</environment>

<task>
1. Read `massive_config.py` and `massive_engine.py` in full, along with all
   six files in `discovery/`. Produce a precise written summary: which of
   the 18 categories are genuinely implemented and callable right now
   versus merely stubbed, what state-tracking exists, and what a full run
   actually requires (API keys, rate limits, the `D:` drive or equivalent).
2. Run the engine against a small, deliberately limited slice first — a
   single category, a handful of sources, a low `max_records` — purely to
   confirm the pipeline genuinely works end to end before pointing it at
   the full 1600+ source configuration.
3. Confirm `priority_ranker.py`'s `PriorityRanker` is wired to actually
   influence collection order or post-collection filtering. If it exists
   but is not called anywhere in the real execution path, wire it in
   rather than leaving a well-designed ranking system unused.
4. Audit for a genuine gap: coding-platform and data-structures-and-
   algorithms content is not obviously covered by the 18 existing
   categories. Do not add direct scraping of sites whose terms of service
   forbid it (this generally includes LeetCode, HackerRank, and
   Codeforces). Instead, extend the existing GitHub category's search
   topics to include openly-shared, developer-published solution
   repositories (for example, topics like "leetcode-solutions" or
   "competitive-programming"), which is both compliant and consistent with
   how the GitHub category already works.
5. Confirm every category respects real rate limits and does not exceed
   what a Windows 11 laptop with limited bandwidth can sustain running in
   the background for hours at a time.
6. Confirm collected raw output eventually flows into `ingestor.py` and
   from there into the same `orchestrator.py` and `quality.py` pipeline
   module M2 already uses — this system should feed the existing quality
   gate, not bypass it and produce a second, unfiltered dataset.
7. Wire a full run into module M10's weekly schedule as a background,
   resumable, long-running process rather than something requiring the
   founder to manually kick off and babysit.
8. Report real, current numbers: how many sources actually ran
   successfully in your test slice, how many records were collected, and a
   realistic time estimate for a meaningfully broad first pass across most
   of the 1600+ sources given real-world rate limits — not a claim that
   everything can be collected instantly.
</task>

<constraints>
Extend and activate the existing `massive_config.py`, `massive_engine.py`,
and `discovery/` modules. Do not write a parallel, simplified acquisition
system alongside them — if something in the existing system is broken,
diagnose and fix that specific thing. The goal is breadth driven by real
signal and sustained over time, not literal completeness collected in a
single run; a system that keeps discovering and improving indefinitely is
the actual goal, not a one-time maximal download.
</constraints>

<reasoning_process>
Before running anything at scale, form a specific, testable belief about
what currently works versus what only looks complete by file size and
docstring — a 1800-line file with an ambitious header comment is not
proof of a working system, only a strong hint that most of the hard design
work is already done. Verify with a small real run before trusting the
scale claim.
</reasoning_process>

<success_criteria>
- Written audit exists distinguishing genuinely-working categories from
  stubbed or broken ones, with specifics, not a rounded-up impression
- A small test run across at least one full category completes and
  produces real records in the expected output location
- `PriorityRanker` confirmed wired into the real execution path, not just
  present in the codebase
- A concrete, ToS-compliant plan exists for DSA/coding-platform coverage
  via GitHub topic search, not direct scraping of platforms that forbid it
- Collected data confirmed to flow into the existing quality-filtered
  pipeline from module M2, not a separate unfiltered path
- Wired into module M10's weekly schedule as an unattended background process
- Final report includes real numbers from an actual run, not projected ones
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [categories verified working X/18, records collected in test run,
         realistic time estimate for a broad first pass]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for the next scheduled run]
</output_format>

<if_blocked>
If a specific category's data source requires a paid API tier or a key the
founder hasn't provided, do not skip it silently — name the exact category
and exact key needed, complete every other category, and let this one
resume once the key is supplied. If any category's terms of service are
genuinely ambiguous about automated collection, treat that as a blocker to
report, not a judgment call to make unilaterally.
</if_blocked>
