"""Uji papan sorotan berlapis: papan utama + varian (emoji/ambang/channel/warna sendiri)."""

from __future__ import annotations

import pytest

import community_tools
import dashboard_admin
import dashboard_ui
import discord

GID = 77


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan():
    community_tools.starboard_guilds.clear()
    yield
    community_tools.starboard_guilds.clear()


class _Reaksi:
    def __init__(self, emoji: str, count: int):
        self.emoji = emoji
        self.count = count


class _Penulis:
    display_name = "Sari"
    bot = False
    display_avatar = None


class _Pesan:
    def __init__(self, reaksi: list[tuple[str, int]]):
        self.id = 555
        self.content = "halo dunia"
        self.attachments = []
        self.jump_url = "https://discord.com/channels/1/2/555"
        self.created_at = discord.utils.utcnow()
        self.author = _Penulis()
        self.reactions = [_Reaksi(e, c) for e, c in reaksi]


class _Kanal:
    def __init__(self, cid: int, log: list):
        self.id = cid
        self.log = log

    async def send(self, content=None, embed=None):
        self.log.append({"aksi": "kirim", "channel": self.id, "content": content, "embed": embed})
        return type("Terkirim", (), {"id": 9000 + self.id})()

    def get_partial_message(self, mid: int):
        kanal = self

        class _Parsial:
            async def edit(self, content=None, embed=None):
                kanal.log.append({"aksi": "edit", "id": mid, "content": content, "embed": embed})

            async def delete(self):
                kanal.log.append({"aksi": "hapus", "id": mid})

        return _Parsial()

    async def fetch_message(self, mid: int):
        return PEMBUNGKUS["pesan"]


PEMBUNGKUS: dict = {"pesan": _Pesan([])}


class _Bot:
    def __init__(self, channels: dict, log: list):
        self.channels = channels
        self.log = log

    def get_channel(self, cid: int):
        if cid not in self.channels:
            return None
        return _Kanal(cid, self.log)


def _payload(emoji: str, *, channel_id: int = 500):
    return type(
        "Payload",
        (),
        {"guild_id": GID, "channel_id": channel_id, "message_id": 555, "emoji": emoji},
    )()


def _siapkan_dua_papan() -> None:
    community_tools.set_starboard_config(GID, channel_id=900, threshold=3)
    community_tools.add_starboard_board(
        GID, "Skull", emoji="💀", threshold=5, channel_id=901, warna="#FF8A00"
    )


# ==============================================================================
# MODEL
# ==============================================================================
def test_papan_utama_selalu_ada_dan_varian_bisa_ditambah():
    assert community_tools.list_starboard_boards(GID) == []

    community_tools.set_starboard_config(GID, channel_id=900, threshold=3)
    papan = community_tools.list_starboard_boards(GID)
    assert len(papan) == 1 and papan[0]["utama"] is True
    assert papan[0]["emoji"] == "⭐" and papan[0]["threshold"] == 3

    ok, pesan = community_tools.add_starboard_board(
        GID, "Skull", emoji="💀", threshold=5, channel_id=901, warna="#ff8a00"
    )
    assert ok is True and "ditambahkan" in pesan
    ok, pesan = community_tools.add_starboard_board(GID, "Clown", emoji="🤡", threshold=7)
    assert ok is True and "ditambahkan" in pesan

    papan = {p["kunci"]: p for p in community_tools.list_starboard_boards(GID)}
    assert set(papan) == {"utama", "skull", "clown"}
    assert papan["skull"]["warna"] == "#FF8A00"
    # Channel varian kosong → ikut channel papan utama
    assert papan["clown"]["channel_id"] == 900
    assert papan["clown"]["threshold"] == 7


def test_batas_jumlah_validasi_dan_hapus_papan():
    community_tools.set_starboard_config(GID, channel_id=900)
    for nama in ("Skull", "Clown", "Cursed"):
        assert community_tools.add_starboard_board(GID, nama)[0] is True
    ok, pesan = community_tools.add_starboard_board(GID, "Keempat", emoji="🔥")
    assert ok is False and "penuh" in pesan

    # Nama papan utama tidak boleh dipakai varian
    assert community_tools.add_starboard_board(GID, "Starboard")[0] is False
    assert community_tools.add_starboard_board(GID, "   ")[0] is False

    # Upsert: nama sama (beda kapital) memperbarui, bukan menambah
    ok, pesan = community_tools.add_starboard_board(GID, "skull", threshold=9)
    assert ok is True and "diperbarui" in pesan
    assert len(community_tools.list_starboard_boards(GID)) == 4

    assert community_tools.remove_starboard_board(GID, "utama")[0] is False
    assert community_tools.remove_starboard_board(GID, "tidak-ada")[0] is False
    assert community_tools.remove_starboard_board(GID, "Clown")[0] is True
    assert "clown" not in {p["kunci"] for p in community_tools.list_starboard_boards(GID)}

    # Varian tanpa starboard aktif ditolak dengan pesan jelas
    community_tools.starboard_guilds.clear()
    ok, pesan = community_tools.add_starboard_board(GID, "Skull")
    assert ok is False and "belum aktif" in pesan
    assert community_tools.remove_starboard_board(GID, "Skull")[0] is False


@pytest.mark.asyncio
async def test_simpan_dan_muat_ulang_papan_varian(monkeypatch, tmp_path):
    """Papan varian ikut tersimpan di community_tools.json dan terbaca lagi."""
    monkeypatch.setattr(
        community_tools, "COMMUNITY_TOOLS_FILE", tmp_path / "community_tools.json"
    )
    _siapkan_dua_papan()
    await community_tools.save_community_tools_to_disk()

    community_tools.starboard_guilds.clear()
    community_tools.load_community_tools_from_disk()
    papan = {p["kunci"]: p for p in community_tools.list_starboard_boards(GID)}
    assert papan["utama"]["channel_id"] == 900
    assert papan["skull"]["emoji"] == "💀" and papan["skull"]["threshold"] == 5
    assert papan["skull"]["warna"] == "#FF8A00"


# ==============================================================================
# PENYOROTAN
# ==============================================================================
@pytest.mark.asyncio
async def test_dua_papan_menyorot_pesan_yang_sama_secara_independen():
    _siapkan_dua_papan()
    log: list = []
    bot = _Bot({500: True, 900: True, 901: True}, log)

    # ⭐ cukup (3) → papan utama menyorot, papan 💀 belum
    PEMBUNGKUS["pesan"] = _Pesan([("⭐", 4)])
    assert await community_tools.handle_starboard_reaction(bot, _payload("⭐"), added=True) is True
    assert [x for x in log if x["aksi"] == "kirim"][0]["channel"] == 900
    assert "Skull" not in str(log[0]["embed"].footer.text)

    # 💀 5 reaksi → papan skull ikut menyorot ke channel-nya sendiri
    log.clear()
    PEMBUNGKUS["pesan"] = _Pesan([("⭐", 4), ("💀", 6)])
    assert await community_tools.handle_starboard_reaction(bot, _payload("💀"), added=True) is True
    kiriman = [x for x in log if x["aksi"] == "kirim"]
    assert kiriman and kiriman[0]["channel"] == 901
    assert "Skull" in str(kiriman[0]["embed"].footer.text)
    assert "**Skull**" in str(kiriman[0]["content"])
    assert kiriman[0]["embed"].colour.value == 0xFF8A00

    # Kedua papan menyimpan entrinya sendiri-sendiri
    assert "555" in community_tools.starboard_guilds[GID]["entries"]
    assert "555" in community_tools.starboard_guilds[GID]["boards"][0]["entries"]


@pytest.mark.asyncio
async def test_reaksi_naik_diperbarui_dan_turun_menghapus_per_papan():
    _siapkan_dua_papan()
    log: list = []
    bot = _Bot({500: True, 900: True, 901: True}, log)

    PEMBUNGKUS["pesan"] = _Pesan([("⭐", 4)])
    await community_tools.handle_starboard_reaction(bot, _payload("⭐"), added=True)

    # ⭐ naik 4 → 7: pesan sorotan diperbarui, bukan dikirim ulang
    log.clear()
    PEMBUNGKUS["pesan"] = _Pesan([("⭐", 8)])
    assert await community_tools.handle_starboard_reaction(bot, _payload("⭐"), added=True) is True
    assert [x["aksi"] for x in log] == ["edit"]
    assert community_tools.starboard_guilds[GID]["entries"]["555"]["count"] == 7

    # ⭐ turun di bawah ambang → sorotan papan utama dihapus, entri bersih
    log.clear()
    PEMBUNGKUS["pesan"] = _Pesan([("⭐", 2)])
    assert await community_tools.handle_starboard_reaction(bot, _payload("⭐"), added=False) is True
    assert [x["aksi"] for x in log] == ["hapus"]
    assert community_tools.starboard_guilds[GID]["entries"] == {}
    # Papan varian tidak terpengaruh
    assert community_tools.starboard_guilds[GID]["boards"][0]["entries"] == {}


@pytest.mark.asyncio
async def test_emoji_asing_pesan_bot_dan_channel_papan_diabaikan():
    _siapkan_dua_papan()
    log: list = []
    bot = _Bot({500: True, 900: True, 901: True}, log)

    PEMBUNGKUS["pesan"] = _Pesan([("⭐", 9)])
    assert await community_tools.handle_starboard_reaction(bot, _payload("🔥"), added=True) is False

    # Channel papan sorotan tidak boleh disorot lagi (anti-loop), termasuk channel varian
    assert await community_tools.handle_starboard_reaction(
        bot, _payload("⭐", channel_id=900), added=True
    ) is False
    assert await community_tools.handle_starboard_reaction(
        bot, _payload("💀", channel_id=901), added=True
    ) is False

    # Pesan dari bot tidak disorot
    bot_pesan = _Pesan([("⭐", 9)])
    bot_pesan.author.bot = True
    PEMBUNGKUS["pesan"] = bot_pesan
    assert await community_tools.handle_starboard_reaction(bot, _payload("⭐"), added=True) is False
    assert log == []


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_setelan_dan_blok_dashboard_papan_varian():
    kunci = {item["kunci"]: item for item in dashboard_admin.FITUR_LIST}
    assert "starboard.warna" in kunci
    community_tools.set_starboard_config(GID, channel_id=900)
    ok, pesan = kunci["starboard.warna"]["simpan"](GID, "#22cc88")
    assert ok and "#22CC88" in pesan
    assert community_tools.starboard_guilds[GID]["warna"] == "#22CC88"
    assert kunci["starboard.warna"]["simpan"](GID, "hijau")[0] is False

    community_tools.add_starboard_board(GID, "Skull", emoji="💀", threshold=5, channel_id=901)

    class _Bot:
        def get_guild(self, gid):
            return None

    html = dashboard_ui.render_starboard_block(_Bot(), GID, "tok")
    assert "Papan sorotan (varian)" in html
    assert "starboard-tambah" in html
    assert "starboard-hapus:skull" in html
    assert "💀 Skull" in html and "≥ 5 reaksi" in html
    # Papan utama tidak punya tombol hapus
    assert "starboard-hapus:utama" not in html
    assert "lencana on" in html and "lencana off" in html


def test_blok_dashboard_menjelaskan_bila_belum_aktif():
    class _Bot:
        def get_guild(self, gid):
            return None

    html = dashboard_ui.render_starboard_block(_Bot(), GID, "tok")
    assert "belum aktif" in html
    # Form tetap ada supaya Admin bisa menyiapkan papan setelah menyalakan starboard
    assert "starboard-tambah" in html


def test_command_varian_terdaftar_dengan_parameter_lengkap():
    from cogs.community_cog import starboard_group

    kunci = {c.name: c for c in starboard_group.commands}
    assert "varian" in kunci
    assert len(kunci["varian"].description) <= 100
    assert {"tambah", "emoji", "batas", "channel", "warna", "hapus"} <= {
        p.name for p in kunci["varian"].parameters
    }
