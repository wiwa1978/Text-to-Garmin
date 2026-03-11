import unittest

from pydantic import ValidationError

from text_to_garmin.builder import build_garmin_workout
from text_to_garmin.models import DurationType, RestStep, Workout, format_workout_preview


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


if __name__ == "__main__":
    unittest.main()
