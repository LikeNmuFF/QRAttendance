import sys, tempfile, threading, fitz
from pathlib import Path
from datetime import datetime, timedelta
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.venv'/'Lib'/'site-packages'))
sys.path.insert(0,str(root/'python'))
from attendance import create_app
from attendance.db import get_db,replace_card,PH
from waitress import create_server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as directory:
    app=create_app(dict(DATABASE=Path(directory)/'ui.db',ADMIN_PASSWORD='test-admin-password',ATTENDANCE_TOKEN='test-device-token',SECRET_KEY='preview'))
    today=datetime.now(PH).date()
    days=[(today-timedelta(days=n)).isoformat() for n in (5,4,3,2,1)]
    with app.app_context(),get_db() as db:
        for sid,name in [('S1','Maria Dela Cruz'),('S2','Juan Santos')]:
            db.execute('INSERT INTO students VALUES (?,?)',(sid,name))
            db.execute('INSERT INTO enrollment VALUES (?,?)',(sid,days[0]))
            replace_card(sid)
        for day in days:
            db.execute("INSERT INTO class_schedule(day,start_time,end_time) VALUES (?,'08:00','10:00')",(day,))
        for day in days[1:]:
            db.execute("INSERT INTO attendance VALUES ('S1',?,'','absent')",(day,))
            db.execute("INSERT INTO attendance VALUES ('S2',?,?,'present')",(day,day+'T08:05:00+08:00'))
            db.execute('INSERT INTO class_reviews VALUES (?,?)',(day,day+'T10:01:00+08:00'))
    server=create_server(app,host='127.0.0.1',port=0)
    threading.Thread(target=server.run,daemon=True).start()
    base='http://127.0.0.1:'+str(server.effective_port)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(base+'/login')
            page.get_by_label('Username',exact=True).fill('admin')
            page.get_by_label('Password',exact=True).fill('test-admin-password')
            page.get_by_role('button',name='Sign in',exact=True).click()
            page.wait_for_url('**/dashboard')
            page.goto(base+'/students')
            with page.expect_download() as task:
                page.get_by_role('button',name='Download all PDF',exact=True).click()
            with fitz.open(task.value.path()) as document:
                assert 'Maria Dela Cruz' in document[0].get_text() and 'Juan Santos' in document[0].get_text()
            page.get_by_label('Select Maria Dela Cruz (S1)',exact=True).check()
            with page.expect_download() as task:
                page.get_by_role('button',name='Download selected PDF',exact=True).click()
            with fitz.open(task.value.path()) as document:
                assert 'Maria Dela Cruz' in document[0].get_text() and 'Juan Santos' not in document[0].get_text()
            with page.expect_download() as task:
                page.get_by_role('link',name='Download QR image for Maria Dela Cruz',exact=True).click()
            assert Path(task.value.path()).read_bytes().startswith(bytes([137,80,78,71]))
            page.get_by_label('Select Maria Dela Cruz (S1)',exact=True).uncheck()
            page.locator('#student-search').fill('Juan')
            page.get_by_label('Select visible students',exact=True).check()
            assert page.get_by_label('Select Juan Santos (S2)',exact=True).is_checked()
            assert not page.get_by_label('Select Maria Dela Cruz (S1)',exact=True).is_checked()
            page.get_by_label('Select visible students',exact=True).uncheck()
            page.locator('#student-search').fill('')
            routes=[('/dashboard','attendance'),('/students','students'),('/calendar','calendar'),('/audit','audit'),('/attendance/'+days[0],'day-review')]
            for width,height,label in [(1440,1000,'desktop'),(390,844,'mobile')]:
                page.set_viewport_size(dict(width=width,height=height))
                for route,name in routes:
                    response=page.goto(base+route)
                    assert response.status==200,(route,response.status)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(route,width)
                    page.screenshot(path=str(root/'.audit'/('new-'+name+'-'+label+'.png')),full_page=True)
            page.set_viewport_size(dict(width=1440,height=1000))
            page.goto(base+'/audit')
            row=page.get_by_role('row').filter(has_text='Maria Dela Cruz').first
            assert 'Dropped / QR blocked' in row.inner_text()
            row.locator('summary').click()
            row.locator('select').select_option('chance')
            row.get_by_label('Reason',exact=True).fill('Teacher approved an additional chance')
            row.get_by_role('button',name='Save teacher decision').click()
            page.wait_for_url('**/audit?student=S1')
            assert 'Chance granted' in page.get_by_role('row').filter(has_text='Maria Dela Cruz').first.inner_text()
            page.goto(base+'/attendance/'+days[0])
            page.get_by_role('checkbox').check()
            page.get_by_role('button',name='Finalize attendance').click()
            page.wait_for_load_state('networkidle')
            assert 'Finalized at' in page.locator('.notice').last.inner_text()
            assert not errors,errors
            browser.close()
            print('PASS: desktop/mobile pages, no horizontal overflow, no JS errors, bulk/individual downloads, visible selection, teacher chance and day finalization in Chromium')
    finally:
        server.close()
        server.task_dispatcher.shutdown()
