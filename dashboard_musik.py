"""Panel **Musik** di halaman Konten & interaksi — server-rendered, tanpa JS.

Mengatur setelan pemutar yang dipakai `/musik` dan panel Discord: volume default,
role DJ, pengumuman panel, filter default, autoplay, mode pengulangan, dan batas
antrean. Ikut menampilkan status node Lavalink supaya penyebab "musik tidak bunyi"
langsung kelihatan.

Jalur tulis: `POST /api/konten` dengan aksi `musik-setelan`.
"""

from __future__ import annotations

import logging

import dashboard_ui

logger = logging.getLogger("gemini_bot.dashboard_musik")

# Nilai bawaan bila berkas setelan belum ada.
_VOLUME_BAWAAN = 60
_FILTER_BAWAAN = "off"
_LOOP_BAWAAN = "mati"
_QUEUE_BAWAAN = 50


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _angka(nilai: object, bawaan: int) -> int:
    try:
        return int(str(nilai).strip())
    except (TypeError, ValueError):
        return bawaan


def _pilihan(opsi: list[tuple[str, str]], terpilih: str) -> str:
    """Deretan `<option>` dengan satu nilai ditandai `selected`."""
    terpilih = str(terpilih)
    return "".join(
        f'<option value="{dashboard_ui._esc(nilai)}"'
        f'{" selected" if str(nilai) == terpilih else ""}>'
        f"{dashboard_ui._esc(label)}</option>"
        for nilai, label in opsi
    )


def _opsi_ya_tidak(nilai: bool) -> str:
    return (
        f'<option value="1"{" selected" if nilai else ""}>Ya</option>'
        f'<option value="0"{" selected" if not nilai else ""}>Tidak</option>'
    )


def _status_node(snapshot: dict) -> str:
    """Ringkasan kondisi node Lavalink (bukan rahasia: tanpa password)."""
    if not snapshot.get("library"):
        return (
            '<p class="muted">⚠️ <b>Wavelink tidak terpasang.</b> '
            "Musik nonaktif sampai dependensinya dipasang.</p>"
        )
    if not snapshot.get("configured"):
        return (
            '<p class="muted">⚠️ <b>Node belum dikonfigurasi.</b> Isi '
            "<code>LAVALINK_URI</code> dan <code>LAVALINK_PASSWORD</code> di "
            "berkas <code>.env</code>, lalu jalankan ulang bot.</p>"
        )
    if snapshot.get("ready"):
        badge = '<b style="color:#2ecc71">🟢 tersambung</b>'
    elif snapshot.get("connecting"):
        badge = '<b style="color:#f1c40f">🟡 menyambung…</b>'
    else:
        badge = '<b style="color:#e74c3c">🔴 terputus</b>'

    uri = dashboard_ui._esc(snapshot.get("uri") or "—")
    baris = (
        f'<p class="muted">Node Lavalink: {badge} · '
        f'<b>{_angka(snapshot.get("connected"), 0)}</b> tersambung · '
        f'<b>{_angka(snapshot.get("connecting"), 0)}</b> menyambung · '
        f'<b>{_angka(snapshot.get("disconnected"), 0)}</b> terputus<br>'
        f"URI: <code>{uri}</code></p>"
    )
    if not snapshot.get("ready"):
        baris += (
            '<p class="muted">Node lama <code>triniumhost</code> sudah tidak '
            "melayani. Ganti URI/password dengan node aktif dari daftar publik "
            "<code>lavalink.darrennathanael.com</code> (pilih <b>Lavalink 4.2.0+</b> "
            "agar lolos enkripsi suara DAVE Discord), lalu nyalakan ulang bot. "
            "Tombol musik tetap tampil, tetapi lagu belum bisa diputar.</p>"
        )
    return baris


def render_musik_block(bot, guild_id: int, token: str) -> str:
    """Panel musik untuk halaman 🧩 Konten & interaksi."""
    import music

    gid = int(guild_id or 0)
    cfg = music.get_music_settings(gid)
    snapshot = music.node_snapshot()
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None

    volume = max(1, min(150, _angka(cfg.get("volume"), _VOLUME_BAWAAN)))
    filter_aktif = str(cfg.get("filter") or _FILTER_BAWAAN)
    loop_aktif = str(cfg.get("loop") or _LOOP_BAWAAN)
    queue_aktif = _angka(cfg.get("max_queue"), _QUEUE_BAWAAN)
    announce = bool(cfg.get("announce", True))
    autoplay = bool(cfg.get("autoplay", False))
    dj_role = _id(cfg.get("dj_role_id"))

    # Opsi role DJ (tanpa @everyone)
    role_opsi = ['<option value="0">— semua member boleh kontrol —</option>']
    for role in list(getattr(guild, "roles", []) or [])[:80]:
        rid = _id(getattr(role, "id", 0))
        if not rid:
            continue
        pemeriksa = getattr(role, "is_default", None)
        if callable(pemeriksa) and pemeriksa():
            continue
        role_opsi.append(
            f'<option value="{rid}"{" selected" if rid == dj_role else ""}>'
            f'@{dashboard_ui._esc(getattr(role, "name", "-"))}</option>'
        )

    filter_opsi = _pilihan(list(music.FILTER_PRESETS.items()), filter_aktif)
    loop_opsi = _pilihan(list(music.LOOP_MODES.items()), loop_aktif)
    volume_opsi = _pilihan(
        [(str(v), f"{v}%") for v in range(10, 151, 10)], str(volume)
    )
    if str(volume) not in {str(v) for v in range(10, 151, 10)}:
        volume_opsi += f'<option value="{volume}" selected>{volume}%</option>'

    setelan = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "musik-setelan")
        + '<div class="medan"><label>Volume default</label>'
        f'<select name="volume">{volume_opsi}</select></div>'
        '<div class="medan"><label>Role DJ (pengontrol musik)</label>'
        f'<select name="dj_role_id">{"".join(role_opsi)}</select></div>'
        '<div class="medan"><label>Filter default</label>'
        f'<select name="filter">{filter_opsi}</select></div>'
        '<div class="medan"><label>Mode pengulangan (loop)</label>'
        f'<select name="loop">{loop_opsi}</select></div>'
        '<div class="medan"><label>Batas antrean (lagu)</label>'
        f'<input type="number" name="max_queue" min="1" max="500" '
        f'value="{queue_aktif}"></div>'
        '<div class="medan"><label>Panel pengumuman lagu</label>'
        f'<select name="announce">{_opsi_ya_tidak(announce)}</select></div>'
        '<div class="medan"><label>Autoplay (radio lagu sejenis)</label>'
        f'<select name="autoplay">{_opsi_ya_tidak(autoplay)}</select></div>'
        '<button type="submit">Simpan setelan musik</button></form>'
    )

    ringkas = (
        f'<p class="muted">Volume <b>{volume}%</b> · filter '
        f'<b>{dashboard_ui._esc(music.FILTER_PRESETS.get(filter_aktif, filter_aktif))}</b> · '
        f'loop <b>{dashboard_ui._esc(music.LOOP_MODES.get(loop_aktif, loop_aktif))}</b> · '
        f'antrean maks <b>{queue_aktif}</b> lagu · autoplay '
        f'<b>{"aktif" if autoplay else "nonaktif"}</b>.</p>'
    )

    return (
        '<div class="subpanel" id="p-musik"><h3>🎵 Musik</h3>'
        '<p class="muted">Setelan ini dipakai panel pemutar di Discord '
        '(<code>/musik panel</code>): 15 tombol grid 5×3, mini-player, dan '
        "dropdown <i>Select a suggested song</i> berisi rekomendasi lagu sejenis. "
        "0 kuota AI.</p>"
        f"{_status_node(snapshot)}{ringkas}{setelan}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_musik(bot, gid: int, aksi: str, payload: dict) -> tuple[bool, str] | None:
    """Jalankan aksi panel musik. `None` bila aksi bukan milik panel ini."""
    if not str(aksi or "").startswith("musik-"):
        return None

    import music

    gid = int(gid or 0)
    if aksi != "musik-setelan":
        return False, f"Aksi musik `{aksi or '-'}` tidak dikenal."

    volume = max(1, min(150, _angka(payload.get("volume"), _VOLUME_BAWAAN)))
    filter_name = str(payload.get("filter") or _FILTER_BAWAAN)
    loop = str(payload.get("loop") or _LOOP_BAWAAN)
    max_queue = max(1, min(500, _angka(payload.get("max_queue"), _QUEUE_BAWAAN)))
    announce = str(payload.get("announce") or "1") not in ("0", "false", "off")
    autoplay = str(payload.get("autoplay") or "0") not in ("0", "false", "off")
    dj_role = _id(payload.get("dj_role_id")) or None

    cfg = music.set_music_settings(
        gid,
        volume=volume,
        dj_role_id=dj_role,
        announce=announce,
        filter_name=filter_name,
        loop=loop,
        max_queue=max_queue,
        autoplay=autoplay,
    )
    await music.save_music_settings_to_disk()

    # Terapkan ke pemutar yang sedang aktif, kalau ada.
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    player = music.get_player(guild) if guild is not None else None
    if player is not None:
        try:
            await player.set_volume(int(cfg["volume"]))
        except Exception as exc:  # pragma: no cover - node terputus
            logger.debug("Gagal menerapkan volume ke pemutar aktif: %s", exc)
        music.set_autoplay(player, autoplay)
        mode = music.queue_mode_from_key(loop)
        if mode is not None and getattr(player, "queue", None) is not None:
            try:
                player.queue.mode = mode
            except Exception as exc:  # pragma: no cover - queue versi lama
                logger.debug("Gagal menerapkan mode loop: %s", exc)

    return True, (
        f"Setelan musik disimpan: volume **{cfg['volume']}%** · filter "
        f"**{music.FILTER_PRESETS.get(cfg.get('filter', 'off'), 'off')}** · "
        f"loop **{music.LOOP_MODES.get(cfg.get('loop', 'mati'), 'mati')}** · "
        f"antrean maks **{cfg['max_queue']}** lagu · autoplay "
        f"**{'aktif' if cfg['autoplay'] else 'nonaktif'}**."
    )
