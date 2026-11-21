import logging

import psycopg
from flask import jsonify, render_template, request
from psycopg_pool import PoolTimeout

log = logging.getLogger(__name__)

BUSY_MESSAGE = "Sedang diproses pengguna lain. Coba lagi sebentar."
UNAVAILABLE_MESSAGE = "Layanan sedang sibuk. Coba lagi dalam beberapa detik."

_RETRY_PREFIXES = ("/reservations", "/payments", "/admin")


def _wants_json():
    if request.is_json:
        return True

    accept = request.headers.get("Accept", "")

    if "application/json" in accept and "text/html" not in accept:
        return True

    if request.path.startswith("/payments"):
        return True

    if request.method != "GET" and request.path.startswith(_RETRY_PREFIXES):
        return True

    return request.accept_mimetypes.best == "application/json"


def _busy_response(error):
    log.exception("Operasi database dibatalkan: %s", error)

    if _wants_json():
        return jsonify({"success": False, "message": BUSY_MESSAGE}), 409

    return (
        render_template(
            "errors/503.html",
            title="Permintaan Sedang Diproses",
            message=BUSY_MESSAGE,
        ),
        409,
    )


def _unavailable_response(error):
    log.exception("Layanan database tidak tersedia: %s", error)

    headers = {"Retry-After": "5"}

    if _wants_json():
        return (
            jsonify({"success": False, "message": UNAVAILABLE_MESSAGE}),
            503,
            headers,
        )

    return (
        render_template(
            "errors/503.html",
            title="Layanan Sedang Sibuk",
            message=UNAVAILABLE_MESSAGE,
        ),
        503,
        headers,
    )


def register_error_handlers(app):
    app.register_error_handler(psycopg.errors.LockNotAvailable, _busy_response)
    app.register_error_handler(psycopg.errors.QueryCanceled, _busy_response)
    app.register_error_handler(psycopg.OperationalError, _unavailable_response)
    app.register_error_handler(PoolTimeout, _unavailable_response)
