"""Middleware HTTP dashboard: blokir brute-force & header keamanan.

Semua aturan ini dulu berada di dalam `start_dashboard()` yang panjangnya
>1.500 baris. Setelah dipisah, kebijakan keamanan bisa dibaca dan diuji tanpa
menyentuh isi halaman sama sekali.

Catatan desain: middleware sengaja **tidak** memegang sesi cookie. Pemasangan
cookie sesi dilakukan `HelperRespons.pasang_sesi` (dipanggil dari middleware
lewat `self.pasang_sesi`) supaya satu tempat menentukan bentuk header
`Set-Cookie`.
"""

from __future__ import annotations

import logging

from aiohttp import web

import dashboard_security

logger = logging.getLogger("gemini_bot.web_dashboard.middleware")


class MiddlewareKeamanan:
    """Blokir IP yang terlalu sering salah token + pasang header keamanan.

    `__middleware_version__ = 1` menandai ini middleware **gaya baru** aiohttp:
    dipanggil `middleware(request, handler)`. Tanpa penanda itu, aiohttp
    menganggapnya gaya lama dan memanggilnya `middleware(app, handler)` —
    akibatnya `request` berisi objek `Application` dan `ip_klien()` meledak.
    (Sebelum pemecahan, `@web.middleware` pada fungsi bersarang memberi efek
    yang sama; decorator itu tidak bisa dipasang pada `__call__` kelas.)
    """

    __middleware_version__ = 1

    def __init__(self, *, pembatas: dashboard_security.Pembatas, pasang_sesi) -> None:
        self.pembatas = pembatas
        self.pasang_sesi = pasang_sesi

    async def __call__(self, request, handler):
        """Alur: cek blokir → jalankan handler → lengkapi cookie & header."""
        kunci = dashboard_security.ip_klien(request)
        if request.path != "/healthz":
            sisa = self.pembatas.diblokir(kunci)
            if sisa > 0:
                logger.warning(
                    "Dashboard: %s diblokir %.0f detik lagi (terlalu banyak token salah).",
                    kunci,
                    sisa,
                )
                return web.Response(
                    text="429 Terlalu banyak percobaan. Coba lagi nanti.",
                    status=429,
                    headers={"Retry-After": str(int(sisa) + 1)},
                )

        respons = await handler(request)

        # Permintaan yang lolos lewat token (query/header/body) dan menghasilkan
        # respons apa pun diberi cookie sesi di sini — satu tempat untuk semua
        # handler, sehingga alamat tujuan tidak perlu membawa `?token=` lagi.
        if request.get("_dash_token_baru") and not request.get("_dash_sesi_terpasang"):
            respons = self.pasang_sesi(request, respons)

        html_page = "text/html" in str(respons.headers.get("Content-Type", ""))
        for nama, nilai in dashboard_security.header_keamanan(html_page=html_page).items():
            respons.headers.setdefault(nama, nilai)
        return respons
