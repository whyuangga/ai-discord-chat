# 🌐 Situs dokumentasi (`site/`)

Situs statis untuk dokumentasi bot, memakai **Hugo + tema [Hextra](https://github.com/imfing/hextra)**
(tampilan seperti <https://wiki.hypr.land>). Tema di-*vendor* di `themes/hextra/`, jadi build
tidak butuh jaringan maupun Node.js.

## ⚠️ Konten dihasilkan otomatis

`site/content/` **jangan diedit langsung**. Sumber kebenaran tetap:

- [`docs/fitur.md`](../docs/fitur.md) — 23 area fitur A–W
- [`docs/command.md`](../docs/command.md) — referensi command

Setelah mengubah salah satunya:

```bash
python3 tools/sync_docs.py     # tulis ulang site/content/
python3 -m pytest -q           # tes menjaga konten situs tetap sinkron
```

`tools/sync_docs.py --check` akan gagal bila situs tertinggal dari sumbernya.

## Pratinjau lokal

Butuh Hugo **extended** ≥ 0.146 (sekali pasang):

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

4. **Environment variable** (wajib, Hextra butuh versi extended):

| Variabel | Nilai |
| :--- | :--- |
| `HUGO_VERSION` | `0.169.0` |

5. Save & Deploy → situs terbit di `https://<project>.pages.dev` dan **dibangun ulang otomatis**
   setiap push ke `main`.

> Kalau nanti pindah domain, cukup ubah `baseURL` di `site/hugo.yaml` (atau biarkan
> `-b $CF_PAGES_URL` yang mengisinya saat build).

## Mengganti tema

Karena tema di-vendor sebagai folder (bukan submodule), mengganti tema = mengganti isi
`site/themes/<nama>/` lalu menyesuaikan `theme:` di `site/hugo.yaml`. Kandidat lain yang
kompatibel dengan Markdown yang sekarang: `hugo-book`, `Blowfish`, `Relearn`, `Docsy`.

## Struktur

```text
site/
├── hugo.yaml              # konfigurasi situs (tema, menu, pencarian)
├── assets/                # FlexSearch lokal (pencarian offline)
├── content/               # HASIL GENERATE — jangan diedit manual
│   ├── _index.md          # halaman depan (hero + kartu fitur)
│   └── docs/              # 23 halaman fitur + referensi command
├── themes/hextra/         # tema (MIT, ikut lisensi aslinya)
└── public/                # hasil build (di-ignore git)
```
