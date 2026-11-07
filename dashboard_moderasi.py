"""Panel **Moderasi** di dashboard: kasus, antrean laporan/banding, & statistik staf.

Semua server-rendered tanpa JavaScript:

* setelan jalur laporan (channel tujuan, cooldown, DM pelapor),
* antrean laporan & banding — ubah status langsung dari HP,
* daftar temp-ban yang masih berjalan + tombol cabut,
* pencarian nomor kasus / kata / jenis aksi (hasil terakhir disimpan per server),
* papan statistik staf (siapa menindak berapa banyak) & ringkasan per jenis aksi.
"""

from __future__ import annotations

import time

import dashboard_ui

#: Hasil pencarian terakhir per server: {guild_id: {"q", "aksi", "hasil", "waktu"}}
_pencarian: dict[int, dict] = {}


def reset() -> None:
    """Membersihkan state pencarian (dipakai tes)."""
    _pencarian.clear()


def _waktu(nilai: float) -> str:
    if not nilai:
        return "-"
    return time.strftime("%d/%m/%y %H:%M", time.localtime(float(nilai)))


def cari_kasus(guild_id: int, q: str = "", aksi: str = "") -> list[dict]:
    """Mencari kasus **dan** menyimpan hasil terakhir (supaya tetap tampil)."""
    import moderation

    hasil = moderation.search_cases(int(guild_id), q=q, aksi=aksi or None, limit=15)
    _pencarian[int(guild_id)] = {
        "q": str(q or ""),
        "aksi": str(aksi or ""),
        "hasil": [int(c.get("id", 0)) for c in hasil],
        "waktu": time.time(),
    }
    return hasil


def hasil_pencarian(guild_id: int) -> dict:
    """Hasil pencarian terakhir untuk server ini (kosong bila belum pernah)."""
    return dict(_pencarian.get(int(guild_id)) or {})


def _baris_kasus(kasus: dict) -> str:
    import moderation

    meta = moderation.ACTIONS.get(str(kasus.get("action")), {"emoji": "•", "label": "Aksi"})
    return (
        "<tr>"
        f'<td><code>#{int(kasus.get("id", 0))}</code></td>'
        f'<td>@{int(kasus.get("user_id", 0))}</td>'
        f'<td>{dashboard_ui._esc(meta["emoji"] + " " + meta["label"])}</td>'
        f'<td>{dashboard_ui._esc(str(kasus.get("reason") or "—")[:120])}</td>'
        f'<td class="muted">{_waktu(kasus.get("created_at", 0))}</td>'
        "</tr>"
    )


def _blok_pencarian(guild_id: int, token: str) -> str:
    import moderation

    terakhir = hasil_pencarian(guild_id)
    opsi_aksi = "".join(
        '<option value="{0}"{1}>{2}</option>'.format(
            kunci,
            " selected" if kunci == terakhir.get("aksi") else "",
            dashboard_ui._esc(f'{meta["emoji"]} {meta["label"]}'),
        )
        for kunci, meta in moderation.ACTIONS.items()
    )
    form = (
        '<form method="post" action="/api/moderasi" class="formgrid">'
        + dashboard_ui._hidden(guild_id, token, "cari-kasus")
        + '<div class="medan"><label>Nomor kasus, ID member, atau kata di alasan</label>'
        f'<input type="text" name="q" value="{dashboard_ui._esc(terakhir.get("q", ""))}" '
        'placeholder="mis. 12, 424242, atau judi"></div>'
        '<div class="medan"><label>Jenis aksi</label>'
        f'<select name="aksi"><option value="">Semua aksi</option>{opsi_aksi}</select></div>'
        '<button type="submit">Cari kasus</button></form>'
    )
    if not terakhir:
        return form + '<p class="muted">Belum ada pencarian. Kasus terbaru ada di bawah.</p>'
    kasus = [moderation.get_case(guild_id, nomor) for nomor in terakhir.get("hasil") or []]
    kasus = [k for k in kasus if k]
    if not kasus:
        return form + '<p class="muted">Tidak ada kasus yang cocok dengan pencarian itu.</p>'
    baris = "".join(_baris_kasus(k) for k in kasus)
    return (
        form
        + f'<p class="muted">{len(kasus)} kasus ditemukan '
        f'(kata kunci <code>{dashboard_ui._esc(terakhir.get("q") or "-")}</code>).</p>'
        '<div class="tabel-wrap"><table class="tabel">'
        "<tr><th>Kasus</th><th>Member</th><th>Aksi</th><th>Alasan</th><th>Waktu</th></tr>"
        f"{baris}</table></div>"
    )


def _blok_antrean(guild_id: int, token: str) -> str:
    import reports

    data = reports.status(guild_id)
    entries = reports.daftar(guild_id, limit=12)
    if not entries:
        return (
            '<p class="muted">Antrean kosong. Member bisa mengirim laporan lewat '
            "<code>/lapor</code> dan banding lewat <code>/banding</code>.</p>"
        )
    potongan = []
    for entri in entries:
        jenis = reports.JENIS.get(str(entri.get("jenis")), "•")
        status_teks = reports.STATUS.get(str(entri.get("status")), "•")
        target = (
            f' → <span class="mono">@{int(entri["target_id"])}</span>'
            if entri.get("target_id")
            else ""
        )
        kasus = (
            f' · kasus <code>#{int(entri["kasus_id"])}</code>' if entri.get("kasus_id") else ""
        )
        catatan = (
            f'<div class="muted">Catatan staf: {dashboard_ui._esc(str(entri.get("catatan")))}</div>'
            if entri.get("catatan")
            else ""
        )
        opsi_status = "".join(
            '<option value="{0}"{1}>{2}</option>'.format(
                kunci,
                " selected" if kunci == entri.get("status") else "",
                dashboard_ui._esc(teks),
            )
            for kunci, teks in reports.STATUS.items()
        )
        potongan.append(
            '<div class="baris-antrean">'
            f'<div><b>#{int(entri["id"])}</b> · {dashboard_ui._esc(jenis)} · '
            f'{dashboard_ui._esc(status_teks)} · '
            f'<span class="mono">@{int(entri["pelapor_id"])}</span>{target}{kasus}</div>'
            f'<div class="muted">{dashboard_ui._esc(str(entri.get("alasan"))[:300])}</div>'
            f"{catatan}"
            '<form method="post" action="/api/moderasi" class="baris-form">'
            + dashboard_ui._hidden(guild_id, token, "antrean-status")
            + f'<input type="hidden" name="kode" value="{int(entri["id"])}">'
            f'<select name="status">{opsi_status}</select>'
            '<input type="text" name="catatan" placeholder="Catatan (opsional)" value="">'
            '<button type="submit">Simpan</button></form>'
            "</div>"
        )
    ringkas = (
        f"Menunggu <b>{data['menunggu']}</b> · laporan <b>{data['laporan']}</b> · "
        f"banding <b>{data['banding']}</b> · diterima <b>{data['diterima']}</b> · "
        f"ditolak <b>{data['ditolak']}</b>"
    )
    return f'<p class="muted">{ringkas}</p>' + "".join(potongan)


def _blok_setelan(guild_id: int, token: str, bot) -> str:
    import reports

    data = reports.status(guild_id)
    guild = bot.get_guild(int(guild_id)) if callable(getattr(bot, "get_guild", None)) else None
    kanal = list(getattr(guild, "text_channels", []) or [])[:80]
    opsi_channel = '<option value="0">— ikut channel log moderasi —</option>' + "".join(
        '<option value="{0}"{1}>#{2}</option>'.format(
            int(getattr(ch, "id", 0)),
            " selected" if int(getattr(ch, "id", 0)) == data["channel_id"] else "",
            dashboard_ui._esc(str(getattr(ch, "name", "-"))),
        )
        for ch in kanal
    )
    lencana = (
        '<span class="lencana on">laporan aktif</span>'
        if data["aktif"]
        else '<span class="lencana off">laporan dimatikan</span>'
    )
    return (
        f'<p class="muted">Status: {lencana} · cooldown <b>{data["cooldown_sec"]} detik</b> '
        f'· DM pelapor: <b>{"ya" if data["dm_pelapor"] else "tidak"}</b></p>'
        '<form method="post" action="/api/moderasi" class="formgrid">'
        + dashboard_ui._hidden(guild_id, token, "laporan-setelan")
        + '<div class="medan"><label>Channel laporan</label>'
        f'<select name="channel_id">{opsi_channel}</select></div>'
        '<div class="medan"><label>Cooldown pelapor (detik, 0–86400)</label>'
        f'<input type="number" name="cooldown_sec" min="0" max="86400" value="{data["cooldown_sec"]}"></div>'
        '<div class="medan"><label>Aktifkan laporan</label>'
        f'<select name="enabled"><option value="1"{" selected" if data["aktif"] else ""}>Ya</option>'
        f'<option value="0"{" selected" if not data["aktif"] else ""}>Tidak</option></select></div>'
        '<div class="medan"><label>DM konfirmasi ke pelapor</label>'
        f'<select name="dm_pelapor"><option value="1"{" selected" if data["dm_pelapor"] else ""}>Ya</option>'
        f'<option value="0"{" selected" if not data["dm_pelapor"] else ""}>Tidak</option></select></div>'
        '<button type="submit">Simpan setelan laporan</button></form>'
    )


def _blok_tempban(guild_id: int, token: str) -> str:
    import moderation

    daftar = moderation.list_tempbans(guild_id)
    if not daftar:
        return '<p class="muted">Tidak ada ban sementara yang berjalan.</p>'
    baris = []
    for entri in daftar[:12]:
        baris.append(
            '<div class="baris-antrean"><div>'
            f'<code>#{int(entri.get("case_id") or 0)}</code> · '
            f'<span class="mono">@{int(entri.get("user_id") or 0)}</span> · berakhir '
            f'{_waktu(entri.get("until", 0))}'
            f'<div class="muted">{dashboard_ui._esc(str(entri.get("reason") or "—")[:160])}</div>'
            '<form method="post" action="/api/moderasi" class="baris-form">'
            + dashboard_ui._hidden(guild_id, token, "tempban-cabut")
            + f'<input type="hidden" name="user_id" value="{int(entri.get("user_id") or 0)}">'
            '<button type="submit">Cabut sekarang</button></form>'
            "</div></div>"
        )
    return (
        f'<p class="muted">{len(daftar)} ban sementara aktif — dicabut otomatis saat waktunya '
        "habis, atau tekan tombol untuk mencabut lebih awal.</p>" + "".join(baris)
    )


def _blok_statistik(guild_id: int) -> str:
    import moderation

    data = moderation.staff_stats(guild_id, days=30, limit=8)
    if not data["total"]:
        return '<p class="muted">Belum ada tindakan moderasi dalam 30 hari terakhir.</p>'
    baris = []
    for nomor, orang in enumerate(data["moderator"], start=1):
        nama = (
            '<span class="mono">🤖 otomatis</span>'
            if orang["moderator_id"] == 0
            else f'<span class="mono">@{orang["moderator_id"]}</span>'
        )
        rincian = " · ".join(
            f"{moderation.ACTIONS.get(a, {}).get('emoji', '•')} {a}: {n}"
            for a, n in orang["per_aksi"].items()
        )
        baris.append(
            f"<tr><td>{nomor}</td><td>{nama}</td><td><b>{orang['total']}</b></td>"
            f'<td class="muted">{dashboard_ui._esc(rincian)}</td></tr>'
        )
    return (
        f'<p class="muted"><b>{data["total"]}</b> tindakan dalam 30 hari terakhir '
        f"({len(data['moderator'])} pelaku, termasuk aksi otomatis).</p>"
        '<div class="tabel-wrap"><table class="tabel">'
        "<tr><th>#</th><th>Staf</th><th>Tindakan</th><th>Rincian</th></tr>"
        f"{''.join(baris)}</table></div>"
    )


def _blok_kasus_terbaru(guild_id: int) -> str:
    import moderation

    kasus = moderation.list_cases(guild_id, limit=10)
    if not kasus:
        return '<p class="muted">Belum ada kasus moderasi tercatat.</p>'
    baris = "".join(_baris_kasus(k) for k in kasus)
    return (
        '<div class="tabel-wrap"><table class="tabel">'
        "<tr><th>Kasus</th><th>Member</th><th>Aksi</th><th>Alasan</th><th>Waktu</th></tr>"
        f"{baris}</table></div>"
    )


def render_moderasi_block(bot, guild_id: int, token: str) -> str:
    """Semua panel moderasi dalam satu blok (dipasang di halaman 🚨 Moderasi)."""
    gid = int(guild_id or 0)
    import reports

    data = reports.status(gid)
    lencana = (
        '<span class="lencana on">aktif</span>'
        if data["aktif"]
        else '<span class="lencana off">nonaktif</span>'
    )
    return (
        '<div class="subpanel"><h3>🚨 Moderasi &amp; antrean member</h3>'
        '<p class="muted">Satu tempat untuk <b>kasus</b> (warn/timeout/kick/ban/tempban/softban), '
        "<b>laporan member</b> (<code>/lapor</code>), dan <b>banding</b> (<code>/banding</code>). "
        "Member tidak pernah dihukum hanya karena dilaporkan — staf yang memutuskan.</p>"
        f'<p class="muted">Jalur laporan: {lencana} · total kasus <b>{len(_semua_kasus(gid))}</b></p>'
        "<h4>📮 Antrean laporan &amp; banding</h4>"
        f"{_blok_antrean(gid, token)}"
        "<h4>⚙️ Setelan jalur laporan</h4>"
        f"{_blok_setelan(gid, token, bot)}"
        "<h4>⏳ Ban sementara (temp-ban)</h4>"
        f"{_blok_tempban(gid, token)}"
        "<h4>🔎 Cari kasus</h4>"
        f"{_blok_pencarian(gid, token)}"
        "<h4>🏆 Statistik staf (30 hari)</h4>"
        f"{_blok_statistik(gid)}"
        "<h4>🗂️ Kasus terbaru</h4>"
        f"{_blok_kasus_terbaru(gid)}"
        "</div>"
    )


def _semua_kasus(guild_id: int) -> list[dict]:
    import moderation

    return moderation.mod_cases.get(int(guild_id)) or []
