"""Uji tautan embed (`link_embed.py`) + halaman `/l/<kode>` di situs (function Vercel)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import link_embed as le

HANDLER = Path(__file__).resolve().parents[1] / "site" / "api" / "l" / "[id].js"


@pytest.fixture(autouse=True)
def _bersih(tmp_path, monkeypatch):
    monkeypatch.setattr(le, "DATA_DIR", tmp_path)
    monkeypatch.setattr(le, "LINKS_FILE", tmp_path / "links.json")
    monkeypatch.setattr(le, "SITE_BASE_URL", "https://contoh.vercel.app")
    le.links.clear()
    yield
    le.links.clear()


# ------------------------------------------------------------------------------
# PAYLOAD & KODE
# ------------------------------------------------------------------------------
def test_build_payload_menyimpan_kunci_pendek():
    payload, galat = le.build_payload(
        title="Panduan",
        description="Aturan server",
        url="https://contoh.id/panduan",
        color="#9B59B6",
        provider="Tim",
    )
    assert galat == []
    assert payload["t"] == "Panduan"
    assert payload["u"] == "https://contoh.id/panduan"
    assert payload["c"] == "9b59b6"          # dinormalkan
    assert payload["v"] == 1


def test_build_payload_butuh_url_http():
    _, galat = le.build_payload(title="X", url="ftp://contoh.id")
    assert any("URL tujuan wajib" in g for g in galat)

    _, galat2 = le.build_payload(title="X", url="javascript:alert(1)")
    assert any("URL tujuan wajib" in g for g in galat2)


def test_build_payload_butuh_judul_atau_isi():
    _, galat = le.build_payload(url="https://contoh.id")
    assert any("judul" in g and "isi" in g for g in galat)


def test_build_payload_menolak_gambar_bukan_http():
    _, galat = le.build_payload(title="X", url="https://contoh.id", image="data:image/png;base64,AAA")
    assert any("URL gambar" in g for g in galat)


def test_build_payload_menolak_warna_ngawur():
    payload, galat = le.build_payload(title="X", url="https://contoh.id", color="ungu")
    assert any("Warna" in g for g in galat)
    assert "c" not in payload


def test_encode_decode_bolak_balik():
    payload, _ = le.build_payload(
        title="Panduan Server",
        description="Semua aturan & tips",
        url="https://contoh.id/panduan",
        image="https://contoh.id/banner.png",
        thumbnail="https://contoh.id/ikon.png",
        color="2ecc71",
        provider="AI Discord Chat",
        site="Server Uji",
    )
    kode = le.encode(payload)
    assert "=" not in kode and "+" not in kode and "/" not in kode   # aman di URL
    hasil = le.decode(kode)
    assert hasil["title"] == "Panduan Server"
    assert hasil["description"] == "Semua aturan & tips"
    assert hasil["url"] == "https://contoh.id/panduan"
    assert hasil["thumbnail"] == "https://contoh.id/ikon.png"
    assert hasil["color"] == "2ecc71"
    assert hasil["site"] == "Server Uji"


@pytest.mark.parametrize(
    "kode",
    ["", "bukan payload!", "%%%", "a" * (le.MAX_CODE + 5), "eyJ2IjoyfQ", "W10"],
)
def test_decode_menolak_kode_rusak(kode):
    assert le.decode(kode) is None


def test_decode_menolak_payload_tanpa_isi():
    kode = le.encode({"v": 1, "u": "https://contoh.id"})
    assert le.decode(kode) is None


def test_decode_menolak_url_berbahaya():
    kode = le.encode({"v": 1, "t": "X", "u": "javascript:alert(1)", "i": "data:xxx"})
    hasil = le.decode(kode)
    assert hasil["url"] == "" and hasil["image"] == ""


def test_build_url_memakai_situs_terkonfigurasi():
    assert le.build_url("abc") == "https://contoh.vercel.app/l/abc"
    assert le.build_url("abc", "https://lain.vercel.app/") == "https://lain.vercel.app/l/abc"


def test_kode_terlalu_panjang_ditolak():
    payload = {
        "v": 1,
        "t": "x" * le.MAX_TITLE,
        "d": "y" * le.MAX_DESCRIPTION,
        "u": "https://contoh.id/" + "z" * 400,
        "i": "https://contoh.id/" + "g" * 250,
        "th": "https://contoh.id/" + "s" * 250,
    }
    kode, galat = le.make_code(payload)
    assert kode == "" and galat and "terlalu panjang" in galat[0]


def test_tautan_normal_muat_di_batas_aman():
    record, galat = le.create_link(
        999,
        title="Panduan Server",
        description="Semua aturan, tips, dan tautan penting untuk anggota baru.",
        url="https://contoh.id/panduan",
        image="https://contoh.id/banner.png",
    )
    assert galat == []
    assert len(record["url"]) < 600


# ------------------------------------------------------------------------------
# CATATAN TAUTAN
# ------------------------------------------------------------------------------
def test_create_link_menyimpan_catatan():
    record, galat = le.create_link(999, title="Panduan", url="https://contoh.id", created_by=7)
    assert galat == []
    assert record["id"].startswith("l")
    assert record["target"] == "https://contoh.id"
    assert le.get_link(999, "panduan") is record
    assert le.get_link(999, record["id"]) is record
    assert le.stats(999)["total"] == 1


def test_create_link_memakai_deskripsi_bila_tanpa_judul():
    record, _ = le.create_link(999, description="Tanpa judul", url="https://contoh.id")
    assert record["title"] == "Tanpa judul"


def test_delete_link():
    record, _ = le.create_link(999, title="Hapus", url="https://contoh.id")
    assert le.delete_link(999, "Hapus") is record
    assert le.list_links(999) == []
    assert le.delete_link(999, "tidak ada") is None


def test_kuota_tautan_per_server(monkeypatch):
    monkeypatch.setattr(le, "MAX_LINKS_PER_GUILD", 2)
    assert le.create_link(999, title="A", url="https://a.id")[0] is not None
    assert le.create_link(999, title="B", url="https://b.id")[0] is not None
    record, galat = le.create_link(999, title="C", url="https://c.id")
    assert record is None and "penuh" in galat[0]


@pytest.mark.asyncio
async def test_simpan_lalu_muat_kembali():
    record, _ = le.create_link(999, title="Panduan", url="https://contoh.id", created_by=7)
    await le.save_to_disk()

    le.links.clear()
    assert le.load_from_disk() == 1
    lagi = le.get_link(999, record["id"])
    assert lagi is not None
    assert lagi["url"] == record["url"]
    assert lagi["target"] == "https://contoh.id"


@pytest.mark.asyncio
async def test_muat_melewati_kode_rusak():
    le.LINKS_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "guilds": {
                    "999": {
                        "l1": {"id": "l1", "title": "Rusak", "code": "bukan-kode"},
                        "l2": {"id": "l2", "title": "Sehat", "code": le.encode({"v": 1, "t": "Ok", "u": "https://a.id"})},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert le.load_from_disk() == 1
    assert le.get_link(999, "Sehat") is not None


# ------------------------------------------------------------------------------
# FUNCTION VERCEL (/l/<kode>)
# ------------------------------------------------------------------------------
def _jalankan_handler(kode: str, *, method: str = "GET") -> dict:
    """Panggil `site/api/l/[id].js` lewat Node dan kembalikan status/headers/body."""
    skrip = """
const handler = require(process.argv[1]);
const hasil = { status: 0, headers: {}, body: "" };
const res = {
  statusCode: 0,
  setHeader(kunci, nilai) { hasil.headers[kunci.toLowerCase()] = nilai; },
  end(isi) { if (isi !== undefined) hasil.body = String(isi); hasil.status = this.statusCode; },
};
handler({ method: process.argv[3], query: { id: process.argv[2] } }, res);
process.stdout.write(JSON.stringify(hasil));
"""
    keluaran = subprocess.run(
        ["node", "-e", skrip, str(HANDLER), kode, method],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(keluaran.stdout)


def _butuh_node() -> None:
    if shutil.which("node") is None:  # pragma: no cover - lingkungan tanpa Node
        pytest.skip("Node.js tidak tersedia")


def test_halaman_menghasilkan_tag_og():
    _butuh_node()
    record, _ = le.create_link(
        999,
        title="Panduan Server",
        description="Semua aturan & tips",
        url="https://contoh.id/panduan",
        image="https://contoh.id/banner.png",
        color="9b59b6",
        provider="AI Discord Chat",
    )
    hasil = _jalankan_handler(record["code"])

    assert hasil["status"] == 200
    assert "text/html" in hasil["headers"]["content-type"]
    assert "noindex" == hasil["headers"]["x-robots-tag"]

    body = hasil["body"]
    assert '<meta property="og:title" content="Panduan Server">' in body
    assert 'content="Semua aturan &amp; tips"' in body
    assert '<meta property="og:image" content="https://contoh.id/banner.png">' in body
    assert '<meta property="og:site_name" content="AI Discord Chat">' in body
    assert '<meta name="theme-color" content="#9b59b6">' in body
    # pengunjung dialihkan ke URL tujuan
    assert 'http-equiv="refresh"' in body and "https://contoh.id/panduan" in body


def test_halaman_menolak_kode_rusak():
    _butuh_node()
    hasil = _jalankan_handler("bukan-kode")
    assert hasil["status"] == 404
    assert "Tautan tidak dikenal" in hasil["body"]
    assert "og:title" not in hasil["body"]


def test_halaman_meloloskan_serangan_html():
    _butuh_node()
    record, _ = le.create_link(
        999,
        title='<script>alert("x")</script>',
        url="https://contoh.id",
    )
    body = _jalankan_handler(record["code"])["body"]
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_halaman_menjawab_HEAD_tanpa_body():
    _butuh_node()
    record, _ = le.create_link(999, title="HEAD", url="https://contoh.id")
    hasil = _jalankan_handler(record["code"], method="HEAD")
    assert hasil["status"] == 200
    assert hasil["body"] == ""


def test_rewrite_vercel_mengarahkan_l_ke_function():
    konfigurasi = json.loads(
        (Path(__file__).resolve().parents[1] / "site" / "vercel.json").read_text(encoding="utf-8")
    )
    rewrites = konfigurasi.get("rewrites") or []
    assert any(
        r.get("source") == "/l/:id" and r.get("destination") == "/api/l/:id" for r in rewrites
    )
