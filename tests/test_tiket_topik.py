"""Uji multi-topik tiket: daftar topik, dropdown panel, role staf per topik, & dashboard."""

from __future__ import annotations

import pytest

import dashboard_tiket
import dashboard_ui
import tickets
import views

GID = 1234


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan(tmp_path, monkeypatch):
    monkeypatch.setattr(tickets, "TICKETS_FILE", tmp_path / "tickets.json")
    monkeypatch.setattr(tickets, "DATA_DIR", tmp_path)
    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    tickets._ticket_seq.clear()
    yield
    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    tickets._ticket_seq.clear()


# ==============================================================================
# MODUL
# ==============================================================================
def test_tambah_cari_perbarui_dan_hapus_topik():
    assert tickets.list_ticket_topics(GID) == []
    ok, pesan = tickets.add_ticket_topic(
        GID, "Pembelian", emoji="🛒", staff_role_id=77, deskripsi="Beli / kirim barang"
    )
    assert ok is True and "ditambahkan" in pesan
    ok, pesan = tickets.add_ticket_topic(GID, "Lapor Bug", emoji="🐞")
    assert ok is True
    assert [t["nama"] for t in tickets.list_ticket_topics(GID)] == ["Pembelian", "Lapor Bug"]

    # Nama sama (beda huruf besar/kecil) memperbarui, bukan menambah
    ok, pesan = tickets.add_ticket_topic(GID, "pembelian", staff_role_id=88)
    assert ok is True and "diperbarui" in pesan
    assert len(tickets.list_ticket_topics(GID)) == 2

    assert tickets.find_topic(GID, "LAPOR BUG")["emoji"] == "🐞"
    assert tickets.find_topic(GID, "") is None
    assert tickets.topic_staff_role(GID, "pembelian") == 88
    assert tickets.topic_staff_role(GID, "tidak-ada") == 0

    assert tickets.remove_ticket_topic(GID, "Pembelian")[0] is True
    assert tickets.remove_ticket_topic(GID, "Pembelian")[0] is False
    assert [t["nama"] for t in tickets.list_ticket_topics(GID)] == ["Lapor Bug"]


def test_topik_dibatasi_dan_dinormalkan():
    assert tickets.add_ticket_topic(GID, "  ")[0] is False
    for i in range(tickets.TICKET_TOPIC_MAX):
        assert tickets.add_ticket_topic(GID, f"Topik {i}")[0] is True
    ok, pesan = tickets.add_ticket_topic(GID, "Kelebihan")
    assert ok is False and "penuh" in pesan

    rapih = tickets.normalize_topics(
        [
            {"nama": "A", "emoji": "🅰️", "staff_role_id": "9"},
            {"nama": "a"},  # duplikat
            {"nama": ""},  # kosong
            "bukan-dict",
            {"nama": "B" * 80},  # dipotong
        ]
    )
    assert [t["nama"] for t in rapih] == ["A", "B" * tickets.TICKET_TOPIC_LEN]
    assert rapih[0]["staff_role_id"] == 9


@pytest.mark.asyncio
async def test_topik_bertahan_setelah_simpan_dan_muat_ulang():
    tickets.add_ticket_topic(GID, "Pembelian", emoji="🛒", staff_role_id=77)
    await tickets.save_tickets_to_disk()

    tickets.ticket_guilds.clear()
    tickets.load_tickets_from_disk()
    topik = tickets.list_ticket_topics(GID)
    assert topik[0]["nama"] == "Pembelian" and topik[0]["staff_role_id"] == 77


def test_embed_tiket_menampilkan_topik_dan_kompatibel_tanpa_topik():
    data = tickets.register_ticket(8001, GID, 501, topic="Bantuan dari Sari", topik="Pembelian")
    embed = tickets.build_ticket_embed(data, staff_role_id=42)
    teks = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "Pembelian" in teks and "Bantuan dari Sari" in teks

    lama = tickets.register_ticket(8002, GID, 502, topic="Bantuan dari Budi")
    assert lama["topik"] == ""
    assert "Bantuan dari Budi" in " ".join(
        f.value for f in tickets.build_ticket_embed(lama).fields
    )


# ==============================================================================
# PANEL & ALUR BUKA TIKET
# ==============================================================================
def test_panel_memakai_dropdown_hanya_saat_ada_topik():
    import discord
    from discord.ui.select import BaseSelect

    def komponen(panel):
        return [
            item.custom_id
            for item in panel.walk_children()
            if isinstance(item, (discord.ui.Button, BaseSelect))
        ]

    assert komponen(views.TicketPanelView(GID)) == ["ticket:panel:open"]

    tickets.add_ticket_topic(GID, "Pembelian", emoji="🛒", deskripsi="Beli / kirim barang")
    tickets.add_ticket_topic(GID, "Lapor Bug", emoji="🐞")
    panel = views.TicketPanelView(GID)
    assert komponen(panel) == ["ticket:panel:topik", "ticket:panel:open"]
    select = next(i for i in panel.walk_children() if isinstance(i, BaseSelect))
    assert [o.value for o in select.options] == ["Pembelian", "Lapor Bug"]
    assert [o.label for o in select.options] == ["🛒 Pembelian", "🐞 Lapor Bug"]


@pytest.mark.asyncio
async def test_buka_tiket_topik_memakai_role_staf_topik():
    tickets.set_ticket_config(GID, enabled=True, staff_role_id=42, max_open=3)
    tickets.add_ticket_topic(GID, "Pembelian", emoji="🛒", staff_role_id=77)
    topik = tickets.find_topic(GID, "Pembelian")

    class _Thread:
        id = 9101

        def __init__(self):
            self.added: list[int] = []
            self.sent: list[dict] = []
            self.name = ""
            self.mention = "<#9101>"

        async def add_user(self, user):
            self.added.append(user.id)

        async def send(self, content=None, **kwargs):
            self.sent.append({"content": content, **kwargs})

    thread = _Thread()

    class _Channel:
        id = 700

        def __init__(self):
            self.created: dict = {}

        async def create_thread(self, **kwargs):
            self.created = kwargs
            return thread

    channel = _Channel()
    anggota_staf_topik = type("M", (), {"id": 620, "bot": False})()
    anggota_staf_umum = type("M", (), {"id": 610, "bot": False})()
    role_topik = type("R", (), {"id": 77, "members": [anggota_staf_topik]})()
    role_umum = type("R", (), {"id": 42, "members": [anggota_staf_umum]})()

    guild = type(
        "G",
        (),
        {
            "id": GID,
            "name": "Server Uji",
            "get_role": lambda self, rid: role_topik if int(rid) == 77 else role_umum,
        },
    )()

    class _Resp:
        def __init__(self):
            self.deferred = False
            self.sent: list[dict] = []

        async def defer(self, *, ephemeral=False):
            self.deferred = True

        async def send_message(self, content=None, **kwargs):
            self.sent.append({"content": content})

    class _Followup:
        def __init__(self):
            self.sent: list[dict] = []

        async def send(self, content=None, **kwargs):
            self.sent.append({"content": content})

    user = type(
        "U",
        (),
        {
            "id": 501,
            "name": "sari",
            "display_name": "Sari",
            "roles": [],
            "bot": False,
            "guild_permissions": type(
                "P",
                (),
                {"administrator": False, "manage_threads": False, "manage_channels": False},
            )(),
        },
    )()
    interaksi = type(
        "Ix",
        (),
        {
            "guild": guild,
            "guild_id": GID,
            "user": user,
            "channel": channel,
            "channel_id": 700,
            "response": _Resp(),
            "followup": _Followup(),
        },
    )()

    await views.handle_ticket_open(interaksi, topik=topik)
    assert interaksi.response.deferred is True
    # Nama thread memuat topik, pembuat + staf topik saja yang ditambahkan
    assert channel.created["name"] == "tiket-pembelian-sari"
    assert thread.added == [501, 620]
    assert 610 not in thread.added, "role staf umum tidak dipakai bila topik punya role sendiri"

    data = tickets.get_ticket(thread.id)
    assert data["topik"] == "Pembelian"
    assert data["topic"].startswith("Pembelian — Sari")
    # Ping memakai role topik
    assert "<@&77>" in str(thread.sent[0]["content"])
    assert "Tiket dibuat" in interaksi.followup.sent[0]["content"]


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_dashboard_kelola_topik_dan_render_form():
    ok, pesan = dashboard_tiket.topik_tambah(
        GID, "Pembelian", role_id=77, emoji="🛒", deskripsi="Beli <b>"
    )
    assert ok is True and "ditambahkan" in pesan
    assert dashboard_tiket.collect_tiket(GID)["topik"][0]["nama"] == "Pembelian"

    data = dashboard_tiket.collect_tiket(GID)
    data["items"] = []
    html = dashboard_ui.render_tiket_block(GID, data, "tok")
    assert "Topik panel tiket" in html
    assert 'value="topik-tambah"' in html
    assert 'value="topik-hapus"' in html
    assert 'name="role_id"' in html
    assert "Beli &lt;b&gt;" in html

    assert dashboard_tiket.topik_hapus(GID, "Pembelian")[0] is True
    assert dashboard_tiket.topik_hapus(GID, "Pembelian")[0] is False
    # Sistem tiket dimatikan → tidak ada jalur tulis di halaman
    mati = dashboard_ui.render_tiket_block(
        GID, {"items": [], "statistik": {"aktifkan": False}, "topik": []}, "tok"
    )
    assert "/api/tiket" not in mati


# ==============================================================================
# COMMAND
# ==============================================================================
def test_command_tiket_topik_terdaftar_dengan_parameter_lengkap():
    from cogs.growth_cog import tiket_group

    kunci = {c.name: c for c in tiket_group.commands}
    assert "topik" in kunci
    assert len(kunci["topik"].description) <= 100
    nama_param = {p.name for p in kunci["topik"].parameters}
    assert {"tambah", "hapus", "role", "emoji", "deskripsi"} <= nama_param
