"""Tes Paket D#5 — antrean submission formulir (kotak masuk dashboard)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import dashboard_form_inbox
import dashboard_uji
import modal_forms
import web_dashboard

GID = 123456789012345678
TOKEN = "tok"


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    modal_forms.forms.clear()
    modal_forms.reset_inbox_state()
    modal_forms._cooldown.clear()
    monkeypatch.setattr(modal_forms, "FORMS_FILE", tmp_path / "forms.json")
    monkeypatch.setattr(modal_forms, "DATA_DIR", tmp_path)
    yield
    modal_forms.forms.clear()
    modal_forms.reset_inbox_state()


def _form(nama="Pendaftaran Staff"):
    return {
        "id": "f1",
        "name": nama,
        "fields": [{"id": "nama", "label": "Nama"}, {"id": "alasan", "label": "Alasan"}],
    }


def _catat(**kwargs):
    return modal_forms.catat_submission(
        GID, _form(), user_id=5, user_nama="Sari", values={"nama": "Sari", "alasan": "Suka server"}, **kwargs
    )


# --------------------------------------------------------------------------- #
# Antrean
# --------------------------------------------------------------------------- #

def test_catat_submission_memberi_nomor_urut():
    pertama = _catat(sekarang=100.0)
    kedua = modal_forms.catat_submission(
        GID, _form("Laporan Bug"), user_id=6, user_nama="Budi", values={"nama": "Budi"}, sekarang=200.0
    )
    assert pertama["nomor"] == 1 and kedua["nomor"] == 2
    assert pertama["status"] == modal_forms.STATUS_BARU
    assert pertama["form_nama"] == "Pendaftaran Staff"
    assert pertama["nilai"] == {"Nama": "Sari", "Alasan": "Suka server"}
    assert kedua["form_id"] == "f1" and kedua["user_id"] == 6


def test_nilai_dipangkas_dan_server_lain_terpisah():
    panjang = "x" * 5000
    entri = modal_forms.catat_submission(
        GID, _form(), user_id=5, user_nama="Sari", values={"alasan": panjang}
    )
    assert len(entri["nilai"]["Alasan"]) == modal_forms.MAKS_JAWABAN_SIMPAN

    lain = modal_forms.catat_submission(999, _form(), user_id=7, user_nama="Eka", values={"nama": "Eka"})
    assert lain["nomor"] == 1  # nomor per server
    assert len(modal_forms.daftar_submission(GID)) == 1


def test_batas_antrean_membuang_yang_tertua(monkeypatch):
    monkeypatch.setattr(modal_forms, "MAKS_ANTREAN", 3)
    for i in range(5):
        modal_forms.catat_submission(
            GID, _form(), user_id=i, user_nama=f"U{i}", values={"nama": f"U{i}"}, sekarang=100.0 + i
        )
    daftar = modal_forms.daftar_submission(GID)
    assert [entri["nomor"] for entri in daftar] == [5, 4, 3]


def test_daftar_terbaru_dulu_dan_filter_status():
    _catat(sekarang=100.0)
    _catat(sekarang=200.0)
    daftar = modal_forms.daftar_submission(GID)
    assert [entri["nomor"] for entri in daftar] == [2, 1]
    assert modal_forms.daftar_submission(GID, limit=1)[0]["nomor"] == 2

    modal_forms.tandai_submission(GID, 1, selesai=True, oleh=99)
    assert [e["nomor"] for e in modal_forms.daftar_submission(GID, status="selesai")] == [1]
    assert [e["nomor"] for e in modal_forms.daftar_submission(GID, status="baru")] == [2]


def test_tandai_dan_hapus():
    _catat()
    assert modal_forms.tandai_submission(GID, 1, selesai=True, oleh=77, sekarang=500.0) is True
    entri = modal_forms.ambil_submission(GID, 1)
    assert entri["status"] == "selesai" and entri["oleh"] == 77 and entri["pada"] == 500.0

    assert modal_forms.tandai_submission(GID, 1, selesai=False) is True
    assert entri["status"] == "baru" and entri["oleh"] == 0 and entri["pada"] == 0.0

    assert modal_forms.hapus_submission(GID, 1) is True
    assert modal_forms.hapus_submission(GID, 1) is False
    assert modal_forms.ambil_submission(GID, 1) is None
    assert modal_forms.tandai_submission(GID, 99) is False


def test_statistik_inbox():
    _catat(sekarang=100.0)
    _catat(sekarang=200.0)
    modal_forms.tandai_submission(GID, 2, selesai=True)
    data = modal_forms.statistik_inbox(GID)
    assert data["total"] == 2 and data["baru"] == 1 and data["selesai"] == 1
    assert data["terakhir"] == 200.0
    assert modal_forms.statistik_inbox(999)["total"] == 0


def test_cleanup_membuang_entri_lama():
    _catat(sekarang=100.0)
    _catat(sekarang=100.0 + modal_forms.ANTREAN_SIMPAN_HARI * 86400 + 10)
    dibuang = modal_forms.cleanup_inbox_runtime(
        sekarang=100.0 + modal_forms.ANTREAN_SIMPAN_HARI * 86400 + 20
    )
    assert dibuang == 1
    assert [e["nomor"] for e in modal_forms.daftar_submission(GID)] == [2]


# --------------------------------------------------------------------------- #
# submit_form mencatat ke antrean
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_submit_form_mencatat_walau_channel_hilang():
    jawaban = []

    class _Response:
        async def send_message(self, isi, **kwargs):
            jawaban.append(isi)

    interaksi = SimpleNamespace(
        guild=SimpleNamespace(id=GID),
        user=SimpleNamespace(id=5, display_name="Sari", name="Sari"),
        client=None,
        response=_Response(),
    )
    form = _form()
    ok = await modal_forms.submit_form(interaksi, form, {"nama": "Sari", "alasan": "Halo"})
    assert ok is False  # channel tujuan belum diatur
    assert "channel tujuan" in jawaban[0].lower() or "tidak ditemukan" in jawaban[0].lower()

    entri = modal_forms.daftar_submission(GID)[0]
    assert entri["user_id"] == 5 and entri["user_nama"] == "Sari"
    assert entri["nilai"]["Alasan"] == "Halo"


@pytest.mark.asyncio
async def test_submit_form_mode_uji_tidak_mengisi_antrean():
    class _Response:
        async def defer(self, **kwargs):
            return None

    class _Followup:
        async def send(self, **kwargs):
            return None

    interaksi = SimpleNamespace(
        guild=SimpleNamespace(id=GID),
        user=SimpleNamespace(id=5, display_name="Sari", name="Sari"),
        response=_Response(),
        followup=_Followup(),
    )
    assert await modal_forms.submit_form(interaksi, _form(), {"nama": "Sari"}, uji=True) is True
    assert modal_forms.daftar_submission(GID) == []


# --------------------------------------------------------------------------- #
# Simpan / muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat_antrean(tmp_path):
    _catat(sekarang=100.0)
    modal_forms.tandai_submission(GID, 1, selesai=True, oleh=9, sekarang=150.0)
    await modal_forms.save_to_disk()

    mentah = json.loads((tmp_path / "forms.json").read_text(encoding="utf-8"))
    assert mentah["inbox"][str(GID)]["1"]["status"] == "selesai"
    assert mentah["inbox"][str(GID)]["1"]["nilai"]["Alasan"] == "Suka server"

    modal_forms.reset_inbox_state()
    modal_forms.load_from_disk()
    entri = modal_forms.ambil_submission(GID, 1)
    assert entri["status"] == "selesai" and entri["oleh"] == 9
    # nomor berikutnya lanjut, bukan mulai dari 1 lagi
    assert _catat()["nomor"] == 2


def test_muat_antrean_rusak(tmp_path):
    berkas = tmp_path / "forms.json"
    berkas.write_text(json.dumps({"guilds": {}, "inbox": {"x": 1, "2": "bukan-dict"}}), encoding="utf-8")
    assert modal_forms.load_from_disk() == 0
    assert modal_forms.daftar_submission(2) == []

    berkas.write_text("{rusak", encoding="utf-8")
    assert modal_forms.load_from_disk() == 0


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def test_panel_inbox_menempel_di_halaman_buat():
    assert web_dashboard.ANCHOR_HALAMAN["p-form-inbox"] == "buat"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["formulir"] == "buat"
    assert dashboard_uji.ANCHOR_UJI["formulir"] == "p-form-inbox"
    halaman = {h["slug"]: h for h in web_dashboard.HALAMAN}
    assert "p-form-inbox" in halaman["buat"]["panel"]


def test_panel_inbox_render():
    _catat(sekarang=100.0)
    html = dashboard_form_inbox.render_inbox_block(None, GID, TOKEN)
    assert 'class="subpanel" id="p-form-inbox"' in html
    assert "Kotak masuk formulir" in html
    assert "Pendaftaran Staff" in html and "Sari" in html
    assert "Suka server" in html
    assert "inbox-selesai:1" in html and "inbox-hapus:1" in html
    assert "belum ditinjau" in html


def test_panel_inbox_escape_html():
    modal_forms.catat_submission(
        GID, _form(), user_id=5, user_nama="<b>Sari</b>", values={"nama": "<script>x</script>"}
    )
    html = dashboard_form_inbox.render_inbox_block(None, GID, TOKEN)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;Sari&lt;/b&gt;" in html


def test_panel_inbox_kosong():
    html = dashboard_form_inbox.render_inbox_block(None, GID, TOKEN)
    assert "Belum ada jawaban formulir" in html


@pytest.mark.asyncio
async def test_aksi_inbox_selesai_buka_hapus():
    _catat()
    ok, pesan = await dashboard_form_inbox.aksi_inbox(GID, "inbox-selesai:1", {})
    assert ok and modal_forms.ambil_submission(GID, 1)["status"] == "selesai"

    ok, pesan = await dashboard_form_inbox.aksi_inbox(GID, "inbox-buka:1", {})
    assert ok and modal_forms.ambil_submission(GID, 1)["status"] == "baru"

    ok, pesan = await dashboard_form_inbox.aksi_inbox(GID, "inbox-hapus:1", {})
    assert ok and modal_forms.ambil_submission(GID, 1) is None

    ok, pesan = await dashboard_form_inbox.aksi_inbox(GID, "inbox-hapus:1", {})
    assert ok is False
    ok, pesan = await dashboard_form_inbox.aksi_inbox(GID, "inbox-ngawur", {})
    assert ok is False


def test_uji_formulir_simulasi():
    ok, pesan = dashboard_uji._uji_formulir(GID)
    assert ok is False and "Belum ada formulir" in pesan

    modal_forms.forms.setdefault(GID, {})["f1"] = {
        **_form(),
        "title": "Pendaftaran",
        "description": "",
        "result_text": "",
        "channel_id": None,
        "color": None,
        "responses": 0,
        "created_at": 0.0,
    }
    ok, pesan = dashboard_uji._uji_formulir(GID)
    assert ok is True and "Simulasi" in pesan
    assert modal_forms.daftar_submission(GID) == []  # tidak membuat submission
