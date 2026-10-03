# Shopee Product Intake and Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user paste a Shopee product URL, choose a UGC style, correct extracted product details, and automatically inspect a styled preview after GFlow generation.

**Architecture:** Keep FastAPI, SQLite and the current media pipeline. Add a small allowlisted product-page reader with a manual fallback; store the selected style and preview metadata on the project. Generate title/soft-blur preview and thumbnail as derived files while preserving the provider clip as the source.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy/SQLite, Jinja2, existing FFmpeg/Pillow pipeline, pytest.

**Spec:** [../specs/2026-10-02-shopee-video-automation-design.md](../specs/2026-10-02-shopee-video-automation-design.md)

## Global Constraints

- Keep the app local to loopback and retain current CSRF, Host/Origin, CSP and file-confinement protections.
- Fetch only HTTPS Shopee product hosts; validate every redirect and resolved IP, and bound response size and time.
- Treat page metadata as untrusted and reviewable; never invent product facts.
- Preserve the raw provider clip; apply the product title and subtle top blur once to derived preview/final output.
- Use the existing dependencies and UI stack; do not add a client framework or external metadata service.
- Existing projects must continue to load after schema changes; do not lose existing media or workflow history.

## Review Focus

1. A private/loopback destination or redirect must be rejected before fetching (test: `test_product_metadata_rejects_private_ip_and_unsafe_redirect`).
2. Oversized or slow product pages must fail within bounded limits and leave manual entry available (test: `test_product_metadata_bounds_body_and_timeout` plus a route fallback assertion).
3. Untrusted title/description markup must render as escaped text and never become approved facts (test: `test_product_metadata_is_escaped_and_unverified`).
4. Existing SQLite projects must load with a default style and no data loss (test: `test_existing_database_gets_default_style_without_losing_project`).
5. Re-generating preview must not modify the original clip or stack overlays (test: `test_preview_derivative_preserves_source_and_replaces_old_overlay`).

---

### Task 1: Add a safe Shopee metadata reader

**Files:**
- Create: `app/product_pages.py`
- Modify: `app/settings.py` only if a timeout/size bound belongs with existing settings
- Test: `tests/test_product_pages.py`

**Interfaces:**
- Produces: `ProductMetadata(title: str, description: str = "", image_urls: list[str] = [])` and `fetch_product_metadata(url: str) -> ProductMetadata`.
- Restrict accepted hostnames to the Shopee country domains already served by the project (at minimum `shopee.co.th` and `shopee.ph`, including their product subdomains); allow HTTPS only. Revalidate each redirect target and DNS result before connecting. Maximum response body 2 MiB and timeout 5 seconds.

- [ ] **Step 1: Write failing tests** for accepted Thai/Philippine product URLs, non-Shopee/HTTP URLs, credentials, private DNS/IP, unsafe redirect, HTML title extraction, escaping boundary and response/time bounds. Mock DNS and URL opener; tests must not make network requests.
- [ ] **Step 2: Run** `python -m pytest tests/test_product_pages.py -q`; expected: collection or named missing-interface failures.
- [ ] **Step 3: Implement** the allowlist, redirect/IP validation and bounded HTML metadata extraction using the standard library; return plain text only and no page-provided facts as verified.
- [ ] **Step 4: Run** `python -m pytest tests/test_product_pages.py -q`; expected: all tests pass.
- [ ] **Step 5: Commit** only `app/product_pages.py`, any settings change and `tests/test_product_pages.py` as `feat: read Shopee product metadata safely`.

### Task 2: Persist selected style and reviewable product details

**Files:**
- Modify: `app/models.py`, `app/workflow.py`
- Modify: `app/web.py`, `app/templates/index.html` (or the current project-create form template)
- Test: `tests/test_workflow.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: `fetch_product_metadata(url: str) -> ProductMetadata` from Task 1.
- Produces: `Project.style: str`, with exact values `pov_demo`, `clean_showcase`, `cozy_lifestyle`; default `pov_demo`. Add `Workflow.update_product_intake(pid, *, product_name: str, style: str) -> None` and route `POST /projects/preview-product` (or adapt existing create route) to return safe metadata for review.

- [ ] **Step 1: Write failing tests** for valid/invalid style, nonblank manual product name, successful metadata preview, metadata failure with manual fallback, and an existing database gaining a default `style` column while retaining its projects and facts.
- [ ] **Step 2: Run** `python -m pytest tests/test_workflow.py tests/test_web.py -q`; expected: new assertions fail before implementation.
- [ ] **Step 3: Implement** style validation and a minimal backward-compatible SQLite `ALTER TABLE` migration in `Workflow.__init__`; keep network access outside DB transactions and preserve CSRF/Host/Origin checks.
- [ ] **Step 4: Run** `python -m pytest tests/test_workflow.py tests/test_web.py -q`; expected: all targeted tests pass.
- [ ] **Step 5: Commit** only the files listed above as `feat: add Shopee URL and style intake`.

### Task 3: Create an automatic styled preview after generation

**Files:**
- Modify: `app/media.py`, `app/workflow.py`, `app/web.py`, `app/templates/project.html`, `app/static/style.css`
- Test: `tests/test_media.py`, `tests/test_workflow.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: persisted `Project.style`, `Project.product_name`, and current completed `Shot.clip_path`.
- Produces: `Workflow.create_preview(pid) -> Path`, with files confined under the project directory (e.g. `preview.mp4`, `thumbnail.jpg`); add an authorized project file route that only serves those fixed derived filenames.

- [ ] **Step 1: Write failing tests** proving the preview uses the selected style/title, has a thumbnail without a play glyph, does not change the source clip hash, and rerunning preview replaces the derivative rather than overlaying an existing derivative.
- [ ] **Step 2: Run** `python -m pytest tests/test_media.py tests/test_workflow.py tests/test_web.py -q`; expected: new preview assertions fail.
- [ ] **Step 3: Implement** preview generation from the raw completed clip and render it directly in the project page after generation; keep existing final assembly from applying title/blur a second time.
- [ ] **Step 4: Run** targeted tests, then `python -m pytest -q`; expected: all tests pass.
- [ ] **Step 5: Commit** only the files listed above as `feat: show styled UGC preview automatically`.
