"""Workout data models."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class StepType(str, Enum):
    WARMUP = "warmup"
    COOLDOWN = "cooldown"
    RUN = "run"
    INTERVAL = "interval"
    REST = "rest"
    REPEAT = "repeat"


class DurationType(str, Enum):
    TIME = "time"
    DISTANCE = "distance"
    LAP_BUTTON = "lap_button"


class Intensity(str, Enum):
    EASY = "easy"
    MODERATE = "moderate"
    TEMPO = "tempo"
    THRESHOLD = "threshold"
    TEN_K = "10k"
    FIVE_K = "5k"
    MILE = "mile"
    SPRINT = "sprint"
    RACE_PACE = "race_pace"
    RECOVERY = "recovery"


class WarmupStep(BaseModel):
    type: Literal["warmup"] = "warmup"
    duration_type: DurationType = DurationType.LAP_BUTTON
    duration: float | None = None
    note: str | None = None


class CooldownStep(BaseModel):
    type: Literal["cooldown"] = "cooldown"
    duration_type: DurationType = DurationType.LAP_BUTTON
    duration: float | None = None
    note: str | None = None


class RunStep(BaseModel):
    type: Literal["run"] = "run"
    duration_type: DurationType = DurationType.TIME
    duration: float
    intensity: Intensity = Intensity.EASY
    pace_target: str | None = None
    note: str | None = None


class IntervalStep(BaseModel):
    type: Literal["interval"] = "interval"
    duration_type: DurationType = DurationType.TIME
    duration: float
    intensity: Intensity = Intensity.THRESHOLD
    pace_target: str | None = None
    note: str | None = None


class RestStep(BaseModel):
    type: Literal["rest"] = "rest"
    duration_type: DurationType = DurationType.TIME
    duration: float | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_duration(self) -> RestStep:
        if self.duration_type != DurationType.LAP_BUTTON and self.duration is None:
            raise ValueError(
                "rest steps require duration unless duration_type is 'lap_button'",
            )
        return self


class RepeatStep(BaseModel):
    type: Literal["repeat"] = "repeat"
    count: int
    steps: list[WorkoutStep]
    note: str | None = None


WorkoutStep = Annotated[
    WarmupStep | CooldownStep | RunStep | IntervalStep | RestStep | RepeatStep,
    Field(discriminator="type"),
]

# Rebuild RepeatStep to resolve the forward reference to WorkoutStep
RepeatStep.model_rebuild()


class Workout(BaseModel):
    name: str = "Workout"
    steps: list[WorkoutStep]
    sport: str = "running"


def _format_duration(seconds: float) -> str:
    """Format seconds into MM:SS or H:MM:SS."""
    total = int(seconds)
    if total >= 3600:
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        return f"{h}:{m:02d}:{s:02d}"
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _format_distance(meters: float) -> str:
    """Format meters into a human-readable string."""
    if meters >= 1000:
        km = meters / 1000
        return f"{km:g} km"
    return f"{meters:g} m"


_STEP_ICONS = {
    "warmup": "🔥",
    "cooldown": "❄️",
    "run": "🏃",
    "interval": "⚡",
    "rest": "😴",
    "repeat": "🔄",
}

_SUB_LABELS = "abcdefghijklmnopqrstuvwxyz"


def _format_step_line(step: WorkoutStep) -> str:
    """Format a single step as a one-line description."""
    icon = _STEP_ICONS.get(step.type, "•")
    label = step.type.capitalize()

    if isinstance(step, (WarmupStep, CooldownStep)):
        if step.duration is None or step.duration_type == DurationType.LAP_BUTTON:
            return f"{icon} {label} (until lap button)"
        dur = (
            _format_duration(step.duration)
            if step.duration_type == DurationType.TIME
            else _format_distance(step.duration)
        )
        return f"{icon} {label} {dur}"

    if isinstance(step, (RunStep, IntervalStep)):
        dur = (
            _format_duration(step.duration)
            if step.duration_type == DurationType.TIME
            else _format_distance(step.duration)
        )
        pace = f" @ {step.pace_target}" if step.pace_target else f" @ {step.intensity.value}"
        return f"{icon} {label} {dur}{pace}"

    if isinstance(step, RestStep):
        if step.duration is None or step.duration_type == DurationType.LAP_BUTTON:
            return f"{icon} {label} (until lap button)"
        dur = (
            _format_duration(step.duration)
            if step.duration_type == DurationType.TIME
            else _format_distance(step.duration)
        )
        return f"{icon} {label} {dur}"

    return ""


def format_workout_preview(workout: Workout) -> str:
    """Format a workout as a human-readable preview string."""
    lines: list[str] = [f"🏃 {workout.name} ({workout.sport})"]
    for i, step in enumerate(workout.steps, 1):
        if isinstance(step, RepeatStep):
            lines.append(f"  {i}. 🔄 Repeat {step.count}x:")
            for j, sub in enumerate(step.steps):
                lbl = _SUB_LABELS[j] if j < len(_SUB_LABELS) else str(j + 1)
                lines.append(f"     {lbl}. {_format_step_line(sub)}")
        else:
            lines.append(f"  {i}. {_format_step_line(step)}")
    return "\n".join(lines)
