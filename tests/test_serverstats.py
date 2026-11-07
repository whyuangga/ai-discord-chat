"""Tes Paket D#6 — channel statistik: tiket terbuka & langganan notifikasi sosial."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import server_features as sf
import social_notify as sn
import tickets

GID = 123456789012345678


@pytest.fixture(autouse=True)
def _bersih():
    tickets.tickets.clear()
    sn.social_guilds.clear()
    yield
    tickets.tickets.clear()
    sn.social_guilds.clear()


def _guild(jumlah=10, bot=2, boost=3):
    anggota = [
        SimpleNamespace(id=100 + i, bot=(i < bot), roles=[])
        for i in range(jumlah)
    ]
    return SimpleNamespace(
        id=GID,
        name="Server Uji",
        members=anggota,
        member_count=jumlah,
        premium_subscription_count=boost,
        premium_tier=1,
        description=None,
        roles=[],
        emojis=[],
        stickers=[],
        channels=[],
        created_at=None,
        owner=None,
        verification_level=None,
        icon=None,
        approximate_presence_count=4,
        get_channel=lambda cid: None,
    )


# --------------------------------------------------------------------------- #
# Spesifikasi channel
# --------------------------------------------------------------------------- #

def test_spesifikasi_baru_terdaftar():
    kunci = [key for key, _, _ in sf.STATS_CHANNEL_SPECS]
    assert "tickets" in kunci and "social" in kunci
    emoji = sf.default_stats_emojis()
    assert emoji["tickets"] == "🎫" and emoji["social"] == "🔔"

    label = {key: label for key, _, label in sf.STATS_CHANNEL_SPECS}
    assert label["tickets"] == "Tiket Terbuka"
    assert label["social"] == "Langganan Sosial"


def test_nama_channel_dibatasi_discord():
    nama = sf._stats_channel_name("🎫", "Tiket Terbuka", "1.234")
    assert nama == "🎫 Tiket Terbuka: 1.234"
    assert len(sf._stats_channel_name("🎫", "Tiket" * 40, "9" * 40)) <= 100
    assert sf._stats_channel_name("", "Bot", "2") == "Bot: 2"


# --------------------------------------------------------------------------- #
# Hitungan
# --------------------------------------------------------------------------- #

def test_hitung_statistik_anggota():
    data = sf.hitung_statistik(_guild(), presence_count=7)
    assert data["members"] == 10
    assert data["bots"] == 2
    assert data["humans"] == 8
    assert data["online"] == 7
    assert data["boosts"] == 3
    assert data["tickets"] == 0 and data["social"] == 0


def test_hitung_statistik_tiket_dan_sosial():
    tickets.tickets[1001] = {"guild_id": GID, "status": "terbuka"}
    tickets.tickets[1002] = {"guild_id": GID, "status": "diklaim"}
    tickets.tickets[1003] = {"guild_id": GID, "status": "selesai"}
    tickets.tickets[1004] = {"guild_id": 999, "status": "terbuka"}

    sn.social_guilds[GID] = {
        "subs": [
            {"id": "a", "platform": "reddit", "target": "indonesia"},
            {"id": "b", "platform": "rss", "target": "https://contoh.com/f.xml"},
        ]
    }

    data = sf.hitung_statistik(_guild())
    assert tickets.count_open(GID) == 2
    assert data["tickets"] == 2
    assert data["social"] == 2


def test_hitung_statistik_aman_bila_modul_gagal(monkeypatch):
    import tickets as tiket_mod

    def meledak(_gid):
        raise RuntimeError("rusak")

    monkeypatch.setattr(tiket_mod, "count_open", meledak)
    data = sf.hitung_statistik(_guild())
    assert data["tickets"] == 0  # tidak boleh melempar ke watcher


# --------------------------------------------------------------------------- #
# Embed
# --------------------------------------------------------------------------- #

def test_embed_menampilkan_tiket_dan_sosial():
    tickets.tickets[1001] = {"guild_id": GID, "status": "terbuka"}
    sn.social_guilds[GID] = {"subs": [{"id": "a", "platform": "rss", "target": "https://x/f"}]}

    embed = sf.build_serverstats_embed(_guild(), presence_count=5)
    nama = [field.name for field in embed.fields]
    assert "📈 Aktivitas Fitur" in nama
    isi = "\n".join(field.value for field in embed.fields)
    assert "Tiket terbuka" in isi and "Langganan sosial" in isi
    assert all(len(field.value) <= 1024 for field in embed.fields)


# --------------------------------------------------------------------------- #
# Setelan emoji tetap konsisten
# --------------------------------------------------------------------------- #

def test_emoji_kustom_untuk_channel_baru():
    sf.set_serverstats_config(GID, enabled=True)
    sf.set_serverstats_emojis(GID, {"tickets": "🎟️", "social": "-"})
    emoji = sf.stats_emojis(GID)
    assert emoji["tickets"] == "🎟️"
    assert emoji["social"] == ""  # "-" = tanpa ikon
    sebelum = sf.stats_emojis(GID)["boosts"]
    sf.set_serverstats_emojis(GID, {"boosts": None})  # None = tidak diubah
    assert sf.stats_emojis(GID)["boosts"] == sebelum


def test_simpan_muat_spec_baru(tmp_path, monkeypatch):
    berkas = tmp_path / "server_features.json"
    berkas.write_text(
        json.dumps(
            {
                "serverstats": {
                    str(GID): {
                        "enabled": True,
                        "emojis": {"tickets": "🎟️", "tidak_dikenal": "x"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sf, "SERVER_FEATURES_FILE", berkas)
    sf.serverstats_guilds.clear()
    sf.load_server_features_from_disk()
    cfg = sf.serverstats_guilds[GID]
    assert cfg["emojis"]["tickets"] == "🎟️"
    assert "tidak_dikenal" not in cfg["emojis"]


# --------------------------------------------------------------------------- #
# Panel dashboard & aksi POST
# --------------------------------------------------------------------------- #

@pytest.fixture()
def simpan_off(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(sf, "save_server_features_to_disk", _noop)


def test_panel_statistik_merender_tujuh_baris():
    import dashboard_stats

    sf.serverstats_guilds.clear()
    sf.set_serverstats_config(GID, enabled=True)
    html = dashboard_stats.render_stats_block(None, GID, "tok")

    assert 'id="p-statistik"' in html
    assert html.count('action="/api/konten"') == 8  # 7 ikon + segarkan
    for label in ("Total Member", "Manusia", "Bot", "Online", "Boost",
                  "Tiket Terbuka", "Langganan Sosial"):
        assert label in html
    assert "nonaktif" not in html and "aktif" in html
    assert "stats-emoji:tickets" in html and "stats-segarkan" in html
    assert "statistik" in html.lower()


def test_panel_statistik_escape_emoji():
    import dashboard_stats

    sf.serverstats_guilds.clear()
    sf.set_serverstats_config(GID, enabled=True)
    sf.set_serverstats_emojis(GID, {"tickets": "<b>"})
    html = dashboard_stats.render_stats_block(None, GID, "tok")
    assert "&lt;b&gt;" in html
    assert 'value="&lt;b&gt;"' in html  # emoji jahat tidak pernah jadi tag


def test_aksi_stats_ganti_ikon(simpan_off):
    import asyncio

    import dashboard_stats

    sf.serverstats_guilds.clear()
    sf.set_serverstats_config(GID, enabled=True)

    ok, pesan = asyncio.run(
        dashboard_stats.aksi_stats(GID, "stats-emoji:tickets", {"nilai": "🎟️"})
    )
    assert ok and "tickets" in pesan
    assert sf.stats_emojis(GID)["tickets"] == "🎟️"

    ok, _ = asyncio.run(dashboard_stats.aksi_stats(GID, "stats-emoji:social", {"nilai": "-"}))
    assert ok and sf.stats_emojis(GID)["social"] == ""


def test_aksi_stats_menolak_kunci_asing_dan_nonaktif(simpan_off):
    import asyncio

    import dashboard_stats

    sf.serverstats_guilds.clear()
    ok, pesan = asyncio.run(dashboard_stats.aksi_stats(GID, "stats-emoji:tickets", {"nilai": "🎫"}))
    assert not ok and "aktif" in pesan

    sf.set_serverstats_config(GID, enabled=True)
    ok, pesan = asyncio.run(dashboard_stats.aksi_stats(GID, "stats-emoji:asing", {"nilai": "x"}))
    assert not ok and "tidak dikenal" in pesan

    ok, pesan = asyncio.run(dashboard_stats.aksi_stats(GID, "stats-lain", {}))
    assert not ok and "tidak dikenal" in pesan


def test_aksi_stats_segarkan_ulang(simpan_off):
    import asyncio

    import dashboard_stats

    sf.serverstats_guilds.clear()
    cfg = sf.set_serverstats_config(GID, enabled=True)
    cfg["last_update_at"] = 999.0

    ok, pesan = asyncio.run(dashboard_stats.aksi_stats(GID, "stats-segarkan", {}))
    assert ok and "diperbarui" in pesan
    assert sf.serverstats_guilds[GID]["last_update_at"] == 0.0


def test_halaman_konten_memuat_panel_statistik():
    import web_dashboard

    halaman = web_dashboard.HALAMAN_SLUG["konten"]
    assert "p-statistik" in halaman["panel"]
    assert web_dashboard.ANCHOR_HALAMAN["p-statistik"] == "konten"
    assert web_dashboard._anchor_konten("stats-emoji:tickets") == "p-statistik"


def test_uji_statistik_simulasi_tanpa_ubah_channel():
    import asyncio

    import dashboard_stats
    import dashboard_uji

    tickets.tickets[1001] = {"guild_id": GID, "status": "terbuka"}
    sn.social_guilds[GID] = {"subs": [{"id": "a", "platform": "rss", "target": "https://x/f"}]}
    sf.serverstats_guilds.clear()
    sf.set_serverstats_config(GID, enabled=True)

    bot_stub = SimpleNamespace(get_guild=lambda gid: _guild())
    ok, pesan = asyncio.run(dashboard_uji.jalankan_uji(bot_stub, GID, "statistik"))
    assert ok
    assert "Tiket Terbuka" in pesan and "Langganan Sosial" in pesan
    assert "aktif" in pesan and "tidak ada channel" in pesan
    assert dashboard_uji.ANCHOR_UJI["statistik"] == "p-statistik"
    assert "Konten & interaksi" in dashboard_uji.halaman_uji("statistik")

    # Angka & ikon tidak berubah karena tes hanya membaca.
    sebelum = dashboard_stats.collect(bot_stub, GID)
    nilai = {b["kunci"]: b["nilai"] for b in sebelum["baris"]}
    assert nilai["tickets"] == "1" and nilai["social"] == "1"
