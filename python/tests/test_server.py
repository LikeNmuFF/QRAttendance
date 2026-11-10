"""Storage checks; run with unittest discovery as documented in README.md."""
import sqlite3
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from attendance import create_app
from attendance.db import PH, get_db, init_db, record, replace_card, qr_payload, signed_payload
from server import load_settings


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = dict(TESTING=True, DATABASE=Path(self.directory.name) / "test.db",
                           ATTENDANCE_TOKEN="test-device-token", ADMIN_PASSWORD="test-admin-password",
                           SECRET_KEY="test-session-key")
        self.app = create_app(self.config)
        with self.app.app_context():
            db = get_db()
            with db:
                db.execute("INSERT INTO students VALUES (?,?)", ("2026-001", "Test Student"))
                replace_card("2026-001")
                db.execute("INSERT INTO class_schedule(day, start_time) VALUES (?,?)", (datetime.now(PH).date().isoformat(), "00:00"))

    def card(self, student_id="2026-001"):
        with self.app.app_context():
            return qr_payload(student_id)

    def test_accept_duplicate_unknown_and_invalid(self):
        with self.app.app_context():
            self.assertEqual(record(self.card())[0], 201)
            self.assertEqual(record(self.card())[0], 409)
            self.assertEqual(record(signed_payload("2026-999", "00" * 32))[0], 403)
            for value in ("", "bad ID!", "x" * 41, "2026-001\x00", "\u00e9"):
                self.assertEqual(record(value)[0], 403)
            self.assertEqual(get_db().execute("SELECT count(*) FROM attendance").fetchone()[0], 1)

    def test_persistence_and_existing_schema(self):
        with self.app.app_context():
            self.assertEqual(record(self.card())[0], 201)
            init_db()
        second_app = create_app(self.config)
        with second_app.app_context():
            self.assertEqual(record(self.card())[0], 409)
            self.assertEqual(get_db().execute("SELECT count(*) FROM students").fetchone()[0], 1)

    def test_foreign_keys(self):
        with self.app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                with get_db() as db:
                    db.execute("INSERT INTO attendance(student_id,day,recorded_at) VALUES ('unknown','2026-01-01','test')")

    def test_concurrent_scans_save_once(self):
        def scan(_):
            with self.app.app_context():
                return record(self.card())[0]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(scan, range(12)))
        self.assertEqual(results.count(201), 1)
        self.assertEqual(results.count(409), 11)

    def test_philippine_midnight_allows_new_day(self):
        with self.app.app_context(), patch("attendance.db.datetime") as clock:
            with get_db() as db:
                db.executemany("INSERT OR REPLACE INTO class_schedule(day, start_time) VALUES (?,?)", [("2026-11-08", "00:00"), ("2026-11-09", "00:00")])
            clock.now.return_value = datetime(2026, 11, 8, 23, 59, 59, tzinfo=PH)
            self.assertEqual(record(self.card())[0], 201)
            clock.now.return_value = datetime(2026, 11, 9, 0, 0, 0, tzinfo=PH)
            self.assertEqual(record(self.card())[0], 201)
            self.assertEqual(record(self.card())[0], 409)

    def test_start_time_and_late_boundaries(self):
        start = datetime(2026, 11, 8, 8, 0, tzinfo=PH)
        with self.app.app_context(), patch("attendance.db.datetime") as clock:
            with get_db() as db:
                db.execute("INSERT OR REPLACE INTO class_schedule(day, start_time) VALUES (?,?)", ("2026-11-08", "08:00"))
            for index, seconds in enumerate((-1, 0, 899, 900, 1800, 2399, 2400, 2401)):
                sid = f"BOUNDARY-{index}"
                with get_db() as db:
                    db.execute("INSERT INTO students VALUES (?,?)", (sid, "Boundary Student"))
                    replace_card(sid)
                clock.now.return_value = start + timedelta(seconds=seconds)
                code, message = record(self.card(sid))
                if seconds < 0:
                    self.assertEqual((code, message), (425, "Class not started"))
                else:
                    expected = "absent" if seconds >= 2400 else "late" if seconds >= 900 else "present"
                    self.assertEqual(code, 201)
                    self.assertEqual(message, expected.title() + "\nBoundary Student")
                    self.assertEqual(get_db().execute("SELECT status FROM attendance WHERE student_id=?", (sid,)).fetchone()[0], expected)

    def test_no_schedule_does_not_save_attendance(self):
        with self.app.app_context():
            with get_db() as db:
                db.execute("DELETE FROM class_schedule")
            self.assertEqual(record(self.card()), (422, "Class time not set"))
            self.assertEqual(get_db().execute("SELECT count(*) FROM attendance").fetchone()[0], 0)

    def test_end_time_boundary_and_duplicate_confirmation(self):
        with self.app.app_context(), patch("attendance.db.datetime") as clock:
            with get_db() as db:
                db.execute("INSERT OR REPLACE INTO class_schedule(day,start_time,end_time) VALUES ('2026-11-08','08:00','09:00')")
            for time, expected in (("09:00:00", 410), ("09:00:01", 410), ("08:59:59", 201), ("09:01:00", 409)):
                clock.now.return_value = datetime.fromisoformat("2026-11-08T" + time + "+08:00")
                result = record(self.card())
                self.assertEqual(result[0], expected)
                if expected == 410:
                    self.assertEqual(result[1], "Class ended")
                    self.assertEqual(get_db().execute("SELECT count(*) FROM attendance").fetchone()[0], 0)

    def test_legacy_database_migration_preserves_records(self):
        path = Path(self.directory.name) / "legacy.db"
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE students(id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE attendance(student_id TEXT NOT NULL REFERENCES students(id), day TEXT NOT NULL,
                    recorded_at TEXT NOT NULL, PRIMARY KEY(student_id,day));
                INSERT INTO students VALUES ('OLD-001','Old Student');
                INSERT INTO attendance VALUES ('OLD-001','2000-01-01','2000-01-01T08:00:00+08:00');
                CREATE TABLE class_schedule(day TEXT PRIMARY KEY, start_time TEXT NOT NULL);
                INSERT INTO class_schedule VALUES ('2000-01-01','08:00');
            """)
        app = create_app({**self.config, "DATABASE": path})
        with app.app_context():
            init_db()
            self.assertEqual(get_db().execute("SELECT student_id,status FROM attendance").fetchone(), ("OLD-001", "not-assessed"))
            self.assertEqual(get_db().execute("SELECT start_time,end_time FROM class_schedule").fetchone(), ("08:00", None))

    def test_signed_cards_reject_forgery_and_plain_ids(self):
        token = self.card()
        self.assertTrue(token.startswith("QA1.2026-001."))
        self.assertEqual(token, self.card())
        with self.app.app_context():
            for payload in ("2026-001", token[:-1] + ("A" if token[-1] != "A" else "B"),
                            token.replace("2026-001", "2026-002"), token + "=", token + "\nforged"):
                self.assertEqual(record(payload), (403, "Invalid QR card"))
            self.assertEqual(get_db().execute("SELECT count(*) FROM attendance").fetchone()[0], 0)

    def test_card_replacement_revokes_old_copies_even_after_checkin(self):
        old = self.card()
        with self.app.app_context():
            self.assertEqual(record(old)[0], 201)
            with get_db():
                replace_card("2026-001")
            new = qr_payload("2026-001")
            self.assertNotEqual(old, new)
            self.assertEqual(record(old), (403, "Invalid QR card"))
            self.assertEqual(record(new), (409, "Already recorded\nTest Student"))

    def test_card_survives_restart_and_lcd_name_is_bounded_ascii(self):
        token = self.card()
        app = create_app({**self.config, "SECRET_KEY": "different-session-key"})
        with app.app_context():
            self.assertEqual(qr_payload("2026-001"), token)
            with get_db() as db:
                db.execute("UPDATE students SET name=? WHERE id=?", ("Jos\u00e9 Extremely Long Student", "2026-001"))
            code, message = record(token)
            self.assertEqual(code, 201)
            self.assertEqual(message.split("\n")[1], "Jose Extremely L")
            self.assertTrue(message.isascii())

    def test_configuration_fails_closed(self):
        for config in ({"ATTENDANCE_TOKEN": ""}, {"ATTENDANCE_TOKEN": "CHANGE_TO_YOUR_DEVICE_TOKEN"},
                       {"ADMIN_PASSWORD": "short"}):
            with self.assertRaises(ValueError):
                create_app({**self.config, **config})

    def test_offline_settings_persist_and_allow_environment_overrides(self):
        path = Path(self.directory.name) / "instance" / "config.json"
        with patch.dict(os.environ, {}, clear=True):
            original = load_settings(path)
            self.assertEqual(load_settings(path), original)
            self.assertGreaterEqual(len(original["ADMIN_PASSWORD"]), 12)
            self.assertNotEqual(original["ADMIN_PASSWORD"], original["ATTENDANCE_TOKEN"])
            app = create_app({**self.config, **original})
            self.assertEqual(app.config["SECRET_KEY"], original["SECRET_KEY"])
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "environment-password"}):
            self.assertEqual(load_settings(path)["ADMIN_PASSWORD"], "environment-password")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_settings(path), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)

