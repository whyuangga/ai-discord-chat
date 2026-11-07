"""Tes panel dashboard `/bangun`: pratinjau dulu, apply eksplisit, rollback tercatat."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import dashboard_bangun as db
import server_builder as sb

GID = 777123
TOKEN = "tok-bangun"


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    sb.reset_state()
    monkeypatch.setattr(sb, "BUILDER_FILE", tmp_path / "server_builder.json")

    async def _save():
        return None

    monkeypatch.setattr(sb, "save_to_disk", _save)
    yield
    sb.reset_state()


class _Guild:
    id = GID
    name = "Studio Uji"

    def __init__(self, *, channels=True, roles=True):
        self.me = SimpleNamespace(guild_permissions=SimpleNamespace(
            manage_channels=channels, manage_roles=roles
        ))


class _Bot:
    def __init__(self, guild=None):
        self.guilds = [guild] if guild else []

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == int(gid)), None)


def test_panel_memuat_semua_tema_dan_alur_pratinjau():
    bot = _Bot(_Guild())
    html = db.render_bangun_block(bot, GID, TOKEN)
    assert len(sb.daftar_tema()) == 15
    assert html.count("<option ") == 15
    assert 'action="/api/bangun"' in html
    assert "Rancang dengan AI" in html and "0 kuota AI" in html
    assert "Belum ada pratinjau" in html
    assert "Terapkan rencana ini" not in html

    snapshot = sb.tema_ke_snapshot("coding", nama_server="Studio Uji")
    sb.simpan_siap(GID, snapshot, sumber="tema:coding")
    html = db.render_bangun_block(bot, GID, TOKEN)
    assert "Pratinjau menunggu keputusan" in html
    assert "Terapkan rencana ini" in html and "Batalkan pratinjau" in html
    assert "Belum ada struktur yang dibuat" in html


@pytest.mark.asyncio
async def test_pilih_tema_hanya_menyimpan_pratinjau_tanpa_membuat_item():
    bot = _Bot(_Guild())
    ok, pesan = await db.proses_aksi(bot, GID, {"action": "tema", "tema": "gaming"})
    pending = sb.ambil_siap(GID)
    assert ok and "Belum ada item yang dibuat" in pesan
    assert pending["sumber"] == "tema:gaming"
    assert pending["snapshot"]["meta"]["guild_name"] == "Studio Uji"


@pytest.mark.asyncio
async def test_ai_gagal_jatuh_ke_tema_dan_tetap_minta_terapkan(monkeypatch):
    bot = _Bot(_Guild())

    async def _gagal(_gid, _prompt):
        return "layanan AI sedang tidak tersedia"

    monkeypatch.setattr(db, "_rancang_ai", _gagal)
    ok, pesan = await db.proses_aksi(
        bot, GID, {"action": "rancang", "deskripsi": "komunitas fotografi untuk pemula"}
    )
    assert ok and "Belum ada item yang dibuat" in pesan
    assert sb.ambil_siap(GID)["sumber"].startswith("tema:")


@pytest.mark.asyncio
async def test_apply_memerlukan_izin_bot_dan_menerapkan_hanya_rencana_pending(monkeypatch):
    snapshot = sb.tema_ke_snapshot("gaming")
    sb.simpan_siap(GID, snapshot, sumber="tema:gaming")
    tanpa_role = _Bot(_Guild(channels=True, roles=False))

    async def _apply(*args, **kwargs):
        pytest.fail("Tidak boleh menerapkan tanpa Manage Roles")

    monkeypatch.setattr(sb, "terapkan", _apply)
    ok, pesan = await db.proses_aksi(tanpa_role, GID, {"action": "terapkan"})
    assert not ok and "Manage Roles" in pesan
    assert sb.ambil_siap(GID) is not None

    bot = _Bot(_Guild())
    panggilan = {}

    async def _apply_ok(guild, plan, **kwargs):
        panggilan.update(guild=guild, snapshot=plan, kwargs=kwargs)
        return {"roles": 3, "categories": 3, "channels": 10, "errors": []}, "Dibuat"

    monkeypatch.setattr(sb, "terapkan", _apply_ok)
    ok, pesan = await db.proses_aksi(bot, GID, {"action": "terapkan"})
    assert ok and pesan == "Dibuat"
    assert panggilan["kwargs"]["actor_id"] == 0
    assert "dashboard" in panggilan["kwargs"]["alasan"]
    assert sb.ambil_siap(GID) is None


@pytest.mark.asyncio
async def test_bongkar_minta_konfirmasi_dan_hanya_panggil_rollback_tercatat(monkeypatch):
    sb.riwayat[GID] = {
        "label": "Coding", "dibuat": {"roles": ["Dev"], "categories": ["INFO"], "channels": ["umum"]}
    }
    bot = _Bot(_Guild())
    panggilan = []

    async def _bongkar(guild, *, gid=None):
        panggilan.append((guild, gid))
        return True, "Dihapus 3 item tercatat"

    monkeypatch.setattr(sb, "bongkar", _bongkar)
    ok, pesan = await db.proses_aksi(bot, GID, {"action": "bongkar"})
    assert not ok and "Centang konfirmasi" in pesan and not panggilan

    ok, pesan = await db.proses_aksi(bot, GID, {"action": "bongkar", "konfirmasi": "ya"})
    assert ok and "3 item tercatat" in pesan
    assert panggilan == [(bot.get_guild(GID), GID)]


@pytest.mark.asyncio
async def test_deskripsi_dan_guild_tidak_valid_ditolak():
    bot = _Bot(_Guild())
    ok, pesan = await db.proses_aksi(bot, GID, {"action": "rancang", "deskripsi": "hi"})
    assert not ok and "minimal 10" in pesan
    ok, pesan = await db.proses_aksi(bot, GID + 1, {"action": "tema", "tema": "gaming"})
    assert not ok and "tidak terhubung" in pesan


def test_pratinjau_mengescape_teks_dari_rencana_agar_tidak_jadi_html():
    snapshot = {
        "meta": {"label": "<script>alert(1)</script>"},
        "roles": [{"name": "<img src=x>"}],
        "categories": [{"name": "<script>"}],
        "channels": [{"name": "<b>umum</b>", "type": "text", "category": "<script>"}],
    }
    sb.simpan_siap(GID, snapshot, sumber="ai")
    out = db.render_bangun_block(_Bot(_Guild()), GID, TOKEN)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out and "&lt;img src=x&gt;" in out
    assert "&lt;b&gt;umum&lt;/b&gt;" in out
