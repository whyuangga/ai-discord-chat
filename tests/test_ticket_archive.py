"""Uji arsip transkrip tiket: HTML mandiri, pencarian di server, & batas simpan.

Arsip ditulis ke folder sementara supaya tes tidak menyentuh `data/` sungguhan.
"""

from __future__ import annotations

import time
import types

import pytest

import dashboard_ui
import ticket_archive as arsip

GID = 4242


# ==============================================================================
# PERKAKAS
# ==============================================================================
class _Pesan:
    def __init__(self, nama: str, isi: str, *, detik: float = 0.0, lampiran=()):
        self.author = types.SimpleNamespace(display_name=nama)
        self.created_at = time.time() - 600 + detik
        self.content = isi
        self.attachments = [
            types.SimpleNamespace(url=url, filename=nama_berkas)
            for url, nama_berkas in lampiran
        ]


def _tiket(nomor: int = 1, *, topik: str = "Nitro tidak masuk", tutup: float | None = None) -> dict:
    return {
        "guild_id": GID,
        "number": nomor,
        "thread_id": 9000 + nomor,
        "id": 9000 + nomor,
        "user_id": 501,
        "topic": topik,
        "created_at": time.time() - 3600,
        "closed_at": tutup if tutup is not None else time.time(),
        "closed_by": 1,
        "claimed_by": 2,
    }


@pytest.fixture(autouse=True)
def _folder_sementara(tmp_path, monkeypatch):
    monkeypatch.setattr(arsip, "ARSIP_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(arsip, "INDEX_FILE", tmp_path / "transcripts" / "index.json")
    arsip.reset_cache()
    yield
    arsip.reset_cache()


def _contoh(nomor: int = 1, **kwargs):
    pesan = [
        _Pesan("Sari", "Halo min, nitronya belum masuk <script>alert(1)</script>", detik=0,
               lampiran=[("https://cdn.example.com/bukti.png", "bukti.png"),
                         ("javascript:alert(1)", "jahat.txt")]),
        _Pesan("Staf", "Siap kak, kami cek dulu ya 🙏", detik=60),
    ]
    return arsip.simpan(_tiket(nomor, **kwargs), pesan, guild_name="Server Uji")


# ==============================================================================
# SIMPAN & BACA
# ==============================================================================
def test_simpan_menulis_html_teks_dan_indeks():
    entri = _contoh(7)
    assert entri is not None and entri["kode"] == "0007"
    assert entri["jumlah_pesan"] == 2 and entri["topik"] == "Nitro tidak masuk"
    assert arsip.INDEX_FILE.exists()

    isi_html = arsip.baca_html(GID, "0007")
    assert isi_html is not None and isi_html.startswith("<!doctype html>")
    # Isi percakapan di-escape, bukan dieksekusi
    assert "<script>alert(1)</script>" not in isi_html
    assert "&lt;script&gt;" in isi_html
    # Lampiran aman: hanya http(s) yang jadi tautan
    assert 'href="https://cdn.example.com/bukti.png"' in isi_html
    assert "javascript:alert" not in isi_html
    assert "Sari" in isi_html and "Staf" in isi_html

    isi_teks = arsip.baca_teks(GID, "0007")
    assert "TRANSKRIP TIKET #0007" in isi_teks
    assert "[100%" not in isi_teks  # format waktu manusia, bukan placeholder

    # Metadata tidak bocor ke server lain
    assert arsip.ambil(9999, "0007") is None
    assert arsip.baca_html(9999, "0007") is None
    assert arsip.daftar(9999) == []


def test_simpan_menolak_data_tidak_lengkap():
    assert arsip.simpan({}, []) is None
    assert arsip.simpan(_tiket(1), []) is None  # tanpa pesan tidak berguna
    rusak = _tiket(2)
    rusak["guild_id"] = 0
    assert arsip.simpan(rusak, [_Pesan("A", "halo")]) is None


def test_simpan_ulang_nomor_sama_menimpa_bukan_menggandakan():
    _contoh(3, topik="Topik lama")
    _contoh(3, topik="Topik baru")
    assert len(arsip.daftar(GID, limit=50)) == 1
    assert arsip.ambil(GID, "0003")["topik"] == "Topik baru"


# ==============================================================================
# PENCARIAN
# ==============================================================================
def test_cari_isi_percakapan_dan_topik_memberi_cuplikan():
    _contoh(1, topik="Nitro tidak masuk")
    _contoh(2, topik="Bug role")
    # Isi pesan contoh selalu memuat "nitro"
    hasil = arsip.cari(GID, "nitro")
    assert hasil and all(item["kode"] in {"0001", "0002"} for item in hasil)
    assert "nitro" in hasil[0]["cuplikan"].lower()

    hanya_topik = arsip.cari(GID, "bug role")
    assert [item["kode"] for item in hanya_topik] == ["0002"]
    assert "Topik:" in hanya_topik[0]["cuplikan"]

    assert arsip.cari(GID, "tidak-ada-kata-ini") == []
    assert arsip.cari(GID, "") == arsip.daftar(GID, limit=25)
    # Pencarian tidak membedakan huruf besar/kecil
    assert arsip.cari(GID, "NITRO") == arsip.cari(GID, "nitro")
    # Server lain tidak melihat arsip ini
    assert arsip.cari(9999, "nitro") == []


# ==============================================================================
# BATAS SIMPAN & HAPUS
# ==============================================================================
def test_pangkas_menyisakan_arsip_terbaru_dan_menghapus_berkas():
    for nomor in range(1, 6):
        _contoh(nomor, tutup=time.time() - (10 - nomor) * 100)
    dibuang = arsip._pangkas(GID, maksimal=2)
    assert dibuang == 3
    sisa = [item["kode"] for item in arsip.daftar(GID, limit=10)]
    assert sisa == ["0005", "0004"]
    # Berkas yang dipangkas benar-benar hilang dari disk
    assert arsip.baca_html(GID, "0001") is None
    folder = arsip.ARSIP_DIR / str(GID)
    assert sorted(p.name for p in folder.glob("tiket-*")) == [
        "tiket-0004.html", "tiket-0004.txt", "tiket-0005.html", "tiket-0005.txt",
    ]


def test_retensi_berbasis_umur_dan_pembersihan_startup(monkeypatch):
    sekarang = time.time()
    monkeypatch.setattr(arsip, "RETENSI_HARI", 0)
    _contoh(10, tutup=sekarang - 60 * 86400)
    _contoh(11, tutup=sekarang - 10 * 86400)

    folder = arsip.ARSIP_DIR / str(GID)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tiket-0099.html").write_text("yatim", "utf-8")
    (folder / "tiket-0099.txt").write_text("yatim", "utf-8")
    (folder / "tiket-0098.html.tmp").write_text("parsial", "utf-8")

    monkeypatch.setattr(arsip, "RETENSI_HARI", 30)
    hasil = arsip.rapikan_arsip(sekarang=sekarang)

    assert hasil == {
        "arsip_dihapus": 1,
        "entri_dipulihkan": 1,
        "berkas_yatim_dihapus": 1,
    }
    assert [item["kode"] for item in arsip.daftar(GID, limit=10)] == ["0099", "0011"]
    assert arsip.baca_html(GID, "0010") is None
    assert arsip.baca_html(GID, "0099") is not None  # pasangan utuh dipulihkan ke indeks
    assert arsip.baca_teks(GID, "0099") is not None
    assert not (folder / "tiket-0098.html.tmp").exists()
    assert arsip.statistik(GID)["retensi_hari"] == 30


def test_startup_memulihkan_indeks_rusak_dari_pasangan_arsip():
    _contoh(12)
    arsip.INDEX_FILE.write_text("{rusak", "utf-8")
    arsip.reset_cache()

    hasil = arsip.rapikan_arsip()

    assert hasil["entri_dipulihkan"] == 1
    assert hasil["arsip_dihapus"] == 0
    assert arsip.INDEX_FILE.exists()
    assert arsip.ambil(GID, "0012")["topik"] == "-"
    assert arsip.baca_teks(GID, "0012") is not None


def test_hapus_menghapus_berkas_dan_entri():
    _contoh(9)
    assert arsip.hapus(GID, "0009") is True
    assert arsip.hapus(GID, "0009") is False
    assert arsip.baca_html(GID, "0009") is None
    assert not list((arsip.ARSIP_DIR / str(GID)).glob("tiket-0009.*"))


def test_statistik_dan_bersihkan_berkas_yatim():
    _contoh(1)
    _contoh(2)
    stat = arsip.statistik(GID)
    assert stat["jumlah"] == 2 and stat["ukuran_kb"] > 0
    assert stat["maksimal"] == arsip.MAX_DISIMPAN
    assert arsip.statistik(9999)["jumlah"] == 0

    # Berkas tanpa entri indeks dibersihkan saat start
    yatim = arsip.ARSIP_DIR / str(GID) / "tiket-0099.html"
    yatim.write_text("<html></html>", "utf-8")
    assert arsip.bersihkan_berkas_yatim() == 1
    assert not yatim.exists()


def test_indeks_dimuat_ulang_dari_disk():
    _contoh(4)
    arsip.reset_cache()
    assert arsip.ambil(GID, "0004")["topik"] == "Nitro tidak masuk"
    assert arsip.statistik(GID)["jumlah"] == 1


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_blok_dan_halaman_arsip_dashboard():
    _contoh(5)
    stat = arsip.statistik(GID)
    terbaru = arsip.daftar(GID, limit=5)

    blok = dashboard_ui.render_arsip_block(GID, "tok", stat, terbaru)
    assert 'action="/transkrip"' in blok
    assert "Buka" in blok and "0005" in blok
    assert "tok" in blok
    kebijakan = (
        f"hapus setelah {arsip.RETENSI_HARI} hari"
        if arsip.RETENSI_HARI
        else "tanpa batas umur"
    )
    assert kebijakan in blok

    halaman = dashboard_ui.render_halaman_arsip(
        GID, "tok", kata="nitro", hasil=arsip.cari(GID, "nitro"), stat=stat,
        nama_server="Server Uji",
    )
    assert halaman.startswith("<!doctype html>")
    assert "/api/transkrip?token=tok" in halaman
    assert 'value="hapus"' in halaman
    assert "Nitro tidak masuk" in halaman
    assert kebijakan in halaman
    # Halaman kosong tetap ramah
    kosong = dashboard_ui.render_halaman_arsip(GID, "tok", kata="zzz", hasil=[], stat=stat)
    assert "Tidak ada arsip yang cocok" in kosong


def test_halaman_tiket_memuat_blok_arsip():
    import web_dashboard

    _contoh(6)
    blok = dashboard_ui.render_arsip_block(
        GID, "tok", arsip.statistik(GID), arsip.daftar(GID, limit=5)
    )
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="tiket", token="tok", guild_id=GID,
        arsip_block=blok,
    )
    assert "Arsip transkrip" in page
    assert 'action="/transkrip"' in page
    assert "Buka arsip lengkap" in page
    # Tanpa blok arsip, halaman tetap tampil (jaring aman)
    polos = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="tiket", token="tok", guild_id=GID
    )
    assert "Arsip transkrip" in polos
