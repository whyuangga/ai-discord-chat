"""Render gambar pratinjau perbaikan keterbacaan dashboard (alat bantu).

Membuat PNG dari struktur yang sama dengan dashboard asli: daftar isi di atas
halaman dan menu sidebar yang berkelompok. Memakai Pillow + font DejaVu karena
browser tidak tersedia di sandbox; tidak dipanggil oleh bot saat berjalan.

    python3 tools/demo/dashboard_gambar.py
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

KELUAR = Path("/home/user/pratinjau-dashboard.png")

LEBAR, TINGGI = 900, 470
PAD = 22

# Palet gelap dashboard
LATAR = (17, 18, 23)
SIDEBAR = (22, 23, 30)
KARTU = (26, 28, 36)
GARIS = (45, 48, 60)
TEKS = (234, 236, 242)
REDUP = (150, 156, 172)
REDUP2 = (110, 116, 132)
AKSEN = (139, 124, 255)
PINK = (232, 74, 138)

_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _f(ukuran: int, tebal: bool = False):
    try:
        return ImageFont.truetype(_FONT_B if tebal else _FONT, ukuran)
    except Exception:  # pragma: no cover - font cadangan
        return ImageFont.load_default()


F_JUDUL = _f(21, True)
F_H2 = _f(14, True)
F_TEKS = _f(12)
F_KECIL = _f(10)
F_KECIL2 = _f(9)


def tanpa_emoji(teks: str) -> str:
    """Buang emoji: font DejaVu tidak punya glyph-nya (tampil sebagai kotak)."""
    hasil = []
    for ch in str(teks):
        kat = unicodedata.category(ch)
        if kat in ("So", "Sk", "Cs"):
            continue
        hasil.append(ch)
    return " ".join("".join(hasil).split())


def _kotak(d, xy, *, radius=8, fill=None, outline=None, width=1):
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _pil(d, xy, teks, font, warna):
    """Pil bertautan (chip) — dipakai untuk daftar isi & menu."""
    lebar = d.textlength(teks, font=font)
    x1, y1 = xy
    kotak = (x1, y1, x1 + lebar + 18, y1 + 22)
    _kotak(d, kotak, radius=11, fill=LATAR, outline=GARIS)
    d.text((x1 + 9, y1 + 5), teks, font=font, fill=warna)
    return kotak[2]


def main() -> int:
    img = Image.new("RGB", (LEBAR, TINGGI), LATAR)
    d = ImageDraw.Draw(img)

    # ---------------- Sidebar ----------------
    sisi = 236
    d.rectangle((0, 0, sisi, TINGGI), fill=SIDEBAR)
    d.line((sisi, 0, sisi, TINGGI), fill=GARIS)

    d.text((PAD, 20), "Dashboard Bot", font=F_JUDUL, fill=TEKS)
    d.text((PAD, 46), "PUSAT KONTROL", font=F_KECIL2, fill=AKSEN)

    _kotak(d, (PAD, 70, sisi - PAD, 116), radius=9, fill=KARTU, outline=GARIS)
    d.text((PAD + 10, 78), "Server aktif", font=F_KECIL2, fill=REDUP2)
    d.text((PAD + 10, 92), "Whyu Test", font=F_TEKS, fill=TEKS)

    y = 136
    for judul, anggota in (
        ("PEMANTAUAN", ("Ringkasan", "AI & Privasi")),
        ("ANGGOTA & PESAN", ("Sambutan & pamit", "Inti & ekonomi", "Tiket & ultah")),
        ("KEAMANAN", ("Keamanan", "Moderasi")),
        ("KONTEN", ("Konten & interaksi", "Buat konten", "Kirim", "Panel", "Giveaway")),
        ("LAINNYA", ("Bangun server", "Ekspor")),
    ):
        d.text((PAD, y), judul, font=F_KECIL2, fill=REDUP2)
        y += 16
        x = PAD
        for nama in anggota:
            lebar = d.textlength(nama, font=F_KECIL)
            if x + lebar + 18 > sisi - PAD:
                x = PAD
                y += 26
            aktif = nama == "Konten & interaksi"
            _kotak(
                d,
                (x, y, x + lebar + 16, y + 20),
                radius=10,
                fill=(60, 52, 110) if aktif else (36, 38, 48),
                outline=AKSEN if aktif else GARIS,
            )
            d.text((x + 8, y + 4), nama, font=F_KECIL, fill=TEKS if aktif else REDUP)
            x += lebar + 22
        y += 34

    # ---------------- Konten ----------------
    x0 = sisi + 26
    d.text((x0, 22), "KONTEN", font=F_KECIL2, fill=PINK)
    d.text((x0, 38), "Konten & interaksi", font=F_JUDUL, fill=TEKS)
    d.text(
        (x0, 66),
        "Fitur AI per channel, starboard, kotak saran, tag siap pakai,",
        font=F_TEKS,
        fill=REDUP,
    )
    d.text((x0, 84), "highlight kata kunci, dan backup.", font=F_TEKS, fill=REDUP)

    # Kotak daftar isi
    y = 118
    _kotak(d, (x0, y, LEBAR - PAD, y + 105), radius=11, fill=KARTU, outline=GARIS)
    d.text((x0 + 14, y + 11), "ISI HALAMAN  ·  9 BAGIAN", font=F_KECIL2, fill=REDUP2)
    d.text(
        (LEBAR - PAD - 128, y + 11),
        "klik untuk melompat",
        font=F_KECIL2,
        fill=AKSEN,
    )
    chip = [
        "Konten & interaksi",
        "Tag jawaban",
        "Highlight kata kunci",
        "Curhat anonim",
        "Notifikasi sosial",
        "Voice linking",
        "Musik",
        "Channel info",
        "Statistik",
    ]
    cx, cy = x0 + 14, y + 32
    for nama in chip:
        lebar = d.textlength(nama, font=F_KECIL)
        if cx + lebar + 18 > LEBAR - PAD - 14:
            cx = x0 + 14
            cy += 26
        cx = _pil(d, (cx, cy), nama, F_KECIL, TEKS) + 8

    # Panel contoh
    py = cy + 36
    d.text((x0, py), "Tag jawaban siap pakai", font=F_H2, fill=TEKS)
    d.text((x0, py + 22), "Balasan instan untuk pertanyaan yang sering muncul.", font=F_TEKS, fill=REDUP)
    py += 46
    for nama, isi in (
        ("faq", "Jawaban FAQ server ini"),
        ("rules", "Tautan ke peraturan"),
        ("sosmed", "Akun sosial media resmi"),
    ):
        _kotak(d, (x0, py, LEBAR - PAD, py + 40), radius=9, fill=KARTU, outline=GARIS)
        _kotak(d, (x0 + 10, py + 9, x0 + 86, py + 31), radius=6, fill=LATAR, outline=GARIS)
        d.text((x0 + 18, py + 13), nama, font=F_KECIL, fill=AKSEN)
        d.text((x0 + 100, py + 13), isi, font=F_KECIL, fill=REDUP)
        py += 48

    # Keterangan bawah
    d.text(
        (x0, TINGGI - 30),
        "Sebelumnya: 9 bagian berderet tanpa pintasan — pengguna harus scroll untuk menemukannya.",
        font=F_KECIL2,
        fill=REDUP2,
    )

    img.save(KELUAR, "PNG")
    print(f"tersimpan: {KELUAR} {img.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
