"""LLM-powered workout parser using Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from rich.console import Console

from .models import Workout


@dataclass
class ClarificationNeeded:
    """Returned by web-safe parser methods when the LLM asks a question."""

    question: str


ParseOutcome = Workout | ClarificationNeeded

# Callback invoked with progress events during a parse. Each event has
# at least a "stage" key. Shape is intentionally open-ended.
EventCb = Optional[Callable[[dict], Awaitable[None]]]

console = Console()

SYSTEM_MESSAGE = """\
You are a running workout parser. Convert natural language workout descriptions into structured JSON.

Common abbreviations:
- W/u, WU = warmup
- C/d, CD = cooldown
- easy, E = easy effort
- tempo, T = tempo effort
- threshold, LT = threshold effort
- 10k, 5k, mile = race pace efforts
- hills = intervals on hills
- strides = short fast accelerations (typically 20-30 seconds)
- strength = strength/conditioning work (treat as a run step with note)
- R, rest = recovery between intervals
- "4x 2min" = 4 repetitions of 2 minutes

IMPORTANT RULES:
1. If rest/recovery between intervals is NOT specified, ASK the user how much rest they want.
2. Always include warmup and cooldown unless explicitly told not to.
3. Duration values are in SECONDS for time type (e.g., 20min = 1200, 2min = 120).
4. Distance values are in METERS for distance type (e.g., 1km = 1000, 400m = 400).
5. For rest-until-lap-button, encode as {"type": "rest", "duration_type": "lap_button", "duration": null}.
6. When the workout is fully specified, output ONLY a JSON code block with no other text.

NAMING:
- If the user explicitly provided a workout name in the prompt, use it verbatim.
- Otherwise, generate a concise descriptive title (max ~40 chars) summarizing the
  workout. Prefer the main set. Examples: "5km easy", "5x1km @ 5k pace",
  "Hill repeats 4x2min", "Threshold 3x10min", "Tempo 20min", "Long run 90min".
  Do NOT use the generic placeholder "Workout".

Output schema:
{
  "name": "string",
  "steps": [
    {"type": "warmup", "duration_type": "lap_button", "duration": null},
    {"type": "run", "duration_type": "time", "duration": 1200, "intensity": "easy", "note": "20min easy"},
    {"type": "repeat", "count": 4, "steps": [
      {"type": "interval", "duration_type": "time", "duration": 120, "intensity": "10k", "note": "2min @ 10k"},
      {"type": "rest", "duration_type": "time", "duration": 60}
    ]},
    {"type": "cooldown", "duration_type": "lap_button", "duration": null}
  ]
}

Valid step types: warmup, cooldown, run, interval, rest, repeat
Valid duration_type: time, distance, lap_button
For rest steps:
- Timed rest example: {"type": "rest", "duration_type": "time", "duration": 60}
- Lap-button rest example: {"type": "rest", "duration_type": "lap_button", "duration": null}
Valid intensity: easy, moderate, tempo, threshold, 10k, 5k, mile, sprint, race_pace, recovery
"""

_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)

MAX_TURNS = 10
MAX_VALIDATION_RETRIES = 3
DEFAULT_MODEL = os.environ.get("TEXT_TO_GARMIN_MODEL")

# A name is treated as "not provided" (→ auto-generate) when it's empty or
# equals our CLI default placeholder.
_AUTO_NAME_SENTINELS = {"", "workout"}


def _is_auto_name(workout_name: str | None) -> bool:
    return (workout_name or "").strip().lower() in _AUTO_NAME_SENTINELS


def _build_initial_prompt(description: str, workout_name: str) -> str:
    if _is_auto_name(workout_name):
        return (
            "Parse this workout into JSON. Generate a concise descriptive "
            "name for the workout (max ~40 chars) based on its contents — "
            'do NOT use the placeholder "Workout".\n\n'
            f"{description}"
        )
    return (
        f'Parse this workout into JSON. Workout name: "{workout_name}"\n\n{description}'
    )


def _extract_json(text: str) -> str | None:
    """Extract JSON from a ```json ... ``` code block."""
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    return None


def _stringify_response_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_stringify_response_content(item) for item in content)
    if isinstance(content, dict):
        return json.dumps(content)
    return str(content)


async def _collect_response(session, prompt: str, on_event: EventCb = None) -> str:
    """Send a prompt and return the final assistant response text."""
    if on_event is not None:
        await on_event({"stage": "sending_prompt", "prompt_chars": len(prompt)})
    response_event = await session.send_and_wait(prompt, timeout=120.0)
    if on_event is not None:
        await on_event({"stage": "received_response"})
    if response_event is None:
        return ""
    return _stringify_response_content(getattr(response_event.data, "content", None))


async def _parse_response_to_workout(
    session,
    response: str,
    workout_name: str,
) -> Workout:
    """Process an LLM response through the multi-turn parse/validate loop."""
    validation_retries = 0

    for _turn in range(MAX_TURNS):
        json_str = _extract_json(response)

        if json_str is not None:
            try:
                data = json.loads(json_str)
                data.setdefault("name", workout_name)
                workout = Workout.model_validate(data)
                return workout
            except (json.JSONDecodeError, Exception) as exc:
                validation_retries += 1
                if validation_retries > MAX_VALIDATION_RETRIES:
                    raise RuntimeError(
                        f"Failed to parse workout after "
                        f"{MAX_VALIDATION_RETRIES} validation retries. "
                        f"Last error: {exc}"
                    ) from exc
                console.print(
                    f"[yellow]Validation error, retrying "
                    f"({validation_retries}/{MAX_VALIDATION_RETRIES})...[/yellow]"
                )
                response = await _collect_response(
                    session,
                    f"The JSON you produced has a validation error: {exc}\n"
                    f"Please fix the JSON and output it again.",
                )
                continue

        # No JSON block — the LLM is asking a clarifying question
        console.print(f"\n[bold cyan]Copilot:[/bold cyan] {response.strip()}")
        user_reply = input("\nYour answer: ")
        response = await _collect_response(session, user_reply)

    raise RuntimeError(f"Workout parsing did not complete within {MAX_TURNS} turns.")


async def _advance_web(
    session,
    response: str,
    workout_name: str,
    on_event: EventCb = None,
) -> ParseOutcome:
    """Web-safe equivalent of _parse_response_to_workout.

    Runs the validation-retry loop but, when the LLM asks a clarifying
    question instead of emitting JSON, returns a :class:`ClarificationNeeded`
    so the caller can surface the question to the user and resume later.
    """
    validation_retries = 0

    while True:
        if on_event is not None:
            await on_event({"stage": "validating"})
        json_str = _extract_json(response)

        if json_str is None:
            if on_event is not None:
                await on_event({"stage": "clarification_needed"})
            return ClarificationNeeded(question=response.strip())

        try:
            data = json.loads(json_str)
            data.setdefault("name", workout_name)
            workout = Workout.model_validate(data)
            if on_event is not None:
                await on_event({"stage": "workout_ready"})
            return workout
        except (json.JSONDecodeError, Exception) as exc:
            validation_retries += 1
            if on_event is not None:
                await on_event(
                    {
                        "stage": "validation_failed",
                        "attempt": validation_retries,
                        "max_attempts": MAX_VALIDATION_RETRIES,
                        "error": str(exc),
                    }
                )
            if validation_retries > MAX_VALIDATION_RETRIES:
                raise RuntimeError(
                    f"Failed to parse workout after "
                    f"{MAX_VALIDATION_RETRIES} validation retries. "
                    f"Last error: {exc}"
                ) from exc
            response = await _collect_response(
                session,
                f"The JSON you produced has a validation error: {exc}\n"
                f"Please fix the JSON and output it again.",
                on_event=on_event,
            )


class WorkoutParserSession:
    """Manages a Copilot session for parsing and revising workouts."""

    def __init__(self, model: Optional[str] = None):
        self._client = None
        self._session = None
        self._workout_name: str = "Workout"
        # Explicit override wins; otherwise fall back to the env default.
        self._model: Optional[str] = model or DEFAULT_MODEL

    async def __aenter__(self):
        try:
            from copilot import CopilotClient
            from copilot.session import PermissionHandler
        except ImportError as exc:
            raise RuntimeError(
                "GitHub Copilot SDK is not installed. "
                "Install it with: pip install github-copilot-sdk"
            ) from exc

        self._client = CopilotClient()
        try:
            await self._client.start()
        except Exception as exc:
            raise RuntimeError(
                "Failed to start Copilot client. "
                "Ensure the Copilot CLI is installed and you are authenticated."
            ) from exc

        session_kwargs = {
            "on_permission_request": PermissionHandler.approve_all,
            "system_message": {"content": SYSTEM_MESSAGE},
        }
        if self._model:
            session_kwargs["model"] = self._model

        self._session = await self._client.create_session(**session_kwargs)
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.destroy()
        if self._client:
            await self._client.stop()

    async def parse(self, description: str, workout_name: str = "Workout") -> Workout:
        """Parse a workout description. Same logic as standalone parse_workout."""
        self._workout_name = workout_name
        initial_prompt = _build_initial_prompt(description, workout_name)
        response = await _collect_response(self._session, initial_prompt)
        return await _parse_response_to_workout(
            self._session,
            response,
            workout_name,
        )

    async def revise(self, feedback: str) -> Workout:
        """Revise the last parsed workout based on user feedback."""
        prompt = (
            f"The user wants to change the workout. Here is their feedback:\n\n"
            f"{feedback}\n\n"
            f"Please output the revised workout as a JSON code block."
        )
        response = await _collect_response(self._session, prompt)
        return await _parse_response_to_workout(
            self._session,
            response,
            self._workout_name,
        )

    # ------------------------------------------------------------------
    # Web-safe (non-interactive) flow
    # ------------------------------------------------------------------
    async def parse_web(
        self,
        description: str,
        workout_name: str = "Workout",
        on_event: EventCb = None,
    ) -> ParseOutcome:
        """Non-interactive parse: returns either a Workout or ClarificationNeeded."""
        self._workout_name = workout_name
        if on_event is not None:
            await on_event({"stage": "preparing_prompt"})
        initial_prompt = _build_initial_prompt(description, workout_name)
        response = await _collect_response(
            self._session, initial_prompt, on_event=on_event
        )
        return await _advance_web(
            self._session, response, workout_name, on_event=on_event
        )

    async def reply_web(
        self, user_reply: str, on_event: EventCb = None
    ) -> ParseOutcome:
        """Continue a paused parse by sending the user's answer to a clarification."""
        response = await _collect_response(self._session, user_reply, on_event=on_event)
        return await _advance_web(
            self._session, response, self._workout_name, on_event=on_event
        )

    async def revise_web(self, feedback: str, on_event: EventCb = None) -> ParseOutcome:
        """Non-interactive revise: returns either a Workout or ClarificationNeeded."""
        prompt = (
            f"The user wants to change the workout. Here is their feedback:\n\n"
            f"{feedback}\n\n"
            f"Please output the revised workout as a JSON code block."
        )
        response = await _collect_response(self._session, prompt, on_event=on_event)
        return await _advance_web(
            self._session, response, self._workout_name, on_event=on_event
        )


async def parse_workout(
    description: str,
    workout_name: str = "Workout",
) -> Workout:
    """Parse a natural language workout description into a structured Workout.

    Uses GitHub Copilot SDK for LLM-powered parsing.
    Interactively asks the user clarifying questions if needed.
    """
    async with WorkoutParserSession() as session:
        return await session.parse(description, workout_name)


@dataclass
class ModelOption:
    """Minimal, serialisable model descriptor for the web UI."""

    id: str
    name: str
    billing_multiplier: float | None = None


async def list_available_models() -> list[ModelOption]:
    """Query the Copilot SDK for the list of models the user can use.

    Starts a short-lived :class:`CopilotClient` to fetch the list. Returns
    an empty list if the SDK is unavailable.
    """
    import logging

    log = logging.getLogger(__name__)

    try:
        from copilot import CopilotClient
    except ImportError:
        log.warning("copilot SDK not importable; returning no models")
        return []

    client = CopilotClient()
    try:
        await client.start()
        raw = await client.list_models()
    except Exception:
        log.exception("list_models failed")
        return []
    finally:
        try:
            await client.stop()
        except Exception:
            pass

    log.info("copilot list_models returned %d entries", len(raw or []))
    options: list[ModelOption] = []
    for m in raw or []:
        mid = getattr(m, "id", None)
        if not mid:
            continue
        billing = getattr(m, "billing", None)
        multiplier = getattr(billing, "multiplier", None) if billing else None
        options.append(
            ModelOption(
                id=mid,
                name=getattr(m, "name", mid),
                billing_multiplier=multiplier,
            )
        )
    log.info(
        "returning %d models to UI: %s",
        len(options),
        ", ".join(o.id for o in options) or "(none)",
    )
    return options
