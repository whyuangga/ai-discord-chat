"""Identitas kustom per pesan — kirim pesan dengan **nama & avatar sendiri** lewat webhook.

Ide ini dipinjam dari Discohook: pesan tidak harus tampil sebagai bot, bisa sebagai
"📢 Pengumuman Server", "🎉 Tim Event", dan seterusnya. Tanpa kuota AI, tanpa dependency
baru — hanya webhook Discord biasa.

Cara kerja:
1. Bot mencari webhook miliknya di channel tujuan (dibuat sekali, lalu di-*cache* di
   `data/webhooks.json` supaya tidak membuat webhook baru setiap kali).
2. Pesan dikirim lewat webhook tersebut dengan `username` & `avatar_url` khusus.

Keamanan:
- Butuh izin **Manage Webhooks** di channel tujuan; pesan tetap dikirim atas nama admin
  yang menjalankannya (tercatat di audit log bila aktif).
- Mention massal dinonaktifkan (`AllowedMentions.none()`) agar tidak bisa dipakai
  men-*ping* @everyone diam-diam.
- Nama dibatasi 80 karakter, avatar wajib URL `http(s)`, isi 2000 karakter / embed 4000.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import discord

from config import DATA_DIR

logger = logging.getLogger("gemini_bot.webhook_identity")

WEBHOOK_FILE = DATA_DIR / "webhooks.json"

MAX_NAME = 80
MAX_CONTENT = 2000
MAX_EMBED_DESCRIPTION = 4000
MAX_TITLE = 256
DEFAULT_WEBHOOK_NAME = "AI Discord Chat"

_lock = asyncio.Lock()

# "guild_id:channel_id" -> {"webhook_id": int, "url": str}
_cache: dict[str, dict] = {}


def _key(channel) -> str:
    guild_id = getattr(getattr(channel, "guild", None), "id", 0) or 0
    return f"{int(guild_id)}:{int(getattr(channel, 'id', 0) or 0)}"


def valid_name(name: str | None) -> tuple[bool, str]:
    """Nama tampilan webhook: 1–80 karakter."""
    bersih = str(name or "").strip()
    if not bersih:
        return False, "Nama tidak boleh kosong."
    if len(bersih) > MAX_NAME:
        return False, f"Nama maksimal **{MAX_NAME} karakter**."
    return True, bersih


def valid_avatar(url: str | None) -> tuple[bool, str | None]:
    """Avatar opsional; harus URL http(s)."""
    bersih = str(url or "").strip()
    if not bersih:
        return True, None
    if not bersih.startswith(("http://", "https://")):
        return False, None
    return True, bersih[:512]


# ------------------------------------------------------------------------------
# CACHE WEBHOOK (data/webhooks.json)
# ------------------------------------------------------------------------------
def remember(channel, webhook) -> None:
    """Simpan webhook hasil buat/temukan ke cache."""
    _cache[_key(channel)] = {
        "webhook_id": int(getattr(webhook, "id", 0) or 0),
        "url": str(getattr(webhook, "url", "") or ""),
    }


def forget(channel) -> None:
    _cache.pop(_key(channel), None)


def cached_webhook_id(channel) -> int:
    return int((_cache.get(_key(channel)) or {}).get("webhook_id") or 0)


async def save_to_disk() -> None:
    """Tulis cache webhook ke `data/webhooks.json` (atomik)."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = Path(str(WEBHOOK_FILE) + ".tmp")
            serialized = json.dumps(_cache, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp, WEBHOOK_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan webhooks.json: %s", exc)


def load_from_disk() -> int:
    """Muat cache webhook; entri rusak dilewati."""
    _cache.clear()
    path = Path(WEBHOOK_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0
    if not isinstance(raw, dict):
        return 0
    for key, data in raw.items():
        if not isinstance(data, dict):
            continue
        webhook_id = int(data.get("webhook_id") or 0)
        url = str(data.get("url") or "")
        if webhook_id and url.startswith("https://"):
            _cache[str(key)] = {"webhook_id": webhook_id, "url": url}
    return len(_cache)


# ------------------------------------------------------------------------------
# WEBHOOK: CARI / BUAT
# ------------------------------------------------------------------------------
async def ensure_webhook(channel) -> tuple[discord.Webhook | None, str]:
    """Webhook milik bot di channel ini — dipakai ulang bila sudah ada.

    Mengembalikan `(webhook, alasan_gagal)`.
    """
    if not hasattr(channel, "webhooks"):
        return None, "Channel ini tidak mendukung webhook."

    me = getattr(getattr(channel, "guild", None), "me", None)
    perms = getattr(me, "guild_permissions", None)
    if perms is not None and not getattr(perms, "manage_webhooks", False):
        return None, "Bot butuh izin **Manage Webhooks** di channel ini."

    # 1. Coba webhook yang sudah di-cache
    webhook_id = cached_webhook_id(channel)
    if webhook_id:
        fetch = getattr(channel.guild, "fetch_webhook", None)
        if callable(fetch):
            try:
                webhook = await fetch(webhook_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                webhook = None
            except Exception:  # pragma: no cover - jaring aman
                webhook = None
            if webhook is not None:
                remember(channel, webhook)
                return webhook, ""

    # 2. Cari webhook milik bot di channel
    try:
        hooks = await channel.webhooks()
    except (discord.Forbidden, discord.HTTPException):
        return None, "Bot tidak bisa membaca daftar webhook channel ini."
    bot_user = getattr(getattr(channel, "guild", None), "me", None)
    for hook in hooks or []:
        if getattr(hook, "user", None) == bot_user or getattr(hook, "owner", None) == bot_user:
            remember(channel, hook)
            return hook, ""

    # 3. Buat baru
    try:
        hook = await channel.create_webhook(name=DEFAULT_WEBHOOK_NAME, reason="Identitas kustom pesan")
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal membuat webhook: %s", exc)
        return None, "Gagal membuat webhook — pastikan bot punya izin **Manage Webhooks**."
    remember(channel, hook)
    return hook, ""


# ------------------------------------------------------------------------------
# KIRIM PESAN
# ------------------------------------------------------------------------------
def build_message_kwargs(
    *,
    nama: str,
    avatar: str | None = None,
    judul: str | None = None,
    isi: str | None = None,
    warna: discord.Colour | None = None,
    footer: str | None = None,
) -> dict:
    """Susun argumen `webhook.send()`: teks biasa, atau embed bila ada judul/warna/footer."""
    kwargs: dict = {"username": nama[:MAX_NAME], "allowed_mentions": discord.AllowedMentions.none()}
    if avatar:
        kwargs["avatar_url"] = avatar

    teks = str(isi or "").strip()
    judul_bersih = str(judul or "").strip()
    if judul_bersih or footer or warna is not None:
        embed = discord.Embed(
            title=(judul_bersih[:MAX_TITLE] or None),
            description=teks[:MAX_EMBED_DESCRIPTION] or None,
            colour=warna or discord.Colour.blurple(),
        )
        if footer:
            embed.set_footer(text=str(footer)[:200])
        kwargs["embed"] = embed
        if not judul_bersih and not teks:
            kwargs["content"] = "​"
    else:
        kwargs["content"] = teks[:MAX_CONTENT] or "​"
    return kwargs


async def kirim_sebagai(
    channel,
    *,
    nama: str,
    isi: str | None = None,
    judul: str | None = None,
    avatar: str | None = None,
    warna: discord.Colour | None = None,
    footer: str | None = None,
) -> tuple[bool, str]:
    """Kirim pesan dengan identitas kustom. `(berhasil, keterangan)`."""
    ok, alasan = valid_name(nama)
    if not ok:
        return False, alasan
    ok_avatar, avatar_bersih = valid_avatar(avatar)
    if not ok_avatar:
        return False, "Avatar harus URL `http://` atau `https://`."

    webhook, galat = await ensure_webhook(channel)
    if webhook is None:
        return False, galat or "Webhook tidak tersedia."

    kwargs = build_message_kwargs(
        nama=alasan,
        avatar=avatar_bersih,
        judul=judul,
        isi=isi,
        warna=warna,
        footer=footer,
    )
    try:
        await webhook.send(**kwargs)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Kirim via webhook gagal: %s", exc)
        forget(channel)
        return False, "Discord menolak pesan webhook itu. Webhook lama mungkin sudah dihapus."
    return True, ""


async def hapus_webhook(channel) -> tuple[bool, str]:
    """Hapus webhook yang di-cache di channel ini (bersih-bersih)."""
    webhook, galat = await ensure_webhook(channel)
    if webhook is None:
        return False, galat or "Webhook tidak ditemukan."
    try:
        await webhook.delete(reason="Pembersihan identitas kustom")
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal menghapus webhook: %s", exc)
        return False, "Gagal menghapus webhook — cek izin bot."
    forget(channel)
    return True, ""


def stats() -> dict:
    """Ringkasan cache (dipakai `/status` atau tes)."""
    return {"channels": len(_cache)}


__all__ = [
    "MAX_NAME",
    "build_message_kwargs",
    "cached_webhook_id",
    "ensure_webhook",
    "forget",
    "hapus_webhook",
    "kirim_sebagai",
    "load_from_disk",
    "remember",
    "save_to_disk",
    "stats",
    "valid_avatar",
    "valid_name",
]
