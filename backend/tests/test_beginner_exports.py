import csv
import io
import json

from test_exports import client_for
from test_results import save


def test_downloads_preserve_configuration_attempts_and_limitations(tmp_path):
    client, factory, engine, eid = client_for(tmp_path)
    save(factory, eid, 0, 0, "A")
    try:
        manifest = client.get(f"/api/experiments/{eid}/export?format=json").json()
        markdown = client.get(f"/api/experiments/{eid}/export?format=markdown").text
        rows = list(csv.DictReader(io.StringIO(
            client.get(f"/api/experiments/{eid}/export?format=csv").text)))
        metadata = json.loads(rows[0]["report_metadata_json"])
        assert metadata["experiment"]["config"] == manifest["experiment"]["config"]
        assert metadata["dataset"] == manifest["dataset"]
        assert metadata["limitations"] == manifest["limitations"]
        assert json.loads(rows[0]["attempts_json"]) == manifest["jobs"][0]["attempts"]
        assert '"attempt_cap": 40' in markdown
        assert '"attempts": [' in markdown
        assert "No overall winner" in markdown
        assert "secret-sentinel" not in markdown
        assert "secret-sentinel" not in rows[0]["report_metadata_json"]
    finally:
        engine.dispose()
