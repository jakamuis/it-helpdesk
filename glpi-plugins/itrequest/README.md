# Request IT — GLPI 11.0.8

Plugin versi awal (0.2.0), terpisah dari Ticket. Tidak mengubah inti GLPI dan tidak mengirim email.

## Yang tersedia

- Form khusus Request Email (baru/reset/ubah/hapus) dan pemasangan Office 365; identitas pengguna terpisah dari pemohon, NIK, jabatan, bagian, cabang, dan perusahaan/beban biaya.
- Pemetaan pemohon → atasan → direktur per entity oleh admin konfigurasi. Direktur wajib untuk Email; Office tidak memerlukannya.
- Email: atasan mengetahui → direktur menyetujui → IT. Office 365: atasan menyetujui → IT. Kedua tahap mendukung revisi/penolakan dengan alasan. IT tidak dapat memulai sebelum persetujuan akhir.
- Antrean IT, PIC yang mengambil pekerjaan, target selesai, permintaan kelengkapan, hasil dan pembatalan.
- Perubahan kebutuhan sesudah approval mengembalikan request untuk revisi dan approval ulang. Selama diproses, pengembalian dilakukan IT.
- Alih approver tahap aktif (atasan atau direktur) oleh admin pada pengajuan menunggu approval, dengan alasan. Tidak memberi admin hak menyetujui atas nama atasan.
- Lampiran PDF/JPG/PNG maksimal 10 MB, disimpan dalam direktori files GLPI; unduhan memeriksa hak akses request.
- Riwayat pelaku, waktu, snapshot pengajuan, dan keputusan; transaksi serta pemeriksaan versi mencegah keputusan pada data lama.
- Menu central **Tools → Request IT** dan self-service **Plugins → Request IT**; akses langsung `/plugins/itrequest/front/index.php`.

## Instalasi lokal

Compose root sudah memiliki mount read-only plugin. Untuk container yang sudah berjalan tanpa mount, salin plugin lalu instal:

```sh
docker cp glpi-plugins/itrequest glpi_app:/var/www/glpi/plugins/itrequest
docker exec -u www-data glpi_app php /var/www/glpi/bin/console plugin:install itrequest --username=glpi --no-interaction
docker exec -u www-data glpi_app php /var/www/glpi/bin/console plugin:activate itrequest --no-interaction
```

Perintah di atas hanya untuk instance lokal. Gunakan prosedur deployment dan backup tersendiri untuk server. Mount berlaku setelah container dibuat ulang; tidak perlu membuat ulang seluruh stack.

Setelah login ulang agar menu diperbarui:

1. Admin membuka **Pengaturan** pada entity yang akan dipakai.
2. Petakan akun pemohon ke atasan dan direktur untuk Request Email; ketiganya harus aktif, berbeda, dan mempunyai profil dalam entity tersebut. Untuk Office, direktur boleh kosong.
3. Tambahkan akun anggota tim IT secara eksplisit. Hak update tiket tidak otomatis memberi hak mengelola request.
4. Pemohon membuat dan menyimpan draft; isi field wajib lalu klik **Kirim ke atasan**.
5. Atasan membuka **Persetujuan Saya**. Direktur juga membuka **Persetujuan Saya** setelah atasan mengetahui. Tim IT membuka **Antrean IT** setelah persetujuan akhir.

Pemohon, approver dan IT harus memilih entity yang sama saat membuka request. Versi awal tidak menggabungkan data child entity dalam satu daftar. Admin konfigurasi dapat melihat detail untuk dukungan administratif dalam entity aktif; akses tersebut tidak memberi hak approval bisnis atau hak penanganan IT.

## Pernyataan dan layanan

Pernyataan penggunaan untuk kepentingan perusahaan dan larangan forward email perusahaan ke email pribadi wajib disetujui sebelum pengiriman. Snapshot teks, akun dan waktu disimpan di event pengiriman. Field email menyesuaikan jenis layanan: alamat baru, alamat lama/baru, atau akun reset/hapus. Office memerlukan email pengguna, perangkat dan aplikasi tujuan. Tidak ada eksekusi otomatis ke sistem email atau Microsoft 365.

Pengajuan reset mengikuti Request Email sesuai formulir manual, melalui atasan dan direktur. IT memverifikasi identitas; password/OTP tidak dimasukkan ke form atau hasil pengerjaan.

Draft lama tetap tersimpan dan harus memilih salah satu layanan baru untuk pengiriman berikutnya. Pengajuan lama yang sudah dikirim mempertahankan alur yang berlaku saat dibuat; tidak dimigrasikan diam-diam menjadi pengajuan email.

## SMTP dan batas versi awal

Email belum diimplementasikan/diaktifkan. Form dan workflow sudah berjalan tanpa SMTP; pengguna memantau antrean di GLPI. Tahap berikutnya memerlukan pengaturan SMTP serta integrasi event, template, antrean/retry notifikasi GLPI. Plugin ini belum membuat antrean email yang akan dikirim otomatis ketika SMTP tersedia.

Belum tersedia: reminder, delegasi otomatis berdasarkan periode cuti, catatan internal terpisah, pengisian departemen/lokasi dari direktori, pencarian/filter lanjutan, integrasi procurement dan approval anggaran. Penggantian atasan sementara saat ini melalui alih approver yang tercatat. Departemen/lokasi dan referensi aset masih berupa teks; tidak mengubah inventaris.

Semua catatan yang diisi pada versi ini dapat dibaca pihak yang berhak melihat request. Pengajuan final tidak dibuka ulang. Draft dibatalkan sebagai arsip; tidak ada hapus permanen di UI. Batas `upload_max_filesize`/`post_max_size` PHP juga berlaku pada upload.

## Pengujian

```sh
docker exec glpi_app sh -c 'find /var/www/glpi/plugins/itrequest -name "*.php" -exec php -l {} \;'
docker exec -u www-data -e ITREQUEST_TEST_LOCAL=1 glpi_app php /var/www/glpi/plugins/itrequest/tests/integration.php
ITREQUEST_TEST_LOCAL=1 python3 glpi-plugins/itrequest/tests/smoke_http.py
```

Integration test hanya untuk lokal, memakai akun fixture yang tersedia, membuat seluruh data dalam transaksi luar dan melakukan rollback. Tidak mengirim notifikasi atau mengubah kredensial/profil akun. Mencakup revisi/approval/penanganan sampai selesai, pembatasan entity dan aktor, stale version, validasi, escaping, form CSRF, riwayat, dan verifikasi bahwa jumlah tiket tidak berubah.

HTTP test menguji halaman terautentikasi, POST tanpa/dengan CSRF, upload dan download lampiran beserta integritas file. Draft, berkas, dan session sementara dihapus dalam `finally`. Jangan jalankan pada server.

Uninstall mempertahankan tabel riwayat dan berkas. Backup database GLPI dan direktori `files/_plugins/itrequest` bersama-sama.
