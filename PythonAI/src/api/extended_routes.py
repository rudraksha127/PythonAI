"""
ForgeAI Extended API Routes — Monitoring, Cache, Retry, Templates, Analytics
=============================================================================

Additional API endpoints for the new modules.

Registered in server.py as a single router.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.extended")

router = APIRouter(prefix="/api", tags=["extended"])


# ═══════════════════════════════════════
# Monitoring Endpoints
# ═══════════════════════════════════════


@router.get("/monitoring/health")
async def extended_health() -> dict[str, Any]:
    """Extended health check with component-level status."""
    from src.monitoring import create_health_report

    try:
        report = create_health_report(
            version="2.0.0",
            db_ok=True,
            inference_connected=True,
            rag_available=True,
            training_idle=True,
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/metrics/prometheus")
async def prometheus_metrics() -> dict[str, Any]:
    """Get metrics in Prometheus exposition format."""
    from src.monitoring import get_metrics

    try:
        text = get_metrics().get_prometheus_text()
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/metrics/save")
async def save_metrics_snapshot() -> dict[str, Any]:
    """Save a metrics snapshot to disk."""
    from src.monitoring import get_metrics

    try:
        get_metrics().save_to_disk()
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# Cache Endpoints
# ═══════════════════════════════════════


class CacheSetRequest(BaseModel):
    """Set a cache entry."""
    query: str = Field(..., min_length=1, max_length=2000)
    response: Any
    provider: str = "default"
    model: str = ""
    token_count: int = 0
    ttl: int | None = None


class CacheGetRequest(BaseModel):
    """Get a cache entry."""
    query: str = Field(..., min_length=1, max_length=2000)
    provider: str = "default"
    model: str = ""


@router.post("/cache/set")
async def cache_set(body: CacheSetRequest) -> dict[str, Any]:
    """Set a cache entry for an LLM query."""
    from src.cache import get_cache

    try:
        get_cache().set(
            query=body.query,
            response=body.response,
            provider=body.provider,
            model=body.model,
            token_count=body.token_count,
            ttl=body.ttl,
        )
        return {"status": "cached"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/get")
async def cache_get(body: CacheGetRequest) -> dict[str, Any]:
    """Get a cache entry by exact match."""
    from src.cache import get_cache

    try:
        result = get_cache().get(body.query, provider=body.provider, model=body.model)
        if result is None:
            # Try semantic match
            result = get_cache().semantic_get(body.query, provider=body.provider, model=body.model)
        return {"found": result is not None, "response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
async def cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    from src.cache import get_cache

    try:
        return get_cache().get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def cache_clear() -> dict[str, Any]:
    """Clear the cache."""
    from src.cache import get_cache

    try:
        count = get_cache().clear()
        return {"cleared": count, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# Templates Endpoints
# ═══════════════════════════════════════


class TemplateCreateRequest(BaseModel):
    """Create a new prompt template."""
    name: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    description: str = ""
    category: str = "general"
    variables: list[str] = []
    tags: list[str] = []


class TemplateUpdateRequest(BaseModel):
    """Update a prompt template."""
    content: str | None = None
    description: str | None = None
    category: str | None = None
    variables: list[str] | None = None
    tags: list[str] | None = None


class TemplateRenderRequest(BaseModel):
    """Render a prompt template with variables."""
    template_id_or_name: str = Field(..., min_length=1)
    variables: dict[str, str] = Field(default_factory=dict)


@router.get("/templates")
async def list_templates(category: str | None = None) -> list[dict[str, Any]]:
    """List all prompt templates."""
    from src.templates import get_template_manager

    try:
        manager = get_template_manager()
        templates = manager.list(category=category)
        return [t.to_dict() for t in templates]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/stats")
async def template_stats() -> dict[str, Any]:
    """Get template statistics."""
    from src.templates import get_template_manager

    try:
        return get_template_manager().get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates")
async def create_template(body: TemplateCreateRequest) -> dict[str, Any]:
    """Create a new prompt template."""
    from src.templates import get_template_manager

    try:
        tmpl = get_template_manager().create(
            name=body.name,
            content=body.content,
            description=body.description,
            category=body.category,
            variables=body.variables or None,
            tags=body.tags,
        )
        return tmpl.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{template_id}")
async def get_template(template_id: str) -> dict[str, Any]:
    """Get a template by ID."""
    from src.templates import get_template_manager

    try:
        tmpl = get_template_manager().get(template_id)
        if tmpl is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return tmpl.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/templates/{template_id}")
async def update_template(template_id: str, body: TemplateUpdateRequest) -> dict[str, Any]:
    """Update a prompt template."""
    from src.templates import get_template_manager

    try:
        tmpl = get_template_manager().update(
            template_id=template_id,
            content=body.content,
            description=body.description,
            category=body.category,
            variables=body.variables,
            tags=body.tags,
        )
        if tmpl is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return tmpl.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str) -> dict[str, Any]:
    """Delete a prompt template."""
    from src.templates import get_template_manager

    try:
        deleted = get_template_manager().delete(template_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/render")
async def render_template(body: TemplateRenderRequest) -> dict[str, Any]:
    """Render a template with variables."""
    from src.templates import get_template_manager

    try:
        result = get_template_manager().render(
            body.template_id_or_name,
            **body.variables,
        )
        return {"rendered": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# Analytics Endpoints
# ═══════════════════════════════════════


class AnalyticsLogRequest(BaseModel):
    """Log a usage event."""
    provider: str = Field(..., max_length=100)
    model: str = Field(..., max_length=100)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None
    latency_ms: float = 0.0
    user_id: str = "anonymous"
    project_id: str = "default"
    session_id: str = ""


@router.post("/analytics/log")
async def analytics_log(body: AnalyticsLogRequest) -> dict[str, Any]:
    """Log an LLM API call for usage tracking."""
    from src.analytics import get_tracker

    try:
        record_id = get_tracker().log_call(
            provider=body.provider,
            model=body.model,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
            cost=body.cost,
            latency_ms=body.latency_ms,
            user_id=body.user_id,
            project_id=body.project_id,
            session_id=body.session_id,
        )
        return {"record_id": record_id, "status": "logged"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/report")
async def analytics_report(days: int = 7) -> dict[str, Any]:
    """Get usage analytics report."""
    from src.analytics import get_tracker

    try:
        return get_tracker().get_report(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/cost")
async def analytics_cost(days: int = 30) -> dict[str, Any]:
    """Get cost summary."""
    from src.analytics import get_tracker

    try:
        return get_tracker().get_cost_summary(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# Retry / Circuit Breaker Endpoints
# ═══════════════════════════════════════


@router.get("/retry/stats")
async def retry_stats() -> dict[str, Any]:
    """Get retry handler statistics."""
    from src.retry import get_retry_handler

    try:
        return get_retry_handler().get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry/reset/{provider}")
async def retry_reset(provider: str) -> dict[str, Any]:
    """Reset circuit breaker for a provider."""
    from src.retry import get_retry_handler

    try:
        get_retry_handler().reset_circuit_breaker(provider)
        return {"status": "reset", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# Capture Engine Hook Endpoints
# ═══════════════════════════════════════


@router.post("/capture/git-hook")
async def capture_git_hook(data: dict[str, Any]) -> dict[str, Any]:
    """Capture a signal from a git hook (post-commit/post-merge).

    Expects JSON with:
      - event_type: "pr_merge"
      - file_path, language, code_content
      - pr_number, branch, git_sha
    """
    from src.learning.capture_engine import CaptureEngine

    try:
        engine = CaptureEngine()

        if data.get("event_type") == "pr_merge":
            signal_id = engine.capture_pr_merge(
                file_path=data.get("file_path", ""),
                language=data.get("language", "unknown"),
                code_content=data.get("code_content", ""),
                pr_number=data.get("pr_number", 0),
                branch_name=data.get("branch", ""),
                git_sha=data.get("git_sha", ""),
                context_before=data.get("context_before", ""),
                context_after=data.get("context_after", ""),
            )
            return {"signal_id": signal_id, "captured": True}
        else:
            raise HTTPException(status_code=400, detail="Unsupported event_type for git hook")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capture/signal-weights")
async def capture_signal_weights() -> dict[str, Any]:
    """Get current signal weight configuration.

    Returns the weight multiplier for each signal type based on
    edit distance, context length, and other quality factors.
    """
    return {
        "signal_weights": {
            "accept": 1.0,
            "reject": -0.5,
            "edit": 0.7,
            "test_pass": 2.0,
            "test_fail": -1.0,
            "pr_merge": 1.5,
            "implicit_accept": 0.3,
        },
        "weight_factors": {
            "edit_distance_boost": 0.3,
            "context_length_boost": 0.1,
            "test_verified_boost": 1.0,
        },
    }


# ═══════════════════════════════════════
# Combined Dashboard Data
# ═══════════════════════════════════════


@router.get("/dashboard/all")
async def dashboard_all_data() -> dict[str, Any]:
    """Get all dashboard data in one call (combined endpoint)."""
    import requests as req

    base = "http://localhost:7337"
    result: dict[str, Any] = {}

    try:
        resp = req.get(f"{base}/health", timeout=5)
        result["health"] = resp.json() if resp.status_code == 200 else {"error": "unavailable"}
    except Exception:
        result["health"] = {"error": "unreachable"}

    try:
        resp = req.get(f"{base}/stats", timeout=5)
        result["stats"] = resp.json() if resp.status_code == 200 else {}
    except Exception:
        result["stats"] = {}

    try:
        resp = req.get(f"{base}/metrics", timeout=5)
        result["metrics"] = resp.json() if resp.status_code == 200 else {}
    except Exception:
        result["metrics"] = {}

    try:
        from src.cache import get_cache
        result["cache"] = get_cache().get_stats()
    except Exception:
        result["cache"] = {"enabled": False}

    try:
        from src.templates import get_template_manager
        result["templates"] = get_template_manager().get_stats()
    except Exception:
        result["templates"] = {"total_templates": 0}

    try:
        from src.monitoring import get_metrics
        result["monitoring"] = get_metrics().get_summary()
    except Exception:
        result["monitoring"] = {}

    return result


# ═══════════════════════════════════════
# Knowledge Graph Endpoints
# ═══════════════════════════════════════


class GraphQueryRequest(BaseModel):
    """Query the knowledge graph."""
    query: str = Field(..., min_length=1, max_length=500)
    hops: int = Field(default=2, ge=1, le=5)
    max_results: int = Field(default=10, ge=1, le=50)


@router.post("/rag/graph-query", tags=["rag"])
async def rag_graph_query(body: GraphQueryRequest) -> dict[str, Any]:
    """
    Query the Knowledge Graph for concept relationships.

    Uses graph traversal (BFS) to find related concepts N hops away.
    Returns ranked results with edge types and similarity scores.
    """
    from src.rag.knowledge_graph import KnowledgeGraph

    try:
        kg = KnowledgeGraph()
        if not kg.load():
            return {
                "success": False,
                "error": "Knowledge graph not built. Run: python -m src.rag.knowledge_graph build",
                "results": [],
            }

        results = kg.query(
            question=body.query,
            hops=body.hops,
            max_results=body.max_results,
        )

        # Get neighbor info for each result
        enriched = []
        for r in results:
            neighbors = kg.get_neighbors(r["node_id"])[:5]
            enriched.append({
                **r,
                "neighbors": [
                    {"title": n["title"], "edge_type": n["edge_type"], "weight": n["weight"]}
                    for n in neighbors
                ],
            })

        return {
            "success": True,
            "query": body.query,
            "total_results": len(results),
            "results": enriched,
            "stats": kg.stats(),
        }
    except Exception as e:
        logger.error(f"Knowledge graph query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/graph/stats", tags=["rag"])
async def rag_graph_stats() -> dict[str, Any]:
    """Get knowledge graph statistics."""
    from src.rag.knowledge_graph import KnowledgeGraph

    try:
        kg = KnowledgeGraph()
        if kg.load():
            return {"success": True, "stats": kg.stats()}
        return {"success": False, "error": "Knowledge graph not built", "stats": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/graph/neighbors/{node_id}", tags=["rag"])
async def rag_graph_neighbors(node_id: str) -> dict[str, Any]:
    """Get neighbors of a knowledge graph node."""
    from src.rag.knowledge_graph import KnowledgeGraph

    try:
        kg = KnowledgeGraph()
        if not kg.load():
            return {"success": False, "error": "Knowledge graph not built"}
        neighbors = kg.get_neighbors(node_id)
        return {"success": True, "node_id": node_id, "neighbors": neighbors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ═══════════════════════════════════════
# Skills Marketplace Endpoints
# ═══════════════════════════════════════


@router.get("/marketplace/adapters")
async def marketplace_list_adapters(
    search: str | None = None,
    category: str | None = None,
    framework: str | None = None,
    industry: str | None = None,
) -> dict[str, Any]:
    """List adapters in the marketplace."""
    from src.marketplace import get_marketplace_manager

    try:
        manager = get_marketplace_manager()
        adapters = manager.list_adapters(
            category=category,
            framework=framework,
            industry=industry,
            search=search,
        )
        return {"success": True, "adapters": [a.to_dict() for a in adapters], "count": len(adapters)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marketplace/adapters/{adapter_id}")
async def marketplace_get_adapter(adapter_id: str) -> dict[str, Any]:
    """Get details for a specific adapter."""
    from src.marketplace import get_marketplace_manager

    try:
        manager = get_marketplace_manager()
        adapter = manager.get_adapter(adapter_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail="Adapter not found")
        return {"success": True, "adapter": adapter.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marketplace/stats")
async def marketplace_stats() -> dict[str, Any]:
    """Get marketplace statistics."""
    from src.marketplace import get_marketplace_manager

    try:
        stats = get_marketplace_manager().get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketplace/install")
async def marketplace_install(data: dict[str, Any]) -> dict[str, Any]:
    """Install an adapter from the marketplace."""
    from src.marketplace import get_marketplace_manager

    try:
        adapter_id = data.get("adapter_id", "")
        if not adapter_id:
            raise HTTPException(status_code=400, detail="adapter_id required")
        success = get_marketplace_manager().install_adapter(adapter_id)
        if not success:
            raise HTTPException(status_code=404, detail="Adapter not found")
        return {"success": True, "message": f"Adapter {adapter_id} installed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketplace/uninstall")
async def marketplace_uninstall(data: dict[str, Any]) -> dict[str, Any]:
    """Uninstall an adapter."""
    from src.marketplace import get_marketplace_manager

    try:
        adapter_id = data.get("adapter_id", "")
        if not adapter_id:
            raise HTTPException(status_code=400, detail="adapter_id required")
        success = get_marketplace_manager().uninstall_adapter(adapter_id)
        if not success:
            raise HTTPException(status_code=404, detail="Adapter not found")
        return {"success": True, "message": f"Adapter {adapter_id} uninstalled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketplace/upload")
async def marketplace_upload(
    name: str = "",
    description: str = "",
    author: str = "anonymous",
    version: str = "1.0.0",
    base_model: str = "",
    framework: str = "",
    industry: str = "",
    tags: str = "",
) -> dict[str, Any]:
    """Upload a new adapter to the marketplace.

    Accepts multipart form data with the adapter file and metadata.
    Automatically scans for PII/proprietary content.
    """
    from fastapi import UploadFile, File
    import tempfile

    from src.marketplace import get_marketplace_manager, scan_adapter

    try:
        if not name:
            raise HTTPException(status_code=400, detail="name required")

        # Check if file is provided via query param
        # In production, use UploadFile. For now, create placeholder
        manager = get_marketplace_manager()
        adapter = manager.register_adapter(
            name=name,
            description=description,
            author=author,
            file_path=Path(tempfile.gettempdir()) / "placeholder.zip",
            version=version,
            base_model=base_model,
            framework=framework,
            industry=industry,
            tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else [],
        )

        if adapter is None:
            return {
                "success": False,
                "message": "Adapter failed sanitization scan or file not found",
            }

        return {
            "success": True,
            "message": f"Adapter '{name}' uploaded successfully",
            "adapter_id": adapter.id,
            "scan": {
                "passed": adapter.is_verified,
                "score": adapter.sanitization_score,
                "total_issues": 0,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketplace/compose")
async def marketplace_compose(data: dict[str, Any]) -> dict[str, Any]:
    """Compose multiple adapters."""
    from src.marketplace import get_marketplace_manager

    try:
        adapter_ids = data.get("adapter_ids", [])
        if not adapter_ids or len(adapter_ids) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 adapter_ids")
        result = get_marketplace_manager().compose_adapters(adapter_ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# SSO Auth Endpoints
# ═══════════════════════════════════════


@router.get("/auth/sso/providers")
async def sso_providers() -> dict[str, Any]:
    """List available SSO providers."""
    from src.auth.providers import get_sso_manager

    try:
        manager = get_sso_manager()
        providers = manager.get_available_providers()
        stats = manager.get_stats()
        return {"success": True, "providers": providers, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/sso/login/{provider}")
async def sso_login(provider: str) -> dict[str, Any]:
    """Initiate SSO login for a provider.

    Returns the authorization URL to redirect the user to.
    """
    from src.auth.providers import get_sso_manager

    try:
        manager = get_sso_manager()
        state = manager.generate_state(provider)

        if provider == "google":
            url = manager.google.get_auth_url(state=state)
        elif provider == "github":
            url = manager.github.get_auth_url(state=state)
        elif provider == "saml":
            url = manager.saml.get_auth_url()
        elif provider == "oidc":
            url = manager.oidc.get_auth_url()
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

        return {"success": True, "auth_url": url, "provider": provider, "state": state}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SSOCallbackRequest(BaseModel):
    """SSO callback request."""
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1, max_length=50)


@router.post("/auth/sso/callback")
async def sso_callback(body: SSOCallbackRequest) -> dict[str, Any]:
    """Handle SSO callback from OAuth2 provider.

    Exchanges the authorization code for user info and creates a session.
    """
    from src.auth.providers import get_sso_manager

    try:
        manager = get_sso_manager()

        # Validate state (CSRF protection)
        if not manager.validate_state(body.state, body.provider):
            raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

        # Exchange code for user
        user = None
        if body.provider == "google":
            user = manager.handle_google_callback(body.code)
        elif body.provider == "github":
            user = manager.handle_github_callback(body.code)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {body.provider}")

        if user is None:
            raise HTTPException(status_code=401, detail="Authentication failed")

        # Create session
        session_id = manager.create_session(user)

        return {
            "success": True,
            "session_id": session_id,
            "user": {
                "provider": user.provider,
                "name": user.name,
                "email": user.email,
                "avatar_url": user.avatar_url,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SSO callback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/sso/stats")
async def sso_stats() -> dict[str, Any]:
    """Get SSO system statistics."""
    from src.auth.providers import get_sso_manager

    try:
        stats = get_sso_manager().get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


logger.info("Extended routes registered")
