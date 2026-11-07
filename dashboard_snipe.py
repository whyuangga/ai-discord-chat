"""Panel **Snipe & EditSnipe** di halaman Moderasi — server-rendered, tanpa JavaScript.

Isinya: sakelar fitur (hapus/ubah), penjelasan bahwa riwayat hanya di memori, dan
ringkasan jumlah channel/pesan yang sedang tersimpan. Jalur tulis: `POST /api/moderasi`
dengan aksi `snipe-*`.
"""

from __future__ import annotations

import dashboard_ui


def render_snipe_block(bot, guild_id: int, token: str) -> str:
    """Panel snipe untuk halaman 🚨 Moderasi."""
    import snipe

    gid = int(guild_id or 0)
    data = snipe.statistik(gid)
    pilih = lambda nilai: " selected" if nilai else ""  # noqa: E731

    form = (
        '<form method="post" action="/api/moderasi" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "snipe-setelan")
        + '<div class="medan"><label>Fitur snipe</label><select name="enabled">'
        f'<option value="1"{pilih(data["aktif"])}>Aktif</option>'
        f'<option value="0"{pilih(not data["aktif"])}>Nonaktif</option></select></div>'
        '<div class="medan"><label>Catat pesan dihapus</label><select name="hapus">'
        f'<option value="1"{pilih(data["hapus"])}>Ya</option>'
        f'<option value="0"{pilih(not data["hapus"])}>Tidak</option></select></div>'
        '<div class="medan"><label>Catat pesan diubah</label><select name="edit">'
        f'<option value="1"{pilih(data["edit"])}>Ya</option>'
        f'<option value="0"{pilih(not data["edit"])}>Tidak</option></select></div>'
        '<button type="submit">Simpan setelan snipe</button></form>'
    )

    return (
        '<div class="subpanel"><h3>🔎 Snipe &amp; EditSnipe</h3>'
        '<p class="muted">Staf bisa melihat pesan yang <i>baru saja</i> dihapus/diubah di '
        "channel tempat ia mengetik <code>/snipe hapus</code> atau <code>/snipe edit</code>. "
        "Riwayat <b>hanya di memori</b> — maksimal 5 pesan per channel dan hilang begitu "
        "bot restart, jadi tidak ada data sensitif yang tersimpan di disk.</p>"
        f'<p class="muted">Status: <b>{"aktif" if data["aktif"] else "nonaktif"}</b> · '
        f'pesan terhapus: <b>{data["entri_hapus"]}</b> di {data["channel_hapus"]} channel · '
        f'pesan diubah: <b>{data["entri_edit"]}</b> di {data["channel_edit"]} channel · '
        f"maks <b>{data['maks_per_channel']}</b>/channel</p>"
        f"{form}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/moderasi`)
# ==============================================================================
async def aksi_snipe(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel snipe → `(berhasil, pesan)`."""
    import snipe

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "snipe-setelan":
        nyala = lambda kunci, bawaan=True: str(payload.get(kunci) or ("1" if bawaan else "0")) not in (  # noqa: E731
            "0",
            "false",
            "off",
        )
        snipe.set_config(
            gid,
            enabled=nyala("enabled"),
            hapus=nyala("hapus"),
            edit=nyala("edit"),
        )
        data = snipe.statistik(gid)
        return True, (
            f"Setelan snipe disimpan: fitur {'aktif' if data['aktif'] else 'nonaktif'} · "
            f"hapus {'ya' if data['hapus'] else 'tidak'} · edit {'ya' if data['edit'] else 'tidak'}."
        )

    return False, f"Aksi snipe `{aksi or '-'}` tidak dikenal."
