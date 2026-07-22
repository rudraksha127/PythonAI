#!/usr/bin/env python3
"""
Catalog Generator - Creates a searchable HTML web catalog from 14.md repo data
Output: docs/catalog.html - a standalone, searchable, filterable HTML page
"""

import json
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CATALOG_PATH = PROJECT_ROOT / "ai_ml_repo_catalog.json"
OUTPUT_DIR = PROJECT_ROOT / "docs"
OUTPUT_FILE = OUTPUT_DIR / "catalog.html"


def load_catalog() -> dict:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_html(catalog: dict) -> str:
    """Generate a standalone HTML page with search, filter, and sort functionality."""
    categories = catalog["categories"]
    all_repos = catalog["all_repos"]
    glossary = catalog.get("glossary", [])

    # Build category filter options
    cat_options = "".join(f'<option value="{c["slug"]}">{c["name"]} ({len(c["repos"])})</option>'
                         for c in sorted(categories, key=lambda x: len(x["repos"]), reverse=True))

    # Build repo data as JSON for JavaScript
    repos_json = json.dumps([
        {
            "name": r.get("name", r["full_name"].split("/")[-1]),
            "full_name": r["full_name"],
            "category": r.get("category", "uncategorized"),
            "clone_url": r.get("clone_url", f"https://github.com/{r['full_name']}.git"),
            "stars": r.get("details", {}).get("stars", ""),
            "params": r.get("details", {}).get("params", ""),
            "description": r.get("details", {}).get("description", "") or r.get("details", {}).get("specialty", "") or r.get("details", {}).get("key feature", "") or "",
            "license": r.get("details", {}).get("license", ""),
        }
        for r in all_repos
    ])

    glossary_json = json.dumps(glossary)

    # Note: Use JS variable placeholders (__REPOS__) instead of f-string interpolation
    # to avoid conflicts between Python f-string {} and JavaScript template literal ${}
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI/ML GitHub Ultimate Catalog</title>
<style>
:root { --bg: #0a0a0b; --surface: #111114; --elevated: #18181c; --border: #27272c;
  --text: #fafafa; --secondary: #a1a1aa; --muted: #71717a; --accent: #5b5bff; --success: #22c55e; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
.header { text-align: center; padding: 40px 0 20px; }
.header h1 { font-size: 2rem; background: linear-gradient(135deg, var(--accent), #06b6d4); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: var(--accent); }
.header p { color: var(--muted); margin-top: 8px; }
.stats { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; margin: 20px 0; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px 24px; text-align: center; min-width: 120px; }
.stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
.stat-card .label { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0; align-items: center; }
.filters input, .filters select { background: var(--surface); border: 1px solid var(--border);
  color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 0.9rem; }
.filters input { flex: 1; min-width: 200px; }
.filters select { cursor: pointer; }
.repo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 12px; margin-top: 16px; }
.repo-card { background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; transition: all 0.2s; cursor: pointer; }
.repo-card:hover { border-color: var(--accent); transform: translateY(-1px); }
.repo-card .repo-name { font-size: 1rem; font-weight: 600; color: var(--text); }
.repo-card .repo-full { font-size: 0.8rem; color: var(--muted); margin-top: 2px; }
.repo-card .repo-desc { font-size: 0.85rem; color: var(--secondary); margin-top: 8px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.repo-card .repo-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.repo-card .badge { font-size: 0.7rem; padding: 2px 8px; border-radius: 4px;
  background: var(--elevated); color: var(--muted); border: 1px solid var(--border); }
.repo-card .badge.stars { color: #f59e0b; }
.repo-card .badge.params { color: #06b6d4; }
.repo-card .badge.license { color: #22c55e; }
.repo-card .repo-actions { margin-top: 10px; display: flex; gap: 8px; }
.repo-card .repo-actions a { text-decoration: none; font-size: 0.8rem;
  padding: 4px 10px; border-radius: 4px; background: var(--elevated);
  color: var(--secondary); border: 1px solid var(--border); transition: all 0.15s; }
.repo-card .repo-actions a:hover { background: var(--accent); color: white; border-color: var(--accent); }
.count-bar { color: var(--muted); font-size: 0.9rem; margin: 10px 0; }
.glossary { margin-top: 40px; }
.glossary h2 { font-size: 1.3rem; margin-bottom: 16px; color: var(--secondary); }
.glossary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 8px; }
.glossary-term { background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px 14px; }
.glossary-term .term { font-weight: 600; color: var(--accent); font-size: 0.9rem; }
.glossary-term .full { font-size: 0.8rem; color: var(--muted); }
.glossary-term .explain { font-size: 0.85rem; color: var(--secondary); margin-top: 4px; }
@media (max-width: 768px) { .repo-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>AI/ML GitHub Ultimate Catalog</h1>
    <p id="headerDesc">Loading...</p>
  </div>

  <div class="stats" id="stats"></div>

  <div class="filters">
    <input type="text" id="search" placeholder="Search repos, descriptions, categories..." oninput="filterRepos()">
    <select id="categoryFilter" onchange="filterRepos()">
      <option value="all">All Categories</option>
      __CAT_OPTIONS__
    </select>
    <select id="sortBy" onchange="filterRepos()">
      <option value="name">Sort: Name</option>
      <option value="stars">Sort: Stars</option>
      <option value="category">Sort: Category</option>
    </select>
  </div>

  <div class="count-bar" id="countBar"></div>
  <div class="repo-grid" id="repoGrid"></div>

  <div class="glossary" id="glossarySection">
    <h2>Master Glossary (__GLOSSARY_COUNT__ terms)</h2>
    <div class="glossary-grid" id="glossaryGrid"></div>
  </div>
</div>

<script>
const repos = __REPOS_JSON__;
const glossary = __GLOSSARY_JSON__;

function renderStats() {
  const cats = [...new Set(repos.map(r => r.category))];
  const totalStars = repos.filter(r => r.stars).reduce((s, r) => {
    const num = parseInt(r.stars.toString().replace(/[^0-9]/g, ''));
    return s + (isNaN(num) ? 0 : num);
  }, 0);
  const cats = [...new Set(repos.map(r => r.category))];
  document.getElementById('headerDesc').textContent = repos.length + '+ repositories across ' + cats.length + ' categories — extracted from 14.md research document';
  document.getElementById('stats').innerHTML =
    '<div class="stat-card"><div class="num">' + repos.length + '</div><div class="label">Total Repos</div></div>' +
    '<div class="stat-card"><div class="num">' + cats.length + '</div><div class="label">Categories</div></div>' +
    '<div class="stat-card"><div class="num">' + (totalStars > 1000 ? (totalStars/1000).toFixed(0) + 'K' : totalStars) + '</div><div class="label">Combined Stars</div></div>' +
    '<div class="stat-card"><div class="num">' + glossary.length + '</div><div class="label">Glossary Terms</div></div>';
}

function renderGlossary() {
  const grid = document.getElementById('glossaryGrid');
  grid.innerHTML = glossary.map(t =>
    '<div class="glossary-term">' +
      '<div class="term">' + t.term + '</div>' +
      '<div class="full">' + t.full_form + '</div>' +
      '<div class="explain">' + t.explanation + '</div>' +
    '</div>'
  ).join('');
}

function filterRepos() {
  const query = document.getElementById('search').value.toLowerCase();
  const category = document.getElementById('categoryFilter').value;
  const sort = document.getElementById('sortBy').value;

  let filtered = repos.filter(r => {
    const matchSearch = !query || r.name.toLowerCase().includes(query) ||
      r.full_name.toLowerCase().includes(query) ||
      r.description.toLowerCase().includes(query) ||
      r.category.toLowerCase().includes(query);
    const matchCat = category === 'all' || r.category === category;
    return matchSearch && matchCat;
  });

  filtered.sort((a, b) => {
    if (sort === 'name') return a.name.localeCompare(b.name);
    if (sort === 'stars') {
      const sa = parseInt(a.stars.toString().replace(/[^0-9]/g, '')) || 0;
      const sb = parseInt(b.stars.toString().replace(/[^0-9]/g, '')) || 0;
      return sb - sa;
    }
    return a.category.localeCompare(b.category);
  });

  document.getElementById('countBar').textContent = 'Showing ' + filtered.length + ' of ' + repos.length + ' repositories';
  const grid = document.getElementById('repoGrid');
  grid.innerHTML = filtered.map(r => {
    const ghUrl = 'https://github.com/' + r.full_name;
    const stars = r.stars ? '<span class="badge stars">&#11088; ' + r.stars + '</span>' : '';
    const params = r.params ? '<span class="badge params">' + r.params + '</span>' : '';
    const license = r.license ? '<span class="badge license">' + r.license + '</span>' : '';
    return '<div class="repo-card">' +
      '<div class="repo-name">' + r.name + '</div>' +
      '<div class="repo-full">' + r.full_name + ' <span class="badge">' + r.category + '</span></div>' +
      '<div class="repo-desc">' + (r.description || 'No description available') + '</div>' +
      '<div class="repo-meta">' + stars + params + license + '</div>' +
      '<div class="repo-actions">' +
        '<a href="' + ghUrl + '" target="_blank">GitHub</a>' +
        '<a href="' + r.clone_url + '" target="_blank">Clone URL</a>' +
      '</div>' +
    '</div>';
  }).join('');
}

renderStats();
renderGlossary();
filterRepos();
</script>
</body>
</html>"""

    # Substitute placeholders
    html = html_template.replace("__REPOS_JSON__", repos_json)
    html = html.replace("__GLOSSARY_JSON__", glossary_json)
    html = html.replace("__CAT_OPTIONS__", cat_options)
    html = html.replace("__GLOSSARY_COUNT__", str(len(glossary)))

    return html


def main():
    print("Loading catalog data...")
    catalog = load_catalog()
    print(f"   Loaded {catalog['total_repos']} repos across {len(catalog['categories'])} categories")

    print("Generating HTML catalog...")
    html = generate_html(catalog)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Saved to {OUTPUT_FILE}")
    print(f"   File size: {len(html):,} bytes")
    print("\nOpen the catalog in your browser:")
    print(f"   file://{OUTPUT_FILE.absolute()}")


if __name__ == "__main__":
    main()
