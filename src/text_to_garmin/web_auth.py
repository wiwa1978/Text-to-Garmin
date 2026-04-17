"""Password-based authentication for the web app.

Design:

* One shared password, set via the ``APP_PASSWORD`` env var by whoever
  deploys the app. Everyone who visits the site types the same password
  once per browser; the backend sets a signed session cookie so they
  stay logged in for 30 days.
* Zero persistent state. No users, no database. If you want to rotate
  the password, change the env var and reprovision — existing sessions
  keep working until the cookie expires (set a new ``APP_SESSION_SECRET``
  at the same time to force everyone out).
* Dev-mode bypass. When ``APP_PASSWORD`` is unset the middleware logs a
  loud warning and accepts every request, so ``uvicorn`` + ``vite dev``
  keeps working without setup.

Endpoints installed by :func:`install_auth`:

* ``GET  /api/auth/me``        — 200 ``{authenticated: true}`` or 401
* ``POST /api/auth/login``     — body ``{password}``, sets cookie; 204 / 401
* ``POST /api/auth/logout``    — clears cookie; 204
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

log = logging.getLogger(__name__)

SESSION_COOKIE = "t2g_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days

_PUBLIC_API_PREFIXES = ("/api/auth/",)
_PUBLIC_API_EXACT = frozenset({"/api/health"})


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def app_password() -> str:
    return _env("APP_PASSWORD")


def session_secret() -> str:
    # Random fallback keeps the app bootable, but invalidates sessions on
    # every restart. Operators should set a stable 32+ byte value.
    secret = _env("APP_SESSION_SECRET")
    if secret:
        return secret
    log.warning(
        "APP_SESSION_SECRET not set; generating a random secret. "
        "Sessions will be invalidated on every restart. Set a stable "
        "secret (>=32 random bytes) in production."
    )
    return secrets.token_urlsafe(48)


def is_auth_enabled() -> bool:
    return bool(app_password())


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_API_EXACT:
        return True
    for prefix in _PUBLIC_API_PREFIXES:
        if path.startswith(prefix):
            return True
    # Non-/api/* paths (SPA shell, static assets) are always reachable;
    # the frontend calls /api/auth/me itself to decide what to render.
    return not path.startswith("/api/")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_auth_enabled():
            return await call_next(request)

        if _is_public_path(request.url.path):
            return await call_next(request)

        if not request.session.get("authed"):
            return JSONResponse(
                {"authenticated": False, "error": "authentication required"},
                status_code=401,
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.get("/me")
async def who_am_i(request: Request):
    if not is_auth_enabled():
        return {"authenticated": True, "dev_mode": True}
    if not request.session.get("authed"):
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True}


@router.post("/login")
async def login(req: LoginRequest, request: Request) -> Response:
    if not is_auth_enabled():
        # No password configured; treat as dev-mode noop.
        return Response(status_code=204)

    # Constant-time comparison to foil timing side-channels.
    if not secrets.compare_digest(req.password, app_password()):
        return JSONResponse(
            {"authenticated": False, "error": "Incorrect password"},
            status_code=401,
        )

    request.session["authed"] = True
    return Response(status_code=204)


@router.post("/logout")
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Public installer
# ---------------------------------------------------------------------------


def install_auth(app: FastAPI) -> None:
    """Attach session middleware, auth middleware, and the auth router."""
    # Starlette applies middleware in reverse add-order on the way in:
    # SessionMiddleware must be added AFTER AuthMiddleware so it wraps
    # AuthMiddleware and populates request.session first.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(),
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=False,  # Container Apps terminates TLS upstream.
    )
    app.include_router(router)

    if is_auth_enabled():
        log.info("Password auth enabled.")
    else:
        log.warning(
            "APP_PASSWORD is not set — auth is DISABLED and every request "
            "will be accepted. Do not expose this to the internet."
        )
