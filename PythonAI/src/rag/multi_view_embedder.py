"""
ForgeAI Multi-View Embedder — 3 Embeddings Per Chunk
=====================================================

Generates separate embeddings for:
  1. Code text (full code with comments)
  2. Docstrings (API documentation surface)
  3. Function signatures (structural interface)

This allows the retriever to match queries to the most relevant
view of the code, improving retrieval accuracy significantly.

Usage:
    from src.rag.multi_view_embedder import MultiViewEmbedder

    embedder = MultiViewEmbedder()
    views = embedder.embed_chunk("def foo(x):\\n    '''Docstring'''\\n    return x + 1")
    # views = {"code_text": [...], "docstring": [...], "signature": [...]}
"""

from __future__ import annotations

import ast
import re
from typing import Any


class MultiViewEmbedder:
    """Generates three separate embeddings per code chunk.

    Each view captures a different aspect of the code:
    - code_text: Full code including comments and logic
    - docstring: API documentation surface
    - signature: Structural interface (function/class names + params)
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._available = False
        self._init_model()

    def _init_model(self) -> None:
        """Initialize embedding model (sentence-transformers or fallback)."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            self._model = SentenceTransformer(self._model_name)
            self._available = True
        except ImportError:
            self._available = False

    def embed_chunk(self, code: str, language: str = "python") -> dict[str, list[float]]:
        """Generate 3 views of embeddings for a code chunk.

        Args:
            code: Source code text
            language: Programming language (default: python)

        Returns:
            dict with keys: code_text, docstring, signature
            Each value is an embedding vector (list of floats)
        """
        views = self._extract_views(code, language)

        embeddings: dict[str, list[float]] = {}
        for view_name, text in views.items():
            if text and text.strip():
                embeddings[view_name] = self._embed(text)
            else:
                # If a view is empty, use a zero vector
                embeddings[view_name] = []

        return embeddings

    def embed_query(self, query: str) -> dict[str, list[float]]:
        """Embed a search query against all 3 views.

        The query is embedded once and used against all views.
        """
        return {
            "code_text": self._embed(query),
            "docstring": self._embed(query),
            "signature": self._embed(query),
        }

    def _embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        if self._available and self._model is not None:
            emb = self._model.encode(text, normalize_embeddings=True)
            return emb.tolist()

        # Fallback: return empty (caller should handle)
        return []

    def _extract_views(self, code: str, language: str) -> dict[str, str]:
        """Extract 3 text views from a code chunk."""
        views: dict[str, str] = {
            "code_text": code,
            "docstring": "",
            "signature": "",
        }

        if language == "python":
            views = self._extract_python_views(code)
        else:
            # For non-Python, use regex-based extraction
            views = self._extract_generic_views(code)

        return views

    def _extract_python_views(self, code: str) -> dict[str, str]:
        """Extract views from Python code using AST."""
        views: dict[str, str] = {
            "code_text": code,
            "docstring": "",
            "signature": "",
        }

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Fall back to regex
            return self._extract_generic_views(code)

        docstrings: list[str] = []
        signatures: list[str] = []

        for node in ast.walk(tree):
            # Function definitions
            if isinstance(node, ast.FunctionDef):
                args = []
                for arg in node.args.args:
                    if arg.arg != "self":
                        args.append(arg.arg)
                sig = f"def {node.name}({', '.join(args)})"
                if node.returns:
                    try:
                        sig += f" -> {ast.dump(node.returns)}"
                    except Exception:
                        pass
                signatures.append(sig)

                # Extract docstring
                doc = ast.get_docstring(node)
                if doc:
                    docstrings.append(doc)

            # Class definitions
            elif isinstance(node, ast.ClassDef):
                bases = [ast.dump(b) for b in node.bases] if node.bases else []
                sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
                signatures.append(sig)

                doc = ast.get_docstring(node)
                if doc:
                    docstrings.append(doc)

            # Async function definitions
            elif isinstance(node, ast.AsyncFunctionDef):
                args = []
                for arg in node.args.args:
                    if arg.arg != "self":
                        args.append(arg.arg)
                sig = f"async def {node.name}({', '.join(args)})"
                signatures.append(sig)

                doc = ast.get_docstring(node)
                if doc:
                    docstrings.append(doc)

        views["docstring"] = "\n".join(docstrings)
        views["signature"] = "\n".join(signatures)

        return views

    def _extract_generic_views(self, code: str) -> dict[str, str]:
        """Extract views from non-Python code using regex."""
        views: dict[str, str] = {
            "code_text": code,
            "docstring": "",
            "signature": "",
        }

        # Extract comments (any language)
        comments = re.findall(r"(?:#|//|--|;|%|')\s*(.*)", code)
        views["docstring"] = "\n".join(c.strip() for c in comments if c.strip())

        # Extract function-like patterns
        funcs = re.findall(
            r"(?:def|function|func|fn|sub)\s+(\w+)\s*\(([^)]*)\)",
            code,
            re.IGNORECASE,
        )
        signatures = [f"def {name}({params})" for name, params in funcs]

        # Extract class-like patterns
        classes = re.findall(r"(?:class|struct|interface|trait)\s+(\w+)", code, re.IGNORECASE)
        for cls in classes:
            signatures.append(f"class {cls}")

        views["signature"] = "\n".join(signatures)

        return views

    @property
    def available(self) -> bool:
        return self._available

    @property
    def model_name(self) -> str:
        return self._model_name


def multi_view_similarity(
    query_embeddings: dict[str, list[float]],
    chunk_embeddings: dict[str, list[float]],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute weighted similarity across all 3 views.

    Args:
        query_embeddings: Query embeddings from embed_query()
        chunk_embeddings: Chunk embeddings from embed_chunk()
        weights: Per-view weights (default: code_text=0.4, docstring=0.35, signature=0.25)

    Returns:
        Weighted similarity score (0-1)
    """
    if weights is None:
        weights = {"code_text": 0.4, "docstring": 0.35, "signature": 0.25}

    import numpy as np

    total_score = 0.0
    total_weight = 0.0

    for view, weight in weights.items():
        q_emb = query_embeddings.get(view, [])
        c_emb = chunk_embeddings.get(view, [])

        if not q_emb or not c_emb:
            continue

        arr_q = np.array(q_emb, dtype=np.float32)
        arr_c = np.array(c_emb, dtype=np.float32)

        norm_q = np.linalg.norm(arr_q)
        norm_c = np.linalg.norm(arr_c)

        if norm_q > 0 and norm_c > 0:
            similarity = float(np.dot(arr_q, arr_c) / (norm_q * norm_c))
            total_score += weight * similarity
            total_weight += weight

    return total_score / max(total_weight, 0.01)


__all__ = [
    "MultiViewEmbedder",
    "multi_view_similarity",
]
