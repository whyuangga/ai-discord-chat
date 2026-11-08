"""Penerjemah hemat kuota: `/terjemah`, reaksi bendera, & auto-post opsional.

Filosofi: **kuota AI itu mahal**, jadi terjemahan otomatis dibuat bertingkat.

| Mode | Kuota | Cara kerja |
| :--- | :--- | :--- |
| **Reaksi bendera** (bawaan) | hanya saat diminta | Bot menempel reaksi 🇮🇩/🇬🇧 di channel terpilih; terjemahan **baru dibuat** ketika ada yang mengklik reaksi. |
| **`/terjemah teks` / `/terjemah pesan`** | 1 panggilan saat dipakai | Manual, paling terkontrol. |
| **Auto-post** (opsional, default **mati**) | 1 panggilan per pesan | Dinyalakan per channel oleh Admin, dengan rate limit & batas kuota server. |

Modul ini menyimpan **konfigurasi channel** + **cache terjemahan** di memori (dan
konfigurasi ke `data/translate.json`). Kalimat yang sama tidak diterjemahkan dua kali
selama cache masih segar, sehingga pertanyaan berulang = **0 kuota**.
"""

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

from config import DATA_DIR, TRANSLATE_FILE

logger = logging.getLogger("gemini_bot.translate_tools")

# Cache terjemahan (kalimat identik = 0 kuota)
TRANSLATE_CACHE_TTL_SEC = 6 * 3600
TRANSLATE_CACHE_MAX = 300

# Batas panjang teks yang layak diterjemahkan otomatis
TRANSLATE_MIN_CHARS = 8
TRANSLATE_MAX_CHARS = 600

# Jeda minimal antar-terjemahan di satu channel (anti-banjir)
TRANSLATE_RATE_LIMIT_SEC = 3

TARGETS: dict[str, str] = {"id": "🇮🇩 Indonesia", "en": "🇬🇧 English"}
# Reaksi bendera -> bahasa tujuan
FLAG_TARGETS: dict[str, str] = {"🇮🇩": "id", "🇬🇧": "en", "🇺🇸": "en"}

translate_guilds: dict[int, dict] = {}
_translate_cache: dict[tuple[str, str], dict] = {}
_rate_limits: dict[int, float] = {}

_URL_RE = re.compile(r"https?://\S+")
_LETTER_RE = re.compile(r"[A-Za-z\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF]")


def default_guild_config() -> dict:
    """Konfigurasi awal penerjemah untuk satu server (semua channel belum dipilih)."""
    return {"enabled": True, "channels": {}}


def get_guild_config(guild_id: int) -> dict:
    cfg = translate_guilds.get(int(guild_id))
    if cfg is None:
        cfg = default_guild_config()
        translate_guilds[int(guild_id)] = cfg
    return cfg


def set_channel_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool = True,
    auto_react: bool = True,
    auto_post: bool = False,
) -> dict:
    """Mengaktifkan/mengatur penerjemah pada satu channel."""
    cfg = get_guild_config(guild_id)
    cid = str(int(channel_id))
    if not enabled:
        cfg["channels"].pop(cid, None)
        return cfg
    cfg["channels"][cid] = {"auto_react": bool(auto_react), "auto_post": bool(auto_post)}
    return cfg


def remove_channel_config(guild_id: int, channel_id: int) -> bool:
    cfg = translate_guilds.get(int(guild_id))
    if not cfg:
        return False
    return cfg["channels"].pop(str(int(channel_id)), None) is not None


def channel_config(guild_id: int, channel_id: int) -> dict | None:
    """Pengaturan channel terpilih, atau `None` bila channel tidak dipantau."""
    cfg = translate_guilds.get(int(guild_id))
    if not cfg or not cfg.get("enabled"):
        return None
    return (cfg.get("channels") or {}).get(str(int(channel_id)))


def watched_channel_ids(guild_id: int) -> list[int]:
    cfg = translate_guilds.get(int(guild_id)) or {}
    out: list[int] = []
    for cid in (cfg.get("channels") or {}):
        try:
            out.append(int(cid))
        except (TypeError, ValueError):
            continue
    return out


# ==============================================================================
# HEURISTIK: pesan mana yang layak diterjemahkan?
# ==============================================================================
def looks_translatable(text: str) -> bool:
    """True bila teks cukup berisi kata untuk diterjemahkan (bukan cuma emoji/link)."""
    raw = str(text or "").strip()
    if len(raw) < TRANSLATE_MIN_CHARS or len(raw) > TRANSLATE_MAX_CHARS:
        return False
    stripped = _URL_RE.sub(" ", raw).strip()
    if len(stripped) < TRANSLATE_MIN_CHARS:
        return False
    if not _LETTER_RE.search(stripped):
        return False
    # Pesan yang hanya berisi perintah slash / mention tidak perlu diterjemahkan
    if stripped.startswith("/") and " " not in stripped:
        return False
    return True


# ==============================================================================
# CACHE TERJEMAHAN
# ==============================================================================
def _cache_key(text: str, target: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())[:600]
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:24]
    return str(target or "id"), digest


def get_cached_translation(text: str, target: str, *, ttl: int | None = None) -> str | None:
    entry = _translate_cache.get(_cache_key(text, target))
    if not entry:
        return None
    limit = TRANSLATE_CACHE_TTL_SEC if ttl is None else int(ttl)
    if limit <= 0 or time.time() - float(entry.get("at") or 0) > limit:
        _translate_cache.pop(_cache_key(text, target), None)
        return None
    return str(entry.get("result") or "")


def store_cached_translation(text: str, target: str, result: str) -> bool:
    value = str(result or "").strip()
    if not value or not looks_translatable(text):
        return False
    _translate_cache[_cache_key(text, target)] = {"result": value[:4000], "at": time.time()}
    while len(_translate_cache) > TRANSLATE_CACHE_MAX:
        _translate_cache.pop(next(iter(_translate_cache)))
    return True


def cache_size() -> int:
    return len(_translate_cache)


def clear_cache() -> int:
    count = len(_translate_cache)
    _translate_cache.clear()
    return count


def cleanup_translate_runtime() -> int:
    """Membuang cache terjemahan kedaluwarsa (dipanggil pembersih RAM per jam)."""
    now = time.time()
    stale = [
        key for key, entry in _translate_cache.items()
        if now - float(entry.get("at") or 0) > TRANSLATE_CACHE_TTL_SEC
    ]
    for key in stale:
        _translate_cache.pop(key, None)
    _rate_limits.clear()
    return len(stale)


# ==============================================================================
# RATE LIMIT PER CHANNEL
# ==============================================================================
def rate_limited(channel_id: int, *, now: float | None = None, window: int = TRANSLATE_RATE_LIMIT_SEC) -> bool:
    """`True` bila channel baru saja diterjemahkan (cegah banjir & pemborosan kuota)."""
    cid = int(channel_id or 0)
    now_ts = time.time() if now is None else float(now)
    last = float(_rate_limits.get(cid) or 0)
    if last and now_ts - last < max(0, int(window)):
        return True
    _rate_limits[cid] = now_ts
    return False


def reset_rate_limits() -> None:
    _rate_limits.clear()


# ==============================================================================
# SIMPAN / MUAT (JSON)
# ==============================================================================
def load_translate_from_disk() -> int:
    """Memuat konfigurasi penerjemah dari `data/translate.json`."""
    translate_guilds.clear()
    path = Path(TRANSLATE_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    loaded = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        cfg = default_guild_config()
        cfg["enabled"] = bool(data.get("enabled", True))
        channels: dict[str, dict] = {}
        for cid_str, ch in (data.get("channels") or {}).items():
            try:
                cid = str(int(cid_str))
            except (TypeError, ValueError):
                continue
            channels[cid] = {
                "auto_react": bool((ch or {}).get("auto_react", True)),
                "auto_post": bool((ch or {}).get("auto_post", False)),
            }
        cfg["channels"] = channels
        translate_guilds[gid] = cfg
        loaded += 1
    return loaded


async def save_translate_to_disk() -> None:
    """Menyimpan konfigurasi penerjemah secara atomik."""
    import asyncio

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"guilds": {}}
        for gid, cfg in translate_guilds.items():
            payload["guilds"][str(gid)] = {
                "enabled": bool(cfg.get("enabled", True)),
                "channels": cfg.get("channels") or {},
            }
        tmp_file = Path(str(TRANSLATE_FILE) + ".tmp")
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
        await asyncio.to_thread(os.replace, tmp_file, TRANSLATE_FILE)
    except Exception:  # pragma: no cover - I/O gagal
        logger.exception("Gagal menyimpan translate.json")
