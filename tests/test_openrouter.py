import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.response import addinfourl

from evaluation.openrouter import FREE_MODELS, generate


MODEL = "google/gemma-4-31b-it:free"
SECRET = "test-secret-do-not-expose"


class OpenRouterTests(unittest.TestCase):
    def call(self, model_id=MODEL, provider_slug="TestProvider"):
        return generate(model_id, "Question?", "Be concise.", provider_slug)

    @patch("evaluation.openrouter.build_opener")
    def test_validation_does_not_send_requests(self, opener):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                self.call()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}):
            for bad_model in ("google/gemma-4-31b-it", "other/model:free", ""):
                with self.subTest(model=bad_model), self.assertRaises(ValueError):
                    self.call(model_id=bad_model)
            for bad_provider in (None, "", "   "):
                with self.subTest(provider=bad_provider), self.assertRaises(ValueError):
                    self.call(provider_slug=bad_provider)
        opener.assert_not_called()

    @patch("evaluation.openrouter.build_opener")
    def test_pinning_and_sanitized_response(self, opener):
        reply = {"id": "gen-1", "model": MODEL, "provider": "TestProvider",
                 "provider_slug": "test-provider/endpoint",
                 "choices": [{"message": {"content": "  Answer.  ", "extra": "discard"},
                              "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6,
                           "cost": 999}, "secret": "discard"}
        opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(reply).encode())
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}):
            result = self.call(provider_slug=" TestProvider ")
        request, = opener.return_value.open.call_args.args
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {SECRET}")
        self.assertEqual(body["model"], MODEL)
        self.assertEqual(body["messages"], [{"role": "system", "content": "Be concise."},
                                            {"role": "user", "content": "Question?"}])
        self.assertEqual(body["provider"], {"only": ["TestProvider"],
                                            "allow_fallbacks": False, "require_parameters": True})
        self.assertEqual((body["temperature"], body["max_tokens"]), (0, 512))
        self.assertEqual(opener.return_value.open.call_args.kwargs, {"timeout": 60})
        self.assertEqual(result, {"answer": "Answer.", "raw_response": "  Answer.  ",
                                   "returned_model": MODEL, "provider": "TestProvider",
                                   "returned_provider_slug": "test-provider/endpoint",
                                   "usage": {"prompt_tokens": 4, "completion_tokens": 2,
                                             "total_tokens": 6, "cost": 999},
                                   "finish_reason": "stop", "generation_id": "gen-1"})

    @patch("evaluation.openrouter.build_opener")
    def test_http_errors_never_include_credentials_or_response_bodies(self, opener):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}):
            for code, category in ((429, "429"), (400, "4xx"), (503, "5xx")):
                opener.return_value.open.side_effect = HTTPError("https://openrouter.ai", code, SECRET, {},
                                                                 io.BytesIO(SECRET.encode()))
                with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, category) as caught:
                    self.call()
                self.assertNotIn(SECRET, str(caught.exception))
            opener.return_value.open.side_effect = URLError(SECRET)
            with self.assertRaises(RuntimeError) as caught:
                self.call()
            self.assertNotIn(SECRET, str(caught.exception))

    @patch("evaluation.openrouter.build_opener")
    def test_bad_response_is_sanitized(self, opener):
        opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(b'{"error":"test-secret-do-not-expose"}')
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}):
            with self.assertRaises(RuntimeError) as caught:
                self.call()
        self.assertNotIn(SECRET, str(caught.exception))

    def test_redirects_never_forward_authorization(self):
        requests = []

        def transport(handler, request):
            requests.append(request)
            response = addinfourl(io.BytesIO(SECRET.encode()),
                                   {"Location": "https://redirect.example.invalid/collect"},
                                   request.full_url, code)
            response.msg = "redirect"
            return response

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": SECRET}), \
                patch("urllib.request.HTTPSHandler.https_open", transport):
            for code in (300, 301, 302, 303, 304, 305, 306, 307, 308, 399):
                with self.subTest(code=code):
                    requests.clear()
                    with self.assertRaises(RuntimeError) as caught:
                        self.call()
                    self.assertEqual(len(requests), 1)
                    self.assertEqual(requests[0].get_header("Authorization"), f"Bearer {SECRET}")
                    self.assertNotIn(SECRET, str(caught.exception))
                    self.assertNotIn("redirect.example.invalid", str(caught.exception))

    def test_exact_allowlist(self):
        self.assertEqual(FREE_MODELS, {
            "nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free",
            "qwen/qwen3.8-27b:free", "cohere/north-mini-code:free",
        })


if __name__ == "__main__":
    unittest.main()
