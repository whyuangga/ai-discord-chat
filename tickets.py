"""Sistem Tiket Dukungan berbasis **Private Thread** (Tier 2C) — 0 kuota Gemini.

Kenapa thread, bukan channel?
- Thread **tidak memakan slot channel** server (batas channel Discord 500/server).
- Otomatis rapi: tiket selesai bisa diarsipkan, bukan menumpuk jadi channel mati.
- Pembuat tiket & staf tetap bisa lanjut diskusi tanpa mengganggu channel umum.

Data disimpan di `data/tickets.json`. Seluruh fitur **default NONAKTIF**
sampai Admin menjalankan `/tiket panel`.
"""

import asyncio
import io
import json
import logging
import os
import time
from pathlib import Path

import discord

from config import (
    DATA_DIR,
    TICKET_AUTO_CLOSE_HOURS,
    TICKET_MAX_OPEN_PER_USER,
    TICKET_MAX_TRANSCRIPT_LINES,
    TICKETS_FILE,
)
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.tickets")

_lock = asyncio.Lock()

TICKET_STATUS: dict[str, str] = {
    "terbuka": "🟢 Terbuka",
    "diklaim": "🙋 Sedang ditangani",
    "selesai": "✅ Selesai",
}

# ==============================================================================
# STATE GLOBAL
# ==============================================================================
ticket_guilds: dict[int, dict] = {}   # guild_id -> konfigurasi panel tiket
tickets: dict[int, dict] = {}         # thread_id -> data tiket
_ticket_seq: dict[int, int] = {}      # guild_id -> nomor tiket terakhir


def default_config() -> dict:
    return {
        "enabled": True,
        "panel_channel_id": None,
        "panel_message_id": None,
        "staff_role_id": None,
        "category_id": None,
        "log_channel_id": None,
        "max_open": int(TICKET_MAX_OPEN_PER_USER),
        "ping_staff": True,
        "opened": 0,
        "closed": 0,
    }


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def load_tickets_from_disk() -> int:
    """Memuat konfigurasi panel tiket & tiket yang tercatat."""
    ticket_guilds.clear()
    tickets.clear()
    _ticket_seq.clear()
    if not TICKETS_FILE.exists():
        return 0

    try:
        raw = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", TICKETS_FILE, exc)
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
                "panel_channel_id": _to_int(data.get("panel_channel_id")) or None,
                "panel_message_id": _to_int(data.get("panel_message_id")) or None,
                "staff_role_id": _to_int(data.get("staff_role_id")) or None,
                "category_id": _to_int(data.get("category_id")) or None,
                "log_channel_id": _to_int(data.get("log_channel_id")) or None,
                "max_open": max(1, _to_int(data.get("max_open"), base["max_open"])),
                "ping_staff": bool(data.get("ping_staff", True)),
                "opened": max(0, _to_int(data.get("opened"))),
                "closed": max(0, _to_int(data.get("closed"))),
            }
        )
        ticket_guilds[gid] = base
        _ticket_seq[gid] = max(_ticket_seq.get(gid, 0), _to_int(data.get("seq")))

    for tid_str, data in (raw.get("tickets") or {}).items():
        try:
            tid = int(tid_str)
            gid = _to_int(data.get("guild_id"))
            uid = _to_int(data.get("user_id"))
        except (TypeError, ValueError):
            continue
        if not gid or not uid:
            continue
        number = max(1, _to_int(data.get("number"), 1))
        tickets[tid] = {
            "thread_id": tid,
            "guild_id": gid,
            "user_id": uid,
            "number": number,
            "status": str(data.get("status") or "terbuka")
            if str(data.get("status") or "terbuka") in TICKET_STATUS
            else "terbuka",
            "topic": str(data.get("topic") or "")[:200],
            "created_at": float(data.get("created_at") or 0),
            "claimed_by": _to_int(data.get("claimed_by")) or None,
            "closed_by": _to_int(data.get("closed_by")) or None,
            "closed_at": float(data.get("closed_at") or 0),
            "added_users": [_to_int(u) for u in (data.get("added_users") or []) if _to_int(u)],
        }
        _ticket_seq[gid] = max(_ticket_seq.get(gid, 0), number)
    return len(ticket_guilds)


async def save_tickets_to_disk() -> None:
    """Menyimpan konfigurasi & data tiket secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            guilds_payload = {}
            for gid, cfg in ticket_guilds.items():
                item = dict(cfg)
                item["seq"] = _ticket_seq.get(gid, 0)
                guilds_payload[str(gid)] = item
            payload = {
                "guilds": guilds_payload,
                "tickets": {str(k): v for k, v in tickets.items()},
            }
            tmp_file = Path(str(TICKETS_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, TICKETS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan tickets.json: %s", sanitize_error_message(exc))


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def get_ticket_config(guild_id: int) -> dict:
    cfg = ticket_guilds.get(int(guild_id))
    if cfg is None:
        cfg = default_config()
        ticket_guilds[int(guild_id)] = cfg
    return cfg


def is_ticket_enabled(guild_id: int) -> bool:
    cfg = ticket_guilds.get(int(guild_id))
    return bool(cfg and cfg.get("enabled"))


def set_ticket_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    panel_channel_id: int | None = None,
    panel_message_id: int | None = None,
    staff_role_id: int | None = None,
    category_id: int | None = None,
    log_channel_id: int | None = None,
    max_open: int | None = None,
    ping_staff: bool | None = None,
) -> dict:
    """Mengubah konfigurasi panel tiket server."""
    cfg = get_ticket_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if panel_channel_id is not None:
        cfg["panel_channel_id"] = int(panel_channel_id) or None
    if panel_message_id is not None:
        cfg["panel_message_id"] = int(panel_message_id) or None
    if staff_role_id is not None:
        cfg["staff_role_id"] = int(staff_role_id) or None
    if category_id is not None:
        cfg["category_id"] = int(category_id) or None
    if log_channel_id is not None:
        cfg["log_channel_id"] = int(log_channel_id) or None
    if max_open is not None:
        cfg["max_open"] = max(1, min(10, int(max_open)))
    if ping_staff is not None:
        cfg["ping_staff"] = bool(ping_staff)
    return cfg


def disable_tickets(guild_id: int) -> bool:
    cfg = ticket_guilds.get(int(guild_id))
    if cfg is None:
        return False
    cfg["enabled"] = False
    return True


def next_ticket_number(guild_id: int) -> int:
    gid = int(guild_id)
    _ticket_seq[gid] = int(_ticket_seq.get(gid, 0)) + 1
    return _ticket_seq[gid]


# ==============================================================================
# SIKLUS HIDUP TIKET
# ==============================================================================
def open_ticket_count(guild_id: int, user_id: int) -> int:
    return sum(
        1
        for data in tickets.values()
        if data.get("guild_id") == int(guild_id)
        and data.get("user_id") == int(user_id)
        and data.get("status") in ("terbuka", "diklaim")
    )


def can_open_ticket(guild_id: int, user_id: int) -> tuple[bool, str]:
    """Memeriksa batas tiket terbuka per member."""
    cfg = get_ticket_config(guild_id)
    limit = int(cfg.get("max_open") or TICKET_MAX_OPEN_PER_USER)
    active = open_ticket_count(guild_id, user_id)
    if active >= limit:
        return False, (
            f"⚠️ Kamu masih punya **{active} tiket aktif** (batas `{limit}`). "
            "Selesaikan dulu tiket lamamu sebelum membuka yang baru."
        )
    return True, ""


def register_ticket(
    thread_id: int,
    guild_id: int,
    user_id: int,
    *,
    topic: str = "",
    now: float | None = None,
) -> dict:
    """Mencatat tiket baru setelah thread berhasil dibuat."""
    gid = int(guild_id)
    number = next_ticket_number(gid)
    data = {
        "thread_id": int(thread_id),
        "guild_id": gid,
        "user_id": int(user_id),
        "number": number,
        "status": "terbuka",
        "topic": str(topic or "")[:200],
        "created_at": time.time() if now is None else float(now),
        "claimed_by": None,
        "closed_by": None,
        "closed_at": 0.0,
        "added_users": [],
    }
    tickets[int(thread_id)] = data
    cfg = get_ticket_config(gid)
    cfg["opened"] = int(cfg.get("opened") or 0) + 1
    return data


def get_ticket(thread_id: int) -> dict | None:
    return tickets.get(int(thread_id))


def claim_ticket(thread_id: int, staff_id: int) -> tuple[str, dict | None]:
    """Menandai tiket sedang ditangani staf. Status: `ok`, `sudah`, `selesai`, `tidak_ada`."""
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    if data.get("status") == "selesai":
        return "selesai", data
    if data.get("claimed_by") == int(staff_id):
        return "sudah", data
    data["claimed_by"] = int(staff_id)
    data["status"] = "diklaim"
    return "ok", data


def close_ticket(thread_id: int, closed_by: int, *, now: float | None = None) -> tuple[str, dict | None]:
    """Menutup tiket. Status: `ok`, `selesai`, `tidak_ada`."""
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    if data.get("status") == "selesai":
        return "selesai", data
    data["status"] = "selesai"
    data["closed_by"] = int(closed_by)
    data["closed_at"] = time.time() if now is None else float(now)
    cfg = get_ticket_config(data["guild_id"])
    cfg["closed"] = int(cfg.get("closed") or 0) + 1
    return "ok", data


def add_user_to_ticket(thread_id: int, user_id: int) -> bool:
    data = tickets.get(int(thread_id))
    if data is None:
        return False
    added = data.setdefault("added_users", [])
    if int(user_id) in added:
        return False
    added.append(int(user_id))
    return True


def can_view_ticket(data: dict, user_id: int) -> bool:
    """Pembuat tiket & member yang ditambahkan boleh melihat tiketnya."""
    if data is None:
        return False
    return int(user_id) in (int(data.get("user_id") or 0), *(int(u) for u in data.get("added_users") or []))


def list_tickets(guild_id: int, *, status: str | None = None, limit: int = 15) -> list[dict]:
    items = [
        data
        for data in tickets.values()
        if data.get("guild_id") == int(guild_id) and (status is None or data.get("status") == status)
    ]
    items.sort(key=lambda d: float(d.get("created_at") or 0), reverse=True)
    return items[:limit]


def stale_tickets(*, hours: int = TICKET_AUTO_CLOSE_HOURS, now: float | None = None) -> list[int]:
    """Tiket yang dianggap kedaluwarsa (bila fitur auto-close diaktifkan Admin)."""
    if hours <= 0:
        return []
    current = time.time() if now is None else float(now)
    limit = current - hours * 3600
    return [
        tid
        for tid, data in tickets.items()
        if data.get("status") in ("terbuka", "diklaim") and float(data.get("created_at") or 0) < limit
    ]


# ==============================================================================
# TAMPILAN
# ==============================================================================
def build_panel_embed(guild_name: str = "", *, staff_role_id: int | None = None) -> discord.Embed:
    """Embed panel pembuatan tiket."""
    embed = discord.Embed(
        title="🎟️ Pusat Bantuan Server",
        description=(
            "Butuh bantuan staf, laporan bug, atau pertanyaan yang butuh data pribadi?\n"
            "Tekan tombol **Buat Tiket** di bawah — bot akan membuatkan **thread privat** "
            "yang hanya bisa dilihat kamu & staf.\n\n"
            "**Tips agar cepat ditangani**\n"
            "• Jelaskan masalahnya langsung di thread (sertakan screenshot bila perlu).\n"
            "• Jangan membuka tiket ganda untuk masalah yang sama.\n"
            "• Tiket akan diarsipkan otomatis setelah selesai."
        ),
        color=discord.Color.blurple(),
    )
    if staff_role_id:
        embed.add_field(name="👥 Petugas", value=f"<@&{staff_role_id}>", inline=False)
    embed.set_footer(text="Tanpa AI & tanpa kuota Gemini • hanya membuat thread, bukan channel baru")
    if guild_name:
        embed.title = f"🎟️ Pusat Bantuan {guild_name}"[:256]
    return embed


def build_ticket_embed(data: dict, *, staff_role_id: int | None = None) -> discord.Embed:
    """Embed pembuka di dalam thread tiket."""
    status = TICKET_STATUS.get(str(data.get("status")), TICKET_STATUS["terbuka"])
    embed = discord.Embed(
        title=f"🎟️ Tiket #{data.get('number', 0):04d}",
        description=(
            f"Terima kasih <@{data.get('user_id')}>! Tiketmu sudah dibuat.\n"
            "Tulis detail masalahmu di thread ini, lalu staf akan segera merespons."
        ),
        color=discord.Color.green() if data.get("status") != "selesai" else discord.Color.dark_gray(),
    )
    embed.add_field(name="📌 Status", value=status, inline=True)
    embed.add_field(
        name="🗂️ Topik",
        value=str(data.get("topic") or "_(tidak diisi)_")[:200],
        inline=True,
    )
    claimed = data.get("claimed_by")
    embed.add_field(name="🙋 Ditangani", value=f"<@{claimed}>" if claimed else "_belum ada_", inline=True)
    if staff_role_id:
        embed.add_field(name="👥 Staf", value=f"<@&{staff_role_id}>", inline=False)
    embed.set_footer(text="Gunakan tombol 🔒 Tutup Tiket bila masalah sudah selesai")
    return embed


def build_ticket_status_embed(guild_id: int, guild=None) -> discord.Embed:
    """Ringkasan konfigurasi & statistik tiket server."""
    cfg = ticket_guilds.get(int(guild_id))
    if not cfg or not cfg.get("enabled"):
        return discord.Embed(
            title="🎟️ Tiket Dukungan: NONAKTIF",
            description=(
                "Sistem tiket belum aktif di server ini.\n"
                "Pasang dengan `/tiket panel channel:#bantuan staff_role:@Staf`."
            ),
            color=discord.Color.dark_gray(),
        )

    panel_channel = cfg.get("panel_channel_id")
    log_channel = cfg.get("log_channel_id")
    embed = discord.Embed(
        title="🎟️ Sistem Tiket Dukungan",
        description=f"Status: **{'✅ Aktif' if cfg.get('enabled') else '⛔ Nonaktif'}**",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="📍 Panel",
        value=f"<#{panel_channel}>" if panel_channel else "_belum dipasang_",
        inline=True,
    )
    embed.add_field(
        name="👥 Role Staf",
        value=f"<@&{cfg['staff_role_id']}>" if cfg.get("staff_role_id") else "_belum diatur_",
        inline=True,
    )
    embed.add_field(
        name="📝 Log Transkrip",
        value=f"<#{log_channel}>" if log_channel else "_belum diatur_",
        inline=True,
    )
    active = [d for d in tickets.values() if d.get("guild_id") == int(guild_id) and d.get("status") in ("terbuka", "diklaim")]
    embed.add_field(
        name="📊 Statistik",
        value=(
            f"• Tiket aktif: `{len(active)}`\n"
            f"• Total dibuka: `{cfg.get('opened', 0)}`\n"
            f"• Total selesai: `{cfg.get('closed', 0)}`\n"
            f"• Batas per member: `{cfg.get('max_open', TICKET_MAX_OPEN_PER_USER)}`"
        ),
        inline=False,
    )
    if active:
        lines = []
        for data in sorted(active, key=lambda d: float(d.get("created_at") or 0), reverse=True)[:8]:
            lines.append(
                f"• `#{data['number']:04d}` <@{data['user_id']}> — {TICKET_STATUS.get(data['status'], '-')}"
            )
        embed.add_field(name="🟢 Tiket Aktif", value="\n".join(lines)[:1024], inline=False)
    embed.set_footer(text="Tiket dibuat sebagai thread privat, bukan channel baru")
    return embed


# ==============================================================================
# TRANSKRIP
# ==============================================================================
def build_transcript(data: dict, messages: list, *, max_lines: int = TICKET_MAX_TRANSCRIPT_LINES) -> tuple[str, str]:
    """Menyusun transkrip teks tiket. Mengembalikan `(isi, nama_berkas)`."""
    base_name = f"tiket-{int(data.get('number') or 0):04d}"
    header = [
        f"TRANSKRIP TIKET #{int(data.get('number') or 0):04d}",
        "=" * 48,
        f"Server     : {data.get('guild_id')}",
        f"Pembuat    : {data.get('user_id')}",
        f"Topik      : {data.get('topic') or '-'}",
        f"Dibuka     : {_format_time(data.get('created_at'))}",
        f"Ditutup    : {_format_time(data.get('closed_at')) if data.get('closed_at') else '-'}",
        f"Ditutup oleh: {data.get('closed_by') or '-'}",
        f"Ditangani  : {data.get('claimed_by') or '-'}",
        "",
        "ISI PERCAKAPAN",
        "-" * 48,
    ]
    lines = list(header)
    for message in list(messages)[-max(1, int(max_lines)):]:
        author = getattr(getattr(message, "author", None), "display_name", None) or "?"
        when = _format_time(getattr(message, "created_at", None))
        content = str(getattr(message, "content", "") or "")
        attachments = getattr(message, "attachments", None) or []
        if attachments:
            links = " ".join(str(getattr(item, "url", "")) for item in attachments)
            content = f"{content} [lampiran: {links}]".strip()
        lines.append(f"[{when}] {author}: {content}")
    lines.append("")
    lines.append("=" * 48)
    lines.append("Dibuat otomatis oleh bot • tanpa AI & tanpa kuota Gemini")
    text = "\n".join(lines)[:180_000]
    return text, f"{base_name}.txt"


def _format_time(value) -> str:
    if not value:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(value)))
    except (TypeError, ValueError, OSError):
        return "-"


async def collect_thread_messages(thread, *, limit: int = TICKET_MAX_TRANSCRIPT_LINES) -> list:
    """Mengambil riwayat pesan thread (aman bila izin baca history kurang)."""
    history = getattr(thread, "history", None)
    if not callable(history):
        return []
    collected = []
    try:
        async for message in history(limit=min(1000, max(10, int(limit))), oldest_first=True):
            collected.append(message)
    except (discord.Forbidden, discord.HTTPException) as exc:  # pragma: no cover - izin kurang
        logger.info("Gagal membaca riwayat tiket: %s", sanitize_error_message(exc))
    return collected


def transcript_file(text: str, filename: str) -> discord.File:
    """Membungkus transkrip menjadi `discord.File`."""
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=filename)


async def send_transcript(bot, data: dict, text: str, filename: str) -> bool:
    """Mengirim transkrip ke channel log server (bila diatur)."""
    cfg = ticket_guilds.get(int(data.get("guild_id") or 0)) or {}
    log_id = _to_int(cfg.get("log_channel_id"))
    if not log_id:
        return False
    channel = None
    get_channel = getattr(bot, "get_channel", None)
    if callable(get_channel):
        channel = get_channel(log_id)
    if channel is None:
        return False
    try:
        await channel.send(
            content=(
                f"📄 Transkrip tiket `#{int(data.get('number') or 0):04d}` "
                f"milik <@{data.get('user_id')}> sudah ditutup."
            ),
            file=transcript_file(text, filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal mengirim transkrip tiket: %s", sanitize_error_message(exc))
        return False


def handle_channel_delete(channel) -> bool:
    """Membersihkan konfigurasi tiket saat channel terkait dihapus."""
    cid = _to_int(getattr(channel, "id", 0))
    changed = False
    for cfg in ticket_guilds.values():
        if cfg.get("panel_channel_id") == cid:
            cfg["panel_channel_id"] = None
            cfg["panel_message_id"] = None
            changed = True
        if cfg.get("log_channel_id") == cid:
            cfg["log_channel_id"] = None
            changed = True
        if cfg.get("category_id") == cid:
            cfg["category_id"] = None
            changed = True
    return changed


def handle_thread_delete(thread_id: int) -> bool:
    """Membuang catatan tiket saat thread-nya dihapus manual."""
    return tickets.pop(int(thread_id), None) is not None


def cleanup_tickets_runtime(*, max_closed: int = 200) -> int:
    """Membatasi jumlah tiket selesai yang disimpan agar JSON tetap kecil."""
    closed = [
        (tid, float(data.get("closed_at") or 0))
        for tid, data in tickets.items()
        if data.get("status") == "selesai"
    ]
    if len(closed) <= max_closed:
        return 0
    closed.sort(key=lambda pair: pair[1])
    removed = 0
    for tid, _ in closed[: len(closed) - max_closed]:
        tickets.pop(tid, None)
        removed += 1
    return removed
