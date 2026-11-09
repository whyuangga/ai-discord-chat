"""Tes Paket D#3 — channel info yang menyegarkan dirinya sendiri (`/kanal-info`)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import dashboard_info
import dashboard_uji
import info_channel as ic
import web_dashboard

GID = 123456789012345678
TOKEN = "tok"
CHANNEL_ID = 505
ISI = "Baca aturan dulu: jangan spam, jangan toxic, dan pakai channel yang sesuai."


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    ic.reset_runtime_state()
    monkeypatch.setattr(ic, "INFO_CHANNEL_FILE", tmp_path / "info_channel.json")
    yield
    ic.reset_runtime_state()


def _siap(**kwargs):
    ic.set_config(GID, enabled=True, channel_id=CHANNEL_ID, judul="Aturan Server", **kwargs)
    ic.set_isi(GID, ISI)


class _Message:
    def __init__(self, mid=900):
        self.id = mid
        self.diedit = []

    async def edit(self, **kwargs):
        self.diedit.append(kwargs)


class _Channel:
    def __init__(self, pesan=None, gagal_kirim=False):
        self.id = CHANNEL_ID
        self.pesan = pesan
        self.dikirim = []
        self.gagal_kirim = gagal_kirim

    async def fetch_message(self, mid):
        if self.pesan is None or getattr(self.pesan, "id", 0) != mid:
            raise RuntimeError("pesan hilang")
        return self.pesan

    async def send(self, **kwargs):
        if self.gagal_kirim:
            raise RuntimeError("tidak boleh kirim")
        baru = SimpleNamespace(id=901)
        self.dikirim.append(kwargs)
        return baru


class _Guild:
    def __init__(self, channel=None):
        self.id = GID
        self._channel = channel
        self.text_channels = [channel] if channel is not None else []

    def get_channel(self, cid):
        return self._channel if int(cid or 0) == CHANNEL_ID else None


def _bot(guild=None):
    return SimpleNamespace(get_guild=lambda gid: guild)


# --------------------------------------------------------------------------- #
# Setelan
# --------------------------------------------------------------------------- #

def test_setelan_dasar_dan_aktif():
    assert ic.aktif(GID) is False
    ic.set_config(GID, enabled=True, channel_id=CHANNEL_ID)
    assert ic.aktif(GID) is False  # isi masih kosong
    ic.set_isi(GID, ISI)
    assert ic.aktif(GID) is True
    ic.set_config(GID, enabled=False)
    assert ic.aktif(GID) is False


def test_set_config_membersihkan_nilai():
    ic.set_config(GID, warna="bukan-warna", interval_menit=1)
    cfg = ic.peek_config(GID)
    assert cfg["warna"] == "#5865f2"
    assert cfg["interval_menit"] == ic.INTERVAL_MIN

    ic.set_config(GID, interval_menit=99999)
    assert ic.peek_config(GID)["interval_menit"] == ic.INTERVAL_MAKS
    ic.set_config(GID, judul="x" * 500)
    assert len(ic.peek_config(GID)["judul"]) == ic.MAKS_JUDUL


def test_ganti_channel_mereset_pesan():
    _siap()
    ic.catat_pesan(GID, 77, sekarang=1000.0)
    assert ic.peek_config(GID)["pesan_id"] == 77
    ic.set_config(GID, channel_id=606)
    cfg = ic.peek_config(GID)
    assert cfg["pesan_id"] == 0 and cfg["terakhir"] == 0.0


def test_set_isi_validasi():
    ok, pesan = ic.set_isi(GID, "pendek")
    assert ok is False and str(ic.MIN_ISI) in pesan
    ok, pesan = ic.set_isi(GID, "x" * (ic.MAKS_ISI + 1))
    assert ok is False and str(ic.MAKS_ISI) in pesan
    ok, pesan = ic.set_isi(GID, ISI)
    assert ok is True and ic.peek_config(GID)["isi"] == ISI


def test_hash_dan_kebutuhan_segarkan():
    _siap()
    assert ic.perlu_segarkan(GID) is True  # pesan belum ada
    hash_awal = ic.isi_hash(GID)
    ic.catat_pesan(GID, 77, sekarang=1000.0)
    assert ic.perlu_segarkan(GID) is False
    assert ic.isi_hash(GID) == hash_awal

    ic.set_isi(GID, ISI + " Tambahan penting.")
    assert ic.isi_hash(GID) != hash_awal
    assert ic.perlu_segarkan(GID) is True

    ic.catat_pesan(GID, 77, sekarang=1000.0)
    ic.set_config(GID, judul="Aturan Baru")
    assert ic.perlu_segarkan(GID) is True


def test_perlu_verifikasi_berdasarkan_interval():
    _siap(interval_menit=10)
    assert ic.perlu_verifikasi(GID, sekarang=1000) is False  # pesan belum terbit
    ic.catat_pesan(GID, 77, sekarang=1000.0)
    assert ic.perlu_verifikasi(GID, sekarang=1000) is False
    assert ic.perlu_verifikasi(GID, sekarang=1000 + 599) is False
    assert ic.perlu_verifikasi(GID, sekarang=1000 + 600) is True


def test_build_embed():
    _siap()
    embed = ic.build_embed(GID, sekarang=1000)
    assert embed.title == "Aturan Server"
    assert embed.description == ISI
    assert embed.colour.value == int("5865f2", 16)
    assert "Diperbarui otomatis" in embed.footer.text


def test_statistik():
    _siap()
    data = ic.statistik(GID)
    assert data["aktif"] is True and data["panjang_isi"] == len(ISI)
    assert data["perlu_segarkan"] is True


# --------------------------------------------------------------------------- #
# Penyegaran
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_segarkan_membuat_pesan_baru():
    _siap()
    kanal = _Channel()
    assert await ic.segarkan(_bot(_Guild(kanal)), GID, sekarang=1000) == "dibuat"
    assert len(kanal.dikirim) == 1 and "embed" in kanal.dikirim[0]
    assert ic.peek_config(GID)["pesan_id"] == 901


@pytest.mark.asyncio
async def test_segarkan_mengedit_pesan_lama():
    _siap()
    pesan = _Message(900)
    kanal = _Channel(pesan)
    ic.catat_pesan(GID, 900, sekarang=1000.0)
    ic.set_isi(GID, ISI + " Versi baru.")

    assert await ic.segarkan(_bot(_Guild(kanal)), GID, sekarang=2000) == "diperbarui"
    assert pesan.diedit and kanal.dikirim == []
    assert ic.peek_config(GID)["terakhir"] == 2000


@pytest.mark.asyncio
async def test_segarkan_membuat_ulang_bila_pesan_hilang():
    _siap()
    kanal = _Channel(pesan=None)  # fetch_message akan gagal
    ic.catat_pesan(GID, 900, sekarang=1000.0)
    assert await ic.segarkan(_bot(_Guild(kanal)), GID, sekarang=2000) == "dibuat"
    assert ic.peek_config(GID)["pesan_id"] == 901


@pytest.mark.asyncio
async def test_segarkan_gagal_dan_nonaktif():
    _siap()
    assert await ic.segarkan(_bot(None), GID) == "gagal"          # guild tidak ada
    assert await ic.segarkan(_bot(_Guild(None)), GID) == "gagal"  # channel tidak ada
    kanal = _Channel(gagal_kirim=True)
    assert await ic.segarkan(_bot(_Guild(kanal)), GID) == "gagal"  # izin kirim kurang

    ic.set_config(GID, enabled=False)
    assert await ic.segarkan(_bot(_Guild(kanal)), GID) == "nonaktif"


@pytest.mark.asyncio
async def test_run_check_menyegarkan_yang_perlu():
    _siap(interval_menit=5)
    pesan = _Message(901)
    kanal = _Channel(pesan)
    bot = _bot(_Guild(kanal))

    assert await ic.run_info_channel_check(bot, sekarang=1000) == 1  # terbit pertama kali
    assert await ic.run_info_channel_check(bot, sekarang=1100) == 0  # sudah sama & belum waktunya
    # interval lewat → pesan diverifikasi (diedit ulang sebagai konfirmasi masih ada)
    assert await ic.run_info_channel_check(bot, sekarang=1000 + 400) == 1
    assert pesan.diedit

    ic.set_isi(GID, ISI + " Update.")
    assert await ic.run_info_channel_check(bot, sekarang=1500) == 1


# --------------------------------------------------------------------------- #
# Simpan / muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat(tmp_path):
    _siap(interval_menit=30)
    ic.catat_pesan(GID, 77, sekarang=1000.0)
    await ic.save_info_channel_to_disk()

    mentah = json.loads((tmp_path / "info_channel.json").read_text(encoding="utf-8"))
    assert mentah["guilds"][str(GID)]["channel_id"] == CHANNEL_ID
    assert mentah["guilds"][str(GID)]["isi"] == ISI

    ic.reset_runtime_state()
    assert ic.load_info_channel_from_disk() == 1
    cfg = ic.peek_config(GID)
    assert cfg["pesan_id"] == 77 and cfg["interval_menit"] == 30
    assert ic.aktif(GID) is True


def test_muat_berkas_rusak(tmp_path):
    berkas = tmp_path / "info_channel.json"
    berkas.write_text("{rusak", encoding="utf-8")
    assert ic.load_info_channel_from_disk() == 0
    berkas.write_text(json.dumps({"guilds": {"x": 1, "2": "bukan-dict"}}), encoding="utf-8")
    assert ic.load_info_channel_from_disk() == 0


def test_cleanup_membuang_server_kosong():
    ic.set_config(9, judul="Kosong")
    _siap()
    assert ic.cleanup_info_channel_runtime() >= 1
    assert 9 not in ic.info_guilds
    assert GID in ic.info_guilds


# --------------------------------------------------------------------------- #
# Command & dashboard
# --------------------------------------------------------------------------- #

def test_group_kanal_info_terdaftar():
    from cogs.info_channel_cog import kanal_info_group

    assert kanal_info_group.name == "kanal-info"
    nama = {cmd.name for cmd in kanal_info_group.commands}
    assert nama == {"atur", "isi", "segarkan", "status"}
    for cmd in kanal_info_group.commands:
        assert len(cmd.description) <= 100, cmd.name


def test_panel_info_menempel_di_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-info"] == "interaksi"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["info"] == "interaksi"
    assert dashboard_uji.ANCHOR_UJI["info"] == "p-info"


def test_panel_info_render():
    _siap()
    kanal = _Channel()
    html = dashboard_info.render_info_block(_bot(_Guild(kanal)), GID, TOKEN)
    assert 'class="subpanel" id="p-info"' in html
    assert "info-setelan" in html and "info-isi" in html and "info-segarkan" in html
    assert "Aturan Server" in html
    assert ISI in html  # pratinjau
    assert "#505" not in html or "channel" in html


def test_panel_info_peringatkan_setelan_kurang():
    ic.set_config(GID, enabled=True)
    html = dashboard_info.render_info_block(None, GID, TOKEN)
    assert "Channel belum dipilih" in html
    ic.set_config(GID, channel_id=CHANNEL_ID)
    html = dashboard_info.render_info_block(None, GID, TOKEN)
    assert "Isi masih kosong" in html


@pytest.mark.asyncio
async def test_aksi_info_setelan_isi_dan_segarkan():
    kanal = _Channel()
    bot = _bot(_Guild(kanal))

    ok, pesan = await dashboard_info.aksi_info(
        bot, GID, "info-setelan",
        {"enabled": "1", "channel_id": str(CHANNEL_ID), "judul": "Info", "warna": "#ff0000",
         "interval_menit": "15"},
    )
    assert ok and "nonaktif" in pesan  # isi belum ada
    assert ic.peek_config(GID)["warna"] == "#ff0000"

    ok, pesan = await dashboard_info.aksi_info(bot, GID, "info-isi", {"isi": ISI})
    assert ok and "dibuat" in pesan
    assert kanal.dikirim

    ok, pesan = await dashboard_info.aksi_info(bot, GID, "info-segarkan", {})
    assert ok is True

    ok, pesan = await dashboard_info.aksi_info(bot, GID, "info-isi", {"isi": "pendek"})
    assert ok is False and "pendek" in pesan

    ok, pesan = await dashboard_info.aksi_info(bot, GID, "info-ngawur", {})
    assert ok is False


def test_uji_info_simulasi():
    ok, pesan = dashboard_uji._uji_info(GID)
    assert ok is False and "belum dipilih" in pesan

    ic.set_config(GID, enabled=True, channel_id=CHANNEL_ID)
    ok, pesan = dashboard_uji._uji_info(GID)
    assert ok is False and "masih kosong" in pesan

    _siap()
    ic.set_config(GID, enabled=False)
    ok, pesan = dashboard_uji._uji_info(GID)
    assert ok is False and "nonaktif" in pesan

    ic.set_config(GID, enabled=True)
    ok, pesan = dashboard_uji._uji_info(GID)
    assert ok is True and "Simulasi" in pesan
    assert ic.peek_config(GID)["pesan_id"] == 0  # tidak menerbitkan pesan
