"""Uji target kirim panel & pengumuman ke thread / forum channel."""

from __future__ import annotations

import pytest

import engagement
import menu_builder as mb


@pytest.fixture(autouse=True)
def _bersihkan(monkeypatch):
    mb.menus.clear()
    engagement.announcements.clear()
    yield
    mb.menus.clear()
    engagement.announcements.clear()


class FakeMessage:
    def __init__(self, message_id=1000):
        self.id = message_id
        self.attachments: list = []


class FakeThreadObject:
    id = 4242


class FakeBanner:
    guild = None


class FakeChannel:
    """Channel teks / thread: punya `send`."""

    def __init__(self, channel_id=500, *, guild=None):
        self.id = channel_id
        self.guild = guild
        self.mention = f"<#{channel_id}>"
        self.terkirim: list = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return FakeMessage()


class FakeForum:
    """Forum channel: `send` tidak ada, hanya `create_thread`."""

    def __init__(self, channel_id=600, *, fail_v2=False):
        self.id = channel_id
        self.guild = None
        self.mention = f"<#{channel_id}>"
        self.fail_v2 = fail_v2
        self.posts: list = []

    async def create_thread(self, **kwargs):
        self.posts.append(kwargs)
        if "view" in kwargs and self.fail_v2:
            raise TypeError("komponen v2 ditolak")
        return type("ThreadWithMessage", (), {"thread": FakeThreadObject(), "message": FakeMessage(2000)})()


class FakeGuildObject:
    id = 77
    me = None


class FakeBot:
    def __init__(self, *, cached=None, fetched=None):
        self.cached = cached
        self.fetched = fetched
        self.views: list = []

    def get_guild(self, guild_id):
        return FakeGuildObject() if int(guild_id) == FakeGuildObject.id else None

    def get_channel(self, channel_id):
        channel = self.cached
        if channel is None:
            return None
        return channel if int(getattr(channel, "id", 0)) == int(channel_id) else None

    async def fetch_channel(self, channel_id):
        if self.fetched is None:
            import discord

            raise discord.NotFound(_FakeResponse(), "hilang")
        return self.fetched

    def add_view(self, view, message_id=None):
        self.views.append((view, message_id))


class _FakeResponse:
    status = 404
    reason = "Not Found"


def _panel() -> dict:
    menu = mb.create_menu(77, "Pusat Info", description="Semua tautan penting")
    mb.add_link_button(menu, "Support", "https://contoh.test")
    return menu


@pytest.mark.asyncio
async def test_panel_ke_thread_menyimpan_id_thread():
    menu = _panel()
    thread = FakeChannel(channel_id=808)
    bot = FakeBot()

    message = await mb.send_panel(bot, menu, thread)

    assert message is not None
    assert menu["channel_id"] == 808 and menu["message_id"] == message.id
    assert thread.terkirim and "view" in thread.terkirim[0]
    assert bot.views and bot.views[0][1] == message.id


@pytest.mark.asyncio
async def test_panel_ke_forum_membuat_post(monkeypatch):
    monkeypatch.setattr(mb, "is_forum_channel", lambda channel: True)
    menu = _panel()
    forum = FakeForum()
    bot = FakeBot()

    message = await mb.send_panel(bot, menu, forum)

    assert message is not None and message.id == 2000
    assert forum.posts[0]["name"] == "Pusat Info"
    assert menu["channel_id"] == FakeThreadObject.id
    assert menu["message_id"] == 2000


@pytest.mark.asyncio
async def test_panel_forum_jatuh_ke_embed_klasik(monkeypatch):
    monkeypatch.setattr(mb, "is_forum_channel", lambda channel: True)
    menu = _panel()
    forum = FakeForum(fail_v2=True)

    message = await mb.send_panel(FakeBot(), menu, forum)

    assert message is not None
    assert len(forum.posts) == 2
    assert "embed" in forum.posts[1] and "view" not in forum.posts[1]


@pytest.mark.asyncio
async def test_refresh_panel_memakai_fetch_bila_thread_tidak_di_cache():
    menu = _panel()
    menu["channel_id"] = 808
    menu["message_id"] = 1000
    thread = FakeChannel(channel_id=808)

    class PesanLama:
        id = 1000

        def __init__(self):
            self.diedit: list = []

        async def edit(self, **kwargs):
            self.diedit.append(kwargs)

    pesan = PesanLama()

    async def fetch_message(message_id):
        return pesan

    thread.fetch_message = fetch_message

    bot = FakeBot(cached=None, fetched=thread)
    assert await mb.refresh_panel(bot, menu) is True
    assert pesan.diedit and "view" in pesan.diedit[0]


# ------------------------------------------------------------------------------
# PENGUMUMAN: thread target
# ------------------------------------------------------------------------------
def _pengumuman(channel_id: int = 4242):
    spec = engagement.parse_announcement_schedule("08:00")
    status, cfg = engagement.add_announcement(
        88, channel_id, "Isi", spec, tz_name="Asia/Jakarta"
    )
    assert status == "ok"
    cfg["next_run_at"] = 0  # agar langsung dianggap jatuh tempo
    return cfg


@pytest.mark.asyncio
async def test_pengumuman_ke_thread_lewat_fetch_channel():
    cfg = _pengumuman()
    cfg["next_run_at"] = 1  # sudah lewat
    thread = FakeChannel(channel_id=4242)

    bot = FakeBot(cached=None, fetched=thread)
    terkirim = await engagement.run_announcement_check(bot)

    assert terkirim == 1
    assert thread.terkirim and "embed" in thread.terkirim[0]
    assert engagement.announcements[cfg["id"]]["last_sent_at"] > 0


@pytest.mark.asyncio
async def test_resolve_channel_memakai_cache_dulu():
    channel = FakeChannel()
    bot = FakeBot(cached=channel, fetched=None)
    assert await engagement.resolve_channel(bot, 500) is channel
    assert await engagement.resolve_channel(bot, 999) is None


@pytest.mark.asyncio
async def test_kirim_sekarang_ke_thread():
    cfg = _pengumuman()
    thread = FakeChannel(channel_id=4242)
    bot = FakeBot(cached=None, fetched=thread)

    status, _ = await engagement.send_announcement_now(bot, cfg["id"], guild_id=88)
    assert status == "ok"
    assert thread.terkirim


def test_perintah_pengumuman_menerima_thread():
    """`/pengumuman tambah` harus bisa menunjuk thread, bukan hanya channel teks."""
    import discord

    from cogs.engagement_cog import pengumuman_group

    cmd = next(c for c in pengumuman_group.commands if c.name == "tambah")
    param = next(p for p in cmd.parameters if p.name == "channel")

    # discord.py menerjemahkan union channel menjadi AppCommandChannel + channel_types
    pilihan = set(getattr(param, "channel_types", None) or ())
    assert discord.ChannelType.public_thread in pilihan
    assert discord.ChannelType.text in pilihan
