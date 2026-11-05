"""Dashboard web ringan **read-only** (status bot & `/pemakaian`) — 0 kuota AI.

Prinsip desain:

1. **Proses yang sama** — memakai `aiohttp.web` di event loop bot yang sudah jalan
   (aiohttp sudah jadi dependency sejak awal), jadi tidak menambah proses & sangat
   hemat RAM (±2–4 MB).
2. **Read-only** — semua endpoint hanya `GET`, tidak ada tombol/aksi yang bisa
   mengubah konfigurasi server. Aman bila tautannya tersebar.
3. **Opt-in** — dashboard hanya menyala bila `DASHBOARD_TOKEN` diisi **dan** ada port
   (`DASHBOARD_PORT`, atau `SERVER_PORT`/`PORT` dari panel hosting seperti Wispbyte).
4. **Tanpa JavaScript wajib** — HTML dirender di server + `meta refresh`, sehingga
   tetap ringan dibuka dari HP.

Endpoint:

| Path | Isi |
| :--- | :--- |
| `/` | Halaman HTML (status + pemakaian + papan level) |
| `/api/status` | JSON status bot (uptime, RAM, latensi, server, versi) |
| `/api/pemakaian?guild=<id>` | JSON pemakaian AI hari ini (operasi, token, cache, kuota) |
| `/api/level?guild=<id>` | JSON papan peringkat level |
| `/healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

Autentikasi: `?token=...`, header `X-Dashboard-Token`, atau `Authorization: Bearer ...`.
"""

import html
import logging
import os
import time

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
        "refresh": max(5, int(DASHBOARD_REFRESH_SEC or 30)),
        "reason": (
            "aktif"
            if (port > 0 and token)
            else ("DASHBOARD_TOKEN belum diisi" if port > 0 else "port dashboard tidak ditemukan")
        ),
    }


def is_authorized(*, query_token: str = "", header_token: str = "", expected: str = "") -> bool:
    """Cek token akses dashboard (query, `X-Dashboard-Token`, atau `Bearer`)."""
    want = str(expected or "").strip()
    if not want:
        return False
    given = str(query_token or header_token or "").strip()
    if given.startswith("Bearer "):
        given = given[len("Bearer "):].strip()
    return bool(given) and given == want


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

    def _top(counter: dict, limit: int = 5) -> list[list]:
        items = sorted((counter or {}).items(), key=lambda kv: int(kv[1]), reverse=True)
        return [[str(k), int(v)] for k, v in items[:limit]]

    payload = {
        "date": insights.today_key(),
        "total": int(bucket.get("total") or 0),
        "cache_hits": int(bucket.get("cache_hits") or 0),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "kinds": _top(bucket.get("kinds") or {}, 8),
        "users": _top(bucket.get("users") or {}, 5),
        "channels": _top(bucket.get("channels") or {}, 5),
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
    except Exception:  # pragma: no cover - jaring aman
        pass
    return payload


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
_PAGE_TEMPLATE = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh}">
<title>Dashboard {bot_name} — v{version}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 20px; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         background: #0f1117; color: #e6e6f0; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .muted {{ color: #8b90a3; font-size: 12px; }}
  .grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
           margin: 16px 0 24px; }}
  .card {{ background: #171a23; border: 1px solid #242838; border-radius: 14px; padding: 14px 16px; }}
  .card b {{ display: block; font-size: 22px; margin-top: 6px; color: #b39dff; }}
  .panel {{ background: #14161f; border: 1px solid #242838; border-radius: 14px; padding: 16px;
            margin-bottom: 14px; }}
  .panel h2 {{ font-size: 14px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: .06em;
               color: #9aa0b5; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td, th {{ text-align: left; padding: 6px 4px; border-bottom: 1px solid #1d2130; }}
  th {{ color: #8b90a3; font-weight: 500; }}
  .ok {{ color: #58d68d; }} .warn {{ color: #f5b041; }}
  footer {{ margin-top: 18px; }}
</style>
</head>
<body>
  <h1>{heading}</h1>
  <div class="muted">v{version} • read-only • tanpa kuota AI • diperbarui {checked_at} (auto-refresh {refresh}s)</div>

  <div class="grid">
    <div class="card">Uptime<b>{uptime}</b></div>
    <div class="card">RAM<b>{ram_mb} MB</b></div>
    <div class="card">Latensi<b>{ping_ms} ms</b></div>
    <div class="card">Server / Member<b>{guilds} / {members}</b></div>
    <div class="card">Gemini<b class="{ai_class}">{ai_label}</b></div>
    <div class="card">Operasi AI Hari Ini<b>{total}</b></div>
  </div>

  <div class="panel">
    <h2>📊 Pemakaian AI — {date}</h2>
    <table>
      <tr><th>Token masuk</th><td>{tokens_in:,}</td><th>Token keluar</th><td>{tokens_out:,}</td></tr>
      <tr><th>Cache hit</th><td>{cache_hits}</td><th>FAQ lokal</th><td>{faq_hits}</td></tr>
      <tr><th>Kuota server</th><td>{guild_usage}</td><th>Batas per member</th><td>{cap_per_user}</td></tr>
    </table>
  </div>

  <div class="panel">
    <h2>🧩 Jenis Operasi</h2>
    {kinds_table}
  </div>

  <div class="panel">
    <h2>📍 Channel Paling Ramai</h2>
    {channels_table}
  </div>

  <div class="panel">
    <h2>🏆 Papan Peringkat Level</h2>
    {levels_table}
  </div>

  <footer class="muted">
    Data dibaca langsung dari memori bot (JSON lokal). Halaman ini hanya menampilkan data —
    tidak bisa mengubah setelan server. Rahasiakan tautan ini.
  </footer>
</body>
</html>
"""


def _rows_table(rows: list, *, value_label: str) -> str:
    if not rows:
        return '<div class="muted">Belum ada data hari ini.</div>'
    body = "".join(
        f"<tr><td>{html.escape(str(name))}</td><td>{int(value)}</td></tr>" for name, value in rows
    )
    return f"<table><tr><th>Nama</th><th>{html.escape(value_label)}</th></tr>{body}</table>"


def _levels_table(payload: dict) -> str:
    rows = payload.get("rows") or []
    if not rows:
        return '<div class="muted">Belum ada data leveling di server ini.</div>'
    body = "".join(
        f"<tr><td><code>{row['user_id']}</code></td><td>{row['level']}</td>"
        f"<td>{row['xp']:,}</td><td>{row['messages']}</td><td>{row['voice_xp']:,}</td></tr>"
        for row in rows
    )
    return (
        "<table><tr><th>Member</th><th>Level</th><th>XP</th><th>Pesan</th><th>XP Voice</th></tr>"
        f"{body}</table>"
    )


def render_dashboard_html(
    *,
    status: dict,
    usage: dict,
    levels: dict,
    refresh: int = 30,
    heading: str = "🛰️ Dashboard Bot",
) -> str:
    """Merender halaman HTML dashboard (string). Aman untuk data kosong."""
    guild_limit = int(usage.get("guild_limit") or 0)
    guild_used = int(usage.get("guild_used") or 0)
    guild_usage = (
        f"{guild_used} / {guild_limit}" if guild_limit else f"{guild_used} (tanpa batas)"
    )
    ai_ready = bool(status.get("ai_ready"))
    return _PAGE_TEMPLATE.format(
        refresh=max(5, int(refresh)),
        version=html.escape(str(status.get("version") or "-")),
        bot_name=html.escape(str(status.get("bot_name") or "Bot")),
        heading=html.escape(heading),
        uptime=html.escape(str(status.get("uptime") or "-")),
        ram_mb=status.get("ram_mb") or 0,
        ping_ms=int(status.get("ping_ms") or 0),
        guilds=int(status.get("guilds") or 0),
        members=int(status.get("members") or 0),
        ai_class="ok" if ai_ready else "warn",
        ai_label="aktif" if ai_ready else "belum ada key",
        checked_at=html.escape(str(status.get("checked_at") or "-")),
        total=int(usage.get("total") or 0),
        date=html.escape(str(usage.get("date") or "-")),
        tokens_in=int(usage.get("tokens_in") or 0),
        tokens_out=int(usage.get("tokens_out") or 0),
        cache_hits=int(usage.get("cache_hits") or 0),
        faq_hits=int(usage.get("faq_hits") or 0),
        guild_usage=html.escape(guild_usage),
        cap_per_user=(
            f"{int(usage.get('cap_per_user') or 0)}/hari"
            if int(usage.get("cap_per_user") or 0)
            else "tanpa batas"
        ),
        kinds_table=_rows_table(usage.get("kinds") or [], value_label="Operasi"),
        channels_table=_rows_table(usage.get("channels") or [], value_label="Operasi"),
        levels_table=_levels_table(levels),
    )


# ==============================================================================
# SERVER HTTP
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
    """Menjalankan server dashboard bila dikonfigurasi. Mengembalikan True jika menyala."""
    global _runner, _site

    cfg = dashboard_config()
    if not cfg["enabled"]:
        logger.info("Dashboard web tidak aktif (%s).", cfg["reason"])
        return False
    if _runner is not None:
        return True

    from aiohttp import web

    app = web.Application()

    def _authorized(request) -> bool:
        header = str(request.headers.get("X-Dashboard-Token") or "").strip()
        if not header:
            header = str(request.headers.get("Authorization") or "").strip()
        return is_authorized(
            query_token=str(request.query.get("token") or ""),
            header_token=header,
            expected=cfg["token"],
        )

    async def handle_health(_request):
        return web.Response(text="ok", content_type="text/plain")

    async def handle_index(request):
        if not _authorized(request):
            return web.Response(text="401 Unauthorized — tambahkan ?token=...", status=401)
        gid, guild_name = _guild_hint(bot, request)
        page = render_dashboard_html(
            status=collect_status(bot),
            usage=collect_usage(gid),
            levels=collect_levels(gid),
            refresh=cfg["refresh"],
            heading=f"🛰️ Dashboard {guild_name}" if guild_name else "🛰️ Dashboard Bot",
        )
        return web.Response(text=page, content_type="text/html", charset="utf-8")

    async def handle_status(request):
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(collect_status(bot))

    async def handle_usage(request):
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, _name = _guild_hint(bot, request)
        return web.json_response(collect_usage(gid))

    async def handle_levels(request):
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, _name = _guild_hint(bot, request)
        return web.json_response(collect_levels(gid))

    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/pemakaian", handle_usage)
    app.router.add_get("/api/level", handle_levels)
    app.router.add_get("/healthz", handle_health)

    try:
        _runner = web.AppRunner(app, access_log=None)
        await _runner.setup()
        _site = web.TCPSite(_runner, cfg["host"], cfg["port"])
        await _site.start()
        logger.info(
            "🛰️ Dashboard web aktif di http://%s:%s/?token=*** (read-only, 0 kuota AI)",
            cfg["host"],
            cfg["port"],
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
