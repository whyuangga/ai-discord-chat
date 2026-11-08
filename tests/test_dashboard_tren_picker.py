"""Uji pemilih server, grafik tren SVG, pratinjau embed, & alat token self-host."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import aiohttp

import dashboard_ui as ui
import insights
import web_dashboard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import dashboard_token as dt  # noqa: E402


# ==============================================================================
# PEMILIH SERVER
# ==============================================================================
class _Guild:
    def __init__(self, gid, nama):
        self.id = gid
        self.name = nama
        self.member_count = 1
        self.channels = []
        self.roles = []


class _Bot:
    def __init__(self, guilds=()):
        self.guilds = list(guilds)
        self.latency = 0.01
        self.user = type("U", (), {"name": "BotUji"})()

    def get_guild(self, gid):
        for g in self.guilds:
            if g.id == int(gid):
                return g
        return None

    def get_channel(self, cid):
        return None


def test_picker_banyak_server_berisi_dropdown():
    bot = _Bot([_Guild(2, "Zeta"), _Guild(1, "Alpha")])
    html = ui.render_guild_picker(bot, 2, "tok")

    assert 'name="guild"' in html and 'method="get"' in html
    assert "<option" in html
    assert html.index("Alpha") < html.index("Zeta")     # urut nama
    assert 'value="2" selected' in html                  # server aktif terpilih
    assert 'value="tok"' in html


def test_picker_satu_server_dan_tanpa_server():
    bot = _Bot([_Guild(1, "Alpha")])
    assert "Alpha" in ui.render_guild_picker(bot, 1, "tok")
    assert "<select" not in ui.render_guild_picker(bot, 1, "tok")
    assert "belum berada" in ui.render_guild_picker(_Bot(), 0, "tok")


def test_halaman_dashboard_memuat_pemilih_server():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, guild_picker="PILIH-SERVER-UJI"
    )
    assert "PILIH-SERVER-UJI" in page


# ==============================================================================
# GRAFIK TREN
# ==============================================================================
def test_collect_tren_mengisi_hari_kosong(monkeypatch):
    import datetime

    hari_ini = datetime.date.today()
    kemarin = (hari_ini - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    kemarin2 = (hari_ini - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    monkeypatch.setattr(
        insights,
        "ai_usage",
        {kemarin: {"total": 7, "cache_hits": 2}, kemarin2: {"total": 3, "cache_hits": 0}},
        raising=False,
    )

    data = web_dashboard.collect_tren(7)
    assert data["hari"] == 7 and len(data["rows"]) == 7
    assert data["rows"][-1]["tanggal"] == hari_ini.strftime("%Y-%m-%d")
    assert data["rows"][-1]["total"] == 0            # hari ini kosong
    assert data["rows"][-2]["total"] == 7
    assert data["total"] == 10 and data["cache_hits"] == 2
    assert all(len(row["label"]) == 5 for row in data["rows"])


def test_collect_tren_aman_tanpa_data(monkeypatch):
    monkeypatch.setattr(insights, "ai_usage", {}, raising=False)
    data = web_dashboard.collect_tren(7)
    assert data["total"] == 0 and len(data["rows"]) == 7


def test_render_tren_svg():
    rows = [
        {"label": "05/11", "total": 4, "cache_hits": 1},
        {"label": "06/11", "total": 9, "cache_hits": 0},
    ]
    svg = ui.render_tren_svg(rows, judul="Operasi AI")
    assert svg.startswith("<div class=\"grafik\">")
    # 2 batang utama + 1 batang kecil untuk cache (baris pertama punya cache_hits=1)
    assert "<svg" in svg and svg.count("<rect") == 3
    assert "#58d68d" in svg
    assert "05/11" in svg and "06/11" in svg
    assert "puncak 9/hari" in svg
    assert "Belum ada data tren" in ui.render_tren_svg([])


def test_render_tren_svg_tidak_meledak_saat_semua_nol():
    svg = ui.render_tren_svg([{"label": "01/01", "total": 0, "cache_hits": 0}])
    assert "<svg" in svg and "puncak 1/hari" in svg


# ==============================================================================
# PRATINJAU EMBED
# ==============================================================================
def test_render_pratinjau_html_lengkap():
    halaman = ui.render_pratinjau_html(
        pratinjau={
            "judul": "Pengumuman",
            "isi": "Baris satu\nbaris dua",
            "warna": "#ff8800",
            "footer": "Bot Uji",
            "gambar": "https://contoh.id/a.png",
            "identitas": "📢 Pengumuman",
            "tombol_label": "Buka",
            "tombol_url": "https://contoh.id",
            "channel_label": "#umum",
            "peringatan": ["Isi lebih dari 4000 karakter."],
        },
        token="tok",
        guild_id=7,
        fields={"action": "kirim", "isi": "Baris satu", "guild": "7"},
    )
    assert "Pratinjau embed" in halaman
    assert "border-left-color:#ff8800" in halaman
    assert "via webhook" in halaman
    assert "Perlu diperiksa" in halaman
    assert 'action="/api/kirim"' in halaman
    assert 'name="isi" value="Baris satu"' in halaman
    assert "/?token=tok&amp;guild=7" in halaman


def test_render_pratinjau_meng_escape_html():
    halaman = ui.render_pratinjau_html(
        pratinjau={"judul": "<script>x</script>", "isi": "<b>tebal</b>"},
        token="t",
        guild_id=1,
        fields={"judul": "<script>x</script>"},
    )
    assert "<script>x</script>" not in halaman
    assert "&lt;script&gt;" in halaman


# ==============================================================================
# PRATINJAU / KIRIM (HTTP)
# ==============================================================================
class _Channel:
    def __init__(self, cid=11, gid=1234):
        self.id = cid
        self.name = "umum"
        self.mention = f"<#{cid}>"
        self.guild = type("G", (), {"id": gid, "name": "Server Uji"})()
        self.terkirim = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return type("M", (), {"id": 1})()


async def test_http_pratinjau_tidak_mengirim_lalu_kirim(tmp_path, monkeypatch):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    ch = _Channel()
    bot = _Bot([_Guild(1234, "Server Uji")])
    bot.get_channel = lambda cid: ch if int(cid) == 11 else None

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "tok-prev")

    assert await web_dashboard.start_dashboard(bot) is True
    base = f"http://127.0.0.1:{port}"
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            async with session.post(
                f"{base}/api/kirim",
                data={"token": "tok-prev", "guild": "1234", "action": "kirim",
                      "channel": "11", "judul": "Halo {server.name}", "isi": "Isi",
                      "warna": "bukan-warna", "pratinjau": "1"},
            ) as resp:
                body = await resp.text()
                assert resp.status == 200
                assert "Pratinjau embed" in body
                assert "#umum" in body
                assert "Warna tidak valid" in body
                assert "Halo Server Uji" in body        # variabel dirender
                assert "belum ada yang dikirim" in body
            assert ch.terkirim == []                     # tidak mengirim apa pun

            # Tombol "Kirim sekarang" mengirim dengan isian yang sama
            async with session.post(
                f"{base}/api/kirim",
                data={"token": "tok-prev", "guild": "1234", "action": "kirim",
                      "channel": "11", "judul": "Halo", "isi": "Isi"},
            ) as resp:
                body = await resp.text()
                assert resp.status == 200 and "Terkirim" in body
            assert len(ch.terkirim) == 1
    finally:
        await web_dashboard.stop_dashboard()


async def test_http_tren_dan_pemilih_server(tmp_path, monkeypatch):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    bot = _Bot([_Guild(1, "Alpha"), _Guild(2, "Beta")])

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "tok-tren")

    assert await web_dashboard.start_dashboard(bot) is True
    base = f"http://127.0.0.1:{port}"
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            async with session.get(f"{base}/api/tren?hari=7", headers={"X-Dashboard-Token": "tok-tren"}) as resp:
                data = await resp.json()
                assert resp.status == 200 and len(data["rows"]) == 7
            # Klien ini kini punya sesi → tanpa header tetap boleh
            async with session.get(f"{base}/api/tren?hari=7") as resp:
                assert resp.status == 200
            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as anon:
                async with anon.get(f"{base}/api/tren?hari=7") as resp:
                    assert resp.status == 401

            async with session.get(f"{base}/?token=tok-tren&guild=2") as resp:
                body = await resp.text()
                assert resp.status == 200
                assert "Tren 7 hari" in body and "<svg" in body
                assert 'value="2" selected' in body       # server aktif
                assert "Alpha" in body and "Beta" in body
    finally:
        await web_dashboard.stop_dashboard()


# ==============================================================================
# ALAT TOKEN SELF-HOST
# ==============================================================================
def test_buat_token_aman_dan_valid():
    token = dt.buat_token()
    assert len(token) >= 40
    assert dt.periksa_token(token) == (True, "")
    assert dt.buat_token() != token


def test_periksa_token_menolak_yang_lemah():
    assert dt.periksa_token("pendek")[0] is False
    assert dt.periksa_token("a" * 30 + " spasi")[0] is False
    assert dt.periksa_token('"' + "a" * 40)[0] is False


def test_tulis_env_membuat_dan_mengganti(tmp_path, capsys):
    env = tmp_path / ".env"
    assert dt.tulis_env(env, "DASHBOARD_TOKEN", "a" * 41) is True
    assert "DASHBOARD_TOKEN=" + "a" * 41 in env.read_text()

    dt.tulis_env(env, "DASHBOARD_PORT", "8080")
    dt.tulis_env(env, "DASHBOARD_TOKEN", "b" * 41)
    isi = env.read_text()
    assert isi.count("DASHBOARD_TOKEN=") == 1          # tidak dobel
    assert "b" * 41 in isi and "DASHBOARD_PORT=8080" in isi

    assert dt.main(["--tulis", "--env", str(env)]) == 0   # token sudah ada → tidak diubah
    assert env.read_text().count("DASHBOARD_TOKEN=") == 1


def test_main_periksa_melaporkan_status(tmp_path, capsys):
    env = tmp_path / ".env"
    assert dt.main(["--periksa", "--env", str(env)]) == 1     # belum siap
    assert "tidak menyala" in capsys.readouterr().out

    env.write_text("DASHBOARD_TOKEN=" + "c" * 41 + "\nDASHBOARD_PORT=8080\n", encoding="utf-8")
    assert dt.main(["--periksa", "--env", str(env)]) == 0
    keluaran = capsys.readouterr().out
    assert "terisi" in keluaran and "8080" in keluaran


def test_baca_env_mengabaikan_komentar(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# komentar\nDASHBOARD_TOKEN=abc\n\nDASHBOARD_PORT=8080\n", encoding="utf-8")
    data = dt.baca_env(env)
    assert data == {"DASHBOARD_TOKEN": "abc", "DASHBOARD_PORT": "8080"}
