
# CATATAN DESAIN SPORTRESERVE

## 1. Gambaran Umum

SportReserve adalah aplikasi web untuk melakukan reservasi lapangan futsal secara online. Aplikasi ini dikembangkan sebagai proyek mata kuliah Komputasi Awan.

Sistem mempertemukan pelanggan yang ingin memesan lapangan dengan admin atau pengelola yang mengatur informasi lapangan, jadwal, dan reservasi.

SportReserve bukan website informasi statis. Sistem merupakan aplikasi web dengan frontend, backend, database, autentikasi, dan penyimpanan file.

## 2. Tujuan Sistem

1. Memudahkan pelanggan melihat informasi lapangan futsal.
2. Memudahkan pelanggan melihat ketersediaan jadwal.
3. Memungkinkan pelanggan melakukan reservasi secara online.
4. Mencegah bentrok jadwal reservasi.
5. Memudahkan admin mengelola lapangan dan reservasi.
6. Menggunakan layanan cloud untuk database dan penyimpanan file.

## 3. Target Pengguna

Sistem memiliki dua role:

### Customer
- Registrasi dan login.
- Melihat daftar lapangan.
- Melihat detail dan foto lapangan.
- Melihat fasilitas dan harga.
- Memeriksa ketersediaan jadwal.
- Melakukan reservasi.
- Mengunggah bukti pembayaran.
- Melihat riwayat reservasi.

### Admin
- Login sebagai pengelola.
- Mengelola data lapangan.
- Mengelola foto lapangan.
- Mengelola fasilitas dan harga.
- Melihat dan mengelola reservasi.
- Memverifikasi pembayaran.
- Mengelola informasi pembayaran QRIS.

## 4. Teknologi

| Komponen | Teknologi |
|---|---|
| Backend | Python Flask |
| Frontend | HTML, CSS, JavaScript |
| Template | Jinja2 |
| Database | Neon PostgreSQL |
| Database Driver | Psycopg |
| Object Storage | Neon Object Storage |
| Version Control | Git dan GitHub |

## 5. Arsitektur Sistem

Arsitektur yang digunakan adalah aplikasi web berbasis Flask.

Alur umum:

1. Pengguna mengakses aplikasi melalui browser.
2. Frontend menampilkan halaman menggunakan HTML, CSS, dan JavaScript.
3. Request dikirim ke backend Flask.
4. Backend memproses autentikasi, aturan bisnis, dan permintaan data.
5. Data utama disimpan atau dibaca melalui Neon PostgreSQL.
6. File gambar disimpan melalui Neon Object Storage.
7. Backend mengirimkan respons kepada frontend.

## 6. Struktur Backend

- app/routes/: endpoint dan alur request.
- app/models/: representasi dan pengolahan data.
- app/templates/: halaman frontend.
- app/static/: CSS, JavaScript, dan aset statis.
- app/config.py: konfigurasi aplikasi.
- app/database.py: koneksi PostgreSQL.
- app/utils.py: fungsi pendukung dan proteksi akses.
- database/: skema SQL dan script administrasi database.

## 7. Aturan Bisnis Utama

### Reservasi
- Customer memilih lapangan, tanggal, jam mulai, dan durasi.
- Sistem menghitung jam selesai dan total harga.
- Sistem menahan jadwal selama 10 menit ketika proses pemesanan berlangsung.
- Sistem harus mencegah dua reservasi aktif menggunakan lapangan dan waktu yang sama.
- Reservasi memerlukan persetujuan admin.

### Pembayaran
- Sistem menggunakan QRIS statis milik pengelola.
- QRIS ditampilkan kepada customer.
- Customer membayar melalui mobile banking atau e-wallet.
- Customer mengunggah bukti pembayaran.
- Admin memeriksa bukti pembayaran secara manual.
- Tidak menggunakan payment gateway otomatis atau webhook.

### Harga
- Harga dapat berbeda berdasarkan lapangan, hari, dan rentang waktu.
- Harga yang berlaku ketika reservasi dibuat harus disimpan sebagai snapshot pada data reservasi.

### Foto dan File
- Foto lapangan disimpan di Neon Object Storage.
- Bukti pembayaran disimpan di Neon Object Storage.
- Database hanya menyimpan object key dan metadata file, bukan isi file gambar.

### Pembatalan
Aturan pembatalan masih perlu difinalisasi sebelum implementasi fitur. Jangan membuat kebijakan baru tanpa persetujuan tim.

## 8. Database

Database menggunakan PostgreSQL dengan 12 tabel:

1. users
2. lapangan
3. lapangan_foto
4. fasilitas
5. lapangan_fasilitas
6. jam_operasional
7. tarif_lapangan
8. reservasi
9. pembayaran
10. reservasi_log
11. pembayaran_log
12. pengaturan_pembayaran

Detail struktur dan relasi mengacu pada:

database/schema.sql

Jangan membuat ulang tabel atau mengubah relasi tanpa memeriksa skema yang sudah tersedia.

## 9. Object Storage

Bucket Neon Object Storage:

sportreserve-images

Status akses bucket: Private.

Prefix object key yang direncanakan:

- fields/: foto lapangan.
- profiles/: foto profil jika diperlukan.
- payment-qr/: gambar QRIS pengelola.
- payment-proofs/: bukti pembayaran customer.

Integrasi backend dengan Object Storage masih perlu dikerjakan.

## 10. Batasan Scope

Fokus pengembangan adalah sistem reservasi lapangan futsal.

Hindari penambahan fitur yang tidak berhubungan langsung dengan kebutuhan utama, seperti:
- Marketplace banyak penyedia lapangan.
- Payment gateway otomatis.
- Sistem chat real-time.
- Fitur sosial media.
- Fitur lain di luar kebutuhan MVP.

Setiap penambahan fitur harus memiliki alasan yang jelas dan disepakati tim.
