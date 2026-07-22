"""
Weaviate Bridge — Production Vector Database
==============================================

Wraps the `weaviate-client` SDK to provide a production-grade vector
database with hybrid (BM25 + vector) search, embedded mode for local
development, and full collection management.

Weaviate handles vector indexing (HNSW, IVF), inverted indices for
keyword search, and supports multi-tenancy, replication, and sharding
for horizontal scaling.

Architecture:
    - Lazy initialization of Weaviate client on first use
    - Supports embedded mode (local) and remote gRPC/HTTP connections
    - Collection CRUD with configurable vectorizers
    - Batch insert with insert_many for efficient loading
    - Hybrid search (BM25 + vector) and pure near-text search
    - Graceful fallback when weaviate-client is not installed

Usage:
    from src.integration.weaviate_bridge import WeaviateBridge

    bridge = WeaviateBridge()
    collection = bridge.create_collection(
        name="Articles",
        properties=[{"name": "title", "data_type": "text"},
                    {"name": "content", "data_type": "text"}],
    )
    bridge.insert("Articles", {"title": "Hello", "content": "World"})
    results = bridge.hybrid_search("Articles", "Hello", limit=5)
    # => {"results": [...], "total_count": 1}

Environment:
    WEAVIATE_MODE        : "embedded" or "remote" (default: embedded)
    WEAVIATE_HOST        : gRPC host for remote mode (default: localhost)
    WEAVIATE_HTTP_PORT   : HTTP port for remote mode (default: 8080)
    WEAVIATE_GRPC_PORT   : gRPC port for remote mode (default: 50051)
    WEAVIATE_EMBEDDED_PATH: Persistence data path for embedded mode
    WEAVIATE_API_KEY     : API key for WCS/cloud instances
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("forgeai.integration.weaviate")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_MODE = "embedded"
DEFAULT_HOST = "localhost"
DEFAULT_HTTP_PORT = 8080
DEFAULT_GRPC_PORT = 50051
DEFAULT_EMBEDDED_PATH = str(Path.cwd() / "weaviate_data")


class WeaviateBridge:
    """Production vector database with hybrid search via Weaviate.

    Provides:
    - Collection CRUD (create, get, list, delete, exists)
    - Single and batch data insertion
    - Hybrid search (BM25 keyword + vector) and near_text search
    - Fetch objects with pagination (limit/offset)
    - Collection statistics and health checks

    Lazy-initializes the Weaviate client on first use.
    Supports both embedded (local) and remote gRPC/HTTP modes.
    """

    def __init__(
        self,
        mode: Literal["embedded", "remote"] | None = None,
        host: str | None = None,
        http_port: int | None = None,
        grpc_port: int | None = None,
        embedded_path: str | None = None,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> None:
        self._mode = mode or os.environ.get("WEAVIATE_MODE", DEFAULT_MODE)
        self._host = host or os.environ.get("WEAVIATE_HOST", DEFAULT_HOST)
        self._http_port = http_port or int(os.environ.get("WEAVIATE_HTTP_PORT", str(DEFAULT_HTTP_PORT)))
        self._grpc_port = grpc_port or int(os.environ.get("WEAVIATE_GRPC_PORT", str(DEFAULT_GRPC_PORT)))
        self._embedded_path = embedded_path or os.environ.get("WEAVIATE_EMBEDDED_PATH", DEFAULT_EMBEDDED_PATH)
        self._api_key = api_key or os.environ.get("WEAVIATE_API_KEY", "")
        self._headers = headers or {}
        self._enabled = enabled

        self._client = None
        self._initialized = False
        self._init_error: str | None = None

        self._stats = {
            "collections_created": 0,
            "objects_inserted": 0,
            "queries_run": 0,
            "hybrid_queries": 0,
            "near_text_queries": 0,
            "fetch_queries": 0,
            "errors": 0,
            "last_error": None,
            "avg_query_ms": 0.0,
        }

    # ── Lazy Initialization ──────────────────────────────────────

    def _ensure_initialized(self) -> bool:
        """Initialize Weaviate client on first use."""
        if self._initialized:
            return self._client is not None

        if not self._enabled:
            self._initialized = True
            self._init_error = "Weaviate bridge disabled"
            logger.info("WeaviateBridge is disabled")
            return False

        try:
            import weaviate

            if self._mode == "remote":
                # Connect to a remote Weaviate instance
                connect_params: dict[str, Any] = {
                    "host": self._host,
                    "port": self._http_port,
                    "grpc_port": self._grpc_port,
                }
                if self._api_key:
                    connect_params["auth_credentials"] = weaviate.auth.AuthApiKey(self._api_key)
                if self._headers:
                    connect_params["headers"] = self._headers

                self._client = weaviate.connect_to_local(**connect_params)
            else:
                # Embedded mode — runs Weaviate in-process
                embed_params: dict[str, Any] = {
                    "persistence_data_path": self._embedded_path,
                }
                if self._headers:
                    embed_params["headers"] = self._headers

                self._client = weaviate.connect_to_embedded(**embed_params)

            self._weaviate = weaviate
            self._initialized = True
            logger.info(f"Weaviate client initialized (mode={self._mode}, persistence={self._embedded_path})")
            return True

        except ImportError:
            self._init_error = "weaviate-client not installed. Run: pip install weaviate-client"
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"WeaviateBridge init failed: {e}")

        self._initialized = True
        return False

    # ── Collection Management ────────────────────────────────────

    def create_collection(
        self,
        name: str,
        properties: list[dict[str, Any]] | None = None,
        vectorizer: str | None = None,
        generative_model: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new collection (analogous to a table/index).

        Args:
            name: Collection name.
            properties: List of property dicts with "name" and "data_type"
                       (e.g., {"name": "title", "data_type": "text"}).
                       Supported types: text, int, number, boolean, date,
                       text[], int[], number[], boolean[].
            vectorizer: Vectorizer module (e.g., "text2vec-openai",
                       "text2vec-huggingface", "text2vec-ollama").
                       If None, no automatic vectorization (must provide
                       vectors manually).
            generative_model: Generative AI module for RAG-style queries
                             (e.g., "generative-openai", "generative-ollama").
            description: Human-readable description of the collection.

        Returns:
            Dict with collection name, status, and config.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "Weaviate not available"}

        try:
            import weaviate.classes.config as wvcc

            # Build property definitions
            prop_defs = []
            if properties:
                for p in properties:
                    dt_name = p.get("data_type", "text").upper()
                    dt = getattr(wvcc.DataType, dt_name, wvcc.DataType.TEXT)
                    prop_defs.append(
                        wvcc.Property(
                            name=p["name"],
                            data_type=dt,
                        )
                    )

            # Build vectorizer config
            vectorizer_config = None
            if vectorizer:
                try:
                    vectorizer_config = getattr(
                        wvcc.Configure.Vectorizer,
                        vectorizer.replace("-", "_"),
                    )()
                except AttributeError:
                    logger.warning(f"Unknown vectorizer: {vectorizer}, using none")

            # Build generative config
            generative_config = None
            if generative_model:
                try:
                    generative_config = getattr(
                        wvcc.Configure.Generative,
                        generative_model.replace("-", "_"),
                    )()
                except AttributeError:
                    logger.warning(f"Unknown generative model: {generative_model}, using none")

            # Create the collection
            create_kwargs: dict[str, Any] = {
                "name": name,
                "description": description or None,
            }
            if prop_defs:
                create_kwargs["properties"] = prop_defs
            if vectorizer_config:
                create_kwargs["vectorizer_config"] = vectorizer_config
            if generative_config:
                create_kwargs["generative_config"] = generative_config

            self._client.collections.create(**create_kwargs)
            self._stats["collections_created"] += 1

            return {
                "name": name,
                "properties": len(prop_defs),
                "vectorizer": vectorizer or "none",
                "status": "created",
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"error": str(e)}

    def get_collection(self, name: str) -> dict[str, Any]:
        """Get a collection by name and return its config.

        Args:
            name: Collection name.

        Returns:
            Dict with collection metadata and property schema.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "Weaviate not available"}

        try:
            collection = self._client.collections.get(name)
            cfg = collection.config.get()

            properties = []
            for prop in getattr(cfg, "properties", []):
                properties.append({
                    "name": getattr(prop, "name", ""),
                    "data_type": str(getattr(prop, "data_type", "")),
                    "indexed": getattr(prop, "index_filterable", True),
                })

            return {
                "name": name,
                "properties": properties,
                "vectorizer": str(getattr(cfg, "vectorizer", "")),
                "description": getattr(cfg, "description", ""),
                "exists": True,
            }

        except Exception as e:
            return {"error": str(e)}

    def list_collections(self) -> list[dict[str, Any]]:
        """List all collections with their names.

        Returns:
            List of collection summary dicts.
        """
        if not self._ensure_initialized() or self._client is None:
            return []

        try:
            collections = self._client.collections.list_all()
            return [
                {"name": str(c)}
                for c in collections
            ]
        except Exception as e:
            self._stats["errors"] += 1
            return []

    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists.

        Args:
            name: Collection name.

        Returns:
            True if the collection exists.
        """
        if not self._ensure_initialized() or self._client is None:
            return False

        try:
            collections = self.list_collections()
            return any(c["name"] == name for c in collections)
        except Exception:
            return False

    def delete_collection(self, name: str) -> bool:
        """Delete a collection and all its data.

        Args:
            name: Collection name.

        Returns:
            True if deletion succeeded.
        """
        if not self._ensure_initialized() or self._client is None:
            return False

        try:
            self._client.collections.delete(name)
            return True
        except Exception:
            return False

    # ── Data Insertion ───────────────────────────────────────────

    def insert(
        self,
        collection_name: str,
        properties: dict[str, Any],
        vector: list[float] | None = None,
    ) -> dict[str, Any]:
        """Insert a single object into a collection.

        Args:
            collection_name: Target collection.
            properties: Dict of property key-value pairs.
            vector: Optional explicit vector (bypasses vectorizer).

        Returns:
            Dict with insertion status and object UUID.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "Weaviate not available"}

        try:
            collection = self._client.collections.get(collection_name)
            kwargs: dict[str, Any] = {"properties": properties}
            if vector is not None:
                kwargs["vector"] = vector

            result = collection.data.insert(**kwargs)
            uuid = str(result) if result else ""

            self._stats["objects_inserted"] += 1
            return {"uuid": uuid, "status": "inserted"}

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"error": str(e)}

    def insert_batch(
        self,
        collection_name: str,
        objects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Insert multiple objects efficiently using insert_many.

        Each object in the list should have "properties" and
        optionally "vector".

        Args:
            collection_name: Target collection.
            objects: List of dicts with "properties" and optional "vector".

        Returns:
            Dict with inserted count, errors, and details.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "Weaviate not available", "inserted": 0}

        try:
            collection = self._client.collections.get(collection_name)

            # Convert to the format expected by insert_many
            objs = []
            for obj in objects:
                props = obj.get("properties", obj)
                entry: dict[str, Any] = {"properties": props}
                if "vector" in obj:
                    entry["vector"] = obj["vector"]
                objs.append(entry)

            response = collection.data.insert_many(objs)
            inserted = len(objs)

            error_details = []
            if hasattr(response, "has_errors") and response.has_errors:
                for err in getattr(response, "errors", []):
                    error_details.append(str(err))

            self._stats["objects_inserted"] += inserted
            return {
                "inserted": inserted,
                "errors": len(error_details),
                "error_details": error_details[:5],  # Limit to first 5
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"inserted": 0, "error": str(e)}

    # ── Search ───────────────────────────────────────────────────

    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        alpha: float = 0.5,
        limit: int = 10,
        offset: int = 0,
        return_properties: list[str] | None = None,
    ) -> dict[str, Any]:
        """Hybrid search combining BM25 keyword and vector search.

        Weaviate's hybrid search merges keyword (BM25F) and vector
        similarity results using the alpha parameter:
        - alpha=1.0: pure vector search
        - alpha=0.0: pure keyword search
        - alpha=0.5: balanced hybrid

        Args:
            collection_name: Collection to search.
            query: Search text.
            alpha: Balance between vector (1.0) and keyword (0.0).
            limit: Max results to return.
            offset: Pagination offset.
            return_properties: Specific properties to return (None = all).

        Returns:
            Dict with "results" (list of matches) and metadata.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"results": [], "error": self._init_error or "Weaviate not available"}

        try:
            start = time.time()
            collection = self._client.collections.get(collection_name)

            result = collection.query.hybrid(
                query=query,
                alpha=alpha,
                limit=limit,
                offset=offset,
                return_properties=return_properties,
            )

            elapsed = time.time() - start
            self._stats["hybrid_queries"] += 1
            self._stats["queries_run"] += 1
            self._stats["avg_query_ms"] = (
                (self._stats["avg_query_ms"] * (self._stats["queries_run"] - 1) + elapsed * 1000)
                / self._stats["queries_run"]
            )

            results = []
            for obj in getattr(result, "objects", []):
                results.append({
                    "uuid": str(getattr(obj, "uuid", "")),
                    "properties": self._serialize_properties(getattr(obj, "properties", {})),
                    "score": getattr(obj, "metadata", None) and getattr(obj.metadata, "score", None),
                })

            return {
                "results": results,
                "total": len(results),
                "elapsed_seconds": round(elapsed, 2),
                "query": query,
                "alpha": alpha,
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"results": [], "error": str(e)}

    def near_text_search(
        self,
        collection_name: str,
        query: str,
        limit: int = 10,
        offset: int = 0,
        certainty: float | None = None,
        distance: float | None = None,
        return_properties: list[str] | None = None,
    ) -> dict[str, Any]:
        """Pure vector search using near_text.

        Converts the query text into a vector via the configured
        vectorizer and finds the most similar objects by vector distance.

        Args:
            collection_name: Collection to search.
            query: Natural language query.
            limit: Max results to return.
            offset: Pagination offset.
            certainty: Minimum certainty threshold (0-1).
            distance: Maximum distance threshold.
            return_properties: Specific properties to return.

        Returns:
            Dict with "results" and metadata.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"results": [], "error": self._init_error or "Weaviate not available"}

        try:
            start = time.time()
            collection = self._client.collections.get(collection_name)

            near_text_kwargs: dict[str, Any] = {
                "query": query,
                "limit": limit,
                "offset": offset,
                "return_properties": return_properties,
            }
            if certainty is not None:
                near_text_kwargs["certainty"] = certainty
            if distance is not None:
                near_text_kwargs["distance"] = distance

            result = collection.query.near_text(**near_text_kwargs)

            elapsed = time.time() - start
            self._stats["near_text_queries"] += 1
            self._stats["queries_run"] += 1
            self._stats["avg_query_ms"] = (
                (self._stats["avg_query_ms"] * (self._stats["queries_run"] - 1) + elapsed * 1000)
                / self._stats["queries_run"]
            )

            results = []
            for obj in getattr(result, "objects", []):
                results.append({
                    "uuid": str(getattr(obj, "uuid", "")),
                    "properties": self._serialize_properties(getattr(obj, "properties", {})),
                    "score": getattr(obj, "metadata", None) and getattr(obj.metadata, "score", None),
                })

            return {
                "results": results,
                "total": len(results),
                "elapsed_seconds": round(elapsed, 2),
                "query": query,
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"results": [], "error": str(e)}

    def fetch_objects(
        self,
        collection_name: str,
        limit: int = 20,
        offset: int = 0,
        return_properties: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch objects with pagination (no search, just retrieval).

        Useful for browsing all objects in a collection or for
        pagination in dashboards.

        Args:
            collection_name: Collection to fetch from.
            limit: Max objects to return.
            offset: Pagination offset.
            return_properties: Specific properties to return.

        Returns:
            Dict with "objects" and total count.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"objects": [], "error": self._init_error or "Weaviate not available"}

        try:
            start = time.time()
            collection = self._client.collections.get(collection_name)

            result = collection.query.fetch_objects(
                limit=limit,
                offset=offset,
                return_properties=return_properties,
            )

            elapsed = time.time() - start
            self._stats["fetch_queries"] += 1
            self._stats["queries_run"] += 1

            objects = []
            for obj in getattr(result, "objects", []):
                objects.append({
                    "uuid": str(getattr(obj, "uuid", "")),
                    "properties": self._serialize_properties(getattr(obj, "properties", {})),
                })

            # Try to get total count via aggregate
            total_count = None
            try:
                agg = collection.aggregate.over_all(total_count=True)
                total_count = getattr(agg, "total_count", None)
            except Exception:
                pass

            return {
                "objects": objects,
                "total": len(objects),
                "total_in_collection": total_count,
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"objects": [], "error": str(e)}

    def collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get aggregate statistics for a collection.

        Args:
            collection_name: Collection to inspect.

        Returns:
            Dict with total_count, property stats, and vector info.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "Weaviate not available"}

        try:
            collection = self._client.collections.get(collection_name)

            # Get total object count
            agg = collection.aggregate.over_all(total_count=True)
            total_count = getattr(agg, "total_count", None)

            # Get schema info
            cfg = collection.config.get()
            num_properties = len(getattr(cfg, "properties", []))

            return {
                "name": collection_name,
                "object_count": total_count,
                "num_properties": num_properties,
                "status": "available",
            }

        except Exception as e:
            return {"error": str(e)}

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _serialize_properties(props: dict[str, Any]) -> dict[str, Any]:
        """Serialise complex property values (UUIDs, dates) to strings.

        Weaviate may return non-JSON-serialisable types like UUID
        objects in property values. This helper converts them safely.
        """
        result: dict[str, Any] = {}
        for key, value in props.items():
            if hasattr(value, "hex") and hasattr(value, "version"):
                # UUID or similar
                result[key] = str(value)
            elif isinstance(value, (dict, list, str, int, float, bool)):
                result[key] = value
            elif value is None:
                result[key] = None
            else:
                result[key] = str(value)
        return result

    # ── Info ─────────────────────────────────────────────────────

    def available(self) -> bool:
        """Check if Weaviate client is available and connected."""
        self._ensure_initialized()
        return self._client is not None

    def is_ready(self) -> bool:
        """Check if Weaviate server is ready to accept requests."""
        if not self._ensure_initialized() or self._client is None:
            return False
        try:
            ready = self._client.is_ready()
            return bool(ready)
        except Exception:
            return False

    def get_stats(self) -> dict[str, Any]:
        """Return adapter statistics."""
        ready = False
        try:
            ready = self.is_ready()
        except Exception:
            pass

        return {
            **self._stats,
            "mode": self._mode,
            "host": f"{self._host}:{self._http_port}",
            "embedded_path": self._embedded_path,
            "initialized": self._initialized,
            "init_error": self._init_error,
            "ready": ready,
            "enabled": self._enabled,
        }

    def health_check(self) -> dict[str, Any]:
        """Comprehensive health check — import, connection, and readiness."""
        checks = []

        try:
            import weaviate  # noqa: F401
            checks.append({"name": "import", "status": "ok"})
        except ImportError:
            checks.append({"name": "import", "status": "fail"})

        if self._ensure_initialized():
            checks.append({
                "name": "connect",
                "status": "ok",
                "detail": f"mode={self._mode}, persistence={self._embedded_path}",
            })
        else:
            checks.append({
                "name": "connect",
                "status": "fail",
                "detail": self._init_error,
            })

        if self._client is not None:
            try:
                ready = self._client.is_ready()
                checks.append({
                    "name": "ready",
                    "status": "ok" if ready else "degraded",
                    "detail": "Server ready" if ready else "Server not ready",
                })
            except Exception as e:
                checks.append({"name": "ready", "status": "fail", "detail": str(e)})
        else:
            checks.append({"name": "ready", "status": "fail", "detail": "No client"})

        return {
            "healthy": all(c["status"] == "ok" for c in checks),
            "checks": checks,
            "timestamp": time.time(),
        }

    def close(self) -> None:
        """Close the Weaviate client and release resources."""
        if self._client is not None:
            try:
                self._client.close()
                logger.info("Weaviate client closed")
            except Exception as e:
                logger.warning(f"Error closing Weaviate client: {e}")
            self._client = None
            self._initialized = False

    def __enter__(self) -> "WeaviateBridge":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── Factory ──────────────────────────────────────────────────────


def create_weaviate_bridge() -> WeaviateBridge | None:
    """Create a WeaviateBridge if weaviate-client is installed.

    Returns None if the library is not available (graceful fallback).
    """
    try:
        import weaviate  # noqa: F401
        return WeaviateBridge()
    except ImportError:
        logger.info("weaviate-client not installed — vector database unavailable")
        return None


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Weaviate Bridge CLI")
    parser.add_argument("--create-collection", help="Create a new collection (provide name)")
    parser.add_argument("--properties", help="JSON string of properties for creation")
    parser.add_argument("--list-collections", action="store_true", help="List all collections")
    parser.add_argument("--get-collection", help="Get collection config by name")
    parser.add_argument("--delete-collection", help="Delete a collection by name")
    parser.add_argument("--insert", help="Insert object as JSON string")
    parser.add_argument("--collection", help="Collection name for search/insert operations")
    parser.add_argument("--hybrid", help="Hybrid search query")
    parser.add_argument("--near-text", help="Near-text search query")
    parser.add_argument("--fetch", type=int, help="Fetch N objects (requires --collection)")
    parser.add_argument("--stats", help="Get collection stats (requires --collection)")
    parser.add_argument("--limit", type=int, default=10, help="Search result limit")
    parser.add_argument("--alpha", type=float, default=0.5, help="Hybrid search alpha")
    parser.add_argument("--health", action="store_true", help="Run health check")
    parser.add_argument("--mode", choices=["embedded", "remote"], default=DEFAULT_MODE)
    args = parser.parse_args()

    bridge = WeaviateBridge(mode=args.mode)

    if args.health:
        result = bridge.health_check()
    elif args.list_collections:
        result = bridge.list_collections()
    elif args.get_collection:
        result = bridge.get_collection(args.get_collection)
    elif args.delete_collection:
        result = {"deleted": bridge.delete_collection(args.delete_collection)}
    elif args.create_collection:
        props = None
        if args.properties:
            props = json.loads(args.properties)
        result = bridge.create_collection(args.create_collection, properties=props)
    elif args.insert and args.collection:
        obj = json.loads(args.insert)
        result = bridge.insert(args.collection, obj)
    elif args.hybrid and args.collection:
        result = bridge.hybrid_search(args.collection, args.hybrid,
                                      alpha=args.alpha, limit=args.limit)
    elif args.near_text and args.collection:
        result = bridge.near_text_search(args.collection, args.near_text,
                                         limit=args.limit)
    elif args.fetch and args.collection:
        result = bridge.fetch_objects(args.collection, limit=args.fetch)
    elif args.stats and args.collection:
        result = bridge.collection_stats(args.stats)
    else:
        result = {"status": bridge.available(), "ready": bridge.is_ready(),
                   "stats": bridge.get_stats()}

    print(json.dumps(result, indent=2, default=str))
