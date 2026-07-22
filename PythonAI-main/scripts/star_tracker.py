#!/usr/bin/env python3
"""
Star Tracker — Daily GitHub star crawler for all 688 repos in the AI/ML catalog.
- Fetches star counts via GitHub API (with rate limiting)
- Stores historical snapshots in SQLite
- Calculates weekly trends and "top movers"
- Generates trending dashboard data

Usage:
  python scripts/star_tracker.py crawl       # Fetch latest stars (rate-limited ~5000/hr)
  python scripts/star_tracker.py trends      # Show this week's top movers
  python scripts/star_tracker.py dashboard   # Generate trending.html dashboard
  python scripts/star_tracker.py full        # Full pipeline: crawl → trends → dashboard
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CATALOG_PATH = PROJECT_ROOT / "ai_ml_repo_catalog.json"
DB_PATH = PROJECT_ROOT / "data" / "star_history.db"
DASHBOARD_PATH = PROJECT_ROOT / "docs" / "trending.html"
DATA_DIR = PROJECT_ROOT / "data"

# GitHub API — unauthenticated: 60 req/hr, authenticated: 5000 req/hr
# Set GITHUB_TOKEN env var for higher rate limits
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "ForgeAI-StarTracker/1.0"
}
if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

API_CALLS_MADE = 0
RATE_LIMIT_REMAINING = 5000 if GITHUB_TOKEN else 60


def load_catalog() -> dict:
    """Load the repo catalog JSON."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def init_db():
    """Initialize SQLite database for star history."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS star_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_name TEXT NOT NULL,
            full_name TEXT NOT NULL,
            stars INTEGER NOT NULL,
            forks INTEGER DEFAULT 0,
            open_issues INTEGER DEFAULT 0,
            snapshot_date TEXT NOT NULL,
            category TEXT DEFAULT '',
            UNIQUE(full_name, snapshot_date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshot_date ON star_snapshots(snapshot_date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_full_name ON star_snapshots(full_name)
    """)
    conn.commit()
    return conn


def fetch_repo_stats(full_name: str) -> Optional[Dict]:
    """Fetch star count and metadata for a single repo via GitHub API."""
    global API_CALLS_MADE, RATE_LIMIT_REMAINING

    # Check rate limit before making call
    if RATE_LIMIT_REMAINING <= 0:
        print(f"  ⚠️  Rate limit exhausted after {API_CALLS_MADE} calls. Waiting 60s...")
        time.sleep(65)
        check_rate_limit()
        if RATE_LIMIT_REMAINING <= 0:
            print("  ❌ Rate limit still exhausted. Stopping.")
            return None

    url = f"https://api.github.com/repos/{full_name}"
    req = urllib.request.Request(url, headers=GITHUB_HEADERS)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            API_CALLS_MADE += 1
            data = json.loads(resp.read().decode())
            
            # Update rate limit from headers
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining:
                RATE_LIMIT_REMAINING = int(remaining)
            
            return {
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "description": data.get("description", ""),
                "language": data.get("language", ""),
            }
    except urllib.error.HTTPError as e:
        API_CALLS_MADE += 1
        if e.code == 403:
            # Rate limited
            remaining = e.headers.get("X-RateLimit-Remaining", "0")
            RATE_LIMIT_REMAINING = int(remaining)
            print(f"  ⚠️  Rate limited (403) on {full_name}. Remaining: {RATE_LIMIT_REMAINING}")
            return None
        elif e.code == 404:
            print(f"  ⚠️  Not found (404): {full_name}")
            return {"stars": 0, "forks": 0, "open_issues": 0, "description": "", "language": ""}
        elif e.code == 301:
            print(f"  ⚠️  Moved (301): {full_name}")
            return None
        else:
            print(f"  ⚠️  HTTP {e.code}: {full_name}")
            return None
    except Exception as e:
        print(f"  ⚠️  Error: {full_name} — {e}")
        return None


def check_rate_limit():
    """Check remaining GitHub API rate limit."""
    global RATE_LIMIT_REMAINING
    url = "https://api.github.com/rate_limit"
    try:
        req = urllib.request.Request(url, headers=GITHUB_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            core = data.get("resources", {}).get("core", {})
            RATE_LIMIT_REMAINING = core.get("remaining", 0)
            reset_time = core.get("reset", 0)
            reset_dt = datetime.fromtimestamp(reset_time) if reset_time else datetime.now()
            print(f"  📊 Rate limit: {RATE_LIMIT_REMAINING} remaining (resets at {reset_dt.strftime('%H:%M:%S')})")
            return RATE_LIMIT_REMAINING
    except Exception as e:
        print(f"  ⚠️  Could not check rate limit: {e}")
        return RATE_LIMIT_REMAINING


def crawl_all_repos(catalog: dict, conn: sqlite3.Connection, limit: int = None):
    """Crawl all repos from catalog and store star snapshots."""
    all_repos = catalog["all_repos"]
    total = limit or len(all_repos)
    
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  Crawling star counts for {total}/{len(all_repos)} repos")
    print(f"  Date: {today}")
    print(f"  Auth: {'GitHub Token' if GITHUB_TOKEN else 'Unauthenticated (60/hr)'}")
    print(f"{'='*60}\n")
    
    # Check which repos already have a snapshot today
    cursor = conn.execute(
        "SELECT full_name FROM star_snapshots WHERE snapshot_date = ?", (today,)
    )
    already_done = set(row[0] for row in cursor.fetchall())
    
    repos_to_crawl = [r for r in all_repos[:total] if r["full_name"] not in already_done]
    skipped = len(all_repos[:total]) - len(repos_to_crawl)
    
    if skipped:
        print(f"  📌 {skipped} repos already crawled today. Skipping.\n")
    
    success = 0
    failed = 0
    skipped_count = skipped
    
    for i, repo in enumerate(repos_to_crawl):
        full_name = repo["full_name"]
        category = repo.get("category", "uncategorized")
        
        print(f"  [{i+1}/{len(repos_to_crawl)}] {full_name}...", end=" ", flush=True)
        
        stats = fetch_repo_stats(full_name)
        
        if stats is None:
            print("⏸️  (rate limit / moved)")
            failed += 1
            # If rate limited, stop crawling
            if RATE_LIMIT_REMAINING <= 0:
                remaining = len(repos_to_crawl) - i - 1
                print(f"\n  ⏹️  Rate limit hit. {remaining} repos skipped until next run.")
                skipped_count += remaining
                break
            continue
        
        conn.execute(
            """INSERT OR IGNORE INTO star_snapshots 
               (repo_name, full_name, stars, forks, open_issues, snapshot_date, category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (full_name.split("/")[-1], full_name, stats["stars"], 
             stats["forks"], stats["open_issues"], today, category)
        )
        conn.commit()
        
        print(f"⭐ {stats['stars']:,} stars")
        success += 1
        
        # Small delay to be nice to GitHub API
        time.sleep(0.1)
    
    print(f"\n{'='*60}")
    print(f"  Crawl complete!")
    print(f"  ✅ Success: {success}")
    print(f"  ⏹️  Skipped: {skipped_count}")
    print(f"  ❌ Failed:  {failed}")
    print(f"  📊 API calls: {API_CALLS_MADE}")
    print(f"{'='*60}\n")


def calculate_trends(conn: sqlite3.Connection) -> List[Dict]:
    """Calculate star growth trends (7-day and 30-day)."""
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Get latest snapshot per repo
    cursor = conn.execute("""
        SELECT s1.full_name, s1.stars, s1.category, s1.snapshot_date,
               s2.stars as stars_week_ago, s3.stars as stars_month_ago
        FROM star_snapshots s1
        LEFT JOIN star_snapshots s2 ON s1.full_name = s2.full_name AND s2.snapshot_date = ?
        LEFT JOIN star_snapshots s3 ON s1.full_name = s3.full_name AND s3.snapshot_date = ?
        WHERE s1.snapshot_date = ?
    """, (week_ago, month_ago, today))
    
    trends = []
    for row in cursor.fetchall():
        full_name, stars, category, date, stars_week_ago, stars_month_ago = row
        
        growth_7d = (stars or 0) - (stars_week_ago or 0)
        growth_30d = (stars or 0) - (stars_month_ago or 0)
        growth_rate_7d = ((growth_7d / (stars_week_ago or 1)) * 100) if stars_week_ago else 0
        
        trends.append({
            "full_name": full_name,
            "stars": stars or 0,
            "growth_7d": growth_7d,
            "growth_30d": growth_30d,
            "growth_rate_7d": round(growth_rate_7d, 1),
            "category": category or "uncategorized",
            "snapshot_date": date,
        })
    
    return trends


def get_trending_report(trends: List[Dict], top_n: int = 30) -> str:
    """Generate a markdown trending report."""
    # Sort by 7-day growth descending
    sorted_trends = sorted(trends, key=lambda t: t["growth_7d"], reverse=True)
    
    lines = []
    lines.append("# ⭐ AI/ML GitHub Star Trends — Weekly Report")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total repos tracked: {len(trends)}")
    lines.append("")
    
    # Top 30 by 7-day growth
    lines.append(f"## 📈 Top {top_n} by Weekly Star Growth")
    lines.append("")
    lines.append("| Rank | Repo | Stars | +7d | +30d | % Growth | Category |")
    lines.append("|------|------|-------|-----|------|----------|----------|")
    
    for i, t in enumerate(sorted_trends[:top_n], 1):
        name = t["full_name"]
        stars = f"{t['stars']:,}"
        g7 = f"+{t['growth_7d']:,}" if t['growth_7d'] > 0 else str(t['growth_7d'])
        g30 = f"+{t['growth_30d']:,}" if t['growth_30d'] > 0 else str(t['growth_30d'])
        rate = f"{t['growth_rate_7d']:.1f}%"
        cat = t["category"][:20]
        lines.append(f"| {i} | [{name}](https://github.com/{name}) | {stars} | {g7} | {g30} | {rate} | {cat} |")
    
    lines.append("")
    
    # Category breakdown
    lines.append("## 📊 Category Breakdown (Total Stars)")
    lines.append("")
    cat_stats = {}
    for t in trends:
        cat = t["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"total_stars": 0, "growth_7d": 0, "count": 0}
        cat_stats[cat]["total_stars"] += t["stars"]
        cat_stats[cat]["growth_7d"] += t["growth_7d"]
        cat_stats[cat]["count"] += 1
    
    lines.append("| Category | Repos | Total Stars | Weekly Growth | Avg Stars |")
    lines.append("|----------|-------|-------------|---------------|-----------|")
    for cat, stats in sorted(cat_stats.items(), key=lambda x: x[1]["total_stars"], reverse=True):
        total = f"{stats['total_stars']:,}"
        growth = f"+{stats['growth_7d']:,}" if stats['growth_7d'] > 0 else str(stats['growth_7d'])
        avg = stats['total_stars'] // max(stats['count'], 1)
        avg_s = f"{avg:,}"
        lines.append(f"| {cat[:25]} | {stats['count']} | {total} | {growth} | {avg_s} |")
    
    lines.append("")
    lines.append("---")
    lines.append("*Daily updates via ForgeAI Star Tracker*")
    
    return "\n".join(lines)


def generate_dashboard_html(trends: List[Dict]) -> str:
    """Generate the trending dashboard HTML page."""
    sorted_trends = sorted(trends, key=lambda t: t["growth_7d"], reverse=True)
    top_movers = sorted_trends[:50]
    
    # Category stats
    cat_stats = {}
    for t in trends:
        cat = t["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"total_stars": 0, "growth_7d": 0, "count": 0}
        cat_stats[cat]["total_stars"] += t["stars"]
        cat_stats[cat]["growth_7d"] += t["growth_7d"]
        cat_stats[cat]["count"] += 1
    
    total_stars = sum(t["stars"] for t in trends)
    total_growth = sum(t["growth_7d"] for t in trends)
    
    repos_json = json.dumps(top_movers)
    cats_json = json.dumps(cat_stats)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI/ML GitHub Star Trends</title>
<style>
:root {{ --bg: #0a0a0b; --surface: #111114; --elevated: #18181c;
  --border: #27272c; --text: #fafafa; --secondary: #a1a1aa;
  --muted: #71717a; --accent: #5b5bff; --success: #22c55e; --warning: #f59e0b; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 30px 0 20px; }}
.header h1 {{ font-size: 1.8rem; background: linear-gradient(135deg, var(--accent), #06b6d4);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }}
.header p {{ color: var(--muted); margin-top: 6px; }}
.stats-row {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin: 16px 0; }}
.stat-card {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 20px; text-align: center; min-width: 130px; }}
.stat-card .num {{ font-size: 1.4rem; font-weight: 700; color: var(--accent);
  font-variant-numeric: tabular-nums; }}
.stat-card .label {{ font-size: 0.78rem; color: var(--muted); margin-top: 2px; }}
.stat-card .num.green {{ color: var(--success); }}
.stat-card .num.warning {{ color: var(--warning); }}
.filters {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; align-items: center; }}
.filters input, .filters select {{ background: var(--surface); border: 1px solid var(--border);
  color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 0.9rem; }}
.filters input {{ flex: 1; min-width: 200px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th {{ text-align: left; padding: 10px 12px; font-size: 0.8rem; color: var(--muted);
  border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; }}
th:hover {{ color: var(--accent); }}
td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
tr:hover td {{ background: var(--elevated); }}
.repo-link {{ color: var(--accent); text-decoration: none; }}
.repo-link:hover {{ text-decoration: underline; }}
.stars-num {{ font-variant-numeric: tabular-nums; }}
.growth-pos {{ color: var(--success); }}
.growth-neg {{ color: #ef4444; }}
.growth-zero {{ color: var(--muted); }}
.badge {{ font-size: 0.7rem; padding: 2px 8px; border-radius: 4px;
  background: var(--elevated); color: var(--muted); border: 1px solid var(--border);
  display: inline-block; white-space: nowrap; }}
.pulse {{ animation: pulse 2s infinite; }}
@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
@media (max-width: 768px) {{ table {{ font-size: 0.8rem; }} td, th {{ padding: 6px 8px; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>⭐ AI/ML Star Trends</h1>
    <p>Tracking {len(trends)} repos across {len(cat_stats)} categories · {datetime.now().strftime('%B %d, %Y')}</p>
  </div>

  <div class="stats-row">
    <div class="stat-card"><div class="num">{total_stars:,}</div><div class="label">Total Stars</div></div>
    <div class="stat-card"><div class="num green">+{total_growth:,}</div><div class="label">Weekly Growth</div></div>
    <div class="stat-card"><div class="num">{len(trends)}</div><div class="label">Repos Tracked</div></div>
    <div class="stat-card"><div class="num">{len(cat_stats)}</div><div class="label">Categories</div></div>
  </div>

  <div class="filters">
    <input type="text" id="search" placeholder="Search repos..." oninput="filterTable()">
    <select id="sortSelect" onchange="sortTable()">
      <option value="growth_7d">Sort: Weekly Growth</option>
      <option value="stars">Sort: Total Stars</option>
      <option value="growth_rate">Sort: Growth Rate %</option>
      <option value="name">Sort: Name</option>
    </select>
    <label style="color:var(--muted);font-size:0.85rem;">
      <input type="checkbox" id="onlyPositive" onchange="filterTable()"> Growing only
    </label>
  </div>

  <table id="trendsTable">
    <thead>
      <tr>
        <th>#</th>
        <th>Repository</th>
        <th style="text-align:right">Stars</th>
        <th style="text-align:right">+7 Days</th>
        <th style="text-align:right">+30 Days</th>
        <th style="text-align:right">Growth %</th>
        <th>Category</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>

  <div style="margin-top:30px;text-align:center;color:var(--muted);font-size:0.8rem;">
    ↑ Click column headers to sort · Data updates daily via GitHub API
  </div>
</div>

<script>
const repos = {repos_json};
let currentSort = 'growth_7d';
let sortAsc = false;

function fmtNum(n) {{ return n.toLocaleString(); }}

function growthClass(val) {{
  if (val > 0) return 'growth-pos';
  if (val < 0) return 'growth-neg';
  return 'growth-zero';
}}

function fmtGrowth(val) {{
  const prefix = val > 0 ? '+' : '';
  return `<span class="${{growthClass(val)}}">${{prefix}}${{fmtNum(val)}}</span>`;
}}

function filterTable() {{
  const query = document.getElementById('search').value.toLowerCase();
  const onlyPos = document.getElementById('onlyPositive').checked;

  let filtered = repos.filter(r => {{
    const matchName = r.full_name.toLowerCase().includes(query);
    const matchPos = !onlyPos || r.growth_7d > 0;
    return matchName && matchPos;
  }});

  renderTable(filtered);
}}

function sortTable() {{
  const sortKey = document.getElementById('sortSelect').value;
  if (sortKey === currentSort) sortAsc = !sortAsc;
  else {{ currentSort = sortKey; sortAsc = false; }}
  filterTable();
}}

function renderTable(data) {{
  data.sort((a, b) => {{
    let cmp = 0;
    if (currentSort === 'growth_7d') cmp = b.growth_7d - a.growth_7d;
    else if (currentSort === 'stars') cmp = b.stars - a.stars;
    else if (currentSort === 'growth_rate') cmp = b.growth_rate_7d - a.growth_rate_7d;
    else if (currentSort === 'name') cmp = a.full_name.localeCompare(b.full_name);
    if (sortAsc) cmp = -cmp;
    return cmp;
  }});

  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = data.map((r, i) =>
    '<tr>' +
      '<td>' + (i + 1) + '</td>' +
      '<td><a class="repo-link" href="https://github.com/' + r.full_name + '" target="_blank">' + r.full_name + '</a></td>' +
      '<td style="text-align:right" class="stars-num">' + fmtNum(r.stars) + '</td>' +
      '<td style="text-align:right" class="stars-num">' + fmtGrowth(r.growth_7d) + '</td>' +
      '<td style="text-align:right" class="stars-num">' + fmtGrowth(r.growth_30d) + '</td>' +
      '<td style="text-align:right" class="stars-num">' + fmtGrowth(r.growth_rate_7d) + '%</td>' +
      '<td><span class="badge">' + r.category + '</span></td>' +
    '</tr>'
  ).join('');
}}

// Initial render
filterTable();
</script>
</body>
</html>"""
    return html


def do_crawl(limit: int = None):
    """Run the full crawl pipeline."""
    print("=" * 60)
    print("  ⭐ ForgeAI Star Tracker — Daily Crawl")
    print("=" * 60)
    
    # Check for GitHub token - critical for 688 repos (need 5000 req/hr)
    if not GITHUB_TOKEN:
        total = limit or 688
        est_hours = total / 60.0
        print(f"  ⚠️  No GITHUB_TOKEN set! Rate limit: 60 req/hr")
        print(f"  ⚠️  {total} repos will take ~{est_hours:.1f} hours")
        print(f"  ⚠️  Set GITHUB_TOKEN env var for 5000 req/hr")
        print(f"  ⚠️  Continuing with 60 req/hr... (Ctrl+C to cancel)")
        print()
    
    catalog = load_catalog()
    print(f"  Loaded catalog: {catalog['total_repos']} repos")
    
    conn = init_db()
    print(f"  Database: {DB_PATH}")
    
    check_rate_limit()
    crawl_all_repos(catalog, conn, limit=limit)
    conn.close()
    
    print("\n  📋 Run `python scripts/star_tracker.py dashboard` to generate the HTML dashboard.")


def do_trends(top_n: int = 30):
    """Show trending report."""
    conn = init_db()
    trends = calculate_trends(conn)
    conn.close()
    
    if not trends:
        print("No trend data available. Run `python scripts/star_tracker.py crawl` first.")
        return
    
    report = get_trending_report(trends, top_n=top_n)
    
    # Save to docs
    report_path = PROJECT_ROOT / "docs" / "TRENDING_REPORT.md"
    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(report)
    print(f"\n📝 Report saved to: {report_path}")


def do_dashboard():
    """Generate the trending dashboard HTML."""
    conn = init_db()
    trends = calculate_trends(conn)
    conn.close()
    
    if not trends:
        print("No trend data available. Run `python scripts/star_tracker.py crawl` first.")
        return
    
    html = generate_dashboard_html(trends)
    os.makedirs(DASHBOARD_PATH.parent, exist_ok=True)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Dashboard generated: {DASHBOARD_PATH}")
    print(f"   Open: http://localhost:8080/trending.html")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1]
    
    if command == "crawl":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
        do_crawl(limit=limit)
    
    elif command == "trends":
        top_n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
        do_trends(top_n=top_n)
    
    elif command == "dashboard":
        do_dashboard()
    
    elif command == "full":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
        do_crawl(limit=limit)
        do_trends()
        do_dashboard()
    
    elif command == "rate":
        remaining = check_rate_limit()
        print(f"Rate limit remaining: {remaining}")
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
