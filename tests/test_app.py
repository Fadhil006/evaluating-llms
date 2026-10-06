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
                    "evaluation.runner.run_live_comparison", create=True,
                    return_value={"paused": False, "models": {}}) as live:
                page = AppTest.from_file(str(app)).run()
                self.assertFalse(page.exception)
                cap_input = next(box for box in page.number_input if box.label == "Total attempt cap for both models")
                self.assertIn("earlier attempts and retries count", cap_input.help)
                self.assertEqual(cap_input.max, 50)
                self.assertIn("shared cumulative cap", page.checkbox[0].label)
                self.assertIn("same two models", page.text_input[0].help)
                self.assertTrue(any("4 prompts × 2 models = 8" in caption.value for caption in page.caption))
                access.preflight.assert_not_called()
                live.assert_not_called()

                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                access.preflight.assert_not_called()
                live.assert_not_called()

                page.checkbox[0].check()
                next(box for box in page.selectbox if box.label == "Second free model / pinned route").set_value(
                    "nvidia/nemotron-3-ultra-550b-a55b:free")
                page = page.button[0].click().run()
                self.assertTrue(any("two different models" in error.value for error in page.error))
                access.preflight.assert_not_called()
                live.assert_not_called()

                next(box for box in page.selectbox if box.label == "Second free model / pinned route").set_value(
                    "google/gemma-4-31b-it:free")
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
                next(box for box in page.selectbox if box.label == "First free model / pinned route").set_value(
                    "qwen/qwen3.8-27b:free")
                next(box for box in page.number_input if box.label == "Total attempt cap for both models").set_value(3)
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                access.preflight.assert_called_with(max_requests=3)
                live.assert_called_once()
                args, kwargs = live.call_args
                self.assertEqual(args, (home / "datasets/v1.0/benchmark.jsonl", home / "runs/my-dev",
                                        ["qwen/qwen3.8-27b:free", "google/gemma-4-31b-it:free"],
                                        {"qwen/qwen3.8-27b:free": "modelrun/fp4",
                                         "google/gemma-4-31b-it:free": "google-ai-studio"}, 3))
                self.assertTrue(callable(kwargs["on_progress"]))
                self.assertFalse(any(heading.value == "Latest saved response" for heading in page.subheader))
                self.assertTrue(any("24 prompts × 2 models = 48" in caption.value and "partial" in caption.value
                                    for caption in page.caption))
                self.assertTrue(any("Free requests remaining: 10" in caption.value for caption in page.caption))
                self.assertFalse(any("SECRET" in caption.value for caption in page.caption))
                self.assertTrue(any("shared cap 3 attempts for both models, including prior attempts" in message.value
                                    for message in page.success))
                self.assertEqual(page.session_state["selected_run"], "my-dev")
                page.run()
                live.assert_called_once()

    def test_live_progress_shows_saved_answer_and_objective_score(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            shutil.copyfile(ROOT / "app.py", home / "app.py")
            access = types.ModuleType("evaluation.access")
            access.preflight = Mock(return_value={"free_remaining": 50})
            model = "nvidia/nemotron-3-ultra-550b-a55b:free"
            event = {"model": model, "item_id": "dr1-o", "prompt": "Which answer is right?",
                     "reference_answer": "B", "answer": "B", "status": "ok",
                     "score_status": "scored", "correct": True, "explanation": "Choice matches reference.",
                     "completed": 1, "planned": 8, "attempts": 2,
                     "summary": {"api_key": "SECRET MUST NOT APPEAR"}, "raw_payload": "SECRET MUST NOT APPEAR"}

            def save_one(*args, on_progress):
                on_progress(event)
                return {"paused": False, "models": {}}

            with patch.dict(sys.modules, {"evaluation.access": access}), patch(
                    "evaluation.runner.run_live_comparison", side_effect=save_one) as live:
                page = AppTest.from_file(str(home / "app.py")).run()
                access.preflight.assert_not_called()
                live.assert_not_called()
                page.checkbox[0].check()
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                self.assertEqual(page.metric[0].value, "1/8")
                self.assertEqual(page.metric[1].value, "2")
                self.assertTrue(any("1/8 planned model answers saved" in getattr(p, "text", "")
                                    for p in page.get("progress")))
                self.assertTrue(any("Nemotron 3 Ultra · dr1-o" in h.value for h in page.subheader))
                self.assertTrue(all(value in [block.value for block in page.code]
                                    for value in ("Which answer is right?", "B", "Choice matches reference.")))
                self.assertTrue(any("Objective score: Correct" in str(text.value) for text in page.markdown))
                self.assertTrue(any("Score status: scored" in caption.value for caption in page.caption))
                self.assertFalse(any("SECRET" in str(node.value) for kind in ("text", "caption", "code", "warning")
                                     for node in page.get(kind)))
                live.assert_called_once()

    def test_live_progress_distinguishes_review_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            shutil.copyfile(ROOT / "app.py", home / "app.py")
            access = types.ModuleType("evaluation.access")
            access.preflight = Mock(return_value={"free_remaining": 50})
            event = {"model": "google/gemma-4-31b-it:free", "item_id": "dm1-o", "prompt": "Compute 3 + 4",
                     "reference_answer": "7", "answer": "Seven units", "status": "ok",
                     "score_status": "review", "correct": None, "explanation": "Units need human review.",
                     "completed": 2, "planned": 8, "attempts": 3}

            def save_one(*args, on_progress):
                on_progress(event)
                return {"paused": True, "models": {}}

            with patch.dict(sys.modules, {"evaluation.access": access}), patch(
                    "evaluation.runner.run_live_comparison", side_effect=save_one):
                page = AppTest.from_file(str(home / "app.py")).run()
                page.checkbox[0].check()
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                self.assertTrue(any("Needs human review" in info.value for info in page.info))
                self.assertTrue(any("Score status: review" in caption.value for caption in page.caption))
                self.assertTrue(any(block.value == "Units need human review." for block in page.code))

                event.update(status="rate_limited", score_status=None, correct=None,
                             explanation=None, answer=None, attempts=4)
                page.checkbox[0].check()
                page = page.button[0].click().run()
                self.assertFalse(page.exception)
                self.assertTrue(any("Rate limited" in warning.value for warning in page.warning))
                self.assertFalse(any("Objective score:" in str(text.value) for text in page.markdown))

    def test_capped_run_feedback_and_same_item_comparison(self):
        level, message = run_feedback({"paused": False, "models": {"m": {"pending": 2, "answered": 2, "total": 4},
                                                                  "n": {"pending": 3, "answered": 1, "total": 4}}}, ["m", "n"])
        self.assertEqual(level, "warning")
        self.assertIn("5 answers still pending", message)
        self.assertIn("m: 2/4 answered", message)
        self.assertIn("n: 1/4 answered", message)
        self.assertEqual(run_feedback({"paused": True}, ["m", "n"])[0], "warning")
        self.assertEqual(run_feedback({"paused": False, "models": {"m": {"pending": 0}}}, ["m", "n"])[0], "success")
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

    def test_saved_two_model_run_shows_matched_comparison_without_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            shutil.copyfile(ROOT / "app.py", home / "app.py")
            fixtures = home / "fixtures.json"
            fixtures.write_text(json.dumps({"first": {"dr1-o": "B", "dr1-p": "B", "dm1-o": "7", "dm1-p": "7"},
                                            "second": {"dr1-o": "A", "dr1-p": "B", "dm1-o": "7",
                                                       "dm1-p": {"status": 429}}}), encoding="utf-8")
            run(ROOT / "datasets/v1.0/dev.jsonl", fixtures, home / "runs" / "pair", ["first", "second"])
            access = types.ModuleType("evaluation.access")
            access.preflight = Mock()
            with patch.dict(sys.modules, {"evaluation.access": access}), patch(
                    "evaluation.runner.run_live_comparison", create=True) as live:
                page = AppTest.from_file(str(home / "app.py")).run()
                self.assertFalse(page.exception)
                self.assertTrue(any(heading.value == "Same-item comparison" for heading in page.subheader))
                matched = next(frame.value for frame in page.dataframe if "Shared scored items" in frame.value.columns)
                self.assertEqual(matched["Correct / matched"].tolist(), ["3/3", "2/3"])
                self.assertTrue(any("Partial comparison" in info.value for info in page.info))
                self.assertTrue(any("first ·" in getattr(progress, "text", "") for progress in page.get("progress")))
                self.assertTrue(any("second ·" in getattr(progress, "text", "") for progress in page.get("progress")))
                access.preflight.assert_not_called()
                live.assert_not_called()


if __name__ == "__main__":
    unittest.main()
