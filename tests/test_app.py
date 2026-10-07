"""Offline HTTP contract checks for the localhost-only Flask dashboard."""

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import app as dashboard
except ImportError:  # The optional Flask UI is not required for the CLI.
    dashboard = None

from evaluation.runner import run
from evaluation.dataset import load_dataset


ROOT = Path(__file__).resolve().parents[1]
ROUTER_A = "nvidia/nemotron-3-ultra-550b-a55b:free"
ROUTER_B = "google/gemma-4-31b-it:free"
CODE_A = "opencode/ling-3.1-flash-free"
CODE_B = "opencode/nemotron-3-ultra-free"


@unittest.skipUnless(dashboard is not None and hasattr(dashboard, "app"), "install .[ui] for Flask dashboard tests")
class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runs = Path(self.temp.name) / "runs"
        self.runs.mkdir()
        self.root_patch = patch.object(dashboard, "RUNS", self.runs)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        old_config = {key: dashboard.app.config[key] for key in ("TESTING", "SERVER_NAME")}
        self.addCleanup(dashboard.app.config.update, old_config)
        dashboard.app.config.update(TESTING=True, SERVER_NAME="127.0.0.1:8501")
        self.client = dashboard.app.test_client()

    def wait_for_worker(self, done):
        self.assertTrue(done.wait(3), "background worker did not invoke mocked runner")
        self.assertTrue(dashboard.worker_lock.acquire(timeout=3), "background worker did not finish")
        dashboard.worker_lock.release()

    def form(self, client=None, **changes):
        page = (client or self.client).get("/")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        fields = {}
        for name in ("csrf_token", "submission_nonce"):
            match = re.search(r'<input\b(?=[^>]*\bname=["\']' + name +
                              r'["\'])(?=[^>]*\bvalue=["\']([^"\']+)["\'])[^>]*>', html)
            self.assertIsNotNone(match, f"missing {name} hidden field")
            fields[name] = match.group(1)
        fields.update(dataset="dev.jsonl", selected_pairs=["dr1", "dm1"], backend="OpenRouter", model_a=ROUTER_A,
                      model_b=ROUTER_B, run_name="pilot", max_requests="8", confirmed="on")
        fields.update(changes)
        return fields

    def save_run(self, name="sample", models=None, pair_ids=None):
        models = models or ["fixture-a", "fixture-b"]
        fixtures = self.runs / "fixtures.json"
        fixtures.write_text(json.dumps({model: {"dr1-o": "B", "dr1-p": "B",
                                                       "dm1-o": "7", "dm1-p": "7"}
                                        for model in models}), encoding="utf-8")
        folder = self.runs / name
        run(ROOT / "datasets/v1.0/dev.jsonl", fixtures, folder, models, pair_ids=pair_ids)
        return folder

    def rewrite_json(self, path, change):
        value = json.loads(path.read_text(encoding="utf-8"))
        change(value)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def rewrite_jsonl(self, path, change):
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        change(records)
        path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")

    def test_get_is_read_only_and_exposes_controls(self):
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router, patch(
                "evaluation.runner.run_opencode_comparison") as code:
            page = self.client.get("/")
            self.assertEqual(page.status_code, 200)
            text = page.get_data(as_text=True)
            for field in ("dataset", "selected_pairs", "backend", "model_a", "model_b", "run_name",
                           "max_requests", "confirmed", "csrf_token", "submission_nonce"):
                self.assertIn(f'name="{field}"', text)
            for item in load_dataset(ROOT / "datasets/v1.0/dev.jsonl"):
                self.assertIn(f'value="{item["pair_id"]}"', text)
            self.assertIn("demo", text.lower())
            preflight.assert_not_called()
            router.assert_not_called()
            code.assert_not_called()

    def test_rejected_submissions_never_check_access_or_dispatch(self):
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router, patch(
                "evaluation.runner.run_opencode_comparison") as code:
            for changes in ({"confirmed": ""}, {"model_b": ROUTER_A},
                            {"model_a": "unknown/free:free"}, {"dataset": "../dev.jsonl"},
                            {"run_name": "../escape"}, {"max_requests": "51"},
                            {"backend": "unexpected"}, {"model_a": CODE_A}, {"csrf_token": ""},
                            {"csrf_token": "wrong"}, {"submission_nonce": ""},
                             {"submission_nonce": "wrong"}, {"selected_pairs": "unknown"},
                             {"selected_pairs": []}, {"selected_pairs": ["dr1", "dr1"]},
                             {"selected_pairs": "../benchmark.jsonl"}):
                with self.subTest(changes=changes):
                    response = self.client.post("/runs", data=self.form(**changes))
                    self.assertEqual(response.status_code, 403 if changes.get("csrf_token") in ("", "wrong") or
                                     changes.get("submission_nonce") in ("", "wrong") else 302)
            preflight.assert_not_called()
            router.assert_not_called()
            code.assert_not_called()

    def test_router_preflight_precedes_dispatch_and_nonce_prevents_replay(self):
        calls = []
        done = threading.Event()

        def check(**kwargs):
            calls.append("preflight")
            return {"allowed": True, "free_remaining": 50, "free_limit": 50,
                    "spend_limit": 10, "spend_remaining": 10,
                    "api_key": "SECRET MUST NOT APPEAR"}

        def dispatch(*args, **kwargs):
            calls.append("dispatch")
            done.set()
            return {"paused": False, "models": {}}

        data = self.form(run_name="live-router", max_requests="3", selected_pairs=["dm1"])
        with patch("evaluation.access.preflight", side_effect=check) as preflight, patch(
                "evaluation.runner.run_live_comparison", side_effect=dispatch) as router, patch(
                "evaluation.runner.run_opencode_comparison") as code:
            response = self.client.post("/runs", data=data)
            self.assertEqual(response.status_code, 302)
            self.wait_for_worker(done)
            self.assertEqual(calls, ["preflight", "dispatch"])
            preflight.assert_called_once_with(max_requests=3)
            args, kwargs = router.call_args
            self.assertEqual(args, (ROOT / "datasets/v1.0/dev.jsonl", self.runs / "live-router",
                                    [ROUTER_A, ROUTER_B],
                                    {ROUTER_A: "nvidia", ROUTER_B: "google-ai-studio"}, 3))
            self.assertTrue(callable(kwargs["on_progress"]))
            self.assertEqual(kwargs["pair_ids"], ["dm1"])
            replay = self.client.post("/runs", data=data)
            self.assertEqual(replay.status_code, 403)
            self.assertEqual(calls, ["preflight", "dispatch"])
            code.assert_not_called()

    def test_original_signed_cookie_cannot_replay_after_worker_finishes(self):
        done = threading.Event()
        data = self.form(run_name="signed-replay")
        original_cookie = self.client.get_cookie("session", domain="127.0.0.1")
        self.assertIsNotNone(original_cookie)
        with patch("evaluation.access.preflight", return_value={"allowed": True, "free_remaining": 50,
                                                                 "free_limit": 50}) as preflight, patch(
                "evaluation.runner.run_live_comparison", side_effect=lambda *a, **kw: done.set()) as dispatch:
            self.assertEqual(self.client.post("/runs", data=data).status_code, 302)
            self.wait_for_worker(done)
            replay_client = dashboard.app.test_client()
            replay_client.set_cookie("session", original_cookie.value, domain="127.0.0.1")
            self.assertEqual(replay_client.post("/runs", data=data).status_code, 403)
            preflight.assert_called_once()
            dispatch.assert_called_once()

    def test_overlapping_valid_submissions_cannot_both_preflight(self):
        second_client = dashboard.app.test_client()
        first = self.form(run_name="first")
        second = self.form(second_client, run_name="second")
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        count_lock = threading.Lock()
        checks = 0

        def slow_preflight(**kwargs):
            nonlocal checks
            with count_lock:
                checks += 1
                first_check = checks == 1
            if first_check:
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("preflight remained blocked")
            return {"allowed": True, "free_remaining": 50, "free_limit": 50}

        with patch("evaluation.access.preflight", side_effect=slow_preflight) as preflight, patch(
                "evaluation.runner.run_live_comparison", side_effect=lambda *a, **kw: done.set()) as dispatch:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first_post = pool.submit(self.client.post, "/runs", data=first)
                try:
                    self.assertTrue(entered.wait(3), "first submission did not reach preflight")
                    second_post = pool.submit(second_client.post, "/runs", data=second)
                    self.assertEqual(second_post.result(timeout=3).status_code, 302)
                finally:
                    release.set()
                self.assertEqual(first_post.result(timeout=3).status_code, 302)
            self.wait_for_worker(done)
            preflight.assert_called_once()
            dispatch.assert_called_once()

    def test_denied_preflight_never_dispatches_and_hides_backend_secrets(self):
        with patch("evaluation.access.preflight", side_effect=ValueError("SECRET MUST NOT APPEAR")), patch(
                "evaluation.runner.run_live_comparison") as router:
            response = self.client.post("/runs", data=self.form())
            self.assertEqual(response.status_code, 302)
            self.assertNotIn(b"SECRET MUST NOT APPEAR", response.data)
            self.assertNotIn(b"SECRET MUST NOT APPEAR", self.client.get("/").data)
            router.assert_not_called()

    def test_opencode_skips_router_preflight(self):
        done = threading.Event()

        def dispatch(*args, **kwargs):
            done.set()
            return {"paused": True, "models": {}}

        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router, patch(
                "evaluation.runner.run_opencode_comparison", side_effect=dispatch) as code:
            response = self.client.post("/runs", data=self.form(backend="OpenCode (free-labeled)", model_a=CODE_A,
                                                                    model_b=CODE_B, run_name="live-code"))
            self.assertEqual(response.status_code, 302)
            self.wait_for_worker(done)
            args, kwargs = code.call_args
            self.assertEqual(args, (ROOT / "datasets/v1.0/dev.jsonl", self.runs / "live-code",
                                    [CODE_A, CODE_B], 8))
            self.assertTrue(callable(kwargs["on_progress"]))
            self.assertEqual(kwargs["pair_ids"], ["dr1", "dm1"])
            preflight.assert_not_called()
            router.assert_not_called()

    def test_saved_synthetic_and_zero_response_live_are_not_measured(self):
        folder = self.save_run()
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router:
            page = self.client.get("/?run=sample")
            self.assertEqual(page.status_code, 200)
            self.assertIn("SYNTHETIC", page.get_data(as_text=True).upper())
            for filename in ("config.json", "summary.json"):
                path = folder / filename
                record = json.loads(path.read_text(encoding="utf-8"))
                record.update(synthetic=False, source="opencode_live")
                if filename == "summary.json":
                    for counts in record["models"].values():
                        counts.update(correct=77, scored=88, answered=0, pending=4)
                path.write_text(json.dumps(record), encoding="utf-8")
            for filename in ("responses.jsonl", "scores.jsonl"):
                (folder / filename).write_text("", encoding="utf-8")
            page = self.client.get("/?run=sample")
            text = page.get_data(as_text=True).lower()
            self.assertEqual(page.status_code, 200)
            self.assertIn("no model responses", text)
            self.assertNotIn('<div class="evidence-banner synthetic">', text)
            self.assertNotIn("objective score: correct", text)
            self.assertNotRegex(text, r'77\s*<span>\s*/\s*88\s*</span>')
            preflight.assert_not_called()
            router.assert_not_called()

    def test_mismatched_dataset_hash_cannot_show_trusted_results(self):
        folder = self.save_run()
        config_path = folder / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["dataset_hash"] = "0" * 64
        config_path.write_text(json.dumps(config), encoding="utf-8")
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as dispatch:
            page = self.client.get("/?run=sample")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Run unreadable", page.get_data(as_text=True))
            self.assertNotIn("Correct / objectively scored", page.get_data(as_text=True))
            self.assertEqual(self.client.get("/runs/sample/results.csv").status_code, 404)
            preflight.assert_not_called()
            dispatch.assert_not_called()

    def test_offline_demo_if_available_never_contacts_providers(self):
        fields = self.form()
        done = threading.Event()

        def save_demo(*args, **kwargs):
            try:
                return run(*args, **kwargs)
            finally:
                done.set()

        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router, patch(
                "evaluation.runner.run_opencode_comparison") as code, patch(
                "evaluation.runner.run", side_effect=save_demo):
            response = self.client.post("/demo", data={key: fields[key] for key in
                                                        ("csrf_token", "submission_nonce")})
            self.assertEqual(response.status_code, 302)
            self.wait_for_worker(done)
            self.assertEqual(len(list(self.runs.glob("*/summary.json"))), 1)
            summary = json.loads(next(self.runs.glob("*/summary.json")).read_text(encoding="utf-8"))
            self.assertTrue(summary["synthetic"])
            self.assertEqual(len(summary["models"]), 2)
            config = json.loads(next(self.runs.glob("*/config.json")).read_text(encoding="utf-8"))
            self.assertEqual(len(config["models"]), 2)
            self.assertEqual(set(config["models"]), set(summary["models"]))
            self.assertTrue(all(config["models"]))
            self.assertEqual(config["selected_pair_ids"], ["dr1", "dm1"])
            self.assertEqual(config["split"], "dev")
            preflight.assert_not_called()
            router.assert_not_called()
            code.assert_not_called()

    def test_csv_only_serves_fixed_results_file_and_rejects_unsafe_paths(self):
        folder = self.save_run()
        expected = (folder / "results.csv").read_bytes()
        result = self.client.get("/runs/sample/results.csv")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, expected)
        self.assertIn("text/csv", result.content_type)
        result.close()
        for path in ("/runs/../results.csv", "/runs/%2e%2e/results.csv",
                     "/runs/sample/config.json", "/runs/sample/results.csv/../config.json"):
            with self.subTest(path=path):
                self.assertNotEqual(self.client.get(path).status_code, 200)
        (folder / "results.csv").unlink()
        (folder / "results.csv").symlink_to(folder / "config.json")
        self.assertNotEqual(self.client.get("/runs/sample/results.csv").status_code, 200)
        external = self.runs / "linked"
        external.symlink_to(folder, target_is_directory=True)
        self.assertNotEqual(self.client.get("/runs/linked/results.csv").status_code, 200)

    def test_selected_pair_is_frozen_in_config_page_and_csv(self):
        folder = self.save_run(pair_ids=["dm1"])
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["selected_pair_ids"], ["dm1"])
        self.assertEqual(config["selected_item_ids"], ["dm1-o", "dm1-p"])
        self.assertEqual(config["split"], "dev")
        page = self.client.get("/?run=sample")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("dm1-o", text)
        self.assertIn("dm1-p", text)
        self.assertNotIn('class="item-id">dr1-', text)
        self.assertIn("dm1", text)
        response = self.client.get("/runs/sample/results.csv")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["item_id"] for row in rows}, {"dm1-o", "dm1-p"})
        self.assertEqual({row["split"] for row in rows}, {"dev"})
        response.close()

    def test_held_out_pair_cannot_be_submitted_with_dev_dataset(self):
        held_out = load_dataset(ROOT / "datasets/v1.0/benchmark.jsonl")[0]["pair_id"]
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as dispatch:
            self.assertEqual(self.client.post("/runs", data=self.form(selected_pairs=[held_out])).status_code, 302)
            preflight.assert_not_called()
            dispatch.assert_not_called()

    def test_held_out_selection_dispatches_only_held_out_pairs(self):
        held_out = load_dataset(ROOT / "datasets/v1.0/benchmark.jsonl")[0]["pair_id"]
        done = threading.Event()
        with patch("evaluation.access.preflight", return_value={"allowed": True, "free_remaining": 50,
                                                                 "free_limit": 50}) as preflight, patch(
                "evaluation.runner.run_live_comparison", side_effect=lambda *a, **kw: done.set()) as dispatch:
            response = self.client.post("/runs", data=self.form(
                dataset="benchmark.jsonl", selected_pairs=[held_out], run_name="held-out"))
            self.assertEqual(response.status_code, 302)
            self.wait_for_worker(done)
            preflight.assert_called_once()
            self.assertEqual(dispatch.call_args.args[0], ROOT / "datasets/v1.0/benchmark.jsonl")
            self.assertEqual(dispatch.call_args.kwargs["pair_ids"], [held_out])

    def test_partial_and_unresolved_live_records_are_visible_without_measured_claim(self):
        folder = self.save_run(pair_ids=["dr1"])
        for filename in ("config.json", "summary.json"):
            self.rewrite_json(folder / filename, lambda record: record.update(
                synthetic=False, source="opencode_live"))
        self.rewrite_jsonl(folder / "responses.jsonl", lambda rows: rows.__setitem__(slice(None), [
            {**rows[0], "synthetic": False, "attempt_id": "completed"}]))
        self.rewrite_jsonl(folder / "scores.jsonl", lambda rows: rows.__setitem__(slice(None), [
            {**rows[0], "synthetic": False}]))
        (folder / "attempts.jsonl").write_text("".join(json.dumps({
            "attempt_id": attempt, "model": "fixture-a", "item_id": item,
            "synthetic": False}) + "\n" for attempt, item in
            (("completed", "dr1-o"), ("unresolved", "dr1-p"))), encoding="utf-8")
        page = self.client.get("/?run=sample")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True).lower()
        self.assertIn("pending", text)
        self.assertIn("unresolved", text)
        self.assertIn("dr1-p", text)
        self.assertNotIn("measured comparison is available", text)
        self.assertIn("saved successful live response", text)
        self.assertNotIn("synthetic · offline fixture", text)

    def test_historical_scores_are_not_recomputed_and_latency_metadata_fails_closed(self):
        folder = self.save_run()
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        config["scorer_version"] = "older-scorer-hash"
        (folder / "config.json").write_text(json.dumps(config) + "\n", encoding="utf-8")
        self.rewrite_jsonl(folder / "responses.jsonl",
                           lambda rows: rows[0].update(latency_ms="125.0"))
        page = self.client.get("/?run=sample")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("Historical scoring version", text)
        self.assertIn("Latency unavailable", text)
        self.assertIn("Correct · objective score", text)  # saved score remains visible, no rescoring
        export = self.client.get("/runs/sample/results.csv")
        self.assertEqual(export.status_code, 404)
        export.close()

    def test_malformed_stale_metadata_scores_and_csv_fail_closed(self):
        cases = (
            ("config.json", lambda value: value.update(selected_item_ids=["dr1-o"])),
            ("config.json", lambda value: value.update(selected_pair_ids=["dm1"])),
            ("config.json", lambda value: value.update(schema_version=999)),
            ("scores.jsonl", lambda rows: rows.append({**rows[0], "correct": False})),
            ("scores.jsonl", lambda rows: rows[0].update(item_id="unknown")),
            ("results.csv", None),
        )
        for index, (filename, mutate) in enumerate(cases):
            with self.subTest(filename=filename, index=index):
                name = f"case-{index}"
                folder = self.save_run(name=name)
                path = folder / filename
                if filename == "results.csv":
                    path.write_text("stale,forged\n1,2\n", encoding="utf-8")
                elif filename.endswith("jsonl"):
                    self.rewrite_jsonl(path, mutate)
                else:
                    self.rewrite_json(path, mutate)
                page = self.client.get(f"/?run={name}")
                self.assertEqual(page.status_code, 200)
                if filename == "results.csv":
                    self.assertIn("CSV unavailable", page.get_data(as_text=True))
                else:
                    self.assertIn("Run unreadable", page.get_data(as_text=True))
                self.assertEqual(self.client.get(f"/runs/{name}/results.csv").status_code, 404)

    def test_saved_content_is_html_escaped(self):
        self.save_run(models=["<script>alert(1)</script>", "fixture-b"])
        page = self.client.get("/?run=sample")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"<script>alert(1)</script>", page.data)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page.data)

    def test_saved_run_and_csv_get_never_invoke_providers_or_runners(self):
        self.save_run()
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router, patch(
                "evaluation.runner.run_opencode_comparison") as code, patch(
                "evaluation.runner.run") as fixtures:
            self.assertEqual(self.client.get("/?run=sample").status_code, 200)
            export = self.client.get("/runs/sample/results.csv")
            self.assertEqual(export.status_code, 200)
            export.close()
            for mocked in (preflight, router, code, fixtures):
                mocked.assert_not_called()

    def test_remote_host_and_origin_are_blocked(self):
        with patch("evaluation.access.preflight") as preflight, patch(
                "evaluation.runner.run_live_comparison") as router:
            data = self.form()
            for response in (self.client.get("/", headers={"Host": "evil.example"}),
                             self.client.post("/runs", data=data, headers={"Host": "evil.example"}),
                             self.client.post("/runs", data=data,
                                              headers={"Origin": "https://evil.example"})):
                self.assertIn(response.status_code, (400, 403))
            preflight.assert_not_called()
            router.assert_not_called()


if __name__ == "__main__":
    unittest.main()
