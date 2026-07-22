"""
Model Battle Arena — FastAPI Router
=====================================
Endpoints:
  POST /api/battle/run      — Run a model battle
  GET  /api/battle/history   — Battle history
  GET  /api/battle/providers — Available providers
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.battle")

router = APIRouter(prefix="/api/battle", tags=["battle"])


class BattleProviderConfig(BaseModel):
    """Provider config for a battle entry."""
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32000)


class BattleRunRequest(BaseModel):
    """Request to run a model battle."""
    prompt: str = Field(..., min_length=1, max_length=10000)
    system_prompt: str | None = Field(default=None, max_length=5000)
    providers: list[BattleProviderConfig] = Field(default_factory=list)
    auto_select: bool = Field(default=False)
    auto_count: int = Field(default=3, ge=2, le=8)


@router.post("/run")
async def battle_run(body: BattleRunRequest):
    """
    Run a Model Battle — send the same prompt to multiple providers
    and compare responses with latency, token usage, and cost metrics.
    """
    from src.battle import BattleEngine, BattleConfig, BattleRequest as BattleReq

    try:
        engine = BattleEngine()

        configs = [
            BattleConfig(
                provider=p.provider,
                model=p.model,
                label=p.label,
                temperature=p.temperature,
                max_tokens=p.max_tokens,
            )
            for p in body.providers
        ]

        req = BattleReq(
            prompt=body.prompt,
            system_prompt=body.system_prompt,
            providers=configs,
            auto_select=body.auto_select or not configs,
            auto_count=body.auto_count,
        )

        result = engine.run_battle(req)

        return {
            "success": True,
            "battle": {
                "prompt": result.prompt,
                "system_prompt": result.system_prompt,
                "results": [
                    {
                        "provider": r.provider,
                        "model": r.model,
                        "label": r.label,
                        "content": r.content,
                        "latency_ms": round(r.latency_ms, 1),
                        "token_count_input": r.token_count_input,
                        "token_count_output": r.token_count_output,
                        "token_count_total": r.token_count_total,
                        "cost_usd": r.cost_usd,
                        "error": r.error,
                    }
                    for r in result.results
                ],
                "winner": result.winner,
                "total_latency_ms": round(result.total_latency_ms, 1),
            },
        }
    except Exception as e:
        logger.error(f"Battle run error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Battle failed: {e}")


@router.get("/history")
async def battle_history(limit: int = Query(default=10, ge=1, le=50)):
    """Get recent model battle history."""
    from src.battle import BattleEngine

    try:
        engine = BattleEngine()
        history = engine.get_history(limit=limit)
        return {
            "success": True,
            "history": [
                {
                    "id": h.id,
                    "prompt": h.prompt,
                    "provider_count": h.provider_count,
                    "winner": h.winner,
                    "created_at": h.created_at,
                }
                for h in history
            ],
        }
    except Exception as e:
        logger.error(f"Battle history error: {e}")
        return {"success": True, "history": []}


@router.get("/providers")
async def battle_available_providers():
    """Get available providers for battle selection."""
    from src.core.providers import ProviderRouter

    router = ProviderRouter()
    statuses = router.get_provider_status()

    providers = []
    for s in statuses:
        if not s["available"]:
            continue
        providers.append({
            "id": s["id"],
            "label": s["label"],
            "default_model": s["default_model"],
            "is_local": s["is_local"],
        })

    return {"success": True, "providers": providers}
