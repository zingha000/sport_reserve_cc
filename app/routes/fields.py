
from flask import Blueprint, render_template, abort
from app.database import get_db_connection

fields_bp = Blueprint("fields", __name__, url_prefix="/fields")


def get_fields():
    """
    Mengambil data lapangan aktif dari PostgreSQL.
    Harga yang ditampilkan merupakan tarif terendah
    yang sedang berlaku untuk setiap lapangan.
    """

    query = """
        SELECT
            l.id_lapangan,
            l.nama_lapangan,
            l.deskripsi,
            l.luas_lapangan,
            l.status,
            MIN(tl.harga_per_jam) AS harga_terendah
        FROM lapangan l
        LEFT JOIN tarif_lapangan tl
            ON l.id_lapangan = tl.id_lapangan
            AND tl.berlaku_mulai <= CURRENT_DATE
            AND (
                tl.berlaku_sampai IS NULL
                OR tl.berlaku_sampai >= CURRENT_DATE
            )
        WHERE l.status = 'aktif'
        GROUP BY
            l.id_lapangan,
            l.nama_lapangan,
            l.deskripsi,
            l.luas_lapangan,
            l.status
        ORDER BY l.id_lapangan
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    fields = []

    for row in rows:
        fields.append({
            "id": row["id_lapangan"],
            "name": row["nama_lapangan"],
            "location": "Bandung",
            "type": "Informasi belum tersedia",
            "price": (
                int(row["harga_terendah"])
                if row["harga_terendah"] is not None
                else 0
            ),
            "status": "Tersedia",
            "image": None,
            "description": (
                row["deskripsi"]
                or "Informasi lapangan belum tersedia."
            ),
            "area": row["luas_lapangan"]
        })

    return fields


@fields_bp.route("/")
def list_fields():
    fields = get_fields()
    return render_template("fields/index.html", fields=fields)


@fields_bp.route("/<int:field_id>")
def detail_field(field_id):
    field = next(
        (item for item in get_fields() if item["id"] == field_id),
        None
    )

    if field is None:
        abort(404)

    return render_template("fields/detail.html", field=field)
