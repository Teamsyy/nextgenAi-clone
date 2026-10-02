# Shopee Video automation design

## Goal

Turn the existing local product-video studio into a short guided flow: paste a Shopee product URL, choose a video style, inspect the generated preview, then approve and publish the Shopee Video with its product attached. Android USB is the publishing bridge. The user wants the app to automate the publish flow after they approve it in the app.

The approved design is for a single local user on Windows, one Android phone, Thai-first UI, the existing GFlow video provider, and one UGC clip per project. Existing raw clips remain available; title and soft top blur are rendered to the preview/final output. The app never stores Shopee passwords or OTP values.

## User flow

1. **One-time setup.** A setup card explains Shopee Affiliate enrollment and Android USB setup. The app opens Shopee's own enrollment flow; the user completes account/social information, OTP, KYC and payout details directly with Shopee. The app never automates identity, OTP, payment or affiliate enrollment. Until enrollment and product attachment are available, publishing stays blocked.
2. **Create a video.** The user pastes a Shopee product URL and chooses a small set of named UGC styles. The app reads public product metadata when available and shows it for correction. If the page cannot be read, it asks only for missing product details and allows reference-image upload. Facts and title remain reviewable before generation.
3. **Generate and preview.** Use the configured provider already supported by the project. After generation, automatically create a derived preview with the selected style, product name, subtle top blur, and a thumbnail without a play icon. Preserve the original provider clip and never apply title/blur twice during assembly.
4. **Prepare and approve.** A preflight checks that the phone is connected, Shopee is ready, and the product can be attached through the native Add Product flow. If matching is ambiguous or Affiliate is unavailable, resolve it before enabling the post action. Once ready, show one clearly labeled action, **“อนุมัติคลิปและโพสต์ Shopee Video”**. Clicking it is explicit approval to publish that reviewed clip. The app transfers the MP4 to the paired phone over USB, fills the caption, attaches the verified product and submits the post.
5. **Report outcome.** Show each stage and the resulting Shopee status when it can be read. Keep the project and local files if publishing fails.

## Android and Shopee integration

Use the installed Android SDK Platform Tools `adb` on the local host; do not add an unofficial Shopee API or reverse-engineer private endpoints. Pairing requires the user to enable USB debugging and accept Android's RSA trust prompt. The app targets one selected, authorized USB serial; reject unauthorized, offline, multiple-unselected, locked or missing devices. Do not enable ADB over Wi-Fi.

The Shopee mobile app remains the account/session owner. The app may automate only the fixed video-upload and Add Product steps needed for this flow. Product matching uses the submitted Shopee product URL/title. A preflight confirms the eligible product and resolves ambiguity before the publish action is enabled. If Shopee presents OTP, CAPTCHA, account enrollment, a policy prompt, or an unrecognized screen, stop and ask the user to finish or inspect it on the phone. Do not bypass those gates.

## State and failure handling

Persist an operation stage so refreshes and restarts do not lose the outcome: `device_check`, `transfer`, `open_shopee`, `select_product`, `upload`, `submit`, `published`, `failed`, or `indeterminate`. Before submission, a definite failure may be retried from that stage. After submission begins, an unknown result is `indeterminate`; never automatically resubmit, because that could create a duplicate public post. The user must reconcile the state in Shopee before retrying.

The post action is CSRF-protected and scoped to the current project and approved preview. Record the preview hash and product URL used, so edits invalidate the approval. Continue to reject stale clips, stale approvals and duplicate concurrent publish jobs.

## Security and privacy

- Bind the service to loopback as today; never expose the ADB bridge as a network endpoint.
- Invoke only fixed ADB commands with argument arrays, selected serial, timeouts and bounded output. Do not accept shell commands, arbitrary device paths, package names or tap coordinates from form input.
- Use a state-aware interaction adapter with known Shopee screen checks. Stop on unknown state rather than guessing taps.
- Keep credentials, cookies, OTPs, payment/KYC values and full ADB screen dumps out of app storage and logs. User authentication stays in Shopee.
- Restrict product-page fetching to HTTPS Shopee hosts, validate redirects and resolved IPs against SSRF, limit response size/time, and treat page text/images as untrusted input.
- Do not use the app's posting automation to bypass login, OTP, CAPTCHA, platform limits, or eligibility checks.

## Scope boundaries

Included: simple URL/style intake, metadata extraction with manual fallback, guided Affiliate/device setup, automatic styled preview, Android USB transfer, Shopee Video upload and native product attachment, in-app approval before each post, stage/status recovery, and visible error guidance.

Not included: automatic affiliate-account enrollment, OTP/KYC/bank entry, silent/background publishing without the in-app approval button, iPhone publishing, bulk campaign posting, multiple accounts/devices, a cloud queue, unofficial/private Shopee APIs, anti-bot bypass, or guaranteed success across arbitrary Shopee app versions.

## Acceptance criteria

1. A user can start with a Shopee URL and a style selection; the app asks only for product facts it cannot safely extract.
2. A completed GFlow generation produces a visible title/blur preview and thumbnail without a duplicate play icon, while preserving the raw clip.
3. The UI explains Affiliate enrollment and USB prerequisites and does not request OTP, password, KYC or payout data.
4. The publish control clearly communicates that approval will publish the preview. It is unavailable until the preview, paired device and verified product attachment are ready.
5. A test/mock ADB adapter can verify transfer, navigation, product matching, success, definite failure and indeterminate submission without a real Shopee account or device.
6. A real-device smoke test uses the user's already enrolled account and requires the user to opt in to a single public post. Unknown screens and unknown submission results never trigger an automatic retry.
7. Existing local media workflow, file confinement, CSRF/Host/Origin defenses, manual review, and all prior tests remain intact.

## Decisions and evidence

- Android is confirmed by the user. Android ADB requires USB debugging and user acceptance of a host RSA key: [Android Debug Bridge](https://developer.android.com/tools/adb).
- Shopee's help center describes adding a product in the Shopee Video caption/publish flow: [Create and edit Shopee Video](https://help.shopee.ph/portal/4/article/137208?seo=1).
- Shopee Affiliate enrollment involves user-submitted account/social details and email verification, with follow-up KYC and payout setup: [Affiliate enrollment](https://help.shopee.co.th/portal/10/article/123889), [application follow-up](https://help.shopee.co.th/portal/10/article/136331).
- Current repository explicitly describes manual posting and has no ADB/Shopee integration. This feature supersedes that product constraint only after this design and a later implementation plan are reviewed.
