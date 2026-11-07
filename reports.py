"""Laporan member & antrean banding — jalur resmi dua arah antara member dan staf.

Moderasi yang hanya satu arah membuat member merasa tidak didengar. Modul ini
menyediakan:

* **Laporan** (`/lapor`): member melaporkan pesan/member lain; masuk ke antrean
  staf + channel laporan, bukan langsung memicu hukuman.
* **Banding** (`/banding`): member yang dikenai hukuman bisa meminta peninjauan,
  terhubung ke **nomor kasus** moderasi yang bersangkutan.
* **Antrean** untuk staf (`/mod antrean` + halaman **Moderasi** di dashboard):
  saring per status, ubah status (`baru` → `diproses` → `diterima`/`ditolak`),
  dan beri catatan staf.

Semua lokal: `data/reports.json`, 1 proses, tanpa AI, **0 kuota**.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from config import DATA_DIR, REPORTS_FILE

logger = logging.getLogger("gemini_bot.reports")

#: Jenis kiriman yang masuk antrean staf.
JENIS: dict[str, str] = {
    "laporan": "🚩 Laporan member",
    "banding": "⚖️ Banding hukuman",
}

#: Status penanganan (urutan = alur kerja).
STATUS: dict[str, str] = {
    "baru": "🆕 Baru",
    "diproses": "🔎 Diproses",
    "diterima": "✅ Diterima",
    "ditolak": "❌ Ditolak",
}

MAX_ANTREAN_PER_GUILD = 300
MIN_ALASAN = 10                # huruf minimum supaya laporan bisa ditindak
MAKS_ALASAN = 800

reports_guilds: dict[int, dict] = {}   # guild_id -> setelan laporan
antrean: dict[int, list[dict]] = {}    # guild_id -> daftar laporan/banding
_cooldown: dict[tuple[int, int, str], float] = {}

_lock = asyncio.Lock()


# ==============================================================================
# PENGATURAN
# ==============================================================================
def default_config() -> dict:
    """Setelan awal: laporan aktif, cooldown 5 menit, tanpa channel khusus."""
    return {
        "enabled": True,
        "channel_id": None,
        "cooldown_sec": 300,
        "dm_pelapor": True,
    }


def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def _normalisasi(data: dict) -> dict:
    base = default_config()
    base.update(
        {
            "enabled": bool(data.get("enabled", True)),
            "channel_id": _to_int(data.get("channel_id")) or None,
            "cooldown_sec": max(0, min(86400, _to_int(data.get("cooldown_sec"), 300))),
            "dm_pelapor": bool(data.get("dm_pelapor", True)),
        }
    )
    return base


def get_config(guild_id: int) -> dict:
    """Setelan laporan server (dibuat aman bila belum ada)."""
    gid = _to_int(guild_id)
    cfg = reports_guilds.get(gid)
    if cfg is None:
        cfg = default_config()
        reports_guilds[gid] = cfg
    return cfg


def peek_config(guild_id: int) -> dict:
    """Baca setelan tanpa membuat entri baru (dipakai dashboard)."""
    cfg = reports_guilds.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    channel_id: int | None = None,
    cooldown_sec: int | None = None,
    dm_pelapor: bool | None = None,
) -> dict:
    """Mengubah setelan laporan."""
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if channel_id is not None:
        cfg["channel_id"] = _to_int(channel_id) or None
    if cooldown_sec is not None:
        cfg["cooldown_sec"] = max(0, min(86400, _to_int(cooldown_sec)))
    if dm_pelapor is not None:
        cfg["dm_pelapor"] = bool(dm_pelapor)
    return cfg


def reset_config(guild_id: int) -> None:
    reports_guilds.pop(_to_int(guild_id), None)


# ==============================================================================
# ANTREAN
# ==============================================================================
def _next_id(guild_id: int) -> int:
    daftar = antrean.get(_to_int(guild_id)) or []
    return max((_to_int(item.get("id")) for item in daftar), default=0) + 1


def sisa_cooldown(guild_id: int, pelapor_id: int, jenis: str = "laporan") -> int:
    """Sisa detik sebelum pelapor boleh mengirim lagi (0 = boleh sekarang)."""
    gid = _to_int(guild_id)
    kunci = (gid, _to_int(pelapor_id), str(jenis or "laporan"))
    batas = _cooldown.get(kunci)
    if not batas:
        return 0
    sisa = int(batas - time.time())
    if sisa <= 0:
        _cooldown.pop(kunci, None)
        return 0
    return sisa


def _pasang_cooldown(guild_id: int, pelapor_id: int, jenis: str) -> None:
    cfg = get_config(guild_id)
    detik = _to_int(cfg.get("cooldown_sec"), 300)
    if detik <= 0:
        return
    _cooldown[(_to_int(guild_id), _to_int(pelapor_id), str(jenis))] = time.time() + detik


def tambah(
    guild_id: int,
    *,
    jenis: str = "laporan",
    pelapor_id: int,
    target_id: int = 0,
    alasan: str,
    bukti: str = "",
    kasus_id: int = 0,
) -> tuple[str, dict | None]:
    """Menambah laporan/banding baru → `(status, entri)`.

    Status: `ok`, `nonaktif`, `terlalu_pendek`, `cooldown`.
    """
    gid = _to_int(guild_id)
    cfg = get_config(gid)
    if not cfg.get("enabled") and str(jenis) == "laporan":
        return "nonaktif", None
    teks = str(alasan or "").strip()
    if len(teks) < MIN_ALASAN:
        return "terlalu_pendek", None
    if sisa_cooldown(gid, pelapor_id, jenis) > 0:
        return "cooldown", None

    jenis_aman = str(jenis).lower() if str(jenis).lower() in JENIS else "laporan"
    entri = {
        "id": _next_id(gid),
        "jenis": jenis_aman,
        "pelapor_id": _to_int(pelapor_id),
        "target_id": _to_int(target_id),
        "kasus_id": _to_int(kasus_id),
        "alasan": teks[:MAKS_ALASAN],
        "bukti": str(bukti or "").strip()[:400],
        "status": "baru",
        "catatan": "",
        "oleh": 0,
        "dibuat": time.time(),
        "diubah": 0.0,
    }
    daftar = antrean.setdefault(gid, [])
    daftar.append(entri)
    if len(daftar) > MAX_ANTREAN_PER_GUILD:
        del daftar[:-MAX_ANTREAN_PER_GUILD]
    _pasang_cooldown(gid, pelapor_id, jenis_aman)
    return "ok", entri


def daftar(
    guild_id: int,
    *,
    status: str | None = None,
    jenis: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Antrean terbaru (opsional disaring status & jenis), urut dari yang paling baru."""
    status = str(status or "").strip().lower() or None
    jenis = str(jenis or "").strip().lower() or None
    hasil = []
    for entri in reversed(antrean.get(_to_int(guild_id)) or []):
        if status and str(entri.get("status")) != status:
            continue
        if jenis and str(entri.get("jenis")) != jenis:
            continue
        hasil.append(entri)
        if len(hasil) >= max(1, int(limit)):
            break
    return hasil


def ambil(guild_id: int, nomor: int) -> dict | None:
    """Satu entri antrean berdasarkan nomornya."""
    for entri in antrean.get(_to_int(guild_id)) or []:
        if _to_int(entri.get("id")) == _to_int(nomor):
            return entri
    return None


def ubah_status(
    guild_id: int,
    nomor: int,
    status: str,
    *,
    oleh: int = 0,
    catatan: str = "",
) -> dict | None:
    """Mengubah status satu entri (`baru`/`diproses`/`diterima`/`ditolak`)."""
    kunci = str(status or "").strip().lower()
    if kunci not in STATUS:
        return None
    entri = ambil(guild_id, nomor)
    if entri is None:
        return None
    entri["status"] = kunci
    entri["oleh"] = _to_int(oleh)
    entri["diubah"] = time.time()
    if catatan:
        entri["catatan"] = str(catatan).strip()[:400]
    return entri


def statistik(guild_id: int) -> dict:
    """Ringkasan antrean untuk dashboard: total & per status/jenis."""
    daftar_semua = antrean.get(_to_int(guild_id)) or []
    data = {
        "total": len(daftar_semua),
        "baru": 0,
        "diproses": 0,
        "diterima": 0,
        "ditolak": 0,
        "laporan": 0,
        "banding": 0,
    }
    for entri in daftar_semua:
        status = str(entri.get("status") or "baru")
        if status in data:
            data[status] += 1
        jenis = str(entri.get("jenis") or "laporan")
        if jenis in ("laporan", "banding"):
            data[jenis] += 1
    data["menunggu"] = data["baru"] + data["diproses"]
    return data


def status(guild_id: int) -> dict:
    """Ringkasan setelan + antrean (satu paket untuk dashboard & command)."""
    cfg = peek_config(guild_id)
    data = statistik(guild_id)
    return {
        "aktif": bool(cfg.get("enabled")),
        "channel_id": _to_int(cfg.get("channel_id")),
        "cooldown_sec": _to_int(cfg.get("cooldown_sec"), 300),
        "dm_pelapor": bool(cfg.get("dm_pelapor", True)),
        **data,
    }


def reset_runtime_state() -> None:
    """Membersihkan state runtime (dipakai tes)."""
    reports_guilds.clear()
    antrean.clear()
    _cooldown.clear()


def cleanup_reports_runtime(limit: int = 200) -> int:
    """Memangkas server tanpa antrean agar hemat RAM."""
    hapus = 0
    for gid in list(antrean):
        if not antrean.get(gid):
            antrean.pop(gid, None)
            hapus += 1
    if len(reports_guilds) > limit:
        for gid in list(reports_guilds)[: len(reports_guilds) - limit]:
            reports_guilds.pop(gid, None)
            antrean.pop(gid, None)
            hapus += 1
    batas = time.time()
    for kunci, sampai in list(_cooldown.items()):
        if sampai <= batas:
            _cooldown.pop(kunci, None)
    return hapus


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_reports_from_disk() -> tuple[int, int]:
    """Memuat setelan & antrean dari `data/reports.json` → (server, entri)."""
    if not REPORTS_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(REPORTS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", REPORTS_FILE, exc)
        return 0, 0

    total = 0
    for gid_str, gdata in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(gdata, dict):
            continue
        if gdata.get("config"):
            reports_guilds[gid] = _normalisasi(gdata["config"])
        entries = []
        for item in (gdata.get("antrean") or [])[-MAX_ANTREAN_PER_GUILD:]:
            try:
                entries.append(
                    {
                        "id": _to_int(item["id"]),
                        "jenis": str(item.get("jenis") or "laporan"),
                        "pelapor_id": _to_int(item.get("pelapor_id")),
                        "target_id": _to_int(item.get("target_id")),
                        "kasus_id": _to_int(item.get("kasus_id")),
                        "alasan": str(item.get("alasan") or "")[:MAKS_ALASAN],
                        "bukti": str(item.get("bukti") or "")[:400],
                        "status": str(item.get("status") or "baru"),
                        "catatan": str(item.get("catatan") or "")[:400],
                        "oleh": _to_int(item.get("oleh")),
                        "dibuat": float(item.get("dibuat") or time.time()),
                        "diubah": float(item.get("diubah") or 0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        if entries:
            antrean[gid] = entries
            total += len(entries)
    return len(reports_guilds) or len(antrean), total


async def save_reports_to_disk() -> None:
    """Menyimpan setelan & antrean secara atomik."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            semua = set(reports_guilds) | set(antrean)
            payload = {
                "guilds": {
                    str(gid): {
                        "config": reports_guilds.get(gid),
                        "antrean": antrean.get(gid) or [],
                    }
                    for gid in semua
                }
            }
            sementara = Path(str(REPORTS_FILE) + ".tmp")
            await asyncio.to_thread(
                sementara.write_text,
                json.dumps(payload, ensure_ascii=False, indent=2),
                "utf-8",
            )
            await asyncio.to_thread(os.replace, sementara, REPORTS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan reports.json: %s", exc)


# ==============================================================================
# SIMULASI (DASHBOARD)
# ==============================================================================
def akan_masuk_antrean(guild_id: int, *, jenis: str = "laporan", panjang_alasan: int = 40) -> dict:
    """Simulasi: apakah laporan sepanjang ini akan diterima? **Tanpa** menambah entri."""
    cfg = peek_config(guild_id)
    if str(jenis) == "laporan" and not cfg.get("enabled"):
        return {"masuk": False, "alasan": "Laporan member sedang dimatikan di server ini."}
    if int(panjang_alasan) < MIN_ALASAN:
        return {
            "masuk": False,
            "alasan": f"Alasan terlalu pendek (minimal {MIN_ALASAN} huruf, ini {int(panjang_alasan)}).",
        }
    return {
        "masuk": True,
        "alasan": (
            f"Laporan akan masuk antrean staf, cooldown pelapor "
            f"{_to_int(cfg.get('cooldown_sec'), 300)} detik."
        ),
    }
