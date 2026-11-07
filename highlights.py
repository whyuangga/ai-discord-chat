"""Highlights (ala wisp): kata kunci pilihan member → DM saat muncul di chat.

Prinsip:
    - **0 kuota AI.** Hanya pencocokan teks biasa (regex batas kata), tanpa model.
    - **Opt-in per member.** Tidak ada yang menerima DM sebelum mendaftarkan kata kunci.
    - **Tidak menyimpan isi pesan.** Hanya penghitung & kata kunci yang disimpan;
      isi pesan yang cocok dikirim sekali ke DM (tidak ditulis ke disk).
    - **Anti-banjir.** Satu kata kunci per member punya jeda sendiri, plus batas
      jumlah DM per member per menit supaya bot tidak jadi spammer.

Data di `data/highlights.json`:
    {"guilds": {"<gid>": {"config": {...}, "members": {"<uid>": {...}}}}}
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

from config import DATA_DIR, HIGHLIGHTS_FILE

logger = __import__("logging").getLogger("gemini_bot.highlights")

MAX_KATA_PER_MEMBER = 10
MAX_MEMBER_PER_GUILD = 300
MAX_KATA_PANJANG = 40
MAX_ABAIKAN_CHANNEL = 20
MAX_ABAIKAN_KATA = 20
MAX_ALERT_PER_MENIT = 5
JEDA_SAMA_KATA_DETIK = 300      # kata yang sama tidak memicu DM lagi selama 5 menit
PANJANG_CUPLIKAN = 180

hl_config: dict[int, dict] = {}
hl_members: dict[int, dict[int, dict]] = {}
_lock = asyncio.Lock()
#: Cache pencocokan per server: {gid: {kata_normal: set(uid)}}
_index: dict[int, dict[str, set[int]]] = {}


# ==============================================================================
# PENGATURAN
# ==============================================================================
def default_config() -> dict:
    return {
        "enabled": True,
        "abaikan_channel": [],    # channel yang tidak pernah memicu highlight
        "max_per_menit": MAX_ALERT_PER_MENIT,
    }


def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def _daftar_id(nilai: object) -> list[int]:
    """Bersihkan daftar ID channel dari JSON/form (unik, maks 20)."""
    hasil: list[int] = []
    for satu in nilai or []:
        angka = _to_int(satu)
        if angka and angka not in hasil:
            hasil.append(angka)
    return hasil[:MAX_ABAIKAN_CHANNEL]


def get_config(guild_id: int) -> dict:
    gid = _to_int(guild_id)
    cfg = hl_config.get(gid)
    if cfg is None:
        cfg = default_config()
        hl_config[gid] = cfg
    return cfg


def peek_config(guild_id: int) -> dict:
    """Baca setelan tanpa membuat entri baru (dipakai dashboard)."""
    cfg = hl_config.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    abaikan_channel: object = None,
    max_per_menit: int | None = None,
) -> dict:
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if abaikan_channel is not None:
        cfg["abaikan_channel"] = _daftar_id(abaikan_channel)
    if max_per_menit is not None:
        cfg["max_per_menit"] = max(1, min(MAX_ALERT_PER_MENIT, _to_int(max_per_menit, MAX_ALERT_PER_MENIT)))
    _index.pop(_to_int(guild_id), None)
    return cfg


# ==============================================================================
# KATA KUNCI PER MEMBER
# ==============================================================================
def normalisasi(kata: object) -> str:
    """Rapikan kata kunci: huruf kecil, spasi tunggal, tanpa tanda baca pinggir."""
    teks = str(kata or "").strip().lower()
    teks = re.sub(r"\s+", " ", teks)
    return teks.strip(" .,!?:;\"'`")


def _data_member(guild_id: int, user_id: int) -> dict:
    gid = _to_int(guild_id)
    uid = _to_int(user_id)
    semua = hl_members.setdefault(gid, {})
    data = semua.get(uid)
    if data is None:
        data = {
            "keywords": [],
            "abaikan_channel": [],
            "abaikan_kata": [],
            "hit": 0,
            "diperbarui": time.time(),
        }
        semua[uid] = data
    data.setdefault("keywords", [])
    data.setdefault("abaikan_channel", [])
    data.setdefault("abaikan_kata", [])
    data.setdefault("hit", 0)
    return data


def _pangkas(guild_id: int) -> None:
    """Jaga RAM: maksimal 300 member terdaftar per server (yang terlama pergi)."""
    semua = hl_members.get(int(guild_id)) or {}
    if len(semua) <= MAX_MEMBER_PER_GUILD:
        return
    urut = sorted(semua.items(), key=lambda pasangan: float((pasangan[1] or {}).get("diperbarui") or 0))
    for uid, _ in urut[: len(urut) - MAX_MEMBER_PER_GUILD]:
        semua.pop(uid, None)


def daftar_kata(guild_id: int, user_id: int) -> list[str]:
    """Kata kunci aktif milik satu member."""
    data = (hl_members.get(_to_int(guild_id)) or {}).get(_to_int(user_id)) or {}
    return list(data.get("keywords") or [])


def tambah_kata(guild_id: int, user_id: int, kata: object) -> tuple[bool, str]:
    """Daftarkan satu kata kunci → `(berhasil, pesan)`."""
    teks = normalisasi(kata)
    if not teks:
        return False, "Kata kunci tidak boleh kosong."
    if len(teks) > MAX_KATA_PANJANG:
        return False, f"Kata kunci maksimal {MAX_KATA_PANJANG} huruf."
    if teks in (_data_member(guild_id, user_id).get("abaikan_kata") or []):
        return False, f"`{teks}` ada di daftar **abaikan** — hapus dulu dari daftar itu."

    data = _data_member(guild_id, user_id)
    if teks in data["keywords"]:
        return False, f"`{teks}` sudah ada di daftar pantauanmu."
    if len(data["keywords"]) >= MAX_KATA_PER_MEMBER:
        return False, f"Maksimal {MAX_KATA_PER_MEMBER} kata kunci per member. Hapus satu dulu."

    data["keywords"].append(teks)
    data["diperbarui"] = time.time()
    _pangkas(guild_id)
    _index.pop(_to_int(guild_id), None)
    return True, f"`{teks}` ditambahkan. Kamu akan dapat DM saat kata itu muncul di chat."


def hapus_kata(guild_id: int, user_id: int, kata: object) -> tuple[bool, str]:
    teks = normalisasi(kata)
    data = _data_member(guild_id, user_id)
    if teks not in data["keywords"]:
        return False, f"`{teks or '-'}` tidak ada di daftar pantauanmu."
    data["keywords"].remove(teks)
    data["diperbarui"] = time.time()
    _index.pop(_to_int(guild_id), None)
    return True, f"`{teks}` dihapus dari pantauan."


def tambah_abaikan(guild_id: int, user_id: int, *, channel_id: int | None = None,
                   kata: object = None) -> tuple[bool, str]:
    """Abaikan satu channel atau satu kata untuk member ini."""
    data = _data_member(guild_id, user_id)
    if channel_id:
        cid = _to_int(channel_id)
        if cid in data["abaikan_channel"]:
            return False, f"<#{cid}> sudah diabaikan."
        if len(data["abaikan_channel"]) >= MAX_ABAIKAN_CHANNEL:
            return False, f"Maksimal {MAX_ABAIKAN_CHANNEL} channel yang diabaikan."
        data["abaikan_channel"].append(cid)
        data["diperbarui"] = time.time()
        _pangkas(guild_id)
        return True, f"<#{cid}> tidak akan memicu highlight untukmu."
    teks = normalisasi(kata)
    if not teks:
        return False, "Sebutkan channel atau kata yang mau diabaikan."
    if teks in data["keywords"]:
        return False, f"`{teks}` justru sedang kamu pantau — hapus dari pantauan kalau ingin diabaikan."
    if teks in data["abaikan_kata"]:
        return False, f"`{teks}` sudah ada di daftar abaikan."
    if len(data["abaikan_kata"]) >= MAX_ABAIKAN_KATA:
        return False, f"Maksimal {MAX_ABAIKAN_KATA} kata yang diabaikan."
    data["abaikan_kata"].append(teks)
    data["diperbarui"] = time.time()
    _pangkas(guild_id)
    _index.pop(_to_int(guild_id), None)
    return True, f"Pesan yang mengandung `{teks}` tidak akan memicu highlight untukmu."


def bersihkan(guild_id: int, user_id: int) -> bool:
    """Hapus seluruh setelan highlight member (opt-out total)."""
    semua = hl_members.get(_to_int(guild_id)) or {}
    terhapus = semua.pop(_to_int(user_id), None) is not None
    if terhapus:
        _index.pop(_to_int(guild_id), None)
    return terhapus


# ==============================================================================
# PENCOCOKAN
# ==============================================================================
def _pola(kata: str) -> re.Pattern[str]:
    """Pola batas kata: `bot` cocok di `bot itu`, tidak di `robot`."""
    return re.compile(r"(?<!\w)" + re.escape(kata) + r"(?!\w)", re.IGNORECASE)


_POLA_CACHE: dict[str, re.Pattern[str]] = {}


def _cocok_kata(teks: str, kata: str) -> bool:
    pola = _POLA_CACHE.get(kata)
    if pola is None:
        pola = _pola(kata)
        if len(_POLA_CACHE) > 2000:  # jaga RAM, cache kecil saja
            _POLA_CACHE.clear()
        _POLA_CACHE[kata] = pola
    return bool(pola.search(teks))


def _daftar_abaikan_kata(guild_id: int) -> set[str]:
    hasil: set[str] = set()
    for data in (hl_members.get(_to_int(guild_id)) or {}).values():
        hasil.update((data or {}).get("abaikan_kata") or [])
    return hasil


def cocok(guild_id: int, teks: str, *, channel_id: int = 0, sekarang: float | None = None) -> list[dict]:
    """Siapa yang harus dikirimi DM untuk pesan ini.

    Mengembalikan daftar `{user_id, kata}` — **tidak** mengirim DM & tidak menyimpan
    isi pesan. Pemanggil (cog) yang mengirim DM lalu memanggil `catat_terkirim()`.
    """
    gid = _to_int(guild_id)
    cfg = peek_config(gid)
    if not cfg.get("enabled", True):
        return []
    isi = str(teks or "")
    if len(isi) < 2:
        return []
    cid = _to_int(channel_id)
    if cid and cid in (cfg.get("abaikan_channel") or []):
        return []

    semua = hl_members.get(gid) or {}
    if not semua:
        return []
    abaikan_global = _daftar_abaikan_kata(gid)
    sekarang = float(sekarang if sekarang is not None else time.time())

    # Pesan yang memuat kata abaikan (milik siapa pun) tidak memicu highlight apa pun.
    for kata_abaikan in abaikan_global:
        if _cocok_kata(isi, kata_abaikan):
            return []

    hasil: list[dict] = []
    for uid, data in semua.items():
        data = data or {}
        if cid and cid in (data.get("abaikan_channel") or []):
            continue
        for kata in data.get("keywords") or []:
            if not _cocok_kata(isi, kata):
                continue
            terakhir = float((data.get("terakhir") or {}).get(kata) or 0)
            if sekarang - terakhir < JEDA_SAMA_KATA_DETIK:
                continue
            hasil.append({"user_id": _to_int(uid), "kata": kata})
            break  # satu DM per pesan per member
    return hasil


def catat_terkirim(guild_id: int, user_id: int, kata: str, *, sekarang: float | None = None) -> int:
    """Catat DM terkirim → mengembalikan jumlah DM member itu dalam 60 detik terakhir."""
    data = _data_member(guild_id, user_id)
    sekarang = float(sekarang if sekarang is not None else time.time())
    data["hit"] = _to_int(data.get("hit")) + 1
    data["diperbarui"] = sekarang
    data.setdefault("terakhir", {})[normalisasi(kata)] = sekarang
    riwayat = [float(x) for x in (data.get("menit") or []) if sekarang - float(x) < 60]
    riwayat.append(sekarang)
    data["menit"] = riwayat[-20:]
    return len(riwayat)


def boleh_kirim(guild_id: int, user_id: int, *, sekarang: float | None = None) -> bool:
    """Batas anti-banjir: maksimal `max_per_menit` DM per member per menit."""
    cfg = peek_config(guild_id)
    batas = max(1, _to_int(cfg.get("max_per_menit"), MAX_ALERT_PER_MENIT))
    data = (hl_members.get(_to_int(guild_id)) or {}).get(_to_int(user_id)) or {}
    sekarang = float(sekarang if sekarang is not None else time.time())
    jumlah = sum(1 for x in (data.get("menit") or []) if sekarang - float(x) < 60)
    return jumlah < batas


def cuplikan(teks: str, kata: str, *, maks: int = PANJANG_CUPLIKAN) -> str:
    """Potong isi pesan di sekitar kata kunci supaya DM tetap ringkas."""
    isi = re.sub(r"\s+", " ", str(teks or "")).strip()
    if not isi:
        return ""
    posisi = isi.lower().find(str(kata or "").lower())
    awal = max(0, posisi - maks // 3) if posisi > 0 else 0
    potong = isi[awal : awal + maks]
    return ("…" if awal else "") + potong + ("…" if awal + maks < len(isi) else "")


# ==============================================================================
# STATISTIK
# ==============================================================================
def statistik(guild_id: int) -> dict:
    """Ringkasan untuk dashboard & `/pantau daftar`."""
    gid = _to_int(guild_id)
    cfg = peek_config(gid)
    semua = hl_members.get(gid) or {}
    jumlah_kata: dict[str, int] = {}
    total = 0
    for data in semua.values():
        for kata in (data or {}).get("keywords") or []:
            jumlah_kata[kata] = jumlah_kata.get(kata, 0) + 1
            total += 1
    teratas = sorted(jumlah_kata.items(), key=lambda pasangan: (-pasangan[1], pasangan[0]))[:5]
    return {
        "aktif": bool(cfg.get("enabled", True)),
        "abaikan_channel": list(cfg.get("abaikan_channel") or []),
        "max_per_menit": _to_int(cfg.get("max_per_menit"), MAX_ALERT_PER_MENIT),
        "pelanggan": sum(1 for data in semua.values() if (data or {}).get("keywords")),
        "total_kata": total,
        "teratas": teratas,
        "hit": sum(_to_int((data or {}).get("hit")) for data in semua.values()),
    }


def daftar_pelanggan(guild_id: int) -> list[dict]:
    """Pelanggan highlight (untuk panel dashboard), urut dari yang paling aktif."""
    hasil = []
    for uid, data in (hl_members.get(_to_int(guild_id)) or {}).items():
        data = data or {}
        if not data.get("keywords"):
            continue
        hasil.append(
            {
                "user_id": _to_int(uid),
                "keywords": list(data.get("keywords") or []),
                "hit": _to_int(data.get("hit")),
            }
        )
    hasil.sort(key=lambda baris: (-baris["hit"], baris["user_id"]))
    return hasil


def reset_runtime_state() -> None:
    hl_config.clear()
    hl_members.clear()
    _index.clear()


def cleanup_highlights_runtime(limit: int = 200) -> int:
    """Pangkas server tanpa pelanggan agar hemat RAM Free Tier."""
    hapus = 0
    for gid in set(hl_config) | set(hl_members):
        punya_kata = any(
            (data or {}).get("keywords") for data in (hl_members.get(gid) or {}).values()
        )
        if not punya_kata:
            hl_members.pop(gid, None)
            hl_config.pop(gid, None)
            _index.pop(gid, None)
            hapus += 1
    if len(hl_config) > limit:
        for gid in list(hl_config)[: len(hl_config) - limit]:
            hl_config.pop(gid, None)
            hl_members.pop(gid, None)
            _index.pop(gid, None)
            hapus += 1
    return hapus


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_highlights_from_disk() -> tuple[int, int]:
    """Muat setelan & pelanggan → `(jumlah server, jumlah pelanggan)`."""
    hl_config.clear()
    hl_members.clear()
    _index.clear()
    if not Path(HIGHLIGHTS_FILE).exists():
        return 0, 0
    try:
        raw = json.loads(Path(HIGHLIGHTS_FILE).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", HIGHLIGHTS_FILE, exc)
        return 0, 0

    total = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str, -1)
        if gid < 0 or not isinstance(data, dict):
            continue
        cfg = default_config()
        sumber = data.get("config") if isinstance(data.get("config"), dict) else {}
        cfg["enabled"] = bool(sumber.get("enabled", True))
        cfg["abaikan_channel"] = _daftar_id(sumber.get("abaikan_channel"))
        cfg["max_per_menit"] = max(
            1, min(MAX_ALERT_PER_MENIT, _to_int(sumber.get("max_per_menit"), MAX_ALERT_PER_MENIT))
        )
        hl_config[gid] = cfg

        anggota: dict[int, dict] = {}
        for uid_str, isi in (data.get("members") or {}).items():
            uid = _to_int(uid_str, -1)
            if uid < 0 or not isinstance(isi, dict):
                continue
            kata = [normalisasi(k) for k in (isi.get("keywords") or [])]
            kata = [k for k in dict.fromkeys(kata) if k and len(k) <= MAX_KATA_PANJANG]
            catatan = {
                "keywords": kata[:MAX_KATA_PER_MEMBER],
                "abaikan_channel": _daftar_id(isi.get("abaikan_channel")),
                "abaikan_kata": [
                    normalisasi(k) for k in (isi.get("abaikan_kata") or []) if normalisasi(k)
                ][:MAX_ABAIKAN_KATA],
                "hit": max(0, _to_int(isi.get("hit"))),
                "diperbarui": float(isi.get("diperbarui") or 0),
            }
            if catatan["keywords"] or catatan["hit"]:
                anggota[uid] = catatan
        if anggota:
            hl_members[gid] = anggota
            total += len(anggota)
    return len(hl_config) or len(hl_members), total


async def save_highlights_to_disk() -> None:
    """Simpan setelan & pelanggan secara atomik (tanpa isi pesan)."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            semua = set(hl_config) | set(hl_members)
            payload = {
                "guilds": {
                    str(gid): {
                        "config": hl_config.get(gid),
                        "members": {
                            str(uid): {
                                "keywords": data.get("keywords") or [],
                                "abaikan_channel": data.get("abaikan_channel") or [],
                                "abaikan_kata": data.get("abaikan_kata") or [],
                                "hit": data.get("hit") or 0,
                                "diperbarui": data.get("diperbarui") or 0,
                            }
                            for uid, data in (hl_members.get(gid) or {}).items()
                        },
                    }
                    for gid in semua
                }
            }
            sementara = Path(str(HIGHLIGHTS_FILE) + ".tmp")
            await asyncio.to_thread(
                sementara.write_text, json.dumps(payload, ensure_ascii=False, indent=2), "utf-8"
            )
            await asyncio.to_thread(os.replace, sementara, HIGHLIGHTS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan highlights.json: %s", exc)
