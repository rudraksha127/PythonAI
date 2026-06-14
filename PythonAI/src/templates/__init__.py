"""
ForgeAI Prompt Templates — Reusable Templates with Variables & Versioning
==========================================================================

Store, manage, and render prompt templates with variables for consistent
LLM interactions.

Features:
  - Template variables with {{variable}} syntax
  - Versioning (auto-increment on save)
  - Categories for organization
  - Template inheritance (extends)
  - JSON CRUD API support

Usage:
    from src.templates import TemplateManager, PromptTemplate

    manager = TemplateManager()
    tmpl = manager.create(
        name="code-review",
        content="Review this {{language}} code:\n```\n{{code}}\n```",
        variables=["language", "code"],
    )
    rendered = tmpl.render(language="Python", code="print('hello')")
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any


# ═══════════════════════════════════════
# Data Models
# ═══════════════════════════════════════


@dataclass
class PromptTemplate:
    """A single prompt template with metadata."""

    id: str
    name: str
    content: str
    description: str = ""
    category: str = "general"
    variables: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    extends: str | None = None  # Template ID to inherit from
    is_active: bool = True

    def render(self, **kwargs: str) -> str:
        """Render the template with variable substitutions.

        Args:
            **kwargs: Variable name to value mapping.

        Returns:
            Rendered template string with {{variable}} placeholders replaced.

        Raises:
            ValueError: If required variables are missing.
        """
        result = self.content

        # Check for missing required variables
        for var in self.variables:
            if var not in kwargs:
                raise ValueError(
                    f"Missing required variable '{{{var}}}' for template '{self.name}'. "
                    f"Required: {self.variables}"
                )

        # Replace {{variable}} with values
        def _replace(match: re.Match) -> str:
            key = match.group(1).strip()
            return str(kwargs.get(key, match.group(0)))

        result = re.sub(r"\{\{(\w+)\}\}", _replace, result)

        return result

    def get_variables_from_content(self) -> list[str]:
        """Extract variable names from template content."""
        return re.findall(r"\{\{(\w+)\}\}", self.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "description": self.description,
            "category": self.category,
            "variables": self.variables,
            "tags": self.tags,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "extends": self.extends,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptTemplate:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            content=data["content"],
            description=data.get("description", ""),
            category=data.get("category", "general"),
            variables=data.get("variables", []),
            tags=data.get("tags", []),
            version=data.get("version", 1),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            extends=data.get("extends"),
            is_active=data.get("is_active", True),
        )


# ═══════════════════════════════════════
# Template Manager
# ═══════════════════════════════════════


class TemplateManager:
    """Manages prompt templates with persistence and versioning."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._lock = Lock()
        self._templates: dict[str, PromptTemplate] = {}
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".forgeai" / "templates"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    # ─── CRUD ─────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        content: str,
        description: str = "",
        category: str = "general",
        variables: list[str] | None = None,
        tags: list[str] | None = None,
        extends: str | None = None,
    ) -> PromptTemplate:
        """Create a new prompt template."""
        template = PromptTemplate(
            id=str(uuid.uuid4()),
            name=name,
            content=content,
            description=description,
            category=category,
            variables=variables or self._extract_variables(content),
            tags=tags or [],
            version=1,
            created_at=time.time(),
            updated_at=time.time(),
            extends=extends,
            is_active=True,
        )

        with self._lock:
            self._templates[template.id] = template
            self._save()

        return template

    def get(self, template_id: str) -> PromptTemplate | None:
        """Get a template by ID."""
        with self._lock:
            return self._templates.get(template_id)

    def get_by_name(self, name: str) -> PromptTemplate | None:
        """Get a template by name (first match)."""
        with self._lock:
            for tmpl in self._templates.values():
                if tmpl.name == name and tmpl.is_active:
                    return tmpl
        return None

    def update(
        self,
        template_id: str,
        content: str | None = None,
        description: str | None = None,
        category: str | None = None,
        variables: list[str] | None = None,
        tags: list[str] | None = None,
        name: str | None = None,
    ) -> PromptTemplate | None:
        """Update an existing template. Auto-increments version."""
        with self._lock:
            tmpl = self._templates.get(template_id)
            if tmpl is None:
                return None

            if name is not None:
                tmpl.name = name
            if content is not None:
                tmpl.content = content
                tmpl.variables = variables or self._extract_variables(content)
            if description is not None:
                tmpl.description = description
            if category is not None:
                tmpl.category = category
            if variables is not None:
                tmpl.variables = variables
            if tags is not None:
                tmpl.tags = tags

            tmpl.version += 1
            tmpl.updated_at = time.time()
            self._save()

        return tmpl

    def delete(self, template_id: str) -> bool:
        """Soft-delete a template (sets is_active=False)."""
        with self._lock:
            tmpl = self._templates.get(template_id)
            if tmpl is None:
                return False
            tmpl.is_active = False
            tmpl.updated_at = time.time()
            self._save()
        return True

    def hard_delete(self, template_id: str) -> bool:
        """Permanently delete a template."""
        with self._lock:
            if template_id not in self._templates:
                return False
            del self._templates[template_id]
            self._save()
        return True

    def list(
        self,
        category: str | None = None,
        tag: str | None = None,
        include_inactive: bool = False,
    ) -> list[PromptTemplate]:
        """List templates with optional filtering."""
        with self._lock:
            results = []
            for tmpl in self._templates.values():
                if not include_inactive and not tmpl.is_active:
                    continue
                if category and tmpl.category != category:
                    continue
                if tag and tag not in tmpl.tags:
                    continue
                results.append(tmpl)
            return sorted(results, key=lambda t: t.updated_at, reverse=True)

    def render(self, template_id_or_name: str, **kwargs: str) -> str:
        """Render a template by ID or name with variables."""
        tmpl = self.get(template_id_or_name) or self.get_by_name(template_id_or_name)
        if tmpl is None:
            raise ValueError(f"Template not found: '{template_id_or_name}'")

        # Handle inheritance
        if tmpl.extends:
            parent = self.get(tmpl.extends)
            if parent:
                parent_content = parent.render(**kwargs)
                # Merge: parent content as base, child content overrides sections
                merged = tmpl.content.replace("{{parent}}", parent_content)
                return merged

        return tmpl.render(**kwargs)

    def duplicate(self, template_id: str, new_name: str | None = None) -> PromptTemplate | None:
        """Duplicate a template."""
        with self._lock:
            original = self._templates.get(template_id)
            if original is None:
                return None

            duplicate = PromptTemplate(
                id=str(uuid.uuid4()),
                name=new_name or f"{original.name} (copy)",
                content=original.content,
                description=original.description,
                category=original.category,
                variables=original.variables.copy(),
                tags=original.tags.copy(),
                version=1,
                created_at=time.time(),
                updated_at=time.time(),
                extends=original.extends,
                is_active=True,
            )
            self._templates[duplicate.id] = duplicate
            self._save()

        return duplicate

    # ─── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get template statistics."""
        with self._lock:
            total = len(self._templates)
            active = sum(1 for t in self._templates.values() if t.is_active)
            categories: dict[str, int] = {}
            for t in self._templates.values():
                categories[t.category] = categories.get(t.category, 0) + 1

            return {
                "total_templates": total,
                "active_templates": active,
                "inactive_templates": total - active,
                "categories": categories,
            }

    # ─── Persistence ──────────────────────────────────────────────

    def _save(self) -> None:
        """Persist templates to disk."""
        data = {
            "templates": [t.to_dict() for t in self._templates.values()],
            "updated_at": time.time(),
        }
        path = self._data_dir / "templates.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load templates from disk."""
        path = self._data_dir / "templates.json"
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for tmpl_data in data.get("templates", []):
                tmpl = PromptTemplate.from_dict(tmpl_data)
                self._templates[tmpl.id] = tmpl
        except (json.JSONDecodeError, KeyError):
            pass

    # ─── Seed Default Templates ───────────────────────────────────

    def seed_defaults(self) -> int:
        """Create default templates if none exist. Returns count created."""
        if self._templates:
            return 0

        defaults = [
            {
                "name": "code-review",
                "content": (
                    "Review the following {{language}} code. Provide feedback on:\n"
                    "1. Code quality and readability\n"
                    "2. Potential bugs and edge cases\n"
                    "3. Performance considerations\n"
                    "4. Security concerns\n"
                    "5. Best practices\n\n"
                    "```{{language}}\n{{code}}\n```\n\n"
                    "Focus on critical issues first."
                ),
                "description": "Standard code review prompt",
                "category": "review",
                "tags": ["review", "code-quality"],
            },
            {
                "name": "rag-search",
                "content": (
                    "Based on the following context, answer the question.\n\n"
                    "Context:\n{{context}}\n\n"
                    "Question: {{query}}\n\n"
                    "Answer concisely and cite relevant sources."
                ),
                "description": "RAG search prompt with context",
                "category": "rag",
                "tags": ["rag", "search"],
            },
            {
                "name": "commit-message",
                "content": (
                    "Generate a concise git commit message for the following changes:\n\n"
                    "{{diff}}\n\n"
                    "Format: type(scope): description\n\n"
                    "Types: feat, fix, chore, docs, refactor, test, style"
                ),
                "description": "Git commit message generator",
                "category": "git",
                "tags": ["git", "commit"],
            },
            {
                "name": "explain-code",
                "content": (
                    "Explain the following {{language}} code in simple terms:\n\n"
                    "```{{language}}\n{{code}}\n```\n\n"
                    "Describe what it does, how it works, and any important details."
                ),
                "description": "Code explanation prompt",
                "category": "learning",
                "tags": ["explain", "learning"],
            },
            {
                "name": "debug-error",
                "content": (
                    "I'm getting this error in my {{language}} code:\n\n"
                    "Error: {{error}}\n\n"
                    "Code:\n```{{language}}\n{{code}}\n```\n\n"
                    "What's causing this and how do I fix it?"
                ),
                "description": "Debug error prompt",
                "category": "debugging",
                "tags": ["debug", "error"],
            },
        ]

        count = 0
        for data in defaults:
            self.create(**data)
            count += 1

        return count

    # ─── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_variables(content: str) -> list[str]:
        """Extract {{variable}} names from content."""
        return list(dict.fromkeys(re.findall(r"\{\{(\w+)\}\}", content)))


# ═══════════════════════════════════════
# Global Singleton
# ═══════════════════════════════════════

_manager: TemplateManager | None = None


def get_template_manager(data_dir: str | Path | None = None) -> TemplateManager:
    """Get or create the global template manager."""
    global _manager
    if _manager is None:
        _manager = TemplateManager(data_dir=data_dir)
        _manager.seed_defaults()
    return _manager


__all__ = [
    "PromptTemplate",
    "TemplateManager",
    "get_template_manager",
]
