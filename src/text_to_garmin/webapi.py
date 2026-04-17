"""FastAPI web app for text-to-garmin.

Endpoints:

* ``POST   /api/drafts``                         — start a new parse
* ``POST   /api/drafts/{draft_id}/reply``        — answer a clarifying question
* ``POST   /api/drafts/{draft_id}/revise``       — revise the current workout
* ``POST   /api/drafts/stream``                  — streaming variant of create
* ``POST   /api/drafts/{draft_id}/reply/stream`` — streaming variant of reply
* ``POST   /api/drafts/{draft_id}/revise/stream``— streaming variant of revise
* ``POST   /api/drafts/{draft_id}/accept``       — upload to Garmin Connect
* ``DELETE /api/drafts/{draft_id}``              — drop the draft (cancel)
* ``GET    /api/models``                         — list available Copilot models
* ``GET    /api/health``                         — liveness probe

Streaming endpoints emit Server-Sent Events. Each event has a ``stage``
(e.g. ``preparing_prompt``, ``sending_prompt``, ``received_response``,
``validating``, ``validation_failed``, ``clarification_needed``,
``workout_ready``) and the final ``result`` event carries the same
``DraftResponse`` payload as the non-streaming endpoints.

Auth model: the backend relies on cached Garmin tokens or ``GARMIN_EMAIL`` /
``GARMIN_PASSWORD`` env vars; it never prompts the user. If credentials are
missing or expired, ``accept`` returns ``status="auth_required"``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import TOKEN_DIR as GARMIN_TOKEN_PATH
from .auth import (
    GarminAuthFailedError,
    GarminAuthRequiredError,
    authenticate,
)
from .draft_store import Draft, DraftStore
from .models import format_workout_preview
from .parser import (
    DEFAULT_MODEL,
    ClarificationNeeded,
    ParseOutcome,
    list_available_models,
)
from .setup_store import (
    apply_env_from_store,
    clear_copilot_token,
    get_copilot_token,
    set_copilot_token,
)
from .uploader import (
    delete_workout_with_client,
    list_workouts_with_client,
    upload_workout_with_client,
)
from .web_auth import install_auth
from .web_schemas import (
    AcceptRequest,
    CreateDraftRequest,
    DraftResponse,
    ListModelsResponse,
    ListWorkoutsResponse,
    ModelInfo,
    ReplyRequest,
    ReviseRequest,
    UploadResponse,
    WorkoutActionResponse,
    WorkoutsRequest,
    WorkoutSummary,
)

log = logging.getLogger(__name__)


store = DraftStore()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    apply_env_from_store()
    try:
        yield
    finally:
        await store.close_all()


app = FastAPI(title="text-to-garmin", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
install_auth(app)


def _draft_response_from(draft: Draft, outcome: ParseOutcome) -> DraftResponse:
    if isinstance(outcome, ClarificationNeeded):
        draft.last_question = outcome.question
        return DraftResponse(
            draft_id=draft.id,
            status="needs_clarification",
            question=outcome.question,
        )
    draft.workout = outcome
    draft.last_question = None
    return DraftResponse(
        draft_id=draft.id,
        status="preview_ready",
        workout=outcome,
        preview=format_workout_preview(outcome),
    )


def _get_draft(draft_id: str) -> Draft:
    draft = store.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models", response_model=ListModelsResponse)
async def list_models() -> ListModelsResponse:
    options = await list_available_models()
    return ListModelsResponse(
        models=[
            ModelInfo(id=o.id, name=o.name, billing_multiplier=o.billing_multiplier)
            for o in options
        ],
        default=DEFAULT_MODEL,
    )


@app.post("/api/drafts", response_model=DraftResponse)
async def create_draft(req: CreateDraftRequest) -> DraftResponse:
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="description must not be empty")
    draft = await store.create(model=req.model)
    try:
        async with draft.lock:
            outcome = await draft.session.parse_web(
                req.description, workout_name=req.name
            )
    except Exception as exc:
        log.exception("parse failed")
        await store.delete(draft.id)
        return DraftResponse(draft_id=draft.id, status="error", error=str(exc))
    return _draft_response_from(draft, outcome)


@app.post("/api/drafts/{draft_id}/reply", response_model=DraftResponse)
async def reply_draft(draft_id: str, req: ReplyRequest) -> DraftResponse:
    draft = _get_draft(draft_id)
    if not req.reply.strip():
        raise HTTPException(status_code=400, detail="reply must not be empty")
    try:
        async with draft.lock:
            outcome = await draft.session.reply_web(req.reply)
    except Exception as exc:
        log.exception("reply failed")
        return DraftResponse(draft_id=draft.id, status="error", error=str(exc))
    return _draft_response_from(draft, outcome)


@app.post("/api/drafts/{draft_id}/revise", response_model=DraftResponse)
async def revise_draft(draft_id: str, req: ReviseRequest) -> DraftResponse:
    draft = _get_draft(draft_id)
    if not req.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback must not be empty")
    try:
        async with draft.lock:
            outcome = await draft.session.revise_web(req.feedback)
    except Exception as exc:
        log.exception("revise failed")
        return DraftResponse(draft_id=draft.id, status="error", error=str(exc))
    return _draft_response_from(draft, outcome)


# ----------------------------------------------------------------------
# Streaming variants (Server-Sent Events)
# ----------------------------------------------------------------------


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _run_streaming(
    run: Callable[[Callable[[dict], Awaitable[None]]], Awaitable[ParseOutcome]],
    finalize: Callable[[ParseOutcome], DraftResponse],
    error_draft_id: str,
) -> AsyncIterator[str]:
    """Drive a parser coroutine while forwarding its events as SSE frames."""
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(evt: dict) -> None:
        await queue.put(evt)

    async def runner() -> ParseOutcome | Exception:
        try:
            return await run(emit)
        except Exception as exc:  # noqa: BLE001
            return exc
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())
    try:
        while True:
            evt = await queue.get()
            if evt is None:
                break
            yield _sse("stage", evt)

        outcome_or_exc = await task
        if isinstance(outcome_or_exc, Exception):
            yield _sse(
                "result",
                {
                    "draft_id": error_draft_id,
                    "status": "error",
                    "error": str(outcome_or_exc),
                },
            )
            return
        yield _sse("result", finalize(outcome_or_exc).model_dump())
    finally:
        if not task.done():
            task.cancel()


@app.post("/api/drafts/stream")
async def create_draft_stream(req: CreateDraftRequest) -> StreamingResponse:
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="description must not be empty")
    draft = await store.create(model=req.model)

    async def run(emit):
        async with draft.lock:
            return await draft.session.parse_web(
                req.description, workout_name=req.name, on_event=emit
            )

    def finalize(outcome: ParseOutcome) -> DraftResponse:
        return _draft_response_from(draft, outcome)

    async def gen() -> AsyncIterator[str]:
        # Emit the draft id up-front so the client can wire discard, etc.
        yield _sse("draft", {"draft_id": draft.id})
        try:
            async for frame in _run_streaming(run, finalize, draft.id):
                yield frame
        except Exception as exc:  # noqa: BLE001
            log.exception("streaming parse failed")
            yield _sse(
                "result",
                {"draft_id": draft.id, "status": "error", "error": str(exc)},
            )
            await store.delete(draft.id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/drafts/{draft_id}/reply/stream")
async def reply_draft_stream(draft_id: str, req: ReplyRequest) -> StreamingResponse:
    draft = _get_draft(draft_id)
    if not req.reply.strip():
        raise HTTPException(status_code=400, detail="reply must not be empty")

    async def run(emit):
        async with draft.lock:
            return await draft.session.reply_web(req.reply, on_event=emit)

    def finalize(outcome: ParseOutcome) -> DraftResponse:
        return _draft_response_from(draft, outcome)

    async def gen() -> AsyncIterator[str]:
        yield _sse("draft", {"draft_id": draft.id})
        async for frame in _run_streaming(run, finalize, draft.id):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/drafts/{draft_id}/revise/stream")
async def revise_draft_stream(draft_id: str, req: ReviseRequest) -> StreamingResponse:
    draft = _get_draft(draft_id)
    if not req.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback must not be empty")

    async def run(emit):
        async with draft.lock:
            return await draft.session.revise_web(req.feedback, on_event=emit)

    def finalize(outcome: ParseOutcome) -> DraftResponse:
        return _draft_response_from(draft, outcome)

    async def gen() -> AsyncIterator[str]:
        yield _sse("draft", {"draft_id": draft.id})
        async for frame in _run_streaming(run, finalize, draft.id):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/drafts/{draft_id}/accept", response_model=UploadResponse)
async def accept_draft(
    draft_id: str, req: AcceptRequest | None = None
) -> UploadResponse:
    draft = _get_draft(draft_id)
    if draft.workout is None:
        raise HTTPException(
            status_code=409,
            detail="Draft has no preview-ready workout yet",
        )

    email = (req.email if req else None) or None
    password = (req.password if req else None) or None
    override_name = (req.name.strip() if req and req.name else "") or None
    if override_name:
        draft.workout.name = override_name

    try:
        client = authenticate(email=email, password=password, interactive=False)
    except GarminAuthRequiredError as exc:
        return UploadResponse(draft_id=draft.id, status="auth_required", error=str(exc))
    except GarminAuthFailedError as exc:
        return UploadResponse(draft_id=draft.id, status="auth_required", error=str(exc))

    try:
        result = upload_workout_with_client(client, draft.workout)
    except Exception as exc:
        log.exception("upload failed")
        return UploadResponse(draft_id=draft.id, status="error", error=str(exc))

    workout_id = result.get("workoutId") if isinstance(result, dict) else None

    # Upload succeeded — discard the draft/session.
    await store.delete(draft.id)

    return UploadResponse(
        draft_id=draft_id,
        status="uploaded",
        workout_id=workout_id,
    )


@app.delete("/api/drafts/{draft_id}")
async def delete_draft(draft_id: str) -> dict[str, str]:
    ok = await store.delete(draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"status": "deleted"}


# ----------------------------------------------------------------------
# Recent workouts from Garmin Connect
# ----------------------------------------------------------------------


def _authenticate_for_garmin(req: WorkoutsRequest | None):
    """Return (client, None) on success or (None, error_response_dict) on auth failure."""
    email = (req.email if req else None) or None
    password = (req.password if req else None) or None
    try:
        client = authenticate(email=email, password=password, interactive=False)
    except (GarminAuthRequiredError, GarminAuthFailedError) as exc:
        return None, {"status": "auth_required", "error": str(exc)}
    return client, None


@app.post("/api/workouts/list", response_model=ListWorkoutsResponse)
async def list_recent_workouts(
    req: WorkoutsRequest | None = None,
) -> ListWorkoutsResponse:
    """Return the caller's most recent Garmin Connect workouts.

    Uses cached Garmin session tokens when available; if none are present
    (or they have expired), responds with ``status="auth_required"`` and
    the UI re-submits with email + password.
    """
    client, err = _authenticate_for_garmin(req)
    if err is not None:
        return ListWorkoutsResponse(**err)

    limit = (req.limit if req and req.limit else 20) or 20
    try:
        rows = list_workouts_with_client(client, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.exception("get_workouts failed")
        return ListWorkoutsResponse(status="error", error=str(exc))

    return ListWorkoutsResponse(
        status="ok",
        workouts=[WorkoutSummary(**r) for r in rows],
    )


@app.post("/api/workouts/{workout_id}/delete", response_model=WorkoutActionResponse)
async def delete_garmin_workout(
    workout_id: int, req: WorkoutsRequest | None = None
) -> WorkoutActionResponse:
    client, err = _authenticate_for_garmin(req)
    if err is not None:
        return WorkoutActionResponse(workout_id=workout_id, **err)

    try:
        delete_workout_with_client(client, workout_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("delete_workout failed")
        return WorkoutActionResponse(
            status="error", workout_id=workout_id, error=str(exc)
        )

    return WorkoutActionResponse(status="ok", workout_id=workout_id)


# ----------------------------------------------------------------------
# Setup (Copilot PAT / Garmin)
# ----------------------------------------------------------------------


class SetupStatus(BaseModel):
    copilot_configured: bool
    copilot_login: Optional[str] = None
    copilot_error: Optional[str] = None
    garmin_tokens_cached: bool


class CopilotTokenRequest(BaseModel):
    token: str


async def _probe_copilot_auth() -> SetupStatus:
    """Start a short-lived Copilot client and report whether auth works."""
    garmin_tokens = GARMIN_TOKEN_PATH.exists()

    if not get_copilot_token() and not _has_local_copilot_config():
        return SetupStatus(copilot_configured=False, garmin_tokens_cached=garmin_tokens)

    try:
        from copilot import CopilotClient
    except ImportError as exc:
        return SetupStatus(
            copilot_configured=False,
            copilot_error=f"Copilot SDK not installed: {exc}",
            garmin_tokens_cached=garmin_tokens,
        )

    client = CopilotClient()
    try:
        await client.start()
        auth = await client.get_auth_status()
    except Exception as exc:  # noqa: BLE001
        return SetupStatus(
            copilot_configured=False,
            copilot_error=str(exc),
            garmin_tokens_cached=garmin_tokens,
        )
    finally:
        try:
            await client.stop()
        except Exception:
            pass

    return SetupStatus(
        copilot_configured=bool(getattr(auth, "isAuthenticated", False)),
        copilot_login=getattr(auth, "login", None),
        garmin_tokens_cached=garmin_tokens,
    )


def _has_local_copilot_config() -> bool:
    """Rough check for a pre-existing ``copilot login`` state on disk."""
    return (Path.home() / ".copilot").is_dir()


@app.get("/api/setup/status", response_model=SetupStatus)
async def setup_status() -> SetupStatus:
    return await _probe_copilot_auth()


@app.post("/api/setup/copilot", response_model=SetupStatus)
async def setup_copilot(req: CopilotTokenRequest) -> SetupStatus:
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="token must not be empty")
    if not (
        token.startswith("github_pat_")
        or token.startswith("gho_")
        or token.startswith("ghu_")
    ):
        log.warning("copilot token does not look like a GitHub token")
    set_copilot_token(token)
    status = await _probe_copilot_auth()
    if not status.copilot_configured:
        # Roll back so we don't keep a token that doesn't work.
        clear_copilot_token()
        raise HTTPException(
            status_code=400,
            detail=status.copilot_error or "Token did not authenticate.",
        )
    return status


@app.delete("/api/setup/copilot", response_model=SetupStatus)
async def setup_copilot_clear() -> SetupStatus:
    clear_copilot_token()
    return await _probe_copilot_auth()


# ----------------------------------------------------------------------
# Static frontend (served in production container)
# ----------------------------------------------------------------------


def _static_dir() -> Optional[Path]:
    override = os.environ.get("TEXT_TO_GARMIN_STATIC_DIR")
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    # Default: ``frontend/dist`` relative to the repo (dev) and
    # ``/app/static`` inside the container (see Dockerfile).
    for candidate in (
        Path("/app/static"),
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ):
        if candidate.is_dir():
            return candidate
    return None


_STATIC = _static_dir()
if _STATIC is not None:
    # Mount /assets so hashed JS/CSS resolve normally.
    if (_STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_catch_all(path: str) -> FileResponse:
        # Anything under /api/* is handled by API routes above; FastAPI
        # matches more specific routes first. For every other path, try
        # to serve a real file (favicon, etc.) and fall back to index.html
        # so the SPA router can take over.
        target = _STATIC / path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(_STATIC / "index.html")
