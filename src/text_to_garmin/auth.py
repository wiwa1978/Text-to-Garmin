"""Garmin Connect authentication module."""

from __future__ import annotations

import os
from getpass import getpass
from pathlib import Path

import garth
from garminconnect import Garmin
from rich.console import Console

console = Console()

TOKEN_DIR = Path.home() / ".text-to-garmin" / ".gauth"


def _get_credentials(
    email: str | None = None, password: str | None = None
) -> tuple[str, str]:
    """Resolve credentials from args, env vars, or interactive prompt."""
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")

    if not email:
        email = input("Garmin Connect email: ")
    if not password:
        password = getpass("Garmin Connect password: ")

    return email, password


def _try_resume() -> bool:
    """Try to resume a saved session. Returns True on success."""
    if not TOKEN_DIR.exists():
        return False
    try:
        garth.resume(str(TOKEN_DIR))
        _ = garth.client.username
        return True
    except Exception:
        return False


def authenticate(
    email: str | None = None, password: str | None = None
) -> garth.Client:
    """
    Authenticate with Garmin Connect.
    Tries saved token first, then falls back to fresh login.
    Returns the authenticated garth client.
    """
    # Try resuming saved token
    with console.status("[bold cyan]Checking saved Garmin session…"):
        if _try_resume():
            console.print(":white_check_mark:  Resumed saved Garmin session.")
            return garth.client

    # Fresh login required
    console.print(":key:  Saved session not found or expired — logging in.")
    email, password = _get_credentials(email, password)

    try:
        with console.status("[bold cyan]Logging in to Garmin Connect…"):
            garth.login(email, password)
    except Exception as exc:
        console.print(f":cross_mark:  Login failed: {exc}")
        raise SystemExit(1) from exc

    # Persist token
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    garth.save(str(TOKEN_DIR))
    console.print(":white_check_mark:  Logged in and session saved.")

    return garth.client


def get_garmin_client() -> Garmin:
    """
    Get an authenticated Garmin Connect client.
    Handles auth and returns ready-to-use garminconnect.Garmin instance.
    """
    authenticate()
    client = Garmin()
    client.garth = garth.client
    return client
