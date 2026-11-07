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
import channel_targets

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
starboard_guilds: dict[int, dict] = {}       # guild_id -> konfigurasi starboard (+ `boards`)
# Maksimum papan sorotan per server, termasuk papan utama (⭐).
STARBOARD_MAX_BOARD = 4
sticky_channels: dict[int, dict] = {}        # channel_id -> konfigurasi sticky
verification_guilds: dict[int, dict] = {}    # guild_id -> gerbang verifikasi

# --- CAPTCHA verifikasi (tanpa dependency baru, hanya kode teks) ---
CAPTCHA_PANJANG = 5
CAPTCHA_TTL_SEC = 300          # kode kedaluwarsa setelah 5 menit
CAPTCHA_MAKS_PERCOBAAN = 3
CAPTCHA_HURUF = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # tanpa 0/O/1/I/L agar tidak salah baca
# guild_id -> {user_id: {"kode", "kedaluwarsa", "percobaan"}}
captcha_pending: dict[int, dict[int, dict]] = {}
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
def _muat_reaction_roles(raw: dict) -> None:
    """Panel reaction role (pesan → pilihan emoji/role)."""
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



def _muat_reminders(raw: dict) -> None:
    """Pengingat terjadwal per pengguna."""
    global _reminder_seq
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



def _muat_starboard(raw: dict) -> None:
    """Papan sorotan: konfigurasi server + daftar board."""
    for gid_str, data in (raw.get("starboard") or {}).items():
        try:
            entries = {
                str(k): {
                    "starboard_id": _to_int(v.get("starboard_id")),
                    "count": _to_int(v.get("count")),
                }
                for k, v in (data.get("entries") or {}).items()
            }
            cfg = {
                "enabled": bool(data.get("enabled", True)),
                "channel_id": _to_int(data.get("channel_id")),
                "threshold": max(1, _to_int(data.get("threshold"), STARBOARD_DEFAULT_THRESHOLD)),
                "emoji": str(data.get("emoji") or STARBOARD_EMOJI),
                "entries": entries,
            }
            warna = str(data.get("warna") or "")
            if warna:
                cfg["warna"] = warna
            boards = []
            for isi in data.get("boards") or []:
                if not isinstance(isi, dict):
                    continue
                entri_board = {
                    str(k): {
                        "starboard_id": _to_int(v.get("starboard_id")),
                        "count": _to_int(v.get("count")),
                    }
                    for k, v in (isi.get("entries") or {}).items()
                }
                boards.append(
                    {
                        "kunci": str(isi.get("kunci") or "")[:20],
                        "nama": str(isi.get("nama") or "")[:40],
                        "emoji": str(isi.get("emoji") or "💀")[:64],
                        "threshold": max(1, _to_int(isi.get("threshold"), STARBOARD_DEFAULT_THRESHOLD)),
                        "channel_id": _to_int(isi.get("channel_id")),
                        "warna": str(isi.get("warna") or ""),
                        "entries": entri_board,
                    }
                )
            if boards:
                cfg["boards"] = boards
            starboard_guilds[int(gid_str)] = cfg
        except (TypeError, ValueError):
            continue



def _muat_sticky_dan_lainnya(raw: dict) -> None:
    """Sticky, verifikasi, dan mode maintenance."""
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
                "captcha": bool(data.get("captcha")),
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



def load_community_tools_from_disk() -> tuple[int, int, int, int, int]:
    """Memuat seluruh konfigurasi fitur komunitas. Mengembalikan jumlah tiap fitur.

    Pembacaan dipecah per kelompok (reaction role, pengingat, starboard, sticky &
    lain-lain) supaya tiap bagian bisa dibaca dan diuji sendiri. Satu kelompok
    yang rusak dilewati tanpa menghentikan kelompok lain.
    """
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

    _muat_reaction_roles(raw)
    _muat_reminders(raw)
    _muat_starboard(raw)
    _muat_sticky_dan_lainnya(raw)

    return (
        len(reaction_role_panels),
        len(reminders),
        len(starboard_guilds),
        len(sticky_channels),
        len(verification_guilds),
    )


def _pesan_galat(exc: Exception) -> str:
    """Pesan galat yang aman dicatat (token/URL sudah disaring)."""
    from utils import sanitize_error_message

    return sanitize_error_message(exc)

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
            logger.exception("Gagal menyimpan community_tools.json: %s", _pesan_galat(exc))


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
# 2. STARBOARD (/starboard) — papan utama + varian (skullboard/clownboard/…)
# ==============================================================================
def set_starboard_config(
    guild_id: int,
    *,
    channel_id: int | None = None,
    threshold: int | None = None,
    emoji: str | None = None,
    enabled: bool | None = None,
    warna: str | None = None,
) -> dict | None:
    """Mengatur channel sorotan, batas bintang, emoji, & status aktif papan utama."""
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
    if warna is not None:
        bersih = str(warna).strip().lstrip("#").upper()
        if bersih and len(bersih) == 6:
            cfg["warna"] = "#" + bersih
        elif not bersih:
            cfg.pop("warna", None)
    cfg["enabled"] = True if enabled is None else bool(enabled)
    starboard_guilds[guild_id] = cfg
    return cfg


def _board_slug(nama: str) -> str:
    """Kunci papan dari namanya (`Skull Board` → `skull-board`)."""
    teks = re.sub(r"[^a-z0-9]+", "-", str(nama or "").strip().lower()).strip("-")
    return teks[:20]


def _warna_embed(warna: str) -> discord.Color:
    """Warna embed dari hex `#RRGGBB` (default emas)."""
    teks = str(warna or "").strip().lstrip("#")
    if len(teks) == 6:
        try:
            return discord.Color(int(teks, 16))
        except ValueError:
            pass
    return discord.Color.gold()


def _board_cfg(board: dict) -> dict:
    """Konfigurasi satu papan dengan nilai bawaan yang aman."""
    return {
        "kunci": str(board.get("kunci") or ""),
        "nama": str(board.get("nama") or "Starboard")[:40],
        "emoji": str(board.get("emoji") or STARBOARD_EMOJI)[:64],
        "threshold": max(1, min(50, _to_int(board.get("threshold"), STARBOARD_DEFAULT_THRESHOLD))),
        "channel_id": _to_int(board.get("channel_id")),
        "warna": str(board.get("warna") or ""),
        "utama": bool(board.get("utama")),
    }


def _iter_boards(cfg: dict):
    """Iterasi papan **aktif** beserta tempat penyimpanan entrinya (objek hidup).

    Papan utama memakai kolom lama (`cfg["entries"]`) supaya data server yang sudah
    jalan tidak perlu dimigrasi; varian menyimpan entrinya sendiri.
    """
    yield (
        _board_cfg(
            {
                "kunci": "utama",
                "nama": "Starboard",
                "emoji": cfg.get("emoji"),
                "threshold": cfg.get("threshold"),
                "channel_id": cfg.get("channel_id"),
                "warna": cfg.get("warna"),
                "utama": True,
            }
        ),
        cfg.setdefault("entries", {}),
    )
    for board in cfg.get("boards") or []:
        if not isinstance(board, dict):
            continue
        data = _board_cfg({**board, "utama": False})
        if not data["kunci"]:
            continue
        yield data, board.setdefault("entries", {})


def list_starboard_boards(guild_id: int) -> list[dict]:
    """Semua papan sorotan server (papan utama dulu), termasuk jumlah sorotan."""
    cfg = starboard_guilds.get(int(guild_id or 0))
    if not cfg or not cfg.get("enabled"):
        return []
    utama_cid = _to_int(cfg.get("channel_id"))
    hasil: list[dict] = []
    for data, entries in _iter_boards(cfg):
        item = dict(data)
        item["channel_id"] = item["channel_id"] or utama_cid
        item["jumlah"] = len(entries or {})
        hasil.append(item)
    return hasil


def add_starboard_board(
    guild_id: int,
    nama: str,
    *,
    emoji: str = "",
    threshold: int = 0,
    channel_id: int = 0,
    warna: str = "",
) -> tuple[bool, str]:
    """Menambah/memperbarui satu papan varian (maks `STARBOARD_MAX_BOARD` papan)."""
    cfg = starboard_guilds.get(int(guild_id or 0))
    if not cfg or not cfg.get("enabled"):
        return False, "Starboard belum aktif — jalankan `/starboard atur channel:#…` dulu."

    kunci = _board_slug(nama)
    if not kunci:
        return False, "Nama papan tidak boleh kosong."
    if kunci in ("utama", "main", "starboard"):
        return False, "Nama itu dipakai papan utama. Pilih nama lain (mis. `skull`)."

    boards = [b for b in (cfg.get("boards") or []) if isinstance(b, dict)]
    lama = next((b for b in boards if _board_slug(b.get("kunci") or b.get("nama") or "") == kunci), None)
    if lama is None and len(boards) + 1 >= STARBOARD_MAX_BOARD:
        return False, (
            f"Papan sudah penuh ({STARBOARD_MAX_BOARD} termasuk papan utama). "
            "Hapus salah satu varian dulu."
        )

    isi = lama if lama is not None else {"kunci": kunci, "entries": {}}
    isi["kunci"] = kunci
    isi["nama"] = str(nama or "").strip()[:40] or kunci
    if emoji and str(emoji).strip():
        isi["emoji"] = str(emoji).strip()[:64]
    else:
        isi.setdefault("emoji", "💀")
    if threshold:
        isi["threshold"] = max(1, min(50, int(threshold)))
    else:
        isi.setdefault("threshold", STARBOARD_DEFAULT_THRESHOLD)
    if channel_id:
        isi["channel_id"] = int(channel_id)
    else:
        isi.setdefault("channel_id", 0)
    if warna:
        isi["warna"] = "#" + str(warna).strip().lstrip("#").upper()[:6]
    else:
        isi.setdefault("warna", "")
    if lama is None:
        boards.append(isi)
    cfg["boards"] = boards
    starboard_guilds[int(guild_id)] = cfg
    kata = "diperbarui" if lama is not None else "ditambahkan"
    return True, (
        f"Papan **{isi['nama']}** {kata} ({isi['emoji']} ≥ {isi['threshold']} reaksi, "
        f"channel: {'<#' + str(isi['channel_id']) + '>' if isi['channel_id'] else 'ikut papan utama'})."
    )


def remove_starboard_board(guild_id: int, nama: str) -> tuple[bool, str]:
    """Menghapus satu papan varian (papan utama tidak bisa dihapus dari sini)."""
    cfg = starboard_guilds.get(int(guild_id or 0))
    if not cfg:
        return False, "Starboard belum aktif di server ini."
    kunci = _board_slug(nama)
    if not kunci:
        return False, "Sebutkan nama papan yang ingin dihapus."
    if kunci in ("utama", "main", "starboard"):
        return False, "Papan utama tidak bisa dihapus — matikan lewat `/starboard atur aktif:False`."
    boards = [b for b in (cfg.get("boards") or []) if isinstance(b, dict)]
    sisa = [
        b for b in boards
        if _board_slug(b.get("kunci") or b.get("nama") or "") != kunci
    ]
    if len(sisa) == len(boards):
        return False, f"Papan varian `{kunci}` tidak ditemukan."
    cfg["boards"] = sisa
    if not sisa:
        cfg.pop("boards", None)
    starboard_guilds[int(guild_id)] = cfg
    return True, f"Papan varian `{kunci}` dihapus. Sorotan lamanya tetap ada di channel."


def build_starboard_embed(
    message: discord.Message,
    count: int,
    emoji: str,
    *,
    nama: str = "",
    warna: str = "",
) -> discord.Embed:
    """Menyusun embed sorotan untuk pesan yang mencapai batas bintang."""
    embed = discord.Embed(
        description=(message.content or "")[:3900] or "_*(tanpa teks — lihat lampiran)*_",
        color=_warna_embed(warna),
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
    label = f"{nama} • " if nama and nama.lower() != "starboard" else ""
    embed.set_footer(text=f"{label}{emoji} {count} • disorot oleh warga server")
    return embed


async def _sync_board(
    bot: discord.Client,
    message,
    board: dict,
    entries: dict,
    payload,
    *,
    emoji_str: str,
) -> bool:
    """Menyamakan satu papan dengan jumlah reaksi saat ini (`True` bila berubah)."""
    kunci = str(payload.message_id)
    entry = entries.get(kunci)
    channel_id = _to_int(board.get("channel_id"))
    if not channel_id:
        return False
    channel = bot.get_channel(channel_id)
    threshold = max(1, _to_int(board.get("threshold"), STARBOARD_DEFAULT_THRESHOLD))

    count = 0
    for reaction in message.reactions:
        if _emoji_matches(emoji_str, str(reaction.emoji)):
            count = max(count, int(reaction.count) - 1)  # kurangi reaksi bot sendiri
            break

    if count >= threshold and not entry:
        if channel is None:
            return False
        nama = str(board.get("nama") or "")
        try:
            posted = await channel.send(
                content=(
                    f"{emoji_str} **{count}** • <#{payload.channel_id}>"
                    + (f" · **{nama}**" if nama and nama.lower() != "starboard" else "")
                ),
                embed=build_starboard_embed(
                    message, count, emoji_str, nama=nama, warna=str(board.get("warna") or "")
                ),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.info("Gagal kirim starboard: %s", sanitize_error_message(exc))
            return False
        entries[kunci] = {"starboard_id": posted.id, "count": count}
        await save_community_tools_to_disk()
        return True

    if count >= threshold and entry:
        # Jumlah reaksi berubah → perbarui angka di pesan sorotan (tanpa spam pesan baru).
        if _to_int(entry.get("count")) == count:
            return False
        entry["count"] = count
        starboard_id = _to_int(entry.get("starboard_id"))
        if channel is not None and starboard_id:
            try:
                partial = channel.get_partial_message(starboard_id)
                await partial.edit(
                    content=(
                        f"{emoji_str} **{count}** • <#{payload.channel_id}>"
                        + (
                            f" · **{board.get('nama')}**"
                            if board.get("nama") and str(board["nama"]).lower() != "starboard"
                            else ""
                        )
                    ),
                    embed=build_starboard_embed(
                        message,
                        count,
                        emoji_str,
                        nama=str(board.get("nama") or ""),
                        warna=str(board.get("warna") or ""),
                    ),
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                pass
        await save_community_tools_to_disk()
        return True

    if entry:
        # Reaksi turun di bawah ambang → hapus jejak sorotan papan ini.
        starboard_id = _to_int(entry.get("starboard_id"))
        if channel is not None and starboard_id:
            try:
                await channel.get_partial_message(starboard_id).delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                pass
        entries.pop(kunci, None)
        await save_community_tools_to_disk()
        return True

    return False


async def handle_starboard_reaction(bot: discord.Client, payload, *, added: bool) -> bool:
    """Menyamakan **semua** papan sorotan yang emojinya cocok dengan reaksi ini."""
    cfg = starboard_guilds.get(getattr(payload, "guild_id", None))
    if not cfg or not cfg.get("enabled"):
        return False

    incoming = str(payload.emoji)
    papan = [
        (board, entries)
        for board, entries in _iter_boards(cfg)
        if _emoji_matches(board["emoji"], incoming)
    ]
    if not papan:
        return False

    # Pesan yang berada di dalam papan sorotan tidak boleh disorot lagi (anti-loop).
    papan_channel = {b["channel_id"] for b, _ in papan if b["channel_id"]}
    papan_channel.add(_to_int(cfg.get("channel_id")))
    if payload.channel_id in papan_channel:
        return False

    if not added and not any(entries.get(str(payload.message_id)) for _, entries in papan):
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

    berubah = False
    for board, entries in papan:
        emoji_str = board["emoji"]
        berubah = await _sync_board(
            bot, message, board, entries, payload, emoji_str=emoji_str
        ) or berubah
    return berubah


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
    captcha: bool | None = None,
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
        "captcha": False,
    }
    if channel_id is not None:
        cfg["channel_id"] = int(channel_id)
    if role_id is not None:
        cfg["role_id"] = int(role_id)
    if message_id is not None:
        cfg["message_id"] = int(message_id)
    if captcha is not None:
        cfg["captcha"] = bool(captcha)
    cfg.setdefault("captcha", False)
    cfg["enabled"] = True if enabled is None else bool(enabled)
    verification_guilds[guild_id] = cfg
    return cfg


def build_verification_embed(
    guild_name: str, role_name: str, extra_note: str = "", *, captcha: bool = False
) -> discord.Embed:
    langkah = (
        "Tekan tombol **Verifikasi Saya**, lalu **ketik kode CAPTCHA** yang muncul "
        "untuk membuka seluruh akses channel.\n"
        if captcha
        else "Tekan tombol **Verifikasi Saya** di bawah untuk membuka seluruh akses channel.\n"
    )
    embed = discord.Embed(
        title="✅ Verifikasi Keanggotaan",
        description=(
            f"Selamat datang di **{guild_name}**!\n\n"
            + langkah
            + f"Kamu akan otomatis mendapatkan role **{role_name}**."
        ),
        color=discord.Color.green(),
    )
    if extra_note:
        embed.add_field(name="📌 Catatan", value=extra_note[:1024], inline=False)
    embed.set_footer(
        text=("Kode CAPTCHA • Anti-bot & anti-raid" if captcha else "Sekali klik saja • Anti-bot & anti-raid")
    )
    return embed


# ==============================================================================
# CAPTCHA VERIFIKASI
# ==============================================================================
def buat_kode(*, panjang: int = CAPTCHA_PANJANG, rng=None) -> str:
    """Kode CAPTCHA acak (huruf/angka tanpa 0/O/1/I/L)."""
    import secrets

    sumber = rng or secrets.SystemRandom()
    panjang = max(4, min(8, int(panjang)))
    return "".join(sumber.choice(CAPTCHA_HURUF) for _ in range(panjang))


def captcha_aktif(guild_id: int) -> bool:
    cfg = verification_guilds.get(int(guild_id)) or {}
    return bool(cfg.get("enabled") and cfg.get("captcha"))


def minta_kode(guild_id: int, user_id: int, *, sekarang: float | None = None, rng=None) -> dict:
    """Ambil kode aktif member, atau buat kode baru (TTL 5 menit, 3 percobaan)."""
    gid, uid = int(guild_id), int(user_id)
    kini = sekarang if sekarang is not None else time.time()
    kumpulan = captcha_pending.setdefault(gid, {})
    data = kumpulan.get(uid)
    if data and float(data.get("kedaluwarsa") or 0) > kini and data.get("kode"):
        return data
    data = {
        "kode": buat_kode(rng=rng),
        "kedaluwarsa": kini + CAPTCHA_TTL_SEC,
        "percobaan": 0,
        "dibuat": kini,
    }
    kumpulan[uid] = data
    return data


def cocokkan_kode(
    guild_id: int, user_id: int, jawaban: str, *, sekarang: float | None = None
) -> str:
    """Cek jawaban member. Kode: ok / salah / habis / kedaluwarsa / tidak_ada."""
    gid, uid = int(guild_id), int(user_id)
    kini = sekarang if sekarang is not None else time.time()
    data = (captcha_pending.get(gid) or {}).get(uid)
    if not data or not data.get("kode"):
        return "tidak_ada"
    if float(data.get("kedaluwarsa") or 0) <= kini:
        captcha_pending[gid].pop(uid, None)
        return "kedaluwarsa"

    tebakan = "".join(str(jawaban or "").upper().split())
    if tebakan == str(data["kode"]).upper():
        captcha_pending[gid].pop(uid, None)
        return "ok"

    data["percobaan"] = int(data.get("percobaan") or 0) + 1
    if data["percobaan"] >= CAPTCHA_MAKS_PERCOBAAN:
        captcha_pending[gid].pop(uid, None)
        return "habis"
    return "salah"


def sisa_percobaan(guild_id: int, user_id: int) -> int:
    """Sisa percobaan untuk kode yang sedang aktif (0 bila tidak ada kode aktif)."""
    data = (captcha_pending.get(int(guild_id)) or {}).get(int(user_id))
    if not data:
        return 0
    return max(0, CAPTCHA_MAKS_PERCOBAAN - int(data.get("percobaan") or 0))


def bersihkan_kode(guild_id: int, user_id: int) -> bool:
    kumpulan = captcha_pending.get(int(guild_id)) or {}
    return kumpulan.pop(int(user_id), None) is not None


def statistik_captcha(guild_id: int) -> dict:
    cfg = verification_guilds.get(int(guild_id)) or {}
    return {
        "aktif": captcha_aktif(guild_id),
        "terpasang": bool(cfg.get("enabled")),
        "menunggu": len(captcha_pending.get(int(guild_id)) or {}),
        "ttl_detik": CAPTCHA_TTL_SEC,
        "maks_percobaan": CAPTCHA_MAKS_PERCOBAAN,
    }


def cleanup_captcha_runtime(limit: int = 500, *, sekarang: float | None = None) -> int:
    """Buang kode kedaluwarsa / server tanpa kode (hemat RAM)."""
    kini = sekarang if sekarang is not None else time.time()
    dibuang = 0
    for gid in list(captcha_pending):
        kumpulan = captcha_pending[gid]
        for uid in list(kumpulan):
            if dibuang >= limit:
                break
            if float((kumpulan.get(uid) or {}).get("kedaluwarsa") or 0) <= kini:
                kumpulan.pop(uid, None)
                dibuang += 1
        if not kumpulan:
            captcha_pending.pop(gid, None)
    return dibuang


def reset_captcha_state() -> None:
    captcha_pending.clear()


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
        ids = channel_targets.daftar(cfg, "backup_channel_id")
        if not ids:
            continue
        if now - float(cfg.get("last_backup_at") or 0) < interval:
            continue

        async def _kirim_backup(channel):
            ok, _ = await send_backup(bot, channel)
            if not ok:
                raise RuntimeError("backup gagal")

        if await channel_targets.sebarkan(bot, ids, _kirim_backup):
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
