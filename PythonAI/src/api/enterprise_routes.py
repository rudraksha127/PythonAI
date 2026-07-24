"""
ForgeAI Enterprise API Routes — SSO, RBAC, Audit Log
=====================================================

Enterprise-grade API endpoints for:
  - Single Sign-On (Google, GitHub, SAML, OIDC)
  - Role-Based Access Control (RBAC)
  - Compliance Audit Log

All routes are under /api/auth/sso/*, /api/admin/*, and /api/audit/*.

Usage (register in server.py):
    from src.api.enterprise_routes import router as enterprise_router
    app.include_router(enterprise_router)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.enterprise")

router = APIRouter(tags=["Enterprise"])

# ═══════════════════════════════════════════════════════════════════
# Lazy imports — these modules may have optional dependencies
# ═══════════════════════════════════════════════════════════════════

_SSO_MANAGER = None
_RBAC_MANAGER = None
_AUDIT_ENGINE = None


def _get_sso():
    global _SSO_MANAGER
    if _SSO_MANAGER is None:
        from src.auth.providers import get_sso_manager
        _SSO_MANAGER = get_sso_manager()
    return _SSO_MANAGER


def _get_rbac():
    global _RBAC_MANAGER
    if _RBAC_MANAGER is None:
        from src.auth.rbac import get_rbac_manager
        _RBAC_MANAGER = get_rbac_manager()
    return _RBAC_MANAGER


def _get_audit():
    global _AUDIT_ENGINE
    if _AUDIT_ENGINE is None:
        from src.audit import get_audit_engine
        _AUDIT_ENGINE = get_audit_engine()
    return _AUDIT_ENGINE


# ═══════════════════════════════════════════════════════════════════
# Request / Response Models
# ═══════════════════════════════════════════════════════════════════


class SSOCallbackRequest(BaseModel):
    code: str = ""
    state: str = ""
    saml_response: str = ""


class RoleAssignRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., pattern=r"^(admin|manager|developer)$")


class ProjectAccessRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    project_id: str = Field(..., min_length=1, max_length=200)
    action: str = Field(default="grant", pattern=r"^(grant|revoke)$")


class AuditQueryRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    action_prefix: str = ""
    actor: str = ""
    resource: str = ""
    category: str = ""
    severity: str = ""
    start_time: float | None = None
    end_time: float | None = None
    search: str = ""
    order: str = "DESC"


# ═══════════════════════════════════════════════════════════════════
# ── SSO Endpoints ─────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════


@router.get("/api/auth/sso/providers")
async def sso_providers():
    """List available SSO providers."""
    sso = _get_sso()
    providers = sso.get_available_providers()
    return {
        "success": True,
        "providers": providers,
        "count": len(providers),
    }


@router.get("/api/auth/sso/{provider}/login")
async def sso_login(provider: str, request: Request):
    """Initiate SSO login by redirecting to the provider's auth URL."""
    sso = _get_sso()
    state = sso.generate_state(provider)

    if provider == "google":
        if not sso.google.is_configured():
            raise HTTPException(status_code=400, detail="Google SSO not configured")
        auth_url = sso.google.get_auth_url(state)
    elif provider == "github":
        if not sso.github.is_configured():
            raise HTTPException(status_code=400, detail="GitHub SSO not configured")
        auth_url = sso.github.get_auth_url(state)
    elif provider == "saml":
        if not sso.saml.is_configured():
            raise HTTPException(status_code=400, detail="SAML not configured")
        auth_url = sso.saml.get_auth_url(state)
    elif provider == "oidc":
        if not sso.oidc.is_configured():
            raise HTTPException(status_code=400, detail="OIDC not configured")
        auth_url = sso.oidc.get_auth_url(state)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown SSO provider: {provider}")

    _get_audit().record(
        action="sso.login_initiated",
        actor="anonymous",
        resource="sso",
        resource_id=provider,
        detail=f"SSO login initiated via {provider}",
        ip_address=request.client.host if request.client else "",
    )

    return {
        "success": True,
        "provider": provider,
        "auth_url": auth_url,
        "state": state,
    }


@router.post("/api/auth/sso/{provider}/callback")
async def sso_callback(provider: str, body: SSOCallbackRequest, request: Request):
    """Handle SSO callback from the provider."""
    sso = _get_sso()
    audit = _get_audit()
    ip = request.client.host if request.client else ""

    # Validate state (CSRF protection)
    if body.state and not sso.validate_state(body.state, provider):
        raise HTTPException(status_code=400, detail="Invalid state parameter (CSRF)")

    user = None
    try:
        if provider == "google":
            user = sso.handle_google_callback(body.code)
        elif provider == "github":
            user = sso.handle_github_callback(body.code)
        elif provider == "saml":
            user = sso.handle_saml_callback(body.saml_response)
        elif provider == "oidc":
            user = sso.handle_oidc_callback(body.code, body.state)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    except Exception as e:
        audit.record(
            action="sso.login_failed",
            actor="anonymous",
            resource="sso",
            resource_id=provider,
            detail=f"SSO callback error for {provider}: {e}",
            severity="warning",
            ip_address=ip,
        )
        raise HTTPException(status_code=401, detail=f"SSO authentication failed: {e}")

    if user is None:
        audit.record(
            action="sso.login_failed",
            actor="anonymous",
            resource="sso",
            resource_id=provider,
            detail=f"SSO authentication failed for {provider} (no user returned)",
            severity="warning",
            ip_address=ip,
        )
        raise HTTPException(status_code=401, detail="SSO authentication failed")

    # Create session
    session_id = sso.create_session(user)
    audit.record_login(
        username=user.email or user.name,
        success=True,
        ip_address=ip,
        method=f"sso_{provider}",
    )

    return {
        "success": True,
        "user": {
            "name": user.name,
            "email": user.email,
            "provider": user.provider,
            "avatar_url": user.avatar_url,
        },
        "session_id": session_id,
        "provider": provider,
    }


@router.get("/api/auth/sso/status")
async def sso_status():
    """Get SSO system status."""
    sso = _get_sso()
    return {
        "success": True,
        **sso.get_stats(),
    }


@router.get("/api/auth/sso/metadata")
async def sso_saml_metadata():
    """Get SAML SP metadata XML for IdP registration."""
    sso = _get_sso()
    if not sso.saml.is_configured():
        raise HTTPException(status_code=400, detail="SAML not configured")
    metadata = sso.saml.get_metadata_xml()
    if not metadata:
        raise HTTPException(status_code=500, detail="Failed to generate SAML metadata")
    return {"success": True, "metadata_xml": metadata}


# ═══════════════════════════════════════════════════════════════════
# ── RBAC / Admin Endpoints ────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════


@router.get("/api/admin/users")
async def admin_list_users():
    """List all users with their roles and project access."""
    rbac = _get_rbac()
    users = rbac.list_users()
    audit = _get_audit()
    audit.record(
        action="admin.users_listed",
        actor="admin",
        resource="user",
        detail=f"Listed {len(users)} users",
    )
    return {"success": True, "users": users, "count": len(users)}


@router.get("/api/admin/users/{username}")
async def admin_get_user(username: str):
    """Get a user's details and permissions."""
    rbac = _get_rbac()
    user = rbac.get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User not found: {username}")
    permissions = rbac.get_role_permissions(user["role"])
    return {
        "success": True,
        "user": user,
        "permissions": permissions,
    }


@router.post("/api/admin/users/role")
async def admin_assign_role(body: RoleAssignRequest, request: Request):
    """Assign a role to a user."""
    rbac = _get_rbac()
    audit = _get_audit()
    ip = request.client.host if request.client else ""

    success = rbac.assign_role(body.username, body.role)
    if not success:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}")

    audit.record_admin_action(
        action="role_assigned",
        admin_actor="admin",
        target_user=body.username,
        detail=f"Role '{body.role}' assigned to {body.username}",
        metadata={"new_role": body.role},
    )

    return {
        "success": True,
        "username": body.username,
        "role": body.role,
        "permissions": rbac.get_role_permissions(body.role),
    }


@router.post("/api/admin/users/project-access")
async def admin_project_access(body: ProjectAccessRequest, request: Request):
    """Grant or revoke a user's access to a project."""
    rbac = _get_rbac()
    audit = _get_audit()
    ip = request.client.host if request.client else ""

    if body.action == "grant":
        ok = rbac.grant_project_access(body.username, body.project_id)
        action_desc = "granted"
    else:
        ok = rbac.revoke_project_access(body.username, body.project_id)
        action_desc = "revoked"

    if not ok:
        raise HTTPException(status_code=404, detail=f"User not found: {body.username}")

    audit.record(
        action="admin.project_access_changed",
        actor="admin",
        resource="user",
        resource_id=body.username,
        detail=f"Project access {action_desc} for {body.username} on {body.project_id[:12]}...",
        ip_address=ip,
        metadata={"project_id": body.project_id, "action": body.action},
    )

    return {
        "success": True,
        "username": body.username,
        "project_id": body.project_id,
        "action": body.action,
    }


@router.get("/api/admin/roles")
async def admin_list_roles():
    """List all available roles and their permissions."""
    from src.auth.rbac import ROLES

    result = {}
    for role_name, role_info in ROLES.items():
        result[role_name] = {
            "description": role_info["description"],
            "permissions": role_info["permissions"],
            "permission_count": len(role_info["permissions"]),
        }
    return {"success": True, "roles": result}


# ═══════════════════════════════════════════════════════════════════
# ── Audit Log Endpoints ───────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════


@router.post("/api/audit/log")
async def audit_record(
    request: Request,
    action: str = Query(..., description="Dot-notation action name"),
    actor: str = Query("system", description="Who performed the action"),
    resource: str = Query("system", description="Resource type"),
    resource_id: str = Query("", description="Specific resource ID"),
    detail: str = Query("", description="Human-readable description"),
    severity: str = Query("info", description="Severity level"),
):
    """Record an audit event."""
    audit = _get_audit()
    ip = request.client.host if request.client else ""

    event = audit.record(
        action=action,
        actor=actor,
        resource=resource,
        resource_id=resource_id,
        detail=detail,
        severity=severity,
        ip_address=ip,
    )

    return {
        "success": True,
        "event_id": event.event_id,
        "action": event.action,
        "timestamp": event.timestamp,
    }


@router.post("/api/audit/query")
async def audit_query(body: AuditQueryRequest):
    """Query audit events with filters and pagination."""
    audit = _get_audit()
    events = audit.query(
        limit=body.limit,
        offset=body.offset,
        action_prefix=body.action_prefix,
        actor=body.actor,
        resource=body.resource,
        category=body.category,
        severity=body.severity,
        start_time=body.start_time,
        end_time=body.end_time,
        search=body.search,
        order=body.order,
    )
    total = audit.count(
        action_prefix=body.action_prefix,
        actor=body.actor,
        resource=body.resource,
        category=body.category,
        severity=body.severity,
        start_time=body.start_time,
        end_time=body.end_time,
        search=body.search,
    )

    return {
        "success": True,
        "events": [e.to_dict() for e in events],
        "total": total,
        "limit": body.limit,
        "offset": body.offset,
        "returned": len(events),
    }


@router.get("/api/audit/stats")
async def audit_stats():
    """Get audit log statistics."""
    audit = _get_audit()
    return {"success": True, **audit.get_stats()}


@router.get("/api/audit/export")
async def audit_export(
    format: str = Query("json", regex=r"^(json|csv)$"),
    action_prefix: str = Query(""),
    actor: str = Query(""),
    category: str = Query(""),
    severity: str = Query(""),
    start_time: float | None = Query(None),
    end_time: float | None = Query(None),
):
    """Export audit events for compliance."""
    import tempfile

    audit = _get_audit()
    query_kwargs = {
        "action_prefix": action_prefix,
        "actor": actor,
        "category": category,
        "severity": severity,
        "start_time": start_time,
        "end_time": end_time,
    }
    # Remove empty filters
    query_kwargs = {k: v for k, v in query_kwargs.items() if v}

    suffix = ".csv" if format == "csv" else ".json"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w") as tmp:
        if format == "csv":
            count = audit.export_csv(tmp.name, **query_kwargs)
        else:
            count = audit.export_json(tmp.name, **query_kwargs)

        tmp_path = tmp.name

    # Read back the temp file
    import os
    with open(tmp_path, "r", encoding="utf-8") as f:
        content = f.read()
    os.unlink(tmp_path)

    audit.record(
        action="admin.audit_exported",
        actor="admin",
        resource="audit",
        detail=f"Exported {count} audit events as {format.upper()}",
        metadata={"format": format, "count": count, "filters": query_kwargs},
    )

    return {
        "success": True,
        "format": format,
        "event_count": count,
        "content": content,
        "filename": f"forgeai_audit_{int(time.time())}.{suffix}",
    }


@router.get("/api/audit/categories")
async def audit_categories():
    """List all available audit action categories."""
    from src.audit.engine import ACTION_CATEGORIES

    return {
        "success": True,
        "categories": ACTION_CATEGORIES,
        "category_count": len(ACTION_CATEGORIES),
        "total_actions": sum(len(actions) for actions in ACTION_CATEGORIES.values()),
    }


@router.post("/api/audit/verify")
async def audit_verify_integrity():
    """Verify the SHA-256 chain integrity of all audit events."""
    audit = _get_audit()
    result = audit.verify_chain_integrity()
    return {"success": True, **result}


@router.post("/api/audit/rotate")
async def audit_rotate():
    """Archive audit events older than retention period."""
    audit = _get_audit()
    result = audit.rotate_logs()
    return {"success": True, **result}


# ═══════════════════════════════════════════════════════════════════
# ── RBAC Middleware (FastAPI dependency) ──────────────────────────
# ═══════════════════════════════════════════════════════════════════


async def require_role(required: str, request: Request) -> str:
    """FastAPI dependency: require a specific role.

    Usage:
        @router.get("/admin/dashboard")
        async def admin_dashboard(username: str = Depends(require_role("admin"))):
            ...

    NOTE: This requires the request.state.user to be set by an auth middleware.
    For standalone use, the middleware injects the authenticated user before
    this dependency runs.
    """
    username = getattr(request.state, "user", None) if hasattr(request.state, "user") else None
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    rbac = _get_rbac()
    user = rbac.get_user(username)
    if user is None:
        raise HTTPException(status_code=403, detail="User not found")

    from src.auth.rbac import ROLES
    required_perms = ROLES.get(required, {}).get("permissions", [])
    has_access = any(rbac.has_permission(username, perm) for perm in required_perms)

    if not has_access:
        _get_audit().record(
            action="admin.access_denied",
            actor=username,
            resource="api",
            severity="warning",
            detail=f"Access denied: requires role '{required}'",
        )
        raise HTTPException(status_code=403, detail=f"Requires role: {required}")

    return username
