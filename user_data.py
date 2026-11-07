"""Privasi mandiri: `/dataku` (ekspor) & `/hapusdataku` (hapus permanen).

Diambil dari janji **purpleGPT**: *"export or delete your data anytime"*. Semua data
disimpan lokal di `data/*.json`, jadi ekspor & hapus bisa dilakukan tanpa proses baru.

Prinsip:

- **Hanya data milik user itu** yang disentuh (kunci `"guild:user"` atau `user_id`).
- Setiap modul dibungkus `try/except` sendiri, jadi satu modul rusak tidak menggagalkan
  seluruh ekspor/penghapusan.
- Isi pesan tidak pernah disimpan oleh bot ini (curhat & snipe hanya metadata), jadi tidak
  ada yang perlu dihapus di sana — cukup dilaporkan jumlahnya.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("gemini_bot.user_data")

MAKS_BARIS = 500


def _to_int(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


# ==============================================================================
# KUMPULKAN (EKSPOR)
# ==============================================================================


def _kumpulkan_level(uid: int) -> dict:
    """Ambil level milik satu user; galat apa pun jadi penanda `galat`."""
    # 1. Level & XP
    try:
        import levels

        baris = []
        for kunci, data in list(levels.levels.items()):
            gid_str, _, uid_str = kunci.partition(":")
            if _to_int(uid_str) == uid:
                baris.append({"guild_id": _to_int(gid_str), **{
                    k: data.get(k) for k in ("xp", "level", "messages", "last_at") if k in data
                }})
        return {"jumlah": len(baris), "data": baris[:MAKS_BARIS]}
    except Exception:  # pragma: no cover - jaring aman
        return {"galat": True}


def _kumpulkan_ekonomi(uid: int) -> dict:
    """Ambil ekonomi milik satu user; galat apa pun jadi penanda `galat`."""
    # 2. Ekonomi
    try:
        import economy

        saldo = []
        for kunci, nilai in list(economy.balances.items()):
            gid_str, _, uid_str = kunci.partition(":")
            if _to_int(uid_str) == uid:
                saldo.append(
                    {
                        "guild_id": _to_int(gid_str),
                        "koin": int(nilai or 0),
                        "meta": economy.meta.get(kunci) or {},
                    }
                )
        return {"jumlah": len(saldo), "data": saldo[:MAKS_BARIS]}
    except Exception:  # pragma: no cover
        return {"galat": True}


def _kumpulkan_lencana(uid: int) -> dict:
    """Ambil lencana milik satu user; galat apa pun jadi penanda `galat`."""
    # 3. Lencana (achievements)
    try:
        import achievements

        lencana = []
        for gid, anggota in list(achievements.ach_members.items()):
            data = (anggota or {}).get(uid)
            if data:
                lencana.append({"guild_id": gid, "lencana": data})
        return {"jumlah": len(lencana), "data": lencana[:MAKS_BARIS]}
    except Exception:  # pragma: no cover
        return {"galat": True}


def _kumpulkan_highlight(uid: int) -> dict:
    """Ambil highlight milik satu user; galat apa pun jadi penanda `galat`."""
    # 4. Highlight kata kunci
    try:
        import highlights

        pantau = []
        for gid, anggota in list(highlights.hl_members.items()):
            data = (anggota or {}).get(uid)
            if data:
                pantau.append(
                    {
                        "guild_id": gid,
                        "kata_kunci": data.get("keywords") or [],
                        "abaikan_channel": data.get("ignore_channels") or [],
                        "hit": data.get("hit") or 0,
                    }
                )
        return {"jumlah": len(pantau), "data": pantau[:MAKS_BARIS]}
    except Exception:  # pragma: no cover
        return {"galat": True}


def _kumpulkan_ultah(uid: int) -> dict:
    """Ambil ultah milik satu user; galat apa pun jadi penanda `galat`."""
    # 5. Ulang tahun
    try:
        import engagement

        ultah = []
        for kunci, data in list(engagement.birthdays.items()):
            gid_str, _, uid_str = kunci.partition(":")
            if _to_int(uid_str) == uid:
                ultah.append({"guild_id": _to_int(gid_str), "data": data})
        return {"jumlah": len(ultah), "data": ultah[:MAKS_BARIS]}
    except Exception:  # pragma: no cover
        return {"galat": True}


def _kumpulkan_game(uid: int) -> dict:
    """Ambil game milik satu user; galat apa pun jadi penanda `galat`."""
    # 6. Skor game
    try:
        import games

        skor = []
        for gid, papan in list(games.guild_game_scores.items()):
            for nama_game, isi in (papan or {}).items():
                nilai = (isi or {}).get(uid) if isinstance(isi, dict) else None
                if nilai:
                    skor.append({"guild_id": gid, "game": nama_game, "data": nilai})
        return {"jumlah": len(skor), "data": skor[:MAKS_BARIS]}
    except Exception:  # pragma: no cover
        return {"galat": True}


def _kumpulkan_formulir(uid: int) -> dict:
    """Ambil formulir milik satu user; galat apa pun jadi penanda `galat`."""
    # 7. Formulir yang pernah dikirim (antrean dashboard)
    try:
        import modal_forms

        kiriman = []
        for gid, isi in list((modal_forms.form_inbox or {}).items()):
            for nomor, entri in (isi or {}).items():
                if _to_int(entri.get("user_id")) == uid:
                    kiriman.append(
                        {
                            "guild_id": gid,
                            "nomor": nomor,
                            "form": entri.get("form_nama"),
                            "dibuat": entri.get("dibuat"),
                            "nilai": entri.get("nilai") or {},
                        }
                    )
        return {"jumlah": len(kiriman), "data": kiriman[:MAKS_BARIS]}
    except Exception:  # pragma: no cover
        return {"galat": True}


def kumpulkan(user_id: int) -> dict:
    """Kumpulkan semua data milik satu user dari seluruh modul."""
    uid = _to_int(user_id)
    hasil: dict = {"user_id": uid, "dibuat": time.time(), "modul": {}}

    def _catat(nama: str, isi: object) -> None:
        hasil["modul"][nama] = isi

    _catat("level", _kumpulkan_level(uid))
    _catat("ekonomi", _kumpulkan_ekonomi(uid))
    _catat("lencana", _kumpulkan_lencana(uid))
    _catat("highlight", _kumpulkan_highlight(uid))
    _catat("ultah", _kumpulkan_ultah(uid))
    _catat("game", _kumpulkan_game(uid))
    _catat("formulir", _kumpulkan_formulir(uid))

    return hasil


def ringkas(data: dict) -> str:
    """Ringkasan manusiawi dari hasil `kumpulkan`."""
    modul = (data or {}).get("modul") or {}
    baris = []
    for nama, isi in modul.items():
        if not isinstance(isi, dict):
            continue
        if isi.get("galat"):
            baris.append(f"• `{nama}`: tidak tersedia")
        elif "jumlah" in isi:
            baris.append(f"• `{nama}`: {isi['jumlah']} catatan")
    return "\n".join(baris) or "_Tidak ada data pribadi yang tersimpan._"


# ==============================================================================
# HAPUS
# ==============================================================================


def hapus(user_id: int) -> dict:
    """Hapus seluruh data pribadi user. Mengembalikan jumlah per modul."""
    uid = _to_int(user_id)
    dihapus: dict[str, int] = {}

    def _hitung(nama: str, jumlah: int) -> None:
        dihapus[nama] = dihapus.get(nama, 0) + int(jumlah)

    # 1. Level
    try:
        import levels

        for kunci in [k for k in levels.levels if _to_int(k.partition(":")[2]) == uid]:
            levels.levels.pop(kunci, None)
            _hitung("level", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data level gagal: %s", exc)

    # 2. Ekonomi
    try:
        import economy

        for kunci in [k for k in economy.balances if _to_int(k.partition(":")[2]) == uid]:
            economy.balances.pop(kunci, None)
            economy.meta.pop(kunci, None)
            _hitung("ekonomi", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data ekonomi gagal: %s", exc)

    # 3. Lencana
    try:
        import achievements

        for gid, anggota in list(achievements.ach_members.items()):
            if isinstance(anggota, dict) and anggota.pop(uid, None) is not None:
                _hitung("lencana", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data lencana gagal: %s", exc)

    # 4. Highlight
    try:
        import highlights

        for gid, anggota in list(highlights.hl_members.items()):
            if isinstance(anggota, dict) and anggota.pop(uid, None) is not None:
                highlights._index.pop(gid, None)  # paksa indeks dibangun ulang
                _hitung("highlight", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data highlight gagal: %s", exc)

    # 5. Ulang tahun
    try:
        import engagement

        for kunci in [k for k in engagement.birthdays if _to_int(k.partition(":")[2]) == uid]:
            engagement.birthdays.pop(kunci, None)
            _hitung("ultah", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data ulang tahun gagal: %s", exc)

    # 6. Skor game
    try:
        import games

        for gid, papan in list(games.guild_game_scores.items()):
            for nama_game, isi in list((papan or {}).items()):
                if isinstance(isi, dict) and isi.pop(uid, None) is not None:
                    _hitung("game", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data game gagal: %s", exc)

    # 7. Formulir (antrean dashboard)
    try:
        import modal_forms

        for gid, isi in list((modal_forms.form_inbox or {}).items()):
            for nomor, entri in list((isi or {}).items()):
                if _to_int(entri.get("user_id")) == uid:
                    isi.pop(nomor, None)
                    _hitung("formulir", 1)
    except Exception as exc:  # pragma: no cover - modul lain bisa berubah bentuk
        logger.warning("Hapus data formulir gagal: %s", exc)

    return dihapus


async def simpan_semua() -> None:
    """Tulis semua modul yang berubah ke disk (dipanggil setelah penghapusan)."""
    modul_simpan = (
        ("levels", "save_levels_to_disk"),
        ("economy", "save_economy_to_disk"),
        ("achievements", "save_achievements_to_disk"),
        ("highlights", "save_highlights_to_disk"),
        ("engagement", "save_engagement_to_disk"),
        ("games", "save_game_scores_to_disk"),
        ("modal_forms", "save_to_disk"),
    )
    for nama, fungsi in modul_simpan:
        try:
            module = __import__(nama)
            pemanggil = getattr(module, fungsi, None)
            if pemanggil is not None:
                await pemanggil()
        except Exception:  # pragma: no cover - jaring aman
            continue
