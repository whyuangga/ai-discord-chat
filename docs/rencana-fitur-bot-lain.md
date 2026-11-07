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
| **Dashboard** | 10 halaman, 52 setelan, 9 tes, auto-refresh | Tiap sistem punya **halaman + statistik sistem** ("Caught today", "Cases 30 days") | Kartu statistik per halaman grup | **B** |

## 3. Fitur BARU yang layak diambil

Semua di bawah ini **tidak butuh dependency baru** dan tetap JSON + 1 proses.

| Fitur | Sumber | Kenapa layak | Effort | Dampak | Paket |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Tags** (`/tag buat/lihat/hapus`) | Arclo | Jawaban server disimpan sekali, dipanggil kapan saja — pengganti FAQ manual, sangat sering dipakai | S | ★★★ | **C** |
| **Achievements** (badge bertingkat + role reward + papan sendiri) | Arclo | Memberi alasan **kembali** selain level; bisa memakai data yang sudah kita catat | M | ★★★ | **C** |
| **Highlights** (kata kunci → DM) | wisp | Sangat murah, langsung terasa: orang tidak perlu membaca seluruh channel | S | ★★★ | **C** |
| **Confessions** (anonim + moderasi) | wisp | Kanal engagement klasik; moderasi tetap jalan lewat antispam | S | ★★ | **C** |
| **Snipe / EditSnipe** | wisp | Kecil, lucu, berguna untuk staf | S | ★★ | **C** |
| **Honeypot + penguji aturan** | Arclo | Menangkap self-bot yang lolos dari filter kata; penguji membuat staf berani mengubah aturan | M | ★★★ | **B** |
| **`/report` + antrean banding** | Arclo, wisp | Tanpa ini, moderasi kita satu arah: member tidak punya jalur resmi | M | ★★★ | **B** |
| **tempban / softban / note** | wisp | Melengkapi tangga hukuman yang sudah ada | S | ★★ | **B** |
| **Kartu rank PNG** | Arclo, AdmiBot | Kartu level yang bisa dibanggakan; Pillow sudah dipakai untuk kartu sambutan | M | ★★★ | **A** |
| **Voice linking** | Arclo | Role + chat privat otomatis selama di voice | S | ★★ | **D** |
| **Information channel** | Arclo | Channel baca-saja berisi aturan & info, disegarkan sendiri | S | ★★ | **D** |
| **Reddit / RSS generik** | Axis | Sumber konten baru tanpa API key | S | ★★ | **D** |
| **CAPTCHA verifikasi** | AdmiBot | Gerbang verifikasi kita masih tombol; CAPTCHA menahan bot yang lebih rajin | M | ★★ | **D** |
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
4. **Starboard varian** — board kedua/ketiga dengan emoji & ambang sendiri.

Berkas: `engagement.py` · `tickets.py` · `levels.py` · `community_tools.py` ·
`dashboard_*.py` · `cogs/*_cog.py` · tes baru per fitur.

### Paket B — Automod & moderasi setara Arclo

1. **Penguji aturan** di halaman Keamanan: tempel teks → lihat aturan mana yang kena, tanpa
   menghapus apa pun dan tanpa menghukum siapa pun.
2. **Honeypot**: channel yang tidak boleh diposting siapa pun; siapa pun yang memposting
   langsung ditindak (self-bot & skrip raid tidak membaca aturan).
3. **Statistik per aturan** ("kena hari ini / total") di halaman Keamanan.
4. **`/report` + antrean banding** di dashboard.
5. **tempban / softban / note** + **statistik staf** (siapa menindak berapa banyak).
6. **Halaman Moderasi** di dashboard (kasus terakhir, cari nomor kasus, statistik staf).

Berkas: `antispam.py` · `moderation.py` · `cogs/moderation_cog.py` ·
`web_dashboard.py` (+ halaman `moderasi`) · `dashboard_admin.py` · tes.

### Paket C — Fitur baru kecil yang berdampak

1. **Tags** (`/tag`) + kelola di dashboard.
2. **Achievements** (chat/voice/giveaway, bertingkat, role reward, papan sendiri).
3. **Highlights** (kata kunci → DM, abaikan channel & kata yang dipilih).
4. **Confessions** (channel anonim, moderasi lewat antispam).
5. **Snipe / EditSnipe**.

Berkas: modul baru (`tags.py`, `achievements.py`, `highlights.py`, `confessions.py`) +
cog baru + entri dashboard + docs + tes.

### Paket D — Integrasi & pelengkap

1. **Reddit/RSS generik** (tanpa API key) di mesin notifikasi sosial yang sudah ada.
2. **Voice linking** (role + chat privat selama di voice).
3. **Information channel** (aturan & info, disegarkan sendiri).
4. **CAPTCHA verifikasi** (kode teks/gambar, tanpa dependency baru).
5. **Antrean submission formulir** di dashboard.
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
