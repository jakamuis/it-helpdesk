# Layanan TI — hasil implementasi cloud dan panduan server

Baseline: `main` pada `60c7765463a66006e0f1d47b82960a4edb9daf97`. Implementasi disiapkan pada branch `feature/layanan-ti-cloud`. Tidak melakukan deployment, perubahan data bisnis, atau pengiriman WhatsApp pada server.

## Cakupan

Plugin tambahan `layananit` 0.1.0 menyediakan navigasi, dashboard, antrean Incident/Request, Asset Computer/Monitor/Printer, User, dan Developer. Fitur native GLPI dipakai kembali untuk pencarian, pagination, detail dan aksi Ticket/Asset/User. Menu Incident memulai pencarian dengan tipe Incident; native filter tetap dapat digunakan petugas sesuai permission. Request native GLPI tidak dipakai untuk pengajuan layanan ini.

Request IT diperbarui ke 0.3.0: IT Manager mengatur PIC; IT hanya mendapat akses kerja pada Request yang ditugaskan kepadanya. Atasan/direktur tetap mengikuti approval sebelumnya. Admin konfigurasi memiliki kontrol administratif, tetapi tidak menyetujui atas nama approver bisnis. Semua catatan Request saat ini masih dapat dibaca aktor yang berhak; catatan internal terpisah belum ditambahkan.

Portal self-service memusatkan navigasi pada pengajuan, bukan dashboard pencatatan pengguna baru. Revisi dan permintaan kelengkapan masih dilakukan lewat form dengan login. Cabang/lokasi diisi pengguna. Data historis, lampiran, nomor referensi dan workflow tetap dipertahankan.

Perhitungan KPI/SLA/target otomatis/beban teknisi ditunda. Tidak ada angka demo yang dipakai sebagai metrik produksi. Mekanisme target tanggal yang sudah ada tetap berlaku saat IT memulai pekerjaan.

## Role dan konfigurasi

Di **Request IT → Pengaturan**, dalam entity yang sesuai:

1. Pertahankan pemetaan pemohon → atasan → direktur yang sudah ada.
2. Tambahkan IT Manager. Admin konfigurasi otomatis memiliki hak manajerial.
3. Tambahkan anggota IT yang boleh dipilih sebagai PIC.
4. Bila WA Request akan dipakai, verifikasi kepemilikan nomor pemohon lalu simpan nomor tujuan dengan format internasional `628xxxxxxxxxx@c.us`. Pengguna tidak dapat menentukan tujuan pesan secara bebas.

Request yang sudah memiliki PIC mempertahankan PIC tersebut; Request tanpa PIC perlu ditugaskan Manager sebelum mulai dikerjakan. Pergantian PIC wajib alasan dan dicatat di event. Form lama ditolak bila versinya sudah berubah.

Role Request ini **tidak otomatis mengubah profil GLPI native**. Untuk Incident, atur profil GLPI yang ada: Manager mempunyai hak assign, IT mempunyai hak penanganan sesuai tugasnya, dan Admin mempunyai kontrol administratif. Verifikasi aturan read/update/assignment pada instance sebelum penggunaan. Jangan menyamakan hak `config` dengan approval bisnis. UI tidak meningkatkan privilege atau membuat akun/profil secara otomatis.

## Lingkungan cloud yang dapat diulang

Gunakan `dev/cloud/compose.yml`, bukan Compose root untuk server:

```sh
export CLOUD_DB_PASSWORD='<password-khusus-fixture-cloud>'
docker compose -f dev/cloud/compose.yml up -d
docker compose -f dev/cloud/compose.yml exec -u www-data glpi php bin/console plugin:install itrequest --username=glpi -n
docker compose -f dev/cloud/compose.yml exec -u www-data glpi php bin/console plugin:activate itrequest -n
docker compose -f dev/cloud/compose.yml exec -u www-data glpi php bin/console plugin:install layananit --username=glpi -n
docker compose -f dev/cloud/compose.yml exec -u www-data glpi php bin/console plugin:activate layananit -n
```

Tunggu instalasi database selesai pada log container sebelum memasang plugin. Image GLPI dipatok `11.0.8`, database/volume baru terpisah, dan port dibatasi ke loopback. Jangan mengimpor kredensial atau database server. Akun bawaan fixture harus diganti sebelum instance dibuka ke jaringan lain. Integrasi WA Request nonaktif tanpa konfigurasi eksplisit.

## Update server setelah review

1. Tinjau perubahan branch/PR dan pastikan GLPI runtime 11.0.8. Jangan menarik image `latest` untuk update UI ini.
2. Backup database GLPI, folder plugin lama, dan `files/_plugins/itrequest` sebagai satu set. Backup `.env`, state SQLite, mapping Ticket dan cursor middleware secara privat bila middleware ikut diperbarui.
3. Ambil commit yang telah disetujui di checkout server. Salin folder `glpi-plugins/itrequest` dan `glpi-plugins/layananit` ke direktori `plugins` GLPI yang benar. Pertahankan owner web server dan permission direktori/file; jangan menyalin konfigurasi cloud.
4. Jalankan update plugin melalui console pada instalasi GLPI server:

```sh
cd /var/www/glpi
sudo -u www-data php bin/console plugin:install itrequest --username='<akun-admin-glpi>' --force --no-interaction
sudo -u www-data php bin/console plugin:activate itrequest --no-interaction
sudo -u www-data php bin/console plugin:install layananit --username='<akun-admin-glpi>' --no-interaction
sudo -u www-data php bin/console plugin:activate layananit --no-interaction
```

Periksa `plugin:install --help` pada instance bila opsi berbeda. Jangan menjalankan root Compose laptop di server. Login ulang untuk memuat menu baru.

Migrasi idempoten menambahkan tabel `glpi_plugin_itrequest_managers` dan `glpi_plugin_itrequest_contacts`. Tabel Request, event, attachment dan pemetaan lama dipertahankan. Plugin UI tidak menambahkan tabel. Perubahan ini tidak mengubah inventaris, sinkronisasi Datasheet, SLA Provider, atau target SLA native.

5. Atur Manager/IT dan uji role pada entity target. Lakukan smoke check baca terlebih dahulu; tes fixture hanya untuk cloud/lokal.
6. Jika memperbarui middleware, ikut salin `request_notifier.py` bersama `app.py` ke lokasi service yang sudah ada. Modul tersebut tetap nonaktif sampai konfigurasi WA ditentukan; alur Ticket lama dipertahankan. Restart service hanya pada jendela update yang dipilih operator.

## Alias portal `/request`

Route siap pakai setelah plugin aktif: `/plugins/layananit/front/request.php`.

Untuk aplikasi di root domain, operator dapat menambahkan redirect khusus pada virtual host yang sudah ada:

```apache
RedirectMatch 302 ^/request/?$ /plugins/layananit/front/request.php
```

Contoh Nginx:

```nginx
location = /request { return 302 /plugins/layananit/front/request.php; }
location = /request/ { return 302 /plugins/layananit/front/request.php; }
```

Jika GLPI dipasang di subpath, sesuaikan prefix tujuan. Verifikasi konfigurasi web server sebelum reload. Alias belum dipasang pada server. Akses tetap meminta login; redirect tidak membuka pengajuan anonim.

## WA Request — opt-in

Ticket sudah memiliki middleware WA; Request membutuhkan feed khusus karena datanya bukan Ticket. Feed baru hanya mengeluarkan nomor referensi, jenis event dan nomor tujuan yang diverifikasi admin. Payload, lampiran, catatan, NIK, dan detail approval tidak dikirim melalui feed.

Konfigurasi **proses PHP web server**:

- `ITREQUEST_BRIDGE_TOKEN`: token acak minimal 32 karakter, disimpan di konfigurasi privat; jangan commit.
- `ITREQUEST_BRIDGE_ENTITY`: ID entity tunggal yang boleh diambil bridge.

Konfigurasi **middleware** di `.env` server yang sudah ada:

- `ITREQUEST_FEED_URL=https://<domain>/plugins/itrequest/front/wa-feed.php`
- `ITREQUEST_BRIDGE_TOKEN`: nilai yang sama dengan konfigurasi PHP.

Gunakan HTTPS dengan sertifikat valid. Pastikan Authorization diteruskan proxy/web server ke PHP. Feed hanya menerima GET, mencocokkan bearer token, membatasi entity di query, dan menolak akses bila token/entity tidak dikonfigurasi. Pengecualian firewall GLPI hanya berlaku untuk route machine feed tersebut; autentikasinya diperiksa oleh token. Halaman portal tetap memakai login GLPI.

Aktivasi pertama melewati event historis tanpa mengirim pesan. Selanjutnya event submit/approval/revisi/penolakan/assignment/start/kelengkapan/selesai/pembatalan menghasilkan pesan status ringkas. Nomor kontak harus sudah dikonfigurasi sebelum event berikutnya. Setiap penyimpanan kontak mencatat batas event saat verifikasi, sehingga kontak yang baru dipetakan tidak menerima riwayat lama. Pesan tidak mengandung tautan login otomatis atau token akses Request.

Cursor tersimpan di SQLite middleware dan diperbarui setelah tiap pengiriman berhasil. Error di feed tidak memblokir loop Incident. Delivery WAHA dan commit SQLite tidak atomik: crash setelah pesan terkirim tetapi sebelum commit dapat menyebabkan satu pesan berulang, seperti batas pengiriman Ticket yang sudah ada. Tidak ada klaim exactly-once. Konfigurasi ini belum diaktifkan atau diuji dengan penerima WA nyata.

## Verifikasi lokal/cloud

Dijalankan pada GLPI 11.0.8 dengan database fixture terpisah:

- Install dan aktivasi kedua plugin.
- Lint PHP untuk seluruh plugin.
- Integrasi Request: approval Email/Office, revisi, assignment, akses, stale version, audit dan tidak membuat Ticket duplikat.
- Feed: pembatasan entity, kontak dan tidak mengeluarkan payload/catatan privat.
- HTTP: delapan halaman Layanan TI; penolakan anonim; CSRF; upload/download beserta integritas file.
- Middleware: 37 tes lulus, termasuk baseline feed, retry dan validasi penerima.
- Browser Chromium: desktop 1440px dan mobile 390px; tidak ada overflow horizontal pada halaman utama.

Perintah fixture (ganti nama container bila perlu):

```sh
docker exec -u www-data -e ITREQUEST_TEST_LOCAL=1 <container-glpi-lokal> php plugins/itrequest/tests/integration.php
docker exec -u www-data -e ITREQUEST_TEST_LOCAL=1 <container-glpi-lokal> php plugins/itrequest/tests/wa_feed.php
ITREQUEST_TEST_LOCAL=1 GLPI_TEST_CONTAINER=<container-glpi-lokal> python3 glpi-plugins/itrequest/tests/smoke_http.py
ITREQUEST_TEST_LOCAL=1 GLPI_TEST_CONTAINER=<container-glpi-lokal> python3 glpi-plugins/layananit/tests/smoke_http.py
python3 -m pytest wa-glpi/tests -q
```

Jangan jalankan tes fixture pada server. Verifikasi WA nyata, profil produksi, dan alias domain masih menjadi langkah pemasangan operator.

## Rollback

Nonaktifkan bridge Request dengan mengosongkan `ITREQUEST_FEED_URL` pada middleware dan restart service sesuai prosedur setempat. Deaktivasi `layananit` mengembalikan akses kerja melalui navigasi GLPI asli; halaman native tidak dimodifikasi. Bila mengembalikan source `itrequest` 0.2.0, pahami bahwa aturan akses kembali ke pola staff lama, bukan assignment-only. Untuk rollback menyeluruh, pulihkan pasangan backup database dan lampiran sesuai jendela perubahan. Uninstall plugin sengaja mempertahankan data; jangan menghapus tabel/berkas sebagai langkah rollback otomatis.

## Tampilan untuk review

Screenshot memakai database fixture kosong; bukan data produksi. Kolom KPI sengaja belum berisi hasil perhitungan.

[Desktop](screenshots/layanan-ti-desktop.png) · [Mobile](screenshots/layanan-ti-mobile.png)

## Pembaruan lokal 15 November 2026

- Branding sidebar menggunakan logo resmi Samator dan IT Helpdesk; Computer, Monitor, Printer berada dalam submenu Asset.
- Dashboard menghitung Incident dan inventaris dari database melalui hak akses GLPI.
- Reporting Tiket menyediakan filter tanggal pembukaan, lokasi, teknisi, status ringkas, tren bulanan, waktu penyelesaian kalender, pagination, dan CSV. Request IT plugin tidak termasuk laporan Ticket native.
- Konfigurasi `dev/local/glpi-apache.conf` mengarahkan root ke Layanan TI dan `/front` ke GLPI native. Query login tetap diteruskan. Konfigurasi ini khusus container lokal; jangan mengganti virtual host server secara langsung.
- Pada server, pull branch `feature/layanan-ti-cloud` di checkout setelah memeriksa perubahan lokal. Pull source tidak otomatis memperbarui plugin di `/var/www/glpi/plugins` atau middleware runtime. Ikuti backup dan instalasi plugin di atas bila melakukan deployment runtime.
- Verifikasi: 48 tes middleware lulus; smoke HTTP lokal mencakup sembilan halaman, CSV, filter teknisi, dan validasi tanggal.
