# 🤖 AI Discord Chat & Community Agent — Google Gemini Edition (`v1.3.0-beta`)

Bot Discord lengkap berbasis **100% Google Gemini API terbaru** yang menggabungkan **tiga sistem pintar dalam satu bot ringan**:
1. **🔒 Panel Ruang Sesi Privat (*Private Thread*)** — Ruang pribadi khusus tiap member untuk konsultasi AI 5 kepribadian, membaca dokumen **`.pdf`** langsung, mendengar **Voice Note (🎤)**, merangkum **video YouTube & link web**, cek **berita & info terbaru hari ini (*Live Web & News Search* Gratis)**, analisis gambar (*Vision*), review file kode, serta pembuatan & pengeditan gambar AI.
2. **🌐 AI Agent & Otomasi Komunitas (*Public Text Channel & Channel Forum*)** — Teman nongkrong virtual bergaya manusia asli dengan **etika anti-nimbrung pintar** (tidak memotong obrolan sesama member!), dilengkapi **Memori Info & FAQ Resmi Server (`/agent info`)**, **Koran & Sapaan Pagi Otomatis (`/agent digest`)**, **Panel Kontrol Admin Interaktif (`/agent panel`)**, serta dukungan penuh **Channel Forum (`ForumChannel` & `MediaChannel`)** lengkap dengan **Auto-Tagging Pintar** & tombol **`✅ Tandai Selesai`**!
3. **🎮 Hiburan & Pintasan Pintar Seluruh Server** — **3 Menu Tekan-Tahan Pesan (*Context Menu Apps*)** tanpa ketik command (`🌐 Terjemahkan ke Indonesia`, `💡 Jelaskan Pesan Ini`, & `🔍 Cek Fakta / Hoaks`), pencari info terkini **`/cari`**, perangkum link **`/ringkas_link`**, serta **6 Mode Mini-Game Tongkrongan AI (`/game`)** (termasuk **🖼️ Tebak Gambar AI** & **⛓️ Sambung Kata**) lengkap dengan Papan Skor (*Leaderboard*) server!

Dirancang sangat ringan (~35–55 MB RAM) menggunakan koneksi `aiohttp` asinkron murni sehingga lancar dijalankan 24/7 di **Wispbyte**, VPS, maupun komputer lokal — serta sudah dioptimalkan khusus agar **100% berjalan lancar pada akun Gemini *Free Tier* (bebas antrean `503` & bebas error `exceeded your current quota`)**.

---

## 📚 Daftar Isi
1. [Penjelasan Lengkap Semua Fitur](#-penjelasan-lengkap-semua-fitur)
   - [A. Fitur Ruang Sesi Privat (Panel AI)](#a-fitur-ruang-sesi-privat-panel-ai)
   - [B. Fitur AI Agent & Otomasi Komunitas](#b-fitur-ai-agent--otomasi-komunitas)
   - [C. Fitur Keamanan, Ketahanan & Performa](#c-fitur-keamanan-ketahanan--performa)
2. [Panduan Cara Pakai Semua Fitur (Step-by-Step)](#-panduan-cara-pakai-semua-fitur-step-by-step)
3. [Cara Mematikan (Disable) Fitur Kapan Saja](#-cara-mematikan-disable-fitur-kapan-saja)
4. [Daftar Lengkap Command & Tombol](#-daftar-lengkap-command--tombol)
5. [Penjelasan Variabel `.env`](#-penjelasan-variabel-env)
6. [Persiapan Discord Developer Portal](#-persiapan-di-discord-developer-portal)
7. [Panduan Deploy di Wispbyte (Step-by-Step)](#-panduan-deploy-di-wispbyte-step-by-step)
8. [Menjalankan Secara Lokal / VPS](#-menjalankan-secara-lokal--vps)
9. [Struktur File Proyek](#-struktur-file-proyek)
10. [FAQ & Solusi Masalah Umum](#-faq--solusi-masalah-umum)

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

#### 2. 🎙️ Mendengar *Voice Note* (🎤), *Vision* Gambar, Link YouTube/Web, & *Live Search*
Di dalam ruang chat privat `ai-...`, member bisa langsung mengirim:
- **Voice Note / Pesan Suara Discord (🎤) & File Audio** (`.ogg`, `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac` — maks. 12 MB): Cukup tekan tombol mikrofon di Discord HP/PC lalu bicara — Gemini mendengarkan langsung isi ucapan beserta intonasinya dan menjawab nyambung tanpa perlu mengetik!
- **Link Video YouTube & Artikel Website**: Tempel langsung link YouTube (`youtube.com/watch`, `youtu.be`, `shorts`, `live`) atau URL berita/artikel untuk dirangkum dan didiskusikan isinya secara instan di ruang privat.
- **Pertanyaan Berita & Info Terkini Hari Ini**: Tanyakan berita terbaru, skor pertandingan, cuaca, harga emas/kurs, atau rilis teknologi terbaru — bot otomatis mencarikan sumber web aktual secara gratis di ruang privat.
- **Gambar / Screenshot** (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` — maks. 8 MB per gambar, hingga 4 gambar sekaligus): Cocok untuk menanyakan soal bergambar, desain UI, atau *screenshot* pesan *error* koding.
- **Dokumen PDF Native** (`.pdf` — maks. 10 MB): Unggah file materi kuliah, jurnal, panduan kerja, atau *e-book* PDF — Gemini langsung membaca dan membedah isinya secara utuh!
- **File Kode & Dokumen Teks** (`.py`, `.js`, `.ts`, `.tsx`, `.json`, `.yaml`, `.html`, `.css`, `.sql`, `.csv`, `.txt`, `.md`, `.log`, `.c`, `.cpp`, `.java`, `.go`, `.rs`, `.php`, dll. — maks. 100 KB per file): Bot otomatis membaca isi file dan memasukkannya sebagai konteks ke Gemini.
- **Stiker Discord**: Bot ikut mengenali visual stiker yang dikirim.

#### 3. 🎨 Generate & Edit Gambar AI (`draw-...`)
Saat menekan tombol **🎨 Generate Gambar AI**, bot membuatkan studio gambar privat (`draw-namauser`):
- **Buat Gambar dari Teks (*Text-to-Image*):** Cukup ketik deskripsi gambar apa saja, bot langsung membuatkannya.
- **Edit Gambar (*Image-to-Image*):** Lampirkan sebuah foto/gambar disertai instruksi teks (contoh: *"ubah latar belakangnya menjadi kota malam cyberpunk"*), maka AI akan mengedit gambar tersebut!
- **7 Pilihan Gaya Art:**
  - 🖼️ *Biasa / Default*
  - ⛩️ *Anime Style*
  - 🏙️ *Cyberpunk Futuristic*
  - 📸 *Photorealistic (Foto Asli)*
  - 🧊 *3D Render (Pixar/Blender)*
  - 👾 *Pixel Art Retro*
  - 🎨 *Lukisan Cat Air (Watercolor)*
- **5 Pilihan Rasio Ukuran:** `1:1 (Persegi)`, `16:9 (Landscape/Banner)`, `9:16 (Portrait/Story HP)`, `4:3 (Foto Klasik)`, dan `3:4 (Poster)`.
- **Mode *Free Tier* Instan & *Paid Tier* Opsional:**
  - Secara default (`GEMINI_PAID_IMAGE_ENABLED=false`), pembuatan gambar dari teks langsung menggunakan **Flux Gratis** secara instan tanpa biaya tambahan.
  - Jika akun Google AI Studio Anda sudah mengaktifkan *Billing/Paid Tier*, ubah `GEMINI_PAID_IMAGE_ENABLED=true` di `.env` untuk memakai **Google Gemini Native Image (`gemini-3.1-flash-lite-image` / Nano Banana Pro `gemini-3-pro-image`)**.

#### 4. 🔄 Reset Memori & 📜 Rekap Transkrip Lengkap ke DM
- **Tombol 🔄 Reset Sesi (atau `/reset`):** Menghapus ingatan obrolan di ruang `ai-...` untuk ganti topik baru, atau mengembalikan setelan gaya/rasio gambar ke awal di ruang `draw-...` tanpa perlu membuat thread baru.
- **Tombol 🔴 Akhiri Sesi:**
  - Merangkum percakapan ke dalam **Embed Discord** yang rapi **sekaligus melampirkan file `rekap-nama-ruang.txt`** berisi transkrip percakapan utuh dari awal sampai akhir ke **DM pribadi member**.
  - Jika DM member dikunci/tertutup, bot otomatis mengirimkan file `.txt` tersebut di dalam thread dan memberi waktu **10 detik** untuk mengunduhnya sebelum ruang privat dihapus.

---

### B. Fitur AI Agent & Otomasi Komunitas (Text Channel & Channel Forum!)

Fitur ini membuat bot berbaur di channel publik server — baik di **Text Channel biasa (`#general`)** maupun di dalam **Channel Forum & Media (`#tanya-jawab`, `#showcase-karya`, `#forum-berita`)** — layaknya **warga/teman nongkrong asli** (bukan gaya kaku robot asisten). Seluruh fiturnya dikendalikan per-channel oleh Admin melalui command `/agent`:
- **Dukungan Penuh & Fitur Pintar Channel Forum (`ForumChannel` & `MediaChannel`):**
  - Saat `/agent chat`, `/agent gallery`, `/agent youtube`, atau `/agent cari` diaktifkan pada sebuah **Channel Forum**, bot otomatis bekerja di seluruh **Postingan (*Post/Thread*)** di dalam forum tersebut!
  - Membaca **Judul Postingan Forum**, **Tag Forum**, isi teks, gambar, dokumen **`.pdf`**, Voice Note, hingga **lampiran file kode** (`.py`, `.js`, `.json`, `.log`, dll.), serta menjaga ingatan obrolan **terpisah di masing-masing postingan** agar topik antar-postingan tidak pernah tercampur!
  - **🏷️ Auto-Tagging Forum Pintar (0 API Call):** Jika member membuat postingan forum baru tanpa memilih Tag, bot otomatis memilihkan 1–2 Tag Forum yang paling relevan dengan judul & isi topiknya tanpa memakan kuota API tambahan.
  - **✅ Tombol Persisten `Tandai Selesai`:** Pada balasan pembuka di Postingan Forum, bot menyematkan tombol hijau **`✅ Tandai Selesai`** yang bisa diklik oleh pembuat postingan atau Moderator untuk menambahkan awalan `✅`, memasang tag *Selesai/Solved*, dan mengarsipkan diskusi dengan rapi!

#### 1. 💬 Auto-Chat Natural ala Manusia & Etika Anti-Nimbrung Pintar (`/agent chat`)
- Menjawab dengan kalimat pendek & santai (1–2 kalimat kasual ala chat Discord Indonesia), tidak pernah mengaku sebagai AI/robot, menyapa member dengan **nama tampilan (`display_name`)** mereka, dan gemar memancing obrolan balik supaya diskusi hidup.
- Memiliki **2 Mode Balasan**:
  - **`Cerdas dan Natural - Rekomendasi (smart)`:**
    - Otomatis membalas saat di-*mention* (`@bot`), saat pesannya di-*reply*, atau saat **nama panggilan akrabnya** (diatur lewat `/agent persona`, misal *"Whas"*) dipanggil langsung di chat.
    - Ikut merespons sapaan pembuka umum (*"pagi"*, *"halo"*, *"sepi nih"*, *"jam berapa"*, dll.), kiriman **Voice Note (🎤)** asli Discord, kiriman yang **murni stiker/emoji ekspresif**, saat channel baru saja hening lama lalu ada warga mulai menyapa, atau selama sesi obrolan **1-on-1** dengan member tersebut masih hangat (**90 detik / maks. 2 chat lanjutan**).
    - **🛡️ 6 Lapis Etika Anti-Nimbrung (Tidak Mengganggu Obrolan Sesama Member):**
      1. **Reply Antar-Member:** Diam jika Member A me-*reply* pesan Member B (kecuali di pesan itu ikut memanggil `@bot` / nama panggilan bot).
      2. **Tag / Mention Member Lain:** Diam jika pesan me-*mention* member manusia lain (misal: *"halo @Budi login yuk"*).
      3. **Otomatis Menepi Saat Warga Ramai (*Crowd-Chat Step-Back*):** Jika ada **≥ 2 member manusia** sedang asyik ngobrol bolak-balik di channel dalam 90 detik terakhir, AI otomatis menepi & diam agar tidak memotong tongkrongan (kecuali dipanggil namanya).
      4. **Kalimat Biasa + Emoji Aman:** Kalimat ngobrol ke teman yang diakhiri emoji (misal *"makasih ya bro 😂"*) tidak akan dianggap memanggil bot.
      5. **Diam Saat Share Link & File Musik Biasa:** Tidak ikut nimbrung saat warga sekadar share link YouTube, Spotify, TikTok, IG, web, atau file lagu `.mp3`/`.wav` tanpa memanggil bot.
      6. **Abaikan Command Bot Lain:** Otomatis mengabaikan prefix command bot lain seperti `!play`, `.help`, `?rank`, `$waifu`, `m!play`, dll.
    - **Tetap Menyimak Pasif:** Walau sedang diam menjaga etika, bot tetap mencatat alur obrolan channel secara pasif — sehingga begitu namanya dipanggil, ia langsung paham konteks pembicaraan warga!
  - **`Balas Semua Pesan Member (all)`:** Membalas setiap pesan di channel tersebut (kecuali balasan/mention spesifik antar sesama member atau command bot lain). Cocok untuk channel khusus seperti `#ngobrol-bareng-ai`.

#### 2. 💤 Pemecah Sepi Otomatis / *Dead-Chat Reviver* (`/agent chat` & `/agent sapa`)
- Jika channel Auto-Chat sepi tidak ada aktivitas selama **`menit_sepi`** (default **30 menit**, mendukung pilihan cepat maupun ketik fleksibel seperti `30 detik`, `1`, `5`, `15`, `30`, `60`, `1 jam`, atau `0` untuk mematikan), AI otomatis memulai obrolan santai sesuai suasana jam saat itu (*contoh malam hari: "Sepi banget nih, tumben pada ngilang pas jam santai gini, pada mabar diam-diam ya kalian? Wkwk."*).
- **Proteksi Anti-Monolog / Anti-Spam:** Jika setelah AI menyapa otomatis ternyata belum ada satu pun member yang membalas, AI **berhenti menyapa ulang** sampai ada member manusia yang chat lagi — sehingga channel tidak pernah penuh spam sendirian!
- **Jam Tenang Malam (*Quiet Hours*):** Secara default aktif pada pukul **23:00 – 06:00** waktu lokal agar AI tidak tiba-tiba memecah sepi jam 3 subuh saat member sedang tidur (bisa diatur lewat `/agent persona`).

#### 3. 🕒 Kesadaran Waktu Lokal *Real-Time* (WIB / WITA / WIT)
- AI selalu tahu hari, tanggal, jam, dan menit saat ini secara presisi (mendukung **WIB**, **WITA**, dan **WIT**).
- Jika ditanya *"sekarang jam berapa?"* pada pukul 16:30, AI akan menjawab akurat pukul 16:30 dan mengaitkannya dengan suasana waktu tersebut (misalnya sore jam-jam rawan ngantuk, pagi semangat, siang terik, atau malam waktunya mabar).

#### 4. 😄 Membaca Visual Stiker & Custom Emoji Server
- Saat member mengirim **Stiker Discord** (PNG/APNG/GIF) atau **Custom Emoji Server** (`<:nama:id>` / `<a:nama:id>`), bot mengunduh gambar visual stiker/emoji tersebut dan memindainya lewat **Gemini Vision**.
- Hasilnya, AI benar-benar "melihat" gambar stiker lucu atau ekspresi wajah pada emoji yang dikirim dan membalasnya secara relevan!

#### 5. 📸 Gallery Auto-Comment: Scan Foto & Video (`/agent gallery`)
- Aktifkan di channel pamer karya, meme, fotografi, cosplay, setup PC, atau klip game (misal `#gallery` / `#media`).
- Setiap kali member mengirim **Foto/Gambar** (hingga 8 MB) atau **Video Klip Pendek** (`.mp4`, `.webm`, `.mov` hingga 15 MB):
  1. Bot otomatis men-scan isi visual gambar atau video tersebut menggunakan Gemini Multimodal.
  2. Memberikan **reaksi emoji otomatis** (`✨`, `🔥`, `😍`, `👏`, atau `🙌` — bisa dinyalakan/dimatikan).
  3. Membalas (*reply*) postingan tersebut dengan komentar spesifik yang menyebutkan detail unik di dalam foto/video (seperti warna kostum, karakter, latar tempat, atau momen serunya).

#### 6. 👋 AI Auto-Welcomer Member Baru (`/agent welcome`)
- Begitu ada member baru bergabung ke server, AI Agent otomatis menyapanya di channel sambutan (`#welcome`) dengan kalimat kreatif yang **selalu gonta-ganti** (anti-monoton), menyesuaikan nama member baru, jam lokal saat ia masuk, gaya bahasa, serta `konteks_komunitas` server Anda!
- Bisa ditambahkan `pesan_tambahan` (contoh: *"Jangan lupa ambil role di #roles ya"*) yang akan dirangkai secara luwes oleh AI, serta dilengkapi tombol `tes_sekarang:True` untuk langsung melihat contoh sambutannya.

#### 7. 📝 Perangkum Obrolan Channel Tertinggal (`/ringkas`)
- Ketinggalan **99+ notifikasi chat** di grup? Siapa pun member bisa mengetik **`/ringkas`** (pilih `25`, `50`, `100`, atau `150` pesan terakhir).
- Bot akan merangkum poin-poin inti obrolan warga beserta info/momen penting ke dalam Embed rapi berbahasa Indonesia (secara default hanya terlihat oleh Anda sendiri agar tidak mengganggu chat).

#### 8. 📲 Menu Tekan-Tahan Pesan / Klik Kanan (*Discord Context Menu Apps*) — Tanpa Ketik Command!
Member tidak perlu mengetik command apa pun untuk menerjemahkan atau memahami pesan asing/rumit:
- **Cara pakai di HP (Android/iOS):** Tekan & tahan (*long-press*) pesan siapa saja di channel mana pun ➔ pilih **Apps** ➔ klik:
  - **`🌐 Terjemahkan ke Indonesia`** — Menerjemahkan pesan bahasa Inggris, Jepang, Korea, Arab, Mandarin, bahasa gaul/slang, maupun teks di dalam gambar/Voice Note ke Bahasa Indonesia yang luwes.
  - **`💡 Jelaskan Pesan Ini`** — Menjelaskan maksud istilah teknis, potongan kode/error, pengumuman panjang, atau meme secara ringkas & mudah dimengerti.
  - **`🔍 Cek Fakta / Hoaks`** — Memeriksa kebenaran klaim berita heboh, rumor, atau tangkapan layar secara objektif menggunakan pencarian berita & web live gratis lengkap dengan tautan sumber buktinya!
- **Cara pakai di PC/Laptop:** Klik kanan pesan ➔ sorot **Apps** ➔ pilih menu di atas. Hasilnya tampil privat (*ephemeral*) hanya untuk Anda!

#### 9. 🎬 Perangkum Video YouTube & Pembaca Link Web Per-Channel (`/ringkas_link` & `/agent youtube`)
- **Diatur Per-Channel (Bisa Aktif di Beberapa Channel Sekaligus!):** Persis seperti `/agent chat` dan `/agent gallery`, Admin bebas memilih channel mana saja yang mengaktifkan fitur rangkum YouTube & link web lewat **`/agent youtube channel:#nama-channel aktif:True`** (bahkan tetap bekerja walaupun channel tersebut tidak menyalakan Auto-Chat!).
- **Command `/ringkas_link` & Ruang Privat `ai-...`:** Tempel link YouTube (`youtube.com/watch`, `youtu.be`, `shorts`, `live`) atau artikel web untuk mendapatkan rangkuman poin penting dalam hitungan detik (100% gratis memakai fitur *YouTube Video Understanding* Gemini)!
- **Panggil Nama Bot + Kirim / Reply Link di Channel Aktif:** Di channel yang sudah diaktifkan `/agent youtube`, member cukup memanggil **nama panggilan bot** / `@mention` / *reply* ke bot sambil menyertakan link YouTube/web — **atau me-*reply* pesan teman yang berisi link YouTube sambil memanggil bot** (contoh: *"Whas rangkumin video YouTube ini dong"*).
- **2 Mode Fleksibel Per-Channel (`auto_di_channel`):**
  - `auto_di_channel: False` (**Default & Rekomendasi**): Diam saat warga sekadar share link biasa di channel tersebut, namun langsung merangkum saat nama bot dipanggil atau memakai `/ringkas_link`.
  - `auto_di_channel: True` (**Mode Channel Khusus Video**): Setiap link YouTube/Web yang dikirim warga di channel tersebut otomatis dirangkum tanpa perlu memanggil nama bot!

#### 10. 🌍 Live Web & News Search Gratis Per-Channel (`/cari` & `/agent cari`)
- **100% Gratis di *Free Tier* (Bebas Error `You exceeded your current quota`):** Menggunakan mesin pencari web & berita *real-time* mandiri (**Google News RSS Indonesia + DuckDuckGo Web** + pembaca isi artikel berita) yang dirangkum oleh model Gemini gratis lengkap dengan daftar tautan **🌐 Sumber Web**! *(Juga mendukung opsi Google Search Grounding Paid Tier via `GEMINI_PAID_SEARCH_ENABLED=true`).*
- **Diatur Per-Channel (Bisa Aktif di Beberapa Channel Sekaligus!):** Admin bebas mengaktifkan fitur pencarian di satu atau beberapa channel pilihan lewat **`/agent cari channel:#nama-channel aktif:True`** (bekerja baik di channel Auto-Chat maupun channel mandiri khusus berita!).
- **Bisa Lewat `/cari` ATAU Panggil Nama Bot Langsung di Channel Aktif:**
  - Ketik **`/cari pertanyaan:berita timnas indonesia hari ini`** di channel yang aktif (atau ruang privat `ai-...`), **ATAU**
  - Langsung panggil nama panggilan bot di channel yang mengaktifkan `auto_di_chat:True` (contoh: *"Whas coba cari berita hari ini tentang harga emas Antam"*) — nama panggilan bot otomatis dibersihkan dari kata kunci pencarian sehingga hasil berita akurat!

#### 11. 🎮 6 Mode Mini-Game Tongkrongan AI (`/game`) + Papan Skor Server (*Leaderboard*)
Bikin channel tongkrongan makin ramai dengan **6 permainan interaktif** (anti-bosan & hemat kuota *Free Tier*!):
- **`🎭 Tebak dari Emoji` (+20 Poin):** Tebak judul film, game, anime, atau makanan populer dari 4–5 petunjuk emoji di chat!
- **`🖼️ Tebak Gambar AI` (+25 Poin):** AI melukis gambar misteri secara langsung lewat Flux *Free Tier* dan warga berlomba menebak objek/karakter di dalamnya!
- **`⛓️ Sambung Kata Indonesia` (+5 Poin/Kata):** Permainan berantai menyambung huruf terakhir kata sebelumnya (hingga 15 rantai kata, **0 panggilan API Gemini per giliran** sehingga super ringan & bebas kuota!).
- **`🧠 Kuis Trivia Cepat A/B/C/D` (+15 Poin):** Adu cepat klik tombol pilihan ganda A/B/C/D langsung di layar (1x kesempatan per orang per ronde!).
- **`🕵️ Tebak Kata Misteri` (+20 Poin):** Permainan *"Siapakah / Apakah Aku?"* dengan 3 petunjuk bertingkat + tombol **💡 Buka Petunjuk**.
- **`🔀 Susun Huruf Acak` (+15 Poin):** Adu cepat menyusun kata Bahasa Indonesia yang hurufnya diacak.
- Seluruh skor kemenangan tersimpan permanen per server di `data/game_scores.json` dan dapat dilihat kapan saja lewat **`/game papan_skor`**!

#### 12. 📌 Memori Info & FAQ Resmi Server (`/agent info`), ☀️ Koran Pagi (`/agent digest`), & 🎛️ Panel Admin (`/agent panel`)
- **Memori Info & FAQ Server (`/agent info`):** Admin dapat menyimpan hingga **25 entri pengetahuan resmi server** (seperti *Rules*, IP Server Minecraft/FiveM, jadwal mabar, cara *open ticket*, atau link sosial media). AI otomatis menghafal dan menjawab akurat berdasarkan data ini baik di channel publik, Forum, maupun ruang konsultasi privat!
- **Koran & Sapaan Pagi Otomatis (`/agent digest`):** Setiap pagi sesuai jam pilihan (default **`07:00`** waktu lokal), bot otomatis merangkum berita terhangat hari ini + fakta unik pembuka hari ke channel pilihan (dilengkapi proteksi anti-dobel kirim di tanggal yang sama).
- **Panel Kontrol Admin Interaktif (`/agent panel`):** Atur semua fitur channel (Auto-Chat, Galeri, YouTube, Cari, Welcome, Digest), ubah Persona, hingga tambah FAQ Server langsung lewat menu *dropdown* & *popup form (Modal)* tanpa perlu menghafal banyak parameter command!

---

### C. Fitur Keamanan, Ketahanan & Performa

1. **💾 Memori Tahan Restart Ganda (*Dual-Layer Persistence*):**
   - Semua sesi privat tersimpan otomatis ke `data/sessions.json` dan pengaturan AI Agent tersimpan di `data/agent_config.json` secara atomik.
   - Bahkan jika container Wispbyte di-*rebuild* bersih sekalipun, ketika member lanjut chat di thread `ai-...` lama, bot mampu membaca ulang riwayat thread Discord untuk memulihkan konteks percakapan secara otomatis!
2. **⚡ *Circuit-Breaker* Anti-503 & Rantai *Auto-Fallback* Instan:**
   - Jika suatu model Gemini sedang mengalami lonjakan trafik (`HTTP 503`) atau batas *rate-limit* (`HTTP 429`), bot langsung berpindah ke model sehat berikutnya (`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-3.6-flash` → `gemini-3.8-flash`) dalam **0 detik** dan menandai model penuh ke masa *cooldown* selama **3 menit** agar chat berikutnya tidak ikut tertahan.
3. **✂️ Pemotong Pesan Cerdas Anti-Rusak Kode Markdown:**
   - Discord membatasi 2.000 karakter per pesan. Jika Gemini menulis tutorial kode sepanjang 5.000 karakter, bot memotong pesan tepat di batas baris/paragraf serta **otomatis menutup (```` ``` ````) dan membuka ulang blok kode (```` ```python ````)** di bagian selanjutnya agar tampilan kode tidak pernah berantakan.
4. **🔐 Proteksi Token & Anti-Spam:**
   - Autentikasi memakai header `x-goog-api-key` (bukan parameter URL) plus penyensoran otomatis sehingga `GEMINI_API_KEY` dan `DISCORD_BOT_TOKEN` tidak pernah bocor ke pesan error Discord.
   - Pembatasan maksimal ruang privat aktif per member (`MAX_THREADS_PER_USER=3`) agar server aman dari spam pembuatan thread.
   - Seluruh tombol memiliki `custom_id` persisten sehingga tetap berfungsi walau bot habis di-*restart*.

---

## 🎮 Panduan Cara Pakai Semua Fitur (Step-by-Step)

### 1. Cara Memasang & Memakai Panel Ruang Privat AI

#### 👑 Untuk Admin Server:
1. Buat atau buka channel teks khusus untuk panel AI (misal `#ai-assistant`).
2. Ketik perintah berikut lalu tekan Enter:
   ```text
   /setup_panel
   ```
   *(Atau bisa juga menggunakan prefix `!setup_panel`).*
3. Bot akan menampilkan kotak **✨ GEMINI AI AUTOMATION PANEL** dengan dua tombol permanen yang siap dipakai seluruh member 24/7.

#### 👤 Untuk Member Server:
- **Mulai Ruang Chat AI, Vision & Koding:**
  1. Klik tombol hijau **💬 Chat AI (Teks & Vision)** pada panel.
  2. Pilih salah satu dari **5 Mode Kepribadian Gemini** (Utama, Kilat, Koding, Riset, atau Curhat).
  3. Klik tautan thread privat `ai-namakamu` yang dibuatkan bot, lalu:
     - Ketik pertanyaan apa saja untuk mengobrol.
     - Lampirkan **foto/screenshot** atau **file kode** (`.py`, `.js`, `.txt`, dll.) jika ingin dianalisis langsung.
     - Pilih menu dropdown **🎭 Ganti Mode** (atau ketik `/model`) jika ingin berganti kepribadian di tengah obrolan.
     - Klik **🔄 Reset Sesi** (atau `/reset`) untuk menghapus ingatan topik lama.
     - Klik **🔴 Akhiri Sesi** jika sudah selesai — rekap percakapan lengkap dalam bentuk file `.txt` akan dikirim otomatis ke DM Anda!

- **Mulai Ruang Generate & Edit Gambar AI:**
  1. Klik tombol biru **🎨 Generate Gambar AI** pada panel.
  2. Masuk ke thread privat `draw-namakamu` yang dibuatkan bot:
     - Pilih **Gaya Art** (Anime, Cyberpunk, Photorealistic, 3D Render, Pixel Art, Watercolor, atau Biasa) dan **Rasio Ukuran** (`1:1`, `16:9`, `9:16`, `4:3`, `3:4`) lewat menu dropdown di atas.
     - **Buat Gambar Baru:** Cukup ketik deskripsi gambar (contoh: `kucing astronot duduk di bulan sambil minum kopi`) lalu kirim.
     - **Edit Gambar *(Paid Tier Gemini)*:** Lampirkan sebuah gambar disertai instruksi perubahan pada pesan yang sama.

---

### 2. Cara Mengaktifkan & Mengatur AI Agent Komunitas (Khusus Admin)

#### A. Mengaktifkan Auto-Chat & Pemecah Sepi Otomatis (`/agent chat`)
Jalankan perintah ini untuk membuat AI ikut berbaur di channel obrolan umum (misal `#welcome` atau `#general`):
```text
/agent chat channel:#welcome aktif:True mode_balas:Cerdas dan Natural - Rekomendasi menit_sepi:30
```
- **Pilihan `menit_sepi` fleksibel:** Saat kolom `menit_sepi` diklik (baik di PC maupun HP Android/iOS), akan muncul pilihan siap klik:
  - `30 detik - Tes Kilat` *(cocok untuk mengetes fitur pemecah sepi secara instan)*
  - `1 menit - Tes Cepat`
  - `5 menit` / `15 menit` / `30 menit - Rekomendasi` / `60 menit - 1 Jam`
  - `0 - Matikan Pemecah Sepi`
  - Atau ketik manual angka bebas seperti `10`, `45`, `45 detik`, `2 jam`.

#### B. Mengetes Sapaan Pemecah Sepi Detik Itu Juga (`/agent sapa`)
Ingin melihat AI menyapa warga sekarang juga tanpa menunggu timer `menit_sepi` habis? Ketik:
```text
/agent sapa channel:#welcome
```
*(Menjalankan `/agent sapa` tidak akan merusak atau mengunci timer otomatis `menit_sepi` yang sedang berjalan).*

#### C. Mengaktifkan Auto-Komentar Foto & Video di Galeri (`/agent gallery`)
Agar bot otomatis mengomentari dan memberi emoji pada kiriman foto/video member di channel showcase/galeri:
```text
/agent gallery channel:#galeri aktif:True auto_reaction:True
```

#### D. Mengaktifkan AI Auto-Welcomer Member Baru (`/agent welcome`)
Agar setiap member baru disambut hangat secara otomatis & anti-monoton:
```text
/agent welcome channel:#welcome aktif:True pesan_tambahan:Jangan lupa mampir ambil role di #roles ya tes_sekarang:True
```

#### E. Merangkum Chat yang Ketinggalan (`/ringkas`)
Bisa dipakai oleh semua member saat baru buka Discord dan tertinggal obrolan panjang:
```text
/ringkas jumlah:50 Pesan Terakhir - Default publik:False
```

#### F. Mengatur Kepribadian, Nama Akrab, Zona Waktu, & Jam Tenang (`/agent persona`)
Sesuaikan karakter AI Agent dengan gaya tongkrongan server Anda:
```text
/agent persona gaya_bahasa:Gaul Tongkrongan Discord (Gue/Lu) nama_panggilan:Whas zona_waktu:WIB - Waktu Indonesia Barat (Asia/Jakarta) jam_tenang_malam:True konteks_komunitas:Server komunitas mabar game dan nongkrong santai
```
*(Tips: Setelah mengatur `nama_panggilan:Whas`, member bisa langsung memanggil nama **Whas** di chat tanpa perlu `@mention` atau slash command!)*

#### G. Mengaktifkan Rangkum YouTube/Web & Pencarian Berita Per-Channel (`/agent youtube` & `/agent cari`)
Kedua fitur ini bersifat **per-channel** — Anda bisa mengaktifkannya di satu channel maupun di beberapa channel sekaligus!
- **Aktifkan Rangkum YouTube & Link Web di Channel Pilihan:**
  ```text
  /agent youtube channel:#share-video aktif:True auto_di_channel:False
  ```
  - `auto_di_channel:False` (**Rekomendasi & Default**): Bot diam saat warga sekadar share link biasa di channel tersebut, namun **langsung merangkum** jika nama bot dipanggil / di-*mention* / di-*reply* bersama link tersebut, atau lewat `/ringkas_link`.
  - `auto_di_channel:True`: Bot otomatis merangkum setiap link YouTube/Web yang dikirim di channel tersebut (cocok untuk channel khusus `#rangkum-youtube`).
- **Aktifkan Pencarian Berita & Web Terkini di Channel Pilihan:**
  ```text
  /agent cari channel:#berita-terkini aktif:True auto_di_chat:True
  ```
  - `auto_di_chat:True` (**Default**): Di channel tersebut member bisa memakai `/cari pertanyaan:...` **sekaligus** memanggil nama bot langsung di chat (contoh: *"Whas coba cari berita hari ini tentang Timnas Indonesia"*).
  - `auto_di_chat:False`: Pencarian di channel tersebut hanya jalan lewat command `/cari`.

#### H. Bermain Mini-Game Tongkrongan (`/game`) & Pintasan Tekan-Tahan Pesan (*Apps*)
- **Mulai Mini-Game Interaktif:**
  ```text
  /game mulai jenis:🎲 Acak (Kejutan!)
  ```
  Lalu cek klasemen skor tertinggi di server kapan saja dengan `/game papan_skor`.
- **Terjemahkan / Jelaskan Pesan Tanpa Command:**
  Tekan-tahan pesan di HP (atau klik kanan di PC) ➔ pilih menu **Apps** ➔ klik **`🌐 Terjemahkan ke Indonesia`** atau **`💡 Jelaskan Pesan Ini`**.

#### I. Mengecek Daftar Channel Aktif & Sisa Hitung Mundur (`/agent status` & `/status`)
- Ketik **`/agent status`** untuk melihat seluruh daftar channel yang aktif (Auto-Chat, Welcome, Galeri, **YouTube**, dan **Pencarian `/cari`**) beserta **sisa waktu hitung mundur pemecah sepi** secara *real-time*.
- Ketik **`/status`** untuk mengecek ping koneksi Discord, pemakaian RAM Wispbyte, *uptime*, dan model Gemini yang sedang aktif.

---

## 🛑 Cara Mematikan (*Disable*) Fitur Kapan Saja

Semua fitur dapat dimatikan satu per satu **langsung lewat Discord tanpa perlu mematikan atau me-*restart* bot**:

| Fitur yang Ingin Dimatikan | Cara / Perintah Discord |
| :--- | :--- |
| **Matikan Auto-Chat & Pemecah Sepi total** di suatu channel | `/agent chat channel:#welcome aktif:False` |
| **Matikan Pemecah Sepi saja** *(tapi Auto-Chat tetap aktif membalas warga)* | `/agent chat channel:#welcome aktif:True menit_sepi:0` |
| **Matikan AI Auto-Welcomer member baru** | `/agent welcome channel:#welcome aktif:False` |
| **Matikan Auto-Komentar Galeri total** di suatu channel | `/agent gallery channel:#galeri aktif:False` |
| **Matikan Auto-Reaction Emoji saja** di Galeri *(komentar teks tetap jalan)* | `/agent gallery channel:#galeri aktif:True auto_reaction:False` |
| **Matikan fitur Rangkum YouTube & Link Web** di suatu channel | `/agent youtube channel:#share-video aktif:False` |
| **Matikan Auto-Rangkum semua link** di channel YouTube *(agar hanya rangkum saat dipanggil / `/ringkas_link` — **Default**)* | `/agent youtube channel:#share-video aktif:True auto_di_channel:False` |
| **Matikan fitur Pencarian Berita/Web (`/cari`)** di suatu channel | `/agent cari channel:#berita-terkini aktif:False` |
| **Matikan Auto-Search saat ngobrol** di channel Cari *(agar hanya jalan kalau ketik `/cari`)* | `/agent cari channel:#berita-terkini aktif:True auto_di_chat:False` |
| **Matikan Jam Tenang Malam (23:00–06:00)** *(agar sapaan tetap jalan tengah malam)* | `/agent persona jam_tenang_malam:False` |
| **Reset Nama Panggilan / Konteks Komunitas kembali ke default** | `/agent persona nama_panggilan:- konteks_komunitas:-` *(isi tanda strip `-`)* |
| **Tutup 1 Ruang Sesi Privat (`ai-...` / `draw-...`)** | Klik tombol merah **🔴 Akhiri Sesi** di dalam thread tersebut |
| **Nonaktifkan Panel Utama AI** di suatu channel | Hapus pesan Embed **✨ GEMINI AI AUTOMATION PANEL** di channel tersebut |

---

## 📋 Daftar Lengkap Command & Tombol

### 1. Menu Tekan-Tahan Pesan / Klik Kanan (*Apps*)
| Menu Apps | Akses | Keterangan |
| :--- | :--- | :--- |
| **`🌐 Terjemahkan ke Indonesia`** | Semua Member | Tekan-tahan / klik kanan pesan siapa saja (teks, embed, gambar, PDF, atau Voice Note) untuk menerjemahkannya ke Bahasa Indonesia secara privat. |
| **`💡 Jelaskan Pesan Ini`** | Semua Member | Tekan-tahan / klik kanan pesan rumit, istilah asing, error koding, atau meme untuk mendapatkan penjelasan ringkas. |
| **`🔍 Cek Fakta / Hoaks`** | Semua Member | Tekan-tahan / klik kanan pesan klaim berita atau *screenshot* untuk memeriksa kebenaran faktanya secara objektif beserta tautan sumber berita. |

### 2. Slash & Prefix Commands Umum, Pintasan & Hiburan
| Command | Akses | Keterangan |
| :--- | :--- | :--- |
| `/setup_panel` atau `!setup_panel` | Administrator | Memasang Embed & tombol Panel Utama AI (Chat & Gambar) di channel saat ini. |
| `/cari` | Semua Member | Mencari berita, skor, cuaca, kurs, & fakta terbaru hari ini via **Live Web & News Search** gratis + sumber web. |
| `/ringkas_link` | Semua Member | Merangkum isi video **YouTube** atau artikel website secara instan (bisa disertai pertanyaan). |
| `/ringkas` | Semua Member | Merangkum `25`–`150` obrolan terakhir di channel agar tidak ketinggalan topik (*TL;DR*). |
| `/game mulai` | Semua Member | Memulai ronde Mini-Game AI (`emoji`, `image_guess`, `word_chain`, `trivia`, `riddle`, `scramble`, atau acak kejutan). |
| `/game papan_skor` | Semua Member | Menampilkan Top 10 Klasemen Papan Skor Mini-Game server beserta peringkat Anda. |
| `/game stop` | Pemulai / Moderator | Menghentikan ronde Mini-Game yang sedang berjalan di channel saat ini. |
| `/game reset_skor` | Administrator | Mereset seluruh Papan Skor Mini-Game server kembali ke `0` untuk musim baru. |
| `/bantuan` | Semua Member | Menampilkan panduan ringkas seluruh fitur & cara pakai bot di Discord. |
| `/model` | Pemilik Ruang Sesi | Mengganti mode kepribadian Gemini (Utama, Kilat, Koding, Riset, Curhat) di ruang `ai-...`. |
| `/reset` | Pemilik Sesi / Moderator | Menghapus memori obrolan di `ai-...` atau mereset setelan gambar di `draw-...`. |
| `/status` | Semua Member | Menampilkan ping Discord, pemakaian RAM (MB), uptime, jam AI, model aktif, & jumlah sesi. |

### 3. Slash Commands Admin untuk AI Agent Komunitas (`/agent`)
| Command | Parameter Utama | Keterangan |
| :--- | :--- | :--- |
| `/agent panel` | — | Membuka **Panel Kontrol Admin Interaktif** (dropdown pilih channel, toggle fitur klik langsung, & form Modal Persona/FAQ). |
| `/agent info` | `aksi`, `topik`, `isi` | Mengelola **Memori Info & FAQ Resmi Server** (maks. 25 entri: rules, IP server, jadwal, link) agar AI selalu menjawab akurat. |
| `/agent digest` | `channel`, `aktif`, `jam`, `topik`, `tes_sekarang` | Mengaktifkan/mematikan jadwal pengiriman **Koran & Sapaan Pagi Otomatis** setiap hari di channel pilihan. |
| `/agent chat` | `channel`, `aktif`, `mode_balas`, `menit_sepi` | Mengaktifkan/mematikan Auto-Chat di Text Channel maupun **Channel Forum** (+ Pemecah Sepi di Text Channel). |
| `/agent welcome` | `channel`, `aktif`, `pesan_tambahan`, `tes_sekarang` | Mengaktifkan/mematikan AI Auto-Welcomer natural untuk member baru. |
| `/agent gallery` | `channel`, `aktif`, `auto_reaction` | Mengaktifkan/mematikan Auto-Komentar Foto & Video di Text Channel maupun **Forum/Media Showcase**. |
| `/agent youtube` | `channel`, `aktif`, `auto_di_channel` | Mengaktifkan/mematikan rangkum YouTube/Web (`/ringkas_link` & baca link) pada satu/beberapa Text Channel atau **Channel Forum**. |
| `/agent cari` | `channel`, `aktif`, `auto_di_chat` | Mengaktifkan/mematikan pencarian berita/web (`/cari` & auto-search) pada satu/beberapa Text Channel atau **Channel Forum**. |
| `/agent persona` | `gaya_bahasa`, `nama_panggilan`, `zona_waktu`, `jam_tenang_malam`, `konteks_komunitas` | Mengubah nama akrab AI, gaya bicara (*Akrab / Gaul / Ramah*), zona waktu (*WIB/WITA/WIT*), Jam Tenang, & deskripsi komunitas. |
| `/agent sapa` | `channel` *(opsional)* | Memicu AI Agent langsung menyapa / memecah sepi detik ini juga (untuk tes instan). |
| `/agent status` | — | Melihat status profil AI Agent, daftar channel aktif, & sisa hitung mundur pemecah sepi. |

---

## ⚙️ Penjelasan Variabel `.env`

Hanya **2 variabel pertama** yang wajib diisi; sisanya bersifat opsional dan sudah memiliki nilai default terbaik:

| Variabel | Wajib? | Default | Fungsi |
| :--- | :---: | :--- | :--- |
| `DISCORD_BOT_TOKEN` | ✅ **Wajib** | — | Token bot dari Discord Developer Portal (juga mendukung alias `DISCORD_TOKEN`). |
| `GEMINI_API_KEY` | ✅ **Wajib** | — | API Key dari [Google AI Studio](https://aistudio.google.com/apikey) *(bisa isi 1 key atau beberapa key dipisahkan koma `key1,key2` untuk rotasi otomatis)*. |
| `DISCORD_GUILD_ID` | Opsional | *(kosong)* | Isi ID Server Discord Anda jika ingin Slash Commands baru langsung muncul instan (<1 detik) & bebas duplikat command global. |
| `GEMINI_DEFAULT_MODEL` | Opsional | `gemini-3.5-flash-lite` | Model utama cepat & stabil (bebas *503 overload* di *Free Tier*) untuk chat umum, curhat, Vision, & AI Agent. |
| `GEMINI_FAST_MODEL` | Opsional | `gemini-3.1-flash-lite` | Model ultra-kilat untuk mode Respon Kilat & cadangan instan. |
| `GEMINI_REASONING_MODEL` | Opsional | `gemini-3.6-flash` | Model penalaran untuk mode Pakar Koding & Riset. |
| `ENABLE_GOOGLE_SEARCH` | Opsional | `true` | Mengizinkan modul Live Search aktif (pengaturan per-channel dikontrol dari Discord lewat `/agent cari`). |
| `ENABLE_URL_READER` | Opsional | `true` | Mengizinkan modul perangkum YouTube/Web aktif (pengaturan per-channel dikontrol dari Discord lewat `/agent youtube`). |
| `GEMINI_PAID_SEARCH_ENABLED` | Opsional | `false` | Biarkan `false` pada *Free Tier* agar memakai mesin pencari web & berita gratis mandiri tanpa error kuota 0. Ubah ke `true` hanya jika akun AI Studio sudah *Paid/Billing*. |
| `GEMINI_SEARCH_MODEL` | Opsional | `gemini-2.5-flash` | Model yang dipakai jika `GEMINI_PAID_SEARCH_ENABLED=true`. |
| `GEMINI_PAID_IMAGE_ENABLED` | Opsional | `false` | Biarkan `false` pada *Free Tier* agar langsung memakai Flux gratis secara instan. Ubah ke `true` jika akun AI Studio sudah *Paid/Billing* untuk memakai Nano Banana / Pro. |
| `GEMINI_IMAGE_MODEL` | Opsional | `gemini-3.1-flash-lite-image` | Model gambar Gemini saat `GEMINI_PAID_IMAGE_ENABLED=true` (bisa diisi `gemini-3-pro-image` untuk Nano Banana Pro). |
| `ENABLE_IMAGE_FALLBACK` | Opsional | `true` | Mengaktifkan generator gambar gratis Flux. |
| `MAX_HISTORY_MESSAGES` | Opsional | `30` | Jumlah riwayat pesan terakhir yang diingat per ruang chat privat. |
| `MAX_THREADS_PER_USER` | Opsional | `3` | Maksimal ruang privat aktif yang boleh dibuka bersamaan oleh 1 member. |
| `BOT_TIMEZONE` | Opsional | `Asia/Jakarta` | Zona waktu default (`Asia/Jakarta`, `Asia/Makassar`, atau `Asia/Jayapura`). |
| `AGENT_DEFAULT_IDLE_MINUTES` | Opsional | `30` | Durasi hening default (menit) sebelum AI Agent memecah kesunyian. |
| `SESSION_EXPIRE_DAYS` | Opsional | `7` | Otomatis membersihkan data sesi privat yang sudah menganggur lebih dari N hari (`0` = nonaktif). |
| `USER_COMMAND_COOLDOWN_SEC` | Opsional | `10` | Jeda wajar per-member (detik) antar pemakaian command berat (`/cari`, `/ringkas_link`, `/ringkas`) demi melindungi kuota *Free Tier* (`0` = nonaktif; Admin otomatis bebas jeda). |

---

## 🔑 Persiapan di Discord Developer Portal

Sebelum menyalakan bot di Wispbyte, pastikan pengaturan berikut sudah aktif:

1. Buka [Discord Developer Portal](https://discord.com/developers/applications) → pilih aplikasi bot Anda.
2. Buka tab **Bot**:
   - Salin **Token** untuk dimasukkan ke `DISCORD_BOT_TOKEN`.
   - Gulir ke bagian **Privileged Gateway Intents**, lalu **AKTIFKAN**:
     - ✅ **Message Content Intent** *(Sangat wajib! Tanpa ini bot tidak bisa membaca isi teks chat maupun lampiran)*
     - ✅ **Server Members Intent** *(Direkomendasikan agar fitur `/agent welcome` bisa menyambut member baru di channel mana saja)*
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
2. **Cara Paling Praktis (Git Auto-Update — Rekomendasi):**
   - Di tab **Startup** Wispbyte, isi **Git Repo Address** dengan URL repository GitHub Anda, isi **Git Branch** dengan `main` (huruf kecil), nyalakan **Auto Update = ON**, dan matikan **User Uploaded Files = OFF**. Setiap kali Anda klik **Restart**, Wispbyte otomatis menarik versi terbaru dari GitHub!
   - *(Alternatif manual)* Buka menu **Files** di panel Wispbyte, lalu unggah `main.py`, `community_agent.py`, `games.py`, `ai_handler.py`, `views.py`, `storage.py`, `utils.py`, `config.py`, dan `requirements.txt`.
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
   ✅ Bot v1.3.0-beta aktif sebagai NamaBot#0000 | Python 3.11+ | discord.py 2.7+ | RAM: ~52.0 MB
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
├── main.py             # Entrypoint utama bot, Context Menus, Slash Commands, & event handler
├── community_agent.py  # Mesin AI Agent Komunitas (Auto-Chat anti-nimbrung, Welcome, Pemecah Sepi, & Galeri)
├── games.py            # Mesin Mini-Game Tongkrongan AI (Trivia, Emoji, Misteri, Acak Kata) & Papan Skor
├── ai_handler.py       # Klien async Gemini API (Chat, Vision, Voice Note, YouTube/Web, & Free Live Search)
├── views.py            # Komponen tombol & dropdown UI Discord persisten tahan restart
├── storage.py          # Penyimpanan sesi privat JSON atomik & auto-recovery dari Discord Thread
├── utils.py            # Pemotong kode Markdown, Live Web/News Search gratis, filter etika chat, & jam lokal
├── config.py           # Konfigurasi variabel .env, daftar 5 kepribadian Gemini, gaya & rasio gambar
├── requirements.txt    # Daftar dependensi Python super ringan
├── .env.example        # Template contoh pengisian variabel .env
├── .gitignore          # Mencegah file rahasia (.env) & folder data sesi ikut ter-commit ke Git
├── LICENSE             # Lisensi Open-Source MIT
└── tests/              # Pengujian otomatis (pytest — 40 test) untuk memastikan seluruh modul bebas bug
```

---

## 📄 Lisensi

Proyek ini dirilis menggunakan **[MIT License](LICENSE)** — bebas digunakan, dipelajari, dan dikembangkan dengan tetap mencantumkan atribusi pembuat asli.

---

## ❓ FAQ & Solusi Masalah Umum

- **Apakah semua fitur (termasuk `/cari` berita, rangkum YouTube, & buat gambar) aman untuk akun Gemini *Free Tier* tanpa kartu kredit?**
  **100% aman & langsung jalan!** Secara default (`GEMINI_PAID_SEARCH_ENABLED=false` dan `GEMINI_PAID_IMAGE_ENABLED=false`), bot menggunakan mesin pencari web/berita gratis mandiri dan generator gambar Flux gratis sehingga bebas dari error `You exceeded your current quota`.
- **Apakah bot bisa dipakai di dalam Channel Forum Discord (`Forum Channel`)?**
  **Bisa penuh!** Anda tinggal memilih nama Channel Forum pada parameter `channel:` saat menjalankan `/agent chat`, `/agent gallery`, `/agent youtube`, atau `/agent cari`. Bot akan otomatis membaca **Judul Postingan, Tag Forum, isi teks, gambar, Voice Note, maupun file kode** di setiap postingan forum tersebut tanpa mencampur ingatan antar-postingan (serta mendukung `/ringkas`, `/ringkas_link`, `/cari`, `/game`, dan tekan-tahan pesan *Apps* di dalam postingan forum).
- **Kenapa bot diam atau menolak saat ada member kirim link YouTube / ketik `/cari` di channel publik?**
  Fitur YouTube dan Pencarian Web kini diatur **per-channel** agar rapi dan tidak mengganggu obrolan warga di sembarang tempat. Pastikan Admin sudah mengaktifkan channel tersebut lewat **`/agent youtube channel:#nama-channel aktif:True`** atau **`/agent cari channel:#nama-channel aktif:True`**. Di channel YouTube yang aktif dengan `auto_di_channel:False` (default), cukup **panggil nama akrab bot / `@mention` / *reply*** bersama link tersebut atau gunakan **`/ringkas_link`**. *(Jika ingin bot otomatis merangkum setiap link di channel khusus, gunakan `auto_di_channel:True`).*
- **Slash Commands (`/setup_panel`, `/agent`) belum muncul atau tampilannya belum ter-update di HP?**
  Isi `DISCORD_GUILD_ID` di `.env` dengan ID Server Discord Anda agar sinkronisasi instan (<1 detik), lalu *restart* bot. Jika memakai aplikasi Discord di HP (Android/iOS), **tutup paksa (*force close*) lalu buka ulang aplikasi Discord sekali** agar cache tampilan *Slash Command* di HP diperbarui.
- **Pemecah Sepi (`menit_sepi`) belum menyapa saat dites malam hari?**
  Secara default fitur **Jam Tenang Malam (23:00 – 06:00)** aktif agar AI tidak membangunkan warga saat jam tidur. Jika Anda sedang mengetes di atas jam 23:00 malam, matikan sementara dengan `/agent persona jam_tenang_malam:False` atau gunakan `/agent sapa` untuk tes instan. Anda juga bisa mengecek sisa hitung mundur lewat `/agent status`.
- **Bot online tapi tidak merespons pesan teks di ruang chat?**
  Pastikan **Message Content Intent** sudah dinyalakan di [Discord Developer Portal](https://discord.com/developers/applications) pada bagian *Bot → Privileged Gateway Intents*, lalu *restart* bot di Wispbyte.
- **Gagal membuat ruang privat (`Missing Permissions`)?**
  Pastikan Role bot di channel tersebut memiliki izin `Create Private Threads`, `Send Messages in Threads`, dan `Read Message History`.
