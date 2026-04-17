import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from text_to_garmin.builder import build_garmin_workout
from text_to_garmin.models import (
    DurationType,
    RestStep,
    Workout,
    format_workout_preview,
)
from text_to_garmin.uploader import save_workout_json


class RestStepRegressionTests(unittest.TestCase):
    def test_time_rest_with_zero_duration_builds_time_end_condition(self) -> None:
        workout = Workout(
            steps=[
                RestStep(duration_type=DurationType.TIME, duration=0),
            ],
        )

        garmin_json = build_garmin_workout(workout)
        step_json = garmin_json["workoutSegments"][0]["workoutSteps"][0]

        self.assertEqual(step_json["endCondition"]["conditionTypeKey"], "time")
        self.assertEqual(step_json["endConditionValue"], 0.0)

    def test_lap_button_rest_builds_lap_button_end_condition(self) -> None:
        workout = Workout(
            steps=[
                RestStep(duration_type=DurationType.LAP_BUTTON, duration=None),
            ],
        )

        garmin_json = build_garmin_workout(workout)
        step_json = garmin_json["workoutSegments"][0]["workoutSteps"][0]

        self.assertEqual(step_json["endCondition"]["conditionTypeKey"], "lap.button")
        self.assertIsNone(step_json["endConditionValue"])

    def test_lap_button_rest_preview_contains_until_lap_button(self) -> None:
        workout = Workout(
            steps=[
                RestStep(duration_type=DurationType.LAP_BUTTON, duration=None),
            ],
        )

        preview = format_workout_preview(workout)

        self.assertIn("😴 Rest (until lap button)", preview)

    def test_non_lap_button_rest_requires_duration(self) -> None:
        with self.assertRaises(ValidationError):
            RestStep(duration_type=DurationType.TIME, duration=None)

    def test_save_workout_json_does_not_require_garth(self) -> None:
        workout = Workout(
            steps=[
                RestStep(duration_type=DurationType.TIME, duration=90),
            ],
        )

        original_import = __import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "garth":
                raise ModuleNotFoundError("No module named 'garth'")
            return original_import(name, globals, locals, fromlist, level)

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "workout.json"

            with patch("builtins.__import__", side_effect=guarded_import):
                saved_path = save_workout_json(workout, str(output_path))

            self.assertEqual(saved_path, str(output_path))
            self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
