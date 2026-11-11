# Run QR Attendance without internet

This folder contains all 15 pinned runtime dependency wheels, including OpenCV and NumPy for laptop QR decoding and ReportLab for printable PDF card sheets. It supports **64-bit Windows with Python 3.13**. Python itself must already be installed; a Python installer is not included. Other operating systems or Python versions require matching dependency wheels.

## On this computer

Double-click `start.cmd` in the project root, then open http://localhost:5000. Keep the server window open while using the app.

The existing `.venv` is ready. The first normal startup creates:

- `python/instance/config.json`: administrator password, device token and session key. Username is `admin`.
- `python/attendance.db`: persistent students, class times and attendance.

Open the local settings file to get or change the login password. Restart the server after editing it. Set the ESP32 firmware's `DEVICE_TOKEN` to the same `ATTENDANCE_TOKEN` value. Environment variables override saved settings when present. Settings are excluded from Git; do not publish your installation's secrets.

## Reinstall without internet

1. Have 64-bit Python 3.13 installed on the destination Windows PC.
2. Copy the application folder, including `offline/wheels` and `offline/requirements-lock.txt`. Virtual environments should be recreated on the destination PC rather than copied.
3. Run `install_offline.cmd` in the project root. It creates `.venv` when missing and installs with `--no-index` from these files; no package server is used.
4. Run `start.cmd`.

Direct offline dependency command, if an environment is already available:

```powershell
.\.venv\Scripts\python.exe -m pip --disable-pip-version-check install --no-index --find-links=offline/wheels -r offline/requirements-lock.txt
```

Do not copy the original computer's `python/instance/config.json` if you want a new installation to generate independent credentials. Copy the existing database/settings only when intentionally migrating that installation, with the old service stopped.

## What offline means

No internet is needed for the landing page, fonts, animations, administrator login, student registration, signed QR creation/verification, lost-card revocation, schedules, Present/Late/Absent attendance or CSV reports. All app assets are local. Browser tests blocked external page requests and restricted server-side connections to loopback while exercising the workflow; no external requests were attempted.

The ESP32-CAM still needs a reachable **local Wi-Fi network** connecting it to the running Python server. A router or hotspot can provide that network without internet. Use the computer's LAN IPv4 address in firmware `SERVER_URL`; the computer's `localhost` address is not reachable from the ESP32. The scanner cannot save attendance when the computer/server is off or disconnected, and it does not have an offline queue.

The computer's clock determines the class time and date in UTC+08:00, so verify it when operating without internet time synchronization. Back up `python/attendance.db` with the service stopped.

Signed QR card secrets are stored in the SQLite database. Back it up with the service stopped. Plain-ID QR cards are rejected; upload the updated sketch and reprint old cards from the website. Revoking a lost card invalidates its copies, but an exact copy of a current signed card is indistinguishable from the original print.

## JPEG scanner update

The current ESP32 firmware uploads native JPEG frames continuously to the laptop. OpenCV decodes QR cards locally; preview viewing is optional. Run the updated offline installer on any existing copy that does not yet have OpenCV/NumPy, restart the Python service, and upload the new firmware together. The image endpoint accepts up to 256 KiB while ordinary form/scan requests keep their smaller limits. No downloaded recognition model or internet connection is needed at runtime.
