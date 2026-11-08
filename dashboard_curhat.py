"""Panel **Curhat anonim** di halaman Konten & interaksi — server-rendered.

Setelan (channel, jeda, tautan), daftar curhat terakhir (nomor + penanda hash, **tanpa teks**),
dan tombol hapus catatan per curhat. Jalur tulis: `POST /api/konten` (`curhat-*`).
"""

from __future__ import annotations

import time

import dashboard_ui


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _waktu(nilai: float) -> str:
    try:
        return time.strftime("%d %b %H:%M", time.localtime(float(nilai or 0)))
    except (OSError, ValueError):
        return "-"


def render_curhat_block(bot, guild_id: int, token: str) -> str:
    """Panel curhat untuk halaman 🧩 Konten & interaksi."""
    import confessions

    gid = int(guild_id or 0)
    data = confessions.statistik(gid)
    daftar = confessions.daftar(gid, limit=15)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    kanal = list(getattr(guild, "text_channels", []) or [])[:80]

    opsi_channel = _opsi_channel_curhat(kanal, data["channel_id"])
    setelan = _setelan_curhat(gid, token, data, opsi_channel)
    tabel = _tabel_curhat(gid, token, daftar)
    status = _status_curhat(data)

    return (
        '<div class="subpanel" id="p-curhat"><h3>💌 Curhat anonim</h3>'
        '<p class="muted">Satu channel khusus untuk curhat tanpa nama. Bot hanya menyimpan '
        "<b>nomor, waktu, dan penanda hash</b> penulis (bukan ID, bukan isi pesan) — jadi staf "
        "bisa melihat apakah satu orang membanjiri channel tanpa tahu siapa.</p>"
        f"{status}{setelan}<h4>Curhat terakhir</h4>{tabel}</div>"
    )


def _opsi_channel_curhat(kanal, dipilih: int) -> str:
    """Daftar <option> channel curhat dengan satu yang terpilih."""
    opsi_channel = '<option value="0">— belum dipilih —</option>' + "".join(
        '<option value="{0}"{1}>#{2}</option>'.format(
            int(getattr(ch, "id", 0)),
            " selected" if int(getattr(ch, "id", 0)) == dipilih else "",
            dashboard_ui._esc(str(getattr(ch, "name", "-"))),
        )
        for ch in kanal
    )

    return opsi_channel


def _setelan_curhat(gid: int, token: str, data: dict, opsi_channel: str) -> str:
    """Form setelan curhat."""
    opsi_ya_tidak = lambda nilai: (
        f'<option value="1"{" selected" if nilai else ""}>Ya</option>'
        f'<option value="0"{" selected" if not nilai else ""}>Tidak</option>'
    )  # noqa: E731


    setelan = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "curhat-setelan")
        + f'<div class="medan"><label>Channel curhat</label>'
        f'<select name="channel_id">{opsi_channel}</select></div>'
        '<div class="medan"><label>Fitur curhat</label><select name="enabled">'
        f'{opsi_ya_tidak(data["dinyalakan"])}</select></div>'
        '<div class="medan"><label>Izinkan tautan</label><select name="izinkan_link">'
        f'{opsi_ya_tidak(data["izinkan_link"])}</select></div>'
        '<div class="medan"><label>Jeda per orang (menit)</label>'
        f'<input type="number" name="jeda_menit" min="1" max="1440" '
        f'value="{max(1, data["cooldown_sec"] // 60)}"></div>'
        '<button type="submit">Simpan setelan curhat</button></form>'
    )

    return setelan


def _tabel_curhat(gid: int, token: str, daftar: list) -> str:
    """Tabel curhat terakhir atau ajakan kosong."""
    if daftar:
        baris = "".join(
            "<tr>"
            f'<td><b>#{item["nomor"]}</b></td>'
            f'<td class="muted">{_waktu(item.get("dibuat"))}</td>'
            f'<td><code>{dashboard_ui._esc(item.get("penulis") or "-")}</code></td>'
            "<td>"
            '<form method="post" action="/api/konten" class="baris-form">'
            + dashboard_ui._hidden(gid, token, f"curhat-hapus:{item['nomor']}")
            + '<button type="submit" class="danger">Hapus catatan</button></form>'
            "</td></tr>"
            for item in daftar
        )
        tabel = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>Nomor</th><th>Waktu</th><th>Penanda penulis</th><th></th></tr>"
            f"{baris}</table></div>"
            '<p class="muted">Isi curhat <b>tidak</b> disimpan di dashboard; hapus pesannya '
            "lewat <code>/curhat hapus nomor:…</code>.</p>"
        )
    else:
        tabel = (
            '<p class="muted">Belum ada curhat. Anggota mengirim lewat '
            "<code>/curhat kirim teks:…</code> dan bot memposting tanpa nama.</p>"
        )

    return tabel


def _status_curhat(data: dict) -> str:
    """Baris status + peringatan channel belum dipilih."""
    status = (
        f'<p class="muted">Status: <b>{"aktif" if data["aktif"] else "nonaktif"}</b> · '
        f'<b>{data["total"]}</b> curhat tercatat · <b>{data["penulis_unik"]}</b> penanda penulis '
        f'unik · nomor terakhir <b>#{data["nomor_terakhir"]}</b></p>'
    )

    if not data["channel_id"]:
        status += (
            '<p class="muted">⚠️ Channel curhat belum dipilih — fitur belum bisa dipakai '
            "walau sakelarnya aktif.</p>"
        )

    return status


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_curhat(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel curhat → `(berhasil, pesan)`."""
    import confessions

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "curhat-setelan":
        menit = max(1, min(1440, _id(payload.get("jeda_menit")) or 5))
        confessions.set_config(
            gid,
            enabled=str(payload.get("enabled") or "0") not in ("0", "false", "off"),
            channel_id=_id(payload.get("channel_id")) or None,
            izinkan_link=str(payload.get("izinkan_link") or "0") not in ("0", "false", "off"),
            cooldown_sec=menit * 60,
        )
        await confessions.save_confessions_to_disk()
        data = confessions.statistik(gid)
        kanal = f"<#{data['channel_id']}>" if data["channel_id"] else "belum dipilih"
        return True, (
            f"Setelan curhat disimpan: {'aktif' if data['aktif'] else 'nonaktif'} · "
            f"channel {kanal} · jeda {data['cooldown_sec'] // 60} menit."
        )

    if aksi.startswith("curhat-hapus:"):
        nomor = _id(aksi.split(":", 1)[1])
        terhapus = confessions.hapus(gid, nomor)
        if terhapus is None:
            return False, f"Curhat #{nomor} tidak ada di catatan."
        await confessions.save_confessions_to_disk()
        return True, (
            f"Catatan curhat #{nomor} dihapus. Pesan di Discord tetap ada — hapus lewat "
            "`/curhat hapus`."
        )

    return False, f"Aksi curhat `{aksi or '-'}` tidak dikenal."
