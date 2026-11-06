"""Uji aksi konten dashboard: kirim embed/webhook, pengumuman, tautan, panel."""

from __future__ import annotations

import engagement
import link_embed
import menu_builder
import webhook_identity
import dashboard_pesan as dp


class _Channel:
    def __init__(self, cid=11, gid=1234, nama="umum"):
        self.id = cid
        self.name = nama
        self.mention = f"<#{cid}>"
        self.guild = type("G", (), {"id": gid, "name": "Server Uji"})()
        self.terkirim = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return type("M", (), {"id": 9})()


class _Bot:
    def __init__(self, channels=()):
        self.channels = list(channels)

    def get_guild(self, gid):
        return type("G", (), {"id": gid, "name": "Server Uji"})()

    def get_channel(self, cid):
        for ch in self.channels:
            if ch.id == int(cid):
                return ch
        return None


async def _tanpa_disk(*_a, **_k):
    return None


def _bot_uji():
    ch = _Channel()
    return _Bot([ch]), ch


# ==============================================================================
# KIRIM
# ==============================================================================
async def test_kirim_menolak_input_kosong_dan_channel_hilang():
    bot, _ch = _bot_uji()

    ok, pesan = await dp.kirim(bot, 1234, {"channel": "0", "judul": "x"})
    assert ok is False and "Channel tidak ditemukan" in pesan

    ok, pesan = await dp.kirim(bot, 1234, {"channel": "11"})
    assert ok is False and "harus diisi" in pesan

    ok, pesan = await dp.kirim(bot, 1234, {"channel": "11", "isi": "hai", "warna": "bukan-warna"})
    assert ok is False and "Warna tidak valid" in pesan

    ok, pesan = await dp.kirim(bot, 1234, {"channel": "11", "isi": "hai", "gambar": "bukan-url"})
    assert ok is False and "http" in pesan

    ok, pesan = await dp.kirim(
        bot, 1234, {"channel": "11", "isi": "hai", "tombol_label": "Buka", "tombol_url": "js:alert(1)"}
    )
    assert ok is False and "URL tombol" in pesan


async def test_kirim_embed_sebagai_bot():
    bot, ch = _bot_uji()

    ok, pesan = await dp.kirim(
        bot,
        1234,
        {"channel": "11", "judul": "Pengumuman", "isi": "Halo semua", "warna": "#5865F2",
         "footer": "Bot Uji"},
    )
    assert ok is True and "Terkirim" in pesan
    embed = ch.terkirim[-1]["embed"]
    assert embed.title == "Pengumuman" and embed.description == "Halo semua"
    assert embed.footer.text == "Bot Uji"
    assert ch.terkirim[-1]["allowed_mentions"].everyone is False


async def test_kirim_teks_biasa_tanpa_embed():
    bot, ch = _bot_uji()
    ok, _ = await dp.kirim(bot, 1234, {"channel": "11", "isi": "pesan polos"})
    assert ok is True
    kiriman = ch.terkirim[-1]
    assert "embed" not in kiriman and kiriman["content"] == "pesan polos"


async def test_kirim_menolak_channel_server_lain():
    ch = _Channel(cid=11, gid=9999)
    bot = _Bot([ch])
    ok, pesan = await dp.kirim(bot, 1234, {"channel": "11", "isi": "hai"})
    assert ok is False and "Channel tidak ditemukan" in pesan


async def test_kirim_lewat_identitas_webhook(monkeypatch):
    bot, ch = _bot_uji()
    tercatat = {}

    async def _palsu(channel, **kwargs):
        tercatat["channel"] = channel
        tercatat.update(kwargs)
        return True, ""

    monkeypatch.setattr(webhook_identity, "kirim_sebagai", _palsu)
    monkeypatch.setattr(webhook_identity, "save_to_disk", _tanpa_disk)

    ok, pesan = await dp.kirim(
        bot, 1234, {"channel": "11", "judul": "Judul", "isi": "Isi",
                    "identitas": "📢 Pengumuman", "avatar": "https://contoh/a.png"}
    )
    assert ok is True and "identitas" in pesan
    assert tercatat["nama"] == "📢 Pengumuman"
    assert tercatat["avatar"] == "https://contoh/a.png"
    assert not ch.terkirim          # tidak dikirim sebagai bot


# ==============================================================================
# PENGUMUMAN
# ==============================================================================
async def test_tambah_pengumuman_validasi(monkeypatch):
    monkeypatch.setattr(engagement, "save_engagement_to_disk", _tanpa_disk)

    ok, pesan = await dp.tambah_pengumuman(1234, {"isi": "x"})
    assert ok is False and "channel" in pesan.lower()

    ok, pesan = await dp.tambah_pengumuman(1234, {"channel": "11"})
    assert ok is False and "tidak boleh kosong" in pesan

    ok, pesan = await dp.tambah_pengumuman(
        1234, {"channel": "11", "isi": "Isi", "jadwal": "kapan-kapan"}
    )
    assert ok is False and "Jadwal tidak dikenali" in pesan


async def test_tambah_pengumuman_sukses(monkeypatch):
    monkeypatch.setattr(engagement, "save_engagement_to_disk", _tanpa_disk)
    gid = 777001

    ok, pesan = await dp.tambah_pengumuman(
        gid, {"channel": "11", "judul": "Rapat", "isi": "Rapat jam 8", "jadwal": "08:00"}
    )
    assert ok is True and "Pengumuman dibuat" in pesan
    assert any(a.get("title") == "Rapat" for a in engagement.list_announcements(gid))


async def test_ubah_pengumuman(monkeypatch):
    monkeypatch.setattr(engagement, "save_engagement_to_disk", _tanpa_disk)
    gid = 777002

    ok, _ = await dp.tambah_pengumuman(
        gid, {"channel": "11", "isi": "Isi", "jadwal": "setiap 3 jam"}
    )
    assert ok is True
    aid = engagement.list_announcements(gid)[0]["id"]

    ok, pesan = await dp.ubah_pengumuman(gid, aid, False)
    assert ok is True and "dijeda" in pesan
    assert engagement.announcements[int(aid)]["enabled"] is False

    ok, _ = await dp.ubah_pengumuman(gid, 999999, True)
    assert ok is False


# ==============================================================================
# TAUTAN
# ==============================================================================
async def test_tambah_tautan_validasi_dan_sukses(monkeypatch):
    monkeypatch.setattr(link_embed, "save_to_disk", _tanpa_disk)

    ok, pesan = await dp.tambah_tautan(1234, {"judul": "Tanpa URL"})
    assert ok is False and "URL" in pesan

    ok, pesan = await dp.tambah_tautan(1234, {"url": "ftp://contoh"})
    assert ok is False                     # build_payload hanya menerima http(s)

    ok, pesan = await dp.tambah_tautan(
        880001, {"judul": "Situs", "isi": "Deskripsi", "url": "https://contoh.id", "warna": "#5865F2"}
    )
    assert ok is True and "/l/" in pesan
    assert len(link_embed.list_links(880001)) == 1


# ==============================================================================
# PANEL
# ==============================================================================
async def test_buat_panel_validasi(monkeypatch):
    bot, _ch = _bot_uji()
    ok, pesan = await dp.buat_panel(bot, 1234, {"channel": "11"})
    assert ok is False and "Judul panel" in pesan

    ok, pesan = await dp.buat_panel(bot, 1234, {"judul": "Pusat Bantuan"})
    assert ok is False and "Pilih channel" in pesan

    monkeypatch.setattr(menu_builder, "create_menu", lambda *a, **k: None)
    ok, pesan = await dp.buat_panel(bot, 1234, {"judul": "X", "channel": "11"})
    assert ok is False and "Kuota" in pesan


async def test_buat_panel_sukses(monkeypatch):
    bot, ch = _bot_uji()
    menu = {"id": "m1", "guild_id": 900001, "title": "Pusat", "message_id": None}

    monkeypatch.setattr(menu_builder, "create_menu", lambda *a, **k: dict(menu))
    monkeypatch.setattr(menu_builder, "save_menus_to_disk", _tanpa_disk)

    async def _send_panel(_bot, record, channel, **_k):
        record["message_id"] = 5
        return type("M", (), {"id": 5})()

    monkeypatch.setattr(menu_builder, "send_panel", _send_panel)

    ok, pesan = await dp.buat_panel(bot, 1234, {"judul": "Pusat", "channel": "11", "isi": "Halo"})
    assert ok is True and "terkirim" in pesan.lower()


# ==============================================================================
# HAPUS & DAFTAR
# ==============================================================================
async def test_hapus_validasi():
    bot, _ch = _bot_uji()
    ok, pesan = await dp.hapus(bot, 1234, "ngawur", "1")
    assert ok is False and "tidak dikenal" in pesan

    ok, pesan = await dp.hapus(bot, 1234, "pengumuman", "")
    assert ok is False and "tidak boleh kosong" in pesan

    ok, pesan = await dp.hapus(bot, 1234, "pengumuman", "987654")
    assert ok is False and "tidak ditemukan" in pesan

    ok, pesan = await dp.hapus(bot, 1234, "tautan", "tidak-ada")
    assert ok is False and "tidak ditemukan" in pesan


async def test_hapus_pengumuman_dan_tautan_sukses(monkeypatch):
    monkeypatch.setattr(engagement, "save_engagement_to_disk", _tanpa_disk)
    monkeypatch.setattr(link_embed, "save_to_disk", _tanpa_disk)
    bot, _ch = _bot_uji()
    gid = 990001

    await dp.tambah_pengumuman(gid, {"channel": "11", "isi": "Isi", "jadwal": "08:00"})
    aid = engagement.list_announcements(gid)[0]["id"]
    ok, pesan = await dp.hapus(bot, gid, "pengumuman", str(aid))
    assert ok is True and "dihapus" in pesan
    assert engagement.list_announcements(gid) == []

    await dp.tambah_tautan(gid, {"judul": "Situs", "url": "https://contoh.id"})
    lid = link_embed.list_links(gid)[0]["id"]
    ok, pesan = await dp.hapus(bot, gid, "tautan", lid)
    assert ok is True and "dihapus" in pesan
    assert link_embed.list_links(gid) == []


def test_daftar_konten_menggabungkan_semua_jenis(monkeypatch):
    monkeypatch.setattr(menu_builder, "list_menus", lambda gid: [{"id": "m1", "title": "Panel", "message_id": 3}])
    monkeypatch.setattr(menu_builder, "count_items", lambda menu: 2)
    monkeypatch.setattr(
        webhook_identity, "_cache", {"4242:11": {"webhook_id": 88, "url": "https://x"}}, raising=False
    )

    data = dp.daftar_konten(4242)
    assert data["panel"][0]["judul"] == "Panel" and "2" in data["panel"][0]["ringkas"]
    assert data["webhook"][0]["id"] == "11"
    assert dp.daftar_konten(9999)["webhook"] == []


# ==============================================================================
# FORMULIR & PEMICU GABUNG
# ==============================================================================
async def test_tambah_formulir_validasi_dan_sukses(monkeypatch):
    import modal_forms

    monkeypatch.setattr(modal_forms, "save_to_disk", _tanpa_disk)

    ok, pesan = await dp.tambah_formulir(1234, {"kolom": "Nama|teks"})
    assert ok is False and "Nama formulir" in pesan

    ok, pesan = await dp.tambah_formulir(
        950001, {"judul": "Pendaftaran", "kolom": "Nama | Asal kota | Alasan:panjang?"}
    )
    assert ok is True and "3 kolom" in pesan
    assert modal_forms.get_form(950001, "Pendaftaran") is not None


async def test_pasang_dan_hapus_pemicu(monkeypatch):
    import flow_triggers

    monkeypatch.setattr(flow_triggers, "save_to_disk", _tanpa_disk)
    gid = 960001

    ok, pesan = await dp.pasang_pemicu(gid, {"alur": "+role:5"})
    assert ok is False and "channel" in pesan.lower()

    ok, pesan = await dp.pasang_pemicu(gid, {"channel": "11"})
    assert ok is False and "Alur wajib" in pesan

    ok, pesan = await dp.pasang_pemicu(gid, {"channel": "11", "alur": "aksi-ngawur"})
    assert ok is False and "tidak dikenal" in pesan

    ok, pesan = await dp.pasang_pemicu(
        gid, {"channel": "11", "alur": "+role:5 > umum:Halo {member.mention}", "umur_akun": "7"}
    )
    assert ok is True and "2 langkah" in pesan
    assert flow_triggers.get_trigger(gid)["min_age_days"] == 7

    ok, pesan = await dp.hapus_pemicu(gid)
    assert ok is True and "dihapus" in pesan
    assert flow_triggers.get_trigger(gid) is None

    ok, pesan = await dp.hapus_pemicu(gid)
    assert ok is False and "belum dipasang" in pesan


async def test_daftar_konten_memuat_pemicu(monkeypatch):
    import flow_triggers

    monkeypatch.setattr(
        flow_triggers, "get_trigger", lambda gid: {"steps": [{"action": "role_add"}], "min_age_days": 3}
        if gid == 970001 else None
    )
    data = dp.daftar_konten(970001)
    assert data["pemicu"][0]["ringkas"].startswith("1 langkah")
    assert dp.daftar_konten(970002)["pemicu"] == []


async def test_hapus_pemicu_lewat_dispatch(monkeypatch):
    import flow_triggers

    monkeypatch.setattr(flow_triggers, "save_to_disk", _tanpa_disk)
    bot, _ch = _bot_uji()
    await dp.pasang_pemicu(980001, {"channel": "11", "alur": "+role:5"})
    ok, pesan = await dp.hapus(bot, 980001, "pemicu", "aktif")
    assert ok is True and "dihapus" in pesan
