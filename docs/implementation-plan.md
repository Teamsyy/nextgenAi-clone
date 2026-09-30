# nextgen-local Implementation Plan
> Execute inline with executing-plans and test-driven-development.
Goal: deliver a runnable local mock MVP and an honest gflow readiness boundary.
Architecture: one shared Workflow for CLI and FastAPI; SQLite persists approvals/jobs; FFmpeg supplies mock media and assembly.
Tech Stack: Python, FastAPI, SQLAlchemy, Pydantic settings, Jinja2, pytest.
Spec: mvp-design.md

Global constraints: 127.0.0.1 only; no API billing fallback; no credentials in UI; no social-platform automation. Real gflow generation blocked until browser behavior and live account/credit verification meet requirements.
Ruling: user explicitly asked to start implementation; execute in this session without another planning approval. New project is isolated at requested path, not the existing Windows repository. Use Windows Python/FFmpeg with WSL-hosted source since existing WSL tools are unavailable.
Ruling: source pipeline absent, implement media module independently and disclose no reuse.

Review focus: stale approvals; concurrent generation; unknown submission outcome; unsafe uploads/paths; audio consistency.

- [ ] Task 1: tests/test_workflow.py and test_providers.py first. Run red, implement settings.py/models.py/prompts.py/providers.py/workflow.py. Verify immutable approval dependencies, source preservation, timeout and transient-only read retries.
- [ ] Task 2: tests/test_media.py first. Implement media.py normalization, ordered concatenation, optional voiceover/subtitles, QC and manifest package. Verify real mock MP4 roundtrip and audio rules.
- [ ] Task 3: tests/test_web.py first. Implement web.py, templates/index.html, templates/project.html, static/style.css and __main__.py. Verify UI creation, CSRF/Host protection, errors and CLI sequence.
- [ ] Task 4: README, .env.example, offline gflow doctor assessment; run complete pytest, CLI demo and browser smoke. Record exact results and limits in docs/verification.md.

Status: implementation starting.

