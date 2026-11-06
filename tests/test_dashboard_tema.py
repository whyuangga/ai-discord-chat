"""Tema dashboard: latar #0D0D0F, teks #FFFFFF, font General Sans (Fontshare)."""

import re

import dashboard_tema
import dashboard_ui
import web_dashboard


def _halaman(**kwargs) -> str:
    dasar = dict(status={}, usage={}, levels={})
    dasar.update(kwargs)
    return web_dashboard.render_dashboard_html(**dasar)


def test_palet_dasar():
    assert dashboard_tema.LATAR == "#0D0D0F"
    assert dashboard_tema.TEKS == "#FFFFFF"
    assert dashboard_tema.FONT_STACK.startswith("'General Sans'")


def test_halaman_memakai_latar_dan_teks_baru():
    html = _halaman()
    assert f"--latar: {dashboard_tema.LATAR}" in html
    assert f"--teks: {dashboard_tema.TEKS}" in html
    assert "background: var(--latar)" in html
    # warna lama tidak boleh tertinggal
    for usang in ("#0f1117", "#e6e6f0", "#14161f", "#171a23"):
        assert usang not in html.lower()


def test_font_general_sans_dimuat_dari_fontshare():
    html = _halaman()
    assert "api.fontshare.com/v2/css" in html
    assert "general-sans@400,500,600,700" in html
    assert "cdn.fontshare.com" in html  # preconnect
    # font stack benar-benar dipakai body
    assert "font-family: 'General Sans'" in html


def test_halaman_hasil_dan_pratinjau_ikut_tema():
    halaman_hasil = dashboard_tema.CSS_HASIL
    assert dashboard_tema.LATAR in halaman_hasil
    assert "'General Sans'" in halaman_hasil

    pratinjau = dashboard_ui.render_pratinjau_html(
        pratinjau={"judul": "Halo", "isi": "Isi", "channel_label": "#umum"},
        token="tok",
        guild_id=1,
        fields={"token": "tok", "guild": "1"},
    )
    assert "general-sans@" in pratinjau
    assert dashboard_tema.LATAR in pratinjau


def test_grafik_memakai_warna_teks_tema():
    svg = dashboard_ui.render_tren_svg([{"label": "01", "total": 5, "cache_hits": 1}])
    assert "General Sans" in svg
    assert "#8b90a3" not in svg


def test_tidak_ada_font_system_ui_di_halaman_utama():
    html = _halaman()
    # semua font-family halaman utama harus General Sans / mono, bukan system-ui
    for deklarasi in re.findall(r"font-family:([^;}]+)", html):
        bersih = deklarasi.strip()
        assert (
            "General Sans" in bersih or "ui-monospace" in bersih or bersih == "inherit"
        ), bersih
