"""Menjaga situs dokumentasi (`site/`) tetap sinkron dengan sumber Markdown di `docs/`."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sync_docs  # noqa: E402


def test_situs_sinkron_dengan_docs():
    """site/content/ harus persis hasil generate dari docs/*.md."""
    stale = sync_docs.check()
    assert stale == [], "Jalankan `python3 tools/sync_docs.py`: " + ", ".join(stale)


def test_semua_bagian_fitur_punya_halaman():
    pages = sync_docs.fitur_pages()
    assert len(pages) == 23
    assert [p["letter"] for p in pages] == list("ABCDEFGHIJKLMNOPQRSTUVW")


def test_ikon_dan_deskripsi_lengkap():
    """Setiap halaman punya ikon Material Symbols dan deskripsi untuk sidebar Lotus Docs."""
    for page in sync_docs.fitur_pages():
        assert re.fullmatch(r"[a-z_]+", page["icon"]), page["letter"]
        assert 20 <= len(page["description"]) <= 140, page["letter"]


@pytest.mark.parametrize("rel", sorted(sync_docs.generate()))
def test_front_matter_lengkap(rel):
    content = sync_docs.generate()[rel]
    assert content.startswith("---\n"), rel
    head = content.split("---\n", 2)[1]
    assert "title:" in head, rel
    if rel != "content/docs/_index.md":
        assert "weight:" in head, rel
        assert "description:" in head, rel
        assert "icon:" in head, rel


def test_tautan_relatif_di_halaman_command_diperbaiki():
    body = sync_docs.generate()["content/docs/command.md"]
    assert "](fitur.md" not in body
    assert "](../README.md)" not in body
    assert "](prefix/)" in body
    assert "github.com/whyuangga/ai-discord-chat" in body


def test_heading_tidak_lebih_dalam_dari_h3():
    """Setelah diturunkan, tidak boleh ada #### + (tema hanya merender h2/h3)."""
    for rel, content in sync_docs.generate().items():
        for line in content.split("\n"):
            if re.match(r"^#{4,} ", line):
                pytest.fail(f"{rel}: heading terlalu dalam → {line[:60]}")


def test_konfigurasi_tema_dan_landing_ada():
    assert (ROOT / "site" / "hugo.toml").is_file()
    assert (ROOT / "site" / "data" / "landing.yaml").is_file()
    assert (ROOT / "site" / "themes" / "lotusdocs" / "theme.toml").is_file()
    # dependency tema (bootstrap + popper) ikut di-vendor agar build tanpa jaringan
    assert (ROOT / "site" / "themes" / "lotusdocs" / "assets" / "scss" / "bootstrap" / "_variables.scss").is_file()
    assert (ROOT / "site" / "themes" / "lotusdocs" / "assets" / "js" / "popper" / "index.js").is_file()


def test_vercel_json_siap_deploy():
    """Konfigurasi Vercel harus memin versi Hugo dan menunjuk output yang benar."""
    import json

    config = json.loads((ROOT / "site" / "vercel.json").read_text())
    assert config["framework"] == "hugo"
    assert config["outputDirectory"] == "public"
    assert config["build"]["env"]["HUGO_VERSION"] == "0.169.0"
    assert "--minify" in config["buildCommand"]
    assert "$VERCEL_URL" in config["buildCommand"]


# Berkas hasil build yang memang tidak perlu dilacak git.
_ARTEFAK_BUILD = ("site/public/", "site/resources/", "site/.hugo_build.lock")


def _git(*args: str) -> str:
    hasil = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    )
    return hasil.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="butuh git")
def test_berkas_situs_dilacak_git():
    """Regresi: `data/` di .gitignore pernah ikut membuang site/data/landing.yaml,
    sehingga build di Vercel gagal ("sort: sequence must be provided")."""
    dilacak = set(_git("ls-files", "site").splitlines())
    assert "site/data/landing.yaml" in dilacak, (
        "site/data/landing.yaml tidak dilacak git — cek pola .gitignore (harus '/data/', bukan 'data/')"
    )
    assert "site/hugo.toml" in dilacak
    assert "site/vercel.json" in dilacak
    assert "site/themes/lotusdocs/theme.toml" in dilacak


@pytest.mark.skipif(shutil.which("git") is None, reason="butuh git")
def test_tidak_ada_berkas_situs_yang_terabaikan():
    """Selain artefak build, tidak boleh ada berkas site/ yang diabaikan .gitignore."""
    terabaikan = _git("ls-files", "--others", "--ignored", "--exclude-standard", "--", "site").splitlines()
    tak_diharapkan = [p for p in terabaikan if not p.startswith(_ARTEFAK_BUILD)]
    assert tak_diharapkan == [], "Berkas situs ini terabaikan .gitignore: " + ", ".join(tak_diharapkan)


def test_landing_yaml_punya_bagian_wajib():
    """layouts/index.html tema membaca .landing.{hero,featureGrid}; kalau kosong build gagal."""
    isi = (ROOT / "site" / "data" / "landing.yaml").read_text(encoding="utf-8")
    for kunci in ("hero:", "featureGrid:", "template: hero", "template: feature grid"):
        assert kunci in isi, f"landing.yaml kehilangan '{kunci}'"
    assert isi.count("    - title:") >= 6, "kartu fitur halaman depan berkurang"


def test_konfigurasi_lotus_docs():
    config = (ROOT / "site" / "hugo.toml").read_text()
    assert 'theme = "lotusdocs"' in config
    assert "[params.docs]" in config
    assert "flexsearch" in config
