#pragma once
// Both flips rotate the actual sensor image 180 degrees for this mounting.
// Set both to 0 if you physically rotate the camera to the opposite orientation.
#define CAMERA_VFLIP 1
#define CAMERA_HMIRROR 1
// Native JPEG capture. The laptop performs QR decoding; PSRAM is required.
#define CAMERA_FRAME_SIZE FRAMESIZE_VGA
#define CAMERA_JPEG_QUALITY 12
#define CAPTURE_INTERVAL_MS 250
#define LED_GREEN 12 // each LED: GPIO -> 470 ohm resistor -> anode; cathode -> GND
#define LED_RED 15   // DFPlayer TX must be disconnected from this pin
#define WIFI_SSID "testing"
#define WIFI_PASSWORD "A06C7FD1"
#define SERVER_URL "http://192.168.254.119:5000/scan"
#define DEVICE_TOKEN "YCpHFqs8Ri1NJXWfMD-GH46g71RCCUe2"
// AI-Thinker ESP32-CAM only. Onboard microSD must NOT be used.
#define LCD_SDA 13
#define LCD_SCL 14
#define LCD_ADDRESS 0x27
#define MP3_TX 2  // ESP32 output, through 1k resistor to DFPlayer RX
#define MP3_VOLUME 22
