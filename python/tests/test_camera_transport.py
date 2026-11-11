"""Exercise the ESP32 JPEG protocol through a real local Waitress connection."""
import io
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path

import qrcode
from PIL import Image
from waitress import create_server

from attendance import create_app
from attendance.db import PH, get_db, qr_payload


class CameraTransportTests(unittest.TestCase):
    def test_jpeg_over_http_returns_lcd_result_only_after_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(dict(DATABASE=Path(directory) / "http.db",
                                  ATTENDANCE_TOKEN="camera-test-token", ADMIN_PASSWORD="test-admin-password"))
            with app.app_context(), get_db() as db:
                from attendance.db import replace_card
                db.execute("INSERT INTO students VALUES ('HTTP-1', 'HTTP Student')")
                db.execute("INSERT INTO enrollment(student_id,joined_on) VALUES ('HTTP-1','2000-01-01')")
                replace_card("HTTP-1")
                db.execute("INSERT INTO class_schedule(day, start_time) VALUES (?, '00:00')",
                           (datetime.now(PH).date().isoformat(),))
                payload = qr_payload("HTTP-1")
            image = Image.new("RGB", (640, 480), "white")
            qr = qrcode.make(payload, box_size=7, border=4).convert("RGB")
            image.paste(qr, ((640 - qr.width)//2, (480 - qr.height)//2))
            stream = io.BytesIO()
            image.save(stream, "JPEG", quality=90)
            jpeg = stream.getvalue()
            self.assertGreater(len(jpeg), 4096)
            server = create_server(app, host="127.0.0.1", port=0, max_request_body_size=262144)
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.effective_port}/camera/frame", data=jpeg,
                    headers={"Content-Type": "image/jpeg", "X-Device-Token": "camera-test-token"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 201)
                    result = response.read()
                    self.assertEqual(int(response.headers["Content-Length"]), len(result))
                    self.assertLessEqual(len(result), 64)
                    status, name = result.decode().split("\n")
                    self.assertIn(status, {"Present", "Late", "Absent"})
                    self.assertEqual(name, "HTTP Student")
                with app.app_context():
                    self.assertEqual(get_db().execute("SELECT COUNT(*) FROM attendance").fetchone()[0], 1)
            finally:
                server.close()
                server.task_dispatcher.shutdown()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
