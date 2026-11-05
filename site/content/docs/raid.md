---
title: "S. Raid Guard (/raid)"
description: "Mode darurat otomatis saat lonjakan join: tahan auto role, verifikasi, lockdown sementara."
icon: "crisis_alert"
weight: 19
toc: true
---

Melengkapi anti-raid yang hanya **melapor**: bila server diserbu akun palsu, bot menyalakan
**mode darurat otomatis** selama beberapa menit lalu mengembalikan keadaan semula. **0 kuota AI.**

| Aksi | Efek saat mode raid aktif |
| :--- | :--- |
| `lapor` | Laporan ke channel log saja — tanpa mengubah server. |
| `verifikasi` *(bawaan)* | **Auto Role ditahan** + member baru diminta verifikasi (DM & sebutan di channel verifikasi). |
| `verifikasi+lockdown` | Semua di atas **+ lockdown** text channel sampai mode berakhir. |

| Command | Fungsi |
| :--- | :--- |
| **`/raid atur`** *(Admin)* | Aktifkan deteksi, ambang join, jendela waktu, aksi, durasi, channel log & verifikasi. |
| **`/raid status`** | Mode aktif?, sisa waktu, ambang, aksi, & channel yang dipakai. |
| **`/raid mulai`** *(Admin)* | Nyalakan mode darurat sekarang (tanpa menunggu ambang). |
| **`/raid akhiri`** *(Admin)* | Akhiri lebih awal & buka kembali lockdown. |

**Pengaman:** default **nonaktif**, hanya **Admin/Manage Server** yang bisa mengubah, laporan
maksimal **sekali per 5 menit** (anti-spam), semua tindakan **reversible** (lockdown dibuka &
Auto Role normal saat mode berakhir), dan setiap kejadian tercatat di **Audit Log**.
