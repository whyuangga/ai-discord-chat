"""Audit Log ringan — catatan aktivitas server ke satu channel (**0 kuota AI**).

Tujuan: melengkapi moderasi bercatatan dengan **bukti aktivitas** yang biasanya
dicari dari bot all-in-one populer.

Yang dicatat (bisa dinyalakan/matikan per kategori):

| Kategori | Contoh isi |
| :--- | :--- |
| `pesan` | pesan dihapus, diedit (sebelum → sesudah), hapus massal |
| `member` | member join/keluar, perubahan nama panggilan |
| `role` | role diberikan/dicabut, role dibuat/dihapus/diubah namanya |
| `channel` | channel dibuat/dihapus |
| `voice` | masuk/keluar/pindah voice channel (default **mati** karena paling ramai) |

Prinsip:
1. **Default NONAKTIF** — baru jalan setelah Admin memasang `/log channel`.
2. **Tanpa AI** sama sekali; murni embed + data dari event Discord.
3. Konfigurasi saja yang disimpan (`data/audit.json`); isi log tidak disimpan ke disk
   supaya tetap hemat RAM & tidak menyimpan data pribadi.
4. Anti-banjir: pesan dari channel yang diabaikan tidak dicatat, dan isi pesan
   dipotong agar embed tidak melebihi batas Discord.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import discord

from config import AUDIT_FILE, DATA_DIR
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.audit_log")

_lock = asyncio.Lock()

CATEGORIES: dict[str, str] = {
    "pesan": "💬 Pesan (hapus/edit)",
    "member": "👤 Member (join/keluar/nama)",
    "role": "🎭 Role (diberi/dicabut/diubah)",
    "channel": "📁 Channel (dibuat/dihapus)",
    "voice": "🔊 Voice (masuk/keluar/pindah)",
}

MAX_LINES = 900          # batas aman panjang embed field
MAX_BULK_LIST = 8        # jumlah pesan yang dirinci saat hapus massal

# guild_id -> konfigurasi
audit_guilds: dict[int, dict] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_config() -> dict:
    return {
        "channel_id": None,
        "categories": {key: (key != "voice") for key in CATEGORIES},
        "ignore_channels": [],
    }


def _normalize(data: dict | None) -> dict:
    base = default_config()
    if not isinstance(data, dict):
        return base
    base["channel_id"] = _to_int(data.get("channel_id")) or None
    raw_cats = data.get("categories") or {}
    for key in CATEGORIES:
        if isinstance(raw_cats, dict) and key in raw_cats:
            base["categories"][key] = bool(raw_cats.get(key))
    base["ignore_channels"] = [
        _to_int(c) for c in (data.get("ignore_channels") or []) if _to_int(c)
    ]
    return base


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def get_config(guild_id: int) -> dict | None:
    """Konfigurasi log server (None bila belum pernah diatur)."""
    return audit_guilds.get(int(guild_id))


def is_enabled(guild_id: int) -> bool:
    cfg = audit_guilds.get(int(guild_id))
    return bool(cfg and cfg.get("channel_id"))


def set_log_channel(guild_id: int, channel_id: int | None) -> dict:
    """Memasang channel log (None/0 = mematikan audit log server)."""
    gid = int(guild_id)
    if not channel_id:
        audit_guilds.pop(gid, None)
        return default_config()
    cfg = _normalize(audit_guilds.get(gid))
    cfg["channel_id"] = int(channel_id)
    audit_guilds[gid] = cfg
    return cfg


def set_category(guild_id: int, category: str, enabled: bool) -> dict | None:
    """Menyalakan/mematikan satu kategori pencatatan."""
    key = str(category or "").strip().lower()
    if key not in CATEGORIES:
        return None
    gid = int(guild_id)
    cfg = _normalize(audit_guilds.get(gid))
    cfg["categories"][key] = bool(enabled)
    audit_guilds[gid] = cfg
    return cfg


def toggle_ignore_channel(guild_id: int, channel_id: int, *, ignore: bool = True) -> dict:
    """Menambah/menghapus channel dari daftar yang tidak dicatat."""
    gid = int(guild_id)
    cfg = _normalize(audit_guilds.get(gid))
    ignored = {int(c) for c in cfg["ignore_channels"]}
    if ignore:
        ignored.add(int(channel_id))
    else:
        ignored.discard(int(channel_id))
    cfg["ignore_channels"] = sorted(ignored)
    audit_guilds[gid] = cfg
    return cfg


def is_category_enabled(guild_id: int, category: str) -> bool:
    cfg = audit_guilds.get(int(guild_id))
    if not cfg or not cfg.get("channel_id"):
        return False
    return bool((cfg.get("categories") or {}).get(str(category)))


def is_channel_ignored(guild_id: int, channel_id: int) -> bool:
    cfg = audit_guilds.get(int(guild_id))
    if not cfg:
        return False
    return int(channel_id or 0) in {int(c) for c in (cfg.get("ignore_channels") or [])}


def handle_channel_delete(channel_id: int) -> bool:
    """Membersihkan channel log/abaikan yang sudah dihapus dari server."""
    cid = _to_int(channel_id)
    changed = False
    for cfg in audit_guilds.values():
        if cfg.get("channel_id") == cid:
            cfg["channel_id"] = None
            changed = True
        if cid in (cfg.get("ignore_channels") or []):
            cfg["ignore_channels"] = [c for c in cfg["ignore_channels"] if c != cid]
            changed = True
    for gid in [g for g, c in audit_guilds.items() if not c.get("channel_id")]:
        # konfigurasi tanpa channel log tidak perlu disimpan
        if not audit_guilds[gid].get("channel_id"):
            audit_guilds.pop(gid, None)
    return changed


# ==============================================================================
# PENULISAN LOG
# ==============================================================================
_COLOR_KIND = {
    "pesan": "warn",
    "member": "info",
    "role": "lock",
    "channel": "info",
    "voice": "info",
    "hapus": "error",
}


def _clip(text: str, limit: int = MAX_LINES) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def build_embed(
    category: str,
    title: str,
    description: str,
    *,
    fields: list[tuple[str, str]] | None = None,
    kind: str | None = None,
) -> discord.Embed:
    """Menyusun embed log (tanpa memanggil ui_theme agar tetap ringan)."""
    color = {
        "info": discord.Color.blurple(),
        "warn": discord.Color.orange(),
        "error": discord.Color.red(),
        "lock": discord.Color.dark_gold(),
        "ok": discord.Color.green(),
    }.get(kind or _COLOR_KIND.get(category, "info"), discord.Color.blurple())

    embed = discord.Embed(
        title=_clip(title, 250),
        description=_clip(description, 3800),
        color=color,
        timestamp=discord.utils.utcnow() if hasattr(discord, "utils") else None,
    )
    for name, value in (fields or [])[:6]:
        embed.add_field(name=_clip(name, 250), value=_clip(value, 1000) or "—", inline=True)
    embed.set_footer(text=f"Audit Log • {CATEGORIES.get(category, category)}")
    return embed


async def _resolve_channel(bot, guild, cfg: dict):
    channel_id = cfg.get("channel_id")
    if not channel_id:
        return None
    get_channel = getattr(bot, "get_channel", None)
    channel = get_channel(int(channel_id)) if callable(get_channel) else None
    if channel is None and guild is not None and callable(getattr(guild, "get_channel", None)):
        channel = guild.get_channel(int(channel_id))
    if channel is None and callable(getattr(bot, "fetch_channel", None)):
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except Exception:  # pragma: no cover - channel terhapus / tanpa izin
            channel = None
    return channel


async def log_event(
    bot,
    guild,
    category: str,
    title: str,
    description: str,
    *,
    fields: list[tuple[str, str]] | None = None,
    kind: str | None = None,
) -> bool:
    """Mengirim satu entri log. Mengembalikan True bila terkirim."""
    if guild is None:
        return False
    gid = _to_int(getattr(guild, "id", 0))
    if not gid or not is_category_enabled(gid, category):
        return False

    cfg = audit_guilds.get(gid) or {}
    try:
        channel = await _resolve_channel(bot, guild, cfg)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Log audit dilewati (%s): %s", category, exc)
        return False
    if channel is None:
        return False

    send = getattr(channel, "send", None)
    if not callable(send):
        return False

    try:
        await send(
            embed=build_embed(category, title, description, fields=fields, kind=kind),
            allowed_mentions=discord.AllowedMentions.none() if hasattr(discord, "AllowedMentions") else None,
        )
        return True
    except Exception as exc:  # pragma: no cover - izin kurang / rate limit
        logger.debug("Gagal mengirim log audit: %s", sanitize_error_message(exc))
        return False


# ==============================================================================
# HELPER PER EVENT
# ==============================================================================
def _author_label(obj) -> str:
    name = getattr(obj, "display_name", None) or getattr(obj, "name", None) or "?"
    uid = _to_int(getattr(obj, "id", 0))
    return f"**{name}** (`{uid}`)" if uid else f"**{name}**"


def _channel_label(channel) -> str:
    if channel is None:
        return "_tidak diketahui_"
    mention = getattr(channel, "mention", None)
    return mention or f"#{getattr(channel, 'name', 'channel')}"


async def log_message_delete(bot, message) -> bool:
    """Mencatat pesan yang dihapus (termasuk lampiran)."""
    guild = getattr(message, "guild", None)
    if guild is None:
        return False
    gid = _to_int(getattr(guild, "id", 0))
    channel_id = _to_int(getattr(getattr(message, "channel", None), "id", 0))
    if is_channel_ignored(gid, channel_id):
        return False
    if getattr(getattr(message, "author", None), "bot", False):
        return False

    content = _clip(getattr(message, "content", "") or "")
    attachments = getattr(message, "attachments", None) or []
    fields = [("Channel", _channel_label(getattr(message, "channel", None)))]
    if attachments:
        fields.append(("Lampiran", ", ".join(str(getattr(a, "filename", "file")) for a in attachments[:5])))
    jump = getattr(message, "jump_url", None)
    if jump:
        fields.append(("Tautan", jump))

    return await log_event(
        bot,
        guild,
        "pesan",
        "🗑️ Pesan dihapus",
        f"{_author_label(getattr(message, 'author', None))}: {content or '_(tanpa teks)_'}",
        fields=fields,
        kind="error",
    )


async def log_message_edit(bot, before, after) -> bool:
    """Mencatat pesan yang diedit (hanya bila isinya benar-benar berubah)."""
    guild = getattr(after, "guild", None)
    if guild is None:
        return False
    gid = _to_int(getattr(guild, "id", 0))
    channel_id = _to_int(getattr(getattr(after, "channel", None), "id", 0))
    if is_channel_ignored(gid, channel_id):
        return False
    if getattr(getattr(after, "author", None), "bot", False):
        return False

    old = str(getattr(before, "content", "") or "")
    new = str(getattr(after, "content", "") or "")
    if old == new:
        return False

    description = (
        f"{_author_label(getattr(after, 'author', None))} di "
        f"{_channel_label(getattr(after, 'channel', None))}\n\n"
        f"**Sebelum:** {_clip(old) or '_(kosong)_'}\n"
        f"**Sesudah:** {_clip(new) or '_(kosong)_'}"
    )
    fields = []
    jump = getattr(after, "jump_url", None)
    if jump:
        fields.append(("Tautan", jump))
    return await log_event(bot, guild, "pesan", "✏️ Pesan diedit", description, fields=fields, kind="warn")


async def log_bulk_delete(bot, messages) -> bool:
    """Mencatat hapus massal (mis. purge atau aksi moderator Discord)."""
    items = list(messages or [])
    if not items:
        return False
    guild = getattr(items[0], "guild", None)
    if guild is None:
        return False
    gid = _to_int(getattr(guild, "id", 0))
    channel_id = _to_int(getattr(getattr(items[0], "channel", None), "id", 0))
    if is_channel_ignored(gid, channel_id):
        return False

    sample = []
    for msg in items[:MAX_BULK_LIST]:
        author = getattr(getattr(msg, "author", None), "display_name", "?")
        text = _clip(getattr(msg, "content", "") or "", 90) or "_(tanpa teks)_"
        sample.append(f"• **{author}**: {text}")

    return await log_event(
        bot,
        guild,
        "pesan",
        f"🧹 Hapus massal — {len(items)} pesan",
        f"Channel: {_channel_label(getattr(items[0], 'channel', None))}",
        fields=[("Contoh pesan", "\n".join(sample) or "—")],
        kind="error",
    )


async def log_member_join(bot, member) -> bool:
    """Mencatat member baru bergabung (umur akun membantu mendeteksi akun bot)."""
    guild = getattr(member, "guild", None)
    if guild is None:
        return False
    created = getattr(member, "created_at", None)
    age_days = None
    if created is not None:
        try:
            age_days = max(0, int((discord.utils.utcnow() - created).total_seconds() // 86400))
        except Exception:  # pragma: no cover - objek tiruan
            age_days = None
    fields = []
    if age_days is not None:
        fields.append(("Umur akun", f"`{age_days}` hari" + (" ⚠️ akun baru" if age_days < 7 else "")))
    count = getattr(guild, "member_count", None)
    if count:
        fields.append(("Total member", f"`{count}`"))
    return await log_event(
        bot,
        guild,
        "member",
        "📥 Member bergabung",
        f"{_author_label(member)} baru masuk ke server.",
        fields=fields,
        kind="ok",
    )


async def log_member_remove(bot, member) -> bool:
    """Mencatat member keluar (termasuk lama berada di server)."""
    guild = getattr(member, "guild", None)
    if guild is None:
        return False
    joined = getattr(member, "joined_at", None)
    fields = []
    if joined is not None:
        try:
            days = max(0, int((discord.utils.utcnow() - joined).total_seconds() // 86400))
            fields.append(("Lama di server", f"`{days}` hari"))
        except Exception:  # pragma: no cover
            pass
    roles = [r for r in (getattr(member, "roles", None) or []) if getattr(r, "name", None)]
    if roles:
        fields.append(("Role", f"`{max(0, len(roles) - 1)}` role"))
    return await log_event(
        bot,
        guild,
        "member",
        "📤 Member keluar",
        f"{_author_label(member)} meninggalkan server.",
        fields=fields,
        kind="warn",
    )


async def log_member_update(bot, before, after) -> bool:
    """Mencatat perubahan nama panggilan & role member."""
    guild = getattr(after, "guild", None)
    if guild is None:
        return False

    sent = False
    old_nick = getattr(before, "nick", None)
    new_nick = getattr(after, "nick", None)
    if old_nick != new_nick:
        display = getattr(after, "display_name", "?")
        sent |= await log_event(
            bot,
            guild,
            "member",
            "📝 Nama panggilan diubah",
            f"**{display}** (`{_to_int(getattr(after, 'id', 0))}`)\n"
            f"**Sebelum:** {old_nick or '_(tanpa nickname)_'}\n"
            f"**Sesudah:** {new_nick or '_(tanpa nickname)_'}",
            kind="info",
        )

    before_roles = {_to_int(getattr(r, "id", 0)) for r in (getattr(before, "roles", None) or [])}
    after_roles = {_to_int(getattr(r, "id", 0)) for r in (getattr(after, "roles", None) or [])}
    added = after_roles - before_roles
    removed = before_roles - after_roles
    if added or removed:
        lines = []
        if added:
            lines.append("**Diberikan:** " + ", ".join(f"<@&{rid}>" for rid in sorted(added)))
        if removed:
            lines.append("**Dicabut:** " + ", ".join(f"<@&{rid}>" for rid in sorted(removed)))
        sent |= await log_event(
            bot,
            guild,
            "role",
            "🎭 Role member berubah",
            f"{_author_label(after)}\n" + "\n".join(lines),
            kind="lock",
        )
    return sent


async def log_role_change(bot, guild, action: str, role) -> bool:
    """Mencatat role dibuat/dihapus."""
    name = getattr(role, "name", "?")
    rid = _to_int(getattr(role, "id", 0))
    title = {"create": "➕ Role dibuat", "delete": "➖ Role dihapus"}.get(action, "🎭 Role diubah")
    return await log_event(
        bot,
        guild,
        "role",
        title,
        f"**{name}** (`{rid}`)",
        kind="lock",
    )


async def log_channel_change(bot, guild, action: str, channel) -> bool:
    """Mencatat channel dibuat/dihapus."""
    name = getattr(channel, "name", "?")
    cid = _to_int(getattr(channel, "id", 0))
    title = {"create": "➕ Channel dibuat", "delete": "➖ Channel dihapus"}.get(action, "📁 Channel diubah")
    kind = "ok" if action == "create" else "warn"
    return await log_event(
        bot,
        guild,
        "channel",
        title,
        f"**#{name}** (`{cid}`)",
        kind=kind,
    )


async def log_voice_change(bot, member, before, after) -> bool:
    """Mencatat perpindahan voice channel (default NONAKTIF karena paling ramai)."""
    guild = getattr(member, "guild", None)
    if guild is None:
        return False
    before_ch = getattr(before, "channel", None)
    after_ch = getattr(after, "channel", None)
    if getattr(before_ch, "id", 0) == getattr(after_ch, "id", 0):
        return False

    if after_ch is None:
        title, detail = "🔇 Keluar voice", f"{_author_label(member)} keluar dari {_channel_label(before_ch)}"
        kind = "warn"
    elif before_ch is None:
        title, detail = "🔊 Masuk voice", f"{_author_label(member)} masuk ke {_channel_label(after_ch)}"
        kind = "ok"
    else:
        title = "🔀 Pindah voice"
        detail = (
            f"{_author_label(member)} pindah dari {_channel_label(before_ch)} "
            f"ke {_channel_label(after_ch)}"
        )
        kind = "info"
    return await log_event(bot, guild, "voice", title, detail, kind=kind)


# ==============================================================================
# SIMPAN / MUAT
# ==============================================================================
def load_audit_from_disk() -> int:
    """Memuat konfigurasi audit log dari `data/audit.json`."""
    audit_guilds.clear()
    path = Path(AUDIT_FILE)
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
        cfg = _normalize(data)
        if not cfg.get("channel_id"):
            continue
        audit_guilds[gid] = cfg
        loaded += 1
    return loaded


async def save_audit_to_disk() -> None:
    """Menyimpan konfigurasi audit log secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(gid): cfg for gid, cfg in audit_guilds.items()}}
            tmp_file = Path(str(AUDIT_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, AUDIT_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan audit.json: %s", sanitize_error_message(exc))


def cleanup_audit_runtime(max_guilds: int = 200) -> int:
    """Membuang konfigurasi tanpa channel log agar RAM tetap kecil."""
    removed = 0
    for gid, cfg in list(audit_guilds.items()):
        if not cfg.get("channel_id"):
            audit_guilds.pop(gid, None)
            removed += 1
    while len(audit_guilds) > max_guilds:
        audit_guilds.pop(next(iter(audit_guilds)))
        removed += 1
    return removed


def build_status_embed(guild_id: int) -> discord.Embed:
    """Ringkasan konfigurasi audit log (dipakai `/log status`)."""
    cfg = audit_guilds.get(int(guild_id))
    embed = discord.Embed(title="📋 Audit Log Server", color=discord.Color.blurple())
    if not cfg or not cfg.get("channel_id"):
        embed.description = (
            "**Nonaktif.** Pasang dengan `/log channel channel:#bot-log`.\n"
            "Setelah aktif, bot mencatat pesan dihapus/diedit, member join/keluar, "
            "perubahan role, dan channel baru."
        )
        return embed

    embed.description = f"**Channel log:** <#{cfg['channel_id']}>"
    cats = cfg.get("categories") or {}
    embed.add_field(
        name="Kategori aktif",
        value="\n".join(
            f"{'✅' if cats.get(key) else '⛔'} {label}" for key, label in CATEGORIES.items()
        )[:1000],
        inline=False,
    )
    ignored = cfg.get("ignore_channels") or []
    embed.add_field(
        name="Channel diabaikan",
        value=", ".join(f"<#{cid}>" for cid in ignored[:12]) or "_tidak ada_",
        inline=False,
    )
    embed.set_footer(text="0 kuota AI • isi log tidak disimpan ke disk")
    return embed
