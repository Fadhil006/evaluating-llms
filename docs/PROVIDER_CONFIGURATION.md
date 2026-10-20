# Provider configuration

The backend supports OpenRouter and OpenCode Console (formerly called Zen). Live
generation is disabled unless a provider credential is configured. A configured
key is not proof that it authenticates successfully; provider checks and catalog
refreshes report the observed result without exposing credential values.

## OpenCode Console

Set `OPENCODE_ZEN_API_KEY`. The legacy `OPENCODE_API_KEY` is also accepted;
when both are set, `OPENCODE_ZEN_API_KEY` takes precedence even if it is blank.
This precedence applies within the same settings source; exported environment
values take precedence over values in the ignored `.env` file.
An explicitly blank canonical value disables the Zen credential rather than
falling back to the legacy value. If the canonical variable is absent, the
legacy value is used; if both variables are blank, no credential is configured.
The selected value is sent as a Bearer credential and is never returned by the
API. Passing `opencode_zen_api_key=SecretStr(...)` directly to `Settings` is
also supported.

Current official documentation:

- [Console models, endpoints, and pricing](https://opencode.ai/v2/docs/console/models/)
- [OpenCode Console API](https://opencode.ai/v2/docs/console/api/)
- [OpenRouter models endpoint](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
- [OpenRouter chat-completions endpoint](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion.md)

The documented catalog endpoint is `GET https://opencode.ai/inference/v1/models`.
Chat generation uses the documented OpenAI-compatible endpoint
`https://opencode.ai/inference/openai/v1/chat/completions`. The adapter accepts
only model IDs present in its chat endpoint map; unrecognized model routes fail
closed. It does not infer eligibility from model names.

The official model page calls free models limited-time and publishes no specific
expiry date. Its free-price table and endpoint table were rechecked on 2026-10-20.
The endpoint and price tables were both fetched from the official page on
2026-10-20 (HTTP 200, uncached official Markdown). All 13 allowlisted IDs still
had explicit Free input, output and cached-read prices, with cached-write “—”.
Thirteen of the fourteen listed free models use the OpenAI-compatible
chat endpoint; `jev-1.13-free` uses `/inference/systemone/v1/systemone` and is
excluded from chat eligibility. The public catalog was also observed returning
HTTP 200 with `application/json` and a top-level `data` list (model metadata,
including `id`, `object`, `created`, and `owned_by`). This validates public
catalog discovery only; authenticated generation has not been tested. The exact
free/chat intersection evidence expires on 2026-10-21 at 00:00 UTC pending fresh
review. This is a local evidence-expiry policy, not a provider guarantee. A
free model without current evidence is not dispatchable. OpenCode does not
document a free-request quota counter; its quota remains unknown rather than
being represented as zero or unlimited.

## OpenRouter

Set `OPENROUTER_API_KEY`. Catalog and completion requests use
`https://openrouter.ai/api/v1`; `/models` and `/chat/completions` are documented
by [OpenRouter's API reference](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion.md).
Free-only enforcement requires current explicit zero-price evidence and sends a
zero-price routing constraint with fallback disabled.

## Readiness and privacy

`/api/providers` reports `readiness` as `missing_credentials`,
`catalog_unavailable`, or `catalog_ready`. `credential_configured` means only
that a nonempty key is present; authentication is established only by a
successful authenticated provider request. `/api/models` reports model-level
`readiness`: `ready`, `missing_credentials`, `expired_prices`,
`unknown_or_paid_prices`, `unsupported`, or `temporarily_unavailable` (other
eligibility reasons may also appear). No provider secret is included in these
responses or sanitized upstream errors.
