"""Transactional upgrade from the single-class register; QR credentials stay intact."""
import sqlite3
from contextlib import closing
from pathlib import Path

from flask import current_app


def upgrade_classes(db):
    if db.execute("PRAGMA user_version").fetchone()[0] >= 1:
        return
    # Keep a consistent, one-time recovery copy before upgrading a real register.
    if not current_app.testing and db.execute("SELECT count(*) FROM students").fetchone()[0]:
        path = Path(current_app.config["DATABASE"])
        backup = path.with_name(path.name + ".pre-classes.bak")
        if not backup.exists():
            with closing(sqlite3.connect(backup)) as destination:
                db.backup(destination)
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE classes(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE)")
            db.execute("INSERT INTO classes VALUES (1,'Default class')")
            db.execute("""CREATE TABLE class_sessions(id INTEGER PRIMARY KEY,
                class_id INTEGER NOT NULL REFERENCES classes(id), name TEXT NOT NULL COLLATE NOCASE,
                UNIQUE(class_id,name))""")
            db.execute("INSERT INTO class_sessions VALUES (1,1,'Daily session')")
            db.execute("""CREATE TABLE scanner_target(id INTEGER PRIMARY KEY CHECK(id=1),
                session_id INTEGER REFERENCES class_sessions(id), day TEXT, revision INTEGER NOT NULL DEFAULT 0)""")
            # Retain the original automatic daily workflow until more sessions are created.
            db.execute("INSERT INTO scanner_target(id,session_id) VALUES (1,1)")
            definitions = {
                "enrollment": """student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    joined_on TEXT NOT NULL, class_id INTEGER NOT NULL DEFAULT 1 REFERENCES classes(id),
                    PRIMARY KEY(student_id,class_id)""",
                "class_schedule": """day TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT,
                    session_id INTEGER NOT NULL DEFAULT 1 REFERENCES class_sessions(id), PRIMARY KEY(session_id,day)""",
                "attendance": """student_id TEXT NOT NULL REFERENCES students(id), day TEXT NOT NULL,
                    recorded_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not-assessed',
                    session_id INTEGER NOT NULL DEFAULT 1 REFERENCES class_sessions(id),
                    PRIMARY KEY(student_id,session_id,day)""",
                "class_reviews": """day TEXT NOT NULL, finalized_at TEXT NOT NULL,
                    session_id INTEGER NOT NULL DEFAULT 1 REFERENCES class_sessions(id),
                    PRIMARY KEY(session_id,day), FOREIGN KEY(session_id,day) REFERENCES class_schedule(session_id,day)""",
            }
            for table, definition in definitions.items():
                columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
                names = ",".join(columns)
                db.execute(f"CREATE TABLE {table}_scoped({definition})")
                db.execute(f"INSERT INTO {table}_scoped({names}) SELECT {names} FROM {table}")
                db.execute(f"DROP TABLE {table}")
                db.execute(f"ALTER TABLE {table}_scoped RENAME TO {table}")
            db.execute("ALTER TABLE attendance_edits ADD COLUMN session_id INTEGER NOT NULL DEFAULT 1 REFERENCES class_sessions(id)")
            db.execute("ALTER TABLE eligibility_decisions ADD COLUMN class_id INTEGER NOT NULL DEFAULT 1 REFERENCES classes(id)")
            db.execute("CREATE INDEX attendance_day_time ON attendance(session_id,day,recorded_at)")
            db.execute("CREATE INDEX eligibility_class_student ON eligibility_decisions(class_id,student_id,id)")
            db.execute("CREATE INDEX attendance_absences ON attendance(student_id,status,session_id,day)")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.IntegrityError("Class upgrade failed integrity validation")
            db.execute("PRAGMA user_version = 1")
    finally:
        db.execute("PRAGMA foreign_keys = ON")
