"""Tests for the FastAPI web app."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from text_to_garmin import setup_store, webapi
from text_to_garmin.auth import GarminAuthRequiredError
from text_to_garmin.models import RunStep, Workout
from text_to_garmin.parser import ClarificationNeeded


def _sample_workout(name: str = "Test") -> Workout:
    return Workout(name=name, steps=[RunStep(duration=600)])


class _FakeSession:
    """Drop-in replacement for WorkoutParserSession used via monkeypatching."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.parse_calls = []
        self.reply_calls = []
        self.revise_calls = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True

    async def parse_web(self, description, workout_name="Workout", on_event=None):
        self.parse_calls.append((description, workout_name))
        if on_event is not None:
            await on_event({"stage": "sending_prompt"})
            await on_event({"stage": "received_response"})
        return self._outcomes.pop(0)

    async def reply_web(self, reply, on_event=None):
        self.reply_calls.append(reply)
        return self._outcomes.pop(0)

    async def revise_web(self, feedback, on_event=None):
        self.revise_calls.append(feedback)
        return self._outcomes.pop(0)


def _install_session(outcomes):
    """Patch ``WorkoutParserSession`` so every construction returns the fake."""
    sessions = []

    def factory(*args, **kwargs):
        fake = _FakeSession(outcomes)
        sessions.append(fake)
        return fake

    patcher = patch("text_to_garmin.draft_store.WorkoutParserSession", factory)
    patcher.start()
    return patcher, sessions


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure the store is empty between tests.
        import asyncio

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            webapi.store.close_all()
        )

    def test_health(self) -> None:
        with TestClient(webapi.app) as client:
            r = client.get("/api/health")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), {"status": "ok"})

    def test_create_draft_returns_preview(self) -> None:
        workout = _sample_workout()
        patcher, _ = _install_session([workout])
        try:
            with TestClient(webapi.app) as client:
                r = client.post(
                    "/api/drafts",
                    json={"description": "10 min easy", "name": "Easy"},
                )
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertEqual(body["status"], "preview_ready")
                self.assertIsNotNone(body["workout"])
                self.assertIn("Test", body["preview"])
                self.assertIsNotNone(body["draft_id"])
        finally:
            patcher.stop()

    def test_clarification_then_reply(self) -> None:
        workout = _sample_workout()
        patcher, sessions = _install_session(
            [ClarificationNeeded(question="How long rest?"), workout]
        )
        try:
            with TestClient(webapi.app) as client:
                r = client.post(
                    "/api/drafts",
                    json={"description": "4x 2min hills"},
                )
                body = r.json()
                self.assertEqual(body["status"], "needs_clarification")
                self.assertEqual(body["question"], "How long rest?")
                draft_id = body["draft_id"]

                r2 = client.post(
                    f"/api/drafts/{draft_id}/reply",
                    json={"reply": "90 seconds"},
                )
                body2 = r2.json()
                self.assertEqual(body2["status"], "preview_ready")
                self.assertEqual(sessions[0].reply_calls, ["90 seconds"])
        finally:
            patcher.stop()

    def test_accept_uploads_via_client(self) -> None:
        workout = _sample_workout()
        patcher, _ = _install_session([workout])

        fake_client = object()
        upload_calls = []

        def fake_upload(client, wk, schedule_date=None):
            upload_calls.append((client, wk))
            return {"workoutId": 42}

        try:
            with (
                TestClient(webapi.app) as client,
                patch(
                    "text_to_garmin.webapi.authenticate",
                    return_value=fake_client,
                ),
                patch(
                    "text_to_garmin.webapi.upload_workout_with_client",
                    side_effect=fake_upload,
                ),
            ):
                r = client.post("/api/drafts", json={"description": "x"})
                draft_id = r.json()["draft_id"]
                r2 = client.post(f"/api/drafts/{draft_id}/accept")
                self.assertEqual(r2.status_code, 200, r2.text)
                body = r2.json()
                self.assertEqual(body["status"], "uploaded")
                self.assertEqual(body["workout_id"], 42)
                self.assertEqual(len(upload_calls), 1)
                self.assertIs(upload_calls[0][0], fake_client)
        finally:
            patcher.stop()

    def test_accept_returns_auth_required_when_no_credentials(self) -> None:
        workout = _sample_workout()
        patcher, _ = _install_session([workout])
        try:
            with (
                TestClient(webapi.app) as client,
                patch(
                    "text_to_garmin.webapi.authenticate",
                    side_effect=GarminAuthRequiredError("no tokens"),
                ),
            ):
                r = client.post("/api/drafts", json={"description": "x"})
                draft_id = r.json()["draft_id"]
                r2 = client.post(f"/api/drafts/{draft_id}/accept")
                body = r2.json()
                self.assertEqual(body["status"], "auth_required")
                self.assertIn("no tokens", body["error"])
        finally:
            patcher.stop()

    def test_accept_forwards_credentials(self) -> None:
        workout = _sample_workout()
        patcher, _ = _install_session([workout])

        captured = {}

        def fake_authenticate(email=None, password=None, *, interactive=True):
            captured["email"] = email
            captured["password"] = password
            captured["interactive"] = interactive
            return object()

        try:
            with (
                TestClient(webapi.app) as client,
                patch(
                    "text_to_garmin.webapi.authenticate",
                    side_effect=fake_authenticate,
                ),
                patch(
                    "text_to_garmin.webapi.upload_workout_with_client",
                    return_value={"workoutId": 1},
                ),
            ):
                r = client.post("/api/drafts", json={"description": "x"})
                draft_id = r.json()["draft_id"]
                r2 = client.post(
                    f"/api/drafts/{draft_id}/accept",
                    json={"email": "u@example.com", "password": "pw"},
                )
                self.assertEqual(r2.status_code, 200, r2.text)
                self.assertEqual(captured["email"], "u@example.com")
                self.assertEqual(captured["password"], "pw")
                self.assertFalse(captured["interactive"])
        finally:
            patcher.stop()

    def test_accept_overrides_workout_name(self) -> None:
        workout = _sample_workout(name="LLM Suggested")
        patcher, _ = _install_session([workout])

        uploaded = {}

        def fake_upload(client, wk, schedule_date=None):
            uploaded["name"] = wk.name
            return {"workoutId": 7}

        try:
            with (
                TestClient(webapi.app) as client,
                patch(
                    "text_to_garmin.webapi.authenticate",
                    return_value=object(),
                ),
                patch(
                    "text_to_garmin.webapi.upload_workout_with_client",
                    side_effect=fake_upload,
                ),
            ):
                r = client.post("/api/drafts", json={"description": "x"})
                draft_id = r.json()["draft_id"]
                r2 = client.post(
                    f"/api/drafts/{draft_id}/accept",
                    json={"name": "User Edited Name"},
                )
                self.assertEqual(r2.status_code, 200, r2.text)
                self.assertEqual(uploaded["name"], "User Edited Name")
        finally:
            patcher.stop()

    def test_delete_draft(self) -> None:
        workout = _sample_workout()
        patcher, _ = _install_session([workout])
        try:
            with TestClient(webapi.app) as client:
                r = client.post("/api/drafts", json={"description": "x"})
                draft_id = r.json()["draft_id"]
                r2 = client.delete(f"/api/drafts/{draft_id}")
                self.assertEqual(r2.status_code, 200)
                r3 = client.delete(f"/api/drafts/{draft_id}")
                self.assertEqual(r3.status_code, 404)
        finally:
            patcher.stop()


class SetupApiTests(unittest.TestCase):
    """Cover /api/setup/status, /api/setup/copilot POST + DELETE."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env_patch = patch.dict(
            os.environ,
            {"TEXT_TO_GARMIN_STATE_DIR": self._tmp.name},
            clear=False,
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        # Make sure no leftover env token leaks in from the host shell.
        os.environ.pop("COPILOT_GITHUB_TOKEN", None)
        # Pretend a `copilot login` config never exists on disk.
        self._local_patch = patch.object(
            webapi, "_has_local_copilot_config", return_value=False
        )
        self._local_patch.start()
        self.addCleanup(self._local_patch.stop)

    def test_status_unconfigured(self) -> None:
        with TestClient(webapi.app) as client:
            r = client.get("/api/setup/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["copilot_configured"])
        self.assertIn("garmin_tokens_cached", body)

    def test_post_copilot_rejects_empty(self) -> None:
        with TestClient(webapi.app) as client:
            r = client.post("/api/setup/copilot", json={"token": "   "})
        self.assertEqual(r.status_code, 400)

    def test_post_copilot_persists_when_probe_succeeds(self) -> None:
        async def fake_probe():
            return webapi.SetupStatus(
                copilot_configured=True,
                copilot_login="octocat",
                garmin_tokens_cached=False,
            )

        with patch.object(webapi, "_probe_copilot_auth", side_effect=fake_probe):
            with TestClient(webapi.app) as client:
                r = client.post(
                    "/api/setup/copilot",
                    json={"token": "github_pat_validlooking"},
                )

        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["copilot_configured"])
        self.assertEqual(body["copilot_login"], "octocat")
        # Token landed in the persistent store and in the live env.
        self.assertEqual(setup_store.get_copilot_token(), "github_pat_validlooking")
        self.assertEqual(
            os.environ.get("COPILOT_GITHUB_TOKEN"), "github_pat_validlooking"
        )

    def test_post_copilot_rolls_back_on_failed_probe(self) -> None:
        async def fake_probe():
            return webapi.SetupStatus(
                copilot_configured=False,
                copilot_error="bad token",
                garmin_tokens_cached=False,
            )

        with patch.object(webapi, "_probe_copilot_auth", side_effect=fake_probe):
            with TestClient(webapi.app) as client:
                r = client.post(
                    "/api/setup/copilot",
                    json={"token": "github_pat_invalid"},
                )

        self.assertEqual(r.status_code, 400)
        self.assertIn("bad token", r.text)
        self.assertIsNone(setup_store.get_copilot_token())
        self.assertNotIn("COPILOT_GITHUB_TOKEN", os.environ)

    def test_delete_copilot_clears_token(self) -> None:
        setup_store.set_copilot_token("github_pat_existing")
        self.assertEqual(setup_store.get_copilot_token(), "github_pat_existing")

        async def fake_probe():
            return webapi.SetupStatus(
                copilot_configured=False, garmin_tokens_cached=False
            )

        with patch.object(webapi, "_probe_copilot_auth", side_effect=fake_probe):
            with TestClient(webapi.app) as client:
                r = client.delete("/api/setup/copilot")

        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["copilot_configured"])
        self.assertIsNone(setup_store.get_copilot_token())
        self.assertNotIn("COPILOT_GITHUB_TOKEN", os.environ)


class RecentWorkoutsApiTests(unittest.TestCase):
    """Cover /api/workouts/list and /api/workouts/{id}/delete."""

    def test_list_returns_workouts_when_authenticated(self) -> None:
        fake_client = object()
        sample = [
            {
                "workout_id": 101,
                "name": "Easy run",
                "sport_type": "running",
                "estimated_duration_s": 1800,
                "estimated_distance_m": 5000,
                "created_date": "2026-04-10T00:00:00",
                "updated_date": "2026-04-10T00:00:00",
                "description": None,
            }
        ]
        with (
            patch.object(webapi, "authenticate", return_value=fake_client),
            patch.object(
                webapi, "list_workouts_with_client", return_value=sample
            ) as mock_list,
        ):
            with TestClient(webapi.app) as client:
                r = client.post("/api/workouts/list", json={"limit": 5})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["workouts"]), 1)
        self.assertEqual(body["workouts"][0]["workout_id"], 101)
        mock_list.assert_called_once_with(fake_client, limit=5)

    def test_list_returns_auth_required_when_no_credentials(self) -> None:
        def fail(*_a, **_kw):
            raise GarminAuthRequiredError("need login")

        with patch.object(webapi, "authenticate", side_effect=fail):
            with TestClient(webapi.app) as client:
                r = client.post("/api/workouts/list", json={})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "auth_required")
        self.assertEqual(body["workouts"], [])
        self.assertIn("need login", body["error"])

    def test_delete_returns_ok(self) -> None:
        fake_client = object()
        with (
            patch.object(webapi, "authenticate", return_value=fake_client),
            patch.object(webapi, "delete_workout_with_client") as mock_del,
        ):
            with TestClient(webapi.app) as client:
                r = client.post("/api/workouts/42/delete", json={})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["workout_id"], 42)
        mock_del.assert_called_once_with(fake_client, 42)

    def test_delete_returns_auth_required(self) -> None:
        def fail(*_a, **_kw):
            raise GarminAuthRequiredError("login plz")

        with patch.object(webapi, "authenticate", side_effect=fail):
            with TestClient(webapi.app) as client:
                r = client.post("/api/workouts/42/delete", json={})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "auth_required")
        self.assertEqual(body["workout_id"], 42)


class AuthTests(unittest.TestCase):
    """Tests for the shared-password auth middleware and endpoints."""

    _VARS = ("APP_PASSWORD", "APP_SESSION_SECRET")

    def setUp(self) -> None:
        for var in self._VARS:
            os.environ.pop(var, None)

    def tearDown(self) -> None:
        # Don't leak auth env vars into sibling test classes — the middleware
        # reads os.environ on every request.
        for var in self._VARS:
            os.environ.pop(var, None)

    def _with_auth_env(self, password: str = "s3cret") -> None:
        os.environ["APP_PASSWORD"] = password
        os.environ["APP_SESSION_SECRET"] = "x" * 48

    def test_dev_mode_allows_unauthenticated_api_calls(self) -> None:
        # APP_PASSWORD is unset (cleared in setUp)
        with TestClient(webapi.app) as client:
            r = client.get("/api/health")
            self.assertEqual(r.status_code, 200)
            me = client.get("/api/auth/me")
            self.assertEqual(me.status_code, 200)
            self.assertTrue(me.json().get("dev_mode"))

    def test_auth_enabled_rejects_unauthenticated_api_calls(self) -> None:
        self._with_auth_env()
        with TestClient(webapi.app) as client:
            r = client.post("/api/drafts", json={"description": "x"})
            self.assertEqual(r.status_code, 401)
            body = r.json()
            self.assertFalse(body["authenticated"])

    def test_auth_enabled_health_still_public(self) -> None:
        self._with_auth_env()
        with TestClient(webapi.app) as client:
            r = client.get("/api/health")
            self.assertEqual(r.status_code, 200)

    def test_login_wrong_password_rejected(self) -> None:
        self._with_auth_env("right-password")
        with TestClient(webapi.app) as client:
            r = client.post("/api/auth/login", json={"password": "wrong"})
            self.assertEqual(r.status_code, 401)
            me = client.get("/api/auth/me")
            self.assertEqual(me.status_code, 401)

    def test_login_correct_password_grants_session(self) -> None:
        self._with_auth_env("right-password")
        with TestClient(webapi.app) as client:
            r = client.post("/api/auth/login", json={"password": "right-password"})
            self.assertEqual(r.status_code, 204)

            me = client.get("/api/auth/me")
            self.assertEqual(me.status_code, 200)
            body = me.json()
            self.assertTrue(body["authenticated"])
            self.assertFalse(body.get("dev_mode", False))

            # Logout clears the session.
            out = client.post("/api/auth/logout")
            self.assertEqual(out.status_code, 204)
            me2 = client.get("/api/auth/me")
            self.assertEqual(me2.status_code, 401)

    def test_login_missing_password_rejected(self) -> None:
        self._with_auth_env("right-password")
        with TestClient(webapi.app) as client:
            r = client.post("/api/auth/login", json={"password": ""})
            self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
