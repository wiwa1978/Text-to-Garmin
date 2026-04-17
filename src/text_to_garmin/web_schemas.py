"""Pydantic schemas for the web API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from .models import Workout

Status = Literal[
    "needs_clarification",
    "preview_ready",
    "uploaded",
    "auth_required",
    "error",
    "ok",
]


class CreateDraftRequest(BaseModel):
    description: str
    # Empty string means "let the LLM generate a descriptive name".
    name: str = ""
    # Copilot model id; when None the backend uses its default.
    model: Optional[str] = None


class ReplyRequest(BaseModel):
    reply: str


class ReviseRequest(BaseModel):
    feedback: str


class AcceptRequest(BaseModel):
    # If provided, overrides the workout name before upload.
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


class DraftResponse(BaseModel):
    draft_id: str
    status: Status
    workout: Optional[Workout] = None
    preview: Optional[str] = None
    question: Optional[str] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    draft_id: str
    status: Status
    workout_id: Optional[int] = None
    garmin_url: str = "https://connect.garmin.com/modern/workouts"
    error: Optional[str] = None


class ModelInfo(BaseModel):
    id: str
    name: str
    billing_multiplier: Optional[float] = None


class ListModelsResponse(BaseModel):
    models: list[ModelInfo]
    default: Optional[str] = None


class WorkoutsRequest(BaseModel):
    """Optional body for list/delete workout endpoints.

    If Garmin session tokens are cached, no body is needed. When the server
    responds ``auth_required``, the UI resends with ``email`` + ``password``.
    """

    limit: Optional[int] = None
    email: Optional[str] = None
    password: Optional[str] = None


class WorkoutSummary(BaseModel):
    workout_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    sport_type: Optional[str] = None
    estimated_duration_s: Optional[float] = None
    estimated_distance_m: Optional[float] = None
    created_date: Optional[str] = None
    updated_date: Optional[str] = None


class ListWorkoutsResponse(BaseModel):
    status: Status  # "ok" | "auth_required" | "error"
    workouts: list[WorkoutSummary] = []
    error: Optional[str] = None


class WorkoutActionResponse(BaseModel):
    status: Status  # "ok" | "auth_required" | "error"
    workout_id: Optional[int] = None
    error: Optional[str] = None
