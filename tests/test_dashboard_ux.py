"""Uji perbaikan UX dashboard: saklar tidak "balik nyala", menu ☰, redirect 303."""

from __future__ import annotations

import socket

import aiohttp

import dashboard_admin
import levels
import web_dashboard

GID = 1234


# ==============================================================================
# SAKLAR TIDAK BALIK NYALA (bug: "Nonaktif" berubah jadi "Aktif" lagi)
# ==============================================================================
def test_peek_level_tidak_membuat_config():
    gid = 90001
    levels.level_guilds.pop(gid, None)
    assert levels.peek_level_config(gid) == {}
    assert gid not in levels.level_guilds          # tetap tidak dibuat
    assert levels.is_leveling_active(gid) is False


async def test_level_aktif_off_tidak_balik_on():
    gid = 90003
    dashboard_admin.read_values(gid)
    ok, pesan = await dashboard_admin.apply(gid, "level.aktif", "off")
    assert ok is True and "nonaktif" in pesan

    for _ in range(3):                              # baca berkali-kali (render + reload)
        assert dashboard_admin.read_values(gid)["level.aktif"] == "off"
        assert web_dashboard.dashboard_controls(gid)["level"] == "off"
        assert levels.is_leveling_active(gid) is False

    ok, pesan = await dashboard_admin.apply(gid, "level.aktif", "on")
    assert ok is True and levels.is_leveling_active(gid) is True
    assert dashboard_admin.read_values(gid)["level.aktif"] == "on"


async def test_mematikan_level_tidak_menghapus_setelan_lain():
    gid = 90004
    levels.set_level_config(gid, announce_channel_id=44, xp_min=20)
    await dashboard_admin.apply(gid, "level.aktif", "off")
    cfg = levels.peek_level_config(gid)
    assert cfg.get("enabled") is False
    assert cfg.get("announce_channel_id") == 44     # setelan tidak ikut hilang
    assert cfg.get("xp_min") == 20

    await dashboard_admin.apply(gid, "level.aktif", "on")
    assert levels.peek_level_config(gid).get("enabled") is True


async def test_saklar_cepat_level_off_tetap_off():
    gid = 90005
    levels.set_level_enabled(gid, True)
    ok, _ = await web_dashboard.apply_dashboard_action(gid, "level", "off")
    assert ok is True
    assert web_dashboard.dashboard_controls(gid)["level"] == "off"
    assert web_dashboard.dashboard_controls(gid)["level"] == "off"   # baca kedua


def test_tombol_kontrol_cepat_mengikuti_keadaan():
    gid = 90006
    levels.set_level_enabled(gid, True)
    hidup = web_dashboard.render_controls_block(gid, "tok")
    assert "Level &amp; XP" in hidup or "Level & XP" in hidup
    assert "Nonaktifkan" in hidup                   # tombol = aksi berikutnya
    assert 'value="off"' in hidup

    levels.set_level_enabled(gid, False)
    mati = web_dashboard.render_controls_block(gid, "tok")
    assert "Aktifkan" in mati and 'value="on"' in mati
    assert mati.count('action="/api/aksi"') == 5     # 3 saklar + 2 pilihan


# ==============================================================================
# MENU HAMBURGER (tanpa JavaScript)
# ==============================================================================
def test_halaman_punya_menu_hamburger_dan_anchor():
    page = web_dashboard.render_dashboard_html(status={}, usage={}, levels={})
    assert "☰ Menu" in page
    assert 'id="nav-buka"' in page and 'for="nav-buka"' in page
    assert "#nav-buka:checked ~ nav.menu" in page     # CSS murni, tanpa JS
    for anchor in ("p-status", "p-setelan", "p-kirim", "p-tiket", "p-panel", "p-riwayat"):
        assert f'id="{anchor}"' in page
        assert f'href="#{anchor}"' in page
    assert "position: sticky" in page                 # header menempel saat digulir


def test_menu_hanya_jadi_hamburger_di_layar_kecil():
    page = web_dashboard.render_dashboard_html(status={}, usage={}, levels={})
    assert "@media (max-width: 820px)" in page
    assert ".menu-btn { display: inline-block; }" in page


# ==============================================================================
# REDIRECT SETELAH SIMPAN (303 → kembali ke panel yang sama)
# ==============================================================================
class _Guild:
    def __init__(self, gid=GID):
        self.id = gid
        self.name = "Server Uji"
        self.member_count = 3
        self.channels = []
        self.roles = []


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
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "tok-ux")

    assert await web_dashboard.start_dashboard(bot) is True
    try:
        async with aiohttp.ClientSession() as session:
            return await fn(session, f"http://127.0.0.1:{port}")
    finally:
        await web_dashboard.stop_dashboard()


async def test_simpan_setelan_redirect_ke_panel_dan_tampilkan_pesan(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/aksi",
            data={"token": "tok-ux", "guild": str(GID),
                  "action": "set.level.aktif", "value": "off"},
            allow_redirects=False,
        ) as resp:
            assert resp.status == 303
            lokasi = resp.headers["Location"]
            assert "pesan=" in lokasi and "ok=1" in lokasi
            assert lokasi.endswith("#p-setelan")

        # Ikuti redirect: kotak pesan tampil dan nilai sudah nonaktif
        async with session.get(base + lokasi) as resp:
            body = await resp.text()
            assert resp.status == 200
            assert 'class="flash"' in body and "nonaktif" in body
            assert '<option value="off" selected>' in body

        # Nilai tidak balik jadi "on" pada muat berikutnya
        async with session.get(f"{base}/?token=tok-ux&guild={GID}") as resp:
            assert '<option value="off" selected>' in await resp.text()
        assert levels.is_leveling_active(GID) is False

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_simpan_gagal_tetap_halaman_hasil_dengan_anchor(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/aksi",
            data={"token": "tok-ux", "guild": str(GID),
                  "action": "set.bukan.kunci", "value": "x"},
            allow_redirects=False,
        ) as resp:
            body = await resp.text()
            assert resp.status == 400
            assert "Kembali ke dashboard" in body
            assert "#p-setelan" in body              # kembali ke panel yang sama

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_kontrol_cepat_redirect_ke_panel_kontrol(monkeypatch, tmp_path):
    bot = _Bot()
    levels.set_level_enabled(GID, True)

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/aksi",
            data={"token": "tok-ux", "guild": str(GID), "action": "level", "value": "off"},
            allow_redirects=False,
        ) as resp:
            assert resp.status == 303
            assert resp.headers["Location"].endswith("#p-kontrol")

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_json_tetap_json_tanpa_redirect(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/aksi",
            json={"token": "tok-ux", "guild": str(GID),
                  "action": "set.level.aktif", "value": "on"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
            assert "aktif" in data["message"]

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


def test_anchor_per_aksi():
    assert web_dashboard._anchor_aksi("set.tiket.aktif") == "p-setelan"
    assert web_dashboard._anchor_aksi("level") == "p-kontrol"
    assert web_dashboard._anchor_konten("buat.panel") == "p-buat"
    assert web_dashboard._anchor_konten("hapus.panel:m1") == "p-konten"
    assert web_dashboard._anchor_konten("banner.panel:m1") == "p-konten"


def test_flash_di_escape():
    assert web_dashboard._flash_box("") == ""
    html_ok = web_dashboard._flash_box("Halo <b>dunia</b>")
    assert "&lt;b&gt;" in html_ok and 'class="flash"' in html_ok
    html_gagal = web_dashboard._flash_box("Gagal", False)
    assert "flash galat" in html_gagal and "⚠️" in html_gagal
