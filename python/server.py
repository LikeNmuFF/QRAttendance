"""Start the offline attendance service: python server.py."""
import json
import os
import secrets
from pathlib import Path

from attendance import create_app


def load_settings(path):
    """Keep installation-specific credentials local; environment values override them."""
    keys = ("ADMIN_PASSWORD", "ATTENDANCE_TOKEN", "SECRET_KEY")
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
    else:
        settings = {key: os.environ.get(key) or secrets.token_urlsafe(24) for key in keys}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return {key: os.environ.get(key, settings[key]) for key in keys}


if __name__ == "__main__":
    from waitress import serve

    config_path = Path(__file__).with_name("instance") / "config.json"
    app = create_app(load_settings(config_path))
    print("QR Attendance: http://localhost:5000 | Administrator: /login", flush=True)
    print("Local settings: python/instance/config.json | Database: python/attendance.db", flush=True)
    print("No internet required. Keep this window open. Ctrl+C to stop.", flush=True)
    serve(app, host="0.0.0.0", port=5000, max_request_body_size=262144)
