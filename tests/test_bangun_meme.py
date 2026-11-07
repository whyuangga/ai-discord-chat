"""Tes Paket E#1 (`/bangun`) & E#4 (`/meme`)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import server_builder as sb
from cogs import bangun_cog as bc
from cogs import meme_cog as mc

GID = 777888999000111222


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    sb.reset_state()
    monkeypatch.setattr(sb, "BUILDER_FILE", tmp_path / "server_builder.json")

    async def _tanpa_disk():
        return None

    monkeypatch.setattr(sb, "save_to_disk", _tanpa_disk)
    yield
    sb.reset_state()


# --------------------------------------------------------------------------- #
# Command & hak akses
# --------------------------------------------------------------------------- #

def test_group_bangun_punya_lima_subcommand():
    nama = {cmd.name for cmd in bc.bangun_group.commands}
    assert nama == {"tema", "rancang", "terapkan", "riwayat", "bongkar"}
    assert bc.bangun_group.name == "bangun"
    assert mc.meme_cmd.name == "meme"


def test_admin_butuh_izin_kelola_channel():
    def _interaksi(**izin):
        perms = SimpleNamespace(
            administrator=izin.get("administrator", False),
            manage_channels=izin.get("manage_channels", False),
            manage_guild=izin.get("manage_guild", False),
        )
        return SimpleNamespace(user=SimpleNamespace(guild_permissions=perms))

    assert bc._admin(_interaksi(administrator=True))
    assert bc._admin(_interaksi(manage_channels=True))
    assert bc._admin(_interaksi(manage_guild=True))
    assert not bc._admin(_interaksi())
    assert not bc._admin(SimpleNamespace(user=SimpleNamespace(guild_permissions=None)))


def test_embed_pratinjau_menyebut_sumber():
    snap = sb.tema_ke_snapshot("gaming", nama_server="Server A")
    embed = bc._embed_pratinjau(snap, "tema:gaming")
    assert "Pratinjau" in embed.title
    assert "tema `gaming`" in embed.fields[0].value
    assert all(len(f.value) <= 1024 for f in embed.fields)
    assert len(embed.description) <= 4096

    embed_ai = bc._embed_pratinjau(snap, "ai")
    assert "Gemini" in embed_ai.fields[0].value


# --------------------------------------------------------------------------- #
# Alur siapkan → konfirmasi
# --------------------------------------------------------------------------- #

class _Response:
    def __init__(self):
        self.sent = []

    async def send_message(self, *args, **kwargs):
        self.sent.append((args, kwargs))

    async def defer(self, *args, **kwargs):
        return None


def _interaksi(gid=GID, admin=True):
    perms = SimpleNamespace(administrator=admin, manage_channels=admin, manage_guild=admin)
    return SimpleNamespace(
        guild=SimpleNamespace(id=gid, name="Server Uji"),
        guild_id=gid,
        user=SimpleNamespace(id=42, guild_permissions=perms),
        response=_Response(),
    )


@pytest.mark.asyncio
async def test_siapkan_menyimpan_rencana_dan_menampilkan_tombol():
    snap = sb.tema_ke_snapshot("coding", nama_server="Dev")
    interaksi = _interaksi()
    ok = await bc.siapkan(interaksi, snap, "tema:coding")

    assert ok
    assert sb.ambil_siap(GID)["snapshot"]["meta"]["sumber"] == "tema:coding"
    _args, kwargs = interaksi.response.sent[-1]
    assert isinstance(kwargs["view"], bc.KonfirmasiBangun)
    assert "Pratinjau" in kwargs["embed"].title


@pytest.mark.asyncio
async def test_siapkan_menolak_struktur_kosong():
    interaksi = _interaksi()
    ok = await bc.siapkan(interaksi, {"channels": []}, "tema:x")
    assert not ok
    assert sb.ambil_siap(GID) is None
    assert "channel" in interaksi.response.sent[-1][0][0]


@pytest.mark.asyncio
async def test_tombol_batal_menghapus_rencana():
    snap = sb.tema_ke_snapshot("musik")
    sb.simpan_siap(GID, snap, sumber="tema:musik")
    view = bc.KonfirmasiBangun(GID, snap, "tema:musik")

    interaksi = _interaksi()

    async def _edit_message(**kwargs):
        interaksi.response.sent.append(((), kwargs))

    interaksi.response.edit_message = _edit_message
    await view.batal.callback(interaksi)
    assert sb.ambil_siap(GID) is None
    assert "Dibatalkan" in interaksi.response.sent[-1][1]["content"]


# --------------------------------------------------------------------------- #
# Eksekusi
# --------------------------------------------------------------------------- #

class _Role:
    def __init__(self, nama):
        self.name = nama
        self.deleted = False

    def is_default(self):
        return self.name == "@everyone"

    async def delete(self, reason=""):
        self.deleted = True


class _Channel:
    def __init__(self, nama, jenis="text"):
        self.name = nama
        self.type = jenis
        self.deleted = False

    async def delete(self, reason=""):
        self.deleted = True


class _Guild:
    def __init__(self):
        self.id = GID
        self.name = "Server Uji"
        self.roles = [_Role("@everyone")]
        self.categories = []
        self.channels = []
        self.created = {"roles": [], "categories": [], "channels": []}

    async def create_role(self, name, **kwargs):
        self.roles.append(_Role(name))
        self.created["roles"].append(name)
        return self.roles[-1]

    async def create_category(self, name, **kwargs):
        item = _Channel(name, "category")
        self.categories.append(item)
        self.created["categories"].append(name)
        return item

    async def create_text_channel(self, name, **kwargs):
        item = _Channel(name)
        self.channels.append(item)
        self.created["channels"].append(name)
        return item

    async def create_voice_channel(self, name, **kwargs):
        item = _Channel(name, "voice")
        self.channels.append(item)
        self.created["channels"].append(name)
        return item


@pytest.mark.asyncio
async def test_terapkan_rencana_membuat_dan_mencatat(monkeypatch):
    import backup_restore as br

    monkeypatch.setattr(br, "CREATE_DELAY_SEC", 0)

    guild = _Guild()
    snap = sb.tema_ke_snapshot("startup")
    sb.simpan_siap(GID, snap, sumber="tema:startup")

    hasil, pesan = await bc.terapkan_rencana(guild, snap, 42)
    assert hasil["channels"] == len(snap["channels"])
    assert "Dibuat" in pesan
    assert sb.riwayat[GID]["oleh"] == 42
    assert len(sb.riwayat[GID]["dibuat"]["channels"]) == len(snap["channels"])


# --------------------------------------------------------------------------- #
# Meme
# --------------------------------------------------------------------------- #

def test_daftar_dan_cari_template_meme():
    daftar = mc.meme_maker.daftar_template()
    assert len(daftar) == 6
    assert mc.meme_maker.cari_template("NEON") == "neon"
    assert mc.meme_maker.cari_template("🙅") == "drake"
    assert mc.meme_maker.cari_template("tidak-ada") == "klasik"
    assert mc.meme_maker.cari_template(None) == "klasik"


def test_meme_kosong_ditolak():
    buffer, galat = mc.meme_maker.buat_meme("", "   ")
    assert buffer is None and "minimal" in galat


@pytest.mark.parametrize("template", ["klasik", "impact", "drake", "neon", "kertas", "terminal"])
def test_semua_template_menghasilkan_png(template):
    pytest.importorskip("PIL")
    buffer, galat = mc.meme_maker.buat_meme(
        "Teks atas", "Teks bawah yang agak panjang sekali agar terbungkus", template=template
    )
    assert galat == "" and buffer is not None
    data = buffer.getvalue()
    assert data.startswith(b"\x89PNG")
    from PIL import Image

    gambar = Image.open(buffer)
    assert gambar.size == (800, 800)


def test_bungkus_teks_membatasi_baris():
    baris = mc.meme_maker._bungkus("kata " * 200, 12)
    assert len(baris) <= 6
    assert all(len(b) <= 14 for b in baris)
    assert mc.meme_maker._bungkus("   ", 20) == []
