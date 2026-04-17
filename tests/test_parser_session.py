import sys
import types
import unittest
from unittest.mock import patch

from text_to_garmin.parser import SYSTEM_MESSAGE, WorkoutParserSession


class _FakeSession:
    def __init__(self) -> None:
        self.destroyed = False

    async def destroy(self) -> None:
        self.destroyed = True


class _FakeCopilotClient:
    last_instance = None

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.session = _FakeSession()
        self.create_session_kwargs = None
        _FakeCopilotClient.last_instance = self

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def create_session(self, **kwargs):
        self.create_session_kwargs = kwargs
        return self.session


class _FakePermissionHandler:
    @staticmethod
    def approve_all(*_args, **_kwargs):
        return {"kind": "approved"}


class WorkoutParserSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_created_with_keyword_arguments(self) -> None:
        fake_copilot = types.SimpleNamespace(CopilotClient=_FakeCopilotClient)
        fake_copilot_session = types.SimpleNamespace(
            PermissionHandler=_FakePermissionHandler,
        )

        with patch.dict(
            sys.modules,
            {
                "copilot": fake_copilot,
                "copilot.session": fake_copilot_session,
            },
        ):
            with patch("text_to_garmin.parser.DEFAULT_MODEL", None):
                session_manager = WorkoutParserSession()
                async with session_manager:
                    client = _FakeCopilotClient.last_instance
                    self.assertIsNotNone(client)
                    self.assertTrue(client.started)
                    self.assertEqual(
                        client.create_session_kwargs,
                        {
                            "on_permission_request": _FakePermissionHandler.approve_all,
                            "system_message": {"content": SYSTEM_MESSAGE},
                        },
                    )

            self.assertTrue(client.session.destroyed)
            self.assertTrue(client.stopped)

    async def test_session_uses_configured_model_override(self) -> None:
        fake_copilot = types.SimpleNamespace(CopilotClient=_FakeCopilotClient)
        fake_copilot_session = types.SimpleNamespace(
            PermissionHandler=_FakePermissionHandler,
        )

        with patch.dict(
            sys.modules,
            {
                "copilot": fake_copilot,
                "copilot.session": fake_copilot_session,
            },
        ):
            with patch("text_to_garmin.parser.DEFAULT_MODEL", "gpt-5"):
                session_manager = WorkoutParserSession()
                async with session_manager:
                    client = _FakeCopilotClient.last_instance
                    self.assertEqual(
                        client.create_session_kwargs,
                        {
                            "on_permission_request": _FakePermissionHandler.approve_all,
                            "model": "gpt-5",
                            "system_message": {"content": SYSTEM_MESSAGE},
                        },
                    )


if __name__ == "__main__":
    unittest.main()
