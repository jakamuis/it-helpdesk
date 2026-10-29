# DRAFT — Eskalasi Tiket ke Provider dan Pembagian Waktu SLA

Tanggal: 29 Oktober 2026 (Asia/Jakarta)  
Status: Draft kebijakan dan target; alur manual sudah diterapkan melalui plugin SLA Provider 1.0.0 pada 29 Oktober 2026.  
Terkait: [Draft Severity dan SLA](DRAFT-TICKET-SLA-SEVERITY.md).

Panduan implementasi: [SLA Provider](../glpi-plugins/providersla/README.md). Pengalihan dan pemulihan tetap diinput manual; durasi dihitung oleh plugin. Integrasi Zabbix ditunda. Target durasi belum ditetapkan secara global.

## Tujuan dan cakupan

Memisahkan pengukuran kinerja Helpdesk dan provider, misalnya ISP, dalam satu tiket yang tetap dapat ditelusuri sampai selesai. Waktu menunggu penanganan provider yang valid tidak dibebankan sebagai waktu penyelesaian Helpdesk. Total gangguan layanan tetap dicatat penuh.

Fokus tahap ini adalah proses tiket, pencatatan eskalasi, dan reporting. Integrasi Zabbix serta otomasi pembuatan/pemulihan tiket ditunda untuk tahap berikutnya.

## Ketentuan proses manual tahap awal

**SLA provider dimulai pada waktu Helpdesk mengalihkan tiket ke provider**, bukan saat tiket dibuat dan bukan saat provider membalas atau menerbitkan nomor tiketnya.

Pengalihan dilakukan dengan memilih/mencatat Supplier provider, mengirim laporan gangguan, dan membuat follow-up pada tiket GLPI berisi waktu pengalihan, petugas, tujuan provider, diagnosis, serta bukti pengiriman. Waktu pengalihan adalah waktu laporan gangguan dikirim ke kanal provider; catatan yang dibuat belakangan harus menuliskan waktu kejadian sebenarnya dan melampirkan buktinya. Assignment Supplier tanpa laporan pengalihan belum menjadi awal hitung.

Perhitungan dilakukan manual dari timestamp yang dicatat, belum menggunakan timer otomatis GLPI. Untuk pencatatan awal, gunakan durasi waktu berjalan 24×7 dalam zona Asia/Jakarta, tanpa jeda otomatis karena Pending. Jika kontrak memakai kalender atau awal hitung berbeda, hitungan kontrak dilaporkan terpisah dari hitungan operasional sejak pengalihan ini.

- Mulai: **waktu pengalihan Helpdesk ke provider**.
- Selesai: **waktu layanan/circuit dalam lingkup provider pulih, berdasarkan bukti yang diverifikasi Helpdesk**. Klaim selesai dari provider saja belum cukup.
- Durasi selesai: **waktu pulih − waktu pengalihan**.
- Durasi tiket berjalan: **waktu snapshot laporan − waktu pengalihan**.
- Deadline: **waktu pengalihan + target durasi provider**, bila target sudah ditetapkan untuk hitungan 24×7 ini.
- Memenuhi: waktu pulih sebelum atau tepat deadline; melanggar: setelah deadline.
- Tiket berjalan: belum lewat jika snapshot sebelum atau tepat deadline; terlambat jika setelah deadline.
- Tanpa target: durasi tetap dicatat, tetapi kepatuhan belum dinilai. Timestamp tidak lengkap: belum dapat dinilai.

Nomor tiket dan waktu penerimaan provider ditambahkan saat tersedia tanpa menggeser waktu mulai operasional. Koreksi waktu harus menyimpan nilai lama, nilai baru, alasan, dan petugas. Pengalihan ulang ke provider yang sama pada episode yang sama tidak mereset hitungan. Pergantian provider atau episode gangguan baru dicatat sebagai interval baru.

### Template follow-up manual

```text
PENGALIHAN KE PROVIDER
Ticket GLPI:
Provider / layanan / circuit ID:
Diagnosis dan alasan pengalihan:
Waktu pengalihan (Asia/Jakarta): YYYY-MM-DD HH:MM
Petugas Helpdesk:
Kanal dan bukti pengiriman:
Nomor tiket provider: [boleh menyusul]
Target pemulihan operasional: [belum ditetapkan / durasi]
Deadline operasional: [jika target tersedia]

PEMULIHAN PROVIDER
Waktu pulih (Asia/Jakarta): YYYY-MM-DD HH:MM
Waktu verifikasi Helpdesk:
Bukti dan hasil pengujian:
Durasi provider sejak pengalihan:
Hasil: [memenuhi / melanggar / tanpa target / belum dapat dinilai]
```

## Prinsip pengukuran

- Helpdesk tetap menjadi pemilik koordinasi tiket: diagnosis awal, eskalasi, follow-up, komunikasi pengguna, dan verifikasi pemulihan.
- Dalam reporting operasional manual ini, waktu provider dihitung sejak pengalihan Helpdesk. Penilaian kewajiban kontraktual tetap mengikuti kontrak dan dipisahkan bila dasar hitung berbeda.
- Perpindahan tanggung jawab perbaikan tidak menghapus riwayat SLA, keterlambatan Helpdesk sebelumnya, maupun downtime layanan.
- Pisahkan KPI penanganan aktif Helpdesk, kewajiban provider, dan SLA layanan kepada pengguna. Pengecualian waktu provider pada KPI Helpdesk tidak otomatis mengecualikannya dari SLA layanan kepada pengguna.
- Kesepakatan vendor eksternal dalam istilah ITIL adalah underpinning contract; OLA merujuk kesepakatan internal. Pemanfaatan fitur OLA GLPI untuk target vendor masih harus diverifikasi, bukan dianggap sebagai mekanisme siap pakai.

## Alur tiket yang diusulkan

| Tahap | Kegiatan | Penanggung jawab perbaikan | Pencatatan minimum |
| --- | --- | --- | --- |
| Tiket masuk | Catat gangguan dan layanan yang terdampak | Belum ditentukan | Waktu gangguan diketahui, waktu dibuat, layanan/site/circuit ID |
| Pemeriksaan Helpdesk | Ambil penanganan, cek perangkat/jaringan internal, kumpulkan bukti | Helpdesk | Waktu mulai penanganan, diagnosis, hasil pemeriksaan |
| Eskalasi provider | Identifikasi dugaan gangguan ISP dan kirim laporan lengkap | Helpdesk sampai pengalihan tercatat | Provider, waktu pengalihan/laporan dikirim, bukti pengiriman, nomor tiket provider bila tersedia |
| Menunggu provider | Provider menangani setelah tiket dialihkan | Provider untuk pengukuran sejak pengalihan | Waktu pengalihan sebagai awal hitung; penerimaan, update, dan estimasi pemulihan dicatat terpisah |
| Verifikasi | Uji layanan setelah informasi pemulihan diterima | Helpdesk | Waktu pulih yang dibuktikan, waktu mulai/selesai verifikasi, hasil uji |
| Solved / Closed | Catat solusi lalu tutup mengikuti proses GLPI | Helpdesk | Solusi, penyebab akhir, tanggal Solved/Closed |

Nama tahap di atas adalah tahapan proses, bukan seluruhnya status bawaan GLPI. Rancangan pemetaan: Assigned/Processing untuk pemeriksaan, Pending dengan alasan khusus “Menunggu Provider” untuk masa tunggu yang valid, kemudian Processing saat verifikasi dan Solved setelah lolos uji. Ketersediaan status/alasan dan dampaknya pada timer harus diverifikasi sebelum implementasi.

## Aturan perpindahan waktu

1. Timer respons Helpdesk dimulai saat tiket dibuat dan berhenti ketika penanganan pertama benar-benar dimulai. Assignment otomatis tidak cukup sebagai bukti petugas mulai memeriksa.
2. Diagnosis serta waktu persiapan/pengiriman eskalasi tetap dihitung ke Helpdesk.
3. KPI penanganan aktif Helpdesk berhenti pada pengalihan lengkap yang tercatat beserta bukti pengiriman. Waktu sebelum pengalihan tetap menjadi waktu Helpdesk.
4. Timer operasional provider dimulai pada waktu pengalihan tersebut. Balasan atau nomor tiket provider yang datang kemudian tidak mengubah awal hitung.
5. Catat waktu penerimaan provider untuk memantau responsnya. Interval pengalihan sampai penerimaan tetap termasuk durasi operasional provider; jika kontrak berbeda, tampilkan hitungan kontrak secara terpisah.
6. Selama menunggu provider, Helpdesk tetap wajib follow-up dan memberi update. KPI follow-up dipisahkan dari KPI penanganan aktif; targetnya belum ditetapkan.
7. Jika provider meminta tindakan internal, catat interval tindakan Helpdesk. Timer operasional provider tetap berjalan tanpa pengurangan otomatis. Pengecualian kontrak, bila ada, dihitung terpisah dengan alasan dan bukti.
8. Akhir hitung operasional provider adalah waktu pemulihan layanan/circuit terkait yang dibuktikan dan diverifikasi Helpdesk. Waktu provider menyatakan selesai, waktu layanan benar-benar pulih, dan waktu verifikasi Helpdesk dicatat terpisah.
9. Verifikasi Helpdesk dihitung sebagai waktu Helpdesk. Tanggal Closed administratif tidak digunakan untuk memperpanjang durasi gangguan atau durasi pemulihan provider.
10. Bila penyebab ternyata internal, koreksi atribusi dengan alasan dan riwayat perubahan. Jangan menghilangkan riwayat eskalasi atau menghitung interval yang sama dua kali pada pembagian waktu eksklusif.

## Ukuran reporting

| Ukuran | Perhitungan / dasar |
| --- | --- |
| Respons Helpdesk | Mulai penanganan pertama − tiket dibuat, mengikuti kalender KPI internal |
| Diagnosis dan eskalasi awal | Waktu pengalihan − mulai penanganan pertama |
| Penanganan aktif Helpdesk | Jumlah interval tanggung jawab aktif Helpdesk, termasuk tindakan internal tambahan dan verifikasi; waktu tunggu provider yang valid dikecualikan |
| Waktu provider | Waktu pulih − waktu pengalihan Helpdesk, 24×7 tanpa jeda otomatis; jika berjalan gunakan waktu snapshot sebagai akhir sementara |
| Total downtime | Jumlah interval layanan tidak tersedia dari awal gangguan yang terbukti sampai pulih; tidak berhenti karena Pending |
| Lama siklus tiket | Solved − tiket dibuat; ditampilkan terpisah dari downtime |
| Kepatuhan follow-up | Perbandingan waktu update aktual dengan kewajiban follow-up yang akan disepakati |

Jika awal gangguan tidak diketahui, tandai sebagai tidak diketahui atau estimasi dan tampilkan dasar estimasinya. Jangan menyamakan tanggal pembuatan tiket dengan awal downtime tanpa bukti. Jika layanan pulih lewat koneksi cadangan, downtime layanan dapat berakhir sementara gangguan circuit ISP masih berlangsung; catat kedua waktu pemulihan tersebut terpisah.

Pembagian interval eksklusif Helpdesk/provider/verifikasi digunakan untuk menjelaskan perjalanan tiket. Timer operasional provider tetap berjalan ketika Helpdesk melakukan tindakan tertentu; karena itu durasi KPI/kontrak tidak selalu dapat dijumlahkan menjadi downtime.

Hasil SLA Helpdesk dan provider dilaporkan masing-masing sebagai memenuhi, melanggar, berjalan belum lewat, berjalan terlambat, atau tanpa target. Data waktu yang tidak lengkap diberi label **belum dapat dinilai**, bukan dianggap memenuhi. Target yang belum disepakati dilaporkan **Tanpa Target**. Jangan menetapkan target jam secara asumsi.

## Contoh alur sederhana

Asumsi: layanan sudah terganggu saat tiket dibuat, kalender operasional 24×7, dan awal hitung provider adalah pengalihan Helpdesk.

| Waktu | Kejadian | Hasil |
| --- | --- | --- |
| 08.00 | Gangguan mulai dan tiket dibuat | Awal downtime dan respons Helpdesk |
| 08.05 | Helpdesk mulai memeriksa | Respons Helpdesk 5 menit |
| 08.15 | Helpdesk mengalihkan dan mengirim laporan ke ISP | Diagnosis/eskalasi 10 menit; mulai waktu provider |
| 08.25 | ISP membalas dan memberikan nomor tiket | Dicatat sebagai penerimaan; awal hitung tetap 08.15 |
| 10.00 | Layanan pulih, kemudian diverifikasi | Waktu pemulihan provider 1 jam 45 menit; downtime 2 jam |
| 10.10 | Verifikasi selesai, tiket Solved | Verifikasi Helpdesk 10 menit; siklus tiket 2 jam 10 menit |

Jika target contoh adalah 2 jam (ilustrasi, bukan target yang ditetapkan), deadline 10.15 dan durasi 1 jam 45 menit memenuhi target.

Dalam contoh ini, penanganan aktif Helpdesk 20 menit (10 menit diagnosis/eskalasi + 10 menit verifikasi). Waktu respons 5 menit dilaporkan terpisah. Masa tunggu ISP 1 jam 45 menit tidak dibebankan ke penanganan aktif Helpdesk. Kepatuhan baru dapat ditentukan setelah ada target.

## Data yang perlu tersedia

- Ticket ID GLPI, provider/Supplier, layanan/site, circuit/customer ID, dan referensi kontrak beserta versi target yang berlaku.
- Jenis gangguan, severity/priority, diagnosis, penyebab akhir, petugas dan grup Helpdesk.
- Waktu gangguan mulai, tiket dibuat, mulai penanganan, laporan dikirim, laporan diterima, serta nomor tiket provider.
- Bukti eskalasi/penerimaan, titik awal dan akhir timer kontrak, kalender, target, serta alasan pengecualian.
- Riwayat perpindahan tanggung jawab berupa interval: pihak, mulai, akhir, alasan, pencatat, dan bukti terkait.
- Update provider, jadwal/aktual follow-up, layanan pulih, circuit pulih bila berbeda, verifikasi, Solved, dan Closed.
- Riwayat koreksi, reopen, pergantian provider, dan waktu snapshot reporting.

Satu nomor tiket provider dapat berhubungan dengan beberapa tiket internal dalam outage bersama. Hubungan tersebut perlu dicatat agar jumlah kejadian dan downtime provider tidak terhitung ganda. Untuk reopen atau gangguan berulang, simpan setiap episode gangguan dan interval tanggung jawabnya.

## Rancangan GLPI dan hal yang masih terbuka

Gunakan satu tiket GLPI sebagai catatan utama dengan Helpdesk sebagai koordinator dan Supplier sebagai provider terkait. Penetapan Supplier tidak otomatis memindahkan timer. Kebutuhan field dan histori di atas akan dipetakan ke fasilitas native, plugin, atau pencatatan tambahan setelah kemampuan versi GLPI diperiksa.

Sebelum implementasi, perlu ditetapkan:

- Provider dan target durasi operasional sejak pengalihan. Awal hitung operasional sudah ditetapkan dalam draft ini; target durasinya belum ditetapkan.
- Kontrak, kalender, titik awal/akhir, dan pengecualian kontraktual untuk laporan terpisah jika berbeda.
- Target respons, diagnosis/eskalasi, verifikasi, dan follow-up Helpdesk.
- Bukti minimum serta siapa yang boleh mengaktifkan/mengakhiri “Menunggu Provider”.
- Pemisahan SLA layanan kepada pengguna dari KPI tim Helpdesk dan kontrak provider.
- Perilaku Pending terhadap SLA/OLA GLPI dan cara memastikan timer provider tidak ikut berhenti tanpa dasar kontrak.
- Pemetaan field, pencatatan interval, audit perubahan, dan format laporan.

Dokumen ini menjadi dasar implementasi manual SLA Provider 1.0.0. Tabel pencatatan provider dan tab tiket sudah ditambahkan di GLPI lokal/server. Plugin menjeda TTR native dengan Pending dan menghitung timer provider secara terpisah; tidak mengirim laporan kepada provider atau mengimplementasikan integrasi Zabbix. Rincian target, downtime, jam kerja aktif Helpdesk, dan KPI lain yang belum tersedia tetap mengikuti batasan pada panduan implementasi.
