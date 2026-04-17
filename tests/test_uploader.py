import unittest
from datetime import datetime
from unittest.mock import patch

from text_to_garmin.models import DurationType, RestStep, Workout
from text_to_garmin.uploader import upload_workout


class UploaderTests(unittest.TestCase):
    def test_schedule_uses_garmin_client_api(self) -> None:
        workout = Workout(
            steps=[RestStep(duration_type=DurationType.TIME, duration=90)]
        )
        fake_client = type("FakeClient", (), {})()
        fake_client.upload_workout = lambda _payload: {"workoutId": 123}
        fake_client.schedule_calls = []

        def schedule_workout(workout_id, date_str):
            fake_client.schedule_calls.append((workout_id, date_str))

        fake_client.schedule_workout = schedule_workout

        with patch(
            "text_to_garmin.uploader.get_garmin_client", return_value=fake_client
        ):
            result = upload_workout(workout, datetime(2026, 4, 20))

        self.assertEqual(result, {"workoutId": 123})
        self.assertEqual(fake_client.schedule_calls, [(123, "2026-04-20")])


if __name__ == "__main__":
    unittest.main()
