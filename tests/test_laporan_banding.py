"""Paket B#4 & B#6: `/lapor`, `/banding`, antrean staf, & halaman dashboard Moderasi.

Prinsip yang dikunci:
* laporan member **tidak** langsung menghukum siapa pun — masuk antrean dulu;
* banding terhubung ke **nomor kasus** dan bisa mencabut hukuman saat diterima;
* panel dashboard menampilkan antrean & bisa mengubah status **tanpa JavaScript**.
"""

from __future__ import annotations

import time

import pytest

import dashboard_moderasi
import moderation as md
import reports

GID = 9601
TOKEN = "tok-mod"


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan():
    reports.reset_runtime_state()
    dashboard_moderasi.reset()
    md.mod_cases.pop(GID, None)
    md.mod_settings.pop(GID, None)
    md.mod_tempbans.pop(GID, None)
    yield
    reports.reset_runtime_state()
    dashboard_moderasi.reset()
    md.mod_cases.pop(GID, None)
    md.mod_settings.pop(GID, None)
    md.mod_tempbans.pop(GID, None)


class _Member:
    def __init__(self, uid: int = 501, *, admin: bool = False):
        self.id = uid
        self.bot = False
        self.guild_permissions = md  # nilai apa pun; hanya dibaca oleh cog
        self.admin = admin
        self.timeout_calls: list = []

    async def timeout(self, durasi, reason: str = ""):
        self.timeout_calls.append((durasi, reason))


class _Guild:
    def __init__(self, gid: int = GID):
        self.id = gid
        self.unban_calls: list = []
        self.members: list = [_Member(501)]

    def get_member(self, uid):
        return next((m for m in self.members if m.id == int(uid)), None)

    async def unban(self, user, reason: str = ""):
        self.unban_calls.append((getattr(user, "id", user), reason))


class _Interaction:
    def __init__(self, uid: int = 900, guild: _Guild | None = None):
        self.user = _Member(uid)
        self.guild = guild if guild is not None else _Guild()


# ==============================================================================
# ANTREAN: LAPORAN & BANDING
# ==============================================================================
def test_laporan_baru_masuk_antrean_berstatus_baru():
    kode, entri = reports.tambah(GID, pelapor_id=5, target_id=9, alasan="spam judi di #umum")
    assert kode == "ok"
    assert entri["status"] == "baru"
    assert entri["jenis"] == "laporan"
    assert reports.ambil(GID, entri["id"]) is entri
    assert reports.status(GID)["menunggu"] == 1


def test_alasan_terlalu_pendek_ditolak():
    kode, entri = reports.tambah(GID, pelapor_id=5, alasan="spam")
    assert kode == "terlalu_pendek" and entri is None
    assert reports.daftar(GID) == []


def test_cooldown_per_pelapor_dan_per_jenis():
    assert reports.tambah(GID, pelapor_id=5, alasan="spam judi di #umum")[0] == "ok"
    assert reports.tambah(GID, pelapor_id=5, alasan="spam judi lagi dong")[0] == "cooldown"
    assert reports.sisa_cooldown(GID, 5) > 0
    # Pelapor lain / jenis lain tidak terpengaruh
    assert reports.tambah(GID, pelapor_id=6, alasan="spam judi di #umum")[0] == "ok"
    assert reports.tambah(GID, jenis="banding", pelapor_id=5, alasan="saya tidak spam")[0] == "ok"


def test_laporan_bisa_dimatikan_dari_setelan():
    reports.set_config(GID, enabled=False)
    kode, entri = reports.tambah(GID, pelapor_id=5, alasan="spam judi di #umum")
    assert kode == "nonaktif" and entri is None
    # Banding tetap diterima walau laporan dimatikan
    assert reports.tambah(GID, jenis="banding", pelapor_id=5, alasan="mohon ditinjau ulang")[0] == "ok"


def test_setelan_dibatasi():
    cfg = reports.set_config(GID, cooldown_sec=999999)
    assert cfg["cooldown_sec"] == 86400
    assert reports.set_config(GID, cooldown_sec=-5)["cooldown_sec"] == 0
    assert reports.set_config(GID, dm_pelapor=False)["dm_pelapor"] is False


def test_status_antrean_dan_penyaringan():
    _, satu = reports.tambah(GID, pelapor_id=5, alasan="spam judi di #umum")
    _, dua = reports.tambah(GID, pelapor_id=6, alasan="kata kasar ke member")
    reports.tambah(GID, jenis="banding", pelapor_id=7, alasan="mohon ditinjau ulang")

    reports.ubah_status(GID, satu["id"], "diterima", oleh=900, catatan="sudah ditindak")
    data = reports.status(GID)
    assert (data["total"], data["baru"], data["diterima"], data["laporan"], data["banding"]) == (
        3, 2, 1, 2, 1,
    )
    # Urut dari yang paling baru
    assert [e["id"] for e in reports.daftar(GID, status="baru")] == [3, dua["id"]]
    assert len(reports.daftar(GID, jenis="banding")) == 1
    assert reports.ambil(GID, satu["id"])["catatan"] == "sudah ditindak"
    assert reports.ambil(GID, satu["id"])["oleh"] == 900


def test_status_tidak_valid_ditolak():
    _, entri = reports.tambah(GID, pelapor_id=5, alasan="spam judi di #umum")
    assert reports.ubah_status(GID, entri["id"], "ngawur") is None
    assert reports.ambil(GID, entri["id"])["status"] == "baru"
    assert reports.ubah_status(GID, 999, "diterima") is None


def test_simulasi_tidak_menambah_antrean():
    hasil = reports.akan_masuk_antrean(GID, panjang_alasan=40)
    assert hasil["masuk"] is True
    assert reports.daftar(GID) == []
    assert reports.akan_masuk_antrean(GID, panjang_alasan=3)["masuk"] is False
    reports.set_config(GID, enabled=False)
    assert reports.akan_masuk_antrean(GID)["masuk"] is False


@pytest.mark.asyncio
async def test_antrean_tersimpan_dan_dimuat(monkeypatch, tmp_path):
    berkas = tmp_path / "reports.json"
    monkeypatch.setattr(reports, "REPORTS_FILE", berkas)

    reports.set_config(GID, channel_id=555, cooldown_sec=120)
    _, entri = reports.tambah(GID, pelapor_id=5, target_id=9, alasan="spam judi di #umum")
    reports.ubah_status(GID, entri["id"], "diproses", oleh=900)
    await reports.save_reports_to_disk()

    reports.reset_runtime_state()
    server, jumlah = reports.load_reports_from_disk()
    assert server >= 1 and jumlah == 1
    assert reports.status(GID)["channel_id"] == 555
    kembali = reports.ambil(GID, entri["id"])
    assert kembali["status"] == "diproses"
    assert kembali["target_id"] == 9


# ==============================================================================
# BANDING ↔ KASUS MODERASI
# ==============================================================================
def test_kasus_hukuman_terakhir_dicari():
    lama = md.add_case(GID, 42, 7, "warn", "spam")
    lama["created_at"] -= 600
    baru = md.add_case(GID, 42, 7, "timeout", "spam lagi", duration_sec=600)
    md.add_case(GID, 42, 7, "note", "catatan saja")

    gid, kasus = md.latest_punishment(42)
    assert (gid, kasus["id"]) == (GID, baru["id"])
    assert md.latest_punishment(42, GID)[1]["id"] == baru["id"]
    assert md.latest_punishment(43) is None


def test_hanya_aksi_tertentu_yang_bisa_dibanding():
    md.add_case(GID, 50, 7, "note", "bukan hukuman")
    assert md.latest_punishment(50) is None


@pytest.mark.asyncio
async def test_banding_diterima_mencabut_timeout(monkeypatch):
    from cogs.moderation_cog import _cabut_hukuman

    async def _catat():
        return None

    monkeypatch.setattr(md, "save_moderation_to_disk", _catat)
    kasus = md.add_case(GID, 501, 7, "timeout", "salah tuduh", duration_sec=600)
    _, entri = reports.tambah(
        GID, jenis="banding", pelapor_id=501, target_id=501, kasus_id=kasus["id"],
        alasan="saya tidak melakukan itu",
    )
    interaksi = _Interaction(uid=900)
    pesan = await _cabut_hukuman(interaksi, entri)
    assert "Timeout dicabut" in pesan
    assert interaksi.guild.get_member(501).timeout_calls
    assert md.list_cases(GID, 501)[0]["action"] == "unmute"


@pytest.mark.asyncio
async def test_banding_diterima_mencabut_tempban(monkeypatch):
    from cogs.moderation_cog import _cabut_hukuman

    async def _catat():
        return None

    monkeypatch.setattr(md, "save_moderation_to_disk", _catat)
    kasus = md.add_case(GID, 502, 7, "tempban", "spam", duration_sec=3600, expires_at=time.time() + 3600)
    md.add_tempban(GID, 502, case_id=kasus["id"], until=time.time() + 3600, oleh=7)
    _, entri = reports.tambah(
        GID, jenis="banding", pelapor_id=502, target_id=502, kasus_id=kasus["id"],
        alasan="mohon ditinjau, saya salah paham",
    )
    interaksi = _Interaction(uid=900)
    pesan = await _cabut_hukuman(interaksi, entri)
    assert "Ban dicabut" in pesan
    assert interaksi.guild.unban_calls[0][0] == 502
    assert md.list_tempbans(GID) == []


@pytest.mark.asyncio
async def test_banding_tanpa_kasus_tidak_mengubah_hukuman(monkeypatch):
    from cogs.moderation_cog import _cabut_hukuman

    _, entri = reports.tambah(GID, jenis="banding", pelapor_id=501, alasan="mohon ditinjau")
    interaksi = _Interaction(uid=900)
    pesan = await _cabut_hukuman(interaksi, entri)
    assert "tidak terhubung" in pesan
    assert interaksi.guild.unban_calls == []


# ==============================================================================
# COMMAND
# ==============================================================================
def test_command_jalur_member_dan_staf_terdaftar():
    from cogs.moderation_cog import banding_cmd, lapor_cmd, mod_group

    assert lapor_cmd.name == "lapor"
    assert banding_cmd.name == "banding"
    nama = {c.name for c in mod_group.commands}
    assert {"antrean", "tindak"} <= nama
    opsi = {p.name for p in lapor_cmd.parameters}
    assert {"member", "alasan", "bukti"} <= opsi


# ==============================================================================
# DASHBOARD: HALAMAN MODERASI
# ==============================================================================
def test_blok_moderasi_memuat_semua_bagian():
    md.add_case(GID, 42, 7, "ban", "menyebar judi")
    md.add_tempban(GID, 42, case_id=1, until=time.time() + 600, oleh=7, reason="judi")
    reports.tambah(GID, pelapor_id=5, target_id=42, alasan="spam judi di #umum")

    html = dashboard_moderasi.render_moderasi_block(None, GID, TOKEN)
    for bagian in ("Antrean laporan", "Setelan jalur laporan", "Ban sementara",
                   "Cari kasus", "Statistik staf", "Kasus terbaru"):
        assert bagian in html, bagian
    assert "antrean-status" in html and "tempban-cabut" in html
    assert "laporan-setelan" in html and "cari-kasus" in html
    # Prinsip: member tidak dihukum hanya karena dilaporkan
    assert "tidak pernah dihukum" in html


def test_pencarian_kasus_menyimpan_hasil_terakhir():
    md.add_case(GID, 42, 7, "ban", "menyebar judi online")
    md.add_case(GID, 43, 7, "warn", "spam link")

    hasil = dashboard_moderasi.cari_kasus(GID, "judi")
    assert [k["user_id"] for k in hasil] == [42]
    terakhir = dashboard_moderasi.hasil_pencarian(GID)
    assert terakhir["q"] == "judi" and len(terakhir["hasil"]) == 1

    # Hasil tetap tampil setelah redirect (tanpa JavaScript)
    html = dashboard_moderasi.render_moderasi_block(None, GID, TOKEN)
    assert "kasus ditemukan" in html
    assert "judi online" in html


def test_pencarian_kosong_memberi_pesan_jelas():
    html = dashboard_moderasi.render_moderasi_block(None, GID, TOKEN)
    assert "Belum ada pencarian" in html
    dashboard_moderasi.cari_kasus(GID, "tidak-ada-sama-sekali")
    html = dashboard_moderasi.render_moderasi_block(None, GID, TOKEN)
    assert "Tidak ada kasus yang cocok" in html


def test_halaman_moderasi_dirender_dan_terisolasi():
    import web_dashboard

    assert web_dashboard.ANCHOR_HALAMAN["p-moderasi"] == "moderasi"
    assert "moderasi" in [h["slug"] for h in web_dashboard.HALAMAN]

    blok = dashboard_moderasi.render_moderasi_block(None, GID, TOKEN)
    halaman = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="moderasi",
        token=TOKEN, guild_id=GID, moderasi_block=blok,
    )
    assert '<div class="panel" id="p-moderasi">' in halaman
    assert "Antrean laporan" in halaman
    # Panel halaman lain tidak ikut
    assert 'id="p-tiket"' not in halaman
    assert 'id="p-keamanan"' not in halaman
    assert "<script" not in halaman.lower()


def test_uji_moderasi_hanya_simulasi():
    import dashboard_uji

    ok, pesan = dashboard_uji._uji_moderasi(GID)
    assert ok is True
    assert "Simulasi" in pesan
    assert reports.daftar(GID) == []      # tidak ada laporan palsu

    reports.set_config(GID, enabled=False)
    ok, pesan = dashboard_uji._uji_moderasi(GID)
    assert ok is False
    assert "dimatikan" in pesan


def test_penguji_moderasi_menempel_di_halaman_moderasi():
    import dashboard_uji
    import web_dashboard

    assert dashboard_uji.ANCHOR_UJI["moderasi"] == "p-moderasi"
    assert "moderasi" in web_dashboard.UJI_HALAMAN["moderasi"]
