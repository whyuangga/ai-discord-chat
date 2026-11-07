"""Panel **Voice linking** di halaman Konten & interaksi — server-rendered, tanpa JS.

Setelan role + channel teks privat saat member di voice, daftar channel privat yang sedang
dikelola bot, dan tombol lepas untuk channel yang tertinggal. Jalur tulis: `POST /api/konten`
(`voice-setelan`, `voice-lepas:<voice_id>`).
"""

from __future__ import annotations

import dashboard_ui


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _opsi_ya_tidak(nilai: bool) -> str:
    return (
        f'<option value="1"{" selected" if nilai else ""}>Ya</option>'
        f'<option value="0"{" selected" if not nilai else ""}>Tidak</option>'
    )


def render_voice_block(bot, guild_id: int, token: str) -> str:
    """Panel voice linking untuk halaman 🧩 Konten & interaksi."""
    import voice_link

    gid = int(guild_id or 0)
    data = voice_link.statistik(gid)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None

    role_opsi = ['<option value="0">— belum dipilih —</option>']
    kategori_opsi = ['<option value="0">— ikut kategori voice —</option>']
    for role in list(getattr(guild, "roles", []) or [])[:80]:
        rid = _id(getattr(role, "id", 0))
        if not rid or getattr(role, "is_default", lambda: False)():
            continue
        role_opsi.append(
            f'<option value="{rid}"{" selected" if rid == data["role_id"] else ""}>'
            f'@{dashboard_ui._esc(getattr(role, "name", "-"))}</option>'
        )
    for kanal in list(getattr(guild, "categories", []) or [])[:40]:
        cid = _id(getattr(kanal, "id", 0))
        kategori_opsi.append(
            f'<option value="{cid}"{" selected" if cid == data["kategori_id"] else ""}>'
            f'{dashboard_ui._esc(getattr(kanal, "name", "-"))}</option>'
        )

    setelan = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "voice-setelan")
        + '<div class="medan"><label>Voice linking</label><select name="enabled">'
        f'{_opsi_ya_tidak(data["enabled"])}</select></div>'
        '<div class="medan"><label>Role selama di voice</label>'
        f'<select name="role_id">{"".join(role_opsi)}</select></div>'
        '<div class="medan"><label>Channel teks privat</label>'
        f'<select name="channel_privat">{_opsi_ya_tidak(data["channel_privat"])}</select></div>'
        '<div class="medan"><label>Hapus channel saat kosong</label>'
        f'<select name="hapus_kosong">{_opsi_ya_tidak(data["hapus_kosong"])}</select></div>'
        '<div class="medan"><label>Kategori channel privat</label>'
        f'<select name="kategori_id">{"".join(kategori_opsi)}</select></div>'
        '<button type="submit">Simpan setelan voice linking</button></form>'
    )

    daftar = voice_link.daftar_link(gid)
    if daftar:
        baris = "".join(
            "<tr>"
            f'<td><code>{item["voice_id"]}</code></td>'
            f'<td><code>{item["text_id"]}</code></td>'
            "<td>"
            '<form method="post" action="/api/konten" class="baris-form">'
            + dashboard_ui._hidden(gid, token, f"voice-lepas:{item['voice_id']}")
            + '<button type="submit" class="danger">Lepas</button></form>'
            "</td></tr>"
            for item in daftar[:20]
        )
        tabel = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>Voice</th><th>Channel teks</th><th></th></tr>"
            f"{baris}</table></div>"
        )
    else:
        tabel = (
            '<p class="muted">Belum ada channel privat. Channel dibuat otomatis saat ada '
            "member masuk voice (butuh izin *Manage Channels*).</p>"
        )

    status = (
        f'<p class="muted">Status: <b>{"aktif" if data["aktif"] else "nonaktif"}</b> · '
        f'<b>{data["jumlah_channel"]}</b> / {data["maks_channel"]} channel privat · '
        f'<b>{data["jumlah_berole"]}</b> member memakai role dari bot.</p>'
    )
    if data["enabled"] and not data["aktif"]:
        status += (
            '<p class="muted">⚠️ Sudah dinyalakan, tapi belum ada efek: pilih **role** '
            "atau nyalakan **channel teks privat**.</p>"
        )

    return (
        '<div class="subpanel" id="p-voice"><h3>🔗 Voice linking</h3>'
        '<p class="muted">Selama member berada di voice channel, bot memberi <b>role khusus</b> '
        "dan membuka <b>channel teks privat</b> untuk voice itu (hanya yang sedang di voice bisa "
        "melihat). Akses dicabut otomatis saat keluar, dan channel privat dihapus bila kosong. "
        "0 kuota AI · tanpa menyimpan isi pesan.</p>"
        f"{status}{setelan}<h4>Channel privat yang dikelola</h4>{tabel}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_voice(bot, gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel voice linking → `(berhasil, pesan)`."""
    import voice_link

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "voice-setelan":
        voice_link.set_config(
            gid,
            enabled=str(payload.get("enabled") or "0") not in ("0", "false", "off"),
            role_id=_id(payload.get("role_id")) or None,
            channel_privat=str(payload.get("channel_privat") or "0") not in ("0", "false", "off"),
            hapus_kosong=str(payload.get("hapus_kosong") or "1") not in ("0", "false", "off"),
            kategori_id=_id(payload.get("kategori_id")) or None,
        )
        await voice_link.save_voice_link_to_disk()
        data = voice_link.statistik(gid)
        return True, (
            f"Setelan voice linking disimpan: {'aktif' if data['aktif'] else 'nonaktif'} · "
            f"role {'<@&' + str(data['role_id']) + '>' if data['role_id'] else 'belum dipilih'} · "
            f"channel privat {'ya' if data['channel_privat'] else 'tidak'}."
        )

    if aksi.startswith("voice-lepas:"):
        voice_id = _id(aksi.split(":", 1)[1])
        text_id = voice_link.link_untuk(gid, voice_id)
        if not voice_link.hapus_link(gid, voice_id):
            return False, "Channel privat itu sudah tidak tercatat."
        guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
        kanal = None
        if guild is not None and text_id:
            get_channel = getattr(guild, "get_channel", None)
            kanal = get_channel(text_id) if callable(get_channel) else None
        pesan = "Catatan channel privat dilepas."
        if kanal is not None:
            try:
                await kanal.delete(reason="Voice link: dilepas dari dashboard")
                pesan = "Channel privat dihapus & catatannya dilepas."
            except Exception:  # pragma: no cover - jaring aman
                pesan = "Catatan dilepas, tapi channel tidak bisa dihapus (cek izin bot)."
        await voice_link.save_voice_link_to_disk()
        return True, pesan

    return False, f"Aksi voice linking `{aksi or '-'}` tidak dikenal."
