"""
Pydantic models for Model Battle Arena.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BattleConfig(BaseModel):
    """Configuration for a single model in a battle."""

    provider: str = Field(..., description="Provider ID (e.g. openai, anthropic, ollama)")
    model: str = Field(..., description="Model ID (e.g. gpt-4o, claude-sonnet-4, qwen2.5-coder)")
    label: str | None = Field(default=None, description="Display label (defaults to provider/model)")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32000)
    system_prompt: str | None = Field(default=None, max_length=5000)


class ProviderResult(BaseModel):
    """Result from a single provider in a battle."""

    provider: str
    model: str
    label: str
    content: str = Field(default="", max_length=50000)
    latency_ms: float = Field(default=0.0, ge=0.0)
    token_count_input: int = Field(default=0, ge=0)
    token_count_output: int = Field(default=0, ge=0)
    token_count_total: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    error: str | None = None
    finished_at: datetime | None = None


class BattleRequest(BaseModel):
    """Request to run a model battle."""

    prompt: str = Field(..., min_length=1, max_length=10000)
    providers: list[BattleConfig] = Field(default_factory=list, min_length=1, max_length=10)
    system_prompt: str | None = Field(default=None, max_length=5000)
    auto_select: bool = Field(default=False, description="Auto-select top providers")
    auto_count: int = Field(default=3, ge=2, le=8, description="Number of providers to auto-select")


class BattleResult(BaseModel):
    """Response from a completed battle."""

    prompt: str
    system_prompt: str | None = None
    results: list[ProviderResult] = Field(default_factory=list)
    winner: str | None = None
    total_latency_ms: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class BattleEntry(BaseModel):
    """A saved battle entry for history."""

    id: str = Field(..., description="Unique battle ID")
    prompt: str = Field(..., max_length=200)
    provider_count: int = Field(..., ge=1)
    results: list[ProviderResult] = Field(default_factory=list)
    winner: str | None = None
    created_at: float = Field(default=0.0)


class BattleResponse(BaseModel):
    """API response wrapper."""

    success: bool = True
    battle: BattleResult | None = None
    error: str | None = None
