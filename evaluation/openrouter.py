"""Minimal, explicit OpenRouter free-model chat completions client."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


FREE_MODELS = frozenset({
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3.8-27b:free",
    "cohere/north-mini-code:free",
})
URL = "https://openrouter.ai/api/v1/chat/completions"


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def generate(model_id, prompt, system_prompt, provider_slug, temperature=0, max_tokens=512, timeout=60):
    """Generate one answer with a pinned provider; never retry or fall back."""
    if not isinstance(model_id, str) or model_id not in FREE_MODELS:
        raise ValueError("model_id must be an explicitly allowed :free model")
    if not isinstance(provider_slug, str) or not provider_slug.strip():
        raise ValueError("provider_slug must be explicit and nonblank")
    if not isinstance(prompt, str) or not isinstance(system_prompt, (str, type(None))):
        raise ValueError("prompt and system_prompt must be text")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or not key.strip():
        raise ValueError("OPENROUTER_API_KEY is required")

    messages = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "provider": {"only": [provider_slug.strip()], "allow_fallbacks": False,
                     "require_parameters": True},
    }
    request = Request(URL, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    })
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        exc.close()
        if exc.code == 429:
            raise RuntimeError("OpenRouter HTTP 429 rate limited") from None
        if 400 <= exc.code < 500:
            raise RuntimeError(f"OpenRouter HTTP 4xx ({exc.code})") from None
        if 500 <= exc.code < 600:
            raise RuntimeError(f"OpenRouter HTTP 5xx ({exc.code})") from None
        raise RuntimeError(f"OpenRouter HTTP error ({exc.code})") from None
    except (URLError, ValueError, UnicodeError) as exc:
        raise RuntimeError("OpenRouter request or response failed") from None

    try:
        choice = result["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("non-text answer")
        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError("invalid usage")
        return {
            "answer": content.strip(),
            "raw_response": content,
            "returned_model": result.get("model"),
            "provider": result.get("provider"),
            "returned_provider_slug": result.get("provider_slug"),
            "usage": usage,
            "finish_reason": choice.get("finish_reason"),
            "generation_id": result.get("id"),
        }
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise RuntimeError("OpenRouter response has invalid chat completion format") from None
