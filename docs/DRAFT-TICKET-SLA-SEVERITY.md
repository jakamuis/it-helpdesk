# DRAFT — Pembagian Severity dan SLA Reporting Tiket

Tanggal: 28 Oktober 2026 (Asia/Jakarta)  
Status: Draft pembahasan; belum menjadi kebijakan dan belum diterapkan ke GLPI.

Draft lanjutan 29 Oktober 2026: [Eskalasi Tiket ke Provider dan Pembagian Waktu SLA](DRAFT-TICKET-PROVIDER-SLA.md). Pembahasan lanjutan berfokus pada tiket provider; integrasi Zabbix ditunda.

## 1. Hasil pemeriksaan saat ini

Pemeriksaan read-only pada GLPI lokal, bukan verifikasi konfigurasi terbaru server 192.168.1.189:

- Terdapat 10 tiket non-deleted: 7 New, 1 Solved, 2 Closed.
- Seluruh tiket memiliki priority Medium (nilai 3).
- Tabel SLA dan SLM belum memiliki konfigurasi.
- Tidak ada tiket dengan SLA TTO, SLA TTR, atau deadline penyelesaian.
- Tiket lokal bertanggal dibuat 31 Maret–20 Mei 2026; data ini tidak mewakili laporan server terkini.
- Export Sheets/AppSheet di `main.py`, fungsi `transform_glpi_tickets`, baru berisi Ticket ID, Title, Status, Priority, Date Created, Date Modified, dan Description.

Kesimpulan: 10 tiket lokal masuk kategori **Tanpa SLA**. Persentase kepatuhan SLA belum dapat dihitung; jangan dilaporkan sebagai 0% atau 100%.

## 2. Dasar konsep ITIL

Berikut parafrasa konsep ITIL untuk rancangan ini, bukan kutipan verbatim dari publikasi resmi:

| Istilah | Pengertian untuk pembahasan |
| --- | --- |
| Incident | Gangguan yang tidak direncanakan terhadap suatu layanan atau penurunan kualitas layanan. |
| Impact | Besarnya dampak gangguan terhadap proses bisnis; mencakup cakupan pengguna, layanan kritis, dan konsekuensi bisnis. |
| Urgency | Seberapa cepat tindakan diperlukan sebelum gangguan menimbulkan dampak bisnis yang berarti. |
| Priority | Tingkat kepentingan relatif untuk menentukan urutan serta waktu penanganan; biasanya ditentukan dari impact dan urgency. |
| Major incident | Incident dengan dampak bisnis signifikan yang memerlukan koordinasi penanganan khusus dan segera. |
| SLA | Kesepakatan terdokumentasi antara penyedia layanan dan pelanggan yang menetapkan layanan serta tingkat layanan yang diharapkan. |

**ITIL tidak menetapkan satu jumlah severity universal.** Organisasi menetapkan skala, kriteria, dan target berdasarkan kebutuhan layanan. Usulan empat level di bawah merupakan rancangan lokal, bukan empat level wajib dari ITIL. Referensi Atlassian bahkan menggunakan tiga level sebagai contoh praktik organisasinya.

Severity menggambarkan tingkat keparahan/dampak incident. Priority menentukan kebutuhan dan urutan penanganan dengan mempertimbangkan urgency. Keduanya tidak otomatis sama, dan severity bukan pengganti status tiket.

## 3. Usulan empat level severity

| Level | Nama | Definisi operasional yang diusulkan | Contoh |
| --- | --- | --- | --- |
| SEV1 | Critical | Layanan bisnis kritis terhenti dengan dampak sangat besar, atau ada ancaman serius terhadap keselamatan, keamanan, atau integritas data; tidak tersedia workaround yang memadai. | Sistem produksi utama berhenti; jaringan site utama terputus sehingga operasi berhenti; insiden keamanan berdampak kritis. |
| SEV2 | High | Gangguan besar pada fungsi penting, satu departemen/site, atau banyak pengguna; operasi sangat terganggu dan workaround tidak tersedia atau sangat terbatas. | Aplikasi penting tidak bisa digunakan satu departemen; koneksi utama bermasalah dengan kapasitas cadangan terbatas. |
| SEV3 | Medium | Gangguan terbatas pada sebagian kecil pengguna atau fungsi nonkritis; bisnis masih dapat berjalan dengan workaround yang layak. | Satu PC kerja bermasalah dan tersedia perangkat pengganti; printer unit bermasalah dengan printer alternatif. |
| SEV4 | Low | Gangguan ringan dengan dampak minimal; fungsi utama dan kegiatan bisnis tetap berjalan. | Gangguan tampilan atau fungsi minor yang tidak menghambat pekerjaan. |

Jumlah pengguna bukan satu-satunya penentu: satu perangkat yang mengendalikan proses kritis dapat memiliki severity tinggi. Ketersediaan workaround dan konsekuensi bisnis harus dinilai. Service request seperti instalasi terencana atau permintaan akses dipisahkan dari incident dan diberi target layanan sesuai katalog; jangan otomatis memasukkan semua request ke SEV4.

SEV1 memicu evaluasi prosedur major incident. Penetapan major incident tetap berdasarkan kriteria dampak bisnis dan kebutuhan koordinasi yang disepakati.

## 4. Usulan penentuan priority

Gunakan tiga tingkat impact dan urgency untuk penilaian awal. Matriks ini adalah usulan lokal, bukan matriks baku wajib ITIL.

| Impact / Urgency | High: tindakan segera diperlukan | Medium: dapat menunggu terbatas | Low: dapat dijadwalkan |
| --- | --- | --- | --- |
| High: proses/layanan kritis atau dampak luas | P1 | P2 | P3 |
| Medium: unit/fungsi penting terdampak | P2 | P3 | P4 |
| Low: dampak terbatas dan bisnis tetap berjalan | P3 | P4 | P4 |

Nama usulan: P1 Critical, P2 High, P3 Medium, P4 Low. Priority menjadi dasar pemilihan target SLA. Jangan memetakan SEV1=P1 sampai SEV4=P4 secara otomatis tanpa menilai urgency.

P1–P4 adalah kode rancangan, bukan ID numerik priority GLPI. GLPI memiliki skala prioritas sendiri; pemetaan label/ID, impact, urgency, dan aturan assignment perlu diverifikasi sebelum implementasi. Severity juga perlu diputuskan apakah akan disimpan sebagai field tambahan atau klasifikasi reporting.

## 5. Pembagian SLA yang akan dilaporkan

| Ukuran | Definisi rancangan | Catatan implementasi |
| --- | --- | --- |
| TTO — Time to Own | Waktu dari tiket dibuat sampai diambil alih untuk ditangani sesuai mekanisme GLPI. | Verifikasi pemicu aktual pengambilan alih. TTO tidak otomatis identik dengan balasan pertama kepada pengguna. |
| TTR — Time to Resolve | Waktu dari tiket dibuat sampai layanan dipulihkan/incident dinyatakan Solved sesuai kebijakan solusi. | Gunakan tanggal Solved dan deadline terkait; Date Modified bukan tanggal penyelesaian. |

Jika KPI respons pertama dibutuhkan, definisikan terpisah: misalnya balasan pertama petugas yang terlihat oleh pelapor. Auto-reply penerimaan tiket tidak otomatis dihitung sebagai respons petugas.

| Priority | Target TTO | Target TTR | Kalender |
| --- | --- | --- | --- |
| P1 | Belum ditetapkan | Belum ditetapkan | Perlu diputuskan |
| P2 | Belum ditetapkan | Belum ditetapkan | Perlu diputuskan |
| P3 | Belum ditetapkan | Belum ditetapkan | Perlu diputuskan |
| P4 | Belum ditetapkan | Belum ditetapkan | Perlu diputuskan |

Target waktu SLA tidak ditentukan secara universal oleh ITIL. Tetapkan melalui kesepakatan layanan dan kemampuan operasional.

## 6. Kelompok hasil reporting

Hitung terpisah untuk TTO dan TTR:

| Kelompok | Kriteria |
| --- | --- |
| Memenuhi SLA | Milestone penanganan/penyelesaian tercapai sebelum atau tepat deadline. |
| Melanggar SLA | Milestone tercapai setelah deadline. |
| Berjalan, belum lewat | Milestone belum tercapai dan deadline belum lewat. |
| Berjalan, terlambat | Milestone belum tercapai dan deadline sudah lewat. |
| Tanpa SLA | Tidak memiliki target yang dapat dievaluasi. |

Usulan metrik tiket yang sudah mencapai milestone:

`Kepatuhan SLA (%) = Memenuhi SLA / (Memenuhi SLA + Melanggar SLA) × 100`

Denominator nol dilaporkan sebagai N/A. Tiket berjalan dan tanpa SLA ditampilkan terpisah beserta jumlahnya. Angka ini perlu dilengkapi jumlah backlog terlambat agar keterlambatan tiket yang belum selesai tetap terlihat.

Untuk laporan penyelesaian bulanan, gunakan cohort tanggal Solved pada bulan laporan. Untuk backlog, gunakan snapshot pada akhir periode. Jangan mencampur cohort tiket dibuat dan tiket selesai tanpa penjelasan. Perubahan priority/SLA dan reopen perlu histori agar hasil laporan periode terdahulu dapat direproduksi.

Kolom minimum yang diusulkan: Ticket ID, jenis tiket, layanan/kategori, severity, impact, urgency, priority, status, tim/teknisi, tanggal dibuat, waktu pengambilan alih, tanggal Solved/Closed, identitas SLA, deadline TTO/TTR, kalender, durasi pending yang relevan, hasil TTO/TTR, serta waktu snapshot laporan.

## 7. Hal yang perlu disepakati sebelum implementasi

- Kriteria layanan kritis, cakupan pengguna/site, dan penanggung jawab validasi severity.
- Target TTO/TTR per priority dan bila perlu per layanan/jenis permintaan.
- Kalender kerja, zona waktu, hari libur, serta dukungan di luar jam kerja.
- Alasan Pending yang menghentikan hitungan, aturan persetujuan, dan perilaku GLPI yang sebenarnya.
- Aturan eskalasi, perubahan priority, pemulihan sementara, penyelesaian permanen, serta reopen.
- Pemetaan ke field GLPI dan penambahan field reporting Sheets/AppSheet.
- Pemeriksaan konfigurasi serta data terbaru di server sebelum menjadikan laporan ini baseline operasional.

## 8. Referensi dan batas sumber

- [IT Process Wiki — Checklist Incident Priority](https://wiki.en.it-processmaps.com/index.php/Checklist_Incident_Priority): referensi sekunder praktik ITIL tentang impact, urgency, priority, dan major incident; berhasil dibaca saat penyusunan draft.
- [Atlassian — Understanding incident severity levels](https://www.atlassian.com/incident-management/kpis/severity-levels): contoh praktik severity organisasi dan perbedaannya dari priority; berhasil dibaca saat penyusunan draft. Ini bukan standar ITIL.
- Publikasi/glossary resmi ITIL dari PeopleCert/AXELOS belum berhasil diakses pada pemeriksaan ini. Definisi di atas merupakan parafrasa untuk draft; kutipan resmi dan edisi ITIL perlu divalidasi sebelum pengesahan kebijakan.

Tidak ada konfigurasi SLA, data tiket, atau integrasi yang diubah dalam penyusunan draft ini.
