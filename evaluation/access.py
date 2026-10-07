"""Local credential and quota gate for opt-in OpenRouter runs."""

import json
import math
import os
import re
import stat
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from .openrouter import _RejectRedirects


_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_KEY_LINE = re.compile(
    r"\s*OPENROUTER_API_KEY\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s#]*))\s*(?:#.*)?$"
)


def _local_key():
    try:
        # O_NOFOLLOW and fstat protect against a swapped-in symlink or unsafe file.
        with os.fdopen(
            os.open(
                _ENV_PATH,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            ),
            "r",
            encoding="utf-8"
        ) as stream:
            info = os.fstat(stream.fileno())

            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ValueError("Unsafe .env file permissions or type")

            lines = stream.readlines()

    except FileNotFoundError:
        raise ValueError("OPENROUTER_API_KEY is required") from None

    except (OSError, UnicodeError):
        raise ValueError("Cannot safely read .env file") from None

    keys = []

    for line in lines:
        if line.lstrip().startswith("OPENROUTER_API_KEY"):
            match = _KEY_LINE.fullmatch(line.rstrip("\r\n"))

            if match is None:
                raise ValueError("Invalid OPENROUTER_API_KEY entry")

            keys.append(
                next(
                    value
                    for value in match.groups()
                    if value is not None
                )
            )

    if len(keys) != 1:
        raise ValueError(
            "Exactly one OPENROUTER_API_KEY entry is required"
        )

    return keys[0]


def _nonnegative_number(value):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("Invalid OpenRouter key quota")

    return value


def preflight(max_requests: int) -> dict:
    """Check local credentials and key limits without dispatching completions."""

    if type(max_requests) is not int or not 1 <= max_requests <= 50:
        raise ValueError("max_requests must be between 1 and 50")

    key = os.environ.get("OPENROUTER_API_KEY")

    if key is None:
        key = _local_key()

    if (
        not key.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in key)
    ):
        raise ValueError("Invalid OPENROUTER_API_KEY")

    try:
        request = Request(
            "https://openrouter.ai/api/v1/key",
            headers={
                "Authorization": f"Bearer {key}"
            },
            method="GET"
        )

        with build_opener(_RejectRedirects()).open(
            request,
            timeout=10
        ) as response:
            result = json.load(response)

    except HTTPError as exc:
        exc.close()
        raise RuntimeError("OpenRouter key check failed") from None

    except Exception:
        raise RuntimeError("OpenRouter key check failed") from None

    try:
        data = result["data"]

        # Free-model daily quota
        free = data["free_model_daily_requests"]
        remaining = free["remaining"]
        limit = free["limit"]

        if type(remaining) is not int or type(limit) is not int:
            raise ValueError("Invalid OpenRouter key quota")

        _nonnegative_number(remaining)
        _nonnegative_number(limit)
                # Free-tier keys may have no configured paid spending cap.
        # For confirmed free-tier keys, spending limit fields may be missing
        # or explicitly null. For non-free tiers, if fields are missing or
        # null they are treated as invalid.
        is_free_tier = data.get("is_free_tier") is True
        has_limit = "limit" in data
        has_limit_remaining = "limit_remaining" in data

        spend_limit = None
        spend_remaining = None

        if has_limit:
            spend_limit = data["limit"]
            if spend_limit is None:
                if not is_free_tier:
                    raise ValueError("Missing OpenRouter key spending cap")
            else:
                spend_limit = _nonnegative_number(spend_limit)
        else:
            if not is_free_tier:
                raise ValueError("Missing OpenRouter key spending cap")

        if has_limit_remaining:
            spend_remaining = data["limit_remaining"]
            if spend_remaining is not None:
                spend_remaining = _nonnegative_number(spend_remaining)
        else:
            if not is_free_tier:
                raise ValueError("Missing OpenRouter key spending cap")



        # Always enforce the free-request quota.
        #
        # If a spend limit exists, also make sure it isn't exhausted.
        # A None spend limit is allowed because free-tier keys may not
        # have a configured paid spending limit.
        if (
            remaining < max_requests
            or spend_limit == 0
            or spend_remaining == 0
        ):
            raise ValueError("Insufficient OpenRouter key quota")

    except (
        KeyError,
        TypeError,
        AttributeError,
        ValueError
    ):
        raise ValueError(
            "OpenRouter key has invalid or insufficient quota"
        ) from None

    os.environ["OPENROUTER_API_KEY"] = key

    return {
        "free_remaining": remaining,
        "free_limit": limit,
        "spend_limit": spend_limit,
        "spend_remaining": spend_remaining,
    }
