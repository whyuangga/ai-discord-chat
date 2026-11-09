"""Satu grup fitur = satu halaman: unggah kartu & tombol tes ikut di halamannya.

Selain itu, subjek tes tidak perlu ID: kosongkan saja → bot memakai pemilik server.
Dulu tes memakai akun bot sendiri, dan pemicu sambutan/perpisahan mengabaikan member
bot, jadi hasilnya selalu "Tidak ada yang terkirim".
"""

from __future__ import annotations

import types

import pytest

import dashboard_ui
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
def test_satu_halaman_per_grup_setelan():
    halaman = {h["slug"]: h for h in web_dashboard.HALAMAN}
    # Sambutan, pamit, & boost digabung dalam satu halaman
    assert halaman["sambutan"]["panel"] == ("p-sambutan",)
    assert set(web_dashboard.BAGIAN_SAMBUTAN and
               [b[0] for b in web_dashboard.BAGIAN_SAMBUTAN]) == {"welcome", "goodbye", "boost"}
    # Tiap grup setelan punya halaman sendiri
    assert set(web_dashboard.GRUP_HALAMAN.values()) <= set(halaman)
    # Inti & level: kontrol cepat, setelan grup, + kartu rank (perender PNG)
    assert halaman["inti"]["panel"] == ("p-kontrol", "p-inti", "p-rank", "p-lencana")
    # Halaman tes gabungan & kartu di /kirim sudah tidak ada
    assert "uji" not in halaman
    assert "p-kartu" not in halaman["kirim"]["panel"]


def test_tes_menempel_di_halaman_fiturnya():
    """Setiap fitur uji punya satu halaman tujuan (tidak ada lagi halaman tes global)."""
    peta = {"welcome": "sambutan", "goodbye": "sambutan", "boost": "sambutan"}
    for slug, kunci in web_dashboard.UJI_HALAMAN.items():
        for satu in kunci:
            peta[satu] = slug
    assert set(peta) == {item["kunci"] for item in dashboard_uji.UJI}
    assert peta["welcome"] == "sambutan" and peta["boost"] == "sambutan"
    assert peta["tiket"] == "tiket" and peta["ekspor"] == "ekspor"


def test_anchor_hasil_tes_dan_setelan_mengarah_ke_halaman_fitur():
    assert dashboard_uji.ANCHOR_UJI["welcome"] == "p-welcome"
    assert dashboard_uji.ANCHOR_UJI["boost"] == "p-boost"
    assert dashboard_uji.ANCHOR_UJI["goodbye"] == "p-goodbye"
    for anchor in dashboard_uji.ANCHOR_UJI.values():
        assert web_dashboard.halaman_dari_anchor(anchor) != "" or anchor in (
            "p-setelan", "p-ai"
        )
    # Setelan sambutan disimpan dari halaman Sambutan → kembali ke sana
    assert web_dashboard._anchor_aksi("set.sambutan.channel") == "p-welcome"
    assert web_dashboard._anchor_aksi("set.pamit.bahasa") == "p-goodbye"
    assert web_dashboard._anchor_aksi("set.boost.channel") == "p-boost"
    assert web_dashboard._anchor_aksi("set.level.aktif") == "p-inti"


def test_kartu_dan_tes_hanya_muncul_di_halaman_fiturnya():
    kartu = dashboard_uji and None
    assert kartu is None
    import dashboard_ui

    # Sambutan & perpisahan tidak lagi memakai slot unggah kartu: tampilannya
    # dipilih lewat panel "Tampilan pesan" (Card/Embed/Text/Container).
    sambutan = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("welcome",))
    assert "set.sambutan.kartu" not in sambutan
    assert "set.sambutan.tampilan" not in sambutan

    boost = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("boost",))
    assert "kartu.simpan:boost" in boost and "kartu.simpan:welcome" not in boost
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


def test_halaman_sambutan_memuat_tiga_bagian():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="sambutan",
        setelan_welcome="SETELAN-W", setelan_goodbye="SETELAN-G", setelan_boost="SETELAN-B",
        kartu_welcome="KARTU-W", kartu_goodbye="KARTU-G", kartu_boost="KARTU-B",
        uji_welcome="UJI-W", uji_goodbye="UJI-G", uji_boost="UJI-B",
    )
    assert 'id="p-sambutan"' in page
    for anchor in ("p-welcome", "p-goodbye", "p-boost"):
        assert f'id="{anchor}"' in page
    for teks in ("SETELAN-W", "SETELAN-G", "SETELAN-B", "KARTU-W", "KARTU-G", "KARTU-B",
                 "UJI-W", "UJI-G", "UJI-B"):
        assert teks in page


@pytest.mark.parametrize(
    "slug,penanda",
    [("ai", "p-ai"), ("buat", "p-buat"), ("panel", "p-panel"), ("tiket", "p-tiket"),
     ("konten", "p-konten"), ("ekspor", "p-ekspor")],
)
def test_tes_ikut_di_halaman_lain(slug, penanda):
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman=slug, uji_block="UJI-X"
    )
    assert f'id="{penanda}"' in page
    assert "UJI-X" in page


@pytest.mark.parametrize("slug,penanda", [("inti", "p-inti"), ("keamanan", "p-keamanan")])
def test_halaman_grup_tanpa_tes(slug, penanda):
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman=slug, setelan_block="SETELAN-X"
    )
    assert f'id="{penanda}"' in page
    assert "SETELAN-X" in page


def test_kontrol_cepat_pindah_ke_halaman_inti():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="inti", kontrol_block="KONTROL-X"
    )
    assert 'id="p-kontrol"' in page and "KONTROL-X" in page


def test_tautan_atur_dulu_mengarah_ke_halaman_fitur_yang_benar():
    """Fitur mati → tautan “Atur dulu” harus mendarat di halaman yang punya setelannya."""
    import dashboard_ui
    import community_agent

    community_agent.boost_agent_guilds.pop(GID, None)          # boost belum aktif
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("boost",))
    assert "Atur dulu" in html
    assert f'href="/sambutan?token={TOKEN}&amp;guild={GID}#p-boost"' in html

    community_agent.goodbye_agent_guilds.pop(GID, None)
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("goodbye",))
    assert f'href="/sambutan?token={TOKEN}&amp;guild={GID}#p-goodbye"' in html

    community_agent.digest_agent_guilds.pop(GID, None)
    html = dashboard_ui.render_uji_block(_Bot(), GID, TOKEN, hanya=("digest",))
    assert f'href="/konten?token={TOKEN}&amp;guild={GID}#p-konten"' in html


def test_halaman_kartu_boost_tanpa_pemilih_mode():
    import dashboard_ui

    html = dashboard_ui.render_kartu_block(GID, TOKEN, hanya=("boost",))
    assert "Tampilan kartu sambutan" not in html
    assert "1024×420" in html


def test_halaman_lama_dialihkan_ke_halaman_grup():
    """Bookmark lama tetap hidup: /setelan → /inti, /perpisahan & /boost → /sambutan."""
    assert web_dashboard.LEGACY_HALAMAN["setelan"] == "inti"
    assert web_dashboard.LEGACY_HALAMAN["perpisahan"] == "sambutan"
    assert web_dashboard.LEGACY_HALAMAN["boost"] == "sambutan"
    assert web_dashboard.LEGACY_HALAMAN["uji"] == "ai"
    slug = {h["slug"] for h in web_dashboard.HALAMAN}
    assert set(web_dashboard.LEGACY_HALAMAN.values()) <= slug
    # Anchor lama menempel ke halaman grup barunya
    assert web_dashboard.ANCHOR_HALAMAN["p-setelan"] == "inti"
    assert web_dashboard.ANCHOR_HALAMAN["p-perpisahan"] == "sambutan"
    assert web_dashboard.ANCHOR_HALAMAN["p-kartu"] == "sambutan"


def test_lima_grup_setelan_punya_halaman():
    """Satu grup setelan = satu halaman (permintaan penggabungan halaman)."""
    assert web_dashboard.GRUP_HALAMAN == {
        "inti": "inti", "sambutan": "sambutan", "keamanan": "keamanan",
        "bantuan": "tiket", "konten": "konten",
    }
    halaman = {h["slug"]: h for h in web_dashboard.HALAMAN}
    # Semua fitur tiap grup kelihatan di halamannya masing-masing. Grup Konten
    # dipecah ke /konten dan /interaksi, jadi tiap kunci diperiksa ke halaman
    # yang benar-benar memuatnya.
    for grup, slug in web_dashboard.GRUP_HALAMAN.items():
        fitur = web_dashboard.fitur_grup(grup)
        assert fitur, grup
        for kunci in fitur:
            tujuan = web_dashboard.HALAMAN_SETELAN[kunci]
            assert tujuan in (slug, *web_dashboard.SUBGRUP_KONTEN.values()), (kunci, tujuan)
            assert tujuan in halaman, tujuan
    # Setiap setelan grup Konten muncul di tepat satu halaman.
    konten_slug = {web_dashboard.HALAMAN_SETELAN[k] for k in web_dashboard.fitur_grup("konten")}
    assert konten_slug == {"konten", "interaksi"}
    # Halaman sambutan memuat tiga bagian, bukan tiga halaman terpisah
    assert [b[0] for b in web_dashboard.BAGIAN_SAMBUTAN] == ["welcome", "goodbye", "boost"]
    assert "perpisahan" not in halaman and "boost" not in halaman and "setelan" not in halaman
    # Inti & level: kontrol cepat, setelan grup, + kartu rank (perender PNG)
    assert halaman["inti"]["panel"] == ("p-kontrol", "p-inti", "p-rank", "p-lencana")


@pytest.mark.parametrize(
    "kunci, potongan",
    [("welcome", "Sambutan"), ("goodbye", "Sambutan"), ("boost", "Sambutan"),
     ("digest", "Konten"), ("pengumuman", "Buat"), ("tiket", "Tiket"),
     ("keamanan", "Keamanan")],
)
def test_pesan_atur_dulu_menunjuk_halaman_grup(kunci, potongan):
    teks = dashboard_uji.halaman_uji(kunci)
    assert potongan in teks or "fiturnya" in teks
    assert "Setelan" not in teks          # halaman /setelan sudah tidak ada


def test_atur_dulu_tidak_pernah_ke_halaman_lama():
    """Tautan “Atur dulu” memakai halaman grup yang benar, bukan /setelan."""
    assert dashboard_ui._JALUR_FITUR["pengumuman"] == "/buat"
    assert dashboard_ui._JALUR_FITUR["digest"] == "/konten"
    assert dashboard_ui._JALUR_FITUR["welcome"] == "/sambutan"
    for jalur in dashboard_ui._JALUR_FITUR.values():
        assert jalur != "/setelan"
