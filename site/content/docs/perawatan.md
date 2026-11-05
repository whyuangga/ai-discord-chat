---
title: "W. Audit RAM & Cache (/perawatan memori)"
description: "Audit RAM, ukuran folder data, cache terbesar beserta batasnya, dan saran otomatis."
icon: "memory"
weight: 23
toc: true
---

Free Tier itu soal **RAM**, jadi bot bisa melaporkan angka nyata dari hosting yang sedang
dipakainya sendiri: `/perawatan memori` *(semua member boleh, jawabannya ephemeral).*

Hasil pengukuran di mesin uji (Python 3.11, tanpa guild aktif):

| Komponen | RAM |
| :--- | :--- |
| Python kosong | ±8.9 MB |
| `discord.py` + `aiohttp` (impor wajib) | ±43.3 MB |
| `wavelink` (klien musik) | ±+0.9 MB |
| `Pillow` (dimuat hanya saat kartu gambar dipakai) | ±+1.7 MB |
| **Bot ini saat diam (import `main`)** | **±53 MB** |
| Beban data ekstrem (5 server × 500 member level + 1000 tiket + 1000 kasus + playlist) | ±+3–4 MB |

**Artinya:** biaya terbesarnya adalah pustaka Discord itu sendiri (±43 MB), bukan fitur kita.
Fitur-fitur baru (raid, playlist, rating tiket, musim, i18n, prefix, ekspor) menambah
**hitungan byte**, bukan megabyte.

**Batas per cache** (semua dipangkas otomatis oleh watcher yang sudah ada):

| Cache | Batas |
| :--- | :--- |
| XP & level | 500 member / server (yang XP-nya tertinggi) |
| Tiket | 200 tiket selesai total |
| Kasus moderasi | 200 kasus / server |
| Riwayat anti-nuke | 20 kejadian / server |
| Playlist musik | 500 lagu / server • 5 playlist × 50 lagu per member |
| Sesi chat/gambar | kedaluwarsa `SESSION_EXPIRE_DAYS` |
| Cache bahasa/prefix/ekspor | 1 entri kecil per server, entri kosong dibuang |

Laporan `/perawatan memori` menampilkan: RAM proses, ukuran `data/`, 6 cache terbesar beserta
batasnya, 5 berkas `data/` terbesar, dan **saran otomatis** (mis. matikan gambar dinamis bila
RAM sudah >200 MB, atau minta member merapikan playlist bila >2000 lagu).
