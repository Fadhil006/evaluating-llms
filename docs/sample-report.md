# Experiment report

**DEMONSTRATION — synthetic responses, no live API calls**

Name: ```
Synthetic ten-item sample
```
Status: `completed`

## Provenance

```
{
  "dataset": {
    "id": 1,
    "name": "LLM Comparison Lab Original Demo",
    "description": "Newly authored demonstration items; not an established benchmark.",
    "origin": "original",
    "source": "Original examples authored for LLM Comparison Lab",
    "license": "CC0-1.0",
    "version_id": 1,
    "version": "v1",
    "content_sha256": "504ac5e28305ae7a284c8f8bde576024edeeb185aa7fe48c0ec10c6f9ec096a3",
    "manifest": {
      "import_schema_version": "1",
      "content_sha256": "504ac5e28305ae7a284c8f8bde576024edeeb185aa7fe48c0ec10c6f9ec096a3",
      "source": "Original examples authored for LLM Comparison Lab",
      "license": "CC0-1.0",
      "format": "jsonl",
      "row_count": 30,
      "duplicate_content": [],
      "duplicate_content_acknowledged": false,
      "category_inventory": {
        "arithmetic": 5,
        "instruction_following": 5,
        "multiple_choice": 5,
        "short_factual": 5,
        "structured_extraction": 5,
        "summarization": 5
      }
    },
    "category_inventory": {
      "arithmetic": 5,
      "instruction_following": 5,
      "multiple_choice": 5,
      "short_factual": 5,
      "structured_extraction": 5,
      "summarization": 5
    },
    "import_schema_version": "1",
    "selected_item_ids": [
      "ar-01",
      "if-01",
      "if-02",
      "mc-01",
      "mc-05",
      "se-02",
      "se-05",
      "sf-04",
      "sf-05",
      "su-01"
    ]
  },
  "models": [
    {
      "slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "display_name": "DEMONSTRATION — synthetic Alpha",
      "endpoint": "chat/completions",
      "capabilities": {
        "context_length": 4096
      },
      "supported_parameters": [
        "max_tokens"
      ],
      "pricing": {
        "provenance": "synthetic_fixture"
      },
      "pricing_source": "fixture://local",
      "pricing_checked_at": "2026-10-08T06:53:00.955218",
      "pricing_expires_at": "2026-10-08T07:08:00.955218",
      "provider_version": {},
      "availability": "available",
      "selected_snapshot_id": 1
    },
    {
      "slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "display_name": "DEMONSTRATION — synthetic Beta",
      "endpoint": "chat/completions",
      "capabilities": {
        "context_length": 4096
      },
      "supported_parameters": [
        "max_tokens"
      ],
      "pricing": {
        "provenance": "synthetic_fixture"
      },
      "pricing_source": "fixture://local",
      "pricing_checked_at": "2026-10-08T06:53:00.955218",
      "pricing_expires_at": "2026-10-08T07:08:00.955218",
      "provider_version": {},
      "availability": "available",
      "selected_snapshot_id": 2
    }
  ]
}
```

## Responses

### Slot 0 — item ```
sf-04
```

Status: `succeeded`

```
Which shelf holds the fictional museum's clay bowl? Answer with the shelf number only.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
sf-04
```

Status: `succeeded`

```
Which shelf holds the fictional museum's clay bowl? Answer with the shelf number only.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
mc-01
```

Status: `succeeded`

```
In the fictional Cedar Hall schedule, the blue room opens at 09:00, the amber room at 10:30, and the green room at 08:15. Which room opens first? Reply with one letter.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
mc-01
```

Status: `succeeded`

```
In the fictional Cedar Hall schedule, the blue room opens at 09:00, the amber room at 10:30, and the green room at 08:15. Which room opens first? Reply with one letter.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
if-02
```

Status: `succeeded`

```
Write exactly two lines: the first line must be north and the second line must be south. Use lowercase letters only and no other text.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
if-02
```

Status: `succeeded`

```
Write exactly two lines: the first line must be north and the second line must be south. Use lowercase letters only and no other text.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
sf-05
```

Status: `succeeded`

```
What is the destination of the fictional ferry Dawn? Answer with the destination name only.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
sf-05
```

Status: `succeeded`

```
What is the destination of the fictional ferry Dawn? Answer with the destination name only.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
se-02
```

Status: `succeeded`

```
Extract the room and start time from the notice. Reply with only a JSON object with exactly the keys room (string) and start (string in HH:MM format).
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
se-02
```

Status: `succeeded`

```
Extract the room and start time from the notice. Reply with only a JSON object with exactly the keys room (string) and start (string in HH:MM format).
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
se-05
```

Status: `succeeded`

```
Extract the adopted pet's name and adoption status. Reply with only a JSON object with exactly the keys pet (string) and adopted (boolean).
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
se-05
```

Status: `succeeded`

```
Extract the adopted pet's name and adoption status. Reply with only a JSON object with exactly the keys pet (string) and adopted (boolean).
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
su-01
```

Status: `succeeded`

```
Summarize the following fictional update in one sentence.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
su-01
```

Status: `succeeded`

```
Summarize the following fictional update in one sentence.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
mc-05
```

Status: `succeeded`

```
A note says that every red folder is stored upstairs, while the single yellow folder is downstairs. Where is the yellow folder? Reply with one letter.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
mc-05
```

Status: `succeeded`

```
A note says that every red folder is stored upstairs, while the single yellow folder is downstairs. Where is the yellow folder? Reply with one letter.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
ar-01
```

Status: `succeeded`

```
A studio has 18 blank cards and uses 7 for invitations. How many blank cards remain? Give the final answer as a single number without units.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
ar-01
```

Status: `succeeded`

```
A studio has 18 blank cards and uses 7 for invitations. How many blank cards remain? Give the final answer as a single number without units.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 1 — item ```
if-01
```

Status: `succeeded`

```
Write exactly one line containing only the lowercase word lantern.
```

```
DEMONSTRATION — synthetic fixture response.
```

### Slot 0 — item ```
if-01
```

Status: `succeeded`

```
Write exactly one line containing only the lowercase word lantern.
```

```
DEMONSTRATION — synthetic fixture response.
```

## Aggregates

```
{
  "experiment_id": 1,
  "selected_model_slots": [
    0,
    1
  ],
  "summaries": [
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "arithmetic",
      "metric": "numeric_exact",
      "scorer_version": "1",
      "scheduled_jobs": 1,
      "responses": 1,
      "complete": 1,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 1,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 1,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 1,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 1,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "instruction_following",
      "metric": "checks_passed",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": null,
      "overall_success": null,
      "overall_success_denominator": null,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "instruction_following",
      "metric": "instruction_checks",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "multiple_choice",
      "metric": "label_accuracy",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "short_factual",
      "metric": "normalized_exact_match",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "short_factual",
      "metric": "raw_exact_match",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "structured_extraction",
      "metric": "field_exact",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "structured_extraction",
      "metric": "json_valid",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "structured_extraction",
      "metric": "schema_valid",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 0,
      "provider": "fixture",
      "model_id": "fixture/alpha-v1",
      "task_type": "summarization",
      "metric": "rouge_l_f1",
      "scorer_version": "1",
      "scheduled_jobs": 1,
      "responses": 1,
      "complete": 1,
      "truncated": 0,
      "parseable": 1,
      "metric_eligible": 1,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 1,
      "macro_f1": null,
      "successes": null,
      "overall_success": null,
      "overall_success_denominator": null,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 2,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "arithmetic",
      "metric": "numeric_exact",
      "scorer_version": "1",
      "scheduled_jobs": 1,
      "responses": 1,
      "complete": 1,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 1,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 1,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 1,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 1,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "instruction_following",
      "metric": "checks_passed",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": null,
      "overall_success": null,
      "overall_success_denominator": null,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "instruction_following",
      "metric": "instruction_checks",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "multiple_choice",
      "metric": "label_accuracy",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "short_factual",
      "metric": "normalized_exact_match",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "short_factual",
      "metric": "raw_exact_match",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 2,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "structured_extraction",
      "metric": "field_exact",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "structured_extraction",
      "metric": "json_valid",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "structured_extraction",
      "metric": "schema_valid",
      "scorer_version": "1",
      "scheduled_jobs": 2,
      "responses": 2,
      "complete": 2,
      "truncated": 0,
      "parseable": 0,
      "metric_eligible": 2,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 2,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 2,
      "macro_f1": null,
      "successes": 0,
      "overall_success": 0.0,
      "overall_success_denominator": 2,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    },
    {
      "model_slot": 1,
      "provider": "fixture",
      "model_id": "fixture/beta-v1",
      "task_type": "summarization",
      "metric": "rouge_l_f1",
      "scorer_version": "1",
      "scheduled_jobs": 1,
      "responses": 1,
      "complete": 1,
      "truncated": 0,
      "parseable": 1,
      "metric_eligible": 1,
      "missing_reference": 0,
      "failures": 0,
      "pending": 0,
      "cancelled": 0,
      "identity_mismatch": 0,
      "format_failures": 0,
      "unscored": 0,
      "quality": 0.0,
      "quality_denominator": 1,
      "macro_f1": null,
      "successes": null,
      "overall_success": null,
      "overall_success_denominator": null,
      "latency_sample_count": 10,
      "median_request_latency_ms": 1.0,
      "p95_request_latency_ms": 1,
      "usage_sample_count": 0,
      "prompt_tokens_total": null,
      "completion_tokens_total": null
    }
  ],
  "common_completed": [
    {
      "task_type": "arithmetic",
      "metric": "numeric_exact",
      "keys": [
        {
          "item_id": "ar-01",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 1,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 1,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 1,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "instruction_following",
      "metric": "checks_passed",
      "keys": [
        {
          "item_id": "if-01",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "if-02",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "instruction_following",
      "metric": "instruction_checks",
      "keys": [
        {
          "item_id": "if-01",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "if-02",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "multiple_choice",
      "metric": "label_accuracy",
      "keys": [
        {
          "item_id": "mc-01",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "mc-05",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "short_factual",
      "metric": "normalized_exact_match",
      "keys": [
        {
          "item_id": "sf-04",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "sf-05",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "short_factual",
      "metric": "raw_exact_match",
      "keys": [
        {
          "item_id": "sf-04",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "sf-05",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "structured_extraction",
      "metric": "field_exact",
      "keys": [
        {
          "item_id": "se-02",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "se-05",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "structured_extraction",
      "metric": "json_valid",
      "keys": [
        {
          "item_id": "se-02",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "se-05",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "structured_extraction",
      "metric": "schema_valid",
      "keys": [
        {
          "item_id": "se-02",
          "repetition": 0,
          "variant": "baseline"
        },
        {
          "item_id": "se-05",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 2,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 2,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    },
    {
      "task_type": "summarization",
      "metric": "rouge_l_f1",
      "keys": [
        {
          "item_id": "su-01",
          "repetition": 0,
          "variant": "baseline"
        }
      ],
      "count": 1,
      "models": [
        {
          "model_slot": 0,
          "eligible_count": 1,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        },
        {
          "model_slot": 1,
          "eligible_count": 1,
          "omitted_count": 0,
          "omitted_keys": [],
          "quality": 0.0
        }
      ]
    }
  ]
}
```

## Human review

```
{
  "rubric": {
    "ratings": [],
    "dimensions": {
      "accuracy": {
        "mean": null,
        "count": 0
      },
      "relevance": {
        "mean": null,
        "count": 0
      },
      "fluency": {
        "mean": null,
        "count": 0
      },
      "transparency": {
        "mean": null,
        "count": 0
      },
      "safety": {
        "mean": null,
        "count": 0
      },
      "task_alignment": {
        "mean": null,
        "count": 0
      }
    },
    "by_model": {},
    "evaluators_per_model_slot": {}
  },
  "pairwise": []
}
```

## Limitations

- Convenience sample; not representative of all tasks or users.
- Route latency is measured under this run's conditions, not intrinsic model speed.
- Human evaluator labels are local and unauthenticated; review is not accuracy.
- Fixture provenance indicates synthetic responses, not live provider performance.
- Unknown usage remains unknown; absent responses remain missing, not zero.
