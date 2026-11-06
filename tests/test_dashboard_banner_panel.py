"""Uji ganti/hapus banner panel yang sudah terkirim dari dashboard."""

from __future__ import annotations

import io
import socket

import aiohttp

import dashboard_pesan as dp
import dashboard_unggah as du
import menu_builder
import web_dashboard

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


class _Lampiran:
    def __init__(self, url="https://cdn.discordapp.com/banner-baru.png"):
        self.url = url
        self.filename = "banner.png"


class _Message:
    def __init__(self):
        self.edits = []
        self.attachments = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        lampiran = kwargs.get("attachments")
        if lampiran:
            self.attachments = [_Lampiran(lampiran[0].filename and f"https://cdn/{lampiran[0].filename}")]
        elif lampiran == []:
            self.attachments = []


class _Channel:
    def __init__(self, cid=11):
        self.id = cid
        self.mention = f"<#{cid}>"
        self.guild = type("G", (), {"id": 1234, "name": "Server Uji"})()
        self.message = _Message()

    async def fetch_message(self, mid):
        return self.message

    async def send(self, **kwargs):
        return _Message()


class _Bot:
    guilds: list = []

    def __init__(self, ch=None):
        self.ch = ch or _Channel()
        self.views = []

    def get_guild(self, gid):
        return type("G", (), {"id": gid, "name": "Server Uji"})()

    def get_channel(self, cid):
        return self.ch if self.ch.id == int(cid) else None

    def add_view(self, view, message_id=None):
        self.views.append((view, message_id))


def _menu(**ubah):
    data = {
        "id": "m1",
        "guild_id": 1234,
        "title": "Pusat Bantuan",
        "description": "Pilih tombol",
        "buttons": [],
        "dropdowns": [],
        "channel_id": 11,
        "message_id": 99,
        "banner_url": "https://cdn.discordapp.com/lama.png",
    }
    data.update(ubah)
    return data


def _siap(tmp_path, monkeypatch, menu=None):
    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(menu_builder, "get_menu", lambda gid, ref: menu)
    monkeypatch.setattr(menu_builder, "save_menus_to_disk", lambda: _async_none())
    monkeypatch.setattr(menu_builder, "build_view", lambda m, **k: {"view": m.get("title"), **k})
    monkeypatch.setattr(menu_builder, "build_fallback_embed", lambda m: {"embed": m.get("title")})


async def _async_none():
    return None


def _berkas(nama="banner.png"):
    import discord

    return discord.File(io.BytesIO(PNG), filename=nama)


# ==============================================================================
# GANTI BANNER
# ==============================================================================
async def test_ganti_banner_menyunting_pesan_asli(tmp_path, monkeypatch):
    menu = _menu()
    _siap(tmp_path, monkeypatch, menu)
    bot = _Bot()
    berkas = _berkas()

    ok, pesan = await dp.ganti_banner_panel(bot, 1234, "m1", banner=berkas)

    assert ok is True and "diganti" in pesan
    edit = bot.ch.message.edits[-1]
    assert edit["attachments"] == [berkas]
    assert edit["view"]["banner_override"] == "attachment://banner.png"
    # URL banner baru ikut disimpan untuk kirim ulang/dokumentasi
    assert menu["banner_url"].startswith("https://cdn/banner.png")
    assert bot.views and bot.views[-1][1] == 99


async def test_hapus_banner_mengosongkan_lampiran(tmp_path, monkeypatch):
    menu = _menu()
    _siap(tmp_path, monkeypatch, menu)
    bot = _Bot()

    ok, pesan = await dp.ganti_banner_panel(bot, 1234, "m1", banner=None)

    assert ok is True and "dihapus" in pesan
    edit = bot.ch.message.edits[-1]
    assert edit["attachments"] == []
    assert edit["view"]["banner_override"] == ""
    assert menu["banner_url"] is None


async def test_ganti_banner_panel_tidak_ditemukan(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch, None)
    ok, pesan = await dp.ganti_banner_panel(_Bot(), 1234, "tidak-ada", banner=_berkas())
    assert ok is False and "Panel tidak ditemukan" in pesan


async def test_ganti_banner_panel_belum_terkirim(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch, _menu(message_id=None))
    ok, pesan = await dp.ganti_banner_panel(_Bot(), 1234, "m1", banner=_berkas())
    assert ok is False and "/menu kirim" in pesan


async def test_ganti_banner_channel_hilang(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch, _menu())
    ok, pesan = await dp.ganti_banner_panel(_Bot(), 1234, "m1", banner=_berkas())

    class _BotKosong(_Bot):
        def get_channel(self, cid):
            return None

        async def fetch_channel(self, cid):
            raise RuntimeError("hilang")

    ok, pesan = await dp.ganti_banner_panel(_BotKosong(), 1234, "m1", banner=_berkas())
    assert ok is False and "Channel panel tidak ditemukan" in pesan


async def test_ganti_banner_ditolak_discord_pakai_embed_klasik(tmp_path, monkeypatch):
    menu = _menu()
    _siap(tmp_path, monkeypatch, menu)
    bot = _Bot()
    berkas = _berkas()
    panggilan = {"n": 0}

    async def _edit(self, **kwargs):
        panggilan["n"] += 1
        if panggilan["n"] == 1:
            raise RuntimeError("komponen V2 ditolak")
        self.edits.append(kwargs)

    monkeypatch.setattr(_Message, "edit", _edit, raising=False)

    ok, pesan = await dp.ganti_banner_panel(bot, 1234, "m1", banner=berkas)
    assert ok is True
    edit = bot.ch.message.edits[-1]
    assert edit["view"] is None and edit["attachments"] == [berkas]
    assert edit["embed"]["embed"] == "Pusat Bantuan"


async def test_ganti_banner_gagal_total(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch, _menu())

    async def _edit(self, **kwargs):
        raise RuntimeError("selalu gagal")

    monkeypatch.setattr(_Message, "edit", _edit, raising=False)
    ok, pesan = await dp.ganti_banner_panel(_Bot(), 1234, "m1", banner=_berkas())
    assert ok is False and "menolak perubahan banner" in pesan


# ==============================================================================
# FORM DI HALAMAN
# ==============================================================================
def test_form_banner_hanya_untuk_panel_terkirim(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch, None)
    html = web_dashboard.render_dashboard_html(
        status={},
        usage={},
        levels={},
        konten_block=_blocks(
            {
                "panel": [
                    {"id": "m1", "judul": "Pusat", "ringkas": "2 tombol", "terkirim": True},
                    {"id": "m2", "judul": "Draf", "ringkas": "0 tombol", "terkirim": False},
                ]
            }
        ),
    )
    assert "banner.panel:m1" in html and "hapusbanner.panel:m1" in html
    assert "banner.panel:m2" not in html
    assert 'enctype="multipart/form-data"' in html


def _blocks(konten: dict) -> str:
    import dashboard_ui

    return dashboard_ui.render_konten_block(1234, konten, "tok")


# ==============================================================================
# HTTP: unggah → ganti banner panel
# ==============================================================================
async def test_http_ganti_dan_hapus_banner_panel(tmp_path, monkeypatch):
    menu = _menu()
    _siap(tmp_path, monkeypatch, menu)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "tok-panel")

    bot = _Bot()
    assert await web_dashboard.start_dashboard(bot) is True
    base = f"http://127.0.0.1:{port}"
    try:
        async with aiohttp.ClientSession() as session:
            # Tanpa berkas & tanpa banner tersimpan → pesan jelas
            form = aiohttp.FormData()
            form.add_field("token", "tok-panel")
            form.add_field("guild", "1234")
            form.add_field("action", "banner.panel:m1")
            async with session.post(f"{base}/api/konten", data=form) as resp:
                body = await resp.text()
                assert resp.status == 400 and "lebih dulu" in body

            # Unggah berkas baru sekaligus ganti banner
            form = aiohttp.FormData()
            form.add_field("token", "tok-panel")
            form.add_field("guild", "1234")
            form.add_field("action", "banner.panel:m1")
            form.add_field("banner", PNG, filename="banner.png", content_type="image/png")
            async with session.post(f"{base}/api/konten", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "diganti" in body
            assert bot.ch.message.edits[-1]["attachments"][0].filename.endswith(".png")
            assert du.jumlah(1234) == 1          # unggahan otomatis tersimpan

            # Pakai banner tersimpan (tanpa berkas baru)
            nama = du.daftar(1234)[0]["nama"]
            form = aiohttp.FormData()
            form.add_field("token", "tok-panel")
            form.add_field("guild", "1234")
            form.add_field("action", "banner.panel:m1")
            form.add_field("banner_tersimpan", nama)
            async with session.post(f"{base}/api/konten", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "diganti" in body
            assert bot.ch.message.edits[-1]["attachments"][0].filename == nama

            # Hapus banner
            form = aiohttp.FormData()
            form.add_field("token", "tok-panel")
            form.add_field("guild", "1234")
            form.add_field("action", "hapusbanner.panel:m1")
            async with session.post(f"{base}/api/konten", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "dihapus" in body
            assert bot.ch.message.edits[-1]["attachments"] == []
    finally:
        await web_dashboard.stop_dashboard()
