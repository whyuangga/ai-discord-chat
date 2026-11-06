"""Satu fitur boleh punya **beberapa channel** sekaligus.

Config bot dulu hanya menyimpan satu channel (`channel_id`, `log_channel_id`,
`announce_channel_id`, …). Sekarang setiap kunci tunggal punya pasangan daftar
(`channel_ids`, `log_channel_ids`, …) yang boleh berisi banyak channel:

| Kunci tunggal | Kunci daftar |
| :--- | :--- |
| `channel_id` | `channel_ids` |
| `log_channel_id` | `log_channel_ids` |
| `announce_channel_id` | `announce_channel_ids` |
| `backup_channel_id` | `backup_channel_ids` |
| `panel_channel_id` | `panel_channel_ids` |

Aturan kompatibilitas (penting untuk config lama di disk):

- `daftar(cfg)` mengembalikan `channel_ids` bila ada; kalau tidak, dibungkus dari
  `channel_id` tunggal. Jadi fitur lama tetap jalan tanpa migrasi.
- `setel(cfg, ids)` menulis **keduanya**: daftar lengkap + `channel_id` = channel
  pertama, supaya kode yang belum sadar multi-channel tetap benar.
- `cocok(cfg, cid, …)` dipakai fitur berbasis pemicu (mis. Auto-Chat) untuk mengecek
  apakah sebuah channel termasuk target.

Fitur yang **sengaja tetap satu channel**: *koran pagi* (`digest`) dan *fakta harian*
(`server_features`) — keduanya mengirim satu jadwal harian, bukan siaran.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("gemini_bot.channel_targets")

KUNCI_TUNGGAL: tuple[str, ...] = (
    "channel_id",
    "log_channel_id",
    "announce_channel_id",
    "backup_channel_id",
    "panel_channel_id",
)


def kunci_daftar(kunci: str = "channel_id") -> str:
    """`channel_id` → `channel_ids`, `log_channel_id` → `log_channel_ids`."""
    kunci = str(kunci or "channel_id").strip()
    if kunci.endswith("_id"):
        return kunci[:-3] + "_ids"
    return kunci + "s"


def _satu(nilai: object) -> int:
    try:
        angka = int(str(nilai).strip())
    except (TypeError, ValueError):
        return 0
    return angka if angka > 0 else 0


def parse(nilai: object) -> list[int]:
    """Daftar ID channel dari `"123, 456"`, `["123","456"]`, `123`, atau mention.

    Urutan dipertahankan, duplikat & nilai tidak sah dibuang.
    """
    if nilai is None:
        return []
    if isinstance(nilai, (list, tuple, set)):
        bagian = [str(item) for item in nilai]
    else:
        bagian = re.split(r"[\s,;]+", str(nilai).strip())
    hasil: list[int] = []
    for item in bagian:
        teks = item.strip().strip("<>#")
        if teks.startswith("@"):
            continue
        angka = _satu(re.sub(r"[^0-9]", "", teks))
        if angka and angka not in hasil:
            hasil.append(angka)
    return hasil


def daftar(cfg: dict | None, kunci: str = "channel_id") -> list[int]:
    """Semua channel target untuk sebuah config (multi → tunggal → kosong)."""
    if not isinstance(cfg, dict):
        return []
    banyak = parse(cfg.get(kunci_daftar(kunci)))
    if banyak:
        return banyak
    satu = _satu(cfg.get(kunci))
    return [satu] if satu else []


def utama(cfg: dict | None, kunci: str = "channel_id") -> int:
    """Channel pertama (dipakai kode yang masih single-channel)."""
    banyak = daftar(cfg, kunci)
    return banyak[0] if banyak else 0


def setel(cfg: dict, ids: object, kunci: str = "channel_id") -> list[int]:
    """Simpan daftar channel + sinkronkan kunci tunggal ke channel pertama."""
    if not isinstance(cfg, dict):
        return []
    bersih = parse(ids)
    cfg[kunci_daftar(kunci)] = list(bersih)
    cfg[kunci] = bersih[0] if bersih else None
    return bersih


def tambah(cfg: dict, cid: int, kunci: str = "channel_id") -> list[int]:
    """Tambahkan satu channel ke daftar (tanpa menghapus yang sudah ada)."""
    bersih = daftar(cfg, kunci)
    if _satu(cid) and _satu(cid) not in bersih:
        bersih.append(_satu(cid))
    return setel(cfg, bersih, kunci)


def hapus(cfg: dict, cid: int, kunci: str = "channel_id") -> list[int]:
    """Buang satu channel dari daftar."""
    sisa = [c for c in daftar(cfg, kunci) if c != _satu(cid)]
    return setel(cfg, sisa, kunci)


def cocok(cfg: dict | None, channel_id: object, kunci: str = "channel_id") -> bool:
    """Apakah `channel_id` termasuk target config ini?"""
    cid = _satu(channel_id)
    return bool(cid) and cid in daftar(cfg, kunci)


def label(ids: object, batas: int = 4) -> str:
    """`<#1>, <#2>, +2 lagi` untuk pesan konfirmasi."""
    bersih = parse(ids)
    if not bersih:
        return "—"
    potongan = [f"<#{cid}>" for cid in bersih[:batas]]
    sisa = len(bersih) - len(potongan)
    teks = ", ".join(potongan)
    return f"{teks} +{sisa} lagi" if sisa > 0 else teks


def objek(bot, ids: object) -> list:
    """Objek channel dari daftar ID (yang tidak ditemukan dilewati)."""
    hasil = []
    getter = getattr(bot, "get_channel", None)
    if not callable(getter):
        return hasil
    for cid in parse(ids):
        channel = getter(cid)
        if channel is not None and channel not in hasil:
            hasil.append(channel)
    return hasil


async def sebarkan(bot, ids: object, kirim) -> int:
    """Kirim ke **semua** channel di daftar; satu channel gagal tidak membatalkan sisanya.

    `kirim` adalah fungsi async yang menerima objek channel. Mengembalikan jumlah
    channel yang berhasil dikirimi.
    """
    berhasil = 0
    for channel in objek(bot, ids):
        try:
            await kirim(channel)
            berhasil += 1
        except Exception as exc:  # pragma: no cover - izin/koneksi
            logger.warning(
                "Gagal mengirim ke channel %s: %s", getattr(channel, "id", "?"), exc
            )
    return berhasil
