"""Uji identitas kustom lewat webhook (`webhook_identity.py`)."""

from __future__ import annotations

import pytest

import webhook_identity as wi


@pytest.fixture(autouse=True)
def _penyimpanan(tmp_path, monkeypatch):
    monkeypatch.setattr(wi, "DATA_DIR", tmp_path)
    monkeypatch.setattr(wi, "WEBHOOK_FILE", tmp_path / "webhooks.json")
    wi._cache.clear()
    yield
    wi._cache.clear()


class FakePerms:
    def __init__(self, manage_webhooks=True):
        self.manage_webhooks = manage_webhooks


class FakeUser:
    id = 1


class FakeGuild:
    id = 999

    def __init__(self, *, manage_webhooks=True, hooks=None):
        self.me = FakeUser()
        self.me.guild_permissions = FakePerms(manage_webhooks)
        self._hooks = hooks or []
        self.created: list[str] = []

    async def fetch_webhook(self, webhook_id):
        for hook in self._hooks:
            if hook.id == webhook_id:
                return hook
        import discord

        raise discord.NotFound(_FakeResponse(), "hilang")

    async def create_webhook(self, name, reason=None):
        hook = FakeWebhook(len(self._hooks) + 100, user=self.me)
        self._hooks.append(hook)
        self.created.append(name)
        return hook


class FakeWebhook:
    def __init__(self, webhook_id, *, user=None, owner=None, url=None):
        self.id = webhook_id
        self.user = user
        self.owner = owner
        self.url = url or f"https://discord.com/api/webhooks/{webhook_id}/token"
        self.terkirim: list[dict] = []
        self.deleted = False

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)

    async def delete(self, reason=None):
        self.deleted = True


class _FakeResponse:
    status = 404
    reason = "Not Found"


class FakeChannel:
    def __init__(self, guild=None, *, hooks=None, fail_create=False):
        self.id = 500
        self.guild = guild or FakeGuild(hooks=hooks)
        self._hooks = hooks if hooks is not None else self.guild._hooks
        self.fail_create = fail_create
        self.created: list[str] = []

    async def webhooks(self):
        return list(self._hooks)

    async def create_webhook(self, name, reason=None):
        if self.fail_create:
            import discord

            raise discord.Forbidden(_FakeResponse(), "tidak boleh")
        hook = FakeWebhook(700, user=self.guild.me)
        self._hooks.append(hook)
        self.guild._hooks.append(hook)
        self.created.append(name)
        return hook


# ------------------------------------------------------------------------------
# VALIDASI & PAYLOAD
# ------------------------------------------------------------------------------
def test_validasi_nama_dan_avatar():
    assert wi.valid_name("📢 Pengumuman") == (True, "📢 Pengumuman")
    assert wi.valid_name("   ")[0] is False
    assert wi.valid_name("x" * (wi.MAX_NAME + 1))[0] is False
    assert wi.valid_avatar(None) == (True, None)
    assert wi.valid_avatar("https://contoh.test/a.png") == (True, "https://contoh.test/a.png")
    assert wi.valid_avatar("javascript:alert(1)")[0] is False


def test_payload_teks_biasa_menonaktifkan_mention_massal():
    kwargs = wi.build_message_kwargs(nama="Tim Event", isi="Halo semua", avatar="https://x/y.png")
    assert kwargs["username"] == "Tim Event"
    assert kwargs["content"] == "Halo semua"
    assert kwargs["avatar_url"] == "https://x/y.png"
    assert "embed" not in kwargs
    assert kwargs["allowed_mentions"].everyone is False


def test_payload_embed_bila_ada_judul_atau_footer():
    kwargs = wi.build_message_kwargs(nama="Server", judul="Judul", isi="Isi", footer="kaki")
    embed = kwargs["embed"]
    assert embed.title == "Judul" and embed.description == "Isi"
    assert embed.footer.text == "kaki"
    assert "content" not in kwargs

    # judul saja (tanpa isi) tetap sah: embed punya judul, tak perlu `content`
    kosong = wi.build_message_kwargs(nama="Server", judul="Judul", isi="")
    assert kosong["embed"].description is None
    assert "content" not in kosong

    # footer saja tanpa judul/isi → embed kosong, jadi pakai `content` pengisi
    pengisi = wi.build_message_kwargs(nama="Server", footer="kaki")
    assert pengisi["content"]


def test_payload_memotong_teks_panjang():
    kwargs = wi.build_message_kwargs(nama="x" * 100, isi="a" * 5000)
    assert len(kwargs["username"]) == wi.MAX_NAME
    assert len(kwargs["content"]) == wi.MAX_CONTENT


# ------------------------------------------------------------------------------
# CACHE
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cache_disimpan_dan_dimuat_ulang():
    channel = FakeChannel()
    wi.remember(channel, FakeWebhook(123))
    assert wi.cached_webhook_id(channel) == 123

    await wi.save_to_disk()
    wi._cache.clear()
    assert wi.load_from_disk() == 1
    assert wi.cached_webhook_id(channel) == 123

    wi.forget(channel)
    assert wi.cached_webhook_id(channel) == 0


def test_load_mengabaikan_entri_rusak(tmp_path):
    (tmp_path / "webhooks.json").write_text(
        '{"999:500": {"webhook_id": 5, "url": "https://x"}, '
        '"999:501": {"webhook_id": 0, "url": "https://y"}, '
        '"999:502": {"webhook_id": 7, "url": ""}}',
        encoding="utf-8",
    )
    assert wi.load_from_disk() == 1


# ------------------------------------------------------------------------------
# CARI / BUAT WEBHOOK
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_buat_webhook_baru_lalu_dipakai_ulang():
    channel = FakeChannel()
    hook, galat = await wi.ensure_webhook(channel)
    assert galat == "" and hook is not None
    assert channel.created == [wi.DEFAULT_WEBHOOK_NAME]
    assert wi.cached_webhook_id(channel) == hook.id

    lagi, galat2 = await wi.ensure_webhook(channel)
    assert galat2 == "" and lagi is hook
    assert channel.created == [wi.DEFAULT_WEBHOOK_NAME]  # tidak membuat dua kali


@pytest.mark.asyncio
async def test_webhook_lama_hilang_lalu_dibuat_ulang():
    channel = FakeChannel()
    wi._cache[wi._key(channel)] = {"webhook_id": 999, "url": "https://discord.com/api/webhooks/999/t"}

    hook, galat = await wi.ensure_webhook(channel)
    assert galat == "" and hook.id == 700
    assert wi.cached_webhook_id(channel) == 700


@pytest.mark.asyncio
async def test_menemukan_webhook_milik_bot_yang_sudah_ada():
    guild = FakeGuild()
    hook = FakeWebhook(42, user=guild.me)
    channel = FakeChannel(guild, hooks=[hook])

    ditemukan, galat = await wi.ensure_webhook(channel)
    assert galat == "" and ditemukan is hook
    assert channel.created == []  # tidak membuat webhook baru


@pytest.mark.asyncio
async def test_tanpa_izin_manage_webhooks():
    channel = FakeChannel(FakeGuild(manage_webhooks=False))
    hook, galat = await wi.ensure_webhook(channel)
    assert hook is None
    assert "Manage Webhooks" in galat


@pytest.mark.asyncio
async def test_gagal_membuat_webhook_diberi_pesan_jelas():
    channel = FakeChannel(fail_create=True)
    hook, galat = await wi.ensure_webhook(channel)
    assert hook is None
    assert "Manage Webhooks" in galat


# ------------------------------------------------------------------------------
# KIRIM & HAPUS
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kirim_sebagai_berhasil():
    channel = FakeChannel()
    berhasil, keterangan = await wi.kirim_sebagai(
        channel, nama="📢 Pengumuman", isi="Rapat jam 8", judul="Rapat"
    )
    assert berhasil and keterangan == ""
    hook = channel.guild._hooks[0]
    assert hook.terkirim[0]["username"] == "📢 Pengumuman"
    assert hook.terkirim[0]["embed"].title == "Rapat"


@pytest.mark.asyncio
async def test_kirim_sebagai_menolak_input_tidak_valid():
    channel = FakeChannel()
    assert (await wi.kirim_sebagai(channel, nama=" ", isi="x"))[0] is False
    assert (await wi.kirim_sebagai(channel, nama="Nama", isi="x", avatar="ftp://x"))[0] is False
    assert wi.cached_webhook_id(channel) == 0  # tidak ada webhook yang dibuat


@pytest.mark.asyncio
async def test_hapus_webhook_membersihkan_cache():
    channel = FakeChannel()
    hook, _ = await wi.ensure_webhook(channel)
    berhasil, keterangan = await wi.hapus_webhook(channel)
    assert berhasil and keterangan == ""
    assert hook.deleted is True
    assert wi.cached_webhook_id(channel) == 0
