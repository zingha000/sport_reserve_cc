import logging
import os
import time
from contextlib import ExitStack, contextmanager
from threading import Lock

import psycopg
from flask import current_app, has_app_context
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

RETRY_DELAY = 1
POOL_RECONNECT_TIMEOUT = 20

_BREAKER_LOCK = Lock()
_breaker_open_until = None
_breaker_error = None
_breaker_probing = False

_default_pool = None
_default_pool_lock = Lock()

_PERMANENT_STATES = ("28", "3D000")
_TRANSIENT_STATES = ("08", "57P01", "57P02", "57P03")

_TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "connection refused",
    "could not translate host name",
    "server closed the connection unexpectedly",
    "connection reset",
    "network is unreachable",
    "terminating connection",
    "starting up",
    "too many connections",
)

_PERMANENT_MARKERS = (
    "password authentication failed",
    "authentication failed",
    "no pg_hba.conf entry",
    "does not exist",
    "invalid catalog name",
    "permission denied for database",
)


def _config(key, default=None):
    if has_app_context():
        return current_app.config.get(key, default)

    return os.getenv(key, default)


def _number_config(key, default, minimum=0):
    try:
        value = float(_config(key, default))
    except (TypeError, ValueError):
        value = float(default)

    return max(value, minimum)


def _database_url():
    url = _config("DATABASE_URL")

    if not url:
        raise ValueError("DATABASE_URL tidak ditemukan di file .env")

    return url


def _pool_max():
    try:
        value = int(_config("DB_POOL_MAX", 5))
    except (TypeError, ValueError):
        return 5

    return max(value, 1)


def _pool_timeout():
    return _number_config("DB_POOL_TIMEOUT", 3, minimum=1)


def _connect_timeout():
    return int(_number_config("DB_CONNECT_TIMEOUT", 10, minimum=1))


def _probe_timeout():
    return _number_config("DB_PROBE_TIMEOUT", 2, minimum=1)


def _acquire_budget():
    return _number_config("DB_ACQUIRE_BUDGET", 6, minimum=1)


def _breaker_seconds():
    return _number_config("DB_BREAKER_SECONDS", 15, minimum=0)


def _breaker_permanent_seconds():
    return _number_config("DB_BREAKER_PERMANENT_SECONDS", 30, minimum=0)


def _pool_kwargs():
    return {
        "row_factory": dict_row,
        "connect_timeout": _connect_timeout(),
        "prepare_threshold": None,
    }


def _create_pool():
    return ConnectionPool(
        conninfo=_database_url(),
        min_size=1,
        max_size=_pool_max(),
        timeout=_pool_timeout(),
        reconnect_timeout=POOL_RECONNECT_TIMEOUT,
        max_lifetime=300,
        max_idle=120,
        check=ConnectionPool.check_connection,
        kwargs=_pool_kwargs(),
        open=False,
    )


def _get_pool():
    if has_app_context():
        pool = current_app.extensions.get("db_pool")

        if pool is None:
            pool = _create_pool()
            current_app.extensions["db_pool"] = pool
            pool.open()

        return pool

    global _default_pool

    if _default_pool is None:
        with _default_pool_lock:
            if _default_pool is None:
                _default_pool = _create_pool()
                _default_pool.open()

    return _default_pool


def _is_permanent_failure(error):
    state = getattr(error, "sqlstate", None)

    if state and state.startswith("28"):
        return True

    if state == "3D000":
        return True

    message = str(error).lower()
    return any(marker in message for marker in _PERMANENT_MARKERS)


def _is_retryable(error):
    if isinstance(error, PoolTimeout):
        return True

    if _is_permanent_failure(error):
        return False

    state = getattr(error, "sqlstate", None)

    if state and (state.startswith("08") or state in _TRANSIENT_STATES):
        return True

    message = str(error).lower()

    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return True

    return isinstance(error, psycopg.OperationalError)


def _connection_error(error):
    if isinstance(error, (psycopg.OperationalError, PoolTimeout)):
        return error

    converted = psycopg.OperationalError(str(error))
    converted.sqlstate = getattr(error, "sqlstate", None)
    return converted


def _breaker_before_acquire():
    """False bila sirkuit tertutup; True bila request ini menjadi probe."""
    global _breaker_probing

    with _BREAKER_LOCK:
        if _breaker_open_until is None:
            return False

        if time.monotonic() < _breaker_open_until:
            raise _breaker_error

        if _breaker_probing:
            raise _breaker_error

        _breaker_probing = True
        return True


def _breaker_cancel_probe():
    global _breaker_probing

    with _BREAKER_LOCK:
        _breaker_probing = False


def _breaker_duration(permanent):
    if permanent:
        configured = _breaker_permanent_seconds()
    else:
        configured = _breaker_seconds()

    return max(configured, _acquire_budget() + 1)


def _breaker_failure(error, permanent, wait_ms):
    global _breaker_open_until, _breaker_error, _breaker_probing

    seconds = _breaker_duration(permanent)
    reason = "permanen" if permanent else "sementara"

    with _BREAKER_LOCK:
        log_open = _breaker_open_until is None or _breaker_probing
        _breaker_open_until = time.monotonic() + seconds
        _breaker_error = error
        _breaker_probing = False

    if log_open:
        log.warning(
            "Circuit breaker database dibuka (%s, %s detik) setelah gagal "
            "mendapatkan koneksi dalam %d ms.",
            reason,
            seconds,
            wait_ms,
        )
    else:
        log.warning(
            "Gagal mendapatkan koneksi database dalam %d ms; sirkuit sudah "
            "terbuka.",
            wait_ms,
        )


def _breaker_success():
    global _breaker_open_until, _breaker_error, _breaker_probing

    with _BREAKER_LOCK:
        was_open = _breaker_open_until is not None or _breaker_probing
        _breaker_open_until = None
        _breaker_error = None
        _breaker_probing = False

    if was_open:
        log.warning("Circuit breaker database ditutup.")


def _set_local_timeouts(conn):
    lock_timeout = _config("DB_LOCK_TIMEOUT", "3s")
    statement_timeout = _config("DB_STATEMENT_TIMEOUT", "10s")

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SET LOCAL lock_timeout = {}").format(
                sql.Literal(str(lock_timeout))
            )
        )
        cur.execute(
            sql.SQL("SET LOCAL statement_timeout = {}").format(
                sql.Literal(str(statement_timeout))
            )
        )


def _remaining(deadline):
    return deadline - time.monotonic()


def _try_pool(pool, stack, deadline):
    remaining = _remaining(deadline)

    if remaining <= 0:
        raise PoolTimeout("Batas waktu koneksi database habis.")

    timeout = max(0.05, min(_pool_timeout(), remaining))
    return stack.enter_context(pool.connection(timeout=timeout))


def _probe_database(deadline):
    remaining = _remaining(deadline)

    if remaining < 1:
        raise PoolTimeout("Batas waktu koneksi database habis.")

    timeout = max(1, min(int(_probe_timeout()), int(remaining)))
    conn = None

    try:
        conn = psycopg.connect(
            _database_url(),
            connect_timeout=timeout,
            prepare_threshold=None,
        )
    finally:
        if conn is not None:
            conn.close()


def _retry_transient(pool, stack, deadline, last_error):
    if _remaining(deadline) <= RETRY_DELAY:
        raise _connection_error(last_error)

    time.sleep(RETRY_DELAY)

    try:
        return _try_pool(pool, stack, deadline)
    except (psycopg.Error, PoolTimeout) as error:
        raise _connection_error(error)


def _acquire_connection(pool, stack, deadline):
    try:
        return _try_pool(pool, stack, deadline)
    except (psycopg.Error, PoolTimeout) as error:
        if _is_permanent_failure(error):
            raise _connection_error(error)

        if not isinstance(error, PoolTimeout):
            if not _is_retryable(error):
                raise _connection_error(error)

            return _retry_transient(pool, stack, deadline, error)

        first_error = error

    if _remaining(deadline) < 1:
        raise first_error

    try:
        _probe_database(deadline)
    except psycopg.Error as probe_error:
        if _is_permanent_failure(probe_error):
            raise _connection_error(probe_error)

        if not _is_retryable(probe_error):
            raise _connection_error(probe_error)

        return _retry_transient(pool, stack, deadline, probe_error)

    return _try_pool(pool, stack, deadline)


@contextmanager
def get_db_connection():
    """Koneksi dari pool; commit normal, rollback saat exception.

    Total waktu mendapatkan koneksi dibatasi DB_ACQUIRE_BUDGET. Retry dan
    circuit breaker hanya berlaku saat mendapatkan koneksi, bukan di tengah
    transaksi yang sudah berjalan.
    """
    started = time.monotonic()
    deadline = started + _acquire_budget()
    probing = _breaker_before_acquire()
    stack = ExitStack()

    try:
        pool = _get_pool()
        conn = _acquire_connection(pool, stack, deadline)
        _set_local_timeouts(conn)
    except (psycopg.OperationalError, PoolTimeout) as error:
        wait_ms = int((time.monotonic() - started) * 1000)
        _breaker_failure(error, _is_permanent_failure(error), wait_ms)
        stack.close()
        raise
    except BaseException:
        if probing:
            _breaker_cancel_probe()
        stack.close()
        raise

    _breaker_success()

    try:
        yield conn
    finally:
        stack.close()


def ping_database(timeout_seconds=3):
    """SELECT 1 cepat untuk health check, tanpa retry dan tanpa breaker."""
    pool = _get_pool()

    with pool.connection(timeout=timeout_seconds) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET LOCAL statement_timeout = {}").format(
                    sql.Literal("{}s".format(int(timeout_seconds)))
                )
            )
            cur.execute("SELECT 1")
            cur.fetchone()
