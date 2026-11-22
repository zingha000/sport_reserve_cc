"""Foto lapangan: unggah ke Neon Object Storage, galeri, thumbnail, hapus."""

from app.rate_limit import rate_limit, by_user
from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from app import storage
from app.database import get_db_connection
from app.utils import admin_required


field_photos_bp = Blueprint("field_photos", __name__, url_prefix="/fields")
admin_field_photos_bp = Blueprint(
    "admin_field_photos", __name__, url_prefix="/admin/fields"
)

MAX_PHOTOS_PER_FIELD = 5
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_FILENAME_LENGTH = 255

SQL_FIELD_STATE = """
    SELECT
        l.id_lapangan,
        (
            SELECT COUNT(*)
            FROM lapangan_foto f
            WHERE f.id_lapangan = l.id_lapangan
        ) AS total
    FROM lapangan l
    WHERE l.id_lapangan = %s
"""

SQL_INSERT_PHOTO = """
    INSERT INTO lapangan_foto (id_lapangan, object_key, nama_file, is_thumbnail)
    VALUES (%s, %s, %s, %s)
    RETURNING id_foto
"""

SQL_LIST_PHOTOS = """
    SELECT id_foto, nama_file, is_thumbnail
    FROM lapangan_foto
    WHERE id_lapangan = %s
    ORDER BY is_thumbnail DESC, id_foto
"""

SQL_PHOTO_FOR_VIEW = """
    SELECT f.object_key, l.status
    FROM lapangan_foto f
    JOIN lapangan l ON l.id_lapangan = f.id_lapangan
    WHERE f.id_foto = %s AND f.id_lapangan = %s
"""

SQL_PHOTOS_OF_FIELDS = """
    SELECT id_foto, id_lapangan
    FROM lapangan_foto
    WHERE id_lapangan = ANY(%s)
    ORDER BY id_lapangan, is_thumbnail DESC, id_foto
"""

SQL_LOCK_FIELD = "SELECT id_lapangan FROM lapangan WHERE id_lapangan = %s FOR UPDATE"

SQL_PHOTO_EXISTS = """
    SELECT id_foto FROM lapangan_foto
    WHERE id_foto = %s AND id_lapangan = %s
"""

SQL_CLEAR_THUMBNAIL = """
    UPDATE lapangan_foto SET is_thumbnail = FALSE
    WHERE id_lapangan = %s AND is_thumbnail
"""

SQL_SET_THUMBNAIL = """
    UPDATE lapangan_foto SET is_thumbnail = TRUE
    WHERE id_foto = %s AND id_lapangan = %s
"""

SQL_DELETE_PHOTO = """
    DELETE FROM lapangan_foto
    WHERE id_foto = %s AND id_lapangan = %s
    RETURNING object_key, is_thumbnail
"""

SQL_PROMOTE_THUMBNAIL = """
    UPDATE lapangan_foto SET is_thumbnail = TRUE
    WHERE id_foto = (
        SELECT id_foto FROM lapangan_foto
        WHERE id_lapangan = %s
        ORDER BY id_foto
        LIMIT 1
    )
"""


def _error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def photo_url(field_id, photo_id):
    return url_for(
        "field_photos.photo", field_id=field_id, photo_id=photo_id
    )


def load_photos(cursor, fields):
    """Isi fields[i]["image"] (thumbnail) dan fields[i]["photos"] (semua URL).

    Satu query untuk seluruh daftar lapangan, memakai cursor yang sudah
    terbuka, jadi tidak menambah koneksi dan tidak ada N+1.
    """
    for field in fields:
        field["image"] = None
        field["photos"] = []

    if not fields:
        return fields

    cursor.execute(SQL_PHOTOS_OF_FIELDS, ([f["id"] for f in fields],))
    by_field = {f["id"]: f for f in fields}

    for row in cursor.fetchall():
        target = by_field.get(row["id_lapangan"])

        if target is None:
            continue

        target["photos"].append(photo_url(row["id_lapangan"], row["id_foto"]))

    for field in fields:
        if field["photos"]:
            field["image"] = field["photos"][0]

    return fields


@field_photos_bp.route("/<int:field_id>/photos/<int:photo_id>", methods=["GET"])
def photo(field_id, photo_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_PHOTO_FOR_VIEW, (photo_id, field_id))
            row = cur.fetchone()

    if row is None:
        abort(404)

    # Foto lapangan nonaktif hanya boleh dilihat admin (pratinjau).
    if row["status"] != "aktif" and session.get("role") != "admin":
        abort(404)

    try:
        url = storage.presigned_url(row["object_key"])
    except storage.StorageError:
        abort(503)

    response = redirect(url, code=302)
    # URL berlaku 5 menit; browser boleh memakai ulang redirect ini 4 menit.
    response.headers["Cache-Control"] = "private, max-age=240"
    return response


@admin_field_photos_bp.route("/<int:field_id>/photos", methods=["GET"])
@admin_required
def list_photos(field_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_FIELD_STATE, (field_id,))

            if cur.fetchone() is None:
                return _error("Lapangan tidak ditemukan.", 404)

            cur.execute(SQL_LIST_PHOTOS, (field_id,))
            rows = cur.fetchall()

    return jsonify({
        "success": True,
        "max": MAX_PHOTOS_PER_FIELD,
        "photos": [
            {
                "id": row["id_foto"],
                "name": row["nama_file"],
                "is_thumbnail": row["is_thumbnail"],
                "url": photo_url(field_id, row["id_foto"]),
            }
            for row in rows
        ],
    })


@admin_field_photos_bp.route("/<int:field_id>/photos", methods=["POST"])
@rate_limit(
    "unggah-foto", limit=10, window=60, key=by_user,
    message="Terlalu banyak unggahan foto. Tunggu 1 menit lalu coba lagi.",
)
@admin_required
def upload_photo(field_id):
    uploaded = request.files.get("photo")

    if uploaded is None or not uploaded.filename:
        return _error("Pilih foto terlebih dahulu.")

    data = uploaded.read()

    if not data:
        return _error("File kosong.")

    if len(data) > MAX_PHOTO_BYTES:
        return _error("Ukuran foto maksimal 5 MB.", 413)

    mime_type = storage.detect_image_type(data)

    if mime_type is None:
        return _error("Format foto harus JPG, PNG, atau WebP.")

    filename = (uploaded.filename or "")[:MAX_FILENAME_LENGTH]

    # Fase 1: pengecekan cepat agar tidak mengunggah bila sudah penuh.
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_FIELD_STATE, (field_id,))
            state = cur.fetchone()

    if state is None:
        return _error("Lapangan tidak ditemukan.", 404)

    if state["total"] >= MAX_PHOTOS_PER_FIELD:
        return _error(
            "Maksimal {} foto per lapangan. Hapus salah satu dahulu.".format(
                MAX_PHOTOS_PER_FIELD
            ),
            409,
        )

    # Fase 2: unggah ke cloud, tanpa koneksi database terbuka.
    try:
        key = storage.save_field_photo(data, mime_type)
    except storage.StorageError as error:
        return _error(str(error), 503)

    # Fase 3: satu transaksi pendek; objek dihapus tepat sekali bila gagal.
    committed = False
    inserted = False
    result = None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(SQL_FIELD_STATE + " FOR UPDATE OF l", (field_id,))
                state = cur.fetchone()

                if state is None:
                    result = _error("Lapangan tidak ditemukan.", 404)
                elif state["total"] >= MAX_PHOTOS_PER_FIELD:
                    result = _error(
                        "Maksimal {} foto per lapangan.".format(
                            MAX_PHOTOS_PER_FIELD
                        ),
                        409,
                    )
                else:
                    cur.execute(
                        SQL_INSERT_PHOTO,
                        (field_id, key, filename or None, state["total"] == 0),
                    )
                    photo_id = cur.fetchone()["id_foto"]
                    result = (
                        jsonify({
                            "success": True,
                            "message": "Foto berhasil diunggah.",
                            "id": photo_id,
                        }),
                        200,
                    )
                    inserted = True

        # Baru dianggap sukses setelah commit (keluar dari `with`) berhasil.
        committed = inserted
    finally:
        if not committed:
            storage.delete(key)

    return result


@admin_field_photos_bp.route(
    "/<int:field_id>/photos/<int:photo_id>/thumbnail", methods=["POST"]
)
@admin_required
def set_thumbnail(field_id, photo_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LOCK_FIELD, (field_id,))

            if cur.fetchone() is None:
                return _error("Lapangan tidak ditemukan.", 404)

            cur.execute(SQL_PHOTO_EXISTS, (photo_id, field_id))

            if cur.fetchone() is None:
                return _error("Foto tidak ditemukan.", 404)

            cur.execute(SQL_CLEAR_THUMBNAIL, (field_id,))
            cur.execute(SQL_SET_THUMBNAIL, (photo_id, field_id))

    return jsonify({"success": True, "message": "Foto utama diubah."})


@admin_field_photos_bp.route(
    "/<int:field_id>/photos/<int:photo_id>/delete", methods=["POST"]
)
@admin_required
def delete_photo(field_id, photo_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_LOCK_FIELD, (field_id,))

            if cur.fetchone() is None:
                return _error("Lapangan tidak ditemukan.", 404)

            cur.execute(SQL_DELETE_PHOTO, (photo_id, field_id))
            deleted = cur.fetchone()

            if deleted is None:
                return _error("Foto tidak ditemukan.", 404)

            if deleted["is_thumbnail"]:
                cur.execute(SQL_PROMOTE_THUMBNAIL, (field_id,))

    # Hapus objek hanya setelah baris database benar-benar ter-commit.
    storage.delete(deleted["object_key"])

    return jsonify({"success": True, "message": "Foto dihapus."})