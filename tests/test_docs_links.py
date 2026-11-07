"""Dokumentasi tetap rapi: semua tautan internal & anchor antar-berkas harus hidup.

Tes ini menjaga hasil "rapikan dokumen" tidak rusak lagi saat ada yang mengganti
judul bagian. Aturannya sederhana: setiap tautan Markdown ke berkas `.md` harus
menunjuk berkas yang ada, dan bila memakai `#anchor`, judulnya harus benar-benar ada
(mengikuti aturan slug GitHub: huruf kecil, tanpa tanda baca, spasi → `-`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOKUMEN = (
    "README.md",
    "docs/fitur.md",
    "docs/command.md",
    "docs/catatan-dashboard-dan-kunci-api.md",
    "site/README.md",
)
POLA_TAUTAN = re.compile(r"\]\(([^)\s]+\.md)(?:#([^)\s]+))?\)")


def slug_github(judul: str) -> str:
    """Slug anchor ala GitHub untuk satu baris judul."""
    teks = judul.strip().lower().replace("`", "")
    teks = re.sub(r"[^\w\- ]+", "", teks)
    return teks.replace(" ", "-")


def anchor_berkas(path: Path) -> set[str]:
    hasil = set()
    teks = path.read_text(encoding="utf-8")
    for baris in teks.split("\n"):
        m = re.match(r"^#{1,6} (.+)$", baris)
        if m:
            hasil.add(slug_github(m.group(1)))
    return hasil


@pytest.mark.parametrize("nama", DOKUMEN)
def test_tautan_markdown_di_dokumen_hidup(nama):
    """Semua tautan `…md` (lokal) menunjuk berkas yang ada & anchor yang valid."""
    berkas = ROOT / nama
    assert berkas.exists(), f"{nama} hilang"
    teks = berkas.read_text(encoding="utf-8")
    masalah: list[str] = []

    for m in POLA_TAUTAN.finditer(teks):
        tujuan, anchor = m.group(1), m.group(2)
        target = (berkas.parent / tujuan).resolve()
        if not target.exists():
            masalah.append(f"berkas tidak ada: {tujuan}")
            continue
        if anchor and anchor not in anchor_berkas(target):
            masalah.append(f"anchor tidak ada: {tujuan}#{anchor}")

    assert not masalah, f"{nama}: " + "; ".join(sorted(set(masalah)))


@pytest.mark.parametrize("nama", DOKUMEN)
def test_anchor_dalam_berkas_sendiri(nama):
    """Tautan `(#…)` di dalam satu berkas harus punya judul yang cocok."""
    berkas = ROOT / nama
    teks = berkas.read_text(encoding="utf-8")
    tersedia = anchor_berkas(berkas)
    rusak = {
        m.group(1)
        for m in re.finditer(r"\]\(#([^)\s]+)\)", teks)
        if m.group(1) not in tersedia
    }
    assert not rusak, f"{nama}: anchor tanpa judul → {sorted(rusak)}"


def test_daftar_isi_readme_berurutan():
    """Daftar isi README harus bernomor 1..N tanpa lompatan atau duplikat."""
    teks = (ROOT / "README.md").read_text(encoding="utf-8")
    mulai = teks.index("## 📚 Daftar Isi")
    akhir = teks.index("## 🎮 Panduan Cara Pakai")
    nomor = [
        int(m.group(1))
        for m in re.finditer(r"^(\d+)\. \[", teks[mulai:akhir], re.MULTILINE)
    ]
    assert nomor == list(range(1, len(nomor) + 1)), nomor


def test_dokumen_menyebut_jumlah_yang_benar():
    """Angka di dokumen harus ikut kode (jumlah command, setelan, & berkas tes)."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "53 command utama" in readme
    assert re.search(r"\*\*\d+ tes otomatis\*\*", readme), "README harus menyebut jumlah tes"
    assert "367 tes" not in readme            # angka lama, jangan balik lagi
    assert "149 test" not in readme

    # Jumlah berkas tes di README harus sama dengan isi tests/ yang sebenarnya.
    jumlah = re.search(r"(\d+) berkas pytest", readme)
    assert jumlah, "README harus menyebut jumlah berkas pytest"
    assert int(jumlah.group(1)) == len(list((ROOT / "tests").glob("test_*.py")))

    fitur = (ROOT / "docs" / "fitur.md").read_text(encoding="utf-8")
    assert "**55 setelan" in fitur or "55 fitur" in fitur


def test_env_example_mencakup_variabel_penting():
    """.env.example harus memuat kunci dashboard & tingkat lanjut yang didokumentasikan."""
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    for kunci in (
        "DISCORD_BOT_TOKEN",
        "GEMINI_API_KEY",
        "DASHBOARD_TOKEN",
        "DASHBOARD_PORT",
        "DASHBOARD_REFRESH_SEC",
        "DASHBOARD_UPLOAD_MB",
    ):
        assert re.search(rf"^#? ?{kunci}=", env, re.MULTILINE), f"{kunci} belum ada di .env.example"


def test_readme_mendokumentasikan_semua_modul():
    """Setiap modul Python tingkat atas & berkas di cogs/ + views/ disebut di README."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    hilang = [
        p.name
        for pola in ("*.py", "cogs/*.py", "views/*.py")
        for p in sorted(ROOT.glob(pola))
        if p.name != "__init__.py" and p.name not in readme
    ]
    assert not hilang, f"belum disebut di README: {hilang}"
