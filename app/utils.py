from functools import wraps
from flask import session, jsonify


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "message": "Silakan login terlebih dahulu."
            }), 401

        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
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