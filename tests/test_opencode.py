"""Offline checks for the tool-denied OpenCode CLI adapter."""

import json
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from evaluation.opencode import ALLOWED_MODELS, MAX_OUTPUT, generate


class OpenCodeTests(unittest.TestCase):
    def test_json_parts_and_isolated_denied_tools(self):
        def run(argv, **kwargs):
            self.assertEqual(argv, ["opencode", "run", "--pure", "--model", ALLOWED_MODELS[0],
                                    "--format", "json", "--agent", "build", "Question: x\nAnswer:"])
            self.assertTrue(os.path.isdir(kwargs["cwd"]))
            self.assertEqual(json.loads(kwargs["env"]["OPENCODE_CONFIG_CONTENT"]),
                              {"permission": {"*": "deny"}})
            self.assertNotIn("OPENROUTER_API_KEY", kwargs["env"])
            self.assertEqual(kwargs["timeout"], 120)
            self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
            kwargs["stdout"].write(b'\n'.join((
                b'{"type":"step_start"}',
                b'{"type":"text","part":{"type":"text","text":"A"}}',
                b'{"type":"text","part":{"type":"text","text":"B"}}')))
            return SimpleNamespace(returncode=0)

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "unrelated-key"}), patch(
                "evaluation.opencode.subprocess.run", side_effect=run) as call:
            self.assertEqual(generate(ALLOWED_MODELS[0], "Question: x\nAnswer:"),
                             {"answer": "AB", "raw_response": "AB"})
            self.assertEqual(call.call_count, 1)

    def test_unknown_failures_never_expose_output(self):
        outputs = ((1, b"private"), (0, b"not json private"),
                   (0, b'{"type":"error","error":"private"}'),
                   (0, b'{"type":"text","part":{"type":"text","text":" "}}'),
                   (0, b"x" * (MAX_OUTPUT + 1)))
        for outcome in (*outputs, subprocess.TimeoutExpired("opencode", 120, output=b"private"),
                        FileNotFoundError("private")):
            def run(argv, **kwargs):
                if isinstance(outcome, Exception):
                    raise outcome
                kwargs["stdout"].write(outcome[1])
                return SimpleNamespace(returncode=outcome[0])

            with self.subTest(outcome=type(outcome)), patch("evaluation.opencode.subprocess.run",
                                                             side_effect=run):
                with self.assertRaisesRegex(RuntimeError, "OpenCode generation failed") as caught:
                    generate(ALLOWED_MODELS[0], "prompt")
                self.assertNotIn("private", str(caught.exception))

    def test_disallowed_model_never_spawns(self):
        with patch("evaluation.opencode.subprocess.run") as call:
            with self.assertRaises(ValueError):
                generate("some/other-model", "prompt")
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
