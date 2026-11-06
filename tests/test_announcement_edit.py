"""Uji `/pengumuman kirim` & `/pengumuman ubah` (ubah tanpa hapus, kirim sekarang)."""

from __future__ import annotations

import pytest

import engagement


@pytest.fixture(autouse=True)
def _penyimpanan(tmp_path, monkeypatch):
    monkeypatch.setattr(engagement, "DATA_DIR", tmp_path)
    monkeypatch.setattr(engagement, "ENGAGEMENT_FILE", tmp_path / "engagement.json")
    engagement.announcements.clear()
    yield
    engagement.announcements.clear()


class FakeChannel:
    id = 900
    mention = "<#900>"

    def __init__(self):
        self.guild = None
        self.terkirim: list = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return object()


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel if int(channel_id) == self.channel.id else None


def _buat(jadwal: str = "08:00", guild_id: int = 55):
    spec = engagement.parse_announcement_schedule(jadwal)
    status, cfg = engagement.add_announcement(
        guild_id, 900, "Isi awal {server.name}", spec, title="Judul awal", tz_name="Asia/Jakarta"
    )
    assert status == "ok"
    return cfg


def test_ubah_isi_dan_judul_tanpa_menggeser_jadwal():
    cfg = _buat()
    jadwal_awal = cfg["next_run_at"]

    status, baru = engagement.update_announcement(
        cfg["id"], guild_id=55, content="Isi baru", title="Judul baru", tz_name="Asia/Jakarta"
    )
    assert status == "ok"
    assert baru["content"] == "Isi baru" and baru["title"] == "Judul baru"
    assert baru["next_run_at"] == jadwal_awal


def test_ubah_jadwal_menghitung_ulang_dan_mengaktifkan():
    cfg = _buat("08:00")
    cfg["enabled"] = False
    spec = engagement.parse_announcement_schedule("senin 19:00")

    status, baru = engagement.update_announcement(
        cfg["id"], guild_id=55, spec=spec, tz_name="Asia/Jakarta"
    )
    assert status == "ok"
    assert baru["kind"] == "mingguan" and baru["hour"] == 19
    assert baru["enabled"] is True
    assert baru["next_run_at"] > 0


def test_ubah_menolak_id_server_lain_dan_isi_kosong():
    cfg = _buat()
    assert engagement.update_announcement(cfg["id"], guild_id=999, content="x")[0] == "tidak_ada"
    assert engagement.update_announcement(cfg["id"], guild_id=55, content="   ")[0] == "kosong"
    assert engagement.announcements[cfg["id"]]["content"] == "Isi awal {server.name}"
    assert engagement.update_announcement(123456, guild_id=55)[0] == "tidak_ada"


@pytest.mark.asyncio
async def test_kirim_sekarang_mengirim_embed_dan_tidak_menggeser_jadwal():
    cfg = _buat("08:00")
    jadwal_awal = cfg["next_run_at"]
    channel = FakeChannel()

    status, terkirim_cfg = await engagement.send_announcement_now(
        FakeBot(channel), cfg["id"], guild_id=55
    )

    assert status == "ok"
    assert len(channel.terkirim) == 1
    embed = channel.terkirim[0]["embed"]
    assert embed.description == "Isi awal "  # {server.name} kosong tanpa konteks guild
    assert terkirim_cfg["last_sent_at"] > 0
    assert terkirim_cfg["next_run_at"] == jadwal_awal
    assert terkirim_cfg["enabled"] is True


@pytest.mark.asyncio
async def test_kirim_sekarang_untuk_jadwal_sekali_menonaktifkan():
    cfg = _buat("sekali 31-12-2026 23:59")
    channel = FakeChannel()

    status, baru = await engagement.send_announcement_now(FakeBot(channel), cfg["id"], guild_id=55)

    assert status == "ok"
    assert baru["enabled"] is False and baru["next_run_at"] == 0.0


@pytest.mark.asyncio
async def test_kirim_sekarang_gagal_bila_channel_hilang():
    cfg = _buat()

    class BotKosong:
        def get_channel(self, channel_id):
            return None

    status, _ = await engagement.send_announcement_now(BotKosong(), cfg["id"], guild_id=55)
    assert status == "channel"
    assert engagement.announcements[cfg["id"]]["last_sent_at"] == 0.0


def test_embed_pengumuman_merender_variabel_server():
    cfg = _buat()

    class Guild:
        name = "Server Uji"
        id = 55
        member_count = 150
        premium_subscription_count = 0
        roles = []
        icon = None
        created_at = None

    embed = engagement.build_announcement_embed(cfg, guild=Guild())
    assert embed.description == "Isi awal Server Uji"


@pytest.mark.parametrize(
    "teks, kind, weekday",
    [
        ("08:00", "harian", 0),
        ("harian 20:30", "harian", 0),
        # regresi: nama hari tanpa kata "mingguan" dulu dianggap HARIAN
        ("senin 19:00", "mingguan", 0),
        ("mingguan sabtu 20:30", "mingguan", 5),
        ("selasa 07:15", "mingguan", 1),
    ],
)
def test_jadwal_nama_hari_tanpa_kata_mingguan(teks, kind, weekday):
    spec = engagement.parse_announcement_schedule(teks)
    assert spec is not None
    assert spec["kind"] == kind
    assert spec["weekday"] == weekday


def test_jadwal_mingguan_wajib_menyebut_hari():
    assert engagement.parse_announcement_schedule("mingguan 08:00") is None
