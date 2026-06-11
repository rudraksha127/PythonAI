from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent  # src/utils/ -> project root
IGNORED_SCAN_DIRS = {".venv", ".git", "__pycache__", "node_modules"}


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def project_python(root: Path = ROOT) -> Path:
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def run_command(command: list[str], timeout: int = 60) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(command, completed.returncode, completed.stdout, completed.stderr)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def iter_project_files(root: Path = ROOT) -> Generator[Path, None, None]:
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_SCAN_DIRS]
        current_path = Path(current)
        for filename in filenames:
            yield current_path / filename


def audit_project(root: Path = ROOT) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    by_ext: dict[str, dict[str, Any]] = defaultdict(lambda: {"files": 0, "bytes": 0})

    for path in iter_project_files(root):
        if not path.is_file():
            continue
        size = path.stat().st_size
        ext = path.suffix.lower() or "no-ext"
        files.append({"path": str(path.relative_to(root)), "bytes": size, "extension": ext})
        by_ext[ext]["files"] += 1
        by_ext[ext]["bytes"] += size

    largest = sorted(files, key=lambda item: item["bytes"], reverse=True)[:20]
    return {
        "total_files": len(files),
        "total_mb": round(sum(item["bytes"] for item in files) / 1024 / 1024, 2),
        "by_extension": dict(sorted(by_ext.items(), key=lambda item: item[1]["bytes"], reverse=True)),
        "largest_files": largest,
    }


def cleanup_dry_run(root: Path = ROOT) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    patterns = ["__pycache__", ".pytest_cache", ".ipynb_checkpoints"]
    suffixes = {".pyc", ".pyo"}

    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in {".venv", ".git"}]
        current_path = Path(current)

        for dirname in list(dirnames):
            path = current_path / dirname
            if dirname in patterns:
                size = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
                candidates.append({"path": str(path.relative_to(root)), "bytes": size, "type": "dir"})
                dirnames.remove(dirname)

        for filename in filenames:
            path = current_path / filename
            if path.suffix.lower() in suffixes:
                candidates.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "type": "file"})

    return {
        "candidate_count": len(candidates),
        "recoverable_mb": round(sum(item["bytes"] for item in candidates) / 1024 / 1024, 4),
        "candidates": candidates,
    }


def dataset_profile(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        path = ROOT / "data" / "training" / "training_dataset.json"
        if not path.exists():
            path = ROOT / "training_dataset.json"

    rows = load_json(path)
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON list.")

    categories = Counter(str(row.get("category", "")) for row in rows if isinstance(row, dict))
    versions = Counter(str(row.get("version", "")) for row in rows if isinstance(row, dict))
    lengths = [
        len(str(row.get("instruction", ""))) + len(str(row.get("output", "")))
        for row in rows
        if isinstance(row, dict)
    ]

    return {
        "path": str(path.relative_to(ROOT)),
        "rows": len(rows),
        "keys": sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
        "categories_top": categories.most_common(10),
        "versions_top": versions.most_common(10),
        "length_min": min(lengths) if lengths else 0,
        "length_avg": round(sum(lengths) / len(lengths), 2) if lengths else 0,
        "length_max": max(lengths) if lengths else 0,
    }


def hardware_profile(python_exe: Path | None = None) -> dict[str, Any]:
    python_exe = python_exe or project_python()
    probe = (
        "import json, platform, psutil, torch;"
        "data={'python': platform.python_version(), 'executable': __import__('sys').executable, "
        "'ram_gb': round(psutil.virtual_memory().total/1024**3, 2), "
        "'cuda_available': torch.cuda.is_available(), 'cuda_version': getattr(torch.version, 'cuda', None)};"
        "data['gpu_name']=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None;"
        "data['gpu_vram_gb']=round(torch.cuda.get_device_properties(0).total_memory/1024**3, 2) if torch.cuda.is_available() else 0;"
        "print(json.dumps(data))"
    )
    result = run_command([str(python_exe), "-c", probe], timeout=30)
    if result.returncode != 0:
        return {"error": result.stderr.strip()}
    loaded: Any = json.loads(result.stdout)
    if not isinstance(loaded, dict):
        return {"error": f"Unexpected hardware probe output: {type(loaded).__name__}"}
    return loaded


def list_ollama_models() -> list[str]:
    if not shutil.which("ollama"):
        return []
    result = run_command(["ollama", "list"], timeout=20)
    if result.returncode != 0:
        return []
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    models = []
    for line in lines[1:]:
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def list_hf_cached_models(cache_dir: Path | None = None) -> list[str]:
    cache_dir = cache_dir or Path.home() / ".cache" / "huggingface" / "hub"
    if not cache_dir.exists():
        return []

    models = []
    for path in cache_dir.iterdir():
        if path.is_dir() and path.name.startswith("models--"):
            models.append(path.name.removeprefix("models--").replace("--", "/"))
    return sorted(models)


def discover_qwen_hf_candidates(root: Path = ROOT) -> list[str]:
    env_candidates = [
        os.getenv("QWEN_MODEL_PATH", "").strip(),
        os.getenv("HF_QWEN_MODEL", "").strip(),
    ]
    candidates = [value for value in env_candidates if value]

    for model in list_hf_cached_models():
        if "qwen" in model.lower():
            candidates.append(model)

    for path in iter_project_files(root):
        if path.name != "config.json":
            continue
        try:
            config = load_json(path)
        except Exception:
            continue
        name = str(path.parent)
        arch = " ".join(str(item) for item in config.get("architectures", []))
        if "qwen" in name.lower() or "qwen" in arch.lower():
            candidates.append(str(path.parent))

    return list(dict.fromkeys(candidates))


def choose_training_base(mode: str, hardware: dict[str, Any], qwen_candidates: list[str]) -> tuple[str, str]:
    if mode == "smoke":
        return "sshleifer/tiny-gpt2", "smoke mode requested"
    if mode == "qwen":
        if not qwen_candidates:
            return "Qwen/Qwen2.5-Coder-14B-Instruct", "HF Qwen 14B not cached; will download from HuggingFace"
        return qwen_candidates[0], "HF-format Qwen candidate found"
    if qwen_candidates and hardware.get("cuda_available"):
        return qwen_candidates[0], "auto selected HF Qwen because CUDA is available"
    return "sshleifer/tiny-gpt2", "auto selected CPU-safe smoke model; Ollama Qwen is for inference, not PEFT training"
