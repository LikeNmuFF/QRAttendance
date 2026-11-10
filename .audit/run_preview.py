"""Local preview with disposable storage; stop with Ctrl+C."""
import sys
import tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'python'))
from attendance import create_app
from waitress import serve

with tempfile.TemporaryDirectory(prefix='qr-attendance-preview-') as directory:
    app = create_app({
        'DATABASE': Path(directory) / 'preview.db',
        'ADMIN_PASSWORD': 'test-admin-password',
        'ATTENDANCE_TOKEN': 'test-device-token',
    })
    print('Preview: http://localhost:5000 | username: admin | password: test-admin-password', flush=True)
    print('Temporary database; test registrations will be discarded when this preview stops.', flush=True)
    serve(app, host='127.0.0.1', port=5000, max_request_body_size=4096)
