# Shopee Video Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user explicitly approve a ready preview in the app, then guide the connected Android Shopee app through upload and native product attachment while safely reporting the result.

**Architecture:** Add a persisted project-scoped publish operation and a state-aware Android/Shopee screen adapter. Enable the approval action only after product facts, preview, USB preflight and Shopee product attachment checks are ready. Persist every stage, stop on unknown screens, and mark uncertain submission results indeterminate with no automatic retry.

**Tech Stack:** Python, FastAPI, SQLAlchemy/SQLite, Android ADB/uiautomator XML, Jinja2, pytest.

**Spec:** [../specs/2026-10-02-shopee-video-automation-design.md](../specs/2026-10-02-shopee-video-automation-design.md)

## Global Constraints

- Use Shopee's authenticated Android app; do not call an unofficial/private posting API or reverse-engineer private endpoints.
- User completes affiliate enrollment, OTP, KYC and payout setup directly with Shopee; never collect or store these values.
- Only the in-app **“อนุมัติคลิปและโพสต์ Shopee Video”** action authorizes one public post.
- Stop on OTP, CAPTCHA, enrollment, policy prompts, ambiguous product matches or unrecognized screens; never bypass them.
- Persist exactly these operation stages: `device_check`, `transfer`, `open_shopee`, `select_product`, `upload`, `submit`, `published`, `failed`, `indeterminate`.
- Before submit, a definite failure may resume at the failed stage; after submit begins, unknown result is `indeterminate` and cannot auto-retry.
- Bind to loopback, retain CSRF/Host/Origin checks, do not accept arbitrary ADB args/serials/paths/tap coordinates, and never log screen dumps or credentials.
- Automated tests use a fake device adapter and never publish to a real account. A real public post requires a separately initiated user smoke test.

## Review Focus

1. Stale preview or edited product URL must invalidate readiness and approval (test: `test_publish_rejects_stale_preview_or_product_url`).
2. Multiple or ambiguous native product matches must block posting pending user resolution (test: `test_product_match_ambiguity_blocks_approval`).
3. OTP/CAPTCHA/enrollment/unknown screen must stop without guessed taps (test: `test_gate_or_unknown_screen_stops_flow`).
4. Crash or timeout after submit must become indeterminate and never resubmit automatically (test: `test_submit_timeout_is_indeterminate_without_retry` and `test_restart_in_submit_is_indeterminate_no_retry`).
5. Concurrent approvals or duplicate POSTs must create at most one active publish job (test: `test_duplicate_publish_approval_is_idempotently_rejected`).

---

### Task 1: Add persisted publish operation state and safe readiness checks

**Files:**
- Modify: `app/models.py`, `app/workflow.py`
- Test: `tests/test_workflow.py`

**Interfaces:**
- Consumes: project preview hash/path from the intake-preview plan and selected authorized serial from the Android USB plan.
- Produces: `PublishJob` with `id`, `project_id`, `stage`, `product_url`, `preview_sha256`, `caption`, `error_code`, `created_at`, `updated_at`; `Workflow.publish_readiness(pid) -> dict`; `Workflow.start_publish(pid) -> PublishJob` guarded by DB transaction and one active job per project.

- [ ] **Step 1: Write failing tests** for allowed/blocked prerequisites, hash/URL invalidation, single active job and migration of existing databases with no publish table.
- [ ] **Step 2: Run** `python -m pytest tests/test_workflow.py -q`; expected: new state/readiness tests fail.
- [ ] **Step 3: Implement** a minimal SQLite-compatible `publish_jobs` table and transactional readiness/start methods. Readiness requires reviewed product facts/title, current preview, selected authorized USB device, explicit confirmation that affiliate eligibility exists, and a successful exact product preflight.
- [ ] **Step 4: Run** `python -m pytest tests/test_workflow.py -q`; expected: tests pass and existing projects remain readable.
- [ ] **Step 5: Commit** model/workflow and tests as `feat: persist Shopee publish readiness and jobs`.

### Task 2: Implement fixed native Shopee Video screen flow

**Files:**
- Create: `app/shopee_video.py`
- Modify: `app/android.py`
- Test: `tests/test_shopee_video.py`

**Interfaces:**
- Consumes: `AndroidBridge` device selection, preflight, transfer and fixed ADB command runner from the Android plan.
- Produces: `ShopeeVideoPublisher.preflight(serial: str, product_url: str) -> ProductMatchResult`, `publish(serial: str, video_path: Path, product_url: str, caption: str, on_stage: Callable[[str], None]) -> PublishResult`.
- `ProductMatchResult` has `state` in `ready|missing|ambiguous|gate|unknown` plus safe display title; `PublishResult` has `state` in `published|failed|indeterminate` and a non-sensitive error code. Coordinates, package launch target and XML selectors are constants in code, never request inputs.

- [ ] **Step 1: Write failing fake-adapter tests** for exact product match, missing/ambiguous match, OTP/CAPTCHA/enrollment/policy gates, unknown screen, happy path, pre-submit failure and submit uncertainty. Assert unknown states issue no taps and post-submit errors never call submit again.
- [ ] **Step 2: Run** `python -m pytest tests/test_shopee_video.py -q`; expected: missing-interface failures.
- [ ] **Step 3: Implement** XML-based state recognition for the supported Shopee screens, fixed package launch and known upload/Add Product interactions; stop with a safe actionable state when recognition fails.
- [ ] **Step 4: Run** `python -m pytest tests/test_shopee_video.py -q`; expected: all mock flow tests pass.
- [ ] **Step 5: Commit** publisher and tests as `feat: automate Shopee Video through Android UI`.

### Task 3: Connect approval, background execution and recovery UI

**Files:**
- Modify: `app/web.py`, `app/workflow.py`, `app/templates/project.html`, `app/static/style.css`
- Test: `tests/test_web.py`, `tests/test_workflow.py`

**Interfaces:**
- Consumes: `Workflow.publish_readiness(pid) -> dict`, `Workflow.start_publish(pid) -> PublishJob`, and `ShopeeVideoPublisher` from Tasks 1–2.
- Produces: CSRF-protected `POST /projects/{pid}/publish/approve` and read-only `GET /projects/{pid}/publish/status`; JSON/status output contains only stage, safe error code, product display title and timestamps.

- [ ] **Step 1: Write failing route tests** for CSRF enforcement, blocked readiness, one approval producing one background job, status polling, stale approval rejection, duplicate concurrent request rejection and safe output without XML/device secrets. Add recovery tests proving pre-submit stages may resume after process restart while a persisted `submit` stage becomes `indeterminate` and is never submitted again.
- [ ] **Step 2: Run** `python -m pytest tests/test_web.py tests/test_workflow.py -q`; expected: the new publish route assertions fail.
- [ ] **Step 3: Implement** approval handler and background worker. Persist each stage callback; on startup resume only safe pre-submit stages, and convert any interrupted `submit` stage to `indeterminate`. On pre-submit definite failure mark `failed`; once submit starts, persist `indeterminate` on unconfirmed outcome and suppress retries. Add a clear review/approve button and stage/progress/error recovery copy in the project UI.
- [ ] **Step 4: Run** `python -m pytest -q`; expected: all project tests pass. Do not connect a device or publish during automated verification.
- [ ] **Step 5: Commit** only the listed files as `feat: approve and track Shopee Video publishing`.

### Task 4: Document one-time user setup and real-device smoke procedure

**Files:**
- Modify: `README.md`, `docs/verification.md`
- Test: existing tests only

- [ ] **Step 1: Write** Thai-first instructions for Affiliate enrollment in Shopee, USB debugging/RSA trust, device preflight, one approval per post and manual reconciliation after an indeterminate result; state explicitly that OTP/KYC/payout are entered only in Shopee.
- [ ] **Step 2: Review** the docs against the spec's setup and failure constraints; remove any promise of compatibility with arbitrary Shopee versions or guaranteed publishing.
- [ ] **Step 3: Run** `python -m pytest -q`; expected: all tests pass. Keep real-device smoke as a separate manual step requiring the user to initiate a single public post.
- [ ] **Step 4: Commit** only docs as `docs: explain Android Shopee Video setup and recovery`.
