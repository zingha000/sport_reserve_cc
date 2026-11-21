import time

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from app import database


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        if hasattr(query, "as_string"):
            query = query.as_string(None)

        self.conn.queries.append(str(query))

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __init__(self):
        self.queries = []

    def cursor(self):
        return FakeCursor(self)


class FakeConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, fail_times=0, error=None):
        self.fail_times = fail_times
        self.error = error or psycopg.OperationalError("connection refused")
        self.attempts = 0
        self.conn = FakeConnection()

    def connection(self, timeout=None):
        self.attempts += 1

        if self.attempts <= self.fail_times:
            raise self.error

        return FakeConnectionContext(self.conn)


class FakeProbeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _use_pool(app, pool):
    app.extensions["db_pool"] = pool


def _reset_breaker():
    database._breaker_open_until = None
    database._breaker_error = None
    database._breaker_probing = False


@pytest.fixture(autouse=True)
def reset_breaker():
    _reset_breaker()
    yield
    _reset_breaker()


def _call(app, error=psycopg.OperationalError):
    with app.app_context():
        with pytest.raises(error):
            with database.get_db_connection():
                pass


def _fake_probe(monkeypatch, error=None):
    calls = []
    conn = FakeProbeConnection()

    def connect(*args, **kwargs):
        calls.append(kwargs)

        if error is not None:
            raise error

        return conn

    monkeypatch.setattr(database.psycopg, "connect", connect)
    return calls, conn


def test_get_db_connection_sets_local_timeouts(app):
    pool = FakePool()
    _use_pool(app, pool)

    with app.app_context():
        with database.get_db_connection():
            pass

    queries = " ".join(pool.conn.queries)

    assert "SET LOCAL lock_timeout = '3s'" in queries
    assert "SET LOCAL statement_timeout = '10s'" in queries


def test_transient_error_retries_once_then_succeeds(app, monkeypatch):
    sleeps = []
    monkeypatch.setattr(database.time, "sleep", sleeps.append)

    pool = FakePool(fail_times=1)
    _use_pool(app, pool)

    with app.app_context():
        with database.get_db_connection():
            pass

    assert pool.attempts == 2
    assert sleeps == [1]


def test_transient_error_stops_after_one_retry(app, monkeypatch):
    sleeps = []
    monkeypatch.setattr(database.time, "sleep", sleeps.append)

    pool = FakePool(fail_times=99)
    _use_pool(app, pool)

    _call(app)

    assert pool.attempts == 2
    assert sleeps == [1]


def test_authentication_error_is_not_retried(app):
    error = psycopg.errors.InvalidPassword("password authentication failed")
    pool = FakePool(fail_times=99, error=error)
    _use_pool(app, pool)

    _call(app, psycopg.OperationalError)

    assert pool.attempts == 1


def test_permanent_errors_are_classified_without_retry(app):
    for error in (
        psycopg.errors.InvalidPassword("password authentication failed"),
        psycopg.errors.InvalidCatalogName("database does not exist"),
        psycopg.OperationalError("password authentication failed for user"),
    ):
        _reset_breaker()
        pool = FakePool(fail_times=99, error=error)
        _use_pool(app, pool)

        _call(app, psycopg.OperationalError)

        assert pool.attempts == 1


def test_probe_permanent_error_opens_long_breaker(app, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(database.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)

    pool = FakePool(fail_times=99, error=PoolTimeout("pool timeout"))
    _use_pool(app, pool)

    error = psycopg.errors.InvalidPassword("password authentication failed")
    calls, _ = _fake_probe(monkeypatch, error)

    _call(app, psycopg.OperationalError)

    assert pool.attempts == 1
    assert len(calls) == 1
    assert database._breaker_open_until == 1000.0 + 30


def test_probe_transient_error_retries_once_then_opens(app, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(database.time, "monotonic", lambda: now[0])

    sleeps = []
    monkeypatch.setattr(database.time, "sleep", sleeps.append)

    pool = FakePool(fail_times=99, error=PoolTimeout("pool timeout"))
    _use_pool(app, pool)

    probe_error = psycopg.OperationalError("connection refused")
    calls, _ = _fake_probe(monkeypatch, probe_error)

    _call(app)

    assert pool.attempts == 2
    assert len(calls) == 1
    assert sleeps == [1]
    assert database._breaker_open_until == 1000.0 + 15


def test_probe_success_retries_pool_and_closes_circuit(app, monkeypatch):
    pool = FakePool(fail_times=1, error=PoolTimeout("pool timeout"))
    _use_pool(app, pool)

    calls, probe_conn = _fake_probe(monkeypatch)

    with app.app_context():
        with database.get_db_connection():
            pass

    assert pool.attempts == 2
    assert len(calls) == 1
    assert probe_conn.closed is True
    assert database._breaker_open_until is None


def test_open_circuit_fails_fast_without_pool(app, monkeypatch):
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)

    pool = FakePool(fail_times=99)
    _use_pool(app, pool)

    _call(app)
    assert pool.attempts == 2

    started = time.perf_counter()

    with app.app_context():
        for _ in range(10):
            with pytest.raises(psycopg.OperationalError):
                with database.get_db_connection():
                    pass

    elapsed = time.perf_counter() - started

    assert pool.attempts == 2
    assert elapsed < 0.05


def test_half_open_success_closes_circuit(app, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(database.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)

    pool = FakePool(fail_times=2)
    _use_pool(app, pool)

    _call(app)
    assert database._breaker_open_until is not None

    now[0] += 16

    with app.app_context():
        with database.get_db_connection():
            pass
        with database.get_db_connection():
            pass

    assert pool.attempts == 4
    assert database._breaker_open_until is None
    assert database._breaker_error is None


def test_half_open_failure_reopens_circuit(app, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(database.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)

    pool = FakePool(fail_times=99)
    _use_pool(app, pool)

    _call(app)
    assert pool.attempts == 2

    now[0] += 16
    _call(app)
    assert pool.attempts == 4

    now[0] += 1
    _call(app)

    assert pool.attempts == 4


def test_breaker_duration_always_exceeds_budget(app):
    app.config["DB_ACQUIRE_BUDGET"] = 20

    with app.app_context():
        assert database._breaker_duration(False) > 20
        assert database._breaker_duration(True) > 20


def test_ping_database_bypasses_open_circuit(app, monkeypatch):
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)

    failing_pool = FakePool(fail_times=99)
    _use_pool(app, failing_pool)
    _call(app)

    _use_pool(app, FakePool())

    with app.app_context():
        database.ping_database()

    assert database._breaker_open_until is not None


def test_pool_timeout_defaults_to_three(app):
    with app.app_context():
        assert database._pool_timeout() == 3


def test_real_pool_closed_port_fails_within_budget(app):
    app.config.update(
        DATABASE_URL="postgresql://test:test@127.0.0.1:1/test",
        DB_POOL_TIMEOUT=1,
        DB_ACQUIRE_BUDGET=2,
        DB_BREAKER_SECONDS=12,
    )
    app.extensions.pop("db_pool", None)

    budget = app.config["DB_ACQUIRE_BUDGET"]

    try:
        started = time.perf_counter()
        _call(app)
        first = time.perf_counter() - started

        started = time.perf_counter()
        _call(app)
        second = time.perf_counter() - started
    finally:
        pool = app.extensions.pop("db_pool", None)
        if pool is not None:
            pool.close(timeout=1)

    assert first <= budget + 1
    assert second < 0.05
