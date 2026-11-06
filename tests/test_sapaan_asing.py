"""Sapaan welcome/goodbye: bahasa asing + huruf latin + terjemahannya."""

import dashboard_admin
import community_agent as ca

MYANMAR = next(item for item in ca.ASIAN_GREETINGS if item["key"] == "myanmar")


def test_semua_kata_punya_huruf_latin_dan_arti():
    for item in ca.ASIAN_GREETINGS + ca.ASIAN_FAREWELLS:
        assert item.get("word"), item
        assert item.get("read"), item          # huruf latin wajib ada
        assert item.get("arti"), item          # terjemahan wajib ada
        assert item.get("lang"), item


def test_contoh_myanmar_sesuai_permintaan():
    teks = ca.format_greeting_markdown(MYANMAR)
    assert teks == '**"မင်္ဂလာပါ"** (Mingalaba) — *semoga berkah*'

    # Panel admin / prompt memuat aksara, latin, arti, & bahasa
    admin = ca.format_greeting_word(MYANMAR)
    assert "မင်္ဂလာပါ" in admin and "Mingalaba" in admin
    assert "semoga berkah" in admin and "Myanmar" in admin


def test_kata_latin_tidak_diulang():
    halo = next(item for item in ca.ASIAN_GREETINGS if item["word"] == "Halo")
    teks = ca.format_greeting_markdown(halo)
    assert teks == '**"Halo"** — *halo*'
    assert "(Halo)" not in teks


def test_arti_bisa_dimatikan():
    teks = ca.format_greeting_markdown(MYANMAR, dengan_arti=False)
    assert teks == '**"မင်္ဂလာပါ"** (Mingalaba)'
    assert "semoga berkah" not in teks


def test_finalisasi_menempel_hiasan_dan_menjaga_mention():
    hasil = ca._finalize_greeting_text("Selamat datang ya!", MYANMAR, "<@555>")
    assert hasil.startswith('**"မင်္ဂလာပါ"** (Mingalaba) — *semoga berkah*')
    assert "<@555>" in hasil
    assert "Selamat datang ya!" in hasil

    # AI kadang sudah menulis aksaranya: jangan sampai dobel
    dobel = ca._finalize_greeting_text('မင်္ဂလာပါ <@555>, halo!', MYANMAR, "<@555>")
    assert dobel.count("မင်္ဂလာပါ") == 1
    assert dobel.count("<@555>") == 1

    tanpa_arti = ca._finalize_greeting_text("Hai!", MYANMAR, "<@555>", dengan_arti=False)
    assert "semoga berkah" not in tanpa_arti
    assert "Mingalaba" in tanpa_arti


async def test_preferensi_arti_tersimpan_di_config():
    cfg = ca.set_welcome_config(77, 778, enabled=True)
    assert cfg["arti"] is True
    cfg = ca.set_welcome_config(77, 778, enabled=True, arti=False)
    assert cfg["arti"] is False
    # Tidak disebut → nilai lama dipertahankan
    cfg = ca.set_welcome_config(77, 778, enabled=True, persona="lucu")
    assert cfg["arti"] is False and cfg["persona"] == "lucu"

    g = ca.set_goodbye_config(77, 779, enabled=True)
    assert g["arti"] is True
    g = ca.set_goodbye_config(77, 779, enabled=True, arti=False)
    assert g["arti"] is False


def test_setelan_dashboard_untuk_bahasa_dan_arti():
    for kunci in ("sambutan.bahasa", "sambutan.arti", "pamit.bahasa", "pamit.arti"):
        assert kunci in dashboard_admin.FITUR, kunci

    opsi = dict(dashboard_admin.FITUR["sambutan.bahasa"]["opsi"])
    assert opsi["auto"].startswith("🌏")
    assert "myanmar" in opsi and opsi["myanmar"] == "Myanmar"
    assert "jepang" in dict(dashboard_admin.FITUR["pamit.bahasa"]["opsi"])


async def test_setelan_bahasa_mengubah_kata_sapaan():
    ca.set_welcome_config(88, 880, enabled=True)
    ok, pesan = await dashboard_admin.apply(88, "sambutan.bahasa", "myanmar")
    assert ok and "myanmar" in pesan.lower()
    assert ca.welcome_agent_guilds[88]["hello_language"] == "myanmar"

    ok, pesan = await dashboard_admin.apply(88, "sambutan.arti", "off")
    assert ok and "disembunyikan" in pesan
    assert ca.welcome_agent_guilds[88]["arti"] is False

    # Tanpa channel pamit, setelan ditolak dengan pesan jelas
    ok, pesan = await dashboard_admin.apply(88, "pamit.bahasa", "korea")
    assert ok is False and "pamit" in pesan.lower()


def test_pilihan_bahasa_slash_command_tidak_melebihi_batas_discord():
    from cogs.agent_cog import _language_choices

    choices = _language_choices(ca.ASIAN_GREETINGS)
    assert len(choices) <= 25
    assert choices[0].value == "auto"
