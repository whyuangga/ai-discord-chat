"""Pelacak pertumbuhan server: **invite tracker** + statistik member (**0 kuota AI**).

Yang dicatat (semua lokal, tanpa AI):

| Data | Kegunaan |
| :--- | :--- |
| Siapa mengundang siapa | Papan **Top Inviter**, mendeteksi undangan "palsu" |
| Jumlah join & keluar per hari | Tren pertumbuhan (7/14/30 hari) |
| Member yang bertahan | **Retensi** (%) → kualitas undangan, bukan cuma jumlah |
| Umur akun saat join | Deteksi gelombang akun bot/raid |

Cara kerja invite tracker:
1. Bot menyimpan **jumlah pemakaian** setiap kode invite (`uses`).
2. Saat member join, bot mengambil daftar invite terbaru lalu mencari kode yang
   `uses`-nya **bertambah 1** → itulah undangan yang dipakai.
3. Bila bot tidak punya izin **Manage Server**, pelacakan invite otomatis dilewati
   dan statistik join/keluar tetap jalan.

Data disimpan di `data/growth.json` (atomik, dipangkas otomatis) dan **tidak menyimpan
isi pesan** sama sekali.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from config import DATA_DIR, GROWTH_FILE

logger = logging.getLogger("gemini_bot.growth_tracker")

_lock = asyncio.Lock()

KEEP_DAYS = 30              # hari statistik harian yang disimpan
KEEP_MEMBER_DAYS = 90       # umur data member sebelum dipangkas (yang sudah keluar)
MAX_MEMBERS = 2000          # batas member terlacak per server
QUICK_LEAVE_SEC = 3600      # keluar < 1 jam dianggap "cepat keluar"

growth_guilds: dict[int, dict] = {}      # guild_id -> konfigurasi
invite_cache: dict[int, dict[str, int]] = {}   # guild_id -> {code: uses}
join_records: dict[str, dict] = {}       # "guild:user" -> {inviter, code, joined_at, left_at}
inviter_stats: dict[str, dict] = {}      # "guild:inviter" -> {joins, leaves, quick_leaves}
daily: dict[int, dict[str, dict]] = {}   # guild_id -> {"YYYY-MM-DD": {joins, leaves}}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _key(guild_id: int, user_id: int) -> str:
    return f"{int(guild_id)}:{int(user_id)}"


def _today(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else float(now)))


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def default_config() -> dict:
    return {"enabled": True, "log_channel_id": None, "track_invites": True}


def get_config(guild_id: int) -> dict:
    gid = int(guild_id)
    cfg = growth_guilds.get(gid)
    if cfg is None:
        cfg = default_config()
        growth_guilds[gid] = cfg
    return cfg


def is_enabled(guild_id: int) -> bool:
    cfg = growth_guilds.get(int(guild_id))
    return bool(cfg.get("enabled", True)) if cfg else True


def set_config(guild_id: int, *, enabled: bool | None = None, log_channel_id: object = None,
               track_invites: bool | None = None) -> dict:
    """Mengubah konfigurasi pelacak pertumbuhan."""
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if track_invites is not None:
        cfg["track_invites"] = bool(track_invites)
    if log_channel_id is not None:
        cfg["log_channel_id"] = _to_int(log_channel_id) or None
    return cfg


def set_log_channel(guild_id: int, channel_id: int | None) -> dict:
    return set_config(guild_id, log_channel_id=_to_int(channel_id) or 0)


def handle_channel_delete(channel_id: int) -> bool:
    cid = _to_int(channel_id)
    changed = False
    for cfg in growth_guilds.values():
        if cfg.get("log_channel_id") == cid:
            cfg["log_channel_id"] = None
            changed = True
    return changed


# ==============================================================================
# INVITE TRACKER
# ==============================================================================
def _snapshot(invites) -> dict[str, int]:
    """Mengubah daftar invite Discord menjadi `{code: uses}`."""
    result: dict[str, int] = {}
    for invite in invites or []:
        code = str(getattr(invite, "code", "") or "")
        if not code:
            continue
        result[code] = _to_int(getattr(invite, "uses", 0))
    return result


async def sync_invites(guild) -> int:
    """Menyegarkan cache invite server. Mengembalikan jumlah kode terpantau."""
    if guild is None:
        return 0
    gid = _to_int(getattr(guild, "id", 0))
    if not gid:
        return 0
    fetch = getattr(guild, "invites", None)
    if not callable(fetch):
        return 0
    try:
        invites = await fetch()
    except Exception as exc:  # pragma: no cover - tanpa izin Manage Server
        logger.debug("Tidak bisa membaca invite server %s: %s", gid, exc)
        return 0
    invite_cache[gid] = _snapshot(invites)
    return len(invite_cache[gid])


def track_invite_create(guild_id: int, invite) -> None:
    """Menambah kode invite baru ke cache (event `on_invite_create`)."""
    gid = _to_int(guild_id)
    code = str(getattr(invite, "code", "") or "")
    if not gid or not code:
        return
    invite_cache.setdefault(gid, {})[code] = _to_int(getattr(invite, "uses", 0))


def track_invite_delete(guild_id: int, invite) -> None:
    """Membuang kode invite yang dihapus dari cache."""
    gid = _to_int(guild_id)
    code = str(getattr(invite, "code", "") or "")
    if not gid or not code:
        return
    invite_cache.get(gid, {}).pop(code, None)


async def detect_inviter(guild, member) -> tuple[int | None, str | None]:
    """Mencari siapa yang mengundang `member`. `(inviter_id, code)` atau `(None, None)`."""
    gid = _to_int(getattr(guild, "id", 0))
    if not gid or not get_config(gid).get("track_invites", True):
        return None, None

    fetch = getattr(guild, "invites", None)
    if not callable(fetch):
        return None, None
    try:
        fresh = _snapshot(await fetch())
    except Exception:  # pragma: no cover - tanpa izin
        return None, None

    previous = invite_cache.get(gid) or {}
    invite_cache[gid] = fresh
    if not previous:
        return None, None

    best_code: str | None = None
    best_delta = 0
    for code, uses in fresh.items():
        delta = uses - int(previous.get(code, 0))
        if delta > best_delta:
            best_delta = delta
            best_code = code

    if best_code is None:
        return None, None

    # Cari inviter dari daftar invite (butuh objek invite, bukan snapshot)
    try:
        for invite in await fetch():
            if str(getattr(invite, "code", "")) == best_code:
                inviter = getattr(invite, "inviter", None)
                return _to_int(getattr(inviter, "id", 0)) or None, best_code
    except Exception:  # pragma: no cover
        pass
    return None, best_code


# ==============================================================================
# PENCATATAN
# ==============================================================================
def record_join(
    guild_id: int,
    user_id: int,
    inviter_id: int | None = None,
    code: str | None = None,
    *,
    now: float | None = None,
) -> dict:
    """Menyimpan data satu member yang bergabung."""
    gid = int(guild_id)
    now_ts = time.time() if now is None else float(now)
    entry = {
        "guild_id": gid,
        "user_id": int(user_id),
        "inviter_id": _to_int(inviter_id) or None,
        "code": str(code or "")[:40] or None,
        "joined_at": now_ts,
        "left_at": 0.0,
    }
    join_records[_key(gid, user_id)] = entry

    day = _today(now_ts)
    bucket = daily.setdefault(gid, {}).setdefault(day, {"joins": 0, "leaves": 0})
    bucket["joins"] = _to_int(bucket.get("joins")) + 1

    if entry["inviter_id"]:
        stats = inviter_stats.setdefault(_key(gid, entry["inviter_id"]), {"joins": 0, "leaves": 0})
        stats["joins"] = _to_int(stats.get("joins")) + 1
    return entry


def record_leave(guild_id: int, user_id: int, *, now: float | None = None) -> dict | None:
    """Menandai member keluar & memperbarui statistik undangan."""
    gid = int(guild_id)
    now_ts = time.time() if now is None else float(now)
    key = _key(gid, user_id)
    entry = join_records.get(key) or {
        "guild_id": gid,
        "user_id": int(user_id),
        "inviter_id": None,
        "code": None,
        "joined_at": 0.0,
        "left_at": 0.0,
    }
    entry["left_at"] = now_ts
    join_records[key] = entry

    day = _today(now_ts)
    bucket = daily.setdefault(gid, {}).setdefault(day, {"joins": 0, "leaves": 0})
    bucket["leaves"] = _to_int(bucket.get("leaves")) + 1

    inviter_id = entry.get("inviter_id")
    if inviter_id:
        stats = inviter_stats.setdefault(_key(gid, inviter_id), {"joins": 0, "leaves": 0})
        stats["leaves"] = _to_int(stats.get("leaves")) + 1
        joined = float(entry.get("joined_at") or 0)
        if joined and now_ts - joined <= QUICK_LEAVE_SEC:
            stats["quick_leaves"] = _to_int(stats.get("quick_leaves")) + 1
    return entry


# ==============================================================================
# STATISTIK
# ==============================================================================
def _days_series(guild_id: int, days: int, *, now: float | None = None) -> list[tuple[str, int, int]]:
    """Deret harian `[(tanggal, join, keluar)]` dari terlama ke terbaru."""
    gid = int(guild_id)
    span = max(1, min(int(days), KEEP_DAYS))
    today_ts = time.time() if now is None else float(now)
    out: list[tuple[str, int, int]] = []
    for offset in range(span - 1, -1, -1):
        stamp = today_ts - offset * 86400
        day = _today(stamp)
        bucket = (daily.get(gid) or {}).get(day) or {}
        out.append((day, _to_int(bucket.get("joins")), _to_int(bucket.get("leaves"))))
    return out


def stats(guild_id: int, days: int = 7, *, now: float | None = None) -> dict:
    """Ringkasan pertumbuhan server untuk `days` hari terakhir."""
    gid = int(guild_id)
    series = _days_series(gid, days, now=now)
    joins = sum(item[1] for item in series)
    leaves = sum(item[2] for item in series)

    tracked = [rec for key, rec in join_records.items() if key.startswith(f"{gid}:")]
    stayed = sum(1 for rec in tracked if not rec.get("left_at"))
    retention = round((stayed / len(tracked)) * 100) if tracked else 0

    top: list[tuple[int, int, int]] = []
    for key, st in inviter_stats.items():
        try:
            gid_str, uid_str = key.split(":", 1)
        except ValueError:
            continue
        if int(gid_str) != gid:
            continue
        inviter_joins = _to_int(st.get("joins"))
        if inviter_joins:
            top.append((int(uid_str), inviter_joins, _to_int(st.get("quick_leaves"))))
    top.sort(key=lambda row: row[1], reverse=True)

    return {
        "days": max(1, min(int(days), KEEP_DAYS)),
        "joins": joins,
        "leaves": leaves,
        "net": joins - leaves,
        "retention_pct": retention,
        "tracked": len(tracked),
        "stayed": stayed,
        "top_inviters": top[:5],
        "series": series,
        "invites_cached": len(invite_cache.get(gid) or {}),
    }


def invite_leaderboard(guild_id: int, *, limit: int = 10) -> list[tuple[int, int, int, int]]:
    """`[(inviter_id, joins, keluar, cepat_keluar)]` terurut terbanyak mengundang."""
    gid = int(guild_id)
    rows: list[tuple[int, int, int, int]] = []
    for key, st in inviter_stats.items():
        try:
            gid_str, uid_str = key.split(":", 1)
        except ValueError:
            continue
        if int(gid_str) != gid:
            continue
        joins = _to_int(st.get("joins"))
        if joins <= 0:
            continue
        rows.append(
            (
                int(uid_str),
                joins,
                _to_int(st.get("leaves")),
                _to_int(st.get("quick_leaves")),
            )
        )
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows[: max(1, int(limit))]


def build_sparkline(series: list[tuple[str, int, int]]) -> str:
    """Bar sederhana untuk tren join per hari."""
    blocks = "▁▂▃▄▅▆▇█"
    joins = [item[1] for item in series]
    if not joins or max(joins) <= 0:
        return "_belum ada data_"
    peak = max(joins)
    return "".join(
        blocks[min(len(blocks) - 1, int((value / peak) * (len(blocks) - 1)))] if peak else blocks[0]
        for value in joins
    )


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def _prune(now: float | None = None) -> None:
    """Memangkas data harian & member lama agar file tetap kecil."""
    now_ts = time.time() if now is None else float(now)
    cutoff_day = _today(now_ts - KEEP_DAYS * 86400)

    for gid, bucket in list(daily.items()):
        keep = {day: val for day, val in bucket.items() if day >= cutoff_day}
        if keep:
            daily[gid] = keep
        else:
            daily.pop(gid, None)

    cutoff_ts = now_ts - KEEP_MEMBER_DAYS * 86400
    for key, rec in list(join_records.items()):
        if rec.get("left_at") and float(rec["left_at"]) < cutoff_ts:
            join_records.pop(key, None)

    per_guild: dict[int, list[str]] = {}
    for key in join_records:
        gid = _to_int(key.split(":", 1)[0])
        per_guild.setdefault(gid, []).append(key)
    for gid, keys in per_guild.items():
        if len(keys) <= MAX_MEMBERS:
            continue
        keys.sort(key=lambda k: float(join_records[k].get("joined_at") or 0), reverse=True)
        for key in keys[MAX_MEMBERS:]:
            join_records.pop(key, None)


def load_growth_from_disk() -> int:
    """Memuat konfigurasi, cache invite, & statistik dari `data/growth.json`."""
    growth_guilds.clear()
    invite_cache.clear()
    join_records.clear()
    inviter_stats.clear()
    daily.clear()

    path = Path(GROWTH_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid:
            continue
        growth_guilds[gid] = {
            "enabled": bool((data or {}).get("enabled", True)),
            "log_channel_id": _to_int((data or {}).get("log_channel_id")) or None,
            "track_invites": bool((data or {}).get("track_invites", True)),
        }

    for gid_str, bucket in (raw.get("invites") or {}).items():
        gid = _to_int(gid_str)
        if gid and isinstance(bucket, dict):
            invite_cache[gid] = {str(code): _to_int(uses) for code, uses in bucket.items()}

    for key, rec in (raw.get("members") or {}).items():
        if not isinstance(rec, dict):
            continue
        join_records[str(key)] = {
            "guild_id": _to_int(rec.get("guild_id")),
            "user_id": _to_int(rec.get("user_id")),
            "inviter_id": _to_int(rec.get("inviter_id")) or None,
            "code": str(rec.get("code") or "")[:40] or None,
            "joined_at": float(rec.get("joined_at") or 0),
            "left_at": float(rec.get("left_at") or 0),
        }

    for key, st in (raw.get("inviters") or {}).items():
        if isinstance(st, dict):
            inviter_stats[str(key)] = {
                "joins": _to_int(st.get("joins")),
                "leaves": _to_int(st.get("leaves")),
                "quick_leaves": _to_int(st.get("quick_leaves")),
            }

    for gid_str, bucket in (raw.get("daily") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(bucket, dict):
            continue
        daily[gid] = {
            str(day): {
                "joins": _to_int((val or {}).get("joins")),
                "leaves": _to_int((val or {}).get("leaves")),
            }
            for day, val in bucket.items()
        }

    return len(growth_guilds)


async def save_growth_to_disk() -> None:
    """Menyimpan data pertumbuhan secara atomik (setelah dipangkas)."""
    async with _lock:
        try:
            _prune()
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(gid): cfg for gid, cfg in growth_guilds.items()},
                "invites": {str(gid): bucket for gid, bucket in invite_cache.items() if bucket},
                "members": join_records,
                "inviters": inviter_stats,
                "daily": {str(gid): bucket for gid, bucket in daily.items() if bucket},
            }
            tmp_file = Path(str(GROWTH_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, GROWTH_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan growth.json: %s", exc)


def cleanup_growth_runtime() -> int:
    """Pemangkasan ringan saat pembersih RAM per jam berjalan."""
    before = len(join_records)
    _prune()
    return before - len(join_records)
