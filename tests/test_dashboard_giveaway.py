"""Uji kendali giveaway dari dashboard: daftar, buat, hentikan, reroll, & template.

Dashboard memakai fungsi yang sama dengan command Discord (`engagement.py`), jadi
tes ini memastikan tidak ada jalur kedua: syarat, bobot, dan riwayat tetap satu
sumber, dan setiap tombol hanya bisa memanggil aksi yang ada di whitelist.
"""

from __future__ import annotations

import pytest

import dashboard_giveaway as dg
import dashboard_ui as ui
import engagement

GID = 1234
TOKEN = "tok-giveaway"


# ==============================================================================
# PERKAKAS
# ==============================================================================
class _Pesan:
    def __init__(self, mid: int):
        self.id = mid
        self.diedit: list[dict] = []

    async def edit(self, **kwargs):
        self.diedit.append(kwargs)
        return self


class _Channel:
    def __init__(self, cid: int = 700):
        self.id = cid
        self.terkirim: list[dict] = []
        self.pesan: dict[int, _Pesan] = {}

    async def send(self, content=None, **kwargs):
        self.terkirim.append({"content": content, **kwargs})
        mid = 9000 + len(self.terkirim)
        self.pesan[mid] = _Pesan(mid)
        return self.pesan[mid]

    def get_partial_message(self, mid: int):
        return self.pesan.setdefault(int(mid), _Pesan(int(mid)))


class _Bot:
    def __init__(self, channel=None):
        self._channel = channel

    def get_channel(self, cid):
        return self._channel if int(cid) == getattr(self._channel, "id", -1) else None


@pytest.fixture(autouse=True)
def _bersihkan():
    engagement.giveaways.clear()
    engagement.giveaway_templates.clear()
    engagement.giveaway_defaults.clear()
    yield
    engagement.giveaways.clear()
    engagement.giveaway_templates.clear()
    engagement.giveaway_defaults.clear()


def _buat(message_id: int = 500, **kwargs) -> dict:
    dasar = dict(
        guild_id=GID,
        channel_id=700,
        message_id=message_id,
        prize="Nitro 1 Bulan",
        host_id=1,
        seconds=3600,
    )
    dasar.update(kwargs)
    return engagement.create_giveaway(**dasar)


# ==============================================================================
# RINGKASAN
# ==============================================================================
def test_collect_giveaway_ringkas_dan_terpisah_aktif_selesai():
    _buat(500, requirements={"level": 5}, bonus_roles={99: 2})
    engagement.join_giveaway(500, 501, level=9, account_age_days=100)
    _buat(501, prize="Pulsa 10rb")
    engagement.end_giveaway(501)

    data = dg.collect(GID)
    assert len(data["aktif"]) == 1 and len(data["selesai"]) == 1
    aktif = data["aktif"][0]
    assert aktif["hadiah"] == "Nitro 1 Bulan" and aktif["peserta"] == 1
    assert "Level minimal" in aktif["syarat"]
    assert data["selesai"][0]["selesai"] is True
    # Server lain tidak ikut terbawa
    assert dg.collect(9999)["aktif"] == []
    # Ringkasan selalu punya kunci setelan bawaan walau kosong
    assert data["bawaan"]["seconds"] == 3600


# ==============================================================================
# SETELAN BAWAAN & TEMPLATE
# ==============================================================================
@pytest.mark.asyncio
async def test_aksi_setelan_bawaan_dan_template():
    ok, pesan = await dg.aksi(
        _Bot(),
        GID,
        "simpan-bawaan",
        {"menit": "90", "pemenang": "3", "level": "4", "umur": "30",
         "role_bonus": "99", "bobot": "2", "ping": "on"},
    )
    assert ok is True and "Setelan" in pesan
    bawaan = engagement.default_giveaway_config(GID)
    assert bawaan["seconds"] == 5400 and bawaan["winner_count"] == 3
    assert bawaan["level"] == 4 and bawaan["account_age_days"] == 30
    assert bawaan["bonus_role_id"] == 99 and bawaan["bonus_weight"] == 2
    assert bawaan["ping_everyone"] is True

    ok, pesan = await dg.aksi(
        _Bot(), GID, "template-simpan",
        {"nama": "Nitro bulanan", "menit": "60", "pemenang": "2", "level": "5", "umur": "7"},
    )
    assert ok is True and "disimpan" in pesan
    tpl = engagement.get_giveaway_template(GID, "nitro bulanan")
    assert tpl["winner_count"] == 2 and tpl["requirements"]["level"] == 5

    ok, pesan = await dg.aksi(_Bot(), GID, "template-hapus", {"nama": "Nitro bulanan"})
    assert ok is True and "dihapus" in pesan
    ok_gagal, pesan_gagal = await dg.aksi(_Bot(), GID, "template-hapus", {"nama": "Nitro bulanan"})
    assert ok_gagal is False and "tidak ditemukan" in pesan_gagal
    # Template tanpa nama ditolak dengan pesan jelas
    ok_kosong, pesan_kosong = await dg.aksi(_Bot(), GID, "template-simpan", {"nama": "  "})
    assert ok_kosong is False and "kosong" in pesan_kosong


@pytest.mark.asyncio
async def test_aksi_tidak_dikenal_ditolak():
    ok, pesan = await dg.aksi(_Bot(), GID, "hapus-semua", {})
    assert ok is False and "tidak dikenal" in pesan


# ==============================================================================
# BUAT → HENTIKAN → REROLL
# ==============================================================================
@pytest.mark.asyncio
async def test_aksi_buat_hentikan_dan_reroll_dari_dashboard():
    channel = _Channel(700)
    bot = _Bot(channel)

    ok, pesan = await dg.aksi(
        bot, GID, "buat",
        {"hadiah": "Nitro 1 Bulan", "channel": "700", "menit": "10", "pemenang": "1",
         "level": "3", "umur": "0"},
    )
    assert ok is True and "dipasang" in pesan
    assert channel.terkirim and "embed" in channel.terkirim[0]
    message_id = next(iter(engagement.giveaways))
    cfg = engagement.giveaways[message_id]
    assert cfg["prize"] == "Nitro 1 Bulan" and cfg["requirements"]["level"] == 3
    assert cfg["ends_at"] > 0

    # Tanpa channel → ditolak, tidak ada giveaway nyasar
    ok_nol, pesan_nol = await dg.aksi(bot, GID, "buat", {"hadiah": "X", "channel": "0"})
    assert ok_nol is False and "channel" in pesan_nol.lower()

    engagement.join_giveaway(message_id, 501, level=9, account_age_days=100)
    engagement.join_giveaway(message_id, 502, level=9, account_age_days=100)

    ok_henti, pesan_henti = await dg.aksi(bot, GID, f"akhiri:{message_id}", {})
    assert ok_henti is True and "Pemenang" in pesan_henti
    assert engagement.giveaways[message_id]["ended"] is True
    assert engagement.giveaway_history(message_id)[-1]["aksi"] == "akhir"
    pesan_discord = channel.get_partial_message(message_id)
    assert pesan_discord.diedit, "pesan giveaway harus diperbarui setelah dihentikan"

    # Menghentikan dua kali ditolak dengan saran reroll
    ok_ulang, pesan_ulang = await dg.aksi(bot, GID, f"akhiri:{message_id}", {})
    assert ok_ulang is False and "sudah selesai" in pesan_ulang

    ok_reroll, pesan_reroll = await dg.aksi(bot, GID, f"reroll:{message_id}", {})
    assert ok_reroll is True and "diundi ulang" in pesan_reroll
    assert engagement.giveaway_history(message_id)[-1]["aksi"] == "reroll"

    # Giveaway server lain tidak boleh disentuh dari dashboard server ini
    ok_lain, _ = await dg.aksi(bot, 9999, f"reroll:{message_id}", {})
    assert ok_lain is False


@pytest.mark.asyncio
async def test_reroll_ditolak_saat_masih_berjalan():
    _buat(510)
    engagement.join_giveaway(510, 501)
    ok, pesan = await dg.aksi(_Bot(), GID, "reroll:510", {})
    assert ok is False and "masih berjalan" in pesan


# ==============================================================================
# RENDER HALAMAN
# ==============================================================================
def test_render_giveaway_block_memuat_form_dan_aman_di_escape():
    _buat(520, prize='Nitro <script>alert("x")</script>')
    engagement.join_giveaway(520, 501)
    data = dg.collect(GID)

    html = ui.render_giveaway_block(GID, data, TOKEN)
    assert 'action="/api/giveaway"' in html
    assert f'name="token" value="{TOKEN}"' in html
    assert "akhiri:520" in html
    assert "<script>" not in html, "nama hadiah harus di-escape"
    assert "&lt;script&gt;" in html

    # Tanpa bot (mis. cache kosong) tetap tergambar, dropdown berisi placeholder
    html_kosong = ui.render_giveaway_block(GID, dg.collect(9999), TOKEN)
    assert "Belum ada giveaway berjalan" in html_kosong
    assert "Belum ada template" in html_kosong


def test_halaman_giveaway_menempel_di_dashboard():
    import web_dashboard

    halaman = web_dashboard.HALAMAN_SLUG["giveaway"]
    assert halaman["panel"] == ("p-giveaway",)
    assert web_dashboard.ANCHOR_HALAMAN["p-giveaway"] == "giveaway"
    assert web_dashboard.UJI_HALAMAN["giveaway"] == ("giveaway",)

    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="giveaway", token=TOKEN, guild_id=GID
    )
    assert 'id="p-giveaway"' in page
    assert "Tes syarat giveaway" in page
