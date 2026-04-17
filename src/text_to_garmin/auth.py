"""Garmin Connect authentication module."""

from __future__ import annotations

import os
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from rich.console import Console

console = Console()

TOKEN_DIR = Path(
    os.environ.get(
        "GARMINTOKENS", str(Path.home() / ".garminconnect" / "garmin_tokens.json")
    )
).expanduser()
LEGACY_TOKEN_DIR = Path.home() / ".text-to-garmin" / ".gauth"


class GarminAuthRequiredError(RuntimeError):
    """Raised in non-interactive mode when credentials are missing."""


class GarminAuthFailedError(RuntimeError):
    """Raised when Garmin login fails (bad creds, MFA, rate limit, etc.)."""


def _get_credentials(
    email: str | None = None,
    password: str | None = None,
    *,
    interactive: bool = True,
) -> tuple[str, str]:
    """Resolve credentials from args, env vars, or interactive prompt."""
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")

    if not email or not password:
        if not interactive:
            raise GarminAuthRequiredError(
                "Garmin credentials not available. Set GARMIN_EMAIL/GARMIN_PASSWORD "
                "or run the CLI once to cache login tokens."
            )
        if not email:
            email = input("Garmin Connect email: ")
        if not password:
            password = getpass("Garmin Connect password: ")

    return email, password


def _prompt_mfa_code() -> str:
    return input("Garmin Connect MFA code: ").strip()


def _noninteractive_mfa_code() -> str:
    raise GarminAuthRequiredError(
        "Garmin account requires MFA. Run the CLI once to complete MFA and cache tokens."
    )


def _resolve_tokenstore() -> Path:
    if TOKEN_DIR.exists() or not LEGACY_TOKEN_DIR.exists():
        return TOKEN_DIR
    return LEGACY_TOKEN_DIR


def _format_auth_error(exc: Exception) -> str:
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return (
            "Garmin login is being blocked or rate-limited by Garmin/Cloudflare. "
            "This is a server-side auth challenge, not just a local cooldown. "
            f"If login succeeds once, tokens will be cached in {_resolve_tokenstore()} for reuse."
        )
    if isinstance(exc, GarminConnectAuthenticationError):
        return str(exc)
    if isinstance(exc, GarminConnectConnectionError):
        return f"Garmin connection failed: {exc}"
    return f"Login failed: {exc}"


def authenticate(
    email: str | None = None,
    password: str | None = None,
    *,
    interactive: bool = True,
) -> Garmin:
    """
    Authenticate with Garmin Connect using native garminconnect token handling.
    Reuses cached tokens when available and falls back to credential login.

    When ``interactive=False`` this function will never call ``input()`` /
    ``getpass()``. If cached tokens are missing/expired and no env-var
    credentials are provided, it raises :class:`GarminAuthRequiredError`.
    On other auth/connection failures it raises :class:`GarminAuthFailedError`.
    """
    tokenstore = _resolve_tokenstore()

    # In non-interactive mode, try a tokens-only login first so we never need creds.
    if not interactive:
        if tokenstore.exists():
            client = Garmin(prompt_mfa=_noninteractive_mfa_code)
            try:
                client.login(str(tokenstore))
                return client
            except (
                GarminConnectAuthenticationError,
                GarminConnectConnectionError,
                GarminConnectTooManyRequestsError,
            ):
                # Fall through to credential-based login below.
                pass

        try:
            email, password = _get_credentials(email, password, interactive=False)
        except GarminAuthRequiredError:
            raise

        client = Garmin(
            email=email, password=password, prompt_mfa=_noninteractive_mfa_code
        )
        try:
            tokenstore.parent.mkdir(parents=True, exist_ok=True)
            client.login(str(tokenstore))
        except (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
        ) as exc:
            raise GarminAuthFailedError(_format_auth_error(exc)) from exc
        return client

    # Interactive (CLI) path — preserves previous behavior.
    email, password = _get_credentials(email, password, interactive=True)
    client = Garmin(email=email, password=password, prompt_mfa=_prompt_mfa_code)

    try:
        with console.status("[bold cyan]Authenticating with Garmin Connect…"):
            tokenstore.parent.mkdir(parents=True, exist_ok=True)
            client.login(str(tokenstore))
    except (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    ) as exc:
        console.print(f":cross_mark:  {_format_auth_error(exc)}")
        raise SystemExit(1) from exc

    console.print(f":white_check_mark:  Garmin session ready ({tokenstore}).")
    return client


def get_garmin_client(*, interactive: bool = True) -> Garmin:
    """
    Get an authenticated Garmin Connect client.
    """
    return authenticate(interactive=interactive)
