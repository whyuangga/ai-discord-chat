---
title: "N. Audit Log Server (/log)"
description: "Catatan pesan, member, role, dan channel beserta aksi moderasinya di satu channel log."
icon: "receipt_long"
weight: 14
toc: true
---

Mencatat aktivitas penting server ke **satu channel** — bukti saat moderasi, tanpa AI.

| Command *(Admin)* | Fungsi |
| :--- | :--- |
| **`/log channel channel:#bot-log`** | Pasang channel log & aktifkan audit log |
| **`/log status`** | Lihat channel, kategori aktif, & daftar channel dikecualikan |
| **`/log kategori nama:voice aktif:True`** | Nyalakan/matikan satu kategori |
| **`/log abaikan channel:#bot-spam`** | Kecualikan channel ramai dari pencatatan |
| **`/log matikan`** | Hentikan audit log server |

| Kategori | Isi | Default |
| :--- | :--- | :--- |
| `pesan` | pesan dihapus, diedit (sebelum → sesudah), hapus massal | ✅ aktif |
| `member` | member join (dengan umur akun), keluar, ganti nama panggilan | ✅ aktif |
| `role` | role member diberikan/dicabut, role dibuat/dihapus | ✅ aktif |
| `channel` | channel dibuat/dihapus | ✅ aktif |
| `voice` | masuk/keluar/pindah voice channel | ⛔ mati (paling ramai) |

- **Tanpa AI & tanpa simpan isi log ke disk** — hanya konfigurasi di `data/audit.json`.
- Isi pesan dipotong otomatis agar tetap di bawah batas embed Discord.
- Konfigurasi channel yang sudah dihapus dibersihkan otomatis.
