"""Penjaga kualitas & kuota AI — 0 dependensi baru, 0 panggilan AI tambahan.

Berisi enam pengaman yang dipakai bersama oleh `ai_handler`, `community_agent`,
`cogs/session_cog`, dan `cogs/agent_cog`:

1. `faq_first_answer()`  — jawab dari FAQ/Info server lokal sebelum memanggil Gemini (hemat kuota).
2. `get_cached_reply()` / `store_cached_reply()` — pertanyaan identik dalam waktu dekat = 0 kuota.
3. `check_guild_cap()` — batas harian per **server** (bukan hanya per member) + peringatan 80%.
4. `route_model_key()` — pertanyaan ringan diarahkan ke model hemat (Flash-Lite).
5. `safety_settings_for()` — tingkat keamanan konten per server (`longgar`/`normal`/`ketat`).
6. `ANTI_HALUSINASI_RULES` + `compress_dropped_history()` — aturan anti-mengarang &
   ringkasan riwayat lama agar konteks percakapan panjang tidak hilang.
"""

import hashlib
import logging
import re
import time

from config import (
    AI_DAILY_CAP_PER_GUILD,
    AI_REPLY_CACHE_MAX,
    AI_REPLY_CACHE_TTL_SEC,
)

logger = logging.getLogger("gemini_bot.ai_guard")

# Statistik penghematan (0 kuota) — dipakai /pemakaian
_savings: dict[str, int] = {"faq_hits": 0, "cache_hits": 0}


def record_savings(kind: str, amount: int = 1) -> None:
    """Mencatat satu jawaban yang dihemat (tanpa memanggil AI)."""
    key = str(kind or "").strip().lower()
    if key in _savings:
        _savings[key] += max(1, int(amount))


def savings_stats() -> dict[str, int]:
    """Salinan statistik penghematan: `faq_hits` (FAQ lokal) & `cache_hits` (cache jawaban)."""
    return dict(_savings)


def reset_savings() -> None:
    for key in _savings:
        _savings[key] = 0

# ==============================================================================
# 1. FAQ-FIRST (0 kuota)
# ==============================================================================
FAQ_MIN_CONFIDENCE = 6.0


def faq_first_answer(entries: list[dict], question: str) -> dict | None:
    """Mencari jawaban lokal dari FAQ server. `None` bila tidak cukup yakin.

    Memakai `insights.search_faq` (skor kata kunci) dan hanya memakai hasil teratas
    bila skornya jelas di atas ambang — supaya tidak "menebak" jawaban salah.
    """
    import insights

    text = str(question or "").strip()
    if len(text) < 12 or not entries:
        return None

    try:
        matches = insights.search_faq(entries, text, limit=1, min_score=int(FAQ_MIN_CONFIDENCE))
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("FAQ-first gagal: %s", exc)
        return None
    if not matches:
        return None

    best = matches[0]
    record_savings("faq_hits")
    return {
        "topic": str(best.get("topic") or "").strip(),
        "content": str(best.get("content") or "").strip(),
        "score": float(best.get("score") or 0.0),
        "entry": best,
    }


def format_faq_reply(hit: dict) -> str:
    """Teks balasan FAQ-first (ringkas, jelas, menyebut sumbernya)."""
    topic = hit.get("topic") or "Info server"
    content = hit.get("content") or ""
    return f"**{topic}**\n{content}\n\n-# dijawab dari FAQ server (0 kuota AI)"


# ==============================================================================
# 2. CACHE JAWABAN IDENTIK
# ==============================================================================
_reply_cache: dict[tuple[int, str], dict] = {}


def normalize_question(text: str) -> str:
    """Normalisasi pertanyaan agar variasi kecil tetap dianggap sama."""
    lowered = str(text or "").lower()
    lowered = re.sub(r"<@!?\d+>", " ", lowered)          # buang mention
    lowered = re.sub(r"https?://\S+", " url ", lowered)   # samakan semua link
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered[:280]


def _cache_key(channel_id: int, question: str) -> tuple[int, str]:
    digest = hashlib.sha1(question.encode("utf-8")).hexdigest()[:20]
    return int(channel_id), digest


def get_cached_reply(channel_id: int, question: str, *, ttl: int | None = None) -> str | None:
    """Balasan tersimpan untuk pertanyaan yang sama (belum kedaluwarsa)."""
    normalized = normalize_question(question)
    if len(normalized) < 8:
        return None
    entry = _reply_cache.get(_cache_key(channel_id, normalized))
    if not entry:
        return None
    limit = int(AI_REPLY_CACHE_TTL_SEC if ttl is None else ttl)
    if limit <= 0 or time.time() - float(entry.get("at") or 0) > limit:
        _reply_cache.pop(_cache_key(channel_id, normalized), None)
        return None
    record_savings("cache_hits")
    return str(entry.get("reply") or "")


def store_cached_reply(channel_id: int, question: str, reply: str) -> bool:
    """Menyimpan balasan; pertanyaan terlalu pendek/panik tidak di-cache."""
    normalized = normalize_question(question)
    text = str(reply or "").strip()
    if len(normalized) < 8 or len(text) < 16 or AI_REPLY_CACHE_TTL_SEC <= 0:
        return False
    _reply_cache[_cache_key(channel_id, normalized)] = {"reply": text[:4000], "at": time.time()}
    while len(_reply_cache) > max(10, AI_REPLY_CACHE_MAX):
        _reply_cache.pop(next(iter(_reply_cache)))
    return True


def reply_cache_size() -> int:
    return len(_reply_cache)


def clear_reply_cache() -> int:
    count = len(_reply_cache)
    _reply_cache.clear()
    return count


def cleanup_ai_guard_runtime() -> int:
    """Membuang cache kedaluwarsa (dipanggil pembersih RAM per jam)."""
    now = time.time()
    ttl = int(AI_REPLY_CACHE_TTL_SEC)
    stale = [
        key for key, entry in _reply_cache.items()
        if ttl <= 0 or now - float(entry.get("at") or 0) > ttl
    ]
    for key in stale:
        _reply_cache.pop(key, None)
    return len(stale)


# ==============================================================================
# 3. BATAS HARIAN PER SERVER
# ==============================================================================
guild_ai_usage: dict[str, dict[int, int]] = {}   # "YYYY-MM-DD" -> {guild_id: count}
_guild_alerted: dict[str, set[int]] = {}        # hari -> server yang sudah diperingatkan


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def record_guild_usage(guild_id: int, amount: int = 1) -> int:
    """Mencatat pemakaian AI sebuah server (dipanggil setiap operasi Gemini sukses)."""
    day = _today()
    bucket = guild_ai_usage.setdefault(day, {})
    bucket[int(guild_id)] = bucket.get(int(guild_id), 0) + max(0, int(amount))
    # sisakan hanya 2 hari terakhir agar RAM tetap kecil
    for old_day in sorted(guild_ai_usage)[:-2]:
        guild_ai_usage.pop(old_day, None)
        _guild_alerted.pop(old_day, None)
    return bucket[int(guild_id)]


def guild_usage_today(guild_id: int) -> int:
    return int((guild_ai_usage.get(_today()) or {}).get(int(guild_id), 0))


def check_guild_cap(guild_id: int, cap: int | None = None) -> tuple[bool, int, int]:
    """`(boleh_lanjut, terpakai, batas)`. Batas 0 = tanpa batas."""
    limit = int(AI_DAILY_CAP_PER_GUILD if cap is None else cap)
    used = guild_usage_today(guild_id)
    if limit <= 0:
        return True, used, 0
    return used < limit, used, limit


def should_alert_guild_cap(guild_id: int, *, ratio: float = 0.8) -> tuple[bool, int, int]:
    """True sekali saja saat pemakaian melewati 80% batas (untuk peringatan ke admin)."""
    limit = int(AI_DAILY_CAP_PER_GUILD)
    if limit <= 0:
        return False, guild_usage_today(guild_id), 0
    used = guild_usage_today(guild_id)
    if used < int(limit * ratio):
        return False, used, limit
    day = _today()
    alerted = _guild_alerted.setdefault(day, set())
    if int(guild_id) in alerted:
        return False, used, limit
    alerted.add(int(guild_id))
    return True, used, limit


def cap_message(guild_id: int, used: int, limit: int) -> str:
    """Pesan ramah saat batas harian server tercapai."""
    return (
        "⚠️ **Kuota AI server ini sudah mencapai batas harian.**\n"
        f"Terpakai `{used}` dari `{limit}` operasi hari ini.\n"
        "Fitur tanpa AI (FAQ lokal, musik, moderasi, giveaway, dsb.) tetap berjalan normal. "
        "Kuota pulih otomatis besok, atau Admin bisa menaikkan `AI_DAILY_CAP_PER_GUILD`."
    )


def load_guild_usage_from_disk(raw: dict | None) -> int:
    """Memuat pemakaian harian per server dari berkas pemakaian AI."""
    guild_ai_usage.clear()
    total = 0
    for day, bucket in (raw or {}).items():
        if not isinstance(bucket, dict):
            continue
        cleaned: dict[int, int] = {}
        for gid, value in bucket.items():
            try:
                cleaned[int(gid)] = int(value)
            except (TypeError, ValueError):
                continue
        if cleaned:
            guild_ai_usage[str(day)] = cleaned
            total += len(cleaned)
    return total


def guild_usage_payload() -> dict[str, dict[str, int]]:
    """Payload siap-JSON untuk disimpan di `data/ai_usage.json`."""
    return {
        day: {str(gid): int(value) for gid, value in bucket.items()}
        for day, bucket in guild_ai_usage.items()
    }


# ==============================================================================
# 4. ROUTER MODEL HEMAT
# ==============================================================================
_HEAVY_HINTS = (
    "kode", "code", "error", "debug", "script", "program", "fungsi", "regex",
    "hitung", "matematika", "integral", "analisis", "jelaskan", "bandingkan",
    "rangkum", "ringkas", "terjemah", "puisi", "esai", "artikel",
)


def route_model_key(
    base_key: str,
    prompt: str,
    *,
    has_media: bool = False,
    has_links: bool = False,
    history_len: int = 0,
) -> str:
    """Memilih model lebih hemat untuk pertanyaan ringan.

    Aturan konservatif (tidak menurunkan kualitas jawaban berat):
        - hanya menurunkan `gemini_flash` → `gemini_fast`
        - TIDAK menurunkan bila ada media/link, riwayat panjang, atau kata kunci berat
        - pertanyaan harus pendek (≤ 140 karakter)
    """
    from config import AI_MODELS

    key = str(base_key or "gemini_flash")
    if key != "gemini_flash" or "gemini_fast" not in AI_MODELS:
        return key
    if has_media or has_links or history_len > 8:
        return key

    text = str(prompt or "").strip()
    if not text or len(text) > 140:
        return key
    lowered = text.lower()
    if any(hint in lowered for hint in _HEAVY_HINTS):
        return key
    return "gemini_fast"


# ==============================================================================
# 5. SAFETY SETTINGS PER SERVER
# ==============================================================================
SAFETY_LEVELS: dict[str, dict] = {
    "longgar": {"label": "Longgar (default Google)", "emoji": "🟢", "threshold": "OFF"},
    "normal": {"label": "Normal — blokir konten berbahaya", "emoji": "🟡", "threshold": "BLOCK_ONLY_HIGH"},
    "ketat": {"label": "Ketat — untuk server keluarga/anak", "emoji": "🔴", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
}

_SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
    "HARM_CATEGORY_CIVIC_INTEGRITY",
)


def safety_settings_for(level: str | None) -> list[dict] | None:
    """Menyusun `safetySettings` Gemini sesuai tingkat server (`None` = default)."""
    key = str(level or "longgar").strip().lower()
    if key not in SAFETY_LEVELS or key == "longgar":
        return None
    threshold = SAFETY_LEVELS[key]["threshold"]
    return [
        {"category": category, "threshold": threshold}
        for category in _SAFETY_CATEGORIES
    ]


def apply_safety(payload: dict, level: str | None) -> dict:
    """Menambahkan `safetySettings` ke payload bila server memilih tingkat ketat/normal."""
    settings = safety_settings_for(level)
    if settings:
        payload["safetySettings"] = settings
    return payload


# ==============================================================================
# 6. ANTI-HALUSINASI & MEMORI RIWAYAT
# ==============================================================================
ANTI_HALUSINASI_RULES = (
    "\n\n[ATURAN AKURASI]\n"
    "- Jika kamu tidak yakin atau datanya tidak ada, katakan terus terang bahwa kamu belum tahu; "
    "jangan mengarang fakta, angka, tanggal, kutipan, atau tautan.\n"
    "- Bedakan jelas antara fakta yang diberikan di konteks dan dugaanmu sendiri.\n"
    "- Saat memakai data pencarian web, sebutkan sumbernya secara singkat.\n"
    "- Selalu jawab dalam bahasa Indonesia kecuali pengguna meminta bahasa lain."
)


def with_accuracy_rules(system_text: str, *, enabled: bool = True) -> str:
    """Menambahkan aturan akurasi ke system prompt (idempoten)."""
    base = str(system_text or "")
    if not enabled or "[ATURAN AKURASI]" in base:
        return base
    return base + ANTI_HALUSINASI_RULES


def compress_dropped_history(dropped: list[dict], *, max_chars: int = 700) -> str:
    """Merangkum giliran percakapan yang terbuang dari jendela riwayat (tanpa AI).

    Hasilnya berupa daftar poin pendek yang bisa diselipkan kembali ke system prompt
    sehingga bot tidak "lupa" topik lama saat riwayat dipangkas.
    """
    lines: list[str] = []
    for item in dropped:
        role = "Pengguna" if str(item.get("role")) == "user" else "Kamu"
        content = " ".join(str(item.get("content") or "").split())
        if not content:
            continue
        lines.append(f"- {role}: {content[:140]}")
    if not lines:
        return ""
    text = "\n".join(lines[-8:])
    if len(text) > max_chars:
        text = text[-max_chars:]
    return "RINGKASAN OBROLAN SEBELUMNYA (sudah keluar dari jendela riwayat):\n" + text


def merge_history_summary(previous: str, dropped: list[dict]) -> str:
    """Menggabungkan ringkasan lama dengan giliran yang baru terbuang."""
    fresh = compress_dropped_history(dropped)
    if not fresh:
        return str(previous or "")
    combined = f"{previous}\n{fresh}" if previous else fresh
    return combined[-1400:]
