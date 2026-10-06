"""Noninteractive, tool-denied OpenCode CLI adapter."""

import json
import os
import subprocess
import tempfile


ALLOWED_MODELS = ("opencode/ling-3.1-flash-free", "opencode/nemotron-3-ultra-free")
MAX_OUTPUT = 1_000_000


def generate(model, prompt):
    if model not in ALLOWED_MODELS:
        raise ValueError("model must be an allowed OpenCode free model")
    with tempfile.TemporaryDirectory() as cwd, tempfile.TemporaryFile() as output_file:
        env = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps({"permission": {"*": "deny"}})
        try:
            result = subprocess.run(
                ["opencode", "run", "--pure", "--model", model, "--format", "json",
                 "--agent", "build", prompt], cwd=cwd,
                 env=env,
                stdout=output_file, stderr=subprocess.DEVNULL, timeout=120, check=False)
            output_file.seek(0)
            output = output_file.read(MAX_OUTPUT + 1)
            if result.returncode or len(output) > MAX_OUTPUT:
                raise RuntimeError("OpenCode generation failed")
            output = output.decode("utf-8")
            parts = []
            for line in output.splitlines():
                event = json.loads(line)
                if not isinstance(event, dict) or event.get("type") in ("error", "session.error") or (
                        "error" in event and event["error"] is not None):
                    raise RuntimeError("OpenCode generation failed")
                part = event.get("part") or {}
                if (not isinstance(part, dict) or part.get("type") == "error" or
                        part.get("reason") == "error" or
                        ("error" in part and part["error"] is not None)):
                    raise RuntimeError("OpenCode generation failed")
                if event.get("type") == "text" and part.get("type") == "text":
                    text = part.get("text")
                    if not isinstance(text, str):
                        raise RuntimeError("OpenCode generation failed")
                    parts.append(text)
            answer = "".join(parts).strip()
            if not answer:
                raise RuntimeError("OpenCode generation failed")
            return {"answer": answer, "raw_response": answer}
        except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError, TypeError) as exc:
            raise RuntimeError("OpenCode generation failed") from None
