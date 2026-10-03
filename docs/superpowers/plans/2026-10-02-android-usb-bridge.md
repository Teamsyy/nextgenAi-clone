# Android USB Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect one authorized Android phone over USB and safely transfer the reviewed MP4 to it for Shopee Video upload.

**Architecture:** Wrap installed Android Platform Tools behind fixed subprocess calls and a small adapter used by the later publish workflow. Persist only the selected USB serial and display safe device state in the local UI; tests use a fake command runner and never require a phone.

**Tech Stack:** Python standard library (`subprocess`, `shutil`, `xml.etree`), FastAPI, SQLAlchemy/SQLite, Jinja2, pytest, Android SDK Platform Tools.

**Spec:** [../specs/2026-10-02-shopee-video-automation-design.md](../specs/2026-10-02-shopee-video-automation-design.md)

## Global Constraints

- Require USB debugging and the user's Android RSA trust confirmation; do not enable or use ADB over Wi-Fi.
- Select exactly one authorized USB serial; reject missing, multiple-unselected, unauthorized, offline and locked devices.
- Call only fixed ADB operations with argument arrays, bounded output and timeouts; never accept commands, package names, remote paths or coordinates from form input.
- Keep screen dumps and credentials out of persistent storage and logs; never expose ADB as a network endpoint.
- Bind the app to loopback and retain CSRF, Host/Origin, CSP and project file-confinement checks.
- Use a fake runner in automated tests; no tests may post to a real Shopee account.

## Review Focus

1. `adb` missing or timing out must produce actionable setup guidance without crashing (test: `test_adb_missing_or_timeout_returns_setup_state`).
2. Unauthorized/offline/multiple devices must not be silently selected (test: `test_device_scan_requires_one_authorized_usb_serial`).
3. Malicious serial or source filename must not alter ADB arguments or transfer destination (test: `test_adb_arguments_are_fixed_and_paths_are_confined`).
4. A disconnected device during copy must report failure and preserve the local MP4 (test: `test_transfer_failure_keeps_local_video`).
5. Malformed ADB output must not select a device or leak raw output (test: `test_malformed_adb_output_fails_closed`).

---

### Task 1: Add fixed-command ADB device discovery

**Files:**
- Create: `app/android.py`
- Modify: `app/settings.py` only if needed to locate an explicit configured `adb` executable
- Test: `tests/test_android.py`

**Interfaces:**
- Produces: `AndroidDevice(serial: str, state: str, model: str = "")`, `AndroidBridge(adb_path: str | None = None, runner=...)`, `list_devices() -> list[AndroidDevice]`, `preflight(serial: str) -> dict`.
- `list_devices()` may invoke only `adb devices -l`; preflight may invoke fixed `get-state`, screen-lock check and USB transport verification using the selected serial. Subprocess timeout: 10 seconds; output limit: 64 KiB.

- [ ] **Step 1: Write failing tests** for parser states `device`, `unauthorized`, `offline`, no devices, multiple devices and malformed output; assert only an explicitly selected, authorized USB serial passes preflight, and TCP/IP serials are rejected.
- [ ] **Step 2: Run** `python -m pytest tests/test_android.py -q`; expected: missing-interface failures.
- [ ] **Step 3: Implement** the minimal fixed-command wrapper using `subprocess.run([...], shell=False, timeout=10, capture_output=True)` and redact/truncate errors.
- [ ] **Step 4: Run** `python -m pytest tests/test_android.py -q`; expected: all discovery and preflight tests pass.
- [ ] **Step 5: Commit** `app/android.py`, its settings change and `tests/test_android.py` as `feat: detect authorized Android USB devices`.

### Task 2: Transfer a project video safely and add local device controls

**Files:**
- Modify: `app/android.py`, `app/models.py`, `app/workflow.py`, `app/web.py`
- Modify: `app/templates/project.html`, `app/static/style.css`
- Test: `tests/test_android.py`, `tests/test_web.py`, `tests/test_workflow.py`

**Interfaces:**
- Consumes: `AndroidBridge.preflight(serial: str) -> dict` from Task 1 and current project preview path from the product-preview plan.
- Produces: `Project.android_serial: str` (default empty), `AndroidBridge.transfer_video(serial: str, local_path: Path) -> str` returning the fixed remote path under `/sdcard/Movies/NextGen/`, and `Workflow.select_android_device(pid, serial) -> None` validating that serial against a fresh scan. Add a backward-compatible SQLite column migration; never store arbitrary remote paths.

- [ ] **Step 1: Write failing tests** for transfer success, timeout/disconnect, basename/path traversal rejection, ADB argument allowlist and project-scoped serial selection; assert local source remains present after every result.
- [ ] **Step 2: Run** `python -m pytest tests/test_android.py tests/test_web.py tests/test_workflow.py -q`; expected: transfer and selection assertions fail.
- [ ] **Step 3: Implement** transfer with fixed `push` destination, source confinement to the project's approved MP4, safe generated basename, and a 120-second timeout; add CSRF-protected device scan/select routes and setup copy for USB debugging/RSA prompt.
- [ ] **Step 4: Run** targeted tests, then `python -m pytest -q`; expected: all pass without invoking real ADB.
- [ ] **Step 5: Commit** only the listed files as `feat: transfer reviewed videos over Android USB`.
