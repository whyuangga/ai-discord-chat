"""Penjaga struktur P3: dashboard tidak boleh kembali menjadi satu fungsi raksasa.

Sebelum P3, `web_dashboard.py` adalah satu berkas 3.164 baris dengan
`start_dashboard()` setinggi **1.571 baris** yang memuat 49 fungsi bersarang.
Tes ini mengunci hasil pemecahannya supaya tidak kembali menggemuk:

1. `start_dashboard()` tetap ringkas (merakit objek + menyalakan server).
2. Tidak ada satu pun fungsi/method di paket `web_dashboard/` yang >100 baris.
3. Handler hidup sebagai method kelas, bukan fungsi bersarang.
4. Tabel rute adalah data yang bisa diperiksa tanpa menyalakan server.
5. Berkas `web_dashboard.py` tidak boleh muncul kembali (akan membayangi paket).

Selain itu ada pemeriksaan perilaku: setiap rute di tabel benar-benar bisa
dipanggil (metodenya ada di salah satu kelas) dan jumlahnya masuk akal.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

import web_dashboard
from web_dashboard import rute as modul_rute
from web_dashboard import tabel_rute

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAKET = ROOT / "web_dashboard"


def _fungsi_di(path: pathlib.Path) -> list[tuple[int, str]]:
    """(jumlah baris, nama) untuk setiap def di satu berkas."""
    pohon = ast.parse(path.read_text(encoding="utf-8"))
    hasil = []
    for node in ast.walk(pohon):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            baris = (node.end_lineno or node.lineno) - node.lineno + 1
            hasil.append((baris, node.name))
    return hasil


def test_start_dashboard_kembali_ringkas():
    """Dulu 1.571 baris; sekarang hanya merakit + menyalakan server."""
    sumber = inspect.getsource(web_dashboard.start_dashboard)
    baris = len(sumber.splitlines())
    assert baris <= 90, f"start_dashboard() menggemuk lagi: {baris} baris"
    # Tugas intinya masih ada dan berurutan.
    for potongan in (
        "dashboard_config()",
        "dashboard_security.kekuatan_token",
        "MiddlewareKeamanan(",
        "pasang_rute(",
        "web.TCPSite(",
    ):
        assert potongan in sumber, potongan


def test_tidak_ada_fungsi_lebih_dari_seratus_baris_di_paket():
    """Batas 100 baris berlaku untuk seluruh paket dashboard."""
    pelanggaran = []
    for path in sorted(PAKET.glob("*.py")):
        for baris, nama in _fungsi_di(path):
            if baris > 100:
                pelanggaran.append(f"{path.name}:{nama} = {baris} baris")
    assert pelanggaran == [], "fungsi terlalu panjang:\n" + "\n".join(pelanggaran)


def test_berkas_modul_lama_tidak_kembali():
    """`web_dashboard.py` akan **membayangi** paket — Python memilih paket."""
    assert not (ROOT / "web_dashboard.py").exists(), (
        "web_dashboard.py muncul lagi; paket web_dashboard/ akan membayanginya "
        "dan berkas itu tidak akan pernah dimuat"
    )


def test_handler_adalah_method_kelas_bukan_fungsi_bersarang():
    """Handler pindah dari 49 fungsi bersarang ke `RuteDashboard`/`HalamanDashboard`."""
    kelas = {
        "RuteDashboard": modul_rute.RuteDashboard,
        "HalamanDashboard": modul_rute.HalamanDashboard,
    }
    method = {
        nama
        for isi in kelas.values()
        for nama, _ in inspect.getmembers(isi, predicate=inspect.isfunction)
        if nama.startswith("handle_") or nama in {"simpan_tiket", "slug_dari_kueri"}
    }
    assert "handle_index" in method
    assert {"handle_aksi", "handle_kirim", "handle_ai", "handle_unggah"} <= method
    assert len(method) >= 28, sorted(method)


@pytest.mark.parametrize("nama_kelas", ["RuteDashboard", "HalamanDashboard"])
def test_kelas_rute_punya_atribut_inti(nama_kelas):
    """Setiap kelas memegang bot/cfg/helper sendiri — tanpa variabel global."""
    kelas = getattr(modul_rute, nama_kelas)
    parameter = list(inspect.signature(kelas.__init__).parameters)
    assert parameter[:4] == ["self", "bot", "cfg", "helper"]


def test_tabel_rute_menunjuk_handler_yang_benar_benar_ada():
    rute = modul_rute.RuteDashboard(None, {}, None, None)
    halaman = modul_rute.HalamanDashboard(None, {}, None)
    for _metode, path, nama in tabel_rute.RUTE_API:
        assert callable(getattr(rute, nama, None)) or callable(
            getattr(halaman, nama, None)
        ), f"{path} → {nama} tidak ada"
    assert callable(halaman.handle_index)


def test_tabel_rute_mencakup_semua_endpoint_wajib():
    path = tabel_rute.daftar_path()
    wajib = {
        "/healthz",
        "/api/status",
        "/api/pemakaian",
        "/api/level",
        "/api/kontrol",
        "/api/fitur",
        "/api/setelan",
        "/api/tren",
        "/api/ekspor",
        "/api/rank.png",
        "/api/kartu/{jenis}",
        "/api/unggahan/{nama}",
        "/transkrip",
        "/api/transkrip",
        "/keluar",
    }
    assert wajib <= path, wajib - path


def test_halaman_dan_bookmark_lama_tetap_dilayani():
    """`/` + semua slug modern + bookmark lama (`/uji`, `/setelan`, …)."""
    slug = tabel_rute.slug_halaman()
    assert "inti" in slug and "ai" in slug and "sambutan" in slug
    # Bookmark lama tidak boleh hilang.
    assert {"uji", "setelan", "perpisahan", "boost"} <= set(slug)


def test_pasang_rute_mendaftarkan_semua_baris_tabel():
    """Penghitung rute = tabel + `/` + semua slug (tidak ada yang diam-diam hilang)."""
    from aiohttp import web

    class _Rute:
        def __getattr__(self, nama):
            async def _handler(_request):
                return None

            return _handler

    class _Halaman(_Rute):
        async def handle_index(self, _request):
            return None

    app = web.Application()
    jumlah = tabel_rute.pasang_rute(app, _Rute(), _Halaman())
    assert jumlah == len(tabel_rute.RUTE_API) + len(tabel_rute.RUTE_HALAMAN) + len(
        tabel_rute.slug_halaman()
    )
    # Setiap rute punya method+path unik (tidak ada pendaftaran ganda).
    app.router.freeze()
    terdaftar = [
        # Rute dinamis melaporkan `path` kosong → pakai `formatter`.
        (r.method, r.get_info().get("path") or r.get_info().get("formatter"))
        for r in app.router.routes()
        if getattr(r, "method", None) and r.method != "HEAD"
    ]
    assert len(terdaftar) == len(set(terdaftar)) == jumlah


def test_pasang_rute_menolak_handler_hilang():
    """Salah tulis nama handler harus meledak saat start, bukan 404 saat dipakai."""
    from aiohttp import web

    class _Kosong:
        pass

    with pytest.raises(AttributeError, match="tidak ditemukan"):
        tabel_rute.pasang_rute(web.Application(), _Kosong(), _Kosong())


def test_middleware_gaya_baru_aiohttp():
    """Tanpa `__middleware_version__`, aiohttp memanggilnya `(app, handler)` → rusak."""
    from web_dashboard.middleware import MiddlewareKeamanan

    assert getattr(MiddlewareKeamanan, "__middleware_version__", None) == 1


def test_nama_publik_lama_masih_bisa_diakses():
    """32 berkas tes & `main.py` masih memakai `web_dashboard.<nama>`."""
    for nama in (
        "start_dashboard",
        "stop_dashboard",
        "dashboard_config",
        "is_authorized",
        "collect_status",
        "collect_usage",
        "collect_features",
        "collect_tren",
        "collect_levels",
        "render_features_block",
        "render_dashboard_html",
        "apply_dashboard_action",
        "dashboard_controls",
        "render_controls_block",
        "halaman_dari_path",
        "halaman_dari_anchor",
        "url_halaman",
        "fitur_grup",
        "HALAMAN",
        "HALAMAN_SLUG",
        "LEGACY_HALAMAN",
        "ANCHOR_HALAMAN",
        "UJI_HALAMAN",
        "GRUP_HALAMAN",
        "SETELAN_SAMBUTAN",
        "COOKIE_AUTO",
        "FIELD_AUTO_MANUAL",
        "PANEL",
        "_anchor_aksi",
        "_anchor_konten",
        "_guild_hint",
        "_id_aman",
    ):
        assert hasattr(web_dashboard, nama), f"web_dashboard.{nama} hilang"
