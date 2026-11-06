"""Uji peta fitur baca-saja di dashboard web (`web_dashboard.py`)."""

from __future__ import annotations

import menu_builder
import modal_forms
import web_dashboard as wd


def test_collect_features_membaca_data_server(monkeypatch):
    monkeypatch.setattr(menu_builder, "list_menus", lambda gid: [{"id": "m1"}, {"id": "m2"}])
    monkeypatch.setattr(modal_forms, "list_forms", lambda gid: [])

    data = wd.collect_features(999)

    assert data["total"] >= 2
    panel = next(r for r in data["items"] if r["nama"] == "Panel menu")
    assert panel["aktif"] is True and "2" in panel["ringkas"]
    assert panel["perintah"].startswith("/menu")

    formulir = next(r for r in data["items"] if r["nama"] == "Formulir (modal)")
    assert formulir["aktif"] is False and formulir["ringkas"] == "belum dipakai"
    assert data["aktif"] == sum(1 for r in data["items"] if r["aktif"])


def test_render_features_block_berisi_status_dan_petunjuk(monkeypatch):
    monkeypatch.setattr(menu_builder, "list_menus", lambda gid: [{"id": "m1"}])
    monkeypatch.setattr(modal_forms, "list_forms", lambda gid: [])

    html = wd.render_features_block(999)

    assert "Panel menu" in html and "/menu buat" in html
    assert "✅" in html and "⬜" in html
    assert "<table>" in html


def test_render_features_block_aman_tanpa_data(monkeypatch):
    for nama in ("list_menus", "list_forms"):
        pass
    monkeypatch.setattr(menu_builder, "list_menus", lambda gid: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(modal_forms, "list_forms", lambda gid: (_ for _ in ()).throw(RuntimeError("x")))

    data = wd.collect_features(999)
    panel = next(r for r in data["items"] if r["nama"] == "Panel menu")
    assert panel["aktif"] is False          # error dibaca sebagai "belum dipakai"
    assert "belum dipakai" in wd.render_features_block(999)


def test_halaman_dashboard_memuat_blok_fitur():
    html = wd.render_dashboard_html(
        status={"version": "1.0", "bot_name": "Bot"},
        usage={},
        levels={},
        fitur_block="<p>BLOK-FITUR-UJI</p>",
    )
    assert "BLOK-FITUR-UJI" in html
