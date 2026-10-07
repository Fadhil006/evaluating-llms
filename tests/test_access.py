import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.response import addinfourl

from evaluation.access import preflight
from evaluation.openrouter import _RejectRedirects


SECRET = "test-secret-do-not-expose"
DATA = {"data": {"free_model_daily_requests": {"remaining": 5, "limit": 50},
                 "limit": 10, "limit_remaining": 3}}


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_path = Path(self.temp.name) / ".env"
        path_patch = patch("evaluation.access._ENV_PATH", self.env_path)
        path_patch.start()
        self.addCleanup(path_patch.stop)
        env_patch = patch.dict(os.environ, {}, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def write_env(self, text, mode=0o600):
        self.env_path.write_text(text, encoding="utf-8")
        self.env_path.chmod(mode)

    def test_env_file_and_safe_result(self):
        self.write_env(f"OTHER=not-loaded\nOPENROUTER_API_KEY='{SECRET}'\n")
        with patch("evaluation.access.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(DATA).encode())
            self.assertEqual(preflight(4), {"free_remaining": 5, "free_limit": 50,
                                            "spend_limit": 10, "spend_remaining": 3})
            request, = opener.return_value.open.call_args.args
            self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/key")
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            self.assertEqual(request.get_header("Authorization"), f"Bearer {SECRET}")
            self.assertIsInstance(opener.call_args.args[0], _RejectRedirects)
            self.assertEqual(opener.return_value.open.call_args.kwargs, {"timeout": 10})
        self.assertEqual(os.environ["OPENROUTER_API_KEY"], SECRET)
        self.assertNotIn("OTHER", os.environ)

    def test_existing_env_key_takes_priority_and_missing_key_fails(self):
        with patch("evaluation.access.build_opener") as opener:
            with self.assertRaises(ValueError):
                preflight(1)
            opener.assert_not_called()
            self.write_env("OPENROUTER_API_KEY=from-file\n")
            os.environ["OPENROUTER_API_KEY"] = SECRET
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(DATA).encode())
            preflight(1)
            self.assertEqual(opener.return_value.open.call_args.args[0].get_header("Authorization"),
                             f"Bearer {SECRET}")

    def test_unsafe_or_invalid_env_does_not_set_key_or_send_request(self):
        with patch("evaluation.access.build_opener") as opener:
            for content, mode in ((f"OPENROUTER_API_KEY={SECRET}\n", 0o644),
                                  (f"OPENROUTER_API_KEY={SECRET}\n", 0o640),
                                  ("OPENROUTER_API_KEY=\n", 0o600),
                                  ("OPENROUTER_API_KEY=$(bad) extra\n", 0o600),
                                  ("OTHER=x\n", 0o600)):
                with self.subTest(content=content, mode=mode):
                    self.write_env(content, mode)
                    with self.assertRaises(ValueError) as caught:
                        preflight(1)
                    self.assertNotIn(SECRET, str(caught.exception))
                    self.assertNotIn("OPENROUTER_API_KEY", os.environ)
            self.env_path.unlink()
            self.env_path.symlink_to(Path(self.temp.name) / "actual")
            (Path(self.temp.name) / "actual").write_text(f"OPENROUTER_API_KEY={SECRET}\n")
            with self.assertRaises(ValueError):
                preflight(1)
            opener.assert_not_called()

    def test_bad_request_count_never_contacts_provider(self):
        os.environ["OPENROUTER_API_KEY"] = SECRET
        with patch("evaluation.access.build_opener") as opener:
            for count in (True, 0, 51, 1.0, "1"):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    preflight(count)
            opener.assert_not_called()

    def test_48_requires_48_free_requests(self):
        os.environ["OPENROUTER_API_KEY"] = SECRET
        with patch("evaluation.access.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(DATA).encode())
            with self.assertRaisesRegex(ValueError, "quota"):
                preflight(48)
            data = json.loads(json.dumps(DATA))
            data["data"]["free_model_daily_requests"]["remaining"] = 48
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            self.assertEqual(preflight(48)["free_remaining"], 48)

    def test_confirmed_free_tier_does_not_need_spending_cap(self):
        os.environ["OPENROUTER_API_KEY"] = SECRET
        data = {"data": {"is_free_tier": True,
                         "free_model_daily_requests": {"remaining": 50, "limit": 50},
                         "limit": None, "limit_remaining": None}}
        with patch("evaluation.access.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            self.assertEqual(preflight(4), {"free_remaining": 50, "free_limit": 50,
                                            "spend_limit": None, "spend_remaining": None})
            del data["data"]["limit"]
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            self.assertIsNone(preflight(4)["spend_limit"])

            data["data"]["free_model_daily_requests"]["remaining"] = 3
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            with self.assertRaisesRegex(ValueError, "quota"):
                preflight(4)

            data["data"]["free_model_daily_requests"]["remaining"] = 50
            data["data"]["limit_remaining"] = 0
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            with self.assertRaisesRegex(ValueError, "quota"):
                preflight(4)

    def test_unconfirmed_tier_still_needs_spending_cap(self):
        os.environ["OPENROUTER_API_KEY"] = SECRET
        with patch("evaluation.access.build_opener") as opener:
            for tier in (False, None, 1, "true"):
                data = {"data": {"is_free_tier": tier,
                                 "free_model_daily_requests": {"remaining": 50, "limit": 50},
                                 "limit": None}}
                opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
                with self.subTest(tier=tier), self.assertRaisesRegex(ValueError, "quota"):
                    preflight(4)

    def test_invalid_missing_or_insufficient_quotas_fail_closed(self):
        self.write_env(f"OPENROUTER_API_KEY=\"{SECRET}\"\n")
        with patch("evaluation.access.build_opener") as opener:
            for change in ({"limit": None}, {"limit": -1}, {"limit": "10"},
                           {"limit": 0}, {"limit_remaining": 0},
                           {"limit_remaining": -1}, {"limit_remaining": float("nan")}):
                data = json.loads(json.dumps(DATA))
                data["data"].update(change)
                opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(
                    json.dumps(data).encode())
                with self.subTest(change=change), self.assertRaises(ValueError) as caught:
                    preflight(4)
                self.assertNotIn(SECRET, str(caught.exception))
                self.assertNotIn("OPENROUTER_API_KEY", os.environ)
            for data in ({"data": {"free_model_daily_requests": {"limit": 50, "remaining": 3},
                                    "limit": 10}},
                         {"data": {"free_model_daily_requests": {"limit": 50, "remaining": True},
                                    "limit": 10}},
                         {"data": {"free_model_daily_requests": {"limit": 50, "remaining": 5}}}):
                opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(
                    json.dumps(data).encode())
                with self.subTest(data=data), self.assertRaises(ValueError):
                    preflight(4)
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(
                json.dumps({"data": {**DATA["data"], "limit_remaining": None}}).encode())
            self.assertIsNone(preflight(4)["spend_remaining"])

    def test_http_invalid_json_and_redirect_errors_are_sanitized(self):
        self.write_env(f"OPENROUTER_API_KEY={SECRET}\n")
        with patch("evaluation.access.build_opener") as opener:
            for failure in (URLError(SECRET), HTTPError("https://redirect.invalid/" + SECRET, 302,
                           SECRET, {"Location": "https://redirect.invalid/" + SECRET},
                           io.BytesIO(SECRET.encode()))):
                opener.return_value.open.side_effect = failure
                with self.subTest(failure=type(failure)), self.assertRaises(RuntimeError) as caught:
                    preflight(1)
                self.assertNotIn(SECRET, str(caught.exception))
                self.assertNotIn("redirect.invalid", str(caught.exception))
                self.assertNotIn("OPENROUTER_API_KEY", os.environ)
            opener.return_value.open.side_effect = None
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(SECRET.encode())
            with self.assertRaises(RuntimeError) as caught:
                preflight(1)
            self.assertNotIn(SECRET, str(caught.exception))

    def test_redirect_never_forwards_authorization(self):
        self.write_env(f"OPENROUTER_API_KEY={SECRET}\n")
        requests = []

        def transport(handler, request):
            requests.append(request)
            response = addinfourl(io.BytesIO(SECRET.encode()),
                                   {"Location": "https://redirect.example.invalid/collect"},
                                   request.full_url, 302)
            response.msg = SECRET
            return response

        with patch("urllib.request.HTTPSHandler.https_open", transport):
            with self.assertRaises(RuntimeError) as caught:
                preflight(1)
        self.assertEqual(len(requests), 1)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertNotIn("OPENROUTER_API_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
