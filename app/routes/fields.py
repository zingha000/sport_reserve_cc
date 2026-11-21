from flask import Blueprint, render_template, abort
from app.database import get_db_connection

fields_bp = Blueprint("fields", __name__, url_prefix="/fields")

TODAY_WIB = "(NOW() AT TIME ZONE 'Asia/Jakarta')::date"

SQL_ACTIVE_FIELDS = """
    SELECT
        l.id_lapangan,
        l.nama_lapangan,
        l.deskripsi,
        l.luas_lapangan,
        l.status,
        MIN(tl.harga_per_jam) AS harga_terendah
    FROM lapangan l
    JOIN tarif_lapangan tl
        ON l.id_lapangan = tl.id_lapangan
        AND tl.berlaku_mulai <= {today}
        AND (
            tl.berlaku_sampai IS NULL
            OR tl.berlaku_sampai >= {today}
        )
    WHERE l.status = 'aktif'
    GROUP BY
        l.id_lapangan,
        l.nama_lapangan,
        l.deskripsi,
        l.luas_lapangan,
        l.status
    ORDER BY l.id_lapangan
""".format(today=TODAY_WIB)


def get_fields():
    """
    Mengambil lapangan aktif yang punya tarif berlaku hari ini (WIB).
    Harga yang ditampilkan adalah tarif terendah yang sedang berlaku.
    Lapangan nonaktif, atau aktif tetapi belum punya tarif berlaku,
    tidak ditampilkan karena memang tidak bisa dipesan.
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL_ACTIVE_FIELDS)
            rows = cursor.fetchall()

    fields = []

    for row in rows:
        fields.append({
            "id": row["id_lapangan"],
            "name": row["nama_lapangan"],
            "location": "Bandung",
            "type": row["luas_lapangan"] or "Lapangan Futsal",
            "price": int(row["harga_terendah"]),
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