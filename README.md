# nextgen-local

A local product-fact and single-shot UGC video studio. FastAPI + Jinja2, SQLite/SQLAlchemy, Pydantic settings and FFmpeg. No automatic publishing.

**Implemented:** editable fact review, prompt review, one synthetic mock UGC clip, explicit clip approval, portrait assembly, local voiceover, soft subtitles, technical QC and ZIP export, UI and CLI.

**Not yet implemented:** live Flow generation through gflow-cli. The gflow backend is an explicit fail-closed readiness boundary, NOT a working video integration. Installing gflow does not enable spending. Do not present mock output as AI product footage.

## Architecture

The UI and CLI use the same Workflow service. SQLite records projects, facts, shots, generation jobs, errors and QC. Generation persists submission intent and operation IDs, polls asynchronously with bounded backoff, and retries only transient status reads. Submission itself is never automatically retried. Unknown submission outcomes block another attempt. One project cannot be modified while it is generating or assembling.

Mock clips are synthetic test patterns, eight seconds each. They prove the video pipeline, not product identity. Briefs/prompts use deterministic templates, not Gemini text generation. No separate API billing is needed.

## Prerequisites and setup

Python 3.11+; ffmpeg and ffprobe on PATH. Check:

```sh
python --version
ffmpeg -version
ffprobe -version
python -m venv .venv
```

Linux/macOS: `source .venv/bin/activate`. Windows PowerShell: `.\.venv\Scripts\Activate.ps1`.

```sh
python -m pip install -r requirements.txt
python -m app --help
python -m app doctor
python -m app serve
```

Open http://127.0.0.1:8000. Server is loopback-only by default and the CLI does not offer a public host option. Do not reverse-proxy it publicly.

If using uv: `uv venv .venv`, then `uv pip install -r requirements.txt`. Copy .env.example to .env only if needed; defaults work without an API key.

### This workspace

Source lives in WSL Ubuntu at /home/teamsy/nextgen-local. The prepared .venv is a **Windows** Python environment because Windows already has Python and FFmpeg. From Windows PowerShell:

```powershell
Set-Location '\\wsl.localhost\Ubuntu\home\teamsy\nextgen-local'
& '.\.venv\Scripts\python.exe' -m app serve
```

Do not run that .venv with Linux Python. For native Linux use a separate .venv-linux after installing Linux FFmpeg and Python venv support.

SQLite cannot reliably lock over the WSL UNC share. On Windows, when OUTPUT_ROOT resolves to a UNC path, database storage automatically uses %LOCALAPPDATA%/nextgen-local/<output-path-hash>/nextgen.db; project media stays under OUTPUT_ROOT. `doctor` prints both locations. Back up both. Explicit DATABASE_URL overrides this behavior; use a local disk for SQLite.

The requested /home/teamsy/flow-content-pipeline was not present, so its four source files could not be read or reused. Media processing here was implemented independently.

## Mock quickstart

```sh
python -m app demo
```

This creates a synthetic sample, approves fixture facts and prompts, generates one mock clip, assembles an 8-second portrait video, runs QC and exports a package. It refuses to run when VIDEO_PROVIDER is not mock. Normal UI/CLI workflows require explicit approvals.

```sh
python -m app create-project --name "Cup reel" --product-name "Blue Cup" --source-url "https://example.com/cup" --target-audience "Office workers"
python -m app generate-brief --project PROJECT_ID
python -m app add-fact --project PROJECT_ID --fact "color: blue" --status verified --source "Product label" --notes "Checked manually"
python -m app add-fact --project PROJECT_ID --fact "shape: cylinder" --status verified --source "Product photo" --notes "Checked manually"
python -m app add-fact --project PROJECT_ID --fact "size: 300 ml" --status verified --source "Product label" --notes "Checked manually"
python -m app add-fact --project PROJECT_ID --fact "accessories: none" --status verified --source "Package contents" --notes "Checked manually"
python -m app approve-facts --project PROJECT_ID
python -m app generate-prompts --project PROJECT_ID
python -m app approve-prompts --project PROJECT_ID
python -m app generate-test --project PROJECT_ID
# Inspect clip-01-hook.mp4, then explicitly approve:
# Inspect the current clip in the UI before approving it:
python -m app approve-test --project PROJECT_ID
python -m app assemble --project PROJECT_ID
python -m app qc --project PROJECT_ID
python -m app export --project PROJECT_ID
```

UI provides these actions, editing forms and media previews. Add evidence before marking facts verified. Verification is a human evidence assessment, not automated source verification. URLs are preserved; no marketplace scraping occurs.

Changing facts, reference images or prompts invalidates dependent approvals and clips. Voiceover/subtitle changes require reassembly. Claim detection is a conservative English/Thai keyword heuristic, not exhaustive safety or factual validation; humans must review all claims. Unverified/seller claims are excluded from prompts.

## Voiceover and Thai subtitles

Upload JPG/PNG/WebP reference images, WAV/MP3/M4A voiceover, or UTF-8 SRT subtitles in the UI. For CLI:

```sh
python -m app assemble --project PROJECT_ID --voiceover narration.wav --subtitles captions.srt
```

Voiceover replaces original audio and is padded/trimmed to reel length. Subtitles are embedded as an MP4 mov_text soft-subtitle track and included as SRT in exports; some social apps ignore soft tracks, so check playback before posting. No automatic Thai TTS or transcription is included. Exports contain editable Thai caption/narration drafts.

Every normalized clip is 720x1280 H.264 at 24 fps with stereo AAC; silent inputs receive a silent track for consistent concatenation. The mock soundtrack is silence, not synthesized narration.

## Exports and QC

projects/PROJECT_ID/exports/final-reel.mp4
projects/PROJECT_ID/exports/qc-report.json
projects/PROJECT_ID/exports/project-package.zip

QC verifies nonempty output, video/audio requirements, positive duration, portrait dimensions, codec information and ffprobe readability; FFmpeg additionally decodes the streams. Visual review remains required: shape/color, logo spelling, extra parts, hands/faces, fake text, claims, continuity and CTA.

ZIP includes the final reel, current clip(s), original source URL/manifest, facts with evidence, prompts, Thai text drafts, QC and a review checklist. Current projects generate one UGC clip; manifests still accept a complete seven-shot legacy package. It is a review package, not publication approval.

## Flow credits and gflow-cli

VIDEO_PROVIDER=gflow deliberately blocks generation and reports why. Run `python -m app gflow-doctor` for local installation metadata; exit 2 means not ready. It does not access browser sessions or balances.

User selected gflow-cli, which is unofficial and reverse-engineered. Upstream documents browser-detection suppression and internal-service usage. The selected package must be audited/adapted before its account/generation paths satisfy this project's no-bypass requirement. Its known-issues documentation also reports missing credit lookup for accounts migrated to flow.google.com. Never substitute guessed account/credit values or enable generation with a config checkbox.

No official public Flow-credit API was located in the research. Google distinguishes Flow/Google One credits from Gemini API/Cloud billing. Some subscription developer Cloud-credit benefits exist, but are not Flow credits. There is no automatic Gemini/Vertex fallback, no GoogleVeoProvider and no GOOGLE_API_KEY field in this revision; this intentionally follows the user's later billing restriction.

For live acceptance, first establish a non-bypass browser path, verify the user's own active Pro/Ultra account, current model, available credits and per-generation cost, then obtain approval for one test only. Do not re-submit an indeterminate operation. Live generation/download/credit consumption have not been tested.

Sources:
- https://support.google.com/flow/answer/16526234?hl=en
- https://ai.google.dev/gemini-api/docs/google-ai-plans
- https://github.com/ffroliva/gflow-cli/blob/develop/docs/ARCHITECTURE.md
- https://github.com/ffroliva/gflow-cli/blob/develop/KNOWN_ISSUES.md

### Veo Lite limits

Do not equate Flow's model UI with Gemini/Vertex model IDs or capabilities. Official Gemini Veo documentation lists model-dependent image-reference/extension support; Lite does not inherit all full-model features. Our mock ignores reference images; live gflow capability flags remain unknown until checked for the selected Flow model. No product identity guarantee, no hardcoded credit price and no claim that every endpoint supports reference images. See https://ai.google.dev/gemini-api/docs/veo and the current Flow model settings. API model examples are irrelevant to this Flow-only build and are not used.

## Manual posting and security

Review final video and facts, correct subtitles/CTA, apply required AI/affiliate disclosures, then manually upload and attach your product through the platform's own UI. This app never logs into, posts to or attaches carts on TikTok, Shopee or Facebook.

No password, cookie, OTP or session-upload fields. No seller/shared account. .env and runtime files are ignored. Mutations require CSRF tokens; Host/Origin checks limit cross-site access. Files are confined to project directories. This is a single-user local tool, not a multi-tenant service. Do not enter secrets in product fields.

## Troubleshooting

- FFmpeg missing: install FFmpeg for the operating system running Python; check both executables in the same terminal.
- database locked on a UNC path: use the automatic local database location or set DATABASE_URL to a local disk.
- Facts approval blocked: add evidenced color:, shape:, size:, accessories: facts, classification verified and review notes.
- Batch disabled: generate and approve the current test, then batch. Editing inputs revokes approval.
- gflow blocked: this is an explicit implementation boundary; do not switch to a paid API to bypass it.
- Crash during a job: preserve database/media and inspect the job. There is no automatic resume/reset for stuck or ambiguous work. Do not submit the same remote generation again without reconciliation.
- Subtitle track not visible: enable it in a capable player; social apps may require burned-in captions, not provided by this MVP.
- Mock clips do not show my product: correct, they are synthetic fixtures.

## Tests

```sh
python -m pytest -q
python -m app demo
```

The suite includes a real FFmpeg/ffprobe integration run; neither command calls an external generation API. Exact verification results and file inventory are recorded in docs/verification.md.

# nextgenAi-clone
