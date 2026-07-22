"""
OMNISCIENT Layer 3 — Knowledge Graph

A living NetworkX-based concept graph that connects isolated knowledge
chunks into a traversable web of understanding.

Nodes  = Knowledge chunks (each doc page, function, concept)
Edges  = Relationships (uses, extends, conflicts_with, deprecated_by, ...)

When a user asks about 'list', the graph traverses 2 hops to pull in:
  list → list_comprehension → generator_expression
  list → sorted_vs_sort → performance
  list → common_TypeError → debugging

This is the GAME CHANGER that moves the system from "search engine"
to "thinking engine."

Usage:
  python -m src.rag.knowledge_graph build
  python -m src.rag.knowledge_graph stats
  python -m src.rag.knowledge_graph query "list comprehension"
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent.parent

# ═══════════════════════════════════════
# PATHS
# ═══════════════════════════════════════
CHUNKS_FILE = ROOT / "data" / "raw" / "raw_chunks_godmode.json"
GRAPH_FILE = ROOT / "data" / "knowledge_graph.gpickle"
INDEX_FILE = ROOT / "data" / "kg_index.json"

# ═══════════════════════════════════════
# EDGE TYPES & WEIGHTS
# ═══════════════════════════════════════

EDGE_TYPES = {
    "uses": {"weight": 0.8, "desc": "A uses/requires B"},
    "extends": {"weight": 0.7, "desc": "A extends/inherits from B"},
    "see_also": {"weight": 0.6, "desc": "A is related to B"},
    "alternative_to": {"weight": 0.5, "desc": "A can replace B"},
    "common_mistake": {"weight": 0.9, "desc": "A has common mistake related to B"},
    "conflicts_with": {"weight": 0.4, "desc": "A conflicts with / contradicts B"},
    "version_changed": {"weight": 0.7, "desc": "Behavior changed across versions"},
    "deprecated_by": {"weight": 0.8, "desc": "A is deprecated in favor of B"},
    "prerequisite": {"weight": 0.9, "desc": "A must be understood before B"},
    "example_of": {"weight": 0.6, "desc": "A is an example/application of B"},
    "similar_to": {"weight": 0.5, "desc": "A is conceptually similar to B"},
    "part_of": {"weight": 0.7, "desc": "A is part of module/package B"},
}

# ═══════════════════════════════════════
# CONCEPT EXTRACTION PATTERNS
# ═══════════════════════════════════════

# Keywords that indicate relationships between concepts
_USES_PATTERNS = [
    re.compile(r"(?:requires?|depends?\s+on|built\s+on|uses?)\s+[:`](\w[\w.]*)", re.I),
    re.compile(r"(?:import|from)\s+([\w.]+)", re.ASCII),
]

_EXTENDS_PATTERNS = [
    re.compile(r"(?:subclass|inherits?\s+from|extends?|derived\s+from)\s+[:`](\w[\w.]*)", re.I),
    re.compile(r"class\s+\w+\((\w[\w.]*)\)", re.ASCII),
]

_SEEALSO_PATTERNS = [
    re.compile(r"(?:see\s+also|related|cf\.|compare\s+with)\s*:?\s*[:`](\w[\w.]*)", re.I),
    re.compile(r":mod:`(\w[\w.]*)`", re.ASCII),
    re.compile(r":func:`(\w[\w.]*)`", re.ASCII),
    re.compile(r":class:`(\w[\w.]*)`", re.ASCII),
]

_DEPRECATED_PATTERNS = [
    re.compile(r"deprecated.*?(?:use|replaced\s+by|see)\s+[:`](\w[\w.]*)", re.I),
    re.compile(r"(?:removed|replaced)\s+(?:in|by)\s+[:`]?(\w[\w.]*)", re.I),
]

_VERSION_PATTERNS = [
    re.compile(r"(?:changed|new|added)\s+in\s+(?:version\s+)?(\d\.\d+)", re.I),
    re.compile(r"(?:since|from)\s+Python\s+(\d\.\d+)", re.I),
    re.compile(r"deprecated\s+since\s+(?:version\s+)?(\d\.\d+)", re.I),
]

# Common concept groupings (manual knowledge)
_CONCEPT_GROUPS: dict[str, list[str]] = {
    "itertools": ["iterator", "generator", "chain", "islice", "product", "permutations"],
    "collections": ["defaultdict", "Counter", "OrderedDict", "deque", "namedtuple", "ChainMap"],
    "functools": ["partial", "lru_cache", "wraps", "reduce", "singledispatch"],
    "typing": ["Optional", "Union", "List", "Dict", "TypeVar", "Generic", "Protocol"],
    "dataclasses": ["dataclass", "field", "asdict", "astuple", "frozen"],
    "pathlib": ["Path", "PurePath", "PosixPath", "WindowsPath"],
    "asyncio": ["async", "await", "coroutine", "event_loop", "Task", "Future", "gather"],
    "threading": ["Thread", "Lock", "RLock", "Semaphore", "Event", "Condition"],
    "list": ["append", "extend", "sort", "sorted", "list_comprehension", "slice"],
    "dict": ["dictionary", "defaultdict", "dict_comprehension", "items", "values", "keys"],
    "string": ["str", "format", "f-string", "encode", "decode", "regex"],
    "exception": ["try", "except", "finally", "raise", "traceback", "BaseException"],
    "decorator": ["functools.wraps", "property", "staticmethod", "classmethod"],
    "context_manager": ["with", "contextlib", "__enter__", "__exit__"],
    "metaclass": ["type", "__new__", "__init_subclass__", "ABCMeta"],
    "descriptor": ["__get__", "__set__", "__delete__", "property"],
}


# ═══════════════════════════════════════
# NODE BUILDER
# ═══════════════════════════════════════


@dataclass
class GraphNode:
    """A node in the knowledge graph."""

    node_id: str
    title: str
    category: str
    version: str
    chunk_type: str
    text_preview: str  # First 300 chars
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


def _make_node_id(chunk: dict[str, Any]) -> str:
    """Create a stable, unique node ID from a chunk."""
    title = chunk.get("title", "untitled")
    version = chunk.get("version", "")
    category = chunk.get("category", "")
    raw = f"{category}:{title}:{version}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _extract_entities(text: str) -> dict[str, list[str]]:
    """Extract Python entities from text."""
    func_re = re.compile(r"(\w+)\s*\(", re.ASCII)
    class_re = re.compile(r"class\s+(\w+)", re.ASCII)
    module_re = re.compile(r"(?:import|from)\s+([\w.]+)", re.ASCII)

    skip = {
        "self",
        "cls",
        "None",
        "True",
        "False",
        "print",
        "len",
        "range",
        "str",
        "int",
        "float",
        "list",
        "dict",
        "set",
        "tuple",
        "type",
        "super",
        "isinstance",
        "issubclass",
        "hasattr",
        "getattr",
        "setattr",
        "delattr",
        "open",
        "input",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "format",
        "repr",
        "iter",
        "next",
        "map",
        "filter",
        "zip",
        "enumerate",
        "sorted",
        "reversed",
        "any",
        "all",
    }

    funcs = [f for f in set(func_re.findall(text)) if f not in skip and len(f) > 2]
    classes = [c for c in set(class_re.findall(text)) if len(c) > 2]
    modules = list(set(module_re.findall(text)))

    return {"functions": funcs[:15], "classes": classes[:10], "modules": modules[:10]}


def chunk_to_node(chunk: dict[str, Any]) -> GraphNode:
    """Convert a raw chunk into a graph node."""
    node_id = _make_node_id(chunk)
    title = re.sub(r"[¶§#*`]", "", chunk.get("title", "untitled")).strip()
    text = chunk.get("text", "")
    codes = chunk.get("codes", [])
    code_text = "\n".join(str(c)[:500] for c in codes[:2]) if codes else ""
    all_text = f"{text}\n{code_text}"

    entities = _extract_entities(all_text)

    # Extract keywords from title
    words = re.findall(r"[a-z][a-z_]{2,}", title.lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "python",
        "module",
        "function",
        "class",
        "method",
        "objects",
        "types",
    }
    keywords = [w for w in words if w not in stop][:10]

    return GraphNode(
        node_id=node_id,
        title=title[:200],
        category=chunk.get("category", ""),
        version=chunk.get("version", ""),
        chunk_type=chunk.get("type", ""),
        text_preview=text[:300],
        functions=entities["functions"],
        classes=entities["classes"],
        modules=entities["modules"],
        keywords=keywords,
    )


# ═══════════════════════════════════════
# EDGE BUILDER
# ═══════════════════════════════════════


def _find_pattern_edges(
    text: str,
    patterns: list[re.Pattern],
    edge_type: str,
) -> list[tuple[str, str]]:
    """Find edges from regex patterns. Returns [(target_concept, edge_type)]."""
    targets: list[tuple[str, str]] = []
    for pattern in patterns:
        matches = pattern.findall(text)
        for match in matches:
            clean = match.strip().lower().replace("::", ".").replace(":", ".")
            if len(clean) > 2 and not clean.startswith("_"):
                targets.append((clean, edge_type))
    return targets


def extract_edges(chunk: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract all relationship edges from a chunk's text."""
    text = chunk.get("text", "") + " " + chunk.get("title", "")
    edges: list[tuple[str, str]] = []

    edges.extend(_find_pattern_edges(text, _USES_PATTERNS, "uses"))
    edges.extend(_find_pattern_edges(text, _EXTENDS_PATTERNS, "extends"))
    edges.extend(_find_pattern_edges(text, _SEEALSO_PATTERNS, "see_also"))
    edges.extend(_find_pattern_edges(text, _DEPRECATED_PATTERNS, "deprecated_by"))

    return edges


# ═══════════════════════════════════════
# KNOWLEDGE GRAPH
# ═══════════════════════════════════════


class KnowledgeGraph:
    """
    The living knowledge graph. Connects concepts into a traversable web.

    Usage:
        kg = KnowledgeGraph()
        kg.build_from_chunks(chunks)
        kg.save()

        # Query
        results = kg.query("list comprehension", hops=2, max_results=10)
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._title_to_id: dict[str, str] = {}  # title_lower → node_id
        self._keyword_to_ids: dict[str, list[str]] = defaultdict(list)  # keyword → [node_ids]
        self._entity_to_ids: dict[str, list[str]] = defaultdict(list)  # entity → [node_ids]

    # ─── Build ──────────────────────────

    def build_from_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Build the knowledge graph from raw chunks."""
        skip_types = {"font", "image_png", "image_jpg", "image_gif", "static", "css"}
        valid = [c for c in chunks if c.get("type", "") not in skip_types and len(c.get("text", "")) > 50]

        print(f"\n[KG] Building knowledge graph from {len(valid):,} chunks...")

        # Phase 1: Create nodes
        print("[KG] Phase 1/3 — Creating nodes...")
        for chunk in tqdm(valid, desc="Nodes"):
            node = chunk_to_node(chunk)
            self._add_node(node)

        print(f"[KG]   → {self.graph.number_of_nodes():,} nodes created")

        # Phase 2: Extract explicit edges from text
        print("[KG] Phase 2/3 — Extracting edges from text...")
        explicit_edges = 0
        for chunk in tqdm(valid, desc="Edges"):
            source_id = _make_node_id(chunk)
            if source_id not in self.graph:
                continue

            edges = extract_edges(chunk)
            for target_concept, edge_type in edges:
                target_ids = self._resolve_concept(target_concept)
                for target_id in target_ids:
                    if target_id != source_id and not self.graph.has_edge(source_id, target_id):
                        weight = EDGE_TYPES.get(edge_type, {}).get("weight", 0.5)
                        self.graph.add_edge(
                            source_id,
                            target_id,
                            type=edge_type,
                            weight=weight,
                        )
                        explicit_edges += 1

        print(f"[KG]   → {explicit_edges:,} explicit edges")

        # Phase 3: Auto-link by concept group similarity
        print("[KG] Phase 3/3 — Auto-linking by concept groups...")
        auto_edges = self._auto_link_concept_groups()
        print(f"[KG]   → {auto_edges:,} auto-linked edges")

        total_edges = self.graph.number_of_edges()
        print(f"\n[KG] COMPLETE: {self.graph.number_of_nodes():,} nodes, {total_edges:,} edges")

    def _add_node(self, node: GraphNode) -> None:
        """Add a node and update indexes."""
        self.graph.add_node(
            node.node_id,
            title=node.title,
            category=node.category,
            version=node.version,
            chunk_type=node.chunk_type,
            text_preview=node.text_preview,
            functions=node.functions,
            classes=node.classes,
            modules=node.modules,
            keywords=node.keywords,
        )

        # Index by title
        title_key = node.title.lower().strip()
        self._title_to_id[title_key] = node.node_id

        # Index by keywords
        for kw in node.keywords:
            self._keyword_to_ids[kw].append(node.node_id)

        # Index by entities
        for fn in node.functions:
            self._entity_to_ids[fn.lower()].append(node.node_id)
        for cls in node.classes:
            self._entity_to_ids[cls.lower()].append(node.node_id)
        for mod in node.modules:
            self._entity_to_ids[mod.lower()].append(node.node_id)

    def _resolve_concept(self, concept: str) -> list[str]:
        """Resolve a concept name to node IDs."""
        concept_lower = concept.lower().strip()
        results: list[str] = []

        # Exact title match
        if concept_lower in self._title_to_id:
            results.append(self._title_to_id[concept_lower])

        # Entity match
        if concept_lower in self._entity_to_ids:
            results.extend(self._entity_to_ids[concept_lower])

        # Keyword match
        if concept_lower in self._keyword_to_ids:
            results.extend(self._keyword_to_ids[concept_lower])

        # Partial title match (last resort)
        if not results:
            for title, nid in self._title_to_id.items():
                if concept_lower in title or title in concept_lower:
                    results.append(nid)
                    if len(results) >= 3:
                        break

        return list(set(results))[:5]

    def _auto_link_concept_groups(self) -> int:
        """Auto-link nodes that belong to the same concept group."""
        edges_added = 0
        for group_name, members in _CONCEPT_GROUPS.items():
            group_nodes: list[str] = []
            for member in members:
                ids = self._resolve_concept(member)
                group_nodes.extend(ids)

            group_nodes = list(set(group_nodes))

            # Link each pair within the group
            for i, n1 in enumerate(group_nodes):
                for n2 in group_nodes[i + 1 :]:
                    if not self.graph.has_edge(n1, n2):
                        self.graph.add_edge(n1, n2, type="similar_to", weight=0.5)
                        edges_added += 1
                    if not self.graph.has_edge(n2, n1):
                        self.graph.add_edge(n2, n1, type="similar_to", weight=0.5)
                        edges_added += 1

        return edges_added

    # ─── Query ──────────────────────────

    def query(
        self,
        question: str,
        hops: int = 2,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Query the knowledge graph for a question.

        1. Extract key concepts from question
        2. Find matching nodes
        3. Traverse N hops to find related concepts
        4. Return ranked results
        """
        if self.graph.number_of_nodes() == 0:
            return []

        # Extract query concepts
        words = re.findall(r"[a-z][a-z_]{2,}", question.lower())
        stop = {
            "how",
            "what",
            "why",
            "does",
            "can",
            "the",
            "and",
            "for",
            "with",
            "python",
            "explain",
            "show",
            "give",
            "tell",
            "please",
            "help",
            "using",
            "about",
            "work",
            "working",
        }
        concepts = [w for w in words if w not in stop]

        # Find seed nodes
        seed_nodes: list[str] = []
        for concept in concepts:
            resolved = self._resolve_concept(concept)
            seed_nodes.extend(resolved)

        seed_nodes = list(set(seed_nodes))[:5]

        if not seed_nodes:
            return []

        # BFS traversal up to N hops
        visited: dict[str, int] = {}  # node_id → distance
        queue: list[tuple[str, int]] = [(n, 0) for n in seed_nodes]

        for node_id, dist in queue:
            if node_id in visited:
                continue
            visited[node_id] = dist

            if dist < hops:
                for neighbor in self.graph.successors(node_id):
                    if neighbor not in visited:
                        queue.append((neighbor, dist + 1))
                for neighbor in self.graph.predecessors(node_id):
                    if neighbor not in visited:
                        queue.append((neighbor, dist + 1))

        # Score and rank results
        results: list[dict[str, Any]] = []
        for node_id, distance in visited.items():
            node_data = self.graph.nodes[node_id]

            # Score: seed nodes get highest, decreasing by hop distance
            score = 1.0 / (1 + distance)

            # Boost for keyword overlap
            node_keywords = set(node_data.get("keywords", []))
            overlap = len(node_keywords & set(concepts))
            score += overlap * 0.3

            # Boost for degree (more connections = more important)
            degree = self.graph.degree(node_id)
            score += min(degree / 50, 0.2)  # Cap boost

            results.append(
                {
                    "node_id": node_id,
                    "title": node_data.get("title", ""),
                    "category": node_data.get("category", ""),
                    "version": node_data.get("version", ""),
                    "text_preview": node_data.get("text_preview", ""),
                    "distance": distance,
                    "score": round(score, 3),
                    "edge_types": self._get_edge_types(node_id, seed_nodes),
                }
            )

        results.sort(key=lambda x: (-x["score"], x["distance"]))
        return results[:max_results]

    def _get_edge_types(self, node_id: str, seed_nodes: list[str]) -> list[str]:
        """Get edge types connecting this node to seed nodes."""
        types: set[str] = set()
        for seed in seed_nodes:
            if self.graph.has_edge(seed, node_id):
                types.add(self.graph.edges[seed, node_id].get("type", "?"))
            if self.graph.has_edge(node_id, seed):
                types.add(self.graph.edges[node_id, seed].get("type", "?"))
        return list(types)

    def get_neighbors(self, node_id: str, edge_type: str | None = None) -> list[dict[str, Any]]:
        """Get direct neighbors of a node, optionally filtered by edge type."""
        results: list[dict[str, Any]] = []

        for successor in self.graph.successors(node_id):
            edge_data = self.graph.edges[node_id, successor]
            if edge_type and edge_data.get("type") != edge_type:
                continue
            node_data = self.graph.nodes[successor]
            results.append(
                {
                    "node_id": successor,
                    "title": node_data.get("title", ""),
                    "edge_type": edge_data.get("type", "?"),
                    "weight": edge_data.get("weight", 0),
                }
            )

        for predecessor in self.graph.predecessors(node_id):
            edge_data = self.graph.edges[predecessor, node_id]
            if edge_type and edge_data.get("type") != edge_type:
                continue
            node_data = self.graph.nodes[predecessor]
            results.append(
                {
                    "node_id": predecessor,
                    "title": node_data.get("title", ""),
                    "edge_type": f"←{edge_data.get('type', '?')}",
                    "weight": edge_data.get("weight", 0),
                }
            )

        return results

    # ─── Persistence ────────────────────

    def save(self, path: Path | None = None) -> None:
        """Save graph to disk."""
        path = path or GRAPH_FILE
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save graph
        with open(path, "wb") as f:
            pickle.dump(self.graph, f, protocol=pickle.HIGHEST_PROTOCOL)

        # Save indexes
        index = {
            "title_to_id": self._title_to_id,
            "keyword_to_ids": dict(self._keyword_to_ids),
            "entity_to_ids": dict(self._entity_to_ids),
            "stats": self.stats(),
        }
        INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[KG] Saved: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")

    def load(self, path: Path | None = None) -> bool:
        """Load graph from disk. Returns True on success."""
        path = path or GRAPH_FILE
        if not path.exists():
            return False

        try:
            with open(path, "rb") as f:
                self.graph = pickle.load(f)

            # Rebuild indexes
            if INDEX_FILE.exists():
                index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                self._title_to_id = index.get("title_to_id", {})
                self._keyword_to_ids = defaultdict(list, index.get("keyword_to_ids", {}))
                self._entity_to_ids = defaultdict(list, index.get("entity_to_ids", {}))
            else:
                self._rebuild_indexes()

            return True
        except Exception as e:
            print(f"[KG] Load error: {e}")
            return False

    def _rebuild_indexes(self) -> None:
        """Rebuild indexes from graph nodes."""
        self._title_to_id.clear()
        self._keyword_to_ids.clear()
        self._entity_to_ids.clear()

        for node_id, data in self.graph.nodes(data=True):
            title = data.get("title", "")
            self._title_to_id[title.lower()] = node_id

            for kw in data.get("keywords", []):
                self._keyword_to_ids[kw].append(node_id)
            for fn in data.get("functions", []):
                self._entity_to_ids[fn.lower()].append(node_id)
            for cls in data.get("classes", []):
                self._entity_to_ids[cls.lower()].append(node_id)

    # ─── Stats ──────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        if self.graph.number_of_nodes() == 0:
            return {"nodes": 0, "edges": 0}

        edge_type_counts: dict[str, int] = defaultdict(int)
        for _, _, data in self.graph.edges(data=True):
            edge_type_counts[data.get("type", "unknown")] += 1

        category_counts: dict[str, int] = defaultdict(int)
        for _, data in self.graph.nodes(data=True):
            category_counts[data.get("category", "unknown")] += 1

        # Find most connected nodes
        degrees = sorted(
            ((n, self.graph.degree(n)) for n in self.graph.nodes()),
            key=lambda x: -x[1],
        )[:10]

        top_hubs = [
            {"node_id": nid, "title": self.graph.nodes[nid].get("title", "?"), "degree": deg} for nid, deg in degrees
        ]

        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "edge_types": dict(edge_type_counts),
            "categories": dict(category_counts),
            "top_hubs": top_hubs,
            "density": round(nx.density(self.graph), 6),
            "avg_degree": round(sum(d for _, d in self.graph.degree()) / max(1, self.graph.number_of_nodes()), 2),
        }

    def print_stats(self) -> None:
        """Print formatted graph statistics."""
        s = self.stats()
        print(f"\n{'=' * 55}")
        print("  OMNISCIENT Knowledge Graph — Statistics")
        print(f"{'=' * 55}")
        print(f"  Nodes    : {s['nodes']:,}")
        print(f"  Edges    : {s['edges']:,}")
        print(f"  Density  : {s.get('density', 0):.6f}")
        print(f"  Avg Deg  : {s.get('avg_degree', 0):.2f}")
        print("\n  Edge Types:")
        for et, count in sorted(s.get("edge_types", {}).items(), key=lambda x: -x[1]):
            print(f"    {et:20s}: {count:,}")
        print("\n  Categories:")
        for cat, count in sorted(s.get("categories", {}).items(), key=lambda x: -x[1]):
            print(f"    {cat:20s}: {count:,}")
        print("\n  Top 10 Hub Nodes:")
        for hub in s.get("top_hubs", []):
            print(f"    [{hub['degree']:3d}] {hub['title'][:60]}")
        print(f"{'=' * 55}")

    def print_query_results(self, question: str, results: list[dict[str, Any]]) -> None:
        """Print formatted query results."""
        print(f"\n{'─' * 55}")
        print(f'  Query: "{question}"')
        print(f"  Found: {len(results)} related concepts")
        print(f"{'─' * 55}")
        for i, r in enumerate(results, 1):
            dist_icon = "●" if r["distance"] == 0 else "○" * r["distance"]
            edges = ", ".join(r["edge_types"]) if r["edge_types"] else "seed"
            print(f"\n  {i:2d}. [{r['score']:.3f}] {dist_icon} {r['title'][:60]}")
            print(f"      Category: {r['category']}  |  Version: {r['version']}  |  Edges: {edges}")
            if r["text_preview"]:
                preview = r["text_preview"][:120].replace("\n", " ")
                print(f"      {preview}...")


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OMNISCIENT Knowledge Graph")
    parser.add_argument("action", choices=["build", "stats", "query"], help="Action to perform")
    parser.add_argument("query_text", nargs="?", default="", help="Query text (for 'query' action)")
    parser.add_argument("--hops", type=int, default=2, help="Traversal depth")
    parser.add_argument("--max-results", type=int, default=10, help="Max results")
    args = parser.parse_args()

    kg = KnowledgeGraph()

    if args.action == "build":
        chunks_file = CHUNKS_FILE if CHUNKS_FILE.exists() else ROOT / "data" / "raw" / "raw_chunks.json"
        if not chunks_file.exists():
            print(f"[ERROR] Chunks file not found: {chunks_file}")
            return

        print(f"[KG] Loading chunks from: {chunks_file.name}")
        with open(chunks_file, encoding="utf-8") as f:
            chunks = json.load(f)

        kg.build_from_chunks(chunks)
        kg.save()
        kg.print_stats()

    elif args.action == "stats":
        if not kg.load():
            print("[ERROR] No knowledge graph found. Run: python -m src.rag.knowledge_graph build")
            return
        kg.print_stats()

    elif args.action == "query":
        if not args.query_text:
            print('[ERROR] Provide a query: python -m src.rag.knowledge_graph query "list comprehension"')
            return
        if not kg.load():
            print("[ERROR] No knowledge graph found. Run: python -m src.rag.knowledge_graph build")
            return
        results = kg.query(args.query_text, hops=args.hops, max_results=args.max_results)
        kg.print_query_results(args.query_text, results)


if __name__ == "__main__":
    main()
