import ast
import json
import tempfile
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

from evaluation.dataset import load_dataset, select_pairs, validate_dataset


ROOT = Path(__file__).resolve().parents[1] / "datasets" / "v1.0"


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_items = load_dataset(ROOT / "benchmark.jsonl")
        cls.dev_items = load_dataset(ROOT / "dev.jsonl")

    def test_authored_items_and_references(self):
        items = self.test_items
        self.assertEqual(len(items), 24)
        self.assertEqual(Counter(x["category"] for x in items if x["variant"] == "original"),
                         {category: 2 for category in
                          ("reasoning", "math", "coding", "knowledge", "summarization", "instruction")})
        self.assertEqual({x["split"] for x in items}, {"test"})
        self.assertEqual({x["split"] for x in self.dev_items}, {"dev"})
        validate_dataset(items + self.dev_items)
        # Independently check each objective reference and rule-shaped proxy example.
        expected = {"r1": "B", "r2": "C", "m1": "36", "m2": "6",
                    "k1": "B", "k2": "Au"}
        for item in items:
            pair = item["pair_id"]
            if pair in expected:
                self.assertEqual(item["reference_answer"], expected[pair])
            if item["scorer"] == "code_syntax":
                function = ast.parse(item["reference_answer"]).body[0]
                self.assertIsInstance(function, ast.FunctionDef)
                self.assertEqual(function.name, item["rules"]["function_name"])
                self.assertEqual([arg.arg for arg in function.args.args], item["rules"]["parameters"])
            if item["scorer"] == "summary_constraints":
                answer, rules = item["reference_answer"], item["rules"]
                self.assertLessEqual(rules["min_words"], len(answer.split()))
                self.assertLessEqual(len(answer.split()), rules["max_words"])
                self.assertTrue(all(term.casefold() in answer.casefold() for term in rules["required_terms"]))
            if item["scorer"] == "instruction_rules":
                answer, rules = item["reference_answer"], item["rules"]
                if "required_keys" in rules:
                    self.assertTrue(set(rules["required_keys"]) <= json.loads(answer).keys())
                if "required_json_values" in rules:
                    self.assertEqual(pair, "i1")
                    self.assertEqual(rules["required_json_values"], {"city": "Oslo", "color": "blue"})
                    self.assertTrue(all(json.loads(answer).get(key) == value
                                        for key, value in rules["required_json_values"].items()))
                if "bullet_count" in rules:
                    self.assertEqual(sum(line.startswith("- ") for line in answer.splitlines()), rules["bullet_count"])
                self.assertTrue(all(word not in answer for word in rules["forbidden_strings"]))

    def test_reject_invalid_schema_and_pairs(self):
        changes = [
            lambda rows: rows[0].pop("prompt"),
            lambda rows: rows[1].update(id=rows[0]["id"]),
            lambda rows: rows[1].update(prompt=rows[0]["prompt"].upper()),
            lambda rows: rows[1].update(variant="original"),
            lambda rows: rows.pop(1),
            lambda rows: rows[1].update(split="dev"),
            lambda rows: rows[1].update(category="math"),
            lambda rows: rows[1].update(reference_answer="A"),
            lambda rows: rows[1].update(rules={"bogus": 1}),
            lambda rows: rows[0].update(category="bogus"),
            lambda rows: rows[0].update(scorer="bogus"),
            lambda rows: rows[0].update(rules={"tolerance": 0.1}),
            lambda rows: rows[0].update(dataset_version="v2"),
            lambda rows: rows[0].update(reference_answer="E"),
            lambda rows: rows[4].update(reference_answer="not a number"),
            lambda rows: rows[5].update(rules={"tolerance": 0.5}),
            lambda rows: rows[8].update(reference_answer="def double(n):\n  return ("),
            lambda rows: rows[14].update(rules={"accepted_answers":["Ag"]}),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                rows = deepcopy(self.test_items)
                change(rows)
                with self.assertRaises(ValueError):
                    validate_dataset(rows)

    def test_load_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"id":\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                load_dataset(path)

    def test_load_rejects_nonstandard_json_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(constant=constant):
                    path.write_text('{"value":' + constant + '}\n', encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "line 1: invalid JSON"):
                        load_dataset(path)

    def test_reject_instruction_rules_without_effective_checks(self):
        for rules in ({"forbidden_strings": []}, {"required_keys": []},
                      {"required_keys": [], "forbidden_strings": []}):
            with self.subTest(rules=rules):
                rows = deepcopy(self.test_items)
                rows[20]["rules"] = rows[21]["rules"] = rules
                with self.assertRaisesRegex(ValueError, "effective check"):
                    validate_dataset(rows)

    def test_numeric_reference_preserves_large_integers(self):
        rows = deepcopy(self.test_items)
        rows[4]["reference_answer"] = rows[5]["reference_answer"] = str(2**53 + 1)
        rows[4]["rules"] = rows[5]["rules"] = {"tolerance": 0}
        validate_dataset(rows)
        for tolerance in (True, float("nan"), float("inf")):
            with self.subTest(tolerance=tolerance):
                rows[4]["rules"] = {"tolerance": tolerance}
                with self.assertRaisesRegex(ValueError, "invalid numeric tolerance"):
                    validate_dataset(rows)

    def test_reject_malformed_required_json_values(self):
        for values in ({}, [], {"city": 5}, {"": "Oslo"}, {"city": "  "}, {5: "Oslo"}):
            with self.subTest(values=values):
                rows = deepcopy(self.test_items)
                rows[20]["rules"]["required_json_values"] = values
                rows[21]["rules"]["required_json_values"] = values
                with self.assertRaisesRegex(ValueError, "invalid required_json_values"):
                    validate_dataset(rows)

    def test_select_pairs_requires_unique_complete_single_split(self):
        rows = self.dev_items + self.test_items
        selected = select_pairs(rows, [self.test_items[2]["pair_id"]])
        self.assertEqual(len(selected), 2)
        self.assertEqual({item["variant"] for item in selected}, {"original", "paraphrase"})
        self.assertEqual({item["split"] for item in selected}, {"test"})
        self.assertIs(select_pairs(self.dev_items), self.dev_items)
        for ids, message in (([], "nonempty"), (["r1", "r1"], "unique"),
                             (["absent"], "unknown"),
                             ([self.dev_items[0]["pair_id"], "r1"], "one split")):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, message):
                select_pairs(rows, ids)
        with self.assertRaisesRegex(ValueError, "expected original and paraphrase"):
            select_pairs(self.dev_items[:-1], [self.dev_items[-2]["pair_id"]])


if __name__ == "__main__":
    unittest.main()
