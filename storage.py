import asyncio
import json
import logging
import os
import time
import discord
from config import (
    AI_MODELS,
    DATA_DIR,
    DEFAULT_IMAGE_SETTINGS,
    MAX_HISTORY_MESSAGES,
    RATIO_OPTIONS,
    SESSION_EXPIRE_DAYS,
    SESSIONS_FILE,
    STYLE_OPTIONS,
    resolve_model_key,
)

logger = logging.getLogger("gemini_bot.storage")

# Memori sesi aktif di RAM (disinkronkan ke data/sessions.json agar tahan restart)
thread_chats: dict[int, dict] = {}
image_thread_settings: dict[int, dict] = {}

# Lock per-thread agar pesan beruntun tidak saling menimpa memori percakapan
_thread_locks: dict[int, asyncio.Lock] = {}
_closing_threads: set[int] = set()
_disk_lock = asyncio.Lock()

# Penanda pesan sistem/UI bot agar tidak ikut masuk ke memori AI atau rekap obrolan
UI_MESSAGE_PREFIXES = (
    "👋 **Selamat Datang",
    "🎨 **Selamat Datang",
    "🔴 *Klik tombol",
    "🧹 **Menyiapkan rekap",
    "🎨 **Memproses gambar",
    "🔄 **Memori percakapan",
    "✅ **Mode AI diubah",
)


def is_bot_ui_message(content: str) -> bool:
    stripped = (content or "").strip()
    return any(stripped.startswith(prefix) for prefix in UI_MESSAGE_PREFIXES)


def get_thread_lock(thread_id: int) -> asyncio.Lock:
    lock = _thread_locks.get(thread_id)
    if lock is None:
        lock = asyncio.Lock()
        _thread_locks[thread_id] = lock
    return lock


def mark_thread_closing(thread_id: int) -> bool:
    """Menandai thread sedang dalam proses penutupan (mencegah double-click crash).
    Mengembalikan True jika berhasil ditandai, False jika memang sedang ditutup.
    """
    if thread_id in _closing_threads:
        return False
    _closing_threads.add(thread_id)
    return True


def unmark_thread_closing(thread_id: int) -> None:
    _closing_threads.discard(thread_id)


def trim_history(history: list[dict], max_messages: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """Memangkas riwayat obrolan agar hemat RAM & kuota token, sambil menjaga urutan user -> model."""
    cleaned = [
        {"role": item["role"], "content": str(item["content"])}
        for item in history
        if item.get("role") in ("user", "model") and str(item.get("content", "")).strip()
    ]
    if len(cleaned) > max_messages:
        cleaned = cleaned[-max_messages:]
    # Pastikan percakapan selalu diawali giliran 'user' untuk validitas Gemini API
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    return cleaned


def init_thread_session(
    thread_id: int,
    model_key: str = "gemini_flash",
    owner_id: int | None = None,
) -> dict:
    """Menginisialisasi sesi chat teks baru untuk sebuah thread."""
    resolved_key = resolve_model_key(model_key)
    existing = thread_chats.get(thread_id)
    effective_owner = owner_id if owner_id is not None else (existing or {}).get("owner_id")

    thread_chats[thread_id] = {
        "model_key": resolved_key,
        "owner_id": effective_owner,
        "history": [],
        "updated_at": time.time(),
    }
    return thread_chats[thread_id]


def switch_thread_model(thread_id: int, new_model_key: str, owner_id: int | None = None) -> dict:
    """Mengganti mode/persona Gemini tanpa menghapus riwayat percakapan di thread tersebut."""
    resolved_key = resolve_model_key(new_model_key)
    session = thread_chats.get(thread_id)
    if session is None:
        return init_thread_session(thread_id, resolved_key, owner_id=owner_id)

    session["model_key"] = resolved_key
    if owner_id is not None and not session.get("owner_id"):
        session["owner_id"] = owner_id
    session["updated_at"] = time.time()
    return session


def reset_thread_history(thread_id: int) -> bool:
    """Menghapus riwayat percakapan di thread chat teks sambil mempertahankan model pilihannya."""
    session = thread_chats.get(thread_id)
    if session is None:
        return False
    session["history"] = []
    session["updated_at"] = time.time()
    return True


def append_conversation_turn(thread_id: int, user_text: str, model_reply: str) -> None:
    """Menyimpan pasangan pesan user & balasan model secara atomik setelah request sukses."""
    session = thread_chats.get(thread_id)
    if session is None:
        session = init_thread_session(thread_id, "gemini_flash")

    session["history"].append({"role": "user", "content": user_text})
    session["history"].append({"role": "model", "content": model_reply})
    session["history"] = trim_history(session["history"])
    session["updated_at"] = time.time()


def init_image_session(thread_id: int, owner_id: int | None = None) -> dict:
    """Menginisialisasi pengaturan gambar default untuk thread 'draw-'."""
    existing = image_thread_settings.get(thread_id)
    effective_owner = owner_id if owner_id is not None else (existing or {}).get("owner_id")
    image_thread_settings[thread_id] = {
        "style": DEFAULT_IMAGE_SETTINGS["style"],
        "ratio": DEFAULT_IMAGE_SETTINGS["ratio"],
        "owner_id": effective_owner,
        "updated_at": time.time(),
    }
    return image_thread_settings[thread_id]


def get_image_settings(thread_id: int) -> dict:
    settings = image_thread_settings.get(thread_id)
    if settings is None:
        settings = init_image_session(thread_id)
    if settings.get("style") not in STYLE_OPTIONS:
        settings["style"] = DEFAULT_IMAGE_SETTINGS["style"]
    if settings.get("ratio") not in RATIO_OPTIONS:
        settings["ratio"] = DEFAULT_IMAGE_SETTINGS["ratio"]
    return settings


def remove_thread_data(thread_id: int) -> bool:
    """Menghapus seluruh data memori untuk thread yang sudah ditutup/dihapus."""
    removed = False
    if thread_id in thread_chats:
        del thread_chats[thread_id]
        removed = True
    if thread_id in image_thread_settings:
        del image_thread_settings[thread_id]
        removed = True
    _thread_locks.pop(thread_id, None)
    _closing_threads.discard(thread_id)
    return removed


def cleanup_expired_sessions(max_age_days: int = SESSION_EXPIRE_DAYS) -> int:
    """Membersihkan otomatis data sesi privat yang sudah menganggur lebih dari N hari
    agar file sessions.json dan RAM tetap ramping tanpa perlu perawatan manual.
    """
    if max_age_days <= 0:
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    expired_ids: set[int] = set()

    for tid, data in list(thread_chats.items()):
        if float(data.get("updated_at") or 0) < cutoff:
            expired_ids.add(tid)

    for tid, data in list(image_thread_settings.items()):
        if float(data.get("updated_at") or 0) < cutoff:
            expired_ids.add(tid)

    for tid in expired_ids:
        remove_thread_data(tid)

    if expired_ids:
        logger.info("Auto-cleanup: %d sesi lama (>%d hari menganggur) dibersihkan.", len(expired_ids), max_age_days)
    return len(expired_ids)


def load_sessions_from_disk() -> tuple[int, int]:
    """Memuat sesi tersimpan dari data/sessions.json saat bot dinyalakan."""
    if not SESSIONS_FILE.exists():
        return 0, 0

    try:
        raw = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal membaca file sesi %s: %s", SESSIONS_FILE, exc)
        return 0, 0

    loaded_chats = 0
    for tid_str, data in (raw.get("thread_chats") or {}).items():
        try:
            tid = int(tid_str)
            model_key = resolve_model_key(data.get("model_key"))
            history = trim_history(data.get("history") or [])
            thread_chats[tid] = {
                "model_key": model_key,
                "owner_id": data.get("owner_id"),
                "history": history,
                "updated_at": float(data.get("updated_at") or time.time()),
            }
            loaded_chats += 1
        except (ValueError, TypeError):
            continue

    loaded_images = 0
    for tid_str, data in (raw.get("image_thread_settings") or {}).items():
        try:
            tid = int(tid_str)
            style = data.get("style")
            ratio = data.get("ratio")
            image_thread_settings[tid] = {
                "style": style if style in STYLE_OPTIONS else DEFAULT_IMAGE_SETTINGS["style"],
                "ratio": ratio if ratio in RATIO_OPTIONS else DEFAULT_IMAGE_SETTINGS["ratio"],
                "owner_id": data.get("owner_id"),
                "updated_at": float(data.get("updated_at") or time.time()),
            }
            loaded_images += 1
        except (ValueError, TypeError):
            continue

    cleanup_expired_sessions()
    return len(thread_chats), len(image_thread_settings)


async def save_sessions_to_disk() -> None:
    """Menyimpan sesi secara atomik ke disk agar aman dari korupsi saat restart mendadak."""
    async with _disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "thread_chats": {str(k): v for k, v in thread_chats.items()},
                "image_thread_settings": {str(k): v for k, v in image_thread_settings.items()},
            }
            tmp_file = SESSIONS_FILE.with_suffix(".json.tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, SESSIONS_FILE)
        except Exception as exc:
            logger.warning("Gagal menyimpan sesi ke disk: %s", exc)


async def recover_session_from_thread(
    thread: discord.Thread,
    bot_user_id: int,
    exclude_message_id: int | None = None,
) -> dict:
    """Memulihkan sesi & konteks percakapan langsung dari riwayat Discord Thread
    apabila file lokal terhapus (misal setelah rebuild container baru di Wispbyte).
    """
    detected_key = "gemini_flash"
    owner_id: int | None = None
    reconstructed: list[dict] = []

    try:
        messages = [
            msg
            async for msg in thread.history(limit=25, oldest_first=True)
            if msg.id != exclude_message_id
        ]

        # 1. Deteksi model & pemilik sesi dari pesan sambutan pertama bot
        for msg in messages[:3]:
            if msg.author.id == bot_user_id:
                text_pool = msg.content or ""
                for emb in msg.embeds:
                    text_pool += f"\n{emb.title or ''}\n{emb.description or ''}"
                for key, info in AI_MODELS.items():
                    if info["name"] in text_pool or info["short_label"] in text_pool:
                        detected_key = key
                        break
                if msg.mentions:
                    owner_id = msg.mentions[0].id
                break

        # 2. Susun ulang percakapan terakhir (mengabaikan pesan UI/status bot)
        for msg in messages:
            content = (msg.content or "").strip()
            if not content or is_bot_ui_message(content):
                continue
            if msg.author.id == bot_user_id and msg.embeds and not content:
                continue

            role = "model" if msg.author.id == bot_user_id else "user"
            if reconstructed and reconstructed[-1]["role"] == role:
                reconstructed[-1]["content"] += f"\n{content}"
            else:
                reconstructed.append({"role": role, "content": content})

        # Jika pesan paling akhir adalah 'user' yang belum terjawab, buang agar tidak dobel
        if reconstructed and reconstructed[-1]["role"] == "user":
            reconstructed.pop()

    except Exception as exc:
        logger.debug("Pemulihan riwayat dari Discord dilewati untuk thread %s: %s", thread.id, exc)

    session = init_thread_session(thread.id, detected_key, owner_id=owner_id)
    session["history"] = trim_history(reconstructed)
    await save_sessions_to_disk()
    return session
