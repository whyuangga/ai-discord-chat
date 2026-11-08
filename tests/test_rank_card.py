"""Uji kartu rank PNG: data, perender, setelan dashboard, endpoint pratinjau, & command."""

from __future__ import annotations

import asyncio
import io
import time

import pytest

import dashboard_admin
import dashboard_ui
import dashboard_uji
import levels
import rank_card

GID = 4321


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan():
    levels.levels.clear()
    levels.level_guilds.clear()
    yield
    levels.levels.clear()
    levels.level_guilds.clear()


def _isi_level() -> None:
    """Tiga member dengan XP berbeda + satu prestise."""
    levels.set_level_config(GID, enabled=True)
    for uid, xp, prestise in ((501, 9000, 0), (502, 5000, 1), (503, 300, 0)):
        levels.levels[f"{GID}:{uid}"] = {
            "xp": xp,
            "level": levels.level_from_total_xp(xp),
            "messages": 120,
            "last_at": time.time(),
            "prestige": prestise,
            "voice_min_today": 45,
            "voice_day": time.strftime("%Y-%m-%d"),
        }


def _avatar() -> bytes:
    from PIL import Image

    gambar = Image.new("RGB", (128, 128), (180, 120, 60))
    buffer = io.BytesIO()
    gambar.save(buffer, "PNG")
    return buffer.getvalue()


# ==============================================================================
# MODEL
# ==============================================================================
def test_rank_position_dan_data_kartu():
    _isi_level()
    assert levels.rank_position(GID, 501) == (1, 3)
    assert levels.rank_position(GID, 503) == (3, 3)
    # Member tanpa XP tidak dipaksa masuk peringkat
    assert levels.rank_position(GID, 999) == (0, 3)
    assert levels.rank_position(999, 1) == (0, 0)

    data = rank_card.data_kartu(GID, 502, nama="Sari", guild_name="Server Uji")
    assert data["level"] >= 5 and data["posisi"] == 2 and data["peserta"] == 3
    assert data["prestige"] == 1 and data["nama"] == "Sari"
    assert data["needed"] >= 1 and 0 <= data["current"] <= data["needed"]
    assert len(data["warna"]) == 3
    baris = " ".join(rank_card.baris_data(data))
    assert "#2 / 3" in baris and "Prestise ×1" in baris


def test_hex_warna_dan_setelan_kartu():
    assert rank_card.hex_warna("#ff8a00") == "#FF8A00"
    assert rank_card.hex_warna("112233") == "#112233"
    assert rank_card.hex_warna("biru") == "" and rank_card.hex_warna("") == ""

    # Default: aktif & warna ikut tema server
    assert rank_card.kartu_aktif(GID) is True
    levels.set_level_config(GID, enabled=True, kartu_aktif=False)
    assert rank_card.kartu_aktif(GID) is False
    levels.set_level_config(GID, kartu_aktif=True, kartu_warna="#FF8A00")
    assert rank_card.warna_aksen(GID) == (255, 138, 0)
    # Warna tidak sah tidak pernah masuk config
    levels.set_level_config(GID, kartu_warna="bukan-hex")
    assert levels.peek_level_config(GID)["kartu_warna"] == ""


# ==============================================================================
# PERENDER
# ==============================================================================
def test_render_kartu_png_dengan_dan_tanpa_avatar():
    _isi_level()
    data = rank_card.data_kartu(GID, 502, nama="Sari", guild_name="Server Uji")

    with_avatar = asyncio.run(rank_card.render_kartu(data, avatar_bytes=_avatar()))
    assert with_avatar and with_avatar[:8] == b"\x89PNG\r\n\x1a\n"
    from PIL import Image

    gambar = Image.open(io.BytesIO(with_avatar))
    assert gambar.size == rank_card.KARTU_UKURAN
    assert len(with_avatar) > 3000

    # Tanpa avatar: tetap jadi (placeholder huruf awal), bukan error
    tanpa = asyncio.run(rank_card.render_kartu(data))
    assert tanpa and tanpa[:4] == b"\x89PNG"


def test_render_kartu_tetap_bisa_saat_dimatikan_dan_aman_saat_kosong():
    _isi_level()
    data = rank_card.data_kartu(GID, 501, nama="Budi")
    assert data["level_aktif"] is True and data["kartu_aktif"] is True

    # Kartu dimatikan: pratinjau dashboard tetap boleh dirender (supaya Admin bisa
    # melihat hasilnya dulu), tapi penegakan ada di command & tombol tes.
    levels.set_level_config(GID, kartu_aktif=False)
    data_mati = rank_card.data_kartu(GID, 501, nama="Budi")
    assert data_mati["kartu_aktif"] is False
    assert asyncio.run(rank_card.render_kartu(data_mati))[:4] == b"\x89PNG"
    # Data kosong tetap aman
    assert asyncio.run(rank_card.render_kartu({})) is None


def test_pesan_cadangan_tanpa_pillow():
    _isi_level()
    data = rank_card.data_kartu(GID, 501, nama="Budi")
    teks = rank_card.pesan_cadangan(data)
    assert "Level" in teks and "Peringkat" in teks


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_setelan_dashboard_kartu_rank_ada_di_grup_inti():
    kunci = {item["kunci"]: item for item in dashboard_admin.FITUR_LIST}
    assert "level.kartu" in kunci and "level.kartu_warna" in kunci
    assert kunci["level.kartu"]["jenis"] == "saklar"
    assert kunci["level.kartu_warna"]["jenis"] == "teks"

    grup_inti = [g for g in dashboard_admin.GRUP if g["kunci"] == "inti"][0]
    assert "level.kartu" in grup_inti["fitur"]
    assert "level.kartu_warna" in grup_inti["fitur"]

    ok, pesan = kunci["level.kartu_warna"]["simpan"](GID, "#22CC88")
    assert ok and "22CC88" in pesan
    assert levels.peek_level_config(GID)["kartu_warna"] == "#22CC88"
    ok, pesan = kunci["level.kartu_warna"]["simpan"](GID, "hijau")
    assert ok is False and "hex" in pesan
    ok, pesan = kunci["level.kartu_warna"]["simpan"](GID, "")
    assert ok and "dikosongkan" in pesan
    ok, pesan = kunci["level.kartu"]["simpan"](GID, "off")
    assert ok and rank_card.kartu_aktif(GID) is False


def test_blok_dashboard_menampilkan_pratinjau_dan_tombol_tes():
    _isi_level()

    class _Guild:
        id = GID
        owner_id = 501
        name = "Server Uji"

    class _Bot:
        def get_guild(self, gid):
            return _Guild() if int(gid) == GID else None

        def get_channel(self, cid):
            return None

    html = dashboard_ui.render_kartu_rank_block(_Bot(), GID, "tok")
    assert "/api/rank.png" in html
    assert "token=tok" in html and f"guild={GID}" in html
    assert "member=501" in html
    assert "unduh=1" in html
    assert "kartu-slot" in html          # slot unggahan latar (menu unggah fitur ini)
    assert "kartu.simpan:rank" in html
    assert 'action="/api/uji"' in html and "uji.kartu" in html
    assert "perender yang sama" in html

    # Saat dimatikan: ada penjelasan, bukan pratinjau menyesatkan
    levels.set_level_config(GID, kartu_aktif=False)
    mati = dashboard_ui.render_kartu_rank_block(_Bot(), GID, "tok")
    assert "dimatikan" in mati and "mati</span>" in mati


def test_registry_tes_kartu_menempel_di_halaman_inti():
    import web_dashboard

    assert dashboard_uji.ANCHOR_UJI["kartu"] == "p-rank"
    assert web_dashboard.halaman_dari_anchor("p-rank") == "inti"
    assert "kartu" in web_dashboard.UJI_HALAMAN["inti"]
    assert dashboard_uji.halaman_uji("kartu") == "di halaman **Inti, level, & ekonomi**"
    assert any(item["kunci"] == "kartu" for item in dashboard_uji.UJI)


def test_tes_kartu_menghasilkan_png():
    _isi_level()

    class _Member:
        id = 502
        bot = False
        display_name = "Sari"

        class display_avatar:
            # Tiru discord.py: `with_size()` mengembalikan objek Asset (bukan
            # coroutine) sehingga `.read()` di dalamnya bisa di-await.
            @staticmethod
            def with_size(_size):
                return _Member.display_avatar

            @staticmethod
            async def read():
                return _avatar()

    class _Guild:
        id = GID
        name = "Server Uji"
        owner_id = 502
        members = []

        def get_member(self, uid):
            return _Member() if int(uid) == 502 else None

    class _Bot:
        def get_guild(self, gid):
            return _Guild() if int(gid) == GID else None

    ok, pesan = asyncio.run(
        dashboard_uji.jalankan_uji(_Bot(), GID, "kartu", _Member(), "")
    )
    assert ok is True and "berhasil dirender" in pesan and "KB" in pesan
    assert "Tidak ada yang dikirim" in pesan

    # Dimatikan lewat dashboard → tes menolak dengan alasan jelas
    levels.set_level_config(GID, kartu_aktif=False)
    ok, pesan = asyncio.run(dashboard_uji.jalankan_uji(_Bot(), GID, "kartu", _Member(), ""))
    assert ok is False and "dimatikan" in pesan


# ==============================================================================
# COMMAND
# ==============================================================================
def test_command_level_kartu_terdaftar():
    from cogs.growth_cog import level_group

    kunci = {c.name: c for c in level_group.commands}
    assert "kartu" in kunci
    assert len(kunci["kartu"].description) <= 100
    assert {"member", "publik"} <= {p.name for p in kunci["kartu"].parameters}
