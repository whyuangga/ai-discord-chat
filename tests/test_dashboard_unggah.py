"""Uji unggah banner dashboard: validasi gambar, simpan, pakai di embed/panel, & HTTP."""

from __future__ import annotations

import io
import socket

import aiohttp

import dashboard_pesan as dp
import dashboard_unggah as du
import web_dashboard

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 120
GIF = b"GIF89a" + b"\x00" * 40


class _Medan:
    """Tiruan `aiohttp.web.FileField`."""

    def __init__(self, data: bytes, nama: str):
        self.filename = nama
        self.file = io.BytesIO(data)


async def _tanpa_disk(*_a, **_k):
    return None


def _siap(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.delenv("DASHBOARD_UPLOAD_MB", raising=False)


# ==============================================================================
# VALIDASI
# ==============================================================================
def test_periksa_menerima_gambar_valid():
    assert du.periksa(PNG, "banner.png") == ("png", "")
    assert du.periksa(JPG, "banner.jpg")[0] == "jpg"
    assert du.periksa(GIF, "animasi.gif")[0] == "gif"
    webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 10
    assert du.periksa(webp, "foto.webp")[0] == "webp"


def test_periksa_menolak_berkas_berbahaya(monkeypatch):
    monkeypatch.delenv("DASHBOARD_UPLOAD_MB", raising=False)
    assert "bukan gambar" in du.periksa(b"MZ\x90\x00executable", "virus.png")[1]
    assert "Format harus" in du.periksa(PNG, "banner.exe")[1]
    assert "bukan JPEG" in du.periksa(PNG, "banner.jpg")[1]
    assert "kosong" in du.periksa(b"", "banner.png")[1]


def test_periksa_menghormati_batas_ukuran(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    monkeypatch.setenv("DASHBOARD_UPLOAD_MB", "1")
    besar = PNG + b"\x00" * (1024 * 1024)
    assert "melebihi 1 MB" in du.periksa(besar, "besar.png")[1]
    assert du.batas_mb() == 1

    monkeypatch.setenv("DASHBOARD_UPLOAD_MB", "99")
    assert du.batas_mb() == 25          # dibatasi jaring aman


# ==============================================================================
# SIMPAN / DAFTAR / HAPUS
# ==============================================================================
def test_simpan_daftar_baca_dan_hapus(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    gid = 501001

    record, galat = du.simpan(gid, PNG, "banner.png")
    assert galat == "" and record and record["nama"].endswith(".png")
    nama = record["nama"]
    assert nama.startswith(f"{gid}_")

    daftar = du.daftar(gid)
    assert len(daftar) == 1 and daftar[0]["nama"] == nama
    assert du.jumlah(gid) == 1
    assert du.baca(gid, nama) == PNG
    assert du.tipe(nama) == "image/png"

    assert du.hapus(gid, nama) is True
    assert du.daftar(gid) == []
    assert du.hapus(gid, nama) is False


def test_kepemilikan_mencegah_path_traversal(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    du.simpan(502001, PNG, "a.png")

    assert du.berkuasa(502001, du.daftar(502001)[0]["nama"]) is True
    assert du.berkuasa(999999, du.daftar(502001)[0]["nama"]) is False
    assert du.baca(999999, du.daftar(502001)[0]["nama"]) is None
    assert du.baca(502001, "../rahasia.png") is None
    assert du.baca(502001, "502001_x.png/../../etc/passwd") is None
    assert du.hapus(502001, "../apa.png") is False


def test_kuota_banner_per_server(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    monkeypatch.setattr(du, "MAX_PER_GUILD", 3)
    gid = 503001

    for _ in range(3):
        record, galat = du.simpan(gid, PNG, "a.png")
        assert galat == ""
    record, galat = du.simpan(gid, PNG, "a.png")
    assert record is None and "penuh" in galat


def test_nama_berkas_selalu_unik(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    nama = {du.simpan(504001, PNG, "sama.png")[0]["nama"] for _ in range(3)}
    assert len(nama) == 3


# ==============================================================================
# SIAPKAN (dipakai form kirim & panel)
# ==============================================================================
def test_siapkan_dari_unggahan_baru(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    gid = 505001

    berkas, galat, nama = du.siapkan(gid, _Medan(PNG, "banner.png"))
    assert galat == "" and berkas is not None and nama.endswith(".png")
    assert berkas.filename == nama
    assert du.jumlah(gid) == 1            # unggahan otomatis tersimpan


def test_siapkan_dari_banner_tersimpan(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    gid = 505002
    record, _ = du.simpan(gid, PNG, "banner.png")

    berkas, galat, nama = du.siapkan(gid, None, record["nama"])
    assert galat == "" and berkas is not None and nama == record["nama"]

    berkas, galat, nama = du.siapkan(gid, None, "tidak-ada.png")
    assert berkas is None and "tidak ditemukan" in galat

    assert du.siapkan(gid) == (None, "", "")


def test_siapkan_menolak_berkas_palsu(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    berkas, galat, nama = du.siapkan(505003, _Medan(b"MZ\x90", "virus.png"))
    assert berkas is None and "bukan gambar" in galat
    assert du.jumlah(505003) == 0


# ==============================================================================
# KIRIM & PANEL DENGAN BANNER
# ==============================================================================
class _Channel:
    def __init__(self, cid=11, gid=1234):
        self.id = cid
        self.mention = f"<#{cid}>"
        self.guild = type("G", (), {"id": gid, "name": "Server Uji"})()
        self.terkirim = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return type("M", (), {"id": 9})()


class _Bot:
    guilds: list = []

    def __init__(self, ch):
        self.ch = ch

    def get_guild(self, gid):
        return type("G", (), {"id": gid, "name": "Server Uji"})()

    def get_channel(self, cid):
        return self.ch if self.ch.id == int(cid) else None


async def test_kirim_dengan_banner_memakai_attachment(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    ch = _Channel()
    berkas, _galat, nama = du.siapkan(1234, _Medan(PNG, "banner.png"))

    ok, pesan = await dp.kirim(
        _Bot(ch), 1234, {"channel": "11", "judul": "Halo", "isi": "Isi"}, banner=berkas
    )
    assert ok is True and "Terkirim" in pesan
    kiriman = ch.terkirim[-1]
    assert kiriman["file"].filename == nama
    assert kiriman["embed"].image.url == f"attachment://{nama}"


async def test_kirim_banner_menimpa_url_gambar(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)
    ch = _Channel()
    berkas, _, _nama = du.siapkan(1234, _Medan(PNG, "banner.png"))

    await dp.kirim(
        _Bot(ch), 1234,
        {"channel": "11", "isi": "Isi", "gambar": "https://contoh.id/a.png"},
        banner=berkas,
    )
    assert ch.terkirim[-1]["embed"].image.url.startswith("attachment://")


async def test_kirim_dengan_banner_lewat_webhook(tmp_path, monkeypatch):
    import webhook_identity

    _siap(tmp_path, monkeypatch)
    ch = _Channel()
    berkas, _, nama = du.siapkan(1234, _Medan(PNG, "banner.png"))
    tercatat = {}

    async def _palsu(channel, **kwargs):
        tercatat.update(kwargs)
        return True, ""

    monkeypatch.setattr(webhook_identity, "kirim_sebagai", _palsu)
    monkeypatch.setattr(webhook_identity, "save_to_disk", _tanpa_disk)

    ok, _ = await dp.kirim(
        _Bot(ch), 1234,
        {"channel": "11", "isi": "Isi", "identitas": "📢 Pengumuman"},
        banner=berkas,
    )
    assert ok is True
    assert tercatat["berkas"].filename == nama


async def test_buat_panel_meneruskan_banner(tmp_path, monkeypatch):
    import menu_builder

    _siap(tmp_path, monkeypatch)
    ch = _Channel()
    berkas, _, nama = du.siapkan(1234, _Medan(PNG, "banner.png"))
    dipakai = {}

    monkeypatch.setattr(menu_builder, "create_menu", lambda *a, **k: {"id": "m1", "title": "Pusat"})
    monkeypatch.setattr(menu_builder, "save_menus_to_disk", _tanpa_disk)

    async def _send_panel(_bot, _menu, _channel, **kwargs):
        dipakai.update(kwargs)
        return type("M", (), {"id": 5})()

    monkeypatch.setattr(menu_builder, "send_panel", _send_panel)

    ok, _ = await dp.buat_panel(
        _Bot(ch), 1234, {"judul": "Pusat", "channel": "11"}, banner=berkas
    )
    assert ok is True
    assert dipakai["banner_file"].filename == nama


# ==============================================================================
# HTTP
# ==============================================================================
async def test_http_unggah_pratinjau_dan_kirim(tmp_path, monkeypatch):
    _siap(tmp_path, monkeypatch)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "token-up")

    ch = _Channel()
    assert await web_dashboard.start_dashboard(_Bot(ch)) is True
    base = f"http://127.0.0.1:{port}"
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            # Unggah tanpa token → 401
            form = aiohttp.FormData()
            form.add_field("token", "salah")
            form.add_field("guild", "1234")
            form.add_field("action", "unggah.simpan")
            form.add_field("banner", PNG, filename="banner.png", content_type="image/png")
            async with session.post(f"{base}/api/unggah", data=form) as resp:
                assert resp.status == 401

            # Unggah sah → tersimpan
            form = aiohttp.FormData()
            form.add_field("token", "token-up")
            form.add_field("guild", "1234")
            form.add_field("action", "unggah.simpan")
            form.add_field("banner", PNG, filename="banner.png", content_type="image/png")
            async with session.post(f"{base}/api/unggah", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "Banner tersimpan" in body
            daftar = du.daftar(1234)
            assert len(daftar) == 1
            nama = daftar[0]["nama"]

            # Pratinjau: cookie sesi cukup, tanpa sesi ditolak 401
            async with session.get(f"{base}/api/unggahan/{nama}?guild=1234") as resp:
                assert resp.status == 200
            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as anon:
                async with anon.get(f"{base}/api/unggahan/{nama}?guild=1234") as resp:
                    assert resp.status == 401
            async with session.get(
                f"{base}/api/unggahan/{nama}?token=token-up&guild=1234"
            ) as resp:
                assert resp.status == 200
                assert resp.content_type == "image/png"
                assert await resp.read() == PNG
            async with session.get(
                f"{base}/api/unggahan/1234_../etc/passwd?token=token-up&guild=1234"
            ) as resp:
                assert resp.status == 404

            # Unggah berkas palsu ditolak dengan pesan jelas
            form = aiohttp.FormData()
            form.add_field("token", "token-up")
            form.add_field("guild", "1234")
            form.add_field("action", "unggah.simpan")
            form.add_field("banner", b"MZ\x90\x00", filename="virus.png",
                           content_type="image/png")
            async with session.post(f"{base}/api/unggah", data=form) as resp:
                body = await resp.text()
                # Gagal → kembali ke panel dengan kotak ⚠️ (bukan halaman buntu)
                assert resp.status == 200 and "ok=0" in str(resp.url)
                assert "bukan gambar" in body and 'class="flash galat"' in body

            # Kirim embed memakai banner tersimpan
            form = aiohttp.FormData()
            form.add_field("token", "token-up")
            form.add_field("guild", "1234")
            form.add_field("action", "kirim")
            form.add_field("channel", "11")
            form.add_field("isi", "Dengan banner")
            form.add_field("banner_tersimpan", nama)
            async with session.post(f"{base}/api/kirim", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "Terkirim" in body
            kiriman = ch.terkirim[-1]
            assert kiriman["file"].filename == nama
            assert kiriman["embed"].image.url == f"attachment://{nama}"

            # Halaman /kirim menampilkan galeri banner
            async with session.get(f"{base}/kirim?token=token-up&guild=1234") as resp:
                body = await resp.text()
                assert "Banner &amp; gambar" in body
                assert nama in body

            # Hapus banner
            form = aiohttp.FormData()
            form.add_field("token", "token-up")
            form.add_field("guild", "1234")
            form.add_field("action", f"hapus.banner:{nama}")
            async with session.post(f"{base}/api/unggah", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "dihapus" in body
            assert du.daftar(1234) == []
    finally:
        await web_dashboard.stop_dashboard()


async def test_unggahan_kebesaran_ditolak_dengan_pesan(tmp_path, monkeypatch):
    """Ukuran berkas diperiksa sebelum disimpan, dengan pesan yang jelas."""
    _siap(tmp_path, monkeypatch)
    monkeypatch.setattr(du, "batas_byte", lambda: 2048)   # 2 KB untuk uji cepat

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "token-up")

    ch = _Channel()
    assert await web_dashboard.start_dashboard(_Bot(ch)) is True
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            form = aiohttp.FormData()
            form.add_field("token", "token-up")
            form.add_field("guild", "1234")
            form.add_field("action", "unggah.simpan")
            form.add_field("banner", PNG + b"\x00" * 5000, filename="besar.png",
                           content_type="image/png")
            async with session.post(f"{base_url(port)}/api/unggah", data=form) as resp:
                body = await resp.text()
                # Ditolak oleh validasi ukuran (bukan 413 bawaan aiohttp 1 MB),
                # lalu kembali ke panel dengan kotak ⚠️.
                assert resp.status == 200 and "ok=0" in str(resp.url)
                assert "melebihi" in body and 'class="flash galat"' in body
    finally:
        await web_dashboard.stop_dashboard()


def base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


async def test_batas_body_aiohttp_mengikuti_setelan_unggah(tmp_path, monkeypatch):
    """Batas bawaan aiohttp hanya 1 MB — harus dinaikkan agar banner 5 MB lolos."""
    _siap(tmp_path, monkeypatch)
    monkeypatch.setenv("DASHBOARD_UPLOAD_MB", "5")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "token-up")

    ch = _Channel()
    assert await web_dashboard.start_dashboard(_Bot(ch)) is True
    try:
        besar = PNG + b"\x00" * (3 * 1024 * 1024)     # 3 MB: > 1 MB, < 5 MB
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            form = aiohttp.FormData()
            form.add_field("token", "token-up")
            form.add_field("guild", "1234")
            form.add_field("action", "unggah.simpan")
            form.add_field("banner", besar, filename="banner.png", content_type="image/png")
            async with session.post(f"{base_url(port)}/api/unggah", data=form) as resp:
                body = await resp.text()
                assert resp.status == 200 and "Banner tersimpan" in body
        assert du.jumlah(1234) == 1
    finally:
        await web_dashboard.stop_dashboard()
