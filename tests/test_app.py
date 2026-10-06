"""Offline Streamlit smoke checks against an isolated copy of the dashboard."""

import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from streamlit.testing.v1 import AppTest
    from app import attention_matches, joined_rows, matched_comparison, run_feedback, safe_run_path, tally
except ImportError:  # Optional UI dependency is not required for the core CLI.
    AppTest = None
from evaluation.runner import run


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(AppTest is not None, "install .[ui] to test the dashboard")
class DashboardTests(unittest.TestCase):
    def test_run_name_cannot_escape_runs(self):
        for name in ("../outside", "/tmp/outside", "a/b", ".hidden", "a\\b", "a b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_run_path(name)

    def test_live_control_requires_confirmation_and_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            app = home / "app.py"
            shutil.copyfile(ROOT / "app.py", app)
            access = types.ModuleType("evaluation.access")
            access.preflight = Mock(return_value={"allowed": True})
            with patch.dict(sys.modules, {"evaluation.access": access}), patch(
                    "evaluation.runner.run_live", return_value={"paused": False}) as live:
                page = AppTest.from_file(str(app)).run()
                self.assertFalse(page.exception)
                cap_input = next(box for box in page.number_input if box.label == "Total attempt cap for this run")
                self.assertIn("earlier attempts and retries count", cap_input.help)
                self.assertIn("cumulative run cap", page.checkbox[0].label)
                self.assertIn("same model and dataset", page.text_input[0].help)
                access.preflight.assert_not_called()
                live.assert_not_called()

                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                access.preflight.assert_not_called()
                live.assert_not_called()

                page.checkbox[0].check()
                next(box for box in page.text_input if box.label == "Local run name").set_value("../outside")
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                access.preflight.assert_not_called()
                live.assert_not_called()

                page.checkbox[0].check()
                next(box for box in page.text_input if box.label == "Local run name").set_value("my-dev")
                access.preflight.side_effect = ValueError("SECRET MUST NOT APPEAR")
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                self.assertFalse(any("SECRET" in error.value for error in page.error))
                live.assert_not_called()

                access.preflight.side_effect = None
                access.preflight.return_value = {"allowed": False}
                page.checkbox[0].check()
                page = page.button[0].click().run()
                live.assert_not_called()

                access.preflight.return_value = {"free_remaining": 10, "free_limit": 50,
                                                 "spend_limit": 5, "spend_remaining": 4,
                                                 "api_key": "SECRET MUST NOT APPEAR"}
                page.checkbox[0].check()
                next(box for box in page.selectbox if box.label == "Dataset").set_value("benchmark.jsonl")
                next(box for box in page.selectbox if box.label == "Free model / pinned route").set_value(
                    "qwen/qwen3.8-27b:free")
                next(box for box in page.number_input if box.label == "Total attempt cap for this run").set_value(3)
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                access.preflight.assert_called_with(max_requests=3)
                live.assert_called_once_with(home / "datasets/v1.0/benchmark.jsonl", home / "runs/my-dev",
                                             "qwen/qwen3.8-27b:free", "modelrun/fp4", 3)
                self.assertTrue(any("Free requests remaining: 10" in caption.value for caption in page.caption))
                self.assertFalse(any("SECRET" in caption.value for caption in page.caption))
                self.assertTrue(any("total cap 3 attempts for this run, including prior attempts" in message.value
                                    for message in page.success))
                self.assertEqual(page.session_state["selected_run"], "my-dev")
                page.run()
                live.assert_called_once()

    def test_capped_run_feedback_and_same_item_comparison(self):
        level, message = run_feedback({"paused": False, "models": {"m": {"pending": 2}}}, "m")
        self.assertEqual(level, "warning")
        self.assertIn("2 items still pending", message)
        self.assertEqual(run_feedback({"paused": True}, "m")[0], "warning")
        self.assertEqual(run_feedback({"paused": False, "models": {"m": {"pending": 0}}}, "m")[0], "success")
        rows = [{"model": "a", "item_id": "one", "correct": True},
                {"model": "b", "item_id": "one", "correct": False},
                {"model": "a", "item_id": "two", "correct": True},
                {"model": "b", "item_id": "two", "correct": None}]
        compared = matched_comparison(rows, ["a", "b"])
        self.assertEqual([row["Correct / matched"] for row in compared], ["1/1", "0/1"])
        self.assertEqual([row["Shared scored items"] for row in compared], [1, 1])
        self.assertTrue(attention_matches({"score_status": "review"}, "Needs review"))
        self.assertFalse(attention_matches({"correct": None}, "Incorrect"))

    def test_offline_demo_runs_from_ui(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            shutil.copyfile(ROOT / "app.py", home / "app.py")
            dataset_dir = home / "datasets" / "v1.0"
            dataset_dir.mkdir(parents=True)
            shutil.copyfile(ROOT / "datasets/v1.0/dev.jsonl", dataset_dir / "dev.jsonl")
            page = AppTest.from_file(str(home / "app.py")).run()
            demo = next(button for button in page.button if button.label == "Try offline demo")
            page = demo.click().run()
            self.assertFalse(page.exception)
            self.assertTrue(any("Synthetic demo saved" in message.value for message in page.success))
            self.assertTrue(any("SYNTHETIC" in message.value for message in page.warning))
            folders = [folder for folder in (home / "runs").iterdir() if folder.is_dir()]
            self.assertEqual(len(folders), 1)
            summary = json.loads((folders[0] / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["synthetic"])
            self.assertEqual(summary["models"]["demo-fixture"]["answered"], 4)

    def test_truncated_saved_answer_is_not_invalid(self):
        rows = joined_rows([{"id": "one", "category": "reasoning"}],
                           [{"model": "m", "item_id": "one", "status": "ok", "finish_reason": "length"}],
                           [], ["m"])
        self.assertEqual(rows[0]["response_status"], "truncated")
        self.assertEqual(tally(rows)["truncated"], 1)
        self.assertEqual(tally(rows)["invalid"], 0)

    def test_empty_and_synthetic_saved_run(self):
        # A copied app resolves runs/ beside itself, independent of anyone's local runs.
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            app = home / "app.py"
            shutil.copyfile(ROOT / "app.py", app)
            empty = AppTest.from_file(str(app)).run()
            self.assertFalse(empty.exception)
            self.assertEqual(empty.title[0].value, "Evidence, not a leaderboard.")
            self.assertEqual([heading.value for heading in empty.header[:2]],
                             ["Make a careful run.", "Read the record."])
            self.assertTrue(any("No saved runs found" in message.value for message in empty.info))

            fixtures = home / "fixtures.json"
            fixtures.write_text(json.dumps({"fixture-a": {"dr1-o": "B", "dr1-p": "A",
                                                       "dm1-o": "7", "dm1-p": "7"}}), encoding="utf-8")
            run(ROOT / "datasets/v1.0/dev.jsonl", fixtures, home / "runs" / "smoke", ["fixture-a"])
            dashboard = AppTest.from_file(str(app)).run()
            self.assertFalse(dashboard.exception)
            self.assertTrue(any("SYNTHETIC" in message.value for message in dashboard.warning))
            self.assertEqual([tab.label for tab in dashboard.tabs],
                             ["Overview", "By category", "Paired robustness", "Answer inspector"])
            metrics = {metric.label: metric.value for metric in dashboard.metric}
            self.assertEqual({label: metrics[label] for label in
                              ("Correct / scored", "Answered / total", "For human review", "Pending")},
                             {"Correct / scored": "3/4", "Answered / total": "4/4",
                              "For human review": "0", "Pending": "0"})
            self.assertEqual(metrics["Complete scored pairs"], "2/2")
            self.assertTrue(any("3/4 scored" in getattr(progress, "text", "")
                                for progress in dashboard.get("progress")), repr(dashboard.get("progress")))
            self.assertTrue(any("Objective rate" in frame.value.columns for frame in dashboard.dataframe))
            self.assertTrue(any("Prompt" in heading.value for heading in dashboard.subheader))
            self.assertTrue(any("What is 3 plus 4" in block.value for block in dashboard.code))
            self.assertTrue(any("B" == block.value for block in dashboard.code))
            self.assertTrue(any("Download saved run as CSV" in button.label
                                for button in dashboard.get("download_button")))
            pair = next(box for box in dashboard.selectbox if box.label == "Pair ID")
            dashboard = pair.set_value("dr1").run()
            self.assertFalse(dashboard.exception)
            self.assertTrue(any("Eva is older" in block.value for block in dashboard.code))
            search = next(box for box in dashboard.text_input if box.label == "Find item")
            dashboard = search.set_value("dm1-o").run()
            self.assertFalse(dashboard.exception)
            self.assertTrue(any(block.value == "7" for block in dashboard.code))
            self.assertTrue(any("Showing 1 of 4" in caption.value for caption in dashboard.caption))


if __name__ == "__main__":
    unittest.main()
