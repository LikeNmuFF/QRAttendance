"""Teacher review and drop-rule integration checks, using disposable databases."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from attendance import create_app
from attendance.db import PH, get_db, qr_payload, replace_card, absence_count, record


class AuditTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = create_app(dict(TESTING=True, DATABASE=Path(directory.name)/'test.db',
            ADMIN_PASSWORD='test-admin-password', ATTENDANCE_TOKEN='test-device-token', SECRET_KEY='test'))
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(admin=True, csrf='test-csrf')
        self.today = datetime.now(PH).date()
        self.days = [(self.today-timedelta(days=n)).isoformat() for n in (4, 3, 2, 1)]
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO students VALUES ('S1','Test Student')")
            db.execute("INSERT INTO enrollment(student_id,joined_on) VALUES ('S1',?)", (self.days[0],))
            replace_card('S1')
            for day in self.days:
                db.execute("INSERT INTO class_schedule(day,start_time,end_time) VALUES (?,'08:00','09:00')", (day,))
            self.card = qr_payload('S1')

    def finalize(self, day):
        return self.client.post(f'/attendance/{day}/finalize', data={'csrf':'test-csrf','confirmed':'yes'})

    def correct(self, day, status='excused', reason='Medical excuse verified'):
        return self.client.post(f'/attendance/{day}/correct', data={
            'csrf':'test-csrf','student_id':'S1','status':status,'reason':reason})

    def test_four_finalized_missing_days_drop_and_correction_restores_qr(self):
        for n, day in enumerate(self.days, 1):
            self.assertEqual(self.finalize(day).status_code, 303)
            with self.app.app_context():
                self.assertEqual(absence_count('S1'), n)
        response = self.client.post('/scan', data=self.card, headers={
            'Content-Type':'text/plain','X-Device-Token':'test-device-token'})
        self.assertEqual((response.status_code,response.text.splitlines()[0]), (423,'You are dropped'))
        self.assertIn('Dropped', self.client.get('/audit').text)
        self.assertEqual(self.correct(self.days[0]).status_code,303)
        with self.app.app_context():
            self.assertEqual(absence_count('S1'),3)
            self.assertEqual(record(self.card)[0],422)  # Valid again; today's schedule is unset.
            self.assertEqual(get_db().execute('SELECT old_status,new_status FROM attendance_edits').fetchone(),('absent','excused'))
        self.assertIn('Medical excuse verified',self.client.get('/attendance/'+self.days[0]).text)

    def test_provisional_absences_do_not_drop_and_finalization_is_idempotent(self):
        with self.app.app_context(), get_db() as db:
            for day in self.days:
                db.execute("INSERT INTO attendance(student_id,day,recorded_at,status) VALUES ('S1',?,?,'absent')",(day,day+'T08:45:00+08:00'))
            self.assertEqual(absence_count('S1'),0)
        self.assertEqual(self.finalize(self.days[0]).status_code,303)
        self.assertEqual(self.finalize(self.days[0]).status_code,409)
        with self.app.app_context():
            self.assertEqual(absence_count('S1'),1)
            self.assertEqual(get_db().execute('SELECT count(*) FROM attendance').fetchone()[0],4)

    def test_new_students_are_not_absent_before_enrollment(self):
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO students VALUES ('NEW','New Student')")
            db.execute("INSERT INTO enrollment(student_id,joined_on) VALUES ('NEW',?)",(self.today.isoformat(),))
        self.assertEqual(self.finalize(self.days[0]).status_code,303)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT count(*) FROM attendance WHERE student_id='NEW'").fetchone()[0],0)

    def test_finalization_requires_auth_csrf_confirmation_schedule_and_end(self):
        url=f'/attendance/{self.days[0]}/finalize'
        self.assertEqual(self.app.test_client().post(url).status_code,303)
        self.assertEqual(self.client.post(url).status_code,403)
        self.assertEqual(self.client.post(url,data={'csrf':'test-csrf'}).status_code,400)
        self.assertEqual(self.finalize(self.today.isoformat()).status_code,409)
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO class_schedule(day,start_time,end_time) VALUES (?,'08:00','10:00')",(self.today.isoformat(),))
        with patch('attendance.routes.datetime') as clock:
            clock.strptime = datetime.strptime
            clock.now.return_value = datetime.combine(self.today,datetime.min.time(),PH).replace(hour=9)
            self.assertEqual(self.finalize(self.today.isoformat()).status_code,409)
            clock.now.return_value = clock.now.return_value.replace(hour=10)
            self.assertEqual(self.finalize(self.today.isoformat()).status_code,303)

    def test_corrections_validate_and_preserve_scan_timestamp(self):
        day=self.days[0]
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO attendance(student_id,day,recorded_at,status) VALUES ('S1',?,?,'absent')",(day,day+'T08:45:00+08:00'))
        self.assertEqual(self.correct(day,'invalid').status_code,400)
        self.assertEqual(self.correct(day,reason='').status_code,400)
        self.assertEqual(self.correct(day,'present').status_code,303)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT recorded_at,status FROM attendance').fetchone(),(day+'T08:45:00+08:00','present'))

    def test_finalized_hours_locked_and_future_days_cannot_be_finalized(self):
        day=self.days[0]
        self.assertEqual(self.finalize(day).status_code,303)
        self.assertEqual(self.client.post('/schedule',data={'csrf':'test-csrf','date':day,'start_time':'08:00','end_time':'10:00'}).status_code,409)
        future=(self.today+timedelta(days=1)).isoformat()
        with self.app.app_context(),get_db() as db:
            db.execute("INSERT INTO class_schedule(day,start_time) VALUES (?,'08:00')",(future,))
        self.assertEqual(self.finalize(future).status_code,409)
        self.assertEqual(self.correct(future).status_code,409)

    def test_calendar_day_history_and_navigation_are_separate(self):
        self.assertEqual(self.client.get('/calendar?month=invalid').status_code,400)
        month=self.days[0][:7]
        response=self.client.get('/calendar?month='+month)
        self.assertEqual(response.status_code,200)
        self.assertIn('/attendance/'+self.days[0],response.text)
        self.assertIn('08:00',response.text)
        self.assertEqual(self.client.get('/attendance/bad-date').status_code,400)
        for path in ('/calendar','/audit','/students','/attendance/'+self.days[0]):
            self.assertEqual(self.app.test_client().get(path).status_code,303)
        self.assertNotIn('id="register-student"',self.client.get('/dashboard').text)
        self.assertIn('id="register-student"',self.client.get('/students').text)
        self.assertIn('No attendance records',self.client.get('/audit?student=S1').text)

    def test_dropped_card_is_blocked_in_camera_transport(self):
        for day in self.days:
            self.finalize(day)
        with patch('attendance.routes.decode_frame',return_value=(self.card,True)):
            response=self.client.post('/camera/frame',data=b'jpeg',headers={
                'Content-Type':'image/jpeg','X-Device-Token':'test-device-token'})
        self.assertEqual(response.status_code,423)
        self.assertIn('You are dropped',response.text)
        self.assertIn('you are dropped',self.client.get('/dashboard').text)

    def test_forged_dropped_card_does_not_reveal_status(self):
        for day in self.days:
            self.finalize(day)
        with self.app.app_context():
            bad=self.card[:-1]+('A' if self.card[-1]!='A' else 'B')
            self.assertEqual(record(bad),(403,'Invalid QR card'))

    def test_teacher_chance_keeps_absences_and_can_be_revoked(self):
        for day in self.days:
            self.finalize(day)
        url='/students/S1/eligibility'
        form={'csrf':'test-csrf','decision':'chance','reason':'Teacher approved another chance'}
        self.assertEqual(self.app.test_client().post(url,data=form).status_code,303)
        self.assertEqual(self.client.post(url,data={**form,'csrf':'wrong'}).status_code,403)
        self.assertEqual(self.client.post(url,data={**form,'decision':'invalid'}).status_code,400)
        self.assertEqual(self.client.post(url,data=form).status_code,303)
        with self.app.app_context():
            self.assertEqual(absence_count('S1'),4)
            self.assertEqual(record(self.card)[0],422)
        self.assertIn('Chance granted',self.client.get('/audit').text)
        with self.app.app_context(),get_db() as db:
            db.execute("INSERT INTO class_schedule(day,start_time,end_time) VALUES (?,'08:00','10:00')",(self.today.isoformat(),))
        self.assertIn('Test Student',self.client.get('/attendance/'+self.today.isoformat()).text)
        with self.app.app_context(), get_db() as db:
            db.execute("UPDATE class_schedule SET start_time='00:00',end_time=NULL WHERE day=?", (self.today.isoformat(),))
        response=self.client.post('/scan',data=self.card,headers={
            'Content-Type':'text/plain','X-Device-Token':'test-device-token'})
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.client.post(url,data={**form,'decision':'default'}).status_code,303)
        with self.app.app_context():
            self.assertEqual(record(self.card)[0],423)
            self.assertEqual(get_db().execute('SELECT count(*) FROM eligibility_decisions').fetchone()[0],2)

    def test_teacher_can_drop_before_threshold_without_altering_attendance(self):
        response=self.client.post('/students/S1/eligibility',data={
            'csrf':'test-csrf','decision':'dropped','reason':'Teacher confirmed withdrawal'})
        self.assertEqual(response.status_code,303)
        with self.app.app_context():
            self.assertEqual(absence_count('S1'),0)
            self.assertEqual(record(self.card)[0],423)
        self.assertIn('Dropped / QR blocked',self.client.get('/audit').text)


if __name__ == '__main__':
    unittest.main()
