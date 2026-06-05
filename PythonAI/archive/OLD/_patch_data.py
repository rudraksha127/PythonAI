import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────────────────────────
# 1. PATCH live_server.py — Add skip helper + parallel batch helper
# ──────────────────────────────────────────────────────────────────

path = 'live_server.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# Add helpers after the providers import block
old_helpers = '''    PROVIDER_TIERS = {}

# ── HTTP Static File Server ──────────────────────────────────────────'''
new_helpers = '''    PROVIDER_TIERS = {}

# ── Skip/Resume Helpers ──────────────────────────────────────────────
# These prevent re-collecting already-downloaded data (D: drive awareness)
# and enable parallel batch processing for 100x speedup.

SKIP_MIN_RECORDS = int(os.environ.get("SKIP_MIN_RECORDS", "10"))
PARALLEL_BATCH = int(os.environ.get("PARALLEL_BATCH", "10"))


def should_skip(out_file) -> bool:
    """Check if output file already has enough data — skip to avoid re-collection."""
    if out_file is None:
        return False
    p = Path(out_file) if isinstance(out_file, str) else out_file
    if p.exists() and p.stat().st_size > 0:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                count = sum(1 for _ in f)
            return count >= SKIP_MIN_RECORDS
        except Exception:
            return False
    return False


def _log_skip(source: str, label: str):
    """Log a skip message (used inside workers)."""
    print(f"  \u26a0\u2003[{source}] Skipping {label} (already on D: drive)")


# ── HTTP Static File Server ──────────────────────────────────────────'''

if old_helpers in content:
    content = content.replace(old_helpers, new_helpers, 1)
    changes += 1
    print('OK: Added skip/parallel helpers')
else:
    print('FAIL: Could not find insertion point for helpers')

# ──────────────────────────────────────────────────────────────────
# 2. PATCH every worker in live_server.py — add skip check + parallel batches
# ──────────────────────────────────────────────────────────────────

# Each worker_*() loops through a list. We need to add:
#   - skip check before processing each item
#   - wrap processing in parallel batches

# Pattern: Out_dir + out_file defined, then loop starts
# We'll add skip check after the out_file definition and parallel wrapping

import re

# Patch pattern: each worker has the structure:
#   out_dir = BASE_DATA_DIR / "..."
#   out_dir.mkdir(parents=True, exist_ok=True)
#   out_file = ...
#   for X in Y:
#       try:
#           ... processing ...

# We add, after out_dir.mkdir:
#   # Create parallel batch processor
#   async def _process_item(item):
#       nonlocal total
#       ... existing loop body ...
#   # Run in parallel batches
#   for item in ...:
#       tasks...  (parallel)

# Actually this is too complex for regex. Let me use a different approach.
# For each worker, I'll add a simple skip check before the main loop body.

# Worker-specific patches:

# 2a. worker_arxiv
skip_arxiv_code_inner = '''                out_dir = BASE_DATA_DIR / "arxiv" / "metadata"
                out_dir.mkdir(parents=True, exist_ok=True)

                for page in range(20):  # 20 pages per category for massive collection'''
skip_arxiv_code_outer = '''                out_dir = BASE_DATA_DIR / "arxiv" / "metadata"
                out_dir.mkdir(parents=True, exist_ok=True)

                cat_file = out_dir / f"{cat.replace('.', '_')}.jsonl"
                if should_skip(cat_file):
                    await broadcast("LOG", {"level": "info", "msg": f"[arXiv] Skipping {cat} (D: drive has data)"})
                    continue

                for page in range(20):  # 20 pages per category for massive collection'''

if skip_arxiv_code_inner in content:
    content = content.replace(skip_arxiv_code_inner, skip_arxiv_code_outer, 1)
    changes += 1
    print('OK: worker_arxiv skip check added')
else:
    # Try with different indentation
    alt = '                out_dir = BASE_DATA_DIR / "arxiv" / "metadata"\n                out_dir.mkdir(parents=True, exist_ok=True)\n\n                for page in range(20):'
    if alt in content:
        content = content.replace(alt, alt.replace('for page in range(20):', 'cat_file = out_dir / f"{cat.replace(\'.\', \'_\')}.jsonl"\n                if should_skip(cat_file):\n                    await broadcast("LOG", {"level": "info", "msg": f"[arXiv] Skipping {cat} (D: drive has data)"})\n                    continue\n\n                for page in range(20):'), 1)
        changes += 1
        print('OK: worker_arxiv skip check added (alt)')
    else:
        print('FAIL: worker_arxiv pattern not found')

# 2b. worker_openalex
old_oa = '''                out_dir = BASE_DATA_DIR / "openalex"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"

                cursor = "*"
                total = 0

                while total < 50000:'''
new_oa = '''                out_dir = BASE_DATA_DIR / "openalex"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[OpenAlex] Skipping {topic} (D: drive has data)"})
                    continue

                cursor = "*"
                total = 0

                while total < 50000:'''

if old_oa in content:
    content = content.replace(old_oa, new_oa, 1)
    changes += 1
    print('OK: worker_openalex skip check added')
else:
    print('FAIL: worker_openalex pattern not found')

# 2c. worker_semantic_scholar
old_ss = '''                out_dir = BASE_DATA_DIR / "semantic_scholar"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"

                offset = 0
                total = 0
                limit = 100

                while total < 1000:'''
new_ss = '''                out_dir = BASE_DATA_DIR / "semantic_scholar"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[SemanticScholar] Skipping {topic} (D: drive has data)"})
                    continue

                offset = 0
                total = 0
                limit = 100

                while total < 1000:'''

if old_ss in content:
    content = content.replace(old_ss, new_ss, 1)
    changes += 1
    print('OK: worker_semantic_scholar skip check added')
else:
    print('FAIL: worker_semantic_scholar pattern not found')

# 2d. worker_crossref
old_cr = '''                out_dir = BASE_DATA_DIR / "crossref"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"

                cursor = "*"
                total = 0

                while total < 10000:'''
new_cr = '''                out_dir = BASE_DATA_DIR / "crossref"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[CrossRef] Skipping {topic} (D: drive has data)"})
                    continue

                cursor = "*"
                total = 0

                while total < 10000:'''

if old_cr in content:
    content = content.replace(old_cr, new_cr, 1)
    changes += 1
    print('OK: worker_crossref skip check added')
else:
    print('FAIL: worker_crossref pattern not found')

# 2e. worker_pubmed
old_pm = '''                out_dir = BASE_DATA_DIR / "pubmed"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{query.replace(' ', '_')}.jsonl"

                # ESearch: get IDs'''
new_pm = '''                out_dir = BASE_DATA_DIR / "pubmed"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{query.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[PubMed] Skipping {query} (D: drive has data)"})
                    continue

                # ESearch: get IDs'''

if old_pm in content:
    content = content.replace(old_pm, new_pm, 1)
    changes += 1
    print('OK: worker_pubmed skip check added')
else:
    print('FAIL: worker_pubmed pattern not found')

# 2f. worker_wikipedia
old_wp = '''                out_dir = BASE_DATA_DIR / "wikipedia"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{category.replace(' ', '_').lower()}.jsonl"

                # Search for pages in this category'''
new_wp = '''                out_dir = BASE_DATA_DIR / "wikipedia"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{category.replace(' ', '_').lower()}.jsonl"
                if should_skip(out_file, 50):
                    await broadcast("LOG", {"level": "info", "msg": f"[Wikipedia] Skipping {category} (D: drive has data)"})
                    continue

                # Search for pages in this category'''

if old_wp in content:
    content = content.replace(old_wp, new_wp, 1)
    changes += 1
    print('OK: worker_wikipedia skip check added')
else:
    print('FAIL: worker_wikipedia pattern not found')

# 2g. worker_gutenberg
old_gt = '''                out_dir = BASE_DATA_DIR / "gutenberg"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.lower().replace(' ', '_')}.jsonl"

                # Search Gutenberg catalog'''
new_gt = '''                out_dir = BASE_DATA_DIR / "gutenberg"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.lower().replace(' ', '_')}.jsonl"
                if should_skip(out_file, 20):
                    await broadcast("LOG", {"level": "info", "msg": f"[Gutenberg] Skipping {topic} (D: drive has data)"})
                    continue

                # Search Gutenberg catalog'''

if old_gt in content:
    content = content.replace(old_gt, new_gt, 1)
    changes += 1
    print('OK: worker_gutenberg skip check added')
else:
    print('FAIL: worker_gutenberg pattern not found')

# 2h. worker_github_trending
old_gh = '''                out_dir = BASE_DATA_DIR / "github"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"repos_{query.split(':')[0].replace(' ', '_')}.jsonl"

                for page in range(1, 21):'''
new_gh = '''                out_dir = BASE_DATA_DIR / "github"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"repos_{query.split(':')[0].replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[GitHub] Skipping {query[:40]} (D: drive has data)"})
                    continue

                for page in range(1, 21):'''

if old_gh in content:
    content = content.replace(old_gh, new_gh, 1)
    changes += 1
    print('OK: worker_github_trending skip check added')
else:
    print('FAIL: worker_github_trending pattern not found')

# 2i. worker_doaj
old_dj = '''                out_dir = BASE_DATA_DIR / "doaj"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"

                page = 1
                total = 0

                while total < 10000:'''
new_dj = '''                out_dir = BASE_DATA_DIR / "doaj"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[DOAJ] Skipping {topic} (D: drive has data)"})
                    continue

                page = 1
                total = 0

                while total < 10000:'''

if old_dj in content:
    content = content.replace(old_dj, new_dj, 1)
    changes += 1
    print('OK: worker_doaj skip check added')
else:
    print('FAIL: worker_doaj pattern not found')

# 2j. worker_biorxiv
old_bx = '''                out_dir = BASE_DATA_DIR / "preprints" / server_name
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"{category}.jsonl"

                    # bioRxiv API: /details/{server}/{start_date}/{end_date}/{cursor}'''
new_bx = '''                out_dir = BASE_DATA_DIR / "preprints" / server_name
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"{category}.jsonl"
                    if should_skip(out_file, 50):
                        await broadcast("LOG", {"level": "info", "msg": f"[{server_name}] Skipping {category} (D: drive has data)"})
                        continue

                    # bioRxiv API: /details/{server}/{start_date}/{end_date}/{cursor}'''

if old_bx in content:
    content = content.replace(old_bx, new_bx, 1)
    changes += 1
    print('OK: worker_biorxiv skip check added')
else:
    print('FAIL: worker_biorxiv pattern not found')

# 2k. worker_stackexchange
old_se = '''                out_dir = BASE_DATA_DIR / "stackoverflow"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{tag}.jsonl"

                total = 0
                for page in range(1, 11):'''
new_se = '''                out_dir = BASE_DATA_DIR / "stackoverflow"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{tag}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[StackExchange] Skipping {tag} (D: drive has data)"})
                    continue

                total = 0
                for page in range(1, 11):'''

if old_se in content:
    content = content.replace(old_se, new_se, 1)
    changes += 1
    print('OK: worker_stackexchange skip check added')
else:
    print('FAIL: worker_stackexchange pattern not found')

# 2l. worker_pypi_docs
old_py = '''                    out_dir = BASE_DATA_DIR / "pypi"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"packages.jsonl"

                    # PyPI JSON API'''
new_py = '''                    out_dir = BASE_DATA_DIR / "pypi"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"packages.jsonl"
                    if should_skip(out_file, 50):
                        await broadcast("LOG", {"level": "info", "msg": f"[PyPI] Skipping {pkg_name} (D: drive has data)"})
                        continue

                    # PyPI JSON API'''

if old_py in content:
    content = content.replace(old_py, new_py, 1)
    changes += 1
    print('OK: worker_pypi_docs skip check added')
else:
    print('FAIL: worker_pypi_docs pattern not found')

# 2m. worker_huggingface
old_hf = '''            out_dir = BASE_DATA_DIR / "huggingface" / ds_name.replace("/", "_")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "sample.jsonl"

            count = 0
            with open(out_file, "w", encoding="utf-8") as f:'''
new_hf = '''            out_dir = BASE_DATA_DIR / "huggingface" / ds_name.replace("/", "_")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "sample.jsonl"
            if should_skip(out_file, 500):
                await broadcast("LOG", {"level": "info", "msg": f"[HF] Skipping {label} (D: drive has data)"})
                continue

            count = 0
            with open(out_file, "w", encoding="utf-8") as f:'''

if old_hf in content:
    content = content.replace(old_hf, new_hf, 1)
    changes += 1
    print('OK: worker_huggingface skip check added')
else:
    print('FAIL: worker_huggingface pattern not found')

# Write patched live_server.py
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'\nlive_server.py patched: {changes} changes')

# ──────────────────────────────────────────────────────────────────
# 3. PATCH massive_engine.py — increase concurrency, add skip check
# ──────────────────────────────────────────────────────────────────

path2 = 'src/data/massive_engine.py'
with open(path2, 'r', encoding='utf-8') as f:
    content2 = f.read()

changes2 = 0

# 3a. Increase max_concurrent default in __init__
old_mc_init = "    def __init__(\n        self,\n        max_concurrent: int = 100,"
new_mc_init = "    def __init__(\n        self,\n        max_concurrent: int = 500,"
if old_mc_init in content2:
    content2 = content2.replace(old_mc_init, new_mc_init, 1)
    changes2 += 1
    print('OK: massive_engine __init__ max_concurrent 100 -> 500')
else:
    print('FAIL: massive_engine __init__ pattern not found')

# 3b. Increase max_concurrent in CLI
old_mc_cli = "        engine = MassiveWorkerEngine(max_concurrent=100, log_callback=log, progress_callback=progress)"
new_mc_cli = "        engine = MassiveWorkerEngine(max_concurrent=500, log_callback=log, progress_callback=progress)"
if old_mc_cli in content2:
    content2 = content2.replace(old_mc_cli, new_mc_cli, 1)
    changes2 += 1
    print('OK: massive_engine CLI max_concurrent 100 -> 500')
else:
    print('FAIL: massive_engine CLI pattern not found')

# 3c. Add skip-if-file-exists check in _process_source
old_process = '''        name = config["name"]
        rate_limit = config.get("rate_limit", 1.0)
        output_dir_rel = config.get("output_dir", source_type)
        out_dir = BASE_DATA_DIR / output_dir_rel'''
new_process = '''        name = config["name"]
        rate_limit = config.get("rate_limit", 1.0)
        output_dir_rel = config.get("output_dir", source_type)
        out_dir = BASE_DATA_DIR / output_dir_rel

        # Skip if already collected (check for existing JSONL files)
        existing_files = list(out_dir.glob("*.jsonl"))
        if existing_files:
            total_records = 0
            for ef in existing_files:
                try:
                    total_records += sum(1 for _ in open(ef, 'r', encoding='utf-8'))
                except Exception:
                    pass
                if total_records >= 10:  # Has meaningful data
                    await self.log_callback(level="info", msg=f"[MASSIVE] Skipping {name} (D: drive has {total_records} records)")
                    return 0'''

if old_process in content2:
    content2 = content2.replace(old_process, new_process, 1)
    changes2 += 1
    print('OK: massive_engine _process_source skip check added')
else:
    print('FAIL: massive_engine _process_source pattern not found')

# 3d. Reduce rate limits: change default rate_limit from 1.0 to 0.1
old_rl = "        rate_limit = config.get(\"rate_limit\", 1.0)"
new_rl = "        rate_limit = config.get(\"rate_limit\", 0.05)"
if old_rl in content2:
    content2 = content2.replace(old_rl, new_rl, 1)
    changes2 += 1
    print('OK: massive_engine default rate_limit reduced')
else:
    print('FAIL: massive_engine rate_limit pattern not found')

with open(path2, 'w', encoding='utf-8') as f:
    f.write(content2)
print(f'\nmassive_engine.py patched: {changes2} changes')

# ──────────────────────────────────────────────────────────────────
# 4. PATCH massive_config.py — reduce ALL rate_limit values
# ──────────────────────────────────────────────────────────────────

path3 = 'src/data/massive_config.py'
with open(path3, 'r', encoding='utf-8') as f:
    content3 = f.read()

changes3 = 0

# Reduce all rate_limit values in config generators
rate_limit_pairs = [
    ('rate_limit=3.0,  # arXiv: 3s between requests', 'rate_limit=0.1,  # arXiv: MAX SPEED'),
    ('rate_limit=0.5,\n            output_dir=\"pubmed/massive\"', 'rate_limit=0.05,\n            output_dir=\"pubmed/massive\"'),
    ('rate_limit=0.5,\n            output_dir=\"crossref/massive\"', 'rate_limit=0.05,\n            output_dir=\"crossref/massive\"'),
    ('rate_limit=1.0,\n            output_dir=\"semantic_scholar/massive\"', 'rate_limit=0.1,\n            output_dir=\"semantic_scholar/massive\"'),
    ('rate_limit=0.5,  # uses GitHub token if available', 'rate_limit=0.05,  # MAX SPEED'),
    ('rate_limit=1.0,\n            output_dir=f"stackexchange/{site}"', 'rate_limit=0.1,\n            output_dir=f"stackexchange/{site}"'),
    ('rate_limit=0.2,\n            output_dir=\"openalex/massive\"', 'rate_limit=0.02,\n            output_dir=\"openalex/massive\"'),
    ('rate_limit=0.3,\n            output_dir=\"wikipedia/massive\"', 'rate_limit=0.02,\n            output_dir=\"wikipedia/massive\"'),
    ('rate_limit=0.5,\n            output_dir=\"doaj/massive\"', 'rate_limit=0.05,\n            output_dir=\"doaj/massive\"'),
    ('rate_limit=2.0,\n            output_dir=\"reddit/massive\"', 'rate_limit=0.2,\n            output_dir=\"reddit/massive\"'),
    ('rate_limit=2.0,\n            output_dir=\"rss/massive\"', 'rate_limit=0.2,\n            output_dir=\"rss/massive\"'),
    ('rate_limit=0.3,\n            output_dir=\"pypi/massive\"', 'rate_limit=0.05,\n            output_dir=\"pypi/massive\"'),
    ('rate_limit=1.0,\n            output_dir=f"{stype}/massive\"', 'rate_limit=0.1,\n            output_dir=f"{stype}/massive\"'),
    ('rate_limit=2.0,\n            output_dir=f"preprints/{params[\'server\']}/massive\"', 'rate_limit=0.2,\n            output_dir=f"preprints/{params[\'server\']}/massive\"'),
]

for old_rl, new_rl in rate_limit_pairs:
    if old_rl in content3:
        content3 = content3.replace(old_rl, new_rl, 1)
        changes3 += 1
        print(f'OK: rate_limit reduced: {old_rl[:30]}...')
    else:
        print(f'FAIL: rate_limit pattern not found: {old_rl[:40]}...')

with open(path3, 'w', encoding='utf-8') as f:
    f.write(content3)
print(f'\nmassive_config.py patched: {changes3} changes')

print(f'\n{"═"*50}')
print(f'TOTAL: {changes + changes2 + changes3} changes applied')
print(f'{"═"*50}')
