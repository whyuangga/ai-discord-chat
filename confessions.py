"""Confessions (ala wisp) — curhat anonim ke satu channel, dengan pagar anti-spam.

Privasi & keamanan:
    - **Tidak menyimpan teks curhat** ke disk. Yang dicatat hanya nomor, waktu, ID pesan
      Discord, dan **hash** penulis (untuk staf melihat apakah satu orang membanjiri channel,
      tanpa pernah tahu siapa). Restart bot tidak menghapus pesan yang sudah terkirim.
    - Jeda per penulis (bawaan 5 menit) + batas 3 kiriman/jam supaya tidak jadi spam.
    - Batas panjang & (opsional) larangan tautan supaya channel tidak jadi tempat promosi.
    - `/curhat hapus` untuk staf bila ada isi yang melanggar.

Data di `data/confessions.json` (tanpa isi curhat).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path

from config import CONFESSIONS_FILE, DATA_DIR

logger = __import__("logging").getLogger("gemini_bot.confessions")

MIN_HURUF = 10
MAKS_HURUF = 900
MAKS_SIMPAN = 300
MAKS_PER_JAM = 3
POLA_LINK = re.compile(r"(https?://|www\.)", re.IGNORECASE)

DEFAULT_CONFIG: dict = {
    "enabled": False,
    "channel_id": None,
    "cooldown_sec": 300,
    "izinkan_link": False,
    "warna": "#5865F2",
}

conf_config: dict[int, dict] = {}
conf_items: dict[int, dict[int, dict]] = {}
conf_nomor: dict[int, int] = {}
#: Jeda terakhir per penulis: {(gid, hash): [timestamp, ...]}
conf_riwayat: dict[tuple[int, str], list[float]] = {}
_lock = asyncio.Lock()


# ==============================================================================
# PENGATURAN
# ==============================================================================
def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def default_config() -> dict:
    return dict(DEFAULT_CONFIG)


def get_config(guild_id: int) -> dict:
    gid = _to_int(guild_id)
    cfg = conf_config.get(gid)
    if cfg is None:
        cfg = default_config()
        conf_config[gid] = cfg
    return cfg


def peek_config(guild_id: int) -> dict:
    cfg = conf_config.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    channel_id: int | None = None,
    cooldown_sec: int | None = None,
    izinkan_link: bool | None = None,
    warna: str | None = None,
) -> dict:
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if channel_id is not None:
        cfg["channel_id"] = _to_int(channel_id) or None
    if cooldown_sec is not None:
        cfg["cooldown_sec"] = max(30, min(86400, _to_int(cooldown_sec, cfg["cooldown_sec"])))
    if izinkan_link is not None:
        cfg["izinkan_link"] = bool(izinkan_link)
    if warna:
        cfg["warna"] = str(warna).strip()[:7]
    return cfg


def aktif(guild_id: int) -> bool:
    """Siap dipakai hanya bila dinyalakan **dan** channel tujuannya sudah diatur."""
    cfg = peek_config(guild_id)
    return bool(cfg.get("enabled")) and bool(cfg.get("channel_id"))


# ==============================================================================
# VALIDASI & PENCATATAN
# ==============================================================================
def hash_penulis(guild_id: int, user_id: int) -> str:
    """Penanda penulis tanpa menyimpan ID asli (12 huruf heksadesimal)."""
    bahan = f"curhat:{_to_int(guild_id)}:{_to_int(user_id)}".encode()
    return hashlib.sha256(bahan).hexdigest()[:12]


def _riwayat(guild_id: int, hash_penulis_: str) -> list[float]:
    return conf_riwayat.setdefault((_to_int(guild_id), hash_penulis_), [])


def sisa_jeda(guild_id: int, hash_penulis_: str, *, sekarang: float | None = None) -> int:
    """Detik sisa sebelum penulis itu boleh kirim lagi (0 = boleh)."""
    cfg = peek_config(guild_id)
    jeda = max(0, _to_int(cfg.get("cooldown_sec"), 300))
    if not jeda:
        return 0
    riwayat = _riwayat(guild_id, hash_penulis_)
    if not riwayat:
        return 0
    sisa = jeda - ((sekarang if sekarang is not None else time.time()) - max(riwayat))
    return max(0, int(sisa))


def validasi(
    guild_id: int,
    user_id: int,
    teks: object,
    *,
    sekarang: float | None = None,
) -> tuple[bool, str]:
    """Cek apakah curhat boleh dikirim → `(boleh, pesan)`.

    Tidak menyimpan apa pun; pemanggil memposting ke Discord lalu memanggil `catat`.
    """
    if not aktif(guild_id):
        return False, (
            "Curhat anonim belum disiapkan Admin (channel & sakelar belum diatur)."
        )
    isi = " ".join(str(teks or "").split())
    if len(isi) < MIN_HURUF:
        return False, f"Tulis minimal {MIN_HURUF} huruf supaya jelas maksudnya."
    if len(isi) > MAKS_HURUF:
        return False, f"Maksimal {MAKS_HURUF} huruf (sekarang {len(isi)})."

    cfg = peek_config(guild_id)
    if not cfg.get("izinkan_link") and POLA_LINK.search(isi):
        return False, "Tautan tidak diizinkan di curhat ini (bisa dimatikan Admin)."

    saat = float(sekarang if sekarang is not None else time.time())
    penanda = hash_penulis(guild_id, user_id)
    sisa = sisa_jeda(guild_id, penanda, sekarang=saat)
    if sisa:
        menit = (sisa + 59) // 60
        return False, f"Tunggu **{menit} menit** lagi sebelum curhat berikutnya."

    riwayat = _riwayat(guild_id, penanda)
    per_jam = [x for x in riwayat if saat - x < 3600]
    if len(per_jam) >= MAKS_PER_JAM:
        return False, f"Maksimal **{MAKS_PER_JAM} curhat per jam**. Coba lagi nanti."
    return True, "OK"


def catat(
    guild_id: int,
    *,
    penulis_hash: str,
    pesan_id: int = 0,
    channel_id: int = 0,
    sekarang: float | None = None,
) -> int:
    """Simpan metadata satu curhat (tanpa teks) → nomor urut."""
    gid = _to_int(guild_id)
    saat = float(sekarang if sekarang is not None else time.time())
    nomor = conf_nomor.get(gid, 0) + 1
    conf_nomor[gid] = nomor
    conf_items.setdefault(gid, {})[nomor] = {
        "nomor": nomor,
        "penulis": str(penulis_hash or "")[:12],
        "pesan_id": _to_int(pesan_id),
        "channel_id": _to_int(channel_id),
        "dibuat": saat,
    }
    daftar = conf_items[gid]
    if len(daftar) > MAKS_SIMPAN:
        for lama in sorted(daftar)[: len(daftar) - MAKS_SIMPAN]:
            daftar.pop(lama, None)
    _riwayat(gid, str(penulis_hash or ""))[:] = [
        x for x in _riwayat(gid, str(penulis_hash or "")) if saat - x < 3600
    ] + [saat]
    return nomor


def ambil(guild_id: int, nomor: int) -> dict | None:
    data = (conf_items.get(_to_int(guild_id)) or {}).get(_to_int(nomor))
    return dict(data) if data else None


def daftar(guild_id: int, *, limit: int = 20) -> list[dict]:
    """Curhat terakhir (metadata saja), terbaru dulu."""
    isi = list((conf_items.get(_to_int(guild_id)) or {}).values())
    isi.sort(key=lambda item: item.get("nomor") or 0, reverse=True)
    return isi[: max(1, int(limit))]


def hapus(guild_id: int, nomor: int) -> dict | None:
    """Hapus metadata satu curhat (dipakai saat staf menghapus pesannya)."""
    gid = _to_int(guild_id)
    return (conf_items.get(gid) or {}).pop(_to_int(nomor), None)


def statistik(guild_id: int) -> dict:
    gid = _to_int(guild_id)
    cfg = peek_config(gid)
    items = conf_items.get(gid) or {}
    penulis = {item.get("penulis") for item in items.values()}
    return {
        "aktif": aktif(gid),
        "dinyalakan": bool(cfg.get("enabled")),
        "channel_id": _to_int(cfg.get("channel_id")) or 0,
        "cooldown_sec": _to_int(cfg.get("cooldown_sec"), 300),
        "izinkan_link": bool(cfg.get("izinkan_link")),
        "warna": str(cfg.get("warna") or "#5865F2"),
        "total": len(items),
        "nomor_terakhir": _to_int(conf_nomor.get(gid)),
        "penulis_unik": len([p for p in penulis if p]),
        "terakhir": max((item.get("dibuat") or 0 for item in items.values()), default=0),
    }


def reset_runtime_state() -> None:
    conf_config.clear()
    conf_items.clear()
    conf_nomor.clear()
    conf_riwayat.clear()


def cleanup_confessions_runtime(limit: int = 200) -> int:
    """Pangkas riwayat jeda & server tanpa curhat (hemat RAM)."""
    hapus = 0
    for kunci in [k for k, isi in conf_riwayat.items() if not isi]:
        conf_riwayat.pop(kunci, None)
        hapus += 1
    for gid in list(conf_config):
        if not conf_items.get(gid):
            conf_config.pop(gid, None)
            conf_nomor.pop(gid, None)
            hapus += 1
    if len(conf_config) > limit:
        for gid in list(conf_config)[: len(conf_config) - limit]:
            conf_config.pop(gid, None)
            conf_items.pop(gid, None)
            conf_nomor.pop(gid, None)
            hapus += 1
    return hapus


# ==============================================================================
# PENYIMPANAN (tanpa isi curhat)
# ==============================================================================
def load_confessions_from_disk() -> tuple[int, int]:
    """Muat setelan & metadata → `(jumlah server, jumlah curhat)`."""
    conf_config.clear()
    conf_items.clear()
    conf_nomor.clear()
    if not Path(CONFESSIONS_FILE).exists():
        return 0, 0
    try:
        raw = json.loads(Path(CONFESSIONS_FILE).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", CONFESSIONS_FILE, exc)
        return 0, 0

    total = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str, -1)
        if gid < 0 or not isinstance(data, dict):
            continue
        cfg = default_config()
        sumber = data.get("config") if isinstance(data.get("config"), dict) else {}
        cfg["enabled"] = bool(sumber.get("enabled", False))
        cfg["channel_id"] = _to_int(sumber.get("channel_id")) or None
        cfg["cooldown_sec"] = max(30, min(86400, _to_int(sumber.get("cooldown_sec"), 300)))
        cfg["izinkan_link"] = bool(sumber.get("izinkan_link", False))
        cfg["warna"] = str(sumber.get("warna") or "#5865F2")[:7]
        conf_config[gid] = cfg

        items: dict[int, dict] = {}
        nomor_tertinggi = 0
        for nomor_str, isi in (data.get("items") or {}).items():
            nomor = _to_int(nomor_str, -1)
            if nomor <= 0 or not isinstance(isi, dict):
                continue
            items[nomor] = {
                "nomor": nomor,
                "penulis": str(isi.get("penulis") or "")[:12],
                "pesan_id": _to_int(isi.get("pesan_id")),
                "channel_id": _to_int(isi.get("channel_id")),
                "dibuat": float(isi.get("dibuat") or 0),
            }
            nomor_tertinggi = max(nomor_tertinggi, nomor)
        if items:
            conf_items[gid] = items
            conf_nomor[gid] = max(nomor_tertinggi, _to_int(data.get("nomor"), 0))
            total += len(items)
    return len(conf_config), total


async def save_confessions_to_disk() -> None:
    """Simpan setelan & metadata curhat secara atomik (tanpa teks curhat)."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            semua = set(conf_config) | set(conf_items)
            payload = {
                "guilds": {
                    str(gid): {
                        "config": conf_config.get(gid) or default_config(),
                        "nomor": _to_int(conf_nomor.get(gid)),
                        "items": {str(nomor): isi for nomor, isi in (conf_items.get(gid) or {}).items()},
                    }
                    for gid in semua
                }
            }
            sementara = Path(str(CONFESSIONS_FILE) + ".tmp")
            await asyncio.to_thread(
                sementara.write_text, json.dumps(payload, ensure_ascii=False, indent=2), "utf-8"
            )
            await asyncio.to_thread(os.replace, sementara, CONFESSIONS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan confessions.json: %s", exc)
