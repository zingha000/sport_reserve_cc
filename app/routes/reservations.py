from datetime import date, time, datetime, timedelta
from decimal import Decimal
import secrets

from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    abort,
    current_app
)
from psycopg.errors import ExclusionViolation

from app import storage
from app.database import get_db_connection
from app.routes.fields import get_fields
from app.utils import login_required, login_required_page


reservations_bp = Blueprint(
    "reservations", __name__, url_prefix="/reservations"
)

HOLD_MINUTES = 10


def _parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_time(value):
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _minutes(value):
    return value.hour * 60 + value.minute


def _expire_holds(cur):
    """Kedaluwarsakan hold yang habis, beserta pembayaran 'menunggu'-nya,
    dan catat ke reservasi_log."""
    cur.execute("""
        WITH expired AS (
            UPDATE reservasi
            SET status_reservasi = 'kedaluwarsa',
                hold_expires_at = NULL
            WHERE status_reservasi = 'ditahan'
              AND hold_expires_at <= NOW()
            RETURNING id_reservasi
        ),
        expired_payments AS (
            UPDATE pembayaran
            SET status_pembayaran = 'kedaluwarsa'
            WHERE status_pembayaran = 'menunggu'
              AND id_reservasi IN (SELECT id_reservasi FROM expired)
            RETURNING id_pembayaran
        )
        INSERT INTO reservasi_log (
            id_reservasi,
            id_user,
            status_sebelumnya,
            status_sesudahnya,
            keterangan
        )
        SELECT
            id_reservasi,
            NULL,
            'ditahan',
            'kedaluwarsa',
            'Batas waktu penahanan jadwal habis.'
        FROM expired;
    """)


def _find_field(field_id):
    return next(
        (item for item in get_fields() if item["id"] == field_id),
        None
    )


def _get_tariff(cur, field_id, tanggal, start_time, end_time):
    cur.execute("""
        SELECT harga_per_jam
        FROM tarif_lapangan
        WHERE id_lapangan = %s
          AND hari = %s
          AND jam_mulai <= %s
          AND jam_selesai >= %s
          AND berlaku_mulai <= %s
          AND (berlaku_sampai IS NULL OR berlaku_sampai >= %s)
        ORDER BY id_tarif DESC
        LIMIT 1;
    """, (
        field_id,
        tanggal.isoweekday(),
        start_time,
        end_time,
        tanggal,
        tanggal
    ))

    return cur.fetchone()


@reservations_bp.route("/create/<int:field_id>")
def create_reservation(field_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))

    field = _find_field(field_id)

    if field is None:
        abort(404)

    return render_template(
        "reservations/create.html",
        field=field,
        customer_name=session.get("nama", "")
    )


@reservations_bp.route("/availability/<int:field_id>")
@login_required
def check_availability(field_id):
    tanggal = _parse_date(request.args.get("date"))

    if tanggal is None:
        return jsonify({
            "success": False,
            "message": "Tanggal tidak valid."
        }), 400

    if tanggal < date.today():
        return jsonify({
            "success": False,
            "message": "Tanggal sudah lewat."
        }), 400

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(
                "SELECT status FROM lapangan WHERE id_lapangan = %s;",
                (field_id,)
            )

            field = cur.fetchone()

            if field is None:
                return jsonify({
                    "success": False,
                    "message": "Lapangan tidak ditemukan."
                }), 404

            if field["status"] != "aktif":
                return jsonify({
                    "success": True,
                    "is_open": False,
                    "message": "Lapangan sedang tidak tersedia.",
                    "operational": None,
                    "reservations": []
                }), 200

            cur.execute("""
                SELECT jam_buka, jam_tutup
                FROM jam_operasional
                WHERE id_lapangan = %s
                  AND hari = %s
                  AND status = TRUE
                ORDER BY id_operasional
                LIMIT 1;
            """, (field_id, tanggal.isoweekday()))

            operational = cur.fetchone()

            if operational is None:
                return jsonify({
                    "success": True,
                    "is_open": False,
                    "message": "Lapangan tutup pada tanggal tersebut.",
                    "operational": None,
                    "reservations": []
                }), 200

            cur.execute("""
                SELECT jam_mulai, jam_selesai
                FROM reservasi
                WHERE id_lapangan = %s
                  AND tanggal = %s
                  AND (
                      status_reservasi IN ('menunggu', 'dikonfirmasi')
                      OR (
                          status_reservasi = 'ditahan'
                          AND hold_expires_at > NOW()
                      )
                  )
                ORDER BY jam_mulai;
            """, (field_id, tanggal))

            reservations = cur.fetchall()

    return jsonify({
        "success": True,
        "is_open": True,
        "message": "",
        "operational": {
            "open": operational["jam_buka"].strftime("%H:%M"),
            "close": operational["jam_tutup"].strftime("%H:%M")
        },
        "reservations": [
            {
                "start": item["jam_mulai"].strftime("%H:%M"),
                "end": item["jam_selesai"].strftime("%H:%M")
            }
            for item in reservations
        ]
    }), 200


SQL_CONFIRM_METHOD = """
    SELECT id_pengaturan, nama_ewallet, nama_pemilik, nomor_akun
    FROM pengaturan_pembayaran
    WHERE status_aktif = TRUE
      AND LOWER(nama_ewallet) = LOWER(%s)
    ORDER BY id_pengaturan
    LIMIT 1;
"""

SQL_IDEMPOTENT_HOLD = """
    SELECT
        r.id_reservasi,
        r.hold_expires_at,
        r.total_harga,
        l.nama_lapangan,
        p.kode_transaksi,
        p.channel_pembayaran,
        p.jumlah_pembayaran,
        pm.id_pengaturan,
        pm.nama_ewallet,
        pm.nama_pemilik,
        pm.nomor_akun
    FROM reservasi r
    JOIN lapangan l ON l.id_lapangan = r.id_lapangan
    LEFT JOIN LATERAL (
        SELECT kode_transaksi, channel_pembayaran, jumlah_pembayaran
        FROM pembayaran
        WHERE id_reservasi = r.id_reservasi
        ORDER BY id_pembayaran DESC
        LIMIT 1
    ) p ON TRUE
    LEFT JOIN LATERAL (
        SELECT id_pengaturan, nama_ewallet, nama_pemilik, nomor_akun
        FROM pengaturan_pembayaran
        WHERE status_aktif = TRUE
          AND LOWER(nama_ewallet) = LOWER(p.channel_pembayaran)
        ORDER BY id_pengaturan
        LIMIT 1
    ) pm ON TRUE
    WHERE r.id_user = %s
      AND r.id_lapangan = %s
      AND r.tanggal = %s
      AND r.jam_mulai = %s
      AND r.jam_selesai = %s
      AND r.status_reservasi = 'ditahan'
      AND r.hold_expires_at > NOW()
    ORDER BY r.id_reservasi DESC
    LIMIT 1;
"""


def _method_payload(method_id, ewallet, pemilik, nomor):
    return {
        "id": method_id,
        "ewallet": ewallet,
        "pemilik": pemilik,
        "nomor": nomor,
        "qr_url": (
            url_for("payments.qr_image", method_id=method_id)
            if method_id is not None else None
        )
    }


@reservations_bp.route("/confirm", methods=["POST"])
@login_required
def confirm_reservation():
    data = request.get_json(silent=True) or {}

    # Metode pembayaran wajib dipilih di langkah konfirmasi.
    channel_input = str(data.get("channel") or "").strip()

    if not channel_input:
        return jsonify({
            "success": False,
            "message": "Pilih metode pembayaran terlebih dahulu."
        }), 400

    field_id = data.get("field_id")
    tanggal = _parse_date(data.get("date"))
    start_time = _parse_time(data.get("start_time"))
    end_time = _parse_time(data.get("end_time"))

    try:
        duration = Decimal(str(data.get("duration")))
    except (ArithmeticError, ValueError):
        duration = None

    if (
        not field_id
        or tanggal is None
        or start_time is None
        or end_time is None
        or duration is None
    ):
        return jsonify({
            "success": False,
            "message": "Data reservasi tidak lengkap."
        }), 400

    if duration <= 0:
        return jsonify({
            "success": False,
            "message": "Durasi tidak valid."
        }), 400

    if _minutes(end_time) - _minutes(start_time) != int(duration * 60):
        return jsonify({
            "success": False,
            "message": "Rentang waktu tidak sesuai dengan durasi."
        }), 400

    start_at = datetime.combine(tanggal, start_time)

    if start_at <= datetime.now():
        return jsonify({
            "success": False,
            "message": "Jadwal yang dipilih sudah lewat."
        }), 400

    user_id = session["user_id"]
    max_holds = int(current_app.config.get("MAX_ACTIVE_HOLDS", 2))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Kunci level transaksi: aman untuk PgBouncer transaction mode.
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s);",
                    (user_id,)
                )

                _expire_holds(cur)

                cur.execute(SQL_IDEMPOTENT_HOLD, (
                    user_id,
                    field_id,
                    tanggal,
                    start_time,
                    end_time
                ))

                existing = cur.fetchone()

                if existing is not None:
                    method_payload = _method_payload(
                        existing["id_pengaturan"],
                        existing["nama_ewallet"]
                        or existing["channel_pembayaran"],
                        existing["nama_pemilik"],
                        existing["nomor_akun"]
                    )

                    return jsonify({
                        "success": True,
                        "idempotent": True,
                        "message": (
                            "Reservasi berhasil ditahan selama 10 menit."
                        ),
                        "reservation": {
                            "id": existing["id_reservasi"],
                            "field": existing["nama_lapangan"],
                            "date": tanggal.isoformat(),
                            "start_time": start_time.strftime("%H:%M"),
                            "end_time": end_time.strftime("%H:%M"),
                            "hold_expires_at": (
                                existing["hold_expires_at"].isoformat()
                            )
                        },
                        "payment": {
                            "transaction_code": existing["kode_transaksi"],
                            "amount": float(
                                existing["jumlah_pembayaran"]
                                or existing["total_harga"]
                            ),
                            "channel": (
                                existing["channel_pembayaran"]
                                or existing["nama_ewallet"]
                            ),
                            "method": method_payload
                        }
                    }), 200

                cur.execute("""
                    SELECT COUNT(*) AS jumlah
                    FROM reservasi
                    WHERE id_user = %s
                      AND status_reservasi = 'ditahan'
                      AND hold_expires_at > NOW();
                """, (user_id,))

                active_holds = cur.fetchone()["jumlah"]

                if active_holds >= max_holds:
                    return jsonify({
                        "success": False,
                        "message": (
                            "Selesaikan atau tunggu pembayaran reservasi "
                            "sebelumnya. Maksimal {} jadwal ditahan."
                        ).format(max_holds)
                    }), 409

                cur.execute(SQL_CONFIRM_METHOD, (channel_input,))
                method = cur.fetchone()

                if method is None:
                    return jsonify({
                        "success": False,
                        "message": (
                            "Metode pembayaran tidak tersedia. "
                            "Pilih metode lain."
                        )
                    }), 400

                cur.execute("""
                    SELECT status, nama_lapangan
                    FROM lapangan
                    WHERE id_lapangan = %s
                    FOR SHARE;
                """, (field_id,))

                field = cur.fetchone()

                if field is None:
                    return jsonify({
                        "success": False,
                        "message": "Lapangan tidak ditemukan."
                    }), 404

                if field["status"] != "aktif":
                    return jsonify({
                        "success": False,
                        "message": "Lapangan sedang tidak tersedia."
                    }), 409

                cur.execute("""
                    SELECT jam_buka, jam_tutup, status
                    FROM jam_operasional
                    WHERE id_lapangan = %s
                      AND hari = %s;
                """, (field_id, tanggal.isoweekday()))

                operational = cur.fetchone()

                if operational is None or not operational["status"]:
                    return jsonify({
                        "success": False,
                        "message": "Lapangan tutup pada hari tersebut."
                    }), 409

                if (
                    start_time < operational["jam_buka"]
                    or end_time > operational["jam_tutup"]
                ):
                    return jsonify({
                        "success": False,
                        "message": "Jadwal di luar jam operasional."
                    }), 409

                tariff = _get_tariff(
                    cur,
                    field_id,
                    tanggal,
                    start_time,
                    end_time
                )

                if tariff is None:
                    return jsonify({
                        "success": False,
                        "message": (
                            "Tarif lapangan untuk jadwal tersebut "
                            "belum tersedia."
                        )
                    }), 409

                price = Decimal(tariff["harga_per_jam"])
                total = price * duration

                cur.execute("""
                    INSERT INTO reservasi (
                        id_user,
                        id_lapangan,
                        tanggal,
                        jam_mulai,
                        jam_selesai,
                        durasi_jam,
                        harga_per_jam,
                        total_harga,
                        status_reservasi,
                        hold_expires_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, 'ditahan',
                        NOW() + (%s * INTERVAL '1 minute')
                    )
                    RETURNING id_reservasi, hold_expires_at;
                """, (
                    user_id,
                    field_id,
                    tanggal,
                    start_time,
                    end_time,
                    duration,
                    price,
                    total,
                    HOLD_MINUTES
                ))

                reservation = cur.fetchone()

                transaction_code = "RSV-{}-{}".format(
                    tanggal.strftime("%Y%m%d"),
                    secrets.token_hex(3).upper()
                )

                cur.execute("""
                    INSERT INTO pembayaran (
                        id_reservasi,
                        kode_transaksi,
                        metode_pembayaran,
                        channel_pembayaran,
                        jumlah_pembayaran,
                        status_pembayaran
                    )
                    VALUES (%s, %s, 'QRIS', %s, %s, 'menunggu')
                    RETURNING kode_transaksi;
                """, (
                    reservation["id_reservasi"],
                    transaction_code,
                    method["nama_ewallet"],
                    total
                ))

                payment = cur.fetchone()

                cur.execute("""
                    INSERT INTO reservasi_log (
                        id_reservasi,
                        id_user,
                        status_sebelumnya,
                        status_sesudahnya,
                        keterangan
                    )
                    VALUES (%s, %s, NULL, 'ditahan', %s);
                """, (
                    reservation["id_reservasi"],
                    user_id,
                    "Reservasi dibuat melalui halaman booking."
                ))

    except ExclusionViolation:
        return jsonify({
            "success": False,
            "message": "Jadwal tersebut sudah dipesan. Pilih waktu lain."
        }), 409

    return jsonify({
        "success": True,
        "message": "Reservasi berhasil ditahan selama 10 menit.",
        "reservation": {
            "id": reservation["id_reservasi"],
            "field": field["nama_lapangan"],
            "date": tanggal.isoformat(),
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "hold_expires_at": reservation["hold_expires_at"].isoformat()
        },
        "payment": {
            "transaction_code": payment["kode_transaksi"],
            "amount": float(total),
            "channel": method["nama_ewallet"],
            "method": _method_payload(
                method["id_pengaturan"],
                method["nama_ewallet"],
                method["nama_pemilik"],
                method["nomor_akun"]
            )
        }
    }), 201

# ======================================================================
# LANGKAH 1: BUKTI PEMBAYARAN, RIWAYAT, DAN DETAIL RESERVASI
# ======================================================================

STATUS_RESERVASI_LABEL = {
    "ditahan": "Menunggu pembayaran",
    "menunggu": "Menunggu verifikasi",
    "dikonfirmasi": "Dikonfirmasi",
    "dibatalkan": "Dibatalkan",
    "kedaluwarsa": "Kedaluwarsa",
    "selesai": "Selesai",
}

STATUS_PEMBAYARAN_LABEL = {
    "berhasil": "Terverifikasi",
    "gagal": "Ditolak",
    "kedaluwarsa": "Kedaluwarsa",
}

_RESERVATION_SELECT = """
    SELECT
        r.id_reservasi,
        l.nama_lapangan,
        r.tanggal,
        r.jam_mulai,
        r.jam_selesai,
        r.durasi_jam,
        r.harga_per_jam,
        r.total_harga,
        r.status_reservasi,
        CASE
            WHEN r.hold_expires_at IS NULL THEN NULL
            ELSE GREATEST(
                0,
                EXTRACT(EPOCH FROM (r.hold_expires_at - NOW()))::int
            )
        END AS sisa_detik,
        p.kode_transaksi,
        p.status_pembayaran,
        p.bukti_object_key,
        p.catatan_admin,
        p.channel_pembayaran,
        p.diverifikasi_pada AT TIME ZONE 'Asia/Jakarta' AS diverifikasi_wib
    FROM reservasi r
    JOIN lapangan l ON l.id_lapangan = r.id_lapangan
    LEFT JOIN LATERAL (
        SELECT kode_transaksi, status_pembayaran,
               bukti_object_key, catatan_admin,
               channel_pembayaran, diverifikasi_pada
        FROM pembayaran
        WHERE id_reservasi = r.id_reservasi
        ORDER BY id_pembayaran DESC
        LIMIT 1
    ) p ON TRUE
"""


@reservations_bp.app_template_filter("rupiah")
def rupiah(value):
    return "Rp" + "{:,.0f}".format(value or 0).replace(",", ".")


@reservations_bp.app_errorhandler(413)
def file_too_large(error):
    return jsonify({
        "success": False,
        "message": "Ukuran file melebihi batas 5 MB."
    }), 413


def _decorate(row):
    """Tambahkan label dan kelas CSS status untuk template."""
    item = dict(row)

    status = item["status_reservasi"]
    payment_status = item["status_pembayaran"]
    has_proof = bool(item["bukti_object_key"])

    item["has_proof"] = has_proof
    item["label_reservasi"] = STATUS_RESERVASI_LABEL.get(status, status)

    if payment_status is None:
        item["label_pembayaran"] = "-"
        item["kelas_pembayaran"] = ""
    elif payment_status == "menunggu":
        # Pada tahap ini 'menunggu' berarti belum dibayar atau
        # bukti sudah dikirim dan menunggu verifikasi admin.
        if has_proof:
            item["label_pembayaran"] = "Menunggu verifikasi"
            item["kelas_pembayaran"] = "menunggu"
        else:
            item["label_pembayaran"] = "Belum dibayar"
            item["kelas_pembayaran"] = "ditahan"
    else:
        item["label_pembayaran"] = STATUS_PEMBAYARAN_LABEL.get(
            payment_status, payment_status
        )
        item["kelas_pembayaran"] = payment_status

    return item


@reservations_bp.route("/")
@login_required_page
def list_reservations():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(
                _RESERVATION_SELECT
                + " WHERE r.id_user = %s"
                + " ORDER BY r.dibuat_pada DESC;",
                (session["user_id"],)
            )

            rows = cur.fetchall()

    return render_template(
        "reservations/index.html",
        reservations=[_decorate(row) for row in rows]
    )


@reservations_bp.route("/<int:reservation_id>")
@login_required_page
def reservation_detail(reservation_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _expire_holds(cur)

            cur.execute(
                _RESERVATION_SELECT
                + " WHERE r.id_reservasi = %s AND r.id_user = %s;",
                (reservation_id, session["user_id"])
            )

            row = cur.fetchone()

    if row is None:
        abort(404)

    return render_template(
        "reservations/detail.html",
        reservation=_decorate(row)
    )


SQL_ACTIVE_CHANNEL = """
    SELECT nama_ewallet
    FROM pengaturan_pembayaran
    WHERE status_aktif = TRUE
      AND LOWER(nama_ewallet) = LOWER(%s)
    ORDER BY id_pengaturan
    LIMIT 1;
"""


@reservations_bp.route("/<int:reservation_id>/payment", methods=["POST"])
@login_required
def upload_payment_proof(reservation_id):
    uploaded = request.files.get("proof")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "success": False,
            "message": "Pilih file bukti pembayaran terlebih dahulu."
        }), 400

    data = uploaded.read()

    if not data:
        return jsonify({
            "success": False,
            "message": "File kosong."
        }), 400

    # Tipe file ditentukan dari isi file, bukan dari nama atau header.
    mime_type = storage.detect_image_type(data)

    if mime_type is None:
        return jsonify({
            "success": False,
            "message": "Format file harus JPG, PNG, atau WebP."
        }), 400

    channel = (request.form.get("channel") or "").strip() or None
    user_id = session["user_id"]
    saved_key = None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _expire_holds(cur)

                # Kunci baris reservasi agar upload ganda / kedaluwarsa
                # tidak saling menimpa.
                cur.execute("""
                    SELECT status_reservasi
                    FROM reservasi
                    WHERE id_reservasi = %s
                      AND id_user = %s
                    FOR UPDATE;
                """, (reservation_id, user_id))

                reservation = cur.fetchone()

                if reservation is None:
                    return jsonify({
                        "success": False,
                        "message": "Reservasi tidak ditemukan."
                    }), 404

                status = reservation["status_reservasi"]

                if status == "kedaluwarsa":
                    return jsonify({
                        "success": False,
                        "message": (
                            "Waktu pembayaran telah habis. "
                            "Jadwal tidak lagi ditahan."
                        )
                    }), 409

                if status != "ditahan":
                    return jsonify({
                        "success": False,
                        "message": (
                            "Bukti pembayaran sudah dikirim atau "
                            "reservasi tidak dapat dibayar lagi."
                        )
                    }), 409

                cur.execute("""
                    SELECT id_pembayaran, channel_pembayaran
                    FROM pembayaran
                    WHERE id_reservasi = %s
                      AND status_pembayaran = 'menunggu'
                    ORDER BY id_pembayaran DESC
                    LIMIT 1
                    FOR UPDATE;
                """, (reservation_id,))

                payment = cur.fetchone()

                if payment is None:
                    return jsonify({
                        "success": False,
                        "message": "Data pembayaran tidak ditemukan."
                    }), 409

                if payment["channel_pembayaran"]:
                    # Metode sudah dipilih saat konfirmasi; tidak diubah lagi.
                    channel = payment["channel_pembayaran"]

                elif channel is not None:
                    cur.execute(SQL_ACTIVE_CHANNEL, (channel,))
                    method = cur.fetchone()

                    if method is None:
                        return jsonify({
                            "success": False,
                            "message": "Metode pembayaran tidak valid."
                        }), 400

                    # Pakai penulisan resmi (mis. 'GoPay'), bukan input mentah.
                    channel = method["nama_ewallet"]

                try:
                    saved_key = storage.save_payment_proof(data, mime_type)
                except storage.StorageError as error:
                    return jsonify({
                        "success": False,
                        "message": str(error)
                    }), 503

                cur.execute("""
                    UPDATE pembayaran
                    SET bukti_object_key = %s,
                        channel_pembayaran = %s
                    WHERE id_pembayaran = %s;
                """, (saved_key, channel, payment["id_pembayaran"]))

                # Constraint reservasi_check2: status selain 'ditahan'
                # wajib hold_expires_at = NULL, jadi diubah bersamaan.
                cur.execute("""
                    UPDATE reservasi
                    SET status_reservasi = 'menunggu',
                        hold_expires_at = NULL
                    WHERE id_reservasi = %s;
                """, (reservation_id,))

                cur.execute("""
                    INSERT INTO reservasi_log (
                        id_reservasi,
                        id_user,
                        status_sebelumnya,
                        status_sesudahnya,
                        keterangan
                    )
                    VALUES (%s, %s, 'ditahan', 'menunggu', %s);
                """, (
                    reservation_id,
                    user_id,
                    "Bukti pembayaran diunggah oleh pelanggan."
                ))

    except Exception:
        # Jangan tinggalkan file yatim bila transaksi database gagal.
        if saved_key:
            storage.delete(saved_key)
        raise

    return jsonify({
        "success": True,
        "message": (
            "Bukti pembayaran berhasil dikirim. "
            "Menunggu verifikasi admin."
        ),
        "reservation": {
            "id": reservation_id,
            "status": "menunggu"
        }
    }), 200


@reservations_bp.route("/<int:reservation_id>/payment-proof")
@login_required_page
def payment_proof(reservation_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id_user, p.bukti_object_key
                FROM reservasi r
                JOIN pembayaran p ON p.id_reservasi = r.id_reservasi
                WHERE r.id_reservasi = %s
                  AND p.bukti_object_key IS NOT NULL
                ORDER BY p.id_pembayaran DESC
                LIMIT 1;
            """, (reservation_id,))

            row = cur.fetchone()

    if row is None:
        abort(404)

    is_owner = row["id_user"] == session["user_id"]
    is_admin = session.get("role") == "admin"

    # 404 (bukan 403) agar keberadaan reservasi orang lain tidak bocor.
    if not (is_owner or is_admin):
        abort(404)

    key = row["bukti_object_key"]

    try:
        url = storage.presigned_url(key)
    except storage.StorageError:
        abort(503)

    # File dibaca langsung dari cloud lewat URL sementara (5 menit).
    response = redirect(url, code=302)
    response.headers["Cache-Control"] = "private, no-store"

    return response
