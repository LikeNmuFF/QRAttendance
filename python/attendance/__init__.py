"""Flask configuration and shared error handling."""
import os
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path
from threading import Lock

from flask import Flask, request, render_template
from werkzeug.exceptions import HTTPException

from .db import close_db, init_db
from .camera import MAX_CAMERA_BYTES


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=Path(__file__).resolve().parent.parent / "attendance.db",
        ATTENDANCE_TOKEN=os.environ.get("ATTENDANCE_TOKEN", ""),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=4096,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if test_config:
        app.config.update(test_config)
    token = app.config["ATTENDANCE_TOKEN"]
    if not token or token in {"replace-with-your-own-device-token", "CHANGE_TO_YOUR_DEVICE_TOKEN"}:
        raise ValueError("Set ATTENDANCE_TOKEN to your own device token first.")
    if len(app.config["ADMIN_PASSWORD"]) < 12:
        raise ValueError("Set ADMIN_PASSWORD to at least 12 characters.")

    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    from .routes import web
    app.register_blueprint(web)
    app.extensions["camera_preview"] = {"frame": None, "lock": Lock(), "decode_lock": Lock()}

    @app.before_request
    def camera_upload_limit():
        if request.path == "/camera/frame" and request.method == "POST":
            request.max_content_length = MAX_CAMERA_BYTES

    def error_response(code, message):
        if request.path in {"/scan", "/camera/frame"}:
            return app.response_class(message, status=code, mimetype="text/plain")
        return render_template("error.html", code=code, message=message), code

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        event_id = secrets.token_hex(8)
        app.logger.exception("Database failure event=%s method=%s route=%s",
                             event_id, request.method, request.url_rule)
        response = app.make_response(error_response(
            503, "Database unavailable; attendance not confirmed. Please try again. Reference: " + event_id))
        response.headers["Retry-After"] = "5"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        body = app.make_response(error_response(error.code, error.description))
        response.set_data(body.get_data())
        response.content_type = body.content_type
        return response

    @app.errorhandler(500)
    def unexpected_error(error):
        return error_response(500, "The request could not be completed. Please try again.")

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob:; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
