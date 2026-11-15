# Zabbix → GLPI tickets

## Status penerapan — 29 Oktober 2026

- Zabbix `http://192.168.1.241/zabbix/`, versi API 6.0.11.
- GLPI `https://192.168.1.189/`; endpoint legacy `apirest.php` berhasil digunakan.
- Media type `GLPI Tickets - IT Helpdesk`, ID `34`, aktif dan berisi konfigurasi koneksi pada Zabbix.
- Media type lama `GLPi` ID `33` dipertahankan. Script lama membuat objek Problem; media type baru membuat Ticket.
- API client GLPI `Zabbix - IT Helpdesk`, ID `5`, aktif dengan batas IPv4 hanya `192.168.1.241`.
- Autentikasi menggunakan App-Token client tersebut dan User-Token akun GLPI yang diberikan pengguna. Token pengguna yang sudah ada tidak dirotasi. Akun layanan dengan hak terbatas dapat disiapkan kemudian.
- Action `GLPI Tickets - High and Disaster`, ID `7`, aktif. Filter trigger severity `>= High` (`conditiontype=4`, `operator=5`, `value=4`) mencakup High dan Disaster saja.
- Penerima teknis Zabbix adalah akun `admho` ID `7`, melalui media type `34`, tujuan `GLPI`, aktif sepanjang hari. Severity mask media `48` hanya mengizinkan High dan Disaster; tidak mengirim email atau WhatsApp.
- Operasi awal dijalankan satu kali pada step `1–1`. Recovery menggunakan `Notify all involved` untuk memperbarui tiket yang telah dibuat. Operasi update manual belum diaktifkan.
- Operasi ditunda selama masalah suppressed, mengikuti `pause_suppressed=1`.

## Bukti uji

Uji dijalankan melalui fasilitas `alert.send` server Zabbix, sehingga request GLPI berasal dari server Zabbix, bukan laptop.

1. Pengiriman PROBLEM uji berhasil membuat **Ticket #23**, judul `[TEST INTEGRASI] Zabbix ke GLPI - 29 Oktober 2026`.
2. Tiket diverifikasi melalui sesi GLPI: judul sesuai dan status New (`1`).
3. Pengiriman RECOVERY uji dengan ID tiket yang sama berhasil menambah catatan `UJI RECOVERY`.
4. Catatan diverifikasi pada tiket #23; status tetap New. Recovery tidak menyelesaikan tiket otomatis.

Setelah aktivasi action, konfigurasi dibaca ulang melalui API: status aktif, filter `>= High`, severity mask penerima `48`, satu operasi awal, dan operasi recovery terverifikasi. Evaluasi keenam level severity hanya meloloskan High dan Disaster. Belum ada uji event produksi baru setelah aktivasi; tiket #23 berasal dari fasilitas uji media, bukan action produksi. Script menyimpan ID tiket melalui event tag `__zbx_glpi_ticket_id`; jangan mengasumsikan jaminan tepat satu tiket ketika terjadi timeout pembuatan atau pengiriman paralel.

## Berkas

- `glpi-ticket-webhook.js`: script yang digunakan media type baru, berasal dari adaptasi script GLPi yang sudah tersedia pada Zabbix.
- `media-type.json`: payload contoh `mediatype.create` untuk Zabbix 6.0, dengan token kosong dan status disabled. Konfigurasi aktif server menyimpan token sebenarnya; berkas ini sengaja tidak memuat rahasia.
- `action-high-disaster.json`: payload action sesuai konfigurasi instance ini, dengan status disabled untuk peninjauan sebelum impor. ID media/penerima perlu disesuaikan pada instance lain; action di server saat ini aktif.

Script menambah App-Token untuk autentikasi dan request GLPI, menggunakan objek Ticket/ITILFollowup, membatasi urgency ke rentang GLPI 1–5, dan mencatat recovery tanpa mengubah status tiket.

## Langkah berikutnya

### Impor problem yang sudah aktif — 29 Oktober 2026

Impor awal keliru mencakup seluruh 206 problem aktif: 7 High, 150 Average, 3 Warning, dan 46 Information. Pengguna mengoreksi bahwa cakupannya harus High/Disaster saja. Tidak ada Disaster pada snapshot tersebut.

Impor awal menghasilkan Ticket #24 sampai #229. Koreksi memindahkan tepat 199 tiket severity di bawah High dari daftar hasil impor ke Trash melalui soft delete, dengan pemeriksaan penanda event sebelum perubahan dan `is_deleted=1` sesudahnya. Tidak dilakukan purge. Tujuh tiket High dipertahankan dan diverifikasi `is_deleted=0`: #53, #87, #112, #116, #133, #202, #224. Penanda `[Zabbix event <eventid>]` tetap menghubungkan masing-masing tiket ke event asalnya.

Media khusus impor ID `35` digunakan tanpa action otomatis dan sudah dinonaktifkan setelah selesai. Action produksi ID `7` tetap aktif dengan filter High/Disaster. Impor tidak memasangkan event lama ke action tersebut secara retroaktif; tiket hasil impor satu kali ini tidak menerima recovery otomatis dari action produksi. Tidak ada perubahan pada status acknowledge atau severity event Zabbix.

Pemetaan event dan tiket disimpan pada `outputs/zabbix-glpi-backfill-20261029/hasil-impor.csv` dengan kolom `current_state` yang mencatat hasil koreksi. `koreksi-severity.json` memuat ID tiket yang dipindahkan ke Trash dan dipertahankan; `verifikasi.json` mencatat hasil awal beserta koreksinya. Berkas tersebut tidak memuat kredensial.

Pantau satu event High/Disaster baru untuk memverifikasi eksekusi action, tag ID tiket, dan recovery secara penuh. Action berlaku untuk event PROBLEM baru yang cocok setelah aktivasi; tidak melakukan backfill masalah lama. Filter host/tag dapat diperketat kemudian. Tiket uji #23 dipertahankan sebagai bukti pengujian.

Untuk menghentikan pembuatan tiket otomatis, nonaktifkan action ID `7`. Untuk menghentikan seluruh koneksi media tersebut, nonaktifkan media type ID `34`. Jangan mengubah media type lama atau menghapus tiket secara otomatis.
