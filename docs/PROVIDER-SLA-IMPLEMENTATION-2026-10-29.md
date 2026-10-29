# Implementasi SLA Provider — 29 Oktober 2026

Plugin internal **SLA Provider 1.2.0** dipasang pada GLPI 11.0.8 laptop dan Development Server. Source: [glpi-plugins/providersla](../glpi-plugins/providersla/README.md).

## Perilaku yang tersedia

- Versi 1.2.0 mengganti aksi **Assign ke Provider** menjadi **Eskalasi ke Vendor** untuk penggunaan umum, termasuk vendor perangkat/aplikasi/layanan. Form utama memuat **No. Incident dari Provider** dan **Nomor SID/Pelanggan**, keduanya opsional. Layanan/aset/lokasi tetap tersedia di detail tambahan.
- Nomor incident memakai `reference` yang sudah ada; SID memakai kolom baru `customer_sid` agar data circuit/layanan lama tidak diartikan ulang. Kedua nomor tampil di riwayat, ringkasan aktif, laporan dan CSV. Koreksi nomor di tab plugin tetap mempertahankan waktu mulai SLA dan audit perubahan.
- Tab **SLA Provider** pada tiket untuk teknisi yang memiliki hak Update tiket dan akses ke entity/tiket terkait.
- Versi 1.1.0 menyederhanakan operasi melalui **Assign ke Provider** pada bagian atas panel kanan detail tiket. Form ringkas berisi provider dan catatan pemeriksaan/bukti laporan; nomor tiket, circuit, dan waktu kejadian sebelumnya disembunyikan di detail tambahan. Form ringkas memakai **Tanpa Target**, sesuai pilihan pengguna.
- Waktu pengalihan/pemulihan ringkas otomatis memakai waktu simpan di server jika tidak diisi manual. Setelah simpan kembali ke detail tiket utama. Episode aktif menampilkan nama provider, waktu mulai, durasi saat halaman dimuat, serta **Catat layanan pulih** pada panel yang sama. Riwayat lengkap tetap tersedia di tab plugin.
- Panel memakai hook resmi `pre_itil_info_section`; dialog form diletakkan di luar form tiket GLPI. Tidak ada perubahan pada kode inti GLPI.
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
- Backup sebelum pembaruan panel kanan 1.1.0: `/home/glpiusr/wa-glpi/backups/20261029-041921-providersla/`, berisi `glpi-before.sql`, `plugin-state.json`, dan `providersla-before-1.1.0.tgz`. CLI mengonfirmasi versi 1.1.0 Enabled setelah pembaruan.
- Backup sebelum pembaruan 1.2.0: `/home/glpiusr/wa-glpi/backups/20261029-043158-providersla/`. Migrasi menambahkan hanya `customer_sid` dengan nilai awal kosong dan pemeriksaan field agar aman dijalankan ulang; nomor incident, circuit, durasi dan riwayat lama tetap dipertahankan.
- Tidak ada perubahan environment middleware, mapping WhatsApp, cursor, ataupun state percakapan. Tidak ada tiket historis yang dialihkan secara otomatis.
- Instalasi menambahkan dua tabel plugin. Uninstall/deaktivasi mempertahankan histori. Selesaikan/batalkan episode aktif sebelum deaktivasi agar tiket tidak tertinggal Pending.

## Validasi yang selesai

- 19 pemeriksaan clock: konversi Jakarta/UTC, tanggal invalid, target pecahan/kosong/invalid, batas deadline, overdue, void, durasi melewati 24 jam, dan formula CSV.
- Tes integrasi lokal dengan rollback seluruh fixture: Pending/resume, Supplier native, target opsional, pengalihan ganda/overlap, tanggal masa depan, referensi tidak mereset waktu, audit, pembatalan, rendering form dan pemeriksaan hak akses. Tambahan 1.1.0 meliputi panel aktif/tidak aktif, CSRF form ringkas, waktu simpan otomatis, pemulihan ringkas, dan pembatasan template preview/hak teknisi.
- HTTP terautentikasi lokal dan server: laporan 200, CSV 200, POST tanpa CSRF 403. Pengujian server memakai HTTPS dengan sertifikat diverifikasi dan resolusi vhost lokal.
- Fixture integrasi lokal seluruhnya di-rollback; nol episode dan nol tiket fixture tersisa. Server tidak dibuatkan tiket/episode uji dan tidak dikirimkan pesan WhatsApp/provider.
- Uji browser headless lokal 1.1.0 pada detail tiket GLPI asli: posisi panel kanan, dialog di luar form native, pengiriman POST assign dan pemulihan, Tanpa Target, serta kembali ke tab utama berhasil. Screenshot panel dan dialog diperiksa; tidak ada galat JavaScript. Fixture UI lokal dihapus setelah uji.
- HTTP HTTPS server 1.1.0: tab utama tiket merender panel kanan dan tombol, form ringkas memuat CSRF, aset JS/CSS 200, laporan/CSV 200, dan POST tanpa CSRF 403. Pemeriksaan tiket server hanya baca; tidak membuat episode atau mengalihkan tiket pengguna.
- PHP lint, pemeriksaan sintaks JavaScript, dan validasi Compose sebelumnya berhasil.
- Versi 1.2.0: integrasi lokal memeriksa penyimpanan incident/SID terpisah dan koreksi keduanya tanpa mengubah waktu mulai. Browser lokal memeriksa judul eskalasi, dua kolom langsung di form utama, simpan eskalasi vendor printer, keluaran incident/SID pada CSV, dan pemulihan; tanpa galat JavaScript. Fixture uji dihapus.
- HTTPS server 1.2.0 dengan profil akun `jaka`: panel tiket merender Eskalasi ke Vendor, form utama merender incident/SID/CSRF, kolom database SID tersedia, laporan/CSV/aset berhasil dimuat, dan POST tanpa CSRF tetap 403. Pemeriksaan server hanya baca; tidak membuat episode vendor.

Panduan operasi dan batasan lengkap terdapat di README plugin.
