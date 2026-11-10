"""SQLite storage. The existing attendance.db schema and location are preserved."""
import re
import sqlite3
import base64
import hmac
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

from flask import current_app, g

PH = timezone(timedelta(hours=8))
ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,40}")
CARD_PATTERN = re.compile(r"QA1\.([A-Za-z0-9-]{1,40})\.[A-Za-z0-9_-]{43}")
MAX_QR_BYTES = 128


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=5)
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS students(id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attendance(
            student_id TEXT NOT NULL REFERENCES students(id),
            day TEXT NOT NULL, recorded_at TEXT NOT NULL,
            PRIMARY KEY(student_id, day));
        CREATE INDEX IF NOT EXISTS attendance_day_time ON attendance(day, recorded_at);
        CREATE TABLE IF NOT EXISTS class_schedule(day TEXT PRIMARY KEY, start_time TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS student_cards(
            student_id TEXT PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
            secret TEXT NOT NULL);
    """)
    if "end_time" not in {column[1] for column in db.execute("PRAGMA table_info(class_schedule)")}:
        with db:
            db.execute("ALTER TABLE class_schedule ADD COLUMN end_time TEXT")
    if "status" not in {column[1] for column in db.execute("PRAGMA table_info(attendance)")}:
        with db:
            db.execute("ALTER TABLE attendance ADD COLUMN status TEXT NOT NULL DEFAULT 'not-assessed'")
    with db:
        db.execute("UPDATE attendance SET status='present' WHERE status='on-time'")
        missing = db.execute("""SELECT s.id FROM students s LEFT JOIN student_cards c
            ON c.student_id=s.id WHERE c.student_id IS NULL""").fetchall()
        for (student_id,) in missing:
            replace_card(student_id)


def replace_card(student_id):
    """Issue a new secret inside the caller's transaction, revoking every old copy."""
    get_db().execute("""INSERT INTO student_cards VALUES (?,?)
        ON CONFLICT(student_id) DO UPDATE SET secret=excluded.secret""",
        (student_id, secrets.token_hex(32)))


def signed_payload(student_id, secret):
    message = "QA1." + student_id
    digest = hmac.digest(bytes.fromhex(secret), message.encode("ascii"), "sha256")
    signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return message + "." + signature


def qr_payload(student_id):
    row = get_db().execute("SELECT secret FROM student_cards WHERE student_id=?", (student_id,)).fetchone()
    if not row:
        raise ValueError("No QR credential issued for this student")
    return signed_payload(student_id, row[0])


def lcd_name(name, student_id):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = "".join(char for char in text if 32 <= ord(char) < 127).strip()
    return (text or student_id)[:16]


def record(payload):
    match = CARD_PATTERN.fullmatch(payload)
    if not match:
        return 403, "Invalid QR card"
    student_id = match.group(1)
    now = datetime.now(PH)
    db = get_db()
    with db:
        # Serialize schedule edits and check-ins so a saved status uses a stable start time.
        db.execute("BEGIN IMMEDIATE")
        student = db.execute("""SELECT s.name,c.secret FROM students s JOIN student_cards c
            ON c.student_id=s.id WHERE s.id=?""", (student_id,)).fetchone()
        if not student or not hmac.compare_digest(payload, signed_payload(student_id, student[1])):
            return 403, "Invalid QR card"
        name = lcd_name(student[0], student_id)
        day = now.date().isoformat()
        if db.execute("SELECT 1 FROM attendance WHERE student_id=? AND day=?", (student_id, day)).fetchone():
            return 409, "Already recorded\n" + name
        schedule = db.execute("SELECT start_time, end_time FROM class_schedule WHERE day=?", (day,)).fetchone()
        if not schedule:
            return 422, "Class time not set"
        hour, minute = map(int, schedule[0].split(":"))
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < start:
            return 425, "Class not started"
        if schedule[1]:
            end_hour, end_minute = map(int, schedule[1].split(":"))
            end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if now >= end:
                return 410, "Class ended"
        elapsed = now - start
        status = "absent" if elapsed >= timedelta(minutes=40) else "late" if elapsed >= timedelta(minutes=15) else "present"
        # The primary key enforces duplicates even for simultaneous scanner requests.
        inserted = db.execute("""INSERT INTO attendance(student_id, day, recorded_at, status) VALUES (?,?,?,?)
            ON CONFLICT(student_id, day) DO NOTHING""",
            (student_id, day, now.isoformat(timespec="seconds"), status)).rowcount
    if not inserted:
        return 409, "Already recorded\n" + name
    return 201, status.title() + "\n" + name
