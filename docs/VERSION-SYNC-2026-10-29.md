# Penyamaan versi laptop dan Development Server — 29 Oktober 2026

Scope: source proyek IT-Helpdesk dan runtime yang digunakan di laptop/server 192.168.1.189. Baseline dipilih dari perubahan terbaru yang ditemukan di kedua lingkungan, bukan upgrade seluruh produk ke release publik terbaru.

## Baseline yang diperiksa

| Komponen | Laptop sebelum sinkronisasi | Server sebelum sinkronisasi | Baseline yang dipilih |
| --- | --- | --- | --- |
| Repository | `3733dac` + perubahan middleware/draft belum di-commit | `c7da2fd` + audit DB lokal | Satu commit baru berisi source gabungan dan draft |
| Middleware aktif | Image lama, belum memuat perubahan Oktober | Notifikasi status, perbaikan TLS dan guard sesi WAHA | Source middleware aktif server, disertai tes dan dokumentasi laptop |
| GLPI | 11.0.8 | 11.0.8 | 11.0.8, tanpa perubahan database |
| WAHA | 2026.7.2 | 2026.9.2 | 2026.9.2 dengan digest image server |
| AI Triage | Source sesuai laptop | Release `9ac9a91` | Source identik; tidak memerlukan rebuild server |

Digest WAHA: `sha256:280bdc8f860267a2488a45d00ec88529646f7468c0bf0283c595d6efdd1b5e3b`. Tag versi `2026.9.2` tidak tersedia di registry saat pemeriksaan, sehingga Compose memakai digest yang diverifikasi.

## Penggabungan perubahan

- Pertahankan middleware server yang memverifikasi TLS untuk panggilan GLPI dan menunggu sesi WAHA WORKING sebelum polling chat.
- Sertakan perubahan laptop: status notifier, greeting response, penggantian konteks tiket selesai, konfirmasi informasi lengkap, pagination follow-up, serta tes terkait.
- Tambahkan tes regresi agar sesi WAHA SCAN_QR_CODE/STOPPED/FAILED tidak memicu polling chat.
- Sertakan draft severity dan proses manual SLA provider sebagai dokumentasi. Draft ini belum mengubah konfigurasi SLA GLPI; integrasi Zabbix ditunda.

## Pemisahan lingkungan dan backup

- Server tetap menggunakan systemd pada `/home/glpiusr/wa-glpi`; laptop menggunakan Docker. Root Compose laptop tidak dijalankan di server.
- Environment, token, database, mapping tiket, cursor follow-up, serta sesi WAHA tetap milik masing-masing lingkungan.
- Backup server ditempatkan di direktori privat `/home/glpiusr/wa-glpi/backups/`, termasuk checkout lama dan snapshot state middleware.
- Backup laptop ditempatkan di direktori privat `~/.local/state/it-helpdesk/backups/`; container lama disimpan dalam kondisi stopped untuk rollback.
- Audit DB server yang dahulu tracked harus dibackup dan dipertahankan sebagai data ignored ketika checkout diperbarui. Spreadsheet Registration Asset tetap sebagai file pembanding lokal dan tidak dimasukkan ke commit atau dijadikan sumber sinkronisasi aset.

## Verifikasi

- Middleware gabungan: 33 tes lulus di laptop sebelum deployment.
- Setelah sinkronisasi, bandingkan commit repository dan hash source middleware aktif; cek GLPI/WAHA melalui versi aplikasi serta AI melalui source dan health endpoint.
- Gunakan pembacaan API untuk smoke check tanpa mengirim pesan uji WhatsApp atau membuat tiket uji.
- Catatan release runtime disimpan terpisah dari state bisnis dan tidak berisi credential.

## Rollback

Untuk laptop, hentikan container pengganti lalu kembalikan nama container lama dan jalankan dengan environment/volume lamanya. Bila format sesi/state berubah, gunakan snapshot backup setelah memastikan tidak ada proses yang masih menulis volume tersebut. Untuk source server, gunakan bundle/backup checkout dan backup runtime setempat; jangan mengganti environment dengan milik laptop.
