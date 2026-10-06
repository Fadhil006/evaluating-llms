"""Noninteractive, tool-denied OpenCode CLI adapter."""

import json
import os
import subprocess
import tempfile


ALLOWED_MODELS = ("opencode/ling-3.1-flash-free", "opencode/nemotron-3-ultra-free")
MAX_OUTPUT = 1_000_000
ERROR_NAMES = ("ProviderAuthError", "ProviderModelNotFoundError", "APIError",
               "ContextOverflowError", "MessageAbortedError", "MessageOutputLengthError")


def _error_name(event):
    if event.get("type") not in ("error", "session.error"):
        return None
    error = event.get("error")
    if not isinstance(error, dict):
        properties = event.get("properties")
        error = properties.get("error") if isinstance(properties, dict) else None
    if not isinstance(error, dict):
        return None
    data = error.get("data")
    for name in (error.get("name"), data.get("name") if isinstance(data, dict) else None):
        if isinstance(name, str) and name in ERROR_NAMES:
            return name
    return None


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
            if len(output) > MAX_OUTPUT:
                raise RuntimeError("OpenCode generation failed")
            output = output.decode("utf-8")
            events = [json.loads(line) for line in output.splitlines()]
            if not all(isinstance(event, dict) for event in events):
                raise RuntimeError("OpenCode generation failed")
            if result.returncode:
                for event in events:
                    name = _error_name(event)
                    if name:
                        raise RuntimeError(f"OpenCode {name}") from None
                raise RuntimeError("OpenCode generation failed")
            parts = []
            for event in events:
                if event.get("type") in ("error", "session.error") or (
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
        except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError, TypeError):
            raise RuntimeError("OpenCode generation failed") from None
