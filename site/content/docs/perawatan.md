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

## X. Pembangun Server Instan (`/bangun`) & Meme Lokal (`/meme`)

## 🏗️ `/bangun` — 15 tema siap pakai + perancang AI

Terinspirasi **Instabot** (server langsung jadi dari tema) dan **purpleGPT** `/genserver`
(jelaskan server impian, AI menyusun strukturnya). **Tidak ada yang dibuat sebelum Admin
menekan tombol Terapkan.**

| Command | Fungsi |
| :--- | :--- |
| `/bangun tema tema:gaming` | Pratinjau struktur dari salah satu **15 tema** (gaming, komunitas, aesthetic, study, musik, seni, teknologi, crypto, anime, roleplay, bisnis, coding, kesehatan, keluarga, startup) — **0 kuota AI**. |
| `/bangun rancang deskripsi:…` | **AI (Gemini)** menyusun kategori, channel, & role dari deskripsi bebas → pratinjau. Bila AI gagal/ngawur, otomatis memakai tema terdekat. |
| `/bangun terapkan` | Terapkan rencana terakhir yang masih menunggu konfirmasi. |
| `/bangun riwayat` | Apa yang terakhir dibangun (jumlah role/kategori/channel). |
| `/bangun bongkar` | Hapus **hanya** item yang tercatat dibuat `/bangun` (rollback aman). |

Pengaman:

- Rencana divalidasi dulu: maks **8 kategori / 40 channel / 12 role**, nama ≤100 huruf, tipe
  channel harus salah satu yang didukung Discord.
- Eksekusi memakai mesin `backup_restore` yang sudah teruji: urutan **role → kategori → channel**,
  jeda anti rate-limit, **hanya menambah**, dan kegagalan satu item tidak menghentikan sisanya.
- AI tidak pernah menyentuh API Discord: ia hanya menghasilkan **JSON rencana**; kode bot yang
  membuat channel setelah konfirmasi.
- Riwayat tersimpan di `data/server_builder.json` sehingga `/bangun bongkar` tetap bisa dipakai
  setelah bot restart.

## 🖼️ `/meme` — meme lokal, 0 kuota AI, tanpa aset gambar

## 🎨 `/gambar` — buat & edit gambar dari slash command

Dari purpleGPT (`/draw` & `/edit`). `/gambar buat prompt:… rasio:… gaya:…` membuat gambar baru
(**5 rasio aspek**, belasan gaya), `/gambar edit prompt:…` mengubah lampiran gambar **atau
otomatis memakai gambar terakhir** di channel itu (tanpa unggah ulang), dan `/gambar pilihan`
menampilkan semua rasio & gaya. Kuota AI tetap dihitung seperti chat, dengan jeda 20 detik per
pengguna agar tidak membanjiri API. Gaya/rasio per panggilan **tidak mengubah setelan channel**.

## 📦 `/dataku` & `/hapusdataku` — privasi mandiri

Dari janji purpleGPT *"export or delete your data anytime"*. `/dataku` mengirim lampiran **JSON**
berisi level/XP, koin, lencana, kata kunci pantau, ulang tahun, skor game, dan kiriman formulir
milikmu. `/hapusdataku` menampilkan tombol konfirmasi lalu menghapus permanen data itu dari
`data/*.json` (hanya milikmu — data member lain tidak tersentuh) dan langsung menyimpannya ke disk.

## ⚙️ `/setelan-ai` — gaya AI per member + kepribadian AI server

Dari purpleGPT (`/settings` & `/server_prompt`), tanpa biaya tambahan: instruksi hanya berupa
**teks tambahan** pada prompt AI, jadi kuota tetap sama dan model tidak berubah.

- **Per member** (`/setelan-ai atur`): **panjang jawaban** (`singkat` maks 3 kalimat / `normal` /
  `detail` poin + contoh), **prompt pribadi** (maks 300 huruf, mis. *"pakai analogi sederhana"*),
  dan **rasio gambar bawaan** untuk `/gambar`.
- **Per server** (`/setelan-ai prompt-server`, khusus Admin): satu "kepribadian" yang ditempelkan
  ke semua balasan AI di server itu (maks 500 huruf; kosongkan untuk menghapus).
- `/setelan-ai lihat` menampilkan semua setelan yang sedang berlaku, `/setelan-ai reset`
  mengembalikan ke bawaan. Data disimpan di `data/ai_settings.json`.

## 🖼️ `/meme teks_atas:"…" teks_bawah:"…" template:neon` menggambar meme sendiri dengan **Pillow**
(tidak ada API gambar & tidak ada berkas aset): 6 gaya — `klasik`, `impact`, `drake` (dua panel
ditolak/diterima), `neon`, `kertas`, `terminal`. Teks otomatis dibungkus (maks 6 baris × 120 huruf)
dan hasilnya dikirim sebagai PNG 800×800.
