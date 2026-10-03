# Implementation Plan: LLM Evaluation Platform

## Brief overview

We will implement the project as an **LLM evaluation platform with a focused research experiment built into it**. The platform will test several models on the same questions, measure their performance, show where they fail, and produce a comparison report.

The original survey provides the framework for deciding what to test. Our implementation will turn that framework into a working application.

**Planning assumptions:** a small academic team, limited computing resources, and approximately **6–8 weeks**. The scope can be adjusted once the deadline, hardware, and API budget are known.

### Proposed project title

**Evaluating Large Language Models: Accuracy, Robustness, and Response Reliability**

### What the application will do

The user will select models and a test dataset, run an evaluation, and see a dashboard containing:

- Accuracy across different tasks.
- Compliance with explicit instructions.
- Performance when questions are reworded or contain small errors.
- Ability to answer from supplied evidence and acknowledge missing information.
- Response time and estimated API cost.
- Individual answers, scoring explanations, and human reviews.

The first version should support **two or three models**, four task categories, automatic scoring, and a small human review workflow.

### Research question

> How do model performance and rankings change when we test different capabilities and vary the wording of the same questions?

### Deliverables

A working application, a documented evaluation dataset, saved experiment results, and a report explaining the findings.

### Implementation sequence

**Prepare tests → connect models → collect answers → score answers → compare results → investigate failures.**

---

## Detailed implementation plan

### 1. Define what the first version will evaluate

The original survey covers too much for one student implementation. We should select a manageable set of capabilities and evaluate them carefully.

| Category | What we will test | Example | Main scoring method |
|---|---|---|---|
| Knowledge | Correctness on questions with verified answers | A multiple-choice science question | Answer accuracy |
| Reasoning | Solving logical or numerical problems | A short problem with a verifiable numerical answer | Answer accuracy |
| Instruction following | Compliance with explicit, checkable requirements | Return valid JSON with specified fields | Rule checks |
| Evidence-based answering | Using a provided passage correctly | Answer a question using only a supplied paragraph | Reference scoring and human review |

**Robustness will be tested across these categories.** We will select questions and create equivalent versions with paraphrasing or minor typos.

For example:

- Original: “A book costs ₹120. What do three books cost?”
- Paraphrase: “How much would you pay for three books priced at ₹120 each?”
- Typo variant: “A book costs ₹120. What do thre books cost?”

The correct answer remains ₹360. Differences in correctness reveal sensitivity to the presentation.

The first release should focus on text responses. Agent workflows, image understanding, multilingual evaluation, and comprehensive safety assessment can become later extensions.

### 2. Define the research contribution

A dashboard demonstrates software development. A controlled experiment gives the project a stronger academic contribution.

We should investigate three questions:

1. **Capability differences:** Does the same model perform best across knowledge, reasoning, instruction following, and evidence-based answering?
2. **Robustness:** How much does accuracy change under meaning-preserving prompt variations?
3. **Evaluation reliability:** Where do automatic scores disagree with human judgments?

These questions connect directly to the original survey and newer work on evaluation generalization. The newer survey examines whether limited tests adequately measure broader capabilities: [Toward Generalizable Evaluation in the LLM Era](https://arxiv.org/abs/2504.18838).

We should describe our contribution as **a reproducible comparative study and an evaluation application**. Any stronger claim of methodological novelty would need supporting literature research.

### 3. Design the user workflow

The application should have five main screens.

| Screen | What the user does | What it displays |
|---|---|---|
| Datasets | Import or select test questions | Categories, sample questions, references, validation errors |
| Experiment setup | Select models and conditions | Question count, generation settings, estimated workload |
| Run progress | Start, cancel, or resume an experiment | Completed responses, failures, elapsed time |
| Results | Compare model performance | Scores, uncertainty, response time, robustness changes |
| Answer review | Inspect and rate individual responses | Prompt, reference, response, automatic score, reviewer rating |

A typical demonstration would be:

1. Select three models.
2. Select a dataset.
3. Enable paraphrase and typo variants.
4. Review the expected number of requests.
5. Run the experiment.
6. Compare results by task.
7. Open examples where a model failed.
8. Export a report.

The result screen must make clear **which dataset, models, settings, and date produced the scores**.

### 4. Use a simple architecture

Use a Python application with a separate experiment runner.

```text
User interface
      │
      ▼
Experiment configuration
      │
      ▼
Experiment runner ───────► Model adapters ───────► Model services
      │                                               │
      ◄──────────────── Responses ────────────────────┘
      │
      ▼
Scoring and human review
      │
      ▼
Saved results and comparison dashboard
```

| Component | Responsibility |
|---|---|
| Dataset manager | Load, validate, version, and organize test cases |
| Model adapters | Send requests to each supported provider |
| Experiment runner | Schedule requests, track progress, and handle failures |
| Scoring engine | Apply the appropriate scoring method to each task |
| Results store | Preserve configurations, answers, scores, and reviews |
| Analysis module | Calculate comparisons and uncertainty |
| Dashboard | Present results and support inspection |
| Report exporter | Produce reusable experiment summaries |

For the first version:

- **Python** for the core application.
- **Streamlit** for the interface.
- **SQLite** for saved experiments.
- **JSONL** for test cases and raw response exports.
- **Pandas and plotting libraries** for analysis and charts.

Streamlit is designed for building interactive data applications in Python, making it a reasonable fit for this project. See the [Streamlit documentation](https://docs.streamlit.io/).

The experiment runner should operate independently of the interface. Refreshing a page should not accidentally restart model requests or lose a running experiment.

### 5. Prepare the dataset before building the dashboard

The dataset determines whether the results are meaningful.

| Dataset portion | Proposed size | Purpose |
|---|---:|---|
| Development questions | 40 | Debug prompts, parsing, and scoring |
| Knowledge test questions | 40 | Measure answer correctness |
| Reasoning test questions | 40 | Measure problem solving |
| Instruction-following test questions | 40 | Check explicit requirements |
| Evidence-based test questions | 40 | Check supported answers and abstention |
| Additional variants | 120 | Two variations of 60 selected test questions |

This gives us **160 base test questions plus 120 variants**, or **280 prompts per model per repetition**. Development questions stay outside reported test results.

These are practical starting numbers, not a guarantee of statistically conclusive comparisons. Forty questions per category can produce considerable uncertainty.

Each test case should store:

```json
{
  "id": "reasoning_001",
  "category": "reasoning",
  "prompt": "A book costs 120 rupees. What do three books cost?",
  "reference_answer": "360",
  "scorer": "numeric_answer",
  "parent_id": null,
  "variant_type": "original",
  "source": "project_authored",
  "dataset_version": "1.0"
}
```

Additional fields can hold answer choices, supporting passages, accepted answer forms, and instruction constraints.

Dataset preparation should include:

- Verify every reference answer.
- Record the source and applicable license.
- Remove duplicates and near duplicates.
- Check that variants preserve the original meaning.
- Keep each original question and its variants in the same split.
- Freeze the test set before examining final results.

If we use a subset or modify a public benchmark, the report must identify it as our subset or adapted evaluation. Its scores should not be presented as directly equivalent to official benchmark results.

### 6. Connect models through a common interface

The evaluation engine should see every model through one interface:

```text
generate(request, configuration) → response
```

Each adapter will translate that request into the provider’s format and return:

- Generated answer.
- Model identifier.
- Timing information.
- Token usage, where available.
- Finish reason, such as completion or truncation.
- Error details when the request fails.

There are two deployment routes:

| Route | Advantage | Constraint |
|---|---|---|
| Hosted model APIs | Minimal local hardware requirements | Usage costs and provider limits |
| Local models | Local control and no per-request API billing | Memory, compute, and runtime requirements |

Ollama provides an API that could support the local-model route. Model selection would still depend on the machine’s available resources. See the [Ollama API documentation](https://docs.ollama.com/api/introduction).

Start with a mock adapter for development, then one real provider, then a second. Select the actual model versions after checking access, hardware, and budget.

For fairness, use common instructions and comparable settings wherever supported, and record any differences. Do not silently ignore unsupported settings.

### 7. Build a dependable experiment runner

Each experiment should save an immutable configuration containing:

- Dataset version and fingerprint.
- Selected question IDs.
- Model identifiers and provider.
- Prompt template and system instruction.
- Supported generation settings.
- Repetition count.
- Scorer versions.
- Experiment timestamp and application version.

The runner should:

1. Validate the experiment.
2. Estimate the workload.
3. Create pending response records.
4. Send requests with controlled concurrency.
5. Save each completed response immediately.
6. Retry temporary failures within a defined limit.
7. Score completed responses.
8. Aggregate results.

It should also support cancellation and resuming unfinished work.

A timeout must be recorded as a request failure. It should not disappear from the report or be silently counted as an incorrect factual answer.

Report both:

- **Answer quality among successfully returned responses.**
- **Overall completion and request-failure rates.**

A low temperature can reduce variation where supported, but it does not guarantee identical outputs. Repeated trials remain useful.

### 8. Implement task-specific scoring

The scoring engine should assign a suitable evaluator to each test case.

| Task | Scoring rule | Important handling |
|---|---|---|
| Multiple choice | Compare extracted choice to reference | Reject ambiguous multiple-choice outputs |
| Numerical reasoning | Compare normalized numerical answer | Handle units and declared tolerances |
| JSON output | Parse JSON and validate its structure | Distinguish syntax from field correctness |
| Explicit constraints | Check each requirement | Define word counting and matching rules |
| Short passage answers | Compare with accepted answers | Review valid alternative wording |
| Unanswerable questions | Check whether the model abstains | Also measure incorrect abstention on answerable questions |

For instruction following, report both:

- Percentage of individual constraints satisfied.
- Percentage of responses satisfying every constraint.

For evidence-based answering, include answerable and unanswerable questions. This lets us detect a model that gets a high abstention score simply by refusing everything.

Avoid calling every mismatch a hallucination. A response can be incomplete, incorrectly formatted, unsupported, or factually wrong; these are different failure types.

### 9. Add human review, then optional LLM judging

Human review should be part of the project because automatic scoring can miss valid answers or reward superficial compliance.

A manageable review procedure is:

- Select approximately 60 responses across models, tasks, and outcomes.
- Hide model names.
- Shuffle presentation order.
- Ask two reviewers to rate them independently.
- Save both original ratings before resolving disagreements.

| Dimension | Suggested rating |
|---|---|
| Correctness | Incorrect / partly correct / correct |
| Evidence support | Unsupported / partly supported / supported |
| Instruction compliance | Fails / partly satisfies / fully satisfies |
| Error category | Wrong answer, unsupported claim, format error, unnecessary refusal, other |

Calculate agreement and explain common disagreements.

An LLM judge can be added after this workflow works. Its inputs should include the question, reference or evidence, response, and rubric. Save its model version and evaluation prompt.

Compare judge ratings with human ratings on the reviewed subset. Treat model-generated scores as measurements from another evaluator, rather than automatic ground truth.

### 10. Analyze robustness and model differences carefully

The dashboard should show separate dimensions rather than immediately compressing everything into a single score.

Useful views include:

- Accuracy by category.
- Instruction compliance by constraint type.
- Original versus perturbed accuracy.
- Correct answers that became incorrect after rewording.
- Answerable-question accuracy versus appropriate abstention.
- Median and high-percentile response time.
- Request-failure rate.
- Estimated cost.
- Human versus automatic scoring disagreements.

For robustness, report:

```text
Accuracy change = original accuracy − variant accuracy
```

Express that change in **percentage points**.

Also report answer consistency, but explain that consistent answers can still be wrong.

Use paired comparisons because models answer the same questions. When estimating uncertainty, keep each base question together with its variants and repeated responses; those observations are related and should not be treated as independent questions.

If a difference is small relative to the uncertainty, the report should say the evidence is inconclusive.

### 11. Control the experiment budget

With the proposed full dataset:

```text
280 prompts × 3 models × 3 repetitions = 2,520 generation requests
```

Judge requests and retries would add to that count.

Before the full experiment:

1. Run 10 questions on two models.
2. Inspect scoring, response lengths, latency, and errors.
3. Estimate the cost of the full run.
4. Run one repetition before committing to additional repetitions.

API cost should be calculated from measured token usage and the applicable provider rates. Store the rate date and label unavailable costs as unknown.

For local models, record hardware and runtime. Local inference still consumes computing resources, even when there is no API bill.

### 12. Build in milestones with clear completion criteria

The schedule below is an estimate for a small team.

| Phase | Estimated duration | Work | Completion criterion |
|---|---:|---|---|
| Scope and protocol | 3–4 days | Fix research questions, task definitions, metrics | Written evaluation protocol |
| Dataset preparation | 1 week | Development set, references, variants, validation | Reviewed and versioned dataset |
| First working pipeline | 1 week | One adapter, runner, persistence, basic scoring | One saved experiment from start to finish |
| Model comparison | 1 week | Additional adapters, retries, repetitions, resume | Two models evaluated under a documented protocol |
| Dashboard and review | 1 week | Charts, answer inspection, human rating, exports | Results are inspectable and exportable |
| Pilot and corrections | 3–4 days | Investigate parsing errors, unreliable questions, cost | Frozen test protocol and working pipeline |
| Final experiments | 1 week | Full runs, human review, statistical analysis | Complete results with uncertainty and failure analysis |
| Report and demonstration | 3–4 days | Findings, limitations, screenshots, documentation | Reproducible project submission |

The **first working milestone** should be much smaller than the final system:

> Load 10 questions, send them to one model, save the responses, calculate accuracy, and display the results.

That establishes the central workflow before investing in interface polish or advanced evaluation.

### 13. Verify the software and the evaluation separately

Both need checking.

Software checks should cover:

- Correct scoring of known correct, incorrect, and malformed answers.
- Handling timeouts and rate limits.
- Resuming without duplicating saved responses.
- Preventing accidental duplicate experiment launches.
- Keeping API credentials out of exports.
- Correct aggregation when some requests fail.

Evaluation checks should cover:

- Correct reference answers.
- Meaning-preserving variants.
- Separation between development and test data.
- Consistency between displayed scores and underlying responses.
- Whether human review exposes systematic scoring errors.

These checks matter because a scoring bug could change the apparent ranking of the models.

For standard benchmark support later, investigate integration with the established **LM Evaluation Harness**, which provides reusable evaluation infrastructure. Compatibility must be checked for the chosen task and model backend. See [LM Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness).

### 14. Define the final submission

The completed project should include:

- A runnable evaluation application.
- A versioned dataset with sources and verified references.
- Reusable experiment configurations.
- Raw responses, automatic scores, and human ratings.
- A dashboard and exported comparison reports.
- Documentation for setup and reproduction.
- A research report covering methods, results, limitations, and future work.

The report should acknowledge that a small test set cannot establish overall model superiority, public questions may have appeared in training, and results depend on model versions and evaluation settings.

## Recommended starting scope

**Two models, four task categories, automatic scoring, paraphrase robustness, and human review.** Build that complete workflow first, then add a third model and LLM judging if time and budget permit.
