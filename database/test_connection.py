
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL tidak ditemukan di file .env")

try:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT current_database(), current_user, version();
            """)

            result = cur.fetchone()

            print("KONEKSI DATABASE BERHASIL!")
            print("Database:", result[0])
            print("User:", result[1])
            print("PostgreSQL:", result[2].split(",")[0])

except Exception as e:
    print("KONEKSI DATABASE GAGAL!")
    print(type(e).__name__, str(e))
