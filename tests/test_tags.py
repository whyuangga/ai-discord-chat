"""Paket C#1: tag jawaban siap pakai (`/tag`) + panel dashboard — 0 kuota AI.

Yang dikunci: isi tag **tidak pernah** dikirim ke AI, penghitung pemakaian hanya
naik saat tag benar-benar dipanggil member, dan panel dashboard bisa membuat /
memperbarui / menghapus tag tanpa JavaScript.
"""

from __future__ import annotations

import pytest

import dashboard_tags
import dashboard_uji
import tags
import web_dashboard

GID = 9701
TOKEN = "tok-tag"


@pytest.fixture(autouse=True)
def _bersihkan():
    tags.reset_runtime_state()
    yield
    tags.reset_runtime_state()


# ==============================================================================
# NAMA & OPERASI DASAR
# ==============================================================================
@pytest.mark.parametrize(
    "masukan,harapan",
    [
        ("Aturan Server", "aturan-server"),
        ("  HARGA!!!  ", "harga"),
        ("jadwal open order", "jadwal-open-order"),
        ("emoji🎉tag", "emoji-tag"),
        ("", ""),
        ("---", ""),
    ],
)
def test_normalisasi_nama(masukan, harapan):
    assert tags.normalisasi(masukan) == harapan


def test_nama_dibatasi_panjangnya():
    assert len(tags.normalisasi("a" * 100)) == tags.TAG_NAMA_MAKS


def test_tambah_tag():
    kode, tag = tags.tambah(GID, "Aturan Server", "Hormati semua member.")
    assert kode == "ok"
    assert tag["nama"] == "aturan-server"
    assert tags.ambil(GID, "aturan server") is tag   # nama dinormalisasi saat dicari


def test_tambah_validasi():
    assert tags.tambah(GID, "", "isi")[0] == "nama_kosong"
    assert tags.tambah(GID, "kosong", "  ")[0] == "isi_kosong"
    tags.tambah(GID, "aturan", "Hormati semua member.")
    kode, tag = tags.tambah(GID, "Aturan", "isi lain")
    assert kode == "sudah_ada"
    assert tag["isi"] == "Hormati semua member."   # tidak menimpa diam-diam


def test_batas_jumlah_tag(monkeypatch):
    monkeypatch.setattr(tags, "MAX_TAG_PER_GUILD", 2)
    assert tags.tambah(GID, "satu", "isi satu")[0] == "ok"
    assert tags.tambah(GID, "dua", "isi dua")[0] == "ok"
    assert tags.tambah(GID, "tiga", "isi tiga")[0] == "penuh"


def test_ubah_tag():
    tags.tambah(GID, "harga", "Mulai 50rb")
    kode, tag = tags.ubah(GID, "harga", "Mulai 75rb")
    assert kode == "ok" and tag["isi"] == "Mulai 75rb"
    assert tags.ubah(GID, "tidak-ada", "isi")[0] == "tidak_ada"
    assert tags.ubah(GID, "harga", " ")[0] == "isi_kosong"
    assert tags.ambil(GID, "harga")["isi"] == "Mulai 75rb"


def test_isi_dibatasi_panjangnya():
    _, tag = tags.tambah(GID, "panjang", "x" * 5000)
    assert len(tag["isi"]) == tags.TAG_ISI_MAKS


def test_hapus_tag():
    tags.tambah(GID, "harga", "Mulai 50rb")
    assert tags.hapus(GID, "HARGA") is True
    assert tags.hapus(GID, "harga") is False
    assert tags.ambil(GID, "harga") is None


def test_penghitung_pemakaian():
    tags.tambah(GID, "aturan", "Hormati semua member.")
    assert tags.ambil(GID, "aturan")["dipakai"] == 0      # dashboard tidak menaikkan
    assert tags.pakai(GID, "aturan")["dipakai"] == 1
    assert tags.pakai(GID, "aturan")["dipakai"] == 2
    assert tags.pakai(GID, "tidak-ada") is None


def test_daftar_dan_cari():
    tags.tambah(GID, "aturan", "Hormati semua member.")
    tags.tambah(GID, "harga", "Refund hanya untuk produk rusak.")
    assert [t["nama"] for t in tags.daftar(GID)] == ["aturan", "harga"]
    assert [t["nama"] for t in tags.cari(GID, "refund")] == ["harga"]   # cari di isi
    assert [t["nama"] for t in tags.cari(GID, "atur")] == ["aturan"]     # cari di nama
    assert tags.cari(GID, "zzz") == []
    assert len(tags.cari(GID, "")) == 2                                   # kosong = semua


def test_statistik():
    tags.tambah(GID, "aturan", "Hormati semua member.")
    tags.tambah(GID, "harga", "Refund hanya untuk produk rusak.")
    tags.pakai(GID, "aturan")
    tags.pakai(GID, "aturan")
    data = tags.statistik(GID)
    assert data["total"] == 2 and data["batas"] == tags.MAX_TAG_PER_GUILD
    assert data["dipakai"] == 2
    assert data["teratas"][0] == {"nama": "aturan", "dipakai": 2}
    assert data["belum_dipakai"] == 1
    assert data["aktif"] is True


def test_setelan_aktif():
    assert tags.peek_config(GID)["enabled"] is True       # default tanpa entri
    tags.set_config(GID, enabled=False)
    assert tags.statistik(GID)["aktif"] is False
    tags.set_config(GID, enabled=True)
    assert tags.statistik(GID)["aktif"] is True


def test_cleanup_membuang_server_kosong():
    tags.tambah(GID, "aturan", "Hormati semua member.")
    tags.set_config(GID, enabled=True)
    tags.hapus(GID, "aturan")
    assert tags.cleanup_tags_runtime() >= 1
    assert tags.daftar(GID) == []


@pytest.mark.asyncio
async def test_simpan_dan_muat(monkeypatch, tmp_path):
    berkas = tmp_path / "tags.json"
    monkeypatch.setattr(tags, "TAGS_FILE", berkas)

    tags.tambah(GID, "aturan", "Hormati semua member.", oleh=99)
    tags.pakai(GID, "aturan")
    tags.set_config(GID, enabled=False)
    await tags.save_tags_to_disk()

    tags.reset_runtime_state()
    server, jumlah = tags.load_tags_from_disk()
    assert (server, jumlah) == (1, 1)
    tag = tags.ambil(GID, "aturan")
    assert tag["isi"] == "Hormati semua member."
    assert tag["dipakai"] == 1 and tag["oleh"] == 99
    assert tags.peek_config(GID)["enabled"] is False


# ==============================================================================
# COMMAND
# ==============================================================================
def test_command_tag_terdaftar():
    from cogs.tags_cog import tag_group

    assert {c.name for c in tag_group.commands} == {
        "lihat", "daftar", "cari", "buat", "ubah", "hapus"
    }
    lihat = next(c for c in tag_group.commands if c.name == "lihat")
    assert {p.name for p in lihat.parameters} == {"nama"}


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_panel_tag_menampilkan_tag_dan_form():
    tags.tambah(GID, "aturan", "Hormati semua member.")
    html = dashboard_tags.render_tags_block(None, GID, TOKEN)
    assert 'id="p-tag"' in html
    assert "tag-simpan" in html and "tag-hapus:aturan" in html
    assert "aturan-server" in html          # nama tampil ternormalisasi
    assert "Hormati semua member." in html   # isi tag ikut terlihat
    assert "0 kuota AI" in html


def test_panel_tag_kosong_tetap_bisa_diisi():
    html = dashboard_tags.render_tags_block(None, GID, TOKEN)
    assert "Belum ada tag" in html
    assert "tag-simpan" in html


def test_simpan_tag_dari_dashboard():
    ok, pesan = dashboard_tags.simpan_tag(GID, {"nama": "Aturan Server", "isi": "Hormati semua."})
    assert ok and "aturan-server" in pesan
    assert tags.ambil(GID, "aturan-server")["isi"] == "Hormati semua."

    # Simpan ulang = perbarui, bukan duplikat
    ok, _ = dashboard_tags.simpan_tag(GID, {"nama": "aturan-server", "isi": "Hormati semua, tanpa kecuali."})
    assert ok and tags.statistik(GID)["total"] == 1
    assert "tanpa kecuali" in tags.ambil(GID, "aturan-server")["isi"]

    assert dashboard_tags.simpan_tag(GID, {"nama": "", "isi": "x"})[0] is False
    assert dashboard_tags.simpan_tag(GID, {"nama": "pendek", "isi": "x"})[0] is False


def test_uji_tag_hanya_simulasi():
    ok, pesan = dashboard_uji._uji_tag(GID)
    assert ok is True and "belum ada isinya" in pesan

    tags.tambah(GID, "aturan", "Hormati semua member.")
    ok, pesan = dashboard_uji._uji_tag(GID)
    assert ok is True and "Simulasi saja" in pesan
    assert tags.ambil(GID, "aturan")["dipakai"] == 0     # tidak menaikkan penghitung

    tags.set_config(GID, enabled=False)
    ok, pesan = dashboard_uji._uji_tag(GID)
    assert ok is False and "dimatikan" in pesan


def test_panel_tag_menempel_di_halaman_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-tag"] == "interaksi"
    assert "tag" in web_dashboard.UJI_HALAMAN["interaksi"]

    halaman = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="interaksi", token=TOKEN, guild_id=GID,
        tag_block=dashboard_tags.render_tags_block(None, GID, TOKEN),
    )
    assert "tag-simpan" in halaman
    assert "<script" not in halaman.lower()
