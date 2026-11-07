"""Tes Paket C#5 — snipe & edit-snipe (memori saja, khusus staf)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import dashboard_snipe
import dashboard_uji
import snipe
import web_dashboard


@pytest.fixture(autouse=True)
def _bersih():
    snipe.reset_runtime_state()
    yield
    snipe.reset_runtime_state()


def _pesan(uid=1, isi="halo dunia", bot=False, kanal=100, lampiran=(), guild=1):
    return SimpleNamespace(
        guild=SimpleNamespace(id=guild) if guild else None,
        author=SimpleNamespace(id=uid, bot=bot, display_name=f"Member {uid}"),
        content=isi,
        attachments=[SimpleNamespace(filename=nama) for nama in lampiran],
        channel=SimpleNamespace(id=kanal),
    )


# --------------------------------------------------------------------------- #
# Pencatatan
# --------------------------------------------------------------------------- #

def test_catat_hapus_menyimpan_pesan():
    assert snipe.catat_hapus(_pesan(uid=7, isi="pesan rahasia")) is True
    entri = snipe.ambil_hapus(1, 100)
    assert len(entri) == 1
    assert entri[0]["user_id"] == 7
    assert entri[0]["isi"] == "pesan rahasia"
    assert entri[0]["nama"] == "Member 7"


def test_catat_hapus_melewati_bot_kosong_dan_dm():
    assert snipe.catat_hapus(_pesan(bot=True)) is False
    assert snipe.catat_hapus(_pesan(isi="   ")) is False
    assert snipe.catat_hapus(_pesan(guild=None)) is False
    assert snipe.ambil_hapus(1, 100) == []
    # hanya lampiran tanpa teks tetap dicatat
    assert snipe.catat_hapus(_pesan(isi="", lampiran=["bukti.png"])) is True
    assert snipe.ambil_hapus(1, 100)[0]["lampiran"] == ["bukti.png"]


def test_batas_lima_pesan_per_channel():
    for nomor in range(8):
        snipe.catat_hapus(_pesan(isi=f"pesan {nomor}"))
    entri = snipe.ambil_hapus(1, 100, 5)
    assert len(entri) == snipe.MAX_PER_CHANNEL
    assert entri[0]["isi"] == "pesan 7"  # terbaru dulu
    assert entri[-1]["isi"] == "pesan 3"


def test_ambil_menghormati_jumlah_dan_channel_lain():
    snipe.catat_hapus(_pesan(isi="satu"))
    snipe.catat_hapus(_pesan(isi="dua"))
    assert len(snipe.ambil_hapus(1, 100, 1)) == 1
    assert len(snipe.ambil_hapus(1, 100, 99)) == 2  # dibatasi
    assert snipe.ambil_hapus(1, 999) == []


def test_catat_edit_menyimpan_sebelum_sesudah():
    sebelum = _pesan(isi="harga 50rb")
    sesudah = _pesan(isi="harga 90rb")
    assert snipe.catat_edit(sebelum, sesudah) is True
    entri = snipe.ambil_edit(1, 100)
    assert entri[0]["isi"] == "harga 50rb"
    assert entri[0]["sesudah"] == "harga 90rb"
    # isi sama → tidak dicatat
    assert snipe.catat_edit(_pesan(isi="sama"), _pesan(isi="sama")) is False


def test_setelan_mematikan_pencatatan():
    snipe.set_config(1, enabled=False)
    assert snipe.catat_hapus(_pesan()) is False
    snipe.set_config(1, enabled=True, hapus=False)
    assert snipe.catat_hapus(_pesan()) is False
    snipe.set_config(1, hapus=True, edit=False)
    assert snipe.catat_hapus(_pesan()) is True
    assert snipe.catat_edit(_pesan(isi="a"), _pesan(isi="b")) is False

    # data lama tetap tidak ditampilkan ketika dimatikan
    snipe.set_config(1, enabled=False)
    assert snipe.ambil_hapus(1, 100) == []


def test_lupakan_channel_dan_statistik():
    snipe.catat_hapus(_pesan(kanal=100))
    snipe.catat_hapus(_pesan(kanal=200))
    snipe.catat_edit(_pesan(kanal=200, isi="x"), _pesan(kanal=200, isi="y"))
    data = snipe.statistik(1)
    assert data["entri_hapus"] == 2 and data["channel_hapus"] == 2
    assert data["entri_edit"] == 1 and data["channel_edit"] == 1
    assert data["aktif"] is True

    snipe.lupakan_channel(200)
    data = snipe.statistik(1)
    assert data["entri_hapus"] == 1 and data["entri_edit"] == 0


def test_membatasi_jumlah_channel(monkeypatch):
    monkeypatch.setattr(snipe, "MAX_CHANNEL", 3)
    for kanal in (1, 2, 3, 4, 5):
        snipe.catat_hapus(_pesan(kanal=kanal))
    assert len(snipe._hapus) <= 3
    assert snipe.cleanup_snipe_runtime() >= 0


def test_cleanup_membersihkan_channel_kosong():
    snipe._hapus[99] = []
    assert snipe.cleanup_snipe_runtime() >= 1
    assert 99 not in snipe._hapus


# --------------------------------------------------------------------------- #
# Command
# --------------------------------------------------------------------------- #

def test_group_snipe_terdaftar_khusus_staf():
    from main import bot as bot_main

    grup = bot_main.tree.get_command("snipe")
    assert grup is not None
    assert {cmd.name for cmd in grup.commands} == {"hapus", "edit", "atur"}
    assert grup.guild_only is True
    perms = grup.default_permissions
    assert perms is not None and perms.manage_messages is True


def test_embed_snipe_aman_untuk_pesan_panjang():
    from cogs.snipe_cog import _embed_edit, _embed_hapus

    snipe.catat_hapus(_pesan(isi="kata " * 400))
    entri = snipe.ambil_hapus(1, 100)
    embed = _embed_hapus(entri, "umum")
    assert embed.fields and len(embed.fields[0].value) <= 1024
    assert "memori" in (embed.description or "").lower()

    snipe.catat_edit(_pesan(isi="awal " * 300), _pesan(isi="akhir " * 300))
    embed = _embed_edit(snipe.ambil_edit(1, 100), "umum")
    assert "Sebelum" in embed.fields[0].value and "Sesudah" in embed.fields[0].value
    assert len(embed.fields[0].value) <= 1024


def test_event_listener_mencatat_snipe():
    akar = Path(__file__).resolve().parent.parent
    isi = (akar / "cogs" / "events_cog.py").read_text(encoding="utf-8")
    assert "snipe.catat_hapus(message)" in isi
    assert "snipe.catat_edit(before, after)" in isi
    assert "snipe.lupakan_channel" in isi


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def test_panel_snipe_menempel_di_halaman_moderasi():
    assert web_dashboard.ANCHOR_HALAMAN["p-snipe"] == "moderasi"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["snipe"] == "moderasi"
    assert dashboard_uji.ANCHOR_UJI["snipe"] == "p-snipe"
    halaman = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="moderasi",
        snipe_block=dashboard_snipe.render_snipe_block(SimpleNamespace(), 1, "tok"),
    )
    assert 'id="p-snipe"' in halaman and "snipe-setelan" in halaman


def test_panel_snipe_isi_status():
    snipe.catat_hapus(_pesan())
    html = dashboard_snipe.render_snipe_block(SimpleNamespace(), 1, "tok")
    assert "Snipe" in html and "memori" in html
    assert "snipe-setelan" in html
    assert "aktif" in html


@pytest.mark.asyncio
async def test_aksi_snipe_setelan():
    ok, pesan = await dashboard_snipe.aksi_snipe(
        1, "snipe-setelan", {"enabled": "0", "hapus": "1", "edit": "0"}
    )
    assert ok and "nonaktif" in pesan
    cfg = snipe.peek_config(1)
    assert cfg == {"enabled": False, "hapus": True, "edit": False}

    ok, pesan = await dashboard_snipe.aksi_snipe(1, "snipe-setelan", {})
    assert ok and snipe.peek_config(1)["enabled"] is True

    ok, pesan = await dashboard_snipe.aksi_snipe(1, "snipe-entah", {})
    assert ok is False and "tidak dikenal" in pesan


def test_uji_snipe_simulasi_bersih():
    ok, pesan = dashboard_uji._uji_snipe(1)
    assert ok is True and "Simulasi" in pesan
    # data simulasi dibersihkan: tidak ada entri tersisa
    assert snipe.statistik(1)["entri_hapus"] == 0
    assert snipe._hapus == {}

    snipe.set_config(1, enabled=False)
    ok, pesan = dashboard_uji._uji_snipe(1)
    assert ok is False and "dimatikan" in pesan


def test_uji_snipe_muncul_di_registry():
    kunci = [item["kunci"] for item in dashboard_uji.UJI]
    assert kunci.count("snipe") == 1
    entri = next(item for item in dashboard_uji.UJI if item["kunci"] == "snipe")
    assert entri["emoji"] == "🔎" and entri["grup"] == "Moderasi"
