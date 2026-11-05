---
title: "V. Ekspor Analitik CSV & Webhook (/analitik)"
linkTitle: "V. Ekspor Analitik CSV & Webhook"
weight: 22
---

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
