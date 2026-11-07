"""Pembuat meme lokal dengan Pillow — **0 kuota AI**, tanpa layanan gambar.

Diambil dari modul meme Instabot, tapi versi hemat: tidak butuh aset gambar sama sekali.
Setiap template hanya "resep" warna + tata letak, teksnya digambar sendiri.

Template yang tersedia (id → gaya):

| id | gaya |
| :-- | :-- |
| `klasik` | teks putih tebal bergaris hitam di atas dasar gelap |
| `impact` | teks kuning besar, tanpa garis (ala meme impact) |
| `drake` | dua panel: atas "ditolak", bawah "diterima" |
| `neon` | teks menyala (glow bertingkat) di dasar ungu gelap |
| `kertas` | dasar krem, teks cokelat, bergaya catatan |
| `terminal` | dasar hitam, teks hijau monospace |

Kalau Pillow tidak terpasang, `buat_meme()` mengembalikan `(None, pesan)`.
"""

from __future__ import annotations

import io
import logging
import textwrap

logger = logging.getLogger("gemini_bot.meme_maker")

MAKS_HURUF = 120  # per kolom teks (atas / bawah)

TEMPLATE: dict[str, dict] = {
    "klasik": {
        "label": "Klasik (putih + garis hitam)", "emoji": "🖼️", "ukuran": (800, 800),
        "latar": ((18, 18, 22), (40, 40, 48)), "teks": (255, 255, 255),
        "garis": (0, 0, 0), "skala": 0.085, "panel": False,
    },
    "impact": {
        "label": "Impact (kuning besar)", "emoji": "💥", "ukuran": (800, 800),
        "latar": ((8, 8, 8), (8, 8, 8)), "teks": (255, 233, 0),
        "garis": (0, 0, 0), "skala": 0.095, "panel": False,
    },
    "drake": {
        "label": "Drake (ditolak / diterima)", "emoji": "🙅", "ukuran": (800, 800),
        "latar": ((235, 235, 235), (255, 255, 255)), "teks": (20, 20, 20),
        "garis": (255, 255, 255), "skala": 0.070, "panel": True,
    },
    "neon": {
        "label": "Neon (menyala)", "emoji": "🌌", "ukuran": (800, 800),
        "latar": ((24, 8, 44), (60, 16, 96)), "teks": (120, 255, 240),
        "garis": (10, 220, 200), "skala": 0.085, "panel": False,
    },
    "kertas": {
        "label": "Kertas (catatan)", "emoji": "📝", "ukuran": (800, 800),
        "latar": ((248, 243, 227), (238, 230, 205)), "teks": (74, 52, 34),
        "garis": (248, 243, 227), "skala": 0.082, "panel": False,
    },
    "terminal": {
        "label": "Terminal (hijau)", "emoji": "💻", "ukuran": (800, 800),
        "latar": ((0, 12, 0), (0, 24, 8)), "teks": (80, 255, 120),
        "garis": (0, 0, 0), "skala": 0.078, "panel": False,
    },
}


def daftar_template() -> list[dict]:
    return [
        {"id": kunci, "label": f'{data["emoji"]} {data["label"]}'}
        for kunci, data in TEMPLATE.items()
    ]


def cari_template(kunci: object) -> str:
    """Id template dari id/label; kembali ke `klasik` bila tidak dikenal."""
    cari = str(kunci or "").strip().casefold()
    if cari in TEMPLATE:
        return cari
    for kunci_tema, data in TEMPLATE.items():
        if cari and (cari in data["label"].casefold() or cari == data["emoji"]):
            return kunci_tema
    return "klasik"


def _gradien(ukuran: tuple[int, int], atas: tuple[int, int, int], bawah: tuple[int, int, int]):
    from PIL import Image

    lebar, tinggi = ukuran
    gambar = Image.new("RGB", ukuran, atas)
    piksel = gambar.load()
    for y in range(tinggi):
        rasio = y / max(1, tinggi - 1)
        warna = tuple(int(atas[i] + (bawah[i] - atas[i]) * rasio) for i in range(3))
        for x in range(lebar):
            piksel[x, y] = warna
    return gambar


def _font(ukuran: int, tebal: bool = True):
    from PIL import ImageFont

    from welcome_media import _FONT_CANDIDATES

    for calon in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(calon, ukuran)
        except Exception:
            continue
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", ukuran)
    except Exception:
        return ImageFont.load_default()


def _bungkus(teks: str, huruf_per_baris: int) -> list[str]:
    rapi = " ".join(str(teks or "").split())
    if not rapi:
        return []
    return textwrap.wrap(rapi, width=max(8, huruf_per_baris))[:6]


def _tulis_blok(draw, baris: list[str], font, *, tengah_x: int, atas_y: int, tinggi_baris: int,
                warna, garis=None, stroke: int = 0) -> int:
    """Tulis beberapa baris ke tengah; kembalikan Y akhir."""
    y = atas_y
    for teks in baris:
        draw.text(
            (tengah_x, y), teks, font=font, fill=warna, anchor="ma",
            stroke_width=stroke, stroke_fill=garis or warna,
        )
        y += tinggi_baris
    return y


def buat_meme(
    teks_atas: object = "",
    teks_bawah: object = "",
    *,
    template: str = "klasik",
) -> tuple[io.BytesIO | None, str]:
    """Gambar meme → `(buffer PNG, pesan galat)`. Tanpa jaringan & tanpa AI."""
    atas = " ".join(str(teks_atas or "").split())[:MAKS_HURUF]
    bawah = " ".join(str(teks_bawah or "").split())[:MAKS_HURUF]
    if not atas and not bawah:
        return None, "Isi minimal salah satu teks (atas atau bawah)."

    try:
        from PIL import ImageDraw
    except Exception:  # pragma: no cover - Pillow tidak terpasang
        return None, "Pillow belum terpasang, jadi meme tidak bisa dibuat."

    kunci = cari_template(template)
    resep = TEMPLATE[kunci]
    lebar, tinggi = resep["ukuran"]
    gambar = _gradien((lebar, tinggi), resep["latar"][0], resep["latar"][1])
    draw = ImageDraw.Draw(gambar)

    ukuran_font = max(18, int(tinggi * resep["skala"]))
    font = _font(ukuran_font)
    huruf_per_baris = max(10, int(lebar / (ukuran_font * 0.62)))

    if resep["panel"]:
        # Dua panel: teks atas di panel atas ("ditolak"), teks bawah di panel bawah.
        tinggi_panel = tinggi // 2
        draw.rectangle([(0, 0), (lebar - 1, tinggi_panel - 1)], fill=(226, 226, 226))
        draw.rectangle([(0, tinggi_panel), (lebar - 1, tinggi - 1)], fill=(255, 255, 255))
        draw.line([(0, tinggi_panel), (lebar, tinggi_panel)], fill=(200, 200, 200), width=3)
        for indeks, teks in enumerate((atas, bawah)):
            if not teks:
                continue
            baris = _bungkus(teks, huruf_per_baris)
            blok_tinggi = len(baris) * int(ukuran_font * 1.15)
            mulai = indeks * tinggi_panel + (tinggi_panel - blok_tinggi) // 2
            _tulis_blok(draw, baris, font, tengah_x=lebar // 2, atas_y=mulai,
                        tinggi_baris=int(ukuran_font * 1.15), warna=resep["teks"])
    else:
        margin = int(tinggi * 0.05)
        jarak = int(ukuran_font * 1.15)
        if atas:
            _tulis_blok(draw, _bungkus(atas, huruf_per_baris), font, tengah_x=lebar // 2,
                        atas_y=margin, tinggi_baris=jarak, warna=resep["teks"],
                        garis=resep["garis"], stroke=3)
        if bawah:
            baris = _bungkus(bawah, huruf_per_baris)
            mulai = tinggi - margin - len(baris) * jarak
            _tulis_blok(draw, baris, font, tengah_x=lebar // 2, atas_y=mulai,
                        tinggi_baris=jarak, warna=resep["teks"], garis=resep["garis"], stroke=3)

    # Tanda kecil agar hasil jelas berasal dari bot ini.
    draw.text(
        (lebar // 2, tinggi - int(tinggi * 0.02)), "• meme lokal •",
        font=_font(max(12, ukuran_font // 3)), fill=resep["teks"], anchor="md",
    )

    buffer = io.BytesIO()
    gambar.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer, ""
