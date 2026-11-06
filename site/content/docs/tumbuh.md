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

## Dashboard web (panel admin lengkap)

Bot menjalankan satu halaman web di port privat (`DASHBOARD_PORT`, token di env) yang
memuat **status bot, pemakaian AI, papan level, peta fitur, dan pengaturan server** —
semua dari satu layar, **0 kuota AI**, tanpa dependency baru, tetap satu proses.

| Bagian | Isi |
| :--- | :--- |
| **Status & pemakaian** | uptime, RAM, latensi, server/member, status Gemini, token masuk/keluar, cache hit, FAQ lokal |
| **Peta fitur** | fitur apa yang sudah dipakai (panel, formulir, pengumuman, tautan, pemicu) + ✅/⬜ |
| **Kontrol Cepat** | 5 sakelar lama: level, ekonomi, pertumbuhan, anti-spam, anti-nuke |
| **Setelan server** | **39 setelan** dalam 5 grup (lihat tabel di bawah) |
| **Kirim pesan & embed** | kirim pengumuman sekali jalan, atau lewat **identitas webhook** (nama & avatar sendiri) |
| **Buat konten** | pengumuman terjadwal, tautan embed `/l/<kode>`, panel menu (+ langsung terkirim) |
| **Konten tersimpan** | daftar pengumuman/tautan/panel/formulir/webhook + tombol **Hapus** |
| **Riwayat perubahan** | 8 perubahan terakhir dari dashboard (siapa-waktu-nilai-hasil) |

### Setelan yang bisa diubah dari web (39 fitur)

| Grup | Fitur |
| :--- | :--- |
| 🧭 **Inti, level, & ekonomi** (8) | Level & XP, pengumuman naik level, channel pengumuman level, ekonomi koin, koin harian, pelacakan pertumbuhan, channel log pertumbuhan, prefix custom |
| 👋 **Sambutan & pamit** (5) | channel sambutan, sambutan via DM, kartu sambutan (mati/statis/dinamis), channel pamit, channel ucapan boost |
| 🛡️ **Keamanan** (9) | mode anti-spam (+log), aksi anti-nuke (+log), pengaman raid (+aksi), channel & role verifikasi, proteksi anti-phishing |
| 🎫 **Tiket & sapaan harian** (6) | sistem tiket, role staf, kategori, log, maksimal tiket terbuka, channel ucapan ulang tahun |
| 🧩 **Konten & interaksi** (11) | starboard, kotak saran, Auto-Chat AI, koran pagi, galeri AI, rangkum YouTube, pencarian berita, terjemahan otomatis, statistik server, fakta harian, channel backup |

Pilih nilai di dropdown → **Simpan**. Perubahan langsung tersimpan ke JSON bot (tanpa
restart), dan setiap perubahan dicatat di `data/dashboard_audit.json` (maksimal 300 entri).

### Kirim embed & webhook

Form **Kirim pesan & embed** menerima: channel, judul, isi, warna, footer, gambar,
label+URL tombol, serta **identitas webhook** (nama & avatar). Kalau kolom identitas diisi,
pesan dikirim lewat webhook channel itu sehingga nama pengirim bisa berbeda dari bot —
praktis untuk "📢 Pengumuman Server". Isi boleh memakai variabel pesan
(`{server.name}`, `{now_long}`) yang diisi otomatis saat dikirim.

### Keamanan bertingkat

| Lapis | Jaminan |
| :--- | :--- |
| **Token** | semua endpoint baca & tulis wajib token (`?token=`, `X-Dashboard-Token`, `Bearer`, atau field tersembunyi pada form HTML) |
| **Whitelist aksi** | hanya 39 kunci di `dashboard_admin.FITUR` yang bisa dijalankan — kunci lain ditolak |
| **Tanpa PUT/DELETE/PATCH** | hanya tiga jalur tulis `POST`: `/api/aksi`, `/api/kirim`, `/api/konten` |
| **Tanpa hapus data massal** | tombol Hapus hanya membuang satu item (pesan lama di Discord tidak ikut terhapus) |
| **Jejak audit** | setiap perubahan (termasuk yang gagal) dicatat waktu, kunci, nilai, dan pesannya |
| **Bind privat** | default `DASHBOARD_HOST=0.0.0.0`, bisa diubah ke `127.0.0.1` + tunnel SSH |

### Endpoint

| Endpoint | Isi |
| :--- | :--- |
| `GET /` | halaman HTML lengkap (butuh token) |
| `GET /api/status` · `/api/pemakaian` · `/api/level` · `/api/kontrol` · `/api/fitur` | data JSON |
| `GET /api/setelan` | semua nilai setelan + ringkasan grup + riwayat |
| `POST /api/aksi` | ubah setelan: `action=set.<kunci>` (token boleh lewat body form) |
| `POST /api/kirim` | kirim pesan/embed; field `channel, judul, isi, warna, footer, gambar, identitas, avatar` |
| `POST /api/konten` | `action=buat.pengumuman` / `buat.tautan` / `buat.panel` / `hapus.<jenis>:<id>` |
| `GET /healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

> 💡 **Auto-refresh**: set `DASHBOARD_REFRESH_SEC=0` bila dashboard dipakai untuk mengisi
> form dari HP — tanpa auto-refresh, ketikan tidak ter-reset tiap 30 detik.
>
> ⚠️ Token dashboard berlaku **satu bot penuh** (bukan per server). Rahasiakan, dan ganti
> bila pernah ikut terlihat di tangkapan layar/percakapan.
