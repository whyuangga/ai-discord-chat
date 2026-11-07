"""Channel informasi yang **menyegarkan dirinya sendiri** (aturan & info server).

Ala bot besar: satu channel baca-saja berisi aturan/info penting. Admin cukup menulis isinya
sekali di `/kanal-info isi` (atau dashboard); bot menerbitkan **satu pesan embed** lalu
**mengedit pesan yang sama** setiap kali isinya berubah — jadi channel tidak penuh pesan lama.

0 kuota AI · tanpa proses latar baru (menumpang watcher yang sudah ada) · isi disimpan
di `data/info_channel.json` karena memang teks yang ditampilkan publik di server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time

from config import INFO_CHANNEL_FILE

logger = logging.getLogger("gemini_bot.info_channel")

JUDUL_BAWAAN = "ℹ️ Informasi Server"
MAKS_ISI = 3500          # aman di bawah batas 4096 karakter description embed
MIN_ISI = 20
MAKS_JUDUL = 200
INTERVAL_BAWAAN = 60     # menit (verifikasi ulang pesan masih ada)
INTERVAL_MIN = 5
INTERVAL_MAKS = 1440

info_guilds: dict[int, dict] = {}


# ==============================================================================
# SETELAN
# ==============================================================================
def default_config() -> dict:
    return {
        "enabled": False,
        "channel_id": None,
        "judul": JUDUL_BAWAAN,
        "isi": "",
        "warna": "#5865F2",
        "interval_menit": INTERVAL_BAWAAN,
        "pesan_id": 0,
        "terakhir": 0.0,
    }


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _warna_sah(nilai: str) -> str:
    teks = str(nilai or "").strip()
    if teks.startswith("#") and len(teks) == 7:
        try:
            int(teks[1:], 16)
            return teks.lower()
        except ValueError:
            return "#5865f2"
    return "#5865f2"


def peek_config(guild_id: int) -> dict:
    return {**default_config(), **dict(info_guilds.get(int(guild_id)) or {})}


def get_config(guild_id: int) -> dict:
    return info_guilds.setdefault(int(guild_id), default_config())


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    channel_id: int | None = None,
    judul: str | None = None,
    warna: str | None = None,
    interval_menit: int | None = None,
) -> dict:
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if channel_id is not None:
        baru = _to_int(channel_id) or None
        if baru != cfg.get("channel_id"):
            cfg["channel_id"] = baru
            cfg["pesan_id"] = 0     # channel baru ⇒ terbitkan pesan baru
            cfg["terakhir"] = 0.0
    if judul is not None:
        teks = str(judul).strip()[:MAKS_JUDUL]
        if teks:
            cfg["judul"] = teks
    if warna is not None:
        cfg["warna"] = _warna_sah(warna)
    if interval_menit is not None:
        cfg["interval_menit"] = max(INTERVAL_MIN, min(INTERVAL_MAKS, _to_int(interval_menit, INTERVAL_BAWAAN)))
    return cfg


def set_isi(guild_id: int, teks: str) -> tuple[bool, str]:
    """Ganti isi channel info. `(berhasil, pesan)`."""
    bersih = str(teks or "").strip()
    if len(bersih) < MIN_ISI:
        return False, f"Isi terlalu pendek (minimal {MIN_ISI} huruf)."
    if len(bersih) > MAKS_ISI:
        return False, f"Isi terlalu panjang (maksimal {MAKS_ISI} huruf)."
    cfg = get_config(guild_id)
    cfg["isi"] = bersih
    return True, "Isi channel info diperbarui."


def aktif(guild_id: int) -> bool:
    cfg = peek_config(guild_id)
    return bool(cfg["enabled"] and cfg["channel_id"] and cfg["isi"])


def isi_hash(guild_id: int) -> str:
    cfg = peek_config(guild_id)
    bahan = f"{cfg['judul']}\x00{cfg['isi']}\x00{cfg['warna']}"
    return hashlib.sha1(bahan.encode("utf-8")).hexdigest()[:16]


def perlu_segarkan(guild_id: int) -> bool:
    """Perlu menerbitkan/mengedit pesan? (isi berubah atau pesan belum ada)."""
    if not aktif(guild_id):
        return False
    cfg = peek_config(guild_id)
    return bool(cfg["pesan_id"] == 0 or cfg.get("hash") != isi_hash(guild_id))


def perlu_verifikasi(guild_id: int, sekarang: float | None = None) -> bool:
    """Pesan sudah terbit tapi perlu dicek masih ada (interval sudah lewat)."""
    if not aktif(guild_id):
        return False
    cfg = peek_config(guild_id)
    if not cfg["pesan_id"]:
        return False
    batas = max(INTERVAL_MIN, _to_int(cfg.get("interval_menit"), INTERVAL_BAWAAN)) * 60
    return (sekarang if sekarang is not None else time.time()) - float(cfg.get("terakhir") or 0) >= batas


def catat_pesan(guild_id: int, pesan_id: int, sekarang: float | None = None) -> dict:
    cfg = get_config(guild_id)
    cfg["pesan_id"] = _to_int(pesan_id)
    cfg["hash"] = isi_hash(guild_id)
    cfg["terakhir"] = sekarang if sekarang is not None else time.time()
    return cfg


def statistik(guild_id: int) -> dict:
    cfg = peek_config(guild_id)
    return {
        **cfg,
        "aktif": aktif(guild_id),
        "panjang_isi": len(cfg["isi"]),
        "perlu_segarkan": perlu_segarkan(guild_id),
    }


# ==============================================================================
# EMBED & PENYEGARAN
# ==============================================================================
def build_embed(guild_id: int, *, sekarang: float | None = None):
    """Embed channel info (judul + isi + footer waktu)."""
    import discord

    cfg = peek_config(guild_id)
    embed = discord.Embed(
        title=cfg["judul"][:256],
        description=(cfg["isi"] or "_(belum diisi)_")[:4096],
        colour=discord.Colour(int(cfg["warna"].lstrip("#"), 16)),
    )
    embed.set_footer(
        text="Diperbarui otomatis · "
        + time.strftime("%d %b %Y %H:%M", time.localtime(sekarang or time.time()))
    )
    return embed


async def segarkan(bot, guild_id: int, *, sekarang: float | None = None) -> str:
    """Terbitkan atau edit pesan info. Kembalikan status: dibuat/diperbarui/sama/gagal."""
    gid = int(guild_id or 0)
    if not aktif(gid):
        return "nonaktif"

    cfg = peek_config(gid)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    if guild is None:
        return "gagal"

    get_channel = getattr(guild, "get_channel", None)
    channel = get_channel(_to_int(cfg["channel_id"])) if callable(get_channel) else None
    if channel is None:
        return "gagal"

    embed = build_embed(gid, sekarang=sekarang)
    pesan_id = _to_int(cfg.get("pesan_id"))

    if pesan_id:
        try:
            pesan = await channel.fetch_message(pesan_id)
            await pesan.edit(embed=embed, allowed_mentions=None)
            catat_pesan(gid, pesan_id, sekarang)
            await save_info_channel_to_disk()
            return "diperbarui"
        except Exception as exc:  # pesan hilang / izin — buat lagi di bawah
            logger.debug("Pesan info %s tidak bisa diedit: %s", pesan_id, exc)

    try:
        baru = await channel.send(embed=embed)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal mengirim pesan channel info: %s", exc)
        return "gagal"

    catat_pesan(gid, getattr(baru, "id", 0), sekarang)
    await save_info_channel_to_disk()
    return "dibuat"


async def run_info_channel_check(bot, *, sekarang: float | None = None) -> int:
    """Panggilan watcher: segarkan semua server yang perlu. Kembalikan jumlah aksi."""
    jumlah = 0
    for gid in list(info_guilds):
        if perlu_segarkan(gid) or perlu_verifikasi(gid, sekarang):
            status = await segarkan(bot, gid, sekarang=sekarang)
            if status in ("dibuat", "diperbarui"):
                jumlah += 1
    return jumlah


# ==============================================================================
# PEMBERSIHAN & PENYIMPANAN
# ==============================================================================
def reset_runtime_state() -> None:
    info_guilds.clear()


def cleanup_info_channel_runtime(limit: int = 500) -> int:
    """Buang server tanpa channel & tanpa isi aktif."""
    dibuang = 0
    for gid in list(info_guilds):
        if dibuang >= limit:
            break
        cfg = peek_config(gid)
        if not cfg["enabled"] and not cfg["channel_id"] and not cfg["isi"]:
            info_guilds.pop(gid, None)
            dibuang += 1
    return dibuang


def load_info_channel_from_disk() -> int:
    """Muat setelan channel info. Kembalikan jumlah server termuat."""
    try:
        raw = json.loads(INFO_CHANNEL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(raw, dict):
        return 0

    jumlah = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        if not str(gid_str).isdigit() or not isinstance(data, dict):
            continue
        gid = int(gid_str)
        cfg = default_config()
        cfg["enabled"] = bool(data.get("enabled"))
        cfg["channel_id"] = _to_int(data.get("channel_id")) or None
        cfg["judul"] = str(data.get("judul") or JUDUL_BAWAAN)[:MAKS_JUDUL]
        cfg["isi"] = str(data.get("isi") or "")[:MAKS_ISI]
        cfg["warna"] = _warna_sah(str(data.get("warna") or ""))
        cfg["interval_menit"] = max(
            INTERVAL_MIN, min(INTERVAL_MAKS, _to_int(data.get("interval_menit"), INTERVAL_BAWAAN))
        )
        cfg["pesan_id"] = _to_int(data.get("pesan_id"))
        cfg["hash"] = str(data.get("hash") or "")
        cfg["terakhir"] = float(data.get("terakhir") or 0.0)
        info_guilds[gid] = cfg
        jumlah += 1
    return jumlah


async def save_info_channel_to_disk() -> None:
    """Tulis state ke `data/info_channel.json` (atomik)."""
    import asyncio

    data = {"guilds": {str(gid): cfg for gid, cfg in info_guilds.items() if cfg.get("channel_id") or cfg.get("isi")}}
    teks = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def _tulis() -> None:
        try:
            INFO_CHANNEL_FILE.parent.mkdir(parents=True, exist_ok=True)
            sementara = INFO_CHANNEL_FILE.with_suffix(".tmp")
            sementara.write_text(teks, encoding="utf-8")
            os.replace(sementara, INFO_CHANNEL_FILE)
        except OSError:  # pragma: no cover - disk penuh/izin
            logger.exception("Gagal menyimpan channel info")

    await asyncio.to_thread(_tulis)


__all__ = [
    "INTERVAL_BAWAAN",
    "JUDUL_BAWAAN",
    "MAKS_ISI",
    "aktif",
    "build_embed",
    "catat_pesan",
    "cleanup_info_channel_runtime",
    "default_config",
    "get_config",
    "isi_hash",
    "load_info_channel_from_disk",
    "peek_config",
    "perlu_segarkan",
    "perlu_verifikasi",
    "reset_runtime_state",
    "run_info_channel_check",
    "save_info_channel_to_disk",
    "segarkan",
    "set_config",
    "set_isi",
    "statistik",
]
