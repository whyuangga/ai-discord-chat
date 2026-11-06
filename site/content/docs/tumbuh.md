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
| **Pemilih server** | dropdown server di pojok atas (muncul otomatis bila bot ada di lebih dari satu server) — tanpa login, cukup token |
| **Status & pemakaian** | uptime, RAM, latensi, server/member, status Gemini, token masuk/keluar, cache hit, FAQ lokal |
| **Tren 7 hari** | grafik batang SVG (operasi AI & cache per hari) — dirender di server, tanpa JavaScript |
| **Peta fitur** | fitur apa yang sudah dipakai (panel, formulir, pengumuman, tautan, pemicu) + ✅/⬜ |
| **Kontrol Cepat** | 5 sakelar lama: level, ekonomi, pertumbuhan, anti-spam, anti-nuke |
| **Setelan server** | **48 setelan** dalam 5 grup (lihat tabel di bawah) |
| **Kirim pesan & embed** | kirim pengumuman sekali jalan, atau lewat **identitas webhook** (nama & avatar sendiri), lengkap dengan **pratinjau sebelum kirim** |
| **Banner & gambar** | **unggah banner** (PNG/JPG/GIF/WEBP) lalu pakai untuk banner panel atau gambar embed, tanpa perlu URL publik |
| **Buat konten** | pengumuman terjadwal, tautan embed `/l/<kode>`, panel menu (+ langsung terkirim), **formulir (modal)**, **pemicu saat member bergabung** |
| **Konten tersimpan** | daftar pengumuman/tautan/panel/formulir/webhook + tombol **Hapus** |
| **Riwayat perubahan** | 8 perubahan terakhir dari dashboard (siapa-waktu-nilai-hasil) |

### Setelan yang bisa diubah dari web (48 fitur)

| Grup | Fitur |
| :--- | :--- |
| 🧭 **Inti, level, & ekonomi** (8) | Level & XP, pengumuman naik level, channel pengumuman level, ekonomi koin, koin harian, pelacakan pertumbuhan, channel log pertumbuhan, prefix custom |
| 👋 **Sambutan & pamit** (6) | channel sambutan, sambutan via DM, kartu sambutan (mati/statis/dinamis), persona sambutan, channel pamit, channel ucapan boost |
| 🛡️ **Keamanan** (10) | mode anti-spam, deteksi huruf kapital, log anti-spam, aksi anti-nuke (+log), pengaman raid (+aksi), channel & role verifikasi, proteksi anti-phishing |
| 🎫 **Tiket & sapaan harian** (8) | sistem tiket, role staf, kategori, log, maksimal tiket terbuka, ping staf, rating tiket, channel ucapan ulang tahun |
| 🧩 **Konten & interaksi** (16) | starboard (+ambang bintang), kotak saran, Auto-Chat AI, koran pagi, galeri AI, rangkum YouTube, pencarian berita, terjemahan otomatis, statistik server, fakta harian, channel backup, gaya bahasa AI, keamanan konten AI, jam tenang, zona waktu |

Pilih nilai di dropdown → **Simpan**. Perubahan langsung tersimpan ke JSON bot (tanpa
restart), dan setiap perubahan dicatat di `data/dashboard_audit.json` (maksimal 300 entri).

### Kirim embed & webhook

Form **Kirim pesan & embed** menerima: channel, judul, isi, warna, footer, gambar,
label+URL tombol, serta **identitas webhook** (nama & avatar). Kalau kolom identitas diisi,
pesan dikirim lewat webhook channel itu sehingga nama pengirim bisa berbeda dari bot —
praktis untuk "📢 Pengumuman Server". Isi boleh memakai variabel pesan
(`{server.name}`, `{now_long}`) yang diisi otomatis saat dikirim.

### Pratinjau sebelum kirim (seperti Discohook)

Form kirim punya dua tombol: **👀 Pratinjau dulu** dan **Kirim sekarang**.

| Tombol | Yang terjadi |
| :--- | :--- |
| **Pratinjau dulu** | bot merender embed mirip Discord (judul, isi, warna, gambar, footer, identitas webhook) + daftar **peringatan** — **tidak ada yang dikirim** |
| **Kirim sekarang** | dari halaman pratinjau, isian diteruskan apa adanya ke channel tujuan |

Yang diperiksa saat pratinjau (semuanya muncul sebagai daftar “Perlu diperiksa”):

- channel tujuan belum dipilih / bot tidak punya akses,
- judul & isi masih kosong, atau melebihi batas Discord (256 / 4000 karakter),
- warna tidak valid (`#5865F2` atau nama seperti `blurple`),
- **variabel tidak dikenal** seperti `{member.nama}` (ditampilkan apa adanya, jadi kelihatan),
- URL gambar/tombol bukan `http(s)`, tombol hanya terisi label atau hanya URL,
- tombol link dipakai bersamaan dengan identitas webhook (tidak didukung).

Pratinjau juga tersedia sebagai JSON untuk otomasi: kirim `pratinjau: true` ke `POST /api/kirim`
dengan header `Content-Type: application/json`.

### Unggah banner & gambar

Banner bisa diunggah langsung dari HP — tidak perlu hosting gambar atau URL publik.

| Langkah | Detail |
| :--- | :--- |
| **1. Unggah** | Panel **🖼️ Banner & gambar** → pilih berkas → **Unggah banner**. Berkas disimpan di `data/uploads/`. |
| **2. Pakai** | Di form **Kirim pesan & embed** atau **Panel menu**, pilih berkas di kolom *Unggah banner* **atau** pilih dari dropdown *banner tersimpan*. |
| **3. Hasil** | Embed memakai `attachment://<nama>` sehingga gambar ikut terkirim; panel menyimpan URL lampirannya sebagai `banner_url`. |
| **4. Panel lama** | Di daftar **Panel** (bagian *Konten tersimpan*), setiap panel yang sudah terkirim punya tombol **Ganti banner** dan **Hapus banner** — pesan aslinya langsung disunting, tanpa kirim ulang. |
| **Bersih-bersih** | Setiap banner di galeri punya tombol **Hapus** (kuota 20 berkas per server). |

Batasan & pengamanan:

- Format: **PNG, JPG, GIF, WEBP**. Isi berkas diperiksa lewat *magic bytes*, jadi file `.exe`
  yang diganti nama jadi `.png` tetap ditolak.
- Ukuran: `DASHBOARD_UPLOAD_MB` (bawaan **8 MB**, maksimal 25 MB). Batas body server
  menyesuaikan nilai ini — bukan 1 MB bawaan aiohttp.
- Nama berkas selalu dibuat ulang (`<guild>_<waktu>_<acak>.<ext>`), jadi aman dari path
  traversal dan tabrakan nama. Pratinjau hanya bisa dibuka dengan token pemilik server.
- **Ganti banner panel lama tidak menghapus pesannya**: bot menyunting pesan panel yang
  sama (`message.edit`) dengan lampiran baru, lalu memperbarui `banner_url` di
  `data/menus.json`. Tombol/dropdown yang sudah ada tetap berfungsi karena view didaftarkan
  ulang. Kalau Discord menolak komponen V2 (mis. klien lama), bot otomatis memakai versi
  embed klasik dengan banner yang sama. Tombol **Hapus banner** menghapus lampiran lama
  tanpa menyentuh isi panel.

### Keamanan bertingkat

| Lapis | Jaminan |
| :--- | :--- |
| **Token** | semua endpoint baca & tulis wajib token (`?token=`, `X-Dashboard-Token`, `Bearer`, atau field tersembunyi pada form HTML) |
| **Whitelist aksi** | hanya 48 kunci di `dashboard_admin.FITUR` yang bisa dijalankan — kunci lain ditolak |
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
| `GET /api/tren?hari=7` | tren operasi AI & cache per hari (JSON) |
| `POST /api/aksi` | ubah setelan: `action=set.<kunci>` (token boleh lewat body form) |
| `POST /api/kirim` | kirim pesan/embed; field `channel, judul, isi, warna, footer, gambar, identitas, avatar`; tambahkan `pratinjau=1` untuk pratinjau tanpa kirim |
| `POST /api/konten` | `action=buat.pengumuman` / `buat.tautan` / `buat.panel` / `buat.formulir` / `buat.pemicu` / `jeda.pengumuman:<id>` / `hapus.<jenis>:<id>` / `banner.panel:<id>` / `hapusbanner.panel:<id>` |
| `POST /api/unggah` | `action=unggah.simpan` (multipart, field `banner`) / `hapus.banner:<nama>` |
| `GET /api/unggahan/<nama>?guild=<id>` | pratinjau banner tersimpan (wajib token) |
| `GET /healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

### Yang tetap lebih enak di Discord

Dashboard mengatur **setelan** dan **konten baru**, tetapi beberapa hal masih butuh
percakapan interaktif di Discord (karena perlu pratinjau langsung):

| Kebutuhan | Command |
| :--- | :--- |
| Menambah tombol/role/alur pada panel yang sudah ada | `/menu tombol-role`, `/menu tombol-link`, `/menu alur`, `/menu dropdown-role` |
| Menyegarkan panel setelah tombol ditambah dari Discord | `/menu ubah` |
| Mengundi (giveaway) — ambil pemenang, reroll | `/giveaway mulai`, `/giveaway pilih` |
| Panel tiket & tombol verifikasi | `/tiket panel`, `/verifikasi kirim` |
| Moderasi, musik, permainan, AI chat | perintah masing-masing (bukan setelan) |

> 💡 **Auto-refresh**: set `DASHBOARD_REFRESH_SEC=0` bila dashboard dipakai untuk mengisi
> form dari HP — tanpa auto-refresh, ketikan tidak ter-reset tiap 30 detik.
>
> ⚠️ Token dashboard berlaku **satu bot penuh** (bukan per server). Rahasiakan, dan ganti
> bila pernah ikut terlihat di tangkapan layar/percakapan.

### Menyalakan dashboard untuk instance sendiri (self-host)

Dashboard ini dirancang untuk **satu pemilik instance**, tanpa login OAuth — jadi setiap orang
yang memakai proyek ini menjalankan dashboard-nya sendiri dengan tokannya sendiri.

```bash
# 1. Buat token & tulis otomatis ke .env (buat DASHBOARD_PORT bila belum ada)
python tools/dashboard_token.py --tulis

# 2. Cek kesiapan konfigurasi (token, port, host, auto-refresh)
python tools/dashboard_token.py --periksa

# 3. Jalankan bot seperti biasa, lalu buka alamat yang dicetak
python main.py
```

| Langkah | Catatan |
| :--- | :--- |
| **Token** | 43 karakter acak, hanya huruf/angka/`_`/`-` → aman di `.env` dan URL |
| **Port** | di panel hosting biarkan `DASHBOARD_PORT=0`; di VPS/Termux isi angka (mis. `8080`) |
| **Alamat** | panel hosting: **IP node + port allocation** (bukan `0.0.0.0`) |
| **Akses** | `http://IP:PORT/?token=TOKEN` — atau lewat header `X-Dashboard-Token` |
| **Banyak server** | pakai dropdown **Server** di pojok atas halaman |
| **Keamanan** | `DASHBOARD_HOST=127.0.0.1` + SSH tunnel, atau Cloudflare Tunnel untuk HTTPS |
| **Nyaman mengetik** | `DASHBOARD_REFRESH_SEC=0` agar isian form tidak ter-reset |

> 💡 Karena tiap instance punya token sendiri, kamu **tidak perlu** membagikan token ke siapa pun.
> Pemakai lain menjalankan bot mereka sendiri dan membuat token mereka sendiri lewat perintah di atas.
