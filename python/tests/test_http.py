"""Endpoint checks with Flask's test client and isolated SQLite storage."""
import base64
import csv
import io
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import qrcode
from PIL import Image
from attendance import create_app
from attendance.db import PH, get_db, qr_payload


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = create_app(dict(TESTING=True, DATABASE=Path(self.directory.name) / "test.db",
                                  ATTENDANCE_TOKEN="test-device-token", ADMIN_PASSWORD="test-admin-password",
                                  SECRET_KEY="test-session-key"))
        self.client = self.app.test_client()
        self.admin = {}  # Authentication is carried by the signed session cookie.
        self.device = {"X-Device-Token": "test-device-token", "Content-Type": "text/plain"}
        self.today = datetime.now(PH).date().isoformat()
        self.sign_in(self.client)
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO class_schedule(day, start_time) VALUES (?,?)", (self.today, "00:00"))
        with self.client.session_transaction() as session:
            self.csrf = session["csrf"]

    def sign_in(self, client):
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["csrf"]
        return client.post("/login", data={"csrf": csrf, "username": "admin", "password": "test-admin-password"})

    def test_optional_end_time_validation_and_edit_after_checkin(self):
        form = {"csrf": self.csrf, "date": self.today, "start_time": "08:00"}
        for end in ("8:30", "25:00", "08:00:00", "08:00", "07:59", "bad"):
            self.assertEqual(self.client.post('/schedule', data={**form, 'end_time': end}).status_code, 400)
        self.assertEqual(self.client.post('/schedule', data={**form, 'end_time': '09:00'}).status_code, 303)
        self.register()
        with patch('attendance.db.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat(self.today+'T08:05:00+08:00')
            self.assertEqual(self.scan().status_code, 201)
        self.assertEqual(self.client.post('/schedule', data={**form, 'end_time': '10:00'}).status_code, 303)
        page = self.client.get('/dashboard').text
        self.assertIn('value="10:00"', page)
        self.assertIn('required readonly', page)
        self.assertEqual(self.client.post('/schedule', data={**form, 'start_time': '08:01', 'end_time': '10:00'}).status_code, 409)
        self.assertEqual(self.client.post('/schedule', data={**form, 'end_time': ''}).status_code, 303)
        with self.app.app_context():
            self.assertIsNone(get_db().execute('SELECT end_time FROM class_schedule').fetchone()[0])

    def test_camera_end_time_rejects_real_qr_without_recording(self):
        self.register()
        with self.app.app_context(), get_db() as db:
            db.execute("UPDATE class_schedule SET start_time='08:00', end_time='09:00'")
        with patch('attendance.db.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat(self.today+'T09:00:00+08:00')
            response = self.upload_frame(self.camera_image(self.card().decode()))
        self.assertEqual((response.status_code, response.text), (410, 'Class ended'))
        self.assertIn('class has ended', self.client.get('/dashboard').text)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT count(*) FROM attendance').fetchone()[0], 0)

    def register(self, sid="2026-001", name="Test Student", **fields):
        return self.client.post("/students", headers=self.admin,
                                data={"csrf": self.csrf, "id": sid, "name": name, **fields})

    def card(self, student_id="2026-001"):
        with self.app.app_context():
            return qr_payload(student_id).encode()

    def scan(self, payload=None, headers=None):
        if payload is None:
            payload = self.card()
        return self.client.post("/scan", data=payload, headers=self.device if headers is None else headers)

    def camera_image(self, payload="", size=(640, 480), mirrored=False):
        image = Image.new("RGB", size, "white")
        if payload:
            code = qrcode.make(payload, box_size=6, border=4).convert("RGB")
            image.paste(code, ((size[0]-code.width)//2, (size[1]-code.height)//2))
        if mirrored:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        stream = io.BytesIO()
        image.save(stream, "JPEG", quality=90)
        return stream.getvalue()

    def upload_frame(self, frame):
        return self.client.post("/camera/frame", data=frame,
                                headers={"X-Device-Token": "test-device-token", "Content-Type": "image/jpeg"})

    def test_all_routes_and_methods(self):
        self.assertEqual({rule.rule for rule in self.app.url_map.iter_rules()},
                         {"/", "/dashboard", "/login", "/logout", "/schedule", "/students", "/scan", "/report.csv", "/static/<path:filename>",
                          "/students/<student_id>/print", "/students/<student_id>/qr.png", "/students/<student_id>/replace-qr", "/camera/frame",
                          "/students/qrcodes.zip", "/students/cards.pdf", "/calendar", "/audit", "/attendance/<day>", "/attendance/<day>/finalize", "/attendance/<day>/correct", "/students/<student_id>/eligibility",
                          "/classes", "/classes/sessions", "/classes/enroll", "/scanner/session"})
        for path in ("/", "/dashboard", "/students", "/calendar", "/audit", "/report.csv", "/static/style.css", "/static/app.js"):
            with self.client.get(path, headers=self.admin) as response:
                self.assertEqual(response.status_code, 200)
            with self.client.head(path, headers=self.admin) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, b"")
        for method, path in (("get", "/scan"), ("post", "/dashboard"),
                             ("post", "/report.csv"), ("post", "/static/style.css"), ("get", "/logout"), ("get", "/schedule")):
            response = getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 405)
            self.assertIn("Allow", response.headers)
        self.assertEqual(self.client.get("/missing").status_code, 404)
        self.assertEqual(self.client.post("/missing").status_code, 404)
        for path in ("/", "/dashboard", "/login", "/logout", "/schedule", "/students", "/scan", "/report.csv", "/static/style.css"):
            with self.client.options(path) as response:
                self.assertEqual(response.status_code, 200)

    def test_landing_page_is_public_without_student_data(self):
        self.register(name="Private Student Name")
        with patch("attendance.routes.get_db", side_effect=AssertionError("Public page must not query student data")):
            response = self.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Less roll call", response.data)
        self.assertIn(b"/dashboard", response.data)
        self.assertNotIn(b"Private Student Name", response.data)
        self.assertNotIn(b"Pause animation", response.data)

    def test_admin_authentication(self):
        anonymous = self.app.test_client()
        for headers in ({}, {"Authorization": "Basic nonsense"},
                        {"Authorization": "Bearer token"},
                        {"Authorization": "Basic " + base64.b64encode(b"admin:test-admin-password").decode()},
                        self.device):
            for path in ("/dashboard", "/report.csv"):
                response = anonymous.get(path, headers=headers)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["Location"], "/login")
            self.assertEqual(anonymous.post("/students", headers=headers).status_code, 303)
        self.assertEqual(self.scan(b"untrusted", headers=self.admin).status_code, 401)

    def test_login_validation_csrf_and_rotation(self):
        client = self.app.test_client()
        page = client.get("/login")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'autocomplete="current-password"', page.data)
        self.assertEqual(client.post("/login", data={"username": "admin", "password": "test-admin-password"}).status_code, 403)
        with client.session_transaction() as session:
            csrf = session["csrf"]
        for username, password in (("admin", "wrong"), ("other", "test-admin-password"), ("admin", "wrong\u00e9")):
            response = client.post("/login", data={"csrf": csrf, "username": username, "password": password})
            self.assertEqual(response.status_code, 401)
            self.assertIn(b"Incorrect username or password", response.data)
            self.assertNotIn(b"test-admin-password", response.data)
            self.assertEqual(client.get("/dashboard").status_code, 303)
        self.assertEqual(self.sign_in(client).status_code, 303)
        with client.session_transaction() as session:
            self.assertTrue(session["admin"])
            self.assertNotEqual(session["csrf"], csrf)
            self.assertTrue(session.permanent)
        self.assertEqual(client.get("/dashboard").status_code, 200)
        self.assertEqual(client.get("/login").headers["Location"], "/dashboard")

    def test_logout_requires_csrf_and_clears_access(self):
        self.assertEqual(self.client.post("/logout", data={"csrf": "wrong"}).status_code, 403)
        self.assertEqual(self.client.get("/dashboard", headers=self.admin).status_code, 200)
        response = self.client.post("/logout", data={"csrf": self.csrf})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/login")
        self.assertEqual(self.client.get("/dashboard").status_code, 303)
        self.assertEqual(self.client.get("/report.csv").status_code, 303)
        self.assertEqual(self.client.post("/students").status_code, 303)

    def test_expired_and_tampered_sessions(self):
        from datetime import timedelta
        self.app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=-1)
        self.assertEqual(self.client.get("/dashboard").status_code, 303)
        client = self.app.test_client()
        client.set_cookie("session", "forged-admin-session")
        self.assertEqual(client.get("/dashboard").status_code, 303)

    def test_schedule_validation_csrf_and_lock(self):
        url = "/schedule"
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post(url).status_code, 303)
        self.assertEqual(self.client.post(url, data={"date": self.today, "start_time": "08:00"}).status_code, 403)
        for time in ("", "25:00", "8:00", "08:00:00", "bad"):
            self.assertEqual(self.client.post(url, data={"csrf": self.csrf, "date": self.today, "start_time": time}).status_code, 400)
        for date in ("bad", "2026-2-1"):
            self.assertEqual(self.client.post(url, data={"csrf": self.csrf, "date": date, "start_time": "08:00"}).status_code, 400)
        response = self.client.post(url, data={"csrf": self.csrf, "date": self.today, "start_time": "00:00"})
        self.assertEqual(response.status_code, 303)
        self.register()
        self.assertEqual(self.scan().status_code, 201)
        self.assertEqual(self.client.post(url, data={"csrf": self.csrf, "date": self.today, "start_time": "09:00"}).status_code, 409)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT start_time FROM class_schedule WHERE day=?", (self.today,)).fetchone()[0], "00:00")

    def test_scan_schedule_messages(self):
        self.register()
        with self.app.app_context(), get_db() as db:
            db.execute("DELETE FROM class_schedule")
        response = self.scan()
        self.assertEqual((response.status_code, response.text), (422, "Class time not set"))
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO class_schedule(day, start_time) VALUES (?,?)", (self.today, "23:59"))
        with patch("attendance.db.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(self.today + "T08:00:00+08:00")
            response = self.scan()
            self.assertEqual((response.status_code, response.text), (425, "Class not started"))

    def test_existing_legacy_checkins_allow_initial_schedule(self):
        self.register()
        with self.app.app_context(), get_db() as db:
            db.execute("DELETE FROM class_schedule")
            db.execute("INSERT INTO attendance(student_id,day,recorded_at) VALUES (?,?,?)",
                       ("2026-001", self.today, self.today + "T08:00:00+08:00"))
        page = self.client.get("/dashboard")
        self.assertIn(b"Not assessed", page.data)
        response = self.client.post("/schedule", data={"csrf": self.csrf, "date": self.today, "start_time": "00:00"})
        self.assertEqual(response.status_code, 303)
        self.register("2026-002", "Second Student")
        self.assertEqual(self.scan(self.card("2026-002")).status_code, 201)

    def test_empty_dashboard_and_security_headers(self):
        response = self.client.get("/dashboard", headers=self.admin)
        self.assertIn(b"No students registered yet", self.client.get('/students').data)
        self.assertIn(b"No check-ins for this date", response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/static/../../server.py").status_code, 404)

    def test_registration_escaping_and_duplicate(self):
        response = self.register(name="A <Student> COUNT DAY CSRF")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/students/2026-001/print")
        response = self.client.get(response.headers["Location"])
        self.assertIn(b"A &lt;Student&gt; COUNT DAY CSRF", response.data)
        self.assertIn(b"Student registered", response.data)
        self.assertEqual(self.register().status_code, 409)

    def test_qr_encodes_id_and_identifies_registered_student(self):
        self.register(name="Maria Test")
        with patch("attendance.routes.qrcode.make", wraps=qrcode.make) as encode:
            response = self.client.get("/students/2026-001/qr.png")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/png")
            self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))
            encode.assert_called_once_with(self.card().decode(), box_size=12, border=4)
            with Image.open(io.BytesIO(response.data)) as image:
                image.verify()
            response.close()
        self.assertEqual(self.scan().status_code, 201)
        page = self.client.get("/dashboard")
        self.assertIn(b"Maria Test", page.data)
        with self.app.app_context():
            row = get_db().execute("SELECT s.name FROM attendance a JOIN students s ON s.id=a.student_id").fetchone()
            self.assertEqual(row[0], "Maria Test")

    def test_qr_routes_require_login_and_existing_student(self):
        anonymous = self.app.test_client()
        for path in ("/students/2026-001/print", "/students/2026-001/qr.png"):
            self.assertEqual(anonymous.get(path).status_code, 303)
            self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.client.post(path).status_code, 405)
            self.assertEqual(self.client.options(path).status_code, 200)
        self.register()
        for path in ("/students/2026-001/print", "/students/2026-001/qr.png"):
            with self.client.head(path) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, b"")
        with self.client.get("/students/2026-001/qr.png?download=1") as response:
            self.assertIn('attachment; filename=student-2026-001.png', response.headers["Content-Disposition"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_maximum_length_student_id_has_printable_qr(self):
        sid = "A" * 40
        self.assertEqual(self.register(sid, "Long ID Student").status_code, 303)
        with self.client.get(f"/students/{sid}/qr.png") as response:
            self.assertEqual(response.status_code, 200)
            with Image.open(io.BytesIO(response.data)) as image:
                self.assertGreaterEqual(image.width, 300)
        self.assertEqual(self.scan(self.card(sid)).status_code, 201)

    def test_card_replacement_requires_auth_and_csrf_and_revokes_old_card(self):
        self.register()
        old = self.card()
        url = "/students/2026-001/replace-qr"
        self.assertEqual(self.app.test_client().post(url).status_code, 303)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, data={"csrf": "wrong"}).status_code, 403)
        self.assertEqual(self.card(), old)
        response = self.client.post(url, data={"csrf": self.csrf})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/students/2026-001/print")
        self.assertNotEqual(self.card(), old)
        self.assertEqual(self.scan(old).status_code, 403)
        self.assertEqual(self.scan().status_code, 201)
        self.assertEqual(self.client.post("/students/missing/replace-qr", data={"csrf": self.csrf}).status_code, 404)

    def test_forged_card_cannot_identify_or_record_a_student(self):
        self.register()
        card = self.card()
        changed = card[:-1] + (b"A" if card[-1:] != b"A" else b"B")
        for payload in (b"2026-001", changed, card.replace(b"2026-001", b"2026-002")):
            response = self.scan(payload)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.text, "Invalid QR card")
            self.assertNotIn("Test Student", response.text)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT count(*) FROM attendance").fetchone()[0], 0)

    def test_registration_rolls_back_if_card_issuance_fails(self):
        with patch("attendance.routes.replace_card", side_effect=sqlite3.OperationalError("private detail")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.register()
        self.assertEqual(response.status_code, 503)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT count(*) FROM students").fetchone()[0], 0)

    def test_lcd_statuses_and_csv_follow_fifteen_and_forty_minute_boundaries(self):
        with self.app.app_context(), get_db() as db:
            db.execute("UPDATE class_schedule SET start_time='08:00' WHERE day=?", (self.today,))
        for index, clock_time, status in ((1, "08:14:59", "present"), (2, "08:15:00", "late"),
                                          (3, "08:39:59", "late"), (4, "08:40:00", "absent")):
            sid = f"BOUNDARY-{index}"
            self.register(sid, "Maria Dela Cruz")
            card = self.card(sid)
            with patch("attendance.db.datetime") as clock:
                clock.now.return_value = datetime.fromisoformat(self.today + "T" + clock_time + "+08:00")
                response = self.scan(card)
            self.assertEqual((response.status_code, response.text), (201, status.title() + "\nMaria Dela Cruz"))
        rows = list(csv.reader(io.StringIO(self.client.get("/report.csv", headers=self.admin).data.decode("utf-8-sig"))))
        self.assertEqual(sorted(row[4] for row in rows[1:]), ["absent", "late", "late", "present"])

    def test_registration_validation(self):
        for sid, name in (("", "Name"), ("x" * 41, "Name"), ("bad ID!", "Name"),
                          ("X", ""), ("X", "N" * 81), ("X", "A\x7fB"), ("X", "A\nB")):
            self.assertEqual(self.register(sid, name).status_code, 400)
        self.assertEqual(self.register("X' OR 1=1 --", "Name").status_code, 400)
        self.assertEqual(self.register("Valid-123", "Jos\u00e9 Dela Cruz").status_code, 303)

    def test_csrf_is_bound_to_session(self):
        self.assertEqual(self.register(csrf="wrong").status_code, 403)
        self.assertEqual(self.register(csrf="\u00e9").status_code, 403)
        other = self.app.test_client()
        self.sign_in(other)
        self.assertEqual(other.post("/students", headers=self.admin,
                                   data={"id": "X", "name": "Name", "csrf": self.csrf}).status_code, 403)

    def test_scan_contract(self):
        self.register()
        self.assertEqual(self.scan(headers={}).status_code, 401)
        accepted = self.scan()
        self.assertEqual(accepted.status_code, 201)
        self.assertIn(accepted.text.split("\n")[0], ("Present", "Late", "Absent"))
        self.assertEqual(accepted.text.split("\n")[1], "Test Student")
        self.assertEqual(self.scan().status_code, 409)
        self.assertEqual(self.scan(b"unknown").status_code, 403)
        for value in (b"", b"x" * 129, b"\xff"):
            self.assertEqual(self.scan(value).status_code, 400)
        for value in (b"invalid!", b"x" * 41, b"x" * 128, b"2026-001", b"2026-001\x00"):
            self.assertEqual(self.scan(value).status_code, 403)
        self.assertEqual(self.scan(headers={"X-Device-Token": "test-device-token"}).status_code, 415)
        self.assertEqual(self.scan(b"x" * 4097).status_code, 413)
        self.assertEqual(self.scan().mimetype, "text/plain")
        self.assertEqual(self.client.post("/students", headers=self.admin, data=b"x" * 4097,
                                          content_type="application/x-www-form-urlencoded").status_code, 413)

    def test_date_validation_on_both_endpoints(self):
        for date in ("2026-2-1", "2026-02-30", "", "garbage", "2026-01-01' OR 1=1"):
            for path in ("/dashboard", "/report.csv"):
                self.assertEqual(self.client.get(path, query_string={"date": date}, headers=self.admin).status_code, 400)

    def test_filter_and_excel_safe_csv(self):
        self.register(name='=HYPERLINK("bad")')
        self.scan()
        report = self.client.get("/report.csv", headers=self.admin)
        self.assertEqual(report.mimetype, "text/csv")
        self.assertTrue(report.data.startswith(b"\xef\xbb\xbf"))
        self.assertIn(f'attendance-class-1-session-1-{self.today}.csv', report.headers["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(report.data.decode("utf-8-sig"))))
        self.assertEqual(rows[1][1], "'=HYPERLINK(\"bad\")")
        self.assertEqual(rows[1][2], self.today)
        self.assertTrue(rows[1][3].endswith("+08:00"))
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO attendance(student_id,day,recorded_at) VALUES (?,?,?)", ("2026-001", "2000-01-01", "2000-01-01T08:00:00+08:00"))
        response = self.client.get("/report.csv?date=2000-01-01", headers=self.admin)
        rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], "2000-01-01")
        response = self.client.get("/report.csv?date=1999-01-01", headers=self.admin)
        self.assertEqual(len(list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))), 1)

    def test_database_failures_are_safe_and_logged(self):
        self.register()
        card = self.card()
        for method, path, target, kwargs in (
            ("post", "/students/2026-001/replace-qr", "attendance.routes.get_db", {"data": {"csrf": self.csrf}}),
            ("post", "/schedule", "attendance.routes.get_db", {"data": {"csrf": self.csrf, "date": self.today, "start_time": "08:00"}}),
            ("get", "/students/X/print", "attendance.routes.get_db", {}),
            ("get", "/students/X/qr.png", "attendance.routes.get_db", {}),
            ("get", "/dashboard", "attendance.routes.get_db", {"headers": self.admin}),
            ("get", "/report.csv", "attendance.routes.get_db", {"headers": self.admin}),
            ("post", "/students", "attendance.routes.get_db", {"headers": self.admin, "data": {"id": "X", "name": "Name", "csrf": self.csrf}}),
            ("post", "/scan", "attendance.db.get_db", {"headers": self.device, "data": card}),
        ):
            with patch(target, side_effect=sqlite3.OperationalError("private database details")):
                with self.assertLogs(self.app.logger, level="ERROR") as logs:
                    response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 503)
                self.assertIn(b"Reference:", response.data)
                self.assertNotIn(b"private database details", response.data)
                self.assertEqual(response.headers["Retry-After"], "5")
                self.assertIn("Database failure event=", logs.output[0])
                self.assertNotIn("test-device-token", logs.output[0])


    def test_camera_access_and_on_demand_frames(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get('/camera/frame').status_code, 303)
        self.assertEqual(anonymous.post('/camera/frame', data=b'').status_code, 401)
        self.assertEqual(self.client.get('/camera/frame').status_code, 503)
        jpeg = self.camera_image()
        response = self.upload_frame(jpeg)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['X-Scanner-State'], 'searching')
        response = self.client.get('/camera/frame')
        self.assertEqual(response.data, jpeg)
        self.assertEqual(response.mimetype, 'image/jpeg')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertNotIn(b'test-device-token', self.client.get('/dashboard').data)
        self.assertEqual(anonymous.get('/camera/frame').status_code, 303)

    def test_camera_limits_staleness_and_validation(self):
        self.assertEqual(self.client.post('/camera/frame', headers=self.device).status_code, 415)
        self.assertEqual(self.upload_frame(b'not jpeg').status_code, 400)
        self.assertEqual(self.upload_frame(b'x' * 262145).status_code, 413)
        self.assertEqual(self.upload_frame(self.camera_image(size=(801, 600))).status_code, 400)
        self.assertEqual(self.client.post('/scan', data=b'x' * 4097, headers=self.device).status_code, 413)
        with patch('attendance.routes.monotonic', return_value=100):
            self.upload_frame(self.camera_image())
        with patch('attendance.routes.monotonic', return_value=106):
            self.assertEqual(self.client.get('/camera/frame').status_code, 503)
        lock = self.app.extensions['camera_preview']['decode_lock']
        lock.acquire()
        try:
            self.assertEqual(self.upload_frame(self.camera_image()).status_code, 429)
        finally:
            lock.release()

    def test_live_dashboard_shows_saved_duplicate_and_rejected_scans(self):
        self.register(name="Maria <Test>")
        with self.app.app_context(), get_db() as db:
            db.execute("UPDATE class_schedule SET start_time='08:00' WHERE day=?", (self.today,))
        with patch("attendance.db.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(self.today + "T08:05:00+08:00")
            self.assertEqual(self.scan().status_code, 201)
            dashboard = self.client.get("/dashboard?date=" + self.today)
            self.assertIn(b"Saved: Present", dashboard.data)
            self.assertIn(b"Maria &lt;Test&gt;", dashboard.data)
            self.assertIn(b"data-dashboard-live=", dashboard.data)
            self.assertIn(b'data-live-part="attendance-rows"', dashboard.data)
            self.assertEqual(self.scan().status_code, 409)
            self.assertIn(b"Already recorded", self.client.get("/dashboard").data)
        self.assertEqual(self.scan(b"not-a-signed-card").status_code, 403)
        self.assertIn(b"Not saved: use a current student QR card", self.client.get("/dashboard").data)
        self.assertNotIn(b"Saved: Present", self.app.test_client().get("/").data)
        self.register("SECOND", "Second Student")
        with self.app.app_context(), get_db() as db:
            db.execute("DELETE FROM class_schedule")
        self.assertEqual(self.scan(self.card("SECOND")).status_code, 422)
        self.assertIn(b"class start time first", self.client.get("/dashboard").data)

    def test_decoder_feedback_requires_device_auth_and_expires(self):
        with patch('attendance.routes.decode_frame', return_value=('', True)) as decode:
            response = self.client.post('/camera/frame', data=b'fake', headers={'Content-Type':'image/jpeg'})
            self.assertEqual(response.status_code, 401)
            decode.assert_not_called()
            with patch('attendance.routes.monotonic', return_value=100):
                response = self.upload_frame(self.camera_image())
                self.assertEqual(response.status_code, 204)
                self.assertEqual(response.headers['X-Scanner-State'], 'decode_failed')
                self.assertIn(b'QR detected but unreadable', self.client.get('/dashboard').data)
        with patch('attendance.routes.monotonic', return_value=106):
            self.assertNotIn(b'QR detected but unreadable', self.client.get('/dashboard').data)


    def test_camera_real_qr_saves_without_viewer_and_suppresses_repeat(self):
        self.register(name="Camera Student")
        jpeg = self.camera_image(self.card().decode())
        with self.app.app_context(), get_db() as db:
            db.execute("UPDATE class_schedule SET start_time='08:00' WHERE day=?", (self.today,))
        with patch('attendance.db.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat(self.today+'T08:05:00+08:00')
            with patch('attendance.routes.monotonic', return_value=100):
                response = self.upload_frame(jpeg)
                self.assertEqual((response.status_code, response.text), (201, 'Present\nCamera Student'))
                self.assertIn(b'Saved: Present', self.client.get('/dashboard').data)
                # Removing a just-scanned card can expose an unreadable partial pattern.
                # Keep the confirmed result visible briefly instead of flashing an error.
                with patch('attendance.routes.monotonic', return_value=101), \
                        patch('attendance.routes.decode_frame', return_value=('', True)):
                    self.upload_frame(self.camera_image())
                    self.assertIn(b'Saved: Present', self.client.get('/dashboard').data)
                response = self.upload_frame(jpeg)
                self.assertEqual(response.status_code, 204)
                self.assertEqual(response.headers['X-Scanner-State'], 'cooldown')
            with patch('attendance.routes.monotonic', return_value=106):
                self.assertEqual(self.upload_frame(jpeg).status_code, 409)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM attendance').fetchone()[0], 1)

    def test_camera_mirrored_max_length_card_and_invalid_qr(self):
        sid = 'M' * 40
        self.register(sid, 'Long ID Student')
        image = self.camera_image(self.card(sid).decode(), mirrored=True)
        self.assertEqual(self.upload_frame(image).status_code, 201)
        response = self.upload_frame(self.camera_image('2026-001'))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.text, 'Invalid QR card')

    def test_camera_decoder_failure_is_safe_and_logged(self):
        import cv2
        with patch('attendance.routes.decode_frame', side_effect=cv2.error('private decoder details')):
            with self.assertLogs(self.app.logger, level='ERROR') as logs:
                response = self.upload_frame(self.camera_image())
        self.assertEqual(response.status_code, 503)
        self.assertIn(b'Reference:', response.data)
        self.assertNotIn(b'private decoder details', response.data)
        self.assertIn('QR decoder failure event=', logs.output[0])
        self.assertNotIn('test-device-token', logs.output[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
