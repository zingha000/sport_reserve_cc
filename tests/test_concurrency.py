import io
import os
import threading
import time
import uuid
from collections import Counter
from datetime import date, time as dt_time, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values
from psycopg.rows import dict_row

import app.database as database
import app.routes.reservations as reservations_module
from app import create_app


_ENV_FILE = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
_RAW_TEST_URL = os.getenv("TEST_DATABASE_URL") or _ENV_FILE.get(
    "TEST_DATABASE_URL"
)
_MAIN_URLS = {
    url for url in (
        os.getenv("DATABASE_URL"),
        _ENV_FILE.get("DATABASE_URL"),
    ) if url
}

if _RAW_TEST_URL and _RAW_TEST_URL in _MAIN_URLS:
    raise RuntimeError(
        "TEST_DATABASE_URL harus memakai database terpisah dari DATABASE_URL."
    )

if _RAW_TEST_URL and str(_RAW_TEST_URL).startswith(
    ("postgresql://", "postgres://")
):
    TEST_DATABASE_URL = _RAW_TEST_URL
    _SKIP_REASON = ""
else:
    TEST_DATABASE_URL = None
    _SKIP_REASON = (
        "TEST_DATABASE_URL belum diset ke URI PostgreSQL yang valid; "
        "tes konkurensi dilewati."
    )

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.skipif(not TEST_DATABASE_URL, reason=_SKIP_REASON),
]

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"concurrency-proof"
DEFAULT_START = "09:00"
DEFAULT_END = "10:00"


class ConcurrencyEnv:
    def __init__(self, prefix, user_ids, field_id, method_id, channel, day):
        self.prefix = prefix
        self.user_ids = user_ids
        self.field_id = field_id
        self.method_id = method_id
        self.channel = channel
        self.day = day
        self.apps = []

    def connect(self):
        return psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row)

    def client(self, app, user_id):
        client = app.test_client()

        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["nama"] = "ctest_customer"
            session["role"] = "customer"

        return client

    def payload(self, start=DEFAULT_START, end=DEFAULT_END):
        return {
            "channel": self.channel,
            "field_id": self.field_id,
            "date": self.day.isoformat(),
            "start_time": start,
            "end_time": end,
            "duration": 1,
        }

    def make_app(
        self,
        *,
        pool_max=5,
        pool_timeout=3,
        acquire_budget=6,
        breaker_seconds=15,
        breaker_permanent_seconds=30,
    ):
        database._breaker_open_until = None
        database._breaker_error = None
        database._breaker_probing = False

        app = create_app()
        app.config.update(
            TESTING=True,
            PROPAGATE_EXCEPTIONS=False,
            SECRET_KEY="ctest-secret-key",
            DATABASE_URL=TEST_DATABASE_URL,
            DB_POOL_MAX=pool_max,
            DB_POOL_TIMEOUT=pool_timeout,
            DB_ACQUIRE_BUDGET=acquire_budget,
            DB_BREAKER_SECONDS=breaker_seconds,
            DB_BREAKER_PERMANENT_SECONDS=breaker_permanent_seconds,
        )
        self.apps.append(app)
        return app


class FakeUploadStorage:
    def __init__(self, prefix, barrier):
        self.prefix = prefix
        self.barrier = barrier
        self.objects = []
        self.deleted = []
        self._lock = threading.Lock()
        self._count = 0

    def save(self, data, mime_type):
        self.barrier.wait(timeout=10)

        with self._lock:
            self._count += 1
            key = "{}/proof-{}.png".format(self.prefix, self._count)
            self.objects.append(key)
            return key

    def delete(self, key):
        with self._lock:
            self.deleted.append(key)

            if key in self.objects:
                self.objects.remove(key)

        return True


def _cleanup(prefix, user_ids, field_id, method_id):
    conn = psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row)

    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM pembayaran_log
                WHERE id_pembayaran IN (
                    SELECT p.id_pembayaran
                    FROM pembayaran p
                    JOIN reservasi r ON r.id_reservasi = p.id_reservasi
                    WHERE r.id_user = ANY(%s) OR r.id_lapangan = %s
                )
            """, (user_ids, field_id))

            cur.execute("""
                DELETE FROM reservasi_log
                WHERE id_reservasi IN (
                    SELECT id_reservasi
                    FROM reservasi
                    WHERE id_user = ANY(%s) OR id_lapangan = %s
                )
            """, (user_ids, field_id))

            cur.execute("""
                DELETE FROM pembayaran
                WHERE id_reservasi IN (
                    SELECT id_reservasi
                    FROM reservasi
                    WHERE id_user = ANY(%s) OR id_lapangan = %s
                )
            """, (user_ids, field_id))

            cur.execute("""
                DELETE FROM reservasi
                WHERE id_user = ANY(%s) OR id_lapangan = %s
            """, (user_ids, field_id))

            cur.execute(
                "DELETE FROM tarif_lapangan WHERE id_lapangan = %s",
                (field_id,),
            )
            cur.execute(
                "DELETE FROM jam_operasional WHERE id_lapangan = %s",
                (field_id,),
            )
            cur.execute(
                "DELETE FROM lapangan WHERE id_lapangan = %s AND nama_lapangan = %s",
                (field_id, prefix + "_field"),
            )
            cur.execute(
                "DELETE FROM pengaturan_pembayaran WHERE id_pengaturan = %s",
                (method_id,),
            )
            cur.execute(
                "DELETE FROM users WHERE id_user = ANY(%s)",
                (user_ids,),
            )

        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def env():
    prefix = "ctest_" + uuid.uuid4().hex[:12]
    day = date.today() + timedelta(days=1)
    channel = prefix + "_pay"
    user_ids = []
    field_id = None
    method_id = None

    try:
        conn = psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row)

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (
                        nama, email, password_hash, role, status_akun
                    )
                    SELECT
                        %s || '_u' || n::text,
                        %s || '_u' || n::text || '@example.test',
                        'ctest-hash',
                        'customer',
                        'aktif'
                    FROM generate_series(1, 32) AS n
                    RETURNING id_user
                """, (prefix, prefix))
                user_ids = [row["id_user"] for row in cur.fetchall()]

                cur.execute("""
                    INSERT INTO lapangan (
                        nama_lapangan, deskripsi, luas_lapangan, status
                    )
                    VALUES (%s, %s, %s, 'aktif')
                    RETURNING id_lapangan
                """, (
                    prefix + "_field",
                    "Lapangan khusus tes konkurensi.",
                    "20x10",
                ))
                field_id = cur.fetchone()["id_lapangan"]

                cur.execute("""
                    INSERT INTO jam_operasional (
                        id_lapangan, hari, jam_buka, jam_tutup, status
                    )
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (
                    field_id,
                    day.isoweekday(),
                    dt_time(0, 0),
                    dt_time(23, 59),
                ))

                cur.execute("""
                    INSERT INTO tarif_lapangan (
                        id_lapangan,
                        hari,
                        jam_mulai,
                        jam_selesai,
                        harga_per_jam,
                        berlaku_mulai,
                        berlaku_sampai
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NULL)
                """, (
                    field_id,
                    day.isoweekday(),
                    dt_time(0, 0),
                    dt_time(23, 59),
                    Decimal("100000"),
                    date.today() - timedelta(days=1),
                ))

                cur.execute("""
                    INSERT INTO pengaturan_pembayaran (
                        nama_pemilik,
                        nama_ewallet,
                        nomor_akun,
                        qr_object_key,
                        status_aktif
                    )
                    VALUES (%s, %s, %s, %s, TRUE)
                    RETURNING id_pengaturan
                """, (
                    prefix + "_owner",
                    channel,
                    "08123456789",
                    prefix + "/qr.png",
                ))
                method_id = cur.fetchone()["id_pengaturan"]

            conn.commit()
        finally:
            conn.close()
    except Exception:
        if user_ids and field_id:
            _cleanup(prefix, user_ids, field_id, method_id)
        raise

    concurrency_env = ConcurrencyEnv(
        prefix,
        user_ids,
        field_id,
        method_id,
        channel,
        day,
    )

    try:
        yield concurrency_env
    finally:
        for app in concurrency_env.apps:
            pool = app.extensions.get("db_pool")

            if pool is not None:
                pool.close()

        _cleanup(prefix, user_ids, field_id, method_id)


def _client_calls(env, app, user_ids, payload):
    clients = [env.client(app, user_id) for user_id in user_ids]

    return [
        lambda client=client: client.post(
            "/reservations/confirm",
            json=payload,
        )
        for client in clients
    ]


def _run_concurrent(callables, timeout=30):
    count = len(callables)
    barrier = threading.Barrier(count)
    results = [None] * count
    started = time.perf_counter()

    def run(index):
        call_started = time.perf_counter()

        try:
            barrier.wait(timeout=timeout)
            response = callables[index]()
            results[index] = (
                response.status_code,
                time.perf_counter() - call_started,
                response.headers.get("Retry-After"),
            )
        except BaseException as error:
            results[index] = (
                "exception",
                time.perf_counter() - call_started,
                repr(error),
            )

    threads = [
        threading.Thread(target=run, args=(index,), daemon=True)
        for index in range(count)
    ]

    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout

    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))

    alive = [thread for thread in threads if thread.is_alive()]
    total = time.perf_counter() - started

    return results, alive, total


def _percentile(values, percentile):
    if not values:
        return 0.0

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower

    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _report(name, results, total):
    statuses = Counter(result[0] for result in results)
    latencies = [result[1] for result in results]

    print(
        "{}: status={} total={:.3f}s p50={:.3f}s p95={:.3f}s".format(
            name,
            dict(statuses),
            total,
            _percentile(latencies, 50),
            _percentile(latencies, 95),
        )
    )

    return statuses


def _assert_no_exception(results):
    assert all(isinstance(result[0], int) for result in results), results


def _active_slot_count(env, day, start, end, user_ids=None):
    with env.connect() as conn:
        with conn.cursor() as cur:
            if user_ids is None:
                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM reservasi
                    WHERE id_lapangan = %s
                      AND tanggal = %s
                      AND jam_mulai = %s
                      AND jam_selesai = %s
                      AND status_reservasi IN (
                          'ditahan', 'menunggu', 'dikonfirmasi'
                      )
                """, (env.field_id, day, start, end))
            else:
                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM reservasi
                    WHERE id_user = ANY(%s)
                      AND status_reservasi = 'ditahan'
                      AND hold_expires_at > NOW()
                """, (user_ids,))

            return cur.fetchone()["total"]


def test_slot_race_exactly_one_winner(env):
    app = env.make_app(pool_max=12)
    payload = env.payload()
    callables = _client_calls(env, app, env.user_ids[:10], payload)

    results, alive, total = _run_concurrent(callables)
    statuses = _report("1 rebutan slot", results, total)

    assert not alive
    _assert_no_exception(results)
    assert statuses[201] == 1
    assert statuses[409] == 9
    assert sum(statuses.values()) == 10
    assert _active_slot_count(
        env,
        env.day,
        dt_time(9, 0),
        dt_time(10, 0),
    ) == 1


def test_double_click_same_payload_is_idempotent(env):
    app = env.make_app(pool_max=8)
    payload = env.payload()
    callables = _client_calls(
        env,
        app,
        [env.user_ids[0]] * 5,
        payload,
    )

    results, alive, total = _run_concurrent(callables)
    statuses = _report("2 klik ganda", results, total)

    assert not alive
    _assert_no_exception(results)
    assert statuses[201] == 1
    assert statuses[200] == 4
    assert statuses[409] == 0
    assert _active_slot_count(
        env,
        env.day,
        dt_time(9, 0),
        dt_time(10, 0),
    ) == 1


def test_active_hold_limit_only_allows_one(env):
    app = env.make_app(pool_max=4)
    app.config["MAX_ACTIVE_HOLDS"] = 1
    payloads = [
        env.payload("09:00", "10:00"),
        env.payload("10:00", "11:00"),
        env.payload("11:00", "12:00"),
    ]
    clients = [env.client(app, env.user_ids[0]) for _ in payloads]
    callables = [
        lambda client=client, payload=payload: client.post(
            "/reservations/confirm",
            json=payload,
        )
        for client, payload in zip(clients, payloads)
    ]

    results, alive, total = _run_concurrent(callables)
    statuses = _report("3 batas hold", results, total)

    assert not alive
    _assert_no_exception(results)
    assert statuses[201] == 1
    assert statuses[409] == 2
    assert _active_slot_count(env, env.day, None, None, [env.user_ids[0]]) == 1


def test_expired_hold_is_replaced_by_other_user(env):
    app = env.make_app(pool_max=4)
    old_user = env.user_ids[0]
    new_user = env.user_ids[1]
    old_code = env.prefix + "-old-payment"

    with env.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reservasi (
                    id_user,
                    id_lapangan,
                    tanggal,
                    jam_mulai,
                    jam_selesai,
                    durasi_jam,
                    harga_per_jam,
                    total_harga,
                    status_reservasi,
                    hold_expires_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, 1, 100000, 100000, 'ditahan',
                    NOW() - INTERVAL '1 minute'
                )
                RETURNING id_reservasi
            """, (
                old_user,
                env.field_id,
                env.day,
                dt_time(9, 0),
                dt_time(10, 0),
            ))
            old_reservation_id = cur.fetchone()["id_reservasi"]

            cur.execute("""
                INSERT INTO pembayaran (
                    id_reservasi,
                    kode_transaksi,
                    metode_pembayaran,
                    channel_pembayaran,
                    jumlah_pembayaran,
                    status_pembayaran
                )
                VALUES (%s, %s, 'QRIS', %s, 100000, 'menunggu')
            """, (old_reservation_id, old_code, env.channel))

        conn.commit()

    client = env.client(app, new_user)
    response = client.post(
        "/reservations/confirm",
        json=env.payload(),
    )
    assert response.status_code == 201

    with env.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status_reservasi, hold_expires_at
                FROM reservasi
                WHERE id_reservasi = %s
            """, (old_reservation_id,))
            old_reservation = cur.fetchone()

    assert old_reservation["status_reservasi"] == "kedaluwarsa"
    assert old_reservation["hold_expires_at"] is None
    assert _active_slot_count(
        env,
        env.day,
        dt_time(9, 0),
        dt_time(10, 0),
    ) == 1


def test_duplicate_payment_proof_upload_keeps_one_object(env, monkeypatch):
    app = env.make_app(pool_max=6)
    user_id = env.user_ids[0]
    code = env.prefix + "-upload-payment"
    barrier = threading.Barrier(2)
    fake_storage = FakeUploadStorage(env.prefix, barrier)

    with env.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reservasi (
                    id_user,
                    id_lapangan,
                    tanggal,
                    jam_mulai,
                    jam_selesai,
                    durasi_jam,
                    harga_per_jam,
                    total_harga,
                    status_reservasi,
                    hold_expires_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, 1, 100000, 100000, 'ditahan',
                    NOW() + INTERVAL '10 minutes'
                )
                RETURNING id_reservasi
            """, (
                user_id,
                env.field_id,
                env.day,
                dt_time(9, 0),
                dt_time(10, 0),
            ))
            reservation_id = cur.fetchone()["id_reservasi"]

            cur.execute("""
                INSERT INTO pembayaran (
                    id_reservasi,
                    kode_transaksi,
                    metode_pembayaran,
                    channel_pembayaran,
                    jumlah_pembayaran,
                    status_pembayaran
                )
                VALUES (%s, %s, 'QRIS', %s, 100000, 'menunggu')
            """, (reservation_id, code, env.channel))

        conn.commit()

    monkeypatch.setattr(
        reservations_module.storage,
        "save_payment_proof",
        fake_storage.save,
    )
    monkeypatch.setattr(
        reservations_module.storage,
        "delete",
        fake_storage.delete,
    )

    clients = [env.client(app, user_id) for _ in range(2)]

    def upload(client):
        return client.post(
            "/reservations/{}/payment".format(reservation_id),
            data={
                "proof": (io.BytesIO(PNG_BYTES), "proof.png"),
                "channel": env.channel,
            },
            content_type="multipart/form-data",
        )

    callables = [
        lambda client=client: upload(client)
        for client in clients
    ]
    results, alive, total = _run_concurrent(callables)
    statuses = _report("5 unggah bukti ganda", results, total)

    assert not alive
    _assert_no_exception(results)
    assert statuses[200] == 1
    assert statuses[409] == 1
    assert len(fake_storage.objects) == 1
    assert len(fake_storage.deleted) == 1
    assert fake_storage.deleted[0] not in fake_storage.objects

    with env.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT bukti_object_key
                FROM pembayaran
                WHERE id_reservasi = %s
            """, (reservation_id,))
            rows = cur.fetchall()

    assert len(rows) == 1
    assert rows[0]["bukti_object_key"] in fake_storage.objects


def test_pool_pressure_has_no_500_and_recovers(env):
    app = env.make_app(
        pool_max=3,
        pool_timeout=1,
        acquire_budget=2,
        breaker_seconds=1,
        breaker_permanent_seconds=1,
    )
    url = "/reservations/availability/{}?date={}".format(
        env.field_id,
        env.day.isoformat(),
    )
    clients = [env.client(app, user_id) for user_id in env.user_ids[:30]]
    callables = [
        lambda client=client: client.get(url)
        for client in clients
    ]

    results, alive, total = _run_concurrent(callables, timeout=20)
    statuses = _report("6 tekanan pool", results, total)

    assert not alive
    _assert_no_exception(results)
    assert statuses[500] == 0
    assert statuses[201] == 0

    for status, _, retry_after in results:
        assert status in (200, 409, 503)
        if status == 503:
            assert retry_after == "5"

    assert statuses[200] + statuses[409] > 0

    recovery = env.client(app, env.user_ids[0])
    deadline = time.monotonic() + 8
    response = None

    while time.monotonic() < deadline:
        response = recovery.get(url)

        if response.status_code == 200:
            break

        time.sleep(0.25)

    assert response is not None
    assert response.status_code == 200
