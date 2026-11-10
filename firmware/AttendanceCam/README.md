# ESP32-CAM attendance scanner: detailed wiring and assembly

This guide matches the current [AttendanceCam.ino](AttendanceCam.ino) and [config.h](config.h). It covers the AI-Thinker ESP32-CAM with an OV3660 camera, a 16x2 I2C LCD, DFPlayer Mini and speaker, and two separate status LEDs.

You can continue testing with only the ESP32-CAM. Add the components later using these assignments; the current firmware already sends their commands. A different LCD address or different pin assignment requires changing `config.h` and uploading again.

The ESP32 sends JPEG images over local Wi-Fi to the laptop. The laptop decodes the QR, verifies the student card, saves attendance and returns a result. The ESP32 then updates the LCD, audio and lights. The laptop/server must be running; internet is not required.

For an overview, open the [wiring diagram](../../hardware-wiring.svg). The [project wiring reference](../../HARDWARE_WIRING.md) includes the checked manufacturer links.

## 1. Parts and tools

| Quantity | Part | Notes |
|---:|---|---|
| 1 | AI-Thinker ESP32-CAM with PSRAM and OV3660 camera | Keep the existing camera ribbon connected. OV2640 is also supported by the camera driver. |
| 1 | 16x2 HD44780-compatible LCD with I2C backpack | Backpack usually exposes GND, VCC, SDA and SCL. Read its actual labels. Firmware address defaults to `0x27`. |
| 1 | Bidirectional I2C level shifter | Needs a 3.3 V low side, 5 V high side, ground and at least two corresponding channels. |
| 1 | DFRobot DFPlayer Mini DFR0299 or a verified compatible module | Pin layouts and clone behavior can differ. Identify pins from the module documentation. |
| 1 | Passive speaker compatible with the exact DFPlayer speaker output | Connect directly across SPK1 and SPK2. Confirm the permitted speaker impedance and power in the module documentation. |
| 1 | Supported microSD card for the DFPlayer | This card goes in the DFPlayer, not the ESP32-CAM. Prepare it as described below. |
| 1 each | Separate green LED and red LED | This guide assumes ordinary two-lead LEDs, not a powered LED module. |
| 2 | 330 Ohm resistors | One series resistor for each LED. Do not share one resistor between both LEDs. |
| 1 | 1 kOhm resistor | Series resistor between ESP32 GPIO2 and DFPlayer RX. |
| 1 | 10 kOhm resistor | Pull-down between GPIO12 and GND; separate from the green LED's series resistor. |
| 1 | Stable regulated 5.0 V supply | A 5 V / 2 A supply is a starting point for this assembly; verify adequate power under camera, Wi-Fi and speaker load. |
| As needed | Breadboard, jumper wires and suitable power connections | Check whether breadboard power rails are split in the middle. |
| 1 | Multimeter | Check supply voltage, polarity, continuity with power off, and component values. |
| 1 | Suitable upload adapter | ESP32-CAM-MB or USB-UART with 3.3 V serial logic. See the upload section before connecting power. |

## 2. Important connections to understand first

**Disconnect all power and USB cables before adding, moving or removing wires.** Verify the labels on the actual hardware rather than copying a physical pin position from an unrelated board photo.

- The shared supply rail is **5 V**, connected only to the components' power inputs listed below.
- ESP32 GPIO signals are **3.3 V**. Do not connect a 5 V signal or power rail to a GPIO.
- ESP32 `3V3` goes to the level shifter's `LV` reference. It does not supply the whole assembly.
- All modules need a common GND, including the USB-UART adapter when it is connected.
- The LCD's I2C signals pass through the level shifter. A 5 V backpack may pull its signals up to 5 V.
- **DFPlayer TX stays unconnected.** Older wiring connected TX to GPIO15; remove that wire. GPIO15 is now the red LED output.
- **GPIO12 must remain low during reset.** Use the green LED circuit and 10 kOhm pull-down below. Do not connect GPIO12 to 3.3 V or 5 V through an LED module or pull-up.
- Keep the ESP32-CAM's onboard microSD slot empty. Its pins are being reused.
- Do not substitute GPIO16 or GPIO17; the AI-Thinker board uses these for PSRAM. GPIO4 is intentionally unused to avoid switching the board's bright white flash.

## 3. Complete connection table

The table uses GPIO numbers, not physical header positions.

| From | Through / intermediate connection | To |
|---|---|---|
| Regulated supply +5 V | Shared 5 V rail | ESP32-CAM `5V` |
| Shared 5 V rail | Direct power connection | LCD `VCC` |
| Shared 5 V rail | Direct power connection | DFPlayer `VCC` |
| Shared 5 V rail | Direct reference connection | Level shifter `HV` |
| Supply GND | Shared ground rail | ESP32-CAM GND, LCD GND, DFPlayer GND and shifter GND |
| ESP32-CAM `3V3` | Direct reference connection | Level shifter `LV` |
| ESP32 GPIO13 | Shifter `LV1` -> corresponding `HV1` | LCD `SDA` |
| ESP32 GPIO14 | Shifter `LV2` -> corresponding `HV2` | LCD `SCL` |
| ESP32 GPIO2 | **1 kOhm series resistor** | DFPlayer `RX` |
| DFPlayer `TX` | **No wire** | Leave unconnected |
| DFPlayer `SPK1` | One speaker wire | One speaker terminal |
| DFPlayer `SPK2` | Other speaker wire | Other speaker terminal |
| ESP32 GPIO12 | **330 Ohm series resistor** | Green LED anode (+) |
| Green LED cathode (-) | Direct wire | Common GND |
| ESP32 GPIO12 | **10 kOhm pull-down resistor** | Common GND |
| ESP32 GPIO15 | **330 Ohm series resistor** | Red LED anode (+) |
| Red LED cathode (-) | Direct wire | Common GND |

The shifter's channel labels may instead be `L1/H1`, `A1/B1`, or another naming scheme. Use the corresponding low/high pair for the same channel. Check its documentation before assuming which side is which.

## 4. Build the power and ground connections

1. Leave the supply disconnected from the assembly. Measure its output and confirm **5.0 V DC** and correct polarity.
2. Make one 5 V distribution rail and one ground rail. If a breadboard rail is split, join only matching sections: 5 V to 5 V, GND to GND.
3. Connect supply GND and ESP32-CAM GND to the ground rail.
4. Connect supply +5 V to the 5 V rail and ESP32-CAM `5V` to that rail.
5. Later, connect LCD VCC, DFPlayer VCC and shifter HV to the same 5 V rail. Their grounds join the ground rail.
6. Connect ESP32 `3V3` only to the shifter LV reference for the wiring in this guide.

Do not use a USB-UART adapter's 3.3 V output to power the camera and speaker assembly. Do not join an external 5 V supply and a USB adapter's power output unless that exact power arrangement is designed to handle both sources.

Test the ESP32-CAM by itself first. Power off again before adding each following component.

## 5. Connect the 16x2 I2C LCD

### Power and level-shifter references

```text
5 V rail -------- LCD VCC
5 V rail -------- shifter HV
ESP32 3V3 ------- shifter LV
GND rail -------- LCD GND and shifter GND
```

### I2C signals

```text
ESP32 GPIO13 ---- shifter LV1 <-> HV1 ---- LCD SDA
ESP32 GPIO14 ---- shifter LV2 <-> HV2 ---- LCD SCL
```

1. Identify GND, VCC, SDA and SCL on the backpack. Do not assume their order.
2. Connect the power and shifter reference wires above.
3. Connect GPIO13 to the low side of channel 1 and its matching high side to LCD SDA.
4. Connect GPIO14 to the low side of channel 2 and its matching high side to LCD SCL.
5. Recheck that LV is 3.3 V and HV is 5 V before powering up.
6. Power up and slowly adjust the backpack's contrast potentiometer until text becomes visible. A lit backlight alone does not confirm correct I2C communication.

The current setting is:

```cpp
#define LCD_ADDRESS 0x27
```

If the exact backpack uses another address, such as `0x3F`, update that value in `config.h` and upload again. If the address is unknown, identify it with an I2C scanner configured for GPIO13/GPIO14 or from the backpack documentation. Changing the LCD contrast does not change its I2C address.

After startup, expect a ready/connection message. After a saved scan, the first row shows the shortened student name and the second shows Present, Late or Absent. Names are limited to 16 printable characters on this display.

## 6. Connect the DFPlayer Mini and speaker

### Use the resistors you already have

| Marking in your resistor set | Use in this assembly | Quantity |
|---|---|---|
| **330R** (330 Ohm) | One series resistor for the green LED and one for the red LED | 2 |
| **1K** (1,000 Ohm) | ESP32 GPIO2 to DFPlayer RX | 1 |
| **10K** (10,000 Ohm) | Separate pull-down from GPIO12 to GND | 1 |

The LED diagrams now use your **330R** resistors. The previously documented 470 Ohm value also works for these ordinary indicator LEDs. No firmware change is needed for this substitution. Resistors have no positive or negative end. Each LED needs its own resistor: long leg (anode) toward the GPIO through the resistor, short leg (cathode) to GND. Keep the separate 10K pull-down on GPIO12.

### DFPlayer connections

With power off, connect the module using its printed pin labels. **DFPlayer RX** receives commands from **ESP32 GPIO2** through your **1K** resistor. Leave **DFPlayer TX** disconnected; GPIO15 belongs to the red LED. The speaker connects across **SPK1 and SPK2**, with neither speaker wire going to GND.

```text
5 V rail ------------------------ DFPlayer VCC
GND rail ------------------------ DFPlayer GND
ESP32 GPIO2 ---- 1 kOhm ---------- DFPlayer RX
DFPlayer TX --------------------- NO CONNECTION

DFPlayer SPK1 ------------------- speaker terminal 1
DFPlayer SPK2 ------------------- speaker terminal 2
```

1. Identify the DFPlayer's VCC, GND, RX, TX, SPK1 and SPK2 labels using its own pin diagram.
2. Connect VCC to 5 V and GND to the common ground.
3. Connect GPIO2 through the **1 kOhm series resistor** to DFPlayer RX. ESP32 TX goes to DFPlayer RX; do not connect TX to TX.
4. **Leave DFPlayer TX unconnected.** Remove any existing wire between it and GPIO15.
5. Connect the passive speaker between SPK1 and SPK2. Neither speaker terminal connects to GND or 5 V.
6. Leave the DFPlayer's unused control pins and DAC outputs unconnected for this setup. SPK1/SPK2 are the outputs used here.
7. Insert the prepared microSD card with power off, then power up and test a scan.

The firmware sends UART commands at 9600 baud and uses volume **22 out of 30**. It uses transmit-only control without acknowledgments. A startup message saying TX-only is enabled confirms the firmware configuration, not that a DFPlayer or card was detected.

### Prepare the audio card

Use a card and FAT16/FAT32 format supported by the exact DFPlayer module. Before formatting a card that contains other files, back up anything you want to keep; formatting erases it.

Create an `mp3` folder at the card root and supply these actual MP3 recordings:

```text
microSD root/
  mp3/
    0001.mp3
    0002.mp3
    0003.mp3
    0004.mp3
```

| File | Event | Suggested recording |
|---|---|---|
| `mp3/0001.mp3` | Attendance saved | "Attendance recorded." |
| `mp3/0002.mp3` | Already recorded | "Your attendance is already recorded." |
| `mp3/0003.mp3` | Invalid or revoked card | "Invalid QR card. Please ask your teacher." |
| `mp3/0004.mp3` | Attendance not saved, including class ended/not started | "Attendance was not saved. Please try again." |

Keep the four-digit filenames and `.mp3` extension. Check that Windows has not hidden an extra extension such as `0001.mp3.mp3`. Audio recordings are not included in this project. The ESP32-CAM's card slot is not used to play these files.

### Test the DFPlayer after wiring

1. With power off, check the 5 V supply, common GND, GPIO2 -> 1K -> RX connection, disconnected TX, speaker terminals and prepared microSD card.
2. Power up the full assembly and start the laptop server. Set a class schedule that is currently open.
3. Scan a current website-issued card for a student who has not checked in today. Confirm the saved row on the dashboard, green LED and `0001.mp3` playback.
4. Remove the card, wait more than five seconds, then scan again. Confirm Already recorded, red LED and `0002.mp3` playback. Rapid repeats are suppressed, so an immediate repeat may stay quiet.
5. If attendance saves but there is no sound, check the card folder/filenames and actual MP3 content, the 1K resistor connection to RX, speaker wiring and power supply. A TX-only startup message is not proof that the module is working.

Missing or incorrectly named audio does not prevent attendance from being saved. Because there is no return UART connection, check the card, wiring and speaker physically if the module is silent.

## 7. Connect the green LED and its pull-down

An ordinary LED has an anode (+) and cathode (-). On many new through-hole LEDs, the longer lead is the anode and the flat side of the body marks the cathode. If leads were trimmed or markings differ, confirm polarity with its documentation or a multimeter's diode test while disconnected.

The green circuit has **two separate branches from GPIO12**:

```text
ESP32 GPIO12 ---- 330 Ohm ---- green LED anode (+)
      |                       green LED cathode (-) ---- GND
      |
      +--------- 10 kOhm ------------------------------ GND
```

1. Connect one end of a 330 Ohm resistor to GPIO12.
2. Connect its other end to the green LED anode.
3. Connect the green LED cathode to common GND.
4. Separately, connect a 10 kOhm resistor directly between GPIO12 and GND.

**The 10 kOhm resistor is a pull-down, not another series resistor in the LED branch.** It keeps the GPIO12 reset strap low. Never connect that resistor to VCC, and never replace this circuit with an LED module that pulls GPIO12 high at reset.

GPIO12 going high after startup turns the green LED on. It means the server confirmed a newly saved attendance record. A saved Late or Absent result also lights green because the record was saved successfully.

## 8. Connect the red LED

```text
ESP32 GPIO15 ---- 330 Ohm ---- red LED anode (+)
                             red LED cathode (-) ---- GND
```

1. Confirm the DFPlayer TX-to-GPIO15 wire has been removed.
2. Connect a second, independent 330 Ohm resistor from GPIO15 to the red LED anode.
3. Connect the red LED cathode to common GND.

Do not share the green LED's resistor. Do not connect the red LED to GPIO4: that pin also operates the board's bright white flash and is not the configured red indicator.

GPIO15 is also a strapping pin. If the board fails to boot after adding external circuitry, power off and temporarily disconnect the external LED and DFPlayer signal wiring, then test the board alone. Do not change pins without updating the firmware and checking what the new pins are used for.

## 9. Upload and Serial Monitor connections

### Bare USB-UART adapter with an external 5 V supply

Use an adapter whose serial signals are 3.3 V logic.

| Adapter / connection | ESP32-CAM connection |
|---|---|
| Adapter TXD | U0R / GPIO3 |
| Adapter RXD | U0T / GPIO1 |
| Adapter GND | Common GND |
| Adapter VCC / power output | **Leave unconnected** when the external supply powers the board |
| External regulated 5 V | ESP32-CAM 5V |
| GPIO0 | Temporarily connect to GND to enter upload mode |

Upload sequence:

1. Power off before changing jumpers.
2. Connect the crossed serial signals, shared ground and board power as above.
3. Connect GPIO0 to GND.
4. Power/reset the board and upload with **AI Thinker ESP32-CAM** selected in Arduino IDE.
5. After upload, power off, remove the GPIO0-to-GND jumper, then power/reset again to run normally.
6. Open Serial Monitor at **115200 baud**. GPIO0 must be released for normal camera operation.

If using an ESP32-CAM-MB board, follow its own documented upload/power arrangement. Do not add a second 5 V supply without checking how that adapter connects power. The normal ESP32 serial monitor can remain connected with GPIO0 released and the power arrangement kept correct.

## 10. Assemble and test in stages

Power off between every stage. The LCD is optional: startup probes its configured address once and skips all LCD commands if it is absent. Serial Monitor still shows scan results. After connecting the LCD, restart the board to detect it; the documented pins and configured address need no code change.

| Stage | Connected hardware | What to verify |
|---|---|---|
| 1 | ESP32-CAM only | Camera initializes, Wi-Fi connects, laptop server receives frames, and a current website-issued card saves attendance. |
| 2 | Add level shifter and LCD | No abnormal heating; readable startup text after contrast adjustment; saved results appear on both rows. |
| 3 | Add LEDs and resistors | GPIO12 has its pull-down; saved attendance lights green; a later duplicate/rejected scan lights red. |
| 4 | Add DFPlayer, card and speaker | Correct track plays for each result; speaker load does not reset the camera. |
| 5 | Full assembly | Repeat startup and several different student scans; check camera, Wi-Fi, display, lights and audio together. |

Before a scan test, run `start.cmd`, keep the laptop and ESP32 on the same reachable Wi-Fi, set today's class start time and use a current card printed by this website. Keep the laptop's current Wi-Fi IP in `SERVER_URL` and the device token matched to the server. No internet is required.

Select today's date on the dashboard. Attendance rows update automatically. Within the first 15 minutes after class start, a saved check-in is Present; later scans follow the Late/Absent rules. A QR scan does not register a new student.

Move a card away after its result. The server suppresses rapid repeats of the same credential for five seconds, so an immediate repeat may produce no second sound or light event. A different student's card can be processed immediately. The scanner continues working when camera preview is stopped or the dashboard is closed.

## 11. Expected output behavior

| Situation | LCD / Serial result | Light | Audio |
|---|---|---|---|
| Newly saved attendance | Student name; Present, Late or Absent | Green, about 2.5 seconds | Track 1 |
| Already recorded today | Student name; Already recorded | Red, about 2.5 seconds | Track 2 |
| Invalid, revoked or unsupported card | Invalid QR card | Red | Track 3 |
| Class start time missing | Not saved; Class time unset | Red | Track 4 |
| Class has not started | Not saved; Class not open | Red | Track 4 |
| Class has ended | Not saved; Class ended | Red | Track 4 |
| HTTP connection/server/token failure | Not saved; relevant error | Red | Track 4; busy retries stay quiet |
| Wi-Fi disconnected | Scanner offline; Connecting WiFi | Red when the state changes | No audio |
| QR pattern found but unreadable | Unreadable QR; Hold card steady | Red when shown | No audio |
| No card visible | Ready to scan / Aim student QR | Off after any prior indication expires | No audio |
| Fatal camera/PSRAM initialization failure | Camera stopped | Red stays on | No audio |

Unreadable-card messages are rate-limited and do not immediately overwrite a just-displayed scan result. Green confirms a saved database record, not a particular attendance status or verified audio playback.

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| Board stops booting after adding green LED | Power off. Check the GPIO12-to-GND 10 kOhm pull-down and that nothing pulls GPIO12 to VCC. Test the board with external signal wires disconnected. |
| Upload fails | Check GPIO0 upload jumper, reset sequence, correct serial port, crossed TX/RX, shared GND and 3.3 V UART logic. Disconnect external strapping-pin circuits while powered off if needed. |
| Board uploads but will not run the camera | Remove GPIO0 from GND and reset. Confirm PSRAM and the correct board selection. |
| LCD backlight on, no readable letters | Adjust contrast gradually. Check address, GND, 5 V power, GPIO13/14 and shifter LV/HV/channel matching. |
| LCD displays blocks or inconsistent characters | Check contrast, I2C address, SDA/SCL assignment, loose wires, shared ground and voltage levels. |
| No sound although a record is saved | Confirm supported card format, `mp3/0001.mp3` filename, actual MP3 content, GPIO2 -> 1 kOhm -> RX and speaker across SPK1/SPK2. Firmware cannot detect missing playback over TX-only control. |
| Wrong sound plays | Recheck four-digit filenames and the event/file table. Test the actual module/card with the documented `playMp3Folder` layout. |
| LEDs never light | Check polarity, individual 330 Ohm resistors, common ground and exact GPIO12/GPIO15 connections. Test an actual saved/rejected event, not an empty camera view. |
| Red LED behavior is strange after adding audio | Confirm DFPlayer TX is completely disconnected from GPIO15. It must not drive the LED output. |
| White onboard flash switches instead of red LED | Check for an accidental GPIO4 connection. Configured red is GPIO15. |
| Camera resets when sound starts | Check regulated supply capacity, wiring resistance, common ground and speaker compatibility under load. Do not power the assembly through the adapter's 3.3 V output. |
| Camera sees the QR but attendance is absent from the table | Read the dashboard feedback and Serial Monitor. Check actual Saved result, selected date, class time, current signed card, server address and token. A visible QR alone does not confirm a save. |
| Camera image is upside-down | Check `CAMERA_VFLIP` and `CAMERA_HMIRROR` in `config.h`. Both default to 1 for the reported mounting; changing them requires uploading again. |

## 13. Before the first full power-up

- [ ] All power and USB cables were disconnected while wiring.
- [ ] Supply output was measured at 5.0 V and polarity checked at every module.
- [ ] All grounds are common, and breadboard rail breaks are understood.
- [ ] No 5 V signal reaches an ESP32 GPIO.
- [ ] LCD signals pass through the shifter, with LV = 3.3 V and HV = 5 V.
- [ ] GPIO2 connects through 1 kOhm to DFPlayer RX; DFPlayer TX has no wire.
- [ ] The speaker connects only across SPK1/SPK2.
- [ ] Both LEDs have their own 330 Ohm series resistor and cathode connected to GND.
- [ ] GPIO12 has the separate 10 kOhm pull-down to GND and no external pull-up.
- [ ] The ESP32-CAM microSD slot is unused; audio card is in the DFPlayer.
- [ ] GPIO0 upload jumper is removed for normal operation.
- [ ] The board is not being powered from two conflicting sources.

This is a wiring reference for the stated modules, not a physical certification of the assembly. Firmware and server software checks have passed, but the complete LCD/audio/LED hardware has not been bench-tested by this project. If an actual module's labels or voltage specifications differ, resolve that difference before applying power.

## Optional class end time

On the dashboard, select the date and enter the start time plus an optional end time under Class schedule. End must be later than start on the same day, using Philippine time. Blank means no cutoff. New scans at or after end are rejected with HTTP 410 / Class ended, with no attendance saved. Earlier records remain unchanged, and a student already recorded still receives Already recorded. Start locks after the first saved scan; end can still be updated or cleared. Restart the updated laptop server and upload the updated firmware to enable the matching Class ended message.
