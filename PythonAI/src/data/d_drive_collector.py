"""
D: Drive Data Collector for PythonAI OMNISCIENT
Collects maximum Python knowledge from multiple sources and stores on D: drive.

Usage:
    python -m src.data.d_drive_collector --all
    python -m src.data.d_drive_collector --source so
    python -m src.data.d_drive_collector --source github
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
D_DRIVE_BASE = Path("D:/PythonAI_Data")

# Directories on D: drive
DIRS = {
    "raw": D_DRIVE_BASE / "raw",
    "processed": D_DRIVE_BASE / "processed",
    "so_data": D_DRIVE_BASE / "stackoverflow",
    "github_data": D_DRIVE_BASE / "github_code",
    "docs": D_DRIVE_BASE / "python_docs",
    "training": D_DRIVE_BASE / "training",
    "embeddings": D_DRIVE_BASE / "embeddings",
    "knowledge_graph": D_DRIVE_BASE / "knowledge_graph",
    "conversations": D_DRIVE_BASE / "conversations",
    "benchmarks": D_DRIVE_BASE / "benchmarks",
}


def setup_d_drive() -> dict[str, Any]:
    """Create all necessary directories on D: drive."""
    print(f"\n[D: Drive] Setting up data directories at {D_DRIVE_BASE}")
    created = []
    for name, path in DIRS.items():
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))
        print(f"  [OK] {name}: {path}")

    # Create a manifest
    manifest = {
        "project": "PythonAI OMNISCIENT",
        "version": "2.0.0",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "directories": {k: str(v) for k, v in DIRS.items()},
        "total_dirs": len(DIRS),
    }
    manifest_path = D_DRIVE_BASE / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n  [OK] Manifest saved: {manifest_path}")
    return manifest


def collect_stackoverflow(tag: str = "python", pages: int = 5, pagesize: int = 100) -> int:
    """Collect top Python Q&A from Stack Overflow API (no key needed for limited use)."""
    output_dir = DIRS["so_data"]
    total_collected = 0

    print(f"\n[SO] Collecting top '{tag}' questions from Stack Overflow...")
    print(f"  Pages: {pages}, Per page: {pagesize}")

    for page in range(1, pages + 1):
        url = (
            f"https://api.stackexchange.com/2.3/questions?"
            f"order=desc&sort=votes&tagged={tag}&site=stackoverflow"
            f"&page={page}&pagesize={pagesize}&filter=withbody"
        )

        try:
            print(f"  [Page {page}/{pages}] Fetching...", end="", flush=True)
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})

            import gzip
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.info().get('Content-Encoding') == 'gzip':
                    data = json.loads(gzip.decompress(resp.read()).decode("utf-8"))
                else:
                    data = json.loads(resp.read().decode("utf-8"))

            questions = data.get("items", [])

            # Save each question
            batch = []
            for q in questions:
                entry = {
                    "question_id": q.get("question_id"),
                    "title": q.get("title", ""),
                    "body": q.get("body", "")[:3000],
                    "score": q.get("score", 0),
                    "view_count": q.get("view_count", 0),
                    "answer_count": q.get("answer_count", 0),
                    "tags": q.get("tags", []),
                    "link": q.get("link", ""),
                    "is_answered": q.get("is_answered", False),
                    "creation_date": q.get("creation_date", 0),
                }
                batch.append(entry)

            # Save batch
            batch_file = output_dir / f"so_top_{tag}_page{page}.json"
            batch_file.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
            total_collected += len(batch)
            print(f" {len(batch)} questions saved.")

            # Respect rate limits
            quota_remaining = data.get("quota_remaining", 0)
            print(f"    API quota remaining: {quota_remaining}")
            if quota_remaining < 10:
                print("  [WARN] Approaching rate limit, stopping.")
                break

            time.sleep(1)  # Be nice to the API

        except Exception as e:
            print(f" Error: {e}")
            time.sleep(2)

    print(f"\n  [OK] Total SO questions collected: {total_collected}")
    return total_collected


def collect_so_answers(question_ids: list[int]) -> int:
    """Collect answers for a list of question IDs."""
    output_dir = DIRS["so_data"]
    total = 0

    # Process in batches of 30
    for i in range(0, len(question_ids), 30):
        batch_ids = question_ids[i:i+30]
        ids_str = ";".join(str(qid) for qid in batch_ids)

        url = (
            f"https://api.stackexchange.com/2.3/questions/{ids_str}/answers?"
            f"order=desc&sort=votes&site=stackoverflow&filter=withbody"
        )

        try:
            import gzip
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.info().get('Content-Encoding') == 'gzip':
                    data = json.loads(gzip.decompress(resp.read()).decode("utf-8"))
                else:
                    data = json.loads(resp.read().decode("utf-8"))

            answers = data.get("items", [])
            batch = []
            for a in answers:
                entry = {
                    "answer_id": a.get("answer_id"),
                    "question_id": a.get("question_id"),
                    "body": a.get("body", "")[:5000],
                    "score": a.get("score", 0),
                    "is_accepted": a.get("is_accepted", False),
                }
                batch.append(entry)

            batch_file = output_dir / f"so_answers_batch_{i//30}.json"
            batch_file.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
            total += len(batch)
            print(f"  [Batch {i//30}] {len(batch)} answers collected")

            time.sleep(1)
        except Exception as e:
            print(f"  [Error] {e}")
            time.sleep(2)

    return total


def collect_github_python_repos(query: str = "python language:python", pages: int = 3) -> int:
    """Collect Python repos metadata from GitHub (no auth needed for basic search)."""
    output_dir = DIRS["github_data"]
    total = 0

    print(f"\n[GitHub] Collecting Python repos: '{query}'")

    for page in range(1, pages + 1):
        url = (
            f"https://api.github.com/search/repositories?"
            f"q={urllib.parse.quote(query)}&sort=stars&order=desc"
            f"&page={page}&per_page=30"
        )

        try:
            print(f"  [Page {page}/{pages}]", end="", flush=True)
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            repos = data.get("items", [])
            batch = []
            for r in repos:
                entry = {
                    "name": r.get("full_name", ""),
                    "description": r.get("description", ""),
                    "stars": r.get("stargazers_count", 0),
                    "language": r.get("language", ""),
                    "topics": r.get("topics", []),
                    "url": r.get("html_url", ""),
                    "created_at": r.get("created_at", ""),
                    "updated_at": r.get("updated_at", ""),
                }
                batch.append(entry)

            batch_file = output_dir / f"github_repos_page{page}.json"
            batch_file.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
            total += len(batch)
            print(f" {len(batch)} repos saved.")

            time.sleep(2)  # Respect GitHub rate limits
        except Exception as e:
            print(f" Error: {e}")
            time.sleep(5)

    print(f"\n  [OK] Total GitHub repos collected: {total}")
    return total


def copy_existing_data() -> dict[str, int]:
    """Copy existing project data to D: drive for backup."""
    stats = {}

    print("\n[Copy] Syncing existing project data to D: drive...")

    # Copy training dataset
    src_training = ROOT / "data" / "training" / "training_dataset.json"
    if src_training.exists():
        dst = DIRS["training"] / "training_dataset.json"
        import shutil
        shutil.copy2(src_training, dst)
        size_mb = dst.stat().st_size / (1024 * 1024)
        stats["training_dataset"] = int(dst.stat().st_size)
        print(f"  [OK] Training dataset: {size_mb:.1f} MB")

    # Copy raw chunks
    src_chunks = ROOT / "data" / "raw" / "raw_chunks_godmode.json"
    if src_chunks.exists():
        dst = DIRS["raw"] / "raw_chunks_godmode.json"
        import shutil
        shutil.copy2(src_chunks, dst)
        size_mb = dst.stat().st_size / (1024 * 1024)
        stats["raw_chunks"] = int(dst.stat().st_size)
        print(f"  [OK] Raw chunks: {size_mb:.1f} MB")

    # Copy augmented data
    src_aug = ROOT / "data" / "training" / "training_dataset_augmented.json"
    if src_aug.exists():
        dst = DIRS["training"] / "training_dataset_augmented.json"
        import shutil
        shutil.copy2(src_aug, dst)
        size_mb = dst.stat().st_size / (1024 * 1024)
        stats["augmented_data"] = int(dst.stat().st_size)
        print(f"  [OK] Augmented dataset: {size_mb:.1f} MB")

    # Copy Mistral finetune data
    src_mistral = ROOT / "checkpoints" / "mistral_finetune" / "training_data.jsonl"
    if src_mistral.exists():
        dst = DIRS["training"] / "mistral_training_data.jsonl"
        import shutil
        shutil.copy2(src_mistral, dst)
        stats["mistral_data"] = int(dst.stat().st_size)
        print("  [OK] Mistral finetune data")

    # Copy cleaned chunks
    src_cleaned = ROOT / "data" / "processed" / "cleaned_chunks.json"
    if src_cleaned.exists():
        dst = DIRS["processed"] / "cleaned_chunks.json"
        import shutil
        shutil.copy2(src_cleaned, dst)
        size_mb = dst.stat().st_size / (1024 * 1024)
        stats["cleaned_chunks"] = int(dst.stat().st_size)
        print(f"  [OK] Cleaned chunks: {size_mb:.1f} MB")

    total_bytes = sum(stats.values())
    print(f"\n  [OK] Total synced: {total_bytes / (1024*1024):.1f} MB")
    return stats


def generate_collection_report() -> dict[str, Any]:
    """Generate a report of all data on D: drive."""
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_path": str(D_DRIVE_BASE),
        "directories": {},
        "total_files": 0,
        "total_bytes": 0,
    }

    for name, path in DIRS.items():
        if path.exists():
            files = list(path.rglob("*"))
            file_count = sum(1 for f in files if f.is_file())
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            report["directories"][name] = {
                "path": str(path),
                "files": file_count,
                "bytes": total_size,
                "mb": round(total_size / (1024 * 1024), 2),
            }
            report["total_files"] += file_count
            report["total_bytes"] += total_size

    report["total_mb"] = round(report["total_bytes"] / (1024 * 1024), 2)

    # Save report
    report_path = D_DRIVE_BASE / "collection_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="D: Drive Data Collector for PythonAI")
    parser.add_argument("--all", action="store_true", help="Run all collection tasks")
    parser.add_argument("--setup", action="store_true", help="Setup D: drive directories only")
    parser.add_argument("--source", choices=["so", "github", "copy", "report"], help="Collect from specific source")
    parser.add_argument("--so-pages", type=int, default=5, help="SO pages to collect (default: 5)")
    parser.add_argument("--github-pages", type=int, default=3, help="GitHub pages to collect (default: 3)")
    args = parser.parse_args()

    print("=" * 60)
    print("  PythonAI OMNISCIENT — D: Drive Data Collector")
    print("=" * 60)

    # Always setup first
    setup_d_drive()

    if args.setup:
        return

    if args.source == "so" or args.all:
        so_count = collect_stackoverflow(pages=args.so_pages)

        # Also collect answers for top questions
        so_dir = DIRS["so_data"]
        all_qids = []
        for f in so_dir.glob("so_top_*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            all_qids.extend(q["question_id"] for q in data if q.get("is_answered"))

        if all_qids:
            print(f"\n[SO] Collecting answers for {len(all_qids)} answered questions...")
            collect_so_answers(all_qids[:90])  # Limit to avoid rate limits

    if args.source == "github" or args.all:
        collect_github_python_repos(pages=args.github_pages)
        # Also search for specific Python topics
        for topic in ["asyncio python", "django python", "fastapi python"]:
            collect_github_python_repos(query=f"{topic} language:python", pages=1)
            time.sleep(3)

    if args.source == "copy" or args.all:
        copy_existing_data()

    if args.source == "report" or args.all:
        report = generate_collection_report()
        print("\n[Report] Collection Summary:")
        print(f"  Total files: {report['total_files']}")
        print(f"  Total size: {report['total_mb']} MB")
        for name, info in report["directories"].items():
            if info["files"] > 0:
                print(f"    {name}: {info['files']} files ({info['mb']} MB)")

    print(f"\n{'='*60}")
    print(f"  [DONE] All data stored at: {D_DRIVE_BASE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
