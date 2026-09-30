# Flow-credit API research

Checked: 2026-10-01. Scope: a supported public API for generating videos using the user's Google AI Pro/Ultra Flow credits, with no separate Gemini/Vertex billing.

## Finding

No official public Flow-credit API was located in this bounded search of Google Flow Help, Google AI developer documentation, and Google developer/cloud search results. This is not proof that no private, partner, or future API exists. Do not label a browser's internal service endpoint an official public API.

## Primary evidence

- Google documents Flow generation as consuming Flow/AI credits and instructs users to check their balance from their profile in the Flow UI. Prices depend on model and are per generation, not necessarily per request; a request can produce multiple generations. Google says to check current prices in the model settings. [Flow credit documentation](https://support.google.com/flow/answer/16526234?hl=en)
- Google's developer plan documentation explicitly distinguishes direct Gemini API usage from AI Studio subscription benefits: external applications/API keys are billed separately, and Google One AI credits do not overlap with Google Cloud credits. Some subscribers may receive developer Cloud credits, but this still requires a Cloud project and billing. Those are not Flow credits and do not satisfy this project's billing restriction. [Google AI plans, updated 2026-08-18](https://ai.google.dev/gemini-api/docs/google-ai-plans)
- Gemini API billing uses Cloud Billing accounts. Its paid tiers and prepayment mechanisms are a separate route, not a documented way to spend a Flow balance. [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing/)
- Flow's official getting-started instructions direct users to a Chromium browser. They do not document an external generation API. This observation supports the bounded finding above; absence from one help page alone would not prove API nonexistence. [Get started with Flow](https://support.google.com/flow/answer/16353333?hl=en)

## What unofficial results mean

The maintainer of gflow-cli describes it as alpha, reverse-engineered, and unaffiliated with Google. Its README describes headed-browser automation and private Flow services, not an official Flow-credit SDK. It claims generation consumes the user's Flow allowance, but that claim has not been independently tested here. It is evidence that community automation exists, not evidence of Google approval or this project's compatibility. No package was installed and no internal endpoint was called. [Maintainer README](https://github.com/ffroliva/gflow-cli)

Its issue notes also document Flow frontend migration and incomplete coverage. This makes automatic credit/account verification and fail-safe submission independent engineering checks, rather than assumptions. [Maintainer known issues](https://github.com/ffroliva/gflow-cli/blob/develop/KNOWN_ISSUES.md)

## Consequence for nextgen-local

The user's latest authorization permits evaluating browser UI automation. It does not permit private-endpoint reverse engineering, CAPTCHA/login/rate-limit bypass, Gemini/Vertex billing fallback, or TikTok/Shopee account automation.

We can develop the local facts, prompts, approval gates, mock clips, assembly, QC, and export while evaluating the Flow UI path. Real generation must stay blocked until the active user account, required subscription, current balance, selected model, and estimated credit charge are verified from the UI. Unknown submission outcomes must not trigger another paid submission automatically.

Live Flow generation remains unverified. The earlier conversation recorded a signed-out Flow state; this research did not recheck the current login. Do not claim that the current account, available credits, downloads, or completed generation have been tested.
