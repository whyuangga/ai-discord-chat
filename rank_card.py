"""Kartu rank PNG (Pillow) — satu perender untuk Discord **dan** pratinjau dashboard.

Kenapa satu modul?
    Arclo merender kartu rank dengan perender yang **sama** untuk gambar yang dikirim
    ke Discord dan pratinjau di browsernya. Itu menghindari "pratinjau bagus, hasil
    beda". Di sini kontraknya sama: `render_kartu()` dipakai `/level kartu`
    (lampiran PNG) dan `GET /api/rank.png` (pratinjau di halaman **Inti & level**).

Prinsip:
    - **Tanpa dependency baru** — Pillow sudah dipakai kartu sambutan (`welcome_media`).
    - **0 kuota AI** — semua angka dari `levels.py`.
    - **Gagal dengan tenang** — Pillow tidak ada / avatar rusak → `None`, dan pemanggil
      otomatis memakai embed teks biasa (`/level lihat`).
    - **Latar bisa diunggah** — slot `rank` di `data/media/` (dashboard: Inti & level).
"""

import asyncio
import io
import logging

logger = logging.getLogger("gemini_bot.rank_card")

#: Ukuran kanvas kartu rank (16:9 ringkas, nyaman dibuka di HP).
KARTU_UKURAN: tuple[int, int] = (1024, 360)

#: Slot unggahan latar kartu (`data/media/rank_<guild>.png`).
JENIS_LATAR = "rank"

#: Warna dasar gelap sesuai tema dashboard (`#0D0D0F`).
_DASAR = (13, 13, 15)
_TEKS = (255, 255, 255)
_TEKS_LEMBUT = (176, 172, 190)

_FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "DejaVuSans-Bold.ttf",
)


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def kartu_aktif(guild_id: int) -> bool:
    """True bila kartu rank diizinkan di server ini (setelan dashboard)."""
    import levels

    cfg = levels.peek_level_config(int(guild_id or 0)) or {}
    if "kartu_aktif" not in cfg:
        return True
    return bool(cfg.get("kartu_aktif"))


def hex_warna(nilai: object) -> str:
    """Menormalkan warna hex `#RRGGBB`/`RRGGBB`; '' bila tidak sah."""
    teks = str(nilai or "").strip().lstrip("#")
    if len(teks) != 6:
        return ""
    try:
        int(teks, 16)
    except ValueError:
        return ""
    return "#" + teks.upper()


def warna_aksen(guild_id: int) -> tuple[int, int, int]:
    """Warna aksen kartu: `kartu_warna` server, atau aksen tema dashboard."""
    import levels

    cfg = levels.peek_level_config(int(guild_id or 0)) or {}
    sah = hex_warna(cfg.get("kartu_warna"))
    if sah:
        return (int(sah[1:3], 16), int(sah[3:5], 16), int(sah[5:7], 16))
    try:
        import ui_theme

        warna = ui_theme.accent_color(int(guild_id or 0))
        nilai = _to_int(getattr(warna, "value", 0), 0)
    except Exception:  # pragma: no cover - tema belum siap
        nilai = 0
    if not nilai:
        return (88, 101, 242)  # blurple Discord
    return ((nilai >> 16) & 0xFF, (nilai >> 8) & 0xFF, nilai & 0xFF)


def latar_bytes(guild_id: int) -> bytes | None:
    """Isi berkas latar kartu rank (bila server sudah mengunggahnya)."""
    import welcome_media

    return welcome_media.read_banner_bytes(int(guild_id or 0), kind=JENIS_LATAR)


def ada_latar(guild_id: int) -> bool:
    import welcome_media

    return welcome_media.has_banner(int(guild_id or 0), kind=JENIS_LATAR)


# ==============================================================================
# DATA
# ==============================================================================
def data_kartu(
    guild_id: int,
    user_id: int,
    *,
    nama: str = "",
    guild_name: str = "",
) -> dict:
    """Semua angka yang tampil di kartu (aman walau member belum pernah chat)."""
    import levels

    gid = _to_int(guild_id)
    uid = _to_int(user_id)
    data = levels.get_member_level(gid, uid)
    posisi, peserta = levels.rank_position(gid, uid)
    musim = levels.season_info(gid) if hasattr(levels, "season_info") else {}
    cfg = levels.peek_level_config(gid) or {}
    return {
        "guild_id": gid,
        "user_id": uid,
        "nama": str(nama or "Member")[:32],
        "guild_name": str(guild_name or "")[:40],
        "level": _to_int(data.get("level")),
        "xp": _to_int(data.get("xp")),
        "current": _to_int(data.get("current")),
        "needed": max(1, _to_int(data.get("needed"), 1)),
        "prestige": _to_int(data.get("prestige")),
        "messages": _to_int(data.get("messages")),
        "voice_min": _to_int(data.get("voice_min_today")),
        "posisi": posisi,
        "peserta": peserta,
        "musim": _to_int((musim or {}).get("musim"), _to_int(cfg.get("season"), 1)) or 1,
        "warna": warna_aksen(gid),
        # `level_aktif` = sistem level menyala; `kartu_aktif` = kartu rank diizinkan.
        # Pratinjau dashboard sengaja tetap boleh dirender walau kartu dimatikan,
        # supaya Admin bisa melihat hasilnya dulu sebelum menyalakan.
        "level_aktif": bool(cfg.get("enabled", True)),
        "kartu_aktif": bool(cfg.get("kartu_aktif", True)),
    }


def baris_data(data: dict) -> list[str]:
    """Ringkasan teks kartu (dipakai embed cadangan & pesan dashboard)."""
    posisi = data.get("posisi") or 0
    peserta = data.get("peserta") or 0
    peringkat = f"#{posisi} / {peserta}" if posisi and peserta else "belum diperingkat"
    baris = [
        f"Level **{data.get('level', 0)}** · {data.get('current', 0):,}/{data.get('needed', 1):,} XP",
        f"Peringkat {peringkat}",
        f"Musim {data.get('musim', 1)} · {data.get('messages', 0):,} pesan · "
        f"{data.get('voice_min', 0)} menit voice hari ini",
    ]
    if data.get("prestige"):
        baris.append(f"Prestise ×{data.get('prestige')}")
    return baris


# ==============================================================================
# PERENDERAN (PILLOW, DIMUAT MALAS)
# ==============================================================================
def pillow_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("PIL") is not None


def _load_font(size: int):
    from PIL import ImageFont

    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _potong(draw, teks: str, font, lebar: int) -> str:
    """Potong teks agar tidak melewati `lebar` piksel (pakai elipsis)."""
    teks = str(teks or "")
    if not teks:
        return ""
    try:
        if draw.textlength(teks, font=font) <= lebar:
            return teks
    except Exception:  # pragma: no cover - font bitmap bawaan
        return teks[:32]
    while teks and draw.textlength(teks + "…", font=font) > lebar:
        teks = teks[:-1]
    return (teks + "…") if teks else "…"


def _campur(a: tuple[int, int, int], b: tuple[int, int, int], rasio: float) -> tuple[int, int, int]:
    rasio = max(0.0, min(1.0, float(rasio)))
    return tuple(int(a[i] + (b[i] - a[i]) * rasio) for i in range(3))  # type: ignore[return-value]


def _latar(data: dict):
    """Latar kartu: banner unggahan (dipotong penuh) atau gradasi warna aksen."""
    from PIL import Image

    lebar, tinggi = KARTU_UKURAN
    isi = latar_bytes(data.get("guild_id", 0))
    if isi:
        try:
            import welcome_media

            gambar = Image.open(io.BytesIO(isi)).convert("RGBA")
            return welcome_media._cover(gambar, KARTU_UKURAN)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - berkas rusak
            logger.warning("Latar kartu rank tidak bisa dibaca (%s) — memakai gradasi.", exc)

    warna = data.get("warna") or (88, 101, 242)
    kanvas = Image.new("RGBA", KARTU_UKURAN, _DASAR + (255,))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(kanvas)
    for y in range(tinggi):
        rasio = y / max(1, tinggi - 1)
        garis = _campur(_campur(_DASAR, warna, 0.35), _DASAR, rasio * 0.9)
        draw.line([(0, y), (lebar, y)], fill=garis + (255,))
    return kanvas


def _avatar_bulat(avatar_bytes: bytes, ukuran: int):
    from PIL import Image, ImageDraw, ImageOps

    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar = ImageOps.fit(avatar, (ukuran, ukuran), Image.LANCZOS)
    mask = Image.new("L", (ukuran, ukuran), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, ukuran, ukuran), fill=255)
    avatar.putalpha(mask)
    return avatar


def _render_sync(data: dict, avatar_bytes: bytes | None) -> bytes:
    """Menyusun kartu rank (dijalankan di thread terpisah)."""
    from PIL import Image, ImageDraw

    lebar, tinggi = KARTU_UKURAN
    kanvas = _latar(data).copy()

    # Panel gelap supaya teks selalu terbaca walau latar terang.
    selubung = Image.new("RGBA", KARTU_UKURAN, (0, 0, 0, 0))
    draw = ImageDraw.Draw(selubung)
    draw.rectangle([(0, 0), (lebar, tinggi)], fill=_DASAR + (150,))
    draw.rectangle([(0, 0), (8, tinggi)], fill=(data.get("warna") or (88, 101, 242)) + (255,))
    kanvas = Image.alpha_composite(kanvas, selubung)

    avatar_ukuran = 152
    posisi_x = 56
    avatar_y = (tinggi - avatar_ukuran) // 2
    if avatar_bytes:
        try:
            avatar = _avatar_bulat(avatar_bytes, avatar_ukuran)
            cincin = Image.new("RGBA", (avatar_ukuran + 14, avatar_ukuran + 14), (0, 0, 0, 0))
            ImageDraw.Draw(cincin).ellipse(
                (0, 0, avatar_ukuran + 13, avatar_ukuran + 13),
                outline=(data.get("warna") or (88, 101, 242)) + (255,),
                width=7,
            )
            cincin.paste(avatar, (7, 7), avatar)
            kanvas.alpha_composite(cincin, (posisi_x - 7, avatar_y - 7))
        except Exception as exc:  # pragma: no cover - avatar rusak
            logger.debug("Avatar kartu rank gagal dirender: %s", exc)
    else:
        # Placeholder: inisial nama di lingkaran aksen.
        lingkaran = Image.new("RGBA", (avatar_ukuran, avatar_ukuran), (0, 0, 0, 0))
        draw_ling = ImageDraw.Draw(lingkaran)
        draw_ling.ellipse(
            (0, 0, avatar_ukuran - 1, avatar_ukuran - 1),
            fill=_campur(_DASAR, data.get("warna") or (88, 101, 242), 0.55) + (255,),
        )
        inisial = (str(data.get("nama") or "?").strip()[:1] or "?").upper()
        font_inisial = _load_font(64)
        try:
            kotak = draw_ling.textbbox((0, 0), inisial, font=font_inisial)
            draw_ling.text(
                (
                    (avatar_ukuran - (kotak[2] - kotak[0])) // 2 - kotak[0],
                    (avatar_ukuran - (kotak[3] - kotak[1])) // 2 - kotak[1],
                ),
                inisial,
                font=font_inisial,
                fill=_TEKS + (255,),
            )
        except Exception:  # pragma: no cover - font bitmap
            pass
        kanvas.alpha_composite(lingkaran, (posisi_x, avatar_y))

    draw = ImageDraw.Draw(kanvas)
    teks_x = posisi_x + avatar_ukuran + 44
    teks_lebar = lebar - teks_x - 56
    aksen = (data.get("warna") or (88, 101, 242)) + (255,)

    font_nama = _load_font(44)
    font_level = _load_font(34)
    font_kecil = _load_font(22)
    font_peringkat = _load_font(30)
    font_footer = _load_font(20)

    # Nama member
    draw.text(
        (teks_x, 52),
        _potong(draw, data.get("nama") or "Member", font_nama, teks_lebar - 190),
        font=font_nama,
        fill=_TEKS + (255,),
    )

    # Lencana level (+ prestise)
    lencana = f"LEVEL {data.get('level', 0)}"
    if data.get("prestige"):
        # Tanpa emoji: font bawaan server tidak selalu punya glyph ✨ (jadi kotak kosong).
        lencana += f"  ·  PRESTISE ×{_to_int(data.get('prestige'))}"
    draw.text((teks_x, 112), lencana, font=font_level, fill=aksen)

    # Peringkat (kanan atas)
    posisi = data.get("posisi") or 0
    peserta = data.get("peserta") or 0
    label_peringkat = f"#{posisi}" if posisi else "—"
    try:
        lebar_peringkat = draw.textlength(label_peringkat, font=font_peringkat)
    except Exception:  # pragma: no cover
        lebar_peringkat = 3 * len(label_peringkat)
    draw.text(
        (lebar - 56 - lebar_peringkat, 56),
        label_peringkat,
        font=font_peringkat,
        fill=_TEKS + (255,),
    )
    sub = f"dari {peserta} peserta" if peserta else "belum diperingkat"
    try:
        lebar_sub = draw.textlength(sub, font=font_kecil)
    except Exception:  # pragma: no cover
        lebar_sub = 8 * len(sub)
    draw.text(
        (lebar - 56 - lebar_sub, 96),
        sub,
        font=font_kecil,
        fill=_TEKS_LEMBUT + (255,),
    )

    # Progress bar
    bar_x, bar_y, bar_h = teks_x, 190, 20
    bar_lebar = lebar - bar_x - 56
    draw.rounded_rectangle(
        [(bar_x, bar_y), (bar_x + bar_lebar, bar_y + bar_h)],
        radius=bar_h // 2,
        fill=(255, 255, 255, 40),
    )
    needed = max(1, _to_int(data.get("needed"), 1))
    rasio = max(0.0, min(1.0, _to_int(data.get("current")) / needed))
    isi_lebar = int(bar_lebar * rasio)
    if isi_lebar >= bar_h:
        draw.rounded_rectangle(
            [(bar_x, bar_y), (bar_x + isi_lebar, bar_y + bar_h)],
            radius=bar_h // 2,
            fill=aksen,
        )
    elif isi_lebar > 0:
        draw.rectangle([(bar_x, bar_y), (bar_x + isi_lebar, bar_y + bar_h)], fill=aksen)

    draw.text(
        (bar_x, bar_y + bar_h + 12),
        f"{_to_int(data.get('current')):,} / {needed:,} XP  ·  total {_to_int(data.get('xp')):,} XP",
        font=font_kecil,
        fill=_TEKS_LEMBUT + (255,),
    )

    # Footer: server · musim · aktivitas (segmen dibuang dari belakang agar tidak terpotong).
    footer: list[str] = []
    if data.get("guild_name"):
        footer.append(str(data.get("guild_name")))
    footer.append(f"Musim {data.get('musim', 1)}")
    footer.append(f"{_to_int(data.get('messages')):,} pesan")
    if _to_int(data.get("voice_min")):
        footer.append(f"{_to_int(data.get('voice_min'))} mnt voice")
    while len(footer) > 1:
        kandidat = "  ·  ".join(footer)
        try:
            if draw.textlength(kandidat, font=font_footer) <= teks_lebar:
                break
        except Exception:  # pragma: no cover - font bitmap
            break
        footer.pop()
    draw.text(
        (teks_x, tinggi - 54),
        _potong(draw, "  ·  ".join(footer), font_footer, lebar=teks_lebar),
        font=font_footer,
        fill=_TEKS_LEMBUT + (255,),
    )

    buffer = io.BytesIO()
    kanvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


async def render_kartu(
    data: dict,
    *,
    avatar_bytes: bytes | None = None,
) -> bytes | None:
    """Membuat kartu rank (PNG). `None` bila Pillow tidak ada atau render gagal."""
    if not data:
        return None
    if not pillow_available():
        logger.info("Pillow tidak tersedia — kartu rank dilewati.")
        return None
    try:
        return await asyncio.to_thread(_render_sync, data, avatar_bytes)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal merender kartu rank: %s", exc)
        return None


async def baca_avatar(orang) -> bytes | None:
    """Byte foto profil (None bila tidak ada / gagal diunduh)."""
    avatar = getattr(orang, "display_avatar", None)
    if avatar is None:
        return None
    try:
        return await avatar.with_size(256).read()
    except Exception:  # pragma: no cover - CDN lambat / izin
        return None


async def render_untuk_member(
    orang,
    *,
    guild_id: int,
    guild_name: str = "",
    avatar_bytes: bytes | None = None,
) -> bytes | None:
    """Kartu rank siap kirim untuk seorang member (`discord.Member`)."""
    data = data_kartu(
        guild_id,
        getattr(orang, "id", 0),
        nama=getattr(orang, "display_name", "") or getattr(orang, "name", ""),
        guild_name=guild_name,
    )
    if avatar_bytes is None:
        avatar_bytes = await baca_avatar(orang)
    return await render_kartu(data, avatar_bytes=avatar_bytes)


# ==============================================================================
# PESAN CADANGAN (TANPA PILLOW)
# ==============================================================================
def pesan_cadangan(data: dict) -> str:
    """Teks pengganti bila kartu PNG tidak bisa dibuat."""
    return "\n".join(baris_data(data))
