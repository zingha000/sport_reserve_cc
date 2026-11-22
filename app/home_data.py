import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import get_db_connection
from app.routes.fields import get_fields

log = logging.getLogger(__name__)

WIB = ZoneInfo("Asia/Jakarta")

BULAN = [
    "", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]

STATUS_LABEL = {
    "dikonfirmasi": "Terisi",
    "menunggu": "Menunggu",
    "ditahan": "Ditahan",
}

SQL_UPCOMING = """
    SELECT
        l.nama_lapangan,
        r.tanggal,
        r.jam_mulai,
        r.jam_selesai,
        r.status_reservasi
    FROM reservasi r
    JOIN lapangan l ON l.id_lapangan = r.id_lapangan
        WHERE r.status_reservasi = 'dikonfirmasi'
      AND (r.tanggal + r.jam_selesai) > (NOW() AT TIME ZONE 'Asia/Jakarta')
    ORDER BY r.tanggal, r.jam_mulai
    LIMIT %s
"""


def _day_label(day):
    today = datetime.now(WIB).date()
    delta = (day - today).days

    if delta == 0:
        return "Hari ini"
    if delta == 1:
        return "Besok"
    return "%d %s" % (day.day, BULAN[day.month])


def get_upcoming_schedule(limit=3):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(SQL_UPCOMING, (limit,))
            rows = cursor.fetchall()

    return [
        {
            "field": row["nama_lapangan"],
            "day": _day_label(row["tanggal"]),
            "start": row["jam_mulai"].strftime("%H:%M"),
            "end": row["jam_selesai"].strftime("%H:%M"),
            "kind": row["status_reservasi"],
            "label": STATUS_LABEL.get(row["status_reservasi"], "Terisi"),
        }
        for row in rows
    ]


def get_home_data():
    """Data beranda. Gagal database tidak boleh merusak halaman."""
    try:
        fields = get_fields()[:3]
    except Exception:
        log.exception("Beranda: gagal memuat lapangan")
        fields = []

    try:
        schedule = get_upcoming_schedule()
    except Exception:
        log.exception("Beranda: gagal memuat jadwal")
        schedule = []

    return fields, schedule