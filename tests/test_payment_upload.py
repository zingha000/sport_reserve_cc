import io
from datetime import datetime, timedelta

import pytest

import app.routes.reservations as reservations_module


USER_ID = 1
RESERVATION_ID = 42
PAYMENT_ID = 99
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image"

EXPIRED_MESSAGE = (
    "Waktu pembayaran telah habis. Jadwal tidak lagi ditahan."
)
ALREADY_MESSAGE = (
    "Bukti pembayaran sudah dikirim atau reservasi tidak dapat dibayar lagi."
)


class FakeDatabase:
    def __init__(self):
        self.depth = 0
        self.max_depth = 0
        self.queries = []
        self.write_queries = []
        self.log_inserts = 0
        self.phase1_ignore_status = False
        self.phase1_ignore_proof = False
        self.fail_phase3 = False
        self.fail_on_update = False
        self.fail_on_commit = False
        self.reservation = {
            "status_reservasi": "ditahan",
            "hold_expires_at": datetime.now() + timedelta(minutes=10),
        }
        self.payment = {
            "id_pembayaran": PAYMENT_ID,
            "status_pembayaran": "menunggu",
            "channel_pembayaran": "GoPay",
            "bukti_object_key": None,
        }

    def connection(self):
        return FakeConnectionContext(self)


class FakeConnection:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)


class FakeConnectionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.depth += 1
        self.db.max_depth = max(self.db.max_depth, self.db.depth)
        return FakeConnection(self.db)

    def __exit__(self, exc_type, exc, tb):
        self.db.depth -= 1

        if exc_type is None and self.db.fail_on_commit:
            raise RuntimeError("commit failed")

        return False


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._next = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        sql = " ".join(str(query).split()).lower()
        self.db.queries.append(sql)
        self._next = None

        if "with expired as" in sql:
            return

        if "select status_reservasi from reservasi" in sql:
            status = self.db.reservation["status_reservasi"]

            if self.db.phase1_ignore_status:
                status = "ditahan"

            self._next = {"status_reservasi": status}
            return

        if "select status_reservasi," in sql and "hold_expires_at" in sql:
            if self.db.fail_phase3:
                raise RuntimeError("phase 3 failed")

            if self.db.reservation is None:
                self._next = None
                return

            self._next = {
                "status_reservasi": self.db.reservation["status_reservasi"],
                "hold_active": (
                    self.db.reservation["hold_expires_at"] is not None
                    and self.db.reservation["hold_expires_at"] > datetime.now()
                ),
            }
            return

        if "from pembayaran" in sql and "select" in sql:
            if self.db.payment is None:
                self._next = None
                return

            payment = dict(self.db.payment)

            if self.db.phase1_ignore_proof and "for update" not in sql:
                payment["bukti_object_key"] = None

            self._next = payment
            return

        if "from pengaturan_pembayaran" in sql:
            self._next = (
                {"nama_ewallet": "GoPay"}
                if params[0].lower() == "gopay"
                else None
            )
            return

        if "update pembayaran" in sql:
            if self.db.fail_on_update:
                raise RuntimeError("update failed")

            self.db.write_queries.append(sql)
            key, channel, payment_id = params
            self.db.payment["bukti_object_key"] = key
            self.db.payment["channel_pembayaran"] = channel
            return

        if "update reservasi" in sql:
            self.db.write_queries.append(sql)
            self.db.reservation["status_reservasi"] = "menunggu"
            self.db.reservation["hold_expires_at"] = None
            return

        if "insert into reservasi_log" in sql:
            self.db.write_queries.append(sql)
            self.db.log_inserts += 1
            return

        raise AssertionError("Query tidak dikenali: {}".format(sql))

    def fetchone(self):
        return self._next


class FakeObjectStorage:
    def __init__(self, db):
        self.db = db
        self.objects = []
        self.deleted = []
        self.uploads = 0
        self.depth_at_upload = None
        self.last_key = None
        self.error = None
        self.on_save = None

    def save_payment_proof(self, data, mime_type):
        self.depth_at_upload = self.db.depth

        if self.error is not None:
            raise self.error

        self.uploads += 1
        key = "bukti-pembayaran/test/{}.png".format(self.uploads)
        self.last_key = key
        self.objects.append(key)

        if self.on_save is not None:
            self.on_save()

        return key

    def delete(self, key):
        self.deleted.append(key)

        if key in self.objects:
            self.objects.remove(key)

        return True


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDatabase()
    monkeypatch.setattr(
        reservations_module,
        "get_db_connection",
        db.connection,
    )
    return db


@pytest.fixture
def fake_storage(monkeypatch, fake_db):
    storage = FakeObjectStorage(fake_db)
    monkeypatch.setattr(
        reservations_module.storage,
        "save_payment_proof",
        storage.save_payment_proof,
    )
    monkeypatch.setattr(
        reservations_module.storage,
        "delete",
        storage.delete,
    )
    return storage


@pytest.fixture
def logged_client(client):
    with client.session_transaction() as session:
        session["user_id"] = USER_ID
        session["nama"] = "Pelanggan"
        session["role"] = "customer"

    return client


def _upload(client, channel="GoPay"):
    return client.post(
        "/reservations/{}/payment".format(RESERVATION_ID),
        data={
            "channel": channel,
            "proof": (io.BytesIO(PNG_BYTES), "proof.png"),
        },
        content_type="multipart/form-data",
    )


def test_upload_runs_without_open_database_connection(
    logged_client,
    fake_db,
    fake_storage,
):
    response = _upload(logged_client)

    assert response.status_code == 200
    assert fake_storage.depth_at_upload == 0
    assert fake_db.max_depth == 1
    assert fake_db.reservation["status_reservasi"] == "menunggu"
    assert fake_db.payment["bukti_object_key"] == fake_storage.objects[0]
    assert fake_db.log_inserts == 1


@pytest.mark.parametrize(
    "mode, expected_message",
    [
        ("missing", ALREADY_MESSAGE),
        ("status", ALREADY_MESSAGE),
        ("payment_status", ALREADY_MESSAGE),
        ("expired", EXPIRED_MESSAGE),
        ("proof", ALREADY_MESSAGE),
    ],
)
def test_phase3_recheck_failure_deletes_uploaded_object(
    logged_client,
    fake_db,
    fake_storage,
    mode,
    expected_message,
):
    def mutate_during_upload():
        if mode == "missing":
            fake_db.reservation = None
        elif mode == "status":
            fake_db.reservation["status_reservasi"] = "menunggu"
        elif mode == "payment_status":
            fake_db.payment["status_pembayaran"] = "dikonfirmasi"
        elif mode == "expired":
            fake_db.reservation["hold_expires_at"] = (
                datetime.now() - timedelta(minutes=1)
            )
        else:
            fake_db.payment["bukti_object_key"] = "bukti-pembayaran/lama.png"

    fake_storage.on_save = mutate_during_upload

    response = _upload(logged_client)

    assert response.status_code == 409
    assert response.get_json()["message"] == expected_message
    assert fake_storage.objects == []
    assert fake_storage.deleted == [fake_storage.last_key]
    assert fake_db.write_queries == []


def test_two_uploads_leave_only_one_object(
    logged_client,
    fake_db,
    fake_storage,
):
    first = _upload(logged_client)
    assert first.status_code == 200

    first_object = fake_storage.objects[0]

    fake_db.phase1_ignore_status = True
    fake_db.phase1_ignore_proof = True

    second = _upload(logged_client)

    assert second.status_code == 409
    assert second.get_json()["message"] == ALREADY_MESSAGE
    assert fake_storage.objects == [first_object]
    assert fake_storage.deleted == [fake_storage.last_key]
    assert fake_storage.last_key != first_object


def test_phase3_exception_deletes_uploaded_object(
    logged_client,
    fake_db,
    fake_storage,
):
    fake_db.fail_phase3 = True

    with pytest.raises(RuntimeError):
        _upload(logged_client)

    assert fake_storage.objects == []
    assert fake_storage.deleted == [fake_storage.last_key]


def test_commit_exception_deletes_uploaded_object(
    logged_client,
    fake_db,
    fake_storage,
):
    fake_storage.on_save = lambda: setattr(fake_db, "fail_on_commit", True)

    with pytest.raises(RuntimeError):
        _upload(logged_client)

    assert fake_storage.objects == []
    assert fake_storage.deleted == [fake_storage.last_key]


def test_storage_error_returns_503_without_database_writes(
    logged_client,
    fake_db,
    fake_storage,
):
    fake_storage.error = reservations_module.storage.StorageError(
        "Penyimpanan cloud tidak dapat dihubungi. Coba lagi sebentar."
    )

    response = _upload(logged_client)

    assert response.status_code == 503
    assert response.get_json()["message"] == (
        "Penyimpanan cloud tidak dapat dihubungi. Coba lagi sebentar."
    )
    assert fake_storage.depth_at_upload == 0
    assert fake_storage.deleted == []
    assert fake_db.write_queries == []
    assert fake_db.log_inserts == 0
