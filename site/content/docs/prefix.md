---
title: "U. Prefix Command per Server (/prefix)"
description: "Prefix teks per server; prefix `!` lama tetap berfungsi dan tidak pernah dihapus."
icon: "terminal"
weight: 21
toc: true
---

Slash command (`/...`) tidak butuh prefix, tetapi bot juga punya command teks lama
(`!setup_panel`). Setiap server boleh mengganti prefix itu:

| Command | Fungsi |
| :--- | :--- |
| **`/prefix lihat`** | Prefix khusus server + daftar prefix yang diterima. |
| **`/prefix atur prefix:?`** *(Admin)* | Ganti prefix (1–5 karakter). |
| **`/prefix reset`** *(Admin)* | Kembalikan ke prefix bawaan `!`. |

**Aturan:** prefix tidak boleh berspasi, tidak boleh memakai karakter `<> & @ # : ` / \ * _ ~ |`,
dan **prefix bawaan `!` tetap diterima** sebagai cadangan agar member lama tidak bingung.
Hanya server yang diubah yang disimpan di `data/prefixes.json` (hemat I/O & RAM).
Command AI di channel tetap tidak terpengaruh: prefix hanya untuk command teks, bukan obrolan.
