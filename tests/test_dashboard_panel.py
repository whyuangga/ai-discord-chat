"""Uji editor panel (tombol & dropdown) dari dashboard + pasang panel tiket."""

from __future__ import annotations

import socket

import aiohttp

import dashboard_panel as dpanel
import dashboard_tiket as dt
import dashboard_ui as ui
import menu_builder
import modal_forms
import tickets
import web_dashboard

GID = 1234
CID = 11


# ==============================================================================
# PERKAKAS
# ==============================================================================
class _Perm:
    administrator = True
    manage_roles = True
    manage_threads = True
    manage_channels = True


class _Role:
    def __init__(self, rid, nama, pos=1, default=False, managed=False):
        self.id = rid
        self.name = nama
        self.position = pos
        self.managed = managed
        self._default = default

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= getattr(other, "position", 0)


class _Anggota:
    guild_permissions = _Perm()


class _Channel:
    def __init__(self, cid=CID, nama="bantuan", jenis="text", pos=1):
        self.id = cid
        self.name = nama
        self.type = type("T", (), {"name": jenis})()
        self.position = pos
        self.mention = f"<#{cid}>"
        self.guild = None
        self.terkirim = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return type("M", (), {"id": 555})()


class _Guild:
    def __init__(self):
        self.id = GID
        self.name = "Server Uji"
        self.bot_role = _Role(99, "Bot", 10)
        self.me = type("Me", (), {"guild_permissions": _Perm(), "top_role": self.bot_role})()
        self.roles = [_Role(1, "Member", 5), _Role(2, "Gamer", 3), _Role(3, "Event", 2)]
        self.channels = [_Channel(CID, "bantuan"), _Channel(12, "log", pos=2)]
        for ch in self.channels:
            ch.guild = self

    def get_role(self, rid):
        for role in self.roles:
            if role.id == int(rid):
                return role
        return None


class _Bot:
    def __init__(self, channel=None):
        self.guild = _Guild()
        self.guilds = [self.guild]
        self.channel = channel if channel is not None else self.guild.channels[0]
        self.views = []

    def get_guild(self, gid):
        return self.guild if int(gid) == GID else None

    def get_channel(self, cid):
        return self.channel if int(cid) == self.channel.id else None

    def add_view(self, view, message_id=None):
        self.views.append((view, message_id))


def _menu(**ubah):
    data = {
        "id": "m1",
        "guild_id": GID,
        "title": "Pusat Bantuan",
        "description": "Pilih tombol",
        "buttons": [],
        "dropdowns": [],
        "channel_id": CID,
        "message_id": 99,
        "banner_url": None,
    }
    data.update(ubah)
    return data


async def _tidur(*_a, **_b):
    return None


def _tanpa_segar(*_a, **_b):
    async def _hasil():
        return False

    return _hasil()


def _siapkan(monkeypatch, menu=None):
    """Isi `menu_builder.menus` dengan satu panel & matikan efek sampingnya."""
    data = menu or _menu()
    monkeypatch.setattr(menu_builder, "menus", {GID: {"m1": data}}, raising=False)
    monkeypatch.setattr(menu_builder, "save_menus_to_disk", _tidur, raising=False)
    monkeypatch.setattr(menu_builder, "refresh_panel", _tanpa_segar, raising=False)
    return data


# ==============================================================================
# collect_panel
# ==============================================================================
def test_collect_panel_kosong(monkeypatch):
    monkeypatch.setattr(menu_builder, "menus", {GID: {}}, raising=False)
    data = dpanel.collect_panel(GID)
    assert data["items"] == []
    assert data["statistik"] == {"panel": 0, "tombol": 0, "dropdown": 0}


def test_collect_panel_berisi_tombol_dan_dropdown(monkeypatch):
    menu = _menu()
    menu["buttons"] = [
        {"id": "i1", "kind": "role", "label": "Gamer", "role_id": 2},
        {"id": "i2", "kind": "link", "label": "Buka", "url": "https://contoh.id"},
        {"id": "i3", "kind": "command", "label": "Statistik", "command": "serverstats"},
        {"id": "i4", "kind": "form", "label": "Daftar", "form_id": "f1"},
    ]
    menu["dropdowns"] = [
        {
            "id": "d1",
            "placeholder": "Pilih role…",
            "options": [
                {"id": "i5", "kind": "role", "label": "Member", "role_id": 1},
                {"id": "i6", "kind": "role", "label": "Event", "role_id": 3},
            ],
        }
    ]
    _siapkan(monkeypatch, menu)

    data = dpanel.collect_panel(GID)
    grup = data["items"][0]
    assert grup["judul"] == "Pusat Bantuan" and grup["terkirim"] is True
    assert [t["label"] for t in grup["tombol"]] == ["Gamer", "Buka", "Statistik", "Daftar"]
    assert grup["tombol"][0]["jenis"] == "Peran"
    assert "role <@&2>" in grup["tombol"][0]["detail"]
    assert grup["tombol"][1]["detail"] == "https://contoh.id"
    assert grup["tombol"][2]["detail"] == "/serverstats"
    assert "formulir" in grup["tombol"][3]["detail"]
    assert grup["dropdown"][0]["ringkas"] == "2 opsi"
    assert len(grup["dropdown"][0]["opsi"]) == 2
    assert data["statistik"] == {"panel": 1, "tombol": 4, "dropdown": 1}


def test_daftar_perintah_dari_whitelist():
    daftar = dpanel.daftar_perintah()
    kunci = [k for k, _ in daftar]
    assert "serverstats" in kunci and "level" in kunci
    assert all(teks.startswith("/") for _, teks in daftar)


# ==============================================================================
# tambah_item
# ==============================================================================
async def test_tambah_tombol_role(monkeypatch):
    menu = _siapkan(monkeypatch)
    bot = _Bot()
    ok, pesan = await dpanel.tambah_item(
        bot, GID, {"panel": "m1", "jenis": "peran", "role": "2", "gaya": "hijau"}
    )
    assert ok is True
    assert menu["buttons"][0]["role_id"] == 2
    assert menu["buttons"][0]["style"] == "hijau"
    assert menu["buttons"][0]["label"] == "Gamer"        # label otomatis dari role
    assert "ditambahkan ke panel **Pusat Bantuan**" in pesan


async def test_tambah_tombol_role_tidak_aman_ditolak(monkeypatch):
    _siapkan(monkeypatch)
    bot = _Bot()
    # role di atas role bot
    bot.guild.roles.append(_Role(7, "Admin", 50))
    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "peran", "role": "7"})
    assert ok is False and "di atas role bot" in pesan

    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "peran", "role": "0"})
    assert ok is False and "Pilih role" in pesan


async def test_tambah_tombol_tautan_perintah_alur_formulir(monkeypatch):
    menu = _siapkan(monkeypatch)
    bot = _Bot()

    ok, pesan = await dpanel.tambah_item(
        bot, GID, {"panel": "m1", "jenis": "tautan", "label": "Buka", "url": "bukan-url"}
    )
    assert ok is False and "http" in pesan

    ok, _ = await dpanel.tambah_item(
        bot, GID,
        {"panel": "m1", "jenis": "tautan", "label": "Situs", "url": "https://contoh.id"},
    )
    assert ok is True and menu["buttons"][0]["kind"] == "link"

    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "perintah", "perintah": "ban"})
    assert ok is False and "daftar aman" in pesan

    ok, _ = await dpanel.tambah_item(
        bot, GID, {"panel": "m1", "jenis": "perintah", "perintah": "serverstats"}
    )
    assert ok is True and menu["buttons"][1]["command"] == "serverstats"

    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "alur", "alur": ""})
    assert ok is False and "kosong" in pesan

    ok, _ = await dpanel.tambah_item(
        bot, GID,
        {"panel": "m1", "jenis": "alur", "label": "Ambil role", "alur": "+role:2 > pesan:Halo"},
    )
    assert ok is True and menu["buttons"][2]["kind"] == "flow"

    monkeypatch.setattr(
        modal_forms, "get_form", lambda gid, ref: {"id": "f1", "name": "Pendaftaran"},
        raising=False,
    )
    ok, _ = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "formulir", "formulir": "f1"})
    assert ok is True and menu["buttons"][3]["kind"] == "form"
    assert menu["buttons"][3]["label"] == "Pendaftaran"

    monkeypatch.setattr(modal_forms, "get_form", lambda gid, ref: None, raising=False)
    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "formulir", "formulir": "x"})
    assert ok is False and "tidak ditemukan" in pesan


async def test_tambah_dropdown_tiga_role(monkeypatch):
    menu = _siapkan(monkeypatch)
    bot = _Bot()
    ok, pesan = await dpanel.tambah_item(
        bot, GID,
        {"panel": "m1", "jenis": "dropdown", "label": "Pilih role…",
         "role": "1", "role2": "2", "role3": "3", "eksklusif": "on"},
    )
    assert ok is True
    grup = menu["dropdowns"][0]
    assert [opt["role_id"] for opt in grup["options"]] == [1, 2, 3]
    assert grup["options"][0]["label"] == "Member"
    assert grup["exclusive"] is True
    assert "3 opsi" in pesan


async def test_tambah_dropdown_tanpa_role_ditolak(monkeypatch):
    _siapkan(monkeypatch)
    ok, pesan = await dpanel.tambah_item(_Bot(), GID, {"panel": "m1", "jenis": "dropdown"})
    assert ok is False and "minimal satu role" in pesan


async def test_tambah_item_panel_asing_atau_jenis_asing(monkeypatch):
    _siapkan(monkeypatch)
    bot = _Bot()
    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "tidak-ada", "jenis": "peran"})
    assert ok is False and "Panel tidak ditemukan" in pesan

    ok, pesan = await dpanel.tambah_item(bot, GID, {"panel": "m1", "jenis": "tombol-ajaib"})
    assert ok is False and "tidak dikenal" in pesan


async def test_tambah_item_melaporkan_refresh_panel(monkeypatch):
    _siapkan(monkeypatch)

    async def _segar(bot, menu):
        return True

    monkeypatch.setattr(menu_builder, "refresh_panel", _segar, raising=False)
    ok, pesan = await dpanel.tambah_item(
        _Bot(), GID, {"panel": "m1", "jenis": "peran", "role": "2"}
    )
    assert ok is True and "langsung diperbarui" in pesan


# ==============================================================================
# hapus_item
# ==============================================================================
async def test_hapus_item_lewat_id_dan_nomor(monkeypatch):
    menu = _menu()
    menu["buttons"] = [
        {"id": "i1", "kind": "role", "label": "Gamer", "role_id": 2},
        {"id": "i2", "kind": "link", "label": "Buka", "url": "https://contoh.id"},
    ]
    _siapkan(monkeypatch, menu)
    bot = _Bot()

    ok, pesan = await dpanel.hapus_item(bot, GID, {"panel": "m1", "item": "i1"})
    assert ok is True and "Gamer" in pesan
    assert len(menu["buttons"]) == 1

    ok, pesan = await dpanel.hapus_item(bot, GID, {"panel": "m1", "item": "1"})
    assert ok is True and "Buka" in pesan
    assert menu["buttons"] == []


async def test_hapus_item_tidak_ditemukan(monkeypatch):
    _siapkan(monkeypatch)
    bot = _Bot()
    ok, pesan = await dpanel.hapus_item(bot, GID, {"panel": "m1", "item": ""})
    assert ok is False and "nomor urut" in pesan

    ok, pesan = await dpanel.hapus_item(bot, GID, {"panel": "m1", "item": "i9"})
    assert ok is False and "tidak ada" in pesan

    ok, pesan = await dpanel.hapus_item(bot, GID, {"panel": "lain", "item": "i1"})
    assert ok is False and "Panel tidak ditemukan" in pesan


# ==============================================================================
# UI: blok editor panel + form pasang panel tiket
# ==============================================================================
def test_render_panel_block_kosong_dan_berisi():
    kosong = ui.render_panel_block(_Bot(), GID, {"items": []}, "tok")
    assert "Belum ada panel" in kosong

    data = {
        "items": [
            {
                "id": "m1",
                "judul": "Pusat Bantuan",
                "deskripsi": "Pilih tombol",
                "terkirim": True,
                "jumlah": 2,
                "tombol": [
                    {"ref": "i1", "label": "Gamer", "jenis": "Peran", "detail": "role <@&2>"},
                    {"ref": "i2", "label": "Buka", "jenis": "Tautan", "detail": "https://contoh.id"},
                ],
                "dropdown": [
                    {
                        "ref": "d1",
                        "label": "Pilih role…",
                        "ringkas": "1 opsi",
                        "opsi": [{"ref": "i3", "label": "Member", "detail": "role <@&1>"}],
                    }
                ],
            }
        ],
        "statistik": {"panel": 1, "tombol": 2, "dropdown": 1},
    }
    html = ui.render_panel_block(_Bot(), GID, data, "tok")
    assert "tombol: 2" in html and "dropdown: 1" in html
    assert "Pusat Bantuan" in html and "sudah terkirim" in html
    assert "hapus:m1:i1" in html and "hapus:m1:i3" in html
    assert "tambah:m1" in html and "<details>" in html
    assert 'name="jenis"' in html and 'value="dropdown"' in html
    # blok ini memuat form verifikasi, bukan form panel tiket
    assert "Pasang panel verifikasi" in html
    assert "Pasang panel tiket" not in html


def test_render_panel_block_escape_html():
    data = {
        "items": [
            {
                "id": "m1",
                "judul": "<script>x</script>",
                "terkirim": False,
                "jumlah": 1,
                "tombol": [{"ref": "i1", "label": "<b>a</b>", "jenis": "Peran", "detail": ""}],
                "dropdown": [],
            }
        ],
        "statistik": {"panel": 1, "tombol": 1, "dropdown": 0},
    }
    html = ui.render_panel_block(_Bot(), GID, data, "tok")
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html and "&lt;b&gt;" in html


def test_render_tiket_block_memuat_form_pasang_panel():
    html = ui.render_tiket_block(GID, {"items": [], "statistik": {}}, "tok", _Bot())
    assert "Pasang panel tiket" in html
    assert 'action="/api/tiket"' in html and 'value="panel"' in html
    assert 'value="matikan"' in html
    assert 'name="staff_role"' in html and 'name="log_channel"' in html
    assert 'name="max_open"' in html


# ==============================================================================
# PANEL TIKET (setara /tiket panel)
# ==============================================================================
def _siapkan_tiket(monkeypatch, *, enabled=False):
    catatan = {"config": {}, "pesan": []}

    def _set_config(gid, **ubah):
        catatan["config"].update(ubah)
        cfg = {
            "enabled": catatan["config"].get("enabled", enabled),
            "panel_channel_id": catatan["config"].get("panel_channel_id"),
            "panel_message_id": catatan["config"].get("panel_message_id"),
            "staff_role_id": catatan["config"].get("staff_role_id"),
            "log_channel_id": catatan["config"].get("log_channel_id"),
            "max_open": catatan["config"].get("max_open") or 2,
        }
        catatan["config"] = dict(cfg)
        return cfg

    def _get_config(gid):
        return catatan["config"]

    def _disable(gid):
        if not catatan["config"].get("enabled"):
            return False
        catatan["config"]["enabled"] = False
        return True

    catatan["config"] = {"enabled": enabled, "max_open": 2}
    monkeypatch.setattr(tickets, "set_ticket_config", _set_config, raising=False)
    monkeypatch.setattr(tickets, "get_ticket_config", _get_config, raising=False)
    monkeypatch.setattr(tickets, "disable_tickets", _disable, raising=False)
    monkeypatch.setattr(
        tickets, "build_panel_embed", lambda nama, staff_role_id=None: {"nama": nama},
        raising=False,
    )
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _tidur, raising=False)

    async def _kirim(channel, gid, embed):
        catatan["pesan"].append((channel.id, gid, embed))
        return type("M", (), {"id": 4321})()

    import views

    monkeypatch.setattr(views, "send_ticket_panel", _kirim, raising=False)
    return catatan


async def test_pasang_panel_tiket(monkeypatch):
    catatan = _siapkan_tiket(monkeypatch)
    bot = _Bot()
    ok, pesan = await dt.pasang_panel(
        bot, GID,
        {"channel": str(CID), "staff_role": "1", "log_channel": "12", "max_open": "3"},
    )
    assert ok is True
    assert "Panel tiket terpasang" in pesan and "<#11>" in pesan
    assert catatan["pesan"][0][0] == CID and catatan["pesan"][0][2] == {"nama": "Server Uji"}
    assert catatan["config"]["enabled"] is True
    assert catatan["config"]["panel_message_id"] == 4321
    assert catatan["config"]["staff_role_id"] == 1
    assert catatan["config"]["log_channel_id"] == 12
    assert catatan["config"]["max_open"] == 3


async def test_pasang_panel_tiket_tanpa_channel(monkeypatch):
    _siapkan_tiket(monkeypatch)
    ok, pesan = await dt.pasang_panel(_Bot(), GID, {"channel": "0"})
    assert ok is False and "Pilih channel" in pesan

    ok, pesan = await dt.pasang_panel(_Bot(), GID, {"channel": "999"})
    assert ok is False and "tidak ditemukan" in pesan


async def test_pasang_panel_tiket_ditolak_discord(monkeypatch):
    _siapkan_tiket(monkeypatch)
    import views

    async def _tolak(channel, gid, embed):
        raise RuntimeError("ditolak")

    monkeypatch.setattr(views, "send_ticket_panel", _tolak, raising=False)
    ok, pesan = await dt.pasang_panel(_Bot(), GID, {"channel": str(CID)})
    assert ok is False and "Discord menolak" in pesan


async def test_matikan_tiket(monkeypatch):
    catatan = _siapkan_tiket(monkeypatch, enabled=True)
    ok, pesan = await dt.matikan_tiket(GID)
    assert ok is True and catatan["config"]["enabled"] is False
    assert "dinonaktifkan" in pesan

    _siapkan_tiket(monkeypatch, enabled=False)
    ok, pesan = await dt.matikan_tiket(GID)
    assert ok is False and "sudah nonaktif" in pesan


# ==============================================================================
# RUTE HTTP /api/panel (+ /api/tiket panel)
# ==============================================================================
async def _jalankan(monkeypatch, bot, fn, tmp_path):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "tok-panel")

    assert await web_dashboard.start_dashboard(bot) is True
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            return await fn(session, f"http://127.0.0.1:{port}")
    finally:
        await web_dashboard.stop_dashboard()


async def test_http_panel_daftar_tambah_hapus(monkeypatch, tmp_path):
    menu = _siapkan(monkeypatch)
    bot = _Bot()

    async def skenario(session, base):
        async with session.get(f"{base}/api/panel?guild={GID}") as resp:
            assert resp.status == 401
        async with session.get(
            f"{base}/api/panel?guild={GID}", headers={"X-Dashboard-Token": "tok-panel"}
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["items"][0]["id"] == "m1"

        # halaman /panel memuat editor panel
        async with session.get(f"{base}/panel?token=tok-panel&guild={GID}") as resp:
            body = await resp.text()
            assert resp.status == 200
            assert "Editor panel" in body and "tambah:m1" in body

        # halaman /tiket memuat tombol pasang panel tiket
        async with session.get(f"{base}/tiket?token=tok-panel&guild={GID}") as resp:
            body = await resp.text()
            assert "Pasang panel tiket" in body

        # tambah tombol role lewat form
        async with session.post(
            f"{base}/api/panel",
            data={"token": "tok-panel", "guild": str(GID), "action": "tambah:m1",
                  "jenis": "peran", "role": "2", "label": "Gamer"},
        ) as resp:
            body = await resp.text()
            assert resp.status == 200 and "ditambahkan" in body
        assert menu["buttons"][0]["label"] == "Gamer"

        # hapus lagi lewat JSON
        async with session.post(
            f"{base}/api/panel",
            json={"token": "tok-panel", "guild": str(GID),
                  "action": f"hapus:m1:{menu['buttons'][0]['id']}"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
        assert menu["buttons"] == []

        async with session.post(
            f"{base}/api/panel",
            json={"token": "tok-panel", "guild": str(GID), "action": "sulap:1"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 400 and "tidak dikenal" in data["message"]

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_http_tiket_pasang_dan_matikan_panel(monkeypatch, tmp_path):
    catatan = _siapkan_tiket(monkeypatch)
    bot = _Bot()

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/tiket",
            json={"token": "tok-panel", "guild": str(GID),
                  "action": "panel", "channel": str(CID), "max_open": "2"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
            assert "Panel tiket terpasang" in data["message"]
        assert catatan["pesan"][0][0] == CID

        async with session.post(
            f"{base}/api/tiket",
            json={"token": "tok-panel", "guild": str(GID), "action": "matikan"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
        assert catatan["config"]["enabled"] is False

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


# ==============================================================================
# PANEL VERIFIKASI (setara /verifikasi pasang)
# ==============================================================================
def _siapkan_verifikasi(monkeypatch, *, enabled=False):
    import community_tools

    catatan = {"config": {"enabled": enabled}, "pesan": []}
    monkeypatch.setattr(
        community_tools, "verification_guilds", {GID: catatan["config"]}, raising=False
    )

    def _set_config(gid, **ubah):
        catatan["config"].update(ubah)
        return catatan["config"]

    monkeypatch.setattr(community_tools, "set_verification_config", _set_config, raising=False)
    monkeypatch.setattr(
        community_tools, "save_community_tools_to_disk", _tidur, raising=False
    )
    monkeypatch.setattr(
        community_tools, "build_verification_embed",
        lambda nama, role, catatan_extra="": {"nama": nama, "role": role, "catatan": catatan_extra},
        raising=False,
    )

    class _View:
        pass

    import views

    monkeypatch.setattr(views, "VerificationGateView", _View, raising=False)
    return catatan


async def test_status_verifikasi(monkeypatch):
    _siapkan_verifikasi(monkeypatch, enabled=False)
    assert dpanel.status_verifikasi(GID) == {"aktif": False, "channel": "", "role": ""}

    import community_tools

    community_tools.verification_guilds[GID].update(
        {"enabled": True, "channel_id": CID, "role_id": 1}
    )
    data = dpanel.collect_panel(GID)
    assert data["verifikasi"] == {"aktif": True, "channel": str(CID), "role": "1"}


async def test_pasang_verifikasi(monkeypatch):
    catatan = _siapkan_verifikasi(monkeypatch)
    bot = _Bot()
    ok, pesan = await dpanel.pasang_verifikasi(
        bot, GID, {"channel": str(CID), "role": "1", "catatan": "Baca aturan"}
    )
    assert ok is True
    assert "Gerbang verifikasi aktif" in pesan and "<#11>" in pesan
    assert catatan["config"]["channel_id"] == CID
    assert catatan["config"]["role_id"] == 1
    assert catatan["config"]["message_id"] == 555      # dari _Channel.send
    assert catatan["config"]["enabled"] is True
    terkirim = bot.channel.terkirim[-1]
    assert terkirim["embed"]["catatan"] == "Baca aturan"


async def test_pasang_verifikasi_validasi(monkeypatch):
    _siapkan_verifikasi(monkeypatch)
    bot = _Bot()

    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": "0", "role": "1"})
    assert ok is False and "Pilih channel" in pesan

    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": str(CID), "role": "0"})
    assert ok is False and "Pilih role" in pesan

    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": str(CID), "role": "404"})
    assert ok is False and "tidak ada" in pesan

    # @everyone ditolak
    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": str(CID), "role": "1"})
    bot.guild.roles.append(_Role(5, "@everyone", 0, default=True))
    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": str(CID), "role": "5"})
    assert ok is False and "@everyone" in pesan

    # role di atas role bot
    bot.guild.roles.append(_Role(8, "Owner", 99))
    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": str(CID), "role": "8"})
    assert ok is False and "di atas role bot" in pesan

    ok, pesan = await dpanel.pasang_verifikasi(bot, GID, {"channel": "777", "role": "1"})
    assert ok is False and "Channel itu tidak ditemukan" in pesan


async def test_matikan_verifikasi(monkeypatch):
    catatan = _siapkan_verifikasi(monkeypatch, enabled=True)
    ok, pesan = await dpanel.matikan_verifikasi(GID)
    assert ok is True and catatan["config"]["enabled"] is False
    assert "dinonaktifkan" in pesan

    ok, pesan = await dpanel.matikan_verifikasi(GID)
    assert ok is False and "sudah nonaktif" in pesan


# ==============================================================================
# EKSPOR CSV
# ==============================================================================
def test_render_ekspor_block_memuat_tautan_bertoken():
    html = ui.render_ekspor_block(GID, "tok-rahasia")
    for jenis in ("level", "moderasi", "tiket", "pemakaian"):
        assert f"/api/ekspor?jenis={jenis}" in html
    assert "token=tok-rahasia" in html
    assert "guild=1234" in html
    assert html.count("<a class=\"tombol-unduh\"") == 4


async def test_http_ekspor_csv(monkeypatch, tmp_path):
    import analytics_export
    import levels

    def _csv(jenis, gid):
        if jenis != "level":
            return None, "", f"Jenis `{jenis}` tidak dikenal."
        return "user_id,level\n1,2\n", f"analitik-level-{gid}.csv", ""

    monkeypatch.setattr(analytics_export, "build_csv", _csv, raising=False)
    monkeypatch.setattr(levels, "levels", {}, raising=False)
    bot = _Bot()

    async def skenario(session, base):
        async with session.get(f"{base}/api/ekspor?jenis=level&guild={GID}") as resp:
            assert resp.status == 401
        async with session.get(
            f"{base}/api/ekspor?jenis=level&guild={GID}",
            headers={"X-Dashboard-Token": "tok-panel"},
        ) as resp:
            body = await resp.text()
            assert resp.status == 200
            assert body.startswith("\ufeffuser_id,level")
            assert "attachment" in resp.headers["Content-Disposition"]
            assert resp.headers["Content-Type"].startswith("text/csv")
        async with session.get(
            f"{base}/api/ekspor?jenis=entah&guild={GID}",
            headers={"X-Dashboard-Token": "tok-panel"},
        ) as resp:
            assert resp.status == 404

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


async def test_http_panel_verifikasi(monkeypatch, tmp_path):
    catatan = _siapkan_verifikasi(monkeypatch)
    bot = _Bot()

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/panel",
            json={"token": "tok-panel", "guild": str(GID), "action": "verifikasi",
                  "channel": str(CID), "role": "1"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
            assert "Gerbang verifikasi aktif" in data["message"]
        assert catatan["config"]["enabled"] is True

        async with session.post(
            f"{base}/api/panel",
            json={"token": "tok-panel", "guild": str(GID), "action": "verifikasi:matikan"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
        assert catatan["config"]["enabled"] is False

    await _jalankan(monkeypatch, bot, skenario, tmp_path)


def test_halaman_memuat_blok_baru_dan_css_hp():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={},
        ekspor_block="EKSPOR-UJI", panel_block="PANEL-UJI", tiket_block="TIKET-UJI",
    )
    assert "📥 Ekspor CSV" in page and "EKSPOR-UJI" in page
    assert "Editor panel (tombol &amp; dropdown)" in page and "PANEL-UJI" in page
    assert "TIKET-UJI" in page
    # tata letak HP: grid jadi satu kolom
    assert "@media (max-width: 620px)" in page
    assert ".baris-kolom { grid-template-columns: 1fr" in page
