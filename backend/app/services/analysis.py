"""Deterministic local analysis snapshots; persistence and HTTP belong to callers."""

import hashlib
import json
import random
from collections import defaultdict

ANALYSIS_VERSION = "paired-family-v1"
BOOTSTRAP_DRAWS = 10_000


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _number(row):
    value = row.get("value")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _ci(differences, seed):
    n = len(differences)
    if n < 10:
        return None
    if len(set(differences)) == 1:
        return {"low": differences[0], "high": differences[0], "degenerate": True}
    rng = random.Random(seed)
    draws = sorted(sum(differences[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAP_DRAWS))
    return {"low": draws[int(.025 * BOOTSTRAP_DRAWS)],
            "high": draws[int(.975 * BOOTSTRAP_DRAWS) - 1], "degenerate": False}


def aggregate(planned, observations, *, selected_slots=(0, 1), seed=0):
    """Aggregate explicit planned keys and score rows.

    Rows use item_id, model_slot, task_type, metric, repetition, variant, value;
    planned rows additionally carry family_id, split, and variant_id where known.
    Missing family metadata is deliberately not inferred from item IDs.
    """
    slots = tuple(selected_slots)
    if len(slots) != 2 or slots[0] == slots[1]:
        raise ValueError("paired analysis requires two distinct model slots")
    meta, key_family, key_task = {}, {}, {}
    for row in planned:
        item = row.get("item_id")
        family = getattr(row, "family_id", None) if not isinstance(row, dict) else row.get("family_id")
        split = getattr(row, "split", None) if not isinstance(row, dict) else row.get("split")
        variant_id = getattr(row, "variant_id", None) if not isinstance(row, dict) else row.get("variant_id")
        family_key = (family, split) if family is not None else None
        if family is not None:
            meta[item] = {"family_id": family, "split": split, "variant_id": variant_id}
        key_family[(item, row.get("repetition", 0), row.get("variant", "baseline"))] = family_key
        key_task[(item, row.get("repetition", 0), row.get("variant", "baseline"))] = row.get("task_type")

    vals = {}
    metrics = set()
    for row in observations:
        key = (row.get("item_id"), row.get("repetition", 0), row.get("variant", "baseline"))
        identity = (row.get("task_type"), row.get("metric"))
        metrics.add(identity)
        value = _number(row)
        if row.get("model_slot") in slots and value is not None:
            vals[(identity, row["model_slot"], key)] = value

    analyses = []
    for task, metric in sorted(metrics):
        family_keys = defaultdict(set)
        for key, family in key_family.items():
            if family is not None and key_task[key] in (None, task):
                family_keys[family].add(key)
        eligible = {}
        for family, keys in family_keys.items():
            common = {key for key in keys if all(((task, metric), slot, key) in vals for slot in slots)}
            # One aggregate observation per family: average planned repeats/variants, never inflate n.
            if common and len(common) == len(keys):
                eligible[family] = [sum(vals[((task, metric), slot, key)] for key in keys) / len(keys)
                                    for slot in slots]
        diffs = [eligible[f][1] - eligible[f][0] for f in sorted(eligible)]
        fam_means = [sum(pair[i] for pair in eligible.values()) / len(eligible) if eligible else None
                     for i in range(2)]
        delta = sum(diffs) / len(diffs) if diffs else None
        analyses.append({"task_type": task, "metric": metric,
                         "family_n": len(eligible) if family_keys else None,
                         "model_means": dict(zip(slots, fam_means)), "paired_delta": delta,
                         "interval_95": _ci(diffs, seed) if family_keys else None,
                         "missing_family_metadata": not bool(family_keys),
                         "omitted_families": [list(f) for f in sorted(set(family_keys) - set(eligible), key=str)],
                          "original_only_delta": _subset_delta(family_keys, meta, key_family, vals,
                                                               task, metric, slots, "original"),
                         "variant_deltas": _variant_deltas(eligible, meta, key_family, vals,
                                                           task, metric, slots)})
    return analyses


def _subset_delta(family_keys, meta, key_family, vals, task, metric, slots, wanted):
    # Original-only is computed only when the dataset declares variant IDs.
    deltas = []
    for planned_keys in family_keys.values():
        keys = [key for key in planned_keys if meta.get(key[0], {}).get("variant_id") == wanted]
        if keys and all(((task, metric), slot, key) in vals for key in keys for slot in slots):
            deltas.append(sum(vals[((task, metric), slots[1], k)] - vals[((task, metric), slots[0], k)]
                              for k in keys) / len(keys))
    return sum(deltas) / len(deltas) if deltas else None


def _variant_deltas(eligible, meta, key_family, vals, task, metric, slots):
    result = {}
    variants = {meta.get(item, {}).get("variant_id") for item, _, _ in key_family}
    for variant in sorted((v for v in variants if v is not None and v != "original"), key=str):
        delta = _subset_delta({family: {key for key, owner in key_family.items() if owner == family}
                               for family in eligible}, meta, key_family, vals, task, metric, slots, variant)
        if delta is not None:
            result[str(variant)] = delta
    return result


def create_snapshot(manifest, planned, observations, *, selected_slots=(0, 1), seed=0):
    """Return a content-addressed immutable snapshot payload; performs no writes."""
    body = {"analysis_version": ANALYSIS_VERSION, "manifest": manifest,
            "selected_model_slots": list(selected_slots),
            "sampling": {"seed": seed, "draws": BOOTSTRAP_DRAWS},
            "planned": list(planned), "observations": list(observations),
            "results": aggregate(planned, observations, selected_slots=selected_slots, seed=seed)}
    snapshot_hash = hashlib.sha256(_canonical(body).encode()).hexdigest()
    return {**body, "sha256": snapshot_hash}
