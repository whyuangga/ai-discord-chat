"""Uji catatan internal staf pada tiket: modul, command, & dashboard.

Catatan internal **tidak pernah** dikirim ke thread tiket — hanya tersimpan di
`data/tickets.json` dan tampil di dashboard bagi staf.
"""

from __future__ import annotations

import pytest

import dashboard_tiket
import dashboard_ui
import tickets

GID = 1234
TID = 7001
TOKEN = "tok-tiket"


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


def _tiket(thread_id: int = TID, gid: int = GID) -> dict:
    return tickets.register_ticket(thread_id, gid, 501, topic="Nitro tidak masuk")


# ==============================================================================
# MODUL
# ==============================================================================
def test_tambah_baca_dan_hapus_catatan():
    data = _tiket()
    assert data["notes"] == []

    status, _ = tickets.add_note(TID, 2, "   ")
    assert status == "kosong"
    status, data = tickets.add_note(TID, 2, "Cek bukti transfer dulu")
    assert status == "ok" and len(data["notes"]) == 1
    assert data["notes"][0]["oleh"] == 2
    assert data["notes"][0]["at"] > 0

    tickets.add_note(TID, 3, "Sudah dikonfirmasi ke pembeli")
    assert [n["teks"] for n in tickets.list_notes(TID)] == [
        "Cek bukti transfer dulu",
        "Sudah dikonfirmasi ke pembeli",
    ]
    # Nomor 1 = paling lama
    status, data = tickets.remove_note(TID, 1)
    assert status == "ok" and len(data["notes"]) == 1
    assert tickets.remove_note(TID, 5)[0] == "tidak_ada"
    assert tickets.add_note(9999, 2, "x")[0] == "tidak_ada"


def test_catatan_dibatasi_dan_teks_dipotong():
    _tiket()
    for i in range(tickets.TICKET_NOTE_MAX):
        assert tickets.add_note(TID, 2, f"catatan {i}")[0] == "ok"
    assert tickets.add_note(TID, 2, "kelebihan")[0] == "penuh"

    tickets.remove_note(TID, 1)
    status, data = tickets.add_note(TID, 2, "x" * 900)
    assert status == "ok"
    assert len(data["notes"][-1]["teks"]) == tickets.TICKET_NOTE_LEN


@pytest.mark.asyncio
async def test_catatan_bertahan_setelah_simpan_dan_muat_ulang():
    _tiket()
    tickets.add_note(TID, 2, "Jangan lupa refund")
    await tickets.save_tickets_to_disk()
    assert tickets.TICKETS_FILE.exists()

    tickets.tickets.clear()
    tickets.ticket_guilds.clear()
    tickets.load_tickets_from_disk()
    assert [n["teks"] for n in tickets.list_notes(TID)] == ["Jangan lupa refund"]
    # Tiket lama (dibuat sebelum fitur ini) tetap aman tanpa kunci `notes`
    assert tickets.tickets[TID]["notes"][0]["oleh"] == 2


def test_muat_data_lama_tanpa_catatan_tetap_aman(tmp_path):
    import json

    berkas = tickets.TICKETS_FILE
    berkas.write_text(
        json.dumps(
            {
                "guilds": {str(GID): {"enabled": True}},
                "tickets": {
                    str(TID): {
                        "guild_id": GID, "user_id": 501, "number": 1,
                        "status": "terbuka", "topic": "Lama",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    tickets.load_tickets_from_disk()
    assert tickets.list_notes(TID) == []
    assert tickets.add_note(TID, 2, "catatan baru")[0] == "ok"


# ==============================================================================
# DASHBOARD
# ==============================================================================
def test_dashboard_catat_dan_hapus_catatan():
    _tiket()
    ok, pesan = dashboard_tiket.catat(GID, TID, "Cek bukti transfer")
    assert ok is True and "tersimpan" in pesan
    ok, pesan = dashboard_tiket.catat(GID, TID, "  ")
    assert ok is False and "kosong" in pesan
    ok, pesan = dashboard_tiket.catat(9999, TID, "salah server")
    assert ok is False and "tidak ditemukan" in pesan

    items = dashboard_tiket.collect_tiket(GID)["items"]
    assert items[0]["catatan"][0]["teks"] == "Cek bukti transfer"
    assert items[0]["catatan"][0]["waktu"] != "-"

    assert dashboard_tiket.hapus_catatan(GID, TID, 1)[0] is True
    assert dashboard_tiket.hapus_catatan(GID, TID, 1)[0] is False
    assert dashboard_tiket.collect_tiket(GID)["items"][0]["catatan"] == []


def test_render_kotak_masuk_menampilkan_catatan_dengan_form():
    _tiket()
    tickets.add_note(TID, 2, "Bukti <script>alert(1)</script> sudah dicek")
    data = dashboard_tiket.collect_tiket(GID)

    html = dashboard_ui.render_tiket_block(GID, data, TOKEN)
    assert f"catat:{TID}" in html
    assert f"catatan-hapus:{TID}:1" in html
    assert "Catatan staf" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert f'name="token" value="{TOKEN}"' in html


# ==============================================================================
# COMMAND DISCORD
# ==============================================================================
def test_command_tiket_catat_terdaftar_dengan_deskripsi_pendek():
    from cogs.growth_cog import tiket_group

    kunci = {c.name: c for c in tiket_group.commands}
    assert "catat" in kunci and "catatan" in kunci
    for nama in ("catat", "catatan"):
        assert len(kunci[nama].description) <= 100
    # Parameter `teks` wajib ada di /tiket catat, `hapus` opsional di /tiket catatan
    param_catat = {p.name for p in kunci["catat"].parameters}
    assert "teks" in param_catat
    assert "hapus" in {p.name for p in kunci["catatan"].parameters}
