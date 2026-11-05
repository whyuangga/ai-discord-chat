---
title: "O. Ekonomi Koin (/ekonomi)"
description: "Koin harian, toko role, transfer, dan papan peringkat — semua lokal tanpa kuota AI."
icon: "paid"
weight: 15
toc: true
---

Gamifikasi ringan supaya member betah — **0 kuota AI**, semua hitungan lokal.

| Command | Fungsi |
| :--- | :--- |
| **`/ekonomi saldo [member]`** | Saldo koin, peringkat, & status hadiah harian |
| **`/ekonomi harian`** | Klaim hadiah harian (bonus **streak** sampai +70%) |
| **`/ekonomi papan`** | Papan peringkat member paling kaya + total koin beredar |
| **`/ekonomi toko`** | Daftar item yang bisa dibeli |
| **`/ekonomi beli item:<nama>`** | Beli item → role otomatis diberikan |
| **`/ekonomi transfer member:@X jumlah:50`** | Kirim koin (minimal 10, ada jeda anti-spam) |
| **`/ekonomi atur`** *(Admin)* | Aktifkan & atur koin/pesan, jeda, koin/voice, hadiah harian, nama mata uang |
| **`/ekonomi tambah-item` / `hapus-item`** *(Admin)* | Kelola toko (maks 20 item: nama, harga, role, deskripsi) |

- **Default NONAKTIF** (`/ekonomi atur aktif:True`) agar server yang tidak butuh tidak terbebani.
- Koin otomatis didapat dari pesan (dengan jeda) & menit di voice channel — memakai pelacakan voice yang sama dengan XP Voice.
- Data di `data/economy.json`, maksimal **500 saldo teratas per server** agar file tetap kecil.
