"""Upload workouts to Garmin Connect."""

from __future__ import annotations

import json
from datetime import datetime
from rich.console import Console
import garth
from .models import Workout
from .builder import build_garmin_workout
from .auth import get_garmin_client

console = Console()


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
                    endpoint = f"/workout-service/schedule/{workout_id}"
                    garth.connectapi(endpoint, method="POST", json={"date": date_str})
                    console.print(f"[green]📅 Workout scheduled for {date_str}[/green]")
                except Exception as exc:
                    console.print(f"[yellow]⚠️  Upload succeeded but scheduling failed: {exc}[/yellow]")
                    console.print("[dim]You can manually schedule it at https://connect.garmin.com/modern/workouts[/dim]")
            else:
                console.print("[yellow]⚠️  Could not extract workout ID for scheduling.[/yellow]")

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
