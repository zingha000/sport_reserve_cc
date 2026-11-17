
import sys
from pathlib import Path

# Menambahkan root project ke Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_db_connection


def test_database():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id_lapangan,
                        nama_lapangan,
                        status
                    FROM lapangan
                    ORDER BY id_lapangan;
                """)

                data = cur.fetchall()

                print("KONEKSI FLASK KE NEON BERHASIL!")
                print("Jumlah lapangan:", len(data))

                for lapangan in data:
                    print(lapangan)

    except Exception as e:
        print("KONEKSI GAGAL!")
        print(type(e).__name__, str(e))


if __name__ == "__main__":
    test_database()
