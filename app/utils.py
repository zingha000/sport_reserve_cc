from functools import wraps
from flask import session, jsonify, redirect, url_for, abort


def login_required(func):
    """Untuk endpoint API: balas JSON 401 bila belum login."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "message": "Silakan login terlebih dahulu."
            }), 401

        return func(*args, **kwargs)

    return wrapper


def login_required_page(func):
    """Untuk halaman HTML: arahkan ke halaman login bila belum login."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login_page"))

        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    """Untuk endpoint API admin: balas JSON 401/403."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "message": "Silakan login terlebih dahulu."
            }), 401

        if session.get("role") != "admin":
            return jsonify({
                "message": "Anda tidak memiliki akses admin."
            }), 403

        return func(*args, **kwargs)

    return wrapper


def admin_required_page(func):
    """Untuk halaman HTML admin: ke login bila belum login, 403 bila bukan admin."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login_page"))

        if session.get("role") != "admin":
            abort(403)

        return func(*args, **kwargs)

    return wrapper