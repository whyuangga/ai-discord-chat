"""Honeypot — channel jebakan untuk self-bot, skrip raid, & spam iklan.

Idenya sederhana dan **sangat efektif**: buat satu channel yang tidak boleh dipakai
siapa pun (biasanya diberi nama menarik seperti `#promo-gratis` atau `#hadiah`).
Warga asli membaca aturan dan tidak akan menyentuhnya; **skrip** & self-bot justru
menganggapnya sasaran empuk. Jadi pesan pertama di channel itu sudah cukup menjadi
bukti — tanpa analisis teks, tanpa ambang, tanpa false positive.

Aturan main (biar aman):
1. **Default `lapor`** — belum ada tindakan sampai Admin memilih `hapus`/`timeout`/`kick`/`ban`.
2. **Staf selalu aman** (`abaikan_staf`, default aktif): Admin / Manage Messages / Manage Guild.
3. **Bot diabaikan**, termasuk bot ini sendiri.
4. Pesan **selalu dihapus** saat mode bertindak, lalu kejadiannya dicatat ke channel log.
5. Maksimal 3 channel jebakan per server (`channel_targets` mendukung banyak channel).

Data disimpan di `data/honeypot.json` — 1 proses, tanpa database, 0 kuota AI.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import discord

from config import DATA_DIR, HONEYPOT_FILE, SPAM_TIMEOUT_SEC
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.honeypot")

_lock = asyncio.Lock()

#: Pilihan tindakan untuk channel jebakan.
AKSI_HONEYPOT: dict[str, str] = {
    "lapor": "👀 Lapor saja (tanpa tindakan)",
    "hapus": "🧹 Hapus pesan",
    "timeout": "⏳ Hapus + time-out member",
    "kick": "👢 Hapus + tendang (kick)",
    "ban": "🔨 Hapus + ban",
}

HONEYPOT_MAX_CHANNEL = 3

honeypot_guilds: dict[int, dict] = {}   # guild_id -> konfigurasi honeypot


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def default_config() -> dict:
    """Konfigurasi awal honeypot (paling aman: hanya melapor)."""
    return {
        "enabled": True,
        "channel_ids": [],
        "aksi": "lapor",
        "timeout_sec": int(SPAM_TIMEOUT_SEC),
        "log_channel_id": None,
        "abaikan_staf": True,
        "tangkap": 0,
        # Kejadian terakhir: {"user_id", "channel_id", "aksi", "at"}
        "terakhir": {},
    }


def _normalisasi(data: dict) -> dict:
    base = default_config()
    aksi = str(data.get("aksi") or base["aksi"]).lower()
    terakhir = data.get("terakhir") or {}
    base.update(
        {
            "enabled": bool(data.get("enabled", True)),
            "channel_ids": [
                _to_int(c) for c in (data.get("channel_ids") or []) if _to_int(c)
            ][:HONEYPOT_MAX_CHANNEL],
            "aksi": aksi if aksi in AKSI_HONEYPOT else "lapor",
            "timeout_sec": max(60, min(86400, _to_int(data.get("timeout_sec"), base["timeout_sec"]))),
            "log_channel_id": _to_int(data.get("log_channel_id")) or None,
            "abaikan_staf": bool(data.get("abaikan_staf", True)),
            "tangkap": max(0, _to_int(data.get("tangkap"))),
            "terakhir": (
                {
                    "user_id": _to_int(terakhir.get("user_id")),
                    "channel_id": _to_int(terakhir.get("channel_id")),
                    "aksi": str(terakhir.get("aksi") or ""),
                    "at": float(terakhir.get("at") or 0),
                }
                if isinstance(terakhir, dict)
                else {}
            ),
        }
    )
    if not base["channel_ids"]:
        base["enabled"] = False
    return base


def load_honeypot_from_disk() -> int:
    """Memuat konfigurasi honeypot semua server."""
    honeypot_guilds.clear()
    if not HONEYPOT_FILE.exists():
        return 0
    try:
        raw = json.loads(HONEYPOT_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", HONEYPOT_FILE, exc)
        return 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            honeypot_guilds[gid] = _normalisasi(data)
    return len(honeypot_guilds)


async def save_honeypot_to_disk() -> None:
    """Menyimpan konfigurasi honeypot secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(k): v for k, v in honeypot_guilds.items()}}
            sementara = Path(str(HONEYPOT_FILE) + ".tmp")
            await asyncio.to_thread(
                sementara.write_text, json.dumps(payload, ensure_ascii=False, indent=2), "utf-8"
            )
            await asyncio.to_thread(os.replace, sementara, HONEYPOT_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan honeypot.json: %s", sanitize_error_message(exc))


def get_config(guild_id: int) -> dict:
    """Konfigurasi honeypot server (dibuat aman bila belum ada)."""
    gid = _to_int(guild_id)
    cfg = honeypot_guilds.get(gid)
    if cfg is None:
        cfg = default_config()
        honeypot_guilds[gid] = cfg
    cfg.setdefault("channel_ids", [])
    return cfg


def peek_config(guild_id: int) -> dict:
    """Baca konfigurasi tanpa membuat entri baru (dipakai dashboard)."""
    cfg = honeypot_guilds.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def status(guild_id: int) -> dict:
    """Ringkasan untuk dashboard & `/keamanan honeypot-status`."""
    cfg = peek_config(guild_id)
    return {
        "aktif": bool(cfg.get("enabled")) and bool(cfg.get("channel_ids")),
        "aksi": str(cfg.get("aksi") or "lapor"),
        "label_aksi": AKSI_HONEYPOT.get(str(cfg.get("aksi") or "lapor"), ""),
        "channel_ids": list(cfg.get("channel_ids") or []),
        "timeout_sec": _to_int(cfg.get("timeout_sec"), int(SPAM_TIMEOUT_SEC)),
        "log_channel_id": _to_int(cfg.get("log_channel_id")) or 0,
        "abaikan_staf": bool(cfg.get("abaikan_staf", True)),
        "tangkap": _to_int(cfg.get("tangkap")),
        "terakhir": dict(cfg.get("terakhir") or {}),
        "batas_channel": HONEYPOT_MAX_CHANNEL,
    }


def set_honeypot(
    guild_id: int,
    *,
    channel_ids: list[int] | None = None,
    aksi: str | None = None,
    timeout_sec: int | None = None,
    log_channel_id: int | None = None,
    abaikan_staf: bool | None = None,
    enabled: bool | None = None,
) -> dict | None:
    """Mengubah setelan honeypot. `enabled=False` mematikan tanpa menghapus channel."""
    gid = _to_int(guild_id)
    if enabled is False:
        cfg = honeypot_guilds.get(gid)
        if cfg is None:
            return None
        cfg["enabled"] = False
        return cfg

    cfg = get_config(gid)
    cfg["enabled"] = True
    if channel_ids is not None:
        bersih = []
        for cid in channel_ids:
            nilai = _to_int(cid)
            if nilai and nilai not in bersih:
                bersih.append(nilai)
        cfg["channel_ids"] = bersih[:HONEYPOT_MAX_CHANNEL]
    if aksi is not None:
        kunci = str(aksi).strip().lower()
        if kunci in AKSI_HONEYPOT:
            cfg["aksi"] = kunci
    if timeout_sec is not None:
        cfg["timeout_sec"] = max(60, min(86400, int(timeout_sec)))
    if log_channel_id is not None:
        cfg["log_channel_id"] = _to_int(log_channel_id) or None
    if abaikan_staf is not None:
        cfg["abaikan_staf"] = bool(abaikan_staf)
    if not cfg.get("channel_ids"):
        cfg["enabled"] = False
    return cfg


def clear_honeypot(guild_id: int) -> bool:
    """Menghapus setelan honeypot server sepenuhnya."""
    return honeypot_guilds.pop(_to_int(guild_id), None) is not None


def is_honeypot_channel(guild_id: int, channel_id: int) -> bool:
    """True bila channel ini termasuk channel jebakan yang aktif."""
    cfg = honeypot_guilds.get(_to_int(guild_id))
    if not cfg or not cfg.get("enabled"):
        return False
    return _to_int(channel_id) in {_to_int(c) for c in cfg.get("channel_ids") or []}


def handle_channel_delete(channel) -> bool:
    """Membuang channel jebakan yang sudah dihapus dari daftar."""
    cid = _to_int(getattr(channel, "id", 0))
    gid = _to_int(getattr(getattr(channel, "guild", None), "id", 0))
    if not cid:
        return False
    berubah = False
    for cfg in honeypot_guilds.values():
        ids = list(cfg.get("channel_ids") or [])
        if cid in ids:
            cfg["channel_ids"] = [c for c in ids if c != cid]
            if not cfg["channel_ids"]:
                cfg["enabled"] = False
            berubah = True
    if berubah and gid:
        logger.info("Channel jebakan %s terhapus — honeypot server %s diperbarui.", cid, gid)
    return berubah


# ==============================================================================
# EVALUASI & TINDAKAN
# ==============================================================================
def _is_staff(member) -> bool:
    """Admin/pengurus dianggap staf (selalu dikecualikan secara bawaan)."""
    if member is None:
        return False
    if _to_int(getattr(member, "id", 0)) == _to_int(getattr(member, "guild", None) and getattr(member.guild, "owner_id", 0)):
        return True
    perms = getattr(member, "guild_permissions", None)
    if perms is None:
        return False
    return bool(
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_messages", False)
        or getattr(perms, "manage_guild", False)
    )


def akan_tertangkap(
    guild_id: int,
    channel_id: int,
    *,
    is_bot: bool = False,
    is_staf: bool = False,
) -> dict:
    """Simulasi keputusan honeypot — **tanpa** tindakan apa pun (dipakai penguji dashboard)."""
    cfg = peek_config(guild_id)
    aktif = bool(cfg.get("enabled")) and bool(cfg.get("channel_ids"))
    if not aktif:
        return {
            "kena": False,
            "alasan": "Honeypot belum aktif (belum ada channel jebakan).",
            "aksi": "lapor",
        }
    if _to_int(channel_id) not in {_to_int(c) for c in cfg.get("channel_ids") or []}:
        return {
            "kena": False,
            "alasan": f"Channel `{_to_int(channel_id)}` bukan channel jebakan.",
            "aksi": "lapor",
        }
    if is_bot:
        return {"kena": False, "alasan": "Pesan dari bot selalu diabaikan.", "aksi": "lapor"}
    if is_staf and cfg.get("abaikan_staf", True):
        return {
            "kena": False,
            "alasan": "Staf/pengurus dikecualikan (setelan *abaikan staf* aktif).",
            "aksi": "lapor",
        }
    aksi = str(cfg.get("aksi") or "lapor")
    return {
        "kena": True,
        "alasan": f"Pesan pertama di channel jebakan → tindakan `{AKSI_HONEYPOT.get(aksi, aksi)}`.",
        "aksi": aksi,
    }


def build_log_embed(guild, member, channel, cfg: dict) -> discord.Embed:
    """Embed laporan kejadian honeypot untuk channel log."""
    aksi = str(cfg.get("aksi") or "lapor")
    embed = discord.Embed(
        title="🪤 Honeypot menangkap pesan",
        description=(
            f"{getattr(member, 'mention', '-')} menulis di channel jebakan "
            f"{getattr(channel, 'mention', '-')}.\n"
            "Channel ini **tidak boleh dipakai siapa pun** — pesan pertama dianggap bukti "
            "spam/self-bot."
        ),
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Tindakan", value=AKSI_HONEYPOT.get(aksi, aksi), inline=True)
    embed.add_field(name="Channel", value=f"<#{_to_int(getattr(channel, 'id', 0))}>", inline=True)
    embed.add_field(
        name="Member",
        value=f"{getattr(member, 'display_name', '-')} (`{_to_int(getattr(member, 'id', 0))}`)",
        inline=False,
    )
    embed.set_footer(text=str(getattr(guild, "name", ""))[:80])
    return embed


async def _kirim_log(bot, guild, embed, cfg: dict) -> bool:
    """Mengirim laporan honeypot ke channel log (bila ada & bisa diakses)."""
    cid = _to_int(cfg.get("log_channel_id"))
    if not cid:
        return False
    channel = None
    getter = getattr(bot, "get_channel", None) if bot is not None else None
    if callable(getter):
        channel = getter(cid)
    if channel is None and guild is not None:
        channel = guild.get_channel(cid)
    if channel is None:
        return False
    try:
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:  # pragma: no cover
        logger.info("Gagal mengirim laporan honeypot: %s", sanitize_error_message(exc))
        return False


async def handle_honeypot(message, *, bot=None) -> bool:
    """Menindak pesan di channel jebakan. `True` bila pesan sudah ditangani."""
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    if guild is None or author is None or channel is None:
        return False
    if getattr(author, "bot", False):
        return False

    gid = _to_int(getattr(guild, "id", 0))
    cid = _to_int(getattr(channel, "id", 0))
    if not is_honeypot_channel(gid, cid):
        return False

    cfg = honeypot_guilds.get(gid) or {}
    if cfg.get("abaikan_staf", True) and _is_staff(author):
        return False

    aksi = str(cfg.get("aksi") or "lapor")

    if aksi != "lapor":
        delete = getattr(message, "delete", None)
        if callable(delete):
            try:
                await delete()
            except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
                logger.warning("Gagal menghapus pesan honeypot: %s", sanitize_error_message(exc))

    if aksi == "timeout":
        timeout = getattr(author, "timeout", None)
        if callable(timeout):
            import datetime as _dt

            try:
                await timeout(
                    _dt.timedelta(seconds=_to_int(cfg.get("timeout_sec"), int(SPAM_TIMEOUT_SEC))),
                    reason="Honeypot: menulis di channel jebakan",
                )
            except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
                logger.warning("Gagal time-out dari honeypot: %s", sanitize_error_message(exc))

    if aksi in ("kick", "ban"):
        metode = getattr(author, aksi, None)
        if callable(metode):
            try:
                await metode(reason="Honeypot: menulis di channel jebakan")
            except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
                logger.warning("Gagal %s member dari honeypot: %s", aksi, sanitize_error_message(exc))

    cfg["tangkap"] = _to_int(cfg.get("tangkap")) + 1
    cfg["terakhir"] = {
        "user_id": _to_int(getattr(author, "id", 0)),
        "channel_id": cid,
        "aksi": aksi,
        "at": time.time(),
    }
    await _kirim_log(bot, guild, build_log_embed(guild, author, channel, cfg), cfg)
    await save_honeypot_to_disk()
    logger.info(
        "Honeypot server %s: %s menulis di channel jebakan %s (aksi: %s)",
        gid, _to_int(getattr(author, "id", 0)), cid, aksi,
    )
    return True


def reset_runtime_state() -> None:
    """Membersihkan state (dipakai tes)."""
    honeypot_guilds.clear()
