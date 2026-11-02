import asyncio
import base64
import io
import logging
import random
import time
import urllib.parse
from contextlib import asynccontextmanager
import aiohttp
import discord

from config import (
    AI_MODELS,
    ENABLE_IMAGE_FALLBACK,
    GEMINI_API_BASE,
    GEMINI_API_KEY,
    GEMINI_IMAGE_FALLBACK_CHAIN,
    GEMINI_PAID_IMAGE_ENABLED,
    GEMINI_TEXT_FALLBACK_CHAIN,
    MAX_CONCURRENT_MEDIA_TASKS,
    RATIO_OPTIONS,
    STYLE_PROMPTS,
    parse_gemini_keys,
    resolve_model_key,
)
from storage import (
    append_conversation_turn,
    get_image_settings,
    init_thread_session,
    recover_session_from_thread,
    save_sessions_to_disk,
    thread_chats,
)
from utils import get_realtime_time_context, sanitize_error_message

logger = logging.getLogger("gemini_bot.ai")

FAST_TEXT_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)
CHAT_TIMEOUT = aiohttp.ClientTimeout(total=45, connect=10)
IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=75, connect=12)
MEDIA_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_MEDIA_TASKS)

MODEL_COOLDOWN_SECONDS = 180.0
_model_cooldown_until: dict[str, float] = {}
_key_rotation_counter = 0


def get_gemini_keys_rotated() -> list[str]:
    """Mengembalikan daftar API Key Gemini dengan urutan rotasi (mendukung 1 atau banyak key)."""
    global _key_rotation_counter
    keys = parse_gemini_keys(GEMINI_API_KEY)
    if len(keys) <= 1:
        return keys
    start = _key_rotation_counter % len(keys)
    _key_rotation_counter += 1
    return keys[start:] + keys[:start]


def is_gemini_key_configured() -> bool:
    return len(parse_gemini_keys(GEMINI_API_KEY)) > 0


def mark_model_unhealthy(model_id: str, cooldown_sec: float = MODEL_COOLDOWN_SECONDS) -> None:
    """Menandai model yang sedang overload (503/timeout) agar pesan berikutnya langsung memakai model sehat."""
    _model_cooldown_until[model_id] = time.time() + cooldown_sec


def clear_model_cooldowns() -> None:
    _model_cooldown_until.clear()


def build_thinking_config(model_id: str, desired_level: str | None = "low") -> dict | None:
    """Menyusun thinkingConfig yang kompatibel agar respon Gemini 3 cepat dan tidak boros token pikiran."""
    if not desired_level:
        return None
    lower_id = (model_id or "").lower()
    if not ("gemini-3" in lower_id or "gemini-4" in lower_id):
        return None

    level = desired_level.lower()
    if level not in ("minimal", "low", "medium", "high"):
        level = "low"

    # gemini-3.8-flash, pro, dan argon minimal menggunakan 'low' ('minimal' ditolak HTTP 400)
    if level == "minimal" and any(tag in lower_id for tag in ("3.8", "pro", "argon")):
        level = "low"

    return {"thinkingLevel": level}


@asynccontextmanager
async def _borrow_session(
    shared_session: aiohttp.ClientSession | None,
    timeout: aiohttp.ClientTimeout,
):
    if shared_session is not None and not shared_session.closed:
        yield shared_session
    else:
        async with aiohttp.ClientSession(timeout=timeout) as temp_session:
            yield temp_session


def _build_model_chain(primary_model: str, fallback_list: list[str]) -> list[str]:
    """Menyusun daftar model unik dan memprioritaskan model yang tidak sedang terkena cooldown 503."""
    deduped: list[str] = []
    for model_id in [primary_model, *fallback_list]:
        cleaned = (model_id or "").strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)

    now = time.time()
    healthy = [m for m in deduped if _model_cooldown_until.get(m, 0.0) <= now]
    cooling = [m for m in deduped if _model_cooldown_until.get(m, 0.0) > now]
    return healthy + cooling


def _build_gemini_contents(
    history: list[dict],
    current_user_text: str,
    image_parts: list[dict] | None = None,
) -> list[dict]:
    """Menyusun array `contents` yang valid untuk Gemini API dengan urutan role bergantian (user/model)."""
    contents: list[dict] = []

    for item in history:
        role = "user" if item.get("role") == "user" else "model"
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].append({"text": text})
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    current_parts: list[dict] = []
    if image_parts:
        current_parts.extend(image_parts)
    current_parts.append({"text": current_user_text or "Tolong analisis lampiran ini."})

    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"].extend(current_parts)
    else:
        contents.append({"role": "user", "parts": current_parts})

    return contents


def _extract_text_from_gemini_response(data: dict) -> tuple[str | None, str | None, bool]:
    """Mengekstrak teks jawaban bersih dari JSON response Gemini (mengabaikan part 'thought' internal).
    Returns:
        (reply_text, block_or_error_reason, should_retry_next_model)
    """
    prompt_feedback = data.get("promptFeedback") or {}
    if prompt_feedback.get("blockReason"):
        reason = prompt_feedback["blockReason"]
        return (
            None,
            f"⚠️ Permintaan tidak dapat diproses karena kebijakan keamanan konten Google Gemini (`{reason}`).",
            False,
        )

    candidates = data.get("candidates") or []
    if not candidates:
        return None, "⚠️ Google Gemini tidak mengembalikan kandidat jawaban.", True

    first = candidates[0]
    finish_reason = first.get("finishReason", "")
    content_obj = first.get("content") or {}
    parts = content_obj.get("parts") or []

    # Ambil semua bagian teks yang bukan 'thought' internal Gemini 3
    visible_texts = [
        p["text"]
        for p in parts
        if isinstance(p.get("text"), str) and not p.get("thought", False)
    ]

    combined = "".join(visible_texts).strip()
    if combined:
        return combined, None, False

    if finish_reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"}:
        return (
            None,
            f"⚠️ Jawaban dibatasi oleh filter keamanan Google Gemini (`{finish_reason}`). "
            "Coba ubah kalimat pertanyaan Anda.",
            False,
        )

    # Jika habis di token thinking (MAX_TOKENS tanpa teks terlihat), coba model lebih ringan berikutnya
    return None, f"⚠️ Respons Gemini kosong (status akhir: `{finish_reason or 'UNKNOWN'}`).", True


async def get_ai_response(
    thread_id: int,
    prompt: str,
    *,
    image_parts: list[dict] | None = None,
    image_filenames: list[str] | None = None,
    text_blocks: list[str] | None = None,
    http_session: aiohttp.ClientSession | None = None,
    thread: discord.Thread | None = None,
    bot_user_id: int | None = None,
) -> str:
    """Mendapatkan balasan percakapan (Teks + Vision + File Kode) dari Google Gemini API."""
    if not is_gemini_key_configured():
        return (
            "⚠️ **`GEMINI_API_KEY` belum dikonfigurasi!**\n"
            "Pastikan admin sudah mengisi `GEMINI_API_KEY` pada file `.env` atau tab Variables di Wispbyte."
        )

    session_data = thread_chats.get(thread_id)
    if session_data is None:
        if thread is not None and bot_user_id is not None:
            session_data = await recover_session_from_thread(thread, bot_user_id)
        else:
            session_data = init_thread_session(thread_id, "gemini_flash")

    model_key = resolve_model_key(session_data.get("model_key"))
    model_info = AI_MODELS[model_key]

    prompt_sections: list[str] = []
    if prompt.strip():
        prompt_sections.append(prompt.strip())
    if text_blocks:
        prompt_sections.extend(text_blocks)
    if not prompt_sections and image_parts:
        prompt_sections.append("Tolong jelaskan dan analisis gambar yang saya lampirkan ini.")

    effective_prompt = "\n\n".join(prompt_sections).strip()

    history_note_parts: list[str] = []
    if image_filenames:
        files_label = ", ".join(image_filenames)
        history_note_parts.append(f"[Pengguna melampirkan gambar: {files_label}]")
    if effective_prompt:
        history_note_parts.append(effective_prompt)
    history_user_entry = "\n".join(history_note_parts).strip()

    contents = _build_gemini_contents(
        session_data.get("history", []),
        effective_prompt,
        image_parts=image_parts,
    )

    time_ctx = get_realtime_time_context()
    system_text = (
        f"{model_info['system_prompt']}\n"
        f"[Informasi Waktu Saat Ini: {time_ctx['summary']}]"
    )

    desired_thinking = model_info.get("thinking_level", "low")
    req_timeout = CHAT_TIMEOUT if image_parts else FAST_TEXT_TIMEOUT
    active_keys = get_gemini_keys_rotated()
    models_to_try = _build_model_chain(model_info["model_id"], GEMINI_TEXT_FALLBACK_CHAIN)
    last_error_msg = "Tidak dapat terhubung ke layanan Google Gemini."

    async with _borrow_session(http_session, req_timeout) as session:
        for attempt_idx, candidate_model in enumerate(models_to_try):
            gen_config: dict = {
                "temperature": model_info.get("temperature", 0.7),
                "maxOutputTokens": 8192,
            }
            thinking_cfg = build_thinking_config(candidate_model, desired_thinking)
            if thinking_cfg:
                gen_config["thinkingConfig"] = thinking_cfg

            payload = {
                "systemInstruction": {"parts": [{"text": system_text}]},
                "contents": contents,
                "generationConfig": gen_config,
            }

            api_key_for_attempt = active_keys[attempt_idx % len(active_keys)]
            headers = {
                "x-goog-api-key": api_key_for_attempt,
                "Content-Type": "application/json",
            }
            url = f"{GEMINI_API_BASE}/{candidate_model}:generateContent"

            try:
                async with session.post(url, headers=headers, json=payload, timeout=req_timeout) as resp:
                    data = await resp.json(content_type=None)

                    if resp.status == 200 and isinstance(data, dict):
                        reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            append_conversation_turn(thread_id, history_user_entry, reply_text)
                            await save_sessions_to_disk()
                            return reply_text
                        if block_msg and not should_retry:
                            return block_msg
                        last_error_msg = block_msg or "Respons kosong dari model."
                        continue

                    err_detail = ""
                    if isinstance(data, dict) and isinstance(data.get("error"), dict):
                        err_detail = data["error"].get("message") or str(data["error"].get("status") or "")
                    else:
                        err_detail = str(data)[:200]

                    err_detail = sanitize_error_message(err_detail)

                    if resp.status in (400, 401, 403) and "api key" in err_detail.lower() and len(active_keys) == 1:
                        return (
                            f"⚠️ **API Key Gemini tidak valid ({resp.status}):** {err_detail}\n"
                            "Periksa kembali `GEMINI_API_KEY` Anda di Google AI Studio."
                        )

                    if resp.status in (429, 500, 502, 503, 504, 404):
                        mark_model_unhealthy(candidate_model)

                    last_error_msg = f"HTTP {resp.status} pada `{candidate_model}`: {err_detail}"
                    logger.warning("Gemini model %s gagal (%s). Pindah instan ke cadangan...", candidate_model, last_error_msg)

            except asyncio.TimeoutError:
                mark_model_unhealthy(candidate_model)
                last_error_msg = f"Waktu tunggu habis pada `{candidate_model}`."
                logger.warning("%s Pindah instan ke cadangan...", last_error_msg)
            except Exception as exc:
                last_error_msg = f"Gangguan jaringan: {sanitize_error_message(exc)}"
                logger.warning("Exception pada Gemini (%s): %s", candidate_model, last_error_msg)

    return (
        "⚠️ **Maaf, server Google Gemini sedang sangat padat saat ini.**\n"
        f"Detail: `{last_error_msg}`\n"
        "*Silakan tunggu beberapa detik lalu kirim ulang pesan Anda.*"
    )


def _mime_to_extension(mime_type: str) -> str:
    mime = (mime_type or "").lower()
    if "jpeg" in mime or "jpg" in mime:
        return "jpg"
    if "webp" in mime:
        return "webp"
    return "png"


async def generate_image(
    thread_id: int,
    prompt: str,
    *,
    reference_images: list[dict] | None = None,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, discord.File | None, str | None]:
    """Menghasilkan (atau mengedit) gambar.
    - Jika `GEMINI_PAID_IMAGE_ENABLED=true` (atau pengguna mengedit lampiran gambar), memakai Gemini Nano Banana.
    - Jika memakai Free Tier (`GEMINI_PAID_IMAGE_ENABLED=false`), langsung membuat gambar via Flux gratis tanpa jeda!

    Returns:
        (engine_label, discord_file, error_message)
    """
    settings = get_image_settings(thread_id)
    style_name = settings["style"]
    ratio_name = settings["ratio"]

    style_suffix = STYLE_PROMPTS.get(style_name, "")
    ratio_meta = RATIO_OPTIONS.get(ratio_name, RATIO_OPTIONS["1:1 (Persegi)"])
    aspect_ratio = ratio_meta["aspect_ratio"]
    width, height = ratio_meta["dimensions"]

    clean_prompt = prompt.strip() or "Create a visually stunning illustration"
    full_prompt = f"{clean_prompt}{style_suffix}"

    gemini_errors: list[str] = []
    should_try_gemini_image = GEMINI_PAID_IMAGE_ENABLED or bool(reference_images)

    async with MEDIA_SEMAPHORE:
        async with _borrow_session(http_session, IMAGE_TIMEOUT) as session:
            # 1. GOOGLE GEMINI NATIVE IMAGE GENERATION (Aktif jika Paid Tier atau Edit Gambar)
            active_keys = get_gemini_keys_rotated()
            if should_try_gemini_image and active_keys:
                request_parts: list[dict] = []
                if reference_images:
                    request_parts.extend(reference_images)
                request_parts.append({"text": full_prompt})

                payload = {
                    "contents": [{"parts": request_parts}],
                    "generationConfig": {
                        "responseModalities": ["TEXT", "IMAGE"],
                        "imageConfig": {
                            "aspectRatio": aspect_ratio,
                        },
                    },
                }

                models_list = _build_model_chain(GEMINI_IMAGE_FALLBACK_CHAIN[0], GEMINI_IMAGE_FALLBACK_CHAIN)
                # Jika hanya mencoba edit gambar pada Free Tier, cukup tes 1 model agar tidak lambat
                if not GEMINI_PAID_IMAGE_ENABLED:
                    models_list = models_list[:1]

                for k_idx, img_model in enumerate(models_list):
                    headers = {
                        "x-goog-api-key": active_keys[k_idx % len(active_keys)],
                        "Content-Type": "application/json",
                    }
                    url = f"{GEMINI_API_BASE}/{img_model}:generateContent"
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=IMAGE_TIMEOUT) as resp:
                            data = await resp.json(content_type=None)
                            if resp.status == 200 and isinstance(data, dict):
                                candidates = data.get("candidates") or []
                                if candidates:
                                    parts = (candidates[0].get("content") or {}).get("parts") or []
                                    for part in parts:
                                        inline = part.get("inlineData") or part.get("inline_data")
                                        if isinstance(inline, dict) and inline.get("data"):
                                            img_bytes = base64.b64decode(inline["data"])
                                            ext = _mime_to_extension(inline.get("mimeType") or inline.get("mime_type") or "")
                                            file_obj = discord.File(
                                                io.BytesIO(img_bytes),
                                                filename=f"gemini_generated.{ext}",
                                            )
                                            return f"Google Gemini ({img_model})", file_obj, None

                            err_msg = ""
                            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                                err_msg = data["error"].get("message") or str(resp.status)
                            else:
                                err_msg = f"HTTP {resp.status}"
                            gemini_errors.append(f"{img_model}: {sanitize_error_message(err_msg)}")
                    except Exception as exc:
                        gemini_errors.append(f"{img_model}: {sanitize_error_message(exc)}")

            # 2. GENERATOR GAMBAR GRATIS (Langsung dieksekusi di Free Tier tanpa menunggu error!)
            if ENABLE_IMAGE_FALLBACK and not reference_images:
                seed = random.randint(1, 999_999_999)
                encoded = urllib.parse.quote(full_prompt)
                fallback_url = (
                    f"https://image.pollinations.ai/prompt/{encoded}"
                    f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux"
                )
                try:
                    async with session.get(fallback_url, timeout=IMAGE_TIMEOUT) as resp:
                        content_type = (resp.headers.get("Content-Type") or "").lower()
                        if resp.status == 200 and content_type.startswith("image/"):
                            img_bytes = await resp.read()
                            if len(img_bytes) > 1024:
                                ext = _mime_to_extension(content_type)
                                file_obj = discord.File(
                                    io.BytesIO(img_bytes),
                                    filename=f"generated.{ext}",
                                )
                                return "Flux AI (Free Tier)", file_obj, None
                        gemini_errors.append(f"Flux HTTP {resp.status}")
                except Exception as exc:
                    gemini_errors.append(f"Flux: {sanitize_error_message(exc)}")

    if reference_images and not GEMINI_PAID_IMAGE_ENABLED:
        return (
            None,
            None,
            "Fitur Edit Gambar lampiran membutuhkan akun Gemini Paid Tier (`GEMINI_PAID_IMAGE_ENABLED=true`). "
            "Untuk Free Tier, ketik langsung deskripsi teks gambar yang ingin dibuat.",
        )

    detail = "; ".join(gemini_errors) or "Gagal mengunduh gambar dari server AI."
    return None, None, detail
