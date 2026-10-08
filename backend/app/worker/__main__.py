"""Run with ``python -m app.worker`` in a separately managed process."""

import os
import time

import httpx
from sqlalchemy.orm import sessionmaker

from app.config import load_settings
from app.db import make_engine
from app.providers.fixture import Fixture
from app.providers.openrouter import OpenRouter
from app.providers.zen import Zen
from app.worker.runner import Worker


def main():
    settings = load_settings()
    engine = make_engine(settings)
    with httpx.Client(timeout=httpx.Timeout(settings.request_timeout_seconds, connect=10)) as client:
        adapters = ({"fixture": Fixture()} if settings.execution_mode == "demo" else {
                "openrouter": OpenRouter(settings.openrouter_api_key.get_secret_value(), client),
                "opencode_zen": Zen(settings.opencode_zen_api_key.get_secret_value(), client),
            })
        worker = Worker(sessionmaker(engine), {
            **adapters,
        }, manual_cap=int(os.environ.get("MANUAL_DAILY_ATTEMPT_CAP", "40")),
                         execution_mode=settings.execution_mode)
        while True:
            if not worker.step():
                time.sleep(2)


if __name__ == "__main__":
    main()
