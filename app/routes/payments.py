from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for
)

from app import storage
from app.database import get_db_connection
from app.utils import (
    admin_required,
    admin_required_page,
    login_required,
    login_required_page
)


payments_bp = Blueprint("payments", __name__, url_prefix="/payments")
admin_payments_bp = Blueprint(
    "admin_payments", __name__, url_prefix="/admin/payments"
)

EWALLETS = ("OVO", "GoPay", "DANA", "ShopeePay")
MAX_OWNER_LENGTH = 100
MAX_NUMBER_LENGTH = 50

SQL_LIST_ALL = """
    SELECT id_pengaturan, nama_pemilik, nama_ewallet, nomor_akun,
           status_aktif
    FROM pengaturan_pembayaran
    ORDER BY status_aktif DESC, id_pengaturan;
"""

SQL_LIST_ACTIVE = """
    SELECT id_pengaturan, nama_pemilik, nama_ewallet, nomor_akun
    FROM pengaturan_pembayaran
    WHERE status_aktif = TRUE
    ORDER BY nama_ewallet, id_pengaturan;
"""

SQL_GET_QR = """
    SELECT qr_object_key, status_aktif
    FROM pengaturan_pembayaran
    WHERE id_pengaturan = %s;
"""

SQL_INSERT = """
    INSERT INTO pengaturan_pembayaran (
        nama_pemilik, nama_ewallet, nomor_akun, qr_object_key, status_aktif
    )
    VALUES (%s, %s, %s, %s, TRUE)
    RETURNING id_pengaturan;
"""

SQL_TOGGLE = """
    UPDATE pengaturan_pembayaran
    SET status_aktif = NOT status_aktif,
        diperbarui_pada = NOW()
    WHERE id_pengaturan = %s
    RETURNING status_aktif;
"""

SQL_DELETE = """
    DELETE FROM pengaturan_pembayaran
    WHERE id_pengaturan = %s
    RETURNING qr_object_key;
"""


def _error(message, status=400):
    return jsonify({"success": False, "message": message}), status


# ----------------------------------------------------------------------
# SISI PELANGGAN
# ----------------------------------------------------------------------

@payments_bp.route("/methods", methods=["GET"])
@login_required
def list_methods():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LIST_ACTIVE)
            rows = cur.fetchall()

    return jsonify({
        "success": True,
        "methods": [
            {
                "id": row["id_pengaturan"],
                "ewallet": row["nama_ewallet"],
                "pemilik": row["nama_pemilik"],
                "nomor": row["nomor_akun"],
                "qr_url": url_for(
                    "payments.qr_image", method_id=row["id_pengaturan"]
                )
            }
            for row in rows
        ]
    })


@payments_bp.route("/qr/<int:method_id>", methods=["GET"])
@login_required_page
def qr_image(method_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_GET_QR, (method_id,))
            row = cur.fetchone()

    if row is None:
        abort(404)

    # QRIS nonaktif hanya boleh dilihat admin.
    if not row["status_aktif"] and session.get("role") != "admin":
        abort(404)

    try:
        url = storage.presigned_url(row["qr_object_key"])
    except storage.StorageError:
        abort(503)

    response = redirect(url, code=302)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@payments_bp.route("/qr/<int:method_id>/file", methods=["GET"])
@login_required_page
def qr_file(method_id):
    """Sajikan QRIS dari origin sendiri agar bisa diunduh/dibagikan."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_GET_QR, (method_id,))
            row = cur.fetchone()

    if row is None:
        abort(404)

    if not row["status_aktif"] and session.get("role") != "admin":
        abort(404)

    try:
        data, mime_type = storage.read_object(row["qr_object_key"])
    except storage.StorageError:
        abort(503)

    response = Response(data, mimetype=mime_type)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Content-Disposition"] = "inline"
    return response


# ----------------------------------------------------------------------
# SISI ADMIN
# ----------------------------------------------------------------------

@admin_payments_bp.route("", methods=["GET"])
@admin_required_page
def list_admin():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LIST_ALL)
            methods = cur.fetchall()

    return render_template(
        "admin/payments.html",
        methods=methods,
        ewallets=EWALLETS
    )


@admin_payments_bp.route("", methods=["POST"])
@admin_required
def create_method():
    ewallet = (request.form.get("ewallet") or "").strip()
    owner = (request.form.get("pemilik") or "").strip()
    number = (request.form.get("nomor") or "").strip()

    if ewallet not in EWALLETS:
        return _error("Pilih e-wallet yang valid.")

    if not owner:
        return _error("Nama merchant wajib diisi.")

    if len(owner) > MAX_OWNER_LENGTH:
        return _error(
            "Nama merchant maksimal {} karakter.".format(MAX_OWNER_LENGTH)
        )

    if len(number) > MAX_NUMBER_LENGTH:
        return _error(
            "Nomor akun maksimal {} karakter.".format(MAX_NUMBER_LENGTH)
        )

    uploaded = request.files.get("qr")

    if uploaded is None or not uploaded.filename:
        return _error("Pilih gambar QRIS terlebih dahulu.")

    data = uploaded.read()

    if not data:
        return _error("File kosong.")

    mime_type = storage.detect_image_type(data)

    if mime_type is None:
        return _error("Format gambar harus JPG, PNG, atau WebP.")

    try:
        key = storage.save_qris_image(data, mime_type)
    except storage.StorageError as error:
        return _error(str(error), 503)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    SQL_INSERT,
                    (owner, ewallet, number or None, key)
                )
                method_id = cur.fetchone()["id_pengaturan"]
    except Exception:
        storage.delete(key)
        raise

    return jsonify({
        "success": True,
        "message": "QRIS {} ditambahkan.".format(ewallet),
        "id": method_id
    }), 200


@admin_payments_bp.route("/<int:method_id>/toggle", methods=["POST"])
@admin_required
def toggle_method(method_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_TOGGLE, (method_id,))
            row = cur.fetchone()

    if row is None:
        return _error("QRIS tidak ditemukan.", 404)

    return jsonify({
        "success": True,
        "message": (
            "QRIS diaktifkan." if row["status_aktif"]
            else "QRIS dinonaktifkan. Pelanggan tidak melihatnya lagi."
        )
    }), 200


@admin_payments_bp.route("/<int:method_id>/delete", methods=["POST"])
@admin_required
def delete_method(method_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_DELETE, (method_id,))
            row = cur.fetchone()

    if row is None:
        return _error("QRIS tidak ditemukan.", 404)

    # Hapus berkas di cloud setelah baris database berhasil dihapus.
    storage.delete(row["qr_object_key"])

    return jsonify({"success": True, "message": "QRIS dihapus."}), 200
