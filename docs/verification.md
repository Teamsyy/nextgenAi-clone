# Verification Report: nextgen-local MVP

Date: 2026-10-01
Status: Verified Offline Mock MVP; Real Flow Generation Gated / Blocked per Design.

## 1. Scope and Implementation Summary

The MVP specified in [`docs/mvp-design.md`](file:///C:/Users/Teamsy/Documents/ChatGPT/nextgen%20clone/docs/mvp-design.md) has been implemented and verified:
- **FastAPI + Jinja2 + SQLite**: Server-side rendering, loopback binding (`127.0.0.1`), strict CSRF protection, trusted host middleware, input size & image megapixel limits.
- **Evidence-First Claims & Prompts**: Fact verification classification (`verified`, `seller_claim`, `unverified`, `prohibited`), 4-part product identity enforcement (`color`, `shape`, `size`, `accessories`), 7 fixed storyboard roles (`hook`, `product_demo`, `lifestyle`, `detail`, `benefit`, `proof`, `cta`), and automated sensitive claim detection without false positives on trusted system prohibitions.
- **Server-Side Approval Gating**: Stale output invalidation on fact/prompt changes, 1-shot test requirement before batch generation, idempotent prompt approval preserving completed test shots and indeterminate status guards.
- **Atomic Operations**: Project states (`generating`, `assembling`, `exporting`) reserved within SQLite transactions (`BEGIN IMMEDIATE`) to prevent concurrent mutation and race conditions.
- **Media Pipeline**: FFmpeg normalization (720x1280 portrait H.264, 24fps, YUV420p, 48kHz stereo AAC), concatenated reel assembly, optional audio voiceover & subtitle muxing, ffprobe + FFmpeg decode quality check, and ZIP package export (`manifest.json`, `facts.json`, `prompts.txt`, `caption-th.txt`, `narration-th.txt`, `review.json`, `qc-report.json`, `final-reel.mp4`, `clips/`).
- **Billing & Flow Credit Gate**: No Gemini/Vertex API fallback; `GFlowProvider` readiness check blocks live generation until non-bypass browser automation and verified user account/subscription/credit balance evidence are established.

---

## 2. Test Suite Results (pytest)

Command: `python -m pytest`
All 28 tests passing:

```
tests/test_media.py ....                                                 [ 14%]
tests/test_providers.py .....                                            [ 32%]
tests/test_regressions.py .........                                      [ 64%]
tests/test_web.py .                                                      [ 67%]
tests/test_workflow.py .........                                         [100%]
======================= 28 passed in 23.09s =======================
```

### Coverage of Key Regressions
1. **Withdrawn facts invalidation**: Modifying or downgrading a fact wipes shot prompts and invalidates approvals; stale claims cannot survive into reapproval.
2. **Idempotent prompt reapproval**: Reapproving unchanged prompts leaves completed test shots (`complete`) and error guards (`indeterminate`) intact, preserving test-before-batch rules.
3. **Atomic reservation during export**: `export()` sets `status="exporting"` inside a transaction, preventing mutations or concurrent operations.
4. **Trusted prompt validation**: Default generated prompts (including `proof` which contains the prohibition `never fabricate tests, testimonials or certifications`) pass validation cleanly while actual unevidenced user claims remain blocked.
5. **Checklist modification invalidation**: Editing manual review checklists on an exported project clears `status="exported"` to `"qc_passed"` and invalidates the exported zip package.
6. **Cross-platform subtitle line endings**: Uploaded subtitles are normalized to LF (`\n`) in export packages.

---

## 3. CLI Verification

### `python -m app doctor`
```json
{
  "provider": "gflow",
  "installed_version": null,
  "executable_found": false,
  "ready": false,
  "account_verified": false,
  "credits": null,
  "estimated_cost": null,
  "model": null,
  "reason": "Live generation blocked: audited non-bypass browser path and live account, Pro/Ultra subscription, model and credit-cost verification are not implemented. Upstream credit lookup reports limitations for flow.google.com.",
  "documentation": "https://github.com/ffroliva/gflow-cli/blob/develop/KNOWN_ISSUES.md",
  "output_root": "C:\\Users\\Teamsy\\Documents\\ChatGPT\\nextgen clone\\projects",
  "database_url": "sqlite:///C:/Users/Teamsy/Documents/ChatGPT/nextgen clone/projects/nextgen.db",
  "ffmpeg": "...\\ffmpeg.EXE",
  "ffprobe": "...\\ffprobe.EXE",
  "active_provider": {
    "provider": "mock",
    "model": "mock-color-bars",
    "ready": true,
    "credits": null,
    "estimated_cost": 0,
    "reason": "Synthetic test clips. No AI depiction, no external API, no credits spent."
  }
}
```

### `python -m app demo`
```json
{
  "project_id": "0a81828d469e4082a2b83498d511428c",
  "final": "...\\exports\\final-reel.mp4",
  "package": "...\\exports\\project-package.zip",
  "qc": {
    "has_video": true,
    "has_audio": true,
    "width": 720,
    "height": 1280,
    "duration": 56.02,
    "portrait": true,
    "codec": "h264",
    "ffprobe_ok": true,
    "visual_review_required": true,
    "passed": true,
    "decode_ok": true
  }
}
```
