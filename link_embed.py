"""Tautan embed (*link embed*) — halaman `/l/<kode>` di situs Vercel dengan tag `og:`.

Ide dari fitur *Link Embeds* Discohook: kita ingin sebuah tautan tampil sebagai embed
cantik di Discord (judul, deskripsi, gambar) tetapi saat diklik tetap membuka URL
tujuan. Discord hanya membaca embed dari **tag `og:`** pada halaman yang ditautkan,
jadi bot membuat kode yang bisa diubah menjadi halaman oleh function Vercel
`site/api/l/[id].js`.

Tanpa database: seluruh isi embed dipaketkan ke dalam kode (JSON → base64url), lalu
ditempel ke URL `https://<situs>/l/<kode>`. Artinya tautan lama tetap hidup walau bot
sedang mati, dan tidak ada data pribadi yang tersimpan di server bot.

Contoh::

    /embed tautan judul:"Panduan Server" isi:"Semua aturan & tips" url:https://situs.kamu
    → https://ai-discord-chat-site.vercel.app/l/eyJ0IjoiUGFuZHVhbi...

Batas aman `MAX_CODE` menjaga URL tetap nyaman dipakai di Discord. Berkas lokal
`data/links.json` hanya mencatat tautan yang pernah dibuat (untuk `/embed tautan daftar`
dan dihapus dari daftar) — menghapus catatan **tidak** mematikan tautannya.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import secrets
import time
from pathlib import Path

from config import DATA_DIR, LINKS_FILE, SITE_BASE_URL

logger = logging.getLogger("gemini_bot.link_embed")

_lock = asyncio.Lock()

MAX_TITLE = 200
MAX_DESCRIPTION = 600
MAX_URL = 500
MAX_IMAGE = 300
MAX_PROVIDER = 60
MAX_SITE = 60
MAX_CODE = 1200            # panjang kode base64url maksimum (URL tetap < ~1.300 karakter)
MAX_LINKS_PER_GUILD = 50
MAX_LINKS_TOTAL = 500

_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")

# data/links.json — catatan tautan yang dibuat lewat Discord
links: dict[int, dict[str, dict]] = {}      # guild_id -> link_id -> record


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _clean(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _http_only(value: str) -> str:
    """Kembalikan URL bila http(s), selain itu string kosong."""
    teks = str(value or "").strip()
    return teks if re.match(r"^https?://", teks, re.I) else ""


# ------------------------------------------------------------------------------
# PAYLOAD & KODE
# ------------------------------------------------------------------------------
def build_payload(
    *,
    title: str = "",
    description: str = "",
    url: str = "",
    image: str = "",
    thumbnail: str = "",
    color: str = "",
    provider: str = "",
    site: str = "",
) -> tuple[dict, list[str]]:
    """Susun payload embed (kunci pendek agar URL ringkas). Kembalikan `(payload, galat)`."""
    galat: list[str] = []
    tujuan = _http_only(_clean(url, MAX_URL))
    if not tujuan:
        galat.append("URL tujuan wajib diisi dan harus diawali `http://` atau `https://`.")

    judul = _clean(title, MAX_TITLE)
    isi = _clean(description, MAX_DESCRIPTION)
    if not judul and not isi:
        galat.append("Isi minimal `judul` atau `isi` — tanpa keduanya Discord tidak menampilkan embed.")

    color_hex = _clean(color, 20).lstrip("#")
    if color_hex and not _COLOR_RE.match(color_hex):
        galat.append("Warna harus kode 6 digit seperti `9B59B6` (atau kosongkan).")
        color_hex = ""

    gambar = _http_only(_clean(image, MAX_IMAGE))
    sampul = _http_only(_clean(thumbnail, MAX_IMAGE))
    if image and not gambar:
        galat.append("URL gambar harus diawali `http://` atau `https://`.")

    payload: dict = {"v": 1}
    if judul:
        payload["t"] = judul
    if isi:
        payload["d"] = isi
    if tujuan:
        payload["u"] = tujuan
    if gambar:
        payload["i"] = gambar
    if sampul:
        payload["th"] = sampul
    if color_hex:
        payload["c"] = color_hex.lower()
    if _clean(provider, MAX_PROVIDER):
        payload["p"] = _clean(provider, MAX_PROVIDER)
    if _clean(site, MAX_SITE):
        payload["s"] = _clean(site, MAX_SITE)
    return payload, galat


def encode(payload: dict) -> str:
    """Payload → kode base64url tanpa padding (aman di URL)."""
    teks = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(teks.encode("utf-8")).decode("ascii").rstrip("=")


def decode(code: str) -> dict | None:
    """Kode → payload tervalidasi. `None` bila rusak/bukan tautan bot ini."""
    teks = str(code or "").strip()
    if not teks or len(teks) > MAX_CODE or not re.fullmatch(r"[A-Za-z0-9_-]+", teks):
        return None
    padding = "=" * (-len(teks) % 4)
    try:
        mentah = base64.urlsafe_b64decode(teks + padding).decode("utf-8")
        data = json.loads(mentah)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if _to_int(data.get("v"), 0) != 1:
        return None

    hasil = {
        "title": _clean(data.get("t"), MAX_TITLE),
        "description": _clean(data.get("d"), MAX_DESCRIPTION),
        "url": _http_only(_clean(data.get("u"), MAX_URL)),
        "image": _http_only(_clean(data.get("i"), MAX_IMAGE)),
        "thumbnail": _http_only(_clean(data.get("th"), MAX_IMAGE)),
        "color": _clean(data.get("c"), 6).lower(),
        "provider": _clean(data.get("p"), MAX_PROVIDER),
        "site": _clean(data.get("s"), MAX_SITE),
    }
    if not hasil["title"] and not hasil["description"]:
        return None
    if hasil["color"] and not _COLOR_RE.match(hasil["color"]):
        hasil["color"] = ""
    return hasil


def build_url(code: str, base: str | None = None) -> str:
    """URL publik halaman embed."""
    akar = str(base or SITE_BASE_URL).rstrip("/")
    return f"{akar}/l/{code}"


def make_code(payload: dict) -> tuple[str, list[str]]:
    """Buat kode + URL dari payload. `galat` terisi bila terlalu panjang."""
    kode = encode(payload)
    if len(kode) > MAX_CODE:
        return "", [
            f"Teks terlalu panjang ({len(kode)} karakter kode, maksimal {MAX_CODE}). "
            "Ringkas judul/isi atau pakai gambar (bukan base64)."
        ]
    return kode, []


# ------------------------------------------------------------------------------
# CATATAN TAUTAN (data/links.json)
# ------------------------------------------------------------------------------
def new_link_id() -> str:
    return "l" + secrets.token_hex(4)


def get_link(guild_id: int, ref: str) -> dict | None:
    """Cari tautan lewat ID atau judulnya."""
    bucket = links.get(_to_int(guild_id)) or {}
    bersih = str(ref or "").strip()
    if not bersih:
        return None
    if bersih in bucket:
        return bucket[bersih]
    kecil = bersih.casefold()
    for record in bucket.values():
        if str(record.get("title", "")).casefold() == kecil:
            return record
    return None


def list_links(guild_id: int) -> list[dict]:
    bucket = links.get(_to_int(guild_id)) or {}
    return sorted(bucket.values(), key=lambda r: float(r.get("created_at") or 0))


def create_link(
    guild_id: int,
    *,
    title: str = "",
    description: str = "",
    url: str = "",
    image: str = "",
    thumbnail: str = "",
    color: str = "",
    provider: str = "",
    site: str = "",
    created_by: int | None = None,
) -> tuple[dict | None, list[str]]:
    """Buat tautan embed. Kembalikan `(record, galat)`; `record` berisi `url` siap kirim."""
    gid = _to_int(guild_id)
    bucket = links.setdefault(gid, {})
    if len(bucket) >= MAX_LINKS_PER_GUILD:
        return None, [f"Kuota tautan server penuh (maksimal {MAX_LINKS_PER_GUILD}). Hapus yang lama dulu."]

    payload, galat = build_payload(
        title=title,
        description=description,
        url=url,
        image=image,
        thumbnail=thumbnail,
        color=color,
        provider=provider,
        site=site,
    )
    if galat:
        return None, galat

    kode, galat_kode = make_code(payload)
    if galat_kode:
        return None, galat_kode

    link_id = new_link_id()
    while link_id in bucket:
        link_id = new_link_id()

    record = {
        "id": link_id,
        "guild_id": gid,
        "title": payload.get("t") or payload.get("d", "")[:60] or "Tautan",
        "code": kode,
        "url": build_url(kode),
        "target": payload.get("u", ""),
        "created_by": _to_int(created_by) or None,
        "created_at": time.time(),
    }
    bucket[link_id] = record
    return record, []


def delete_link(guild_id: int, ref: str) -> dict | None:
    record = get_link(guild_id, ref)
    if record is None:
        return None
    (links.get(_to_int(guild_id)) or {}).pop(record["id"], None)
    return record


def stats(guild_id: int) -> dict:
    bucket = links.get(_to_int(guild_id)) or {}
    total = sum(len(b) for b in links.values())
    return {"total": len(bucket), "semua": total, "maks": MAX_LINKS_PER_GUILD}


# ------------------------------------------------------------------------------
# SIMPAN / MUAT
# ------------------------------------------------------------------------------
def _record_payload(record: dict) -> dict:
    return {
        "id": record.get("id"),
        "title": record.get("title"),
        "code": record.get("code"),
        "url": record.get("url"),
        "target": record.get("target"),
        "created_by": record.get("created_by"),
        "created_at": record.get("created_at"),
    }


def load_from_disk() -> int:
    """Muat catatan tautan dari `data/links.json`."""
    links.clear()
    path = Path(LINKS_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    total = 0
    for gid_str, bucket in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(bucket, dict):
            continue
        for link_id, data in bucket.items():
            if not isinstance(data, dict):
                continue
            kode = str(data.get("code") or "").strip()
            if not kode or decode(kode) is None:
                continue  # kode rusak/tidak bisa dipakai lagi
            links.setdefault(gid, {})[str(link_id)] = {
                "id": str(data.get("id") or link_id),
                "guild_id": gid,
                "title": _clean(data.get("title"), MAX_TITLE) or "Tautan",
                "code": kode,
                "url": build_url(kode),
                "target": _http_only(_clean(data.get("target"), MAX_URL)),
                "created_by": _to_int(data.get("created_by")) or None,
                "created_at": float(data.get("created_at") or 0),
            }
            total += 1
    return total


async def save_to_disk() -> None:
    """Simpan catatan tautan ke `data/links.json` (atomik)."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            isi = {
                "version": 1,
                "guilds": {
                    str(gid): {lid: _record_payload(rec) for lid, rec in bucket.items()}
                    for gid, bucket in links.items()
                },
            }
            sementara = Path(str(LINKS_FILE) + ".tmp")
            sementara.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding="utf-8")
            sementara.replace(Path(LINKS_FILE))
        except Exception as exc:  # pragma: no cover - IO jarang gagal
            logger.warning("Gagal menyimpan %s: %s", LINKS_FILE, exc)


__all__ = [
    "MAX_CODE",
    "MAX_DESCRIPTION",
    "MAX_LINKS_PER_GUILD",
    "MAX_TITLE",
    "build_payload",
    "build_url",
    "create_link",
    "decode",
    "delete_link",
    "encode",
    "get_link",
    "links",
    "list_links",
    "load_from_disk",
    "make_code",
    "save_to_disk",
    "stats",
]
