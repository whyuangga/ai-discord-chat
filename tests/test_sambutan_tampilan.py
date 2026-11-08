"""Tes empat mode tampilan sambutan/perpisahan + panel pratinjau dashboard.

Menjaga tiga hal yang mudah rusak tanpa sengaja:

1. Empat mode (`card`, `embed`, `text`, `container`) menghasilkan bentuk pesan
   yang berbeda, dan mode yang tidak bisa dipakai **mundur** dengan aman
   (Card tanpa gambar → Embed).
2. Mention hanya hidup di `content` — mode `container` wajib mengirimkannya.
3. Nama mode lama (`mati`/`statis`/`dinamis`) tetap dipetakan sehingga data
   setelan yang sudah tersimpan tidak rusak.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import community_agent
import dashboard_sambutan
import welcome_view

GID = 123456789012345678
TOKEN = "tok"


class _Avatar:
    url = "https://cdn.discordapp.com/avatars/1/a.png"

    async def read(self):
        return b""


def _member(nama="Anggota Baru"):
    return SimpleNamespace(
        id=501,
        display_name=nama,
        name=nama,
        mention="<@501>",
        display_avatar=_Avatar(),
    )


def _guild():
    return SimpleNamespace(id=GID, name="Whyu Test", member_count=3, roles=[])


@pytest.fixture(autouse=True)
def _bersih():
    community_agent.welcome_agent_guilds.pop(GID, None)
    community_agent.goodbye_agent_guilds.pop(GID, None)
    yield
    community_agent.welcome_agent_guilds.pop(GID, None)
    community_agent.goodbye_agent_guilds.pop(GID, None)


# --------------------------------------------------------------------------- #
# Mode & normalisasi
# --------------------------------------------------------------------------- #
def test_empat_mode_tersedia_dan_berurutan():
    assert list(welcome_view.VIEW_MODES) == ["card", "embed", "text", "container"]
    assert welcome_view.label("card") == "Card"
    assert welcome_view.label("container") == "Container"


@pytest.mark.parametrize(
    "masukan,harapan",
    [
        ("card", "card"),
        ("EMBED", "embed"),
        (" Container ", "container"),
        # nama lama tetap dipetakan
        ("mati", "text"),
        ("statis", "embed"),
        ("dinamis", "card"),
        # nilai ngawur jatuh ke text, bukan error
        ("ngawur", "text"),
        ("", "text"),
        (None, "text"),
    ],
)
def test_normalisasi_mode(masukan, harapan):
    assert welcome_view.normalisasi_mode(masukan) == harapan


def test_mode_kartu_butuh_gambar():
    assert welcome_view.butuh_gambar("card") is True
    assert welcome_view.butuh_gambar("embed") is False
    assert welcome_view.butuh_gambar("text") is False
    assert welcome_view.butuh_gambar("container") is False


# --------------------------------------------------------------------------- #
# Variabel template
# --------------------------------------------------------------------------- #
def test_isi_variabel_mengganti_semua_kunci():
    teks = "Hai {user_mention} / {user_name} / {user} di {server} (member {member_count}, {count})"
    hasil = welcome_view.isi_variabel(teks, member=_member("Budi"), guild=_guild(), member_count=3)
    assert "<@501>" in hasil
    assert "Budi" in hasil
    assert "Whyu Test" in hasil
    assert "member 3" in hasil
    assert "{" not in hasil


def test_isi_variabel_aman_untuk_data_kosong():
    """Variabel yang tidak bisa diisi dibiarkan agar Admin melihat salah ketik."""
    hasil = welcome_view.isi_variabel("Hai {user_name} di {server}", member=None, guild=None)
    assert "{user_name}" in hasil and "{server}" in hasil


def test_template_bawaan_berbeda_per_jenis():
    assert "Selamat datang" in welcome_view.template_bawaan("welcome")
    assert "Sampai jumpa" in welcome_view.template_bawaan("goodbye")


# --------------------------------------------------------------------------- #
# Payload per mode
# --------------------------------------------------------------------------- #
def test_payload_text_hanya_content():
    isi = welcome_view.payload("text", guild_id=GID, guild=_guild(), member=_member(), teks="Halo")
    assert isi == {"content": "Halo"}


def test_payload_embed_tanpa_berkas():
    isi = welcome_view.payload("embed", guild_id=GID, guild=_guild(), member=_member(), teks="Halo")
    assert set(isi) == {"embed"}
    assert isi["embed"].description == "Halo"


def test_payload_embed_dengan_banner_attachment():

    isi = welcome_view.payload(
        "embed",
        guild_id=GID,
        guild=_guild(),
        member=_member(),
        teks="Halo",
        banner_url="attachment://banner-welcome.png",
    )
    assert isi["embed"].image.url == "attachment://banner-welcome.png"


def test_payload_card_memakai_lampiran():
    isi = welcome_view.payload(
        "card",
        guild_id=GID,
        guild=_guild(),
        member=_member(),
        teks="Halo",
        kartu_bytes=b"\x89PNG\r\n\x1a\n",
        kartu_nama="sambutan-welcome.png",
    )
    assert set(isi) == {"embed", "file"}
    assert isi["file"].filename == "sambutan-welcome.png"
    assert isi["embed"].image.url == "attachment://sambutan-welcome.png"


def test_payload_card_tanpa_gambar_mundur_ke_embed():
    """Card tanpa gambar kartu tidak boleh gagal — harus jadi Embed."""
    isi = welcome_view.payload("card", guild_id=GID, guild=_guild(), member=_member(), teks="Halo")
    assert set(isi) == {"embed"}
    assert isi["embed"].description == "Halo"


def test_payload_container_membawa_mention_di_content():
    isi = welcome_view.payload(
        "container",
        guild_id=GID,
        guild=_guild(),
        member=_member(),
        teks="Hai <@501> di **Whyu Test**",
    )
    assert "view" in isi
    assert isi["content"] == "<@501>"


def test_payload_container_tanpa_mention_tidak_mengirim_content():
    isi = welcome_view.payload("container", guild_id=GID, guild=_guild(), member=_member(), teks="Halo")
    assert set(isi) == {"view"}


def test_payload_container_berisi_container_bertema():
    from discord import ui

    isi = welcome_view.payload("container", guild_id=GID, guild=_guild(), member=_member(), teks="Halo")
    assert isinstance(isi["view"].children[0], ui.Container)


def test_payload_menghormati_kind_goodbye():
    isi = welcome_view.payload(
        "embed", guild_id=GID, guild=_guild(), member=_member(), teks="Dadah", kind="goodbye"
    )
    assert "Sampai Jumpa" in isi["embed"].title


# --------------------------------------------------------------------------- #
# Setelan tersimpan
# --------------------------------------------------------------------------- #
def test_set_welcome_card_mode_menyimpan_view_mode():
    community_agent.set_welcome_config(GID, 600, enabled=True)
    assert community_agent.set_welcome_card_mode(GID, "container") == "container"
    assert community_agent.welcome_agent_guilds[GID]["view_mode"] == "container"


def test_set_welcome_card_mode_tanpa_config_tidak_melempar():
    assert community_agent.set_welcome_card_mode(GID, "embed") == "embed"


def test_template_greeting_simpan_baca_dan_bawaan():
    community_agent.set_welcome_config(GID, 600, enabled=True)
    assert community_agent.template_greeting(GID, "welcome") == welcome_view.template_bawaan("welcome")

    assert community_agent.set_template_greeting(GID, "welcome", "Hai {user_name}!") == "Hai {user_name}!"
    assert community_agent.template_greeting(GID, "welcome") == "Hai {user_name}!"

    # dikosongkan → kembali ke bawaan
    community_agent.set_template_greeting(GID, "welcome", "   ")
    assert community_agent.template_greeting(GID, "welcome") == welcome_view.template_bawaan("welcome")


def test_set_goodbye_view_mode():
    community_agent.goodbye_agent_guilds[GID] = {"enabled": True, "channel_id": 700}
    assert community_agent.set_goodbye_view_mode(GID, "card") == "card"
    assert community_agent.goodbye_agent_guilds[GID]["view_mode"] == "card"


# --------------------------------------------------------------------------- #
# Panel dashboard + pratinjau
# --------------------------------------------------------------------------- #
def _bot():
    return SimpleNamespace(get_guild=lambda gid: _guild() if gid == GID else None)


def test_panel_tampilan_render_dengan_pratinjau():
    community_agent.set_welcome_config(GID, 600, enabled=True)
    community_agent.set_welcome_card_mode(GID, "text")

    html = dashboard_sambutan.render_tampilan_block(_bot(), GID, TOKEN)

    assert 'id="p-tampilan"' in html
    assert "sambutan.tampilan" in html and "sambutan.template" in html
    assert "pamit.tampilan" in html and "pamit.template" in html
    # keempat tombol mode muncul untuk sambutan dan perpisahan
    for mode in ("card", "embed", "text", "container"):
        assert f'value="{mode}"' in html
    # pratinjau hadir (satu per bagian)
    assert html.count("pratinjau-kotak") == 2
    assert "pratinjau-teks" in html


def test_panel_tampilan_pratinjau_berubah_mengikuti_mode():
    import asyncio

    community_agent.set_welcome_config(GID, 600, enabled=True)

    asyncio.run(dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.tampilan", "card"))
    html_kartu = dashboard_sambutan.render_tampilan_block(_bot(), GID, TOKEN)
    assert "pratinjau-kartu" in html_kartu
    assert "pratinjau-teks" not in html_kartu

    asyncio.run(dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.tampilan", "embed"))
    html_embed = dashboard_sambutan.render_tampilan_block(_bot(), GID, TOKEN)
    assert "pratinjau-embed" in html_embed


def test_panel_tampilan_hanya_untuk_bagian_tertentu():
    community_agent.set_welcome_config(GID, 600, enabled=True)
    html = dashboard_sambutan.render_tampilan_block(_bot(), GID, TOKEN, hanya=("goodbye",))
    assert "pamit.tampilan" in html
    assert "sambutan.tampilan" not in html


def test_panel_tampilan_menampilkan_variabel():
    html = dashboard_sambutan.render_tampilan_block(_bot(), GID, TOKEN)
    for nama in ("{user_mention}", "{user_name}", "{server}", "{member_count}"):
        assert nama in html


def test_panel_tampilan_menyebut_mention_tidak_jalan_di_embed():
    community_agent.set_welcome_config(GID, 600, enabled=True)
    community_agent.set_welcome_card_mode(GID, "embed")
    html = dashboard_sambutan.render_tampilan_block(_bot(), GID, TOKEN)
    assert "tidak</b> me-ping" in html or "tidak me-ping" in html


# --------------------------------------------------------------------------- #
# Aksi POST
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_aksi_tampilan_menyimpan_dan_memberi_catatan_kartu():
    community_agent.set_welcome_config(GID, 600, enabled=True)
    ok, pesan = await dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.tampilan", "card")
    assert ok is True
    assert "Card" in pesan
    assert community_agent.welcome_agent_guilds[GID]["view_mode"] == "card"


@pytest.mark.asyncio
async def test_aksi_tampilan_menolak_tanpa_channel():
    ok, pesan = await dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.tampilan", "embed")
    assert ok is False
    assert "channel sambutan" in pesan


@pytest.mark.asyncio
async def test_aksi_template_menyimpan_dan_mengosongkan():
    community_agent.set_welcome_config(GID, 600, enabled=True)

    ok, pesan = await dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.template", "Hai {user}!")
    assert ok is True and "disimpan" in pesan

    ok, pesan = await dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.template", "  ")
    assert ok is True and "dikosongkan" in pesan


@pytest.mark.asyncio
async def test_aksi_pamit_memakai_pool_perpisahan():
    community_agent.goodbye_agent_guilds[GID] = {"enabled": True, "channel_id": 700}
    ok, _ = await dashboard_sambutan.aksi_sambutan(None, GID, "pamit.tampilan", "container")
    assert ok is True
    assert community_agent.goodbye_agent_guilds[GID]["view_mode"] == "container"


@pytest.mark.asyncio
async def test_aksi_sambutan_mengembalikan_none_untuk_aksi_lain():
    assert await dashboard_sambutan.aksi_sambutan(None, GID, "musik-setelan", "x") is None
    assert await dashboard_sambutan.aksi_sambutan(None, GID, "voice-setelan", "x") is None


@pytest.mark.asyncio
async def test_aksi_sambutan_menolak_subaksi_asing():
    ok, pesan = await dashboard_sambutan.aksi_sambutan(None, GID, "sambutan.hapus", "x")
    assert ok is False and "tidak dikenal" in pesan
