import unittest
from pathlib import Path
from unittest.mock import patch

from garminconnect import GarminConnectTooManyRequestsError

from text_to_garmin.auth import (
    GarminAuthRequiredError,
    LEGACY_TOKEN_DIR,
    TOKEN_DIR,
    _format_auth_error,
    _resolve_tokenstore,
    authenticate,
    get_garmin_client,
)


class AuthTests(unittest.TestCase):
    def test_rate_limited_login_error_is_actionable(self) -> None:
        message = _format_auth_error(GarminConnectTooManyRequestsError("blocked"))

        self.assertIn("blocked or rate-limited", message)
        self.assertIn(str(_resolve_tokenstore()), message)

    def test_prefers_default_token_dir(self) -> None:
        with patch(
            "text_to_garmin.auth.LEGACY_TOKEN_DIR", Path("/tmp/legacy-tokenstore")
        ):
            with patch(
                "text_to_garmin.auth.TOKEN_DIR", Path("/tmp/default-tokenstore")
            ):
                with patch("pathlib.Path.exists", side_effect=[True]):
                    self.assertEqual(
                        _resolve_tokenstore(), Path("/tmp/default-tokenstore")
                    )

    def test_falls_back_to_legacy_token_dir(self) -> None:
        with patch(
            "text_to_garmin.auth.LEGACY_TOKEN_DIR", Path("/tmp/legacy-tokenstore")
        ):
            with patch(
                "text_to_garmin.auth.TOKEN_DIR", Path("/tmp/default-tokenstore")
            ):
                with patch("pathlib.Path.exists", side_effect=[False, True]):
                    self.assertEqual(
                        _resolve_tokenstore(), Path("/tmp/legacy-tokenstore")
                    )

    def test_get_garmin_client_returns_authenticated_client(self) -> None:
        garmin_client = object()

        with patch("text_to_garmin.auth.authenticate", return_value=garmin_client):
            client = get_garmin_client()

        self.assertIs(client, garmin_client)

    def test_noninteractive_raises_when_no_tokens_and_no_env(self) -> None:
        with (
            patch("text_to_garmin.auth.TOKEN_DIR", Path("/nonexistent/tokens.json")),
            patch("text_to_garmin.auth.LEGACY_TOKEN_DIR", Path("/nonexistent/legacy")),
            patch.dict("os.environ", {}, clear=False),
        ):
            import os

            os.environ.pop("GARMIN_EMAIL", None)
            os.environ.pop("GARMIN_PASSWORD", None)
            with self.assertRaises(GarminAuthRequiredError):
                authenticate(interactive=False)


if __name__ == "__main__":
    unittest.main()
