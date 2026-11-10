# QR Attendance Scanner Wiring Guide

For expanded assembly instructions and troubleshooting, see the **[detailed firmware wiring README](firmware/AttendanceCam/README.md)**.

## Scope and assumptions

This guide matches the current firmware in `firmware/AttendanceCam/config.h` and assumes:

- AI-Thinker ESP32-CAM with an OV3660 (or compatible OV2640) camera and PSRAM.
- A 16x2 HD44780-compatible LCD with an I2C backpack.
- A bidirectional I2C logic-level shifter.
- DFRobot DFPlayer Mini, SKU DFR0299, and a passive speaker suitable for its speaker output.
- Two separate indicator LEDs (green and red), each with its own 330 Ohm series resistor.
- One 10 kOhm pull-down resistor from GPIO12 to GND.
- One regulated 5.0 V supply with enough current for the camera, Wi-Fi and audio load.

The wiring image is [hardware-wiring.svg](hardware-wiring.svg). This is a reference for those exact assumptions, not proof that an unmarked clone uses the same connector layout or voltages. Before connecting power, compare the labels and datasheets for the actual modules. If a label, pin order, voltage, or board model differs, stop and resolve it first. Do not guess from physical position or wire color.

## Net-by-net connections

| Net | Connect | Important check |
|---|---|---|
| Regulated +5 V | ESP32-CAM `5V`, LCD backpack `VCC`, DFPlayer `VCC`, level-shifter `HV` | Measure the unloaded supply first; it must be 5.0 V, not 12 V. Confirm polarity at every module. |
| Common ground | ESP32-CAM `GND`, LCD `GND`, DFPlayer `GND`, shifter `GND`, USB-UART `GND` while flashing | All signal voltages need the same ground reference. |
| 3.3 V reference | ESP32-CAM `3V3` to shifter `LV` | This powers the low-voltage reference side; do not use it to power the ESP32-CAM or speaker. |
| LCD SDA | ESP32 GPIO13 -> shifter low-side channel 1 -> corresponding high-side channel 1 -> LCD `SDA` | Verify the channel labels on the shifter. Some boards mark these `L1/H1`; others use different names. |
| LCD SCL | ESP32 GPIO14 -> shifter low-side channel 2 -> corresponding high-side channel 2 -> LCD `SCL` | Do not swap SDA and SCL. Both I2C lines are bidirectional. |
| ESP32 to DFPlayer command | ESP32 GPIO2 -> **1 kOhm series resistor** -> DFPlayer `RX` | The resistor belongs in this direction, between ESP32 TX and DFPlayer RX. |
| DFPlayer TX | **Leave unconnected** | TX-only commands free GPIO15 for the red LED. Remove any previous TX-to-GPIO15 wire before uploading the new firmware. |
| Green LED | GPIO12 -> **330 Ohm** -> green LED anode (+); cathode (-) -> GND | Add a **10 kOhm pull-down from GPIO12 to GND**. Never pull GPIO12 high at reset: it is a flash-voltage strapping pin. |
| Red LED | GPIO15 -> **330 Ohm** -> red LED anode (+); cathode (-) -> GND | Do not also connect DFPlayer TX here. This is an active-high output after boot. |
| Speaker | One speaker lead to DFPlayer `SPK1`; the other to `SPK2` | This is a two-wire speaker output. Neither speaker lead goes to ground. Observe the DFPlayer speaker rating. |

The LCD backpack may pull SDA and SCL up to its supply voltage. This diagram therefore routes both signals through a bidirectional shifter. Do not bypass the shifter unless the exact backpack documentation confirms that its I2C lines are pulled up to 3.3 V and safe for the ESP32.

The sketch uses GPIO2, GPIO12 and GPIO15, which are ESP32 strapping pins. GPIO12 must stay low during reset for the board's normal flash-voltage selection; use the specified LED-to-GND circuit and 10 kOhm pull-down, never an LED module that pulls GPIO12 toward VCC. GPIO15 now drives the red LED, not UART input. If boot or flashing fails, power off and disconnect the external LED/DFPlayer signal wires before retrying. The onboard microSD slot remains unused. GPIO4 is intentionally unused so status indications do not switch the board's bright white flash. Do not use GPIO16/17, which the board needs for PSRAM.

## USB-UART flashing connections

For a bare USB-UART adapter, connect only its serial signals and ground. Keep the ESP32-CAM powered by the regulated 5 V supply during this method; do not connect the adapter's `VCC` pin. Confirm that the adapter's TXD/RXD logic is 3.3 V.

| USB-UART adapter | AI-Thinker ESP32-CAM | Use |
|---|---|---|
| `TXD` (3.3 V logic) | `U0R` / GPIO3 | Upload serial data into the board |
| `RXD` (3.3 V logic) | `U0T` / GPIO1 | Serial output from the board |
| `GND` | `GND` | Shared reference |
| `VCC` | **Leave unconnected** | Prevents a second power source |
| — | `GPIO0` to `GND` temporarily | Hold low, reset to enter upload mode; remove this jumper and reset to run normally |

If using an ESP32-CAM-MB adapter, use its documented power arrangement instead of adding a second 5 V source. Never connect two 5 V supplies together unless both devices explicitly support it.

## Before applying power

1. Disconnect all power and USB cables. Put the ESP32-CAM onboard microSD slot out of use; the current sketch reserves those pins for LCD/audio wiring.
2. Read each module's printed pin labels and confirm the model. Check the LCD backpack supply voltage, I2C pull-up voltage, shifter orientation, DFPlayer pin labels, and speaker rating against that exact module's documentation.
3. Set the bench supply to **5.0 V** and verify it with a multimeter before connecting it. Use a supply with adequate current for ESP32-CAM Wi-Fi/camera peaks and the DFPlayer speaker load; a weak supply may cause resets or unstable behavior.
4. With everything unpowered, check every wire against the net table and image. Check for reversed VCC/GND, loose strands, solder bridges, and accidental 5 V connections to GPIO pins. Verify that 5 V and ground are not shorted together.
5. Connect only the ESP32-CAM first. Power it from the regulated 5 V supply and verify the board's 5 V input and 3.3 V rail with a multimeter. Power off before adding the next module.
6. Add the shifter and LCD wiring while powered off. Recheck `LV=3.3 V`, `HV=5 V`, SDA-to-SDA and SCL-to-SCL, then power and check for abnormal heating or smell. Power off immediately if either occurs.
7. Add the DFPlayer and LEDs while powered off. Check `GPIO2 -> 1 kOhm -> DFPlayer RX`, leave **DFPlayer TX unconnected**, and connect the speaker only across `SPK1/SPK2`. Check each LED has its own 330 Ohm resistor and cathode to GND; GPIO12 also needs its 10 kOhm pull-down. Disconnect the old GPIO15-to-DFPlayer-TX wire before connecting the red LED there.
8. Before flashing, confirm adapter TX/RX are crossed correctly, grounds are common, adapter VCC is disconnected, and GPIO0 is grounded only for entering upload mode.
9. First power-up should be supervised with a multimeter and the ability to disconnect power immediately. If you cannot identify the module pins or safely measure the rails, have an electronics technician inspect the assembly before power is applied.

This checklist reduces wiring mistakes; it cannot certify an unidentified clone, damaged module, or power supply. No physical hardware was available for this project to validate physical wiring or safe operation. The firmware compile check is separate from a bench test.

## Firmware pin cross-check

These values are read from `firmware/AttendanceCam/config.h`:

| Firmware setting | Value | Connection represented here |
|---|---:|---|
| `LCD_SDA` | GPIO13 | LCD I2C SDA through shifter |
| `LCD_SCL` | GPIO14 | LCD I2C SCL through shifter |
| `LED_GREEN` | GPIO12 | 330 Ohm -> green LED anode; cathode -> GND; 10 kOhm pull-down to GND |
| `LED_RED` | GPIO15 | 330 Ohm -> red LED anode; cathode -> GND |
| `MP3_TX` | GPIO2 | ESP32 TX through 1 kOhm resistor into DFPlayer RX |
| `LCD_ADDRESS` | `0x27` | Backpack address; some backpacks use `0x3F` |

The firmware also needs the correct Wi-Fi SSID/password, local server IP and device token in `config.h`. Those settings do not change the physical wiring.

## References checked

- [AI-Thinker ESP32-CAM schematic](https://docs.ai-thinker.com/_media/esp32/docs/esp32_cam_sch.pdf) — board pin labels and onboard SD connections.
- [Espressif GPIO guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html) — strapping pins, GPIO limits and pin notes.
- [Espressif I2C guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2c.html) — bidirectional open-drain SDA/SCL lines.
- [DFRobot DFPlayer Mini DFR0299 page](https://wiki.dfrobot.com/dfr0299) and [datasheet](https://dfimg.dfrobot.com/wiki/20532/DFR0299_mp3-player-module_datasheet_V1.0.pdf) — supply range, UART, resistor note, and speaker output.

## Indicators and audio

- Green: the server confirmed a newly saved attendance record (Present, Late or Absent). It does not mean every accepted scan is on time.
- Red: duplicate/already recorded, invalid/revoked card, class not open or unset, unreadable QR pattern, or camera/network/server failure. An empty scene is idle, not a failure.
- Each indicator normally lights for about 2.5 seconds. Fatal camera initialization leaves the red indicator on.
- DFPlayer `/mp3/0001.mp3`: attendance saved; `0002.mp3`: already recorded; `0003.mp3`: invalid card; `0004.mp3`: not saved. Supply the recordings on the DFPlayer's own supported FAT-formatted card. No audio recordings are bundled.
- The LCD displays the student name followed by Present/Late/Absent after a saved scan, or a duplicate/error message. UART is TX-only, so firmware cannot verify that the audio module/card is present or playback succeeded.

The ESP32 captures native JPEG frames and sends them to the laptop even when the dashboard is closed. The laptop performs QR decoding and verification. No QR-reader Arduino library is needed for the current sketch. Test the camera/server first, then add the LCD, audio and LEDs with power off between changes.

## Resistors from your available set

Use two **330R** resistors (one per LED), one **1K** resistor (GPIO2 to DFPlayer RX), and one **10K** resistor (GPIO12 to GND pull-down). Resistors have no polarity. The previous 470 Ohm LED value is also acceptable; 330R needs no firmware change. Follow the [detailed DFPlayer wiring, audio card and testing instructions](firmware/AttendanceCam/README.md#6-connect-the-dfplayer-mini-and-speaker).
