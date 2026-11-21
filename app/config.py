import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise ValueError("SECRET_KEY tidak ditemukan di file .env")

    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_URL_DIRECT = os.getenv("DATABASE_URL_DIRECT")

    # Pool koneksi aplikasi. Aplikasi memakai DATABASE_URL ber-"-pooler";
    # DATABASE_URL_DIRECT hanya untuk migrasi/skrip administratif.
    try:
        DB_POOL_MAX = max(int(os.getenv("DB_POOL_MAX", "5")), 1)
    except ValueError:
        DB_POOL_MAX = 5

    try:
        DB_POOL_TIMEOUT = max(float(os.getenv("DB_POOL_TIMEOUT", "3")), 1)
    except ValueError:
        DB_POOL_TIMEOUT = 3

    try:
        DB_CONNECT_TIMEOUT = max(int(os.getenv("DB_CONNECT_TIMEOUT", "10")), 1)
    except ValueError:
        DB_CONNECT_TIMEOUT = 10

    try:
        DB_PROBE_TIMEOUT = max(float(os.getenv("DB_PROBE_TIMEOUT", "2")), 1)
    except ValueError:
        DB_PROBE_TIMEOUT = 2

    try:
        DB_ACQUIRE_BUDGET = max(
            float(os.getenv("DB_ACQUIRE_BUDGET", "6")), 1
        )
    except ValueError:
        DB_ACQUIRE_BUDGET = 6

    try:
        DB_BREAKER_SECONDS = max(
            float(os.getenv("DB_BREAKER_SECONDS", "15")), 0
        )
    except ValueError:
        DB_BREAKER_SECONDS = 15

    try:
        DB_BREAKER_PERMANENT_SECONDS = max(
            float(os.getenv("DB_BREAKER_PERMANENT_SECONDS", "30")), 0
        )
    except ValueError:
        DB_BREAKER_PERMANENT_SECONDS = 30

    DB_LOCK_TIMEOUT = os.getenv("DB_LOCK_TIMEOUT", "3s")
    DB_STATEMENT_TIMEOUT = os.getenv("DB_STATEMENT_TIMEOUT", "10s")

    try:
        MAX_ACTIVE_HOLDS = max(int(os.getenv("MAX_ACTIVE_HOLDS", "2")), 1)
    except ValueError:
        MAX_ACTIVE_HOLDS = 2

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = not DEBUG

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # Maksimal upload 5 MB

    # Neon Object Storage (S3-compatible). Semua file upload (bukti
    # pembayaran, gambar QRIS) disimpan di cloud, tidak ada penyimpanan lokal.
    # Nama variabel AWS_* sama dengan yang ditulis `neon deploy` ke .env.
    S3_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL_S3")
    S3_REGION = os.getenv("AWS_REGION", "us-east-1")
    S3_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    S3_BUCKET = os.getenv("S3_BUCKET")