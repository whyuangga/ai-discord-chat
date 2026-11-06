"""Uji jadwal berulang (`setiap N jam`) untuk pengumuman terjadwal."""

from __future__ import annotations

import time

import pytest

import engagement as e


@pytest.fixture(autouse=True)
def _bersih():
    e.announcements.clear()
    yield
    e.announcements.clear()


@pytest.mark.parametrize(
    "teks, menit",
    [
        ("setiap 2 jam", 120),
        ("tiap 3 jam", 180),
        ("setiap 2j", 120),
        ("interval 1440 menit", 1440),
        ("SETIAP 8 JAM", 480),
        ("setiap 168 jam", e.MAX_INTERVAL_MINUTES),
    ],
)
def test_parse_interval_valid(teks, menit):
    spec = e.parse_announcement_schedule(teks)
    assert spec is not None and spec["kind"] == "interval"
    assert spec["interval_minutes"] == menit


@pytest.mark.parametrize(
    "teks", ["setiap 1 jam", "setiap 30 menit", "setiap 3 hari", "setiap", "setiap 999 jam"]
)
def test_parse_interval_ditolak(teks):
    assert e.parse_announcement_schedule(teks) is None


def test_parse_format_lama_tetap_jalan():
    assert e.parse_announcement_schedule("08:00")["kind"] == "harian"
    assert e.parse_announcement_schedule("senin 19:00")["kind"] == "mingguan"
    assert e.parse_announcement_schedule("sekali 31-12-2026 23:59")["kind"] == "sekali"


def test_compute_next_run_interval_menambah_interval():
    spec = e.parse_announcement_schedule("setiap 3 jam")
    hasil = e.compute_next_run(spec)
    assert abs(hasil - (time.time() + 3 * 3600)) < 5


def test_advance_interval_tidak_menumpuk_kiriman():
    awal = 1_000_000.0
    # Bot mati 2 hari: semua jadwal yang lewat dilewati, hanya satu titik berikutnya.
    hasil = e.advance_interval_next_run(180, awal, now=awal + 2 * 86400)
    assert hasil > awal + 2 * 86400
    assert (hasil - awal) % (180 * 60) == 0


def test_advance_interval_belum_waktunya():
    awal = 2_000_000.0
    assert e.advance_interval_next_run(120, awal, now=awal - 10) == awal


def test_describe_interval():
    assert e.describe_announcement({"kind": "interval", "interval_minutes": 180}) == "setiap 3 jam"
    assert (
        e.describe_announcement({"kind": "interval", "interval_minutes": 150})
        == "setiap 2 jam 30 menit"
    )


def test_add_dan_update_menyimpan_interval():
    spec = e.parse_announcement_schedule("setiap 4 jam")
    status, cfg = e.add_announcement(1, 2, "Halo", spec)
    assert status == "ok"
    assert cfg["kind"] == "interval" and cfg["interval_minutes"] == 240

    baru = e.parse_announcement_schedule("setiap 6 jam")
    status, cfg = e.update_announcement(cfg["id"], 1, spec=baru)
    assert status == "ok" and cfg["interval_minutes"] == 360

    harian = e.parse_announcement_schedule("08:00")
    _, cfg = e.update_announcement(cfg["id"], 1, spec=harian)
    assert cfg["kind"] == "harian" and cfg["interval_minutes"] == 0


def test_load_merapikan_interval_rusak(tmp_path, monkeypatch):
    import json

    berkas = tmp_path / "engagement.json"
    berkas.write_text(
        json.dumps(
            {
                "announcements": {
                    "1": {"content": "A", "kind": "interval", "interval_minutes": 5},
                    "2": {"content": "B", "kind": "interval", "interval_minutes": 0},
                    "3": {"content": "C", "kind": "interval", "interval_minutes": 99999},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(e, "ENGAGEMENT_FILE", berkas)
    monkeypatch.setattr(e, "DATA_DIR", tmp_path)
    assert e.load_engagement_from_disk()[3] == 3

    a = e.announcements[1]
    assert a["interval_minutes"] == e.MIN_INTERVAL_MINUTES       # dinaikkan ke batas minimum
    assert e.announcements[2]["kind"] == "harian"                # 0 → kembali harian
    assert e.announcements[3]["interval_minutes"] == e.MAX_INTERVAL_MINUTES


@pytest.mark.asyncio
async def test_check_menggeser_jadwal_interval(monkeypatch):
    class FakeChannel:
        mention = "<#2>"

        def __init__(self):
            self.terkirim = []

        async def send(self, *args, **kwargs):
            self.terkirim.append(kwargs)

    class FakeBot:
        def __init__(self, channel):
            self.channel = channel

        def get_channel(self, cid):
            return self.channel if int(cid) == 2 else None

    async def _tanpa_simpan():
        return None

    monkeypatch.setattr(e, "save_engagement_to_disk", _tanpa_simpan)

    channel = FakeChannel()
    spec = e.parse_announcement_schedule("setiap 2 jam")
    _, cfg = e.add_announcement(1, 2, "Halo", spec)
    cfg["next_run_at"] = time.time() - 60          # jadwalnya baru lewat

    terkirim = await e.run_announcement_check(FakeBot(channel))

    assert terkirim == 1 and len(channel.terkirim) == 1
    assert cfg["enabled"] is True                   # interval tidak pernah berhenti
    assert cfg["next_run_at"] > time.time()
