# Implementasi SLA Provider — 29 Oktober 2026

Plugin internal **SLA Provider 1.0.0** dipasang pada GLPI 11.0.8 laptop dan Development Server. Source: [glpi-plugins/providersla](../glpi-plugins/providersla/README.md).

## Perilaku yang tersedia

- Tab **SLA Provider** pada tiket untuk teknisi yang memiliki hak Update tiket dan akses ke entity/tiket terkait.
- Pengalihan manual dengan nama provider atau Supplier, circuit/layanan, timestamp pengiriman laporan, bukti diagnosis/pengiriman, nomor tiket opsional, dan target jam opsional.
- Awal hitung dari pengalihan Helpdesk, tanpa menunggu penerimaan atau nomor tiket ISP. Perubahan nomor tiket tidak menggeser waktu mulai.
- Tiket dibuat Pending saat pengalihan untuk menjeda TTR native. Timer provider sendiri tetap berjalan 24×7, menggunakan timestamp Asia/Jakarta yang disimpan sebagai Unix seconds.
- Pencatatan pemulihan yang diverifikasi menghentikan durasi provider dan melanjutkan penanganan Helpdesk. Penyelesaian GLPI tetap dilakukan terpisah.
- Pencegahan episode aktif ganda, overlap, tanggal sebelum tiket dibuat, dan timestamp masa depan. Pembatalan memerlukan alasan dan mempertahankan audit before/after.
- Laporan melalui **Tools → SLA Provider**, rekap status SLA, serta CSV. Batas 500 episode ditandai jelas di tampilan dan file.

Target jam global belum ditentukan. Target kosong ditandai **Tanpa Target**, bukan memenuhi/melanggar. Belum ada Supplier di kedua instance saat pemeriksaan awal, sehingga nama provider dapat dicatat manual tanpa membuat data provider fiktif.

Ringkasan non-provider adalah selisih elapsed siklus tiket dengan interval provider, bukan jam kerja aktif Helpdesk. Downtime dan respons pertama belum diklaim sebagai hasil pengukuran. Jika timestamp dicatat terlambat, laporan plugin mengikuti waktu kejadian; histori SLA native tidak ditulis ulang. Integrasi Zabbix dan restitusi tetap di luar tahap ini.

## Instalasi dan backup

- Source plugin aktif: `/var/www/glpi/plugins/providersla` pada kedua instance.
- Compose laptop ditambahkan mount source plugin untuk pembuatan ulang container berikutnya; container aktif dipasang melalui penyalinan source.
- Kedua instance sebelumnya memiliki mode eksekusi plugin `suspended_by_update`. Setelah kompatibilitas diperiksa, eksekusi di-resume agar plugin dapat diinstal dan diaktifkan. Server mengembalikan Data Injection 2.15.4 yang sebelumnya berstatus Enabled; GDrive 3.0.0 tetap Not Installed. Tidak ada proses impor/sinkronisasi aset yang dijalankan.
- Backup database server sebelum instalasi: `/home/glpiusr/wa-glpi/backups/20261029-030339-providersla/glpi-before.sql` (timestamp nama direktori UTC; file mode 600). Status plugin sebelumnya dicatat pada `plugin-state.json` di direktori yang sama.
- Tidak ada perubahan environment middleware, mapping WhatsApp, cursor, ataupun state percakapan. Tidak ada tiket historis yang dialihkan secara otomatis.
- Instalasi menambahkan dua tabel plugin. Uninstall/deaktivasi mempertahankan histori. Selesaikan/batalkan episode aktif sebelum deaktivasi agar tiket tidak tertinggal Pending.

## Validasi yang selesai

- 19 pemeriksaan clock: konversi Jakarta/UTC, tanggal invalid, target pecahan/kosong/invalid, batas deadline, overdue, void, durasi melewati 24 jam, dan formula CSV.
- Tes integrasi lokal dengan rollback seluruh fixture: Pending/resume, Supplier native, target opsional, pengalihan ganda/overlap, tanggal masa depan, referensi tidak mereset waktu, audit, pembatalan, rendering form dan pemeriksaan hak akses.
- HTTP terautentikasi lokal dan server: laporan 200, CSV 200, POST tanpa CSRF 403. Pengujian server memakai HTTPS dengan sertifikat diverifikasi dan resolusi vhost lokal.
- Fixture integrasi lokal seluruhnya di-rollback; nol episode dan nol tiket fixture tersisa. Server tidak dibuatkan tiket/episode uji dan tidak dikirimkan pesan WhatsApp/provider.
- PHP lint dan validasi Compose berhasil. Tampilan tidak diuji melalui screenshot browser karena akses Computer Use belum tersedia; HTML form dan halaman diperiksa melalui render/HTTP.

Panduan operasi dan batasan lengkap terdapat di README plugin.
