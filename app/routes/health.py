from flask import Blueprint, current_app, jsonify

from app import storage
from app.database import ping_database

health_bp = Blueprint("health", __name__)


def _database_status():
    try:
        ping_database(timeout_seconds=3)
        return "ok"
    except Exception:
        current_app.logger.exception("Health check database gagal")
        return "error"


def _storage_status():
    try:
        storage.ping()
        return "ok"
    except Exception:
        current_app.logger.exception("Health check storage gagal")
        return "error"


@health_bp.route("/health", methods=["GET"])
def health():
    database = _database_status()
    storage_status = _storage_status()
    healthy = database == "ok" and storage_status == "ok"

    return (
        jsonify(
            {
                "status": "ok" if healthy else "error",
                "database": database,
                "storage": storage_status,
            }
        ),
        200 if healthy else 503,
    )
