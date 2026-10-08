import csv
import io
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_results import save, setup

from app.api.exports import router
from app.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    Experiment,
    HumanRating,
    ModelSnapshot,
    ReviewAssignment,
)


def client_for(tmp_path):
    _, factory, engine, eid = setup(tmp_path, count=1)
    app = FastAPI()
    app.state.sessions = factory
    app.state.export_redactions = ["secret-sentinel"]
    app.include_router(router)
    with factory.begin() as session:
        experiment = session.get(Experiment, eid)
        experiment.config = {"item_ids": ["item-0"], "models": [], "seed": 42,
                             "repetitions": 1, "max_tokens": 512, "attempt_cap": 40,
                             "provenance_mode": "demo"}
        dataset = session.get(Dataset, 1)
        dataset.name = "DEMONSTRATION synthetic fixture"
        dataset.source = "fixture://local"
        dataset.license = "CC0-1.0"
        version = session.get(DatasetVersion, 1)
        version.version = "fixture-v1"
        item = session.scalar(select(DatasetItem))
        item.prompt = "=secret-sentinel"
        item.reference_answers = ["secret-sentinel"]
        model = session.scalar(select(ModelSnapshot))
        model.model_id = "+secret-sentinel"
        eid = experiment.id
    return TestClient(app), factory, engine, eid


def test_json_allowlist_redacts_and_partial_draft_fields(tmp_path):
    client, factory, engine, eid = client_for(tmp_path)
    with factory.begin() as session:
        exp = session.get(Experiment, eid)
        exp.status = "draft"
    response = client.get(f"/api/experiments/{eid}/export?format=json")
    assert response.status_code == 200
    text = response.text
    assert "secret-sentinel" not in text
    data = response.json()
    assert data["schema_version"] == "1"
    assert data["experiment"]["status"] == "draft"
    assert data["dataset"]["selected_item_ids"] == ["item-0"]
    assert data["models"][0]["model_id"] == "+[REDACTED]"
    assert data["jobs"][0]["response"] is None
    assert data["jobs"][0]["status"] == "pending"
    assert "secret" not in text.lower()
    engine.dispose()


def test_html_and_markdown_escape_untrusted_content(tmp_path):
    client, factory, engine, eid = client_for(tmp_path)
    save(factory, eid, 0, 0, '</pre><script>alert(1)</script> [click](javascript:alert(1)) <img src=x>')
    html = client.get(f"/api/experiments/{eid}/export?format=html").text
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    markdown = client.get(f"/api/experiments/{eid}/export?format=markdown").text
    assert "[click](javascript:" in markdown and "```\n</pre><script>" in markdown
    assert "<img src=x>" in markdown  # enclosed in dynamically sized code fences
    assert "secret-sentinel" not in markdown
    engine.dispose()


def test_csv_quotes_and_defends_formula_strings(tmp_path):
    client, factory, engine, eid = client_for(tmp_path)
    save(factory, eid, 0, 0, '="response, value"')
    with factory.begin() as session:
        item = session.scalar(select(DatasetItem))
        item.prompt = " \t=1+2"
        assignment = ReviewAssignment(opaque_id="opaque", experiment_id=eid, dataset_item_id=item.id,
                                     mode="rubric", evaluator_label="evaluator", presentation={})
        session.add(assignment)
        session.flush()
        session.add(HumanRating(assignment_id=assignment.id, response_id=1, evaluator_label="evaluator",
                                rubric_version="1", scores={}, comments="@SUM(1,2)"))
    content = client.get(f"/api/experiments/{eid}/export?format=csv").text
    rows = list(csv.DictReader(io.StringIO(content)))
    assert rows[0]["model_id"] == "'+[REDACTED]"
    assert rows[0]["response"] == '\'="response, value"'
    assert rows[0]["prompt"] == "' \t=1+2"
    assert rows[0]["human_feedback"].startswith("[")  # JSON cell cannot be a spreadsheet formula
    assert rows[0]["human_comments"] == "'@SUM(1,2)"
    assert json.loads(rows[0]["usage_json"]) if rows[0]["usage_json"] else True
    assert '"response, value"' in content
    assert "secret-sentinel" not in content
    engine.dispose()
