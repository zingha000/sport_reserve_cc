from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, render_template, request, url_for, abort

from app.database import get_db_connection
from app.utils import admin_required, admin_required_page


admin_fields_bp = Blueprint(
    "admin_fields",
    __name__,
    url_prefix="/admin/fields"
)

DAYS = [
    (1, "Senin"),
    (2, "Selasa"),
    (3, "Rabu"),
    (4, "Kamis"),
    (5, "Jumat"),
    (6, "Sabtu"),
    (7, "Minggu"),
]
DAY_NAMES = dict(DAYS)

MAX_NAME_LENGTH = 100
MAX_SIZE_LENGTH = 50
MAX_DESCRIPTION_LENGTH = 2000
MAX_PRICE = Decimal("10000000")

# ----------------------------------------------------------------------
# SQL
# ----------------------------------------------------------------------

TODAY_WIB = "(NOW() AT TIME ZONE 'Asia/Jakarta')::date"

SQL_LIST_FIELDS = """
    SELECT
        l.id_lapangan,
        l.nama_lapangan,
        l.luas_lapangan,
        l.status,
        (
            SELECT MIN(t.harga_per_jam)
            FROM tarif_lapangan t
            WHERE t.id_lapangan = l.id_lapangan
              AND t.berlaku_mulai <= {today}
              AND (t.berlaku_sampai IS NULL OR t.berlaku_sampai >= {today})
        ) AS harga_terendah,
        (
            SELECT COUNT(*)
            FROM jam_operasional j
            WHERE j.id_lapangan = l.id_lapangan AND j.status = TRUE
        ) AS hari_buka,
        (
            SELECT COUNT(*)
            FROM reservasi r
            WHERE r.id_lapangan = l.id_lapangan
              AND r.status_reservasi IN ('ditahan', 'menunggu', 'dikonfirmasi')
              AND r.tanggal >= {today}
        ) AS reservasi_aktif
    FROM lapangan l
    ORDER BY l.id_lapangan;
""".format(today=TODAY_WIB)

SQL_GET_FIELD = """
    SELECT id_lapangan, nama_lapangan, deskripsi, luas_lapangan, status
    FROM lapangan
    WHERE id_lapangan = %s;
"""

SQL_LOCK_FIELD = """
    SELECT id_lapangan, status
    FROM lapangan
    WHERE id_lapangan = %s
    FOR UPDATE;
"""

SQL_INSERT_FIELD = """
    INSERT INTO lapangan (nama_lapangan, deskripsi, luas_lapangan, status)
    VALUES (%s, %s, %s, 'nonaktif')
    RETURNING id_lapangan;
"""

SQL_UPDATE_FIELD = """
    UPDATE lapangan
    SET nama_lapangan = %s,
        deskripsi = %s,
        luas_lapangan = %s
    WHERE id_lapangan = %s
    RETURNING id_lapangan;
"""

SQL_SET_FIELD_STATUS = """
    UPDATE lapangan
    SET status = %s
    WHERE id_lapangan = %s;
"""

SQL_READINESS = """
    SELECT
        (
            SELECT COUNT(*) FROM jam_operasional
            WHERE id_lapangan = %s AND status = TRUE
        ) AS hari_buka,
        (
            SELECT COUNT(*) FROM tarif_lapangan
            WHERE id_lapangan = %s
              AND berlaku_mulai <= {today}
              AND (berlaku_sampai IS NULL OR berlaku_sampai >= {today})
        ) AS tarif_berlaku;
""".format(today=TODAY_WIB)

SQL_COUNT_ACTIVE_RESERVATIONS = """
    SELECT COUNT(*) AS jumlah
    FROM reservasi
    WHERE id_lapangan = %s
      AND status_reservasi IN ('ditahan', 'menunggu', 'dikonfirmasi')
      AND tanggal >= {today};
""".format(today=TODAY_WIB)

SQL_OTHER_CURRENT_TARIFFS = """
    SELECT COUNT(*) AS jumlah
    FROM tarif_lapangan
    WHERE id_lapangan = %s
      AND id_tarif <> %s
      AND berlaku_mulai <= {today}
      AND (berlaku_sampai IS NULL OR berlaku_sampai >= {today});
""".format(today=TODAY_WIB)

SQL_LIST_HOURS = """
    SELECT hari, jam_buka, jam_tutup, status
    FROM jam_operasional
    WHERE id_lapangan = %s
    ORDER BY hari;
"""

SQL_UPSERT_HOURS = """
    INSERT INTO jam_operasional (id_lapangan, hari, jam_buka, jam_tutup, status)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (id_lapangan, hari) DO UPDATE
    SET jam_buka = EXCLUDED.jam_buka,
        jam_tutup = EXCLUDED.jam_tutup,
        status = EXCLUDED.status;
"""

SQL_COUNT_OPEN_DAYS = """
    SELECT COUNT(*) AS jumlah
    FROM jam_operasional
    WHERE id_lapangan = %s AND status = TRUE;
"""

SQL_LIST_TARIFFS = """
    SELECT id_tarif, hari, jam_mulai, jam_selesai, harga_per_jam,
           berlaku_mulai, berlaku_sampai,
           (
               berlaku_mulai <= {today}
               AND (berlaku_sampai IS NULL OR berlaku_sampai >= {today})
           ) AS sedang_berlaku
    FROM tarif_lapangan
    WHERE id_lapangan = %s
    ORDER BY hari, jam_mulai, berlaku_mulai;
""".format(today=TODAY_WIB)

SQL_TARIFF_OVERLAP = """
    SELECT 1
    FROM tarif_lapangan
    WHERE id_lapangan = %s
      AND hari = %s
      AND jam_mulai < %s
      AND jam_selesai > %s
      AND berlaku_mulai <= COALESCE(%s::date, 'infinity'::date)
      AND COALESCE(berlaku_sampai, 'infinity'::date) >= %s::date
    LIMIT 1;
"""

SQL_INSERT_TARIFF = """
    INSERT INTO tarif_lapangan (
        id_lapangan, hari, jam_mulai, jam_selesai,
        harga_per_jam, berlaku_mulai, berlaku_sampai
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s);
"""

SQL_DELETE_TARIFF = """
    DELETE FROM tarif_lapangan
    WHERE id_tarif = %s AND id_lapangan = %s
    RETURNING id_tarif;
"""


# ----------------------------------------------------------------------
# HELPER
# ----------------------------------------------------------------------

class FormError(Exception):
    """Input tidak valid; pesan aman ditampilkan ke admin."""


def _error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def _ok(message, **extra):
    payload = {"success": True, "message": message}
    payload.update(extra)
    return jsonify(payload), 200


def _text(value, label, max_length, required=False):
    text = str(value or "").strip()

    if required and not text:
        raise FormError("{} wajib diisi.".format(label))

    if len(text) > max_length:
        raise FormError(
            "{} maksimal {} karakter.".format(label, max_length)
        )

    return text or None


def _time(value, label):
    try:
        return datetime.strptime(str(value or "").strip()[:5], "%H:%M").time()
    except ValueError:
        raise FormError("{} tidak valid (format JJ:MM).".format(label))


def _date(value, label, required=True):
    text = str(value or "").strip()

    if not text:
        if required:
            raise FormError("{} wajib diisi.".format(label))
        return None

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise FormError("{} tidak valid.".format(label))


def _day(value):
    try:
        day = int(value)
    except (TypeError, ValueError):
        raise FormError("Hari tidak valid.")

    if day not in DAY_NAMES:
        raise FormError("Hari tidak valid.")

    return day


def _price(value):
    try:
        price = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise FormError("Harga per jam harus berupa angka.")

    if not price.is_finite() or price <= 0:
        raise FormError("Harga per jam harus lebih dari 0.")

    if price > MAX_PRICE:
        raise FormError("Harga per jam terlalu besar.")

    return price.quantize(Decimal("0.01"))


def _field_payload(data):
    return (
        _text(data.get("nama"), "Nama lapangan", MAX_NAME_LENGTH, True),
        _text(data.get("deskripsi"), "Deskripsi", MAX_DESCRIPTION_LENGTH),
        _text(data.get("luas"), "Luas lapangan", MAX_SIZE_LENGTH),
    )


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# ----------------------------------------------------------------------
# HALAMAN
# ----------------------------------------------------------------------

@admin_fields_bp.route("", methods=["GET"])
@admin_required_page
def list_fields():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LIST_FIELDS)
            fields = cur.fetchall()

    return render_template("admin/fields_list.html", fields=fields)


@admin_fields_bp.route("/new", methods=["GET"])
@admin_required_page
def new_field():
    return render_template(
        "admin/field_form.html",
        field=None,
        days=DAYS,
        hours={},
        tariffs=[]
    )


@admin_fields_bp.route("/<int:field_id>", methods=["GET"])
@admin_required_page
def edit_field(field_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_GET_FIELD, (field_id,))
            field = cur.fetchone()

            if field is None:
                abort(404)

            cur.execute(SQL_LIST_HOURS, (field_id,))
            hours = {row["hari"]: row for row in cur.fetchall()}

            cur.execute(SQL_LIST_TARIFFS, (field_id,))
            tariffs = cur.fetchall()

    return render_template(
        "admin/field_form.html",
        field=field,
        days=DAYS,
        hours=hours,
        tariffs=tariffs
    )


# ----------------------------------------------------------------------
# AKSI (JSON)
# ----------------------------------------------------------------------

@admin_fields_bp.route("", methods=["POST"])
@admin_required
def create_field():
    try:
        name, description, size = _field_payload(_json_body())
    except FormError as error:
        return _error(str(error))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_INSERT_FIELD, (name, description, size))
            field_id = cur.fetchone()["id_lapangan"]

    return _ok(
        "Lapangan dibuat. Lengkapi jam operasional dan tarif, lalu aktifkan.",
        id=field_id,
        redirect=url_for("admin_fields.edit_field", field_id=field_id)
    )


@admin_fields_bp.route("/<int:field_id>/update", methods=["POST"])
@admin_required
def update_field(field_id):
    try:
        name, description, size = _field_payload(_json_body())
    except FormError as error:
        return _error(str(error))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                SQL_UPDATE_FIELD,
                (name, description, size, field_id)
            )

            if cur.fetchone() is None:
                return _error("Lapangan tidak ditemukan.", 404)

    return _ok("Data lapangan disimpan.")


@admin_fields_bp.route("/<int:field_id>/status", methods=["POST"])
@admin_required
def set_status(field_id):
    status = str(_json_body().get("status") or "").strip()

    if status not in ("aktif", "nonaktif"):
        return _error("Status harus 'aktif' atau 'nonaktif'.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LOCK_FIELD, (field_id,))

            if cur.fetchone() is None:
                return _error("Lapangan tidak ditemukan.", 404)

            if status == "aktif":
                cur.execute(SQL_READINESS, (field_id, field_id))
                ready = cur.fetchone()

                if ready["hari_buka"] == 0:
                    return _error(
                        "Atur jam operasional (minimal satu hari buka) "
                        "sebelum mengaktifkan lapangan.",
                        409
                    )

                if ready["tarif_berlaku"] == 0:
                    return _error(
                        "Tambahkan minimal satu tarif yang sedang berlaku "
                        "sebelum mengaktifkan lapangan.",
                        409
                    )

            cur.execute(SQL_SET_FIELD_STATUS, (status, field_id))

            remaining = 0

            if status == "nonaktif":
                cur.execute(SQL_COUNT_ACTIVE_RESERVATIONS, (field_id,))
                remaining = cur.fetchone()["jumlah"]

    if status == "aktif":
        return _ok("Lapangan diaktifkan dan tampil untuk pelanggan.")

    message = "Lapangan dinonaktifkan. Pelanggan tidak bisa memesannya lagi."

    if remaining:
        message += (
            " Masih ada {} reservasi mendatang yang tidak dibatalkan "
            "otomatis; tinjau di dashboard.".format(remaining)
        )

    return _ok(message)


@admin_fields_bp.route("/<int:field_id>/hours", methods=["POST"])
@admin_required
def save_hours(field_id):
    rows = _json_body().get("hours")

    if not isinstance(rows, list) or not rows:
        return _error("Data jam operasional kosong.")

    parsed = []
    seen = set()

    try:
        for item in rows:
            if not isinstance(item, dict):
                raise FormError("Data jam operasional tidak valid.")

            day = _day(item.get("hari"))

            if day in seen:
                raise FormError("Hari {} terkirim dua kali.".format(
                    DAY_NAMES[day]
                ))

            seen.add(day)

            opens = _time(item.get("buka"), "Jam buka " + DAY_NAMES[day])
            closes = _time(item.get("tutup"), "Jam tutup " + DAY_NAMES[day])

            if opens >= closes:
                raise FormError(
                    "{}: jam buka harus lebih awal dari jam tutup "
                    "(jam tutup maksimal 23:59).".format(DAY_NAMES[day])
                )

            parsed.append((day, opens, closes, bool(item.get("aktif"))))
    except FormError as error:
        return _error(str(error))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LOCK_FIELD, (field_id,))
            field = cur.fetchone()

            if field is None:
                return _error("Lapangan tidak ditemukan.", 404)

            for day, opens, closes, active in parsed:
                cur.execute(
                    SQL_UPSERT_HOURS,
                    (field_id, day, opens, closes, active)
                )

            cur.execute(SQL_COUNT_OPEN_DAYS, (field_id,))
            open_days = cur.fetchone()["jumlah"]

            if field["status"] == "aktif" and open_days == 0:
                conn.rollback()
                return _error(
                    "Lapangan yang aktif harus buka minimal satu hari. "
                    "Nonaktifkan lapangan terlebih dahulu.",
                    409
                )

    return _ok("Jam operasional disimpan.")


@admin_fields_bp.route("/<int:field_id>/tariffs", methods=["POST"])
@admin_required
def add_tariff(field_id):
    data = _json_body()

    try:
        raw_days = data.get("hari")

        if not isinstance(raw_days, list) or not raw_days:
            raise FormError("Pilih minimal satu hari.")

        days = sorted({_day(value) for value in raw_days})

        start = _time(data.get("jam_mulai"), "Jam mulai")
        end = _time(data.get("jam_selesai"), "Jam selesai")

        if start >= end:
            raise FormError("Jam mulai harus lebih awal dari jam selesai.")

        price = _price(data.get("harga"))
        valid_from = _date(data.get("berlaku_mulai"), "Tanggal mulai berlaku")
        valid_until = _date(
            data.get("berlaku_sampai"),
            "Tanggal akhir berlaku",
            required=False
        )

        if valid_until is not None and valid_until < valid_from:
            raise FormError(
                "Tanggal akhir berlaku tidak boleh sebelum tanggal mulai."
            )
    except FormError as error:
        return _error(str(error))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LOCK_FIELD, (field_id,))

            if cur.fetchone() is None:
                return _error("Lapangan tidak ditemukan.", 404)

            clashes = []

            for day in days:
                cur.execute(
                    SQL_TARIFF_OVERLAP,
                    (field_id, day, end, start, valid_until, valid_from)
                )

                if cur.fetchone() is not None:
                    clashes.append(DAY_NAMES[day])

            if clashes:
                return _error(
                    "Tarif bertumpang tindih dengan tarif yang sudah ada "
                    "pada: {}. Hapus tarif lama atau ubah rentangnya."
                    .format(", ".join(clashes)),
                    409
                )

            for day in days:
                cur.execute(SQL_INSERT_TARIFF, (
                    field_id, day, start, end,
                    price, valid_from, valid_until
                ))

    return _ok("Tarif ditambahkan.")


@admin_fields_bp.route(
    "/<int:field_id>/tariffs/<int:tariff_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_tariff(field_id, tariff_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LOCK_FIELD, (field_id,))
            field = cur.fetchone()

            if field is None:
                return _error("Lapangan tidak ditemukan.", 404)

            if field["status"] == "aktif":
                cur.execute(SQL_OTHER_CURRENT_TARIFFS, (field_id, tariff_id))

                if cur.fetchone()["jumlah"] == 0:
                    return _error(
                        "Lapangan yang aktif harus punya minimal satu tarif "
                        "berlaku. Nonaktifkan lapangan terlebih dahulu.",
                        409
                    )

            cur.execute(SQL_DELETE_TARIFF, (tariff_id, field_id))

            if cur.fetchone() is None:
                return _error("Tarif tidak ditemukan.", 404)

    return _ok("Tarif dihapus.")