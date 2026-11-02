import asyncio
import base64
from datetime import datetime, timedelta, timezone
import html
import io
import ipaddress
import re
from pathlib import Path
import urllib.parse
import xml.etree.ElementTree as ET
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
    MAX_WEBPAGE_FETCH_BYTES,
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
    """Menyembunyikan token/API key serta membersihkan pesan kuota/URL mentah agar tidak memicu preview besar di Discord."""
    text = str(error)
    secrets = [GEMINI_API_KEY, DISCORD_BOT_TOKEN, *parse_gemini_keys(GEMINI_API_KEY)]
    for secret in secrets:
        if secret and len(secret) >= 8 and secret in text:
            text = text.replace(secret, "[REDACTED]")

    lower = text.lower()
    if "exceeded your current quota" in lower or "check your plan and billing" in lower:
        return "Batas kuota per menit Gemini Free Tier sedang penuh sesaat, silakan coba beberapa detik lagi."

    # Cegah URL dokumentasi Google/eksternal memunculkan kartu link preview raksasa di pesan error Discord
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" .:-")
    return text or "Terjadi gangguan sementara pada layanan AI."


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


# ==============================================================================
# DETEKTOR LINK YOUTUBE, PEMBACA ARTIKEL WEB AMAN, & PEMICU GOOGLE SEARCH
# ==============================================================================
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_IGNORED_WEB_DOMAINS = (
    "cdn.discordapp.com",
    "media.discordapp.net",
    "discord.gg",
    "discord.com",
    "discordapp.com",
    "tenor.com",
    "giphy.com",
)

_LIVE_SEARCH_TRIGGER_RE = re.compile(
    r"("
    r"\bcari(?:in|kan)?\s+(?:di\s+)?(?:google|internet|web|berita|info)\b|"
    r"\b(?:berita|kabar|info|update|rilis|patch)\s+(?:hari\s+ini|terbaru|terkini|sekarang|minggu\s+ini|202[5-9])\b|"
    r"\b(?:skor|hasil\s+pertandingan|klasemen|jadwal\s+(?:bola|pertandingan|mpl|valorant|liga|bioskop))\b|"
    r"\b(?:cuaca|prakiraan\s+cuaca|gempa)\s+(?:hari\s+ini|sekarang|terkini|di\s+\w+)\b|"
    r"\b(?:harga|kurs|nilai\s+tukar)\s+(?:emas|dollar|dolar|usd|rupiah|idr|bitcoin|btc|crypto|saham|bbm)\b|"
    r"\bsiapa\s+(?:presiden|juara|pemenang|pelatih|ceo|menteri|gubernur)\b|"
    r"\b(?:tadi\s+malam|semalam|kemarin|barusan)\s+(?:siapa\s+yang\s+menang|ada\s+berita\s+apa)\b"
    r")",
    re.IGNORECASE,
)


def normalize_youtube_url(url: str) -> str | None:
    """Mengubah berbagai variasi link YouTube (youtu.be, shorts, live, mobile) ke format kanonik."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if host.startswith("www.") or host.startswith("m."):
        host = host.split(".", 1)[1]

    video_id: str | None = None
    if host == "youtu.be":
        seg = parsed.path.strip("/").split("/")[0]
        if _YT_ID_RE.match(seg):
            video_id = seg
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        qs = urllib.parse.parse_qs(parsed.query)
        if "v" in qs and qs["v"] and _YT_ID_RE.match(qs["v"][0]):
            video_id = qs["v"][0]
        else:
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v") and _YT_ID_RE.match(parts[1]):
                video_id = parts[1]

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def is_safe_public_url(url: str) -> bool:
    """Mencegah SSRF dengan memastikan URL mengarah ke host publik HTTP/HTTPS (bukan localhost/IP privat)."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host or host in ("localhost", "0.0.0.0") or host.endswith((".local", ".internal", ".localhost")):
        return False

    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    except ValueError:
        # Hostname domain biasa (bukan literal IP) -> pastikan memiliki titik domain publik
        if "." not in host:
            return False

    return True


def extract_urls_from_text(text: str, *, include_ignored_domains: bool = False) -> tuple[list[str], list[str]]:
    """Mengekstrak hingga 2 URL YouTube kanonik dan hingga 2 URL artikel/halaman web publik dari teks."""
    if not text:
        return [], []

    yt_urls: list[str] = []
    web_urls: list[str] = []

    for match in _URL_RE.findall(text):
        cleaned = match.rstrip(".,;:!?\"')]>")
        yt_canon = normalize_youtube_url(cleaned)
        if yt_canon:
            if yt_canon not in yt_urls and len(yt_urls) < 2:
                yt_urls.append(yt_canon)
            continue

        if not is_safe_public_url(cleaned):
            continue

        host = (urllib.parse.urlparse(cleaned).hostname or "").lower()
        if not include_ignored_domains and any(
            host == dom or host.endswith(f".{dom}") for dom in _IGNORED_WEB_DOMAINS
        ):
            continue

        # Lewati link file gambar/video/audio mentah karena sudah ditangani ekstraktor media
        path_lower = urllib.parse.urlparse(cleaned).path.lower()
        if path_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mp3", ".ogg", ".wav")):
            continue

        if cleaned not in web_urls and len(web_urls) < 2:
            web_urls.append(cleaned)

    return yt_urls, web_urls


def clean_html_to_readable_text(raw_html: str, max_chars: int = 8000) -> tuple[str | None, str]:
    """Mengekstrak judul dan teks bersih dari HTML tanpa membutuhkan library eksternal seperti BeautifulSoup."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else None

    meta_desc = ""
    meta_match = re.search(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        flags=re.IGNORECASE,
    )
    if meta_match:
        meta_desc = html.unescape(meta_match.group(1).strip())

    # Buang bagian script, style, svg, nav, footer, dan komentar HTML
    cleaned = re.sub(
        r"<(script|style|noscript|svg|iframe|header|footer|nav)[^>]*>.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"</?(?:p|div|br|li|tr|h[1-6]|article|section|blockquote)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)

    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in cleaned.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 2]
    body = "\n".join(lines)
    if meta_desc and meta_desc not in body[:600]:
        body = f"Deskripsi Ringkas: {meta_desc}\n\n{body}"

    return title, body[:max_chars].strip()


async def _is_resolved_host_public(url: str) -> bool:
    """Memastikan hasil resolusi DNS hostname tidak mengarah ke IP privat/loopback (anti-DNS Rebinding SSRF)."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").strip()
        if not host:
            return False
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(loop.getaddrinfo(host, None), timeout=3.0)
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            ip_obj = ipaddress.ip_address(sockaddr[0])
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


async def fetch_webpage_text(
    url: str,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Mengunduh dan mengekstrak isi teks halaman web publik secara ringan & aman dari SSRF.

    Returns:
        (page_title, extracted_text) — extracted_text bernilai None jika gagal/diblokir situs.
    """
    if not is_safe_public_url(url):
        return None, None

    # Validasi resolusi DNS non-blocking saat memakai koneksi jaringan nyata
    if http_session is None or isinstance(http_session, aiohttp.ClientSession):
        if not await _is_resolved_host_public(url):
            return None, None

    timeout = aiohttp.ClientTimeout(total=10, connect=5)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DiscordGeminiAssistant/1.2; +https://github.com)",
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.5",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    async def _do_get(sess: aiohttp.ClientSession) -> tuple[str | None, str | None]:
        async with sess.get(url, headers=headers, timeout=timeout, allow_redirects=True, max_redirects=4) as resp:
            final_url = str(resp.url)
            if not is_safe_public_url(final_url) or resp.status >= 400:
                return None, None
            if isinstance(sess, aiohttp.ClientSession) and not await _is_resolved_host_public(final_url):
                return None, None

            ctype = (resp.headers.get("Content-Type") or "").lower()
            if not any(t in ctype for t in ("text/", "json", "xml", "xhtml", "javascript")) and ctype:
                return None, None

            raw_bytes = await resp.content.read(MAX_WEBPAGE_FETCH_BYTES)
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            if "html" in ctype or "<html" in raw_text[:500].lower():
                title, body = clean_html_to_readable_text(raw_text)
                return title, (body if len(body) >= 30 else None)
            return None, raw_text[:8000].strip() or None

    try:
        if http_session is not None and not http_session.closed:
            return await _do_get(http_session)
        async with aiohttp.ClientSession(timeout=timeout) as temp:
            return await _do_get(temp)
    except Exception:
        return None, None


def needs_live_web_search(text: str) -> bool:
    """Mendeteksi apakah kalimat pengguna menanyakan informasi/berita terkini yang membutuhkan Google Search."""
    cleaned = (text or "").strip()
    if len(cleaned) < 6:
        return False
    return bool(_LIVE_SEARCH_TRIGGER_RE.search(cleaned))


def has_youtube_url(text: str) -> bool:
    """Mengecek cepat apakah sebuah teks pesan mengandung link video YouTube."""
    if not text:
        return False
    for match in _URL_RE.findall(text):
        if normalize_youtube_url(match.rstrip(".,;:!?\"')]>")):
            return True
    return False


def _strip_html_inline(raw: str) -> str:
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _unwrap_ddg_url(raw_href: str) -> str:
    href = html.unescape((raw_href or "").strip())
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in (parsed.hostname or "").lower():
        qs = urllib.parse.parse_qs(parsed.query)
        if qs.get("uddg"):
            return qs["uddg"][0].strip()
    return href


async def _search_duckduckgo_html(
    query: str,
    session: aiohttp.ClientSession,
    max_items: int = 5,
) -> list[dict]:
    """Mengambil hasil pencarian web umum gratis dari DuckDuckGo HTML (tanpa API key)."""
    encoded = urllib.parse.quote_plus(query.strip())
    url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=id-id"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    timeout = aiohttp.ClientTimeout(total=7, connect=4)
    results: list[dict] = []
    try:
        async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as resp:
            if resp.status != 200:
                return []
            raw_bytes = await resp.content.read(220 * 1024)
            page = raw_bytes.decode("utf-8", errors="replace")

        blocks = re.findall(
            r'<div[^>]+class="[^"]*result__body[^"]*"[^>]*>(.*?)</div>\s*</div>',
            page,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not blocks:
            blocks = page.split('class="result__body"')

        for blk in blocks:
            a_match = re.search(
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                blk,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not a_match:
                continue
            target_url = _unwrap_ddg_url(a_match.group(1))
            if not target_url.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in target_url:
                continue
            title = _strip_html_inline(a_match.group(2))
            snip_match = re.search(
                r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|span)>',
                blk,
                flags=re.IGNORECASE | re.DOTALL,
            )
            snippet = _strip_html_inline(snip_match.group(1)) if snip_match else ""
            if title:
                results.append(
                    {
                        "title": title[:120],
                        "url": target_url,
                        "snippet": snippet[:320],
                        "date": "",
                        "kind": "web",
                    }
                )
            if len(results) >= max_items:
                break
    except Exception:
        return []
    return results


async def _search_google_news_rss(
    query: str,
    session: aiohttp.ClientSession,
    max_items: int = 5,
) -> list[dict]:
    """Mengambil berita terbaru hari ini secara real-time dari Google News RSS Indonesia (gratis & anti-blokir)."""
    encoded = urllib.parse.quote_plus(query.strip())
    url = f"https://news.google.com/rss/search?q={encoded}&hl=id&gl=ID&ceid=ID:id"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DiscordGeminiAssistant/1.2)",
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    }
    timeout = aiohttp.ClientTimeout(total=7, connect=4)
    results: list[dict] = []
    try:
        async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as resp:
            if resp.status != 200:
                return []
            raw_xml = (await resp.content.read(220 * 1024)).decode("utf-8", errors="replace")

        root = ET.fromstring(raw_xml)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = _strip_html_inline(item.findtext("description") or "")
            src_el = item.find("source")
            src_name = (src_el.text or "").strip() if src_el is not None else ""
            src_url = (src_el.attrib.get("url") or "").strip() if src_el is not None else ""

            if not title:
                continue
            results.append(
                {
                    "title": title[:130],
                    "url": link or src_url,
                    "source_label": src_name or title[:45],
                    "snippet": desc[:280],
                    "date": pub_date[:25],
                    "kind": "news",
                }
            )
            if len(results) >= max_items:
                break
    except Exception:
        return []
    return results


async def _search_wikipedia_api(
    query: str,
    session: aiohttp.ClientSession,
    max_items: int = 3,
) -> list[dict]:
    """Cadangan pencarian fakta ensiklopedia dari Wikipedia Bahasa Indonesia (JSON ringan, selalu gratis)."""
    encoded = urllib.parse.quote_plus(query.strip())
    url = (
        f"https://id.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={encoded}&srlimit={max_items}&utf8=1&format=json"
    )
    headers = {"User-Agent": "DiscordGeminiAssistant/1.2 (https://github.com)"}
    timeout = aiohttp.ClientTimeout(total=6, connect=4)
    results: list[dict] = []
    try:
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
        for row in (data.get("query") or {}).get("search") or []:
            title = str(row.get("title") or "").strip()
            snippet = _strip_html_inline(str(row.get("snippet") or ""))
            if title:
                wiki_url = f"https://id.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append(
                    {
                        "title": f"{title} — Wikipedia",
                        "url": wiki_url,
                        "snippet": snippet[:300],
                        "date": "",
                        "kind": "wiki",
                    }
                )
    except Exception:
        return []
    return results


async def free_live_web_search(
    query: str,
    *,
    max_results: int = 6,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str, list[dict]]:
    """Mencari informasi & berita terkini secara gratis tanpa kuota berbayar Google Search API.

    Menggabungkan DuckDuckGo Web + Google News RSS Indonesia (+ cadangan Wikipedia),
    lalu menyusun blok konteks siap baca untuk Gemini beserta daftar tautan sumber web.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return "", []

    async def _run_with_session(sess: aiohttp.ClientSession) -> tuple[str, list[dict]]:
        ddg_task = _search_duckduckgo_html(clean_q, sess, max_items=4)
        news_task = _search_google_news_rss(clean_q, sess, max_items=4)
        ddg_res, news_res = await asyncio.gather(ddg_task, news_task)

        combined: list[dict] = []
        seen_urls: set[str] = set()

        # Selang-seling hasil web umum & berita terbaru agar cakupan lengkap
        for bucket in (news_res, ddg_res):
            for item in bucket:
                u = item.get("url") or ""
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                combined.append(item)
                if len(combined) >= max_results:
                    break
            if len(combined) >= max_results:
                break

        if len(combined) < 2:
            wiki_res = await _search_wikipedia_api(clean_q, sess, max_items=3)
            for item in wiki_res:
                u = item.get("url") or ""
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    combined.append(item)

        if not combined:
            return "", []

        # Perkaya 1 halaman web langsung teratas (bukan redirect RSS) bila tersedia agar detail angka/fakta presisi
        top_web_excerpt = ""
        for item in ddg_res[:2]:
            candidate_url = item.get("url") or ""
            if candidate_url and is_safe_public_url(candidate_url):
                try:
                    _, body = await asyncio.wait_for(
                        fetch_webpage_text(candidate_url, http_session=sess),
                        timeout=4.5,
                    )
                    if body:
                        top_web_excerpt = (
                            f"\n\n[Kutipan Isi Halaman Teratas ({item['title']})]:\n{body[:1800]}"
                        )
                        break
                except Exception:
                    continue

        lines: list[str] = []
        sources: list[dict] = []
        for idx, item in enumerate(combined[:max_results], start=1):
            date_tag = f" ({item['date']})" if item.get("date") else ""
            snip_tag = f"\n   Ringkasan: {item['snippet']}" if item.get("snippet") else ""
            lines.append(f"{idx}. **{item['title']}**{date_tag}{snip_tag}\n   URL: {item['url']}")
            if len(sources) < 4 and item.get("url"):
                short_label = item.get("source_label") or item["title"]
                sources.append({"title": short_label[:55], "url": item["url"]})

        context_block = (
            f"Hasil Pencarian Web & Berita Terkini untuk `{clean_q}`:\n"
            + "\n".join(lines)
            + top_web_excerpt
        )
        return context_block, sources

    timeout = aiohttp.ClientTimeout(total=10, connect=5)
    if http_session is not None and not http_session.closed:
        return await _run_with_session(http_session)
    async with aiohttp.ClientSession(timeout=timeout) as temp_sess:
        return await _run_with_session(temp_sess)


def extract_message_text_for_context(message: discord.Message) -> str:
    """Mengambil gabungan teks pesan beserta isi Embed & Stiker (berguna untuk fitur tekan-tahan Context Menu)."""
    parts: list[str] = []
    if getattr(message, "content", None) and message.content.strip():
        parts.append(message.content.strip())
    for emb in getattr(message, "embeds", []) or []:
        if getattr(emb, "title", None):
            parts.append(str(emb.title).strip())
        if getattr(emb, "description", None):
            parts.append(str(emb.description).strip())
        for field in getattr(emb, "fields", []) or []:
            fname = getattr(field, "name", "")
            fval = getattr(field, "value", "")
            if fname or fval:
                parts.append(f"{fname}: {fval}".strip())
    for stk in getattr(message, "stickers", []) or []:
        sname = getattr(stk, "name", "")
        if sname:
            parts.append(f"[Stiker: {sname}]")
    return "\n\n".join(parts).strip()

