"""Editor panel menu dari dashboard web — tambah/hapus tombol & dropdown tanpa Discord.

Dulu tombol panel hanya bisa ditambah lewat `/menu tombol-role`, `tombol-link`,
`tombol-command`, `alur`, atau `dropdown-role` di Discord. Modul ini menyediakan jalur
yang setara dari browser:

- `collect_panel(guild_id)` — daftar panel + isi tombol/opsi dropdown-nya.
- `tambah_item(bot, guild_id, data)` — tambah tombol peran/tautan/perintah/alur/formulir
  atau satu dropdown peran, lalu **menyegarkan panel** yang sudah terkirim.
- `hapus_item(bot, guild_id, data)` — hapus satu item (nomor urut, ID, atau label).

Semua fungsi mengembalikan `(berhasil, pesan)` berbahasa Indonesia, memakai aturan
`menu_builder` yang sama (batas 5 tombol / 5 dropdown / 25 opsi, role harus di bawah
role bot), dan **tidak** memakai kuota AI.
"""

import logging

logger = logging.getLogger("gemini_bot.dashboard_panel")

JENIS_ITEM = ("peran", "tautan", "perintah", "alur", "formulir", "dropdown")
JENIS_LABEL = {
    "role": "Peran",
    "link": "Tautan",
    "command": "Perintah",
    "flow": "Alur",
    "form": "Formulir",
    "dropdown": "Dropdown",
}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _bersih(data: dict, key: str, limit: int = 200) -> str:
    return str((data or {}).get(key) or "").strip()[:limit]


# ==============================================================================
# BACA: DAFTAR PANEL + ISINYA
# ==============================================================================
def _ringkas_item(item: dict) -> str:
    """Keterangan singkat satu tombol/opsi untuk ditampilkan di dashboard."""
    kind = str(item.get("kind") or "")
    if kind == "role":
        return f"role <@&{_to_int(item.get('role_id'))}>"
    if kind == "link":
        return str(item.get("url") or "")[:120]
    if kind == "command":
        return f"/{str(item.get('command') or '').replace('_', ' ')}"
    if kind == "flow":
        return f"{len(item.get('flow') or [])} langkah"
    if kind == "form":
        return f"formulir `{item.get('form_id')}`"
    return kind or "-"


def collect_panel(guild_id: int, *, batas_panel: int = 10) -> dict:
    """Daftar panel server + tombol & opsi dropdown-nya."""
    import menu_builder

    gid = _to_int(guild_id)
    panel: list[dict] = []
    try:
        menus = menu_builder.list_menus(gid)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal membaca panel: %s", exc)
        menus = []

    for menu in menus[: max(1, int(batas_panel))]:
        tombol = []
        for item in menu.get("buttons") or []:
            tombol.append(
                {
                    "ref": str(item.get("id") or ""),
                    "label": str(item.get("label") or "-")[:80],
                    "jenis": JENIS_LABEL.get(str(item.get("kind")), "Tombol"),
                    "detail": _ringkas_item(item),
                }
            )
        dropdown = []
        for posisi, grup in enumerate(menu.get("dropdowns") or [], start=1):
            dropdown.append(
                {
                    "ref": str(grup.get("id") or f"d{posisi}"),
                    "label": str(grup.get("placeholder") or "Dropdown")[:80],
                    "ringkas": f"{len(grup.get('options') or [])} opsi",
                    "opsi": [
                        {
                            "ref": str(opt.get("id") or ""),
                            "label": str(opt.get("label") or "-")[:80],
                            "detail": _ringkas_item(opt),
                        }
                        for opt in (grup.get("options") or [])
                    ],
                }
            )
        panel.append(
            {
                "id": str(menu.get("id")),
                "judul": str(menu.get("title") or "Panel")[:80],
                "deskripsi": str(menu.get("description") or "")[:160],
                "terkirim": bool(menu.get("message_id")),
                "tombol": tombol,
                "dropdown": dropdown,
                "jumlah": menu_builder.count_items(menu),
            }
        )

    return {
        "guild": gid,
        "items": panel,
        "verifikasi": status_verifikasi(gid),
        "statistik": {
            "panel": len(panel),
            "tombol": sum(len(p["tombol"]) for p in panel),
            "dropdown": sum(len(p["dropdown"]) for p in panel),
        },
    }


def daftar_perintah() -> list[tuple[str, str]]:
    """Pilihan perintah aman untuk tombol perintah: `[(kunci, "/perintah")]`."""
    import menu_builder

    hasil: list[tuple[str, str]] = []
    for kunci, spec in menu_builder.SAFE_COMMANDS.items():
        hasil.append((str(kunci), str(spec.get("desc") or kunci)))
    return hasil


# ==============================================================================
# TULIS: TAMBAH / HAPUS ITEM
# ==============================================================================
def _ambil_menu(guild_id: int, ref: str):
    import menu_builder

    acuan = str(ref or "").strip()
    if not acuan:
        return None
    menu = menu_builder.get_menu(guild_id, acuan)
    if menu is None and acuan.isdigit():
        daftar = menu_builder.list_menus(guild_id)
        posisi = int(acuan) - 1
        if 0 <= posisi < len(daftar):
            menu = daftar[posisi]
    return menu


def _role_label(guild, role_id: int) -> str:
    role = guild.get_role(role_id) if callable(getattr(guild, "get_role", None)) else None
    return str(getattr(role, "name", "") or f"role {role_id}")[:100]


async def tambah_item(bot, guild_id: int, data: dict) -> tuple[bool, str]:
    """Tambah satu tombol/dropdown ke panel dari dashboard."""
    import menu_builder

    gid = _to_int(guild_id)
    menu = _ambil_menu(gid, _bersih(data, "panel", 60))
    if menu is None:
        return False, "Panel tidak ditemukan di server ini."

    jenis = _bersih(data, "jenis", 20).lower() or "peran"
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    label = _bersih(data, "label", 80)
    emoji = _bersih(data, "emoji", 32) or None
    gaya = _bersih(data, "gaya", 12).lower() or "biru"
    catatan: list[str] = []

    if jenis == "peran":
        role_id = _to_int(data.get("role"))
        if role_id <= 0:
            return False, "Pilih role yang mau dijadikan tombol."
        if guild is not None:
            boleh, alasan = menu_builder.check_role_usable(guild, role_id)
            if not boleh:
                return False, alasan
        label = label or (_role_label(guild, role_id) if guild is not None else "Role")
        item = menu_builder.add_role_button(menu, role_id, label, emoji=emoji, style=gaya)
        if item is None:
            return False, "Gagal menambah tombol role (batas 5 tombol atau role sudah ada)."
        pesan = f"Tombol role **{item['label']}** ditambahkan ke panel **{menu.get('title')}**."
    elif jenis == "tautan":
        url = _bersih(data, "url", 400)
        if not url.startswith(("http://", "https://")):
            return False, "URL tombol tautan harus diawali `http://` atau `https://`."
        item = menu_builder.add_link_button(menu, label or "Buka", url, emoji=emoji)
        if item is None:
            return False, "Gagal menambah tombol tautan (batas 5 tombol atau URL tidak valid)."
        pesan = f"Tombol tautan **{item['label']}** ditambahkan ke panel **{menu.get('title')}**."
    elif jenis == "perintah":
        kunci = _bersih(data, "perintah", 60)
        if kunci not in menu_builder.SAFE_COMMANDS:
            return False, "Perintah itu tidak ada di daftar aman (hanya perintah info)."
        item = menu_builder.add_command_button(
            menu, kunci, label=label or None, emoji=emoji, style=gaya,
            visibility=_bersih(data, "visibilitas", 12) or "auto",
        )
        if item is None:
            return False, "Gagal menambah tombol perintah (batas 5 tombol)."
        pesan = f"Tombol perintah **{item['label']}** ditambahkan ke panel **{menu.get('title')}**."
    elif jenis == "alur":
        import flows

        langkah, galat = flows.parse(_bersih(data, "alur", 900))
        if not langkah:
            return False, " ".join(galat) or "Alur tidak valid."
        item = menu_builder.add_flow_button(menu, label or "Aksi", langkah, emoji=emoji, style=gaya)
        if item is None:
            return False, "Gagal menambah tombol alur (batas 5 tombol atau langkah kosong)."
        catatan.extend(galat)
        pesan = f"Tombol alur **{item['label']}** ditambahkan ke panel **{menu.get('title')}**."
    elif jenis == "formulir":
        import modal_forms

        form = modal_forms.get_form(gid, _bersih(data, "formulir", 60))
        if form is None:
            return False, "Formulir tidak ditemukan — buat dulu di bagian **Buat konten**."
        item = menu_builder.add_form_button(menu, form, label=label or None, emoji=emoji, style=gaya)
        if item is None:
            return False, "Gagal menambah tombol formulir (batas 5 tombol)."
        pesan = f"Tombol formulir **{item['label']}** ditambahkan ke panel **{menu.get('title')}**."
    elif jenis == "dropdown":
        role_ids: list[int] = []
        for kunci in ("role", "role2", "role3"):
            rid = _to_int(data.get(kunci))
            if rid > 0 and rid not in role_ids:
                role_ids.append(rid)
        if not role_ids:
            return False, "Pilih minimal satu role untuk dropdown."
        if guild is not None:
            for rid in role_ids:
                boleh, alasan = menu_builder.check_role_usable(guild, rid)
                if not boleh:
                    return False, alasan
        opsi = [
            {
                "role_id": rid,
                "label": _role_label(guild, rid) if guild is not None else f"Role {rid}",
            }
            for rid in role_ids
        ]
        grup = menu_builder.add_dropdown(
            menu, _bersih(data, "label", 150) or "Pilih role…", opsi,
            exclusive=_bersih(data, "eksklusif", 12).lower() in ("on", "1", "ya", "true"),
        )
        if grup is None:
            return False, "Gagal menambah dropdown (batas 5 dropdown per panel)."
        pesan = (
            f"Dropdown **{grup['placeholder']}** ({len(grup['options'])} opsi) "
            f"ditambahkan ke panel **{menu.get('title')}**."
        )
    else:
        return False, f"Jenis `{jenis}` tidak dikenal. Pilih: {', '.join(JENIS_ITEM)}."

    await menu_builder.save_menus_to_disk()
    tersegar = await menu_builder.refresh_panel(bot, menu)
    if tersegar:
        pesan += " Panel di Discord langsung diperbarui."
    elif menu.get("message_id"):
        pesan += " Panel tersimpan, tetapi pesan lama gagal disegarkan (cek izin bot)."
    else:
        pesan += " Panel belum terkirim, jadi belum ada pesan yang diperbarui."
    if catatan:
        pesan += " Catatan: " + " ".join(catatan)
    return True, pesan


async def hapus_item(bot, guild_id: int, data: dict) -> tuple[bool, str]:
    """Hapus satu tombol/opsi dropdown dari panel, lalu segarkan pesannya."""
    import menu_builder

    gid = _to_int(guild_id)
    menu = _ambil_menu(gid, _bersih(data, "panel", 60))
    if menu is None:
        return False, "Panel tidak ditemukan di server ini."
    ref = _bersih(data, "item", 80)
    if not ref:
        return False, "Isi nomor urut, ID, atau label item yang mau dihapus."

    label = menu_builder.remove_item(menu, ref)
    if label is None:
        return False, f"Item `{ref}` tidak ada di panel **{menu.get('title')}**."

    await menu_builder.save_menus_to_disk()
    pesan = f"Item **{label}** dihapus dari panel **{menu.get('title')}**."
    if await menu_builder.refresh_panel(bot, menu):
        pesan += " Panel di Discord sudah diperbarui."
    else:
        pesan += " Pesan lama di Discord tidak berubah (panel belum terkirim atau bot tidak punya akses)."
    return True, pesan


# ==============================================================================
# PANEL VERIFIKASI (setara /verifikasi pasang)
# ==============================================================================
def status_verifikasi(guild_id: int) -> dict:
    """Status gerbang verifikasi server: aktif, channel, role."""
    try:
        import community_tools

        cfg = community_tools.verification_guilds.get(_to_int(guild_id)) or {}
    except Exception:  # pragma: no cover - jaring aman
        cfg = {}
    return {
        "aktif": bool(cfg.get("enabled")),
        "channel": str(cfg.get("channel_id") or ""),
        "role": str(cfg.get("role_id") or ""),
    }


async def pasang_verifikasi(bot, guild_id: int, data: dict) -> tuple[bool, str]:
    """Pasang panel verifikasi (tombol sekali klik → role) dari dashboard."""
    import community_tools
    from views import VerificationGateView

    gid = _to_int(guild_id)
    channel_id = _to_int(data.get("channel"))
    role_id = _to_int(data.get("role"))
    if channel_id <= 0:
        return False, "Pilih channel tempat panel verifikasi dipasang."
    if role_id <= 0:
        return False, "Pilih role yang diberikan setelah member verifikasi."

    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    if guild is None:
        return False, "Server tidak ditemukan."

    role = guild.get_role(role_id) if callable(getattr(guild, "get_role", None)) else None
    if role is None:
        return False, "Role itu sudah tidak ada di server ini."
    if callable(getattr(role, "is_default", None)) and role.is_default():
        return False, "Role `@everyone` tidak bisa dipakai — pilih role khusus (mis. `Member`)."
    me = getattr(guild, "me", None)
    top = getattr(me, "top_role", None) if me is not None else None
    if top is not None and role >= top:
        return False, "Role itu di atas role bot. Pindahkan role bot lebih tinggi dulu."

    channel = await _saluran(bot, gid, channel_id)
    if channel is None:
        return False, "Channel itu tidak ditemukan di server ini."

    embed = community_tools.build_verification_embed(
        str(getattr(guild, "name", "") or "")[:100],
        str(getattr(role, "name", "") or "Member"),
        _bersih(data, "catatan", 200),
    )
    try:
        pesan = await channel.send(embed=embed, view=VerificationGateView())
    except Exception as exc:
        logger.warning("Panel verifikasi dari dashboard gagal dikirim: %s", exc)
        return False, (
            "Discord menolak panel verifikasi "
            "(cek izin **Kirim Pesan**, **Embed Links**, & **Manage Roles**)."
        )

    community_tools.set_verification_config(
        gid,
        channel_id=channel_id,
        role_id=role_id,
        message_id=_to_int(getattr(pesan, "id", 0)),
        enabled=True,
    )
    await community_tools.save_community_tools_to_disk()
    acuan = str(getattr(channel, "mention", f"<#{channel_id}>"))
    return True, (
        f"✅ Gerbang verifikasi aktif di {acuan}. Member yang menekan **Verifikasi Saya** "
        f"otomatis mendapat <@&{role_id}>."
    )


async def matikan_verifikasi(guild_id: int) -> tuple[bool, str]:
    """Matikan gerbang verifikasi (tombol lama tidak lagi memberi role)."""
    import community_tools

    gid = _to_int(guild_id)
    cfg = community_tools.verification_guilds.get(gid) or {}
    if not cfg.get("enabled"):
        return False, "Gerbang verifikasi memang sudah nonaktif."
    cfg["enabled"] = False
    await community_tools.save_community_tools_to_disk()
    return True, "Gerbang verifikasi dinonaktifkan. Tombol lama tidak akan memberi role lagi."


async def _saluran(bot, guild_id: int, channel_id: int):
    import dashboard_tiket

    return await dashboard_tiket._saluran(bot, guild_id, channel_id)


__all__ = [
    "JENIS_ITEM",
    "JENIS_LABEL",
    "collect_panel",
    "daftar_perintah",
    "hapus_item",
    "matikan_verifikasi",
    "pasang_verifikasi",
    "status_verifikasi",
    "tambah_item",
]
