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