"""Class/session context, roster management, and the shared scanner selection."""
import sqlite3
import unicodedata
from datetime import datetime

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from .db import PH, get_db, scanner_target

SCOPED = {
    'dashboard', 'students_page', 'save_schedule', 'register_student', 'print_student',
    'replace_student_qr', 'student_qr', 'download_student_qrs', 'student_cards_pdf',
    'report', 'calendar_page', 'day_attendance', 'finalize_day', 'correct_attendance',
    'audit_page', 'decide_eligibility', 'classes_page', 'create_class', 'create_session',
    'enroll_student', 'activate_scanner',
}


def class_students():
    return get_db().execute("""SELECT s.id,s.name FROM students s JOIN enrollment e
        ON e.student_id=s.id WHERE e.class_id=? ORDER BY s.id""", (g.class_id,)).fetchall()


def valid_name(value):
    value = value.strip()
    if not 1 <= len(value) <= 80 or any(unicodedata.category(c).startswith('C') for c in value):
        abort(400, 'Use a name of 1–80 characters without control characters.')
    return value


def init_class_routes(web, admin_required, require_csrf, csrf_token):
    @web.before_request
    def select_context():
        if not session.get('admin') or request.endpoint not in {'web.' + name for name in SCOPED}:
            return
        db = get_db()
        class_value = request.args.get('class_id', request.form.get('class_id'))
        session_value = request.args.get('session_id', request.form.get('session_id'))
        try:
            class_id = int(class_value) if class_value is not None else None
            session_id = int(session_value) if session_value is not None else None
        except (ValueError, TypeError):
            abort(400, 'Choose a valid class and session.')
        if session_id is not None:
            selected = db.execute('SELECT id,class_id,name FROM class_sessions WHERE id=?', (session_id,)).fetchone()
            if not selected or (class_id is not None and selected[1] != class_id):
                abort(404, 'This session does not belong to the selected class.')
            class_id = selected[1]
        else:
            class_id = class_id if class_id is not None else 1
            selected = db.execute('SELECT id,class_id,name FROM class_sessions WHERE class_id=? ORDER BY id LIMIT 1', (class_id,)).fetchone()
            if not selected:
                abort(404, 'Class not found. Choose a class from the workspace.')
        g.class_id, g.session_id = class_id, selected[0]
        g.current_session = selected
        g.current_class = db.execute('SELECT id,name FROM classes WHERE id=?', (class_id,)).fetchone()

    @web.url_defaults
    def scoped_urls(endpoint, values):
        if endpoint.removeprefix('web.') not in SCOPED or not hasattr(g, 'class_id'):
            return
        # Keep old default-class links working; other contexts always travel in the URL.
        if g.class_id != 1 or g.session_id != 1:
            values.setdefault('class_id', g.class_id)
            values.setdefault('session_id', g.session_id)

    @web.context_processor
    def class_context():
        if not hasattr(g, 'class_id'):
            return {}
        db = get_db()
        return dict(current_class=g.current_class, current_session=g.current_session,
                    class_id=g.class_id, session_id=g.session_id,
                    classes=db.execute('SELECT id,name FROM classes ORDER BY name').fetchall(),
                    sessions=db.execute('SELECT id,name FROM class_sessions WHERE class_id=? ORDER BY id', (g.class_id,)).fetchall(),
                    scanner=scanner_target(), today=datetime.now(PH).date().isoformat())

    @web.get('/classes')
    @admin_required
    def classes_page():
        db = get_db()
        available = db.execute('''SELECT id,name FROM students WHERE id NOT IN
            (SELECT student_id FROM enrollment WHERE class_id=?) ORDER BY name,id''', (g.class_id,)).fetchall()
        return render_template('classes.html', page='classes', csrf=csrf_token(),
                               members=class_students(), available=available)

    @web.post('/classes')
    @admin_required
    def create_class():
        require_csrf()
        name = valid_name(request.form.get('name', ''))
        db = get_db()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                class_id = db.execute('INSERT INTO classes(name) VALUES (?)', (name,)).lastrowid
                session_id = db.execute("INSERT INTO class_sessions(class_id,name) VALUES (?,'Daily session')", (class_id,)).lastrowid
                db.execute('UPDATE scanner_target SET session_id=NULL,day=NULL,revision=revision+1 WHERE day IS NULL')
        except sqlite3.IntegrityError:
            abort(409, 'A class with this name already exists. Choose another name.')
        flash('Class created. Enroll students and set this session’s hours to get started.')
        return redirect(url_for('web.classes_page', class_id=class_id, session_id=session_id), code=303)

    @web.post('/classes/sessions')
    @admin_required
    def create_session():
        require_csrf()
        name = valid_name(request.form.get('name', ''))
        db = get_db()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                sid = db.execute('INSERT INTO class_sessions(class_id,name) VALUES (?,?)', (g.class_id,name)).lastrowid
                db.execute('UPDATE scanner_target SET session_id=NULL,day=NULL,revision=revision+1 WHERE day IS NULL')
        except sqlite3.IntegrityError:
            abort(409, 'This class already has a session with that name.')
        flash('Session created. Set its hours from Attendance, then select it for scanning.')
        return redirect(url_for('web.dashboard', class_id=g.class_id, session_id=sid), code=303)

    @web.post('/classes/enroll')
    @admin_required
    def enroll_student():
        require_csrf()
        sid = request.form.get('student_id', '')
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM students WHERE id=?', (sid,)).fetchone():
                abort(404, 'Student not found. Register the student first.')
            inserted = db.execute('''INSERT INTO enrollment(student_id,joined_on,class_id) VALUES (?,?,?)
                ON CONFLICT(student_id,class_id) DO NOTHING''', (sid,datetime.now(PH).date().isoformat(),g.class_id)).rowcount
            if not inserted:
                abort(409, 'This student is already enrolled in this class.')
        flash('Student enrolled from today. Their existing QR card works for every session in this class.')
        return redirect(url_for('web.classes_page'), code=303)

    @web.post('/scanner/session')
    @admin_required
    def activate_scanner():
        require_csrf()
        from .routes import valid_day
        day = valid_day(request.form.get('date', ''))
        if day != datetime.now(PH).date().isoformat():
            abort(409, 'The scanner can only record attendance for today.')
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM class_schedule WHERE session_id=? AND day=?', (g.session_id,day)).fetchone():
                abort(409, 'Save this session’s hours before selecting it for scanning.')
            if db.execute('SELECT 1 FROM class_reviews WHERE session_id=? AND day=?', (g.session_id,day)).fetchone():
                abort(409, 'This session is finalized. Select another session.')
            db.execute('UPDATE scanner_target SET session_id=?,day=?,revision=revision+1 WHERE id=1', (g.session_id,day))
        flash('Scanner selected: ' + g.current_class[1] + ' / ' + g.current_session[2] + '. All scanner requests now use this session.')
        return redirect(url_for('web.dashboard', date=day), code=303)
