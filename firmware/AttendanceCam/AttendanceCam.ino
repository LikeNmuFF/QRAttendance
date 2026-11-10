#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DFRobotDFPlayerMini.h>
#include <esp_camera.h>
#include "camera_pins.h"
#include "config.h"

LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);
HardwareSerial audioSerial(1);
DFRobotDFPlayerMini audio;
unsigned long resetAt = 0, lightsUntil = 0, capturedAt = 0;
bool lcdReady = false;

void writeLCD(String first, String second) {
  if (!lcdReady) return;
  lcd.clear(); lcd.setCursor(0, 0); lcd.print(first.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(second.substring(0, 16));
}

void lights(bool success) {
  digitalWrite(LED_GREEN, success ? HIGH : LOW);
  digitalWrite(LED_RED, success ? LOW : HIGH);
  lightsUntil = millis() + 2500;
}
void show(String first, String second, int track = 0, int indicator = 0) {
  writeLCD(first, second);
  Serial.println(first + ": " + second);
  if (track) audio.playMp3Folder(track);
  if (indicator) lights(indicator == 1);
  resetAt = millis() + 3000;
}

void startWiFi() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  // The ESP32 core owns retries; do not also reconnect from loop().
  WiFi.setAutoReconnect(true);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event != ARDUINO_EVENT_WIFI_STA_DISCONNECTED) return;
    uint8_t reason = info.wifi_sta_disconnected.reason;
    Serial.printf("WiFi disconnected: reason %u.\n", reason);
    if (reason == WIFI_REASON_NO_AP_FOUND)
      Serial.println("Configured hotspot not found. Check exact SSID, hotspot visibility and signal.");
    else if (reason == WIFI_REASON_AUTH_FAIL || reason == WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT || reason == WIFI_REASON_HANDSHAKE_TIMEOUT)
      Serial.println("WiFi authentication failed or timed out. Check hotspot password and security mode, then reset.");
  }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  Serial.printf("Scanning 2.4 GHz for hotspot '%s'...\n", WIFI_SSID);
  int networks = WiFi.scanNetworks(false, true);
  bool found = false;
  for (int i = 0; i < networks; i++) {
    if (WiFi.SSID(i) != WIFI_SSID) continue;
    found = true;
    bool open = WiFi.encryptionType(i) == WIFI_AUTH_OPEN;
    Serial.printf("Hotspot found: channel %d, signal %d dBm, %s.\n",
                  WiFi.channel(i), WiFi.RSSI(i), open ? "open network" : "password-protected");
    if (open && strlen(WIFI_PASSWORD))
      Serial.println("Hotspot has no password but firmware has one. Set WIFI_PASSWORD to an empty string only for an open hotspot.");
  }
  if (networks < 0) Serial.println("WiFi scan failed; still attempting the configured hotspot.");
  else if (!found) Serial.println("Hotspot not visible in this scan. Check exact name, 2.4 GHz mode, visibility and distance.");
  WiFi.scanDelete();
  WiFi.begin(WIFI_SSID, strlen(WIFI_PASSWORD) ? WIFI_PASSWORD : nullptr);
}


bool setupCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = CAMERA_FRAME_SIZE;
  c.jpeg_quality = CAMERA_JPEG_QUALITY;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) { Serial.printf("Camera init failed: 0x%x.\n", err); return false; }
  sensor_t *sensor = esp_camera_sensor_get();
  if (!sensor || sensor->set_vflip(sensor, CAMERA_VFLIP) != 0 ||
      sensor->set_hmirror(sensor, CAMERA_HMIRROR) != 0) return false;
  Serial.printf("Camera sensor PID 0x%x; JPEG %dx%d. Laptop decodes QR.\n",
                sensor->id.PID, resolution[CAMERA_FRAME_SIZE].width, resolution[CAMERA_FRAME_SIZE].height);
  return true;
}

void reportFailure(int code) {
  static int previousCode = 0;
  static unsigned long reportedAt = 0;
  if (code == previousCode && millis() - reportedAt < 5000) return;
  previousCode = code; reportedAt = millis();
  Serial.printf("Camera upload/attendance failed: HTTP %d.\n", code);
  if (code < 0 && code != -100) Serial.println("Connection error: " + HTTPClient::errorToString(code));
  if (code == -100) show("Camera stopped", "Check camera", 0, 2);
  else if (code == 401) show("Not saved", "Device token", 4, 2);
  else if (code == 403) show("Invalid QR card", "Use website card", 3, 2);
  else if (code == 422) show("Not saved", "Class time unset", 4, 2);
  else if (code == 425) show("Not saved", "Class not open", 4, 2);
  else if (code == 410) show("Not saved", "Class ended", 4, 2);
  else if (code == 413) show("Not saved", "Image too large", 4, 2);
  else if (code == 200 || code == 404) show("Not saved", "Update server", 4, 2);
  else if (code == 429) show("Not saved", "Server busy", 0, 2);
  else show("Not saved", "Check server", 4, 2);
}

void sendFrame() {
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) { reportFailure(-100); return; }
  if (frame->format != PIXFORMAT_JPEG || frame->len > 262144) {
    esp_camera_fb_return(frame); reportFailure(413); return;
  }
  String url = SERVER_URL;
  url = url.substring(0, url.lastIndexOf('/')) + "/camera/frame";
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(1500); http.setTimeout(2500);
  if (!http.begin(client, url)) {
    esp_camera_fb_return(frame); reportFailure(-1); return;
  }
  const char *headers[] = {"X-Scanner-State"};
  http.collectHeaders(headers, 1);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  int code = http.POST(frame->buf, frame->len);
  esp_camera_fb_return(frame);
  String state = http.header("X-Scanner-State");
  String result;
  if ((code == 201 || code == 409) && http.getSize() > 0 && http.getSize() <= 64)
    result = http.getString();
  http.end();
  if (code == 204) {
    static unsigned long warningAt = 0;
    if (state == "decode_failed" && !resetAt && (!warningAt || millis() - warningAt >= 3000)) {
      warningAt = millis();
      show("Unreadable QR", "Hold card steady", 0, 2);
    }
    return;
  }
  int split = result.indexOf('\n');
  String status = split > 0 ? result.substring(0, split) : "";
  String name = split > 0 ? result.substring(split + 1) : "";
  bool validName = name.length() > 0 && name.length() <= 16;
  for (unsigned int i = 0; i < name.length(); i++)
    if (name[i] < 32 || name[i] > 126) validName = false;
  if (code == 201 && validName && (status == "Present" || status == "Late" || status == "Absent")) {
    Serial.println("Attendance saved by laptop.");
    show(name, status, 1, 1);
  } else if (code == 409 && validName && status == "Already recorded") {
    show(name, "Already recorded", 2, 2);
  } else reportFailure(code);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_GREEN, OUTPUT); pinMode(LED_RED, OUTPUT);
  digitalWrite(LED_GREEN, LOW); digitalWrite(LED_RED, LOW);
  Wire.begin(LCD_SDA, LCD_SCL); Wire.setTimeOut(100);
  Wire.beginTransmission(LCD_ADDRESS);
  lcdReady = Wire.endTransmission() == 0;
  if (lcdReady) { lcd.init(); lcd.backlight(); }
  else Serial.println("LCD not detected; continuing with Serial Monitor only. Connect LCD and restart to enable it.");
  show("Attendance", "Starting...");
  // TX-only: DFPlayer TX must be disconnected; GPIO15 is the red indicator.
  audioSerial.begin(9600, SERIAL_8N1, -1, MP3_TX);
  audio.begin(audioSerial, false, false);
  audio.volume(MP3_VOLUME);
  Serial.println("DFPlayer TX-only enabled; card and playback cannot be verified over UART.");
  if (!psramFound()) {
    show("Camera stopped", "PSRAM required", 0, 2);
    while (true) delay(1000);
  }
  startWiFi();
  if (!setupCamera()) {
    show("Camera stopped", "Check camera/RAM", 0, 2);
    while (true) delay(1000);
  }
  show("Ready to scan", "Connecting WiFi");
}
void loop() {
  static wl_status_t previousWiFi = WL_NO_SHIELD;
  wl_status_t currentWiFi = WiFi.status();
  if (currentWiFi != previousWiFi) {
    if (currentWiFi == WL_CONNECTED) {
      Serial.print("WiFi connected. ESP32 IP: "); Serial.println(WiFi.localIP());
      Serial.print("Attendance server: "); Serial.println(SERVER_URL);
      show("Ready to scan", "WiFi connected");
    } else show("Scanner offline", "Connecting WiFi", 0, 2);
    previousWiFi = currentWiFi;
  }
  if (lightsUntil && (long)(millis() - lightsUntil) >= 0) {
    digitalWrite(LED_GREEN, LOW); digitalWrite(LED_RED, LOW); lightsUntil = 0;
  }
  if (resetAt && (long)(millis() - resetAt) >= 0) {
    resetAt = 0;
    writeLCD("Ready to scan", currentWiFi == WL_CONNECTED ? "Aim student QR" : "WiFi offline");
  }
  if (currentWiFi == WL_CONNECTED && millis() - capturedAt >= CAPTURE_INTERVAL_MS) {
    capturedAt = millis(); sendFrame();
  }
  delay(5);
}
