---
title: "A. Fitur Ruang Sesi Privat (/sesi)"
description: "Private thread AI per member: 5 kepribadian, PDF, voice note, vision, dan generate gambar."
icon: "forum"
weight: 1
toc: true
---

Admin cukup memasang satu panel permanen di channel khusus (misalnya `#ai-assistant`) menggunakan `/sesi panel` (atau `!setup_panel`). Dari panel tersebut, setiap member dapat membuka ruang privat (*Private Thread*) yang hanya bisa dilihat oleh member itu sendiri.

## 1. 💬 Chat AI Multi-Persona (5 Kepribadian Gemini)
Saat menekan tombol **💬 Chat AI (Teks & Vision)**, member bebas memilih 1 dari 5 mode kepribadian:
| Mode | Model Utama | Karakter & Kegunaan |
| :--- | :--- | :--- |
| **♊ Gemini Flash (Asisten Utama)** | `gemini-3.5-flash-lite` | Cerdas, ramah, cepat (~1 detik), & serba bisa untuk topik umum sehari-hari. |
| **⚡ Gemini Flash-Lite (Respon Kilat)** | `gemini-3.1-flash-lite` | Jawaban ringkas, padat, *to-the-point*, instan, & paling hemat kuota API. |
| **💻 Gemini - Pakar Koding & Debug** | `gemini-3.6-flash` | Spesialis pemrograman, struktur kode rapi, penjelasan logika, & bedah *bug*. |
| **🧠 Gemini - Penalaran & Riset** | `gemini-3.6-flash` | Analitis & sistematis *step-by-step* untuk matematika, sains, tugas, & riset. |
| **🛋️ Gemini - Teman Curhat** | `gemini-3.5-flash-lite` | Pendengar yang hangat, empatik, tidak menghakimi, dan suportif ala sahabat dekat. |

> 💡 **Ganti Mode Kapan Saja:** Di dalam ruang `ai-...`, tersedia menu *dropdown* dan command `/sesi model` untuk mengganti kepribadian Gemini di tengah percakapan **tanpa menghapus riwayat obrolan sebelumnya**.

## 2. 🎙️ Mendengar *Voice Note* (🎤), *Vision* Gambar, Link YouTube/Web, & *Live Search*
Di dalam ruang chat privat `ai-...`, member bisa langsung mengirim:
- **Voice Note / Pesan Suara Discord (🎤) & File Audio** (`.ogg`, `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac` — maks. 12 MB): Cukup tekan tombol mikrofon di Discord HP/PC lalu bicara — Gemini mendengarkan langsung isi ucapan beserta intonasinya dan menjawab nyambung tanpa perlu mengetik!
- **Link Video YouTube & Artikel Website**: Tempel langsung link YouTube (`youtube.com/watch`, `youtu.be`, `shorts`, `live`) atau URL berita/artikel untuk dirangkum dan didiskusikan isinya secara instan di ruang privat.
- **Pertanyaan Berita & Info Terkini Hari Ini**: Tanyakan berita terbaru, skor pertandingan, cuaca, harga emas/kurs, atau rilis teknologi terbaru — bot otomatis mencarikan sumber web aktual secara gratis di ruang privat.
- **Gambar / Screenshot** (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` — maks. 8 MB per gambar, hingga 4 gambar sekaligus): Cocok untuk menanyakan soal bergambar, desain UI, atau *screenshot* pesan *error* koding.
- **Dokumen PDF Native** (`.pdf` — maks. 10 MB): Unggah file materi kuliah, jurnal, panduan kerja, atau *e-book* PDF — Gemini langsung membaca dan membedah isinya secara utuh!
- **File Kode & Dokumen Teks** (`.py`, `.js`, `.ts`, `.tsx`, `.json`, `.yaml`, `.html`, `.css`, `.sql`, `.csv`, `.txt`, `.md`, `.log`, `.c`, `.cpp`, `.java`, `.go`, `.rs`, `.php`, dll. — maks. 100 KB per file): Bot otomatis membaca isi file dan memasukkannya sebagai konteks ke Gemini.
- **Stiker Discord**: Bot ikut mengenali visual stiker yang dikirim.

## 3. 🎨 Generate & Edit Gambar AI (`draw-...`)
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

## 4. 🔄 Reset Memori & 📜 Rekap Transkrip Lengkap ke DM
- **Tombol 🔄 Reset Sesi (atau `/sesi reset`):** Menghapus ingatan obrolan di ruang `ai-...` untuk ganti topik baru, atau mengembalikan setelan gaya/rasio gambar ke awal di ruang `draw-...` tanpa perlu membuat thread baru.
- **Tombol 🔴 Akhiri Sesi (atau `/sesi tutup`):**
  - Merangkum percakapan ke dalam **Embed Discord** yang rapi **sekaligus melampirkan file `rekap-nama-ruang.txt`** berisi transkrip percakapan utuh dari awal sampai akhir ke **DM pribadi member**.
  - Jika DM member dikunci/tertutup, bot otomatis mengirimkan file `.txt` tersebut di dalam thread dan memberi waktu **10 detik** untuk mengunduhnya sebelum ruang privat dihapus.

---
