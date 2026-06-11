"""
DOWNLOAD ORCHESTRATOR
Multi-protocol download engine for the Phase 1-4 data collection pipeline.

Protocols supported:
- HuggingFace (datasets library) — most datasets
- HTTP/HTTPS with resume capability — for direct file downloads
- Git LFS — for large model/data repos
- S3 — for AWS-hosted datasets
- API — for REST API data sources

Features:
- Resumable downloads with byte-range headers
- Configurable retry with exponential backoff
- Rate limiting per source
- Parallel downloads with concurrency control
- Progress tracking via MetadataManager
- Streaming decompression (gzip, zstd)
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import shutil
import subprocess
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.data.metadata import (
    DatasetRecord,
    DownloadProtocol,
    DownloadStatus,
    MetadataManager,
)

# Base data directory
BASE_DATA_DIR = Path(os.environ.get("DATA_DIR", "D:/PythonAI_Data"))


# ════════════════════════════════════════════
# Rate Limiter
# ════════════════════════════════════════════

class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, calls_per_second: float = 5.0):
        self.interval = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self._last_call = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last_call = time.time()


# ════════════════════════════════════════════
# Progress callback types
# ════════════════════════════════════════════

ProgressCallback = Callable[[str, int, int], None]  # dataset_id, current, total


# ════════════════════════════════════════════
# Core Downloader
# ════════════════════════════════════════════

class DownloadOrchestrator:
    """
    Downloads datasets from various sources into the Phase 1 data structure.

    Usage:
        orch = DownloadOrchestrator(metadata_mgr)
        await orch.download_all_phase(phase=1)
        await orch.download_week(phase=1, week=1)
        await orch.download_one("fineweb_edu_en")
    """

    def __init__(
        self,
        metadata_mgr: MetadataManager,
        max_concurrent: int = 4,
        global_rate_limit: float = 10.0,
        progress_callback: ProgressCallback | None = None,
        log_callback: Callable[[str], None] | None = None,
    ):
        self.metadata = metadata_mgr
        self.max_concurrent = max_concurrent
        self.rate_limiter = RateLimiter(global_rate_limit)
        self.progress_callback = progress_callback or (lambda _id, c, t: None)
        self.log_callback = log_callback or print
        self._session = None

    async def _ensure_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=600),
                headers={"User-Agent": "PythonAI-Collector/1.0"},
            )
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    # ── Top-level orchestration ──────────────────────────────────

    async def download_one(self, dataset_id: str) -> dict[str, Any]:
        """Download a single dataset by ID. Returns result stats."""
        record = self.metadata.get(dataset_id)
        if not record:
            return {"error": f"Dataset '{dataset_id}' not found in metadata registry"}
        if record.is_ready:
            return {"dataset_id": dataset_id, "status": "already_ready", "records": record.actual_record_count}

        self.metadata.update_status(dataset_id, DownloadStatus.DOWNLOADING)
        result = await self._dispatch_download(record)
        return result

    async def download_week(self, phase: int, week: int,
                            datasets: list[str] | None = None) -> list[dict[str, Any]]:
        """Download all datasets for a given phase+week, or a filtered subset."""
        targets = self.metadata.list_by_week(phase, week)
        if datasets:
            targets = [d for d in targets if d.id in datasets]

        results: list[dict[str, Any]] = []
        for record in targets:
            if record.is_ready:
                continue
            self.log_callback(f"[Download] {record.id}: starting...")
            result = await self.download_one(record.id)
            results.append(result)
            status = result.get("status", result.get("error", "unknown"))
            self.log_callback(f"[Download] {record.id}: {status}")

        return results

    async def download_all_phase(self, phase: int,
                                  datasets: list[str] | None = None) -> list[dict[str, Any]]:
        """Download all datasets for a given phase."""
        results = []
        for week in range(1, 5):
            wk = await self.download_week(phase, week, datasets)
            results.extend(wk)
        return results

    async def download_pending(self) -> list[dict[str, Any]]:
        """Download all pending datasets across all phases."""
        pending = self.metadata.list_pending()
        results = []
        for record in pending:
            result = await self.download_one(record.id)
            results.append(result)
        return results

    # ── Dispatch by protocol ─────────────────────────────────────

    async def _dispatch_download(self, record: DatasetRecord) -> dict[str, Any]:
        """Route a dataset record to the correct protocol handler."""
        try:
            handlers = {
                DownloadProtocol.HUGGINGFACE: self._download_hf,
                DownloadProtocol.HTTP: self._download_http,
                DownloadProtocol.GIT_LFS: self._download_git_lfs,
                DownloadProtocol.S3: self._download_s3,
                DownloadProtocol.API: self._download_api,
                DownloadProtocol.LOCAL: self._download_local,
            }
            handler = handlers.get(record.protocol)
            if not handler:
                raise ValueError(f"Unsupported protocol: {record.protocol}")

            output_dir = BASE_DATA_DIR / record.output_subdir
            output_dir.mkdir(parents=True, exist_ok=True)

            self.rate_limiter.wait()
            result = await handler(record, output_dir)

            self.metadata.update_size(record.id, result.get("records", 0), result.get("bytes", 0))
            self.metadata.update_status(record.id, DownloadStatus.DOWNLOADED)
            return {"dataset_id": record.id, "status": "downloaded", **result}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            self.metadata.update_status(record.id, DownloadStatus.ERROR, error_msg)
            self.log_callback(f"[ERROR] {record.id}: {error_msg}")
            return {"dataset_id": record.id, "error": error_msg}

    # ── HuggingFace downloader ───────────────────────────────────

    async def _download_hf(self, record: DatasetRecord, out_dir: Path) -> dict[str, Any]:
        """Download a dataset from HuggingFace using huggingface_hub directly.

        Uses huggingface_hub to list and download Parquet/JSONL files
        instead of the datasets library, for better Python 3.14 compatibility.
        """
        try:
            from huggingface_hub import hf_hub_download, list_repo_files
        except ImportError:
            raise RuntimeError("huggingface_hub not installed. Run: pip install huggingface_hub")

        repo = record.source_url
        config = record.hf_config
        split = record.hf_split
        max_records = record.download_params.get("max_records", 0)

        self.log_callback(f"  Scanning HF dataset: {repo} (config={config}, split={split})")

        # List all files in the dataset repository
        all_files = list_repo_files(repo, repo_type="dataset")

        # Filter files based on config and split
        if config:
            # For config-based datasets, look in config subdirectory
            prefix = f"{config}/"
            topic_files = [f for f in all_files if f.startswith(prefix)]
            # If no files under config prefix, try config-split pattern
            if not topic_files:
                # Try 'data/{config}/' or '{config}-{split}' patterns
                topic_files = [f for f in all_files if f.startswith(f"data/{config}/")]
            if not topic_files:
                # Filter with more precision to avoid false matches
                topic_files = [f for f in all_files if f"/{config}/" in f or f"/{config}-" in f or f"/{config}_" in f]
        else:
            topic_files = [f for f in all_files if not f.startswith(".")]

        # Filter to parquet files and limit to requested split
        parquet_files = sorted([f for f in topic_files if f.endswith(".parquet")])
        # Filter to split if applicable
        if split:
            split_files = [f for f in parquet_files if f"/{split}-" in f or f"-{split}-" in f]
            if split_files:
                parquet_files = split_files

        # Also look for JSONL files as fallback
        if not parquet_files:
            jsonl_files = sorted([f for f in topic_files if f.endswith(".jsonl") or f.endswith(".json")])
            if jsonl_files:
                self.log_callback(f"  Found {len(jsonl_files)} JSONL files, downloading...")
                return await self._download_hf_jsonl(record, out_dir, jsonl_files, repo, max_records)

        if not parquet_files:
            # Last resort: try root-level parquet files
            parquet_files = sorted([f for f in all_files if f.endswith(".parquet")])
            if not parquet_files:
                raise RuntimeError(f"No parquet/JSONL files found for {repo} (config={config}, split={split})")

        self.log_callback(f"  Found {len(parquet_files)} parquet files to download")

        total_records = 0
        total_bytes = 0
        output_file = out_dir / f"{record.id}.jsonl"
        temp_file = out_dir / f".{record.id}.partial.jsonl"

        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise RuntimeError("pyarrow not installed. Run: pip install pyarrow")

        with open(temp_file, "w", encoding="utf-8", newline="") as f:
            for pf in parquet_files:
                if max_records and total_records >= max_records:
                    break

                # Download parquet file (non-blocking)
                loop = asyncio.get_event_loop()
                local_path = await loop.run_in_executor(
                    None, lambda f=pf: hf_hub_download(
                        repo_id=repo, filename=f,
                        repo_type="dataset", local_dir=out_dir / ".hf_cache",
                    )
                )

                # Read parquet and write as JSONL (non-blocking)
                table = await loop.run_in_executor(None, pq.read_table, local_path)
                batch = table.to_pylist()

                for row in batch:
                    if max_records and total_records >= max_records:
                        break
                    line = json.dumps(row, ensure_ascii=False)
                    f.write(line + "\n")
                    total_records += 1
                    total_bytes += len(line.encode("utf-8"))

                self.progress_callback(record.id, total_records, max_records or total_records)

                # Clean up cached parquet file
                try:
                    os.remove(local_path)
                except OSError:
                    pass

        # Atomically rename
        temp_file.rename(output_file)
        self.log_callback(f"  Saved {total_records:,} records to {output_file}")

        return {"records": total_records, "bytes": total_bytes, "file": str(output_file)}

    async def _download_hf_jsonl(
        self, record: DatasetRecord, out_dir: Path,
        jsonl_files: list[str], repo: str, max_records: int
    ) -> dict[str, Any]:
        """Download JSONL/JSON files directly from HuggingFace Hub."""
        from huggingface_hub import hf_hub_download

        total_records = 0
        total_bytes = 0
        output_file = out_dir / f"{record.id}.jsonl"
        temp_file = out_dir / f".{record.id}.partial.jsonl"

        with open(temp_file, "w", encoding="utf-8", newline="") as f:
            for jf in jsonl_files:
                if max_records and total_records >= max_records:
                    break

                loop = asyncio.get_event_loop()
                local_path = await loop.run_in_executor(
                    None, lambda f=jf: hf_hub_download(
                        repo_id=repo, filename=f,
                        repo_type="dataset", local_dir=out_dir / ".hf_cache",
                    )
                )

                with open(local_path, encoding="utf-8") as jf_reader:
                    for line in jf_reader:
                        if max_records and total_records >= max_records:
                            break
                        line = line.strip()
                        if line:
                            try:
                                # Validate JSON
                                json.loads(line)
                                f.write(line + "\n")
                                total_records += 1
                                total_bytes += len(line.encode("utf-8"))
                            except json.JSONDecodeError:
                                pass

                self.progress_callback(record.id, total_records, max_records or total_records)
                try:
                    os.remove(local_path)
                except OSError:
                    pass

        temp_file.rename(output_file)
        self.log_callback(f"  Saved {total_records:,} records from JSONL to {output_file}")
        return {"records": total_records, "bytes": total_bytes, "file": str(output_file)}


    # ── HTTP downloader with resume ──────────────────────────────

    async def _download_http(self, record: DatasetRecord, out_dir: Path) -> dict[str, Any]:
        """Download a file via HTTP/HTTPS with resume support."""
        url = record.source_url
        filename = url.split("/")[-1].split("?")[0] or f"{record.id}.data"
        output_path = out_dir / filename

        session = await self._ensure_session()
        downloaded = 0

        # Check if partial download exists for resume
        headers = {}
        if output_path.exists():
            existing_size = output_path.stat().st_size
            if existing_size > 0:
                headers["Range"] = f"bytes={existing_size}-"
                downloaded = existing_size
                self.log_callback(f"  Resuming {filename} from byte {existing_size}")

        async with session.get(url, headers=headers) as resp:
            if resp.status not in (200, 206):
                raise RuntimeError(f"HTTP {resp.status} for {url}")

            mode = "ab" if downloaded > 0 else "wb"
            total = int(resp.headers.get("Content-Length", 0)) + downloaded
            chunk_size = 8192
            bytes_written = downloaded

            temp_path = out_dir / f".{record.id}.partial"
            with open(temp_path, mode) as f:
                async for chunk in resp.content.iter_chunked(chunk_size):
                    f.write(chunk)
                    bytes_written += len(chunk)
                    if total > 0 and bytes_written % (1024 * 1024) == 0:
                        self.progress_callback(record.id, bytes_written, total)

            # Atomically rename
            if output_path.exists():
                output_path.unlink()
            temp_path.rename(output_path)

        self.log_callback(f"  Downloaded {bytes_written:,} bytes to {output_path}")
        return {"records": 1, "bytes": bytes_written, "file": str(output_path)}

    # ── Git LFS downloader ───────────────────────────────────────

    async def _run_cmd(self, cmd: list[str], check: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess:
        """Run a subprocess in a thread to avoid blocking the event loop."""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, check=check, cwd=cwd),
        )

    async def _download_git_lfs(self, record: DatasetRecord, out_dir: Path) -> dict[str, Any]:
        """Clone or pull a Git LFS repository."""
        url = record.source_url
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        repo_path = out_dir / repo_name

        if repo_path.exists():
            self.log_callback(f"  Pulling updates for {repo_name}...")
            await self._run_cmd(["git", "-C", str(repo_path), "pull"], cwd=repo_path)
            await self._run_cmd(["git", "-C", str(repo_path), "lfs", "pull"], cwd=repo_path)
        else:
            self.log_callback(f"  Cloning {repo_name} with LFS...")
            await self._run_cmd(["git", "clone", url, str(repo_path)], check=True)
            await self._run_cmd(["git", "-C", str(repo_path), "lfs", "pull"], cwd=repo_path, check=True)

        # Count files
        total_bytes = 0
        total_files = 0
        for f in repo_path.rglob("*"):
            if f.is_file() and ".git" not in str(f):
                total_bytes += f.stat().st_size
                total_files += 1

        self.log_callback(f"  Repository size: {total_files} files, {total_bytes:,} bytes")
        return {"records": total_files, "bytes": total_bytes, "file": str(repo_path)}

    # ── S3 downloader ────────────────────────────────────────────

    async def _download_s3(self, record: DatasetRecord, out_dir: Path) -> dict[str, Any]:
        """Download from S3-compatible storage."""
        url = record.source_url
        parsed = urlparse(url)
        bucket = parsed.netloc.split(".")[0]
        key = parsed.path.lstrip("/")

        # Try boto3 first, fallback to HTTP
        try:
            import boto3
            s3 = boto3.client("s3")
            filename = key.split("/")[-1] or f"{record.id}.data"
            output_path = out_dir / filename

            self.log_callback(f"  Downloading s3://{bucket}/{key}...")
            s3.download_file(bucket, key, str(output_path))
            size = output_path.stat().st_size

            self.log_callback(f"  Downloaded {size:,} bytes")
            return {"records": 1, "bytes": size, "file": str(output_path)}

        except ImportError:
            # Fallback to presigned URL or direct HTTP
            return await self._download_http(record, out_dir)

        except Exception as e:
            self.log_callback(f"  S3 download failed, trying HTTP fallback: {e}")
            return await self._download_http(record, out_dir)

    # ── API downloader ───────────────────────────────────────────

    async def _download_api(self, record: DatasetRecord, out_dir: Path) -> dict[str, Any]:
        """Download data from a REST API endpoint (paginated JSON/JSONL)."""
        url = record.source_url
        session = await self._ensure_session()

        params = record.download_params.get("api_params", {})
        pagination = record.download_params.get("pagination", {})
        page_param = pagination.get("page_param", "page")
        page_size = pagination.get("page_size", 100)
        max_pages = pagination.get("max_pages", 10)
        results_key = pagination.get("results_key", "results")
        total_key = pagination.get("total_key")

        output_file = out_dir / f"{record.id}.jsonl"
        temp_file = out_dir / f".{record.id}.partial.jsonl"

        total_records = 0
        total_bytes = 0

        with open(temp_file, "w", encoding="utf-8", newline="") as f:
            for page in range(1, max_pages + 1):
                params[page_param] = page
                params["page_size"] = page_size

                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        if page == 1:
                            raise RuntimeError(f"API {resp.status} for {url}")
                        break
                    data = await resp.json()

                # Navigate to results
                items = data
                for key_part in results_key.split(".") if results_key else []:
                    items = items.get(key_part, {})

                if not isinstance(items, list) or len(items) == 0:
                    break

                for item in items:
                    line = json.dumps(item, ensure_ascii=False)
                    f.write(line + "\n")
                    total_records += 1
                    total_bytes += len(line.encode("utf-8"))

                # Check total (if API provides it)
                if total_key:
                    total = data
                    for key_part in total_key.split("."):
                        total = total.get(key_part, 0) if isinstance(total, dict) else 0
                    if total_records >= total:
                        break

                self.rate_limiter.wait()
                self.progress_callback(record.id, page, max_pages)

        temp_file.rename(output_file)
        self.log_callback(f"  Downloaded {total_records:,} records from API")
        return {"records": total_records, "bytes": total_bytes, "file": str(output_file)}

    # ── Local copy ───────────────────────────────────────────────

    async def _download_local(self, record: DatasetRecord, out_dir: Path) -> dict[str, Any]:
        """Copy data from a local path."""
        src = Path(record.source_url)
        if not src.exists():
            raise FileNotFoundError(f"Local source not found: {src}")

        if src.is_dir():
            dst = out_dir / src.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            total_bytes = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
            return {"records": 1, "bytes": total_bytes, "file": str(dst)}
        else:
            dst = out_dir / src.name
            shutil.copy2(src, dst)
            return {"records": 1, "bytes": dst.stat().st_size, "file": str(dst)}


# ════════════════════════════════════════════
# Utility: decompress downloaded archives
# ════════════════════════════════════════════

def decompress_file(path: Path, output_dir: Path | None = None, log: Callable[[str], None] | None = None) -> list[Path]:
    """Decompress a downloaded file (gzip, zip, zstd). Returns list of extracted files."""
    log = log or print
    output_dir = output_dir or path.parent
    suffix = path.suffix.lower()
    extracted: list[Path] = []

    if suffix == ".gz":
        output_path = output_dir / path.stem
        with gzip.open(path, "rb") as gz:
            with open(output_path, "wb") as out:
                shutil.copyfileobj(gz, out)
        extracted.append(output_path)

    elif suffix == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(output_dir)
            extracted = [output_dir / name for name in zf.namelist()]

    elif suffix == ".zst":
        try:
            import pyzstd
            output_path = output_dir / path.stem.replace(".tar", "")
            with open(path, "rb") as f:
                compressed = f.read()
            decompressed = pyzstd.decompress(compressed)
            output_path.write_bytes(decompressed)
            extracted.append(output_path)
        except ImportError:
            log(f"  pyzstd not installed, skipping decompression of {path}")

    return extracted
