"""Render gambar pratinjau panel sambutan (alat bantu, bukan bagian bot).

Membuat PNG dari struktur HTML yang sama dengan `dashboard_sambutan`, memakai
Pillow + font DejaVu. Dipakai untuk dokumentasi & tangkapan layar saat browser
tidak tersedia; tidak dipanggil oleh bot saat berjalan.

    python3 tools/demo/sambutan_gambar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont

import community_agent
import welcome_view

KELUAR = Path("/home/user/pratinjau-sambutan.png")

# Palet gelap dashboard (mendekati dashboard_tema.py).
LATAR = (16, 18, 24)
KARTU = (26, 29, 38)
KARTU2 = (33, 37, 48)
GARIS = (52, 58, 74)
TEKS = (232, 235, 245)
REDUP = (156, 164, 184)
REDUP2 = (116, 124, 144)
AKSEN = (235, 69, 158)
AKSEN2 = (88, 101, 242)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
F_NORMAL = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf", 15)
F_KECIL = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf", 13)
F_KECIL2 = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf", 12)
F_TEBAL = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", 17)
F_JUDUL = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", 21)
F_AVATAR = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", 26)

GID = 1
LEBAR = 760
PAD = 24


def tanpa_emoji(teks: str) -> str:
    """Buang emoji: font DejaVu tidak punya glyph-nya (akan jadi kotak kosong)."""
    bersih = "".join(
        ch for ch in str(teks) if unicodedata.category(ch) not in ("So", "Sk", "Cs")
    )
    return re.sub(r"\s{2,}", " ", bersih).strip()


def _teks_terbungkus(draw, teks, font, lebar):
    """Pecah teks jadi baris sesuai lebar piksel."""
    baris, sekarang = [], ""
    for kata in str(teks).split():
        coba = f"{sekarang} {kata}".strip()
        if draw.textlength(coba, font=font) <= lebar:
            sekarang = coba
        else:
            if sekarang:
                baris.append(sekarang)
            sekarang = kata
    if sekarang:
        baris.append(sekarang)
    return baris or [""]


def _kotak(draw, xy, radius=14, fill=KARTU, outline=GARIS, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def gambar():
    data = {
        "welcome": {
            "mode": "container",
            "teks": "Hai Anggota Baru! Selamat datang di Whyu Test",
            "template": "Selamat datang **{user_mention}** di **{server}**! Kamu member ke-{member_count}",
        },
        "goodbye": {
            "mode": "embed",
            "teks": "Sampai jumpa, Anggota Baru",
            "template": "Sampai jumpa, **{user_name}**. Terima kasih sudah di **{server}**",
        },
    }
    tinggi_total = 1030
    img = Image.new("RGB", (LEBAR, tinggi_total), LATAR)
    d = ImageDraw.Draw(img)

    y = PAD
    # ---- header panel ----
    d.text((PAD, y), tanpa_emoji("👋 Sambutan & pamit"), font=F_JUDUL, fill=TEKS)
    y += 32
    for baris in _teks_terbungkus(
        d,
        "Empat mode tampilan: Card, Embed, Text, Container. Pilih mode, isi template, "
        "lihat pratinjau, lalu simpan.",
        F_KECIL,
        LEBAR - PAD * 2,
    ):
        d.text((PAD, y), baris, font=F_KECIL, fill=REDUP)
        y += 19
    y += 14

    # ---- kartu panel tampilan ----
    akhir = 980
    _kotak(d, (PAD - 8, y, LEBAR - PAD + 8, akhir))
    y += 18
    d.text((PAD, y), tanpa_emoji("🎨 Tampilan pesan"), font=F_TEBAL, fill=TEKS)
    y += 30

    for kind, label in (("welcome", "👋 Sambutan member baru"), ("goodbye", "👣 Pesan perpisahan")):
        info = data[kind]
        mode = info["mode"]

        _kotak(d, (PAD, y, LEBAR - PAD, y + 330), radius=12, fill=KARTU2, outline=GARIS)
        pad_dalam = PAD + 14
        y += 14
        d.text((pad_dalam, y), tanpa_emoji(label), font=F_TEBAL, fill=TEKS)
        y += 28

        # deretan tombol mode
        lebar_tombol = (LEBAR - PAD * 2 - 28 - 3 * 8) // 4
        for i, (kunci, meta) in enumerate(welcome_view.VIEW_MODES.items()):
            x0 = pad_dalam + i * (lebar_tombol + 8)
            aktif = kunci == mode
            _kotak(
                d,
                (x0, y, x0 + lebar_tombol, y + 40),
                radius=9,
                fill=AKSEN if aktif else LATAR,
                outline=AKSEN if aktif else GARIS,
            )
            teks = f"{meta['emoji']} {meta['label']}"
            w = d.textlength(tanpa_emoji(teks), font=F_KECIL)
            d.text(
                (x0 + (lebar_tombol - w) / 2, y + 11),
                tanpa_emoji(teks),
                font=F_KECIL,
                fill=(255, 255, 255) if aktif else REDUP,
            )
        y += 54

        # pratinjau
        d.text((pad_dalam, y), tanpa_emoji(f"PRATINJAU · {mode.upper()}"), font=F_KECIL2, fill=REDUP2)
        y += 20
        kotak_y = y
        _kotak(d, (pad_dalam, kotak_y, LEBAR - PAD - 14, kotak_y + 150), radius=10, fill=LATAR)

        isi_x = pad_dalam + 12
        isi_y = kotak_y + 12
        if mode == "container":
            d.rounded_rectangle(
                (isi_x, isi_y, LEBAR - PAD - 26, isi_y + 126), radius=10, outline=AKSEN, width=2
            )
            d.text((isi_x + 12, isi_y + 12), tanpa_emoji("👋 Selamat Datang!"), font=F_TEBAL, fill=TEKS)
            baris = _teks_terbungkus(d, info["teks"], F_KECIL, LEBAR - PAD - 90)
            yy = isi_y + 40
            for b in baris:
                d.text((isi_x + 12, yy), b, font=F_KECIL, fill=TEKS)
                yy += 20
            d.text((isi_x + 12, isi_y + 100), tanpa_emoji("Whyu Test • member ke-3"), font=F_KECIL2, fill=REDUP2)
        else:  # embed
            d.rectangle((isi_x, isi_y + 4, isi_x + 4, isi_y + 118), fill=AKSEN2)
            d.text((isi_x + 16, isi_y + 10), tanpa_emoji("👣 Sampai Jumpa!"), font=F_TEBAL, fill=TEKS)
            d.text((isi_x + 16, isi_y + 40), info["teks"], font=F_KECIL, fill=TEKS)
            d.text((isi_x + 16, isi_y + 108), tanpa_emoji("Whyu Test"), font=F_KECIL2, fill=REDUP2)

        y = kotak_y + 166
        # slot unggah gambar (untuk mode Card)
        _kotak(d, (pad_dalam, y, LEBAR - PAD - 14, y + 62), radius=9, fill=KARTU, outline=GARIS)
        d.text((pad_dalam + 12, y + 8), "Gambar kartu (untuk mode Card)", font=F_KECIL, fill=TEKS)
        _kotak(d, (pad_dalam + 12, y + 28, pad_dalam + 210, y + 54), radius=6, fill=LATAR, outline=GARIS)
        d.text((pad_dalam + 22, y + 34), "Pilih berkas…", font=F_KECIL2, fill=REDUP2)
        _kotak(d, (pad_dalam + 220, y + 28, pad_dalam + 322, y + 54), radius=6, fill=AKSEN2, outline=AKSEN2)
        lebar_tombol_unggah = d.textlength("Unggah gambar", font=F_KECIL2)
        d.text(
            (pad_dalam + 220 + (102 - lebar_tombol_unggah) / 2, y + 34),
            "Unggah gambar",
            font=F_KECIL2,
            fill=(255, 255, 255),
        )
        d.text((pad_dalam + 334, y + 35), "1024x420 px - maks 8 MB", font=F_KECIL2, fill=REDUP2)
        y += 76
        # textarea template
        _kotak(d, (pad_dalam, y, LEBAR - PAD - 14, y + 46), radius=9, fill=LATAR)
        d.text(
            (pad_dalam + 12, y + 14),
            "Template: " + info["template"],
            font=F_KECIL,
            fill=REDUP,
        )
        y += 60
        _kotak(d, (pad_dalam, y, pad_dalam + 150, y + 32), radius=8, fill=AKSEN2, outline=AKSEN2)
        d.text((pad_dalam + 24, y + 8), tanpa_emoji("Simpan template"), font=F_KECIL, fill=(255, 255, 255))
        y += 48

    img.save(KELUAR)
    print("tersimpan:", KELUAR, img.size)
    return KELUAR


if __name__ == "__main__":
    # Pakai template sungguhan dari modul agar gambar tidak menampilkan teks palsu.
    community_agent.welcome_agent_guilds[GID] = community_agent.set_welcome_config(
        GID, 600, enabled=True
    )
    community_agent.set_welcome_card_mode(GID, "container")
    print("template bawaan:", welcome_view.template_bawaan("welcome")[:60])
    gambar()
