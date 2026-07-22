"""Detailed stats of all collected data in anti_gravity_data (ASCII-safe)."""

import os, json, sys

BASE = "D:/PythonAI_Data/anti_gravity_data"


def fmt_size(sz):
    if sz < 1024:
        return f"{sz} B"
    elif sz < 1024 * 1024:
        return f"{sz / 1024:.1f} KB"
    else:
        return f"{sz / 1024 / 1024:.2f} MB"


print("=" * 75)
print("  ANTI-GRAVITY DATA COLLECTION - DETAILED STATS")
print("=" * 75)

total_rows = 0
total_files = 0
total_size = 0

all_sources = []

for root, dirs, files in os.walk(BASE):
    source = os.path.relpath(root, BASE)
    if source == ".":
        continue
    jsonl_files = sorted([f for f in files if f.endswith(".jsonl")])
    if not jsonl_files:
        continue

    source_total_rows = 0
    source_total_size = 0
    file_details = []

    for f in jsonl_files:
        fpath = os.path.join(root, f)
        size = os.path.getsize(fpath)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                row_count = sum(1 for _ in fh if _.strip())
        except Exception:
            row_count = 0
        file_details.append((f, row_count, size))
        source_total_rows += row_count
        source_total_size += size

    all_sources.append((source, file_details, source_total_rows, source_total_size))
    total_rows += source_total_rows
    total_files += len(jsonl_files)
    total_size += source_total_size

all_sources.sort(key=lambda x: x[0])

# Print detailed per-file breakdown
for source, file_details, srows, ssize in all_sources:
    print(f"\n  >>> {source}/")
    print(f"      {'-' * 55}")
    for fname, rows, sz in file_details:
        print(f"      {fname:50s}  {rows:>6,} rows  {fmt_size(sz):>10}")
    print(f"      {'-' * 55}")
    print(f"      Subtotal:             {srows:>6,} rows  {fmt_size(ssize):>10}")

# Grand total
print(f"\n{'=' * 75}")
print(f"  GRAND TOTAL:  {total_files} files  |  {total_rows:,} rows  |  {fmt_size(total_size)}")
print(f"{'=' * 75}")

# Summary table
print(f"\n{'=' * 75}")
print("  SUMMARY BY SOURCE")
print(f"{'=' * 75}")
print(f"  {'Source':<30s}  {'Files':>5s}  {'Rows':>10s}  {'Size':>10s}")
print(f"  {'-' * 30}  {'-' * 5}  {'-' * 10}  {'-' * 10}")
for source, file_details, srows, ssize in all_sources:
    nfiles = len(file_details)
    print(f"  {source:<30s}  {nfiles:>5d}  {srows:>10,}  {fmt_size(ssize):>10}")

# Topic breakdown
print(f"\n{'=' * 75}")
print("  TOPIC BREAKDOWN")
print(f"{'=' * 75}")
for source, file_details, srows, ssize in all_sources:
    print(f"\n  [{source}]")
    for fname, rows, sz in file_details:
        topic = os.path.splitext(fname)[0]
        print(f"    {topic:45s}  {rows:>6,} rows  {fmt_size(sz):>10}")

# Sample data quality check
print(f"\n{'=' * 75}")
print("  DATA QUALITY SAMPLE - First row keys from each source")
print(f"{'=' * 75}")
for source, file_details, srows, ssize in all_sources:
    if file_details:
        first_file = os.path.join(BASE, source, file_details[0][0])
        try:
            with open(first_file, "r", encoding="utf-8", errors="ignore") as fh:
                first_line = fh.readline().strip()
                if first_line:
                    parsed = json.loads(first_line)
                    keys = list(parsed.keys())
                    print(f"\n  [{source}/{file_details[0][0]}]")
                    print(f"      Keys ({len(keys)}): {', '.join(keys[:12])}")
                    if len(keys) > 12:
                        print(f"        ... +{len(keys) - 12} more")
                    # Show preview
                    preview = json.dumps(parsed, ensure_ascii=False, indent=2)
                    if len(preview) > 500:
                        preview = preview[:500] + "\n        ... (truncated)"
                    for line in preview.splitlines()[:6]:
                        print(f"      {line}")
        except Exception as e:
            print(f"\n  [{source}/{file_details[0][0]}] Error: {e}")
