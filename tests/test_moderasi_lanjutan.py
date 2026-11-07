"""Paket B#5: temp-ban otomatis dicabut, softban, catatan staff, & statistik staf.

Yang dikunci di sini:
* temp-ban punya tenggat (`expires_at`) & dicabut watcher, bukan menunggu staf;
* `/mod note` **tidak** menghukum siapa pun — hanya catatan internal;
* statistik menghitung tindakan (bukan catatan) & memisahkan aksi otomatis.
"""

from __future__ import annotations

import time

import pytest

import moderation as md

GID = 9501


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan():
    md.mod_cases.pop(GID, None)
    md.mod_settings.pop(GID, None)
    md.mod_tempbans.pop(GID, None)
    yield
    md.mod_cases.pop(GID, None)
    md.mod_settings.pop(GID, None)
    md.mod_tempbans.pop(GID, None)


class _Kanal:
    def __init__(self):
        self.kirim: list = []

    async def send(self, teks=None, **kwargs):
        self.kirim.append(teks)
        return None


class _Guild:
    def __init__(self, gid: int = GID):
        self.id = gid
        self.unban_calls: list = []
        self.kanal = _Kanal()
        self.gagal: Exception | None = None

    async def unban(self, user, reason: str = ""):
        if self.gagal is not None:
            raise self.gagal
        self.unban_calls.append((getattr(user, "id", user), reason))

    def get_channel(self, cid):
        return self.kanal


class _Bot:
    def __init__(self, guild: _Guild | None):
        self.guild = guild
        self.user = type("U", (), {"id": 999})()

    def get_guild(self, gid):
        return self.guild if self.guild and int(gid) == self.guild.id else None


# ==============================================================================
# TEMP-BAN
# ==============================================================================
def test_aksi_baru_punya_label_indonesia():
    for kunci in ("tempban", "softban", "note"):
        assert md.ACTIONS[kunci]["label"]
        assert md.ACTIONS[kunci]["emoji"]


def test_kasus_menyimpan_tenggat():
    sampai = time.time() + 3600
    case = md.add_case(GID, 42, 7, "tempban", "spam", duration_sec=3600, expires_at=sampai)
    assert case["expires_at"] == pytest.approx(sampai)
    assert md.get_case(GID, case["id"])["duration_sec"] == 3600
    assert md.add_case(GID, 43, 7, "ban", "iklan")["expires_at"] is None


def test_daftar_tempban_urut_dan_satu_per_member():
    md.add_tempban(GID, 42, case_id=1, until=time.time() + 900, oleh=7)
    md.add_tempban(GID, 43, case_id=2, until=time.time() + 300, oleh=7)
    md.add_tempban(GID, 42, case_id=3, until=time.time() + 60, oleh=8)  # menimpa yang lama

    daftar = md.list_tempbans(GID)
    assert [e["user_id"] for e in daftar] == [42, 43]
    assert daftar[0]["case_id"] == 3
    assert md.due_tempbans() == []


def test_tempban_kedaluwarsa_dan_pembersihan():
    md.add_tempban(GID, 42, case_id=1, until=time.time() - 5)
    assert len(md.due_tempbans()) == 1
    md.add_tempban(GID, 43, case_id=2, until=time.time() + 60)
    assert md.cleanup_tempbans() == 1
    assert [e["user_id"] for e in md.list_tempbans(GID)] == [43]
    assert md.drop_tempban(GID, 43) is True
    assert md.drop_tempban(GID, 43) is False
    assert md.list_tempbans(GID) == []


@pytest.mark.asyncio
async def test_watcher_mencabut_ban_dan_mencatat_kasus_unban(monkeypatch):
    disimpan: list = []

    async def _catat():
        disimpan.append(True)

    monkeypatch.setattr(md, "save_moderation_to_disk", _catat)
    md.set_settings(GID, log_channel=555)
    md.add_tempban(GID, 42, case_id=1, until=time.time() - 1, oleh=7)
    guild = _Guild()
    jumlah = await md.run_tempban_check(_Bot(guild))

    assert jumlah == 1
    assert guild.unban_calls and guild.unban_calls[0][0] == 42
    assert md.list_tempbans(GID) == []
    kasus = md.list_cases(GID, 42)
    assert kasus[0]["action"] == "unban"
    assert "otomatis" in kasus[0]["reason"].lower()
    assert disimpan and guild.kanal.kirim  # laporan ikut dikirim ke channel log


@pytest.mark.asyncio
async def test_watcher_tidak_bekerja_bila_belum_jatuh_tempo(monkeypatch):
    async def _catat():  # pragma: no cover - tidak boleh dipanggil
        raise AssertionError("tidak perlu menyimpan bila tidak ada yang dicabut")

    monkeypatch.setattr(md, "save_moderation_to_disk", _catat)
    md.add_tempban(GID, 42, case_id=1, until=time.time() + 3600)
    guild = _Guild()
    assert await md.run_tempban_check(_Bot(guild)) == 0
    assert guild.unban_calls == []
    assert md.list_tempbans(GID) != []


@pytest.mark.asyncio
async def test_watcher_membersihkan_bila_member_sudah_tidak_diban(monkeypatch):
    import discord

    async def _catat():
        return None

    monkeypatch.setattr(md, "save_moderation_to_disk", _catat)
    md.add_tempban(GID, 42, case_id=1, until=time.time() - 1)
    guild = _Guild()
    guild.gagal = discord.NotFound.__new__(discord.NotFound)
    assert await md.run_tempban_check(_Bot(guild)) == 0
    # Tidak dicoba terus-menerus: entri dibuang walau unban gagal karena sudah tidak diban.
    assert md.list_tempbans(GID) == []


@pytest.mark.asyncio
async def test_watcher_menahan_entri_bila_izin_kurang(monkeypatch):
    import discord

    async def _catat():
        return None

    monkeypatch.setattr(md, "save_moderation_to_disk", _catat)
    md.add_tempban(GID, 42, case_id=1, until=time.time() - 1)
    guild = _Guild()
    guild.gagal = discord.Forbidden.__new__(discord.Forbidden)
    assert await md.run_tempban_check(_Bot(guild)) == 0
    assert len(md.list_tempbans(GID)) == 1  # dicoba lagi di putaran berikutnya


@pytest.mark.asyncio
async def test_watcher_mengabaikan_server_yang_tidak_dikenal():
    md.add_tempban(GID, 42, case_id=1, until=time.time() - 1)
    assert await md.run_tempban_check(_Bot(None)) == 0
    assert len(md.list_tempbans(GID)) == 1


# ==============================================================================
# PENCARIAN & STATISTIK
# ==============================================================================
def test_pencarian_kasus():
    md.add_case(GID, 42, 7, "ban", "menyebar iklan judi")
    md.add_case(GID, 43, 8, "warn", "spam link")
    md.add_case(GID, 42, 8, "note", "pernah minta maaf")

    assert [c["user_id"] for c in md.search_cases(GID, q="judi")] == [42]
    assert [c["action"] for c in md.search_cases(GID, user_id=42)] == ["note", "ban"]
    assert [c["action"] for c in md.search_cases(GID, aksi="warn")] == ["warn"]
    assert [c["id"] for c in md.search_cases(GID, q="#1")] == [1]
    assert md.search_cases(GID, q="tidak-ada") == []
    assert len(md.search_cases(GID, limit=2)) == 2


def test_statistik_staf_memisahkan_otomatis_dan_catatan():
    md.add_case(GID, 42, 7, "ban", "iklan")
    md.add_case(GID, 43, 7, "warn", "spam")
    md.add_case(GID, 43, 8, "timeout", "spam lagi")
    md.add_case(GID, 44, 0, "timeout", "auto-punish")
    md.add_case(GID, 44, 7, "note", "catatan saja")

    data = md.staff_stats(GID)
    assert data["total"] == 4  # catatan staff tidak dihitung
    assert data["otomatis"] == 1
    assert data["per_aksi"]["ban"] == 1
    papan = {d["moderator_id"]: d["total"] for d in data["moderator"]}
    assert papan == {7: 2, 8: 1, 0: 1}


def test_statistik_bisa_dibatasi_rentang_hari():
    lama = md.add_case(GID, 42, 7, "ban", "lama")
    lama["created_at"] -= 20 * 86400
    md.add_case(GID, 43, 7, "warn", "baru")

    assert md.staff_stats(GID, days=7)["total"] == 1
    assert md.staff_stats(GID, days=30)["total"] == 2
    assert md.staff_stats(GID, days=7)["moderator"][0]["moderator_id"] == 7


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
@pytest.mark.asyncio
async def test_tempban_ikut_tersimpan_dan_dimuat(monkeypatch, tmp_path):
    berkas = tmp_path / "moderation.json"
    monkeypatch.setattr(md, "MODERATION_FILE", berkas)

    until = time.time() + 7200
    case = md.add_case(GID, 42, 7, "tempban", "spam", duration_sec=7200, expires_at=until)
    md.add_tempban(GID, 42, case_id=case["id"], until=until, oleh=7, reason="spam")
    await md.save_moderation_to_disk()

    md.mod_cases.clear()
    md.mod_settings.clear()
    md.mod_tempbans.clear()
    md.load_moderation_from_disk()

    assert md.get_case(GID, case["id"])["expires_at"] == pytest.approx(until)
    daftar = md.list_tempbans(GID)
    assert daftar and daftar[0]["user_id"] == 42
    assert daftar[0]["until"] == pytest.approx(until)


def test_command_moderasi_baru_terdaftar():
    from cogs.moderation_cog import mod_group

    nama = {c.name for c in mod_group.commands}
    assert {"tempban", "softban", "note", "statistik"} <= nama
    deskripsi = {c.name: c.description for c in mod_group.commands}
    assert "otomatis" in deskripsi["tempban"].lower()
