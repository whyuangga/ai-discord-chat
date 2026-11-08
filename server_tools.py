"""Perkakas server ringan: AFK, thread otomatis, & lockdown darurat.

Semua fitur di sini **0 kuota AI** dan menyimpan data sesedikit mungkin:
    - AFK      → `data/afk.json` (siapa, alasan, sejak kapan)
    - Thread   → `data/afk.json` bagian `threads` (channel mana yang auto-thread)
    - Lockdown → `data/lockdown.json` (izin awal tiap channel untuk pemulihan setelah restart)
"""

import asyncio
import json
import logging
import os
import time

import discord

from config import AFK_FILE, DATA_DIR

logger = logging.getLogger("gemini_bot.server_tools")

MAX_AFK_ENTRIES = 2000
LOCKDOWN_FILE = DATA_DIR / "lockdown.json"

afk_users: dict[int, dict[int, dict]] = {}          # guild_id -> {user_id: {reason, since}}
auto_thread_channels: dict[int, dict[int, dict]] = {}  # guild_id -> {channel_id: {archive, since}}
# guild_id -> {channels: [{id, send_messages}], since, by, reason, recovered?}
lockdown_state: dict[int, dict] = {}
_disk_lock = asyncio.Lock()
_lockdown_disk_lock = asyncio.Lock()
_lockdown_operation_lock = asyncio.Lock()


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


def load_lockdowns_from_disk() -> int:
    """Muat lockdown tertunda; tidak mengubah izin Discord secara otomatis."""
    lockdown_state.clear()
    try:
        raw = json.loads(LOCKDOWN_FILE.read_text(encoding="utf-8")) if LOCKDOWN_FILE.exists() else {}
    except Exception as exc:
        logger.warning("Gagal memuat pemulihan lockdown dari %s: %s", LOCKDOWN_FILE, exc)
        return 0
    if not isinstance(raw, dict):
        logger.warning("Format pemulihan lockdown di %s tidak valid.", LOCKDOWN_FILE)
        return 0

    for guild_key, item in raw.items():
        if not isinstance(item, dict):
            continue
        try:
            guild_id = int(guild_key)
            since = float(item.get("since") or time.time())
            by_id = int(item.get("by") or 0)
        except (TypeError, ValueError):
            continue
        if guild_id <= 0:
            continue
        channels = []
        for channel in item.get("channels") or []:
            if not isinstance(channel, dict):
                continue
            try:
                channel_id = int(channel.get("id") or 0)
            except (TypeError, ValueError):
                continue
            previous = channel.get("send_messages", "invalid")
            if channel_id <= 0 or not (previous is None or isinstance(previous, bool)):
                continue
            channels.append({"id": channel_id, "send_messages": previous})
        if channels:
            lockdown_state[guild_id] = {
                "channels": channels,
                "since": since,
                "by": by_id,
                "reason": str(item.get("reason") or "")[:200],
                "recovered": True,
            }
    return len(lockdown_state)


async def _save_lockdowns_to_disk() -> bool:
    """Simpan izin awal sebelum mutasi Discord agar restart tetap bisa dipulihkan."""
    payload = {
        str(guild_id): {
            "channels": [
                {"id": int(channel["id"]), "send_messages": channel["send_messages"]}
                for channel in state.get("channels") or []
            ],
            "since": float(state.get("since") or time.time()),
            "by": int(state.get("by") or 0),
            "reason": str(state.get("reason") or "")[:200],
        }
        for guild_id, state in lockdown_state.items()
        if state.get("channels")
    }

    async with _lockdown_disk_lock:
        try:
            def write_file() -> None:
                LOCKDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
                if not payload:
                    LOCKDOWN_FILE.unlink(missing_ok=True)
                    return
                temporary = LOCKDOWN_FILE.with_suffix(LOCKDOWN_FILE.suffix + ".tmp")
                temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temporary, LOCKDOWN_FILE)

            await asyncio.to_thread(write_file)
            return True
        except OSError as exc:
            logger.error("Gagal menyimpan pemulihan lockdown ke %s: %s", LOCKDOWN_FILE, exc)
            return False


async def start_lockdown(guild: discord.Guild, by_id: int, reason: str = "") -> tuple[int, int]:
    """Kunci text channel dan simpan izin awalnya; hasil = (berhasil, gagal)."""
    guild_id = int(guild.id)
    async with _lockdown_operation_lock:
        if guild_id in lockdown_state:
            return 0, 0

        state = {
            "channels": [],
            "since": time.time(),
            "by": int(by_id),
            "reason": str(reason or "")[:200],
            "recovered": False,
        }
        lockdown_state[guild_id] = state
        changed = 0
        failed = 0
        for channel in list(guild.text_channels):
            previous = channel.overwrites_for(guild.default_role).send_messages
            if previous is False:
                continue  # sudah terkunci sebelum bot; jangan diubah atau dipulihkan

            record = {"id": int(channel.id), "send_messages": previous}
            state["channels"].append(record)
            # Tulis niat pemulihan sebelum mengubah izin Discord. Jika penyimpanan gagal,
            # jangan mengunci channel tanpa catatan yang bisa dipakai setelah restart.
            if not await _save_lockdowns_to_disk():
                state["channels"].remove(record)
                failed += 1
                break
            try:
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=False,
                    reason=f"Lockdown oleh {by_id}: {reason[:90]}",
                )
                changed += 1
            except (discord.Forbidden, discord.HTTPException) as exc:
                state["channels"].remove(record)
                await _save_lockdowns_to_disk()
                logger.warning("Gagal mengunci channel %s di guild %s: %s", channel.id, guild_id, exc)
                failed += 1

        if not state["channels"]:
            lockdown_state.pop(guild_id, None)
            await _save_lockdowns_to_disk()
        return changed, failed


async def stop_lockdown(guild: discord.Guild) -> int:
    """Pulihkan hanya channel yang masih memakai deny lockdown; kegagalan tetap tertunda."""
    guild_id = int(guild.id)
    async with _lockdown_operation_lock:
        state = lockdown_state.get(guild_id)
        if not state:
            return 0

        restored = 0
        for record in list(state.get("channels") or []):
            channel_id = int(record.get("id") or 0)
            channel = guild.get_channel(channel_id)
            if channel is None:
                fetch_channel = getattr(guild, "fetch_channel", None)
                if callable(fetch_channel):
                    try:
                        channel = await fetch_channel(channel_id)
                    except discord.NotFound:
                        state["channels"].remove(record)
                        await _save_lockdowns_to_disk()
                        continue
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        logger.warning("Gagal mengambil channel %s untuk pemulihan lockdown: %s", channel_id, exc)
                        continue
                else:
                    continue

            # Jika izin telah diubah manual sejak lockdown, jangan timpa perubahan itu.
            current = channel.overwrites_for(guild.default_role).send_messages
            if current is not False:
                state["channels"].remove(record)
                await _save_lockdowns_to_disk()
                continue
            try:
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=record.get("send_messages"),
                    reason="Pemulihan izin sebelum lockdown",
                )
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Gagal memulihkan channel %s setelah lockdown: %s", channel_id, exc)
                continue
            state["channels"].remove(record)
            restored += 1
            await _save_lockdowns_to_disk()

        if not state["channels"]:
            lockdown_state.pop(guild_id, None)
            await _save_lockdowns_to_disk()
        return restored


# ==============================================================================
# PENYIMPANAN (AFK + THREAD)
# ==============================================================================
def load_server_tools_from_disk() -> tuple[int, int]:
    """Muat AFK, auto-thread, & catatan pemulihan lockdown dari disk."""
    load_lockdowns_from_disk()
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
        except Exception:
            logger.exception("Gagal menyimpan afk.json")


def cleanup_server_tools_runtime(limit: int = 200) -> int:
    """Memangkas guild tak aktif dari memori."""
    removed = 0
    if len(auto_thread_channels) > limit:
        for gid in list(auto_thread_channels)[: len(auto_thread_channels) - limit]:
            auto_thread_channels.pop(gid, None)
            removed += 1
    _trim_afk()
    return removed
