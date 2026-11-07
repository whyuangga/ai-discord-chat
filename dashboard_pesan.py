"""Aksi konten dari dashboard: kirim embed/webhook, kelola pengumuman, tautan,
panel, formulir, & webhook.

Semua fungsi di sini mengembalikan `(berhasil, pesan)` berbahasa Indonesia dan
**tidak** memakai kuota AI. Yang menyentuh Discord hanya `kirim`, `buat_panel`,
dan `hapus_webhook`; sisanya murni JSON lokal.
"""

import logging

logger = logging.getLogger("gemini_bot.dashboard_pesan")

JENIS_KONTEN = ("pengumuman", "tautan", "panel", "formulir", "webhook", "pemicu")
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


def _ambil_channel_sync(bot, guild_id: int, channel_id: int):
    """Cari channel dari cache saja (tanpa await) — untuk pratinjau."""
    if channel_id <= 0:
        return None
    getter = getattr(bot, "get_channel", None)
    channel = getter(channel_id) if callable(getter) else None
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


async def kirim(bot, guild_id: int, data: dict, banner=None) -> tuple[bool, str]:
    """Kirim pesan/embed ke channel, opsional dengan identitas webhook & banner.

    `banner` adalah `discord.File` hasil unggahan dashboard; bila ada, gambar embed
    memakai lampiran itu (`attachment://<nama>`) sehingga tidak butuh URL publik.
    """
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
    nama_banner = str(getattr(banner, "filename", "") or "") if banner is not None else ""
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
    gambar_final = f"attachment://{nama_banner}" if nama_banner else gambar
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
            berkas=banner,
        )
        if not ok:
            return False, pesan or "Gagal mengirim lewat webhook."
        await webhook_identity.save_to_disk()
        return True, f"Terkirim ke {getattr(channel, 'mention', 'channel')} lewat identitas **{identitas}**."

    embed = None
    if judul or warna is not None or footer or gambar_final:
        embed = discord.Embed(
            title=judul or None,
            description=isi or None,
            colour=warna or discord.Colour.blurple(),
        )
        if footer:
            embed.set_footer(text=footer)
        if gambar_final:
            embed.set_image(url=gambar_final)

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
    if banner is not None:
        kwargs["file"] = banner

    try:
        await channel.send(**kwargs)
    except discord.Forbidden:
        return False, "Bot tidak punya izin mengirim pesan di channel itu."
    except discord.HTTPException as exc:
        logger.warning("Kirim dari dashboard gagal: %s", exc)
        return False, "Discord menolak pesan itu (embed tidak valid atau channel terkunci)."
    return True, f"Terkirim ke {getattr(channel, 'mention', 'channel')}."


def pratinjau(bot, guild_id: int, data: dict, banner=None) -> dict:
    """Siapkan tampilan embed **tanpa mengirim** (dipakai tombol “Pratinjau”).

    Kembalikan dict berisi isian yang sudah dirender (variabel pesan diganti),
    label channel tujuan, nama banner, dan daftar `peringatan` yang perlu dicek.
    """
    import message_template

    gid = _to_int(guild_id)
    channel_id = _to_int((data or {}).get("channel"))
    channel = _ambil_channel_sync(bot, gid, channel_id)
    channel_label = (
        f"#{getattr(channel, 'name', channel_id)}" if channel is not None else "channel tidak ditemukan"
    )

    judul = _bersih(data, "judul", 256)
    isi = _bersih(data, "isi", MAX_ISI)
    footer = _bersih(data, "footer", 200)
    gambar = _bersih(data, "gambar", 400)
    identitas = _bersih(data, "identitas", 80)
    avatar = _bersih(data, "avatar", 400)
    tombol_label = _bersih(data, "tombol_label", 80)
    tombol_url = _bersih(data, "tombol_url", 400)
    warna_teks = _bersih(data, "warna", 20)
    nama_banner = str(getattr(banner, "filename", "") or "") if banner is not None else ""

    peringatan: list[str] = []
    guild = _guild_dari(bot, gid)
    if guild is not None:
        judul = message_template.render(judul, guild=guild, channel=channel)
        isi = message_template.render(isi, guild=guild, channel=channel)

    if channel is None:
        peringatan.append("Channel tujuan belum dipilih atau bot tidak punya akses.")
    if not judul and not isi:
        peringatan.append("Isi pesan atau judul embed masih kosong.")
    if len(judul) > 256:
        peringatan.append("Judul lebih dari 256 karakter — Discord akan memotongnya.")
    if len(isi) > 4000:
        peringatan.append("Isi lebih dari 4000 karakter — sisanya tidak terkirim.")

    warna = _warna(warna_teks)
    if warna_teks and warna is None:
        peringatan.append("Warna tidak valid — pakai `#5865F2` atau nama seperti `blurple`.")

    for token in (message_template.unknown_tokens(judul) + message_template.unknown_tokens(isi)):
        peringatan.append(f"Variabel `{{{token}}}` tidak dikenal, jadi ditampilkan apa adanya.")

    if gambar and not gambar.lower().startswith(("http://", "https://")):
        peringatan.append("URL gambar harus dimulai `http://` atau `https://`.")
    if tombol_url and not tombol_url.lower().startswith(("http://", "https://")):
        peringatan.append("URL tombol harus dimulai `http://` atau `https://`.")
    if bool(tombol_label) != bool(tombol_url):
        peringatan.append("Tombol butuh label **dan** URL sekaligus.")
    if identitas and tombol_label:
        peringatan.append("Tombol link tidak bisa dipakai saat mengirim lewat webhook.")
    if identitas and len(identitas) > 80:
        peringatan.append("Nama identitas webhook maksimal 80 karakter.")

    return {
        "judul": judul,
        "isi": isi,
        "warna": warna_teks,
        "footer": footer,
        "gambar": (
            f"attachment://{nama_banner}" if nama_banner
            else gambar
        ),
        "identitas": identitas,
        "avatar": avatar,
        "tombol_label": tombol_label,
        "tombol_url": tombol_url,
        "channel": channel_id,
        "channel_label": channel_label,
        "banner": nama_banner,
        "peringatan": peringatan,
    }


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
async def buat_panel(bot, guild_id: int, data: dict, banner=None) -> tuple[bool, str]:
    """Buat panel menu sederhana lalu kirim ke channel (tombol ditambah di Discord).

    `banner` (`discord.File`) dikirim sebagai gambar panel; URL lampirannya otomatis
    disimpan ke `menu["banner_url"]` oleh `menu_builder.send_panel`.
    """
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
    message = await menu_builder.send_panel(bot, menu, channel, banner_file=banner)
    if message is None:
        return False, "Panel tersimpan, tetapi Discord menolak pengirimannya (cek izin bot)."
    await menu_builder.save_menus_to_disk()
    return True, f"Panel **{judul}** terkirim ke {getattr(channel, 'mention', 'channel')}."


# ==============================================================================
# GANTI / HAPUS BANNER PANEL YANG SUDAH TERKIRIM
# ==============================================================================
async def _pesan_panel(bot, guild_id: int, menu: dict):
    """Ambil (channel, message) untuk panel yang sudah terkirim. `(None, None)` bila gagal."""
    channel = await _ambil_channel(bot, guild_id, _to_int(menu.get("channel_id")))
    if channel is None:
        return None, None
    try:
        message = await channel.fetch_message(_to_int(menu.get("message_id")))
    except Exception:  # pragma: no cover - NotFound/Forbidden/HTTP
        return channel, None
    return channel, message


def _lampiran_panel(menu: dict, nama_banner: str, guild=None):
    """View panel dengan referensi banner `attachment://` (atau tanpa banner)."""
    import menu_builder

    ref = f"attachment://{nama_banner}" if nama_banner else ""
    return menu_builder.build_view(menu, banner_override=ref or "", guild=guild)


async def ganti_banner_panel(bot, guild_id: int, ref: str, banner=None) -> tuple[bool, str]:
    """Ganti banner panel yang sudah terkirim (edit pesan asli, tanpa kirim ulang).

    `banner` = `discord.File` dari unggahan dashboard. `None` berarti **hapus** banner.
    """
    import menu_builder

    gid = _to_int(guild_id)
    menu = menu_builder.get_menu(gid, str(ref or "")) if gid else None
    if menu is None:
        return False, "Panel tidak ditemukan."

    if not menu.get("message_id"):
        return False, (
            "Panel ini belum terkirim, jadi belum punya banner. Kirim dulu lewat "
            "`/menu kirim` (atau buat panel baru), lalu ganti bannernya dari sini."
        )
    channel, message = await _pesan_panel(bot, gid, menu)
    if channel is None:
        return False, "Channel panel tidak ditemukan (mungkin sudah dihapus)."
    if message is None:
        return False, (
            "Pesan panel tidak ditemukan. Kirim ulang panelnya dulu lewat "
            "`/menu kirim`, lalu ganti bannernya dari sini."
        )

    nama = str(getattr(banner, "filename", "") or "") if banner is not None else ""
    guild = _guild_dari(bot, gid)
    # Untuk menghapus banner, kosongkan dulu agar `build_view` tidak memakai URL lama.
    if not nama:
        menu_builder.set_banner(menu, None)
    view = _lampiran_panel(menu, nama, guild)

    try:
        if banner is not None:
            await message.edit(view=view, attachments=[banner])
        else:
            await message.edit(view=view, attachments=[])
    except Exception as exc:
        logger.warning("Ganti banner panel gagal (%s) — mencoba versi embed klasik.", exc)
        try:
            embed = menu_builder.build_fallback_embed(menu)
            if banner is not None:
                await message.edit(embed=embed, view=None, attachments=[banner])
            else:
                await message.edit(embed=embed, view=None, attachments=[])
        except Exception as exc2:
            logger.warning("Ganti banner panel gagal total: %s", exc2)
            return False, "Discord menolak perubahan banner (cek izin bot di channel itu)."

    if banner is not None:
        lampiran = list(getattr(message, "attachments", None) or [])
        if lampiran:
            menu_builder.set_banner(menu, str(getattr(lampiran[0], "url", "") or "")[:400])
    try:
        bot.add_view(
            menu_builder.build_view(menu, guild=guild),
            message_id=_to_int(menu.get("message_id")),
        )
    except Exception as exc:  # pragma: no cover - depends on client state
        logger.debug("Efek samping opsional gagal: %s", exc)
    await menu_builder.save_menus_to_disk()
    if banner is None:
        return True, f"Banner panel **{menu.get('title') or ref}** dihapus."
    return True, f"Banner panel **{menu.get('title') or ref}** diganti."


# ==============================================================================
# FORMULIR (MODAL)
# ==============================================================================
def kolom_dari_baris(data: dict, batas: int = 5) -> str:
    """Susun teks kolom dari baris visual form (`kolom_label_1`, `kolom_jenis_1`, …).

    Hasilnya memakai sintaks yang dipahami `modal_forms.parse_fields`, mis.
    `Nama | Asal:panjang?`. Mengembalikan `""` bila semua baris kosong.
    """
    bagian: list[str] = []
    for nomor in range(1, batas + 1):
        label = _bersih(data, f"kolom_label_{nomor}", 45)
        if not label:
            continue
        jenis = _bersih(data, f"kolom_jenis_{nomor}", 20).lower()
        wajib = _bersih(data, f"kolom_wajib_{nomor}", 20).lower()
        potongan = label.replace("|", "/")
        if jenis in ("panjang", "paragraf", "long"):
            potongan += ":panjang"
        if wajib not in ("on", "1", "ya", "wajib", "true"):
            potongan += "?"
        bagian.append(potongan)
    return " | ".join(bagian)


async def tambah_formulir(guild_id: int, data: dict) -> tuple[bool, str]:
    """Buat formulir (modal); tombolnya dipasang lewat `/menu form tombol`."""
    import modal_forms

    gid = _to_int(guild_id)
    nama = _bersih(data, "judul", 100)
    # Mode visual (baris label/jenis/wajib) diutamakan; teks bebas tetap didukung.
    kolom = kolom_dari_baris(data) or _bersih(data, "kolom", 900)
    if not nama:
        return False, "Nama formulir wajib diisi."
    if not kolom:
        return False, "Isi minimal satu kolom (label kolom pertama tidak boleh kosong)."
    form, galat = modal_forms.create_form(
        gid,
        nama,
        kolom,
        description=_bersih(data, "isi", 500),
        channel_id=_to_int((data or {}).get("channel")) or None,
        color=_bersih(data, "warna", 20) or None,
    )
    if form is None:
        return False, " ".join(galat) or "Formulir gagal dibuat."
    await modal_forms.save_to_disk()
    pesan = f"Formulir **{form.get('name')}** dibuat dengan {len(form.get('fields') or [])} kolom."
    if galat:
        pesan += " Catatan: " + " ".join(galat)
    return True, pesan


# ==============================================================================
# PEMICU SAAT MEMBER BERGABUNG
# ==============================================================================
async def pasang_pemicu(guild_id: int, data: dict) -> tuple[bool, str]:
    """Pasang alur otomatis saat member baru bergabung."""
    import flows
    import flow_triggers

    gid = _to_int(guild_id)
    channel_id = _to_int((data or {}).get("channel"))
    teks = _bersih(data, "alur", 900)
    umur = max(0, _to_int((data or {}).get("umur_akun")))
    if channel_id <= 0:
        return False, "Pilih channel untuk pesan/thread sambutan."
    if not teks:
        return False, "Alur wajib diisi, mis. `+role:123 > umum:Selamat datang {member.mention}`."
    langkah, galat = flows.parse(teks)
    if not langkah:
        return False, " ".join(galat) or "Alur tidak valid."
    trigger, galat2 = flow_triggers.set_trigger(
        gid, langkah, channel_id=channel_id, min_age_days=umur
    )
    if trigger is None:
        return False, " ".join(galat2) or "Pemicu gagal dipasang."
    await flow_triggers.save_to_disk()
    return True, f"Pemicu gabung dipasang: {len(trigger.get('steps') or [])} langkah."


async def hapus_pemicu(guild_id: int) -> tuple[bool, str]:
    """Hapus alur pemicu gabung server."""
    import flow_triggers

    if not flow_triggers.remove_trigger(_to_int(guild_id)):
        return False, "Pemicu gabung belum dipasang."
    await flow_triggers.save_to_disk()
    return True, "Pemicu gabung dihapus."


# ==============================================================================
# DAFTAR & HAPUS KONTEN
# ==============================================================================
def _daftar_pengumuman(gid: int) -> list:
    """Kumpulkan pengumuman milik server; kosong bila modulnya gagal dimuat."""
    hasil: list = []
    try:
        import engagement

        for item in engagement.list_announcements(gid):
            hasil.append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Pengumuman")[:60],
                    "ringkas": engagement.describe_announcement(item),
                    "aktif": bool(item.get("enabled", True)),
                    "channel": str(item.get("channel_id") or ""),
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("Daftar pengumuman gagal dimuat: %s", exc)

    return hasil


def _daftar_tautan(gid: int) -> list:
    """Kumpulkan tautan milik server; kosong bila modulnya gagal dimuat."""
    hasil: list = []
    try:
        import link_embed

        for item in link_embed.list_links(gid):
            hasil.append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Tautan")[:60],
                    "ringkas": str(item.get("target") or ""),
                    "url": str(item.get("url") or ""),
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("Daftar tautan gagal dimuat: %s", exc)

    return hasil


def _daftar_panel(gid: int) -> list:
    """Kumpulkan panel menu milik server; kosong bila modulnya gagal dimuat."""
    hasil: list = []
    try:
        import menu_builder

        for item in menu_builder.list_menus(gid):
            hasil.append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Panel")[:60],
                    "ringkas": f"{menu_builder.count_items(item)} tombol",
                    "terkirim": bool(item.get("message_id")),
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("Daftar panel menu gagal dimuat: %s", exc)

    return hasil


def _daftar_formulir(gid: int) -> list:
    """Kumpulkan formulir milik server; kosong bila modulnya gagal dimuat."""
    hasil: list = []
    try:
        import modal_forms

        for item in modal_forms.list_forms(gid):
            hasil.append(
                {
                    "id": str(item.get("id")),
                    "judul": str(item.get("title") or "Formulir")[:60],
                    "ringkas": f"{len(item.get('fields') or [])} kolom",
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("Daftar formulir gagal dimuat: %s", exc)

    return hasil


def _daftar_webhook(gid: int, bot=None) -> list:
    """Kumpulkan webhook milik server; kosong bila modulnya gagal dimuat."""
    hasil: list = []
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
            hasil.append(
                {
                    "id": channel_id,
                    "judul": f"#{nama}" if nama else f"channel {channel_id}",
                    "ringkas": f"webhook {data.get('webhook_id')}",
                    "channel": channel_id,
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("Daftar webhook gagal dimuat: %s", exc)

    return hasil


def _daftar_pemicu(gid: int) -> list:
    """Kumpulkan pemicu alur milik server; kosong bila modulnya gagal dimuat."""
    hasil: list = []
    try:
        import flow_triggers

        alur = flow_triggers.get_trigger(gid)
        if alur:
            hasil.append(
                {
                    "id": "aktif",
                    "judul": "Alur saat member bergabung",
                    "ringkas": f"{len(alur.get('steps') or [])} langkah • "
                               f"umur akun ≥ {int(alur.get('min_age_days') or 0)} hari",
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.debug("Daftar pemicu alur gagal dimuat: %s", exc)

    return hasil


def daftar_konten(guild_id: int, bot=None) -> dict:
    """Ringkasan konten server untuk ditampilkan di dashboard."""
    gid = _to_int(guild_id)
    return {
        "pengumuman": _daftar_pengumuman(gid),
        "tautan": _daftar_tautan(gid),
        "panel": _daftar_panel(gid),
        "formulir": _daftar_formulir(gid),
        "webhook": _daftar_webhook(gid, bot),
        "pemicu": _daftar_pemicu(gid),
    }


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

    if kunci == "pemicu":
        return await hapus_pemicu(gid)

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
    "kolom_dari_baris",
    "pratinjau",
    "buat_panel",
    "ganti_banner_panel",
    "daftar_konten",
    "hapus",
    "kirim",
    "tambah_pengumuman",
    "tambah_tautan",
    "ubah_pengumuman",
]
