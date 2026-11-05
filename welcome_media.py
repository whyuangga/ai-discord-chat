"""Penyimpanan & perender gambar kustom (banner sambutan, perpisahan, & boost).

Kenapa file disimpan lokal, bukan URL?
    URL lampiran Discord (`cdn.discordapp.com/attachments/...`) mengandung tanda tangan
    yang **kedaluwarsa ±24 jam**. Kalau hanya URL-nya yang disimpan, banner akan hilang
    keesokan harinya. Jadi berkasnya disimpan di `data/media/` dan dikirim ulang
    sebagai lampiran setiap kali dibutuhkan (`attachment://`).

Mode tampilan sambutan:
    - `mati`    → sambutan teks biasa (perilaku lama, paling hemat)
    - `statis`  → embed dengan banner yang di-upload Admin
    - `dinamis` → banner + foto profil member + nama, dirakit dengan Pillow

Pillow hanya diimpor **saat mode dinamis benar-benar dipakai** agar RAM Free Tier aman.
"""

import asyncio
import io
import logging
import re
from pathlib import Path

from config import MEDIA_DIR

logger = logging.getLogger("gemini_bot.welcome_media")

CARD_MODES: dict[str, dict] = {
    "mati": {"label": "Teks saja (paling hemat)", "emoji": "💬"},
    "statis": {"label": "Banner gambar dari Admin", "emoji": "🖼️"},
    "dinamis": {"label": "Kartu dinamis (avatar + nama)", "emoji": "✨"},
}

ALLOWED_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_BANNER_BYTES = 8 * 1024 * 1024  # batas unggah Discord untuk pengguna biasa

CARD_SIZE: tuple[int, int] = (1024, 420)
AVATAR_SIZE = 168

_FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "DejaVuSans-Bold.ttf",
)


# ==============================================================================
# PENYIMPANAN BERKAS
# ==============================================================================
def media_dir() -> Path:
    """Folder penyimpanan gambar (dibuat otomatis bila belum ada)."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return MEDIA_DIR


def normalize_extension(filename: str | None) -> str:
    """Ekstensi aman yang diizinkan (default `.png`)."""
    suffix = Path(str(filename or "")).suffix.lower()
    return suffix if suffix in ALLOWED_EXTENSIONS else ".png"


def banner_filename(guild_id: int, kind: str = "welcome") -> str:
    """Nama berkas banner milik server (mis. `welcome_123.png`)."""
    safe_kind = re.sub(r"[^a-z0-9_]", "", str(kind).lower())[:20] or "welcome"
    return f"{safe_kind}_{int(guild_id)}{_stored_suffix(guild_id, safe_kind)}"


def _stored_suffix(guild_id: int, kind: str) -> str:
    """Ekstensi yang sedang tersimpan untuk server ini (`.png` bila belum ada)."""
    for path in media_dir().glob(f"{kind}_{int(guild_id)}.*"):
        if path.suffix.lower() in ALLOWED_EXTENSIONS:
            return path.suffix.lower()
    return ".png"


def banner_path(guild_id: int, kind: str = "welcome") -> Path | None:
    """Lokasi banner tersimpan, atau `None` bila server belum mengunggahnya."""
    for path in media_dir().glob(f"{kind}_{int(guild_id)}.*"):
        if path.suffix.lower() in ALLOWED_EXTENSIONS and path.is_file():
            return path
    return None


def has_banner(guild_id: int, kind: str = "welcome") -> bool:
    return banner_path(guild_id, kind) is not None


def save_banner(guild_id: int, data: bytes, filename: str | None = None, *, kind: str = "welcome") -> Path:
    """Menyimpan banner server (menimpa yang lama, termasuk beda ekstensi)."""
    if not data:
        raise ValueError("Berkas gambar kosong.")
    if len(data) > MAX_BANNER_BYTES:
        raise ValueError("Ukuran gambar melebihi 8 MB — perkecil dulu lalu unggah lagi.")

    delete_banner(guild_id, kind=kind)
    target = media_dir() / f"{kind}_{int(guild_id)}{normalize_extension(filename)}"
    target.write_bytes(data)
    logger.info("Banner %s server %s disimpan (%d KB).", kind, guild_id, len(data) // 1024)
    return target


def delete_banner(guild_id: int, *, kind: str = "welcome") -> bool:
    """Menghapus banner server. `True` bila ada berkas yang terhapus."""
    removed = False
    for path in media_dir().glob(f"{kind}_{int(guild_id)}.*"):
        try:
            path.unlink()
            removed = True
        except OSError:  # pragma: no cover - izin berkas
            continue
    return removed


def media_footprint_mb() -> float:
    """Total ukuran gambar tersimpan (MB) — untuk log startup & pemantauan RAM disk."""
    total = 0
    for path in media_dir().glob("*.*"):
        try:
            total += path.stat().st_size
        except OSError:  # pragma: no cover
            continue
    return round(total / (1024 * 1024), 2)


# ==============================================================================
# PERENDERAN KARTU (PILLOW, DIMUAT MALAS)
# ==============================================================================
def pillow_available() -> bool:
    """True bila Pillow terpasang (dipakai untuk mode kartu dinamis)."""
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


def _cover(image, size: tuple[int, int]):
    """Potong & skala gambar agar menutupi seluruh kanvas (seperti `object-fit: cover`)."""
    from PIL import Image

    target_w, target_h = size
    src_w, src_h = image.size
    if not src_w or not src_h:
        return image.resize(size)
    scale = max(target_w / src_w, target_h / src_h)
    new_size = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    left = (new_size[0] - target_w) // 2
    top = (new_size[1] - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _circular(avatar_bytes: bytes, size: int):
    """Membuat avatar bulat dengan latar transparan."""
    from PIL import Image, ImageDraw, ImageOps

    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar = ImageOps.fit(avatar, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    avatar.putalpha(mask)
    return avatar


def _render_sync(
    banner_bytes: bytes | None,
    avatar_bytes: bytes | None,
    title: str,
    subtitle: str,
    footer: str,
) -> bytes:
    """Menyusun kartu sambutan (dijalankan di thread terpisah)."""
    from PIL import Image, ImageDraw

    if banner_bytes:
        try:
            background = _cover(Image.open(io.BytesIO(banner_bytes)).convert("RGBA"), CARD_SIZE)
        except Exception as exc:  # pragma: no cover - berkas rusak
            logger.warning("Banner tidak bisa dibaca (%s) — memakai latar gradasi.", exc)
            background = None
    else:
        background = None

    if background is None:
        width, height = CARD_SIZE
        background = Image.new("RGBA", CARD_SIZE, (32, 30, 46, 255))
        draw = ImageDraw.Draw(background)
        for y in range(height):
            ratio = y / max(1, height - 1)
            draw.line(
                [(0, y), (width, y)],
                fill=(int(60 + 40 * ratio), int(30 + 25 * ratio), int(120 + 40 * ratio), 255),
            )

    canvas = background.copy()
    width, height = canvas.size
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Panel gelap di kiri agar teks selalu terbaca walau banner terang
    draw.rectangle([(0, 0), (int(width * 0.62), height)], fill=(12, 10, 24, 165))
    draw.rectangle([(0, height - 96), (width, height)], fill=(10, 8, 20, 185))
    canvas = Image.alpha_composite(canvas, overlay)

    avatar_size = AVATAR_SIZE
    if avatar_bytes:
        try:
            avatar = _circular(avatar_bytes, avatar_size)
            ring = Image.new("RGBA", (avatar_size + 12, avatar_size + 12), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse((0, 0, avatar_size + 11, avatar_size + 11), fill=(155, 89, 182, 255))
            ring.paste(avatar, (6, 6), avatar)
            canvas.alpha_composite(ring, (48, (height - avatar_size - 12) // 2))
        except Exception as exc:  # pragma: no cover - avatar rusak
            logger.debug("Avatar gagal dirender: %s", exc)

    draw = ImageDraw.Draw(canvas)
    text_x = 48 + (avatar_size + 30 if avatar_bytes else 0)
    title_font = _load_font(56)
    subtitle_font = _load_font(32)
    footer_font = _load_font(24)

    y = height // 2 - 92
    draw.text((text_x, y), title[:28], font=title_font, fill=(255, 255, 255, 255))
    y += 76
    for line in subtitle.split("\n")[:2]:
        draw.text((text_x, y), line[:42], font=subtitle_font, fill=(226, 220, 240, 255))
        y += 42
    draw.text((48, height - 66), footer[:80], font=footer_font, fill=(196, 190, 214, 255))

    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


async def render_card(
    *,
    banner_bytes: bytes | None = None,
    avatar_bytes: bytes | None = None,
    title: str = "",
    subtitle: str = "",
    footer: str = "",
) -> bytes | None:
    """Membuat kartu sambutan (PNG). `None` bila Pillow tidak tersedia/gagal."""
    if not pillow_available():
        logger.info("Pillow tidak tersedia — mode kartu dinamis dilewati.")
        return None
    try:
        return await asyncio.to_thread(
            _render_sync, banner_bytes, avatar_bytes, title, subtitle, footer
        )
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal merender kartu dinamis: %s", exc)
        return None


def read_banner_bytes(guild_id: int, kind: str = "welcome") -> bytes | None:
    """Isi berkas banner server (untuk perenderan)."""
    path = banner_path(guild_id, kind=kind)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:  # pragma: no cover
        return None
