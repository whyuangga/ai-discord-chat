"""Fitur komunitas ringan yang **tidak memakai kuota Gemini** sama sekali.

Isi modul ini:
1. Reaction Role      — member klik emoji untuk mengambil role sendiri.
2. Starboard          — pesan populer otomatis disalin ke channel sorotan.
3. Reminder           — pengingat pribadi yang tahan restart.
4. Verification Gate  — tombol "Verifikasi Saya" untuk memberi role member.
5. Sticky Message     — pesan petunjuk yang selalu berada di bawah channel.
6. Perawatan          — backup konfigurasi otomatis + pelaporan error ke Discord.

Seluruh fitur **default NONAKTIF** sampai Admin menyalakannya per server/channel,
sehingga server yang belum memakai fitur ini tidak menambah beban sama sekali.
"""

import asyncio
import io
import json
import logging
import os
import re
import time
import zipfile

import discord

from config import (
    BACKUP_INTERVAL_DAYS,
    BOT_LOG_CHANNEL_ID,
    COMMUNITY_TOOLS_FILE,
    DATA_DIR,
    REMINDER_MAX_PER_USER,
    STARBOARD_DEFAULT_THRESHOLD,
    STARBOARD_EMOJI,
    STICKY_MIN_INTERVAL_SEC,
)
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.community_tools")

_tools_lock = asyncio.Lock()

# ==============================================================================
# STATE GLOBAL (dimuat & disimpan ke data/community_tools.json)
# ==============================================================================
reaction_role_panels: dict[int, dict] = {}   # message_id -> panel
reminders: dict[int, dict] = {}              # reminder_id -> data
starboard_guilds: dict[int, dict] = {}       # guild_id -> konfigurasi starboard
sticky_channels: dict[int, dict] = {}        # channel_id -> konfigurasi sticky
verification_guilds: dict[int, dict] = {}    # guild_id -> gerbang verifikasi
maintenance_guilds: dict[int, dict] = {}     # guild_id -> backup & log channel

_sticky_last_refresh: dict[int, float] = {}
_sticky_last_save: dict[int, float] = {}
_reminder_seq: int = 0
_last_error: dict = {"at": 0.0, "context": "", "message": ""}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def load_community_tools_from_disk() -> tuple[int, int, int, int, int]:
    """Memuat seluruh konfigurasi fitur komunitas. Mengembalikan jumlah tiap fitur."""
    global _reminder_seq
    reaction_role_panels.clear()
    reminders.clear()
    starboard_guilds.clear()
    sticky_channels.clear()
    verification_guilds.clear()
    maintenance_guilds.clear()
    _reminder_seq = 0

    if not COMMUNITY_TOOLS_FILE.exists():
        return 0, 0, 0, 0, 0

    try:
        raw = json.loads(COMMUNITY_TOOLS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", COMMUNITY_TOOLS_FILE, exc)
        return 0, 0, 0, 0, 0

    for mid_str, data in (raw.get("reaction_roles") or {}).items():
        try:
            options = []
            for opt in data.get("options") or []:
                role_id = _to_int(opt.get("role_id"))
                emoji = str(opt.get("emoji") or "").strip()
                if not role_id or not emoji:
                    continue
                options.append(
                    {
                        "emoji": emoji,
                        "role_id": role_id,
                        "label": str(opt.get("label") or "")[:100],
                    }
                )
            if not options:
                continue
            reaction_role_panels[int(mid_str)] = {
                "guild_id": _to_int(data.get("guild_id")),
                "channel_id": _to_int(data.get("channel_id")),
                "title": str(data.get("title") or "Ambil Role")[:256],
                "description": str(data.get("description") or "")[:4000],
                "options": options,
            }
        except (TypeError, ValueError):
            continue

    for rid_str, data in (raw.get("reminders") or {}).items():
        try:
            rid = int(rid_str)
        except (TypeError, ValueError):
            continue
        due_at = float(data.get("due_at") or 0)
        if due_at <= 0 or not data.get("text"):
            continue
        reminders[rid] = {
            "guild_id": _to_int(data.get("guild_id")),
            "channel_id": _to_int(data.get("channel_id")),
            "user_id": _to_int(data.get("user_id")),
            "text": str(data.get("text"))[:900],
            "due_at": due_at,
            "created_at": float(data.get("created_at") or 0),
        }
        _reminder_seq = max(_reminder_seq, rid)

    for gid_str, data in (raw.get("starboard") or {}).items():
        try:
            entries = {
                str(k): {
                    "starboard_id": _to_int(v.get("starboard_id")),
                    "count": _to_int(v.get("count")),
                }
                for k, v in (data.get("entries") or {}).items()
            }
            starboard_guilds[int(gid_str)] = {
                "enabled": bool(data.get("enabled", True)),
                "channel_id": _to_int(data.get("channel_id")),
                "threshold": max(1, _to_int(data.get("threshold"), STARBOARD_DEFAULT_THRESHOLD)),
                "emoji": str(data.get("emoji") or STARBOARD_EMOJI),
                "entries": entries,
            }
        except (TypeError, ValueError):
            continue

    for cid_str, data in (raw.get("sticky") or {}).items():
        try:
            content = str(data.get("content") or "").strip()
            if not content:
                continue
            sticky_channels[int(cid_str)] = {
                "guild_id": _to_int(data.get("guild_id")),
                "content": content[:3900],
                "title": str(data.get("title") or "")[:256],
                "last_message_id": _to_int(data.get("last_message_id")),
            }
        except (TypeError, ValueError):
            continue

    for gid_str, data in (raw.get("verification") or {}).items():
        try:
            role_id = _to_int(data.get("role_id"))
            if not role_id:
                continue
            verification_guilds[int(gid_str)] = {
                "enabled": bool(data.get("enabled", True)),
                "channel_id": _to_int(data.get("channel_id")),
                "role_id": role_id,
                "message_id": _to_int(data.get("message_id")),
            }
        except (TypeError, ValueError):
            continue

    for gid_str, data in (raw.get("maintenance") or {}).items():
        try:
            maintenance_guilds[int(gid_str)] = {
                "backup_channel_id": _to_int(data.get("backup_channel_id")) or None,
                "log_channel_id": _to_int(data.get("log_channel_id")) or None,
                "auto_backup": bool(data.get("auto_backup", True)),
                "last_backup_at": float(data.get("last_backup_at") or 0),
            }
        except (TypeError, ValueError):
            continue

    return (
        len(reaction_role_panels),
        len(reminders),
        len(starboard_guilds),
        len(sticky_channels),
        len(verification_guilds),
    )


async def save_community_tools_to_disk() -> None:
    """Menyimpan seluruh konfigurasi fitur komunitas secara atomik."""
    async with _tools_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "reaction_roles": {str(k): v for k, v in reaction_role_panels.items()},
                "reminders": {str(k): v for k, v in reminders.items()},
                "starboard": {str(k): v for k, v in starboard_guilds.items()},
                "sticky": {str(k): v for k, v in sticky_channels.items()},
                "verification": {str(k): v for k, v in verification_guilds.items()},
                "maintenance": {str(k): v for k, v in maintenance_guilds.items()},
            }
            tmp_file = COMMUNITY_TOOLS_FILE.with_suffix(".json.tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, COMMUNITY_TOOLS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan community_tools.json: %s", sanitize_error_message(exc))


# ==============================================================================
# 1. REACTION ROLE (/panel-role)
# ==============================================================================
def create_reaction_role_panel(
    guild_id: int,
    channel_id: int,
    message_id: int,
    *,
    title: str,
    description: str = "",
) -> dict:
    """Mendaftarkan pesan panel reaction role baru."""
    reaction_role_panels[int(message_id)] = {
        "guild_id": int(guild_id),
        "channel_id": int(channel_id),
        "title": (title or "Ambil Role")[:256],
        "description": (description or "")[:4000],
        "options": [],
    }
    return reaction_role_panels[int(message_id)]


def add_reaction_role_option(
    message_id: int,
    emoji: str,
    role_id: int,
    label: str = "",
) -> dict | None:
    """Menambah satu pasangan emoji ➔ role pada panel. Mengembalikan `None` bila duplikat."""
    panel = reaction_role_panels.get(int(message_id))
    if panel is None:
        return None
    clean_emoji = str(emoji or "").strip()
    if not clean_emoji:
        return None
    for opt in panel["options"]:
        if opt["emoji"] == clean_emoji or opt["role_id"] == int(role_id):
            return None
    panel["options"].append(
        {"emoji": clean_emoji, "role_id": int(role_id), "label": str(label or "")[:100]}
    )
    return panel


def remove_reaction_role_option(message_id: int, emoji: str) -> dict | None:
    """Menghapus pasangan emoji pada panel. Mengembalikan `None` bila tidak ditemukan."""
    panel = reaction_role_panels.get(int(message_id))
    if panel is None:
        return None
    clean_emoji = str(emoji or "").strip()
    before = len(panel["options"])
    panel["options"] = [opt for opt in panel["options"] if opt["emoji"] != clean_emoji]
    return panel if len(panel["options"]) != before else None


def delete_reaction_role_panel(message_id: int) -> bool:
    return reaction_role_panels.pop(int(message_id), None) is not None


def get_guild_reaction_panels(guild_id: int) -> list[tuple[int, dict]]:
    return [(mid, p) for mid, p in reaction_role_panels.items() if p.get("guild_id") == guild_id]


def _emoji_matches(stored: str, incoming: str) -> bool:
    """Membandingkan emoji biasa maupun emoji kustom (`nama:id`)."""
    if stored == incoming:
        return True
    if ":" in stored and ":" in incoming:
        return stored.split(":")[0] == incoming.split(":")[0]
    return False


def resolve_reaction_role(message_id: int, emoji: str) -> int | None:
    """Mencari `role_id` yang terhubung dengan emoji pada sebuah panel."""
    panel = reaction_role_panels.get(int(message_id))
    if panel is None:
        return None
    for opt in panel["options"]:
        if _emoji_matches(opt["emoji"], str(emoji)):
            return int(opt["role_id"])
    return None


async def handle_reaction_role(bot: discord.Client, payload, *, added: bool) -> bool:
    """Memberi/mencabut role saat member menekan emoji pada panel reaction role."""
    guild_id = getattr(payload, "guild_id", None)
    if guild_id is None:
        return False
    role_id = resolve_reaction_role(payload.message_id, str(payload.emoji))
    if role_id is None:
        return False

    guild = bot.get_guild(guild_id) if hasattr(bot, "get_guild") else None
    if guild is None:
        return False

    member = getattr(payload, "member", None)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
    if getattr(member, "bot", False):
        return False

    role = guild.get_role(role_id)
    if role is None:
        return False
    if guild.me and role >= guild.me.top_role:
        logger.info("Reaction Role dilewati: role %s berada di atas role bot.", role_id)
        return False

    try:
        if added:
            await member.add_roles(role, reason="Reaction Role")
        else:
            await member.remove_roles(role, reason="Reaction Role dilepas")
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.info("Gagal mengubah Reaction Role: %s", sanitize_error_message(exc))
        return False
    return True


# ==============================================================================
# 2. STARBOARD (/starboard)
# ==============================================================================
def set_starboard_config(
    guild_id: int,
    *,
    channel_id: int | None = None,
    threshold: int | None = None,
    emoji: str | None = None,
    enabled: bool | None = None,
) -> dict | None:
    """Mengatur channel sorotan, batas bintang, emoji, & status aktif starboard."""
    existing = starboard_guilds.get(guild_id)
    if enabled is False:
        starboard_guilds.pop(guild_id, None)
        return None

    cfg = existing or {
        "enabled": True,
        "channel_id": 0,
        "threshold": STARBOARD_DEFAULT_THRESHOLD,
        "emoji": STARBOARD_EMOJI,
        "entries": {},
    }
    if channel_id is not None:
        cfg["channel_id"] = int(channel_id)
    if threshold is not None:
        cfg["threshold"] = max(1, min(50, int(threshold)))
    if emoji is not None and str(emoji).strip():
        cfg["emoji"] = str(emoji).strip()[:64]
    cfg["enabled"] = True if enabled is None else bool(enabled)
    starboard_guilds[guild_id] = cfg
    return cfg


def build_starboard_embed(message: discord.Message, count: int, emoji: str) -> discord.Embed:
    """Menyusun embed sorotan untuk pesan yang mencapai batas bintang."""
    embed = discord.Embed(
        description=(message.content or "")[:3900] or "_*(tanpa teks — lihat lampiran)*_",
        color=discord.Color.gold(),
        timestamp=message.created_at or discord.utils.utcnow(),
    )
    embed.set_author(
        name=getattr(message.author, "display_name", "Member"),
        icon_url=getattr(getattr(message.author, "display_avatar", None), "url", None),
    )
    if message.attachments:
        first = message.attachments[0]
        if (first.content_type or "").startswith("image"):
            embed.set_image(url=first.url)
        else:
            embed.add_field(name="📎 Lampiran", value=first.filename[:200], inline=False)
    embed.add_field(
        name="🔗 Sumber",
        value=f"[Lompat ke pesan]({message.jump_url})",
        inline=False,
    )
    embed.set_footer(text=f"{emoji} {count} • disorot oleh warga server")
    return embed


async def handle_starboard_reaction(bot: discord.Client, payload, *, added: bool) -> bool:
    """Menyalin/menghapus pesan di channel starboard sesuai jumlah reaksi."""
    cfg = starboard_guilds.get(getattr(payload, "guild_id", None))
    if not cfg or not cfg.get("enabled"):
        return False
    starboard_cid = _to_int(cfg.get("channel_id"))
    if not starboard_cid or payload.channel_id == starboard_cid:
        return False
    if not _emoji_matches(str(cfg.get("emoji") or STARBOARD_EMOJI), str(payload.emoji)):
        return False

    entry_key = str(payload.message_id)
    entry = (cfg.get("entries") or {}).get(entry_key)
    if not added and not entry:
        return False

    source_channel = bot.get_channel(payload.channel_id) if hasattr(bot, "get_channel") else None
    if source_channel is None:
        return False
    try:
        message = await source_channel.fetch_message(payload.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False
    if getattr(message.author, "bot", False):
        return False

    emoji_str = str(cfg.get("emoji") or STARBOARD_EMOJI)
    count = 0
    for reaction in message.reactions:
        if _emoji_matches(emoji_str, str(reaction.emoji)):
            count = max(count, int(reaction.count) - 1)  # kurangi reaksi bot sendiri
            break

    threshold = max(1, _to_int(cfg.get("threshold"), STARBOARD_DEFAULT_THRESHOLD))
    starboard_channel = bot.get_channel(starboard_cid)

    if count >= threshold and not entry:
        if starboard_channel is None:
            return False
        try:
            posted = await starboard_channel.send(
                content=f"{emoji_str} **{count}** • <#{payload.channel_id}>",
                embed=build_starboard_embed(message, count, emoji_str),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.info("Gagal kirim starboard: %s", sanitize_error_message(exc))
            return False
        cfg.setdefault("entries", {})[entry_key] = {
            "starboard_id": posted.id,
            "count": count,
        }
        await save_community_tools_to_disk()
        return True

    if count < threshold and entry:
        if starboard_channel is not None and _to_int(entry.get("starboard_id")):
            try:
                partial = starboard_channel.get_partial_message(int(entry["starboard_id"]))
                await partial.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        cfg.get("entries", {}).pop(entry_key, None)
        await save_community_tools_to_disk()
        return True

    return False


# ==============================================================================
# 3. REMINDER (/ingatkan)
# ==============================================================================
_UNIT_SECONDS: dict[str, int] = {
    "s": 1, "dtk": 1, "detik": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "mnt": 60, "menit": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "j": 3600, "jam": 3600, "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "hari": 86400, "day": 86400, "days": 86400,
    "w": 604800, "mgg": 604800, "minggu": 604800, "week": 604800, "weeks": 604800,
}

REMINDER_MAX_SECONDS = 365 * 86400


def parse_reminder_duration(raw: str | None) -> int | None:
    """Membaca durasi pengingat fleksibel: `10m`, `2 jam`, `1j30m`, `2 hari`, `45` (menit)."""
    text = str(raw or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"(?i)\bdan\b", " ", text).replace(",", " ")

    total = 0
    matched = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]*)", text):
        try:
            number = float(value)
        except ValueError:
            continue
        multiplier = _UNIT_SECONDS.get(unit, 60) if unit else 60
        total += int(number * multiplier)
        matched = True

    if not matched or total <= 0 or total > REMINDER_MAX_SECONDS:
        return None
    return total


def format_duration_short(seconds: int) -> str:
    """Format durasi singkat Bahasa Indonesia: `2j 15m`."""
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} hari")
    if hours:
        parts.append(f"{hours}j")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not parts:
        parts.append(f"{secs}d")
    return " ".join(parts) or "0d"


def add_reminder(
    guild_id: int,
    channel_id: int,
    user_id: int,
    text: str,
    seconds: int,
) -> dict | None:
    """Menyimpan pengingat baru. `None` bila kuota pengingat pengguna sudah penuh."""
    global _reminder_seq
    active = [r for r in reminders.values() if r.get("user_id") == user_id]
    if len(active) >= REMINDER_MAX_PER_USER:
        return None

    _reminder_seq += 1
    now = time.time()
    reminders[_reminder_seq] = {
        "id": _reminder_seq,
        "guild_id": int(guild_id),
        "channel_id": int(channel_id),
        "user_id": int(user_id),
        "text": str(text or "")[:900],
        "due_at": now + max(1, int(seconds)),
        "created_at": now,
    }
    return reminders[_reminder_seq]


def cancel_reminder(reminder_id: int, user_id: int) -> bool:
    """Membatalkan pengingat milik pengguna tertentu."""
    data = reminders.get(int(reminder_id))
    if data is None or data.get("user_id") != user_id:
        return False
    reminders.pop(int(reminder_id), None)
    return True


def list_user_reminders(user_id: int) -> list[dict]:
    items = [r for r in reminders.values() if r.get("user_id") == user_id]
    return sorted(items, key=lambda r: float(r.get("due_at") or 0))


async def run_reminder_check(bot: discord.Client) -> int:
    """Mengirim seluruh pengingat yang sudah jatuh tempo (dipanggil dari loop latar belakang)."""
    now = time.time()
    due = [(rid, r) for rid, r in list(reminders.items()) if float(r.get("due_at") or 0) <= now]
    sent = 0
    for rid, data in due:
        user_id = _to_int(data.get("user_id"))
        content = (
            f"⏰ <@{user_id}> **Pengingat!**\n"
            f"> {str(data.get('text') or '')[:900]}\n"
            f"*(dipasang {format_duration_short(now - float(data.get('created_at') or now))} lalu)*"
        )
        delivered = False

        channel = None
        get_channel = getattr(bot, "get_channel", None)
        if callable(get_channel):
            channel = get_channel(_to_int(data.get("channel_id")))
        if channel is not None:
            try:
                await channel.send(content=content, allowed_mentions=discord.AllowedMentions(users=True))
                delivered = True
            except (discord.Forbidden, discord.HTTPException):
                delivered = False

        if not delivered:
            get_user = getattr(bot, "get_user", None)
            user = get_user(user_id) if callable(get_user) else None
            if user is not None:
                try:
                    await user.send(content=content)
                    delivered = True
                except (discord.Forbidden, discord.HTTPException):
                    delivered = False

        reminders.pop(rid, None)
        sent += 1

    if sent:
        await save_community_tools_to_disk()
    return sent


# ==============================================================================
# 4. VERIFICATION GATE (/verifikasi)
# ==============================================================================
def set_verification_config(
    guild_id: int,
    *,
    channel_id: int | None = None,
    role_id: int | None = None,
    message_id: int | None = None,
    enabled: bool | None = None,
) -> dict | None:
    """Mengatur gerbang verifikasi (channel + role yang diberikan setelah klik tombol)."""
    if enabled is False:
        verification_guilds.pop(guild_id, None)
        return None

    cfg = verification_guilds.get(guild_id) or {
        "enabled": True,
        "channel_id": 0,
        "role_id": 0,
        "message_id": 0,
    }
    if channel_id is not None:
        cfg["channel_id"] = int(channel_id)
    if role_id is not None:
        cfg["role_id"] = int(role_id)
    if message_id is not None:
        cfg["message_id"] = int(message_id)
    cfg["enabled"] = True if enabled is None else bool(enabled)
    verification_guilds[guild_id] = cfg
    return cfg


def build_verification_embed(guild_name: str, role_name: str, extra_note: str = "") -> discord.Embed:
    embed = discord.Embed(
        title="✅ Verifikasi Keanggotaan",
        description=(
            f"Selamat datang di **{guild_name}**!\n\n"
            "Tekan tombol **Verifikasi Saya** di bawah untuk membuka seluruh akses channel.\n"
            f"Kamu akan otomatis mendapatkan role **{role_name}**."
        ),
        color=discord.Color.green(),
    )
    if extra_note:
        embed.add_field(name="📌 Catatan", value=extra_note[:1024], inline=False)
    embed.set_footer(text="Sekali klik saja • Anti-bot & anti-raid")
    return embed


async def grant_verification_role(user: discord.abc.User, guild_id: int) -> tuple[bool, str]:
    """Memberi role verifikasi kepada member. Mengembalikan `(berhasil, pesan)`."""
    cfg = verification_guilds.get(guild_id)
    if not cfg or not cfg.get("enabled"):
        return False, "⚠️ Gerbang verifikasi belum aktif di server ini."

    role_id = _to_int(cfg.get("role_id"))
    if not role_id:
        return False, "⚠️ Role verifikasi belum diatur. Hubungi Admin."

    if not isinstance(user, discord.Member):
        return False, "⚠️ Verifikasi hanya bisa dilakukan di dalam server."

    if any(role.id == role_id for role in user.roles):
        return True, "✅ Kamu sudah terverifikasi sebelumnya. Selamat menikmati server!"

    guild = user.guild
    role = guild.get_role(role_id)
    if role is None:
        return False, "⚠️ Role verifikasi sudah dihapus dari server. Hubungi Admin."
    if guild.me and role >= guild.me.top_role:
        return False, "⚠️ Role verifikasi berada di atas role bot. Minta Admin menurunkannya."

    try:
        await user.add_roles(role, reason="Verifikasi member")
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.info("Gagal memberi role verifikasi: %s", sanitize_error_message(exc))
        return False, "⚠️ Bot tidak punya izin memberikan role tersebut."
    return True, f"✅ Verifikasi berhasil! Role **{role.name}** sudah terpasang."


# ==============================================================================
# 5. STICKY MESSAGE (/sticky)
# ==============================================================================
def set_sticky_config(
    channel_id: int,
    guild_id: int,
    content: str,
    *,
    title: str = "",
) -> dict | None:
    """Memasang pesan sticky pada sebuah channel (default aktif)."""
    clean = str(content or "").strip()
    if not clean:
        return None
    existing = sticky_channels.get(channel_id) or {}
    sticky_channels[channel_id] = {
        "guild_id": int(guild_id),
        "content": clean[:3900],
        "title": str(title or "")[:256],
        "last_message_id": _to_int(existing.get("last_message_id")),
    }
    return sticky_channels[channel_id]


def remove_sticky_config(channel_id: int) -> bool:
    _sticky_last_refresh.pop(int(channel_id), None)
    _sticky_last_save.pop(int(channel_id), None)
    return sticky_channels.pop(int(channel_id), None) is not None


def build_sticky_embed(cfg: dict) -> discord.Embed:
    return discord.Embed(
        title=(cfg.get("title") or "📌 Informasi Penting")[:256],
        description=str(cfg.get("content") or "")[:4000],
        color=discord.Color.blurple(),
    ).set_footer(text="Pesan ini otomatis turun ke bawah setiap ada obrolan baru")


async def maybe_refresh_sticky(bot: discord.Client, message: discord.Message) -> bool:
    """Menurunkan ulang pesan sticky ke bawah channel (dibatasi agar tidak spam)."""
    channel_id = getattr(message.channel, "id", None)
    cfg = sticky_channels.get(channel_id)
    if not cfg:
        return False

    now = time.time()
    if now - _sticky_last_refresh.get(channel_id, 0.0) < STICKY_MIN_INTERVAL_SEC:
        return False
    _sticky_last_refresh[channel_id] = now

    old_id = _to_int(cfg.get("last_message_id"))
    if old_id:
        try:
            await message.channel.get_partial_message(old_id).delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    try:
        posted = await message.channel.send(embed=build_sticky_embed(cfg))
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.info("Gagal mengirim sticky message: %s", sanitize_error_message(exc))
        return False

    cfg["last_message_id"] = posted.id

    # Hemat I/O: simpan maksimal sekali per menit per channel (channel ramai tetap aman).
    if now - _sticky_last_save.get(channel_id, 0.0) >= 60:
        _sticky_last_save[channel_id] = now
        await save_community_tools_to_disk()
    return True


# ==============================================================================
# 6. PERAWATAN: BACKUP OTOMATIS & LOG ERROR (/perawatan)
# ==============================================================================
_UNSET: object = object()


def set_maintenance_config(
    guild_id: int,
    *,
    backup_channel_id: object = _UNSET,
    log_channel_id: object = _UNSET,
    auto_backup: object = _UNSET,
) -> dict:
    """Mengatur channel backup, channel log error, & status backup otomatis."""
    cfg = maintenance_guilds.get(guild_id) or {
        "backup_channel_id": None,
        "log_channel_id": None,
        "auto_backup": True,
        "last_backup_at": 0.0,
    }
    if backup_channel_id is not _UNSET:
        cfg["backup_channel_id"] = _to_int(backup_channel_id) or None
    if log_channel_id is not _UNSET:
        cfg["log_channel_id"] = _to_int(log_channel_id) or None
    if auto_backup is not _UNSET:
        cfg["auto_backup"] = bool(auto_backup)
    maintenance_guilds[guild_id] = cfg
    return cfg


def build_backup_archive() -> tuple[bytes, str]:
    """Membuat arsip ZIP berisi seluruh berkas konfigurasi `data/*.json`."""
    buffer = io.BytesIO()
    included = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DATA_DIR.glob("*.json")):
            try:
                archive.writestr(f"data/{path.name}", path.read_text(encoding="utf-8"))
                included += 1
            except Exception:  # pragma: no cover - berkas terkunci
                continue
        archive.writestr(
            "INFO.txt",
            "Backup konfigurasi bot AI Discord Chat.\n"
            f"Dibuat: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Jumlah berkas konfigurasi: {included}\n"
            "Cara memulihkan: ekstrak folder `data/` ke direktori bot, lalu restart bot.\n",
        )
    buffer.seek(0)
    return buffer.getvalue(), f"backup-bot-{time.strftime('%Y%m%d-%H%M%S')}.zip"


async def send_backup(bot: discord.Client, channel) -> tuple[bool, str]:
    """Mengirim berkas backup ke channel tujuan."""
    data, filename = build_backup_archive()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > 7.5:
        return False, f"⚠️ Ukuran backup {size_mb:.1f} MB melebihi batas upload Discord (8 MB)."
    try:
        await channel.send(
            content="🗂️ **Backup konfigurasi bot** — simpan berkas ini di tempat aman.",
            file=discord.File(io.BytesIO(data), filename=filename),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        return False, f"⚠️ Gagal mengirim backup: {sanitize_error_message(exc)}"
    return True, filename


async def run_backup_check(bot: discord.Client) -> int:
    """Backup otomatis berkala ke channel yang dipilih Admin (default tiap 7 hari)."""
    if BACKUP_INTERVAL_DAYS <= 0:
        return 0
    interval = BACKUP_INTERVAL_DAYS * 86400
    now = time.time()
    sent = 0
    for gid, cfg in list(maintenance_guilds.items()):
        if not cfg.get("auto_backup"):
            continue
        channel_id = _to_int(cfg.get("backup_channel_id"))
        if not channel_id:
            continue
        if now - float(cfg.get("last_backup_at") or 0) < interval:
            continue
        get_channel = getattr(bot, "get_channel", None)
        channel = get_channel(channel_id) if callable(get_channel) else None
        if channel is None:
            continue
        ok, _ = await send_backup(bot, channel)
        if not ok:
            continue
        cfg["last_backup_at"] = now
        sent += 1

    if sent:
        await save_community_tools_to_disk()
    return sent


def record_last_error(context: str, exc: BaseException) -> None:
    """Menyimpan jejak error terakhir untuk ditampilkan di `/status`."""
    _last_error["at"] = time.time()
    _last_error["context"] = str(context or "")[:200]
    _last_error["message"] = sanitize_error_message(exc)[:400]


def get_last_error() -> dict:
    return dict(_last_error)


async def report_error(
    bot: discord.Client,
    *,
    context: str,
    exc: BaseException,
    guild: discord.Guild | None = None,
) -> bool:
    """Mengirim ringkasan error ke channel log Discord (jika Admin mengaturnya)."""
    record_last_error(context, exc)

    channel_id = 0
    if guild is not None:
        channel_id = _to_int((maintenance_guilds.get(guild.id) or {}).get("log_channel_id"))
    if not channel_id:
        channel_id = _to_int(BOT_LOG_CHANNEL_ID)
    if not channel_id:
        return False

    get_channel = getattr(bot, "get_channel", None)
    channel = get_channel(channel_id) if callable(get_channel) else None
    if channel is None:
        return False

    detail = sanitize_error_message(exc)[:1500]
    embed = discord.Embed(
        title="🚨 Terjadi Error pada Bot",
        description=f"**Konteks:** `{str(context)[:200]}`\n**Tipe:** `{type(exc).__name__}`",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📄 Detail", value=f"```\n{detail}\n```"[:1024], inline=False)
    embed.set_footer(text="Log otomatis • cek panel Wispbyte untuk traceback lengkap")
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        return False
    return True


# ==============================================================================
# PEMBERSIHAN SAAT CHANNEL DIHAPUS
# ==============================================================================
def handle_channel_delete(channel) -> bool:
    """Membersihkan konfigurasi yang menunjuk ke channel yang sudah dihapus."""
    channel_id = getattr(channel, "id", None)
    guild_id = getattr(getattr(channel, "guild", None), "id", None)
    if not channel_id:
        return False

    changed = False
    if remove_sticky_config(channel_id):
        changed = True

    for mid, panel in list(reaction_role_panels.items()):
        if panel.get("channel_id") == channel_id:
            reaction_role_panels.pop(mid, None)
            changed = True

    cfg = starboard_guilds.get(guild_id) if guild_id else None
    if cfg and _to_int(cfg.get("channel_id")) == channel_id:
        starboard_guilds.pop(guild_id, None)
        changed = True

    v_cfg = verification_guilds.get(guild_id) if guild_id else None
    if v_cfg and _to_int(v_cfg.get("channel_id")) == channel_id:
        verification_guilds.pop(guild_id, None)
        changed = True

    m_cfg = maintenance_guilds.get(guild_id) if guild_id else None
    if m_cfg:
        if _to_int(m_cfg.get("backup_channel_id")) == channel_id:
            m_cfg["backup_channel_id"] = None
            changed = True
        if _to_int(m_cfg.get("log_channel_id")) == channel_id:
            m_cfg["log_channel_id"] = None
            changed = True

    return changed
