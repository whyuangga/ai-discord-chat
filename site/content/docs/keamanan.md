---
title: "C. Fitur Keamanan, Ketahanan & Performa"
description: "Moderasi bercatatan, raid guard, perkakas server, pemulihan struktur, sampai anti-503."
icon: "shield"
weight: 3
toc: true
---

## 1. 🛡️ Moderasi Bercatatan (`/mod`) — Warn, Timeout, Kick, Ban, Purge

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

## 1b. 🚨 Jalur member: `/lapor` & `/banding`

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

## 2. 🚨 Raid Guard — Mode Darurat Otomatis (`/raid`)

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

## 3. 🧰 Perkakas Server: AFK, Thread Otomatis, Lockdown & Backup Struktur

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
- **Lockdown tidak tersimpan di disk** — kalau bot restart saat lockdown, jalankan `/lockdown aktif aktif:False` lalu periksa manual. Ini disengaja agar tidak ada "kunci hantu".
- **Backup bersifat baca-saja**: bot **tidak** akan membuat/menghapus channel dari berkas itu, jadi tidak ada risiko server rusak karena salah klik.
- Auto-thread otomatis berhenti membuat thread bila bot kehilangan izin *Create Public Threads* (hanya dicatat di log).

## 4. ♻️ Pemulihan Struktur Server (`/backup pratinjau`, `/backup pulihkan`)

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
- **Maksimal 30 item per pemulihan** (agar aman dari rate limit Discord) — jalankan ulang untuk sisanya.
- **Overwrite per-member dilewati** (ID member berbeda di server lain); izin **per-role** tetap diterapkan berdasarkan nama role.
- Tipe yang belum didukung (`forum`, `media`) dilaporkan sebagai "dilewati", bukan error.
- Setiap pemulihan tercatat di **Audit Log** (`/log`) dan bisa dibatalkan manual bila hasilnya tidak sesuai.
- Berkas divalidasi: harus JSON hasil `/backup struktur`, versi ≤ 1, maksimal 4 MB.

## 5. Ketahanan & Performa Bawaan
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
