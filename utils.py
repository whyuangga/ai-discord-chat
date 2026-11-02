import base64
from datetime import datetime, timedelta, timezone
import io
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import aiohttp
import discord
from config import (
    BOT_TIMEZONE,
    DISCORD_BOT_TOKEN,
    GEMINI_API_KEY,
    MAX_AUDIO_ATTACHMENT_BYTES,
    MAX_IMAGE_ATTACHMENT_BYTES,
    MAX_IMAGES_PER_MESSAGE,
    MAX_STICKER_EMOJI_BYTES,
    MAX_TEXT_ATTACHMENT_BYTES,
    MAX_VIDEO_ATTACHMENT_BYTES,
    parse_gemini_keys,
)
from storage import is_bot_ui_message

IMAGE_MIME_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

AUDIO_MIME_BY_EXT: dict[str, str] = {
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".m4a": "audio/aac",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}

AUDIO_MIME_ALIASES: dict[str, str] = {
    "audio/ogg": "audio/ogg",
    "audio/opus": "audio/ogg",
    "application/ogg": "audio/ogg",
    "audio/mpeg": "audio/mp3",
    "audio/mp3": "audio/mp3",
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/aac": "audio/aac",
    "audio/mp4": "audio/aac",
    "audio/m4a": "audio/aac",
    "audio/x-m4a": "audio/aac",
    "audio/flac": "audio/flac",
    "audio/x-flac": "audio/flac",
    "audio/aiff": "audio/aiff",
    "audio/x-aiff": "audio/aiff",
}

VIDEO_MIME_BY_EXT: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}

SUPPORTED_IMAGE_MIMES = set(IMAGE_MIME_BY_EXT.values())
SUPPORTED_VIDEO_MIMES = set(VIDEO_MIME_BY_EXT.values())


def is_discord_voice_attachment(att) -> bool:
    """Mendeteksi apakah lampiran adalah Voice Note (Pesan Suara 🎤) asli Discord."""
    checker = getattr(att, "is_voice_message", None)
    if callable(checker):
        try:
            if checker():
                return True
        except Exception:
            pass
    fname = str(getattr(att, "filename", "") or "").lower()
    has_waveform = bool(getattr(att, "waveform", None))
    return has_waveform or fname.startswith("voice-message.")


def resolve_audio_mime(att) -> str | None:
    """Menentukan MIME audio standar Gemini untuk lampiran Voice Note atau file suara."""
    if is_discord_voice_attachment(att):
        return "audio/ogg"
    ext = Path(str(getattr(att, "filename", "") or "")).suffix.lower()
    content_type = (getattr(att, "content_type", None) or "").split(";")[0].strip().lower()
    if content_type in AUDIO_MIME_ALIASES:
        return AUDIO_MIME_ALIASES[content_type]
    return AUDIO_MIME_BY_EXT.get(ext)


def has_voice_or_audio_attachment(message) -> bool:
    """Mengecek cepat apakah sebuah pesan Discord berisi Voice Note atau lampiran audio."""
    flags = getattr(message, "flags", None)
    if flags is not None and bool(getattr(flags, "voice", False)):
        return True
    for att in getattr(message, "attachments", []) or []:
        if resolve_audio_mime(att) is not None:
            return True
    return False

_CUSTOM_EMOJI_RE = re.compile(r"<(a?):([a-zA-Z0-9_]{2,32}):(\d{15,22})>")

_INDONESIAN_DAYS = (
    "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"
)
_INDONESIAN_MONTHS = (
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
)
_TZ_FALLBACK_OFFSETS = {
    "Asia/Jakarta": (7, "WIB"),
    "Asia/Makassar": (8, "WITA"),
    "Asia/Jayapura": (9, "WIT"),
}


def get_realtime_time_context(tz_name: str = BOT_TIMEZONE) -> dict:
    """Menghasilkan informasi jam, hari, tanggal, dan suasana waktu lokal secara real-time."""
    clean_tz = (tz_name or "Asia/Jakarta").strip()
    tz_label = _TZ_FALLBACK_OFFSETS.get(clean_tz, (7, clean_tz))[1]

    try:
        tz_obj = ZoneInfo(clean_tz)
    except ZoneInfoNotFoundError:
        offset_hours, tz_label = _TZ_FALLBACK_OFFSETS.get(clean_tz, (7, "WIB"))
        tz_obj = timezone(timedelta(hours=offset_hours))

    now = datetime.now(tz_obj)
    hour = now.hour
    clock_str = now.strftime("%H:%M")
    day_name = _INDONESIAN_DAYS[now.weekday()]
    date_str = f"{now.day} {_INDONESIAN_MONTHS[now.month]} {now.year}"

    if 5 <= hour < 10:
        vibe = "Pagi hari (suasana segar, mulai beraktivitas / sarapan)"
    elif 10 <= hour < 15:
        vibe = "Siang hari / siang bolong (jam sibuk, istirahat makan siang, atau cuaca terik)"
    elif 15 <= hour < 18:
        vibe = "Sore hari (jam-jam rawan ngantuk, santai sore, atau pulang aktivitas)"
    elif 18 <= hour < 22:
        vibe = "Malam hari (waktunya istirahat, nongkrong santai, atau mabar game)"
    else:
        vibe = "Larut malam / dini hari (jam begadang, suasana sunyi, waktunya tidur)"

    summary = f"{day_name}, {date_str} | Pukul {clock_str} {tz_label} — {vibe}"
    return {
        "hour": hour,
        "minute": now.minute,
        "clock": f"{clock_str} {tz_label}",
        "day_name": day_name,
        "date_str": date_str,
        "tz_label": tz_label,
        "vibe": vibe,
        "summary": summary,
    }

TEXT_FILE_EXTENSIONS: set[str] = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".html",
    ".css", ".scss", ".sql", ".csv", ".log", ".sh", ".bash",
    ".bat", ".ps1", ".c", ".cpp", ".h", ".hpp", ".cs", ".java",
    ".kt", ".go", ".rs", ".php", ".rb", ".lua", ".xml", ".dockerfile",
}

_FENCE_RE = re.compile(r"^\s*(`{3,})([\w.+-]*)\s*$")


def sanitize_error_message(error: Exception | str) -> str:
    """Menyembunyikan token/API key jika tidak sengaja muncul dalam pesan error."""
    text = str(error)
    secrets = [GEMINI_API_KEY, DISCORD_BOT_TOKEN, *parse_gemini_keys(GEMINI_API_KEY)]
    for secret in secrets:
        if secret and len(secret) >= 8 and secret in text:
            text = text.replace(secret, "[REDACTED]")
    return text


def _toggle_fence_state(line: str, current_fence: str | None) -> str | None:
    match = _FENCE_RE.match(line.rstrip("\r\n"))
    if not match:
        return current_fence
    ticks, lang = match.group(1), match.group(2)
    if current_fence is None:
        return f"{ticks}{lang}"
    # Menutup fence jika jumlah backtick sama atau lebih panjang dan tidak ada info bahasa baru
    opening_ticks = re.match(r"^`+", current_fence)
    min_ticks = len(opening_ticks.group(0)) if opening_ticks else 3
    if len(ticks) >= min_ticks and not lang:
        return None
    return current_fence


def _split_oversized_line(line: str, limit: int) -> list[str]:
    """Memecah satu baris sangat panjang berdasarkan spasi atau batas karakter."""
    parts: list[str] = []
    remaining = line
    while len(remaining) > limit:
        cut = remaining.rfind(" ", 0, limit)
        if cut <= limit // 3:
            cut = limit
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip(" ")
    if remaining:
        parts.append(remaining)
    return parts


def split_discord_message(text: str, max_length: int = 1900) -> list[str]:
    """Memotong balasan panjang agar sesuai batas 2000 karakter Discord
    tanpa memutus kata atau merusak blok kode Markdown (```...```).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ["*(Tidak ada respons teks)*"]
    if len(cleaned) <= max_length:
        return [cleaned]

    chunks: list[str] = []
    current_buf = ""
    open_fence: str | None = None

    for raw_line in cleaned.splitlines(keepends=True):
        next_fence = _toggle_fence_state(raw_line, open_fence)
        closing_reserve = 5 if next_fence is not None else 0
        available_for_single_line = max_length - (len(open_fence) + 1 if open_fence else 0) - closing_reserve

        if len(raw_line) > available_for_single_line:
            # Flush buffer yang ada terlebih dahulu
            if current_buf.strip():
                if open_fence is not None:
                    chunks.append(f"{current_buf.rstrip()}\n```")
                    current_buf = f"{open_fence}\n"
                else:
                    chunks.append(current_buf.rstrip())
                    current_buf = ""

            sub_limit = max(100, max_length - (len(open_fence) + 1 if open_fence else 0) - 6)
            sub_lines = _split_oversized_line(raw_line.rstrip("\r\n"), sub_limit)
            for idx, sub in enumerate(sub_lines):
                piece = f"{open_fence}\n{sub}" if (open_fence and not current_buf) else f"{current_buf}{sub}"
                is_last = idx == len(sub_lines) - 1
                if not is_last:
                    if open_fence is not None:
                        chunks.append(f"{piece}\n```")
                        current_buf = f"{open_fence}\n"
                    else:
                        chunks.append(piece)
                        current_buf = ""
                else:
                    current_buf = f"{piece}\n" if raw_line.endswith("\n") else piece
            open_fence = next_fence
            continue

        if len(current_buf) + len(raw_line) + closing_reserve > max_length and current_buf:
            if open_fence is not None:
                chunks.append(f"{current_buf.rstrip()}\n```")
                current_buf = f"{open_fence}\n{raw_line}"
            else:
                chunks.append(current_buf.rstrip())
                current_buf = raw_line
        else:
            current_buf += raw_line

        open_fence = next_fence

    if current_buf.strip():
        if open_fence is not None:
            # Jika dari model sendiri lupa menutup blok kode, tutup otomatis
            if len(current_buf) + 4 <= max_length:
                chunks.append(f"{current_buf.rstrip()}\n```")
            else:
                chunks.append(current_buf.rstrip())
        else:
            chunks.append(current_buf.rstrip())

    return chunks or [cleaned[:max_length]]


async def extract_message_attachments(
    message: discord.Message,
    http_session: aiohttp.ClientSession | None = None,
    *,
    include_audio: bool = True,
) -> tuple[list[dict], list[str], list[str], list[str]]:
    """Mengekstrak lampiran gambar (Vision), Voice Note / Audio, Stiker Discord, dan file teks/kode.

    Returns:
        (media_parts, media_filenames, text_blocks, warnings)
    """
    image_parts: list[dict] = []
    image_filenames: list[str] = []
    text_blocks: list[str] = []
    warnings: list[str] = []

    for att in getattr(message, "attachments", []) or []:
        ext = Path(att.filename).suffix.lower()
        content_type = (att.content_type or "").split(";")[0].strip().lower()

        # 1. Deteksi Lampiran Gambar (Vision / Image Edit)
        mime = content_type if content_type in SUPPORTED_IMAGE_MIMES else IMAGE_MIME_BY_EXT.get(ext)
        if mime:
            if len(image_parts) >= MAX_IMAGES_PER_MESSAGE:
                warnings.append(f"Maksimal {MAX_IMAGES_PER_MESSAGE} lampiran media per pesan (`{att.filename}` dilewati).")
                continue
            if att.size > MAX_IMAGE_ATTACHMENT_BYTES:
                max_mb = MAX_IMAGE_ATTACHMENT_BYTES // (1024 * 1024)
                warnings.append(f"Ukuran gambar `{att.filename}` melebihi batas {max_mb} MB.")
                continue
            try:
                raw_bytes = await att.read()
                b64_data = base64.b64encode(raw_bytes).decode("ascii")
                image_parts.append({"inlineData": {"mimeType": mime, "data": b64_data}})
                image_filenames.append(att.filename)
            except Exception as exc:
                warnings.append(f"Gagal membaca gambar `{att.filename}`: {sanitize_error_message(exc)}")
            continue

        # 2. Deteksi Voice Note (Pesan Suara 🎤) & File Audio (.ogg, .mp3, .wav, .m4a, .flac)
        audio_mime = resolve_audio_mime(att)
        if audio_mime:
            if not include_audio:
                warnings.append("Ruang gambar hanya menerima lampiran gambar referensi (bukan audio/voice note).")
                continue
            if len(image_parts) >= MAX_IMAGES_PER_MESSAGE:
                warnings.append(f"Maksimal {MAX_IMAGES_PER_MESSAGE} lampiran media per pesan (`{att.filename}` dilewati).")
                continue
            if att.size > MAX_AUDIO_ATTACHMENT_BYTES:
                max_mb = MAX_AUDIO_ATTACHMENT_BYTES // (1024 * 1024)
                warnings.append(f"Ukuran audio `{att.filename}` melebihi batas {max_mb} MB.")
                continue
            try:
                raw_bytes = await att.read()
                b64_data = base64.b64encode(raw_bytes).decode("ascii")
                image_parts.append({"inlineData": {"mimeType": audio_mime, "data": b64_data}})
                prefix = "voice_note:" if is_discord_voice_attachment(att) else "audio:"
                image_filenames.append(f"{prefix}{att.filename}")
            except Exception as exc:
                warnings.append(f"Gagal membaca pesan suara/audio `{att.filename}`: {sanitize_error_message(exc)}")
            continue

        # 3. Deteksi Lampiran File Teks / Kode Sumber
        if ext in TEXT_FILE_EXTENSIONS or content_type.startswith("text/"):
            if att.size > MAX_TEXT_ATTACHMENT_BYTES:
                max_kb = MAX_TEXT_ATTACHMENT_BYTES // 1024
                warnings.append(f"File teks `{att.filename}` melebihi batas {max_kb} KB.")
                continue
            try:
                raw_bytes = await att.read()
                decoded = raw_bytes.decode("utf-8", errors="replace").strip()
                if decoded:
                    lang_hint = ext.lstrip(".")
                    text_blocks.append(f"📄 **Lampiran File `{att.filename}`:**\n```{lang_hint}\n{decoded}\n```")
            except Exception as exc:
                warnings.append(f"Gagal membaca file `{att.filename}`: {sanitize_error_message(exc)}")
            continue

        warnings.append(
            f"Format lampiran `{att.filename}` belum didukung (gunakan gambar, Voice Note/audio, atau file teks/kode)."
        )

    # 3. Deteksi Stiker Discord di ruang chat privat
    for sticker in getattr(message, "stickers", []) or []:
        s_name = getattr(sticker, "name", "stiker")
        fmt = getattr(sticker, "format", None)
        s_url = str(getattr(sticker, "url", "") or "")
        if fmt != discord.StickerFormatType.lottie and s_url and len(image_parts) < MAX_IMAGES_PER_MESSAGE:
            try:
                raw_s = await _fetch_small_media_bytes(s_url, http_session)
                if raw_s:
                    s_mime = "image/gif" if fmt == discord.StickerFormatType.gif else "image/png"
                    image_parts.append({"inlineData": {"mimeType": s_mime, "data": base64.b64encode(raw_s).decode("ascii")}})
                    image_filenames.append(f"stiker:{s_name}")
                    continue
            except Exception:
                pass
        text_blocks.append(f'[Pengguna mengirim Stiker Discord bernama "{s_name}"]')

    return image_parts, image_filenames, text_blocks, warnings


async def _fetch_small_media_bytes(
    url: str,
    http_session: aiohttp.ClientSession | None,
    max_bytes: int = MAX_STICKER_EMOJI_BYTES,
) -> bytes | None:
    """Mengunduh gambar stiker atau custom emoji Discord secara aman dengan batas ukuran."""
    timeout = aiohttp.ClientTimeout(total=12, connect=6)
    if http_session is not None and not http_session.closed:
        async with http_session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = await resp.content.read(max_bytes + 1)
            return data if len(data) <= max_bytes else None

    async with aiohttp.ClientSession(timeout=timeout) as temp:
        async with temp.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = await resp.content.read(max_bytes + 1)
            return data if len(data) <= max_bytes else None


async def extract_social_media_and_stickers(
    message: discord.Message,
    http_session: aiohttp.ClientSession | None = None,
    *,
    include_video: bool = True,
    include_audio: bool = True,
) -> tuple[list[dict], list[str], list[str]]:
    """Mengekstrak gambar, Voice Note / Audio, video pendek (Galeri), Stiker Discord, serta Custom Emoji
    agar AI Agent dapat mendengar pesan suara maupun melihat visual ekspresi stiker/emoji/foto/video!

    Returns:
        (media_parts, descriptions, warnings)
    """
    media_parts: list[dict] = []
    descriptions: list[str] = []
    warnings: list[str] = []

    # 1. Lampiran File Gambar, Voice Note / Audio, & Video Klip
    for att in getattr(message, "attachments", []) or []:
        ext = Path(att.filename).suffix.lower()
        content_type = (att.content_type or "").split(";")[0].strip().lower()

        img_mime = content_type if content_type in SUPPORTED_IMAGE_MIMES else IMAGE_MIME_BY_EXT.get(ext)
        if img_mime:
            if len(media_parts) >= MAX_IMAGES_PER_MESSAGE:
                continue
            if att.size > MAX_IMAGE_ATTACHMENT_BYTES:
                warnings.append(f"Gambar `{att.filename}` terlalu besar (> {MAX_IMAGE_ATTACHMENT_BYTES // (1024 * 1024)} MB).")
                continue
            try:
                raw = await att.read()
                b64 = base64.b64encode(raw).decode("ascii")
                media_parts.append({"inlineData": {"mimeType": img_mime, "data": b64}})
                descriptions.append(f"[Mengirim foto/gambar: {att.filename}]")
            except Exception as exc:
                warnings.append(f"Gagal membaca gambar `{att.filename}`: {sanitize_error_message(exc)}")
            continue

        audio_mime = resolve_audio_mime(att)
        if include_audio and audio_mime:
            if len(media_parts) >= MAX_IMAGES_PER_MESSAGE:
                continue
            if att.size > MAX_AUDIO_ATTACHMENT_BYTES:
                warnings.append(
                    f"Audio `{att.filename}` melebihi batas {MAX_AUDIO_ATTACHMENT_BYTES // (1024 * 1024)} MB."
                )
                continue
            try:
                raw = await att.read()
                b64 = base64.b64encode(raw).decode("ascii")
                media_parts.append({"inlineData": {"mimeType": audio_mime, "data": b64}})
                dur = getattr(att, "duration", None)
                dur_info = f" ({dur:.0f} detik)" if isinstance(dur, (int, float)) and dur > 0 else ""
                if is_discord_voice_attachment(att):
                    descriptions.append(
                        f"[Mengirim Voice Note / Pesan Suara{dur_info} — dengarkan isi ucapannya dan balas langsung!]"
                    )
                else:
                    descriptions.append(f"[Mengirim file audio: {att.filename}{dur_info} — dengarkan isinya!]")
            except Exception as exc:
                warnings.append(f"Gagal membaca pesan suara/audio `{att.filename}`: {sanitize_error_message(exc)}")
            continue

        vid_mime = content_type if content_type in SUPPORTED_VIDEO_MIMES else VIDEO_MIME_BY_EXT.get(ext)
        if include_video and vid_mime:
            if att.size > MAX_VIDEO_ATTACHMENT_BYTES:
                warnings.append(
                    f"Video `{att.filename}` melebihi batas {MAX_VIDEO_ATTACHMENT_BYTES // (1024 * 1024)} MB untuk di-scan AI."
                )
                continue
            try:
                raw = await att.read()
                b64 = base64.b64encode(raw).decode("ascii")
                media_parts.append({"inlineData": {"mimeType": vid_mime, "data": b64}})
                descriptions.append(f"[Mengirim video: {att.filename}]")
            except Exception as exc:
                warnings.append(f"Gagal membaca video `{att.filename}`: {sanitize_error_message(exc)}")

    # 2. Stiker Discord (PNG / APNG / GIF dapat dilihat langsung visualnya oleh Gemini Vision!)
    for sticker in getattr(message, "stickers", []) or []:
        sticker_name = getattr(sticker, "name", "stiker")
        fmt = getattr(sticker, "format", None)
        sticker_url = str(getattr(sticker, "url", "") or "")

        if fmt != discord.StickerFormatType.lottie and sticker_url and len(media_parts) < MAX_IMAGES_PER_MESSAGE:
            try:
                raw_sticker = await _fetch_small_media_bytes(sticker_url, http_session)
                if raw_sticker:
                    s_mime = "image/gif" if fmt == discord.StickerFormatType.gif else "image/png"
                    b64 = base64.b64encode(raw_sticker).decode("ascii")
                    media_parts.append({"inlineData": {"mimeType": s_mime, "data": b64}})
                    descriptions.append(f'[Mengirim Stiker Discord bernama "{sticker_name}" — lihat gambar stikernya]')
                    continue
            except Exception:
                pass

        descriptions.append(f'[Mengirim Stiker Discord bernama "{sticker_name}"]')

    # 3. Custom Emoji Server (<:nama:id> atau <a:nama:id>) -> Unduh visual ekspresinya!
    content_str = getattr(message, "content", "") or ""
    custom_emojis = _CUSTOM_EMOJI_RE.findall(content_str)
    for is_anim, emoji_name, emoji_id in custom_emojis[:2]:
        if len(media_parts) >= MAX_IMAGES_PER_MESSAGE:
            descriptions.append(f"[Menggunakan custom emoji :{emoji_name}:]")
            continue
        ext = "gif" if is_anim else "png"
        emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128"
        try:
            raw_emoji = await _fetch_small_media_bytes(emoji_url, http_session)
            if raw_emoji:
                e_mime = "image/gif" if is_anim else "image/png"
                b64 = base64.b64encode(raw_emoji).decode("ascii")
                media_parts.append({"inlineData": {"mimeType": e_mime, "data": b64}})
                descriptions.append(f"[Menggunakan custom emoji :{emoji_name}: — lihat ekspresi gambar emojinya]")
                continue
        except Exception:
            pass
        descriptions.append(f"[Menggunakan custom emoji :{emoji_name}:]")

    return media_parts, descriptions, warnings


def _close_unbalanced_fence_in_preview(preview: str) -> str:
    fence_state: str | None = None
    for line in preview.splitlines():
        fence_state = _toggle_fence_state(line, fence_state)
    if fence_state is not None:
        return f"{preview}\n```"
    return preview


async def build_session_transcript(
    channel: discord.Thread,
    requester: discord.abc.User,
    bot_user_id: int,
) -> tuple[discord.Embed, discord.File | None]:
    """Menyusun Embed ringkasan dan file transkrip lengkap (.txt) untuk dikirim sebelum sesi ditutup."""
    is_image_session = channel.name.startswith("draw-")
    session_type = "🎨 Generate Gambar AI" if is_image_session else "💬 Chat Teks & Vision Gemini"

    embed_entries: list[str] = []
    txt_entries: list[str] = [
        "============================================================",
        "REKAP SESI AI PRIBADI DISCORD",
        f"Tipe Sesi : {session_type}",
        f"Ruang     : #{channel.name}",
        f"Pengguna  : {requester} ({requester.id})",
        "============================================================",
        "",
    ]

    async for msg in channel.history(limit=200, oldest_first=True):
        content = (msg.content or "").strip()
        if is_bot_ui_message(content):
            continue
        if msg.author.id == bot_user_id and msg.embeds and not content and not msg.attachments:
            continue

        attachment_notes = [f"[Lampiran: {a.filename}]" for a in msg.attachments]
        combined = "\n".join(filter(None, [content, " ".join(attachment_notes)])).strip()
        if not combined:
            continue

        is_bot = msg.author.id == bot_user_id
        sender_embed = "🤖 Gemini AI" if is_bot else f"👤 {msg.author.display_name}"
        sender_txt = "GEMINI AI" if is_bot else f"USER ({msg.author.display_name})"
        timestamp_str = msg.created_at.strftime("%Y-%m-%d %H:%M UTC")

        embed_entries.append(f"**{sender_embed}:**\n{combined}")
        txt_entries.append(f"[{timestamp_str}] {sender_txt}:\n{combined}\n")

    if embed_entries:
        preview_body = "\n\n".join(embed_entries)
        if len(preview_body) > 3400:
            preview_body = _close_unbalanced_fence_in_preview(preview_body[:3400].rstrip())
            preview_body += "\n\n*(Ringkasan dipotong — buka lampiran file `.txt` untuk transkrip utuh)*"
    else:
        preview_body = "*Tidak ada percakapan yang tercatat pada sesi ini.*"

    embed = discord.Embed(
        title="📜 Rekap Sesi Gemini AI Anda",
        description=(
            f"**📍 Tipe Sesi:** {session_type}\n"
            f"**📍 Ruang:** `{channel.name}`\n"
            f"**💬 Total Pesan:** `{len(embed_entries)}` pesan\n\n"
            f"---\n\n{preview_body}"
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="Salinan transkrip pribadi — hanya dikirimkan untuk Anda.")

    transcript_file: discord.File | None = None
    if embed_entries:
        full_txt = "\n".join(txt_entries)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", channel.name)[:40] or "sesi-ai"
        transcript_file = discord.File(
            io.BytesIO(full_txt.encode("utf-8")),
            filename=f"rekap-{safe_name}.txt",
        )

    return embed, transcript_file
