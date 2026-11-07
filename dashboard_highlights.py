"""Panel **Highlight kata kunci** (ala wisp) di halaman Konten & interaksi.

Server-rendered: setelan global (aktif, batas DM/menit, channel yang diabaikan),
daftar pelanggan beserta kata kunci, dan tombol hapus per pelanggan.
Jalur tulis: `POST /api/konten` dengan aksi `pantau-*`.
"""

from __future__ import annotations

import dashboard_ui


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _daftar_id(teks: object) -> list[int]:
    """`"123, 456 789"` → `[123, 456, 789]`."""
    hasil: list[int] = []
    for potong in str(teks or "").replace(",", " ").split():
        if potong.isdigit() and int(potong) not in hasil:
            hasil.append(int(potong))
    return hasil[:20]


def render_highlights_block(bot, guild_id: int, token: str) -> str:
    """Panel highlight untuk halaman 🧩 Konten & interaksi."""
    import highlights

    gid = int(guild_id or 0)
    data = highlights.statistik(gid)
    pelanggan = highlights.daftar_pelanggan(gid)

    status = (
        f'<p class="muted">Status: <b>{"aktif" if data["aktif"] else "nonaktif"}</b> · '
        f'<b>{data["pelanggan"]}</b> pelanggan · <b>{data["total_kata"]}</b> kata kunci · '
        f'<b>{data["hit"]}</b> DM terkirim · batas <b>{data["max_per_menit"]}</b> DM/menit</p>'
    )
    abaikan = " ".join(f"<code>{cid}</code>" for cid in data["abaikan_channel"]) or "tidak ada"
    opsi_aktif = (
        f'<option value="1"{" selected" if data["aktif"] else ""}>Aktif</option>'
        f'<option value="0"{" selected" if not data["aktif"] else ""}>Nonaktif</option>'
    )
    setelan = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "pantau-setelan")
        + '<div class="medan"><label>Fitur highlight</label>'
        f'<select name="enabled">{opsi_aktif}</select></div>'
        '<div class="medan"><label>Batas DM per member per menit</label>'
        f'<input type="number" name="max_per_menit" min="1" max="5" value="{data["max_per_menit"]}"></div>'
        '<div class="medan"><label>Channel diabaikan (ID, pisahkan spasi)</label>'
        f'<input type="text" name="abaikan_channel" value="{" ".join(str(c) for c in data["abaikan_channel"])}" '
        'placeholder="contoh: 123456789012345678"></div>'
        '<button type="submit">Simpan setelan highlight</button></form>'
    )

    if pelanggan:
        baris = "".join(
            "<tr>"
            f'<td><span class="mono">@{row["user_id"]}</span></td>'
            f'<td>{dashboard_ui._esc(", ".join(row["keywords"]))}</td>'
            f'<td><b>{row["hit"]}</b></td>'
            "<td>"
            '<form method="post" action="/api/konten" class="baris-form">'
            + dashboard_ui._hidden(gid, token, f"pantau-hapus:{row['user_id']}")
            + '<button type="submit" class="danger">Hapus</button></form>'
            "</td></tr>"
            for row in pelanggan[:50]
        )
        tabel = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>Member</th><th>Kata kunci</th><th>DM</th><th></th></tr>"
            f"{baris}</table></div>"
        )
        if len(pelanggan) > 50:
            tabel += f'<p class="muted">{len(pelanggan) - 50} pelanggan lain tidak ditampilkan.</p>'
    else:
        tabel = (
            '<p class="muted">Belum ada member yang memantau kata kunci. '
            "Member menambahkannya sendiri lewat <code>/pantau tambah kata:open order</code>.</p>"
        )

    teratas = (
        " · ".join(f"`{kata}` ({jumlah})" for kata, jumlah in data["teratas"]) or "belum ada"
    )

    return (
        '<div class="panel" id="p-pantau">\n    <h2>🔔 Highlight kata kunci</h2>\n'
        '    <p class="muted">Member memilih kata kunci sendiri, lalu bot mengirim <b>DM</b> '
        "saat kata itu muncul di chat (maks 10 kata kunci/member). Bot <b>tidak</b> menyimpan "
        "isi pesan dan <b>tidak memakai AI</b> — 0 kuota.</p>\n"
        f"    {status}\n"
        f'    <p class="muted">Channel diabaikan: {abaikan} · kata teratas: {teratas}</p>\n'
        f"    {setelan}\n"
        f'    <h4>Pelanggan</h4>\n    {tabel}\n'
        "  </div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_highlights(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel highlight → `(berhasil, pesan)`."""
    import highlights

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "pantau-setelan":
        cfg = highlights.get_config(gid)
        highlights.set_config(
            gid,
            enabled=str(payload.get("enabled") or "1") not in ("0", "false", "off"),
            abaikan_channel=_daftar_id(payload.get("abaikan_channel"))
            if "abaikan_channel" in payload
            else cfg.get("abaikan_channel"),
            max_per_menit=_id(payload.get("max_per_menit")) or None,
        )
        await highlights.save_highlights_to_disk()
        data = highlights.statistik(gid)
        return True, (
            f"Setelan highlight disimpan: {'aktif' if data['aktif'] else 'nonaktif'} · "
            f"batas {data['max_per_menit']} DM/menit · "
            f"{len(data['abaikan_channel'])} channel diabaikan."
        )

    if aksi.startswith("pantau-hapus:"):
        uid = _id(aksi.split(":", 1)[1])
        if highlights.bersihkan(gid, uid):
            await highlights.save_highlights_to_disk()
            return True, f"Setelan highlight member `{uid}` dihapus."
        return False, f"Member `{uid}` tidak punya setelan highlight."

    return False, f"Aksi highlight `{aksi or '-'}` tidak dikenal."
