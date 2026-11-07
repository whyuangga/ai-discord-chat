"""Tes Paket E#3 — setelan AI per member & kepribadian AI per server."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import ai_user_settings as aus
from cogs import setelan_ai_cog as sc

UID = 424242
GID = 515151


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    aus.reset_state()
    monkeypatch.setattr(aus, "SETTINGS_FILE", tmp_path / "ai_settings.json")
    yield
    aus.reset_state()


# --------------------------------------------------------------------------- #
# Per member
# --------------------------------------------------------------------------- #

def test_bawaan_lengkap():
    data = aus.get_user(UID)
    assert data == {"panjang": "normal", "prompt": "", "rasio": ""}
    assert aus.gabung_instruksi(UID) == ""  # tidak ada instruksi tambahan


def test_set_user_dan_validasi():
    data = aus.set_user(UID, panjang="detail", prompt="  pakai bahasa santai  ")
    assert data["panjang"] == "detail" and data["prompt"] == "pakai bahasa santai"

    aus.set_user(UID, panjang="panjang-banget")
    assert aus.get_user(UID)["panjang"] == "normal"  # nilai asing → normal

    aus.set_user(UID, prompt="x" * 500)
    assert len(aus.get_user(UID)["prompt"]) == aus.MAKS_PROMPT


def test_setelan_bawaan_tidak_disimpan():
    aus.set_user(UID, panjang="normal", prompt="", rasio="")
    assert UID not in aus.users


def test_reset_user():
    aus.set_user(UID, panjang="singkat", rasio="16:9 (Landscape)")
    aus.reset_user(UID)
    assert aus.get_user(UID) == {"panjang": "normal", "prompt": "", "rasio": ""}
    assert aus.rasio_bawaan(UID) == ""


def test_instruksi_menggabung_member_dan_server():
    aus.set_user(UID, panjang="singkat", prompt="suka analogi")
    aus.set_server_prompt(GID, "ramah dan ringkas", oleh=1)
    teks = aus.gabung_instruksi(UID, GID)
    assert "3 kalimat" in teks and "suka analogi" in teks and "Kepribadian server" in teks
    assert len(teks) <= 900


def test_rasio_bawaan():
    aus.set_user(UID, rasio="9:16 (Portrait/Story)")
    assert aus.rasio_bawaan(UID) == "9:16 (Portrait/Story)"
    assert aus.rasio_bawaan(None) == ""


# --------------------------------------------------------------------------- #
# Per server
# --------------------------------------------------------------------------- #

def test_server_prompt_set_dan_hapus():
    assert aus.set_server_prompt(GID, "  sopan  ", oleh=9) == "sopan"
    assert aus.get_server_prompt(GID) == "sopan"
    assert aus.servers[GID]["oleh"] == 9

    assert aus.set_server_prompt(GID, "x" * 900) == "x" * aus.MAKS_PROMPT_SERVER
    assert aus.set_server_prompt(GID, "   ") == ""
    assert aus.get_server_prompt(GID) == ""


def test_statistik():
    aus.set_user(UID, panjang="detail", prompt="a", rasio="1:1 (Persegi)")
    aus.set_user(UID + 1, panjang="detail")
    aus.set_server_prompt(GID, "kepribadian")
    stat = aus.statistik()
    assert stat["member"] == 2 and stat["server"] == 1
    assert stat["panjang"]["detail"] == 2
    assert stat["prompt_member"] == 1 and stat["rasio"] == 1


# --------------------------------------------------------------------------- #
# Simpan & muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat_putaran_penuh():
    aus.set_user(UID, panjang="detail", prompt="pakai emoji", rasio="4:3 (Klasik)")
    aus.set_server_prompt(GID, "gaya santai", oleh=3)
    await aus.save_to_disk()

    aus.reset_state()
    member, server = aus.load_from_disk()
    assert (member, server) == (1, 1)
    assert aus.get_user(UID)["panjang"] == "detail"
    assert aus.get_server_prompt(GID) == "gaya santai"


def test_muat_berkas_rusak_diabaikan():
    from pathlib import Path

    Path(aus.SETTINGS_FILE).write_text("{rusak", encoding="utf-8")
    assert aus.load_from_disk() == (0, 0)

    Path(aus.SETTINGS_FILE).write_text(
        json.dumps({"users": {"abc": {}, str(UID): {"panjang": "asing", "prompt": ""}},
                    "servers": {str(GID): {"prompt": ""}}}),
        encoding="utf-8",
    )
    assert aus.load_from_disk() == (0, 0)  # nilai bawaan/ kosong tidak dimuat


# --------------------------------------------------------------------------- #
# Command
# --------------------------------------------------------------------------- #

def test_group_setelan_ai():
    nama = {cmd.name for cmd in sc.setelan_ai_group.commands}
    assert nama == {"lihat", "atur", "prompt-server", "reset"}
    assert {c.value for c in sc.PANJANG} == set(aus.PANJANG)
    assert len(sc.RASIO) == 5


def test_hanya_admin_bisa_ubah_prompt_server():
    def _interaksi(**izin):
        perms = SimpleNamespace(
            administrator=izin.get("administrator", False),
            manage_guild=izin.get("manage_guild", False),
        )
        return SimpleNamespace(user=SimpleNamespace(guild_permissions=perms))

    assert sc._admin(_interaksi(administrator=True))
    assert sc._admin(_interaksi(manage_guild=True))
    assert not sc._admin(_interaksi())
