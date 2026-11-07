"""Panel Keamanan di dashboard: **penguji aturan** & **statistik per aturan**.

Kenapa di modul sendiri?
    `antispam.py` adalah mesin penindak (dipakai jalur pesan Discord). Dashboard hanya
    butuh dua hal tambahan: menyimpan **hasil uji terakhir** per server (supaya tetap
    terlihat setelah redirect, tanpa JavaScript) dan merangkum statistiknya.

Semua pemanggilan di sini **tidak menindak apa pun**: tidak menghapus pesan, tidak
me-time-out member, dan tidak mencatat riwayat spam (lihat `antispam.uji_aturan`).
"""

import logging

logger = logging.getLogger("gemini_bot.dashboard_keamanan")

#: Hasil uji terakhir per server (hanya di memori — hilang saat restart, dan itu cukup).
_uji_terakhir: dict[int, dict] = {}


def reset() -> None:
    """Membersihkan cache hasil uji (dipakai tes)."""
    _uji_terakhir.clear()


def terakhir(guild_id: int) -> dict | None:
    """Hasil uji aturan terakhir untuk server ini (None bila belum pernah)."""
    return _uji_terakhir.get(int(guild_id or 0))


def uji(guild_id: int, teks: str, *, ulang: int = 1) -> tuple[bool, str]:
    """Menjalankan penguji aturan; hasilnya disimpan untuk ditampilkan lagi."""
    import antispam

    gid = int(guild_id or 0)
    isi = str(teks or "")
    if not isi.strip():
        return False, "Tempel contoh pesan dulu — penguji tidak mengubah isi channel."

    hasil = antispam.uji_aturan(isi, guild_id=gid, ulang=ulang)
    _uji_terakhir[gid] = hasil

    if not hasil.get("kena"):
        return True, (
            "Tidak ada aturan yang kena. Pesan ini aman menurut setelan sekarang."
        )
    label = {item["kunci"]: item["label"] for item in hasil.get("aturan") or []}
    daftar = ", ".join(str(label.get(kunci, kunci)).split(" ", 1)[-1] for kunci in hasil["kena"])
    return True, (
        f"{len(hasil['kena'])} aturan kena: {daftar}. Tidak ada pesan yang dihapus — "
        "ini hanya simulasi."
    )


def collect(guild_id: int) -> dict:
    """Data untuk blok dashboard: statistik per aturan + hasil uji terakhir."""
    import antispam

    gid = int(guild_id or 0)
    return {
        "statistik": antispam.statistik_aturan(gid),
        "uji": _uji_terakhir.get(gid),
        "aturan": list(antispam.ATURAN_UJI),
    }
