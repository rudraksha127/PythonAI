#!/bin/bash
# ============================================================================
# AI/ML GitHub Ultimate Ecosystem — Master Orchestrator
# Runs ALL extraction, generation, and analysis steps in sequence
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  AI/ML GitHub Ultimate Ecosystem — Full Pipeline           ║"
echo "║  Started: $TIMESTAMP                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

START_TOTAL=$(date +%s)

# Step 1: Extract data from 14.md
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 1/7: Extract repo data from 14.md → JSON catalog"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 scripts/extract_repos_from_14md.py
echo ""

# Step 2: Generate searchable HTML catalog
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 2/7: Generate searchable HTML catalog"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 scripts/catalog_generator.py
echo ""

# Step 3: Generate integration matrix
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 3/7: Generate integration matrix & roadmap"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 scripts/integration_matrix.py
echo ""

# Step 4: Star tracker — daily crawl
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 4/7: Star tracker — crawl GitHub stars (sample: 10)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 scripts/star_tracker.py crawl 10
echo ""

# Step 5: Generate trending dashboard
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 5/7: Generate trending dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 scripts/star_tracker.py dashboard
echo ""

# Step 6: Full crawl (if not recently done)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 6/7: Star tracker — full crawl (optional, use 'full')"
echo "  Skip for now — run 'python3 scripts/star_tracker.py full'"
echo "  to crawl all 564 repos (requires GITHUB_TOKEN)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 7: Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  STEP 7/7: Pipeline complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

END_TOTAL=$(date +%s)
DURATION=$((END_TOTAL - START_TOTAL))

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ PIPELINE COMPLETE                                       ║"
echo "║  Duration: ${DURATION}s                                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Generated files:"
echo "  📄 ai_ml_repo_catalog.json          — Structured JSON catalog"
echo "  📄 docs/catalog.html                — Searchable HTML catalog"
echo "  📄 docs/INTEGRATION_MATRIX.md       — Integration roadmap"
echo "  📄 docs/trending.html               — Trending star dashboard"
echo "  📄 scripts/clone_all_repos.sh       — Bash clone script"
echo "  📄 scripts/clone_all_repos.ps1      — PowerShell clone script"
echo "  📄 scripts/pip_install_tools.sh     — pip install script"
echo "  📄 scripts/star_tracker.py          — Star tracking system"
echo "  📄 scripts/setup_star_tracker.sh    — Cron setup script"
echo "  📄 data/star_history.db             — Star history (SQLite)"
echo "  📄 data/star_rankings.json          — Top 30 rankings"
echo "  📄 Readme/README_14.md              — 14.md summary"
echo ""
echo "Start the web server to view:"
echo "  python3 -m http.server 8080 --directory docs/"
echo "  → http://localhost:8080/catalog.html"
echo "  → http://localhost:8080/trending.html"
echo "  → http://localhost:8080/INTEGRATION_MATRIX.md"
