"""Fitur komunitas **Tier 2A** — ramai tanpa memakai kuota Gemini sama sekali.

Isi modul ini:
1. Giveaway      — undian berhadiah dengan tombol 🎉, pemenang diacak otomatis.
2. Ulang Tahun   — member mendaftarkan tanggal lahir, bot mengucapkan otomatis.
3. Auto-Responder — balasan otomatis berbasis kata kunci per channel (dengan jeda aman).
4. Pengumuman Terjadwal — pesan Admin yang dikirim sekali / harian / mingguan.

Seluruh fitur **default NONAKTIF** sampai Admin menyalakannya per server/channel,
sehingga server yang belum memakainya tidak menambah beban apa pun. Semua data
disimpan di `data/engagement.json` dengan penulisan atomik.
"""

import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
import channel_targets

import message_template

try:  # Python 3.9+
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python lama
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[misc,assignment]

from config import BOT_TIMEZONE, ENGAGEMENT_FILE, GIVEAWAY_HISTORY_MAX, DATA_DIR
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.engagement")

_lock = asyncio.Lock()

# ==============================================================================
# STATE GLOBAL (dimuat & disimpan ke data/engagement.json)
# ==============================================================================
giveaways: dict[int, dict] = {}          # message_id -> data giveaway
birthday_guilds: dict[int, dict] = {}    # guild_id -> {channel_id, hour, minute, last_announced}
birthdays: dict[str, dict] = {}          # "guild_id:user_id" -> {day, month, year, user_id, guild_id}
auto_reply_channels: dict[int, dict] = {}  # channel_id -> {guild_id, enabled, cooldown, rules, last_fired}
announcements: dict[int, dict] = {}      # announcement_id -> data pengumuman terjadwal
giveaway_templates: dict[int, dict] = {}  # guild_id -> {nama: {winner_count, seconds, requirements, bonus_roles}}
giveaway_defaults: dict[int, dict] = {}   # guild_id -> setelan bawaan giveaway berlapis

# Jadwal berulang berbasis interval: minimal 2 jam (batas Discohook), maksimal seminggu.
MIN_INTERVAL_MINUTES = 120
MAX_INTERVAL_MINUTES = 7 * 24 * 60

# Batas aman giveaway berlapis.
GIVEAWAY_MAX_WEIGHT = 6          # bobot maksimal per peserta (anti-curang)
GIVEAWAY_MAX_TEMPLATE = 25       # template per server
GIVEAWAY_MAX_REQUIREMENT_ROLES = 5
GIVEAWAY_MAX_ENTRY_LOG = 200     # jejak peserta per giveaway (buat audit dashboard)

_giveaway_seq: int = 0
_announcement_seq: int = 0
_last_auto_reply_at: dict[int, float] = {}


# ==============================================================================
# UTILITAS DASAR
# ==============================================================================
def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def get_timezone(tz_name: str | None) -> timezone:
    """Mengambil objek zona waktu; jatuh ke Asia/Jakarta (+7) bila tidak dikenal."""
    clean = (tz_name or BOT_TIMEZONE).strip() or BOT_TIMEZONE
    if ZoneInfo is not None:
        try:
            return ZoneInfo(clean)  # type: ignore[return-value]
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            pass
    return timezone(timedelta(hours=7))


def now_in(tz_name: str | None) -> datetime:
    return datetime.now(get_timezone(tz_name))


def format_duration_short(seconds: int) -> str:
    """Format durasi singkat Bahasa Indonesia: `2j 15m`."""
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} hari")
    if hours:
        parts.append(f"{hours}j")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not parts:
        parts.append(f"{secs}d")
    return " ".join(parts) or "0d"


def format_timestamp(epoch: float, style: str = "F") -> str:
    """Format waktu Discord `<t:...>` agar otomatis mengikuti zona waktu pembaca."""
    return f"<t:{int(epoch)}:{style}>"


_INDONESIAN_MONTHS = (
    "januari", "februari", "maret", "april", "mei", "juni",
    "juli", "agustus", "september", "oktober", "november", "desember",
)
_WEEKDAYS = ("senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu")


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def _muat_giveaway(raw: dict) -> None:
    """Giveaway aktif beserta riwayat & bobot bonus role."""
    for mid_str, data in (raw.get("giveaways") or {}).items():
        try:
            mid = int(mid_str)
            prize = str(data.get("prize") or "").strip()
            if not prize:
                continue
            giveaways[mid] = {
                "message_id": mid,
                "guild_id": _to_int(data.get("guild_id")),
                "channel_id": _to_int(data.get("channel_id")),
                "prize": prize[:200],
                "host_id": _to_int(data.get("host_id")),
                "winner_count": max(1, _to_int(data.get("winner_count"), 1)),
                "ends_at": float(data.get("ends_at") or 0),
                "ended": bool(data.get("ended", False)),
                "role_id": _to_int(data.get("role_id")) or None,
                "requirements": normalize_requirements(
                    roles=(data.get("requirements") or {}).get("roles")
                    or ([data.get("role_id")] if data.get("role_id") else []),
                    level=(data.get("requirements") or {}).get("level"),
                    account_age_days=(data.get("requirements") or {}).get("account_age_days"),
                ),
                "bonus_roles": {
                    str(k): max(1, min(5, _to_int(v, 1)))
                    for k, v in (data.get("bonus_roles") or {}).items()
                    if _to_int(k)
                },
                "weights": {
                    str(k): max(1, min(GIVEAWAY_MAX_WEIGHT, _to_int(v, 1)))
                    for k, v in (data.get("weights") or {}).items()
                    if _to_int(k)
                },
                "history": [
                    {
                        "at": float(item.get("at") or 0),
                        "aksi": str(item.get("aksi") or "akhir")[:20],
                        "pemenang": [_to_int(x) for x in (item.get("pemenang") or []) if _to_int(x)],
                        "oleh": _to_int(item.get("oleh")),
                    }
                    for item in (data.get("history") or [])
                    if isinstance(item, dict)
                ][-GIVEAWAY_HISTORY_MAX:],
                "entries": [_to_int(x) for x in (data.get("entries") or []) if _to_int(x)],
                "winners": [_to_int(x) for x in (data.get("winners") or []) if _to_int(x)],
            }
        except (TypeError, ValueError):
            continue



def _muat_giveaway_template(raw: dict) -> None:
    """Template giveaway per server."""
    for gid_str, data in (raw.get("giveaway_templates") or {}).items():
        try:
            gid = int(gid_str)
            kumpulan: dict[str, dict] = {}
            for nama, isi in (data or {}).items():
                kunci = str(nama or "").strip().lower()
                if not kunci or not isinstance(isi, dict):
                    continue
                kumpulan[kunci] = {
                    "nama": str(isi.get("nama") or nama)[:60],
                    "winner_count": max(1, min(20, _to_int(isi.get("winner_count"), 1))),
                    "seconds": max(60, _to_int(isi.get("seconds"), 3600)),
                    "requirements": normalize_requirements(
                        roles=(isi.get("requirements") or {}).get("roles"),
                        level=(isi.get("requirements") or {}).get("level"),
                        account_age_days=(isi.get("requirements") or {}).get("account_age_days"),
                    ),
                    "bonus_roles": {
                        str(k): max(1, min(5, _to_int(v, 1)))
                        for k, v in (isi.get("bonus_roles") or {}).items()
                        if _to_int(k)
                    },
                }
            if kumpulan:
                giveaway_templates[gid] = kumpulan
        except (TypeError, ValueError):
            continue



def _muat_giveaway_default(raw: dict) -> None:
    """Nilai bawaan giveaway per server (durasi, syarat, pemenang)."""
    for gid_str, data in (raw.get("giveaway_defaults") or {}).items():
        try:
            gid = int(gid_str)
            if not isinstance(data, dict):
                continue
            giveaway_defaults[gid] = {
                "winner_count": max(1, min(20, _to_int(data.get("winner_count"), 1))),
                "seconds": max(60, min(30 * 86400, _to_int(data.get("seconds"), 3600))),
                "level": max(0, min(500, _to_int(data.get("level")))),
                "account_age_days": max(0, min(3650, _to_int(data.get("account_age_days")))),
                "bonus_role_id": _to_int(data.get("bonus_role_id")),
                "bonus_weight": max(1, min(5, _to_int(data.get("bonus_weight"), 1))),
                "ping_everyone": bool(data.get("ping_everyone", False)),
            }
        except (TypeError, ValueError):
            continue



def _muat_channel_ultah(raw: dict) -> None:
    """Channel pengumuman ulang tahun per server."""
    for gid_str, data in (raw.get("birthday_channels") or {}).items():
        try:
            birthday_guilds[int(gid_str)] = {
                "channel_id": _to_int(data.get("channel_id")),
                "hour": min(23, max(0, _to_int(data.get("hour"), 8))),
                "minute": min(59, max(0, _to_int(data.get("minute"), 0))),
                "last_announced": str(data.get("last_announced") or ""),
            }
        except (TypeError, ValueError):
            continue



def _muat_ultah(raw: dict) -> None:
    """Data ulang tahun member."""
    for key, data in (raw.get("birthdays") or {}).items():
        try:
            day = _to_int(data.get("day"))
            month = _to_int(data.get("month"))
            user_id = _to_int(data.get("user_id"))
            guild_id = _to_int(data.get("guild_id"))
            if not (1 <= day <= 31 and 1 <= month <= 12 and user_id and guild_id):
                continue
            birthdays[f"{guild_id}:{user_id}"] = {
                "guild_id": guild_id,
                "user_id": user_id,
                "day": day,
                "month": month,
                "year": _to_int(data.get("year")) or None,
            }
        except (TypeError, ValueError):
            continue



def _muat_auto_reply(raw: dict) -> None:
    """Auto-responder per channel."""
    for cid_str, data in (raw.get("auto_replies") or {}).items():
        try:
            rules = []
            for rule in data.get("rules") or []:
                trigger = str(rule.get("trigger") or "").strip()
                reply = str(rule.get("reply") or "").strip()
                if not trigger or not reply:
                    continue
                rules.append(
                    {
                        "trigger": trigger[:120],
                        "reply": reply[:1500],
                        "mode": "persis" if rule.get("mode") == "persis" else "kata",
                    }
                )
            if not rules:
                continue
            auto_reply_channels[int(cid_str)] = {
                "guild_id": _to_int(data.get("guild_id")),
                "enabled": bool(data.get("enabled", True)),
                "cooldown": max(0, _to_int(data.get("cooldown"), 20)),
                "rules": rules[:30],
                "last_fired": float(data.get("last_fired") or 0),
            }
        except (TypeError, ValueError):
            continue



def _muat_pengumuman(raw: dict) -> None:
    """Pengumuman terjadwal (harian & interval)."""
    global _giveaway_seq, _announcement_seq
    for aid_str, data in (raw.get("announcements") or {}).items():
        try:
            aid = int(aid_str)
            content = str(data.get("content") or "").strip()
            if not content:
                continue
            kind = str(data.get("kind") or "harian")
            if kind == "interval":
                # Data lama/rusak: interval di luar batas dirapikan, 0 dianggap harian.
                menit = _to_int(data.get("interval_minutes"))
                if menit <= 0:
                    kind = "harian"
                menit = min(MAX_INTERVAL_MINUTES, max(MIN_INTERVAL_MINUTES, menit))
            else:
                menit = _to_int(data.get("interval_minutes"))
            announcements[aid] = {
                "id": aid,
                "guild_id": _to_int(data.get("guild_id")),
                "channel_id": _to_int(data.get("channel_id")),
                "title": str(data.get("title") or "")[:200],
                "content": content[:1900],
                "kind": kind,
                "hour": min(23, max(0, _to_int(data.get("hour"), 8))),
                "minute": min(59, max(0, _to_int(data.get("minute"), 0))),
                "weekday": _to_int(data.get("weekday"), 0) % 7,
                "interval_minutes": menit,
                "next_run_at": float(data.get("next_run_at") or 0),
                "last_sent_at": float(data.get("last_sent_at") or 0),
                "enabled": bool(data.get("enabled", True)),
                "created_by": _to_int(data.get("created_by")),
            }
            _announcement_seq = max(_announcement_seq, aid)
        except (TypeError, ValueError):
            continue




def load_engagement_from_disk() -> tuple[int, int, int, int]:
    """Memuat giveaway, ulang tahun, auto-responder, & pengumuman terjadwal.

    Tiap kelompok dimuat oleh helper sendiri (`_muat_*`) agar satu data rusak
    hanya melewati bagiannya, bukan seluruh berkas.
    """
    global _giveaway_seq, _announcement_seq
    giveaways.clear()
    giveaway_templates.clear()
    giveaway_defaults.clear()
    birthday_guilds.clear()
    birthdays.clear()
    auto_reply_channels.clear()
    announcements.clear()
    _giveaway_seq = 0
    _announcement_seq = 0

    if not ENGAGEMENT_FILE.exists():
        return 0, 0, 0, 0

    try:
        raw = json.loads(ENGAGEMENT_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", ENGAGEMENT_FILE, exc)
        return 0, 0, 0, 0

    _muat_giveaway(raw)
    _muat_giveaway_template(raw)
    _muat_giveaway_default(raw)
    _muat_channel_ultah(raw)
    _muat_ultah(raw)
    _muat_auto_reply(raw)
    _muat_pengumuman(raw)

    return (
        len(giveaways),
        len(birthdays),
        len(auto_reply_channels),
        len(announcements),
    )


def _pesan_galat(exc: Exception) -> str:
    """Pesan galat yang aman dicatat (token/URL sudah disaring)."""
    from utils import sanitize_error_message

    return sanitize_error_message(exc)

async def save_engagement_to_disk() -> None:
    """Menyimpan seluruh data fitur engagement secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "giveaways": {str(k): v for k, v in giveaways.items()},
                "giveaway_templates": {
                    str(k): v for k, v in giveaway_templates.items() if v
                },
                "giveaway_defaults": {str(k): v for k, v in giveaway_defaults.items() if v},
                "birthday_channels": {str(k): v for k, v in birthday_guilds.items()},
                "birthdays": {
                    str(k): {
                        "guild_id": v["guild_id"],
                        "user_id": v["user_id"],
                        "day": v["day"],
                        "month": v["month"],
                        "year": v.get("year"),
                    }
                    for k, v in birthdays.items()
                },
                "auto_replies": {str(k): v for k, v in auto_reply_channels.items()},
                "announcements": {str(k): v for k, v in announcements.items()},
            }
            tmp_file = Path(str(ENGAGEMENT_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, ENGAGEMENT_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan engagement.json: %s", _pesan_galat(exc))


# ==============================================================================
# 1. GIVEAWAY (/giveaway)
# ==============================================================================
def parse_giveaway_duration(raw: str | None) -> int | None:
    """Membaca durasi giveaway: `10m`, `2 jam`, `1j30m`, `2 hari`, `45` (menit)."""
    from community_tools import parse_reminder_duration

    return parse_reminder_duration(raw)


def _norm_roles(roles) -> list[int]:
    """Daftar role syarat yang unik & dibatasi jumlahnya."""
    hasil: list[int] = []
    for item in roles or []:
        rid = _to_int(item)
        if rid and rid not in hasil:
            hasil.append(rid)
    return hasil[:GIVEAWAY_MAX_REQUIREMENT_ROLES]


def normalize_requirements(*, roles=None, level=None, account_age_days=None) -> dict:
    """Merapikan syarat giveaway: role wajib, level minimum, & umur akun minimum.

    Nilai `0` berarti syarat itu **tidak dipakai**, jadi giveaway lama (tanpa syarat)
    tetap berjalan persis seperti sebelumnya.
    """
    return {
        "roles": _norm_roles(roles),
        "level": max(0, min(500, _to_int(level))),
        "account_age_days": max(0, min(3650, _to_int(account_age_days))),
    }


def normalize_bonus_roles(bonus_roles) -> dict[str, int]:
    """Role peluang ekstra → tambahan bobot undian (1–5, kunci selalu string ID)."""
    hasil: dict[str, int] = {}
    for rid, extra in dict(bonus_roles or {}).items():
        kunci = str(_to_int(rid))
        if kunci == "0":
            continue
        hasil[kunci] = max(1, min(5, _to_int(extra, 1)))
    return hasil


def describe_requirements(cfg: dict) -> list[str]:
    """Baris-baris syarat giveaway dalam bahasa manusia (untuk embed & dashboard)."""
    req = cfg.get("requirements") or {}
    roles = _norm_roles(req.get("roles"))
    baris: list[str] = []
    if roles:
        if len(roles) == 1:
            baris.append(f"Punya role <@&{roles[0]}>")
        else:
            baris.append("Punya role " + " + ".join(f"<@&{rid}>" for rid in roles))
    level = _to_int(req.get("level"))
    if level:
        baris.append(f"Level minimal **{level}**")
    hari = _to_int(req.get("account_age_days"))
    if hari:
        baris.append(f"Akun berumur minimal **{hari} hari**")
    bonus = normalize_bonus_roles(cfg.get("bonus_roles"))
    if bonus:
        baris.append(
            "Peluang ekstra: " + " · ".join(f"<@&{rid}> +{bobot}" for rid, bobot in bonus.items())
        )
    return baris


def requirement_summary(cfg: dict) -> str:
    """Ringkasan satu baris syarat (dipakai `/giveaway daftar` & dashboard)."""
    baris = describe_requirements(cfg)
    return " · ".join(baris) if baris else "tanpa syarat"


def describe_rejection(kode: str, cfg: dict) -> str:
    """Kalimat alasan penolakan + rincian syarat (dipakai tombol & command)."""
    req = cfg.get("requirements") or {}
    alasan = {
        "syarat_role": "role yang diwajibkan belum kamu miliki",
        "syarat_level": f"level kamu belum mencapai **{_to_int(req.get('level'))}**",
        "syarat_umur": "umur akun Discord-mu belum cukup",
    }.get(kode, "syarat giveaway belum terpenuhi")
    baris = describe_requirements(cfg)
    rincian = "\n".join(f"• {item}" for item in baris)
    return f"🔒 **Belum bisa ikut** — {alasan}." + (f"\n{rincian}" if rincian else "")


def check_requirements(
    cfg: dict,
    *,
    role_ids: set[int] | list[int] | None = None,
    level: int | None = None,
    account_age_days: int | None = None,
) -> str | None:
    """Cek semua syarat. `None` = lolos, selain itu kode alasan penolakan.

    Kode: `syarat_role`, `syarat_level`, `syarat_umur`. Bila data member tidak
    diberikan (`None`), syarat itu dianggap **tidak terpenuhi** supaya tidak ada
    yang lolos tanpa bukti.
    """
    req = cfg.get("requirements") or {}
    wajib = set(_norm_roles(req.get("roles")))
    if wajib:
        punya = {_to_int(r) for r in (role_ids or [])}
        if not wajib.issubset(punya):
            return "syarat_role"
    level_min = _to_int(req.get("level"))
    if level_min and _to_int(level) < level_min:
        return "syarat_level"
    umur_min = _to_int(req.get("account_age_days"))
    if umur_min and _to_int(account_age_days) < umur_min:
        return "syarat_umur"
    return None


def entry_weight(cfg: dict, role_ids: set[int] | list[int] | None = None) -> tuple[int, list[int]]:
    """Bobot undian seorang peserta + daftar role bonus yang ia miliki."""
    punya = {_to_int(r) for r in (role_ids or [])}
    bobot = 1
    pakai: list[int] = []
    for rid, extra in normalize_bonus_roles(cfg.get("bonus_roles")).items():
        if _to_int(rid) in punya:
            bobot += extra
            pakai.append(_to_int(rid))
    return min(GIVEAWAY_MAX_WEIGHT, bobot), pakai


def _weight_of(cfg: dict, user_id: int) -> int:
    weights = cfg.get("weights") or {}
    return max(1, min(GIVEAWAY_MAX_WEIGHT, _to_int(weights.get(str(int(user_id))), 1)))


def _add_history(cfg: dict, aksi: str, winners: list[int], actor_id: int = 0) -> None:
    """Menyimpan jejak pengundian (siapa diundi, kapan, oleh siapa)."""
    riwayat = list(cfg.get("history") or [])
    riwayat.append(
        {
            "at": time.time(),
            "aksi": "reroll" if aksi == "reroll" else "akhir",
            "pemenang": [int(x) for x in winners],
            "oleh": int(actor_id or 0),
        }
    )
    cfg["history"] = riwayat[-GIVEAWAY_HISTORY_MAX:]


def giveaway_history(message_id: int) -> list[dict]:
    """Riwayat pengundian & reroll satu giveaway (terbaru di akhir)."""
    cfg = giveaways.get(int(message_id)) or {}
    return list(cfg.get("history") or [])


def build_giveaway_embed(cfg: dict, *, ended: bool = False, winners: list[int] | None = None) -> discord.Embed:
    """Embed pengumuman giveaway (dipakai saat mulai, diperbarui saat pesertaan, & saat selesai)."""
    entries = cfg.get("entries") or []
    ends_at = float(cfg.get("ends_at") or 0)
    winner_count = max(1, _to_int(cfg.get("winner_count"), 1))

    if ended:
        title = "🎉 Giveaway Selesai!"
        color = discord.Color.dark_green()
    else:
        title = "🎉 GIVEAWAY!"
        color = discord.Color.gold()

    embed = discord.Embed(title=title, color=color)
    embed.description = f"## {cfg.get('prize', '-')}"
    embed.add_field(name="🏆 Jumlah Pemenang", value=f"`{winner_count}` orang", inline=True)
    embed.add_field(name="👥 Peserta", value=f"`{len(entries)}`", inline=True)

    if ended:
        winners = winners if winners is not None else (cfg.get("winners") or [])
        if winners:
            embed.add_field(
                name="🥳 Pemenang",
                value="\n".join(f"{idx}. <@{uid}>" for idx, uid in enumerate(winners, start=1))[:1024],
                inline=False,
            )
        else:
            embed.add_field(name="🥳 Pemenang", value="_Tidak ada peserta yang memenuhi syarat._", inline=False)
        embed.set_footer(text="Bot tidak pernah menagih data pribadi lewat DM.")
    else:
        if ends_at:
            embed.add_field(
                name="⏰ Berakhir",
                value=f"{format_timestamp(ends_at, 'F')} ({format_timestamp(ends_at, 'R')})",
                inline=False,
            )
        syarat = describe_requirements(cfg)
        if syarat:
            embed.add_field(
                name="🔒 Syarat Ikut",
                value="\n".join(f"• {baris}" for baris in syarat)[:1024],
                inline=False,
            )
        embed.add_field(
            name="📝 Cara Ikut",
            value="Tekan tombol **Ikuti Giveaway** di bawah. Boleh keluar-masuk kapan saja sebelum waktu habis.",
            inline=False,
        )
        embed.set_footer(text="Satu akun = satu peluang (role bonus menambah peluang).")

    host_id = _to_int(cfg.get("host_id"))
    if host_id:
        embed.add_field(name="🎁 Diadakan oleh", value=f"<@{host_id}>", inline=True)
    return embed


def create_giveaway(
    *,
    guild_id: int,
    channel_id: int,
    message_id: int,
    prize: str,
    host_id: int,
    seconds: int,
    winner_count: int = 1,
    role_id: int | None = None,
    requirements: dict | None = None,
    bonus_roles: dict | None = None,
) -> dict:
    """Mendaftarkan giveaway baru setelah pesannya berhasil dikirim.

    `role_id` lama tetap didukung (jadi syarat role pertama). `requirements`
    menampung `roles`, `level`, & `account_age_days`; `bonus_roles` memetakan
    role → tambahan bobot undian.
    """
    global _giveaway_seq
    _giveaway_seq += 1
    sumber = requirements if isinstance(requirements, dict) else {}
    req = normalize_requirements(
        roles=sumber.get("roles") or ([role_id] if role_id else None),
        level=sumber.get("level"),
        account_age_days=sumber.get("account_age_days"),
    )
    cfg = {
        "message_id": int(message_id),
        "guild_id": int(guild_id),
        "channel_id": int(channel_id),
        "prize": str(prize or "")[:200],
        "host_id": int(host_id),
        "winner_count": max(1, min(20, int(winner_count))),
        "ends_at": time.time() + max(10, int(seconds)),
        "ended": False,
        "role_id": req["roles"][0] if req["roles"] else None,
        "requirements": req,
        "bonus_roles": normalize_bonus_roles(bonus_roles),
        "weights": {},
        "entry_log": [],
        "history": [],
        "entries": [],
        "winners": [],
    }
    giveaways[int(message_id)] = cfg
    return cfg


def join_giveaway(
    message_id: int,
    user_id: int,
    role_ids: set[int] | None = None,
    *,
    level: int | None = None,
    account_age_days: int | None = None,
) -> tuple[str, dict | None]:
    """Mendaftarkan peserta. Mengembalikan `(status, data_giveaway)`.

    Status: `ok`, `ended`, `duplikat`, `syarat_role`, `syarat_level`, `syarat_umur`,
    `tidak_ada`.
    """
    cfg = giveaways.get(int(message_id))
    if cfg is None:
        return "tidak_ada", None
    if cfg.get("ended") or float(cfg.get("ends_at") or 0) <= time.time():
        return "ended", cfg
    entries = cfg.setdefault("entries", [])
    if int(user_id) in entries:
        return "duplikat", cfg
    alasan = check_requirements(
        cfg, role_ids=role_ids, level=level, account_age_days=account_age_days
    )
    if alasan:
        return alasan, cfg
    entries.append(int(user_id))
    bobot, pakai = entry_weight(cfg, role_ids)
    cfg.setdefault("weights", {})[str(int(user_id))] = bobot
    log = cfg.setdefault("entry_log", [])
    log.append({"user_id": int(user_id), "at": time.time(), "weight": bobot, "bonus": pakai})
    if len(log) > GIVEAWAY_MAX_ENTRY_LOG:
        del log[:-GIVEAWAY_MAX_ENTRY_LOG]
    return "ok", cfg


def leave_giveaway(message_id: int, user_id: int) -> tuple[str, dict | None]:
    """Membatalkan pesertaan. Status: `ok`, `ended`, `tidak_terdaftar`, `tidak_ada`."""
    cfg = giveaways.get(int(message_id))
    if cfg is None:
        return "tidak_ada", None
    if cfg.get("ended") or float(cfg.get("ends_at") or 0) <= time.time():
        return "ended", cfg
    entries = cfg.setdefault("entries", [])
    if int(user_id) not in entries:
        return "tidak_terdaftar", cfg
    entries.remove(int(user_id))
    (cfg.get("weights") or {}).pop(str(int(user_id)), None)
    log = cfg.get("entry_log") or []
    cfg["entry_log"] = [item for item in log if _to_int(item.get("user_id")) != int(user_id)]
    return "ok", cfg


def pick_winners(
    entries: list[int],
    count: int,
    *,
    rng: random.Random | None = None,
    weights: dict | None = None,
) -> list[int]:
    """Mengacak pemenang unik. Bila `weights` diberikan, undian berbobot."""
    pool = [int(x) for x in entries]
    if not pool:
        return []
    picker = rng or random
    amount = max(0, min(int(count), len(pool)))
    if not weights:
        return picker.sample(pool, amount)

    sisa = {uid: max(1, min(GIVEAWAY_MAX_WEIGHT, _to_int(weights.get(str(uid), weights.get(uid, 1)), 1))) for uid in pool}
    hasil: list[int] = []
    for _ in range(amount):
        total = sum(sisa.values())
        if total <= 0:  # pragma: no cover - jaring aman
            break
        undian = picker.random() * total
        akumulasi = 0.0
        dipilih = None
        for uid in list(sisa.keys()):
            akumulasi += sisa[uid]
            if undian <= akumulasi:
                dipilih = uid
                break
        if dipilih is None:  # pragma: no cover - pembulatan float
            dipilih = list(sisa.keys())[-1]
        hasil.append(dipilih)
        sisa.pop(dipilih, None)
    return hasil


def end_giveaway(
    message_id: int, *, rng: random.Random | None = None, actor_id: int = 0
) -> dict | None:
    """Menutup giveaway & menentukan pemenang (idempoten)."""
    cfg = giveaways.get(int(message_id))
    if cfg is None or cfg.get("ended"):
        return None
    cfg["ended"] = True
    cfg["winners"] = pick_winners(
        cfg.get("entries") or [],
        cfg.get("winner_count") or 1,
        rng=rng,
        weights=cfg.get("weights"),
    )
    _add_history(cfg, "akhir", cfg["winners"], actor_id)
    return cfg


def reroll_giveaway(
    message_id: int, *, rng: random.Random | None = None, actor_id: int = 0
) -> tuple[str, dict | None]:
    """Mengundi ulang pemenang dari peserta yang belum pernah menang.

    Setiap reroll tercatat di `history` sehingga bisa diaudit dari dashboard.
    Status: `ok`, `belum_selesai`, `habis`, `tidak_ada`.
    """
    cfg = giveaways.get(int(message_id))
    if cfg is None:
        return "tidak_ada", None
    if not cfg.get("ended"):
        return "belum_selesai", cfg
    previous = [int(x) for x in (cfg.get("winners") or [])]
    semua_pernah_menang = {
        int(x) for riwayat in (cfg.get("history") or []) for x in (riwayat.get("pemenang") or [])
    }
    remaining = [
        int(x)
        for x in (cfg.get("entries") or [])
        if int(x) not in previous and int(x) not in semua_pernah_menang
    ]
    if not remaining:
        # Semua peserta sudah pernah menang → ulangi dari peserta yang belum menang
        # di putaran ini saja supaya tombol reroll tidak mengunci selamanya.
        remaining = [int(x) for x in (cfg.get("entries") or []) if int(x) not in previous]
    if not remaining:
        return "habis", cfg
    cfg["winners"] = pick_winners(
        remaining, cfg.get("winner_count") or 1, rng=rng, weights=cfg.get("weights")
    )
    _add_history(cfg, "reroll", cfg["winners"], actor_id)
    return "ok", cfg


async def run_giveaway_check(bot: discord.Client) -> int:
    """Menutup giveaway yang waktunya sudah habis & mengumumkan pemenangnya."""
    now = time.time()
    due = [
        mid
        for mid, cfg in list(giveaways.items())
        if not cfg.get("ended") and float(cfg.get("ends_at") or 0) <= now
    ]
    finished = 0
    for mid in due:
        cfg = end_giveaway(mid)
        if cfg is None:
            continue
        finished += 1
        await _update_giveaway_message(bot, cfg)

    if finished:
        await save_engagement_to_disk()
        await _prune_ended_giveaways()
    return finished


async def _update_giveaway_message(bot: discord.Client, cfg: dict) -> bool:
    """Mengedit pesan giveaway agar embed-nya sesuai kondisi terbaru."""
    get_channel = getattr(bot, "get_channel", None)
    channel = get_channel(_to_int(cfg.get("channel_id"))) if callable(get_channel) else None
    if channel is None:
        return False
    try:
        message = channel.get_partial_message(int(cfg["message_id"]))
        view = None
        if not cfg.get("ended"):
            from views import GiveawayJoinView

            view = GiveawayJoinView()
        await message.edit(embed=build_giveaway_embed(cfg, ended=bool(cfg.get("ended"))), view=view)
        return True
    except discord.NotFound:
        giveaways.pop(int(cfg["message_id"]), None)
        return False
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.debug("Gagal memperbarui giveaway: %s", sanitize_error_message(exc))
        return False


async def _prune_ended_giveaways(max_items: int = 25) -> None:
    """Membatasi jumlah giveaway selesai yang disimpan agar file JSON tetap kecil."""
    ended = [(mid, float(cfg.get("ends_at") or 0)) for mid, cfg in giveaways.items() if cfg.get("ended")]
    if len(ended) <= max_items:
        return
    ended.sort(key=lambda item: item[1])
    for mid, _ in ended[: len(ended) - max_items]:
        giveaways.pop(mid, None)
    await save_engagement_to_disk()


# ==============================================================================
# 1b. GIVEAWAY BERLAPIS — setelan bawaan server & template
# ==============================================================================
def default_giveaway_config(guild_id: int) -> dict:
    """Setelan bawaan giveaway satu server (dipakai `/giveaway mulai` & dashboard)."""
    data = giveaway_defaults.get(int(guild_id)) or {}
    return {
        "winner_count": max(1, min(20, _to_int(data.get("winner_count"), 1))),
        "seconds": max(60, min(30 * 86400, _to_int(data.get("seconds"), 3600))),
        "level": max(0, min(500, _to_int(data.get("level")))),
        "account_age_days": max(0, min(3650, _to_int(data.get("account_age_days")))),
        "bonus_role_id": _to_int(data.get("bonus_role_id")) or 0,
        "bonus_weight": max(1, min(5, _to_int(data.get("bonus_weight"), 1))),
        "ping_everyone": bool(data.get("ping_everyone", False)),
    }


def set_giveaway_defaults(guild_id: int, **kwargs) -> dict:
    """Mengubah sebagian setelan bawaan giveaway satu server."""
    gid = int(guild_id)
    sekarang = default_giveaway_config(gid)
    for kunci, nilai in kwargs.items():
        if kunci in ("winner_count", "seconds", "level", "account_age_days", "bonus_role_id"):
            sekarang[kunci] = max(0, _to_int(nilai))
        elif kunci == "bonus_weight":
            sekarang[kunci] = max(1, min(5, _to_int(nilai, 1)))
        elif kunci == "ping_everyone":
            sekarang[kunci] = bool(nilai)
    sekarang["winner_count"] = max(1, min(20, sekarang["winner_count"]))
    sekarang["seconds"] = max(60, min(30 * 86400, sekarang["seconds"]))
    sekarang["level"] = min(500, sekarang["level"])
    sekarang["account_age_days"] = min(3650, sekarang["account_age_days"])
    giveaway_defaults[gid] = dict(sekarang)
    return dict(sekarang)


def default_requirements(guild_id: int) -> dict:
    """Syarat bawaan server dalam bentuk siap pakai `create_giveaway(requirements=…)`."""
    data = default_giveaway_config(guild_id)
    return normalize_requirements(level=data["level"], account_age_days=data["account_age_days"])


def default_bonus_roles(guild_id: int) -> dict[str, int]:
    """Bonus role bawaan server (`{}` bila belum diatur)."""
    data = default_giveaway_config(guild_id)
    if not data["bonus_role_id"]:
        return {}
    return {str(data["bonus_role_id"]): data["bonus_weight"]}


def save_giveaway_template(
    guild_id: int,
    nama: str,
    *,
    winner_count: int = 1,
    seconds: int = 3600,
    requirements: dict | None = None,
    bonus_roles: dict | None = None,
) -> tuple[bool, str]:
    """Menyimpan (atau menimpa) template giveaway satu server. `(ok, pesan)`."""
    gid = int(guild_id)
    kunci = str(nama or "").strip().lower()
    if not kunci:
        return False, "Nama template tidak boleh kosong."
    if len(kunci) > 40:
        return False, "Nama template maksimal 40 karakter."
    kumpulan = giveaway_templates.setdefault(gid, {})
    if kunci not in kumpulan and len(kumpulan) >= GIVEAWAY_MAX_TEMPLATE:
        return False, f"Template sudah penuh (maksimal {GIVEAWAY_MAX_TEMPLATE}). Hapus satu dulu."
    sumber = requirements if isinstance(requirements, dict) else {}
    kumpulan[kunci] = {
        "nama": str(nama).strip()[:60],
        "winner_count": max(1, min(20, _to_int(winner_count, 1))),
        "seconds": max(60, min(30 * 86400, _to_int(seconds, 3600))),
        "requirements": normalize_requirements(
            roles=sumber.get("roles"),
            level=sumber.get("level"),
            account_age_days=sumber.get("account_age_days"),
        ),
        "bonus_roles": normalize_bonus_roles(bonus_roles),
    }
    return True, f"Template **{kumpulan[kunci]['nama']}** disimpan."


def get_giveaway_template(guild_id: int, nama: str) -> dict | None:
    """Ambil satu template (tidak peka huruf besar/kecil)."""
    kunci = str(nama or "").strip().lower()
    return (giveaway_templates.get(int(guild_id)) or {}).get(kunci)


def list_giveaway_templates(guild_id: int) -> list[dict]:
    """Semua template server (urut nama)."""
    items = list((giveaway_templates.get(int(guild_id)) or {}).values())
    return sorted(items, key=lambda item: str(item.get("nama") or "").lower())


def delete_giveaway_template(guild_id: int, nama: str) -> bool:
    """Hapus satu template; `True` bila ada yang dihapus."""
    gid = int(guild_id)
    kumpulan = giveaway_templates.get(gid) or {}
    kunci = str(nama or "").strip().lower()
    if kunci not in kumpulan:
        return False
    kumpulan.pop(kunci, None)
    if not kumpulan:
        giveaway_templates.pop(gid, None)
    return True


def apply_giveaway_template(guild_id: int, nama: str) -> dict | None:
    """Kwarg siap pakai untuk `create_giveaway` dari sebuah template."""
    tpl = get_giveaway_template(guild_id, nama)
    if not tpl:
        return None
    return {
        "winner_count": tpl["winner_count"],
        "seconds": tpl["seconds"],
        "requirements": dict(tpl["requirements"]),
        "bonus_roles": dict(tpl["bonus_roles"]),
    }


def guild_giveaways(guild_id: int) -> list[dict]:
    """Semua giveaway satu server, yang masih berjalan lebih dulu."""
    items = [cfg for cfg in giveaways.values() if _to_int(cfg.get("guild_id")) == int(guild_id)]
    return sorted(items, key=lambda cfg: (bool(cfg.get("ended")), -float(cfg.get("ends_at") or 0)))


def reroll_pool_size(message_id: int) -> int:
    """Berapa peserta yang masih bisa muncul di reroll berikutnya."""
    cfg = giveaways.get(int(message_id)) or {}
    sudah = {
        int(x) for riwayat in (cfg.get("history") or []) for x in (riwayat.get("pemenang") or [])
    }
    return len([x for x in (cfg.get("entries") or []) if int(x) not in sudah])


# ==============================================================================
# 2. ULANG TAHUN (/ultah)
# ==============================================================================
def parse_birthday_date(raw: str | None) -> tuple[int, int, int | None] | None:
    """Membaca tanggal lahir fleksibel: `12-08`, `12/8/2000`, `12 agustus`, `1 Januari 1999`.

    Mengembalikan `(hari, bulan, tahun|None)` atau `None` bila tidak valid.
    """
    text = str(raw or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"(?i)\b(tgl|tanggal|lahir)\b", " ", text).strip()
    text = re.sub(r"\s+", " ", text.replace(",", " ")).strip()

    numbers = re.findall(r"\d{1,4}", text)
    if not numbers:
        return None

    # Format angka: 12-08, 12/8/2000, 2000-08-12
    if re.fullmatch(r"\d{1,4}\s*[-/.]\s*\d{1,2}(\s*[-/.]\s*\d{1,4})?", text):
        parts = [int(p) for p in re.split(r"[-/.]", text) if p.strip()]
        if len(parts) >= 3 and parts[0] > 31:  # YYYY-MM-DD
            year, month, day = parts[0], parts[1], parts[2]
        elif len(parts) == 3:
            day, month, year = parts[0], parts[1], parts[2]
        else:
            day, month, year = parts[0], parts[1], None
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None
        if year is not None and not (1900 <= year <= 2100):
            year = None
        return day, month, year

    # Format nama bulan: "12 agustus 1999" / "agustus 12"
    for idx, month_name in enumerate(_INDONESIAN_MONTHS, start=1):
        if month_name in text:
            day_match = re.search(r"\d{1,2}", text.replace(month_name, " "))
            if not day_match:
                return None
            day = int(day_match.group(0))
            year = None
            for candidate in numbers:
                if len(candidate) == 4 and 1900 <= int(candidate) <= 2100:
                    year = int(candidate)
            if not (1 <= day <= 31):
                return None
            return day, idx, year

    return None


def set_birthday(guild_id: int, user_id: int, day: int, month: int, year: int | None = None) -> dict:
    """Menyimpan/memperbarui tanggal lahir seorang member."""
    key = f"{int(guild_id)}:{int(user_id)}"
    birthdays[key] = {
        "guild_id": int(guild_id),
        "user_id": int(user_id),
        "day": int(day),
        "month": int(month),
        "year": int(year) if year else None,
    }
    return birthdays[key]


def remove_birthday(guild_id: int, user_id: int) -> bool:
    return birthdays.pop(f"{int(guild_id)}:{int(user_id)}", None) is not None


def get_birthday(guild_id: int, user_id: int) -> dict | None:
    return birthdays.get(f"{int(guild_id)}:{int(user_id)}")


def list_birthdays(guild_id: int, month: int | None = None) -> list[dict]:
    """Daftar ulang tahun sebuah server, diurutkan per tanggal (opsional: satu bulan)."""
    items = [
        data
        for data in birthdays.values()
        if data.get("guild_id") == int(guild_id) and (month is None or data.get("month") == int(month))
    ]
    return sorted(items, key=lambda d: (int(d.get("month") or 0), int(d.get("day") or 0)))


def birthday_age(data: dict, current_year: int) -> int | None:
    """Menghitung umur pada tahun berjalan (bila tahun lahir diisi)."""
    year = data.get("year")
    if not year:
        return None
    age = int(current_year) - int(year)
    return age if 0 < age < 130 else None


def set_birthday_channel(guild_id: int, channel_id: int, hour: int = 8, minute: int = 0) -> dict:
    """Mengaktifkan/mengubah channel & jam pengumuman ulang tahun server."""
    cfg = {
        "channel_id": int(channel_id),
        "hour": min(23, max(0, int(hour))),
        "minute": min(59, max(0, int(minute))),
        "last_announced": (birthday_guilds.get(int(guild_id)) or {}).get("last_announced", ""),
    }
    birthday_guilds[int(guild_id)] = cfg
    return cfg


def disable_birthday_channel(guild_id: int) -> bool:
    return birthday_guilds.pop(int(guild_id), None) is not None


def build_birthday_embed(items: list[dict], *, today: datetime, include_age: bool = True) -> discord.Embed:
    """Embed ucapan ulang tahun untuk member yang berulang tahun hari ini."""
    embed = discord.Embed(
        title="🎂 Selamat Ulang Tahun!",
        description=f"Ada yang berulang tahun hari ini ({today.day} {_INDONESIAN_MONTHS[today.month - 1]})! 🎉",
        color=discord.Color.magenta(),
    )
    mentions = []
    for data in items:
        line = f"🎉 <@{data['user_id']}>"
        age = birthday_age(data, today.year) if include_age else None
        if age:
            line += f" — **{age} tahun**"
        mentions.append(line)
    if mentions:
        embed.add_field(name="Yang Berbahagia", value="\n".join(mentions)[:1024], inline=False)
    embed.set_footer(text="Semoga sehat selalu, rezeki lancar, & bahagia! 🥳")
    return embed


async def run_birthday_check(bot: discord.Client) -> int:
    """Mengirim ucapan ulang tahun sekali sehari pada jam yang diatur Admin."""
    sent = 0
    for guild_id, cfg in list(birthday_guilds.items()):
        ids = channel_targets.daftar(cfg, "channel_id")
        channel = await resolve_channel(bot, ids[0] if ids else 0)
        if channel is None:
            continue

        guild = None
        get_guild = getattr(bot, "get_guild", None)
        if callable(get_guild):
            guild = get_guild(int(guild_id))
        tz_name = BOT_TIMEZONE
        if guild is not None:
            try:
                from community_agent import get_guild_settings

                tz_name = get_guild_settings(int(guild_id)).get("timezone", BOT_TIMEZONE)
            except Exception:  # pragma: no cover - modul opsional
                tz_name = BOT_TIMEZONE

        today = now_in(tz_name)
        if str(cfg.get("last_announced") or "") == today.strftime("%Y-%m-%d"):
            continue
        if (today.hour, today.minute) < (int(cfg.get("hour") or 0), int(cfg.get("minute") or 0)):
            continue

        todays = [
            data
            for data in birthdays.values()
            if data.get("guild_id") == int(guild_id)
            and int(data.get("day") or 0) == today.day
            and int(data.get("month") or 0) == today.month
        ]
        cfg["last_announced"] = today.strftime("%Y-%m-%d")
        if not todays:
            continue

        try:
            embed_ultah = build_birthday_embed(todays, today=today)

            async def _kirim(channel):
                await channel.send(
                    embed=embed_ultah,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )

            if await channel_targets.sebarkan(bot, ids, _kirim):
                sent += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Gagal kirim ucapan ultah di %s: %s", guild_id, sanitize_error_message(exc))
            continue
        await save_engagement_to_disk()

    if sent:
        await save_engagement_to_disk()
    return sent


# ==============================================================================
# 3. AUTO-RESPONDER (/jawab-otomatis)
# ==============================================================================
def set_auto_reply_config(
    channel_id: int,
    guild_id: int,
    *,
    enabled: bool | None = None,
    cooldown: int | None = None,
) -> dict:
    """Mengaktifkan/mematikan auto-responder & mengatur jeda aman per channel."""
    cfg = auto_reply_channels.get(int(channel_id))
    if cfg is None:
        cfg = {
            "guild_id": int(guild_id),
            "enabled": True,
            "cooldown": 20,
            "rules": [],
            "last_fired": 0.0,
        }
        auto_reply_channels[int(channel_id)] = cfg
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if cooldown is not None:
        cfg["cooldown"] = max(0, min(300, int(cooldown)))
    return cfg


def add_auto_reply(
    channel_id: int,
    guild_id: int,
    trigger: str,
    reply: str,
    *,
    mode: str = "kata",
    max_rules: int = 25,
) -> tuple[str, dict | None]:
    """Menambahkan aturan balasan otomatis. Status: `ok`, `duplikat`, `penuh`, `kosong`."""
    trigger = str(trigger or "").strip()
    reply = str(reply or "").strip()
    if not trigger or not reply:
        return "kosong", None
    cfg = set_auto_reply_config(channel_id, guild_id)
    rules = cfg.setdefault("rules", [])
    normalized = "persis" if mode == "persis" else "kata"
    for rule in rules:
        if rule.get("trigger", "").lower() == trigger.lower() and rule.get("mode") == normalized:
            return "duplikat", cfg
    if len(rules) >= max_rules:
        return "penuh", cfg
    rules.append({"trigger": trigger[:120], "reply": reply[:1500], "mode": normalized})
    return "ok", cfg


def remove_auto_reply(channel_id: int, trigger: str) -> bool:
    """Menghapus satu aturan berdasarkan pemicunya (tidak peka huruf besar/kecil)."""
    cfg = auto_reply_channels.get(int(channel_id))
    if not cfg:
        return False
    target = str(trigger or "").strip().lower()
    rules = cfg.get("rules") or []
    kept = [rule for rule in rules if rule.get("trigger", "").lower() != target]
    if len(kept) == len(rules):
        return False
    cfg["rules"] = kept
    if not kept:
        auto_reply_channels.pop(int(channel_id), None)
    return True


def source_has_invite_or_link(content: str) -> bool:
    """Mendeteksi link/undangan agar auto-responder tidak dipakai menyebarkan spam."""
    return bool(re.search(r"(?i)(https?://|discord\.gg/|www\.)", str(content or "")))


def match_auto_reply(channel_id: int, content: str, *, now: float | None = None) -> str | None:
    """Mencari balasan yang cocok untuk sebuah pesan (menghormati jeda aman per channel)."""
    cfg = auto_reply_channels.get(int(channel_id))
    if not cfg or not cfg.get("enabled"):
        return None
    text = str(content or "").strip()
    if not text:
        return None

    current = time.time() if now is None else float(now)
    cooldown = float(cfg.get("cooldown") or 0)
    last_fired = max(float(cfg.get("last_fired") or 0), _last_auto_reply_at.get(int(channel_id), 0.0))
    if cooldown and current - last_fired < cooldown:
        return None

    lowered = text.lower()
    best: tuple[int, str] | None = None
    for rule in cfg.get("rules") or []:
        trigger = str(rule.get("trigger") or "").lower()
        if not trigger:
            continue
        if rule.get("mode") == "persis":
            if lowered == trigger or lowered.strip("!?., ") == trigger:
                best = (len(trigger), str(rule.get("reply") or ""))
                break
        elif trigger in lowered:
            score = len(trigger)
            if best is None or score > best[0]:
                best = (score, str(rule.get("reply") or ""))

    if best is None:
        return None
    cfg["last_fired"] = current
    _last_auto_reply_at[int(channel_id)] = current
    return best[1]


# ==============================================================================
# 4. PENGUMUMAN TERJADWAL (/pengumuman)
# ==============================================================================
def parse_announcement_schedule(raw: str | None) -> dict | None:
    """Membaca jadwal pengumuman.

    Format yang diterima:
    - `08:00` atau `harian 08:00`      ➔ setiap hari
    - `senin 19:00` / `mingguan sabtu 20:30` ➔ setiap minggu
    - `sekali 31-12-2026 23:59`        ➔ satu kali
    - `setiap 3 jam` / `tiap 90 menit` ➔ berulang tiap interval (min. 2 jam)

    Mengembalikan `{kind, hour, minute, weekday, once_at, interval_minutes}` atau `None`.
    """
    text = str(raw or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)

    kind = "harian"
    if text.startswith(("setiap", "tiap", "interval")):
        kind = "interval"
        text = re.sub(r"^(setiap|tiap|interval)\s*", "", text).strip()
        cocok = re.search(r"(\d{1,4})\s*(menit|mnt|min|jam|j|hr|hours?)", text)
        if not cocok:
            return None
        jumlah = int(cocok.group(1))
        satuan = cocok.group(2)
        menit = jumlah if satuan in ("menit", "mnt", "min") else jumlah * 60
        if not (MIN_INTERVAL_MINUTES <= menit <= MAX_INTERVAL_MINUTES):
            return None
        return {
            "kind": "interval",
            "interval_minutes": menit,
            "hour": 0,
            "minute": 0,
            "weekday": 0,
        }
    if text.startswith("sekali"):
        kind = "sekali"
        text = text[len("sekali"):].strip()
    elif text.startswith("mingguan"):
        kind = "mingguan"
        text = text[len("mingguan"):].strip()
    elif text.startswith("harian"):
        kind = "harian"
        text = text[len("harian"):].strip()

    time_match = re.search(r"(\d{1,2})\s*[:.]\s*(\d{2})", text)
    hour = minute = None
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

    if kind == "sekali":
        date_match = re.search(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", text)
        if not date_match or hour is None:
            return None
        day, month, year = (int(g) for g in date_match.groups())
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None
        try:
            once_dt = datetime(year, month, day, hour, minute or 0)
        except ValueError:
            return None
        return {
            "kind": "sekali",
            "hour": hour,
            "minute": minute or 0,
            "weekday": 0,
            "once_at": once_dt,
        }

    if hour is None:
        return None

    # "senin 19:00" tanpa kata "mingguan" tetap dianggap mingguan — dulu nama hari
    # diabaikan sehingga jadwalnya berjalan SETIAP HARI.
    weekday = 0
    ada_hari = False
    for idx, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name}\b", text):
            weekday = idx
            ada_hari = True
            break

    if kind == "harian" and ada_hari:
        kind = "mingguan"
    if kind == "mingguan" and not ada_hari:
        return None

    return {
        "kind": kind,
        "hour": hour,
        "minute": minute or 0,
        "weekday": weekday,
    }


def compute_next_run(spec: dict, *, tz_name: str | None = None, reference: datetime | None = None) -> float:
    """Menghitung epoch kapan pengumuman berikutnya harus dikirim."""
    now = reference or now_in(tz_name)
    if spec.get("kind") == "interval":
        menit = min(
            MAX_INTERVAL_MINUTES,
            max(MIN_INTERVAL_MINUTES, _to_int(spec.get("interval_minutes"), MIN_INTERVAL_MINUTES)),
        )
        return (now + timedelta(minutes=menit)).timestamp()
    if spec.get("kind") == "sekali":
        once_at: datetime = spec["once_at"]
        localized = once_at.replace(tzinfo=get_timezone(tz_name))
        return localized.timestamp() if localized > now else 0.0

    target_hour = int(spec.get("hour") or 0)
    target_minute = int(spec.get("minute") or 0)
    candidate = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if spec.get("kind") == "mingguan":
        delta = (int(spec.get("weekday") or 0) - now.weekday()) % 7
        candidate = candidate + timedelta(days=delta)
        if candidate <= now:
            candidate += timedelta(days=7)
    elif candidate <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def advance_interval_next_run(
    interval_minutes: int,
    last_ts: float,
    *,
    now: float | None = None,
) -> float:
    """Jadwal interval berikutnya setelah `last_ts` — tanpa menumpuk kiriman yang terlewat.

    Bot yang sempat mati lama tidak akan mengirim puluhan pengumuman sekaligus: semua
    jadwal yang sudah lewat dilewati, lalu diambil satu titik berikutnya.
    """
    menit = min(
        MAX_INTERVAL_MINUTES,
        max(MIN_INTERVAL_MINUTES, _to_int(interval_minutes, MIN_INTERVAL_MINUTES)),
    )
    langkah = menit * 60
    sekarang = time.time() if now is None else float(now)
    nxt = float(last_ts or 0)
    if not nxt:
        return sekarang + langkah
    if nxt > sekarang:
        return nxt
    lewat = int((sekarang - nxt) // langkah) + 1
    return nxt + lewat * langkah


def add_announcement(
    guild_id: int,
    channel_id: int,
    content: str,
    spec: dict,
    *,
    title: str = "",
    created_by: int = 0,
    tz_name: str | None = None,
    max_items: int = 15,
) -> tuple[str, dict | None]:
    """Menyimpan pengumuman terjadwal baru. Status: `ok`, `penuh`, `kosong`."""
    global _announcement_seq
    body = str(content or "").strip()
    if not body:
        return "kosong", None
    existing = [a for a in announcements.values() if a.get("guild_id") == int(guild_id)]
    if len(existing) >= max_items:
        return "penuh", None

    _announcement_seq += 1
    cfg = {
        "id": _announcement_seq,
        "guild_id": int(guild_id),
        "channel_id": int(channel_id),
        "title": str(title or "")[:200],
        "content": body[:1900],
        "kind": spec.get("kind") or "harian",
        "hour": int(spec.get("hour") or 0),
        "minute": int(spec.get("minute") or 0),
        "weekday": int(spec.get("weekday") or 0),
        "interval_minutes": _to_int(spec.get("interval_minutes")),
        "next_run_at": compute_next_run(spec, tz_name=tz_name),
        "last_sent_at": 0.0,
        "enabled": True,
        "created_by": int(created_by),
    }
    announcements[_announcement_seq] = cfg
    return "ok", cfg


def update_announcement(
    announcement_id: int,
    guild_id: int | None = None,
    *,
    content: str | None = None,
    title: str | None = None,
    spec: dict | None = None,
    tz_name: str | None = None,
) -> tuple[str, dict | None]:
    """Ubah isi/judul/jadwal pengumuman tanpa menghapusnya.

    Status: `ok`, `tidak_ada` (ID bukan milik server ini), `kosong` (isi jadi kosong).
    """
    cfg = announcements.get(int(announcement_id))
    if cfg is None or (guild_id is not None and cfg.get("guild_id") != int(guild_id)):
        return "tidak_ada", None

    if content is not None:
        body = str(content).strip()
        if not body:
            return "kosong", None
        cfg["content"] = body[:1900]
    if title is not None:
        cfg["title"] = str(title)[:200]
    if spec is not None:
        cfg["kind"] = spec.get("kind") or cfg.get("kind") or "harian"
        cfg["hour"] = int(spec.get("hour") or 0)
        cfg["minute"] = int(spec.get("minute") or 0)
        cfg["weekday"] = int(spec.get("weekday") or 0)
        cfg["interval_minutes"] = _to_int(spec.get("interval_minutes"))
        cfg["next_run_at"] = compute_next_run(spec, tz_name=tz_name)
        cfg["enabled"] = True
    return "ok", cfg


async def send_announcement_now(
    bot: discord.Client,
    announcement_id: int,
    guild_id: int | None = None,
) -> tuple[str, dict | None]:
    """Kirim pengumuman saat ini juga, tanpa menunggu jadwal.

    Status: `ok`, `tidak_ada`, `channel` (channel hilang/tanpa izin).
    Jadwal pengumuman **tidak** digeser — `next_run_at` tetap seperti semula.
    """
    cfg = announcements.get(int(announcement_id))
    if cfg is None or (guild_id is not None and cfg.get("guild_id") != int(guild_id)):
        return "tidak_ada", None

    channel = await resolve_channel(bot, cfg.get("channel_id"))
    if channel is None:
        return "channel", cfg

    try:
        await channel.send(
            embed=build_announcement_embed(
                cfg,
                guild=getattr(channel, "guild", None),
                channel=channel,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal kirim pengumuman %s sekarang: %s", announcement_id, sanitize_error_message(exc))
        return "channel", cfg

    cfg["last_sent_at"] = time.time()
    if cfg.get("kind") == "sekali":
        cfg["enabled"] = False
        cfg["next_run_at"] = 0.0
    await save_engagement_to_disk()
    return "ok", cfg


def remove_announcement(announcement_id: int, guild_id: int | None = None) -> bool:
    cfg = announcements.get(int(announcement_id))
    if cfg is None:
        return False
    if guild_id is not None and cfg.get("guild_id") != int(guild_id):
        return False
    announcements.pop(int(announcement_id), None)
    return True


def set_announcement_enabled(announcement_id: int, enabled: bool, *, tz_name: str | None = None) -> bool:
    cfg = announcements.get(int(announcement_id))
    if cfg is None:
        return False
    cfg["enabled"] = bool(enabled)
    if enabled and not float(cfg.get("next_run_at") or 0):
        cfg["next_run_at"] = compute_next_run(cfg, tz_name=tz_name)
    return True


def list_announcements(guild_id: int) -> list[dict]:
    items = [a for a in announcements.values() if a.get("guild_id") == int(guild_id)]
    return sorted(items, key=lambda a: float(a.get("next_run_at") or 0))


def describe_announcement(cfg: dict) -> str:
    """Ringkasan jadwal dalam Bahasa Indonesia."""
    clock = f"{int(cfg.get('hour') or 0):02d}:{int(cfg.get('minute') or 0):02d}"
    kind = cfg.get("kind")
    if kind == "mingguan":
        return f"setiap {_WEEKDAYS[int(cfg.get('weekday') or 0) % 7].capitalize()} {clock}"
    if kind == "sekali":
        return f"sekali pada {clock}"
    if kind == "interval":
        menit = min(
            MAX_INTERVAL_MINUTES,
            max(MIN_INTERVAL_MINUTES, _to_int(cfg.get("interval_minutes"), MIN_INTERVAL_MINUTES)),
        )
        if menit % 60 == 0:
            return f"setiap {menit // 60} jam"
        if menit > 60:
            return f"setiap {menit // 60} jam {menit % 60} menit"
        return f"setiap {menit} menit"
    return f"setiap hari {clock}"


def build_announcement_embed(
    cfg: dict,
    *,
    tz_label: str = "WIB",
    guild: discord.Guild | None = None,
    channel: discord.abc.GuildChannel | None = None,
) -> discord.Embed:
    """Embed pengumuman; variabel `{server.*}`/`{now}` dirender saat dikirim."""
    judul = message_template.render(cfg.get("title") or "", guild=guild, channel=channel)
    isi = message_template.render(str(cfg.get("content") or ""), guild=guild, channel=channel)
    embed = discord.Embed(
        title=(judul[:256] or "📢 Pengumuman"),
        description=isi[:4000],
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"Pengumuman terjadwal • {describe_announcement(cfg)} ({tz_label})")
    return embed


async def resolve_channel(bot: discord.Client, channel_id: int):
    """Cari channel dari cache; kalau tidak ada (mis. thread), ambil lewat API."""
    getter = getattr(bot, "get_channel", None)
    channel = getter(_to_int(channel_id)) if callable(getter) else None
    if channel is not None:
        return channel
    fetcher = getattr(bot, "fetch_channel", None)
    if callable(fetcher):
        try:
            return await fetcher(_to_int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
        except Exception:  # pragma: no cover - jaring aman
            return None
    return None


async def run_announcement_check(bot: discord.Client) -> int:
    """Mengirim pengumuman yang jadwalnya sudah tiba, lalu menghitung jadwal berikutnya."""
    now = time.time()
    sent = 0
    for aid, cfg in list(announcements.items()):
        if not cfg.get("enabled"):
            continue
        next_run = float(cfg.get("next_run_at") or 0)
        if not next_run or next_run > now:
            continue

        channel = await resolve_channel(bot, cfg.get("channel_id"))

        delivered = False
        if channel is not None:
            try:
                await channel.send(
                    embed=build_announcement_embed(
                        cfg,
                        guild=getattr(channel, "guild", None),
                        channel=channel,
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                delivered = True
                sent += 1
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Gagal kirim pengumuman %s: %s", aid, sanitize_error_message(exc))

        cfg["last_sent_at"] = now if delivered else 0.0
        if cfg.get("kind") == "sekali":
            cfg["enabled"] = False
            cfg["next_run_at"] = 0.0
        elif cfg.get("kind") == "interval":
            cfg["next_run_at"] = advance_interval_next_run(
                cfg.get("interval_minutes"), next_run, now=now
            )
        else:
            cfg["next_run_at"] = compute_next_run(cfg)

    if sent:
        await save_engagement_to_disk()
    return sent


# ==============================================================================
# PEMERIKSAAN TERPADU (dipanggil dari loop latar belakang main.py)
# ==============================================================================
async def run_engagement_check(bot: discord.Client) -> dict[str, int]:
    """Menjalankan seluruh pemeriksaan fitur engagement dalam satu putaran."""
    result = {
        "giveaway": await run_giveaway_check(bot),
        "ultah": await run_birthday_check(bot),
        "pengumuman": await run_announcement_check(bot),
    }
    return result


def handle_channel_delete(channel) -> bool:
    """Membersihkan konfigurasi engagement saat channel dihapus dari server."""
    cid = getattr(channel, "id", 0)
    changed = False
    if auto_reply_channels.pop(int(cid), None) is not None:
        changed = True
    gid = getattr(getattr(channel, "guild", None), "id", 0)
    if gid and (birthday_guilds.get(int(gid)) or {}).get("channel_id") == cid:
        birthday_guilds.pop(int(gid), None)
        changed = True
    for aid, cfg in list(announcements.items()):
        if _to_int(cfg.get("channel_id")) == cid:
            announcements.pop(aid, None)
            changed = True
    for mid, cfg in list(giveaways.items()):
        if _to_int(cfg.get("channel_id")) == cid:
            giveaways.pop(mid, None)
            changed = True
    return changed


def cleanup_engagement_runtime() -> int:
    """Membuang cache runtime agar RAM tetap kecil (dipanggil pembersih berkala)."""
    removed = 0
    now = time.time()
    for cid, cfg in list(auto_reply_channels.items()):
        if not cfg.get("enabled") and not cfg.get("rules"):
            auto_reply_channels.pop(cid, None)
            removed += 1
    for cid, stamp in list(_last_auto_reply_at.items()):
        if now - stamp > 86400:
            _last_auto_reply_at.pop(cid, None)
            removed += 1
    return removed
