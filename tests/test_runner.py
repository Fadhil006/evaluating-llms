"""Hand-counted synthetic runner checks; no provider calls."""

import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.runner import reanalyze, run, run_live, run_live_comparison, run_opencode_comparison
from evaluation.openrouter import FREE_MODELS
from evaluation.opencode import ALLOWED_MODELS


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = self.root / "benchmark.jsonl"
        self.fixtures = self.root / "fixtures.json"
        self.out = self.root / "run"
        base = {"pair_id": "p1", "split": "test", "category": "reasoning",
                "scorer": "mcq", "reference_answer": "A", "rules": {},
                "dataset_version": "v1", "source": "local test"}
        items = [{**base, "id": "o", "variant": "original", "prompt": "Choose one."},
                 {**base, "id": "p", "variant": "paraphrase", "prompt": "Pick one."}]
        self.dataset.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")

    def fixture(self, value):
        self.fixtures.write_text(json.dumps(value), encoding="utf-8")

    def lines(self):
        return [json.loads(line) for line in (self.out / "responses.jsonl").read_text().splitlines()]

    def test_counts_resume_and_offline_reanalysis(self):
        self.fixture({"a": {"o": "A", "p": "B"}, "b": {"o": {"status": 503, "error": "offline fail"}}})
        result = run(self.dataset, self.fixtures, self.out, ["a", "b"])
        a = result["models"]["a"]
        self.assertEqual({k: a[k] for k in ("planned", "answered", "scored", "correct", "incorrect",
                                           "review", "invalid", "failures", "pending")},
                         dict(planned=2, answered=2, scored=2, correct=1, incorrect=1,
                              review=0, invalid=0, failures=0, pending=0))
        self.assertEqual(a["accuracy"], 0.5)
        self.assertEqual(a["categories"]["reasoning"]["scored"], 2)
        self.assertEqual(a["pairs"]["original_minus_variant_pp"], 100.0)
        with (self.out / "results.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(row["score_status"] == "scored" for row in rows), 2)
        self.assertEqual(result["models"]["b"]["failures"], 2)  # 503 and missing fixture
        self.assertTrue(result["synthetic"])
        self.assertTrue(all(row["synthetic"] for row in self.lines()))
        self.assertEqual(run(self.dataset, self.fixtures, self.out, ["a", "b"])["models"], result["models"])
        self.assertEqual(len(self.lines()), 4)
        (self.out / "scores.jsonl").unlink()
        self.assertEqual(reanalyze(self.out)["models"], result["models"])
        self.assertEqual(len((self.out / "scores.jsonl").read_text().splitlines()), 2)
        self.assertEqual(json.loads((self.out / "config.json").read_text())["split"], "test")

    def test_scorer_change_blocks_fixture_reanalysis_and_resume(self):
        self.fixture({"a": {"o": "A", "p": "A"}})
        run(self.dataset, self.fixtures, self.out, ["a"])
        with patch("evaluation.runner._scorer_hash", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "scorer version"):
                reanalyze(self.out)
            with self.assertRaisesRegex(ValueError, "config mismatch"):
                run(self.dataset, self.fixtures, self.out, ["a"])

    def test_config_mismatch_and_truncated_log(self):
        self.fixture({"a": {"o": "A", "p": "A"}})
        run(self.dataset, self.fixtures, self.out, ["a"])
        with self.assertRaisesRegex(ValueError, "config mismatch"):
            run(self.dataset, self.fixtures, self.out, ["b"])
        with (self.out / "responses.jsonl").open("ab") as stream:
            stream.write(b'{"model":')
        with self.assertRaisesRegex(ValueError, "truncated JSONL"):
            run(self.dataset, self.fixtures, self.out, ["a"])

    def test_429_pauses_then_resumes_saved_state(self):
        self.fixture({"a": {"o": "A", "p": {"status": 429}}, "b": {"o": "A", "p": "A"}})
        result = run(self.dataset, self.fixtures, self.out, ["a", "b"])
        self.assertTrue(result["paused"])
        self.assertEqual(len(self.lines()), 2)
        self.assertEqual(result["models"]["a"]["pending"], 1)
        self.assertEqual(result["models"]["a"]["rate_limited"], 1)
        self.assertEqual(result["models"]["b"]["pending"], 2)
        self.fixture({"a": {"o": "B", "p": "A"}, "b": {"o": "A", "p": "B"}})
        resumed = run(self.dataset, self.fixtures, self.out, ["a", "b"])
        self.assertFalse(resumed["paused"])
        self.assertEqual(len(self.lines()), 5)
        self.assertEqual(self.lines()[0]["answer"], "A")  # completed key not replaced
        self.assertEqual(resumed["models"]["a"]["correct"], 2)
        self.assertEqual(resumed["models"]["b"]["incorrect"], 1)


class LiveRunnerTests(unittest.TestCase):
    lines = RunnerTests.lines

    def setUp(self):
        RunnerTests.setUp(self)
        self.models = sorted(FREE_MODELS)[:2]
        self.providers = {self.models[0]: "pinned-one", self.models[1]: "pinned-two"}
        key = patch.dict("os.environ", {"OPENROUTER_API_KEY": "offline-test-key"})
        key.start()
        self.addCleanup(key.stop)
        sleeper = patch("evaluation.runner.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def attempts(self):
        return [json.loads(line) for line in (self.out / "attempts.jsonl").read_text().splitlines()]

    def reply(self, model, provider):
        return {"answer": "A", "raw_response": "A", "returned_model": model,
                "returned_provider_slug": provider, "usage": {"cost": 0}, "finish_reason": "stop"}

    def test_comparison_dispatch_resume_and_cumulative_cap(self):
        calls = []

        def generate(model, prompt, system, provider, **settings):
            calls.append((model, provider, prompt, settings))
            return self.reply(model, provider)

        with patch("evaluation.openrouter.generate", side_effect=generate):
            first = run_live_comparison(self.dataset, self.out, self.models, self.providers, 2)
            self.assertEqual([a["model"] for a in self.attempts()], [self.models[0]] * 2)
            self.assertEqual(len(self.lines()), 2)
            self.assertEqual(first["models"][self.models[1]]["pending"], 2)
            resumed = run_live_comparison(self.dataset, self.out, self.models, self.providers, 4)
            self.assertEqual([a["model"] for a in self.attempts()],
                             [self.models[0]] * 2 + [self.models[1]] * 2)
            self.assertEqual([r["model"] for r in self.lines()],
                             [self.models[0]] * 2 + [self.models[1]] * 2)
            self.assertEqual([c[1] for c in calls], [self.providers[m] for m in
                                                    [self.models[0]] * 2 + [self.models[1]] * 2])
            self.assertEqual(len({a["attempt_id"] for a in self.attempts()}), 4)
            self.assertEqual(resumed["models"][self.models[1]]["answered"], 2)
            run_live_comparison(self.dataset, self.out, self.models, self.providers, 4)
            self.assertEqual(len(calls), 4)
            self.assertEqual(reanalyze(self.out)["models"], resumed["models"])
        config = json.loads((self.out / "config.json").read_text())
        self.assertEqual(config["providers"], self.providers)
        self.assertEqual(config["models"], self.models)

    def test_50_attempt_ceiling_and_cross_model_linkage(self):
        template = json.loads(self.dataset.read_text().splitlines()[0])
        items = [{**template, "id": f"{n}-{variant}", "pair_id": str(n),
                  "prompt": f"Choose {n} ({variant}).", "variant": variant}
                 for n in range(13) for variant in ("original", "paraphrase")]
        self.dataset.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
        with patch("evaluation.openrouter.generate", side_effect=lambda model, prompt, system, provider,
                   **settings: self.reply(model, provider)) as call:
            run_live_comparison(self.dataset, self.out, self.models, self.providers, 48)
            run_live_comparison(self.dataset, self.out, self.models, self.providers, 50)
            run_live_comparison(self.dataset, self.out, self.models, self.providers, 50)
            self.assertEqual(call.call_count, 50)
        self.assertEqual(len(self.attempts()), 50)
        self.assertEqual(len(self.lines()), 50)
        self.assertEqual({a["model"] for a in self.attempts()}, set(self.models))
        records = self.lines()
        records[-1]["model"] = self.models[0]
        (self.out / "responses.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mismatched live response"):
            reanalyze(self.out)

    def test_comparison_progress_saved_scores_and_order(self):
        events = []
        replies = [self.reply(self.models[0], self.providers[self.models[0]]),
                   {**self.reply(self.models[0], self.providers[self.models[0]]),
                    "finish_reason": "length"},
                   RuntimeError("OpenRouter HTTP 4xx (400)"),
                   self.reply(self.models[1], self.providers[self.models[1]])]
        calls = []

        def generate(model, prompt, system, provider, **settings):
            calls.append((model, prompt))
            response = replies[len(calls) - 1]
            if isinstance(response, Exception):
                raise response
            return response

        def progress(event):
            events.append(event)
            self.assertEqual(len(self.lines()), len(events))
            self.assertEqual(len(self.attempts()), len(events))
            self.assertEqual(event["summary"], json.loads((self.out / "summary.json").read_text()))
            self.assertEqual(event["attempts"], len(events))
            self.assertEqual(event["completed"], len(events))
            self.assertEqual(event["planned"], 4)

        with patch("evaluation.openrouter.generate", side_effect=generate) as mock_generate:
            result = run_live_comparison(self.dataset, self.out, self.models, self.providers,
                                         4, on_progress=progress)
            self.assertEqual(mock_generate.call_count, 4)
            run_live_comparison(self.dataset, self.out, self.models, self.providers, 4,
                                on_progress=progress)
            self.assertEqual(mock_generate.call_count, 4)
        self.assertEqual(len(events), 4)
        self.assertEqual([(e["model"], e["item_id"]) for e in events],
                         [(self.models[0], "o"), (self.models[0], "p"),
                          (self.models[1], "o"), (self.models[1], "p")])
        self.assertEqual([e["status"] for e in events], ["ok", "truncated", "error", "ok"])
        self.assertEqual([e["score_status"] for e in events], ["scored", None, None, "scored"])
        self.assertEqual([e["correct"] for e in events], [True, None, None, True])
        self.assertEqual([e["answer"] for e in events], ["A", "A", None, "A"])
        self.assertEqual([e["prompt"] for e in events],
                         ["Choose one.", "Pick one.", "Choose one.", "Pick one."])
        self.assertTrue(all(e["reference_answer"] == "A" for e in events))
        self.assertEqual(events[0]["explanation"], "Single choice compared to reference.")
        self.assertIsNone(events[1]["explanation"])
        self.assertEqual(set(events[0]), {"model", "item_id", "prompt", "reference_answer",
                                          "answer", "status", "score_status", "correct",
                                          "explanation", "completed", "planned", "attempts", "summary"})
        self.assertEqual(events[-1]["summary"]["models"], result["models"])

    def test_comparison_progress_429_and_noop_cap(self):
        events = []

        def progress(event):
            events.append(event)
            self.assertEqual(event["summary"], json.loads((self.out / "summary.json").read_text()))
            self.assertEqual(len(self.lines()), 1)

        with patch("evaluation.openrouter.generate",
                   side_effect=RuntimeError("OpenRouter HTTP 429 rate limited")) as call:
            result = run_live_comparison(self.dataset, self.out, self.models, self.providers,
                                         1, on_progress=progress)
            self.assertTrue(result["paused"])
            self.assertEqual(call.call_count, 1)
            run_live_comparison(self.dataset, self.out, self.models, self.providers,
                                1, on_progress=progress)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(len(events), 1)
        self.assertEqual({key: events[0][key] for key in
                          ("status", "answer", "score_status", "correct", "explanation",
                           "completed", "planned", "attempts")},
                         {"status": "rate_limited", "answer": None, "score_status": None,
                          "correct": None, "explanation": None, "completed": 0,
                          "planned": 4, "attempts": 1})

    def test_blocked_anomaly_unresolved_and_429(self):
        with patch("evaluation.openrouter.generate", return_value={
                **self.reply(self.models[0], self.providers[self.models[0]]), "usage": {"cost": 1}}) as call:
            self.assertTrue(run_live_comparison(self.dataset, self.out, self.models,
                                                self.providers, 4)["paused"])
            self.assertEqual(call.call_count, 1)
            with self.assertRaisesRegex(ValueError, "suspicious routing or billing"):
                run_live_comparison(self.dataset, self.out, self.models, self.providers, 4)
        self.out = self.root / "unresolved"
        with patch("evaluation.openrouter.generate", side_effect=RuntimeError("transport")) as call:
            result = run_live_comparison(self.dataset, self.out, self.models, self.providers, 4)
            self.assertTrue(result["paused"])
            self.assertEqual(result["unresolved_attempts"], 0)
            self.assertEqual(call.call_count, 1)
        self.out = self.root / "limited"
        with patch("evaluation.openrouter.generate", side_effect=RuntimeError("OpenRouter HTTP 429 rate limited")) as call:
            self.assertTrue(run_live_comparison(self.dataset, self.out, self.models,
                                                self.providers, 4)["paused"])
            self.assertEqual(call.call_count, 1)

    def test_invalid_comparison_and_legacy_single_model_config(self):
        with patch("evaluation.openrouter.generate") as call:
            for models, providers, cap in ((self.models[:1], self.providers, 4),
                                           ([self.models[0]] * 2, self.providers, 4),
                                           (self.models, {self.models[0]: "only"}, 4),
                                           (self.models, self.providers, 51)):
                with self.subTest(models=models, cap=cap), self.assertRaises(ValueError):
                    run_live_comparison(self.dataset, self.out, models, providers, cap)
            call.assert_not_called()
        with patch("evaluation.openrouter.generate", return_value=self.reply(
                self.models[0], self.providers[self.models[0]])):
            run_live(self.dataset, self.out, self.models[0], self.providers[self.models[0]], 1)
            run_live(self.dataset, self.out, self.models[0], self.providers[self.models[0]], 1)
        config = json.loads((self.out / "config.json").read_text())
        self.assertEqual(config["models"], [self.models[0]])
        self.assertEqual(config["provider"], self.providers[self.models[0]])
        self.assertNotIn("providers", config)
        self.assertEqual(len(self.attempts()), 1)


class OpenCodeRunnerTests(unittest.TestCase):
    lines = RunnerTests.lines
    attempts = LiveRunnerTests.attempts

    def setUp(self):
        RunnerTests.setUp(self)
        self.models = list(ALLOWED_MODELS)
        key = patch.dict("os.environ", {}, clear=True)
        key.start()
        self.addCleanup(key.stop)
        sleeper = patch("evaluation.runner.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_score_events_resumed_cap_and_unchanged_openrouter(self):
        events, calls = [], []

        def generate(model, prompt):
            calls.append((model, prompt))
            return {"answer": "A", "raw_response": "A"}

        def progress(event):
            events.append(event)
            self.assertEqual(event["summary"], json.loads((self.out / "summary.json").read_text()))
            self.assertEqual(len(self.attempts()), len(events))
            self.assertEqual(len(self.lines()), len(events))

        with patch("evaluation.opencode.generate", side_effect=generate) as cli:
            with patch("evaluation.openrouter.generate") as openrouter:
                first = run_opencode_comparison(self.dataset, self.out, self.models, 2, progress)
                self.assertEqual(first["models"][self.models[1]]["pending"], 2)
                resumed = run_opencode_comparison(self.dataset, self.out, self.models, 4, progress)
                run_opencode_comparison(self.dataset, self.out, self.models, 4, progress)
                self.assertEqual(cli.call_count, 4)
                openrouter.assert_not_called()
        self.assertEqual([e["model"] for e in events], [self.models[0]] * 2 + [self.models[1]] * 2)
        self.assertEqual([e["item_id"] for e in events], ["o", "p"] * 2)
        self.assertEqual([e["completed"] for e in events], [1, 2, 3, 4])
        self.assertEqual([e["attempts"] for e in events], [1, 2, 3, 4])
        self.assertTrue(all(e["planned"] == 4 and e["score_status"] == "scored" and
                            e["correct"] is True and e["answer"] == "A" and
                            e["explanation"] == "Single choice compared to reference." and
                            e["summary"]["source"] == "opencode_live" for e in events))
        self.assertEqual(resumed["models"][self.models[1]]["answered"], 2)
        self.assertEqual([call[1] for call in calls], ["Question: Choose one.\nAnswer:",
                                                      "Question: Pick one.\nAnswer:"] * 2)
        config = json.loads((self.out / "config.json").read_text())
        self.assertEqual(config["runtime"], "opencode")
        self.assertEqual(config["models"], self.models)
        self.assertEqual(config["permission"], {"*": "deny"})
        self.assertEqual(reanalyze(self.out)["source"], "opencode_live")
        with self.assertRaisesRegex(ValueError, "config mismatch"):
            run_opencode_comparison(self.dataset, self.out, self.models[::-1], 4)

    def test_timeout_leaves_unresolved_and_blocks_redispatch(self):
        events = []
        with patch("evaluation.opencode.generate", side_effect=RuntimeError("secret timeout")) as cli:
            result = run_opencode_comparison(self.dataset, self.out, self.models, 4, events.append)
            self.assertTrue(result["paused"])
            self.assertEqual(result["unresolved_attempts"], 0)
            self.assertEqual(len(self.attempts()), 1)
            self.assertTrue((self.out / "responses.jsonl").exists())
            self.assertEqual(cli.call_count, 1)
            self.assertEqual(len(events), 1)

    def test_shared_50_attempt_ceiling(self):
        template = json.loads(self.dataset.read_text().splitlines()[0])
        items = [{**template, "id": f"{n}-{variant}", "pair_id": str(n),
                  "prompt": f"Choose {n} ({variant}).", "variant": variant}
                 for n in range(13) for variant in ("original", "paraphrase")]
        self.dataset.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
        with patch("evaluation.opencode.generate", return_value={"answer": "A", "raw_response": "A"}) as cli:
            run_opencode_comparison(self.dataset, self.out, self.models, 48)
            run_opencode_comparison(self.dataset, self.out, self.models, 50)
            run_opencode_comparison(self.dataset, self.out, self.models, 50)
            self.assertEqual(cli.call_count, 50)
        self.assertEqual(len(self.attempts()), 50)
        self.assertEqual(len(self.lines()), 50)

    def test_model_validation_and_cap_before_dispatch(self):
        with patch("evaluation.opencode.generate") as cli:
            for models, cap in ((self.models[:1], 4), (self.models[:1] * 2, 4),
                                ([self.models[0], "unlisted"], 4), (self.models, 0),
                                (self.models, 51), (self.models, True)):
                with self.subTest(models=models, cap=cap), self.assertRaises(ValueError):
                    run_opencode_comparison(self.dataset, self.out, models, cap)
            cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
