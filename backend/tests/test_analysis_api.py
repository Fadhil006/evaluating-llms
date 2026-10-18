from sqlalchemy import func, select
from test_results import save, setup

from app.api.exports import router as exports_router
from app.models import AnalysisSnapshot, DatasetItem, MetricResult, ModelResponse


def test_analysis_creation_is_explicit_and_snapshots_are_immutable(tmp_path):
    client, factory, engine, experiment_id = setup(tmp_path, count=1)
    # The results test app intentionally mounts only its router; add export coverage here.
    client.app.include_router(exports_router)
    with factory.begin() as session:
        item = session.scalar(select(DatasetItem))
        item.family_id = "family-0"
        item.split = "test"
        item.variant_id = "original"
    save(factory, experiment_id, 0, 0, "A")
    save(factory, experiment_id, 1, 0, "B")
    metrics_url = f"/api/experiments/{experiment_id}/results"

    assert client.get(metrics_url).status_code == 200
    assert client.get(f"/api/experiments/{experiment_id}/responses").status_code == 200
    assert client.get(f"/api/experiments/{experiment_id}/export").status_code == 200
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MetricResult)) == 0
        assert session.scalar(select(func.count()).select_from(AnalysisSnapshot)) == 0

    created = client.post(f"/api/experiments/{experiment_id}/analyses")
    assert created.status_code == 201, created.text
    frozen = created.json()
    assert set(frozen) == {"id", "sha256", "results", "manifest"}
    assert frozen["manifest"]["selected_model_slots"] == [0, 1]
    assert frozen["results"][0]["paired_delta"] == -1.0
    with factory.begin() as session:
        item = session.scalar(select(DatasetItem))
        item.family_id = "changed-later"
    assert client.post(f"/api/experiments/{experiment_id}/analyses").status_code == 201
    historical = client.get(f"/api/experiments/{experiment_id}/analyses/{frozen['id']}").json()
    assert historical == frozen
    assert client.get(metrics_url, params={"analysis_id": frozen["id"]}).json()["analysis"] == frozen
    listed = client.get(f"/api/experiments/{experiment_id}/analyses").json()
    assert [row["id"] for row in listed] == [frozen["id"], frozen["id"] + 1]
    export = client.get(f"/api/experiments/{experiment_id}/export",
                        params={"analysis_id": frozen["id"], "format": "json"}).json()
    assert {key: export["analysis"][key] for key in frozen} == frozen
    assert export["analysis"]["snapshot"]["planned"]
    for format_name in ("html", "markdown", "csv"):
        report = client.get(f"/api/experiments/{experiment_id}/export",
                            params={"analysis_id": frozen["id"], "format": format_name})
        assert report.status_code == 200 and frozen["sha256"] in report.text
    assert client.get(f"/api/experiments/{experiment_id}/analyses/999").status_code == 404
    engine.dispose()


def test_analysis_excludes_mismatched_and_legacy_truncated_scores(tmp_path):
    client, factory, engine, experiment_id = setup(tmp_path, count=3)
    with factory.begin() as session:
        for item in session.scalars(select(DatasetItem)):
            item.family_id = f"family-{item.external_id}"
            item.split = "test"
            item.variant_id = "original"
    save(factory, experiment_id, 0, 0, "A", mismatch=True)
    save(factory, experiment_id, 1, 0, "A")
    save(factory, experiment_id, 0, 1, "A", finish="length")
    save(factory, experiment_id, 1, 1, "A")
    save(factory, experiment_id, 0, 2, "A")
    save(factory, experiment_id, 1, 2, "A")

    response = client.post(f"/api/experiments/{experiment_id}/analyses")
    assert response.status_code == 201, response.text
    result = response.json()["results"][0]
    assert result["family_n"] == 1
    assert result["omitted_families"] == [["family-item-0", "test"], ["family-item-1", "test"]]
    with factory() as session:
        saved = session.scalar(select(AnalysisSnapshot))
        observations = saved.snapshot["observations"]
        assert all(not (row["item_id"] == "item-0" and row["model_slot"] == 0)
                   for row in observations)
        assert all(not (row["item_id"] == "item-1" and row["model_slot"] == 0)
                   for row in observations)
    assert client.post(f"/api/experiments/{experiment_id}/analyses",
                       json={"selected_model_slots": [0, 9]}).status_code == 422
    engine.dispose()


def test_instruction_all_checks_pooled_accuracy_and_empty_evidence(tmp_path):
    client, factory, engine, experiment_id = setup(tmp_path, count=2)
    with factory.begin() as session:
        items = session.scalars(select(DatasetItem).order_by(DatasetItem.external_id)).all()
        items[0].task_type = items[1].task_type = "instruction_following"
        items[0].scoring_config = {"metric": "instruction_checks", "checks": [
            {"type": "exact_text", "value": "yes"}, {"type": "exact_text", "value": "other"}]}
        items[1].scoring_config = {"metric": "instruction_checks", "checks": [
            {"type": "exact_text", "value": value} for value in ("a", "b", "c", "d")]}
    save(factory, experiment_id, 0, 0, "yes")  # 1/2 checks
    save(factory, experiment_id, 0, 1, "")  # completed invalid answer: 0/4, not 0/0
    save(factory, experiment_id, 1, 0, "yes")
    save(factory, experiment_id, 1, 1, "a")
    assert client.post(f"/api/experiments/{experiment_id}/analyses").status_code == 201

    with factory() as session:
        passed_rows = session.scalars(select(MetricResult).where(
            MetricResult.metric == "instruction_pooled_passed")).all()
        total_rows = session.scalars(select(MetricResult).where(
            MetricResult.metric == "instruction_pooled_total")).all()
        assert [row.value for row in passed_rows] == [1, 0, 1, 1]
        assert [row.value for row in total_rows] == [2, 4, 2, 4]
        empty_evidence = session.scalar(select(MetricResult).join(ModelResponse).where(
            MetricResult.metric == "instruction_all_checks", ModelResponse.raw_text == ""))
        assert '"passed":false' in empty_evidence.explanation
    data = client.get(f"/api/experiments/{experiment_id}/results").json()
    slot_zero = {row["metric"]: row for row in data["summaries"] if row["model_slot"] == 0}
    assert slot_zero["instruction_all_checks"]["quality"] == 0.0
    assert slot_zero["instruction_pooled_passed"]["quality"] == 1 / 6
    assert slot_zero["instruction_pooled_total"]["quality"] is None
    frozen = client.get(f"/api/experiments/{experiment_id}/analyses").json()[0]
    pooled = frozen["manifest"]["instruction_summary"]["instruction_following:0"]
    assert pooled["pooled_accuracy"] == 1 / 6
    assert pooled["all_checks_accuracy"] == 0.0
    with factory() as session:
        stored = session.scalar(select(AnalysisSnapshot).where(AnalysisSnapshot.id == frozen["id"]))
        assert all(row["metric_name"] != "instruction_pooled_passed"
                   for row in stored.snapshot["observations"])
    engine.dispose()
