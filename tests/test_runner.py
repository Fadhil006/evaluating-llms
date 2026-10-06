"""Hand-counted synthetic runner checks; no provider calls."""

import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.runner import reanalyze, run


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


if __name__ == "__main__":
    unittest.main()
