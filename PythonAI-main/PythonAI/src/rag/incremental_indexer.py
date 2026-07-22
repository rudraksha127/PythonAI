"""
ForgeAI Incremental Indexer — Smart Re-indexing for RAG v2
===========================================================

Only re-processes files that have changed since the last index,
saving time and compute on large codebases.

Uses file modification timestamps and content hashing to detect changes.

Usage:
    from src.rag.incremental_indexer import IncrementalIndexer

    indexer = IncrementalIndexer()
    stats = indexer.index_directory("/path/to/project", force=False)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from src.rag.cast_chunker import CastChunker
from src.rag.multi_view_embedder import MultiViewEmbedder

logger = logging.getLogger("forgeai.incremental_indexer")


class IncrementalIndexer:
    """Smart indexer that only processes changed files.

    Maintains a manifest of indexed files with their last-modified
    timestamps and content hashes. On re-index, only files that
    have changed (new, modified, or deleted) are processed.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".forgeai" / "index"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._manifest_path = self._data_dir / "manifest.json"
        self._manifest: dict[str, Any] = self._load_manifest()

        self._chunker = CastChunker()
        self._embedder = MultiViewEmbedder()

    # ─── Public API ───────────────────────────────────────────────

    def index_directory(
        self,
        directory: str | Path,
        force: bool = False,
        pattern: str = "**/*.{py,js,ts,jsx,tsx,go,rs,java,rb,cpp,c,h,hpp,cs,swift,kt,scala,php}",
    ) -> dict[str, Any]:
        """Index a directory, skipping unchanged files unless force=True.

        Args:
            directory: Root directory to index
            force: If True, re-index all files regardless of changes
            pattern: Glob pattern for files to include

        Returns:
            Stats dict with counts of indexed, skipped, and deleted files
        """
        directory = Path(directory)
        if not directory.is_dir():
            return {"error": f"Not a directory: {directory}", "indexed": 0, "skipped": 0, "deleted": 0}

        logger.info(f"Indexing {directory} (force={force}, pattern={pattern})")
        start_time = time.time()

        # Get current files
        current_files: set[str] = set()
        indexed = 0
        skipped = 0
        errors = 0
        new_chunks = 0

        for f in sorted(directory.rglob("*")):
            if not f.is_file():
                continue
            if not self._matches_pattern(f.name, pattern):
                continue

            rel_path = str(f.relative_to(directory))
            current_files.add(rel_path)

            # Check if file needs re-indexing
            if not force and self._is_unchanged(rel_path, f):
                skipped += 1
                continue

            # Index this file
            try:
                chunks = self._chunker.chunk_file(f)
                embeddings = []
                for chunk in chunks:
                    emb = self._embedder.embed_chunk(chunk.text, chunk.language)
                    embeddings.append({
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        "language": chunk.language,
                        "embeddings": emb,
                        "metadata": chunk.metadata,
                    })

                # Update manifest
                content_hash = self._hash_file(f)
                self._manifest["files"][rel_path] = {
                    "path": rel_path,
                    "size": f.stat().st_size,
                    "mtime": os.path.getmtime(str(f)),
                    "content_hash": content_hash,
                    "chunk_count": len(chunks),
                    "last_indexed": time.time(),
                }
                indexed += 1
                new_chunks += len(chunks)

            except Exception as e:
                logger.warning(f"Error indexing {rel_path}: {e}")
                errors += 1

        # Remove deleted files from manifest
        deleted = 0
        deleted_paths = [p for p in self._manifest.get("files", {}) if p not in current_files]
        for p in deleted_paths:
            del self._manifest["files"][p]
            deleted += 1

        # Update manifest metadata
        self._manifest["last_indexed"] = time.time()
        self._manifest["directory"] = str(directory)
        self._manifest["total_files"] = len(self._manifest.get("files", {}))
        self._save_manifest()

        elapsed = time.time() - start_time

        stats = {
            "indexed": indexed,
            "skipped": skipped,
            "deleted": deleted,
            "errors": errors,
            "new_chunks": new_chunks,
            "total_files_indexed": self._manifest["total_files"],
            "elapsed_seconds": round(elapsed, 2),
            "elapsed_human": f"{elapsed:.1f}s",
        }

        logger.info(f"Indexing complete: {stats}")
        return stats

    def index_file(self, file_path: str | Path, force: bool = False) -> dict[str, Any]:
        """Index a single file."""
        file_path = Path(file_path)
        if not file_path.is_file():
            return {"error": f"Not a file: {file_path}"}

        rel_path = file_path.name

        if not force and self._is_unchanged(rel_path, file_path):
            return {"status": "skipped", "reason": "unchanged"}

        try:
            chunks = self._chunker.chunk_file(file_path)
            self._manifest["files"][rel_path] = {
                "path": rel_path,
                "size": file_path.stat().st_size,
                "mtime": os.path.getmtime(str(file_path)),
                "content_hash": self._hash_file(file_path),
                "chunk_count": len(chunks),
                "last_indexed": time.time(),
            }
            self._save_manifest()
            return {"status": "indexed", "chunks": len(chunks)}
        except Exception as e:
            return {"error": str(e)}

    def get_stats(self) -> dict[str, Any]:
        """Get indexing statistics."""
        files = self._manifest.get("files", {})
        total_chunks = sum(f.get("chunk_count", 0) for f in files.values())
        total_size = sum(f.get("size", 0) for f in files.values())

        # Language breakdown
        languages: dict[str, int] = {}
        for f in files:
            ext = f.split(".")[-1] if "." in f else "unknown"
            languages[ext] = languages.get(ext, 0) + 1

        return {
            "total_files": len(files),
            "total_chunks": total_chunks,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "languages": languages,
            "last_indexed": self._manifest.get("last_indexed"),
            "directory": self._manifest.get("directory"),
        }

    def clear(self) -> int:
        """Clear the index manifest. Returns number of files removed."""
        count = len(self._manifest.get("files", {}))
        self._manifest = {
            "version": 2,
            "created_at": time.time(),
            "last_indexed": None,
            "directory": None,
            "files": {},
        }
        self._save_manifest()
        return count

    # ─── Internal ────────────────────────────────────────────────

    def _is_unchanged(self, rel_path: str, file_path: Path) -> bool:
        """Check if a file is unchanged since last index."""
        stored = self._manifest.get("files", {}).get(rel_path)
        if stored is None:
            return False

        # Check content hash
        current_hash = self._hash_file(file_path)
        return current_hash == stored.get("content_hash")

    def _hash_file(self, file_path: Path) -> str:
        """Compute a fast content hash for a file."""
        hasher = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                # Read first 64KB + file size for a fast hash
                data = f.read(65536)
                hasher.update(data)
                # Include file size to detect truncation
                hasher.update(str(file_path.stat().st_size).encode())
        except OSError:
            return ""
        return hasher.hexdigest()[:16]

    def _load_manifest(self) -> dict[str, Any]:
        """Load the index manifest from disk."""
        if self._manifest_path.exists():
            try:
                data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
                if data.get("version") == 2:
                    return data
            except (json.JSONDecodeError, KeyError):
                pass

        return {
            "version": 2,
            "created_at": time.time(),
            "last_indexed": None,
            "directory": None,
            "files": {},
        }

    def _save_manifest(self) -> None:
        """Save the index manifest to disk."""
        self._manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _matches_pattern(filename: str, pattern: str) -> bool:
        """Check if a filename matches a glob pattern."""
        from fnmatch import fnmatch

        # Split multi-pattern (e.g., **/*.{py,js})
        if "{" in pattern:
            base = pattern[: pattern.index("{")]
            exts = pattern[pattern.index("{") + 1 : pattern.index("}")].split(",")
            return any(fnmatch(filename, f"{base}{ext}") for ext in exts)

        return fnmatch(filename, pattern)


__all__ = ["IncrementalIndexer"]
