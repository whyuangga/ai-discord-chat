"""Uji pemicu alur saat member bergabung (`flow_triggers.py`)."""

from __future__ import annotations

import pytest

import flow_triggers as ft
import flows


@pytest.fixture(autouse=True)
def _bersih(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ft, "FLOW_FILE", tmp_path / "flow_triggers.json")
    ft.triggers.clear()
    yield
    ft.triggers.clear()


class FakeRole:
    def __init__(self, role_id):
        self.id = role_id


class FakeMember:
    def __init__(self, roles=()):
        self.id = 4001
        self.bot = False
        self.display_name = "Budi"
        self.mention = "<@4001>"
        self.roles = list(roles)
        self.added: list[int] = []
        self.removed: list[int] = []

    async def add_roles(self, *roles, reason=None):
        for role in roles:
            self.roles.append(role)
            self.added.append(role.id)

    async def remove_roles(self, *roles, reason=None):
        for role in roles:
            if role in self.roles:
                self.roles.remove(role)
                self.removed.append(role.id)


class FakeChannel:
    id = 500
    mention = "<#500>"

    def __init__(self):
        self.sent: list[str] = []
        self.threads: list[str] = []

    async def send(self, teks, **kwargs):
        self.sent.append(teks)

    async def create_thread(self, name, **kwargs):
        self.threads.append(name)
        return type("T", (), {"id": 777})()


class FakeGuild:
    id = 999
    name = "Server Uji"

    def __init__(self, roles=()):
        self.roles = list(roles)
        self.channel = FakeChannel()

    def get_role(self, role_id):
        return next((r for r in self.roles if r.id == role_id), None)

    def get_channel(self, channel_id):
        return self.channel


def test_set_trigger_validasi():
    langkah, _ = flows.parse("+role:5 > umum:Halo {member.mention}")
    data, galat = ft.set_trigger(999, langkah, channel_id=500, min_age_days=3)
    assert galat == [] and data["steps"][0]["role_id"] == 5
    assert data["min_age_days"] == 3
    assert ft.get_trigger(999) is data

    kosong, galat2 = ft.set_trigger(999, [], channel_id=500)
    assert kosong is None and galat2

    tanpa_channel, galat3 = ft.set_trigger(999, langkah, channel_id=0)
    assert tanpa_channel is None and galat3


def test_umur_akun_minimal():
    import datetime as dt

    lama = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
    baru = dt.datetime.now(dt.timezone.utc)
    member_lama = FakeMember()
    member_lama.created_at = lama
    member_baru = FakeMember()
    member_baru.created_at = baru

    assert ft.akun_cukup_tua({"min_age_days": 0}, member_baru) is True
    assert ft.akun_cukup_tua({"min_age_days": 7}, member_baru) is False
    assert ft.akun_cukup_tua({"min_age_days": 7}, member_lama) is True


@pytest.mark.asyncio
async def test_run_join_flow_memberi_role_dan_mengirim_pesan(monkeypatch):
    role = FakeRole(5)
    guild = FakeGuild([role])
    member = FakeMember()
    langkah, _ = flows.parse("+role:5 > umum:Selamat datang {member.display_name}! > thread:sambutan")
    data, _ = ft.set_trigger(999, langkah, channel_id=500)

    hasil = await ft.run_join_flow(guild, member, data)

    assert member.added == [5]
    assert guild.channel.sent == ["Selamat datang Budi!"]
    assert guild.channel.threads == ["sambutan"]
    assert hasil["errors"] == [] and hasil["sent"] == 1


@pytest.mark.asyncio
async def test_run_join_flow_syarat_menghentikan_alur():
    guild = FakeGuild([FakeRole(9)])
    member = FakeMember()
    langkah, _ = flows.parse("syarat:9 > umum:Tidak boleh")
    data, _ = ft.set_trigger(999, langkah, channel_id=500)

    hasil = await ft.run_join_flow(guild, member, data)
    assert hasil["stopped"] is True
    assert guild.channel.sent == []


@pytest.mark.asyncio
async def test_handle_member_join_menghormati_umur_akun(monkeypatch):
    import datetime as dt

    member = FakeMember()
    member.created_at = dt.datetime.now(dt.timezone.utc)
    member.guild = FakeGuild([FakeRole(5)])
    langkah, _ = flows.parse("+role:5")
    ft.set_trigger(999, langkah, channel_id=500, min_age_days=30)

    assert await ft.handle_member_join(None, member) is None
    assert member.added == []


@pytest.mark.asyncio
async def test_simpan_dan_muat_pemicu():
    langkah, _ = flows.parse("+role:5")
    ft.set_trigger(999, langkah, channel_id=500, min_age_days=2)
    await ft.save_to_disk()

    ft.triggers.clear()
    assert ft.load_from_disk() == 1
    data = ft.get_trigger(999)
    assert data["channel_id"] == 500 and data["min_age_days"] == 2


def test_hapus_pemicu():
    langkah, _ = flows.parse("+role:5")
    ft.set_trigger(999, langkah, channel_id=500)
    assert ft.remove_trigger(999) is True
    assert ft.get_trigger(999) is None
    assert ft.remove_trigger(999) is False
