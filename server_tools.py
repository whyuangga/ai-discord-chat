"""Perkakas server ringan: AFK, thread otomatis, & lockdown darurat.

Semua fitur di sini **0 kuota AI** dan menyimpan data sesedikit mungkin:
    - AFK      → `data/afk.json` (siapa, alasan, sejak kapan)
    - Thread   → `data/afk.json` bagian `threads` (channel mana yang auto-thread)
    - Lockdown → hanya di RAM (status darurat; aman hilang saat restart)
"""

import asyncio
import json
import logging
import time

import discord

from config import AFK_FILE, DATA_DIR

logger = logging.getLogger("gemini_bot.server_tools")

MAX_AFK_ENTRIES = 2000

afk_users: dict[int, dict[int, dict]] = {}          # guild_id -> {user_id: {reason, since}}
auto_thread_channels: dict[int, dict[int, dict]] = {}  # guild_id -> {channel_id: {archive, since}}
lockdown_state: dict[int, dict] = {}                # guild_id -> {channels: [ids], since, by}
_disk_lock = asyncio.Lock()


# ==============================================================================
# AFK
# ==============================================================================
def set_afk(guild_id: int, user_id: int, reason: str = "") -> dict:
    entry = {
        "reason": str(reason or "").strip()[:200] or "tanpa alasan",
        "since": time.time(),
    }
    afk_users.setdefault(int(guild_id), {})[int(user_id)] = entry
    _trim_afk()
    return entry


def pop_afk(guild_id: int, user_id: int) -> dict | None:
    """Menghapus status AFK (dipanggil saat member kembali bicara)."""
    return (afk_users.get(int(guild_id)) or {}).pop(int(user_id), None)


def get_afk(guild_id: int, user_id: int) -> dict | None:
    return (afk_users.get(int(guild_id)) or {}).get(int(user_id))


def afk_mentions(guild_id: int, content: str) -> list[tuple[int, dict]]:
    """Mendeteksi member AFK yang di-mention dalam sebuah pesan."""
    import re

    ids = {int(x) for x in re.findall(r"<@!?(\d+)>", str(content or ""))}
    found = []
    for user_id in ids:
        entry = get_afk(guild_id, user_id)
        if entry:
            found.append((user_id, entry))
    return found


def _trim_afk(limit: int = MAX_AFK_ENTRIES) -> int:
    """Membatasi jumlah entri AFK agar RAM tetap kecil."""
    total = sum(len(items) for items in afk_users.values())
    removed = 0
    if total <= limit:
        return 0
    for gid, items in afk_users.items():
        for user_id in sorted(items, key=lambda uid: float(items[uid].get("since", 0))):
            if total <= limit:
                break
            items.pop(user_id, None)
            total -= 1
            removed += 1
    return removed


def afk_since_text(entry: dict) -> str:
    delta = max(0, int(time.time() - float(entry.get("since") or 0)))
    if delta < 60:
        return f"{delta} detik"
    if delta < 3600:
        return f"{delta // 60} menit"
    if delta < 86400:
        return f"{delta // 3600} jam"
    return f"{delta // 86400} hari"


# ==============================================================================
# THREAD OTOMATIS
# ==============================================================================
def enable_auto_thread(guild_id: int, channel_id: int, *, archive_minutes: int = 1440) -> dict:
    config = {
        "archive": max(60, min(10080, int(archive_minutes))),
        "since": time.time(),
    }
    auto_thread_channels.setdefault(int(guild_id), {})[int(channel_id)] = config
    return config


def disable_auto_thread(guild_id: int, channel_id: int) -> bool:
    return (auto_thread_channels.get(int(guild_id)) or {}).pop(int(channel_id), None) is not None


def auto_thread_config(guild_id: int, channel_id: int) -> dict | None:
    return (auto_thread_channels.get(int(guild_id)) or {}).get(int(channel_id))


def list_auto_threads(guild_id: int) -> dict[int, dict]:
    return dict(auto_thread_channels.get(int(guild_id)) or {})


def thread_name_for(message: discord.Message) -> str:
    """Nama thread dari potongan awal pesan."""
    text = " ".join(str(getattr(message, "content", "") or "").split())
    if not text and getattr(message, "attachments", None):
        text = "lampiran"
    base = text[:60] or "diskusi"
    return base[:100]


# ==============================================================================
# LOCKDOWN
# ==============================================================================
def lockdown_active(guild_id: int) -> dict | None:
    return lockdown_state.get(int(guild_id))


async def start_lockdown(guild: discord.Guild, by_id: int, reason: str = "") -> tuple[int, int]:
    """Mencabut izin kirim @everyone di semua text channel. Mengembalikan (berhasil, gagal)."""
    if int(guild.id) in lockdown_state:
        return 0, 0

    changed: list[int] = []
    failed = 0
    for channel in list(guild.text_channels):
        overwrite = channel.overwrites_for(guild.default_role)
        if overwrite.send_messages is False:
            continue  # sudah terkunci sebelumnya, jangan diubah lagi
        try:
            await channel.set_permissions(
                guild.default_role, send_messages=False, reason=f"Lockdown oleh {by_id}: {reason[:90]}"
            )
            changed.append(channel.id)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    lockdown_state[int(guild.id)] = {
        "channels": changed,
        "since": time.time(),
        "by": int(by_id),
        "reason": str(reason or "")[:200],
    }
    return len(changed), failed


async def stop_lockdown(guild: discord.Guild) -> int:
    """Mengembalikan izin kirim channel yang sebelumnya dikunci oleh bot."""
    state = lockdown_state.pop(int(guild.id), None)
    if not state:
        return 0
    restored = 0
    for channel_id in state.get("channels") or []:
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            continue
        try:
            await channel.set_permissions(
                guild.default_role, send_messages=None, reason="Lockdown dicabut"
            )
            restored += 1
        except (discord.Forbidden, discord.HTTPException):
            continue
    return restored


# ==============================================================================
# PENYIMPANAN (AFK + THREAD)
# ==============================================================================
def load_server_tools_from_disk() -> tuple[int, int]:
    """Memuat AFK & konfigurasi thread otomatis dari data/afk.json."""
    if not AFK_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(AFK_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", AFK_FILE, exc)
        return 0, 0

    afk_total = 0
    for gid_str, items in (raw.get("afk") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        bucket: dict[int, dict] = {}
        for uid_str, entry in items.items():
            try:
                bucket[int(uid_str)] = {
                    "reason": str(entry.get("reason") or "tanpa alasan")[:200],
                    "since": float(entry.get("since") or time.time()),
                }
            except (TypeError, ValueError, AttributeError):
                continue
        if bucket:
            afk_users[gid] = bucket
            afk_total += len(bucket)

    threads_total = 0
    for gid_str, items in (raw.get("threads") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        bucket: dict[int, dict] = {}
        for cid_str, entry in items.items():
            try:
                bucket[int(cid_str)] = {
                    "archive": int(entry.get("archive") or 1440),
                    "since": float(entry.get("since") or time.time()),
                }
            except (TypeError, ValueError, AttributeError):
                continue
        if bucket:
            auto_thread_channels[gid] = bucket
            threads_total += len(bucket)
    return afk_total, threads_total


async def save_server_tools_to_disk() -> None:
    """Menyimpan AFK & konfigurasi thread otomatis secara atomik."""
    async with _disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "afk": {
                    str(gid): {str(uid): entry for uid, entry in items.items()}
                    for gid, items in afk_users.items()
                },
                "threads": {
                    str(gid): {str(cid): entry for cid, entry in items.items()}
                    for gid, items in auto_thread_channels.items()
                },
            }
            tmp = AFK_FILE.with_suffix(".json.tmp")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp.write_text, text, "utf-8")
            import os

            await asyncio.to_thread(os.replace, tmp, AFK_FILE)
        except Exception as exc:
            logger.warning("Gagal menyimpan afk.json: %s", exc)


def cleanup_server_tools_runtime(limit: int = 200) -> int:
    """Memangkas guild tak aktif dari memori."""
    removed = 0
    if len(auto_thread_channels) > limit:
        for gid in list(auto_thread_channels)[: len(auto_thread_channels) - limit]:
            auto_thread_channels.pop(gid, None)
            removed += 1
    _trim_afk()
    return removed
