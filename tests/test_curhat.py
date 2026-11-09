"""Tes Paket C#4 — curhat anonim (`/curhat`) tanpa menyimpan isi pesan."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import confessions
import dashboard_curhat
import dashboard_uji
import web_dashboard


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    confessions.reset_runtime_state()
    monkeypatch.setattr(confessions, "CONFESSIONS_FILE", tmp_path / "confessions.json")
    yield
    confessions.reset_runtime_state()


def _siap(gid=1, kanal=555, **kwargs):
    confessions.set_config(gid, enabled=True, channel_id=kanal, **kwargs)


# --------------------------------------------------------------------------- #
# Setelan
# --------------------------------------------------------------------------- #

def test_aktif_butuh_channel_dan_sakelar():
    assert confessions.aktif(1) is False  # default: belum dinyalakan
    confessions.set_config(1, enabled=True)
    assert confessions.aktif(1) is False  # channel belum dipilih
    confessions.set_config(1, channel_id=555)
    assert confessions.aktif(1) is True
    confessions.set_config(1, enabled=False)
    assert confessions.aktif(1) is False


def test_set_config_membatasi_nilai():
    confessions.set_config(1, cooldown_sec=5)
    assert confessions.peek_config(1)["cooldown_sec"] == 30
    confessions.set_config(1, cooldown_sec=999999)
    assert confessions.peek_config(1)["cooldown_sec"] == 86400
    confessions.set_config(1, channel_id="bukan-angka")
    assert confessions.peek_config(1)["channel_id"] is None
    confessions.set_config(1, warna="#abcdef")
    assert confessions.peek_config(1)["warna"] == "#abcdef"


# --------------------------------------------------------------------------- #
# Validasi
# --------------------------------------------------------------------------- #

def test_validasi_panjang_dan_tautan():
    assert confessions.validasi(1, 7, "halo")[0] is False  # belum aktif
    _siap()
    assert confessions.validasi(1, 7, "halo")[0] is False
    assert "10 huruf" in confessions.validasi(1, 7, "halo")[1]
    assert confessions.validasi(1, 7, "x" * 901)[0] is False
    ok, pesan = confessions.validasi(1, 7, "aku capek banget minggu ini")
    assert ok and pesan == "OK"

    assert confessions.validasi(1, 8, "cek https://contoh.com ya")[0] is False
    confessions.set_config(1, izinkan_link=True)
    assert confessions.validasi(1, 8, "cek https://contoh.com ya")[0] is True


def test_jeda_dan_batas_per_jam():
    _siap()
    ok, _ = confessions.validasi(1, 7, "curhat pertama untuk tes jeda", sekarang=1000)
    assert ok
    confessions.catat(1, penulis_hash=confessions.hash_penulis(1, 7), sekarang=1000)

    ok, pesan = confessions.validasi(1, 7, "curhat kedua cepat sekali", sekarang=1010)
    assert ok is False and "menit" in pesan
    assert confessions.sisa_jeda(1, confessions.hash_penulis(1, 7), sekarang=1010) > 0

    # setelah jeda lewat, boleh lagi
    assert confessions.validasi(1, 7, "curhat ketiga setelah jeda", sekarang=1400)[0] is True

    # batas 3 per jam (jeda dipersingkat supaya yang diuji benar-benar batas/jam)
    confessions.set_config(1, cooldown_sec=30)
    for detik in (2000, 2400, 2800):
        assert confessions.validasi(1, 9, "curhat beruntun untuk batas", sekarang=detik)[0] is True
        confessions.catat(1, penulis_hash=confessions.hash_penulis(1, 9), sekarang=detik)
    ok, pesan = confessions.validasi(1, 9, "curhat keempat dalam satu jam", sekarang=3000)
    assert ok is False and "per jam" in pesan


def test_hash_penulis_stabil_dan_tidak_membocorkan_id():
    hash_a = confessions.hash_penulis(1, 12345)
    assert hash_a == confessions.hash_penulis(1, 12345)
    assert hash_a != confessions.hash_penulis(2, 12345)
    assert "12345" not in hash_a
    assert len(hash_a) == 12


# --------------------------------------------------------------------------- #
# Pencatatan
# --------------------------------------------------------------------------- #

def test_catat_memberi_nomor_urut_tanpa_menyimpan_teks():
    _siap()
    nomor = confessions.catat(1, penulis_hash="abc123abc123", pesan_id=10, channel_id=555)
    assert nomor == 1
    nomor2 = confessions.catat(1, penulis_hash="abc123abc123", pesan_id=11, channel_id=555)
    assert nomor2 == 2

    data = confessions.ambil(1, 1)
    assert set(data) == {"nomor", "penulis", "pesan_id", "channel_id", "dibuat"}
    assert "teks" not in json.dumps(data)
    assert confessions.ambil(1, 99) is None


def test_daftar_dan_hapus():
    _siap()
    for pesan_id in (1, 2, 3):
        confessions.catat(1, penulis_hash="hash-hash-ha", pesan_id=pesan_id, channel_id=555)
    daftar = confessions.daftar(1, limit=2)
    assert [item["nomor"] for item in daftar] == [3, 2]
    assert confessions.hapus(1, 2)["nomor"] == 2
    assert confessions.ambil(1, 2) is None
    assert confessions.hapus(1, 2) is None


def test_batas_penyimpanan(monkeypatch):
    monkeypatch.setattr(confessions, "MAKS_SIMPAN", 3)
    _siap()
    for _ in range(6):
        confessions.catat(1, penulis_hash="hash-hash-ha", pesan_id=1, channel_id=555)
    assert len(confessions.conf_items[1]) == 3
    assert confessions.statistik(1)["total"] == 3
    assert confessions.statistik(1)["nomor_terakhir"] == 6


def test_statistik():
    _siap()
    confessions.catat(1, penulis_hash="aaaaaaaaaaaa", pesan_id=1, channel_id=555)
    confessions.catat(1, penulis_hash="bbbbbbbbbbbb", pesan_id=2, channel_id=555)
    data = confessions.statistik(1)
    assert data["aktif"] is True and data["total"] == 2
    assert data["penulis_unik"] == 2 and data["nomor_terakhir"] == 2
    assert data["cooldown_sec"] == 300 and data["channel_id"] == 555


def test_cleanup_membuang_server_tanpa_curhat():
    confessions.set_config(9, enabled=True, channel_id=1)
    _siap()
    confessions.catat(1, penulis_hash="cccccccccccc", pesan_id=1)
    assert confessions.cleanup_confessions_runtime() >= 1
    assert 9 not in confessions.conf_config
    assert 1 in confessions.conf_config


# --------------------------------------------------------------------------- #
# Simpan / muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat_tanpa_isi_curhat(tmp_path):
    _siap(cooldown_sec=120)
    confessions.catat(1, penulis_hash="dddddddddddd", pesan_id=77, channel_id=555)
    await confessions.save_confessions_to_disk()

    mentah = json.loads((tmp_path / "confessions.json").read_text(encoding="utf-8"))
    isi = mentah["guilds"]["1"]
    assert isi["config"]["channel_id"] == 555
    assert isi["nomor"] == 1
    assert isi["items"]["1"]["pesan_id"] == 77
    assert "teks" not in json.dumps(mentah)

    confessions.reset_runtime_state()
    server, total = confessions.load_confessions_from_disk()
    assert (server, total) == (1, 1)
    assert confessions.ambil(1, 1)["penulis"] == "dddddddddddd"
    assert confessions.statistik(1)["nomor_terakhir"] == 1
    assert confessions.peek_config(1)["cooldown_sec"] == 120


@pytest.mark.asyncio
async def test_muat_data_rusak(tmp_path):
    berkas = tmp_path / "confessions.json"
    berkas.write_text("{rusak", encoding="utf-8")
    assert confessions.load_confessions_from_disk() == (0, 0)
    berkas.write_text(json.dumps({"guilds": {"x": 1, "2": "bukan-dict"}}), encoding="utf-8")
    assert confessions.load_confessions_from_disk() == (0, 0)


# --------------------------------------------------------------------------- #
# Command
# --------------------------------------------------------------------------- #

def test_group_curhat_terdaftar():
    from main import bot as bot_main

    grup = bot_main.tree.get_command("curhat")
    assert grup is not None and grup.guild_only is True
    assert {cmd.name for cmd in grup.commands} == {"kirim", "atur", "hapus"}


def test_embed_curhat_tanpa_identitas():
    from cogs.confessions_cog import embed_curhat

    embed = embed_curhat(7, "isi curhat yang cukup panjang")
    assert "Curhat #7" in embed.title
    assert embed.description == "isi curhat yang cukup panjang"
    assert not embed.fields  # tidak ada nama penulis
    panjang = embed_curhat(1, "x" * 5000)
    assert len(panjang.description) <= 4000


@pytest.mark.asyncio
async def test_command_kirim_memposting_anonim(monkeypatch):
    from cogs.confessions_cog import curhat_kirim_cmd

    _siap()
    dikirim = []

    class _Channel:
        id = 555
        mention = "#curhat"

        async def send(self, **kwargs):
            dikirim.append(kwargs)
            return SimpleNamespace(id=9876)

    guild = SimpleNamespace(id=1, get_channel=lambda cid: _Channel() if cid == 555 else None)
    jawaban = []

    class _Interaction:
        def __init__(self):
            self.guild = guild
            self.user = SimpleNamespace(id=7)
            self.response = SimpleNamespace(send_message=self._send)

        async def _send(self, *args, **kwargs):
            jawaban.append((args, kwargs))

    monkeypatch.setattr(
        confessions, "save_confessions_to_disk", lambda: _async_noop()
    )
    await curhat_kirim_cmd.callback(_Interaction(), "aku capek banget minggu ini")
    assert dikirim and "embed" in dikirim[0]
    assert dikirim[0]["embed"].title == "💌 Curhat #1"
    assert jawaban and "#1" in jawaban[0][0][0]
    assert confessions.ambil(1, 1)["pesan_id"] == 9876


async def _async_noop(*args, **kwargs):
    return None


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def test_panel_curhat_menempel_di_halaman_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-curhat"] == "interaksi"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["curhat"] == "interaksi"
    assert dashboard_uji.ANCHOR_UJI["curhat"] == "p-curhat"
    html = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="interaksi",
        curhat_block=dashboard_curhat.render_curhat_block(SimpleNamespace(), 1, "tok"),
    )
    assert 'id="p-curhat"' in html and "curhat-setelan" in html


def test_panel_curhat_render_status():
    _siap()
    confessions.catat(1, penulis_hash="eeeeeeeeeeee", pesan_id=5, channel_id=555)
    html = dashboard_curhat.render_curhat_block(SimpleNamespace(), 1, "tok")
    assert "Curhat anonim" in html
    assert "eeeeeeeeeeee" in html
    assert "curhat-hapus:1" in html
    assert "tidak tersedia" not in html


def test_panel_curhat_peringatkan_channel_kosong():
    confessions.set_config(1, enabled=True)
    html = dashboard_curhat.render_curhat_block(None, 1, "tok")
    assert "belum dipilih" in html


@pytest.mark.asyncio
async def test_aksi_curhat_setelan_dan_hapus():
    ok, pesan = await dashboard_curhat.aksi_curhat(
        1, "curhat-setelan",
        {"enabled": "1", "channel_id": "555", "izinkan_link": "0", "jeda_menit": "10"},
    )
    assert ok and "aktif" in pesan
    cfg = confessions.peek_config(1)
    assert cfg["channel_id"] == 555 and cfg["cooldown_sec"] == 600

    confessions.catat(1, penulis_hash="ffffffffffff", pesan_id=1)
    ok, pesan = await dashboard_curhat.aksi_curhat(1, "curhat-hapus:1", {})
    assert ok and confessions.ambil(1, 1) is None
    ok, pesan = await dashboard_curhat.aksi_curhat(1, "curhat-hapus:9", {})
    assert ok is False
    ok, _ = await dashboard_curhat.aksi_curhat(1, "curhat-ngawur", {})
    assert ok is False


def test_uji_curhat_simulasi_tidak_memakai_nomor():
    ok, pesan = dashboard_uji._uji_curhat(1)
    assert ok is False and "belum dinyalakan" in pesan

    confessions.set_config(1, enabled=True)
    ok, pesan = dashboard_uji._uji_curhat(1)
    assert ok is False and "Channel" in pesan

    _siap()
    ok, pesan = dashboard_uji._uji_curhat(1)
    assert ok is True and "Simulasi" in pesan
    assert confessions.statistik(1)["nomor_terakhir"] == 0  # nomor tidak terpakai
    assert confessions.statistik(1)["total"] == 0
