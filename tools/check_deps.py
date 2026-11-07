"""Pastikan daftar dependensi tidak pernah lagi berbeda antar tempat.

Ada dua jalur pemasangan yang harus selalu sepakat:

1. `requirements.txt` — dipakai hosting (Wispbyte) & CI.
2. `[project].dependencies` di `pyproject.toml` — dipakai `pip install .`.

Riwayat bug: `pyproject.toml` pernah menulis `devey` (HTTP 404 di PyPI) padahal
`requirements.txt` menulis `davey`. Akibatnya `pip install .` gagal padahal
deploy lewat `requirements.txt` aman — persis jenis kesalahan yang tidak
kelihatan sampai ada yang mencoba memasang paketnya.

Pakai:

    python3 tools/check_deps.py          # exit 1 bila ada perbedaan

Aturan pencocokan sengaja longgar pada versi opsional (`>=`, `<`, `~=`) dan
ketat pada **nama** paket, karena nama salah eja itulah yang tidak terdeteksi
oleh pemasangan biasa (pemasangan hanya gagal di sisi pengguna).
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
PYPROJECT = ROOT / "pyproject.toml"

_NAMA = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def baca_requirements(path: Path = REQUIREMENTS) -> dict[str, str]:
    """Nama paket (huruf kecil, `_`→`-`) → spesifikasi versi mentah."""
    hasil: dict[str, str] = {}
    if not path.exists():
        return hasil
    for baris in path.read_text(encoding="utf-8").splitlines():
        isi = baris.split("#", 1)[0].strip()
        if not isi or isi.startswith("-"):
            continue
        cocok = _NAMA.match(isi)
        if not cocok:
            continue
        hasil[normal(cocok.group(1))] = isi[cocok.end():].strip()
    return hasil


def baca_pyproject(path: Path = PYPROJECT) -> dict[str, str]:
    """Sama seperti `baca_requirements`, tapi dari `[project].dependencies`."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    hasil: dict[str, str] = {}
    for isi in data.get("project", {}).get("dependencies", []) or []:
        teks = str(isi).split(";", 1)[0].strip()
        cocok = _NAMA.match(teks)
        if cocok:
            hasil[normal(cocok.group(1))] = teks[cocok.end():].strip()
    return hasil


def normal(nama: str) -> str:
    """Normalisasi nama paket sesuai PEP 503."""
    return re.sub(r"[-_.]+", "-", nama).lower()


def bandingkan(req: dict[str, str], proj: dict[str, str]) -> list[str]:
    """Daftar masalah yang bisa dibaca manusia (kosong bila sinkron)."""
    masalah: list[str] = []
    for nama in sorted(set(req) - set(proj)):
        masalah.append(f"hanya di requirements.txt: {nama}")
    for nama in sorted(set(proj) - set(req)):
        masalah.append(f"hanya di pyproject.toml: {nama}")
    for nama in sorted(set(req) & set(proj)):
        if req[nama] != proj[nama]:
            masalah.append(
                f"versi beda untuk {nama}: requirements.txt='{req[nama] or '(bebas)'}' "
                f"vs pyproject.toml='{proj[nama] or '(bebas)'}'"
            )
    return masalah


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    req = baca_requirements()
    proj = baca_pyproject()
    if not req or not proj:
        print("✖ Tidak bisa membaca daftar dependensi (berkas kosong/hilang).")
        return 1
    masalah = bandingkan(req, proj)
    if not masalah:
        print(f"✔ {len(req)} dependensi sinkron antara requirements.txt & pyproject.toml")
        return 0
    print("✖ Dependensi tidak sinkron:")
    for baris in masalah:
        print(f"  - {baris}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
