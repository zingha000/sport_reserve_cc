
import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL tidak ditemukan di file .env")

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )
