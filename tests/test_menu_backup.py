"""Uji ekspor/impor panel (backup) & ubah teks panel — `menu_builder`."""

from __future__ import annotations

import pytest

import flows
import menu_builder as mb


@pytest.fixture(autouse=True)
def _bersihkan_menu():
    mb.menus.clear()
    yield
    mb.menus.clear()


def _panel_contoh(guild_id: int = 11) -> dict:
    menu = mb.create_menu(guild_id, "Panel Uji", description="Deskripsi awal", banner_url="https://x/y.png")
    mb.add_role_button(menu, 123, "Member", emoji="🎮")
    mb.add_link_button(menu, "Support", "https://discord.gg/contoh")
    mb.add_command_button(menu, "serverstats")
    mb.add_flow_button(menu, "Buka Tiket", flows.parse("+role:321 > pesan:Halo {member.mention}")[0])
    mb.add_dropdown(menu, "Pilih minat", [{"role_id": 555, "label": "Musik"}, {"role_id": 556, "label": "Gaming"}])
    return menu


def test_ekspor_membuang_id_dan_menyimpan_alur():
    menu = _panel_contoh()
    data = mb.export_menu(menu)

    assert data["format"] == mb.EXPORT_FORMAT and data["version"] == mb.EXPORT_VERSION
    assert data["title"] == "Panel Uji"
    assert len(data["buttons"]) == 4
    assert all("id" not in tombol for tombol in data["buttons"])
    assert data["buttons"][3]["flow"][0] == {"action": flows.ACTION_ROLE_ADD, "role_id": 321}
    assert len(data["dropdowns"][0]["options"]) == 2
    assert all("id" not in opt for opt in data["dropdowns"][0]["options"])


def test_impor_bolak_balik_menghasilkan_panel_baru():
    asli = _panel_contoh()
    data = mb.export_menu(asli)

    baru, galat = mb.import_menu(99, data)
    assert galat == []
    assert baru is not None and baru["guild_id"] == 99
    assert baru["id"] != asli["id"]
    assert baru["title"] == asli["title"] and baru["description"] == asli["description"]
    assert [b["kind"] for b in baru["buttons"]] == [b["kind"] for b in asli["buttons"]]
    # ID item dibuat ulang → tidak bentrok dengan panel asal
    assert set(b["id"] for b in baru["buttons"]).isdisjoint(b["id"] for b in asli["buttons"])
    assert len(baru["dropdowns"][0]["options"]) == 2


def test_impor_judul_baru_dan_batas_kuota():
    data = mb.export_menu(_panel_contoh())
    baru, galat = mb.import_menu(5, data, title="Panel Salinan")
    assert galat == [] and baru["title"] == "Panel Salinan"

    for i in range(mb.MAX_MENUS_PER_GUILD - 1):
        assert mb.create_menu(5, f"Panel {i}") is not None
    gagal, galat2 = mb.import_menu(5, data)
    assert gagal is None
    assert any("penuh" in g for g in galat2)


@pytest.mark.parametrize(
    "payload, potongan",
    [
        ("bukan objek", "bukan objek"),
        ({"format": "milik-orang-lain"}, "bukan ekspor panel"),
        ({"format": mb.EXPORT_FORMAT, "version": 99}, "lebih baru"),
        ({"format": mb.EXPORT_FORMAT, "buttons": "salah"}, "harus berupa daftar"),
        ({"format": mb.EXPORT_FORMAT, "buttons": []}, "Tidak ada tombol"),
    ],
)
def test_impor_menolak_payload_aneh(payload, potongan):
    menu, galat = mb.import_menu(7, payload)  # type: ignore[arg-type]
    assert menu is None
    assert any(potongan in g for g in galat), galat


def test_impor_melewati_item_tidak_valid_tanpa_gagal():
    payload = {
        "format": mb.EXPORT_FORMAT,
        "version": 1,
        "title": "Campur",
        "buttons": [
            {"kind": "role", "label": "Tanpa ID", "role_id": 0},
            {"kind": "link", "label": "URL salah", "url": "javascript:alert(1)"},
            {"kind": "command", "label": "Bahaya", "command": "ban"},
            {"kind": "flow", "label": "Alur kosong", "flow": [{"action": "hack"}]},
            {"kind": "link", "label": "Aman", "url": "https://contoh.test"},
            {"kind": "role", "label": "Member", "role_id": 4321},
        ],
        "dropdowns": [{"options": [{"label": "Tanpa role"}, {"role_id": 9, "label": "Oke"}]}],
    }
    menu, galat = mb.import_menu(8, payload)
    assert menu is not None
    assert [b["label"] for b in menu["buttons"]] == ["Aman", "Member"]
    assert len(galat) == 4, galat
    assert len(menu["dropdowns"][0]["options"]) == 1


def test_update_menu_text_mengubah_dan_memvalidasi():
    menu = mb.create_menu(3, "Judul Lama", description="Lama")
    assert mb.update_menu_text(menu, title="Judul Baru", description="Baru") == []
    assert menu["title"] == "Judul Baru" and menu["description"] == "Baru"

    galat = mb.update_menu_text(menu, title="   ")
    assert galat and menu["title"] == "Judul Baru"

    mb.update_menu_text(menu, description="x" * (mb.MAX_DESCRIPTION + 50))
    assert len(menu["description"]) == mb.MAX_DESCRIPTION
