
import sys
from pathlib import Path
from getpass import getpass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash
from app.database import get_db_connection


email = input("Email admin: ").strip().lower()
password = getpass("Password baru: ")
konfirmasi = getpass("Konfirmasi password: ")

if len(password) < 8:
    print("Password minimal 8 karakter.")
elif password != konfirmasi:
    print("Password tidak cocok.")
else:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s
                WHERE email = %s AND role = 'admin'
                RETURNING id_user, nama, email, role;
                """,
                (generate_password_hash(password), email)
            )
            admin = cur.fetchone()

    if admin:
        print("Password admin berhasil diperbarui!")
        print(admin)
    else:
        print("Akun admin tidak ditemukan.")
