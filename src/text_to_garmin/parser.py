"""LLM-powered workout parser using Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import re

from rich.console import Console

from .models import Workout

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


def _extract_json(text: str) -> str | None:
    """Extract JSON from a ```json ... ``` code block."""
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    return None


async def _collect_response(session, prompt: str) -> str:
    """Send a prompt and collect the full assistant response."""
    done = asyncio.Event()
    response_parts: list[str] = []

    def on_event(event):
        if event.type.value == "assistant.message_delta":
            if event.data.delta_content:
                response_parts.append(event.data.delta_content)
        elif event.type.value == "assistant.message":
            if event.data.content:
                response_parts.append(event.data.content)
        elif event.type.value == "session.idle":
            done.set()

    unsubscribe = session.on(on_event)
    try:
        await session.send({"prompt": prompt})
        await done.wait()
    finally:
        unsubscribe()

    return "".join(response_parts)


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

    raise RuntimeError(
        f"Workout parsing did not complete within {MAX_TURNS} turns."
    )


class WorkoutParserSession:
    """Manages a Copilot session for parsing and revising workouts."""

    def __init__(self):
        self._client = None
        self._session = None
        self._workout_name: str = "Workout"

    async def __aenter__(self):
        try:
            from copilot import CopilotClient
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

        self._session = await self._client.create_session({
            "model": "gpt-4",
            "system_message": SYSTEM_MESSAGE,
        })
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.destroy()
        if self._client:
            await self._client.stop()

    async def parse(self, description: str, workout_name: str = "Workout") -> Workout:
        """Parse a workout description. Same logic as standalone parse_workout."""
        self._workout_name = workout_name
        initial_prompt = (
            f"Parse this workout into JSON. "
            f'Workout name: "{workout_name}"\n\n{description}'
        )
        response = await _collect_response(self._session, initial_prompt)
        return await _parse_response_to_workout(
            self._session, response, workout_name,
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
            self._session, response, self._workout_name,
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
