import unittest
from pathlib import Path

from evaluation.dataset import load_dataset
from evaluation.scoring import score


class ScoringTests(unittest.TestCase):
    def check(self, scorer, reference, answer, rules, status, correct):
        result = score({"scorer": scorer, "reference_answer": reference, "rules": rules}, answer)
        self.assertEqual((result["status"], result["correct"]), (status, correct))
        self.assertIsInstance(result["explanation"], str)
        self.assertIsInstance(result["checks"], dict)
        return result

    def test_mcq(self):
        self.check("mcq", "B", "Choice: b", {}, "scored", True)
        self.check("mcq", "B", "A", {}, "scored", False)
        self.check("mcq", "B", "A or B", {}, "invalid", None)
        self.check("mcq", "B", "", {}, "invalid", None)

    def test_numeric(self):
        self.check("numeric", "10", "final answer: 10.00009", {}, "scored", True)
        self.check("numeric", "10", "11", {}, "scored", False)
        self.check("numeric", "10", "10 or 11", {}, "invalid", None)
        self.check("numeric", "10", "10 lb", {}, "review", None)
        for answer in ("nan", "inf", "1e9999", "10 11"):
            self.check("numeric", "10", answer, {}, "invalid", None)
        self.check("numeric", "10", "10.1", {"tolerance": 0.2}, "scored", True)
        self.check("numeric", "10", "10", {"tolerance": -1}, "invalid", None)

    def test_numeric_exact_large_values_and_invalid_tolerance(self):
        large = 2**53
        result = self.check("numeric", str(large), str(large + 1), {"tolerance": 0}, "scored", False)
        self.assertEqual(result["checks"]["value"], str(large + 1))
        self.check("numeric", str(large + 1), str(large + 1), {"tolerance": 0}, "scored", True)
        self.check("numeric", "1", "1.1", {"tolerance": 0.1}, "scored", True)
        for tolerance in (True, "0", float("nan"), float("inf")):
            with self.subTest(tolerance=tolerance):
                self.check("numeric", "1", "1", {"tolerance": tolerance}, "invalid", None)
        for reference in ("NaN", "Infinity", "not a number"):
            self.check("numeric", reference, "1", {}, "invalid", None)

    def test_short_answer(self):
        rules = {"accepted_answers": ["NYC", "New York City"]}
        self.check("short_answer", "NYC", "  new   york CITY ", rules, "scored", True)
        self.check("short_answer", "NYC", "York", rules, "scored", False)
        self.check("short_answer", "NYC", " ", rules, "invalid", None)

    def test_instruction_rules(self):
        rules = {"required_keys": ["ok"], "required_json_values": {"ok": "yes"},
                 "forbidden_strings": ["secret"]}
        result = self.check("instruction_rules", "", '{"ok":"yes"}', rules, "scored", True)
        self.assertEqual(result["checks"]["fraction_passed"], 1)
        result = self.check("instruction_rules", "", '{"ok":"no"}', rules, "scored", False)
        self.assertFalse(result["checks"]["required_json_value:ok"])
        self.assertEqual(result["checks"]["fraction_passed"], 0.75)
        result = self.check("instruction_rules", "", '{"other":"SECRET"}', rules, "scored", False)
        self.assertEqual(result["checks"]["fraction_passed"], 0.25)
        result = self.check("instruction_rules", "", "not json", rules, "scored", False)
        self.assertFalse(result["checks"]["valid_json_object"])
        self.assertEqual(result["checks"]["fraction_passed"], 0.25)
        self.check("instruction_rules", "", "[]", rules, "scored", False)
        self.check("instruction_rules", "", "- one\n- two", {"bullet_count": 2}, "scored", True)
        self.check("instruction_rules", "", "- one", {"bullet_count": 2}, "scored", False)

    def test_instruction_rules_require_effective_checks_and_strict_json(self):
        for rules in ({"forbidden_strings": []}, {"required_keys": []},
                      {"required_keys": [], "forbidden_strings": []}):
            with self.subTest(rules=rules):
                self.check("instruction_rules", "", "{}", rules, "invalid", None)
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                result = self.check("instruction_rules", "", '{"ok":' + constant + '}',
                                    {"required_keys": ["ok"]}, "scored", False)
                self.assertFalse(result["checks"]["valid_json_object"])

    def test_summary_proxy(self):
        rules = {"min_words": 2, "max_words": 4, "required_terms": ["Paris"]}
        result = self.check("summary_constraints", "", "Paris is here", rules, "review", None)
        self.assertTrue(result["checks"]["word_range"])
        self.assertTrue(result["checks"]["entity_coverage"])
        self.assertIn("Proxy", result["explanation"])
        result = self.check("summary_constraints", "", "London", rules, "review", None)
        self.assertFalse(result["checks"]["entity_coverage"])
        self.check("summary_constraints", "", "text", {"min_words": 3}, "invalid", None)

    def test_code_never_runs(self):
        import os
        import tempfile

        rules = {"function_name": "solve", "parameters": ["x"]}
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "executed")
            code = f"import pathlib\npathlib.Path({marker!r}).touch()\ndef solve(x):\n    return x\n"
            result = self.check("code_syntax", "", code, rules, "review", None)
            self.assertTrue(all(result["checks"].values()))
            self.assertFalse(os.path.exists(marker))
        result = self.check("code_syntax", "", "def solve(y): return y", rules, "review", None)
        self.assertFalse(result["checks"]["signature"])
        self.check("code_syntax", "", "def solve(:", rules, "invalid", None)
        self.check("code_syntax", "", "pass", rules, "review", None)

    def test_bad_inputs(self):
        self.check("unknown", "", "answer", {}, "invalid", None)
        self.assertEqual(score({}, None)["status"], "invalid")
        self.assertEqual(score({"scorer": "mcq", "rules": []}, "A")["status"], "invalid")

    def test_dataset_reference_answers(self):
        path = Path(__file__).resolve().parents[1] / "datasets/v1.0/benchmark.jsonl"
        items = load_dataset(path)
        self.assertTrue(items)
        for item in items:
            with self.subTest(item=item["id"]):
                result = score(item, item["reference_answer"])
                if item["scorer"] in {"code_syntax", "summary_constraints"}:
                    self.assertEqual((result["status"], result["correct"]), ("review", None))
                    self.assertTrue(all(v for k, v in result["checks"].items() if k != "word_count"))
                else:
                    self.assertEqual((result["status"], result["correct"]), ("scored", True))


if __name__ == "__main__":
    unittest.main()
