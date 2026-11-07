# ✨ Penjelasan Lengkap Semua Fitur (A–W)

Dokumen ini memuat penjelasan panjang **23 area fitur** bot. Sengaja dipisah dari
[README](../README.md) supaya halaman depan tetap ringkas dan cepat dibaca.

- Butuh cara memasang? Lihat [README](../README.md) — `.env`, Developer Portal, deploy Wispbyte.
- Butuh daftar command? Lihat [daftar command lengkap](command.md).
- Butuh versi ringkas di dalam Discord? Pakai `/bantuan`.

## Daftar Bagian

- [A. Fitur Ruang Sesi Privat (`/sesi`)](#a-fitur-ruang-sesi-privat-sesi)
- [B. Fitur AI Agent & Otomasi Komunitas (`/agent`)](#b-fitur-ai-agent--otomasi-komunitas-agent)
- [C. Fitur Keamanan, Ketahanan & Performa](#c-fitur-keamanan-ketahanan--performa)
- [D. Fitur Server Otomatis (`/serverstats`, `/autorole`, `/fakta`, `/keamanan`)](#d-fitur-server-otomatis-serverstats-autorole-fakta-keamanan)
- [E. Fitur Komunitas Ringan (`/panel-role`, `/poll`, `/saran`, `/embed`, `/tempvoice`)](#e-fitur-komunitas-ringan-panel-role-poll-saran-embed-tempvoice)
- [F. Streaming Musik 24/7 (`/musik` + Lavalink)](#f-streaming-musik-247-musik--lavalink)
- [G. Fitur Keramaian Server (`/giveaway`, `/ultah`, `/jawab-otomatis`, `/pengumuman`)](#g-fitur-keramaian-server-giveaway-ultah-jawab-otomatis-pengumuman)
- [H. Anti-Spam & Anti-Raid Ringan (`/keamanan spam`)](#h-anti-spam--anti-raid-ringan-keamanan-spam)
- [I. Level & XP serta Tiket Dukungan (`/level`, `/tiket`)](#i-level--xp-serta-tiket-dukungan-level-tiket)
- [J. Dashboard Web (`DASHBOARD_TOKEN`)](#j-dashboard-web-dashboard_token)
- [K. Penerjemah Hemat Kuota (`/terjemah`)](#k-penerjemah-hemat-kuota-terjemah)
- [L. Hemat Kuota AI (`/pemakaian`, `/ringkas channel`, `/faq`)](#l-hemat-kuota-ai-pemakaian-ringkas-channel-faq)
- [M. Tampilan Panel Components V2 (`/panel`, `/tampilan`)](#m-tampilan-panel-components-v2-panel-tampilan)
- [N. Audit Log Server (`/log`)](#n-audit-log-server-log)
- [O. Ekonomi Koin (`/ekonomi`)](#o-ekonomi-koin-ekonomi)
- [P. Pertumbuhan Server & Invite Tracker (`/tumbuh`)](#p-pertumbuhan-server--invite-tracker-tumbuh)
- [Q. Menu Builder & Self Roles v2 (`/menu`)](#q-menu-builder--self-roles-v2-menu)
- [R. Anti-Nuke (`/nuke`)](#r-anti-nuke-nuke)
- [S. Raid Guard (`/raid`)](#s-raid-guard-raid)
- [T. Bahasa Antarmuka (`/bahasa`)](#t-bahasa-antarmuka-bahasa)
- [U. Prefix Command per Server (`/prefix`)](#u-prefix-command-per-server-prefix)
- [V. Ekspor Analitik CSV & Webhook (`/analitik`)](#v-ekspor-analitik-csv--webhook-analitik)
- [W. Audit RAM & Cache (`/perawatan memori`)](#w-audit-ram--cache-perawatan-memori)

---

## 🚀 Mulai cepat: `/mulai`

Bagi admin baru, cara tercepat memasang bot adalah **satu command** ini — tanpa perlu tahu
nama command lain:

```text
/mulai paket:🏡 Server Komunitas channel_sambutan:#sambutan role_otomatis:@Member channel_log:#log
```

| Paket | Menyalakan |
| :--- | :--- |
| 🏡 **Server Komunitas** | Sambutan + auto role + log moderasi + pengumuman terjadwal |
| 🎮 **Server Gaming** | Auto role + sambutan + pengumuman event |
| 🎓 **Server Sekolah** | Sambutan + auto role kelas + log moderasi |

- Semua parameter opsional: `/mulai` saja akan menampilkan daftar paket & contoh pemakaian.
- Tambahkan `pratinjau:True` untuk melihat rencananya **tanpa mengubah apa pun** — cocok untuk
  memastikan channel/role yang dipilih sudah benar.
- Setelah dipasang, bot merangkum apa yang aktif dan apa yang masih perlu diatur (mis. isi
  pengumuman). Semua tetap bisa diubah/dimatikan lewat command masing-masing.

## A. Fitur Ruang Sesi Privat (`/sesi`)

Admin cukup memasang satu panel permanen di channel khusus (misalnya `#ai-assistant`) menggunakan `/sesi panel` (atau `!setup_panel`). Dari panel tersebut, setiap member dapat membuka ruang privat (*Private Thread*) yang hanya bisa dilihat oleh member itu sendiri.

### 1. 💬 Chat AI Multi-Persona (5 Kepribadian Gemini)
Saat menekan tombol **💬 Chat AI (Teks & Vision)**, member bebas memilih 1 dari 5 mode kepribadian:
| Mode | Model Utama | Karakter & Kegunaan |
| :--- | :--- | :--- |
| **♊ Gemini Flash (Asisten Utama)** | `gemini-3.5-flash-lite` | Cerdas, ramah, cepat (~1 detik), & serba bisa untuk topik umum sehari-hari. |
| **⚡ Gemini Flash-Lite (Respon Kilat)** | `gemini-3.1-flash-lite` | Jawaban ringkas, padat, *to-the-point*, instan, & paling hemat kuota API. |
| **💻 Gemini - Pakar Koding & Debug** | `gemini-3.6-flash` | Spesialis pemrograman, struktur kode rapi, penjelasan logika, & bedah *bug*. |
| **🧠 Gemini - Penalaran & Riset** | `gemini-3.6-flash` | Analitis & sistematis *step-by-step* untuk matematika, sains, tugas, & riset. |
| **🛋️ Gemini - Teman Curhat** | `gemini-3.5-flash-lite` | Pendengar yang hangat, empatik, tidak menghakimi, dan suportif ala sahabat dekat. |

> 💡 **Ganti Mode Kapan Saja:** Di dalam ruang `ai-...`, tersedia menu *dropdown* dan command `/sesi model` untuk mengganti kepribadian Gemini di tengah percakapan **tanpa menghapus riwayat obrolan sebelumnya**.

### 2. 🎙️ Mendengar *Voice Note* (🎤), *Vision* Gambar, Link YouTube/Web, & *Live Search*
Di dalam ruang chat privat `ai-...`, member bisa langsung mengirim:
- **Voice Note / Pesan Suara Discord (🎤) & File Audio** (`.ogg`, `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac` — maks. 12 MB): Cukup tekan tombol mikrofon di Discord HP/PC lalu bicara — Gemini mendengarkan langsung isi ucapan beserta intonasinya dan menjawab nyambung tanpa perlu mengetik!
- **Link Video YouTube & Artikel Website**: Tempel langsung link YouTube (`youtube.com/watch`, `youtu.be`, `shorts`, `live`) atau URL berita/artikel untuk dirangkum dan didiskusikan isinya secara instan di ruang privat.
- **Pertanyaan Berita & Info Terkini Hari Ini**: Tanyakan berita terbaru, skor pertandingan, cuaca, harga emas/kurs, atau rilis teknologi terbaru — bot otomatis mencarikan sumber web aktual secara gratis di ruang privat.
- **Gambar / Screenshot** (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` — maks. 8 MB per gambar, hingga 4 gambar sekaligus): Cocok untuk menanyakan soal bergambar, desain UI, atau *screenshot* pesan *error* koding.
- **Dokumen PDF Native** (`.pdf` — maks. 10 MB): Unggah file materi kuliah, jurnal, panduan kerja, atau *e-book* PDF — Gemini langsung membaca dan membedah isinya secara utuh!
- **File Kode & Dokumen Teks** (`.py`, `.js`, `.ts`, `.tsx`, `.json`, `.yaml`, `.html`, `.css`, `.sql`, `.csv`, `.txt`, `.md`, `.log`, `.c`, `.cpp`, `.java`, `.go`, `.rs`, `.php`, dll. — maks. 100 KB per file): Bot otomatis membaca isi file dan memasukkannya sebagai konteks ke Gemini.
- **Stiker Discord**: Bot ikut mengenali visual stiker yang dikirim.

### 3. 🎨 Generate & Edit Gambar AI (`draw-...`)
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

### 4. 🔄 Reset Memori & 📜 Rekap Transkrip Lengkap ke DM
- **Tombol 🔄 Reset Sesi (atau `/sesi reset`):** Menghapus ingatan obrolan di ruang `ai-...` untuk ganti topik baru, atau mengembalikan setelan gaya/rasio gambar ke awal di ruang `draw-...` tanpa perlu membuat thread baru.
- **Tombol 🔴 Akhiri Sesi (atau `/sesi tutup`):**
  - Merangkum percakapan ke dalam **Embed Discord** yang rapi **sekaligus melampirkan file `rekap-nama-ruang.txt`** berisi transkrip percakapan utuh dari awal sampai akhir ke **DM pribadi member**.
  - Jika DM member dikunci/tertutup, bot otomatis mengirimkan file `.txt` tersebut di dalam thread dan memberi waktu **10 detik** untuk mengunduhnya sebelum ruang privat dihapus.

---

## B. Fitur AI Agent & Otomasi Komunitas (`/agent`)

Fitur ini membuat bot berbaur di channel publik server — baik di **Text Channel biasa (`#general`)** maupun di dalam **Channel Forum & Media (`#tanya-jawab`, `#showcase-karya`, `#forum-berita`)** — layaknya **warga/teman nongkrong asli** (bukan gaya kaku robot asisten). Seluruh fiturnya dikendalikan per-channel oleh Admin melalui command `/agent`:
- **Dukungan Penuh & Fitur Pintar Channel Forum (`ForumChannel` & `MediaChannel`):**
  - Saat `/agent chat`, `/agent gallery`, `/agent youtube`, atau `/agent cari` diaktifkan pada sebuah **Channel Forum**, bot otomatis bekerja di seluruh **Postingan (*Post/Thread*)** di dalam forum tersebut!
  - Membaca **Judul Postingan Forum**, **Tag Forum**, isi teks, gambar, dokumen **`.pdf`**, Voice Note, hingga **lampiran file kode** (`.py`, `.js`, `.json`, `.log`, dll.), serta menjaga ingatan obrolan **terpisah di masing-masing postingan** agar topik antar-postingan tidak pernah tercampur!
  - **🏷️ Auto-Tagging Forum Pintar (0 API Call):** Jika member membuat postingan forum baru tanpa memilih Tag, bot otomatis memilihkan 1–2 Tag Forum yang paling relevan dengan judul & isi topiknya tanpa memakan kuota API tambahan.
  - **✅ Tombol Persisten `Tandai Selesai`:** Pada balasan pembuka di Postingan Forum, bot menyematkan tombol hijau **`✅ Tandai Selesai`** yang bisa diklik oleh pembuat postingan atau Moderator untuk menambahkan awalan `✅`, memasang tag *Selesai/Solved*, dan mengarsipkan diskusi dengan rapi!

### 1. 💬 Auto-Chat Natural ala Manusia & Etika Anti-Nimbrung Pintar (`/agent chat`)
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

### 2. 💤 Pemecah Sepi Otomatis / *Dead-Chat Reviver* (`/agent chat` & `/agent sapa`)
- Jika channel Auto-Chat sepi tidak ada aktivitas selama **`menit_sepi`** (default **30 menit**, mendukung pilihan cepat maupun ketik fleksibel seperti `30 detik`, `1`, `5`, `15`, `30`, `60`, `1 jam`, atau `0` untuk mematikan), AI otomatis memulai obrolan santai sesuai suasana jam saat itu (*contoh malam hari: "Sepi banget nih, tumben pada ngilang pas jam santai gini, pada mabar diam-diam ya kalian? Wkwk."*).
- **Proteksi Anti-Monolog / Anti-Spam:** Jika setelah AI menyapa otomatis ternyata belum ada satu pun member yang membalas, AI **berhenti menyapa ulang** sampai ada member manusia yang chat lagi — sehingga channel tidak pernah penuh spam sendirian!
- **Jam Tenang Malam (*Quiet Hours*):** Secara default aktif pada pukul **23:00 – 06:00** waktu lokal agar AI tidak tiba-tiba memecah sepi jam 3 subuh saat member sedang tidur (bisa diatur lewat `/agent persona`).

### 3. 🕒 Kesadaran Waktu Lokal *Real-Time* (WIB / WITA / WIT)
- AI selalu tahu hari, tanggal, jam, dan menit saat ini secara presisi (mendukung **WIB**, **WITA**, dan **WIT**).
- Jika ditanya *"sekarang jam berapa?"* pada pukul 16:30, AI akan menjawab akurat pukul 16:30 dan mengaitkannya dengan suasana waktu tersebut (misalnya sore jam-jam rawan ngantuk, pagi semangat, siang terik, atau malam waktunya mabar).

### 4. 😄 Membaca Visual Stiker & Custom Emoji Server
- Saat member mengirim **Stiker Discord** (PNG/APNG/GIF) atau **Custom Emoji Server** (`<:nama:id>` / `<a:nama:id>`), bot mengunduh gambar visual stiker/emoji tersebut dan memindainya lewat **Gemini Vision**.
- Hasilnya, AI benar-benar "melihat" gambar stiker lucu atau ekspresi wajah pada emoji yang dikirim dan membalasnya secara relevan!

### 5. 📸 Gallery Auto-Comment: Scan Foto & Video (`/agent gallery`)
- Aktifkan di channel pamer karya, meme, fotografi, cosplay, setup PC, atau klip game (misal `#gallery` / `#media`).
- Setiap kali member mengirim **Foto/Gambar** (hingga 8 MB) atau **Video Klip Pendek** (`.mp4`, `.webm`, `.mov` hingga 15 MB):
  1. Bot otomatis men-scan isi visual gambar atau video tersebut menggunakan Gemini Multimodal.
  2. Memberikan **reaksi emoji otomatis** (`✨`, `🔥`, `😍`, `👏`, atau `🙌` — bisa dinyalakan/dimatikan).
  3. Membalas (*reply*) postingan tersebut dengan komentar spesifik yang menyebutkan detail unik di dalam foto/video (seperti warna kostum, karakter, latar tempat, atau momen serunya).

### 6. 👋 AI Auto-Welcomer Member Baru + Persona Sambutan Khusus (`/agent welcome`)
- **Persona sambutan TERPISAH dari persona Auto-Chat!** Pilih gaya sambutan lewat `persona:` — **🤗 Hangat & Tulus**, **😂 Lucu & Receh**, **😎 Santai & Akrab**, atau **🙂 Normal & Sopan**. Mengubah `/agent persona` (gaya obrolan harian) **tidak akan** mengacaukan gaya sambutan, begitu pula sebaliknya.
- **Kata sapaan "halo/hai" berganti-ganti dari 64 sapaan / 45 bahasa** — Asia Timur & Tenggara (`こんにちは` Jepang, `안녕하세요` Korea, `你好` Mandarin, `สวัสดี` Thailand, `Xin chào` Vietnam, `Kumusta` Filipina, `မင်္ဂလာပါ` Myanmar, `សួស្តី` Kamboja, `ສະບາຍດີ` Laos, `Ola` Timor Leste), Timur Tengah & India (`مرحبا` Arab, `سلام` Persia, `नमस्ते` Hindi, `வணக்கம்` Tamil), sampai Eropa & Afrika (`Привет` Rusia, `Γεια σου` Yunani, `שלום` Ibrani, `Bonjour` Prancis, `Hola` Spanyol, `Sawubona` Zulu). **Hanya kata sapaan pembuka** yang berbahasa asing — seluruh kalimat sambutan tetap **Bahasa Indonesia** yang hangat/lucu sesuai persona.
- **Huruf latin & terjemahannya ikut tampil**, jadi member yang tidak membaca aksaranya tetap paham. Formatnya: **`"မင်္ဂလာပါ"` (Mingalaba)** — *semoga berkah* → lalu kalimat Bahasa Indonesia. Huruf latin & arti ditempel oleh kode (bukan oleh AI) supaya konsisten dan tidak pernah salah tulis. Bisa dimatikan dengan `arti:False` (hanya aksara aslinya).
- **Kalimat sambutannya tetap dibuat AI (Gemini), bukan template.** Urutannya: kode memilih kata sapaan (acak, hindari pengulangan 8 sambutan terakhir) → AI menulis 1–2 kalimat sambutan sesuai persona, jam, tanggal, info tambahan, dan anti-monoton → kode menempelkan huruf latin + arti di depan. Kuota tetap **1 panggilan AI per member baru** (tidak ada panggilan tambahan), dan bila AI gagal/tanpa API key tidak ada pesan yang dikirim — sama seperti sebelumnya.
- Bisa memilih **satu bahasa** tertentu (`bahasa_sapaan:jepang`) atau **acak semua bahasa** (default, `auto`) agar setiap member baru mendapat sapaan yang berbeda.
- Tabel arti lengkap ada di `community_agent.ASIAN_GREETINGS` (`word` = aksara asli, `read` = huruf latin, `arti` = terjemahan Indonesia) — menambah bahasa baru cukup menambah satu baris di sana, dan otomatis muncul di `/agent welcome`, `/agent goodbye`, serta dashboard.
- Bisa ditambahkan `pesan_tambahan` (contoh: *"Jangan lupa ambil role di #roles ya"*) yang akan dirangkai secara luwes oleh AI, serta `tes_sekarang:True` untuk langsung melihat contoh sambutannya.

### 7. 👣 AI Auto-Goodbye: Kartu Perpisahan Member Keluar (`/agent goodbye`)
- Saat ada member keluar dari server, bot otomatis mengirim **kartu perpisahan** berisi pesan hangat + foto profil + **lama masa kebersamaan** (jumlah hari sejak bergabung).
- Punya **persona perpisahan sendiri** (Hangat / Lucu / Santai / Normal) dan **61 kata perpisahan dari 40+ bahasa** seperti `またね` (Mata ne — sampai nanti, Jepang), `안녕히 가세요` (Annyeonghi gaseyo — selamat jalan, Korea), `再见` (Zàijiàn — sampai jumpa, Mandarin), `ลาก่อน` (Lakorn, Thailand), `مع السلامة` (Ma'a as-salama, Arab), `Auf Wiedersehen` (Jerman), `Kwaheri` (Swahili), dan lainnya — sisa kalimat tetap Bahasa Indonesia.
- Format pesan perpisahan sama: **`"またね"` (Mata ne)** — *sampai nanti* `@member`, lalu kalimat hangatnya. Huruf latin & arti bisa dimatikan lewat `arti:False`.
- Kalimat perpisahannya **juga tetap ditulis AI** (1 panggilan per member keluar, dengan konteks lama bergabung & anti-monoton); kode hanya memilih kata perpisahan lalu menempelkan huruf latin + artinya.
- Anti-dobel: tetap ramah kuota karena hanya 1 pesan per member keluar dan ada deduplikasi otomatis.

### 8. 🖼️ Banner Gambar & Kartu Sambutan Dinamis (`/agent banner`, `/agent kartu`)

Sapphire punya welcome berbasis gambar; sekarang bot ini juga — tanpa dashboard, cukup lewat Discord.

- **`/agent banner gambar:<file> jenis:Sambutan`** — unggah gambar (PNG/JPG/WEBP/GIF, maks 8 MB) sebagai
  banner sambutan, perpisahan, atau pesan boost. Berkas disimpan di **`data/media/`**, **bukan** URL.
- **`/agent kartu mode:<pilihan>`** — tiga tampilan sambutan:
  | Mode | Hasil | Biaya |
  | :--- | :--- | :--- |
  | 💬 Teks | sambutan polos seperti sebelumnya | paling hemat |
  | 🖼️ Statis | embed: banner + teks sambutan + foto profil kecil | ringan |
  | ✨ Dinamis | **kartu PNG**: banner + foto profil bulat + nama + jumlah member | +10–15 MB RAM saat render |
- **`/agent dm aktif:True`** — kirim juga salinan sambutan lewat DM ke member baru
  (gagal senyap bila DM member ditutup).
- **`/agent boost channel:#umum`** — pesan terima kasih otomatis saat ada member **nge-boost** server,
  mendukung teks kustom `{user}`, `{name}`, `{guild}` + banner boost sendiri.

> **Kenapa gambarnya disimpan di server, bukan URL?**
> URL lampiran Discord (`cdn.discordapp.com/attachments/...`) mengandung tanda tangan yang **kedaluwarsa
> ±24 jam**. Kalau hanya URL yang disimpan, banner hilang besok. Karena itu berkasnya disimpan lokal lalu
> dikirim ulang sebagai lampiran (`attachment://`) setiap kali sambutan dikirim.
>
> Mode **dinamis** membutuhkan **Pillow** (sudah ada di `requirements.txt`). Bila Pillow tidak terpasang,
> bot otomatis mundur ke mode banner statis — tidak ada error.

### 9. 🔔 Notifikasi Sosial: YouTube, Twitch, TikTok, Reddit & RSS/Atom (`/sosial`)

Tidak perlu dashboard web seperti Sapphire — semua dari Discord, **0 kuota AI** (pesan memakai template).

| Platform | Sumber data | Kredensial |
| :--- | :--- | :--- |
| 🎬 **YouTube** | RSS resmi `youtube.com/feeds/videos.xml` | **tidak perlu** |
| 🟣 **Twitch** | Helix API (Client Credentials) | `TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET` (gratis di dev.twitch.tv) |
| 🎵 **TikTok / RSS** | URL feed RSS (mis. instance RSSHub) | **tidak perlu** |
| 👽 **Reddit** | feed `.rss` resmi `reddit.com/r/<sub>/new/.rss` | **tidak perlu** |
| 📰 **RSS / Atom** | URL feed situs apa pun (blog, berita, Substack, dsb.) | **tidak perlu** |

Contoh pemasangan:
```bash
/sosial tambah platform:🎬 YouTube target:@NamaChannel channel:#info
/sosial tambah platform:🟣 Twitch target:ninja channel:#live role:@Warga
/sosial tambah platform:🎵 TikTok target:https://rsshub.app/tiktok/user/namaakun channel:#tiktok
/sosial tambah platform:👽 Reddit target:r/indonesia channel:#reddit
/sosial tambah platform:📰 RSS/Atom target:https://blog.contoh.com/feed.xml channel:#artikel
/sosial daftar          # lihat ID tiap langganan
/sosial tes id:ab12cd34 # kirim contoh notifikasi sekarang
/sosial hapus id:ab12cd34
```

Cara kerja & pengaman:
- **Anti-banjir:** pemeriksaan pertama hanya *menandai* konten lama sebagai sudah dilihat — channel tidak dibanjiri video lama.
- **Twitch:** notifikasi hanya dikirim saat status berubah **offline → live**, bukan setiap pengecekan.
- **Jadwal:** id channel YouTube & feed RSS dicek ≤5 menit, Twitch tiap 2 menit. Semua dijalankan di dalam watcher yang sudah ada, jadi **tidak menambah proses** di Wispbyte.
- **Reddit tanpa API key:** cukup tulis nama subreddit (`r/indonesia`, `indonesia`, atau link
  subreddit) — bot menyusun sendiri URL `…/r/<sub>/new/.rss` dan membaca format Atom-nya.
- **RSS/Atom generik:** tempel URL feed apa pun; kalau situs tidak punya feed, fitur ini tidak
  bisa memantaunya (tidak ada scraping HTML).
- **Batas:** maksimal 12 langganan per server; `seen` disimpan 25 ID terakhir per langganan agar `data/social.json` tetap kecil.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🔔 Notifikasi sosial* — daftar
  langganan (platform, URL feed sebenarnya, channel, jejak item), form tambah dengan pilihan
  platform & role, serta tombol hapus per langganan. Jalur tulis: `POST /api/konten`
  (`sosial-tambah`, `sosial-hapus:<id>`).
- Tombol tes **Notifikasi sosial** hanya memeriksa bentuk URL feed semua langganan —
  **tanpa memanggil jaringan** dan tanpa mengirim pesan.
- **Template kustom:** `{source}` `{title}` `{url}` `{game}` — mis. `pesan:"Video baru dari {source}: {title} {url}"`.

### Cara mendapatkan `TWITCH_CLIENT_ID` & `TWITCH_CLIENT_SECRET` (sekali saja, gratis)

1. Buka **https://dev.twitch.tv/console/apps** → login dengan akun Twitch kamu.
2. Klik **Register Your Application**:
   - **Name:** bebas (mis. `BotKomunitas`)
   - **OAuth Redirect URLs:** `http://localhost`
   - **Category:** `Bot`
   - Klik **Create**.
3. Di halaman aplikasi, salin **Client ID** → klik **New Secret** lalu salin **Client Secret**.
   *(Secret hanya muncul sekali; kalau hilang, buat yang baru.)*
4. Wispbyte → panel server → **Startup / Variables** → tambahkan dua variabel:
   ```
   TWITCH_CLIENT_ID=isi_client_id_kamu
   TWITCH_CLIENT_SECRET=isi_client_secret_kamu
   ```
5. **Restart** server, lalu jalankan **`/sosial status`** sampai baris Twitch bertanda ✅.

> 🔒 Jangan pernah menempelkan Client Secret ke chat Discord, README, atau commit git. Simpan hanya di tab
> Variables Wispbyte. Kalau secret sempat bocor, klik **New Secret** untuk membatalkan yang lama.

> **Catatan jujur soal TikTok:** TikTok **tidak menyediakan API feed gratis resmi** untuk bot. Karena itu opsi TikTok memakai jalur **feed RSS** (RSSHub publik/self-host). Kalau feed-nya diblokir atau mati, bot hanya mencatat di log dan tidak error. YouTube & Twitch tidak punya masalah ini.

### 10. 📝 Perangkum Obrolan Channel Tertinggal (`/ringkas`)
- Ketinggalan **99+ notifikasi chat** di grup? Siapa pun member bisa mengetik **`/ringkas`** (pilih `25`, `50`, `100`, atau `150` pesan terakhir).
- Bot akan merangkum poin-poin inti obrolan warga beserta info/momen penting ke dalam Embed rapi berbahasa Indonesia (secara default hanya terlihat oleh Anda sendiri agar tidak mengganggu chat).

### 11. 📲 Menu Tekan-Tahan Pesan / Klik Kanan (*Discord Context Menu Apps*) — Tanpa Ketik Command!
Member tidak perlu mengetik command apa pun untuk menerjemahkan atau memahami pesan asing/rumit:
- **Cara pakai di HP (Android/iOS):** Tekan & tahan (*long-press*) pesan siapa saja di channel mana pun ➔ pilih **Apps** ➔ klik:
  - **`🌐 Terjemahkan ke Indonesia`** — Menerjemahkan pesan bahasa Inggris, Jepang, Korea, Arab, Mandarin, bahasa gaul/slang, maupun teks di dalam gambar/Voice Note ke Bahasa Indonesia yang luwes.
  - **`💡 Jelaskan Pesan Ini`** — Menjelaskan maksud istilah teknis, potongan kode/error, pengumuman panjang, atau meme secara ringkas & mudah dimengerti.
  - **`🔍 Cek Fakta / Hoaks`** — Memeriksa kebenaran klaim berita heboh, rumor, atau tangkapan layar secara objektif menggunakan pencarian berita & web live gratis lengkap dengan tautan sumber buktinya!
- **Cara pakai di PC/Laptop:** Klik kanan pesan ➔ sorot **Apps** ➔ pilih menu di atas. Hasilnya tampil privat (*ephemeral*) hanya untuk Anda!

### 12. 🎬 Perangkum Video YouTube & Pembaca Link Web Per-Channel (`/ringkas link` & `/agent youtube`)
- **Diatur Per-Channel (Bisa Aktif di Beberapa Channel Sekaligus!):** Persis seperti `/agent chat` dan `/agent gallery`, Admin bebas memilih channel mana saja yang mengaktifkan fitur rangkum YouTube & link web lewat **`/agent youtube channel:#nama-channel aktif:True`** (bahkan tetap bekerja walaupun channel tersebut tidak menyalakan Auto-Chat!).
- **Command `/ringkas link` & Ruang Privat `ai-...`:** Tempel link YouTube (`youtube.com/watch`, `youtu.be`, `shorts`, `live`) atau artikel web untuk mendapatkan rangkuman poin penting dalam hitungan detik (100% gratis memakai fitur *YouTube Video Understanding* Gemini)!
- **Panggil Nama Bot + Kirim / Reply Link di Channel Aktif:** Di channel yang sudah diaktifkan `/agent youtube`, member cukup memanggil **nama panggilan bot** / `@mention` / *reply* ke bot sambil menyertakan link YouTube/web — **atau me-*reply* pesan teman yang berisi link YouTube sambil memanggil bot** (contoh: *"Whas rangkumin video YouTube ini dong"*).
- **2 Mode Fleksibel Per-Channel (`auto_di_channel`):**
  - `auto_di_channel: False` (**Default & Rekomendasi**): Diam saat warga sekadar share link biasa di channel tersebut, namun langsung merangkum saat nama bot dipanggil atau memakai `/ringkas link`.
  - `auto_di_channel: True` (**Mode Channel Khusus Video**): Setiap link YouTube/Web yang dikirim warga di channel tersebut otomatis dirangkum tanpa perlu memanggil nama bot!

### 13. 🌍 Live Web & News Search Gratis Per-Channel (`/cari` & `/agent cari`)
- **100% Gratis di *Free Tier* (Bebas Error `You exceeded your current quota`):** Menggunakan mesin pencari web & berita *real-time* mandiri (**Google News RSS Indonesia + DuckDuckGo Web** + pembaca isi artikel berita) yang dirangkum oleh model Gemini gratis lengkap dengan daftar tautan **🌐 Sumber Web**! *(Juga mendukung opsi Google Search Grounding Paid Tier via `GEMINI_PAID_SEARCH_ENABLED=true`).*
- **Diatur Per-Channel (Bisa Aktif di Beberapa Channel Sekaligus!):** Admin bebas mengaktifkan fitur pencarian di satu atau beberapa channel pilihan lewat **`/agent cari channel:#nama-channel aktif:True`** (bekerja baik di channel Auto-Chat maupun channel mandiri khusus berita!).
- **Bisa Lewat `/cari` ATAU Panggil Nama Bot Langsung di Channel Aktif:**
  - Ketik **`/cari pertanyaan:berita timnas indonesia hari ini`** di channel yang aktif (atau ruang privat `ai-...`), **ATAU**
  - Langsung panggil nama panggilan bot di channel yang mengaktifkan `auto_di_chat:True` (contoh: *"Whas coba cari berita hari ini tentang harga emas Antam"*) — nama panggilan bot otomatis dibersihkan dari kata kunci pencarian sehingga hasil berita akurat!

### 14. 🎮 6 Mode Mini-Game Tongkrongan AI (`/game`) + Papan Skor Server (*Leaderboard*)
Bikin channel tongkrongan makin ramai dengan **6 permainan interaktif** (anti-bosan & hemat kuota *Free Tier*!):
- **`🎭 Tebak dari Emoji` (+20 Poin):** Tebak judul film, game, anime, atau makanan populer dari 4–5 petunjuk emoji di chat!
- **`🖼️ Tebak Gambar AI` (+25 Poin):** AI melukis gambar misteri secara langsung lewat Flux *Free Tier* dan warga berlomba menebak objek/karakter di dalamnya!
- **`⛓️ Sambung Kata Indonesia` (+5 Poin/Kata):** Permainan berantai menyambung huruf terakhir kata sebelumnya (hingga 15 rantai kata, **0 panggilan API Gemini per giliran** sehingga super ringan & bebas kuota!).
- **`🧠 Kuis Trivia Cepat A/B/C/D` (+15 Poin):** Adu cepat klik tombol pilihan ganda A/B/C/D langsung di layar (1x kesempatan per orang per ronde!).
- **`🕵️ Tebak Kata Misteri` (+20 Poin):** Permainan *"Siapakah / Apakah Aku?"* dengan 3 petunjuk bertingkat + tombol **💡 Buka Petunjuk**.
- **`🔀 Susun Huruf Acak` (+15 Poin):** Adu cepat menyusun kata Bahasa Indonesia yang hurufnya diacak.
- Seluruh skor kemenangan tersimpan permanen per server di `data/game_scores.json` dan dapat dilihat kapan saja lewat **`/game papan_skor`**!

### 15. 📌 Memori Info & FAQ Resmi Server (`/agent info`), ☀️ Koran Pagi (`/agent digest`), & 🎛️ Panel Admin (`/agent panel`)
- **Memori Info & FAQ Server (`/agent info`):** Admin dapat menyimpan hingga **25 entri pengetahuan resmi server** (seperti *Rules*, IP Server Minecraft/FiveM, jadwal mabar, cara *open ticket*, atau link sosial media). AI otomatis menghafal dan menjawab akurat berdasarkan data ini baik di channel publik, Forum, maupun ruang konsultasi privat!
- **Koran & Sapaan Pagi Otomatis (`/agent digest`):** Setiap pagi sesuai jam pilihan (default **`07:00`** waktu lokal), bot otomatis merangkum berita terhangat hari ini + fakta unik pembuka hari ke channel pilihan (dilengkapi proteksi anti-dobel kirim di tanggal yang sama).
- **Panel Kontrol Admin Interaktif (`/agent panel`):** Atur semua fitur channel (Auto-Chat, Galeri, YouTube, Cari, **Welcome, Goodbye, Digest, Fakta Harian**), ubah Persona, hingga tambah FAQ Server langsung lewat menu *dropdown* & *popup form (Modal)* tanpa perlu menghafal banyak parameter command!

---

## C. Fitur Keamanan, Ketahanan & Performa

### 1. 🛡️ Moderasi Bercatatan (`/mod`) — Warn, Timeout, Kick, Ban, Purge

| Command | Fungsi |
| :--- | :--- |
| `/mod warn member @x alasan:...` | Peringatan resmi + tercatat. Setelah ambang tercapai → **timeout otomatis**. |
| `/mod timeout member @x durasi:1h30m alasan:...` | Bisukan sementara (timeout native Discord, maks 28 hari). |
| `/mod kick` / `/mod ban` / `/mod unban` | Kick, ban (opsional hapus pesan 0–7 hari), cabut ban via ID. |
| `/mod tempban member:@x durasi:2d alasan:...` | **Ban sementara** — dicabut **otomatis** saat durasi habis (maks 365 hari), tanpa perlu staf mengingat. |
| `/mod softban member:@x hapus_pesan_hari:7` | **Softban** — ban sebentar untuk menghapus pesan, ban **langsung dicabut** sehingga member boleh kembali. |
| `/mod note member:@x teks:...` | **Catatan internal staff** (tidak menghukum, tidak memberi tahu member). |
| `/mod purge jumlah:50 member:@x tipe:link` | Hapus massal dengan filter **semua / bot / link / gambar**. |
| `/mod catatan member:@x` | Riwayat kasus + jumlah peringatan aktif. |
| `/mod hapus id:12` | Hapus kasus salah catat (khusus Admin). |
| `/mod atur log_channel:#mod-log ambang_warn:3 durasi_auto:1h jendela_hari:30 dm:True` | Semua pengaturan moderasi. |
| `/mod slowmode detik:30 channel:#umum` | **Mode lambat** per channel (0 = matikan, maks 6 jam) — anti-banjir tanpa hapus pesan. |
| `/mod role member:@x role:@Gamer aksi:beri` | Beri/cabut satu role (hierarki & role terkelola dijaga). |
| `/mod role-massal role:@Event aksi:beri filter_role:@Aktif batas:50` | **Beri/cabut role ke banyak member** sekaligus, dengan dialog konfirmasi & ringkasan hasil. |
| `/mod nickname member:@x nama:Sobat` | Ubah/reset nickname member (kosongkan `nama` untuk reset). |
| `/mod statistik hari:30` | **Statistik staf**: siapa menindak berapa banyak, rincian per jenis aksi, & daftar temp-ban yang masih berjalan. |

Pengaman bawaan:
- **Hierarki dihormati** — bot menolak menindak pemilik server, Administrator, atau role yang lebih tinggi darinya (pesan errornya menjelaskan cara memperbaikinya).
- **Semua aksi terlihat** — DM ke member (bisa dimatikan) + laporan embed ke channel log.
- **Anti salah hapus** — `/mod purge` hanya menghapus pesan, tidak pernah menyentuh pinned secara sengaja; jumlah dibatasi 100 per perintah.
- **Tangga hukuman lengkap** — `warn` → `timeout` → `kick` → `softban` → `tempban` → `ban`, semuanya membuat **satu kasus bernomor** yang dipakai bersama `/mod catatan`, `/mod statistik`, & dashboard.
- **Temp-ban tidak menggantung** — watcher utama (tiap 15 detik) mencabut ban yang jatuh tempo, mencatat kasus `unban` otomatis, dan mengirim laporan ke channel log. Bila server/bot sedang mati saat waktunya habis, temp-ban dicabut pada putaran pertama setelah bot hidup lagi.
- **Catatan ≠ hukuman** — `/mod note` hanya menulis riwayat untuk staff; member tidak diberi DM dan tidak dikenai aksi apa pun.
- **Default NONAKTIF-kan diri sendiri:** bot tidak menindak siapa pun sampai staff menjalankan `/mod`. Anti-spam yang ada tetap berjalan dalam mode *lapor saja*.

### 1b. 🚨 Jalur member: `/lapor` & `/banding`

Moderasi yang hanya satu arah membuat member merasa tidak didengar. Dua command ini
membuka jalur resmi **member → staf**, tanpa menambah risiko:

| Command | Fungsi |
| :--- | :--- |
| `/lapor member:@x alasan:... bukti:...` | Member melaporkan pesan/member. Laporan **masuk antrean staf** (bukan langsung hukuman), dikirim ke channel laporan, dan pelapor dapat DM konfirmasi. |
| `/banding alasan:... [kasus:12]` | Member mengajukan peninjauan hukuman. Bisa dijalankan dari **DM** (untuk yang sudah diban) — bot mencari kasus terakhir atas nama member itu. |
| `/mod antrean [status] [jenis]` | *(Staff)* Lihat antrean laporan & banding. |
| `/mod tindak kode:12 status:diterima catatan:"..." cabut:True` | *(Staff)* Ubah status; `cabut:True` pada banding **langsung mencabut** timeout/ban/temp-ban terkait dan mencatat kasus baru. |

Pengaman:
- **Tidak ada hukuman otomatis** dari laporan — keputusan tetap di staf.
- **Anti-spam laporan**: cooldown per pelapor (bawaan **300 detik**), alasan minimal **10 huruf**, dan laporan beruntun tidak menumpuk antrean.
- **Banding terhubung kasus**: nomor kasus ikut tersimpan, dan hanya kasus atas nama pelapor yang bisa dibanding.
- Semua antrean tersimpan di `data/reports.json` (maks 300 entri/server) dan bisa dikelola dari halaman **🚨 Moderasi** di dashboard.

### 1c. 🔎 Snipe & EditSnipe (`/snipe`)

Pesan yang dihapus/diubah **sebelum staf sempat melihat** tidak hilang begitu saja.

| Command | Fungsi |
| :--- | :--- |
| `/snipe hapus [jumlah]` | Tampilkan 1–5 pesan terakhir yang dihapus **di channel itu**. |
| `/snipe edit [jumlah]` | Tampilkan isi **sebelum → sesudah** pesan yang baru diubah. |
| `/snipe atur aktif:True hapus:True edit:True` | *(Admin)* Sakelar fitur, per jenis. |

Detail penting:
- **Khusus staf:** grup `/snipe` memakai izin bawaan *Manage Messages*, jadi member biasa
  tidak melihatnya sama sekali.
- **Hanya di memori** — maksimal 5 pesan per channel dan **hilang saat bot restart**.
  Tidak ada berkas baru, tidak ada riwayat permanen, tidak ada risiko data sensitif tersimpan.
- Bot, pesan kosong, dan pesan tanpa lampiran tidak dicatat; pesan yang ikut terhapus oleh
  `purge` juga dicatat (maks 5 terakhir).
- **Panel dashboard:** halaman **🚨 Moderasi** → *🔎 Snipe & EditSnipe* — sakelar aktif,
  catat-hapus, catat-edit, plus jumlah entri yang sedang tersimpan di memori.
  Jalur tulis: `POST /api/moderasi` (`snipe-setelan`).
- Tombol tes **Snipe & EditSnipe** mencatat pesan contoh di memori, membacanya kembali, lalu
  membersihkannya — tidak menyentuh pesan asli.

### 2. 🚨 Raid Guard — Mode Darurat Otomatis (`/raid`)

Anti-raid di `/keamanan` hanya **melapor**. **Raid Guard** bertindak: kalau server diserbu
akun palsu (lonjakan join), bot menyalakan mode darurat sendiri selama beberapa menit.

| Aksi | Efek saat mode raid aktif |
| :--- | :--- |
| `lapor` | Laporan ke channel log saja — tanpa mengubah server. |
| `verifikasi` *(bawaan)* | **Auto Role ditahan**, member baru dapat pengingat verifikasi (DM + sebutan di channel verifikasi). |
| `verifikasi+lockdown` | Semua di atas **+ lockdown** semua text channel sampai mode berakhir. |

```text
/raid atur aktif:True ambang:8 jendela_detik:60 aksi:verifikasi durasi_menit:15 log_channel:#mod-log
/raid status
/raid mulai alasan:"Diserbu akun baru" durasi_menit:30
/raid akhiri
```

Pengaman: default **nonaktif**, hanya **Admin/Manage Server** yang bisa mengubah, laporan
maksimal **sekali per 5 menit** (anti-spam), semua tindakan **reversible** (lockdown dibuka &
Auto Role normal saat mode berakhir), dan setiap kejadian tercatat di Audit Log.

### 3. 🧰 Perkakas Server: AFK, Thread Otomatis, Lockdown & Backup Struktur

| Command | Siapa | Fungsi |
| :--- | :--- | :--- |
| `/afk atur alasan:sekolah` | Semua | Tandai AFK. Kalau ada yang me-mention kamu, bot menjawab dengan alasan & durasinya. Status hilang otomatis begitu kamu bicara lagi. |
| `/afk daftar` / `/afk hapus` | Semua | Lihat member AFK / hapus statusmu lebih awal. |
| `/thread-otomatis aktifkan arsip_menit:1440` | Admin | Setiap pesan baru di channel itu dibuatkan thread (judul dari awal pesan). |
| `/thread-otomatis status` / `matikan` | Admin | Kelola daftar channel auto-thread. |
| `/lockdown aktif:True alasan:raid` | Admin | **Darurat**: cabut izin kirim `@everyone` di semua text channel. |
| `/lockdown aktif:False` | Admin | Buka kembali **hanya** channel yang dikunci bot (tidak mengubah channel yang sudah terkunci sebelumnya). |
| `/lockdown status` | Admin | Cek durasi, channel terkunci, & alasannya. |
| `/backup struktur` | Admin | Unduh JSON berisi role, kategori, channel, & permission overwrite. |

Catatan penting:
- Status lockdown disimpan atomik di `data/lockdown.json` beserta nilai izin `@everyone` sebelum dikunci. Setelah restart, `/lockdown status` menandai status yang dipulihkan; `/lockdown aktif aktif:False` mengembalikan izin awal.
- Channel yang sudah terkunci sebelum lockdown tidak disentuh. Jika izin channel diubah manual saat lockdown berlangsung, pemulihan mempertahankan perubahan manual itu; kegagalan izin tetap tercatat agar Admin bisa mencoba lagi.
- Lockdown yang dibuat oleh versi bot sebelum catatan pemulihan ini tersedia tidak punya snapshot izin dan harus diperiksa manual.
- **Backup bersifat baca-saja**: bot **tidak** akan membuat/menghapus channel dari berkas itu, jadi tidak ada risiko server rusak karena salah klik.
- Auto-thread otomatis berhenti membuat thread bila bot kehilangan izin *Create Public Threads* (hanya dicatat di log).

### 4. ♻️ Pemulihan Struktur Server (`/backup pratinjau`, `/backup pulihkan`)

Kalau server kena *nuke* / salah hapus channel, backup JSON yang pernah kamu unduh bisa
dipakai untuk **membangun ulang** role, kategori, dan channel — lengkap dengan izin per role.

| Command | Fungsi |
| :--- | :--- |
| `/backup struktur` | Unduh snapshot role/kategori/channel/izin (tanpa isi pesan). |
| `/backup pratinjau berkas:<file.json>` | **Dry-run**: lihat apa yang akan dibuat, apa yang sudah ada, apa yang dilewati. **Tidak mengubah server.** |
| `/backup pulihkan berkas:<file.json> buat_role:True buat_kategori:True buat_channel:True` | Buat ulang struktur setelah konfirmasi. |

Pengaman:
- **Hanya menambah.** Bot tidak pernah menghapus, memindahkan, atau menimpa channel/role yang sudah ada.
- Item dicocokkan dari **nama & tipe**; yang sudah ada otomatis dilewati (tidak dobel).
- Kategori dan channel baru diproses sesuai urutan posisi di snapshot, tanpa menggeser item yang sudah ada.
- **Maksimal 30 item per pemulihan** (agar aman dari rate limit Discord) — jalankan ulang untuk sisanya.
- **Overwrite per-member dilewati** (ID member berbeda di server lain); izin **per-role** tetap diterapkan berdasarkan nama role.
- Channel **forum** dipulihkan beserta setelan dasar dan tag; channel **media** didukung dengan Discord.py ≥2.6. Jika versi/API tidak mendukung tipe media, pratinjau menandainya sebagai dilewati.
- Backup forum/media berisi konfigurasi channel, bukan post/thread; emoji tag custom tidak dibawa lintas server (tag dan emoji Unicode tetap dicatat).
- Posisi absolut mungkin berbeda jika server tujuan sudah berisi item; bot tidak memindahkan channel lama demi menjaga mode hanya-menambah.
- Setiap pemulihan tercatat di **Audit Log** (`/log`) dan bisa dibatalkan manual bila hasilnya tidak sesuai.
- Berkas divalidasi: harus JSON hasil `/backup struktur`, versi ≤ 1, maksimal 4 MB.

### 5. Ketahanan & Performa Bawaan
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

## D. Fitur Server Otomatis (`/serverstats`, `/autorole`, `/fakta`, `/keamanan`)

### 1. 📊 Statistik Server seperti Bot Serverstats (`/serverstats`)
- **`/serverstats lihat`** — kartu statistik lengkap: total anggota, manusia vs bot, perkiraan member online, boost & level, jumlah channel teks/suara/forum, role, emoji, stiker, tanggal server dibuat, pemilik, dan level verifikasi.
- **`/serverstats otomatis aktif:True`** *(Admin)* — membuat kategori **`📊 Statistik Server`** berisi Voice Channel penghitung yang **ter-update otomatis setiap ±10 menit**:
  `👥 Total Member: 1.204` · `🙋 Manusia: 1.150` · `🤖 Bot: 54` · `🟢 Online: 312` · `💎 Boost: 7` ·
  `🎫 Tiket Terbuka: 3` · `🔔 Langganan Sosial: 5`
- Dua penghitung terakhir membaca **state bot** (bukan API tambahan): jumlah tiket yang belum
  ditutup (`/tiket` + `/menu tiket`) dan jumlah langganan notifikasi sosial YouTube/Twitch/TikTok/
  Reddit/RSS yang aktif — jadi operator bisa melihat beban komunitas & isi langganan sekilas.
  Kartu **`/serverstats lihat`** juga memuat baris **📈 Aktivitas Fitur** (tiket terbuka + langganan sosial).
- Emoji tiap channel bisa diganti lewat **`/serverstats ikon`** atau panel **📊 Channel statistik**
  di halaman *🧩 Konten & interaksi* (form ikon per channel + tombol **🔄 Segarkan sekarang**,
  jalur tulis `POST /api/konten` → `stats-emoji:<kunci>`, `stats-segarkan`). Isi `-` untuk
  menghapus ikon. Tombol tes **📊 Channel statistik** menghitung ulang 7 angka itu tanpa
  membuat/mengganti nama channel.
- Warga **tidak bisa masuk** ke channel penghitung (hanya bisa melihat angka), dan update dibatasi aman dari *rate limit* Discord (maks. 2 rename / 10 menit per channel).

### 2. 🎭 Auto Role Member Baru (`/autorole`) *(Admin)*
- **`/autorole atur role:@Member role2:@Notif aktif:True`** — berikan **hingga 3 role** otomatis setiap ada member baru bergabung, tanpa perlu verifikasi manual.
- **`/autorole status`** — cek daftar role aktif & peringatan otomatis jika posisi role bot terlalu rendah.
- **`/autorole isi`** — berikan Auto Role ke member lama yang belum memilikinya (maks. 150 member per eksekusi, aman dari rate limit).
- Role bot/integrasi, `@everyone`, dan role di atas posisi bot otomatis dilewati agar tidak error.

### 3. 🌍 Fakta Unik Dunia Terjadwal 4x Sehari (`/fakta`)
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

### 4. 🛡️ Anti-Phishing Guard Tanpa API Berbayar (`/keamanan`)
- **`/keamanan phising aktif:True`** *(Admin)* — bot memindai setiap link di pesan warga dan otomatis:
  1. **Menghapus** pesan yang berisi link phishing tingkat **berbahaya**.
  2. **Memperingatkan** pengirim & warga lain di channel.
  3. **Mencatat** detailnya ke channel log moderator (opsional).
- **Deteksi lokal gratis** (tanpa API berbayar / tanpa kartu kredit): domain tiruan brand populer (Discord, Steam, Roblox, Netflix, Binance, Shopee, DANA, BCA, dll.), karakter **punycode `xn--`**, link berbasis **IP langsung**, **TLD berisiko** (`.tk`, `.ml`, `.ga`, `.zip`, dll.), **pemendek URL** (`bit.ly` dsb.), trik `@` pada URL, dan **daftar hitam** domain phishing yang sudah dikenal.
- **`/keamanan cek link:https://...`** bisa dipakai **semua member** untuk memeriksa keamanan link sebelum membuka.
- Bisa dibatasi hanya ke channel tertentu, dan mode **ketat** (`ketat:True`) juga menindak link yang baru *mencurigakan*.

### 5. 🪤 Honeypot — Channel Jebakan (`/keamanan honeypot`)

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

## E. Fitur Komunitas Ringan (`/panel-role`, `/poll`, `/saran`, `/embed`, `/tempvoice`)

> 💡 Semua fitur di bagian ini **tidak memanggil Gemini sama sekali** (0 kuota, 0 biaya) dan **default NONAKTIF**.
> Server yang belum memakai fitur ini tidak mendapat beban tambahan apa pun (tanpa event listener berat, tanpa RAM ekstra).

### 1. 🎭 Reaction Role — Member Ambil Role Sendiri (`/panel-role`)
- **`/panel-role pasang channel:#ambil-role judul:Ambil Role role1:@Gamer emoji1:🎮 role2:@Artist emoji2:🎨`** — bot mengirim panel embed lalu memasang reaksi emoji secara otomatis (maks **3 role sekali pasang**).
- Warga cukup **klik emoji** untuk mendapatkan role, **klik lagi** untuk melepasnya. Tidak ada kuota, tidak ada tombol kedaluwarsa.
- **`/panel-role tambah pesan:<ID/link> emoji:🎵 role:@Musik`** — tambah role ke panel yang sudah ada.
- **`/panel-role hapus`**, **`/panel-role daftar`** — kelola & lihat semua panel.
- Posisi role diperiksa otomatis: role di atas role bot dilewati dengan peringatan jelas.

### 2. 📊 Polling Native Discord (`/poll`)
- **`/poll pertanyaan:"Mabar malam ini jam berapa?" opsi:"Jam 8, Jam 9, Jam 10" durasi_jam:24`**
- Memakai **Poll bawaan Discord**: hitung suara real-time, tampilan rapi, tidak bisa di-*double vote* — tanpa beban server sama sekali.
- Mendukung **multi-pilihan** (`multi:True`), **anonim/terbuka** (`anonim:True`), dan durasi **1–768 jam** (maks 32 hari).
- Maksimal **10 pilihan** (batas Discord); lebih dari itu dipotong otomatis dengan pemberitahuan.

### 3. ⏰ Pengingat Pribadi Tahan Restart (`/ingatkan`)
- **`/ingatkan pasang waktu:"2j" pesan:"Rapat pengurus"`** — bot menagih kamu saat waktunya tiba (di channel atau DM bila channel tak bisa diakses).
- Format waktu fleksibel: `10m`, `2j`, `1j30m`, `2 hari`, `45` (menit), bahkan `1 jam dan 15 menit`. Maksimal **365 hari**.
- **Tahan restart:** pengingat disimpan di `data/community_tools.json`, jadi tetap dikirim walau bot baru di-*restart*.
- **`/ingatkan daftar`** & **`/ingatkan batal nomor:3`** — kelola pengingat aktif (maks 15 per member).

### 4. ⭐ Starboard — Sorotan Pesan Populer (`/starboard`)
- **`/starboard atur channel:#starboard batas:3 emoji:⭐`** — pesan warga yang mendapat **3 reaksi bintang** otomatis disalin ke channel sorotan (embed cantik + tautan sumber).
- Bila reaksi turun di bawah batas, sorotannya **otomatis dihapus** agar starboard tetap rapi.
- Pesan bot dilewati, emoji bisa diganti bebas (`🔥`, `❤️`, dll.), dan **`/starboard status`** menampilkan semua papan + jumlah sorotan.

**Papan berlapis / varian (v1.40.0-beta):**

| Aspek | Detail |
| :--- | :--- |
| **Papan utama + varian** | Papan ⭐ tetap seperti biasa. Tambahkan **skullboard 💀**, **clownboard 🤡**, dll. dengan `/starboard varian tambah:Skull emoji:💀 batas:5 channel:#skull warna:#FF8A00`. Maksimal `STARBOARD_MAX_BOARD` = **4 papan** per server (termasuk papan utama). |
| **Mandiri** | Tiap papan punya emoji, ambang, channel, dan warna embed sendiri. Satu pesan bisa masuk ke **beberapa papan sekaligus**; entri sorotan disimpan per papan sehingga menghapus sorotan di satu papan tidak mengganggu papan lain. |
| **Channel kosong** | Bila channel papan tidak diisi, papan itu ikut channel papan utama. |
| **Angka ikut naik** | Saat reaksi bertambah, angka di pesan sorotan **diperbarui** (bukan mengirim ulang); turun di bawah ambang → sorotan papan itu dihapus. |
| **Anti-loop** | Pesan yang berada di channel papan mana pun tidak akan disorot lagi. |
| **Dashboard** | Halaman **🧩 Konten & interaksi** → panel *Papan sorotan (varian)*: daftar papan + tombol hapus, form tambah (nama, emoji, ambang, channel, warna), dan setelan **warna embed** papan utama. |

### 5. ✅ Gerbang Verifikasi Anti-Bot (`/verifikasi`)
- **`/verifikasi pasang channel:#verifikasi role:@Member`** — panel dengan tombol **✅ Verifikasi Saya**.
- Member baru klik sekali → langsung dapat role akses, tanpa perlu Admin menunggu. Cocok dipadukan dengan `/autorole`.
- **`/verifikasi status`** & **`/verifikasi matikan`** — pantau / matikan kapan saja.
- Tombol bersifat **persisten** (`custom_id`), jadi tetap berfungsi setelah bot restart.

**CAPTCHA (v1.40.0-beta, tanpa dependency baru):**

```bash
/verifikasi pasang channel:#verifikasi role:@Member captcha:True
```

- Member menekan **✅ Verifikasi Saya** → muncul **modal** berisi kode **5 huruf** (alfabet
  tanpa `0/O/1/I/L` supaya tidak salah baca). Kode hanya terlihat oleh member itu.
- Salah ketik: **3 percobaan**, kode **kedaluwarsa 5 menit**; habis/kedaluwarsa → tekan tombol
  lagi untuk kode baru. Kode disimpan **di memori** saja dan dibersihkan otomatis tiap jam.
- Bedanya dengan tombol biasa: bot self-bot/otomasi tidak bisa menyelesaikan modal, jadi
  gerbang ini menahan akun yang "rajin" klik.
- **Dashboard:** halaman **🛡️ Keamanan** → sakelar *CAPTCHA verifikasi* (butuh channel
  verifikasi terpasang dulu) + tombol tes **Gerbang verifikasi & CAPTCHA** yang hanya
  memeriksa setelan — **tidak** memberikan role ke siapa pun.

### 6. 📌 Sticky Message — Petunjuk Selalu di Bawah (`/sticky`)
- **`/sticky pasang isi:"Baca #rules dulu sebelum chat!" channel:#umum judul:"📌 Aturan"`**
- Setiap ada obrolan baru, bot menurunkan ulang pesan petunjuk ke bawah channel (pesan lama dihapus).
- **Anti-spam:** jeda minimum **5 detik** per channel (`STICKY_MIN_INTERVAL_SEC`), jadi channel ramai tidak dibanjiri bot.
- **`/sticky lepas`** & **`/sticky status`** — cabut / lihat daftar channel sticky.

### 7. 👤 Kartu Profil & Server (`/info`)
- **`/info user member:@Warga`** — umur akun, tanggal bergabung, jumlah role, plus **peringatan keamanan** otomatis jika akun masih **< 7 hari** (indikasi akun raid).
- **`/info server`** — total member (manusia vs bot), online, boost, jumlah channel, status verifikasi & auto role, pemilik, dan tanggal server dibuat.

### 8. 🗂️ Perawatan: Backup Otomatis & Log Error (`/perawatan`)
- **`/perawatan atur backup_channel:#bot-backup log_channel:#bot-log`** — backup konfigurasi otomatis tiap **7 hari** (`BACKUP_INTERVAL_DAYS`) & laporan error masuk ke channel.
- **`/perawatan backup`** — kirim berkas ZIP berisi seluruh `data/*.json` saat itu juga (penyelamat saat Wispbyte rebuild bersih).
- **`/perawatan status`** — channel backup/log, waktu backup terakhir, ukuran arsip, & RAM bot.
- Error Slash Command maupun error event otomatis diringkas ke channel log (tanpa membocorkan API key — sudah disanitasi) dan jejaknya tampil di **`/status`**.

### 9. 💡 Kotak Saran (`/saran`) & 📝 Pembuat Embed (`/embed`)

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
| `/embed variabel` | Daftar variabel `{member.mention}`, `{server.members}`, `{now_relative}`, … |
| `/embed sebagai nama:"📢 Pengumuman" isi:"..."` | Kirim dengan **nama & avatar sendiri** lewat webhook |
| `/embed webhook` | Cek / hapus webhook identitas yang dipakai bot |

Warna menerima `#9B59B6`, `ungu`, `biru`, `merah`, `hijau`, `emas`, `abu`. Hanya **staff** (Manage Messages/Server) yang bisa mengirim.

**Identitas kustom (webhook).** `/embed sebagai` mengirim pesan sebagai *siapa pun* pilihanmu
("📢 Pengumuman Server", "🎉 Tim Event") lengkap dengan avatar — ide dari Discohook. Bot membuat
satu webhook per channel lalu memakainya ulang (`data/webhooks.json`), jadi tidak membuat webhook
baru setiap kali. Butuh izin **Manage Webhooks**; mention massal dinonaktifkan agar tidak bisa
dipakai men-*ping* `@everyone` diam-diam. Tujuan bisa channel teks **atau thread**.

**Tautan embed (`/embed tautan`).** Ingin tautan yang tampil sebagai **embed cantik** di Discord
(judul, deskripsi, gambar) tetapi saat diklik membuka situsmu — persis *Link Embeds*-nya Discohook?
Bot membuat tautan ke halaman `/l/<kode>` di situs dokumentasi (Vercel) ini:

```text
/embed tautan url:https://situs.kamu/panduan judul:"Panduan Server" isi:"Semua aturan & tips" gambar:https://…/banner.png
→ https://ai-discord-chat-site.vercel.app/l/eyJ0IjoiUGFuZHVhbiBTZXJ2ZXIiLCJkIjoi…
```

- Halaman itu memuat tag `og:` (judul, deskripsi, gambar) sehingga Discord menampilkan embed, lalu
  **mengalihkan pengunjung** ke `url` tujuan lewat `<meta http-equiv="refresh">`.
- **Tanpa database**: seluruh isi embed dipaketkan ke dalam kode pada URL, jadi tautan lama tetap
  hidup walau bot mati dan tidak ada data yang tersimpan di server bot.
- Batasan: URL maksimal ±1.300 karakter (kode ≤1.200), jadi ringkas judul/isi — gambar memakai
  tautan, bukan unggahan. Maksimal **50 tautan** tercatat per server.
- `/embed tautan daftar` melihat yang sudah dibuat; `/embed tautan hapus` hanya menghapus catatan
  (halaman tetap bisa dibuka — hapus pesannya bila ingin benar-benar hilang).
- Alamat situs diatur lewat env `SITE_BASE_URL` (bawaan `https://ai-discord-chat-site.vercel.app`).
  Caranya: `site/api/l/[id].js` + rewrite `/l/:id` di `site/vercel.json` — keduanya sudah ada di repo,
  jadi cukup deploy `site/` seperti biasa. Kalau situs belum dideploy, tautan akan 404.

### 10. 🔊 Temp Voice: Voice Room Sementara (`/tempvoice`)

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

### 11. 🏷️ Tag Jawaban Siap Pakai (`/tag`)

Jawaban yang paling sering ditanya staf (`aturan`, `harga`, `cara refund`) disimpan
sekali, lalu dipanggil kapan saja oleh siapa pun. **Tanpa AI sama sekali** — isi tag
tidak pernah dikirim ke Gemini, jadi 0 kuota dan tidak bisa "dikarang" model.

| Command | Fungsi |
| :--- | :--- |
| `/tag lihat nama:aturan` | Tampilkan isi tag (siapa pun boleh). Nama bisa dicari langsung dari dropdown. |
| `/tag daftar` | Daftar semua tag server + jumlah pemakaian. |
| `/tag cari kata:refund` | Cari tag lewat **nama atau isi** — berguna saat staf lupa nama tag-nya. |
| `/tag buat nama:aturan isi:…` | *(Staf)* Buat tag baru. |
| `/tag ubah nama:aturan isi:…` | *(Staf)* Perbarui isi tag. |
| `/tag hapus nama:aturan` | *(Staf)* Hapus tag. |

Detail penting:
- Nama tag **dinormalisasi** otomatis (`Aturan Server!` → `aturan-server`) supaya mudah dipanggil.
- Maksimal **100 tag/server**, isi maks **1.800 huruf** (batas embed), tanpa biaya kuota.
- Penghitung `dipakai` membantu melihat tag mana yang benar-benar berguna (dan mana yang usang).
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🏷️ Tag jawaban siap pakai* — tambah/perbarui, hapus per tag, lihat statistik pemakaian, dan **sakelar aktif/nonaktif** (data tetap tersimpan). Jalur tulis: `POST /api/konten` (`tag-simpan`, `tag-hapus:<nama>`, `tag-aktif:1|0`).
- Data di `data/tags.json`; tombol tes **Tag jawaban server** hanya menyimulasikan pencarian tanpa menaikkan penghitung.

### 12. 🏅 Lencana Bertingkat (`/lencana`)

Pencapaian yang **dihitung dari data yang sudah dicatat bot** (jumlah pesan, menit voice,
level, riwayat menang undian). Tidak ada pelacakan baru, tidak ada tabel tambahan, dan
**0 kuota AI**.

| Lencana | Tangga tingkat |
| :--- | :--- |
| 💬 Rajin Ngobrol | 50 · 250 · 1.000 · 5.000 · 15.000 pesan |
| 🎙️ Penghuni Voice | 60 · 300 · 1.200 · 5.000 menit voice |
| 📈 Pendaki Level | 5 · 10 · 25 · 50 level (prestise menambah 100) |
| 🎉 Hoki Undian | 1 · 3 · 10 kali menang undian |

| Command | Fungsi |
| :--- | :--- |
| `/lencana lihat [member]` | Lencana + bar progres + sisa menuju tingkat berikutnya. |
| `/lencana papan` | Papan lencana server (10 teratas, medali 🥇🥈🥉). |
| `/lencana periksa [member]` | *(Staf)* Segarkan lencana sekarang — berguna setelah impor data level. |
| `/lencana atur channel:… aktif:…` | *(Admin)* Channel pengumuman lencana & sakelar global. |
| `/lencana role kunci:… tingkat:… role:…` | *(Admin)* Role hadiah per tingkat (kosongkan `role` untuk menghapus). |

Detail penting:
- Pemeriksaan otomatis menempel di alur XP pesan & voice, jadi tidak ada pekerjaan latar
  tambahan dan tidak menambah beban CPU server Free Tier.
- Pemberian role hadiah **idempoten**: tingkat yang sudah diumumkan tidak diulang, dan
  pemberian lencana selalu aman walau bot restart (tersimpan di `data/achievements.json`).
- Maksimal **500 member terdata per server** (yang paling lama tidak aktif dikeluarkan lebih dulu).
- **Panel dashboard:** halaman **⚙️ Inti & level** → *🏅 Lencana bertingkat* — setelan channel
  pengumuman, sakelar aktif/nonaktif, pemasangan/penghapusan role hadiah per tingkat, tangga
  tingkat, dan papan lencana. Jalur tulis: `POST /api/lencana`
  (`lencana-setelan`, `lencana-role`, `lencana-hapus:<kunci>:<tingkat>`).
- Tombol tes **Lencana bertingkat** hanya menghitung progres (simulasi) — tidak memberi role
  dan tidak mengirim pengumuman.

### 13. 🔔 Highlight Kata Kunci (`/pantau`)

Member memilih kata kunci sendiri (mis. `open order`, nama barang, nama dirinya), lalu bot
mengirim **DM** berisi tautan pesan, penulis, channel, dan cuplikan singkat setiap kali kata
itu muncul di chat. Khas bot besar, tapi di sini **tanpa AI** dan **tanpa menyimpan isi pesan**.

| Command | Fungsi |
| :--- | :--- |
| `/pantau tambah kata:open order` | Pantau satu kata/frasa (maks **10** per member). |
| `/pantau hapus kata:open order` | Berhenti memantau satu kata. |
| `/pantau daftar` | Lihat kata kunci, channel & kata yang diabaikan, jumlah DM terkirim. |
| `/pantau abaikan channel:#umum` | Channel ini tidak memicu highlight untukmu. |
| `/pantau abaikan kata:spam` | Kata ini tidak memicu highlight untuk siapa pun. |
| `/pantau bersihkan` | Hapus semua setelan highlight milikmu (opt-out total). |
| `/pantau atur aktif:… abaikan_channel:…` | *(Admin)* Sakelar server & channel yang selalu diabaikan. |

Detail penting:
- **Pencocokan batas kata** (`bot` cocok di “bot itu”, tidak di “robot”), tidak peka huruf besar.
- **Anti-banjir:** jeda 5 menit untuk kata yang sama per member + maksimal **5 DM/menit**
  (bisa diturunkan dari dashboard). Satu pesan = maksimal satu DM per member.
- Penulis pesan tidak dikirimi DM untuk pesannya sendiri; DM yang ditutup member dilewati
  tanpa mengganggu chat.
- Tidak ada isi pesan yang ditulis ke disk — `data/highlights.json` hanya berisi kata kunci,
  daftar abaikan, dan penghitung.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🔔 Highlight kata kunci* — sakelar
  aktif, batas DM/menit, daftar channel yang diabaikan, daftar pelanggan + tombol hapus.
  Jalur tulis: `POST /api/konten` (`pantau-setelan`, `pantau-hapus:<user_id>`).
- Tombol tes **Highlight kata kunci** hanya menyimulasikan pencocokan kalimat contoh —
  tidak ada DM yang dikirim.

### 14. 💌 Curhat Anonim (`/curhat`)

Satu channel khusus untuk **curhat tanpa nama** ala bot besar. Pesan diposting bot dengan
nomor urut dan tanpa penulis; bot **tidak menyimpan isi curhat**. 0 kuota AI.

| Command | Fungsi |
| :--- | :--- |
| `/curhat kirim teks:…` | Kirim curhat anonim ke channel yang sudah diatur. |
| `/curhat atur channel:… aktif:… izinkan_link:… jeda_menit:…` | *(Admin)* Pilih channel, sakelar, izin tautan, jeda per orang. |
| `/curhat hapus nomor:…` | *(staf)* Hapus curhat yang melanggar + catatannya. |

Detail penting:
- **Batas:** 10–900 huruf, maksimal **3 curhat/jam** per penanda penulis, jeda bawaan **5 menit**.
- **Tautan** diblokir kecuali Admin mengizinkan (`izinkan_link`).
- Identitas penulis hanya disimpan sebagai **hash 12 huruf** (`sha256`) — cukup untuk
  menegakkan jeda, tapi tidak membocorkan siapa penulisnya.
- `data/confessions.json` hanya berisi setelan, **nomor**, `pesan_id`, `channel_id`, waktu,
  dan hash — **tanpa teks curhat**.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *💌 Curhat anonim* — channel,
  sakelar, izin tautan, jeda, daftar curhat terakhir (nomor + penanda hash) + tombol hapus
  catatan. Jalur tulis: `POST /api/konten` (`curhat-setelan`, `curhat-hapus:<nomor>`).
- Tombol tes **Curhat anonim** menjalankan validasi aturan pada kalimat contoh — tidak ada
  pesan yang diposting dan nomor tidak terpakai.

### 15. 🔗 Voice Linking (`/tempvoice tautkan`)

Ala bot besar: selama member berada di voice channel, bot memberi **role khusus** dan membuka
**channel teks privat** untuk voice itu. Keluar voice → akses dicabut otomatis. **0 kuota AI.**

| Command | Fungsi |
| :--- | :--- |
| `/tempvoice tautkan` | Lihat status voice linking (role, channel privat, jumlah channel). |
| `/tempvoice tautkan aktif:True role:@Warga Voice` | *(Admin)* Nyalakan & pilih role selama di voice. |
| `/tempvoice tautkan channel_privat:True kategori:#Voice` | *(Admin)* Buat channel teks privat per voice, di kategori tertentu. |
| `/tempvoice tautkan hapus_kosong:False` | *(Admin)* Biarkan channel privat tetap ada walau voice kosong. |

Cara kerja:
- Saat member **masuk** voice: role diberikan (hanya bila dia belum memilikinya) dan channel
  `⌨️-<nama voice>` dibuat/disiapkan. `@everyone` **tidak** bisa melihat; hanya member yang
  sedang di voice itu yang mendapat izin lihat + kirim.
- Saat member **keluar**: izinnya dicabut. Bila voice channel jadi kosong dan
  `hapus_kosong` menyala, channel privatnya dihapus. Pindah voice **tidak** mencabut role.
- Role yang **sudah dimiliki member sebelum masuk voice** tidak akan dicabut saat keluar —
  bot hanya mencabut role yang benar-benar ia berikan.
- Batas **40** channel privat per server. Butuh izin **Manage Roles** & **Manage Channels**.
- Satu listener voice dipakai bersama XP voice, audit log, dan Temp Voice (supaya tidak saling
  menimpa) — lihat `cogs/events_cog.py`.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🔗 Voice linking* — sakelar, role,
  channel privat, hapus-saat-kosong, kategori, daftar channel yang dikelola + tombol lepas.
  Jalur tulis: `POST /api/konten` (`voice-setelan`, `voice-lepas:<voice_id>`).
- Tombol tes **Voice linking** hanya memeriksa setelan & keberadaan role — tidak mengubah role
  atau channel siapa pun.

### 16. ℹ️ Channel Info Otomatis (`/kanal-info`)

Channel baca-saja berisi **aturan & info penting** yang diperbarui sendiri. Admin menulis isinya
sekali; bot menerbitkan **satu pesan embed** lalu **mengedit pesan yang sama** setiap kali isi
berubah — channel tidak penuh pesan lama. **0 kuota AI**, menumpang watcher yang sudah ada.

| Command | Fungsi |
| :--- | :--- |
| `/kanal-info atur` | *(Admin)* Pilih channel, sakelar, judul, warna, & interval cek. |
| `/kanal-info isi` | *(Admin)* Tulis/ganti isi aturan & info (20–3500 huruf, boleh multi-baris). |
| `/kanal-info segarkan` | *(Admin)* Terbitkan/perbarui pesan sekarang juga. |
| `/kanal-info status` | Lihat ringkasan setelan + cuplikan isi. |

Cara kerja:
- Pesan diterbitkan saat isi pertama kali disimpan; setelah itu **hanya diedit** (id pesan
  disimpan di `data/info_channel.json`).
- Bila pesan terhapus manual, bot menerbitkannya lagi pada pemeriksaan berikutnya.
- Interval (5–1440 menit) dipakai untuk **memverifikasi** pesan masih ada, bukan untuk
  menulis ulang isi.
- Bot butuh izin **Send Messages**, **Embed Links**, & **Manage Messages** di channel itu.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *ℹ️ Channel info otomatis* —
  channel, sakelar, judul, warna, interval, kotak isi + tombol simpan & segarkan, plus
  pratinjau embed. Jalur tulis: `POST /api/konten` (`info-setelan`, `info-isi`, `info-segarkan`).
- Tombol tes **Channel info otomatis** hanya memeriksa kelengkapan setelan — tidak mengedit
  pesan di channel.

## F. Streaming Musik 24/7 (`/musik` + Lavalink)

> ⚠️ **Kenapa Lavalink?** Wispbyte hanya menjalankan **satu proses Python tanpa FFmpeg/yt-dlp**.
> Supaya musik tetap jalan tanpa membebani bot (RAM tetap ~50–80 MB), audio didelegasikan ke **Lavalink v4**
> — server kecil berbahasa Java khusus musik. Bot hanya mengirim perintah "putar lagu X" ke node tersebut.

### 1. Menyiapkan Node Lavalink (3 pilihan, semuanya gratis)

| Pilihan | Cara | Cocok untuk |
| :--- | :--- | :--- |
| **A. Node publik gratis** | Ambil URI + password dari direktori node publik (mis. `lavalink.darrennathanael.com`). Tempel ke `LAVALINK_URI` & `LAVALINK_PASSWORD`. | Tes cepat / server kecil. **Node dipakai bersama**, bisa lambat atau mati sewaktu-waktu. |
| **B. Host Lavalink sendiri (Docker)** | Jalankan lokal/VPS: `docker run -d -p 2333:2333 -e LAVALINK_SERVER_PASSWORD=rahasia ghcr.io/lavalink-devs/lavalink:4` lalu isi `LAVALINK_URI=ip-vps:2333`. | Paling stabil & privat. Butuh VPS kecil (RAM ±300 MB). |
| **C. Platform gratis (Railway/Fly.io/Koyeb)** | Deploy image `ghcr.io/lavalink-devs/lavalink:4` dengan `application.yml` (password + plugin LavaSrc bila perlu Spotify). | Tanpa VPS, tapi ada batas jam gratis. |

Setelah node siap, isi di **Variables Wispbyte** (atau `.env`):
```text
LAVALINK_URI=lavalink.contoh.com:2333
LAVALINK_PASSWORD=password-node
LAVALINK_NODE_NAME=utama
```
Lalu **restart bot**. Cek dengan `/musik status` atau `/musik node` — baris *Node Lavalink* harus berbunyi
**✅ Tersambung — node `utama` (N player)**. Bila belum diisi, bot **tetap jalan normal** dan `/musik` hanya menampilkan panduan setup.

### 2. Kalau node tidak tersambung (troubleshooting)

Status node **dibaca langsung** dari Pool wavelink, jadi tidak lagi menampilkan "Siap" palsu:

| Tampilan `/musik status` | Artinya | Tindakan |
| :--- | :--- | :--- |
| **✅ Tersambung — node `utama` (N player)** | Node hidup & siap memutar | — |
| **⏳ Node sedang menyambung** | Handshake TCP/TLS sukses, tapi Lavalink belum mengirim sinyal `ready` (node publik kelebihan beban / baru restart) | Tunggu ±1 menit (bot mencoba ulang otomatis tiap 60 detik) atau `/musik node sambung:True` |
| **⚠️ Belum tersambung — tidak ada node Lavalink aktif** | Tidak ada node terdaftar di Pool: **password salah, host/port keliru, atau koneksi keluar diblokir** | Cek `.env`, lalu tes dengan `curl` di Console |
| **⛔ Belum dikonfigurasi** | `LAVALINK_URI`/`LAVALINK_PASSWORD` kosong | Isi di Variables Wispbyte |

**Tes cepat di Console Wispbyte** (ganti password & host sesuai `.env`):
```bash
curl -s -m 15 -H "Authorization: password-node" https://lavalink.jirayu.net:443/v4/info
```
- Keluar JSON `{"version":{"semver":"4.x.x"}}` → node **hidup** & password benar.
- `401`/`403` → **password salah** di `LAVALINK_PASSWORD`.
- `timeout` / `Could not resolve host` → node mati **atau** koneksi keluar hosting diblokir → ganti node.

**Aturan penulisan URI (penyebab tersering):**

| `.env` | Benar? | Catatan |
| :--- | :--- | :--- |
| `LAVALINK_URI=wss://lavalink.jirayu.net:443` | ✅ | Port **443 wajib** awalan `wss://` |
| `LAVALINK_URI=lavalink.jirayu.net:13592` | ✅ | Port non-443 **tanpa** awalan → otomatis jadi `ws://` |
| `LAVALINK_URI=lavalink.jirayu.net:443` | ❌ | Jadi `ws://…:443` → handshake gagal |
| `LAVALINK_URI=wss://lavalink.jirayu.net:13592` | ❌ | TLS ke port non-TLS → gagal |

**Pemulihan otomatis:** bila node terputus, `on_wavelink_node_closed` mencatat alasannya di log lalu bot
**menyambung ulang sendiri** (maks. sekali per 60 detik, menumpang watcher 15 detik yang sudah ada — **tanpa loop baru**).
Admin juga bisa memaksa lewat **`/musik node sambung:True`** tanpa me-restart bot.

### 3. Daftar Command (`/musik`)

| Command | Fungsi |
| :--- | :--- |
| **`/musik putar query:judul atau link`** | Cari & langsung putar (bot otomatis join voice channel kamu). Mendukung link YouTube, Spotify, SoundCloud, atau playlist. |
| **`/musik putar query:... berikutnya:True`** | Selalu **antrekan** tanpa memotong lagu yang sedang berjalan. |
| **`/musik cari query:...`** | Tampilkan 5 hasil + dropdown untuk memilih lagu. |
| **`/musik antrean halaman:2`** | Antrean **berhalaman** (10 lagu/halaman, tombol ◀ ▶) + total durasi. |
| **`/musik sekarang`** | Lagu aktif, **progress bar**, volume, filter, & mode pengulangan. |
| **`/musik jeda` / `/musik lanjut`** | Jeda / lanjutkan tanpa keluar voice. |
| **`/musik lewati jumlah:2`** | Lewati satu atau beberapa lagu. |
| **`/musik sebelumnya`** | Kembali ke lagu sebelumnya dari riwayat antrean. |
| **`/musik seek posisi:1:30`** | Lompat ke menit/detik tertentu (`95`, `1:30`, atau `01:02:03`). |
| **`/musik filter jenis:bassboost`** | Efek audio: `off`, `bassboost`, `nightcore`, `vaporwave`, `8d`, `karaoke`, `treble`. |
| **`/musik autoplay aktif:True`** | Putar rekomendasi otomatis begitu antrean habis. |
| **`/musik panel`** | Kirim ulang panel pemutar bila pesan lamanya terhapus. |
| **`/musik acak`** | Acak urutan antrean. |
| **`/musik ulang mode:mati\|satu\|semua`** | Mode pengulangan. |
| **`/musik volume level:70`** | Atur volume (disimpan sebagai default server, maks 150%). |
| **`/musik hentikan`** | Stop, kosongkan antrean, & keluarkan bot dari voice. |
| **`/musik pengaturan`** *(Admin)* | Pengumuman Now Playing, **role DJ**, & volume default. |
| **`/musik status`** | Cek **kondisi nyata node Lavalink**, antrean, volume, role DJ, & channel pengumuman. |
| **`/musik node sambung:True`** *(Admin)* | Diagnosa teknis node (status per node, jumlah player) & **sambung ulang paksa** tanpa restart. |
| **`/musik playlist simpan nama:Favorit`** | Simpan antrean (atau `dari:sekarang`) sebagai **playlist pribadi** — tersimpan permanen per member. |
| **`/musik playlist daftar`** / **`lihat`** | Lihat semua playlistmu & isinya (nomor lagu untuk hapus-lagu). |
| **`/musik playlist putar nama:Favorit`** | Mainkan playlist pribadi ke voice channel (`berikutnya:True` untuk menambah tanpa memotong). |
| **`/musik playlist hapus-lagu` / `ganti-nama` / `hapus`** | Kelola isi playlist (hapus pakai dialog konfirmasi). |

### 4. Perilaku & Pengamanan
- **Anti-nimbrung voice:** bot hanya bisa dikontrol member yang **berada di voice channel yang sama**, punya **role DJ**, atau Admin. Bot juga menolak berpindah channel kalau sedang memutar di channel lain.
- **Role DJ bukan syarat memutar lagu.** `/musik putar` cukup dijalankan sambil **berada di voice channel** (bot ikut masuk otomatis). Role DJ hanya mengunci **tombol kontrol** (⏯️ ⏭️ ⏹️) untuk member yang tidak berada di VC yang sama — atur dengan `/musik pengaturan role_dj:@DJ`.
- **Keluar otomatis** setelah `MUSIC_IDLE_DISCONNECT_SEC` (default 5 menit) tanpa lagu — hemat RAM & tidak "nangkring" di voice selamanya.
- **Batas antrean** `MUSIC_MAX_QUEUE` (default 50) agar RAM tetap kecil; lagu berlebih dilewati dengan pemberitahuan, bukan error.
- **Panel pemutar ala Rythm:** satu pesan per server yang **di-edit** (bukan pesan baru tiap lagu) berisi progress bar `▬▬🔘▬▬` + 9 tombol. Progress bar disegarkan **tiap 10 detik** oleh `music_panel_watcher` (dilewati total bila fitur musik nonaktif). Bila pesan panel terhapus, `/musik panel` mengirim ulang; bila bot keluar voice, panel ikut dibersihkan.
- **Filter & autoplay tersimpan per server** (`data/music_settings.json`) dan otomatis dipulihkan saat bot bergabung lagi ke voice channel.
- **Pengumuman Now Playing** otomatis di channel asal command (bisa dimatikan lewat `/musik pengaturan pengumuman:False`).
- **Tanpa FFmpeg lokal** sama sekali → aman untuk Wispbyte yang hanya boleh 1 proses.
- **Dependensi voice otomatis:** `requirements.txt` sudah memuat `wavelink`, `PyNaCl` (enkripsi voice), & `davey` (protokol DAVE Discord terbaru), jadi Wispbyte cukup `pip install -r requirements.txt` seperti biasa.
- **Tanpa node Lavalink pun bot tetap ringan**: modul musik hanya diimpor sekali, tidak ada loop latar belakang tambahan.

---

## G. Fitur Keramaian Server (`/giveaway`, `/ultah`, `/jawab-otomatis`, `/pengumuman`)

> 💡 **Empat fitur ini benar-benar 0 kuota Gemini.** Tidak ada satu pun permintaan AI, semuanya
> berjalan lokal memakai `data/engagement.json`. Cocok untuk server yang kuota AI-nya ingin
> dihemat untuk obrolan & ringkasan saja.

### 1. Giveaway (`/giveaway`)

| Command | Fungsi |
| :--- | :--- |
| **`/giveaway mulai hadiah:<teks> durasi:2jam pemenang:3`** | Pasang giveaway + tombol **🎉 Ikuti Giveaway** (peserta otomatis dicatat). |
| **`/giveaway mulai ... syarat_role:@Booster syarat_role_2:@Member`** | Peserta wajib punya **semua** role yang disebut. |
| **`/giveaway mulai ... syarat_level:5 syarat_umur_akun:30`** | Syarat berlapis: level server minimal & umur akun Discord minimal (hari). |
| **`/giveaway mulai ... role_bonus:@Booster bobot_bonus:2`** | Role bonus menambah peluang menang (bobot 1–5, dibatasi total 6×). |
| **`/giveaway mulai hadiah:... templat:nitro-bulanan`** | Pakai setelan tersimpan: pemenang, durasi, syarat, & bonus role. |
| **`/giveaway akhiri id_pesan:<ID>`** | Tutup lebih awal & umumkan pemenang. ID pesan dikirim saat giveaway dibuat. |
| **`/giveaway reroll id_pesan:<ID>`** | Undi ulang dari peserta yang belum pernah menang; setiap reroll tercatat. |
| **`/giveaway daftar`** | Giveaway yang masih berjalan + riwayat pemenang terakhir. |
| **`/giveaway peserta id_pesan:<ID>`** *(Admin)* | Daftar peserta + peluang masing-masing + riwayat undian & reroll. |
| **`/giveaway template-simpan / template-daftar / template-hapus`** | Kelola template giveaway rutin (maksimal 25 per server). |

- **Format durasi fleksibel:** `30m`, `2 jam`, `1j30m`, `2 hari`, `45` (menit). Minimal 1 menit. Kosongkan
  `durasi`/`pemenang` untuk memakai setelan bawaan server.
- **Syarat dicek saat tombol ditekan**, bukan saat pengundian: member langsung tahu apa yang kurang —
  *"role yang diwajibkan belum kamu miliki"*, *"level kamu belum mencapai 5"*, atau *"umur akun
  Discord-mu belum cukup"*. Tidak ada data member yang dikirim ke pihak lain.
- **Peluang ekstra tanpa curang:** pemilik role bonus mendapat bobot undian lebih besar (mis. `2×`),
  tetapi total bobot per peserta dibatasi `6×` dan satu akun tetap hanya terdaftar sekali.
- **Tahan restart:** tombol memakai `custom_id` persisten, jadi peserta tetap bisa klik setelah bot restart.
  Bobot, log peserta, & riwayat undian ikut tersimpan di `data/engagement.json`.
- **Riwayat undian:** siapa diundi lebih dulu, kapan, oleh siapa (manual via `/giveaway akhiri` atau
  otomatis oleh loop latar belakang) — tersimpan maksimal `GIVEAWAY_HISTORY_MAX` entri per giveaway.
- Peserta bisa membatalkan sendiri kapan saja sebelum waktu habis; giveaway yang waktunya habis
  ditutup otomatis oleh loop latar belakang (maksimal ±15 detik setelah waktunya).

### 2. Ulang Tahun (`/ultah`)

| Command | Fungsi |
| :--- | :--- |
| **`/ultah set tanggal:12-08`** | Daftarkan/perbarui tanggal lahir. Menerima `12-08`, `12/8/2000`, `12 Agustus 1999`, `1 Januari`. |
| **`/ultah daftar bulan:8`** | Lihat daftar ulang tahun member (opsional filter satu bulan). |
| **`/ultah hapus`** | Hapus data sendiri kapan saja. |
| **`/ultah atur channel:#umum jam:08:00`** *(Admin)* | Channel & jam ucapan otomatis. Kosongkan `channel` untuk mematikan. |

- Yang disimpan hanya **tanggal & bulan** (tahun opsional untuk menghitung umur). Tidak ada data lain.
- Ucapan dikirim **sekali per hari** pada jam yang diatur, mengikuti zona waktu server (`/agent` persona/timezone).

### 3. Balasan Otomatis (`/jawab-otomatis`)

| Command | Fungsi |
| :--- | :--- |
| **`/jawab-otomatis tambah pemicu:cara daftar balasan:Ketik /verifikasi`** | Bot menjawab saat kata kunci muncul. |
| **`/jawab-otomatis tambah pemicu:ping balasan:pong persis:True`** | Hanya menanggapi bila pesannya **sama persis**. |
| **`/jawab-otomatis daftar`** / **`hapus pemicu:...`** | Lihat & hapus aturan di channel tersebut. |
| **`/jawab-otomatis atur aktif:False jeda:30`** | Jeda/matikan tanpa menghapus aturan. |

- **Aman untuk obrolan:** hanya aktif di channel yang dipilih Admin, minimal pemicu 3 karakter,
  dan ada **jeda aman** (default 20 detik) agar bot tidak pernah membanjiri channel.
- Maksimal `AUTO_REPLY_MAX_RULES` (default 25) aturan per channel.

### 4. Pengumuman Terjadwal (`/pengumuman`)

| Command | Fungsi |
| :--- | :--- |
| **`/pengumuman tambah isi:... jadwal:08:00`** | Setiap hari pukul 08:00 (waktu server). |
| **`/pengumuman tambah isi:... jadwal:senin 19:00`** | Setiap minggu (nama hari Indonesia). |
| **`/pengumuman tambah isi:... jadwal:sekali 31-12-2026 23:59`** | Satu kali saja, lalu otomatis nonaktif. |
| **`/pengumuman daftar`** / **`hapus id:3`** / **`atur id:3 aktif:False`** | Kelola jadwal tanpa menghapus isi. |
| **`/pengumuman kirim id:3`** | Kirim **sekarang** tanpa menunggu jadwal — jadwal berikutnya tidak digeser. |
| **`/pengumuman ubah id:3 isi:... judul:... jadwal:...`** | Ubah isi/judul/jadwal tanpa menghapus; jadwal baru langsung dihitung. |

- Format jadwal ringkas: `08:00`, `harian 20:30`, `senin 19:00`, `mingguan sabtu 20:30`, `sekali 31-12-2026 23:59`.
- **Berulang tiap interval:** `setiap 3 jam`, `tiap 90 menit`, `interval 8 jam` — minimal **2 jam**
  (batas aman agar tidak dianggap spam), maksimal **168 jam** (seminggu). Jadwal dihitung dari
  waktu pemasangan, dan kalau bot sempat mati lama, semua jadwal yang terlewat **dilewati** —
  hanya satu kiriman berikutnya yang diambil, jadi pengumuman tidak menumpuk.
- Isi pengumuman boleh memakai variabel (`{server.name}`, `{server.members}`, `{now_relative}`) yang diisi **saat dikirim**.
- Tujuan boleh **thread** (bukan hanya channel teks). Pengumuman ulang tahun juga ikut mendukung thread.
- Pengumuman **sekali** otomatis dinonaktifkan setelah terkirim sehingga tidak pernah dobel.
- Batas `ANNOUNCEMENT_MAX_PER_GUILD` (default 15) pengumuman per server.

---

## H. Anti-Spam & Anti-Raid Ringan (`/keamanan spam`)

> 🕊️ **Filosofi fitur ini: "lapor dulu, tindak belakangan".** Banyak bot moderasi merusak obrolan
> karena terlalu cepat menghapus atau menendang. Di sini **mode bawaan hanya melapor** ke channel log,
> dan seluruh staf selalu dikecualikan.

### 1. Command

| Command | Fungsi |
| :--- | :--- |
| **`/keamanan spam aktif:True`** | Nyalakan penjaga dalam **mode lapor** (aman, tanpa tindakan). |
| **`/keamanan spam mode:hapus log_channel:#mod-log`** | Hapus pesan spam + catat ke channel log. |
| **`/keamanan spam mode:timeout timeout_detik:600`** | Hapus + time-out member sementara (maks 1 hari). |
| **`/keamanan spam ambang_banjir:8 jendela:15`** | Sesuaikan sensitivitas flood. |
| **`/keamanan spam mention_maks:10 link_maks:5`** | Sesuaikan batas mention & link. |
| **`/keamanan spam kapital:True`** | Ikut menindak HURUF KAPITAL berlebihan (default nonaktif). |
| **`/keamanan spam kecualikan_channel:#ngobrol kecualikan_role:@Staf`** | Pengecualian permanen. |
| **`/keamanan spam-status`** | Lihat ambang, pengecualian, mode, & jumlah tindakan. |
| **`/keamanan spam aktif:False`** | Matikan total kapan saja. |

### 2. Yang dideteksi

| Pemicu | Ambang bawaan | Catatan |
| :--- | :--- | :--- |
| 🌊 **Banjir pesan** | 6 pesan / 10 detik | Per member per channel; tidak pernah lintas channel. |
| 🔁 **Pesan berulang** | isi sama 3x / 30 detik | Link dinormalisasi agar tidak lolos dengan variasi URL. |
| 📣 **Mention massal** | 6 mention dalam 1 pesan | Deteksi paling cepat & paling aman. |
| 🔗 **Link beruntun** | 4 link dalam 1 pesan, atau link sama 3x / 60 detik | Berguna untuk spam iklan. |
| 🔠 **Huruf kapital** | ≥70% kapital & ≥20 karakter | **Default NONAKTIF** (sering salah tuduh). |
| 🚨 **Raid (join)** | 8 join / 60 detik | **Hanya peringatan** ke channel log + saran tindakan. |

### 3. Penguji aturan & statistik per aturan (dashboard)

| Aspek | Detail |
| :--- | :--- |
| **Penguji aturan** | Halaman **🛡️ Keamanan** → panel *Penguji aturan & statistik*. Tempel contoh pesan (+ "dibayangkan dikirim berapa kali"), lalu lihat **aturan mana yang kena** beserta angkanya. |
| **Tanpa tindakan** | Penguji **tidak** menghapus pesan, **tidak** me-time-out siapa pun, dan **tidak** mengubah riwayat anti-spam — murni simulasi, jadi aman dipakai saat jam sibuk. |
| **Hasil bertahan** | Hasil uji terakhir disimpan per server (di memori) sehingga tetap terlihat setelah form dikirim — tanpa JavaScript. |
| **Statistik per aturan** | Tabel **hari ini / total** untuk tiap aturan (`antispam.py` mencatatnya setiap kali aturan benar-benar menangkap pesan), plus mode tindakan, status aktif, dan total tertangkap. Statistik ikut tersimpan di `data/antispam.json`. |
| **Jalur tulis** | `POST /api/keamanan` (`action=uji-aturan`) — wajib token, tanpa efek samping. |

### 4. Pengamanan bawaan

- **Staf aman:** pemilik `Administrator`, `Manage Messages`, atau `Manage Guild` **tidak pernah** diperiksa.
- **Bot aman:** seluruh pesan bot lain diabaikan.
- **Satu laporan / 2 menit per member** agar channel log tidak dibanjiri (raid: 1 laporan / 4 menit).
- **Tidak ada ban otomatis.** Time-out hanya bila Admin memilih `mode:timeout`, maksimal 1 hari.
- **Tanpa AI & tanpa API eksternal** → 0 kuota Gemini, tetap ringan (state runtime dibersihkan tiap jam).

---

## I. Level & XP serta Tiket Dukungan (`/level`, `/tiket`)

> 🧩 Kedua fitur ini **retensi + pelayanan**: membuat warga betah (level & papan peringkat) dan
> membuat staf rapi menangani bantuan (tiket thread). **Tanpa AI, tanpa database eksternal.**

### 1. Leveling & XP (`/level`)

| Command | Fungsi |
| :--- | :--- |
| **`/level lihat [member]`** | Kartu level + progress bar `▰▰▰▱▱`, total XP, & jumlah pesan. |
| **`/level kartu [member] [publik:True]`** | **Kartu rank PNG** dirender server (Pillow): foto profil bulat, nama, level, prestise, peringkat `#3 / 24`, progress bar, & ringkasan aktivitas. Tanpa Pillow/kartu dimatikan → otomatis kembali ke kartu teks. |
| **`/level papan halaman:1`** | Papan peringkat 10 besar (🥇🥈🥉) + total member terdata. |
| **`/level atur aktif:True jeda:60 xp_minimal:15 xp_maksimal:25`** *(Admin)* | Nyalakan & atur XP. |
| **`/level atur pengumuman:False channel_pengumuman:#level`** | Atur pengumuman naik level. |
| **`/level atur abaikan_channel:#spam abaikan_role:@Bot`** | Kecualikan channel/role dari XP. |
| **`/level role level:5 role:@Aktif`** *(Admin)* | Hadiah role otomatis saat mencapai level 5. |
| **`/level role level:5`** *(tanpa role)* | Hapus hadiah level tersebut. |
| **`/level voice aktif:True xp_per_menit:2 batas_menit_harian:240`** *(Admin)* | Nyalakan & atur **XP Voice** (0 kuota AI). |
| **`/level voice abaikan_channel:#musik`** *(Admin)* | Kecualikan voice channel tertentu dari hitungan XP. |
| **`/level voice`** *(tanpa argumen)* | Lihat setelan XP Voice server ini. |
| **`/level status`** | Statistik: member terdata, XP tertinggi, total level-up, peta hadiah, & status XP Voice. |
| **`/level atur aktif:False`** | Matikan (data XP tetap tersimpan). |
| **`/level musim status`** | Musim berjalan, sisa hari, peringkat sementara, & juara musim lalu. |
| **`/level musim ulang konfirmasi:True reset_otomatis_hari:90`** *(Admin)* | Tutup musim & mulai musim baru (XP direset, prestige disimpan). |
| **`/level prestise`** | Tukar level maksimum menjadi **1× Prestige** (XP kembali 0, trofi permanen). |

**Rumus & batas:**
- XP per pesan acak `LEVELS_XP_MIN`–`LEVELS_XP_MAX` (default **15–25**), dengan **jeda `LEVELS_COOLDOWN_SEC`** (default **60 detik**) per member → tidak bisa di-*farming*.
- Kebutuhan XP level: `5·L² + 50·L + 100` (level 0→1 = 100 XP, 1→2 = 155 XP, 5→6 = 475 XP).
- Data per member hanya `xp`, `level`, `messages`, `voice_xp`, `voice_sec`, `prestige`, & waktu terakhir; disimpan **maksimal 500 member teratas per server** (`LEVELS_MAX_MEMBERS`) agar JSON tetap kecil.

**🏁 Musim Level & 🌟 Prestige (0 kuota AI):**

| Fitur | Detail |
| :--- | :--- |
| **Musim** | Setiap server punya nomor musim. `/level musim ulang konfirmasi:True` menutup musim: XP semua member direset, **3 juara teratas** disimpan sebagai riwayat (maks 12 musim), lalu musim baru dimulai. |
| **Reset otomatis** | `reset_otomatis_hari:N` (1–365) membuat bot mereset musim otomatis setiap N hari. **Default nonaktif** (manual saja) supaya tidak mengejutkan member. |
| **Prestige** | Member yang mencapai `LEVELS_MAX_LEVEL` bisa `/level prestise`: level & XP kembali 0, dapat **1× Prestige** permanen yang tampil di kartu level & papan peringkat. Bisa dimatikan Admin (`prestige_aktif`) atau syaratnya diturunkan. |
| **Pengumuman** | Saat musim berganti, bot mengumumkan juara musim ke channel pengumuman level (bila diatur). 0 kuota AI — semua dihitung lokal. |

**🎙️ XP Voice (`/level voice`) — 0 kuota AI:**
- Member dapat `LEVELS_VOICE_XP_PER_MIN` XP (default **2**) untuk setiap **menit penuh** berada di voice channel, dan XP masuk ke total yang sama seperti XP pesan (kurva level tidak berubah).
- **Anti-eksploit:** XP dihitung **per menit** (bukan per join/leave), **self-mute & self-deaf tidak dihitung**, channel **AFK** server dilewati, dan ada **batas `LEVELS_VOICE_DAILY_CAP_MIN`** (default **240 menit/member/hari**) supaya tidak bisa "idle 24 jam".
- Sesi voice **tidak disimpan ke disk** dan di-reset saat restart, jadi tidak ada XP "hantu" dari waktu bot mati.
- Kenaikan level dari voice tetap memakai **role hadiah** & **pengumuman** level yang sama (dikirim ke channel pengumuman, atau `system_channel` bila belum diatur).

### 2. Tiket Dukungan (`/tiket`)

| Command | Fungsi |
| :--- | :--- |
| **`/tiket panel channel:#bantuan staff_role:@Staf log_channel:#log-tiket max_open:2`** *(Admin)* | Pasang panel **🎟️ Buat Tiket**. |
| **`/tiket status`** | Konfigurasi, statistik, & daftar tiket aktif. |
| **`/tiket daftar [hanya_milikku:True]`** | Tiket yang masih terbuka/ditangani. |
| **`/tiket tambah member:@X`** | *(Staf)* Tambahkan pihak lain ke thread tiket. |
| **`/tiket tutup`** | Tutup tiket (pembuat atau staf) + kirim transkrip. |
| **`/tiket atur sla_jam:2 auto_close_jam:72 rating_aktif:True channel_sla:#mod-log`** *(Admin)* | Batas **SLA respons pertama**, **auto-close** tiket menganggur, & kartu **rating bintang**. |
| **`/tiket rating`** | Rata-rata rating bintang, sebaran bintang, & statistik SLA server. |
| **`/tiket catat teks:...`** *(Staf)* | Catatan internal — **tidak dikirim ke thread**, hanya tersimpan & tampil di dashboard. |
| **`/tiket catatan [hapus:<nomor>]`** *(Staf)* | Lihat/hapus catatan internal tiket ini (1 = paling lama). |
| **`/tiket topik [tambah:<nama>] [hapus:<nama>] [role:@Staf] [emoji:🛒] [deskripsi:...]`** *(Admin)* | Atur **beberapa topik** pada satu panel. Tanpa argumen = daftar topik. |
| **`/tiket matikan`** *(Admin)* | Matikan sistem tiket (thread lama tetap bisa dibaca). |

**Cara kerja:**
1. Member klik **🎟️ Buat Tiket** → bot membuat **private thread** `tiket-<nama>` (bukan channel baru → tidak memakan slot 500 channel/server).
   Bila panel sudah punya **topik** (mis. *Pembelian*, *Lapor Bug*), tombol tunggal berganti menjadi
   **dropdown topik**; thread-nya bernama `tiket-<topik>-<nama>`, judul tiket menyebut topiknya, dan
   yang diundang adalah **role staf topik itu** (kalau belum diatur, ikut role staf umum). Tombol
   **Topik lain** tetap tersedia untuk keluhan yang tidak masuk daftar. Maksimal
   `TICKET_TOPIC_MAX` (default **8**) topik per server, nama maks `TICKET_TOPIC_LEN` (40) karakter.
2. Pembuat tiket otomatis ditambahkan, lalu **maksimal 15 staf** dari role petugas ikut ditambahkan; sisanya bisa lewat `/tiket tambah`.
3. Staf memakai **🙋 Klaim** (thread di-rename `tiket-0001-ditangani`) dan **🔒 Tutup Tiket**.
4. Saat ditutup: thread **di-lock & diarsipkan**, lalu **transkrip `.txt`** (maks `TICKET_MAX_TRANSCRIPT_LINES`) dikirim ke `log_channel`.
   Transkrip juga diarsipkan sebagai **HTML** di `data/transcripts/<server>/` sehingga bisa **dibuka & dicari
   dari dashboard** (halaman `/tiket` → subpanel *Arsip transkrip*) tanpa mengunduh berkas. Arsip
   dibatasi `TICKET_ARSIP_MAX` (default **200** tiket/server) dan `TICKET_ARSIP_RETENSI_HARI`
   (default **180 hari**; `0` menonaktifkan batas umur). Yang melewati batas jumlah/umur dihapus
   otomatis saat tiket diarsipkan dan saat bot mulai. Pasangan HTML/TXT utuh tanpa indeks akan
   direkonstruksi; berkas sementara atau pasangan tidak lengkap dibersihkan.
   Setiap tiket juga bisa diberi **catatan internal staf** (`/tiket catat` atau kotak di dashboard):
   disimpan di `data/tickets.json`, maksimal **25 catatan** per tiket, dan **tidak pernah** dikirim
   ke thread — member tidak bisa membacanya.
5. Batas tiket aktif per member `TICKET_MAX_OPEN_PER_USER` (default **2**) mencegah spam tiket.

**Kartu rank PNG (v1.40.0-beta, 0 kuota AI):**

| Aspek | Detail |
| :--- | :--- |
| **Perender tunggal** | `rank_card.py` merender kartu untuk **`/level kartu`** *dan* pratinjau dashboard (`GET /api/rank.png`) — preview = hasil asli, bukan gambar contoh. |
| **Yang tampil** | Foto profil bulat + cincin warna aksen, nama, level, prestise (`· PRESTISE ×2`), peringkat `#3 / 24`, progress bar XP, total XP, server · musim · jumlah pesan. Member tanpa avatar dapat lingkaran inisial; nama & angka panjang dipotong dengan `…`, bukan merusak tata letak. |
| **Latar** | Gradasi warna aksen bawaan, atau **gambar yang diunggah** dari dashboard (slot *kartu rank*, PNG/JPG/GIF/WEBP, maks 8 MB). |
| **Setelan** | Sakelar **Kartu rank PNG**, warna aksen hex (`#5865F2`), unggah/hapus latar, dan **tombol tes** — semuanya di halaman **⚙️ Inti & level** (rule #72). |
| **Batas** | Ukuran 1024×360 px, hasil ±18–30 KB. Tanpa Pillow terpasang, fitur otomatis mundur ke kartu teks (tidak pernah error ke member). |

**Kualitas layanan tiket (v1.33.0-beta, 0 kuota AI):**

| Fitur | Detail |
| :--- | :--- |
| **⭐ Rating bintang** | Setelah tiket ditutup, pembuat tiket menerima kartu **1–5 bintang** di thread (sebelum thread dikunci). Hanya pembuat tiket yang bisa menilai, satu kali per tiket. Rekap di `/tiket rating`. |
| **⏰ SLA respons pertama** | Bot mencatat **pesan staf pertama** di tiket. Bila belum ada respons sampai `sla_jam`, peringatan dikirim ke `channel_sla` / channel log (sekali per tiket, anti-spam). |
| **🧹 Auto-close** | Tiket tanpa aktivitas selama `auto_close_jam` ditutup otomatis: pesan penjelasan, transkrip tetap dikirim ke log, thread dikunci & diarsipkan. Aktivitas member (termasuk pembuat tiket) memperbarui hitungan. |
| **Default aman** | Rating **aktif**, SLA & auto-close **nonaktif** (`0`) sampai Admin menyalakannya. Pemeriksaan berjalan tiap 1 menit di watcher yang sudah ada. |

---

## J. Dashboard Web (`DASHBOARD_TOKEN`)

Satu server web ringan (proses yang sama dengan bot) untuk memantau **dan** mengatur bot
tanpa membuka Discord: status, pemakaian AI, papan level, peta fitur, **56 setelan server
dalam 14 halaman** (satu grup fitur = satu halaman), **kirim embed/webhook**, unggah banner
& kartu sambutan, kotak masuk tiket, kendali giveaway, panel moderasi (antrean laporan &
banding), generator gambar & prompt AI server, petunjuk privasi mandiri, serta **24 tombol tes fitur**.
Template halaman depan ada di [README](../README.md#-dashboard-web-sekilas); rincian tiap
bagian ada di [Dashboard web (panel admin lengkap)](#dashboard-web-panel-admin-lengkap).

| Aspek | Detail |
| :--- | :--- |
| **Cara nyala** | Isi `DASHBOARD_TOKEN` (kata sandi acak) **dan** sediakan port (`DASHBOARD_PORT`, atau otomatis dari `SERVER_PORT`/`PORT` panel). Kosong = dashboard mati. |
| **Akses** | `http://<ip-server>:<port>/?token=<DASHBOARD_TOKEN>` — token juga bisa lewat header `X-Dashboard-Token` / `Authorization: Bearer` atau field tersembunyi pada form. |
| **Endpoint baca** | `/` (HTML), `/api/status`, `/api/pemakaian?guild=<id>`, `/api/level?guild=<id>`, `/api/kontrol?guild=<id>`, `/api/fitur?guild=<id>`, `/api/setelan?guild=<id>`, `/healthz` (tanpa token). |
| **Endpoint tulis** | Empat belas jalur `POST`, semuanya **wajib token**: `/api/aksi` (setelan), `/api/ai` (buat gambar atau simpan prompt server; prompt/gambar tidak masuk audit), `/api/kirim` (pesan/embed/webhook + pratinjau), `/api/konten` (buat/hapus konten), `/api/unggah` (banner & kartu), `/api/uji` (tes fitur), `/api/tiket` (balas/tutup tiket, panel tiket, topik, catatan staf), `/api/panel` (tombol/dropdown & verifikasi),
`/api/giveaway` (buat/hentikan/reroll giveaway, template, & setelan bawaan),
`/api/transkrip` (hapus arsip transkrip tiket),
`/api/keamanan` (penguji aturan anti-spam), `/api/lencana` (setelan lencana), `/api/bangun` (pratinjau tema/AI, terapkan, batal, bongkar tercatat),
`/api/moderasi` (setelan jalur laporan, status antrean, cari kasus, cabut temp-ban). Aksi lama (`level`, `ekonomi`, `tumbuh`, `antispam`, `antinuke`) tetap didukung. |
| **Endpoint unduh** | `/api/tren` (tren AI 7 hari), `/api/ekspor?jenis=…` (CSV level/moderasi/tiket/pemakaian), & `/api/transkrip?kode=…` (transkrip HTML satu tiket). |
| **Arsip transkrip** | Halaman `/transkrip` berisi kotak pencarian (dicari di **isi percakapan**, bukan cuma judul) + tautan buka/hapus. Tanpa JavaScript, tanpa login tambahan. |
| **Setelan** | **56 fitur** dalam 5 grup: inti/level/ekonomi, sambutan & pamit, keamanan, tiket & sapaan harian, konten & interaksi. |
| **Whitelist** | Hanya kunci yang terdaftar di `dashboard_admin.FITUR` yang bisa dijalankan — nama fungsi bebas tidak pernah dieksekusi. |
| **Mitigasi** | Halaman `/` tetap **GET-only** (POST ke `/` ditolak). Tidak ada `PUT`/`DELETE`/`PATCH`. Tombol Hapus hanya membuang satu item. Perubahan dicatat sebagai metadata di `data/dashboard_audit.json` dan log bot; prompt bebas serta isi gambar tidak direkam. |
| **Unggahan** | Banner/gambar bisa diunggah dari dashboard (`DASHBOARD_UPLOAD_MB`, bawaan 8 MB) ke `data/uploads/` lalu dipakai sebagai banner panel, gambar embed, atau lampiran webhook. |
| **Biaya** | Membuka/mengatur dashboard tidak memanggil AI; `/gambar` dan rancangan AI `/bangun` memakai kuota hanya saat diminta. ±2–4 MB RAM, tanpa dependency baru, tetap **1 proses**. |
| **Tanpa JS** | HTML dirender di server (semua form HTML biasa), `meta refresh` bawaan **30 detik** (`DASHBOARD_REFRESH_SEC`; `0` = mati) dan **bisa diatur sendiri lewat satu dropdown di header** tanpa restart → ringan dibuka dari HP. |

> ⚠️ Dashboard hanya bisa dibuka dari luar bila panel hosting memberi **port allocation**.
> Di Wispbyte cek tab **Network / Allocations**; bila tidak ada alokasi, dashboard otomatis
> tidak menyala dan bot tetap berjalan normal (tidak ada error).

### Dashboard web (panel admin lengkap)

Bot menjalankan satu halaman web di port privat (`DASHBOARD_PORT`, token di env) yang
memuat **status bot, pemakaian AI, papan level, peta fitur, dan pengaturan server** —
fitur dibagi ke **14 halaman** per grup, tanpa dependency baru dan tetap satu proses. AI hanya dipanggil secara eksplisit untuk gambar atau rancangan `/bangun`.

| Bagian | Isi |
| :--- | :--- |
| **Pemilih server** | dropdown server di pojok atas (muncul otomatis bila bot ada di lebih dari satu server) — tanpa login, cukup token |
| **Menu ☰ & navigasi** | header menempel di atas + menu pindah halaman (satu halaman per grup fitur); di HP menu berubah jadi **hamburger** (CSS murni, tanpa JavaScript) |
| **Status & pemakaian** | uptime, RAM, latensi, server/member, status Gemini, token masuk/keluar, cache hit, FAQ lokal |
| **Tren 7 hari** | grafik batang SVG (operasi AI & cache per hari) — dirender di server, tanpa JavaScript |
| **Peta fitur** | fitur apa yang sudah dipakai (panel, formulir, pengumuman, tautan, pemicu) + ✅/⬜ |
| **Kontrol Cepat** | sakelar level, ekonomi, & pertumbuhan dengan **tombol yang mengikuti keadaan** (“Nonaktifkan” saat aktif, “Aktifkan” saat mati) + mode anti-spam & aksi anti-nuke |
| **Setelan server** | **56 setelan** dalam 5 grup (lihat tabel di bawah) |
| **Kirim pesan & embed** | kirim pengumuman sekali jalan, atau lewat **identitas webhook** (nama & avatar sendiri), lengkap dengan **pratinjau sebelum kirim** |
| **Banner & gambar** | **unggah banner** (PNG/JPG/GIF/WEBP) lalu pakai untuk banner panel atau gambar embed, tanpa perlu URL publik |
| **Kartu sambutan** | **unggah sendiri** tiga gambar kartu (sambutan, pamit, boost) di halaman `/sambutan` — satu bagian per kartu; disimpan di `data/media/`, dikirim ulang sebagai lampiran jadi tidak kedaluwarsa |
| **Kartu rank** | Halaman `/inti` → panel **🖼️ Kartu rank (PNG)**: pratinjau `GET /api/rank.png` memakai perender yang **sama** dengan `/level kartu`, sakelar hidup/mati, warna aksen hex, unggah/hapus latar, & tombol tes render. |
| **Tes fitur** | tombol **Kirim tes** ada di halaman fiturnya (sambutan, perpisahan, boost, pengumuman, panel, tiket, giveaway, koran pagi, koneksi AI, ekspor). Subjek tes **tidak perlu ID**: kosongkan saja → bot memakai **pemilik server** |
| **Buat konten** | pengumuman terjadwal, tautan embed `/l/<kode>`, panel menu (+ langsung terkirim), **formulir (modal)**, **pemicu saat member bergabung** |
| **Konten tersimpan** | daftar pengumuman/tautan/panel/formulir/webhook + tombol **Hapus** |
| **Kotak masuk formulir** | panel *📬 Kotak masuk formulir*: semua jawaban formulir dikumpulkan sebagai **antrean** (nomor, formulir, pengirim, waktu, status **baru/selesai**) — jawaban bisa dibaca langsung, **tandai selesai**, **buka lagi**, atau **hapus**. Batas 200/server, dibersihkan otomatis setelah 30 hari. Jalur tulis: `POST /api/konten` (`inbox-selesai:<nomor>`, `inbox-buka:<nomor>`, `inbox-hapus:<nomor>`). |
| **AI & privasi** | halaman `/ai`: generator `/gambar` (prompt, channel, gaya, rasio, lampiran acuan opsional) + prompt kepribadian AI server. Lampiran divalidasi dan diproses di memori; prompt tidak dicatat di audit. Per-member memakai `/setelan-ai`; `/dataku` dan `/hapusdataku` tetap ephemeral dan hanya untuk pemilik akun. |
| **Bangun server** | halaman `/bangun`: pilih satu dari 15 tema (0 kuota AI) atau rancang dengan AI; tinjau pratinjau, tekan Terapkan secara eksplisit, lihat riwayat, dan bongkar hanya item tercatat |
| **Giveaway** | halaman `/giveaway`: buat giveaway dari HP (hadiah, channel, durasi, pemenang, level, umur akun, role bonus), **hentikan**, **undi ulang**, simpan/hapus **template**, dan atur **setelan bawaan** — semua memakai fungsi yang sama dengan command Discord |
| **Kotak masuk tiket** | daftar tiket aktif (umur, diam, status, SLA) + **balas** & **tutup** langsung dari web, plus **pasang panel tiket** |
| **Moderasi** | Halaman `/moderasi`: antrean **laporan member** & **banding** (ubah status + catatan), **setelan jalur laporan** (channel, cooldown, DM pelapor), daftar **temp-ban** dengan tombol cabut, **pencarian kasus** (nomor/ID/kata/jenis aksi), **statistik staf** 30 hari, & kasus terbaru |
| **Editor panel** | tambah/hapus **tombol** (role, tautan, perintah, alur, formulir) & **dropdown role** — panel di Discord langsung disegarkan |
| **Panel verifikasi** | pasang/matikan gerbang verifikasi (tombol sekali klik → role) tanpa command |
| **Ekspor CSV** | unduh data level, moderasi, tiket, & pemakaian AI langsung dari browser |
| **Riwayat perubahan** | 8 perubahan terakhir dari dashboard (siapa-waktu-nilai-hasil) |

#### Tampilan (tema gelap + General Sans)

| Bagian | Nilai |
| :--- | :--- |
| **Latar** | `#0D0D0F` (hitam netral) — sama untuk halaman utama, halaman pratinjau embed, dan halaman hasil submit |
| **Warna teks** | `#FFFFFF`; teks sekunder memakai putih transparan (`rgba(255,255,255,.62)`) |
| **Font** | **General Sans** (Fontshare, bobot 400/500/600/700) dimuat lewat `api.fontshare.com`; cadangan `Inter` → `system-ui` → `Segoe UI` bila CDN tidak terjangkau |
| **Aksen** | ungu `#8B7CFF` (fokus, tautan), biru Discord `#5865F2` (tombol utama), hijau `#4ADE80` (berhasil), kuning `#FBBF24` (peringatan), merah `#E5484D` (tombol hapus/tutup) |
| **Bentuk** | kartu radius 16 px, garis `rgba(255,255,255,.09)`, lapisan gradien/glow ungu yang halus, tanpa JavaScript |
| **Layout** | sidebar tetap selebar 252 px di desktop (≥ 821 px), kartu statistik responsif bergaya bento; di HP menu tetap checkbox CSS |
| **Aksesibilitas** | `color-scheme: dark`, outline fokus ungu 2 px, menu bisa dioperasikan keyboard, `prefers-reduced-motion` menghilangkan gerak |

Arah visual mengadaptasi pola sidebar, status aktif, dan kartu metrik dari
[hasil pencarian dashboard Dribbble](https://dribbble.com/search/dashboard),
[Dashboard with Collapsible Sidebar](https://21st.dev/@uniquesonu/components/dashboard-with-collapsible-sidebar),
dan [Stats Bento](https://21st.dev/@uilayout.contact/components/stats-bento) di 21st.dev.
Yang diambil hanya pola visualnya—tidak menyalin React/Tailwind atau menambah dependency; halaman tetap HTML server-rendered tanpa JavaScript.

Semua warna & font tinggal di satu modul, `dashboard_tema.py` (`LATAR`, `TEKS`,
`FONT_STACK`, `CSS_HALAMAN`, `CSS_PRATINJAU`, `CSS_HASIL`) — mengganti tema cukup
mengubah satu berkas itu, tanpa menyentuh `web_dashboard.py` atau `dashboard_ui.py`.

#### Satu grup fitur = satu halaman (menu ☰ di HP)

Dashboard tidak lagi satu halaman gulung panjang, dan **tidak ada halaman tes gabungan**.
Fitur yang saling berhubungan digabung dalam **satu halaman per grup**, jadi mengatur lalu
menguji satu kelompok fitur tidak perlu berpindah-pindah halaman.

| Halaman | Isi | Panel |
| :--- | :--- | :--- |
| `/` | Ringkasan: status, pemakaian AI, jenis operasi, tren 7 hari, channel teramai, papan level | 6 |
| `/ai` | Generator gambar + lampiran acuan, prompt server, privasi mandiri, **tes koneksi AI** | 4 |
| `/sambutan` | **sambutan + pamit + boost** jadi satu halaman: tiap bagian punya setelan, **gambar kartu**, & **tombol tes** sendiri (`#p-welcome`, `#p-goodbye`, `#p-boost`) | 1 |
| `/inti` | **Kontrol Cepat** + setelan grup **inti, level, & ekonomi** (prefix, kartu rank, lencana, koin harian, …) | 4 |
| `/keamanan` | setelan **anti-spam, anti-nuke, pengaman raid, verifikasi, & anti-phishing** | 1 |
| `/moderasi` | Antrean laporan/banding, pencarian kasus, temp-ban, statistik staf, snipe | 2 |
| `/tiket` | Kotak masuk tiket + pasang panel tiket + setelan **tiket & sapaan harian** + arsip + **tes panel tiket** | 1 |
| `/konten` | **Konten & interaksi** (Auto-Chat AI, starboard, saran, fakta harian, koran pagi, backup, …) + statistik & tes | 2 |
| `/bangun` | Tema lokal atau rancangan AI; pratinjau, Terapkan eksplisit, riwayat & bongkar item tercatat | 1 |
| `/giveaway` | Buat/hentikan/undi ulang giveaway, template, syarat & setelan bawaan | 1 |
| `/kirim` | Kirim pesan/embed + pratinjau, banner & unggahan | 2 |
| `/buat` | Buat pengumuman/tautan/panel/formulir/pemicu + konten tersimpan & kotak masuk formulir | 3 |
| `/panel` | Editor tombol & dropdown + gerbang verifikasi + **tes panel** | 1 |
| `/ekspor` | Ekspor CSV + riwayat perubahan + **tes ekspor** | 2 |

Aturan mainnya:

| Bagian | Perilaku |
| :--- | :--- |
| **Menu halaman** | 📡 Ringkasan · 🤖 AI & Privasi · 👋 Sambutan · ⚙️ Inti · 🛡️ Keamanan · 🚨 Moderasi · 🎫 Tiket · 🧩 Konten · 🏗️ Bangun · 🎁 Giveaway · ✉️ Kirim · ➕ Buat · 🎨 Panel · 📥 Ekspor; halaman aktif ditandai `aria-current="page"` (warna ungu) |
| **Token & server terbawa** | setiap tautan menu menyertakan `?token=…&guild=…`, jadi pindah halaman tidak pernah keluar sesi (tetap tanpa login) |
| **Sidebar desktop** | di layar ≥ 821 px navigasi fitur menjadi sidebar tetap; halaman aktif ditandai ungu, sedangkan pilihan server & auto-refresh ada di bawah |
| **Menu HP** | di layar ≤ 820 px sidebar berubah menjadi bar atas lengket dengan tombol **☰ Menu**; buka/tutup lewat `<input type="checkbox">` + CSS, **tanpa JavaScript** (tetap bisa diakses keyboard) |
| **Judul halaman** | judul + ringkasan fitur tampil di area konten; nama server, versi, waktu baca, dan interval refresh tetap terlihat di navigasi |
| **Anchor tetap ada** | tiap panel & bagian masih punya `id` (`#p-welcome`, `#p-inti`, `#p-tiket`, …) + `scroll-margin-top`, jadi `…/sambutan#p-goodbye` bisa dipakai sebagai bookmark |
| **Bookmark lama** | `/setelan` → `/inti`, `/perpisahan` & `/boost` → `/sambutan`, `/uji` → `/ai` (semua `303`); anchor lama (`#p-setelan` → `/inti`, `#p-perpisahan` → `/sambutan`) ikut diarahkan; `/api/*` tidak berubah |

#### Setelah menekan Simpan

Form memakai pola **POST → redirect (303) → GET**: setelah menyimpan, kamu kembali ke
**halaman asal** dan panel yang sama (`/kirim#p-banner`, `/inti#p-kontrol`, …) lalu
melihat kotak pesan ✅ berisi hasilnya — nilai barunya sudah
terbaca dari JSON, jadi tidak perlu klik “kembali” atau muat ulang. Kalau gagal pun kamu
tetap dikembalikan ke halaman fiturnya (`…?pesan=…&ok=0`) dengan kotak ⚠️ berisi alasannya —
tidak ada lagi halaman buntu tanpa jalan pulang.
Endpoint JSON (`Content-Type: application/json`) tetap menerima `200`/`400` + `{"ok": …}`
tanpa redirect.

> 🐞 **Perbaikan**: saklar **Level & XP** dulu kembali ke “Aktif” setelah disimpan jadi
> “Nonaktif”, karena pembacaan setelan memakai `get_level_config()` yang membuat konfigurasi
> default (`enabled: True`) dan `set_level_config(aktif=False)` menghapus konfigurasi.
> Sekarang dashboard memakai `peek_level_config()` (baca tanpa membuat config) dan
> `set_level_enabled()` (menyimpan `enabled: False` tanpa menghapus setelan XP/channel/season).

#### Kartu sambutan sendiri (unggah dari dashboard)

Tiap bagian di halaman `/sambutan` punya slot unggahnya sendiri — **satu menu unggah,
di dalam bagian fiturnya**:

| Bagian di `/sambutan` | Slot | Dipakai saat | Berkas |
| :--- | :--- | :--- | :--- |
| `#p-welcome` | **Sambutan** | member baru bergabung (mode kartu *statis* / *dinamis*) | `data/media/welcome_<id>.png` |
| `#p-goodbye` | **Perpisahan** | member keluar (otomatis bila gambarnya ada) | `data/media/goodbye_<id>.png` |
| `#p-boost` | **Boost** | member nge-boost server | `data/media/boost_<id>.png` |

> Contoh gambar siap pakai (1024×420) bisa dibuat sendiri dengan AI image generator —
> gaya gelap `#0D0D0F` dengan aksen ungu/emas paling menyatu dengan kartu bot.

- Unggah: **PNG/JPG/GIF/WEBP**, maksimal 8 MB, isi berkas diperiksa lewat *magic bytes*
  (file `.exe` yang di-rename tetap ditolak). Gambar ditimpa per jenis, jadi tidak menumpuk.
- Pratinjau tampil langsung di dashboard (`/api/kartu/<jenis>?token=…`, wajib token).
- Tombol **Hapus kartu** mengembalikan bot ke tampilan teks/embed biasa.
- Pemilih **Tampilan kartu sambutan** ada di halaman `/sambutan` (satu tempat dengan kartunya). Ukuran gambar ideal **1024×420 px**.

#### Bedanya “Kartu statis” dan “Kartu dinamis”

| Mode | Yang dikirim bot | Cocok untuk |
| :--- | :--- | :--- |
| 💬 **Teks saja** | pesan teks polos, tanpa gambar | server hemat kuota / tanpa gambar |
| 🖼️ **Kartu statis** | *embed*: gambar kartu yang kamu unggah dipakai apa adanya, plus **foto profil kecil** & teks sambutan | paling ringan — gambar dipakai ulang tanpa diolah |
| ✨ **Kartu dinamis** | bot **membuat gambar baru setiap kali** (Pillow): gambar kartu jadi latar, lalu ditimpa **foto profil bulat + nama member + “Member ke-N” + nama server** | server yang ingin tiap member dapat kartu bertuliskan namanya |

Ringkasnya: **statis = gambar buatanmu dikirim utuh**; **dinamis = gambar buatanmu dipakai
sebagai latar, lalu bot menambahkan nama & foto profil member**. Keduanya butuh gambar kartu
yang sudah diunggah — tanpa gambar, bot otomatis memakai mode teks.

#### Uji fitur tanpa menunggu event (tombol di halaman fiturnya)

Tidak ada halaman tes gabungan: tombol **Kirim tes** ada di halaman fiturnya masing-masing.

| Halaman | Fitur | Subjek | Yang terjadi |
| :--- | :--- | :--- | :--- |
| `/sambutan` | 👋 Sambutan member baru | pemilik server (bisa diganti) | kirim contoh sambutan + sapaan asing (`force=True`, dedup dilewati) |
| `/sambutan` | 👣 Pesan perpisahan | pemilik server (bisa diganti) | kirim contoh kartu perpisahan |
| `/sambutan` | 💎 Ucapan boost | pemilik server (bisa diganti) | kirim contoh ucapan boost |
| `/buat` | ⏰ Pengumuman terjadwal | daftar pengumuman tersimpan | kirim satu pengumuman **sekarang** (jadwal aslinya tidak digeser) |
| `/panel` | 🧩 Panel menu | daftar panel tersimpan | segarkan panel di Discord supaya tombol/dropdown terbaru tampil |
| `/konten` | 📰 Koran pagi (digest) | — | buat contoh rubrik pagi; **tidak dikirim** ke channel |
| `/tiket` | 🎫 Panel tiket | channel | pasang ulang panel **Buka Tiket** di channel itu |
| `/` | 🤖 Koneksi AI (Gemini) | — | satu panggilan AI kecil; membuktikan API key, kuota, & jaringan sehat |
| `/ekspor` | 📥 Ekspor CSV | — | bangun CSV level; melaporkan jumlah baris data |

**Subjek tes tidak perlu ID.** Kolom *contoh atas nama* sudah terisi **👑 Pemilik server
(otomatis)** — tekan Kirim tes saja. Bisa juga pilih member lain dari dropdown, atau tempel
`@nama` / `<@id>` di kolom opsional. Akun bot sendiri **tidak pernah** dipakai sebagai
contoh (pemicu sambutan/perpisahan memang mengabaikan member bot).

Tes yang memakai AI (sambutan, perpisahan, boost, koran pagi, koneksi AI) memakan
**1 panggilan AI**; tes sambutan/boost/pengumuman/panel tiket mengirim pesan **sungguhan**
ke channel. Hasilnya tampil sebagai kotak ✅/⚠️ di **halaman fiturnya** (atau JSON bila
dipanggil sebagai API). Kalau gagal, alasannya spesifik: `GEMINI_API_KEY` kosong, channel
tujuan sudah dihapus, bot tidak punya izin **Kirim Pesan**, atau AI tidak menjawab.
Fitur ber-channel yang belum aktif menampilkan tombol **Atur dulu** alih-alih tombol tes.

#### Beberapa channel untuk satu fitur

Setelan bertanda **channel** boleh diisi **lebih dari satu** — cukup centang di kotak
pilihan (tanpa JavaScript). Bot mengirim ke semua channel yang dicentang, dan satu channel
yang bermasalah tidak membatalkan pengiriman ke channel lain.

| Fitur | Bisa berapa channel |
| :--- | :--- |
| Channel sambutan · pesan pamit · ucapan boost | banyak |
| Channel pengumuman level (+ musim) | banyak |
| Log anti-spam · log anti-nuke · log tiket | banyak |
| Ucapan ulang tahun · backup otomatis | banyak |
| Auto-Chat AI · Galeri AI · Rangkum YouTube · Pencarian berita · Terjemahan otomatis | banyak (satu per channel) |
| **Koran pagi (digest)** · **Fakta harian** | **satu** (sengaja, sesuai permintaan) |
| Kategori tiket · kotak saran · gerbang verifikasi · starboard · log pertumbuhan | satu (satu kategori/pintu/papan, bukan siaran) |

Cara kerjanya: config menyimpan **daftar** (`channel_ids`, `log_channel_ids`, …) sekaligus
channel pertama di kunci lama (`channel_id`), jadi config lama di disk tetap terbaca tanpa
migrasi. Centang **🚫 Kosongkan** untuk mematikan fitur. Penjelasan teknis ada di modul
`channel_targets.py`.

#### Setelan yang bisa diubah dari web (56 fitur)

| Grup | Fitur |
| :--- | :--- |
| 🧭 **Inti, level, & ekonomi** (10) | Level & XP, pengumuman naik level, channel pengumuman level, **kartu rank PNG**, **warna aksen kartu rank**, ekonomi koin, koin harian, pelacakan pertumbuhan, channel log pertumbuhan, prefix custom |
| 👋 **Sambutan & pamit** (10 — semuanya di halaman `/sambutan`, per bagian `#p-welcome`/`#p-goodbye`/`#p-boost`) | channel sambutan, sambutan via DM, kartu sambutan (mati/statis/dinamis), persona sambutan, **bahasa sapaan sambutan**, **latin & arti sapaan**, channel pamit, **bahasa kata perpisahan**, **latin & arti perpisahan**, channel ucapan boost |
| 🛡️ **Keamanan** (10) | mode anti-spam, deteksi huruf kapital, log anti-spam, aksi anti-nuke (+log), pengaman raid (+aksi), channel & role verifikasi, proteksi anti-phishing |
| 🎫 **Tiket & sapaan harian** (8) | sistem tiket, role staf, kategori, log, maksimal tiket terbuka, ping staf, rating tiket, channel ucapan ulang tahun |
| 🧩 **Konten & interaksi** (17) | starboard (+ambang & **warna embed**), **papan sorotan varian** (kelola di panel Konten), kotak saran, Auto-Chat AI, koran pagi, galeri AI, rangkum YouTube, pencarian berita, terjemahan otomatis, statistik server, fakta harian, channel backup, gaya bahasa AI, keamanan konten AI, jam tenang, zona waktu |

Pilih nilai di dropdown → **Simpan**. Perubahan langsung tersimpan ke JSON bot (tanpa
restart), dan setiap perubahan dicatat di `data/dashboard_audit.json` (maksimal 300 entri).

#### Kirim embed & webhook

Form **Kirim pesan & embed** menerima: channel, judul, isi, warna, footer, gambar,
label+URL tombol, serta **identitas webhook** (nama & avatar). Kalau kolom identitas diisi,
pesan dikirim lewat webhook channel itu sehingga nama pengirim bisa berbeda dari bot —
praktis untuk "📢 Pengumuman Server". Isi boleh memakai variabel pesan
(`{server.name}`, `{now_long}`) yang diisi otomatis saat dikirim.

#### Pratinjau sebelum kirim (seperti Discohook)

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

#### Unggah banner & gambar

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

#### Kotak masuk tiket dari web

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

#### Formulir: kolom diisi lewat baris visual

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

#### Editor panel: tombol & dropdown tanpa Discord

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

#### Ekspor CSV dari browser

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

#### Keamanan bertingkat

| Lapis | Jaminan |
| :--- | :--- |
| **Token** | semua endpoint baca & tulis wajib token (`?token=`, `X-Dashboard-Token`, `Bearer`, atau field tersembunyi pada form HTML) |
| **Whitelist aksi** | 56 setelan di `dashboard_admin.FITUR` punya kunci yang terdaftar; aksi tak dikenal ditolak |
| **Tanpa PUT/DELETE/PATCH** | ada 14 jalur tulis `POST`, semuanya memeriksa token; data personal tetap memakai command Discord owner-only |
| **Tanpa hapus data massal** | tombol Hapus hanya membuang satu item (pesan lama di Discord tidak ikut terhapus) |
| **Jejak audit** | perubahan mencatat metadata, waktu, status, dan hasil; prompt bebas serta isi gambar tidak ditulis ke audit |
| **Bind privat** | default `DASHBOARD_HOST=0.0.0.0`, bisa diubah ke `127.0.0.1` + tunnel SSH |

#### Endpoint

| Endpoint | Isi |
| :--- | :--- |
| `GET /` | halaman HTML lengkap (butuh token) |
| `GET /api/status` · `/api/pemakaian` · `/api/level` · `/api/kontrol` · `/api/fitur` | data JSON |
| `GET /api/setelan` | semua nilai setelan + ringkasan grup + riwayat |
| `GET /api/tren?hari=7` | tren operasi AI & cache per hari (JSON) |
| `POST /api/aksi` | ubah setelan: `action=set.<kunci>` atau sakelar cepat lama (token boleh lewat body form) |
| `POST /api/ai` | `action=gambar` (multipart: `prompt`, `channel_id`, `style`, `ratio`, `acuan` opsional) / `action=prompt-server` (`prompt_server`, maks 500 huruf); prompt/gambar tidak masuk audit |
| `POST /api/bangun` | tema/pratinjau AI, Terapkan eksplisit, batalkan, riwayat, dan bongkar item builder tercatat |
| `POST /api/kirim` | kirim pesan/embed; field `channel, judul, isi, warna, footer, gambar, identitas, avatar`; tambahkan `pratinjau=1` untuk pratinjau tanpa kirim |
| `POST /api/konten` | `action=buat.pengumuman` / `buat.tautan` / `buat.panel` / `buat.formulir` / `buat.pemicu` / `jeda.pengumuman:<id>` / `hapus.<jenis>:<id>` / `banner.panel:<id>` / `hapusbanner.panel:<id>` |
| `POST /api/unggah` | `action=unggah.simpan` (multipart, field `banner`) / `hapus.banner:<nama>` |
| `POST /api/uji` | tes fitur; subjek opsional dan tanpa ID memakai pemilik server |
| `GET /api/unggahan/<nama>?guild=<id>` | pratinjau banner tersimpan (wajib token) |
| `GET /api/tiket?guild=<id>` | daftar tiket aktif + statistik (JSON) |
| `POST /api/tiket` | balas/tutup tiket, pasang/matikan panel, kelola topik & catatan staf |
| `GET /api/panel?guild=<id>` | daftar panel + tombol/dropdown-nya (JSON) |
| `POST /api/panel` | tambah/hapus tombol atau dropdown, pasang/matikan verifikasi |
| `POST /api/keamanan` | setel honeypot dan uji aturan anti-spam tanpa menindak member |
| `POST /api/moderasi` | setelan jalur laporan, status antrean, cari kasus, cabut temp-ban |
| `POST /api/lencana` | atur lencana dan hadiah role server |
| `GET /api/giveaway` · `POST /api/giveaway` | daftar, buat/hentikan/undi ulang, template & setelan bawaan |
| `GET /api/transkrip` · `POST /api/transkrip` | cari/unduh arsip HTML atau hapus satu transkrip tiket |
| `GET /api/ekspor?jenis=<level\|moderasi\|tiket\|pemakaian>` | unduh CSV analitik server (wajib token) |
| `GET /healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

#### Yang tetap lebih enak di Discord

Dashboard mengatur **setelan**, **konten**, **panel**, **tiket**, **verifikasi**,
**generator gambar**, prompt AI server, dan **ekspor analitik server**. Ekspor/penghapusan
data personal bukan API operator: `/dataku` dan `/hapusdataku` hanya dilakukan member
yang menjalankan command di Discord (ephemeral + konfirmasi pemilik). Yang masih butuh
percakapan interaktif di Discord:

| Kebutuhan | Command |
| :--- | :--- |
| Menyusun ulang teks panel (judul/deskripsi) setelah tombol ada | `/menu ubah` *(tombol & dropdown sudah bisa dari dashboard)* |
| Mengundi (giveaway) — ambil pemenang, reroll | `/giveaway mulai`, `/giveaway pilih` |
| Moderasi, musik, permainan, AI chat | perintah masing-masing (bukan setelan) |

> 💡 **Auto-refresh**: **aktif sendiri** setiap **30 detik** — tidak perlu menyetel apa pun.
> Mau diubah? Di header ada **satu dropdown** `🔄 Auto-refresh` + tombol **Set**:
>
> | Pilihan | Arti |
> | :--- | :--- |
> | `⏸ Mati` | tanpa `meta refresh` — aman mengisi form panjang dari HP |
> | `1 menit` · `10 menit` · `30 menit` · `1 jam` | interval tetap |
> | `✏️ Isi sendiri…` | memunculkan **kotak angka detik** (`0`–`3600`, mis. `45`) tepat di sebelah dropdown |
> | `Ikut .env` | kembali mengikuti `DASHBOARD_REFRESH_SEC` |
>
> Angka bebas tidak “menghilang”: memilih `✏️ Isi sendiri…` lalu **Set** akan menampilkan
> kotak angkanya; mengisi `45` di URL (`…&refresh=45`) atau cookie juga otomatis membuka
> mode itu dengan angka yang sudah terisi. Di luar batas dipotong ke 0–3600 (bukan error),
> isian bukan angka tidak mengubah apa pun, dan nilai 1–4 detik tetap dirender 5 detik oleh
> `meta refresh`. Semua pilihan disimpan di cookie **30 hari** untuk **semua halaman**,
> **tanpa restart** dan tanpa menyentuh `.env`.
>
> ⚠️ Token dashboard berlaku **satu bot penuh** (bukan per server). Rahasiakan, dan ganti
> bila pernah ikut terlihat di tangkapan layar/percakapan.

#### Menyalakan dashboard untuk instance sendiri (self-host)

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
| **Auto-refresh** | bawaan **30 detik**; atur sendiri lewat satu dropdown di header (`Mati`/`1m`/`10m`/`30m`/`1 jam`/`✏️ Isi sendiri…`/`Ikut .env`), atau `DASHBOARD_REFRESH_SEC=0` untuk mati permanen |

> 💡 Karena tiap instance punya token sendiri, kamu **tidak perlu** membagikan token ke siapa pun.
> Pemakai lain menjalankan bot mereka sendiri dan membuat token mereka sendiri lewat perintah di atas.

## K. Penerjemah Hemat Kuota (`/terjemah`)

Tiga tingkat pemakaian kuota, dari paling hemat:

| Mode | Kuota AI | Cara pakai |
| :--- | :--- | :--- |
| **Reaksi bendera** (disarankan, default) | hanya saat diminta | `/terjemah channel channel:#english-chat` → bot menempel 🇮🇩/🇬🇧 di pesan warga; terjemahan **baru dibuat ketika ada yang mengklik**, lalu dikirim lewat **DM** agar channel tidak banjir. |
| **Manual** | 1 panggilan / penggunaan | `/terjemah teks teks:... ke:id` atau `/terjemah pesan pesan_id:... ke:en` (tempel ID/tautan pesan). |
| **Auto-post** (opsional, **default mati**) | 1 panggilan / pesan | `/terjemah channel channel:#chat auto:True` — setiap pesan layak diterjemahkan otomatis (rate limit 3 detik/channel + batas kuota server). |

- **Cache 6 jam:** kalimat yang sama tidak diterjemahkan dua kali (maks 300 entri) → pesan berulang **0 kuota**.
- **Filter pintar:** hanya teks 8–600 karakter berisi kata; link/emoji-only/pesan terlalu panjang dilewati.
- **Batas kuota dihormati:** bila `AI_DAILY_CAP_PER_GUILD` tercapai, penerjemah berhenti sementara dan memberi pesan ramah.
- **Tercatat di `/pemakaian`** sebagai jenis operasi `Terjemah` (termasuk hitungan cache hit).
- Perintah pendukung: `/terjemah status` (channel terpilih, ukuran cache, sisa kuota server) dan `/terjemah channel aktif:False` untuk melepas channel.

## L. Hemat Kuota AI (`/pemakaian`, `/ringkas channel`, `/faq`)

> 💡 Free Tier Gemini punya batas harian. Tiga fitur ini membuat bot **tetap pintar tanpa boros kuota**:
> rekap yang **di-cache**, FAQ yang dijawab **tanpa AI**, dan laporan pemakaian agar Admin tahu siapa/apa yang paling banyak memakai.

### 1. Pantau Pemakaian (`/pemakaian`)

| Command | Fungsi |
| :--- | :--- |
| **`/pemakaian lihat`** | Operasi AI **hari ini**: total, rincian per jenis (`Chat`, `Cari`, `Rekap`, `Auto-Chat`, `Galeri`, `Transform`, `Fakta`), 5 member teraktif, & channel tersibuk. |
| **`/pemakaian tren hari:7`** | Tren harian: total operasi vs **cache hit** (yang menghemat kuota). |
| **`/pemakaian status`** | Ringkasan penghematan: jumlah cache hit, batas harian per member, TTL cache rekap, & jumlah entri FAQ lokal. |
| **`/pemakaian reset`** *(Admin)* | Bersihkan catatan pemakaian hari ini. |

**Yang dicatat:** hanya operasi yang **benar-benar memanggil Gemini**. `/faq tanya`, cache hit `/ringkas channel`,
dan seluruh perintah non-AI **tidak** dihitung sebagai pemakaian (justru tercatat sebagai `cache hit` → bukti penghematan).

### 2. Rekap Channel Ber-cache (`/ringkas channel`)

| Command | Fungsi |
| :--- | :--- |
| **`/ringkas channel periode:6 jam terakhir`** | Rekap obrolan channel/thread per rentang waktu (1 jam → 7 hari). |
| **`/ringkas channel periode:24 jam terakhir paksa:True`** | Abaikan cache & buat rekap **baru** (memakai 1 panggilan AI). |
| **`/ringkas channel ... publik:True`** | Tampilkan hasil rekap ke channel, bukan hanya ke peminta. |

**Cara kerja cache:**
1. Hasil rekap disimpan **`REKAP_CACHE_TTL_SEC`** (default **1800 detik / 30 menit**) per pasangan **channel + periode**.
2. Permintaan berulang untuk channel & periode yang sama dalam 30 menit → **0 kuota** (diambil dari cache, embed diberi label `♻️`).
3. Maksimal `REKAP_MAX_MESSAGES` (default **400**) pesan dianalisis agar token tetap hemat.

### 3. FAQ Server Lokal (`/faq`) — 0 Kuota

| Command | Fungsi |
| :--- | :--- |
| **`/faq tanya pertanyaan:cara verifikasi?`** | Jawaban dicari **lokal** (pencocokan kata kunci) dari basis FAQ server — **tanpa memanggil AI**. |
| **`/faq daftar`** | Semua entri FAQ/Info server + jumlah kuota yang dihemat. |
| **`/faq tambah topik:Cara verifikasi isi:Klik tombol ✅ di #verifikasi`** *(Admin)* | Tambah/perbarui entri FAQ. |
| **`/faq hapus target:2`** *(Admin)* | Hapus entri berdasarkan nomor urut (`/faq daftar`) atau nama topik. |

**Dua manfaat satu entri:** entri FAQ dipakai `/faq tanya` (0 kuota) **dan** otomatis ikut sebagai konteks resmi
saat AI menjawab di Auto-Chat (`/agent`), sehingga AI tidak menebak-nebak info server.

**Batas maksimal:** `MAX_SERVER_KNOWLEDGE_ENTRIES` (default **25 entri** per server) agar prompt tetap kecil & hemat token.

### 4. Batas Harian AI per Member (opsional)

- `AI_DAILY_CAP_PER_USER=0` → **tanpa batas** (bawaan).
- `AI_DAILY_CAP_PER_USER=20` → tiap member maksimal **20 operasi AI per hari** pada perintah AI berbasis slash
  (`/cari`, `/ringkas link`, `/ringkas chat`, `/ringkas channel`, cek fakta, terjemah, dll.); setelah itu bot
  menyarankan `/faq tanya` & cache rekap. Obrolan AI di ruang privat `/sesi` & Auto-Chat tetap berjalan
  (tetap tercatat di `/pemakaian`).
- **Admin server bebas** dari jeda antar-perintah **dan** batas harian ini (agar tetap bisa mengurus server);
  member & staf biasa tetap dibatasi.
- Data disimpan di `data/ai_usage.json` dan otomatis **dipangkas** menyisakan `AI_USAGE_KEEP_DAYS` (default **7 hari**).

### 5. Batas Harian AI per Server & Keamanan Konten (opsional)

- `AI_DAILY_CAP_PER_GUILD=0` → **tanpa batas** (bawaan). Isi misalnya `300` agar satu server tidak menghabiskan
  kuota gratis bersama; setelah batas tercapai, AI berhenti menjawab sementara **semua fitur non-AI tetap jalan**
  (FAQ lokal, musik, moderasi, giveaway, tiket, dll.).
- Saat pemakaian server melewati **80%**, bot mengirim peringatan **sekali per hari** ke channel log `/perawatan`
  (atau channel tempat bot dipanggil) — tanpa memakai kuota AI.
- **`/agent keamanan`** *(Admin)* mengatur `safetySettings` Gemini per server: `longgar` (bawaan, pengaturan Google),
  `normal` (blokir konten berisiko tinggi), `ketat` (blokir risiko sedang — cocok untuk server keluarga/remaja).
- Penghemat kuota yang berjalan **otomatis tanpa setting apa pun**:
  - **FAQ-first** — pertanyaan yang cocok dengan entri `/agent info` dijawab lokal oleh Auto-Chat (**0 kuota**).
  - **Cache jawaban** — pertanyaan identik di channel yang sama dalam `AI_REPLY_CACHE_TTL_SEC` (default 15 menit)
    dijawab dari cache (**0 kuota**), maksimal `AI_REPLY_CACHE_MAX` entri (RAM kecil).
  - **Router model hemat** — pertanyaan pendek tanpa media/link diarahkan ke model Flash-Lite.
  - **Token nyata** dari `usageMetadata` Gemini dicatat & tampil di `/pemakaian lihat` (bukan hanya jumlah operasi).
  - **Rotasi API key sehat** — key yang kena `429` diistirahatkan mengikuti header `Retry-After` (1–120 detik)
    dan key sehat dipakai lebih dulu; ada juga aturan anti-halusinasi di setiap system prompt.

### 6. Urutan Paling Hemat Kuota

1. **`/faq tanya`** → 0 kuota (info server, aturan, jam event, dsb).
2. **`/ringkas channel`** berulang → 0 kuota (cache 30 menit).
3. **`/cari`** & **`/ringkas link`** → 1 panggilan per permintaan.
4. **Obrolan AI** (`/sesi`, Auto-Chat) → paling mahal, pakai saat memang perlu kreativitas/penalaran.

---

## M. Tampilan Panel Components V2 (`/panel`, `/tampilan`)

Discord kini mendukung **Components V2** (`Container`, `Section`, `TextDisplay`, `Separator`,
`Thumbnail`, `Label`), jadi panel bot bisa tampil seperti dashboard web hosting: kartu berwarna
aksen, baris status, badge ON/OFF, dan navigasi tab — **tanpa kuota AI sama sekali**.

- **`/panel buka`** — **Control Center**. Satu pesan berisi kartu status + dropdown untuk berpindah tab:
  `🏠 Ringkasan`, `🤖 AI Agent`, `🛠️ Server`, `🧩 Komunitas`, `🎵 Musik`, `📊 Kuota & Level`.
  Tombol **🔄 Segarkan**, **🎨 Tampilan**, dan **🚪 Tutup** selalu tersedia.
- **`/tampilan atur`** *(Admin)* — editor branding server. Semua pilihan **langsung berefek**:
  - **warna aksen** (8 pilihan: ungu, biru, teal, hijau, oranye, merah, pink, abu-abu) → warna kartu V2,
    warna embed cadangan, dan emoji aksen di footer;
  - **gaya emoji** (standar/minimalis) → seluruh ikon panel;
  - **kepadatan** → *ringkas* menyembunyikan baris penjelas (`>`), *nyaman* menampilkan semuanya;
  - **thumbnail** → ikon server tampil sebagai `Section` + `Thumbnail` di kepala dashboard;
  - **gaya navigasi** → dropdown atau baris tombol tab;
  - **interval refresh panel musik** → 10 / 20 / 30 / 60 detik (watcher berdetak tiap 10 detik, jadi
    10 detik adalah resolusi paling segar dan menghemat rate limit Discord);
  - toggle **footer** dan **dialog konfirmasi** untuk aksi merusak.
- **`/tampilan pratinjau`** — lihat dashboard dengan tema yang sedang aktif sebelum disimpan rapi.
- **`/tampilan reset`** — kembalikan semua tampilan ke bawaan bot (memakai dialog konfirmasi).
- **`/pemakaian lihat`** — kini tampil sebagai kartu V2 dengan **progress bar** efisiensi cache.
- Tema disimpan **per server**; bila sebuah pilihan tidak diubah, bot memakai default
  (ungu • emoji standar • ringkas • thumbnail ikon • footer aktif • konfirmasi aktif • refresh 10 detik).

### Panel lain yang sudah memakai Components V2

| Command | Tampilan baru |
| :--- | :--- |
| `/status` | Kartu diagnostik: latensi, RAM, uptime, status AI/komunitas/musik + tombol **Muat Ulang** & **Control Center**. |
| `/agent panel` | Dua kartu: ringkasan channel target + **8 tombol toggle berwarna** (🟢 hijau = aktif, 🔴 merah = mati), dropdown channel, serta tombol Persona / Tambah FAQ / Kelola FAQ / Segarkan / Tutup. |
| `/tiket panel` | Panel "Pusat Bantuan" bergaya kartu dengan tombol **🎟️ Buat Tiket** (tetap menempel setelah bot restart). |
| `/musik antrean` | Antrean berhalaman sebagai kartu: judul, total durasi, tombol **◀ Sebelumnya / Berikutnya ▶ / Tutup**. |
| `/musik panel` & panel pemutar otomatis | Panel Rythm versi kartu: progress bar, volume, filter, autoplay, plus **9 tombol kontrol** dalam 2 baris (⏮ ⏯ ⏭ ⏹ 🔁 / 🔀 🔉 🔊 📜). |
| `/musik sekarang` | Kartu Now Playing bertema (progres, sumber, antrean, diminta oleh). |
| `/bantuan` | Pusat panduan sebagai kartu + **dropdown 11 kategori** yang langsung berganti halaman. Halaman depan kini memuat panel **🆕 Terbaru (v1.28 → v1.39)** berisi ringkasan fitur terbaru (`/raid`, `/nuke`, `/backup pulihkan`, `/level musim`, `/musik playlist`, `/tiket rating`, `/bahasa`, `/prefix`, `/analitik`, `/perawatan memori`) dan jumlah menu utama dihitung dari command yang benar-benar terdaftar. |
| `/agent status` | Ringkasan seluruh channel AI Agent sebagai kartu bertema. |
| `/giveaway daftar` | Daftar giveaway aktif & riwayat sebagai kartu. |
| `/pemakaian reset`, `/musik hentikan`, `/tampilan reset` | Dialog **konfirmasi bergaya kartu** sebelum aksi merusak (bisa dimatikan Admin lewat `/tampilan atur`). |

> **Soal ikon 🔊 di channel statistik:** ikon pengeras suara itu **ikon bawaan Discord untuk Voice
> Channel** — tidak bisa diganti lewat nama atau emoji. Ikon mengikuti **tipe channel**, jadi cara
> satu-satunya menggantinya adalah memilih tipe lain lewat **`/serverstats tipe`**:
>
> | Tipe | Ikon | Catatan |
> | :--- | :--- | :--- |
> | `voice` (bawaan) | 🔊 | paling lazim dipakai bot statistik |
> | `text` | #️⃣ | warga bisa melihat angka, **tidak bisa mengirim pesan** |
> | `announcement` | 📢 | mundur ke `text` bila server menolak channel pengumuman |
> | `stage` | 🎤 | mundur ke `voice` bila stage channel tidak diizinkan |
>
> Emoji di dalam **nama** channel (mis. `👥 Total Member: 12`) dan nama kategori tetap bisa diatur
> lewat `/serverstats ikon`.

### Batas Keras Discord yang Tidak Bisa Dilanggar

| Batas | Nilai |
| :--- | :--- |
| Baris tombol per pesan | maks 5 baris, 5 tombol per baris |
| Total komponen per pesan | ~40 komponen |
| Opsi pada dropdown | maks 25 opsi |
| Warna kartu | hanya pilihan aksen bawaan Discord (tidak bisa hex bebas) |
| Teks satu blok | maks 4000 karakter |

Tidak ada CSS, font kustom, animasi, atau gambar di dalam tombol — itu memang tidak didukung Discord.

### Kalau Server/Klien Tidak Mendukung V2

Bot otomatis **mundur ke embed klasik** (warna aksen tetap dipakai). Jadi tidak ada command yang
gagal hanya karena tampilan V2 ditolak klien. Data tema disimpan di **`data/ui_theme.json`** per server.

---

## N. Audit Log Server (`/log`)

Mencatat aktivitas penting server ke **satu channel** — bukti saat moderasi, tanpa AI.

| Command *(Admin)* | Fungsi |
| :--- | :--- |
| **`/log channel channel:#bot-log`** | Pasang channel log & aktifkan audit log |
| **`/log status`** | Lihat channel, kategori aktif, & daftar channel dikecualikan |
| **`/log kategori nama:voice aktif:True`** | Nyalakan/matikan satu kategori |
| **`/log abaikan channel:#bot-spam`** | Kecualikan channel ramai dari pencatatan |
| **`/log matikan`** | Hentikan audit log server |

| Kategori | Isi | Default |
| :--- | :--- | :--- |
| `pesan` | pesan dihapus, diedit (sebelum → sesudah), hapus massal | ✅ aktif |
| `member` | member join (dengan umur akun), keluar, ganti nama panggilan | ✅ aktif |
| `role` | role member diberikan/dicabut, role dibuat/dihapus | ✅ aktif |
| `channel` | channel dibuat/dihapus | ✅ aktif |
| `voice` | masuk/keluar/pindah voice channel | ⛔ mati (paling ramai) |

- **Tanpa AI & tanpa simpan isi log ke disk** — hanya konfigurasi di `data/audit.json`.
- Isi pesan dipotong otomatis agar tetap di bawah batas embed Discord.
- Konfigurasi channel yang sudah dihapus dibersihkan otomatis.

## O. Ekonomi Koin (`/ekonomi`)

Gamifikasi ringan supaya member betah — **0 kuota AI**, semua hitungan lokal.

| Command | Fungsi |
| :--- | :--- |
| **`/ekonomi saldo [member]`** | Saldo koin, peringkat, & status hadiah harian |
| **`/ekonomi harian`** | Klaim hadiah harian (bonus **streak** sampai +70%) |
| **`/ekonomi papan`** | Papan peringkat member paling kaya + total koin beredar |
| **`/ekonomi toko`** | Daftar item yang bisa dibeli |
| **`/ekonomi beli item:<nama>`** | Beli item → role otomatis diberikan |
| **`/ekonomi transfer member:@X jumlah:50`** | Kirim koin (minimal 10, ada jeda anti-spam) |
| **`/ekonomi atur`** *(Admin)* | Aktifkan & atur koin/pesan, jeda, koin/voice, hadiah harian, nama mata uang |
| **`/ekonomi tambah-item` / `hapus-item`** *(Admin)* | Kelola toko (maks 20 item: nama, harga, role, deskripsi) |

- **Default NONAKTIF** (`/ekonomi atur aktif:True`) agar server yang tidak butuh tidak terbebani.
- Koin otomatis didapat dari pesan (dengan jeda) & menit di voice channel — memakai pelacakan voice yang sama dengan XP Voice.
- Data di `data/economy.json`, maksimal **500 saldo teratas per server** agar file tetap kecil.

## P. Pertumbuhan Server & Invite Tracker (`/tumbuh`)

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

## Q. Menu Builder & Self Roles v2 (`/menu`)

Bikin panel sendiri — mirip *Self Roles* milik bot Discohook, tapi isinya tidak harus role:
satu panel bisa memuat **tombol role, tombol link, dan tombol command** sekaligus. 0 kuota AI.

| Command | Fungsi |
| :--- | :--- |
| **`/menu buat judul:… [deskripsi] [banner] [banner_url] [channel]`** *(Admin)* | Membuat panel + mengirimnya ke channel |
| **`/menu tombol-role menu:… role:@Gamer [label] [emoji] [gaya]`** | Tombol role: klik = dapat, klik lagi = lepas |
| **`/menu tombol-link menu:… label:Support url:https://…`** | Tombol tautan (buka URL, tanpa aksi bot) |
| **`/menu tombol-command menu:… aksi:serverstats [visibilitas]`** | Tombol yang menjalankan command info |
| **`/menu dropdown-role menu:… role1:@A role2:@B [eksklusif]`** | Dropdown role (maks 25 role, bisa eksklusif) |
| **`/menu alur menu:… label:… aksi:…`** | Tombol yang menjalankan **alur aksi** berurutan (lihat di bawah) |
| **`/menu alur-bantuan`** | Panduan singkat menulis alur |
| **`/menu form buat nama:… kolom:… tujuan:#x`** | **Formulir (modal)** buatan sendiri: kolom bebas (lihat di bawah) |
| **`/menu form tombol form:… menu:… [label]`** | Pasang formulir sebagai tombol di panel |
| **`/menu form daftar`** / **`/menu form uji form:…`** | Lihat semua formulir / coba isi tanpa mengirim hasil |
| **`/menu hapus-item menu:… item:2`** *(Admin)* | Hapus tombol/opsi (nomor urut, ID, atau label) |
| **`/menu ubah menu:… judul:… deskripsi:…`** *(Admin)* | Ubah teks panel; pesan yang sudah terkirim ikut berubah |
| **`/menu ekspor menu:…`** *(Admin)* | Unduh panel sebagai JSON (backup / pindah server) |
| **`/menu impor berkas:…`** *(Admin)* | Buat panel baru dari JSON hasil ekspor |
| **`/menu kirim menu:… [channel]`** *(Admin)* | Kirim ulang panel ke channel lain |
| **`/menu daftar`** | Lihat semua panel beserta isinya |
| **`/menu hapus menu:…`** *(Admin)* | Hapus panel dari daftar bot |

### Alur aksi tombol (`/menu alur`)
Satu tombol bisa menjalankan **beberapa aksi berurutan** — ide yang dipinjam dari *flows* Discohook.
Langkah dipisah `>` dan teksnya boleh memakai variabel (`{member.mention}`, `{server.name}`):

```text
/menu alur menu:1 label:Buka Tiket aksi:+role:123456 > pesan:Halo {member.mention}, tiketmu siap! > thread:tiket-{member.name}
```

| Langkah | Arti |
| :--- | :--- |
| `role:<id>` | Toggle role (dapat bila belum punya, lepas bila sudah) |
| `+role:<id>` / `-role:<id>` | Tambah / lepas role |
| `syarat:<id>` | Berhenti diam-diam bila member **tidak** punya role itu |
| `pesan:<teks>` | Balasan pribadi (*ephemeral*) |
| `umum:<teks>` | Balasan yang terlihat semua orang |
| `thread:<nama>` | Buat thread publik di channel panel |
| `tunggu:<detik>` | Jeda (maks 15 detik) |
| `stop[:<teks>]` | Hentikan alur, opsional kirim alasan |
| `webhook:<nama>\|<teks>` | Kirim pesan sebagai **nama sendiri** lewat webhook (butuh *Manage Webhooks*) |
| `hapus` | Hapus balasan bot yang sudah dikirim alur ini (pasangan `umum:… > tunggu:5 > hapus`) |

Batas: **10 langkah** per tombol, 1000 karakter per pesan. Role tetap wajib di bawah role bot.

### Pemicu saat member bergabung (`/menu pemicu`)
Alur yang sama bisa dijalankan **tanpa klik tombol** — dipicu ketika ada member baru masuk:

```text
/menu pemicu tambah aksi:"+role:123456 > umum:Selamat datang {member.mention}!" channel:#umum umur_akun:7
```

- Pilih `channel` untuk pesan/thread sambutan; `umur_akun` menolak akun yang terlalu baru
  (bawaan 0 = semua akun) — pengaman saat server kena raid.
- Langkah yang butuh interaksi (`pesan`, `hapus`) dilewati karena tidak ada yang mengklik apa pun;
  `role`, `syarat`, `umum`, `webhook`, `thread`, `tunggu`, `stop` tetap berlaku.
- Satu alur gabung per server; `/menu pemicu daftar` melihatnya, `/menu pemicu hapus` mematikannya.
  Data disimpan di `data/flow_triggers.json`.

### Formulir (modal) buatan sendiri — `/menu form`
`/agent panel` punya modal dengan kolom tetap. Lewat `/menu form`, **Admin merancang sendiri**
isinya: sebut kolom yang diinginkan, pasang sebagai tombol, dan jawaban anggota dikirim rapi ke
channel pilihan — cocok untuk lamaran staff, laporan bug, atau pendaftaran event.

```text
/menu form buat nama:"Lamaran Staff" kolom:"Nama | Umur | Alasan:panjang?" tujuan:#lamaran
/menu form tombol form:"Lamaran Staff" menu:Pusat menu label:"📝 Daftar Staff"
```

| Tulis di `kolom` | Artinya |
| :--- | :--- |
| `Nama` | Kolom pendek, wajib diisi |
| `Nama?` | Kolom pendek, boleh kosong |
| `Alasan:panjang` | Kolom paragraf (bisa beberapa baris) |
| `Catatan:panjang?` | Paragraf, boleh kosong (urutan penanda bebas) |

- Kolom dipisah `|`; **maksimal 5** kolom — atau **4** bila memakai `penjelasan` (kalimat pengantar
  di dalam modal memakan satu slot).
- `hasil` mengatur bentuk pesan yang masuk ke channel, mis.
  `hasil:"**Nama:** {form.nama}
**Umur:** {form.umur}
**Alasan:** {form.alasan}"`.
  Kosongkan untuk daftar otomatis (`**Kolom**` lalu jawabannya).
- `{form.<kolom>}` diisi jawaban anggota; variabel biasa (`{member.mention}`, `{server.name}`,
  `{now_relative}`) tetap jalan.
- **Tanpa mention:** hasil dikirim dengan *mention* dimatikan, jadi jawaban anggota tidak bisa
  dipakai men-*ping* `@everyone`.
- Jawaban **tidak disimpan** bot — hanya diteruskan ke channel tujuan; yang dicatat cuma jumlahnya.
- `/menu form uji` menampilkan pratinjau hasil tanpa mengirim ke channel. Satu formulir per
  server dibatasi **20**, dan `/menu form hapus` ikut membersihkan tombolnya di panel.
- Berkas data: `data/forms.json`. Tombol formulir **tidak ikut** `/menu ekspor` (formulirnya
  terpisah) — pesan ekspor akan menyebutkan tombol mana yang dilewati.

### Variabel pesan
Judul/isi `/embed`, `/pengumuman`, `/menu`, dan teks alur bisa memakai variabel yang diisi saat
pesan dikirim: `{member.name}`, `{member.display_name}`, `{member.mention}`, `{member.created_relative}`,
`{server.name}`, `{server.members}`, `{server.boosts}`, `{channel.mention}`, `{now_relative}`, dll.
Daftar lengkap: `/embed variabel`. Variabel yang tidak dikenal dibiarkan apa adanya agar salah
ketik terlihat; variabel yang datanya tidak ada (mis. `{member.name}` di pengumuman terjadwal)
diganti kosong.

### Backup panel
`/menu ekspor` menghasilkan berkas JSON (`ai-discord-chat/panel` v1) berisi judul, deskripsi,
banner, tombol (role/link/command/alur), dan dropdown — tanpa ID guild/channel/pesan.
`/menu impor` memulihkannya sebagai panel baru di server mana pun; ID role tetap milik server
asal, jadi di server lain role perlu dibuat ulang sebelum tombolnya dipakai.

**Tautan bagikan (tanpa berkas).** `/menu bagikan` membuat kode ringkas dari panel itu dan
sebuah URL pratinjau `https://<situs>/p/<kode>` (halaman situs, lengkap dengan tag `og:` jadi
tampil rapi saat ditempel di Discord). Siapa pun bisa memasangnya dengan
`/menu impor kode:<tautan atau kode>` — menerima URL penuh, `ai-discord-chat/panel:<kode>`,
maupun kodenya saja. Tidak ada database: isi panel ikut di dalam kode.
Kode diringkas dengan **zlib + base64** (awalan `z.`), jadi panel berisi 20 tombol pun
masih muat (±430 karakter). Kode lama tanpa awalan tetap bisa diimpor. Batas kerasnya
1.500 karakter — panel yang lebih besar ditolak dengan saran memakai `/menu ekspor`.

### Tombol yang bisa menjalankan command
Klik tombol = bot menjalankan **command yang sama** atas nama **member yang mengklik**, jadi semua
cek izin tetap berlaku. Contoh isi panel "Pusat Info":

| Tombol | Menjalankan |
| :--- | :--- |
| 📊 Statistik | `/serverstats lihat` |
| 📈 Level Saya | `/level lihat` |
| 🌱 Pertumbuhan | `/tumbuh ringkas` |
| 💰 Saldo Koin | `/ekonomi saldo` |
| 🎟️ Daftar Tiket | `/tiket daftar` |
| 📋 Audit Log | `/log status` |
| 🔋 Pemakaian AI | `/pemakaian lihat` |
| 📖 Bantuan | `/bantuan` |

- **Visibilitas per tombol:** `auto` (ikut command), `ephemeral` (hanya yang klik), atau `publik`.
- **Whitelist** — hanya command informasi. `ban`, `purge`, `lockdown`, `backup`, `/mod`,
  `/ekonomi atur`, dll. **tidak bisa** dipasang sebagai tombol.

### Self Roles v2 lewat `/panel-role`
`/panel-role pasang` sekarang punya parameter **`gaya`**:

| Gaya | Tampilan |
| :--- | :--- |
| `reaksi` (bawaan) | Cara lama: klik emoji di bawah embed |
| `tombol` | Baris tombol role (maks 20) |
| `dropdown` | Satu menu pilihan role (maks 25) |
| `campuran` | **Banner + tombol + dropdown** — persis gaya Self Roles Discohook |

Tambah **`banner`** (unggah `.png/.jpg`) atau **`banner_url`** untuk gambar besar di atas panel.

**Target kirim:** panel bisa dikirim ke **channel teks**, **thread**, atau **forum channel**
(untuk forum, panel menjadi post baru dengan judul panel sebagai nama post).

### Batas & pengaman
| Hal | Nilai |
| :--- | :--- |
| Tombol per panel | 20 (5 tombol per baris) |
| Dropdown per panel | 2, maksimal 25 opsi masing-masing |
| Panel per server | 20 |
| Banner | PNG/JPG/WebP, maks 8 MB |
| Jeda klik role | 3 detik per member (anti spam-klik) |
| Role hadiah | wajib **di bawah** role bot & bot punya izin **Manage Roles** |
| Data | `data/menus.json` (panel persisten; tombol tetap hidup setelah restart) |
| Audit | setiap perubahan role tercatat di `/log` bila audit log aktif |

---

## R. Anti-Nuke (`/nuke`)

Melindungi server dari **penghancuran massal oleh staff jahat atau akun yang di-hack**.
Bot membaca **Audit Log** Discord (siapa melakukan apa), menghitung aksi berisiko per pelaku,
lalu bertindak sesuai pengaturan Admin. **0 kuota AI.**

| Command | Fungsi |
| :--- | :--- |
| **`/nuke status`** | Status, aksi aktif, ambang tiap jenis, izin bot, whitelist, & pelanggaran terakhir |
| **`/nuke atur`** *(Admin)* | Aktifkan, channel log, aksi, durasi timeout, DM owner, pemulihan, ambang & jendela waktu |
| **`/nuke whitelist`** *(Admin)* | Lihat / tambah / hapus member & role yang dikecualikan |
| **`/nuke uji`** *(Admin)* | Uji kering: lihat ambang & tindakan yang akan dijalankan (tidak menindak) |
| **`/nuke pulihkan`** *(Admin)* | Pulihkan nama & ikon server dari titik pulih terakhir |
| **`/nuke beku durasi_menit:30`** *(Admin)* | **Mode beku**: setiap aksi destruktif langsung ditindak (ambang = 1) selama N menit |
| **`/nuke cairkan`** *(Admin)* | Akhiri mode beku lebih awal |
| **`/nuke matikan`** *(Admin)* | Hentikan pemantauan |

### Yang dipantau (ambang bisa diubah Admin)
| Aksi | Ambang bawaan | Kenapa berbahaya |
| :--- | :--- | :--- |
| 🧨 Hapus channel | 3× / 60 dtk | Riwayat chat hilang permanen |
| 🎭 Hapus role | 3× / 60 dtk | Struktur izin hancur |
| 🔨 Ban massal | 5× / 60 dtk | Server dikosongkan |
| 👢 Kick massal | 5× / 60 dtk | Sama, tanpa jejak ban |
| 🌊 Buat channel massal | 8× / 60 dtk | Server dibanjiri channel sampah |
| 🪝 Buat webhook | 3× / 5 mnt | Saluran spam yang tetap hidup walau bot keluar |
| 🏷️ Ubah identitas server | 2× / 5 mnt | Pembajakan nama/ikon |
| 🧯 Cabut role massal | 12× / 60 dtk | Member kehilangan akses beramai-ramai |
| 🤖 **Bot asing ditambahkan** | **1×** | Bot jahat bisa jadi Administrator & menghancurkan server |
| 🎨 Buat role massal | 4× / 60 dtk | Role admin palsu / izin kacau |

### Perlindungan bot jahat & mode beku (v1.35.0-beta, 0 kuota AI)
- **Bot asing langsung dikeluarkan.** Saat ada yang menambahkan bot lewat OAuth, bot ini menangkap
  `bot_add` di Audit Log dan **menendang bot itu** seketika (bisa dimatikan: `/nuke atur keluarkan_bot:False`).
  Tambahan bot juga dicatat sebagai pelanggaran pelaku, jadi aksi berikutnya ikut ditindak.
- **Mode beku (`/nuke beku`)** dipakai saat server sedang diserang: **ambang menjadi 1 aksi** untuk semua
  jenis (hapus channel, ban massal, webhook, dll.), berlaku 1–1440 menit, dan otomatis cair saat waktunya
  habis (watcher memeriksa tiap 1 jam) atau lewat `/nuke cairkan`.
- Kalau aksi server masih `lapor`, mode beku tetap **melapor instan** tetapi tidak menindak — ubah dulu ke
  `cabut-role`/`timeout`/`kick`/`ban` lewat `/nuke atur aksi:` atau `/nuke beku paksa_aksi:`.
- **Peran bot yang disarankan:** beri bot **View Audit Log + Manage Roles + Kick Members + Manage Channels**
  (jangan Administrator). Dengan cara itu bot bisa menindak tanpa menjadi sasaran serangan balik.

### Aksi bertingkat (pilih di `/nuke atur aksi:`)
| Mode | Efek |
| :--- | :--- |
| `lapor` *(bawaan)* | Hanya laporan ke channel log + DM owner — **tanpa tindakan otomatis** |
| `cabut-role` | Laporan + cabut semua role berbahaya pelaku (administrator, manage server, ban, dll.) |
| `timeout` | Laporan + timeout sementara (durasi diatur, maks 28 hari) |
| `kick` | Laporan + keluarkan pelaku |
| `ban` | Laporan + ban pelaku |

### Pemulihan ringan (opsional, aktif bawaan)
- **Nama & ikon server** dikembalikan dari titik pulih yang disimpan saat bot start / saat Admin menyimpan pengaturan.
- **Webhook buatan pelaku** dihapus otomatis.
- Bisa dipulihkan manual kapan saja: `/nuke pulihkan`.

### Pengaman
| Hal | Perilaku |
| :--- | :--- |
| Owner server | **Tidak pernah** ditindak (batasan Discord) |
| Bot ini sendiri | Selalu dikecualikan |
| Whitelist | Member/role terpercaya tidak pernah ditindak (`/nuke whitelist`) |
| Izin bot | Butuh **View Audit Log**; tanpa itu `/nuke status` memberi peringatan jelas |
| Salah tembak | Hanya pelaku (dari audit log) yang dihitung, bukan seluruh staff |
| Pembatasan | Bot tidak bisa mengembalikan **isi pesan** yang sudah dihapus — hanya struktur & identitas |
| Data | `data/antinuke.json` (konfigurasi + 20 pelanggaran terakhir) |

> **Rekomendasi:** biarkan mode `lapor` selama 1–2 minggu untuk melihat apakah ada false positive
> (mis. staff yang memang sedang merapikan channel), baru naikkan ke `cabut-role` atau `timeout`.

---

## S. Raid Guard (`/raid`)

Melengkapi anti-raid yang hanya **melapor**: bila server diserbu akun palsu, bot menyalakan
**mode darurat otomatis** selama beberapa menit lalu mengembalikan keadaan semula. **0 kuota AI.**

| Aksi | Efek saat mode raid aktif |
| :--- | :--- |
| `lapor` | Laporan ke channel log saja — tanpa mengubah server. |
| `verifikasi` *(bawaan)* | **Auto Role ditahan** + member baru diminta verifikasi (DM & sebutan di channel verifikasi). |
| `verifikasi+lockdown` | Semua di atas **+ lockdown** text channel sampai mode berakhir. |

| Command | Fungsi |
| :--- | :--- |
| **`/raid atur`** *(Admin)* | Aktifkan deteksi, ambang join, jendela waktu, aksi, durasi, channel log & verifikasi. |
| **`/raid status`** | Mode aktif?, sisa waktu, ambang, aksi, & channel yang dipakai. |
| **`/raid mulai`** *(Admin)* | Nyalakan mode darurat sekarang (tanpa menunggu ambang). |
| **`/raid akhiri`** *(Admin)* | Akhiri lebih awal & buka kembali lockdown. |

**Pengaman:** default **nonaktif**, hanya **Admin/Manage Server** yang bisa mengubah, laporan
maksimal **sekali per 5 menit** (anti-spam), semua tindakan **reversible** (lockdown dibuka &
Auto Role normal saat mode berakhir), dan setiap kejadian tercatat di **Audit Log**.

## T. Bahasa Antarmuka (`/bahasa`)

Bot berbicara **Bahasa Indonesia** secara bawaan, tapi teks **kerangka** bisa diganti ke English
per server. Semua terjemahan lokal — tidak memanggil AI sama sekali.

| Command | Fungsi |
| :--- | :--- |
| **`/bahasa lihat`** | Bahasa aktif, pilihan yang tersedia, & contoh teks yang ikut berubah. |
| **`/bahasa atur kode:id\|en`** *(Admin)* | Ganti bahasa server (per server, bukan per member). |

**Yang diterjemahkan (inti):** tombol & kartu **dialog konfirmasi** (`Ya, lanjutkan` / `Batal`,
`Dikonfirmasi` / `Dibatalkan`), kata **status umum** (`aktif` / `nonaktif`, `tersimpan`),
**pesan izin** (`Butuh izin Admin`), dan command `/bahasa` itu sendiri.

**Yang tetap Bahasa Indonesia:** seluruh penjelasan panjang fitur (`/bantuan`, README, pesan
panduan). Alasannya sederhana: menjaga konsistensi dokumentasi & menghemat RAM/berkas.
Bahasa disimpan di `data/i18n.json` (bahasa default tidak ditulis agar berkas tetap kecil).

## U. Prefix Command per Server (`/prefix`)

Slash command (`/...`) tidak butuh prefix, tetapi bot juga punya command teks lama
(`!setup_panel`). Setiap server boleh mengganti prefix itu:

| Command | Fungsi |
| :--- | :--- |
| **`/prefix lihat`** | Prefix khusus server + daftar prefix yang diterima. |
| **`/prefix atur prefix:?`** *(Admin)* | Ganti prefix (1–5 karakter). |
| **`/prefix reset`** *(Admin)* | Kembalikan ke prefix bawaan `!`. |

**Aturan:** prefix tidak boleh berspasi, tidak boleh memakai karakter `<> & @ # : ` / \ * _ ~ |`,
dan **prefix bawaan `!` tetap diterima** sebagai cadangan agar member lama tidak bingung.
Hanya server yang diubah yang disimpan di `data/prefixes.json` (hemat I/O & RAM).
Command AI di channel tetap tidak terpengaruh: prefix hanya untuk command teks, bukan obrolan.

## V. Ekspor Analitik CSV & Webhook (`/analitik`)

Data yang bot sudah punya bisa **diunduh** atau **dikirim otomatis** ke webhook Discord
(bukan langganan analytics pihak ketiga) — berguna untuk laporan bulanan atau arsip staf.

| Command | Fungsi |
| :--- | :--- |
| **`/analitik ekspor jenis:level`** *(Admin)* | Unduh CSV (lampiran file) — `level`, `moderasi`, `tiket`, `pemakaian`. |
| **`/analitik webhook url:https://discord.com/api/webhooks/... [jadwal:harian]`** *(Admin)* | Kirim CSV otomatis ke webhook (uji kirim langsung dijalankan). |
| **`/analitik status`** | Status, jadwal, jumlah baris tiap jenis, & kapan terakhir dikirim. |
| **`/analitik matikan`** *(Admin)* | Hentikan ekspor otomatis & hapus URL webhook dari penyimpanan. |

**Isi tiap CSV**
| Jenis | Kolom |
| :--- | :--- |
| `level` | `user_id, level, xp, messages, voice_xp, prestige, last_activity` |
| `moderasi` | `case_id, user_id, moderator_id, action, reason, duration_sec, created_at` |
| `tiket` | `ticket_number, user_id, status, topic, claimed_by, created_at, first_response_at, first_response_minutes, duration_minutes, rating, closed_reason` |
| `pemakaian` | `day, total_calls, cache_hits, chat, ringkas, gambar, cari` |

**Detail teknis:** CSV dibuat di memori (maks **2000 baris** per berkas), dikirim sebagai
lampiran multipart dengan **BOM UTF-8** agar rapi di Excel; pengiriman otomatis memakai
`aiohttp` yang sudah dipakai bot (tanpa dependency baru). URL webhook hanya disimpan lokal di
`data/analytics.json` dan **disamarkan** di Discord. Jadwal diperiksa tiap 5 menit di watcher
yang sudah ada; default **nonaktif** sampai Admin mengaturnya.

## W. Audit RAM & Cache (`/perawatan memori`)

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

### 🏗️ `/bangun` — 15 tema siap pakai + perancang AI

Terinspirasi **Instabot** (server langsung jadi dari tema) dan **purpleGPT** `/genserver`
(jelaskan server impian, AI menyusun strukturnya). **Tidak ada yang dibuat sebelum Admin
menekan tombol Terapkan.**

| Command | Fungsi |
| :--- | :--- |
| `/bangun tema tema:gaming` | Pratinjau struktur dari salah satu **15 tema** (gaming, komunitas, aesthetic, study, musik, seni, teknologi, crypto, anime, roleplay, bisnis, coding, kesehatan, keluarga, startup) — **0 kuota AI**. |
| `/bangun rancang deskripsi:…` | **AI (Gemini)** menyusun kategori, channel, & role dari deskripsi bebas → pratinjau. Bila AI gagal/ngawur, otomatis memakai tema terdekat. |
| `/bangun terapkan` | Terapkan rencana terakhir yang masih menunggu konfirmasi. |
| `/bangun riwayat` | Build terbaru dan jumlah build sebelumnya yang masih bisa di-rollback. |
| `/bangun bongkar` | Bongkar build terbaru saja; bisa diulang untuk build sebelumnya. |

Dashboard juga menyediakan halaman **`/bangun`** dan endpoint bertoken `POST /api/bangun`: pilih tema atau kirim deskripsi AI, baca pratinjau, lalu tekan **Terapkan**. Tombol **Bongkar** meminta checkbox konfirmasi dan rollback dilakukan berurutan dari build terbaru. Pemilihan tema tidak memakai AI; rencana AI tidak membuat struktur sebelum penerapan eksplisit.

Pengaman:

- Rencana divalidasi dulu: maks **8 kategori / 40 channel / 12 role**, nama ≤100 huruf, tipe
  channel harus salah satu yang didukung Discord. Kategori channel diambil dari nama pada template
  `/bangun` atau `category_id` pada backup; bila kategori yang diminta gagal dibuat, channel itu
  dilewati, bukan dibuat tanpa kategori.
- Eksekusi memakai mesin `backup_restore` yang sudah teruji: urutan **role → kategori → channel**,
  jeda anti rate-limit, **hanya menambah**, dan kegagalan satu item tidak menghentikan sisanya.
- AI tidak pernah menyentuh API Discord: ia hanya menghasilkan **JSON rencana**; kode bot yang
  membuat channel setelah konfirmasi.
- Stack riwayat per server tersimpan di `data/server_builder.json`. Tiap entri mencatat ID objek
  Discord yang benar-benar berhasil dibuat, sehingga rollback berulang hanya menghapus build yang
  dipilih dan tetap tersedia setelah bot restart. Jika sebagian penghapusan gagal, sisanya tetap
  tercatat untuk dicoba lagi; format riwayat lama yang hanya berisi nama tetap dimigrasikan.

### 🖼️ `/meme` — meme lokal, 0 kuota AI, tanpa aset gambar

### 🎨 `/gambar` — buat & edit gambar dari slash command

Dari purpleGPT (`/draw` & `/edit`). `/gambar buat prompt:… rasio:… gaya:…` membuat gambar baru
(**5 rasio aspek**, belasan gaya), `/gambar edit prompt:…` mengubah lampiran gambar **atau
otomatis memakai gambar terakhir** di channel itu (tanpa unggah ulang), dan `/gambar pilihan`
menampilkan semua rasio & gaya. Kuota AI tetap dihitung seperti chat, dengan jeda 20 detik per
pengguna agar tidak membanjiri API. Gaya/rasio per panggilan **tidak mengubah setelan channel**.

### 📦 `/dataku` & `/hapusdataku` — privasi mandiri

Dari janji purpleGPT *"export or delete your data anytime"*. `/dataku` mengirim lampiran **JSON**
berisi level/XP, koin, lencana, kata kunci pantau, ulang tahun, skor game, dan kiriman formulir
milikmu. `/hapusdataku` menampilkan tombol konfirmasi lalu menghapus permanen data itu dari
`data/*.json` (hanya milikmu — data member lain tidak tersentuh) dan langsung menyimpannya ke disk.

### ⚙️ `/setelan-ai` — gaya AI per member + kepribadian AI server

Dari purpleGPT (`/settings` & `/server_prompt`), tanpa biaya tambahan: instruksi hanya berupa
**teks tambahan** pada prompt AI, jadi kuota tetap sama dan model tidak berubah.

- **Per member** (`/setelan-ai atur`): **panjang jawaban** (`singkat` maks 3 kalimat / `normal` /
  `detail` poin + contoh), **temperature** (bawaan model / konsisten `0,2` / seimbang `0,7` /
  kreatif `1,0`), **bahasa balasan** (otomatis atau Indonesia, Inggris, Spanyol, Prancis, Jepang,
  Korea, Portugis, Mandarin), **prompt pribadi** (maks 300 huruf, mis. *"pakai analogi sederhana"*),
  dan **rasio gambar bawaan** untuk `/gambar`.
- **Per server** (`/setelan-ai prompt-server`, khusus Admin): satu "kepribadian" yang ditempelkan
  ke semua balasan AI di server itu (maks 500 huruf; kosongkan untuk menghapus).
- `/setelan-ai lihat` menampilkan semua setelan yang sedang berlaku, `/setelan-ai reset`
  mengembalikan ke bawaan. Data disimpan di `data/ai_settings.json`.

### 🖼️ `/meme teks_atas:"…" teks_bawah:"…" template:neon` menggambar meme sendiri dengan **Pillow**
(tidak ada API gambar & tidak ada berkas aset): 6 gaya — `klasik`, `impact`, `drake` (dua panel
ditolak/diterima), `neon`, `kertas`, `terminal`. Teks otomatis dibungkus (maks 6 baris × 120 huruf)
dan hasilnya dikirim sebagai PNG 800×800.
