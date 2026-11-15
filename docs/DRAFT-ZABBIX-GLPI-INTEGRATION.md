# Draft integrasi alert Zabbix ke tiket GLPI

Tanggal: 29 Oktober 2026  
Status: draft untuk ditinjau; belum diterapkan atau diuji pada server.

## Tujuan dan lingkungan

Alert Zabbix otomatis membuat tiket insiden di GLPI, kemudian memperbarui tiket yang sama saat ada perubahan atau pemulihan.

| Komponen | Alamat | Catatan |
| --- | --- | --- |
| Zabbix | `192.168.1.241` | Versi, skema HTTP/HTTPS, dan path UI belum diperiksa |
| GLPI | `192.168.1.189` | Versi dan endpoint API belum diperiksa |
| Integrasi | Layanan terpisah pada server GLPI, usulan | Port, metode publikasi, dan kapasitas perlu diperiksa |

Tidak ada perubahan pada middleware WhatsApp dalam draft ini. Integrasi ditambahkan sebagai layanan tersendiri agar kompatibilitas layanan yang ada terjaga.

## Rancangan alur

1. Trigger Zabbix masuk kondisi PROBLEM dan memenuhi filter action.
2. Media type webhook Zabbix mengirim identitas event dan informasi masalah ke layanan integrasi.
3. Layanan memvalidasi autentikasi dan payload, lalu mencari pemetaan event ke tiket.
4. Jika belum ada pemetaan, layanan membuat tiket GLPI melalui API dan menyimpan ID tiket.
5. Pengiriman ulang event yang sama menggunakan pemetaan tersebut, sehingga tidak membuat tiket baru.
6. Update atau recovery memperbarui tiket yang sama. Recovery menambahkan tindak lanjut; penyelesaian otomatis bersifat opsional.

Usulan menggunakan layanan perantara dengan penyimpanan persisten agar deduplikasi, retry, dan keterlambatan event dapat ditangani. Sebelum implementasi, periksa apakah versi Zabbix menyediakan integrasi GLPI resmi yang sudah memenuhi kebutuhan tersebut; jika sesuai, gunakan integrasi resmi untuk mengurangi komponen yang harus dipelihara.

## Kebijakan tiket awal yang diusulkan

| Kondisi | Tindakan |
| --- | --- |
| PROBLEM pertama | Buat tiket insiden dengan status New |
| PROBLEM dikirim ulang | Gunakan tiket yang sama |
| Update event | Tambahkan tindak lanjut jika isinya baru |
| RECOVERY | Tambahkan tindak lanjut berisi waktu pulih; status tetap untuk verifikasi petugas |
| Event baru pada host yang sama | Buat tiket baru berdasarkan event masalah yang berbeda |
| Recovery datang sebelum tiket terbentuk | Simpan untuk rekonsiliasi; jangan dibuang |

Identitas utama: kombinasi instance Zabbix dan ID event PROBLEM asli. ID event recovery harus dikorelasikan ke ID masalah asli menggunakan macro yang didukung versi Zabbix terpasang. Nama host atau judul masalah tidak digunakan sebagai kunci deduplikasi.

Filter awal: hanya High dan Disaster; host sedang maintenance dikecualikan. Perlu penetapan entity, kategori, grup penanggung jawab, dan akun pemohon GLPI sebelum aktivasi. Tiket dibuat pada entity yang ditentukan konfigurasi, bukan dari input bebas webhook.

| Severity Zabbix | Urgency GLPI usulan |
| --- | --- |
| Not classified / Information | Very low |
| Warning | Low |
| Average | Medium |
| High | High |
| Disaster | Very high |

Impact mengikuti cakupan gangguan yang disetujui. Priority mengikuti matriks urgency dan impact GLPI; severity tidak langsung menetapkan SLA atau membuktikan dampak bisnis.

## Isi tiket

Judul: `[Zabbix][{severity}] {host}: {problem_name}`

Deskripsi:

```text
Sumber       : Zabbix 192.168.1.241
Host         : <nama host>
Alamat host  : <IP/DNS>
Masalah      : <nama trigger/event>
Severity     : <severity>
Mulai        : <waktu beserta zona waktu>
Event ID     : <ID event PROBLEM asli>
Operational data: <jika tersedia>
Tautan event : <URL event Zabbix>
```

Konten dari Zabbix harus di-escape sesuai format GLPI. Batasi ukuran payload dan jangan memasukkan password, token, atau hasil monitoring yang mengandung rahasia. Relasi ke aset GLPI dapat ditambahkan kemudian dengan pemetaan host yang tervalidasi.

## Kontrak webhook usulan

Endpoint usulan: `POST /integrations/zabbix/events` pada layanan integrasi; bukan endpoint bawaan GLPI. Alamat lengkap dan port belum ditetapkan.

Autentikasi: `Authorization: Bearer <secret-khusus-integrasi>`.

Contoh payload konseptual, bukan template macro siap impor:

```json
{
  "source": "zabbix-192.168.1.241",
  "problem_event_id": "123456",
  "delivery_event_id": "123456",
  "event_type": "problem",
  "occurred_at": "2026-10-29T10:00:00+07:00",
  "host": "router-cabang-01",
  "host_address": "192.0.2.10",
  "severity": "High",
  "problem_name": "Host unavailable",
  "operational_data": "Unavailable",
  "event_url": "<URL event Zabbix>"
}
```

`event_type` menerima `problem`, `update`, atau `recovery`. Penamaan field, macro, dan timestamp final harus disesuaikan dengan versi Zabbix. Identitas pengiriman diperlukan untuk mencegah tindak lanjut berulang pada update/recovery.

Layanan hanya mengakui penerimaan setelah event tersimpan secara persisten. Worker memproses antrean dan menyimpan pemetaan tiket. Kegagalan sementara memakai retry dengan jeda bertambah dan batas percobaan; kegagalan permanen masuk antrean pemeriksaan petugas. Respons ambigu saat membuat tiket harus direkonsiliasi melalui penanda event pada GLPI sebelum mengulang pembuatan, karena request timeout dapat terjadi setelah tiket berhasil dibuat.

## Kebutuhan GLPI dan operasional

- Verifikasi versi GLPI dan API yang didukung. Kandidat untuk API legacy: `/apirest.php`, dengan alur `initSession`, pembuatan Ticket, penambahan ITILFollowup, lalu `killSession`. Endpoint dan field wajib diverifikasi terhadap instance sebenarnya.
- Gunakan akun integrasi dengan hak minimum untuk entity tujuan, membuat tiket, membaca tiket terkait, dan menambah tindak lanjut. Hak menyelesaikan tiket hanya jika kebijakan tersebut disetujui.
- Simpan App-Token, User-Token, dan secret webhook pada environment server khusus integrasi dengan mode file `600`; jangan masukkan ke Git atau dokumentasi.
- Batasi akses jaringan endpoint integrasi dari server Zabbix. Gunakan HTTPS dengan sertifikat tervalidasi saat menerbitkan endpoint.
- Simpan antrean dan pemetaan pada SQLite persisten dengan indeks unik untuk identitas event dan pengiriman. Cadangkan database sebelum pembaruan layanan.
- Log hanya metadata yang diperlukan: event ID, ticket ID, status pemrosesan, dan jenis kegagalan. Redaksi token dan header autentikasi.
- Selaraskan waktu kedua server. Simpan timestamp dengan zona waktu dan tampilkan waktu operasional dalam Asia/Jakarta.
- Pantau kesehatan layanan, jumlah antrean tertunda, dan kegagalan; sediakan pemeriksaan manual saat integrasi bermasalah.

## Tahapan penerapan setelah draft disepakati

1. Periksa versi Zabbix/GLPI, endpoint API, konektivitas, dan integrasi resmi yang tersedia.
2. Tetapkan entity, kategori, pemohon, grup teknisi, severity yang diaktifkan, serta aturan recovery.
3. Siapkan akun dan kredensial integrasi di server tanpa menyalinnya ke repositori.
4. Siapkan layanan, penyimpanan persisten, dan konfigurasi media type sesuai versi Zabbix.
5. Buat action terbatas pada satu host uji; jangan langsung menerapkan ke seluruh host.
6. Jalankan skenario penerimaan berikut dan tinjau tiket hasilnya.
7. Aktifkan bertahap pada host yang dipilih dan pantau antrean serta duplikasi.

## Skenario penerimaan

- Satu PROBLEM menghasilkan tepat satu tiket pada entity dan grup yang ditetapkan.
- Pengiriman PROBLEM berulang, termasuk bersamaan, tidak menambah tiket.
- Update dan recovery masuk ke tiket yang benar, termasuk jika terkirim ulang atau tidak berurutan.
- Recovery menambahkan catatan tanpa menyelesaikan tiket pada kebijakan awal.
- GLPI tidak tersedia sementara: event tetap tersimpan dan diproses setelah pulih.
- Timeout setelah tiket dibuat: rekonsiliasi menemukan tiket tanpa membuat duplikat.
- Restart layanan tidak menghilangkan antrean atau pemetaan.
- Token salah ditolak; log dan respons tidak membocorkan kredensial.
- Host maintenance dan severity di luar filter tidak menghasilkan tiket.

## Penghentian dan rollback

Nonaktifkan action Zabbix terlebih dahulu, lalu hentikan layanan integrasi jika diperlukan. Pertahankan database pemetaan, antrean, dan tiket yang sudah dibuat untuk audit serta kelanjutan proses. Jangan menghapus tiket otomatis saat rollback. Layanan GLPI dan middleware WhatsApp tetap berjalan.

## Hal yang masih perlu ditetapkan

- Versi Zabbix dan GLPI serta URL lengkap masing-masing.
- Pilihan integrasi resmi atau layanan perantara setelah pemeriksaan kemampuan versi.
- Entity, kategori, akun pemohon, grup teknisi, dan aturan SLA GLPI.
- Cakupan host dan severity awal; usulan High/Disaster perlu ditinjau.
- Kebijakan recovery: catatan saja atau menyelesaikan tiket otomatis; default draft adalah catatan saja.
- Lokasi layanan, port, sertifikat, retensi antrean/log, dan penanggung jawab operasional.
