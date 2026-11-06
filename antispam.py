"""Penjaga anti-spam & anti-raid ringan (Tier 2B) — **0 kuota Gemini**.

Prinsip utama: **tidak pernah mengganggu obrolan wajar**. Karena itu:

1. Mode default adalah **`lapor`** (hanya mencatat ke channel log, tidak menghapus apa pun).
   Admin harus memilih sendiri mode `hapus` atau `timeout` bila sudah yakin.
2. Admin, pengurus server (Manage Messages), bot, & role yang dikecualikan **selalu diabaikan**.
3. Setiap member hanya memicu **satu peringatan per 2 menit** agar channel log tidak dibanjiri.
4. Deteksi berjalan lokal tanpa API: banjir pesan, pesan berulang, mention massal,
   link beruntun, HURUF KAPITAL berlebihan (opsional), dan lonjakan member join (raid).

Data disimpan di `data/antispam.json`.
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import discord
import channel_targets

from config import (
    ANTISPAM_FILE,
    DATA_DIR,
    SPAM_CAPS_MIN_LENGTH,
    SPAM_FLOOD_COUNT,
    SPAM_FLOOD_WINDOW_SEC,
    SPAM_MENTION_LIMIT,
    SPAM_LINK_LIMIT,
    SPAM_RAID_JOIN_COUNT,
    SPAM_RAID_WINDOW_SEC,
    SPAM_TIMEOUT_SEC,
)
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.antispam")

_lock = asyncio.Lock()

SPAM_MODES: dict[str, str] = {
    "lapor": "👀 Lapor ke log saja (aman, tanpa tindakan)",
    "hapus": "🧹 Hapus pesan + catat ke log",
    "timeout": "⏳ Hapus + time-out member sementara",
}
SPAM_REASONS: dict[str, str] = {
    "flood": "🌊 Banjir pesan (flood)",
    "duplikat": "🔁 Pesan berulang",
    "mention": "📣 Mention massal",
    "link": "🔗 Link beruntun",
    "caps": "🔠 Huruf kapital berlebihan",
}

# ==============================================================================
# STATE RUNTIME
# ==============================================================================
spam_guilds: dict[int, dict] = {}          # guild_id -> konfigurasi penjaga spam
_recent_messages: dict[tuple[int, int, int], list[float]] = {}
_recent_texts: dict[tuple[int, int, int], list[tuple[float, str]]] = {}
_recent_links: dict[tuple[int, int], list[tuple[float, str]]] = {}
_recent_joins: dict[int, list[tuple[float, int]]] = {}
_last_alert: dict[tuple[int, int], float] = {}

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
ALERT_COOLDOWN_SEC = 120.0


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_config() -> dict:
    """Konfigurasi awal penjaga spam (mode paling aman: hanya lapor)."""
    return {
        "enabled": True,
        "mode": "lapor",
        "log_channel_id": None,
        "flood_count": int(SPAM_FLOOD_COUNT),
        "flood_window": int(SPAM_FLOOD_WINDOW_SEC),
        "mention_limit": int(SPAM_MENTION_LIMIT),
        "link_limit": int(SPAM_LINK_LIMIT),
        "duplicate_count": 3,
        "duplicate_window": 30,
        "caps_enabled": False,
        "caps_min_length": int(SPAM_CAPS_MIN_LENGTH),
        "timeout_sec": int(SPAM_TIMEOUT_SEC),
        "exempt_roles": [],
        "exempt_channels": [],
        "blocked": 0,
    }


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def load_antispam_from_disk() -> int:
    """Memuat konfigurasi penjaga spam semua server."""
    spam_guilds.clear()
    if not ANTISPAM_FILE.exists():
        return 0
    try:
        raw = json.loads(ANTISPAM_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", ANTISPAM_FILE, exc)
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
                "mode": str(data.get("mode") or "lapor")
                if str(data.get("mode") or "lapor") in SPAM_MODES
                else "lapor",
                "log_channel_id": _to_int(data.get("log_channel_id")) or None,
                "flood_count": max(3, _to_int(data.get("flood_count"), base["flood_count"])),
                "flood_window": max(3, _to_int(data.get("flood_window"), base["flood_window"])),
                "mention_limit": max(2, _to_int(data.get("mention_limit"), base["mention_limit"])),
                "link_limit": max(1, _to_int(data.get("link_limit"), base["link_limit"])),
                "duplicate_count": max(2, _to_int(data.get("duplicate_count"), 3)),
                "duplicate_window": max(5, _to_int(data.get("duplicate_window"), 30)),
                "caps_enabled": bool(data.get("caps_enabled", False)),
                "caps_min_length": max(8, _to_int(data.get("caps_min_length"), base["caps_min_length"])),
                "timeout_sec": max(60, min(86400, _to_int(data.get("timeout_sec"), base["timeout_sec"]))),
                "exempt_roles": [_to_int(r) for r in (data.get("exempt_roles") or []) if _to_int(r)],
                "exempt_channels": [_to_int(c) for c in (data.get("exempt_channels") or []) if _to_int(c)],
                "blocked": max(0, _to_int(data.get("blocked"))),
            }
        )
        spam_guilds[gid] = base
    return len(spam_guilds)


async def save_antispam_to_disk() -> None:
    """Menyimpan konfigurasi penjaga spam secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(k): v for k, v in spam_guilds.items()}}
            tmp_file = Path(str(ANTISPAM_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, ANTISPAM_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan antispam.json: %s", sanitize_error_message(exc))


# ==============================================================================
# KONFIGURASI PER SERVER
# ==============================================================================
def get_spam_config(guild_id: int) -> dict:
    cfg = spam_guilds.get(int(guild_id))
    if cfg is None:
        cfg = default_config()
        spam_guilds[int(guild_id)] = cfg
    return cfg


def is_spam_guard_active(guild_id: int) -> bool:
    cfg = spam_guilds.get(int(guild_id))
    return bool(cfg and cfg.get("enabled"))


def set_spam_config(guild_id: int, **changes) -> dict | None:
    """Mengubah konfigurasi penjaga spam. `aktif=False` mematikan penjaga."""
    if changes.get("aktif") is False or changes.get("enabled") is False:
        spam_guilds.pop(int(guild_id), None)
        _clear_runtime_guild(int(guild_id))
        return None

    cfg = get_spam_config(guild_id)
    cfg["enabled"] = True

    mode = changes.get("mode")
    if mode in SPAM_MODES:
        cfg["mode"] = str(mode)
    log_channel = changes.get("log_channel_id")
    if log_channel is not None:
        cfg["log_channel_id"] = int(log_channel) if int(log_channel) else None
    for key in ("flood_count", "flood_window", "mention_limit", "link_limit", "duplicate_count",
                "duplicate_window", "caps_min_length", "timeout_sec"):
        if changes.get(key) is not None:
            cfg[key] = max(1, int(changes[key]))
    if changes.get("caps_enabled") is not None:
        cfg["caps_enabled"] = bool(changes["caps_enabled"])
    if changes.get("exempt_roles") is not None:
        cfg["exempt_roles"] = [int(r) for r in changes["exempt_roles"]]
    if changes.get("exempt_channels") is not None:
        cfg["exempt_channels"] = [int(c) for c in changes["exempt_channels"]]
    return cfg


def _clear_runtime_guild(guild_id: int) -> None:
    gid = int(guild_id)
    for store in (_recent_messages, _recent_texts):
        for key in [k for k in store if k[0] == gid]:
            store.pop(key, None)
    for key in [k for k in _recent_links if k[0] == gid]:
        _recent_links.pop(key, None)
    for key in [k for k in _last_alert if k[0] == gid]:
        _last_alert.pop(key, None)
    _recent_joins.pop(gid, None)


def handle_channel_delete(channel) -> bool:
    """Membuang channel yang dihapus dari daftar pengecualian/log."""
    cid = _to_int(getattr(channel, "id", 0))
    changed = False
    for cfg in spam_guilds.values():
        if cfg.get("log_channel_id") == cid:
            cfg["log_channel_id"] = None
            changed = True
        if cid in (cfg.get("exempt_channels") or []):
            cfg["exempt_channels"] = [c for c in cfg["exempt_channels"] if c != cid]
            changed = True
    return changed


# ==============================================================================
# DETEKSI
# ==============================================================================
def normalize_text(text: str) -> str:
    """Merapikan teks untuk perbandingan pesan berulang."""
    lowered = str(text or "").lower()
    lowered = re.sub(r"(?i)https?://\S+", "<link>", lowered)
    return re.sub(r"\s+", " ", lowered).strip(" !?.,~")


def extract_links(text: str) -> list[str]:
    return [m.rstrip(".,;:!?\")]>}").lower() for m in _URL_RE.findall(str(text or ""))]


def caps_ratio(text: str) -> float:
    """Rasio huruf kapital terhadap seluruh huruf pada teks."""
    letters = [ch for ch in str(text or "") if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ch.isupper()) / len(letters)


def is_exempt(message, cfg: dict) -> bool:
    """Admin, pengurus, bot, role & channel pengecualian tidak pernah ditindak."""
    author = getattr(message, "author", None)
    if author is None:
        return True
    if getattr(author, "bot", False):
        return True
    perms = getattr(author, "guild_permissions", None)
    if perms is not None and (
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_messages", False)
        or getattr(perms, "manage_guild", False)
    ):
        return True
    member_roles = {_to_int(getattr(role, "id", 0)) for role in (getattr(author, "roles", None) or [])}
    if member_roles & {int(r) for r in (cfg.get("exempt_roles") or [])}:
        return True
    cid = _to_int(getattr(getattr(message, "channel", None), "id", 0))
    if cid in {int(c) for c in (cfg.get("exempt_channels") or [])}:
        return True
    return False


def _prune(values: list, now: float, window: float) -> list:
    cutoff = now - window
    return [item for item in values if (item[0] if isinstance(item, tuple) else item) >= cutoff]


def detect_spam(message, *, now: float | None = None) -> dict | None:
    """Memeriksa satu pesan & mencatat riwayatnya. `None` berarti pesan wajar.

    Mengembalikan `{"reason", "label", "count", "detail"}` bila terdeteksi.
    """
    guild = getattr(message, "guild", None)
    channel = getattr(message, "channel", None)
    author = getattr(message, "author", None)
    if guild is None or channel is None or author is None:
        return None

    gid = _to_int(getattr(guild, "id", 0))
    cfg = spam_guilds.get(gid)
    if not cfg or not cfg.get("enabled") or is_exempt(message, cfg):
        return None

    current = time.time() if now is None else float(now)
    uid = _to_int(getattr(author, "id", 0))
    cid = _to_int(getattr(channel, "id", 0))
    content = str(getattr(message, "content", "") or "")
    key = (gid, uid, cid)

    # 1. Mention massal (paling jelas & paling cepat dikenali)
    mentions = len(getattr(message, "mentions", None) or [])
    mention_limit = int(cfg.get("mention_limit") or SPAM_MENTION_LIMIT)
    if mentions >= mention_limit:
        return {
            "reason": "mention",
            "label": SPAM_REASONS["mention"],
            "count": mentions,
            "detail": f"`{mentions}` mention dalam satu pesan (batas `{mention_limit}`).",
        }

    # 2. Link beruntun (banyak link sekaligus atau link sama berulang)
    links = extract_links(content)
    link_limit = int(cfg.get("link_limit") or SPAM_LINK_LIMIT)
    link_store = _recent_links.setdefault((gid, uid), [])
    link_store[:] = _prune(link_store, current, 60.0)
    for link in links:
        link_store.append((current, link))
    repeated_link = None
    for link in set(links):
        if sum(1 for ts, item in link_store if item == link) >= 3:
            repeated_link = link
            break
    if len(links) >= link_limit or repeated_link:
        return {
            "reason": "link",
            "label": SPAM_REASONS["link"],
            "count": len(links) if not repeated_link else 3,
            "detail": (
                f"`{len(links)}` link dalam satu pesan (batas `{link_limit}`)."
                if not repeated_link
                else f"Link yang sama dikirim berulang: `{str(repeated_link)[:120]}`."
            ),
        }

    # 3. Banjir pesan (flood)
    flood_store = _recent_messages.setdefault(key, [])
    flood_store[:] = _prune(flood_store, current, float(cfg.get("flood_window") or 10))
    flood_store.append(current)
    flood_count = int(cfg.get("flood_count") or SPAM_FLOOD_COUNT)
    if len(flood_store) >= flood_count:
        window = int(cfg.get("flood_window") or 10)
        return {
            "reason": "flood",
            "label": SPAM_REASONS["flood"],
            "count": len(flood_store),
            "detail": f"`{len(flood_store)}` pesan dalam `{window}` detik (batas `{flood_count}`).",
        }

    # 4. Pesan berulang (isi sama, mis. copy-paste spam)
    normalized = normalize_text(content)
    text_store = _recent_texts.setdefault(key, [])
    text_store[:] = _prune(text_store, current, float(cfg.get("duplicate_window") or 30))
    if normalized and len(normalized) >= 4:
        text_store.append((current, normalized))
        duplicate_count = int(cfg.get("duplicate_count") or 3)
        same = sum(1 for _, text in text_store if text == normalized)
        if same >= duplicate_count:
            return {
                "reason": "duplikat",
                "label": SPAM_REASONS["duplikat"],
                "count": same,
                "detail": f"Pesan yang sama dikirim `{same}` kali (batas `{duplicate_count}`).",
            }

    # 5. Huruf kapital berlebihan (opsional, default NONAKTIF)
    if cfg.get("caps_enabled"):
        min_len = int(cfg.get("caps_min_length") or SPAM_CAPS_MIN_LENGTH)
        ratio = caps_ratio(content)
        if len(content) >= min_len and ratio >= 0.7:
            return {
                "reason": "caps",
                "label": SPAM_REASONS["caps"],
                "count": int(ratio * 100),
                "detail": f"`{int(ratio * 100)}%` huruf kapital pada `{len(content)}` karakter.",
            }

    return None


# ==============================================================================
# TINDAKAN & LAPORAN
# ==============================================================================
def build_spam_alert_embed(
    guild,
    author,
    channel,
    violation: dict,
    *,
    cfg: dict,
    acted: str,
    content: str = "",
) -> discord.Embed:
    """Embed laporan untuk channel log moderasi."""
    mode_label = SPAM_MODES.get(cfg.get("mode", "lapor"), SPAM_MODES["lapor"])
    embed = discord.Embed(
        title=f"🛡️ Anti-Spam — {violation.get('label', 'Terdeteksi')}",
        color=discord.Color.red() if acted in ("hapus", "timeout") else discord.Color.orange(),
    )
    user_id = _to_int(getattr(author, "id", 0))
    channel_id = _to_int(getattr(channel, "id", 0))
    embed.add_field(name="👤 Pelaku", value=f"<@{user_id}> (`{user_id}`)", inline=True)
    channel_text = f"<#{channel_id}>" if channel_id else "_tidak diketahui_"
    embed.add_field(name="📍 Channel", value=channel_text, inline=True)
    embed.add_field(name="🔍 Pemicu", value=str(violation.get("label", "-"))[:100], inline=True)
    embed.add_field(name="📊 Detail", value=str(violation.get("detail", "-"))[:300], inline=False)
    if content:
        embed.add_field(name="💬 Isi Pesan", value=f"```{content[:400]}```", inline=False)
    embed.add_field(
        name="⚙️ Mode Server",
        value=f"{mode_label}\n• **Tindakan dijalankan:** `{acted}`",
        inline=False,
    )
    footer = "Mode aman: hanya lapor" if cfg.get("mode", "lapor") == "lapor" else "Tindakan otomatis aktif"
    embed.set_footer(text=f"{footer} • atur dengan /keamanan spam")
    return embed


async def _notify(bot, cfg: dict, guild, embed: discord.Embed) -> bool:
    """Mengirim laporan ke channel log moderasi (bila diatur)."""
    ids = channel_targets.daftar(cfg, "log_channel_id")
    if not ids:
        return False

    async def _kirim(channel):
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    return bool(await channel_targets.sebarkan(bot, ids, _kirim))


async def handle_spam_guard(message, *, bot=None, now: float | None = None) -> bool:
    """Memeriksa & menindak satu pesan. `True` bila pesan sudah dihapus/di-timeout."""
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    if guild is None or author is None or channel is None:
        return False

    violation = detect_spam(message, now=now)
    if violation is None:
        return False

    gid = _to_int(guild.id)
    uid = _to_int(getattr(author, "id", 0))
    cfg = spam_guilds.get(gid) or default_config()
    mode = str(cfg.get("mode") or "lapor")
    current = time.time() if now is None else float(now)

    acted = "lapor"
    deleted = False
    timed_out = False

    if mode in ("hapus", "timeout"):
        delete = getattr(message, "delete", None)
        if callable(delete):
            try:
                await delete()
                deleted = True
                acted = "hapus"
            except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
                logger.warning("Gagal menghapus pesan spam: %s", sanitize_error_message(exc))

    if mode == "timeout":
        timeout = getattr(author, "timeout", None)
        if callable(timeout):
            import datetime as _dt

            seconds = int(cfg.get("timeout_sec") or SPAM_TIMEOUT_SEC)
            try:
                await timeout(_dt.timedelta(seconds=seconds), reason="Anti-spam otomatis")
                timed_out = True
                acted = "timeout"
            except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
                logger.warning("Gagal time-out member spam: %s", sanitize_error_message(exc))

    cfg["blocked"] = int(cfg.get("blocked") or 0) + 1

    # Satu laporan per member per 2 menit supaya log tidak dibanjiri
    alert_key = (gid, uid)
    should_report = current - _last_alert.get(alert_key, 0.0) >= ALERT_COOLDOWN_SEC
    if should_report:
        _last_alert[alert_key] = current

    client = bot
    if client is None:
        get_state = getattr(message, "_state", None)
        client = getattr(get_state, "_get_client", lambda: None)() if get_state else None

    if client is not None and should_report:
        embed = build_spam_alert_embed(
            guild,
            author,
            channel,
            violation,
            cfg=cfg,
            acted=acted,
            content=str(getattr(message, "content", "") or ""),
        )
        await _notify(client, cfg, guild, embed)

    await save_antispam_to_disk()
    return deleted or timed_out


# ==============================================================================
# ANTI-RAID (lonjakan member join)
# ==============================================================================
def record_join(guild_id: int, *, now: float | None = None, user_id: int = 0) -> int:
    """Mencatat member join & mengembalikan jumlah join dalam jendela raid."""
    gid = int(guild_id)
    current = time.time() if now is None else float(now)
    store = _recent_joins.setdefault(gid, [])
    store[:] = [item for item in store if item[0] >= current - SPAM_RAID_WINDOW_SEC]
    store.append((current, int(user_id)))
    return len(store)


def build_raid_alert_embed(guild, join_count: int, recent_members: list[int]) -> discord.Embed:
    embed = discord.Embed(
        title="🚨 Kemungkinan Serangan Raid",
        description=(
            f"`{join_count}` member bergabung dalam **{SPAM_RAID_WINDOW_SEC} detik terakhir** "
            f"(ambang `{SPAM_RAID_JOIN_COUNT}`)."
        ),
        color=discord.Color.red(),
    )
    if recent_members:
        embed.add_field(
            name="👥 Akun Terbaru",
            value=", ".join(f"<@{uid}>" for uid in recent_members[-10:])[:1024],
            inline=False,
        )
    embed.add_field(
        name="🛠️ Saran Tindakan",
        value=(
            "• Aktifkan `/verifikasi` agar member baru harus klik tombol sebelum bisa chat.\n"
            "• Nyalakan `/keamanan spam mode:hapus` bila pesan spam mulai masuk.\n"
            "• Jangan ban massal sebelum memastikan — cek daftar akun di atas."
        ),
        inline=False,
    )
    embed.set_footer(text="Anti-Raid hanya melapor (tidak pernah menendang otomatis).")
    return embed


async def handle_member_join_guard(bot, member, *, now: float | None = None) -> bool:
    """Mendeteksi lonjakan join & melapor ke channel log. Tidak menendang siapa pun."""
    guild = getattr(member, "guild", None)
    if guild is None:
        return False
    gid = _to_int(getattr(guild, "id", 0))
    cfg = spam_guilds.get(gid)
    if not cfg or not cfg.get("enabled"):
        return False
    if getattr(member, "bot", False):
        return False

    count = record_join(gid, now=now, user_id=_to_int(getattr(member, "id", 0)))
    if count < SPAM_RAID_JOIN_COUNT:
        return False

    alert_key = (gid, 0)  # 0 = laporan raid, terpisah dari laporan per member
    current = time.time() if now is None else float(now)
    if current - _last_alert.get(alert_key, 0.0) < ALERT_COOLDOWN_SEC * 2:
        return False
    _last_alert[alert_key] = current

    members = [uid for _, uid in _recent_joins.get(gid, [])]
    embed = build_raid_alert_embed(guild, count, members)
    sent = await _notify(bot, cfg, guild, embed)
    if sent:
        logger.warning("Peringatan raid dikirim untuk guild %s (%d join).", gid, count)
    return sent


# ==============================================================================
# STATUS & PEMBERSIHAN
# ==============================================================================
def build_spam_status_embed(guild_id: int, guild=None) -> discord.Embed:
    cfg = spam_guilds.get(int(guild_id))
    if not cfg or not cfg.get("enabled"):
        return discord.Embed(
            title="🛡️ Anti-Spam: NONAKTIF",
            description=(
                "Penjaga anti-spam belum dinyalakan di server ini.\n"
                "Aktifkan dengan `/keamanan spam aktif:True` — mode awalnya **lapor saja** "
                "(tidak ada pesan dihapus)."
            ),
            color=discord.Color.dark_gray(),
        )

    log_id = _to_int(cfg.get("log_channel_id"))
    embed = discord.Embed(
        title="🛡️ Anti-Spam & Anti-Raid",
        description=f"Mode: **{SPAM_MODES.get(cfg.get('mode', 'lapor'), SPAM_MODES['lapor'])}**",
        color=discord.Color.orange() if cfg.get("mode") == "lapor" else discord.Color.red(),
    )
    embed.add_field(
        name="📊 Ambang Deteksi",
        value=(
            f"• Flood: `{cfg['flood_count']}` pesan / `{cfg['flood_window']}` dtk\n"
            f"• Pesan berulang: `{cfg['duplicate_count']}`x / `{cfg['duplicate_window']}` dtk\n"
            f"• Mention massal: `{cfg['mention_limit']}`\n"
            f"• Link beruntun: `{cfg['link_limit']}`\n"
            f"• Huruf kapital: {'✅ aktif' if cfg.get('caps_enabled') else '⛔ nonaktif'}"
        ),
        inline=False,
    )
    embed.add_field(name="📝 Channel Log", value=f"<#{log_id}>" if log_id else "_belum diatur_", inline=True)
    embed.add_field(name="⏳ Time-out", value=f"`{cfg['timeout_sec']}` detik", inline=True)
    embed.add_field(name="🚫 Ditindak", value=f"`{cfg.get('blocked', 0)}` kejadian", inline=True)
    exempt_channels = cfg.get("exempt_channels") or []
    exempt_roles = cfg.get("exempt_roles") or []
    embed.add_field(
        name="🕊️ Pengecualian",
        value=(
            f"• Channel: {', '.join(f'<#{c}>' for c in exempt_channels[:5]) or '_tidak ada_'}\n"
            f"• Role: {', '.join(f'<@&{r}>' for r in exempt_roles[:5]) or '_tidak ada_'}"
        )[:1024],
        inline=False,
    )
    embed.set_footer(
        text=f"Anti-Raid: lapor bila ≥{SPAM_RAID_JOIN_COUNT} join / {SPAM_RAID_WINDOW_SEC} dtk • Admin & staf selalu dikecualikan"
    )
    return embed


def cleanup_antispam_runtime() -> int:
    """Membersihkan riwayat runtime lama agar RAM tidak membengkak."""
    removed = 0
    now = time.time()
    for store in (_recent_messages, _recent_texts):
        for key in list(store):
            store[key] = _prune(store[key], now, 300.0)
            if not store[key]:
                store.pop(key, None)
                removed += 1
    for key in list(_recent_links):
        _recent_links[key] = _prune(_recent_links[key], now, 300.0)
        if not _recent_links[key]:
            _recent_links.pop(key, None)
            removed += 1
    for key in list(_last_alert):
        if now - _last_alert[key] > 3600:
            _last_alert.pop(key, None)
            removed += 1
    for gid in list(_recent_joins):
        _recent_joins[gid] = [item for item in _recent_joins[gid] if item[0] >= now - 600]
        if not _recent_joins[gid]:
            _recent_joins.pop(gid, None)
            removed += 1
    return removed


def reset_runtime_state() -> None:
    """Mengosongkan seluruh state runtime (dipakai pengujian)."""
    _recent_messages.clear()
    _recent_texts.clear()
    _recent_links.clear()
    _recent_joins.clear()
    _last_alert.clear()
