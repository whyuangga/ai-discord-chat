---
title: "H. Anti-Spam & Anti-Raid Ringan (/keamanan spam)"
linkTitle: "H. Anti-Spam & Anti-Raid Ringan"
weight: 8
---

> 🕊️ **Filosofi fitur ini: "lapor dulu, tindak belakangan".** Banyak bot moderasi merusak obrolan
> karena terlalu cepat menghapus atau menendang. Di sini **mode bawaan hanya melapor** ke channel log,
> dan seluruh staf selalu dikecualikan.

## 1. Command

| Command | Fungsi |
| :--- | :--- |
| **`/keamanan spam aktif:True`** | Nyalakan penjaga dalam **mode lapor** (aman, tanpa tindakan). |
| **`/keamanan spam mode:hapus log_channel:#mod-log`** | Hapus pesan spam + catat ke channel log. |
| **`/keamanan spam mode:timeout timeout_detik:600`** | Hapus + time-out member sementara (maks 1 hari). |
| **`/keamanan spam ambang_banjir:8 jendela:15`** | Sesuaikan sensitivitas flood. |
| **`/keamanan spam mention_maks:10 link_maks:5`** | Sesuaikan batas mention & link. |
| **`/keamanan spam kapital:True`** | Ikut menindak HURUF KAPITAL berlebihan (default nonaktif). |
| **`/keamanan spam kecualikan_channel:#ngobrol kecualikan_role:@Staf`** | Pengecualian permanen. |
| **`/keamanan spam-status`** | Lihat ambang, pengecualian, mode, & jumlah tindakan. |
| **`/keamanan spam aktif:False`** | Matikan total kapan saja. |

## 2. Yang dideteksi

| Pemicu | Ambang bawaan | Catatan |
| :--- | :--- | :--- |
| 🌊 **Banjir pesan** | 6 pesan / 10 detik | Per member per channel; tidak pernah lintas channel. |
| 🔁 **Pesan berulang** | isi sama 3x / 30 detik | Link dinormalisasi agar tidak lolos dengan variasi URL. |
| 📣 **Mention massal** | 6 mention dalam 1 pesan | Deteksi paling cepat & paling aman. |
| 🔗 **Link beruntun** | 4 link dalam 1 pesan, atau link sama 3x / 60 detik | Berguna untuk spam iklan. |
| 🔠 **Huruf kapital** | ≥70% kapital & ≥20 karakter | **Default NONAKTIF** (sering salah tuduh). |
| 🚨 **Raid (join)** | 8 join / 60 detik | **Hanya peringatan** ke channel log + saran tindakan. |

## 3. Pengamanan bawaan

- **Staf aman:** pemilik `Administrator`, `Manage Messages`, atau `Manage Guild` **tidak pernah** diperiksa.
- **Bot aman:** seluruh pesan bot lain diabaikan.
- **Satu laporan / 2 menit per member** agar channel log tidak dibanjiri (raid: 1 laporan / 4 menit).
- **Tidak ada ban otomatis.** Time-out hanya bila Admin memilih `mode:timeout`, maksimal 1 hari.
- **Tanpa AI & tanpa API eksternal** → 0 kuota Gemini, tetap ringan (state runtime dibersihkan tiap jam).

---
