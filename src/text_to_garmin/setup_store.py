"""Persisted setup state: Copilot auth token + (optionally) Garmin creds.

State is saved to ``$TEXT_TO_GARMIN_STATE_DIR`` (defaults to ``~/.text-to-garmin``)
so a container restart doesn't lose the configuration — mount that directory
as a persistent volume in Azure if you want the setup to survive revisions.

Nothing in this module is encrypted at rest. In production the directory
should either be backed by Key Vault-sourced env vars (``COPILOT_GITHUB_TOKEN``)
or mounted from a secure volume. The setup endpoints are intended for a
single-tenant deployment ("run your own copy") model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

_STATE_DIR_ENV = "TEXT_TO_GARMIN_STATE_DIR"


def state_dir() -> Path:
    raw = os.environ.get(_STATE_DIR_ENV)
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".text-to-garmin"


def _config_path() -> Path:
    return state_dir() / "config.json"


def _load() -> dict:
    p = _config_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = _config_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Copilot PAT
# ---------------------------------------------------------------------------


def get_copilot_token() -> Optional[str]:
    """Return the configured Copilot PAT, or ``None``.

    Env var wins so cloud deploys can inject via secrets without going through
    the UI.
    """
    env = os.environ.get("COPILOT_GITHUB_TOKEN")
    if env:
        return env
    return _load().get("copilot_token") or None


def set_copilot_token(token: str) -> None:
    data = _load()
    data["copilot_token"] = token.strip()
    _save(data)
    # Make it visible to subprocesses the Copilot SDK spawns.
    os.environ["COPILOT_GITHUB_TOKEN"] = token.strip()


def clear_copilot_token() -> None:
    data = _load()
    data.pop("copilot_token", None)
    _save(data)
    os.environ.pop("COPILOT_GITHUB_TOKEN", None)


def apply_env_from_store() -> None:
    """Populate process env from the persisted store on startup.

    Does not overwrite values already present in the environment.
    """
    tok = _load().get("copilot_token")
    if tok and not os.environ.get("COPILOT_GITHUB_TOKEN"):
        os.environ["COPILOT_GITHUB_TOKEN"] = tok
