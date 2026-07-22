#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Star Tracker — Cron Job Setup
# ═══════════════════════════════════════════════════════════════
# Run this once to schedule daily star tracking at 6 AM UTC.
# Usage: bash scripts/setup_star_tracker.sh
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_PATH="$(which python3 || which python)"
LOG_DIR="$PROJECT_DIR/data/logs"

# Create log directory
mkdir -p "$LOG_DIR"

# Check for GitHub token
if [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️  No GITHUB_TOKEN set. API rate limit: 60 req/hr (688 repos need 688+ calls)."
    echo "   Set a token for 5000 req/hr:"
    echo "   export GITHUB_TOKEN='your_token_here'"
    echo ""
    echo "   Add to your ~/.bashrc or ~/.zshrc:"
    echo '   echo "export GITHUB_TOKEN=ghp_xxxxxxxxxxxx" >> ~/.bashrc'
    echo ""
fi

# Install the cron job
CRON_JOB="0 6 * * * cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_DIR/star_tracker.py full >> $LOG_DIR/star_tracker.log 2>&1"

# Check if crontab is available
if ! command -v crontab &> /dev/null; then
    echo "⚠️  crontab not found in this environment."
    echo "   To run manually, add this to your crontab:"
    echo "   $CRON_JOB"
    echo ""
    echo "📋 Or run once:"
    echo "   python $SCRIPT_DIR/star_tracker.py full"
    exit 0
fi

# Check if already installed
EXISTING=$(crontab -l 2>/dev/null | grep "star_tracker.py" || echo "")
if [ -n "$EXISTING" ]; then
    echo "⚠️  Star tracker cron job already exists. Updating..."
    (crontab -l 2>/dev/null | grep -v "star_tracker.py"; echo "$CRON_JOB") | crontab -
else
    echo "📅 Installing daily cron job (6 AM UTC)..."
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
fi

echo ""
echo "✅ Star tracker cron job installed!"
echo "   Runs daily at 6:00 AM UTC"
echo "   Logs: $LOG_DIR/star_tracker.log"
echo ""
echo "📋 Commands:"
echo "   Run once now:    python $SCRIPT_DIR/star_tracker.py full"
echo "   Test crawl (10): python $SCRIPT_DIR/star_tracker.py crawl 10"
echo "   View trends:     python $SCRIPT_DIR/star_tracker.py trends"
echo "   Generate dash:   python $SCRIPT_DIR/star_tracker.py dashboard"
echo "   Check rate lim:  python $SCRIPT_DIR/star_tracker.py rate"
echo ""
echo "📊 After first crawl, open:"
echo "   http://localhost:8080/trending.html"
