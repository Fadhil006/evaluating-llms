"""Generate a real local fixture-backed sample report; makes no provider calls."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import make_engine
from app.models import Dataset, DatasetVersion, Experiment, ModelSnapshot, Provider
from app.providers.catalog import refresh
from app.providers.fixture import Fixture
from app.services.datasets import save
from app.services.experiment_lifecycle import start
from app.services.experiments import Design, save_design
from app.services.exports import render_markdown, report_data
from app.worker.runner import Worker

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="llm-lab-sample-") as temporary:
        database = Path(temporary) / "demo.sqlite3"
        environment = os.environ | {
            "EXECUTION_MODE": "demo",
            "DATABASE_PATH": str(Path(temporary) / "live.sqlite3"),
            "DEMO_DATABASE_PATH": str(database),
            "OPENROUTER_API_KEY": "",
            "OPENCODE_ZEN_API_KEY": "",
        }
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=BACKEND, env=environment, check=True)
        settings = Settings(execution_mode="demo", database_path=Path(temporary) / "live.sqlite3",
                            demo_database_path=database, openrouter_api_key="", opencode_zen_api_key="")
        engine = make_engine(settings)
        sessions = sessionmaker(engine)
        fixture = Fixture()
        dataset_file = ROOT / "datasets" / "original_demo_v1.jsonl"
        with sessions.begin() as session:
            refresh(session, fixture, fixture.catalog())
            saved = save(session, dataset_file.read_bytes(), "jsonl", name="LLM Comparison Lab Original Demo",
                         version="v1", source="Original examples authored for LLM Comparison Lab",
                         license="CC0-1.0")
            session.get(Dataset, saved["dataset_id"]).origin = "original"
            session.get(Dataset, saved["dataset_id"]).description = "Newly authored demonstration items; not an established benchmark."
            model_ids = session.scalars(select(ModelSnapshot.id).join(Provider).where(
                Provider.slug == "fixture").order_by(ModelSnapshot.id)).all()
            version_id = session.scalar(select(DatasetVersion.id).where(
                DatasetVersion.dataset_id == saved["dataset_id"]))
            design = Design(name="Synthetic ten-item sample", dataset_version_id=version_id,
                            model_snapshot_ids=model_ids,
                            system_prompt="Answer the given task concisely.", max_tokens=128,
                            temperature=None, repetitions=1, seed=42, timeout_seconds=30,
                            retries_per_job=0, attempt_cap=20)
            experiment = save_design(session, design, mode="demo")
            experiment_id = experiment["id"]
        with sessions.begin() as session:
            start(session, session.get(Experiment, experiment_id))
        worker = Worker(sessions, {"fixture": fixture}, spacing_seconds=0, execution_mode="demo")
        while worker.step():
            pass
        with sessions.begin() as session:
            data = report_data(session, experiment_id)
        if data is None:
            raise RuntimeError("Sample experiment disappeared")
        output = ROOT / "docs" / "sample-report.md"
        output.write_text(render_markdown(data), encoding="utf-8")
        print(f"Wrote {output.relative_to(ROOT)} from {len(data['jobs'])} synthetic fixture jobs; no live calls.")
        engine.dispose()


if __name__ == "__main__":
    main()
