"""Class/session isolation, migration, and shared scanner integration."""
import io
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from attendance import create_app
from attendance.db import PH, absence_count, get_db, is_dropped, qr_payload, record, scanner_target


class ClassSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = dict(TESTING=True, DATABASE=Path(self.directory.name)/'test.db',
                           ADMIN_PASSWORD='test-password-long', ATTENDANCE_TOKEN='device-test', SECRET_KEY='test')
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.client.session_transaction() as login:
            login.update(admin=True, csrf='csrf-test')
        self.today = datetime.now(PH).date().isoformat()
        self.yesterday = (datetime.now(PH).date()-timedelta(days=1)).isoformat()
        self.assertEqual(self.post('/students', id='S1', name='Shared Student').status_code,303)
        with self.app.app_context():
            self.card = qr_payload('S1')

    def post(self, path, **data):
        return self.client.post(path, data={'csrf':'csrf-test', **data})

    def scope(self, path, sid=1, cid=1):
        return path + ('&' if '?' in path else '?') + f'class_id={cid}&session_id={sid}'

    def add_session(self):
        self.assertEqual(self.post('/classes/sessions',name='Afternoon').status_code,303)
        with self.app.app_context():
            return get_db().execute('SELECT MAX(id) FROM class_sessions').fetchone()[0]

    def add_class(self, name='Mathematics'):
        self.assertEqual(self.post('/classes',name=name).status_code,303)
        with self.app.app_context():
            return get_db().execute('SELECT class_id,id FROM class_sessions ORDER BY id DESC LIMIT 1').fetchone()

    def hours(self, sid=1, cid=1, day=None):
        return self.post(self.scope('/schedule',sid,cid), date=day or self.today, start_time='00:00')

    def activate(self, sid=1, cid=1):
        return self.post(self.scope('/scanner/session',sid,cid), date=self.today)

    def scan(self):
        return self.client.post('/scan',data=self.card, headers={'Content-Type':'text/plain','X-Device-Token':'device-test'})

    def test_same_qr_checks_into_two_sessions_and_duplicate_stays_scoped(self):
        sid = self.add_session()
        self.assertEqual(self.hours().status_code,303)
        self.assertEqual(self.hours(sid).status_code,303)
        self.assertEqual(self.scan().status_code,422)  # Multiple sessions require a deliberate target.
        self.assertEqual(self.activate().status_code,303)
        self.assertEqual(self.scan().status_code,201)
        self.assertEqual(self.scan().status_code,409)
        self.assertEqual(self.activate(sid).status_code,303)
        self.assertEqual(self.scan().status_code,201)
        self.assertEqual(self.scan().status_code,409)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT count(*) FROM attendance').fetchone()[0],2)
            self.assertEqual(qr_payload('S1'),self.card)

    def test_classes_have_separate_rosters_and_reuse_existing_card(self):
        cid,sid = self.add_class()
        self.assertNotIn('Shared Student</span>',self.client.get(self.scope('/students',sid,cid)).text)
        self.hours(sid,cid)
        self.activate(sid,cid)
        self.assertEqual(self.scan().text,'Not in this class')
        self.assertEqual(self.post(self.scope('/classes/enroll',sid,cid),student_id='S1').status_code,303)
        self.assertEqual(self.scan().status_code,201)
        self.assertIn('Shared Student',self.client.get(self.scope('/students',sid,cid)).text)
        self.assertEqual(self.post(self.scope('/students',sid,cid),id='S2',name='Math Only').status_code,303)
        self.assertNotIn('Math Only',self.client.get('/students').text)
        self.assertIn('Math Only',self.client.get(self.scope('/students',sid,cid)).text)
        with self.app.app_context():
            self.assertEqual(qr_payload('S1'),self.card)

    def test_exports_and_individual_cards_are_scoped_to_class(self):
        cid,sid = self.add_class()
        self.post(self.scope('/students',sid,cid),id='S2',name='Math Only')
        response = self.client.get(self.scope('/students/qrcodes.zip',sid,cid))
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(),['student-S2.png'])
        for path in ('/students/S1/qr.png','/students/S1/print','/students/cards.pdf?mode=selected&student_id=S1'):
            self.assertEqual(self.client.get(self.scope(path,sid,cid)).status_code,404)

    def test_schedule_locks_and_reports_are_per_session(self):
        sid = self.add_session()
        self.hours()
        self.hours(sid)
        self.activate()
        self.scan()
        self.assertEqual(self.post('/schedule',date=self.today,start_time='01:00').status_code,409)
        self.assertEqual(self.post(self.scope('/schedule',sid),date=self.today,start_time='01:00').status_code,303)
        self.assertIn('Shared Student',self.client.get('/report.csv').text)
        self.assertNotIn('Shared Student',self.client.get(self.scope('/report.csv',sid)).text)
        self.assertIn('session-'+str(sid),self.client.get(self.scope('/report.csv',sid)).headers['Content-Disposition'])

    def test_finalization_and_corrections_do_not_change_another_session(self):
        sid = self.add_session()
        with self.app.app_context(),get_db() as db:
            db.execute("UPDATE enrollment SET joined_on='2000-01-01'")
        self.hours(day=self.yesterday)
        self.hours(sid,day=self.yesterday)
        path=f'/attendance/{self.yesterday}'
        self.assertEqual(self.post(path+'/finalize',confirmed='yes').status_code,303)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT session_id,status FROM attendance').fetchall(),[(1,'absent')])
            self.assertEqual(get_db().execute('SELECT session_id FROM class_reviews').fetchall(),[(1,)])
        self.assertEqual(self.post(self.scope(path+'/correct',sid),student_id='S1',status='excused',reason='Medical excuse').status_code,303)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT session_id,status FROM attendance ORDER BY session_id').fetchall(),[(1,'absent'),(sid,'excused')])
            self.assertEqual(get_db().execute('SELECT session_id FROM attendance_edits').fetchone(),(sid,))
        self.assertIn('Medical excuse',self.client.get(self.scope(path,sid)).text)
        self.assertNotIn('Medical excuse',self.client.get(path).text)

    def test_drop_totals_span_sessions_but_never_other_classes(self):
        afternoon = self.add_session()
        cid,other = self.add_class()
        self.post(self.scope('/classes/enroll',other,cid),student_id='S1')
        with self.app.app_context(),get_db() as db:
            for offset in (2,1):
                day=(datetime.now(PH).date()-timedelta(days=offset)).isoformat()
                for sid in (1,afternoon):
                    db.execute("INSERT INTO class_schedule(day,start_time,session_id) VALUES (?,'08:00',?)",(day,sid))
                    db.execute("INSERT INTO attendance(student_id,day,recorded_at,status,session_id) VALUES ('S1',?,'','absent',?)",(day,sid))
                    db.execute('INSERT INTO class_reviews(day,finalized_at,session_id) VALUES (?,?,?)',(day,day+'T10:00:00+08:00',sid))
            self.assertEqual(absence_count('S1'),4)
            self.assertTrue(is_dropped('S1'))
            self.assertEqual(absence_count('S1',cid),0)
            self.assertFalse(is_dropped('S1',cid))
        self.hours()
        self.activate()
        self.assertEqual(self.scan().status_code,423)
        self.hours(other,cid)
        self.activate(other,cid)
        self.assertEqual(self.scan().status_code,201)
        self.post('/students/S1/eligibility',decision='chance',reason='Another chance')
        self.post(self.scope('/students/S1/eligibility',other,cid),decision='dropped',reason='Withdrawn from math')
        with self.app.app_context():
            self.assertFalse(is_dropped('S1'))
            self.assertTrue(is_dropped('S1',cid))
        history=self.client.get('/audit?student=S1').text
        self.assertIn('Afternoon',history)
        self.assertNotIn('Withdrawn from math',history)

    def test_calendar_and_history_keep_session_context(self):
        sid = self.add_session()
        self.hours(sid)
        calendar=self.client.get(self.scope('/calendar',sid)).text
        self.assertIn('session_id='+str(sid),calendar)
        self.assertIn('name="session_id" value="'+str(sid)+'"',calendar)
        self.assertIn('name="session_id" value="'+str(sid)+'"',self.client.get(self.scope('/students',sid)).text)
        self.assertEqual(self.client.get(self.scope('/classes',sid)).status_code,200)

    def test_fourth_morning_absence_excludes_later_session_without_rewriting_morning(self):
        sid=self.add_session()
        with self.app.app_context(),get_db() as db:
            db.execute("UPDATE enrollment SET joined_on='2000-01-01'")
            for offset in (4,3,2):
                day=(datetime.now(PH).date()-timedelta(days=offset)).isoformat()
                db.execute("INSERT INTO class_schedule(day,start_time) VALUES (?,'08:00')",(day,))
                db.execute("INSERT INTO attendance(student_id,day,recorded_at,status) VALUES ('S1',?,'','absent')",(day,))
                db.execute('INSERT INTO class_reviews(day,finalized_at) VALUES (?,?)',(day,day+'T10:00:00+08:00'))
            db.execute("INSERT INTO class_schedule(day,start_time) VALUES (?,'08:00')",(self.yesterday,))
            db.execute("INSERT INTO class_schedule(day,start_time,session_id) VALUES (?,'13:00',?)",(self.yesterday,sid))
        path=f'/attendance/{self.yesterday}'
        self.assertEqual(self.post(path+'/finalize',confirmed='yes').status_code,303)
        self.assertNotIn('Correct attendance for Shared Student',self.client.get(self.scope(path,sid)).text)
        self.assertEqual(self.post(self.scope(path+'/finalize',sid),confirmed='yes').status_code,303)
        with self.app.app_context():
            self.assertEqual(absence_count('S1'),4)
            self.assertEqual(get_db().execute('SELECT count(*) FROM attendance WHERE session_id=?',(sid,)).fetchone()[0],0)
        self.assertIn('Shared Student',self.client.get(path).text)

    def test_context_validation_and_all_new_actions_require_auth_csrf(self):
        cid,sid = self.add_class()
        for url,code in (('/dashboard?class_id=bad',400),('/dashboard?session_id=999',404),
                         (f'/dashboard?class_id=1&session_id={sid}',404),('/classes?class_id=999',404)):
            self.assertEqual(self.client.get(url).status_code,code)
        for url in ('/classes','/classes/sessions','/classes/enroll','/scanner/session'):
            self.assertEqual(self.app.test_client().post(url).status_code,303)
            self.assertEqual(self.client.post(url).status_code,403)
        self.assertEqual(self.post('/classes',name='mathematics').status_code,409)
        self.assertEqual(self.post('/classes',name='\n').status_code,400)
        self.assertEqual(self.post('/classes/sessions',name='Daily session').status_code,409)
        self.assertEqual(self.post('/classes/enroll',student_id='missing').status_code,404)
        self.assertEqual(self.post('/classes/enroll',student_id='S1').status_code,409)

    def test_scanner_selection_persists_and_expired_day_cannot_receive_scans(self):
        sid=self.add_session()
        self.hours(sid)
        self.activate(sid)
        restarted=create_app(self.config)
        with restarted.app_context():
            self.assertEqual(scanner_target()[:2],(sid,self.today))
            with get_db() as db:
                db.execute('UPDATE scanner_target SET day=?',(self.yesterday,))
            self.assertEqual(record(self.card),(422,'Select a session'))
            self.assertEqual(get_db().execute('SELECT count(*) FROM attendance').fetchone()[0],0)
        self.assertEqual(self.post('/scanner/session',date=self.yesterday).status_code,409)

    def test_camera_cooldown_is_reset_by_session_switch(self):
        sid=self.add_session()
        self.hours()
        self.hours(sid)
        self.activate()
        headers={'Content-Type':'image/jpeg','X-Device-Token':'device-test'}
        with patch('attendance.routes.decode_frame',return_value=(self.card,True)):
            self.assertEqual(self.client.post('/camera/frame',data=b'jpeg',headers=headers).status_code,201)
            self.assertEqual(self.client.post('/camera/frame',data=b'jpeg',headers=headers).status_code,204)
            self.activate(sid)
            self.assertEqual(self.client.post('/camera/frame',data=b'jpeg',headers=headers).status_code,201)

    def test_inflight_frame_cannot_land_in_newly_selected_session(self):
        sid=self.add_session()
        self.hours()
        self.hours(sid)
        self.activate()
        with self.app.app_context():
            revision=scanner_target()[2]
        self.activate(sid)
        with self.app.app_context():
            self.assertEqual(record(self.card,expected_revision=revision),(422,'Select a session'))
            self.assertEqual(get_db().execute('SELECT count(*) FROM attendance').fetchone()[0],0)

    def test_switching_sessions_hides_previous_session_scan_feedback(self):
        sid=self.add_session()
        self.hours()
        self.hours(sid)
        self.activate()
        self.assertEqual(self.scan().status_code,201)
        self.assertIn('Saved:',self.client.get('/dashboard').text)
        self.activate(sid)
        self.assertNotIn('Saved:',self.client.get(self.scope('/dashboard',sid)).text)

    def test_browsing_does_not_switch_scanner_and_finalized_session_rejects_activation(self):
        sid=self.add_session()
        self.hours()
        self.activate()
        self.client.get(self.scope('/dashboard',sid))
        with self.app.app_context():
            self.assertEqual(scanner_target()[0],1)
            with get_db() as db:
                db.execute('INSERT INTO class_reviews(day,finalized_at) VALUES (?,?)',(self.today,self.today+'T00:00:00+08:00'))
        self.assertEqual(self.activate().status_code,409)
        self.assertEqual(self.scan().status_code,410)


class ClassMigrationTests(unittest.TestCase):
    def test_invalid_legacy_foreign_keys_roll_back_class_upgrade(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'broken.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript("""
                    CREATE TABLE students(id TEXT PRIMARY KEY,name TEXT NOT NULL);
                    CREATE TABLE attendance(student_id TEXT NOT NULL REFERENCES students(id),day TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,PRIMARY KEY(student_id,day));
                    INSERT INTO attendance VALUES ('missing','2020-01-01','saved-time');
                """)
            with self.assertRaises(sqlite3.IntegrityError):
                create_app(dict(TESTING=True,DATABASE=path,ADMIN_PASSWORD='test-password-long',ATTENDANCE_TOKEN='device-test'))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],0)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='classes'").fetchone())
                self.assertNotIn('session_id',{row[1] for row in db.execute('PRAGMA table_info(attendance)')})
                self.assertEqual(db.execute('SELECT student_id,recorded_at FROM attendance').fetchall(),[('missing','saved-time')])

    def test_legacy_upgrade_preserves_history_credentials_and_makes_recovery_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'legacy.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript("""
                    CREATE TABLE students(id TEXT PRIMARY KEY,name TEXT NOT NULL);
                    CREATE TABLE attendance(student_id TEXT NOT NULL REFERENCES students(id),day TEXT NOT NULL,
                      recorded_at TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(student_id,day));
                    CREATE TABLE class_schedule(day TEXT PRIMARY KEY,start_time TEXT NOT NULL,end_time TEXT);
                    CREATE TABLE student_cards(student_id TEXT PRIMARY KEY REFERENCES students(id),secret TEXT NOT NULL);
                    CREATE TABLE enrollment(student_id TEXT PRIMARY KEY REFERENCES students(id),joined_on TEXT NOT NULL);
                    CREATE TABLE class_reviews(day TEXT PRIMARY KEY REFERENCES class_schedule(day),finalized_at TEXT NOT NULL);
                    CREATE TABLE attendance_edits(id INTEGER PRIMARY KEY,student_id TEXT,day TEXT,old_status TEXT,new_status TEXT,reason TEXT,changed_at TEXT);
                    CREATE TABLE eligibility_decisions(id INTEGER PRIMARY KEY,student_id TEXT,decision TEXT,reason TEXT,changed_at TEXT);
                    INSERT INTO students VALUES ('OLD','Legacy Student');
                    INSERT INTO student_cards VALUES ('OLD','0000000000000000000000000000000000000000000000000000000000000000');
                    INSERT INTO enrollment VALUES ('OLD','2000-01-01');
                    INSERT INTO class_schedule VALUES ('2020-01-01','08:00','10:00');
                    INSERT INTO attendance VALUES ('OLD','2020-01-01','2020-01-01T08:00:00+08:00','present');
                    INSERT INTO class_reviews VALUES ('2020-01-01','2020-01-01T10:00:00+08:00');
                    INSERT INTO attendance_edits VALUES (1,'OLD','2020-01-01','absent','present','Verified','2020-01-02');
                    INSERT INTO eligibility_decisions VALUES (1,'OLD','chance','Approved','2020-01-02');
                """)
            config=dict(DATABASE=path,ADMIN_PASSWORD='test-password-long',ATTENDANCE_TOKEN='device-test',SECRET_KEY='test')
            app=create_app(config)
            with app.app_context():
                db=get_db()
                card=qr_payload('OLD')
                self.assertEqual(db.execute('SELECT * FROM attendance').fetchone(),('OLD','2020-01-01','2020-01-01T08:00:00+08:00','present',1))
                self.assertEqual(db.execute('SELECT class_id FROM enrollment').fetchone(),(1,))
                self.assertEqual(db.execute('SELECT session_id FROM attendance_edits').fetchone(),(1,))
                self.assertEqual(db.execute('SELECT class_id FROM eligibility_decisions').fetchone(),(1,))
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            backup=path.with_name(path.name+'.pre-classes.bak')
            self.assertTrue(backup.exists())
            with closing(sqlite3.connect(backup)) as db:
                self.assertNotIn('session_id',{r[1] for r in db.execute('PRAGMA table_info(attendance)')})
            with create_app(config).app_context():
                self.assertEqual(qr_payload('OLD'),card)
                self.assertEqual(get_db().execute('SELECT count(*) FROM attendance').fetchone()[0],1)
