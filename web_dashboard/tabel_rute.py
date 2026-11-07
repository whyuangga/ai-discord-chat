"""Tabel rute dashboard (path → handler) sebagai data, bukan 40 baris `add_get`.

Sebelumnya daftar rute ditulis langsung di badan `start_dashboard()` dan dicampur
dengan pengecekan token. Dengan tabel ini:

- rute yang sama sekali tidak terdaftar (mis. `/api/giveaway` hilang) langsung
  terlihat saat membaca berkas;
- tes bisa memeriksa tabel tanpa menyalakan server (lihat tests/test_dashboard_rute.py);
- penambahan rute baru cukup satu baris.

Urutan penting: rute statis (`/api/rank.png`) didaftarkan sebelum rute dinamis
(`/api/kartu/{jenis}`) agar tidak saling tertukar.
"""

from __future__ import annotations

from typing import Iterable

from aiohttp import web

from web_dashboard.halaman import HALAMAN, LEGACY_HALAMAN

# (method, path, nama method di kelas RuteDashboard/HalamanDashboard)
RUTE_API: tuple[tuple[str, str, str], ...] = (
    ("GET", "/healthz", "handle_health"),
    ("GET", "/api/status", "handle_status"),
    ("GET", "/api/pemakaian", "handle_usage"),
    ("GET", "/api/level", "handle_levels"),
    ("GET", "/api/kontrol", "handle_kontrol"),
    ("GET", "/api/fitur", "handle_features"),
    ("GET", "/api/setelan", "handle_setelan"),
    ("GET", "/api/tren", "handle_tren"),
    ("GET", "/api/ekspor", "handle_ekspor"),
    ("GET", "/api/rank.png", "handle_rank_png"),
    ("GET", "/api/kartu/{jenis}", "handle_kartu"),
    ("GET", "/api/unggahan/{nama}", "handle_berkas"),
    ("GET", "/transkrip", "handle_transkrip"),
    ("GET", "/api/transkrip", "handle_transkrip_berkas"),
    ("GET", "/keluar", "handle_logout"),
    ("POST", "/keluar", "handle_logout"),
    # Tulis (hanya POST — tidak ada PUT/DELETE/PATCH di dashboard)
    ("POST", "/api/aksi", "handle_aksi"),
    ("POST", "/api/kirim", "handle_kirim"),
    ("POST", "/api/konten", "handle_konten"),
    ("POST", "/api/unggah", "handle_unggah"),
    ("POST", "/api/uji", "handle_uji"),
    ("POST", "/api/bangun", "handle_bangun"),
    ("POST", "/api/ai", "handle_ai"),
    ("POST", "/api/panel", "handle_panel"),
    ("POST", "/api/tiket", "handle_tiket"),
    ("POST", "/api/transkrip", "handle_transkrip_berkas"),
    ("POST", "/api/keamanan", "handle_keamanan"),
    ("POST", "/api/moderasi", "handle_moderasi"),
    ("POST", "/api/lencana", "handle_lencana"),
    ("POST", "/api/giveaway", "handle_giveaway"),
    ("GET", "/api/panel", "handle_panel"),
    ("GET", "/api/tiket", "handle_tiket"),
    ("GET", "/api/giveaway", "handle_giveaway"),
)

# Halaman HTML: satu handler (`handle_index`) melayani semua slug, karena isi
# halaman dipilih dari `HALAMAN_SLUG` di dalam handler.
RUTE_HALAMAN: tuple[str, ...] = ("/",)


def slug_halaman() -> tuple[str, ...]:
    """Slug halaman modern + slug lama (bookmark) yang harus tetap hidup."""
    slug = [h["slug"] for h in HALAMAN if h["slug"]]
    return tuple(slug) + tuple(LEGACY_HALAMAN)


def pasang_rute(app: web.Application, rute, halaman) -> int:
    """Daftarkan semua rute; kembalikan jumlah rute yang terpasang.

    `rute` adalah instance `RuteDashboard`, `halaman` instance `HalamanDashboard`.
    """
    jumlah = 0
    for metode, path, nama in RUTE_API:
        handler = getattr(rute, nama, None) or getattr(halaman, nama, None)
        if handler is None:
            raise AttributeError(f"handler {nama} untuk {path} tidak ditemukan")
        app.router.add_route(metode, path, handler)
        jumlah += 1

    for path in RUTE_HALAMAN:
        app.router.add_get(path, halaman.handle_index)
        jumlah += 1
    for slug in slug_halaman():
        app.router.add_get(f"/{slug}", halaman.handle_index)
        jumlah += 1
    return jumlah


def daftar_path(rute_iter: Iterable[tuple[str, str, str]] = RUTE_API) -> set[str]:
    """Himpunan path untuk pemeriksaan cepat di tes."""
    return {path for _m, path, _n in rute_iter}
