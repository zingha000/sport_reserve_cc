import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise ValueError("SECRET_KEY tidak ditemukan di file .env")

    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    DATABASE_URL = os.getenv("DATABASE_URL")

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