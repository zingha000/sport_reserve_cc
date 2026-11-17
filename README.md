
# SportReserve

SportReserve adalah aplikasi web untuk melakukan reservasi lapangan futsal secara online. Aplikasi ini dikembangkan menggunakan Flask sebagai backend dan Neon PostgreSQL sebagai database.

## Teknologi

- Python
- Flask
- PostgreSQL (Neon)
- Psycopg
- HTML, CSS, dan JavaScript
- Neon Object Storage (penyimpanan file)

## Struktur Proyek

```text
sport_reserve_cc/
├── app/
│   ├── models/
│   ├── routes/
│   ├── templates/
│   ├── static/
│   ├── config.py
│   ├── database.py
│   ├── utils.py
│   └── __init__.py
├── database/
│   ├── schema.sql
│   ├── create_admin.py
│   ├── reset_admin_password.py
│   ├── test_connection.py
│   └── test_flask_db.py
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── README.md
```

## Instalasi

### 1. Clone repository

```bash
git clone https://github.com/zingha000/sport_reserve_cc.git
cd sport_reserve_cc
```

### 2. Buat virtual environment

```bash
python -m venv venv
```

### 3. Aktifkan virtual environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 4. Instal dependensi

```bash
pip install -r requirements.txt
```

### 5. Konfigurasi environment

Salin `.env.example` menjadi `.env`.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Sesuaikan konfigurasi di dalam `.env`:

- `FLASK_APP`: run.py
- `FLASK_DEBUG`: True untuk pengembangan lokal
- `SECRET_KEY`: gunakan secret key sendiri
- `DATABASE_URL`: gunakan connection string Neon PostgreSQL

Jangan membagikan file `.env` atau mengunggahnya ke GitHub.

### 6. Siapkan database

Pastikan database Neon PostgreSQL sudah tersedia dan koneksi telah dikonfigurasi.

Jalankan SQL pada `database/schema.sql` apabila membuat database baru.

### 7. Jalankan aplikasi

```bash
python run.py
```

Aplikasi berjalan secara lokal pada:

http://127.0.0.1:5000

## Endpoint API

| Method | Endpoint | Keterangan |
|---|---|---|
| POST | /auth/register | Registrasi pengguna |
| POST | /auth/login | Login pengguna |
| POST | /auth/logout | Logout pengguna |
| GET | /auth/me | Informasi session |
| GET | /admin/dashboard | Dashboard admin |

## Role Pengguna

- Customer: pengguna yang melakukan reservasi lapangan.
- Admin: pengelola data lapangan dan reservasi.

## Database

Database menggunakan PostgreSQL melalui layanan Neon. Struktur tabel tersedia di `database/schema.sql`.

## Catatan Pengembangan

Proyek ini dikembangkan secara bertahap dan dapat dilanjutkan oleh anggota tim melalui repository GitHub.

Pastikan setiap anggota menggunakan file `.env` masing-masing dan tidak membagikan kredensial database.
