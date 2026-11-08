---
title: "B. Fitur AI Agent & Otomasi Komunitas (/agent)"
description: "Auto-chat dengan etika anti-nimbrung, pemecah sepi, galeri, welcome/goodbye, digest & FAQ."
icon: "smart_toy"
weight: 2
toc: true
---

Fitur ini membuat bot berbaur di channel publik server — baik di **Text Channel biasa (`#general`)** maupun di dalam **Channel Forum & Media (`#tanya-jawab`, `#showcase-karya`, `#forum-berita`)** — layaknya **warga/teman nongkrong asli** (bukan gaya kaku robot asisten). Seluruh fiturnya dikendalikan per-channel oleh Admin melalui command `/agent`:
- **Dukungan Penuh & Fitur Pintar Channel Forum (`ForumChannel` & `MediaChannel`):**
  - Saat `/agent chat`, `/agent gallery`, `/agent youtube`, atau `/agent cari` diaktifkan pada sebuah **Channel Forum**, bot otomatis bekerja di seluruh **Postingan (*Post/Thread*)** di dalam forum tersebut!
  - Membaca **Judul Postingan Forum**, **Tag Forum**, isi teks, gambar, dokumen **`.pdf`**, Voice Note, hingga **lampiran file kode** (`.py`, `.js`, `.json`, `.log`, dll.), serta menjaga ingatan obrolan **terpisah di masing-masing postingan** agar topik antar-postingan tidak pernah tercampur!
  - **🏷️ Auto-Tagging Forum Pintar (0 API Call):** Jika member membuat postingan forum baru tanpa memilih Tag, bot otomatis memilihkan 1–2 Tag Forum yang paling relevan dengan judul & isi topiknya tanpa memakan kuota API tambahan.
  - **✅ Tombol Persisten `Tandai Selesai`:** Pada balasan pembuka di Postingan Forum, bot menyematkan tombol hijau **`✅ Tandai Selesai`** yang bisa diklik oleh pembuat postingan atau Moderator untuk menambahkan awalan `✅`, memasang tag *Selesai/Solved*, dan mengarsipkan diskusi dengan rapi!

## 1. 💬 Auto-Chat Natural ala Manusia & Etika Anti-Nimbrung Pintar (`/agent chat`)
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

## 2. 💤 Pemecah Sepi Otomatis / *Dead-Chat Reviver* (`/agent chat` & `/agent sapa`)
- Jika channel Auto-Chat sepi tidak ada aktivitas selama **`menit_sepi`** (default **30 menit**, mendukung pilihan cepat maupun ketik fleksibel seperti `30 detik`, `1`, `5`, `15`, `30`, `60`, `1 jam`, atau `0` untuk mematikan), AI otomatis memulai obrolan santai sesuai suasana jam saat itu (*contoh malam hari: "Sepi banget nih, tumben pada ngilang pas jam santai gini, pada mabar diam-diam ya kalian? Wkwk."*).
- **Proteksi Anti-Monolog / Anti-Spam:** Jika setelah AI menyapa otomatis ternyata belum ada satu pun member yang membalas, AI **berhenti menyapa ulang** sampai ada member manusia yang chat lagi — sehingga channel tidak pernah penuh spam sendirian!
- **Jam Tenang Malam (*Quiet Hours*):** Secara default aktif pada pukul **23:00 – 06:00** waktu lokal agar AI tidak tiba-tiba memecah sepi jam 3 subuh saat member sedang tidur (bisa diatur lewat `/agent persona`).

## 3. 🕒 Kesadaran Waktu Lokal *Real-Time* (WIB / WITA / WIT)
- AI selalu tahu hari, tanggal, jam, dan menit saat ini secara presisi (mendukung **WIB**, **WITA**, dan **WIT**).
- Jika ditanya *"sekarang jam berapa?"* pada pukul 16:30, AI akan menjawab akurat pukul 16:30 dan mengaitkannya dengan suasana waktu tersebut (misalnya sore jam-jam rawan ngantuk, pagi semangat, siang terik, atau malam waktunya mabar).

## 4. 😄 Membaca Visual Stiker & Custom Emoji Server
- Saat member mengirim **Stiker Discord** (PNG/APNG/GIF) atau **Custom Emoji Server** (`<:nama:id>` / `<a:nama:id>`), bot mengunduh gambar visual stiker/emoji tersebut dan memindainya lewat **Gemini Vision**.
- Hasilnya, AI benar-benar "melihat" gambar stiker lucu atau ekspresi wajah pada emoji yang dikirim dan membalasnya secara relevan!

## 5. 📸 Gallery Auto-Comment: Scan Foto & Video (`/agent gallery`)
- Aktifkan di channel pamer karya, meme, fotografi, cosplay, setup PC, atau klip game (misal `#gallery` / `#media`).
- Setiap kali member mengirim **Foto/Gambar** (hingga 8 MB) atau **Video Klip Pendek** (`.mp4`, `.webm`, `.mov` hingga 15 MB):
  1. Bot otomatis men-scan isi visual gambar atau video tersebut menggunakan Gemini Multimodal.
  2. Memberikan **reaksi emoji otomatis** (`✨`, `🔥`, `😍`, `👏`, atau `🙌` — bisa dinyalakan/dimatikan).
  3. Membalas (*reply*) postingan tersebut dengan komentar spesifik yang menyebutkan detail unik di dalam foto/video (seperti warna kostum, karakter, latar tempat, atau momen serunya).

## 6. 👋 AI Auto-Welcomer Member Baru + Persona Sambutan Khusus (`/agent welcome`)
- **Persona sambutan TERPISAH dari persona Auto-Chat!** Pilih gaya sambutan lewat `persona:` — **🤗 Hangat & Tulus**, **😂 Lucu & Receh**, **😎 Santai & Akrab**, atau **🙂 Normal & Sopan**. Mengubah `/agent persona` (gaya obrolan harian) **tidak akan** mengacaukan gaya sambutan, begitu pula sebaliknya.
- **Kata sapaan "halo/hai" berganti-ganti dari 64 sapaan / 45 bahasa** — Asia Timur & Tenggara (`こんにちは` Jepang, `안녕하세요` Korea, `你好` Mandarin, `สวัสดี` Thailand, `Xin chào` Vietnam, `Kumusta` Filipina, `မင်္ဂလာပါ` Myanmar, `សួស្តី` Kamboja, `ສະບາຍດີ` Laos, `Ola` Timor Leste), Timur Tengah & India (`مرحبا` Arab, `سلام` Persia, `नमस्ते` Hindi, `வணக்கம்` Tamil), sampai Eropa & Afrika (`Привет` Rusia, `Γεια σου` Yunani, `שלום` Ibrani, `Bonjour` Prancis, `Hola` Spanyol, `Sawubona` Zulu). **Hanya kata sapaan pembuka** yang berbahasa asing — seluruh kalimat sambutan tetap **Bahasa Indonesia** yang hangat/lucu sesuai persona.
- **Huruf latin & terjemahannya ikut tampil**, jadi member yang tidak membaca aksaranya tetap paham. Formatnya: **`"မင်္ဂလာပါ"` (Mingalaba)** — *semoga berkah* → lalu kalimat Bahasa Indonesia. Huruf latin & arti ditempel oleh kode (bukan oleh AI) supaya konsisten dan tidak pernah salah tulis. Bisa dimatikan dengan `arti:False` (hanya aksara aslinya).
- **Kalimat sambutannya tetap dibuat AI (Gemini), bukan template.** Urutannya: kode memilih kata sapaan (acak, hindari pengulangan 8 sambutan terakhir) → AI menulis 1–2 kalimat sambutan sesuai persona, jam, tanggal, info tambahan, dan anti-monoton → kode menempelkan huruf latin + arti di depan. Kuota tetap **1 panggilan AI per member baru** (tidak ada panggilan tambahan), dan bila AI gagal/tanpa API key tidak ada pesan yang dikirim — sama seperti sebelumnya.
- Bisa memilih **satu bahasa** tertentu (`bahasa_sapaan:jepang`) atau **acak semua bahasa** (default, `auto`) agar setiap member baru mendapat sapaan yang berbeda.
- Tabel arti lengkap ada di `community_agent.ASIAN_GREETINGS` (`word` = aksara asli, `read` = huruf latin, `arti` = terjemahan Indonesia) — menambah bahasa baru cukup menambah satu baris di sana, dan otomatis muncul di `/agent welcome`, `/agent goodbye`, serta dashboard.
- Bisa ditambahkan `pesan_tambahan` (contoh: *"Jangan lupa ambil role di #roles ya"*) yang akan dirangkai secara luwes oleh AI, serta `tes_sekarang:True` untuk langsung melihat contoh sambutannya.

## 7. 👣 AI Auto-Goodbye: Kartu Perpisahan Member Keluar (`/agent goodbye`)
- Saat ada member keluar dari server, bot otomatis mengirim **kartu perpisahan** berisi pesan hangat + foto profil + **lama masa kebersamaan** (jumlah hari sejak bergabung).
- Punya **persona perpisahan sendiri** (Hangat / Lucu / Santai / Normal) dan **61 kata perpisahan dari 40+ bahasa** seperti `またね` (Mata ne — sampai nanti, Jepang), `안녕히 가세요` (Annyeonghi gaseyo — selamat jalan, Korea), `再见` (Zàijiàn — sampai jumpa, Mandarin), `ลาก่อน` (Lakorn, Thailand), `مع السلامة` (Ma'a as-salama, Arab), `Auf Wiedersehen` (Jerman), `Kwaheri` (Swahili), dan lainnya — sisa kalimat tetap Bahasa Indonesia.
- Format pesan perpisahan sama: **`"またね"` (Mata ne)** — *sampai nanti* `@member`, lalu kalimat hangatnya. Huruf latin & arti bisa dimatikan lewat `arti:False`.
- Kalimat perpisahannya **juga tetap ditulis AI** (1 panggilan per member keluar, dengan konteks lama bergabung & anti-monoton); kode hanya memilih kata perpisahan lalu menempelkan huruf latin + artinya.
- Anti-dobel: tetap ramah kuota karena hanya 1 pesan per member keluar dan ada deduplikasi otomatis.

## 8. 🖼️ Banner Gambar & Empat Tampilan Sambutan (`/agent banner`, `/agent kartu`)

Sapphire punya welcome berbasis gambar; sekarang bot ini juga — tanpa dashboard, cukup lewat Discord.

- **`/agent banner gambar:<file> jenis:Sambutan`** — unggah gambar (PNG/JPG/WEBP/GIF, maks 8 MB) sebagai
  banner sambutan, perpisahan, atau pesan boost. Berkas disimpan di **`data/media/`**, **bukan** URL.
- **`/agent kartu mode:<pilihan>`** — empat tampilan sambutan (dan perpisahan):
  | Mode | Hasil | Biaya |
  | :--- | :--- | :--- |
  | 📝 Text | teks polos — **satu-satunya mode yang bisa me-ping member** | paling hemat |
  | 🧱 Embed | embed bertema server, banner + foto profil kecil | ringan |
  | 🖼️ Card | **kartu PNG**: banner + foto profil bulat + nama + jumlah member | +10–15 MB RAM saat render |
  | 🗂️ Container | kartu Components V2 bertema server | ringan |

  Setelan di dashboard: halaman **👋 Sambutan & pamit → 🎨 Tampilan pesan** — pilih mode, isi
  template (`{user_mention}`, `{user_name}`, `{server}`, `{member_count}`), lalu lihat
  **pratinjau** bentuk pesannya sebelum menyimpan. Di panel yang sama ada slot
  **unggah gambar kartu** untuk mode Card (+ tombol hapus), jadi tidak perlu command.
- **`/agent dm aktif:True`** — kirim juga salinan sambutan lewat DM ke member baru
  (gagal senyap bila DM member ditutup).
- **`/agent boost channel:#umum`** — pesan terima kasih otomatis saat ada member **nge-boost** server,
  mendukung teks kustom `{user}`, `{name}`, `{guild}` + banner boost sendiri.

> **Kenapa gambarnya disimpan di server, bukan URL?**
> URL lampiran Discord (`cdn.discordapp.com/attachments/...`) mengandung tanda tangan yang **kedaluwarsa
> ±24 jam**. Kalau hanya URL yang disimpan, banner hilang besok. Karena itu berkasnya disimpan lokal lalu
> dikirim ulang sebagai lampiran (`attachment://`) setiap kali sambutan dikirim.
>
> Mode **Card** membutuhkan **Pillow** (sudah ada di `requirements.txt`). Bila Pillow tidak terpasang
> **atau** gambar kartu belum diunggah, bot otomatis mundur ke mode **Embed** — tidak ada error.

> **Kenapa mention hanya jalan di Text & Container?** Di dalam embed (dan lampiran kartu), `@nama`
> hanyalah teks biasa — Discord tidak memicu notifikasi. Karena itu mode yang mendukung ping
> mengirim mention lewat `content` terpisah, di luar embed/kartu.

## 9. 🔔 Notifikasi Sosial: YouTube, Twitch, TikTok, Reddit & RSS/Atom (`/sosial`)

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

## Cara mendapatkan `TWITCH_CLIENT_ID` & `TWITCH_CLIENT_SECRET` (sekali saja, gratis)

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

## 10. 📝 Perangkum Obrolan Channel Tertinggal (`/ringkas`)
- Ketinggalan **99+ notifikasi chat** di grup? Siapa pun member bisa mengetik **`/ringkas`** (pilih `25`, `50`, `100`, atau `150` pesan terakhir).
- Bot akan merangkum poin-poin inti obrolan warga beserta info/momen penting ke dalam Embed rapi berbahasa Indonesia (secara default hanya terlihat oleh Anda sendiri agar tidak mengganggu chat).

## 11. 📲 Menu Tekan-Tahan Pesan / Klik Kanan (*Discord Context Menu Apps*) — Tanpa Ketik Command!
Member tidak perlu mengetik command apa pun untuk menerjemahkan atau memahami pesan asing/rumit:
- **Cara pakai di HP (Android/iOS):** Tekan & tahan (*long-press*) pesan siapa saja di channel mana pun ➔ pilih **Apps** ➔ klik:
  - **`🌐 Terjemahkan ke Indonesia`** — Menerjemahkan pesan bahasa Inggris, Jepang, Korea, Arab, Mandarin, bahasa gaul/slang, maupun teks di dalam gambar/Voice Note ke Bahasa Indonesia yang luwes.
  - **`💡 Jelaskan Pesan Ini`** — Menjelaskan maksud istilah teknis, potongan kode/error, pengumuman panjang, atau meme secara ringkas & mudah dimengerti.
  - **`🔍 Cek Fakta / Hoaks`** — Memeriksa kebenaran klaim berita heboh, rumor, atau tangkapan layar secara objektif menggunakan pencarian berita & web live gratis lengkap dengan tautan sumber buktinya!
- **Cara pakai di PC/Laptop:** Klik kanan pesan ➔ sorot **Apps** ➔ pilih menu di atas. Hasilnya tampil privat (*ephemeral*) hanya untuk Anda!

## 12. 🎬 Perangkum Video YouTube & Pembaca Link Web Per-Channel (`/ringkas link` & `/agent youtube`)
- **Diatur Per-Channel (Bisa Aktif di Beberapa Channel Sekaligus!):** Persis seperti `/agent chat` dan `/agent gallery`, Admin bebas memilih channel mana saja yang mengaktifkan fitur rangkum YouTube & link web lewat **`/agent youtube channel:#nama-channel aktif:True`** (bahkan tetap bekerja walaupun channel tersebut tidak menyalakan Auto-Chat!).
- **Command `/ringkas link` & Ruang Privat `ai-...`:** Tempel link YouTube (`youtube.com/watch`, `youtu.be`, `shorts`, `live`) atau artikel web untuk mendapatkan rangkuman poin penting dalam hitungan detik (100% gratis memakai fitur *YouTube Video Understanding* Gemini)!
- **Panggil Nama Bot + Kirim / Reply Link di Channel Aktif:** Di channel yang sudah diaktifkan `/agent youtube`, member cukup memanggil **nama panggilan bot** / `@mention` / *reply* ke bot sambil menyertakan link YouTube/web — **atau me-*reply* pesan teman yang berisi link YouTube sambil memanggil bot** (contoh: *"Whas rangkumin video YouTube ini dong"*).
- **2 Mode Fleksibel Per-Channel (`auto_di_channel`):**
  - `auto_di_channel: False` (**Default & Rekomendasi**): Diam saat warga sekadar share link biasa di channel tersebut, namun langsung merangkum saat nama bot dipanggil atau memakai `/ringkas link`.
  - `auto_di_channel: True` (**Mode Channel Khusus Video**): Setiap link YouTube/Web yang dikirim warga di channel tersebut otomatis dirangkum tanpa perlu memanggil nama bot!

## 13. 🌍 Live Web & News Search Gratis Per-Channel (`/cari` & `/agent cari`)
- **100% Gratis di *Free Tier* (Bebas Error `You exceeded your current quota`):** Menggunakan mesin pencari web & berita *real-time* mandiri (**Google News RSS Indonesia + DuckDuckGo Web** + pembaca isi artikel berita) yang dirangkum oleh model Gemini gratis lengkap dengan daftar tautan **🌐 Sumber Web**! *(Juga mendukung opsi Google Search Grounding Paid Tier via `GEMINI_PAID_SEARCH_ENABLED=true`).*
- **Diatur Per-Channel (Bisa Aktif di Beberapa Channel Sekaligus!):** Admin bebas mengaktifkan fitur pencarian di satu atau beberapa channel pilihan lewat **`/agent cari channel:#nama-channel aktif:True`** (bekerja baik di channel Auto-Chat maupun channel mandiri khusus berita!).
- **Bisa Lewat `/cari` ATAU Panggil Nama Bot Langsung di Channel Aktif:**
  - Ketik **`/cari pertanyaan:berita timnas indonesia hari ini`** di channel yang aktif (atau ruang privat `ai-...`), **ATAU**
  - Langsung panggil nama panggilan bot di channel yang mengaktifkan `auto_di_chat:True` (contoh: *"Whas coba cari berita hari ini tentang harga emas Antam"*) — nama panggilan bot otomatis dibersihkan dari kata kunci pencarian sehingga hasil berita akurat!

## 14. 🎮 6 Mode Mini-Game Tongkrongan AI (`/game`) + Papan Skor Server (*Leaderboard*)
Bikin channel tongkrongan makin ramai dengan **6 permainan interaktif** (anti-bosan & hemat kuota *Free Tier*!):
- **`🎭 Tebak dari Emoji` (+20 Poin):** Tebak judul film, game, anime, atau makanan populer dari 4–5 petunjuk emoji di chat!
- **`🖼️ Tebak Gambar AI` (+25 Poin):** AI melukis gambar misteri secara langsung lewat Flux *Free Tier* dan warga berlomba menebak objek/karakter di dalamnya!
- **`⛓️ Sambung Kata Indonesia` (+5 Poin/Kata):** Permainan berantai menyambung huruf terakhir kata sebelumnya (hingga 15 rantai kata, **0 panggilan API Gemini per giliran** sehingga super ringan & bebas kuota!).
- **`🧠 Kuis Trivia Cepat A/B/C/D` (+15 Poin):** Adu cepat klik tombol pilihan ganda A/B/C/D langsung di layar (1x kesempatan per orang per ronde!).
- **`🕵️ Tebak Kata Misteri` (+20 Poin):** Permainan *"Siapakah / Apakah Aku?"* dengan 3 petunjuk bertingkat + tombol **💡 Buka Petunjuk**.
- **`🔀 Susun Huruf Acak` (+15 Poin):** Adu cepat menyusun kata Bahasa Indonesia yang hurufnya diacak.
- Seluruh skor kemenangan tersimpan permanen per server di `data/game_scores.json` dan dapat dilihat kapan saja lewat **`/game papan_skor`**!

## 15. 📌 Memori Info & FAQ Resmi Server (`/agent info`), ☀️ Koran Pagi (`/agent digest`), & 🎛️ Panel Admin (`/agent panel`)
- **Memori Info & FAQ Server (`/agent info`):** Admin dapat menyimpan hingga **25 entri pengetahuan resmi server** (seperti *Rules*, IP Server Minecraft/FiveM, jadwal mabar, cara *open ticket*, atau link sosial media). AI otomatis menghafal dan menjawab akurat berdasarkan data ini baik di channel publik, Forum, maupun ruang konsultasi privat!
- **Koran & Sapaan Pagi Otomatis (`/agent digest`):** Setiap pagi sesuai jam pilihan (default **`07:00`** waktu lokal), bot otomatis merangkum berita terhangat hari ini + fakta unik pembuka hari ke channel pilihan (dilengkapi proteksi anti-dobel kirim di tanggal yang sama).
- **Panel Kontrol Admin Interaktif (`/agent panel`):** Atur semua fitur channel (Auto-Chat, Galeri, YouTube, Cari, **Welcome, Goodbye, Digest, Fakta Harian**), ubah Persona, hingga tambah FAQ Server langsung lewat menu *dropdown* & *popup form (Modal)* tanpa perlu menghafal banyak parameter command!

---
