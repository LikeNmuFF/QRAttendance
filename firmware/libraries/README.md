# Legacy QR reader archive ? not used by current firmware

The current `AttendanceCam.ino` uses Espressif native JPEG capture and laptop/OpenCV decoding. It does not include or require this library. The notes below are retained only for the earlier onboard-decoding firmware. Do not follow them for the current setup.

# Arduino QR reader dependency

Install `ESP32QRCodeReader-1.1.0-Arduino.zip` through **Sketch > Include Library > Add .ZIP Library...**, then restart Arduino IDE and verify `AttendanceCam.ino` with **AI Thinker ESP32-CAM** selected.

Source: [alvarowolfx/ESP32QRCodeReader](https://github.com/alvarowolfx/ESP32QRCodeReader), upstream `master` ZIP downloaded 2026-11-10. Its `library.properties` declares version 1.1.0. The upstream MIT license is included in the archive.

Local changes from upstream:

- `include/ESP32QRCodeReader.h` and `include/ESP32CameraPins.h` are also copied into `src/`. Arduino needs these headers there; the upstream layout separates them into `include` for PlatformIO.
- `#include <Arduino.h>` is prepended to `src/openmv/collections.c` and `src/quirc/decode.c`, supplying declarations for `ps_malloc`, `free` and `memcpy` required by the ESP32 3.2.0 toolchain. This follows the include already used in upstream `src/quirc/quirc.c`.

The public `onFrame` callback reuses the decoder-owned frame for the dashboard preview. The header defines `ATTENDANCE_CAMERA_PREVIEW` so the sketch can detect an outdated library. The decoded-payload copy now rejects lengths at or above the destination capacity before copying or appending a terminator. This archive is a local compatibility fix, not an upstream release.

Archive SHA-256: `0AAECB2AFA878CAFEB8AD8ADF726685656AA942005E99F15A5691EFE26A09D4C`.

Install **LiquidCrystal I2C** and **DFRobotDFPlayerMini** separately with Library Manager. WiFi, HTTPClient, Wire and the camera driver come with Espressif's ESP32 board package.

If Arduino still cannot find the header, check the sketchbook location in Preferences and confirm `libraries/ESP32QRCodeReader-master/src/ESP32QRCodeReader.h` exists there. Avoid an extra nested library folder. If another QR reader copy is installed, use verbose compilation output to identify which copy Arduino selects.

This archive addresses the specific decoder payload-copy bounds issue documented in [AUDIT.md](../../AUDIT.md). Hardware scanning, memory use under load, LCD and audio still need physical testing.

If you installed the earlier ZIP, close Arduino IDE, remove its `ESP32QRCodeReader-master` folder from your sketchbook `libraries` folder, and import this updated ZIP. Only remove that library folder. Then reopen and upload `AttendanceCam.ino`; the earlier ZIP does not provide the preview callback.

## Build verification (2026-11-10)

Arduino CLI successfully compiled `firmware/AttendanceCam/AttendanceCam.ino` with board `esp32:esp32:esp32cam`, Espressif core **3.2.0**, this library's source, **LiquidCrystal I2C 1.1.2**, and **DFRobotDFPlayerMini 1.0.6**. Updated preview firmware program storage: 1,065,966 bytes (33%); global variables: 64,068 bytes (19%). The LCD library reports an AVR architecture warning, which did not prevent compilation. No physical upload, scan, LCD or audio test was performed.
