"""Single-file desktop launcher for the LLM Comparison Lab."""

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "LLMComparisonLab"


def configure() -> Path:
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    env_file = data_dir / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# Edit this file to configure provider API keys. Restart the app afterward.\n"
            "EXECUTION_MODE=demo\n"
            f"DATABASE_PATH={data_dir / 'lab.sqlite3'}\n"
            f"DEMO_DATABASE_PATH={data_dir / 'demo.sqlite3'}\n"
            "OPENROUTER_API_KEY=\n"
            "OPENCODE_ZEN_API_KEY=\n",
            encoding="utf-8",
        )
    os.environ["LCLAB_ENV_FILE"] = str(env_file)
    os.environ["DATABASE_PATH"] = str(data_dir / "lab.sqlite3")
    os.environ["DEMO_DATABASE_PATH"] = str(data_dir / "demo.sqlite3")
    return data_dir


def main() -> None:
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(bundle / "backend"))
    configure()

    from alembic import command
    from alembic.config import Config
    from app import models  # noqa: F401 - register SQLAlchemy models
    from app.config import load_settings
    from app.worker.__main__ import main as run_worker
    from app.main import create_app
    import uvicorn

    settings = load_settings()
    migration = Config(str(bundle / "backend" / "alembic.ini"))
    migration.set_main_option("script_location", str(bundle / "backend" / "alembic"))
    command.upgrade(migration, "head")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    threading.Thread(target=run_worker, name="lab-worker", daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    server = threading.Thread(
        target=uvicorn.run,
        args=(create_app(settings),),
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "warning"},
        name="lab-api",
        daemon=True,
    )
    server.start()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            break
        except Exception:
            if not server.is_alive():
                raise RuntimeError("The local API failed to start") from None
            time.sleep(0.2)
    else:
        raise RuntimeError("Timed out while starting the local API")

    webbrowser.open(url)
    print(f"LLM Comparison Lab is running at {url}. Close this window to stop it.", flush=True)
    try:
        server.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
