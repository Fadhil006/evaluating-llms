# AI Project: Survey on Evaluating LLMs

## Overview

This project studies how to measure the capabilities, reliability, and limitations of large language models (LLMs). Its central question is: **How do we know whether an LLM is good at a task, and whether its answers can be trusted?**

The project’s main reference is the 2024 paper [*A Survey on Evaluation of Large Language Models*](sources/ai_project.md). The available files contain the survey and supporting figures; they do not yet include an experimental implementation or model-comparison results.

## Why LLM evaluation is difficult

An LLM can perform many different tasks, and a convincing answer is not necessarily a correct answer. For example, a model might write a polished summary while adding a fact that was not in the source, solve a math problem but fail when its wording changes, perform well in English but poorly in another language, or sound confident when it should acknowledge uncertainty.

Evaluation therefore needs to cover multiple dimensions. A single overall score can hide weaknesses that matter in a specific application. The survey organizes the problem around three questions: **what to evaluate, where to evaluate, and how to evaluate**.

## 1. What to evaluate: abilities and behavior

The paper covers a broad range of tasks and risks:

| Area | What evaluation examines | Example |
|---|---|---|
| Language understanding | Meaning, context, and relationships | Decide whether two statements contradict each other |
| Text generation | Relevance, coherence, and faithfulness | Summarize an article without inventing details |
| Reasoning | Logical, mathematical, and commonsense problem solving | Solve a problem after its wording or assumptions change |
| Factuality and trustworthiness | Accuracy and appropriate handling of uncertainty | Answer a question when evidence is insufficient |
| Robustness | Performance under difficult or changed inputs | Repeat a task with paraphrases, typos, or distracting text |
| Ethics, bias, and safety | Harmful output and unfair differences | Compare responses across otherwise equivalent scenarios |
| Specialized knowledge | Performance in a particular field | Interpret a scientific passage or identify a contract clause |
| Agent capabilities | Tool use and multi-step actions | Choose a tool, use its result, and complete a task |

The survey also discusses social science, natural science and engineering, medicine, education, and other applications. A useful distinction is between **knowing information** and **using it successfully**: answering a question about a tool does not show that a model can operate that tool correctly.

## 2. Where to evaluate: datasets and benchmarks

A **dataset** supplies test examples. A **benchmark** defines a standardized evaluation, typically combining tasks, test data, scoring rules, and a testing procedure.

The original survey compiles 46 benchmarks and groups them into general language tasks, specialized tasks, and multimodal tasks involving inputs such as images and text. Examples include:

| Benchmark | Main purpose in the survey |
|---|---|
| MMLU | Test knowledge across multiple subjects |
| BIG-bench | Test a broad collection of challenging capabilities |
| HELM | Evaluate models across multiple scenarios and metrics |
| MATH | Assess mathematical problem solving |
| APPS | Assess code generation |
| MultiMedQA | Assess medical question answering |
| PromptBench | Examine resilience to adversarial prompts |
| MT-Bench | Assess multi-turn conversation |
| Chatbot Arena | Compare anonymous model responses through human preferences |
| API-Bank | Evaluate tool use |
| MMBench | Evaluate vision-language capabilities |

These examples come from the paper and are not a complete list of current evaluation options. The benchmark needs to match the intended use: performance on subject-knowledge questions gives limited evidence about how well a model will summarize documents or complete a workflow.

## 3. How to evaluate: automatic and human assessment

### Automatic evaluation

Automatic evaluation computes scores without manually judging every response. It makes large comparisons practical, but the chosen metric affects what “good performance” means.

| Metric or approach | What it measures | Important limitation |
|---|---|---|
| Accuracy | Proportion of answers that are correct | Requires a clear definition of correctness |
| Exact match | Whether an answer matches the reference | Can reject a correct answer expressed differently |
| F1 | Balance between precision and recall, with task-specific definitions | Does not capture every aspect of response quality |
| ROUGE | Text overlap with a reference answer | Overlap alone does not establish factual correctness |
| Calibration | How well confidence corresponds to actual correctness | Requires a meaningful way to measure confidence |
| Performance drop | How much results worsen under changed inputs | Depends on which changes are tested |
| LLM-based judging | Another model scores or compares responses | The evaluator also needs reliability checks |

For instance, a summary can share many words with a reference while misrepresenting its main conclusion. Text overlap can be a useful signal, but it is incomplete.

### Human evaluation

Human evaluation asks people to judge responses using explicit criteria. The survey highlights six:

- **Accuracy:** Is the information correct?
- **Relevance:** Does it address the request?
- **Fluency:** Is it clear and readable?
- **Transparency:** Does it communicate its basis and limitations clearly?
- **Safety:** Does it avoid harmful output?
- **Human alignment:** Does it fit appropriate human values and expectations?

The number of evaluators, their expertise, and the scoring rubric matter. Human judgments can vary, so dependable assessment needs clear criteria and a way to handle disagreement. Automatic tests offer scale; human review helps assess qualities that are difficult to capture in a simple score.

## 4. What the original survey found

The studies reviewed in the paper reported strengths in fluent text generation, several language-understanding tasks, translation, question answering, and some forms of reasoning.

They also reported weaknesses in:

- Abstract reasoning and complex contexts.
- Low-resource languages and certain writing systems.
- Hallucinations and factual reliability.
- Bias and toxic output.
- Handling recent or changing information.
- Sensitivity to prompt wording and adversarial inputs.

These are historical findings about models and datasets reviewed before the paper’s 2024 publication. They should not be treated as measured results for current models. The broader conclusion is that no single benchmark or evaluation procedure proves a model is best for every purpose.

## 5. Main research challenges

The survey asks whether evaluation itself deserves our trust. It identifies several open problems:

- **Test contamination:** If a model encountered test questions during training, its score may exaggerate its ability to solve unfamiliar problems.
- **Static tests:** A fixed benchmark can become less informative as models improve.
- **Robustness:** Small input changes can expose failures that ordinary tests miss.
- **Real-world behavior:** Isolated questions do not fully capture performance in open environments or long interactions.
- **Evaluator reliability:** Human assessors and automated judges can both make mistakes.
- **Broad coverage:** Evaluation needs to support different languages, tasks, modalities, and safety requirements.
- **Actionable results:** Scores should help explain failures and guide improvements.

Evaluation is most useful when it explains **where and why a model fails**, rather than merely producing a ranking.

## 6. How newer papers extend the project

The following surveys add perspectives beyond the original paper:

| Paper | Main contribution |
|---|---|
| [*Toward Generalizable Evaluation in the LLM Era* (April 2025)](https://arxiv.org/abs/2504.18838) | Examines capability-based testing, automated test creation, and LLM judges. Its central concern is whether limited test sets can adequately assess broad and growing abilities. |
| [*Evaluation and Benchmarking of LLM Agents* (July 2025)](https://arxiv.org/abs/2507.21504) | Organizes agent evaluation around objectives and procedures, with attention to long interactions, reliability, access permissions, and deployment needs. |
| [*A Survey on Large Language Model Benchmarks* (August 2025)](https://arxiv.org/abs/2508.15361) | Reviews 283 benchmarks across general abilities, specialized domains, and targeted concerns. Discusses contamination, cultural and linguistic bias, and gaps in testing processes and changing environments. |

Together, these papers shift attention toward whether benchmark performance transfers to real use.

## 7. Possible project outputs

A strong literature-survey report could include:

1. Why LLM evaluation is difficult.
2. A classification of capabilities and risks.
3. A comparison of benchmarks, metrics, and evaluation methods.
4. An analysis of limitations such as contamination and judge bias.
5. A comparison between the original survey and newer research.
6. Research gaps and recommendations for choosing an evaluation approach.

An optional experimental extension could investigate:

> **How much does an LLM’s answer accuracy change when the same questions are paraphrased?**

You could prepare questions with verified answers, create equivalent paraphrases, run selected models under documented conditions, and compare accuracy and consistency. Human review could then classify the failures. This would turn one theme from the survey—robustness—into a focused investigation. The current project files do not show that this experiment has been conducted.
