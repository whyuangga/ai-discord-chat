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
    GEMINI_API_BASE,
    GEMINI_API_KEY,
    GEMINI_DEFAULT_MODEL,
    GEMINI_TEXT_FALLBACK_CHAIN,
)
from ai_handler import (
    CHAT_TIMEOUT,
    FAST_TEXT_TIMEOUT,
    MEDIA_SEMAPHORE,
    _borrow_session,
    _build_model_chain,
    _extract_text_from_gemini_response,
    build_thinking_config,
    get_gemini_keys_rotated,
    is_gemini_key_configured,
    mark_model_unhealthy,
)
from utils import (
    extract_social_media_and_stickers,
    get_realtime_time_context,
    sanitize_error_message,
)

logger = logging.getLogger("gemini_bot.agent")

# Penyimpanan konfigurasi & status AI Agent Komunitas (disinkronkan ke data/agent_config.json)
guild_agent_settings: dict[int, dict] = {}
chat_agent_channels: dict[int, dict] = {}
gallery_agent_channels: dict[int, dict] = {}
channel_histories: dict[int, list[dict]] = {}

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
    r"\b(pagi|siang|sore|malem|malam|halo+|hai+|hi+|hello|hey|p|tes|test|"
    r"assalamu'?alaikum|permisi|sepi|gabut|bosan|bosen|ngantuk|laper|lapar|"
    r"jam\s*berapa|ada\s*orang|pada\s*kemana)\b",
    re.IGNORECASE,
)

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


def set_chat_channel_config(
    guild_id: int,
    channel_id: int,
    *,
    enabled: bool,
    reply_mode: str = "smart",
    idle_minutes: int = AGENT_DEFAULT_IDLE_MINUTES,
) -> dict | None:
    if not enabled:
        chat_agent_channels.pop(channel_id, None)
        channel_histories.pop(channel_id, None)
        return None

    now = time.time()
    existing = chat_agent_channels.get(channel_id) or {}
    chat_agent_channels[channel_id] = {
        "guild_id": guild_id,
        "enabled": True,
        "reply_mode": reply_mode if reply_mode in ("smart", "all") else "smart",
        "idle_minutes": max(0, int(idle_minutes)),
        "last_activity_at": float(existing.get("last_activity_at") or now),
        "last_human_at": float(existing.get("last_human_at") or now),
        "last_bot_reply_at": float(existing.get("last_bot_reply_at") or 0.0),
        "consecutive_idle_pokes": int(existing.get("consecutive_idle_pokes") or 0),
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
            chat_agent_channels[cid] = {
                "guild_id": int(cdata["guild_id"]),
                "enabled": True,
                "reply_mode": cdata.get("reply_mode") if cdata.get("reply_mode") in ("smart", "all") else "smart",
                "idle_minutes": max(0, int(cdata.get("idle_minutes", AGENT_DEFAULT_IDLE_MINUTES))),
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

    for cid_str, hist in (raw.get("channel_histories") or {}).items():
        try:
            cid = int(cid_str)
            if cid in chat_agent_channels and isinstance(hist, list):
                channel_histories[cid] = [
                    {"role": h["role"], "content": str(h["content"])}
                    for h in hist[-AGENT_HISTORY_MESSAGES:]
                    if h.get("role") in ("user", "model") and str(h.get("content", "")).strip()
                ]
        except (ValueError, TypeError, KeyError):
            continue

    return len(chat_agent_channels), len(gallery_agent_channels)


async def save_agent_config_to_disk() -> None:
    """Menyimpan konfigurasi & status AI Agent secara atomik ke data/agent_config.json."""
    async with _agent_disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guild_settings": {str(k): v for k, v in guild_agent_settings.items()},
                "chat_channels": {str(k): v for k, v in chat_agent_channels.items()},
                "gallery_channels": {str(k): v for k, v in gallery_agent_channels.items()},
                "channel_histories": {str(k): v[-AGENT_HISTORY_MESSAGES:] for k, v in channel_histories.items()},
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


def should_agent_reply_in_chat(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
) -> tuple[bool, bool]:
    """Menentukan secara cerdas apakah AI Agent perlu membalas pesan di channel publik.

    Returns:
        (should_reply, use_reply_reference)
    """
    ch_cfg = chat_agent_channels.get(message.channel.id)
    if not ch_cfg or not ch_cfg.get("enabled"):
        return False, False

    now = time.time()
    prev_activity = float(ch_cfg.get("last_activity_at") or 0.0)
    last_bot_at = float(ch_cfg.get("last_bot_reply_at") or 0.0)

    # Catat aktivitas manusia & reset counter pemecah sepi
    ch_cfg["last_activity_at"] = now
    ch_cfg["last_human_at"] = now
    ch_cfg["consecutive_idle_pokes"] = 0

    content = (message.content or "").strip()
    guild_cfg = get_guild_settings(ch_cfg["guild_id"])
    agent_nick = (guild_cfg.get("nickname") or bot_user.display_name or "").strip().lower()

    is_direct_mention = bot_user in message.mentions
    if not is_direct_mention and agent_nick and len(agent_nick) >= 3:
        if re.search(rf"\b{re.escape(agent_nick)}\b", content.lower()):
            is_direct_mention = True

    # Cek apakah pesan ini me-reply pesan seseorang
    replied_to_bot = False
    replied_to_other_human = False
    if message.reference and message.reference.message_id:
        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message):
            if resolved.author.id == bot_user.id:
                replied_to_bot = True
            elif not is_direct_mention:
                replied_to_other_human = True

    # Jangan memotong obrolan ketika member sedang me-reply member lain secara spesifik
    if replied_to_other_human:
        if content:
            _append_channel_history(message.channel.id, "user", f"[{message.author.display_name}]: {content}")
        return False, False

    if is_direct_mention or replied_to_bot:
        return True, True

    # Cooldown singkat agar tidak membanjiri API saat chat sangat ramai
    if now - last_bot_at < AGENT_CHANNEL_COOLDOWN_SEC:
        if content:
            _append_channel_history(message.channel.id, "user", f"[{message.author.display_name}]: {content}")
        return False, False

    if ch_cfg.get("reply_mode") == "all":
        return True, False

    # Mode 'smart' (Natural ala manusia seperti di video):
    # 1. Percakapan dengan bot masih hangat (dalam 6 menit terakhir)
    if last_bot_at > 0 and (now - last_bot_at) <= 360:
        return True, False

    # 2. Channel tadinya sepi (>= 3 menit hening) lalu ada member masuk ngobrol
    if prev_activity == 0 or (now - prev_activity) >= 180:
        return True, True

    # 3. Member mengirim stiker atau pesan reaksi penuh emoji
    has_sticker = bool(getattr(message, "stickers", None))
    has_emoji_expr = bool(_UNICODE_EMOJI_RE.search(content) or "<:" in content or "<a:" in content)
    if has_sticker or (has_emoji_expr and len(content) <= 60):
        return True, True

    # 4. Sapaan / celetukan pemicu obrolan atau nanya jam
    if _GREETING_KEYWORDS.search(content):
        return True, True

    # Simpan sebagai konteks pasif grup jika tidak dibalas langsung
    if content:
        _append_channel_history(message.channel.id, "user", f"[{message.author.display_name}]: {content}")
    return False, False


def _build_community_system_prompt(guild_cfg: dict, bot_display_name: str, time_ctx: dict) -> str:
    agent_name = guild_cfg.get("nickname") or bot_display_name or "Teman"
    style_key = guild_cfg.get("style_preset", "akrab")
    style_guide = STYLE_DESCRIPTIONS.get(style_key, STYLE_DESCRIPTIONS["akrab"])
    extra = guild_cfg.get("custom_prompt", "").strip()

    prompt = (
        f"Nama panggilanmu di server Discord ini adalah '{agent_name}'. "
        "Kamu adalah teman nongkrong komunitas yang asik, santai, peka situasi, dan terasa 100% seperti "
        "manusia asli yang sedang chat di Discord.\n\n"
        "ATURAN PENTING GAYA BICARA:\n"
        f"1. {style_guide}\n"
        "2. JANGAN PERNAH menyebut dirimu AI, bot, robot, asisten virtual, atau buatan Google. Ngobrollah "
        "selayaknya teman manusia biasa.\n"
        "3. Ketik singkat, kasual, dan mengalir seperti chat Discord beneran: cukup 1–2 kalimat pendek "
        "(jangan pakai bullet points, jangan pakai penomoran kaku, dan jangan ceramah panjang).\n"
        "4. Sesekali sapa lawan bicara dengan nama panggilan/display name mereka biar akrab, dan sering "
        "pancing balik dengan pertanyaan ringan supaya obrolan terus nyambung dan hidup.\n"
        "5. Jika member mengirim STIKER atau EMOJI, perhatikan ekspresi visual pada gambar stiker/emoji "
        "tersebut lalu komentari ekspresinya secara spesifik, seru, atau jenaka!\n"
        f"6. WAKTU SEKARANG: {time_ctx['summary']}. Kamu tahu persis jam berapa sekarang ({time_ctx['clock']}) "
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
    http_session: aiohttp.ClientSession | None = None,
) -> str | None:
    active_keys = get_gemini_keys_rotated()
    if not active_keys:
        return None

    req_timeout = CHAT_TIMEOUT if has_media else FAST_TEXT_TIMEOUT
    models_to_try = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)

    async with _borrow_session(http_session, req_timeout) as session:
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
    )

    author_name = message.author.display_name
    desc_prefix = " ".join(media_descs)
    if clean_text and desc_prefix:
        user_turn_text = f"[{author_name}]: {clean_text}\n{desc_prefix}"
    elif clean_text:
        user_turn_text = f"[{author_name}]: {clean_text}"
    elif desc_prefix:
        user_turn_text = f"[{author_name}]: {desc_prefix}"
    else:
        return None

    # Bangun contents dari riwayat singkat channel publik
    contents: list[dict] = []
    for item in channel_histories.get(message.channel.id, []):
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
    system_prompt = _build_community_system_prompt(guild_cfg, bot_display, time_ctx)

    reply = await _call_gemini_agent(
        system_prompt,
        contents,
        temperature=0.88,
        max_tokens=2048,
        thinking_level="minimal",
        has_media=bool(media_parts),
        http_session=http_session,
    )

    if reply:
        # Bersihkan awalan seperti "[NamaBot]:" jika model tidak sengaja menuliskannya
        reply = re.sub(r"^\[[^\]]+\]\s*:\s*", "", reply).strip()
        _append_channel_history(message.channel.id, "user", user_turn_text)
        _append_channel_history(message.channel.id, "model", reply)
        ch_cfg = chat_agent_channels.get(message.channel.id)
        if ch_cfg:
            now = time.time()
            ch_cfg["last_bot_reply_at"] = now
            ch_cfg["last_activity_at"] = now
        await save_agent_config_to_disk()

    return reply


async def generate_idle_icebreaker(
    channel_id: int,
    guild_id: int,
    bot_display_name: str,
    *,
    idle_minutes_elapsed: int = 30,
    http_session: aiohttp.ClientSession | None = None,
) -> str | None:
    """Membuat sapaan/celetukan santai otomatis saat channel chat sedang sepi."""
    guild_cfg = get_guild_settings(guild_id)
    time_ctx = get_realtime_time_context(guild_cfg.get("timezone", BOT_TIMEZONE))
    system_prompt = _build_community_system_prompt(guild_cfg, bot_display_name, time_ctx)

    icebreaker_instruction = (
        f"(Instruksi situasi: Channel chat ini sudah sepi sekitar {max(1, idle_minutes_elapsed)} menit belum ada "
        f"yang ngobrol. Sekarang pukul {time_ctx['clock']} ({time_ctx['vibe']}). "
        "Nyeletuklah duluan secara spontan dan santai 1 kalimat pendek untuk memecah kesunyian atau "
        "menyapa warga server sesuai jam sekarang — contoh vibe seperti 'Aduh sepi amat nih siang-siang, "
        "pada kemana guys?' atau celetukan kreatif lain yang tidak monoton!)"
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
            ch_cfg["consecutive_idle_pokes"] = int(ch_cfg.get("consecutive_idle_pokes") or 0) + 1
        await save_agent_config_to_disk()

    return reply


async def generate_gallery_comment(
    message: discord.Message,
    bot_user: discord.ClientUser | discord.User,
    *,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Men-scan gambar atau video di channel Galeri dan memberikan komentar otomatis yang relevan.

    Returns:
        (comment_text, reaction_emoji)
    """
    gal_cfg = gallery_agent_channels.get(message.channel.id)
    if not gal_cfg or not gal_cfg.get("enabled"):
        return None, None

    async with MEDIA_SEMAPHORE:
        media_parts, media_descs, _ = await extract_social_media_and_stickers(
            message,
            http_session,
            include_video=True,
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

        idle_mins = int(ch_cfg.get("idle_minutes") or 0)
        if idle_mins <= 0:
            continue

        # Anti-spam: jangan terus-terusan monolog sendirian jika belum ada satupun manusia membalas
        if int(ch_cfg.get("consecutive_idle_pokes") or 0) >= AGENT_MAX_IDLE_POKES:
            continue

        last_act = float(ch_cfg.get("last_activity_at") or 0.0)
        elapsed_sec = now - last_act
        if elapsed_sec < idle_mins * 60:
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
            if (time.time() - float(ch_cfg.get("last_activity_at") or 0.0)) < idle_mins * 60:
                continue

            bot_name = (
                channel.guild.me.display_name
                if channel.guild.me
                else (bot.user.display_name if bot.user else "Teman")
            )
            elapsed_mins = int(elapsed_sec // 60)
            icebreaker = await generate_idle_icebreaker(
                channel_id,
                guild_id,
                bot_name,
                idle_minutes_elapsed=elapsed_mins,
                http_session=http_session,
            )
            if icebreaker:
                try:
                    async with channel.typing():
                        await asyncio.sleep(random.uniform(1.0, 2.2))
                        await channel.send(icebreaker)
                    poked_count += 1
                    logger.info("Pemecah sepi terkirim di #%s (%s)", channel.name, channel_id)
                except (discord.Forbidden, discord.HTTPException) as exc:
                    logger.warning("Gagal mengirim pemecah sepi di %s: %s", channel_id, exc)

    return poked_count
