"""Dashboard: unggah kartu sambutan/perpisahan sendiri + tombol tes fitur."""

from __future__ import annotations

import socket

import aiohttp
import pytest

import community_agent
import dashboard_ui
import dashboard_uji
import dashboard_unggah
import web_dashboard
import welcome_media

GID = 4242
TOKEN = "tok-kartu"
PNG = (  # PNG 1×1 transparan
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ==============================================================================
# KARTU SAMBUTAN (data/media)
# ==============================================================================
@pytest.fixture()
def media(tmp_path, monkeypatch):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(welcome_media, "MEDIA_DIR", tmp_path / "media")
    return tmp_path


class _Berkas:
    def __init__(self, data: bytes, nama: str):
        self.file = type("F", (), {"read": lambda self: data})()
        self.filename = nama


def test_jenis_kartu_yang_didukung():
    # Tiga slot agen (sambutan/perpisahan/boost) + latar kartu rank (v1.40).
    assert dashboard_unggah.JENIS_KARTU == ("welcome", "goodbye", "boost", "rank")
    assert dashboard_unggah.KARTU_AGEN == ("welcome", "goodbye", "boost")
    assert dashboard_unggah.normalisasi_kartu("GOODBYE") == "goodbye"
    assert dashboard_unggah.normalisasi_kartu("RANK") == "rank"
    assert dashboard_unggah.normalisasi_kartu("../../etc/passwd") == ""


def test_simpan_kartu_lalu_terbaca_dan_terhapus(media):
    info = dashboard_unggah.kartu_info(GID)
    assert info == {"welcome": None, "goodbye": None, "boost": None, "rank": None}

    ok, pesan = dashboard_unggah.simpan_kartu(GID, _Berkas(PNG, "kartu.png"), "welcome")
    assert ok and "sambutan" in pesan
    assert welcome_media.banner_path(GID, kind="welcome") is not None
    # jenis lain tidak ikut terisi
    assert welcome_media.banner_path(GID, kind="goodbye") is None

    ok, pesan = dashboard_unggah.simpan_kartu(GID, _Berkas(PNG, "bye.png"), "goodbye")
    assert ok
    info = dashboard_unggah.kartu_info(GID)
    assert info["welcome"]["nama"] == f"welcome_{GID}.png"
    assert info["goodbye"]["nama"] == f"goodbye_{GID}.png"

    data, tipe = dashboard_unggah.baca_kartu(GID, "welcome")
    assert data == PNG and tipe == "image/png"

    ok, pesan = dashboard_unggah.hapus_kartu(GID, "welcome")
    assert ok and "dihapus" in pesan
    assert dashboard_unggah.baca_kartu(GID, "welcome") == (None, "application/octet-stream")
    ok, pesan = dashboard_unggah.hapus_kartu(GID, "welcome")
    assert ok is False and "Belum ada" in pesan


def test_kartu_menolak_berkas_palsu_dan_jenis_ngawur(media):
    ok, pesan = dashboard_unggah.simpan_kartu(GID, _Berkas(b"<html>", "x.png"), "welcome")
    assert ok is False and "bukan gambar" in pesan
    ok, pesan = dashboard_unggah.simpan_kartu(GID, _Berkas(PNG, "x.png"), "avatar")
    assert ok is False and "tidak dikenal" in pesan
    ok, pesan = dashboard_unggah.simpan_kartu(GID, None, "welcome")
    assert ok is False and "Pilih berkas" in pesan


def test_panel_kartu_menampilkan_tiga_slot(media):
    # Halaman fitur hanya memuat slotnya sendiri
    html_boost = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("boost",))
    assert html_boost.count('class="kartu-slot"') == 1
    assert "kartu.simpan:boost" in html_boost and "kartu.simpan:welcome" not in html_boost
    html = dashboard_ui.render_kartu_block(GID, TOKEN)
    assert "Kartu sambutan &amp; perpisahan" not in html      # judul ada di panel web_dashboard
    assert html.count('class="kartu-slot"') == 3
    assert "kartu.simpan:welcome" in html and "kartu.simpan:goodbye" in html
    assert html.count("Belum ada gambar") == 3
    assert "set.sambutan.kartu" in html                      # pemilih mode kartu

    dashboard_unggah.simpan_kartu(GID, _Berkas(PNG, "k.png"), "goodbye")
    html = dashboard_unggah and dashboard_ui.render_kartu_block(GID, TOKEN)
    assert f"/api/kartu/goodbye?token={TOKEN}&amp;guild={GID}" in html
    assert "kartu.hapus:goodbye" in html


# ==============================================================================
# TOMBOL TES FITUR
# ==============================================================================
class _Guild:
    id = GID
    name = "Server Uji"
    member_count = 3
    channels: list = []
    roles: list = []
    owner_id = 1                      # pemilik server = akun contoh bawaan tes

    def __init__(self):
        self.me = _Member(1)
        self.members = [_Member(1), _Member(777), _Member(9)]
        self.members[2].bot = True

    def get_member(self, uid):
        for orang in self.members:
            if orang.id == int(uid):
                return orang
        return None


class _Member:
    def __init__(self, uid=1):
        self.id = uid
        self.display_name = "Bintang"
        self.mention = f"<@{uid}>"
        self.bot = False
        self.display_avatar = None


class _Channel:
    def __init__(self, cid, nama):
        self.id, self.name = cid, nama


class _Bot:
    def __init__(self):
        self.guilds = [_Guild()]
        self.user = _Member(1)
        self.latency = 0.01

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GID else None

    def get_channel(self, cid):
        return _Channel(cid, "sambutan") if int(cid) == 505 else None


def test_status_uji_mengikuti_konfigurasi():
    community_agent.set_welcome_config(GID, 505, enabled=True)
    community_agent.set_goodbye_config(GID, 0, enabled=False)
    status = dashboard_uji.status_uji(GID)
    assert status["welcome"]["aktif"] is True and status["welcome"]["channel_id"] == 505
    assert status["goodbye"]["aktif"] is False


async def test_jalankan_uji_mengirim_dan_menolak_bila_mati(monkeypatch):
    from cogs import agent_cog

    dipanggil = {}

    async def pura_pura(bot, guild, member, *, force=False):
        dipanggil["member"] = member.id
        dipanggil["force"] = force
        return "Halo <@1>!"

    monkeypatch.setattr(agent_cog, "trigger_member_welcome", pura_pura)
    community_agent.set_welcome_config(GID, 505, enabled=True)

    # Tanpa mengisi ID apa pun → memakai pemilik server (bukan akun bot)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "welcome")
    assert ok is True and "terkirim" in pesan and "<#505>" in pesan
    assert "pemilik server" in pesan and "**Bintang**" in pesan
    assert dipanggil == {"member": 1, "force": True}

    # Member tertentu lewat ID
    member = dashboard_uji.cari_member(_Bot().guilds[0], "777")
    ok, _ = await dashboard_uji.jalankan_uji(_Bot(), GID, "welcome", member)
    assert ok is True and dipanggil["member"] == 777

    # Fitur mati → tidak memanggil AI sama sekali
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "goodbye")
    assert ok is False and "belum aktif" in pesan

    # Kunci ngawur
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "musik")
    assert ok is False and "tidak dikenal" in pesan


async def test_jalankan_uji_melaporkan_kegagalan_kirim(monkeypatch):
    from cogs import agent_cog

    async def gagal(bot, guild, member, *, force=False):
        return None

    monkeypatch.setattr(agent_cog, "trigger_member_goodbye", gagal)
    community_agent.set_goodbye_config(GID, 404, enabled=True)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "goodbye")
    # Channel 404 tidak ada di cache bot → alasan spesifik, bukan "cek izin"
    assert ok is False and "tidak ada di server ini" in pesan
    community_agent.set_goodbye_config(GID, 505, enabled=True)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "goodbye")
    assert ok is False and "GEMINI_API_KEY" in pesan


def test_panel_uji_punya_tombol_dan_tautan_setelan():
    community_agent.set_welcome_config(GID, 505, enabled=True)
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN)
    # Semua fitur yang punya tes tampil, dikelompokkan per grup
    assert html.count('class="uji-baris"') == len(dashboard_uji.UJI) == 14
    assert html.count("<h3>") == len({item["grup"] for item in dashboard_uji.UJI})
    assert 'action="/api/uji"' in html and "uji.welcome" in html
    assert "👑 Pemilik server" in html                 # subjek default tanpa ID
    assert 'name="opsi_manual"' in html                # bisa tempel @nama/<@id>
    assert "#sambutan" in html                     # nama channel tampil
    assert "Atur dulu" in html                      # fitur yang belum aktif
    assert "1 panggilan AI" in html
    # Fitur tanpa config tetap bisa dites & punya pemilih subjek
    for kunci in ("pengumuman", "panel", "tiket", "honeypot", "tag", "moderasi", "kartu", "ai", "ekspor"):
        assert f'name="action" value="uji.{kunci}"' in html, kunci
    # Fitur ber-config yang belum aktif tetap tampil (dengan tautan Setelan)
    for kunci in ("goodbye", "boost", "digest"):
        assert dashboard_uji.UJI_MAP[kunci]["label"] in html, kunci
    assert "Koran pagi (digest)" in html


# ==============================================================================
# HTTP
# ==============================================================================
async def _jalankan(monkeypatch, bot, fn, tmp_path):
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", TOKEN)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_REFRESH_SEC", 0)

    assert await web_dashboard.start_dashboard(bot) is True
    try:
        async with aiohttp.ClientSession() as session:
            return await fn(session, f"http://127.0.0.1:{port}")
    finally:
        await web_dashboard.stop_dashboard()


async def test_http_unggah_kartu_pratinjau_dan_hapus(monkeypatch, tmp_path):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(welcome_media, "MEDIA_DIR", tmp_path / "media")
    bot = _Bot()
    halaman = f"token={TOKEN}&guild={GID}"

    async def skenario(session, base):
        # Sambutan, pamit, & boost jadi satu halaman: tiga slot ada di sana
        async with session.get(f"{base}/sambutan?{halaman}") as resp:
            body = await resp.text()
            assert resp.status == 200 and 'id="p-sambutan"' in body
            for slot in ("welcome", "goodbye", "boost"):
                assert f"kartu.simpan:{slot}" in body
                assert f'id="p-{slot}"' in body
        # Bookmark /perpisahan dialihkan ke halaman gabungan
        async with session.get(f"{base}/perpisahan?{halaman}", allow_redirects=False) as resp:
            assert resp.status == 303 and resp.headers["Location"].startswith("/sambutan?")

        # Unggah kartu sambutan
        form = aiohttp.FormData()
        form.add_field("token", TOKEN)
        form.add_field("guild", str(GID))
        form.add_field("action", "kartu.simpan:welcome")
        form.add_field("banner", PNG, filename="kartu.png", content_type="image/png")
        async with session.post(
            f"{base}/api/unggah", data=form, allow_redirects=False
        ) as resp:
            assert resp.status == 303
            lokasi = resp.headers["Location"]
            assert lokasi.startswith("/sambutan?") and lokasi.endswith("#p-sambutan")

        # Pratinjau bisa diambil (butuh token)
        async with session.get(f"{base}/api/kartu/welcome?{halaman}") as resp:
            assert resp.status == 200 and await resp.read() == PNG
            assert resp.headers["Content-Type"] == "image/png"
        async with session.get(f"{base}/api/kartu/welcome?guild={GID}") as resp:
            assert resp.status == 401
        async with session.get(f"{base}/api/kartu/goodbye?{halaman}") as resp:
            assert resp.status == 404

        # Halaman kini menampilkan thumbnail
        async with session.get(f"{base}/sambutan?{halaman}") as resp:
            assert f"/api/kartu/welcome?token={TOKEN}" in await resp.text()

        # Hapus
        async with session.post(
            f"{base}/api/unggah",
            data={"token": TOKEN, "guild": str(GID), "action": "kartu.hapus:welcome"},
            allow_redirects=False,
        ) as resp:
            assert resp.status == 303
        assert dashboard_unggah.kartu_info(GID)["welcome"] is None

        # Berkas palsu ditolak dengan pesan (halaman hasil 400)
        form = aiohttp.FormData()
        form.add_field("token", TOKEN)
        form.add_field("guild", str(GID))
        form.add_field("action", "kartu.simpan:welcome")
        form.add_field("banner", b"<html>", filename="x.png", content_type="image/png")
        async with session.post(f"{base}/api/unggah", data=form) as resp:
            body = await resp.text()
            assert resp.status == 200 and "ok=0" in str(resp.url)
            assert "bukan gambar" in body

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_http_halaman_uji_dan_endpoint(monkeypatch, tmp_path):
    from cogs import agent_cog

    async def pura_pura(bot, guild, member, *, force=False):
        return "Halo <@1>!"

    monkeypatch.setattr(agent_cog, "trigger_member_welcome", pura_pura)
    community_agent.set_welcome_config(GID, 505, enabled=True)
    community_agent.set_goodbye_config(GID, 0, enabled=False)   # tes fitur mati
    bot = _Bot()
    halaman = f"token={TOKEN}&guild={GID}"

    async def skenario(session, base):
        # Tiap fitur punya halamannya sendiri (tidak ada lagi /uji gabungan)
        async with session.get(f"{base}/sambutan?{halaman}") as resp:
            body = await resp.text()
            assert resp.status == 200 and 'id="p-sambutan"' in body
            assert "Tes fitur" in body and "uji.welcome" in body
            assert "👣 Pesan perpisahan" in body and "💎 Ucapan boost" in body
            assert 'aria-current="page"' in body
        # Bookmark lama /uji dialihkan ke Ringkasan
        async with session.get(f"{base}/uji?{halaman}", allow_redirects=False) as resp:
            assert resp.status == 303 and resp.headers["Location"].startswith("/?")

        # Tombol tes → 303 kembali ke halaman fiturnya + pesan
        async with session.post(
            f"{base}/api/uji",
            data={"token": TOKEN, "guild": str(GID), "action": "uji.welcome"},
            allow_redirects=False,
        ) as resp:
            assert resp.status == 303
            lokasi = resp.headers["Location"]
            assert lokasi.startswith("/sambutan?") and "pesan=" in lokasi
            assert lokasi.endswith("#p-welcome")

        # JSON tetap JSON
        async with session.post(
            f"{base}/api/uji",
            json={"token": TOKEN, "guild": str(GID), "action": "uji.welcome"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
            assert "terkirim" in data["message"]

        # Fitur mati: form HTML → redirect ⚠️, JSON → 400 + alasan
        async with session.post(
            f"{base}/api/uji",
            data={"token": TOKEN, "guild": str(GID), "action": "uji.goodbye"},
            allow_redirects=False,
        ) as resp:
            assert resp.status == 303 and "ok=0" in resp.headers["Location"]
        async with session.post(
            f"{base}/api/uji",
            json={"token": TOKEN, "guild": str(GID), "action": "uji.goodbye"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 400 and data["ok"] is False
            assert "belum aktif" in data["message"]

        # Tanpa token
        async with session.post(f"{base}/api/uji", data={"guild": str(GID)}) as resp:
            assert resp.status == 401

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


# ==============================================================================
# SEMUA FITUR YANG PUNYA TES
# ==============================================================================
def test_registry_uji_lengkap_dan_berkelompok():
    kunci = [item["kunci"] for item in dashboard_uji.UJI]
    assert kunci == ["welcome", "goodbye", "boost", "pengumuman", "panel",
                     "digest", "tiket", "giveaway", "honeypot", "tag", "moderasi", "kartu", "ai", "ekspor"]
    for item in dashboard_uji.UJI:
        for wajib in ("kunci", "label", "emoji", "grup", "contoh"):
            assert item.get(wajib), (item["kunci"], wajib)
        assert item["kunci"] in dashboard_uji.UJI_MAP


async def test_uji_pengumuman_memakai_yang_tersimpan(monkeypatch):
    import engagement

    dikirim = {}

    async def kirim(bot, aid, guild_id=None):
        dikirim["id"] = aid
        return "ok", {"channel_id": 909}

    monkeypatch.setattr(engagement, "send_announcement_now", kirim)
    engagement.announcements.clear()
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "pengumuman")
    assert ok is False and "Belum ada pengumuman" in pesan

    engagement.announcements[31] = {"guild_id": GID, "title": "Kopi darat"}
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "pengumuman")
    assert ok and dikirim["id"] == 31 and "<#909>" in pesan

    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "uji.pengumuman", opsi="31")
    assert ok


async def test_uji_panel_menyegarkan_panel_terpasang(monkeypatch):
    import menu_builder

    disegarkan = []

    async def refresh(bot, menu):
        disegarkan.append(menu["id"])
        return True

    monkeypatch.setattr(menu_builder, "refresh_panel", refresh)
    monkeypatch.setattr(menu_builder, "list_menus", lambda gid: [])
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "panel")
    assert ok is False and "Belum ada panel" in pesan

    monkeypatch.setattr(
        menu_builder, "list_menus",
        lambda gid: [{"id": "m1", "title": "Panel utama", "message_id": None}],
    )
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "panel")
    assert ok is False and "belum terpasang" in pesan

    monkeypatch.setattr(
        menu_builder, "list_menus",
        lambda gid: [{"id": "m1", "title": "Panel utama", "message_id": 55}],
    )
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "panel", opsi="m1")
    assert ok and disegarkan == ["m1"] and "disegarkan" in pesan


async def test_uji_digest_ai_dan_ekspor(monkeypatch):
    import analytics_export
    import community_agent as ca

    async def digest(gid, nama, **kwargs):
        return "☀️ Selamat pagi! 📰 Sorotan hari ini…", None

    monkeypatch.setattr(ca, "generate_morning_digest", digest)
    ca.digest_agent_guilds[GID] = {"enabled": True, "channel_id": 606}
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "digest")
    assert ok and "Contoh koran pagi" in pesan and "tidak dikirim" in pesan

    async def jawab(system, contents, **kwargs):
        return "siap"

    # Tanpa key → alasan jelas, tanpa memanggil AI
    monkeypatch.setattr(ca, "GEMINI_API_KEY", "", raising=False)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "ai")
    assert ok is False and "GEMINI_API_KEY" in pesan

    monkeypatch.setattr(ca, "GEMINI_API_KEY", "kunci-uji", raising=False)
    monkeypatch.setattr(ca, "_call_gemini_agent", jawab)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "ai")
    assert ok and "koneksi sehat" in pesan

    monkeypatch.setattr(
        ca, "_call_gemini_agent", lambda *a, **k: _kosong()
    )
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "ai")
    assert ok is False and "tidak menjawab" in pesan

    monkeypatch.setattr(
        analytics_export, "build_csv",
        lambda kind, gid: ("a,b\n1,2\n3,4\n", "level.csv", ""),
    )
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "ekspor")
    assert ok and "2 baris" in pesan

    monkeypatch.setattr(analytics_export, "build_csv", lambda kind, gid: (None, "", "gagal"))
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "ekspor")
    assert ok is False and pesan == "gagal"


async def _kosong():
    return None


async def test_uji_tiket_memilih_channel(monkeypatch):
    import dashboard_tiket

    dipanggil = {}

    async def pasang(bot, gid, data):
        dipanggil.update(data)
        return True, "Panel tiket terpasang."

    monkeypatch.setattr(dashboard_tiket, "pasang_panel", pasang)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "tiket")
    assert ok is False and "Pilih channel" in pesan
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "tiket", opsi="101")
    assert ok and dipanggil == {"channel": 101}


def test_status_uji_memberi_pilihan_pengumuman_dan_panel(monkeypatch):
    import engagement
    import menu_builder

    engagement.announcements.clear()
    engagement.announcements[7] = {"guild_id": GID, "title": "Event"}
    monkeypatch.setattr(menu_builder, "list_menus", lambda gid: [{"id": "m1", "title": "Panel"}])

    status = dashboard_uji.status_uji(GID)
    assert status["pengumuman"]["pilihan"] == [("7", "#7 · Event")]
    assert status["panel"]["pilihan"] == [("m1", "Panel")]
    assert status["ai"]["aktif"] is True and status["ai"]["kolom"] == ""
