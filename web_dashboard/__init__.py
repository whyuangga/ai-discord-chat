"""Inti dashboard: konfigurasi, token, pengumpulan data, dan siklus server aiohttp.

Dulu modul ini satu berkas 3.146 baris dengan `start_dashboard()` setinggi 1.571
baris. Sekarang pembagiannya:

===============  ==============================================================
`halaman`        konstanta halaman/anchor/auto-refresh, URL, menu (murni)
`tampilan`       template HTML + panel per fitur (murni)
`kontrol`        blok kontrol on/off (murni)
`bersama`        `HelperRespons`: payload, izin, redirect, sesi
`middleware`     `MiddlewareKeamanan`: anti brute-force + header keamanan
`rute`           `RuteDashboard` + `HalamanDashboard`: semua handler HTTP
`tabel_rute`     daftar rute sebagai data (bukan 40 baris `add_get`)
===============  ==============================================================

Berkas ini hanya memuat hal yang memang "inti": konfigurasi, verifikasi token,
pengumpulan data untuk API, dan menyalakan/mematikan server.

Catatan penting: `web_dashboard` adalah **paket**, jadi `web_dashboard.py` tidak
boleh ada lagi — Python memuat paket lebih dulu dan berkas modul itu akan
diabaikan diam-diam.
"""

from __future__ import annotations

import html
import logging
import os
import time

import dashboard_admin
import dashboard_security
import dashboard_unggah
import insights
from config import (
    AI_DAILY_CAP_PER_GUILD,
    AI_DAILY_CAP_PER_USER,
    BOT_VERSION,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_REFRESH_SEC,
    DASHBOARD_TOKEN,
)

logger = logging.getLogger("gemini_bot.web_dashboard")

_runner = None          # aiohttp.web.AppRunner
_site = None            # aiohttp.web.TCPSite
pembatas = dashboard_security.Pembatas()   # dipakai helper + middleware


def dashboard_config() -> dict:
    """Konfigurasi efektif dashboard (port dari env panel bila `DASHBOARD_PORT` kosong)."""
    port = int(DASHBOARD_PORT or 0)
    if port <= 0:
        for env_name in ("SERVER_PORT", "PORT"):
            raw = str(os.getenv(env_name) or "").strip()
            if raw.isdigit():
                port = int(raw)
                break
    token = str(DASHBOARD_TOKEN or "").strip()
    return {
        "enabled": bool(port > 0 and token),
        "host": str(DASHBOARD_HOST or "0.0.0.0"),
        "port": port,
        "token": token,
        "refresh": max(0, int(DASHBOARD_REFRESH_SEC if DASHBOARD_REFRESH_SEC is not None else 30)),
        "reason": (
            "aktif"
            if (port > 0 and token)
            else ("DASHBOARD_TOKEN belum diisi" if port > 0 else "port dashboard tidak ditemukan")
        ),
    }


# Cookie kecil untuk menghidupkan/menjeda auto-refresh tanpa menyentuh `.env`


def is_authorized(*, query_token: str = "", header_token: str = "", expected: str = "") -> bool:
    """Cek token akses dashboard (query, `X-Dashboard-Token`, atau `Bearer`).

    Perbandingan memakai `hmac.compare_digest` (lihat `dashboard_security`),
    bukan `==`, supaya waktu eksekusi tidak bergantung pada isi token.
    """
    return dashboard_security.verify_token(
        query_token=query_token,
        header_token=header_token,
        expected=expected,
    )


# ==============================================================================
# PENGUMPULAN DATA (tanpa memanggil AI)
# ==============================================================================
def collect_status(bot) -> dict:
    """Ringkasan status bot untuk dashboard & `/api/status`."""
    from cogs.helpers import get_memory_usage_mb

    started_at = float(getattr(bot, "started_at", time.time()) or time.time())
    uptime = max(0, int(time.time() - started_at))
    hours, rem = divmod(uptime, 3600)
    minutes, seconds = divmod(rem, 60)
    latency = getattr(bot, "latency", 0.0)
    try:
        ping_ms = round(float(latency) * 1000)
    except (TypeError, ValueError):
        ping_ms = 0
    guilds = len(getattr(bot, "guilds", []) or [])
    users = 0
    for guild in getattr(bot, "guilds", []) or []:
        users += int(getattr(guild, "member_count", 0) or 0)
    return {
        "version": BOT_VERSION,
        "bot_name": str(getattr(getattr(bot, "user", None), "name", "") or "-"),
        "uptime": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        "uptime_sec": uptime,
        "ram_mb": float(get_memory_usage_mb()),
        "ping_ms": ping_ms,
        "guilds": guilds,
        "members": users,
        "ai_ready": bool(_gemini_ready()),
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _gemini_ready() -> bool:
    try:
        import ai_handler

        return bool(ai_handler.is_gemini_key_configured())
    except Exception:  # pragma: no cover - jaring aman
        return False


def collect_usage(guild_id: int = 0) -> dict:
    """Pemakaian AI hari ini (operasi, token, cache hit, kuota server, & penghematan)."""
    bucket = insights.ai_usage.get(insights.today_key()) or {}
    tokens_in, tokens_out = insights.token_totals()

    def _label_kinds(counter: dict, limit: int = 8) -> list[list]:
        """Jenis operasi dengan label ramah (mis. `🤖 Auto-Chat komunitas`)."""
        items = sorted((counter or {}).items(), key=lambda kv: int(kv[1]), reverse=True)
        labels = getattr(insights, "AI_KIND_LABELS", {}) or {}
        return [[str(labels.get(k, k)), int(v)] for k, v in items[:limit]]

    def _label_ids(counter: dict, prefix: str, limit: int = 5) -> list[list]:
        items = sorted((counter or {}).items(), key=lambda kv: int(kv[1]), reverse=True)
        return [[f"{prefix}{k}", int(v)] for k, v in items[:limit]]

    payload = {
        "date": insights.today_key(),
        "total": int(bucket.get("total") or 0),
        "cache_hits": int(bucket.get("cache_hits") or 0),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "kinds": _label_kinds(bucket.get("kinds") or {}, 8),
        "users": _label_ids(bucket.get("users") or {}, "Member ", 5),
        "channels": _label_ids(bucket.get("channels") or {}, "Channel ", 5),
        "cap_per_user": int(AI_DAILY_CAP_PER_USER or 0),
        "cap_per_guild": int(AI_DAILY_CAP_PER_GUILD or 0),
        "guild_used": 0,
        "guild_limit": int(AI_DAILY_CAP_PER_GUILD or 0),
        "faq_hits": 0,
        "cached_answers": 0,
    }
    try:
        import ai_guard

        payload["faq_hits"] = int(ai_guard.savings_stats().get("faq_hits") or 0)
        payload["cached_answers"] = int(ai_guard.savings_stats().get("cache_hits") or 0)
        if guild_id:
            _ok, used, limit = ai_guard.check_guild_cap(int(guild_id))
            payload["guild_used"] = int(used)
            payload["guild_limit"] = int(limit)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Efek samping opsional gagal: %s", exc)
    return payload


def collect_features(guild_id: int) -> dict:
    """Peta fitur per server (baca-saja) + petunjuk cara mengubahnya di Discord.

    Dashboard sengaja tidak menulis apa pun di sini: tujuannya supaya admin melihat
    "fitur apa yang sudah menyala" lalu tahu command mana yang dipakai mengubahnya.
    """
    rows: list[dict] = []

    def _hitung(nama: str, perintah: str, pengambil) -> None:
        try:
            jumlah = int(pengambil())
        except Exception:  # pragma: no cover - jaring aman
            jumlah = 0
        rows.append(
            {
                "nama": nama,
                "aktif": jumlah > 0,
                "ringkas": f"{jumlah} aktif" if jumlah else "belum dipakai",
                "perintah": perintah,
            }
        )

    import menu_builder
    import modal_forms

    _hitung("Panel menu", "/menu buat", lambda: len(menu_builder.list_menus(guild_id)))
    _hitung("Formulir (modal)", "/menu form buat", lambda: len(modal_forms.list_forms(guild_id)))

    try:
        import engagement

        _hitung(
            "Pengumuman terjadwal",
            "/pengumuman tambah",
            lambda: len([a for a in engagement.list_announcements(guild_id) if a.get("enabled")]),
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("Efek samping opsional gagal: %s", exc)

    try:
        import link_embed

        _hitung("Tautan embed", "/embed tautan buat", lambda: len(link_embed.list_links(guild_id)))
    except Exception as exc:  # pragma: no cover
        logger.debug("Efek samping opsional gagal: %s", exc)

    try:
        import flow_triggers

        alur = flow_triggers.get_trigger(guild_id)
        rows.append(
            {
                "nama": "Pemicu gabung",
                "aktif": alur is not None,
                "ringkas": f"{len((alur or {}).get('steps') or [])} langkah" if alur else "belum dipakai",
                "perintah": "/menu pemicu tambah",
            }
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("Efek samping opsional gagal: %s", exc)

    return {"items": rows, "aktif": sum(1 for r in rows if r["aktif"]), "total": len(rows)}


def render_features_block(guild_id: int) -> str:
    """Tabel HTML ringkas untuk blok fitur di halaman utama dashboard."""
    data = collect_features(guild_id)
    if not data["items"]:
        return '<div class="muted">Belum ada data fitur.</div>'
    baris = "\n".join(
        f'<tr><td>{html.escape(r["nama"])}</td>'
        f'<td>{"✅" if r["aktif"] else "⬜"} {html.escape(r["ringkas"])}</td>'
        f'<td><code>{html.escape(r["perintah"])}</code></td></tr>'
        for r in data["items"]
    )
    return (
        f'<p class="muted">{data["aktif"]} dari {data["total"]} fitur sudah dipakai di server ini.</p>'
        "<table><thead><tr><th>Fitur</th><th>Status</th><th>Cara mengubah di Discord</th></tr></thead>"
        f"<tbody>{baris}</tbody></table>"
    )


def collect_tren(hari: int = 7) -> dict:
    """Tren pemakaian AI per hari (dari `insights.ai_usage`) — 0 kuota AI."""
    import datetime

    jumlah = max(2, min(30, int(hari or 7)))
    rows: list[dict] = []
    total = cache = 0
    try:
        data = insights.ai_usage or {}
    except Exception:  # pragma: no cover - jaring aman
        data = {}
    hari_ini = datetime.date.today()
    for mundur in range(jumlah - 1, -1, -1):
        tanggal = hari_ini - datetime.timedelta(days=mundur)
        kunci = tanggal.strftime("%Y-%m-%d")
        bucket = data.get(kunci) or {}
        operasi = int(bucket.get("total") or 0)
        cache_hari = int(bucket.get("cache_hits") or 0)
        total += operasi
        cache += cache_hari
        rows.append(
            {
                "tanggal": kunci,
                "label": tanggal.strftime("%d/%m"),
                "total": operasi,
                "cache_hits": cache_hari,
            }
        )
    return {"hari": jumlah, "rows": rows, "total": total, "cache_hits": cache}


def collect_levels(guild_id: int, *, limit: int = 10) -> dict:
    """Papan peringkat level server (0 kuota AI)."""
    import levels

    if not guild_id:
        return {"guild_id": 0, "rows": [], "total": 0}
    rows, page, total_pages = levels.leaderboard(int(guild_id), limit=limit)
    return {
        "guild_id": int(guild_id),
        "page": page + 1,
        "total_pages": total_pages,
        "rows": [
            {
                "user_id": int(uid),
                "level": int(data.get("level") or 0),
                "xp": int(data.get("xp") or 0),
                "messages": int(data.get("messages") or 0),
                "voice_xp": int(data.get("voice_xp") or 0),
            }
            for uid, data in rows
        ],
    }


# ==============================================================================
# RENDER HTML (server-side, tanpa framework)
# ==============================================================================


def _guild_hint(bot, request) -> tuple[int, str]:
    """Ambil `guild` dari query; jatuh ke server pertama bila kosong/tidak valid."""
    raw = str(request.query.get("guild") or "").strip()
    gid = int(raw) if raw.isdigit() else 0
    guild = None
    if gid and callable(getattr(bot, "get_guild", None)):
        guild = bot.get_guild(gid)
    if guild is None:
        guild_list = list(getattr(bot, "guilds", []) or [])
        if guild_list:
            guild = guild_list[0]
            gid = int(getattr(guild, "id", 0) or 0)
    return gid, str(getattr(guild, "name", "") or "")

async def start_dashboard(bot) -> bool:
    """Menjalankan server dashboard bila dikonfigurasi. Mengembalikan True jika menyala.

    Fungsi ini dulu 1.571 baris karena semua handler ditulis bersarang di sini.
    Sekarang tugasnya tinggal empat: siapkan `web.Application`, pasang middleware
    keamanan, daftarkan rute dari tabel, lalu nyalakan `TCPSite`.
    """
    global _runner, _site

    cfg = dashboard_config()
    if not cfg["enabled"]:
        logger.info("Dashboard web tidak aktif (%s).", cfg["reason"])
        return False
    if _runner is not None:
        return True

    from aiohttp import web

    from web_dashboard.bersama import HelperRespons
    from web_dashboard.middleware import MiddlewareKeamanan
    from web_dashboard.rute import HalamanDashboard, RuteDashboard
    from web_dashboard.tabel_rute import pasang_rute

    # Batas body dinaikkan supaya unggahan banner (DASHBOARD_UPLOAD_MB) bisa diterima.
    app = web.Application(client_max_size=dashboard_unggah.batas_byte() + (512 * 1024))

    # Token lemah tidak mematikan dashboard (pengguna lama bisa terkunci), tetapi
    # wajib terlihat di log supaya diperbaiki.
    _kuat, _pesan_kuat = dashboard_security.kekuatan_token(cfg["token"])
    if not _kuat:
        logger.warning("⚠️ %s", _pesan_kuat)
    else:
        logger.info("🔐 %s", _pesan_kuat)

    # Pembatas percobaan token: satu IP yang salah 20× dalam 10 menit diblokir 15 menit.
    # Satu instance dipakai bersama oleh helper (mencatat) dan middleware (menegakkan).
    global pembatas
    pembatas = dashboard_security.Pembatas()

    helper = HelperRespons(bot, cfg)
    app.middlewares.append(
        MiddlewareKeamanan(pembatas=pembatas, pasang_sesi=helper.pasang_sesi)
    )
    jumlah_rute = pasang_rute(app, RuteDashboard(bot, cfg, helper, pembatas), HalamanDashboard(bot, cfg, helper))
    logger.debug("Dashboard: %s rute terpasang.", jumlah_rute)

    try:
        _runner = web.AppRunner(app, access_log=None)
        await _runner.setup()
        _site = web.TCPSite(_runner, cfg["host"], cfg["port"])
        await _site.start()
        logger.info(
            "🛰️ Dashboard web aktif di http://%s:%s/?token=*** "
            "(%s setelan, kirim embed/webhook; AI hanya saat diminta)",
            cfg["host"],
            cfg["port"],
            len(dashboard_admin.FITUR),
        )
        return True
    except Exception as exc:  # pragma: no cover - port bentrok/ditolak panel
        logger.warning("Dashboard web gagal dinyalakan: %s", exc)
        _runner = None
        _site = None
        return False


async def stop_dashboard() -> None:
    """Mematikan server dashboard (dipanggil saat bot shutdown)."""
    global _runner, _site

    if _runner is None:
        return
    try:
        if _site is not None:
            await _site.stop()
        await _runner.cleanup()
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Gagal mematikan dashboard: %s", exc)
    finally:
        _runner = None
        _site = None
        dashboard_security.bersihkan_sesi()


# ---------------------------------------------------------------------------
# Kompatibilitas: nama lama tetap dapat diakses lewat `web_dashboard.*`
# ---------------------------------------------------------------------------
# Sebelum pemecahan, semua nama ini hidup di satu modul `web_dashboard.py`.
# Supaya 32 berkas tes dan `main.py` tidak perlu diubah, nama tersebut
# di-import ulang di sini (bukan disalin).
from web_dashboard.halaman import (  # noqa: E402,F401  (setelah definisi inti)
    ANCHOR_HALAMAN,
    BAGIAN_SAMBUTAN,
    BATAS_AUTO,
    COOKIE_AUTO,
    COOKIE_AUTO_MAKS,
    FIELD_AUTO_MANUAL,
    GRUP_HALAMAN,
    HALAMAN,
    HALAMAN_SETELAN,
    HALAMAN_SLUG,
    KARTU_HALAMAN,
    LEGACY_HALAMAN,
    PILIHAN_AUTO,
    SETELAN_BOOST,
    SETELAN_PERPISAHAN,
    SETELAN_SAMBUTAN,
    UJI_HALAMAN,
    _ANCHOR_BAGIAN,
    _ANCHOR_GRUP,
    _anchor_aksi,
    _anchor_konten,
    _flash_box,
    _id_aman,
    _label_auto,
    _teks_pesan,
    detik_auto,
    detik_dari_kueri,
    fitur_grup,
    form_auto,
    halaman_dari_anchor,
    halaman_dari_path,
    render_menu,
    url_halaman,
)
from web_dashboard.kontrol import (  # noqa: E402,F401
    FITUR_SEDERHANA,
    LEVEL_OPTIONS,
    apply_dashboard_action,
    dashboard_controls,
    render_controls_block,
)
from web_dashboard.tampilan import (  # noqa: E402,F401
    PANEL,
    _PAGE_TEMPLATE,
    _label_tes,
    _levels_table,
    _rows_table,
    render_dashboard_html,
    susun_isi,
    susun_isi_lengkap,
)
from web_dashboard.bersama import HelperRespons  # noqa: E402,F401
from web_dashboard.middleware import MiddlewareKeamanan  # noqa: E402,F401
from web_dashboard.rute import HalamanDashboard, RuteDashboard  # noqa: E402,F401
from web_dashboard.tabel_rute import RUTE_API, RUTE_HALAMAN, pasang_rute  # noqa: E402,F401

__all__ = [
    "start_dashboard",
    "stop_dashboard",
    "dashboard_config",
    "is_authorized",
    "_guild_hint",
    "collect_status",
    "collect_usage",
    "collect_features",
    "collect_tren",
    "collect_levels",
    "render_features_block",
    "HALAMAN",
    "HALAMAN_SLUG",
    "LEGACY_HALAMAN",
    "ANCHOR_HALAMAN",
    "halaman_dari_path",
    "halaman_dari_anchor",
    "url_halaman",
    "fitur_grup",
    "render_dashboard_html",
    "HelperRespons",
    "MiddlewareKeamanan",
    "RuteDashboard",
    "HalamanDashboard",
    "RUTE_API",
    "RUTE_HALAMAN",
    "pasang_rute",
    "BAGIAN_SAMBUTAN",
    "BATAS_AUTO",
    "COOKIE_AUTO",
    "COOKIE_AUTO_MAKS",
    "FIELD_AUTO_MANUAL",
    "GRUP_HALAMAN",
    "HALAMAN_SETELAN",
    "KARTU_HALAMAN",
    "PILIHAN_AUTO",
    "SETELAN_BOOST",
    "SETELAN_PERPISAHAN",
    "SETELAN_SAMBUTAN",
    "UJI_HALAMAN",
    "_ANCHOR_BAGIAN",
    "_ANCHOR_GRUP",
    "_anchor_aksi",
    "_anchor_konten",
    "_flash_box",
    "_id_aman",
    "_label_auto",
    "_teks_pesan",
    "detik_auto",
    "detik_dari_kueri",
    "form_auto",
    "render_menu",
    "FITUR_SEDERHANA",
    "LEVEL_OPTIONS",
    "apply_dashboard_action",
    "dashboard_controls",
    "render_controls_block",
    "PANEL",
    "_PAGE_TEMPLATE",
    "_label_tes",
    "_levels_table",
    "_rows_table",
    "susun_isi",
    "susun_isi_lengkap",
]
