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
    assert slug == ["", "ai", "sambutan", "inti", "keamanan", "moderasi", "tiket", "konten",
                    "interaksi", "bangun", "giveaway", "kirim", "buat", "panel", "ekspor"]
    assert "uji" not in slug and "setelan" not in slug

    # Semua panel punya halaman — tidak ada yang hilang. Panel pindah halaman
    # saat grup Konten dipecah, jadi urutannya tidak lagi sama dengan PANEL.
    semua = [a for h in web_dashboard.HALAMAN for a in h["panel"]]
    assert sorted(set(semua)) == sorted(web_dashboard.PANEL)
    assert len(semua) == len(set(semua)), "satu panel tidak boleh tampil di dua halaman"


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
    assert web_dashboard.halaman_dari_anchor("p-gambar") == "ai"
    assert web_dashboard.halaman_dari_anchor("p-ai-settings") == "ai"
    assert web_dashboard.halaman_dari_anchor("p-privasi") == "ai"
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
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
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

        # Cookie sesi yang sama dipakai halaman mana pun…
        async with session.get(f"{base}/inti?guild={GID}") as resp:
            assert resp.status == 200
        # …tetapi tanpa sesi sama sekali tetap 401 (termasuk halaman baru)
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as anon:
            async with anon.get(f"{base}/inti?guild={GID}") as resp:
                assert resp.status == 401

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_bookmark_lama_dialihkan_ke_halaman_baru(monkeypatch, tmp_path):
    bot = _Bot()

    async def skenario(session, base):
        # Redirect internal tidak lagi membawa token: sesi sudah di cookie.
        async with session.get(
            f"{base}/?token={TOKEN}&guild={GID}&halaman=setelan", allow_redirects=False
        ) as resp:
            assert resp.status == 303
            assert resp.headers["Location"] == f"/inti?guild={GID}"

        async with session.get(
            f"{base}/uji?token={TOKEN}&guild={GID}", allow_redirects=False
        ) as resp:
            assert resp.status == 303
            assert resp.headers["Location"] == f"/ai?guild={GID}"

        # Halaman yang sama tidak me-redirect terus-menerus: kunjungan dengan
        # `?token=` sekali dialihkan (token dibuang), lalu 200 tanpa redirect.
        async with session.get(
            f"{base}/inti?token={TOKEN}&guild={GID}&halaman=inti", allow_redirects=False
        ) as resp:
            assert resp.status == 303
            tujuan = resp.headers["Location"]
            assert "token=" not in tujuan
        async with session.get(f"{base}/inti?guild={GID}", allow_redirects=False) as resp:
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
            assert resp.headers["Location"].startswith(f"/bangun?guild={GID}")
        assert sb.ambil_siap(GID) is not None
        audit = dashboard_admin.audit_terakhir(GID, limit=1)[0]
        assert audit["aksi"] == "bangun.tema" and audit["nilai"] == "tema:coding"
        async with session.get(f"{base}/bangun?token={TOKEN}&guild={GID}") as resp:
            body = await resp.text()
            assert resp.status == 200
            assert 'id="p-bangun"' in body
            assert "Pratinjau menunggu keputusan" in body
            assert "Belum ada struktur yang dibuat" in body

        # Tanpa token di body, cookie sesi dipakai → tetap terautentikasi.
        # Penolakan tanpa kredensial apa pun diuji di klien anonim.
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as anon:
            async with anon.post(
                f"{base}/api/bangun", data={"guild": str(GID), "action": "terapkan"}
            ) as resp:
                assert resp.status == 401

    try:
        await _jalankan(monkeypatch, bot, skenario, tmp_path)
    finally:
        sb.reset_state()


# ==============================================================================
# DAFTAR ISI & KELOMPOK MENU (keterbacaan halaman panjang)
# ==============================================================================
def _halaman_html(slug: str) -> str:
    """HTML satu halaman dashboard, dirender lewat jalur produksi."""
    from web_dashboard.tampilan import susun_isi

    data = web_dashboard.tampilan._data_halaman({}, {}, {})
    data.update(web_dashboard.tampilan._blok_halaman({}))
    return susun_isi(slug, data)


def test_daftar_isi_menautkan_semua_bagian_halaman_panjang():
    """Halaman dengan banyak bagian wajib punya pintasan di atas."""
    from web_dashboard.halaman import daftar_isi_dari_isi

    isi = _halaman_html("konten")
    nav = daftar_isi_dari_isi(isi)
    assert 'class="daftar-isi"' in nav
    assert "Isi halaman" in nav
    # Setiap tautan daftar isi harus benar-benar menunjuk anchor yang ada.
    anchor = re.findall(r'href="#(p-[a-z0-9-]+)"', nav)
    assert len(anchor) >= 2
    for a in anchor:
        assert f'id="{a}"' in isi, f"anchor {a} tidak ada di halaman"


def test_daftar_isi_menangkap_sub_bagian_di_dalam_panel():
    """Sub-bagian bersarang ikut terdaftar, bukan hanya panel induknya.

    Halaman Konten menyimpan 7 fitur sebagai blok ber-id `p-*` di dalam satu
    panel induk. Tanpa ini, daftar isi hanya menampilkan 2 tautan.
    """
    from web_dashboard.halaman import daftar_isi_dari_isi

    html = (
        '<div class="panel" id="p-konten"><h2>Konten</h2>'
        '<div class="subpanel" id="p-tag"><h3>Tag jawaban</h3></div>'
        '<div class="subpanel" id="p-curhat"><h3>Curhat anonim</h3></div>'
        '<div class="subpanel" id="p-sosial"><h3>Notifikasi sosial</h3></div>'
        "</div>"
        '<div class="panel" id="p-statistik"><h2>Statistik</h2></div>'
    )
    nav = daftar_isi_dari_isi(html)
    jumlah = re.search(r"Isi halaman · (\d+) bagian", nav)
    assert jumlah and int(jumlah.group(1)) == 5
    assert "Tag jawaban" in nav and "Curhat anonim" in nav
    assert 'href="#p-tag"' in nav


def test_halaman_satu_bagian_tidak_diberi_daftar_isi():
    """Jangan menambah kebisingan kalau halaman hanya punya satu bagian."""
    from web_dashboard.halaman import daftar_isi_dari_isi

    assert daftar_isi_dari_isi('<div class="panel" id="p-panel"><h2>Satu</h2></div>') == ""


def test_render_dashboard_html_menyisipkan_daftar_isi():
    html = web_dashboard.tampilan.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="konten", keterangan="Uji daftar isi"
    )
    assert 'class="daftar-isi"' in html
    assert html.index("daftar-isi") < html.index('id="p-konten"')


def test_menu_dikelompokkan_dan_tidak_ada_halaman_hilang():
    from web_dashboard.halaman import HALAMAN, render_menu

    menu = render_menu("konten", TOKEN, GID)
    judul = re.findall(r'class="menu-kelompok-judul">([^<]+)<', menu)
    assert judul == ["Pemantauan", "Anggota &amp; pesan", "Keamanan", "Konten", "Lainnya"]
    # Setiap halaman tetap muncul di menu meski dikelompokkan.
    for h in HALAMAN:
        assert f">{h['menu']}</a>" in menu
    assert 'aria-current="page"' in menu


# ==============================================================================
# PEMECAHAN HALAMAN KONTEN
# ==============================================================================
def test_konten_dipecah_jadi_dua_halaman():
    """17 setelan + 9 panel terlalu padat untuk satu halaman."""
    slug = [h["slug"] for h in web_dashboard.HALAMAN]
    assert "konten" in slug and "interaksi" in slug
    halaman = {h["slug"]: h for h in web_dashboard.HALAMAN}
    assert "p-interaksi" in halaman["interaksi"]["panel"]
    # Panel interaksi tidak lagi menumpang di halaman konten.
    for panel in ("p-tag", "p-pantau", "p-curhat", "p-sosial", "p-voice", "p-musik", "p-info"):
        assert panel not in halaman["konten"]["panel"]


def test_setiap_setelan_konten_punya_tepat_satu_halaman():
    """Tidak boleh ada setelan yang hilang atau tampil di dua halaman."""
    from collections import Counter

    kunci = web_dashboard.fitur_grup("konten")
    assert len(kunci) == 17
    peta = Counter(web_dashboard.HALAMAN_SETELAN[k] for k in kunci)
    assert set(peta) == {"konten", "interaksi"}
    assert sum(peta.values()) == 17
    # Kunci halaman hanya mengembalikan setelan miliknya.
    assert set(web_dashboard.kunci_halaman("interaksi")) <= set(kunci)
    assert not (set(web_dashboard.kunci_halaman("konten")) & set(web_dashboard.kunci_halaman("interaksi")))


def test_halaman_konten_lebih_ringan_setelah_dipecah():
    """Bukti dampak: form interaksi tidak lagi menumpang di halaman konten."""
    a = web_dashboard.render_dashboard_html(status={}, usage={}, levels={}, halaman="konten")
    b = web_dashboard.render_dashboard_html(status={}, usage={}, levels={}, halaman="interaksi")
    assert 'id="p-konten"' in a and 'id="p-konten"' not in b
    assert 'id="p-interaksi"' in b and 'id="p-interaksi"' not in a
    # Setelan yang dirender tiap halaman tidak beririsan.
    dari_a = set(web_dashboard.kunci_halaman("konten"))
    dari_b = set(web_dashboard.kunci_halaman("interaksi"))
    assert dari_a and dari_b and not (dari_a & dari_b)


def test_anchor_panel_interaksi_menunjuk_halaman_baru():
    for panel in ("p-tag", "p-pantau", "p-curhat", "p-sosial", "p-voice", "p-musik", "p-info"):
        assert web_dashboard.ANCHOR_HALAMAN[panel] == "interaksi", panel
    assert web_dashboard.ANCHOR_HALAMAN["p-konten"] == "konten"
