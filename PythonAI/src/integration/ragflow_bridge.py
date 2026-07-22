"""
RAGFlow Bridge — Deep Document Understanding RAG Engine
========================================================

Wraps the `ragflow-sdk` library (infiniflow/ragflow) to provide
deep document ingestion, parsing, and retrieval-augmented generation.

RAGFlow excels at complex document understanding — PDFs with tables,
images, and mixed layouts — extracting structured chunks that
preserve document hierarchy for better RAG quality.

Architecture:
    - Communicates with RAGFlow server via REST API
    - SDK provides RAGFlow, DataSet, and Document classes
    - Supports OpenAI-compatible chat API for queries
    - Multi-modal document parsing (PDF, DOCX, Excel, Images)
    - Graceful fallback when ragflow-sdk is not installed

Usage:
    from src.integration.ragflow_bridge import RAGFlowBridge

    bridge = RAGFlowBridge()
    dataset = bridge.create_dataset("codebase")
    bridge.upload_document(dataset, "document.pdf")
    answer = bridge.query("What does this document say about X?")
    # => {"answer": "...", "sources": [...]}

Environment:
    RAGFLOW_API_KEY     : API key for RAGFlow server
    RAGFLOW_BASE_URL    : Server URL (default: http://localhost:9380)
    RAGFLOW_DATASET_ID  : Default dataset ID to use
    RAGFLOW_CHUNK_METHOD: "naive", "manual", "knowledge_graph" (default: naive)
    RAGFLOW_LLM_MODEL   : Model for answer generation (default: gpt-4o-mini)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.integration.ragflow")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_BASE_URL = "http://localhost:9380"
DEFAULT_CHUNK_METHOD = "naive"
DEFAULT_LLM_MODEL = "gpt-4o-mini"


class RAGFlowBridge:
    """Document ingestion and RAG query engine via RAGFlow.

    Provides:
    - create_dataset / list_datasets / delete_dataset
    - upload_document / list_documents / parse_document
    - query with source citations
    - OpenAI-compatible chat API wrapper
    - Health check for server connectivity

    Lazy-initializes the SDK client on first use.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_dataset_id: str | None = None,
        chunk_method: str | None = None,
        llm_model: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._api_key = api_key or os.environ.get("RAGFLOW_API_KEY", "")
        self._base_url = base_url or os.environ.get("RAGFLOW_BASE_URL", DEFAULT_BASE_URL)
        self._default_dataset_id = default_dataset_id or os.environ.get("RAGFLOW_DATASET_ID", "")
        self._chunk_method = chunk_method or os.environ.get("RAGFLOW_CHUNK_METHOD", DEFAULT_CHUNK_METHOD)
        self._llm_model = llm_model or os.environ.get("RAGFLOW_LLM_MODEL", DEFAULT_LLM_MODEL)
        self._enabled = enabled

        self._ragflow = None
        self._initialized = False
        self._init_error: str | None = None

        self._stats = {
            "datasets_created": 0,
            "documents_uploaded": 0,
            "documents_parsed": 0,
            "queries_run": 0,
            "errors": 0,
            "last_error": None,
            "avg_query_ms": 0.0,
        }

    # ── Lazy Initialization ──────────────────────────────────────

    def _ensure_initialized(self) -> bool:
        """Initialize ragflow-sdk client on first use."""
        if self._initialized:
            return self._ragflow is not None

        if not self._enabled:
            self._initialized = True
            self._init_error = "RAGFlow bridge disabled"
            return False

        try:
            from ragflow_sdk import RAGFlow

            self._ragflow = RAGFlow(
                api_key=self._api_key,
                base_url=self._base_url,
            )
            self._initialized = True
            logger.info(f"RAGFlow client initialized: {self._base_url}")
            return True

        except ImportError:
            self._init_error = "ragflow-sdk not installed. Run: pip install ragflow-sdk"
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"RAGFlowBridge init failed: {e}")

        self._initialized = True
        return False

    # ── Dataset Management ───────────────────────────────────────

    def create_dataset(self, name: str) -> dict[str, Any]:
        """Create a new knowledge base dataset.

        Args:
            name: Display name for the dataset.

        Returns:
            Dict with "id", "name", and "status".
        """
        if not self._ensure_initialized() or self._ragflow is None:
            return {"error": self._init_error or "RAGFlow not available"}

        try:
            dataset = self._ragflow.create_dataset(name=name)
            self._stats["datasets_created"] += 1
            return {
                "id": getattr(dataset, "id", ""),
                "name": name,
                "status": "created",
            }
        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"error": str(e)}

    def list_datasets(self) -> list[dict[str, Any]]:
        """List all available datasets."""
        if not self._ensure_initialized() or self._ragflow is None:
            return []

        try:
            datasets = self._ragflow.list_datasets()
            return [
                {"id": d.id if hasattr(d, "id") else "", "name": d.name if hasattr(d, "name") else ""}
                for d in datasets
            ]
        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return []

    def delete_dataset(self, dataset_id: str) -> bool:
        """Delete a dataset by ID."""
        if not self._ensure_initialized() or self._ragflow is None:
            return False

        try:
            dataset = self._ragflow.list_datasets()
            for d in dataset:
                if getattr(d, "id", "") == dataset_id:
                    d.delete()
                    return True
            return False
        except Exception as e:
            self._stats["errors"] += 1
            return False

    # ── Document Management ──────────────────────────────────────

    def upload_document(
        self,
        dataset: Any | str,
        file_path: str | Path,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """Upload a document to a dataset for parsing.

        Args:
            dataset: A DataSet object, dataset ID string, or name string.
            file_path: Path to the document file.
            display_name: Optional display name (defaults to filename).

        Returns:
            Dict with document info or error.
        """
        if not self._ensure_initialized() or self._ragflow is None:
            return {"error": self._init_error or "RAGFlow not available"}

        try:
            # Resolve dataset
            if isinstance(dataset, str):
                datasets = self._ragflow.list_datasets()
                for d in datasets:
                    if getattr(d, "id", "") == dataset or getattr(d, "name", "") == dataset:
                        dataset_obj = d
                        break
                else:
                    return {"error": f"Dataset '{dataset}' not found"}
            else:
                dataset_obj = dataset

            fpath = Path(file_path)
            if not fpath.exists():
                return {"error": f"File not found: {file_path}"}

            blob = fpath.read_bytes()
            name = display_name or fpath.name

            dataset_obj.upload_documents([{"display_name": name, "blob": blob}])
            self._stats["documents_uploaded"] += 1

            return {"name": name, "path": str(fpath), "size": len(blob), "status": "uploaded"}

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"error": str(e)}

    def upload_text(
        self,
        dataset: Any | str,
        text: str,
        display_name: str = "inline_text.txt",
    ) -> dict[str, Any]:
        """Upload text content as a document to a dataset.

        Args:
            dataset: DataSet object or dataset identifier.
            text: Text content to upload.
            display_name: Name for the document.

        Returns:
            Dict with document info or error.
        """
        if not self._ensure_initialized() or self._ragflow is None:
            return {"error": self._init_error or "RAGFlow not available"}

        try:
            if isinstance(dataset, str):
                datasets = self._ragflow.list_datasets()
                for d in datasets:
                    if getattr(d, "id", "") == dataset or getattr(d, "name", "") == dataset:
                        dataset_obj = d
                        break
                else:
                    return {"error": f"Dataset '{dataset}' not found"}
            else:
                dataset_obj = dataset

            blob = text.encode("utf-8")
            dataset_obj.upload_documents([{"display_name": display_name, "blob": blob}])
            self._stats["documents_uploaded"] += 1
            return {"name": display_name, "size": len(blob), "status": "uploaded"}

        except Exception as e:
            self._stats["errors"] += 1
            return {"error": str(e)}

    def list_documents(self, dataset: Any | str) -> list[dict[str, Any]]:
        """List documents in a dataset."""
        if not self._ensure_initialized() or self._ragflow is None:
            return []

        try:
            if isinstance(dataset, str):
                datasets = self._ragflow.list_datasets()
                for d in datasets:
                    if getattr(d, "id", "") == dataset or getattr(d, "name", "") == dataset:
                        dataset_obj = d
                        break
                else:
                    return []
            else:
                dataset_obj = dataset

            docs = dataset_obj.list_documents()
            return [
                {"id": getattr(d, "id", ""), "name": getattr(d, "name", ""),
                 "status": getattr(d, "status", "unknown"), "size": getattr(d, "size", 0)}
                for d in docs
            ]
        except Exception as e:
            return []

    def parse_document(
        self,
        dataset: Any | str,
        document_id: str,
        chunk_method: str | None = None,
    ) -> dict[str, Any]:
        """Trigger parsing for a document.

        RAGFlow will split the document into chunks, extract entities,
        and build a structured representation.

        Args:
            dataset: DataSet object or identifier.
            document_id: ID of the document to parse.
            chunk_method: Chunking method (default: self._chunk_method).

        Returns:
            Dict with parse status.
        """
        if not self._ensure_initialized() or self._ragflow is None:
            return {"error": self._init_error or "RAGFlow not available"}

        try:
            if isinstance(dataset, str):
                datasets = self._ragflow.list_datasets()
                for d in datasets:
                    if getattr(d, "id", "") == dataset or getattr(d, "name", "") == dataset:
                        dataset_obj = d
                        break
                else:
                    return {"error": f"Dataset '{dataset}' not found"}
            else:
                dataset_obj = dataset

            chunk = chunk_method or self._chunk_method
            docs = dataset_obj.list_documents(keywords="")
            target = None
            for doc in docs:
                if getattr(doc, "id", "") == document_id:
                    target = doc
                    break

            if target is None:
                return {"error": f"Document '{document_id}' not found"}

            dataset_obj.parse_documents([document_id])
            self._stats["documents_parsed"] += 1
            return {"document_id": document_id, "chunk_method": chunk, "status": "parsing_started"}

        except Exception as e:
            self._stats["errors"] += 1
            return {"error": str(e)}

    # ── Query ────────────────────────────────────────────────────

    def query(
        self,
        question: str,
        dataset_id: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Query a RAGFlow dataset for an answer with source citations.

        Uses the OpenAI-compatible chat endpoint internally.

        Args:
            question: The user's question.
            dataset_id: Dataset ID (defaults to RAGFLOW_DATASET_ID env var).
            top_k: Number of chunks to retrieve.

        Returns:
            Dict with "answer", "sources" (list), and metadata.
        """
        if not self._ensure_initialized() or self._ragflow is None:
            return {"answer": "", "error": self._init_error or "RAGFlow not available"}

        ds_id = dataset_id or self._default_dataset_id
        if not ds_id:
            return {"answer": "", "error": "No dataset ID configured. Set RAGFLOW_DATASET_ID or pass dataset_id."}

        try:
            start = time.time()

            # Find the dataset
            datasets = self._ragflow.list_datasets()
            target = None
            for d in datasets:
                if getattr(d, "id", "") == ds_id:
                    target = d
                    break

            if target is None:
                return {"answer": "", "error": f"Dataset '{ds_id}' not found"}

            # Use the dataset's built-in retrieval
            result = target.query(question, top_k=top_k)

            elapsed = time.time() - start
            self._stats["queries_run"] += 1
            self._stats["avg_query_ms"] = (
                (self._stats["avg_query_ms"] * (self._stats["queries_run"] - 1) + elapsed * 1000)
                / self._stats["queries_run"]
            )

            answer = getattr(result, "answer", "") or getattr(result, "response", "")
            chunks = getattr(result, "chunks", []) or getattr(result, "documents", [])

            sources = []
            for chunk in chunks[:top_k]:
                sources.append({
                    "content": getattr(chunk, "content", str(chunk))[:500],
                    "source": getattr(chunk, "source", ""),
                    "score": getattr(chunk, "score", 0),
                })

            return {
                "answer": str(answer).strip(),
                "sources": sources,
                "num_sources": len(sources),
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"answer": "", "sources": [], "error": str(e)}

    def chat_completion(
        self,
        message: str,
        dataset_id: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Query using RAGFlow's OpenAI-compatible chat endpoint.

        This endpoint adapts the standard OpenAI chat completion format
        to RAGFlow's retrieval-augmented generation pipeline.

        Args:
            message: User message text.
            dataset_id: Dataset ID to search.
            model: Model override.

        Returns:
            Dict with assistant reply and metadata.
        """
        if not self._ensure_initialized() or self._ragflow is None:
            return {"content": "", "error": self._init_error or "RAGFlow not available"}

        import httpx

        try:
            ds_id = dataset_id or self._default_dataset_id
            if not ds_id:
                return {"content": "", "error": "No dataset ID"}

            base = self._base_url.rstrip("/")
            url = f"{base}/api/v1/openai/{ds_id}/chat/completions"

            payload = {
                "model": model or self._llm_model,
                "messages": [{"role": "user", "content": message}],
                "max_tokens": 2048,
                "temperature": 0.1,
            }

            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {self._api_key}"}

            start = time.time()
            response = httpx.post(url, json=payload, headers=headers, timeout=60)
            elapsed = time.time() - start

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"content": content, "elapsed_seconds": round(elapsed, 2)}
            else:
                return {"content": "", "error": f"HTTP {response.status_code}: {response.text[:200]}"}

        except Exception as e:
            return {"content": "", "error": str(e)}

    # ── Info ─────────────────────────────────────────────────────

    def available(self) -> bool:
        """Check if RAGFlow SDK is available."""
        self._ensure_initialized()
        return self._ragflow is not None

    def get_stats(self) -> dict[str, Any]:
        """Return adapter statistics."""
        return {
            **self._stats,
            "base_url": self._base_url,
            "has_api_key": bool(self._api_key),
            "default_dataset_id": self._default_dataset_id,
            "initialized": self._initialized,
            "init_error": self._init_error,
            "enabled": self._enabled,
        }

    def health_check(self) -> dict[str, Any]:
        """Check RAGFlow server connectivity and SDK availability."""
        checks = []

        try:
            from ragflow_sdk import RAGFlow  # noqa: F401
            checks.append({"name": "import", "status": "ok"})
        except ImportError:
            checks.append({"name": "import", "status": "fail"})

        if self._ensure_initialized():
            try:
                datasets = self._ragflow.list_datasets()
                checks.append({"name": "server", "status": "ok",
                               "detail": f"Connected to {self._base_url}, {len(datasets)} datasets"})
            except Exception as e:
                checks.append({"name": "server", "status": "fail", "detail": str(e)})
        else:
            checks.append({"name": "server", "status": "fail", "detail": self._init_error})

        return {"healthy": all(c["status"] == "ok" for c in checks),
                "checks": checks, "timestamp": time.time()}


# ── Factory ──────────────────────────────────────────────────────


def create_ragflow_bridge() -> RAGFlowBridge | None:
    """Create a RAGFlowBridge if ragflow-sdk is installed."""
    try:
        from ragflow_sdk import RAGFlow  # noqa: F401
        return RAGFlowBridge()
    except ImportError:
        logger.info("ragflow-sdk not installed — RAGFlow document RAG unavailable")
        return None


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAGFlow Bridge CLI")
    parser.add_argument("--query", help="Ask a question")
    parser.add_argument("--upload", help="Upload a document file")
    parser.add_argument("--dataset", help="Dataset name or ID")
    parser.add_argument("--create-dataset", help="Create a new dataset")
    parser.add_argument("--list-datasets", action="store_true", help="List datasets")
    parser.add_argument("--health", action="store_true", help="Run health check")
    args = parser.parse_args()

    bridge = RAGFlowBridge()

    if args.health:
        result = bridge.health_check()
    elif args.create_dataset:
        result = bridge.create_dataset(args.create_dataset)
    elif args.list_datasets:
        result = bridge.list_datasets()
    elif args.upload and args.dataset:
        result = bridge.upload_document(args.dataset, args.upload)
    elif args.query:
        result = bridge.query(args.query, dataset_id=args.dataset)
    else:
        result = {"status": bridge.available(), "stats": bridge.get_stats()}

    print(json.dumps(result, indent=2, default=str))
