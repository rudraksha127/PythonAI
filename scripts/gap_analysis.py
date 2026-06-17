#!/usr/bin/env python3
"""
Gap Analysis — Categorize Missing Repos by Extraction Issue Type
=================================================================

Compares the 14.md research document against the extracted JSON catalog
to identify repositories that were NOT captured, categorized by the
reason they were missed.

Issue Categories:
    - NO_CLONE_URL       : Table entry without a clone URL column
    - SUB_TABLE          : Nested/category sub-tables with no clone URLs
    - EMBEDDED_CODE_BLOCK: Repos in ```bash code blocks (should be captured)
    - BULLET_LIST        : Repos mentioned in bullet lists
    - COMPARISON_TABLE   : Non-standard markdown tables
    - INLINE_TEXT        : Repos mentioned in prose, not in a table or code block

Output: docs/GAP_ANALYSIS.md
"""

import json
import re
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_FILE = PROJECT_ROOT / "14.md"
CATALOG_FILE = PROJECT_ROOT / "ai_ml_repo_catalog.json"
OUTPUT_FILE = PROJECT_ROOT / "docs" / "GAP_ANALYSIS.md"


def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def load_catalog():
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_all_github_refs(text):
    """Find ALL unique GitHub owner/repo references in the document."""
    refs = set()
    # Pattern 1: github.com/owner/repo URLs
    for m in re.finditer(r'https?://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-/]+)', text):
        path = m.group(1).rstrip(".',;)\"")
        # Strip trailing tree/blob paths
        parts = path.split("/")
        if len(parts) >= 2:
            refs.add(f"{parts[0]}/{parts[1]}")
    # Pattern 2: **owner/repo** bold references
    for m in re.finditer(r'\*\*([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-]+)\*\*', text):
        refs.add(m.group(1))
    # Pattern 3: owner/repo in table cells (before a | separator)
    for m in re.finditer(r'\|\s*\*\*?([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-]+)\**\s*\|', text):
        refs.add(m.group(1))
    return refs


def extract_table_repos(text):
    """Find repos referenced in markdown tables."""
    table_repos = set()
    lines = text.split("\n")
    in_table = False
    for line in lines:
        if "|" in line and "---" in line:
            in_table = True
            continue
        if in_table:
            if "|" in line:
                cells = [c.strip() for c in line.split("|")]
                for cell in cells:
                    # Check for github.com URLs in cells
                    url_match = re.search(r'https?://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-]+)', cell)
                    if url_match:
                        path = url_match.group(1).rstrip(".')")
                        table_repos.add(path)
                    # Check for **owner/repo** patterns
                    bold_match = re.search(r'\*\*([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-]+)\*\*', cell)
                    if bold_match:
                        table_repos.add(bold_match.group(1))
                    # Check for plain owner/repo patterns
                    plain_match = re.match(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.\-]+$', cell)
                    if plain_match:
                        table_repos.add(cell)
            else:
                in_table = False
    return table_repos


def extract_code_block_repos(text):
    """Find repos referenced in ```bash or ``` code blocks with git clone."""
    code_repos = set()
    for m in re.finditer(r'```(?:bash)?\s*\n(.*?)```', text, re.DOTALL):
        block = m.group(1)
        for clone in re.finditer(r'git clone https?://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-/]+)', block):
            path = clone.group(1).rstrip(".')")
            parts = path.split("/")
            if len(parts) >= 2:
                code_repos.add(f"{parts[0]}/{parts[1]}")
    return code_repos


def extract_inline_repos(text):
    """Find repos mentioned in-line (bullet lists, prose) not in tables or code blocks."""
    inline_repos = set()
    # Remove code blocks first
    text_no_code = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # Remove tables
    lines = text_no_code.split("\n")
    table_lines = False
    clean_lines = []
    for line in lines:
        if "|" in line and "---" in line:
            table_lines = True
            continue
        if table_lines:
            if "|" in line:
                continue
            else:
                table_lines = False
        clean_lines.append(line)
    clean_text = "\n".join(clean_lines)

    # Now find owner/repo patterns
    for m in re.finditer(r'([A-Za-z0-9_.-]+/[A-Za-z0-9_.\-]+)', clean_text):
        ref = m.group(1)
        # Filter out false positives (version numbers, file paths, etc.)
        if not any(c in ref for c in [" ", "\t", "\n", ".md", ".py", ".js", ".ts"]):
            if ref.count("/") == 1:
                inline_repos.add(ref)
    return inline_repos


def determine_issue_type(ref, text, table_repos, code_repos):
    """Determine why a repo reference was likely missed by the extractor."""
    # Find all occurrences of this ref in the text
    indices = [m.start() for m in re.finditer(re.escape(ref), text)]

    for idx in indices[:3]:  # Check first few occurrences
        context = text[max(0, idx - 200):idx + 200]

        # Check if it's in a table
        lines_around = context.split("\n")
        for line in lines_around:
            if "|" in line and ref in line:
                # Is there a clone URL in this table row?
                if "git clone" not in line and "Clone" not in line.split("|")[-1]:
                    # Check if this is a sub-table (fewer columns)
                    cols = [c.strip() for c in line.split("|") if c.strip()]
                    if len(cols) <= 5:
                        return "COMPARISON_TABLE"
                    return "NO_CLONE_URL"
                return "HAS_CLONE_URL"  # Should have been extracted

        # Check if it's in a code block
        if "```" in context:
            if "git clone" in context:
                return "EMBEDDED_CODE_BLOCK"
            return "CODE_BLOCK_NO_CLONE"

        # Check if it's in a bullet list
        if any(f"- [{ref}" in line or f"- **{ref}" in line or f"- {ref}" in line
               for line in lines_around):
            return "BULLET_LIST"

        # Check if it's in a comparison-style row (no table, just inline)
        if ref in context:
            return "INLINE_TEXT"

    return "UNKNOWN"


def build_report():
    text = read_file(INPUT_FILE)
    catalog = load_catalog()

    # Get extracted repos
    extracted_repos = {r["full_name"].lower() for r in catalog["all_repos"]}

    # Get all referenced repos in different contexts
    all_refs = extract_all_github_refs(text)
    table_refs = extract_table_repos(text)
    code_refs = extract_code_block_repos(text)
    inline_refs = extract_inline_repos(text)

    # Filter to valid-looking repo names (owner/repo format)
    def is_valid_repo(ref):
        parts = ref.split("/")
        if len(parts) != 2:
            return False
        if not parts[0] or not parts[1]:
            return False
        if len(parts[0]) < 2 or len(parts[1]) < 2:
            return False
        # Filter out common false positives
        if any(kw in ref.lower() for kw in ["example", "sample", "test", "todo", "fixme"]):
            return False
        return True

    all_refs = {r for r in all_refs if is_valid_repo(r)}
    table_refs = {r for r in table_refs if is_valid_repo(r)}
    code_refs = {r for r in code_refs if is_valid_repo(r)}
    inline_refs = {r for r in inline_refs if is_valid_repo(r)}

    # Find missing repos
    all_refs_lower = {r.lower(): r for r in all_refs}
    missing_refs = set()

    for ref_lower, ref_original in all_refs_lower.items():
        if ref_lower not in extracted_repos:
            missing_refs.add(ref_original)

    # Also check against known false positives from the catalog
    known_good_catalog = set()
    for r in catalog["all_repos"]:
        fn = r["full_name"]
        known_good_catalog.add(fn.lower())

    missing_refs = {r for r in missing_refs if r.lower() not in known_good_catalog}

    # Categorize missing repos
    categories = defaultdict(list)
    for ref in sorted(missing_refs):
        issue = determine_issue_type(ref, text, table_refs, code_refs)
        categories[issue].append(ref)

    # Build report
    lines = []
    lines.append("# Gap Analysis: 14.md → Extracted Catalog")
    lines.append("")
    lines.append(f"**Source:** 14.md (research document)")
    lines.append(f"**Catalog:** {catalog['total_repos']} repos extracted")
    lines.append(f"**Unique GitHub refs found in source:** {len(all_refs)}")
    lines.append(f"**Missing from catalog:** {len(missing_refs)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Overview table
    lines.append("## Overview")
    lines.append("")
    lines.append("| Issue Type | Count | Description |")
    lines.append("|------------|-------|-------------|")
    for cat_name in ["NO_CLONE_URL", "COMPARISON_TABLE", "SUB_TABLE",
                     "EMBEDDED_CODE_BLOCK", "CODE_BLOCK_NO_CLONE",
                     "BULLET_LIST", "INLINE_TEXT", "UNKNOWN"]:
        count = len(categories.get(cat_name, []))
        if count > 0:
            desc = {
                "NO_CLONE_URL": "Table entry missing clone URL column",
                "COMPARISON_TABLE": "Non-standard comparison table (fewer columns)",
                "SUB_TABLE": "Nested sub-table without clone URLs",
                "EMBEDDED_CODE_BLOCK": "In code block with git clone command",
                "CODE_BLOCK_NO_CLONE": "In code block without git clone",
                "BULLET_LIST": "Bullet list item without clone URL",
                "INLINE_TEXT": "Mentioned in prose, not in table/code",
                "UNKNOWN": "Could not determine extraction issue",
            }.get(cat_name, "")
            lines.append(f"| {cat_name} | {count} | {desc} |")
    lines.append("")

    # Detailed breakdown by category
    lines.append("## Detailed Breakdown")
    lines.append("")

    priority_order = [
        ("EMBEDDED_CODE_BLOCK", "🟢 Repos in Code Blocks (Easiest to Fix)", "These repos ARE in code blocks with git clone commands. The extractor should have caught them. Likely a regex or path parsing issue."),
        ("NO_CLONE_URL", "🟡 Repos in Tables Without Clone URLs", "These repos appear in table rows that do NOT have a clone URL column. Need to infer clone URLs from the owner/repo name."),
        ("COMPARISON_TABLE", "🟡 Repos in Comparison Tables", "These repos are in compact comparison tables with fewer columns. The table parser may not recognize them as repo entries."),
        ("SUB_TABLE", "🟡 Repos in Sub-Tables", "Nested sub-tables without standard headers. Common in MCP, Video Gen, and other subsections."),
        ("CODE_BLOCK_NO_CLONE", "🔴 Repos in Code Blocks Without Clone", "These repos are mentioned in code blocks but without git clone commands — harder to extract automatically."),
        ("BULLET_LIST", "🔴 Repos in Bullet Lists", "Mentioned in bullet-point lists without explicit clone URLs. Need to infer from context."),
        ("INLINE_TEXT", "🔴 Repos in Prose", "Mentioned in running text only. Hardest to extract — requires context-aware parsing."),
        ("UNKNOWN", "⚪ Unknown Issue", "Could not automatically determine why these were missed."),
    ]

    for cat_key, title, description in priority_order:
        items = categories.get(cat_key, [])
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        lines.append(description)
        lines.append("")
        lines.append(f"**{len(items)} repos:**")
        lines.append("")
        # Find which section/category each missing repo belongs to
        sectioned = defaultdict(list)
        for ref in items:
            section = find_section_for_repo(text, ref)
            sectioned[section].append(ref)

        for section in sorted(sectioned.keys()):
            repos = sectioned[section]
            lines.append(f"**{section}** ({len(repos)} repos)")
            for ref in repos:
                # Find a context snippet
                snippet = find_context_snippet(text, ref)
                lines.append(f"- [{ref}](https://github.com/{ref}) — {snippet}")
            lines.append("")
        lines.append("")

    # Recommendations
    lines.append("---")
    lines.append("## Recommendations")
    lines.append("")
    lines.append("### 1. Fix Code Block Extraction (Easiest)")
    lines.append(f"Update `extract_repos_from_14md.py` to better parse repos from code blocks — {len(categories.get('EMBEDDED_CODE_BLOCK', []))} repos are in code blocks with git clone commands.")
    lines.append("")
    lines.append("### 2. Add Clone URL Inference for Tables")
    lines.append(f"Infer clone URLs for {len(categories.get('NO_CLONE_URL', [])) + len(categories.get('COMPARISON_TABLE', []))} repos from their owner/repo name rather than requiring an explicit clone URL column.")
    lines.append("")
    lines.append("### 3. Parse Sub-Tables Recursively")
    lines.append(f"Add recursive sub-table parsing for nested sections — affects {len(categories.get('SUB_TABLE', []))} repos in sub-categories.")
    lines.append("")
    lines.append("### 4. Context-Aware Extraction for Bullet Lists & Prose")
    lines.append(f"The remaining {len(categories.get('BULLET_LIST', [])) + len(categories.get('INLINE_TEXT', []))} repos require context-aware extraction from bullet lists and prose text.")
    lines.append("")
    lines.append("### 5. Priority by Section")
    lines.append("Focus on sections with the most misses:")
    lines.append("")

    # Count by section
    section_counts = defaultdict(int)
    for cat_items in categories.values():
        for ref in cat_items:
            section = find_section_for_repo(text, ref)
            section_counts[section] += 1

    for section, count in sorted(section_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{section}**: {count} repos")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by gap_analysis.py | Catalog: {catalog['total_repos']} repos | Missing: {len(missing_refs)} refs*")
    lines.append("")

    return "\n".join(lines), missing_refs, categories, all_refs


def find_section_for_repo(text, ref):
    """Find which section header a repo reference belongs to."""
    idx = text.find(ref)
    if idx < 0:
        return "Unknown"
    before = text[:idx]
    # Find the closest # header
    headers = re.findall(r'^# [^#].*$', before, re.MULTILINE)
    if headers:
        header = headers[-1].strip()
        header = header.replace("# ", "").replace("**", "")
        return header[:60]
    return "Preamble"


def find_context_snippet(text, ref):
    """Find a brief context snippet around a repo reference."""
    idx = text.find(ref)
    if idx < 0:
        return ""
    snippet = text[idx:idx + 80].replace("\n", " ")
    snippet = re.sub(r'\s+', ' ', snippet)
    return snippet.strip()[:60]


def main():
    print("Running gap analysis...")
    report, missing_refs, categories, all_refs = build_report()

    # Write report
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Saved to {OUTPUT_FILE}")

    # Summary stats
    print(f"\n{'=' * 50}")
    print(f"GAP ANALYSIS SUMMARY")
    print(f"{'=' * 50}")
    print(f"  Total unique GitHub refs in 14.md: {len(all_refs)}")
    print(f"  Missing from catalog:              {len(missing_refs)}")
    print(f"\n  Breakdown by issue type:")
    for cat_name in ["NO_CLONE_URL", "COMPARISON_TABLE", "SUB_TABLE",
                     "EMBEDDED_CODE_BLOCK", "CODE_BLOCK_NO_CLONE",
                     "BULLET_LIST", "INLINE_TEXT", "UNKNOWN"]:
        count = len(categories.get(cat_name, []))
        if count > 0:
            print(f"    {cat_name:25s}: {count}")
    print()


if __name__ == "__main__":
    main()
