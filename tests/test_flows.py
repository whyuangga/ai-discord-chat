"""Uji alur aksi tombol (`flows.py`) — parser, sanitasi, dan penjalanan."""

from __future__ import annotations

import pytest

import flows


# ------------------------------------------------------------------------------
# PARSER
# ------------------------------------------------------------------------------
def test_parse_contoh_lengkap():
    langkah, galat = flows.parse(
        "+role:123 > pesan:Halo {member.mention}! > tunggu:2 > thread:tiket-{member.name}"
    )
    assert galat == []
    assert [s["action"] for s in langkah] == [
        flows.ACTION_ROLE_ADD,
        flows.ACTION_SAY,
        flows.ACTION_WAIT,
        flows.ACTION_THREAD,
    ]
    assert langkah[1]["ephemeral"] is True
    assert langkah[2]["seconds"] == 2.0


def test_parse_toggle_umum_stop_dan_syarat():
    langkah, galat = flows.parse("syarat:9 > role:9 > umum:Selamat datang > stop:Selesai")
    assert galat == []
    assert langkah[0] == {"action": flows.ACTION_REQUIRE_ROLE, "role_id": 9}
    assert langkah[1] == {"action": flows.ACTION_ROLE_TOGGLE, "role_id": 9}
    assert langkah[2]["ephemeral"] is False
    assert langkah[3]["text"] == "Selesai"


def test_parse_menerima_mention_role():
    langkah, _ = flows.parse("+role:<@&123456789012345678>")
    assert langkah[0]["role_id"] == 123456789012345678


def test_pemisah_bisa_di_escape():
    langkah, galat = flows.parse(r"pesan:5 \> 3 itu benar")
    assert galat == []
    assert langkah[0]["text"] == "5 > 3 itu benar"


@pytest.mark.parametrize(
    "teks, potongan_galat",
    [
        ("", "masih kosong"),
        ("terbang:1", "tidak dikenal"),
        ("+role:abc", "butuh ID role"),
        ("pesan:", "butuh teks"),
        ("thread:", "butuh nama thread"),
        ("tunggu:abc", "butuh angka"),
        ("tunggu:0", "antara 1"),
        ("tunggu:99", "antara 1"),
    ],
)
def test_parse_menolak_masukan_salah(teks, potongan_galat):
    langkah, galat = flows.parse(teks)
    assert galat and any(potongan_galat in g for g in galat), galat


def test_parse_membatasi_jumlah_langkah():
    teks = " > ".join(["pesan:halo"] * (flows.MAX_STEPS + 1))
    langkah, galat = flows.parse(teks)
    assert langkah == []
    assert any("maksimal" in g for g in galat)


def test_parse_memotong_teks_panjang():
    langkah, _ = flows.parse("pesan:" + "a" * 2000)
    assert len(langkah[0]["text"]) == flows.MAX_TEXT


# ------------------------------------------------------------------------------
# SANITASI & TAMPILAN
# ------------------------------------------------------------------------------
def test_sanitize_menolak_data_dari_disk_yang_aneh():
    bersih = flows.sanitize_steps(
        [
            "bukan dict",
            {"action": "hack"},
            {"action": flows.ACTION_ROLE_ADD, "role_id": 0},
            {"action": flows.ACTION_SAY, "text": ""},
            {"action": flows.ACTION_WAIT, "seconds": 999},
            {"action": flows.ACTION_ROLE_ADD, "role_id": 7},
            {"action": flows.ACTION_SAY, "text": "Halo", "ephemeral": False},
        ]
    )
    assert bersih == [
        {"action": flows.ACTION_ROLE_ADD, "role_id": 7},
        {"action": flows.ACTION_SAY, "text": "Halo", "ephemeral": False},
    ]
    assert flows.sanitize_steps("bukan list") == []


def test_to_text_dan_describe():
    langkah, _ = flows.parse("+role:5 > pesan:Halo > tunggu:3 > stop")
    teks = flows.to_text(langkah)
    assert teks == "+role:5 > pesan:Halo > tunggu:3.0 > stop"
    baris = flows.describe(langkah, {5: "Member"})
    assert baris[0].startswith("➕ beri @Member")
    assert any("⏳" in b for b in baris)
    assert flows.describe([]) == ["(alur kosong)"]


# ------------------------------------------------------------------------------
# PENJALANAN (dengan tiruan Interaction)
# ------------------------------------------------------------------------------
class FakeResponse:
    def __init__(self):
        self.sent: list[tuple[str, bool]] = []
        self.deferred = False
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, teks, ephemeral=False, **kwargs):
        self.sent.append((teks, ephemeral))
        self._done = True

    async def defer(self, ephemeral=False, thinking=False, **kwargs):
        self.deferred = True
        self._done = True


class FakeFollowup:
    def __init__(self):
        self.sent: list[tuple[str, bool]] = []

    async def send(self, teks, ephemeral=False, **kwargs):
        self.sent.append((teks, ephemeral))


class FakePerms:
    manage_roles = True


class FakeRole:
    def __init__(self, role_id, name="Member"):
        self.id = role_id
        self.name = name
        self.managed = False
        self.is_default = lambda: False

    def __ge__(self, other):  # dibandingkan dengan top_role bot
        return False


class FakeMember:
    def __init__(self, roles=()):
        self.id = 4001
        self.name = "budi"
        self.display_name = "Budi"
        self.mention = "<@4001>"
        self.bot = False
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


class FakeBotMember:
    guild_permissions = FakePerms()
    top_role = FakeRole(1, "Bot")


class FakeGuild:
    def __init__(self, roles):
        self.id = 999
        self.name = "Server Uji"
        self.roles = roles
        self.me = FakeBotMember()

    def get_role(self, role_id):
        return next((r for r in self.roles if r.id == role_id), None)


class FakeThread:
    id = 777


class FakeChannel:
    name = "panel"
    mention = "<#500>"
    id = 500

    def __init__(self):
        self.threads: list[str] = []

    async def create_thread(self, name, **kwargs):
        self.threads.append(name)
        return FakeThread()


class FakeInteraction:
    def __init__(self, member=None, guild=None, channel=None):
        self.user = member or FakeMember()
        self.guild = guild or FakeGuild([FakeRole(5, "Member")])
        self.channel = channel or FakeChannel()
        self.response = FakeResponse()
        self.followup = FakeFollowup()


@pytest.mark.asyncio
async def test_run_flow_beri_role_dan_kirim_pesan():
    interaction = FakeInteraction()
    hasil = await flows.run_flow(interaction, flows.parse("+role:5 > pesan:Halo {member.mention}")[0])

    assert hasil["roles"] == [5]
    assert interaction.user.added == [5]
    assert hasil.sent == 1
    teks, ephemeral = interaction.response.sent[0]
    assert teks == "Halo <@4001>"
    assert ephemeral is True


@pytest.mark.asyncio
async def test_run_flow_syarat_menghentikan_alur():
    role = FakeRole(9, "Staff")
    guild = FakeGuild([role])
    interaction = FakeInteraction(guild=guild)
    hasil = await flows.run_flow(interaction, flows.parse("syarat:9 > pesan:Tidak boleh")[0])

    assert hasil["stopped"] is True
    assert hasil.sent == 0
    assert interaction.response.sent == []


@pytest.mark.asyncio
async def test_run_flow_lanjut_bila_syarat_terpenuhi():
    role = FakeRole(9, "Staff")
    guild = FakeGuild([role])
    member = FakeMember(roles=[role])
    interaction = FakeInteraction(member=member, guild=guild)
    hasil = await flows.run_flow(interaction, flows.parse("syarat:9 > -role:9")[0])

    assert hasil["stopped"] is False
    assert hasil["roles"] == [9]
    assert member.removed == [9]


@pytest.mark.asyncio
async def test_run_flow_thread_memaksa_defer_dan_membuat_thread():
    interaction = FakeInteraction()
    hasil = await flows.run_flow(interaction, flows.parse("thread:tiket-{member.name}")[0])

    assert interaction.response.deferred is True
    assert interaction.channel.threads == ["tiket-budi"]
    assert hasil["threads"] == [777]


@pytest.mark.asyncio
async def test_run_flow_tunggu_lalu_pesan_lewat_followup():
    interaction = FakeInteraction()
    hasil = await flows.run_flow(interaction, flows.parse("tunggu:1 > pesan:Selesai")[0])

    assert interaction.response.deferred is True
    assert hasil.sent == 1
    assert interaction.followup.sent[0][0] == "Selesai"


@pytest.mark.asyncio
async def test_run_flow_stop_dengan_alasan():
    interaction = FakeInteraction()
    hasil = await flows.run_flow(interaction, flows.parse("stop:Belum waktunya")[0])

    assert hasil["stopped"] is True
    assert interaction.response.sent[0] == ("Belum waktunya", True)


@pytest.mark.asyncio
async def test_run_flow_alur_kosong_tidak_melempar():
    interaction = FakeInteraction()
    hasil = await flows.run_flow(interaction, [])
    assert hasil["errors"] == ["alur kosong"]
    assert interaction.response.sent == []
