"""Arsip tiket berbentuk **HTML** yang bisa dibuka & dicari dari dashboard.

Kenapa HTML, bukan hanya `.txt`?
- Bisa dibaca langsung di HP tanpa mengunduh berkas.
- Pencariannya **di server** (bukan JavaScript): dashboard mengirim kata kunci,
  bot membaca berkas, lalu mengembalikan hasil + cuplikan kalimat.
- Versi `.txt` tetap disimpan untuk diunduh/di-grep staf.

Berkas: `data/transcripts/<guild_id>/tiket-0001.html` + `.txt`, indeks di
`data/transcripts/index.json`. Semua **tanpa JavaScript, tanpa dependency baru,
tanpa kuota AI**. Arsip dibatasi oleh jumlah tiket dan `TICKET_ARSIP_RETENSI_HARI`.
"""

import html
import json
import logging
import os
import time
from pathlib import Path

from config import DATA_DIR, TICKET_ARSIP_MAX, TICKET_ARSIP_RETENSI_HARI

logger = logging.getLogger("gemini_bot.ticket_archive")

ARSIP_DIR = Path(DATA_DIR) / "transcripts"
INDEX_FILE = ARSIP_DIR / "index.json"

MAX_DISIMPAN = max(10, int(TICKET_ARSIP_MAX or 200))
RETENSI_HARI = max(0, int(TICKET_ARSIP_RETENSI_HARI or 0))
MAX_CARI = 50

_index: dict[str, dict] | None = None


# ==============================================================================
# UTILITAS
# ==============================================================================
def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def _esc(nilai: object) -> str:
    return html.escape(str(nilai if nilai is not None else ""), quote=True)


def _kunci(guild_id: int, kode: object) -> str:
    return f"{int(guild_id)}:{str(kode).strip()}"


def kode_dari(data: dict) -> str:
    """Kode arsip = nomor tiket 4 digit (`0001`)."""
    return f"{_to_int((data or {}).get('number')):04d}"


def _folder(guild_id: int) -> Path:
    return ARSIP_DIR / str(int(guild_id))


def _waktu(nilai: object) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(nilai or 0)))
    except (TypeError, ValueError, OSError):
        return "-"


def _tulis_atomik(path: Path, isi: str) -> None:
    """Tulis ke berkas sementara lalu ganti nama agar arsip tidak setengah tertulis."""
    sementara = path.with_name(path.name + ".tmp")
    sementara.write_text(isi, encoding="utf-8")
    os.replace(sementara, path)


# ==============================================================================
# INDEKS
# ==============================================================================
def load_index(*, paksa: bool = False) -> dict[str, dict]:
    """Indeks arsip (dimuat sekali, disimpan lagi setiap ada perubahan)."""
    global _index
    if _index is not None and not paksa:
        return _index
    data: dict[str, dict] = {}
    try:
        if INDEX_FILE.exists():
            raw = json.loads(INDEX_FILE.read_text(encoding="utf-8")) or {}
            for kunci, item in raw.items():
                if isinstance(item, dict) and item.get("kode"):
                    data[str(kunci)] = item
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal membaca indeks arsip tiket: %s", exc)
    _index = data
    return _index


def reset_cache() -> None:
    """Lupakan indeks di memori (dipakai tes & setelah berkas diubah manual)."""
    global _index
    _index = None


def _simpan_index() -> bool:
    try:
        ARSIP_DIR.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(INDEX_FILE) + ".tmp")
        tmp.write_text(
            json.dumps(load_index(), ensure_ascii=False, indent=1), "utf-8"
        )
        os.replace(tmp, INDEX_FILE)
        return True
    except OSError as exc:  # pragma: no cover - I/O gagal
        logger.warning("Gagal menyimpan indeks arsip tiket: %s", exc)
        return False


# ==============================================================================
# RENDER HTML
# ==============================================================================
def _tema() -> dict[str, str]:
    """Warna & font mengikuti dashboard; ada nilai cadangan bila modul absen."""
    bawaan = {
        "latar": "#0D0D0F",
        "teks": "#FFFFFF",
        "kartu": "#131316",
        "garis": "rgba(255,255,255,.09)",
        "redup": "rgba(255,255,255,.62)",
        "aksen": "#8B7CFF",
        "font": "'General Sans', system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        "mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        "font_link": "",
    }
    try:
        import dashboard_tema as tema

        bawaan.update(
            {
                "latar": tema.LATAR,
                "teks": tema.TEKS,
                "kartu": tema.KARTU,
                "garis": tema.GARIS,
                "redup": tema.REDUP,
                "aksen": tema.AKSEN,
                "font": tema.FONT_STACK,
                "mono": tema.FONT_MONO,
                "font_link": tema.FONT_LINK,
            }
        )
    except Exception as exc:  # pragma: no cover - tema opsional
        logger.debug("Efek samping opsional gagal: %s", exc)
    return bawaan


def _pesan_html(messages: list) -> str:
    bagian: list[str] = []
    for pesan in messages:
        penulis = getattr(getattr(pesan, "author", None), "display_name", None) or "?"
        dibuat = getattr(pesan, "created_at", None)
        kapan = _waktu(dibuat.timestamp() if hasattr(dibuat, "timestamp") else dibuat)
        isi = str(getattr(pesan, "content", "") or "").strip()
        lampiran = ""
        for item in getattr(pesan, "attachments", None) or []:
            url = str(getattr(item, "url", "") or "")
            nama = str(getattr(item, "filename", "") or "lampiran")
            if url.startswith(("http://", "https://")):
                lampiran += (
                    f'<div class="lampiran">📎 <a href="{_esc(url)}" rel="noreferrer noopener" '
                    f'target="_blank">{_esc(nama)}</a></div>'
                )
        if not isi and not lampiran:
            continue
        bagian.append(
            '<div class="pesan">'
            f'<div class="kepala"><b>{_esc(penulis)}</b><span>{_esc(kapan)}</span></div>'
            f'<div class="isi">{_esc(isi)}</div>{lampiran}</div>'
        )
    return "".join(bagian) or '<p class="redup">Tidak ada pesan yang bisa diarsipkan.</p>'


def build_html(data: dict, messages: list, *, guild_name: str = "") -> str:
    """HTML mandiri (satu berkas, tanpa aset luar) untuk satu tiket."""
    data = data or {}
    tema = _tema()
    nomor = _to_int(data.get("number"))
    meta = [
        ("Server", guild_name or str(data.get("guild_id") or "-")),
        ("Nomor", f"#{nomor:04d}"),
        ("Topik", str(data.get("topic") or "-")),
        ("Pembuat", f"<@{data.get('user_id')}>" if data.get("user_id") else "-"),
        ("Dibuka", _waktu(data.get("created_at"))),
        ("Ditutup", _waktu(data.get("closed_at")) if data.get("closed_at") else "-"),
        ("Ditutup oleh", str(data.get("closed_by") or "-")),
        ("Ditangani", str(data.get("claimed_by") or "-")),
        ("Jumlah pesan", str(len(messages or []))),
    ]
    baris_meta = "".join(
        f'<div class="meta-baris"><span>{_esc(k)}</span><b>{_esc(v) if not str(v).startswith("<@") else str(v)}</b></div>'
        for k, v in meta
    )
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tiket #{nomor:04d} — {_esc(data.get('topic') or 'transkrip')}</title>
{tema['font_link']}
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 20px 16px 48px; background: {tema['latar']}; color: {tema['teks']};
         font-family: {tema['font']}; line-height: 1.55; -webkit-text-size-adjust: 100%; }}
  main {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.35rem; margin: 0 0 4px; }}
  .redup {{ color: {tema['redup']}; }}
  .kartu {{ background: {tema['kartu']}; border: 1px solid {tema['garis']}; border-radius: 14px;
            padding: 14px 16px; margin: 16px 0; }}
  .meta-baris {{ display: flex; gap: 12px; justify-content: space-between; font-size: .9rem;
                 padding: 3px 0; border-bottom: 1px dashed {tema['garis']}; }}
  .meta-baris:last-child {{ border-bottom: 0; }}
  .meta-baris span {{ color: {tema['redup']}; }}
  .meta-baris b {{ text-align: right; word-break: break-word; }}
  .pesan {{ border-left: 3px solid {tema['aksen']}; padding: 8px 12px; margin: 10px 0;
            background: {tema['kartu']}; border-radius: 0 10px 10px 0; }}
  .kepala {{ display: flex; gap: 10px; align-items: baseline; font-size: .85rem; }}
  .kepala span {{ color: {tema['redup']}; font-family: {tema['mono']}; font-size: .78rem; }}
  .isi {{ white-space: pre-wrap; word-break: break-word; margin-top: 4px; }}
  .lampiran {{ font-size: .85rem; margin-top: 4px; }}
  a {{ color: {tema['aksen']}; }}
  footer {{ color: {tema['redup']}; font-size: .78rem; text-align: center; margin-top: 28px; }}
</style></head>
<body><main>
<h1>Tiket #{nomor:04d}</h1>
<p class="redup">Transkrip arsip — dicari & dibuka dari dashboard bot.</p>
<div class="kartu">{baris_meta}</div>
{_pesan_html(list(messages or []))}
<footer>Dibuat otomatis oleh bot • tanpa AI &amp; tanpa kuota Gemini</footer>
</main></body></html>
"""


def build_text(data: dict, messages: list) -> str:
    """Versi teks polos (untuk unduhan & pencarian cepat)."""
    data = data or {}
    nomor = _to_int(data.get("number"))
    baris = [
        f"TRANSKRIP TIKET #{nomor:04d}",
        "=" * 48,
        f"Topik      : {data.get('topic') or '-'}",
        f"Dibuka     : {_waktu(data.get('created_at'))}",
        f"Ditutup    : {_waktu(data.get('closed_at')) if data.get('closed_at') else '-'}",
        "",
    ]
    for pesan in messages or []:
        penulis = getattr(getattr(pesan, "author", None), "display_name", None) or "?"
        dibuat = getattr(pesan, "created_at", None)
        kapan = _waktu(dibuat.timestamp() if hasattr(dibuat, "timestamp") else dibuat)
        isi = str(getattr(pesan, "content", "") or "")
        baris.append(f"[{kapan}] {penulis}: {isi}")
    return "\n".join(baris)[:180_000]


# ==============================================================================
# SIMPAN / BACA / HAPUS
# ==============================================================================
def simpan(
    data: dict,
    messages: list,
    *,
    guild_name: str = "",
    teks: str | None = None,
) -> dict | None:
    """Arsipkan satu tiket (HTML + teks + indeks). `None` bila tidak bisa diarsipkan."""
    data = data or {}
    gid = _to_int(data.get("guild_id"))
    nomor = _to_int(data.get("number"))
    pesan = list(messages or [])
    if gid <= 0 or nomor <= 0 or not pesan:
        return None

    kode = kode_dari(data)
    folder = _folder(gid)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        berkas_html = folder / f"tiket-{kode}.html"
        berkas_teks = folder / f"tiket-{kode}.txt"
        isi_html = build_html(data, pesan, guild_name=guild_name)
        isi_teks = teks or build_text(data, pesan)
        _tulis_atomik(berkas_html, isi_html)
        _tulis_atomik(berkas_teks, isi_teks)
    except OSError as exc:  # pragma: no cover - I/O gagal
        logger.warning("Gagal menyimpan arsip tiket: %s", exc)
        return None

    entri = {
        "guild_id": gid,
        "kode": kode,
        "nomor": nomor,
        "thread_id": _to_int(data.get("thread_id")) or _to_int(data.get("id")),
        "user_id": _to_int(data.get("user_id")),
        "topik": str(data.get("topic") or "-")[:200],
        "dibuka": float(data.get("created_at") or 0),
        "ditutup": float(data.get("closed_at") or 0) or time.time(),
        "ditutup_oleh": _to_int(data.get("closed_by")),
        "ditangani": _to_int(data.get("claimed_by")),
        "jumlah_pesan": len(pesan),
        "ukuran": len(isi_html) + len(isi_teks),
    }
    load_index()[_kunci(gid, kode)] = entri
    _pangkas(gid)
    _simpan_index()
    return entri


def _waktu_tutup(item: dict) -> float:
    try:
        return float(item.get("ditutup") or 0)
    except (TypeError, ValueError):
        return 0.0


def _pangkas(
    guild_id: int,
    *,
    maksimal: int | None = None,
    retensi_hari: int | None = None,
    sekarang: float | None = None,
) -> int:
    """Terapkan batas umur dan jumlah; hapus berkas tiket yang sudah kedaluwarsa."""
    gid = int(guild_id)
    indeks = load_index()
    milik = [
        (kunci, item)
        for kunci, item in indeks.items()
        if _to_int(item.get("guild_id")) == gid
    ]
    dibuang = 0
    hari = max(0, int(RETENSI_HARI if retensi_hari is None else retensi_hari))
    if hari:
        saat_ini = time.time() if sekarang is None else float(sekarang)
        batas = saat_ini - hari * 86400
        kedaluwarsa = [(kunci, item) for kunci, item in milik if _waktu_tutup(item) < batas]
        for kunci, item in kedaluwarsa:
            indeks.pop(kunci, None)
            _hapus_berkas(gid, str(item.get("kode") or ""))
            dibuang += 1
        if kedaluwarsa:
            kunci_lama = {kunci for kunci, _item in kedaluwarsa}
            milik = [(kunci, item) for kunci, item in milik if kunci not in kunci_lama]

    batas_jumlah = max(0, int(MAX_DISIMPAN if maksimal is None else maksimal))
    if len(milik) > batas_jumlah:
        milik.sort(key=lambda pasangan: -_waktu_tutup(pasangan[1]))
        for kunci, item in milik[batas_jumlah:]:
            indeks.pop(kunci, None)
            _hapus_berkas(gid, str(item.get("kode") or ""))
            dibuang += 1
    return dibuang


def _hapus_berkas(guild_id: int, kode: str) -> None:
    if not str(kode).isdigit():
        return
    folder = _folder(guild_id)
    for ekstensi in ("html", "txt"):
        try:
            (folder / f"tiket-{kode}.{ekstensi}").unlink(missing_ok=True)
        except OSError:  # pragma: no cover - jaring aman
            pass


def ambil(guild_id: int, kode: object) -> dict | None:
    """Metadata satu arsip."""
    return load_index().get(_kunci(guild_id, kode))


def baca_html(guild_id: int, kode: object) -> str | None:
    """Isi HTML satu arsip (lengkap, siap ditampilkan di browser)."""
    item = ambil(guild_id, kode)
    if item is None:
        return None
    try:
        return (_folder(guild_id) / f"tiket-{item['kode']}.html").read_text("utf-8")
    except OSError:
        return None


def baca_teks(guild_id: int, kode: object) -> str | None:
    item = ambil(guild_id, kode)
    if item is None:
        return None
    try:
        return (_folder(guild_id) / f"tiket-{item['kode']}.txt").read_text("utf-8")
    except OSError:
        return None


def hapus(guild_id: int, kode: object) -> bool:
    """Hapus satu arsip (berkas + entri indeks)."""
    gid = int(guild_id)
    kunci = _kunci(gid, kode)
    item = load_index().pop(kunci, None)
    if item is None:
        return False
    _hapus_berkas(gid, str(item.get("kode") or ""))
    _simpan_index()
    return True


def daftar(guild_id: int, *, limit: int = 10) -> list[dict]:
    """Arsip satu server, terbaru lebih dulu."""
    gid = int(guild_id)
    items = [
        item for item in load_index().values() if _to_int(item.get("guild_id")) == gid
    ]
    items.sort(key=lambda item: -float(item.get("ditutup") or 0))
    return items[: max(1, int(limit))]


def cari(guild_id: int, kata: str = "", *, limit: int = 25) -> list[dict]:
    """Cari arsip berdasarkan kata kunci (topik **dan** isi percakapan).

    Pencarian dilakukan di server: berkas teks dibaca lalu dicocokkan tanpa
    membedakan huruf besar/kecil. Hasil memuat `cuplikan` kalimat yang cocok.
    """
    gid = int(guild_id)
    kueri = str(kata or "").strip()
    if not kueri:
        return daftar(gid, limit=limit)

    jarum = kueri.lower()
    hasil: list[dict] = []
    for item in daftar(gid, limit=MAX_DISIMPAN):
        cuplikan = ""
        cocok = jarum in str(item.get("topik") or "").lower()
        if not cocok:
            teks = baca_teks(gid, item.get("kode")) or ""
            posisi = teks.lower().find(jarum)
            if posisi >= 0:
                cocok = True
                mulai = max(0, posisi - 70)
                cuplikan = " ".join(teks[mulai : posisi + 150].split())
        elif jarum:
            cuplikan = f"Topik: {item.get('topik')}"
        if cocok:
            hasil.append({**item, "cuplikan": cuplikan})
        if len(hasil) >= max(1, min(MAX_CARI, int(limit))):
            break
    return hasil


def statistik(guild_id: int) -> dict:
    """Ringkasan arsip satu server untuk ditampilkan di dashboard."""
    gid = int(guild_id)
    items = [
        item for item in load_index().values() if _to_int(item.get("guild_id")) == gid
    ]
    ukuran = sum(_to_int(item.get("ukuran")) for item in items)
    terbaru = max(items, key=lambda item: float(item.get("ditutup") or 0), default={})
    return {
        "jumlah": len(items),
        "ukuran_kb": round(ukuran / 1024, 1),
        "terakhir": _waktu(terbaru.get("ditutup")) if terbaru else "-",
        "maksimal": MAX_DISIMPAN,
        "retensi_hari": RETENSI_HARI,
    }


def _pulihkan_entri_dari_berkas(indeks: dict[str, dict]) -> int:
    """Rekonstruksi metadata minimum dari pasangan HTML/TXT sebelum membersihkan yatim."""
    dipulihkan = 0
    if not ARSIP_DIR.exists():
        return 0
    for folder in ARSIP_DIR.iterdir():
        if not folder.is_dir() or not folder.name.isdigit():
            continue
        guild_id = int(folder.name)
        for berkas_html in folder.glob("tiket-*.html"):
            kode = berkas_html.stem.removeprefix("tiket-")
            berkas_teks = folder / f"tiket-{kode}.txt"
            if not kode.isdigit() or not berkas_teks.is_file():
                continue
            try:
                ditutup = max(berkas_html.stat().st_mtime, berkas_teks.stat().st_mtime)
                ukuran = berkas_html.stat().st_size + berkas_teks.stat().st_size
            except OSError:
                continue
            kunci = _kunci(guild_id, kode)
            entri = indeks.get(kunci)
            if entri is None:
                indeks[kunci] = {
                    "guild_id": guild_id,
                    "kode": kode,
                    "nomor": _to_int(kode),
                    "thread_id": 0,
                    "user_id": 0,
                    "topik": "-",
                    "dibuka": 0,
                    "ditutup": ditutup,
                    "ditutup_oleh": 0,
                    "ditangani": 0,
                    "jumlah_pesan": 0,
                    "ukuran": ukuran,
                }
                dipulihkan += 1
            elif _waktu_tutup(entri) <= 0:
                entri["ditutup"] = ditutup
                entri["guild_id"] = guild_id
                entri["kode"] = kode
                dipulihkan += 1
    return dipulihkan


def rapikan_arsip(*, sekarang: float | None = None) -> dict[str, int]:
    """Terapkan retensi saat startup dan buang entri/berkas arsip yang tidak lengkap."""
    indeks = load_index()
    dipulihkan = _pulihkan_entri_dari_berkas(indeks)
    sebelum = len(indeks)
    jumlah_dihapus = 0
    guild_ids = sorted(
        {
            _to_int(item.get("guild_id"))
            for item in indeks.values()
            if _to_int(item.get("guild_id")) > 0
        }
    )
    for guild_id in guild_ids:
        jumlah_dihapus += _pangkas(guild_id, sekarang=sekarang)

    # Jangan tampilkan arsip yang hanya punya salah satu dari berkas HTML/TXT.
    for kunci, item in list(indeks.items()):
        guild_id = _to_int(item.get("guild_id"))
        kode = str(item.get("kode") or "")
        if guild_id <= 0 or not kode.isdigit():
            indeks.pop(kunci, None)
            jumlah_dihapus += 1
            continue
        folder = _folder(guild_id)
        pasangan_utuh = (folder / f"tiket-{kode}.html").is_file() and (
            folder / f"tiket-{kode}.txt"
        ).is_file()
        if not pasangan_utuh:
            indeks.pop(kunci, None)
            _hapus_berkas(guild_id, kode)
            jumlah_dihapus += 1

    berubah = bool(dipulihkan or jumlah_dihapus or len(indeks) != sebelum)
    if berubah:
        _simpan_index()
    yatim = bersihkan_berkas_yatim()
    return {
        "arsip_dihapus": jumlah_dihapus,
        "entri_dipulihkan": dipulihkan,
        "berkas_yatim_dihapus": yatim,
    }


def bersihkan_berkas_yatim() -> int:
    """Hapus HTML/TXT sementara atau yatim; dipanggil oleh `rapikan_arsip` saat start."""
    indeks = load_index()
    dibuang = 0
    if not ARSIP_DIR.exists():
        return 0
    for folder in ARSIP_DIR.iterdir():
        if not folder.is_dir() or not folder.name.isdigit():
            continue
        guild_id = int(folder.name)
        for berkas in folder.glob("tiket-*"):
            # Sisa penulisan atomik selalu aman dibuang setelah proses sebelumnya berhenti.
            if berkas.name.endswith((".html.tmp", ".txt.tmp")):
                yatim = True
            elif berkas.suffix in {".html", ".txt"}:
                kode = berkas.stem.removeprefix("tiket-")
                yatim = _kunci(guild_id, kode) not in indeks
            else:
                continue
            if yatim:
                try:
                    berkas.unlink()
                    dibuang += 1
                except OSError:  # pragma: no cover - jaring aman
                    pass
    return dibuang
