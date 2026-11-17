
from flask import Blueprint, jsonify
from app.utils import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    return jsonify({
        "message": "Selamat datang di dashboard admin SportReserve.",
        "role": "admin"
    }), 200
