---
title: "E. Fitur Komunitas Ringan (/panel-role, /poll, /saran, /embed, /tempvoice)"
description: "Reaction role, polling, pengingat, starboard, verifikasi, sticky, temp voice, kotak saran."
icon: "groups"
weight: 5
toc: true
---

> 💡 Semua fitur di bagian ini **tidak memanggil Gemini sama sekali** (0 kuota, 0 biaya) dan **default NONAKTIF**.
> Server yang belum memakai fitur ini tidak mendapat beban tambahan apa pun (tanpa event listener berat, tanpa RAM ekstra).

## 1. 🎭 Reaction Role — Member Ambil Role Sendiri (`/panel-role`)
- **`/panel-role pasang channel:#ambil-role judul:Ambil Role role1:@Gamer emoji1:🎮 role2:@Artist emoji2:🎨`** — bot mengirim panel embed lalu memasang reaksi emoji secara otomatis (maks **3 role sekali pasang**).
- Warga cukup **klik emoji** untuk mendapatkan role, **klik lagi** untuk melepasnya. Tidak ada kuota, tidak ada tombol kedaluwarsa.
- **`/panel-role tambah pesan:<ID/link> emoji:🎵 role:@Musik`** — tambah role ke panel yang sudah ada.
- **`/panel-role hapus`**, **`/panel-role daftar`** — kelola & lihat semua panel.
- Posisi role diperiksa otomatis: role di atas role bot dilewati dengan peringatan jelas.

## 2. 📊 Polling Native Discord (`/poll`)
- **`/poll pertanyaan:"Mabar malam ini jam berapa?" opsi:"Jam 8, Jam 9, Jam 10" durasi_jam:24`**
- Memakai **Poll bawaan Discord**: hitung suara real-time, tampilan rapi, tidak bisa di-*double vote* — tanpa beban server sama sekali.
- Mendukung **multi-pilihan** (`multi:True`), **anonim/terbuka** (`anonim:True`), dan durasi **1–768 jam** (maks 32 hari).
- Maksimal **10 pilihan** (batas Discord); lebih dari itu dipotong otomatis dengan pemberitahuan.

## 3. ⏰ Pengingat Pribadi Tahan Restart (`/ingatkan`)
- **`/ingatkan pasang waktu:"2j" pesan:"Rapat pengurus"`** — bot menagih kamu saat waktunya tiba (di channel atau DM bila channel tak bisa diakses).
- Format waktu fleksibel: `10m`, `2j`, `1j30m`, `2 hari`, `45` (menit), bahkan `1 jam dan 15 menit`. Maksimal **365 hari**.
- **Tahan restart:** pengingat disimpan di `data/community_tools.json`, jadi tetap dikirim walau bot baru di-*restart*.
- **`/ingatkan daftar`** & **`/ingatkan batal nomor:3`** — kelola pengingat aktif (maks 15 per member).

## 4. ⭐ Starboard — Sorotan Pesan Populer (`/starboard`)
- **`/starboard atur channel:#starboard batas:3 emoji:⭐`** — pesan warga yang mendapat **3 reaksi bintang** otomatis disalin ke channel sorotan (embed cantik + tautan sumber).
- Bila reaksi turun di bawah batas, sorotannya **otomatis dihapus** agar starboard tetap rapi.
- Pesan bot dilewati, emoji bisa diganti bebas (`🔥`, `❤️`, dll.), dan **`/starboard status`** menampilkan konfigurasi + jumlah sorotan.

## 5. ✅ Gerbang Verifikasi Anti-Bot (`/verifikasi`)
- **`/verifikasi pasang channel:#verifikasi role:@Member`** — panel dengan tombol **✅ Verifikasi Saya**.
- Member baru klik sekali → langsung dapat role akses, tanpa perlu Admin menunggu. Cocok dipadukan dengan `/autorole`.
- **`/verifikasi status`** & **`/verifikasi matikan`** — pantau / matikan kapan saja.
- Tombol bersifat **persisten** (`custom_id`), jadi tetap berfungsi setelah bot restart.

## 6. 📌 Sticky Message — Petunjuk Selalu di Bawah (`/sticky`)
- **`/sticky pasang isi:"Baca #rules dulu sebelum chat!" channel:#umum judul:"📌 Aturan"`**
- Setiap ada obrolan baru, bot menurunkan ulang pesan petunjuk ke bawah channel (pesan lama dihapus).
- **Anti-spam:** jeda minimum **5 detik** per channel (`STICKY_MIN_INTERVAL_SEC`), jadi channel ramai tidak dibanjiri bot.
- **`/sticky lepas`** & **`/sticky status`** — cabut / lihat daftar channel sticky.

## 7. 👤 Kartu Profil & Server (`/info`)
- **`/info user member:@Warga`** — umur akun, tanggal bergabung, jumlah role, plus **peringatan keamanan** otomatis jika akun masih **< 7 hari** (indikasi akun raid).
- **`/info server`** — total member (manusia vs bot), online, boost, jumlah channel, status verifikasi & auto role, pemilik, dan tanggal server dibuat.

## 8. 🗂️ Perawatan: Backup Otomatis & Log Error (`/perawatan`)
- **`/perawatan atur backup_channel:#bot-backup log_channel:#bot-log`** — backup konfigurasi otomatis tiap **7 hari** (`BACKUP_INTERVAL_DAYS`) & laporan error masuk ke channel.
- **`/perawatan backup`** — kirim berkas ZIP berisi seluruh `data/*.json` saat itu juga (penyelamat saat Wispbyte rebuild bersih).
- **`/perawatan status`** — channel backup/log, waktu backup terakhir, ukuran arsip, & RAM bot.
- Error Slash Command maupun error event otomatis diringkas ke channel log (tanpa membocorkan API key — sudah disanitasi) dan jejaknya tampil di **`/status`**.

## 9. 💡 Kotak Saran (`/saran`) & 📝 Pembuat Embed (`/embed`)

**Kotak saran** — ala Carl-bot, tapi tanpa dashboard:

| Command | Siapa | Fungsi |
| :--- | :--- | :--- |
| `/saran pasang channel:#saran` | Admin | Tentukan channel kotak saran (`nonaktifkan:True` untuk mematikan) |
| `/saran kirim teks:...` | Semua | Kirim usulan → muncul sebagai embed dengan tombol **👍 / 👎** |
| `/saran daftar status:baru` | Semua | Lihat saran terbaru + skor voting |
| `/saran status id:3 status:diterima` | Staff | Ubah status (pesan asli ikut berubah) + memberi tahu pengusul |
| `/saran hapus id:3` | Admin | Hapus saran beserta pesannya |

- **Satu member satu suara**; memilih sisi lain akan **memindahkan** suara, bukan menambah.
- Tombol **tahan restart** (persistent view) — voting tetap jalan setelah bot restart.
- Status: 🆕 baru · 🛠️ dikerjakan · ✅ diterima · ❌ ditolak. Maks 20 saran tersimpan per server.

**Pembuat embed** — pengumuman cantik tanpa perlu tahu format:

| Command | Fungsi |
| :--- | :--- |
| `/embed buat channel:#pengumuman warna:ungu` | Buka **formulir** (judul, isi, URL banner, footer) → langsung terkirim |
| `/embed cepat channel:#x judul:"..." isi:"..."` | Kirim cepat tanpa formulir |

Warna menerima `#9B59B6`, `ungu`, `biru`, `merah`, `hijau`, `emas`, `abu`. Hanya **staff** (Manage Messages/Server) yang bisa mengirim.

## 10. 🔊 Temp Voice: Voice Room Sementara (`/tempvoice`)

Cukup satu voice channel sebagai "tombol" pembuat room — konsep sama dengan ProBot/YAGPDB.

**Pemasangan (1 menit):**
1. Buat voice channel baru, misal **➕ Buat Voice**, di kategori yang kamu mau.
2. Jalankan `/tempvoice atur hub:#➕ Buat Voice`.
3. Selesai — member yang masuk ke channel itu langsung dipindahkan ke room pribadinya.

| Command | Siapa | Fungsi |
| :--- | :--- | :--- |
| `/tempvoice atur hub:#x nama:"🔊 Room {user}" limit:5` | Admin | Aktifkan hub & atur template nama/batas |
| `/tempvoice status` | Semua | Lihat hub & room yang sedang aktif |
| `/tempvoice kunci aktif:True` | Pemilik room | Kunci/buka room |
| `/tempvoice nama nama:Ngobrol Santai` | Pemilik room | Ganti nama room |
| `/tempvoice limit jumlah:4` | Pemilik room | Batasi jumlah orang (0 = bebas) |
| `/tempvoice tendang member:@x` | Pemilik room | Keluarkan orang dari room |

Detail penting:
- **Hemat kuota channel:** maksimal **30 room** per server, dihapus otomatis saat kosong (Discord membatasi 500 channel/server).
- **Aman restart:** daftar room di `data/temp_voice.json`; room yatim dibersihkan lewat penyapuan tiap 5 menit.
- **Tidak mengganggu musik:** listener hanya menyentuh channel hub & room yang dibuatnya sendiri.
- **0 kuota AI.**
