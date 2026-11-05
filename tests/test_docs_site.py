"""Menjaga situs dokumentasi (`site/`) tetap sinkron dengan sumber Markdown di `docs/`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sys

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


@pytest.mark.parametrize("rel", sorted(sync_docs.generate()))
def test_front_matter_lengkap(rel):
    content = sync_docs.generate()[rel]
    assert content.startswith("---\n"), rel
    head = content.split("---\n", 2)[1]
    assert "title:" in head, rel
    if rel.startswith("content/docs/") and not rel.endswith("_index.md"):
        assert "weight:" in head, rel


def test_tautan_relatif_di_halaman_command_diperbaiki():
    body = sync_docs.generate()["content/docs/command.md"]
    assert "](fitur.md" not in body
    assert "](../README.md)" not in body
    assert "github.com/whyuangga/ai-discord-chat" in body


def test_heading_tidak_lebih_dalam_dari_h3():
    """Setelah diturunkan, tidak boleh ada #### + (Hextra hanya butuh h2/h3)."""
    for rel, content in sync_docs.generate().items():
        if not rel.endswith(".md"):
            continue
        for line in content.split("\n"):
            if re.match(r"^#{4,} ", line):
                pytest.fail(f"{rel}: heading terlalu dalam → {line[:60]}")


def test_konfigurasi_dan_tema_ada():
    assert (ROOT / "site" / "hugo.yaml").is_file()
    assert (ROOT / "site" / "themes" / "hextra" / "theme.toml").is_file()
    assert (ROOT / "site" / "assets" / "flexsearch.bundle.min.js").is_file()
