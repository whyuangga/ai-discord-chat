---
title: "K. Penerjemah Hemat Kuota (/terjemah)"
linkTitle: "K. Penerjemah Hemat Kuota"
weight: 11
---

Tiga tingkat pemakaian kuota, dari paling hemat:

| Mode | Kuota AI | Cara pakai |
| :--- | :--- | :--- |
| **Reaksi bendera** (disarankan, default) | hanya saat diminta | `/terjemah channel channel:#english-chat` → bot menempel 🇮🇩/🇬🇧 di pesan warga; terjemahan **baru dibuat ketika ada yang mengklik**, lalu dikirim lewat **DM** agar channel tidak banjir. |
| **Manual** | 1 panggilan / penggunaan | `/terjemah teks teks:... ke:id` atau `/terjemah pesan pesan_id:... ke:en` (tempel ID/tautan pesan). |
| **Auto-post** (opsional, **default mati**) | 1 panggilan / pesan | `/terjemah channel channel:#chat auto:True` — setiap pesan layak diterjemahkan otomatis (rate limit 3 detik/channel + batas kuota server). |

- **Cache 6 jam:** kalimat yang sama tidak diterjemahkan dua kali (maks 300 entri) → pesan berulang **0 kuota**.
- **Filter pintar:** hanya teks 8–600 karakter berisi kata; link/emoji-only/pesan terlalu panjang dilewati.
- **Batas kuota dihormati:** bila `AI_DAILY_CAP_PER_GUILD` tercapai, penerjemah berhenti sementara dan memberi pesan ramah.
- **Tercatat di `/pemakaian`** sebagai jenis operasi `Terjemah` (termasuk hitungan cache hit).
- Perintah pendukung: `/terjemah status` (channel terpilih, ukuran cache, sisa kuota server) dan `/terjemah channel aktif:False` untuk melepas channel.
