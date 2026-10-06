"""Hand-counted denominators and CSV for synthetic saved records."""

import csv
import tempfile
import unittest
from pathlib import Path

from evaluation.analysis import analyze, export_csv


class AnalysisTests(unittest.TestCase):
    def test_missing_failure_review_invalid_truncated_and_429(self):
        items = [{"id": f"{n}-{v}", "pair_id": n, "variant": v,
                  "category": "coding" if n == "p3" else "reasoning", "split": "test"}
                 for n in ("p1", "p2", "p3", "p4", "p5") for v in ("original", "paraphrase")]
        def response(id, status="ok", **kwargs):
            return {"model": "fixture-a", "item_id": id, "status": status,
                    "answer": "synthetic answer", **kwargs}

        responses = [response("p1-original"), response("p1-paraphrase"),
                     response("p2-original"), response("p2-paraphrase"),
                     response("p3-original"), response("p3-paraphrase", "error"),
                     response("p4-original"), response("p4-paraphrase", "rate_limited"),
                     response("p5-original", "truncated")]
        def scored(id, correct, status="scored"):
            return {"model": "fixture-a", "item_id": id, "correct": correct, "status": status}

        scores = [scored("p1-original", True), scored("p1-paraphrase", False),
                  scored("p2-original", False), scored("p2-paraphrase", True),
                  scored("p3-original", None, "review"), scored("p4-original", None, "invalid")]
        summary = analyze(items, responses, scores, ["fixture-a"])
        model = summary["models"]["fixture-a"]
        self.assertEqual({k: model[k] for k in ("planned", "answered", "scored", "correct",
                                                 "incorrect", "review", "invalid", "failures",
                                                 "truncated", "rate_limited", "pending")},
                         dict(planned=10, answered=6, scored=4, correct=2, incorrect=2,
                              review=1, invalid=1, failures=1, truncated=1, rate_limited=1, pending=2))
        self.assertEqual(model["accuracy"], 0.5)
        self.assertEqual(model["categories"]["coding"]["accuracy"], None)
        self.assertEqual(model["categories"]["coding"]["review"], 1)
        self.assertEqual(model["categories"]["reasoning"]["scored"], 4)
        self.assertEqual(model["pairs"], {"planned": 5, "complete": 2,
                                          "original_correct": 1, "variant_correct": 1,
                                          "original_minus_variant_pp": 0.0,
                                          "original_correct_variant_wrong": 1,
                                          "original_wrong_variant_correct": 1})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            export_csv(path, items, responses, scores, ["fixture-a"])
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), model["planned"])
        self.assertTrue(all(row["synthetic"] == "true" and row["source"] == "offline_fixture"
                            for row in rows))
        self.assertEqual(sum(row["score_status"] == "scored" for row in rows), model["scored"])
        self.assertEqual(sum(row["score_status"] == "review" for row in rows), model["review"])
        self.assertEqual(sum(row["score_status"] == "invalid" for row in rows), model["invalid"])
        self.assertEqual(sum(row["response_status"] == "rate_limited" for row in rows), 1)
        self.assertEqual(sum(row["response_status"] == "pending" for row in rows), 1)

    def test_unscored_pairs_have_no_delta(self):
        items = [{"id": v, "pair_id": "x", "variant": v, "category": "coding", "split": "test"}
                 for v in ("original", "paraphrase")]
        responses = [{"model": "a", "item_id": v, "status": "ok"} for v in ("original", "paraphrase")]
        scores = [{"model": "a", "item_id": v, "status": "review", "correct": None}
                  for v in ("original", "paraphrase")]
        result = analyze(items, responses, scores, ["a"])["models"]["a"]
        self.assertIsNone(result["accuracy"])
        self.assertIsNone(result["pairs"]["original_minus_variant_pp"])
        self.assertEqual(result["pairs"]["complete"], 0)

    def test_csv_escapes_formula_cells_without_changing_responses_or_counts(self):
        items = [{"id": variant, "pair_id": "p", "variant": variant,
                  "category": "reasoning", "split": "test"}
                 for variant in ("original", "paraphrase")]
        scores = [{"model": "m", "item_id": "original", "status": "scored", "correct": True}]
        for answer in ("=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)",
                       "  =1+1", "\tformula", "\rformula", "\nformula", "ordinary"):
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as directory:
                responses = [{"model": "m", "item_id": "original", "status": "ok", "answer": answer}]
                path = Path(directory) / "results.csv"
                export_csv(path, items, responses, scores, ["m"], source="=formula")
                with path.open(newline="", encoding="utf-8") as stream:
                    row = next(csv.DictReader(stream))
                self.assertEqual(row["answer"], ("'" if answer != "ordinary" else "") + answer)
                self.assertEqual(row["source"], "'=formula")
                self.assertEqual(responses[0]["answer"], answer)
                model = analyze(items, responses, scores, ["m"])["models"]["m"]
                self.assertEqual((model["answered"], model["scored"], model["correct"],
                                  model["accuracy"]), (1, 1, 1, 1.0))


if __name__ == "__main__":
    unittest.main()
