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

## Deploy ke Cloudflare Pages (gratis, repo tetap privat)

1. Cloudflare Dashboard → **Workers & Pages** → **Create** → tab **Pages** → **Connect to Git**.
2. Pilih repo `whyuangga/ai-discord-chat` (boleh privat).
3. Isi build setting:

| Setelan | Nilai |
| :--- | :--- |
| Framework preset | Hugo |
| Root directory | `site` |
| Build command | `hugo --gc --minify -b $CF_PAGES_URL` |
| Build output directory | `public` |

4. **Environment variable** (wajib — Hugo harus versi *extended* karena tema memakai SCSS):

| Variabel | Nilai |
| :--- | :--- |
| `HUGO_VERSION` | `0.169.0` |

5. Save & Deploy → situs terbit di `https://<project>.pages.dev` dan **dibangun ulang otomatis**
   setiap push ke `main`.

> **Catatan versi:** Lotus Docs (rilis v0.3.0) masih memakai `css.Sass` (libsass) yang sudah
> *deprecated* di Hugo, sehingga build mengeluarkan peringatan — bukan error. Karena itu versi
> Hugo **dipin** di `0.169.0`. Kalau nanti tema ini pindah ke Dart Sass, pin boleh dilepas.

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
