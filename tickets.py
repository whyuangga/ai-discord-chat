"""Sistem Tiket Dukungan berbasis **Private Thread** (Tier 2C) — 0 kuota Gemini.

Kenapa thread, bukan channel?
- Thread **tidak memakan slot channel** server (batas channel Discord 500/server).
- Otomatis rapi: tiket selesai bisa diarsipkan, bukan menumpuk jadi channel mati.
- Pembuat tiket & staf tetap bisa lanjut diskusi tanpa mengganggu channel umum.

Data disimpan di `data/tickets.json`. Seluruh fitur **default NONAKTIF**
sampai Admin menjalankan `/tiket panel`.
"""

import asyncio
import io
import json
import logging
import os
import time
from pathlib import Path

import discord
import channel_targets

from config import (
    DATA_DIR,
    TICKET_AUTO_CLOSE_HOURS,
    TICKET_MAX_OPEN_PER_USER,
    TICKET_MAX_TRANSCRIPT_LINES,
    TICKETS_FILE,
)
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.tickets")

_lock = asyncio.Lock()

# Catatan internal staf: tidak pernah dikirim ke thread, hanya tampil di dashboard.
TICKET_NOTE_MAX = 25
TICKET_NOTE_LEN = 500

# Topik tiket: panel bisa menawarkan beberapa topik, masing-masing dengan role staf sendiri.
TICKET_TOPIC_MAX = 8
TICKET_TOPIC_LEN = 40

TICKET_STATUS: dict[str, str] = {
    "terbuka": "🟢 Terbuka",
    "diklaim": "🙋 Sedang ditangani",
    "selesai": "✅ Selesai",
}

# ==============================================================================
# STATE GLOBAL
# ==============================================================================
ticket_guilds: dict[int, dict] = {}   # guild_id -> konfigurasi panel tiket
tickets: dict[int, dict] = {}         # thread_id -> data tiket
_ticket_seq: dict[int, int] = {}      # guild_id -> nomor tiket terakhir


def default_config() -> dict:
    return {
        "enabled": True,
        "panel_channel_id": None,
        "panel_message_id": None,
        "staff_role_id": None,
        "category_id": None,
        "log_channel_id": None,
        "max_open": int(TICKET_MAX_OPEN_PER_USER),
        "ping_staff": True,
        "opened": 0,
        "closed": 0,
        # v1.33.0-beta: rating bintang, SLA respons pertama, & auto-close
        "rating_aktif": True,
        "sla_jam": 0,            # 0 = nonaktif; N = jam sebelum tiket tanpa respons dianggap telat
        "auto_close_jam": int(TICKET_AUTO_CLOSE_HOURS or 0),  # 0 = nonaktif
        "sla_channel_id": None,
        "rating_sum": 0,
        "rating_count": 0,
        "auto_closed": 0,
        "sla_alerted": 0,
        # v1.40: multi-topik (kosong = satu topik umum seperti sebelumnya)
        "topics": [],
    }


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ==============================================================================
# PERSISTENSI
# ==============================================================================
def load_tickets_from_disk() -> int:
    """Memuat konfigurasi panel tiket & tiket yang tercatat."""
    ticket_guilds.clear()
    tickets.clear()
    _ticket_seq.clear()
    if not TICKETS_FILE.exists():
        return 0

    try:
        raw = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", TICKETS_FILE, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        base = default_config()
        base.update(
            {
                "enabled": bool(data.get("enabled", True)),
                "panel_channel_id": _to_int(data.get("panel_channel_id")) or None,
                "panel_message_id": _to_int(data.get("panel_message_id")) or None,
                "staff_role_id": _to_int(data.get("staff_role_id")) or None,
                "category_id": _to_int(data.get("category_id")) or None,
                "log_channel_id": _to_int(data.get("log_channel_id")) or None,
                "max_open": max(1, _to_int(data.get("max_open"), base["max_open"])),
                "ping_staff": bool(data.get("ping_staff", True)),
                "opened": max(0, _to_int(data.get("opened"))),
                "closed": max(0, _to_int(data.get("closed"))),
                "rating_aktif": bool(data.get("rating_aktif", True)),
                "sla_jam": max(0, min(720, _to_int(data.get("sla_jam")))),
                "auto_close_jam": max(0, min(720, _to_int(data.get("auto_close_jam"), base["auto_close_jam"]))),
                "sla_channel_id": _to_int(data.get("sla_channel_id")) or None,
                "rating_sum": max(0, _to_int(data.get("rating_sum"))),
                "rating_count": max(0, _to_int(data.get("rating_count"))),
                "auto_closed": max(0, _to_int(data.get("auto_closed"))),
                "sla_alerted": max(0, _to_int(data.get("sla_alerted"))),
                "topics": normalize_topics(data.get("topics")),
            }
        )
        ticket_guilds[gid] = base
        _ticket_seq[gid] = max(_ticket_seq.get(gid, 0), _to_int(data.get("seq")))

    for tid_str, data in (raw.get("tickets") or {}).items():
        try:
            tid = int(tid_str)
            gid = _to_int(data.get("guild_id"))
            uid = _to_int(data.get("user_id"))
        except (TypeError, ValueError):
            continue
        if not gid or not uid:
            continue
        number = max(1, _to_int(data.get("number"), 1))
        tickets[tid] = {
            "thread_id": tid,
            "guild_id": gid,
            "user_id": uid,
            "number": number,
            "status": str(data.get("status") or "terbuka")
            if str(data.get("status") or "terbuka") in TICKET_STATUS
            else "terbuka",
            "topic": str(data.get("topic") or "")[:200],
            "created_at": float(data.get("created_at") or 0),
            "claimed_by": _to_int(data.get("claimed_by")) or None,
            "closed_by": _to_int(data.get("closed_by")) or None,
            "closed_at": float(data.get("closed_at") or 0),
            "added_users": [_to_int(u) for u in (data.get("added_users") or []) if _to_int(u)],
            "first_response_at": float(data.get("first_response_at") or 0),
            "first_response_by": _to_int(data.get("first_response_by")) or None,
            "last_activity": float(data.get("last_activity") or data.get("created_at") or 0),
            "sla_alerted": bool(data.get("sla_alerted", False)),
            "rating": max(0, min(5, _to_int(data.get("rating")))),
            "rated_at": float(data.get("rated_at") or 0),
            "closed_reason": str(data.get("closed_reason") or "")[:100],
            "topik": str(data.get("topik") or "")[:TICKET_TOPIC_LEN],
            "notes": [
                {
                    "teks": str(item.get("teks") or "")[:TICKET_NOTE_LEN],
                    "oleh": _to_int(item.get("oleh")),
                    "at": float(item.get("at") or 0),
                }
                for item in (data.get("notes") or [])
                if isinstance(item, dict) and str(item.get("teks") or "").strip()
            ][-TICKET_NOTE_MAX:],
        }
        _ticket_seq[gid] = max(_ticket_seq.get(gid, 0), number)
    return len(ticket_guilds)


async def save_tickets_to_disk() -> None:
    """Menyimpan konfigurasi & data tiket secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            guilds_payload = {}
            for gid, cfg in ticket_guilds.items():
                item = dict(cfg)
                item["seq"] = _ticket_seq.get(gid, 0)
                guilds_payload[str(gid)] = item
            payload = {
                "guilds": guilds_payload,
                "tickets": {str(k): v for k, v in tickets.items()},
            }
            tmp_file = Path(str(TICKETS_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, TICKETS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan tickets.json: %s", sanitize_error_message(exc))


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def get_ticket_config(guild_id: int) -> dict:
    cfg = ticket_guilds.get(int(guild_id))
    if cfg is None:
        cfg = default_config()
        ticket_guilds[int(guild_id)] = cfg
    return cfg


def is_ticket_enabled(guild_id: int) -> bool:
    cfg = ticket_guilds.get(int(guild_id))
    return bool(cfg and cfg.get("enabled"))


def set_ticket_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    panel_channel_id: int | None = None,
    panel_message_id: int | None = None,
    staff_role_id: int | None = None,
    category_id: int | None = None,
    log_channel_id: int | None = None,
    max_open: int | None = None,
    ping_staff: bool | None = None,
    rating_aktif: bool | None = None,
    sla_jam: int | None = None,
    auto_close_jam: int | None = None,
    sla_channel_id: int | None = None,
) -> dict:
    """Mengubah konfigurasi panel tiket server."""
    cfg = get_ticket_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if panel_channel_id is not None:
        cfg["panel_channel_id"] = int(panel_channel_id) or None
    if panel_message_id is not None:
        cfg["panel_message_id"] = int(panel_message_id) or None
    if staff_role_id is not None:
        cfg["staff_role_id"] = int(staff_role_id) or None
    if category_id is not None:
        cfg["category_id"] = int(category_id) or None
    if log_channel_id is not None:
        cfg["log_channel_id"] = int(log_channel_id) or None
    if max_open is not None:
        cfg["max_open"] = max(1, min(10, int(max_open)))
    if ping_staff is not None:
        cfg["ping_staff"] = bool(ping_staff)
    if rating_aktif is not None:
        cfg["rating_aktif"] = bool(rating_aktif)
    if sla_jam is not None:
        cfg["sla_jam"] = max(0, min(720, int(sla_jam)))
    if auto_close_jam is not None:
        cfg["auto_close_jam"] = max(0, min(720, int(auto_close_jam)))
    if sla_channel_id is not None:
        cfg["sla_channel_id"] = int(sla_channel_id) or None
    return cfg


def disable_tickets(guild_id: int) -> bool:
    cfg = ticket_guilds.get(int(guild_id))
    if cfg is None:
        return False
    cfg["enabled"] = False
    return True


def next_ticket_number(guild_id: int) -> int:
    gid = int(guild_id)
    _ticket_seq[gid] = int(_ticket_seq.get(gid, 0)) + 1
    return _ticket_seq[gid]


# ==============================================================================
# SIKLUS HIDUP TIKET
# ==============================================================================
def open_ticket_count(guild_id: int, user_id: int) -> int:
    return sum(
        1
        for data in tickets.values()
        if data.get("guild_id") == int(guild_id)
        and data.get("user_id") == int(user_id)
        and data.get("status") in ("terbuka", "diklaim")
    )


def can_open_ticket(guild_id: int, user_id: int) -> tuple[bool, str]:
    """Memeriksa batas tiket terbuka per member."""
    cfg = get_ticket_config(guild_id)
    limit = int(cfg.get("max_open") or TICKET_MAX_OPEN_PER_USER)
    active = open_ticket_count(guild_id, user_id)
    if active >= limit:
        return False, (
            f"⚠️ Kamu masih punya **{active} tiket aktif** (batas `{limit}`). "
            "Selesaikan dulu tiket lamamu sebelum membuka yang baru."
        )
    return True, ""


def register_ticket(
    thread_id: int,
    guild_id: int,
    user_id: int,
    *,
    topic: str = "",
    topik: str = "",
    now: float | None = None,
) -> dict:
    """Mencatat tiket baru setelah thread berhasil dibuat."""
    gid = int(guild_id)
    number = next_ticket_number(gid)
    data = {
        "thread_id": int(thread_id),
        "guild_id": gid,
        "user_id": int(user_id),
        "number": number,
        "status": "terbuka",
        "topic": str(topic or "")[:200],
        "created_at": time.time() if now is None else float(now),
        "claimed_by": None,
        "closed_by": None,
        "closed_at": 0.0,
        "added_users": [],
        "first_response_at": 0.0,
        "first_response_by": None,
        "last_activity": time.time() if now is None else float(now),
        "sla_alerted": False,
        "rating": 0,
        "rated_at": 0.0,
        "closed_reason": "",
        "topik": str(topik or "")[:TICKET_TOPIC_LEN],
        "notes": [],
    }
    tickets[int(thread_id)] = data
    cfg = get_ticket_config(gid)
    cfg["opened"] = int(cfg.get("opened") or 0) + 1
    return data


def get_ticket(thread_id: int) -> dict | None:
    return tickets.get(int(thread_id))


def claim_ticket(thread_id: int, staff_id: int) -> tuple[str, dict | None]:
    """Menandai tiket sedang ditangani staf. Status: `ok`, `sudah`, `selesai`, `tidak_ada`."""
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    if data.get("status") == "selesai":
        return "selesai", data
    if data.get("claimed_by") == int(staff_id):
        return "sudah", data
    data["claimed_by"] = int(staff_id)
    data["status"] = "diklaim"
    return "ok", data


def close_ticket(
    thread_id: int,
    closed_by: int,
    *,
    now: float | None = None,
    reason: str = "manual",
) -> tuple[str, dict | None]:
    """Menutup tiket. Status: `ok`, `selesai`, `tidak_ada`."""
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    if data.get("status") == "selesai":
        return "selesai", data
    data["status"] = "selesai"
    data["closed_by"] = int(closed_by)
    data["closed_at"] = time.time() if now is None else float(now)
    data["closed_reason"] = str(reason or "manual")[:100]
    cfg = get_ticket_config(data["guild_id"])
    cfg["closed"] = int(cfg.get("closed") or 0) + 1
    return "ok", data


def add_user_to_ticket(thread_id: int, user_id: int) -> bool:
    data = tickets.get(int(thread_id))
    if data is None:
        return False
    added = data.setdefault("added_users", [])
    if int(user_id) in added:
        return False
    added.append(int(user_id))
    return True


def normalize_topics(topics) -> list[dict]:
    """Rapikan daftar topik tiket: nama unik, role/emoji opsional, dibatasi jumlahnya."""
    hasil: list[dict] = []
    for item in topics or []:
        if not isinstance(item, dict):
            continue
        nama = str(item.get("nama") or "").strip()[:TICKET_TOPIC_LEN]
        if not nama or any(t["nama"].lower() == nama.lower() for t in hasil):
            continue
        hasil.append(
            {
                "nama": nama,
                "emoji": str(item.get("emoji") or "").strip()[:32],
                "staff_role_id": _to_int(item.get("staff_role_id")) or 0,
                "deskripsi": str(item.get("deskripsi") or "").strip()[:100],
            }
        )
        if len(hasil) >= TICKET_TOPIC_MAX:
            break
    return hasil


def list_ticket_topics(guild_id: int) -> list[dict]:
    """Semua topik tiket server (kosong = satu topik umum)."""
    cfg = ticket_guilds.get(int(guild_id)) or {}
    return list(cfg.get("topics") or [])


def set_ticket_topics(guild_id: int, topics) -> list[dict]:
    """Ganti seluruh daftar topik satu server."""
    cfg = get_ticket_config(int(guild_id))
    cfg["topics"] = normalize_topics(topics)
    return list(cfg["topics"])


def find_topic(guild_id: int, nama: str) -> dict | None:
    """Cari topik berdasarkan nama (tidak peka huruf besar/kecil)."""
    kunci = str(nama or "").strip().lower()
    if not kunci:
        return None
    for item in list_ticket_topics(guild_id):
        if str(item.get("nama") or "").lower() == kunci:
            return item
    return None


def add_ticket_topic(
    guild_id: int,
    nama: str,
    *,
    emoji: str = "",
    staff_role_id: int = 0,
    deskripsi: str = "",
) -> tuple[bool, str]:
    """Tambah (atau perbarui) satu topik. `(berhasil, pesan)`."""
    gid = int(guild_id)
    label = str(nama or "").strip()[:TICKET_TOPIC_LEN]
    if not label:
        return False, "Nama topik tidak boleh kosong."
    daftar = list_ticket_topics(gid)
    baru = {
        "nama": label,
        "emoji": str(emoji or "").strip()[:32],
        "staff_role_id": _to_int(staff_role_id),
        "deskripsi": str(deskripsi or "").strip()[:100],
    }
    posisi = next(
        (i for i, item in enumerate(daftar) if item["nama"].lower() == label.lower()), None
    )
    if posisi is None:
        if len(daftar) >= TICKET_TOPIC_MAX:
            return False, f"Topik sudah penuh (maksimal {TICKET_TOPIC_MAX}). Hapus satu dulu."
        daftar.append(baru)
        pesan = f"Topik **{label}** ditambahkan."
    else:
        daftar[posisi] = baru
        pesan = f"Topik **{label}** diperbarui."
    set_ticket_topics(gid, daftar)
    return True, pesan


def remove_ticket_topic(guild_id: int, nama: str) -> tuple[bool, str]:
    """Hapus satu topik berdasarkan nama."""
    gid = int(guild_id)
    kunci = str(nama or "").strip().lower()
    daftar = list_ticket_topics(gid)
    sisa = [item for item in daftar if str(item.get("nama") or "").lower() != kunci]
    if len(sisa) == len(daftar):
        return False, f"Topik `{nama}` tidak ditemukan."
    set_ticket_topics(gid, sisa)
    return True, f"Topik `{nama}` dihapus."


def topic_staff_role(guild_id: int, topik: str) -> int:
    """Role staf khusus satu topik (0 = pakai role staf umum)."""
    data = find_topic(guild_id, topik)
    return _to_int((data or {}).get("staff_role_id"))


def add_note(thread_id: int, author_id: int, teks: str, *, now: float | None = None) -> tuple[str, dict | None]:
    """Tambah catatan internal staf. Status: `ok`, `kosong`, `penuh`, `tidak_ada`."""
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    isi = str(teks or "").strip()
    if not isi:
        return "kosong", data
    catatan = data.setdefault("notes", [])
    if len(catatan) >= TICKET_NOTE_MAX:
        return "penuh", data
    catatan.append(
        {
            "teks": isi[:TICKET_NOTE_LEN],
            "oleh": int(author_id or 0),
            "at": time.time() if now is None else float(now),
        }
    )
    return "ok", data


def list_notes(thread_id: int) -> list[dict]:
    """Catatan internal satu tiket (terlama lebih dulu)."""
    data = tickets.get(int(thread_id)) or {}
    return list(data.get("notes") or [])


def remove_note(thread_id: int, nomor: int) -> tuple[str, dict | None]:
    """Hapus catatan nomor ke-`nomor` (1 = paling lama). Status: `ok`, `tidak_ada`."""
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    catatan = data.get("notes") or []
    posisi = int(nomor) - 1
    if posisi < 0 or posisi >= len(catatan):
        return "tidak_ada", data
    catatan.pop(posisi)
    data["notes"] = catatan
    return "ok", data


def can_view_ticket(data: dict, user_id: int) -> bool:
    """Pembuat tiket & member yang ditambahkan boleh melihat tiketnya."""
    if data is None:
        return False
    return int(user_id) in (int(data.get("user_id") or 0), *(int(u) for u in data.get("added_users") or []))


def count_open(guild_id: int) -> int:
    """Jumlah tiket yang belum ditutup (dipakai channel statistik server)."""
    return sum(
        1
        for data in tickets.values()
        if int(data.get("guild_id") or 0) == int(guild_id) and data.get("status") != "selesai"
    )


def list_tickets(guild_id: int, *, status: str | None = None, limit: int = 15) -> list[dict]:
    items = [
        data
        for data in tickets.values()
        if data.get("guild_id") == int(guild_id) and (status is None or data.get("status") == status)
    ]
    items.sort(key=lambda d: float(d.get("created_at") or 0), reverse=True)
    return items[:limit]


def record_activity(thread_id: int, *, now: float | None = None) -> bool:
    """Memperbarui waktu aktivitas terakhir tiket (dipakai auto-close)."""
    data = tickets.get(int(thread_id))
    if data is None or data.get("status") == "selesai":
        return False
    data["last_activity"] = time.time() if now is None else float(now)
    return True


def record_first_response(thread_id: int, staff_id: int, *, now: float | None = None) -> bool:
    """Mencatat respons staf pertama (SLA). Mengembalikan True bila baru dicatat."""
    data = tickets.get(int(thread_id))
    if data is None or data.get("status") == "selesai":
        return False
    if float(data.get("first_response_at") or 0) > 0:
        return False
    data["first_response_at"] = time.time() if now is None else float(now)
    data["first_response_by"] = int(staff_id)
    data["status"] = "diklaim" if data.get("status") == "terbuka" else data.get("status")
    data.setdefault("claimed_by", int(staff_id))
    data["claimed_by"] = data.get("claimed_by") or int(staff_id)
    return True


def is_staff_member(member, cfg: dict | None = None) -> bool:
    """Apakah member ini staf (izin kelola thread/channel, admin, atau role staf)."""
    perms = getattr(member, "guild_permissions", None)
    if perms is not None and (
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_threads", False)
        or getattr(perms, "manage_channels", False)
    ):
        return True
    role_id = _to_int((cfg or {}).get("staff_role_id"))
    if role_id:
        return role_id in {_to_int(getattr(role, "id", 0)) for role in (getattr(member, "roles", None) or [])}
    return False


def maybe_track_ticket_message(message) -> bool:
    """Mencatat aktivitas & respons pertama staf dari sebuah pesan. `(perubahan?)`."""
    channel = getattr(message, "channel", None)
    tid = _to_int(getattr(channel, "id", 0))
    data = tickets.get(tid)
    if data is None or data.get("status") == "selesai":
        return False
    author = getattr(message, "author", None)
    if author is None or getattr(author, "bot", False):
        return False

    changed = record_activity(tid)
    if _to_int(getattr(author, "id", 0)) == _to_int(data.get("user_id")):
        return changed
    cfg = get_ticket_config(data["guild_id"])
    if is_staff_member(author, cfg) and record_first_response(tid, author.id):
        changed = True
    return changed


def sla_overdue(
    *,
    hours: int | None = None,
    guild_id: int | None = None,
    now: float | None = None,
) -> list[int]:
    """Tiket aktif yang belum direspons staf melewati batas SLA (per server)."""
    current = time.time() if now is None else float(now)
    overdue: list[int] = []
    for tid, data in tickets.items():
        if data.get("status") not in ("terbuka", "diklaim"):
            continue
        if float(data.get("first_response_at") or 0) > 0:
            continue
        if guild_id is not None and int(data.get("guild_id") or 0) != int(guild_id):
            continue
        cfg = get_ticket_config(data["guild_id"])
        limit_hours = _to_int(cfg.get("sla_jam"), 0) if hours is None else int(hours)
        if limit_hours <= 0:
            continue
        if current - float(data.get("created_at") or 0) >= limit_hours * 3600:
            overdue.append(tid)
    return overdue


def mark_sla_alerted(thread_id: int) -> bool:
    data = tickets.get(int(thread_id))
    if data is None or data.get("sla_alerted"):
        return False
    data["sla_alerted"] = True
    cfg = get_ticket_config(data["guild_id"])
    cfg["sla_alerted"] = _to_int(cfg.get("sla_alerted")) + 1
    return True


def rate_ticket(
    thread_id: int,
    stars: int,
    *,
    user_id: int | None = None,
    now: float | None = None,
) -> tuple[str, dict | None]:
    """Memberi rating bintang (1–5) untuk tiketnya.

    Status: `ok`, `sudah`, `belum_selesai`, `bukan_pemilik`, `tidak_valid`, `tidak_ada`.
    """
    data = tickets.get(int(thread_id))
    if data is None:
        return "tidak_ada", None
    score = _to_int(stars)
    if score < 1 or score > 5:
        return "tidak_valid", data
    if user_id is not None and _to_int(user_id) != _to_int(data.get("user_id")):
        return "bukan_pemilik", data
    if data.get("status") != "selesai":
        return "belum_selesai", data
    if _to_int(data.get("rating")) > 0:
        return "sudah", data

    data["rating"] = score
    data["rated_at"] = time.time() if now is None else float(now)
    cfg = get_ticket_config(data["guild_id"])
    cfg["rating_sum"] = _to_int(cfg.get("rating_sum")) + score
    cfg["rating_count"] = _to_int(cfg.get("rating_count")) + 1
    return "ok", data


def rating_summary(guild_id: int) -> dict:
    """Ringkasan rating bintang server: jumlah, rata-rata, & sebaran."""
    rated = [
        _to_int(d.get("rating"))
        for d in tickets.values()
        if _to_int(d.get("guild_id")) == int(guild_id) and _to_int(d.get("rating")) > 0
    ]
    distribution = {star: rated.count(star) for star in range(1, 6)}
    cfg = get_ticket_config(guild_id)
    count = len(rated) or _to_int(cfg.get("rating_count"))
    total = sum(rated) or _to_int(cfg.get("rating_sum"))
    closed = _to_int(cfg.get("closed")) or 0
    return {
        "count": count,
        "sum": total,
        "average": round(total / count, 2) if count else 0.0,
        "distribution": distribution,
        "response_rate": round(count / closed * 100) if closed else 0,
    }


def sla_stats(guild_id: int) -> dict:
    """Statistik SLA: tiket dengan respons pertama & rata-rata waktu respons (menit)."""
    gid = int(guild_id)
    responded = []
    pending = 0
    for data in tickets.values():
        if _to_int(data.get("guild_id")) != gid:
            continue
        if data.get("status") not in ("terbuka", "diklaim", "selesai"):
            continue
        first = float(data.get("first_response_at") or 0)
        if first > 0:
            responded.append(max(0.0, first - float(data.get("created_at") or first)))
        elif data.get("status") in ("terbuka", "diklaim"):
            pending += 1
    return {
        "responded": len(responded),
        "pending": pending,
        "avg_minutes": round(sum(responded) / len(responded) / 60) if responded else 0,
    }


def stale_tickets(
    *,
    hours: int | None = None,
    guild_id: int | None = None,
    now: float | None = None,
) -> list[int]:
    """Tiket kedaluwarsa (bila auto-close diaktifkan Admin).

    `hours=None` memakai pengaturan `auto_close_jam` per server; aktivitas terakhir
    (pesan terbaru) dipakai agar tiket yang masih dibalas tidak ikut ditutup.
    """
    current = time.time() if now is None else float(now)
    result: list[int] = []
    for tid, data in tickets.items():
        if data.get("status") not in ("terbuka", "diklaim"):
            continue
        if guild_id is not None and _to_int(data.get("guild_id")) != int(guild_id):
            continue
        limit_hours = _to_int(get_ticket_config(data["guild_id"]).get("auto_close_jam")) if hours is None else int(hours)
        if limit_hours <= 0:
            continue
        last = float(data.get("last_activity") or data.get("created_at") or 0)
        if last < current - limit_hours * 3600:
            result.append(tid)
    return result


# ==============================================================================
# TAMPILAN
# ==============================================================================
def build_panel_embed(guild_name: str = "", *, staff_role_id: int | None = None) -> discord.Embed:
    """Embed panel pembuatan tiket."""
    embed = discord.Embed(
        title="🎟️ Pusat Bantuan Server",
        description=(
            "Butuh bantuan staf, laporan bug, atau pertanyaan yang butuh data pribadi?\n"
            "Tekan tombol **Buat Tiket** di bawah — bot akan membuatkan **thread privat** "
            "yang hanya bisa dilihat kamu & staf.\n\n"
            "**Tips agar cepat ditangani**\n"
            "• Jelaskan masalahnya langsung di thread (sertakan screenshot bila perlu).\n"
            "• Jangan membuka tiket ganda untuk masalah yang sama.\n"
            "• Tiket akan diarsipkan otomatis setelah selesai."
        ),
        color=discord.Color.blurple(),
    )
    if staff_role_id:
        embed.add_field(name="👥 Petugas", value=f"<@&{staff_role_id}>", inline=False)
    embed.set_footer(text="Tanpa AI & tanpa kuota Gemini • hanya membuat thread, bukan channel baru")
    if guild_name:
        embed.title = f"🎟️ Pusat Bantuan {guild_name}"[:256]
    return embed


def build_ticket_embed(data: dict, *, staff_role_id: int | None = None) -> discord.Embed:
    """Embed pembuka di dalam thread tiket."""
    status = TICKET_STATUS.get(str(data.get("status")), TICKET_STATUS["terbuka"])
    embed = discord.Embed(
        title=f"🎟️ Tiket #{data.get('number', 0):04d}",
        description=(
            f"Terima kasih <@{data.get('user_id')}>! Tiketmu sudah dibuat.\n"
            "Tulis detail masalahmu di thread ini, lalu staf akan segera merespons."
        ),
        color=discord.Color.green() if data.get("status") != "selesai" else discord.Color.dark_gray(),
    )
    embed.add_field(name="📌 Status", value=status, inline=True)
    topik = str(data.get("topik") or "").strip()
    nilai_topik = str(data.get("topic") or "_(tidak diisi)_")[:200]
    if topik:
        nilai_topik = f"**{topik}** · {nilai_topik}"[:200]
    embed.add_field(name="🗂️ Topik", value=nilai_topik, inline=True)
    claimed = data.get("claimed_by")
    embed.add_field(name="🙋 Ditangani", value=f"<@{claimed}>" if claimed else "_belum ada_", inline=True)
    if staff_role_id:
        embed.add_field(name="👥 Staf", value=f"<@&{staff_role_id}>", inline=False)
    embed.set_footer(text="Gunakan tombol 🔒 Tutup Tiket bila masalah sudah selesai")
    return embed


def build_ticket_status_embed(guild_id: int, guild=None) -> discord.Embed:
    """Ringkasan konfigurasi & statistik tiket server."""
    cfg = ticket_guilds.get(int(guild_id))
    if not cfg or not cfg.get("enabled"):
        return discord.Embed(
            title="🎟️ Tiket Dukungan: NONAKTIF",
            description=(
                "Sistem tiket belum aktif di server ini.\n"
                "Pasang dengan `/tiket panel channel:#bantuan staff_role:@Staf`."
            ),
            color=discord.Color.dark_gray(),
        )

    panel_channel = cfg.get("panel_channel_id")
    log_channel = cfg.get("log_channel_id")
    embed = discord.Embed(
        title="🎟️ Sistem Tiket Dukungan",
        description=f"Status: **{'✅ Aktif' if cfg.get('enabled') else '⛔ Nonaktif'}**",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="📍 Panel",
        value=f"<#{panel_channel}>" if panel_channel else "_belum dipasang_",
        inline=True,
    )
    embed.add_field(
        name="👥 Role Staf",
        value=f"<@&{cfg['staff_role_id']}>" if cfg.get("staff_role_id") else "_belum diatur_",
        inline=True,
    )
    embed.add_field(
        name="📝 Log Transkrip",
        value=f"<#{log_channel}>" if log_channel else "_belum diatur_",
        inline=True,
    )
    active = [d for d in tickets.values() if d.get("guild_id") == int(guild_id) and d.get("status") in ("terbuka", "diklaim")]
    embed.add_field(
        name="📊 Statistik",
        value=(
            f"• Tiket aktif: `{len(active)}`\n"
            f"• Total dibuka: `{cfg.get('opened', 0)}`\n"
            f"• Total selesai: `{cfg.get('closed', 0)}`\n"
            f"• Batas per member: `{cfg.get('max_open', TICKET_MAX_OPEN_PER_USER)}`"
        ),
        inline=False,
    )
    if active:
        lines = []
        for data in sorted(active, key=lambda d: float(d.get("created_at") or 0), reverse=True)[:8]:
            lines.append(
                f"• `#{data['number']:04d}` <@{data['user_id']}> — {TICKET_STATUS.get(data['status'], '-')}"
            )
        embed.add_field(name="🟢 Tiket Aktif", value="\n".join(lines)[:1024], inline=False)
    rating = rating_summary(guild_id)
    sla = sla_stats(guild_id)
    rating = rating_summary(guild_id)
    sla = sla_stats(guild_id)
    sla_line = (
        "nonaktif"
        if not _to_int(cfg.get("sla_jam"))
        else f"aktif — {sla['pending']} tiket menunggu"
    )
    auto_line = "nonaktif" if not _to_int(cfg.get("auto_close_jam")) else "aktif"
    embed.add_field(
        name="⭐ Layanan",
        value=(
            f"• Rating: **{rating['average']} / 5** (`{rating['count']}` penilaian)\n"
            f"• SLA respons pertama ({_to_int(cfg.get('sla_jam'))} jam): {sla_line}\n"
            f"• Auto-close ({_to_int(cfg.get('auto_close_jam'))} jam): {auto_line}"
        ),
        inline=False,
    )
    embed.set_footer(text="Tiket dibuat sebagai thread privat, bukan channel baru")
    return embed


# ==============================================================================
# TRANSKRIP
# ==============================================================================
def build_transcript(data: dict, messages: list, *, max_lines: int = TICKET_MAX_TRANSCRIPT_LINES) -> tuple[str, str]:
    """Menyusun transkrip teks tiket. Mengembalikan `(isi, nama_berkas)`."""
    base_name = f"tiket-{int(data.get('number') or 0):04d}"
    header = [
        f"TRANSKRIP TIKET #{int(data.get('number') or 0):04d}",
        "=" * 48,
        f"Server     : {data.get('guild_id')}",
        f"Pembuat    : {data.get('user_id')}",
        f"Topik      : {data.get('topic') or '-'}",
        f"Dibuka     : {_format_time(data.get('created_at'))}",
        f"Ditutup    : {_format_time(data.get('closed_at')) if data.get('closed_at') else '-'}",
        f"Ditutup oleh: {data.get('closed_by') or '-'}",
        f"Ditangani  : {data.get('claimed_by') or '-'}",
        "",
        "ISI PERCAKAPAN",
        "-" * 48,
    ]
    lines = list(header)
    for message in list(messages)[-max(1, int(max_lines)):]:
        author = getattr(getattr(message, "author", None), "display_name", None) or "?"
        when = _format_time(getattr(message, "created_at", None))
        content = str(getattr(message, "content", "") or "")
        attachments = getattr(message, "attachments", None) or []
        if attachments:
            links = " ".join(str(getattr(item, "url", "")) for item in attachments)
            content = f"{content} [lampiran: {links}]".strip()
        lines.append(f"[{when}] {author}: {content}")
    lines.append("")
    lines.append("=" * 48)
    lines.append("Dibuat otomatis oleh bot • tanpa AI & tanpa kuota Gemini")
    text = "\n".join(lines)[:180_000]
    return text, f"{base_name}.txt"


def _format_time(value) -> str:
    if not value:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(value)))
    except (TypeError, ValueError, OSError):
        return "-"


async def collect_thread_messages(thread, *, limit: int = TICKET_MAX_TRANSCRIPT_LINES) -> list:
    """Mengambil riwayat pesan thread (aman bila izin baca history kurang)."""
    history = getattr(thread, "history", None)
    if not callable(history):
        return []
    collected = []
    try:
        async for message in history(limit=min(1000, max(10, int(limit))), oldest_first=True):
            collected.append(message)
    except (discord.Forbidden, discord.HTTPException) as exc:  # pragma: no cover - izin kurang
        logger.info("Gagal membaca riwayat tiket: %s", sanitize_error_message(exc))
    return collected


def transcript_file(text: str, filename: str) -> discord.File:
    """Membungkus transkrip menjadi `discord.File`."""
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=filename)


async def send_transcript(bot, data: dict, text: str, filename: str) -> bool:
    """Mengirim transkrip ke channel log server (bila diatur)."""
    cfg = ticket_guilds.get(int(data.get("guild_id") or 0)) or {}
    ids = channel_targets.daftar(cfg, "log_channel_id")
    if not ids:
        return False

    async def _kirim_satu(channel):
        await channel.send(
            content=(
                f"📄 Transkrip tiket `#{int(data.get('number') or 0):04d}` "
                f"milik <@{data.get('user_id')}> sudah ditutup."
            ),
            file=transcript_file(text, filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    try:
        return bool(await channel_targets.sebarkan(bot, ids, _kirim_satu))
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal mengirim transkrip tiket: %s", sanitize_error_message(exc))
        return False


def handle_channel_delete(channel) -> bool:
    """Membersihkan konfigurasi tiket saat channel terkait dihapus."""
    cid = _to_int(getattr(channel, "id", 0))
    changed = False
    for cfg in ticket_guilds.values():
        if cfg.get("panel_channel_id") == cid:
            cfg["panel_channel_id"] = None
            cfg["panel_message_id"] = None
            changed = True
        if cfg.get("log_channel_id") == cid:
            cfg["log_channel_id"] = None
            changed = True
        if cfg.get("category_id") == cid:
            cfg["category_id"] = None
            changed = True
    return changed


def handle_thread_delete(thread_id: int) -> bool:
    """Membuang catatan tiket saat thread-nya dihapus manual."""
    return tickets.pop(int(thread_id), None) is not None


# ==============================================================================
# PENGAWAS SLA & AUTO-CLOSE (v1.33.0-beta) — 0 kuota AI
# ==============================================================================
def build_sla_embed(guild, thread_ids: list[int], hours: int) -> discord.Embed:
    """Laporan tiket yang belum direspons staf melewati batas SLA."""
    lines = []
    for tid in thread_ids[:10]:
        data = tickets.get(tid) or {}
        lines.append(
            f"• `#{_to_int(data.get('number')):04d}` <@{_to_int(data.get('user_id'))}> — "
            f"dibuat <t:{int(float(data.get('created_at') or 0))}:R>"
        )
    embed = discord.Embed(
        title="⏰ SLA Terlampaui — belum ada respons staf",
        description=(
            f"`{len(thread_ids)}` tiket melewati batas **{hours} jam** tanpa respons pertama.\n"
            + "\n".join(lines)
            + ("\n… dan tiket lainnya." if len(thread_ids) > 10 else "")
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="SLA Tiket • 0 kuota AI • atur batas lewat /tiket atur")
    return embed


def _alert_channel(bot, guild, cfg: dict):
    for key in ("sla_channel_id", "log_channel_id"):
        cid = _to_int(cfg.get(key))
        if cid and callable(getattr(bot, "get_channel", None)):
            channel = bot.get_channel(cid)
            if channel is not None and hasattr(channel, "send"):
                return channel
    channel = getattr(guild, "system_channel", None)
    return channel if channel is not None and hasattr(channel, "send") else None


async def run_ticket_check(bot) -> dict:
    """Dipanggil berkala: kirim peringatan SLA & tutup tiket yang lama menganggur."""
    result = {"sla": 0, "closed": 0}
    guilds = {
        _to_int(data.get("guild_id"))
        for data in tickets.values()
        if data.get("status") in ("terbuka", "diklaim")
    }
    for gid in guilds:
        if not gid:
            continue
        guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
        if guild is None:
            continue
        cfg = get_ticket_config(gid)

        # 1. SLA respons pertama
        hours = _to_int(cfg.get("sla_jam"))
        if hours > 0:
            overdue = [tid for tid in sla_overdue(hours=hours, guild_id=gid) if mark_sla_alerted(tid)]
            if overdue:
                channel = _alert_channel(bot, guild, cfg)
                if channel is not None:
                    try:
                        await channel.send(
                            embed=build_sla_embed(guild, overdue, hours),
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                        result["sla"] += len(overdue)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        # 2. Auto-close tiket yang menganggur
        for tid in stale_tickets(guild_id=gid):
            thread = None
            if callable(getattr(bot, "get_channel", None)):
                thread = bot.get_channel(tid)
            status, closed = close_ticket(tid, 0, reason="otomatis (menganggur)")
            if closed is None:
                continue
            cfg["auto_closed"] = _to_int(cfg.get("auto_closed")) + 1
            result["closed"] += 1
            if thread is not None:
                try:
                    import ticket_archive

                    pesan_arsip = await collect_thread_messages(thread)
                    ticket_archive.simpan(
                        closed, pesan_arsip, guild_name=str(getattr(guild, "name", "") or "")
                    )
                except Exception:  # pragma: no cover - arsip opsional
                    pass
                try:
                    await thread.send(
                        f"⏰ Tiket ditutup **otomatis** karena tidak ada aktivitas selama "
                        f"`{_to_int(cfg.get('auto_close_jam'))}` jam. "
                        "Buka tiket baru kapan saja bila masih butuh bantuan."
                    )
                except (discord.Forbidden, discord.HTTPException, AttributeError):
                    pass
                try:
                    await thread.edit(
                        name=f"tiket-{_to_int(closed.get('number')):04d}-otomatis"[:100],
                        locked=True,
                        archived=True,
                        reason="Auto-close tiket menganggur",
                    )
                except (discord.Forbidden, discord.HTTPException, AttributeError):
                    pass

    if result["sla"] or result["closed"]:
        await save_tickets_to_disk()
    return result


def cleanup_tickets_runtime(*, max_closed: int = 200) -> int:
    """Membatasi jumlah tiket selesai yang disimpan agar JSON tetap kecil."""
    closed = [
        (tid, float(data.get("closed_at") or 0))
        for tid, data in tickets.items()
        if data.get("status") == "selesai"
    ]
    if len(closed) <= max_closed:
        return 0
    closed.sort(key=lambda pair: pair[1])
    removed = 0
    for tid, _ in closed[: len(closed) - max_closed]:
        tickets.pop(tid, None)
        removed += 1
    return removed
