"""Tes panel musik: grid 5×3 gaya LunaBot + mini-player + rekomendasi + dashboard.

Menjaga tiga hal yang mudah rusak tanpa sengaja:

1. Panel Discord tetap **15 tombol dalam 3 baris** (batas keras Discord: 5/baris).
2. Dropdown rekomendasi memakai format LunaBot `channel • source • durasi` dan
   tidak dibuat bila daftar kosong (Discord menolak menu tanpa opsi).
3. Setelan musik bisa ditulis dari dashboard dan langsung berlaku ke pemutar.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from discord import ui

import dashboard_musik
import music
import views
import web_dashboard

GID = 123456789012345678
TOKEN = "tok"


# --------------------------------------------------------------------------- #
# Objek palsu
# --------------------------------------------------------------------------- #
class _Queue(list):
    mode = SimpleNamespace(name="normal")


def _track(judul="Lagu Asli", artis="Penyanyi", durasi=215_000, sumber="youtube"):
    return SimpleNamespace(
        title=judul,
        author=artis,
        length=durasi,
        source=sumber,
        uri="https://contoh/lagu",
        is_stream=False,
        artwork="",
        extras={"requester": "Budi"},
    )


class _Player(SimpleNamespace):
    def __init__(self, lagu=None):
        super().__init__(
            current=lagu or _track(),
            position=61_000,
            volume=75,
            paused=False,
            queue=_Queue(),
            playing=True,
            autoplay=SimpleNamespace(name="disabled"),
            channel=SimpleNamespace(id=1),
            guild=SimpleNamespace(id=GID),
        )


def _tombol(view):
    return [i for i in view.walk_children() if isinstance(i, ui.Button)]


def _baris(view):
    return [i for i in view.walk_children() if isinstance(i, ui.ActionRow)]


def _dropdown(view):
    return [i for i in view.walk_children() if isinstance(i, ui.Select)]


@pytest.fixture(autouse=True)
def _bersih(monkeypatch):
    music.music_guilds.clear()
    music._REKOMENDASI_CACHE.clear()
    monkeypatch.setattr(music, "get_player", lambda guild: None)
    yield
    music.music_guilds.clear()
    music._REKOMENDASI_CACHE.clear()


# --------------------------------------------------------------------------- #
# Panel Discord
# --------------------------------------------------------------------------- #
def test_panel_musik_grid_5x3_gaya_lunabot():
    view = views.build_music_panel_luna_view(_Player(), guild_id=GID, rekomendasi=[])
    tombol = _tombol(view)
    baris_tombol = [r for r in _baris(view) if all(isinstance(b, ui.Button) for b in r.children)]

    assert len(tombol) == 15
    assert len(baris_tombol) == 3
    assert all(len(r.children) == 5 for r in baris_tombol)
    # Urutan grid sama dengan MUSIC_PANEL_ORDER (5 kolom per baris)
    assert [b.custom_id for b in tombol] == views.MUSIC_PANEL_ORDER


def test_panel_musik_tombol_baru_terdaftar_persisten():
    view = views.MusicPlayerView()
    ids = {c.custom_id for c in view.children}
    for wajib in (
        "music:panel:seek_back",
        "music:panel:seek_fwd",
        "music:panel:fav",
        "music:panel:radio",
        "music:panel:filter",
        "music:panel:tutup",
    ):
        assert wajib in ids
    assert view.is_persistent() is True


def test_panel_musik_dropdown_rekomendasi_format_lunabot():
    rekomendasi = [
        _track("Lagu Mirip 1", "Penyanyi A", 120_000, "youtube"),
        _track("Lagu Mirip 2", "Penyanyi B", 185_000, "spotify"),
    ]
    view = views.build_music_panel_luna_view(_Player(), guild_id=GID, rekomendasi=rekomendasi)
    dropdown = _dropdown(view)

    assert len(dropdown) == 1
    assert dropdown[0].placeholder == "Select a suggested song"
    label = [o.label for o in dropdown[0].options]
    assert label == ["Lagu Mirip 1", "Lagu Mirip 2"]
    # deskripsi: `channel/artis • source • durasi`
    assert dropdown[0].options[0].description == "Penyanyi A • youtube • 2:00"
    assert dropdown[0].options[1].description == "Penyanyi B • spotify • 3:05"


def test_panel_musik_tanpa_rekomendasi_tidak_buat_dropdown_kosong():
    """Discord menolak menu tanpa opsi — panel harus tetap tampil tanpa dropdown."""
    view = views.build_music_panel_luna_view(_Player(), guild_id=GID, rekomendasi=[])
    assert _dropdown(view) == []
    assert len(_tombol(view)) == 15


def test_mini_player_berisi_judul_durasi_volume_dan_requester():
    teks = views.build_mini_player(_Player())
    assert "Lagu Asli" in teks
    assert "1:01 / 3:35" in teks
    assert "75%" in teks
    assert "Requested by **Budi**" in teks


def test_mini_player_saat_kosong():
    teks = views.build_mini_player(None)
    assert "Tidak ada lagu" in teks


def test_mini_player_lagu_live():
    lagu = _track("Siaran Langsung")
    lagu.is_stream = True
    teks = views.build_mini_player(_Player(lagu))
    assert "LIVE" in teks


# --------------------------------------------------------------------------- #
# Rekomendasi
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_rekomendasi_lagu_menyaring_duplikat_dan_stream(monkeypatch):
    hasil = [
        _track("Lagu Asli"),          # sama dengan yang diputar → dibuang
        _track("Lagu Mirip 1"),
        _track("Lagu Mirip 1"),       # duplikat judul → dibuang
        SimpleNamespace(title="Live", author="X", length=0, uri="https://x",
                        source="youtube", is_stream=True),  # stream → dibuang
        _track("Lagu Mirip 2"),
    ]

    async def _palsu(query):
        return hasil, None

    monkeypatch.setattr(music, "search_tracks", _palsu)
    rekomendasi = await music.rekomendasi_lagu(_track("Lagu Asli"))

    assert [t.title for t in rekomendasi] == ["Lagu Mirip 1", "Lagu Mirip 2"]


@pytest.mark.asyncio
async def test_rekomendasi_lagu_tidak_melempar_saat_node_mati(monkeypatch):
    async def _gagal(query):
        raise music.MusicUnavailable("node mati")

    monkeypatch.setattr(music, "search_tracks", _gagal)
    assert await music.rekomendasi_lagu(_track()) == []


@pytest.mark.asyncio
async def test_rekomendasi_panel_di_cache_dan_dibatasi_saat_gagal(monkeypatch):
    panggilan = []

    async def _palsu(query):
        panggilan.append(query)
        return [_track("Lagu Mirip 1")], None

    monkeypatch.setattr(music, "search_tracks", _palsu)
    player = _Player()

    pertama = await music.rekomendasi_panel(player, GID)
    kedua = await music.rekomendasi_panel(player, GID)
    assert [t.title for t in pertama] == ["Lagu Mirip 1"]
    assert pertama == kedua
    assert len(panggilan) == 1, "panel di-refresh tiap detik, pencarian harus di-cache"

    # Gagal → jangan spam node; hasil kosong dipertahankan selama cooldown
    async def _gagal(query):
        panggilan.append(query)
        raise music.MusicUnavailable("mati")

    monkeypatch.setattr(music, "search_tracks", _gagal)
    music._REKOMENDASI_CACHE.clear()
    assert await music.rekomendasi_panel(player, GID) == []
    assert await music.rekomendasi_panel(player, GID) == []
    assert len(panggilan) == 2, "kegagalan harus di-cache selama cooldown"


def test_kata_kunci_rekomendasi_membuang_topic():
    lagu = _track("Judul", "Penyanyi Hebat - Topic")
    assert music._kata_kunci_rekomendasi(lagu) == "Penyanyi Hebat"


def test_deskripsi_rekomendasi_tanpa_artis():
    lagu = _track("Judul", artis="", durasi=0)
    assert music.deskripsi_rekomendasi(lagu) == "youtube • 0:00"


# --------------------------------------------------------------------------- #
# Setelan per server
# --------------------------------------------------------------------------- #
def test_setelan_musik_loop_dan_batas_antrean():
    cfg = music.set_music_settings(GID, loop="semua", max_queue=120)
    assert cfg["loop"] == "semua"
    assert cfg["max_queue"] == 120

    # Nilai di luar batas dijepit, nilai sampah diabaikan
    music.set_music_settings(GID, loop="tidak-ada", max_queue=9_999)
    cfg = music.get_music_settings(GID)
    assert cfg["loop"] == "semua"
    assert cfg["max_queue"] == 500


def test_max_queue_untuk_memakai_setelan_server():
    player = _Player()
    music.set_music_settings(GID, max_queue=7)
    assert music.max_queue_untuk(player) == 7


# --------------------------------------------------------------------------- #
# Dashboard web
# --------------------------------------------------------------------------- #
def test_panel_musik_menempel_di_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-musik"] == "interaksi"


def test_panel_musik_render_lengkap():
    guild = SimpleNamespace(id=GID, roles=[])
    bot = SimpleNamespace(get_guild=lambda gid: guild)
    music.set_music_settings(GID, volume=80, filter_name="bassboost", loop="satu", max_queue=33)

    html = dashboard_musik.render_musik_block(bot, GID, TOKEN)

    assert 'class="subpanel" id="p-musik"' in html
    assert "musik-setelan" in html
    for medan in ("volume", "dj_role_id", "filter", "loop", "max_queue", "announce", "autoplay"):
        assert f'name="{medan}"' in html
    assert "80%" in html and "Bass Boost" in html
    assert "33" in html


def test_panel_musik_menampilkan_status_node():
    html = dashboard_musik.render_musik_block(None, GID, TOKEN)
    assert "Node Lavalink" in html or "belum dikonfigurasi" in html


@pytest.mark.asyncio
async def test_aksi_musik_menyimpan_dan_menerapkan_ke_player(monkeypatch):
    class _P:
        def __init__(self):
            self.queue = _Queue()
            self.volume_diterapkan = None

        async def set_volume(self, nilai):
            self.volume_diterapkan = nilai

    pemutar = _P()
    monkeypatch.setattr(music, "get_player", lambda guild: pemutar)
    bot = SimpleNamespace(get_guild=lambda gid: SimpleNamespace(id=GID))

    ok, pesan = await dashboard_musik.aksi_musik(
        bot, GID, "musik-setelan",
        {
            "volume": "90",
            "filter": "nightcore",
            "loop": "semua",
            "max_queue": "120",
            "announce": "0",
            "autoplay": "1",
            "dj_role_id": "9",
        },
    )

    assert ok is True and "90%" in pesan
    cfg = music.get_music_settings(GID)
    assert cfg["volume"] == 90
    assert cfg["filter"] == "nightcore"
    assert cfg["loop"] == "semua"
    assert cfg["max_queue"] == 120
    assert cfg["announce"] is False
    assert cfg["autoplay"] is True
    assert cfg["dj_role_id"] == 9
    assert pemutar.volume_diterapkan == 90


@pytest.mark.asyncio
async def test_aksi_musik_menolak_aksi_asing_dan_mengembalikan_none():
    assert await dashboard_musik.aksi_musik(None, GID, "musik-hapus", {}) == (
        False,
        "Aksi musik `musik-hapus` tidak dikenal.",
    )
    assert await dashboard_musik.aksi_musik(None, GID, "voice-setelan", {}) is None
