from flask import (
    Blueprint,
    abort,
    jsonify,
    render_template,
    request,
    session
)
from psycopg.types.json import Json

from app.database import get_db_connection
from app.routes.reservations import _decorate, _expire_holds
from app.utils import admin_required, admin_required_page


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

STATUS_FILTERS = [
    ("menunggu", "Perlu verifikasi"),
    ("ditahan", "Menunggu pembayaran"),
    ("dikonfirmasi", "Dikonfirmasi"),
    ("dibatalkan", "Dibatalkan"),
    ("kedaluwarsa", "Kedaluwarsa"),
    ("semua", "Semua"),
]

DEFAULT_FILTER = "menunggu"
LIST_LIMIT = 200
OVERVIEW_LIMIT = 5
MAX_NOTE_LENGTH = 500

# ----------------------------------------------------------------------
# SQL
# ----------------------------------------------------------------------

SQL_ADMIN_SELECT = """
    SELECT
        r.id_reservasi,
        l.nama_lapangan,
        u.nama AS nama_pelanggan,
        u.email,
        u.no_telepon,
        r.tanggal,
        r.jam_mulai,
        r.jam_selesai,
        r.durasi_jam,
        r.harga_per_jam,
        r.total_harga,
        r.status_reservasi,
        r.dibuat_pada AT TIME ZONE 'Asia/Jakarta' AS dibuat_wib,
        p.id_pembayaran,
        p.kode_transaksi,
        p.status_pembayaran,
        p.bukti_object_key,
        p.catatan_admin,
        p.channel_pembayaran,
        p.diverifikasi_pada AT TIME ZONE 'Asia/Jakarta' AS diverifikasi_wib
    FROM reservasi r
    JOIN lapangan l ON l.id_lapangan = r.id_lapangan
    JOIN users u ON u.id_user = r.id_user
    LEFT JOIN LATERAL (
        SELECT id_pembayaran, kode_transaksi, status_pembayaran,
               bukti_object_key, catatan_admin, channel_pembayaran,
               diverifikasi_pada
        FROM pembayaran
        WHERE id_reservasi = r.id_reservasi
        ORDER BY id_pembayaran DESC
        LIMIT 1
    ) p ON TRUE
"""

SQL_COUNT_BY_STATUS = """
    SELECT status_reservasi, COUNT(*) AS jumlah
    FROM reservasi
    GROUP BY status_reservasi;
"""

SQL_OVERVIEW_EXTRA = """
    SELECT
        (SELECT COUNT(*) FROM lapangan WHERE status = 'aktif') AS lapangan_aktif,
        (SELECT COUNT(*) FROM lapangan) AS lapangan_total,
        (
            SELECT COALESCE(SUM(total_harga), 0)
            FROM reservasi
            WHERE status_reservasi IN ('dikonfirmasi', 'selesai')
        ) AS pendapatan;
"""
SQL_PAYMENT_METHOD = """
    SELECT nama_pemilik, nomor_akun
    FROM pengaturan_pembayaran
    WHERE LOWER(nama_ewallet) = LOWER(%s)
    ORDER BY status_aktif DESC, id_pengaturan DESC
    LIMIT 1;
"""

SQL_RESERVATION_LOG = """
    SELECT
        status_sebelumnya,
        status_sesudahnya,
        keterangan,
        dibuat_pada AT TIME ZONE 'Asia/Jakarta' AS waktu_wib
    FROM reservasi_log
    WHERE id_reservasi = %s
    ORDER BY id_log;
"""

SQL_LOCK_RESERVATION = """
    SELECT status_reservasi
    FROM reservasi
    WHERE id_reservasi = %s
    FOR UPDATE;
"""

SQL_LOCK_PAYMENT = """
    SELECT id_pembayaran
    FROM pembayaran
    WHERE id_reservasi = %s
      AND status_pembayaran = 'menunggu'
      AND bukti_object_key IS NOT NULL
    ORDER BY id_pembayaran DESC
    LIMIT 1
    FOR UPDATE;
"""

SQL_APPROVE_PAYMENT = """
    UPDATE pembayaran
    SET status_pembayaran = 'berhasil',
        paid_at = NOW(),
        diverifikasi_oleh = %s,
        diverifikasi_pada = NOW(),
        catatan_admin = NULL
    WHERE id_pembayaran = %s;
"""

SQL_REJECT_PAYMENT = """
    UPDATE pembayaran
    SET status_pembayaran = 'gagal',
        diverifikasi_oleh = %s,
        diverifikasi_pada = NOW(),
        catatan_admin = %s
    WHERE id_pembayaran = %s;
"""

SQL_SET_RESERVATION_STATUS = """
    UPDATE reservasi
    SET status_reservasi = %s
    WHERE id_reservasi = %s;
"""

SQL_LOG_RESERVATION = """
    INSERT INTO reservasi_log (
        id_reservasi,
        id_user,
        status_sebelumnya,
        status_sesudahnya,
        keterangan
    )
    VALUES (%s, %s, 'menunggu', %s, %s);
"""

SQL_LOG_PAYMENT = """
    INSERT INTO pembayaran_log (
        id_pembayaran,
        status_sebelumnya,
        status_sesudahnya,
        payload
    )
    VALUES (%s, 'menunggu', %s, %s);
"""


# ----------------------------------------------------------------------
# HALAMAN
# ----------------------------------------------------------------------

@admin_bp.route("/dashboard", methods=["GET"])
@admin_required_page
def dashboard():
    """Ringkasan: statistik dan reservasi yang perlu diverifikasi."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(SQL_COUNT_BY_STATUS)
            counts = {
                row["status_reservasi"]: row["jumlah"]
                for row in cur.fetchall()
            }

            cur.execute(SQL_OVERVIEW_EXTRA)
            extra = cur.fetchone()

            cur.execute(
                SQL_ADMIN_SELECT
                + " WHERE r.status_reservasi = 'menunggu'"
                + " ORDER BY r.dibuat_pada ASC LIMIT {};".format(
                    OVERVIEW_LIMIT
                )
            )
            pending = cur.fetchall()

    return render_template(
        "admin/dashboard.html",
        counts=counts,
        total=sum(counts.values()),
        extra=extra,
        pending=[_decorate(row) for row in pending],
        overview_limit=OVERVIEW_LIMIT
    )


@admin_bp.route("/reservations", methods=["GET"])
@admin_required_page
def reservation_list():
    valid_filters = {key for key, _ in STATUS_FILTERS}
    active_status = request.args.get("status", DEFAULT_FILTER)

    if active_status not in valid_filters:
        active_status = DEFAULT_FILTER

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(SQL_COUNT_BY_STATUS)
            counts = {
                row["status_reservasi"]: row["jumlah"]
                for row in cur.fetchall()
            }

            query = SQL_ADMIN_SELECT
            params = ()

            if active_status != "semua":
                query += " WHERE r.status_reservasi = %s"
                params = (active_status,)

            query += (
                " ORDER BY r.dibuat_pada DESC LIMIT {};".format(LIST_LIMIT)
            )
            cur.execute(query, params)
            rows = cur.fetchall()

    return render_template(
        "admin/reservations.html",
        filters=STATUS_FILTERS,
        active_status=active_status,
        counts=counts,
        total=sum(counts.values()),
        reservations=[_decorate(row) for row in rows],
        list_limit=LIST_LIMIT
    )


@admin_bp.route("/reservations/<int:reservation_id>", methods=["GET"])
@admin_required_page
def reservation_detail(reservation_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(
                SQL_ADMIN_SELECT + " WHERE r.id_reservasi = %s;",
                (reservation_id,)
            )
            row = cur.fetchone()

            if row is None:
                abort(404)

            cur.execute(SQL_RESERVATION_LOG, (reservation_id,))
            logs = cur.fetchall()

            method = None
            channel = row.get("channel_pembayaran")

            if channel:
                cur.execute(SQL_PAYMENT_METHOD, (channel,))
                method = cur.fetchone()

    return render_template(
        "admin/reservation_detail.html",
        reservation=_decorate(row),
        logs=logs,
        method=method
    )


# ----------------------------------------------------------------------
# AKSI VERIFIKASI / TOLAK PEMBAYARAN
# ----------------------------------------------------------------------

def _review_payment(reservation_id, approve, note=None):
    """Verifikasi atau tolak bukti pembayaran satu reservasi.

    Hanya reservasi berstatus 'menunggu' (bukti sudah diunggah) yang bisa
    ditinjau. Seluruh perubahan dilakukan dalam satu transaksi.

    KEPUTUSAN YANG PERLU DIKONFIRMASI TIM:
    - Diverifikasi -> reservasi 'dikonfirmasi', pembayaran 'berhasil'.
    - Ditolak      -> reservasi 'dibatalkan' (jadwal dilepas),
                      pembayaran 'gagal' + catatan admin; pelanggan
                      tidak bisa mengunggah ulang.
    """
    admin_id = session["user_id"]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(SQL_LOCK_RESERVATION, (reservation_id,))
            reservation = cur.fetchone()

            if reservation is None:
                return jsonify({
                    "success": False,
                    "message": "Reservasi tidak ditemukan."
                }), 404

            if reservation["status_reservasi"] != "menunggu":
                return jsonify({
                    "success": False,
                    "message": (
                        "Reservasi ini tidak sedang menunggu verifikasi."
                    )
                }), 409

            cur.execute(SQL_LOCK_PAYMENT, (reservation_id,))
            payment = cur.fetchone()

            if payment is None:
                return jsonify({
                    "success": False,
                    "message": "Bukti pembayaran tidak ditemukan."
                }), 409

            payment_id = payment["id_pembayaran"]

            if approve:
                new_payment_status = "berhasil"
                new_reservation_status = "dikonfirmasi"
                description = "Pembayaran diverifikasi admin."

                cur.execute(SQL_APPROVE_PAYMENT, (admin_id, payment_id))
            else:
                new_payment_status = "gagal"
                new_reservation_status = "dibatalkan"
                description = "Pembayaran ditolak admin: {}".format(note)

                cur.execute(
                    SQL_REJECT_PAYMENT,
                    (admin_id, note, payment_id)
                )

            cur.execute(
                SQL_SET_RESERVATION_STATUS,
                (new_reservation_status, reservation_id)
            )

            cur.execute(SQL_LOG_RESERVATION, (
                reservation_id,
                admin_id,
                new_reservation_status,
                description
            ))

            cur.execute(SQL_LOG_PAYMENT, (
                payment_id,
                new_payment_status,
                Json({"admin_id": admin_id, "catatan": note})
            ))

    return jsonify({
        "success": True,
        "message": (
            "Pembayaran berhasil diverifikasi. Reservasi dikonfirmasi."
            if approve
            else "Pembayaran ditolak. Reservasi dibatalkan."
        ),
        "reservation": {
            "id": reservation_id,
            "status": new_reservation_status
        }
    }), 200


@admin_bp.route(
    "/reservations/<int:reservation_id>/verify",
    methods=["POST"]
)
@admin_required
def verify_payment(reservation_id):
    return _review_payment(reservation_id, approve=True)


@admin_bp.route(
    "/reservations/<int:reservation_id>/reject",
    methods=["POST"]
)
@admin_required
def reject_payment(reservation_id):
    data = request.get_json(silent=True) or {}
    note = str(data.get("note") or "").strip()

    if not note:
        return jsonify({
            "success": False,
            "message": "Alasan penolakan wajib diisi."
        }), 400

    if len(note) > MAX_NOTE_LENGTH:
        return jsonify({
            "success": False,
            "message": "Alasan penolakan maksimal {} karakter.".format(
                MAX_NOTE_LENGTH
            )
        }), 400

    return _review_payment(reservation_id, approve=False, note=note)