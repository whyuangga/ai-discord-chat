import asyncio
import base64
import io
import logging
import random
import re
import time
import urllib.parse
from contextlib import asynccontextmanager
import aiohttp
import discord

from config import (
    AI_MODELS,
    BOT_TIMEZONE,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_IMAGE_FALLBACK,
    ENABLE_URL_READER,
    GEMINI_API_BASE,
    GEMINI_API_KEY,
    GEMINI_DEFAULT_MODEL,
    GEMINI_FAST_MODEL,
    GEMINI_IMAGE_FALLBACK_CHAIN,
    GEMINI_PAID_IMAGE_ENABLED,
    GEMINI_PAID_SEARCH_ENABLED,
    GEMINI_SEARCH_FALLBACK_CHAIN,
    GEMINI_SEARCH_MODEL,
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
from utils import (
    build_clean_search_query,
    extract_urls_from_text,
    fetch_webpage_text,
    free_live_web_search,
    get_realtime_time_context,
    needs_live_web_search,
    sanitize_error_message,
)

logger = logging.getLogger("gemini_bot.ai")

FAST_TEXT_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)
CHAT_TIMEOUT = aiohttp.ClientTimeout(total=45, connect=10)
VIDEO_LINK_TIMEOUT = aiohttp.ClientTimeout(total=65, connect=10)
IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=75, connect=12)
MEDIA_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_MEDIA_TASKS)

MODEL_COOLDOWN_SECONDS = 180.0
_model_cooldown_until: dict[str, float] = {}
_key_rotation_counter = 0
_paid_google_search_available = True


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
    global _paid_google_search_available
    _model_cooldown_until.clear()
    _paid_google_search_available = True


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


def _extract_grounding_sources(data: dict, max_sources: int = 4) -> list[tuple[str, str]]:
    """Mengekstrak daftar sumber web unik (judul, url) dari groundingMetadata Google Search."""
    candidates = data.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return []

    first = candidates[0]
    meta = first.get("groundingMetadata") or first.get("grounding_metadata") or {}
    chunks = meta.get("groundingChunks") or meta.get("grounding_chunks") or []

    sources: list[tuple[str, str]] = []
    seen_uris: set[str] = set()
    for ch in chunks:
        if not isinstance(ch, dict):
            continue
        web = ch.get("web") or {}
        uri = str(web.get("uri") or "").strip()
        title = str(web.get("title") or "").strip()
        if not uri or uri in seen_uris:
            continue
        seen_uris.add(uri)
        if not title:
            title = urllib.parse.urlparse(uri).hostname or "Sumber Web"
        sources.append((title[:48], uri))
        if len(sources) >= max_sources:
            break
    return sources


def _format_grounding_footer(sources: list[tuple[str, str] | dict]) -> str:
    if not sources:
        return ""
    links: list[str] = []
    for idx, item in enumerate(sources):
        if isinstance(item, dict):
            title = str(item.get("title") or "Sumber Web").strip()
            uri = str(item.get("url") or item.get("uri") or "").strip()
        else:
            title, uri = item
        if uri:
            links.append(f"[{idx + 1}. {title}](<{uri}>)")
    if not links:
        return ""
    return "\n\n🌐 **Sumber Web:** " + " • ".join(links)


async def get_ai_response(
    thread_id: int,
    prompt: str,
    *,
    image_parts: list[dict] | None = None,
    image_filenames: list[str] | None = None,
    text_blocks: list[str] | None = None,
    allow_url_reader: bool | None = None,
    allow_web_search: bool | None = None,
    http_session: aiohttp.ClientSession | None = None,
    thread: discord.Thread | None = None,
    bot_user_id: int | None = None,
    server_knowledge: str = "",
) -> str:
    """Mendapatkan balasan percakapan (Teks + Vision + Audio + PDF + YouTube/Web + Live Search) dari Google Gemini API."""
    global _paid_google_search_available
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

    url_reader_on = ENABLE_URL_READER if allow_url_reader is None else bool(allow_url_reader)
    web_search_on = ENABLE_GOOGLE_SEARCH if allow_web_search is None else bool(allow_web_search)

    combined_media_parts: list[dict] = list(image_parts or [])
    yt_urls: list[str] = []
    web_urls: list[str] = []
    unfetched_web_urls: list[str] = []

    if url_reader_on and prompt.strip():
        yt_urls, web_urls = extract_urls_from_text(prompt)

    for yt_url in yt_urls:
        combined_media_parts.append({"fileData": {"fileUri": yt_url}})

    fetched_web_blocks: list[str] = []
    for w_url in web_urls:
        w_title, w_body = await fetch_webpage_text(w_url, http_session=http_session)
        if w_body:
            heading = f"{w_title} ({w_url})" if w_title else w_url
            fetched_web_blocks.append(f"🌐 **Isi Halaman Web `{heading}`:**\n{w_body}")
        else:
            unfetched_web_urls.append(w_url)

    prompt_sections: list[str] = []
    stripped_prompt = prompt.strip()
    # Jika pengguna hanya menempelkan link YouTube tanpa instruksi tambahan, beri instruksi rangkuman otomatis
    only_yt_link = bool(yt_urls) and not re.sub(r"https?://\S+", "", stripped_prompt).strip()
    only_web_link = bool(web_urls) and not yt_urls and not re.sub(r"https?://\S+", "", stripped_prompt).strip()

    if only_yt_link:
        prompt_sections.append(
            f"{stripped_prompt}\nTolong tonton/pahami isi video YouTube di atas lalu buat rangkuman lengkap "
            "poin-poin utamanya dalam bahasa Indonesia yang rapi dan mudah dipahami."
        )
    elif only_web_link:
        prompt_sections.append(
            f"{stripped_prompt}\nTolong baca dan rangkumkan inti pembahasan dari halaman web di atas dalam bahasa Indonesia."
        )
    elif stripped_prompt:
        prompt_sections.append(stripped_prompt)

    if text_blocks:
        prompt_sections.extend(text_blocks)
    if fetched_web_blocks:
        prompt_sections.extend(fetched_web_blocks)

    has_audio_only = bool(image_filenames) and all(
        fn.startswith(("voice_note:", "audio:")) for fn in image_filenames
    )
    has_pdf_only = bool(image_filenames) and all(
        fn.startswith("pdf:") for fn in image_filenames
    )
    if not prompt_sections and combined_media_parts:
        if has_audio_only:
            prompt_sections.append(
                "Dengarkan pesan suara (voice note) atau audio yang saya kirim ini dengan saksama, "
                "lalu jawab atau tanggapi langsung isi ucapannya secara jelas, ramah, dan relevan."
            )
        elif has_pdf_only:
            prompt_sections.append(
                "Baca dokumen PDF yang saya lampirkan ini dengan saksama, lalu berikan ringkasan terstruktur "
                "poin-poin utamanya dalam bahasa Indonesia yang jelas."
            )
        else:
            prompt_sections.append("Tolong jelaskan dan analisis lampiran media/gambar yang saya kirim ini.")

    effective_prompt = "\n\n".join(prompt_sections).strip()

    history_note_parts: list[str] = []
    if image_filenames:
        files_label = ", ".join(image_filenames)
        if has_audio_only:
            media_tag = "pesan suara/audio"
        elif has_pdf_only:
            media_tag = "dokumen PDF"
        else:
            media_tag = "gambar"
        history_note_parts.append(f"[Pengguna melampirkan {media_tag}: {files_label}]")
    if yt_urls:
        history_note_parts.append(f"[Video YouTube: {', '.join(yt_urls)}]")
    if stripped_prompt:
        history_note_parts.append(stripped_prompt)
    elif effective_prompt and not fetched_web_blocks:
        history_note_parts.append(effective_prompt)
    history_user_entry = "\n".join(history_note_parts).strip()

    contents = _build_gemini_contents(
        session_data.get("history", []),
        effective_prompt,
        image_parts=combined_media_parts or None,
    )

    time_ctx = get_realtime_time_context()
    knowledge_section = f"\n\n{server_knowledge.strip()}" if server_knowledge and server_knowledge.strip() else ""
    system_text = (
        f"{model_info['system_prompt']}\n"
        f"[Informasi Waktu Saat Ini: {time_ctx['summary']}]"
        f"{knowledge_section}"
    )

    desired_thinking = model_info.get("thinking_level", "low")
    wants_live_search = (
        web_search_on
        and not combined_media_parts
        and not fetched_web_blocks
        and needs_live_web_search(stripped_prompt)
    )
    use_paid_search_tool = wants_live_search and GEMINI_PAID_SEARCH_ENABLED and _paid_google_search_available
    use_url_context_tool = bool(unfetched_web_urls) and not combined_media_parts and GEMINI_PAID_SEARCH_ENABLED

    req_timeout = (
        VIDEO_LINK_TIMEOUT
        if yt_urls
        else (CHAT_TIMEOUT if (combined_media_parts or wants_live_search or use_url_context_tool) else FAST_TEXT_TIMEOUT)
    )
    active_keys = get_gemini_keys_rotated()
    last_error_msg = "Tidak dapat terhubung ke layanan Google Gemini."
    free_search_sources: list[dict] = []

    async with _borrow_session(http_session, req_timeout) as session:
        # JALUR OPSIONAL PAID TIER: Native Google Search Grounding (hanya jika GEMINI_PAID_SEARCH_ENABLED=true)
        if use_paid_search_tool or use_url_context_tool:
            grounded_models = _build_model_chain(GEMINI_SEARCH_MODEL, GEMINI_SEARCH_FALLBACK_CHAIN)
            tools_list: list[dict] = []
            if use_url_context_tool:
                tools_list.append({"url_context": {}})
            if use_paid_search_tool:
                tools_list.append({"google_search": {}})

            for s_idx, s_model in enumerate(grounded_models):
                s_gen_cfg: dict = {"temperature": 0.5, "maxOutputTokens": 4096}
                s_think = build_thinking_config(s_model, "low")
                if s_think:
                    s_gen_cfg["thinkingConfig"] = s_think

                s_payload = {
                    "systemInstruction": {"parts": [{"text": system_text}]},
                    "contents": contents,
                    "tools": tools_list,
                    "generationConfig": s_gen_cfg,
                }
                s_key = active_keys[s_idx % len(active_keys)]
                s_headers = {"x-goog-api-key": s_key, "Content-Type": "application/json"}
                s_url = f"{GEMINI_API_BASE}/{s_model}:generateContent"

                try:
                    async with session.post(s_url, headers=s_headers, json=s_payload, timeout=CHAT_TIMEOUT) as resp:
                        data = await resp.json(content_type=None)
                        if resp.status == 200 and isinstance(data, dict):
                            reply_text, _, _ = _extract_text_from_gemini_response(data)
                            if reply_text:
                                sources = _extract_grounding_sources(data)
                                final_reply = f"{reply_text}{_format_grounding_footer(sources)}"
                                append_conversation_turn(thread_id, history_user_entry, final_reply)
                                await save_sessions_to_disk()
                                return final_reply
                        elif resp.status == 429 and isinstance(data, dict):
                            raw_err = str((data.get("error") or {}).get("message") or "").lower()
                            if "exceeded your current quota" in raw_err or "billing" in raw_err:
                                _paid_google_search_available = False
                                break
                except (asyncio.TimeoutError, aiohttp.ClientError):
                    continue
                except Exception:
                    continue

        # JALUR FREE TIER MANDIRI: Ambil hasil pencarian web & berita terkini secara gratis tanpa tool berbayar
        if wants_live_search:
            free_ctx, free_search_sources = await free_live_web_search(
                build_clean_search_query(stripped_prompt),
                http_session=session,
            )
            if free_ctx:
                enriched_prompt = (
                    f"{effective_prompt}\n\n"
                    f"[DATA PENCARIAN WEB & BERITA REAL-TIME HARI INI]:\n{free_ctx}\n\n"
                    "Gunakan data pencarian terbaru di atas untuk menjawab secara akurat dan sebutkan fakta terbarunya."
                )
                contents = _build_gemini_contents(
                    session_data.get("history", []),
                    enriched_prompt,
                    image_parts=combined_media_parts or None,
                )

        # JALUR UTAMA: Model Percakapan Standar (+ Vision / Audio / YouTube / Konteks Web Gratis)
        models_to_try = _build_model_chain(model_info["model_id"], GEMINI_TEXT_FALLBACK_CHAIN)
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
                            if free_search_sources:
                                reply_text = f"{reply_text}{_format_grounding_footer(free_search_sources)}"
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

                    # Jika gagal karena video YouTube privat / tidak bisa diakses oleh fileData, lepaskan fileData di percobaan berikutnya
                    if resp.status in (400, 403) and yt_urls:
                        contents = _build_gemini_contents(
                            session_data.get("history", []),
                            effective_prompt,
                            image_parts=image_parts,
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


async def summarize_channel_messages(
    messages_log: list[str],
    channel_name: str,
    *,
    timezone_name: str = BOT_TIMEZONE,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Merangkum daftar riwayat obrolan channel menjadi ringkasan TL;DR berbahasa Indonesia yang rapi.

    Returns:
        (summary_text, error_message)
    """
    if not is_gemini_key_configured():
        return None, "⚠️ `GEMINI_API_KEY` belum dikonfigurasi oleh Admin."

    if not messages_log:
        return None, "Belum ada percakapan teks yang cukup di channel ini untuk dirangkum."

    time_ctx = get_realtime_time_context(timezone_name)
    system_prompt = (
        "Kamu adalah perangkum obrolan komunitas Discord yang cerdas, ringkas, asik, dan akurat.\n"
        f"Waktu saat ini: {time_ctx['summary']}.\n\n"
        "TUGASMU:\n"
        "Buat ringkasan cepat (TL;DR) dalam bahasa Indonesia yang santai namun rapi agar member yang baru buka HP "
        "langsung paham apa saja yang barusan dibahas warga tanpa harus scroll panjang.\n"
        "Gunakan struktur singkat berikut:\n"
        "**📌 Topik Utama yang Dibahas**\n"
        "- Sebutkan 2–5 poin inti obrolan beserta nama member yang membahasnya.\n\n"
        "**🔥 Info / Momen Penting**\n"
        "- Sebutkan jika ada ajakan mabar, kesepakatan, pengumuman, link/karya menarik, atau pertanyaan yang belum terjawab "
        "(jika tidak ada yang khusus, tulis singkat suasana obrolannya)."
    )

    joined_transcript = "\n".join(messages_log)[-24000:]
    user_prompt = (
        f"Berikut adalah {len(messages_log)} pesan terakhir di channel #{channel_name}:\n\n"
        f"{joined_transcript}\n\n"
        "Rangkumkan isi obrolan di atas sekarang!"
    )

    active_keys = get_gemini_keys_rotated()
    models_to_try = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
    last_err = "Server Gemini sedang sibuk, coba beberapa saat lagi."

    async with _borrow_session(http_session, FAST_TEXT_TIMEOUT) as session:
        for idx, model_id in enumerate(models_to_try):
            gen_config: dict = {"temperature": 0.4, "maxOutputTokens": 2048}
            t_cfg = build_thinking_config(model_id, "low")
            if t_cfg:
                gen_config["thinkingConfig"] = t_cfg

            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": gen_config,
            }
            api_key = active_keys[idx % len(active_keys)]
            url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

            try:
                async with session.post(url, headers=headers, json=payload, timeout=FAST_TEXT_TIMEOUT) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200:
                        reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            return reply_text, None
                        if not should_retry and block_msg:
                            return None, block_msg
                        continue

                    if resp.status in (500, 502, 503, 504):
                        mark_model_unhealthy(model_id)
                        continue
                    if resp.status == 429:
                        continue
                    err_detail = (
                        data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if isinstance(data, dict)
                        else f"HTTP {resp.status}"
                    )
                    last_err = sanitize_error_message(err_detail)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                mark_model_unhealthy(model_id)
                continue

    return None, f"⚠️ Gagal merangkum obrolan: {last_err}"


async def search_web_with_gemini(
    query: str,
    *,
    timezone_name: str = BOT_TIMEZONE,
    include_sources_footer: bool = True,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Mencari informasi/berita terbaru secara real-time (100% ramah Free Tier dengan pencari web mandiri + Gemini)."""
    global _paid_google_search_available
    if not is_gemini_key_configured():
        return None, "⚠️ `GEMINI_API_KEY` belum dikonfigurasi oleh Admin."

    time_ctx = get_realtime_time_context(timezone_name)
    system_prompt = (
        "Kamu adalah asisten pencari informasi terkini berbasis Google Gemini.\n"
        f"Waktu saat ini: {time_ctx['summary']}.\n"
        "Jawablah dalam bahasa Indonesia yang akurat, padat, rapi, dan langsung menyebutkan fakta/tanggal terbaru "
        "berdasarkan hasil pencarian web & berita yang diberikan."
    )

    active_keys = get_gemini_keys_rotated()
    last_err = "Layanan pencarian sedang sibuk, silakan coba beberapa detik lagi."

    async with _borrow_session(http_session, CHAT_TIMEOUT) as session:
        # 1. Opsional Paid Tier: Gunakan tool google_search bawaan hanya bila GEMINI_PAID_SEARCH_ENABLED=true
        if GEMINI_PAID_SEARCH_ENABLED and _paid_google_search_available:
            paid_models = _build_model_chain(GEMINI_SEARCH_MODEL, GEMINI_SEARCH_FALLBACK_CHAIN)
            for idx, model_id in enumerate(paid_models):
                gen_config: dict = {"temperature": 0.3, "maxOutputTokens": 4096}
                t_cfg = build_thinking_config(model_id, "low")
                if t_cfg:
                    gen_config["thinkingConfig"] = t_cfg

                payload = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": query}]}],
                    "tools": [{"google_search": {}}],
                    "generationConfig": gen_config,
                }
                api_key = active_keys[idx % len(active_keys)]
                url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
                headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

                try:
                    async with session.post(url, headers=headers, json=payload, timeout=CHAT_TIMEOUT) as resp:
                        data = await resp.json(content_type=None)
                        if resp.status == 200 and isinstance(data, dict):
                            reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                            if reply_text:
                                if include_sources_footer:
                                    sources = _extract_grounding_sources(data)
                                    footer = _format_grounding_footer(sources)
                                    max_body = max(500, 3850 - len(footer))
                                    clipped = reply_text[:max_body] + ("…" if len(reply_text) > max_body else "")
                                    reply_text = f"{clipped}{footer}"
                                return reply_text, None
                            if block_msg and not should_retry:
                                return None, block_msg
                            continue

                        if resp.status == 429 and isinstance(data, dict):
                            raw_msg = str((data.get("error") or {}).get("message") or "").lower()
                            if "exceeded your current quota" in raw_msg or "billing" in raw_msg:
                                _paid_google_search_available = False
                                break
                        if resp.status in (500, 502, 503, 504):
                            mark_model_unhealthy(model_id)
                except (asyncio.TimeoutError, aiohttp.ClientError):
                    mark_model_unhealthy(model_id)
                    continue

        # 2. Jalur Utama Free Tier: Ambil hasil pencarian web & berita real-time gratis (DuckDuckGo + Google News RSS)
        live_ctx, live_sources = await free_live_web_search(query, http_session=session)
        if live_ctx:
            user_prompt = (
                f"Pertanyaan Pengguna: {query}\n\n"
                f"{live_ctx}\n\n"
                "Berdasarkan hasil pencarian web & berita terbaru di atas, berikan jawaban yang akurat, "
                "jelas, dan terstruktur dalam bahasa Indonesia!"
            )
        else:
            user_prompt = (
                f"Pertanyaan Pengguna: {query}\n\n"
                "Jawablah pertanyaan di atas secara informatif dan jujur dalam bahasa Indonesia."
            )

        text_models = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
        # Tambahkan jeda ulang singkat bila seluruh model terkena lonjakan batas RPM sesaat
        all_candidates = [*text_models, f"__retry__:{GEMINI_FAST_MODEL}"]

        for idx, raw_model in enumerate(all_candidates):
            if raw_model.startswith("__retry__:"):
                await asyncio.sleep(1.5)
                model_id = raw_model.split(":", 1)[1]
            else:
                model_id = raw_model

            gen_config = {"temperature": 0.35, "maxOutputTokens": 3072}
            t_cfg = build_thinking_config(model_id, "low")
            if t_cfg:
                gen_config["thinkingConfig"] = t_cfg
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": gen_config,
            }
            api_key = active_keys[idx % len(active_keys)]
            url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            try:
                async with session.post(url, headers=headers, json=payload, timeout=FAST_TEXT_TIMEOUT) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            if include_sources_footer and live_sources:
                                footer = _format_grounding_footer(live_sources)
                                max_body = max(500, 3850 - len(footer))
                                clipped = reply_text[:max_body] + ("…" if len(reply_text) > max_body else "")
                                reply_text = f"{clipped}{footer}"
                            elif not live_ctx:
                                reply_text += (
                                    "\n\n*(Catatan: Pencarian berita eksternal sedang tidak terjangkau — "
                                    "dijawab berdasarkan pengetahuan model)*"
                                )
                            return reply_text, None
                        if block_msg and not should_retry:
                            return None, block_msg
                        continue

                    if resp.status in (500, 502, 503, 504):
                        mark_model_unhealthy(model_id)
                    err_detail = (
                        data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if isinstance(data, dict)
                        else f"HTTP {resp.status}"
                    )
                    last_err = sanitize_error_message(err_detail)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                mark_model_unhealthy(model_id)
                continue

    return None, f"⚠️ Gagal mencari informasi: {last_err}"


async def analyze_link_with_gemini(
    raw_url: str,
    question: str | None = "",
    *,
    timezone_name: str = BOT_TIMEZONE,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Merangkum atau menjawab pertanyaan seputar link video YouTube maupun artikel halaman web."""
    if not is_gemini_key_configured():
        return None, "⚠️ `GEMINI_API_KEY` belum dikonfigurasi oleh Admin."

    q_clean = (question or "").strip()
    yt_urls, web_urls = extract_urls_from_text(raw_url, include_ignored_domains=False)
    if not yt_urls and not web_urls:
        return None, "⚠️ Link tidak valid atau mengarah ke jaringan lokal/internal yang dibatasi."

    parts: list[dict] = []
    use_url_context = False
    target_label = yt_urls[0] if yt_urls else web_urls[0]

    if yt_urls:
        parts.append({"fileData": {"fileUri": yt_urls[0]}})
        user_task = q_clean or (
            "Rangkumkan isi video YouTube ini secara terstruktur (Topik Utama, Poin-Poin Penting, & Kesimpulan) "
            "dalam bahasa Indonesia yang jelas!"
        )
        parts.append({"text": f"URL Video YouTube: {yt_urls[0]}\nInstruksi: {user_task}"})
    else:
        w_title, w_body = await fetch_webpage_text(web_urls[0], http_session=http_session)
        user_task = q_clean or (
            "Rangkumkan inti pembahasan halaman web ini secara rapi dan padat dalam bahasa Indonesia!"
        )
        if w_body:
            heading = f"{w_title} ({web_urls[0]})" if w_title else web_urls[0]
            parts.append({"text": f"Halaman Web: {heading}\n\nIsi Teks Halaman:\n{w_body}\n\nInstruksi: {user_task}"})
        else:
            use_url_context = True
            parts.append({"text": f"Buka dan baca URL ini: {web_urls[0]}\nInstruksi: {user_task}"})

    time_ctx = get_realtime_time_context(timezone_name)
    system_prompt = (
        "Kamu adalah asisten perangkum konten video YouTube dan artikel web berbahasa Indonesia yang tajam, "
        f"akurat, rapi, dan mudah dipahami. Waktu saat ini: {time_ctx['summary']}."
    )

    active_keys = get_gemini_keys_rotated()
    chain = (
        _build_model_chain(GEMINI_SEARCH_MODEL, GEMINI_SEARCH_FALLBACK_CHAIN)
        if use_url_context
        else _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
    )
    last_err = f"Tidak dapat memproses link `{target_label}`."

    req_link_timeout = VIDEO_LINK_TIMEOUT if yt_urls else CHAT_TIMEOUT
    async with _borrow_session(http_session, req_link_timeout) as session:
        for idx, model_id in enumerate(chain):
            gen_config: dict = {"temperature": 0.4, "maxOutputTokens": 4096}
            t_cfg = build_thinking_config(model_id, "low")
            if t_cfg:
                gen_config["thinkingConfig"] = t_cfg

            payload: dict = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen_config,
            }
            if use_url_context:
                payload["tools"] = [{"url_context": {}}]

            api_key = active_keys[idx % len(active_keys)]
            url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

            try:
                async with session.post(url, headers=headers, json=payload, timeout=req_link_timeout) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            return reply_text, None
                        if block_msg and not should_retry:
                            return None, block_msg
                        continue

                    err_detail = (
                        data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if isinstance(data, dict)
                        else f"HTTP {resp.status}"
                    )
                    last_err = sanitize_error_message(err_detail)
                    # Video YouTube privat / dibatasi usia akan ditolak 400/403 di semua model -> beri pesan jelas langsung
                    if yt_urls and resp.status in (400, 403) and "api key" not in last_err.lower():
                        return (
                            None,
                            "⚠️ Video YouTube tersebut bersifat **privat**, **dibatasi usia/wilayah**, atau tidak dapat diakses publik.",
                        )
                    if resp.status in (500, 502, 503, 504):
                        mark_model_unhealthy(model_id)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                mark_model_unhealthy(model_id)
                continue

    return None, f"⚠️ Gagal menganalisis link: {last_err}"


async def transform_message_with_gemini(
    mode: str,
    message_text: str,
    *,
    media_parts: list[dict] | None = None,
    text_blocks: list[str] | None = None,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Memproses aksi cepat Context Menu (Terjemahkan ke Indonesia / Jelaskan Pesan Ini)."""
    if not is_gemini_key_configured():
        return None, "⚠️ `GEMINI_API_KEY` belum dikonfigurasi oleh Admin."

    combined_text_parts = [p for p in [message_text.strip(), *(text_blocks or [])] if p]
    full_text = "\n\n".join(combined_text_parts).strip()

    if not full_text and not media_parts:
        return None, "⚠️ Pesan tersebut kosong dan tidak memiliki gambar/suara/teks yang bisa diproses."

    if mode == "translate_id":
        system_prompt = (
            "Kamu adalah penerjemah bahasa profesional ke Bahasa Indonesia yang akurat dan luwes.\n"
            "TUGASMU:\n"
            "1. Terjemahkan seluruh teks pesan (atau ucapan suara / tulisan di dalam gambar terlampir) ke Bahasa Indonesia yang alami dan mudah dipahami.\n"
            "2. Pertahankan format Markdown atau blok kode seperti aslinya (jangan menerjemahkan sintaks kode program, cukup komentarnya saja).\n"
            "3. Sebutkan singkat bahasa aslinya di baris paling atas (contoh: `🌐 Bahasa Asal: Inggris`), dan jika ada istilah gaul/idiom unik, beri catatan arti singkat di bawahnya."
        )
        user_prompt = full_text or "Terjemahkan isi tulisan pada gambar atau ucapan pada pesan suara ini ke Bahasa Indonesia."
    else:
        system_prompt = (
            "Kamu adalah asisten penjelas serba tahu yang ramah, jernih, dan mudah dimengerti.\n"
            "TUGASMU:\n"
            "Jelaskan maksud pesan ini (baik berupa istilah asing/teknis, potongan kode/error, pengumuman panjang, "
            "meme/gambar, maupun pesan suara) dalam Bahasa Indonesia yang ringkas, jelas, dan langsung ke intinya!"
        )
        user_prompt = full_text or "Jelaskan maksud isi gambar atau pesan suara lampiran ini dengan jelas dalam Bahasa Indonesia."

    parts: list[dict] = [*(media_parts or []), {"text": user_prompt}]
    req_timeout = CHAT_TIMEOUT if media_parts else FAST_TEXT_TIMEOUT
    active_keys = get_gemini_keys_rotated()
    models_to_try = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
    last_err = "Server Gemini sedang sibuk."

    async with _borrow_session(http_session, req_timeout) as session:
        for idx, model_id in enumerate(models_to_try):
            gen_config: dict = {"temperature": 0.35, "maxOutputTokens": 3072}
            t_cfg = build_thinking_config(model_id, "low")
            if t_cfg:
                gen_config["thinkingConfig"] = t_cfg

            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen_config,
            }
            api_key = active_keys[idx % len(active_keys)]
            url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

            try:
                async with session.post(url, headers=headers, json=payload, timeout=req_timeout) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            return reply_text, None
                        if block_msg and not should_retry:
                            return None, block_msg
                        continue

                    if resp.status in (500, 502, 503, 504):
                        mark_model_unhealthy(model_id)
                    err_detail = (
                        data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if isinstance(data, dict)
                        else f"HTTP {resp.status}"
                    )
                    last_err = sanitize_error_message(err_detail)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                mark_model_unhealthy(model_id)
                continue

    return None, f"⚠️ Gagal memproses pesan: {last_err}"


async def fact_check_message_with_gemini(
    message_text: str,
    *,
    media_parts: list[dict] | None = None,
    text_blocks: list[str] | None = None,
    timezone_name: str = BOT_TIMEZONE,
    http_session: aiohttp.ClientSession | None = None,
) -> tuple[str | None, str | None]:
    """Memeriksa kebenaran klaim/berita/tangkapan layar (Cek Fakta / Hoaks) dengan pencarian web live gratis + Gemini."""
    if not is_gemini_key_configured():
        return None, "⚠️ `GEMINI_API_KEY` belum dikonfigurasi oleh Admin."

    combined_text_parts = [p for p in [message_text.strip(), *(text_blocks or [])] if p]
    full_text = "\n\n".join(combined_text_parts).strip()

    if not full_text and not media_parts:
        return None, "⚠️ Pesan tersebut kosong dan tidak memiliki klaim teks maupun gambar/dokumen yang bisa diperiksa."

    time_ctx = get_realtime_time_context(timezone_name)
    system_prompt = (
        "Kamu adalah pemeriksa fakta (fact-checker) independen yang objektif, kritis, dan teliti.\n"
        f"Waktu saat ini: {time_ctx['summary']}.\n\n"
        "TUGASMU:\n"
        "Periksa klaim di dalam teks pesan maupun tangkapan layar/gambar/dokumen terlampir secara jujur dan netral.\n"
        "Gunakan struktur ringkas berikut dalam Bahasa Indonesia:\n"
        "**🏷️ Status Klaim:** Pilih salah satu (`✅ Fakta Valid`, `⚠️ Perlu Konteks / Sebagian Benar`, "
        "`❌ Indikasi Hoaks / Keliru`, atau `❓ Belum Dapat Diverifikasi Pasti`)\n"
        "**📌 Klaim Utama:** (1 kalimat inti klaim yang diperiksa)\n"
        "**🔎 Hasil Pemeriksaan Fakta:** (Penjelasan singkat, padat, dan berbasis bukti/sumber terbaru)"
    )

    req_timeout = CHAT_TIMEOUT if media_parts else FAST_TEXT_TIMEOUT
    active_keys = get_gemini_keys_rotated()
    models_to_try = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
    last_err = "Server Gemini sedang sibuk."

    async with _borrow_session(http_session, req_timeout) as session:
        live_ctx = ""
        live_sources: list = []
        # Jika ada teks klaim yang cukup jelas, cari referensi berita/web terbaru secara gratis
        search_seed = re.sub(r"https?://\S+", " ", message_text).strip()
        if len(search_seed) >= 8:
            live_ctx, live_sources = await free_live_web_search(search_seed[:180], http_session=session)

        prompt_parts_text: list[str] = []
        if full_text:
            prompt_parts_text.append(f"Klaim / Pesan yang Diperiksa:\n{full_text}")
        else:
            prompt_parts_text.append(
                "Baca teks/klaim atau tangkapan layar berita pada media lampiran ini lalu periksa kebenaran faktanya!"
            )
        if live_ctx:
            prompt_parts_text.append(f"Referensi Web & Berita Terbaru:\n{live_ctx}")

        parts: list[dict] = [*(media_parts or []), {"text": "\n\n".join(prompt_parts_text)}]

        for idx, model_id in enumerate(models_to_try):
            gen_config: dict = {"temperature": 0.25, "maxOutputTokens": 3072}
            t_cfg = build_thinking_config(model_id, "low")
            if t_cfg:
                gen_config["thinkingConfig"] = t_cfg

            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen_config,
            }
            api_key = active_keys[idx % len(active_keys)]
            url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

            try:
                async with session.post(url, headers=headers, json=payload, timeout=req_timeout) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        reply_text, block_msg, should_retry = _extract_text_from_gemini_response(data)
                        if reply_text:
                            if live_sources:
                                footer = _format_grounding_footer(live_sources)
                                max_body = max(500, 3850 - len(footer))
                                clipped = reply_text[:max_body] + ("…" if len(reply_text) > max_body else "")
                                reply_text = f"{clipped}{footer}"
                            return reply_text, None
                        if block_msg and not should_retry:
                            return None, block_msg
                        continue

                    if resp.status in (500, 502, 503, 504):
                        mark_model_unhealthy(model_id)
                    err_detail = (
                        data.get("error", {}).get("message", f"HTTP {resp.status}")
                        if isinstance(data, dict)
                        else f"HTTP {resp.status}"
                    )
                    last_err = sanitize_error_message(err_detail)
            except (asyncio.TimeoutError, aiohttp.ClientError):
                mark_model_unhealthy(model_id)
                continue

    return None, f"⚠️ Gagal memeriksa fakta pesan: {last_err}"


async def generate_mystery_game_image_bytes(
    visual_prompt: str,
    *,
    http_session: aiohttp.ClientSession | None = None,
) -> bytes | None:
    """Membuat gambar petunjuk bebas-teks ukuran ringan (512x512) untuk mini-game 🖼️ Tebak Gambar AI (100% Free Tier)."""
    clean_desc = (visual_prompt or "").strip()
    if not clean_desc or not ENABLE_IMAGE_FALLBACK:
        return None

    full_prompt = (
        f"{clean_desc}, clear recognizable illustration, vibrant colors, centered subject, "
        "strictly no text, no letters, no words, no numbers, no watermark"
    )
    seed = random.randint(1, 999_999_999)
    encoded = urllib.parse.quote(full_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=512&height=512&seed={seed}&nologo=true&model=flux"
    )
    game_img_timeout = aiohttp.ClientTimeout(total=20, connect=8)
    async with _borrow_session(http_session, game_img_timeout) as session:
        try:
            async with session.get(url, timeout=game_img_timeout) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if resp.status == 200 and ctype.startswith("image/"):
                    img_bytes = await resp.read()
                    if len(img_bytes) > 1024:
                        return img_bytes
        except Exception:
            return None
    return None


