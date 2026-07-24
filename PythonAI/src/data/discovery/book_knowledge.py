"""
BOOK & EDUCATIONAL RESOURCE KNOWLEDGE BASE
==========================================
Systematic knowledge base that collects and indexes knowledge from:

1. Python programming books (classics like "Fluent Python", "Python Cookbook")
2. Free programming textbooks and educational resources
3. Official Python documentation and tutorials
4. Online courses and lecture notes
5. Interactive tutorials and coding platforms
6. Technical blog posts and engineering blogs

This creates a rich, structured knowledge source that complements
the research paper knowledge base for the RAG system.

Usage:
    from src.data.discovery.book_knowledge import BookKnowledgeBase
    bkb = BookKnowledgeBase()
    bkb.collect_knowledge()
"""

from __future__ import annotations

import json
import re
import time
import hashlib
import urllib.request
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import defaultdict

# ── Paths ───────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
KNOWLEDGE_DIR = ROOT / "data" / "research_knowledge"
BOOKS_INDEX_FILE = KNOWLEDGE_DIR / "books_index.json"
BOOK_CHUNKS_FILE = KNOWLEDGE_DIR / "book_chunks.json"
TUTORIAL_CACHE_FILE = KNOWLEDGE_DIR / "tutorial_cache.json"


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class BookKnowledge:
    """Structured knowledge from a book or educational resource."""

    # Identity
    book_id: str
    title: str
    author: str = ""
    publisher: str = ""
    year: int = 0
    isbn: str = ""

    # Classification
    topics: list[str] = field(default_factory=list)
    skill_level: str = "intermediate"  # beginner, intermediate, advanced
    category: str = "python"  # python, ml, ds, algorithms, etc.

    # Content
    description: str = ""
    table_of_contents: list[str] = field(default_factory=list)
    key_concepts: list[str] = field(default_factory=list)
    code_examples: list[str] = field(default_factory=list)

    # Quality
    rating: float = 0.0  # Community rating 0-5
    relevance_score: float = 0.5
    downloads: int = 0

    # Source
    source_url: str = ""
    source_type: str = "book"  # book, tutorial, course, blog, doc
    license: str = ""

    # Tracking
    ingested_at: str = ""
    last_updated: str = ""

    @property
    def as_chunk_dict(self) -> dict[str, Any]:
        """Convert to chunk dict for RAG ingestion."""
        text_parts = [
            f"Title: {self.title}",
            f"Author: {self.author}",
            f"Publisher: {self.publisher}" if self.publisher else "",
            f"Year: {self.year}" if self.year else "",
            f"Level: {self.skill_level}",
            f"Topics: {', '.join(self.topics[:10])}",
            "",
            "DESCRIPTION:",
            self.description,
        ]

        if self.key_concepts:
            text_parts.append("")
            text_parts.append("KEY CONCEPTS:")
            for c in self.key_concepts[:15]:
                text_parts.append(f"  • {c}")

        if self.code_examples:
            text_parts.append("")
            text_parts.append("CODE EXAMPLES:")
            for c in self.code_examples[:3]:
                text_parts.append(f"  ```python\n{c[:500]}\n  ```")

        text = "\n".join(text_parts)

        return {
            "id": f"book_{self.book_id}",
            "title": self.title[:200],
            "text": text[:4000],
            "type": f"book_{self.source_type}",
            "category": f"education_{self.category}",
            "version": str(self.year) if self.year else "",
            "codes": self.code_examples[:3],
            "source": self.source_url,
        }


@dataclass
class TutorialResource:
    """An online tutorial or educational resource."""

    resource_id: str
    title: str
    url: str
    description: str = ""
    platform: str = ""  # RealPython, GeeksforGeeks, etc.
    topics: list[str] = field(default_factory=list)
    difficulty: str = "intermediate"
    content_snippet: str = ""
    is_free: bool = True


# ── Knowledge Base ──────────────────────────────────────────────────


# Comprehensive list of essential Python and AI/ML books
ESSENTIAL_BOOKS: list[dict[str, Any]] = [
    # Python Core
    {
        "title": "Fluent Python",
        "author": "Luciano Ramalho",
        "publisher": "O'Reilly Media",
        "year": 2022,
        "isbn": "978-1492056355",
        "topics": ["Python", "idiomatic Python", "data structures", "OOP", "metaclasses", "concurrency"],
        "skill_level": "advanced",
        "description": (
            "Fluent Python is a comprehensive guide to writing idiomatic Python code. "
            "It covers data structures, functions, objects, metaclasses, concurrency, "
            "and how Python really works under the hood. Essential for any serious Python developer."
        ),
        "key_concepts": [
            "Python data model and special methods",
            "Sequence types and slicing",
            "Dictionary and set internals",
            "Function decorators and closures",
            "Descriptor protocol and properties",
            "Metaclasses and class creation",
            "Concurrency with asyncio",
            "Context managers and contextlib",
            "Abstract base classes (ABCs)",
            "Operator overloading",
        ],
        "rating": 4.8,
        "source_type": "book",
    },
    {
        "title": "Python Cookbook",
        "author": "David Beazley, Brian K. Jones",
        "publisher": "O'Reilly Media",
        "year": 2013,
        "isbn": "978-1449340377",
        "topics": ["Python", "recipes", "data processing", "metaprogramming", "networking"],
        "skill_level": "intermediate",
        "description": (
            "Python Cookbook contains hundreds of practical recipes for solving "
            "everyday programming problems. Covers data structures, strings, text, "
            "functions, classes, metaprogramming, networking, and concurrency."
        ),
        "key_concepts": [
            "Text processing and regular expressions",
            "Data structures and algorithms",
            "Functions and functional programming",
            "Classes and OOP patterns",
            "Metaprogramming techniques",
            "Modules and packages",
            "Iterators and generators",
            "File I/O and serialization",
        ],
        "rating": 4.7,
        "source_type": "book",
    },
    {
        "title": "Effective Python",
        "author": "Brett Slatkin",
        "publisher": "Addison-Wesley",
        "year": 2019,
        "isbn": "978-0134853987",
        "topics": ["Python", "best practices", "performance", "style"],
        "skill_level": "intermediate",
        "description": (
            "90 specific ways to write better Python. Each item covers a specific "
            "topic with concrete examples. Covers modern Python 3.8+ features."
        ),
        "key_concepts": [
            "Pythonic thinking and idioms",
            "Functions and comprehensions",
            "Classes and interfaces",
            "Metaclasses and attributes",
            "Concurrency and parallelism",
            "Built-in modules",
            "Testing and debugging",
            "Productionization",
        ],
        "rating": 4.7,
        "source_type": "book",
    },
    {
        "title": "Python for Data Analysis",
        "author": "Wes McKinney",
        "publisher": "O'Reilly Media",
        "year": 2022,
        "isbn": "978-1098104030",
        "topics": ["Python", "pandas", "NumPy", "data analysis", "data science"],
        "skill_level": "intermediate",
        "description": (
            "The definitive guide to data analysis with Python. Covers NumPy, pandas, "
            "data cleaning, transformation, aggregation, and visualization."
        ),
        "key_concepts": [
            "NumPy arrays and vectorized operations",
            "pandas Series and DataFrame",
            "Data cleaning and preparation",
            "Data transformation and aggregation",
            "Time series analysis",
            "Data visualization with matplotlib",
            "Working with relational databases",
        ],
        "rating": 4.6,
        "source_type": "book",
    },
    {
        "title": "Deep Learning with Python",
        "author": "François Chollet",
        "publisher": "Manning",
        "year": 2021,
        "isbn": "978-1617296864",
        "topics": ["deep learning", "Keras", "TensorFlow", "neural networks"],
        "skill_level": "intermediate",
        "description": (
            "The definitive introduction to deep learning using Keras. Covers "
            "neural network fundamentals, computer vision, NLP, generative models, "
            "and best practices for deep learning."
        ),
        "key_concepts": [
            "Neural network fundamentals",
            "Convolutional neural networks",
            "Recurrent neural networks",
            "Attention and transformers",
            "Generative models and GANs",
            "Transfer learning",
            "Model deployment",
            "Hyperparameter tuning",
        ],
        "rating": 4.6,
        "source_type": "book",
    },
    {
        "title": "Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow",
        "author": "Aurélien Géron",
        "publisher": "O'Reilly Media",
        "year": 2022,
        "isbn": "978-1098125974",
        "topics": ["machine learning", "scikit-learn", "TensorFlow", "deep learning"],
        "skill_level": "intermediate",
        "description": (
            "A comprehensive, practical guide to machine learning. Covers classical ML "
            "algorithms, neural networks, training pipelines, and deployment. "
            "Includes hands-on exercises and real-world projects."
        ),
        "key_concepts": [
            "Linear and logistic regression",
            "Support vector machines",
            "Decision trees and random forests",
            "Ensemble methods",
            "Dimensionality reduction",
            "Neural network architecture",
            "Training deep neural networks",
            "Custom models with TensorFlow",
            "Deploying ML models",
        ],
        "rating": 4.7,
        "source_type": "book",
    },
    {
        "title": "Designing Data-Intensive Applications",
        "author": "Martin Kleppmann",
        "publisher": "O'Reilly Media",
        "year": 2017,
        "isbn": "978-1449373320",
        "topics": ["distributed systems", "databases", "streaming", "consistency"],
        "skill_level": "advanced",
        "description": (
            "The definitive guide to designing robust, scalable data systems. "
            "Covers databases, stream processing, batch processing, replication, "
            "partitioning, transactions, and distributed systems theory."
        ),
        "key_concepts": [
            "Reliability, scalability, maintainability",
            "Data models and query languages",
            "Storage and retrieval",
            "Encoding and evolution",
            "Replication strategies",
            "Partitioning techniques",
            "Transactions and concurrency",
            "Consistency and consensus",
            "Batch and stream processing",
        ],
        "rating": 4.8,
        "source_type": "book",
    },
    {
        "title": "The Pragmatic Programmer",
        "author": "Andrew Hunt, David Thomas",
        "publisher": "Addison-Wesley",
        "year": 2019,
        "isbn": "978-0135957059",
        "topics": ["software engineering", "best practices", "craftsmanship"],
        "skill_level": "intermediate",
        "description": (
            "Timeless software engineering wisdom. Covers practical approaches to "
            "software development including DRY, orthogonality, reversibility, "
            "prototyping, estimation, and team collaboration."
        ),
        "key_concepts": [
            "DRY principle and orthogonality",
            "Tracer bullets and prototyping",
            "Domain-specific languages",
            "Version control and automation",
            "Testing and debugging strategies",
            "Concurrency and parallelism",
            "Estimation techniques",
            "Agile and team collaboration",
        ],
        "rating": 4.7,
        "source_type": "book",
    },
    {
        "title": "Clean Code",
        "author": "Robert C. Martin",
        "publisher": "Prentice Hall",
        "year": 2008,
        "isbn": "978-0132350884",
        "topics": ["software engineering", "clean code", "refactoring", "TDD"],
        "skill_level": "intermediate",
        "description": (
            "The definitive guide to writing clean, maintainable code. Covers naming "
            "conventions, functions, comments, formatting, error handling, and "
            "test-driven development practices."
        ),
        "key_concepts": [
            "Meaningful naming conventions",
            "Function design and composition",
            "Comments and documentation",
            "Code formatting and style",
            "Error handling patterns",
            "Unit testing and TDD",
            "Class design principles",
            "Refactoring techniques",
        ],
        "rating": 4.5,
        "source_type": "book",
    },
    {
        "title": "Introduction to Algorithms (CLRS)",
        "author": "Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein",
        "publisher": "MIT Press",
        "year": 2022,
        "isbn": "978-0262046305",
        "topics": ["algorithms", "data structures", "complexity theory"],
        "skill_level": "advanced",
        "description": (
            "The definitive textbook on algorithms. Covers sorting, graph algorithms, "
            "dynamic programming, greedy algorithms, NP-completeness, and more. "
            "Essential reference for any serious programmer."
        ),
        "key_concepts": [
            "Analysis of algorithms and Big-O notation",
            "Sorting and order statistics",
            "Hash tables and data structures",
            "Binary search trees and balanced trees",
            "Graph algorithms and traversal",
            "Dynamic programming techniques",
            "Greedy algorithms",
            "NP-completeness and approximation",
            "String matching algorithms",
        ],
        "rating": 4.7,
        "source_type": "book",
    },
    {
        "title": "Structure and Interpretation of Computer Programs (SICP)",
        "author": "Harold Abelson, Gerald Jay Sussman",
        "publisher": "MIT Press",
        "year": 1996,
        "isbn": "978-0262510875",
        "topics": ["computer science", "programming languages", "abstraction"],
        "skill_level": "advanced",
        "description": (
            "A classic computer science text that teaches fundamental principles "
            "of programming through building abstractions, metacircular evaluators, "
            "and exploring the nature of computation itself."
        ),
        "key_concepts": [
            "Building abstractions with procedures",
            "Data abstraction and hierarchical data",
            "Symbolic data and quotation",
            "Metacircular evaluator",
            "Register machines and compilation",
            "Streams and lazy evaluation",
            "Object-oriented programming principles",
            "Non-deterministic computing",
        ],
        "rating": 4.6,
        "source_type": "book",
    },
    {
        "title": "The Art of Computer Programming (TAOCP)",
        "author": "Donald E. Knuth",
        "publisher": "Addison-Wesley",
        "year": 2011,
        "isbn": "978-0201896831",
        "topics": ["algorithms", "computer science", "mathematics"],
        "skill_level": "advanced",
        "description": (
            "Donald Knuth's monumental reference work on algorithms and computer programming. "
            "Covers fundamental algorithms, seminumerical algorithms, searching and sorting, "
            "and combinatorial algorithms with rigorous mathematical analysis."
        ),
        "key_concepts": [
            "Fundamental algorithms and data structures",
            "Information structures and indexing",
            "Random numbers and generation",
            "Arithmetic and number theory",
            "Searching techniques",
            "Sorting methods and analysis",
            "Combinatorial algorithms",
            "Mathematical analysis of algorithms",
        ],
        "rating": 4.8,
        "source_type": "book",
    },
]

# Python and AI/ML tutorial resources (curated, high-quality)
ESSENTIAL_TUTORIALS: list[dict[str, Any]] = [
    {
        "title": "Python Official Tutorial",
        "url": "https://docs.python.org/3/tutorial/",
        "platform": "Python.org",
        "topics": ["Python", "basics", "standard library"],
        "difficulty": "beginner",
        "description": "The official Python tutorial covering language fundamentals, control flow, data structures, modules, input/output, errors, classes, and standard library.",
    },
    {
        "title": "Real Python Tutorials",
        "url": "https://realpython.com/",
        "platform": "Real Python",
        "topics": ["Python", "web development", "data science", "testing"],
        "difficulty": "intermediate",
        "description": "In-depth Python tutorials covering web frameworks (Django, Flask), data science, testing, performance optimization, and modern Python features.",
    },
    {
        "title": "Python Module of the Week (PyMOTW)",
        "url": "https://pymotw.com/3/",
        "platform": "PyMOTW",
        "topics": ["Python", "standard library", "modules"],
        "difficulty": "intermediate",
        "description": "Comprehensive tour of Python's standard library with practical examples for each module.",
    },
    {
        "title": "FastAI Practical Deep Learning",
        "url": "https://course.fast.ai/",
        "platform": "fast.ai",
        "topics": ["deep learning", "neural networks", "Python"],
        "difficulty": "intermediate",
        "description": "A top-down approach to deep learning. Start by training state-of-the-art models and then dive into the underlying theory.",
    },
    {
        "title": "ML Course by Andrew Ng (Stanford CS229)",
        "url": "https://cs229.stanford.edu/",
        "platform": "Stanford",
        "topics": ["machine learning", "statistics", "algorithms"],
        "difficulty": "advanced",
        "description": "Stanford's legendary machine learning course covering supervised learning, unsupervised learning, learning theory, reinforcement learning, and practical ML engineering.",
    },
    {
        "title": "Full Stack Deep Learning",
        "url": "https://fullstackdeeplearning.com/",
        "platform": "FullStackDL",
        "topics": ["deep learning", "MLOps", "deployment", "engineering"],
        "difficulty": "intermediate",
        "description": "Comprehensive guide to production ML: project setup, data management, training infrastructure, deployment, monitoring, and team management.",
    },
]


class BookKnowledgeBase:
    """
    Knowledge base of programming books, tutorials, and educational resources.

    Provides structured, curated knowledge that complements research papers
    for the RAG system. Focuses on established, high-quality resources.
    """

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else KNOWLEDGE_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._books: dict[str, BookKnowledge] = {}
        self._load_index()
        self._initialize_from_curated()

    # ── Persistence ───────────────────────────────────────────

    def _load_index(self) -> None:
        """Load previously collected book knowledge."""
        if BOOKS_INDEX_FILE.exists():
            try:
                data = json.loads(BOOKS_INDEX_FILE.read_text(encoding="utf-8"))
                for item in data.get("books", []):
                    book = BookKnowledge(**item)
                    self._books[book.book_id] = book
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    def _save_index(self) -> None:
        """Save book knowledge to disk."""
        books_data = [asdict(b) for b in self._books.values()]
        BOOKS_INDEX_FILE.write_text(
            json.dumps({"books": books_data, "count": len(books_data)}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_all_books(self) -> list[BookKnowledge]:
        """Get all books and resources. Public accessor for KnowledgeIntelligence."""
        return list(self._books.values())

    def _initialize_from_curated(self) -> None:
        """Initialize knowledge base with curated book and tutorial data."""
        now = datetime.now(timezone.utc).isoformat()
        added = 0

        for book_data in ESSENTIAL_BOOKS:
            book_id = self._make_book_id(book_data["title"])
            if book_id not in self._books:
                book = BookKnowledge(
                    book_id=book_id,
                    title=book_data["title"],
                    author=book_data.get("author", ""),
                    publisher=book_data.get("publisher", ""),
                    year=book_data.get("year", 0),
                    isbn=book_data.get("isbn", ""),
                    topics=book_data.get("topics", []),
                    skill_level=book_data.get("skill_level", "intermediate"),
                    description=book_data.get("description", ""),
                    key_concepts=book_data.get("key_concepts", []),
                    code_examples=book_data.get("code_examples", []),
                    rating=book_data.get("rating", 0.0),
                    relevance_score=0.7 + (book_data.get("rating", 0) / 10),
                    source_type=book_data.get("source_type", "book"),
                    ingested_at=now,
                    last_updated=now,
                )
                self._books[book_id] = book
                added += 1

        # Add tutorials
        for tut_data in ESSENTIAL_TUTORIALS:
            tut_id = self._make_book_id(tut_data["title"])
            if tut_id not in self._books:
                tutorial = BookKnowledge(
                    book_id=tut_id,
                    title=tut_data["title"],
                    author=tut_data.get("platform", ""),
                    topics=tut_data.get("topics", []),
                    skill_level=tut_data.get("difficulty", "intermediate"),
                    description=tut_data.get("description", ""),
                    source_url=tut_data.get("url", ""),
                    source_type="tutorial",
                    relevance_score=0.6,
                    ingested_at=now,
                    last_updated=now,
                )
                self._books[tut_id] = tutorial
                added += 1

        if added > 0:
            self._save_index()

    @staticmethod
    def _make_book_id(title: str) -> str:
        """Create a stable book ID from title."""
        clean = re.sub(r"[^a-z0-9]", "_", title.lower().strip())
        clean = re.sub(r"_+", "_", clean)
        return clean[:40]

    # ── Collection ────────────────────────────────────────────

    def crawl_free_sources(self) -> list[BookKnowledge]:
        """
        Run all free-book crawlers and return newly discovered books.

        Sources:
          - GitHub: EbookFoundation/free-programming-books list
          - Google Books API: free ebooks in programming/cs categories

        Returns:
            List of newly discovered BookKnowledge objects (not already in index).
        """
        newly_discovered: list[BookKnowledge] = []
        seen_titles: set[str] = {b.title.lower().strip() for b in self._books.values()}

        # Crawler 1: GitHub free-programming-books list
        print("  [Crawler] GitHub: EbookFoundation/free-programming-books...")
        try:
            gh_books = self._crawl_github_free_books()
            for book in gh_books:
                if book.title.lower().strip() not in seen_titles:
                    self._books[book.book_id] = book
                    newly_discovered.append(book)
                    seen_titles.add(book.title.lower().strip())
            print(f"    -> {len(gh_books)} found, {sum(1 for b in gh_books if b.book_id in self._books)} new")
        except Exception as e:
            print(f"    [ERROR] GitHub crawl failed: {e}")

        # Crawler 2: Google Books API free ebooks
        print("  [Crawler] Google Books API: free programming ebooks...")
        try:
            gb_books = self._crawl_google_books()
            for book in gb_books:
                if book.title.lower().strip() not in seen_titles:
                    self._books[book.book_id] = book
                    newly_discovered.append(book)
                    seen_titles.add(book.title.lower().strip())
            print(f"    -> {len(gb_books)} found, {sum(1 for b in gb_books if b.book_id in self._books)} new")
        except Exception as e:
            print(f"    [ERROR] Google Books crawl failed: {e}")

        # Save updated index
        if newly_discovered:
            self._save_index()
            print(f"  [OK] {len(newly_discovered)} new resources indexed")
        else:
            print("  [INFO] No new resources discovered")

        return newly_discovered

    def _crawl_github_free_books(self) -> list[BookKnowledge]:
        """
        Crawl the EbookFoundation/free-programming-books list on GitHub.

        Fetches the main markdown file and parses book entries for
        programming, AI/ML, and computer science categories.
        """
        import urllib.request
        import ssl
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        now = datetime.now(timezone.utc).isoformat()
        books: list[BookKnowledge] = []

        # URLs for the free-programming-books lists
        list_urls = [
            ("https://raw.githubusercontent.com/EbookFoundation/free-programming-books/main/books/free-programming-books-langs.md", "programming"),
            ("https://raw.githubusercontent.com/EbookFoundation/free-programming-books/main/books/free-programming-books-subjects.md", "subject"),
        ]

        # Topics we care about (case-insensitive)
        relevant_topics = {
            "python", "machine learning", "deep learning", "artificial intelligence",
            "data science", "computer science", "algorithms", "data structures",
            "javascript", "typescript", "rust", "go", "java", "c++", "c ",
            "julia", "r programming", "sql", "database", "linux", "git",
            "docker", "kubernetes", "neural networks", "nlp", "computer vision",
        }

        for url, list_type in list_urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "PythonAI/2.0"})
                with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                    content = resp.read().decode("utf-8")
            except Exception as exc:
                print(f"    [WARN] Could not fetch {url.split('/')[-1]}: {exc}")
                continue

            # Parse markdown sections
            current_category = ""
            for line in content.split("\n"):
                # Detect category headers (### Category Name)
                header_match = re.match(r"^###\s+(.+)", line)
                if header_match:
                    current_category = header_match.group(1).lower().strip()
                    continue

                # Skip non-relevant categories
                if current_category and not any(t in current_category for t in relevant_topics):
                    continue

                # Parse book entry: * [Title](url) - Description (description optional)
                entry_match = re.match(r"^\s*[-*]\s+\[([^\]]+)\]\(([^)]+)\)(?:\s*-\s*(.+))?", line)
                if entry_match:
                    title = entry_match.group(1).strip()
                    url = entry_match.group(2).strip()
                    desc = (entry_match.group(3) or "").strip()[:300]

                    book_id = self._make_book_id(title)
                    if book_id not in self._books:
                        books.append(BookKnowledge(
                            book_id=book_id,
                            title=title[:200],
                            description=desc,
                            source_url=url,
                            source_type="free_book",
                            topics=[current_category] if current_category else ["programming"],
                            skill_level="intermediate",
                            relevance_score=0.5,
                            ingested_at=now,
                            last_updated=now,
                        ))

        return books

    def _crawl_google_books(self) -> list[BookKnowledge]:
        """
        Search Google Books API for free programming ebooks.

        Uses the public API (no key needed at low volume) and
        filters for free ebooks only.
        """
        import urllib.request
        import urllib.parse
        import json
        import ssl
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        now = datetime.now(timezone.utc).isoformat()
        books: list[BookKnowledge] = []

        # Search queries for free programming ebooks
        search_queries = [
            "python programming",
            "machine learning",
            "deep learning",
            "data science",
            "algorithms",
            "computer science",
            "javascript",
            "rust programming",
            "artificial intelligence",
        ]

        for query in search_queries:
            time.sleep(0.5)  # Respect Google API rate limits
            try:
                params = urllib.parse.urlencode({
                    "q": query,
                    "filter": "free-ebooks",
                    "maxResults": 10,
                    "printType": "books",
                })
                url = f"https://www.googleapis.com/books/v1/volumes?{params}"
                req = urllib.request.Request(url, headers={"User-Agent": "PythonAI/2.0"})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                for item in data.get("items", []):
                    vol = item.get("volumeInfo", {})
                    title = vol.get("title", "")[:200]
                    if not title:
                        continue

                    authors = ", ".join(vol.get("authors", ["Unknown"]))
                    desc = (vol.get("description", "") or "")[:300]
                    isbn = ""
                    for id_info in vol.get("industryIdentifiers", []):
                        if id_info.get("type") in ("ISBN_13", "ISBN_10"):
                            isbn = id_info.get("identifier", "")
                            break

                    publisher = vol.get("publisher", "")
                    year = 0
                    pub_date = vol.get("publishedDate", "")
                    if pub_date:
                        year_match = re.match(r"(\d{4})", pub_date)
                        if year_match:
                            year = int(year_match.group(1))

                    categories = [c.lower() for c in vol.get("categories", ["programming"])]
                    page_count = vol.get("pageCount", 0)
                    info_link = vol.get("infoLink", "")

                    book_id = self._make_book_id(title)
                    if book_id not in self._books:
                        books.append(BookKnowledge(
                            book_id=book_id,
                            title=title[:200],
                            author=authors[:200],
                            publisher=publisher[:100],
                            year=year,
                            isbn=isbn,
                            topics=categories[:5],
                            description=desc,
                            source_url=info_link,
                            source_type="free_ebook",
                            skill_level="intermediate",
                            relevance_score=0.5,
                            ingested_at=now,
                            last_updated=now,
                        ))

            except Exception as exc:
                print(f"    [WARN] Google Books query '{query}' failed: {exc}")
                continue

        return books

    def scan_free_resources(self) -> list[BookKnowledge]:
        """
        Discover free programming resources from the web.

        Returns the currently indexed books (including curated + crawled).
        """
        return list(self._books.values())

    def generate_knowledge_chunks(self) -> list[dict[str, Any]]:
        """Generate RAG-compatible chunks from book knowledge."""
        chunks: list[dict[str, Any]] = []

        for book in self._books.values():
            if book.relevance_score < 0.4:
                continue

            chunk = book.as_chunk_dict
            chunks.append(chunk)

            # Also create individual concept chunks
            for i, concept in enumerate(book.key_concepts[:10]):
                concept_chunk = {
                    "id": f"concept_{book.book_id}_{i}",
                    "title": f"{concept} — from {book.title}",
                    "text": (
                        f"Concept: {concept}\n"
                        f"Source: {book.title} by {book.author}\n"
                        f"Level: {book.skill_level}\n"
                        f"Context: This is a key concept from the book '{book.title}' "
                        f"which covers {book.topics[0] if book.topics else 'programming'}. "
                        f"The concept '{concept}' is fundamental to understanding "
                        f"{'Python' if 'python' in str(book.topics).lower() else 'programming'} "
                        f"at the {book.skill_level} level."
                    ),
                    "type": "book_concept",
                    "category": f"education_{book.source_type}",
                    "version": str(book.year) if book.year else "",
                }
                chunks.append(concept_chunk)

        return chunks

    def save_knowledge_chunks(self) -> Path:
        """Save book knowledge chunks for RAG ingestion."""
        chunks = self.generate_knowledge_chunks()
        BOOK_CHUNKS_FILE.write_text(
            json.dumps(chunks, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n[BOOKS] Saved {len(chunks)} book knowledge chunks to {BOOK_CHUNKS_FILE}")
        return BOOK_CHUNKS_FILE

    def search(self, query: str, max_results: int = 10) -> list[BookKnowledge]:
        """Search book knowledge by topic or keyword."""
        query_lower = query.lower()
        # Tokenize query into individual words for better matching
        query_words = set(w for w in re.findall(r'[a-zA-Z]+', query_lower) if len(w) > 2)
        scored: list[tuple[BookKnowledge, float]] = []

        for book in self._books.values():
            score = 0.0
            title_lower = book.title.lower()

            # Substring match (full phrase)
            if query_lower in title_lower:
                score += 0.5
            if query_lower in book.description.lower():
                score += 0.2

            # Word-level matches for more flexible search
            text_to_check = (
                title_lower + ' ' +
                ' '.join(t.lower() for t in book.topics) + ' ' +
                ' '.join(c.lower() for c in book.key_concepts) + ' ' +
                book.description.lower()
            )
            word_matches = sum(1 for w in query_words if w in text_to_check)
            if query_words and word_matches > 0:
                score += (word_matches / len(query_words)) * 0.5

            score *= book.relevance_score

            if score > 0:
                scored.append((book, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [b for b, s in scored[:max_results]]

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the book knowledge base."""
        if not self._books:
            return {"total_books": 0}

        types: dict[str, int] = defaultdict(int)
        levels: dict[str, int] = defaultdict(int)
        all_topics: dict[str, int] = defaultdict(int)

        for book in self._books.values():
            types[book.source_type] += 1
            levels[book.skill_level] += 1
            for topic in book.topics:
                all_topics[topic] += 1

        return {
            "total_resources": len(self._books),
            "by_type": dict(types),
            "by_level": dict(levels),
            "top_topics": dict(sorted(all_topics.items(), key=lambda x: x[1], reverse=True)[:15]),
            "total_concepts": sum(len(b.key_concepts) for b in self._books.values()),
        }


def collect_book_knowledge() -> BookKnowledgeBase:
    """Convenience: collect and save book knowledge."""
    bkb = BookKnowledgeBase()
    bkb.scan_free_resources()
    bkb.save_knowledge_chunks()
    return bkb


if __name__ == "__main__":
    bkb = collect_book_knowledge()
    stats = bkb.get_statistics()
    print(json.dumps(stats, indent=2))
