"""Tes Paket E#2 (`/gambar`) & E#5 (`/dataku`, `/hapusdataku`)."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import discord
import pytest

import ai_handler
import user_data
from cogs import dataku_cog as dc
from cogs import gambar_cog as gc


# --------------------------------------------------------------------------- #
# /gambar
# --------------------------------------------------------------------------- #

def test_group_gambar_dan_pilihan():
    nama = {cmd.name for cmd in gc.gambar_group.commands}
    assert nama == {"buat", "edit", "pilihan"}
    assert len(gc.RASIO) == 5 and len(gc.GAYA) >= 3
    assert {c.value for c in gc.RASIO} <= set(gc.config.RATIO_OPTIONS)


def test_jeda_per_user():
    gc._jeda.clear()
    gc._jeda[7] = __import__("time").time()
    assert gc._sisa_jeda(7) > 0
    assert gc._sisa_jeda(8) == 0
    gc._jeda.clear()


@pytest.mark.asyncio
async def test_lampiran_none_tidak_membaca_apa_pun():
    parts, nama = await gc._part_dari_lampiran(None)
    assert parts == [] and nama == ""


class _Followup:
    def __init__(self):
        self.kirim = []

    async def send(self, *args, **kwargs):
        if args:
            kwargs = dict(kwargs, content=args[0])
        self.kirim.append(kwargs)


class _Resp:
    def __init__(self):
        self.defered = False
        self.pesan = []

    async def defer(self, *args, **kwargs):
        self.defered = True

    async def send_message(self, *args, **kwargs):
        self.pesan.append((args, kwargs))


def _interaksi(uid=31, cid=99):
    interaksi = SimpleNamespace(
        user=SimpleNamespace(id=uid),
        channel_id=cid,
        guild=SimpleNamespace(id=555),
        response=_Resp(),
        followup=_Followup(),
    )
    return interaksi


@pytest.mark.asyncio
async def test_buat_gambar_mengirim_berkas(monkeypatch):
    gc._jeda.clear()
    dipanggil = {}

    async def _palsu(thread_id, prompt, **kwargs):
        dipanggil["args"] = (thread_id, prompt, kwargs)
        return "gemini", discord.File(io.BytesIO(b"\x89PNG\r\n\x1a\nxx"), filename="hasil.png"), None

    monkeypatch.setattr(ai_handler, "generate_image", _palsu)
    interaksi = _interaksi()

    await gc._jawab_gambar(interaksi, "kucing astronot", rasio="16:9 (Landscape)", gaya="Anime")
    assert dipanggil["args"][2]["ratio"] == "16:9 (Landscape)"
    assert dipanggil["args"][2]["style"] == "Anime"
    assert interaksi.followup.kirim[-1]["file"] is not None
    assert "Gambar baru" in interaksi.followup.kirim[-1]["content"]


@pytest.mark.asyncio
async def test_jeda_memblokir_permintaan_kedua(monkeypatch):
    gc._jeda.clear()

    async def _palsu(*args, **kwargs):
        return "gemini", discord.File(io.BytesIO(b"x"), filename="a.png"), None

    monkeypatch.setattr(ai_handler, "generate_image", _palsu)
    interaksi = _interaksi(uid=77)
    await gc._jawab_gambar(interaksi, "satu")

    kedua = _interaksi(uid=77)
    await gc._jawab_gambar(kedua, "dua")
    assert "Tunggu" in kedua.response.pesan[-1][0][0]
    gc._jeda.clear()


@pytest.mark.asyncio
async def test_edit_tanpa_acuan_dan_tanpa_riwayat():
    gc._terakhir.clear()
    interaksi = _interaksi(uid=88, cid=1234)
    await gc._jawab_gambar(interaksi, "jadikan biru", edit=True)
    pesan = interaksi.response.pesan[-1][0][0]
    assert "Belum ada gambar" in pesan


@pytest.mark.asyncio
async def test_edit_memakai_gambar_terakhir(monkeypatch):
    gc._jeda.clear()
    gc._terakhir[4321] = ({"inlineData": {"mimeType": "image/png", "data": "AAA"}}, "lama.png")
    dipanggil = {}

    async def _palsu(thread_id, prompt, **kwargs):
        dipanggil["ref"] = kwargs.get("reference_images")
        return "gemini", discord.File(io.BytesIO(b"x"), filename="b.png"), None

    monkeypatch.setattr(ai_handler, "generate_image", _palsu)
    interaksi = _interaksi(uid=99, cid=4321)
    await gc._jawab_gambar(interaksi, "tambahkan topi", edit=True)

    assert dipanggil["ref"][0]["inlineData"]["data"] == "AAA"
    assert "Acuan" in interaksi.followup.kirim[-1]["content"]
    gc._jeda.clear()
    gc._terakhir.clear()


# --------------------------------------------------------------------------- #
# /dataku & /hapusdataku
# --------------------------------------------------------------------------- #

def _isi_data():
    import achievements
    import economy
    import engagement
    import games
    import highlights
    import levels
    import modal_forms

    levels.levels.clear()
    levels.levels["10:5"] = {"xp": 120, "level": 3, "messages": 40}
    levels.levels["10:6"] = {"xp": 5, "level": 0, "messages": 2}

    economy.balances.clear()
    economy.meta.clear()
    economy.balances["10:5"] = 500
    economy.meta["10:5"] = {"streak": 2}
    economy.balances["10:6"] = 90

    achievements.ach_members.clear()
    achievements.ach_members[10] = {5: {"lencana": {"chat": 2}}, 6: {"lencana": {"chat": 1}}}

    highlights.hl_members.clear()
    highlights.hl_members[10] = {
        5: {"keywords": ["kucing"], "ignore_channels": [1], "hit": 3},
        6: {"keywords": ["anjing"], "ignore_channels": [], "hit": 0},
    }

    engagement.birthdays.clear()
    engagement.birthdays["10:5"] = {"day": 1, "month": 2}
    engagement.birthdays["10:6"] = {"day": 3, "month": 4}

    games.guild_game_scores.clear()
    games.guild_game_scores[10] = {"tebak": {5: 7, 6: 4}}

    modal_forms.form_inbox.clear()
    modal_forms.form_inbox[10] = {
        1: {"user_id": 5, "form_nama": "Rekrutmen", "nilai": {"Nama": "Budi"}, "dibuat": 1.0},
        2: {"user_id": 6, "form_nama": "Rekrutmen", "nilai": {"Nama": "Sari"}, "dibuat": 2.0},
    }


def test_kumpulkan_hanya_data_user_itu():
    _isi_data()
    data = user_data.kumpulkan(5)
    modul = data["modul"]
    assert data["user_id"] == 5
    assert modul["level"]["jumlah"] == 1
    assert modul["ekonomi"]["data"][0]["koin"] == 500
    assert modul["lencana"]["jumlah"] == 1
    assert modul["highlight"]["data"][0]["kata_kunci"] == ["kucing"]
    assert modul["ultah"]["jumlah"] == 1
    assert modul["game"]["jumlah"] == 1
    assert modul["formulir"]["jumlah"] == 1

    teks = user_data.ringkas(data)
    assert "level" in teks and "formulir" in teks
    json.dumps(data)  # harus bisa diserialkan


def test_hapus_hanya_data_user_itu():
    _isi_data()
    dihapus = user_data.hapus(5)
    assert dihapus["level"] == 1 and dihapus["ekonomi"] == 1
    assert dihapus["lencana"] == 1 and dihapus["highlight"] == 1
    assert dihapus["ultah"] == 1 and dihapus["game"] == 1 and dihapus["formulir"] == 1

    import achievements
    import economy
    import engagement
    import games
    import highlights
    import levels
    import modal_forms

    assert "10:5" not in levels.levels and "10:6" in levels.levels
    assert "10:5" not in economy.balances and "10:6" in economy.balances
    assert "10:5" not in economy.meta
    assert 5 not in achievements.ach_members[10] and 6 in achievements.ach_members[10]
    assert 5 not in highlights.hl_members[10]
    assert "10:5" not in engagement.birthdays
    assert 5 not in games.guild_game_scores[10]
    assert modal_forms.form_inbox[10].keys() == {2}


def test_ringkas_tanpa_data():
    assert "Tidak ada data" in user_data.ringkas({"modul": {}})


def test_command_dataku_terdaftar():
    assert dc.dataku_cmd.name == "dataku"
    assert dc.hapusdataku_cmd.name == "hapusdataku"


@pytest.mark.asyncio
async def test_tombol_hapus_menghapus_data_sendiri(monkeypatch):
    _isi_data()
    belum = []

    async def _simpan():
        belum.append(True)

    monkeypatch.setattr(user_data, "simpan_semua", _simpan)

    interaksi = SimpleNamespace(
        user=SimpleNamespace(id=5),
        response=SimpleNamespace(defer=_defer),
        followup=_Followup(),
    )
    view = dc.KonfirmasiHapus(5)
    await view.hapus.callback(interaksi)
    assert belum == [True]
    assert "sudah dihapus" in interaksi.followup.kirim[-1]["content"]

    _isi_data()
    orang_lain = SimpleNamespace(
        user=SimpleNamespace(id=9),
        response=SimpleNamespace(send_message=_kirim_pesan),
        followup=_Followup(),
    )
    await view.hapus.callback(orang_lain)
    import levels

    assert "10:5" in levels.levels  # tombol orang lain tidak menghapus


async def _defer(*args, **kwargs):
    return None


async def _kirim_pesan(*args, **kwargs):
    return None
