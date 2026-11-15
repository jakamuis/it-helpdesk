# Project Guidelines

- **Asset Data Source of Truth:** The absolute source of truth for asset data is the "Datasheet" (e.g. Google Sheets DATABASE INVENTARIS). Files like "Registration Asset" (Excel) are strictly for comparison purposes only. Do NOT add new assets or sync data from "Registration Asset".

## Zabbix → GLPI: aturan wajib severity

- Hanya problem Zabbix dengan severity **High (4)** atau **Disaster (5)** yang boleh dibuatkan tiket GLPI.
- Aturan ini berlaku untuk action otomatis, pengujian memakai problem nyata, impor manual, backfill, dan permintaan ekspor problem ke GLPI.
- Permintaan seperti "semua problem", "export ke GLPI", atau "problem yang masih aktif" tetap berarti semua problem yang memenuhi filter **High + Disaster**, kecuali pengguna secara eksplisit meminta perubahan cakupan severity.
- Jangan membuat tiket dari **Not classified, Information, Warning, atau Average**. Jangan memperluas cakupan hanya karena tidak disebut ulang pada pesan terbaru.
- Untuk impor problem aktif, ambil hanya problem yang belum pulih, terapkan filter severity sebelum membuat tiket, dan periksa tiket yang sudah ada agar tidak duplikat. **Satu event Zabbix = satu tiket GLPI**.
- Sebelum pemrosesan massal, sampaikan jumlah problem yang memenuhi filter beserta rincian severity. Setelah selesai, verifikasi jumlah tiket dan severity hasilnya.
- Konfigurasi produksi: action `GLPI Tickets - High and Disaster` memakai kondisi **severity >= High**; media penerima hanya mengizinkan High dan Disaster (severity mask `48`). Pertahankan filter ini pada perubahan berikutnya.
- Koreksi 29 Oktober 2026: 199 tiket severity di bawah High dari impor yang keliru telah dipindahkan ke Trash. Jangan memulihkan atau mengimpor ulang tiket tersebut tanpa instruksi eksplisit pengguna yang mengubah cakupan severity.
