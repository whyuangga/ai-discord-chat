"""Aksi konten dari dashboard: kirim embed/webhook, kelola pengumuman, tautan,
panel, formulir, & webhook.

Semua fungsi di sini mengembalikan `(berhasil, pesan)` berbahasa Indonesia dan
**tidak** memakai kuota AI. Yang menyentuh Discord hanya `kirim`, `buat_panel`,
dan `hapus_webhook`; sisanya murni JSON lokal.
"""

import logging

logger = logging.getLogger("gemini_bot.dashboard_pesan")

JENIS_KONTEN = ("pengumuman", "tautan", "panel", "formulir", "webhook")
MAX_ISI = 3500


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _bersih(data: dict, key: str, limit: int = 200) -> str:
    return str((data or {}).get(key) or "").strip()[:limit]


# ==============================================================================
# KIRIM PESAN / EMBED
# ==============================================================================
async def _ambil_channel(bot, guild_id: int, channel_id: int):
    """Cari channel dari cache, lalu `fetch_channel` bila belum ada (thread/forum)."""
    if channel_id <= 0:
        return None
    getter = getattr(bot, "get_channel", None)
    channel = getter(channel_id) if callable(getter) else None
    if channel is not None:
        guild = getattr(channel, "guild", None)
        if guild is not None and _to_int(getattr(guild, "id", 0)) != _to_int(guild_id):
            return None
        return channel
    fetcher = getattr(bot, "fetch_channel", None)
    if callable(fetcher):
        try:
            channel = await fetcher(channel_id)
        except Exception:  # pragma: no cover - NotFound/Forbidden/HTTP
            return None
    if channel is None:
        return None
    guild = getattr(channel, "guild", None)
    if guild is not None and _to_int(getattr(guild, "id", 0)) != _to_int(guild_id):
        return None
    return channel


def _guild_dari(bot, guild_id: int):
    getter = getattr(bot, "get_guild", None)
    if callable(getter):
        return getter(_to_int(guild_id))
    return None


def _warna(nilai: str):
    """Ubah teks warna (#5865F2 / blurple) menjadi `discord.Colour` atau None."""
    text = str(nilai or "").strip()
    if not text:
        return None
    try:
        import modal_forms

        return modal_forms.parse_color(text)
    except Exception:  # pragma: no cover - jaring aman
        return None


async def kirim(bot, guild_id: int, data: dict) -> tuple[bool, str]:
    """Kirim pesan/embed ke channel, opsional dengan identitas webhook kustom."""
    import discord

    import message_template
    import webhook_identity

    gid = _to_int(guild_id)
    channel_id = _to_int((data or {}).get("channel"))
    channel = await _ambil_channel(bot, gid, channel_id)
    if channel is None:
        return False, "Channel tidak ditemukan. Pastikan bot ada di server & channel itu."

    judul = _bersih(data, "judul", 256)
    isi = _bersih(data, "isi", MAX_ISI)
    footer = _bersih(data, "footer", 200)
    gambar = _bersih(data, "gambar", 400)
    identitas = _bersih(data, "identitas", 80)
    avatar = _bersih(data, "avatar", 400)
    tombol_label = _bersih(data, "tombol_label", 80)
    tombol_url = _bersih(data, "tombol_url", 400)

    if not judul and not isi:
        return False, "Isi pesan atau judul embed harus diisi."

    guild = _guild_dari(bot, gid)
    if guild is not None:
        judul = message_template.render(judul, guild=guild, channel=channel)
        isi = message_template.render(isi, guild=guild, channel=channel)

    warna = _warna(_bersih(data, "warna", 20))
    if _bersih(data, "warna", 20) and warna is None:
        return False, "Warna tidak valid — pakai format `#5865F2` atau nama seperti `blurple`."

    if gambar and not gambar.lower().startswith(("http://", "https://")):
        return False, "URL gambar harus dimulai `http://` atau `https://`."
    if tombol_url and not tombol_url.lower().startswith(("http://", "https://")):
        return False, "URL tombol harus dimulai `http://` atau `https://`."

    if identitas:
        ok, pesan = await webhook_identity.kirim_sebagai(
            channel,
            nama=identitas,
            isi=isi,
            judul=judul,
            avatar=avatar or None,
            warna=warna,
            footer=footer or None,
        )
        if not ok:
            return False, pesan or "Gagal mengirim lewat webhook."
        await webhook_identity.save_to_disk()
        return True, f"Terkirim ke {getattr(channel, 'mention', 'channel')} lewat identitas **{identitas}**."

    embed = None
    if judul or warna is not None or footer or gambar:
        embed = discord.Embed(
            title=judul or None,
            description=isi or None,
            colour=warna or discord.Colour.blurple(),
        )
        if footer:
            embed.set_footer(text=footer)
        if gambar:
            embed.set_image(url=gambar)

    kwargs: dict = {"allowed_mentions": discord.AllowedMentions.none()}
    if embed is not None:
        kwargs["embed"] = embed
        if not isi and not judul:
            kwargs["content"] = "​"
    else:
        kwargs["content"] = isi or "​"

    if tombol_label and tombol_url:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=tombol_label, url=tombol_url))
        kwargs["view"] = view

    try:
        await channel.send(**kwargs)
    except discord.Forbidden:
        return False, "Bot tidak punya izin mengirim pesan di channel itu."
    except discord.HTTPException as exc:
        logger.warning("Kirim dari dashboard gagal: %s", exc)
        return False, "Discord menolak pesan itu (embed tidak valid atau channel terkunci)."
    return True, f"Terkirim ke {getattr(channel, 'mention', 'channel')}."


# ==============================================================================
# PENGUMUMAN TERJADWAL
# ==============================================================================
async def tambah_pengumuman(guild_id: int, data: dict) -> tuple[bool, str]:
    """Buat pengumuman terjadwal dari form dashboard."""
    import engagement

    gid = _to_int(guild_id)
    channel_id = _to_int((data or {}).get("channel"))
    isi = _bersih(data, "isi", 1800)
    judul = _bersih(data, "judul", 256)
    jadwal = _bersih(data, "jadwal", 60)
    if channel_id <= 0:
        return False, "Pilih channel tujuan pengumuman."
    if not isi:
        return False, "Isi pengumuman tidak boleh kosong."
    spec = engagement.parse_announcement_schedule(jadwal or "harian 08:00")
    if spec is None:
        return False, "Jadwal tidak dikenali. Contoh: `08:00`, `mingguan senin 19:00`, `setiap 3 jam`."
    status, _cfg = engagement.add_announcement(
        gid, channel_id, isi, spec, title=judul or "Pengumuman"
    )
    if status == "penuh":
        return False, "Kuota pengumuman server sudah penuh — hapus yang lama dulu."
    if status == "kosong":
        return False, "Isi pengumuman tidak boleh kosong."
    await engagement.save_engagement_to_disk()
    return True, f"Pengumuman dibuat: **{engagement.describe_announcement(_cfg or {})}**."


async def ubah_pengumuman(guild_id: int, pengumuman_id: int, aktif: bool) -> tuple[bool, str]:
    """Nyalakan/matikan pengumuman tanpa menghapusnya."""
    import engagement

    if not engagement.set_announcement_enabled(_to_int(pengumuman_id), bool(aktif)):
        return False, "Pengumuman tidak ditemukan."
    await engagement.save_engagement_to_disk()
    return True, f"Pengumuman #{_to_int(pengumuman_id)} **{'diaktifkan' if aktif else 'dijeda'}**."


# ==============================================================================
# TAUTAN EMBED
# ==============================================================================
async def tambah_tautan(guild_id: int, data: dict) -> tuple[bool, str]:
    """Buat tautan embed (`/l/<kode>`) dari form dashboard."""
    import link_embed

    gid = _to_int(guild_id)
    judul = _bersih(data, "judul", 256)
    deskripsi = _bersih(data, "isi", 400)
    url = _bersih(data, "url", 400)
    gambar = _bersih(data, "gambar", 400)
    warna = _bersih(data, "warna", 20)
    if not url:
        return False, "URL tujuan wajib diisi."
    record, galat = link_embed.create_link(
        gid,
        title=judul,
        description=deskripsi,
        url=url,
        image=gambar,
        color=warna,
    )
    if record is None:
        return False, " ".join(galat) or "Tautan gagal dibuat."
    await link_embed.save_to_disk()
    return True, f"Tautan dibuat: {record.get('url')}"


# ==============================================================================
# PANEL MENU
# ==============================================================================
async def buat_panel(bot, guild_id: int, data: dict) -> tuple[bool, str]:
    """Buat panel menu sederhana lalu kirim ke channel (tombol ditambah di Discord)."""
    import menu_builder

    gid = _to_int(guild_id)
    judul = _bersih(data, "judul", 256)
    deskripsi = _bersih(data, "isi", 1800)
    channel_id = _to_int((data or {}).get("channel"))
    if not judul:
        return False, "Judul panel wajib diisi."
    if channel_id <= 0:
        return False, "Pilih channel untuk mengirim panel."
    menu = menu_builder.create_menu(gid, judul, description=deskripsi)
    if menu is None:
        return False, "Kuota panel server sudah penuh atau judul kosong."
    channel = await _ambil_channel(bot, gid, channel_id)
    if channel is None:
        return False, "Panel tersimpan, tetapi channel tidak ditemukan sehingga belum terkirim."
    message = await menu_builder.send_panel(bot, menu, channel)
    if message is None:
        return False, "Panel tersimpan, tetapi Discord menolak pengirimannya (cek izin bot)."
    await menu_builder.save_menus_to_disk()
    return True, f"Panel **{judul}** terkirim ke {getattr(channel, 'mention', 'channel')}."


# ==============================================================================
# DAFTAR & HAPUS KONTEN
# ==============================================================================
def daftar_konten(guild_id: int, bot=None) -> dict:
    """Ringkasan konten server untuk ditampilkan di dashboard."""
    gid = _to_int(guild_id)
    hasil: dict = {"pengumuman": [], "tautan": [], "panel": [], "formulir": [], "webhook": []}

    try:
        import engagement

        for item in engagement.list_announcements(gid):
            hasil["pengumuman"].append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Pengumuman")[:60],
                    "ringkas": engagement.describe_announcement(item),
                    "aktif": bool(item.get("enabled", True)),
                    "channel": str(item.get("channel_id") or ""),
                }
            )
    except Exception:  # pragma: no cover
        pass

    try:
        import link_embed

        for item in link_embed.list_links(gid):
            hasil["tautan"].append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Tautan")[:60],
                    "ringkas": str(item.get("target") or ""),
                    "url": str(item.get("url") or ""),
                }
            )
    except Exception:  # pragma: no cover
        pass

    try:
        import menu_builder

        for item in menu_builder.list_menus(gid):
            hasil["panel"].append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Panel")[:60],
                    "ringkas": f"{menu_builder.count_items(item)} tombol",
                    "terkirim": bool(item.get("message_id")),
                }
            )
    except Exception:  # pragma: no cover
        pass

    try:
        import modal_forms

        for item in modal_forms.list_forms(gid):
            hasil["formulir"].append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Formulir")[:60],
                    "ringkas": f"{len(item.get('fields') or [])} kolom",
                }
            )
    except Exception:  # pragma: no cover
        pass

    try:
        import webhook_identity

        prefix = f"{gid}:"
        for key, data in (webhook_identity._cache or {}).items():
            if not str(key).startswith(prefix):
                continue
            channel_id = str(key).split(":", 1)[1]
            nama = ""
            if bot is not None:
                channel = getattr(bot, "get_channel", lambda _id: None)(_to_int(channel_id))
                nama = str(getattr(channel, "name", "") or "")
            hasil["webhook"].append(
                {
                    "id": channel_id,
                    "judul": f"#{nama}" if nama else f"channel {channel_id}",
                    "ringkas": f"webhook {data.get('webhook_id')}",
                    "channel": channel_id,
                }
            )
    except Exception:  # pragma: no cover
        pass

    return hasil


async def hapus(bot, guild_id: int, jenis: str, ref: str) -> tuple[bool, str]:
    """Hapus satu konten (pengumuman/tautan/panel/formulir/webhook)."""
    gid = _to_int(guild_id)
    kunci = str(jenis or "").strip().lower()
    acuan = str(ref or "").strip()
    if kunci not in JENIS_KONTEN:
        return False, f"Jenis `{kunci or '-'}` tidak dikenal."
    if not acuan:
        return False, "ID konten tidak boleh kosong."

    if kunci == "pengumuman":
        import engagement

        if not engagement.remove_announcement(_to_int(acuan), gid):
            return False, "Pengumuman tidak ditemukan."
        await engagement.save_engagement_to_disk()
        return True, f"Pengumuman #{acuan} dihapus."

    if kunci == "tautan":
        import link_embed

        if link_embed.delete_link(gid, acuan) is None:
            return False, "Tautan tidak ditemukan."
        await link_embed.save_to_disk()
        return True, f"Tautan {acuan} dihapus."

    if kunci == "panel":
        import menu_builder

        if not menu_builder.delete_menu(gid, acuan):
            return False, "Panel tidak ditemukan."
        await menu_builder.save_menus_to_disk()
        return True, f"Panel {acuan} dihapus (pesan lama di Discord tidak ikut terhapus)."

    if kunci == "formulir":
        import modal_forms

        if not modal_forms.delete_form(gid, acuan):
            return False, "Formulir tidak ditemukan."
        await modal_forms.save_to_disk()
        return True, f"Formulir {acuan} dihapus."

    # webhook: `acuan` = channel id
    import webhook_identity

    channel = await _ambil_channel(bot, gid, _to_int(acuan))
    if channel is None:
        return False, "Channel webhook tidak ditemukan."
    ok, pesan = await webhook_identity.hapus_webhook(channel)
    if not ok:
        return False, pesan or "Gagal menghapus webhook."
    await webhook_identity.save_to_disk()
    return True, f"Webhook di channel `{acuan}` dihapus."


__all__ = [
    "JENIS_KONTEN",
    "buat_panel",
    "daftar_konten",
    "hapus",
    "kirim",
    "tambah_pengumuman",
    "tambah_tautan",
    "ubah_pengumuman",
]
