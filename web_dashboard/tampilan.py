"""Perakitan HTML dashboard: template halaman, panel per fitur, dan blok kontrol.

Dipisah dari `web_dashboard` (inti) karena bagian ini hanya berurusan dengan
potongan HTML — tidak menyentuh request, sesi, maupun router. Semua fungsi di
sini memakai data yang sudah dikumpulkan pemanggilnya, jadi bisa diuji dengan
dict biasa tanpa menyalakan server.
"""

from __future__ import annotations

import html

import dashboard_tema
from web_dashboard.halaman import (
    BAGIAN_SAMBUTAN,
    HALAMAN_SLUG,
    _flash_box,
    _label_auto,
    form_auto,
    render_menu,
)


def _label_tes(blok: str) -> str:
    """Beri judul kecil di atas tombol tes (kalau blok tesnya ada)."""
    if not blok:
        return ""
    return f'<div class="kepala-tes"><b>🧪 Tes fitur</b></div>{blok}'


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
  <aside class="topbar" aria-label="Navigasi dashboard">
    <input type="checkbox" id="nav-buka" class="nav-buka" aria-label="Tampilkan menu dashboard">
    <div class="brand-row">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">✦</span>
        <span class="brand-copy"><span class="brand-name">Dashboard Bot</span>
          <span class="brand-caption">PUSAT KONTROL</span></span>
      </div>
      <label class="menu-btn" for="nav-buka">☰ Menu</label>
    </div>
    <div class="server-context">
      <span class="server-context-label">Server aktif</span>
      <span class="judul">{heading}</span>
      <span class="meta">v{version} · {checked_at}{refresh_info}</span>
    </div>
    {menu}
    <div class="sidebar-controls">{guild_picker}{auto_pilih}</div>
  </aside>
  <main class="workspace">
    <header class="page-heading">
      <div class="page-eyebrow">Ruang kerja · Discord</div>
      <h1>{page_title}</h1>
      <p class="keterangan-halaman">{keterangan}</p>
    </header>
    {flash}

{isi}

    <footer class="muted">
      Data dibaca dari JSON lokal bot. Kontrol di sini hanya mengubah setelan fitur (bukan menghapus data).
      Rahasiakan tautan ini — siapa pun yang punya token bisa mengubah setelan.
    </footer>
  </main>
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
def _panel_gambar(d: dict) -> str:
    return (
        '<div class="panel" id="p-gambar">\n    <h2>🎨 Generator gambar AI</h2>\n'
        '    <p class="muted">Masukkan prompt, pilih channel dan gaya, lalu kirim hasilnya. '
        'Form ini tidak berjalan sampai tombol ditekan.</p>\n'
        f'    {d["gambar_block"]}\n  </div>'
    )
def _panel_ai_settings(d: dict) -> str:
    return (
        '<div class="panel" id="p-ai-settings">\n    <h2>🧠 Kepribadian AI server</h2>\n'
        f'    {d["ai_prompt_block"]}\n  </div>'
    )
def _panel_privasi(d: dict) -> str:
    return (
        '<div class="panel" id="p-privasi">\n    <h2>🔐 Privasi data member</h2>\n'
        f'    {d["ai_privasi_block"]}\n  </div>'
    )
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
        'pesan perpisahan, dan ucapan saat server di-boost. Untuk sambutan &amp; perpisahan, '
        'pilih tampilan <b>Card</b>, <b>Embed</b>, <b>Text</b>, atau <b>Container</b> lalu '
        'lihat pratinjaunya.</p>\n'
        f'    {d.get("tampilan_block", "")}'
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
def _panel_bangun(d: dict) -> str:
    return (
        '<div class="panel" id="p-bangun">\n    <h2>🏗️ Bangun server</h2>\n'
        '    <p class="muted">Bangun dari tema atau rancangan AI, tinjau pratinjau, lalu '
        'terapkan secara eksplisit. Riwayat rollback hanya berisi item yang dibuat fitur ini.</p>\n'
        f'    {d["bangun_block"]}\n  </div>'
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
    "p-gambar": _panel_gambar,
    "p-ai-settings": _panel_ai_settings,
    "p-privasi": _panel_privasi,
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
        "tag",
        "pantau",
        "curhat",
        "sosial",
        "voice",
        "musik",
        "info",
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
    "p-lencana": lambda d: (
        '<div class="panel" id="p-lencana">\n    '
        + (d.get("lencana_block") or '<div class="muted">Panel lencana tidak tersedia.</div>')
        + "\n  </div>"
    ),
    "p-snipe": lambda d: (
        '<div class="panel" id="p-snipe">\n    '
        + (d.get("snipe_block") or '<div class="muted">Panel snipe tidak tersedia.</div>')
        + "\n  </div>"
    ),
    "p-moderasi": lambda d: (
        '<div class="panel" id="p-moderasi">\n    '
        + (d.get("moderasi_block") or '<div class="muted">Panel moderasi tidak tersedia.</div>')
        + "\n  </div>"
    ),
    "p-statistik": lambda d: (
        '<div class="panel" id="p-statistik">\n    '
        + (d.get("stats_block") or '<div class="muted">Panel statistik tidak tersedia.</div>')
        + "\n  </div>"
    ),
    "p-form-inbox": lambda d: (
        '<div class="panel" id="p-form-inbox">\n    '
        + (d.get("form_inbox_block") or '<div class="muted">Kotak masuk formulir tidak tersedia.</div>')
        + "\n  </div>"
    ),
    "p-giveaway": _panel_giveaway,
    "p-bangun": _panel_bangun,
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
def _meta_refresh(detik: int, alamat_bersih: str, flash_pesan: str) -> str:
    """`<meta refresh>` — dimatikan bila auto-refresh 0, diarahkan bila ada pesan.

    Saat ada kotak pesan, refresh diarahkan ke alamat tanpa `pesan` supaya
    notifikasinya hilang sendiri (dan tidak terkirim ulang tiap 30 detik).
    """
    if detik <= 0:
        return ""
    tujuan = (
        f";url={html.escape(alamat_bersih, quote=True)}" if flash_pesan and alamat_bersih else ""
    )
    return f'<meta http-equiv="refresh" content="{max(5, detik)}{tujuan}">'


def _teks_refresh(detik: int) -> str:
    """Keterangan kecil di header: “(🔄 auto-refresh 600s · 10 menit)”."""
    if detik <= 0:
        return " (⏸ auto-refresh mati)"
    petunjuk = f" · {_label_auto(detik)}" if detik >= 60 else ""
    return f" (🔄 auto-refresh {detik}s{petunjuk})"


# Blok yang tidak dirender pemanggil tetap tampil sebagai kotak "tidak tersedia"
# alih-alih halaman kosong. Dulu ini ~40 baris `x_block or '...'` berulang;
# sekarang jadi data supaya tidak ada blok yang lupa diberi fallback.
_BAWAAN_BLOK: dict[str, str] = {
    "setelan_block": "Setelan tidak tersedia.",
    "audit_block": "Belum ada perubahan.",
    "banner_block": "Unggahan tidak tersedia.",
    "kartu_block": "Kartu tidak tersedia.",
    "honeypot_block": "Honeypot tidak tersedia.",
    "moderasi_block": "Panel moderasi tidak tersedia.",
    "snipe_block": "Panel snipe tidak tersedia.",
    "tag_block": "Panel tag tidak tersedia.",
    "curhat_block": "Panel curhat tidak tersedia.",
    "sosial_block": "Panel notifikasi sosial tidak tersedia.",
    "voice_block": "Panel voice linking tidak tersedia.",
    "tampilan_block": "Panel tampilan sambutan tidak tersedia.",
    "musik_block": "Panel musik tidak tersedia.",
    "info_block": "Panel channel info tidak tersedia.",
    "form_inbox_block": "Kotak masuk formulir tidak tersedia.",
    "stats_block": "Panel statistik tidak tersedia.",
    "bangun_block": "Panel bangun tidak tersedia.",
    "gambar_block": "Generator gambar tidak tersedia.",
    "ai_prompt_block": "Prompt AI server tidak tersedia.",
    "ai_privasi_block": "Informasi privasi tidak tersedia.",
    "pantau_block": "Panel highlight tidak tersedia.",
    "lencana_block": "Panel lencana tidak tersedia.",
    "aturan_block": "Penguji aturan tidak tersedia.",
    "starboard_block": "Papan sorotan tidak tersedia.",
    "kartu_rank_block": "Kartu rank tidak tersedia.",
    "uji_block": "Tes fitur tidak tersedia.",
    "setelan_welcome": "Setelan tidak tersedia.",
    "setelan_goodbye": "Setelan tidak tersedia.",
    "setelan_boost": "Setelan tidak tersedia.",
    "kartu_welcome": "Kartu tidak tersedia.",
    "kartu_goodbye": "Kartu tidak tersedia.",
    "kartu_boost": "Kartu tidak tersedia.",
    "uji_welcome": "Tes tidak tersedia.",
    "uji_goodbye": "Tes tidak tersedia.",
    "uji_boost": "Tes tidak tersedia.",
    "ekspor_block": "Ekspor tidak tersedia.",
    "panel_block": "Editor panel tidak tersedia.",
    "tiket_block": "Kotak masuk tiket tidak tersedia.",
    "giveaway_block": "Kendali giveaway tidak tersedia.",
    "arsip_block": "Arsip transkrip tidak tersedia.",
    "tren_block": "Belum ada data tren.",
}


def _data_halaman(status: dict, usage: dict, levels: dict) -> dict:
    """Angka & tabel ringkasan: status bot, pemakaian AI, papan level."""
    guild_limit = int(usage.get("guild_limit") or 0)
    guild_used = int(usage.get("guild_used") or 0)
    guild_usage = (
        f"{guild_used} / {guild_limit}" if guild_limit else f"{guild_used} (tanpa batas)"
    )
    ai_ready = bool(status.get("ai_ready"))
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
    }
    return data


def _blok_halaman(nilai: dict) -> dict:
    """Semua `*_block` beserta fallback-nya (dari `_BAWAAN_BLOK`)."""
    hasil = {}
    for kunci, bawaan in _BAWAAN_BLOK.items():
        hasil[kunci] = nilai.get(kunci) or f'<div class="muted">{bawaan}</div>'
    for kunci in (
        "kontrol_block",
        "fitur_block",
        "kirim_block",
        "buat_block",
        "konten_block",
        "giveaway_block",
        "tren_hari",
    ):
        if kunci in nilai:
            hasil[kunci] = nilai[kunci]
    return hasil


def _susun_halaman(
    status: dict,
    usage: dict,
    levels: dict,
    halaman: str | None,
    isi: str | None,
    nilai: dict,
) -> tuple[str, str]:
    """Slug + isi halaman: `isi` eksplisit, mode lama (semua panel), atau per halaman."""
    data = _data_halaman(status, usage, levels)
    data.update(_blok_halaman(nilai))
    slug = halaman if halaman in HALAMAN_SLUG else ""
    if isi is not None:
        return slug, isi
    if halaman is None:
        return slug, susun_isi_lengkap(data)   # mode lama: semua panel
    return slug, susun_isi(slug, data)


def _format_halaman(
    *,
    status: dict,
    menu: str,
    isi: str,
    keterangan: str,
    guild_picker: str,
    judul: str,
    heading: str,
    refresh_info: str,
    auto_pilih: str,
    meta_refresh: str,
    flash_pesan: str,
    flash_ok: bool,
) -> str:
    """Isi `_PAGE_TEMPLATE` — satu-satunya tempat escaping data status."""
    return _PAGE_TEMPLATE.format(
        font_link=dashboard_tema.FONT_LINK,
        css=dashboard_tema.CSS_HALAMAN,
        refresh_info=refresh_info,
        auto_pilih=auto_pilih,
        meta_refresh=meta_refresh,
        version=html.escape(str(status.get("version") or "-")),
        bot_name=html.escape(str(status.get("bot_name") or "Bot")),
        heading=html.escape(str(heading or "Bot")),
        page_title=html.escape(str(judul or "Dashboard")),
        checked_at=html.escape(str(status.get("checked_at") or "-")),
        menu=menu,
        isi=isi,
        keterangan=html.escape(keterangan),
        guild_picker=guild_picker,
        flash=_flash_box(flash_pesan, flash_ok),
    )


_BAWAAN_PARAM_BLOK: dict[str, str] = {
    'kontrol_block': '<div class="muted">Kontrol tidak tersedia.</div>',
    'fitur_block': '',
    'setelan_block': '',
    'kirim_block': '',
    'buat_block': '',
    'konten_block': '',
    'audit_block': '',
    'banner_block': '',
    'ekspor_block': '',
    'panel_block': '',
    'tiket_block': '',
    'giveaway_block': '',
    'arsip_block': '',
    'tren_block': '',
    'kartu_block': '',
    'kartu_rank_block': '',
    'starboard_block': '',
    'aturan_block': '',
    'honeypot_block': '',
    'moderasi_block': '',
    'snipe_block': '',
    'tag_block': '',
    'lencana_block': '',
    'pantau_block': '',
    'curhat_block': '',
    'sosial_block': '',
    'voice_block': '',
    'tampilan_block': '',
    'musik_block': '',
    'info_block': '',
    'form_inbox_block': '',
    'stats_block': '',
    'bangun_block': '',
    'gambar_block': '',
    'ai_prompt_block': '',
    'ai_privasi_block': '',
    'uji_block': '',
    'setelan_welcome': '',
    'setelan_goodbye': '',
    'setelan_boost': '',
    'kartu_welcome': '',
    'kartu_goodbye': '',
    'kartu_boost': '',
    'uji_welcome': '',
    'uji_goodbye': '',
    'uji_boost': '',
}


def render_dashboard_html(
    *,
    status,
    usage,
    levels,
    refresh=30,
    auto_aksi='',
    auto_dipilih='',
    heading='🛰️ Dashboard Bot',
    guild_picker='',
    flash_pesan='',
    flash_ok=True,
    alamat_bersih='',
    tren_hari=7,
    halaman=None,
    menu='',
    isi=None,
    token='',
    guild_id=0,
    judul_halaman='',
    keterangan='',
    **blok_ui: str,
) -> str:
    """Merender satu halaman dashboard (string). Aman untuk data kosong.

    `halaman` menentukan kelompok panel yang ditampilkan; bila `isi` diberikan
    (mis. hasil `susun_isi`) isi itulah yang dipakai. Tanpa `halaman`/`isi`,
    semua panel dirender dalam satu halaman — perilaku lama tetap jalan.

    Panel opsional (`*_block`, `setelan_*`, `kartu_*`, `uji_*`) boleh dikirim
    sebagai keyword argumen; yang tidak dikirim memakai `_BAWAAN_PARAM_BLOK`.
    """
    tak_dikenal = set(blok_ui) - set(_BAWAAN_PARAM_BLOK)
    if tak_dikenal:
        raise TypeError(f"argumen panel tak dikenal: {sorted(tak_dikenal)}")
    nilai = {**_BAWAAN_PARAM_BLOK, **blok_ui, "tren_hari": tren_hari}
    detik = int(refresh or 0)
    meta_refresh = _meta_refresh(detik, alamat_bersih, flash_pesan)
    refresh_info = _teks_refresh(detik)
    auto_pilih = form_auto(auto_aksi, token, guild_id, detik, auto_dipilih)
    slug, isi_halaman = _susun_halaman(status, usage, levels, halaman, isi, nilai)
    menu_html = menu or render_menu(slug, token, guild_id)
    page_title = judul_halaman or HALAMAN_SLUG.get(slug, HALAMAN_SLUG[""])["judul"]

    return _format_halaman(
        status=status,
        menu=menu_html,
        isi=isi_halaman,
        keterangan=keterangan,
        guild_picker=guild_picker,
        judul=page_title or "Dashboard",
        heading=heading,
        refresh_info=refresh_info,
        auto_pilih=auto_pilih,
        meta_refresh=meta_refresh,
        flash_pesan=flash_pesan,
        flash_ok=flash_ok,
    )
