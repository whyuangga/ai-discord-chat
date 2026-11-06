# 🤖 AI Discord Chat & Community Agent — Google Gemini Edition (`v1.40.0-beta`)

Bot Discord modular berbasis **Google Gemini** dengan arsitektur **`cogs/`** yang rapi:
**satu proses**, penyimpanan **JSON** (tanpa database/Redis), dan dirancang untuk
**Free Tier** (±53 MB RAM saat diam). Fitur AI memakai kuota Gemini seminimal mungkin, dan
sebagian besar fitur komunitas berjalan **tanpa AI sama sekali (0 kuota)**.

> **Versi `v1.40.0-beta`** · **53 command utama** · **367 tes otomatis** · tanpa dependency baru
> sejak v1.20 · detail tiap fitur ada di [daftar isi](#-daftar-isi) atau situs dokumentasi
> (`site/`, cara deploy di [`site/README.md`](site/README.md)).

---

## 🗺️ Peta Fitur

Pintasan cepat sebelum masuk penjelasan lengkap — detail tiap area ada di
[**dokumentasi fitur**](docs/fitur.md), referensi command di
[**daftar command**](docs/command.md). Kolom **Kuota** menandakan apakah fitur itu memanggil
Gemini (`AI`) atau berjalan lokal (`0`).

| Area | Command utama | Isi singkat | Kuota |
| :--- | :--- | :--- | :---: |
| 🔒 **Ruang AI privat** | `/sesi` | Private thread, 5 kepribadian, PDF, voice note, vision, generate/edit gambar | AI |
| 🌐 **AI Agent publik** | `/agent` | Auto-chat dengan **etika anti-nimbrung**, forum auto-tag + `✅ Tandai Selesai`, digest pagi, welcome & goodbye | AI |
| 🔎 **Pintasan pintar** | `/ringkas`, `/cari`, `/terjemah`, `/faq` | Rekap chat/link/YouTube, info terkini, terjemahan ter-cache, FAQ lokal | AI / 0 |
| 🎮 **Hiburan** | `/game` | 6 mini-game tongkrongan + papan skor server | AI |
| 🎵 **Musik 24/7** | `/musik` | Lavalink v4, panel ala Rythm, filter audio, **playlist pribadi** per member | 0 |
| 🛠️ **Server otomatis** | `/serverstats`, `/autorole`, `/fakta`, `/keamanan` | Channel statistik, auto role, fakta 4× sehari, anti-phishing | 0 |
| 🧩 **Komunitas** | `/panel-role`, `/menu`, `/poll`, `/saran`, `/embed`, `/tempvoice`, `/starboard`, `/sticky`, `/verifikasi`, `/ingatkan`, `/info` | Reaction role, menu builder, polling, kotak saran, temp voice, sorotan pesan | 0 |
| 📈 **Retensi & pelayanan** | `/level`, `/tiket` | XP pesan + voice, **musim** & **prestige**; tiket thread + **SLA**, **auto-close**, **rating bintang** | 0 |
| 🛡️ **Keamanan** | `/mod`, `/keamanan spam`, `/nuke`, `/raid` | Moderasi bercatatan, anti-spam/anti-raid, anti-nuke (**bot asing** & **mode beku**), raid guard otomatis | 0 |
| 💰 **Ekonomi & tumbuh** | `/ekonomi`, `/tumbuh`, `/log` | Koin + toko role, invite tracker & retensi, audit log pesan | 0 |
| 🧰 **Admin & diagnosa** | `/backup`, `/analitik`, `/bahasa`, `/prefix`, `/perawatan`, `/panel`, `/tampilan` | Restore struktur, ekspor CSV/webhook, i18n ID/EN, prefix per server, audit RAM, tema | 0 |
| 📊 **Hemat kuota** | `/pemakaian`, dashboard web | Statistik AI, cache jawaban, cap harian, **48 setelan**, kirim embed/webhook + pratinjau, unggah banner, grafik tren, **kotak masuk tiket** (balas/tutup/pasang panel), editor panel, panel verifikasi, ekspor CSV | 0 |

---

## ⚡ Kenapa ringan (angka terukur, bukan perkiraan)

| Aspek | Angka | Bukti |
| :--- | :--- | :--- |
| RAM saat diam | **±53 MB** — `discord.py` sendiri ±43 MB | `/perawatan memori`, `/status` |
| Tambahan data ekstrem¹ | **+3–4 MB** | diukur di sandbox, lihat [Audit RAM](docs/fitur.md#w-audit-ram--cache-perawatan-memori) |
| Proses & penyimpanan | **1 proses**, JSON, tanpa DB/Redis | `/perawatan memori` |
| Kuota untuk UI, panel, & alert | **0** | semua tombol/panel dibuat lokal |
| Dependency baru sejak v1.20 | **tidak ada** | `requirements.txt` tidak berubah |

> ¹ 5 server × 500 member level + 1.000 tiket + 1.000 kasus moderasi + playlist penuh.
> Biaya terbesar bot ini adalah pustaka Discord, **bukan** fitur-fiturnya.

---

## 🚀 Mulai cepat

1. **Isi `.env`** — minimal `DISCORD_BOT_TOKEN` & `GEMINI_API_KEY`
   (lihat [Penjelasan Variabel `.env`](#-penjelasan-variabel-env)).
2. **Undang bot** dengan scope `bot` + `applications.commands`
   (lihat [Persiapan Developer Portal](#-persiapan-di-discord-developer-portal)).
3. **Pasang panel** di server: `/sesi panel`, `/agent panel`, lalu `/panel` sebagai pusat kontrol.
   Untuk server ramai, lanjut ke `/tiket panel`, `/menu buat`, `/level atur aktif:True`, `/nuke atur`.

> 🔐 Fitur keamanan (`/nuke`, `/raid`) butuh izin **View Audit Log**. Saran izin lengkap ada di
> [Persiapan Developer Portal](#-persiapan-di-discord-developer-portal).

---

## 📚 Daftar Isi

1. [Peta Fitur (ringkasan semua area)](#-peta-fitur)
2. [Kenapa ringan (angka RAM terukur)](#-kenapa-ringan-angka-terukur-bukan-perkiraan)
3. [Mulai cepat (3 langkah)](#-mulai-cepat)
4. [Penjelasan Lengkap Semua Fitur A–W](docs/fitur.md) — *dokumen terpisah*
5. [Daftar Lengkap Command & Tombol](docs/command.md) — *dokumen terpisah*
6. [Panduan Cara Pakai Semua Fitur (Step-by-Step)](#-panduan-cara-pakai-semua-fitur-step-by-step)
7. [Cara Mematikan (**Disable**) Fitur Kapan Saja](#-cara-mematikan-disable-fitur-kapan-saja)
8. [Penjelasan Variabel `.env`](#-penjelasan-variabel-env)
9. [Persiapan di Discord Developer Portal](#-persiapan-di-discord-developer-portal)
10. [Checklist Uji Coba di Server Orang Lain](#-checklist-uji-coba-di-server-orang-lain)
11. [Panduan Deploy di Wispbyte (Step-by-Step)](#-panduan-deploy-di-wispbyte-step-by-step)
12. [Menjalankan Secara Lokal / VPS](#-menjalankan-secara-lokal--vps)
13. [Struktur File Proyek (Modular `cogs/`)](#-struktur-file-proyek-modular-cogs)
14. [FAQ & Solusi Masalah Umum](#-faq--solusi-masalah-umum)
15. [Lisensi](#-lisensi)

> 📌 **Catatan terpisah:** [rencana dashboard web, BYOK, & “isi sendiri API key” yang masih diparkir](docs/catatan-dashboard-dan-kunci-api.md).
>
> 🛰️ **Dashboard untuk instance sendiri:** jalankan `python tools/dashboard_token.py --tulis`
> (membuat token & mengisi `.env`), lalu `python tools/dashboard_token.py --periksa` untuk cek
> kesiapan dan melihat alamat yang dibuka. Tanpa login OAuth — tiap orang memakai tokannya sendiri.

---

## 🎮 Panduan Cara Pakai Semua Fitur (Step-by-Step)

### 1. Cara Memasang & Memakai Panel Ruang Privat AI

#### 👑 Untuk Admin Server:
1. Buat atau buka channel teks khusus untuk panel AI (misal `#ai-assistant`).
2. Ketik perintah berikut lalu tekan Enter:
   ```text
   /sesi panel
   ```
   *(Atau bisa juga menggunakan prefix `!setup_panel`).*
3. Bot akan menampilkan kotak **✨ PANEL RUANG PRIVAT GOOGLE GEMINI AI** dengan dua tombol permanen yang siap dipakai seluruh member 24/7.

#### 👤 Untuk Member Server:
- **Mulai Ruang Chat AI, Vision & Koding:**
  1. Klik tombol hijau **💬 Chat AI (Teks & Vision)** pada panel.
  2. Pilih salah satu dari **5 Mode Kepribadian Gemini** (Utama, Kilat, Koding, Riset, atau Curhat).
  3. Klik tautan thread privat `ai-namakamu` yang dibuatkan bot, lalu:
     - Ketik pertanyaan apa saja untuk mengobrol.
     - Lampirkan **foto/screenshot**, **PDF**, **Voice Note (🎤)**, atau **file kode** (`.py`, `.js`, `.txt`, dll.) jika ingin dianalisis langsung.
     - Pilih menu dropdown **🎭 Ganti Mode** (atau ketik `/sesi model`) jika ingin berganti kepribadian di tengah obrolan.
     - Klik **🔄 Reset Sesi** (atau `/sesi reset`) untuk menghapus ingatan topik lama.
     - Klik **🔴 Akhiri Sesi** (atau `/sesi tutup`) jika sudah selesai — rekap percakapan lengkap dalam bentuk file `.txt` akan dikirim otomatis ke DM Anda!

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

#### E. Merangkum Chat yang Ketinggalan (`/ringkas chat`)
Bisa dipakai oleh semua member saat baru buka Discord dan tertinggal obrolan panjang:
```text
/ringkas chat jumlah:50 Pesan Terakhir - Default publik:False
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
  - `auto_di_channel:False` (**Rekomendasi & Default**): Bot diam saat warga sekadar share link biasa di channel tersebut, namun **langsung merangkum** jika nama bot dipanggil / di-*mention* / di-*reply* bersama link tersebut, atau lewat `/ringkas link`.
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

#### J. Mengatur Sambutan Persona & Sapaan Bahasa Asia (`/agent welcome`) + Perpisahan (`/agent goodbye`)
```text
/agent welcome channel:#welcome aktif:True persona:lucu bahasa_sapaan:auto tes_sekarang:True
/agent goodbye channel:#perpisahan aktif:True persona:hangat bahasa_sapaan:korea
```
- `persona:` menentukan gaya **sambutan/perpisahan** saja (Hangat / Lucu / Santai / Normal) — tidak mengubah gaya obrolan AI harian.
- `bahasa_sapaan:` memilih bahasa kata sapaan pembuka (`auto` = acak semua bahasa Asia Timur & Tenggara). Isi kalimat tetap Bahasa Indonesia.

#### K. Memasang Fitur Server (Statistik, Auto Role, Fakta, & Anti-Phishing)
```text
/serverstats otomatis aktif:True
/autorole atur role:@Member role2:@Notif
/fakta atur channel:#umum jadwal:08:00,12:00,16:00,20:00
/keamanan phising aktif:True aksi:hapus_peringat log_channel:#mod-log
```
- `/serverstats otomatis` membuat Voice Channel penghitung yang diperbarui ±10 menit sekali.
- `/fakta sekarang` mengirim contoh rubrik fakta saat itu juga (tanpa menunggu slot jadwal).
- `/fakta status` menampilkan seluruh slot, slot berikutnya, dan slot yang sudah terkirim hari ini.
- `/keamanan cek link:https://...` bisa dipakai semua member untuk memeriksa link.

---

## 🛑 Cara Mematikan (*Disable*) Fitur Kapan Saja

Semua fitur dapat dimatikan satu per satu **langsung lewat Discord tanpa perlu mematikan atau me-*restart* bot**:

| Fitur yang Ingin Dimatikan | Cara / Perintah Discord |
| :--- | :--- |
| **Matikan Auto-Chat & Pemecah Sepi total** di suatu channel | `/agent chat channel:#welcome aktif:False` |
| **Matikan Pemecah Sepi saja** *(tapi Auto-Chat tetap aktif membalas warga)* | `/agent chat channel:#welcome aktif:True menit_sepi:0` |
| **Matikan AI Auto-Welcomer member baru** | `/agent welcome channel:#welcome aktif:False` |
| **Matikan Pesan Perpisahan (Goodbye)** | `/agent goodbye channel:#perpisahan aktif:False` |
| **Matikan Rubrik Fakta Unik Dunia** | `/fakta atur channel:#umum aktif:False` |
| **Matikan Voice Channel Statistik Server** | `/serverstats otomatis aktif:False` |
| **Matikan Auto Role** | `/autorole atur role:@Member aktif:False` |
| **Matikan Anti-Phishing Guard** | `/keamanan phising aktif:False` |
| **Matikan Anti-Spam/Anti-Raid** | `/keamanan spam aktif:False` |
| **Ganti Anti-Spam ke mode paling longgar** | `/keamanan spam mode:lapor` (hanya mencatat, tanpa tindakan) |
| **Matikan leveling (data tetap aman)** | `/level atur aktif:False` |
| **Matikan sistem tiket** | `/tiket matikan` |
| **Matikan batas harian AI per member** | Kosongkan/isi `AI_DAILY_CAP_PER_USER=0` lalu restart |
| **Matikan cache rekap channel** *(setiap rekap memakai kuota)* | `REKAP_CACHE_TTL_SEC=0` lalu restart |
| **Kosongkan cache rekap sekarang** | `/pemakaian reset cache_rekap:True` |
| **Matikan FAQ lokal (jawaban tanpa AI)** | `/faq hapus target:<nomor>` untuk tiap entri |
| **Matikan Starboard (sorotan pesan)** | `/starboard atur aktif:False` |
| **Matikan Gerbang Verifikasi** | `/verifikasi matikan` |
| **Lepas Sticky Message** di suatu channel | `/sticky lepas channel:#umum` |
| **Hapus panel Reaction Role** | Hapus pesan panelnya, lalu `/panel-role daftar` untuk memastikan |
| **Matikan backup otomatis & log error** | `/perawatan atur otomatis:False` |
| **Hentikan musik & keluarkan bot dari voice** | `/musik hentikan` |
| **Matikan pengumuman Now Playing** | `/musik pengaturan pengumuman:False` |
| **Matikan fitur musik sepenuhnya** *(bot tetap jalan)* | Kosongkan `LAVALINK_URI` & `LAVALINK_PASSWORD`, lalu restart |
| **Matikan Auto-Komentar Galeri total** di suatu channel | `/agent gallery channel:#galeri aktif:False` |
| **Matikan Auto-Reaction Emoji saja** di Galeri *(komentar teks tetap jalan)* | `/agent gallery channel:#galeri aktif:True auto_reaction:False` |
| **Matikan fitur Rangkum YouTube & Link Web** di suatu channel | `/agent youtube channel:#share-video aktif:False` |
| **Matikan Auto-Rangkum semua link** di channel YouTube *(agar hanya rangkum saat dipanggil / `/ringkas link` — **Default**)* | `/agent youtube channel:#share-video aktif:True auto_di_channel:False` |
| **Matikan fitur Pencarian Berita/Web (`/cari`)** di suatu channel | `/agent cari channel:#berita-terkini aktif:False` |
| **Matikan Auto-Search saat ngobrol** di channel Cari *(agar hanya jalan kalau ketik `/cari`)* | `/agent cari channel:#berita-terkini aktif:True auto_di_chat:False` |
| **Matikan Jam Tenang Malam (23:00–06:00)** *(agar sapaan tetap jalan tengah malam)* | `/agent persona jam_tenang_malam:False` |
| **Reset Nama Panggilan / Konteks Komunitas kembali ke default** | `/agent persona nama_panggilan:- konteks_komunitas:-` *(isi tanda strip `-`)* |
| **Tutup 1 Ruang Sesi Privat (`ai-...` / `draw-...`)** | Klik tombol merah **🔴 Akhiri Sesi** atau ketik `/sesi tutup` |
| **Nonaktifkan Panel Utama AI** di suatu channel | Hapus pesan Embed **✨ PANEL RUANG PRIVAT GOOGLE GEMINI AI** di channel tersebut |

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
| `MAX_CONCURRENT_MEDIA_TASKS` | Opsional | `2` | Batas tugas media (unduh/unggah gambar, video, Voice Note) yang berjalan bersamaan — kecilkan bila RAM host terbatas. |
| `AGENT_HISTORY_MESSAGES` | Opsional | `20` | Jumlah pesan terakhir yang dibaca AI Agent sebagai konteks percakapan. |
| `AGENT_MAX_IDLE_POKES` | Opsional | `1` | Batas berapa kali AI Agent boleh memecah kesunyian sebelum menunggu balasan warga. |
| `BOT_TIMEZONE` | Opsional | `Asia/Jakarta` | Zona waktu default (`Asia/Jakarta`, `Asia/Makassar`, atau `Asia/Jayapura`). |
| `AGENT_DEFAULT_IDLE_MINUTES` | Opsional | `30` | Durasi hening default (menit) sebelum AI Agent memecah kesunyian. |
| `SESSION_EXPIRE_DAYS` | Opsional | `7` | Otomatis membersihkan data sesi privat yang sudah menganggur lebih dari N hari (`0` = nonaktif). |
| `USER_COMMAND_COOLDOWN_SEC` | Opsional | `10` | Jeda wajar per-member (detik) antar pemakaian command berat (`/cari`, `/ringkas link`, `/ringkas chat`) demi melindungi kuota *Free Tier* (`0` = nonaktif; Admin otomatis bebas jeda). |
| `ENABLE_PHISHING_GUARD` | Opsional | `true` | Mengaktifkan mesin Anti-Phishing lokal (tetap perlu dinyalakan per server lewat `/keamanan phising`). |
| `SERVERSTATS_UPDATE_SEC` | Opsional | `600` | Interval pembaruan Voice Channel statistik (minimum `600` detik agar aman dari rate limit Discord). |
| `FACTS_DEFAULT_TIMES` | Opsional | `08:00,12:00,16:00,20:00` | Jadwal default rubrik Fakta Unik Dunia (4 slot/hari). Bisa diubah per server via `/fakta atur`. |
| `FACTS_MAX_SLOTS` | Opsional | `6` | Batas maksimal slot jadwal fakta per hari yang boleh dipasang Admin (`1`–`8`). |
| `AUTOROLE_MAX_ROLES` | Opsional | `3` | Jumlah maksimal role yang bisa dipasang lewat Auto Role. |
| `STARBOARD_EMOJI` | Opsional | `⭐` | Emoji default starboard (bisa diganti per server lewat `/starboard atur`). |
| `STARBOARD_DEFAULT_THRESHOLD` | Opsional | `3` | Jumlah reaksi minimal agar pesan masuk starboard. |
| `REMINDER_MAX_PER_USER` | Opsional | `15` | Maksimal pengingat aktif per member (`/ingatkan`). |
| `STICKY_MIN_INTERVAL_SEC` | Opsional | `5` | Jeda minimum (detik) sebelum sticky message turun ulang, agar channel tidak dibanjiri bot. |
| `BACKUP_INTERVAL_DAYS` | Opsional | `7` | Interval backup konfigurasi otomatis ke channel `/perawatan atur` (`0` = nonaktif). |
| `BOT_LOG_CHANNEL_ID` | Opsional | *(kosong)* | ID channel global untuk laporan error bot (bisa juga diatur per server lewat `/perawatan atur log_channel`). |
| `LAVALINK_URI` | Opsional | *(kosong)* | Alamat node Lavalink v4 (`host:port`, `https://…`, atau `wss://…`). Kosong = fitur musik nonaktif. |
| `LAVALINK_PASSWORD` | Opsional | *(kosong)* | Password node Lavalink. Wajib diisi bersama `LAVALINK_URI` untuk mengaktifkan musik. |
| `LAVALINK_NODE_NAME` | Opsional | `utama` | Nama node untuk log. |
| `MUSIC_DEFAULT_VOLUME` | Opsional | `60` | Volume default saat bot bergabung ke voice (`1`–`150`). |
| `MUSIC_MAX_QUEUE` | Opsional | `50` | Batas jumlah lagu dalam antrean (menjaga RAM tetap kecil). |
| `MUSIC_IDLE_DISCONNECT_SEC` | Opsional | `300` | Keluar otomatis dari voice setelah sekian detik tanpa lagu. |
| `AUTO_REPLY_MAX_RULES` | Opsional | `25` | Batas aturan `/jawab-otomatis` per channel. |
| `AUTO_REPLY_COOLDOWN_SEC` | Opsional | `20` | Jeda aman antar-balasan otomatis (detik) agar channel tidak dibanjiri. |
| `ANNOUNCEMENT_MAX_PER_GUILD` | Opsional | `15` | Batas pengumuman terjadwal per server. |
| `GIVEAWAY_HISTORY_MAX` | Opsional | `25` | Jumlah giveaway selesai yang tetap disimpan di `data/engagement.json`. |
| `SPAM_FLOOD_COUNT` | Opsional | `6` | Jumlah pesan sebelum dianggap banjir (flood). |
| `SPAM_FLOOD_WINDOW_SEC` | Opsional | `10` | Jendela waktu (detik) untuk menghitung flood. |
| `SPAM_MENTION_LIMIT` | Opsional | `6` | Batas mention dalam satu pesan. |
| `SPAM_LINK_LIMIT` | Opsional | `4` | Batas jumlah link dalam satu pesan. |
| `SPAM_CAPS_MIN_LENGTH` | Opsional | `20` | Panjang minimum pesan sebelum HURUF KAPITAL diperiksa. |
| `SPAM_TIMEOUT_SEC` | Opsional | `300` | Durasi time-out mode `timeout` (maks 86400). |
| `SPAM_RAID_JOIN_COUNT` | Opsional | `8` | Jumlah join pemicu peringatan raid. |
| `SPAM_RAID_WINDOW_SEC` | Opsional | `60` | Jendela waktu (detik) deteksi raid. |
| `LEVELS_XP_MIN` / `LEVELS_XP_MAX` | Opsional | `15` / `25` | Rentang XP acak per pesan. |
| `LEVELS_COOLDOWN_SEC` | Opsional | `60` | Jeda minimum antar XP per member (anti-farming). |
| `LEVELS_MAX_LEVEL` | Opsional | `100` | Batas atas level. |
| `LEVELS_MAX_MEMBERS` | Opsional | `500` | Jumlah member teratas yang disimpan per server. |
| `LEVELS_VOICE_XP_PER_MIN` | Opsional | `2` | XP per menit berada di voice channel (0 kuota AI). |
| `LEVELS_VOICE_DAILY_CAP_MIN` | Opsional | `240` | Batas menit voice yang dihitung per member per hari (anti-farming). |
| `DASHBOARD_TOKEN` | Opsional | Kosong | Kata sandi akses dashboard web. Kosong = dashboard nonaktif. |
| `DASHBOARD_PORT` | Opsional | `0` | Port dashboard (`0` = ambil otomatis dari `SERVER_PORT`/`PORT` panel). |
| `DASHBOARD_HOST` | Opsional | `0.0.0.0` | Alamat bind server dashboard (jangan diganti kecuali perlu). |
| `DASHBOARD_REFRESH_SEC` | Opsional | `30` | Interval auto-refresh halaman dashboard (detik). Isi `0` untuk mematikan (dianjurkan bila sering mengisi form dari HP). |
| `DASHBOARD_UPLOAD_MB` | Opsional | `8` | Batas ukuran unggahan banner/gambar dari dashboard (MB, 1–25). Disimpan di `data/uploads/`. |
| `TRANSLATE_RATE_LIMIT_SEC` | — | `3` | (internal, `translate_tools.py`) Jeda minimal antar-terjemahan per channel. |
| `TICKET_MAX_OPEN_PER_USER` | Opsional | `2` | Batas tiket aktif per member. |
| `TICKET_MAX_TRANSCRIPT_LINES` | Opsional | `400` | Jumlah baris pesan pada transkrip tiket. |
| `TICKET_AUTO_CLOSE_HOURS` | Opsional | `0` | Tutup otomatis tiket menggantung setelah N jam (0 = nonaktif). |
| `AI_DAILY_CAP_PER_USER` | Opsional | `0` | Batas operasi AI per member per hari (`0` = tanpa batas). |
| `AI_DAILY_CAP_PER_GUILD` | Opsional | `0` | Batas operasi AI **per server** per hari (`0` = tanpa batas) + peringatan 80% ke Admin. |
| `AI_REPLY_CACHE_TTL_SEC` | Opsional | `900` | Umur cache jawaban AI untuk pertanyaan identik, per channel (`0` = cache mati). |
| `AI_REPLY_CACHE_MAX` | Opsional | `200` | Jumlah maksimal entri cache jawaban AI di RAM (hemat memori Free Tier). |
| `AI_USAGE_KEEP_DAYS` | Opsional | `7` | Berapa hari catatan `data/ai_usage.json` disimpan sebelum dipangkas. |
| `REKAP_CACHE_TTL_SEC` | Opsional | `1800` | Umur cache `/ringkas channel` dalam detik (`0` = cache mati). |
| `REKAP_MAX_MESSAGES` | Opsional | `400` | Maksimal pesan yang dianalisis saat membuat rekap berperiode. |
---
| `TWITCH_CLIENT_ID` | Opsional | Kosong | Client ID aplikasi Twitch (gratis) untuk notifikasi *streamer mulai live*. Kosong = fitur Twitch dilewati. |
| `TWITCH_CLIENT_SECRET` | Opsional | Kosong | Client Secret pasangan `TWITCH_CLIENT_ID`. |
| `SOCIAL_CHECK_SEC` | Opsional | `300` | Jeda minimal pemeriksaan feed `/sosial` (detik). Twitch selalu 120 detik. |

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

     | Kelompok | Izin | Dibutuhkan untuk |
     | :--- | :--- | :--- |
     | **Wajib (dasar)** | `View Channels`, `Send Messages`, `Send Messages in Threads`, `Embed Links`, `Attach Files`, `Add Reactions`, `Read Message History` | Chat AI, panel, embed, lampiran |
     | **Ruang privat & tiket** | `Create Public Threads`, `Create Private Threads`, `Manage Threads` | `/sesi`, `/tiket`, thread otomatis |
     | **Moderasi** | `Manage Messages`, `Moderate Members`, `Kick Members`, `Ban Members` | `/mod`, purge, anti-phishing, anti-spam mode `hapus`/`timeout`, `/lockdown` |
     | **Komunitas** | `Manage Roles`, `Manage Channels` | `/autorole`, role hadiah `/level`, reaction role, toko `/ekonomi`, `/serverstats`, `/tempvoice` |
     | **Keamanan lanjutan** | `View Audit Log`, `Manage Webhooks` | `/nuke` (deteksi & pemulihan), `/raid` (mode darurat), pembersihan webhook pelaku |
     | **Analitik** | `Manage Server` *(Manage Guild)* | **`/tumbuh` invite tracker** (membaca daftar invite) |
     | **Musik** | `Connect`, `Speak`, `Move Members` | `/musik` (hanya bila `LAVALINK_URI` diisi) |
     | **Eksternal** | `Use External Emojis` | Emoji kustom di nama channel statistik |

   - **Cara tercepat untuk uji coba di server teman:** centang **`Administrator`** saja dulu
     (bot ini hanya dipakai sendiri/jadi milikmu), lalu persempit izin belakangan setelah
     semua fitur terbukti jalan. Tanpa `Administrator`, pastikan **posisi role bot paling atas**
     agar bisa memberi/mencabut role (`/autorole`, `/level role`, `/ekonomi beli`).
   - Salin URL paling bawah lalu buka di browser untuk mengundang bot ke server Discord Anda.

---

## 🤝 Checklist Uji Coba di Server Orang Lain

Bot ini **multi-server**: satu proses (satu token) bisa dipakai di server kamu **dan** server
temanmu tanpa salinan kedua. Semua data disimpan **per `guild_id`**, jadi pengaturan di servermu
tidak bocor ke server teman (dan sebaliknya).

### Sebelum teman mencoba
| # | Cek | Kenapa penting |
| :---: | :--- | :--- |
| 1 | Versi terbaru sudah **di-merge ke `main`** lalu hosting **di-restart** | Wispbyte menarik kode dari branch `main`; fitur `/log`, `/ekonomi`, `/tumbuh` ada di PR, bukan di `main` lama |
| 2 | **Message Content Intent** & **Server Members Intent** aktif di Developer Portal | Tanpa ini bot tidak bisa membaca chat / menyambut member |
| 3 | Bot diundang dengan scope `bot` + `applications.commands` | Tanpa `applications.commands`, slash command tidak muncul |
| 4 | `DISCORD_GUILD_ID` **dikosongkan** | Kalau diisi, command hanya disinkronkan ke 1 server (servermu saja) |
| 5 | Kuota AI diamankan: `AI_DAILY_CAP_PER_GUILD=300`, `AI_DAILY_CAP_PER_USER=30` | 1 API key Gemini dipakai bersama semua server — jatah Free Tier tetap aman |
| 6 | `DASHBOARD_TOKEN` dikosongkan bila teman tidak perlu akses web | Token dashboard berlaku untuk seluruh bot, bukan per server |

### Yang otomatis terjadi saat bot masuk server baru
- Bot **menyinkronkan Slash Command khusus server itu** (muncul detik itu juga, tidak perlu menunggu ±1 jam propagasi global).
- Bot mengirim **checklist setup 5 langkah** ke channel sistem server tersebut (0 kuota AI).
- Fitur "berat" tetap **NONAKTIF** sampai Admin server itu menyalakannya: `/ekonomi` (mati),
  `anti-spam` (lapor saja), `/level`, `/tiket`, `/starboard`, `/giveaway`, dll.
- Audit Log (`/log`) & `/tumbuh` diam sampai Admin memasang channel-nya (kecuali statistik join/keluar yang ringan).

### Batas yang wajar untuk uji coba bersama
| Sumber daya | Batas realistis |
| :--- | :--- |
| RAM | ±35–55 MB untuk **semua** server sekaligus (bukan per server) |
| Gemini Free Tier | ±250–500 permintaan/hari **total** semua server → pakai cap di atas |
| Voice channel statistik | 2 rename / 10 menit per channel (batas Discord) |
| Musik | 1 node Lavalink dipakai bersama; 1–2 server memutar lagu berbarengan masih aman, lebih dari itu bisa macet |
| Data JSON | Tumbuh per member aktif: `/level` 500 saldo/server, `/ekonomi` 500 saldo/server, `/tumbuh` maks 2000 member/server |

### Kalau ada yang aneh di server teman
1. `/status` → cek latensi, RAM, status AI, & musik.
2. `/tumbuh status` → apakah bot punya izin *Manage Server* (penyebab invite tracker kosong).
3. `/perawatan atur log_channel:#bot-log` → error command otomatis dilaporkan ke channel itu.
4. Command tidak muncul sama sekali → cek scope `applications.commands` saat mengundang; kalau baru saja diundang, tunggu ±1 menit atau restart bot.

---

## 🚀 Panduan Deploy di Wispbyte (Step-by-Step)

1. Masuk ke dashboard **[Wispbyte](https://wispbyte.com)**, lalu buat server baru dengan runtime **Python** (pilih Python 3.11 atau 3.12+).
2. **Cara Paling Praktis (Git Auto-Update — Rekomendasi):**
   - Di tab **Startup** Wispbyte, isi **Git Repo Address** dengan URL repository GitHub Anda, isi **Git Branch** dengan `main` (huruf kecil), nyalakan **Auto Update = ON**, dan matikan **User Uploaded Files = OFF**. Setiap kali Anda klik **Restart**, Wispbyte otomatis menarik versi terbaru dari GitHub!
   - *(Alternatif manual)* Buka menu **Files** di panel Wispbyte, lalu unggah `main.py`, `community_agent.py`, `games.py`, `ai_handler.py`, folder `views/`, folder `cogs/`, `storage.py`, `utils.py`, `config.py`, dan `requirements.txt`.
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

### Berkas data yang dibuat otomatis (tidak perlu disiapkan)

Setelah bot berjalan, folder `data/` terisi sendiri. Tidak ada database, tidak ada Redis —
semuanya JSON kecil yang dipangkas otomatis oleh watcher bawaan.

| Berkas | Dibuat saat | Isi |
| :--- | :--- | :--- |
| `data/settings.json` | bot pertama kali dipakai | channel/role/fitur per server |
| `data/levels.json` | `/level atur aktif:True` | XP, musim level, & prestige |
| `data/tickets.json` | `/tiket panel` | tiket, rating bintang, SLA, aktivitas terakhir |
| `data/antinuke.json` | `/nuke atur` | ambang, whitelist, titik pulih identitas, **status mode beku** |
| `data/raid.json` | `/raid atur` | ambang deteksi & mode raid aktif |
| `data/music_playlists.json` | `/musik playlist simpan` | playlist pribadi member |
| `data/i18n.json` | `/bahasa atur` | bahasa server (ID/EN) |
| `data/prefixes.json` | `/prefix atur` | prefix command per server |
| `data/analytics.json` | `/analitik webhook` | tujuan webhook ekspor CSV (disimpan lokal) |
| `data/ai_usage.json` | otomatis | pemakaian AI harian (dipangkas `AI_USAGE_KEEP_DAYS`) |
| `data/media/` | upload banner | gambar banner/kartu sambutan |

> 🔐 **`data/` berisi pengaturan server** (termasuk URL webhook di `analytics.json`).
> Jangan diunggah ke publik. `.env` dan `data/` memang tidak ikut `/backup struktur`,
> jadi backup struktur aman dibagikan. Untuk **migrasi** server, salin seluruh folder `data/`
> apa adanya lalu restart — semua pengaturan kembali seperti semula.

**Tidak ada dependency baru** untuk fitur v1.28–v1.38 (raid, playlist, rating tiket, musim,
anti-nuke lanjutan, i18n, prefix, ekspor CSV): `requirements.txt` tetap sama karena `aiohttp`
dan `discord.py` sudah dipakai sejak awal. Cukup `git pull` + restart (Auto Update).
6. Jika berhasil, dalam beberapa detik akan muncul log:
   ```text
   ✅ Bot v1.10.0-beta aktif sebagai NamaBot#0000 | Python 3.11+ | discord.py 2.7+ | RAM: ~52.0 MB
   ```
7. Sekarang masuk ke server Discord Anda dan coba:
   - Ketik **`/sesi panel`** di channel panel AI privat.
   - Ketik **`/agent panel`** untuk menyalakan fitur obrolan umum, galeri, digest pagi, maupun FAQ lewat klik tombol!

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

## 📂 Struktur File Proyek (Modular `cogs/`)

```text
ai-discord-chat/
├── main.py             # Entrypoint ringan (Wispbyte Startup File), sinkronisasi tree, & background loop
├── cogs/               # Modul fitur terpisah (siap ekspansi All-in-One)
│   ├── session_cog.py  # Grup /sesi (panel, model, reset, tutup) & perute ruang privat ai-/draw-
│   ├── tools_cog.py    # Grup /ringkas (chat, channel, link), /cari, /bantuan, /status, & 3 Context Menus
│   ├── agent_cog.py    # Grup /agent (panel, status, chat, gallery, persona, welcome, digest, info, dll.)
│   ├── games_cog.py    # Grup /game (mulai 6 mode, papan_skor, stop, reset_skor)
│   ├── server_cog.py   # Grup /serverstats, /autorole, /fakta, & /keamanan (Anti-Phishing, Anti-Spam)
│   ├── community_cog.py# Grup /panel-role, /poll, /ingatkan, /starboard, /verifikasi, /sticky, /info, /perawatan
│   ├── music_cog.py    # Grup /musik (putar, cari, antrean berhalaman, seek, sebelumnya, filter, autoplay, DJ, panel)
│   ├── engagement_cog.py # Grup /giveaway, /ultah, /jawab-otomatis, /pengumuman (tanpa kuota AI)
│   ├── growth_cog.py   # Grup /level (XP, papan peringkat) & /tiket (tiket thread privat)
│   ├── insights_cog.py # Grup /pemakaian (statistik kuota AI) & /faq (jawaban lokal 0 kuota)
│   ├── panel_cog.py    # Grup /panel (dashboard Control Center) & /tampilan (editor tema V2)
│   ├── audit_cog.py    # Grup /log (audit log server)
│   ├── economy_cog.py  # Grup /ekonomi (saldo, harian, toko, transfer, atur)
│   ├── analytics_cog.py# Grup /tumbuh (ringkasan pertumbuhan, Top Inviter, atur)
│   ├── menu_cog.py     # Grup /menu (buat panel, tombol role/link/command, dropdown, kelola)
│   ├── antinuke_cog.py # Grup /nuke (status, atur, whitelist, uji, pulihkan, matikan)
│   ├── events_cog.py   # Event listener terpusat (on_ready, on_message, audit & growth hooks, cleanup)
│   └── helpers.py      # Utilitas bersama antar-modul (proteksi cooldown, izin Admin, pembaca RAM)
├── welcome_media.py    # Penyimpanan banner (data/media/) + perender kartu sambutan dengan Pillow
├── social_notify.py    # Notifikasi YouTube/Twitch/TikTok-RSS (parser feed, template, data/social.json)
├── moderation.py       # Kasus moderasi, peringatan bertingkat, auto-punish (data/moderation.json)
├── temp_voice.py       # Voice room sementara join-to-create (data/temp_voice.json)
├── suggestions.py      # Kotak saran + voting & status (data/suggestions.json)
├── server_tools.py     # AFK, auto-thread, lockdown, & snapshot backup struktur (data/afk.json)
├── backup_restore.py   # Pemulihan struktur dari JSON: validasi, dry-run (plan), & eksekusi aman
├── ui_theme.py         # Tema tampilan per server (aksen, emoji, kepadatan, footer) → data/ui_theme.json
├── ui_kit.py           # Komponen V2 siap pakai (kartu, baris status, progress bar, tombol, konfirmasi)
├── community_agent.py  # Mesin AI Agent Komunitas, Forum Pintar, Persona Sambutan/Perpisahan, Digest, FAQ, & pembersih RAM
├── server_features.py  # Server Stats, Auto Role, Fakta Unik Dunia, & mesin Anti-Phishing lokal
├── community_tools.py  # Reaction Role, Reminder, Starboard, Sticky, Verifikasi, Backup, & Log Error (0 kuota AI)
├── music.py            # Klien Lavalink (wavelink), panel pemutar Rythm (progress bar, filter, autoplay), pengaturan per server
├── engagement.py       # Giveaway, ulang tahun, auto-responder, & pengumuman terjadwal (0 kuota AI)
├── antispam.py         # Penjaga anti-spam & anti-raid ringan (mode bawaan: lapor saja)
├── levels.py           # Sistem level & XP + role hadiah (Rumus 5L²+50L+100)
├── tickets.py          # Tiket dukungan berbasis private thread + transkrip .txt
├── insights.py         # Pencatat pemakaian AI, cache rekap berperiode, & mesin FAQ lokal (0 kuota)
├── audit_log.py        # Audit log server: hapus/edit pesan, member, role, channel, voice (data/audit.json)
├── economy.py          # Ekonomi koin: pesan, voice, hadiah harian ber-streak, toko role (data/economy.json)
├── growth_tracker.py   # Invite tracker + statistik pertumbuhan & retensi member (data/growth.json)
├── menu_builder.py     # Menu Builder: panel tombol/dropdown role, link, & command (data/menus.json)
├── antinuke.py         # Anti-Nuke: deteksi audit log, tindakan bertingkat, & pemulihan (data/antinuke.json)
├── raid_guard.py       # Raid Guard: mode darurat otomatis saat lonjakan join (data/raid.json)
├── music_playlists.py  # Playlist musik per member (data/music_playlists.json)
├── i18n.py             # Terjemahan teks kerangka ID/EN per server (data/i18n.json)
├── prefixes.py         # Prefix command teks per server (data/prefixes.json)
├── analytics_export.py # Ekspor CSV (level/moderasi/tiket/pemakaian) & kirim webhook (data/analytics.json)
├── memory_audit.py     # Audit RAM, ukuran data/, & jumlah entri cache (/perawatan memori)
├── games.py            # Mesin 6 Mode Mini-Game Tongkrongan AI & Papan Skor server
├── ai_handler.py       # Klien async Gemini API (Chat, Vision, PDF, Voice Note, YouTube/Web, & Live Search)
├── views/              # Paket komponen UI (dipecah agar tiap berkas tetap ringkas)
│   ├── __init__.py     # Re-export semua view: `from views import X` tetap bekerja
│   ├── session.py      # Panel & tombol ruang AI privat (/sesi): panel utama, persona, gambar, model
│   ├── agent.py        # /agent panel & /agent status (kartu V2, toggle berwarna), pengelola FAQ
│   ├── music.py        # Panel pemutar ala Rythm, antrean berhalaman, panel musik V2
│   ├── tickets.py      # Panel tiket persisten + tombol klaim/tutup di thread
│   ├── community.py    # Gerbang verifikasi & tombol "Tandai Selesai" forum
│   ├── engagement.py   # Tombol ikut/batalkan giveaway
│   └── help.py         # Menu /bantuan klasik & panel panduan V2 (11 kategori)
├── storage.py          # Penyimpanan sesi privat JSON atomik & auto-recovery dari Discord Thread
├── utils.py            # Pemotong kode Markdown, Live Web/News Search gratis, SSRF guard, & jam lokal
├── config.py           # Konfigurasi variabel .env, daftar 5 kepribadian Gemini, gaya & rasio gambar
├── requirements.txt    # Daftar dependensi Python super ringan
├── .env.example        # Template contoh pengisian variabel .env
├── .gitignore          # Mencegah file rahasia (.env) & folder data sesi ikut ter-commit ke Git
├── docs/               # Dokumentasi panjang (dipisah dari README)
│   ├── fitur.md        # Penjelasan lengkap 23 area fitur (A–W) + batas cache & RAM
│   ├── command.md      # Referensi 53 command utama, subcommand, & tombol panel
│   └── catatan-dashboard-dan-kunci-api.md  # Rencana dashboard/BYOK yang masih diparkir
├── site/               # Situs dokumentasi statis (Hugo + tema Lotus Docs, deploy Vercel)
│   ├── hugo.toml       # Konfigurasi situs: params.docs, pencarian, warna tema
│   ├── vercel.json     # Setelan build Vercel (Hugo 0.169.0, output public)
│   ├── data/landing.yaml  # Halaman depan: hero + 6 kartu fitur
│   └── content/        # HASIL GENERATE dari docs/ — jangan diedit manual
├── tools/
│   └── sync_docs.py    # docs/*.md → site/content/ (juga dipakai tes sinkronisasi)
├── LICENSE             # Lisensi Open-Source MIT
└── tests/              # Pengujian otomatis (pytest — 149 test) untuk memastikan seluruh modul bebas bug
```

---

## ❓ FAQ & Solusi Masalah Umum

- **Apakah semua fitur (termasuk `/cari` berita, rangkum YouTube, & buat gambar) aman untuk akun Gemini *Free Tier* tanpa kartu kredit?**
  **100% aman & langsung jalan!** Secara default (`GEMINI_PAID_SEARCH_ENABLED=false` dan `GEMINI_PAID_IMAGE_ENABLED=false`), bot menggunakan mesin pencari web/berita gratis mandiri dan generator gambar Flux gratis sehingga bebas dari error `You exceeded your current quota`.
- **Apakah bot bisa dipakai di dalam Channel Forum Discord (`Forum Channel`)?**
  **Bisa penuh!** Anda tinggal memilih nama Channel Forum pada parameter `channel:` saat menjalankan `/agent panel`, `/agent chat`, `/agent gallery`, `/agent youtube`, atau `/agent cari`. Bot akan otomatis membaca **Judul Postingan, Tag Forum, isi teks, gambar, PDF, Voice Note, maupun file kode** di setiap postingan forum tersebut tanpa mencampur ingatan antar-postingan (serta mendukung `/ringkas chat`, `/ringkas link`, `/cari`, `/game`, dan tekan-tahan pesan *Apps* di dalam postingan forum).
- **Kenapa bot diam atau menolak saat ada member kirim link YouTube / ketik `/cari` di channel publik?**
  Fitur YouTube dan Pencarian Web kini diatur **per-channel** agar rapi dan tidak mengganggu obrolan warga di sembarang tempat. Pastikan Admin sudah mengaktifkan channel tersebut lewat **`/agent panel`** (atau `/agent youtube` / `/agent cari`). Di channel YouTube yang aktif dengan `auto_di_channel:False` (default), cukup **panggil nama akrab bot / `@mention` / *reply*** bersama link tersebut atau gunakan **`/ringkas link`**. *(Jika ingin bot otomatis merangkum setiap link di channel khusus, gunakan `auto_di_channel:True`).*
- **Slash Commands (`/sesi`, `/ringkas`, `/agent`) belum muncul atau tampilannya belum ter-update di HP?**
  Isi `DISCORD_GUILD_ID` di `.env` dengan ID Server Discord Anda agar sinkronisasi instan (<1 detik), lalu *restart* bot. Jika memakai aplikasi Discord di HP (Android/iOS), **tutup paksa (*force close*) lalu buka ulang aplikasi Discord sekali** agar cache tampilan *Slash Command* di HP diperbarui.
- **Pemecah Sepi (`menit_sepi`) belum menyapa saat dites malam hari?**
  Secara default fitur **Jam Tenang Malam (23:00 – 06:00)** aktif agar AI tidak membangunkan warga saat jam tidur. Jika Anda sedang mengetes di atas jam 23:00 malam, matikan sementara dengan `/agent persona jam_tenang_malam:False` atau gunakan `/agent sapa` untuk tes instan. Anda juga bisa mengecek sisa hitung mundur lewat `/agent status`.
- **Bot online tapi tidak merespons pesan teks di ruang chat?**
  Pastikan **Message Content Intent** sudah dinyalakan di [Discord Developer Portal](https://discord.com/developers/applications) pada bagian *Bot → Privileged Gateway Intents*, lalu *restart* bot di Wispbyte.
- **Apakah Anti-Phishing butuh API key atau layanan berbayar?**
  **Tidak.** Pemeriksaan berjalan **lokal tanpa biaya**: pencocokan domain tiruan brand populer, punycode `xn--`, IP langsung, TLD berisiko, pemendek URL, trik `@`, dan daftar hitam domain phishing. Aktifkan dengan `/keamanan phising aktif:True` (butuh izin **Manage Messages** untuk menghapus pesan).
- **Kenapa Voice Channel statistik tidak berubah setiap detik?**
  Discord hanya mengizinkan **2 rename per 10 menit per channel**, jadi bot memperbarui tiap ±10 menit (bisa diubah lewat `SERVERSTATS_UPDATE_SEC`, minimum `600`). Ini sengaja agar akun bot tidak kena rate limit.
- **Bagaimana cara membuat persona sambutan berbeda dari gaya obrolan AI?**
  Persona sambutan punya pengaturan sendiri: `/agent welcome persona:lucu` atau `/agent goodbye persona:hangat`. Mengubah `/agent persona gaya_bahasa:gaul` (gaya obrolan harian) **tidak memengaruhi** gaya sambutan, dan sebaliknya.
- **Gagal membuat ruang privat (`Missing Permissions`)?**
  Pastikan Role bot di channel tersebut memiliki izin `Create Private Threads`, `Send Messages in Threads`, dan `Read Message History`.

---

## 📄 Lisensi

Proyek ini dirilis menggunakan **[MIT License](LICENSE)** — bebas digunakan, dipelajari, dan dikembangkan dengan tetap mencantumkan atribusi pembuat asli.
