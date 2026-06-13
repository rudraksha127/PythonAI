"""
Unified API Gateway — Ek Port Se Sab Projects Accessible
===========================================================

Proxies requests to all ForgeAI ecosystem services through a single port.

Architecture:
  ┌────────────────────────────────────────────┐
  │        Unified Gateway (Port 8000)          │
  │                                             │
  │  /api/pythonai/*    ───▶ PythonAI:7337     │
  │  /api/rudra-bots/*  ───▶ Rudra-bots:7000   │
  │  /api/dashboard/*   ───▶ Dashboard:3000    │
  │  /api/hermes/*      ───▶ Hermes:8642       │
  │  /health            ───▶ Self health       │
  │  /api/auth/*        ───▶ Auth hub (local)  │
  └────────────────────────────────────────────┘

Usage:
    python -m src.integration.gateway --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import websockets
import websockets.exceptions

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.integration.auth import ForgeAIAuth, ForgeAIToken
from src.integration.ecosystem_manager import EcosystemManager

logger = logging.getLogger("forgeai.gateway")

# Service registry: name → (base_url, prefix_strip)
SERVICES: dict[str, tuple[str, bool]] = {
    "pythonai": ("http://localhost:7337", True),
    "rudra-bots": ("http://localhost:7000", True),
    "dashboard": ("http://localhost:3000", True),
    "hermes": ("http://localhost:8642", True),
}

# Health check cache
_health_cache: dict[str, dict[str, Any]] = {}
_health_cache_time: float = 0


def _discover_services():
    """Auto-discover services from environment variables."""
    import os

    if os.environ.get("PYTHONAI_URL"):
        SERVICES["pythonai"] = (os.environ["PYTHONAI_URL"], True)
    if os.environ.get("RUDRA_BOTS_URL"):
        SERVICES["rudra-bots"] = (os.environ["RUDRA_BOTS_URL"], True)
    if os.environ.get("DASHBOARD_URL"):
        SERVICES["dashboard"] = (os.environ["DASHBOARD_URL"], True)
    if os.environ.get("HERMES_URL"):
        SERVICES["hermes"] = (os.environ["HERMES_URL"], True)


_discover_services()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ForgeAI Gateway starting up...")
    # Start the self-healing watchdog
    watchdog_task = asyncio.create_task(_service_watchdog())
    logger.info("Service watchdog started (checks every 60s)")
    yield
    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    logger.info("ForgeAI Gateway shutting down.")


# ── Service Watchdog ──────────────────────────────────────────────

_watchdog_status: dict[str, Any] = {}


async def _service_watchdog():
    """Background task that pings services every 60s.

    Records uptime stats and logs warnings when services go down.
    In the future, can be extended to auto-restart via EcosystemManager.
    """
    while True:
        try:
            await asyncio.sleep(60)
            for name, (url, _) in SERVICES.items():
                health_path = "/health"
                if name == "rudra-bots":
                    health_path = "/api/health"
                elif name == "dashboard":
                    health_path = "/api/health"  # Now uses the proper endpoint
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        r = await client.get(f"{url}{health_path}")
                        _watchdog_status[name] = {
                            "status": "healthy" if r.status_code == 200 else "degraded",
                            "last_check": time.time(),
                            "code": r.status_code,
                        }
                except Exception:
                    prev = _watchdog_status.get(name, {})
                    fail_count = prev.get("consecutive_fails", 0) + 1
                    _watchdog_status[name] = {
                        "status": "down",
                        "last_check": time.time(),
                        "consecutive_fails": fail_count,
                    }
                    logger.warning(
                        f"Watchdog: {name} is DOWN (fail #{fail_count}). "
                        f"Consider restarting via ecosystem manager."
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Watchdog error: {e}")


app = FastAPI(
    title="ForgeAI Unified Gateway",
    description="Single entry point for all ForgeAI ecosystem services",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared auth instance
_auth = ForgeAIAuth()
_ecosystem = EcosystemManager()

# ── Auth Middleware ──────────────────────────────────────────────

_AUTH_EXEMPT_PATHS = {
    "/health",
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/verify",
    "/api/auth/service-token",
    "/api/ecosystem",
    "/api/watchdog",
    "/api/forgeai/ecosystem-metrics",
}

# Prefix-based exemptions for browsable API routes
_AUTH_EXEMPT_PREFIXES = (
    "/api/arsenal/",
    "/api/forgeai/",
)


class _AuthMiddleware(BaseHTTPMiddleware):
    """Validates JWT bearer tokens on all proxy/auth routes.

    Exempts health and auth-login/signup so the first login can
    happen without credentials. All other routes require a valid
    Authorization: Bearer <token> header.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for exempt paths
        if path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)

        # Skip auth for prefix-exempt paths (arsenal, forgeai)
        if any(path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        # Skip auth for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid Authorization header. Use: Bearer <token>"},
            )

        token_str = auth_header[7:]
        token: ForgeAIToken | None = _auth.validate_token(token_str)
        if token is None:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or expired token"},
            )

        # Attach user info to request state for downstream use
        request.state.auth_user = token.username
        request.state.auth_role = token.role
        request.state.auth_token = token

        return await call_next(request)


app.add_middleware(_AuthMiddleware)


# ── Health ───────────────────────────────────────────────────────


@app.get("/health")
async def gateway_health():
    """Gateway health + ecosystem status."""
    global _health_cache, _health_cache_time

    now = time.time()
    if now - _health_cache_time > 10:  # Cache for 10s
        _health_cache = {}
        for name, (url, _) in SERVICES.items():
            try:
                health_path = "/health"
                if name == "rudra-bots":
                    health_path = "/api/health"
                elif name == "dashboard":
                    health_path = "/api/health"  # Proper health endpoint now

                async with httpx.AsyncClient(timeout=3.0) as client:
                    r = await client.get(f"{url}{health_path}")
                    _health_cache[name] = {
                        "status": "healthy" if r.status_code == 200 else "degraded",
                        "code": r.status_code,
                    }
            except Exception:
                _health_cache[name] = {"status": "unreachable"}
        _health_cache_time = now

    return {
        "gateway": "running",
        "version": "2.1.0",
        "services": _health_cache,
        "service_count": len(_health_cache),
        "healthy_count": sum(1 for s in _health_cache.values() if s["status"] == "healthy"),
        "watchdog": _watchdog_status,
    }


# ── Service Proxy ────────────────────────────────────────────────


async def _proxy_request(
    service_name: str,
    request: Request,
    path: str,
) -> Response:
    """Proxy an HTTP request to a backend service."""
    service_entry = SERVICES.get(service_name)
    if service_entry is None:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    service_url, strip_prefix = service_entry

    # Build target URL
    target_path = path
    if strip_prefix:
        prefix = f"/api/{service_name}"
        if target_path.startswith(prefix):
            target_path = target_path[len(prefix) :] or "/"

    target_url = f"{service_url}{target_path}"

    # Forward query params
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Forward authenticated user context to downstream services
    forwarded_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    if hasattr(request.state, "auth_user"):
        forwarded_headers["X-Forwarded-User"] = request.state.auth_user
    if hasattr(request.state, "auth_role"):
        forwarded_headers["X-Forwarded-Role"] = request.state.auth_role

    # Read body
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forwarded_headers,
                content=body or None,
            )

        # Return the proxied response
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding",)},
        )

    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail=f"Service '{service_name}' unreachable at {service_url}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Service '{service_name}' timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Proxy Routes ────────────────────────────────────────────────

# PythonAI proxy
@app.api_route("/api/pythonai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_pythonai(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/pythonai/{path}")


# Also proxy /api/pythonai root
@app.api_route("/api/pythonai", methods=["GET", "POST"])
async def proxy_pythonai_root(request: Request):
    return await _proxy_request("pythonai", request, "/api/pythonai")


# PythonAI direct endpoints (for dashboard compatibility)
@app.api_route("/api/metrics/{path:path}", methods=["GET", "POST"])
async def proxy_metrics(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/metrics/{path}")


@app.api_route("/api/training/{path:path}", methods=["GET", "POST", "PUT"])
async def proxy_training(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/training/{path}")


@app.api_route("/api/projects{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_projects(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/projects{path}")


@app.api_route("/api/seal/{path:path}", methods=["GET", "POST"])
async def proxy_seal(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/seal/{path}")


@app.api_route("/api/rag/{path:path}", methods=["GET", "POST"])
async def proxy_rag(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/rag/{path}")


@app.api_route("/api/events", methods=["POST"])
async def proxy_events(request: Request):
    return await _proxy_request("pythonai", request, "/api/events")


@app.api_route("/api/agent/{path:path}", methods=["GET", "POST"])
async def proxy_agent(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/agent/{path}")


# Rudra-bots proxy
@app.api_route("/api/rudra-bots/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_rudra_bots(path: str, request: Request):
    return await _proxy_request("rudra-bots", request, f"/api/rudra-bots/{path}")


# Ecosystem metrics proxy
@app.api_route("/api/forgeai/ecosystem-metrics", methods=["GET"])
async def proxy_ecosystem_metrics(request: Request):
    return await _proxy_request("pythonai", request, "/api/forgeai/ecosystem-metrics")


# ForgeAI routes inside Rudra-bots
@app.api_route("/api/forgeai/{path:path}", methods=["GET", "POST", "DELETE"])
async def proxy_forgeai(path: str, request: Request):
    return await _proxy_request("rudra-bots", request, f"/api/forgeai/{path}")


# Dashboard proxy (Next.js)
@app.api_route("/dashboard/{path:path}", methods=["GET"])
async def proxy_dashboard(path: str, request: Request):
    return await _proxy_request("dashboard", request, f"/{path}")


@app.api_route("/_next/{path:path}", methods=["GET"])
async def proxy_next_assets(path: str, request: Request):
    return await _proxy_request("dashboard", request, f"/_next/{path}")


# Arsenal proxy
@app.api_route("/api/arsenal/{path:path}", methods=["GET"])
async def proxy_arsenal(path: str, request: Request):
    return await _proxy_request("pythonai", request, f"/api/arsenal/{path}")


# ── WebSocket Proxy Routes ──────────────────────────────────────


async def _ws_proxy(ws_client: WebSocket, target_url: str):
    """Bidirectional WebSocket proxy to a backend service."""
    await ws_client.accept()
    try:
        async with websockets.connect(target_url) as ws_backend:
            async def client_to_backend():
                try:
                    while True:
                        data = await ws_client.receive_text()
                        await ws_backend.send(data)
                except WebSocketDisconnect:
                    pass

            async def backend_to_client():
                try:
                    async for message in ws_backend:
                        await ws_client.send_text(str(message))
                except websockets.exceptions.ConnectionClosed:
                    pass

            await asyncio.gather(client_to_backend(), backend_to_client())
    except Exception as e:
        logger.warning(f"WebSocket proxy error: {e}")
    finally:
        try:
            await ws_client.close()
        except Exception:
            pass


@app.websocket("/ws/events")
async def ws_proxy_events(ws: WebSocket):
    """Proxy WebSocket connections to PythonAI's /ws/events."""
    await _ws_proxy(ws, "ws://localhost:7337/ws/events")


@app.websocket("/ws/training-progress")
async def ws_proxy_training(ws: WebSocket):
    """Proxy WebSocket connections to PythonAI's /ws/training-progress."""
    await _ws_proxy(ws, "ws://localhost:7337/ws/training-progress")


# ── Watchdog Status Endpoint ─────────────────────────────────────


@app.get("/api/watchdog")
async def get_watchdog_status():
    """Get the service watchdog status with per-service health history."""
    return {
        "watchdog": "active",
        "services": _watchdog_status,
        "check_interval_seconds": 60,
    }


# ── Auth Endpoints (native, body-based) ──────────────────────────────

from pydantic import BaseModel


class _LoginBody(BaseModel):
    username: str
    password: str


class _SignupBody(BaseModel):
    username: str
    password: str
    email: str = ""
    role: str = "developer"


class _VerifyBody(BaseModel):
    token: str


class _ServiceTokenBody(BaseModel):
    service_name: str


@app.post("/api/auth/login")
async def auth_login(body: _LoginBody):
    return _auth.authenticate(body.username, body.password)


@app.post("/api/auth/signup")
async def auth_signup(body: _SignupBody):
    result = _auth.create_user(body.username, body.password, body.email, body.role)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/auth/verify")
async def auth_verify(body: _VerifyBody):
    result = _auth.validate_token(body.token)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return result.to_dict()


@app.get("/api/auth/users")
async def list_users():
    return {"users": _auth.list_users()}


@app.post("/api/auth/service-token")
async def create_service_token(body: _ServiceTokenBody):
    token = _auth.create_service_token(body.service_name)
    return {"token": token.token, "service": body.service_name, "expires_at": token.expires_at}


# ── Ecosystem Status ─────────────────────────────────────────────


@app.get("/api/ecosystem")
async def ecosystem_status():
    """Get full ecosystem status."""
    return _ecosystem.get_ecosystem_status()


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="ForgeAI Unified API Gateway")
    parser.add_argument("--port", type=int, default=8000, help="Gateway port (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")

    args = parser.parse_args()

    print(f"\n{'=' * 50}")
    print("  FORGEAI UNIFIED GATEWAY")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"{'=' * 50}")
    print(f"\n  Service routes:")
    for name, (url, _) in SERVICES.items():
        # Use ASCII-safe arrows to avoid UnicodeEncodeError on Windows cp1252
        print(f"    /api/{name}/*  -->  {url}")
    print(f"  Auth:    /api/auth/*  (native)")
    print(f"  Health:  /health")
    print(f"  Ecosystem: /api/ecosystem")
    print(f"{'=' * 50}\n")

    uvicorn.run(
        "src.integration.gateway:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
