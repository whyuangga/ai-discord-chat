"""Helper bersama semua handler dashboard (auth, payload, redirect, sesi).

Dipisah dari `middleware.py` agar aturan keamanan dan tata letak respons
(form/JSON/redirect) tidak saling menumpuk. Semua helper di sini **murni**
(atau hanya menyentuh request), jadi bisa diuji tanpa menyalakan server.
"""

from __future__ import annotations

import html
import logging
from urllib.parse import urlencode

from aiohttp import web

import dashboard_security
import dashboard_tema
import dashboard_unggah
from web_dashboard.halaman import HALAMAN_SLUG, LEGACY_HALAMAN, _teks_pesan, halaman_dari_anchor

logger = logging.getLogger("gemini_bot.web_dashboard.bersama")


class HelperRespons:
    """Pembungkus request -> payload yang aman + pembuat respons form/JSON."""

    def __init__(self, bot, cfg: dict) -> None:
        self.bot = bot
        self.cfg = cfg

    # -- autentikasi ---------------------------------------------------------
    def _sesi_aktif(self, request) -> bool:
        """Cookie sesi (HttpOnly) yang masih hidup dan cocok dengan browser ini."""
        cookie = str(request.cookies.get(dashboard_security.NAMA_COOKIE_SESI) or "")
        if not cookie:
            return False
        sesi = dashboard_security.baca_sesi(
            cookie,
            user_agent=str(request.headers.get("User-Agent") or ""),
        )
        return sesi is not None

    def _catat_galat(self, kunci: str) -> None:
        from web_dashboard import pembatas

        sisa = pembatas.catat_galat(kunci)
        pembatas.pangkas()
        if sisa:
            logger.warning(
                "Dashboard: %s melewati batas percobaan token → diblokir %.0f detik.",
                kunci,
                sisa,
            )

    def authorized(self, request) -> bool:
        """Token (query/header) **atau** cookie sesi yang sah.

        Token yang dikirim di query string langsung ditukar menjadi cookie sesi
        oleh `handle_index`, lalu dibuang dari URL, sehingga tautan antar-halaman
        tidak lagi membawa rahasia.
        """
        from web_dashboard import is_authorized, pembatas

        kunci = dashboard_security.ip_klien(request)
        query_token, header_token = dashboard_security.token_dari_request(request)
        if query_token or header_token:
            if is_authorized(
                query_token=query_token,
                header_token=header_token,
                expected=self.cfg["token"],
            ):
                pembatas.catat_sukses(kunci)
                request["_dash_token_baru"] = True
                return True
            self._catat_galat(kunci)
            return False
        return self._sesi_aktif(request)

    async def payload(self, request) -> dict:
        """Baca body JSON/form/multipart. Gagal baca → `{"__galat__": pesan}`."""
        try:
            if str(request.content_type or "").startswith("application/json"):
                return dict(await request.json())
            data = await request.post()
            hasil: dict = {}
            for kunci in data:
                nilai = data.getall(kunci, [])
                berkas = [v for v in nilai if hasattr(v, "file")]
                if berkas:
                    hasil[kunci] = nilai[0]
                elif len(nilai) > 1:
                    # checkbox multi (mis. pilih banyak channel) → "1,2,3"
                    hasil[kunci] = ",".join(str(v).strip() for v in nilai if str(v).strip())
                else:
                    hasil[kunci] = nilai[0] if nilai else ""
            return hasil
        except Exception as exc:
            if "TooLarge" in type(exc).__name__ or "too large" in str(exc).lower():
                return {
                    "__galat__": f"Berkas terlalu besar — maksimal {dashboard_unggah.batas_mb()} MB."
                }
            return {}

    def galat_payload(self, payload: dict):
        """Balasan untuk body yang gagal dibaca (mis. unggahan kebesaran)."""
        pesan = str((payload or {}).get("__galat__") or "")
        if not pesan:
            return None
        logger.warning("Payload dashboard ditolak: %s", pesan)
        return self.halaman_hasil(False, pesan)

    def izin(self, request, payload: dict) -> bool:
        """Token boleh lewat query/header (API) atau field tersembunyi (form HTML)."""
        from web_dashboard import is_authorized, pembatas

        if self.authorized(request):
            return True
        token_body = str((payload or {}).get("token") or "")
        if is_authorized(query_token=token_body, expected=self.cfg["token"]):
            pembatas.catat_sukses(dashboard_security.ip_klien(request))
            request["_dash_token_baru"] = True
            return True
        if token_body:
            self._catat_galat(dashboard_security.ip_klien(request))
        return False

    def halaman_hasil(self, ok: bool, pesan: str, anchor: str = ""):
        """Halaman kecil untuk submit yang **gagal**: pesan jelas + tautan kembali.

        Submit yang berhasil tidak memakai halaman ini lagi — lihat `_kembali()`
        supaya pengguna langsung berada di panel yang sama dan melihat nilai baru.
        """
        slug = halaman_dari_anchor(anchor)
        dasar = f"/{slug}" if slug else "/"
        tujuan = dasar
        if anchor:
            tujuan += f"#{html.escape(anchor, quote=True)}"
        page = (
            "<!doctype html><html lang=id><head><meta charset=utf-8>"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Dashboard — hasil</title>"
            f"{dashboard_tema.FONT_LINK}"
            f"<style>{dashboard_tema.CSS_HASIL}</style></head><body>"
            f"<h1>{'✅' if ok else '⚠️'}</h1>"
            f'<p style="font-size:16px">{_teks_pesan(pesan)}</p>'
            f'<p><a href="{tujuan}">← Kembali ke dashboard</a></p>'
            "</body></html>"
        )
        return web.Response(text=page, content_type="text/html", charset="utf-8",
                            status=200 if ok else 400)

    def anchor_form(self, request, payload: dict | None = None) -> str:
        """Anchor panel yang dikirim form (`__anchor`) — menentukan halaman balik."""
        nilai = str((payload or {}).get("__anchor") or request.query.get("_anchor") or "").strip()
        return nilai if halaman_dari_anchor(nilai) else ""

    def kembali(self, gid: int, pesan: str, anchor: str, ok: bool = True, *, request=None):
        """303 kembali ke panel yang sama + kotak pesan (POST → redirect → GET).

        Token **tidak** disertakan: sesi sudah tersimpan di cookie HttpOnly, jadi
        alamat hasil redirect tidak bisa dipakai ulang tanpa cookie tersebut.
        """
        kueri = urlencode(
            {
                "guild": int(gid or 0),
                "pesan": str(pesan or "")[:500],
                "ok": "1" if ok else "0",
            }
        )
        pilih =  (self.anchor_form(request) if request is not None else "") or str(anchor or "")
        slug = halaman_dari_anchor(pilih)
        tujuan = f"/{slug}?{kueri}" if slug else f"/?{kueri}"
        if pilih:
            tujuan += f"#{pilih}"
        # Parameter bookmark lama (`?halaman=setelan`) diteruskan agar halaman
        # tujuan akhirnya tetap tercapai setelah redirect ini.
        if request is not None and str(request.query.get("halaman") or "").strip():
            tujuan += f"&halaman={request.query.get('halaman')}"
        return web.Response(status=303, headers={"Location": tujuan})

    def jawab(self, gid: int, ok: bool, pesan: str, anchor: str, request):
        """JSON untuk otomasi; form HTML selalu kembali ke panelnya (✅ atau ⚠️).

        Gagal pun tetap redirect: pengguna mendarat di halaman fiturnya dengan
        kotak pesan yang jelas, bukan halaman buntu tanpa jalan pulang.
        """
        if str(request.content_type or "").startswith("application/json"):
            return web.json_response(
                {"ok": ok, "message": pesan, "guild": gid}, status=200 if ok else 400
            )
        return self.kembali(gid, pesan, anchor, ok=ok, request=request)

    def url_kembali(self, request) -> str:
        """URL boleh dibuka tanpa `?token=`, dengan anchor panel tetap utuh.

        Contoh: `/?token=X&guild=1234` → `/?guild=1234`
                `/inti?token=X&guild=1234#p-inti` → `/inti?guild=1234#p-inti`

        Dua hal yang ikut dipertahankan supaya UX tidak "melompat":
        - anchor panel (`#p-inti`) — pengguna kembali ke panel yang sedang dibuka;
        - bookmark lama (`?halaman=setelan`, `/uji`) — diteruskan apa adanya agar
          redirect halaman tujuan terjadi setelah sesi terpasang.
        """
        from web_dashboard import halaman_dari_path, url_halaman

        pinta = str(request.query.get("halaman") or "").strip()
        lama = str(request.path or "").strip("/")
        # Bookmark lama langsung diarahkan ke tempat akhirnya, sekaligus memasang
        # sesi — jadi pengguna tidak melewati dua kali redirect.
        tujuan_lama = ""
        if pinta in LEGACY_HALAMAN:
            tujuan_lama = LEGACY_HALAMAN[pinta]
        elif lama in LEGACY_HALAMAN and not pinta:
            tujuan_lama = LEGACY_HALAMAN[lama]
        elif pinta and pinta in HALAMAN_SLUG and lama != pinta and not (
            lama == HALAMAN_SLUG[pinta]["slug"] or halaman_dari_path("/" + lama) == pinta
        ):
            tujuan_lama = pinta
        if tujuan_lama:
            return url_halaman(tujuan_lama, "", int(request.query.get("guild") or 0))

        slug = halaman_dari_path(request.path)
        dasar = f"/{slug}" if slug else "/"
        lewat = {"token", "pesan", "ok", "guild"}
        kueri = urlencode({k: v for k, v in request.query.items() if k not in lewat})
        tujuan = f"{dasar}?{kueri}" if kueri else dasar
        # `guild` selalu diteruskan supaya server yang dipilih tidak berubah.
        gid = int(request.query.get("guild") or 0)
        if gid:
            tujuan += ("&" if "?" in tujuan else "?") + f"guild={gid}"
        return tujuan + str(request.query.get("_anchor") or "")

    def url_kembali_dari(self, request, anchor: str = "") -> str:
        """Sama seperti `_url_kembali`, tetapi anchor berasal dari field form."""
        dasar = self.url_kembali(request)
        bersih = dasar.split("#", 1)[0]
        if anchor:
            return f"{bersih}#{anchor}"
        return dasar

    def pasang_sesi(self, request, respons):
        """Buat sesi baru + pasang cookie HttpOnly; cookie lama ditimpa.

        Cookie lain pada respons yang sama (mis. `dash_auto` untuk interval
        auto-refresh) ikut dipertahankan — `set_cookie` pada respons yang sama
        tidak menghapus cookie yang sudah dipasang handler.
        """
        lama = str(request.cookies.get(dashboard_security.NAMA_COOKIE_SESI) or "")
        if lama:
            dashboard_security.hapus_sesi(lama)
        sesi = dashboard_security.buat_sesi(
            user_agent=str(request.headers.get("User-Agent") or "")
        )
        aturan = dashboard_security.aturan_cookie(
            https=dashboard_security.berasal_dari_https(request)
        )
        # Tulis manual agar Set-Cookie yang sudah ada (dash_auto) tidak tertimpa:
        # `Response.set_cookie()` mengganti header, bukan menambah.
        potongan = [
            f"{dashboard_security.NAMA_COOKIE_SESI}={sesi.nilai}",
            f"Max-Age={int(aturan['max_age'])}",
            f"Path={aturan['path']}",
            "SameSite=Strict",
            "HttpOnly",
        ]
        if aturan.get("secure"):
            potongan.append("Secure")
        respons.headers.add("Set-Cookie", "; ".join(potongan))
        request["_dash_sesi_terpasang"] = True
        return respons
