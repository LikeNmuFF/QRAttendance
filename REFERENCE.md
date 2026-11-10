# QR Attendance technical reference

Return to the [project README](README.md) for the quick start, diagrams and hardware overview.

A trusted-LAN attendance system for an AI-Thinker ESP32-CAM with OV3660/OV2640 camera and PSRAM, a 16×2 I2C LCD, and a DFPlayer Mini with a speaker. The ESP32 captures JPEG frames; local OpenCV on the laptop decodes the signed QR credential and Flask verifies it; SQLite records one check-in per student per Philippine calendar day (UTC+08:00).

The teacher dashboard supports student registration, printable QR cards, daily class start and optional end times, Present/Late/Absent attendance, date filtering, and Excel-friendly CSV downloads. Sign in through `/login` with username **admin** and your `ADMIN_PASSWORD`. The scanner uses a separate device token.

## Project structure

```text
firmware/AttendanceCam/
  AttendanceCam.ino             Camera, Wi-Fi, LCD and audio behavior
  config.h                      Wi-Fi, server, device token and pin settings
  camera_pins.h                 AI-Thinker camera wiring for esp_camera
python/
  server.py                     Waitress entry point on port 5000
  requirements.txt              Flask, Waitress and QR image dependencies
  attendance/
    __init__.py                 Application factory, configuration, safe errors
    db.py                       SQLite connections, schema and check-in logic
    routes.py                   Dashboard, registration, scanning and CSV routes
    camera.py                   Bounded JPEG validation and local OpenCV QR decoding
    templates/
      base.html                 Shared HTML document
      components.html           Shared brand and SVG icons
      landing.html              Public animated landing page
      dashboard.html            Attendance and student registration
      error.html                Error and recovery page
      login.html                Administrator sign-in
      student_card.html         Printable student QR card
    static/
      style.css                 Responsive and print styles
      print.js                  Print dialog button
      app.js                    Motion, search, password and form enhancements
      fonts/                    Self-hosted typography and licenses
  tests/
    test_server.py              Storage and concurrency tests
    test_http.py                Endpoint and security tests
  attendance.db                 Persistent students, schedules and attendance
  instance/config.json          Local generated settings; excluded from Git
start.cmd                       One-click local service launcher
install_offline.cmd             Offline dependency installer
offline/                        Bundled Windows/Python 3.13 dependency wheels
AUDIT.md                        Findings, endpoint contract and remaining risks
```

## Offline use and one-click startup

The application runs without internet. On this prepared computer, double-click **`start.cmd`**, then open **http://localhost:5000**. The launcher starts the actual service with a persistent local database, rather than the disposable preview.

The first startup saves generated installation credentials in **`python/instance/config.json`**. Sign in as **admin** using its `ADMIN_PASSWORD`. Its `ATTENDANCE_TOKEN` must match the firmware device token. You can edit the file and restart; environment variables override saved values. Keep this settings file local. The session key is saved so signing sessions does not depend on a new random key each restart.

For a matching Windows/Python installation, **`install_offline.cmd`** installs dependencies entirely from `offline/wheels` using the pinned `offline/requirements-lock.txt`. The included wheels target **64-bit Windows and Python 3.13**, which must already be installed. No Python installer is bundled. See [offline/README.md](offline/README.md).

A local router/hotspot is still needed for the ESP32-CAM to reach the running computer. Internet access is not needed, but a stopped/unreachable server cannot record scans.

## Setup on Windows

Install 64-bit Python 3.13 (the verified Windows version). Open PowerShell in the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r python/requirements.txt
$env:ATTENDANCE_TOKEN = 'choose-your-own-long-random-device-token'
$env:ADMIN_PASSWORD = 'choose-a-strong-password-at-least-12-characters'
.\.venv\Scripts\python.exe python/server.py
```

Use different secrets for the device and administrator. The token must match `DEVICE_TOKEN` in firmware `config.h`. The application requires both secrets; `server.py` generates and saves them on first startup if not supplied. Placeholder device tokens and admin passwords shorter than 12 characters are rejected. Environment values are examples: replace them before use.

Open **http://localhost:5000** for the landing page, then choose **Open dashboard**. Sign in as **admin** with `ADMIN_PASSWORD` at `/login`. The protected workspace is at `/dashboard`. No activation or execution-policy change is required for the direct commands above.

New databases start empty. Register `2026-001` through the dashboard to open its printable QR card. Set today's class start time before testing a scan. Existing databases keep their students and attendance, including any earlier demo data; startup does not add or remove students. Back up `python/attendance.db` with the server stopped before upgrading or copying it.

The Flask factory is available as `attendance.create_app` from the `python` folder. `python server.py` uses Waitress, which supports Windows. For local development only, the activated environment can run `python -m flask --app attendance:create_app run`; Flask's development server is not the scanner deployment entry point. See the official [Flask project layout](https://flask.palletsprojects.com/en/stable/tutorial/layout/) and [Waitress deployment guide](https://flask.palletsprojects.com/en/stable/deploying/waitress/).

The normal server launcher saves a session signing key in `python/instance/config.json`. Direct application-factory usage without a configured key generates a temporary key and requires signing in again after restart. Optionally set a long random `SECRET_KEY` environment value to keep signed sessions valid across restarts. Administrator sessions expire after eight hours; **Sign out** clears the current browser session. Session cookies contain an authenticated flag, CSRF token and flash messages, not passwords. Login, registration, schedule changes and logout use CSRF protection. Enable secure session cookies when deploying behind HTTPS.

## Endpoints

| Method | Path | Authentication | Result |
|---|---|---|---|
| GET / HEAD / POST | `/login` | Public; POST requires CSRF | Sign-in form and authentication |
| POST | `/logout` | Admin session + CSRF | Sign out |
| POST | `/schedule` | Admin session + CSRF | Save start and optional end time for selected date |
| GET / HEAD | `/` | Public | Animated product landing page |
| GET / HEAD | `/dashboard` | Admin session | Dashboard; optional `?date=YYYY-MM-DD` |
| POST | `/students` | Admin session + CSRF | Register `id` and `name`; 303 redirect to printable card |
| GET / HEAD | `/students/<student_id>/print` | Admin session | Printable student card |
| GET / HEAD | `/students/<student_id>/qr.png` | Admin session | QR image; `?download=1` downloads PNG |
| GET / HEAD | `/camera/frame` | Admin session | Latest live preview JPEG, or 503 while waiting |
| POST | `/camera/frame` | `X-Device-Token` | JPEG decode and attendance check-in; 256 KiB maximum |
| POST | `/scan` | `X-Device-Token` | Signed QR credential; two-line LCD response |
| POST | `/students/<student_id>/replace-qr` | Admin session + CSRF | Replace a lost card and revoke all old copies |
| GET / HEAD | `/report.csv` | Admin session | CSV attachment for optional `?date=YYYY-MM-DD` |
| GET / HEAD | `/static/<filename>` | Public | CSS, JavaScript, bundled fonts and font licenses |

Unauthenticated dashboard, report and card requests redirect to `/login`. Flask supplies OPTIONS for these routes. Unsupported methods return 405; unknown paths return 404. Attendance dates must use a valid, zero-padded ISO date. Responses containing student data are marked `no-store`.

`POST /scan` requires `Content-Type: text/plain` and `X-Device-Token`. Send the exact signed credential decoded from the website-issued QR card, not a student ID. Payloads use `QA1.<student-id>.<signature>` and are limited to 128 bytes; current signed payloads are at most 88 ASCII bytes for a 40-character ID. The general application limit remains 4096 bytes.

| Status | Meaning | Scanner behavior |
|---|---|---|
| 201 | Two lines: `Present`, `Late` or `Absent`, then the LCD-safe student name | Name on LCD row 1, status on row 2; track 1 |
| 409 | Two lines: `Already recorded`, then the LCD-safe student name | Name on row 1, duplicate on row 2; track 2 |
| 403 | Invalid, unsigned, forged or revoked QR credential | Invalid QR card; ask your teacher; track 3 |
| 422 | Class time not set for today | Not saved; class time unset; track 4 |
| 425 | Class has not started | Not saved; class not open; track 4 |
| 410 | Class has ended | Not saved; class ended; red light and track 4 |
| 400 | Empty/oversized body or invalid UTF-8 | Generic failure; track 4 |
| 401 | Missing or wrong device token | Device-token error; track 4 |
| 415 / 413 | Wrong media type / application request too large | Generic failure; track 4 |
| 503 | Database unavailable | No success confirmation; retry later; track 4 |

For example, a verified Present scan returns this plain-text body with a single newline:

```text
Present
Maria Dela Cruz
```

The two-line response is status first, name second; the firmware displays the **name first** and the **status second**. The name is transliterated to printable ASCII and shortened to 16 characters for the standard LCD. If transliteration produces no name, it falls back to the student ID. The website and CSV retain the full student name.

An unsigned QR containing only `2026-001` must now be rejected. A repeated scan of a valid current card returns 409. Unknown/tampered/revoked credentials all return the same 403 response without disclosing a student name.

## Network setup

Use `ipconfig` to find the laptop's Wi-Fi IPv4 address and put it in firmware `SERVER_URL`, for example `http://192.168.1.100:5000/scan`. Keep laptop and scanner on the same reachable Wi-Fi without client isolation. Allow inbound TCP 5000 only on the trusted private network. Keep the laptop awake and the service running. Runtime does not require internet access.

When using a phone hotspot, connect **both the laptop and ESP32-CAM to that hotspot** before checking `ipconfig`. Use the laptop's resulting **Wi-Fi IPv4 address**, not the example IP or the phone's gateway address. Update `SERVER_URL` and upload again whenever that address changes. Having internet on both devices does not establish that they can reach one another. From another device on the hotspot, opening `http://<laptop-ip>:5000/` can help check incoming connectivity; a local `localhost` test alone does not check Windows Firewall or hotspot client isolation.

Serial Monitor initially prints `Ready to scan: Connecting WiFi`; this is a startup message. Updated firmware then prints the actual connection state, the ESP32's assigned IP and the configured attendance URL. Preview failures include the HTTP or connection-error code: HTTP 401 indicates a token mismatch; HTTP 404 indicates the server lacks the preview route; a connection error calls for checking the address, running server, firewall and network reachability. Device tokens and Wi-Fi passwords are not printed.

Before starting the camera, firmware scans for the exact configured SSID and reports whether it was visible, its channel, signal strength and whether it requires a password. It also prints Wi-Fi disconnect reason codes. Status `1` means the configured access point was not found; status `6` means disconnected. Use a visible 2.4 GHz hotspot with an exact matching SSID and password. An enabled hotspot may still be hidden or out of range; a wrong password is not established by status `1` alone. Only for a hotspot without a password, use `#define WIFI_PASSWORD ""`. The ESP32 core handles automatic reconnect; the sketch no longer calls `WiFi.reconnect()` every 15 seconds while another attempt may be running. After changing hotspot credentials, reset the board to start a fresh attempt.

`cam_hal: EV-VSYNC-OVF` is a separate camera frame-synchronization overflow, not a device-token error. If it persists after Wi-Fi is stable, camera capture timing and physical performance need separate testing. Compilation alone cannot verify those conditions.

Login passwords, session cookies and device tokens are unencrypted over plain HTTP. This configuration is for a trusted LAN; do not expose port 5000 to the internet. Wider deployment needs HTTPS, firmware certificate validation, and appropriate account/access controls. Waitress improves request handling but does not provide TLS or individual teacher accounts.

## Physical wiring — AI-Thinker board only

For the full component-by-component assembly instructions, read **[the detailed wiring README](firmware/AttendanceCam/README.md)**. It includes the parts list, complete pin table, LCD level-shifter connections, DFPlayer audio card setup, LED resistor/pull-down diagrams, upload steps, staged testing and troubleshooting.

Use the dedicated [wiring diagram](hardware-wiring.svg) with the matching [step-by-step wiring and pre-power checklist](HARDWARE_WIRING.md). These documents assume the exact board and module types listed there; verify the silk-screen labels and specifications on your hardware before connecting power.

Power off while wiring. Do not use the ESP32-CAM onboard microSD slot; these pins are reused. The DFPlayer has its own card.

| From | To |
|---|---|
| Stable regulated 5V supply | ESP32-CAM 5V, LCD VCC, DFPlayer VCC |
| Supply ground | ESP32-CAM GND, LCD GND, DFPlayer GND, level-shifter GND |
| ESP32-CAM GPIO13 | Level-shifter LV channel 1 → HV channel 1 → LCD SDA |
| ESP32-CAM GPIO14 | Level-shifter LV channel 2 → HV channel 2 → LCD SCL |
| ESP32-CAM 3V3 | I2C level-shifter LV reference |
| Supply 5V | I2C level-shifter HV reference |
| ESP32-CAM GPIO2 | 1kΩ series resistor → DFPlayer RX |
| DFPlayer TX | **Leave unconnected**; GPIO15 is now the red LED output |
| ESP32-CAM GPIO12 | 330 Ohm resistor -> green LED anode; cathode -> GND |
| ESP32-CAM GPIO15 | 330 Ohm resistor -> red LED anode; cathode -> GND |
| ESP32-CAM GPIO12 | Additional 10 kOhm pull-down resistor -> GND |
| DFPlayer SPK1 and SPK2 | Speaker terminals; do not ground either terminal |

Use a bidirectional I2C logic-level shifter if the 5V LCD backpack pulls SDA/SCL up to 5V; ESP32 inputs are not 5V tolerant. The shifter's LV and HV reference pins must connect to 3V3 and 5V respectively, and its ground must join the common ground. Use a regulated supply with headroom (typically 5V/2A for this assembly), and verify it under camera/Wi-Fi/speaker load. Do not power the ESP32-CAM or speaker load from a USB-UART adapter's 3V3 output. Adjust LCD contrast. LCD address defaults to 0x27; some backpacks use 0x3F.

GPIO2, GPIO12 and GPIO15 are boot-strapping pins. GPIO12 must remain low during reset; never use an indicator circuit that pulls it up to VCC. Disconnect the old DFPlayer TX-to-GPIO15 wire before using the updated firmware. If upload/boot fails, disconnect the DFPlayer UART wires while powered off, then retry. Do not substitute GPIO16/17, which AI-Thinker uses for PSRAM. Confirm your board and modules before following these assignments. The ESP32-CAM 5V pin, LCD and DFPlayer may share the regulated 5V rail, but every module and the USB-UART adapter must share ground. Never connect 5V logic to an ESP32 GPIO.

### Connect the USB-UART adapter to upload firmware

Power off before changing these connections. Use a 3.3V-logic USB-UART adapter for serial signals; provide board power from the stable regulated 5V supply.

| USB-UART adapter | AI-Thinker ESP32-CAM | Purpose |
|---|---|---|
| TXD (3.3V logic) | U0R / GPIO3 | Firmware upload serial input |
| RXD (3.3V logic) | U0T / GPIO1 | Firmware upload serial output |
| GND | GND | Common reference |
| Stable 5V supply | 5V | Board power; avoid relying on adapter power |
| GPIO0 | GND only while entering upload mode | Hold low, reset, upload; disconnect GPIO0 from GND and reset to run |

Do not connect the adapter's 5V UART signals to U0R/U0T. Avoid powering the board from two 5V sources at once unless the adapter/board wiring is designed for it.

## DFPlayer audio

Use your **1K** resistor between **GPIO2 and DFPlayer RX**. Power DFPlayer VCC from the regulated 5 V rail and connect GND to common ground. Leave TX unconnected. Connect the speaker only across SPK1/SPK2. Use two **330R** resistors for the separate LEDs and a separate **10K** pull-down from GPIO12 to GND. See the [detailed DFPlayer and resistor instructions](firmware/AttendanceCam/README.md#6-connect-the-dfplayer-mini-and-speaker).

Supply actual recordings on a supported FAT-formatted microSD card in the DFPlayer. Audio files are not included.

| Card file | Message |
|---|---|
| `/mp3/0001.mp3` | Attendance recorded |
| `/mp3/0002.mp3` | Attendance already recorded |
| `/mp3/0003.mp3` | Invalid or replaced QR card |
| `/mp3/0004.mp3` | Attendance not saved; please try again later |

Firmware uses `playMp3Folder()` and volume 22 of 30. Commands are TX-only (GPIO2 -> 1 kOhm -> DFPlayer RX), with no UART acknowledgment. Leave DFPlayer TX unconnected. Missing audio does not prevent recording, and the firmware cannot verify playback/card presence. Test each track physically before deployment.

## Firmware setup

1. Install **esp32 by Espressif Systems 3.2.0** through Boards Manager. The camera driver is included. Install **LiquidCrystal I2C** and **DFRobotDFPlayerMini** through Library Manager. **ESP32QRCodeReader is no longer used or required.**
2. Open `firmware/AttendanceCam/AttendanceCam.ino`; keep `config.h` and `camera_pins.h` beside it.
3. Keep the correct Wi-Fi credentials, laptop `SERVER_URL` (for example `http://<laptop-ip>:5000/scan`) and matching `DEVICE_TOKEN` in `config.h`. The new firmware derives `/camera/frame` from that server address. Keep secrets private.
4. Select **AI Thinker ESP32-CAM**, with PSRAM and a suitable large application partition. Start upload speed at 115200. The camera driver detects OV3660/OV2640; the board pin map stays AI-Thinker.
5. **Before uploading, power off and remove any DFPlayer TX-to-GPIO15 wire.** GPIO15 now drives the red LED. Wire the separate green/red LEDs using [HARDWARE_WIRING.md](HARDWARE_WIRING.md), each with its own 330 Ohm resistor. GPIO12 also needs its 10 kOhm pull-down.
6. Upload using a suitable adapter with 3.3 V UART logic and stable 5 V power. For manual flashing: GPIO0 to GND, reset, upload, remove GPIO0-GND and reset to run. Open Serial Monitor at 115200.
7. On this prepared laptop the new OpenCV/NumPy packages are installed. For a copied/reinstalled system, run `install_offline.cmd` to install the updated bundled wheels. Stop the old server and restart `start.cmd` before testing the new firmware.
8. Register a student, set today's class start time, and present a current website-issued QR. The firmware now uploads native JPEG continuously; the laptop decodes/verifies the card and returns the LCD/audio/LED result. Scanning works with the dashboard closed. No internet is needed.

Camera initialization failure stops with a red indicator. A failed or timed-out request never produces a green success indication. A timeout may occur after the database commits; rescan to check, with **Already recorded** confirming the existing attendance. There is no offline queue. The laptop must remain running and reachable.

## Scanner, LCD, audio and status lights

The ESP32 captures native VGA (640 x 480) JPEG frames with two PSRAM buffers and sends them to `/camera/frame`, targeting one upload every 250 ms. Actual rate depends on camera, Wi-Fi and laptop decoding time. It no longer runs the old grayscale QR decoder or software JPEG conversion on the board. The server validates JPEG dimensions (maximum 800 x 600) and size (256 KiB), decodes locally with OpenCV, verifies the existing signed credential and records attendance. Other application requests retain the 4096-byte limit. No cloud decoding or image recording is used.

| Result | LCD | Audio | Light |
|---|---|---|---|
| Newly saved attendance | Student name, then Present/Late/Absent | Track 1 | Green |
| Already recorded | Student name, then Already recorded | Track 2 | Red |
| Invalid/revoked/unsupported card | Invalid QR card | Track 3 | Red |
| Unset class time, class not started/ended, connection/server error | Not saved + reason | Track 4 (busy errors stay quiet) | Red |
| QR pattern detected but unreadable | Unreadable QR / Hold card steady | None | Red |
| No QR visible | Ready to scan | None | Off |

Lights normally stay on about 2.5 seconds. Green confirms a database save, including a saved Late or Absent status; it does not imply the student was on time. A five-second same-card cooldown prevents per-frame repeated database/audio events. Remove a card after its result. Different students can scan immediately. The supported hardware is two separate LEDs; never connect LEDs without series resistors. The white onboard flash is not used.

## Live scanner camera preview

The signed-in dashboard has a medium **Scanner camera** panel beside attendance. Choose **Start preview** to see the same native JPEG frames used for laptop decoding; **Stop preview** stops viewing, while attendance scanning continues. Preview refresh is capped at approximately two frames per second. The panel remains capped at 440px wide on smaller screens. Hidden tabs pause browser updates.

Only the latest frame and recent scanner feedback are held in server RAM. Administrator authentication is required to read the preview; the device token is not placed in the browser. A stale frame is hidden and retried. The supplied single-process Waitress server is required for this in-memory preview. An invalid/unreadable frame never produces a successful attendance indication.

### Aim, orientation and automatic records

Keep the whole website-issued QR and its white border inside the aiming guide. Use even lighting, avoid glare, adjust distance until the small squares look sharp and hold still. The laptop decoder also retries a mirrored image when it has found a pattern it cannot decode. Software decoding cannot recover missing image detail from an out-of-focus camera; physical focus, exposure and actual scan rate still need board testing.

`CAMERA_VFLIP` and `CAMERA_HMIRROR` both default to `1` for the reported upside-down mounting, correcting the actual sensor image. Set both to `0` and upload again if you physically rotate the camera to the opposite orientation. `CAMERA_FRAME_SIZE` defaults to VGA and should not exceed SVGA (800 x 600) for the current server bounds. `CAMERA_JPEG_QUALITY` defaults to 12; lower numbers mean higher JPEG quality in the camera driver.

Attendance rows, counts and recent feedback update in place about every two seconds, preserving camera controls, search and typed class time. Without JavaScript use **Refresh records**. The dashboard reports saved/duplicate/rejected/unreadable outcomes. Serial Monitor logs the sensor PID, server address and HTTP errors, never the QR credential, device token or Wi-Fi password.

Scanning records check-in for an existing student; it does not register students. Select today's attendance date and set its class start time before a test. Present applies within the first 15 minutes; later scans follow the Late/Absent rules.

## Tests and audit

From the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s python/tests -t python -p 'test_*.py' -v
```

All tests use temporary databases. They cover every declared endpoint, authentication, CSRF, validation, HTML escaping, CSV formula protection, safe database failures, storage persistence, foreign keys, concurrent duplicates, and the local midnight boundary. See [AUDIT.md](AUDIT.md) for the actual verification results and outstanding limitations. Hardware compilation and physical bench tests are separate from Python endpoint tests.

There is one class schedule and one check-in per student per day. Multiple class sessions, check-out, automatic absence calculations, offline queue, individual teacher accounts and presenter identity verification are not included. Static QR codes can be copied. The dashboard refreshes saved attendance automatically about every two seconds.

## Registration, printing and attendance

1. Open the website and sign in at `/login`; the administrator workspace is `/dashboard`.
2. Enter a student ID and full name; click **Register & create QR**.
3. The card opens automatically. Click **Print QR card** to print or save as PDF, or **Download QR image** for a PNG. Existing students have a **Print QR card** link in the registry.
4. Return to the dashboard, choose the attendance date, and save the **Class start time** for that date in Philippine time (UTC+08:00).
5. Present the printed QR to the ESP32-CAM. It uploads a JPEG frame; OpenCV decodes the signed credential and Flask verifies its signature, resolves the student name, saves attendance/status, and returns the LCD result.

The QR encodes a version prefix, student ID, and HMAC-SHA256 signature. It does not contain a name, URL, server secret, device token or signing secret. Images are generated locally with [python-qrcode](https://github.com/lincolnloop/python-qrcode); no student data is sent to an external QR service. Print at 100% scale on white paper, preserving the white border. Camera focus, lighting and print quality still require bench verification.

## Class time and late rules

| Scan time relative to class start | Result |
|---|---|
| Before start | Not saved; LCD shows class not open |
| Start through 14 minutes 59 seconds | Saved as **Present** |
| Exactly 15 minutes through 39 minutes 59 seconds | Saved as **Late** |
| Exactly 40 minutes or more | Saved as **Absent** |
| No class time set for today | Not saved; LCD asks for class time |

For an 08:00 start, 08:14:59 is Present; 08:15 through 08:39:59 is Late; 08:40 and later is Absent. Class times are set separately for each date. After the first check-in, the configured start time is locked so later edits cannot change the meaning of existing statuses. At 40 minutes the first scan is saved as Absent. Students who never scan are not automatically marked absent, and a duplicate scan does not change their earlier saved status. Saved scans appear automatically on the dashboard. CSV reports include a **Status** column.

Existing databases are upgraded without deleting records. Earlier attendance without a schedule is shown as **Not assessed** rather than being retroactively labeled late. An initial class time can still be set for a date containing these legacy records; their original status stays unchanged.

**Upload the updated `.ino` again and reprint all old plain-ID QR cards.** The firmware now accepts signed credentials and displays the student name above Present/Late/Absent. Track 1 remains the generic attendance-recorded audio for all saved outcomes; no new audio file is required. Firmware compilation passed; physical testing remains outstanding. See AUDIT.md for verification details.

## Signed cards and lost-card replacement

Each student has an independent random 256-bit card secret in SQLite's `student_cards` table. The server uses [HMAC-SHA256](https://docs.python.org/3/library/hmac.html) to sign the versioned student ID and uses constant-time comparison to verify it. This requires no internet or additional Python dependency. Signing secrets stay on the server; the ESP32 only forwards the scanned credential.

Knowing the payload format or a student ID does not allow creating a new valid signature. The student may choose any QR generator, but unsigned or altered content is rejected.

**An exact copy of a valid signed QR is still valid.** A static signature authenticates the issued data; it cannot identify the original piece of paper or prove who is holding it. Supervise scanning if proxy attendance is a concern.

For a lost or copied card, open that student's **Print QR card** page, expand **Lost or copied QR card?**, and click **Replace QR card**. This rotates only that student's secret. The old card and every copy of it are rejected immediately, even if the student already checked in. Print the newly generated replacement. Normal reprinting does not rotate the credential.

The existing database is migrated without deleting students or attendance. Earlier `on-time` labels become `present`; historical Late records are retained rather than retroactively relabeled Absent. Card secrets persist across restarts and session-key changes. Back up the complete SQLite database to preserve current card validity; restoring an older database also restores that snapshot's card secrets/revocations.

**Upgrade requirements:** legacy plain-ID QR cards are deliberately rejected after this change. Use the new firmware and new website-issued signed QR cards together.

## Upstream references

- [Espressif camera driver and OV3660 support](https://github.com/espressif/esp32-camera)
- [OpenCV QR decoder](https://docs.opencv.org/4.x/de/dc3/classcv_1_1QRCodeDetector.html)
- [DFRobot DFPlayer example](https://github.com/DFRobot/DFRobotDFPlayerMini/blob/master/examples/FullFunction/FullFunction.ino)
- [Espressif Arduino installation](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)


## Interface and landing page

The public landing page includes an animated CSS 3D scanner/card scene, workflow explanation and class-time rules. Reduced-motion preferences disable decorative motion. The dashboard includes searchable attendance/student tables, real counts for the selected date, explicit late badges, class scheduling and printable cards. Login has a show/hide password button.

Typography is self-hosted, so the app does not require online fonts, a JavaScript CDN or a frontend build step. Edit Jinja templates under `python/attendance/templates`, styles in `static/style.css` and enhancements in `static/app.js`. [DESIGN.md](DESIGN.md) records the visual system and the Superdesign reference.

### Optional class end time and camera-only testing

In **Class schedule**, set a start time and optionally an end time for the selected date, then choose **Save class schedule**. Times use Philippine time (UTC+08:00). End time must be later than start on the same date; overnight sessions are not supported. Blank end time means no closing time, preserving existing schedules. At the exact end time and afterward, new check-ins return `410 Class ended` without saving attendance. Already saved attendance still returns `Already recorded`. The normal Present/Late/Absent rules apply only while check-in is open.

Start time locks after the first check-in. You can still change or clear end time; this only affects future scans and does not change earlier records. Restart `start.cmd` after updating so the database gains the optional end-time column automatically; existing data is retained.

The firmware probes the configured LCD address once at startup. With no LCD attached, it skips LCD initialization and writes, and continues scanning with Serial Monitor output. Power off before adding the LCD, then restart to detect it. No firmware change is needed when using the documented pins and configured address. Re-upload the updated sketch for this behavior and the `Class ended` display. This does not fix a separate `Check server` network/token error; consult the HTTP code in Serial Monitor.
