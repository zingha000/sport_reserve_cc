
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import get_db_connection
from app.utils import login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    nama = data.get("nama", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not nama or not email or not password:
        return jsonify({
            "message": "Nama, email, dan password wajib diisi."
        }), 400

    if len(password) < 8:
        return jsonify({
            "message": "Password minimal 8 karakter."
        }), 400

    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (nama, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id_user, nama, email, role;
                """, (nama, email, password_hash))

                user = cur.fetchone()

        return jsonify({
            "message": "Registrasi berhasil.",
            "user": user
        }), 201

    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({
                "message": "Email sudah terdaftar."
            }), 409

        return jsonify({
            "message": "Terjadi kesalahan pada server."
        }), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({
            "message": "Email dan password wajib diisi."
        }), 400

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id_user, nama, email, password_hash, role
                FROM users
                WHERE email = %s AND status_akun = 'aktif';
            """, (email,))

            user = cur.fetchone()

    if not user or not check_password_hash(
        user["password_hash"], password
    ):
        return jsonify({
            "message": "Email atau password salah."
        }), 401

    session.clear()
    session["user_id"] = user["id_user"]
    session["nama"] = user["nama"]
    session["role"] = user["role"]

    return jsonify({
        "message": "Login berhasil.",
        "user": {
            "id_user": user["id_user"],
            "nama": user["nama"],
            "email": user["email"],
            "role": user["role"]
        }
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "message": "Logout berhasil."
    }), 200

@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({
        "message": "Session aktif.",
        "user": {
            "id_user": session["user_id"],
            "nama": session["nama"],
            "role": session["role"]
        }
    }), 200
