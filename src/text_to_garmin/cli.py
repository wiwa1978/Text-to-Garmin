"""Interactive CLI interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from rich.console import Console
from rich.panel import Panel

console = Console()


def _parse_date(date_str: str) -> datetime:
    """Parse a date string into a datetime."""
    if not date_str:
        return None

    date_str_lower = date_str.strip().lower()

    if date_str_lower in ("today",):
        return datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    elif date_str_lower in ("tomorrow",):
        return (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    elif date_str_lower.startswith("+"):
        val = date_str_lower[1:]
        if val.endswith("d"):
            days = int(val[:-1])
            return (datetime.now() + timedelta(days=days)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif val.endswith("w"):
            weeks = int(val[:-1])
            return (datetime.now() + timedelta(weeks=weeks)).replace(hour=9, minute=0, second=0, microsecond=0)

    # Day-of-week names → next occurrence
    day_names = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    if date_str_lower in day_names:
        target = day_names[date_str_lower]
        today = datetime.now()
        days_ahead = (target - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # if today is that day, pick next week
        return (today + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(hour=9, minute=0, second=0, microsecond=0)
        except ValueError:
            continue

    raise ValueError(f"Unrecognized date format: {date_str}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="text-to-garmin",
        description="Convert natural language workout descriptions to Garmin Connect workouts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  text-to-garmin "W/u, 20min easy, 4x 2min hills @ 10k effort, c/d"
  text-to-garmin "5x 1km @ 5k pace with 90s rest" -n "5x1km VO2max"
  text-to-garmin --json-only "10x 400m @ mile pace, 200m jog rest"
  text-to-garmin "tempo run" -n "Tempo" -d tomorrow
  text-to-garmin "long run" -d 2026-03-15
  text-to-garmin  (interactive mode - will prompt for description)
""",
    )
    parser.add_argument(
        "description",
        nargs="?",
        default=None,
        help="Workout description in natural language",
    )
    parser.add_argument(
        "-n", "--name",
        default="Workout",
        help="Workout name (default: Workout)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Output Garmin JSON only (no upload)",
    )
    parser.add_argument(
        "--save",
        nargs="?",
        const="workout.json",
        default=None,
        metavar="FILE",
        help="Save Garmin JSON to file (default: workout.json)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Parse and preview only, skip upload",
    )
    parser.add_argument(
        "-d", "--date",
        default=None,
        help="Schedule workout for a date. Formats: YYYY-MM-DD, tomorrow, +3d, +1w",
    )
    return parser.parse_args(argv)


async def _async_main(args: argparse.Namespace) -> int:
    from .parser import WorkoutParserSession
    from .models import format_workout_preview
    from .uploader import upload_workout, save_workout_json
    from .builder import workout_to_json_string

    # Get description
    description = args.description
    if not description:
        console.print("[bold]Enter your workout description:[/bold]")
        description = input("> ").strip()
        if not description:
            console.print("[red]No workout description provided.[/red]")
            return 1

    # Parse workout
    console.print()
    console.print("[bold cyan]Parsing workout...[/bold cyan]")

    try:
        async with WorkoutParserSession() as parser_session:
            workout = await parser_session.parse(description, workout_name=args.name)

            # Confirmation loop
            while True:
                preview = format_workout_preview(workout)
                console.print()
                console.print(Panel(preview, title="Workout Preview", border_style="green"))

                if args.json_only:
                    console.print()
                    console.print(workout_to_json_string(workout))
                    return 0

                console.print()
                response = input("Does this look correct? [Y/n/edit] ").strip()

                if response.lower() in ("", "y", "yes"):
                    break
                elif response.lower() in ("n", "no"):
                    console.print("[yellow]Workout cancelled.[/yellow]")
                    return 0
                else:
                    # Treat any other input as revision feedback
                    console.print("[bold cyan]Revising workout...[/bold cyan]")
                    try:
                        workout = await parser_session.revise(response)
                    except RuntimeError as exc:
                        console.print(f"[red]Revision failed: {exc}[/red]")

    except RuntimeError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        return 1

    # Save to file
    if args.save:
        save_workout_json(workout, args.save)

    # Parse schedule date
    schedule_date = None
    if args.date:
        try:
            schedule_date = _parse_date(args.date)
            console.print(f"[dim]📅 Will schedule for: {schedule_date.strftime('%Y-%m-%d')}[/dim]")
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1

    # Upload
    if not args.no_upload:
        console.print()
        result = upload_workout(workout, schedule_date=schedule_date)
        return 0 if result is not None else 1

    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        exit_code = asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
