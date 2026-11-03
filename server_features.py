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
    FACTS_DEFAULT_HOUR,
    FACTS_DEFAULT_MINUTE,
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

    for gid_str, data in (raw.get("serverstats") or {}).items():
        try:
            if not data.get("enabled", True):
                continue
            serverstats_guilds[int(gid_str)] = {
                "enabled": True,
                "category_id": _to_int(data.get("category_id")) or None,
                "channels": {str(k): _to_int(v) for k, v in (data.get("channels") or {}).items()},
                "last_update_at": float(data.get("last_update_at") or 0.0),
            }
        except (TypeError, ValueError):
            continue

    for gid_str, data in (raw.get("autorole") or {}).items():
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

    for gid_str, data in (raw.get("facts") or {}).items():
        try:
            if not data.get("enabled", True):
                continue
            facts_guilds[int(gid_str)] = {
                "enabled": True,
                "channel_id": _to_int(data.get("channel_id")),
                "hour": max(0, min(23, _to_int(data.get("hour"), FACTS_DEFAULT_HOUR))),
                "minute": max(0, min(59, _to_int(data.get("minute"), FACTS_DEFAULT_MINUTE))),
                "last_sent_date": str(data.get("last_sent_date") or ""),
                "recent_facts": [str(x) for x in (data.get("recent_facts") or [])[-12:]],
            }
        except (TypeError, ValueError):
            continue

    for gid_str, data in (raw.get("security") or {}).items():
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

    return len(serverstats_guilds), len(autorole_guilds), len(facts_guilds), len(security_guilds)


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
        except Exception as exc:
            logger.warning("Gagal menyimpan server_features.json: %s", sanitize_error_message(exc))


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
)

STATS_CATEGORY_NAME = "📊 Statistik Server"


def set_serverstats_config(guild_id: int, *, enabled: bool) -> dict | None:
    """Mengaktifkan / menonaktifkan pembaruan otomatis Voice Channel statistik server."""
    if not enabled:
        serverstats_guilds.pop(guild_id, None)
        return None

    existing = serverstats_guilds.get(guild_id) or {}
    serverstats_guilds[guild_id] = {
        "enabled": True,
        "category_id": existing.get("category_id"),
        "channels": dict(existing.get("channels") or {}),
        "last_update_at": float(existing.get("last_update_at") or 0.0),
    }
    return serverstats_guilds[guild_id]


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


def build_serverstats_embed(
    guild: discord.Guild,
    *,
    presence_count: int | None = None,
) -> discord.Embed:
    """Menyusun kartu statistik server yang cantik & informatif (tanpa API berbayar)."""
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

    embed = discord.Embed(
        title=f"📊 Statistik Server — {getattr(guild, 'name', 'Server')}",
        description=(
            getattr(guild, "description", None)
            or "_Ringkasan lengkap kondisi server saat ini._"
        ),
        color=discord.Color.brand_green(),
        timestamp=discord.utils.utcnow(),
    )

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
    embed.add_field(
        name="📅 Informasi Server",
        value=(
            f"• **Dibuat:** {created_txt}\n"
            f"• **Pemilik:** {owner_txt}"
        ),
        inline=True,
    )

    icon = getattr(guild, "icon", None)
    if icon:
        embed.set_thumbnail(url=icon.url if hasattr(icon, "url") else str(icon))
    embed.set_footer(text="Statistik real-time • diperbarui otomatis")
    return embed


def _stats_channel_name(emoji: str, label: str, value: str) -> str:
    return f"{emoji} {label}: {value}"[:100]


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

    presence_count = getattr(guild, "approximate_presence_count", None)
    if bot is not None and presence_count is None:
        try:
            fresh = await bot.fetch_guild(guild.id, with_counts=True)
            presence_count = getattr(fresh, "approximate_presence_count", None)
        except (discord.HTTPException, AttributeError):
            presence_count = None

    members = list(getattr(guild, "members", []) or [])
    total_members = int(getattr(guild, "member_count", 0) or 0)
    bots = sum(1 for m in members if getattr(m, "bot", False))
    humans = max(0, total_members - bots) if members else None
    boost_count = int(getattr(guild, "premium_subscription_count", 0) or 0)

    values = {
        "members": format_number(total_members),
        "humans": format_number(humans),
        "bots": format_number(bots),
        "online": format_number(presence_count),
        "boosts": format_number(boost_count),
    }

    category = None
    cat_id = cfg.get("category_id")
    if cat_id:
        found = guild.get_channel(int(cat_id))
        if isinstance(found, discord.CategoryChannel):
            category = found

    if category is None:
        try:
            category = await guild.create_category(STATS_CATEGORY_NAME, reason="Server Stats otomatis")
            cfg["category_id"] = category.id
        except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
            logger.warning("Gagal membuat kategori Server Stats: %s", sanitize_error_message(exc))
            return 0

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)
    }

    channels_cfg: dict = cfg.setdefault("channels", {})
    changed = 0
    for key, emoji, label in STATS_CHANNEL_SPECS:
        desired = _stats_channel_name(emoji, label, values[key])
        existing = guild.get_channel(int(channels_cfg[key])) if channels_cfg.get(key) else None

        if not isinstance(existing, discord.VoiceChannel):
            existing = None
            # Cari channel yang sudah ada dengan nama serupa agar tidak duplikat saat restart
            for ch in getattr(guild, "voice_channels", []) or []:
                if str(getattr(ch, "name", "")).startswith(f"{emoji} {label}:"):
                    existing = ch
                    break

        try:
            if existing is None:
                created = await guild.create_voice_channel(
                    desired,
                    category=category,
                    overwrites=overwrites,
                    reason="Server Stats otomatis",
                )
                channels_cfg[key] = created.id
                changed += 1
                continue

            if existing.name != desired:
                await existing.edit(name=desired, reason="Perbarui Server Stats")
                changed += 1
            channels_cfg[key] = existing.id
        except discord.HTTPException as exc:
            logger.warning("Gagal memperbarui channel statistik %s: %s", key, sanitize_error_message(exc))
        except AttributeError:
            return 0

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
# 3. FAKTA UNIK DUNIA HARIAN (/fakta)
# ==============================================================================
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
    hour: int | None = None,
    minute: int | None = None,
) -> dict | None:
    """Mengatur jadwal rubrik Fakta Unik Dunia harian (default 08:00)."""
    if not enabled:
        facts_guilds.pop(guild_id, None)
        return None

    existing = facts_guilds.get(guild_id) or {}
    facts_guilds[guild_id] = {
        "enabled": True,
        "channel_id": int(channel_id),
        "hour": max(0, min(23, int(hour if hour is not None else existing.get("hour", FACTS_DEFAULT_HOUR)))),
        "minute": max(0, min(59, int(minute if minute is not None else existing.get("minute", FACTS_DEFAULT_MINUTE)))),
        "last_sent_date": str(existing.get("last_sent_date") or ""),
        "recent_facts": list(existing.get("recent_facts") or [])[-12:],
    }
    return facts_guilds[guild_id]


async def generate_daily_facts(
    guild_id: int,
    bot_display_name: str,
    *,
    count: int = 4,
    http_session=None,
) -> tuple[str | None, str | None]:
    """Membuat 3–4 fakta unik dari berbagai negara memakai Gemini Free Tier."""
    guild_cfg = get_guild_settings(guild_id)
    agent_name = guild_cfg.get("nickname") or bot_display_name or "Teman"
    cfg = facts_guilds.get(guild_id) or {}
    recent = [str(x) for x in (cfg.get("recent_facts") or [])[-8:]]
    avoid_block = ""
    if recent:
        joined = " | ".join(f'"{r[:90]}"' for r in recent)
        avoid_block = (
            f"\nJANGAN mengulang fakta berikut yang sudah pernah dipakai: [{joined}]. "
            "Pilih negara & fakta yang benar-benar berbeda."
        )

    system_prompt = (
        f"Kamu adalah '{agent_name}', penulis rubrik **Fakta Unik Dunia** di sebuah server Discord Indonesia.\n"
        "Tulis dengan gaya santai, cerdas, dan membuat pembaca berkata 'wow, baru tahu!'.\n"
        "Seluruh tulisan WAJIB Bahasa Indonesia yang rapi dan enak dibaca."
    )
    user_prompt = (
        f"Buat tepat {count} fakta unik & benar dari {count} NEGARA BERBEDA di benua/region yang berbeda-beda "
        "(contoh: Asia Timur, Asia Tenggara, Eropa, Afrika, Amerika Latin, Timur Tengah, Oseania).\n\n"
        "ATURAN FORMAT (wajib dipatuhi):\n"
        f"1. Setiap fakta diawali emoji bendera negara + nama negara tebal, contoh: 🇯🇵 **Jepang** — fakta...\n"
        "2. Satu fakta 1–2 kalimat pendek, maksimal 220 karakter.\n"
        "3. Fakta harus spesifik, unik, dan tidak normatif (budaya, alam, sains, kuliner, sejarah, teknologi).\n"
        "4. Pisahkan setiap fakta dengan satu baris kosong.\n"
        "5. Tanpa judul, tanpa pengantar, tanpa penutup, tanpa penomoran tambahan."
        f"{avoid_block}"
    )

    reply = await _call_gemini_agent(
        system_prompt,
        [{"role": "user", "parts": [{"text": user_prompt}]}],
        temperature=0.95,
        max_tokens=1200,
        thinking_level="minimal",
        has_media=False,
        http_session=http_session,
    )
    if reply:
        cleaned = reply.strip()
        if len(cleaned) >= 80:
            return cleaned[:3900], None
    return None, "Gagal membuat fakta (cek GEMINI_API_KEY atau kuota Free Tier)."


def build_facts_fallback(count: int = 4) -> str:
    """Cadangan fakta statis agar rubrik tetap terkirim walau Gemini sedang gangguan."""
    day_index = int(time.time() // 86400)
    picked = [FACTS_FALLBACK[(day_index + i) % len(FACTS_FALLBACK)] for i in range(count)]
    return "\n\n".join(picked)


def build_facts_embed(guild_config: dict, content: str) -> discord.Embed:
    t_ctx = get_realtime_time_context(guild_config.get("timezone", BOT_TIMEZONE))
    return discord.Embed(
        title=f"🌍 Fakta Unik Dunia — {t_ctx['day_name']}, {t_ctx['date_str']}",
        description=content[:4050],
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    ).set_footer(text=f"Rubrik Fakta Harian • {t_ctx['clock']}")


async def run_facts_check(bot: discord.Client, *, http_session=None) -> int:
    """Loop latar belakang: mengirim rubrik Fakta Unik Dunia sesuai jadwal tiap server."""
    sent = 0
    for gid, cfg in list(facts_guilds.items()):
        if not cfg.get("enabled"):
            continue
        channel = bot.get_channel(int(cfg.get("channel_id") or 0))
        if channel is None:
            continue

        guild_cfg = get_guild_settings(gid)
        t_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))
        if str(cfg.get("last_sent_date") or "") == t_ctx["iso_date"]:
            continue

        due_hour = int(cfg.get("hour", FACTS_DEFAULT_HOUR))
        due_minute = int(cfg.get("minute", FACTS_DEFAULT_MINUTE))
        if (t_ctx["hour"], t_ctx["minute"]) < (due_hour, due_minute):
            continue

        bot_name = getattr(getattr(bot, "user", None), "display_name", None) or "Teman"
        content, err = await generate_daily_facts(gid, bot_name, http_session=http_session)
        if not content:
            logger.info("Fakta harian memakai cadangan statis: %s", err)
            content = build_facts_fallback()

        try:
            await channel.send(embed=build_facts_embed(guild_cfg, content))
            sent += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Gagal kirim Fakta Harian di %s: %s", gid, sanitize_error_message(exc))
            continue

        cfg["last_sent_date"] = t_ctx["iso_date"]
        cfg["recent_facts"] = (list(cfg.get("recent_facts") or []) + [content[:400]])[-12:]
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

    score = max(0, min(100, score))
    if score >= 60:
        verdict = "berbahaya"
    elif score >= 30:
        verdict = "mencurigakan"
    else:
        verdict = "aman"
        if not reasons:
            reasons.append("Tidak ada pola phishing yang terdeteksi")

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
