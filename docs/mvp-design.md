# nextgen-local: Flow-credit MVP design

Status: proposed design; implementation and real Flow generation not yet verified.
Date: 2026-10-01

## Scope and current requirements

A local FastAPI + Jinja2 + SQLite app and Python CLI turn manually sourced product facts into seven reviewed video prompts, clips, a portrait reel, QC and a manual-posting export package. Use SQLAlchemy, Pydantic settings, httpx and pytest. No Docker, Redis, Celery or public hosting.

User amendments supersede the original official-Veo-API integration request: real videos must use the user's own Flow credits; Gemini/Vertex billing and seller/shared keys are excluded. The user authorized evaluating Flow browser UI automation. Private endpoint reverse engineering, CAPTCHA bypass, quota bypass and social-platform account/posting automation remain excluded.

## Implementation order

1. Implement and test the complete offline mock workflow first. Fixture videos are explicitly mock and spend no credits.
2. Evaluate Flow through visible browser controls in the user's authenticated session. No credentials or session exports are accepted by the app. The previous inspection stopped at Signed out.
3. Only implement real generation after the actual UI supplies reliable account, subscription, credit, model, cost, result and download evidence. Unsupported or ambiguous states block real submission. Mock success is not evidence of working Flow integration.

## Modules

- app/settings.py: environment settings, loopback binding, output paths; no paid API fallback.
- app/models.py: Project, ProductFact, Shot, GenerationJob and QCReport, retaining requested fields and timestamps.
- app/workflow.py: shared CLI/UI operations, approvals and stale-output invalidation.
- app/prompts.py: seven templates using approved facts, Thai narration/subtitle draft text; no text API charges.
- app/providers.py: requested provider protocol and mock implementation; no pretend operational Flow adapter.
- app/media.py: subprocess FFmpeg assembly, ffprobe QC, ZIP export and manifest validation.
- app/web.py and templates: dashboard, review, generation status, QC and export.
- app/__main__.py: requested commands plus explicit approval commands.
- tests/: workflow, claims, approvals, retry/timeout, media and security checks.

## Workflow and safety

Preserve source_url exactly. User-entered listing data is unverified or seller_claim until reviewed with evidence; approval alone must not magically verify a claim. Detect unsupported sensitive claims and visibly flag them. Prompt generation uses only approved allowable facts; missing product identity details block prompt approval rather than inventing color, size, shape or accessories.

Seven numbered roles and filenames follow the original request. Prompts specify portrait 9:16, target 8 seconds, realistic direction, camera motion, exact approved identity and continuity, and prohibitions on fake text/logos, deformation, extra accessories, brand changes and unsupported claims. Cleaning/handling uses a reusable template only where appropriate evidence allows it; do not imply waterproofness.

Server-side approvals apply to both CLI and UI. Facts or prompt changes invalidate dependent approvals. Generate exactly one test clip first. Batch requires approval of that specific current test clip and current prompt set. Each subsequent generation rechecks the observed account, selected model, available credit evidence and estimate. Never substitute a model or billing route silently.

One local worker processes one job at a time, with durable SQLite job records. Persist submission intent before clicking Generate. Record returned identifiers only if the UI exposes them; do not invent an API operation ID. If outcome is ambiguous after submission or restart, mark needs_review and do not resubmit. Read-only status polling may back off until timeout. Authentication, permission, policy and invalid-input failures are not retried automatically.

Reference images are stored per project. Capability information must distinguish confirmed, unsupported and unknown for the selected Flow model. Warn when identity guidance is unavailable; never guarantee visual identity.

## Media and exports

Normalize to 720x1280 H.264 with a consistent frame rate and pixel format. Preserve/normalize audio when present and handle silent clips consistently for concatenation. Optional local voiceover and subtitles; validate uploads and paths, invoke FFmpeg without shell interpolation. Export projects/{id}/exports/final-reel.mp4, qc-report.json, manifest, approved facts, prompts and caption/subtitle drafts.

QC verifies existence, nonempty file, readable video codec, positive duration, portrait dimensions, ffprobe success and audio if voiceover requested. Check actual decoding separately when practical; probing alone is not visual review. Require manual checks for identity, logo spelling, extra parts, hands/faces, fake text, unsupported claims, continuity and CTA.

## Security and verification

Bind to 127.0.0.1. Restrict Host/Origin, protect mutation requests, constrain file paths, validate media types/size, redact credentials and exclude runtime data/secrets from git. No password, OTP, cookie or session-upload fields. Do not send product data externally in mock mode.

Verify CLI and UI project creation, fact classification and unsupported claims, seven prompts, approval invalidation, test-before-batch enforcement, mock operation polling/backoff/timeout, no duplicate submissions, manifest validation, FFmpeg construction, ffprobe parsing, secret redaction and absence of social automation. Run a real local mock-to-MP4 integration check.

## Environment and reuse

Requested /home/teamsy/flow-content-pipeline is absent in WSL Ubuntu; the four source files could not be inspected. Do not claim reuse. Python 3.14.4 was found; WSL FFmpeg, ffprobe and pip were absent at initial inspection. Windows has FFmpeg. Resolve local dependencies before implementation checks and report exact commands/results.

## Acceptance boundary

Offline MVP acceptance and live Flow integration acceptance are separate. A disabled Flow button or mock provider does not satisfy the real-generation requirement. Live acceptance requires observed successful submission/download with the user's authorized test and verified credit budget; none has occurred yet.

## Selected integration: gflow-cli (2026-10-01)

The user explicitly selected gflow-cli as the integration to evaluate and reuse. It is a candidate backend for the local UI, not a verified live provider. Do not replace it with Gemini or Vertex billing.

Review of the upstream architecture revealed two concrete compatibility issues:

1. Its documented browser launch paths suppress navigator.webdriver detection and include a retry strategy following browser rejection. The user's no-platform-restriction-bypass requirement remains in force. Do not run authentication/generation paths with these behaviors; assess whether an ordinary browser path can be used without suppression or rejection workarounds.
2. The current known-issues page says credit-balance lookup is not implemented for accounts migrated to flow.google.com. Real generation must remain blocked when account/subscription/balance/model/cost cannot be verified. Never bypass this gate just because gflow generation may work.

The current production generation transport is described as UI automation, while other operations and experimental transports use internal services/session tokens. User selection of the package does not mean every subcommand has been approved. No package was installed or executed during this documentation review.

Sources:
- https://github.com/ffroliva/gflow-cli/blob/develop/docs/ARCHITECTURE.md (Headed-browser dependency)
- https://github.com/ffroliva/gflow-cli/blob/develop/KNOWN_ISSUES.md (No in-CLI quota visibility)
