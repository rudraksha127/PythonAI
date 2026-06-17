#!/usr/bin/env python3
"""
Extract Repository Data from 14.md -> Structured JSON Catalog
Captures: 25 categories, star rankings, glossary, clone URLs
"""

import re
import json
import os
from pathlib import Path
from typing import Dict, List

INPUT_FILE = Path(__file__).parent.parent / "14.md"
OUTPUT_FILE = Path(__file__).parent.parent / "ai_ml_repo_catalog.json"

# All 25 categories from the document
CATEGORY_PATTERNS = [
    (r"# 1\..*FOUNDATION LLMs", "foundation-llms"),
    (r"# 2\..*INFERENCE ENGINES", "inference-engines"),
    (r"# 3\..*FINE-TUNING", "fine-tuning"),
    (r"# 4\..*AGENTIC AI", "agentic-ai"),
    (r"# 5\..*MCP SERVERS", "mcp-servers"),
    (r"# 6\..*AGENTIC CODING CLI", "agentic-cli-tools"),
    (r"# 7\..*VECTOR DATABASES", "vector-databases"),
    (r"# 8\..*RAG FRAMEWORKS", "rag-frameworks"),
    (r"# 9\..*CHAT UIS", "chat-uis"),
    (r"# 10\..*GENERATIVE AI", "generative-ai"),
    (r"# 11\..*ML FRAMEWORKS", "ml-frameworks"),
    (r"# 12\..*DATASETS", "datasets"),
    (r"# 13\..*QUANTIZATION", "quantization"),
    (r"# 14\..*EVALUATION", "evaluation"),
    (r"# 15\..*MODEL SERVING", "model-serving"),
    (r"# 16\..*MULTIMODAL", "multimodal"),
    (r"# 17\..*RESEARCH PAPERS", "research-papers"),
    (r"# 18\..*REINFORCEMENT LEARNING", "reinforcement-learning"),
    (r"# 19\..*AI SAFETY", "ai-safety"),
    (r"# 20\..*LLM TOOLCHAINS", "llm-toolchains"),
    (r"# 21\..*LEARNING RESOURCES", "learning-resources"),
    (r"# 22\..*ORCHESTRATION", "orchestration"),
    (r"# 23\..*EMBEDDINGS", "embeddings"),
    (r"# 24\..*MULTILINGUAL", "multilingual"),
    (r"# 25\..*ARCHITECTURE VARIANTS", "architecture-variants"),
]

KNOWN_PIP_PACKAGES = {
    # inference
    "vllm": "vllm", "sglang": "sglang", "litellm": "litellm",
    "gpt4all": "gpt4all", "exllamav2": "exllamav2",
    # finetuning
    "peft": "peft", "trl": "trl", "unsloth": "unsloth",
    "flash-attention": "flash-attention", "bitsandbytes": "bitsandbytes",
    "qlora": "qlora", "llama-factory": "llama-factory",
    # agents
    "langchain": "langchain", "langgraph": "langgraph",
    "pydantic-ai": "pydantic-ai", "phidata": "phidata",
    "swarm": "openai-swarm", "camel": "camel-ai", "crewai": "crewai",
    "openai-agents-sdk": "openai-agents",
    # RAG
    "llama-index": "llama-index", "haystack": "haystack",
    "ragas": "ragas", "unstructured": "unstructured",
    "chonkie": "chonkie", "mem0": "mem0ai",
    # vector dbs
    "chroma": "chromadb", "faiss": "faiss-cpu",
    "lancedb": "lancedb", "usearch": "usearch", "annoy": "annoy",
    # ML frameworks
    "transformers": "transformers", "datasets": "datasets",
    "sentence-transformers": "sentence-transformers",
    "scikit-learn": "scikit-learn", "xgboost": "xgboost",
    "lightgbm": "lightgbm", "ultralytics": "ultralytics",
    "optuna": "optuna", "wandb": "wandb", "mlflow": "mlflow",
    # tools
    "instructor": "instructor", "outlines": "outlines",
    "guidance": "guidance", "tiktoken": "tiktoken",
    "pydantic": "pydantic", "spacy": "spacy", "nltk": "nltk",
    "fastapi": "fastapi",
    # evaluation
    "deepeval": "deepeval", "lm-eval": "lm-eval",
    # data
    "beautifulsoup": "beautifulsoup4", "scrapy": "scrapy",
    "crawl4ai": "crawl4ai", "duckduckgo-search": "duckduckgo_search",
    "docling": "docling", "marker": "marker",
    "browser-use": "browser-use",
    # UI
    "gradio": "gradio", "streamlit": "streamlit", "chainlit": "chainlit",
    # speech
    "whisper": "openai-whisper", "faster-whisper": "faster-whisper",
    "bark": "bark", "tts": "TTS", "openvoice": "openvoice",
    "speechbrain": "speechbrain",
    # image
    "diffusers": "diffusers",
    # safety
    "guardrails": "guardrails-ai", "llm-guard": "llm-guard",
    # monitoring
    "langfuse": "langfuse", "helicone": "helicone",
    "traceloop": "openllmetry",
    # quantization
    "autoawq": "autoawq", "auto-gptq": "auto-gptq",
    "optimum": "optimum",
    # deep learning
    "pytorch": "torch", "tensorflow": "tensorflow",
    "jax": "jax", "keras": "keras", "mlx": "mlx",
}


def read_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_sections(text: str) -> List[Dict]:
    """Extract all sections with their content and category mapping."""
    sections = []
    lines = text.split("\n")
    current_cat = "uncategorized"
    current_sub = ""
    section_start = 0

    for i, line in enumerate(lines):
        for pattern, slug in CATEGORY_PATTERNS:
            if re.match(pattern, line, re.IGNORECASE):
                if i > section_start:
                    sections.append({"category": current_cat, "subcategory": current_sub,
                                     "start": section_start, "end": i, "lines": lines[section_start:i]})
                current_cat = slug
                current_sub = ""
                section_start = i
                break
        if line.startswith("###") and not line.startswith("####"):
            current_sub = line.replace("###", "").strip()
    
    if section_start < len(lines):
        sections.append({"category": current_cat, "subcategory": current_sub,
                         "start": section_start, "end": len(lines), "lines": lines[section_start:]})
    return sections


def extract_github_repos_from_section(section_lines: List[str]) -> List[Dict]:
    """Extract GitHub repositories from markdown table rows and clone commands."""
    repos = []
    global MCP_SERVER_MAP
    if not MCP_SERVER_MAP:
        MCP_SERVER_MAP.update(load_mcp_mapping())
    
    text = "\n".join(section_lines)
    
    # Pattern 1: git clone URLs in code blocks
    for match in re.finditer(r'git clone https://github\.com/([^/\s]+/[^/\s\)\"]+)', text):
        path = match.group(1).rstrip(".'\"")
        parts = path.split("/")
        if len(parts) >= 2:
            fn = f"{parts[0]}/{parts[1]}"
            if not any(r["full_name"] == fn for r in repos):
                repos.append({"full_name": fn, "owner": parts[0], "name": parts[1],
                              "clone_url": f"https://github.com/{fn}.git",
                              "source": "clone_command",
                              "stars": extract_stars_from_context(text, fn)})
    
    # Pattern 2: github.com/owner/repo in markdown links
    for match in re.finditer(r'https://github\.com/([^/\s]+/[^/\s\)\]\"\s]+)', text):
        path = match.group(1).rstrip(".'\"")
        parts = path.split("/")
        if len(parts) >= 2:
            # Handle subdirectory paths like owner/repo/tree/main/src/... -> owner/repo
            fn = f"{parts[0]}/{parts[1]}"
            name = parts[1].replace(")", "").replace("]", "").strip()
            if not any(r["full_name"] == fn for r in repos):
                repos.append({"full_name": fn, "owner": parts[0], "name": name,
                              "clone_url": f"https://github.com/{fn}.git",
                              "source": "link",
                              "stars": extract_stars_from_context(text, fn)})
    
    # Pattern 3: MCP sub-tables and similar tables (| **Name** | ... | Clone |)
    # Handles: same repo refs, subdirectory paths, tables with/without clone columns
    lines = text.split("\n")
    in_sub_table = False
    last_clone_url = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect table start: | --- | --- | pattern
        if stripped.startswith("|") and "---" in stripped and "|" in stripped[1:]:
            in_sub_table = True
            continue
        if not in_sub_table:
            continue
        # Check if this is still a table row
        if not stripped.startswith("|"):
            in_sub_table = False
            last_clone_url = None
            continue
        # Skip table header rows
        if "Server" in stripped or "Model" in stripped or "Framework" in stripped:
            if "---" not in stripped:
                continue
        
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]  # Remove empty cells from split
        
        if len(cells) >= 2:
            first_cell = cells[0].replace("**", "")
            last_cell = cells[-1] if len(cells) >= 4 else ""
            
            # Check for clone URL in last cell
            clone_match = re.search(r'git clone https://github\.com/([^/\s]+/[^/\s\)\"]+)', last_cell)
            if clone_match:
                path = clone_match.group(1).rstrip(".'\"")
                # Handle subdirectory paths
                parts = path.split("/")
                if len(parts) >= 2:
                    fn = f"{parts[0]}/{parts[1]}"
                    last_clone_url = f"https://github.com/{fn}.git"
                    if not any(r["full_name"] == fn for r in repos):
                        repos.append({"full_name": fn, "owner": parts[0], "name": parts[1],
                                      "clone_url": last_clone_url,
                                      "source": "sub_table_clone",
                                      "stars": extract_stars_from_context(text, fn)})
            elif "same repo" in last_cell.lower() or "same" in last_cell.lower():
                # Inherit the last seen clone URL
                if last_clone_url:
                    # Extract repo name from URL
                    url_parts = last_clone_url.rstrip(".git").split("/")
                    if len(url_parts) >= 2:
                        owner = url_parts[-2]
                        repo_name = url_parts[-1]
                        fn = f"{owner}/{repo_name}"
                        if not any(r["full_name"] == fn for r in repos):
                            repos.append({"full_name": fn, "owner": owner, "name": repo_name,
                                          "clone_url": last_clone_url,
                                          "source": "sub_table_same_repo",
                                          "stars": extract_stars_from_context(text, fn)})
            else:
                # Check MCP server name mapping first
                server_name = first_cell.strip().lower()
                mapped = MCP_SERVER_MAP.get(server_name, {})
                if mapped:
                    fn = mapped["full_name"]
                    if not any(r["full_name"] == fn for r in repos):
                        parts = fn.split("/")
                        repos.append({"full_name": fn, "owner": parts[0], "name": parts[1],
                                      "clone_url": mapped.get("clone_url", f"https://github.com/{fn}.git"),
                                      "source": "mcp_mapping",
                                      "stars": extract_stars_from_context(text, fn)})
                        last_clone_url = mapped.get("clone_url", f"https://github.com/{fn}.git")
                # Check if the last cell contains a full github URL (not git clone)
                url_match = re.search(r'https://github\.com/([^/\s]+/[^/\s\)\]\"\s]+)', last_cell)
                if url_match:
                    path = url_match.group(1).rstrip(".'\")")
                    parts = path.split("/")
                    if len(parts) >= 2:
                        fn = f"{parts[0]}/{parts[1]}"
                        last_clone_url = f"https://github.com/{fn}.git"
                        if not any(r["full_name"] == fn for r in repos):
                            repos.append({"full_name": fn, "owner": parts[0], "name": parts[1],
                                          "clone_url": last_clone_url,
                                          "source": "sub_table_url",
                                          "stars": extract_stars_from_context(text, fn)})
                # Also try to extract owner/repo from the first cell
                elif "/" in first_cell and len(first_cell.split("/")) == 2:
                    parts = first_cell.split("/")
                    owner, name = parts[0], parts[1]
                    if len(owner) > 2 and len(name) > 1 and all(c.isalnum() or c in "-_." for c in owner+name):
                        fn = f"{owner}/{name}"
                        if not any(r["full_name"] == fn for r in repos):
                            repos.append({"full_name": fn, "owner": owner, "name": name,
                                          "clone_url": f"https://github.com/{fn}.git",
                                          "source": "sub_table_name",
                                          "stars": extract_stars_from_context(text, fn)})
    
    return repos


def extract_stars_from_context(text: str, repo_name: str) -> str:
    """Try to extract star count from nearby text."""
    idx = text.find(repo_name)
    if idx < 0:
        return ""
    context = text[max(0, idx-200):idx+200]
    star_match = re.search(r'([⭐*]\s*)(\d+\.?\d*)(k|K)?', context)
    if star_match:
        count = star_match.group(2)
        suffix = star_match.group(3) or ""
        return f"{count}{suffix}"
    return ""


def extract_all_repos(text: str) -> Dict:
    """Extract all repos from the document organized by category."""
    sections = extract_sections(text)
    
    # First pass: extract categories and their repos
    category_repos = {}
    all_seen = set()
    
    for section in sections:
        cat = section["category"]
        if cat not in category_repos:
            category_repos[cat] = {"slug": cat, "name": cat.replace("-", " ").title(), "repos": []}
        
        repos = extract_github_repos_from_section(section["lines"])
        for repo in repos:
            if repo["full_name"] not in all_seen:
                all_seen.add(repo["full_name"])
                category_repos[cat]["repos"].append(repo)
    
    return category_repos, all_seen


def extract_uncategorized_globs(text: str, seen: set) -> List[Dict]:
    """Extract repos from the global bash script and other sections not in categories."""
    extras = []
    
    # Extract from the ULTIMATE QUICK-CLONE BASH SCRIPT section
    bash_section = text.split("# ULTIMATE QUICK-CLONE BASH SCRIPT")
    if len(bash_section) > 1:
        bash_text = bash_section[1]
        for match in re.finditer(r'git clone https://github\.com/([^/\s]+/[^/\s\)\"]+)', bash_text):
            path = match.group(1).rstrip(".'\"")
            parts = path.split("/")
            if len(parts) >= 2:
                fn = f"{parts[0]}/{parts[1]}"
                if fn not in seen:
                    seen.add(fn)
                    extras.append({"full_name": fn, "owner": parts[0], "name": parts[1],
                                   "clone_url": f"https://github.com/{fn}.git",
                                   "source": "bash_script", "category": "from-bash-script"})
    
    return extras


def extract_star_rankings(text: str) -> List[Dict]:
    """Extract the Top 30 star power rankings."""
    rankings = []
    idx = text.find("# 🏆 STAR POWER RANKINGS")
    if idx < 0:
        idx = text.find("STAR POWER RANKINGS")
    if idx < 0:
        return rankings
    
    lines = text[idx:idx+4000].split("\n")
    # The first --- is the one right before the star rankings (not inside table rows)
    # Skip until we see the table header separator which contains ----
    found_sep = False
    for line in lines:
        stripped = line.strip()
        # Skip standalone --- dividers before the table
        if stripped == "---" and not found_sep:
            continue
        # Found the table separator line
        if "----" in stripped:
            found_sep = True
            continue
        # Stop at standalone --- divider after table
        if stripped == "---" and found_sep:
            break
        if not found_sep:
            continue
        match = re.match(r'^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*[⭐*]\s*(\d+)\s*k?\s*\|\s*([^|]+)\s*\|$', stripped)
        if match:
            rank = int(match.group(1))
            name = match.group(2).strip().replace("**", "")
            stars_raw = match.group(3).strip()
            cat = match.group(4).strip().replace("**", "")
            stars = int(stars_raw) * 1000
            rankings.append({"rank": rank, "name": name, "stars": stars, "category": cat})
    
    print(f"  Star rankings found: {len(rankings)}")
    return rankings


def extract_glossary(text: str) -> List[Dict]:
    """Extract glossary terms."""
    terms = []
    for header in ["# 📖 MASTER GLOSSARY", "# MASTER GLOSSARY", "MASTER GLOSSARY"]:
        idx = text.find(header)
        if idx >= 0:
            break
    if idx < 0:
        return terms
    
    section = text[idx:idx+5000]
    # Split on a standalone --- line divider (not inside table rows)
    lines = section.split("\n")
    in_table = False
    for line in lines:
        stripped = line.strip()
        # Skip the table header/separator lines
        if stripped.startswith("|") and "---" in stripped:
            continue
        # Stop at standalone --- divider
        if stripped == "---" and in_table:
            break
        if stripped.startswith("|") and "**" in stripped:
            in_table = True
            match = re.match(r'^\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$', stripped)
            if match:
                terms.append({"term": match.group(1).strip(), "full_form": match.group(2).strip(),
                              "explanation": match.group(3).strip()})
    
    print(f"  Glossary terms found: {len(terms)}")
    return terms


def load_mcp_mapping() -> dict:
    """Load MCP server name → GitHub repo mapping."""
    mapping_path = Path(__file__).parent.parent / "data" / "mcp_server_mapping.json"
    if mapping_path.exists():
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("servers", {})
        except Exception as e:
            print(f"  Warning: Could not load MCP mapping: {e}")
    return {}


MCP_SERVER_MAP: dict = {}


def is_pip_installable(repo_name: str) -> bool:
    """Check if a repo has a known pip package."""
    base = repo_name.split("/")[-1].lower()
    return base in KNOWN_PIP_PACKAGES


def get_pip_package(repo_name: str) -> str:
    """Get the pip package name for a repo."""
    base = repo_name.split("/")[-1].lower()
    return KNOWN_PIP_PACKAGES.get(base, base)


def build_catalog(text: str) -> Dict:
    """Build complete structured catalog."""
    category_repos, seen = extract_all_repos(text)
    extras = extract_uncategorized_globs(text, seen)
    rankings = extract_star_rankings(text)
    glossary = extract_glossary(text)

    categories_list = sorted(category_repos.values(), key=lambda c: len(c["repos"]), reverse=True)
    all_repos = []
    for cat in categories_list:
        for repo in cat["repos"]:
            all_repos.append({
                "full_name": repo["full_name"],
                "category": cat["slug"],
                "clone_url": repo.get("clone_url", f"https://github.com/{repo['full_name']}.git"),
                "stars": repo.get("stars", ""),
                "pip_installable": is_pip_installable(repo["full_name"]),
                "pip_package": get_pip_package(repo["full_name"]) if is_pip_installable(repo["full_name"]) else "",
            })
    
    for repo in extras:
        all_repos.append({
            "full_name": repo["full_name"],
            "category": repo.get("category", "bash-script"),
            "clone_url": repo.get("clone_url", f"https://github.com/{repo['full_name']}.git"),
            "stars": "",
            "pip_installable": is_pip_installable(repo["full_name"]),
            "pip_package": get_pip_package(repo["full_name"]) if is_pip_installable(repo["full_name"]) else "",
        })

    return {
        "catalog_name": "AI/ML GitHub ULTIMATE DEEP DIVE",
        "source_file": "14.md",
        "total_categories": len(categories_list),
        "total_repos": len(all_repos),
        "total_glossary_terms": len(glossary),
        "total_star_rankings": len(rankings),
        "categories": categories_list,
        "all_repos": all_repos,
        "star_rankings": rankings,
        "glossary": glossary,
        # Summary stats
        "pip_installable_count": sum(1 for r in all_repos if r["pip_installable"]),
    }


def generate_bash_clone_script(catalog: Dict) -> str:
    """Generate bash clone script."""
    cats = {}
    for repo in catalog["all_repos"]:
        cats.setdefault(repo["category"], []).append(repo)

    lines = [
        "#!/bin/bash",
        "# AI/ML GitHub - Ultimate Clone Script",
        f"# {catalog['total_repos']} repos across {catalog['total_categories']} categories",
        "",
        'BASE_DIR="${1:-ai_ml_ultimate_repos}"',
        'mkdir -p "$BASE_DIR" && cd "$BASE_DIR"',
        "",
        'success=0; failed=0; skipped=0',
        'clone_repo() { local c="$1" u="$2" n="$3"; local d="$BASE_DIR/$c/$n"',
        '  if [ -d "$d/.git" ]; then echo "  [SKIP] $n"; skipped=$((skipped+1)); return 0; fi',
        '  mkdir -p "$BASE_DIR/$c"',
        '  if git clone --depth 1 "$u" "$d" 2>/dev/null; then echo "  [OK] $n"; success=$((success+1))',
        '  else echo "  [FAIL] $n"; failed=$((failed+1)); fi',
        '}',
        'START_TIME=$(date +%s)',
        "",
    ]
    for cat_slug, repos in sorted(cats.items()):
        lines.append(f"# {cat_slug.replace('-',' ').title()} ({len(repos)})")
        for r in repos:
            lines.append(f'clone_repo "{cat_slug}" "{r["clone_url"]}" "{r["full_name"].split("/")[-1]}"')
    lines.extend([
        'echo "Done: $success OK, $failed FAIL, $skipped SKIP ($(($(date +%s)-START_TIME))s)"',
    ])
    return "\n".join(lines)


def generate_powershell_script(catalog: Dict) -> str:
    """Generate PowerShell clone script."""
    cats = {}
    for repo in catalog["all_repos"]:
        cats.setdefault(repo["category"], []).append(repo)

    lines = [
        "# AI/ML GitHub - Ultimate Clone Script (PowerShell)",
        f"# {catalog['total_repos']} repos across {catalog['total_categories']} categories",
        "",
        "$ErrorActionPreference = 'Continue'",
        '$BASE = "ai_ml_ultimate_repos"',
        'if (-not (Test-Path $BASE)) { New-Item -ItemType Directory -Path $BASE -Force | Out-Null }',
        '$global:s=0; $global:f=0; $global:sk=0',
        'function Clone-Repo { param([string]$c,[string]$u,[string]$n)',
        '  $d = Join-Path $BASE $c; $t = Join-Path $d $n',
        '  if (Test-Path (Join-Path $t ".git")) { Write-Host "  [SKIP] $n" -ForegroundColor Yellow; $global:sk++; return }',
        '  if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }',
        '  try { git clone --depth 1 $u $t 2>&1 | Out-Null',
        '    if ($LASTEXITCODE -eq 0) { Write-Host "  [OK] $n" -ForegroundColor Green; $global:s++ }',
        '    else { Write-Host "  [FAIL] $n" -ForegroundColor Red; $global:f++ }',
        '  } catch { Write-Host "  [FAIL] $n - $_" -ForegroundColor Red; $global:f++ }',
        '}',
        '$totalStart = Get-Date',
        "",
    ]
    for cat_slug, repos in sorted(cats.items()):
        lines.append(f"# {cat_slug.replace('-',' ').title()} ({len(repos)})")
        for r in repos:
            lines.append(f'Clone-Repo "{cat_slug}" "{r["clone_url"]}" "{r["full_name"].split("/")[-1]}"')
    lines.extend([
        '',
        '$e = (Get-Date)-$totalStart',
        'Write-Host "Done: $($global:s) OK, $($global:f) FAIL, $($global:sk) SKIP ($([math]::Round($e.TotalMinutes,1)) min)"',
    ])
    return "\n".join(lines)


def generate_pip_install_script() -> str:
    """Generate pip install script."""
    cats = {
        "core":       "torch transformers datasets sentence-transformers scikit-learn fastapi pydantic tiktoken spacy nltk xgboost lightgbm",
        "inference":  "vllm sglang litellm gpt4all exllamav2",
        "finetuning": "peft trl unsloth flash-attention bitsandbytes",
        "agents":     "langchain langgraph pydantic-ai phidata crewai camel-ai instructor outlines guidance openai-agents",
        "rag":        "llama-index haystack ragas unstructured mem0ai chromadb faiss-cpu lancedb",
        "vector-db":  "chromadb faiss-cpu lancedb usearch annoy",
        "ml":         "transformers datasets ultralytics optuna wandb mlflow sentence-transformers",
        "eval":       "deepeval ragas lm-eval",
        "speech":     "openai-whisper faster-whisper bark TTS speechbrain",
        "image":      "diffusers",
        "safety":     "guardrails-ai llm-guard",
        "monitor":    "langfuse helicone openllmetry",
        "quant":      "autoawq auto-gptq bitsandbytes optimum",
        "data":       "beautifulsoup4 scrapy crawl4ai duckduckgo_search docling marker browser-use",
        "ui":         "gradio streamlit chainlit",
    }
    lines = [
        "#!/bin/bash",
        "# AI/ML GitHub - pip install tools by category",
        'CATEGORY="${1:-all}"',
        'install_cat() { local l="$1"; shift; echo "  [$l] $# pkgs"; for p in "$@"; do pip install -q "$p" 2>/dev/null || echo "  FAIL: $p"; done }',
        'case "$CATEGORY" in',
    ]
    for cat_name, pkgs_str in cats.items():
        pkgs = pkgs_str.split()
        lines.append(f'    {cat_name}) install_cat "{cat_name}" {" ".join(pkgs)} ;;')
    lines.extend([
        '    all)',
    ])
    for cat_name, pkgs_str in cats.items():
        pkgs = pkgs_str.split()
        lines.append(f'        install_cat "{cat_name}" {" ".join(pkgs)}')
    lines.extend([
        '        ;;',
        '    *) echo "Categories: core inference finetuning agents rag vector-db ml eval speech image safety monitor quant data ui" ;;',
        'esac',
    ])
    return "\n".join(lines)


def main():
    text = read_file(INPUT_FILE)
    print(f"Read {len(text):,} chars from 14.md")
    
    catalog = build_catalog(text)
    
    print(f"\n{'='*50}")
    print(f"CATALOG SUMMARY")
    print(f"{'='*50}")
    print(f"  Categories:     {catalog['total_categories']}")
    print(f"  Total repos:    {catalog['total_repos']}")
    print(f"  Star rankings:  {catalog['total_star_rankings']}")
    print(f"  Glossary terms: {catalog['total_glossary_terms']}")
    print(f"  Pip installable:{catalog['pip_installable_count']}")
    print(f"\nPer-category breakdown:")
    for cat in sorted(catalog["categories"], key=lambda c: len(c["repos"]), reverse=True):
        print(f"  {cat['name'][:30]:30s} {len(cat['repos']):3d} repos")
    
    # Also read the raw content file from the heredoc target if it exists
    raw_md = Path("/mnt/user-data/outputs/AI_ML_GitHub_ULTIMATE_DEEPDIVE.md")
    if raw_md.exists():
        print(f"\nAlso found raw markdown at {raw_md}")
    
    # Save catalog
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {OUTPUT_FILE}")
    
    # Generate scripts
    os.makedirs(OUTPUT_FILE.parent / "scripts", exist_ok=True)
    
    for name, gen_fn, ext in [
        ("clone_all_repos.sh", generate_bash_clone_script, ".sh"),
        ("clone_all_repos.ps1", generate_powershell_script, ".ps1"),
    ]:
        path = OUTPUT_FILE.parent / "scripts" / name
        content = gen_fn(catalog)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(path, 0o755)
        print(f"Saved: {path} ({len(content):,} bytes)")
    
    pip_script = generate_pip_install_script()
    pip_path = OUTPUT_FILE.parent / "scripts" / "pip_install_tools.sh"
    with open(pip_path, "w", encoding="utf-8") as f:
        f.write(pip_script)
    os.chmod(pip_path, 0o755)
    print(f"Saved: {pip_path} ({len(pip_script):,} bytes)")
    
    # Save star rankings separately
    rank_path = OUTPUT_FILE.parent / "data" / "star_rankings.json"
    os.makedirs(rank_path.parent, exist_ok=True)
    with open(rank_path, "w", encoding="utf-8") as f:
        json.dump(catalog["star_rankings"], f, indent=2)
    print(f"Saved: {rank_path}")
    
    print(f"\n✅ Extraction complete!")


if __name__ == "__main__":
    main()
