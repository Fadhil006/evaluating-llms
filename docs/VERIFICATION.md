# Guided comparison verification — 2026-10-20

## Live-mode follow-up

The user requested real mode rather than the synthetic demonstration. Port 18202
now serves live mode with the existing server-side credentials and a separate
`data/beginner-live.sqlite3` database. No generation was started for verification.
Both real catalogs refreshed successfully (468 OpenRouter entries, 44 Zen
entries at observation); **19 OpenRouter and 8 Zen routes** passed current
eligibility checks. A visible browser selected
`openrouter / google/gemma-4-31b-it:free` and `opencode_zen / big-pickle`, retained
the choices across provider filters, and verified the enabled Start button and
20-request review estimate. The verification script blocked create/start/resume
mutations. Authenticated generation remains untested.

Follow-up checks: frontend typecheck/build passed, **5 browser tests passed**,
and the full backend suite passed (**106 tests**); Ruff passed. The new environment-file regression
checks legacy-key loading without copying secrets. See
[real model selection](screenshots/live-model-selection.png) and
[live review before start](screenshots/live-review.png).

Final checks ran from `/home/fadhil/Projects/llm-comparison-beginner` on branch
`beginner-comparison`, using the existing installed Python environment and frontend
dependencies through ignored local symlinks. The implementation commit is `00fd193`;
the follow-up verification commit contains this report, screenshots, and final
mobile layout/screenshot adjustments.

## Commands and outcomes

| Directory | Command | Outcome |
| --- | --- | --- |
| `backend/` | `.venv/bin/python -m pytest -q` | **105 passed**; three dependency/configuration deprecation warnings |
| `backend/` | `.venv/bin/ruff check app tests alembic scripts` | **Passed** |
| `frontend/` | `npm run typecheck` | **Passed** |
| `frontend/` | `npm run build` | **Passed**, 45 modules; Node module-loader deprecation warning |
| `frontend/` | `npm run test:e2e` | **5 passed** in the final run |
| `frontend/` | `SHOW_BROWSER=1 node scripts/verify-demo.mjs` | **Passed**: visible Chromium, 1440×1000 desktop and 390×844 mobile, 20 synthetic requests, paired answers, hidden names, all four downloads, no captured browser errors or HTTP 5xx |
| repository | `git diff --check` | **Passed** |

The preserved Flask/CLI prototype was not changed or used as proof of current-app
behavior. Its separate test suite was not rerun for this change.

## Coverage and integration fixes

- Backend mocked tests cover strict price validation/expiry, unsupported endpoints,
  canonical/legacy credential precedence (including explicit blank), duplicate
  start without duplicated jobs, durable progress, rate-limit pause, uncertain
  outcomes, scoring, imports, exports, and migrations.
- Added regression for mode-aware estimates: synthetic fixture routes are ready
  only in demo mode; live readiness still requires configured credentials and
  allowed price/route policy. Browser testing found and fixed the earlier estimate
  mismatch that blocked Start in demo mode.
- Browser tests exercise same-provider and cross-provider choices, same model ID
  across different providers, exact-route duplicate prevention, search/filter
  selection retention, expired/missing/unsupported routes, and catalog-refresh
  snapshot changes without silent substitution.
- Validated import is exercised with rejected malformed JSONL followed by a valid
  import selected in the same wizard. Navigation retains settings; invalid caps
  block start; request/retry estimates update; double-click start creates one run.
- Actual fixture workers exercise completion, pause/resume/cancel, durable review
  after reload, saved analyses and export links. Browser fixtures separately test
  rate-limit/unknown-outcome acknowledgement, partial answers, all-failed results,
  and status filters retaining the other model's matching answer.
- Keyboard focus and mobile page width are checked. Visible Chromium screenshots
  were inspected, and mobile navigation wrapping, result controls, and question
  navigation were adjusted. No embedded in-app browser tool was available; this
  was a real headed Chromium/Playwright walkthrough, not a claim of embedded-tool
  verification.

## Screenshots

All screenshots show **synthetic demonstration data**, not measured provider quality.

- [Model selection — desktop](screenshots/model-selection-desktop.png)
- [Model selection — mobile](screenshots/model-selection-mobile.png)
- [Results — desktop](screenshots/results-desktop.png)
- [Results — mobile](screenshots/results-mobile.png)

## Provider evidence versus generation tests

No new real generation requests were sent. Official provider documentation was
read, and the public unauthenticated Zen model catalog returned HTTP 200 with a
`data` array. This verifies public discovery, **not authenticated generation or
model availability**. Endpoint/request/response integration was tested with mocks.
Context7 documentation lookup was attempted but its monthly quota was exhausted;
official provider pages were retrieved directly instead.

Zen's 13 supported free/chat routes were individually rechecked against the
official price and endpoint table on 2026-10-20. Jev's free route remains excluded
because it uses SystemOne, not chat-completions. Dated evidence expires at
**2026-10-21 00:00 UTC** and then fails closed until reviewed again. This is not
a permanent guarantee from the provider. There is no documented Zen free-quota
counter; unknown stays unknown.

The original server at port 18201 was not restarted. Experiment 1 was rechecked:
still paused for rate limit, **0 successful / 1 failed / 19 pending**, one attempt
consumed. Its unknown remote outcome was not retried and its external live
database was not copied, migrated, or modified by this work.

## Remaining limits

- Local, single-user app only; no public deployment or browser key collection.
- No new evidence of live authentication or real provider/model quality. A concrete
  live test needs separate approval of exact routes, counts, retries, cap and pricing.
- The question selector uses the existing up-to-ten category-balanced local sample.
  These authored questions are demonstrations, not a representative benchmark.
- Results load all response pages to keep matching answers together. Very large
  comparisons may need server-side grouped pagination in a later change.
- Name hiding affects the results view, not self-identifying answer text. The
  separate human-review workflow retains randomized assignments. AI judging is
  a documented proposal only; see [the design](AI_JUDGE_DESIGN.md).
- Existing dependency deprecations remain; no unrelated dependency upgrades were
  made solely to silence warnings.
