"""Panel **Lencana (achievements)** di halaman Inti & level — server-rendered.

Isi panel: statistik singkat, setelan (aktif + channel pengumuman), matriks
**role hadiah** per tingkat, papan lencana, dan tombol hapus hadiah.
Semua form HTML biasa (tanpa JavaScript) dan lewat `POST /api/lencana`.
"""

from __future__ import annotations

import dashboard_ui


def _id(nilai: object) -> int:
    """Angka aman dari field form (kosong/bukan angka → 0)."""
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _bar(persen: int) -> str:
    penuh = max(0, min(10, int(persen) // 10))
    return "▰" * penuh + "▱" * (10 - penuh)


def _status_lencana(achievements, data: dict) -> str:
    """Baris status: aktif/nonaktif, jumlah member, tingkat, role hadiah."""
    lencana = (
        '<span class="lencana on">aktif</span>'
        if data["aktif"]
        else '<span class="lencana off">nonaktif</span>'
    )
    rincian = " · ".join(
        f"{achievements.ACHIEVEMENT_MAP[k]['emoji']} {v}"
        for k, v in data["per_lencana"].items()
    )
    status = (
        f'<p class="muted">Status: {lencana} · <b>{data["anggota"]}</b> member terdata · '
        f"<b>{data['total_tingkat']}</b> tingkat diberikan ({rincian}) · "
        f"role hadiah: <b>{data['hadiah_role']}</b></p>"
    )
    return status


def _form_setelan(achievements, data: dict, kanal: list, gid: int, token: str) -> str:
    """Form pemilihan channel pengumuman & sakelar aktif lencana."""
    opsi_channel = '<option value="0">— tanpa pengumuman —</option>' + "".join(
        '<option value="{0}"{1}>#{2}</option>'.format(
            int(getattr(ch, "id", 0)),
            " selected" if int(getattr(ch, "id", 0)) == data["channel_id"] else "",
            dashboard_ui._esc(str(getattr(ch, "name", "-"))),
        )
        for ch in kanal
    )
    setelan = (
        '<form method="post" action="/api/lencana" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "lencana-setelan")
        + f'<div class="medan"><label>Channel pengumuman lencana</label>'
        f'<select name="channel_id">{opsi_channel}</select></div>'
        '<div class="medan"><label>Lencana</label><select name="enabled">'
        f'<option value="1"{" selected" if data["aktif"] else ""}>Aktif</option>'
        f'<option value="0"{" selected" if not data["aktif"] else ""}>Nonaktif</option>'
        "</select></div>"
        '<button type="submit">Simpan setelan lencana</button></form>'
    )
    return setelan


def _form_hadiah(achievements, roles: list, gid: int, token: str) -> str:
    """Form pemasangan role hadiah per lencana/tingkat."""
    opsi_kunci = "".join(
        '<option value="{0}">{1} {2} ({3} tingkat)</option>'.format(
            item["kunci"],
            item["emoji"],
            dashboard_ui._esc(item["label"]),
            len(item["tingkat"]),
        )
        for item in achievements.ACHIEVEMENTS
    )
    opsi_role = "".join(
        '<option value="{0}">@{1}</option>'.format(
            int(getattr(r, "id", 0)), dashboard_ui._esc(str(getattr(r, "name", "-")))
        )
        for r in roles
    ) or '<option value="0">(belum ada role)</option>'
    form_hadiah = (
        '<form method="post" action="/api/lencana" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "lencana-role")
        + f'<div class="medan"><label>Lencana</label><select name="kunci">{opsi_kunci}</select></div>'
        '<div class="medan"><label>Tingkat (1–5)</label>'
        '<input type="number" name="tingkat" min="1" max="5" value="1"></div>'
        f'<div class="medan"><label>Role hadiah</label><select name="role_id">{opsi_role}</select></div>'
        '<button type="submit">Pasang role hadiah</button></form>'
    )
    return form_hadiah


def _tabel_hadiah(cfg: dict, achievements, gid: int, token: str) -> str:
    """Tabel role hadiah terpasang beserta tombol hapus."""
    rewards = cfg.get("rewards") or {}
    if rewards:
        baris = []
        for ref, role_id in sorted(rewards.items()):
            kunci, _, tingkat = ref.partition(":")
            item = achievements.ACHIEVEMENT_MAP.get(kunci, {})
            ambang = ""
            if item and tingkat.isdigit() and 1 <= int(tingkat) <= len(item["tingkat"]):
                ambang = f' ({item["tingkat"][int(tingkat) - 1]:,} {item["satuan"]})'
            baris.append(
                "<tr>"
                f'<td>{item.get("emoji", "•")} {dashboard_ui._esc(item.get("label", kunci))}'
                f" tingkat {dashboard_ui._esc(tingkat)}{dashboard_ui._esc(ambang)}</td>"
                f'<td><span class="mono">&lt;@&amp;{int(role_id)}&gt;</span></td>'
                "<td>"
                '<form method="post" action="/api/lencana" class="baris-form">'
                + dashboard_ui._hidden(gid, token, f"lencana-hapus:{ref}")
                + '<button type="submit" class="danger">Hapus</button></form>'
                "</td></tr>"
            )
        tabel_hadiah = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>Lencana</th><th>Role</th><th></th></tr>"
            f"{''.join(baris)}</table></div>"
        )
    else:
        tabel_hadiah = (
            '<p class="muted">Belum ada role hadiah. Angka di bawah menunjukkan kapan '
            "tiap tingkat terbuka.</p>"
        )
    return tabel_hadiah


def _papan_lencana(achievements, gid: int) -> str:
    """Tabel 5 member dengan lencana terbanyak."""
    papan = achievements.papan(gid, limit=5)
    if papan:
        baris_papan = "".join(
            f"<tr><td>{nomor}</td><td><span class=\"mono\">@{row['user_id']}</span></td>"
            f"<td><b>{row['total']}</b></td>"
            f'<td class="muted"><code>{_bar(min(100, row["total"] * 10))}</code></td></tr>'
            for nomor, row in enumerate(papan, start=1)
        )
        tabel_papan = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>#</th><th>Member</th><th>Tingkat</th><th></th></tr>"
            f"{baris_papan}</table></div>"
        )
    else:
        tabel_papan = '<p class="muted">Belum ada lencana tercatat.</p>'
    return tabel_papan


def render_lencana_block(bot, guild_id: int, token: str) -> str:
    """Panel lencana untuk halaman ⚙️ Inti & level."""
    import achievements

    gid = int(guild_id or 0)
    cfg = achievements.peek_config(gid)
    data = achievements.statistik(gid)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    kanal = list(getattr(guild, "text_channels", []) or [])[:80]
    roles = [r for r in (getattr(guild, "roles", []) or []) if not getattr(r, "is_default", False)][:60]
    daftar_tingkat = "".join(
        '<li><b>{0} {1}</b> — {2}</li>'.format(
            item["emoji"],
            dashboard_ui._esc(item["label"]),
            " · ".join(f"{ambang:,} {item['satuan']}" for ambang in item["tingkat"]),
        )
        for item in achievements.ACHIEVEMENTS
    )

    status = _status_lencana(achievements, data)
    setelan = _form_setelan(achievements, data, kanal, gid, token)
    form_hadiah = _form_hadiah(achievements, roles, gid, token)
    tabel_hadiah = _tabel_hadiah(cfg, achievements, gid, token)

    tabel_papan = _papan_lencana(achievements, gid)
    return (
        '<div class="subpanel"><h3>🏅 Lencana bertingkat</h3>'
        '<p class="muted">Lencana dihitung dari data yang <b>sudah</b> dicatat bot '
        "(pesan, menit voice, level, riwayat menang undian) — tidak ada pelacakan baru, "
        "<b>0 kuota AI</b>. Setiap tingkat bisa diberi role hadiah.</p>"
        f"{status}{setelan}{form_hadiah}{tabel_hadiah}"
        f'<p class="muted">Tangga tingkat:</p><ul class="muted">{daftar_tingkat}</ul>'
        "<h4>🏆 Papan lencana</h4>"
        f"{tabel_papan}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/lencana`)
# ==============================================================================
async def aksi_lencana(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel lencana → `(berhasil, pesan)`.

    Dipisah dari handler HTTP supaya gampang dites tanpa server.
    """
    import achievements

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "lencana-setelan":
        achievements.set_config(
            gid,
            enabled=str(payload.get("enabled") or "1") not in ("0", "false", "off"),
            channel_id=_id(payload.get("channel_id")),
        )
        await achievements.save_achievements_to_disk()
        data = achievements.statistik(gid)
        kanal = f"#{data['channel_id']}" if data["channel_id"] else "dimatikan"
        return True, (
            f"Setelan lencana disimpan: {'aktif' if data['aktif'] else 'nonaktif'} · "
            f"pengumuman {kanal}."
        )

    if aksi == "lencana-role":
        ok, pesan = achievements.set_reward(
            gid,
            str(payload.get("kunci") or ""),
            _id(payload.get("tingkat")),
            _id(payload.get("role_id")) or None,
        )
        if ok:
            await achievements.save_achievements_to_disk()
        return ok, pesan

    if aksi.startswith("lencana-hapus:"):
        ref = aksi.split(":", 1)[1]
        kunci, _, tingkat = ref.partition(":")
        ok, pesan = achievements.set_reward(
            gid, kunci, _id(tingkat), None
        )
        if ok:
            await achievements.save_achievements_to_disk()
        return ok, pesan

    return False, f"Aksi lencana `{aksi or '-'}` tidak dikenal."
