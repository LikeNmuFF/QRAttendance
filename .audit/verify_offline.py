import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.venv' / 'Lib' / 'site-packages'))
sys.path.insert(0, str(ROOT / 'python'))
import socket
from urllib.parse import urlsplit
original_connect = socket.socket.connect
def local_connections_only(sock, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', 'localhost', '::1'):
        raise AssertionError('Unexpected external server connection')
    return original_connect(sock, address)
socket.socket.connect = local_connections_only
import tempfile
import threading
import cv2
import numpy as np
import fitz
from attendance import create_app
from waitress import create_server
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as directory:
    app = create_app(dict(DATABASE=Path(directory)/'ui.db', ADMIN_PASSWORD='test-admin-password',
                          ATTENDANCE_TOKEN='test-device-token', SECRET_KEY='ui-test-key'))
    server = create_server(app, host='127.0.0.1', port=0)
    threading.Thread(target=server.run, daemon=True).start()
    base = f'http://127.0.0.1:{server.effective_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(service_workers='block')
            external = []
            def local_requests_only(route):
                if urlsplit(route.request.url).netloc != urlsplit(base).netloc:
                    external.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()
            context.route('**/*', local_requests_only)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_viewport_size({'width':1280, 'height':1000})
            page.goto(base)
            assert page.get_by_role('heading',name='Less roll call. More class time.').is_visible()
            assert page.evaluate('document.compatMode') == 'CSS1Compat'
            for width,height,name in ((1440,1100,'landing-desktop'),(768,1024,'landing-tablet'),(375,812,'landing-mobile'),(812,375,'landing-landscape')):
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
                page.screenshot(path=str(ROOT/'.audit'/f'{name}.png'),full_page=True)
            page.emulate_media(reduced_motion='reduce')
            assert page.locator('.scanner-object').evaluate("el => getComputedStyle(el).animationName") == 'none'
            page.emulate_media(reduced_motion='no-preference')
            page.goto(base+'/dashboard')
            assert page.url.endswith('/login')
            for width, height, name in ((1280,1000,'login-desktop'),(390,844,'login-mobile')):
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'.audit'/f'{name}.png'), full_page=True)
            page.get_by_label('Username', exact=True).fill('admin')
            page.get_by_label('Password', exact=True).fill('wrong-password')
            page.get_by_role('button', name='Sign in', exact=True).click()
            assert page.get_by_role('alert').is_visible()
            page.get_by_label('Username', exact=True).fill('admin')
            page.get_by_label('Password', exact=True).fill('test-admin-password')
            page.get_by_role('button',name='Show password',exact=True).click()
            assert page.locator('#password').get_attribute('type') == 'text'
            page.get_by_role('button',name='Hide password',exact=True).click()
            page.get_by_role('button', name='Sign in', exact=True).click()
            assert page.get_by_role('heading', name='Attendance overview', exact=True).is_visible()
            page.locator('#start-time').fill('00:00')
            page.get_by_role('button', name='Save class time', exact=True).click()
            assert page.get_by_role('status').is_visible()
            page.get_by_label('Student ID', exact=True).fill('2026-001')
            page.get_by_label('Full name', exact=True).fill('Maria Dela Cruz')
            page.get_by_role('button', name='Register & create QR', exact=True).click()
            assert page.url.endswith('/students/2026-001/print')
            assert page.get_by_role('status').is_visible()
            image = page.locator('.qr-image')
            image.wait_for()
            assert image.evaluate("async (img) => { await img.decode(); return img.naturalWidth > 0; }")
            for width, height, name in ((1280,1000,'card-desktop'),(390,844,'card-mobile')):
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'.audit'/f'{name}.png'), full_page=True)
            with page.expect_download() as download:
                page.get_by_role('link', name='Download QR image').click()
            assert download.value.suggested_filename == 'student-2026-001.png'
            png = (context.request.get(base+'/students/2026-001/qr.png')).body()
            decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_GRAYSCALE))
            assert decoded == '2026-001', repr(decoded)
            page.evaluate('window.print = () => { window.didPrint = true; }')
            page.get_by_role('button',name='Print QR card',exact=True).click()
            assert page.evaluate('window.didPrint')
            page.pdf(path=str(ROOT/'.audit/student-card.pdf'), format='A4', print_background=True)
            with fitz.open(ROOT/'.audit/student-card.pdf') as pdf:
                assert len(pdf) == 1
                assert pdf[0].get_pixmap().pixel(0,0)[:3] == (255,255,255)
                text = pdf[0].get_text()
                assert 'Maria Dela Cruz' in text and '2026-001' in text
                assert 'Download QR image' not in text and 'Student QR card' not in text
                pdf[0].get_pixmap(matrix=fitz.Matrix(1,1)).save(ROOT/'.audit/card-print.png')
            scan = context.request.post(base+'/scan', data=decoded, headers={'X-Device-Token':'test-device-token','Content-Type':'text/plain'})
            assert scan.status == 201 and scan.text() == 'Attendance saved: late'
            duplicate = context.request.post(base+'/scan',data=decoded,headers={'X-Device-Token':'test-device-token','Content-Type':'text/plain'})
            assert duplicate.status == 409
            page.get_by_role('link', name='Return to dashboard').click()
            assert page.get_by_text('1 recorded',exact=True).is_visible()
            assert page.get_by_role('cell',name='Late',exact=True).is_visible()
            assert page.get_by_role('button',name='Save class time',exact=True).is_disabled()
            page.get_by_label('Search attendance',exact=True).fill('missing-student')
            assert page.locator('#attendance-table .search-empty').is_visible()
            page.get_by_label('Search attendance',exact=True).fill('Maria')
            assert page.locator('#attendance-table [data-search-row]').is_visible()
            page.get_by_label('Search attendance',exact=True).fill('')
            page.get_by_label('Search registered students',exact=True).fill('missing-student')
            assert page.locator('#student-table .search-empty').is_visible()
            page.get_by_label('Search registered students',exact=True).fill('')
            for width,height,name in ((1280,1100,'desktop'),(768,1024,'tablet'),(390,844,'mobile')):
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'.audit'/f'{name}.png'),full_page=True)
            with page.expect_download() as download:
                page.get_by_role('link',name='Export CSV').click()
            assert download.value.suggested_filename.startswith('attendance-')
            csrf = page.locator('form[action="/students"] input[name="csrf"]').input_value()
            sid = 'A' * 40
            response = context.request.post(base+'/students',form={'csrf':csrf,'id':sid,'name':'Maximum ID Student'})
            assert response.status == 200
            png = context.request.get(base+f'/students/{sid}/qr.png').body()
            decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_GRAYSCALE))
            assert decoded == sid
            page.get_by_role('button',name='Sign out',exact=True).click()
            assert page.url.endswith('/login')
            page.goto(base+'/dashboard')
            assert page.url.endswith('/login')
            assert not errors, errors
            assert not external, external
            print('PASS: all internet page requests blocked, no external requests attempted; server connections restricted to loopback',flush=True)
            print('PASS: Waitress + browser login/logout, class time, registration, QR decode, print button/PDF, late scan, duplicates, CSV and responsive layout',flush=True)
            print('PASS: OpenCV independently decoded both a normal ID and a 40-character ID from generated QR images',flush=True)
            browser.close()
    finally:
        server.close()
        server.task_dispatcher.shutdown()


