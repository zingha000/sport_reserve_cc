import psycopg
import pytest
from psycopg_pool import PoolTimeout

from app import storage
from app.routes import health as health_module


@pytest.fixture
def fake_health(monkeypatch):
    monkeypatch.setattr(health_module, "ping_database", lambda timeout_seconds=3: None)
    monkeypatch.setattr(storage, "ping", lambda: True)


def test_health_ok(client, fake_health):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "database": "ok",
        "storage": "ok",
    }


def test_health_database_error(client, monkeypatch):
    def fail(timeout_seconds=3):
        raise psycopg.OperationalError("database down")

    monkeypatch.setattr(health_module, "ping_database", fail)
    monkeypatch.setattr(storage, "ping", lambda: True)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "database": "error",
        "storage": "ok",
    }


def test_health_storage_error(client, monkeypatch):
    monkeypatch.setattr(health_module, "ping_database", lambda timeout_seconds=3: None)

    def fail():
        raise storage.StorageError("storage down")

    monkeypatch.setattr(storage, "ping", fail)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "database": "ok",
        "storage": "error",
    }


def test_lock_error_returns_409_json(app, client):
    def boom():
        raise psycopg.errors.LockNotAvailable("lock")

    app.add_url_rule("/__test/lock", "test_lock", boom)

    response = client.get("/__test/lock", headers={"Accept": "application/json"})

    assert response.status_code == 409
    assert response.get_json() == {
        "success": False,
        "message": "Sedang diproses pengguna lain. Coba lagi sebentar.",
    }


def test_operational_error_returns_503_json(app, client):
    def boom():
        raise psycopg.OperationalError("connection refused")

    app.add_url_rule("/__test/down", "test_down", boom)

    response = client.get("/__test/down", headers={"Accept": "application/json"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.get_json() == {
        "success": False,
        "message": "Layanan sedang sibuk. Coba lagi dalam beberapa detik.",
    }


def test_pool_timeout_returns_503_html(app, client):
    def boom():
        raise PoolTimeout("pool timeout")

    app.add_url_rule("/__test/pool", "test_pool", boom)

    response = client.get("/__test/pool", headers={"Accept": "text/html"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert b"Muat ulang" in response.data
