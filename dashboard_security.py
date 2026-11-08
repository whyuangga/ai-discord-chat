"""Keamanan dashboard web: token, sesi cookie, header, & pembatas percobaan.

Modul ini **tidak** menyentuh aiohttp maupun `web_dashboard` (selain tipe yang
sengaja dibuat generik), sehingga seluruh aturannya bisa diuji tanpa server.
Ini memisahkan "kebijakan keamanan" dari "handler rute" — sebelumnya keduanya
menumpuk di dalam `start_dashboard()` yang panjangnya >1.300 baris.

Tiga lapis yang disediakan:

1. **Verifikasi token** (`verify_token`) — perbandingan waktu-konstan lewat
   `hmac.compare_digest`, bukan `==` seperti sebelumnya. `==` pada string
   berhenti di karakter pertama yang beda, yang secara teori membocorkan
   informasi lewat pengukuran waktu.
2. **Cookie sesi** (`Sesi`, `buat_sesi`, `baca_sesi`) — token ditukar dengan
   token acak berumur pendek yang disimpan di cookie `HttpOnly`/`SameSite=Strict`.
   Dengan begitu token asli tidak lagi ikut di setiap `<a href>`, hidden input,
   maupun `Location:` hasil redirect (yang semuanya tercatat di access log proxy
   dan riwayat browser).
3. **Pembatas percobaan** (`Pembatas`) — penghitung galat per IP dengan jendela
   waktu, mencegah brute-force token 32+ karakter dari satu sumber.

Aturan penting: `?token=...` **tetap diterima** (API & tautan yang sudah
tersebar). Setelah satu permintaan `GET` berhasil, cookie sesi dipasang dan
token di URL dibuang lewat redirect 303 supaya tidak tertinggal di riwayat.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import re
import secrets
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 1. Verifikasi token
# ---------------------------------------------------------------------------
HEADER_TOKEN = "X-Dashboard-Token"
HEADER_AUTH = "Authorization"
PREFIX_BEARER = "bearer "

# Panjang minimum token. 32 karakter acak (±192 bit) membuat brute-force lewat
# HTTP praktis mustahil; nilai lebih pendek ditolak saat startup dengan pesan
# yang menjelaskan cara membuatnya.
MIN_TOKEN_LENGTH = 32
CONTOH_TOKEN = "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""


def normalisasi_token(nilai: str) -> str:
    """Buang spasi & awalan `Bearer ` (tidak peka huruf besar/kecil)."""
    teks = str(nilai or "").strip()
    if teks[: len(PREFIX_BEARER)].lower() == PREFIX_BEARER:
        teks = teks[len(PREFIX_BEARER):].strip()
    return teks


def verify_token(
    *,
    query_token: str = "",
    header_token: str = "",
    expected: str = "",
) -> bool:
    """True bila salah satu token yang diberikan cocok dengan `expected`.

    Perbandingan memakai `hmac.compare_digest` dan selalu membandingkan
    panjang yang sama (HMAC-SHA256 dari nilai) supaya waktu eksekusi tidak
    bergantung pada isi. Token kosong tidak pernah dianggap sah.
    """
    want = str(expected or "").strip()
    if not want:
        return False
    given = normalisasi_token(query_token or header_token)
    if not given:
        return False
    a = hashlib.sha256(given.encode("utf-8", "surrogatepass")).digest()
    b = hashlib.sha256(want.encode("utf-8", "surrogatepass")).digest()
    return hmac.compare_digest(a, b)


def token_dari_request(request) -> tuple[str, str]:
    """Ambil (token_query, token_header) dari objek request aiohttp."""
    query = str(request.query.get("token") or "")
    header = str(request.headers.get(HEADER_TOKEN) or "").strip()
    if not header:
        header = str(request.headers.get(HEADER_AUTH) or "").strip()
    return query, header


def kekuatan_token(token: str) -> tuple[bool, str]:
    """Periksa kekuatan token dashboard sebelum server dinyalakan.

    Mengembalikan `(ok, pesan)`. Pesan dipakai sebagai peringatan di log —
    dashboard tetap menyala supaya pengguna lama tidak terkunci, tetapi
    masalahnya terlihat jelas.
    """
    teks = str(token or "").strip()
    if len(teks) < MIN_TOKEN_LENGTH:
        return (
            False,
            f"DASHBOARD_TOKEN terlalu pendek ({len(teks)} karakter, minimum "
            f"{MIN_TOKEN_LENGTH}). Buat yang acak: {CONTOH_TOKEN}",
        )
    if len(set(teks)) < 8:
        return False, "DASHBOARD_TOKEN terlalu monoton (karakternya berulang)."
    for pola, alasan in (
        (r"^(.)\1+$", "satu karakter berulang"),
        (r"(?i)^(rahasia|secret|password|token|admin|test|uji)\d*$", "kata yang mudah ditebak"),
        (r"^\d+$", "hanya angka"),
        (r"(?i)^(qwerty|asdf|1234)", "pola papan ketik"),
        (r"(?i)(rahasia|secret|password|sandi|admin|token){2,}", "kata sandi berulang"),
    ):
        if re.search(pola, teks):
            return False, f"DASHBOARD_TOKEN mudah ditebak ({alasan})."
    return True, "Token dashboard memenuhi syarat minimum."


# ---------------------------------------------------------------------------
# 2. Sesi cookie
# ---------------------------------------------------------------------------
NAMA_COOKIE_SESI = "dash_sesi"
UMUR_SESI_SEC = 60 * 60 * 12       # 12 jam — cukup untuk satu shift admin
IDLE_SESI_SEC = 60 * 30            # 30 menit tanpa aktivitas → sesi dimatikan
BATAS_SESI = 64                    # jumlah sesi hidup maksimum (pengaman RAM)


@dataclass
class Sesi:
    """Satu sesi login dashboard hasil penukaran token.

    `repr` sengaja menyembunyikan nilai cookie: objek ini kerap muncul di pesan
    log/traceback, dan nilai itu setara kunci masuk dashboard.
    """

    nilai: str
    dibuat: float
    terakhir: float
    percobaan: int = 0
    user_agent: str = ""

    def __repr__(self) -> str:  # pragma: no cover - hanya untuk log
        sisa = max(0, int(UMUR_SESI_SEC - (time.time() - self.terakhir)))
        return f"Sesi(<disembunyikan>, sisa={sisa}s, percobaan={self.percobaan})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass
class _Gudang:
    """Penyimpanan sesi di memori (proses tunggal, tanpa DB)."""

    isi: dict[str, Sesi] = field(default_factory=dict)

    def buang_kedaluwarsa(self, sekarang: float, umur: int = UMUR_SESI_SEC) -> int:
        """Buang sesi yang lewat umur total **atau** terlalu lama menganggur."""
        mati = [
            k
            for k, s in self.isi.items()
            if sekarang - s.dibuat > umur or sekarang - s.terakhir > IDLE_SESI_SEC
        ]
        for kunci in mati:
            self.isi.pop(kunci, None)
        return len(mati)

    def pangkas(self, batas: int = BATAS_SESI) -> None:
        """Sisakan `batas` sesi dengan aktivitas terbaru."""
        if len(self.isi) <= batas:
            return
        urut = sorted(self.isi.values(), key=lambda s: s.terakhir, reverse=True)
        simpan = {s.nilai for s in urut[:batas]}
        for kunci in [k for k in self.isi if k not in simpan]:
            self.isi.pop(kunci, None)


_sesi = _Gudang()


def _sid(nilai: str) -> str:
    """Kunci penyimpanan: hash dari nilai cookie (nilai asli tak disimpan)."""
    return hashlib.sha256(str(nilai or "").encode("utf-8", "surrogatepass")).hexdigest()


def buat_sesi(*, user_agent: str = "", now: float | None = None) -> Sesi:
    """Buat sesi baru dengan token acak 32 byte."""
    detik = time.time() if now is None else float(now)
    _sesi.buang_kedaluwarsa(detik)
    sesi = Sesi(
        nilai=secrets.token_urlsafe(32),
        dibuat=detik,
        terakhir=detik,
        user_agent=str(user_agent or "")[:200],
    )
    _sesi.isi[_sid(sesi.nilai)] = sesi
    _sesi.pangkas()
    return sesi


def baca_sesi(nilai: str, *, user_agent: str = "", now: float | None = None) -> Sesi | None:
    """Validasi cookie sesi; sesi kedaluwarsa dihapus dan dianggap tidak ada.

    Bila `user_agent` diberikan dan berbeda dari saat sesi dibuat, sesi
    dianggap tidak sah — pencurian cookie lewat jalur lain jadi tidak berguna.
    """
    detik = time.time() if now is None else float(now)
    sesi = _sesi.isi.get(_sid(nilai))
    if sesi is None:
        return None
    if detik - sesi.terakhir > IDLE_SESI_SEC or detik - sesi.dibuat > UMUR_SESI_SEC:
        _sesi.isi.pop(_sid(nilai), None)
        return None
    if user_agent and sesi.user_agent and sesi.user_agent != str(user_agent)[:200]:
        return None
    sesi.terakhir = detik
    return sesi


def hapus_sesi(nilai: str) -> bool:
    """Hapus satu sesi (logout). True bila memang ada."""
    return _sesi.isi.pop(_sid(nilai), None) is not None


def jumlah_sesi() -> int:
    _sesi.buang_kedaluwarsa(time.time())
    return len(_sesi.isi)


def bersihkan_sesi() -> None:
    """Kosongkan semua sesi — dipakai `stop_dashboard()` & tes."""
    _sesi.isi.clear()


def aturan_cookie(https: bool = False) -> dict:
    """Atribut cookie sesi. `Secure` hanya saat benar-benar HTTPS.

    Dashboard sering dibuka lewat IP:port polos (Wispbyte/VPS), dan browser
    menolak mengirim cookie `Secure` di atas HTTP — memasangnya selalu akan
    membuat login mustahil. Jadi HTTPS dideteksi dari `X-Forwarded-Proto`.
    """
    return {
        "httponly": True,
        "samesite": "Strict",
        "secure": bool(https),
        "path": "/",
        "max_age": UMUR_SESI_SEC,
    }


# ---------------------------------------------------------------------------
# 3. Pembatas percobaan (brute-force)
# ---------------------------------------------------------------------------
GALAT_MAKS = 20                     # salah token per jendela sebelum diblokir
JENDELA_GALAT_SEC = 10 * 60         # 10 menit
BLOKIR_SEC = 15 * 60                # 15 menit setelah batas terlampaui


@dataclass
class _Catatan:
    galat: int = 0
    mulai: float = 0.0
    diblokir_sampai: float = 0.0


class Pembatas:
    """Penghitung galat token per kunci (biasanya alamat IP)."""

    def __init__(
        self,
        maks: int = GALAT_MAKS,
        jendela: float = JENDELA_GALAT_SEC,
        blokir: float = BLOKIR_SEC,
    ) -> None:
        self.maks = max(1, int(maks))
        self.jendela = max(1.0, float(jendela))
        self.blokir = max(1.0, float(blokir))
        self._isi: dict[str, _Catatan] = {}

    def _catatan(self, kunci: str, sekarang: float) -> _Catatan:
        cat = self._isi.get(kunci)
        if cat is None:
            cat = _Catatan(mulai=sekarang)
            self._isi[kunci] = cat
        elif sekarang - cat.mulai > self.jendela and not cat.diblokir_sampai:
            # jendela baru → hitungan diulang
            cat.galat = 0
            cat.mulai = sekarang
        return cat

    def diblokir(self, kunci: str, now: float | None = None) -> float:
        """Sisa detik blokir (0 bila tidak diblokir)."""
        detik = time.time() if now is None else float(now)
        cat = self._isi.get(kunci)
        if cat is None or not cat.diblokir_sampai:
            return 0.0
        sisa = cat.diblokir_sampai - detik
        if sisa <= 0:
            self._isi.pop(kunci, None)
            return 0.0
        return sisa

    def catat_galat(self, kunci: str, now: float | None = None) -> float:
        """Catat satu galat; kembalikan sisa detik blokir (0 bila belum)."""
        detik = time.time() if now is None else float(now)
        cat = self._catatan(kunci, detik)
        cat.galat += 1
        if cat.galat >= self.maks:
            # Selalu diperpanjang dari galat terakhir, bukan dari galat minimum —
            # percobaan yang terus berlanjut tidak boleh memperpendek blokir.
            cat.diblokir_sampai = max(cat.diblokir_sampai, detik + self.blokir)
            return cat.diblokir_sampai - detik
        return 0.0

    def catat_sukses(self, kunci: str) -> None:
        """Login berhasil → hitungan galat kunci itu dihapus."""
        self._isi.pop(kunci, None)

    def reset(self) -> None:
        self._isi.clear()

    def jumlah_tercatat(self) -> int:
        return len(self._isi)

    def pangkas(self, batas: int = 2048) -> None:
        """Buang catatan lama supaya memori tidak tumbuh tanpa batas."""
        if len(self._isi) <= batas:
            return
        urut = sorted(self._isi.items(), key=lambda kv: kv[1].mulai)
        for kunci, _cat in urut[: len(self._isi) - batas]:
            self._isi.pop(kunci, None)


# ---------------------------------------------------------------------------
# 4. Header keamanan respons
# ---------------------------------------------------------------------------
# Halaman dashboard memakai CSS inline & style= atribut, memuat font dari
# Fontshare, dan memasang `meta refresh` (bukan script). CSP di bawah mengizinkan
# tepat itu saja.
CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline' https://api.fontshare.com https://cdn.fontshare.com; "
    "font-src https://cdn.fontshare.com data:; "
    "img-src 'self' data: https:; "
    "form-action 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)


def header_keamanan(*, html_page: bool = True) -> dict[str, str]:
    """Header yang dipasang pada setiap respons dashboard."""
    hasil = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Cache-Control": "no-store",
    }
    if html_page:
        hasil["Content-Security-Policy"] = CSP
    return hasil


# ---------------------------------------------------------------------------
# 5. Utilitas untuk halaman
# ---------------------------------------------------------------------------
URL_TOKEN = re.compile(r"([?&])token=[^&]*&?")


def bersihkan_url(url: str) -> str:
    """Buang parameter `token` dari sebuah URL (sisakan URL yang tetap valid)."""
    teks = str(url or "")
    hasil = URL_TOKEN.sub(r"\1", teks)
    hasil = hasil.replace("?&", "?").replace("&&", "&")
    if hasil.endswith(("?", "&")):
        hasil = hasil[:-1].rstrip("&")
    if hasil.endswith("#"):
        hasil = hasil[:-1]
    return hasil


def escape(nilai: str) -> str:
    """Escape standar untuk atribut & teks HTML."""
    return html.escape(str(nilai or ""), quote=True)


def sembunyikan_token(teks: str) -> str:
    """Ganti kemunculan apa pun yang tampak seperti token di log/pesan galat."""
    return re.sub(r"(?i)(token[=:\s]+)([A-Za-z0-9_\-]{8,})", r"\1***", str(teks or ""))


def berasal_dari_https(request) -> bool:
    """Deteksi HTTPS di balik proxy (Wispbyte/Vercel/Cloudflare)."""
    proto = str(request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    return bool(getattr(request, "secure", False))


def ip_klien(request) -> str:
    """Alamat IP klien untuk pembatas percobaan (ikut header proxy bila ada)."""
    for header in ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"):
        nilai = str(request.headers.get(header) or "").strip()
        if nilai:
            return nilai.split(",")[0].strip()[:64]
    peername = getattr(request, "remote", "") or ""
    return str(peername)[:64] or "lokal"


def pastikan_env_token() -> str:
    """Bantu operator: token acak siap tempel ke `.env`."""
    return os.environ.get("DASHBOARD_TOKEN") or secrets.token_urlsafe(32)
