---
title: "J. Dashboard Web (DASHBOARD_TOKEN)"
description: "Dashboard web ringan di proses yang sama: pantau status dan kontrol fitur dari browser."
icon: "dashboard"
weight: 10
toc: true
---

Satu halaman web untuk memantau **dan** mengatur bot: status, pemakaian AI, papan level,
peta fitur, **48 setelan server**, **kirim embed/webhook**, dan pengelolaan konten.
Rincian tiap bagian ada di [Dashboard web (panel admin lengkap)](#dashboard-web-panel-admin-lengkap).

| Aspek | Detail |
| :--- | :--- |
| **Cara nyala** | Isi `DASHBOARD_TOKEN` (kata sandi acak) **dan** sediakan port (`DASHBOARD_PORT`, atau otomatis dari `SERVER_PORT`/`PORT` panel). Kosong = dashboard mati. |
| **Akses** | `http://<ip-server>:<port>/?token=<DASHBOARD_TOKEN>` — token juga bisa lewat header `X-Dashboard-Token` / `Authorization: Bearer` atau field tersembunyi pada form. |
| **Endpoint baca** | `/` (HTML), `/api/status`, `/api/pemakaian?guild=<id>`, `/api/level?guild=<id>`, `/api/kontrol?guild=<id>`, `/api/fitur?guild=<id>`, `/api/setelan?guild=<id>`, `/healthz` (tanpa token). |
| **Endpoint tulis** | Enam jalur `POST`, semuanya **wajib token**: `/api/aksi` (setelan), `/api/kirim` (pesan/embed/webhook + pratinjau), `/api/konten` (buat/hapus konten), `/api/unggah` (banner), `/api/tiket` (balas/tutup tiket, panel tiket), `/api/panel` (tombol/dropdown & verifikasi). Aksi lama (`level`, `ekonomi`, `tumbuh`, `antispam`, `antinuke`) tetap didukung. |
| **Endpoint unduh** | `/api/tren` (tren AI 7 hari) & `/api/ekspor?jenis=…` (CSV level/moderasi/tiket/pemakaian). |
| **Setelan** | **48 fitur** dalam 5 grup: inti/level/ekonomi, sambutan & pamit, keamanan, tiket & sapaan harian, konten & interaksi. |
| **Whitelist** | Hanya kunci yang terdaftar di `dashboard_admin.FITUR` yang bisa dijalankan — nama fungsi bebas tidak pernah dieksekusi. |
| **Mitigasi** | Halaman `/` tetap **GET-only** (POST ke `/` ditolak). Tidak ada `PUT`/`DELETE`/`PATCH`. Tombol Hapus hanya membuang satu item. Semua perubahan (berhasil maupun gagal) dicatat di `data/dashboard_audit.json` dan log bot. |
| **Unggahan** | Banner/gambar bisa diunggah dari dashboard (`DASHBOARD_UPLOAD_MB`, bawaan 8 MB) ke `data/uploads/` lalu dipakai sebagai banner panel, gambar embed, atau lampiran webhook. |
| **Biaya** | **0 kuota AI**, ±2–4 MB RAM, tanpa dependency baru (`aiohttp.web` sudah dipakai bot), tetap **1 proses**. |
| **Tanpa JS** | HTML dirender di server (semua form HTML biasa), `meta refresh` opsional (`DASHBOARD_REFRESH_SEC`, isi `0` untuk mematikan) → ringan dibuka dari HP. |

> ⚠️ Dashboard hanya bisa dibuka dari luar bila panel hosting memberi **port allocation**.
> Di Wispbyte cek tab **Network / Allocations**; bila tidak ada alokasi, dashboard otomatis
> tidak menyala dan bot tetap berjalan normal (tidak ada error).

## Dashboard web (panel admin lengkap)

Bot menjalankan satu halaman web di port privat (`DASHBOARD_PORT`, token di env) yang
memuat **status bot, pemakaian AI, papan level, peta fitur, dan pengaturan server** —
semua dari satu layar, **0 kuota AI**, tanpa dependency baru, tetap satu proses.

| Bagian | Isi |
| :--- | :--- |
| **Pemilih server** | dropdown server di pojok atas (muncul otomatis bila bot ada di lebih dari satu server) — tanpa login, cukup token |
| **Menu ☰ & navigasi** | header menempel di atas + menu anchor ke tiap panel; di HP menu berubah jadi **hamburger** (CSS murni, tanpa JavaScript) |
| **Status & pemakaian** | uptime, RAM, latensi, server/member, status Gemini, token masuk/keluar, cache hit, FAQ lokal |
| **Tren 7 hari** | grafik batang SVG (operasi AI & cache per hari) — dirender di server, tanpa JavaScript |
| **Peta fitur** | fitur apa yang sudah dipakai (panel, formulir, pengumuman, tautan, pemicu) + ✅/⬜ |
| **Kontrol Cepat** | sakelar level, ekonomi, & pertumbuhan dengan **tombol yang mengikuti keadaan** (“Nonaktifkan” saat aktif, “Aktifkan” saat mati) + mode anti-spam & aksi anti-nuke |
| **Setelan server** | **48 setelan** dalam 5 grup (lihat tabel di bawah) |
| **Kirim pesan & embed** | kirim pengumuman sekali jalan, atau lewat **identitas webhook** (nama & avatar sendiri), lengkap dengan **pratinjau sebelum kirim** |
| **Banner & gambar** | **unggah banner** (PNG/JPG/GIF/WEBP) lalu pakai untuk banner panel atau gambar embed, tanpa perlu URL publik |
| **Buat konten** | pengumuman terjadwal, tautan embed `/l/<kode>`, panel menu (+ langsung terkirim), **formulir (modal)**, **pemicu saat member bergabung** |
| **Konten tersimpan** | daftar pengumuman/tautan/panel/formulir/webhook + tombol **Hapus** |
| **Kotak masuk tiket** | daftar tiket aktif (umur, diam, status, SLA) + **balas** & **tutup** langsung dari web, plus **pasang panel tiket** |
| **Editor panel** | tambah/hapus **tombol** (role, tautan, perintah, alur, formulir) & **dropdown role** — panel di Discord langsung disegarkan |
| **Panel verifikasi** | pasang/matikan gerbang verifikasi (tombol sekali klik → role) tanpa command |
| **Ekspor CSV** | unduh data level, moderasi, tiket, & pemakaian AI langsung dari browser |
| **Riwayat perubahan** | 8 perubahan terakhir dari dashboard (siapa-waktu-nilai-hasil) |

### Navigasi dashboard (menu ☰ di HP)

Halaman dashboard itu panjang (status → setelan → kirim → tiket → panel → banner).
Supaya tidak perlu menggulir buta:

| Bagian | Perilaku |
| :--- | :--- |
| **Header menempel** | bar atas (`position: sticky`) selalu terlihat: nama bot, versi, waktu baca, & pemilih server |
| **Menu anchor** | baris tombol 📡 Status · 📊 Pemakaian · 📈 Tren · 🏆 Level · 🛠️ Setelan · ✉️ Kirim · ➕ Buat · 🎫 Tiket · 🧩 Panel · 🖼️ Banner · 📥 Ekspor · 🗂️ Konten · 🧾 Riwayat |
| **Hamburger di HP** | di layar ≤ 820 px menu dilipat jadi **☰ Menu**; buka/tutup lewat `<input type="checkbox">` + CSS, **tanpa JavaScript** (tetap bisa diakses keyboard) |
| **Lompatan rapi** | setiap panel punya `id` (`#p-setelan`, `#p-tiket`, …) dan `scroll-margin-top`, jadi judulnya tidak tertutup header |

### Setelah menekan Simpan

Form memakai pola **POST → redirect (303) → GET**: setelah menyimpan, kamu kembali ke
panel yang sama (`#p-…`) dan melihat kotak pesan ✅ berisi hasilnya — nilai barunya sudah
terbaca dari JSON, jadi tidak perlu klik “kembali” atau muat ulang. Kalau gagal, pesan ⚠️
dan alasannya tampil di halaman hasil dengan tautan kembali ke panel yang sama.
Endpoint JSON (`Content-Type: application/json`) tetap menerima `200`/`400` + `{"ok": …}`
tanpa redirect.

> 🐞 **Perbaikan**: saklar **Level & XP** dulu kembali ke “Aktif” setelah disimpan jadi
> “Nonaktif”, karena pembacaan setelan memakai `get_level_config()` yang membuat konfigurasi
> default (`enabled: True`) dan `set_level_config(aktif=False)` menghapus konfigurasi.
> Sekarang dashboard memakai `peek_level_config()` (baca tanpa membuat config) dan
> `set_level_enabled()` (menyimpan `enabled: False` tanpa menghapus setelan XP/channel/season).

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

### Kotak masuk tiket dari web

Panel **🎫 Kotak masuk tiket** menampilkan tiket yang belum selesai untuk server yang
sedang dipilih — jadi staf bisa menjawab tanpa membuka Discord di HP.

| Kolom | Arti |
| :--- | :--- |
| **#nomor** | nomor tiket (sama dengan nama thread `tiket-0001`) |
| **Status** | 🟢 terbuka · 🟡 diklaim (dengan ID staf) · ⏰ lewat SLA |
| **umur / diam** | sejak tiket dibuat / sejak pesan terakhir di thread |
| **Ringkasan** | jumlah aktif, diklaim, lewat SLA, dan rating rata-rata |

Setiap baris punya dua tombol:

| Tombol | Yang terjadi |
| :--- | :--- |
| **Balas** | kirim isi kolom teks ke thread tiket sebagai bot, atau sebagai **identitas webhook** bila kolom nama pengirim diisi (mis. “Tim Bantuan”). Respons staf pertama otomatis dicatat untuk hitungan SLA. |
| **Tutup** | tutup tiket: transkrip dibuat & dikirim ke channel log (bila diatur), thread dikunci + diarsipkan, status tersimpan di `data/tickets.json`. |

Tiket yang sudah selesai hilang dari daftar dan tidak bisa dibalas lagi — sama seperti
`/tiket tutup` di Discord.

Panel **Buat Tiket** juga bisa dipasang dari sini: buka
**🎟️ Pasang panel tiket (setara /tiket panel)** lalu pilih channel panel, role staf,
channel log transkrip, dan batas tiket per member. Tombol **Matikan sistem tiket**
menghentikan pembuatan tiket baru tanpa menghapus pesan panel lama. Member tetap membuka
tiketnya sendiri lewat tombol **Buat Tiket** di Discord — itu memang harus dari Discord.

### Formulir: kolom diisi lewat baris visual

Form **Buat formulir** sekarang menampilkan **5 baris kolom** siap pakai, bukan satu
kotak teks sintaks:

| Isian per baris | Fungsi |
| :--- | :--- |
| **Label kolom** | judul pertanyaan, mis. `Nama` |
| **pendek / paragraf** | `pendek` = satu baris, `paragraf` = jawaban panjang |
| **wajib** | centang = tidak boleh kosong |

Baris yang labelnya dikosongkan diabaikan. Mode lanjutan (`<details>`) tetap menyediakan
kolom teks bebas `Nama | Asal:panjang?` bagi yang lebih suka menulis sintaks — teks itu
hanya dipakai bila kelima baris visual kosong.

### Editor panel: tombol & dropdown tanpa Discord

Panel **🧩 Editor panel** memuat semua panel server beserta isinya, jadi aturan panel
tidak lagi harus lewat `/menu tombol-role`, `tombol-link`, `tombol-command`, `alur`, atau
`dropdown-role` di Discord.

| Bagian | Isi |
| :--- | :--- |
| **Isi panel** | daftar tombol (label · jenis · detail) lalu opsi dropdown, bernomor urut seperti tampil di Discord |
| **Hapus** | tombol **Hapus** per item — bisa juga lewat nomor urut, ID, atau label |
| **Tambah** | blok **➕ Tambah tombol / dropdown**: pilih *jenis* lalu isi kolom yang sesuai |

Jenis item yang bisa ditambah dari web:

| Jenis | Isian yang dipakai | Hasil |
| :--- | :--- | :--- |
| **peran** | Role, Label, Emoji, Gaya | tombol beri/cabut role (klik = dapat, klik lagi = lepas) |
| **tautan** | URL, Label, Emoji | tombol link (harus `http://` atau `https://`) |
| **perintah** | daftar perintah aman, Visibilitas | tombol yang menjalankan perintah info (`/serverstats`, `/level papan`, …) |
| **alur** | teks alur, mis. `+role:12 > pesan:Halo {member.mention}` | tombol yang menjalankan beberapa aksi sekaligus |
| **formulir** | daftar formulir | tombol yang membuka modal formulir |
| **dropdown** | Label (placeholder), Role 1–3, Eksklusif | satu dropdown role; *eksklusif* = hanya satu role boleh aktif |

Di bawah daftar panel ada blok **🛡️ Gerbang verifikasi** yang setara `/verifikasi pasang`:
pilih channel + role, isi catatan (opsional), lalu **Pasang panel verifikasi**. Statusnya
(aktif/nonaktif, channel, role) tampil di baris judul, dan tombol **Matikan verifikasi**
menghentikan pemberian role dari tombol lama.

Pengamanan editor panel sama dengan versi Discord: maksimal **5 tombol**, **5 dropdown**, **25 opsi**,
role harus **di bawah role bot** (dan bot punya *Manage Roles*), `@everyone`/role terkelola
ditolak, serta perintah berbahaya (`ban`, `purge`, `lockdown`, …) tidak ada di daftar.
Setelah ditambah/dihapus, panel yang sudah terkirim **langsung disunting** (`message.edit`)
sehingga tombol baru langsung bisa dipakai member.

### Ekspor CSV dari browser

Panel **📥 Ekspor CSV** menyediakan empat tombol unduh — sama dengan `/ekspor` di Discord,
tapi tanpa perlu menyimpan berkas dulu ke chat:

| Berkas | Isi |
| :--- | :--- |
| **📈 Level & XP** | peringkat member: level, XP, jumlah pesan, voice XP, prestige, aktivitas terakhir |
| **🛡️ Kasus moderasi** | semua kasus (aksi, alasan, durasi, moderator, waktu) — terbaru dulu |
| **🎟️ Tiket & rating** | nomor tiket, pemilik, status, waktu buka/tutup, respons pertama, rating |
| **📊 Pemakaian AI** | operasi AI & cache per hari |

CSV dibuat ulang setiap kali diunduh (tidak disimpan ke disk), memakai BOM UTF-8 supaya
angka & huruf non-ASCII tetap rapi di Excel, dan token tetap wajib — tautan unduhnya sudah
membawa token halaman.

### Keamanan bertingkat

| Lapis | Jaminan |
| :--- | :--- |
| **Token** | semua endpoint baca & tulis wajib token (`?token=`, `X-Dashboard-Token`, `Bearer`, atau field tersembunyi pada form HTML) |
| **Whitelist aksi** | hanya 48 kunci di `dashboard_admin.FITUR` yang bisa dijalankan — kunci lain ditolak |
| **Tanpa PUT/DELETE/PATCH** | hanya enam jalur tulis `POST`: `/api/aksi`, `/api/kirim`, `/api/konten`, `/api/unggah`, `/api/tiket`, `/api/panel` |
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
| `GET /api/tiket?guild=<id>` | daftar tiket aktif + statistik (JSON) |
| `POST /api/tiket` | `action=balas:<id>` (field `teks`, `identitas` opsional) / `action=tutup:<id>` / `action=panel` (field `channel`, `staff_role`, `log_channel`, `max_open`) / `action=matikan` |
| `GET /api/panel?guild=<id>` | daftar panel + tombol/dropdown-nya (JSON) |
| `POST /api/panel` | `action=tambah:<id panel>` (field `jenis`: `peran`/`tautan`/`perintah`/`alur`/`formulir`/`dropdown`) / `action=hapus:<id panel>:<ref item>` / `action=verifikasi` (field `channel`, `role`, `catatan`) / `action=verifikasi:matikan` |
| `GET /api/ekspor?jenis=<level\|moderasi\|tiket\|pemakaian>` | unduh CSV analitik server (wajib token) |
| `GET /healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

### Yang tetap lebih enak di Discord

Dashboard mengatur **setelan**, **konten**, **panel**, **tiket**, **verifikasi**, dan
**ekspor data**. Yang masih butuh percakapan interaktif di Discord:

| Kebutuhan | Command |
| :--- | :--- |
| Menyusun ulang teks panel (judul/deskripsi) setelah tombol ada | `/menu ubah` *(tombol & dropdown sudah bisa dari dashboard)* |
| Mengundi (giveaway) — ambil pemenang, reroll | `/giveaway mulai`, `/giveaway pilih` |
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
