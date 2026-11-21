from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from psycopg.errors import ExclusionViolation

import app.routes.reservations as reservations_module


USER_ID = 1
FIELD_ID = 7
FIELD_NAME = "Lapangan A"

METHOD = {
    "id_pengaturan": 3,
    "nama_ewallet": "GoPay",
    "nama_pemilik": "SportReserve",
    "nomor_akun": "08123456789",
}


class FakeDatabase:
    def __init__(self):
        self.queries = []
        self.params = []
        self._next = None
        self._next_many = []
        self.holds = []
        self.next_reservation_id = 1
        self.inserted_reservations = 0
        self.inserted_payments = 0
        self.exclusion = False
        self.field_exists = True
        self.field_status = "aktif"
        self.operational = {
            "jam_buka": time(8, 0),
            "jam_tutup": time(22, 0),
            "status": True,
        }
        self.tariff = {"harga_per_jam": Decimal("100000")}

    def add_hold(
        self,
        start,
        end,
        expires_in_minutes=10,
        status="ditahan",
        day=None,
    ):
        reservation_id = self.next_reservation_id
        self.next_reservation_id += 1

        hold = {
            "id": reservation_id,
            "user_id": USER_ID,
            "field_id": FIELD_ID,
            "tanggal": day or (date.today() + timedelta(days=1)),
            "start": start,
            "end": end,
            "status": status,
            "hold_expires_at": (
                datetime.now() + timedelta(minutes=expires_in_minutes)
            ),
            "total": Decimal("100000"),
            "field_name": FIELD_NAME,
            "kode_transaksi": "RSV-EXISTING-{}".format(reservation_id),
            "channel": "GoPay",
            "amount": Decimal("100000"),
        }

        self.holds.append(hold)
        return hold

    def active_holds(self):
        now = datetime.now()
        return [
            hold for hold in self.holds
            if hold["status"] == "ditahan"
            and hold["hold_expires_at"] > now
        ]

    def availability_rows(self):
        now = datetime.now()
        rows = []

        for hold in self.holds:
            if hold["status"] in ("menunggu", "dikonfirmasi"):
                rows.append(hold)
            elif (
                hold["status"] == "ditahan"
                and hold["hold_expires_at"] > now
            ):
                rows.append(hold)

        return [
            {"jam_mulai": hold["start"], "jam_selesai": hold["end"]}
            for hold in sorted(rows, key=lambda item: item["start"])
        ]

    def method_for(self, channel):
        if channel.lower() == METHOD["nama_ewallet"].lower():
            return METHOD

        return None


class FakeCursor:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        sql = " ".join(str(query).split()).lower()
        self.db.queries.append(sql)
        self.db.params.append(params)
        self.db._next = None
        self.db._next_many = []

        if "pg_advisory_xact_lock" in sql:
            return

        if "with expired as" in sql:
            return

        if (
            "from reservasi r" in sql
            and "r.status_reservasi = 'ditahan'" in sql
        ):
            user_id, field_id, tanggal, start, end = params

            for hold in self.db.active_holds():
                if (
                    hold["user_id"] == user_id
                    and hold["field_id"] == field_id
                    and hold["tanggal"] == tanggal
                    and hold["start"] == start
                    and hold["end"] == end
                ):
                    method = self.db.method_for(hold["channel"])

                    self.db._next = {
                        "id_reservasi": hold["id"],
                        "hold_expires_at": hold["hold_expires_at"],
                        "total_harga": hold["total"],
                        "nama_lapangan": hold["field_name"],
                        "kode_transaksi": hold["kode_transaksi"],
                        "channel_pembayaran": hold["channel"],
                        "jumlah_pembayaran": hold["amount"],
                        "id_pengaturan": (
                            method["id_pengaturan"] if method else None
                        ),
                        "nama_ewallet": (
                            method["nama_ewallet"] if method else None
                        ),
                        "nama_pemilik": (
                            method["nama_pemilik"] if method else None
                        ),
                        "nomor_akun": (
                            method["nomor_akun"] if method else None
                        ),
                    }
                    return

            return

        if "count(*) as jumlah" in sql:
            self.db._next = {"jumlah": len(self.db.active_holds())}
            return

        if "from pengaturan_pembayaran" in sql:
            self.db._next = self.db.method_for(params[0])
            return

        if "select status, nama_lapangan from lapangan" in sql:
            if self.db.field_exists:
                self.db._next = {
                    "status": self.db.field_status,
                    "nama_lapangan": FIELD_NAME,
                }
            return

        if "select status from lapangan" in sql:
            if self.db.field_exists:
                self.db._next = {"status": self.db.field_status}
            return

        if "from jam_operasional" in sql:
            self.db._next = self.db.operational
            return

        if "from tarif_lapangan" in sql:
            self.db._next = self.db.tariff
            return

        if "insert into reservasi_log" in sql:
            return

        if "insert into reservasi" in sql:
            if self.db.exclusion:
                raise ExclusionViolation("overlap")

            user_id, field_id, tanggal, start, end, _, _, total, minutes = (
                params
            )
            reservation_id = self.db.next_reservation_id
            self.db.next_reservation_id += 1
            hold_expires_at = datetime.now() + timedelta(minutes=minutes)

            self.db.holds.append({
                "id": reservation_id,
                "user_id": user_id,
                "field_id": field_id,
                "tanggal": tanggal,
                "start": start,
                "end": end,
                "status": "ditahan",
                "hold_expires_at": hold_expires_at,
                "total": total,
                "field_name": FIELD_NAME,
                "kode_transaksi": None,
                "channel": None,
                "amount": total,
            })

            self.db.inserted_reservations += 1
            self.db._next = {
                "id_reservasi": reservation_id,
                "hold_expires_at": hold_expires_at,
            }
            return

        if "insert into pembayaran" in sql:
            reservation_id, code, channel, total = params
            self.db.inserted_payments += 1

            for hold in self.db.holds:
                if hold["id"] == reservation_id:
                    hold["kode_transaksi"] = code
                    hold["channel"] = channel
                    hold["amount"] = total

            self.db._next = {"kode_transaksi": code}
            return

        if "select jam_mulai, jam_selesai from reservasi" in sql:
            self.db._next_many = self.db.availability_rows()
            return

        raise AssertionError("Query tidak dikenali: {}".format(sql))

    def fetchone(self):
        return self.db._next

    def fetchall(self):
        return self.db._next_many


class FakeConnection:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)


class FakeConnectionContext:
    def __init__(self, db):
        self.conn = FakeConnection(db)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDatabase()
    monkeypatch.setattr(
        reservations_module,
        "get_db_connection",
        lambda: FakeConnectionContext(db),
    )
    return db


@pytest.fixture
def logged_client(client):
    with client.session_transaction() as session:
        session["user_id"] = USER_ID
        session["nama"] = "Pelanggan"
        session["role"] = "customer"

    return client


def _payload(start="10:00", end="11:00", day=None):
    return {
        "channel": "GoPay",
        "field_id": FIELD_ID,
        "date": (day or (date.today() + timedelta(days=1))).isoformat(),
        "start_time": start,
        "end_time": end,
        "duration": 1,
    }


def test_confirm_twice_is_idempotent(logged_client, fake_db):
    first = logged_client.post("/reservations/confirm", json=_payload())
    assert first.status_code == 201

    first_body = first.get_json()
    first_code = first_body["payment"]["transaction_code"]
    first_id = first_body["reservation"]["id"]

    second = logged_client.post("/reservations/confirm", json=_payload())
    assert second.status_code == 200

    second_body = second.get_json()
    assert second_body["idempotent"] is True
    assert second_body["reservation"]["id"] == first_id
    assert second_body["payment"]["transaction_code"] == first_code
    assert fake_db.inserted_reservations == 1
    assert fake_db.inserted_payments == 1


def test_active_hold_limit_blocks_third_hold(logged_client, fake_db):
    logged_client.application.config["MAX_ACTIVE_HOLDS"] = 2

    fake_db.add_hold(time(8, 0), time(9, 0))
    fake_db.add_hold(time(9, 0), time(10, 0))

    response = logged_client.post("/reservations/confirm", json=_payload())

    assert response.status_code == 409
    assert response.get_json()["message"] == (
        "Selesaikan atau tunggu pembayaran reservasi sebelumnya. "
        "Maksimal 2 jadwal ditahan."
    )
    assert fake_db.inserted_reservations == 0


def test_inactive_field_is_rejected(logged_client, fake_db):
    fake_db.field_status = "nonaktif"

    response = logged_client.post("/reservations/confirm", json=_payload())

    assert response.status_code == 409
    assert response.get_json()["message"] == "Lapangan sedang tidak tersedia."
    assert fake_db.inserted_reservations == 0


def test_closed_day_is_rejected(logged_client, fake_db):
    fake_db.operational = None

    response = logged_client.post("/reservations/confirm", json=_payload())

    assert response.status_code == 409
    assert response.get_json()["message"] == (
        "Lapangan tutup pada hari tersebut."
    )
    assert fake_db.inserted_reservations == 0


def test_outside_operational_hours_is_rejected(logged_client, fake_db):
    fake_db.operational = {
        "jam_buka": time(8, 0),
        "jam_tutup": time(10, 0),
        "status": True,
    }

    response = logged_client.post("/reservations/confirm", json=_payload())

    assert response.status_code == 409
    assert response.get_json()["message"] == (
        "Jadwal di luar jam operasional."
    )
    assert fake_db.inserted_reservations == 0


def test_advisory_lock_runs_first_and_query_order(logged_client, fake_db):
    response = logged_client.post("/reservations/confirm", json=_payload())
    assert response.status_code == 201

    queries = fake_db.queries

    assert "pg_advisory_xact_lock" in queries[0]
    assert "with expired as" in queries[1]

    markers = [
        ("from reservasi r", 2),
        ("count(*) as jumlah", 3),
        ("from pengaturan_pembayaran", 4),
        ("select status, nama_lapangan from lapangan", 5),
        ("from jam_operasional", 6),
        ("from tarif_lapangan", 7),
        ("insert into reservasi", 8),
        ("insert into pembayaran", 9),
        ("insert into reservasi_log", 10),
    ]

    for marker, index in markers:
        assert marker in queries[index]


def test_exclusion_violation_keeps_existing_message(logged_client, fake_db):
    fake_db.exclusion = True

    response = logged_client.post("/reservations/confirm", json=_payload())

    assert response.status_code == 409
    assert response.get_json()["message"] == (
        "Jadwal tersebut sudah dipesan. Pilih waktu lain."
    )
    assert fake_db.inserted_reservations == 0
    assert fake_db.inserted_payments == 0


def test_availability_does_not_count_expired_holds(logged_client, fake_db):
    fake_db.add_hold(time(8, 0), time(9, 0), expires_in_minutes=-5)
    fake_db.add_hold(time(9, 0), time(10, 0), expires_in_minutes=5)

    response = logged_client.get(
        "/reservations/availability/{}?date={}".format(
            FIELD_ID,
            (date.today() + timedelta(days=1)).isoformat(),
        )
    )

    body = response.get_json()

    assert response.status_code == 200
    assert body["is_open"] is True
    assert body["reservations"] == [{"start": "09:00", "end": "10:00"}]


def test_availability_rejects_inactive_field(logged_client, fake_db):
    fake_db.field_status = "nonaktif"

    response = logged_client.get(
        "/reservations/availability/{}?date={}".format(
            FIELD_ID,
            (date.today() + timedelta(days=1)).isoformat(),
        )
    )

    body = response.get_json()

    assert response.status_code == 200
    assert body["is_open"] is False
    assert body["message"] == "Lapangan sedang tidak tersedia."
    assert body["reservations"] == []
