"""Uji penguji aturan anti-spam: simulasi tanpa tindakan, statistik per aturan, & dashboard."""

from __future__ import annotations

import time

import pytest

import antispam
import dashboard_keamanan
import dashboard_ui
import web_dashboard

GID = 9001


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan():
    antispam.spam_guilds.clear()
    antispam.reset_runtime_state()
    dashboard_keamanan.reset()
    yield
    antispam.spam_guilds.clear()
    antispam.reset_runtime_state()
    dashboard_keamanan.reset()


class _Penulis:
    def __init__(self, uid: int = 501):
        self.id = uid
        self.bot = False
        self.timeout_calls: list = []

    async def timeout(self, durasi, reason: str = ""):
        self.timeout_calls.append((durasi, reason))


class _Kanal:
    def __init__(self, cid: int = 700):
        self.id = cid
        self.deleted = False

    async def send(self, *args, **kwargs):
        return None


class _Pesan:
    def __init__(self, isi: str, *, mentions: int = 0, uid: int = 501, cid: int = 700):
        self.content = isi
        self.author = _Penulis(uid)
        self.channel = _Kanal(cid)
        self.guild = type("G", (), {"id": GID, "name": "Server Uji"})()
        self.mentions = [object() for _ in range(mentions)]
        self.deleted = False

    async def delete(self):
        self.deleted = True


# ==============================================================================
# PENGUJI ATURAN
# ==============================================================================
def test_uji_aturan_menyebut_semua_aturan_dan_kapan_kena():
    antispam.set_spam_config(
        GID, enabled=True, mode="hapus", mention_limit=3, link_limit=2, flood_count=5
    )
    hasil = antispam.uji_aturan(
        "halo <@1> <@2> <@3> cek https://a.com dan https://b.com", guild_id=GID
    )
    kunci = [item["kunci"] for item in hasil["aturan"]]
    assert kunci == list(antispam.ATURAN_UJI)
    assert set(hasil["kena"]) == {"mention", "link"}
    detail = {item["kunci"]: item["detail"] for item in hasil["aturan"]}
    assert "3" in detail["mention"] and "batas" in detail["mention"]
    assert "2" in detail["link"]

    # Aturan berbasis riwayat disimulasikan lewat `ulang`
    assert "flood" not in hasil["kena"]
    spam = antispam.uji_aturan("halo halo", guild_id=GID, ulang=9)
    assert "flood" in spam["kena"] and "duplikat" in spam["kena"]
    assert spam["ulang"] == 9

    # Teks pendek tidak bisa kena aturan duplikat (dilewati, tidak error)
    pendek = antispam.uji_aturan("ok", guild_id=GID, ulang=9)
    assert "duplikat" not in pendek["kena"]


def test_uji_aturan_tidak_menindak_dan_tidak_mencatat_riwayat():
    antispam.set_spam_config(GID, enabled=True, mode="timeout", mention_limit=2)
    sebelum_pesan = {k: list(v) for k, v in antispam._recent_messages.items()}
    sebelum_teks = {k: list(v) for k, v in antispam._recent_texts.items()}

    hasil = antispam.uji_aturan("<@1> <@2> halo", guild_id=GID, ulang=5)
    assert "mention" in hasil["kena"]
    assert antispam.spam_guilds[GID].get("blocked", 0) == 0
    assert antispam._recent_messages == sebelum_pesan
    assert antispam._recent_texts == sebelum_teks
    assert antispam.statistik_aturan(GID)["blocked"] == 0


def test_aturan_caps_ditandai_nonaktif_bila_dimatikan():
    antispam.set_spam_config(GID, enabled=True, caps_enabled=False)
    hasil = antispam.uji_aturan("INI SEMUA HURUF BESAR SEKALI", guild_id=GID)
    caps = [item for item in hasil["aturan"] if item["kunci"] == "caps"][0]
    assert caps["aktif"] is False and caps["kena"] is False
    assert "dimatikan" in caps["detail"]

    antispam.set_spam_config(GID, caps_enabled=True, caps_min_length=10)
    hasil = antispam.uji_aturan("INI SEMUA HURUF BESAR SEKALI", guild_id=GID)
    assert "caps" in hasil["kena"]


def test_uji_aturan_pakai_setelan_bawaan_bila_server_belum_diatur():
    hasil = antispam.uji_aturan("halo <@1> <@2> <@3> <@4> <@5> <@6>", guild_id=999)
    assert hasil["aturan"] and hasil["mode"] == "lapor"
    assert "mention" in hasil["kena"]


# ==============================================================================
# STATISTIK PER ATURAN
# ==============================================================================
def test_statistik_per_aturan_naik_dan_reset_harian():
    antispam.set_spam_config(GID, enabled=True)
    assert antispam.statistik_aturan(GID)["hari"] == time.strftime("%Y-%m-%d")
    antispam.catat_aturan(GID, "mention")
    antispam.catat_aturan(GID, "mention")
    antispam.catat_aturan(GID, "flood")
    stat = antispam.statistik_aturan(GID)
    peta = {item["kunci"]: item for item in stat["aturan"]}
    assert peta["mention"]["hari_ini"] == 2 and peta["mention"]["total"] == 2
    assert peta["flood"]["hari_ini"] == 1
    assert peta["link"]["hari_ini"] == 0

    # Kemarin: `hari_ini` kembali 0, `total` tetap terakumulasi
    kemarin = time.time() - 86400
    stat_lama = antispam.statistik_aturan(GID, now=kemarin)
    peta_lama = {item["kunci"]: item for item in stat_lama["aturan"]}
    assert peta_lama["mention"]["hari_ini"] == 0
    assert peta_lama["mention"]["total"] == 2

    # Aturan tak dikenal diabaikan
    assert antispam.catat_aturan(GID, "bukan-aturan") == {}
    assert antispam.catat_aturan(123456, "mention") == {}


@pytest.mark.asyncio
async def test_penindakan_spam_ikut_mencatat_statistik():
    antispam.set_spam_config(GID, enabled=True, mode="hapus", mention_limit=2)
    pesan = _Pesan("<@1> <@2> halo semuanya", mentions=2)
    ditindak = await antispam.handle_spam_guard(pesan, bot=None)
    assert ditindak is True and pesan.deleted is True

    stat = antispam.statistik_aturan(GID)
    peta = {item["kunci"]: item for item in stat["aturan"]}
    assert peta["mention"]["hari_ini"] == 1 and peta["mention"]["total"] == 1
    assert stat["blocked"] == 1


@pytest.mark.asyncio
async def test_statistik_bertahan_setelah_simpan_dan_muat_ulang(monkeypatch, tmp_path):
    monkeypatch.setattr(antispam, "ANTISPAM_FILE", tmp_path / "antispam.json")
    antispam.set_spam_config(GID, enabled=True, mode="lapor", mention_limit=2)
    antispam.catat_aturan(GID, "link")
    await antispam.save_antispam_to_disk()

    antispam.spam_guilds.clear()
    antispam.load_antispam_from_disk()
    peta = {item["kunci"]: item for item in antispam.statistik_aturan(GID)["aturan"]}
    assert peta["link"]["total"] == 1 and peta["link"]["hari_ini"] == 1


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_dashboard_uji_menyimpan_hasil_dan_menolak_teks_kosong():
    antispam.set_spam_config(GID, enabled=True, mention_limit=3)
    ok, pesan = dashboard_keamanan.uji(GID, "   ")
    assert ok is False and "Tempel" in pesan
    assert dashboard_keamanan.terakhir(GID) is None

    ok, pesan = dashboard_keamanan.uji(GID, "<@1> <@2> <@3> halo")
    assert ok is True and "Mention massal" in pesan and "simulasi" in pesan
    hasil = dashboard_keamanan.terakhir(GID)
    assert hasil["kena"] == ["mention"]
    assert dashboard_keamanan.collect(GID)["uji"]["kena"] == ["mention"]

    ok, pesan = dashboard_keamanan.uji(GID, "halo kak, apa kabar?")
    assert ok is True and "Tidak ada aturan" in pesan
    assert dashboard_keamanan.terakhir(GID)["kena"] == []


def test_blok_keamanan_menampilkan_form_statistik_dan_hasil():
    antispam.set_spam_config(GID, enabled=True, mode="hapus", mention_limit=2)
    antispam.catat_aturan(GID, "mention")
    dashboard_keamanan.uji(GID, "<@1> <@2> halo")

    html = dashboard_ui.render_aturan_block(GID, "tok", dashboard_keamanan.collect(GID))
    assert "Penguji aturan" in html
    assert 'action="/api/keamanan"' in html and "uji-aturan" in html
    assert 'name="teks"' in html and 'name="ulang"' in html
    assert "Hasil uji terakhir" in html and "Mention massal" in html
    assert "Statistik per aturan" in html
    assert "hapus pesan" in html          # mode tindakan ditampilkan apa adanya
    assert "Tidak ada pesan yang dihapus" in html or "tidak menghapus pesan" in html

    # Hasil uji di-escape (tidak ada HTML mentah dari input pengguna)
    dashboard_keamanan.uji(GID, "<script>alert(1)</script> <@1> <@2>")
    html = dashboard_ui.render_aturan_block(GID, "tok", dashboard_keamanan.collect(GID))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_blok_keamanan_tanpa_hasil_uji_tetap_berguna():
    html = dashboard_ui.render_aturan_block(GID, "tok", dashboard_keamanan.collect(GID))
    assert "Hasil uji terakhir" not in html
    assert "Statistik per aturan" in html
    assert "nonaktif" in html          # penjaga spam belum diatur di server ini


def test_halaman_keamanan_memuat_blok_penguji():
    assert web_dashboard.halaman_dari_anchor("p-aturan") == "keamanan"
    assert "p-keamanan" in web_dashboard.HALAMAN_SLUG["keamanan"]["panel"]

    halaman = web_dashboard.render_dashboard_html(
        status={"version": "v1.40.0-beta", "bot_name": "Bot", "checked_at": "-"},
        usage={},
        levels={},
        refresh=0,
        halaman="keamanan",
        token="tok",
        guild_id=GID,
        aturan_block="<div id=\"p-aturan\">uji</div>",
    )
    assert "p-aturan" in halaman
