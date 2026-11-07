"""Panel **Channel info** di halaman Konten & interaksi — server-rendered, tanpa JS.

Setelan channel/judul/warna/interval, kotak isi aturan & info, tombol simpan + segarkan,
dan pratinjau embed. Jalur tulis: `POST /api/konten` (`info-setelan`, `info-isi`,
`info-segarkan`).
"""

from __future__ import annotations

import dashboard_ui


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _opsi_channel(guild, terpilih: int) -> str:
    kanal = list(getattr(guild, "text_channels", []) or [])[:80]
    opsi = ['<option value="0">— belum dipilih —</option>']
    for ch in kanal:
        cid = _id(getattr(ch, "id", 0))
        opsi.append(
            f'<option value="{cid}"{" selected" if cid == int(terpilih or 0) else ""}>'
            f'#{dashboard_ui._esc(getattr(ch, "name", "-"))}</option>'
        )
    return "".join(opsi)


def render_info_block(bot, guild_id: int, token: str) -> str:
    """Panel channel info untuk halaman 🧩 Konten & interaksi."""
    import info_channel as ic

    gid = int(guild_id or 0)
    data = ic.statistik(gid)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None

    setelan = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "info-setelan")
        + f'<div class="medan"><label>Channel info</label>'
        f'<select name="channel_id">{_opsi_channel(guild, data["channel_id"] or 0)}</select></div>'
        '<div class="medan"><label>Penyegaran otomatis</label><select name="enabled">'
        f'<option value="1"{" selected" if data["enabled"] else ""}>Ya</option>'
        f'<option value="0"{" selected" if not data["enabled"] else ""}>Tidak</option></select></div>'
        '<div class="medan"><label>Judul embed</label>'
        f'<input type="text" name="judul" maxlength="200" value="{dashboard_ui._esc(data["judul"])}"></div>'
        '<div class="medan"><label>Warna (#RRGGBB)</label>'
        f'<input type="text" name="warna" maxlength="7" value="{dashboard_ui._esc(data["warna"])}"></div>'
        '<div class="medan"><label>Interval cek (menit)</label>'
        f'<input type="number" name="interval_menit" min="{ic.INTERVAL_MIN}" max="{ic.INTERVAL_MAKS}" '
        f'value="{data["interval_menit"]}"></div>'
        '<button type="submit">Simpan setelan channel info</button></form>'
    )

    isi_form = (
        '<form method="post" action="/api/konten">'
        + dashboard_ui._hidden(gid, token, "info-isi")
        + '<div class="medan"><label>Isi aturan & info</label>'
        f'<textarea name="isi" rows="10" maxlength="{ic.MAKS_ISI}" '
        f'placeholder="Tulis aturan server, jam operasional, link penting, dsb.">'
        f'{dashboard_ui._esc(data["isi"])}</textarea></div>'
        '<button type="submit">Simpan isi & segarkan</button></form>'
        '<form method="post" action="/api/konten" class="baris-form">'
        + dashboard_ui._hidden(gid, token, "info-segarkan")
        + '<button type="submit">Segarkan sekarang</button></form>'
    )

    status = (
        f'<p class="muted">Status: <b>{"aktif" if data["aktif"] else "nonaktif"}</b> · '
        f'isi <b>{data["panjang_isi"]}</b> huruf · pesan '
        f'<b>{"terpasang" if data["pesan_id"] else "belum terpasang"}</b> · cek tiap '
        f"<b>{data['interval_menit']}</b> menit.</p>"
    )
    if data["enabled"] and not data["channel_id"]:
        status += '<p class="muted">⚠️ Channel belum dipilih.</p>'
    if data["enabled"] and data["channel_id"] and not data["isi"]:
        status += '<p class="muted">⚠️ Isi masih kosong — tulis dulu di kotak bawah.</p>'

    pratinjau = ""
    if data["isi"]:
        pratinjau = (
            '<h4>Pratinjau</h4>'
            f'<div class="pratinjau-info" style="border-left:4px solid {dashboard_ui._esc(data["warna"])};">'
            f'<b>{dashboard_ui._esc(data["judul"])}</b>'
            f'<div class="muted" style="white-space:pre-wrap;">'
            f'{dashboard_ui._esc(data["isi"][:1200])}</div></div>'
        )

    return (
        '<div class="subpanel" id="p-info"><h3>ℹ️ Channel info otomatis</h3>'
        '<p class="muted">Satu channel baca-saja berisi aturan & info penting. Bot menerbitkan '
        "**satu pesan embed** lalu mengeditnya setiap kali isi berubah — channel tidak penuh "
        "pesan lama. 0 kuota AI.</p>"
        f"{status}{setelan}{isi_form}{pratinjau}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_info(bot, gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel channel info → `(berhasil, pesan)`."""
    import info_channel as ic

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "info-setelan":
        ic.set_config(
            gid,
            enabled=str(payload.get("enabled") or "0") not in ("0", "false", "off"),
            channel_id=_id(payload.get("channel_id")) or None,
            judul=str(payload.get("judul") or "") or None,
            warna=str(payload.get("warna") or "") or None,
            interval_menit=_id(payload.get("interval_menit")) or None,
        )
        await ic.save_info_channel_to_disk()
        data = ic.statistik(gid)
        return True, (
            f"Setelan channel info disimpan: {'aktif' if data['aktif'] else 'nonaktif'} · "
            f"interval {data['interval_menit']} menit."
        )

    if aksi == "info-isi":
        ok, pesan = ic.set_isi(gid, str(payload.get("isi") or ""))
        if not ok:
            return False, pesan
        await ic.save_info_channel_to_disk()
        status = "tersimpan"
        if ic.aktif(gid) and bot is not None:
            status = await ic.segarkan(bot, gid)
        return True, f"{pesan} Pesan di channel: {status}."

    if aksi == "info-segarkan":
        if bot is None:
            return False, "Bot tidak tersedia untuk menyegarkan channel."
        status = await ic.segarkan(bot, gid)
        pesan = {
            "dibuat": "Pesan info diterbitkan.",
            "diperbarui": "Pesan info diperbarui.",
            "sama": "Pesan info sudah paling baru.",
            "nonaktif": "Channel info belum aktif (isi & channel belum lengkap).",
            "gagal": "Channel tidak ditemukan atau bot tidak punya izin.",
        }.get(status, status)
        return status in ("dibuat", "diperbarui", "sama"), pesan

    return False, f"Aksi channel info `{aksi or '-'}` tidak dikenal."
