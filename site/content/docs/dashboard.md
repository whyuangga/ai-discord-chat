---
title: "J. Dashboard Web (DASHBOARD_TOKEN)"
description: "Dashboard web ringan di proses yang sama: pantau status dan kontrol fitur dari browser."
icon: "dashboard"
weight: 10
toc: true
---

Satu halaman web ringan untuk melihat angka yang biasanya hanya bisa dilihat lewat Discord
(uptime, RAM, latensi, operasi AI, token, cache hit, kuota server, papan level).

| Aspek | Detail |
| :--- | :--- |
| **Cara nyala** | Isi `DASHBOARD_TOKEN` (kata sandi acak) **dan** sediakan port (`DASHBOARD_PORT`, atau otomatis dari `SERVER_PORT`/`PORT` panel). Kosong = dashboard mati. |
| **Akses** | `http://<ip-server>:<port>/?token=<DASHBOARD_TOKEN>` — token juga bisa lewat header `X-Dashboard-Token` / `Authorization: Bearer`. |
| **Endpoint baca** | `/` (HTML), `/api/status`, `/api/pemakaian?guild=<id>`, `/api/level?guild=<id>`, `/api/kontrol?guild=<id>`, `/healthz` (tanpa token). |
| **Endpoint tulis** | `POST /api/aksi` (JSON atau form) — **wajib token**. Aksi yang didukung: `level`, `ekonomi`, `tumbuh`, `antispam` (`off`/`lapor`/`hapus`/`timeout`), `antinuke` (`lapor`/`cabut-role`/`timeout`/`kick`/`ban`). |
| **Kontrol Cepat** | Halaman dashboard punya panel **⚙️ Kontrol Cepat** berisi dropdown + tombol Simpan untuk menyalakan/mematikan fitur per server. Tidak ada tombol yang menghapus data. |
| **Mitigasi** | Halaman `/` tetap **GET-only** (POST ke `/` = 405); satu-satunya jalur tulis adalah `/api/aksi` yang selalu memeriksa token. Semua aksi dicatat di log bot. |
| **Biaya** | **0 kuota AI**, ±2–4 MB RAM, tanpa dependency baru (`aiohttp.web` sudah dipakai bot), tetap **1 proses**. |
| **Tanpa JS** | HTML dirender di server + `meta refresh` (`DASHBOARD_REFRESH_SEC`, default 30 detik) → ringan dibuka dari HP. |

> ⚠️ Dashboard hanya bisa dibuka dari luar bila panel hosting memberi **port allocation**.
> Di Wispbyte cek tab **Network / Allocations**; bila tidak ada alokasi, dashboard otomatis
> tidak menyala dan bot tetap berjalan normal (tidak ada error).
