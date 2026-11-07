---
title: "D. Fitur Server Otomatis (/serverstats, /autorole, /fakta, /keamanan)"
description: "Channel statistik otomatis, auto role, fakta 4x sehari, dan anti-phishing tanpa API berbayar."
icon: "dns"
weight: 4
toc: true
---

## 1. 📊 Statistik Server seperti Bot Serverstats (`/serverstats`)
- **`/serverstats lihat`** — kartu statistik lengkap: total anggota, manusia vs bot, perkiraan member online, boost & level, jumlah channel teks/suara/forum, role, emoji, stiker, tanggal server dibuat, pemilik, dan level verifikasi.
- **`/serverstats otomatis aktif:True`** *(Admin)* — membuat kategori **`📊 Statistik Server`** berisi Voice Channel penghitung yang **ter-update otomatis setiap ±10 menit**:
  `👥 Total Member: 1.204` · `🙋 Manusia: 1.150` · `🤖 Bot: 54` · `🟢 Online: 312` · `💎 Boost: 7`
- Warga **tidak bisa masuk** ke channel penghitung (hanya bisa melihat angka), dan update dibatasi aman dari *rate limit* Discord (maks. 2 rename / 10 menit per channel).

## 2. 🎭 Auto Role Member Baru (`/autorole`) *(Admin)*
- **`/autorole atur role:@Member role2:@Notif aktif:True`** — berikan **hingga 3 role** otomatis setiap ada member baru bergabung, tanpa perlu verifikasi manual.
- **`/autorole status`** — cek daftar role aktif & peringatan otomatis jika posisi role bot terlalu rendah.
- **`/autorole isi`** — berikan Auto Role ke member lama yang belum memilikinya (maks. 150 member per eksekusi, aman dari rate limit).
- Role bot/integrasi, `@everyone`, dan role di atas posisi bot otomatis dilewati agar tidak error.

## 3. 🌍 Fakta Unik Dunia Terjadwal 4x Sehari (`/fakta`)
- **Jadwal default: `08:00` (pagi) · `12:00` (siang) · `16:00` (sore) · `20:00` (malam)** — setiap slot bot mengirim **3–4 fakta menarik dari negara berbeda** (bendera + nama negara + penjelasan ringkas) dengan sapaan sesuai suasana waktu (pagi/siang/sore/malam).
- **Jadwal bisa digonta-ganti Admin kapan saja:**
  ```text
  /fakta atur channel:#umum jadwal:08:00,12:00,16:00,20:00
  /fakta atur channel:#umum jadwal:8,20            ← 2x sehari (format singkat)
  /fakta atur channel:#umum jadwal:09:00           ← 1x sehari
  ```
  Menerima **1–6 slot per hari** dengan format fleksibel (`8`, `08:00`, `8.30`, dipisah koma/spasi/`dan`). Autocomplete Discord juga menyediakan preset siap pakai.
- **Anti-dobel & anti-banjir:** setiap slot hanya dikirim **sekali per hari**. Jika bot sempat mati/offline melewati beberapa slot, hanya **1 pesan terbaru** yang dikirim (slot terlewat ditandai selesai, bukan di-spam).
- **Anti-monoton:** fakta yang sudah pernah dikirim (16 fakta terakhir) tidak diulang, dan jika Gemini sedang sibuk bot otomatis memakai **bank fakta offline** agar rubrik tetap terkirim.
- **`/fakta sekarang`** untuk kirim contoh langsung (tanpa mengubah jadwal), **`/fakta status`** untuk melihat seluruh slot, slot berikutnya, & slot yang sudah terkirim hari ini.

## 4. 🛡️ Anti-Phishing Guard Tanpa API Berbayar (`/keamanan`)
- **`/keamanan phising aktif:True`** *(Admin)* — bot memindai setiap link di pesan warga dan otomatis:
  1. **Menghapus** pesan yang berisi link phishing tingkat **berbahaya**.
  2. **Memperingatkan** pengirim & warga lain di channel.
  3. **Mencatat** detailnya ke channel log moderator (opsional).
- **Deteksi lokal gratis** (tanpa API berbayar / tanpa kartu kredit): domain tiruan brand populer (Discord, Steam, Roblox, Netflix, Binance, Shopee, DANA, BCA, dll.), karakter **punycode `xn--`**, link berbasis **IP langsung**, **TLD berisiko** (`.tk`, `.ml`, `.ga`, `.zip`, dll.), **pemendek URL** (`bit.ly` dsb.), trik `@` pada URL, dan **daftar hitam** domain phishing yang sudah dikenal.
- **`/keamanan cek link:https://...`** bisa dipakai **semua member** untuk memeriksa keamanan link sebelum membuka.
- Bisa dibatasi hanya ke channel tertentu, dan mode **ketat** (`ketat:True`) juga menindak link yang baru *mencurigakan*.

## 5. 🪤 Honeypot — Channel Jebakan (`/keamanan honeypot`)

> 🍯 **Filosofi: jebakan, bukan tongkat.** Channel jebakan **tidak boleh dipakai siapa pun**.
> Warga asli membaca aturan dan tidak akan menyentuhnya; **self-bot, skrip promo, & bot raid**
> justru menganggapnya sasaran empuk. Jadi pesan pertama di sana sudah menjadi bukti — tanpa
> analisis teks, tanpa ambang, tanpa salah tuduh.

| Command | Fungsi |
| :--- | :--- |
| **`/keamanan honeypot channel:#promo-gratis`** *(Admin)* | Pasang channel jebakan (maks **3** channel per server). |
| **`/keamanan honeypot channel:#promo aksi:timeout timeout_detik:600`** | Pilih tindakan: `lapor`, `hapus`, `timeout`, `kick`, atau `ban`. |
| **`/keamanan honeypot channel:#promo log_channel:#mod-log`** | Kirim laporan kejadian ke channel log. |
| **`/keamanan honeypot channel:#promo abaikan_staf:False`** | Ikut menindak staf (default **staf & pemilik aman**). |
| **`/keamanan honeypot`** *(tanpa argumen)* | Lihat setelan & jumlah tangkapan. |
| **`/keamanan honeypot aktif:False`** | Matikan sementara — daftar channel tetap tersimpan. |

**Aturan main:**
- **Bawaan `lapor`** — belum ada tindakan sampai Admin memilih yang lebih keras.
- **Staf selalu aman** (`abaikan_staf` default aktif): Administrator / Manage Messages / Manage Guild.
- **Bot diabaikan** (termasuk bot ini sendiri), supaya webhook & bot resmi tidak ikut kena.
- Saat mode bertindak, pesan **selalu dihapus** dulu, lalu laporan dikirim ke channel log.
- Channel jebakan yang dihapus otomatis dibuang dari daftar; honeypot mati bila daftar kosong.
- **0 kuota AI**, data di `data/honeypot.json`, maksimal 3 channel/server.

**Di dashboard:** halaman **🛡️ Keamanan** → panel *🪤 Honeypot*: pilih channel & tindakan,
atur time-out, channel log, dan tombol **uji simulasi** (menampilkan keputusan honeypot untuk
seorang member **tanpa** menghapus pesan atau menghukum siapa pun). Jalur tulis:
`POST /api.keamanan` (`action=honeypot-simpan` / `honeypot-hapus`).

---
