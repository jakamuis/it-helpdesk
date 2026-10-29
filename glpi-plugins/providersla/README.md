# SLA Provider 1.0.0 — GLPI 11.0.8

Plugin internal untuk pencatatan manual pengalihan Helpdesk ke provider. Tidak memerlukan integrasi Zabbix dan tidak mengirim laporan/pesan ke provider.

## Pemakaian

1. Buka tiket dengan profil teknisi yang mempunyai hak Update tiket, lalu pilih tab **SLA Provider**.
2. Periksa gangguan dan kirim laporan ke provider melalui kanal yang biasa dipakai.
3. Isi **Alihkan ke provider**: Supplier atau nama provider, circuit/layanan, waktu laporan dikirim (Asia/Jakarta), diagnosis dan bukti pengiriman. Nomor tiket provider boleh menyusul. Target jam opsional; kosong berarti **Tanpa Target**.
4. Klik **Catat pengalihan & mulai SLA provider**. Awal hitung adalah timestamp pengalihan, bukan pembuatan tiket atau balasan ISP. Tiket menjadi Pending dan timer provider tetap berjalan 24×7.
5. Setelah koneksi pulih dan hasilnya diverifikasi, isi **Catat layanan pulih** beserta waktu dan bukti uji. Provider berhenti dihitung pada waktu pulih; tiket dilanjutkan untuk Helpdesk. Penyelesaian/Solved dilakukan melalui proses GLPI biasa.
6. Buka **Tools → SLA Provider**, atau tombol **Laporan SLA Provider** di tab tiket, untuk rekap serta ekspor CSV.

Jika Supplier dipilih, plugin menambahkan Supplier sebagai assigned actor tanpa menghapus grup/teknisi Helpdesk. Jika nama diisi manual, provider tercatat di episode tanpa membuat Supplier baru. Belum ada Supplier pada pemeriksaan awal laptop/server; nama provider dapat dicatat manual.

## Hitungan dan batasan

- `Durasi provider = pulih − pengalihan`. Untuk episode berjalan gunakan snapshot waktu laporan. Semua timestamp disimpan sebagai Unix seconds dan ditampilkan Asia/Jakarta; hitungan 24×7 tanpa jeda Pending.
- `Deadline = pengalihan + target jam`. Tepat deadline masih memenuhi; target kosong tidak dianggap memenuhi atau melanggar.
- Ringkasan tab menampilkan provider, siklus tiket sampai sekarang/Solved, dan selisih **waktu non-provider**. Selisih mencakup antrean dan waktu tunggu lain; bukan jam kerja aktif Helpdesk, bukan respons pertama, dan bukan downtime layanan. Downtime belum dihitung karena awal gangguan belum tersedia dalam tahap ini.
- Status Pending menjeda TTR native GLPI, termasuk SLA/OLA yang terpasang. Timer provider berada pada tabel plugin terpisah sehingga tidak ikut dijeda. SLA layanan kepada pengguna harus dibaca terpisah bila diwajibkan tetap berjalan secara end-to-end.
- Native Pending dihitung sejak perubahan status sebenarnya. Bila pengalihan/pemulihan dicatat terlambat, laporan plugin memakai timestamp kejadian, tetapi plugin tidak menulis ulang histori SLA native GLPI.
- Saat pemulihan, plugin hanya melanjutkan Pending yang dibuat episode tersebut; perubahan status di luar tab dipertahankan. Perubahan workflow di luar tab saat provider masih aktif memunculkan peringatan. Pending karena alasan lain harus dilanjutkan dahulu sebelum pengalihan baru.
- Tidak ada target jam global yang dikarang. Target saat pengalihan disimpan sebagai snapshot dan tidak diubah saat nomor referensi ditambahkan.
- Satu episode aktif per tiket; validasi server dan unique index mencegah pengalihan ganda, waktu masa depan, tanggal sebelum tiket, dan episode tumpang tindih. Pengalihan ulang tidak mereset episode aktif.
- Pembatalan memerlukan alasan, mempertahankan bukti dan audit before/after, serta mengecualikan episode dari total. Koreksi timestamp dilakukan dengan pembatalan lalu pencatatan ulang pada tiket terbuka. Tidak tersedia penghapusan histori melalui UI.
- Hak akses mengikuti native ticket read/update dan entity GLPI, hanya untuk interface central dengan hak Update tiket. Self-service tidak dapat membaca catatan provider. Mutasi hanya POST dengan CSRF native GLPI 11.
- Laporan memakai cohort tanggal pengalihan; setiap episode dihitung penuh sampai pulih/snapshot. Batas 500 episode berlaku pada tampilan dan CSV serta ditampilkan jelas; persempit tanggal untuk hasil lengkap. CSV menetralkan nilai yang dapat menjadi formula spreadsheet.
- Persentase memenuhi hanya memakai episode selesai yang memiliki target. Episode berjalan, tanpa target dan dibatalkan ditampilkan terpisah.
- Tidak menghitung restitusi, tidak mengubah target SLA/OLA yang sudah ada, tidak membuat severity atau provider fiktif, dan tidak otomatis menutup tiket.

## Instalasi / rollback

Simpan folder `providersla` ke direktori `plugins` GLPI, lalu jalankan sebagai user web server:

```sh
php bin/console plugin:install providersla --username=<admin-glpi> --no-interaction
php bin/console plugin:activate providersla --no-interaction
```

Root Compose laptop sudah memuat bind mount plugin untuk pembuatan ulang container berikutnya. Container GLPI lokal yang sedang berjalan dipasang dengan menyalin source plugin ke lokasi aktif. Server tetap memakai struktur instalasi GLPI yang sudah ada.

Instalasi menambahkan hanya tabel `glpi_plugin_providersla_episodes` dan `glpi_plugin_providersla_events`; tidak memigrasikan tiket lama. Backup database dan direktori plugin sebelum pemasangan. Untuk rollback gunakan `plugin:deactivate providersla`; tabel bukti sengaja dipertahankan, termasuk saat uninstall. Jika ada episode aktif, catat pemulihan/pembatalannya sebelum deaktivasi agar tiket tidak tertinggal Pending.

## Verifikasi lokal

```sh
php plugins/providersla/tests/clock.php
PROVIDERSLA_TEST_LOCAL=1 php plugins/providersla/tests/integration.php
```

Tes integrasi **hanya lokal** memakai user fixture `glpi`, membuat tiket dalam transaksi luar, dan melakukan rollback seluruh fixture. Tes ini tidak dijalankan di server. Pengiriman notifikasi dimatikan pada mutasi fixture; tidak ada pesan atau tiket provider eksternal.

Source memakai lisensi GPL-3.0-or-later, sesuai lisensi GLPI.
