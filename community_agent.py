import asyncio
import json
import logging
import os
import random
import re
import time
import aiohttp
import discord

from config import (
    AGENT_CHANNEL_COOLDOWN_SEC,
    AGENT_CONFIG_FILE,
    AGENT_DEFAULT_IDLE_MINUTES,
    AGENT_HISTORY_MESSAGES,
    AGENT_MAX_IDLE_POKES,
    BOT_TIMEZONE,
    DATA_DIR,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_READER,
    GEMINI_API_BASE,
    GEMINI_API_KEY,
    GEMINI_DEFAULT_MODEL,
    GEMINI_PAID_SEARCH_ENABLED,
    GEMINI_SEARCH_FALLBACK_CHAIN,
    GEMINI_SEARCH_MODEL,
    GEMINI_TEXT_FALLBACK_CHAIN,
)
from ai_handler import (
    CHAT_TIMEOUT,
    FAST_TEXT_TIMEOUT,
    MEDIA_SEMAPHORE,
    VIDEO_LINK_TIMEOUT,
    _borrow_session,
    _build_model_chain,
    _extract_text_from_gemini_response,
    build_thinking_config,
    get_gemini_keys_rotated,
    is_gemini_key_configured,
    mark_model_unhealthy,
)
from utils import (
    build_clean_search_query,
    extract_social_media_and_stickers,
    extract_urls_from_text,
    fetch_webpage_text,
    free_live_web_search,
    get_realtime_time_context,
    has_any_url,
    has_discord_voice_note,
    has_voice_or_audio_attachment,
    has_youtube_url,
    needs_live_web_search,
    sanitize_error_message,
)

logger = logging.getLogger("gemini_bot.agent")

# Penyimpanan konfigurasi & status AI Agent Komunitas (disinkronkan ke data/agent_config.json)
guild_agent_settings: dict[int, dict] = {}
chat_agent_channels: dict[int, dict] = {}
gallery_agent_channels: dict[int, dict] = {}
youtube_agent_channels: dict[int, dict] = {}
search_agent_channels: dict[int, dict] = {}
welcome_agent_guilds: dict[int, dict] = {}
channel_histories: dict[int, list[dict]] = {}
_recent_welcomed_members: dict[tuple[int, int], float] = {}
_standalone_last_reply_at: dict[int, float] = {}
_post_runtime_state: dict[int, dict] = {}

_agent_disk_lock = asyncio.Lock()
_agent_channel_locks: dict[int, asyncio.Lock] = {}

STYLE_DESCRIPTIONS: dict[str, str] = {
    "akrab": (
        "Gunakan bahasa Indonesia santai sehari-hari yang akrab dan hangat (pakai 'aku/kamu' atau "
        "langsung sebut nama panggilannya). Sesekali boleh pakai ekspresi chat wajar seperti 'wih', "
        "'waduh', 'haha', 'wkwk', 'asik banget', tapi tetap natural dan enak dibaca."
    ),
    "gaul": (
        "Gunakan bahasa gaul tongkrongan Discord Indonesia yang santai, seru, dan ekspresif "
        "(pakai 'gue/lu' atau panggil nama membernya, ekspresi seperti 'wih gokil', 'wkwk', 'parah sih', "
        "'asli seru banget'), tetap sopan dan ramah ke semua member."
    ),
    "ramah": (
        "Gunakan bahasa Indonesia santai yang sopan, positif, hangat, dan ramah untuk semua kalangan."
    ),
}

GALLERY_REACTIONS = ("✨", "🔥", "😍", "👏", "🙌")

_GREETING_KEYWORDS = re.compile(
    r"\b(pagi|siang|sore|malem|malam|halo+|hai+|hi+|hello|hey|tes|test|"
    r"assalamu'?alaikum|permisi|sepi|gabut|bosan|bosen|ngantuk|laper|lapar|"
    r"jam\s*berapa|ada\s*orang|pada\s*kemana)\b",
    re.IGNORECASE,
)

# Abaikan perintah untuk bot lain di server (bot musik m!play, ekonomi owo/pls, Mudae $wa, dll.)
_OTHER_BOT_COMMAND_RE = re.compile(
    r"^(?:[!?$%&.;~-][a-zA-Z]|[a-zA-Z]{1,3}![a-zA-Z]|(?:owo|pls)\s+\w+)",
    re.IGNORECASE,
)

# Lacak pengirim chat terbaru per channel di RAM untuk mendeteksi saat beberapa manusia sedang asyik ngobrol
_recent_channel_speakers: dict[int, list[tuple[int, float]]] = {}

_ONLY_EMOJI_OR_SHORT_RE = re.compile(
    r"^[\s\W_0-9\U00010000-\U0010ffff<>a-zA-Z0-9:]{1,40}$"
)
_UNICODE_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]"
)


def get_agent_channel_lock(channel_id: int) -> asyncio.Lock:
    lock = _agent_channel_locks.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        _agent_channel_locks[channel_id] = lock
    return lock


def get_guild_settings(guild_id: int) -> dict:
    settings = guild_agent_settings.get(guild_id)
    if settings is None:
        settings = {
            "nickname": "",
            "style_preset": "akrab",
            "custom_prompt": "",
            "timezone": BOT_TIMEZONE,
            "quiet_hours": True,
        }
        guild_agent_settings[guild_id] = settings
    return settings


def set_youtube_channel_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    auto_in_chat: bool = False,
) -> dict | None:
    """Mengatur atau menonaktifkan fitur perangkum YouTube & link web per channel."""
    if not enabled:
        youtube_agent_channels.pop(channel_id, None)
        _standalone_last_reply_at.pop(channel_id, None)
        if channel_id not in chat_agent_channels and channel_id not in search_agent_channels:
            channel_histories.pop(channel_id, None)
        return None

    youtube_agent_channels[channel_id] = {
        "guild_id": int(guild_id),
        "enabled": True,
        "auto_in_chat": bool(auto_in_chat),
    }
    return youtube_agent_channels[channel_id]


def set_search_channel_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    auto_in_chat: bool = True,
) -> dict | None:
    """Mengatur atau menonaktifkan fitur pencarian berita & web (/cari & auto-search) per channel."""
    if not enabled:
        search_agent_channels.pop(channel_id, None)
        _standalone_last_reply_at.pop(channel_id, None)
        if channel_id not in chat_agent_channels and channel_id not in youtube_agent_channels:
            channel_histories.pop(channel_id, None)
        return None

    search_agent_channels[channel_id] = {
        "guild_id": int(guild_id),
        "enabled": True,
        "auto_in_chat": bool(auto_in_chat),
    }
    return search_agent_channels[channel_id]


def is_youtube_enabled_in_channel(
    channel_id: int | None,
    *,
    require_auto_in_chat: bool = False,
) -> bool:
    """Mengecek apakah fitur rangkum YouTube & link web aktif pada channel tertentu."""
    if not ENABLE_URL_READER or channel_id is None:
        return False
    cfg = youtube_agent_channels.get(int(channel_id))
    if not cfg or not cfg.get("enabled"):
        return False
    if require_auto_in_chat and not cfg.get("auto_in_chat", False):
        return False
    return True


def is_search_enabled_in_channel(
    channel_id: int | None,
    *,
    for_auto_chat: bool = False,
) -> bool:
    """Mengecek apakah fitur pencarian web (/cari & auto-search) aktif pada channel tertentu."""
    if not ENABLE_GOOGLE_SEARCH or channel_id is None:
        return False
    cfg = search_agent_channels.get(int(channel_id))
    if not cfg or not cfg.get("enabled"):
        return False
    if for_auto_chat and not cfg.get("auto_in_chat", True):
        return False
    return True


def get_guild_youtube_channels(guild_id: int) -> list[tuple[int, dict]]:
    return [
        (cid, cdata)
        for cid, cdata in youtube_agent_channels.items()
        if cdata.get("guild_id") == guild_id and cdata.get("enabled")
    ]


def get_guild_search_channels(guild_id: int) -> list[tuple[int, dict]]:
    return [
        (cid, cdata)
        for cid, cdata in search_agent_channels.items()
        if cdata.get("guild_id") == guild_id and cdata.get("enabled")
    ]


def resolve_agent_channel_id(channel: object) -> tuple[int | None, bool, bool]:
    """Mengembalikan `(config_channel_id, is_thread_or_post, is_forum_post)`.
    - Untuk TextChannel biasa: `(channel.id, False, False)`.
    - Untuk ruang privat `ai-...` / `draw-...`: `(None, True, False)`.
    - Untuk Postingan Forum / Media atau Thread publik: gunakan `parent_id` sebagai `config_channel_id`
      agar seluruh fitur `/agent` yang diaktifkan di Channel Forum/TextChannel otomatis berlaku di setiap postingan!
    """
    if channel is None:
        return None, False, False

    parent_id = getattr(channel, "parent_id", None)
    is_thread_like = isinstance(channel, discord.Thread) or parent_id is not None
    if is_thread_like:
        ch_name = str(getattr(channel, "name", "") or "")
        if ch_name.startswith(("ai-", "draw-")):
            return None, True, False
        if parent_id is not None:
            parent_obj = getattr(channel, "parent", None)
            is_forum = isinstance(parent_obj, discord.ForumChannel) or bool(
                getattr(channel, "is_forum_post", False)
            )
            return int(parent_id), True, is_forum

    cid = getattr(channel, "id", None)
    return (int(cid) if cid is not None else None), False, False


def _extract_forum_post_context(message: discord.Message) -> tuple[str, list[str], bool]:
    """Mengambil `(judul_postingan, daftar_tag, is_starter_post)` jika pesan berada di dalam Thread/Postingan Forum."""
    channel = getattr(message, "channel", None)
    _, is_thread_like, _ = resolve_agent_channel_id(channel)
    if not is_thread_like or channel is None:
        return "", [], False

    post_title = str(getattr(channel, "name", "") or "").strip()
    raw_tags = getattr(channel, "applied_tags", None) or []
    tag_names = [
        str(getattr(t, "name", "")).strip()
        for t in raw_tags
        if str(getattr(t, "name", "")).strip()
    ]
    msg_id = getattr(message, "id", None)
    ch_id = getattr(channel, "id", None)
    is_starter_post = bool(msg_id is not None and ch_id is not None and msg_id == ch_id)
    return post_title, tag_names, is_starter_post


def format_idle_duration(idle_seconds: int) -> str:
    """Memformat durasi pemecah sepi ke teks yang mudah dibaca (detik / menit)."""
    sec = max(0, int(idle_seconds))
    if sec == 0:
        return "Nonaktif"
    if sec < 60 or sec % 60 != 0:
        return f"{sec} detik"
    mins = sec // 60
    return f"{mins} menit"


def parse_idle_duration(raw_value: str | int | float | None) -> tuple[int, str] | None:
    """Mengubah input fleksibel pengguna (misal: '1', '30', '30 detik', '5 menit', '1 jam', '0')
    menjadi (idle_seconds, label_teks). Mengembalikan None jika format tidak dikenali.
    """
    if raw_value is None:
        sec = max(0, int(AGENT_DEFAULT_IDLE_MINUTES) * 60)
        return sec, format_idle_duration(sec)

    if isinstance(raw_value, (int, float)):
        sec = max(0, min(43200, int(round(float(raw_value) * 60))))
        if 0 < sec < 15:
            sec = 15
        return sec, format_idle_duration(sec)

    cleaned = str(raw_value).strip().lower().replace(",", ".")
    if not cleaned:
        sec = max(0, int(AGENT_DEFAULT_IDLE_MINUTES) * 60)
        return sec, format_idle_duration(sec)

    if cleaned in ("0", "off", "mati", "nonaktif", "false", "matikan", "disable"):
        return 0, "Nonaktif"

    match = re.match(
        r"^(\d+(?:\.\d+)?)\s*(d|dtk|detik|s|sec|second|seconds|m|mnt|menit|min|mins|j|jam|h|hr|hour|hours)?$",
        cleaned,
    )
    if not match:
        return None

    num = float(match.group(1))
    unit = (match.group(2) or "menit").strip()

    if num <= 0:
        return 0, "Nonaktif"

    if unit in ("d", "dtk", "detik", "s", "sec", "second", "seconds"):
        sec = int(round(num))
    elif unit in ("j", "jam", "h", "hr", "hour", "hours"):
        sec = int(round(num * 3600))
    else:
        sec = int(round(num * 60))

    # Batasi aman antara 15 detik hingga 12 jam (43200 detik)
    sec = max(15, min(43200, sec))
    return sec, format_idle_duration(sec)


def record_human_channel_activity(channel_id: int) -> None:
    """Mencatat aktivitas chat member manusia agar penghitung pemecah sepi selalu akurat."""
    ch_cfg = chat_agent_channels.get(channel_id)
    if ch_cfg and ch_cfg.get("enabled"):
        now = time.time()
        ch_cfg["last_activity_at"] = now
        ch_cfg["last_human_at"] = now
        ch_cfg["consecutive_idle_pokes"] = 0


def set_chat_channel_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    reply_mode: str = "smart",
    idle_minutes: int = AGENT_DEFAULT_IDLE_MINUTES,
    idle_seconds: int | None = None,
) -> dict | None:
    if not enabled:
        chat_agent_channels.pop(channel_id, None)
        channel_histories.pop(channel_id, None)
        _recent_channel_speakers.pop(channel_id, None)
        return None

    now = time.time()
    existing = chat_agent_channels.get(channel_id) or {}
    computed_sec = (
        max(0, int(idle_seconds))
        if idle_seconds is not None
        else max(0, int(idle_minutes) * 60)
    )
    computed_mins = computed_sec // 60 if computed_sec >= 60 else (1 if computed_sec > 0 else 0)

    # Reset last_activity_at & consecutive_idle_pokes setiap pengaturan disimpan
    # supaya timer menit_sepi langsung mulai menghitung segar dan tidak terkunci!
    chat_agent_channels[channel_id] = {
        "guild_id": guild_id,
        "enabled": True,
        "reply_mode": reply_mode if reply_mode in ("smart", "all") else "smart",
        "idle_minutes": computed_mins if idle_seconds is not None else max(0, int(idle_minutes)),
        "idle_seconds": computed_sec,
        "last_activity_at": now,
        "last_human_at": float(existing.get("last_human_at") or now),
        "last_bot_reply_at": float(existing.get("last_bot_reply_at") or 0.0),
        "consecutive_idle_pokes": 0,
    }
    return chat_agent_channels[channel_id]


def set_gallery_channel_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    auto_reaction: bool = True,
) -> dict | None:
    if not enabled:
        gallery_agent_channels.pop(channel_id, None)
        return None

    gallery_agent_channels[channel_id] = {
        "guild_id": guild_id,
        "enabled": True,
        "auto_reaction": bool(auto_reaction),
    }
    return gallery_agent_channels[channel_id]


def set_welcome_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    extra_note: str | None = None,
) -> dict | None:
    """Mengatur atau menonaktifkan fitur AI Auto-Welcomer untuk member baru di suatu server."""
    if not enabled:
        welcome_agent_guilds.pop(guild_id, None)
        return None

    existing = welcome_agent_guilds.get(guild_id) or {}
    if extra_note is None:
        note = str(existing.get("extra_note") or "").strip()
    elif extra_note.strip() == "-":
        note = ""
    else:
        note = extra_note.strip()[:250]

    welcome_agent_guilds[guild_id] = {
        "enabled": True,
        "channel_id": int(channel_id),
        "extra_note": note,
        "recent_welcomes": list(existing.get("recent_welcomes") or [])[-5:],
    }
    return welcome_agent_guilds[guild_id]


def should_process_member_welcome(guild_id: int, user_id: int, *, force: bool = False) -> bool:
    """Mencegah sambutan ganda jika event on_member_join & System Join Message aktif bersamaan."""
    now = time.time()
    # Bersihkan entri kadaluarsa (> 5 menit)
    expired = [k for k, ts in _recent_welcomed_members.items() if now - ts > 300]
    for k in expired:
        _recent_welcomed_members.pop(k, None)

    key = (int(guild_id), int(user_id))
    if not force and key in _recent_welcomed_members and (now - _recent_welcomed_members[key]) < 60:
        return False

    _recent_welcomed_members[key] = now
    return True


def load_agent_config_from_disk() -> tuple[int, int]:
    """Memuat konfigurasi AI Agent Komunitas dari data/agent_config.json."""
    if not AGENT_CONFIG_FILE.exists():
        return 0, 0

    try:
        raw = json.loads(AGENT_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", AGENT_CONFIG_FILE, exc)
        return 0, 0

    for gid_str, gdata in (raw.get("guild_settings") or {}).items():
        try:
            gid = int(gid_str)
            style = gdata.get("style_preset", "akrab")
            guild_agent_settings[gid] = {
                "nickname": str(gdata.get("nickname") or "").strip(),
                "style_preset": style if style in STYLE_DESCRIPTIONS else "akrab",
                "custom_prompt": str(gdata.get("custom_prompt") or "").strip(),
                "timezone": str(gdata.get("timezone") or BOT_TIMEZONE).strip(),
                "quiet_hours": bool(gdata.get("quiet_hours", True)),
            }
        except (ValueError, TypeError):
            continue

    now = time.time()
    for cid_str, cdata in (raw.get("chat_channels") or {}).items():
        try:
            cid = int(cid_str)
            if not cdata.get("enabled", True):
                continue
            loaded_mins = max(0, int(cdata.get("idle_minutes", AGENT_DEFAULT_IDLE_MINUTES)))
            loaded_secs = int(cdata.get("idle_seconds", loaded_mins * 60))
            chat_agent_channels[cid] = {
                "guild_id": int(cdata["guild_id"]),
                "enabled": True,
                "reply_mode": cdata.get("reply_mode") if cdata.get("reply_mode") in ("smart", "all") else "smart",
                "idle_minutes": loaded_mins,
                "idle_seconds": max(0, loaded_secs),
                "last_activity_at": float(cdata.get("last_activity_at") or now),
                "last_human_at": float(cdata.get("last_human_at") or now),
                "last_bot_reply_at": float(cdata.get("last_bot_reply_at") or 0.0),
                "consecutive_idle_pokes": int(cdata.get("consecutive_idle_pokes") or 0),
            }
        except (KeyError, ValueError, TypeError):
            continue

    for cid_str, gdata in (raw.get("gallery_channels") or {}).items():
        try:
            cid = int(cid_str)
            if not gdata.get("enabled", True):
                continue
            gallery_agent_channels[cid] = {
                "guild_id": int(gdata["guild_id"]),
                "enabled": True,
                "auto_reaction": bool(gdata.get("auto_reaction", True)),
            }
        except (KeyError, ValueError, TypeError):
            continue

    for cid_str, ydata in (raw.get("youtube_channels") or {}).items():
        try:
            cid = int(cid_str)
            if not ydata.get("enabled", True):
                continue
            youtube_agent_channels[cid] = {
                "guild_id": int(ydata["guild_id"]),
                "enabled": True,
                "auto_in_chat": bool(ydata.get("auto_in_chat", False)),
            }
        except (KeyError, ValueError, TypeError):
            continue

    for cid_str, sdata in (raw.get("search_channels") or {}).items():
        try:
            cid = int(cid_str)
            if not sdata.get("enabled", True):
                continue
            search_agent_channels[cid] = {
                "guild_id": int(sdata["guild_id"]),
                "enabled": True,
                "auto_in_chat": bool(sdata.get("auto_in_chat", True)),
            }
        except (KeyError, ValueError, TypeError):
            continue

    for gid_str, wdata in (raw.get("welcome_guilds") or {}).items():
        try:
            gid = int(gid_str)
            if not wdata.get("enabled", True):
                continue
            welcome_agent_guilds[gid] = {
                "enabled": True,
                "channel_id": int(wdata["channel_id"]),
                "extra_note": str(wdata.get("extra_note") or "").strip()[:250],
                "recent_welcomes": [str(x) for x in (wdata.get("recent_welcomes") or [])[-5:]],
            }
        except (KeyError, ValueError, TypeError):
            continue

    raw_histories = list((raw.get("channel_histories") or {}).items())[-60:]
    has_any_active_feature = bool(chat_agent_channels or youtube_agent_channels or search_agent_channels)
    for cid_str, hist in raw_histories:
        try:
            cid = int(cid_str)
            if has_any_active_feature and isinstance(hist, list):
                cleaned_hist = [
                    {"role": h["role"], "content": str(h["content"])}
                    for h in hist[-AGENT_HISTORY_MESSAGES:]
                    if h.get("role") in ("user", "model") and str(h.get("content", "")).strip()
                ]
                if cleaned_hist:
                    channel_histories[cid] = cleaned_hist
        except (ValueError, TypeError, KeyError):
            continue

    return len(chat_agent_channels), len(gallery_agent_channels)


async def save_agent_config_to_disk() -> None:
    """Menyimpan konfigurasi & status AI Agent secara atomik ke data/agent_config.json."""
    async with _agent_disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            recent_hist_items = list(channel_histories.items())[-60:]
            payload = {
                "guild_settings": {str(k): v for k, v in guild_agent_settings.items()},
                "chat_channels": {str(k): v for k, v in chat_agent_channels.items()},
                "gallery_channels": {str(k): v for k, v in gallery_agent_channels.items()},
                "youtube_channels": {str(k): v for k, v in youtube_agent_channels.items()},
                "search_channels": {str(k): v for k, v in search_agent_channels.items()},
                "welcome_guilds": {str(k): v for k, v in welcome_agent_guilds.items()},
                "channel_histories": {str(k): v[-AGENT_HISTORY_MESSAGES:] for k, v in recent_hist_items},
            }
            tmp_file = AGENT_CONFIG_FILE.with_suffix(".json.tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, AGENT_CONFIG_FILE)
        except Exception as exc:
            logger.warning("Gagal menyimpan agent_config.json: %s", exc)


def _append_channel_history(channel_id: int, role: str, text: str) -> None:
    cleaned = (text or "").strip()
    if not cleaned:
        return
    hist = channel_histories.setdefault(channel_id, [])
    if hist and hist[-1]["role"] == role and role == "user":
        hist[-1]["content"] = f"{hist[-1]['content']}\n{cleaned}"[-1500:]
    else:
        hist.append({"role": role, "content": cleaned[:1500]})
    if len(hist) > AGENT_HISTORY_MESSAGES:
        del hist[:-AGENT_HISTORY_MESSAGES]
    while hist and hist[0]["role"] != "user":
        hist.pop(0)


def _is_direct_bot_call(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
    guild_cfg: dict,
) -> tuple[bool, bool, bool]:
    """Mengembalikan (is_direct_mention_or_nick, replied_to_bot, directed_at_other_human)."""
    content = (message.content or "").strip()
    post_title, _, is_starter_post = _extract_forum_post_context(message)
    searchable_text = f"{post_title}\n{content}".strip() if (is_starter_post and post_title) else content
    agent_nick = (guild_cfg.get("nickname") or bot_user.display_name or "").strip().lower()

    mentions_list = getattr(message, "mentions", None) or []
    is_direct_mention = bot_user in mentions_list
    if not is_direct_mention and agent_nick and len(agent_nick) >= 2:
        if re.search(rf"\b{re.escape(agent_nick)}\b", searchable_text.lower()):
            is_direct_mention = True

    mentioned_other_human = any(
        getattr(u, "id", None) != bot_user.id and not getattr(u, "bot", False)
        for u in mentions_list
    )

    replied_to_bot = False
    replied_to_other_human = False
    ref = getattr(message, "reference", None)
    if ref and getattr(ref, "message_id", None):
        resolved = getattr(ref, "resolved", None)
        if resolved is not None and getattr(resolved, "author", None) is not None:
            if resolved.author.id == bot_user.id:
                replied_to_bot = True
            elif not is_direct_mention:
                replied_to_other_human = True

    directed_at_other_human = (replied_to_other_human or mentioned_other_human) and not is_direct_mention
    return is_direct_mention, replied_to_bot, directed_at_other_human


def _record_and_check_crowd_chat(channel_id: int, author_id: int, now: float) -> bool:
    """Mencatat pengirim pesan & mendeteksi apakah >= 2 member manusia berbeda sedang aktif ngobrol (60 detik terakhir)."""
    arr = _recent_channel_speakers.setdefault(channel_id, [])
    arr.append((author_id, now))
    cutoff = now - 60.0
    arr[:] = [(uid, ts) for uid, ts in arr if ts >= cutoff][-12:]
    distinct_humans = {uid for uid, _ in arr}
    return len(distinct_humans) >= 2


def _is_pure_emoji_or_sticker(message: discord.Message, content: str) -> bool:
    """True hanya jika pesan berisi Stiker atau murni ekspresi Emoji (bukan kalimat teks ke teman yang diakhiri emoji)."""
    if getattr(message, "stickers", None) and not content:
        return True
    if not content or len(content) > 60:
        return False
    has_emoji = bool(_UNICODE_EMOJI_RE.search(content) or "<:" in content or "<a:" in content)
    if not has_emoji:
        return False
    # Buang sintaks custom emoji Discord <:nama:123>, lalu pastikan tidak ada kata huruf/angka >= 2 karakter
    without_custom = re.sub(r"<a?:[a-zA-Z0-9_]{2,32}:\d{15,22}>", " ", content)
    return not bool(re.search(r"[a-zA-Z0-9]{2,}", without_custom))


def should_agent_reply_in_chat(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
) -> tuple[bool, bool]:
    """Menentukan secara cerdas & sopan apakah AI Agent perlu membalas pesan di channel publik / Forum Post.

    Returns:
        (should_reply, use_reply_reference)
    """
    cfg_cid, is_post_thread, _ = resolve_agent_channel_id(message.channel)
    if cfg_cid is None:
        return False, False

    ch_cfg = chat_agent_channels.get(cfg_cid)
    if not ch_cfg or not ch_cfg.get("enabled"):
        return False, False

    conv_id = message.channel.id
    state_bag = _post_runtime_state.setdefault(conv_id, {}) if is_post_thread else ch_cfg

    now = time.time()
    prev_activity = float(state_bag.get("last_activity_at") or 0.0)
    last_bot_at = float(state_bag.get("last_bot_reply_at") or 0.0)

    # Catat aktivitas manusia & reset counter pemecah sepi
    state_bag["last_activity_at"] = now
    ch_cfg["last_activity_at"] = now
    ch_cfg["last_human_at"] = now
    ch_cfg["consecutive_idle_pokes"] = 0

    content = (message.content or "").strip()
    post_title, _, is_starter_post = _extract_forum_post_context(message)
    guild_cfg = get_guild_settings(ch_cfg["guild_id"])
    is_direct_mention, replied_to_bot, directed_at_other_human = _is_direct_bot_call(
        message, bot_user, guild_cfg
    )
    humans_chatting_together = _record_and_check_crowd_chat(
        conv_id, message.author.id, now
    )

    # 1. Abaikan perintah untuk bot lain (contoh: m!play, $wa, owo, .help) kecuali memanggil bot ini langsung
    if content and _OTHER_BOT_COMMAND_RE.match(content) and not is_direct_mention and not replied_to_bot:
        return False, False

    # 2. Jangan pernah memotong ketika member me-reply atau me-@mention member manusia lain!
    if directed_at_other_human:
        if content:
            _append_channel_history(conv_id, "user", f"[{message.author.display_name}]: {content}")
        return False, False

    # 3. Jika member memanggil nama bot, @mention bot, atau me-reply pesan bot -> PASTI dibalas!
    if is_direct_mention or replied_to_bot:
        state_bag["last_bot_target_user_id"] = message.author.id
        state_bag["warm_followups"] = 0
        return True, True

    # 4. Jika member hanya membagikan link (YouTube, Spotify, TikTok, IG, Web) tanpa memanggil bot:
    #    - Bila auto_di_channel OFF pada channel/forum ini -> diam sopan (kecuali postingan diskusi Forum baru yg bukan murni link).
    #    - Bila auto_di_channel ON pada channel/forum ini & linknya YouTube/Web -> rangkum/komentari otomatis!
    auto_link_on = is_youtube_enabled_in_channel(cfg_cid, require_auto_in_chat=True)
    if has_youtube_url(content) or has_any_url(content):
        if auto_link_on:
            if now - last_bot_at >= AGENT_CHANNEL_COOLDOWN_SEC:
                yt_u, web_u = extract_urls_from_text(content)
                if yt_u or web_u:
                    state_bag["last_bot_target_user_id"] = message.author.id
                    state_bag["warm_followups"] = 0
                    return True, True
            return False, False
        if not is_starter_post:
            if content:
                _append_channel_history(conv_id, "user", f"[{message.author.display_name}]: {content}")
            return False, False
        # Untuk Postingan Forum baru yang HANYA berisi link mentah tanpa pertanyaan teks, tetap hormati auto_di_channel=False
        stripped_no_url = re.sub(r"https?://\S+", "", content).strip()
        if not stripped_no_url and not post_title:
            return False, False

    # 5. Jika member mengunggah file lagu/audio biasa (.mp3/.wav, bukan rekaman mikrofon Voice Note 🎤)
    #    tanpa memanggil nama bot -> jangan menyela kiriman musik member!
    if has_voice_or_audio_attachment(message) and not has_discord_voice_note(message):
        return False, False

    # 5B. POSTINGAN BARU DI CHANNEL FORUM (is_starter_post) -> Sambut / bantu jawab postingan pertamanya secara otomatis!
    if is_starter_post:
        state_bag["last_bot_target_user_id"] = message.author.id
        state_bag["warm_followups"] = 0
        return True, True

    # Cooldown singkat agar tidak membanjiri API saat chat sangat ramai
    if now - last_bot_at < AGENT_CHANNEL_COOLDOWN_SEC:
        if content:
            _append_channel_history(conv_id, "user", f"[{message.author.display_name}]: {content}")
        return False, False

    # 6. Rekaman mikrofon Voice Note (🎤) asli Discord -> balas jika bukan di tengah keramaian obrolan sesama warga
    if has_discord_voice_note(message) and not humans_chatting_together:
        state_bag["last_bot_target_user_id"] = message.author.id
        state_bag["warm_followups"] = 0
        return True, True

    if ch_cfg.get("reply_mode") == "all":
        return True, False

    # Mode 'smart' (Natural, tahu diri, & tidak mengganggu obrolan sesama member):
    # A. Channel/postingan tadinya sepi (>= 3 menit hening) lalu ada member masuk ngobrol
    if prev_activity == 0 or (now - prev_activity) >= 180:
        state_bag["last_bot_target_user_id"] = message.author.id
        state_bag["warm_followups"] = 0
        return True, True

    # Jika 2+ manusia sedang aktif saling mengobrol dalam 60 detik terakhir, tahan diri (mundur sopan)
    # sampai ada yang memanggil nama bot!
    if humans_chatting_together:
        if content:
            _append_channel_history(conv_id, "user", f"[{message.author.display_name}]: {content}")
        return False, False

    # B. Kelanjutan obrolan 1-lawan-1 yang masih hangat (maks. 90 detik & maks. 2 sahutan ke orang yang sama)
    last_target_uid = state_bag.get("last_bot_target_user_id")
    warm_count = int(state_bag.get("warm_followups") or 0)
    if (
        last_bot_at > 0
        and (now - last_bot_at) <= 90
        and last_target_uid == message.author.id
        and warm_count < 2
    ):
        state_bag["warm_followups"] = warm_count + 1
        return True, False

    # C. Member mengirim murni Stiker atau ekspresi Emoji saja (bukan kalimat teks ke orang lain)
    if _is_pure_emoji_or_sticker(message, content):
        state_bag["last_bot_target_user_id"] = message.author.id
        state_bag["warm_followups"] = 0
        return True, True

    # D. Sapaan pembuka obrolan umum / nanya jam saat channel sedang santai
    if _GREETING_KEYWORDS.search(content):
        state_bag["last_bot_target_user_id"] = message.author.id
        state_bag["warm_followups"] = 0
        return True, True

    # Simpan sebagai konteks pasif grup jika tidak dibalas langsung
    if content:
        _append_channel_history(conv_id, "user", f"[{message.author.display_name}]: {content}")
    return False, False


def should_standalone_feature_reply(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
) -> bool:
    """Menentukan apakah bot perlu merespons pada channel/forum khusus `/agent youtube` atau `/agent cari`
    (meskipun channel/forum tersebut tidak mengaktifkan `/agent chat`).
    """
    cfg_cid, _, _ = resolve_agent_channel_id(message.channel)
    if cfg_cid is None:
        return False

    yt_on = is_youtube_enabled_in_channel(cfg_cid)
    search_on = is_search_enabled_in_channel(cfg_cid, for_auto_chat=True)
    if not yt_on and not search_on:
        return False

    content = (message.content or "").strip()
    post_title, _, is_starter_post = _extract_forum_post_context(message)
    guild_id = message.guild.id if message.guild else 0
    guild_cfg = get_guild_settings(guild_id)
    is_direct_mention, replied_to_bot, directed_at_other_human = _is_direct_bot_call(
        message, bot_user, guild_cfg
    )
    is_direct_call = is_direct_mention or replied_to_bot

    # 1. Abaikan command bot lain & jangan pernah memotong obrolan antar-member
    if content and _OTHER_BOT_COMMAND_RE.match(content) and not is_direct_call:
        return False
    if directed_at_other_human:
        return False

    now = time.time()
    conv_id = message.channel.id
    last_standalone = float(_standalone_last_reply_at.get(conv_id) or 0.0)

    # 2. Cek pemicu YouTube / Link Web pada channel atau Forum Post ini
    if yt_on:
        auto_yt_channel = is_youtube_enabled_in_channel(cfg_cid, require_auto_in_chat=True)
        if is_direct_call or auto_yt_channel:
            text_for_links = f"{post_title}\n{content}".strip() if (is_starter_post and post_title) else content
            ref = getattr(message, "reference", None)
            resolved = getattr(ref, "resolved", None) if ref else None
            if is_direct_call and resolved is not None and getattr(resolved, "content", None):
                text_for_links = f"{text_for_links}\n{resolved.content}"
            if text_for_links.strip():
                yt_urls, web_urls = extract_urls_from_text(text_for_links)
                if yt_urls or web_urls:
                    if is_direct_call or (now - last_standalone >= AGENT_CHANNEL_COOLDOWN_SEC):
                        return True

    # 3. Cek pemicu Pencarian Berita/Web di obrolan saat nama bot dipanggil (atau Postingan Forum baru bertema berita jika auto_di_chat ON)
    if search_on and (is_direct_call or is_starter_post):
        raw_q = f"{post_title} {content}".strip() if (is_starter_post and post_title) else content
        if bot_user.mention in raw_q:
            raw_q = raw_q.replace(bot_user.mention, guild_cfg.get("nickname") or bot_user.display_name)
        raw_q = re.sub(r"<@!?\d+>", "", raw_q).strip()
        if needs_live_web_search(raw_q):
            return True

    return False


def _build_community_system_prompt(
    guild_cfg: dict,
    bot_display_name: str,
    time_ctx: dict,
    *,
    is_forum_post: bool = False,
) -> str:
    agent_name = guild_cfg.get("nickname") or bot_display_name or "Teman"
    style_key = guild_cfg.get("style_preset", "akrab")
    style_guide = STYLE_DESCRIPTIONS.get(style_key, STYLE_DESCRIPTIONS["akrab"])
    extra = guild_cfg.get("custom_prompt", "").strip()

    length_rule = (
        "3. Karena ini berada di dalam **Postingan Diskusi Forum**, jawablah dengan ramah, santai, jelas, dan "
        "benar-benar membantu sesuai judul & isi topik postingannya (boleh 2–5 kalimat atau poin ringkas bila "
        "member bertanya solusi/koding/rangkuman, namun tetap dengan bahasa manusia akrab, jangan kaku seperti robot).\n"
        if is_forum_post
        else (
            "3. Ketik singkat, kasual, dan mengalir seperti chat Discord beneran: cukup 1–2 kalimat pendek "
            "(jangan pakai bullet points kaku dan jangan ceramah panjang — kecuali jika member secara khusus "
            "meminta rangkuman isi video/artikel atau info berita terbaru, jelaskan intinya secara padat, santai, "
            "dan mudah dipahami).\n"
        )
    )

    prompt = (
        f"Nama panggilanmu di server Discord ini adalah '{agent_name}'. "
        "Kamu adalah teman nongkrong komunitas yang asik, santai, peka situasi, dan terasa 100% seperti "
        "manusia asli yang sedang chat di Discord.\n\n"
        "ATURAN PENTING GAYA BICARA:\n"
        f"1. {style_guide}\n"
        "2. JANGAN PERNAH menyebut dirimu AI, bot, robot, asisten virtual, atau buatan Google. Ngobrollah "
        "selayaknya teman manusia biasa.\n"
        f"{length_rule}"
        "4. Sesekali sapa lawan bicara dengan nama panggilan/display name mereka biar akrab, dan sering "
        "pancing balik dengan pertanyaan ringan supaya obrolan terus nyambung dan hidup.\n"
        "5. Jika member mengirim STIKER atau EMOJI, perhatikan ekspresi visual pada gambar stiker/emoji "
        "tersebut lalu komentari ekspresinya secara spesifik, seru, atau jenaka!\n"
        "6. Jika member mengirim VOICE NOTE (pesan suara) atau AUDIO, dengarkan baik-baik apa yang mereka "
        "ucapkan beserta intonasinya, lalu balas langsung isi pembicaraannya secara santai seolah kamu baru "
        "mendengarkan voice note temanmu (jangan kaku bilang 'aku sudah mendengarkan rekaman audio kamu').\n"
        f"7. WAKTU SEKARANG: {time_ctx['summary']}. Kamu tahu persis jam berapa sekarang ({time_ctx['clock']}) "
        "dan sesuaikan obrolanmu dengan suasana jam ini secara alami."
    )
    if extra:
        prompt += f"\n\nKonteks Tambahan Komunitas: {extra}"
    return prompt


async def _call_gemini_agent(
    system_prompt: str,
    contents: list[dict],
    *,
    temperature: float = 0.88,
    max_tokens: int = 2048,
    thinking_level: str = "minimal",
    has_media: bool = False,
    has_youtube: bool = False,
    use_google_search: bool = False,
    http_session: aiohttp.ClientSession | None = None,
) -> str | None:
    active_keys = get_gemini_keys_rotated()
    if not active_keys:
        return None

    req_timeout = (
        VIDEO_LINK_TIMEOUT
        if has_youtube
        else (CHAT_TIMEOUT if (has_media or use_google_search) else FAST_TEXT_TIMEOUT)
    )

    async with _borrow_session(http_session, req_timeout) as session:
        # Opsional Paid Tier: Native Google Search tool hanya bila GEMINI_PAID_SEARCH_ENABLED=true
        if use_google_search and GEMINI_PAID_SEARCH_ENABLED:
            search_models = _build_model_chain(GEMINI_SEARCH_MODEL, GEMINI_SEARCH_FALLBACK_CHAIN)
            for s_idx, s_model in enumerate(search_models):
                s_cfg: dict = {"temperature": 0.65, "maxOutputTokens": max(1024, max_tokens)}
                s_think = build_thinking_config(s_model, "low")
                if s_think:
                    s_cfg["thinkingConfig"] = s_think
                s_payload = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "tools": [{"google_search": {}}],
                    "generationConfig": s_cfg,
                }
                s_headers = {
                    "x-goog-api-key": active_keys[s_idx % len(active_keys)],
                    "Content-Type": "application/json",
                }
                s_url = f"{GEMINI_API_BASE}/{s_model}:generateContent"
                try:
                    async with session.post(s_url, headers=s_headers, json=s_payload, timeout=CHAT_TIMEOUT) as resp:
                        data = await resp.json(content_type=None)
                        if resp.status == 200 and isinstance(data, dict):
                            reply_text, _, _ = _extract_text_from_gemini_response(data)
                            if reply_text:
                                return reply_text.strip()
                except Exception:
                    continue

        models_to_try = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
        for idx, model_id in enumerate(models_to_try):
            gen_config: dict = {
                "temperature": temperature,
                "maxOutputTokens": max(1024, max_tokens),
            }
            thinking_cfg = build_thinking_config(model_id, thinking_level)
            if thinking_cfg:
                gen_config["thinkingConfig"] = thinking_cfg

            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": gen_config,
            }
            headers = {
                "x-goog-api-key": active_keys[idx % len(active_keys)],
                "Content-Type": "application/json",
            }
            url = f"{GEMINI_API_BASE}/{model_id}:generateContent"

            try:
                async with session.post(url, headers=headers, json=payload, timeout=req_timeout) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        reply_text, _, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            return reply_text.strip()
                        if not should_retry:
                            return None
                        continue

                    if resp.status in (400, 403):
                        # Jika gagal karena fileData YouTube privat/terkunci, buang part fileData agar teks chat tetap dibalas
                        stripped_any = False
                        for turn in contents:
                            old_parts = turn.get("parts") or []
                            new_parts = [p for p in old_parts if "fileData" not in p]
                            if len(new_parts) != len(old_parts) and new_parts:
                                turn["parts"] = new_parts
                                stripped_any = True
                        if stripped_any:
                            continue

                    if resp.status in (429, 500, 502, 503, 504, 404):
                        mark_model_unhealthy(model_id)
                        logger.warning(
                            "Agent Gemini model %s HTTP %s, pindah instan ke model cadangan...",
                            model_id,
                            resp.status,
                        )
            except asyncio.TimeoutError:
                mark_model_unhealthy(model_id)
                logger.warning("Agent Gemini model %s timeout, pindah instan ke cadangan...", model_id)
            except Exception as exc:
                logger.warning("Agent Gemini (%s) gagal: %s", model_id, sanitize_error_message(exc))
    return None


async def generate_community_chat_reply(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
    *,
    http_session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Menghasilkan balasan chat komunitas natural (mendukung teks, stiker, custom emoji, & foto)."""
    guild_id = message.guild.id if message.guild else 0
    guild_cfg = get_guild_settings(guild_id)
    time_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))

    # Bersihkan mention ID mentah (<@12345>) agar dibaca natural sebagai nama
    clean_text = (message.content or "").strip()
    if bot_user.mention in clean_text:
        clean_text = clean_text.replace(bot_user.mention, guild_cfg.get("nickname") or bot_user.display_name)
    clean_text = re.sub(r"<@!?\d+>", "", clean_text).strip()

    media_parts, media_descs, _ = await extract_social_media_and_stickers(
        message,
        http_session,
        include_video=False,
        include_audio=True,
        include_text_files=True,
    )

    is_direct_mention, replied_to_bot, _ = _is_direct_bot_call(message, bot_user, guild_cfg)
    is_direct_call = is_direct_mention or replied_to_bot

    cfg_cid, is_post_thread, _ = resolve_agent_channel_id(message.channel)
    effective_cfg_cid = cfg_cid if cfg_cid is not None else message.channel.id
    post_title, post_tags, is_starter_post = _extract_forum_post_context(message)

    forum_ctx_note = ""
    if is_post_thread and post_title:
        tag_str = f" | Tag: {', '.join(post_tags)}" if post_tags else ""
        starter_label = "Postingan Forum Baru" if is_starter_post else "Diskusi di Postingan Forum"
        forum_ctx_note = f'[{starter_label} — Judul: "{post_title}"{tag_str}]'

    yt_urls: list[str] = []
    web_snippets: list[str] = []
    # Baca link YouTube/Web hanya jika fitur YouTube AKTIF pada channel/forum ini DAN
    # (member memanggil nama/mention/reply bot secara langsung ATAU mode auto_di_channel dinyalakan di channel/forum ini)
    allow_public_link_reader = is_youtube_enabled_in_channel(effective_cfg_cid) and (
        is_direct_call or is_youtube_enabled_in_channel(effective_cfg_cid, require_auto_in_chat=True)
    )
    if allow_public_link_reader:
        text_for_links = f"{post_title}\n{clean_text}".strip() if (is_starter_post and post_title) else clean_text
        # Dukung juga bila member me-reply pesan orang lain yang berisi link YouTube sambil memanggil nama bot!
        ref = getattr(message, "reference", None)
        resolved = getattr(ref, "resolved", None) if ref else None
        if is_direct_call and resolved is not None and getattr(resolved, "content", None):
            text_for_links = f"{text_for_links}\n{resolved.content}"

        if text_for_links.strip():
            yt_urls, web_urls = extract_urls_from_text(text_for_links)
            for yt_u in yt_urls[:1]:
                media_parts.append({"fileData": {"fileUri": yt_u}})
                media_descs.append(
                    f"[Video YouTube terlampir ({yt_u}) — tonton/pahami isi videonya untuk menjawab permintaan {message.author.display_name}!]"
                )
            for web_u in web_urls[:1]:
                w_title, w_body = await fetch_webpage_text(web_u, http_session=http_session)
                if w_body:
                    label = f"{w_title} ({web_u})" if w_title else web_u
                    web_snippets.append(f"[Isi ringkas link {label}: {w_body[:2500]}]")

    search_text_candidate = f"{post_title} {clean_text}".strip() if (is_starter_post and post_title) else clean_text
    use_search = (
        is_search_enabled_in_channel(effective_cfg_cid, for_auto_chat=True)
        and not media_parts
        and not web_snippets
        and needs_live_web_search(search_text_candidate)
    )
    if use_search and not GEMINI_PAID_SEARCH_ENABLED:
        nick_for_clean = guild_cfg.get("nickname") or bot_user.display_name
        search_q = build_clean_search_query(search_text_candidate, nick_for_clean)
        free_ctx, _ = await free_live_web_search(search_q, max_results=4, http_session=http_session)
        if free_ctx:
            web_snippets.append(f"[Info Berita/Web Terkini Hari Ini:\n{free_ctx[:2200]}]")

    author_name = message.author.display_name
    desc_items = [x for x in (forum_ctx_note, *media_descs, *web_snippets) if x]
    desc_prefix = " ".join(desc_items)
    if clean_text and desc_prefix:
        user_turn_text = f"[{author_name}]: {clean_text}\n{desc_prefix}"
    elif clean_text:
        user_turn_text = f"[{author_name}]: {clean_text}"
    elif desc_prefix:
        user_turn_text = f"[{author_name}]: {desc_prefix}"
    else:
        return None

    # Bangun contents dari riwayat singkat channel publik / per-Postingan Forum
    conv_id = message.channel.id
    contents: list[dict] = []
    for item in channel_histories.get(conv_id, []):
        role = "user" if item["role"] == "user" else "model"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].append({"text": item["content"]})
        else:
            contents.append({"role": role, "parts": [{"text": item["content"]}]})

    current_parts: list[dict] = [*media_parts, {"text": user_turn_text}]
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"].extend(current_parts)
    else:
        contents.append({"role": "user", "parts": current_parts})

    bot_display = (
        message.guild.me.display_name
        if (message.guild and message.guild.me)
        else bot_user.display_name
    )
    system_prompt = _build_community_system_prompt(
        guild_cfg,
        bot_display,
        time_ctx,
        is_forum_post=is_post_thread,
    )

    reply = await _call_gemini_agent(
        system_prompt,
        contents,
        temperature=0.88,
        max_tokens=2048,
        thinking_level="low" if (media_parts or use_search or is_post_thread) else "minimal",
        has_media=bool(media_parts),
        has_youtube=bool(yt_urls),
        use_google_search=(use_search and GEMINI_PAID_SEARCH_ENABLED),
        http_session=http_session,
    )

    if reply:
        # Bersihkan awalan seperti "[NamaBot]:" jika model tidak sengaja menuliskannya
        reply = re.sub(r"^\[[^\]]+\]\s*:\s*", "", reply).strip()
        _append_channel_history(conv_id, "user", user_turn_text)
        _append_channel_history(conv_id, "model", reply)
        now = time.time()
        _standalone_last_reply_at[conv_id] = now
        if is_post_thread:
            p_state = _post_runtime_state.setdefault(conv_id, {})
            p_state["last_bot_reply_at"] = now
            p_state["last_activity_at"] = now
        ch_cfg = chat_agent_channels.get(effective_cfg_cid)
        if ch_cfg:
            if not is_post_thread:
                ch_cfg["last_bot_reply_at"] = now
            ch_cfg["last_activity_at"] = now
        await save_agent_config_to_disk()

    return reply


_ICEBREAKER_ANGLES: tuple[str, ...] = (
    "Sapa warga santai sesuai jam & hari sekarang sambil nanya lagi pada sibuk ngapain.",
    "Lempar satu pertanyaan pilihan ringan ala tongkrongan (misal soal makanan/minuman favorit di jam segini, kebiasaan unik, atau hal relate sehari-hari) tanpa terdengar kaku.",
    "Tanyain santai warga lagi pada dengerin lagu apa, nonton apa, atau main game apa belakangan ini.",
    "Nyeletuk santai soal suasana hari/jam sekarang (misal vibe hari kerja vs weekend, jam rawan lapar/ngantuk, atau jam enak buat rebahan) lalu pancing obrolan.",
    "Ajak warga ngobrol ringan soal hobi atau topik seru yang nyambung sama tema server.",
    "Sapa tongkrongan dengan gaya akrab dan jenaka seolah baru buka HP dan mampir ke channel.",
    "Lempar celetukan random yang lucu/relate soal kehidupan sehari-hari biar warga tertarik nyaut.",
    "Nyeletuk ringan memecah keheningan channel dengan gaya santai khas anak Discord.",
)


async def generate_idle_icebreaker(
    channel_id: int,
    guild_id: int,
    bot_display_name: str,
    *,
    idle_minutes_elapsed: int = 30,
    manual_trigger: bool = False,
    http_session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Membuat sapaan/celetukan santai otomatis yang selalu bervariasi saat channel sedang sepi."""
    guild_cfg = get_guild_settings(guild_id)
    time_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))
    system_prompt = _build_community_system_prompt(guild_cfg, bot_display_name, time_ctx)

    # Ambil 5 celetukan terakhir milik bot sendiri agar kalimat & topiknya tidak pernah diulang
    past_hist = channel_histories.get(channel_id, [])
    recent_bot_msgs = [h["content"] for h in past_hist if h.get("role") == "model"][-5:]
    avoid_block = ""
    if recent_bot_msgs:
        joined_prev = " | ".join(f'"{m[:120]}"' for m in recent_bot_msgs)
        avoid_block = (
            f"\nPENTING ANTI-MONOTON: Sebelumnya kamu sudah pernah mengirim kalimat ini: [{joined_prev}]. "
            "JANGAN gunakan awalan kata, struktur kalimat, atau topik yang sama/mirip dengan kalimat sebelumnya tersebut! "
            "Jangan terus-menerus mengawali kalimat dengan kata 'Sepi banget' atau 'Aduh sepi'."
        )

    chosen_angle = random.choice(_ICEBREAKER_ANGLES)
    icebreaker_instruction = (
        f"(Instruksi situasi: Channel chat ini belum ada obrolan baru sekitar {max(1, idle_minutes_elapsed)} menit. "
        f"Sekarang hari {time_ctx['day_name']} pukul {time_ctx['clock']} ({time_ctx['vibe']}).\n"
        f"Ide sudut obrolan kali ini: {chosen_angle}\n"
        "Buat 1 kalimat pendek yang spontan, segar, bervariasi, dan sangat manusiawi untuk memulai obrolan "
        f"dengan warga server!){avoid_block}"
    )

    contents = [{"role": "user", "parts": [{"text": icebreaker_instruction}]}]
    reply = await _call_gemini_agent(
        system_prompt,
        contents,
        temperature=0.95,
        max_tokens=2048,
        thinking_level="minimal",
        has_media=False,
        http_session=http_session,
    )

    if reply:
        reply = re.sub(r"^\[[^\]]+\]\s*:\s*", "", reply).strip().strip('"')
        _append_channel_history(channel_id, "user", "[Situasi: Channel sedang sepi]")
        _append_channel_history(channel_id, "model", reply)
        ch_cfg = chat_agent_channels.get(channel_id)
        if ch_cfg:
            now = time.time()
            ch_cfg["last_activity_at"] = now
            ch_cfg["last_bot_reply_at"] = now
            if manual_trigger:
                # Sapaan manual via /agent sapa tidak boleh mengunci penghitung otomatis menit_sepi
                ch_cfg["consecutive_idle_pokes"] = 0
            else:
                ch_cfg["consecutive_idle_pokes"] = int(ch_cfg.get("consecutive_idle_pokes") or 0) + 1
        await save_agent_config_to_disk()

    return reply


async def generate_gallery_comment(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
    *,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Men-scan gambar atau video di channel/forum Galeri dan memberikan komentar otomatis yang relevan.

    Returns:
        (comment_text, reaction_emoji)
    """
    cfg_cid, is_post_thread, _ = resolve_agent_channel_id(message.channel)
    if cfg_cid is None:
        return None, None

    gal_cfg = gallery_agent_channels.get(cfg_cid)
    if not gal_cfg or not gal_cfg.get("enabled"):
        return None, None

    async with MEDIA_SEMAPHORE:
        media_parts, media_descs, _ = await extract_social_media_and_stickers(
            message,
            http_session,
            include_video=True,
            include_audio=False,
        )
    # Hanya komentari kiriman yang benar-benar memiliki lampiran foto/gambar atau video di galeri
    has_gallery_attachment = any(
        d.startswith("[Mengirim foto/gambar:") or d.startswith("[Mengirim video:")
        for d in media_descs
    )
    if not media_parts or not has_gallery_attachment:
        return None, None

    guild_id = message.guild.id if message.guild else gal_cfg["guild_id"]
    guild_cfg = get_guild_settings(guild_id)
    time_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))
    style_key = guild_cfg.get("style_preset", "akrab")
    style_guide = STYLE_DESCRIPTIONS.get(style_key, STYLE_DESCRIPTIONS["akrab"])

    author_name = message.author.display_name
    caption = (message.content or "").strip()
    post_title, post_tags, _ = _extract_forum_post_context(message)

    gallery_system_prompt = (
        "Kamu adalah teman komunitas Discord yang seru, jeli, dan apresiatif di channel Galeri/Showcase.\n"
        f"{style_guide}\n"
        "TUGASMU:\n"
        "1. Perhatikan baik-baik isi foto, karya gambar, screenshot, kostum/karakter, atau video yang dikirim member.\n"
        "2. Berikan komentar 1–2 kalimat pendek yang SPESIFIK menyebutkan detail menarik, lucu, estetik, atau keren "
        "yang benar-benar terlihat di gambar/video tersebut (jangan memberi pujian generik seperti 'Gambar yang bagus!').\n"
        "3. Jangan pernah menyebut dirimu AI atau bot. Tulis santai seperti teman komunitas yang antusias melihat postingan itu."
    )

    user_prompt = f"Member '{author_name}' baru saja membagikan media di galeri ({' '.join(media_descs)})."
    if is_post_thread and post_title:
        tag_info = f" (Tag: {', '.join(post_tags)})" if post_tags else ""
        user_prompt += f"\nJudul Postingan Forum: \"{post_title}\"{tag_info}"
    if caption:
        user_prompt += f"\nCaption dari {author_name}: \"{caption}\""
    user_prompt += f"\n(Waktu saat ini: {time_ctx['clock']}). Berikan komentarmu!"

    contents = [{"role": "user", "parts": [*media_parts, {"text": user_prompt}]}]
    reply = await _call_gemini_agent(
        gallery_system_prompt,
        contents,
        temperature=0.85,
        max_tokens=2048,
        thinking_level="low",
        has_media=True,
        http_session=http_session,
    )

    reaction = random.choice(GALLERY_REACTIONS) if gal_cfg.get("auto_reaction", True) else None
    return (reply.strip() if reply else None), reaction


async def run_idle_chat_check(bot: discord.Client, http_session: aiohttp.ClientSession | None = None) -> int:
    """Memeriksa seluruh channel Auto-Chat aktif dan mengirim sapaan pemecah sepi jika waktunya tiba.
    Mengembalikan jumlah channel yang berhasil disapa.
    """
    if not is_gemini_key_configured():
        return 0

    now = time.time()
    poked_count = 0

    for channel_id, ch_cfg in list(chat_agent_channels.items()):
        if not ch_cfg.get("enabled"):
            continue

        idle_secs = int(
            ch_cfg.get("idle_seconds")
            if ch_cfg.get("idle_seconds") is not None
            else int(ch_cfg.get("idle_minutes") or 0) * 60
        )
        if idle_secs <= 0:
            continue

        # Anti-spam: jangan terus-terusan monolog sendirian jika belum ada satupun manusia membalas
        if int(ch_cfg.get("consecutive_idle_pokes") or 0) >= AGENT_MAX_IDLE_POKES:
            continue

        last_act = float(ch_cfg.get("last_activity_at") or 0.0)
        elapsed_sec = now - last_act
        if elapsed_sec < idle_secs:
            continue

        guild_id = ch_cfg["guild_id"]
        guild_cfg = get_guild_settings(guild_id)
        time_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))

        # Jam tenang malam (23:00 - 05:59 waktu lokal): tahan celetukan otomatis saat warga tidur
        if guild_cfg.get("quiet_hours", True) and (time_ctx["hour"] >= 23 or time_ctx["hour"] < 6):
            continue

        channel = bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            continue

        lock = get_agent_channel_lock(channel_id)
        if lock.locked():
            continue

        async with lock:
            # Cek ulang setelah mendapat lock
            if (time.time() - float(ch_cfg.get("last_activity_at") or 0.0)) < idle_secs:
                continue

            bot_name = (
                channel.guild.me.display_name
                if channel.guild.me
                else (bot.user.display_name if bot.user else "Teman")
            )
            elapsed_mins = max(1, int(elapsed_sec // 60))
            try:
                async with channel.typing():
                    icebreaker = await generate_idle_icebreaker(
                        channel_id,
                        guild_id,
                        bot_name,
                        idle_minutes_elapsed=elapsed_mins,
                        manual_trigger=False,
                        http_session=http_session,
                    )
                    if icebreaker:
                        await channel.send(icebreaker)
                        poked_count += 1
                        logger.info("Pemecah sepi terkirim di #%s (%s)", channel.name, channel_id)
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Gagal mengirim pemecah sepi di %s: %s", channel_id, exc)

    return poked_count


_WELCOME_ANGLES: tuple[str, ...] = (
    "Sambut dengan antusias layaknya warga lama yang senang kedatangan teman tongkrongan baru.",
    "Sambut hangat sesuai suasana jam sekarang lalu ajak kenalan santai atau tanya lagi sibuk/main apa.",
    "Sambut akrab dan seru sesuai tema komunitas server, bikin dia langsung merasa betah dan tidak canggung.",
    "Beri sambutan ceria yang santai ala Discord Indonesia lalu pancing satu pertanyaan ringan biar dia mau nyaut.",
    "Sambut ramah seolah membukakan pintu tongkrongan sambil menyapa namanya dengan akrab.",
)


async def generate_welcome_greeting(
    guild_id: int,
    member_display_name: str,
    member_mention: str,
    bot_display_name: str,
    *,
    guild_name: str = "",
    member_count: int | None = None,
    http_session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Membuat sambutan otomatis yang unik & natural ala manusia untuk member yang baru bergabung."""
    w_cfg = welcome_agent_guilds.get(guild_id)
    if not w_cfg or not w_cfg.get("enabled"):
        return None

    guild_cfg = get_guild_settings(guild_id)
    time_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))
    system_prompt = _build_community_system_prompt(guild_cfg, bot_display_name, time_ctx)

    recent_welcomes = list(w_cfg.get("recent_welcomes") or [])[-5:]
    avoid_block = ""
    if recent_welcomes:
        joined_prev = " | ".join(f'"{m[:110]}"' for m in recent_welcomes)
        avoid_block = (
            f"\nPENTING ANTI-MONOTON: Sambutan sebelumnya yang sudah pernah kamu kirim: [{joined_prev}]. "
            "Buat variasi kalimat & pembuka yang berbeda supaya setiap member baru mendapat sambutan segar!"
        )

    extra_note = str(w_cfg.get("extra_note") or "").strip()
    note_instruction = (
        f"\nSelipkan juga info penting ini secara santai (jangan kaku seperti pengumuman): \"{extra_note}\""
        if extra_note
        else ""
    )
    count_info = f" (member ke-{member_count})" if member_count else ""
    server_label = f" di server '{guild_name}'" if guild_name else ""
    angle = random.choice(_WELCOME_ANGLES)

    welcome_prompt = (
        f"(Instruksi situasi: Member baru bernama '{member_display_name}'{count_info} baru saja bergabung{server_label} "
        f"pada hari {time_ctx['day_name']} pukul {time_ctx['clock']} ({time_ctx['vibe']}).\n"
        f"Gaya sambutan kali ini: {angle}\n"
        f"Gunakan tag persis {member_mention} satu kali di dalam kalimatmu agar member tersebut ter-mention, "
        "tulis 1–2 kalimat pendek saja yang hangat, gaul/akrab, dan mengundang dia ikut ngobrol!)"
        f"{note_instruction}{avoid_block}"
    )

    reply = await _call_gemini_agent(
        system_prompt,
        [{"role": "user", "parts": [{"text": welcome_prompt}]}],
        temperature=0.92,
        max_tokens=1536,
        thinking_level="minimal",
        has_media=False,
        http_session=http_session,
    )

    if reply:
        reply = re.sub(r"^\[[^\]]+\]\s*:\s*", "", reply).strip().strip('"')
        if member_mention and member_mention not in reply:
            reply = f"{member_mention} {reply}"
        recent_welcomes.append(reply)
        w_cfg["recent_welcomes"] = recent_welcomes[-5:]
        channel_id = int(w_cfg["channel_id"])
        if channel_id in chat_agent_channels:
            _append_channel_history(channel_id, "model", reply)
        await save_agent_config_to_disk()

    return reply

