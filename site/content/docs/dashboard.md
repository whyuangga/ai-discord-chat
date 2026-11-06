---
title: "J. Dashboard Web (DASHBOARD_TOKEN)"
description: "Dashboard web ringan di proses yang sama: pantau status dan kontrol fitur dari browser."
icon: "dashboard"
weight: 10
toc: true
---

Satu halaman web untuk memantau **dan** mengatur bot: status, pemakaian AI, papan level,
peta fitur, **39 setelan server**, **kirim embed/webhook**, dan pengelolaan konten.
Rincian tiap bagian ada di [Dashboard web (panel admin lengkap)](#dashboard-web-panel-admin-lengkap).

| Aspek | Detail |
| :--- | :--- |
| **Cara nyala** | Isi `DASHBOARD_TOKEN` (kata sandi acak) **dan** sediakan port (`DASHBOARD_PORT`, atau otomatis dari `SERVER_PORT`/`PORT` panel). Kosong = dashboard mati. |
| **Akses** | `http://<ip-server>:<port>/?token=<DASHBOARD_TOKEN>` — token juga bisa lewat header `X-Dashboard-Token` / `Authorization: Bearer` atau field tersembunyi pada form. |
| **Endpoint baca** | `/` (HTML), `/api/status`, `/api/pemakaian?guild=<id>`, `/api/level?guild=<id>`, `/api/kontrol?guild=<id>`, `/api/fitur?guild=<id>`, `/api/setelan?guild=<id>`, `/healthz` (tanpa token). |
| **Endpoint tulis** | Hanya tiga jalur `POST`, semuanya **wajib token**: `/api/aksi` (setelan, `action=set.<kunci>`), `/api/kirim` (pesan/embed/webhook), `/api/konten` (buat/hapus pengumuman, tautan, panel). Aksi lama (`level`, `ekonomi`, `tumbuh`, `antispam`, `antinuke`) tetap didukung. |
| **Setelan** | **39 fitur** dalam 5 grup: inti/level/ekonomi, sambutan & pamit, keamanan, tiket & sapaan harian, konten & interaksi. |
| **Whitelist** | Hanya kunci yang terdaftar di `dashboard_admin.FITUR` yang bisa dijalankan — nama fungsi bebas tidak pernah dieksekusi. |
| **Mitigasi** | Halaman `/` tetap **GET-only** (POST ke `/` ditolak). Tidak ada `PUT`/`DELETE`/`PATCH`. Tombol Hapus hanya membuang satu item. Semua perubahan (berhasil maupun gagal) dicatat di `data/dashboard_audit.json` dan log bot. |
| **Biaya** | **0 kuota AI**, ±2–4 MB RAM, tanpa dependency baru (`aiohttp.web` sudah dipakai bot), tetap **1 proses**. |
| **Tanpa JS** | HTML dirender di server (semua form HTML biasa), `meta refresh` opsional (`DASHBOARD_REFRESH_SEC`, isi `0` untuk mematikan) → ringan dibuka dari HP. |

> ⚠️ Dashboard hanya bisa dibuka dari luar bila panel hosting memberi **port allocation**.
> Di Wispbyte cek tab **Network / Allocations**; bila tidak ada alokasi, dashboard otomatis
> tidak menyala dan bot tetap berjalan normal (tidak ada error).
