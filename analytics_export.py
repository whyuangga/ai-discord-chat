"""Ekspor analitik server ke **CSV** & kirim ke **webhook** (**0 kuota AI**).

Tiga sumber data yang sudah dimiliki bot, tanpa API eksternal:

| Jenis | Isi |
| :--- | :--- |
| `level` | Papan peringkat XP (user, level, XP, pesan, prestige) |
| `moderasi` | Riwayat kasus moderasi (ID, member, moderator, aksi, alasan, waktu) |
| `tiket` | Tiket beserta status, waktu respons pertama, durasi, & rating bintang |
| `pemakaian` | Pemakaian AI harian (total, cache hit, per jenis) |

CSV dibuat di memori lalu dikirim sebagai lampiran `discord.File` atau ke webhook.
Batas baris dijaga (`MAX_ROWS`) supaya RAM Free Tier tetap aman.
"""

import asyncio
import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from config import ANALYTICS_FILE, DATA_DIR

logger = logging.getLogger("gemini_bot.analytics_export")

_lock = asyncio.Lock()

MAX_ROWS = 2000
KINDS: dict[str, str] = {
    "level": "📈 Papan peringkat XP",
    "moderasi": "🛡️ Riwayat kasus moderasi",
    "tiket": "🎟️ Data tiket & rating",
    "pemakaian": "📊 Pemakaian AI",
}
JADWAL: dict[str, str] = {
    "mati": "⛔ Nonaktif",
    "harian": "🗓️ Harian",
    "mingguan": "📅 Mingguan",
}
JADWAL_SEC: dict[str, int] = {"harian": 86400, "mingguan": 7 * 86400}

# guild_id -> konfigurasi ekspor
analytics_guilds: dict[int, dict] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_config() -> dict:
    return {
        "aktif": False,
        "webhook_url": None,
        "jadwal": "mati",
        "jenis": ["level", "moderasi", "tiket", "pemakaian"],
        "last_sent": 0.0,
        "sent_count": 0,
    }


def get_config(guild_id: int) -> dict:
    gid = int(guild_id)
    cfg = analytics_guilds.get(gid)
    if cfg is None:
        cfg = default_config()
        analytics_guilds[gid] = cfg
    else:
        for key, value in default_config().items():
            cfg.setdefault(key, value)
    return cfg


def set_config(guild_id: int, **changes) -> dict:
    cfg = get_config(guild_id)
    if changes.get("aktif") is not None:
        cfg["aktif"] = bool(changes["aktif"])
    if changes.get("jadwal") in JADWAL:
        cfg["jadwal"] = str(changes["jadwal"])
    if changes.get("webhook_url") is not None:
        url = str(changes["webhook_url"] or "").strip()
        cfg["webhook_url"] = url or None
    if changes.get("jenis") is not None:
        picked = [kind for kind in changes["jenis"] if kind in KINDS]
        cfg["jenis"] = picked or list(KINDS)
    return cfg


def validate_webhook(url: str) -> tuple[bool, str]:
    """Memastikan URL adalah webhook Discord yang wajar."""
    value = str(url or "").strip()
    if not value:
        return False, "URL webhook kosong."
    if not value.startswith("https://"):
        return False, "URL webhook harus diawali `https://`."
    allowed = (
        "discord.com/api/webhooks/",
        "discordapp.com/api/webhooks/",
        "ptb.discord.com/api/webhooks/",
        "canary.discord.com/api/webhooks/",
    )
    if not any(host in value for host in allowed):
        return False, "Itu bukan URL webhook Discord (harus `discord.com/api/webhooks/...`)."
    if " " in value:
        return False, "URL webhook tidak boleh mengandung spasi."
    return True, ""


# ==============================================================================
# PEMBUATAN CSV
# ==============================================================================
def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def _fmt_time(value) -> str:
    seconds = float(value or 0)
    if seconds <= 0:
        return ""
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _write_csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows[:MAX_ROWS])
    return buffer.getvalue()


def build_level_csv(guild_id: int) -> str:
    import levels

    rows = []
    for key, data in list(levels.levels.items())[:]:
        try:
            gid_str, uid_str = str(key).split(":", 1)
        except ValueError:
            continue
        if int(gid_str) != int(guild_id):
            continue
        rows.append(
            [
                int(uid_str),
                _to_int(data.get("level")),
                _to_int(data.get("xp")),
                _to_int(data.get("messages")),
                _to_int(data.get("voice_xp")),
                _to_int(data.get("prestige")),
                _fmt_time(data.get("last_at")),
            ]
        )
    rows.sort(key=lambda row: row[2], reverse=True)
    return _write_csv(
        ["user_id", "level", "xp", "messages", "voice_xp", "prestige", "last_activity"],
        rows,
    )


def build_moderation_csv(guild_id: int) -> str:
    import moderation

    rows = [
        [
            _to_int(case.get("id")),
            _to_int(case.get("user_id")),
            _to_int(case.get("moderator_id")),
            str(case.get("action") or ""),
            str(case.get("reason") or ""),
            _to_int(case.get("duration_sec")),
            _fmt_time(case.get("created_at")),
        ]
        for case in (moderation.mod_cases.get(int(guild_id)) or [])
    ]
    rows.reverse()  # terbaru dulu
    return _write_csv(
        ["case_id", "user_id", "moderator_id", "action", "reason", "duration_sec", "created_at"],
        rows,
    )


def build_ticket_csv(guild_id: int) -> str:
    import tickets

    rows = []
    for data in tickets.tickets.values():
        if _to_int(data.get("guild_id")) != int(guild_id):
            continue
        created = float(data.get("created_at") or 0)
        closed = float(data.get("closed_at") or 0)
        first = float(data.get("first_response_at") or 0)
        rows.append(
            [
                _to_int(data.get("number")),
                _to_int(data.get("user_id")),
                str(data.get("status") or ""),
                str(data.get("topic") or ""),
                _to_int(data.get("claimed_by")),
                _fmt_time(created),
                _fmt_time(first),
                round((first - created) / 60) if first and created else "",
                round((closed - created) / 60) if closed and created else "",
                _to_int(data.get("rating")),
                str(data.get("closed_reason") or ""),
            ]
        )
    rows.sort(key=lambda row: row[0])
    return _write_csv(
        [
            "ticket_number",
            "user_id",
            "status",
            "topic",
            "claimed_by",
            "created_at",
            "first_response_at",
            "first_response_minutes",
            "duration_minutes",
            "rating",
            "closed_reason",
        ],
        rows,
    )


def build_usage_csv() -> str:
    import insights

    rows = []
    for day in sorted(insights.ai_usage):
        bucket = insights.ai_usage.get(day) or {}
        kinds = bucket.get("kinds") or {}
        rows.append(
            [
                day,
                _to_int(bucket.get("total")),
                _to_int(bucket.get("cache_hits")),
                _to_int(kinds.get("chat")),
                _to_int(kinds.get("ringkas")),
                _to_int(kinds.get("gambar")),
                _to_int(kinds.get("cari")),
            ]
        )
    return _write_csv(
        ["day", "total_calls", "cache_hits", "chat", "ringkas", "gambar", "cari"],
        rows,
    )


BUILDERS = {
    "level": build_level_csv,
    "moderasi": build_moderation_csv,
    "tiket": build_ticket_csv,
    "pemakaian": build_usage_csv,
}


def build_csv(kind: str, guild_id: int) -> tuple[str | None, str, str]:
    """Membangun CSV. Mengembalikan `(isi_csv, nama_berkas, error)`."""
    key = str(kind or "").lower()
    builder = BUILDERS.get(key)
    if builder is None:
        return None, "", f"Jenis `{kind}` tidak dikenal. Pilihan: {', '.join(KINDS)}."
    try:
        if key == "pemakaian":
            body = builder()  # type: ignore[call-arg]
        else:
            body = builder(int(guild_id))
    except Exception as exc:  # pragma: no cover - data rusak
        logger.warning("Gagal membuat CSV %s: %s", key, exc)
        return None, "", f"Gagal membuat CSV `{key}`: `{type(exc).__name__}`"

    rows = max(0, body.count("\n") - 1)
    if rows == 0:
        return None, "", f"Belum ada data **{KINDS[key].split(' ', 1)[-1]}** untuk diekspor."
    filename = f"analitik-{key}-{int(guild_id)}-{_now_stamp()}.csv"
    return body, filename, ""


def csv_bytes(body: str) -> bytes:
    """CSV + BOM agar Excel membaca UTF-8 dengan benar."""
    return ("\ufeff" + body).encode("utf-8")


def build_all(guild_id: int) -> list[tuple[str, str, str]]:
    """Semua CSV yang tersedia: `[(jenis, nama_berkas, isi)]`."""
    hasil = []
    for kind in KINDS:
        body, filename, _error = build_csv(kind, guild_id)
        if body:
            hasil.append((kind, filename, body))
    return hasil


# ==============================================================================
# PENGIRIMAN WEBHOOK
# ==============================================================================
def is_due(guild_id: int, *, now: float | None = None) -> bool:
    """Apakah jadwal ekspor webhook sudah waktunya jalan."""
    cfg = get_config(guild_id)
    if not cfg.get("aktif") or not cfg.get("webhook_url"):
        return False
    interval = JADWAL_SEC.get(str(cfg.get("jadwal") or "mati"))
    if not interval:
        return False
    current = time.time() if now is None else float(now)
    return current - float(cfg.get("last_sent") or 0) >= interval


async def post_csv_to_webhook(
    url: str,
    body: str,
    filename: str,
    *,
    session=None,
    timeout: float = 20.0,
) -> tuple[bool, str]:
    """Mengirim satu CSV ke webhook Discord (multipart, tanpa dependency baru)."""
    ok, error = validate_webhook(url)
    if not ok:
        return False, error

    import aiohttp

    payload = {
        "content": f"📊 **Ekspor analitik** `{filename}`",
        "username": "Analitik Server",
        "allowed_mentions": {"parse": []},
    }
    form = aiohttp.FormData()
    form.add_field("payload_json", json.dumps(payload), content_type="application/json")
    form.add_field(
        "files[0]",
        csv_bytes(body),
        filename=filename,
        content_type="text/csv",
    )

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    try:
        async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status in (200, 204):
                return True, "terkirim"
            detail = (await resp.text())[:200]
            return False, f"webhook menolak (`{resp.status}`): {detail}"
    except Exception as exc:  # pragma: no cover - jaringan
        return False, f"gagal kirim (`{type(exc).__name__}`)"
    finally:
        if own_session:
            await session.close()


async def run_analytics_check(bot, *, now: float | None = None, session=None) -> int:
    """Dipanggil berkala: kirim CSV ke webhook server yang jadwalnya sudah tiba."""
    sent = 0
    network = session or getattr(bot, "http_session", None)
    for gid in list(analytics_guilds):
        if not is_due(gid, now=now):
            continue
        cfg = get_config(gid)
        kinds = [kind for kind in (cfg.get("jenis") or list(KINDS)) if kind in KINDS]
        delivered = 0
        for kind in kinds:
            body, filename, error = build_csv(kind, gid)
            if not body:
                logger.debug("Ekspor %s dilewati di %s: %s", kind, gid, error)
                continue
            ok, message = await post_csv_to_webhook(
                str(cfg.get("webhook_url")), body, filename, session=network
            )
            if ok:
                delivered += 1
            else:
                logger.warning("Ekspor %s ke webhook %s gagal: %s", kind, gid, message)
        cfg["last_sent"] = time.time() if now is None else float(now)
        cfg["sent_count"] = _to_int(cfg.get("sent_count")) + delivered
        if delivered:
            sent += delivered
    if sent or analytics_guilds:
        await save_analytics_to_disk()
    return sent


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def load_analytics_from_disk() -> int:
    analytics_guilds.clear()
    path = Path(ANALYTICS_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(data, dict):
            continue
        cfg = default_config()
        cfg["aktif"] = bool(data.get("aktif", False))
        url = str(data.get("webhook_url") or "").strip()
        cfg["webhook_url"] = url or None
        cfg["jadwal"] = data.get("jadwal") if data.get("jadwal") in JADWAL else "mati"
        picked = [kind for kind in (data.get("jenis") or []) if kind in KINDS]
        cfg["jenis"] = picked or list(KINDS)
        cfg["last_sent"] = float(data.get("last_sent") or 0)
        cfg["sent_count"] = max(0, _to_int(data.get("sent_count")))
        analytics_guilds[gid] = cfg
    return len(analytics_guilds)


async def save_analytics_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(gid): cfg for gid, cfg in analytics_guilds.items()}}
            tmp_file = Path(str(ANALYTICS_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, ANALYTICS_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan analytics.json")


def cleanup_analytics_runtime() -> int:
    """Membuang konfigurasi ekspor yang kosong (tanpa webhook & nonaktif)."""
    removed = 0
    for gid, cfg in list(analytics_guilds.items()):
        if not cfg.get("aktif") and not cfg.get("webhook_url"):
            analytics_guilds.pop(gid, None)
            removed += 1
    return removed


def mask_webhook(url: str | None) -> str:
    """Menyamarkan URL webhook untuk ditampilkan di Discord."""
    value = str(url or "")
    if not value:
        return "_belum diatur_"
    token = value.rsplit("/", 1)[-1]
    return f"`...{token[-6:]}`" if len(token) > 6 else "`***`"
