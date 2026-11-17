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
    abort
)
from psycopg.errors import ExclusionViolation

from app.database import get_db_connection
from app.routes.fields import get_fields
from app.utils import login_required


reservations_bp = Blueprint(
    "reservations", __name__, url_prefix="/reservations"
)

HOLD_MINUTES = 10

ACTIVE_STATUSES = ("ditahan", "menunggu", "dikonfirmasi")


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
    cur.execute("""
        UPDATE reservasi
        SET status_reservasi = 'kedaluwarsa',
            hold_expires_at = NULL
        WHERE status_reservasi = 'ditahan'
          AND hold_expires_at <= NOW();
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
                conn.rollback()
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
                  AND status_reservasi = ANY(%s)
                  AND (
                      status_reservasi <> 'ditahan'
                      OR hold_expires_at > NOW()
                  )
                ORDER BY jam_mulai;
            """, (field_id, tanggal, list(ACTIVE_STATUSES)))

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


@reservations_bp.route("/confirm", methods=["POST"])
@login_required
def confirm_reservation():
    data = request.get_json(silent=True) or {}

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

    field = _find_field(field_id)

    if field is None:
        return jsonify({
            "success": False,
            "message": "Lapangan tidak ditemukan."
        }), 404

    user_id = session["user_id"]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _expire_holds(cur)

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
                        jumlah_pembayaran,
                        status_pembayaran
                    )
                    VALUES (%s, %s, 'QRIS', %s, 'menunggu')
                    RETURNING kode_transaksi;
                """, (
                    reservation["id_reservasi"],
                    transaction_code,
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
            "field": field["name"],
            "date": tanggal.isoformat(),
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "hold_expires_at": reservation["hold_expires_at"].isoformat()
        },
        "payment": {
            "transaction_code": payment["kode_transaksi"],
            "amount": float(total)
        }
    }), 201
