"""Penyimpanan file SportReserve di Neon Object Storage (S3-compatible).

Semua file upload (bukti pembayaran, gambar QRIS) disimpan di cloud.
Database hanya menyimpan *object key* (mis. "bukti-pembayaran/2026/11/abc.png"),
bukan URL. Bucket bersifat privat: file dilihat lewat presigned URL
berumur pendek yang dibuat setelah pengecekan hak akses di route.
"""

import logging
import uuid
from datetime import datetime

from flask import current_app

log = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

PRESIGN_SECONDS = 300  # presigned URL berlaku 5 menit

_REQUIRED_ENV = (
    ("AWS_ENDPOINT_URL_S3", "S3_ENDPOINT_URL"),
    ("AWS_ACCESS_KEY_ID", "S3_ACCESS_KEY_ID"),
    ("AWS_SECRET_ACCESS_KEY", "S3_SECRET_ACCESS_KEY"),
    ("S3_BUCKET", "S3_BUCKET"),
)


class StorageError(Exception):
    """Penyimpanan cloud tidak dapat dipakai; pesan aman untuk admin."""


def detect_image_type(data):
    """Kenali tipe gambar dari isi file (bukan dari nama/ekstensi)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    return None


def _bucket():
    name = current_app.config.get("S3_BUCKET")

    if not name:
        raise StorageError(
            "Penyimpanan cloud belum dikonfigurasi: S3_BUCKET kosong."
        )

    return name


def _client():
    extensions = current_app.extensions

    if "s3_client" in extensions:
        return extensions["s3_client"]

    config = current_app.config
    missing = [env for env, key in _REQUIRED_ENV if not config.get(key)]

    if missing:
        raise StorageError(
            "Penyimpanan cloud belum dikonfigurasi: isi "
            + ", ".join(missing) + " di file .env."
        )

    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        raise StorageError(
            "Paket boto3 belum terpasang. Jalankan: pip install boto3"
        )

    client = boto3.client(
        "s3",
        region_name=config["S3_REGION"],
        endpoint_url=config["S3_ENDPOINT_URL"],
        aws_access_key_id=config["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=config["S3_SECRET_ACCESS_KEY"],
        config=BotoConfig(
            signature_version="s3v4",
            # Neon Object Storage hanya mendukung path-style.
            s3={"addressing_style": "path"},
            retries={
                "max_attempts": config.get("S3_MAX_ATTEMPTS", 2),
                "mode": "standard",
            },
            connect_timeout=5,
            read_timeout=config.get("S3_READ_TIMEOUT", 10),
        ),
    )

    extensions["s3_client"] = client
    return client


def _run(action, function, **kwargs):
    try:
        return function(**kwargs)
    except StorageError:
        raise
    except Exception as error:
        log.exception("Operasi storage '%s' gagal", action)
        raise StorageError(
            "Penyimpanan cloud tidak dapat dihubungi. Coba lagi sebentar."
        ) from error


def _save_image(prefix, data, mime_type, cache_control="private, no-store"):
    key = "{}/{}/{}{}".format(
        prefix,
        datetime.now().strftime("%Y/%m"),
        uuid.uuid4().hex,
        ALLOWED_IMAGE_TYPES[mime_type],
    )

    _run(
        "upload",
        _client().put_object,
        Bucket=_bucket(),
        Key=key,
        Body=data,
        ContentType=mime_type,
        CacheControl=cache_control,
    )

    return key


def save_payment_proof(data, mime_type):
    """Unggah bukti pembayaran ke cloud dan kembalikan object key-nya."""
    return _save_image("bukti-pembayaran", data, mime_type)


def save_qris_image(data, mime_type):
    """Unggah gambar QRIS ke cloud dan kembalikan object key-nya."""
    return _save_image("qris", data, mime_type)


def save_field_photo(data, mime_type):
    """Unggah foto lapangan ke cloud dan kembalikan object key-nya."""
    return _save_image(
        "lapangan", data, mime_type, cache_control="public, max-age=86400"
    )


def presigned_url(key, seconds=PRESIGN_SECONDS):
    """URL sementara untuk membaca file privat langsung dari cloud."""
    return _run(
        "presign",
        _client().generate_presigned_url,
        ClientMethod="get_object",
        Params={"Bucket": _bucket(), "Key": str(key)},
        ExpiresIn=seconds,
    )


def read_object(key):
    """Baca isi file dari cloud; dipakai untuk unduh/bagikan QRIS."""
    obj = _run(
        "download",
        _client().get_object,
        Bucket=_bucket(),
        Key=str(key),
    )

    return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"


def ping():
    """Pastikan bucket dapat diakses untuk health check."""
    _run(
        "ping",
        _client().list_objects_v2,
        Bucket=_bucket(),
        MaxKeys=1,
    )

    return True


def exists(key):
    try:
        _client().head_object(Bucket=_bucket(), Key=str(key))
        return True
    except StorageError:
        raise
    except Exception as error:
        code = getattr(error, "response", {}).get("Error", {}).get("Code")

        if code in ("404", "NoSuchKey", "NotFound"):
            return False

        log.exception("Operasi storage 'head' gagal")
        raise StorageError(
            "Penyimpanan cloud tidak dapat dihubungi. Coba lagi sebentar."
        ) from error


def delete(key):
    """Hapus file; kegagalan hanya dicatat agar tidak menutupi error asli."""
    try:
        _client().delete_object(Bucket=_bucket(), Key=str(key))
        return True
    except Exception:
        log.exception("Gagal menghapus objek %s dari storage", key)
        return False