"""Uji dua langkah alur baru: `webhook:` (identitas sendiri) dan `hapus`."""

from __future__ import annotations

import pytest

import flows
import webhook_identity as wi


class FakeMessage:
    def __init__(self):
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeResponse:
    def __init__(self):
        self.sent: list[str] = []
        self.deferred = False

    def is_done(self) -> bool:
        return bool(self.sent or self.deferred)

    async def send_message(self, teks, ephemeral=False, **kwargs):
        self.sent.append(teks)

    async def defer(self, ephemeral=False, thinking=False, **kwargs):
        self.deferred = True


class FakeFollowup:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, teks, ephemeral=False, **kwargs):
        self.sent.append(teks)


class FakeUser:
    id = 4001
    display_name = "Budi"
    mention = "<@4001>"
    bot = False


class FakeChannel:
    id = 500
    mention = "<#500>"
    name = "umum"


class FakeGuild:
    id = 999
    name = "Server Uji"


class FakeInteraction:
    def __init__(self):
        self.user = FakeUser()
        self.guild = FakeGuild()
        self.channel = FakeChannel()
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = FakeMessage()

    async def original_response(self):
        return self.message


# ------------------------------------------------------------------------------
# PARSER
# ------------------------------------------------------------------------------
def test_parse_webhook_memakai_pipa():
    langkah, galat = flows.parse("webhook:📢 Pengumuman Server|Halo {member.mention}")
    assert galat == []
    assert langkah == [
        {"action": flows.ACTION_WEBHOOK, "name": "📢 Pengumuman Server", "text": "Halo {member.mention}"}
    ]


@pytest.mark.parametrize(
    "teks", ["webhook:", "webhook:hanya nama", "webhook:|tanpa nama", "webhook:nama|"]
)
def test_parse_webhook_tidak_valid(teks):
    langkah, galat = flows.parse(teks)
    assert langkah == [] and galat


def test_parse_hapus():
    langkah, galat = flows.parse("umum:Halo > tunggu:1 > hapus")
    assert galat == []
    assert langkah[-1] == {"action": flows.ACTION_DELETE}


def test_sanitize_membuang_webhook_kosong():
    bersih = flows.sanitize_steps(
        [
            {"action": flows.ACTION_WEBHOOK, "name": "", "text": "halo"},
            {"action": flows.ACTION_WEBHOOK, "name": "Tim", "text": "halo"},
            {"action": flows.ACTION_DELETE},
        ]
    )
    assert bersih == [
        {"action": flows.ACTION_WEBHOOK, "name": "Tim", "text": "halo"},
        {"action": flows.ACTION_DELETE},
    ]


def test_to_text_dan_describe():
    langkah, _ = flows.parse("webhook:Tim Event|Halo > hapus")
    assert flows.to_text(langkah) == "webhook:Tim Event|Halo > hapus"
    baris = flows.describe(langkah)
    assert "🎭" in baris[0] and "Tim Event" in baris[0]
    assert "🗑️" in baris[1]


def test_help_menyebut_langkah_baru():
    teks = "\n".join(flows.HELP_LINES)
    assert "webhook:<nama>|<teks>" in teks
    assert "`hapus`" in teks


# ------------------------------------------------------------------------------
# PENJALANAN
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_flow_webhook_mengirim_dengan_nama_sendiri(monkeypatch):
    terkirim: list[dict] = []

    async def fake_kirim(channel, *, nama, isi=None, **kwargs):
        terkirim.append({"channel": channel, "nama": nama, "isi": isi})
        return True, "ok"

    monkeypatch.setattr(wi, "kirim_sebagai", fake_kirim)

    interaction = FakeInteraction()
    langkah, _ = flows.parse("webhook:📢 Pengumuman|Halo {member.display_name}!")
    hasil = await flows.run_flow(interaction, langkah)

    assert hasil["sent"] == 1 and hasil["errors"] == []
    assert terkirim[0]["nama"] == "📢 Pengumuman"
    assert terkirim[0]["isi"] == "Halo Budi!"


@pytest.mark.asyncio
async def test_run_flow_webhook_ditolak_dicatat(monkeypatch):
    async def fake_kirim(channel, *, nama, isi=None, **kwargs):
        return False, "butuh izin Manage Webhooks"

    monkeypatch.setattr(wi, "kirim_sebagai", fake_kirim)

    langkah, _ = flows.parse("webhook:Tim|Halo")
    hasil = await flows.run_flow(FakeInteraction(), langkah)
    assert hasil["sent"] == 0
    assert any("Manage Webhooks" in e for e in hasil["errors"])


@pytest.mark.asyncio
async def test_run_flow_hapus_menghapus_balasan_bot():
    interaction = FakeInteraction()
    langkah, _ = flows.parse("umum:Pesan sementara > hapus")

    hasil = await flows.run_flow(interaction, langkah)

    assert interaction.response.sent == ["Pesan sementara"]
    assert interaction.message.deleted is True
    assert hasil["errors"] == []
