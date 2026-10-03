# Verification Report: nextgen-local MVP

Date: 2026-10-03
Status: Offline tests pass; one live gflow clip was generated in Flow and recovered into the app. Visual approval remains pending.

## 1. Scope and Implementation Summary

The original seven-shot scope in [`docs/mvp-design.md`](mvp-design.md) has since been narrowed in the working implementation to one UGC shot. The current branch state is:
- **FastAPI + Jinja2 + SQLite**: Server-side rendering, loopback binding (`127.0.0.1`), strict CSRF protection, trusted host middleware, input size & image megapixel limits.
- **Evidence-First Claims & Prompts**: Fact verification classification (`verified`, `seller_claim`, `unverified`, `prohibited`), 4-part product identity enforcement, one UGC prompt, and automated sensitive claim detection.
- **Server-Side Approval Gating**: Stale output invalidation on fact/prompt changes, explicit approval of the current clip before assembly, and indeterminate submission guards.
- **Atomic Operations**: Project states (`generating`, `assembling`, `exporting`) reserved within SQLite transactions (`BEGIN IMMEDIATE`) to prevent concurrent mutation and race conditions.
- **Media Pipeline**: FFmpeg normalization (720x1280 portrait H.264, 24fps, YUV420p, 48kHz stereo AAC), concatenated reel assembly, optional audio voiceover & subtitle muxing, ffprobe + FFmpeg decode quality check, and ZIP package export (`manifest.json`, `facts.json`, `prompts.txt`, `caption-th.txt`, `narration-th.txt`, `review.json`, `qc-report.json`, `final-reel.mp4`, `clips/`).
- **Billing & Flow**: No Gemini/Vertex API fallback. The live NextGen request generated one 8-second 720p clip in Flow and used 10 credits. gflow v0.80 rejected an explicit duration before submit; omitting it reached generation, but its result-record lookup failed. The MP4 was recovered from Flow, copied into the app project, and muted to match the approved prompt. gflow-cli was then updated to v0.82.1; no additional billable run was made.

---

## 2. Test Suite Results (pytest)

Command: `python -m pytest -q`
Result: **55 passed**. The run reports one upstream Starlette deprecation warning about its httpx test client.

```
..............................................                           [100%]
55 passed, 1 warning in 11.19s
```

The smoke demo also completed in a temporary directory: QC passed for a portrait MP4 of 8.02 seconds, and the ZIP package was created. No files were written to the user's project directory by that run.

The studio now uses Thai labels, a four-step progress trail, next-action guidance, inline project errors, validation recovery, safe status polling without a page refresh, and dashboard search/status filters. Existing multi-shot projects remain readable and downloadable; their editing actions are blocked because the active workflow produces one UGC clip.

Keyboard and screen-reader review, real-browser viewport screenshots, contrast measurement, web-vitals measurements, and task testing with target users remain unverified. Performance targets in the UI plan are budgets, not measured results.

### Coverage of Key Regressions
1. **Withdrawn facts invalidation**: Modifying or downgrading a fact wipes the prompt and invalidates dependent approvals.
2. **Single UGC shot**: The workflow, CLI demo, manifest, assembly, QC, and export agree on one current clip.
3. **Approved media inputs**: The normal assembly path retains voiceover and subtitles.
4. **Legacy project safety**: A seven-shot project is visibly marked read-only; rejected edits leave its shots intact.
5. **Status and form recovery**: Safe job fields and in-progress job stages are returned from the status route; validation and CSRF errors retain safe entered values, rotate the CSRF token, and never replay the submitted action. Successful form actions return to the relevant project section or edited fact.
6. **Security checks**: CSRF, Host/Origin rejection, upload validation, XSS escaping, and absence of social-publishing actions remain covered.

---

## 3. Live Flow Verification

Project: `JAMAY FS930 · POV UGC` (`8b0d88e5c80e4690ae6310bdd90ac256`). The app now shows the recovered MP4 in its clip preview and download link. The saved app copy is 720×1280, H.264, 8 seconds, and has no audio stream. Flow charged 10 credits for the generated source clip. The generated fan's blade design and display details may differ from the listing; the clip remains in **รอตรวจคลิป** and has not been approved for assembly or publishing.

`gflow-cli` was upgraded from 0.80.0 to 0.82.1 after the test to address the lost Flow workflow/result record. That version was not used for another live generation, to avoid spending credits twice.
