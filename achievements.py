"""Achievements — lencana bertingkat dari data yang **sudah** kita catat (0 kuota AI).

Tidak ada pelacakan baru yang berat: semua angka diambil dari modul yang sudah ada.

| Lencana | Sumber data | Tingkat |
| :--- | :--- | :--- |
| 💬 **Rajin Ngobrol** | `levels` → jumlah pesan | 50 · 250 · 1.000 · 5.000 · 15.000 |
| 🎙️ **Penghuni Voice** | `levels` → total menit voice | 60 · 300 · 1.200 · 5.000 |
| 📈 **Pendaki Level** | `levels` → level | 5 · 10 · 25 · 50 |
| 🎉 **Hoki Undian** | `engagement` → riwayat pemenang | 1 · 3 · 10 |

Setiap tingkat bisa diberi **role hadiah** (`rewards["chat:2"] = role_id`).
Data tersimpan di `data/achievements.json` — 1 proses, JSON, tanpa database.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from config import ACHIEVEMENTS_FILE, DATA_DIR

logger = logging.getLogger("gemini_bot.achievements")

#: Definisi lencana (urutan = urutan tampil).
ACHIEVEMENTS: tuple[dict, ...] = (
    {
        "kunci": "chat",
        "label": "Rajin Ngobrol",
        "emoji": "💬",
        "satuan": "pesan",
        "tingkat": (50, 250, 1000, 5000, 15000),
    },
    {
        "kunci": "voice",
        "label": "Penghuni Voice",
        "emoji": "🎙️",
        "satuan": "menit voice",
        "tingkat": (60, 300, 1200, 5000),
    },
    {
        "kunci": "level",
        "label": "Pendaki Level",
        "emoji": "📈",
        "satuan": "level",
        "tingkat": (5, 10, 25, 50),
    },
    {
        "kunci": "giveaway",
        "label": "Hoki Undian",
        "emoji": "🎉",
        "satuan": "kali menang",
        "tingkat": (1, 3, 10),
    },
)

ACHIEVEMENT_MAP: dict[str, dict] = {item["kunci"]: item for item in ACHIEVEMENTS}

MAX_MEMBER_PER_GUILD = 500

#: {guild_id: {"enabled": bool, "channel_id": int|None, "rewards": {"chat:2": role_id}}}
ach_config: dict[int, dict] = {}
#: {guild_id: {user_id: {"chat": 2, "voice": 0, ...}}}
ach_members: dict[int, dict[int, dict]] = {}

_lock = asyncio.Lock()

#: Cache jumlah kemenangan undian per server: {gid: (dibuat, {uid: jumlah})}
_cache_menang: dict[int, tuple[float, dict[int, int]]] = {}
_CACHE_MENANG_SEC = 60


# ==============================================================================
# PENGATURAN
# ==============================================================================
def default_config() -> dict:
    """Setelan awal: lencana aktif, tanpa channel pengumuman & tanpa role hadiah."""
    return {"enabled": True, "channel_id": None, "rewards": {}}


def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def get_config(guild_id: int) -> dict:
    gid = _to_int(guild_id)
    cfg = ach_config.get(gid)
    if cfg is None:
        cfg = default_config()
        ach_config[gid] = cfg
    return cfg


def peek_config(guild_id: int) -> dict:
    """Baca setelan tanpa membuat entri baru (dipakai dashboard)."""
    cfg = ach_config.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    channel_id: int | None = None,
) -> dict:
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if channel_id is not None:
        cfg["channel_id"] = _to_int(channel_id) or None
    return cfg


def set_reward(guild_id: int, kunci: str, tingkat: int, role_id: int | None) -> tuple[bool, str]:
    """Pasang/hapus role hadiah untuk satu tingkat lencana."""
    kunci = str(kunci or "").strip().lower()
    item = ACHIEVEMENT_MAP.get(kunci)
    if item is None:
        return False, f"Lencana `{kunci or '-'}` tidak dikenal."
    tingkat = _to_int(tingkat)
    if not 1 <= tingkat <= len(item["tingkat"]):
        return False, f"Tingkat harus 1–{len(item['tingkat'])} untuk lencana `{kunci}`."

    rewards = get_config(guild_id).setdefault("rewards", {})
    ref = f"{kunci}:{tingkat}"
    if not role_id:
        dihapus = rewards.pop(ref, None) is not None
        return dihapus, (
            f"Role hadiah `{ref}` dihapus." if dihapus else f"Tidak ada role hadiah `{ref}`."
        )
    rewards[ref] = _to_int(role_id)
    return True, (
        f"Role <@&{_to_int(role_id)}> diberikan saat **{item['label']}** mencapai "
        f"tingkat {tingkat} ({item['tingkat'][tingkat - 1]:,} {item['satuan']})."
    )


def role_for(guild_id: int, kunci: str, tingkat: int) -> int:
    """Role hadiah untuk satu tingkat lencana (0 = tidak ada)."""
    rewards = peek_config(guild_id).get("rewards") or {}
    return _to_int(rewards.get(f"{kunci}:{tingkat}"))


# ==============================================================================
# NILAI & PROGRES
# ==============================================================================
def _menang_giveaway(guild_id: int) -> dict[int, int]:
    """Jumlah kemenangan undian per member (dengan cache 60 detik)."""
    import engagement

    gid = _to_int(guild_id)
    sekarang = time.time()
    tersimpan = _cache_menang.get(gid)
    if tersimpan and sekarang - tersimpan[0] < _CACHE_MENANG_SEC:
        return tersimpan[1]

    hasil: dict[int, int] = {}
    for cfg in (getattr(engagement, "giveaways", {}) or {}).values():
        if _to_int(cfg.get("guild_id")) != gid:
            continue
        for riwayat in cfg.get("history") or []:
            for uid in riwayat.get("pemenang") or []:
                peserta = _to_int(uid)
                if peserta:
                    hasil[peserta] = hasil.get(peserta, 0) + 1
    _cache_menang[gid] = (sekarang, hasil)
    return hasil


def nilai_member(guild_id: int, user_id: int) -> dict[str, int]:
    """Angka mentah untuk tiap lencana (dari modul yang sudah ada)."""
    import levels

    data = levels.get_member_level(guild_id, user_id)
    uid = _to_int(user_id)
    menang = _menang_giveaway(guild_id).get(uid, 0)
    return {
        "chat": _to_int(data.get("messages")),
        "voice": levels.voice_minutes(guild_id, user_id),
        "level": _to_int(data.get("level")) + _to_int(data.get("prestige")) * 100,
        "giveaway": menang,
    }


def tingkat_tercapai(kunci: str, nilai: int) -> int:
    """Berapa tingkat lencana yang sudah tercapai dari angka `nilai`."""
    item = ACHIEVEMENT_MAP.get(str(kunci))
    if item is None:
        return 0
    return sum(1 for ambang in item["tingkat"] if int(nilai) >= ambang)


def progres(guild_id: int, user_id: int) -> list[dict]:
    """Progres semua lencana seorang member (untuk `/lencana lihat` & dashboard)."""
    nilai = nilai_member(guild_id, user_id)
    hasil = []
    for item in ACHIEVEMENTS:
        angka = int(nilai.get(item["kunci"], 0))
        tingkat = tingkat_tercapai(item["kunci"], angka)
        berikut = item["tingkat"][tingkat] if tingkat < len(item["tingkat"]) else None
        sebelum = item["tingkat"][tingkat - 1] if tingkat else 0
        persen = (
            min(100, int((angka - sebelum) * 100 / max(1, berikut - sebelum)))
            if berikut
            else 100
        )
        hasil.append(
            {
                "kunci": item["kunci"],
                "label": item["label"],
                "emoji": item["emoji"],
                "nilai": angka,
                "satuan": item["satuan"],
                "tingkat": tingkat,
                "maks": len(item["tingkat"]),
                "berikut": berikut,
                "persen": persen,
            }
        )
    return hasil


def total_lencana(guild_id: int, user_id: int) -> int:
    """Jumlah tingkat lencana yang sudah dikumpulkan seorang member."""
    return sum(tingkat_tercapai(k, v) for k, v in nilai_member(guild_id, user_id).items())


def tersimpan(guild_id: int, user_id: int) -> dict:
    """Tingkat lencana yang **sudah** dicatat (sudah diumumkan & diberi role)."""
    return dict((ach_members.get(_to_int(guild_id)) or {}).get(_to_int(user_id)) or {})


def cek_member(guild_id: int, user_id: int) -> list[dict]:
    """Lencana yang baru naik tingkat → daftar `{kunci, tingkat, ambang, role_id, ...}`.

    Fungsi ini **tidak** menyentuh Discord; pemanggil yang memberi role & mengumumkan.
    """
    gid = _to_int(guild_id)
    uid = _to_int(user_id)
    cfg = peek_config(gid)
    if not cfg.get("enabled", True):
        return []

    nilai = nilai_member(gid, uid)
    tercatat = (ach_members.get(gid) or {}).get(uid) or {}
    baru: list[dict] = []
    for item in ACHIEVEMENTS:
        kunci = item["kunci"]
        sekarang = tingkat_tercapai(kunci, int(nilai.get(kunci, 0)))
        sebelumnya = _to_int(tercatat.get(kunci))
        if sekarang <= sebelumnya:
            continue
        for tingkat in range(sebelumnya + 1, sekarang + 1):
            baru.append(
                {
                    "kunci": kunci,
                    "label": item["label"],
                    "emoji": item["emoji"],
                    "tingkat": tingkat,
                    "maks": len(item["tingkat"]),
                    "ambang": item["tingkat"][tingkat - 1],
                    "satuan": item["satuan"],
                    "role_id": role_for(gid, kunci, tingkat),
                }
            )
        daftar = ach_members.setdefault(gid, {}).setdefault(uid, {})
        daftar[kunci] = sekarang
        daftar["diperbarui"] = time.time()
    if len(ach_members.get(gid) or {}) > MAX_MEMBER_PER_GUILD:
        urut = sorted(
            (ach_members[gid] or {}).items(),
            key=lambda pasangan: float((pasangan[1] or {}).get("diperbarui") or 0),
        )
        for uid_lama, _ in urut[: len(urut) - MAX_MEMBER_PER_GUILD]:
            ach_members[gid].pop(uid_lama, None)
    return baru


def papan(guild_id: int, *, limit: int = 10) -> list[dict]:
    """Papan lencana: siapa mengumpulkan tingkat terbanyak (dari data yang tercatat)."""
    papan_guild = ach_members.get(_to_int(guild_id)) or {}
    baris = []
    for uid, data in papan_guild.items():
        total = sum(_to_int(v) for k, v in data.items() if k != "diperbarui")
        if total:
            baris.append({"user_id": _to_int(uid), "total": total})
    baris.sort(key=lambda d: (-d["total"], d["user_id"]))
    return baris[: max(1, int(limit))]


def statistik(guild_id: int) -> dict:
    """Ringkasan untuk dashboard: anggota terdata, lencana terbanyak, total pemberian."""
    gid = _to_int(guild_id)
    data = ach_members.get(gid) or {}
    total = sum(
        _to_int(v)
        for data_member in data.values()
        for k, v in (data_member or {}).items()
        if k != "diperbarui"
    )
    per_lencana = {item["kunci"]: 0 for item in ACHIEVEMENTS}
    for data_member in data.values():
        for kunci in per_lencana:
            per_lencana[kunci] += _to_int((data_member or {}).get(kunci))
    return {
        "aktif": bool(peek_config(gid).get("enabled", True)),
        "channel_id": _to_int(peek_config(gid).get("channel_id")),
        "anggota": len(data),
        "total_tingkat": total,
        "per_lencana": per_lencana,
        "hadiah_role": len((peek_config(gid).get("rewards") or {})),
    }


def reset_runtime_state() -> None:
    """Membersihkan state runtime (dipakai tes)."""
    ach_config.clear()
    ach_members.clear()
    _cache_menang.clear()


def cleanup_achievements_runtime(limit: int = 200) -> int:
    """Memangkas server tanpa data lencana agar hemat RAM Free Tier."""
    hapus = 0
    for gid in list(ach_members):
        if not ach_members.get(gid):
            ach_members.pop(gid, None)
            ach_config.pop(gid, None)
            hapus += 1
    if len(ach_config) > limit:
        for gid in list(ach_config)[: len(ach_config) - limit]:
            ach_config.pop(gid, None)
            ach_members.pop(gid, None)
            hapus += 1
    return hapus


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_achievements_from_disk() -> tuple[int, int]:
    """Memuat setelan & catatan lencana → `(jumlah server, jumlah anggota)`."""
    ach_config.clear()
    ach_members.clear()
    if not ACHIEVEMENTS_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(ACHIEVEMENTS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", ACHIEVEMENTS_FILE, exc)
        return 0, 0

    total = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        cfg = default_config()
        if isinstance(data.get("config"), dict):
            cfg["enabled"] = bool(data["config"].get("enabled", True))
            cfg["channel_id"] = _to_int(data["config"].get("channel_id")) or None
            cfg["rewards"] = {
                str(k): _to_int(v)
                for k, v in (data["config"].get("rewards") or {}).items()
                if _to_int(v)
            }
        ach_config[gid] = cfg
        anggota: dict[int, dict] = {}
        for uid_str, isi in (data.get("members") or {}).items():
            try:
                uid = int(uid_str)
            except (TypeError, ValueError):
                continue
            if not isinstance(isi, dict):
                continue
            catatan = {
                kunci: max(0, _to_int(isi.get(kunci)))
                for kunci in ACHIEVEMENT_MAP
                if _to_int(isi.get(kunci))
            }
            catatan["diperbarui"] = float(isi.get("diperbarui") or 0)
            if catatan:
                anggota[uid] = catatan
        if anggota:
            ach_members[gid] = anggota
            total += len(anggota)
    return len(ach_config) or len(ach_members), total


async def save_achievements_to_disk() -> None:
    """Menyimpan setelan & catatan lencana secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            semua = set(ach_config) | set(ach_members)
            payload = {
                "guilds": {
                    str(gid): {
                        "config": ach_config.get(gid),
                        "members": {
                            str(uid): data for uid, data in (ach_members.get(gid) or {}).items()
                        },
                    }
                    for gid in semua
                }
            }
            sementara = Path(str(ACHIEVEMENTS_FILE) + ".tmp")
            await asyncio.to_thread(
                sementara.write_text,
                json.dumps(payload, ensure_ascii=False, indent=2),
                "utf-8",
            )
            await asyncio.to_thread(os.replace, sementara, ACHIEVEMENTS_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan achievements.json")
