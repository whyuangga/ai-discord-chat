"""Dashboard web ringan: status bot, pemakaian AI, **setelan server**, dan
pengiriman embed/webhook — 0 kuota AI.

Prinsip desain:

1. **Proses yang sama** — memakai `aiohttp.web` di event loop bot yang sudah jalan
   (aiohttp sudah jadi dependency sejak awal), jadi tidak menambah proses & sangat
   hemat RAM (±2–4 MB).
2. **Baca + tulis terkendali** — halaman `GET /` tidak pernah mengubah apa pun
   (tidak ada efek samping saat membaca setelan).
   Semua perubahan lewat `POST /api/aksi` (setelan), `POST /api/kirim` (pesan/embed),
   dan `POST /api/konten` (pengumuman/tautan/panel/hapus) yang selalu memeriksa token
   dan hanya menjalankan aksi dari whitelist `dashboard_admin`.
3. **Opt-in** — dashboard hanya menyala bila `DASHBOARD_TOKEN` diisi **dan** ada port
   (`DASHBOARD_PORT`, atau `SERVER_PORT`/`PORT` dari panel hosting seperti Wispbyte).
4. **Tanpa JavaScript wajib** — HTML dirender di server + `meta refresh`, sehingga
   tetap ringan dibuka dari HP. Menu ☰ dibuat dengan CSS (`#nav-buka:checked`), dan
   submit form memakai pola POST → redirect (303) → GET supaya nilai baru langsung
   terlihat di panel yang sama.

Endpoint:

| Path | Isi |
| :--- | :--- |
| `/` | Halaman HTML (status + pemakaian + papan level) |
| `/api/status` | JSON status bot (uptime, RAM, latensi, server, versi) |
| `/api/pemakaian?guild=<id>` | JSON pemakaian AI hari ini (operasi, token, cache, kuota) |
| `/api/level?guild=<id>` | JSON papan peringkat level |
| `/api/kontrol?guild=<id>` | JSON status 5 sakelar cepat (level, ekonomi, tumbuh, antispam, antinuke) |
| `/api/fitur?guild=<id>` | JSON peta fitur server |
| `/api/setelan?guild=<id>` | JSON semua setelan (48 fitur) + nilai sekarang |
| `POST /api/aksi` | Ubah setelan (`action=set.<kunci>`) / sakelar cepat lama |
| `POST /api/kirim` | Kirim pesan/embed, opsional lewat webhook identitas |
| `POST /api/konten` | Buat/hapus pengumuman, tautan, panel, formulir, pemicu; ganti/hapus banner panel |
| `POST /api/unggah` | Simpan / hapus banner (`data/uploads/`) |
| `GET /api/tiket` · `POST /api/tiket` | Kotak masuk tiket: daftar, balas (`balas:<id>`), tutup (`tutup:<id>`), pasang panel (`panel`), matikan (`matikan`) |
| `GET /api/panel` · `POST /api/panel` | Editor panel: daftar item, tambah (`tambah:<id>`), hapus (`hapus:<id>:<ref>`), pasang/matikan verifikasi (`verifikasi` / `verifikasi:matikan`) |
| `GET /api/ekspor?jenis=<level/moderasi/tiket/pemakaian>` | unduh CSV analitik server (wajib token) |
| `GET /api/unggahan/<nama>` | Pratinjau banner tersimpan (butuh token) |
| `/healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

Autentikasi: `?token=...`, header `X-Dashboard-Token`, atau `Authorization: Bearer ...`.
"""

import html
import logging
import os
import time
from urllib.parse import urlencode

import dashboard_admin
import dashboard_giveaway
import dashboard_keamanan
import dashboard_panel
import dashboard_pesan
import dashboard_tema
import dashboard_tiket
import dashboard_ui
import dashboard_unggah
import dashboard_uji
import insights
import ticket_archive
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
        "refresh": max(0, int(DASHBOARD_REFRESH_SEC if DASHBOARD_REFRESH_SEC is not None else 30)),
        "reason": (
            "aktif"
            if (port > 0 and token)
            else ("DASHBOARD_TOKEN belum diisi" if port > 0 else "port dashboard tidak ditemukan")
        ),
    }


# Cookie kecil untuk menghidupkan/menjeda auto-refresh tanpa menyentuh `.env`
# (tautan di header dashboard: `…?refresh=0` / `…?refresh=30` / `…?refresh=auto`).
COOKIE_AUTO = "dash_auto"
COOKIE_AUTO_MAKS = 60 * 60 * 24 * 30   # 30 hari


def detik_auto(request, bawaan: int = 30) -> int:
    """Interval auto-refresh yang dipakai: cookie dulu, lalu `DASHBOARD_REFRESH_SEC`."""
    simpan = str(request.cookies.get(COOKIE_AUTO) or "").strip()
    if simpan.isdigit():
        return max(0, min(3600, int(simpan)))
    return max(0, min(3600, int(bawaan or 0)))


# Pilihan cepat interval auto-refresh di header (form GET biasa, tanpa JavaScript).
PILIHAN_AUTO: tuple[tuple[int, str], ...] = (
    (0, "⏸ Mati"),
    (60, "1 menit"),
    (600, "10 menit"),
    (1800, "30 menit"),
    (3600, "1 jam"),
)
# Nama field angka bebas (menimpa pilihan dropdown bila diisi).
FIELD_AUTO_MANUAL = "refresh_detik"
BATAS_AUTO = (0, 3600)


def detik_dari_kueri(kueri) -> str:
    """Nilai mentah auto-refresh dari query: kotak angka dulu, lalu dropdown.

    Hasilnya salah satu dari:
    - `"auto"` → ikut `DASHBOARD_REFRESH_SEC` (cookie dihapus),
    - `"manual"` → dropdown memilih “✏️ Isi sendiri…” tapi angkanya belum ada,
    - atau angka detik sebagai string (di luar 0–3600 dipotong, bukan ditolak,
      supaya tidak pernah ada form buntu).
    """
    bawah, atas = BATAS_AUTO
    manual = str(kueri.get(FIELD_AUTO_MANUAL) or "").strip()
    pilihan = str(kueri.get("refresh") or "").strip().lower()
    if manual.lstrip("+-").isdigit():
        return str(max(bawah, min(atas, int(manual))))
    if manual:
        # Ada isian tapi bukan angka → jangan ubah apa pun, tampilkan kotaknya lagi.
        return "manual"
    if pilihan in ("manual", "isi", "custom"):
        return "manual"
    if not pilihan or pilihan in ("auto", "bawaan", "env"):
        return "auto"
    if pilihan.lstrip("+-").isdigit():
        return str(max(bawah, min(atas, int(pilihan))))
    return "0"


def _label_auto(detik: int) -> str:
    """Label manusiawi untuk angka detik (mis. 45 → “45 detik”, 3600 → “1 jam”)."""
    for nilai, label in PILIHAN_AUTO:
        if nilai == detik:
            return label
    if detik >= 60 and detik % 60 == 0:
        menit = detik // 60
        return f"{menit} menit"
    return f"{detik} detik"


def form_auto(aksi: str, token: str = "", guild_id: int = 0,
              detik: int = 30, dipilih: str = "") -> str:
    """Pengatur “🔄 Auto-refresh” di header — **satu dropdown**, tanpa `.env`.

    Isi dropdown: `⏸ Mati` · `1 menit` · `10 menit` · `30 menit` · `1 jam` ·
    `✏️ Isi sendiri…` · `Ikut .env`. Pilih “Isi sendiri” lalu tekan **Set** →
    halaman dimuat ulang dengan kotak angka detik (0–3600) di dalam form yang
    sama, jadi header tetap ringkas dan angkanya tetap bebas.

    `dipilih` boleh `"auto"` (ikut `DASHBOARD_REFRESH_SEC`), `"manual"`, atau
    angka detik; angka di luar daftar otomatis tampil sebagai mode “Isi sendiri”
    dengan angkanya sudah terisi (pilihan aktif tidak pernah “hilang”).
    """
    if not str(aksi or "").strip():
        return ""
    angka_daftar = {str(nilai) for nilai, _ in PILIHAN_AUTO}
    dipilih = str(dipilih if str(dipilih or "").strip() else max(0, int(detik or 0))).lower()
    manual = ""
    if dipilih in ("manual", "isi", "custom"):
        pilih = "manual"
    elif dipilih.isdigit() and dipilih not in angka_daftar:
        pilih, manual = "manual", dipilih          # angka bebas → mode isi sendiri
    else:
        pilih = dipilih
    opsi = "".join(
        f'<option value="{nilai}"{" selected" if str(nilai) == pilih else ""}>{label}</option>'
        for nilai, label in PILIHAN_AUTO
    )
    opsi += f'<option value="manual"{" selected" if pilih == "manual" else ""}>✏️ Isi sendiri…</option>'
    opsi += f'<option value="auto"{" selected" if pilih == "auto" else ""}>Ikut .env</option>'
    kotak = ""
    if pilih == "manual":
        kotak = (
            f'<input type="number" name="{FIELD_AUTO_MANUAL}" id="input-auto"'
            f' min="{BATAS_AUTO[0]}" max="{BATAS_AUTO[1]}" step="5" inputmode="numeric"'
            f' value="{html.escape(manual, quote=True)}" placeholder="{max(0, int(detik or 0))}"'
            ' aria-label="Interval auto-refresh dalam detik"'
            ' title="Isi sendiri: detik, mis. 45" autofocus>'
            '<span class="muted satuan">detik</span>'
        )
    return (
        f'<form method="get" action="{html.escape(aksi, quote=True)}" class="pemilih-auto">'
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
        '<label for="pilih-auto">🔄 Auto-refresh</label>'
        '<select name="refresh" id="pilih-auto" aria-label="Interval auto-refresh">'
        f"{opsi}</select>"
        f"{kotak}"
        '<button type="submit">Set</button></form>'
    )


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
    except Exception:  # pragma: no cover - jaring aman
        pass
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
    except Exception:  # pragma: no cover
        pass

    try:
        import link_embed

        _hitung("Tautan embed", "/embed tautan buat", lambda: len(link_embed.list_links(guild_id)))
    except Exception:  # pragma: no cover
        pass

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
    except Exception:  # pragma: no cover
        pass

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
_PAGE_TEMPLATE = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta_refresh}
<title>Dashboard {bot_name} — v{version}</title>
{font_link}
<style>{css}</style>
</head>
<body>
  <header class="topbar">
    <input type="checkbox" id="nav-buka" class="nav-buka">
    <div class="baris">
      <span class="judul">{heading}</span>
      <span class="meta">v{version} • {checked_at}{refresh_info}</span>
      <label class="menu-btn" for="nav-buka">☰ Menu</label>
    </div>
    {menu}
    <div class="baris" style="margin-top:8px">{guild_picker}{auto_pilih}</div>
  </header>
  {flash}
  <p class="keterangan-halaman">{keterangan}</p>

{isi}

  <footer class="muted">
    Data dibaca dari JSON lokal bot. Kontrol di sini hanya mengubah setelan fitur (bukan menghapus data).
    Rahasiakan tautan ini — siapa pun yang punya token bisa mengubah setelan.
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


_ANCHOR_GRUP: dict[str, str] = {
    "inti": "p-inti",
    "tiket": "p-tiket",
    "sambutan": "p-welcome",
    "keamanan": "p-keamanan",
    "bantuan": "p-tiket",
    "konten": "p-konten",
}
_ANCHOR_BAGIAN: tuple[tuple[str, str], ...] = (
    ("sambutan.", "p-welcome"),
    ("pamit.", "p-goodbye"),
    ("boost.", "p-boost"),
)


def _anchor_aksi(aksi: str) -> str:
    """Panel tujuan setelah submit: halaman grup, bagian sambutan, atau kontrol cepat."""
    kunci = str(aksi or "").strip().lower()
    if kunci.startswith("set."):
        nama = kunci[len("set."):]
        for awalan, anchor in _ANCHOR_BAGIAN:
            if nama.startswith(awalan):
                return anchor
        return _ANCHOR_GRUP.get(HALAMAN_SETELAN.get(nama, ""), "p-inti")
    # Aksi lain (sakelar level/ekonomi/pertumbuhan) ada di halaman Inti.
    return "p-kontrol"


def _anchor_konten(aksi: str) -> str:
    """Panel tujuan untuk aksi konten (buat/hapus/banner)."""
    kunci = str(aksi or "").strip().lower()
    if kunci.startswith(("banner.", "hapusbanner.")):
        return "p-konten"
    if kunci.startswith("hapus."):
        return "p-konten"
    if kunci.startswith("unggah."):
        return "p-banner"
    return "p-buat"


def _teks_pesan(pesan: str) -> str:
    """Escape HTML lalu ubah `**tebal**` menjadi <b> (pesan bot memakai markdown)."""
    aman = html.escape(str(pesan or "").strip())
    bagian = aman.split("**")
    if len(bagian) < 3:
        return aman
    hasil = bagian[0]
    for urutan, potongan in enumerate(bagian[1:], start=1):
        hasil += (f"<b>{potongan}</b>" if urutan % 2 else potongan)
    return hasil


def _flash_box(pesan: str, ok: bool = True) -> str:
    """Kotak pesan setelah submit (pengganti halaman hasil terpisah)."""
    teks = str(pesan or "").strip()
    if not teks:
        return ""
    kelas = "flash" if ok else "flash galat"
    tanda = "✅" if ok else "⚠️"
    return f'<div class="{kelas}">{tanda} {_teks_pesan(teks)}</div>'


# ==============================================================================
# HALAMAN (fitur dipecah per halaman — tanpa JavaScript)
# ==============================================================================
# Satu halaman = satu kelompok fitur. Menu atas menjadi tautan antar-halaman
# (token & server tetap terbawa di query), dan tiap panel masih punya `id`
# sendiri supaya `…/setelan#p-setelan` tetap bisa dipakai sebagai bookmark.
HALAMAN: tuple[dict, ...] = (
    {
        "slug": "",
        "menu": "📡 Ringkasan",
        "judul": "📡 Ringkasan",
        "keterangan": "Status bot, pemakaian AI, tren 7 hari, papan peringkat, & tes koneksi AI.",
        "panel": ("p-status", "p-pemakaian", "p-jenis", "p-tren", "p-channel", "p-level", "p-ai"),
    },
    {
        "slug": "sambutan",
        "menu": "👋 Sambutan & pamit",
        "judul": "👋 Sambutan & pamit",
        "keterangan": "Sambutan member baru, pesan perpisahan, dan ucapan boost — satu halaman.",
        "panel": ("p-sambutan",),
    },
    {
        "slug": "inti",
        "menu": "⚙️ Inti & level",
        "judul": "⚙️ Inti, level, & ekonomi",
        "keterangan": "Kontrol cepat + setelan level, ekonomi koin, pelacakan pertumbuhan, & prefix.",
        "panel": ("p-kontrol", "p-inti", "p-rank"),
    },
    {
        "slug": "keamanan",
        "menu": "🛡️ Keamanan",
        "judul": "🛡️ Keamanan",
        "keterangan": "Anti-spam, anti-nuke, pengaman raid, verifikasi, & proteksi anti-phishing.",
        "panel": ("p-keamanan",),
    },
    {
        "slug": "tiket",
        "menu": "🎫 Tiket & sapaan",
        "judul": "🎫 Tiket & sapaan harian",
        "keterangan": "Kotak masuk tiket, setelan tiket, & ucapan ulang tahun.",
        "panel": ("p-tiket",),
    },
    {
        "slug": "konten",
        "menu": "🧩 Konten & interaksi",
        "judul": "🧩 Konten & interaksi",
        "keterangan": "Fitur AI per channel, starboard, kotak saran, fakta harian, koran pagi, & backup.",
        "panel": ("p-konten",),
    },
    {
        "slug": "giveaway",
        "menu": "🎁 Giveaway",
        "judul": "🎁 Giveaway",
        "keterangan": "Buat, hentikan, & undi ulang giveaway; atur syarat berlapis & template.",
        "panel": ("p-giveaway",),
    },
    {
        "slug": "kirim",
        "menu": "✉️ Kirim",
        "judul": "✉️ Kirim pesan & banner",
        "keterangan": "Kirim pesan/embed, pratinjau dulu, dan unggah banner.",
        "panel": ("p-kirim", "p-banner"),
    },
    {
        "slug": "buat",
        "menu": "➕ Buat",
        "judul": "➕ Buat konten",
        "keterangan": "Pengumuman, tautan, panel, formulir, pemicu + daftar konten tersimpan.",
        "panel": ("p-buat", "p-tersimpan"),
    },
    {
        "slug": "panel",
        "menu": "🎨 Panel",
        "judul": "🎨 Editor panel",
        "keterangan": "Tambah/hapus tombol & dropdown, segarkan panel, pasang gerbang verifikasi.",
        "panel": ("p-panel",),
    },
    {
        "slug": "ekspor",
        "menu": "📥 Ekspor",
        "judul": "📥 Ekspor & riwayat",
        "keterangan": "Unduh CSV (level, moderasi, tiket, pemakaian) & lihat riwayat perubahan.",
        "panel": ("p-ekspor", "p-riwayat"),
    },
)

HALAMAN_SLUG: dict[str, dict] = {h["slug"]: h for h in HALAMAN}
ANCHOR_HALAMAN: dict[str, str] = {
    anchor: h["slug"] for h in HALAMAN for anchor in h["panel"]
}
# Bookmark lama tetap diarahkan ke tempat barunya.
ANCHOR_HALAMAN.update({
    "p-kartu": "sambutan",
    "p-uji": "",
    "p-rank": "inti",
    "p-aturan": "keamanan",
    "p-honeypot": "keamanan",
    "p-setelan": "inti",
    "p-perpisahan": "sambutan",
    "p-boost": "sambutan",
    "p-welcome": "sambutan",
    "p-goodbye": "sambutan",
    "p-boost-slot": "sambutan",
})
LEGACY_HALAMAN: dict[str, str] = {"uji": "", "setelan": "inti", "perpisahan": "sambutan",
                                  "boost": "sambutan"}

# Setelan sambutan/pamit/boost dipisah per bagian di halamannya masing-masing.
SETELAN_SAMBUTAN: tuple[str, ...] = (
    "sambutan.channel", "sambutan.dm", "sambutan.kartu", "sambutan.persona",
    "sambutan.bahasa", "sambutan.arti",
)
SETELAN_PERPISAHAN: tuple[str, ...] = ("pamit.channel", "pamit.bahasa", "pamit.arti")
SETELAN_BOOST: tuple[str, ...] = ("boost.channel",)

# Satu halaman per grup setelan (lihat `dashboard_admin.GRUP`).
GRUP_HALAMAN: dict[str, str] = {
    "inti": "inti",
    "sambutan": "sambutan",
    "keamanan": "keamanan",
    "bantuan": "tiket",
    "konten": "konten",
}


def fitur_grup(kunci_grup: str) -> tuple[str, ...]:
    """Daftar kunci setelan milik satu grup dashboard."""
    for grup in dashboard_admin.GRUP:
        if grup.get("kunci") == kunci_grup:
            return tuple(k for k in grup["fitur"] if k in dashboard_admin.FITUR)
    return ()


# Kunci setelan → halaman tempat ia ditampilkan (dipakai `_anchor_aksi`).
HALAMAN_SETELAN: dict[str, str] = {}
for _grup, _slug in GRUP_HALAMAN.items():
    for _kunci in fitur_grup(_grup):
        HALAMAN_SETELAN[_kunci] = _slug
for _kunci in SETELAN_SAMBUTAN + SETELAN_PERPISAHAN + SETELAN_BOOST:
    HALAMAN_SETELAN[_kunci] = "sambutan"

# Halaman sambutan: tiga bagian (sambutan, pamit, boost) di satu halaman.
BAGIAN_SAMBUTAN: tuple[tuple[str, str, str, str], ...] = (
    ("welcome", "p-welcome", "👋 Sambutan member baru", "Dikirim saat ada member baru gabung."),
    ("goodbye", "p-goodbye", "👣 Pesan perpisahan", "Dikirim saat member keluar."),
    ("boost", "p-boost", "💎 Ucapan boost", "Dikirim saat member nge-boost server."),
)

# Kartu & tes yang menempel di halaman selain halaman bagian sambutan.
KARTU_HALAMAN: dict[str, tuple[str, ...]] = {"sambutan": ("welcome", "goodbye", "boost")}
UJI_HALAMAN: dict[str, tuple[str, ...]] = {
    "": ("ai",),
    "buat": ("pengumuman",),
    "panel": ("panel",),
    "tiket": ("tiket",),
    "konten": ("digest",),
    "ekspor": ("ekspor",),
    "giveaway": ("giveaway",),
    "inti": ("kartu",),
    "keamanan": ("honeypot",),
}


def _id_aman(nilai: object) -> int:
    """Angka dari form/URL tanpa pernah melempar `ValueError`."""
    try:
        return int(str(nilai).strip())
    except (TypeError, ValueError):
        return 0


def halaman_dari_path(path: str) -> str:
    """Slug halaman dari URL (`/` -> "", `/setelan` -> "setelan")."""
    slug = str(path or "").strip("/")
    return slug if slug in HALAMAN_SLUG else ""


def halaman_dari_anchor(anchor: str) -> str:
    """Halaman tempat sebuah panel (`p-tiket`, …) berada."""
    return ANCHOR_HALAMAN.get(str(anchor or "").strip(), "")


def url_halaman(slug: str, token: str = "", guild_id: int = 0) -> str:
    """Alamat satu halaman dengan token & server tetap terbawa."""
    dasar = f"/{slug}" if slug else "/"
    return f"{dasar}?{urlencode({'token': token, 'guild': int(guild_id or 0)})}"


def render_menu(slug: str, token: str = "", guild_id: int = 0) -> str:
    """Menu utama: tautan antar-halaman, halaman aktif ditandai `aria-current`."""
    aktif = slug if slug in HALAMAN_SLUG else ""
    butir = []
    for halaman in HALAMAN:
        ini = halaman["slug"] == aktif
        tanda = ' aria-current="page"' if ini else ""
        tautan = html.escape(url_halaman(halaman["slug"], token, guild_id), quote=True)
        butir.append(f'<a href="{tautan}"{tanda}>{halaman["menu"]}</a>')
    return '<nav class="menu" aria-label="Halaman dashboard">' + "".join(butir) + "</nav>"


def _panel_status(d: dict) -> str:
    return (
        '<section id="p-status">\n  <div class="grid">\n'
        f'    <div class="card">Uptime<b>{d["uptime"]}</b></div>\n'
        f'    <div class="card">RAM<b>{d["ram_mb"]} MB</b></div>\n'
        f'    <div class="card">Latensi<b>{d["ping_ms"]} ms</b></div>\n'
        f'    <div class="card">Server / Member<b>{d["guilds"]} / {d["members"]}</b></div>\n'
        f'    <div class="card">Gemini<b class="{d["ai_class"]}">{d["ai_label"]}</b></div>\n'
        f'    <div class="card">Operasi AI Hari Ini<b>{d["total"]}</b></div>\n'
        "  </div>\n  </section>"
    )


def _panel_pemakaian(d: dict) -> str:
    return (
        f'<div class="panel" id="p-pemakaian">\n'
        f'    <h2>📊 Pemakaian AI — {d["date"]}</h2>\n    <table>\n'
        f'      <tr><th>Token masuk</th><td>{d["tokens_in"]:,}</td>'
        f'<th>Token keluar</th><td>{d["tokens_out"]:,}</td></tr>\n'
        f'      <tr><th>Cache hit</th><td>{d["cache_hits"]}</td>'
        f'<th>FAQ lokal</th><td>{d["faq_hits"]}</td></tr>\n'
        f'      <tr><th>Kuota server</th><td>{d["guild_usage"]}</td>'
        f'<th>Batas per member</th><td>{d["cap_per_user"]}</td></tr>\n'
        "    </table>\n  </div>"
    )


def _panel_jenis(d: dict) -> str:
    return (
        '<div class="panel" id="p-jenis">\n    <h2>🧩 Jenis Operasi</h2>\n'
        f'    {d["kinds_table"]}\n  </div>'
    )


def _panel_tren(d: dict) -> str:
    return (
        f'<div class="panel" id="p-tren">\n    <h2>📈 Tren {d["tren_hari"]} hari</h2>\n'
        f'    {d["tren_block"]}\n  </div>'
    )


def _panel_channel(d: dict) -> str:
    return (
        '<div class="panel" id="p-channel">\n    <h2>📍 Channel Paling Ramai</h2>\n'
        f'    {d["channels_table"]}\n  </div>'
    )


def _panel_level(d: dict) -> str:
    return (
        '<div class="panel" id="p-level">\n    <h2>🏆 Papan Peringkat Level</h2>\n'
        f'    {d["levels_table"]}\n  </div>'
    )


def _panel_kontrol(d: dict) -> str:
    return (
        '<div class="panel" id="p-kontrol">\n    <h2>⚙️ Kontrol Cepat</h2>\n'
        '    <p class="muted">Menyala/mematikan fitur per server. Butuh token dashboard yang sah.</p>\n'
        f'    {d["fitur_block"]}\n\n    {d["kontrol_block"]}\n  </div>'
    )


def _panel_kirim(d: dict) -> str:
    return (
        '<div class="panel" id="p-kirim">\n    <h2>✉️ Kirim pesan &amp; embed</h2>\n'
        '    <p class="muted">Kirim pengumuman sekali jalan, atau pakai identitas webhook supaya\n'
        '    nama &amp; avatar pengirim bisa berbeda dari bot.</p>\n'
        f'    {d["kirim_block"]}\n  </div>'
    )


def _panel_buat(d: dict) -> str:
    return (
        '<div class="panel" id="p-buat">\n    <h2>➕ Buat konten</h2>\n'
        f'    {d["buat_block"]}\n'
        '    <div class="subpanel"><h3>🧪 Tes pengumuman</h3>'
        f'{d["uji_block"]}</div>\n  </div>'
    )


def _panel_tersimpan(d: dict) -> str:
    return (
        '<div class="panel" id="p-tersimpan">\n    <h2>🗂️ Konten tersimpan</h2>\n'
        '    <p class="muted">Klik Hapus untuk membuang konten. Pesan yang sudah terkirim di Discord\n'
        '    tidak ikut terhapus.</p>\n'
        f'    {d["konten_block"]}\n  </div>'
    )


def _panel_ekspor(d: dict) -> str:
    return (
        '<div class="panel" id="p-ekspor">\n    <h2>📥 Ekspor CSV</h2>\n'
        f'    {d["ekspor_block"]}\n'
        '    <div class="subpanel"><h3>🧪 Tes ekspor</h3>'
        f'{d["uji_block"]}</div>\n  </div>'
    )


def _panel_panel(d: dict) -> str:
    return (
        '<div class="panel" id="p-panel">\n    <h2>🧩 Editor panel (tombol &amp; dropdown)</h2>\n'
        '    <p class="muted">Tambah atau hapus tombol/role/dropdown tanpa membuka Discord.</p>\n'
        f'    {d["panel_block"]}\n'
        '    <div class="subpanel"><h3>🧪 Tes panel</h3>'
        f'{d["uji_block"]}</div>\n  </div>'
    )


def _panel_tiket(d: dict) -> str:
    return (
        '<div class="panel" id="p-tiket">\n    <h2>🎫 Tiket &amp; sapaan harian</h2>\n'
        '    <p class="muted">Balas atau tutup tiket dari HP, atur sistem tiket, dan '
        'ucapan ulang tahun — semuanya di halaman ini.</p>\n'
        f'    {d["tiket_block"]}\n'
        '    <div class="subpanel"><h3>⚙️ Setelan tiket &amp; sapaan</h3>'
        f'{d["setelan_block"]}</div>\n'
        '    <div class="subpanel"><h3>📚 Arsip transkrip (bisa dicari)</h3>'
        f'{d.get("arsip_block", "")}</div>\n'
        '    <div class="subpanel"><h3>🧪 Tes panel tiket</h3>'
        f'{d["uji_block"]}</div>\n  </div>'
    )


def _panel_banner(d: dict) -> str:
    return (
        '<div class="panel" id="p-banner">\n    <h2>🖼️ Banner &amp; gambar</h2>\n'
        '    <p class="muted">Unggah gambar lalu pakai untuk banner panel atau gambar embed —\n'
        '    tanpa perlu URL publik. Berkas disimpan di <code>data/uploads/</code>.</p>\n'
        f'    {d["banner_block"]}\n  </div>'
    )


def _panel_ai(d: dict) -> str:
    return (
        '<div class="panel" id="p-ai">\n    <h2>🤖 Diagnostik AI</h2>\n'
        '    <p class="muted">Satu panggilan AI kecil untuk memastikan API key, kuota, '
        'dan jaringan sehat. Tidak mengirim pesan ke Discord.</p>\n'
        f'    {d["uji_block"]}\n  </div>'
    )


def _label_tes(blok: str) -> str:
    """Beri judul kecil di atas tombol tes (kalau blok tesnya ada)."""
    if not blok:
        return ""
    return f'<div class="kepala-tes"><b>🧪 Tes fitur</b></div>{blok}'


def _panel_sambutan(d: dict) -> str:
    """Sambutan, perpisahan, & boost dalam **satu** halaman (setelan + kartu + tes)."""
    bagian = ""
    for jenis, anchor, judul, ket in BAGIAN_SAMBUTAN:
        bagian += (
            f'<div class="subpanel" id="{anchor}">'
            f"<h3>{judul}</h3>"
            f'<p class="muted">{ket}</p>'
            f'{d.get("setelan_" + jenis, "")}'
            f'{d.get("kartu_" + jenis, "")}'
            f'{_label_tes(d.get("uji_" + jenis, ""))}'
            "</div>\n"
        )
    return (
        '<div class="panel" id="p-sambutan">\n    <h2>👋 Sambutan &amp; pamit</h2>\n'
        '    <p class="muted">Tiga pesan otomatis dalam satu tempat: sambutan member baru, '
        'pesan perpisahan, dan ucapan saat server di-boost. Tiap bagian punya setelan, '
        'gambar kartu, dan tombol tesnya sendiri.</p>\n'
        f"    {bagian}  </div>"
    )


def _panel_grup(anchor: str, judul: str, ket: str, *extra: str) -> object:
    """Halaman satu grup setelan (+ blok tambahan seperti inbox atau tes)."""

    def render(d: dict) -> str:
        tambahan = "".join(
            d.get(nama + "_block", d.get(nama, "")) for nama in extra
        )
        return (
            f'<div class="panel" id="{anchor}">\n    <h2>{judul}</h2>\n'
            f'    <p class="muted">{ket}</p>\n'
            f'    {d["setelan_block"]}\n'
            f"{tambahan}  </div>"
        )

    return render


def _panel_giveaway(d: dict) -> str:
    """Halaman giveaway: kendali penuh + tombol tes syarat."""
    return (
        '<div class="panel" id="p-giveaway">\n    <h2>🎁 Giveaway</h2>\n'
        '    <p class="muted">Buat, hentikan, dan undi ulang giveaway langsung dari HP. '
        'Syarat berlapis — role, level server, umur akun — dan peluang ekstra untuk '
        'pemilik role bonus diatur di sini, bukan lewat command.</p>\n'
        f'    {d.get("giveaway_block", "")}\n'
        '    <div class="subpanel"><h3>🧪 Tes syarat giveaway</h3>'
        f'{d["uji_block"]}</div>\n  </div>'
    )


def _panel_riwayat(d: dict) -> str:
    return (
        '<div class="panel" id="p-riwayat">\n    <h2>🧾 Riwayat perubahan</h2>\n'
        f'    {d["audit_block"]}\n  </div>'
    )


PANEL: dict[str, object] = {
    "p-status": _panel_status,
    "p-pemakaian": _panel_pemakaian,
    "p-jenis": _panel_jenis,
    "p-tren": _panel_tren,
    "p-channel": _panel_channel,
    "p-level": _panel_level,
    "p-kontrol": _panel_kontrol,
    "p-kirim": _panel_kirim,
    "p-buat": _panel_buat,
    "p-ekspor": _panel_ekspor,
    "p-panel": _panel_panel,
    "p-tiket": _panel_tiket,
    "p-banner": _panel_banner,
    "p-ai": _panel_ai,
    "p-sambutan": _panel_sambutan,
    "p-inti": _panel_grup(
        "p-inti", "⚙️ Inti, level, &amp; ekonomi",
        "Setelan dasar server: level &amp; XP, ekonomi koin, pelacakan pertumbuhan, dan prefix.",
    ),
    "p-keamanan": _panel_grup(
        "p-keamanan", "🛡️ Keamanan",
        "Anti-spam, anti-nuke, pengaman raid, verifikasi, &amp; proteksi anti-phishing. "
        "Mode “Lapor” hanya mencatat — paling aman untuk memulai.",
        "honeypot",
        "aturan",
    ),
    "p-konten": _panel_grup(
        "p-konten", "🧩 Konten &amp; interaksi",
        "Fitur AI per channel (boleh lebih dari satu), starboard, kotak saran, fakta harian, "
        "koran pagi, &amp; backup otomatis.",
        "starboard",
        "uji",
    ),
    "p-rank": lambda d: (
        '<div class="panel" id="p-rank">\n    <h2>🖼️ Kartu rank (PNG)</h2>\n'
        '    <p class="muted">Kartu rank yang dikirim <code>/level kartu</code> dirender '
        'server (Pillow) dengan <b>perender yang sama</b> seperti pratinjau di bawah. '
        'Latar boleh diunggah sendiri; tanpa latar, bot memakai gradasi warna aksen.</p>\n'
        f'    {d.get("kartu_rank_block", "")}\n  </div>'
    ),
    "p-giveaway": _panel_giveaway,
    "p-tersimpan": _panel_tersimpan,
    "p-riwayat": _panel_riwayat,
}


def susun_isi(slug: str, data: dict) -> str:
    """HTML isi untuk satu halaman (hanya panel milik halaman itu)."""
    halaman = HALAMAN_SLUG.get(slug) or HALAMAN_SLUG[""]
    return "\n\n".join(PANEL[a](data) for a in halaman["panel"] if a in PANEL)


def susun_isi_lengkap(data: dict) -> str:
    """Semua panel dalam satu halaman (dipakai tes lama & mode cetak)."""
    return "\n\n".join(PANEL[a](data) for a in PANEL)


def render_dashboard_html(
    *,
    status: dict,
    usage: dict,
    levels: dict,
    refresh: int = 30,
    auto_aksi: str = "",
    auto_dipilih: str = "",
    heading: str = "🛰️ Dashboard Bot",
    kontrol_block: str = '<div class="muted">Kontrol tidak tersedia.</div>',
    fitur_block: str = "",
    setelan_block: str = "",
    kirim_block: str = "",
    buat_block: str = "",
    konten_block: str = "",
    audit_block: str = "",
    banner_block: str = "",
    guild_picker: str = "",
    flash_pesan: str = "",
    flash_ok: bool = True,
    alamat_bersih: str = "",
    ekspor_block: str = "",
    panel_block: str = "",
    tiket_block: str = "",
    giveaway_block: str = "",
    arsip_block: str = "",
    tren_block: str = "",
    kartu_block: str = "",
    kartu_rank_block: str = "",
    starboard_block: str = "",
    aturan_block: str = "",
    honeypot_block: str = "",
    uji_block: str = "",
    setelan_welcome: str = "",
    setelan_goodbye: str = "",
    setelan_boost: str = "",
    kartu_welcome: str = "",
    kartu_goodbye: str = "",
    kartu_boost: str = "",
    uji_welcome: str = "",
    uji_goodbye: str = "",
    uji_boost: str = "",
    tren_hari: int = 7,
    halaman: str | None = None,
    menu: str = "",
    isi: str | None = None,
    token: str = "",
    guild_id: int = 0,
    judul_halaman: str = "",
    keterangan: str = "",
) -> str:
    """Merender satu halaman dashboard (string). Aman untuk data kosong.

    `halaman` menentukan kelompok panel yang ditampilkan; bila `isi` diberikan
    (mis. hasil `susun_isi`) isi itulah yang dipakai. Tanpa `halaman`/`isi`,
    semua panel dirender dalam satu halaman — perilaku lama tetap jalan.
    """
    guild_limit = int(usage.get("guild_limit") or 0)
    guild_used = int(usage.get("guild_used") or 0)
    guild_usage = (
        f"{guild_used} / {guild_limit}" if guild_limit else f"{guild_used} (tanpa batas)"
    )
    ai_ready = bool(status.get("ai_ready"))
    detik = int(refresh or 0)
    # refresh <= 0 = tanpa auto-refresh (lebih nyaman saat mengisi form panjang).
    # Saat ada kotak pesan, auto-refresh diarahkan ke alamat tanpa `pesan` supaya
    # notifikasinya hilang sendiri (dan tidak terkirim ulang tiap 30 detik).
    tujuan_refresh = (
        f";url={html.escape(alamat_bersih, quote=True)}" if flash_pesan and alamat_bersih else ""
    )
    meta_refresh = (
        f'<meta http-equiv="refresh" content="{max(5, detik)}{tujuan_refresh}">'
        if detik > 0
        else ""
    )
    # Angka besar lebih enak dibaca sebagai menit/jam: “600s · 10 menit”.
    petunjuk = f" · {_label_auto(detik)}" if detik >= 60 else ""
    refresh_info = (
        f" (🔄 auto-refresh {detik}s{petunjuk})" if detik > 0 else " (⏸ auto-refresh mati)"
    )
    auto_pilih = form_auto(auto_aksi, token, guild_id, detik, auto_dipilih)
    data = {
        "uptime": html.escape(str(status.get("uptime") or "-")),
        "ram_mb": status.get("ram_mb") or 0,
        "ping_ms": int(status.get("ping_ms") or 0),
        "guilds": int(status.get("guilds") or 0),
        "members": int(status.get("members") or 0),
        "ai_class": "ok" if ai_ready else "warn",
        "ai_label": "aktif" if ai_ready else "belum ada key",
        "total": int(usage.get("total") or 0),
        "date": html.escape(str(usage.get("date") or "-")),
        "tokens_in": int(usage.get("tokens_in") or 0),
        "tokens_out": int(usage.get("tokens_out") or 0),
        "cache_hits": int(usage.get("cache_hits") or 0),
        "faq_hits": int(usage.get("faq_hits") or 0),
        "guild_usage": html.escape(guild_usage),
        "cap_per_user": (
            f"{int(usage.get('cap_per_user') or 0)}/hari"
            if int(usage.get("cap_per_user") or 0)
            else "tanpa batas"
        ),
        "kinds_table": _rows_table(usage.get("kinds") or [], value_label="Operasi"),
        "channels_table": _rows_table(usage.get("channels") or [], value_label="Operasi"),
        "levels_table": _levels_table(levels),
        "kontrol_block": kontrol_block,
        "fitur_block": fitur_block,
        "setelan_block": setelan_block or '<div class="muted">Setelan tidak tersedia.</div>',
        "kirim_block": kirim_block,
        "buat_block": buat_block,
        "konten_block": konten_block,
        "audit_block": audit_block or '<div class="muted">Belum ada perubahan.</div>',
        "banner_block": banner_block or '<div class="muted">Unggahan tidak tersedia.</div>',
        "kartu_block": kartu_block or '<div class="muted">Kartu tidak tersedia.</div>',
        "honeypot_block": honeypot_block
        or '<div class="muted">Honeypot tidak tersedia.</div>',
        "aturan_block": aturan_block
        or '<div class="muted">Penguji aturan tidak tersedia.</div>',
        "starboard_block": starboard_block
        or '<div class="muted">Papan sorotan tidak tersedia.</div>',
        "kartu_rank_block": kartu_rank_block
        or '<div class="muted">Kartu rank tidak tersedia.</div>',
        "uji_block": uji_block or '<div class="muted">Tes fitur tidak tersedia.</div>',
        "setelan_welcome": setelan_welcome or '<div class="muted">Setelan tidak tersedia.</div>',
        "setelan_goodbye": setelan_goodbye or '<div class="muted">Setelan tidak tersedia.</div>',
        "setelan_boost": setelan_boost or '<div class="muted">Setelan tidak tersedia.</div>',
        "kartu_welcome": kartu_welcome or '<div class="muted">Kartu tidak tersedia.</div>',
        "kartu_goodbye": kartu_goodbye or '<div class="muted">Kartu tidak tersedia.</div>',
        "kartu_boost": kartu_boost or '<div class="muted">Kartu tidak tersedia.</div>',
        "uji_welcome": uji_welcome or '<div class="muted">Tes tidak tersedia.</div>',
        "uji_goodbye": uji_goodbye or '<div class="muted">Tes tidak tersedia.</div>',
        "uji_boost": uji_boost or '<div class="muted">Tes tidak tersedia.</div>',
        "ekspor_block": ekspor_block or '<div class="muted">Ekspor tidak tersedia.</div>',
        "panel_block": panel_block or '<div class="muted">Editor panel tidak tersedia.</div>',
        "tiket_block": tiket_block or '<div class="muted">Kotak masuk tiket tidak tersedia.</div>',
        "giveaway_block": giveaway_block or '<div class="muted">Kendali giveaway tidak tersedia.</div>',
        "arsip_block": arsip_block or '<div class="muted">Arsip transkrip tidak tersedia.</div>',
        "tren_block": tren_block or '<div class="muted">Belum ada data tren.</div>',
        "tren_hari": int(tren_hari or 7),
    }
    slug = halaman if halaman in HALAMAN_SLUG else ""
    if isi is not None:
        isi_halaman = isi
    elif halaman is None:
        isi_halaman = susun_isi_lengkap(data)   # mode lama: semua panel
    else:
        isi_halaman = susun_isi(slug, data)
    menu_html = menu or render_menu(slug, token, guild_id)
    if judul_halaman:
        heading_final = f"{judul_halaman} · {heading}" if heading else judul_halaman
    else:
        heading_final = heading

    return _PAGE_TEMPLATE.format(
        font_link=dashboard_tema.FONT_LINK,
        css=dashboard_tema.CSS_HALAMAN,
        refresh_info=refresh_info,
        auto_pilih=auto_pilih,
        meta_refresh=meta_refresh,
        version=html.escape(str(status.get("version") or "-")),
        bot_name=html.escape(str(status.get("bot_name") or "Bot")),
        heading=html.escape(heading_final),
        checked_at=html.escape(str(status.get("checked_at") or "-")),
        menu=menu_html,
        isi=isi_halaman,
        keterangan=html.escape(keterangan),
        guild_picker=guild_picker,
        flash=_flash_box(flash_pesan, flash_ok),
    )


# ==============================================================================
# KONTROL TULIS (v1.29.0-beta) — hanya lewat token dashboard
# ==============================================================================
LEVEL_OPTIONS = [("on", "Aktif"), ("off", "Nonaktif")]
FITUR_SEDERHANA = {
    "level": "Level & XP",
    "ekonomi": "Ekonomi koin",
    "tumbuh": "Pertumbuhan & invite",
}


def dashboard_controls(guild_id: int) -> dict:
    """Status ringkas fitur yang bisa dinyalakan/dimatikan dari dashboard."""
    import antinuke
    import antispam
    import economy
    import growth_tracker
    import levels

    gid = int(guild_id or 0)
    # Level dibaca lewat `is_leveling_active` (tidak membuat config default seperti
    # `get_level_config` — dulu itu membuat fitur menyala lagi setelah dimatikan).
    econ_cfg = economy.get_config(gid) if gid else {}
    growth_cfg = growth_tracker.get_config(gid) if gid else {}
    spam_cfg = antispam.get_spam_config(gid) if gid else {}
    nuke_cfg = antinuke.get_config(gid) if gid else {}

    return {
        "guild": gid,
        "level": "on" if levels.is_leveling_active(gid) else "off",
        "ekonomi": "on" if econ_cfg.get("enabled") else "off",
        "tumbuh": "on" if growth_cfg.get("enabled", True) else "off",
        "antispam": str(spam_cfg.get("mode")) if spam_cfg.get("enabled") else "off",
        "antinuke": str(nuke_cfg.get("action") or "lapor"),
    }


async def apply_dashboard_action(guild_id: int, action: str, value: str) -> tuple[bool, str]:
    """Menjalankan satu aksi tulis dari dashboard. `(berhasil, pesan)`."""
    import antinuke
    import antispam
    import economy
    import growth_tracker
    import levels

    gid = int(guild_id or 0)
    if not gid:
        return False, "Server tidak dikenali."
    act = str(action or "").strip().lower()
    val = str(value or "").strip().lower()

    if act == "level":
        if val not in ("on", "off"):
            return False, "Nilai level harus `on` atau `off`."
        setter = getattr(levels, "set_level_enabled", None)
        if callable(setter):
            setter(gid, val == "on")
        else:  # pragma: no cover - versi lama
            levels.set_level_config(gid, enabled=(val == "on"))
        await levels.save_levels_to_disk()
        return True, f"Level & XP sekarang **{'aktif' if val == 'on' else 'nonaktif'}**."

    if act == "ekonomi":
        if val not in ("on", "off"):
            return False, "Nilai ekonomi harus `on` atau `off`."
        economy.set_config(gid, aktif=(val == "on"))
        await economy.save_economy_to_disk()
        return True, f"Ekonomi koin sekarang **{'aktif' if val == 'on' else 'nonaktif'}**."

    if act == "tumbuh":
        if val not in ("on", "off"):
            return False, "Nilai pertumbuhan harus `on` atau `off`."
        growth_tracker.set_config(gid, enabled=(val == "on"))
        await growth_tracker.save_growth_to_disk()
        return True, f"Pelacakan pertumbuhan **{'aktif' if val == 'on' else 'nonaktif'}**."

    if act == "antispam":
        if val == "off":
            antispam.set_spam_config(gid, aktif=False)
            await antispam.save_antispam_to_disk()
            return True, "Anti-spam **dimatikan**."
        if val not in antispam.SPAM_MODES:
            return False, "Mode anti-spam tidak dikenal."
        antispam.set_spam_config(gid, mode=val)
        await antispam.save_antispam_to_disk()
        return True, f"Anti-spam aktif dengan mode **{val}**."

    if act == "antinuke":
        if val not in antinuke.PUNISH_CHOICES:
            return False, "Aksi anti-nuke tidak dikenal."
        antinuke.set_config(gid, action=val)
        await antinuke.save_antinuke_to_disk()
        return True, f"Anti-Nuke memakai aksi **{val}**."

    return False, f"Aksi `{act or '-'}` tidak didukung (hanya: level, ekonomi, tumbuh, antispam, antinuke)."


def render_controls_block(guild_id: int, token: str) -> str:
    """Saklar cepat: tombolnya mengikuti keadaan (Aktif → "Nonaktifkan")."""
    import antinuke
    import antispam

    state = dashboard_controls(guild_id)
    hidden = (
        f'<input type="hidden" name="token" value="{html.escape(token)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
    )

    def _saklar(action: str, label: str, aktif: bool) -> str:
        """Satu tombol: label menyebut aksi berikutnya, bukan keadaan sekarang."""
        tujuan = "off" if aktif else "on"
        teks = "Nonaktifkan" if aktif else "Aktifkan"
        kelas = ' class="danger"' if aktif else ""
        tanda = "✅" if aktif else "⬜"
        return (
            f'<form method="post" action="/api/aksi" class="kontrol">'
            f'{hidden}<input type="hidden" name="action" value="{action}">'
            f'<input type="hidden" name="value" value="{tujuan}">'
            f'<label>{tanda} {html.escape(label)} '
            f'<span class="muted">({"aktif" if aktif else "nonaktif"})</span></label>'
            f'<button type="submit"{kelas}>{teks}</button></form>'
        )

    def _pilih(action: str, label: str, options: list[tuple[str, str]], current: str) -> str:
        opts = "".join(
            f'<option value="{html.escape(value)}"'
            + (" selected" if value == current else "")
            + f'>{html.escape(text)}</option>'
            for value, text in options
        )
        return (
            f'<form method="post" action="/api/aksi" class="kontrol">'
            f'{hidden}<input type="hidden" name="action" value="{action}">'
            f'<label>{html.escape(label)}</label>'
            f'<select name="value">{opts}</select>'
            f'<button type="submit">Simpan</button></form>'
        )

    sp_options = [("off", "Mati")] + [(key, key.capitalize()) for key in antispam.SPAM_MODES]
    nuke_options = [(key, key) for key in antinuke.PUNISH_CHOICES]

    return "".join(
        [
            _saklar("level", "📈 Level & XP", state["level"] == "on"),
            _saklar("ekonomi", "💰 Ekonomi koin", state["ekonomi"] == "on"),
            _saklar("tumbuh", "🌱 Pertumbuhan & invite", state["tumbuh"] == "on"),
            _pilih("antispam", "🚨 Anti-spam", sp_options, state["antispam"]),
            _pilih("antinuke", "🛡️ Anti-Nuke (aksi)", nuke_options, state["antinuke"]),
        ]
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

    # Batas body dinaikkan supaya unggahan banner (DASHBOARD_UPLOAD_MB) bisa diterima.
    app = web.Application(client_max_size=dashboard_unggah.batas_byte() + (512 * 1024))

    def _authorized(request) -> bool:
        header = str(request.headers.get("X-Dashboard-Token") or "").strip()
        if not header:
            header = str(request.headers.get("Authorization") or "").strip()
        return is_authorized(
            query_token=str(request.query.get("token") or ""),
            header_token=header,
            expected=cfg["token"],
        )

    async def _payload(request) -> dict:
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

    def _galat_payload(payload: dict):
        """Balasan untuk body yang gagal dibaca (mis. unggahan kebesaran)."""
        pesan = str((payload or {}).get("__galat__") or "")
        if not pesan:
            return None
        logger.warning("Payload dashboard ditolak: %s", pesan)
        return _halaman_hasil(False, pesan)

    def _izin(request, payload: dict) -> bool:
        """Token boleh lewat query/header (API) atau field tersembunyi (form HTML)."""
        if _authorized(request):
            return True
        return is_authorized(
            query_token=str((payload or {}).get("token") or ""),
            expected=cfg["token"],
        )

    def _halaman_hasil(ok: bool, pesan: str, anchor: str = ""):
        """Halaman kecil untuk submit yang **gagal**: pesan jelas + tautan kembali.

        Submit yang berhasil tidak memakai halaman ini lagi — lihat `_kembali()`
        supaya pengguna langsung berada di panel yang sama dan melihat nilai baru.
        """
        token_url = html.escape(cfg["token"], quote=True)
        slug = halaman_dari_anchor(anchor)
        dasar = f"/{slug}" if slug else "/"
        tujuan = f"{dasar}?token={token_url}"
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

    def _kembali(gid: int, pesan: str, anchor: str, ok: bool = True):
        """303 kembali ke panel yang sama + kotak pesan (POST → redirect → GET)."""
        from urllib.parse import urlencode

        kueri = urlencode(
            {
                "token": cfg["token"],
                "guild": int(gid or 0),
                "pesan": str(pesan or "")[:500],
                "ok": "1" if ok else "0",
            }
        )
        slug = halaman_dari_anchor(anchor)
        tujuan = f"/{slug}?{kueri}" if slug else f"/?{kueri}"
        if anchor:
            tujuan += f"#{anchor}"
        return web.Response(status=303, headers={"Location": tujuan})

    def _jawab(gid: int, ok: bool, pesan: str, anchor: str, request):
        """JSON untuk otomasi; form HTML selalu kembali ke panelnya (✅ atau ⚠️).

        Gagal pun tetap redirect: pengguna mendarat di halaman fiturnya dengan
        kotak pesan yang jelas, bukan halaman buntu tanpa jalan pulang.
        """
        if str(request.content_type or "").startswith("application/json"):
            return web.json_response(
                {"ok": ok, "message": pesan, "guild": gid}, status=200 if ok else 400
            )
        return _kembali(gid, pesan, anchor, ok=ok)

    async def handle_health(_request):
        return web.Response(text="ok", content_type="text/plain")

    async def handle_index(request):
        if not _authorized(request):
            return web.Response(text="401 Unauthorized — tambahkan ?token=...", status=401)
        gid, guild_name = _guild_hint(bot, request)
        token = cfg["token"]
        flash_pesan = str(request.query.get("pesan") or "")[:300]
        flash_ok = str(request.query.get("ok") or "1") != "0"

        # 🔄 Atur auto-refresh dari header (tanpa JavaScript, tanpa .env).
        # Dropdown `?refresh=600` atau angka bebas `?refresh_detik=45` → cookie;
        # `?refresh=auto` (atau kosong) → hapus cookie, ikut DASHBOARD_REFRESH_SEC.
        if "refresh" in request.query or FIELD_AUTO_MANUAL in request.query:
            nilai = detik_dari_kueri(request.query)
            balik = url_halaman(halaman_dari_path(request.path), token, gid)
            if nilai == "manual":
                # “✏️ Isi sendiri…” dipilih tapi angkanya belum diisi: tampilkan
                # kotak angka (tanpa mengubah nilai yang sedang berlaku).
                return web.Response(status=303, headers={"Location": balik + "&isi=1"})
            jawab = web.Response(status=303, headers={"Location": balik})
            if nilai == "auto":
                jawab.del_cookie(COOKIE_AUTO, path="/")
            else:
                jawab.set_cookie(
                    COOKIE_AUTO, nilai,
                    max_age=COOKIE_AUTO_MAKS, path="/", httponly=True, samesite="Lax",
                )
            return jawab

        # Bookmark lama berbentuk `/?halaman=setelan` atau `/uji` diarahkan ke halaman barunya.
        pinta = str(request.query.get("halaman") or "").strip()
        lama = request.path.strip("/")
        if lama in LEGACY_HALAMAN and not pinta:
            tujuan = url_halaman(LEGACY_HALAMAN[lama], token, gid)
            return web.Response(status=303, headers={"Location": tujuan})
        if pinta in LEGACY_HALAMAN:
            tujuan = url_halaman(LEGACY_HALAMAN[pinta], token, gid)
            return web.Response(status=303, headers={"Location": tujuan})
        if pinta and pinta in HALAMAN_SLUG and request.path.strip("/") != pinta:
            return web.Response(status=303, headers={
                "Location": url_halaman(pinta, token, gid)
            })

        slug = halaman_dari_path(request.path)
        halaman_meta = HALAMAN_SLUG[slug]

        # Interval yang benar-benar dipakai: cookie (kalau ada) lalu
        # `DASHBOARD_REFRESH_SEC`. Dropdown di header menampilkan yang aktif.
        simpan_auto = str(request.cookies.get(COOKIE_AUTO) or "").strip()
        detik = detik_auto(request, cfg["refresh"])
        pilih_auto = simpan_auto if simpan_auto.isdigit() else "auto"
        if str(request.query.get("isi") or "").strip() == "1":
            pilih_auto = "manual"        # mode “✏️ Isi sendiri…” dibuka

        def _blok(pembuat, bawaan: str) -> str:
            """Gambar satu blok; kegagalan satu blok tidak mematikan halaman."""
            try:
                return pembuat()
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Blok dashboard gagal dirender: %s", exc)
                return bawaan

        try:
            nilai = dashboard_admin.read_values(gid)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Nilai setelan gagal dibaca: %s", exc)
            nilai = {}

        def _setelan(kunci: tuple[str, ...]) -> str:
            return _blok(
                lambda: dashboard_ui.render_setelan_block(
                    nilai, bot, gid, token, hanya=kunci
                ),
                '<div class="muted">Setelan tidak tersedia.</div>',
            )

        def _kartu(jenis: str) -> str:
            return _blok(
                lambda: dashboard_ui.render_kartu_block(gid, token, hanya=(jenis,)),
                '<div class="muted">Kartu tidak tersedia.</div>',
            )

        def _uji(*kunci: str) -> str:
            return _blok(
                lambda: dashboard_ui.render_uji_block(bot, gid, token, hanya=kunci),
                '<div class="muted">Tes fitur tidak tersedia.</div>',
            )

        # Halaman sambutan: tiga bagian, satu halaman.
        setelan_welcome = _setelan(SETELAN_SAMBUTAN) if slug == "sambutan" else ""
        setelan_goodbye = _setelan(SETELAN_PERPISAHAN) if slug == "sambutan" else ""
        setelan_boost = _setelan(SETELAN_BOOST) if slug == "sambutan" else ""
        kartu_welcome = _kartu("welcome") if slug == "sambutan" else ""
        kartu_goodbye = _kartu("goodbye") if slug == "sambutan" else ""
        kartu_boost = _kartu("boost") if slug == "sambutan" else ""
        uji_welcome = _uji("welcome") if slug == "sambutan" else ""
        uji_goodbye = _uji("goodbye") if slug == "sambutan" else ""
        uji_boost = _uji("boost") if slug == "sambutan" else ""
        kartu_block = ""
        uji_block = _uji(*UJI_HALAMAN.get(slug, ()))
        grup_slug = {v: k for k, v in GRUP_HALAMAN.items()}.get(slug)
        setelan_block = _setelan(fitur_grup(grup_slug)) if grup_slug else ""
        kirim_block = _blok(
            lambda: dashboard_ui.render_kirim_block(bot, gid, token),
            '<div class="muted">Form kirim tidak tersedia.</div>',
        )
        buat_block = _blok(
            lambda: dashboard_ui.render_buat_block(bot, gid, token),
            '<div class="muted">Form konten tidak tersedia.</div>',
        )
        konten_block = _blok(
            lambda: dashboard_ui.render_konten_block(
                gid, dashboard_pesan.daftar_konten(gid, bot), token
            ),
            '<div class="muted">Daftar konten tidak tersedia.</div>',
        )
        tiket_block = _blok(
            lambda: dashboard_ui.render_tiket_block(
                gid, dashboard_tiket.collect_tiket(gid), token, bot
            ),
            '<div class="muted">Kotak masuk tiket tidak tersedia.</div>',
        )
        arsip_block = _blok(
            lambda: dashboard_ui.render_arsip_block(
                gid, token, ticket_archive.statistik(gid), ticket_archive.daftar(gid, limit=5)
            ),
            '<div class="muted">Arsip transkrip tidak tersedia.</div>',
        )
        kartu_rank_block = _blok(
            lambda: dashboard_ui.render_kartu_rank_block(bot, gid, token),
            '<div class="muted">Kartu rank tidak tersedia.</div>',
        )
        honeypot_block = _blok(
            lambda: dashboard_ui.render_honeypot_block(bot, gid, token),
            '<div class="muted">Honeypot tidak tersedia.</div>',
        )
        aturan_block = _blok(
            lambda: dashboard_ui.render_aturan_block(
                gid, token, dashboard_keamanan.collect(gid)
            ),
            '<div class="muted">Penguji aturan tidak tersedia.</div>',
        )
        starboard_block = _blok(
            lambda: dashboard_ui.render_starboard_block(bot, gid, token),
            '<div class="muted">Papan sorotan tidak tersedia.</div>',
        )
        giveaway_block = _blok(
            lambda: dashboard_ui.render_giveaway_block(
                gid, dashboard_giveaway.collect(gid), token, bot
            ),
            '<div class="muted">Kendali giveaway tidak tersedia.</div>',
        )
        ekspor_block = _blok(
            lambda: dashboard_ui.render_ekspor_block(gid, token),
            '<div class="muted">Ekspor tidak tersedia.</div>',
        )
        panel_block = _blok(
            lambda: dashboard_ui.render_panel_block(
                bot, gid, dashboard_panel.collect_panel(gid), token
            ),
            '<div class="muted">Editor panel tidak tersedia.</div>',
        )
        banner_block = _blok(
            lambda: dashboard_ui.render_banner_block(gid, token),
            '<div class="muted">Unggahan tidak tersedia.</div>',
        )
        audit_block = _blok(
            lambda: dashboard_ui.render_audit_block(dashboard_admin.audit_terakhir(gid, limit=8)),
            '<div class="muted">Riwayat tidak tersedia.</div>',
        )

        guild_picker = _blok(
            lambda: dashboard_ui.render_guild_picker(bot, gid, token, halaman=slug),
            "",
        )
        tren = collect_tren(7)
        tren_block = _blok(
            lambda: dashboard_ui.render_tren_svg(tren["rows"], judul="Operasi AI"),
            '<div class="muted">Belum ada data tren.</div>',
        )

        page = render_dashboard_html(
            status=collect_status(bot),
            usage=collect_usage(gid),
            levels=collect_levels(gid),
            refresh=detik,
            auto_aksi=f"/{slug}" if slug else "/",
            auto_dipilih=pilih_auto,
            heading=guild_name or "Bot",
            kontrol_block=render_controls_block(gid, token),
            fitur_block=render_features_block(gid),
            setelan_block=setelan_block,
            kirim_block=kirim_block,
            buat_block=buat_block,
            konten_block=konten_block,
            audit_block=audit_block,
            banner_block=banner_block,
            kartu_block=kartu_block,
            kartu_rank_block=kartu_rank_block,
            starboard_block=starboard_block,
            aturan_block=aturan_block,
            honeypot_block=honeypot_block,
            uji_block=uji_block,
            setelan_welcome=setelan_welcome,
            setelan_goodbye=setelan_goodbye,
            setelan_boost=setelan_boost,
            kartu_welcome=kartu_welcome,
            kartu_goodbye=kartu_goodbye,
            kartu_boost=kartu_boost,
            uji_welcome=uji_welcome,
            uji_goodbye=uji_goodbye,
            uji_boost=uji_boost,
            guild_picker=guild_picker,
            flash_pesan=flash_pesan,
            flash_ok=flash_ok,
            alamat_bersih=url_halaman(slug, token, gid),
            ekspor_block=ekspor_block,
            panel_block=panel_block,
            tiket_block=tiket_block,
            giveaway_block=giveaway_block,
            arsip_block=arsip_block,
            tren_block=tren_block,
            tren_hari=tren["hari"],
            halaman=slug,
            token=token,
            guild_id=gid,
            judul_halaman=halaman_meta["judul"],
            keterangan=halaman_meta["keterangan"],
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

    async def handle_kontrol(request):
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, guild_name = _guild_hint(bot, request)
        return web.json_response({"guild": gid, "guild_name": guild_name,
                                  "controls": dashboard_controls(gid)})

    async def handle_aksi(request):
        """Ubah setelan. Body JSON atau form HTML (token boleh di body)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip()
        nilai = str(payload.get("value") or "")

        if aksi.lower().startswith("set."):
            kunci = aksi[4:]
            ok, message = await dashboard_admin.apply(gid, kunci, dashboard_admin.normalisasi(kunci, nilai))
        else:
            ok, message = await apply_dashboard_action(gid, aksi, nilai)
        logger.info("Dashboard aksi %s=%s (server %s): %s", aksi, nilai, gid, message)
        return _jawab(gid, ok, message, _anchor_aksi(aksi), request)

    async def handle_kirim(request):
        """Kirim pesan/embed ke channel (opsional lewat identitas webhook)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        banner, galat_banner, nama_banner = dashboard_unggah.siapkan(
            gid, payload.get("banner"), str(payload.get("banner_tersimpan") or "")
        )
        if galat_banner:
            return _kembali(gid, galat_banner, "p-kirim", ok=False)

        # Tombol "Pratinjau" (name=pratinjau) menampilkan hasil tanpa mengirim.
        if str(payload.get("pratinjau") or "").strip():
            data = dashboard_pesan.pratinjau(bot, gid, payload, banner=banner)
            logger.info("Dashboard pratinjau embed (server %s) ke %s", gid, data.get("channel_label"))
            if str(request.content_type or "").startswith("application/json"):
                return web.json_response({"ok": True, "pratinjau": data, "guild": gid})
            isian = {k: str(v) for k, v in payload.items() if k not in ("token", "pratinjau")}
            isian["token"] = cfg["token"]
            isian["guild"] = str(gid)
            isian["action"] = "kirim"
            if nama_banner:
                isian["banner_tersimpan"] = nama_banner
            halaman = dashboard_ui.render_pratinjau_html(
                pratinjau=data, token=cfg["token"], guild_id=gid, fields=isian
            )
            return web.Response(text=halaman, content_type="text/html", charset="utf-8")

        ok, message = await dashboard_pesan.kirim(bot, gid, payload, banner=banner)
        logger.info("Dashboard kirim (server %s): %s", gid, message)
        return _jawab(gid, ok, message, "p-kirim", request)

    async def handle_konten(request):
        """Buat / hapus konten: `action=buat.<jenis>` atau `hapus.<jenis>:<id>`."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()

        if aksi == "buat.pengumuman":
            ok, message = await dashboard_pesan.tambah_pengumuman(gid, payload)
        elif aksi == "buat.tautan":
            ok, message = await dashboard_pesan.tambah_tautan(gid, payload)
        elif aksi == "buat.panel":
            banner, galat_banner, _nama = dashboard_unggah.siapkan(
                gid, payload.get("banner"), str(payload.get("banner_tersimpan") or "")
            )
            if galat_banner:
                return _kembali(gid, galat_banner, "p-buat", ok=False)
            ok, message = await dashboard_pesan.buat_panel(bot, gid, payload, banner=banner)
        elif aksi == "buat.formulir":
            ok, message = await dashboard_pesan.tambah_formulir(gid, payload)
        elif aksi == "buat.pemicu":
            ok, message = await dashboard_pesan.pasang_pemicu(gid, payload)
        elif aksi.startswith("jeda."):
            sisa = aksi[len("jeda."):]
            jenis, _, ref = sisa.partition(":")
            if jenis == "pengumuman":
                import engagement

                data_pengumuman = engagement.announcements.get(int(ref)) if ref.isdigit() else None
                if data_pengumuman is None:
                    ok, message = False, "Pengumuman tidak ditemukan."
                else:
                    ok, message = await dashboard_pesan.ubah_pengumuman(
                        gid, int(ref), not bool(data_pengumuman.get("enabled", True))
                    )
            else:
                ok, message = False, f"Jenis `{jenis or '-'}` tidak bisa dijeda."
        elif aksi == "starboard-tambah":
            import community_tools

            ok, message = community_tools.add_starboard_board(
                gid,
                str(payload.get("nama") or ""),
                emoji=str(payload.get("emoji") or ""),
                threshold=_id_aman(payload.get("batas")),
                channel_id=_id_aman(payload.get("channel_id")),
                warna=str(payload.get("warna") or ""),
            )
            if ok:
                await community_tools.save_community_tools_to_disk()
        elif aksi.startswith("starboard-hapus:"):
            import community_tools

            ok, message = community_tools.remove_starboard_board(
                gid, aksi.split(":", 1)[1]
            )
            if ok:
                await community_tools.save_community_tools_to_disk()
        elif aksi.startswith(("banner.panel:", "hapusbanner.panel:")):
            ref_panel = aksi.split(":", 1)[1]
            if aksi.startswith("hapusbanner."):
                ok, message = await dashboard_pesan.ganti_banner_panel(
                    bot, gid, ref_panel, banner=None
                )
            else:
                banner, galat_banner, _nama = dashboard_unggah.siapkan(
                    gid, payload.get("banner"), str(payload.get("banner_tersimpan") or "")
                )
                if galat_banner:
                    return _kembali(gid, galat_banner, "p-panel", ok=False)
                if banner is None:
                    return _kembali(
                        gid, "Pilih berkas banner atau banner tersimpan lebih dulu.",
                        "p-panel", ok=False,
                    )
                ok, message = await dashboard_pesan.ganti_banner_panel(
                    bot, gid, ref_panel, banner=banner
                )
        elif aksi.startswith("hapus."):
            sisa = aksi[len("hapus."):]
            jenis, _, ref = sisa.partition(":")
            ok, message = await dashboard_pesan.hapus(bot, gid, jenis, ref)
        else:
            ok, message = False, f"Aksi konten `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard konten %s (server %s): %s", aksi, gid, message)
        return _jawab(gid, ok, message, _anchor_konten(aksi), request)

    async def handle_panel(request):
        """Editor panel: daftar item (GET) atau tambah/hapus item (POST)."""
        if request.method == "GET":
            if not _authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(bot, request)
            return web.json_response(dashboard_panel.collect_panel(gid))

        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        jenis, _, ref = aksi.partition(":")

        if jenis == "tambah":
            ok, message = await dashboard_panel.tambah_item(
                bot, gid, {**payload, "panel": ref}
            )
        elif jenis == "verifikasi" and ref.strip().lower() == "matikan":
            ok, message = await dashboard_panel.matikan_verifikasi(gid)
        elif jenis == "verifikasi":
            ok, message = await dashboard_panel.pasang_verifikasi(bot, gid, payload)
        elif jenis == "hapus":
            panel_id, _, item_ref = ref.partition(":")
            ok, message = await dashboard_panel.hapus_item(
                bot, gid, {**payload, "panel": panel_id, "item": item_ref}
            )
        else:
            ok, message = False, f"Aksi panel `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard panel %s (server %s): %s", aksi, gid, message)
        return _jawab(gid, ok, message, "p-panel", request)

    async def _simpan_tiket() -> None:
        """Simpan perubahan konfigurasi tiket (topik) ke `data/tickets.json`."""
        import tickets

        try:
            await tickets.save_tickets_to_disk()
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan konfigurasi tiket: %s", exc)

    async def handle_keamanan(request):
        """POST penguji aturan anti-spam (tanpa menindak apa pun)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()

        if aksi == "honeypot-simpan":
            import honeypot

            cid = _id_aman(payload.get("channel_id"))
            lama = honeypot.status(gid)
            ids = list(lama["channel_ids"])
            if cid and cid not in ids:
                ids.append(cid)
            ok, message = True, ""
            honeypot.set_honeypot(
                gid,
                channel_ids=ids,
                aksi=str(payload.get("aksi") or ""),
                timeout_sec=_id_aman(payload.get("timeout_sec")) or None,
                log_channel_id=_id_aman(payload.get("log_channel_id")),
                abaikan_staf=str(payload.get("abaikan_staf") or "1") not in ("0", "false", "off"),
            )
            await honeypot.save_honeypot_to_disk()
            data = honeypot.status(gid)
            message = (
                f"Honeypot disimpan: channel {', '.join(f'#{c}' for c in data['channel_ids'])} · "
                f"tindakan {data['label_aksi']}."
                if data["channel_ids"]
                else "Honeypot disimpan, tapi belum ada channel jebakan yang dipilih."
            )
        elif aksi == "honeypot-hapus":
            import honeypot

            ok = honeypot.clear_honeypot(gid)
            if ok:
                await honeypot.save_honeypot_to_disk()
            message = (
                "Honeypot dimatikan & setelannya dihapus."
                if ok
                else "Belum ada setelan honeypot untuk dihapus."
            )
        elif aksi == "uji-aturan":
            ok, message = dashboard_keamanan.uji(
                gid, str(payload.get("teks") or ""), ulang=_id_aman(payload.get("ulang"))
            )
        else:
            ok, message = False, f"Aksi keamanan `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard keamanan %s (server %s): %s", aksi, gid, message)
        return _jawab(gid, ok, message, "p-aturan", request)

    async def handle_tiket(request):
        """Kotak masuk tiket: daftar (GET) atau balas/tutup (POST)."""
        if request.method == "GET":
            if not _authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(bot, request)
            return web.json_response(dashboard_tiket.collect_tiket(gid))

        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        jenis, _, ref = aksi.partition(":")

        if jenis == "balas":
            ok, message = await dashboard_tiket.balas(
                bot, gid, ref, str(payload.get("teks") or ""),
                identitas=str(payload.get("identitas") or ""),
            )
        elif jenis == "tutup":
            ok, message = await dashboard_tiket.tutup(bot, gid, ref)
        elif jenis == "topik-tambah":
            ok, message = dashboard_tiket.topik_tambah(
                gid,
                str(payload.get("nama") or ""),
                role_id=_id_aman(payload.get("role_id")),
                emoji=str(payload.get("emoji") or ""),
                deskripsi=str(payload.get("deskripsi") or ""),
            )
            if ok:
                await _simpan_tiket()
        elif jenis == "topik-hapus":
            ok, message = dashboard_tiket.topik_hapus(gid, str(payload.get("nama") or ""))
            if ok:
                await _simpan_tiket()
        elif jenis == "catat":
            ok, message = dashboard_tiket.catat(
                gid, _id_aman(ref), str(payload.get("teks") or "")
            )
        elif jenis == "catatan-hapus":
            tid_str, _, nomor = ref.partition(":")
            ok, message = dashboard_tiket.hapus_catatan(gid, _id_aman(tid_str), _id_aman(nomor))
        elif jenis == "panel":
            ok, message = await dashboard_tiket.pasang_panel(bot, gid, payload)
        elif jenis == "matikan":
            ok, message = await dashboard_tiket.matikan_tiket(gid)
        else:
            ok, message = False, f"Aksi tiket `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard tiket %s (server %s): %s", aksi, gid, message)
        return _jawab(gid, ok, message, "p-tiket", request)

    async def handle_transkrip(request):
        """Halaman arsip transkrip tiket + pencarian (tanpa JavaScript)."""
        if not _authorized(request):
            return web.Response(
                text="401 Unauthorized — tambahkan ?token=...", status=401
            )
        gid, guild_name = _guild_hint(bot, request)
        kata = str(request.query.get("q") or "").strip()[:80]
        hasil = (
            ticket_archive.cari(gid, kata, limit=30)
            if kata
            else ticket_archive.daftar(gid, limit=30)
        )
        page = dashboard_ui.render_halaman_arsip(
            gid,
            cfg["token"],
            kata=kata,
            hasil=hasil,
            stat=ticket_archive.statistik(gid),
            nama_server=guild_name,
        )
        return web.Response(
            text=page,
            content_type="text/html",
            charset="utf-8",
            headers={"X-Robots-Tag": "noindex"},
        )

    async def handle_transkrip_berkas(request):
        """Berkas transkrip HTML satu tiket (GET) atau hapus arsip (POST)."""
        if request.method == "GET":
            if not _authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(bot, request)
            kode = str(request.query.get("kode") or "").strip()
            isi = ticket_archive.baca_html(gid, kode)
            if isi is None:
                return web.Response(
                    text="Arsip transkrip tidak ditemukan (mungkin sudah dihapus).",
                    status=404,
                    content_type="text/plain",
                    charset="utf-8",
                )
            return web.Response(
                text=isi,
                content_type="text/html",
                charset="utf-8",
                headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"},
            )

        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        if aksi == "hapus":
            ok = ticket_archive.hapus(gid, str(payload.get("kode") or "").strip())
            pesan = (
                f"Arsip transkrip #{payload.get('kode')} dihapus."
                if ok
                else "Arsip transkrip itu tidak ditemukan."
            )
        else:
            ok, pesan = False, f"Aksi arsip `{aksi or '-'}` tidak dikenal."
        try:
            await dashboard_admin.audit_append(
                gid, f"transkrip.{aksi or '-'}", str(payload.get("kode") or "")[:40],
                ok=ok, pesan=pesan,
            )
        except Exception:  # pragma: no cover - audit opsional
            pass
        logger.info("Dashboard transkrip %s (server %s): %s", aksi, gid, pesan)
        return _jawab(gid, ok, pesan, "p-tiket", request)

    async def handle_giveaway(request):
        """Kendali giveaway: daftar (GET) atau aksi buat/akhiri/reroll/template (POST)."""
        if request.method == "GET":
            if not _authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(bot, request)
            return web.json_response(dashboard_giveaway.collect(gid))

        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        try:
            ok, pesan = await dashboard_giveaway.aksi(bot, gid, aksi, payload)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Aksi giveaway gagal: %s", exc)
            ok, pesan = False, "Aksi giveaway gagal dijalankan."

        nama_aksi = aksi.partition(":")[0] or "-"
        try:
            await dashboard_admin.audit_append(
                gid,
                f"giveaway.{nama_aksi}",
                str(payload.get("hadiah") or payload.get("nama") or aksi)[:120],
                ok=ok,
                pesan=pesan,
            )
        except Exception:  # pragma: no cover - audit opsional
            pass
        logger.info("Dashboard giveaway %s (server %s): %s", aksi, gid, pesan)
        return _jawab(gid, ok, pesan, "p-giveaway", request)

    async def handle_ekspor(request):
        """Unduh CSV analitik server (level/moderasi/tiket/pemakaian)."""
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        import analytics_export

        gid, _name = _guild_hint(bot, request)
        jenis = str(request.query.get("jenis") or "level").strip().lower()
        isi, nama_berkas, galat = analytics_export.build_csv(jenis, gid)
        if isi is None:
            return web.Response(
                text=galat or "Data belum tersedia.", status=404,
                content_type="text/plain", charset="utf-8",
            )
        return web.Response(
            body=analytics_export.csv_bytes(isi),
            content_type="text/csv",
            charset="utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nama_berkas}"'},
        )

    async def handle_unggah(request):
        """Simpan / hapus banner. Multipart untuk berkas, form biasa untuk hapus."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()

        if aksi == "unggah.simpan":
            berkas, galat, nama = dashboard_unggah.siapkan(gid, payload.get("banner"))
            if galat:
                ok, message = False, galat
            elif not nama:
                ok, message = False, "Pilih berkas gambar lebih dulu."
            else:
                ok, message = True, f"Banner tersimpan: `{nama}`."
        elif aksi.startswith("kartu.simpan:"):
            ok, message = dashboard_unggah.simpan_kartu(
                gid, payload.get("banner"), aksi.split(":", 1)[1]
            )
        elif aksi.startswith("kartu.hapus:"):
            ok, message = dashboard_unggah.hapus_kartu(gid, aksi.split(":", 1)[1])
        elif aksi.startswith("hapus.banner:"):
            nama = aksi.split(":", 1)[1]
            ok = dashboard_unggah.hapus(gid, nama)
            message = f"Banner `{nama}` dihapus." if ok else "Banner tidak ditemukan."
        else:
            ok, message = False, f"Aksi unggah `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard unggah %s (server %s): %s", aksi, gid, message)
        anchor = "p-banner"
        if aksi.startswith("kartu."):
            jenis = aksi.split(":", 1)[1] if ":" in aksi else ""
            anchor = {
                "welcome": "p-sambutan",
                "goodbye": "p-perpisahan",
                "boost": "p-boost",
            }.get(jenis, "p-sambutan")
        return _jawab(gid, ok, message, anchor, request)

    async def handle_uji(request):
        """Jalankan satu tes fitur. Subjek tes opsional — default pemilik server."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await _payload(request)
        galat_body = _galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not _izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        kunci = aksi.split(":", 1)[1].strip() if ":" in aksi else aksi.removeprefix("uji.").strip()
        opsi = str(
            payload.get("opsi_manual") or payload.get("opsi") or payload.get("member") or ""
        ).strip()
        ok, message = await dashboard_uji.jalankan_uji(bot, gid, kunci, None, opsi)
        logger.info("Dashboard uji %s (server %s): %s", kunci, gid, message)
        anchor = dashboard_uji.ANCHOR_UJI.get(str(kunci).strip().lower(), "p-kontrol")
        return _jawab(gid, ok, message, anchor, request)

    async def handle_kartu(request):
        """Sajikan gambar kartu sambutan tersimpan (pratinjau di dashboard)."""
        if not _authorized(request):
            return web.Response(text="401 Unauthorized", status=401)
        jenis = str(request.match_info.get("jenis") or "")
        gid, _nama = _guild_hint(bot, request)
        isi, tipe = dashboard_unggah.baca_kartu(gid, jenis)
        if isi is None:
            return web.Response(text="404 Not Found", status=404)
        return web.Response(
            body=isi,
            content_type=tipe,
            headers={"Cache-Control": "private, max-age=60"},
        )

    async def handle_rank_png(request):
        """Kartu rank PNG untuk pratinjau dashboard (perender sama dengan /level kartu)."""
        if not _authorized(request):
            return web.Response(text="401 Unauthorized", status=401)

        import rank_card

        gid, _nama = _guild_hint(bot, request)
        member = _id_aman(request.query.get("member"))
        guild = None
        getter = getattr(bot, "get_guild", None)
        if callable(getter):
            guild = getter(gid)
        if not member and guild is not None:
            member = int(getattr(guild, "owner_id", 0) or 0)

        nama = "Member"
        avatar = None
        orang = None
        cari = getattr(guild, "get_member", None) if guild is not None else None
        if callable(cari) and member:
            try:
                orang = cari(member)
            except Exception:  # pragma: no cover - jaring aman
                orang = None
        if orang is not None:
            nama = getattr(orang, "display_name", "") or getattr(orang, "name", "") or nama
            avatar = await rank_card.baca_avatar(orang)

        data = rank_card.data_kartu(
            gid,
            member,
            nama=nama,
            guild_name=str(getattr(guild, "name", "") or ""),
        )
        isi = await rank_card.render_kartu(data, avatar_bytes=avatar)
        if not isi:
            return web.Response(
                text="Kartu rank tidak bisa dirender (Pillow tidak tersedia atau dimatikan).",
                status=503,
                content_type="text/plain",
            )
        unduh = str(request.query.get("unduh") or "") in ("1", "true", "ya")
        header = {
            "Cache-Control": "no-store",
            "Content-Disposition": (
                f'attachment; filename="kartu-rank-{member or 0}.png"'
                if unduh
                else f'inline; filename="kartu-rank-{member or 0}.png"'
            ),
        }
        return web.Response(body=isi, content_type="image/png", headers=header)

    async def handle_berkas(request):
        """Sajikan banner tersimpan untuk pratinjau di halaman dashboard."""
        if not _authorized(request):
            return web.Response(text="401 Unauthorized", status=401)
        nama = str(request.match_info.get("nama") or "")
        gid, _name = _guild_hint(bot, request)
        if not dashboard_unggah.berkuasa(gid, nama):
            return web.Response(text="404 Not Found", status=404)
        isi = dashboard_unggah.baca(gid, nama)
        if isi is None:
            return web.Response(text="404 Not Found", status=404)
        return web.Response(
            body=isi,
            content_type=dashboard_unggah.tipe(nama),
            headers={"Cache-Control": "private, max-age=300"},
        )

    async def handle_tren(request):
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(collect_tren(int(request.query.get("hari") or 7)))

    async def handle_setelan(request):
        """JSON semua setelan + nilai sekarang (untuk otomasi/tes)."""
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, guild_name = _guild_hint(bot, request)
        return web.json_response(
            {
                "guild": gid,
                "guild_name": guild_name,
                "ringkasan": dashboard_admin.ringkasan(),
                "nilai": dashboard_admin.read_values(gid),
                "riwayat": dashboard_admin.audit_terakhir(gid, limit=10),
            }
        )

    app.router.add_get("/api/kontrol", handle_kontrol)

    async def handle_features(request):
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, _name = _guild_hint(bot, request)
        return web.json_response(collect_features(gid))

    app.router.add_get("/api/fitur", handle_features)
    app.router.add_get("/api/setelan", handle_setelan)
    app.router.add_get("/api/tren", handle_tren)
    app.router.add_post("/api/aksi", handle_aksi)
    app.router.add_post("/api/kirim", handle_kirim)
    app.router.add_post("/api/konten", handle_konten)
    app.router.add_post("/api/unggah", handle_unggah)
    app.router.add_post("/api/uji", handle_uji)
    app.router.add_get("/api/kartu/{jenis}", handle_kartu)
    app.router.add_get("/api/rank.png", handle_rank_png)
    app.router.add_get("/api/ekspor", handle_ekspor)
    app.router.add_get("/api/panel", handle_panel)
    app.router.add_post("/api/panel", handle_panel)
    app.router.add_get("/api/tiket", handle_tiket)
    app.router.add_post("/api/tiket", handle_tiket)
    app.router.add_post("/api/keamanan", handle_keamanan)
    app.router.add_get("/api/giveaway", handle_giveaway)
    app.router.add_post("/api/giveaway", handle_giveaway)
    app.router.add_get("/transkrip", handle_transkrip)
    app.router.add_get("/api/transkrip", handle_transkrip_berkas)
    app.router.add_post("/api/transkrip", handle_transkrip_berkas)
    app.router.add_get("/api/unggahan/{nama}", handle_berkas)
    app.router.add_get("/", handle_index)
    for _lama in LEGACY_HALAMAN:
        app.router.add_get(f"/{_lama}", handle_index)
    for _halaman in HALAMAN:
        if _halaman["slug"]:
            app.router.add_get(f"/{_halaman['slug']}", handle_index)
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
            "🛰️ Dashboard web aktif di http://%s:%s/?token=*** "
            "(%s setelan, kirim embed/webhook, 0 kuota AI)",
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
