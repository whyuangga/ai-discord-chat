# 🌐 Situs dokumentasi (`site/`)

Situs statis untuk dokumentasi bot, memakai **Hugo + tema [Lotus Docs](https://github.com/colinwilson/lotusdocs)**
(MIT). Seluruh kebutuhan tema — Bootstrap 5 SCSS, JavaScript Bootstrap, dan Popper — sudah
di-*vendor* di `site/themes/lotusdocs/`, jadi build **tidak butuh Go, Node.js, npm, maupun jaringan**.

## ⚠️ Konten dihasilkan otomatis

`site/content/` **jangan diedit langsung**. Sumber kebenaran tetap:

- [`docs/fitur.md`](../docs/fitur.md) — 23 area fitur A–W
- [`docs/command.md`](../docs/command.md) — referensi command

Setelah mengubah salah satunya:

```bash
python3 tools/sync_docs.py     # tulis ulang site/content/
python3 -m pytest -q           # tes menjaga konten situs tetap sinkron
```

`tools/sync_docs.py --check` gagal bila situs tertinggal dari sumbernya.
Halaman depan (hero + kartu fitur) ditulis manual di [`site/data/landing.yaml`](data/landing.yaml).

## Pratinjau lokal

Butuh Hugo **extended** ≥ 0.140 (sekali pasang):

```bash
pip install hugo              # binary Hugo dari PyPI (tanpa Go / npm)
cd site && hugo server -D
```

Buka <http://localhost:1313>. Build produksi: `cd site && hugo --minify` → hasil di `site/public/`.

## Deploy ke Vercel (gratis, repo tetap privat)

Konfigurasi build sudah disimpan di [`site/vercel.json`](vercel.json), jadi di dashboard
cukup menunjuk root directory ke `site/`.

1. Vercel Dashboard → **Add New… → Project** → **Import Git Repository** → pilih
   `whyuangga/ai-discord-chat` (repo privat boleh).
2. Pada layar konfigurasi, isi **Root Directory** = `site` lalu **klik Edit** di bagian
   *Build and Output Settings*, dan pastikan:

| Setelan | Nilai |
| :--- | :--- |
| Framework Preset | **Hugo** |
| Build Command | `hugo --gc --minify --baseURL "https://${VERCEL_PROJECT_PRODUCTION_URL:-${VERCEL_URL:-ai-discord-chat-site.vercel.app}}"` |
| Output Directory | `public` |
| Install Command | *(kosongkan)* |

3. **Environment Variables** (wajib — Hugo di Vercel versinya lama dan tema butuh *extended*):

| Variabel | Nilai |
| :--- | :--- |
| `HUGO_VERSION` | `0.169.0` |

4. **Deploy** → situs terbit di `https://<project>.vercel.app`. Setiap push ke `main`
   otomatis memicu deploy baru; pull request mendapat **Preview Deployment** sendiri.

`vercel.json` sudah memuat `framework`, `buildCommand`, `outputDirectory`, dan
`build.env.HUGO_VERSION`, jadi langkah 2–3 sebenarnya hanya perlu bila kamu ingin
mengubahnya — kalau file itu terbaca, build langsung benar.

**Kalau memakai domain sendiri:** tambahkan di *Settings → Domains*. `--baseURL` di atas memakai
`VERCEL_PROJECT_PRODUCTION_URL` (domain produksi) lebih dulu, lalu `VERCEL_URL` (URL deployment /
preview), lalu domain sekarang sebagai cadangan terakhir. Jadi `sitemap.xml`, `robots.txt`, dan
`og:url` **tidak** menunjuk ke URL deployment panjang saat situs dibuka dari domain produksi —
tanpa perlu mengubah `hugo.toml`.

> **Catatan versi:** Lotus Docs (rilis v0.3.0) masih memakai `css.Sass` (libsass) yang sudah
> *deprecated* di Hugo, sehingga build mengeluarkan peringatan — bukan error. Karena itu versi
> Hugo **dipin** di `0.169.0` (`site/vercel.json`). Kalau tema sudah pindah ke Dart Sass, pin
> boleh dilepas.

> Alternatif lain tetap bisa: Cloudflare Pages atau Netlify dengan setelan yang sama
> (build `hugo --gc --minify`, output `public`, `HUGO_VERSION=0.169.0`).

## Berkas tambahan di luar tema

| Berkas | Kenapa ada |
| :--- | :--- |
| `site/data/landing.yaml` | hero + 6 kartu halaman depan (tema tidak menyediakannya) |
| `site/layouts/robots.txt` | menambah baris `Sitemap:` — templat bawaan Hugo hanya `User-agent: *` |
| `disableKinds = ["taxonomy", "term"]` di `hugo.toml` | mencegah `/categories/` & `/tags/` kosong ikut ke sitemap |
| `site/layouts/partials/head.html` | menimpa `<head>` halaman depan: meta tema ("A Lightweight, Modern Documentation Theme…", author Colin Wilson, email support@aigis.uk) diganti deskripsi/keywords/author situs + kartu Open Graph & Twitter |
| `site/content/_index.md` | sumber `title` & `description` halaman depan; halaman depan tetap dirender dari `data/landing.yaml`, isi berkas ini tidak tampil |
| `keywords` / `author` di `[params]` `hugo.toml` | dipakai `site/layouts/partials/head.html` |

## Isi tema & asal-usulnya (untuk update manual)

| Komponen | Versi / commit | Sumber |
| :--- | :--- | :--- |
| Tema Lotus Docs | commit `3d1639d` (rilis v0.3.0) | <https://github.com/colinwilson/lotusdocs> |
| Bootstrap (SCSS + JS src) | v5.3.8 | <https://github.com/twbs/bootstrap> |
| Popper | 2.11.8 | npm `@popperjs/core` (dist/esm) |

Bootstrap dan Popper di-*vendor* karena tema aslinya memakai **Hugo Modules** (butuh Go +
unduh saat build). Satu-satunya perubahan pada kode Bootstrap: dua baris `import` di
`assets/js/bootstrap/src/dropdown.js` & `tooltip.js` diarahkan dari `'@popperjs/core'` ke
`'../../popper/index.js'` agar bundle JS tidak butuh `node_modules`.

**Cara update tema:** unduh rilis baru, ganti isi `site/themes/lotusdocs/` (jangan lupa folder
`assets/scss/bootstrap`, `assets/js/bootstrap/src`, `assets/js/popper` yang kita tambahkan sendiri),
lalu jalankan `cd site && hugo --minify` dan cek ulang tautannya.

## Mengganti tema

Struktur konten sekarang mengikuti Lotus Docs (`title`, `description`, `icon`, `weight`, `toc`).
Tema lain (Hextra, hugo-book, Monochrome) tetap bisa dipakai, tetapi `tools/sync_docs.py` bagian
`_fm()` perlu disesuaikan karena kunci *front matter*-nya berbeda.

## Struktur

```text
site/
├── hugo.toml              # konfigurasi situs (tema, params.docs, FlexSearch)
├── data/landing.yaml      # halaman depan: hero + 6 kartu fitur (ditulis manual)
├── content/docs/          # HASIL GENERATE — jangan diedit manual
│   ├── _index.md          # daftar 23 area + referensi command
│   ├── <slug>.md          # 23 halaman fitur
│   └── command.md         # referensi command & tombol
├── themes/lotusdocs/      # tema + Bootstrap SCSS/JS + Popper (MIT/Apache-2.0)
└── public/                # hasil build (di-ignore git)
```
