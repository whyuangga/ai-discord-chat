"""Snipe & EditSnipe — lihat pesan yang baru dihapus/diubah (ala wisp).

Prinsip keamanan & hemat RAM:
    - **Hanya di memori.** Tidak ada isi pesan yang ditulis ke disk, jadi restart bot
      (atau server mati) otomatis menghapus jejaknya. Tidak ada `data/*.json` baru.
    - **Batas keras:** 5 pesan terakhir per channel & maksimal 300 channel per server.
    - **Khusus staf:** command `/snipe` memakai izin *Manage Messages*.
    - Bot & pesan kosong (tanpa teks/lampiran) tidak dicatat.

Catatan: snipe berguna untuk kasus "pesan dihapus sebelum staf sempat melihat", bukan
untuk mengawasi member. Karena itu datanya sengaja **tidak** persisten.
"""

from __future__ import annotations

import time

MAX_PER_CHANNEL = 5
MAX_CHANNEL = 300
ISI_MAKS = 900

SALAH_KUNCI = ("enabled", "hapus", "edit")

snipe_config: dict[int, dict] = {}
#: {channel_id: [{"user_id", "nama", "isi", "lampiran", "kanal_id", "waktu"}]}
_hapus: dict[int, list[dict]] = {}
_edit: dict[int, list[dict]] = {}


def default_config() -> dict:
    return {"enabled": True, "hapus": True, "edit": True}


def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def get_config(guild_id: int) -> dict:
    gid = _to_int(guild_id)
    cfg = snipe_config.get(gid)
    if cfg is None:
        cfg = default_config()
        snipe_config[gid] = cfg
    return cfg


def peek_config(guild_id: int) -> dict:
    cfg = snipe_config.get(_to_int(guild_id))
    return dict(cfg) if cfg else default_config()


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    hapus: bool | None = None,
    edit: bool | None = None,
) -> dict:
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if hapus is not None:
        cfg["hapus"] = bool(hapus)
    if edit is not None:
        cfg["edit"] = bool(edit)
    return cfg


def aktif(guild_id: int, *, jenis: str = "hapus") -> bool:
    cfg = peek_config(guild_id)
    if not cfg.get("enabled", True):
        return False
    return bool(cfg.get(jenis if jenis in ("hapus", "edit") else "hapus", True))


def _rapikan_channel(peta: dict[int, list[dict]]) -> None:
    """Jaga RAM: kalau channel tersimpan melebihi batas, buang yang paling lama."""
    if len(peta) <= MAX_CHANNEL:
        return
    urut = sorted(
        peta.items(),
        key=lambda pasangan: max((e.get("waktu") or 0) for e in pasangan[1]) if pasangan[1] else 0,
    )
    for cid, _ in urut[: len(urut) - MAX_CHANNEL]:
        peta.pop(cid, None)


def _entri(objek, *, isi: str | None = None, keterangan: str = "") -> dict:
    author = getattr(objek, "author", None)
    lampiran = [str(getattr(a, "filename", "") or "") for a in (getattr(objek, "attachments", []) or [])]
    return {
        "user_id": _to_int(getattr(author, "id", 0)),
        "nama": str(getattr(author, "display_name", "") or getattr(author, "name", "") or "-")[:60],
        "isi": str(isi if isi is not None else getattr(objek, "content", ""))[:ISI_MAKS],
        "lampiran": [nama for nama in lampiran if nama][:5],
        "kanal_id": _to_int(getattr(getattr(objek, "channel", None), "id", 0)),
        "waktu": time.time(),
        "keterangan": keterangan,
    }


def catat_hapus(message) -> bool:
    """Catat satu pesan yang dihapus → `True` bila disimpan."""
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    if guild is None or author is None or getattr(author, "bot", False):
        return False
    if not aktif(guild.id, jenis="hapus"):
        return False
    entri = _entri(message)
    if not entri["isi"].strip() and not entri["lampiran"]:
        return False
    daftar = _hapus.setdefault(entri["kanal_id"], [])
    daftar.append(entri)
    del daftar[:-MAX_PER_CHANNEL]
    _rapikan_channel(_hapus)
    return True


def catat_edit(before, after) -> bool:
    """Catat perubahan pesan (isi sebelum & sesudah)."""
    guild = getattr(before, "guild", None) or getattr(after, "guild", None)
    author = getattr(before, "author", None)
    if guild is None or author is None or getattr(author, "bot", False):
        return False
    if not aktif(guild.id, jenis="edit"):
        return False
    lama = str(getattr(before, "content", "") or "")
    baru = str(getattr(after, "content", "") or "")
    if lama == baru:
        return False
    entri = _entri(before, isi=lama)
    entri["sesudah"] = baru[:ISI_MAKS]
    if not entri["isi"].strip() and not baru.strip():
        return False
    daftar = _edit.setdefault(entri["kanal_id"], [])
    daftar.append(entri)
    del daftar[:-MAX_PER_CHANNEL]
    _rapikan_channel(_edit)
    return True


def ambil_hapus(guild_id: int, channel_id: int, jumlah: int = 1) -> list[dict]:
    """Pesan terakhir yang dihapus di satu channel (terbaru dulu)."""
    if not aktif(guild_id, jenis="hapus"):
        return []
    daftar = list(reversed(_hapus.get(_to_int(channel_id)) or []))
    return daftar[: max(1, min(MAX_PER_CHANNEL, _to_int(jumlah, 1)))]


def ambil_edit(guild_id: int, channel_id: int, jumlah: int = 1) -> list[dict]:
    """Pesan terakhir yang diubah di satu channel (terbaru dulu)."""
    if not aktif(guild_id, jenis="edit"):
        return []
    daftar = list(reversed(_edit.get(_to_int(channel_id)) or []))
    return daftar[: max(1, min(MAX_PER_CHANNEL, _to_int(jumlah, 1)))]


def lupakan_channel(channel_id: int) -> None:
    """Buang riwayat satu channel (dipakai saat channel/thread dihapus)."""
    cid = _to_int(channel_id)
    _hapus.pop(cid, None)
    _edit.pop(cid, None)


def statistik(guild_id: int) -> dict:
    """Ringkasan untuk command & dashboard."""
    gid = _to_int(guild_id)
    channel_hapus = [cid for cid, isi in _hapus.items() if isi]
    channel_edit = [cid for cid, isi in _edit.items() if isi]
    cfg = peek_config(gid)
    return {
        "aktif": bool(cfg.get("enabled", True)),
        "hapus": bool(cfg.get("hapus", True)),
        "edit": bool(cfg.get("edit", True)),
        "channel_hapus": len(channel_hapus),
        "channel_edit": len(channel_edit),
        "entri_hapus": sum(len(isi) for isi in _hapus.values()),
        "entri_edit": sum(len(isi) for isi in _edit.values()),
        "maks_per_channel": MAX_PER_CHANNEL,
    }


def reset_runtime_state() -> None:
    snipe_config.clear()
    _hapus.clear()
    _edit.clear()


def cleanup_snipe_runtime(limit: int = MAX_CHANNEL) -> int:
    """Pangkas channel yang entrinya sudah kosong (dipanggil rutin oleh bot)."""
    hapus = 0
    for peta in (_hapus, _edit):
        for cid in [cid for cid, isi in peta.items() if not isi]:
            peta.pop(cid, None)
            hapus += 1
        _rapikan_channel(peta)
        if len(peta) > limit:
            hapus += len(peta) - limit
            _rapikan_channel(peta)
    return hapus
