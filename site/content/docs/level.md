---
title: "I. Level & XP serta Tiket Dukungan (/level, /tiket)"
description: "XP pesan & voice, role hadiah, musim dan prestige; tiket thread dengan SLA & rating bintang."
icon: "military_tech"
weight: 9
toc: true
---

> 🧩 Kedua fitur ini **retensi + pelayanan**: membuat warga betah (level & papan peringkat) dan
> membuat staf rapi menangani bantuan (tiket thread). **Tanpa AI, tanpa database eksternal.**

## 1. Leveling & XP (`/level`)

| Command | Fungsi |
| :--- | :--- |
| **`/level lihat [member]`** | Kartu level + progress bar `▰▰▰▱▱`, total XP, & jumlah pesan. |
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

## 2. Tiket Dukungan (`/tiket`)

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
   dari dashboard** (halaman `/tiket` → subpanel *Arsip transkrip*) tanpa mengunduh berkas. Batas arsip
   `TICKET_ARSIP_MAX` (default **200** tiket terbaru per server); arsip lama otomatis dipangkas.
   Setiap tiket juga bisa diberi **catatan internal staf** (`/tiket catat` atau kotak di dashboard):
   disimpan di `data/tickets.json`, maksimal **25 catatan** per tiket, dan **tidak pernah** dikirim
   ke thread — member tidak bisa membacanya.
5. Batas tiket aktif per member `TICKET_MAX_OPEN_PER_USER` (default **2**) mencegah spam tiket.

**Kualitas layanan (v1.33.0-beta, 0 kuota AI):**

| Fitur | Detail |
| :--- | :--- |
| **⭐ Rating bintang** | Setelah tiket ditutup, pembuat tiket menerima kartu **1–5 bintang** di thread (sebelum thread dikunci). Hanya pembuat tiket yang bisa menilai, satu kali per tiket. Rekap di `/tiket rating`. |
| **⏰ SLA respons pertama** | Bot mencatat **pesan staf pertama** di tiket. Bila belum ada respons sampai `sla_jam`, peringatan dikirim ke `channel_sla` / channel log (sekali per tiket, anti-spam). |
| **🧹 Auto-close** | Tiket tanpa aktivitas selama `auto_close_jam` ditutup otomatis: pesan penjelasan, transkrip tetap dikirim ke log, thread dikunci & diarsipkan. Aktivitas member (termasuk pembuat tiket) memperbarui hitungan. |
| **Default aman** | Rating **aktif**, SLA & auto-close **nonaktif** (`0`) sampai Admin menyalakannya. Pemeriksaan berjalan tiap 1 menit di watcher yang sudah ada. |

---
