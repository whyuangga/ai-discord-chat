"""Satu fitur = satu halaman: unggah kartu & tombol tes ikut di halaman fiturnya.

Selain itu, subjek tes tidak perlu ID: kosongkan saja → bot memakai pemilik server.
Dulu tes memakai akun bot sendiri, dan pemicu sambutan/perpisahan mengabaikan member
bot, jadi hasilnya selalu "Tidak ada yang terkirim".
"""

from __future__ import annotations

import types

import pytest

import dashboard_uji
import web_dashboard

GID = 1234
TOKEN = "tok-fitur"


# ==============================================================================
# FAKE DISCORD
# ==============================================================================
def _member(uid: int, nama: str, bot: bool = False):
    return types.SimpleNamespace(
        id=uid, display_name=nama, name=nama, global_name=nama,
        mention=f"<@{uid}>", bot=bot, display_avatar=None,
    )


class _Guild:
    id = GID
    name = "Server Uji"
    member_count = 4
    owner_id = 42

    def __init__(self):
        self.me = _member(1, "CoffeeBot", bot=True)
        self.members = [
            _member(42, "Bintang"),
            _member(77, "Rani"),
            _member(88, "Dimas"),
            _member(1, "CoffeeBot", bot=True),
        ]

    def get_member(self, uid):
        return next((m for m in self.members if m.id == int(uid)), None)


class _Channel:
    def __init__(self, cid, nama):
        self.id, self.name = cid, nama


class _Bot:
    def __init__(self):
        self.guilds = [_Guild()]
        self.user = _member(1, "CoffeeBot", bot=True)
        self.latency = 0.01

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GID else None

    def get_channel(self, cid):
        return _Channel(cid, f"kanal-{cid}")


def _guild():
    return _Bot().guilds[0]


# ==============================================================================
# SUBJEK TES: TANPA ID → PEMILIK SERVER
# ==============================================================================
async def test_subjek_otomatis_adalah_pemilik_server():
    orang, sumber = await dashboard_uji.ambil_subjek(_guild(), "")
    assert orang.id == 42 and sumber == "pemilik server"


async def test_subjek_terima_mention_id_dan_nama():
    guild = _guild()
    assert (await dashboard_uji.ambil_subjek(guild, "<@77>"))[0].display_name == "Rani"
    assert (await dashboard_uji.ambil_subjek(guild, "<@!42>"))[0].id == 42
    assert (await dashboard_uji.ambil_subjek(guild, "88"))[0].display_name == "Dimas"
    assert (await dashboard_uji.ambil_subjek(guild, "@rani"))[0].id == 77


async def test_subjek_menolak_akun_bot_dan_id_ngawur():
    guild = _guild()
    assert await dashboard_uji.ambil_subjek(guild, "1") == (None, "")      # akun bot
    assert await dashboard_uji.ambil_subjek(guild, "999") == (None, "")    # tidak ada


async def test_subjek_jatuh_ke_member_pertama_bila_pemilik_tidak_ada():
    guild = _guild()
    guild.owner_id = 999                       # pemilik sudah keluar dari server
    guild.members = [_member(77, "Rani")]
    orang, sumber = await dashboard_uji.ambil_subjek(guild, "")
    assert orang.id == 77 and sumber == "member pertama"


async def test_subjek_kosong_bila_server_tanpa_manusia():
    guild = _guild()
    guild.owner_id = 0
    guild.members = []
    assert await dashboard_uji.ambil_subjek(guild, "") == (None, "")


def test_dropdown_subjek_memakai_pemilik_paling_atas():
    pilihan = dashboard_uji.pilihan_subjek(_guild())
    assert pilihan[0] == ("42", "👑 Bintang")
    # Urut nama (Bintang, Dimas, Rani) dan akun bot dibuang
    assert [uid for uid, _ in pilihan] == ["42", "88", "77"]
    # Di dashboard pemilik sudah diwakili opsi default 👑 → tidak dobel
    tanpa_pemilik = dashboard_uji.pilihan_subjek(_guild(), sertakan_pemilik=False)
    assert [uid for uid, _ in tanpa_pemilik] == ["88", "77"]
    assert dashboard_uji.nama_pemilik(_guild()) == "Bintang"


async def test_uji_gagal_jelas_saat_tidak_ada_member(monkeypatch):
    guild = _guild()
    guild.owner_id = 0
    guild.members = []
    monkeypatch.setattr(_Bot, "get_guild", lambda self, gid: guild, raising=False)
    import community_agent

    community_agent.set_welcome_config(GID, 505, enabled=True)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "welcome")
    assert ok is False and "pemilik server" in pesan


async def test_uji_menyebut_nama_pemilik_saat_berhasil(monkeypatch):
    from cogs import agent_cog

    dipakai = {}

    async def pura_pura(bot, guild, member, *, force=False):
        dipakai["siapa"] = member.display_name
        return "Halo!"

    monkeypatch.setattr(agent_cog, "trigger_member_welcome", pura_pura)
    import community_agent

    community_agent.set_welcome_config(GID, 505, enabled=True)
    ok, pesan = await dashboard_uji.jalankan_uji(_Bot(), GID, "welcome")
    assert ok and dipakai["siapa"] == "Bintang"
    assert "pemilik server" in pesan and "Bintang" in pesan


# ==============================================================================
# HALAMAN: UNGGAH + TES DI FITURNYA
# ==============================================================================
def test_tiap_fitur_punya_halaman_sendiri():
    halaman = {h["slug"]: h for h in web_dashboard.HALAMAN}
    assert set(web_dashboard.FITUR_HALAMAN) == {"sambutan", "perpisahan", "boost"}
    assert halaman["sambutan"]["panel"] == ("p-sambutan",)
    assert halaman["perpisahan"]["panel"] == ("p-perpisahan",)
    assert halaman["boost"]["panel"] == ("p-boost",)
    # Halaman gabungan /uji sudah dihapus, /kirim tidak lagi memuat kartu
    assert "uji" not in halaman
    assert "p-kartu" not in halaman["kirim"]["panel"]


def test_tes_menempel_di_halaman_fiturnya():
    """Setiap fitur uji punya satu halaman tujuan (tidak ada lagi halaman tes global)."""
    peta = {}
    for slug, data in web_dashboard.FITUR_HALAMAN.items():
        for kunci in data["uji"]:
            peta[kunci] = slug
    for slug, kunci in web_dashboard.UJI_HALAMAN.items():
        for satu in kunci:
            peta[satu] = slug
    assert set(peta) == {item["kunci"] for item in dashboard_uji.UJI}
    assert peta["welcome"] == "sambutan" and peta["boost"] == "boost"
    assert peta["tiket"] == "tiket" and peta["ekspor"] == "ekspor"


def test_anchor_hasil_tes_dan_setelan_mengarah_ke_halaman_fitur():
    assert dashboard_uji.ANCHOR_UJI["welcome"] == "p-sambutan"
    assert dashboard_uji.ANCHOR_UJI["boost"] == "p-boost"
    for anchor in dashboard_uji.ANCHOR_UJI.values():
        assert web_dashboard.halaman_dari_anchor(anchor) != "" or anchor in (
            "p-setelan", "p-ai"
        )
    # Setelan sambutan disimpan dari halaman Sambutan → kembali ke sana
    assert web_dashboard._anchor_aksi("set.sambutan.channel") == "p-sambutan"
    assert web_dashboard._anchor_aksi("set.pamit.bahasa") == "p-perpisahan"
    assert web_dashboard._anchor_aksi("set.boost.channel") == "p-boost"
    assert web_dashboard._anchor_aksi("set.level.aktif") == "p-setelan"


def test_kartu_dan_tes_hanya_muncul_di_halaman_fiturnya():
    kartu = dashboard_uji and None
    assert kartu is None
    import dashboard_ui

    sambutan = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("welcome",))
    boost = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("boost",))
    assert "kartu.simpan:welcome" in sambutan and "kartu.simpan:boost" not in sambutan
    assert "kartu.simpan:boost" in boost and "kartu.simpan:welcome" not in boost
    # Mode kartu (statis/dinamis) hanya relevan untuk sambutan
    assert "set.sambutan.kartu" in sambutan
    assert "set.sambutan.kartu" not in boost


def test_setelan_sambutan_tidak_lagi_duplikat_di_halaman_setelan():
    import dashboard_admin
    import dashboard_ui

    page = dashboard_ui.render_setelan_block(
        {"sambutan.channel": "0", "level.aktif": "on"}, None, GID, TOKEN,
        kecuali_grup=("sambutan",),
    )
    assert "set.level.aktif" in page
    for kunci in ("sambutan.channel", "pamit.channel", "boost.channel"):
        assert f"set.{kunci}" not in page, kunci
    # Sebaliknya, halaman fitur hanya memuat setelannya sendiri
    khusus = dashboard_ui.render_setelan_block(
        {"sambutan.channel": "0", "level.aktif": "on"}, None, GID, TOKEN,
        hanya=web_dashboard.SETELAN_SAMBUTAN,
    )
    assert "set.sambutan.channel" in khusus and "set.level.aktif" not in khusus
    assert len(web_dashboard.SETELAN_SAMBUTAN) < len(dashboard_admin.FITUR)


def test_tombol_tes_di_halaman_fitur_unik():
    import dashboard_ui

    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("welcome",))
    assert html.count('class="uji-baris"') == 1
    assert "uji.welcome" in html and "uji.tiket" not in html
    assert "<h3>" not in html                    # satu fitur → tanpa judul grup
    assert "👑 Pemilik server (otomatis)" in html and "· Bintang" in html
    assert dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=()) == ""


def test_halaman_fitur_memuat_tiga_bagian():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="sambutan",
        setelan_block="SETELAN-X", kartu_block="KARTU-X", uji_block="UJI-X",
    )
    assert 'id="p-sambutan"' in page
    assert "⚙️ Setelan" in page and "🖼️ Gambar kartu" in page and "🧪 Tes fitur" in page
    assert "SETELAN-X" in page and "KARTU-X" in page and "UJI-X" in page


@pytest.mark.parametrize(
    "slug,penanda",
    [("", "p-ai"), ("buat", "p-buat"), ("panel", "p-panel"),
     ("tiket", "p-tiket"), ("ekspor", "p-ekspor"), ("setelan", "p-setelan")],
)
def test_tes_ikut_di_halaman_lain(slug, penanda):
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman=slug, uji_block="UJI-X"
    )
    assert f'id="{penanda}"' in page
    assert "UJI-X" in page


def test_tautan_atur_dulu_mengarah_ke_halaman_fitur_yang_benar():
    """Fitur mati → tautan “Atur dulu” harus mendarat di halaman yang punya setelannya."""
    import dashboard_ui
    import community_agent

    community_agent.boost_agent_guilds.pop(GID, None)          # boost belum aktif
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("boost",))
    assert "Atur dulu" in html
    assert f'href="/boost?token={TOKEN}&amp;guild={GID}#p-boost"' in html

    community_agent.goodbye_agent_guilds.pop(GID, None)
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("goodbye",))
    assert f'href="/perpisahan?token={TOKEN}&amp;guild={GID}#p-perpisahan"' in html

    community_agent.digest_agent_guilds.pop(GID, None)
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("digest",))
    assert f'href="/setelan?token={TOKEN}&amp;guild={GID}#p-setelan"' in html


def test_halaman_kartu_boost_tanpa_pemilih_mode():
    import dashboard_ui

    html = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("boost",))
    assert "Tampilan kartu sambutan" not in html
    assert "1024×420" in html
