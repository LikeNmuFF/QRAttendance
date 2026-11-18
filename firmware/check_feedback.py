"""Check event/track/LED mappings against the actual sketch and audio manifest.

Run: python firmware/check_feedback.py
This checks source contracts; Arduino compilation and physical bench tests are separate.
"""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sketch = (root / "firmware/AttendanceCam/AttendanceCam.ino").read_text()
config = (root / "firmware/AttendanceCam/config.h").read_text()
manifest = json.loads((root / "audio/dfplayer-male-14/messages.json").read_text())

failures = sketch.split("void reportFailure(int code) {", 1)[1].split("void sendFrame()", 1)[0]
branches = re.findall(r'(?:if|else if)\s*\(([^()]*)\)\s*show\("[^"]*", "[^"]*", (\d+), (\d+)\)', failures)
fallback = re.search(r'else show\("[^"]*", "[^"]*", (\d+), (\d+)\)', failures)
assert fallback


def failure_feedback(code):
    for condition, track, light in branches:
        condition = condition.replace("||", " or ").replace("&&", " and ")
        if eval(condition, {"__builtins__": {}}, {"code": code}):
            return int(track), int(light)
    return tuple(map(int, fallback.groups()))


for code, track in {
    -100: 13, -1: 12, -11: 12, 401: 4, 403: 3, 423: 7,
    422: 10, 425: 8, 410: 9, 413: 4, 400: 4, 415: 4,
    200: 4, 404: 4, 429: 0, 500: 4, 503: 4,
}.items():
    assert failure_feedback(code) == (track, 2), (code, failure_feedback(code))

saved = sketch.split('Serial.println("Attendance saved by laptop.");', 1)[1].split('} else if (code == 409', 1)[0]
assert re.search(r'if \(status == "Present"\) show\(name, status, 1, 1\)', saved)
assert re.search(r'else if \(status == "Late"\) show\(name, status, 5, 3\)', saved)
assert 'else show(name, status, 6, 2)' in saved
assert 'show(name, "Already recorded", 2, 2)' in sketch
assert 'show("Unreadable QR", "Hold card steady", 11, 2)' in sketch
assert 'show("Camera stopped", "PSRAM required", 13, 2)' in sketch
assert 'show("Camera stopped", "Check camera/RAM", 13, 2)' in sketch
assert 'show("Ready to scan", "WiFi connected", readyAnnounced ? 0 : 14)' in sketch
assert 'show("Scanner offline", "Connecting WiFi", 12, 2)' in sketch

for name, pin, indicator in [("GREEN", 12, 1), ("RED", 15, 2), ("YELLOW", 4, 3)]:
    assert re.search(rf"#define LED_{name}\s+{pin}\b", config)
    assert f'digitalWrite(LED_{name}, indicator == {indicator} ? HIGH : LOW)' in sketch
    assert f'pinMode(LED_{name}, OUTPUT)' in sketch
    assert sketch.count(f'digitalWrite(LED_{name}, LOW)') == 2  # startup and timeout
assert 'if (indicator) lights(indicator);' in sketch
assert 'millis() - reportedAt < 10000' in failures
assert 'millis() - warningAt >= 10000' in sketch
assert 'millis() - offlineAt >= 15000' in sketch

assert [m["file"] for m in manifest] == [f"{n:04}.mp3" for n in range(1, 15)]
for message in manifest:
    path = root / "audio/dfplayer-male-14/mp3" / message["file"]
    assert path.stat().st_size > 1000, path
print("Feedback contracts passed: 14 tracks, 3 LED outputs, HTTP errors, startup and repeat limits.")
