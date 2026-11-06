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
    # baseURL harus mengikuti domain produksi, bukan URL deployment per-build,
    # dengan fallback ke URL preview lalu ke domain produksi yang sekarang.
    perintah = config["buildCommand"]
    assert re.search(
        r"\$\{VERCEL_PROJECT_PRODUCTION_URL:-\$\{VERCEL_URL:-[a-z0-9.-]+\}\}", perintah
    ), perintah


def test_robots_txt_menunjuk_sitemap():
    """robots.txt bawaan Hugo hanya 'User-agent: *' — kita tambah baris Sitemap."""
    templat = (ROOT / "site" / "layouts" / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap:" in templat
    assert "sitemap.xml" in templat
    assert "absURL" in templat


def test_taksonomi_kosong_dimatikan():
    """Tanpa disableKinds, Hugo membuat /categories/ & /tags/ kosong yang masuk sitemap."""
    config = (ROOT / "site" / "hugo.toml").read_text(encoding="utf-8")
    assert "disableKinds" in config
    for kind in ("taxonomy", "term"):
        assert f'"{kind}"' in config


def test_landing_tidak_memuat_angka_tes_usang():
    """Angka tes di halaman depan pernah tertinggal (149 vs 152)."""
    import re

    isi = (ROOT / "site" / "data" / "landing.yaml").read_text(encoding="utf-8")
    assert "tes otomatis" in isi
    angka = re.findall(r"(\d+)\+?\s*tes otomatis", isi)
    assert angka, "landing.yaml harus menyebut jumlah tes"
    assert all(int(a) >= 150 for a in angka), f"angka tes usang: {angka}"


def test_halaman_depan_punya_meta_sendiri():
    """Halaman depan dulu memakai meta bawaan tema: deskripsi "A Lightweight, Modern
    Documentation Theme for Hugo", author "Colin Wilson - Lotus Labs", dan tanpa kartu
    Open Graph — pratinjau tautan di Google/Discord jadi salah atau kosong."""
    override = ROOT / "site" / "layouts" / "partials" / "head.html"
    assert override.is_file(), "parsial head.html tema harus ditimpa di site/layouts/"
    isi = override.read_text(encoding="utf-8")
    assert 'partial "docs/head/opengraph.html"' in isi
    assert 'partial "docs/head/twitter_cards.html"' in isi
    # meta tidak boleh lagi ditulis mati (hardcode) seperti versi tema
    assert 'content="A Lightweight, Modern Documentation Theme for Hugo"' not in isi
    assert '{{ .Site.Params.author | default .Site.Title }}' in isi
    assert '<link rel="canonical"' in isi

    index = (ROOT / "site" / "content" / "_index.md").read_text(encoding="utf-8")
    deskripsi = re.search(r'^description:\s*"([^"]+)"', index, re.MULTILINE)
    assert deskripsi, "content/_index.md harus punya description"
    assert 70 <= len(deskripsi.group(1)) <= 200, "deskripsi halaman depan kepanjangan/pendek"

    config = (ROOT / "site" / "hugo.toml").read_text(encoding="utf-8")
    for kunci in ("keywords =", "author ="):
        assert kunci in config, f"hugo.toml kehilangan params {kunci!r}"


_HUGO = shutil.which("hugo") or str(ROOT / ".venv" / "bin" / "hugo")


@pytest.fixture(scope="module")
def hasil_build(tmp_path_factory):
    """Build situs sekali untuk semua tes yang memeriksa hasil build."""
    if not Path(_HUGO).is_file():
        pytest.skip("butuh hugo untuk build")
    out = tmp_path_factory.mktemp("situs") / "public"
    subprocess.run(
        [_HUGO, "--quiet", "--minify", "--baseURL", "https://contoh.test/", "--destination", str(out)],
        cwd=ROOT / "site",
        check=True,
        capture_output=True,
        text=True,
    )
    return out


def test_meta_halaman_depan_hasil_build(hasil_build):
    """Uji hasil build: meta & kartu OG halaman depan harus milik situs ini."""
    head = (hasil_build / "index.html").read_text(encoding="utf-8").split("</head>")[0]
    assert "Lightweight, Modern Documentation Theme" not in head
    assert "Colin Wilson" not in head
    for tag in ("og:title", "og:description", "og:image", "twitter:card"):
        assert tag in head, f"halaman depan tidak punya {tag}"
    assert "https://contoh.test/opengraph/" in head, "kartu OG halaman depan tidak terbentuk"


def test_meta_dokumen_tidak_membawa_identitas_tema(hasil_build):
    """Halaman /docs/** dulu membawa author "Colin Wilson - Lotus Labs",
    email support@aigis.uk, dan keywords bawaan tema Lotus Docs."""
    for rel in ("docs/index.html", "docs/command/index.html", "docs/musik/index.html"):
        head = (hasil_build / rel).read_text(encoding="utf-8").split("</head>")[0]
        for sisa in ("Colin Wilson", "support@aigis.uk", "lotusdocs.dev", "Documentation,Hugo,Hugo Theme"):
            assert sisa not in head, f"{rel} masih memuat meta tema: {sisa}"


def test_indeks_pencarian_dimuat_terpisah(hasil_build):
    """Seluruh teks 26 halaman dulu di-inline ke HTML setiap halaman (± 110 KB).

    Sekarang indeks jadi berkas JSON yang hanya diunduh saat kotak pencarian dipakai.
    """
    indeks = list((hasil_build / "search").glob("index.*.json"))
    assert len(indeks) == 1, f"berkas indeks pencarian tidak tunggal: {indeks}"
    import json

    dokumen = json.loads(indeks[0].read_text(encoding="utf-8"))
    assert len(dokumen) >= 20, "indeks pencarian kehilangan halaman"
    for kunci in ("id", "href", "title", "description", "content"):
        assert kunci in dokumen[0], f"dokumen indeks tanpa '{kunci}'"

    for rel in ("docs/command/index.html", "docs/musik/index.html"):
        halaman = hasil_build / rel
        html = halaman.read_text(encoding="utf-8")
        assert "searchIndexURL" in html, f"{rel} tidak memakai indeks terpisah"
        assert halaman.stat().st_size < 90_000, (
            f"{rel} masih {halaman.stat().st_size} byte — indeks pencarian mungkin kembali inline"
        )


def test_feed_rss_ringkas_dan_valid(hasil_build):
    """Templat RSS bawaan Hugo mengirim isi penuh semua halaman (232 KB)."""
    import xml.etree.ElementTree as ET

    for rel in ("index.xml", "docs/index.xml"):
        berkas = hasil_build / rel
        assert berkas.stat().st_size < 40_000, f"{rel} masih {berkas.stat().st_size} byte"
        isi = berkas.read_text(encoding="utf-8")
        assert "content:encoded" not in isi, f"{rel} masih memuat isi penuh halaman"
        item = ET.parse(berkas).getroot().findall("./channel/item")
        assert len(item) >= 20, f"{rel} hanya {len(item)} item"


def test_tidak_ada_source_map_ter_deploy(hasil_build):
    """`$options` sumber-map ter-shadow sehingga `.map` 900 KB ikut ke produksi."""
    peta = list(hasil_build.rglob("*.map"))
    assert peta == [], f"source map ikut ter-deploy: {[str(p.relative_to(hasil_build)) for p in peta]}"


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
    # tema hanya merender tautan kartu dari kunci `ctaLink` (bukan `url`)
    assert isi.count("      ctaLink:") >= 6, "kartu fitur tidak punya tautan (kunci harus ctaLink)"
    assert "/docs/sesi/" in isi and "/docs/command/" not in isi.split("items:")[0]


def test_konfigurasi_lotus_docs():
    config = (ROOT / "site" / "hugo.toml").read_text()
    assert 'theme = "lotusdocs"' in config
    assert "[params.docs]" in config
    assert "flexsearch" in config
