"""Fitur Server All-in-One untuk AI Discord Chat.

Modul ini menampung empat fitur server yang berjalan hemat RAM di Wispbyte:

1. **Server Stats** (`/serverstats`) — kartu statistik server + Voice Channel penghitung otomatis.
2. **Auto Role** (`/autorole`) — pemberian role otomatis saat member bergabung.
3. **Fakta Unik Dunia** (`/fakta`) — rubrik 3–4 fakta dari berbagai negara setiap pukul 08:00.
4. **Anti-Phishing** (`/keamanan`) — deteksi & hapus link phishing tanpa API berbayar.

Seluruh konfigurasi disimpan atomik ke `data/server_features.json`.
"""

import asyncio
import json
import logging
import os
import re
import time
from urllib.parse import urlsplit

import discord

from community_agent import _call_gemini_agent, get_guild_settings
from config import (
    AUTOROLE_MAX_ROLES,
    BOT_TIMEZONE,
    DATA_DIR,
    ENABLE_PHISHING_GUARD,
    FACTS_DEFAULT_TIMES,
    FACTS_MAX_SLOTS,
    SERVER_FEATURES_FILE,
    SERVERSTATS_UPDATE_SEC,
)
from utils import get_realtime_time_context, sanitize_error_message

logger = logging.getLogger("gemini_bot.server_features")

# ==============================================================================
# PENYIMPANAN KONFIGURASI (RAM + data/server_features.json)
# ==============================================================================
serverstats_guilds: dict[int, dict] = {}
autorole_guilds: dict[int, dict] = {}
facts_guilds: dict[int, dict] = {}
security_guilds: dict[int, dict] = {}

_features_lock = asyncio.Lock()


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_server_features_from_disk() -> tuple[int, int, int, int]:
    """Memuat konfigurasi Server Stats, Auto Role, Fakta Harian, & Anti-Phishing dari disk."""
    serverstats_guilds.clear()
    autorole_guilds.clear()
    facts_guilds.clear()
    security_guilds.clear()

    if not SERVER_FEATURES_FILE.exists():
        return 0, 0, 0, 0

    try:
        raw = json.loads(SERVER_FEATURES_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - I/O rusak
        logger.warning("Gagal memuat %s: %s", SERVER_FEATURES_FILE, exc)
        return 0, 0, 0, 0

    _muat_serverstats(raw)

    _muat_autorole(raw)

    _muat_facts(raw)

    _muat_security(raw)

    return len(serverstats_guilds), len(autorole_guilds), len(facts_guilds), len(security_guilds)


def _entri_aman(raw: dict, kunci: str):
    """Iterasi `(k, v)` untuk `raw[kunci]`, aman bila nilainya bukan dict.

    Lihat catatan di `economy._entri`: data JSON tidak bisa dipercaya tipenya.
    """
    bagian = raw.get(kunci) if isinstance(raw, dict) else None
    return bagian.items() if isinstance(bagian, dict) else ()


def _muat_serverstats(raw: dict) -> None:
    """Isi serverstats_guilds dari data mentah."""
    for gid_str, data in _entri_aman(raw, "serverstats"):
        if not isinstance(data, dict):
            continue
        try:
            if not data.get("enabled", True):
                continue
            serverstats_guilds[int(gid_str)] = {
                "enabled": True,
                "category_id": _to_int(data.get("category_id")) or None,
                "category_name": str(data.get("category_name") or STATS_CATEGORY_NAME)[:100],
                "channel_type": str(data.get("channel_type") or "voice")
                if str(data.get("channel_type") or "voice") in STATS_CHANNEL_TYPES
                else "voice",
                "channels": {str(k): _to_int(v) for k, v in (data.get("channels") or {}).items()},
                "emojis": {
                    str(k): str(v)[:8]
                    for k, v in (data.get("emojis") or {}).items()
                    if str(k) in {key for key, _, _ in STATS_CHANNEL_SPECS}
                },
                "last_update_at": float(data.get("last_update_at") or 0.0),
            }
        except (TypeError, ValueError):
            continue


def _muat_autorole(raw: dict) -> None:
    """Isi autorole_guilds dari data mentah."""
    for gid_str, data in _entri_aman(raw, "autorole"):
        if not isinstance(data, dict):
            continue
        try:
            if not data.get("enabled", True):
                continue
            roles = [
                _to_int(r)
                for r in (data.get("role_ids") or [])[:AUTOROLE_MAX_ROLES]
                if _to_int(r)
            ]
            if not roles:
                continue
            autorole_guilds[int(gid_str)] = {
                "enabled": True,
                "role_ids": roles,
                "include_bots": bool(data.get("include_bots", False)),
            }
        except (TypeError, ValueError):
            continue


def _muat_facts(raw: dict) -> None:
    """Isi facts_guilds dari data mentah."""
    for gid_str, data in _entri_aman(raw, "facts"):
        if not isinstance(data, dict):
            continue
        try:
            if not data.get("enabled", True):
                continue
            facts_guilds[int(gid_str)] = _parse_facts_guild_config(data)
        except (TypeError, ValueError):
            continue


def _muat_security(raw: dict) -> None:
    """Isi security_guilds dari data mentah."""
    for gid_str, data in _entri_aman(raw, "security"):
        if not isinstance(data, dict):
            continue
        try:
            action = str(data.get("action") or "hapus_peringat")
            if action not in PHISHING_ACTIONS:
                action = "hapus_peringat"
            security_guilds[int(gid_str)] = {
                "enabled": bool(data.get("enabled", True)),
                "action": action,
                "log_channel_id": _to_int(data.get("log_channel_id")) or None,
                "channel_ids": [_to_int(c) for c in (data.get("channel_ids") or []) if _to_int(c)],
                "strict": bool(data.get("strict", False)),
                "blocked": _to_int(data.get("blocked")),
            }
        except (TypeError, ValueError):
            continue


def _parse_facts_guild_config(data: dict) -> dict:
    """Normalisasi konfigurasi Fakta Unik Dunia, termasuk migrasi format lama (hour/minute tunggal)."""
    raw_times = data.get("times")
    if raw_times:
        times = _normalize_times(raw_times)
    else:
        legacy_hour = max(0, min(23, _to_int(data.get("hour"), 8)))
        legacy_minute = max(0, min(59, _to_int(data.get("minute"), 0)))
        times = [f"{legacy_hour:02d}:{legacy_minute:02d}"]

    sent_raw = data.get("sent_slots")
    sent_slots: dict[str, list[str]] = {}
    if isinstance(sent_raw, dict):
        for day, slots in sent_raw.items():
            day_key = str(day)[:10]
            sent_slots[day_key] = [s for s in _normalize_times(slots) if s in times]
    else:
        # Migrasi: konfigurasi lama hanya menyimpan `last_sent_date` tanpa detail slot.
        legacy_date = str(data.get("last_sent_date") or "")
        if legacy_date and len(times) == 1:
            sent_slots[legacy_date[:10]] = [times[0]]

    sent_slots = {k: v for k, v in sent_slots.items() if v}
    return {
        "enabled": True,
        "channel_id": _to_int(data.get("channel_id")),
        "times": times,
        "sent_slots": dict(sorted(sent_slots.items())[-2:]),
        "recent_facts": [str(x) for x in (data.get("recent_facts") or [])[-16:]],
    }


async def save_server_features_to_disk() -> None:
    """Menyimpan seluruh konfigurasi fitur server secara atomik."""
    async with _features_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "serverstats": {str(k): v for k, v in serverstats_guilds.items()},
                "autorole": {str(k): v for k, v in autorole_guilds.items()},
                "facts": {str(k): v for k, v in facts_guilds.items()},
                "security": {str(k): v for k, v in security_guilds.items()},
            }
            tmp_file = SERVER_FEATURES_FILE.with_suffix(".json.tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, SERVER_FEATURES_FILE)
        except Exception:
            logger.exception("Gagal menyimpan server_features.json")


def format_number(value: int | None) -> str:
    """Format angka gaya Indonesia: 12345 -> 12.345."""
    if value is None:
        return "—"
    return f"{max(0, int(value)):,}".replace(",", ".")


# ==============================================================================
# 1. SERVER STATS (/serverstats)
# ==============================================================================
STATS_CHANNEL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("members", "👥", "Total Member"),
    ("humans", "🙋", "Manusia"),
    ("bots", "🤖", "Bot"),
    ("online", "🟢", "Online"),
    ("boosts", "💎", "Boost"),
    ("tickets", "🎫", "Tiket Terbuka"),
    ("social", "🔔", "Langganan Sosial"),
)


def hitung_statistik(guild, *, presence_count: int | None = None) -> dict[str, int | None]:
    """Nilai semua channel statistik (dipakai counter & tes) — 0 kuota AI.

    `tickets` = tiket yang belum ditutup, `social` = langganan notifikasi sosial
    (YouTube/Twitch/TikTok/Reddit/RSS). Keduanya dibaca dari state di memori.
    """
    members = list(getattr(guild, "members", []) or [])
    total_members = int(getattr(guild, "member_count", 0) or 0)
    bots = sum(1 for m in members if getattr(m, "bot", False))
    humans = max(0, total_members - bots) if members else None
    boost_count = int(getattr(guild, "premium_subscription_count", 0) or 0)

    gid = int(getattr(guild, "id", 0) or 0)
    tiket_terbuka = 0
    try:
        import tickets as tickets_mod

        tiket_terbuka = tickets_mod.count_open(gid)
    except Exception:  # pragma: no cover - jaring aman
        tiket_terbuka = 0

    langganan = 0
    try:
        import social_notify

        langganan = len(social_notify.get_subscriptions(gid))
    except Exception:  # pragma: no cover - jaring aman
        langganan = 0

    return {
        "members": total_members,
        "humans": humans,
        "bots": bots,
        "online": presence_count,
        "boosts": boost_count,
        "tickets": tiket_terbuka,
        "social": langganan,
    }

STATS_CATEGORY_NAME = "📊 Statistik Server"

# Jenis channel untuk counter. Ikon di kiri nama channel ditentukan oleh TIPE ini
# (bukan oleh bot): voice = 🔊, text = #, announcement = 📢, stage = 🎤.
STATS_CHANNEL_TYPES: dict[str, dict] = {
    "voice": {"label": "Voice channel (ikon 🔊)", "emoji": "🔊"},
    "text": {"label": "Text channel (ikon #)", "emoji": "#️⃣"},
    "news": {"label": "Announcement channel (ikon 📢)", "emoji": "📢"},
    "stage": {"label": "Stage channel (ikon 🎤)", "emoji": "🎤"},
}


def set_serverstats_config(guild_id: int, *, enabled: bool) -> dict | None:
    """Mengaktifkan / menonaktifkan pembaruan otomatis Voice Channel statistik server."""
    if not enabled:
        serverstats_guilds.pop(guild_id, None)
        return None

    existing = serverstats_guilds.get(guild_id) or {}
    serverstats_guilds[guild_id] = {
        "enabled": True,
        "category_id": existing.get("category_id"),
        "category_name": str(existing.get("category_name") or STATS_CATEGORY_NAME),
        "channel_type": str(existing.get("channel_type") or "voice"),
        "channels": dict(existing.get("channels") or {}),
        "emojis": dict(existing.get("emojis") or {}),
        "last_update_at": float(existing.get("last_update_at") or 0.0),
    }
    return serverstats_guilds[guild_id]


def default_stats_emojis() -> dict[str, str]:
    """Ikon bawaan tiap channel statistik (dari `STATS_CHANNEL_SPECS`)."""
    return {key: emoji for key, emoji, _ in STATS_CHANNEL_SPECS}


def stats_emojis(guild_id: int) -> dict[str, str]:
    """Ikon channel statistik milik server (default bila belum dikustomisasi)."""
    base = default_stats_emojis()
    cfg = serverstats_guilds.get(int(guild_id)) or {}
    base.update({k: v for k, v in (cfg.get("emojis") or {}).items() if k in base})
    return base


def set_serverstats_emojis(guild_id: int, mapping: dict[str, str | None]) -> dict[str, str]:
    """Mengubah ikon (emoji) channel statistik. Nilai kosong/`-` = tanpa ikon."""
    cfg = serverstats_guilds.get(int(guild_id))
    if cfg is None:
        cfg = set_serverstats_config(int(guild_id), enabled=True)
    stored = dict(cfg.get("emojis") or {})
    valid = {key for key, _, _ in STATS_CHANNEL_SPECS}
    for key, value in mapping.items():
        if key not in valid or value is None:
            continue
        text = str(value).strip()
        if text in {"-", "tanpa", "none", "kosong"}:
            text = ""
        stored[key] = text[:8]
    cfg["emojis"] = stored
    return stats_emojis(int(guild_id))


def reset_serverstats_appearance(guild_id: int) -> None:
    """Mengembalikan ikon & nama kategori statistik ke bawaan bot."""
    cfg = serverstats_guilds.get(int(guild_id))
    if cfg is None:
        return
    cfg["emojis"] = {}
    cfg["category_name"] = STATS_CATEGORY_NAME


def set_serverstats_category_name(guild_id: int, name: str | None) -> str:
    """Mengubah nama kategori channel statistik (boleh tanpa emoji)."""
    cfg = serverstats_guilds.get(int(guild_id))
    if cfg is None:
        cfg = set_serverstats_config(int(guild_id), enabled=True)
    text = str(name).strip()[:100] if name else STATS_CATEGORY_NAME
    if text in {"-", "tanpa", "none", "kosong"}:
        text = "Statistik Server"
    cfg["category_name"] = text
    return text


def stats_channel_type(guild_id: int) -> str:
    """Jenis channel counter milik server (`voice`/`text`/`news`/`stage`)."""
    cfg = serverstats_guilds.get(int(guild_id)) or {}
    kind = str(cfg.get("channel_type") or "voice")
    return kind if kind in STATS_CHANNEL_TYPES else "voice"


def set_serverstats_channel_type(guild_id: int, kind: str) -> str:
    """Mengubah jenis channel counter (mengubah ikon di kiri nama channel)."""
    chosen = str(kind or "voice").strip().lower()
    if chosen not in STATS_CHANNEL_TYPES:
        chosen = "voice"
    cfg = serverstats_guilds.get(int(guild_id))
    if cfg is None:
        cfg = set_serverstats_config(int(guild_id), enabled=True)
    # ID channel lama sengaja dipertahankan: saat update berikutnya channel bertipe
    # berbeda itu dihapus lalu diganti channel baru (tidak menyisakan counter ganda).
    cfg["channel_type"] = chosen
    return chosen


def _stats_channel_is_type(channel, kind: str) -> bool:
    """True bila channel yang ada sudah memiliki tipe yang diinginkan."""
    if channel is None:
        return False
    mapping = {
        "voice": discord.VoiceChannel,
        "text": discord.TextChannel,
        "news": discord.TextChannel,     # announcement = TextChannel(news=True)
        "stage": discord.StageChannel,
    }
    expected = mapping.get(kind)
    if expected is None or not isinstance(channel, expected):
        return False
    if kind == "news":
        return bool(getattr(channel, "is_news", lambda: False)())
    if kind == "text":
        return not bool(getattr(channel, "is_news", lambda: False)())
    return True


def _stats_overwrites(guild: discord.Guild, kind: str) -> dict:
    """Izin aman per jenis channel: warga bisa melihat, tidak bisa mengganggu."""
    if kind in ("voice", "stage"):
        return {guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
    return {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            add_reactions=False,
        )
    }


async def _create_stats_channel(
    guild: discord.Guild,
    kind: str,
    name: str,
    category,
    overwrites: dict,
):
    """Membuat satu channel counter sesuai tipe; announcement mundur ke teks bila ditolak."""
    reason = "Server Stats otomatis"
    if kind == "voice":
        return await guild.create_voice_channel(name, category=category, overwrites=overwrites, reason=reason)
    if kind == "stage":
        try:
            return await guild.create_stage_channel(
                name, category=category, overwrites=overwrites, reason=reason
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return await guild.create_voice_channel(
                name, category=category, overwrites=overwrites, reason=reason
            )
    if kind == "news":
        try:
            return await guild.create_news_channel(
                name, category=category, overwrites=overwrites, reason=reason
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return await guild.create_text_channel(
                name, category=category, overwrites=overwrites, reason=reason
            )
    return await guild.create_text_channel(name, category=category, overwrites=overwrites, reason=reason)


def _count_channel_types(guild: discord.Guild) -> dict[str, int]:
    counts = {"text": 0, "voice": 0, "forum": 0, "category": 0, "stage": 0}
    for channel in getattr(guild, "channels", []) or []:
        ctype = getattr(channel, "type", None)
        if ctype in (discord.ChannelType.text, discord.ChannelType.news):
            counts["text"] += 1
        elif ctype == discord.ChannelType.voice:
            counts["voice"] += 1
        elif ctype == discord.ChannelType.forum:
            counts["forum"] += 1
        elif ctype == discord.ChannelType.category:
            counts["category"] += 1
        elif ctype == discord.ChannelType.stage_voice:
            counts["stage"] += 1
    return counts


def _hitung_statistik_server(guild, presence_count: int | None) -> dict:
    """Kumpulkan semua angka statistik yang dipakai kartu server."""
    members = list(getattr(guild, "members", []) or [])
    total_members = int(getattr(guild, "member_count", 0) or len(members) or 0)
    bots = sum(1 for m in members if getattr(m, "bot", False)) if members else 0
    humans = max(0, total_members - bots) if members else None

    if presence_count is None:
        presence_count = getattr(guild, "approximate_presence_count", None)

    counts = _count_channel_types(guild)
    roles = len(getattr(guild, "roles", []) or [])
    emojis = len(getattr(guild, "emojis", []) or [])
    stickers = len(getattr(guild, "stickers", []) or [])
    boost_count = int(getattr(guild, "premium_subscription_count", 0) or 0)
    boost_tier = int(getattr(guild, "premium_tier", 0) or 0)

    created_at = getattr(guild, "created_at", None)
    created_txt = (
        discord.utils.format_dt(created_at, "D") if created_at else "Tidak diketahui"
    )
    owner = getattr(guild, "owner", None)
    owner_txt = str(owner) if owner else "Tidak diketahui"
    verify_raw = getattr(guild, "verification_level", None)
    verify_level = str(getattr(verify_raw, "name", None) or verify_raw or "Tidak diketahui").replace("_", " ").title()
    return {
        "members": members,
        "total_members": total_members,
        "bots": bots,
        "humans": humans,
        "presence_count": presence_count,
        "counts": counts,
        "roles": roles,
        "emojis": emojis,
        "stickers": stickers,
        "boost_count": boost_count,
        "boost_tier": boost_tier,
        "created_txt": created_txt,
        "owner_txt": owner_txt,
        "verify_level": verify_level,
    }


def _hitung_aktivitas_fitur(gid: int) -> tuple[int, int]:
    """Tiket terbuka & jumlah langganan sosial; `0` bila modulnya gagal."""
    try:
        import tickets as tickets_mod

        tiket_terbuka = tickets_mod.count_open(gid)
    except Exception:  # pragma: no cover - jaring aman
        tiket_terbuka = 0
    try:
        import social_notify

        langganan_sosial = len(social_notify.get_subscriptions(gid))
    except Exception:  # pragma: no cover - jaring aman
        langganan_sosial = 0
    return tiket_terbuka, langganan_sosial


def _tambah_field_utama(embed: discord.Embed, stat: dict) -> None:
    """Empat field pertama: anggota, aktivitas, kanal, dan lainnya."""
    total_members = stat["total_members"]
    humans = stat["humans"]
    bots = stat["bots"]
    presence_count = stat["presence_count"]
    counts = stat["counts"]
    roles = stat["roles"]
    emojis = stat["emojis"]
    stickers = stat["stickers"]
    boost_count = stat["boost_count"]
    boost_tier = stat["boost_tier"]
    verify_level = stat["verify_level"]
    embed.add_field(
        name="👥 Anggota",
        value=(
            f"• **Total:** `{format_number(total_members)}`\n"
            f"• **Manusia:** `{format_number(humans)}`\n"
            f"• **Bot:** `{format_number(bots)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="🟢 Aktivitas",
        value=(
            f"• **Online (perkiraan):** `{format_number(presence_count)}`\n"
            f"• **Boost:** `{format_number(boost_count)}` (Level `{boost_tier}`)\n"
            f"• **Verifikasi:** `{verify_level}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="💬 Kanal",
        value=(
            f"• **Teks:** `{format_number(counts['text'])}`\n"
            f"• **Suara:** `{format_number(counts['voice'])}`\n"
            f"• **Forum:** `{format_number(counts['forum'])}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="🎭 Lainnya",
        value=(
            f"• **Role:** `{format_number(roles)}`\n"
            f"• **Emoji:** `{format_number(emojis)}`\n"
            f"• **Stiker:** `{format_number(stickers)}`"
        ),
        inline=True,
    )


def _tambah_field_fitur(
    embed: discord.Embed, stat: dict, tiket_terbuka: int, langganan_sosial: int
) -> None:
    """Dua field terakhir: aktivitas fitur dan informasi server."""
    created_txt = stat["created_txt"]
    owner_txt = stat["owner_txt"]
    embed.add_field(
        name="📈 Aktivitas Fitur",
        value=(
            f"• **Tiket terbuka:** `{format_number(tiket_terbuka)}`\n"
            f"• **Langganan sosial:** `{format_number(langganan_sosial)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="📅 Informasi Server",
        value=(
            f"• **Dibuat:** {created_txt}\n"
            f"• **Pemilik:** {owner_txt}"
        ),
        inline=True,
    )


def build_serverstats_embed(
    guild: discord.Guild,
    *,
    presence_count: int | None = None,
) -> discord.Embed:
    """Menyusun kartu statistik server yang cantik & informatif (tanpa API berbayar)."""
    stat = _hitung_statistik_server(guild, presence_count)

    embed = discord.Embed(
        title=f"📊 Statistik Server — {getattr(guild, 'name', 'Server')}",
        description=(
            getattr(guild, "description", None)
            or "_Ringkasan lengkap kondisi server saat ini._"
        ),
        color=discord.Color.brand_green(),
        timestamp=discord.utils.utcnow(),
    )

    _tambah_field_utama(embed, stat)
    gid = int(getattr(guild, "id", 0) or 0)

    tiket_terbuka, langganan_sosial = _hitung_aktivitas_fitur(gid)

    _tambah_field_fitur(embed, stat, tiket_terbuka, langganan_sosial)

    icon = getattr(guild, "icon", None)
    if icon:
        embed.set_thumbnail(url=icon.url if hasattr(icon, "url") else str(icon))
    embed.set_footer(text="Statistik real-time • diperbarui otomatis")
    return embed


def _stats_channel_name(emoji: str, label: str, value: str) -> str:
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}{label}: {value}"[:100]


async def _ambil_presence_count(guild: discord.Guild, bot, presence_count):
    """Jumlah member online; ambil ulang lewat API bila belum tersedia."""
    if bot is not None and presence_count is None:
        try:
            fresh = await bot.fetch_guild(guild.id, with_counts=True)
            presence_count = getattr(fresh, "approximate_presence_count", None)
        except (discord.HTTPException, AttributeError):
            presence_count = None

    return presence_count


def _nilai_statistik(angka: dict) -> dict:
    """Ubah angka statistik jadi label siap tampil di nama channel."""
    return {
        "members": format_number(angka["members"]),
        "humans": format_number(angka["humans"]),
        "bots": format_number(angka["bots"]),
        "online": format_number(angka["online"]),
        "boosts": format_number(angka["boosts"]),
        "tickets": format_number(angka["tickets"]),
        "social": format_number(angka["social"]),
    }


async def _pastikan_kategori_stats(
    guild: discord.Guild, cfg: dict
) -> tuple[discord.CategoryChannel | None, int, bool]:
    """Pastikan kategori Server Stats ada dan namanya sesuai konfigurasi.

    Mengembalikan `(kategori, jumlah perubahan, boleh lanjut)`.
    """
    category = None

    cat_id = cfg.get("category_id")

    if cat_id:
        found = guild.get_channel(int(cat_id))
        if isinstance(found, discord.CategoryChannel):
            category = found


    changed = 0

    desired_category = str(cfg.get("category_name") or STATS_CATEGORY_NAME)[:100]

    if category is None:
        try:
            category = await guild.create_category(desired_category, reason="Server Stats otomatis")
            cfg["category_id"] = category.id
        except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
            logger.warning("Gagal membuat kategori Server Stats: %s", sanitize_error_message(exc))
            return None, 0, False
    elif str(getattr(category, "name", "")) != desired_category:
        try:
            await category.edit(name=desired_category, reason="Ganti nama kategori Server Stats")
            changed += 1
        except (discord.Forbidden, discord.HTTPException):
            pass


    return category, changed, True


async def _sinkron_satu_channel(
    guild: discord.Guild,
    key: str,
    label: str,
    desired: str,
    kind: int,
    category,
    overwrites: dict,
    channels_cfg: dict,
) -> tuple[int, bool]:
    """Selaraskan satu channel penghitung; `(jumlah perubahan, boleh lanjut)`."""
    changed = 0
    existing = guild.get_channel(int(channels_cfg[key])) if channels_cfg.get(key) else None

    if not _stats_channel_is_type(existing, kind):
        # Tipe channel berubah (mis. voice → text): hapus counter lama milik bot,
        # lalu cari channel sejenis yang sudah ada agar tidak duplikat saat restart.
        if existing is not None:
            try:
                await existing.delete(reason="Server Stats: ganti jenis channel")
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        existing = None
        for ch in getattr(guild, "channels", []) or []:
            # Cocokkan lewat label ("Total Member:") + tipe yang sama
            if f"{label}:" in str(getattr(ch, "name", "")) and _stats_channel_is_type(ch, kind):
                existing = ch
                break


    try:
        if existing is None:
            created = await _create_stats_channel(guild, kind, desired, category, overwrites)
            channels_cfg[key] = created.id
            changed += 1
            return changed, True

        if existing.name != desired:
            await existing.edit(name=desired, reason="Perbarui Server Stats")
            changed += 1
        channels_cfg[key] = existing.id
    except discord.HTTPException as exc:
        logger.warning("Gagal memperbarui channel statistik %s: %s", key, sanitize_error_message(exc))
    except AttributeError:
        return changed, False

    return changed, True


async def _sinkron_semua_channel(
    guild: discord.Guild, cfg: dict, values: dict, kind: int, overwrites: dict, category
) -> tuple[int, bool]:
    """Selaraskan semua channel statistik; `(jumlah perubahan, boleh lanjut)`."""
    channels_cfg: dict = cfg.setdefault("channels", {})
    emojis = stats_emojis(guild.id)
    total = 0
    for key, _default_emoji, label in STATS_CHANNEL_SPECS:
        emoji = emojis.get(key, _default_emoji)
        desired = _stats_channel_name(emoji, label, values[key])
        tambahan, lanjut = await _sinkron_satu_channel(
            guild, key, label, desired, kind, category, overwrites, channels_cfg
        )
        total += tambahan
        if not lanjut:
            return total, False
    return total, True


async def update_serverstats_channels(
    guild: discord.Guild,
    *,
    force: bool = False,
    bot: discord.Client | None = None,
) -> int:
    """Membuat/menyegarkan Voice Channel penghitung statistik server.

    Discord membatasi **2 rename / 10 menit per channel**, sehingga update default
    hanya dijalankan setiap `SERVERSTATS_UPDATE_SEC` (10 menit) agar 100% aman.
    """
    cfg = serverstats_guilds.get(getattr(guild, "id", 0))

    if not cfg or not cfg.get("enabled"):
        return 0


    now = time.time()

    if not force and now - float(cfg.get("last_update_at") or 0.0) < SERVERSTATS_UPDATE_SEC:
        return 0


    presence_count = await _ambil_presence_count(
        guild, bot, getattr(guild, "approximate_presence_count", None)
    )

    angka = hitung_statistik(guild, presence_count=presence_count)

    values = _nilai_statistik(angka)

    category, changed, lanjut = await _pastikan_kategori_stats(guild, cfg)
    if not lanjut:
        return 0

    kind = stats_channel_type(guild.id)

    overwrites = _stats_overwrites(guild, kind)


    tambahan, lanjut = await _sinkron_semua_channel(
        guild, cfg, values, kind, overwrites, category
    )
    if not lanjut:
        return 0
    changed += tambahan

    cfg["last_update_at"] = now

    await save_server_features_to_disk()

    return changed


async def run_serverstats_check(bot: discord.Client) -> int:
    """Loop latar belakang: menyegarkan Voice Channel statistik seluruh server."""
    updated = 0
    for gid in list(serverstats_guilds.keys()):
        guild = bot.get_guild(gid)
        if guild is None:
            continue
        try:
            updated += await update_serverstats_channels(guild, bot=bot)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Server Stats guild %s gagal: %s", gid, sanitize_error_message(exc))
    return updated


# ==============================================================================
# 2. AUTO ROLE (/autorole)
# ==============================================================================
def set_autorole_config(guild_id: int, role_ids: list[int], *, enabled: bool = True) -> dict | None:
    """Mengatur role yang otomatis diberikan saat member baru bergabung."""
    cleaned = [int(r) for r in role_ids if _to_int(r)][:AUTOROLE_MAX_ROLES]
    if not enabled or not cleaned:
        autorole_guilds.pop(guild_id, None)
        return None

    autorole_guilds[guild_id] = {
        "enabled": True,
        "role_ids": cleaned,
        "include_bots": False,
    }
    return autorole_guilds[guild_id]


def get_autorole_role_ids(guild_id: int) -> list[int]:
    cfg = autorole_guilds.get(guild_id) or {}
    return list(cfg.get("role_ids") or []) if cfg.get("enabled") else []


def _is_assignable_role(role: object) -> bool:
    if role is None:
        return False
    if bool(getattr(role, "managed", False)):
        return False
    if bool(getattr(role, "is_default", lambda: False)()):
        return False
    return True


async def apply_autorole_to_member(member: object) -> list[str]:
    """Memberikan role otomatis ke satu member. Mengembalikan nama role yang berhasil diberikan."""
    guild = getattr(member, "guild", None)
    if guild is None or getattr(member, "bot", False):
        return []

    cfg = autorole_guilds.get(getattr(guild, "id", 0))
    if not cfg or not cfg.get("enabled"):
        return []

    applied: list[str] = []
    for role_id in cfg.get("role_ids") or []:
        role = guild.get_role(int(role_id))
        if not _is_assignable_role(role):
            continue
        if role in getattr(member, "roles", []):
            continue
        try:
            await member.add_roles(role, reason="Auto Role member baru")
            applied.append(str(getattr(role, "name", role_id)))
        except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
            logger.warning("Gagal memberikan Auto Role %s: %s", role_id, sanitize_error_message(exc))
    return applied


async def backfill_autoroles(guild: discord.Guild, *, limit: int = 150) -> tuple[int, int]:
    """Memberikan role otomatis ke member lama yang belum memilikinya (maks. `limit` member)."""
    cfg = autorole_guilds.get(getattr(guild, "id", 0))
    if not cfg or not cfg.get("enabled"):
        return 0, 0

    roles = [guild.get_role(int(r)) for r in cfg.get("role_ids") or []]
    roles = [r for r in roles if _is_assignable_role(r)]
    if not roles:
        return 0, 0

    changed = 0
    checked = 0
    async for member in guild.fetch_members(limit=limit):
        if getattr(member, "bot", False):
            continue
        checked += 1
        missing = [r for r in roles if r not in member.roles]
        if not missing:
            continue
        try:
            await member.add_roles(*missing, reason="Auto Role backfill")
            changed += 1
        except (discord.Forbidden, discord.HTTPException):
            break
        await asyncio.sleep(0.25)
    return changed, checked


# ==============================================================================
# 3. FAKTA UNIK DUNIA HARIAN MULTI-SLOT (/fakta)
# ==============================================================================
SLOT_VIBES: tuple[tuple[int, int, str, str], ...] = (
    (4, 10, "☀️ Pagi", "sapaan semangat pagi, temani warga sarapan & mulai aktivitas"),
    (10, 15, "🌤️ Siang", "sapaan siang santai, temani jam istirahat & makan siang"),
    (15, 18, "🌇 Sore", "sapaan sore, temani warga pulang aktivitas & ngopi sore"),
    (18, 24, "🌙 Malam", "sapaan malam, temani warga nongkrong & istirahat malam"),
    (0, 4, "🌌 Dini Hari", "sapaan dini hari untuk para begadang"),
)


def slot_to_minutes(value: object) -> int | None:
    """Mengubah slot jam fleksibel ('8', '08:00', '8.30', ' 20 : 00 ') menjadi total menit."""
    if isinstance(value, (int, float)):
        hour = int(value)
        return hour * 60 if 0 <= hour <= 23 else None

    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2})(?:\s*[:.]\s*(\d{1,2}))?", text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def minutes_to_slot(minutes: int) -> str:
    total = max(0, min(1439, int(minutes)))
    return f"{total // 60:02d}:{total % 60:02d}"


def _normalize_times(values: object) -> list[str]:
    """Merapikan daftar slot jam: unik, urut, & dibatasi `FACTS_MAX_SLOTS`."""
    raw_items: list[object]
    if isinstance(values, str):
        raw_items = [chunk for chunk in re.split(r"[,;|/\s]+", values) if chunk]
    elif isinstance(values, (list, tuple, set)):
        raw_items = list(values)
    else:
        raw_items = []

    found: list[str] = []
    for item in raw_items:
        minutes = slot_to_minutes(item)
        if minutes is None:
            continue
        slot = minutes_to_slot(minutes)
        if slot not in found:
            found.append(slot)

    return sorted(found)[:FACTS_MAX_SLOTS]


def parse_schedule_input(
    raw_value: str | None,
    *,
    default_times: list[str] | None = None,
) -> tuple[list[str] | None, str | None]:
    """Membaca input jadwal Admin yang fleksibel.

    Contoh yang diterima: `08:00,12:00,16:00,20:00`, `8,12,16,20`, `8.30 12.00 16.00`,
    `09:00; 15:00; 21:00`, `10:00 dan 22:00`.

    Mengembalikan `(times, None)` bila valid, `(None, pesan_error)` bila ada format salah,
    dan daftar default bila input kosong.
    """
    defaults = _normalize_times(default_times or FACTS_DEFAULT_TIMES)
    text = str(raw_value or "").strip()
    if not text:
        return (defaults or list(FACTS_DEFAULT_TIMES)), None

    normalized = re.sub(r"(?i)\s+dan\s+", ",", text)
    chunks = [chunk for chunk in re.split(r"[,;|/\s]+", normalized) if chunk.strip()]
    if not chunks:
        return (defaults or list(FACTS_DEFAULT_TIMES)), None

    parsed: list[str] = []
    invalid: list[str] = []
    for chunk in chunks:
        minutes = slot_to_minutes(chunk)
        if minutes is None:
            invalid.append(chunk.strip())
            continue
        slot = minutes_to_slot(minutes)
        if slot not in parsed:
            parsed.append(slot)

    if invalid:
        shown = ", ".join(f"`{item[:12]}`" for item in invalid[:5])
        return None, f"Format jam tidak dikenali: {shown}"
    if not parsed:
        return None, "Tidak ada jam valid yang bisa dibaca."
    if len(parsed) > FACTS_MAX_SLOTS:
        return None, f"Maksimal **{FACTS_MAX_SLOTS} slot** per hari (kamu mengirim {len(parsed)})."
    return sorted(parsed), None


def describe_slot(slot: str | None) -> str:
    """Label suasana waktu untuk sebuah slot (Pagi/Siang/Sore/Malam/Dini Hari)."""
    minutes = slot_to_minutes(slot)
    if minutes is None:
        return "🕒 Kapan Saja"
    hour = minutes // 60
    for start, end, label, _ in SLOT_VIBES:
        if start <= hour < end:
            return label
    return "🌙 Malam"


def slot_vibe_hint(slot: str | None) -> str:
    minutes = slot_to_minutes(slot)
    if minutes is None:
        return "netral, ramah, dan hangat"
    hour = minutes // 60
    for start, end, _, hint in SLOT_VIBES:
        if start <= hour < end:
            return hint
    return "netral, ramah, dan hangat"


def format_facts_schedule(times: list[str] | None) -> str:
    """Format daftar slot untuk ditampilkan di Discord: `08:00` • `12:00` • ..."""
    slots = _normalize_times(times or FACTS_DEFAULT_TIMES)
    return " • ".join(f"`{slot}`" for slot in slots) if slots else "_belum diatur_"


def next_facts_slot(times: list[str] | None, *, now_minutes: int) -> tuple[str, int] | None:
    """Mengembalikan `(slot_berikutnya, menit_tersisa)` dari jadwal hari ini."""
    slots = [slot_to_minutes(item) for item in _normalize_times(times or FACTS_DEFAULT_TIMES)]
    valid = sorted(item for item in slots if item is not None)
    if not valid:
        return None
    for minutes in valid:
        if minutes > now_minutes:
            return minutes_to_slot(minutes), minutes - now_minutes
    first = valid[0]
    return minutes_to_slot(first), (1440 - now_minutes) + first


def sent_slots_today(cfg: dict | None, iso_date: str) -> list[str]:
    """Daftar slot yang sudah terkirim pada tanggal tertentu (aman untuk data rusak)."""
    if not cfg:
        return []
    raw = cfg.get("sent_slots")
    if not isinstance(raw, dict):
        return []
    return [str(slot) for slot in (raw.get(iso_date) or []) if slot_to_minutes(slot) is not None]


FACTS_FALLBACK: tuple[str, ...] = (
    "🇯🇵 **Jepang** — Di Jepang ada kereta cepat Shinkansen yang rata-rata terlambatnya kurang dari satu menit per tahun.",
    "🇮🇸 **Islandia** — Hampir seluruh listrik Islandia berasal dari energi panas bumi dan air, bukan batu bara.",
    "🇧🇷 **Brasil** — Brasil memiliki lebih dari 3.000 jenis buah hutan Amazon, banyak yang belum punya nama resmi.",
    "🇪🇬 **Mesir** — Piramida Giza adalah satu-satunya dari Tujuh Keajaiban Dunia Kuno yang masih berdiri.",
    "🇮🇩 **Indonesia** — Indonesia punya lebih dari 700 bahasa daerah dan menjadi negara dengan bahasa terbanyak kedua di dunia.",
    "🇳🇱 **Belanda** — Belanda punya lebih banyak sepeda daripada jumlah penduduknya.",
    "🇰🇷 **Korea Selatan** — Di Korea Selatan ada tradisi 'Doljanchi', perayaan ulang tahun pertama bayi yang sangat meriah.",
    "🇲🇽 **Meksiko** — Cokelat pertama di dunia diolah oleh bangsa Maya dan Aztec sebagai minuman pahit bernama xocolatl.",
    "🇦🇺 **Australia** — Australia punya peternakan terbesar di dunia, Anna Creek Station, yang lebih luas dari negara Israel.",
    "🇳🇴 **Norwegia** — Di Norwegia ada matahari tengah malam, di mana matahari tidak terbenam selama berbulan-bulan di musim panas.",
)


def set_facts_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    times: list[str] | str | None = None,
) -> dict | None:
    """Mengatur jadwal multi-slot rubrik Fakta Unik Dunia.

    `times` menerima daftar slot (mis. `["08:00", "12:00"]`) maupun teks bebas
    (`"8,12,16,20"`). Bila `None`, jadwal lama dipertahankan (atau memakai default
    `08:00 • 12:00 • 16:00 • 20:00` untuk server baru).
    """
    if not enabled:
        facts_guilds.pop(guild_id, None)
        return None

    existing = facts_guilds.get(guild_id) or {}
    if times is None:
        chosen_times = _normalize_times(existing.get("times") or FACTS_DEFAULT_TIMES)
    else:
        parsed, error = parse_schedule_input(
            times if isinstance(times, str) else ",".join(str(t) for t in times)
        )
        if error or not parsed:
            return None
        chosen_times = parsed

    # Slot yang sudah terkirim hari ini tetap dipertahankan, tetapi dibuang bila jadwal berubah.
    kept_sent: dict[str, list[str]] = {}
    raw_sent = existing.get("sent_slots")
    if isinstance(raw_sent, dict):
        for day, slots in list(raw_sent.items())[-2:]:
            valid = [s for s in _normalize_times(slots) if s in chosen_times]
            if valid:
                kept_sent[str(day)[:10]] = valid

    facts_guilds[guild_id] = {
        "enabled": True,
        "channel_id": int(channel_id),
        "times": chosen_times,
        "sent_slots": kept_sent,
        "recent_facts": list(existing.get("recent_facts") or [])[-16:],
    }
    return facts_guilds[guild_id]


async def generate_daily_facts(
    guild_id: int,
    bot_display_name: str,
    *,
    count: int = 4,
    slot: str | None = None,
    http_session=None,
) -> tuple[str | None, str | None]:
    """Membuat 3–4 fakta unik dari berbagai negara memakai Gemini Free Tier."""
    guild_cfg = get_guild_settings(guild_id)
    agent_name = guild_cfg.get("nickname") or bot_display_name or "Teman"
    cfg = facts_guilds.get(guild_id) or {}
    recent = [str(x) for x in (cfg.get("recent_facts") or [])[-16:]]
    avoid_block = ""
    if recent:
        joined = " | ".join(f'"{r[:90]}"' for r in recent)
        avoid_block = (
            f"\nJANGAN mengulang fakta berikut yang sudah pernah dipakai: [{joined}]. "
            "Pilih negara & fakta yang benar-benar berbeda."
        )

    session_block = ""
    if slot:
        session_block = (
            f"\nSesi ini adalah **{describe_slot(slot)}** ({slot}). "
            f"Awali dengan satu sapaan singkat bernuansa {slot_vibe_hint(slot)}, lalu lanjut ke fakta.\n"
        )

    system_prompt = (
        f"Kamu adalah '{agent_name}', penulis rubrik **Fakta Unik Dunia** di sebuah server Discord Indonesia.\n"
        "Tulis dengan gaya santai, cerdas, dan membuat pembaca berkata 'wow, baru tahu!'.\n"
        "Seluruh tulisan WAJIB Bahasa Indonesia yang rapi dan enak dibaca."
    )
    user_prompt = (
        f"Buat tepat {count} fakta unik & benar dari {count} NEGARA BERBEDA di benua/region yang berbeda-beda "
        "(contoh: Asia Timur, Asia Tenggara, Eropa, Afrika, Amerika Latin, Timur Tengah, Oseania).\n"
        f"{session_block}\n"
        "ATURAN FORMAT (wajib dipatuhi):\n"
        f"1. Setiap fakta diawali emoji bendera negara + nama negara tebal, contoh: 🇯🇵 **Jepang** — fakta...\n"
        "2. Satu fakta 1–2 kalimat pendek, maksimal 220 karakter.\n"
        "3. Fakta harus spesifik, unik, dan tidak normatif (budaya, alam, sains, kuliner, sejarah, teknologi).\n"
        "4. Pisahkan setiap fakta dengan satu baris kosong.\n"
        "5. Tanpa judul, tanpa pengantar berlebihan, tanpa penutup, tanpa penomoran tambahan."
        f"{avoid_block}"
    )

    reply = await _call_gemini_agent(
        system_prompt,
        [{"role": "user", "parts": [{"text": user_prompt}]}],
        temperature=0.95,
        max_tokens=1400,
        thinking_level="minimal",
        has_media=False,
        http_session=http_session,
    )
    if reply:
        cleaned = reply.strip()
        if len(cleaned) >= 80:
            return cleaned[:3900], None
    return None, "Gagal membuat fakta (cek GEMINI_API_KEY atau kuota Free Tier)."


def build_facts_fallback(count: int = 4, *, slot: str | None = None) -> str:
    """Cadangan fakta statis agar rubrik tetap terkirim walau Gemini sedang gangguan.

    Pemilihan fakta dibedakan per slot (pagi/siang/sore/malam) agar tidak selalu sama.
    """
    day_index = int(time.time() // 86400)
    slot_minutes = slot_to_minutes(slot) or 0
    offset = day_index + (slot_minutes // 60) * 3
    picked = [FACTS_FALLBACK[(offset + i) % len(FACTS_FALLBACK)] for i in range(max(3, count))]
    return "\n\n".join(picked)


def build_facts_embed(
    guild_config: dict,
    content: str,
    *,
    slot: str | None = None,
    times: list[str] | None = None,
) -> discord.Embed:
    t_ctx = get_realtime_time_context(guild_config.get("timezone", BOT_TIMEZONE))
    slot_label = describe_slot(slot) if slot else ""
    title = f"🌍 Fakta Unik Dunia — {t_ctx['day_name']}, {t_ctx['date_str']}"
    if slot_label:
        title = f"🌍 Fakta Unik Dunia • {slot_label} — {t_ctx['day_name']}, {t_ctx['date_str']}"

    footer_bits = [f"Rubrik Fakta Harian • {t_ctx['clock']}"]
    if times:
        footer_bits.append("Jadwal: " + " / ".join(_normalize_times(times)))
    return discord.Embed(
        title=title[:256],
        description=content[:4050],
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    ).set_footer(text=" • ".join(footer_bits)[:2048])


async def run_facts_check(bot: discord.Client, *, http_session=None) -> int:
    """Loop latar belakang: mengirim rubrik Fakta Unik Dunia sesuai seluruh slot jadwal server.

    - Mengecek tiap menit; slot yang jamnya sudah lewat & belum terkirim hari ini langsung dikirim.
    - Bila bot sempat offline melewati beberapa slot, hanya **1 pesan** yang dikirim dan
      slot-slot yang terlewat ditandai selesai agar tidak membanjiri channel.
    """
    sent = 0
    for gid, cfg in list(facts_guilds.items()):
        if not cfg.get("enabled"):
            continue
        channel = bot.get_channel(int(cfg.get("channel_id") or 0))
        if channel is None:
            continue

        guild_cfg = get_guild_settings(gid)
        t_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))
        today = t_ctx["iso_date"]
        times = _normalize_times(cfg.get("times") or FACTS_DEFAULT_TIMES)
        already_sent = sent_slots_today(cfg, today)
        now_minutes = t_ctx["hour"] * 60 + t_ctx["minute"]

        due_slots = [
            slot
            for slot in times
            if (slot_to_minutes(slot) or 0) <= now_minutes and slot not in already_sent
        ]

        # Pangkas riwayat slot tanggal lama agar RAM & file JSON tetap kecil.
        cfg["sent_slots"] = {today: already_sent} if already_sent else {}
        if not due_slots:
            continue

        current_slot = due_slots[-1]
        bot_name = getattr(getattr(bot, "user", None), "display_name", None) or "Teman"
        content, err = await generate_daily_facts(
            gid, bot_name, slot=current_slot, http_session=http_session
        )
        if not content:
            logger.info("Fakta harian memakai cadangan statis: %s", err)
            content = build_facts_fallback(slot=current_slot)

        try:
            await channel.send(embed=build_facts_embed(guild_cfg, content, slot=current_slot, times=times))
            sent += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Gagal kirim Fakta Harian di %s: %s", gid, sanitize_error_message(exc))
            continue

        # Tandai seluruh slot yang sudah lewat agar tidak terjadi penumpukan pesan.
        cfg["sent_slots"] = {today: sorted(set(already_sent) | set(due_slots))}
        cfg["recent_facts"] = (list(cfg.get("recent_facts") or []) + [content[:400]])[-16:]
        await save_server_features_to_disk()
    return sent


# ==============================================================================
# 4. ANTI-PHISHING (/keamanan)
# ==============================================================================
PHISHING_ACTIONS: dict[str, str] = {
    "hapus_peringat": "Hapus link + beri peringatan ke pengirim",
    "hapus": "Hapus link saja (tanpa peringatan publik)",
    "peringatkan": "Peringatkan saja tanpa menghapus pesan",
}

HIGH_RISK_TLDS: frozenset[str] = frozenset({
    "tk", "ml", "ga", "cf", "gq", "zip", "mov", "cfd", "sbs", "cyou", "monster",
    "icu", "buzz", "click", "rest", "quest", "country", "gdn", "mom", "lol", "kim",
})

SUSPICIOUS_TLDS: frozenset[str] = frozenset({
    "top", "xyz", "online", "site", "website", "shop", "store", "live", "support",
    "work", "link", "club", "space", "fun", "pw", "cc", "ws", "su",
})

URL_SHORTENERS: frozenset[str] = frozenset({
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "is.gd", "shorturl.at",
    "rebrand.ly", "s.id", "gg.gg", "shorte.st", "adf.ly", "bl.ink", "ow.ly",
})

OFFICIAL_BRAND_DOMAINS: dict[str, tuple[str, ...]] = {
    "discord": ("discord.com", "discord.gg", "discordapp.com", "discordapp.net", "dis.gd", "discord.media", "discordstatus.com", "discord.new"),
    "steam": ("steampowered.com", "steamcommunity.com", "steamgames.com", "steamstatic.com", "steam.tv"),
    "roblox": ("roblox.com", "robloxlabs.com", "rbxcdn.com", "rblx.co"),
    "instagram": ("instagram.com", "instagr.am", "cdninstagram.com"),
    "facebook": ("facebook.com", "fb.com", "fb.me", "fb.watch", "messenger.com"),
    "whatsapp": ("whatsapp.com", "wa.me", "whatsapp.net"),
    "telegram": ("telegram.org", "t.me", "telegram.me"),
    "tiktok": ("tiktok.com", "tiktokv.com", "douyin.com"),
    "netflix": ("netflix.com", "nflxvideo.net"),
    "spotify": ("spotify.com", "spotify.link", "scdn.co"),
    "google": ("google.com", "gmail.com", "google.co.id", "googleapis.com", "g.co", "youtube.com", "youtu.be", "goo.gl"),
    "microsoft": ("microsoft.com", "live.com", "office.com", "outlook.com", "bing.com", "microsoftonline.com", "sharepoint.com", "xbox.com"),
    "github": ("github.com", "github.io", "githubusercontent.com"),
    "paypal": ("paypal.com", "paypal.me", "paypalobjects.com"),
    "binance": ("binance.com", "binance.us", "bnbstatic.com"),
    "tokopedia": ("tokopedia.com", "tokopedia.link", "tokocrypto.com"),
    "shopee": ("shopee.co.id", "shopee.com", "shp.ee", "shopee.co.th"),
    "dana": ("dana.id",),
    "ovo": ("ovo.id",),
    "gopay": ("gopay.co.id", "gojek.com"),
    "bca": ("bca.co.id", "klikbca.com"),
    "mandiri": ("bankmandiri.co.id", "mandiri.co.id"),
    "bri": ("bri.co.id",),
    "bni": ("bni.co.id",),
    "apple": ("apple.com", "icloud.com"),
    "amazon": ("amazon.com", "amazon.co.id", "amzn.to"),
    "linkedin": ("linkedin.com", "lnkd.in"),
    "twitter": ("twitter.com", "x.com", "t.co"),
    "twitch": ("twitch.tv", "ttvnw.net"),
}

PHISHING_KEYWORDS: tuple[str, ...] = (
    "nitro", "gift", "free", "airdrop", "claim", "reward", "verify",
    "verifikasi", "login", "wallet", "seed-phrase", "seedphrase", "bonus", "hadiah",
    "giveaway", "steamcommunlty", "token", "unlock", "recovery", "pulsa", "saldo",
    "refund", "klaim", "menang", "undian", "helpdesk", "secure",
)

KNOWN_BAD_HOSTS: frozenset[str] = frozenset({
    "discord-nitro.com", "discord-nitro.net", "discordgift.com", "discord-gift.com",
    "discordnitro.com", "nitro-discord.com", "free-nitro.com", "steamcommunlty.com",
    "steamcomunity.com", "steamcommunity.ru", "csgo-skins.net", "csgofast.com",
    "robloxgift.com", "roblox-free.com", "free-robux.com", "rbx-gift.com",
    "claim-nitrogift.com", "discord-airdrop.com", "binance-airdrop.com",
})

_URL_FIND_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>()\[\]{}\"'`]+")

_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_PUNYCODE_RE = re.compile(r"(^|\.)xn--", re.IGNORECASE)


def set_security_config(
    guild_id: int,
    *,
    enabled: bool,
    action: str | None = None,
    log_channel_id: int | None = None,
    channel_ids: list[int] | None = None,
    strict: bool | None = None,
) -> dict | None:
    """Mengatur proteksi Anti-Phishing server."""
    if not enabled:
        security_guilds.pop(guild_id, None)
        return None

    existing = security_guilds.get(guild_id) or {}
    chosen_action = action if action in PHISHING_ACTIONS else existing.get("action", "hapus_peringat")
    security_guilds[guild_id] = {
        "enabled": True,
        "action": chosen_action,
        "log_channel_id": int(log_channel_id) if log_channel_id else existing.get("log_channel_id"),
        "channel_ids": [int(c) for c in (channel_ids if channel_ids is not None else existing.get("channel_ids") or [])],
        "strict": bool(strict if strict is not None else existing.get("strict", False)),
        "blocked": int(existing.get("blocked") or 0),
    }
    return security_guilds[guild_id]


def extract_links(text: str) -> list[str]:
    """Mengekstrak seluruh link dari teks pesan (tanpa batas seperti fitur ringkas)."""
    links: list[str] = []
    for match in _URL_FIND_RE.findall(text or ""):
        cleaned = match.rstrip(".,;:!?\"')]>}")
        if cleaned and cleaned not in links:
            links.append(cleaned)
    return links[:10]


# Brand pendek (<= 4 huruf) hanya dicocokkan sebagai potongan utuh agar tidak salah tuduh
# (contoh: "bri" jangan sampai menandai "bridge.com").
_SHORT_BRAND_TOKENS = frozenset({"dana", "ovo", "bca", "bri", "bni"})


def _brand_hits(host: str) -> list[str]:
    host_lower = host.lower()
    tokens = {t for t in re.split(r"[.\-_]", host_lower) if t}
    hits: list[str] = []
    for brand in OFFICIAL_BRAND_DOMAINS:
        if brand in _SHORT_BRAND_TOKENS:
            if brand in tokens:
                hits.append(brand)
        elif brand in host_lower:
            hits.append(brand)
    return hits


def _is_official_domain(host: str, brand: str) -> bool:
    for domain in OFFICIAL_BRAND_DOMAINS.get(brand, ()):  # type: ignore[arg-type]
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _skor_sinyal_domain(
    host: str, bare_host: str, tld: str, impersonated, parts
) -> tuple[int, list[str]]:
    """Poin risiko dari bentuk domain itu sendiri."""
    reasons: list[str] = []
    score = 0
    if bare_host in KNOWN_BAD_HOSTS or host in KNOWN_BAD_HOSTS:
        score = 100
        reasons.append("Domain ada di daftar hitam phishing")
    if _PUNYCODE_RE.search(host):
        score += 55
        reasons.append("Domain memakai karakter punycode (`xn--`) untuk menyamarkan brand")
    if _IPV4_RE.match(host):
        score += 40
        reasons.append("Link memakai alamat IP langsung, bukan nama domain resmi")
    if impersonated:
        score += 60
        reasons.append(f"Meniru brand **{impersonated.title()}** tetapi bukan domain resmi")
    if tld in HIGH_RISK_TLDS:
        score += 40
        reasons.append(f"Akronim domain `.{tld}` sangat sering dipakai kampanye phishing")
    elif tld in SUSPICIOUS_TLDS:
        score += 18
        reasons.append(f"Akronim domain `.{tld}` perlu diwaspadai")
    if bare_host in URL_SHORTENERS or host in URL_SHORTENERS:
        score += 30
        reasons.append("Link pemendek URL menyembunyikan alamat asli")
    if "@" in (parts.netloc or ""):
        score += 45
        reasons.append("Link memakai trik `@` untuk menyamarkan domain asli")
    return score, reasons


def _skor_sinyal_struktur(
    host: str, labels: list, tld: str, suspicious_context: bool, parts
) -> tuple[int, list[str]]:
    """Poin risiko dari struktur host (subdomain, tanda hubung, panjang, angka)."""
    reasons: list[str] = []
    score = 0
    is_ip_host = _IPV4_RE.match(host) is not None
    if not is_ip_host and len(labels) >= 4:
        score += 15
        reasons.append("Subdomain bertumpuk tidak wajar")
    hyphen_count = host.count("-")
    if not is_ip_host and hyphen_count >= 2:
        score += 12
        reasons.append("Domain memakai banyak tanda hubung (ciri domain tiruan)")
    if not is_ip_host and tld in HIGH_RISK_TLDS and len(labels) >= 3:
        score += 10
    if suspicious_context and any(k in (parts.path or "").lower() for k in PHISHING_KEYWORDS):
        score += 10
    if suspicious_context and any(k in host for k in PHISHING_KEYWORDS):
        score += 12
    if len(host) > 45:
        score += 8
    if re.search(r"\d{4,}", host):
        score += 8
    return score, reasons


def _nilai_risiko(score: int, reasons: list[str]) -> tuple[int, str]:
    """Batasi skor 0..100 lalu tentukan vonisnya."""
    score = max(0, min(100, score))
    if score >= 60:
        verdict = "berbahaya"
    elif score >= 30:
        verdict = "mencurigakan"
    else:
        verdict = "aman"
        if not reasons:
            reasons.append("Tidak ada pola phishing yang terdeteksi")
    return score, verdict


def analyze_url_risk(raw_url: str) -> dict:
    """Menganalisis risiko satu link tanpa API berbayar.

    Mengembalikan dict: `{url, host, score, verdict, reasons, brand}` dengan
    `verdict` bernilai `aman`, `mencurigakan`, atau `berbahaya`.
    """
    url = (raw_url or "").strip()
    reasons: list[str] = []
    score = 0

    candidate = url if "://" in url else f"https://{url.lstrip('/')}"
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return {
            "url": url,
            "host": "",
            "score": 100,
            "verdict": "berbahaya",
            "reasons": ["Format link tidak valid"],
            "brand": None,
        }

    if not host:
        return {
            "url": url,
            "host": "",
            "score": 100,
            "verdict": "berbahaya",
            "reasons": ["Link tanpa domain yang jelas"],
            "brand": None,
        }

    bare_host = host[4:] if host.startswith("www.") else host
    labels = host.split(".")
    tld = labels[-1] if labels else ""
    brand_hits = _brand_hits(host)
    impersonated = next((b for b in brand_hits if not _is_official_domain(host, b)), None)
    suspicious_context = (
        impersonated is not None
        or tld in HIGH_RISK_TLDS
        or tld in SUSPICIOUS_TLDS
        or bare_host in URL_SHORTENERS
        or _IPV4_RE.match(host) is not None
        or _PUNYCODE_RE.search(host) is not None
    )
    poin_domain, alasan_domain = _skor_sinyal_domain(host, bare_host, tld, impersonated, parts)
    poin_struktur, alasan_struktur = _skor_sinyal_struktur(
        host, labels, tld, suspicious_context, parts
    )
    score += poin_domain + poin_struktur
    reasons.extend(alasan_domain + alasan_struktur)

    score, verdict = _nilai_risiko(score, reasons)
    return {
        "url": url,
        "host": host,
        "score": score,
        "verdict": verdict,
        "reasons": reasons,
        "brand": impersonated,
    }


def scan_text_for_phishing(text: str) -> list[dict]:
    """Memeriksa seluruh link dalam teks dan hanya mengembalikan yang tidak aman."""
    findings: list[dict] = []
    for link in extract_links(text):
        result = analyze_url_risk(link)
        if result["verdict"] != "aman":
            findings.append(result)
    findings.sort(key=lambda item: item["score"], reverse=True)
    return findings


def is_phishing_guard_active(channel_id: int, guild_id: int) -> bool:
    cfg = security_guilds.get(guild_id)
    if not cfg or not cfg.get("enabled"):
        return False
    allowed = cfg.get("channel_ids") or []
    return not allowed or channel_id in allowed


def build_phishing_alert_embed(finding: dict, member: object) -> discord.Embed:
    embed = discord.Embed(
        title="🛡️ Link Berbahaya Terdeteksi & Ditindak",
        description=(
            f"**Pelaku:** {getattr(member, 'mention', 'Member')}\n"
            f"**Link:** `{finding['url'][:300]}`\n"
            f"**Domain:** `{finding['host']}`\n"
            f"**Tingkat Risiko:** **{finding['verdict'].upper()}** ({finding['score']}/100)"
        ),
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="🔍 Alasan Terdeteksi",
        value="\n".join(f"• {r}" for r in finding["reasons"][:6])[:1024],
        inline=False,
    )
    embed.set_footer(text="Anti-Phishing Guard • Tanpa API berbayar")
    return embed


async def handle_phishing_guard(message: object, *, notify: bool = True) -> bool:
    """Memeriksa satu pesan. Mengembalikan True jika pesan sudah ditindak (dihapus)."""
    guild = getattr(message, "guild", None)
    channel = getattr(message, "channel", None)
    author = getattr(message, "author", None)
    if guild is None or channel is None or author is None:
        return False
    if getattr(author, "bot", False) or not ENABLE_PHISHING_GUARD:
        return False

    if not is_phishing_guard_active(int(getattr(channel, "id", 0)), int(getattr(guild, "id", 0))):
        return False

    permissions = getattr(author, "guild_permissions", None)
    if permissions is not None and (
        getattr(permissions, "administrator", False) or getattr(permissions, "manage_messages", False)
    ):
        return False

    content = str(getattr(message, "content", "") or "")
    if "http" not in content and "www." not in content:
        return False

    findings = scan_text_for_phishing(content)
    if not findings:
        return False

    cfg = security_guilds.get(int(guild.id)) or {}
    strict = bool(cfg.get("strict", False))
    top = findings[0]
    should_act = top["verdict"] == "berbahaya" or (strict and top["verdict"] == "mencurigakan")
    action = str(cfg.get("action") or "hapus_peringat")

    deleted = False
    if should_act and action in ("hapus", "hapus_peringat"):
        try:
            await message.delete()
            deleted = True
        except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
            logger.warning("Gagal menghapus pesan phishing: %s", sanitize_error_message(exc))

    if should_act:
        cfg["blocked"] = int(cfg.get("blocked") or 0) + 1
        await save_server_features_to_disk()

    if notify and (deleted or action == "peringatkan" or strict):
        try:
            await channel.send(
                f"⚠️ {getattr(author, 'mention', 'Member')}, link itu terindikasi **{top['verdict']}** "
                f"(`{top['host']}`) dan demi keamanan warga lain "
                f"{'sudah dihapus' if deleted else 'mohon jangan dibuka'}.\n"
                "> 🛡️ *Selalu cek ejaan domain sebelum login atau klaim hadiah.*"
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    log_channel_id = cfg.get("log_channel_id")
    if log_channel_id:
        log_channel = guild.get_channel(int(log_channel_id)) if hasattr(guild, "get_channel") else None
        if log_channel is not None:
            try:
                await log_channel.send(embed=build_phishing_alert_embed(top, author))
            except (discord.Forbidden, discord.HTTPException):
                pass

    return deleted
