# 🤖 AI Discord Chat & Community Agent — Google Gemini Edition

Bot Discord lengkap berbasis **100% Google Gemini API terbaru** yang menggabungkan **dua sistem utama dalam satu bot ringan**:
1. **🔒 Panel Ruang Sesi Privat (*Private Thread*)** — Ruang pribadi khusus tiap member untuk konsultasi AI 5 kepribadian, analisis gambar (*Vision*), review file kode, serta pembuatan & pengeditan gambar AI.
2. **🌐 AI Agent & Otomasi Komunitas (*Public Channel*)** — Teman nongkrong virtual bergaya manusia asli yang bisa ikut ngobrol santai di *General Chat*, memecah keheningan saat channel sepi (*Dead-Chat Reviver*), paham jam lokal secara *real-time*, membaca ekspresi **Stiker & Custom Emoji**, hingga otomatis mengomentari kiriman **Foto & Video** di channel Galeri!

Dirancang sangat ringan (~35–45 MB RAM) menggunakan koneksi `aiohttp` asinkron murni sehingga lancar dijalankan 24/7 di **Wispbyte**, VPS, maupun komputer lokal.

---

## 📚 Daftar Isi
1. [Penjelasan Lengkap Semua Fitur](#-penjelasan-lengkap-semua-fitur)
   - [A. Fitur Ruang Sesi Privat (Panel AI)](#a-fitur-ruang-sesi-privat-panel-ai)
   - [B. Fitur AI Agent & Otomasi Komunitas](#b-fitur-ai-agent--otomasi-komunitas)
   - [C. Fitur Keamanan, Ketahanan & Performa](#c-fitur-keamanan-ketahanan--performa)
2. [Daftar Lengkap Command & Tombol](#-daftar-lengkap-command--tombol)
3. [Penjelasan Variabel `.env`](#-penjelasan-variabel-env)
4. [Persiapan Discord Developer Portal](#-persiapan-di-discord-developer-portal)
5. [Panduan Deploy di Wispbyte (Step-by-Step)](#-panduan-deploy-di-wispbyte-step-by-step)
6. [Menjalankan Secara Lokal / VPS](#-menjalankan-secara-lokal--vps)
7. [Struktur File Proyek](#-struktur-file-proyek)
8. [FAQ & Solusi Masalah Umum](#-faq--solusi-masalah-umum)

---

## ✨ Penjelasan Lengkap Semua Fitur

### A. Fitur Ruang Sesi Privat (Panel AI)

Admin cukup memasang satu panel permanen di channel khusus (misalnya `#ai-assistant`) menggunakan `/setup_panel`. Dari panel tersebut, setiap member dapat membuka ruang privat (*Private Thread*) yang hanya bisa dilihat oleh member itu sendiri.

#### 1. 💬 Chat AI Multi-Persona (5 Kepribadian Gemini)
Saat menekan tombol **💬 Chat AI (Teks & Vision)**, member bebas memilih 1 dari 5 mode kepribadian:
| Mode | Model Utama | Karakter & Kegunaan |
| :--- | :--- | :--- |
| **♊ Gemini Flash (Asisten Utama)** | `gemini-3.5-flash-lite` | Cerdas, ramah, cepat (~1 detik), & serba bisa untuk topik umum sehari-hari. |
| **⚡ Gemini Flash-Lite (Respon Kilat)** | `gemini-3.1-flash-lite` | Jawaban ringkas, padat, *to-the-point*, instan, & paling hemat kuota API. |
| **💻 Gemini - Pakar Koding & Debug** | `gemini-3.6-flash` | Spesialis pemrograman, struktur kode rapi, penjelasan logika, & bedah *bug*. |
| **🧠 Gemini - Penalaran & Riset** | `gemini-3.6-flash` | Analitis & sistematis *step-by-step* untuk matematika, sains, tugas, & riset. |
| **🛋️ Gemini - Teman Curhat** | `gemini-3.5-flash-lite` | Pendengar yang hangat, empatik, tidak menghakimi, dan suportif ala sahabat dekat. |

> 💡 **Ganti Mode Kapan Saja:** Di dalam ruang `ai-...`, tersedia menu *dropdown* dan command `/model` untuk mengganti kepribadian Gemini di tengah percakapan **tanpa menghapus riwayat obrolan sebelumnya**.

#### 2. 📷 Analisis Gambar (*Vision*), Stiker, & Pembaca File Kode
Di dalam ruang chat `ai-...`, member tidak hanya bisa mengetik teks, tetapi juga melampirkan:
- **Gambar / Screenshot** (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` — maks. 8 MB per gambar, hingga 4 gambar sekaligus): Cocok untuk menanyakan soal bergambar, desain UI, atau *screenshot* pesan *error* koding.
- **File Kode & Dokumen Teks** (`.py`, `.js`, `.ts`, `.tsx`, `.json`, `.yaml`, `.html`, `.css`, `.sql`, `.csv`, `.txt`, `.md`, `.log`, `.c`, `.cpp`, `.java`, `.go`, `.rs`, `.php`, dll. — maks. 100 KB per file): Bot otomatis membaca isi file dan memasukkannya sebagai konteks ke Gemini.
- **Stiker Discord**: Bot ikut mengenali visual stiker yang dikirim.

#### 3. 🎨 Generate & Edit Gambar AI (`draw-...`)
Saat menekan tombol **🎨 Generate Gambar AI**, bot membuatkan studio gambar privat (`draw-namauser`):
- **Buat Gambar dari Teks (*Text-to-Image*):** Cukup ketik deskripsi gambar apa saja, bot langsung membuatkannya.
- **Edit Gambar (*Image-to-Image*):** Lampirkan sebuah foto/gambar disertai instruksi teks (contoh: *"ubah latar belakangnya menjadi kota malam cyberpunk"*), maka Gemini akan mengedit gambar tersebut!
- **7 Pilihan Gaya Art:**
  - 🖼️ *Biasa / Default*
  - ⛩️ *Anime Style*
  - 🏙️ *Cyberpunk Futuristic*
  - 📸 *Photorealistic (Foto Asli)*
  - 🧊 *3D Render (Pixar/Blender)*
  - 👾 *Pixel Art Retro*
  - 🎨 *Lukisan Cat Air (Watercolor)*
- **5 Pilihan Rasio Ukuran:** `1:1 (Persegi)`, `16:9 (Landscape/Banner)`, `9:16 (Portrait/Story HP)`, `4:3 (Foto Klasik)`, dan `3:4 (Poster)`.
- **Smart Auto-Fallback Gratis:** Utama menggunakan **Google Gemini Native Image (`gemini-3.1-flash-lite-image` / `gemini-nano-banana-2.1`)**. Apabila akun `GEMINI_API_KEY` Anda memakai paket *Free Tier* yang kuota gambarnya dibatasi Google, bot **otomatis beralih ke generator cadangan gratis (Flux)** tanpa memerlukan API key tambahan!

#### 4. 🔄 Reset Memori & 📜 Rekap Transkrip Lengkap ke DM
- **Tombol 🔄 Reset Sesi (atau `/reset`):** Menghapus ingatan obrolan di ruang `ai-...` untuk ganti topik baru, atau mengembalikan setelan gaya/rasio gambar ke awal di ruang `draw-...` tanpa perlu membuat thread baru.
- **Tombol 🔴 Akhiri Sesi:**
  - Merangkum percakapan ke dalam **Embed Discord** yang rapi **sekaligus melampirkan file `rekap-nama-ruang.txt`** berisi transkrip percakapan utuh dari awal sampai akhir ke **DM pribadi member**.
  - Jika DM member dikunci/tertutup, bot otomatis mengirimkan file `.txt` tersebut di dalam thread dan memberi waktu **10 detik** untuk mengunduhnya sebelum ruang privat dihapus.

---

### B. Fitur AI Agent & Otomasi Komunitas

Fitur ini membuat bot berbaur di channel publik server layaknya **warga/teman nongkrong asli** (bukan gaya kaku robot asisten). Seluruh fiturnya dikendalikan oleh Admin melalui command `/agent`.

#### 1. 💬 Auto-Chat Natural ala Manusia (`/agent chat`)
- Menjawab dengan kalimat pendek & santai (1–2 kalimat kasual ala chat Discord Indonesia), tidak pernah mengaku sebagai AI/robot, menyapa member dengan **nama tampilan (`display_name`)** mereka, dan gemar memancing obrolan balik supaya diskusi hidup.
- Memiliki **2 Mode Balasan**:
  - **`Cerdas & Natural (smart)` *(Rekomendasi)*:**
    - Otomatis membalas saat di-*mention*, saat pesannya di-*reply*, saat member menyapa (*"pagi"*, *"halo"*, *"sepi nih"*, *"jam berapa"*, dll.), saat member mengirim stiker/emoji ekspresif, saat channel baru saja hening lalu ada yang mulai chat, atau selama percakapan dengan bot masih hangat (6 menit terakhir).
    - **Tahu Diri (Tidak Memotong Obrolan):** Jika Member A sedang me-*reply* pesan Member B secara spesifik, AI **tidak akan ikut campur** memotong obrolan mereka (namun tetap menyimak konteksnya secara pasif).
  - **`Balas Semua Pesan (all)`:** Membalas setiap pesan di channel tersebut (kecuali balasan antar sesama member). Cocok untuk channel khusus seperti `#ngobrol-bareng-ai`.
- Dilengkapi **jeda mengetik realistis (*human typing delay*)** selama ~1–2 detik agar terasa natural.

#### 2. 💤 Pemecah Sepi Otomatis / *Dead-Chat Reviver* (`/agent chat` & `/agent sapa`)
- Jika channel Auto-Chat sepi tidak ada aktivitas selama **`menit_sepi`** (default **30 menit**, bisa diatur bebas atau diisi `0` untuk mematikan), AI otomatis memulai obrolan santai sesuai suasana jam saat itu (*contoh siang hari: "Sepi amat nih siang bolong, pada lagi ngapain guys?"*).
- **Proteksi Anti-Monolog / Anti-Spam:** Jika setelah AI menyapa ternyata belum ada satu pun member yang membalas, AI **berhenti menyapa ulang** sampai ada member manusia yang chat lagi — sehingga channel tidak pernah penuh spam sendirian!
- **Jam Tenang Malam (*Quiet Hours*):** Secara default aktif pada pukul **23:00 – 06:00** waktu lokal agar AI tidak tiba-tiba memecah sepi jam 3 subuh saat member sedang tidur (bisa diatur lewat `/agent persona`).

#### 3. 🕒 Kesadaran Waktu Lokal *Real-Time* (WIB / WITA / WIT)
- AI selalu tahu hari, tanggal, jam, dan menit saat ini secara presisi (mendukung **WIB**, **WITA**, dan **WIT**).
- Jika ditanya *"sekarang jam berapa?"* pada pukul 16:30, AI akan menjawab akurat pukul 16:30 dan mengaitkannya dengan suasana waktu tersebut (misalnya sore jam-jam rawan ngantuk, pagi semangat, siang terik, atau malam waktunya mabar).

#### 4. 😄 Membaca Visual Stiker & Custom Emoji Server
- Saat member mengirim **Stiker Discord** (PNG/APNG/GIF) atau **Custom Emoji Server** (`<:nama:id>` / `<a:nama:id>`), bot mengunduh gambar visual stiker/emoji tersebut dan memindainya lewat **Gemini Vision**.
- Hasilnya, AI benar-benar "melihat" gambar stiker lucu atau ekspresi wajah songong pada emoji yang dikirim dan membalasnya secara relevan!

#### 5. 📸 Gallery Auto-Comment: Scan Foto & Video (`/agent gallery`)
- Aktifkan di channel pamer karya, meme, fotografi, cosplay, setup PC, atau klip game (misal `#gallery` / `#media`).
- Setiap kali member mengirim **Foto/Gambar** (hingga 8 MB) atau **Video Klip Pendek** (`.mp4`, `.webm`, `.mov` hingga 15 MB):
  1. Bot otomatis men-scan isi visual gambar atau video tersebut menggunakan Gemini Multimodal.
  2. Memberikan **reaksi emoji otomatis** (`✨`, `🔥`, `😍`, `👏`, atau `🙌` — bisa dinyalakan/dimatikan).
  3. Membalas (*reply*) postingan tersebut dengan komentar spesifik yang menyebutkan detail unik di dalam foto/video (seperti warna kostum, karakter, latar tempat, atau momen serunya).

---

### C. Fitur Keamanan, Ketahanan & Performa

1. **💾 Memori Tahan Restart Ganda (*Dual-Layer Persistence*):**
   - Semua sesi privat tersimpan otomatis ke `data/sessions.json` dan pengaturan AI Agent tersimpan di `data/agent_config.json` secara atomik.
   - Bahkan jika container Wispbyte di-*rebuild* bersih sekalipun, ketika member lanjut chat di thread `ai-...` lama, bot mampu membaca ulang riwayat thread Discord untuk memulihkan konteks percakapan secara otomatis!
2. **🔀 Rantai *Auto-Fallback* Model Gemini:**
   - Jika model utama (`gemini-3.8-flash`) sedang terkena antrean penuh (HTTP 503) atau batas *rate-limit* sementara (HTTP 429), bot otomatis mencoba ke model cadangan (`gemini-flash-latest` → `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`) menggunakan API key yang sama.
3. **✂️ Pemotong Pesan Cerdas Anti-Rusak Kode Markdown:**
   - Discord membatasi 2.000 karakter per pesan. Jika Gemini menulis tutorial kode sepanjang 5.000 karakter, bot memotong pesan tepat di batas baris/paragraf serta **otomatis menutup (```` ``` ````) dan membuka ulang blok kode (```` ```python ````)** di bagian selanjutnya agar tampilan kode tidak pernah berantakan.
4. **🔐 Proteksi Token & Anti-Spam:**
   - Autentikasi memakai header `x-goog-api-key` (bukan parameter URL) plus penyensoran otomatis sehingga `GEMINI_API_KEY` dan `DISCORD_BOT_TOKEN` tidak pernah bocor ke pesan error Discord.
   - Pembatasan maksimal ruang privat aktif per member (`MAX_THREADS_PER_USER=3`) agar server aman dari spam pembuatan thread.
   - Seluruh tombol memiliki `custom_id` persisten sehingga tetap berfungsi walau bot habis di-*restart*.

---

## 📋 Daftar Lengkap Command & Tombol

### 1. Slash & Prefix Commands Umum / Ruang Privat
| Command | Akses | Keterangan |
| :--- | :--- | :--- |
| `/setup_panel` atau `!setup_panel` | Administrator | Memasang Embed & tombol Panel Utama AI (Chat & Gambar) di channel saat ini. |
| `/model` | Pemilik Ruang Sesi | Mengganti mode kepribadian Gemini (Utama, Kilat, Koding, Riset, Curhat) di ruang `ai-...`. |
| `/reset` | Pemilik Sesi / Moderator | Menghapus memori obrolan di `ai-...` atau mereset setelan gambar di `draw-...`. |
| `/status` | Semua Member | Menampilkan ping Discord, pemakaian RAM (MB), uptime, jam AI, & jumlah sesi aktif. |

### 2. Slash Commands Admin untuk AI Agent Komunitas (`/agent`)
| Command | Parameter Utama | Keterangan |
| :--- | :--- | :--- |
| `/agent chat` | `channel`, `aktif`, `mode_balas`, `menit_sepi` | Mengaktifkan/mematikan Auto-Chat & Pemecah Sepi otomatis di channel publik. |
| `/agent gallery` | `channel`, `aktif`, `auto_reaction` | Mengaktifkan/mematikan Auto-Komentar Foto & Video di channel Galeri/Showcase. |
| `/agent persona` | `gaya_bahasa`, `nama_panggilan`, `zona_waktu`, `jam_tenang_malam`, `konteks_komunitas` | Mengubah nama akrab AI, gaya bicara (*Akrab / Gaul / Ramah*), zona waktu (*WIB/WITA/WIT*), Jam Tenang, & deskripsi komunitas. |
| `/agent sapa` | `channel` *(opsional)* | Memicu AI Agent langsung menyapa / memecah sepi detik ini juga (untuk tes instan). |
| `/agent status` | — | Melihat status profil AI Agent beserta daftar channel Auto-Chat & Galeri yang aktif. |

---

## ⚙️ Penjelasan Variabel `.env`

Hanya **2 variabel pertama** yang wajib diisi; sisanya bersifat opsional dan sudah memiliki nilai default terbaik:

| Variabel | Wajib? | Default | Fungsi |
| :--- | :---: | :--- | :--- |
| `DISCORD_BOT_TOKEN` | ✅ **Wajib** | — | Token bot dari Discord Developer Portal (juga mendukung alias `DISCORD_TOKEN`). |
| `GEMINI_API_KEY` | ✅ **Wajib** | — | API Key dari [Google AI Studio](https://aistudio.google.com/apikey) *(bisa isi 1 key atau beberapa key dipisahkan koma `key1,key2` untuk rotasi otomatis)*. |
| `DISCORD_GUILD_ID` | Opsional | *(kosong)* | Isi ID Server Discord Anda jika ingin Slash Commands baru langsung muncul instan (<1 detik) tanpa menunggu cache global Discord. |
| `GEMINI_DEFAULT_MODEL` | Opsional | `gemini-3.5-flash-lite` | Model utama cepat & stabil (bebas *503 overload* di *Free Tier*) untuk chat umum, curhat, Vision, & AI Agent. |
| `GEMINI_FAST_MODEL` | Opsional | `gemini-3.1-flash-lite` | Model ultra-kilat untuk mode Respon Kilat & cadangan instan. |
| `GEMINI_REASONING_MODEL` | Opsional | `gemini-3.6-flash` | Model penalaran untuk mode Pakar Koding & Riset. |
| `GEMINI_PAID_IMAGE_ENABLED` | Opsional | `false` | Biarkan `false` pada *Free Tier* agar langsung memakai Flux gratis secara instan. Ubah ke `true` jika akun AI Studio sudah *Paid/Billing* untuk memakai Nano Banana / Pro. |
| `GEMINI_IMAGE_MODEL` | Opsional | `gemini-3.1-flash-lite-image` | Model gambar Gemini saat `GEMINI_PAID_IMAGE_ENABLED=true` (bisa diisi `gemini-3-pro-image` untuk Nano Banana Pro). |
| `ENABLE_IMAGE_FALLBACK` | Opsional | `true` | Mengaktifkan generator gambar gratis Flux. |
| `MAX_HISTORY_MESSAGES` | Opsional | `30` | Jumlah riwayat pesan terakhir yang diingat per ruang chat privat. |
| `MAX_THREADS_PER_USER` | Opsional | `3` | Maksimal ruang privat aktif yang boleh dibuka bersamaan oleh 1 member. |
| `BOT_TIMEZONE` | Opsional | `Asia/Jakarta` | Zona waktu default (`Asia/Jakarta`, `Asia/Makassar`, atau `Asia/Jayapura`). |
| `AGENT_DEFAULT_IDLE_MINUTES` | Opsional | `30` | Durasi hening default (menit) sebelum AI Agent memecah kesunyian. |
| `SESSION_EXPIRE_DAYS` | Opsional | `7` | Otomatis membersihkan data sesi privat yang sudah menganggur lebih dari N hari (`0` = nonaktif). |

---

## 🔑 Persiapan di Discord Developer Portal

Sebelum menyalakan bot di Wispbyte, pastikan pengaturan berikut sudah aktif:

1. Buka [Discord Developer Portal](https://discord.com/developers/applications) → pilih aplikasi bot Anda.
2. Buka tab **Bot**:
   - Salin **Token** untuk dimasukkan ke `DISCORD_BOT_TOKEN`.
   - Gulir ke bagian **Privileged Gateway Intents**, lalu **AKTIFKAN**:
     - ✅ **Message Content Intent** *(Sangat wajib! Tanpa ini bot tidak bisa membaca isi teks chat maupun lampiran)*
   - Klik **Save Changes**.
3. Buka tab **OAuth2 → URL Generator**:
   - Centang **Scopes**: `bot` dan `applications.commands`.
   - Centang **Bot Permissions**:
     - `View Channels`
     - `Send Messages`
     - `Send Messages in Threads`
     - `Create Private Threads`
     - `Manage Threads`
     - `Embed Links`
     - `Attach Files`
     - `Add Reactions`
     - `Read Message History`
   - Salin URL paling bawah lalu buka di browser untuk mengundang bot ke server Discord Anda.

---

## 🚀 Panduan Deploy di Wispbyte (Step-by-Step)

1. Masuk ke dashboard **[Wispbyte](https://wispbyte.com)**, lalu buat server baru dengan runtime **Python** (pilih Python 3.11 atau 3.12+).
2. Buka menu **Files** di panel Wispbyte, lalu unggah file utama berikut:
   - `main.py`
   - `community_agent.py`
   - `ai_handler.py`
   - `views.py`
   - `storage.py`
   - `utils.py`
   - `config.py`
   - `requirements.txt`
   *(Atau hubungkan langsung dengan repository GitHub ini melalui menu Git jika tersedia).*
3. Buka menu **Startup** di panel Wispbyte:
   - Pastikan **Startup File / App py file** diatur ke: `main.py`
   - Pastikan **Requirements file** diatur ke: `requirements.txt` *(atau isi `discord.py aiohttp python-dotenv` pada kolom Additional Python Packages)*.
4. **Mengisi Token & API Key (Pilih salah satu cara):**
   - **Cara 1 (Lewat file `.env`):** Di menu **Files**, klik **New File**, beri nama persis **`.env`**, lalu isi:
     ```env
     DISCORD_BOT_TOKEN=paste_token_discord_kamu_di_sini
     GEMINI_API_KEY=paste_gemini_api_key_kamu_di_sini
     DISCORD_GUILD_ID=paste_id_server_discord_kamu_opsional
     ```
   - **Cara 2 (Lewat tab Startup/Variables):** Jika template Wispbyte menyediakan kolom variabel, masukkan `DISCORD_BOT_TOKEN` dan `GEMINI_API_KEY` di sana.
5. Buka tab **Console**, lalu klik tombol **Start**.
6. Jika berhasil, dalam beberapa detik akan muncul log:
   ```text
   ✅ Bot aktif sebagai NamaBot#0000 | Python 3.11+ | discord.py 2.7+ | RAM: ~38.0 MB
   ```
7. Sekarang masuk ke server Discord Anda dan coba:
   - Ketik **`/setup_panel`** di channel panel AI privat.
   - Ketik **`/agent chat`** di channel obrolan umum dan **`/agent gallery`** di channel galeri!

---

## 💻 Menjalankan Secara Lokal / VPS

```bash
# 1. Buat & aktifkan virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Di Windows: .venv\Scripts\activate

# 2. Install library yang dibutuhkan
pip install -r requirements.txt

# 3. Buat file .env dari contoh template, lalu isi token & API key Anda
cp .env.example .env

# 4. Jalankan bot
python main.py
```

---

## 📂 Struktur File Proyek

```text
ai-discord-chat/
├── main.py             # Entrypoint utama bot, Slash Commands, loop pemecah sepi & event handler
├── community_agent.py  # Mesin AI Agent Komunitas (Auto-Chat, Pemecah Sepi, Stiker/Emoji, & Galeri)
├── ai_handler.py       # Klien async HTTP ke Google Gemini REST API (Chat, Vision, Kode, & Gambar)
├── views.py            # Komponen tombol & dropdown UI Discord persisten tahan restart
├── storage.py          # Penyimpanan sesi privat JSON atomik & auto-recovery dari Discord Thread
├── utils.py            # Pemotong pesan kode Markdown, ekstraktor media/stiker/video, & jam lokal
├── config.py           # Konfigurasi variabel .env, daftar 5 kepribadian Gemini, gaya & rasio gambar
├── requirements.txt    # Daftar dependensi Python super ringan
├── .env.example        # Template contoh pengisian variabel .env
├── .gitignore          # Mencegah file rahasia (.env) & folder data sesi ikut ter-commit ke Git
├── LICENSE             # Lisensi Open-Source MIT
└── tests/              # Pengujian otomatis (pytest) untuk memastikan seluruh modul bebas bug
```

---

## 📄 Lisensi

Proyek ini dirilis menggunakan **[MIT License](LICENSE)** — bebas digunakan, dipelajari, dan dikembangkan dengan tetap mencantumkan atribusi pembuat asli.

---

## ❓ FAQ & Solusi Masalah Umum

- **Slash Commands (`/setup_panel`, `/agent`) belum muncul di Discord?**
  Sinkronisasi global Discord terkadang membutuhkan waktu hingga beberapa menit. Agar langsung muncul dalam 1 detik, isi `DISCORD_GUILD_ID` di `.env` dengan ID Server Discord Anda (klik kanan ikon server dengan *Developer Mode* aktif → *Copy Server ID*), lalu *restart* bot. Pastikan juga saat mengundang bot, scope `applications.commands` sudah tercentang.
- **Bot online tapi tidak merespons pesan teks di ruang chat?**
  Pastikan **Message Content Intent** sudah dinyalakan di [Discord Developer Portal](https://discord.com/developers/applications) pada bagian *Bot → Privileged Gateway Intents*, lalu *restart* bot di Wispbyte.
- **Gagal membuat ruang privat (`Missing Permissions`)?**
  Pastikan Role bot di channel tersebut memiliki izin `Create Private Threads`, `Send Messages in Threads`, dan `Read Message History`.
