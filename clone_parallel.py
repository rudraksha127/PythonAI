import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from datetime import datetime

BASE_DIR = r"c:\Users\lucky_vv7fub\OneDrive\Desktop\Today 1 June\arsenal"
PS_FILE = r"c:\Users\lucky_vv7fub\OneDrive\Desktop\Today 1 June\clone_arsenal.ps1"

# Step 1: Clean up any existing directories that are incomplete (missing .git)
def clean_incomplete_dirs(base):
    if not os.path.exists(base):
        return
    for root, dirs, files in os.walk(base):
        # We only want to look at direct children of the category folders
        # base/category/repo
        # root is base/category, dirs are repo folders
        rel_path = os.path.relpath(root, base)
        if rel_path == "." or rel_path == "..":
            continue
        parts = rel_path.split(os.sep)
        if len(parts) == 1: # root is a category directory, e.g. "01-ai-foundations"
            for d in list(dirs):
                repo_path = os.path.join(root, d)
                git_path = os.path.join(repo_path, ".git")
                if not os.path.exists(git_path):
                    print(f"Cleaning up incomplete/failed clone folder: {repo_path}")
                    try:
                        shutil.rmtree(repo_path, ignore_errors=True)
                    except Exception as e:
                        print(f"Failed to remove {repo_path}: {e}")

print("Scanning for incomplete directories...")
clean_incomplete_dirs(BASE_DIR)

if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

# Parse repos from clone_arsenal.ps1
repos = []
# Match pattern: Clone-Repo "category" "owner/name"
pattern = re.compile(r'Clone-Repo\s+"([^"]+)"\s+"([^"]+)"')

with open(PS_FILE, "r", encoding="utf-8") as f:
    for line in f:
        match = pattern.search(line)
        if match:
            category, repo = match.groups()
            repos.append((category, repo))

print(f"Parsed {len(repos)} repositories from {PS_FILE}")

# Thread safe tracking
success_list = []
failed_list = []
skipped_list = []
print_lock = threading.Lock()
progress_counter = 0
total_repos = len(repos)

def clone_repo(category, repo):
    global progress_counter
    cat_dir = os.path.join(BASE_DIR, category)
    if not os.path.exists(cat_dir):
        try:
            os.makedirs(cat_dir, exist_ok=True)
        except Exception:
            pass
            
    repo_name = repo.split("/")[-1]
    target_dir = os.path.join(cat_dir, repo_name)
    
    # If the folder exists and has .git, skip it
    if os.path.exists(target_dir) and os.path.exists(os.path.join(target_dir, ".git")):
        with print_lock:
            progress_counter += 1
            print(f"[{progress_counter}/{total_repos}] [SKIP] {category}/{repo_name} (already exists)")
        return "skipped", f"{category}/{repo_name}"
    elif os.path.exists(target_dir):
        # Exists but incomplete, delete it
        try:
            shutil.rmtree(target_dir, ignore_errors=True)
        except Exception:
            pass
        
    with print_lock:
        print(f"[{progress_counter + 1}/{total_repos}] [CLONE] {repo} -> {category}/{repo_name}")
        
    try:
        # Build environment dictionary to skip git-lfs smudge
        my_env = os.environ.copy()
        my_env["GIT_LFS_SKIP_SMUDGE"] = "1"
        
        cmd = ["git", "clone", "--depth", "1", f"https://github.com/{repo}.git", target_dir]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, env=my_env)
        
        if result.returncode == 0:
            with print_lock:
                progress_counter += 1
                print(f"[{progress_counter}/{total_repos}] [OK] {category}/{repo_name}")
            return "success", f"{category}/{repo_name}"
        else:
            # Clean up failed clone directory
            try:
                shutil.rmtree(target_dir, ignore_errors=True)
            except Exception:
                pass
            with print_lock:
                progress_counter += 1
                print(f"[{progress_counter}/{total_repos}] [FAIL] {category}/{repo_name} (code {result.returncode})")
            return "failed", f"{category}/{repo_name} (code {result.returncode})"
    except Exception as e:
        # Clean up directory on exception/timeout
        try:
            shutil.rmtree(target_dir, ignore_errors=True)
        except Exception:
            pass
        with print_lock:
            progress_counter += 1
            print(f"[{progress_counter}/{total_repos}] [FAIL] {category}/{repo_name} - Exception: {e}")
        return "failed", f"{category}/{repo_name} - Exception: {e}"

# Run with ThreadPoolExecutor
max_workers = 12
start_time = datetime.now()

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(clone_repo, cat, rep) for cat, rep in repos]
    for future in as_completed(futures):
        status, item = future.result()
        if status == "success":
            success_list.append(item)
        elif status == "skipped":
            skipped_list.append(item)
        elif status == "failed":
            failed_list.append(item)

elapsed = datetime.now() - start_time
elapsed_mins = elapsed.total_seconds() / 60.0

# Generate report
report_lines = [
    "# Arsenal Clone Report",
    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    f"Duration: {elapsed_mins:.1f} minutes",
    "",
    f"## Success ({len(success_list)})",
]
for s in sorted(success_list):
    report_lines.append(f"- {s}")
    
report_lines.append("")
report_lines.append(f"## Skipped ({len(skipped_list)})")
for s in sorted(skipped_list):
    report_lines.append(f"- {s}")

report_lines.append("")
report_lines.append(f"## Failed ({len(failed_list)})")
for f in sorted(failed_list):
    report_lines.append(f"- {f}")

report_path = os.path.join(BASE_DIR, "CLONE_REPORT.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print(f"\n========================================")
print(f"CLONE COMPLETE!")
print(f"========================================")
print(f" SUCCESS: {len(success_list)}")
print(f" SKIPPED: {len(skipped_list)}")
print(f" FAILED:  {len(failed_list)}")
print(f" TIME:    {elapsed_mins:.1f} minutes")
print(f"========================================")
print(f"Report saved to: {report_path}")
