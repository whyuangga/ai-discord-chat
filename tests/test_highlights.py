"""Tes Paket C#3 — highlight kata kunci (`/pantau` → DM).

Mencakup pencocokan batas kata, daftar abaikan, jeda anti-banjir, cuplikan, batas
jumlah pelanggan, simpan/muat JSON, pengiriman DM, command `/pantau`, panel dashboard,
dan penguji simulasi (tidak mengirim DM).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import achievements  # noqa: F401  (pastikan modul lain tetap bisa diimpor)
import dashboard_highlights
import dashboard_uji
import highlights
import web_dashboard


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    highlights.reset_runtime_state()
    highlights._terakhir.clear() if hasattr(highlights, "_terakhir") else None
    monkeypatch.setattr(highlights, "HIGHLIGHTS_FILE", tmp_path / "highlights.json")
    yield
    highlights.reset_runtime_state()


# --------------------------------------------------------------------------- #
# Kata kunci
# --------------------------------------------------------------------------- #

def test_normalisasi_kata():
    assert highlights.normalisasi("  Open   ORDER!! ") == "open order"
    assert highlights.normalisasi("Harga?") == "harga"
    assert highlights.normalisasi(None) == ""


def test_tambah_hapus_dan_batas_kata():
    ok, pesan = highlights.tambah_kata(1, 10, "Open Order")
    assert ok and "open order" in pesan
    assert highlights.daftar_kata(1, 10) == ["open order"]

    ok, pesan = highlights.tambah_kata(1, 10, "open order")
    assert ok is False and "sudah ada" in pesan
    assert highlights.tambah_kata(1, 10, "   ")[0] is False
    assert highlights.tambah_kata(1, 10, "x" * 41)[0] is False

    for i in range(highlights.MAX_KATA_PER_MEMBER - 1):
        assert highlights.tambah_kata(1, 10, f"kata{i}")[0] is True
    ok, pesan = highlights.tambah_kata(1, 10, "kelebihan")
    assert ok is False and str(highlights.MAX_KATA_PER_MEMBER) in pesan

    assert highlights.hapus_kata(1, 10, "kata0")[0] is True
    assert "kata0" not in highlights.daftar_kata(1, 10)
    assert highlights.hapus_kata(1, 10, "tidak-ada")[0] is False


def test_abaikan_channel_dan_kata():
    ok, pesan = highlights.tambah_abaikan(1, 20, channel_id=555)
    assert ok and "<#555>" in pesan
    assert highlights.tambah_abaikan(1, 20, channel_id=555)[0] is False
    assert highlights.tambah_abaikan(1, 20, kata="spam")[0] is True
    assert highlights.tambah_abaikan(1, 20, kata="spam")[0] is False
    assert highlights.tambah_abaikan(1, 20)[0] is False

    # kata abaikan tidak boleh sekaligus dipantau, dan sebaliknya
    highlights.tambah_kata(1, 21, "promo")
    assert highlights.tambah_abaikan(1, 21, kata="promo")[0] is False
    highlights.tambah_abaikan(1, 21, kata="diskon")
    assert highlights.tambah_kata(1, 21, "diskon")[0] is False

    assert highlights.bersihkan(1, 20) is True
    assert highlights.bersihkan(1, 20) is False
    assert highlights.daftar_kata(1, 20) == []


# --------------------------------------------------------------------------- #
# Pencocokan
# --------------------------------------------------------------------------- #

def test_cocok_batas_kata_dan_kapital():
    highlights.tambah_kata(1, 1, "bot")
    assert highlights.cocok(1, "bot itu keren")[0]["user_id"] == 1
    assert highlights.cocok(1, "BOT!")[0]["user_id"] == 1
    assert highlights.cocok(1, "robot baru") == []
    assert highlights.cocok(1, "botak") == []
    assert highlights.cocok(1, "a") == []  # terlalu pendek


def test_cocok_frasa_dan_satu_dm_per_pesan():
    highlights.tambah_kata(1, 1, "open order")
    highlights.tambah_kata(1, 1, "open")
    hasil = highlights.cocok(1, "siap open order hari ini?")
    assert len(hasil) == 1  # satu DM walau dua kata cocok
    assert hasil[0]["kata"] in ("open order", "open")


def test_cocok_menghormati_abaikan():
    highlights.set_config(1, abaikan_channel=[777])
    highlights.tambah_kata(1, 1, "promo")
    assert highlights.cocok(1, "promo besar", channel_id=777) == []
    assert highlights.cocok(1, "promo besar", channel_id=888)

    highlights.tambah_abaikan(1, 1, channel_id=999)
    assert highlights.cocok(1, "promo besar", channel_id=999) == []

    # kata abaikan milik siapa pun mematikan highlight sedunia
    highlights.tambah_kata(2, 2, "promo")
    highlights.tambah_abaikan(1, 3, kata="promo")
    assert highlights.cocok(1, "promo besar") == []


def test_cocok_dimatikan_dan_jeda_per_kata():
    highlights.tambah_kata(1, 1, "promo")
    assert highlights.cocok(1, "promo", sekarang=1000)
    highlights.catat_terkirim(1, 1, "promo", sekarang=1000)
    assert highlights.cocok(1, "promo", sekarang=1001) == []  # masih jeda
    assert highlights.cocok(1, "promo", sekarang=1000 + highlights.JEDA_SAMA_KATA_DETIK + 1)

    highlights.set_config(1, enabled=False)
    assert highlights.cocok(1, "promo", sekarang=10**9) == []


def test_batas_dm_per_menit():
    highlights.tambah_kata(1, 1, "promo")
    highlights.set_config(1, max_per_menit=2)
    for detik in (1, 2):
        assert highlights.boleh_kirim(1, 1, sekarang=detik)
        highlights.catat_terkirim(1, 1, f"promo{detik}", sekarang=detik)
    assert highlights.boleh_kirim(1, 1, sekarang=3) is False
    assert highlights.boleh_kirim(1, 1, sekarang=200) is True  # jendela bergeser


def test_cuplikan_memotong_di_sekitar_kata():
    teks = "a" * 500 + " kunci " + "b" * 500
    hasil = highlights.cuplikan(teks, "kunci")
    assert "kunci" in hasil and len(hasil) <= highlights.PANJANG_CUPLIKAN + 4
    assert hasil.startswith("…") and hasil.endswith("…")
    assert highlights.cuplikan("pendek", "pendek") == "pendek"


# --------------------------------------------------------------------------- #
# Statistik & batas memori
# --------------------------------------------------------------------------- #

def test_statistik_dan_daftar_pelanggan():
    highlights.tambah_kata(1, 1, "promo")
    highlights.tambah_kata(1, 1, "diskon")
    highlights.tambah_kata(1, 2, "promo")
    highlights.catat_terkirim(1, 2, "promo")
    data = highlights.statistik(1)
    assert data["pelanggan"] == 2 and data["total_kata"] == 3 and data["hit"] == 1
    assert data["teratas"][0] == ("promo", 2)
    assert highlights.daftar_pelanggan(1)[0]["user_id"] == 2  # hit terbanyak dulu
    assert highlights.statistik(99)["pelanggan"] == 0


def test_batas_pelanggan_per_server(monkeypatch):
    monkeypatch.setattr(highlights, "MAX_MEMBER_PER_GUILD", 3)
    for uid in (1, 2, 3):
        highlights.tambah_kata(1, uid, f"kata{uid}")
        highlights.hl_members[1][uid]["diperbarui"] = float(uid)
    highlights.tambah_kata(1, 4, "kata4")
    assert len(highlights.hl_members[1]) == 3
    assert 4 in highlights.hl_members[1] and 1 not in highlights.hl_members[1]


# --------------------------------------------------------------------------- #
# Simpan / muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat_roundtrip(tmp_path):
    highlights.set_config(1, enabled=True, abaikan_channel=[5], max_per_menit=3)
    highlights.tambah_kata(1, 1, "promo")
    highlights.tambah_abaikan(1, 1, kata="spam")
    await highlights.save_highlights_to_disk()

    mentah = json.loads((tmp_path / "highlights.json").read_text(encoding="utf-8"))
    isi = mentah["guilds"]["1"]
    assert isi["config"]["abaikan_channel"] == [5]
    assert isi["members"]["1"]["keywords"] == ["promo"]
    assert "isi" not in json.dumps(mentah)  # tidak menyimpan isi pesan

    highlights.reset_runtime_state()
    server, pelanggan = highlights.load_highlights_from_disk()
    assert (server, pelanggan) == (1, 1)
    assert highlights.daftar_kata(1, 1) == ["promo"]
    assert highlights.peek_config(1)["max_per_menit"] == 3


@pytest.mark.asyncio
async def test_muat_data_rusak(tmp_path, monkeypatch):
    berkas = tmp_path / "highlights.json"
    berkas.write_text("{rusak", encoding="utf-8")
    assert highlights.load_highlights_from_disk() == (0, 0)
    berkas.write_text(json.dumps({"guilds": {"x": 1, "2": "bukan-dict"}}), encoding="utf-8")
    assert highlights.load_highlights_from_disk() == (0, 0)


def test_cleanup_membuang_server_kosong():
    highlights.set_config(5, enabled=False)
    highlights.tambah_kata(6, 1, "promo")
    assert highlights.cleanup_highlights_runtime() >= 1
    assert 5 not in highlights.hl_config and 6 in highlights.hl_members


# --------------------------------------------------------------------------- #
# Pengiriman DM
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_kirim_highlight_mengirim_dm(monkeypatch):
    from cogs.highlights_cog import kirim_highlight

    highlights.tambah_kata(1, 2, "promo")
    dikirim = []

    class _Target:
        id = 2

        async def send(self, **kwargs):
            dikirim.append(kwargs.get("embed"))

    pembuat = SimpleNamespace(id=1, bot=False)
    pesan = SimpleNamespace(
        guild=SimpleNamespace(id=1, name="Server", get_member=lambda uid: _Target() if uid == 2 else None),
        author=pembuat,
        content="ada promo besar malam ini",
        channel=SimpleNamespace(id=90, mention="#umum"),
        jump_url="https://discord.com/x",
    )
    monkeypatch.setattr(highlights, "save_highlights_to_disk", _async_noop)
    assert await kirim_highlight(SimpleNamespace(), pesan) == 1
    assert dikirim and "promo" in (dikirim[0].title or "")
    assert dikirim[0].url == "https://discord.com/x"


@pytest.mark.asyncio
async def test_kirim_highlight_melewati_kasus_tidak_penting(monkeypatch):
    from cogs.highlights_cog import kirim_highlight

    highlights.tambah_kata(1, 2, "promo")
    monkeypatch.setattr(highlights, "save_highlights_to_disk", _async_noop)

    def _pesan(author_id=1, bot=False, isi="ada promo"):
        return SimpleNamespace(
            guild=SimpleNamespace(id=1, name="S", get_member=lambda uid: None),
            author=SimpleNamespace(id=author_id, bot=bot),
            content=isi,
            channel=SimpleNamespace(id=90, mention="#umum"),
            jump_url="",
        )

    assert await kirim_highlight(SimpleNamespace(), _pesan(bot=True)) == 0  # penulis bot
    assert await kirim_highlight(SimpleNamespace(), _pesan(isi="")) == 0  # kosong
    assert await kirim_highlight(SimpleNamespace(), SimpleNamespace(guild=None)) == 0
    # penulis sendiri tidak perlu dikirimi DM
    assert await kirim_highlight(SimpleNamespace(), _pesan(author_id=2)) == 0
    # target tidak ada di cache → dilewati
    assert await kirim_highlight(SimpleNamespace(), _pesan()) == 0


@pytest.mark.asyncio
async def test_kirim_highlight_menghormati_dm_tertutup(monkeypatch):
    import discord

    from cogs.highlights_cog import kirim_highlight

    highlights.tambah_kata(1, 2, "promo")
    monkeypatch.setattr(highlights, "save_highlights_to_disk", _async_noop)

    class _Target:
        id = 2

        async def send(self, **kwargs):
            raise discord.Forbidden(SimpleNamespace(status=403, reason=""), "dm closed")

    pesan = SimpleNamespace(
        guild=SimpleNamespace(id=1, name="S", get_member=lambda uid: _Target()),
        author=SimpleNamespace(id=1, bot=False),
        content="promo!",
        channel=SimpleNamespace(id=90, mention="#umum"),
        jump_url="",
    )
    assert await kirim_highlight(SimpleNamespace(), pesan) == 0


async def _async_noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_maybe_highlight_throttle_per_detik(monkeypatch):
    from cogs import highlights_cog

    highlights_cog._terakhir.clear()
    panggilan = []

    async def _palsu(bot, pesan):
        panggilan.append(pesan)
        return 1

    monkeypatch.setattr(highlights_cog, "kirim_highlight", _palsu)
    pesan = SimpleNamespace(guild=SimpleNamespace(id=5))
    assert await highlights_cog.maybe_highlight(SimpleNamespace(), pesan) == 1
    assert await highlights_cog.maybe_highlight(SimpleNamespace(), pesan) == 0  # ter-throttle
    assert await highlights_cog.maybe_highlight(SimpleNamespace(), SimpleNamespace(guild=None)) == 0


# --------------------------------------------------------------------------- #
# Command /pantau
# --------------------------------------------------------------------------- #

def test_group_pantau_terdaftar():
    from main import bot as bot_main

    grup = bot_main.tree.get_command("pantau")
    assert grup is not None and grup.guild_only is True
    assert {cmd.name for cmd in grup.commands} == {
        "tambah", "hapus", "daftar", "abaikan", "bersihkan", "atur",
    }


def test_atur_hanya_admin():
    from cogs.highlights_cog import _is_admin

    def _i(admin, manage):
        return SimpleNamespace(
            user=SimpleNamespace(
                guild_permissions=SimpleNamespace(administrator=admin, manage_guild=manage)
            )
        )

    assert _is_admin(_i(True, False)) and _is_admin(_i(False, True))
    assert not _is_admin(_i(False, False))


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def test_panel_highlight_menempel_di_halaman_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-pantau"] == "interaksi"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["pantau"] == "interaksi"
    assert dashboard_uji.ANCHOR_UJI["pantau"] == "p-pantau"
    html = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="interaksi",
        pantau_block=dashboard_highlights.render_highlights_block(SimpleNamespace(), 1, "tok"),
    )
    assert 'id="p-pantau"' in html and "pantau-setelan" in html


def test_panel_highlight_render_isinya():
    highlights.tambah_kata(1, 7, "promo")
    highlights.tambah_kata(1, 7, "diskon")
    highlights.catat_terkirim(1, 7, "promo")
    html = dashboard_highlights.render_highlights_block(SimpleNamespace(), 1, "tok")
    assert "Highlight kata kunci" in html
    assert "pantau-setelan" in html and "pantau-hapus:7" in html
    assert "promo" in html and "diskon" in html
    kosong = dashboard_highlights.render_highlights_block(SimpleNamespace(), 42, "tok")
    assert "Belum ada member" in kosong


@pytest.mark.asyncio
async def test_aksi_panel_highlight():
    ok, pesan = await dashboard_highlights.aksi_highlights(
        1, "pantau-setelan", {"enabled": "0", "max_per_menit": "2", "abaikan_channel": "11 12,13"}
    )
    assert ok and "nonaktif" in pesan
    assert highlights.peek_config(1)["max_per_menit"] == 2
    assert highlights.peek_config(1)["abaikan_channel"] == [11, 12, 13]

    highlights.tambah_kata(1, 7, "promo")
    ok, pesan = await dashboard_highlights.aksi_highlights(1, "pantau-hapus:7", {})
    assert ok and highlights.daftar_kata(1, 7) == []
    ok, pesan = await dashboard_highlights.aksi_highlights(1, "pantau-hapus:999", {})
    assert ok is False
    ok, _ = await dashboard_highlights.aksi_highlights(1, "pantau-ngawur", {})
    assert ok is False


def test_uji_pantau_simulasi_tanpa_dm():
    highlights.set_config(1, enabled=False)
    ok, pesan = dashboard_uji._uji_pantau(1)
    assert ok is False and "dimatikan" in pesan

    highlights.set_config(1, enabled=True)
    ok, pesan = dashboard_uji._uji_pantau(1)
    assert ok is False and "Belum ada member" in pesan

    highlights.tambah_kata(1, 7, "promo")
    ok, pesan = dashboard_uji._uji_pantau(1)
    assert ok is True and "promo" in pesan and "Simulasi" in pesan
    # tidak ada DM tercatat setelah simulasi
    assert highlights.statistik(1)["hit"] == 0
