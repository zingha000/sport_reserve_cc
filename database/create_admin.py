
import sys
from pathlib import Path
from getpass import getpass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash
from psycopg.errors import UniqueViolation
from app.database import get_db_connection


def create_admin():
    print("=== PEMBUATAN AKUN ADMIN SPORTRESERVE ===")

    nama = input("Nama admin: ").strip()
    email = input("Email admin: ").strip().lower()
    password = getpass("Password admin: ")
    konfirmasi = getpass("Konfirmasi password: ")

    if not nama or not email:
        print("Nama dan email wajib diisi.")
        return

    if len(password) < 8:
        print("Password minimal 8 karakter.")
        return

    if password != konfirmasi:
        print("Konfirmasi password tidak cocok.")
        return

    password_hash = generate_password_hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (nama, email, password_hash, role)
                    VALUES (%s, %s, %s, 'admin')
                    RETURNING id_user, nama, email, role;
                    """,
                    (nama, email, password_hash)
                )

                admin = cur.fetchone()

        print("\nAkun admin berhasil dibuat!")
        print(f"ID    : {admin['id_user']}")
        print(f"Nama  : {admin['nama']}")
        print(f"Email : {admin['email']}")
        print(f"Role  : {admin['role']}")

    except UniqueViolation:
        print("Email sudah terdaftar. Gunakan email lain.")

    except Exception as e:
        print(f"Gagal membuat akun admin: {e}")


if __name__ == "__main__":
    create_admin()
