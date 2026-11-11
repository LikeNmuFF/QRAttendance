"""Bulk QR downloads preserve the current signed cards and require teacher access."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np

from attendance import create_app
from attendance.db import get_db, qr_payload, record, replace_card


class QrDownloadTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = create_app(dict(TESTING=True, DATABASE=Path(directory.name)/'test.db',
            ADMIN_PASSWORD='test-admin-password', ATTENDANCE_TOKEN='test-device-token', SECRET_KEY='test'))
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(admin=True, csrf='test-csrf')
        with self.app.app_context(), get_db() as db:
            for sid in ('S1', 'S2', 'S3'):
                db.execute('INSERT INTO students VALUES (?,?)', (sid, 'Student '+sid))
                db.execute("INSERT INTO enrollment(student_id,joined_on) VALUES (?,'2000-01-01')", (sid,))
                replace_card(sid)
            self.original = {sid:qr_payload(sid) for sid in ('S1', 'S2', 'S3')}

    def archive(self, path='/students/qrcodes.zip'):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return zipfile.ZipFile(io.BytesIO(response.data))

    def test_all_pngs_decode_to_current_credentials_without_rotating(self):
        with self.archive() as archive:
            self.assertEqual(archive.namelist(), ['student-S1.png','student-S2.png','student-S3.png'])
            for sid, expected in self.original.items():
                image=cv2.imdecode(np.frombuffer(archive.read(f'student-{sid}.png'),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
                decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
                self.assertEqual(decoded, expected)
        with self.app.app_context():
            self.assertEqual({sid:qr_payload(sid) for sid in self.original}, self.original)

    def test_selection_exports_only_requested_students_once(self):
        with self.archive('/students/qrcodes.zip?mode=selected&student_id=S3&student_id=S1&student_id=S1') as archive:
            self.assertEqual(archive.namelist(), ['student-S1.png','student-S3.png'])

    def test_authentication_and_selection_validation(self):
        self.assertEqual(self.app.test_client().get('/students/qrcodes.zip').status_code,303)
        for query, code in [('mode=selected',400),('mode=invalid',400),
                            ('mode=selected&student_id=missing',404),('mode=selected&student_id=../bad',400)]:
            self.assertEqual(self.client.get('/students/qrcodes.zip?'+query).status_code,code)
        with self.app.app_context(), get_db() as db:
            db.execute('DELETE FROM students')
        self.assertEqual(self.client.get('/students/qrcodes.zip').status_code,409)

    def test_individual_download_is_available_from_student_list(self):
        page=self.client.get('/students').text
        self.assertIn('/students/S1/qr.png?download=1',page)
        self.assertIn('Download selected',page)
        self.assertIn('Download all PDF',page)
        response=self.client.get('/students/S1/qr.png?download=1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/png')
        self.assertIn('attachment',response.headers['Content-Disposition'])

    def test_download_does_not_unblock_a_dropped_student(self):
        with self.app.app_context(), get_db() as db:
            db.execute("INSERT INTO eligibility_decisions(student_id,decision,reason,changed_at) VALUES ('S1','dropped','Teacher decision','2026-11-11T10:00:00+08:00')")
        with self.archive() as archive:
            self.assertIn('student-S1.png',archive.namelist())
        with self.app.app_context():
            self.assertEqual(record(self.original['S1'])[0],423)

    def test_printable_pdf_download_for_all_or_one_student(self):
        for query in ('', '?mode=selected&student_id=S2&message=Bring+this+card+to+class.'):
            response=self.client.get('/students/cards.pdf'+query)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'application/pdf')
            self.assertTrue(response.data.startswith(b'%PDF-'))
            self.assertIn('attachment',response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        with self.app.app_context():
            self.assertEqual(qr_payload('S2'),self.original['S2'])

    def test_pdf_rejects_invalid_selection_and_message(self):
        self.assertEqual(self.app.test_client().get('/students/cards.pdf').status_code,303)
        for query,code in [('mode=selected',400),('mode=selected&student_id=missing',404),
                            ('message='+('x'*81),400),('message=bad%0Amessage',400)]:
            self.assertEqual(self.client.get('/students/cards.pdf?'+query).status_code,code)


if __name__ == '__main__':
    unittest.main()
