"""Tes foto lapangan dengan database & storage tiruan (tanpa jaringan)."""
import io

import pytest

from app import create_app, storage
from app.routes import field_photos

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class FakeDB:
    def __init__(self, total=0, field_exists=True, fail_on_insert=False):
        self.field_exists = field_exists
        self.photos = [
            {"id_foto": i + 1, "object_key": "lapangan/k%d.png" % i,
             "is_thumbnail": i == 0}
            for i in range(total)
        ]
        self.fail_on_insert = fail_on_insert
        self.inserted = []
        self.commits = 0
        self.open_connections = 0
        self.status = "aktif"

    def __call__(self):
        return FakeConn(self)


class FakeConn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.open_connections += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.db.open_connections -= 1
        if exc_type is None:
            self.db.commits += 1
        return False

    def cursor(self):
        return FakeCursor(self.db)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.row = None
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        db = self.db
        self.row, self.rows = None, []
        if "COUNT(*)" in sql:
            if db.field_exists:
                self.row = {"id_lapangan": params[0],
                            "total": len(db.photos)}
        elif sql.strip().startswith("INSERT INTO lapangan_foto"):
            if db.fail_on_insert:
                raise RuntimeError("db down")
            new = {"id_foto": len(db.photos) + 1, "object_key": params[1],
                   "is_thumbnail": params[3]}
            db.photos.append(new)
            db.inserted.append(new)
            self.row = {"id_foto": new["id_foto"]}
        elif "FOR UPDATE" in sql and "FROM lapangan WHERE" in sql:
            if db.field_exists:
                self.row = {"id_lapangan": params[0]}
        elif sql.strip().startswith("DELETE FROM lapangan_foto"):
            for p in db.photos:
                if p["id_foto"] == params[0]:
                    db.photos.remove(p)
                    self.row = {"object_key": p["object_key"],
                                "is_thumbnail": p["is_thumbnail"]}
                    break
        elif sql.strip().startswith("UPDATE lapangan_foto SET is_thumbnail = TRUE"):
            if db.photos and "SELECT id_foto" in sql:
                db.photos[0]["is_thumbnail"] = True
        elif "SELECT id_foto FROM lapangan_foto" in sql:
            for p in db.photos:
                if p["id_foto"] == params[0]:
                    self.row = {"id_foto": p["id_foto"]}
        elif "SELECT f.object_key" in sql:
            for p in db.photos:
                if p["id_foto"] == params[0]:
                    self.row = {"object_key": p["object_key"],
                                "status": db.status}

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


@pytest.fixture
def env(monkeypatch):
    class Env:
        pass

    e = Env()
    e.deleted, e.saved = [], []
    monkeypatch.setattr(storage, "save_field_photo",
                        lambda d, m: e.saved.append(1) or "lapangan/new.png")
    monkeypatch.setattr(storage, "delete", lambda k: e.deleted.append(k))
    monkeypatch.setattr(storage, "presigned_url", lambda k: "https://s3/" + k)
    app = create_app()
    app.config["TESTING"] = True
    e.app = app

    def setup(db, role="admin"):
        monkeypatch.setattr(field_photos, "get_db_connection", db)
        client = app.test_client()
        if role:
            with client.session_transaction() as s:
                s["user_id"], s["role"] = 1, role
        return client

    e.setup = setup
    return e


def upload(client, data=PNG, name="a.png"):
    return client.post("/admin/fields/1/photos",
                       data={"photo": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def test_upload_ok_first_photo_is_thumbnail_and_db_not_open_during_upload(env, monkeypatch):
    db = FakeDB(total=0)
    client = env.setup(db)

    def save(d, m):
        assert db.open_connections == 0  # tidak ada koneksi saat unggah
        return "lapangan/new.png"

    monkeypatch.setattr(storage, "save_field_photo", save)
    r = upload(client)
    assert r.status_code == 200
    assert db.inserted[0]["is_thumbnail"] is True
    assert env.deleted == []


def test_second_photo_not_thumbnail(env):
    db = FakeDB(total=1)
    assert upload(env.setup(db)).status_code == 200
    assert db.inserted[0]["is_thumbnail"] is False


def test_full_field_rejected_before_upload(env):
    db = FakeDB(total=field_photos.MAX_PHOTOS_PER_FIELD)
    r = upload(env.setup(db))
    assert r.status_code == 409
    assert env.saved == [] and env.deleted == []


def test_db_failure_deletes_object_exactly_once(env):
    db = FakeDB(total=0, fail_on_insert=True)
    client = env.setup(db)
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    r = upload(client)
    assert r.status_code == 500
    assert env.deleted == ["lapangan/new.png"]


def test_missing_field_404_no_upload(env):
    r = upload(env.setup(FakeDB(field_exists=False)))
    assert r.status_code == 404 and env.saved == []


def test_invalid_type_and_empty(env):
    client = env.setup(FakeDB())
    assert upload(client, b"GIF89a....").status_code == 400
    assert upload(client, b"").status_code == 400
    assert env.saved == []


def test_too_large_rejected(env):
    r = upload(env.setup(FakeDB()), PNG + b"0" * (5 * 1024 * 1024))
    assert r.status_code == 413
    assert env.saved == []


def test_storage_error_503_no_db_write(env, monkeypatch):
    db = FakeDB()
    client = env.setup(db)

    def boom(d, m):
        raise storage.StorageError("cloud mati")

    monkeypatch.setattr(storage, "save_field_photo", boom)
    r = upload(client)
    assert r.status_code == 503 and db.inserted == []


def test_customer_and_anonymous_blocked(env):
    assert upload(env.setup(FakeDB(), role="customer")).status_code == 403
    assert upload(env.setup(FakeDB(), role=None)).status_code == 401


def test_delete_removes_object_after_commit_and_promotes(env):
    db = FakeDB(total=2)
    client = env.setup(db)
    r = client.post("/admin/fields/1/photos/1/delete")
    assert r.status_code == 200
    assert env.deleted == ["lapangan/k0.png"]
    assert db.photos[0]["is_thumbnail"] is True


def test_delete_unknown_photo_404_no_storage_call(env):
    r = env.setup(FakeDB(total=1)).post("/admin/fields/1/photos/99/delete")
    assert r.status_code == 404 and env.deleted == []


def test_set_thumbnail_unknown_404(env):
    r = env.setup(FakeDB(total=1)).post("/admin/fields/1/photos/99/thumbnail")
    assert r.status_code == 404


def test_public_photo_redirects_with_cache_header(env):
    r = env.setup(FakeDB(total=1), role=None).get("/fields/1/photos/1")
    assert r.status_code == 302
    assert r.headers["Location"] == "https://s3/lapangan/k0.png"
    assert "max-age=240" in r.headers["Cache-Control"]


def test_inactive_field_photo_hidden_from_public(env):
    db = FakeDB(total=1)
    client = env.setup(db, role=None)
    db.status = "nonaktif"
    assert client.get("/fields/1/photos/1").status_code == 404


def test_load_photos_single_query_and_thumbnail_first(env):
    class Cur:
        calls = 0

        def execute(self, sql, params):
            Cur.calls += 1

        def fetchall(self):
            return [{"id_foto": 7, "id_lapangan": 1},
                    {"id_foto": 8, "id_lapangan": 1}]

    fields = [{"id": 1}, {"id": 2}]
    with env.app.test_request_context():
        field_photos.load_photos(Cur(), fields)
    assert Cur.calls == 1
    assert fields[0]["image"].endswith("/fields/1/photos/7")
    assert len(fields[0]["photos"]) == 2
    assert fields[1]["image"] is None