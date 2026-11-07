# 🔍 Bedah 6 Bot Pembanding & Fitur yang Layak Diambil

> **Status: riset & rencana** — belum ada kode yang diubah. Dokumen ini memetakan
> apa yang dipakai bot besar, apa yang **sudah** kita punya, dan apa yang layak ditambah
> tanpa melanggar prinsip proyek (1 proses, JSON, tanpa dependency baru, tanpa JavaScript).
>
> Terakhir diperbarui: v1.40.0-beta

Sumber yang dibaca: [arclo.gg](https://arclo.gg/), [axis.cmds.media](https://axis.cmds.media/),
[wisp (top.gg)](https://top.gg/bot/973958601616015380), [admibot.xyz](https://admibot.xyz/),
[bytemate.me](https://bytemate.me/), [breed.rip](https://breed.rip/).

## 1. Ringkasan: apa yang membuat tiap bot dipakai

| Bot | Skala | Kekuatan yang menonjol | Catatan untuk kita |
| :--- | :--- | :--- | :--- |
| **Arclo** | 3.000+ server | 50+ sistem, **satu dashboard per sistem**, satu "jalur hukuman" (moderasi & filter berbagi case number), automod 36 filter + **penguji aturan** + honeypot, tiket dengan **transkrip yang bisa dicari di browser**, **kartu rank yang didesain di browser (preview = output)**, giveaway dengan syarat yang benar-benar menggating + log reroll, achievements, tags, threat level | Paling relevan: semua bisa ditiru **tanpa** dependency baru. Fokus utama kita. |
| **Axis** | 448 server | **Halaman publik per server** + vanity, integrasi YouTube/Reddit/Steam, custom command, notifikasi sederhana | Integrasi RSS (Reddit/YouTube) & halaman publik = kandidat; halaman publik perlu keputusan privasi. |
| **wisp** | 2.100+ command | Keluasan modul: prison/softban/hardban, **fake permissions**, anti-bot, forced nickname, auto-reaction, AutoPFP, **confessions**, **highlights** (kata kunci → DM), **snipe/edit-snipe**, skullboard/clownboard, ekonomi dalam (saham, crypto, gambling), profil game, last.fm, esports | Ambil yang **kecil & berdampak**: highlights, confessions, snipe, varian board. Lewati yang berat. |
| **AdmiBot** | — | Chatbot AI gratis, musik, welcome/farewell, tiket, keamanan + **CAPTCHA**, automasi & logging, **Minecraft RCON**, game klasik, level + kartu rank | CAPTCHA & game klasik layak; RCON tidak (port & kredensial baru). |
| **ByteMate** | 600+ kreator | Fokus Twitch: command, alert, giveaway, **overlay OBS**, watchtime, klip, statistik | Overlay butuh halaman publik → bertabrakan dengan model satu token. Lewati dulu. |
| **breed** | baru (0 server) | Isi standar (moderasi ber-case ID, level, musik, tiket) tapi **presentasinya rapi**: setiap fitur punya contoh nyata | Pelajaran: dokumentasi & contoh lebih penting daripada jumlah fitur. |

**Kesimpulan singkat:** keunggulan mereka **bukan** jumlah fitur, melainkan
(1) **kedalaman** tiap fitur, (2) **satu tempat** untuk mengatur & menguji, dan
(3) **bukti kerja** (case number, transkrip, log, statistik). Kita sudah punya semua
fondasinya — yang kurang adalah kedalaman dan bukti.

## 2. Fitur yang SUDAH kita punya → apa yang perlu dimaksimalkan

Kolom **Paket** menunjuk ke roadmap di bagian 5.

| Fitur kita | Keadaan sekarang | Punya mereka | Yang perlu ditambah | Paket |
| :--- | :--- | :--- | :--- | :---: |
| **Giveaway** | 1 syarat: `role_id`. Tombol ikut, auto-end, reroll | Syarat **level, role, umur akun** dicek saat menekan; **extra entry** untuk booster; **log siapa yang dapat lebih dulu**; **template + jadwal** | Syarat berlapis + extra entry + log reroll + template | **A** |
| **Tiket** | Thread/channel, klaim staf, SLA, rating bintang, transkrip `.txt` | **Transkrip HTML yang bisa dicari di browser**, topik per tombol, catatan internal, builder 10 tab | Transkrip HTML di dashboard + pencarian + catatan internal | **A** |
| **Level** | XP pesan & voice, role reward, musim, prestige, papan peringkat **embed** | **Kartu rank PNG**, didesain di browser dan **preview-nya adalah hasil aslinya**; multiplier per channel/role; pilihan kurva XP | Kartu rank PNG (Pillow sudah ada) + pratinjau di dashboard + multiplier | **A** |
| **Automod / anti-spam** | Spam rate, invite, link, caps, anti-raid, mode "lapor" | 36 filter, **penguji aturan** di dashboard, **honeypot**, slowmode otomatis, hitungan per aturan | Penguji aturan + honeypot + statistik per aturan | **B** |
| **Moderasi** | Kasus bernomor, warn → auto-punish, timeout/kick/ban/purge/slowmode | `/report`, **antrean banding**, tempban/softban, catatan (note), **statistik staf**, halaman moderasi di dashboard | Laporan + banding + tempban/softban/note + statistik staf + halaman dashboard | **B** |
| **Sambutan / pamit / boost** | Kartu statis & dinamis, DM, persona, bahasa, arti | **Role boost yang bisa diklaim**, information channel | Klaim role booster + information channel | **D** |
| **Starboard** | Satu papan, ambang bintang | **Skullboard / clownboard** terpisah | Varian papan kedua & ketiga | **A** |
| **Statistik channel** | Member, boost, dll. | Member, role, boost, **tiket**, **pengikut sosial** | Tambah sumber angka tiket & sosial | **D** |
| **Notifikasi sosial** | YouTube, Twitch, TikTok/RSS | **14 platform** satu mesin | Tambah Reddit & RSS generik (tanpa API key) | **D** |
| **Formulir (modal)** | Buat & kirim formulir | **Antrean submission** yang direview | Daftar kiriman + status di dashboard | **D** |
| **Dashboard** | 12 halaman, 55 setelan, 13 tes, auto-refresh | Tiap sistem punya **halaman + statistik sistem** ("Caught today", "Cases 30 days") | Kartu statistik per halaman grup | **B** |

## 3. Fitur BARU yang layak diambil

Semua di bawah ini **tidak butuh dependency baru** dan tetap JSON + 1 proses.

| Fitur | Sumber | Kenapa layak | Effort | Dampak | Paket |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Tags** (`/tag buat/lihat/hapus`) | Arclo | Jawaban server disimpan sekali, dipanggil kapan saja — pengganti FAQ manual, sangat sering dipakai | S | ★★★ | **C** ✅ v1.40 |
| **Achievements** (badge bertingkat + role reward + papan sendiri) | Arclo | Memberi alasan **kembali** selain level; bisa memakai data yang sudah kita catat | M | ★★★ | **C** ✅ v1.40 |
| **Highlights** (kata kunci → DM) | wisp | Sangat murah, langsung terasa: orang tidak perlu membaca seluruh channel | S | ★★★ | **C** ✅ v1.40 |
| **Confessions** (anonim + moderasi) | wisp | Kanal engagement klasik; moderasi tetap jalan lewat antispam | S | ★★ | **C** ✅ v1.40 |
| **Snipe / EditSnipe** | wisp | Kecil, lucu, berguna untuk staf | S | ★★ | **C** ✅ v1.40 |
| **Honeypot + penguji aturan** | Arclo | Menangkap self-bot yang lolos dari filter kata; penguji membuat staf berani mengubah aturan | M | ★★★ | **B** ✅ v1.40 |
| **`/report` + antrean banding** | Arclo, wisp | Tanpa ini, moderasi kita satu arah: member tidak punya jalur resmi | M | ★★★ | **B** ✅ v1.40 |
| **tempban / softban / note** | wisp | Melengkapi tangga hukuman yang sudah ada | S | ★★ | **B** ✅ v1.40 |
| **Kartu rank PNG** | Arclo, AdmiBot | Kartu level yang bisa dibanggakan; Pillow sudah dipakai untuk kartu sambutan | M | ★★★ | **A** ✅ v1.40 |
| **Voice linking** | Arclo | Role + chat privat otomatis selama di voice | S | ★★ | **D** ✅ v1.40 |
| **Information channel** | Arclo | Channel baca-saja berisi aturan & info, disegarkan sendiri | S | ★★ | **D** ✅ v1.40 |
| **Reddit / RSS generik** | Axis | Sumber konten baru tanpa API key | S | ★★ | **D** ✅ v1.40 |
| **CAPTCHA verifikasi** | AdmiBot | Gerbang verifikasi kita masih tombol; CAPTCHA menahan bot yang lebih rajin | M | ★★ | **D** ✅ v1.40 |
| **Halaman publik server** | Axis | Keren, tapi membuka data ke publik | M | ★ | — (butuh keputusan) |

## 4. Yang **tidak** kita ambil (dan alasannya)

| Fitur mereka | Alasan tidak diambil |
| :--- | :--- |
| Prison / darkshop / saham / crypto / gambling | Bukan posisi bot ini; menambah ratusan baris kode, risiko penyalahgunaan, dan beban data tanpa menambah kuota komunitas. |
| Marriage / keluarga / RP | Meta sosial yang sangat spesifik; jarang dipakai server yang bot ini layani. |
| Profil game (Steam, Roblox, Valorant, …) & Last.fm | Butuh API key pihak ketiga untuk tiap layanan — bertabrakan dengan "tanpa dependency/API baru". |
| Minecraft RCON | Membuka port & kredensial baru di host; risiko keamanan lebih besar dari manfaatnya. |
| Overlay OBS (ByteMate) | Butuh halaman **publik tanpa token**; bertabrakan dengan model satu token dashboard. |
| AI moderation lokal (Arclo) | Kita sudah memakai Gemini; menjalankan model lokal menambah RAM di luar Free Tier. "AI review" per pesan juga mahal kuota. |
| Esports / turnamen | Kebutuhan sempit, jauh dari fokus komunitas umum. |

## 5. Roadmap 4 paket (urutan yang disarankan)

### Paket A — Maksimalkan yang sudah ada *(paling berdampak, risiko paling kecil)*

1. **Giveaway berlapis** — syarat level / umur akun / role, extra entry booster, log reroll
   (siapa dapat lebih dulu), simpan sebagai **template** dan bisa dijadwalkan.
   ✅ **Sudah jalan** (v1.40): syarat berlapis + alasan penolakan spesifik, bobot peluang
   role bonus, log peserta & riwayat undian, template per server, setelan bawaan, dan
   halaman dashboard `/giveaway` (buat, hentikan, undi ulang, tes syarat).
2. **Tiket lebih dalam** — transkrip **HTML** yang bisa dibuka & dicari dari dashboard,
   catatan internal staf, lebih dari satu topik per panel.
   ✅ **Sudah jalan** (v1.40): transkrip HTML + `.txt` diarsipkan otomatis tiap tiket
   ditutup (command, dashboard, atau auto-close) dan bisa **dicari dari dashboard**
   (`/transkrip`, dicari di isi percakapan), **catatan internal staf** (command & dashboard),
   serta **beberapa topik per panel** (`/tiket topik` + pengelola di halaman `/tiket`):
   dropdown topik, role staf per topik, thread `tiket-<topik>-<nama>`, maks 8 topik/server.
3. **Kartu rank PNG** — dirender server (Pillow) dari data level yang sudah ada, dengan
   **pratinjau di dashboard yang memakai perender yang sama**.
   ✅ **Sudah jalan** (v1.40): `/level kartu` + pratinjau `GET /api/rank.png` lewat modul
   `rank_card.py` yang sama, latar bisa diunggah, warna aksen + sakelar + tombol tes di
   halaman Inti & level.
4. **Starboard varian** — board kedua/ketiga dengan emoji & ambang sendiri.
   ✅ **Sudah jalan** (v1.40): `/starboard varian` + panel *Papan sorotan varian* di
   halaman Konten & interaksi — tiap papan punya emoji, ambang, channel, & warna embed
   sendiri (maks 4 papan/server), angka sorotan diperbarui otomatis.

Berkas: `engagement.py` · `tickets.py` · `levels.py` · `community_tools.py` ·
`dashboard_*.py` · `cogs/*_cog.py` · tes baru per fitur.

### Paket B — Automod & moderasi setara Arclo

1. **Penguji aturan** di halaman Keamanan: tempel teks → lihat aturan mana yang kena, tanpa
   menghapus apa pun dan tanpa menghukum siapa pun.
   ✅ **Sudah jalan** (v1.40): panel *Penguji aturan & statistik* (`antispam.uji_aturan` +
   `dashboard_keamanan.py`), 5 aturan disimulasikan, hasil terakhir tersimpan per server.
2. **Honeypot**: channel yang tidak boleh diposting siapa pun; siapa pun yang memposting
   langsung ditindak (self-bot & skrip raid tidak membaca aturan).
   ✅ **Sudah jalan** (v1.40): `/keamanan honeypot` + modul `honeypot.py` (maks 3 channel,
   aksi lapor/hapus/timeout/kick/ban, staf & bot aman) + panel & penguji simulasi di
   halaman Keamanan, tersimpan di `data/honeypot.json`.
3. **Statistik per aturan** ("kena hari ini / total") di halaman Keamanan.
   ✅ **Sudah jalan** (v1.40): penghitung `stats` per aturan di `data/antispam.json`,
   reset harian otomatis, ditampilkan di panel yang sama dengan penguji aturan.
4. **`/report` + antrean banding** di dashboard.
   ✅ **Sudah jalan** (v1.40): `/lapor` & `/banding` (termasuk dari DM) + antrean staf
   (`/mod antrean`, `/mod tindak`) + panel antrean di halaman **🚨 Moderasi**;
   data di `data/reports.json`.
5. **tempban / softban / note** + **statistik staf** (siapa menindak berapa banyak).
   ✅ **Sudah jalan** (v1.40): `/mod tempban` (dicabut otomatis oleh watcher 15 detik),
   `/mod softban`, `/mod note`, `/mod statistik` + `moderation.staff_stats()` dan
   `moderation.search_cases()` untuk papan & pencarian kasus.
6. **Halaman Moderasi** di dashboard (kasus terakhir, cari nomor kasus, statistik staf).
   ✅ **Sudah jalan** (v1.40): halaman **🚨 Moderasi** (`dashboard_moderasi.py`) berisi
   antrean laporan/banding, setelan jalur laporan, temp-ban + tombol cabut, pencarian
   kasus (nomor/ID/kata/jenis), statistik staf 30 hari, & kasus terbaru.

Berkas: `antispam.py` · `moderation.py` · `cogs/moderation_cog.py` ·
`web_dashboard.py` (+ halaman `moderasi`) · `dashboard_admin.py` · tes.

### Paket C — Fitur baru kecil yang berdampak

1. **Tags** (`/tag`) + kelola di dashboard.
2. **Achievements** (chat/voice/giveaway, bertingkat, role reward, papan sendiri).
   ✅ **Sudah jalan** (v1.40): modul `achievements.py` (4 lencana × 3–5 tingkat dari data
   pesan/voice/level/undian yang sudah ada, role hadiah per tingkat, papan sendiri,
   maks 500 member/server) + `/lencana lihat|papan|periksa|atur|role` + panel
   *🏅 Lencana bertingkat* di halaman **Inti & level** + tombol uji simulasi.
   Pemberian lencana menempel di alur XP pesan & voice — 0 kuota AI, tanpa proses latar baru.
3. **Highlights** (kata kunci → DM, abaikan channel & kata yang dipilih).
   ✅ **Sudah jalan** (v1.40): modul `highlights.py` + `/pantau tambah|hapus|daftar|abaikan|
   bersihkan|atur` + listener di `cogs/events_cog.py` (maks 10 kata kunci/member, pencocokan
   batas kata, jeda 5 menit per kata, batas DM/menit, tanpa menyimpan isi pesan) + panel
   *🔔 Highlight kata kunci* di halaman Konten & interaksi + tombol uji simulasi.
4. **Confessions** (channel anonim, moderasi lewat antispam).
   ✅ **Sudah jalan** (v1.40): modul `confessions.py` (maks 300 curhat/server, 10–900 huruf,
   3/jam per hash penulis, jeda bawaan 5 menit, **tanpa menyimpan isi curhat**) +
   `/curhat kirim|atur|hapus` + panel *💌 Curhat anonim* di halaman Konten & interaksi +
   tombol uji simulasi; blokir tautan opsional, identitas penulis hanya hash 12 huruf.
5. **Snipe / EditSnipe**.
   ✅ **Sudah jalan** (v1.40): modul `snipe.py` (memori saja, maks 5 pesan/channel, 300 channel)
   + `/snipe hapus|edit|atur` (izin *Manage Messages*) + panel *🔎 Snipe & EditSnipe* di halaman
   Moderasi + tombol uji simulasi yang membersihkan datanya sendiri.

Berkas: modul baru (`tags.py`, `achievements.py`, `highlights.py`, `confessions.py`) +
cog baru + entri dashboard + docs + tes.
Sudah ada: `tags.py` + `cogs/tags_cog.py` + `dashboard_tags.py` (C#1),
`achievements.py` + `cogs/lencana_cog.py` + `dashboard_lencana.py` (C#2),
`highlights.py` + `cogs/highlights_cog.py` + `dashboard_highlights.py` (C#3),
`confessions.py` + `cogs/confessions_cog.py` + `dashboard_curhat.py` (C#4),
`snipe.py` + `cogs/snipe_cog.py` + `dashboard_snipe.py` (C#5).

### Paket D — Integrasi & pelengkap

1. **Reddit/RSS generik** (tanpa API key) di mesin notifikasi sosial yang sudah ada.
   ✅ **Sudah jalan** (v1.40): platform **👽 Reddit** (`.rss` resmi, parser Atom sendiri) &
   **📰 RSS/Atom** umum di `social_notify.py` (`normalize_subreddit`, `feed_url`,
   `parse_reddit_feed`) sehingga `/sosial` langsung punya 5 platform, plus panel
   *🔔 Notifikasi sosial* di halaman Konten & interaksi (tambah/hapus langganan) dan
   tombol tes yang **tidak memanggil jaringan**.
2. **Voice linking** (role + chat privat selama di voice).
   ✅ **Sudah jalan** (v1.40): modul `voice_link.py` + `/tempvoice tautkan` —
   role diberikan saat masuk voice (hanya jika belum dimiliki) + channel `⌨️-<nama voice>`
   dengan izin per member, dicabut otomatis saat keluar, channel dihapus bila kosong
   (maks 40/server) + panel *🔗 Voice linking* di halaman Konten & interaksi + tombol tes
   simulasi. Sekaligus memperbaiki bug lama: **dua listener `on_voice_state_update` saling
   menimpa**, sehingga pembuatan room Temp Voice bisa mati; kini satu listener di
   `cogs/events_cog.py` memanggil XP voice, audit log, Temp Voice, dan voice linking.
3. **Information channel** (aturan & info, disegarkan sendiri).
   ✅ **Sudah jalan** (v1.40): modul `info_channel.py` + `/kanal-info atur|isi|segarkan|status`
   — satu pesan embed yang **diedit**, bukan dikirim ulang (diterbitkan ulang otomatis bila
   pesan hilang), interval verifikasi 5–1440 menit, maks 3500 huruf + panel *ℹ️ Channel info
   otomatis* di halaman Konten & interaksi + tombol tes yang tidak mengedit apa pun.
4. **CAPTCHA verifikasi** (kode teks/gambar, tanpa dependency baru).
   ✅ **Sudah jalan** (v1.40): CAPTCHA **teks** di `community_tools.py` (kode 5 huruf tanpa
   0/O/1/I/L, TTL 5 menit, 3 percobaan, hanya di memori) + modal Discord di
   `views/community.py` + `/verifikasi pasang … captcha:True` + sakelar *CAPTCHA verifikasi*
   di halaman Keamanan + tombol tes yang tidak memberi role.
5. **Antrean submission formulir** di dashboard.
   ✅ **Sudah jalan** (v1.40): `modal_forms.py` menyimpan setiap jawaban ke antrean
   (`data/forms.json` → `inbox`, maks 200/server, dibersihkan setelah 30 hari, label kolom
   asli, status baru/selesai + pencatat penanganan) + panel *📬 Kotak masuk formulir* di
   halaman Buat konten + tombol tes yang tidak membuat submission.
6. **Statistik channel**: tambah angka tiket & pengikut sosial.

## 6. Prinsip yang tetap dijaga di semua paket

| Prinsip | Artinya untuk fitur baru |
| :--- | :--- |
| **Tanpa dependency baru** | Pillow & aiohttp yang sudah ada; CAPTCHA/PNG pakai Pillow, RSS pakai `xml.etree` |
| **Tanpa JavaScript** | Form HTML biasa, `meta refresh`, tombol tes per fitur |
| **1 proses, JSON** | Semua data di `data/*.json`, tanpa Redis/DB |
| **Dashboard mengatur semua fitur** | Tiap fitur baru wajib muncul sebagai setelan/halaman (aturan #72) |
| **Bisa diuji** | Tombol tes per fitur bila bermakna; subjek = pemilik server |
| **Dokumentasi ikut** | `docs/fitur.md` + `site/content` lewat `tools/sync_docs.py`, tes tautan |
| **Tanpa naik versi** | Versi tetap `v1.40.0-beta` sampai owner memutuskan |

## 7. Rekomendasi

Mulai dari **Paket A** (memaksimalkan yang sudah ada) karena:

- Tidak menambah permukaan fitur baru → risiko bug kecil, dokumentasi tidak meledak.
- Langsung terasa di server nyata: giveaway yang benar-benar menggating peserta, transkrip
  tiket yang bisa dicari, kartu rank yang bisa dipamerkan.
- Semuanya bisa masuk ke dashboard yang sudah ada (5 grup setelan) dengan menambah satu
  halaman fitur per kebutuhan (giveaway sudah dapat halaman `/giveaway`).

**Paket B** menyusul karena menyentuh keamanan — perlu tes paling hati-hati.
**Paket C** paling menyenangkan untuk engagement harian, dan bisa dicicil satu fitur per PR.
**Paket D** terakhir karena bergantung pada pihak ketiga atau keputusan privasi.
