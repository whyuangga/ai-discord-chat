"""Sistem Leveling & XP ringan (Tier 2C) — **0 kuota Gemini**.

Aturan mainnya dibuat sederhana supaya tetap murah di Wispbyte (RAM ~50 MB):

1. XP hanya diberikan pada channel yang diizinkan, dengan **jeda per member**
   (default 60 detik) agar tidak bisa di-*farming* dengan spam.
2. Data disimpan ringkas: hanya `xp`, `level`, `messages`, & waktu terakhir.
3. Saat menyimpan, daftar member dipangkas ke **500 teratas per server**
   (`LEVELS_MAX_MEMBERS`) sehingga file JSON tidak tumbuh tanpa batas.
4. **Role hadiah level** diterapkan otomatis saat member naik level (opsional).
5. Pengumuman naik level bisa dimatikan, dan tidak pernah dikirim ke channel
   yang sama berulang-ulang bila `announce=False`.

Seluruh data ada di `data/levels.json`.
"""

import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path

import discord
import channel_targets

from config import (
    DATA_DIR,
    LEVELS_COOLDOWN_SEC,
    LEVELS_FILE,
    LEVELS_MAX_MEMBERS,
    LEVELS_MAX_LEVEL,
    LEVELS_VOICE_DAILY_CAP_MIN,
    LEVELS_VOICE_XP_PER_MIN,
    LEVELS_XP_MAX,
    LEVELS_XP_MIN,
)
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.levels")

_lock = asyncio.Lock()

# ==============================================================================
# STATE GLOBAL
# ==============================================================================
level_guilds: dict[int, dict] = {}   # guild_id -> konfigurasi
levels: dict[str, dict] = {}         # "guild:user" -> {xp, level, messages, last_at}


def default_config() -> dict:
    return {
        "enabled": True,
        "announce": True,
        "announce_channel_id": None,   # None = balas di channel tempat naik level
        "xp_min": int(LEVELS_XP_MIN),
        "xp_max": int(LEVELS_XP_MAX),
        "cooldown": int(LEVELS_COOLDOWN_SEC),
        "ignore_channels": [],
        "ignore_roles": [],
        "voice_enabled": True,            # XP dari voice channel ikut dihitung
        "voice_xp_per_min": int(LEVELS_VOICE_XP_PER_MIN),
        "voice_daily_cap_min": int(LEVELS_VOICE_DAILY_CAP_MIN),
        "voice_ignore_channels": [],      # voice channel yang tidak dihitung
        "level_roles": {},             # {"5": role_id, ...}
        "leveled_up": 0,
        # v1.34.0-beta: musim & prestige
        "season": 1,
        "season_started_at": 0.0,
        "season_auto_hari": 0,          # 0 = reset musim manual saja (default aman)
        "season_announce": True,
        "season_history": [],           # ringkasan beberapa musim terakhir
        "prestige_aktif": True,
        "prestige_min_level": 0,        # 0 = pakai LEVELS_MAX_LEVEL
        "prestige_count": 0,
    }


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _key(guild_id: int, user_id: int) -> str:
    return f"{int(guild_id)}:{int(user_id)}"


# ==============================================================================
# RUMUS XP
# ==============================================================================
def xp_for_level(level: int) -> int:
    """XP yang dibutuhkan untuk naik DARI `level` ke `level+1`."""
    target = max(0, int(level))
    return 5 * target * target + 50 * target + 100


def total_xp_for_level(level: int) -> int:
    """Total XP kumulatif untuk mencapai `level` tertentu (level 0 = 0 XP)."""
    return sum(xp_for_level(idx) for idx in range(max(0, int(level))))


def level_from_total_xp(xp: int, *, max_level: int = LEVELS_MAX_LEVEL) -> int:
    """Menghitung level dari total XP (dibatasi `max_level`)."""
    remaining = max(0, int(xp))
    level = 0
    while level < max_level and remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level


def progress_in_level(xp: int, level: int) -> tuple[int, int]:
    """Mengembalikan `(xp_di_level_ini, xp_dibutuhkan)` untuk progress bar."""
    needed = xp_for_level(level)
    spent = max(0, int(xp)) - total_xp_for_level(level)
    return max(0, min(spent, needed)), needed


def build_progress_bar(current: int, needed: int, *, size: int = 12) -> str:
    """Progress bar sederhana untuk kartu level: `▰▰▰▱▱…`."""
    bar_size = max(4, int(size))
    if needed <= 0:
        return "▰" * bar_size
    ratio = max(0.0, min(1.0, float(current) / float(needed)))
    filled = min(bar_size, max(0, int(round(ratio * bar_size))))
    return "▰" * filled + "▱" * (bar_size - filled)


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def load_levels_from_disk() -> int:
    """Memuat konfigurasi & data XP seluruh server."""
    level_guilds.clear()
    levels.clear()
    if not LEVELS_FILE.exists():
        return 0

    try:
        raw = json.loads(LEVELS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", LEVELS_FILE, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        base = default_config()
        base.update(
            {
                "enabled": bool(data.get("enabled", True)),
                "announce": bool(data.get("announce", True)),
                "announce_channel_id": _to_int(data.get("announce_channel_id")) or None,
                "xp_min": max(1, _to_int(data.get("xp_min"), base["xp_min"])),
                "xp_max": max(1, _to_int(data.get("xp_max"), base["xp_max"])),
                "cooldown": max(0, _to_int(data.get("cooldown"), base["cooldown"])),
                "ignore_channels": [_to_int(c) for c in (data.get("ignore_channels") or []) if _to_int(c)],
                "ignore_roles": [_to_int(r) for r in (data.get("ignore_roles") or []) if _to_int(r)],
                "voice_enabled": bool(data.get("voice_enabled", True)),
                "voice_xp_per_min": max(1, _to_int(data.get("voice_xp_per_min"), base["voice_xp_per_min"])),
                "voice_daily_cap_min": max(0, _to_int(data.get("voice_daily_cap_min"), base["voice_daily_cap_min"])),
                "voice_ignore_channels": [
                    _to_int(c) for c in (data.get("voice_ignore_channels") or []) if _to_int(c)
                ],
                "level_roles": {
                    str(max(1, _to_int(k))): _to_int(v)
                    for k, v in (data.get("level_roles") or {}).items()
                    if _to_int(v)
                },
                "leveled_up": max(0, _to_int(data.get("leveled_up"))),
                "season": max(1, _to_int(data.get("season"), 1)),
                "season_started_at": float(data.get("season_started_at") or 0),
                "season_auto_hari": max(0, min(365, _to_int(data.get("season_auto_hari")))),
                "season_announce": bool(data.get("season_announce", True)),
                "season_history": [
                    dict(item)
                    for item in (data.get("season_history") or [])
                    if isinstance(item, dict)
                ][-12:],
                "prestige_aktif": bool(data.get("prestige_aktif", True)),
                "prestige_min_level": max(0, _to_int(data.get("prestige_min_level"))),
                "prestige_count": max(0, _to_int(data.get("prestige_count"))),
            }
        )
        if base["xp_max"] < base["xp_min"]:
            base["xp_max"] = base["xp_min"]
        level_guilds[gid] = base

    for key, data in (raw.get("members") or {}).items():
        try:
            gid_str, uid_str = str(key).split(":", 1)
            gid, uid = int(gid_str), int(uid_str)
        except (TypeError, ValueError):
            continue
        xp = max(0, _to_int(data.get("xp")))
        if xp <= 0:
            continue
        levels[_key(gid, uid)] = {
            "xp": xp,
            "level": max(0, _to_int(data.get("level"), level_from_total_xp(xp))),
            "messages": max(0, _to_int(data.get("messages"))),
            "last_at": float(data.get("last_at") or 0),
            "voice_xp": max(0, _to_int(data.get("voice_xp"))),
            "voice_sec": max(0, _to_int(data.get("voice_sec"))),
            "voice_day": str(data.get("voice_day") or ""),
            "voice_min_today": max(0, _to_int(data.get("voice_min_today"))),
            "prestige": max(0, _to_int(data.get("prestige"))),
        }
    return len(level_guilds)


def _prune_members() -> None:
    """Membatasi jumlah member tersimpan per server (yang XP-nya teratas)."""
    per_guild: dict[int, list[tuple[str, int]]] = {}
    for key, data in levels.items():
        try:
            gid = int(key.split(":", 1)[0])
        except (TypeError, ValueError):
            continue
        per_guild.setdefault(gid, []).append((key, int(data.get("xp") or 0)))

    for gid, items in per_guild.items():
        if len(items) <= LEVELS_MAX_MEMBERS:
            continue
        items.sort(key=lambda pair: pair[1], reverse=True)
        for key, _ in items[LEVELS_MAX_MEMBERS:]:
            levels.pop(key, None)


async def save_levels_to_disk() -> None:
    """Menyimpan konfigurasi & data XP secara atomik (setelah dipangkas)."""
    async with _lock:
        try:
            _prune_members()
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(k): v for k, v in level_guilds.items()},
                "members": levels,
            }
            tmp_file = Path(str(LEVELS_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, LEVELS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan levels.json: %s", sanitize_error_message(exc))


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def get_level_config(guild_id: int) -> dict:
    cfg = level_guilds.get(int(guild_id))
    if cfg is None:
        cfg = default_config()
        level_guilds[int(guild_id)] = cfg
    return cfg


def peek_level_config(guild_id: int) -> dict:
    """Baca konfigurasi level **tanpa** membuat default baru.

    `get_level_config()` membuat config default (`enabled: True`) bila belum ada,
    sehingga sekadar *membaca* bisa menyalakan ulang leveling yang baru dimatikan.
    """
    return dict(level_guilds.get(int(guild_id)) or {})


def set_level_enabled(guild_id: int, aktif: bool) -> dict:
    """Nyalakan/matikan leveling **tanpa menghapus** setelan lain (XP, channel, season).

    Berbeda dengan `set_level_config(aktif=False)` yang membuang seluruh konfigurasi.
    """
    cfg = get_level_config(guild_id)
    cfg["enabled"] = bool(aktif)
    return cfg


def is_leveling_active(guild_id: int) -> bool:
    cfg = level_guilds.get(int(guild_id))
    return bool(cfg and cfg.get("enabled"))


def set_level_config(guild_id: int, **changes) -> dict | None:
    """Mengubah konfigurasi leveling. `aktif=False` mematikan fitur."""
    if changes.get("aktif") is False or changes.get("enabled") is False:
        level_guilds.pop(int(guild_id), None)
        return None

    cfg = get_level_config(guild_id)
    cfg["enabled"] = True
    if changes.get("announce") is not None:
        cfg["announce"] = bool(changes["announce"])
    if changes.get("announce_channel_id") is not None:
        cid = _to_int(changes["announce_channel_id"])
        cfg["announce_channel_id"] = cid or None
    for key in ("xp_min", "xp_max", "cooldown"):
        if changes.get(key) is not None:
            cfg[key] = max(0 if key == "cooldown" else 1, int(changes[key]))
    if changes.get("voice_enabled") is not None:
        cfg["voice_enabled"] = bool(changes["voice_enabled"])
    if changes.get("voice_xp_per_min") is not None:
        cfg["voice_xp_per_min"] = max(1, int(changes["voice_xp_per_min"]))
    if changes.get("voice_daily_cap_min") is not None:
        cfg["voice_daily_cap_min"] = max(0, int(changes["voice_daily_cap_min"]))
    if changes.get("voice_ignore_channels") is not None:
        cfg["voice_ignore_channels"] = [
            _to_int(c) for c in (changes["voice_ignore_channels"] or []) if _to_int(c)
        ]
    if cfg["xp_max"] < cfg["xp_min"]:
        cfg["xp_max"] = cfg["xp_min"]
    for key in ("ignore_channels", "ignore_roles"):
        if changes.get(key) is not None:
            cfg[key] = sorted({int(v) for v in changes[key]})
    if changes.get("season_auto_hari") is not None:
        cfg["season_auto_hari"] = max(0, min(365, int(changes["season_auto_hari"])))
    if changes.get("season_announce") is not None:
        cfg["season_announce"] = bool(changes["season_announce"])
    if changes.get("prestige_aktif") is not None:
        cfg["prestige_aktif"] = bool(changes["prestige_aktif"])
    if changes.get("prestige_min_level") is not None:
        cfg["prestige_min_level"] = max(0, int(changes["prestige_min_level"]))
    return cfg


def disable_leveling(guild_id: int) -> bool:
    return level_guilds.pop(int(guild_id), None) is not None


def set_level_role(guild_id: int, level: int, role_id: int | None) -> dict:
    """Menetapkan/menghapus role hadiah untuk sebuah level."""
    cfg = get_level_config(guild_id)
    mapping = cfg.setdefault("level_roles", {})
    if role_id:
        mapping[str(max(1, int(level)))] = int(role_id)
    else:
        mapping.pop(str(max(0, int(level))), None)
    return cfg


def reward_role_for_level(cfg: dict, level: int) -> int | None:
    """Role hadiah untuk level tersebut (bila ada)."""
    mapping = cfg.get("level_roles") or {}
    role_id = mapping.get(str(int(level)))
    return int(role_id) if role_id else None


# ==============================================================================
# PEMBERIAN XP
# ==============================================================================
def is_ignored(channel_id: int, role_ids: set[int] | None, cfg: dict) -> bool:
    if int(channel_id) in {int(c) for c in (cfg.get("ignore_channels") or [])}:
        return True
    roles = {int(r) for r in (cfg.get("ignore_roles") or [])}
    return bool(roles and role_ids and roles & {int(r) for r in role_ids})


def add_message_xp(
    guild_id: int,
    user_id: int,
    *,
    channel_id: int = 0,
    role_ids: set[int] | None = None,
    now: float | None = None,
    rng: random.Random | None = None,
) -> dict | None:
    """Memberi XP untuk satu pesan. `None` bila tidak memenuhi syarat.

    Hasil berisi: `gained`, `level`, `level_up`, `role_id`, `xp`, `needed`, `current`.
    """
    gid = int(guild_id)
    cfg = level_guilds.get(gid)
    if not cfg or not cfg.get("enabled"):
        return None
    if channel_id and is_ignored(channel_id, role_ids, cfg):
        return None

    current_time = time.time() if now is None else float(now)
    key = _key(gid, user_id)
    data = levels.get(key)
    if data is None:
        data = {"xp": 0, "level": 0, "messages": 0, "last_at": 0.0}
        levels[key] = data

    cooldown = int(cfg.get("cooldown") or 0)
    if cooldown and current_time - float(data.get("last_at") or 0) < cooldown:
        data["messages"] = int(data.get("messages") or 0) + 1
        return None

    picker = rng or random
    low = max(1, int(cfg.get("xp_min") or LEVELS_XP_MIN))
    high = max(low, int(cfg.get("xp_max") or LEVELS_XP_MAX))
    gained = picker.randint(low, high)

    data["xp"] = int(data.get("xp") or 0) + gained
    data["messages"] = int(data.get("messages") or 0) + 1
    data["last_at"] = current_time
    old_level = int(data.get("level") or 0)
    new_level = level_from_total_xp(int(data["xp"]))
    data["level"] = new_level
    level_up = new_level > old_level

    role_id = None
    if level_up:
        cfg["leveled_up"] = int(cfg.get("leveled_up") or 0) + 1
        role_id = reward_role_for_level(cfg, new_level)

    current, needed = progress_in_level(int(data["xp"]), new_level)
    return {
        "gained": gained,
        "xp": int(data["xp"]),
        "level": new_level,
        "old_level": old_level,
        "level_up": level_up,
        "role_id": role_id,
        "current": current,
        "needed": needed,
    }


def _today_str(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(float(now)))


def add_voice_minutes(
    guild_id: int,
    user_id: int,
    minutes: int,
    *,
    channel_id: int = 0,
    now: float | None = None,
) -> dict | None:
    """Memberi XP karena berada di voice channel selama `minutes` menit.

    `None` bila leveling/voice XP nonaktif, channel diabaikan, atau batas harian habis.
    Hasil berisi kunci yang sama dengan `add_message_xp` + `minutes`.
    """
    gid = int(guild_id)
    cfg = level_guilds.get(gid)
    if not cfg or not cfg.get("enabled") or not cfg.get("voice_enabled", True):
        return None
    if channel_id and int(channel_id) in {int(c) for c in (cfg.get("voice_ignore_channels") or [])}:
        return None

    whole = max(0, int(minutes))
    if whole <= 0:
        return None

    current_time = time.time() if now is None else float(now)
    key = _key(gid, user_id)
    data = levels.get(key)
    if data is None:
        data = {"xp": 0, "level": 0, "messages": 0, "last_at": 0.0}
        levels[key] = data

    # Reset hitungan harian bila hari berubah
    today = _today_str(current_time)
    if str(data.get("voice_day") or "") != today:
        data["voice_day"] = today
        data["voice_min_today"] = 0

    cap = max(0, int(cfg.get("voice_daily_cap_min") or 0))
    used_today = max(0, int(data.get("voice_min_today") or 0))
    if cap and used_today >= cap:
        return None
    if cap:
        whole = min(whole, cap - used_today)

    per_min = max(1, int(cfg.get("voice_xp_per_min") or LEVELS_VOICE_XP_PER_MIN))
    gained = whole * per_min

    data["voice_min_today"] = used_today + whole
    data["voice_sec"] = int(data.get("voice_sec") or 0) + whole * 60
    data["voice_xp"] = int(data.get("voice_xp") or 0) + gained
    data["xp"] = int(data.get("xp") or 0) + gained
    data["last_at"] = current_time

    old_level = int(data.get("level") or 0)
    new_level = level_from_total_xp(int(data["xp"]))
    data["level"] = new_level
    level_up = new_level > old_level

    role_id = None
    if level_up:
        cfg["leveled_up"] = int(cfg.get("leveled_up") or 0) + 1
        role_id = reward_role_for_level(cfg, new_level)

    current, needed = progress_in_level(int(data["xp"]), new_level)
    return {
        "gained": gained,
        "minutes": whole,
        "xp": int(data["xp"]),
        "level": new_level,
        "old_level": old_level,
        "level_up": level_up,
        "role_id": role_id,
        "current": current,
        "needed": needed,
        "voice_xp": int(data["voice_xp"]),
        "voice_min_today": int(data["voice_min_today"]),
        "voice_daily_cap_min": cap,
    }


def get_member_level(guild_id: int, user_id: int) -> dict:
    """Data level seorang member (aman walau belum pernah chat)."""
    data = levels.get(_key(guild_id, user_id)) or {"xp": 0, "level": 0, "messages": 0, "last_at": 0.0}
    current, needed = progress_in_level(int(data.get("xp") or 0), int(data.get("level") or 0))
    return {
        "xp": int(data.get("xp") or 0),
        "level": int(data.get("level") or 0),
        "messages": int(data.get("messages") or 0),
        "current": current,
        "needed": needed,
        "voice_xp": int(data.get("voice_xp") or 0),
        "voice_min_today": int(data.get("voice_min_today") or 0),
        "voice_day": str(data.get("voice_day") or ""),
        "prestige": int(data.get("prestige") or 0),
    }


def leaderboard(guild_id: int, *, limit: int = 10, page: int = 0) -> tuple[list[tuple[int, dict]], int, int]:
    """Papan peringkat server. Mengembalikan `(entries, halaman, total_halaman)`."""
    rows: list[tuple[int, dict]] = []
    for key, data in levels.items():
        try:
            gid_str, uid_str = key.split(":", 1)
        except ValueError:
            continue
        if int(gid_str) != int(guild_id):
            continue
        rows.append((int(uid_str), data))
    rows.sort(key=lambda pair: int(pair[1].get("xp") or 0), reverse=True)

    size = max(1, int(limit))
    total_pages = max(1, (len(rows) + size - 1) // size)
    current_page = max(0, min(total_pages - 1, int(page)))
    start = current_page * size
    return rows[start : start + size], current_page, total_pages


def reset_member(guild_id: int, user_id: int) -> bool:
    return levels.pop(_key(guild_id, user_id), None) is not None


async def apply_level_role(member, role_id: int) -> bool:
    """Memberikan role hadiah level (gagal senyap bila izin kurang)."""
    if member is None or not role_id:
        return False
    add_role = getattr(member, "add_roles", None)
    if not callable(add_role):
        return False
    guild = getattr(member, "guild", None)
    get_role = getattr(guild, "get_role", None)
    role = get_role(int(role_id)) if callable(get_role) else None
    if role is None:
        return False
    try:
        await add_role(role, reason="Hadiah level otomatis")
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.info("Gagal memberi role level %s: %s", role_id, sanitize_error_message(exc))
        return False


# ==============================================================================
# TAMPILAN
# ==============================================================================
# ==============================================================================
# MUSIM & PRESTIGE (v1.34.0-beta) — 0 kuota AI
# ==============================================================================
def season_info(guild_id: int, *, now: float | None = None) -> dict:
    """Informasi musim level server: nomor, mulai, sisa hari, & juara musim lalu."""
    cfg = get_level_config(guild_id)
    current = time.time() if now is None else float(now)
    started = float(cfg.get("season_started_at") or 0) or current
    auto_days = _to_int(cfg.get("season_auto_hari"))
    remaining = 0
    if auto_days > 0:
        remaining = max(0, int((started + auto_days * 86400 - current) // 86400))
    history = cfg.get("season_history") or []
    return {
        "season": max(1, _to_int(cfg.get("season"), 1)),
        "started_at": started,
        "days_elapsed": max(0, int((current - started) // 86400)),
        "auto_hari": auto_days,
        "sisa_hari": remaining,
        "history": history,
        "last": history[-1] if history else None,
    }


def season_top(guild_id: int, limit: int = 3) -> list[dict]:
    """Peringkat teratas musim berjalan (untuk snapshot saat reset)."""
    rows, _page, _total = leaderboard(guild_id, limit=limit)
    return [
        {
            "user_id": int(uid),
            "level": int(data.get("level") or 0),
            "xp": int(data.get("xp") or 0),
            "messages": int(data.get("messages") or 0),
        }
        for uid, data in rows
    ]


def reset_season(guild_id: int, *, by_id: int = 0, now: float | None = None) -> dict:
    """Menutup musim berjalan & memulai musim baru (XP direset, prestige disimpan)."""
    gid = int(guild_id)
    cfg = get_level_config(gid)
    current = time.time() if now is None else float(now)

    top = season_top(gid, limit=3)
    members_before = 0
    for key in list(levels.keys()):
        try:
            key_gid = int(key.split(":", 1)[0])
        except (TypeError, ValueError):
            continue
        if key_gid != gid:
            continue
        members_before += 1
        # Prestige tetap tersimpan sebagai trofi permanen
        prestige = max(0, _to_int(levels[key].get("prestige")))
        if prestige:
            levels[key] = {"xp": 0, "level": 0, "messages": 0, "last_at": 0.0, "prestige": prestige}
        else:
            levels.pop(key, None)

    closed = max(1, _to_int(cfg.get("season"), 1))
    snapshot = {
        "season": closed,
        "ended_at": current,
        "participants": members_before,
        "top": top,
        "by": int(by_id) if by_id else 0,
    }
    history = list(cfg.get("season_history") or [])
    history.append(snapshot)
    cfg["season_history"] = history[-12:]
    cfg["season"] = closed + 1
    cfg["season_started_at"] = current
    return snapshot


def season_due(guild_id: int, *, now: float | None = None) -> bool:
    """Apakah musim sudah waktunya direset otomatis."""
    cfg = get_level_config(guild_id)
    auto_days = _to_int(cfg.get("season_auto_hari"))
    if auto_days <= 0:
        return False
    current = time.time() if now is None else float(now)
    started = float(cfg.get("season_started_at") or 0)
    if started <= 0:
        cfg["season_started_at"] = current
        return False
    return current - started >= auto_days * 86400


def prestige_min_level(guild_id: int) -> int:
    cfg = get_level_config(guild_id)
    return _to_int(cfg.get("prestige_min_level")) or int(LEVELS_MAX_LEVEL)


def can_prestige(guild_id: int, user_id: int) -> tuple[bool, str]:
    """Syarat prestige: fitur aktif & level sudah mencapai batas."""
    cfg = get_level_config(guild_id)
    if not cfg.get("prestige_aktif", True):
        return False, "Fitur **prestige** dimatikan di server ini."
    data = get_member_level(guild_id, user_id)
    need = prestige_min_level(guild_id)
    if int(data.get("level") or 0) < need:
        return False, (
            f"Prestige butuh **level {need}**. Levelmu sekarang `{int(data.get('level') or 0)}` — "
            "terus aktif ya!"
        )
    return True, ""


def apply_prestige(guild_id: int, user_id: int) -> tuple[bool, dict]:
    """Menandai prestige: XP kembali 0, jumlah prestige bertambah (permanen)."""
    gid, uid = int(guild_id), int(user_id)
    ok, reason = can_prestige(gid, uid)
    if not ok:
        return False, {"reason": reason}
    key = _key(gid, uid)
    data = levels.get(key) or {}
    prestige = max(0, _to_int(data.get("prestige"))) + 1
    levels[key] = {
        "xp": 0,
        "level": 0,
        "messages": max(0, _to_int(data.get("messages"))),
        "last_at": 0.0,
        "voice_xp": 0,
        "voice_sec": max(0, _to_int(data.get("voice_sec"))),
        "voice_day": "",
        "voice_min_today": 0,
        "prestige": prestige,
    }
    cfg = get_level_config(gid)
    cfg["prestige_count"] = _to_int(cfg.get("prestige_count")) + 1
    return True, {"prestige": prestige, "reason": ""}


def build_season_announce_embed(guild, snapshot: dict, *, next_season: int) -> discord.Embed:
    """Pengumuman pergantian musim level."""
    lines = ["XP semua member direset — mulai lembaran baru! 🎉"]
    top = snapshot.get("top") or []
    if top:
        medals = ["🥇", "🥈", "🥉"]
        lines.append("")
        lines.append(f"**Juara Musim {snapshot.get('season')}**")
        for index, row in enumerate(top[:3]):
            lines.append(
                f"{medals[index]} <@{row['user_id']}> — level `{row.get('level', 0)}` "
                f"(`{row.get('xp', 0)}` XP)"
            )
    lines.append("")
    lines.append(f"**Musim {next_season}** dimulai sekarang. Prestige tetap tersimpan.")
    embed = discord.Embed(
        title=f"🏁 Musim {snapshot.get('season')} Berakhir — Musim {next_season} Dimulai",
        description="\n".join(lines)[:4096],
        color=discord.Color.purple(),
    )
    guild_name = getattr(guild, "name", None)
    embed.set_footer(
        text=f"{guild_name} • /level lihat untuk progres barumu" if guild_name else "/level lihat"
    )
    return embed


async def run_level_season_check(bot) -> int:
    """Dipanggil berkala: reset musim otomatis untuk server yang mengaktifkannya."""
    reset_count = 0
    for gid, cfg in list(level_guilds.items()):
        if not season_due(gid):
            continue
        guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
        snapshot = reset_season(gid)
        reset_count += 1
        ids = channel_targets.daftar(cfg, "announce_channel_id")
        if guild is None or not ids or not cfg.get("season_announce", True):
            continue
        embed = build_season_announce_embed(
            guild, snapshot, next_season=_to_int(cfg.get("season"), 1)
        )

        async def _kirim(channel, embed=embed):
            await channel.send(
                embed=embed, allowed_mentions=discord.AllowedMentions.none()
            )

        await channel_targets.sebarkan(bot, ids, _kirim)
    if reset_count:
        await save_levels_to_disk()
    return reset_count


def build_level_embed(member, data: dict, cfg: dict | None = None) -> discord.Embed:
    """Kartu level seorang member."""
    name = getattr(member, "display_name", None) or str(member)
    embed = discord.Embed(
        title=f"📈 Level {data.get('level', 0)} — {name}",
        color=discord.Color.teal(),
    )
    bar = build_progress_bar(int(data.get("current") or 0), int(data.get("needed") or 1))
    embed.description = (
        f"{bar}\n`{int(data.get('current') or 0)} / {int(data.get('needed') or 1)} XP` "
        f"• total `{int(data.get('xp') or 0)} XP`"
    )
    embed.add_field(name="💬 Pesan", value=f"`{int(data.get('messages') or 0)}`", inline=True)
    embed.add_field(name="🏅 Level", value=f"`{int(data.get('level') or 0)}`", inline=True)
    prestige = int(data.get("prestige") or 0)
    if prestige:
        embed.add_field(name="🌟 Prestige", value=f"`{prestige}×`", inline=True)
    voice_xp = int(data.get("voice_xp") or 0)
    if voice_xp:
        embed.add_field(name="🎙️ XP Voice", value=f"`{voice_xp}`", inline=True)
    next_role = reward_role_for_level(cfg or {}, int(data.get("level") or 0) + 1)
    if next_role:
        embed.add_field(name="🎁 Hadiah Berikutnya", value=f"<@&{next_role}>", inline=True)
    avatar = getattr(member, "display_avatar", None)
    if avatar is not None:
        try:
            embed.set_thumbnail(url=avatar.url)
        except Exception:  # pragma: no cover - avatar tiruan
            pass
    embed.set_footer(text="XP dari pesan (ada jeda anti-spam) & dari menit di voice channel")
    return embed


def build_leaderboard_embed(
    guild,
    rows: list[tuple[int, dict]],
    *,
    page: int,
    total_pages: int,
    total_members: int,
    page_size: int = 10,
) -> discord.Embed:
    """Papan peringkat level server."""
    embed = discord.Embed(
        title="🏆 Papan Peringkat Level",
        color=discord.Color.gold(),
        description=f"`{total_members}` member terdata • halaman `{page + 1}/{total_pages}`",
    )
    if not rows:
        embed.description = "Belum ada data XP. Ajak warga ngobrol dulu! 💬"
        return embed

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    lines = []
    offset = max(0, int(page)) * max(1, int(page_size))
    for idx, (uid, data) in enumerate(rows):
        rank = offset + idx + 1
        badge = medals.get(rank - 1, f"`{rank}.`")
        prestige = int(data.get("prestige") or 0)
        star = f" 🌟`{prestige}×`" if prestige else ""
        lines.append(
            f"{badge} <@{uid}> — level `{int(data.get('level') or 0)}`{star} "
            f"(`{int(data.get('xp') or 0)}` XP • `{int(data.get('messages') or 0)}` pesan)"
        )
    embed.add_field(name="Peringkat", value="\n".join(lines)[:1024], inline=False)
    guild_name = getattr(guild, "name", None)
    embed.set_footer(text=f"{guild_name} • /level lihat untuk kartu levelmu" if guild_name else "/level lihat")
    return embed


def cleanup_levels_runtime() -> int:
    """Membuang data XP 0 & konfigurasi kosong agar RAM tetap kecil."""
    removed = 0
    for key, data in list(levels.items()):
        if int(data.get("xp") or 0) <= 0:
            levels.pop(key, None)
            removed += 1
    return removed


def handle_channel_delete(channel) -> bool:
    """Membersihkan channel yang dihapus dari daftar abaikan & channel pengumuman."""
    cid = _to_int(getattr(channel, "id", 0))
    changed = False
    for cfg in level_guilds.values():
        if cid in (cfg.get("ignore_channels") or []):
            cfg["ignore_channels"] = [c for c in cfg["ignore_channels"] if c != cid]
            changed = True
        if cfg.get("announce_channel_id") == cid:
            cfg["announce_channel_id"] = None
            changed = True
    return changed
