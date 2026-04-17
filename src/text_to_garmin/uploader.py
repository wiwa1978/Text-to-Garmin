"""Upload workouts to Garmin Connect."""

from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console

from .models import Workout
from .builder import build_garmin_workout
from .auth import get_garmin_client

console = Console()


def upload_workout_with_client(
    client,
    workout: Workout,
    schedule_date: datetime | None = None,
) -> dict:
    """
    Upload a workout using a pre-authenticated Garmin client.

    Raises exceptions from the underlying client on failure (the caller is
    responsible for translating them). This is the web-safe variant.
    """
    garmin_json = build_garmin_workout(workout)
    result = client.upload_workout(garmin_json)

    if schedule_date and isinstance(result, dict):
        workout_id = result.get("workoutId")
        if workout_id:
            date_str = schedule_date.strftime("%Y-%m-%d")
            client.schedule_workout(workout_id, date_str)

    return result


def upload_workout(
    workout: Workout,
    schedule_date: datetime | None = None,
) -> dict | None:
    """
    Upload a workout to Garmin Connect and optionally schedule it.

    1. Gets authenticated Garmin client (handles auth internally)
    2. Builds the Garmin JSON from the Workout model
    3. Uploads via garminconnect library
    4. Optionally schedules for *schedule_date*
    5. Returns the API response dict, or None on failure
    """
    garmin_json = build_garmin_workout(workout)

    console.print("\n[bold]Uploading workout to Garmin Connect...[/bold]")

    try:
        client = get_garmin_client()
        result = client.upload_workout(garmin_json)

        console.print("[green]✅ Workout uploaded successfully![/green]")

        if schedule_date and result:
            workout_id = None
            if isinstance(result, dict):
                workout_id = result.get("workoutId")

            if workout_id:
                try:
                    date_str = schedule_date.strftime("%Y-%m-%d")
                    client.schedule_workout(workout_id, date_str)
                    console.print(f"[green]📅 Workout scheduled for {date_str}[/green]")
                except Exception as exc:
                    console.print(
                        f"[yellow]⚠️  Upload succeeded but scheduling failed: {exc}[/yellow]"
                    )
                    console.print(
                        "[dim]You can manually schedule it at https://connect.garmin.com/modern/workouts[/dim]"
                    )
            else:
                console.print(
                    "[yellow]⚠️  Could not extract workout ID for scheduling.[/yellow]"
                )

        console.print("[dim]View at: https://connect.garmin.com/modern/workouts[/dim]")
        return result
    except Exception as exc:
        console.print(f"[red]❌ Upload failed: {exc}[/red]")
        return None


def save_workout_json(workout: Workout, path: str = "workout.json") -> str:
    """Save workout as Garmin JSON file (for manual upload or debugging)."""
    garmin_json = build_garmin_workout(workout)
    with open(path, "w") as f:
        json.dump(garmin_json, f, indent=2)
    console.print(f"[green]💾 Workout saved to {path}[/green]")
    return path


def list_workouts_with_client(client, limit: int = 20) -> list[dict]:
    """Return the user's most recent Garmin Connect workouts.

    The raw garminconnect response is a list of dicts with a stable-ish
    shape; we pass through the useful keys plus a flattened ``sport_type``.
    """
    raw = client.get_workouts(0, max(1, min(limit, 100))) or []
    out: list[dict] = []
    for w in raw:
        if not isinstance(w, dict):
            continue
        sport = w.get("sportType") or {}
        sport_key = (
            sport.get("sportTypeKey") if isinstance(sport, dict) else None
        ) or w.get("sportTypeKey")
        out.append(
            {
                "workout_id": w.get("workoutId"),
                "name": w.get("workoutName") or "(unnamed)",
                "description": w.get("description"),
                "sport_type": sport_key,
                "estimated_duration_s": w.get("estimatedDurationInSecs"),
                "estimated_distance_m": w.get("estimatedDistanceInMeters"),
                "created_date": w.get("createdDate"),
                "updated_date": w.get("updatedDate"),
            }
        )
    return out


def delete_workout_with_client(client, workout_id: int | str) -> None:
    """Delete a workout from Garmin Connect."""
    client.delete_workout(workout_id)
