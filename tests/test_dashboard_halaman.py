"""Dashboard dipecah per halaman fitur (tanpa JavaScript)."""

from __future__ import annotations

import re
import socket

import aiohttp

import dashboard_admin
import levels
import server_builder as sb
import web_dashboard

GID = 1234
TOKEN = "tok-halaman"


def _panel(html: str, anchor: str) -> bool:
    """Panel dashboard punya penanda container sendiri (id juga dipakai form)."""
    return (
        f'<div class="panel" id="{anchor}">' in html
        or f'<section id="{anchor}">' in html
    )


# ==============================================================================
# STRUKTUR HALAMAN
# ==============================================================================
def test_halaman_sesuai_kelompok_fitur():
    slug = [h["slug"] for h in web_dashboard.HALAMAN]
    # Satu grup fitur = satu halaman: unggah kartu & tombol tes ikut di halamannya.
    # Satu halaman per grup setelan — sambutan/pamit/boost digabung.
    assert slug == ["", "sambutan", "inti", "keamanan", "moderasi", "tiket", "konten",
                    "bangun", "giveaway", "kirim", "buat", "panel", "ekspor"]
    assert "uji" not in slug and "setelan" not in slug

    # Semua panel lama tetap punya halaman — tidak ada yang hilang
    semua = [a for h in web_dashboard.HALAMAN for a in h["panel"]]
    assert sorted(semua) == sorted(web_dashboard.PANEL)
    assert len(semua) == len(set(semua))


def test_setiap_halaman_hanya_memuat_panelnya():
    for halaman in web_dashboard.HALAMAN:
        page = web_dashboard.render_dashboard_html(
            status={}, usage={}, levels={}, halaman=halaman["slug"]
        )
        for anchor in halaman["panel"]:
            assert _panel(page, anchor), (halaman["slug"], anchor)
        for anchor in web_dashboard.PANEL:
            if anchor not in halaman["panel"]:
                assert not _panel(page, anchor), (halaman["slug"], anchor)


def test_menu_menautkan_halaman_dan_menandai_yang_aktif():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="keamanan", token=TOKEN, guild_id=GID
    )
    assert f'href="/keamanan?token={TOKEN}&amp;guild={GID}" aria-current="page"' in page
    assert page.count(' aria-current="page">') == 1   # hanya satu menu aktif
    # Token & server tetap terbawa di semua tautan menu
    assert f'href="/inti?token={TOKEN}&amp;guild={GID}"' in page
    assert f'href="/?token={TOKEN}&amp;guild={GID}"' in page
    assert page.count("<nav class=\"menu\"") == 1


def test_tidak_ada_javascript_di_semua_halaman():
    for halaman in web_dashboard.HALAMAN:
        page = web_dashboard.render_dashboard_html(
            status={}, usage={}, levels={}, halaman=halaman["slug"]
        )
        assert "<script" not in page.lower()
        assert "onclick" not in page.lower()


def test_url_halaman_dan_pemetaan_anchor():
    assert web_dashboard.url_halaman("", "t", 5) == "/?token=t&guild=5"
    assert web_dashboard.url_halaman("panel", "t", 5) == "/panel?token=t&guild=5"
    assert web_dashboard.halaman_dari_anchor("p-tiket") == "tiket"
    assert web_dashboard.halaman_dari_anchor("p-banner") == "kirim"
    assert web_dashboard.halaman_dari_anchor("p-riwayat") == "ekspor"
    assert web_dashboard.halaman_dari_anchor("p-sambutan") == "sambutan"
    assert web_dashboard.halaman_dari_anchor("p-bangun") == "bangun"
    assert web_dashboard.halaman_dari_anchor("p-konten") == "konten"
    assert web_dashboard.halaman_dari_anchor("p-keamanan") == "keamanan"
    # Bookmark lama tetap nyasar ke tempat yang benar
    assert web_dashboard.halaman_dari_anchor("p-kartu") == "sambutan"
    assert web_dashboard.halaman_dari_anchor("p-ngawur") == ""
    assert web_dashboard.halaman_dari_path("/inti") == "inti"
    assert web_dashboard.halaman_dari_path("/setelan") == ""   # slug lama
    assert web_dashboard.halaman_dari_path("/") == ""
    assert web_dashboard.halaman_dari_path("/tidak-ada") == ""


def test_halaman_lama_tetap_dirender_lengkap():
    """Pemanggilan tanpa `halaman` (tes/integrasi lama) tetap memuat semua panel."""
    page = web_dashboard.render_dashboard_html(status={}, usage={}, levels={})
    for anchor in web_dashboard.PANEL:
        assert _panel(page, anchor), anchor


# ==============================================================================
# HTTP: rute, redirect, & API
# ==============================================================================
class _Guild:
    id = GID
    name = "Server Halaman"
    member_count = 3
    channels: list = []
    roles: list = []


class _Bot:
    def __init__(self):
        self.guilds = [_Guild()]
        self.latency = 0.01
        self.user = type("U", (), {"name": "BotUji"})()

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GID else None

    def get_channel(self, cid):
        return None


async def _jalankan(monkeypatch, bot, fn, tmp_path):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(dashboard_admin, "AUDIT_FILE", tmp_path / "dashboard_audit.json")
    dashboard_admin.reset_cache()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", TOKEN)

    assert await web_dashboard.start_dashboard(bot) is True
    try:
        async with aiohttp.ClientSession() as session:
            return await fn(session, f"http://127.0.0.1:{port}")
    finally:
        await web_dashboard.stop_dashboard()
        dashboard_admin.reset_cache()


async def test_semua_rute_halaman_200_dan_terisolasi(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        for halaman in web_dashboard.HALAMAN:
            alamat = f"{base}/{halaman['slug']}?token={TOKEN}&guild={GID}"
            async with session.get(alamat) as resp:
                assert resp.status == 200, halaman["slug"]
                body = await resp.text()
            for anchor in halaman["panel"]:
                assert _panel(body, anchor), halaman["slug"]
            lain = [a for a in web_dashboard.PANEL if a not in halaman["panel"]]
            for anchor in lain:
                assert not _panel(body, anchor), (halaman["slug"], anchor)

        # Tanpa token tetap 401 (termasuk halaman baru)
        async with session.get(f"{base}/inti?guild={GID}") as resp:
            assert resp.status == 401

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_bookmark_lama_dialihkan_ke_halaman_baru(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        async with session.get(
            f"{base}/?token={TOKEN}&guild={GID}&halaman=setelan", allow_redirects=False
        ) as resp:
            assert resp.status == 303
            assert resp.headers["Location"] == f"/inti?token={TOKEN}&guild={GID}"

        # Halaman yang sama tidak me-redirect terus-menerus
        async with session.get(
            f"{base}/inti?token={TOKEN}&guild={GID}&halaman=inti", allow_redirects=False
        ) as resp:
            assert resp.status == 200

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_redirect_kembali_ke_halaman_asal_per_aksi(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        pasangan = [
            ("aksi", {"action": "level", "value": "off"}, "/inti"),   # p-kontrol
            ("aksi", {"action": "set.level.aktif", "value": "on"}, "/inti"),
            ("konten", {"aksi": "hapus.panel:tidak-ada"}, "/buat"),
            ("panel", {"aksi": "tambah:tidak-ada"}, "/panel"),
            ("tiket", {"aksi": "balas:tidak-ada", "teks": "halo"}, "/tiket"),
            ("unggah", {"aksi": "hapus", "nama": "tidak-ada.png"}, "/kirim"),
        ]
        for rute, data, halaman in pasangan:
            kirim = {"token": TOKEN, "guild": str(GID), **data}
            async with session.post(
                f"{base}/api/{rute}", data=kirim, allow_redirects=False
            ) as resp:
                assert resp.status in (200, 303, 400), rute
                if resp.status == 303:
                    lokasi = resp.headers["Location"]
                    assert lokasi.startswith(f"{halaman}?"), (rute, lokasi)

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_api_json_tidak_terpengaruh_halaman(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        async with session.get(f"{base}/api/status?token={TOKEN}") as resp:
            assert resp.status == 200 and "version" in await resp.json()
        async with session.get(f"{base}/api/setelan?token={TOKEN}&guild={GID}") as resp:
            data = await resp.json()
            assert resp.status == 200
            assert len(data["nilai"]) == len(dashboard_admin.FITUR)
        # POST JSON tetap JSON (bukan redirect), walau UI kini per halaman
        async with session.post(
            f"{base}/api/aksi",
            json={"token": TOKEN, "guild": str(GID), "action": "level", "value": "on"},
        ) as resp:
            assert resp.status == 200
            assert (await resp.json())["ok"] is True

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


def test_nomor_versi_tidak_berubah():
    import config

    assert re.match(r"^\d+\.\d+\.\d+", config.BOT_VERSION)
    # halaman baru tetap ringan: tidak ada berkas statis tambahan
    assert levels.peek_level_config(0) == {}


async def test_panel_bangun_bisa_membuat_pratinjau_tanpa_menerapkan(monkeypatch, tmp_path):
    bot = _Bot()
    sb.reset_state()

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/bangun",
            data={"token": TOKEN, "guild": str(GID), "action": "tema", "tema": "coding"},
            allow_redirects=False,
        ) as resp:
            assert resp.status == 303
            assert resp.headers["Location"].startswith(f"/bangun?token={TOKEN}&guild={GID}")
        assert sb.ambil_siap(GID) is not None
        audit = dashboard_admin.audit_terakhir(GID, limit=1)[0]
        assert audit["aksi"] == "bangun.tema" and audit["nilai"] == "tema:coding"
        async with session.get(f"{base}/bangun?token={TOKEN}&guild={GID}") as resp:
            body = await resp.text()
            assert resp.status == 200
            assert 'id="p-bangun"' in body
            assert "Pratinjau menunggu keputusan" in body
            assert "Belum ada struktur yang dibuat" in body

        async with session.post(
            f"{base}/api/bangun", data={"guild": str(GID), "action": "terapkan"}
        ) as resp:
            assert resp.status == 401

    try:
        await _jalankan(monkeypatch, bot, skenario, tmp_path)
    finally:
        sb.reset_state()
