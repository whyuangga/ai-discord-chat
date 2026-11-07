"""Sistem moderasi bercatatan (ala Dyno/Carl-bot) — tanpa AI, tanpa kuota.

Isi:
    - Catatan kasus (`case`) per server: siapa, oleh siapa, jenis aksi, alasan, durasi.
    - Peringatan bertingkat: setelah N `warn` dalam jendela tertentu, bot otomatis
      memberi timeout (auto-punish) — perilaku sama seperti Dyno/YAGPDB.
    - Semua data lokal di `data/moderation.json`, aman restart.

Prinsip keamanan:
    - Modul ini **tidak** menghapus data apa pun kecuali Admin memintanya.
    - Aksi ke Discord tetap dicek izin & hierarki role oleh cog (lihat `cogs/moderation_cog.py`).
"""

import asyncio
import json
import logging
import re
import time

from config import DATA_DIR, MODERATION_FILE

logger = logging.getLogger("gemini_bot.moderation")

ACTIONS: dict[str, dict] = {
    "warn": {"label": "Peringatan", "emoji": "⚠️"},
    "timeout": {"label": "Timeout (bisu sementara)", "emoji": "🔇"},
    "kick": {"label": "Kick", "emoji": "👢"},
    "ban": {"label": "Ban", "emoji": "🔨"},
    "unban": {"label": "Unban", "emoji": "🔓"},
    "unmute": {"label": "Cabut timeout", "emoji": "🔊"},
    "note": {"label": "Catatan staff", "emoji": "📝"},
    "tempban": {"label": "Temp-ban (ban sementara)", "emoji": "⏳"},
    "softban": {"label": "Softban (hapus pesan, ban dicabut)", "emoji": "🧹"},
}

DEFAULT_SETTINGS: dict = {
    "log_channel": None,      # channel tempat setiap aksi moderasi dilaporkan
    "warn_threshold": 3,      # jumlah warn dalam jendela waktu sebelum auto-punish (0 = mati)
    "warn_window_days": 30,   # jendela hitung warn
    "auto_timeout_min": 60,   # durasi timeout otomatis (menit) saat ambang tercapai
    "dm_user": True,          # kirim DM ke member saat dikenai aksi
}

MAX_CASES_PER_GUILD = 800
MAX_BAN_DELETE_DAYS = 7
MAX_TEMPBAN_PER_GUILD = 200

mod_cases: dict[int, list[dict]] = {}
mod_settings: dict[int, dict] = {}
#: Ban sementara yang menunggu dicabut otomatis: {guild_id: [{case_id, user_id, until, ...}]}
mod_tempbans: dict[int, list[dict]] = {}
_disk_lock = asyncio.Lock()


# ==============================================================================
# PENGATURAN
# ==============================================================================
def get_settings(guild_id: int) -> dict:
    """Pengaturan moderasi server (selalu berisi semua kunci)."""
    stored = mod_settings.get(int(guild_id)) or {}
    settings = dict(DEFAULT_SETTINGS)
    settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    return settings


def set_settings(guild_id: int, **changes) -> dict:
    """Mengubah sebagian pengaturan moderasi."""
    current = get_settings(guild_id)
    for key, value in changes.items():
        if key not in DEFAULT_SETTINGS or value is None:
            continue
        if key == "warn_threshold":
            current[key] = max(0, min(10, int(value)))
        elif key == "warn_window_days":
            current[key] = max(1, min(365, int(value)))
        elif key == "auto_timeout_min":
            current[key] = max(1, min(10080, int(value)))
        elif key == "log_channel":
            current[key] = int(value)
        elif key == "dm_user":
            current[key] = bool(value)
    mod_settings[int(guild_id)] = current
    return current


def reset_settings(guild_id: int) -> None:
    mod_settings.pop(int(guild_id), None)


# ==============================================================================
# DURASI
# ==============================================================================
_DURATION_UNITS = {
    "d": 86400,
    "h": 3600,
    "j": 3600,
    "m": 60,
    "s": 1,
}


def parse_duration(text: str, *, default_sec: int = 600) -> int:
    """Mengubah `10m`, `1h30m`, `2d`, atau `600` menjadi detik."""
    raw = str(text or "").strip().lower()
    if not raw:
        return default_sec
    if raw.isdigit():
        return max(1, int(raw))

    total = 0
    for amount, unit in re.findall(r"(\d+)\s*([dhjms])", raw):
        total += int(amount) * _DURATION_UNITS[unit]
    return total if total > 0 else default_sec


def format_duration(seconds: int | None) -> str:
    """Menyajikan durasi dalam bahasa Indonesia singkat."""
    if not seconds:
        return "permanen"
    remaining = int(seconds)
    parts: list[str] = []
    for label, size in (("hari", 86400), ("jam", 3600), ("menit", 60), ("detik", 1)):
        if remaining >= size:
            amount, remaining = divmod(remaining, size)
            parts.append(f"{amount} {label}")
        if len(parts) == 2:
            break
    return " ".join(parts) or "instan"


# ==============================================================================
# CATATAN KASUS
# ==============================================================================
def _next_case_id(guild_id: int) -> int:
    cases = mod_cases.get(int(guild_id)) or []
    return max((int(case.get("id", 0)) for case in cases), default=0) + 1


def add_case(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    action: str,
    reason: str = "",
    *,
    duration_sec: int | None = None,
    expires_at: float | None = None,
) -> dict:
    """Mencatat satu kasus moderasi (juga dipakai untuk aksi otomatis bot)."""
    key = str(action or "").strip().lower()
    case = {
        "id": _next_case_id(guild_id),
        "user_id": int(user_id),
        "moderator_id": int(moderator_id),
        "action": key if key in ACTIONS else "note",
        "reason": str(reason or "").strip()[:400],
        "duration_sec": int(duration_sec) if duration_sec else None,
        "created_at": time.time(),
        "expires_at": float(expires_at) if expires_at else None,
    }
    cases = mod_cases.setdefault(int(guild_id), [])
    cases.append(case)
    if len(cases) > MAX_CASES_PER_GUILD:
        del cases[:-MAX_CASES_PER_GUILD]
    return case


def list_cases(guild_id: int, user_id: int | None = None, *, limit: int = 10) -> list[dict]:
    """Kasus terbaru (opsional difilter per member), urut dari yang paling baru."""
    cases = mod_cases.get(int(guild_id)) or []
    filtered = (
        [case for case in cases if int(case.get("user_id", 0)) == int(user_id)]
        if user_id is not None
        else list(cases)
    )
    return list(reversed(filtered))[: max(1, limit)]


def get_case(guild_id: int, case_id: int) -> dict | None:
    for case in mod_cases.get(int(guild_id)) or []:
        if int(case.get("id", 0)) == int(case_id):
            return case
    return None


def delete_case(guild_id: int, case_id: int) -> bool:
    cases = mod_cases.get(int(guild_id)) or []
    for index, case in enumerate(cases):
        if int(case.get("id", 0)) == int(case_id):
            del cases[index]
            return True
    return False


def count_warns(guild_id: int, user_id: int, *, days: int | None = None) -> int:
    """Jumlah `warn` aktif (dalam jendela hari tertentu) untuk satu member."""
    window = get_settings(guild_id)["warn_window_days"] if days is None else max(1, int(days))
    cutoff = time.time() - window * 86400
    return sum(
        1
        for case in mod_cases.get(int(guild_id)) or []
        if int(case.get("user_id", 0)) == int(user_id)
        and case.get("action") == "warn"
        and float(case.get("created_at", 0)) >= cutoff
    )


def should_auto_punish(guild_id: int, user_id: int) -> tuple[bool, int]:
    """True + durasi timeout (menit) bila jumlah warn mencapai ambang server."""
    settings = get_settings(guild_id)
    threshold = int(settings["warn_threshold"])
    if threshold <= 0:
        return False, 0
    if count_warns(guild_id, user_id) < threshold:
        return False, 0
    return True, int(settings["auto_timeout_min"])


def cleanup_moderation_runtime(limit: int = 200) -> int:
    """Memangkas server tak aktif dari memori agar hemat RAM Free Tier."""
    removed = 0
    if len(mod_cases) > limit:
        for gid in list(mod_cases)[: len(mod_cases) - limit]:
            mod_cases.pop(gid, None)
            mod_settings.pop(gid, None)
            mod_tempbans.pop(gid, None)
            removed += 1
    return removed


# ==============================================================================
# BAN SEMENTARA (TEMP-BAN)
# ==============================================================================
def add_tempban(
    guild_id: int,
    user_id: int,
    *,
    case_id: int = 0,
    until: float,
    oleh: int = 0,
    reason: str = "",
) -> dict:
    """Mencatat ban sementara yang harus dicabut otomatis saat `until` lewat."""
    entry = {
        "case_id": int(case_id or 0),
        "user_id": int(user_id),
        "until": float(until),
        "moderator_id": int(oleh or 0),
        "reason": str(reason or "")[:200],
    }
    daftar = mod_tempbans.setdefault(int(guild_id), [])
    daftar = [e for e in daftar if int(e.get("user_id", 0)) != entry["user_id"]]
    daftar.append(entry)
    mod_tempbans[int(guild_id)] = daftar[-MAX_TEMPBAN_PER_GUILD:]
    return entry


def list_tempbans(guild_id: int) -> list[dict]:
    """Ban sementara yang masih menunggu, urut dari yang paling cepat berakhir."""
    return sorted(mod_tempbans.get(int(guild_id)) or [], key=lambda e: float(e.get("until", 0)))


def due_tempbans(now: float | None = None) -> list[tuple[int, dict]]:
    """Semua ban sementara yang sudah waktunya dicabut (tanpa mengubah apa pun)."""
    batas = float(now if now is not None else time.time())
    hasil: list[tuple[int, dict]] = []
    for gid, daftar in mod_tempbans.items():
        for entry in daftar:
            if float(entry.get("until", 0)) <= batas:
                hasil.append((int(gid), entry))
    return hasil


def drop_tempban(guild_id: int, user_id: int) -> bool:
    """Membuang satu ban sementara dari daftar tunggu (setelah dicabut)."""
    daftar = mod_tempbans.get(int(guild_id)) or []
    baru = [e for e in daftar if int(e.get("user_id", 0)) != int(user_id)]
    if len(baru) == len(daftar):
        return False
    if baru:
        mod_tempbans[int(guild_id)] = baru
    else:
        mod_tempbans.pop(int(guild_id), None)
    return True


def cleanup_tempbans(now: float | None = None) -> int:
    """Membuang entri temp-ban yang sudah kedaluwarsa (sisa restart/gagal unban)."""
    hapus = 0
    for gid, entry in due_tempbans(now):
        if drop_tempban(gid, int(entry.get("user_id", 0))):
            hapus += 1
    return hapus


# ==============================================================================
# PENCARIAN & STATISTIK STAF
# ==============================================================================
def search_cases(
    guild_id: int,
    *,
    q: str = "",
    user_id: int | None = None,
    aksi: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Cari kasus berdasarkan nomor kasus, ID member, jenis aksi, atau kata di alasan."""
    kata = str(q or "").strip().lower().lstrip("#")
    aksi = str(aksi or "").strip().lower() or None
    hasil: list[dict] = []
    for case in reversed(mod_cases.get(int(guild_id)) or []):
        if user_id is not None and int(case.get("user_id", 0)) != int(user_id):
            continue
        if aksi and str(case.get("action", "")) != aksi:
            continue
        if kata and kata not in " ".join(
            (
                str(case.get("id", "")),
                str(case.get("user_id", "")),
                str(case.get("action", "")),
                str(case.get("reason", "")).lower(),
            )
        ):
            continue
        hasil.append(case)
        if len(hasil) >= max(1, int(limit)):
            break
    return hasil


def staff_stats(guild_id: int, *, days: int | None = None, limit: int = 10) -> dict:
    """Siapa menindak berapa banyak: total per moderator + rincian per jenis aksi."""
    cutoff = 0.0
    if days:
        cutoff = time.time() - max(1, int(days)) * 86400
    per_orang: dict[int, dict] = {}
    per_aksi: dict[str, int] = {}
    total = 0
    for case in mod_cases.get(int(guild_id)) or []:
        if float(case.get("created_at", 0)) < cutoff:
            continue
        aksi = str(case.get("action", "note"))
        pembuat = int(case.get("moderator_id") or 0)
        if aksi == "note":
            continue  # catatan staff bukan tindakan
        total += 1
        per_aksi[aksi] = per_aksi.get(aksi, 0) + 1
        data = per_orang.setdefault(pembuat, {"moderator_id": pembuat, "total": 0, "per_aksi": {}})
        data["total"] += 1
        data["per_aksi"][aksi] = data["per_aksi"].get(aksi, 0) + 1
    papan = sorted(per_orang.values(), key=lambda d: (-d["total"], d["moderator_id"]))
    return {
        "total": total,
        "hari": int(days) if days else 0,
        "per_aksi": per_aksi,
        "moderator": papan[: max(1, int(limit))],
        "otomatis": per_orang.get(0, {}).get("total", 0),
    }


async def run_tempban_check(bot) -> int:
    """Mencabut ban sementara yang sudah waktunya habis (dipanggil watcher utama).

    Aman dipanggil sesering apa pun: tidak ada ban yang jatuh tempo → tidak ada kerja.
    """
    import discord

    from utils import sanitize_error_message

    jumlah = 0
    for gid, entry in due_tempbans():
        guild = bot.get_guild(gid) if bot is not None else None
        if guild is None:
            continue
        uid = int(entry.get("user_id", 0))
        if not uid:
            continue
        try:
            await guild.unban(discord.Object(id=uid), reason="Temp-ban berakhir otomatis")
        except discord.NotFound:
            drop_tempban(gid, uid)  # sudah tidak diban — jangan dicoba lagi
            continue
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.info("Gagal mencabut temp-ban %s di server %s: %s", uid, gid, sanitize_error_message(exc))
            continue
        case = add_case(gid, uid, getattr(getattr(bot, "user", None), "id", 0) or 0, "unban", "Temp-ban berakhir otomatis")
        drop_tempban(gid, uid)
        jumlah += 1
        settings = get_settings(gid)
        log_id = settings.get("log_channel")
        if log_id:
            channel = guild.get_channel(int(log_id))
            if channel is not None:
                try:
                    await channel.send(
                        f"⏳ Temp-ban **{uid}** berakhir — ban dicabut otomatis (kasus `#{case['id']}`)."
                    )
                except Exception as exc:  # pragma: no cover - jaring aman
                    logger.debug("Gagal mengirim log temp-ban: %s", exc)
    if jumlah:
        await save_moderation_to_disk()
    return jumlah


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_moderation_from_disk() -> tuple[int, int]:
    """Memuat kasus & pengaturan dari data/moderation.json → (jumlah server kasus, jumlah kasus)."""
    if not MODERATION_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(MODERATION_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", MODERATION_FILE, exc)
        return 0, 0

    total = 0
    for gid_str, gdata in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        cases = []
        for item in (gdata.get("cases") or [])[-MAX_CASES_PER_GUILD:]:
            try:
                cases.append(
                    {
                        "id": int(item["id"]),
                        "user_id": int(item["user_id"]),
                        "moderator_id": int(item.get("moderator_id") or 0),
                        "action": str(item.get("action") or "note"),
                        "reason": str(item.get("reason") or "")[:400],
                        "duration_sec": int(item["duration_sec"]) if item.get("duration_sec") else None,
                        "created_at": float(item.get("created_at") or time.time()),
                        "expires_at": float(item["expires_at"]) if item.get("expires_at") else None,
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        if cases:
            mod_cases[gid] = cases
            total += len(cases)
        tunggu = []
        for entry in (gdata.get("tempbans") or [])[-MAX_TEMPBAN_PER_GUILD:]:
            try:
                tunggu.append(
                    {
                        "case_id": int(entry.get("case_id") or 0),
                        "user_id": int(entry["user_id"]),
                        "until": float(entry["until"]),
                        "moderator_id": int(entry.get("moderator_id") or 0),
                        "reason": str(entry.get("reason") or "")[:200],
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        if tunggu:
            mod_tempbans[gid] = tunggu
        if gdata.get("settings"):
            mod_settings[gid] = {**DEFAULT_SETTINGS, **{
                k: v for k, v in gdata["settings"].items() if k in DEFAULT_SETTINGS
            }}
    return len(mod_cases), total


async def save_moderation_to_disk() -> None:
    """Menyimpan kasus & pengaturan secara atomik."""
    async with _disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            semua = set(mod_cases) | set(mod_tempbans) | set(mod_settings)
            payload = {
                "guilds": {
                    str(gid): {
                        "cases": mod_cases.get(gid) or [],
                        "settings": mod_settings.get(gid),
                        "tempbans": mod_tempbans.get(gid) or [],
                    }
                    for gid in semua
                }
            }
            tmp = MODERATION_FILE.with_suffix(".json.tmp")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp.write_text, text, "utf-8")
            import os

            await asyncio.to_thread(os.replace, tmp, MODERATION_FILE)
        except Exception as exc:
            logger.warning("Gagal menyimpan moderation.json: %s", exc)


def summarize_case(case: dict, guild=None) -> str:
    """Satu baris ringkas untuk `/mod catatan`."""
    meta = ACTIONS.get(str(case.get("action")), {"emoji": "•", "label": "Aksi"})
    reason = case.get("reason") or "_tanpa alasan_"
    duration = case.get("duration_sec")
    duration_text = f" ({format_duration(duration)})" if duration else ""
    when = time.strftime("%d/%m/%y %H:%M", time.localtime(float(case.get("created_at", 0))))
    return (
        f"`#{case['id']}` {meta['emoji']} **{meta['label']}**{duration_text} — {reason} • {when}"
    )
