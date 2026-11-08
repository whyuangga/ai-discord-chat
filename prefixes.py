"""Prefix command teks **per server** (`!setup_panel`, dll.) — **0 kuota AI**.

Slash command tidak terpengaruh; pengaturan ini hanya untuk command berbasis prefix.
Default tetap `!` (dari `config.COMMAND_PREFIX`), dan setiap server boleh menggantinya
lewat `/prefix atur`. Disimpan di `data/prefixes.json` (hanya server yang berubah).
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from config import COMMAND_PREFIX, DATA_DIR, PREFIX_FILE

logger = logging.getLogger("gemini_bot.prefixes")

_lock = asyncio.Lock()

MIN_LEN = 1
MAX_LEN = 5
DEFAULT_PREFIX = str(COMMAND_PREFIX or "!")

# Karakter yang membingungkan / bentrok dengan fitur Discord
_BLOCKED = set("<>&@#:`/\\*_~|")

guild_prefixes: dict[int, str] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def validate_prefix(raw: str) -> tuple[str | None, str]:
    """Memeriksa prefix baru. Mengembalikan `(prefix_bersih, error)`."""
    value = str(raw or "").strip()
    if not value:
        return None, "Prefix tidak boleh kosong."
    if any(ch.isspace() for ch in value):
        return None, "Prefix tidak boleh mengandung spasi."
    if len(value) > MAX_LEN:
        return None, f"Prefix maksimal **{MAX_LEN} karakter** (contoh: `!`, `?`, `..`)."
    if len(value) < MIN_LEN:
        return None, "Prefix terlalu pendek."
    if value[0] in _BLOCKED or any(ch in _BLOCKED for ch in value):
        return None, "Prefix tidak boleh memakai karakter `<> & @ # : ` / \\ * _ ~ |`."
    if value.isalnum() and value.lower() in {"a", "i"}:
        return None, "Prefix berupa satu huruf itu terlalu mudah bentrok dengan obrolan biasa."
    return value, ""


def get_prefix(guild_id: int | None) -> str:
    """Prefix aktif untuk sebuah server (default `!`)."""
    if guild_id is None:
        return DEFAULT_PREFIX
    return guild_prefixes.get(_to_int(guild_id), DEFAULT_PREFIX)


def set_prefix(guild_id: int, raw: str) -> tuple[bool, str, str]:
    """Mengubah prefix server. Mengembalikan `(ok, prefix_hasil, pesan)`."""
    gid = _to_int(guild_id)
    if gid <= 0:
        return False, DEFAULT_PREFIX, "Server tidak dikenali."
    value, error = validate_prefix(raw)
    if value is None:
        return False, get_prefix(gid), error
    if value == DEFAULT_PREFIX:
        guild_prefixes.pop(gid, None)
        return True, value, "Prefix kembali ke bawaan."
    guild_prefixes[gid] = value
    return True, value, f"Prefix server diganti menjadi `{value}`."


def reset_prefix(guild_id: int) -> bool:
    """Mengembalikan prefix server ke bawaan."""
    return guild_prefixes.pop(_to_int(guild_id), None) is not None


def prefixes_for(guild_id: int | None) -> list[str]:
    """Daftar prefix yang aktif (bawaan + prefix khusus server)."""
    custom = get_prefix(guild_id)
    if custom == DEFAULT_PREFIX:
        return [DEFAULT_PREFIX]
    return [custom, DEFAULT_PREFIX]


def match_prefix(text: str, guild_id: int | None) -> str | None:
    """Prefix yang dipakai sebuah pesan (None bila bukan command prefix)."""
    content = str(text or "").strip()
    for prefix in prefixes_for(guild_id):
        if prefix and content.startswith(prefix):
            return prefix
    return None


def is_prefix_command(text: str, guild_id: int | None) -> bool:
    return match_prefix(text, guild_id) is not None


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def load_prefixes_from_disk() -> int:
    guild_prefixes.clear()
    path = Path(PREFIX_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, value in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        clean, error = validate_prefix(str(value))
        if gid and clean and not error and clean != DEFAULT_PREFIX:
            guild_prefixes[gid] = clean
    return len(guild_prefixes)


async def save_prefixes_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(gid): prefix for gid, prefix in guild_prefixes.items()}}
            tmp_file = Path(str(PREFIX_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, PREFIX_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan prefixes.json")


def cleanup_prefixes_runtime() -> int:
    """Membuang entri yang ternyata sama dengan prefix bawaan."""
    removed = 0
    for gid, prefix in list(guild_prefixes.items()):
        if prefix == DEFAULT_PREFIX or not prefix:
            guild_prefixes.pop(gid, None)
            removed += 1
    return removed
