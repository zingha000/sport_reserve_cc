
# CATATAN PENGERJAAN SPORTRESERVE

## 1. Status Proyek

Proyek berada pada tahap penyelesaian fondasi backend dan persiapan kolaborasi tim.

Repository:
https://github.com/zingha000/sport_reserve_cc

Branch utama:
main

Direktori lokal:
C:\project\sport_reserve_cc

## 2. Lingkungan Pengembangan

- OS: Windows.
- Python: 3.14.0.
- Flask: 3.1.3.
- Psycopg: 3.3.9.
- PostgreSQL: Neon PostgreSQL.
- Virtual environment: venv.
- Server lokal: http://127.0.0.1:5000.

## 3. Pekerjaan yang Sudah Dilakukan

### A. Persiapan Proyek
- Struktur folder Flask dibuat.
- Application factory dibuat.
- File run.py tersedia.
- Virtual environment dibuat.
- Dependensi Python dipasang.
- File requirements.txt dibuat.
- File .gitignore dibuat.
- File .env.example dibuat.

### B. Database
- Koneksi Neon PostgreSQL berhasil.
- File database/schema.sql dibuat.
- Sebanyak 12 tabel telah dibuat.
- Struktur relasi database telah disiapkan.
- Tabel pengaturan_pembayaran ditambahkan untuk konfigurasi QRIS statis.

### C. Object Storage
- Project Neon Object Storage tersedia.
- Bucket sportreserve-images telah dibuat.
- Bucket menggunakan akses Private.
- Integrasi Object Storage ke Flask belum selesai.

### D. Backend Flask
- Application factory berjalan.
- Blueprint auth, fields, reservations, dan admin telah disiapkan.
- Koneksi database melalui app/database.py tersedia.
- Fungsi proteksi akses tersedia di app/utils.py.

### E. Autentikasi
- Registrasi customer berhasil.
- Login customer berhasil.
- Logout berhasil.
- Pemeriksaan session berhasil.
- Password disimpan menggunakan password hash.
- Akun admin berhasil dibuat melalui script khusus.
- Login admin berhasil.
- Customer ditolak ketika mengakses endpoint admin dengan status 403.

Catatan:
Pastikan endpoint dashboard admin menghasilkan 200 OK menggunakan session admin sebelum menyatakan seluruh pengujian otorisasi selesai.

## 4. Endpoint yang Sudah Disiapkan

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | /auth/register | Registrasi |
| POST | /auth/login | Login |
| POST | /auth/logout | Logout |
| GET | /auth/me | Pemeriksaan session |
| GET | /admin/dashboard | Tes akses admin |

## 5. File Penting

- app/__init__.py: application factory.
- app/config.py: konfigurasi Flask.
- app/database.py: koneksi PostgreSQL.
- app/utils.py: decorator login_required dan admin_required.
- app/routes/auth.py: autentikasi.
- app/routes/admin.py: endpoint admin.
- database/schema.sql: struktur database.
- database/create_admin.py: membuat akun admin.
- database/reset_admin_password.py: mengatur ulang password admin.
- test_api.http: pengujian API.
- requirements.txt: dependensi.

## 6. Pekerjaan yang Belum Selesai

### Prioritas 1: Persiapan Kolaborasi
- Merapikan dokumentasi.
- Memastikan file sensitif tidak masuk GitHub.
- Memastikan repository dapat di-clone.
- Membuat commit dan push fondasi proyek.
- Membuat panduan setup untuk anggota tim.

### Prioritas 2: Integrasi Cloud Storage
- Mengambil konfigurasi S3-compatible dari Neon Object Storage.
- Mengatur credential melalui .env.
- Membuat fungsi upload dan pengambilan file.
- Menguji upload foto lapangan.
- Menguji upload bukti pembayaran.

### Prioritas 3: Modul Aplikasi
- CRUD data lapangan.
- Pengelolaan foto lapangan.
- Pengelolaan fasilitas dan tarif.
- Halaman daftar dan detail lapangan.
- Pemeriksaan ketersediaan jadwal.
- Proses reservasi.
- Pengunggahan bukti pembayaran.
- Verifikasi pembayaran oleh admin.
- Riwayat reservasi customer.

### Prioritas 4: Frontend
- Membuat halaman login dan registrasi.
- Membuat halaman utama customer.
- Membuat halaman daftar dan detail lapangan.
- Membuat halaman reservasi.
- Membuat dashboard admin.
- Menyesuaikan tampilan untuk desktop dan mobile.

## 7. Kondisi Pengembangan Saat Ini

Aplikasi sudah memiliki fondasi backend dan database.

Frontend lengkap belum dibuat.

Integrasi Neon Object Storage belum dilakukan.

CRUD lapangan dan reservasi belum diimplementasikan.

Jangan menganggap modul yang baru memiliki file Blueprint sebagai fitur yang sudah selesai.

## 8. Aturan Melanjutkan Pengerjaan

1. Periksa kode yang sudah tersedia sebelum mengubahnya.
2. Jangan menghapus fitur yang telah berjalan.
3. Jangan membuat ulang database tanpa alasan.
4. Jangan mengubah nama tabel atau kolom tanpa koordinasi.
5. Jangan menaruh password atau credential di dalam source code.
6. Gunakan koneksi database yang sudah tersedia.
7. Ikuti struktur folder yang sudah dibuat.
8. Kerjakan fitur secara bertahap.
9. Uji setiap perubahan sebelum melanjutkan.
10. Perbarui catatan ini setelah menyelesaikan modul.

## 9. Update Progres

Setiap anggota yang menyelesaikan pekerjaan perlu mencatat:

- Tanggal pengerjaan.
- Nama anggota.
- File yang dibuat atau diubah.
- Fitur yang diselesaikan.
- Hasil pengujian.
- Kendala yang belum selesai.

Dengan demikian, anggota lain dapat melanjutkan pekerjaan tanpa mengulang proses sebelumnya.
