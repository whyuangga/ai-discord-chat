"""Tes Paket C#2 — lencana (achievements) bertingkat.

Mencakup: tangga tingkat & progres, role hadiah, sakelar per server, idempotensi
`cek_member`, batas 500 member, papan & statistik, simpan/muat JSON, command
`/lencana`, hook pertumbuhan (pesan & voice), serta panel dashboard + tombol uji.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import achievements
import dashboard_lencana
import dashboard_uji
import levels
import web_dashboard


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    achievements.reset_runtime_state()
    monkeypatch.setattr(levels, "levels", {})
    monkeypatch.setattr(achievements, "ACHIEVEMENTS_FILE", tmp_path / "achievements.json")
    monkeypatch.setattr(achievements, "_cache_menang", {})
    yield
    achievements.reset_runtime_state()


def _member(gid: int, uid: int, *, pesan: int = 0, voice_sec: int = 0, level: int = 1,
            prestige: int = 0):
    """Isi data level mentah persis seperti yang dicatat `levels.py`."""
    levels.levels[f"{int(gid)}:{int(uid)}"] = {
        "xp": 0,
        "level": level,
        "messages": pesan,
        "voice_sec": voice_sec,
        "prestige": prestige,
    }


# --------------------------------------------------------------------------- #
# Tangga tingkat, progres, & nilai mentah
# --------------------------------------------------------------------------- #

def test_tangga_tingkat_empat_lencana():
    kunci = [item["kunci"] for item in achievements.ACHIEVEMENTS]
    assert kunci == ["chat", "voice", "level", "giveaway"]
    assert achievements.ACHIEVEMENT_MAP["chat"]["tingkat"] == (50, 250, 1000, 5000, 15000)
    assert achievements.ACHIEVEMENT_MAP["voice"]["tingkat"] == (60, 300, 1200, 5000)
    assert achievements.ACHIEVEMENT_MAP["level"]["tingkat"] == (5, 10, 25, 50)
    assert achievements.ACHIEVEMENT_MAP["giveaway"]["tingkat"] == (1, 3, 10)
    for item in achievements.ACHIEVEMENTS:
        assert item["satuan"] and item["label"] and item["emoji"]
        assert list(item["tingkat"]) == sorted(item["tingkat"])


def test_tingkat_tercapai_dan_total_lencana():
    assert achievements.tingkat_tercapai("chat", 0) == 0
    assert achievements.tingkat_tercapai("chat", 49) == 0
    assert achievements.tingkat_tercapai("chat", 50) == 1
    assert achievements.tingkat_tercapai("chat", 249) == 1
    assert achievements.tingkat_tercapai("chat", 10**9) == 5
    assert achievements.tingkat_tercapai("giveaway", 10**9) == 3
    assert achievements.tingkat_tercapai("tidak-ada", 10**6) == 0
    _member(1, 5, pesan=260, level=7)
    assert achievements.total_lencana(1, 5) == 3  # chat 2 + level 1


def test_nilai_member_membaca_data_yang_sudah_ada(monkeypatch):
    import engagement

    _member(1, 42, pesan=260, voice_sec=1500, level=7)
    monkeypatch.setattr(
        engagement,
        "giveaways",
        {
            "900": {
                "guild_id": 1,
                "history": [
                    {"pemenang": [42], "aksi": "akhir"},
                    {"pemenang": [42, 43], "aksi": "reroll"},
                    {"pemenang": [43], "aksi": "reroll"},
                ],
            },
            "901": {"guild_id": 2, "history": [{"pemenang": [42], "aksi": "akhir"}]},
        },
    )
    monkeypatch.setattr(achievements, "_cache_menang", {})
    assert achievements.nilai_member(1, 42) == {
        "chat": 260,
        "voice": 25,
        "level": 7,
        "giveaway": 2,
    }
    # server lain tidak ikut terhitung
    assert achievements.nilai_member(2, 42)["giveaway"] == 1


def test_progres_member_lengkap_dan_aman():
    _member(5, 7, pesan=60, level=12)
    baris = achievements.progres(5, 7)
    assert len(baris) == 4
    chat = next(b for b in baris if b["kunci"] == "chat")
    assert chat["nilai"] == 60 and chat["tingkat"] == 1
    assert chat["maks"] == 5 and chat["berikut"] == 250
    assert 0 <= chat["persen"] <= 10
    level = next(b for b in baris if b["kunci"] == "level")
    assert level["tingkat"] == 2 and level["berikut"] == 25
    kosong = achievements.progres(999, 12345)  # member tak dikenal tetap aman
    assert all(item["nilai"] == 0 and item["tingkat"] == 0 for item in kosong)
    assert all(item["persen"] == 0 for item in kosong)


def test_progres_maksimum_penuh_dan_prestise():
    _member(1, 3, pesan=20000, voice_sec=60 * 6000, level=80)
    baris = {b["kunci"]: b for b in achievements.progres(1, 3)}
    assert baris["chat"]["persen"] == 100 and baris["chat"]["berikut"] is None
    assert baris["voice"]["tingkat"] == 4 and baris["level"]["tingkat"] == 4


# --------------------------------------------------------------------------- #
# Setelan & role hadiah
# --------------------------------------------------------------------------- #

def test_setelan_default_aktif_tanpa_channel():
    cfg = achievements.peek_config(3)
    assert cfg["enabled"] is True
    assert cfg["channel_id"] is None and cfg["rewards"] == {}

    achievements.set_config(3, enabled=False, channel_id=77)
    assert achievements.get_config(3)["channel_id"] == 77
    assert achievements.peek_config(3)["enabled"] is False
    # angka aneh → tanpa channel, tidak melempar
    achievements.set_config(3, channel_id="bukan-angka")
    assert achievements.get_config(3)["channel_id"] is None
    achievements.set_config(3, channel_id=0)
    assert achievements.get_config(3)["channel_id"] is None
    # peek_config mengembalikan salinan: dashboard tidak bisa merusak store
    achievements.peek_config(3)["enabled"] = True
    assert achievements.peek_config(3)["enabled"] is False
    assert achievements.get_config(3) is achievements.get_config(3)


def test_role_hadiah_validasi_dan_rekap():
    ok, pesan = achievements.set_reward(1, "chat", 1, 555)
    assert ok and "<@&555>" in pesan and "50" in pesan
    assert achievements.role_for(1, "chat", 1) == 555
    assert achievements.role_for(1, "chat", 2) == 0

    assert achievements.set_reward(1, "tidak-ada", 1, 555)[0] is False
    assert achievements.set_reward(1, "chat", 0, 555)[0] is False
    assert achievements.set_reward(1, "chat", 99, 555)[0] is False

    ok, pesan = achievements.set_reward(1, "voice", 2, 999)
    assert ok and achievements.role_for(1, "voice", 2) == 999
    ok, pesan = achievements.set_reward(1, "voice", 2, None)
    assert ok and "dihapus" in pesan
    assert achievements.role_for(1, "voice", 2) == 0
    ok, pesan = achievements.set_reward(1, "voice", 2, None)
    assert ok is False and "tidak ada" in pesan.lower()


def test_cek_member_idempoten_dan_hanya_tingkat_baru():
    _member(1, 9, pesan=60, level=6)
    baru = achievements.cek_member(1, 9)
    assert {(item["kunci"], item["tingkat"]) for item in baru} == {("chat", 1), ("level", 1)}
    assert all(item["ambang"] for item in baru)
    assert achievements.cek_member(1, 9) == []  # tidak dobel
    assert achievements.tersimpan(1, 9)["chat"] == 1

    _member(1, 9, pesan=1200, level=10)
    baru = achievements.cek_member(1, 9)
    # chat 1 → 3 (melewati 250 & 1.000 sekaligus) dan level 1 → 2
    assert {(item["kunci"], item["tingkat"]) for item in baru} == {
        ("chat", 2),
        ("chat", 3),
        ("level", 2),
    }
    assert achievements.tersimpan(1, 9)["chat"] == 3


def test_cek_member_dimatikan_tidak_mencatat():
    achievements.set_config(1, enabled=False)
    _member(1, 9, pesan=5000, level=60)
    assert achievements.cek_member(1, 9) == []
    assert achievements.tersimpan(1, 9) == {}


def test_cek_member_tanpa_aktivitas_tidak_memakan_kuota():
    assert achievements.cek_member(1, 77) == []
    assert 1 not in (achievements.ach_members or {})


def test_batas_member_per_server(monkeypatch):
    monkeypatch.setattr(achievements, "MAX_MEMBER_PER_GUILD", 3)
    achievements.ach_members[1] = {
        uid: {"chat": 1, "diperbarui": float(uid)} for uid in (1, 2, 3)
    }
    _member(1, 4, pesan=60)
    baru = achievements.cek_member(1, 4)
    assert baru
    tersimpan = achievements.ach_members[1]
    assert len(tersimpan) == 3
    assert 4 in tersimpan and 1 not in tersimpan
    # eviction memakai "diperbarui" terlama
    assert achievements.cleanup_achievements_runtime() >= 0


def test_papan_dan_statistik():
    achievements.set_config(1, enabled=True, channel_id=5)
    achievements.set_reward(1, "chat", 1, 800)
    achievements.set_reward(1, "level", 2, 801)
    _member(1, 1, pesan=900, level=30)
    _member(1, 2, pesan=60, level=3)
    _member(1, 3, pesan=0, level=1)
    for uid in (1, 2, 3):
        achievements.cek_member(1, uid)

    papan = achievements.papan(1, limit=10)
    assert [row["user_id"] for row in papan] == [1, 2]
    assert papan[0]["total"] >= papan[1]["total"]
    assert len(achievements.papan(1, limit=1)) == 1
    assert achievements.papan(2) == []

    data = achievements.statistik(1)
    assert data["aktif"] is True and data["channel_id"] == 5
    assert data["anggota"] == 2
    assert data["hadiah_role"] == 2
    assert data["total_tingkat"] == sum(data["per_lencana"].values())
    # member 1 (level 30 → 3 tingkat, 900 pesan → 2) · member 2 (level 3 & 60 pesan → 1)
    assert data["per_lencana"]["chat"] == 3
    assert data["per_lencana"]["level"] == 3
    assert data["total_tingkat"] == 6
    kosong = achievements.statistik(2)
    assert kosong["anggota"] == 0 and kosong["total_tingkat"] == 0
    assert kosong["aktif"] is True and kosong["hadiah_role"] == 0


# --------------------------------------------------------------------------- #
# Simpan / muat JSON
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_muat_dan_bersihkan(tmp_path):
    achievements.set_config(1, enabled=True, channel_id=9)
    achievements.set_reward(1, "chat", 1, 700)
    _member(1, 1, pesan=55)
    achievements.cek_member(1, 1)
    await achievements.save_achievements_to_disk()

    mentah = json.loads((tmp_path / "achievements.json").read_text(encoding="utf-8"))
    isi = mentah["guilds"]["1"]
    assert isi["config"]["channel_id"] == 9
    assert isi["config"]["rewards"] == {"chat:1": 700}
    assert isi["members"]["1"]["chat"] == 1

    achievements.reset_runtime_state()
    server, anggota = achievements.load_achievements_from_disk()
    assert (server, anggota) == (1, 1)
    assert achievements.peek_config(1)["channel_id"] == 9
    assert achievements.role_for(1, "chat", 1) == 700
    assert achievements.tersimpan(1, 1)["chat"] == 1

    # pemangkasan runtime tidak membuang data yang masih dipakai
    assert achievements.cleanup_achievements_runtime() == 0
    assert achievements.peek_config(1)["enabled"] is True


@pytest.mark.asyncio
async def test_muat_data_rusak_tidak_melempar(tmp_path, monkeypatch):
    berkas = tmp_path / "achievements.json"
    berkas.write_text("{bukan json", encoding="utf-8")
    assert achievements.load_achievements_from_disk() == (0, 0)

    berkas.write_text(json.dumps({"guilds": {"x": 1}}), encoding="utf-8")
    assert achievements.load_achievements_from_disk() == (0, 0)

    berkas.write_text(json.dumps({"guilds": {"2": "bukan-dict"}}), encoding="utf-8")
    assert achievements.load_achievements_from_disk() == (0, 0)


@pytest.mark.asyncio
async def test_simpan_membuat_berkas_dan_idempoten(tmp_path):
    await achievements.save_achievements_to_disk()
    await achievements.save_achievements_to_disk()
    assert (tmp_path / "achievements.json").exists()
    assert not (tmp_path / "achievements.json.tmp").exists()


# --------------------------------------------------------------------------- #
# Command /lencana
# --------------------------------------------------------------------------- #

def test_group_lencana_terdaftar_dengan_lima_subcommand():
    from main import bot as bot_main

    group = bot_main.tree.get_command("lencana")
    assert group is not None
    assert {cmd.name for cmd in group.commands} == {"lihat", "papan", "periksa", "atur", "role"}
    assert group.guild_only is True
    for cmd in group.commands:
        assert cmd.description and len(cmd.description) <= 100


def test_atur_dan_role_hanya_untuk_staf():
    from cogs.lencana_cog import _is_admin

    def _interaksi(admin: bool, manage: bool):
        return SimpleNamespace(
            user=SimpleNamespace(
                guild_permissions=SimpleNamespace(administrator=admin, manage_guild=manage)
            )
        )

    assert _is_admin(_interaksi(True, False))
    assert _is_admin(_interaksi(False, True))
    assert not _is_admin(_interaksi(False, False))
    assert not _is_admin(SimpleNamespace(user=SimpleNamespace(guild_permissions=None)))


def test_bar_progres_sepuluh_kotak():
    from cogs.lencana_cog import _bar

    assert _bar(0) == "▱" * 10
    assert _bar(100) == "▰" * 10
    assert len(_bar(45)) == 10 and _bar(45).count("▰") == 4
    assert len(_bar(-20)) == 10 and len(_bar(999)) == 10


@pytest.mark.asyncio
async def test_proses_lencana_memberi_role_dan_mengumumkan():
    from cogs.lencana_cog import proses_lencana

    achievements.set_config(1, enabled=True, channel_id=10)
    achievements.set_reward(1, "chat", 1, 800)
    _member(1, 5, pesan=51, level=2)

    ditambah, dikirim = [], []

    class _Role:
        id = 800

    class _Member:
        id = 5
        display_name = "Budi"
        mention = "<@5>"
        roles = []
        bot = False

        async def add_roles(self, role, reason=None):
            ditambah.append((role.id, reason))

    class _Channel:
        id = 10

        async def send(self, *args, **kwargs):
            dikirim.append(args[0] if args else kwargs.get("content"))

    guild = SimpleNamespace(
        id=1, name="Server", get_role=lambda rid: _Role(), get_channel=lambda cid: _Channel()
    )
    bot = SimpleNamespace(guilds=[guild], get_channel=lambda cid: _Channel())

    hasil = await proses_lencana(bot, guild, _Member(), sumber="chat")
    assert any(item.get("role_id") == 800 for item in hasil)
    assert ditambah and ditambah[0][0] == 800
    assert "alasan" not in ditambah[0][1].lower() and "Lencana" in ditambah[0][1]
    assert dikirim and "membuka lencana" in dikirim[0]
    # panggilan kedua tidak mengulang hadiah/pengumuman
    assert await proses_lencana(bot, guild, _Member(), sumber="chat") == []
    assert len(dikirim) == 1


@pytest.mark.asyncio
async def test_proses_lencana_aman_tanpa_guild_channel_atau_bot():
    from cogs.lencana_cog import proses_lencana

    assert await proses_lencana(None, None, None) == []
    assert await proses_lencana(SimpleNamespace(), None, SimpleNamespace(id=1)) == []
    assert await proses_lencana(None, SimpleNamespace(id=1), None) == []
    # member bot tidak pernah diberi lencana
    assert await proses_lencana(SimpleNamespace(), SimpleNamespace(id=1),
                                SimpleNamespace(id=2, bot=True)) == []

    _member(2, 5, pesan=51)
    member = SimpleNamespace(id=5, display_name="A", mention="<@5>", roles=[], bot=False)
    guild = SimpleNamespace(id=2, name="S", get_role=lambda rid: None, get_channel=lambda cid: None)
    hasil = await proses_lencana(SimpleNamespace(guilds=[guild]), guild, member)
    assert hasil and all(item.get("role_id") in (None, 0) for item in hasil)


@pytest.mark.asyncio
async def test_proses_lencana_abaikan_lencana_mati():
    from cogs.lencana_cog import proses_lencana

    achievements.set_config(1, enabled=False)
    _member(1, 5, pesan=20000)
    member = SimpleNamespace(id=5, display_name="A", mention="<@5>", roles=[], bot=False)
    guild = SimpleNamespace(id=1, name="S", get_role=lambda rid: None, get_channel=lambda cid: None)
    assert await proses_lencana(SimpleNamespace(), guild, member) == []


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def test_panel_lencana_terpasang_di_halaman_inti():
    assert web_dashboard.ANCHOR_HALAMAN["p-lencana"] == "inti"
    halaman = {h["slug"]: h for h in web_dashboard.HALAMAN}
    assert "p-lencana" in halaman["inti"]["panel"]
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["lencana"] == "inti"
    assert dashboard_uji.ANCHOR_UJI["lencana"] == "p-lencana"


def test_panel_lencana_render_dan_bisa_dikontrol():
    achievements.set_config(1, enabled=True, channel_id=10)
    achievements.set_reward(1, "chat", 2, 555)
    _member(1, 7, pesan=260, level=9)
    achievements.cek_member(1, 7)

    html = dashboard_lencana.render_lencana_block(SimpleNamespace(), 1, "tok")
    assert "p-lencana" in html
    assert 'action="/api/lencana"' in html
    assert "lencana-setelan" in html and "lencana-role" in html
    assert "lencana-hapus:chat:2" in html
    assert "Rajin Ngobrol" in html and "Penghuni Voice" in html
    assert "15,000" in html  # ambang ditulis dengan pemisah ribuan
    assert "&lt;@&amp;555&gt;" in html
    assert "lencana off" not in html


def test_panel_lencana_tanpa_guild_tetap_render():
    html = dashboard_lencana.render_lencana_block(None, 0, "tok")
    assert "p-lencana" in html and "tidak tersedia" not in html


@pytest.mark.asyncio
async def test_aksi_lencana_setelan():
    ok, pesan = await dashboard_lencana.aksi_lencana(
        1, "lencana-setelan", {"enabled": "0", "channel_id": "12"}
    )
    assert ok and "nonaktif" in pesan and "#12" in pesan
    assert achievements.peek_config(1)["enabled"] is False
    assert achievements.peek_config(1)["channel_id"] == 12

    ok, pesan = await dashboard_lencana.aksi_lencana(
        1, "lencana-setelan", {"enabled": "1", "channel_id": "0"}
    )
    assert ok and "aktif" in pesan and "dimatikan" in pesan
    assert achievements.peek_config(1)["channel_id"] is None


@pytest.mark.asyncio
async def test_aksi_lencana_role_dan_hapus():
    ok, pesan = await dashboard_lencana.aksi_lencana(
        1, "lencana-role", {"kunci": "voice", "tingkat": "2", "role_id": "640"}
    )
    assert ok and achievements.role_for(1, "voice", 2) == 640

    ok, pesan = await dashboard_lencana.aksi_lencana(1, "lencana-hapus:voice:2", {})
    assert ok and achievements.role_for(1, "voice", 2) == 0

    ok, pesan = await dashboard_lencana.aksi_lencana(
        1, "lencana-role", {"kunci": "entah", "tingkat": "1", "role_id": "5"}
    )
    assert ok is False and "tidak dikenal" in pesan
    ok, pesan = await dashboard_lencana.aksi_lencana(1, "lencana-entah", {})
    assert ok is False and "tidak dikenal" in pesan


def test_uji_lencana_masuk_registry_dan_simulasi():
    kunci = [item["kunci"] for item in dashboard_uji.UJI]
    assert "lencana" in kunci
    entri = next(item for item in dashboard_uji.UJI if item["kunci"] == "lencana")
    assert entri["emoji"] == "🏅" and entri["grup"] == "Level & XP"

    achievements.set_config(1, enabled=False)
    ok, pesan = dashboard_uji._uji_lencana(1, None)
    assert ok is False and "dimatikan" in pesan

    achievements.set_config(1, enabled=True)
    _member(1, 7, pesan=260, level=9)
    achievements.cek_member(1, 7)
    ok, pesan = dashboard_uji._uji_lencana(1, None)
    assert ok is True and "Simulasi" in pesan

    orang = SimpleNamespace(id=7, display_name="Budi", name="Budi", global_name="Budi")
    ok, pesan = dashboard_uji._uji_lencana(1, orang)
    assert ok is True and "Progres" in pesan and "Simulasi" in pesan
    # simulasi tidak memberi role baru
    assert achievements.role_for(1, "chat", 1) == 0


@pytest.mark.asyncio
async def test_uji_lencana_lewat_jalankan_uji():
    _member(1, 7, pesan=260)
    achievements.cek_member(1, 7)
    guild = SimpleNamespace(id=1, name="S")
    bot = SimpleNamespace(get_guild=lambda gid: guild if gid == 1 else None)
    ok, pesan = await dashboard_uji.jalankan_uji(bot, 1, "lencana")
    assert ok is True and "Simulasi" in pesan
    ok, pesan = await dashboard_uji.jalankan_uji(
        bot, 1, "uji.lencana", SimpleNamespace(id=7, display_name="B")
    )
    assert ok is True and "B" in pesan


def test_hook_pertumbuhan_dan_main_memanggil_lencana():
    akar = Path(__file__).resolve().parent.parent
    src = (akar / "cogs" / "growth_cog.py").read_text(encoding="utf-8")
    assert src.count("proses_lencana") >= 2
    assert 'sumber="chat"' in src and 'sumber="voice"' in src
    utama = (akar / "main.py").read_text(encoding="utf-8")
    assert "await save_achievements_to_disk()" in utama
    assert "load_achievements_from_disk()" in utama
    assert "cleanup_achievements_runtime()" in utama
