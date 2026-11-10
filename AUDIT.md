# Codebase and endpoint audit

Audited 2026-11-08. Scope: all application files, HTTP routes, SQLite storage, ESP32 request/response handling, LCD/audio control flow, original launcher and QR helper, and setup documentation. The optional launcher and QR helper were subsequently removed during cleanup; regression tests now live in `python/tests/`. This is a source audit plus isolated software verification, not certification of assembled hardware.

The application now uses Flask with separate routes, database code, Jinja templates and static CSS. Its documented classroom workflow is implemented. It remains a trusted-LAN prototype; the unresolved findings below matter before wider deployment.

## Findings addressed

| Priority | Finding in original code | Resolution |
|---|---|---|
| High | Database exceptions on dashboard, registration and CSV requests were uncaught, so failures could terminate requests without a useful response. | Shared SQLite error handler returns 503, a safe message, retry guidance and an event reference. Server logs retain the exception for diagnosis. Scanner errors remain plain text. |
| Medium | Application was described as Flask but used `BaseHTTPRequestHandler`, a single-threaded `HTTPServer`, inline HTML and inline CSS. | Flask application factory and blueprint; `templates/base.html`, `dashboard.html`, `error.html`; `static/style.css`; Waitress service entry point. |
| Medium | Startup silently inserted three demo students into every database. | Initialization now creates schema/index only. Existing students and attendance are preserved; new databases start empty. |
| Medium | Manual string replacement could modify student content containing template marker words such as COUNT, DAY or CSRF. | Jinja renders values once and autoescapes HTML. Regression test preserves these literal words in student names. |
| Medium | SQLite foreign-key declarations were not enforced per connection. | `PRAGMA foreign_keys = ON` on each connection, with a regression test. Existing orphaned data, if any, is not automatically removed. |
| Medium | Any insertion integrity error was treated as a duplicate. | Explicit conflict targets distinguish known duplicate keys from unrelated constraint failures. Other SQLite failures reach the safe error handler. |
| Medium | CSRF token was global to the running process rather than bound to a browser session. | Signed session CSRF token; another client cannot reuse the token without its session. Cookies are HttpOnly and SameSite Strict. |
| Medium | Camera initialization result was ignored, allowing a false ready state when initialization failed. | Sketch checks `reader.setup() != SETUP_OK`, displays a camera failure and stops. Source fix only; compile/bench verification remains required. |
| Medium | A binary QR payload containing an embedded null byte could be truncated by conversion to Arduino `String`, changing the submitted ID. | Reject embedded null bytes before conversion. Source fix only; compile/bench verification remains required. |
| Low | Date parsing accepted noncanonical dates; CSV lacked a download filename; names allowed DEL/control characters. | Exact ISO date validation, attachment filename and Unicode control-character rejection. |
| Low | Dashboard had no initial empty registry state or registration confirmation, and error responses lacked recovery links. | Empty-state copy, one-time success message, common error page, labels/captions, keyboard focus and responsive form layout. |

Existing strengths retained: parameterized SQL, primary key on `(student_id, day)`, device authentication, admin authentication, HTML escaping, input limits, Excel formula escaping, UTC+08:00 timestamps, bounded scanner HTTP timeouts, and success audio only after HTTP 201.

## Remaining findings and limitations

### High: unencrypted credentials and student data on HTTP

Login credentials, session cookies and the shared device token travel over plain HTTP in the supplied configuration. A party able to observe the connection can read them. Keep this deployment on a trusted private network. Before internet or broader institutional deployment, provide HTTPS and firmware certificate validation, and review account access. Waitress does not itself add TLS. No internet deployment was performed.

### Historical: retired onboard QR decoder payload-copy fix

The current JPEG firmware no longer includes or executes this library. For the earlier onboard-decoding implementation, the original upstream decoder copied `data.payload_len` bytes into the 1024-byte `QRCodeData.payload` and appended a terminator without a capacity check. The updated bundled archive now rejects decoded lengths greater than or equal to the destination capacity before either write. This addresses the identified copy site; it is not a complete audit of the decoder. Replace any earlier installed copy with the updated ZIP. Its source changes and SHA-256 are recorded in `firmware/libraries/README.md`.

### Medium: shared account and token, without login throttling

There is one administrator identity, no separate teacher roles, no per-user access history, and one scanner token. There is no login attempt throttling or token rotation interface. These match the current prototype scope but do not support accountable multi-user school administration. Use strong, distinct secrets and restrict network access; add individual accounts and controls when that deployment is required. The browser now uses a signed eight-hour administrator session and a CSRF-protected Sign out action; individual accounts and server-side session revocation are not implemented.

### Medium: static QR content does not prove student identity

Anyone who copies a registered ID's QR can present it. One check-in per day prevents duplicate rows; it does not establish who scanned. Teacher supervision or a separate identity check is required if preventing proxy attendance is a requirement.

### Medium: offline scans and ambiguous timeouts

No local queue or delivery acknowledgment beyond the HTTP result exists. Disconnected scans are not saved. A timeout can occur after commit; rescan and inspect the dashboard, with 409 confirming that day's existing attendance. This is documented rather than hidden by optimistic success messages. The scanner's five-second repeat throttle also applies after a failed attempt.

### Medium: hardware remains unverified

The current native-JPEG firmware compiles for AI Thinker ESP32-CAM on Espressif core 3.2.0, with no QR-reader dependency. The server's real-JPEG and real-local-HTTP tests pass. No physical board was exercised by these checks. Camera focus, sustained capture rate, PSRAM, LCD contrast/address, DFPlayer tracks, actual LED wiring, power stability and boot-strapping behavior remain bench acceptance items. GPIO2, GPIO12 and GPIO15 now carry external signals; GPIO12 must stay low at reset and DFPlayer TX must be disconnected from GPIO15. Earlier dated findings below describe earlier implementation/verification states.

### Low: reporting and operational scope

The date is determined by the server clock in fixed UTC+08:00. Correct the host clock if it is wrong. Records now include on-time/late status using one class start time per calendar day. Multiple class sessions, check-out and automatic absence calculations remain unsupported. The dashboard requires refresh. Lists and CSV are not paginated; reassess for large registries. Backups and log retention are manual. Configuration/environment mistakes and database initialization failures stop startup rather than starting an unusable service.

## Endpoint verification

| Route | Verified outcomes |
|---|---|
| `GET /` | Admin session required; populated and empty dashboard; strict date validation; escaped student content; no-store headers; database failure 503. |
| `POST /students` | Admin session and same-session CSRF required; valid registration 303 to printable QR card; duplicate 409; invalid input 400; oversized form 413; database failure 503. |
| `POST /scan` | Device token required 401; registered first scan 201; duplicate 409; unknown 404; malformed/empty/oversized ID and invalid UTF-8 400; wrong media type 415; application body limit 413; database failure 503; plain-text response. |
| `GET /report.csv` | Admin required; date filter; empty report; Excel UTF-8 BOM; formula protection; UTC+08:00 timestamps; attachment filename; invalid date 400; database failure 503. |
| `GET /static/style.css` | Public CSS 200; traversal outside static folder rejected. |
| HTTP methods and routing | GET routes support HEAD without a response body; declared routes support OPTIONS; unsupported methods 405 with Allow header; unknown paths 404. |

The table above describes the original audit. New authentication, scheduling and QR endpoints are listed in the current update below and in README.md. Public static assets contain CSS and print-button JavaScript only. Authentication and CSRF tokens are not sent to the scanner response. Flask's route map is asserted in tests so new routes require a coverage review.

## Verification performed

- **16 automated tests passed**, using temporary SQLite databases. Includes simultaneous scans (one 201 and eleven 409 responses), persistence after reopening, foreign keys, and check-ins either side of Philippine midnight.
- Final command: `.\.venv\Scripts\python.exe -m unittest discover -s python/tests -t python -p 'test_*.py' -v`. The final run passed without warnings.
- Real HTTP request through Waitress passed for dashboard authentication and rendering.
- Headless Chromium passed registration, success feedback, a device scan, a refreshed attendance count, CSV download, error page and recovery link.
- Desktop 1280×1000, tablet 768×1024 and mobile 390×844 had no document-level horizontal overflow. Desktop and mobile screenshots were visually inspected. Tables remain horizontally scrollable on narrow screens.
- UI detector returned no findings, but could not resolve a Jinja `url_for` stylesheet link statically; linked-CSS analysis was incomplete. Actual browser requests loaded the stylesheet.
- Tested dependency environment: Python 3.13.2, Flask 3.1.3, Waitress 3.0.2. Python 3.9 is the documented minimum, but was not separately tested. Dependencies installed in project `.venv`.
- Expected database-failure tests verified generic client errors and server-side diagnostic capture. Errors are visible to the operator in the server log/terminal, not exposed in a web diagnostics dashboard. No log persistence, alerting, or new developer-role interface was added.

Browser smoke scripts and screenshots are local ignored artifacts in `.audit/`. They are not part of the application or the repeatable unit-test suite. No real student database was created or changed during testing.

## Hardware acceptance checks before use

1. Compile with the actual installed libraries and selected board/core; review and address the upstream QR bounds issue first.
2. Boot and scan with LCD and DFPlayer connected; verify stable supply voltage under camera, Wi-Fi and speaker load.
3. Register a test ID and scan once: verify exactly one database row, LCD confirmation and track 1.
4. Scan it again: verify no new row, duplicate LCD message and track 2.
5. Scan an unknown ID and malformed/oversized/binary QR: verify rejection without a wrong student ID being submitted or a crash.
6. Disconnect Wi-Fi, stop the server, use a wrong token, and simulate a database failure: verify no success confirmation and appropriate failure feedback.
7. Reconnect and rescan after an ambiguous timeout; confirm the dashboard and duplicate behavior agree.
8. Verify tracks 1–4, camera initialization failure display, long-ID LCD truncation, power cycling and attendance across the local date boundary.


## Current feature update: login, QR cards and class times

- Browser Basic authentication was replaced with `/login` (GET/POST), `/logout` (POST), signed eight-hour sessions, CSRF validation, and fresh CSRF state after login. Unauthenticated administrative requests redirect to login; device authentication is unchanged.
- Registration opens `/students/<student_id>/print`. `/students/<student_id>/qr.png` generates a locally encoded, authenticated QR image from only that registered ID; unknown students return 404. The print page includes a PNG download and print stylesheet.
- `/schedule` (POST) validates a date and 24-hour start time. The daily schedule is locked once it exists and attendance has been saved. Initial scheduling remains possible for legacy records, whose status is not retroactively assessed.
- Attendance is accepted from the class start time. Under 15 minutes is on time; exactly 15 minutes, 30 minutes, and more than 30 minutes are late. No schedule returns 422; scanning before start returns 425; both leave attendance unchanged. SQLite serializes schedule edits/check-ins so a saved status uses a consistent schedule.
- Existing databases receive a status column with `not-assessed` for old records and a new `class_schedule` table. No student or attendance records are removed. Dashboard and CSV expose the saved status.
- Updated firmware reads the 201 response body: `Attendance saved` displays **On time**, `Attendance saved: late` displays **Late**. Both play success track 1. Codes 422 and 425 display class-time failures and play track 4. Firmware must be uploaded again; compilation and physical LCD/audio behavior remain unverified.
- The original 16-test/browser result above is historical. Updated tests cover form login/logout, session expiry/tampering, CSRF, QR generation/authentication, schedule validation/locking, legacy migration, and the exact late boundaries in addition to the earlier checks. Final verification results are recorded after running the current suite.

Final verification for this feature update:

- **28 automated tests passed** without warnings, including exact start/15-minute/30-minute boundaries, simultaneous scans, legacy migration and initial scheduling for legacy records.
- Real Waitress + Chromium flow passed: form login (including wrong-password recovery), logout, schedule save/lock, registration, print/download, late scan, duplicate, CSV, and mobile/tablet/desktop layout.
- OpenCV independently decoded the generated PNGs to the exact registered IDs for both `2026-001` and a 40-character ID. The decoded normal ID was then posted to `/scan`; the saved attendance resolved to the registered student and showed Late.
- The print button was exercised and a one-page A4 PDF was generated. Its student name/ID were verified, controls were excluded, and the printed layout was visually inspected. Login, card and mobile dashboard screenshots were also inspected.
- Dependency environment now also includes qrcode 8.2 and Pillow 13.0.0. The UI detector returned no findings, with the same static Jinja stylesheet-resolution limitation recorded above.
- Physical QR decoding by the ESP32-CAM, LCD output, audio and firmware compilation have not been verified. Upload the new sketch and complete the hardware acceptance checks before use.

## Interface redesign and public landing page

The user selected a darker futuristic style. A new public `/` landing page explains the product, with an authored CSS 3D scanner/card scene and optional pointer tilt. The administrator workspace moved to `/dashboard`; all protected endpoints still require the signed administrator session. A new regression check ensures that the public landing page does not query or expose student data.

The dashboard now has real attendance counts for the selected date, attendance/registry searches, semantic status badges, class scheduling, and clear links to printable QR cards and CSV reports. Login includes password visibility. Search, motion and pending states are progressive enhancements; core forms and navigation remain server-rendered Flask.

- **29 endpoint and storage tests passed**, including the public/private route split and all existing attendance/security cases.
- Live Waitress/Chromium checks passed for login/logout, wrong-password recovery, password visibility, class-time save/lock, registration, QR decoding, the print button and PDF, late scans/duplicates, CSV downloads, and table search filtering.
- Landing screenshots were checked at 1440px desktop, 768px tablet, 375px phone and landscape sizes. Login, print-card and dashboard desktop/mobile views were checked. No document-level horizontal overflow was found; wide data tables scroll inside their regions.
- Animation Pause/Play and reduced-motion behavior were checked in the browser. There are no third-party runtime script/font/image dependencies; fonts are self-hosted with license files.
- A print-preview defect was corrected so the A4 PDF has white margins instead of dark page margins. Template UTF-8 BOMs were removed to preserve standards-mode HTML rendering.
- The landing-page decorative scanner and sample QR do not represent a physical hardware test or connection telemetry. Firmware behavior and hardware audit limitations above remain unchanged.

[DESIGN.md](DESIGN.md) records the selected palette, typography, interaction rules and Superdesign reference. The design reference was reviewed, and unsupported roster-import/version claims in the generated concept were corrected before handoff.

## Offline runtime and installation verification

- All runtime assets, fonts, scripts, QR rendering and SQLite storage are local. The full browser workflow passed with internet page requests intercepted/blocked and Python socket connections restricted to loopback. No external requests were attempted.
- **30 automated tests passed**, including persistence of installation settings and environment-variable overrides.
- A clean virtual environment installed all 11 pinned runtime packages from `offline/wheels` with `--no-index`, `--no-cache-dir` and pip version checks disabled. Dependency validation and a QR-generation import check passed. Bundled wheels target Windows x64 / CPython 3.13; Python itself is not bundled.
- `start.cmd` starts the normal Waitress service on port 5000 using `python/attendance.db`. This is persistent storage, unlike the earlier disposable preview. Its initial generated administrator password, device token and stable session key are stored in ignored `python/instance/config.json`; environment variables may override them. Credentials are not printed by the server or served as public files.
- `install_offline.cmd` supplies the no-index installer for matching systems. See `offline/README.md` for setup and network requirements.
- Offline means no internet access is required. A reachable local Wi-Fi connection and a running server remain necessary for the ESP32-CAM. The hardware has no offline delivery queue. The physical scanner, wiring, LCD and audio still require bench verification.

## Signed cards, student-name LCD output and 40-minute absence

This update supersedes the earlier plain-ID QR payload, on-time label and late-only timing rules above.

- Website-issued cards now contain a version, student ID and HMAC-SHA256 signature. Each student has a random 256-bit signing key stored in SQLite. The server verifies signatures with a constant-time comparison; plain IDs, modified IDs/signatures and revoked cards return 403 without creating attendance.
- Authenticated, CSRF-protected `POST /students/<student_id>/replace-qr` rotates that student's key. All previous cards and their copies become invalid. An exact copy of a currently valid QR remains usable: signatures do not authenticate the person presenting it or distinguish original paper from a photograph.
- Accepted scans save Present before 15 minutes, Late from 15 minutes to just before 40 minutes, and Absent at 40 minutes or later. Students who never scan are not automatically marked absent. Duplicate scans preserve the first saved status.
- The two-line device response contains status followed by an ASCII-safe student name of at most 16 characters. Updated firmware displays the name on LCD row 1 and Present/Late/Absent on row 2. Duplicate scans display the name and Already recorded. Saved outcomes use the existing attendance-recorded audio track.
- Startup provisions keys for existing students and renames historical on-time statuses to present. Historical Late records are preserved. No new runtime dependencies are required. Upload the updated firmware and reprint all legacy plain-ID cards.
- **37 automated tests passed**, covering timing boundaries, tampering, replacement, persistence, concurrent duplicates, rollback, endpoint authentication/CSRF and LCD-safe output.
- Real Waitress/Chromium verification passed with internet blocked: registration, independent OpenCV decoding of signed cards, replacement/revocation, name/status responses for all three outcomes, CSV, print/PDF, search and responsive layouts. A maximum-length student ID produced an 88-byte signed payload and decoded successfully.
- Firmware compilation, physical ESP32-CAM decoding, LCD output and audio remain unverified. The upstream QR-reader bounds concern recorded above remains a hardware-release prerequisite.

## Dashboard camera preview (2026-11-10)

- Added token-authenticated JPEG uploads and administrator-only reads at `/camera/frame`. The device checks demand while idle, sends at most approximately two frames per second while viewed, and reuses the decoder-owned grayscale frame through a callback. No concurrent camera acquisition is introduced.
- Only the latest frame is retained in server RAM. Frames older than five seconds are not served. Uploads are limited to 64 KiB; other Flask requests remain limited to 4096 bytes. No camera IP, device token, or credentials are embedded in the dashboard.
- The panel includes explicit Start/Stop, connection and stale-frame states, and pauses while its browser tab is hidden. It does not claim that a visible QR has been accepted; attendance remains determined by the scan endpoint.
- All 39 Python tests passed, including preview authentication, demand, upload limits, staleness and ordinary scan-body limits. JavaScript syntax and the runnable preview control check (`node python/tests/test_camera_preview.cjs`) passed. Updated firmware compiled on ESP32 core 3.2.0 for `esp32:esp32:esp32cam` (1,065,966 bytes program storage; 64,068 bytes globals). Browser inspection could not run because both the browser host and native computer-use pipe were unavailable in this session; visual and physical acceptance remain outstanding.
- The preview shares the existing trusted-LAN HTTP limitation. It adds encoding and network load and can pause during scan submissions. It is an aiming aid, with no recording, not a guaranteed full-motion stream. The supplied single-process Waitress server is required for the in-memory frame cache.

## Camera aiming, scan feedback and live records (2026-11-10)

- Configurable sensor-level vertical flip and horizontal mirror rotate the actual camera image 180 degrees. Capture defaults to VGA for more QR detail. The preview and decoder share that corrected image. No dependency ZIP change was needed.
- Added an aiming guide, periodic no-decode and frame-stall diagnostics, explicit HTTP scan-result logs, and recent administrator-only scanner feedback. Feedback is token-authenticated and transient; QR payloads, device tokens and Wi-Fi passwords are not logged. A detected pattern is not presented as a successful check-in.
- Dashboard attendance rows, counts and recent feedback update about every two seconds, preserving the preview, form entries and search filter. Updates pause in hidden tabs; network/session failures are visible. Full-page manual refresh remains available without JavaScript. This supersedes earlier notes that the dashboard requires a manual refresh.
- All 41 Python tests passed, including saved/duplicate/rejected check-in feedback, output escaping, decoder feedback authentication and expiry. JavaScript syntax, preview controls and live-update behavior checks passed. Final AI Thinker firmware build passed on ESP32 core 3.2.0: 1,070,506 bytes program storage, 64,108 bytes globals.
- Physical focus, VGA capture/decoder speed, orientation on the assembled board, actual QR reading and end-to-end hardware check-in remain unverified. Browser visual inspection remains unavailable in this session. Changes improve aiming and diagnostics without claiming that the reported physical decode failure has been reproduced or eliminated.

## Native JPEG, laptop QR decoding and hardware results (2026-11-10)

This section supersedes the earlier onboard-decoder and preview-demand behavior above.

- ESP32 firmware now uses Espressif `esp_camera` directly: native VGA JPEG, two PSRAM buffers and a 250 ms target capture interval. There is no `ESP32QRCodeReader`, quirc decoding or software preview JPEG conversion on the ESP32. OV3660/OV2640 sensor identification is automatic for the AI-Thinker board pin map.
- Token-authenticated `/camera/frame` uploads are decoded locally with OpenCV. Only bounded JPEGs up to 800 x 600 and 256 KiB are accepted. No internet API, downloaded recognition model or image/video recording is used. Administrator-only preview reads still expire after five seconds. Scanning runs with no dashboard viewer.
- QR credentials still pass the existing HMAC verification, revocation and schedule checks. No image alone can bypass signed-card validation. Same-credential events have a five-second cooldown, and a decode lock prevents concurrent frame processing. Empty scenes return 204 without a failure indication; unreadable patterns return a distinct state without recording attendance.
- The server returns 201 plus the established status/name body only after saving. The firmware validates that body before green light/track 1. Duplicates are red/track 2; invalid cards red/track 3; network/server/schedule failures red/track 4. Unreadable patterns use red with no audio. Saved Late/Absent records are still successful database saves and therefore green.
- LCD uses GPIO13/14 through the level shifter. DFPlayer commands use GPIO2 through 1 kOhm, with no acknowledgment or RX pin. DFPlayer TX must be left unconnected. Green LED uses GPIO12 and red uses GPIO15, each with its own 470 Ohm resistor to the anode and cathode to GND. GPIO12 additionally needs a 10 kOhm pull-down and must never be pulled high during reset. GPIO4 is unused, avoiding the onboard white flash.
- All 45 Python tests passed, including actual signed/mirrored/max-ID JPEG decoding, invalid-card rejection, dimension/body limits, authorization, safe decoder failure logging, cooldown, and a real Waitress JPEG upload/LCD-response transport check. Existing preview/live-dashboard JavaScript checks passed. OpenCV 4.14.0.94 and NumPy 2.5.4 are installed and bundled; all 13 pinned packages installed into a clean temporary environment with no index/network access, and dependency/import checks passed.
- The wiring guide and SVG have been updated. Browser visual inspection remained unavailable because the browser host/native pipe were not running. Physical focus, scan latency/reliability, LED behavior, LCD and audio playback have not been bench-tested; TX-only audio cannot verify module/card presence or playback success. No claim is made that software tests certify the assembled hardware or guarantee a scan speed.

Final native-JPEG firmware compile passed: 1,043,074 bytes program storage (33%) and 55,836 bytes globals (17%) on ESP32 core 3.2.0. The 45-test suite passed again after the final recent-result display adjustment. Wiring SVG styling was expanded for portable rendering and the rendered net/resistor labels were checked.

## Optional class end time and missing-LCD handling (2026-11-10)

- Added nullable end_time migration preserving old schedules and records. Strict same-day HH:MM validation rejects end at/before start. New check-ins at or after end return 410 Class ended without saving; duplicates still confirm existing records. End can be changed/cleared after check-in while start stays locked. Dashboard form and live refresh keep end editing available.
- Firmware probes the configured I2C LCD address once on startup and skips LCD initialization/writes when absent. Serial results continue. Restart after connecting LCD at the configured address. Firmware handles Class ended with red/track 4. The separate Check server error still needs network/server diagnostics.
- All 48 Python tests passed, including exact end boundary, no-save rejection through real QR JPEG upload, editable end with locked start, input validation and legacy schema migration. Dashboard refresh and camera preview JavaScript checks passed, along with JavaScript syntax checks. Hardware behavior and browser appearance have not been verified for this change.

Firmware compile passed for AI Thinker ESP32-CAM: 1,043,546 bytes program storage (33%) and 55,844 bytes globals (17%). LiquidCrystal architecture warning remains nonfatal.
