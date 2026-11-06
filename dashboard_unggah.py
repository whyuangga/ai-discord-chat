"""Unggah & simpan banner/gambar dari dashboard web (tanpa dependency baru).

Berkas disimpan di `data/uploads/`, satu nama unik per unggahan, dan dipakai untuk:

- **banner panel menu** (`menu_builder.send_panel(banner_file=...)`),
- **gambar embed** saat mengirim pesan (`attachment://<nama>`),
- **identitas webhook** (pesan + lampiran).

Keamanan:

1. Ekstensi di-whitelist (`png`, `jpg`, `jpeg`, `gif`, `webp`) **dan** isi berkas
   diperiksa lewat *magic bytes* — file `.exe` yang di-rename tetap ditolak.
2. Ukuran dibatasi `DASHBOARD_UPLOAD_MB` (bawaan 8 MB) dan jumlah banner per server
   dibatasi `MAX_PER_GUILD`.
3. Nama berkas selalu dibuat ulang (`<guild>_<waktu>_<acak>.<ext>`) sehingga tidak ada
   path traversal dan tidak ada tabrakan nama.
"""

import io
import logging
import os
import re
import time
import uuid
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger("gemini_bot.dashboard_unggah")

UPLOAD_DIR = Path(DATA_DIR) / "uploads"
MAX_PER_GUILD = 20
DEFAULT_MAX_MB = 8
EKSTENSI = {"png", "jpg", "jpeg", "gif", "webp"}
NAMA_AMAN = re.compile(r"^[0-9A-Za-z_.-]{1,120}$")
_TIPE = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def batas_mb() -> int:
    """Batas ukuran unggahan (MB) dari env, dengan jaring aman 1–25."""
    try:
        nilai = int(str(os.getenv("DASHBOARD_UPLOAD_MB") or DEFAULT_MAX_MB).strip())
    except ValueError:
        nilai = DEFAULT_MAX_MB
    return max(1, min(25, nilai))


def batas_byte() -> int:
    return batas_mb() * 1024 * 1024


# ==============================================================================
# VALIDASI
# ==============================================================================
def _ekstensi(nama: str) -> str:
    akhiran = str(nama or "").rsplit(".", 1)[-1].lower() if "." in str(nama or "") else ""
    return akhiran if akhiran in EKSTENSI else ""


def _cocok_magic(data: bytes) -> str:
    """Tebak format gambar dari beberapa byte pertama; '' bila bukan gambar."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return ""


def periksa(data: bytes, nama: str) -> tuple[str, str]:
    """Validasi isi & nama berkas. Kembalikan `(ekstensi, galat)`."""
    if not data:
        return "", "Berkas kosong."
    batas = batas_byte()
    if len(data) > batas:
        return "", f"Ukuran berkas melebihi {batas_mb()} MB."
    ekstensi = _ekstensi(nama)
    if not ekstensi:
        return "", "Format harus PNG, JPG, GIF, atau WEBP."
    tipe = _cocok_magic(data)
    if not tipe:
        return "", "Isi berkas bukan gambar yang valid (PNG/JPG/GIF/WEBP)."
    if ekstensi in ("jpg", "jpeg") and tipe != "jpeg":
        return "", "Ekstensi `.jpg` tetapi isi berkas bukan JPEG."
    if ekstensi == "png" and tipe != "png":
        return "", "Ekstensi `.png` tetapi isi berkas bukan PNG."
    if ekstensi == "gif" and tipe != "gif":
        return "", "Ekstensi `.gif` tetapi isi berkas bukan GIF."
    if ekstensi == "webp" and tipe != "webp":
        return "", "Ekstensi `.webp` tetapi isi berkas bukan WEBP."
    return ekstensi, ""


# ==============================================================================
# SIMPAN / BACA / HAPUS
# ==============================================================================
def _folder() -> Path:
    path = Path(UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _awalan(guild_id: int) -> str:
    return f"{_to_int(guild_id)}_"


def daftar(guild_id: int) -> list[dict]:
    """Semua banner milik satu server (terbaru lebih dulu)."""
    awalan = _awalan(guild_id)
    folder = _folder()
    hasil: list[dict] = []
    try:
        for path in folder.glob(f"{awalan}*"):
            if not path.is_file() or path.suffix.lower().lstrip(".") not in EKSTENSI:
                continue
            try:
                info = path.stat()
            except OSError:  # pragma: no cover - berkas hilang di tengah jalan
                continue
            hasil.append(
                {
                    "nama": path.name,
                    "ukuran_kb": max(1, round(info.st_size / 1024)),
                    "dibuat": time.strftime("%Y-%m-%d %H:%M", time.localtime(info.st_mtime)),
                    "tipe": _TIPE.get(path.suffix.lower().lstrip("."), "image/png"),
                }
            )
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal membaca folder unggahan: %s", exc)
    return sorted(hasil, key=lambda item: item["dibuat"], reverse=True)


def jumlah(guild_id: int) -> int:
    return len(daftar(guild_id))


def simpan(guild_id: int, data: bytes, nama_asli: str) -> tuple[dict | None, str]:
    """Simpan berkas unggahan. Kembalikan `(record, galat)`."""
    ekstensi, galat = periksa(data, nama_asli)
    if galat:
        return None, galat
    if jumlah(guild_id) >= MAX_PER_GUILD:
        return None, f"Kuota banner server penuh ({MAX_PER_GUILD} berkas) — hapus yang lama dulu."

    nama = f"{_awalan(guild_id)}{int(time.time())}_{uuid.uuid4().hex[:8]}.{ekstensi}"
    try:
        folder = _folder()
        sementara = folder / f".{nama}.tmp"
        sementara.write_bytes(data)
        sementara.replace(folder / nama)
    except Exception as exc:  # pragma: no cover - IO jarang gagal
        logger.warning("Gagal menyimpan banner: %s", exc)
        return None, "Gagal menyimpan berkas di server."
    return {
        "nama": nama,
        "ukuran_kb": max(1, round(len(data) / 1024)),
        "tipe": _TIPE.get(ekstensi, "image/png"),
    }, ""


def berkuasa(guild_id: int, nama: str) -> bool:
    """True bila `nama` adalah banner milik server ini (aman dari path traversal)."""
    return bool(NAMA_AMAN.match(str(nama or ""))) and str(nama).startswith(_awalan(guild_id))


def baca(guild_id: int, nama: str) -> bytes | None:
    """Isi berkas banner (divalidasi kepemilikannya)."""
    if not berkuasa(guild_id, nama):
        return None
    path = _folder() / str(nama)
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:  # pragma: no cover
        return None


def tipe(nama: str) -> str:
    akhiran = str(nama or "").rsplit(".", 1)[-1].lower()
    return _TIPE.get(akhiran, "application/octet-stream")


def hapus(guild_id: int, nama: str) -> bool:
    """Hapus satu banner milik server."""
    if not berkuasa(guild_id, nama):
        return False
    path = _folder() / str(nama)
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError as exc:  # pragma: no cover
        logger.warning("Gagal menghapus banner %s: %s", nama, exc)
    return False


def berkas_discord(guild_id: int, nama: str):
    """`discord.File` siap kirim dari banner tersimpan (None bila tidak ada)."""
    isi = baca(guild_id, nama)
    if isi is None:
        return None
    try:
        import discord

        return discord.File(io.BytesIO(isi), filename=str(nama))
    except Exception:  # pragma: no cover - discord belum siap
        return None


def berkas_dari_data(nama: str, data: bytes):
    """`discord.File` dari data mentah (hasil unggahan baru, belum tersimpan)."""
    try:
        import discord

        return discord.File(io.BytesIO(data), filename=str(nama))
    except Exception:  # pragma: no cover
        return None


# ==============================================================================
# BANTUAN FORM
# ==============================================================================
def siapkan(guild_id: int, medan=None, tersimpan: str = "") -> tuple[object | None, str, str]:
    """Siapkan `discord.File` dari unggahan baru **atau** banner tersimpan.

    Kembalikan `(berkas, galat, nama)`. `berkas` = `None` bila tidak ada banner.
    Unggahan baru langsung disimpan ke `data/uploads/` supaya bisa dipakai ulang.
    """
    if medan is not None:
        try:
            data = medan.file.read()
        except Exception:  # pragma: no cover - jarang
            return None, "Berkas tidak bisa dibaca.", ""
        if data:
            record, galat = simpan(guild_id, data, getattr(medan, "filename", "") or "")
            if galat:
                return None, galat, ""
            nama = str((record or {}).get("nama") or "")
            return berkas_dari_data(nama, data), "", nama

    nama = str(tersimpan or "").strip()
    if not nama:
        return None, "", ""
    berkas = berkas_discord(guild_id, nama)
    if berkas is None:
        return None, "Banner tersimpan tidak ditemukan (mungkin sudah dihapus).", ""
    return berkas, "", nama


__all__ = [
    "EKSTENSI",
    "JENIS_KARTU",
    "LABEL_KARTU",
    "MAX_PER_GUILD",
    "baca",
    "baca_kartu",
    "batas_byte",
    "batas_mb",
    "berkas_dari_data",
    "berkas_discord",
    "berkuasa",
    "daftar",
    "hapus",
    "hapus_kartu",
    "kartu_info",
    "jumlah",
    "periksa",
    "siapkan",
    "simpan",
    "simpan_kartu",
    "tipe",
]


# ==============================================================================
# KARTU SAMBUTAN / PERPISAHAN / BOOST (disimpan di `data/media/`)
# ==============================================================================
# Berbeda dari banner di atas (dipakai untuk panel & embed), kartu di sini adalah
# **latar kartu sambutan** yang dikirim bot saat member bergabung/keluar — berkas
# aslinya disimpan `welcome_media` supaya bisa dikirim ulang sebagai lampiran
# (`attachment://`) tanpa URL kedaluwarsa.
JENIS_KARTU: tuple[str, ...] = ("welcome", "goodbye", "boost")
LABEL_KARTU: dict[str, str] = {
    "welcome": "sambutan",
    "goodbye": "perpisahan",
    "boost": "ucapan boost",
}


def normalisasi_kartu(jenis: str) -> str:
    """Jenis kartu yang sah (`welcome` / `goodbye` / `boost`), '' bila tidak dikenal."""
    kunci = str(jenis or "").strip().lower()
    return kunci if kunci in JENIS_KARTU else ""


def kartu_info(guild_id: int) -> dict[str, dict | None]:
    """Ringkasan kartu server: `{jenis: {nama, ukuran_kb, dibuat, tipe} | None}`."""
    import welcome_media

    hasil: dict[str, dict | None] = {}
    for jenis in JENIS_KARTU:
        path = welcome_media.banner_path(int(guild_id or 0), kind=jenis)
        if path is None:
            hasil[jenis] = None
            continue
        try:
            info = path.stat()
        except OSError:  # pragma: no cover - berkas hilang di tengah jalan
            hasil[jenis] = None
            continue
        hasil[jenis] = {
            "nama": path.name,
            "ukuran_kb": max(1, round(info.st_size / 1024)),
            "dibuat": time.strftime("%Y-%m-%d %H:%M", time.localtime(info.st_mtime)),
            "tipe": _TIPE.get(path.suffix.lower().lstrip("."), "image/png"),
        }
    return hasil


def simpan_kartu(guild_id: int, medan, jenis: str) -> tuple[bool, str]:
    """Validasi & simpan kartu sambutan dari unggahan dashboard."""
    kunci = normalisasi_kartu(jenis)
    if not kunci:
        return False, "Jenis kartu tidak dikenal (hanya welcome/goodbye/boost)."
    if medan is None:
        return False, "Pilih berkas gambar kartu lebih dulu."
    try:
        data = medan.file.read()
    except Exception:  # pragma: no cover - jarang
        return False, "Berkas tidak bisa dibaca."
    ekstensi, galat = periksa(data, getattr(medan, "filename", "") or "")
    if galat:
        return False, galat
    try:
        import welcome_media

        path = welcome_media.save_banner(
            int(guild_id or 0), data, f"kartu.{ekstensi}", kind=kunci
        )
    except ValueError as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover - IO jarang gagal
        logger.warning("Gagal menyimpan kartu %s: %s", kunci, exc)
        return False, "Gagal menyimpan kartu di server."
    return True, (
        f"Kartu {LABEL_KARTU[kunci]} tersimpan (`{path.name}`, {max(1, round(len(data) / 1024))} KB)."
    )


def hapus_kartu(guild_id: int, jenis: str) -> tuple[bool, str]:
    """Hapus kartu server (bot kembali mengirim teks/embed biasa)."""
    kunci = normalisasi_kartu(jenis)
    if not kunci:
        return False, "Jenis kartu tidak dikenal."
    try:
        import welcome_media

        terhapus = welcome_media.delete_banner(int(guild_id or 0), kind=kunci)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal menghapus kartu %s: %s", kunci, exc)
        return False, "Gagal menghapus kartu."
    if terhapus:
        return True, f"Kartu {LABEL_KARTU[kunci]} dihapus."
    return False, f"Belum ada kartu {LABEL_KARTU[kunci]} yang tersimpan."


def baca_kartu(guild_id: int, jenis: str) -> tuple[bytes | None, str]:
    """Isi berkas kartu untuk pratinjau di dashboard: `(data, tipe)`."""
    kunci = normalisasi_kartu(jenis)
    if not kunci:
        return None, "application/octet-stream"
    import welcome_media

    path = welcome_media.banner_path(int(guild_id or 0), kind=kunci)
    if path is None:
        return None, "application/octet-stream"
    try:
        return path.read_bytes(), _TIPE.get(path.suffix.lower().lstrip("."), "image/png")
    except OSError:  # pragma: no cover
        return None, "application/octet-stream"
