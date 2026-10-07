"""Offline counts and paired accuracy from frozen items and saved records."""

import csv
import math
import os
from statistics import mean, median


def _counts(planned):
    return {"total": planned, "planned": planned, "answered": 0, "scored": 0, "correct": 0,
            "incorrect": 0, "accuracy": None, "review": 0, "invalid": 0, "unscored": 0,
            "failures": 0, "truncated": 0, "rate_limited": 0, "pending": planned}


def analyze(items, responses, scores, models, *, synthetic=True, source="offline_fixture"):
    """Return metrics; only objectively scored answers enter accuracy and pairs."""
    by_id = {item["id"]: item for item in items}
    response_by_key = {}
    for response in responses:
        key = (response["model"], response["item_id"])
        if key[0] not in models or key[1] not in by_id or (key in response_by_key and
                response_by_key[key]["status"] != "rate_limited"):
            raise ValueError(f"unexpected or duplicate response key: {key}")
        response_by_key[key] = response
    score_by_key = {}
    for record in scores:
        key = (record["model"], record["item_id"])
        if (key in score_by_key or key not in response_by_key or
                response_by_key[key]["status"] != "ok" or
                response_by_key[key].get("finish_reason") == "length"):
            raise ValueError(f"unexpected or duplicate score key: {key}")
        score_by_key[key] = record

    summaries = {}
    for model in models:
        categories = {category: _counts(sum(i["category"] == category for i in items))
                      for category in sorted({item["category"] for item in items})}
        overall = _counts(len(items))
        objective = {}
        latencies = []
        for item in items:
            key = (model, item["id"])
            response = response_by_key.get(key)
            record = score_by_key.get(key)
            for counts in (overall, categories[item["category"]]):
                if response is None:
                    continue
                status = response["status"]
                if status == "rate_limited":
                    counts["rate_limited"] += 1
                    continue
                counts["pending"] -= 1
                if status == "truncated" or response.get("finish_reason") == "length":
                    counts["truncated"] += 1
                elif status != "ok":
                    counts["failures"] += 1
                else:
                    counts["answered"] += 1
                    if (counts is overall and not synthetic and source in
                            {"openrouter_live", "opencode_live"} and
                            type(response.get("latency_ms")) in (int, float) and
                            math.isfinite(response["latency_ms"]) and response["latency_ms"] >= 0):
                        latencies.append(response["latency_ms"])
                    if record is None:
                        counts["unscored"] += 1
                    elif record["status"] == "scored" and type(record["correct"]) is bool:
                        counts["scored"] += 1
                        counts["correct" if record["correct"] else "incorrect"] += 1
                        objective[key] = record["correct"]
                    elif record["status"] == "review":
                        counts["review"] += 1
                    else:
                        counts["invalid"] += 1
        for counts in (overall, *categories.values()):
            if counts["scored"]:
                counts["accuracy"] = counts["correct"] / counts["scored"]
        pairs = {}
        for item in items:
            pair = pairs.setdefault(item["pair_id"], {})
            pair[item["variant"]] = item["id"]
        complete = [(objective[(model, pair["original"])], objective[(model, pair["paraphrase"])])
                    for pair in pairs.values() if {"original", "paraphrase"} <= pair.keys()
                    and (model, pair["original"]) in objective
                    and (model, pair["paraphrase"]) in objective]
        orig_correct = sum(original for original, _ in complete)
        variant_correct = sum(variant for _, variant in complete)
        overall["categories"] = categories
        overall["latency_ms"] = {"count": len(latencies), "average": mean(latencies) if latencies else None,
                                 "median": median(latencies) if latencies else None}
        overall["pairs"] = {"planned": len(pairs), "complete": len(complete),
                            "original_scored": len(complete), "paraphrase_scored": len(complete),
                            "original_correct": orig_correct, "variant_correct": variant_correct,
                            "original_accuracy": orig_correct / len(complete) if complete else None,
                            "paraphrase_accuracy": variant_correct / len(complete) if complete else None,
                            "original_minus_variant_pp": 100 * (orig_correct - variant_correct) / len(complete)
                            if complete else None,
                            "original_correct_variant_wrong": sum(o and not v for o, v in complete),
                            "original_wrong_variant_correct": sum(not o and v for o, v in complete)}
        summaries[model] = overall

    # Comparison metrics use only item IDs objectively scored for every model.
    matched = {item_id for item_id in by_id
               if all((model, item_id) in score_by_key and
                      score_by_key[(model, item_id)]["status"] == "scored" and
                      type(score_by_key[(model, item_id)]["correct"]) is bool
                      for model in models)}
    matched_by_category = {}
    for category in sorted({item["category"] for item in items}):
        category_ids = {item["id"] for item in items
                        if item["category"] == category and item["id"] in matched}
        matched_by_category[category] = {
            model: {"scored": len(category_ids),
                    "correct": sum(score_by_key[(model, item_id)]["correct"]
                                   for item_id in category_ids),
                    "accuracy": (sum(score_by_key[(model, item_id)]["correct"]
                                     for item_id in category_ids) / len(category_ids)
                                 if category_ids else None)}
            for model in models
        }
    comparison = {"matched_questions": len(matched),
                  "models": {model: {
                      "scored": len(matched),
                      "correct": sum(score_by_key[(model, item_id)]["correct"] for item_id in matched),
                      "accuracy": (sum(score_by_key[(model, item_id)]["correct"]
                                       for item_id in matched) / len(matched) if matched else None)}
                      for model in models},
                   "categories": matched_by_category,
                   "category_matched_questions": {category: rows[models[0]]["scored"]
                                                  for category, rows in matched_by_category.items()} if models else {}}
    if len(models) == 2:
        accuracies = [comparison["models"][model]["accuracy"] for model in models]
        comparison["accuracy_difference_pp"] = (100 * (accuracies[0] - accuracies[1])
                                                   if all(value is not None for value in accuracies)
                                                   else None)
    return {"synthetic": synthetic, "source": source, "models": summaries,
            "matched_comparison": comparison}


CSV_FIELDS = ("synthetic", "source", "model", "item_id", "pair_id", "variant", "split",
              "category", "response_status", "score_status", "correct", "answer", "error", "latency_ms")


def _csv_cell(value):
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@"))
                                   or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


def export_csv(path, items, responses, scores, models, *, synthetic=True, source="offline_fixture"):
    """Export one row per planned model/item; derive entirely from saved records."""
    response_by_key = {(r["model"], r["item_id"]): r for r in responses}
    score_by_key = {(s["model"], s["item_id"]): s for s in scores}
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for model in models:
            for item in items:
                key = (model, item["id"])
                response = response_by_key.get(key, {})
                score = score_by_key.get(key, {})
                status = response.get("status", "pending")
                if status == "ok" and response.get("finish_reason") == "length":
                    status = "truncated"
                row = {"synthetic": str(synthetic).lower(), "source": source, "model": model,
                                 "item_id": item["id"], "pair_id": item["pair_id"],
                                 "variant": item["variant"], "split": item["split"],
                                 "category": item["category"], "response_status": status,
                                 "score_status": score.get("status", ""), "correct":
                                 str(score["correct"]).lower() if score.get("correct") is not None else "",
                                 "answer": response.get("answer") or "", "error": response.get("error") or "",
                                 "latency_ms": response.get("latency_ms", "")}
                writer.writerow({field: _csv_cell(value) for field, value in row.items()})
    os.replace(tmp, path)
