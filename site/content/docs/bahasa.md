---
title: "T. Bahasa Antarmuka (/bahasa)"
description: "Antarmuka ID/EN untuk dialog konfirmasi, kata status, dan pesan izin (0 kuota AI)."
icon: "language"
weight: 20
toc: true
---

Bot berbicara **Bahasa Indonesia** secara bawaan, tapi teks **kerangka** bisa diganti ke English
per server. Semua terjemahan lokal — tidak memanggil AI sama sekali.

| Command | Fungsi |
| :--- | :--- |
| **`/bahasa lihat`** | Bahasa aktif, pilihan yang tersedia, & contoh teks yang ikut berubah. |
| **`/bahasa atur kode:id\|en`** *(Admin)* | Ganti bahasa server (per server, bukan per member). |

**Yang diterjemahkan (inti):** tombol & kartu **dialog konfirmasi** (`Ya, lanjutkan` / `Batal`,
`Dikonfirmasi` / `Dibatalkan`), kata **status umum** (`aktif` / `nonaktif`, `tersimpan`),
**pesan izin** (`Butuh izin Admin`), dan command `/bahasa` itu sendiri.

**Yang tetap Bahasa Indonesia:** seluruh penjelasan panjang fitur (`/bantuan`, README, pesan
panduan). Alasannya sederhana: menjaga konsistensi dokumentasi & menghemat RAM/berkas.
Bahasa disimpan di `data/i18n.json` (bahasa default tidak ditulis agar berkas tetap kecil).
