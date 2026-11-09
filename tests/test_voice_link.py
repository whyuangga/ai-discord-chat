"""Tes Paket D#2 — voice linking (role + channel teks privat selama di voice)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import dashboard_uji
import dashboard_voice
import voice_link
import web_dashboard

GID = 123456789012345678
TOKEN = "tok"
ROLE_ID = 900


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    voice_link.reset_runtime_state()
    monkeypatch.setattr(voice_link, "VOICE_LINK_FILE", tmp_path / "voice_link.json")
    yield
    voice_link.reset_runtime_state()


# --------------------------------------------------------------------------- #
# Objek palsu
# --------------------------------------------------------------------------- #
class _Role:
    def __init__(self, rid, nama="Warga Voice"):
        self.id = rid
        self.name = nama
        self.is_default = lambda: False


class _TextChannel:
    def __init__(self, cid=500, nama="⌨️-umum"):
        self.id = cid
        self.name = nama
        self.izin: list[tuple] = []
        self.dihapus = False

    async def set_permissions(self, target, **kwargs):
        if kwargs.get("overwrite", "x") is None:
            self.izin.append(("cabut", getattr(target, "id", 0)))
        else:
            self.izin.append(("beri", getattr(target, "id", 0), kwargs))

    async def delete(self, reason=""):
        self.dihapus = True


class _VoiceChannel:
    def __init__(self, cid=400, nama="Meet & Greet", members=None):
        self.id = cid
        self.name = nama
        self.members = members or []
        self.category = None


class _Guild:
    def __init__(self, channels=None, roles=None):
        self.id = GID
        self.name = "Server Uji"
        self.roles = roles if roles is not None else [_Role(ROLE_ID)]
        self.categories = []
        self.default_role = SimpleNamespace(id=GID, name="@everyone")
        self._channels = {ch.id: ch for ch in (channels or [])}
        self.text_channels = [ch for ch in (channels or []) if isinstance(ch, _TextChannel)]
        self.dibuat: list[str] = []

    def get_channel(self, cid):
        return self._channels.get(int(cid or 0))

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid or 0)), None)

    async def create_text_channel(self, nama, category=None, reason="", overwrites=None):
        ch = _TextChannel(cid=600 + len(self.dibuat), nama=nama)
        self.dibuat.append(nama)
        self._channels[ch.id] = ch
        return ch


class _Member:
    def __init__(self, uid=321, roles=None, bot=False):
        self.id = uid
        self.bot = bot
        self.roles = roles if roles is not None else []
        self.guild = None
        self.diberi: list[int] = []
        self.dicabut: list[int] = []

    async def add_roles(self, role, reason=""):
        self.diberi.append(role.id)
        self.roles = list(self.roles) + [role]

    async def remove_roles(self, role, reason=""):
        self.dicabut.append(role.id)
        self.roles = [r for r in self.roles if r.id != role.id]


def _siap(kanal_privat=True, role=True, **kwargs):
    voice_link.set_config(
        GID,
        enabled=True,
        role_id=ROLE_ID if role else None,
        channel_privat=kanal_privat,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Setelan
# --------------------------------------------------------------------------- #

def test_setelan_dasar():
    data = voice_link.statistik(GID)
    assert data["aktif"] is False and data["enabled"] is False
    assert data["channel_privat"] is True and data["hapus_kosong"] is True

    # channel privat default menyala ⇒ sudah ada efek, jadi aktif begitu dinyalakan
    voice_link.set_config(GID, enabled=True)
    assert voice_link.aktif(GID) is True

    voice_link.set_config(GID, channel_privat=False, role_id=None)
    assert voice_link.aktif(GID) is False  # tidak ada role & tidak ada channel → tanpa efek

    voice_link.set_config(GID, role_id=ROLE_ID)
    assert voice_link.aktif(GID) is True
    voice_link.set_config(GID, enabled=False)
    assert voice_link.aktif(GID) is False


def test_set_config_tidak_menimpa_nilai_lain():
    voice_link.set_config(GID, enabled=True, role_id=ROLE_ID, hapus_kosong=False)
    cfg = voice_link.set_config(GID, kategori_id=77)
    assert cfg["role_id"] == ROLE_ID and cfg["hapus_kosong"] is False
    assert cfg["kategori_id"] == 77 and cfg["enabled"] is True
    voice_link.set_config(GID, role_id=0)
    assert voice_link.peek_config(GID)["role_id"] is None


def test_nama_channel():
    assert voice_link.nama_channel("Meet & Greet 2026!") == "⌨️-meet-greet-2026"
    assert voice_link.nama_channel("  ") == "⌨️-voice"
    assert len(voice_link.nama_channel("x" * 200)) <= voice_link.NAMA_CHANNEL_MAKS


def test_penanda_role_tidak_dobel():
    assert voice_link.tandai_role(GID, 321) is True
    assert voice_link.tandai_role(GID, 321) is False
    assert voice_link.anggota_berole(GID) == {321}
    assert voice_link.lepas_role(GID, 321) is True
    assert voice_link.lepas_role(GID, 321) is False


def test_pasangan_channel_dan_batasnya():
    assert voice_link.link_untuk(GID, 400) == 0
    assert voice_link.catat_link(GID, 400, 500) is True
    assert voice_link.link_untuk(GID, 400) == 500
    daftar = voice_link.daftar_link(GID)
    assert daftar[0]["voice_id"] == 400 and daftar[0]["text_id"] == 500

    for i in range(voice_link.MAX_LINK_PER_GUILD - 1):
        assert voice_link.catat_link(GID, 1000 + i, 2000 + i) is True
    assert voice_link.catat_link(GID, 9999, 8888) is False
    # memperbarui pasangan yang sudah ada tetap boleh walau penuh
    assert voice_link.catat_link(GID, 400, 501) is True
    assert voice_link.hapus_link(GID, 400) is True
    assert voice_link.hapus_link(GID, 400) is False


# --------------------------------------------------------------------------- #
# Alur event
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_masuk_voice_dapat_role_dan_channel_privat():
    _siap()
    guild = _Guild()
    member = _Member()
    member.guild = guild
    voice = _VoiceChannel()

    aksi = await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=voice)
    )
    assert member.diberi == [ROLE_ID]
    assert "role_diberi" in aksi and "channel_dibuat" in aksi and "akses_diberi" in aksi
    text_id = voice_link.link_untuk(GID, voice.id)
    assert text_id
    teks = guild.get_channel(text_id)
    assert teks.izin[0] == ("beri", GID, {"view_channel": False}) or teks.izin[0][0] == "beri"
    assert voice_link.anggota_berole(GID) == {member.id}


@pytest.mark.asyncio
async def test_keluar_voice_mencabut_semua_dan_menghapus_channel_kosong():
    _siap()
    guild = _Guild()
    member = _Member()
    member.guild = guild
    voice = _VoiceChannel(members=[])

    await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=voice)
    )
    text_id = voice_link.link_untuk(GID, voice.id)

    aksi = await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=voice), SimpleNamespace(channel=None)
    )
    assert member.dicabut == [ROLE_ID]
    assert "role_dicabut" in aksi and "akses_dicabut" in aksi and "channel_dihapus" in aksi
    assert guild.get_channel(text_id).dihapus is True
    assert voice_link.link_untuk(GID, voice.id) == 0
    assert voice_link.anggota_berole(GID) == set()


@pytest.mark.asyncio
async def test_pindah_channel_tidak_mencabut_role():
    _siap(kanal_privat=False)
    guild = _Guild()
    member = _Member()
    member.guild = guild
    a = _VoiceChannel(cid=400, nama="A")
    b = _VoiceChannel(cid=401, nama="B")

    await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=a)
    )
    await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=a), SimpleNamespace(channel=b)
    )
    assert member.dicabut == []
    assert member.diberi == [ROLE_ID]  # tidak dobel karena role sudah dimiliki


@pytest.mark.asyncio
async def test_role_asli_tidak_dicabut():
    _siap(kanal_privat=False)
    guild = _Guild()
    role = _Role(ROLE_ID)
    member = _Member(roles=[role])  # sudah punya role sebelum masuk voice
    member.guild = guild
    voice = _VoiceChannel()

    await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=voice)
    )
    assert voice_link.anggota_berole(GID) == set()  # bukan bot yang memberi

    await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=voice), SimpleNamespace(channel=None)
    )
    assert member.dicabut == []  # role asli tetap dipegang member


@pytest.mark.asyncio
async def test_channel_privat_mati_tidak_membuat_channel():
    _siap(kanal_privat=False)
    guild = _Guild()
    member = _Member()
    member.guild = guild
    voice = _VoiceChannel()

    aksi = await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=voice)
    )
    assert guild.dibuat == [] and "channel_dibuat" not in aksi
    assert "role_diberi" in aksi


@pytest.mark.asyncio
async def test_batas_channel_privat():
    _siap(role=False)
    for i in range(voice_link.MAX_LINK_PER_GUILD):
        voice_link.catat_link(GID, 5000 + i, 6000 + i)
    guild = _Guild()
    member = _Member()
    member.guild = guild

    aksi = await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=_VoiceChannel(cid=400))
    )
    assert "batas_channel" in aksi and guild.dibuat == []


@pytest.mark.asyncio
async def test_hapus_kosong_mati_membiarkan_channel():
    _siap(kanal_privat=True, hapus_kosong=False)
    guild = _Guild()
    member = _Member()
    member.guild = guild
    voice = _VoiceChannel()

    await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=voice)
    )
    text_id = voice_link.link_untuk(GID, voice.id)
    aksi = await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=voice), SimpleNamespace(channel=None)
    )
    assert "channel_dihapus" not in aksi
    assert voice_link.link_untuk(GID, voice.id) == text_id


@pytest.mark.asyncio
async def test_bot_dan_fitur_mati_dilewati():
    _siap()
    guild = _Guild()
    bot_member = _Member(uid=999, bot=True)
    bot_member.guild = guild
    voice = _VoiceChannel()
    assert await voice_link.handle_voice_state(
        bot_member, SimpleNamespace(channel=None), SimpleNamespace(channel=voice)
    ) == []

    voice_link.set_config(GID, enabled=False)
    member = _Member()
    member.guild = guild
    assert await voice_link.handle_voice_state(
        member, SimpleNamespace(channel=None), SimpleNamespace(channel=_VoiceChannel())
    ) == []


# --------------------------------------------------------------------------- #
# Simpan / muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat(tmp_path):
    _siap(kanal_privat=True)
    voice_link.catat_link(GID, 400, 500)
    await voice_link.save_voice_link_to_disk()

    mentah = json.loads((tmp_path / "voice_link.json").read_text(encoding="utf-8"))
    isi = mentah["guilds"][str(GID)]
    assert isi["config"]["role_id"] == ROLE_ID
    assert isi["channels"]["400"]["text_id"] == 500

    voice_link.reset_runtime_state()
    assert voice_link.load_voice_link_from_disk() == (1, 1)
    assert voice_link.aktif(GID) is True
    assert voice_link.link_untuk(GID, 400) == 500


def test_muat_berkas_rusak(tmp_path):
    berkas = tmp_path / "voice_link.json"
    berkas.write_text("{rusak", encoding="utf-8")
    assert voice_link.load_voice_link_from_disk() == (0, 0)
    berkas.write_text(json.dumps({"guilds": {"x": 1, "2": "bukan-dict"}}), encoding="utf-8")
    assert voice_link.load_voice_link_from_disk() == (0, 0)


def test_cleanup_membuang_server_kosong():
    voice_link.set_config(9, role_id=1)  # nonaktif & tanpa channel → boleh dibuang
    _siap()
    voice_link.catat_link(GID, 400, 500)
    assert voice_link.cleanup_voice_link_runtime() >= 1
    assert 9 not in voice_link.link_config
    assert GID in voice_link.link_config


# --------------------------------------------------------------------------- #
# Satu listener voice (anti-tabrakan `bot.event`)
# --------------------------------------------------------------------------- #

def test_hanya_satu_listener_voice():
    akar = Path(__file__).resolve().parents[1]
    tempvoice = (akar / "cogs" / "tempvoice_cog.py").read_text(encoding="utf-8")
    assert "@bot.event" not in tempvoice, "listener kedua akan menimpa listener di events_cog"
    events = (akar / "cogs" / "events_cog.py").read_text(encoding="utf-8")
    assert "tv.handle_voice_update" in events
    assert "voice_link.handle_voice_state" in events


# --------------------------------------------------------------------------- #
# Command & dashboard
# --------------------------------------------------------------------------- #

def test_command_tautkan_terdaftar():
    from cogs.tempvoice_cog import tempvoice_group

    perintah = {cmd.name: cmd for cmd in tempvoice_group.commands}
    assert "tautkan" in perintah
    opsi = {p.name for p in perintah["tautkan"].parameters}
    assert opsi == {"aktif", "role", "channel_privat", "hapus_kosong", "kategori"}


def test_panel_voice_menempel_di_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-voice"] == "interaksi"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["voice"] == "interaksi"
    assert dashboard_uji.ANCHOR_UJI["voice"] == "p-voice"


def test_panel_voice_render():
    _siap()
    voice_link.catat_link(GID, 400, 500)
    guild = _Guild()
    bot = SimpleNamespace(get_guild=lambda gid: guild)
    html = dashboard_voice.render_voice_block(bot, GID, TOKEN)
    assert 'class="subpanel" id="p-voice"' in html
    assert "voice-setelan" in html
    assert "voice-lepas:400" in html
    assert "@Warga Voice" in html
    assert "aktif" in html


def test_panel_voice_peringatkan_tanpa_efek():
    voice_link.set_config(GID, enabled=True, channel_privat=False, role_id=None)
    html = dashboard_voice.render_voice_block(None, GID, TOKEN)
    assert "belum ada efek" in html
    assert "Belum ada channel privat" in html


@pytest.mark.asyncio
async def test_aksi_voice_setelan_dan_lepas():
    ok, pesan = await dashboard_voice.aksi_voice(
        None, GID, "voice-setelan",
        {"enabled": "1", "role_id": str(ROLE_ID), "channel_privat": "0", "hapus_kosong": "1"},
    )
    assert ok and "aktif" in pesan
    cfg = voice_link.peek_config(GID)
    assert cfg["enabled"] is True and cfg["role_id"] == ROLE_ID and cfg["channel_privat"] is False

    voice_link.catat_link(GID, 400, 500)
    ok, pesan = await dashboard_voice.aksi_voice(None, GID, "voice-lepas:400", {})
    assert ok and voice_link.link_untuk(GID, 400) == 0
    ok, pesan = await dashboard_voice.aksi_voice(None, GID, "voice-lepas:400", {})
    assert ok is False
    ok, pesan = await dashboard_voice.aksi_voice(None, GID, "voice-ngawur", {})
    assert ok is False


@pytest.mark.asyncio
async def test_uji_voice_simulasi():
    guild = _Guild()
    ok, pesan = dashboard_uji._uji_voice(None, guild)
    assert ok is False and "belum dinyalakan" in pesan

    voice_link.set_config(GID, enabled=True, channel_privat=False, role_id=None)
    ok, pesan = dashboard_uji._uji_voice(None, guild)
    assert ok is False and "belum berefek" in pesan

    _siap()
    ok, pesan = dashboard_uji._uji_voice(None, guild)
    assert ok is True and "Simulasi" in pesan
    assert "Warga Voice" in pesan or f"<@&{ROLE_ID}>" in pesan
    assert voice_link.anggota_berole(GID) == set()  # tidak menyentuh member

    guild.roles = []  # role dihapus dari server
    ok, pesan = dashboard_uji._uji_voice(None, guild)
    assert ok is False and "tidak ada" in pesan
