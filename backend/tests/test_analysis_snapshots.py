from app.services.analysis import aggregate, create_snapshot


def test_complete_family_pairing_and_missingness_three_families():
    planned, scores = [], []
    # F2 loses its variant; F3 loses both keys. B therefore has three, not four,
    # eligible complete families, and incomplete families are omitted for both.
    for family in ("F1", "F2", "F3", "F4", "F5"):
        for variant in ("original", "paraphrase"):
            item = f"{family}-{variant}"
            planned.append({"item_id": item, "family_id": family, "split": "test",
                            "variant_id": variant, "repetition": 0, "variant": "baseline"})
            if family == "F3" or (family == "F2" and variant == "paraphrase"):
                continue
            for slot, value in ((0, 0.0), (1, 1.0)):
                scores.append({"item_id": item, "model_slot": slot, "task_type": "multiple_choice",
                               "metric": "label_accuracy", "value": value})
    result = aggregate(planned, scores)[0]
    assert result["family_n"] == 3
    assert result["model_means"] == {0: 0.0, 1: 1.0}
    assert result["paired_delta"] == 1.0
    assert result["interval_95"] is None
    assert result["omitted_families"] == [["F2", "test"], ["F3", "test"]]


def test_legacy_has_no_independent_family_inference_and_hash_is_stable():
    planned = [{"item_id": "old-1", "repetition": 0, "variant": "baseline"}]
    observations = [{"item_id": "old-1", "model_slot": 0, "task_type": "qa", "metric": "f1", "value": .5},
                   {"item_id": "old-1", "model_slot": 1, "task_type": "qa", "metric": "f1", "value": .7}]
    first = create_snapshot({"experiment_id": 1}, planned, observations, seed=4)
    second = create_snapshot({"experiment_id": 1}, planned, observations, seed=4)
    row = first["results"][0]
    assert first["sha256"] == second["sha256"]
    assert row["family_n"] is None and row["interval_95"] is None
    assert row["missing_family_metadata"] is True


def test_bootstrap_reproducible_and_degenerate():
    planned, scores = [], []
    for i in range(10):
        planned.append({"item_id": str(i), "family_id": f"f{i}", "split": "test"})
        for slot, value in ((0, .2), (1, .5)):
            scores.append({"item_id": str(i), "model_slot": slot, "task_type": "qa", "metric": "f1",
                           "value": value})
    a = aggregate(planned, scores, seed=91)[0]
    b = aggregate(planned, scores, seed=91)[0]
    assert a["interval_95"] == b["interval_95"]
    assert a["interval_95"] == {"low": .3, "high": .3, "degenerate": True}


def test_original_only_keeps_families_with_missing_variant():
    planned = [{"item_id": f"f-{variant}", "family_id": "f", "split": "test",
                "variant_id": variant, "task_type": "instruction_following"}
               for variant in ("original", "paraphrase")]
    scores = [{"item_id": "f-original", "model_slot": slot, "task_type": "instruction_following",
               "metric": "instruction_all_checks", "value": value}
              for slot, value in ((0, 0), (1, 1))]
    result = aggregate(planned, scores)[0]
    assert result["family_n"] == 0
    assert result["original_only_delta"] == 1


def test_paired_bootstrap_uses_independent_families_and_is_reversible():
    planned = [{"item_id": f"f{i}-{repeat}", "family_id": f"f{i}", "split": "test",
                "task_type": "multiple_choice", "repetition": repeat}
               for i in range(10) for repeat in range(2)]
    scores = [{"item_id": row["item_id"], "repetition": row["repetition"],
               "model_slot": slot, "task_type": "multiple_choice", "metric": "label_accuracy",
               "value": (i % 2 if slot == 1 else 0)}
              for i in range(10) for row in planned[2 * i:2 * i + 2] for slot in (0, 1)]
    forward = aggregate(planned, scores, selected_slots=(0, 1), seed=9)[0]
    backward = aggregate(planned, scores, selected_slots=(1, 0), seed=9)[0]
    assert forward["family_n"] == 10 and forward["paired_delta"] == 0.5
    assert forward["interval_95"]["low"] < forward["interval_95"]["high"]
    assert backward["paired_delta"] == -forward["paired_delta"]
    assert backward["interval_95"]["low"] == -forward["interval_95"]["high"]
