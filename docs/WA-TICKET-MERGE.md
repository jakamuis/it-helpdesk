# Merge tiket GLPI dan penerima WhatsApp

Middleware mendeteksi hasil merge manual GLPI 11: tiket sumber berada di Trash (`is_deleted=1`) dan memiliki satu relasi `Ticket_Ticket` bertipe `SON_OF` (`link=3`) menuju tiket tujuan. Relasi terkait/duplikat tanpa merge tidak mengalihkan penerima. Jangan purge tiket asal sebelum middleware memproses merge. Merge tanpa relasi yang tersimpan tidak dapat dideteksi; periksa opsi relasi saat menggabungkan.

Pada polling berikutnya sebelum membaca pesan WA, middleware:

- Menelusuri rantai merge sampai tiket tujuan yang tidak dihapus; menolak siklus dan tujuan ambigu.
- Mencatat transfer di SQLite agar pemindahan yang terputus dapat dilanjutkan.
- Menggabungkan penerima tanpa menimpa pelapor lain, memindahkan referensi percakapan ke tiket utama, dan menghapus mapping tiket sumber.
- Mengirim pemberitahuan nomor tiket pengganti kepada pelapor asal, dengan retry persisten.
- Mengirim follow-up publik dan perubahan status Solved tiket utama kepada seluruh penerima terkait. Follow-up internal dan pesan WA masuk tetap tidak diteruskan kembali.

Format `ticket_mapping.json` tetap menerima string lama; beberapa penerima memakai array string. Jalankan satu instance penulis middleware seperti deployment saat ini. Mapping, SQLite, dan cursor harus tetap disimpan di disk persisten. Jangan jalankan versi middleware lama pada mapping array.

Pengiriman menggunakan checkpoint setelah WAHA menerima request. Timeout setelah WAHA menerima pesan masih dapat menyebabkan pesan terkirim ulang; ini bukan jaminan exactly-once.

## Penerapan

Perubahan diterapkan ke server `192.168.1.189` pada 29 Oktober 2026 sekitar 16:07 WIB setelah akses SSH tersedia. Backup privat source, environment, mapping, cursor, dan snapshot SQLite berada di `/home/glpiusr/wa-glpi/backups/ticket-merge-20261029-160655/`.

Verifikasi: 38 tes lokal lulus; hash ketiga file runtime sesuai source lokal; `wa-glpi.service` active/running dengan `NRestarts=0`; SQLite quick_check `ok`; tabel journal merge terbentuk; sesi WAHA `WORKING`; tidak ada Traceback/error merge dalam pemeriksaan log setelah restart. Endpoint tiket dan relasi Ticket_Ticket berhasil dibaca menggunakan environment server. Belum ada pengujian merge tiket nyata.

Untuk penerapan ulang: hentikan service middleware yang aktif, backup privat `.env`, mapping, SQLite (beserta WAL/SHM jika ada), cursor follow-up, dan source lama. Pasang `app.py`, `status_notifier.py`, serta modul baru `ticket_merge.py` bersama dalam `/home/glpiusr/wa-glpi/`, tanpa mengganti environment/state. Jalankan kembali unit systemd yang sama dan periksa log merge/retry. Tidak perlu menjalankan Compose laptop pada server.

Verifikasi fungsional berikutnya memakai merge yang disetujui helpdesk: pastikan mapping sumber berpindah, seluruh pelapor tetap terdaftar, nomor tiket pengganti diterima user, balasan user masuk ke tujuan, dan notifikasi follow-up/Solved tetap tersampaikan. Belum ada merge tiket nyata atau pesan WA uji yang dilakukan dalam implementasi ini.

Untuk rollback source, hentikan service dan pertahankan backup state pasca perubahan. Versi lama tidak mendukung penerima array; jangan meratakan array dengan membuang pelapor. Gunakan source yang mendukung array atau lakukan pemulihan terkontrol dari backup dengan rekonsiliasi laporan setelah backup.
