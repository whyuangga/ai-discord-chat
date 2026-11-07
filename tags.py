"""Tags — jawaban siap pakai milik server (`/tag`), 0 kuota AI, tanpa database.

Satu tag = satu jawaban yang disimpan sekali dan dipanggil kapan saja
(`/tag lihat aturan`). Jauh lebih ringan daripada `/faq` AI: **tanpa Gemini sama
sekali**, hanya pencarian kamus di memori.

Isi:
    * `data/tags.json` (JSON, 1 proses) — aman restart.
    * Maksimal 100 tag/server, isi maks 1800 karakter (batas embed Discord).
    * Nama tag dinormalisasi (`Aturan Server` → `aturan-server`).
    * Penghitung pemakaian (`dipakai`) untuk melihat tag mana yang paling berguna.
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

from config import DATA_DIR, TAGS_FILE

logger = logging.getLogger("gemini_bot.tags")

MAX_TAG_PER_GUILD = 100
TAG_NAMA_MAKS = 32
TAG_ISI_MAKS = 1800

#: {guild_id: {nama_tag: {"isi", "oleh", "dibuat", "dipakai"}}}
tags_guilds: dict[int, dict[str, dict]] = {}
#: {guild_id: {"enabled": bool}}
tags_config: dict[int, dict] = {}

_lock = asyncio.Lock()

_POLA_NAMA = re.compile(r"[^a-z0-9]+")


# ==============================================================================
# PENGATURAN & NAMA
# ==============================================================================
def default_config() -> dict:
    """Setelan awal tags: aktif."""
    return {"enabled": True}


def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def normalisasi(nama: object) -> str:
    """`Aturan Server!` → `aturan-server` (huruf kecil, tanpa spasi/emoji)."""
    teks = str(nama or "").strip().lower()
    teks = _POLA_NAMA.sub("-", teks).strip("-")
    return teks[:TAG_NAMA_MAKS]


def get_config(guild_id: int) -> dict:
    gid = _to_int(guild_id)
    cfg = tags_config.get(gid)
    if cfg is None:
        cfg = default_config()
        tags_config[gid] = cfg
    return cfg


def peek_config(guild_id: int) -> dict:
    """Baca setelan tanpa membuat entri baru (dipakai dashboard)."""
    cfg = tags_config.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def set_config(guild_id: int, *, enabled: bool | None = None) -> dict:
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    return cfg


# ==============================================================================
# OPERASI TAG
# ==============================================================================
def _kamus(guild_id: int) -> dict[str, dict]:
    return tags_guilds.setdefault(_to_int(guild_id), {})


def tambah(guild_id: int, nama: object, isi: object, oleh: int = 0) -> tuple[str, dict | None]:
    """Membuat tag baru → `(status, tag)`. Status: `ok`, `nama_kosong`, `isi_kosong`, `penuh`, `sudah_ada`."""
    kunci = normalisasi(nama)
    teks = str(isi or "").strip()
    if not kunci:
        return "nama_kosong", None
    kamus = _kamus(guild_id)
    if kunci in kamus:
        return "sudah_ada", kamus[kunci]
    if not teks:
        return "isi_kosong", None
    if len(kamus) >= MAX_TAG_PER_GUILD:
        return "penuh", None
    tag = {
        "nama": kunci,
        "isi": teks[:TAG_ISI_MAKS],
        "oleh": _to_int(oleh),
        "dibuat": time.time(),
        "dipakai": 0,
    }
    kamus[kunci] = tag
    return "ok", tag


def ubah(guild_id: int, nama: object, isi: object, oleh: int = 0) -> tuple[str, dict | None]:
    """Mengubah isi tag yang sudah ada → `(status, tag)`. Status: `ok`, `tidak_ada`, `isi_kosong`."""
    kunci = normalisasi(nama)
    kamus = _kamus(guild_id)
    tag = kamus.get(kunci)
    if tag is None:
        return "tidak_ada", None
    teks = str(isi or "").strip()
    if not teks:
        return "isi_kosong", None
    tag["isi"] = teks[:TAG_ISI_MAKS]
    tag["oleh"] = _to_int(oleh)
    tag["diubah"] = time.time()
    return "ok", tag


def hapus(guild_id: int, nama: object) -> bool:
    return _kamus(guild_id).pop(normalisasi(nama), None) is not None


def ambil(guild_id: int, nama: object) -> dict | None:
    """Ambil tag **tanpa** menaikkan penghitung (dipakai dashboard)."""
    return _kamus(guild_id).get(normalisasi(nama))


def pakai(guild_id: int, nama: object) -> dict | None:
    """Ambil tag untuk dikirim ke member & naikkan penghitung pemakaian."""
    tag = ambil(guild_id, nama)
    if tag is None:
        return None
    tag["dipakai"] = _to_int(tag.get("dipakai")) + 1
    return tag


def daftar(guild_id: int, *, limit: int = 25) -> list[dict]:
    """Semua tag server, urut abjad."""
    kamus = _kamus(guild_id)
    urut = sorted(kamus.values(), key=lambda t: str(t.get("nama")))
    return urut[: max(1, int(limit))]


def cari(guild_id: int, kata: object, *, limit: int = 10) -> list[dict]:
    """Cari tag berdasarkan nama **atau** isi (tidak peka huruf besar/kecil)."""
    q = str(kata or "").strip().lower()
    if not q:
        return daftar(guild_id, limit=limit)
    hasil = [
        tag
        for tag in sorted(_kamus(guild_id).values(), key=lambda t: str(t.get("nama")))
        if q in str(tag.get("nama", "")).lower() or q in str(tag.get("isi", "")).lower()
    ]
    return hasil[: max(1, int(limit))]


def statistik(guild_id: int) -> dict:
    """Ringkasan untuk dashboard: total, paling sering dipakai, & belum pernah dipakai."""
    kamus = _kamus(guild_id)
    teratas = sorted(kamus.values(), key=lambda t: -_to_int(t.get("dipakai")))[:5]
    return {
        "total": len(kamus),
        "batas": MAX_TAG_PER_GUILD,
        "dipakai": sum(_to_int(t.get("dipakai")) for t in kamus.values()),
        "teratas": [
            {"nama": t.get("nama"), "dipakai": _to_int(t.get("dipakai"))} for t in teratas
        ],
        "belum_dipakai": sum(1 for t in kamus.values() if not _to_int(t.get("dipakai"))),
        "aktif": bool(get_config(guild_id).get("enabled", True)),
    }


def reset_runtime_state() -> None:
    """Membersihkan state runtime (dipakai tes)."""
    tags_guilds.clear()
    tags_config.clear()


def cleanup_tags_runtime(limit: int = 200) -> int:
    """Memangkas server tanpa tag agar hemat RAM Free Tier."""
    hapus_total = 0
    for gid in list(tags_guilds):
        if not tags_guilds.get(gid):
            tags_guilds.pop(gid, None)
            tags_config.pop(gid, None)
            hapus_total += 1
    if len(tags_guilds) > limit:
        for gid in list(tags_guilds)[: len(tags_guilds) - limit]:
            tags_guilds.pop(gid, None)
            tags_config.pop(gid, None)
            hapus_total += 1
    return hapus_total


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_tags_from_disk() -> tuple[int, int]:
    """Memuat tag semua server → `(jumlah server, jumlah tag)`."""
    tags_guilds.clear()
    tags_config.clear()
    if not TAGS_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(TAGS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", TAGS_FILE, exc)
        return 0, 0

    total = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        kamus: dict[str, dict] = {}
        for nama, isi_data in (data.get("tags") or {}).items():
            if not isinstance(isi_data, dict):
                continue
            kunci = normalisasi(nama)
            teks = str(isi_data.get("isi") or "").strip()
            if not kunci or not teks:
                continue
            kamus[kunci] = {
                "nama": kunci,
                "isi": teks[:TAG_ISI_MAKS],
                "oleh": _to_int(isi_data.get("oleh")),
                "dibuat": float(isi_data.get("dibuat") or time.time()),
                "dipakai": max(0, _to_int(isi_data.get("dipakai"))),
            }
        if kamus:
            tags_guilds[gid] = kamus
            total += len(kamus)
        if data.get("enabled") is not None:
            tags_config[gid] = {"enabled": bool(data.get("enabled"))}
    return len(tags_guilds), total


async def save_tags_to_disk() -> None:
    """Menyimpan tag secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            semua = set(tags_guilds) | set(tags_config)
            payload = {
                "guilds": {
                    str(gid): {
                        "enabled": bool(peek_config(gid).get("enabled", True)),
                        "tags": tags_guilds.get(gid) or {},
                    }
                    for gid in semua
                }
            }
            sementara = Path(str(TAGS_FILE) + ".tmp")
            await asyncio.to_thread(
                sementara.write_text,
                json.dumps(payload, ensure_ascii=False, indent=2),
                "utf-8",
            )
            await asyncio.to_thread(os.replace, sementara, TAGS_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan tags.json")
