from flask import Blueprint, jsonify, session, url_for

from app.database import get_db_connection
from app.utils import login_required


notifications_bp = Blueprint(
    "notifications", __name__, url_prefix="/notifications"
)

LIST_LIMIT = 10

SQL_LIST = """
    SELECT
        id_notifikasi,
        id_reservasi,
        jenis,
        judul,
        pesan,
        dibaca,
        TO_CHAR(
            dibuat_pada AT TIME ZONE 'Asia/Jakarta', 'DD-MM-YYYY HH24:MI'
        ) AS waktu
    FROM notifikasi
    WHERE id_user = %s
    ORDER BY dibuat_pada DESC, id_notifikasi DESC
    LIMIT %s;
"""

SQL_UNREAD = """
    SELECT COUNT(*) AS total
    FROM notifikasi
    WHERE id_user = %s AND dibaca = FALSE;
"""

SQL_MARK_READ = """
    UPDATE notifikasi
    SET dibaca = TRUE
    WHERE id_user = %s AND dibaca = FALSE;
"""


def _detail_url(reservation_id):
    # Halaman detail pelanggan berada satu level di atas /payment-proof.
    proof = url_for("reservations.payment_proof", reservation_id=reservation_id)
    return proof.rsplit("/payment-proof", 1)[0]


@notifications_bp.route("", methods=["GET"])
@login_required
def list_notifications():
    user_id = session["user_id"]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LIST, (user_id, LIST_LIMIT))
            rows = cur.fetchall()

            cur.execute(SQL_UNREAD, (user_id,))
            unread = cur.fetchone()["total"]

    return jsonify({
        "success": True,
        "unread": int(unread),
        "items": [
            {
                "id": row["id_notifikasi"],
                "jenis": row["jenis"],
                "judul": row["judul"],
                "pesan": row["pesan"],
                "dibaca": row["dibaca"],
                "waktu": row["waktu"],
                "url": (
                    _detail_url(row["id_reservasi"])
                    if row["id_reservasi"] else None
                )
            }
            for row in rows
        ]
    })


@notifications_bp.route("/read", methods=["POST"])
@login_required
def mark_read():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_MARK_READ, (session["user_id"],))

    return jsonify({"success": True})
