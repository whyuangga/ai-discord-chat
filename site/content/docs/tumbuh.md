---
title: "P. Pertumbuhan Server & Invite Tracker (/tumbuh)"
description: "Ringkasan pertumbuhan server, invite tracker, dan retensi member baru."
icon: "trending_up"
weight: 16
toc: true
---

Menjawab pertanyaan "server ini tumbuh atau mati?" — **0 kuota AI**.

| Command | Fungsi |
| :--- | :--- |
| **`/tumbuh ringkas hari:7`** | Join, keluar, selisih bersih, **retensi %**, tren harian, & top pengundang |
| **`/tumbuh undang`** | Papan **Top Inviter** (termasuk berapa yang keluar & keluar cepat) |
| **`/tumbuh status`** | Status pelacakan + apakah bot bisa membaca daftar invite |
| **`/tumbuh atur`** *(Admin)* | Aktif/matikan pelacakan, channel log join-keluar, & mode lacak invite |
| **`/tumbuh sinkron`** *(Admin)* | Segarkan cache invite secara manual |

- **Cara deteksi pengundang:** bot menyimpan jumlah pemakaian tiap kode invite, lalu saat member join mencari kode yang `uses`-nya bertambah satu.
- Butuh izin **Manage Server** pada role bot. Tanpa izin itu, statistik join/keluar tetap jalan (hanya invite tracker yang dilewati) — bot tidak error.
- Data di `data/growth.json`: statistik harian **30 hari**, data member **90 hari**, maksimal 2000 member terlacak per server.
- **Tidak menyimpan isi pesan** sama sekali.
