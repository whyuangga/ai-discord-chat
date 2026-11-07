"""Fitur **hemat kuota AI** (Tier 3) — pencatatan pemakaian, rekap ber-cache, & FAQ lokal.

Modul ini tidak memanggil Gemini sama sekali. Isinya:

1. **Pemakaian AI** — mencatat setiap operasi AI (chat, sesi, cari, ringkas, auto-chat,
   galeri, game) per hari/server/channel/member lalu menyajikannya lewat `/pemakaian`.
   Bisa dipakai sebagai **batas harian per member** (`AI_DAILY_CAP_PER_USER`).
2. **Rekap channel ber-cache** — `/ringkas channel periode:24j` menyimpan hasil ringkasan
   ke cache (`REKAP_CACHE_TTL_SEC`, default 30 menit) sehingga permintaan berulang
   **tidak memakan kuota lagi**.
3. **FAQ lokal (0 kuota)** — `/faq tanya` menjawab dari basis pengetahuan server dengan
   pencocokan kata kunci lokal; AI hanya dipakai bila memang diminta lewat `/cari`/`/sesi`.

Semua data disimpan di `data/ai_usage.json` (dipangkas otomatis 7 hari terakhir).
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import discord

from config import (
    AI_DAILY_CAP_PER_USER,
    AI_USAGE_FILE,
    AI_USAGE_KEEP_DAYS,
    DATA_DIR,
    REKAP_CACHE_TTL_SEC,
    REKAP_MAX_MESSAGES,
)

logger = logging.getLogger("gemini_bot.insights")

_lock = asyncio.Lock()

# ==============================================================================
# STATE
# ==============================================================================
ai_usage: dict[str, dict] = {}   # "YYYY-MM-DD" -> {total, cache_hits, kinds{}, users{}, channels{}}
rekap_cache: dict[tuple[int, int], dict] = {}   # (channel_id, hours) -> {text, created_at, count, requester}
# Batas entri member/channel yang dilacak per hari agar data/ai_usage.json tidak membengkak
MAX_TRACKED_PER_DAY = 300

AI_KIND_LABELS: dict[str, str] = {
    "chat": "💬 Chat (& vision/dokumen)",
    "sesi": "🔒 Ruang privat AI",
    "cari": "🌐 Cari berita",
    "ringkas_chat": "📝 Ringkas chat",
    "ringkas_link": "🔗 Ringkas link/YouTube",
    "rekap": "🗓️ Rekap channel berperiode",
    "auto_chat": "🤖 Auto-Chat komunitas",
    "galeri": "🖼️ Komentar galeri",
    "game": "🎮 Gambar game AI",
    "transform": "🌐 Terjemahkan/Jelaskan",
    "terjemah": "🌐 Terjemah (bendera/manual)",
    "cache": "♻️ Dijawab dari cache",
    "fakta": "🌍 Fakta Harian",
}

REKAP_PERIODS: dict[str, int] = {
    "1j": 1,
    "3j": 3,
    "6j": 6,
    "12j": 12,
    "24j": 24,
    "7h": 24 * 7,
}


def period_label(hours: int) -> str:
    """Label manusiawi untuk periode rekap."""
    total = max(1, int(hours))
    if total > 24 and total % 24 == 0:
        days = total // 24
        return "7 hari terakhir" if days == 7 else f"{days} hari terakhir"
    return f"{total} jam terakhir"


def today_key(*, now: float | None = None) -> str:
    current = time.time() if now is None else float(now)
    return time.strftime("%Y-%m-%d", time.localtime(current))


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def _empty_bucket() -> dict:
    return {
        "total": 0,
        "cache_hits": 0,
        "kinds": {},
        "users": {},
        "channels": {},
        "tokens_in": 0,
        "tokens_out": 0,
    }


def load_ai_usage_from_disk() -> int:
    """Memuat catatan pemakaian AI (hanya beberapa hari terakhir)."""
    ai_usage.clear()
    if not AI_USAGE_FILE.exists():
        return 0
    try:
        raw = json.loads(AI_USAGE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", AI_USAGE_FILE, exc)
        return 0

    for day, data in (raw.get("days") or {}).items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
            continue
        bucket = _empty_bucket()
        bucket["total"] = max(0, int(data.get("total") or 0))
        bucket["cache_hits"] = max(0, int(data.get("cache_hits") or 0))
        bucket["tokens_in"] = max(0, int(data.get("tokens_in") or 0))
        bucket["tokens_out"] = max(0, int(data.get("tokens_out") or 0))
        for field in ("kinds", "users", "channels"):
            bucket[field] = {
                str(key): max(0, int(value))
                for key, value in (data.get(field) or {}).items()
                if str(key)
            }
        ai_usage[str(day)] = bucket

    # Pemakaian per server disimpan terpisah (lihat ai_guard) agar ringkasan tetap ringkas
    try:
        import ai_guard

        ai_guard.load_guild_usage_from_disk(raw.get("guild_days") or {})
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Gagal memuat pemakaian per server: %s", exc)

    _prune_days()
    return len(ai_usage)


async def save_ai_usage_to_disk() -> None:
    """Menyimpan catatan pemakaian AI secara atomik (dipangkas dulu)."""
    async with _lock:
        try:
            _prune_days()
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"days": ai_usage}
            try:
                import ai_guard

                payload["guild_days"] = ai_guard.guild_usage_payload()
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.debug("Efek samping opsional gagal: %s", exc)
            tmp_file = Path(str(AI_USAGE_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, AI_USAGE_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan ai_usage.json")


def _prune_days() -> None:
    keep = max(1, int(AI_USAGE_KEEP_DAYS))
    if len(ai_usage) <= keep:
        return
    for day in sorted(ai_usage)[: len(ai_usage) - keep]:
        ai_usage.pop(day, None)


# ==============================================================================
# PENCATATAN PEMAKAIAN
# ==============================================================================
def record_ai_usage(
    kind: str,
    *,
    user_id: int = 0,
    channel_id: int = 0,
    guild_id: int = 0,
    cache_hit: bool = False,
    now: float | None = None,
) -> dict:
    """Mencatat satu operasi AI (atau cache hit) pada tanggal berjalan."""
    day = today_key(now=now)
    bucket = ai_usage.setdefault(day, _empty_bucket())
    label = str(kind or "chat")
    if cache_hit:
        bucket["cache_hits"] = int(bucket.get("cache_hits") or 0) + 1
        bucket.setdefault("kinds", {})["cache"] = int(bucket.get("kinds", {}).get("cache") or 0) + 1
        return bucket

    bucket["total"] = int(bucket.get("total") or 0) + 1
    kinds = bucket.setdefault("kinds", {})
    kinds[label] = int(kinds.get(label) or 0) + 1
    if user_id:
        users = bucket.setdefault("users", {})
        users[str(int(user_id))] = int(users.get(str(int(user_id))) or 0) + 1
        _trim_counter(users)
    if channel_id:
        channels = bucket.setdefault("channels", {})
        channels[str(int(channel_id))] = int(channels.get(str(int(channel_id))) or 0) + 1
        _trim_counter(channels)
    if guild_id:
        # Batas harian per server (ai_guard) ikut dihitung dari sini
        try:
            import ai_guard

            ai_guard.record_guild_usage(int(guild_id))
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Efek samping opsional gagal: %s", exc)
    return bucket


def add_token_usage(prompt_tokens: int = 0, output_tokens: int = 0, *, now: float | None = None) -> dict:
    """Mencatat token nyata dari `usageMetadata` Gemini (untuk /pemakaian)."""
    day = today_key(now=now)
    bucket = ai_usage.setdefault(day, _empty_bucket())
    bucket["tokens_in"] = int(bucket.get("tokens_in") or 0) + max(0, int(prompt_tokens))
    bucket["tokens_out"] = int(bucket.get("tokens_out") or 0) + max(0, int(output_tokens))
    return bucket


def token_totals(*, day: str | None = None) -> tuple[int, int]:
    """`(token masuk, token keluar)` pada satu hari."""
    bucket = ai_usage.get(day or today_key()) or {}
    return int(bucket.get("tokens_in") or 0), int(bucket.get("tokens_out") or 0)


def _trim_counter(counter: dict, limit: int = MAX_TRACKED_PER_DAY) -> None:
    """Menyisakan `limit` entri dengan hitungan tertinggi (server besar tetap hemat RAM)."""
    extra = len(counter) - int(limit)
    if extra <= 0:
        return
    for key, _ in sorted(counter.items(), key=lambda item: int(item[1]))[:extra]:
        counter.pop(key, None)


def usage_for_user(user_id: int, *, day: str | None = None) -> int:
    bucket = ai_usage.get(day or today_key()) or {}
    return int((bucket.get("users") or {}).get(str(int(user_id))) or 0)


def check_daily_cap(user_id: int, *, cap: int | None = None, day: str | None = None) -> tuple[bool, int, int]:
    """Memeriksa batas harian AI per member. `(boleh, terpakai, batas)`; batas 0 = tanpa limit."""
    limit = int(AI_DAILY_CAP_PER_USER if cap is None else cap)
    used = usage_for_user(user_id, day=day)
    if limit <= 0:
        return True, used, 0
    return used < limit, used, limit


def total_usage(*, day: str | None = None) -> int:
    bucket = ai_usage.get(day or today_key()) or {}
    return int(bucket.get("total") or 0)


# ==============================================================================
# REKAP BER-CACHE
# ==============================================================================
def cache_key(channel_id: int, hours: int) -> tuple[int, int]:
    return int(channel_id), int(hours)


def get_cached_rekap(channel_id: int, hours: int, *, max_age: int | None = None) -> dict | None:
    """Mengambil rekap dari cache bila masih segar."""
    ttl = int(REKAP_CACHE_TTL_SEC if max_age is None else max_age)
    entry = rekap_cache.get(cache_key(channel_id, hours))
    if not entry:
        return None
    if ttl > 0 and time.time() - float(entry.get("created_at") or 0) > ttl:
        rekap_cache.pop(cache_key(channel_id, hours), None)
        return None
    return entry


def store_rekap(
    channel_id: int,
    hours: int,
    text: str,
    *,
    message_count: int = 0,
    requester: str = "",
    now: float | None = None,
) -> dict:
    """Menyimpan hasil rekap ke cache (menggantikan entri lama)."""
    entry = {
        "text": str(text or ""),
        "created_at": time.time() if now is None else float(now),
        "count": int(message_count),
        "requester": str(requester or "")[:80],
    }
    rekap_cache[cache_key(channel_id, hours)] = entry
    return entry


def cache_age(entry: dict, *, now: float | None = None) -> int:
    """Umur cache dalam detik (untuk label 'diperbarui X lalu')."""
    current = time.time() if now is None else float(now)
    return max(0, int(current - float(entry.get("created_at") or 0)))


def cleanup_insights_runtime(*, max_age: int = REKAP_CACHE_TTL_SEC * 2) -> int:
    """Membuang cache rekap yang kedaluwarsa agar RAM tetap kecil."""
    removed = 0
    current = time.time()
    for key, entry in list(rekap_cache.items()):
        if max_age > 0 and current - float(entry.get("created_at") or 0) > max_age:
            rekap_cache.pop(key, None)
            removed += 1
    return removed


def rekap_message_limit() -> int:
    return max(20, int(REKAP_MAX_MESSAGES))


def reset_all_usage() -> int:
    """Menghapus seluruh catatan pemakaian. Mengembalikan jumlah hari yang dihapus."""
    count = len(ai_usage)
    ai_usage.clear()
    return count


def reset_rekap_cache() -> int:
    """Mengosongkan cache rekap. Mengembalikan jumlah entri yang dihapus."""
    count = len(rekap_cache)
    rekap_cache.clear()
    return count


# ==============================================================================
# TAMPILAN: PEMAKAIAN
# ==============================================================================
def _top_items(mapping: dict, limit: int = 5) -> list[tuple[str, int]]:
    rows = [(str(k), int(v)) for k, v in (mapping or {}).items()]
    rows.sort(key=lambda pair: pair[1], reverse=True)
    return rows[:limit]


def build_usage_embed(
    *, day: str | None = None, now: float | None = None, guild_id: int = 0
) -> discord.Embed:
    """Embed laporan pemakaian AI hari ini (tanpa memanggil Gemini).

    Bila `guild_id` diisi, ikut ditampilkan pemakaian & sisa kuota harian server
    serta penghematan dari FAQ lokal + cache jawaban.
    """
    key = day or today_key(now=now)
    bucket = ai_usage.get(key) or _empty_bucket()
    total = int(bucket.get("total") or 0)
    hits = int(bucket.get("cache_hits") or 0)
    tokens_in = int(bucket.get("tokens_in") or 0)
    tokens_out = int(bucket.get("tokens_out") or 0)

    token_line = (
        f"Token: **{tokens_in + tokens_out:,}** (masuk {tokens_in:,} • keluar {tokens_out:,})\n"
        if (tokens_in or tokens_out)
        else "Token: _belum tercatat hari ini_\n"
    )

    embed = discord.Embed(
        title="📊 Pemakaian AI Hari Ini",
        color=discord.Color.blurple(),
        description=(
            f"**{total}** operasi AI • **{hits}** cache hit (hemat kuota)\n"
            f"{token_line}"
            f"Tanggal: `{key}` • batas per member: "
            + (f"`{AI_DAILY_CAP_PER_USER}` operasi/hari" if AI_DAILY_CAP_PER_USER > 0 else "_tanpa batas_")
        ),
    )

    if guild_id:
        try:
            import ai_guard

            _cap_ok, cap_used, cap_limit = ai_guard.check_guild_cap(int(guild_id))
            savings = ai_guard.savings_stats()
            guild_line = (
                f"• Kuota server hari ini: **{cap_used}** / `{cap_limit}` operasi"
                if cap_limit > 0
                else f"• Kuota server hari ini: **{cap_used}** operasi (_tanpa batas_)"
            )
            embed.add_field(
                name="🏠 Kuota Server & Penghematan",
                value=(
                    f"{guild_line}\n"
                    f"• Dijawab dari FAQ lokal: **{int(savings.get('faq_hits') or 0)}** (0 kuota)\n"
                    f"• Dijawab dari cache: **{int(savings.get('cache_hits') or 0)}** (0 kuota)\n"
                    "-# Angka penghematan dihitung sejak bot terakhir restart."
                )[:1024],
                inline=False,
            )
        except Exception as exc:  # pragma: no cover - laporan tidak boleh gagal
            logger.debug("Efek samping opsional gagal: %s", exc)

    kinds = _top_items(bucket.get("kinds") or {}, limit=8)
    if kinds:
        embed.add_field(
            name="🧩 Jenis Operasi",
            value="\n".join(
                f"• {AI_KIND_LABELS.get(name, name)}: **{count}**" for name, count in kinds
            )[:1024],
            inline=False,
        )
    else:
        embed.add_field(name="🧩 Jenis Operasi", value="_belum ada pemakaian AI hari ini_", inline=False)

    users = _top_items(bucket.get("users") or {}, limit=5)
    if users:
        embed.add_field(
            name="👥 Member Paling Aktif",
            value="\n".join(f"• <@{uid}>: **{count}** operasi" for uid, count in users)[:1024],
            inline=False,
        )

    channels = _top_items(bucket.get("channels") or {}, limit=5)
    if channels:
        embed.add_field(
            name="📍 Channel Paling Ramai AI",
            value="\n".join(f"• <#{cid}>: **{count}** operasi" for cid, count in channels)[:1024],
            inline=False,
        )

    embed.set_footer(
        text=(
            "Hemat kuota: FAQ lokal & cache jawaban otomatis dipakai lebih dulu • "
            "/faq tanya menjawab tanpa AI"
        )
    )
    return embed


def build_usage_history_embed(days: int = 7, *, now: float | None = None) -> discord.Embed:
    """Ringkasan tren pemakaian beberapa hari terakhir."""
    embed = discord.Embed(
        title=f"📈 Tren Pemakaian AI ({days} hari)",
        color=discord.Color.dark_teal(),
    )
    keys = sorted(ai_usage)[-max(1, int(days)):]
    if not keys:
        embed.description = "Belum ada catatan pemakaian."
        return embed
    lines = []
    for key in keys:
        bucket = ai_usage[key]
        lines.append(
            f"`{key}` — **{int(bucket.get('total') or 0)}** operasi "
            f"({int(bucket.get('cache_hits') or 0)} cache hit)"
        )
    embed.description = "\n".join(lines)[:4000]
    embed.set_footer(text=f"Data disimpan maksimal {AI_USAGE_KEEP_DAYS} hari terakhir")
    return embed


# ==============================================================================
# TAMPILAN: REKAP
# ==============================================================================
def build_rekap_embed(
    channel_name: str,
    text: str,
    *,
    hours: int,
    message_count: int,
    cached: bool = False,
    cache_age_sec: int = 0,
    requested_by: str = "",
) -> discord.Embed:
    """Embed hasil rekap percakapan berperiode."""
    embed = discord.Embed(
        title=f"🗓️ Rekap #{channel_name} — {period_label(hours)}",
        description=str(text or "")[:3900],
        color=discord.Color.blurple() if not cached else discord.Color.teal(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="💬 Pesan Dianalisis", value=f"`{int(message_count)}`", inline=True)
    embed.add_field(
        name="🧠 Sumber",
        value="⚡ dari cache (0 kuota)" if cached else "Gemini (1 operasi)",
        inline=True,
    )
    footer = f"Diminta oleh {requested_by}" if requested_by else "Rekap berperiode"
    if cached and cache_age_sec:
        footer += f" • cache {cache_age_sec // 60} menit lalu"
    footer += " • gunakan paksa:True untuk menyegarkan"
    embed.set_footer(text=footer[:2048])
    return embed


# ==============================================================================
# FAQ LOKAL (tanpa kuota)
# ==============================================================================
_STOPWORDS: frozenset[str] = frozenset(
    {
        "yang", "dan", "atau", "untuk", "dengan", "apa", "apakah", "bagaimana", "gimana",
        "cara", "itu", "ini", "di", "ke", "dari", "aku", "saya", "kak", "min", "bang",
        "nya", "ada", "bisa", "kah", "dong", "ya", "tidak", "engga", "gak", "the", "a",
        "is", "how", "what", "do", "i",
    }
)


def tokenize(text: str) -> list[str]:
    """Memecah teks menjadi kata kunci bermakna (tanpa stopword)."""
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return [word for word in words if len(word) >= 3 and word not in _STOPWORDS]


def score_entry(entry: dict, query_tokens: list[str], query_text: str) -> int:
    """Skor kecocokan sebuah entri FAQ terhadap pertanyaan (lokal & murah)."""
    if not query_tokens:
        return 0
    topic = str(entry.get("topic") or "").lower()
    content = str(entry.get("content") or "").lower()
    blob = f"{topic} {content}"
    score = 0
    for token in query_tokens:
        if token in topic:
            score += 4
        if token in content:
            score += 2
    # Bonus bila frasa utuh muncul
    clean_query = " ".join(query_text.lower().split())
    if clean_query and clean_query in blob:
        score += 6
    return score


def search_faq(entries: list[dict], query: str, *, limit: int = 3, min_score: int = 4) -> list[dict]:
    """Mencari entri FAQ paling relevan. Mengembalikan daftar `{topic, content, score}`."""
    tokens = tokenize(query)
    if not tokens or not entries:
        return []
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        score = score_entry(entry, tokens, str(query or "").strip())
        if score >= min_score:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {"topic": str(entry.get("topic") or ""), "content": str(entry.get("content") or ""), "score": score}
        for score, entry in scored[: max(1, int(limit))]
    ]


def build_faq_answer_embed(query: str, matches: list[dict]) -> discord.Embed:
    """Embed jawaban FAQ lokal (0 kuota)."""
    embed = discord.Embed(
        title="📚 Jawaban dari FAQ Server",
        description=f"**Pertanyaan:** {str(query or '')[:300]}",
        color=discord.Color.green(),
    )
    if not matches:
        embed.color = discord.Color.orange()
        embed.description = (
            f"**Pertanyaan:** {str(query or '')[:300]}\n\n"
            "Belum ada entri FAQ yang cocok. Coba kata kunci lain, atau tanyakan langsung "
            "ke staf / buka tiket lewat `/tiket daftar`."
        )
        embed.set_footer(text="Jawaban lokal (0 kuota AI) • minta Admin menambah FAQ lewat /faq tambah")
        return embed

    for entry in matches[:3]:
        embed.add_field(
            name=f"📌 {str(entry.get('topic') or '')[:200]}",
            value=str(entry.get("content") or "")[:900],
            inline=False,
        )
    embed.set_footer(text="Dijawab tanpa AI (0 kuota) • sumber: basis FAQ server")
    return embed


def build_faq_list_embed(
    entries: list[dict],
    *,
    guild_name: str = "",
    max_shown: int = 20,
) -> discord.Embed:
    """Daftar entri FAQ server."""
    embed = discord.Embed(
        title="📚 Basis FAQ Server",
        color=discord.Color.blurple(),
        description=f"`{len(entries)}` entri tersimpan" + (f" • {guild_name}" if guild_name else ""),
    )
    if not entries:
        embed.description = (
            "Belum ada FAQ. Tambahkan dengan:\n"
            "`/faq tambah topik:Aturan umum isi:...`"
        )
        return embed
    lines = []
    for idx, entry in enumerate(entries[: max(1, int(max_shown))], start=1):
        topic = str(entry.get("topic") or "")[:60]
        content = str(entry.get("content") or "")[:140]
        lines.append(f"`{idx}.` **{topic}** — {content}")
    embed.description = "\n".join(lines)[:4000]
    if len(entries) > max_shown:
        embed.set_footer(text=f"Menampilkan {max_shown} dari {len(entries)} entri")
    else:
        embed.set_footer(text="Warga bisa bertanya lewat /faq tanya (tanpa memakai kuota AI)")
    return embed


