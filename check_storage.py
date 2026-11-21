"""Uji koneksi Neon Object Storage: unggah, baca lewat presigned URL, hapus.

Jalankan dari folder proyek (venv aktif):
    python check_storage.py
"""

import sys
import urllib.request

from app import create_app, storage

# PNG 1x1 piksel
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
)


def step(label, ok, detail=""):
    print(("[OK]    " if ok else "[GAGAL] ") + label + (" - " + detail if detail else ""))

    if not ok:
        sys.exit(1)


app = create_app()

with app.app_context():
    try:
        key = storage.save_payment_proof(PNG, "image/png")
        step("Unggah ke bucket", True, key)

        step("Objek terdeteksi di cloud (HEAD)", storage.exists(key))

        url = storage.presigned_url(key)
        with urllib.request.urlopen(url, timeout=20) as response:
            body = response.read()
        step(
            "Baca lewat presigned URL",
            body == PNG,
            "{} byte, status {}".format(len(body), response.status),
        )

        step("Hapus objek", storage.delete(key))
        step("Objek sudah hilang", not storage.exists(key))
    except storage.StorageError as error:
        step("Koneksi storage", False, str(error))

print("\nSemua tahap berhasil. Penyimpanan cloud siap dipakai.")