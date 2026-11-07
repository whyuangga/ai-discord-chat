"""Regresi P1 — dependensi & metadata paket harus bisa dipakai.

Latar belakang: `pyproject.toml` pernah menulis `devey>=0.2.0` sementara
`requirements.txt` menulis `davey`. Karena nama `devey` tidak ada di PyPI
(HTTP 404), `pip install .` gagal total — padahal deploy normal lewat
`requirements.txt` tetap berhasil, jadi kesalahannya tidak terlihat.

Tes ini menjaga empat hal:

1. Nama dependensi di kedua berkas identik (lewat `tools/check_deps.py`).
2. Tidak ada lagi nama paket yang salah eja (`devey`).
3. `pyproject.toml` mendeklarasikan semua modul root, sehingga
   `pip install .`/`pip wheel .` tidak menolak karena "Multiple top-level
   packages discovered in a flat-layout".
4. `[project].scripts` menunjuk fungsi yang benar-benar ada.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

import tools.check_deps as check_deps

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_nama_dependensi_sama_di_requirements_dan_pyproject():
    req = check_deps.baca_requirements()
    proj = check_deps.baca_pyproject()
    assert req, "requirements.txt tidak terbaca"
    assert check_deps.bandingkan(req, proj) == []
    # Nama yang benar-benar ada di PyPI untuk protokol DAVE
    assert "davey" in req and "devey" not in req
    assert req["davey"] == proj["davey"]


def test_tidak_ada_nama_paket_salah_eja():
    """Nama yang dipakai harus `davey` (ada di PyPI), bukan `devey` (404)."""
    nama_req = set(check_deps.baca_requirements())
    nama_proj = set(check_deps.baca_pyproject())
    assert "devey" not in nama_req | nama_proj
    assert "davey" in nama_req


def test_check_deps_mendeteksi_perbedaan(tmp_path, capsys):
    """Alat penjaga harus benar-benar gagal saat ada selisih (bukan selalu ✔)."""
    req_file = tmp_path / "requirements.txt"
    proj_file = tmp_path / "pyproject.toml"
    req_file.write_text("discord.py>=2.5.0\nsalah-eja>=1.0\n", encoding="utf-8")
    proj_file.write_text(
        '[project]\nname = "uji"\nversion = "0"\n'
        'dependencies = ["discord.py>=2.5.0", "nama-lain>=1.0"]\n',
        encoding="utf-8",
    )
    masalah = check_deps.bandingkan(
        check_deps.baca_requirements(req_file), check_deps.baca_pyproject(proj_file)
    )
    assert any("salah-eja" in m for m in masalah)
    assert any("nama-lain" in m for m in masalah)
    assert check_deps.main.__module__ == "tools.check_deps"

    kode = check_deps.main([])
    assert kode == 0  # berkas asli repo tetap sinkron
    assert "sinkron" in capsys.readouterr().out


def test_pyproject_mendeklarasikan_semua_modul_root():
    """Flat layout: tanpa daftar eksplisit, setuptools menolak build."""
    py_modules = set(_pyproject()["tool"]["setuptools"]["py-modules"])
    nyata = {p.stem for p in ROOT.glob("*.py")}
    assert nyata - py_modules == set(), "modul root belum terdaftar di py-modules"
    assert py_modules - nyata == set(), "py-modules memuat berkas yang tidak ada"


def test_paket_direktori_terdaftar():
    packages = set(_pyproject()["tool"]["setuptools"]["packages"])
    assert {"cogs", "views"} <= packages
    for nama in packages:
        assert (ROOT / nama / "__init__.py").exists(), f"{nama}/__init__.py tidak ada"


def test_build_backend_dan_skrip_entrypoint():
    data = _pyproject()
    assert data["build-system"]["build-backend"] == "setuptools.build_meta"
    skrip = data["project"]["scripts"]["ai-discord-chat"]
    modul, _, fungsi = skrip.partition(":")
    assert modul == "main" and fungsi == "main"

    # Fungsi `main` di main.py memang ada (bukan nama yang sudah berganti)
    pohon = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    fungsi_ada = {
        node.name
        for node in pohon.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "main" in fungsi_ada


def _pep440(versi: str) -> str:
    """Normalisasi versi gaya manusia (`1.40.0-beta`) ke PEP 440 (`1.40.0b0`).

    `packaging` bukan dependensi bot, jadi aturan yang dipakai hanya yang
    benar-benar dipakai proyek ini (alpha/beta/rc).
    """
    bersih = str(versi).strip().lower().replace(" ", "")
    for akhiran, kode in (("-beta", "b0"), ("-alpha", "a0"), ("-rc", "rc1")):
        if bersih.endswith(akhiran):
            return bersih[: -len(akhiran)] + kode
    return bersih


def test_versi_pyproject_dan_config_sinkron():
    """Versi di metadata paket tidak boleh berbeda dari BOT_VERSION bot."""
    import config

    versi = str(_pyproject()["project"]["version"])
    assert _pep440(config.BOT_VERSION) == _pep440(versi)
    assert _pep440("1.40.0-beta") == versi


@pytest.mark.parametrize("nama", ["pyflakes", "ruff", "pytest"])
def test_alat_dev_dideklarasikan(nama):
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert any(item.startswith(nama) for item in dev), f"{nama} tidak ada di extra [dev]"
