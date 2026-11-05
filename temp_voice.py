"""Temp Voice — "Join to Create" voice channel (ala ProBot / YAGPDB).

Alur:
    1. Admin menjalankan `/tempvoice atur hub:#➕ Buat Voice`.
    2. Member masuk ke channel hub → bot membuat voice room baru di kategori yang sama,
       memindahkan member ke sana, dan menjadikannya **pemilik** room.
    3. Pemilik bisa mengunci room, mengganti nama, membatasi jumlah slot, & menendang.
    4. Room otomatis dihapus saat kosong (hemat kuota channel Discord: maks 500 channel/server).

Semua data lokal di `data/temp_voice.json` → aman restart, tanpa AI/kuota.
"""

import asyncio
import json
import logging
import re
import time

import discord

from config import DATA_DIR, TEMP_VOICE_FILE

logger = logging.getLogger("gemini_bot.temp_voice")

MAX_ROOMS_PER_GUILD = 30          # jaga-jaga agar tidak menyentuh batas 500 channel/server
DEFAULT_NAME_TEMPLATE = "🔊 {user}"

temp_voice_guilds: dict[int, dict] = {}   # guild_id -> {hub_id, name_template, user_limit, enabled}
temp_rooms: dict[int, dict] = {}          # channel_id -> {guild_id, owner_id, created_at, locked, name}
_disk_lock = asyncio.Lock()


# ==============================================================================
# PENGATURAN
# ==============================================================================
def get_config(guild_id: int) -> dict | None:
    data = temp_voice_guilds.get(int(guild_id))
    return dict(data) if data else None


def set_hub(
    guild_id: int,
    hub_id: int,
    *,
    enabled: bool = True,
    name_template: str | None = None,
    user_limit: int | None = None,
) -> dict | None:
    """Mengatur channel hub (pintu masuk pembuatan room)."""
    if not enabled:
        temp_voice_guilds.pop(int(guild_id), None)
        return None

    existing = temp_voice_guilds.get(int(guild_id)) or {}
    if name_template is None:
        template = str(existing.get("name_template") or DEFAULT_NAME_TEMPLATE)
    else:
        template = str(name_template)
    template = template.strip() or DEFAULT_NAME_TEMPLATE
    limit = existing.get("user_limit", 0) if user_limit is None else max(0, min(99, int(user_limit)))

    temp_voice_guilds[int(guild_id)] = {
        "enabled": True,
        "hub_id": int(hub_id),
        "name_template": template[:80],
        "user_limit": limit,
    }
    return dict(temp_voice_guilds[int(guild_id)])


def room_name_for(config: dict, member: discord.abc.User) -> str:
    """Nama room dari template (`{user}`, `{name}`, `{guild}`)."""
    template = str(config.get("name_template") or DEFAULT_NAME_TEMPLATE)
    display = getattr(member, "display_name", None) or getattr(member, "name", "Member")
    return (
        template.replace("{user}", display)
        .replace("{name}", display)
        .replace("{guild}", getattr(getattr(member, "guild", None), "name", ""))
    )[:100] or DEFAULT_NAME_TEMPLATE


def register_room(channel_id: int, guild_id: int, owner_id: int, name: str = "") -> dict:
    """Mendaftarkan room sementara yang baru dibuat."""
    room = {
        "guild_id": int(guild_id),
        "owner_id": int(owner_id),
        "created_at": time.time(),
        "locked": False,
        "name": str(name or "")[:100],
    }
    temp_rooms[int(channel_id)] = room
    return room


def get_room(channel_id: int) -> dict | None:
    return temp_rooms.get(int(channel_id))


def unregister_room(channel_id: int) -> bool:
    return temp_rooms.pop(int(channel_id), None) is not None


def is_owner(channel_id: int, user_id: int) -> bool:
    room = get_room(channel_id)
    return bool(room and int(room.get("owner_id", 0)) == int(user_id))


def rooms_of_guild(guild_id: int) -> dict[int, dict]:
    return {cid: room for cid, room in temp_rooms.items() if int(room.get("guild_id", 0)) == int(guild_id)}


def guild_room_count(guild_id: int) -> int:
    return len(rooms_of_guild(guild_id))


def set_room_locked(channel_id: int, locked: bool) -> bool:
    room = get_room(channel_id)
    if room is None:
        return False
    room["locked"] = bool(locked)
    return True


def set_room_name(channel_id: int, name: str) -> bool:
    room = get_room(channel_id)
    if room is None:
        return False
    room["name"] = str(name or "")[:100]
    return True


def cleanup_temp_voice_runtime(limit: int = 400) -> int:
    """Memangkas data room yang terlalu banyak di RAM (pertahanan Free Tier)."""
    removed = 0
    if len(temp_rooms) > limit:
        ordered = sorted(temp_rooms.items(), key=lambda item: float(item[1].get("created_at", 0)))
        for channel_id, _ in ordered[: len(temp_rooms) - limit]:
            temp_rooms.pop(channel_id, None)
            removed += 1
    return removed


# ==============================================================================
# PEMBUATAN & PENGHAPUSAN ROOM
# ==============================================================================
def _room_overwrites(guild: discord.Guild, owner: discord.Member) -> dict:
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
        owner: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            manage_channels=True,
            move_members=True,
            mute_members=True,
        ),
    }


async def create_room(
    guild: discord.Guild, member: discord.Member, config: dict
) -> discord.VoiceChannel | None:
    """Membuat room baru + memindahkan pemilik ke dalamnya."""
    if guild_room_count(guild.id) >= MAX_ROOMS_PER_GUILD:
        logger.info("Batas %d room sementara tercapai di guild %s.", MAX_ROOMS_PER_GUILD, guild.id)
        return None

    hub = guild.get_channel(int(config["hub_id"]))
    category = getattr(hub, "category", None)
    name = room_name_for(config, member)

    try:
        channel = await guild.create_voice_channel(
            name,
            category=category,
            user_limit=int(config.get("user_limit") or 0),
            overwrites=_room_overwrites(guild, member),
            reason="Temp Voice: room otomatis",
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal membuat room Temp Voice di %s: %s", guild.id, exc)
        return None

    register_room(channel.id, guild.id, member.id, name)
    try:
        await member.move_to(channel, reason="Temp Voice: pemilik room")
    except (discord.Forbidden, discord.HTTPException):
        pass

    # Pesan sambutan singkat di room (auto-hapus agar tidak menumpuk)
    try:
        import ui_theme

        await channel.send(
            embed=ui_theme.status_embed(
                guild.id,
                "info",
                f"Room milik {member.display_name}",
                "Kamu **pemilik** room ini. Atur lewat command berikut:\n"
                "• `/tempvoice kunci` — kunci/buka room\n"
                "• `/tempvoice nama` — ganti nama room\n"
                "• `/tempvoice limit` — batasi jumlah orang\n"
                "• `/tempvoice tendang` — keluarkan member\n\n"
                "_Room ini terhapus otomatis saat kosong._",
            ),
            delete_after=45,
        )
    except (discord.Forbidden, discord.HTTPException):
        pass
    return channel


async def delete_room(channel_id: int, guild: discord.Guild | None = None, reason: str = "Temp Voice: room kosong") -> bool:
    """Menghapus room sementara (beserta catatannya)."""
    if guild is not None:
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.VoiceChannel):
            try:
                await channel.delete(reason=reason)
            except (discord.Forbidden, discord.HTTPException):
                return False
    unregister_room(channel_id)
    return True


async def handle_voice_update(
    before: discord.VoiceState, after: discord.VoiceState, member: discord.Member
) -> None:
    """Logika inti: buat room saat masuk hub, hapus room saat kosong."""
    guild = member.guild
    config = get_config(guild.id)

    # 1. Baru masuk / pindah ke hub → buatkan room
    if config and config.get("enabled") and after.channel is not None:
        if int(after.channel.id) == int(config["hub_id"]) and before.channel != after.channel:
            if not getattr(member, "bot", False):
                await create_room(guild, member, config)

    # 2. Meninggalkan salah satu room sementara
    if before.channel is not None and before.channel.id != getattr(after.channel, "id", None):
        channel_id = int(before.channel.id)
        if get_room(channel_id) is not None:
            remaining = [m for m in getattr(before.channel, "members", []) or [] if not m.bot]
            # `before.channel.members` bisa masih memuat member yang baru keluar
            remaining = [m for m in remaining if m.id != member.id]
            if not remaining:
                await delete_room(channel_id, guild)
                await save_temp_voice_to_disk()


async def sweep_empty_rooms(bot) -> int:
    """Membersihkan room yatim (kosong / channel hilang) — dijalankan saat startup & tiap jam."""
    removed = 0
    for channel_id, room in list(temp_rooms.items()):
        guild = bot.get_guild(int(room.get("guild_id", 0)))
        if guild is None:
            unregister_room(channel_id)
            removed += 1
            continue
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            unregister_room(channel_id)
            removed += 1
            continue
        humans = [m for m in getattr(channel, "members", []) or [] if not m.bot]
        if not humans:
            if await delete_room(channel_id, guild, reason="Temp Voice: room kosong saat pembersihan"):
                removed += 1
    if removed:
        await save_temp_voice_to_disk()
    return removed


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_temp_voice_from_disk() -> tuple[int, int]:
    """Memuat pengaturan hub & daftar room dari data/temp_voice.json."""
    if not TEMP_VOICE_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(TEMP_VOICE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", TEMP_VOICE_FILE, exc)
        return 0, 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            if not data.get("enabled", True):
                continue
            temp_voice_guilds[int(gid_str)] = {
                "enabled": True,
                "hub_id": int(data["hub_id"]),
                "name_template": str(data.get("name_template") or DEFAULT_NAME_TEMPLATE)[:80],
                "user_limit": int(data.get("user_limit") or 0),
            }
        except (KeyError, TypeError, ValueError):
            continue

    for cid_str, room in (raw.get("rooms") or {}).items():
        try:
            temp_rooms[int(cid_str)] = {
                "guild_id": int(room["guild_id"]),
                "owner_id": int(room["owner_id"]),
                "created_at": float(room.get("created_at") or time.time()),
                "locked": bool(room.get("locked", False)),
                "name": str(room.get("name") or "")[:100],
            }
        except (KeyError, TypeError, ValueError):
            continue
    return len(temp_voice_guilds), len(temp_rooms)


async def save_temp_voice_to_disk() -> None:
    """Menyimpan pengaturan & daftar room secara atomik."""
    async with _disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(gid): data for gid, data in temp_voice_guilds.items()},
                "rooms": {
                    str(cid): {
                        "guild_id": room["guild_id"],
                        "owner_id": room["owner_id"],
                        "created_at": room["created_at"],
                        "locked": room.get("locked", False),
                        "name": room.get("name", ""),
                    }
                    for cid, room in temp_rooms.items()
                },
            }
            tmp = TEMP_VOICE_FILE.with_suffix(".json.tmp")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp.write_text, text, "utf-8")
            import os

            await asyncio.to_thread(os.replace, tmp, TEMP_VOICE_FILE)
        except Exception as exc:
            logger.warning("Gagal menyimpan temp_voice.json: %s", exc)


def sanitize_room_name(name: str) -> str:
    """Membersihkan nama room dari karakter aneh (tanpa mengubah emoji)."""
    cleaned = re.sub(r"\s+", " ", str(name or "")).strip()
    return cleaned[:100]
