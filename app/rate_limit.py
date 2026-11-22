"""Pembatas laju permintaan (rate limiter) sederhana di memori.

Algoritma: sliding window. Untuk tiap kunci (mis. IP + email) kita simpan
waktu permintaan terakhir; jika jumlahnya dalam jendela waktu melebihi batas,
permintaan ditolak dengan HTTP 429 dan header Retry-After.

Catatan: penghitung hidup di memori satu proses. Cocok untuk satu instance;
bila di-deploy ke banyak instance, pindahkan penghitung ke penyimpanan bersama.
"""

import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import current_app, jsonify, request, session

_lock = threading.Lock()
_hits = defaultdict(deque)   # kunci -> deque waktu permintaan (monotonic)
_windows = {}                # kunci -> panjang jendela (detik)
_last_cleanup = 0.0
CLEANUP_INTERVAL = 60.0


def reset():
    """Kosongkan semua penghitung (dipakai oleh tes)."""
    with _lock:
        _hits.clear()
        _windows.clear()


def _cleanup(now):
    global _last_cleanup
    if now - _last_cleanup < CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    for key in list(_hits):
        window = _windows.get(key, 0)
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if not q:
            del _hits[key]
            _windows.pop(key, None)


def check_limit(bucket, key, limit, window):
    """Catat satu permintaan. Kembalikan (diizinkan, detik_tunggu)."""
    now = time.monotonic()
    full_key = (bucket, key)
    with _lock:
        q = _hits[full_key]
        _windows[full_key] = window
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            retry_after = int(q[0] + window - now) + 1
            return False, retry_after
        q.append(now)
        _cleanup(now)
        return True, 0


# --- fungsi pembentuk kunci ---------------------------------------------

def by_ip():
    return request.remote_addr or "unknown"


def by_user():
    return "user:%s" % session.get("user_id", by_ip())


def by_ip_and_email():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    return "%s|%s" % (by_ip(), email)


# --- dekorator -----------------------------------------------------------

def rate_limit(bucket, limit, window, key=by_ip, message=None):
    """Batasi `limit` permintaan per `window` detik untuk tiap kunci."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            enabled = current_app.config.get(
                "RATELIMIT_ENABLED", not current_app.testing
            )
            if not enabled:
                return view(*args, **kwargs)

            allowed, retry_after = check_limit(bucket, key(), limit, window)
            if allowed:
                return view(*args, **kwargs)

            text = message or (
                "Terlalu banyak permintaan. Coba lagi dalam %d detik." % retry_after
            )
            wants_json = (
                request.is_json
                or request.accept_mimetypes.best != "text/html"
            )
            if wants_json:
                response = jsonify({"success": False, "message": text})
            else:
                response = current_app.response_class(text, mimetype="text/plain")
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        return wrapper

    return decorator