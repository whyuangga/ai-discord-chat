"""Panel **Channel statistik** di halaman Konten & interaksi — tanpa JS.

Menampilkan 7 penghitung (anggota, manusia, bot, online, boost, tiket terbuka,
langganan notifikasi sosial) beserta angka terkini, dan membiarkan operator
mengganti ikon tiap channel dari HP. Jalur tulis: `POST /api/konten`
(`stats-emoji:<kunci>`, `stats-segarkan`).
"""

from __future__ import annotations

import dashboard_ui

# Satuan interval pembaruan channel statistik (detik) → teks manusia.
def _menit(detik: object) -> str:
    try:
        nilai = int(float(detik or 0))
    except (TypeError, ValueError):
        return "-"
    if nilai <= 0:
        return "manual"
    if nilai % 3600 == 0:
        return f"{nilai // 3600} jam"
    if nilai % 60 == 0:
        return f"{nilai // 60} menit"
    return f"{nilai} detik"


def collect(bot, guild_id: int) -> dict:
    """Ringkasan status channel statistik + angka terkini untuk satu server."""
    import server_features as sf

    gid = int(guild_id or 0)
    cfg = sf.serverstats_guilds.get(gid) or {}
    guild = None
    if bot is not None and hasattr(bot, "get_guild"):
        try:
            guild = bot.get_guild(gid)
        except Exception:  # pragma: no cover - jaring aman
            guild = None

    angka = sf.hitung_statistik(guild) if guild is not None else {}
    emoji = sf.stats_emojis(gid)
    jenis = sf.stats_channel_type(gid)
    label_jenis = str((sf.STATS_CHANNEL_TYPES.get(jenis) or {}).get("label") or jenis)

    baris = []
    for kunci, bawaan, label in sf.STATS_CHANNEL_SPECS:
        nilai = angka.get(kunci)
        baris.append(
            {
                "kunci": kunci,
                "label": label,
                "emoji": emoji.get(kunci, bawaan),
                "nilai": sf.format_number(nilai) if nilai is not None else "—",
            }
        )

    return {
        "aktif": bool(cfg.get("enabled")),
        "jenis": label_jenis,
        "kategori": str(cfg.get("category_name") or sf.STATS_CATEGORY_NAME),
        "interval": _menit(sf.SERVERSTATS_UPDATE_SEC),
        "terakhir": float(cfg.get("last_update_at") or 0.0),
        "jumlah_channel": len([k for k in (cfg.get("channels") or {}) if cfg["channels"][k]]),
        "baris": baris,
        "guild_ada": guild is not None,
    }


def render_stats_block(bot, guild_id: int, token: str) -> str:
    """Panel channel statistik: status, tabel angka, & form ikon per channel."""
    import server_features as sf

    gid = int(guild_id or 0)
    data = collect(bot, gid)
    lencana = (
        '<span class="lencana ok">aktif</span>'
        if data["aktif"]
        else '<span class="lencana">nonaktif</span>'
    )

    baris_html = ""
    for item in data["baris"]:
        kunci = item["kunci"]
        tampil = dashboard_ui._esc(item["emoji"]) or "<i>tanpa ikon</i>"
        baris_html += (
            f'<tr><td>{tampil} {dashboard_ui._esc(item["label"])}</td>'
            f'<td class="angka">{dashboard_ui._esc(item["nilai"])}</td>'
            '<td><form method="post" action="/api/konten" class="baris-form">'
            + dashboard_ui._hidden(gid, token, f"stats-emoji:{kunci}")
            + f'<input type="text" name="nilai" value="{dashboard_ui._esc(item["emoji"])}" '
            'maxlength="8" size="4" placeholder="-">'
            '<button type="submit">Simpan</button></form></td></tr>'
        )

    segarkan = (
        '<form method="post" action="/api/konten" class="baris-form">'
        + dashboard_ui._hidden(gid, token, "stats-segarkan")
        + '<button type="submit">🔄 Segarkan sekarang</button></form>'
    )

    catatan = "" if data["aktif"] else (
        '<p class="muted">Nyalakan lewat setelan <b>Statistik server (voice)</b> di halaman ini; '
        "channel penghitung akan dibuat otomatis.</p>"
    )
    if data["aktif"] and not data["guild_ada"]:
        catatan += (
            '<p class="muted">Server belum ada di cache bot, jadi angka tampil “—” sampai '
            "bot tersambung.</p>"
        )

    return (
        '<div class="subpanel" id="p-statistik"><h3>📊 Channel statistik</h3>'
        f'<p class="muted">Status: {lencana} · jenis <b>{dashboard_ui._esc(data["jenis"])}</b> '
        f'· kategori <b>{dashboard_ui._esc(data["kategori"])}</b> '
        f'· diperbarui tiap <b>{dashboard_ui._esc(data["interval"])}</b> '
        f'· {data["jumlah_channel"]}/{len(sf.STATS_CHANNEL_SPECS)} channel terpasang.</p>'
        f"{catatan}"
        '<table><thead><tr><th>Channel</th><th class="angka">Angka</th>'
        f"<th>Ikon</th></tr></thead><tbody>{baris_html}</tbody></table>"
        '<p class="muted">Isi <b>-</b> untuk menghapus ikon. Discord membatasi 2 rename per '
        "10 menit per channel, jadi angka tidak selalu real-time.</p>"
        f'<div class="baris-aksi">{segarkan}</div></div>'
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================


async def aksi_stats(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel statistik → `(berhasil, pesan)`."""
    import server_features as sf

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi.startswith("stats-emoji:"):
        kunci = aksi.split(":", 1)[1].strip()
        valid = {key for key, _, _ in sf.STATS_CHANNEL_SPECS}
        if kunci not in valid:
            return False, f"Channel statistik `{kunci or '-'}` tidak dikenal."
        nilai = str(payload.get("nilai") or "").strip()
        if sf.serverstats_guilds.get(gid) is None:
            return False, "Statistik server belum aktif — nyalakan dulu setelan Statistik server."
        sf.set_serverstats_emojis(gid, {kunci: nilai or "-"})
        await sf.save_server_features_to_disk()
        tampil = sf.stats_emojis(gid).get(kunci) or "tanpa ikon"
        return True, f"Ikon channel `{kunci}` disimpan ({tampil})."

    if aksi == "stats-segarkan":
        cfg = sf.serverstats_guilds.get(gid)
        if cfg is None:
            return False, "Statistik server belum aktif."
        cfg["last_update_at"] = 0.0  # watcher berikutnya langsung memperbarui
        await sf.save_server_features_to_disk()
        return True, "Antrean segarkan disiapkan — channel diperbarui pada putaran berikutnya."

    return False, f"Aksi statistik `{aksi or '-'}` tidak dikenal."
