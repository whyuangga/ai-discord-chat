"""Uji preset & wizard `/mulai` (`presets.py`, `cogs/mulai_cog.py`)."""

from __future__ import annotations

import presets
from cogs.mulai_cog import mulai_cmd


class FakeChannel:
    def __init__(self, channel_id=500, name="sambutan"):
        self.id = channel_id
        self.name = name
        self.mention = f"<#{channel_id}>"


class FakeRole:
    id = 700
    name = "Member"


def test_daftar_preset_dan_pencarian():
    kunci = [p["key"] for p in presets.list_presets()]
    assert "komunitas" in kunci and "gaming" in kunci
    assert presets.get_preset("Komunitas")["label"] == "Server Komunitas"
    assert presets.get_preset("tidak-ada") is None
    assert presets.get_preset(None) is None


def test_build_plan_menandai_yang_belum_siap():
    preset = presets.get_preset("komunitas")
    rencana = presets.build_plan(preset)
    assert [r["aksi"] for r in rencana] == ["sambutan", "autorole", "log", "pengumuman"]
    assert all(r["siap"] is False for r in rencana[:3])
    assert rencana[3]["siap"] is True          # pengumuman tidak butuh pilihan


def test_build_plan_dengan_pilihan_lengkap():
    preset = presets.get_preset("komunitas")
    rencana = presets.build_plan(
        preset,
        channel_sambutan=FakeChannel(1),
        role_otomatis=FakeRole(),
        channel_log=FakeChannel(2, "log"),
    )
    assert all(r["siap"] for r in rencana)
    assert "Member" in rencana[1]["label"]
    assert "Sambutan" in rencana[0]["label"]


def test_ringkas_menyebut_label_dan_deskripsi():
    teks = presets.ringkas(presets.get_preset("gaming"))
    assert "Server Gaming" in teks and "🎮" in teks


def test_command_mulai_terdaftar_dengan_parameter_wajib_opsional():
    nama = {p.name for p in mulai_cmd.parameters}
    assert {"paket", "channel_sambutan", "role_otomatis", "channel_log", "pratinjau"} == nama
    assert all(p.required is False for p in mulai_cmd.parameters)
