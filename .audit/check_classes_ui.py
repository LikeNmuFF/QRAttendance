"""Optional Playwright workflow check, using an isolated database and local server."""
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / '.venv' / 'Lib' / 'site-packages'))
sys.path.insert(0, str(root / 'python'))

from attendance import create_app
from attendance.db import PH, get_db, qr_payload
from playwright.sync_api import sync_playwright
from waitress import create_server


with tempfile.TemporaryDirectory() as directory:
    app = create_app(dict(TESTING=True, DATABASE=Path(directory)/'ui.db',
                         ADMIN_PASSWORD='test-admin-password', ATTENDANCE_TOKEN='device-test', SECRET_KEY='ui-test'))
    with app.test_client() as setup:
        with setup.session_transaction() as login:
            login.update(admin=True, csrf='setup')
        assert setup.post('/students', data={'csrf':'setup', 'id':'S1', 'name':'Maria Shared'}).status_code == 303
    server = create_server(app, host='127.0.0.1', port=0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.effective_port)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base+'/login')
            page.get_by_label('Username', exact=True).fill('admin')
            page.get_by_label('Password', exact=True).fill('test-admin-password')
            page.get_by_role('button', name='Sign in', exact=True).click()
            page.wait_for_url('**/dashboard')
            page.get_by_role('link', name='Classes & sessions', exact=True).click()
            page.get_by_label('Class name', exact=True).fill('Mathematics')
            page.get_by_role('button', name='Create class', exact=True).click()
            page.wait_for_url('**/classes?**')
            page.get_by_label('Enroll an existing student', exact=True).select_option('S1')
            page.get_by_role('button', name='Enroll in this class', exact=True).click()
            assert page.get_by_role('cell', name='Maria Shared', exact=True).is_visible()
            page.get_by_label('New session name', exact=True).fill('Afternoon')
            page.get_by_role('button', name='Add session', exact=True).click()
            page.wait_for_url('**/dashboard?**')
            assert page.locator('#workspace-session option:checked').inner_text() == 'Afternoon'
            page.locator('#start-time').fill('00:00')
            page.get_by_role('button', name='Save session hours', exact=True).click()
            page.get_by_role('button', name='Use Afternoon for scanning', exact=True).click()
            assert 'Mathematics / Afternoon' in page.locator('[data-live-part="scanner-target"]').inner_text()
            with app.app_context():
                card = qr_payload('S1')
            with app.test_client() as device:
                assert device.post('/scan',data=card,headers={'Content-Type':'text/plain','X-Device-Token':'device-test'}).status_code == 201
            page.get_by_role('cell', name='Maria Shared', exact=True).wait_for()
            page.get_by_role('link', name='Calendar', exact=True).click()
            assert 'Afternoon' in page.locator('.context-note').inner_text()
            month_form = page.locator('form.date-filter')
            month_form.get_by_role('button',name='Go',exact=True).click()
            assert 'session_id=' in page.url
            page.get_by_role('link', name='Students & QR cards',exact=True).click()
            with page.expect_download() as download:
                page.get_by_role('button',name='Download all PDF',exact=True).click()
            assert Path(download.value.path()).read_bytes().startswith(b'%PDF')
            assert 'session_id=' in page.url
            # Class selection starts at its first session; browsing leaves scanner alone.
            page.locator('#workspace-class').select_option('1')
            page.get_by_role('button',name='Open class',exact=True).click()
            assert page.locator('#workspace-class option:checked').inner_text() == 'Default class'
            assert 'Mathematics / Afternoon' in page.locator('[data-live-part="scanner-target"]').inner_text()
            with app.app_context():
                cid,sid=get_db().execute("SELECT class_id,id FROM class_sessions WHERE name='Afternoon'").fetchone()
            routes = [('/classes', 'classes'),('/dashboard','attendance'),('/students','students'),
                      ('/calendar','calendar'),('/audit','audit'),
                      ('/attendance/'+datetime.now(PH).date().isoformat(),'review')]
            for width,height,label in [(1440,1000,'desktop'),(390,844,'mobile')]:
                page.set_viewport_size({'width':width,'height':height})
                for route,name in routes:
                    response=page.goto(base+route+f'?class_id={cid}&session_id={sid}')
                    assert response.status == 200, (route,response.status)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (route,label,'page overflow')
                    assert page.locator('#workspace-class option:checked').inner_text() == 'Mathematics'
                    assert page.locator('#workspace-session option:checked').inner_text() == 'Afternoon'
                    page.screenshot(path=str(root/'.audit'/f'new-classes-{name}-{label}.png'),full_page=True)
            assert not errors, errors
            browser.close()
            print('Browser workflows passed: classes, enrollment, sessions, scanner, live attendance, PDF, navigation; six pages at desktop/mobile sizes.')
    finally:
        server.close()
        server.task_dispatcher.shutdown()
        thread.join(timeout=2)
