"""Uji formulir (modal) buatan Admin — `modal_forms.py` & tombol panelnya."""

from __future__ import annotations

import pytest

import menu_builder
import modal_forms as mf


@pytest.fixture(autouse=True)
def _bersih(tmp_path, monkeypatch):
    monkeypatch.setattr(mf, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mf, "FORMS_FILE", tmp_path / "forms.json")
    mf.forms.clear()
    mf._cooldown.clear()
    yield
    mf.forms.clear()
    mf._cooldown.clear()


# ------------------------------------------------------------------------------
# TIRUAN
# ------------------------------------------------------------------------------
class FakeResponse:
    def __init__(self):
        self.sent: list[tuple[str, bool]] = []
        self.modal = None
        self.deferred = False

    def is_done(self) -> bool:
        return bool(self.sent or self.modal or self.deferred)

    async def send_message(self, teks, ephemeral=False, **kwargs):
        self.sent.append((teks, ephemeral))

    async def send_modal(self, modal):
        self.modal = modal

    async def defer(self, ephemeral=False, thinking=False, **kwargs):
        self.deferred = True


class FakeFollowup:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, *args, **kwargs):
        self.sent.append({"args": args, **kwargs})


class FakeUser:
    def __init__(self, user_id=4001, nama="Budi"):
        self.id = user_id
        self.name = nama.lower()
        self.display_name = nama
        self.mention = f"<@{user_id}>"
        self.bot = False


class FakeGuild:
    id = 999
    name = "Server Uji"


class FakeChannel:
    def __init__(self, channel_id=500):
        self.id = channel_id
        self.mention = f"<#{channel_id}>"
        self.name = "lamaran"
        self.terkirim: list[dict] = []

    async def send(self, *args, **kwargs):
        self.terkirim.append({"args": args, **kwargs})


class FakeClient:
    def __init__(self, channels=()):
        self._channels = {ch.id: ch for ch in channels}

    def get_channel(self, channel_id):
        return self._channels.get(int(channel_id))

    async def fetch_channel(self, channel_id):
        return self._channels.get(int(channel_id))


class FakeInteraction:
    def __init__(self, *, user=None, guild=None, client=None):
        self.user = user or FakeUser()
        self.guild = guild or FakeGuild()
        self.client = client or FakeClient([FakeChannel()])
        self.response = FakeResponse()
        self.followup = FakeFollowup()


# ------------------------------------------------------------------------------
# PARSER KOLOM
# ------------------------------------------------------------------------------
def test_parse_kolom_dasar():
    kolom, galat = mf.parse_fields("Nama | Umur")
    assert galat == []
    assert [(k["id"], k["style"], k["required"]) for k in kolom] == [
        ("nama", mf.STYLE_SHORT, True),
        ("umur", mf.STYLE_SHORT, True),
    ]


@pytest.mark.parametrize("teks", ["Alasan:panjang?", "Alasan?:panjang", "Alasan:panjang ?"])
def test_parse_penanda_opsional_urutan_bebas(teks):
    kolom, galat = mf.parse_fields(teks)
    assert galat == []
    assert kolom[0]["style"] == mf.STYLE_LONG
    assert kolom[0]["required"] is False


def test_parse_membatasi_lima_kolom():
    kolom, galat = mf.parse_fields(" | ".join(f"Kolom{i}" for i in range(1, 8)))
    assert len(kolom) == mf.MAX_FIELDS
    assert any("5 kolom pertama" in g for g in galat)


def test_parse_id_unik_dan_aman():
    kolom, _ = mf.parse_fields("Nama | nama | Nama!!")
    ids = [k["id"] for k in kolom]
    assert ids[0] == "nama"
    assert len(set(ids)) == 3


def test_parse_kosong_ditolak():
    kolom, galat = mf.parse_fields("   |   ")
    assert kolom == [] and galat


def test_label_dipotong_sesuai_batas_discord():
    kolom, _ = mf.parse_fields("x" * 200)
    assert len(kolom[0]["label"]) == mf.MAX_LABEL


# ------------------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------------------
def test_create_form_menolak_nama_ganda():
    form, galat = mf.create_form(999, "Lamaran", "Nama")
    assert form is not None and galat == []
    kedua, galat2 = mf.create_form(999, "Lamaran", "Nama")
    assert kedua is None
    assert any("Sudah ada" in g for g in galat2)


def test_create_form_menolak_penjelasan_plus_lima_kolom():
    form, galat = mf.create_form(
        999, "Panjang", "A|B|C|D|E", description="Isi dengan jujur"
    )
    assert form is None
    assert any("maksimal **4 kolom**" in g for g in galat)


def test_create_form_penjelasan_plus_empat_kolom_ok():
    form, galat = mf.create_form(999, "Pas", "A|B|C|D", description="Halo")
    assert form is not None and galat == []


def test_get_form_lewat_nama_tidak_peka_huruf():
    form, _ = mf.create_form(999, "Lamaran Staff", "Nama")
    assert mf.get_form(999, "lamaran staff") is form
    assert mf.get_form(999, form["id"]) is form
    assert mf.get_form(999, "tidak ada") is None


def test_update_form_menolak_nama_bentrok():
    mf.create_form(999, "Satu", "Nama")
    dua, _ = mf.create_form(999, "Dua", "Nama")
    galat = mf.update_form(dua, name="Satu")
    assert any("sudah dipakai" in g for g in galat)
    assert dua["name"] == "Dua"


def test_update_form_menolak_kolom_kebanyakan_bila_ada_penjelasan():
    form, _ = mf.create_form(999, "F", "A", description="Halo")
    galat = mf.update_form(form, fields="A|B|C|D|E")
    assert any("maksimal" in g for g in galat)
    assert len(form["fields"]) == 1


def test_delete_form():
    form, _ = mf.create_form(999, "Hapus Aku", "Nama")
    assert mf.delete_form(999, form["id"]) is True
    assert mf.get_form(999, form["id"]) is None
    assert mf.delete_form(999, "tidak-ada") is False


# ------------------------------------------------------------------------------
# RENDER HASIL
# ------------------------------------------------------------------------------
def test_render_template_hasil_memakai_nilai_dan_variabel():
    form, _ = mf.create_form(
        999, "F", "Nama | Umur", result_text="**{form.nama}** ({form.umur}) di {server.name}"
    )
    teks = mf.render_result(form, {"nama": "Budi", "umur": "20"}, guild=FakeGuild())
    assert teks == "**Budi** (20) di Server Uji"


def test_render_template_hasil_tanpa_template_membuat_daftar():
    form, _ = mf.create_form(999, "F", "Nama | Alasan:panjang")
    teks = mf.render_result(form, {"nama": "Budi"})
    assert "**Nama**\nBudi" in teks
    assert "**Alasan**\n—" in teks  # kolom kosong diberi tanda


def test_render_membersihkan_token_form_yang_tidak_ada():
    form, _ = mf.create_form(999, "F", "Nama", result_text="{form.tidak_ada}!")
    assert mf.render_result(form, {"nama": "x"}) == "!"


def test_result_embed_warna_dan_footer():
    form, _ = mf.create_form(999, "Lamaran", "Nama", color="hijau")
    embed = mf.result_embed(form, {"nama": "Budi"}, member=FakeUser())
    assert embed.title.startswith("📩")
    assert embed.colour.value == mf.WARNA_NAMA["hijau"]
    assert "Budi" in (embed.footer.text or "")


def test_parse_color():
    assert mf.parse_color("ungu").value == 0x9B59B6
    assert mf.parse_color("#3498db").value == 0x3498DB
    assert mf.parse_color("") is None
    assert mf.parse_color("bukanwarna") is None


# ------------------------------------------------------------------------------
# MODAL
# ------------------------------------------------------------------------------
def test_modal_memuat_kolom_dan_penjelasan():
    form, _ = mf.create_form(999, "F", "Nama | Alasan:panjang", description="Isi jujur")
    modal = mf.FormModal(form, member=FakeUser(), guild=FakeGuild())
    payload = modal.to_dict()

    assert payload["title"] == "F"
    assert payload["components"][0]["type"] == 10          # TextDisplay (penjelasan)
    labels = [c for c in payload["components"] if c["type"] == 18]
    assert [c["label"] for c in labels] == ["Nama", "Alasan"]
    assert labels[1]["component"]["style"] == 2            # paragraf
    assert modal.values() == {"nama": "", "alasan": ""}


def test_modal_tanpa_penjelasan_muat_lima_kolom():
    form, _ = mf.create_form(999, "F", "A|B|C|D|E")
    modal = mf.FormModal(form)
    assert len(modal.to_dict()["components"]) == 5


@pytest.mark.asyncio
async def test_open_modal_untuk_formulir_hilang():
    interaction = FakeInteraction()
    assert await mf.open_form_modal(interaction, None) is False
    assert interaction.response.modal is None
    assert "sudah dihapus" in interaction.response.sent[0][0]


@pytest.mark.asyncio
async def test_open_modal_dan_cooldown():
    form, _ = mf.create_form(999, "F", "Nama")
    interaction = FakeInteraction()
    assert await mf.open_form_modal(interaction, form) is True
    assert isinstance(interaction.response.modal, mf.FormModal)

    mf._mark_cooldown(999, form["id"], interaction.user.id)
    kedua = FakeInteraction()
    assert await mf.open_form_modal(kedua, form) is False
    assert "Tunggu" in kedua.response.sent[0][0]


# ------------------------------------------------------------------------------
# PENGIRIMAN JAWABAN
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_submit_mengirim_embed_ke_channel_tujuan():
    channel = FakeChannel()
    form, _ = mf.create_form(999, "Lamaran", "Nama | Umur", channel_id=channel.id)
    interaction = FakeInteraction(client=FakeClient([channel]))

    ok = await mf.submit_form(interaction, form, {"nama": "Budi", "umur": "20"})

    assert ok is True
    assert len(channel.terkirim) == 1
    kirim = channel.terkirim[0]
    assert "Budi" in kirim["embed"].description
    assert isinstance(kirim["allowed_mentions"], type(kirim["allowed_mentions"]))
    assert kirim["allowed_mentions"].everyone is False      # mention massal mati
    assert form["responses"] == 1
    assert interaction.followup.sent and "Terima kasih" in interaction.followup.sent[-1]["args"][0]


@pytest.mark.asyncio
async def test_submit_channel_tujuan_hilang():
    form, _ = mf.create_form(999, "Lamaran", "Nama", channel_id=123)
    interaction = FakeInteraction(client=FakeClient([]))
    ok = await mf.submit_form(interaction, form, {"nama": "Budi"})
    assert ok is False
    assert "tidak ditemukan" in interaction.response.sent[0][0]
    assert form["responses"] == 0


@pytest.mark.asyncio
async def test_submit_mode_uji_tidak_mengirim_ke_channel():
    channel = FakeChannel()
    form, _ = mf.create_form(999, "Lamaran", "Nama", channel_id=channel.id)
    interaction = FakeInteraction(client=FakeClient([channel]))

    ok = await mf.submit_form(interaction, form, {"nama": "Budi"}, uji=True)

    assert ok is True
    assert channel.terkirim == []
    embed = interaction.followup.sent[-1]["embed"]
    assert embed.title.startswith("🔍 Pratinjau")
    assert form["responses"] == 0


# ------------------------------------------------------------------------------
# SIMPAN / MUAT
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_simpan_lalu_muat_kembali():
    form, _ = mf.create_form(999, "Lamaran", "Nama | Alasan:panjang?", channel_id=500, color="biru")
    await mf.save_to_disk()

    mf.forms.clear()
    assert mf.load_from_disk() == 1
    lagi = mf.get_form(999, "Lamaran")
    assert lagi is not None
    assert lagi["channel_id"] == 500
    assert lagi["fields"][1]["style"] == mf.STYLE_LONG
    assert lagi["fields"][1]["required"] is False


@pytest.mark.asyncio
async def test_muat_melewati_formulir_tanpa_kolom(tmp_path):
    import json

    mf.FORMS_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "guilds": {
                    "999": {
                        "f1": {"id": "f1", "name": "Rusak", "fields": []},
                        "f2": {"id": "f2", "name": "Sehat", "fields": [{"label": "Nama"}]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert mf.load_from_disk() == 1
    assert mf.get_form(999, "Sehat") is not None


# ------------------------------------------------------------------------------
# TOMBOL PANEL
# ------------------------------------------------------------------------------
def test_add_form_button_dan_handle_button_membuka_modal():
    form, _ = mf.create_form(999, "Lamaran", "Nama")
    menu = menu_builder.create_menu(999, "Panel Uji")

    item = menu_builder.add_form_button(menu, form, label="📝 Daftar")
    assert item["kind"] == menu_builder.KIND_FORM
    assert item["form_id"] == form["id"]

    view = menu_builder.build_view(menu)
    assert view is not None


@pytest.mark.asyncio
async def test_handle_button_formulir_membuka_modal():
    form, _ = mf.create_form(999, "Lamaran", "Nama")
    menu = menu_builder.create_menu(999, "Panel Uji")
    item = menu_builder.add_form_button(menu, form)

    interaction = FakeInteraction()
    await menu_builder.handle_button(interaction, menu["id"], item["id"])
    assert isinstance(interaction.response.modal, mf.FormModal)


def test_form_button_tanpa_form_id_dibuang_dari_disk():
    bersih = menu_builder._sanitize_buttons(
        [
            {"kind": menu_builder.KIND_FORM, "label": "Hilang"},
            {"kind": menu_builder.KIND_FORM, "label": "Ada", "form_id": "f1"},
        ]
    )
    assert [b["label"] for b in bersih] == ["Ada"]
