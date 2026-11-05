---
title: "R. Anti-Nuke (/nuke)"
description: "Anti-nuke: deteksi penghapusan massal, bot asing, mode beku, dan pemulihan ringan."
icon: "security"
weight: 18
toc: true
---

Melindungi server dari **penghancuran massal oleh staff jahat atau akun yang di-hack**.
Bot membaca **Audit Log** Discord (siapa melakukan apa), menghitung aksi berisiko per pelaku,
lalu bertindak sesuai pengaturan Admin. **0 kuota AI.**

| Command | Fungsi |
| :--- | :--- |
| **`/nuke status`** | Status, aksi aktif, ambang tiap jenis, izin bot, whitelist, & pelanggaran terakhir |
| **`/nuke atur`** *(Admin)* | Aktifkan, channel log, aksi, durasi timeout, DM owner, pemulihan, ambang & jendela waktu |
| **`/nuke whitelist`** *(Admin)* | Lihat / tambah / hapus member & role yang dikecualikan |
| **`/nuke uji`** *(Admin)* | Uji kering: lihat ambang & tindakan yang akan dijalankan (tidak menindak) |
| **`/nuke pulihkan`** *(Admin)* | Pulihkan nama & ikon server dari titik pulih terakhir |
| **`/nuke beku durasi_menit:30`** *(Admin)* | **Mode beku**: setiap aksi destruktif langsung ditindak (ambang = 1) selama N menit |
| **`/nuke cairkan`** *(Admin)* | Akhiri mode beku lebih awal |
| **`/nuke matikan`** *(Admin)* | Hentikan pemantauan |

## Yang dipantau (ambang bisa diubah Admin)
| Aksi | Ambang bawaan | Kenapa berbahaya |
| :--- | :--- | :--- |
| 🧨 Hapus channel | 3× / 60 dtk | Riwayat chat hilang permanen |
| 🎭 Hapus role | 3× / 60 dtk | Struktur izin hancur |
| 🔨 Ban massal | 5× / 60 dtk | Server dikosongkan |
| 👢 Kick massal | 5× / 60 dtk | Sama, tanpa jejak ban |
| 🌊 Buat channel massal | 8× / 60 dtk | Server dibanjiri channel sampah |
| 🪝 Buat webhook | 3× / 5 mnt | Saluran spam yang tetap hidup walau bot keluar |
| 🏷️ Ubah identitas server | 2× / 5 mnt | Pembajakan nama/ikon |
| 🧯 Cabut role massal | 12× / 60 dtk | Member kehilangan akses beramai-ramai |
| 🤖 **Bot asing ditambahkan** | **1×** | Bot jahat bisa jadi Administrator & menghancurkan server |
| 🎨 Buat role massal | 4× / 60 dtk | Role admin palsu / izin kacau |

## Perlindungan bot jahat & mode beku (v1.35.0-beta, 0 kuota AI)
- **Bot asing langsung dikeluarkan.** Saat ada yang menambahkan bot lewat OAuth, bot ini menangkap
  `bot_add` di Audit Log dan **menendang bot itu** seketika (bisa dimatikan: `/nuke atur keluarkan_bot:False`).
  Tambahan bot juga dicatat sebagai pelanggaran pelaku, jadi aksi berikutnya ikut ditindak.
- **Mode beku (`/nuke beku`)** dipakai saat server sedang diserang: **ambang menjadi 1 aksi** untuk semua
  jenis (hapus channel, ban massal, webhook, dll.), berlaku 1–1440 menit, dan otomatis cair saat waktunya
  habis (watcher memeriksa tiap 1 jam) atau lewat `/nuke cairkan`.
- Kalau aksi server masih `lapor`, mode beku tetap **melapor instan** tetapi tidak menindak — ubah dulu ke
  `cabut-role`/`timeout`/`kick`/`ban` lewat `/nuke atur aksi:` atau `/nuke beku paksa_aksi:`.
- **Peran bot yang disarankan:** beri bot **View Audit Log + Manage Roles + Kick Members + Manage Channels**
  (jangan Administrator). Dengan cara itu bot bisa menindak tanpa menjadi sasaran serangan balik.

## Aksi bertingkat (pilih di `/nuke atur aksi:`)
| Mode | Efek |
| :--- | :--- |
| `lapor` *(bawaan)* | Hanya laporan ke channel log + DM owner — **tanpa tindakan otomatis** |
| `cabut-role` | Laporan + cabut semua role berbahaya pelaku (administrator, manage server, ban, dll.) |
| `timeout` | Laporan + timeout sementara (durasi diatur, maks 28 hari) |
| `kick` | Laporan + keluarkan pelaku |
| `ban` | Laporan + ban pelaku |

## Pemulihan ringan (opsional, aktif bawaan)
- **Nama & ikon server** dikembalikan dari titik pulih yang disimpan saat bot start / saat Admin menyimpan pengaturan.
- **Webhook buatan pelaku** dihapus otomatis.
- Bisa dipulihkan manual kapan saja: `/nuke pulihkan`.

## Pengaman
| Hal | Perilaku |
| :--- | :--- |
| Owner server | **Tidak pernah** ditindak (batasan Discord) |
| Bot ini sendiri | Selalu dikecualikan |
| Whitelist | Member/role terpercaya tidak pernah ditindak (`/nuke whitelist`) |
| Izin bot | Butuh **View Audit Log**; tanpa itu `/nuke status` memberi peringatan jelas |
| Salah tembak | Hanya pelaku (dari audit log) yang dihitung, bukan seluruh staff |
| Pembatasan | Bot tidak bisa mengembalikan **isi pesan** yang sudah dihapus — hanya struktur & identitas |
| Data | `data/antinuke.json` (konfigurasi + 20 pelanggaran terakhir) |

> **Rekomendasi:** biarkan mode `lapor` selama 1–2 minggu untuk melihat apakah ada false positive
> (mis. staff yang memang sedang merapikan channel), baru naikkan ke `cabut-role` atau `timeout`.

---
