"""Anti-Nuke — penjaga server dari penghancuran massal oleh staff/akun hack (**0 kuota AI**).

Cara kerja singkat
------------------
1. Discord mencatat **siapa melakukan apa** di *Audit Log*. Bot mendengarkan event
   `on_audit_log_entry_create` (butuh izin **View Audit Log**) — tanpa polling, jadi RAM & CPU tetap kecil.
2. Setiap aksi berisiko dihitung per pelaku dalam jendela waktu tertentu
   (mis. hapus channel, hapus role, ban massal, buat webhook, ubah identitas server).
3. Bila melewati ambang → **pelanggaran** dicatat, lalu ditindak sesuai pengaturan Admin:
   `lapor` (bawaan) → `cabut-role` → `timeout` → `kick` → `ban`.
4. **Pemulihan ringan** (opsional): kembalikan nama & ikon server serta hapus webhook buatan pelaku.

Yang selalu aman
----------------
- **Owner server, bot ini sendiri, & daftar whitelist (member/role) tidak pernah ditindak.**
- Bawaan **`lapor`**: tidak ada aksi otomatis sampai Admin menaikkannya sendiri.
- Tidak memakai AI sama sekali; data di `data/antinuke.json`.
"""

import asyncio
import datetime
import json
import logging
import os
import time
from pathlib import Path

import discord
import channel_targets

from config import ANTINUKE_FILE, DATA_DIR

logger = logging.getLogger("gemini_bot.antinuke")

_lock = asyncio.Lock()

# ------------------------------------------------------------------------------
# DEFINISI AKSI BERISIKO
# ------------------------------------------------------------------------------
ACTIONS: dict[str, dict] = {
    "channel_delete": {"label": "Hapus channel", "emoji": "🧨", "count": 3, "window": 60,
                       "audit": ("channel_delete",)},
    "channel_create": {"label": "Buat channel massal", "emoji": "🌊", "count": 8, "window": 60,
                       "audit": ("channel_create",)},
    "role_delete": {"label": "Hapus role", "emoji": "🎭", "count": 3, "window": 60,
                    "audit": ("role_delete",)},
    "ban": {"label": "Ban massal", "emoji": "🔨", "count": 5, "window": 60,
            "audit": ("ban", "member_ban_add")},
    "kick": {"label": "Kick massal", "emoji": "👢", "count": 5, "window": 60,
             "audit": ("kick", "member_kick")},
    "webhook_create": {"label": "Buat webhook", "emoji": "🪝", "count": 3, "window": 300,
                       "audit": ("webhook_create",)},
    "guild_update": {"label": "Ubah identitas server", "emoji": "🏷️", "count": 2, "window": 300,
                     "audit": ("guild_update",)},
    "member_role_update": {"label": "Cabut role massal", "emoji": "🧯", "count": 12, "window": 60,
                           "audit": ("member_role_update",)},
    # v1.35.0-beta: bot asing & role admin massal
    "bot_add": {"label": "Bot asing ditambahkan", "emoji": "🤖", "count": 1, "window": 60,
                "audit": ("bot_add",)},
    "role_create": {"label": "Buat role massal", "emoji": "🎨", "count": 4, "window": 60,
                    "audit": ("role_create",)},
}

PUNISH_CHOICES: dict[str, str] = {
    "lapor": "Lapor saja (tanpa tindakan otomatis)",
    "cabut-role": "Lapor + cabut role berbahaya pelaku",
    "timeout": "Lapor + timeout sementara",
    "kick": "Lapor + keluarkan (kick) dari server",
    "ban": "Lapor + ban dari server",
}

# Role yang dicabut saat mode `cabut-role` (hanya yang berbahaya)
DANGEROUS_PERMS = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members",
    "manage_messages",
)

# ------------------------------------------------------------------------------
# STATE
# ------------------------------------------------------------------------------
antinuke_guilds: dict[int, dict] = {}      # guild_id -> konfigurasi
_events: dict[str, list[float]] = {}       # "guild:user:action" -> [timestamp]
violations: dict[int, list[dict]] = {}     # guild_id -> riwayat pelanggaran (maks 20)
_recent_alerts: dict[str, float] = {}      # "guild:user" -> alert terakhir (anti spam laporan)


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_config() -> dict:
    return {
        "enabled": True,
        "log_channel_id": None,
        "dm_owner": True,
        "action": "lapor",
        "timeout_sec": 3600,
        "restore": True,
        "whitelist_users": [],
        "whitelist_roles": [],
        "thresholds": {key: {"count": spec["count"], "window": spec["window"]} for key, spec in ACTIONS.items()},
        "identity": {},          # {"name": str, "icon_url": str | None}
        # v1.35.0-beta: proteksi bot jahat & mode beku
        "freeze_aktif": False,
        "freeze_until": 0.0,
        "freeze_by": None,
        "auto_kick_bot": True,   # bot asing yang ditambahkan langsung dikeluarkan
        "freeze_count": 0,
    }


def get_config(guild_id: int) -> dict:
    gid = int(guild_id)
    cfg = antinuke_guilds.get(gid)
    if cfg is None:
        cfg = default_config()
        antinuke_guilds[gid] = cfg
    else:
        base = default_config()
        for key, value in base.items():
            cfg.setdefault(key, value)
        for key in ACTIONS:
            cfg["thresholds"].setdefault(key, base["thresholds"][key])
    return cfg


def is_enabled(guild_id: int) -> bool:
    cfg = antinuke_guilds.get(int(guild_id))
    return bool(cfg.get("enabled", True)) if cfg else True


def set_config(guild_id: int, **changes) -> dict:
    """Mengubah konfigurasi anti-nuke (hanya nilai yang dikirim)."""
    cfg = get_config(guild_id)
    for key in ("log_channel_id", "timeout_sec"):
        if key in changes and changes[key] is not None:
            cfg[key] = _to_int(changes[key])
    for key in ("enabled", "dm_owner", "restore", "auto_kick_bot"):
        if key in changes and changes[key] is not None:
            cfg[key] = bool(changes[key])
    if changes.get("action") in PUNISH_CHOICES:
        cfg["action"] = changes["action"]
    if isinstance(changes.get("thresholds"), dict):
        for key, value in changes["thresholds"].items():
            if key in ACTIONS and value:
                cfg["thresholds"][key]["count"] = max(1, _to_int(value))
    if isinstance(changes.get("window"), int) and changes["window"] > 0:
        for key in ACTIONS:
            cfg["thresholds"][key]["window"] = int(changes["window"])
    return cfg


def set_log_channel(guild_id: int, channel_id: int | None) -> dict:
    return set_config(guild_id, log_channel_id=_to_int(channel_id) or 0)


def handle_channel_delete(channel_id: int) -> int:
    cid = _to_int(channel_id)
    changed = 0
    for cfg in antinuke_guilds.values():
        if cfg.get("log_channel_id") == cid:
            cfg["log_channel_id"] = None
            changed += 1
    return changed


# ==============================================================================
# WHITELIST
# ==============================================================================
def add_whitelist(guild_id: int, *, user_id: int | None = None, role_id: int | None = None) -> bool:
    cfg = get_config(guild_id)
    if user_id:
        uid = _to_int(user_id)
        if uid in cfg["whitelist_users"]:
            return False
        cfg["whitelist_users"].append(uid)
        return True
    if role_id:
        rid = _to_int(role_id)
        if rid in cfg["whitelist_roles"]:
            return False
        cfg["whitelist_roles"].append(rid)
        return True
    return False


def remove_whitelist(guild_id: int, *, user_id: int | None = None, role_id: int | None = None) -> bool:
    cfg = get_config(guild_id)
    if user_id and _to_int(user_id) in cfg["whitelist_users"]:
        cfg["whitelist_users"].remove(_to_int(user_id))
        return True
    if role_id and _to_int(role_id) in cfg["whitelist_roles"]:
        cfg["whitelist_roles"].remove(_to_int(role_id))
        return True
    return False


def is_whitelisted(guild, member) -> bool:
    """Owner, bot sendiri, member whitelist, & pemegang role whitelist selalu aman."""
    if guild is None or member is None:
        return True
    cfg = get_config(getattr(guild, "id", 0))
    uid = _to_int(getattr(member, "id", 0))
    if uid and uid == _to_int(getattr(guild, "owner_id", 0)):
        return True
    me = getattr(guild, "me", None)
    if me is not None and uid == _to_int(getattr(me, "id", 0)):
        return True
    if uid in (cfg.get("whitelist_users") or []):
        return True
    roles = cfg.get("whitelist_roles") or []
    for role in getattr(member, "roles", []) or []:
        if _to_int(getattr(role, "id", 0)) in roles:
            return True
    return False


# ==============================================================================
# DETEKSI
# ==============================================================================
def classify(audit_action_name: str) -> str | None:
    """Memetakan nama `AuditLogAction` Discord ke kunci aksi internal."""
    name = str(audit_action_name or "").lower()
    for key, spec in ACTIONS.items():
        if name in spec["audit"]:
            return key
    return None


def thresholds(guild_id: int) -> dict[str, dict]:
    return get_config(guild_id)["thresholds"]


def reset_events() -> None:
    _events.clear()
    _recent_alerts.clear()


def register_event(guild_id: int, user_id: int, action_key: str, *, now: float | None = None) -> tuple[int, int]:
    """Mencatat satu kejadian; mengembalikan `(jumlah dalam jendela, ambang)`."""
    gid = int(guild_id)
    cfg = get_config(gid)
    spec = cfg["thresholds"].get(action_key) or ACTIONS[action_key]
    window = max(1, _to_int(spec.get("window"), 60))
    limit = max(1, _to_int(spec.get("count"), 3))
    now_ts = time.time() if now is None else float(now)

    key = f"{gid}:{int(user_id)}:{action_key}"
    stamps = [ts for ts in _events.get(key, []) if now_ts - ts <= window]
    stamps.append(now_ts)
    _events[key] = stamps
    return len(stamps), limit


def should_punish(guild_id: int, user_id: int, action_key: str, *, now: float | None = None) -> tuple[bool, int, int]:
    """`(melewati_ambang, jumlah, ambang)`. Saat mode beku, ambang menjadi **1 aksi**."""
    count, limit = register_event(guild_id, user_id, action_key, now=now)
    if is_frozen(guild_id, now=now):
        return True, count, 1
    return count >= limit, count, limit


# ==============================================================================
# MODE BEKU (FREEZE) — v1.35.0-beta
# ==============================================================================
FREEZE_MAX_MINUTES = 1440


def is_frozen(guild_id: int, *, now: float | None = None) -> bool:
    """Apakah server sedang dalam mode beku (setiap aksi destruktif langsung ditindak)."""
    cfg = antinuke_guilds.get(int(guild_id))
    if not cfg or not cfg.get("freeze_aktif"):
        return False
    current = time.time() if now is None else float(now)
    until = float(cfg.get("freeze_until") or 0)
    if until and current >= until:
        cfg["freeze_aktif"] = False
        cfg["freeze_until"] = 0.0
        return False
    return True


def freeze_remaining(guild_id: int, *, now: float | None = None) -> int:
    """Sisa detik mode beku (0 bila tidak aktif)."""
    cfg = antinuke_guilds.get(int(guild_id))
    if not cfg or not is_frozen(guild_id, now=now):
        return 0
    current = time.time() if now is None else float(now)
    return max(0, int(float(cfg.get("freeze_until") or 0) - current))


def start_freeze(guild_id: int, *, minutes: int = 30, by_id: int = 0, now: float | None = None) -> dict:
    """Membekukan server: SEMUA aksi destruktif langsung ditindak selama N menit."""
    cfg = get_config(guild_id)
    minutes = max(1, min(FREEZE_MAX_MINUTES, int(minutes)))
    current = time.time() if now is None else float(now)
    cfg["freeze_aktif"] = True
    cfg["freeze_until"] = current + minutes * 60
    cfg["freeze_by"] = int(by_id) or None
    cfg["freeze_count"] = _to_int(cfg.get("freeze_count")) + 1
    return cfg


def end_freeze(guild_id: int) -> bool:
    """Mencairkan server (mode normal kembali)."""
    cfg = antinuke_guilds.get(int(guild_id))
    if not cfg or not cfg.get("freeze_aktif"):
        return False
    cfg["freeze_aktif"] = False
    cfg["freeze_until"] = 0.0
    return True


def expired_freezes(*, now: float | None = None) -> list[int]:
    """Server yang mode bekunya sudah habis (untuk dipulihkan watcher)."""
    current = time.time() if now is None else float(now)
    done = []
    for gid, cfg in antinuke_guilds.items():
        if not cfg.get("freeze_aktif"):
            continue
        until = float(cfg.get("freeze_until") or 0)
        if until and current >= until:
            done.append(gid)
    return done


async def kick_foreign_bot(guild, target) -> str:
    """Mengeluarkan bot asing yang baru ditambahkan (bila masih ada di server)."""
    if target is None or not getattr(target, "bot", False):
        return "target bukan bot"
    try:
        await target.kick(reason="Anti-Nuke: bot asing ditambahkan tanpa izin")
    except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
        return f"gagal mengeluarkan bot (`{type(exc).__name__}`)"
    return f"bot `{getattr(target, 'name', '?')}` dikeluarkan dari server"


def record_violation(guild, member, action_key: str, count: int, limit: int, action_taken: str) -> dict:
    gid = _to_int(getattr(guild, "id", 0))
    entry = {
        "guild_id": gid,
        "user_id": _to_int(getattr(member, "id", 0)),
        "user_name": str(getattr(member, "name", "?")),
        "action": action_key,
        "label": ACTIONS[action_key]["label"],
        "count": int(count),
        "limit": int(limit),
        "taken": action_taken,
        "at": time.time(),
    }
    bucket = violations.setdefault(gid, [])
    bucket.insert(0, entry)
    del bucket[20:]
    return entry


def recent_violations(guild_id: int, limit: int = 5) -> list[dict]:
    return (violations.get(int(guild_id)) or [])[: max(1, int(limit))]


# ==============================================================================
# IDENTITAS SERVER (untuk pemulihan)
# ==============================================================================
def snapshot_identity(guild) -> dict:
    """Menyimpan nama & ikon server sebagai titik pulih."""
    gid = _to_int(getattr(guild, "id", 0))
    cfg = get_config(gid)
    icon = getattr(guild, "icon", None)
    cfg["identity"] = {
        "name": str(getattr(guild, "name", "")),
        "icon_url": str(getattr(icon, "url", "") or "") or None,
    }
    return cfg["identity"]


async def restore_identity(bot, guild, *, reason: str = "Anti-Nuke: pulihkan identitas server") -> tuple[bool, str]:
    """Mengembalikan nama & ikon server dari titik pulih terakhir."""
    cfg = get_config(_to_int(getattr(guild, "id", 0)))
    saved = cfg.get("identity") or {}
    name = str(saved.get("name") or "").strip()
    icon_url = saved.get("icon_url")
    if not name and not icon_url:
        return False, "Belum ada titik pulih identitas. Jalankan `/nuke status` sekali saat kondisi server normal."

    kwargs: dict = {}
    if name and str(getattr(guild, "name", "")) != name:
        kwargs["name"] = name[:100]

    if icon_url:
        data = None
        session = getattr(bot, "http_session", None)
        try:
            if session is not None:
                async with session.get(icon_url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.read()
        except Exception as exc:  # pragma: no cover - jaringan
            logger.debug("Gagal mengunduh ikon server: %s", exc)
        if data and len(data) <= 10 * 1024 * 1024:
            kwargs["icon"] = data

    if not kwargs:
        return False, "Nama & ikon server sudah sama dengan titik pulih."

    try:
        await guild.edit(**kwargs, reason=reason[:400])
    except (discord.Forbidden, discord.HTTPException) as exc:
        return False, f"Gagal memulihkan identitas: `{type(exc).__name__}`."
    return True, "Nama/ikon server dipulihkan."


# ==============================================================================
# TINDAKAN
# ==============================================================================
def _dangerous_roles(member) -> list:
    roles = []
    for role in getattr(member, "roles", []) or []:
        if getattr(role, "is_default", lambda: False)():
            continue
        perms = getattr(role, "permissions", None)
        if perms is not None and any(getattr(perms, name, False) for name in DANGEROUS_PERMS):
            roles.append(role)
    return roles


async def apply_action(guild, member, action: str, *, timeout_sec: int = 3600, reason: str = "Anti-Nuke") -> str:
    """Menjalankan tindakan ke pelaku. Mengembalikan ringkasan yang dilakukan."""
    if action not in PUNISH_CHOICES or action == "lapor":
        return "lapor saja (tanpa tindakan)"

    if action == "cabut-role":
        roles = _dangerous_roles(member)
        if not roles:
            return "cabut-role: tidak ada role berbahaya"
        try:
            await member.remove_roles(*roles, reason=reason[:400])
        except (discord.Forbidden, discord.HTTPException) as exc:
            return f"cabut-role gagal (`{type(exc).__name__}`)"
        return f"cabut-role: {len(roles)} role berbahaya dicabut"

    if action == "timeout":
        if not hasattr(member, "timeout"):
            return "timeout tidak didukung klien"
        duration = min(max(60, int(timeout_sec)), 28 * 86400)
        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
            await member.timeout(until, reason=reason[:400])
        except (discord.Forbidden, discord.HTTPException) as exc:
            return f"timeout gagal (`{type(exc).__name__}`)"
        return f"timeout {duration // 60} menit"

    if action == "kick":
        try:
            await member.kick(reason=reason[:400])
        except (discord.Forbidden, discord.HTTPException) as exc:
            return f"kick gagal (`{type(exc).__name__}`)"
        return "di-kick dari server"

    if action == "ban":
        try:
            await guild.ban(member, reason=reason[:400], delete_message_seconds=0)
        except (discord.Forbidden, discord.HTTPException) as exc:
            return f"ban gagal (`{type(exc).__name__}`)"
        return "di-ban dari server"

    return "tidak ada tindakan"


async def cleanup_offender_webhooks(guild, member) -> int:
    """Menghapus webhook yang dibuat pelaku (pemulihan ringan)."""
    removed = 0
    try:
        hooks = await guild.webhooks()
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return 0
    uid = _to_int(getattr(member, "id", 0))
    for hook in hooks:
        creator = getattr(hook, "user", None)
        if creator is not None and _to_int(getattr(creator, "id", 0)) == uid:
            try:
                await hook.delete(reason="Anti-Nuke: webhook buatan pelaku")
                removed += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
    return removed


def build_alert_embed(guild, member, violation: dict, taken: str, *, extras: list[str] | None = None) -> discord.Embed:
    """Embed laporan anti-nuke (tidak memakai AI)."""
    spec = ACTIONS.get(violation["action"], {})
    embed = discord.Embed(
        title=f"{spec.get('emoji', '🚨')} Anti-Nuke: {violation['label']} terdeteksi",
        description=(
            f"**Pelaku:** {getattr(member, 'mention', violation['user_name'])} "
            f"(`{violation['user_name']}` • `{violation['user_id']}`)\n"
            f"**Jumlah aksi:** `{violation['count']}` dalam jendela waktu "
            f"(ambang `{violation['limit']}`)\n"
            f"**Tindakan:** {taken}"
        ),
        color=discord.Color.red(),
    )
    if extras:
        embed.add_field(name="Pemulihan", value="\n".join(extras)[:1024], inline=False)
    embed.set_footer(text="Anti-Nuke • 0 kuota AI • periksa Audit Log server untuk bukti lengkap")
    return embed


async def _notify(bot, guild, cfg, embed: discord.Embed) -> None:
    ids = channel_targets.daftar(cfg, "log_channel_id")

    async def _kirim(channel):
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    if not await channel_targets.sebarkan(bot, ids, _kirim):
        sistem = getattr(guild, "system_channel", None)
        if sistem is not None:
            try:
                await _kirim(sistem)
            except (discord.Forbidden, discord.HTTPException):
                pass

    if not cfg.get("dm_owner", True):
        return
    try:
        owner = guild.owner or (await guild.fetch_member(guild.owner_id))
        if owner is not None:
            await owner.send(embed=embed)
    except Exception as exc:  # pragma: no cover - DM tertutup
        logger.debug("DM owner anti-nuke gagal: %s", exc)


# ==============================================================================
# ENTRY POINT (dipanggil dari event `on_audit_log_entry_create`)
# ==============================================================================
async def handle_audit_entry(bot, entry, *, now: float | None = None) -> dict | None:
    """Memproses satu entri audit log. Mengembalikan dict pelanggaran bila terdeteksi."""
    guild = getattr(entry, "guild", None)
    if guild is None:
        return None
    gid = _to_int(getattr(guild, "id", 0))
    if not gid or not is_enabled(gid):
        return None

    action_obj = getattr(entry, "action", None)
    action_key = classify(getattr(action_obj, "name", "") or str(action_obj or ""))
    if action_key is None:
        return None

    user = getattr(entry, "user", None)
    if user is None:
        return None
    me = getattr(guild, "me", None)
    if me is not None and _to_int(getattr(user, "id", 0)) == _to_int(getattr(me, "id", 0)):
        return None

    member = user
    if callable(getattr(guild, "get_member", None)):
        found = guild.get_member(_to_int(getattr(user, "id", 0)))
        if found is not None:
            member = found
    if is_whitelisted(guild, member):
        return None

    exceeded, count, limit = should_punish(gid, _to_int(getattr(user, "id", 0)), action_key, now=now)
    if not exceeded:
        return None

    cfg = get_config(gid)
    taken = await apply_action(
        guild,
        member,
        str(cfg.get("action") or "lapor"),
        timeout_sec=_to_int(cfg.get("timeout_sec"), 3600),
        reason=f"Anti-Nuke: {ACTIONS[action_key]['label']} berulang",
    )

    extras: list[str] = []
    frozen = is_frozen(gid, now=now)
    if frozen:
        extras.append("🧊 Mode **beku** aktif — tindakan langsung dijalankan tanpa menunggu ambang")
    if action_key == "bot_add":
        target = getattr(entry, "target", None)
        if cfg.get("auto_kick_bot", True):
            result = await kick_foreign_bot(guild, target)
            prefix = "⚠️ " if ("gagal" in result or "bukan bot" in result) else "✅ "
            extras.append(prefix + result)
        else:
            extras.append("⚠️ `auto_kick_bot` nonaktif — keluarkan bot itu manual bila tidak dikenal")
    if cfg.get("restore", True):
        if action_key == "guild_update":
            ok, message = await restore_identity(bot, guild)
            extras.append(("✅ " if ok else "⚠️ ") + message)
        elif action_key == "webhook_create":
            removed = await cleanup_offender_webhooks(guild, member)
            if removed:
                extras.append(f"✅ {removed} webhook buatan pelaku dihapus")

    violation = record_violation(guild, member, action_key, count, limit, taken)
    embed = build_alert_embed(guild, member, violation, taken, extras=extras)
    await _notify(bot, guild, cfg, embed)
    logger.warning(
        "Anti-Nuke di %s: %s melakukan %s (%d kali) → %s",
        getattr(guild, "name", gid),
        getattr(member, "name", "?"),
        ACTIONS[action_key]["label"],
        count,
        taken,
    )
    return violation


def simulate(guild_id: int, action_key: str, *, times: int | None = None) -> dict:
    """Uji kering: berapa kali sampai ambang tercapai (tanpa mengubah state)."""
    cfg = get_config(guild_id)
    spec = cfg["thresholds"].get(action_key) or ACTIONS.get(action_key, {})
    limit = max(1, _to_int(spec.get("count"), 3))
    window = max(1, _to_int(spec.get("window"), 60))
    return {
        "action": action_key,
        "label": ACTIONS.get(action_key, {}).get("label", action_key),
        "limit": limit,
        "window": window,
        "action_mode": cfg.get("action", "lapor"),
        "needed": times if times is not None else limit,
    }


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def load_antinuke_from_disk() -> int:
    antinuke_guilds.clear()
    violations.clear()
    reset_events()

    path = Path(ANTINUKE_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(data, dict):
            continue
        cfg = default_config()
        cfg["enabled"] = bool(data.get("enabled", True))
        cfg["log_channel_id"] = _to_int(data.get("log_channel_id")) or None
        cfg["dm_owner"] = bool(data.get("dm_owner", True))
        cfg["action"] = data.get("action") if data.get("action") in PUNISH_CHOICES else "lapor"
        cfg["timeout_sec"] = _to_int(data.get("timeout_sec"), 3600)
        cfg["restore"] = bool(data.get("restore", True))
        cfg["whitelist_users"] = [_to_int(uid) for uid in (data.get("whitelist_users") or []) if _to_int(uid)]
        cfg["whitelist_roles"] = [_to_int(rid) for rid in (data.get("whitelist_roles") or []) if _to_int(rid)]
        for key, value in (data.get("thresholds") or {}).items():
            if key in ACTIONS and isinstance(value, dict):
                cfg["thresholds"][key] = {
                    "count": max(1, _to_int(value.get("count"), ACTIONS[key]["count"])),
                    "window": max(1, _to_int(value.get("window"), ACTIONS[key]["window"])),
                }
        cfg["freeze_aktif"] = bool(data.get("freeze_aktif", False))
        cfg["freeze_until"] = float(data.get("freeze_until") or 0)
        cfg["freeze_by"] = _to_int(data.get("freeze_by")) or None
        cfg["auto_kick_bot"] = bool(data.get("auto_kick_bot", True))
        cfg["freeze_count"] = max(0, _to_int(data.get("freeze_count")))
        identity = data.get("identity") or {}
        if isinstance(identity, dict):
            cfg["identity"] = {
                "name": str(identity.get("name") or ""),
                "icon_url": str(identity.get("icon_url") or "") or None,
            }
        antinuke_guilds[gid] = cfg

    for gid_str, rows in (raw.get("violations") or {}).items():
        gid = _to_int(gid_str)
        if gid and isinstance(rows, list):
            violations[gid] = [row for row in rows if isinstance(row, dict)][:20]

    return len(antinuke_guilds)


async def save_antinuke_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(gid): cfg for gid, cfg in antinuke_guilds.items()},
                "violations": {str(gid): rows for gid, rows in violations.items() if rows},
            }
            tmp_file = Path(str(ANTINUKE_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, ANTINUKE_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan antinuke.json")


async def refresh_freezes(bot=None) -> int:
    """Mencairkan otomatis mode beku yang durasinya habis (& lapor bila mungkin)."""
    done = expired_freezes()
    for gid in done:
        cfg = antinuke_guilds.get(gid) or {}
        cfg["freeze_aktif"] = False
        cfg["freeze_until"] = 0.0
        guild = bot.get_guild(gid) if bot is not None and callable(getattr(bot, "get_guild", None)) else None
        if guild is None:
            continue
        embed = discord.Embed(
            title="🧊 Mode Beku Anti-Nuke Berakhir",
            description=(
                "Durasi beku selesai — server kembali ke ambang normal.\n"
                "Periksa riwayat pelanggaran lewat `/nuke status`."
            ),
            color=discord.Color.green(),
        )
        await _notify(bot, guild, cfg, embed)
    if done:
        await save_antinuke_to_disk()
    return len(done)


def cleanup_antinuke_runtime() -> int:
    """Membuang catatan kejadian & alert yang sudah kedaluwarsa (jaga RAM tetap kecil)."""
    now = time.time()
    max_window = max(_to_int(spec["window"], 300) for spec in ACTIONS.values()) * 2
    removed = 0
    for key, stamps in list(_events.items()):
        fresh = [ts for ts in stamps if now - ts <= max_window]
        if fresh:
            _events[key] = fresh
        else:
            _events.pop(key, None)
            removed += 1
    for key, ts in list(_recent_alerts.items()):
        if now - float(ts) > 3600:
            _recent_alerts.pop(key, None)
    return removed
