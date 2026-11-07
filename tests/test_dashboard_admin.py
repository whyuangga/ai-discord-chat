"""Uji panel admin dashboard: registry setelan, audit, & endpoint HTTP baru."""

from __future__ import annotations

import asyncio
import json
import socket

import aiohttp

import dashboard_admin
import dashboard_ui
import levels
import web_dashboard


# ==============================================================================
# REGISTRY
# ==============================================================================
def test_registry_konsisten():
    kunci = [item["kunci"] for item in dashboard_admin.FITUR_LIST]
    assert len(kunci) == len(set(kunci)), "kunci setelan harus unik"
    assert len(kunci) >= 35, "dashboard harus mencakup sebagian besar fitur"

    for item in dashboard_admin.FITUR_LIST:
        assert item["jenis"] in {"saklar", "pilihan", "channel", "channels", "role", "teks", "angka"}
        assert callable(item["nilai"]) and callable(item["simpan"])
        if item["jenis"] == "pilihan":
            assert item["opsi"], f"{item['kunci']} butuh daftar opsi"

    # Setiap kunci di grup harus terdaftar, dan sebaliknya semua fitur tampil di grup.
    di_grup = [k for grup in dashboard_admin.GRUP for k in grup["fitur"]]
    assert len(di_grup) == len(set(di_grup)), "satu fitur hanya boleh muncul sekali"
    assert set(di_grup) == set(kunci)


def test_read_values_selalu_string_dan_aman():
    nilai = dashboard_admin.read_values(424242)
    assert set(nilai) == set(dashboard_admin.FITUR)
    assert all(isinstance(v, str) for v in nilai.values())
    assert nilai["level.aktif"] in {"on", "off"}
    assert nilai["antispam.mode"] in {"off", "lapor", "hapus", "timeout"}


def test_ringkasan_berisi_grup():
    data = dashboard_admin.ringkasan()
    assert data["fitur"] == len(dashboard_admin.FITUR)
    assert len(data["grup"]) == len(dashboard_admin.GRUP)
    assert all(g["jumlah"] > 0 for g in data["grup"])


# ==============================================================================
# APPLY & AUDIT
# ==============================================================================
async def _audit_bersih(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_admin, "AUDIT_FILE", tmp_path / "dashboard_audit.json")
    monkeypatch.setattr(dashboard_admin, "DATA_DIR", tmp_path)
    dashboard_admin.reset_cache()


async def test_apply_setelan_saklar_dan_pilihan(tmp_path, monkeypatch):
    await _audit_bersih(tmp_path, monkeypatch)
    gid = 987001

    ok, pesan = await dashboard_admin.apply(gid, "level.aktif", "off")
    assert ok is True and "nonaktif" in pesan
    # Mematikan leveling = konfigurasi dilepas, jadi dibaca lewat is_leveling_active.
    assert levels.is_leveling_active(gid) is False

    ok, _ = await dashboard_admin.apply(gid, "level.aktif", "on")
    assert ok is True and levels.is_leveling_active(gid) is True

    ok, pesan = await dashboard_admin.apply(gid, "antispam.mode", "timeout")
    assert ok is True and "timeout" in pesan
    assert dashboard_admin.read_values(gid)["antispam.mode"] == "timeout"


async def test_apply_menolak_kunci_dan_nilai_ngawur(tmp_path, monkeypatch):
    await _audit_bersih(tmp_path, monkeypatch)

    ok, pesan = await dashboard_admin.apply(11, "tidak.ada", "on")
    assert ok is False and "tidak dikenal" in pesan

    ok, pesan = await dashboard_admin.apply(11, "raid.aksi", "hapus-semua")
    assert ok is False and "tidak termasuk pilihan" in pesan

    ok, pesan = await dashboard_admin.apply(0, "level.aktif", "on")
    assert ok is False and "tidak dikenali" in pesan


async def test_apply_channel_dan_keterangan(tmp_path, monkeypatch):
    await _audit_bersih(tmp_path, monkeypatch)
    gid = 987002

    ok, pesan = await dashboard_admin.apply(gid, "tiket.log", "555")
    assert ok is True and "555" in pesan
    assert dashboard_admin.read_values(gid)["tiket.log"] == "555"

    ok, pesan = await dashboard_admin.apply(gid, "tiket.log", "0")
    assert ok is True and "Log tiket" in pesan
    assert dashboard_admin.read_values(gid)["tiket.log"] in ("", "0")


async def test_audit_tertulis_dan_terbaca(tmp_path, monkeypatch):
    await _audit_bersih(tmp_path, monkeypatch)
    gid = 987003

    await dashboard_admin.apply(gid, "level.aktif", "off")
    await dashboard_admin.apply(gid, "tidak.ada", "on")

    berkas = tmp_path / "dashboard_audit.json"
    assert berkas.exists()
    isi = json.loads(berkas.read_text(encoding="utf-8"))
    assert isi["version"] == 1 and len(isi["items"]) == 2
    assert isi["items"][0]["aksi"] == "level.aktif" and isi["items"][0]["ok"] is True
    assert isi["items"][1]["ok"] is False

    terbaru = dashboard_admin.audit_terakhir(gid, limit=5)
    assert len(terbaru) == 2 and terbaru[0]["aksi"] == "tidak.ada"  # terbaru dulu
    assert dashboard_admin.audit_terakhir(999, limit=5) == []


async def test_audit_dibatasi_jumlah_maksimal(tmp_path, monkeypatch):
    await _audit_bersih(tmp_path, monkeypatch)
    monkeypatch.setattr(dashboard_admin, "MAX_AUDIT", 3)
    for _ in range(5):
        await dashboard_admin.apply(987004, "level.aktif", "on")
    isi = json.loads((tmp_path / "dashboard_audit.json").read_text(encoding="utf-8"))
    assert len(isi["items"]) == 3


def test_normalisasi_masukan():
    assert dashboard_admin.normalisasi("level.aktif", " AKTIF ") == "on"
    assert dashboard_admin.normalisasi("level.aktif", "nonaktif") == "off"
    assert dashboard_admin.normalisasi("antispam.mode", "Timeout") == "timeout"
    assert dashboard_admin.normalisasi("prefix", " ! ") == "!"


# ==============================================================================
# UI FORM
# ==============================================================================
def test_render_setelan_block_berisi_form_dan_nilai():
    nilai = dashboard_admin.read_values(123)
    html = dashboard_ui.render_setelan_block(nilai, None, 123, "tok-uji")

    assert html.count('action="/api/aksi"') == len(dashboard_admin.FITUR)
    assert 'name="action" value="set.level.aktif"' in html
    assert 'name="token" value="tok-uji"' in html
    assert "Inti, level" in html and "Keamanan" in html
    assert "🛡️" in html


def test_kontrol_html_memilih_jenis_yang_tepat():
    assert dashboard_ui.kontrol_html("level.aktif", "on", None, 1).startswith("<select")
    assert 'selected' in dashboard_ui.kontrol_html("level.aktif", "on", None, 1)
    assert "type=\"number\"" in dashboard_ui.kontrol_html("tiket.maks", "2", None, 1)
    assert "type=\"text\"" in dashboard_ui.kontrol_html("prefix", "!", None, 1)


class _Channel:
    def __init__(self, cid, name, *, kategori=False, position=0):
        self.id = cid
        self.name = name
        self.position = position
        self.type = type("T", (), {"name": "category" if kategori else "text"})()
        self.mention = f"<#{cid}>"
        self.guild = None
        self.terkirim = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return type("M", (), {"id": 1})()


class _Role:
    def __init__(self, rid, name, position=1, default=False):
        self.id = rid
        self.name = name
        self.position = position
        self.is_default = default


class _Guild:
    def __init__(self, gid=1234, nama="Server Uji"):
        self.id = gid
        self.name = nama
        self.member_count = 10
        self.channels = [
            _Channel(11, "umum", position=1),
            _Channel(12, "log", position=2),
            _Channel(13, "Kategori Tiket", kategori=True, position=0),
        ]
        self.roles = [_Role(1234, "@everyone", default=True), _Role(77, "Staf", position=5)]
        for ch in self.channels:
            ch.guild = self


class _Bot:
    started_at = 0.0
    latency = 0.05
    user = type("U", (), {"name": "BotUji"})()

    def __init__(self):
        self.guild_list = [_Guild()]
        self.guilds = self.guild_list

    def get_guild(self, gid):
        for g in self.guild_list:
            if g.id == int(gid):
                return g
        return None

    def get_channel(self, cid):
        for g in self.guild_list:
            for ch in g.channels:
                if ch.id == int(cid):
                    return ch
        return None


def test_pilihan_channel_dan_role_dari_cache_bot():
    bot = _Bot()
    channel = dashboard_ui.pilihan_channel(bot, 1234)
    assert channel[0] == ("0", "— tidak dipakai —")
    assert ("11", "# umum") in channel
    assert all("Kategori" not in label for _, label in channel)

    kategori = dashboard_ui.pilihan_channel(bot, 1234, kategori_saja=True)
    assert ("13", "# Kategori Tiket") in kategori

    role = dashboard_ui.pilihan_role(bot, 1234)
    assert ("77", "@ Staf") in role
    assert all(value != "1234" for value, _ in role)   # @everyone dilewati


def test_kontrol_channel_menandai_id_di_luar_server():
    # tiket.log kini multi-channel (checkbox), tapi channel di luar server tetap ditandai
    html = dashboard_ui.kontrol_html("tiket.log", "999999", _Bot(), 1234)
    assert "di luar server ini" in html and f'value="999999" checked' in html
    # Setelan single-channel tetap memakai <select> + opsi "selected"
    tunggal = dashboard_ui.kontrol_html("digest.channel", "999999", _Bot(), 1234)
    assert "di luar server ini" in tunggal and "selected" in tunggal


def test_render_kirim_dan_konten_block():
    kirim = dashboard_ui.render_kirim_block(_Bot(), 1234, "tok")
    assert 'action="/api/kirim"' in kirim
    assert 'name="identitas"' in kirim and 'name="avatar"' in kirim
    assert "# umum" in kirim

    buat = dashboard_ui.render_buat_block(_Bot(), 1234, "tok")
    assert buat.count('action="/api/konten"') == 5
    for aksi in ("buat.pengumuman", "buat.tautan", "buat.panel", "buat.formulir", "buat.pemicu"):
        assert aksi in buat, f"form {aksi} hilang"

    konten = dashboard_ui.render_konten_block(
        1234,
        {"pengumuman": [{"id": "3", "judul": "Tes", "ringkas": "harian 08:00"}], "tautan": []},
        "tok",
    )
    assert "harian 08:00" in konten
    assert "hapus.pengumuman:3" in konten
    assert "Belum ada." in konten


def test_render_audit_block():
    assert "Belum ada perubahan" in dashboard_ui.render_audit_block([])
    html = dashboard_ui.render_audit_block(
        [{"aksi": "level.aktif", "nilai": "off", "ok": True, "waktu": "2026-01-01", "pesan": "ok"}]
    )
    assert "level.aktif" in html and "✅" in html


def test_halaman_dashboard_memuat_semua_blok_baru():
    page = web_dashboard.render_dashboard_html(
        status={"version": "1.0"},
        usage={},
        levels={},
        setelan_block="BLOK-SETELAN",
        kirim_block="BLOK-KIRIM",
        buat_block="BLOK-BUAT",
        konten_block="BLOK-KONTEN",
        audit_block="BLOK-AUDIT",
    )
    for penanda in ("BLOK-SETELAN", "BLOK-KIRIM", "BLOK-BUAT", "BLOK-KONTEN", "BLOK-AUDIT"):
        assert penanda in page
    assert "Kirim pesan" in page and "Riwayat perubahan" in page


# ==============================================================================
# HTTP END-TO-END
# ==============================================================================
async def test_endpoint_baru_dengan_token(tmp_path, monkeypatch):
    await _audit_bersih(tmp_path, monkeypatch)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "token-uji")

    bot = _Bot()
    assert await web_dashboard.start_dashboard(bot) is True
    base = f"http://127.0.0.1:{port}"
    try:
        async with aiohttp.ClientSession() as session:
            # Halaman grup memuat form setelan (dashboard kini satu halaman per grup)
            async with session.get(f"{base}/inti?token=token-uji&guild=1234") as resp:
                body = await resp.text()
                assert resp.status == 200
                assert "Kontrol Cepat" in body and 'id="p-inti"' in body
                assert 'value="set.level.aktif"' in body

            # Halaman /kirim memuat form kirim pesan
            async with session.get(f"{base}/kirim?token=token-uji&guild=1234") as resp:
                body = await resp.text()
                assert resp.status == 200 and "Kirim pesan" in body

            # /api/setelan
            async with session.get(f"{base}/api/setelan?token=token-uji&guild=1234") as resp:
                data = await resp.json()
                assert resp.status == 200
                assert data["ringkasan"]["fitur"] == len(dashboard_admin.FITUR)
                assert data["nilai"]["level.aktif"] == "on"
            async with session.get(f"{base}/api/setelan?guild=1234") as resp:
                assert resp.status == 401

            # Token lewat field form (bukan query/header) → harus diterima
            async with session.post(
                f"{base}/api/aksi",
                data={"token": "token-uji", "guild": "1234",
                      "action": "set.level.aktif", "value": "off"},
            ) as resp:
                body = await resp.text()
                assert resp.status == 200 and "nonaktif" in body
            assert levels.is_leveling_active(1234) is False

            # Token salah di field form → 401
            async with session.post(
                f"{base}/api/aksi",
                data={"token": "salah", "guild": "1234",
                      "action": "set.level.aktif", "value": "on"},
            ) as resp:
                assert resp.status == 401

            # JSON + header tetap jalan untuk otomasi
            async with session.post(
                f"{base}/api/aksi",
                json={"guild": 1234, "action": "set.level.aktif", "value": "on"},
                headers={"X-Dashboard-Token": "token-uji"},
            ) as resp:
                data = await resp.json()
                assert resp.status == 200 and data["ok"] is True

            # Kirim embed ke channel uji
            async with session.post(
                f"{base}/api/kirim",
                data={"guild": "1234", "action": "kirim", "channel": "11",
                      "judul": "Halo", "isi": "Isi uji", "warna": "#5865F2"},
            ) as resp:
                assert resp.status == 401   # tanpa token tetap ditolak
            async with session.post(
                f"{base}/api/kirim",
                data={"token": "token-uji", "guild": "1234", "action": "kirim",
                      "channel": "11", "judul": "Halo", "isi": "Isi uji",
                      "warna": "#5865F2"},
            ) as resp:
                body = await resp.text()
                assert resp.status == 200 and "Terkirim" in body
            terkirim = bot.get_channel(11).terkirim
            assert terkirim and terkirim[-1]["embed"].title == "Halo"

            # Buat pengumuman terjadwal
            async with session.post(
                f"{base}/api/konten",
                data={"token": "token-uji", "guild": "1234", "action": "buat.pengumuman",
                      "channel": "11", "judul": "Rapat", "isi": "Rapat jam 8",
                      "jadwal": "08:00"},
            ) as resp:
                body = await resp.text()
                assert resp.status == 200 and "Pengumuman dibuat" in body

            # Aksi konten tak dikenal ditolak
            async with session.post(
                f"{base}/api/konten",
                data={"token": "token-uji", "guild": "1234", "action": "buat.ngawur"},
            ) as resp:
                # Form HTML: redirect + kotak ⚠️ (JSON tetap 400)
                assert resp.status == 200 and "ok=0" in str(resp.url)
    finally:
        await web_dashboard.stop_dashboard()


def test_refresh_nol_mematikan_meta_refresh():
    tanpa = web_dashboard.render_dashboard_html(status={}, usage={}, levels={}, refresh=0)
    assert "http-equiv=\"refresh\"" not in tanpa
    assert "auto-refresh mati" in tanpa

    pakai = web_dashboard.render_dashboard_html(status={}, usage={}, levels={}, refresh=30)
    assert 'http-equiv="refresh" content="30"' in pakai
    assert "auto-refresh 30s" in pakai


def test_modul_dashboard_tidak_menambah_dependency():
    """Dashboard hanya memakai stdlib + aiohttp/discord yang sudah ada."""
    import ast
    from pathlib import Path

    for berkas in ("dashboard_admin.py", "dashboard_ui.py", "dashboard_pesan.py"):
        isi = Path(berkas).read_text(encoding="utf-8")
        pohon = ast.parse(isi)
        modul = set()
        for node in ast.walk(pohon):
            if isinstance(node, ast.Import):
                modul.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modul.add(node.module.split(".")[0])
        dilarang = {"requests", "flask", "fastapi", "jinja2", "sqlalchemy", "redis", "numpy"}
        assert not (modul & dilarang), f"{berkas} memakai dependency baru: {modul & dilarang}"


def test_dropdown_auto_refresh_di_header():
    """Header punya dropdown interval auto-refresh (form GET, tanpa JavaScript)."""
    dasar = dict(status={}, usage={}, levels={}, token="tok", guild_id=1234)

    html = web_dashboard.render_dashboard_html(
        **dasar, refresh=30, auto_aksi="/inti", auto_dipilih="30"
    )
    assert 'class="pemilih-auto"' in html
    assert 'action="/inti"' in html and 'name="refresh"' in html
    assert 'id="pilih-auto"' in html
    for nilai in ("0", "15", "30", "60", "120", "300"):
        assert f'<option value="{nilai}"' in html
    assert '<option value="auto"' in html            # ikut DASHBOARD_REFRESH_SEC
    assert '<option value="30" selected>' in html
    assert 'name="token" value="tok"' in html and 'name="guild" value="1234"' in html
    assert "auto-refresh 30s" in html

    # Nilai .env → opsi “Ikut .env” yang terpilih
    ikut = web_dashboard.render_dashboard_html(
        **dasar, refresh=25, auto_aksi="/", auto_dipilih="auto"
    )
    assert '<option value="auto" selected>' in ikut
    assert '<option value="30" selected>' not in ikut

    # Angka di luar daftar (mis. dari URL ?refresh=45) tetap tampil & terpilih
    lain = web_dashboard.render_dashboard_html(
        **dasar, refresh=45, auto_aksi="/", auto_dipilih="45"
    )
    assert '<option value="45" selected>45 detik</option>' in lain

    # Mati → tidak ada meta refresh, opsi Mati terpilih
    mati = web_dashboard.render_dashboard_html(
        **dasar, refresh=0, auto_aksi="/", auto_dipilih="0"
    )
    assert "auto-refresh mati" in mati
    assert '<option value="0" selected>' in mati
    assert 'http-equiv="refresh"' not in mati

    # Tanpa `auto_aksi` (render manual) tidak memunculkan form
    polos = web_dashboard.render_dashboard_html(status={}, usage={}, levels={}, refresh=0)
    assert 'class="pemilih-auto"' not in polos


def test_form_auto_bisa_dipanggil_langsung():
    assert web_dashboard.form_auto("") == ""       # tanpa aksi → kosong
    html = web_dashboard.form_auto("/tiket", "abc", 99, 30, "auto")
    assert 'action="/tiket"' in html and "abc" in html and "99" in html
    assert '<option value="auto" selected>' in html


def test_detik_auto_memakai_cookie_lalu_env(monkeypatch):
    class _Req:
        def __init__(self, cookie=""):
            self.cookies = {web_dashboard.COOKIE_AUTO: cookie} if cookie != "" else {}

    assert web_dashboard.detik_auto(_Req(), 30) == 30
    assert web_dashboard.detik_auto(_Req("0"), 30) == 0
    assert web_dashboard.detik_auto(_Req("45"), 30) == 45
    assert web_dashboard.detik_auto(_Req("ngawur"), 30) == 30
    assert web_dashboard.detik_auto(_Req("99999"), 30) == 3600     # dibatasi


def test_http_dropdown_auto_refresh_lewat_header(monkeypatch):
    """Pilih interval di dropdown → cookie tersimpan, meta refresh ikut berubah."""

    async def jalankan():
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
        monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
        monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "token-uji")
        monkeypatch.setattr(web_dashboard, "DASHBOARD_REFRESH_SEC", 30)

        assert await web_dashboard.start_dashboard(_Bot()) is True
        base = f"http://127.0.0.1:{port}/"
        try:
            # `unsafe=True`: aiohttp menolak cookie dari host berupa IP, browser tidak.
            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
                # Tanpa cookie: dropdown menunjuk “Ikut .env”, refresh 30 detik
                async with session.get(f"{base}?token=token-uji&guild=1234") as resp:
                    body = await resp.text()
                    assert 'class="pemilih-auto"' in body
                    assert '<option value="auto" selected>' in body
                    assert "auto-refresh 30s" in body

                # Pilih 60 detik (persis seperti submit form) → 303 + cookie + meta 60
                async with session.get(
                    f"{base}?token=token-uji&guild=1234&refresh=60",
                    allow_redirects=False,
                ) as resp:
                    assert resp.status == 303
                    assert resp.headers["Location"] == "/?token=token-uji&guild=1234"
                    assert resp.cookies[web_dashboard.COOKIE_AUTO].value == "60"

                async with session.get(f"{base}?token=token-uji&guild=1234") as resp:
                    body = await resp.text()
                    assert "auto-refresh 60s" in body
                    assert 'http-equiv="refresh" content="60"' in body
                    assert '<option value="60" selected>' in body
                    assert '<option value="auto" selected>' not in body

                # Pilih “Mati” → cookie 0, tanpa meta refresh
                async with session.get(
                    f"{base}?token=token-uji&guild=1234&refresh=0",
                    allow_redirects=False,
                ) as resp:
                    assert resp.status == 303
                async with session.get(f"{base}?token=token-uji&guild=1234") as resp:
                    body = await resp.text()
                    assert "auto-refresh mati" in body
                    assert 'http-equiv="refresh"' not in body
                    assert '<option value="0" selected>' in body

                # Pilih “Ikut .env” → cookie dibuang, kembali 30 detik
                async with session.get(
                    f"{base}?token=token-uji&guild=1234&refresh=auto", allow_redirects=False
                ) as resp:
                    assert resp.status == 303
                async with session.get(f"{base}?token=token-uji&guild=1234") as resp:
                    body = await resp.text()
                    assert "auto-refresh 30s" in body
                    assert '<option value="auto" selected>' in body

                # Dropdown ikut ke halaman lain & tetap membawa anchor halaman itu
                async with session.get(f"{base}inti?token=token-uji&guild=1234") as resp:
                    body = await resp.text()
                    assert 'action="/inti"' in body
                    assert '<option value="auto" selected>' in body
        finally:
            await web_dashboard.stop_dashboard()

    asyncio.run(jalankan())
