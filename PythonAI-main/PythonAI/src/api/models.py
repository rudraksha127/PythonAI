"""
ForgeAI API Pydantic Schemas & Models
"""
from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field, field_validator

_MAX_QUESTION_LENGTH = 10000
_MAX_HISTORY_LENGTH = 50
_MAX_HISTORY_MSG_LENGTH = 5000


def _sanitize_text(text: str, max_len: int = 10000) -> str:
    """Sanitize input string."""
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) != 127))
    return cleaned[:max_len]


class EventPayload(BaseModel):
    """Event from VS Code extension."""

    event_type: str = Field(..., description="accept, reject, edit, pr_merge, test_pass, test_fail")
    session_id: str
    project_id: str
    file_path: str
    line_number: int = 0
    language: str
    framework: str | None = None
    project_type: str = "general"
    suggestion: str
    suggestion_metadata: dict = Field(default_factory=dict)
    context_before: str = ""
    context_after: str = ""
    full_context: str = ""
    final_code: str | None = None
    edit_distance: float = 0.0
    developer_id: str | None = None

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        valid = {"accept", "reject", "edit", "pr_merge", "test_pass", "test_fail"}
        if v not in valid:
            raise ValueError(f"Invalid event_type. Must be one of: {valid}")
        return v


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    model: str = Field(default="", max_length=100)
    query_expansion: bool = False
    mmr: bool = False
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("question")
    @classmethod
    def _clean_question(cls, v: str) -> str:
        return _sanitize_text(v, _MAX_QUESTION_LENGTH)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    model: str = Field(default="", max_length=100)
    query_expansion: bool = False
    mmr: bool = False
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    history: list[dict[str, Any]] = Field(default_factory=list)
    project_id: str | None = None

    @field_validator("history")
    @classmethod
    def _trim_history(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trimmed = v[-_MAX_HISTORY_LENGTH:]
        for msg in trimmed:
            if isinstance(msg.get("content"), str):
                msg["content"] = _sanitize_text(msg["content"], _MAX_HISTORY_MSG_LENGTH)
        return trimmed


class RAGSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: str
    strategy: str = Field(default="hybrid", description="hybrid, vector, graph, agentic")
    k: int = Field(default=10, ge=1, le=50)


class IndexRequest(BaseModel):
    project_id: str
    repo_path: str
    force_reindex: bool = False


class MemoryAddRequest(BaseModel):
    user_id: str = Field(default="default", max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)


class MemorySearchRequest(BaseModel):
    user_id: str = Field(default="default", max_length=100)
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class DocumentInsertRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=500, description="Text documents to insert")


class IngestRequest(BaseModel):
    directory: str = Field(..., min_length=1, max_length=2000, description="Directory path to scan")
    pattern: str = Field(
        default="**/*.{py,js,ts,jsx,tsx,md,txt,rst,json,yaml,yml}",
        description="Glob pattern for files to include",
    )
    max_files: int = Field(default=200, ge=1, le=5000, description="Maximum files to process")


class LightRAGHealthRequest(BaseModel):
    verbose: bool = Field(default=False, description="Run a full pipeline test (insert + query)")


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    path: str = Field(..., min_length=1, max_length=1000)
    description: str = Field(default="", max_length=1000)
    project_type: str = Field(default="general", max_length=100)
    language: str = Field(default="python", max_length=50)
    framework: str | None = Field(default=None, max_length=50)


class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    description: str
    project_type: str
    language: str
    framework: str | None
    created_at: float
    updated_at: float
    status: str
