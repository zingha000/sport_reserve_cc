# PANDUAN TIM DAN AI SPORTRESERVE

## 1. Informasi Tim

Proyek SportReserve dikerjakan secara berkelompok.

Nama anggota yang telah disebutkan:

1. Acep
2. Edo
3. Faldy
4. Asep
5. Yosafat
6. Zeni

## 2. Rencana Pembagian Pekerjaan

Pembagian berikut masih bersifat sementara dan perlu disepakati bersama.

### Pengembangan Backend

- Edo: direncanakan membantu pengembangan backend.
- Asep: direncanakan membantu pengembangan backend.

### UI dan Penyempurnaan

- Acep: membantu penyempurnaan UI, tampilan, dan integrasi frontend dengan backend.
- Acep juga membantu pengujian dan perbaikan bagian yang diperlukan.

### Anggota Lain

- Faldy.
- Yosafat.
- Zeni.

Tugas spesifik ketiga anggota tersebut belum ditentukan. Pembagian dapat disesuaikan berdasarkan kesepakatan kelompok.

## 3. Alur Kolaborasi

1. Semua anggota menggunakan repository GitHub yang sama.
2. Setiap anggota melakukan clone repository.
3. Setiap anggota membuat branch untuk pekerjaan masing-masing.
4. Pekerjaan diuji secara lokal.
5. Perubahan di-push ke GitHub.
6. Perubahan digabungkan ke branch utama setelah diperiksa.
7. Dokumentasi diperbarui setiap kali ada perubahan penting.

Hindari mengerjakan perubahan besar langsung pada branch main.

## 4. Persiapan Setiap Anggota

Sebelum melakukan coding, setiap anggota perlu menyiapkan:

### Software

- Git.
- Python 3.14 atau versi kompatibel yang disepakati.
- Visual Studio Code.
- REST Client extension di VS Code.
- Browser.
- Akun GitHub.

### Persiapan Repository

Clone repository:

git clone https://github.com/zingha000/sport_reserve_cc.git

Masuk ke folder:

cd sport_reserve_cc

Buat virtual environment:

python -m venv venv

Aktifkan virtual environment di Windows:

.\venv\Scripts\Activate.ps1

Install dependensi:

pip install -r requirements.txt

Salin konfigurasi:

Copy-Item .env.example .env

Isi file .env menggunakan konfigurasi yang diberikan secara aman oleh pengelola proyek.

Jalankan aplikasi:

python run.py

Buka browser:

http://127.0.0.1:5000

## 5. Persiapan Akses Cloud

Setiap anggota yang membutuhkan akses database dan storage harus mendapatkan konfigurasi melalui pengelola proyek.

Informasi yang dibutuhkan:

- DATABASE_URL untuk Neon PostgreSQL.
- Konfigurasi Object Storage jika mengerjakan integrasi file.
- Hak akses repository GitHub.
- Akun pengujian customer dan admin sesuai kebutuhan.

Jangan mengirim credential melalui repository, source code, atau percakapan publik.

Jangan menjalankan ulang schema.sql pada database bersama tanpa koordinasi.

## 6. Aturan Git

Sebelum mulai mengerjakan:

git pull origin main

Buat branch:

git checkout -b feature/nama-fitur

Setelah pekerjaan selesai:

git add .
git commit -m "feat: deskripsi perubahan"
git push origin feature/nama-fitur

Ajukan Pull Request ke branch main untuk diperiksa sebelum digabungkan.

Gunakan nama branch yang jelas, misalnya:

- feature/field-management
- feature/reservation
- feature/payment
- feature/customer-ui
- feature/admin-dashboard

## 7. Aturan Pengembangan

- Ikuti struktur proyek yang sudah ada.
- Gunakan Flask sebagai backend utama.
- Gunakan Neon PostgreSQL untuk database.
- Gunakan Neon Object Storage untuk file.
- Gunakan session dan role yang sudah disiapkan.
- Pisahkan route, model, template, dan static file.
- Jangan membuat koneksi database baru di setiap route jika fungsi koneksi yang tersedia sudah cukup.
- Jangan menyimpan password dalam bentuk teks biasa.
- Jangan mengubah struktur database tanpa koordinasi.
- Jangan menambahkan teknologi atau layanan cloud baru tanpa persetujuan tim.

## 8. Instruksi untuk AI yang Melanjutkan Proyek

AI yang melanjutkan SportReserve harus membaca dokumen berikut terlebih dahulu:

1. docs/CATATAN_DESAIN.md
2. docs/CATATAN_PENGERJAAN.md
3. docs/PANDUAN_TIM_DAN_AI.md
4. README.md
5. database/schema.sql

Setelah membaca, AI harus memahami kondisi proyek sebelum memberikan kode atau instruksi.

### Konteks Wajib

SportReserve adalah aplikasi web Flask untuk reservasi lapangan futsal.

Proyek sudah memiliki:

- Struktur Flask.
- Koneksi Neon PostgreSQL.
- 12 tabel database.
- Sistem registrasi dan login.
- Password hashing.
- Session.
- Proteksi role customer dan admin.
- Bucket Neon Object Storage.

Jangan membuat ulang komponen yang sudah tersedia.

### Cara Bekerja

1. Periksa file yang berkaitan dengan tugas.
2. Jelaskan perubahan yang akan dilakukan.
3. Berikan kode sesuai struktur proyek.
4. Sebutkan lokasi file secara spesifik.
5. Berikan instruksi pengujian.
6. Tunggu hasil pengujian sebelum melanjutkan ke tahap berikutnya.
7. Perbarui dokumentasi setelah fitur selesai.

### Larangan

- Jangan mengubah framework tanpa persetujuan.
- Jangan mengganti PostgreSQL dengan database lain.
- Jangan membuat sistem pembayaran otomatis.
- Jangan mengubah aturan QRIS statis.
- Jangan menghapus tabel yang sudah ada.
- Jangan mengarang data atau hasil pengujian.
- Jangan membuat fitur di luar scope proyek.
- Jangan memberikan banyak perubahan besar sekaligus.
- Jangan menganggap kode berhasil sebelum diuji.

## 9. Standar Penyelesaian Fitur

Setiap fitur dianggap selesai jika:

- Kode sudah dibuat.
- Terhubung dengan database jika diperlukan.
- Tidak mengganggu fitur sebelumnya.
- Berhasil diuji.
- Memiliki penanganan error dasar.
- Dokumentasi diperbarui.
- Perubahan sudah di-push ke GitHub.

## 10. Prinsip Utama

SportReserve dikembangkan secara kolaboratif.

Prioritas utama adalah menyelesaikan kebutuhan inti aplikasi, menjaga konsistensi database, memastikan integrasi cloud berjalan, dan membuat sistem yang dapat dipahami serta dilanjutkan oleh semua anggota kelompok.

Tidak perlu menambah kompleksitas jika kebutuhan utama belum selesai.

SportReserve: aturan coding

Disepakati 22 Nov 2026. Berlaku setiap kali menambah atau mengubah fitur.

Fitur baru tidak menyentuh alur inti (reservasi, pembayaran, login). Kalau memang harus mengubahnya, jalankan ulang pengujian bagian itu.
Satu fitur satu branch git dan satu commit terpisah. Branch main selalu versi stabil; kalau fitur merusak sesuatu, kembali ke main.
Jangan ubah struktur database (tabel atau kolom baru) tanpa keperluan jelas; kalau perlu, coba dulu di branch Neon, bukan langsung di production.
Pengujian ulang cukup dua hal: python -m pytest -q -m "not concurrency" harus tetap lulus semua (terakhir 60 passed, 6 deselected), lalu uji manual fitur barunya sekali dari awal sampai akhir.
Kerjakan satu langkah per pesan.