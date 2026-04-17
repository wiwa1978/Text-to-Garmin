"""GitHub OAuth authentication for the web app.

Design goals:

* Zero persistent state. The signed session cookie holds the authenticated
  GitHub username; no database, no token storage.
* Username allowlist. Only logins listed in ``ALLOWED_GITHUB_USERS`` may
  use the app, so a leaked/guessable state parameter is never enough on
  its own to gain access.
* Dev-mode bypass. When ``GITHUB_OAUTH_CLIENT_ID`` is unset the middleware
  logs a loud warning and treats every request as authenticated. This
  keeps the uvicorn + ``vite dev`` workflow friction-free.
* No scopes requested. The app only needs the caller's GitHub login, so
  the OAuth flow asks for ``scope=`` (empty). This means we see public
  profile info only — nothing about private repos, emails, orgs, etc.

Endpoints installed by :func:`install_auth`:

* ``GET  /api/auth/me``         — 200 ``{authenticated, username, avatar}``
                                  or 401 ``{authenticated: false}``
* ``GET  /api/auth/login``      — 302 to GitHub's authorize URL
* ``GET  /api/auth/callback``   — exchanges ?code, sets cookie, 302 to /
* ``POST /api/auth/logout``     — clears the session cookie, 204

The middleware protects every path except ``/api/auth/*``,
``/api/health``, and static files (``/``, ``/assets/*``, favicons, …).
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (read from env vars — see README "Enable GitHub sign-in")
# ---------------------------------------------------------------------------

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

SESSION_COOKIE = "t2g_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days

# Paths that are always reachable without a session (login flow + static).
_PUBLIC_API_PREFIXES = ("/api/auth/",)
_PUBLIC_API_EXACT = frozenset({"/api/health"})


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def client_id() -> str:
    return _env("GITHUB_OAUTH_CLIENT_ID")


def client_secret() -> str:
    return _env("GITHUB_OAUTH_CLIENT_SECRET")


def session_secret() -> str:
    # Fall back to a random per-process value so the app still boots if the
    # operator forgets to set one, but every restart invalidates sessions.
    secret = _env("APP_SESSION_SECRET")
    if secret:
        return secret
    log.warning(
        "APP_SESSION_SECRET not set; generating a random secret. "
        "Sessions will be invalidated on every restart. Set a stable "
        "secret (>=32 random bytes) in production."
    )
    return secrets.token_urlsafe(48)


def allowed_users() -> frozenset[str]:
    raw = _env("ALLOWED_GITHUB_USERS")
    if not raw:
        return frozenset()
    return frozenset(u.strip().lower() for u in raw.split(",") if u.strip())


def app_base_url() -> str:
    """Public URL of the app (used to build the OAuth callback URL)."""
    return _env("APP_BASE_URL").rstrip("/")


def is_auth_enabled() -> bool:
    """Auth is enabled iff a GitHub OAuth client id is configured."""
    return bool(client_id())


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_API_EXACT:
        return True
    for prefix in _PUBLIC_API_PREFIXES:
        if path.startswith(prefix):
            return True
    # Anything that isn't /api/* is either the SPA shell or static asset;
    # we let the frontend render and call /api/auth/me itself to decide
    # what to show.
    return not path.startswith("/api/")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_auth_enabled():
            return await call_next(request)

        if _is_public_path(request.url.path):
            return await call_next(request)

        user = request.session.get("user")
        if not user:
            return JSONResponse(
                {"authenticated": False, "error": "authentication required"},
                status_code=401,
            )

        if user.lower() not in allowed_users():
            # Shouldn't happen (the callback enforces the allowlist) but
            # guard against an operator removing a user from the list
            # while their cookie is still valid.
            request.session.clear()
            return JSONResponse(
                {"authenticated": False, "error": "user not on allowlist"},
                status_code=403,
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def who_am_i(request: Request):
    if not is_auth_enabled():
        return {"authenticated": True, "username": "dev", "dev_mode": True}
    user = request.session.get("user")
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {
        "authenticated": True,
        "username": user,
        "avatar": request.session.get("avatar"),
    }


@router.get("/login")
async def start_login(request: Request, next: Optional[str] = None):
    if not is_auth_enabled():
        # In dev-mode bypass there's nothing to do; just go home.
        return RedirectResponse(url=next or "/", status_code=302)

    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    if next:
        request.session["post_login_redirect"] = next

    params = {
        "client_id": client_id(),
        "redirect_uri": _callback_url(request),
        "state": state,
        "scope": "",  # public profile only; no scopes
        "allow_signup": "false",
    }
    return RedirectResponse(
        url=f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}", status_code=302
    )


@router.get("/callback")
async def handle_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    if not is_auth_enabled():
        return RedirectResponse(url="/", status_code=302)

    if error:
        raise HTTPException(status_code=400, detail=f"GitHub returned error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    expected_state = request.session.pop("oauth_state", None)
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token = await _exchange_code(code, _callback_url(request))
    username, avatar = await _fetch_user(token)

    if username.lower() not in allowed_users():
        log.warning("Rejected login from non-allowlisted user: %s", username)
        raise HTTPException(
            status_code=403,
            detail=(
                f"GitHub user '{username}' is not on the allowlist. "
                f"Ask the app owner to add you to ALLOWED_GITHUB_USERS."
            ),
        )

    request.session["user"] = username
    request.session["avatar"] = avatar
    redirect_to = request.session.pop("post_login_redirect", "/") or "/"
    log.info("Authenticated GitHub user %s", username)
    return RedirectResponse(url=redirect_to, status_code=302)


@router.post("/logout")
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _callback_url(request: Request) -> str:
    base = app_base_url()
    if base:
        return f"{base}/api/auth/callback"
    # Fall back to the request's own scheme+host. Useful when running
    # ``uvicorn`` locally; in production APP_BASE_URL should be set so
    # that the URL registered with GitHub matches exactly.
    return str(request.url_for("handle_callback"))


async def _exchange_code(code: str, redirect_uri: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id(),
                "client_secret": client_secret(),
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub token exchange failed: {r.status_code}",
        )
    payload = r.json()
    token = payload.get("access_token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub token exchange returned no access_token: {payload}",
        )
    return token


async def _fetch_user(token: str) -> tuple[str, Optional[str]]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub /user failed: {r.status_code}",
        )
    body = r.json()
    login = body.get("login")
    if not login:
        raise HTTPException(status_code=502, detail="GitHub /user returned no login")
    return login, body.get("avatar_url")


# ---------------------------------------------------------------------------
# Public installer
# ---------------------------------------------------------------------------


def install_auth(app: FastAPI) -> None:
    """Attach session middleware, auth middleware, and the auth router."""
    app.add_middleware(AuthMiddleware)
    # SessionMiddleware must be added AFTER our middleware so that in the
    # final stack `request.session` is populated before AuthMiddleware
    # looks at it. Starlette processes middleware in reverse add-order.
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(),
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=False,  # keep False; Container Apps terminates TLS.
    )
    app.include_router(router)

    if is_auth_enabled():
        users = sorted(allowed_users())
        if not users:
            log.warning(
                "GITHUB_OAUTH_CLIENT_ID is set but ALLOWED_GITHUB_USERS is "
                "empty. Nobody will be able to sign in."
            )
        else:
            log.info("GitHub auth enabled for users: %s", ", ".join(users))
    else:
        log.warning(
            "GITHUB_OAUTH_CLIENT_ID is not set — auth is DISABLED and every "
            "request will be accepted. Do not expose this to the internet."
        )
