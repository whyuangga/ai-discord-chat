"""Uji tautan bagikan panel (`/menu bagikan` → `/menu impor kode:` + halaman `/p/<kode>`)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import menu_builder as mb

HANDLER = Path(__file__).resolve().parents[1] / "site" / "api" / "p" / "[id].js"


@pytest.fixture(autouse=True)
def _bersih(monkeypatch):
    mb.menus.clear()
    monkeypatch.setattr(mb, "SITE_BASE_URL", "https://contoh.vercel.app")
    yield
    mb.menus.clear()


def _panel():
    menu = mb.create_menu(999, "Pusat Info", description="Halo {server.members}")
    mb.add_link_button(menu, "Support", "https://contoh.id/support")
    mb.add_command_button(menu, "serverstats")
    mb.add_role_button(menu, 123, "Gamer")
    return menu


# ------------------------------------------------------------------------------
# KODE BAGIKAN
# ------------------------------------------------------------------------------
def test_encode_lalu_decode():
    menu = _panel()
    kode, galat = mb.encode_share(menu)
    assert galat == [] and kode

    payload, galat2 = mb.decode_share(kode)
    assert galat2 == []
    assert payload["title"] == "Pusat Info"
    assert [b["label"] for b in payload["buttons"]] == ["Support", "Statistik Server", "Gamer"]


def test_decode_menerima_url_dan_prefix():
    kode, _ = mb.encode_share(_panel())
    url = mb.share_url(kode)
    assert url == f"https://contoh.vercel.app/p/{kode}"

    assert mb.decode_share(url)[0]["title"] == "Pusat Info"
    assert mb.decode_share(f"{url}?utm=discord")[0]["title"] == "Pusat Info"
    assert mb.decode_share(f"{mb.SHARE_PREFIX}{kode}")[0]["title"] == "Pusat Info"


@pytest.mark.parametrize("teks", ["", "bukan kode!", "%%%", "a" * (mb.MAX_SHARE_CODE + 5)])
def test_decode_menolak_kode_rusak(teks):
    payload, galat = mb.decode_share(teks)
    assert payload is None and galat


def test_panel_terlalu_besar_ditolak():
    # Label acak (tidak berulang) supaya zlib pun tidak bisa memampatkannya di bawah batas.
    import hashlib

    acak = lambda teks: hashlib.sha256(teks.encode()).hexdigest()
    menu = mb.create_menu(999, "Besar " + acak("judul"))
    for i in range(20):
        mb.add_role_button(menu, 1000 + i, f"{i}-{acak(str(i))}-{acak(str(i) + 'x')}")
    for i in range(2):
        mb.add_dropdown(
            menu,
            "Pilih " + acak(f"dd{i}"),
            [
                {"role_id": 5000 + i * 30 + n, "label": f"{n}-{acak(f'{i}{n}')}"}
                for n in range(25)
            ],
        )
    kode, galat = mb.encode_share(menu)
    assert kode == "" and any("terlalu besar" in g for g in galat)


def test_impor_dari_kode_membuat_panel_baru():
    kode, _ = mb.encode_share(_panel())
    payload, _ = mb.decode_share(kode)

    baru, galat = mb.import_menu(4242, payload)
    assert baru is not None and galat == []
    assert baru["title"] == "Pusat Info"
    assert len(baru["buttons"]) == 3
    assert mb.get_menu(4242, baru["id"]) is baru


# ------------------------------------------------------------------------------
# HALAMAN /p/<kode>
# ------------------------------------------------------------------------------
def _jalankan(kode: str) -> dict:
    skrip = """
const handler = require(process.argv[1]);
const hasil = { status: 0, headers: {}, body: "" };
const res = {
  statusCode: 0,
  setHeader(k, v) { hasil.headers[k.toLowerCase()] = v; },
  end(b) { if (b !== undefined) hasil.body = String(b); hasil.status = this.statusCode; },
};
handler({ method: 'GET', query: { id: process.argv[2] } }, res);
process.stdout.write(JSON.stringify(hasil));
"""
    keluaran = subprocess.run(
        ["node", "-e", skrip, str(HANDLER), kode], capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(keluaran.stdout)


def _butuh_node():
    if shutil.which("node") is None:  # pragma: no cover
        pytest.skip("Node.js tidak tersedia")


def test_halaman_pratinjau_panel():
    _butuh_node()
    kode, _ = mb.encode_share(_panel())
    hasil = _jalankan(kode)

    assert hasil["status"] == 200
    body = hasil["body"]
    assert '<meta property="og:title" content="Pusat Info">' in body
    assert "Support" in body and "Gamer" in body
    assert f"/menu impor kode:{kode}" in body
    assert f"ai-discord-chat/panel:{kode}" in body


def test_halaman_panel_kode_rusak():
    _butuh_node()
    hasil = _jalankan("bukan-kode")
    assert hasil["status"] == 404
    assert "Tautan panel tidak dikenal" in hasil["body"]


def test_halaman_panel_meloloskan_html():
    _butuh_node()
    menu = mb.create_menu(999, '<script>alert("x")</script>')
    mb.add_link_button(menu, "<b>klik</b>", "https://contoh.id")
    kode, _ = mb.encode_share(menu)
    body = _jalankan(kode)["body"]
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_rewrite_vercel_untuk_halaman_panel():
    konfigurasi = json.loads(
        (Path(__file__).resolve().parents[1] / "site" / "vercel.json").read_text(encoding="utf-8")
    )
    assert any(
        r.get("source") == "/p/:id" and r.get("destination") == "/api/p/:id"
        for r in konfigurasi.get("rewrites", [])
    )


# ------------------------------------------------------------------------------
# KOMPRESI KODE BAGIKAN (zlib)
# ------------------------------------------------------------------------------
def _panel_besar():
    menu = mb.create_menu(999, "Panel Besar")
    for i in range(20):
        mb.add_role_button(menu, 1000 + i, f"Tombol dengan label panjang nomor {i}")
    return menu


def test_kode_dikompresi_dan_masih_terbaca():
    kode, galat = mb.encode_share(_panel())
    assert galat == [] and kode.startswith(mb.SHARE_ZLIB_PREFIX)
    assert mb.decode_share(kode)[0]["title"] == "Pusat Info"


def test_panel_besar_kini_muat_di_batas_tautan():
    import base64
    import json

    menu = _panel_besar()
    kode, galat = mb.encode_share(menu)
    mentah = base64.urlsafe_b64encode(
        json.dumps(mb.export_menu(menu), separators=(",", ":")).encode()
    ).decode()
    assert len(mentah) > mb.MAX_SHARE_CODE          # tanpa kompresi memang tidak muat
    assert galat == [] and len(kode) <= mb.MAX_SHARE_CODE
    assert len(mb.decode_share(kode)[0]["buttons"]) == 20


def test_kode_lama_tanpa_kompresi_tetap_terbaca():
    import base64
    import json

    menu = mb.create_menu(999, "Lama")
    mb.add_link_button(menu, "Support", "https://contoh.id")
    lama = base64.urlsafe_b64encode(
        json.dumps(mb.export_menu(menu), separators=(",", ":")).encode()
    ).decode().rstrip("=")
    assert not lama.startswith(mb.SHARE_ZLIB_PREFIX)
    assert mb.decode_share(lama)[0]["title"] == "Lama"


def test_kode_kompresi_rusak_ditolak():
    payload, galat = mb.decode_share(mb.SHARE_ZLIB_PREFIX + "bukan-zlib")
    assert payload is None and galat
