# Layanan TI 0.1.0 — GLPI 11.0.8

Antarmuka tambahan melalui plugin, tanpa patch core. Buka **Tools → Layanan TI** atau `/plugins/layananit/front/index.php` setelah instalasi dan aktivasi.

- Sidebar navy/teal, dashboard responsif, antrean Incident dan Request yang terpisah.
- Incident, Computer, Monitor, Printer, User memakai native Search GLPI, beserta filter, pagination, permission dan entity-nya. Detail dan operasi inventaris tetap menggunakan halaman GLPI yang tersedia.
- Antrean Incident ringkas menggunakan native Search untuk delapan item terbaru; Request memakai pemeriksaan akses plugin pada setiap baris.
- Request IT tetap objek plugin, tidak dikonversi menjadi Ticket dan tidak menggandakan approval.
- Developer hanya untuk admin konfigurasi. Kontrol akun, profil dan entity di header asli GLPI dipertahankan.
- Route portal plugin: `/plugins/layananit/front/request.php` mengharuskan login dan mengarah ke form Request yang tersedia. Alias `/request` memerlukan konfigurasi web server terpisah; tidak dipasang otomatis.
- Angka KPI, rumus SLA dan beban teknisi sengaja belum dihitung. Tanda `—` bukan nilai nol atau data operasional.
- Request IT harus di-update ke 0.3.0 sebelum memasang antarmuka ini. GLPI 12 belum didukung.

Lihat [panduan pemasangan dan rollback](../../docs/LAYANAN-TI-CLOUD.md) untuk role, migrasi, notifikasi WA opsional, lingkungan cloud dan verifikasi.
