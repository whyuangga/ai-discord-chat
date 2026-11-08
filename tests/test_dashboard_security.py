"""Uji keamanan dashboard (P5): token, sesi cookie, header, & anti brute-force.

Latar belakang masalah yang ditutup di sini:

1. `is_authorized()` memakai `==` — perbandingan yang berhenti di karakter
   pertama berbeda, sehingga secara teori membocorkan panjang awalan token.
2. Token ikut di setiap `<a href>`, hidden input, dan `Location:` hasil
   redirect → tercatat di access log proxy & riwayat browser.
3. Tidak ada pembatas percobaan; token 6 karakter bisa di-brute-force.
4. Tidak ada header keamanan (CSP, X-Frame-Options, Referrer-Policy, …).
"""

from __future__ import annotations

import time

import pytest

import dashboard_security as ds


# ==============================================================================
# 1. PERBANDINGAN TOKEN
# ==============================================================================
def test_token_cocok_lewat_query_header_dan_bearer():
    rahasia = "a" * 40
    assert ds.verify_token(query_token=rahasia, expected=rahasia) is True
    assert ds.verify_token(header_token=rahasia, expected=rahasia) is True
    assert ds.verify_token(header_token=f"Bearer {rahasia}", expected=rahasia) is True
    assert ds.verify_token(header_token=f"bearer {rahasia}", expected=rahasia) is True
    assert ds.verify_token(header_token=f"  Bearer   {rahasia}  ", expected=rahasia) is True


def test_token_salah_atau_kosong_selalu_ditolak():
    rahasia = "a" * 40
    for salah in ("", " ", "a" * 39, "a" * 41, "b" * 40, rahasia[:-1] + "b"):
        assert ds.verify_token(query_token=salah, expected=rahasia) is False
    # Token yang diharapkan kosong → tidak ada yang sah
    assert ds.verify_token(query_token="apa saja", expected="") is False
    assert ds.verify_token(expected=rahasia) is False


def test_perbandingan_tidak_memakai_operator_sama_dengan(monkeypatch):
    """Regresi: implementasi harus lewat hmac.compare_digest, bukan `==`."""
    dipanggil = {"n": 0}
    asli = ds.hmac.compare_digest

    def _pantau(a, b):
        dipanggil["n"] += 1
        return asli(a, b)

    monkeypatch.setattr(ds.hmac, "compare_digest", _pantau)
    assert ds.verify_token(query_token="x" * 32, expected="x" * 32) is True
    assert dipanggil["n"] == 1


class _Req:
    """Request palsu minimal untuk `token_dari_request`."""

    def __init__(self, query=None, headers=None):
        self.query = query or {}
        self.headers = headers or {}


def test_token_diambil_dari_query_atau_header():
    assert ds.token_dari_request(_Req({"token": "abc"})) == ("abc", "")
    assert ds.token_dari_request(_Req(headers={"X-Dashboard-Token": "h"})) == ("", "h")
    assert ds.token_dari_request(_Req(headers={"Authorization": "Bearer z"})) == ("", "Bearer z")


# ==============================================================================
# 2. KEKUATAN TOKEN
# ==============================================================================
@pytest.mark.parametrize(
    "lemah",
    [
        "",                       # kosong
        "rahasia",                # pendek
        "rahasia-uji",            # pendek (kasus nyata di tes lama)
        "a" * 40,                 # satu karakter berulang
        "12345678901234567890123456789012",   # hanya angka
        "qwertyuiopasdfghjklzxcvbnm123456",
        "secretsecretsecretsecretsecret1234",
        "password123456789012345678901234",
    ],
)
def test_token_lemah_ditolak(lemah):
    ok, pesan = ds.kekuatan_token(lemah)
    assert ok is False and pesan


def test_token_acak_diterima():
    import secrets

    for _ in range(5):
        ok, pesan = ds.kekuatan_token(secrets.token_urlsafe(32))
        assert ok is True and "memenuhi" in pesan


def test_pesan_token_lemah_mengajarkan_cara_membuat():
    ok, pesan = ds.kekuatan_token("pendek")
    assert ok is False
    assert "secrets.token_urlsafe" in pesan and "minimum 32" in pesan


# ==============================================================================
# 3. SESI COOKIE
# ==============================================================================
def test_sesi_dibuat_dibaca_dan_dihapus():
    ds.bersihkan_sesi()
    sesi = ds.buat_sesi(user_agent="BrowserA", now=1000.0)
    assert len(sesi.nilai) >= 32

    # Dibaca dengan user agent yang sama
    assert ds.baca_sesi(sesi.nilai, user_agent="BrowserA", now=1001.0) is not None
    # User agent berbeda → dianggap dicuri
    assert ds.baca_sesi(sesi.nilai, user_agent="BrowserB", now=1002.0) is None
    # Nilai asli tidak disimpan di memori
    assert all(k != sesi.nilai for k in ds._sesi.isi)
    # Hapus
    assert ds.hapus_sesi(sesi.nilai) is True
    assert ds.hapus_sesi(sesi.nilai) is False
    assert ds.baca_sesi(sesi.nilai) is None


def test_sesi_kedaluwarsa_karena_umur_dan_karena_menganggur():
    ds.bersihkan_sesi()
    sesi = ds.buat_sesi(now=0.0)
    # Masih hidup selama dipakai lebih sering dari batas menganggur
    assert ds.baca_sesi(sesi.nilai, now=ds.IDLE_SESI_SEC - 1) is not None
    assert ds.baca_sesi(sesi.nilai, now=ds.IDLE_SESI_SEC * 2 - 2) is not None
    # Menganggur terlalu lama → mati
    assert ds.baca_sesi(
        sesi.nilai, now=ds.IDLE_SESI_SEC * 2 - 2 + ds.IDLE_SESI_SEC + 1
    ) is None
    assert ds.jumlah_sesi() == 0

    # Umur total tetap membatasi walau terus dipakai
    ds.bersihkan_sesi()
    sesi2 = ds.buat_sesi(now=0.0)
    detik = 0.0
    while detik < ds.UMUR_SESI_SEC - ds.IDLE_SESI_SEC:
        detik += ds.IDLE_SESI_SEC - 1
        assert ds.baca_sesi(sesi2.nilai, now=detik) is not None
    assert ds.baca_sesi(sesi2.nilai, now=ds.UMUR_SESI_SEC + 1) is None


def test_jumlah_sesi_dibatasi():
    ds.bersihkan_sesi()
    for i in range(ds.BATAS_SESI + 20):
        ds.buat_sesi(now=float(i))
    assert ds.jumlah_sesi() <= ds.BATAS_SESI


def test_aturan_cookie_httponly_dan_samesite_strict():
    biasa = ds.aturan_cookie(https=False)
    assert biasa["httponly"] is True and biasa["samesite"] == "Strict"
    assert biasa["secure"] is False          # HTTP polos tetap bisa login
    https = ds.aturan_cookie(https=True)
    assert https["secure"] is True


def test_https_dikenali_dari_header_proxy():
    class _R:
        def __init__(self, headers=None, secure=False):
            self.headers = headers or {}
            self.secure = secure

    assert ds.berasal_dari_https(_R({"X-Forwarded-Proto": "https"})) is True
    assert ds.berasal_dari_https(_R({"X-Forwarded-Proto": "https, http"})) is True
    assert ds.berasal_dari_https(_R({"X-Forwarded-Proto": "http"})) is False
    assert ds.berasal_dari_https(_R(secure=True)) is True
    assert ds.berasal_dari_https(_R()) is False


# ==============================================================================
# 4. PEMBATAS PERCOBAAN
# ==============================================================================
def test_pembatas_memblokir_setelah_batas_galat():
    p = ds.Pembatas(maks=3, jendela=60, blokir=30)
    assert p.catat_galat("ip", now=0) == 0
    assert p.catat_galat("ip", now=1) == 0
    assert p.catat_galat("ip", now=2) == 30          # batas tercapai
    assert p.diblokir("ip", now=5) == 27             # dihitung dari galat terakhir
    # Galat baru memperpanjang blokir, tidak memperpendeknya
    assert p.catat_galat("ip", now=10) == 30
    assert p.diblokir("ip", now=12) == 28
    assert p.diblokir("ip", now=100) == 0            # blokir selesai
    # IP lain tidak terpengaruh
    assert p.diblokir("ip-lain", now=5) == 0


def test_pembatas_mengulang_jendela_dan_reset_saat_sukses():
    p = ds.Pembatas(maks=2, jendela=10, blokir=100)
    assert p.catat_galat("ip", now=0) == 0
    # Lewat jendela → hitungan mulai dari nol
    assert p.catat_galat("ip", now=50) == 0
    assert p.catat_galat("ip", now=51) == 100
    p.catat_sukses("ip")
    assert p.diblokir("ip", now=60) == 0

    p2 = ds.Pembatas(maks=2, jendela=10, blokir=5)
    p2.catat_galat("x", now=0)
    p2.catat_galat("x", now=0)
    assert p2.diblokir("x", now=1) == 4
    assert p2.jumlah_tercatat() == 1
    for i in range(100):
        p2.catat_galat(f"ip-{i}", now=0)
    p2.pangkas(batas=10)
    assert p2.jumlah_tercatat() <= 10


def test_ip_klien_mengikuti_header_proxy():
    class _R:
        def __init__(self, headers=None, remote="10.0.0.1"):
            self.headers = headers or {}
            self.remote = remote

    assert ds.ip_klien(_R({"CF-Connecting-IP": "1.2.3.4"})) == "1.2.3.4"
    assert ds.ip_klien(_R({"X-Forwarded-For": "5.6.7.8, 9.9.9.9"})) == "5.6.7.8"
    assert ds.ip_klien(_R(remote="127.0.0.1")) == "127.0.0.1"


# ==============================================================================
# 5. HEADER KEAMANAN
# ==============================================================================
def test_header_keamanan_lengkap():
    h = ds.header_keamanan(html_page=True)
    assert h["X-Frame-Options"] == "DENY"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["Cache-Control"] == "no-store"
    csp = h["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    # Halaman non-HTML tidak perlu CSP tapi tetap no-store
    json_h = ds.header_keamanan(html_page=False)
    assert "Content-Security-Policy" not in json_h
    assert json_h["Cache-Control"] == "no-store"


def test_csp_mengizinkan_font_dan_gambar_yang_dipakai():
    csp = ds.CSP
    assert "https://cdn.fontshare.com" in csp       # font dashboard_tema
    assert "img-src" in csp and "data:" in csp       # kartu/PNG inline


# ==============================================================================
# 6. UTILITAS URL & LOG
# ==============================================================================
@pytest.mark.parametrize(
    "masuk, keluar",
    [
        ("/?token=rahasia", "/"),
        ("/?token=rahasia&guild=1", "/?guild=1"),
        ("/inti?guild=1&token=rahasia", "/inti?guild=1"),
        ("/inti?token=rahasia&guild=1#p-inti", "/inti?guild=1#p-inti"),
        ("/ai", "/ai"),
        ("/?guild=1", "/?guild=1"),
    ],
)
def test_token_dibuang_dari_url(masuk, keluar):
    assert ds.bersihkan_url(masuk) == keluar


def test_token_disamarkan_di_pesan_galat():
    assert "rahasia123" not in ds.sembunyikan_token("token=rahasia123 gagal")
    assert ds.sembunyikan_token("token=rahasia123") == "token=***"


def test_escape_html_untuk_atribut():
    assert ds.escape('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"
    assert ds.escape("") == ""


def test_pastikan_env_token_menghasilkan_nilai_acak():
    nilai = ds.pastikan_env_token()
    assert isinstance(nilai, str) and nilai


@pytest.mark.parametrize("fungsi", ["buat_sesi", "baca_sesi", "hapus_sesi"])
def test_sesi_tidak_pernah_membocorkan_nilai_ke_repr(fungsi):
    """Nilai sesi tidak boleh tercetak lewat repr objek Sesi di log."""
    sesi = ds.buat_sesi(now=time.time())
    assert sesi.nilai not in repr(sesi)
