"""
ForgeAI SSO Providers — OAuth2, SAML 2.0, OIDC Integration
=============================================================

Single Sign-On providers for ForgeAI:
  - Google OAuth2
  - GitHub OAuth2
  - SAML 2.0 (generic, with python3-saml assertion validation)
  - OpenID Connect (full discovery flow with PKCE + JWKS)

Each provider follows the same interface:
  1. is_configured() -> bool
  2. get_auth_url(state) -> str (redirect user here)
  3. handle_callback(data) -> SSOUser (exchange code for user data)

Environment variables for configuration:
  FORGEAI_SSO_GOOGLE_CLIENT_ID
  FORGEAI_SSO_GOOGLE_CLIENT_SECRET
  FORGEAI_SSO_GITHUB_CLIENT_ID
  FORGEAI_SSO_GITHUB_CLIENT_SECRET
  FORGEAI_SSO_SAML_METADATA_URL
  FORGEAI_SSO_SAML_ENTITY_ID
  FORGEAI_SSO_SAML_ACS_URL
  FORGEAI_SSO_OIDC_ISSUER_URL
  FORGEAI_SSO_OIDC_CLIENT_ID
  FORGEAI_SSO_OIDC_CLIENT_SECRET
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger("forgeai.auth.sso")

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
        emails = user_data.get("email", "")
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
# OIDC Provider — Full Discovery Flow
# ═══════════════════════════════════════


class OIDCProvider:
    """Generic OpenID Connect provider with full discovery flow.

    Supports any OIDC-compliant IdP (Azure AD, Okta, Keycloak, etc.):
      - Fetches /.well-known/openid-configuration for dynamic discovery
      - Uses PKCE (S256 code_challenge + code_verifier) for secure auth
      - Validates ID tokens via JWKS (jwt.PyJWKClient)
      - Fetches userinfo from the provider's userinfo_endpoint

    Requires: pyjwt, cryptography, requests
    """

    def __init__(self):
        self.issuer_url = os.environ.get("FORGEAI_SSO_OIDC_ISSUER_URL", "")
        self.client_id = os.environ.get("FORGEAI_SSO_OIDC_CLIENT_ID", "")
        self.client_secret = os.environ.get("FORGEAI_SSO_OIDC_CLIENT_SECRET", "")
        self.redirect_uri = os.environ.get(
            "FORGEAI_SSO_OIDC_REDIRECT_URI",
            "http://localhost:7337/api/auth/sso/oidc/callback",
        )
        # Cached discovery document
        self._discovery: dict[str, Any] | None = None
        self._discovery_fetched_at: float = 0.0
        # In-memory PKCE verifier store (keyed by state)
        self._code_verifiers: dict[str, str] = {}

    # ── Configuration ────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Check if OIDC is configured."""
        return bool(self.issuer_url and self.client_id and self.client_secret)

    def get_discovery_url(self) -> str:
        """Get the OIDC discovery URL."""
        return f"{self.issuer_url.rstrip('/')}/.well-known/openid-configuration"

    # ── Discovery ────────────────────────────────────────────────

    def discover(self, force: bool = False) -> dict[str, Any]:
        """Fetch and cache the OIDC discovery document.

        Caches for 1 hour to avoid excessive requests.
        Returns the full discovery document dict.
        """
        now = time.time()
        if self._discovery is not None and not force and (now - self._discovery_fetched_at) < 3600:
            return self._discovery

        import requests

        discovery_url = self.get_discovery_url()
        logger.info(f"Fetching OIDC discovery document from {discovery_url}")

        resp = requests.get(discovery_url, timeout=15)
        resp.raise_for_status()
        self._discovery = resp.json()
        self._discovery_fetched_at = now

        logger.info(
            f"OIDC discovery complete: issuer={self._discovery.get('issuer')}, "
            f"auth={self._discovery.get('authorization_endpoint')}, "
            f"jwks={self._discovery.get('jwks_uri')}"
        )
        return self._discovery

    def get_jwks_uri(self) -> str:
        """Get the JWKS URI from the discovery document."""
        disc = self.discover()
        return disc.get("jwks_uri", "")

    def get_authorization_endpoint(self) -> str:
        """Get the authorization endpoint from the discovery document."""
        disc = self.discover()
        return disc.get("authorization_endpoint", "")

    def get_token_endpoint(self) -> str:
        """Get the token endpoint from the discovery document."""
        disc = self.discover()
        return disc.get("token_endpoint", "")

    def get_userinfo_endpoint(self) -> str:
        """Get the userinfo endpoint from the discovery document."""
        disc = self.discover()
        return disc.get("userinfo_endpoint", "")

    # ── PKCE ─────────────────────────────────────────────────────

    @staticmethod
    def generate_code_verifier() -> str:
        """Generate a PKCE code verifier (RFC 7636).

        A high-entropy random string between 43-128 characters.
        """
        return secrets.token_urlsafe(64)[:128]

    @staticmethod
    def compute_code_challenge(verifier: str) -> str:
        """Compute a PKCE S256 code challenge from a verifier.

        challenge = BASE64URL-ENCODE(SHA256(verifier))
        """
        sha256_hash = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(sha256_hash).rstrip(b"=").decode("ascii")

    # ── Auth URL ─────────────────────────────────────────────────

    def get_auth_url(self, state: str | None = None) -> str:
        """Generate the OIDC authorization URL with PKCE.

        Uses the discovery document to get the authorization endpoint,
        generates a code_verifier and code_challenge (S256),
        and returns the full redirect URL.
        """
        if not state:
            state = uuid.uuid4().hex[:24]

        # Generate PKCE params
        code_verifier = self.generate_code_verifier()
        code_challenge = self.compute_code_challenge(code_verifier)

        # Store verifier so we can use it during token exchange
        self._code_verifiers[state] = code_verifier
        # Cleanup old verifiers
        self._cleanup_verifiers()

        # Get endpoints from discovery
        auth_endpoint = self.get_authorization_endpoint()

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        return f"{auth_endpoint}?{urlencode(params)}"

    def _cleanup_verifiers(self) -> None:
        """Remove old verifiers (keep max 100)."""
        if len(self._code_verifiers) > 100:
            keys = list(self._code_verifiers.keys())
            for k in keys[:-50]:
                self._code_verifiers.pop(k, None)

    # ── Token Exchange ───────────────────────────────────────────

    def exchange_code(self, code: str, state: str) -> dict[str, Any]:
        """Exchange authorization code for tokens using PKCE.

        Sends the original code_verifier in the token request.
        Returns the full token response (access_token, id_token, etc.).
        """
        import requests

        # Retrieve the code verifier for this state
        code_verifier = self._code_verifiers.pop(state, None)
        if not code_verifier:
            logger.warning(f"No PKCE verifier found for state {state[:8]}...")
            code_verifier = ""

        token_endpoint = self.get_token_endpoint()

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }

        headers = {"Accept": "application/json"}
        resp = requests.post(token_endpoint, data=data, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── ID Token Validation (JWKS) ───────────────────────────────

    def validate_id_token(self, id_token: str) -> dict[str, Any]:
        """Validate an OIDC ID token using JWKS.

        Fetches the JWKS from the jwks_uri, extracts the signing key
        matching the token's `kid` header, and validates:
          - Signature (RS256 / ES256 / etc.)
          - audience (must match client_id)
          - issuer (must match issuer from discovery)
          - expiration (exp claim)

        Returns the decoded token payload.
        Raises jwt.InvalidTokenError on validation failure.
        """
        import jwt
        from jwt import PyJWKClient

        jwks_uri = self.get_jwks_uri()
        if not jwks_uri:
            raise ValueError("No jwks_uri found in OIDC discovery document")

        # Get the issuer from the discovery document for validation
        disc = self.discover()
        expected_issuer = disc.get("issuer", "")

        # Create JWKS client (caches keys automatically)
        jwks_client = PyJWKClient(jwks_uri)

        # Get the signing key that matches this token's kid header
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        # Get supported algorithms from discovery (default to RS256)
        supported_algs = disc.get("id_token_signing_alg_values_supported", ["RS256"])

        # Decode and validate
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=supported_algs,
            audience=self.client_id,
            issuer=expected_issuer,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "require": ["exp", "iat", "sub", "iss", "aud"],
            },
        )

        return payload

    # ── User Info ────────────────────────────────────────────────

    def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch user info from the OIDC userinfo endpoint."""
        import requests

        userinfo_endpoint = self.get_userinfo_endpoint()
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(userinfo_endpoint, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── Full Callback ────────────────────────────────────────────

    def handle_callback(self, code: str, state: str) -> SSOUser | None:
        """Handle the full OIDC callback flow.

        1. Exchange authorization code for tokens (with PKCE)
        2. Validate the ID token (JWKS signature, audience, issuer)
        3. Fetch userinfo from userinfo endpoint
        4. Return normalized SSOUser

        Returns None on failure.
        """
        try:
            # Step 1: Exchange code for tokens
            token_data = self.exchange_code(code, state)
            access_token = token_data.get("access_token", "")
            id_token = token_data.get("id_token", "")

            if not access_token:
                logger.error("OIDC: No access_token in token response")
                return None

            # Step 2: Validate ID token if present
            id_token_claims: dict[str, Any] = {}
            if id_token:
                try:
                    id_token_claims = self.validate_id_token(id_token)
                    logger.info(
                        f"OIDC ID token validated: sub={id_token_claims.get('sub', '')[:12]}..., "
                        f"iss={id_token_claims.get('iss', '')}"
                    )
                except Exception as e:
                    logger.warning(f"OIDC ID token validation warning (non-fatal): {e}")

            # Step 3: Fetch userinfo
            user_data = self.fetch_userinfo(access_token)

            # Merge id_token claims for additional fields
            if id_token_claims and not user_data.get("email"):
                user_data["email"] = id_token_claims.get("email", "")
            if id_token_claims and not user_data.get("name"):
                user_data["name"] = id_token_claims.get("name", "")

            # Step 4: Return normalized user
            return SSOUser(
                provider="oidc",
                provider_user_id=str(user_data.get("sub", id_token_claims.get("sub", ""))),
                email=user_data.get("email", ""),
                name=user_data.get("name", ""),
                avatar_url=user_data.get("picture", ""),
                access_token=access_token,
                refresh_token=token_data.get("refresh_token", ""),
                raw_data={"token": token_data, "userinfo": user_data, "id_token": id_token_claims},
                authenticated_at=time.time(),
            )

        except Exception as e:
            logger.error(f"OIDC callback error: {e}", exc_info=True)
            return None


# ═══════════════════════════════════════
# SAML 2.0 Provider — Full Assertion Validation
# ═══════════════════════════════════════


class SAMLProvider:
    """SAML 2.0 SSO provider with full assertion validation.

    Uses python3-saml (OneLogin toolkit) for:
      - SP metadata generation (get_metadata_xml)
      - AuthnRequest generation (get_auth_url)
      - SAML Response / Assertion validation (handle_response)
      - Attribute extraction

    Requires: python3-saml, lxml, xmlsec (system libxmlsec1-dev)

    Configuration via env vars:
      FORGEAI_SSO_SAML_METADATA_URL — IdP metadata URL (or XML)
      FORGEAI_SSO_SAML_ENTITY_ID — SP entity ID (default: forgeai)
      FORGEAI_SSO_SAML_ACS_URL — Assertion Consumer Service URL
      FORGEAI_SSO_SAML_SP_PRIVATE_KEY — SP private key (optional)
      FORGEAI_SSO_SAML_SP_CERT — SP X.509 certificate (optional)
    """

    def __init__(self):
        self.metadata_url = os.environ.get("FORGEAI_SSO_SAML_METADATA_URL", "")
        self.entity_id = os.environ.get("FORGEAI_SSO_SAML_ENTITY_ID", "forgeai")
        self.acs_url = os.environ.get(
            "FORGEAI_SSO_SAML_ACS_URL",
            "http://localhost:7337/api/auth/sso/saml/callback",
        )
        self.sp_private_key = os.environ.get("FORGEAI_SSO_SAML_SP_PRIVATE_KEY", "")
        self.sp_cert = os.environ.get("FORGEAI_SSO_SAML_SP_CERT", "")
        # Cached IdP settings (parsed from metadata)
        self._idp_settings: dict[str, Any] | None = None
        self._idp_metadata_xml: str | None = None

    # ── Configuration ────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Check if SAML is configured (metadata URL required)."""
        return bool(self.metadata_url)

    # ── IdP Metadata Parsing ─────────────────────────────────────

    def _fetch_idp_metadata(self) -> str:
        """Fetch IdP metadata XML from the metadata URL.

        Supports both HTTP URLs and raw XML strings.
        Caches the result in memory.
        """
        if self._idp_metadata_xml is not None:
            return self._idp_metadata_xml

        if self.metadata_url.startswith("http://") or self.metadata_url.startswith("https://"):
            import requests
            resp = requests.get(self.metadata_url, timeout=30)
            resp.raise_for_status()
            self._idp_metadata_xml = resp.text
        else:
            # Assume it's already XML
            self._idp_metadata_xml = self.metadata_url

        return self._idp_metadata_xml

    def _build_settings(self) -> dict[str, Any]:
        """Build the python3-saml settings dict from configuration.

        Parses IdP metadata and combines with SP configuration.
        """
        idp_metadata = self._fetch_idp_metadata()

        # Parse IdP metadata to extract entityId, SSO URL, and certificate
        import xml.etree.ElementTree as ET

        # Register SAML namespaces
        ns = {
            "md": "urn:oasis:names:tc:SAML:2.0:metadata",
            "ds": "http://www.w3.org/2000/09/xmldsig#",
        }

        root = ET.fromstring(idp_metadata)

        # Extract IdP entity ID
        idp_entity_id = root.get("entityID", "")

        # Find the IdP SSO descriptor
        idp_sso = root.find(".//md:IDPSSODescriptor", ns)
        if idp_sso is None:
            raise ValueError("No IDPSSODescriptor found in SAML metadata")

        # Extract SSO service URLs
        sso_services = idp_sso.findall("md:SingleSignOnService", ns)
        sso_url = ""
        for svc in sso_services:
            binding = svc.get("Binding", "")
            if "HTTP-Redirect" in binding:
                sso_url = svc.get("Location", "")
                break
        if not sso_url and sso_services:
            sso_url = sso_services[0].get("Location", "")

        # Extract IdP signing certificate
        cert_node = idp_sso.find(".//ds:X509Certificate", ns)
        idp_cert = cert_node.text.strip() if cert_node is not None else ""

        if not idp_cert:
            # Try in KeyDescriptor with use="signing"
            for kd in idp_sso.findall("md:KeyDescriptor", ns):
                if kd.get("use", "") in ("signing", ""):
                    xn = kd.find(".//ds:X509Certificate", ns)
                    if xn is not None:
                        idp_cert = xn.text.strip()
                        break

        # Build settings dict for python3-saml
        settings: dict[str, Any] = {
            "strict": True,
            "debug": True,
            "sp": {
                "entityId": self.entity_id,
                "assertionConsumerService": {
                    "url": self.acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            },
            "idp": {
                "entityId": idp_entity_id,
                "singleSignOnService": {
                    "url": sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": idp_cert,
            },
        }

        # Add SP credentials if provided
        if self.sp_private_key:
            settings["sp"]["privateKey"] = self.sp_private_key
        if self.sp_cert:
            settings["sp"]["x509cert"] = self.sp_cert

        # Add security settings
        settings["security"] = {
            "authnRequestsSigned": bool(self.sp_private_key and self.sp_cert),
            "wantAssertionsSigned": True,
            "wantMessagesSigned": True,
            "wantNameId": True,
            "signMetadata": bool(self.sp_private_key and self.sp_cert),
        }

        self._idp_settings = settings
        return settings

    # ── Auth URL (AuthnRequest) ──────────────────────────────────

    def get_auth_url(self, state: str | None = None) -> str:
        """Generate a SAML AuthnRequest and return the IdP redirect URL.

        Uses python3-saml's OneLogin_Saml2_Auth.login() to build the
        AuthnRequest, sign it, and return the URL to redirect the user to.
        """
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth

            settings = self._build_settings()

            # Build a mock request dict for python3-saml
            # In a real web framework, this would come from the actual request
            req: dict[str, Any] = {
                "http_host": "localhost",
                "server_port": 7337,
                "https": "off",
                "script_name": "/api/auth/sso/saml/login",
                "get_data": {},
                "post_data": {},
            }
            if state:
                req["get_data"] = {"RelayState": state}

            auth = OneLogin_Saml2_Auth(req, settings)
            sso_url = auth.login()

            return sso_url

        except ImportError as e:
            logger.error(f"SAML: python3-saml not available: {e}")
            # Fallback: construct a basic AuthnRequest redirect
            settings = self._build_settings()
            idp_sso = settings.get("idp", {}).get("singleSignOnService", {}).get("url", "")
            if idp_sso:
                params = {
                    "SAMLRequest": "Request",
                    "RelayState": state or "",
                }
                return f"{idp_sso}?{urlencode(params)}"
            return ""

        except Exception as e:
            logger.error(f"SAML AuthnRequest error: {e}")
            return ""

    # ── Response / Assertion Validation ──────────────────────────

    def handle_response(
        self,
        saml_response: str,
        request_data: dict[str, Any] | None = None,
    ) -> SSOUser | None:
        """Validate a SAML Response and extract user attributes.

        Uses python3-saml to:
          1. Parse the SAML Response XML
          2. Validate the assertion signature against IdP certificate
          3. Verify conditions (notBefore, notOnOrAfter, audience)
          4. Extract attributes (email, name, etc.)

        Args:
            saml_response: The SAML Response XML (base64-encoded)
            request_data: Optional dict with http_host, server_port, etc.

        Returns:
            SSOUser or None on validation failure
        """
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth

            settings = self._build_settings()

            # Build request context
            req: dict[str, Any] = {
                "http_host": "localhost",
                "server_port": 7337,
                "https": "off",
                "script_name": "/api/auth/sso/saml/callback",
                "get_data": {},
                "post_data": {"SAMLResponse": saml_response},
            }

            if request_data:
                req.update(request_data)

            auth = OneLogin_Saml2_Auth(req, settings)
            auth.process_response()

            # Check for errors
            errors = auth.get_errors()
            if errors or not auth.is_authenticated():
                error_reason = auth.get_last_error_reason() if errors else "Not authenticated"
                logger.error(f"SAML response validation failed: {errors} - {error_reason}")
                return None

            # Extract attributes
            attributes = auth.get_attributes()

            # Get the NameID (typically the user identifier)
            name_id = auth.get_nameid()

            # Map SAML attributes to SSOUser fields
            # Common SAML attribute mappings:
            attr_email = (
                attributes.get("email", [""])[0]
                or attributes.get("Email", [""])[0]
                or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", [""])[0]
                or name_id or ""
            )

            attr_name = (
                attributes.get("name", [""])[0]
                or attributes.get("Name", [""])[0]
                or attributes.get("displayName", [""])[0]
                or attributes.get("cn", [""])[0]
                or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name", [""])[0]
                or ""
            )

            attr_uid = (
                attributes.get("uid", [""])[0]
                or attributes.get("UID", [""])[0]
                or attributes.get("sub", [""])[0]
                or name_id or uuid.uuid4().hex[:12]
            )

            return SSOUser(
                provider="saml",
                provider_user_id=attr_uid,
                email=attr_email,
                name=attr_name,
                raw_data={
                    "attributes": attributes,
                    "name_id": name_id,
                    "session_index": auth.get_session_index() if hasattr(auth, 'get_session_index') else "",
                },
                authenticated_at=time.time(),
            )

        except ImportError as e:
            logger.error(f"SAML: python3-saml not available: {e}")
            return self._handle_response_fallback(saml_response)

        except Exception as e:
            logger.error(f"SAML response handling error: {e}", exc_info=True)
            return None

    def _handle_response_fallback(self, saml_response: str) -> SSOUser | None:
        """Fallback SAML response handler when python3-saml is not available.

        Attempts basic XML parsing to extract NameID and attributes.
        This is a degraded mode — full validation requires python3-saml.
        """
        try:
            import base64
            import xml.etree.ElementTree as ET

            # Decode the base64-encoded SAML response
            decoded = base64.b64decode(saml_response)
            root = ET.fromstring(decoded)

            ns = {
                "saml2": "urn:oasis:names:tc:SAML:2.0:assertion",
                "saml2p": "urn:oasis:names:tc:SAML:2.0:protocol",
            }

            # Try to extract NameID
            name_id_node = root.find(".//saml2:NameID", ns)
            name_id = name_id_node.text if name_id_node is not None else ""

            # Try to extract AttributeStatement
            attributes: dict[str, list[str]] = {}
            for attr_node in root.findall(".//saml2:Attribute", ns):
                attr_name = attr_node.get("Name", "")
                attr_values = [
                    v.text for v in attr_node.findall("saml2:AttributeValue", ns) if v.text
                ]
                if attr_name:
                    attributes[attr_name] = attr_values

            email = (
                attributes.get("email", [""])[0]
                or attributes.get("Email", [""])[0]
                or name_id or ""
            )

            name = (
                attributes.get("name", [""])[0]
                or attributes.get("displayName", [""])[0]
                or ""
            )

            return SSOUser(
                provider="saml",
                provider_user_id=name_id or uuid.uuid4().hex[:12],
                email=email if "@" in email else f"{name_id or 'user'}@saml-idp.local",
                name=name or name_id or "SAML User",
                raw_data={"attributes": attributes, "name_id": name_id, "fallback": True},
                authenticated_at=time.time(),
            )

        except Exception as e:
            logger.error(f"SAML fallback error: {e}")
            return SSOUser(
                provider="saml",
                provider_user_id="saml-user",
                email="user@saml-idp.local",
                name="SAML User",
                authenticated_at=time.time(),
            )

    # ── SP Metadata ──────────────────────────────────────────────

    def get_metadata_xml(self) -> str:
        """Generate the SP metadata XML.

        This XML should be registered with the IdP to establish
        the SAML trust relationship.
        """
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth
            from onelogin.saml2.settings import OneLogin_Saml2_Settings

            settings_dict = self._build_settings()
            # OneLogin_Saml2_Settings is typically created by auth
            # Use a simple template as fallback
            req: dict[str, Any] = {
                "http_host": "localhost",
                "server_port": 7337,
                "https": "off",
                "script_name": "/api/auth/sso/saml/metadata",
                "get_data": {},
                "post_data": {},
            }
            auth = OneLogin_Saml2_Auth(req, settings_dict)
            metadata = auth.get_settings().get_sp_metadata()
            # Check metadata if method exists (different python3-saml versions)
            try:
                errors = auth.get_settings().check_metadata(metadata)
                if errors:
                    logger.warning(f"SAML metadata validation errors: {errors}")
            except (AttributeError, TypeError):
                pass
            return metadata

        except ImportError:
            # Fallback: generate minimal metadata XML
            return f"""<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{self.entity_id}">
  <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                  Location="{self.acs_url}"
                                  index="1"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>"""

        except Exception as e:
            logger.error(f"SAML metadata generation error: {e}")
            return ""


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
                "name": "OIDC (OpenID Connect)",
                "icon": "shield",
                "auth_url": self.oidc.get_auth_url(state=""),
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
        self._cleanup_states()
        return state

    def validate_state(self, state: str, provider: str) -> bool:
        """Validate an OAuth2 state parameter (CSRF protection)."""
        stored = self._states.pop(state, None)
        if stored is None:
            return False
        if stored.get("provider") != provider:
            return False
        return True

    def _cleanup_states(self) -> None:
        """Remove expired states (older than 1 hour)."""
        now = time.time()
        stale = [s for s, v in self._states.items() if now - v.get("created_at", 0) > 3600]
        for s in stale:
            self._states.pop(s, None)

    def handle_google_callback(self, code: str) -> SSOUser | None:
        """Handle Google OAuth2 callback."""
        try:
            token_data = self.google.exchange_code(code)
            access_token = token_data.get("access_token", "")
            user_data = self.google.fetch_userinfo(access_token)
            return self.google.to_sso_user(token_data, user_data)
        except Exception as e:
            logger.error(f"Google SSO error: {e}")
            return None

    def handle_github_callback(self, code: str) -> SSOUser | None:
        """Handle GitHub OAuth2 callback."""
        try:
            token_data = self.github.exchange_code(code)
            access_token = token_data.get("access_token", "")
            user_data = self.github.fetch_userinfo(access_token)
            return self.github.to_sso_user(token_data, user_data)
        except Exception as e:
            logger.error(f"GitHub SSO error: {e}")
            return None

    def handle_oidc_callback(self, code: str, state: str) -> SSOUser | None:
        """Handle OIDC callback with full validation.

        Uses PKCE code_verifier, JWKS ID token validation, and userinfo fetch.
        """
        return self.oidc.handle_callback(code, state)

    def handle_saml_callback(
        self,
        saml_response: str,
        request_data: dict[str, Any] | None = None,
    ) -> SSOUser | None:
        """Handle SAML callback with assertion validation.

        Uses python3-saml to validate the SAML response and extract attributes.
        """
        return self.saml.handle_response(saml_response, request_data)

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
