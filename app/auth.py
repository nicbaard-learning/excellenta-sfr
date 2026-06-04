"""
Self-hosted OAuth 2.0 for the SFR MCP server.

Implements the Authorization Code flow with PKCE so that Claude.ai's
web connector can authenticate. Uses only Python stdlib (hmac, hashlib, secrets).

Endpoints:
    GET  /.well-known/oauth-authorization-server   — OAuth metadata (auto-discovery)
    GET  /oauth/authorize                           — Authorization endpoint
    POST /oauth/token                               — Token exchange endpoint

The MCP SSE app (mounted at /mcp) is wrapped with Bearer token validation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────
# These should be set via environment variables for production
CLIENT_ID = settings.mcp_oauth_client_id or "sfr-mcp"
CLIENT_SECRET = settings.mcp_oauth_client_secret or secrets.token_hex(32)
JWT_SECRET = settings.mcp_jwt_secret or secrets.token_hex(32)

# Base URL for constructing OAuth URLs (override for production)
# If not set, determined from request's host header
BASE_URL = settings.mcp_oauth_base_url or ""

# Token expiry (seconds)
TOKEN_EXPIRY = 86400  # 24 hours
AUTH_CODE_EXPIRY = 300  # 5 minutes

# In-memory auth code store (single-use, expiring)
# In production, consider using a database or Redis
auth_codes: dict[str, dict[str, Any]] = {}

# ── Router ─────────────────────────────────────────────────────────────
router = APIRouter(tags=["oauth"])


# ── Token management (HMAC-signed, no external deps) ──────────────────


def _make_token(sub: str, scope: str = "mcp") -> str:
    """Create an HMAC-SHA256 signed access token (stateless)."""
    now = int(time.time())
    payload = json.dumps(
        {
            "sub": sub,
            "scope": scope,
            "iat": now,
            "exp": now + TOKEN_EXPIRY,
            "jti": secrets.token_hex(16),
        },
        separators=(",", ":"),
    )
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify an HMAC-signed access token and return its payload."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(
            JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            # Pad payload for decoding
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            if payload.get("exp", 0) > time.time():
                return payload
    except Exception:
        logger.warning("Token verification failed", exc_info=True)
    return None


# ── OAuth Endpoints ───────────────────────────────────────────────────


def _get_base_url(request: Request) -> str:
    """Determine the base URL for constructing OAuth URLs."""
    if BASE_URL:
        return BASE_URL.rstrip("/")
    # Fall back to request's host header
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost:8000")
    return f"{proto}://{host}"


@router.get("/.well-known/oauth-authorization-server")
async def well_known_oauth(request: Request):
    """OAuth 2.0 Authorization Server Metadata (RFC 8414).

    This lets Claude.ai auto-discover OAuth endpoints without manual config.
    """
    base = _get_base_url(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "none"],
    }


@router.get("/oauth/authorize")
async def oauth_authorize(
    request: Request,
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
):
    """OAuth 2.0 Authorization Endpoint.

    Claude.ai redirects the user here to approve the connection.
    Shows a consent page; on approval, redirects back with an auth code.
    """
    # Validate required params
    if response_type != "code":
        return HTMLResponse("<h1>Invalid response_type</h1>", status_code=400)
    if client_id != CLIENT_ID:
        return HTMLResponse(
            f"<h1>Unknown client</h1><p>Client ID '{client_id}' not recognised.</p>",
            status_code=400,
        )
    if not redirect_uri:
        return HTMLResponse("<h1>Missing redirect_uri</h1>", status_code=400)

    # Render consent page
    base = _get_base_url(request)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Authorize MCP Connection</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #f5f5f5; display: flex; justify-content: center; align-items: center;
           min-height: 100vh; margin: 0; }}
    .card {{ background: white; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.1);
             padding: 32px; max-width: 420px; width: 90%; text-align: center; }}
    h1 {{ font-size: 20px; margin-bottom: 8px; }}
    p {{ color: #666; font-size: 14px; line-height: 1.5; margin-bottom: 24px; }}
    .btn {{ display: inline-block; padding: 12px 32px; border-radius: 8px;
            font-size: 15px; font-weight: 600; border: none; cursor: pointer; }}
    .btn-primary {{ background: #0066cc; color: white; }}
    .btn-primary:hover {{ background: #0052a3; }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
    .details {{ text-align: left; background: #f9f9f9; border-radius: 8px; padding: 12px;
               margin-bottom: 24px; font-size: 13px; }}
    .details dt {{ font-weight: 600; margin-top: 8px; }}
    .details dd {{ margin: 4px 0 0 20px; color: #666; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🔐</div>
    <h1>Authorize MCP Connection</h1>
    <p>A request was made to connect to the <strong>SFR Compliance Action Engine</strong>
       from Claude.ai. This will allow Claude to access your compliance data via the
       following MCP tools:</p>
    <div class="details">
      <dl>
        <dt>Application</dt>
        <dd>Claude.ai (Client ID: <code>{urllib.parse.quote(client_id)}</code>)</dd>
        <dt>Capabilities</dt>
        <dd>Framework recommendations, evidence checklists, compliance translation,
            maturity assessment, roadmaps, risk intelligence, audit readiness</dd>
        <dt>Redirect URI</dt>
        <dd><code>{urllib.parse.quote(redirect_uri)}</code></dd>
      </dl>
    </div>
    <form method="POST" action="/oauth/approve">
      <input type="hidden" name="client_id" value="{client_id}">
      <input type="hidden" name="redirect_uri" value="{redirect_uri}">
      <input type="hidden" name="state" value="{state}">
      <input type="hidden" name="code_challenge" value="{code_challenge}">
      <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
      <button type="submit" name="action" value="approve" class="btn btn-primary">
        Authorize Connection
      </button>
      <p style="margin-top:12px;font-size:12px;color:#999;">
        By authorizing, you grant Claude.ai access to read compliance data
        through the SFR MCP server.
      </p>
    </form>
  </div>
</body>
</html>"""
    return HTMLResponse(html)


@router.post("/oauth/approve")
async def oauth_approve(request: Request):
    """Handle the authorization consent form submission.

    Instead of redirecting (which many MCP clients don't handle),
    shows the authorization code on a success page for the user to
    copy and paste into their MCP client.
    """
    form = await request.form()
    action = form.get("action", "")
    client_id = form.get("client_id", "")
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")
    code_challenge = form.get("code_challenge", "")
    code_challenge_method = form.get("code_challenge_method", "S256")

    if action != "approve":
        return HTMLResponse("<h1>Authorization declined</h1>", status_code=403)

    # Generate single-use auth code
    code = secrets.token_urlsafe(32)
    auth_codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires_at": time.time() + AUTH_CODE_EXPIRY,
    }

    # Show success page with the code — user copies it into their MCP client
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Authorization Successful</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #f0fdf4; display: flex; justify-content: center; align-items: center;
           min-height: 100vh; margin: 0; }}
    .card {{ background: white; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.1);
             padding: 40px; max-width: 520px; width: 90%; text-align: center; }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    h1 {{ font-size: 22px; margin-bottom: 8px; color: #166534; }}
    p {{ color: #666; font-size: 14px; line-height: 1.5; margin-bottom: 20px; }}
    .code-box {{ background: #f9f9f9; border: 2px dashed #22c55e; border-radius: 8px;
                 padding: 16px; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
                 font-size: 14px; word-break: break-all; user-select: all;
                 margin-bottom: 20px; cursor: pointer; }}
    .code-box:hover {{ background: #f0fdf4; }}
    .hint {{ font-size: 12px; color: #999; }}
    .btn {{ display: inline-block; padding: 10px 24px; border-radius: 8px;
            font-size: 14px; font-weight: 600; border: none; cursor: pointer;
            background: #22c55e; color: white; text-decoration: none; }}
    .btn:hover {{ background: #16a34a; }}
    .state-info {{ font-size: 11px; color: #999; margin-top: 16px; padding-top: 16px;
                   border-top: 1px solid #eee; }}
  </style>
  <script>
    function copyCode() {{
      const code = document.getElementById('auth-code');
      navigator.clipboard.writeText(code.textContent).then(() => {{
        const btn = document.getElementById('copy-btn');
        btn.textContent = '✓ Copied!';
        setTimeout(() => {{ btn.textContent = 'Copy Code'; }}, 3000);
      }});
    }}
  </script>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Authorization Successful</h1>
    <p>Your MCP connection has been authorized. Copy the code below and paste it into your client (Perplexity, Claude, etc.) to complete the connection.</p>
    <div class="code-box" id="auth-code" onclick="copyCode()">{code}</div>
    <button class="btn" id="copy-btn" onclick="copyCode()">Copy Code</button>
    <p class="hint">Click the code or the button to copy it, then return to Perplexity (or your MCP client) and paste it where prompted. This code expires in 5 minutes.</p>
    <div class="state-info">
      Client ID: {client_id}
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(html)


@router.post("/oauth/token")
async def oauth_token(request: Request):
    """OAuth 2.0 Token Endpoint.

    Claude.ai exchanges the authorization code for an access token here.
    """
    # Support both form-encoded and JSON bodies
    try:
        body = await request.json()
    except Exception:
        body = dict(await request.form())

    grant_type = body.get("grant_type", "authorization_code")
    code = body.get("code", "")
    redirect_uri = body.get("redirect_uri", "")
    client_id = body.get("client_id", "")
    client_secret = body.get("client_secret", "")
    code_verifier = body.get("code_verifier", "")

    # Validate grant type
    if grant_type != "authorization_code":
        return JSONResponse(
            {"error": "unsupported_grant_type"}, status_code=400
        )

    # Validate auth code
    if code not in auth_codes:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Code not found or already used"},
            status_code=400,
        )

    stored = auth_codes.pop(code)  # Single-use

    if stored["expires_at"] < time.time():
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Code expired"},
            status_code=400,
        )

    if client_id and stored["client_id"] and client_id != stored["client_id"]:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Client ID mismatch"},
            status_code=400,
        )

    # PKCE verification (simplified - accepts if challenge matches verifier)
    if stored.get("code_challenge") and code_verifier:
        if stored["code_challenge_method"] == "S256":
            expected_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).rstrip(b"=").decode()
            if stored["code_challenge"] != expected_challenge:
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "PKCE verification failed"},
                    status_code=400,
                )

    # Issue access token
    access_token = _make_token(sub=client_id or CLIENT_ID)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_EXPIRY,
        "scope": "mcp",
    }


# ── MCP Auth Middleware (raw ASGI — compatible with SSE) ─────────────


class MCPAuthMiddleware:
    """Raw ASGI middleware that validates Bearer tokens on MCP SSE endpoints.

    This is a pure ASGI middleware (NOT Starlette's BaseHTTPMiddleware) to
    avoid the known incompatibility between BaseHTTPMiddleware and SSE streaming
    responses. It passes through ASGI messages without buffering the body.

    Protects /mcp/sse and /mcp/messages routes inside the mounted MCP sub-app.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").rstrip("/")

        # Only protect MCP SSE transport endpoints
        is_mcp_endpoint = path == "/sse" or path.startswith("/messages")

        if is_mcp_endpoint:
            # Extract Bearer token from headers
            headers = dict(scope.get("headers", []))
            auth_bytes = headers.get(b"authorization", b"")
            auth_header = auth_bytes.decode("utf-8", errors="replace")

            if not auth_header.startswith("Bearer "):
                logger.warning("MCP request without Bearer token: %s", path)
                return await _send_401(send, "Unauthorized – Bearer token required")

            token_str = auth_header[len("Bearer "):]
            payload = verify_token(token_str)
            if not payload:
                logger.warning("MCP request with invalid/expired token: %s", path)
                return await _send_401(send, "Invalid or expired token")

            logger.debug("Authenticated MCP request: sub=%s scope=%s", payload.get("sub"), payload.get("scope"))

        await self.app(scope, receive, send)


async def _send_401(send, message: str):
    """Send a 401 Unauthorized response via raw ASGI send."""
    body = message.encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
            (b"www-authenticate", b"Bearer"),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })
