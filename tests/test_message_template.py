"""Uji mesin variabel pesan (`message_template.py`)."""

from __future__ import annotations

from datetime import datetime, timezone

import message_template as mt


class FakeRole:
    def __init__(self, role_id: int):
        self.id = role_id


class FakeAvatar:
    url = "https://cdn.example/avatar.png"


class FakeMember:
    name = "budi"
    display_name = "Budi S."
    mention = "<@4001>"
    id = 4001
    bot = False
    display_avatar = FakeAvatar()
    created_at = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    joined_at = datetime(2025, 1, 5, 8, 30, tzinfo=timezone.utc)
    roles = [FakeRole(1), FakeRole(2), FakeRole(3)]


class FakeGuild:
    name = "Server Uji"
    id = 999
    member_count = 150
    premium_subscription_count = 3
    roles = [FakeRole(i) for i in range(1, 9)]
    icon = FakeAvatar()
    owner = FakeMember()
    created_at = datetime(2023, 5, 20, tzinfo=timezone.utc)


class FakeChannel:
    name = "umum"
    mention = "<#500>"
    id = 500


def test_variabel_member_dan_server_diisi():
    teks = mt.render(
        "Halo {member.mention} ({member.name}) — member ke-{server.members} di {server.name}",
        member=FakeMember(),
        guild=FakeGuild(),
    )
    assert teks == "Halo <@4001> (budi) — member ke-150 di Server Uji"


def test_alias_lama_tetap_dukung():
    """Pesan boost yang sudah ada memakai {user}, {name}, {guild}."""
    teks = mt.render(
        "Terima kasih {user} ({name}) sudah boost {guild}!",
        member=FakeMember(),
        guild=FakeGuild(),
    )
    assert teks == "Terima kasih <@4001> (Budi S.) sudah boost Server Uji!"


def test_token_tanpa_data_jadi_kosong():
    """Pengumuman terjadwal tidak punya konteks member — jangan bocorkan teks mentah."""
    teks = mt.render("Halo {member.name}, ini {server.name}", guild=FakeGuild())
    assert teks == "Halo , ini Server Uji"
    assert "{member.name}" not in teks


def test_token_typo_dibiarkan_dan_terdeteksi():
    teks = mt.render("Halo {member.nmae} di {server.name}", guild=FakeGuild())
    assert "{member.nmae}" in teks
    assert mt.unknown_tokens("Halo {member.nmae} {server.name} {now}") == ["{member.nmae}"]


def test_timestamp_pakai_format_discord():
    teks = mt.render("{member.created} {member.created_relative} {now}", member=FakeMember(), now=1_700_000_000)
    assert teks.startswith("<t:1709287200:f> <t:1709287200:R> <t:1700000000:f>")


def test_variabel_channel_dan_angka():
    teks = mt.render(
        "{channel.mention} / {channel.name} • boost {server.boosts} • role {server.roles}",
        guild=FakeGuild(),
        channel=FakeChannel(),
    )
    assert teks == "<#500> / umum • boost 3 • role 8"


def test_role_count_tanpa_everyone():
    assert mt.render("{member.role_count}", member=FakeMember()) == "2"


def test_teks_kosong_dan_none_aman():
    assert mt.render("") == ""
    assert mt.render(None) == ""  # type: ignore[arg-type]
    assert mt.render("{member.bot}") == ""
    assert mt.render("{member.bot}", member=FakeMember()) == "Tidak"


def test_batas_panjang_hasil():
    panjang = mt.render("{server.name}" * 200, guild=FakeGuild(), limit=100)
    assert len(panjang) == 100


def test_help_dan_check_memberi_peringatan():
    baris = mt.help_lines(mt.MEMBER_TOKENS)
    assert baris[0].startswith("`{member.name}`")
    assert len(baris) == len(mt.MEMBER_TOKENS)
    peringatan = mt.check("Halo {member.name} {ngawur}", member=None)
    assert any("tidak dikenal" in p for p in peringatan)
    assert any("butuh konteks member" in p for p in peringatan)
    assert mt.check("Halo {server.name}", guild=FakeGuild()) == []


def test_semua_token_terdaftar_unik():
    nama = [n for n, _ in mt.ALL_TOKENS]
    assert len(nama) == len(set(nama))
    assert mt.KNOWN_TOKENS == set(nama)
