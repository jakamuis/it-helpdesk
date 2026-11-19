# Panduan Penggunaan IT Helpdesk SAMATOR

Panduan ini menjelaskan cara melaporkan gangguan atau kebutuhan layanan dan cara tim IT menangani tiket di GLPI. Alur utamanya mengikuti presentasi **IT Helpdesk SAMATOR — Standardisasi Operasional & SLA**.

> **Penting:** Kategori prioritas, target SLA, dan angka KPI pada presentasi masih berupa usulan atau ilustrasi. Gunakan hanya kebijakan dan target yang telah disetujui perusahaan. Jangan menyampaikan target simulasi sebagai janji layanan resmi.

## 1. Kenali jenis layanan

| Jenis | Gunakan untuk | Contoh |
|---|---|---|
| **Incident** | Gangguan pada layanan atau fasilitas IT yang sudah digunakan dan perlu dipulihkan. | Jaringan terputus, email bermasalah, aplikasi tidak dapat diakses. |
| **Service Request** | Permintaan layanan, akses, atau kebutuhan baru yang bukan laporan gangguan. | Permintaan akses aplikasi atau instalasi software. |
| **Request IT** | Pengajuan tertentu yang membutuhkan proses persetujuan tersendiri, bukan tiket Incident. | Pembuatan, reset, perubahan, atau penghapusan email; pemasangan Office 365. |

Gunakan **Incident** jika sesuatu yang sebelumnya berfungsi kini terganggu. Gunakan **Service Request** jika meminta sesuatu yang baru atau perubahan layanan. Untuk layanan yang tercakup pada **Request IT**, ikuti formulir dan alur approval Request IT; jangan menggantinya dengan tiket gangguan. Request IT merupakan objek terpisah dari tiket GLPI.

## 2. Cara pengguna membuat laporan

Kirim laporan melalui kanal Helpdesk resmi yang tersedia di perusahaan, misalnya WhatsApp, email, atau portal GLPI. Ketersediaan tiap kanal bergantung pada konfigurasi yang aktif. Pastikan laporan telah tercatat sebagai tiket dan simpan nomor tiket untuk tindak lanjut.

### Informasi yang perlu disertakan

1. Nama pelapor dan cara untuk menghubungi kembali.
2. Jenis masalah atau layanan yang diminta.
3. Layanan, aplikasi, perangkat, serta lokasi/cabang yang terdampak.
4. Waktu mulai dan waktu terakhir layanan diketahui berfungsi.
5. Pesan kesalahan atau gejala yang terlihat, disertai langkah yang telah dicoba.
6. Dampak terhadap pekerjaan: siapa yang terdampak, proses yang terhenti, dan apakah ada cara sementara untuk bekerja.
7. Bukti yang membantu pemeriksaan, seperti tangkapan layar tanpa kata sandi, OTP, atau informasi rahasia.

Jangan mengirim kata sandi, OTP, token, atau data rahasia melalui tiket maupun WhatsApp. Untuk dugaan insiden keamanan, sampaikan segera melalui jalur eskalasi keamanan perusahaan; jangan menunggu komunikasi biasa jika ada dampak aktif.

### Setelah laporan dikirim

- Simpan nomor tiket dan gunakan tiket yang sama untuk menambahkan informasi tentang gangguan yang sama.
- Beri tahu Helpdesk jika dampak, jumlah pengguna, atau kondisi layanan berubah.
- Tanggapi permintaan informasi dari teknisi agar pemeriksaan tidak terhambat.
- Uji layanan setelah ada informasi pemulihan. Jika masalah belum benar-benar selesai, beri tahu Helpdesk melalui kanal tindak lanjut yang tersedia.
- Hindari membuat laporan ganda untuk gangguan yang sama. Jika ada tiket lain yang terkait, sampaikan nomor tiketnya.

## 3. Menentukan dampak dan prioritas

Prioritas mempertimbangkan **dampak terhadap operasional**, bukan jabatan atau senioritas pelapor. Pengguna sebaiknya menjelaskan dampaknya; tim IT menetapkan prioritas sesuai kebijakan yang telah disepakati.

| Kategori dampak pada presentasi | Panduan memahami dampak |
|---|---|
| **Major** | Operasional kritikal berhenti total dan tidak ada alternatif. |
| **Very High** | Gangguan berat pada layanan penting atau aktivitas utama. |
| **High** | Gangguan signifikan pada divisi/cabang sehingga operasional terbatas. |
| **Medium** | Pekerjaan individu/kelompok terhambat, tetapi tersedia alternatif. |
| **Low** | Gangguan minor dengan dampak kecil pada produktivitas. |
| **Very Low** | Permintaan administratif tanpa dampak langsung pada operasional. |

Nama dan pemetaan kategori ini mengikuti usulan pada presentasi. Gunakan pilihan prioritas yang benar-benar tersedia di GLPI dan aturan prioritas yang telah disahkan; jangan mengasumsikan kategori di atas sudah menjadi konfigurasi resmi.

## 4. Alur kerja tim IT

1. **Catat setiap Incident dan Service Request sebagai tiket.** Laporan dari kanal mana pun perlu masuk ke sistem pencatatan agar memiliki nomor, status, penanggung jawab, dan riwayat.
2. **Tinjau dan klasifikasikan.** Pastikan jenis tiket, layanan/aset, lokasi, dampak, dan informasi awal cukup. Minta detail tambahan bila perlu.
3. **Tetapkan PIC.** Tunjuk teknisi atau grup yang bertanggung jawab sesuai layanan dan dampak. Assignment saja belum merupakan respons teknis kepada pengguna.
4. **Berikan respons pertama.** Konfirmasikan bahwa laporan ditinjau dan sampaikan langkah berikutnya. Balasan otomatis bukan respons teknisi.
5. **Periksa, tangani, dan perbarui tiket.** Catat temuan, tindakan, hasil uji, serta perkembangan penting. Beri pengguna pembaruan yang relevan, terutama bila penanganan membutuhkan waktu atau informasi tambahan.
6. **Eskalasi bila diperlukan.** Jika perlu bantuan vendor, ikuti prosedur eskalasi provider dan catat referensi serta bukti komunikasi pada riwayat yang sesuai.
7. **Verifikasi pemulihan.** Uji layanan atau minta konfirmasi pengguna sesuai kondisi. Catat solusi dan bukti verifikasi sebelum mengubah tiket menjadi **Solved**.
8. **Tutup sesuai proses GLPI yang berlaku.** Pastikan klasifikasi, komunikasi, dan ringkasan penyelesaian dapat dipahami oleh petugas berikutnya.

### Prinsip pencatatan

- Gunakan riwayat tiket sebagai sumber informasi bersama: catat waktu, tindakan, hasil, komunikasi penting, dan alasan menunggu atau eskalasi.
- Assignment, balasan otomatis, dan respons teknis kepada pengguna adalah hal yang berbeda.
- Jangan menandai tiket **Solved** hanya karena alert Zabbix pulih. Recovery alert bukan bukti bahwa layanan telah diverifikasi.
- Jangan menyatakan gangguan selesai sebelum hasil pemulihan diuji atau dikonfirmasi.
- Jika beberapa tiket berkaitan, cantumkan referensi silang agar pemeriksaan dan pelaporan tidak kehilangan konteks.

### Alert Zabbix

Alert dengan tingkat High/Disaster dapat menjadi sumber tiket sesuai aturan monitoring yang dikonfigurasi. Tinjau layanan dan dampak alert, kaitkan dengan insiden yang sedang ditangani bila relevan, lalu catat hasil pemeriksaan di tiket. Perubahan status alert menjadi pulih **tidak otomatis** menyelesaikan tiket; teknisi tetap melakukan verifikasi dan memperbarui status tiket.

### Eskalasi ke provider

Eskalasi provider dilakukan jika masalah memerlukan tindakan pihak luar. Ikuti kanal pelaporan vendor yang berlaku, lalu catat sekurang-kurangnya nama provider, waktu pengalihan, referensi insiden provider bila tersedia, layanan/lokasi terkait, dan ringkasan bukti atau pemeriksaan. Saat layanan dilaporkan pulih, catat waktu serta hasil pengujiannya dan kembalikan penanganan tiket ke proses Helpdesk.

Pencatatan SLA provider adalah riwayat terpisah dari respons dan penyelesaian Helpdesk. Pada konfigurasi yang menggunakan plugin SLA Provider, status **Pending** dapat menjeda perhitungan SLA/OLA native GLPI, sedangkan timer provider berjalan terpisah. Karena itu, gunakan status dan pencatatan sesuai kebijakan operasional; jangan menganggap durasi provider sama dengan waktu penyelesaian layanan kepada pengguna.

## 5. Memahami Response Time, Resolution Time, dan SLA

- **Response Time**: waktu dari tiket dibuat hingga respons pertama teknisi kepada pengguna. Assignment dan auto-reply tidak dihitung sebagai respons teknisi.
- **Resolution Time**: waktu dari tiket dibuat hingga penanganan mencapai status **Solved**.
- **SLA**: target layanan yang disepakati sebagai acuan pengukuran dan evaluasi. Cara menghitung waktu kerja, jeda Pending, jam layanan, kalender, dan pengecualian harus ditetapkan dalam kebijakan resmi.

Contoh pada presentasi: tiket **High** dibuat pukul 09.00, mendapat respons IT pukul 09.45, dan **Solved** pukul 16.00. Dalam ilustrasi tersebut Response Time adalah 45 menit dan Resolution Time adalah 7 jam. Contoh ini tidak menetapkan batas waktu resmi.

### Target simulasi pada presentasi — bukan SLA resmi

| Prioritas | Target response simulasi | Target resolution simulasi |
|---|---:|---:|
| Major | 15 menit | 2 jam |
| Very High | 30 menit | 4 jam |
| High | 1 jam | 8 jam |
| Medium | 2 jam | 1 hari kerja |
| Low | 4 jam | 3 hari kerja |
| Very Low | 8 jam | 5 hari kerja |

Seluruh angka di tabel adalah **usulan/simulasi** yang perlu divalidasi terhadap baseline layanan dan disetujui sebelum dipakai sebagai target operasional. Satuan jam kerja atau jam kalender harus diperjelas dalam kebijakan resmi.

## 6. Monitoring dan evaluasi

Laporan berkala sebaiknya memeriksa volume tiket, Response SLA, Resolution SLA, tiket yang masih terbuka, tiket yang melewati target, serta hasil per prioritas. Evaluasi perlu menggunakan data dan definisi perhitungan yang konsisten, termasuk perlakuan terhadap Pending dan tiket yang menunggu provider.

Angka total tiket, persentase SLA, dan grafik pada slide presentasi hanya ilustrasi. Jangan menyajikannya sebagai hasil aktual. Dashboard KPI, rumus SLA, dan metrik beban teknisi juga dapat bergantung pada implementasi serta konfigurasi GLPI yang aktif; pastikan sumber dan kelengkapan data sebelum menerbitkan laporan.

## 7. Catatan penggunaan Request IT

Untuk permintaan email atau pemasangan Office 365 yang menggunakan plugin Request IT:

- Buat pengajuan melalui menu **Request IT** yang tersedia pada profil/portal GLPI, lalu pilih layanan dan isi informasi yang diminta.
- Ikuti alur persetujuan yang ditampilkan. Request Email melalui atasan langsung lalu direktur sebelum diteruskan ke IT; pemasangan Office 365 melalui atasan langsung lalu IT.
- Pantau status melalui GLPI. Notifikasi email belum tersedia pada implementasi yang dijelaskan dalam dokumentasi proyek.
- Untuk reset email, jangan mengisi password atau OTP pada pengajuan. IT memverifikasi identitas dan menyampaikan instruksi pemulihan melalui jalur aman.
- Persetujuan pengajuan bukan otomatisasi pembuatan/perubahan akun, pembelian lisensi, atau persetujuan anggaran.

Ketersediaan menu dan hak akses mengikuti konfigurasi GLPI, entity, dan plugin pada lingkungan yang digunakan. Jika menu atau layanan tidak tersedia, hubungi administrator/helpdesk; jangan mengirim pengajuan duplikat melalui kanal lain tanpa arahan.

## 8. Ringkasan cepat

**Pengguna:** laporkan melalui kanal resmi → jelaskan layanan, gejala, lokasi, waktu, dan dampak → simpan nomor tiket → bantu teknisi dengan informasi tambahan → verifikasi pemulihan.

**Tim IT:** catat tiket → tentukan dampak dan prioritas sesuai kebijakan → tetapkan PIC → respons teknis → tangani dan perbarui riwayat → eskalasi dengan bukti bila perlu → verifikasi → tandai **Solved** hanya setelah penyelesaian teruji.
