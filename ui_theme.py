"""Tema tampilan (UI/UX) per server — **0 kuota AI**, murni kosmetik.

Setiap server bisa mengatur tampilan seluruh panel bot lewat `/tampilan`:

- **Warna aksen** (8 preset) → dipakai kartu Components V2 & warna embed.
- **Emoji pack** → `standar` (emoji penuh) atau `minimalis` (hemat emoji).
- **Kepadatan** → `ringkas` (info penting) atau `nyaman` (detail lengkap).
- **Thumbnail** → ikon server ditampilkan atau tidak.
- **Footer** → tampilkan versi bot & RAM atau tidak.
- **Konfirmasi** → aksi berbahaya meminta konfirmasi dulu.
- **Refresh panel musik** → 5–60 detik.

Data disimpan di `data/ui_theme.json` (atomik) dan hanya berisi preferensi kecil,
sehingga tetap ringan untuk Wispbyte.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import discord

from config import DATA_DIR, BOT_VERSION
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.ui_theme")

UI_THEME_FILE: Path = DATA_DIR / "ui_theme.json"
_lock = asyncio.Lock()

# ==============================================================================
# PRESET WARNA AKSEN
# ==============================================================================
ACCENTS: dict[str, dict] = {
    "purple": {"label": "Ungu (bawaan)", "emoji": "🟣", "color": 0x9B59B6},
    "blue": {"label": "Biru", "emoji": "🔵", "color": 0x3498DB},
    "teal": {"label": "Tosca", "emoji": "🩵", "color": 0x1ABC9C},
    "green": {"label": "Hijau", "emoji": "🟢", "color": 0x57F287},
    "orange": {"label": "Oranye", "emoji": "🟠", "color": 0xE67E22},
    "red": {"label": "Merah", "emoji": "🔴", "color": 0xED4245},
    "pink": {"label": "Pink", "emoji": "🩷", "color": 0xEB459E},
    "gray": {"label": "Abu Netral", "emoji": "⚪", "color": 0x95A5A6},
}

DENSITIES: dict[str, dict] = {
    "ringkas": {"label": "Ringkas (info utama)", "emoji": "📦"},
    "nyaman": {"label": "Nyaman (detail lengkap)", "emoji": "🧾"},
}

THUMBNAIL_MODES: dict[str, dict] = {
    "ikon": {"label": "Ikon server", "emoji": "🖼️"},
    "tanpa": {"label": "Tanpa gambar", "emoji": "🚫"},
}

NAV_STYLES: dict[str, dict] = {
    "select": {"label": "Dropdown menu", "emoji": "📂"},
    "tombol": {"label": "Tombol baris", "emoji": "🔘"},
}

REFRESH_CHOICES: dict[int, str] = {
    5: "5 detik (paling segar)",
    10: "10 detik (seimbang)",
    30: "30 detik (hemat)",
    60: "60 detik (paling hemat)",
}

# ==============================================================================
# EMOJI PACK
# ==============================================================================
_EMOJI_STANDAR: dict[str, str] = {
    "ai": "🤖",
    "music": "🎵",
    "level": "📈",
    "ticket": "🎟️",
    "shield": "🛡️",
    "insight": "📊",
    "help": "❓",
    "panel": "🛰️",
    "theme": "🎨",
    "refresh": "🔄",
    "faq": "📚",
    "on": "🟢",
    "off": "🔴",
    "ok": "✅",
    "warn": "⚠️",
    "info": "ℹ️",
    "spark": "✨",
    "clock": "🕒",
    "user": "👤",
    "channel": "📍",
    "close": "🚪",
    "save": "💾",
    "reset": "↺",
    "preview": "👁️",
    "next": "▶️",
    "prev": "◀️",
}

_EMOJI_MINIMALIS: dict[str, str] = {
    "ai": "AI",
    "music": "♪",
    "level": "↑",
    "ticket": "◎",
    "shield": "◇",
    "insight": "▤",
    "help": "?",
    "panel": "▦",
    "theme": "◑",
    "refresh": "↻",
    "faq": "▤",
    "on": "✓",
    "off": "✗",
    "ok": "✓",
    "warn": "!",
    "info": "i",
    "spark": "+",
    "clock": "◷",
    "user": "▪",
    "channel": "#",
    "close": "✕",
    "save": "▣",
    "reset": "↺",
    "preview": "◉",
    "next": "›",
    "prev": "‹",
}

EMOJI_PACKS: dict[str, dict] = {
    "standar": {"label": "Standar (emoji penuh)", "emoji": "😀", "map": _EMOJI_STANDAR},
    "minimalis": {"label": "Minimalis (teks bersih)", "emoji": "▫️", "map": _EMOJI_MINIMALIS},
}

DEFAULT_THEME: dict = {
    "accent": "purple",
    "emoji_pack": "standar",
    "density": "ringkas",
    "thumbnail": "ikon",
    "footer": True,
    "confirm": True,
    "refresh": 10,
    "nav": "select",
    "updated_at": 0.0,
}

# guild_id -> dict tema (hanya field yang diubah dari default)
ui_themes: dict[int, dict] = {}


# ==============================================================================
# AKSES TEMA
# ==============================================================================
def get_theme(guild_id: int | None) -> dict:
    """Tema efektif sebuah server (default + perubahan tersimpan)."""
    theme = dict(DEFAULT_THEME)
    stored = ui_themes.get(int(guild_id or 0)) or {}
    for key, value in stored.items():
        if key in DEFAULT_THEME or key == "updated_at":
            theme[key] = value
    # Normalisasi bila data lama/rusak
    if theme.get("accent") not in ACCENTS:
        theme["accent"] = DEFAULT_THEME["accent"]
    if theme.get("emoji_pack") not in EMOJI_PACKS:
        theme["emoji_pack"] = DEFAULT_THEME["emoji_pack"]
    if theme.get("density") not in DENSITIES:
        theme["density"] = DEFAULT_THEME["density"]
    if theme.get("thumbnail") not in THUMBNAIL_MODES:
        theme["thumbnail"] = DEFAULT_THEME["thumbnail"]
    if theme.get("nav") not in NAV_STYLES:
        theme["nav"] = DEFAULT_THEME["nav"]
    try:
        theme["refresh"] = int(theme.get("refresh") or DEFAULT_THEME["refresh"])
    except (TypeError, ValueError):
        theme["refresh"] = DEFAULT_THEME["refresh"]
    if theme["refresh"] not in REFRESH_CHOICES:
        theme["refresh"] = DEFAULT_THEME["refresh"]
    theme["footer"] = bool(theme.get("footer", True))
    theme["confirm"] = bool(theme.get("confirm", True))
    return theme


def set_theme(guild_id: int, **changes) -> dict:
    """Menyimpan perubahan tema (hanya field valid yang dipakai)."""
    gid = int(guild_id or 0)
    if not gid:
        return dict(DEFAULT_THEME)

    allowed = {
        "accent": ACCENTS,
        "emoji_pack": EMOJI_PACKS,
        "density": DENSITIES,
        "thumbnail": THUMBNAIL_MODES,
        "nav": NAV_STYLES,
    }
    stored = ui_themes.setdefault(gid, {})
    for key, valid in allowed.items():
        value = changes.get(key)
        if value is not None and value in valid:
            stored[key] = value

    for flag in ("footer", "confirm"):
        if changes.get(flag) is not None:
            stored[flag] = bool(changes[flag])

    refresh = changes.get("refresh")
    if refresh is not None:
        try:
            refresh_int = int(refresh)
        except (TypeError, ValueError):
            refresh_int = 0
        if refresh_int in REFRESH_CHOICES:
            stored["refresh"] = refresh_int

    stored["updated_at"] = time.time()
    _trim()
    return get_theme(gid)


def reset_theme(guild_id: int) -> bool:
    """Menghapus seluruh perubahan tema server (kembali ke default)."""
    return ui_themes.pop(int(guild_id or 0), None) is not None


def is_customized(guild_id: int | None) -> bool:
    return int(guild_id or 0) in ui_themes


def _trim(limit: int = 2000) -> None:
    """Membatasi jumlah server yang disimpan agar JSON tetap kecil."""
    extra = len(ui_themes) - limit
    if extra <= 0:
        return
    oldest = sorted(ui_themes.items(), key=lambda kv: float(kv[1].get("updated_at") or 0))[:extra]
    for gid, _ in oldest:
        ui_themes.pop(gid, None)


# ==============================================================================
# HELPER TAMPILAN
# ==============================================================================
def accent_color(guild_id: int | None) -> discord.Colour:
    """Warna aksen server sebagai `discord.Colour`."""
    return discord.Colour(ACCENTS[get_theme(guild_id)["accent"]]["color"])


def accent_int(guild_id: int | None) -> int:
    return int(ACCENTS[get_theme(guild_id)["accent"]]["color"])


def accent_emoji(guild_id: int | None) -> str:
    return ACCENTS[get_theme(guild_id)["accent"]]["emoji"]


def emoji(guild_id: int | None, key: str, fallback: str = "•") -> str:
    """Emoji sesuai pack server (otomatis jatuh ke standar bila key tak dikenal)."""
    pack = EMOJI_PACKS[get_theme(guild_id)["emoji_pack"]]["map"]
    return pack.get(key) or _EMOJI_STANDAR.get(key) or fallback


def is_compact(guild_id: int | None) -> bool:
    """`True` bila server memilih kepadatan *ringkas*."""
    return get_theme(guild_id)["density"] == "ringkas"


def show_thumbnail(guild_id: int | None) -> bool:
    return get_theme(guild_id)["thumbnail"] == "ikon"


def confirm_enabled(guild_id: int | None) -> bool:
    return bool(get_theme(guild_id)["confirm"])


def refresh_interval(guild_id: int | None) -> int:
    return int(get_theme(guild_id)["refresh"])


def footer_text(guild_id: int | None, extra: str = "") -> str | None:
    """Footer standar (versi bot) — `None` bila server mematikannya."""
    theme = get_theme(guild_id)
    if not theme["footer"]:
        return extra or None
    base = f"Gemini AI v{BOT_VERSION} • {ACCENTS[theme['accent']]['label']}"
    return f"{base} • {extra}" if extra else base


def apply_embed_theme(embed: discord.Embed, guild_id: int | None, *, footer: str | None = None) -> discord.Embed:
    """Menerapkan warna aksen & footer tema ke embed klasik (dipakai pesan non-V2)."""
    embed.color = accent_color(guild_id)
    text = footer_text(guild_id, footer or "")
    if text:
        embed.set_footer(text=text[:2048])
    return embed


def theme_summary(guild_id: int | None) -> str:
    """Ringkasan satu baris tema aktif (untuk `/status` & dashboard)."""
    theme = get_theme(guild_id)
    return (
        f"{ACCENTS[theme['accent']]['emoji']} {ACCENTS[theme['accent']]['label']} • "
        f"{EMOJI_PACKS[theme['emoji_pack']]['emoji']} {EMOJI_PACKS[theme['emoji_pack']]['label'].split(' (')[0]} • "
        f"{DENSITIES[theme['density']]['emoji']} {theme['density'].title()}"
    )


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def load_ui_themes_from_disk() -> int:
    """Memuat tema tersimpan. Mengembalikan jumlah server yang punya tema."""
    ui_themes.clear()
    if not UI_THEME_FILE.exists():
        return 0
    try:
        raw = json.loads(UI_THEME_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", UI_THEME_FILE, exc)
        return 0

    guilds = raw.get("guilds") if isinstance(raw, dict) else None
    for gid, data in (guilds or {}).items():
        try:
            int(gid)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        entry: dict = {}
        for key, valid in (
            ("accent", ACCENTS),
            ("emoji_pack", EMOJI_PACKS),
            ("density", DENSITIES),
            ("thumbnail", THUMBNAIL_MODES),
            ("nav", NAV_STYLES),
        ):
            value = data.get(key)
            if value in valid:
                entry[key] = value
        for flag in ("footer", "confirm"):
            if isinstance(data.get(flag), bool):
                entry[flag] = data[flag]
        try:
            refresh = int(data.get("refresh"))
        except (TypeError, ValueError):
            refresh = 0
        if refresh in REFRESH_CHOICES:
            entry["refresh"] = refresh
        try:
            entry["updated_at"] = float(data.get("updated_at") or 0)
        except (TypeError, ValueError):
            entry["updated_at"] = 0.0
        ui_themes[int(gid)] = entry

    _trim()
    return len(ui_themes)


async def save_ui_themes_to_disk() -> None:
    """Menyimpan tema secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(gid): data for gid, data in ui_themes.items()}}
            tmp_file = Path(str(UI_THEME_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, UI_THEME_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan ui_theme.json: %s", sanitize_error_message(exc))


def cleanup_ui_runtime(limit: int = 2000) -> int:
    """Membatasi jumlah tema tersimpan agar RAM/berkas tetap kecil."""
    before = len(ui_themes)
    _trim(limit)
    return before - len(ui_themes)
