"""Live-run safety tests: provider generate is mocked in every test."""

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.__main__ import main
from evaluation.openrouter import FREE_MODELS
from evaluation.runner import _locked, reanalyze, run, run_live


MODEL = sorted(FREE_MODELS)[0]


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "benchmark.jsonl"
        self.out = self.root / "run"
        base = {"pair_id": "p1", "split": "test", "category": "reasoning",
                "scorer": "mcq", "reference_answer": "A", "rules": {},
                "dataset_version": "v1", "source": "local test"}
        self.dataset.write_text("".join(json.dumps({**base, "id": name, "variant": variant,
                                                    "prompt": prompt}) + "\n"
                                        for name, variant, prompt in (("o", "original", "One?"),
                                                                      ("p", "paraphrase", "Two?"))),
                                encoding="utf-8")
        self.env = patch.dict(os.environ, {"OPENROUTER_API_KEY": "private-test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = patch("evaluation.openrouter.generate")
        self.generate = self.provider.start()
        self.addCleanup(self.provider.stop)
        self.sleeper = patch("evaluation.runner.time.sleep")
        self.sleep = self.sleeper.start()
        self.addCleanup(self.sleeper.stop)

    def reply(self, answer="A", finish_reason="stop"):
        return {"answer": answer, "raw_response": answer, "returned_model": MODEL,
                "provider": "Pinned", "usage": {}, "finish_reason": finish_reason,
                "generation_id": "mock-only"}

    def records(self, filename):
        return [json.loads(row) for row in (self.out / filename).read_text().splitlines()]

    def live(self, cap=4):
        return run_live(self.dataset, self.out, MODEL, "Pinned", cap)

    def test_cap_resume_pacing_and_offline_reanalysis(self):
        self.generate.side_effect = [self.reply(), self.reply("B")]
        first = self.live(1)
        self.assertEqual(first["models"][MODEL]["pending"], 1)
        self.assertEqual(len(self.records("attempts.jsonl")), 1)
        self.assertEqual(first["models"][MODEL]["pairs"]["complete"], 0)
        second = self.live(2)
        self.assertEqual(self.generate.call_count, 2)
        self.sleep.assert_called_once_with(3)
        self.assertEqual(second["models"][MODEL]["pairs"]["original_minus_variant_pp"], 100.0)
        self.assertFalse(second["synthetic"])
        self.assertEqual(reanalyze(self.out)["models"], second["models"])
        self.live(2)
        self.assertEqual(self.generate.call_count, 2)
        config = json.loads((self.out / "config.json").read_text())
        self.assertEqual((config["models"], config["provider"], config["temperature"],
                          config["max_tokens"]), ([MODEL], "Pinned", 0, 512))
        self.assertIn("scorer_version", config)
        self.assertIn("created_at", config)
        self.assertNotIn("private-test-key", str(config))
        self.assertEqual([r["synthetic"] for r in self.records("responses.jsonl")], [False, False])
        self.assertEqual([r["synthetic"] for r in self.records("scores.jsonl")], [False, False])
        with (self.out / "results.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r["synthetic"] for r in rows], ["false", "false"])
        self.assertEqual([r["source"] for r in rows], ["openrouter_live", "openrouter_live"])

    def test_429_pauses_with_durable_state_and_resumes_without_repeating_completed(self):
        self.generate.side_effect = [self.reply(), RuntimeError("OpenRouter HTTP 429 rate limited"), self.reply()]
        first = self.live(3)
        self.assertTrue(first["paused"])
        self.assertEqual(first["models"][MODEL]["rate_limited"], 1)
        self.assertEqual(len(self.records("attempts.jsonl")), 2)
        second = self.live(3)
        self.assertFalse(second["paused"])
        self.assertEqual(self.generate.call_count, 3)
        self.assertEqual(len(self.records("responses.jsonl")), 3)
        self.assertEqual(second["models"][MODEL]["pairs"]["complete"], 1)

    def test_uncertain_timeout_blocks_redispatch_and_never_persists_exception(self):
        self.generate.side_effect = RuntimeError("private-test-key timeout uncertain")
        result = self.live()
        self.assertTrue(result["paused"])
        self.assertEqual(result["unresolved_attempts"], 0)
        self.assertEqual(reanalyze(self.out)["unresolved_attempts"], 0)
        self.assertTrue(json.loads((self.out / "summary.json").read_text())["paused"])
        self.assertTrue((self.out / "responses.jsonl").exists())
        responses = self.records("responses.jsonl")
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["status"], "error")
        self.assertNotIn("private-test-key", (self.out / "attempts.jsonl").read_text())
        self.assertNotIn("private-test-key", (self.out / "responses.jsonl").read_text())
        self.assertEqual(self.generate.call_count, 1)

    def test_failure_truncation_and_malformed_log_fail_closed(self):
        self.generate.side_effect = [RuntimeError("OpenRouter HTTP 5xx (503)"),
                                     self.reply(finish_reason="length")]
        result = self.live()
        counts = result["models"][MODEL]
        self.assertEqual((counts["failures"], counts["truncated"], counts["scored"]), (1, 1, 0))
        self.assertEqual(len(self.records("scores.jsonl")), 0)
        with (self.out / "attempts.jsonl").open("ab") as stream:
            stream.write(b'{"attempt_id":')
        with self.assertRaisesRegex(ValueError, "truncated JSONL"):
            self.live()
        self.assertEqual(self.generate.call_count, 2)

    def test_invalid_config_key_and_fixture_directory_are_rejected_before_dispatch(self):
        for model, provider, cap in (("other:free", "Pinned", 2), (MODEL, "", 2), (MODEL, "Pinned", 41)):
            with self.assertRaises(ValueError):
                run_live(self.dataset, self.out, model, provider, cap)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                self.live()
        fixtures = self.root / "fixtures.json"
        fixtures.write_text("{}")
        run(self.dataset, fixtures, self.out)
        with self.assertRaisesRegex(ValueError, "config mismatch"):
            self.live()
        self.generate.assert_not_called()

    def test_cli_never_enables_live_implicitly(self):
        args = ["evaluation", "--dataset", str(self.dataset), "--run-dir", str(self.out),
                "--model", MODEL, "--provider", "Pinned"]
        with patch.object(sys, "argv", args), self.assertRaises(SystemExit) as caught:
            main()
        self.assertEqual(caught.exception.code, 2)
        self.generate.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_returned_model_mismatch_is_failure_not_a_scored_answer(self):
        reply = self.reply()
        reply["returned_model"] = "another/model:free"
        self.generate.return_value = reply
        result = self.live()
        self.assertTrue(result["paused"])
        self.assertEqual(result["models"][MODEL]["failures"], 1)
        self.assertEqual(result["models"][MODEL]["scored"], 0)
        self.assertEqual(self.generate.call_count, 1)
        with self.assertRaisesRegex(ValueError, "suspicious routing"):
            self.live()

    def test_positive_cost_and_comparable_provider_mismatch_halt(self):
        for property_, value in (("cost", 0.01), ("returned_provider_slug", "vendor/other")):
            with self.subTest(property_=property_), tempfile.TemporaryDirectory() as directory:
                self.out = Path(directory) / "run"
                reply = self.reply()
                if property_ == "cost":
                    reply["usage"] = {"cost": value}
                else:
                    reply["returned_provider_slug"] = value
                self.generate.reset_mock(return_value=True, side_effect=True)
                self.generate.return_value = reply
                result = self.live()
                self.assertTrue(result["paused"])
                self.assertEqual(result["models"][MODEL]["failures"], 1)
                self.assertEqual(self.generate.call_count, 1)
                record = self.records("responses.jsonl")[0]
                if property_ == "cost":
                    self.assertEqual(record["usage"]["cost"], value)
                    self.assertEqual(reanalyze(self.out)["paused"], True)
                    self.assertEqual(json.loads((self.out / "summary.json").read_text())["paused"], True)
                with self.assertRaisesRegex(ValueError, "suspicious routing or billing"):
                    self.live()
                self.assertEqual(self.generate.call_count, 1)

    def test_duplicate_success_for_item_blocks_resume_and_reports(self):
        self.generate.return_value = self.reply()
        self.live(1)
        intent = {**self.records("attempts.jsonl")[0], "attempt_id": "second-intent"}
        response = {**self.records("responses.jsonl")[0], "attempt_id": "second-intent"}
        with (self.out / "attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(intent) + "\n")
        with (self.out / "responses.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(response) + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate response key"):
            reanalyze(self.out)
        with self.assertRaisesRegex(ValueError, "duplicate response key"):
            self.live()
        self.assertEqual(self.generate.call_count, 1)

    def test_provider_display_name_is_not_a_comparable_slug(self):
        reply = self.reply()
        reply["provider"] = "A different-looking provider display name"
        reply["returned_provider_slug"] = "Pinned"
        self.generate.return_value = reply
        result = self.live(1)
        self.assertFalse(result["paused"])
        self.assertEqual(result["models"][MODEL]["scored"], 1)

    def test_orphan_response_and_changed_scorer_block_dispatch_and_reanalysis(self):
        self.generate.return_value = self.reply()
        self.live(1)
        with patch("evaluation.runner._scorer_hash", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "scorer version"):
                reanalyze(self.out)
            with self.assertRaisesRegex(ValueError, "config mismatch"):
                self.live(2)
        orphan = {**self.records("responses.jsonl")[0], "attempt_id": "orphan", "item_id": "p"}
        with (self.out / "responses.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(orphan) + "\n")
        with self.assertRaisesRegex(ValueError, "orphan"):
            reanalyze(self.out)
        with self.assertRaisesRegex(ValueError, "orphan"):
            self.live(2)
        self.assertEqual(self.generate.call_count, 1)

    def test_exclusive_lock_prevents_second_dispatch_and_report(self):
        with _locked(self.out):
            with self.assertRaisesRegex(ValueError, "locked"):
                self.live()
            with self.assertRaisesRegex(ValueError, "locked"):
                reanalyze(self.out)
        self.generate.assert_not_called()

    def test_mixed_split_rejected_before_dispatch(self):
        items = [json.loads(line) for line in self.dataset.read_text().splitlines()]
        extra = [{**item, "id": "dev-" + item["id"], "pair_id": "dev",
                  "split": "dev", "prompt": "Development " + item["prompt"]} for item in items]
        self.dataset.write_text("".join(json.dumps(item) + "\n" for item in items + extra))
        with self.assertRaisesRegex(ValueError, "mixed dev/test"):
            self.live()
        self.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
