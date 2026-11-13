# Rancangan Request IT — sesuai form manual

Diperbarui: 13 November 2026. Rancangan awal yang mencakup lima kategori umum diganti dengan dua kebutuhan berikut. Implementasi lokal: plugin `itrequest` 0.2.0, GLPI 11.0.8.

## Jenis dan alur

| Jenis | Alur |
|---|---|
| Request Email | Requestor → Atasan Langsung (Mengetahui) → Direktur (Menyetujui) → IT |
| Pemasangan Office 365 | Requestor → Atasan Langsung → IT |

Request merupakan objek terpisah dari tiket. Approval pada aplikasi adalah pencatatan keputusan akun yang login, lengkap dengan nama, tahap, waktu, catatan dan versi pengajuan; bukan gambar tanda tangan atau sertifikat tanda tangan elektronik.

## Identitas dan isi form

Requestor otomatis dari akun login, dipisahkan dari nama pengguna fasilitas yang bisa diwakilkan. Identitas pengguna meliputi nama, NIK, bagian/departemen, jabatan, cabang/lokasi dan perusahaan/beban biaya. Nomor request dan waktu pengajuan dicatat sistem. Nomor dokumen pada foto contoh tidak disalin sebagai nomor tetap untuk setiap request.

### Request Email

| Layanan | Detail wajib |
|---|---|
| Email baru | Usulan alamat email lengkap dengan domain |
| Reset / ubah password | Alamat email saat ini |
| Ubah alamat email | Alamat lama dan usulan alamat baru yang berbeda |
| Hapus alamat email | Alamat email yang dihapus |

Semua layanan email mengikuti alur atasan → direktur → IT sesuai form manual. Reset password dalam modul ini hanya pengajuan; IT tetap memverifikasi identitas dan menyerahkan link pemulihan/kredensial lewat jalur aman. Password dan OTP tidak diminta atau ditulis pada request. Tidak ada otomatisasi reset, pembuatan, perubahan atau penghapusan akun.

### Pemasangan Office 365

Email perusahaan pengguna, hostname/nomor aset perangkat tujuan, serta aplikasi yang dibutuhkan. IT memeriksa lisensi dan kelayakan perangkat sebelum pemasangan. Persetujuan bukan pembelian lisensi atau persetujuan anggaran otomatis.

### Bersama

Judul, keterangan/alasan, tanggal dibutuhkan, lampiran opsional PDF/JPG/PNG maksimum 10 MB per file. Seluruh identitas dan detail sesuai jenis wajib lengkap saat dikirim; draft boleh belum lengkap.

Pernyataan wajib disetujui sebelum pengiriman:

> Fasilitas di atas hanya dipergunakan untuk keperluan dan kepentingan perusahaan serta menunjang aktivitas kerja. Tidak diperkenankan untuk meneruskan (forward) email perusahaan ke alamat email pribadi.

Teks pernyataan, akun yang menyetujui, snapshot isi dan waktu pengiriman disimpan dalam riwayat.

## Approval dan hak akses

- Admin memetakan pemohon → atasan → direktur per entity. Satu direktur yang sama dapat dipilih pada banyak pemohon; tidak ada nama direktur yang ditetapkan dari foto contoh.
- Direktur wajib untuk Email; boleh kosong untuk Office. Email tidak dapat dikirim tanpa kedua approver aktif.
- Pemohon, atasan dan direktur pada pengajuan Email harus akun berbeda. User tidak dapat menyetujui request sendiri.
- Approver disimpan saat pengiriman. Perubahan pemetaan tidak mengubah pengajuan berjalan secara diam-diam.
- Atasan melihat dan bertindak pada antrean atasan. Direktur mendapat antrean setelah atasan mengetahui. Atasan tidak dapat mengambil keputusan tahap direktur.
- IT baru mendapat akses pekerjaan sesudah persetujuan akhir. Penolakan sebelum persetujuan akhir tidak membuka request kepada IT biasa.
- Admin dapat mengalihkan approver pada tahap aktif dengan alasan dan riwayat. Ini tidak memberi hak menyetujui atas nama orang lain.
- Penolakan dan revisi wajib alasan; keduanya dapat dilakukan di tahap atasan maupun direktur.
- Revisi dikirim ulang mulai dari atasan dan membatalkan penggunaan approval sebelumnya. Perubahan lingkup setelah disetujui juga perlu approval ulang; IT mengembalikan ke revisi jika sudah diproses.
- Setiap keputusan memeriksa hak akses, tahap aktif dan versi terbaru. Pembatasan entity aktif berlaku pada detail, antrean dan unduhan.

## Status dan penanganan

Draft → Menunggu Atasan Langsung → [Menunggu Persetujuan Direktur, khusus Email] → Menunggu IT → Diproses → Selesai.

Status tambahan: Perlu Revisi, Menunggu Kelengkapan, Ditolak dan Dibatalkan. IT mengambil pekerjaan sebagai PIC, menetapkan target selesai, meminta kelengkapan bila perlu, dan mengisi hasil wajib sebelum selesai. Tidak ada perubahan inventaris otomatis. Pemohon dapat membatalkan sebelum diproses; sesudahnya koordinasi melalui IT.

## Email notifikasi

SMTP dan integrasi notifikasi belum tersedia. Saat ini pemohon/approver/IT memantau melalui halaman GLPI. Tahap berikutnya: SMTP, template untuk tiap tahap, penerima atasan/direktur, antrean dan retry. Tidak ada email yang dikirim oleh plugin saat ini.

## Verifikasi dan batas saat ini

Pengujian mencakup kedua alur, pencegahan melewati direktur, validasi field kondisional dan pernyataan, revisi dari direktur yang kembali ke atasan, pengalihan approver, penolakan, pembatasan entity/aktor, stale decision, upload/download dan jumlah Ticket GLPI tetap.

Implementasi sudah di lokal, belum di server. Identitas/lokasi masih diisi manual, belum ditarik dari direktori karyawan. Belum ada reminder, delegasi otomatis periode cuti, approval anggaran atau catatan internal terpisah. Request lama tidak dihapus; draft lama perlu memilih layanan baru sebelum dikirim ulang.
