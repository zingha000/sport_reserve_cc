import pytest
from flask import Flask, jsonify

from app import rate_limit as rl


@pytest.fixture(autouse=True)
def _bersihkan_penghitung():
    rl.reset()
    yield
    rl.reset()


def buat_app(enabled=True):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = enabled

    @app.post("/uji")
    @rl.rate_limit(
        "uji", limit=3, window=60, key=rl.by_ip_and_email,
        message="Terlalu banyak percobaan.",
    )
    def uji():
        return jsonify({"ok": True})

    return app


def test_permintaan_di_atas_batas_ditolak_429_dengan_retry_after():
    client = buat_app().test_client()

    for _ in range(3):
        assert client.post("/uji", json={"email": "a@x.com"}).status_code == 200

    respons = client.post("/uji", json={"email": "a@x.com"})
    assert respons.status_code == 429
    assert respons.get_json()["message"] == "Terlalu banyak percobaan."
    assert int(respons.headers["Retry-After"]) >= 1


def test_kunci_berbeda_dihitung_terpisah():
    client = buat_app().test_client()

    for _ in range(3):
        client.post("/uji", json={"email": "a@x.com"})

    assert client.post("/uji", json={"email": "a@x.com"}).status_code == 429
    assert client.post("/uji", json={"email": "b@x.com"}).status_code == 200


def test_batas_pulih_setelah_jendela_waktu_berlalu(monkeypatch):
    jam = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: jam[0])
    client = buat_app().test_client()

    for _ in range(3):
        client.post("/uji", json={"email": "a@x.com"})
    assert client.post("/uji", json={"email": "a@x.com"}).status_code == 429

    jam[0] += 61
    assert client.post("/uji", json={"email": "a@x.com"}).status_code == 200


def test_klien_browser_menerima_teks_biasa_bukan_json():
    client = buat_app().test_client()

    for _ in range(3):
        client.post("/uji", headers={"Accept": "text/html"})

    respons = client.post("/uji", headers={"Accept": "text/html"})
    assert respons.status_code == 429
    assert respons.mimetype == "text/plain"


def test_dinonaktifkan_lewat_konfigurasi():
    client = buat_app(enabled=False).test_client()

    for _ in range(10):
        assert client.post("/uji", json={"email": "a@x.com"}).status_code == 200