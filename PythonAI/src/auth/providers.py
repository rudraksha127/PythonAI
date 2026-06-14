"""
ForgeAI SSO Providers — OAuth2, SAML 2.0, OIDC Integration
=============================================================

Single Sign-On providers for ForgeAI:
  - Google OAuth2
  - GitHub OAuth2
  - SAML 2.0 (generic)
  - OpenID Connect (OIDC, generic)

Each provider follows the same interface:
  1. get_auth_url() -> str (redirect user here)
  2. handle_callback(code) -> UserInfo (exchange code for user data)
  3. get_user_info() -> UserInfo (fetch user profile)

Environment variables for configuration:
  FORGEAI_SSO_GOOGLE_CLIENT_ID
  FORGEAI_SSO_GOOGLE_CLIENT_SECRET
  FORGEAI_SSO_GITHUB_CLIENT_ID
  FORGEAI_SSO_GITHUB_CLIENT_SECRET
  FORGEAI_SSO_SAML_METADATA_URL
  FORGEAI_SSO_OIDC_ISSUER_URL
  FORGEAI_SSO_OIDC_CLIENT_ID
  FORGEAI_SSO_OIDC_CLIENT_SECRET
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


# ═══════════════════════════════════════
# Data Models
# ═══════════════════════════════════════


@dataclass
class SSOUser:
    """Normalized user info from any SSO provider."""

    provider: str  # "google", "github", "saml", "oidc"
    provider_user_id: str
    email: str
    name: str
    avatar_url: str = ""
    access_token: str = ""
    refresh_token: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)
    authenticated_at: float = 0.0


@dataclass
class SSOProviderConfig:
    """Configuration for an SSO provider."""

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = field(default_factory=list)
    extra_params: dict[str, str] = field(default_factory=dict)


# ═══════════════════════════════════════
# OAuth2 Provider Base
# ═══════════════════════════════════════


class OAuth2Provider:
    """Base class for OAuth2 providers."""

    def __init__(
        self,
        name: str,
        config: SSOProviderConfig,
        auth_url: str,
        token_url: str,
        userinfo_url: str,
    ):
        self.name = name
        self.config = config
        self.auth_url = auth_url
        self.token_url = token_url
        self.userinfo_url = userinfo_url

    def get_auth_url(self, state: str | None = None) -> str:
        """Generate the OAuth2 authorization URL."""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        params.update(self.config.extra_params)
        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for tokens.

        Makes HTTP POST to token_url with the code.
        Returns the token response dict.
        """
        import requests

        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.redirect_uri,
        }

        headers = {"Accept": "application/json"}
        resp = requests.post(self.token_url, data=data, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch user info from the provider's userinfo endpoint."""
        import requests

        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(self.userinfo_url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def to_sso_user(self, token_data: dict[str, Any], user_data: dict[str, Any]) -> SSOUser:
        """Convert provider-specific data to normalized SSOUser.

        Subclasses should override this for provider-specific field mapping.
        """
        return SSOUser(
            provider=self.name,
            provider_user_id=str(user_data.get("sub", user_data.get("id", ""))),
            email=user_data.get("email", ""),
            name=user_data.get("name", ""),
            avatar_url=user_data.get("picture", user_data.get("avatar_url", "")),
            access_token=token_data.get("access_token", ""),
            refresh_token=token_data.get("refresh_token", ""),
            raw_data=user_data,
            authenticated_at=time.time(),
        )


# ═══════════════════════════════════════
# Google OAuth2 Provider
# ═══════════════════════════════════════


class GoogleProvider(OAuth2Provider):
    """Google OAuth2 SSO provider."""

    def __init__(self, redirect_uri: str = "http://localhost:7337/api/auth/sso/google/callback"):
        client_id = os.environ.get("FORGEAI_SSO_GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("FORGEAI_SSO_GOOGLE_CLIENT_SECRET", "")

        config = SSOProviderConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=["openid", "email", "profile"],
        )

        super().__init__(
            name="google",
            config=config,
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        )

    def is_configured(self) -> bool:
        """Check if Google OAuth2 is configured."""
        return bool(self.config.client_id and self.config.client_secret)


# ═══════════════════════════════════════
# GitHub OAuth2 Provider
# ═══════════════════════════════════════


class GitHubProvider(OAuth2Provider):
    """GitHub OAuth2 SSO provider."""

    def __init__(self, redirect_uri: str = "http://localhost:7337/api/auth/sso/github/callback"):
        client_id = os.environ.get("FORGEAI_SSO_GITHUB_CLIENT_ID", "")
        client_secret = os.environ.get("FORGEAI_SSO_GITHUB_CLIENT_SECRET", "")

        config = SSOProviderConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=["read:user", "user:email"],
        )

        super().__init__(
            name="github",
            config=config,
            auth_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
        )

    def is_configured(self) -> bool:
        """Check if GitHub OAuth2 is configured."""
        return bool(self.config.client_id and self.config.client_secret)

    def to_sso_user(self, token_data: dict[str, Any], user_data: dict[str, Any]) -> SSOUser:
        """GitHub-specific user mapping."""
        # GitHub user endpoint returns different field names
        emails = user_data.get("email", "")
        # If email is null, try fetching emails separately
        if not emails:
            import requests

            headers = {"Authorization": f"Bearer {token_data.get('access_token', '')}"}
            try:
                resp = requests.get("https://api.github.com/user/emails", headers=headers, timeout=10)
                if resp.status_code == 200:
                    email_list = resp.json()
                    primary = [e for e in email_list if e.get("primary")]
                    if primary:
                        emails = primary[0].get("email", "")
                    elif email_list:
                        emails = email_list[0].get("email", "")
            except Exception:
                pass

        return SSOUser(
            provider="github",
            provider_user_id=str(user_data.get("id", "")),
            email=emails,
            name=user_data.get("name", user_data.get("login", "")),
            avatar_url=user_data.get("avatar_url", ""),
            access_token=token_data.get("access_token", ""),
            raw_data=user_data,
            authenticated_at=time.time(),
        )


# ═══════════════════════════════════════
# SAML 2.0 Provider (Stub)
# ═══════════════════════════════════════


class SAMLProvider:
    """SAML 2.0 SSO provider (stub for enterprise).

    Full implementation requires xmlsec1 and python3-saml.
    This stub provides the interface and configuration validation.
    """

    def __init__(self, metadata_url: str = ""):
        self.metadata_url = metadata_url or os.environ.get("FORGEAI_SSO_SAML_METADATA_URL", "")
        self.entity_id = os.environ.get("FORGEAI_SSO_SAML_ENTITY_ID", "forgeai")
        self.acs_url = os.environ.get(
            "FORGEAI_SSO_SAML_ACS_URL",
            "http://localhost:7337/api/auth/sso/saml/callback",
        )

    def is_configured(self) -> bool:
        """Check if SAML is configured."""
        return bool(self.metadata_url)

    def get_auth_url(self) -> str:
        """Get the SAML login URL.

        In production, this would generate a SAML AuthnRequest
        and redirect to the IdP.
        """
        return f"/api/auth/sso/saml/login"

    def handle_response(self, saml_response: str) -> SSOUser:
        """Process a SAML response.

        In production, this would validate the SAML assertion,
        extract attributes, and return a normalized SSOUser.
        """
        return SSOUser(
            provider="saml",
            provider_user_id="saml-user",
            email="user@enterprise.com",
            name="SAML User",
            authenticated_at=time.time(),
        )


# ═══════════════════════════════════════
# OIDC Provider (Stub)
# ═══════════════════════════════════════


class OIDCProvider:
    """Generic OpenID Connect provider (stub for enterprise).

    Supports any OIDC-compliant IdP (Azure AD, Okta, Keycloak, etc.).
    Full implementation requires the `authlib` library.
    """

    def __init__(self):
        self.issuer_url = os.environ.get("FORGEAI_SSO_OIDC_ISSUER_URL", "")
        self.client_id = os.environ.get("FORGEAI_SSO_OIDC_CLIENT_ID", "")
        self.client_secret = os.environ.get("FORGEAI_SSO_OIDC_CLIENT_SECRET", "")
        self.redirect_uri = os.environ.get(
            "FORGEAI_SSO_OIDC_REDIRECT_URI",
            "http://localhost:7337/api/auth/sso/oidc/callback",
        )

    def is_configured(self) -> bool:
        """Check if OIDC is configured."""
        return bool(self.issuer_url and self.client_id and self.client_secret)

    def get_discovery_url(self) -> str:
        """Get the OIDC discovery URL."""
        return f"{self.issuer_url.rstrip('/')}/.well-known/openid-configuration"

    def get_auth_url(self) -> str:
        """Get the OIDC authorization URL.

        In production, this would use the discovery document to
        construct the authorization request with PKCE.
        """
        return f"/api/auth/sso/oidc/login"


# ═══════════════════════════════════════
# SSO Manager
# ═══════════════════════════════════════


class SSOManager:
    """Manages all SSO providers and session state."""

    def __init__(self):
        self.google = GoogleProvider()
        self.github = GitHubProvider()
        self.saml = SAMLProvider()
        self.oidc = OIDCProvider()
        # In-memory state store (in production, use Redis)
        self._states: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, SSOUser] = {}

    def get_available_providers(self) -> list[dict[str, Any]]:
        """List all configured SSO providers."""
        providers = []

        if self.google.is_configured():
            providers.append({
                "id": "google",
                "name": "Google",
                "icon": "google",
                "auth_url": self.google.get_auth_url(),
            })

        if self.github.is_configured():
            providers.append({
                "id": "github",
                "name": "GitHub",
                "icon": "github",
                "auth_url": self.github.get_auth_url(),
            })

        if self.saml.is_configured():
            providers.append({
                "id": "saml",
                "name": "SAML 2.0",
                "icon": "shield",
                "auth_url": self.saml.get_auth_url(),
            })

        if self.oidc.is_configured():
            providers.append({
                "id": "oidc",
                "name": "OIDC",
                "icon": "shield",
                "auth_url": self.oidc.get_auth_url(),
            })

        return providers

    def generate_state(self, provider: str) -> str:
        """Generate and store an OAuth2 state parameter."""
        state = uuid.uuid4().hex[:24]
        self._states[state] = {
            "provider": provider,
            "created_at": time.time(),
        }
        # Cleanup old states
        now = time.time()
        stale = [s for s, v in self._states.items() if now - v.get("created_at", 0) > 3600]
        for s in stale:
            self._states.pop(s, None)
        return state

    def validate_state(self, state: str, provider: str) -> bool:
        """Validate an OAuth2 state parameter (CSRF protection)."""
        stored = self._states.pop(state, None)
        if stored is None:
            return False
        if stored.get("provider") != provider:
            return False
        return True

    def handle_google_callback(self, code: str) -> SSOUser | None:
        """Handle Google OAuth2 callback."""
        try:
            token_data = self.google.exchange_code(code)
            access_token = token_data.get("access_token", "")
            user_data = self.google.fetch_userinfo(access_token)
            return self.google.to_sso_user(token_data, user_data)
        except Exception as e:
            import logging
            logging.getLogger("forgeai.auth.sso").error(f"Google SSO error: {e}")
            return None

    def handle_github_callback(self, code: str) -> SSOUser | None:
        """Handle GitHub OAuth2 callback."""
        try:
            token_data = self.github.exchange_code(code)
            access_token = token_data.get("access_token", "")
            user_data = self.github.fetch_userinfo(access_token)
            return self.github.to_sso_user(token_data, user_data)
        except Exception as e:
            import logging
            logging.getLogger("forgeai.auth.sso").error(f"GitHub SSO error: {e}")
            return None

    def create_session(self, user: SSOUser) -> str:
        """Create a session for an authenticated SSO user."""
        session_id = uuid.uuid4().hex[:32]
        self._sessions[session_id] = user
        return session_id

    def get_session(self, session_id: str) -> SSOUser | None:
        """Get an SSO session."""
        return self._sessions.get(session_id)

    def get_stats(self) -> dict[str, Any]:
        """Get SSO system statistics."""
        return {
            "providers_configured": len(self.get_available_providers()),
            "providers": [p["id"] for p in self.get_available_providers()],
            "active_sessions": len(self._sessions),
            "pending_states": len(self._states),
            "google_configured": self.google.is_configured(),
            "github_configured": self.github.is_configured(),
            "saml_configured": self.saml.is_configured(),
            "oidc_configured": self.oidc.is_configured(),
        }


# ── Singleton ────────────────────────────────────────────────────

_sso_manager: SSOManager | None = None


def get_sso_manager() -> SSOManager:
    """Get or create the global SSO manager."""
    global _sso_manager
    if _sso_manager is None:
        _sso_manager = SSOManager()
    return _sso_manager


__all__ = [
    "SSOManager",
    "SSOUser",
    "GoogleProvider",
    "GitHubProvider",
    "SAMLProvider",
    "OIDCProvider",
    "OAuth2Provider",
    "get_sso_manager",
]
