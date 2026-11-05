---
title: "L. Hemat Kuota AI (/pemakaian, /ringkas channel, /faq)"
description: "Statistik pemakaian AI, cache rekap channel, FAQ lokal, dan cap harian per member/server."
icon: "savings"
weight: 12
toc: true
---

> 💡 Free Tier Gemini punya batas harian. Tiga fitur ini membuat bot **tetap pintar tanpa boros kuota**:
> rekap yang **di-cache**, FAQ yang dijawab **tanpa AI**, dan laporan pemakaian agar Admin tahu siapa/apa yang paling banyak memakai.

## 1. Pantau Pemakaian (`/pemakaian`)

| Command | Fungsi |
| :--- | :--- |
| **`/pemakaian lihat`** | Operasi AI **hari ini**: total, rincian per jenis (`Chat`, `Cari`, `Rekap`, `Auto-Chat`, `Galeri`, `Transform`, `Fakta`), 5 member teraktif, & channel tersibuk. |
| **`/pemakaian tren hari:7`** | Tren harian: total operasi vs **cache hit** (yang menghemat kuota). |
| **`/pemakaian status`** | Ringkasan penghematan: jumlah cache hit, batas harian per member, TTL cache rekap, & jumlah entri FAQ lokal. |
| **`/pemakaian reset`** *(Admin)* | Bersihkan catatan pemakaian hari ini. |

**Yang dicatat:** hanya operasi yang **benar-benar memanggil Gemini**. `/faq tanya`, cache hit `/ringkas channel`,
dan seluruh perintah non-AI **tidak** dihitung sebagai pemakaian (justru tercatat sebagai `cache hit` → bukti penghematan).

## 2. Rekap Channel Ber-cache (`/ringkas channel`)

| Command | Fungsi |
| :--- | :--- |
| **`/ringkas channel periode:6 jam terakhir`** | Rekap obrolan channel/thread per rentang waktu (1 jam → 7 hari). |
| **`/ringkas channel periode:24 jam terakhir paksa:True`** | Abaikan cache & buat rekap **baru** (memakai 1 panggilan AI). |
| **`/ringkas channel ... publik:True`** | Tampilkan hasil rekap ke channel, bukan hanya ke peminta. |

**Cara kerja cache:**
1. Hasil rekap disimpan **`REKAP_CACHE_TTL_SEC`** (default **1800 detik / 30 menit**) per pasangan **channel + periode**.
2. Permintaan berulang untuk channel & periode yang sama dalam 30 menit → **0 kuota** (diambil dari cache, embed diberi label `♻️`).
3. Maksimal `REKAP_MAX_MESSAGES` (default **400**) pesan dianalisis agar token tetap hemat.

## 3. FAQ Server Lokal (`/faq`) — 0 Kuota

| Command | Fungsi |
| :--- | :--- |
| **`/faq tanya pertanyaan:cara verifikasi?`** | Jawaban dicari **lokal** (pencocokan kata kunci) dari basis FAQ server — **tanpa memanggil AI**. |
| **`/faq daftar`** | Semua entri FAQ/Info server + jumlah kuota yang dihemat. |
| **`/faq tambah topik:Cara verifikasi isi:Klik tombol ✅ di #verifikasi`** *(Admin)* | Tambah/perbarui entri FAQ. |
| **`/faq hapus target:2`** *(Admin)* | Hapus entri berdasarkan nomor urut (`/faq daftar`) atau nama topik. |

**Dua manfaat satu entri:** entri FAQ dipakai `/faq tanya` (0 kuota) **dan** otomatis ikut sebagai konteks resmi
saat AI menjawab di Auto-Chat (`/agent`), sehingga AI tidak menebak-nebak info server.

**Batas maksimal:** `MAX_SERVER_KNOWLEDGE_ENTRIES` (default **25 entri** per server) agar prompt tetap kecil & hemat token.

## 4. Batas Harian AI per Member (opsional)

- `AI_DAILY_CAP_PER_USER=0` → **tanpa batas** (bawaan).
- `AI_DAILY_CAP_PER_USER=20` → tiap member maksimal **20 operasi AI per hari** pada perintah AI berbasis slash
  (`/cari`, `/ringkas link`, `/ringkas chat`, `/ringkas channel`, cek fakta, terjemah, dll.); setelah itu bot
  menyarankan `/faq tanya` & cache rekap. Obrolan AI di ruang privat `/sesi` & Auto-Chat tetap berjalan
  (tetap tercatat di `/pemakaian`).
- **Admin server bebas** dari jeda antar-perintah **dan** batas harian ini (agar tetap bisa mengurus server);
  member & staf biasa tetap dibatasi.
- Data disimpan di `data/ai_usage.json` dan otomatis **dipangkas** menyisakan `AI_USAGE_KEEP_DAYS` (default **7 hari**).

## 5. Batas Harian AI per Server & Keamanan Konten (opsional)

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

## 6. Urutan Paling Hemat Kuota

1. **`/faq tanya`** → 0 kuota (info server, aturan, jam event, dsb).
2. **`/ringkas channel`** berulang → 0 kuota (cache 30 menit).
3. **`/cari`** & **`/ringkas link`** → 1 panggilan per permintaan.
4. **Obrolan AI** (`/sesi`, Auto-Chat) → paling mahal, pakai saat memang perlu kreativitas/penalaran.

---
