---
title: "F. Streaming Musik 24/7 (/musik + Lavalink)"
description: "Lavalink v4 gratis: panel ala Rythm, filter audio, autoplay, role DJ, dan playlist per member."
icon: "music_note"
weight: 6
toc: true
---

> ⚠️ **Kenapa Lavalink?** Wispbyte hanya menjalankan **satu proses Python tanpa FFmpeg/yt-dlp**.
> Supaya musik tetap jalan tanpa membebani bot (RAM tetap ~50–80 MB), audio didelegasikan ke **Lavalink v4**
> — server kecil berbahasa Java khusus musik. Bot hanya mengirim perintah "putar lagu X" ke node tersebut.

## 1. Menyiapkan Node Lavalink (3 pilihan, semuanya gratis)

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

## 2. Kalau node tidak tersambung (troubleshooting)

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

## 3. Daftar Command (`/musik`)

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

## 4. Perilaku & Pengamanan
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
