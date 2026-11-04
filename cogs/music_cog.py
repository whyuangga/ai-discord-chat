import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import music
from music import (
    FILTER_PRESETS,
    LOOP_MODES,
    MUSIC_SETUP_HINT,
    QUEUE_PAGE_SIZE,
    MusicUnavailable,
    announce_channels,
    apply_filter,
    build_now_playing_embed,
    build_player_embed,
    build_queue_embed,
    build_queue_page_embed,
    build_search_embed,
    can_control,
    close_panel,
    enqueue_tracks,
    ensure_nodes_alive,
    ensure_player,
    node_diagnosis,
    node_snapshot,
    format_duration,
    get_music_settings,
    get_player,
    loop_label_from_mode,
    music_panels,
    music_status,
    parse_seek,
    play_first_if_idle,
    remember_announce_channel,
    save_music_settings_to_disk,
    search_tracks,
    send_or_update_panel,
    set_autoplay,
    set_music_settings,
    skip_previous,
    track_title,
)
from config import MUSIC_MAX_QUEUE
from views import MusicPlayerView, QueuePaginationView

logger = logging.getLogger("gemini_bot.music_cog")


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _require_player(interaction: discord.Interaction):
    """Mengambil player aktif; mengirim pesan bantuan bila belum ada."""
    if not music.WAVELINK_AVAILABLE or not music.MUSIC_ENABLED:
        await interaction.response.send_message(MUSIC_SETUP_HINT, ephemeral=True)
        return None

    player = get_player(interaction.guild)
    if player is None or getattr(player, "channel", None) is None:
        await interaction.response.send_message(
            "⚠️ Belum ada musik yang diputar. Mulai dengan `/musik putar query:judul lagu`.",
            ephemeral=True,
        )
        return None
    if not can_control(player, interaction.user):
        await interaction.response.send_message(
            "⚠️ Kamu harus berada di **voice channel yang sama** dengan bot "
            "(atau punya role DJ / izin Admin) untuk mengontrol pemutaran.",
            ephemeral=True,
        )
        return None
    return player


class MusicSearchView(discord.ui.View):
    """Dropdown pemilih lagu dari hasil `/musik cari` (berlaku 60 detik)."""

    def __init__(self, tracks: list, requester_id: int):
        super().__init__(timeout=60)
        self.tracks = tracks[:5]
        self.requester_id = requester_id
        options = [
            discord.SelectOption(
                label=track_title(track, 90),
                value=str(idx),
                description=(f"{str(getattr(track, 'author', '') or '—')[:60]} • "
                             f"{'LIVE' if getattr(track, 'is_stream', False) else format_duration(getattr(track, 'length', 0))}")[:100],
                emoji="🎵",
            )
            for idx, track in enumerate(self.tracks)
        ]
        self.select_menu.options = options

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "💡 Jalankan `/musik cari` sendiri untuk memilih lagu.", ephemeral=True
            )
            return False
        return True

    @discord.ui.select(placeholder="🎧 Pilih lagu yang ingin diputar...", options=[])
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        try:
            track = self.tracks[int(select.values[0])]
        except (ValueError, IndexError):
            await interaction.response.send_message("⚠️ Pilihan lagu tidak valid.", ephemeral=True)
            return

        player, error = await ensure_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        try:
            started = await play_first_if_idle(player, [track], interaction.user)
            if not started:
                added, skipped = await enqueue_tracks(player, [track], interaction.user)
                if not added:
                    await interaction.response.send_message(
                        f"⚠️ Antrean penuh (maks **{MUSIC_MAX_QUEUE}** lagu).", ephemeral=True
                    )
                    return
        except Exception as exc:  # pragma: no cover - node mati
            await interaction.response.send_message(
                f"⚠️ Gagal memutar lagu: `{exc}`", ephemeral=True
            )
            return

        remember_announce_channel(interaction.guild.id, interaction.channel_id)
        embed = build_now_playing_embed(
            track,
            requester=interaction.user.display_name,
            queue_length=len(player.queue),
            volume=getattr(player, "volume", None),
            loop_label=loop_label_from_mode(getattr(player.queue, "mode", None)),
        )
        embed.title = ("🎶 " if started else "➕ Ditambahkan ke Antrean: ") + track_title(track, 90)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# /musik — Streaming Musik (Lavalink)
# ==============================================================================
musik_group = app_commands.Group(
    name="musik",
    description="Streaming musik dari YouTube/Spotify/SoundCloud via Lavalink",
    guild_only=True,
)


@musik_group.command(name="putar", description="Putar lagu atau playlist (judul, link YouTube, atau URL Spotify)")
@app_commands.describe(
    query="Judul lagu atau tautan (YouTube/Spotify/SoundCloud)",
    berikutnya="True untuk selalu menambahkan ke antrean tanpa memotong lagu yang sedang diputar",
)
async def musik_putar_cmd(
    interaction: discord.Interaction,
    query: str,
    berikutnya: bool = False,
):
    if interaction.guild is None:
        return
    await interaction.response.defer(ephemeral=False)

    try:
        tracks, playlist_name = await search_tracks(query)
    except MusicUnavailable as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return

    if not tracks:
        await interaction.followup.send(
            f"🔍 Tidak ada hasil untuk **{query[:100]}**. Coba kata kunci lain "
            "atau tempel tautan langsung dari YouTube/Spotify.",
            ephemeral=True,
        )
        return

    player, error = await ensure_player(interaction)
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return

    try:
        started = False
        if not berikutnya:
            started = await play_first_if_idle(player, tracks, interaction.user)
            remaining = tracks if not started else tracks[1:]
        else:
            remaining = tracks

        added, skipped = await enqueue_tracks(player, remaining, interaction.user)
    except Exception as exc:  # pragma: no cover - node mati
        detail = str(exc)
        if "CONNECTED state" in detail or "Node" in detail or "node" in detail.lower():
            await interaction.followup.send(
                "🎵 **Gagal memutar** — koneksi ke node musik terputus.\n" + node_diagnosis(),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"⚠️ Gagal memutar lagu: `{detail[:200]}`", ephemeral=True
            )
        return

    remember_announce_channel(interaction.guild.id, interaction.channel_id)

    # Panel pemutar ala Rythm (satu pesan yang di-edit, bukan pesan baru tiap lagu)
    if get_music_settings(interaction.guild.id).get("announce", True):
        await send_or_update_panel(
            interaction.client,
            interaction.guild.id,
            channel=interaction.channel,
            view=MusicPlayerView(),
        )

    if playlist_name:
        await interaction.followup.send(
            f"📥 **Playlist `{playlist_name[:80]}`** dimasukkan — "
            f"`{added + (1 if started else 0)}` lagu ditambahkan"
            + (f", `{skipped}` dilewati karena antrean penuh." if skipped else "."),
            ephemeral=True,
        )
        return

    if started:
        await interaction.followup.send(
            f"▶️ Memutar **{track_title(tracks[0], 80)}** — kontrol lewat panel di channel ini.",
            ephemeral=True,
        )
        return

    total_ms = sum(int(getattr(t, "length", 0) or 0) for t in remaining)
    await interaction.followup.send(
        f"➕ **{added} lagu** ditambahkan ke antrean (`{format_duration(total_ms)}`), "
        f"posisi setelah `{len(player.queue) - added}` lagu lain."
        + (f"\n⚠️ `{skipped}` lagu dilewati karena batas antrean **{MUSIC_MAX_QUEUE}**." if skipped else ""),
        ephemeral=True,
    )


@musik_group.command(name="cari", description="Cari lagu lalu pilih dari dropdown (tanpa harus tempel link)")
@app_commands.describe(query="Kata kunci pencarian lagu")
async def musik_cari_cmd(interaction: discord.Interaction, query: str):
    if interaction.guild is None:
        return
    await interaction.response.defer(ephemeral=True)

    try:
        tracks, _ = await search_tracks(query)
    except MusicUnavailable as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return

    if not tracks:
        await interaction.followup.send(
            f"🔍 Tidak ada hasil untuk **{query[:100]}**.", ephemeral=True
        )
        return

    await interaction.followup.send(
        embed=build_search_embed(query, tracks),
        view=MusicSearchView(tracks, interaction.user.id),
        ephemeral=True,
    )


@musik_group.command(name="antrean", description="Lihat antrean musik berhalaman (◀ ▶) beserta total durasi")
@app_commands.describe(halaman=f"Halaman antrean yang ingin dilihat ({QUEUE_PAGE_SIZE} lagu per halaman)")
async def musik_antrean_cmd(interaction: discord.Interaction, halaman: int = 1):
    if interaction.guild is None:
        return
    player = get_player(interaction.guild)
    if player is None:
        await interaction.response.send_message(
            "⚠️ Belum ada musik yang diputar.", ephemeral=True
        )
        return

    tracks = list(player.queue)
    view = QueuePaginationView(
        tracks,
        requester_id=interaction.user.id,
        page=max(0, int(halaman) - 1),
        now_playing=getattr(player, "current", None),
    )
    await interaction.response.send_message(embed=view._embed(), view=view, ephemeral=True)


@musik_group.command(name="sekarang", description="Lihat lagu yang sedang diputar beserta progresnya")
async def musik_sekarang_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = get_player(interaction.guild)
    current = getattr(player, "current", None) if player is not None else None
    if player is None or current is None:
        await interaction.response.send_message(
            "⏹️ Tidak ada lagu yang sedang diputar.", ephemeral=True
        )
        return

    settings = get_music_settings(interaction.guild.id)
    embed = build_player_embed(
        player,
        track=current,
        filter_name=settings.get("filter", "off"),
        autoplay=bool(settings.get("autoplay", False)),
        hint="Detail lagu aktif • pakai tombol pada panel untuk kontrol cepat",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@musik_group.command(name="lewati", description="Lewati lagu saat ini dan putar lagu berikutnya")
@app_commands.describe(jumlah="Berapa lagu yang ingin dilewati (default 1)")
async def musik_lewati_cmd(interaction: discord.Interaction, jumlah: int = 1):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    step = max(1, min(10, int(jumlah)))
    for _ in range(step - 1):
        try:
            player.queue.get()
        except Exception:
            break

    skipped_track = getattr(player, "current", None)
    try:
        await player.skip(force=True)
    except Exception as exc:  # pragma: no cover - node mati
        await interaction.response.send_message(f"⚠️ Gagal melewati lagu: `{exc}`", ephemeral=True)
        return

    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message(
        f"⏭️ Dilewati: **{track_title(skipped_track)}**" if skipped_track else "⏭️ Lagu dilewati.",
        ephemeral=True,
    )


@musik_group.command(name="sebelumnya", description="Putar kembali lagu sebelumnya dari riwayat antrean")
async def musik_sebelumnya_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    if not await skip_previous(player):
        await interaction.response.send_message(
            "⚠️ Belum ada riwayat lagu sebelumnya di sesi ini.", ephemeral=True
        )
        return

    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message("⏮️ Kembali ke lagu sebelumnya.", ephemeral=True)


@musik_group.command(name="seek", description="Lompat ke detik/menit tertentu pada lagu yang sedang diputar")
@app_commands.describe(posisi="Posisi tujuan: 90 (detik), 1:30, atau 01:02:03")
async def musik_seek_cmd(interaction: discord.Interaction, posisi: str):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    current = getattr(player, "current", None)
    target_ms = parse_seek(posisi)
    if target_ms is None:
        await interaction.response.send_message(
            "⚠️ Format posisi tidak valid. Contoh: `seek posisi:1:30` atau `seek posisi:95`.",
            ephemeral=True,
        )
        return
    if current is None:
        await interaction.response.send_message("⚠️ Tidak ada lagu yang diputar.", ephemeral=True)
        return

    length = int(getattr(current, "length", 0) or 0)
    if length and target_ms >= length:
        await interaction.response.send_message(
            f"⚠️ Posisi melebihi durasi lagu (`{format_duration(length)}`).", ephemeral=True
        )
        return

    try:
        await player.seek(target_ms)
    except Exception as exc:  # pragma: no cover - node menolak seek
        await interaction.response.send_message(f"⚠️ Gagal melompat: `{exc}`", ephemeral=True)
        return

    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message(
        f"⏩ Melompat ke `{format_duration(target_ms)}`.", ephemeral=True
    )


@musik_group.command(name="autoplay", description="Putar rekomendasi lagu otomatis saat antrean habis")
@app_commands.describe(aktif="True untuk menyalakan autoplay, False untuk mematikan")
async def musik_autoplay_cmd(interaction: discord.Interaction, aktif: bool = True):
    if interaction.guild is None:
        return

    player = get_player(interaction.guild)
    if player is not None and not can_control(player, interaction.user):
        await interaction.response.send_message(
            "⚠️ Kamu harus berada di voice channel yang sama dengan bot (atau punya role DJ).",
            ephemeral=True,
        )
        return

    if player is not None and not set_autoplay(player, aktif):
        await interaction.response.send_message(
            "⚠️ Node Lavalink ini belum mendukung autoplay.", ephemeral=True
        )
        return

    set_music_settings(interaction.guild.id, autoplay=aktif)
    await save_music_settings_to_disk()
    if player is not None:
        await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message(
        ("♾️ **Autoplay AKTIF** — lagu rekomendasi akan diputar otomatis saat antrean habis."
         if aktif else "➡️ **Autoplay NONAKTIF** — pemutaran berhenti saat antrean habis."),
        ephemeral=True,
    )


@musik_group.command(name="filter", description="Terapkan efek audio: bass boost, nightcore, 8D, vaporwave, dll.")
@app_commands.describe(jenis="Preset filter audio yang ingin dipakai")
@app_commands.choices(
    jenis=[
        app_commands.Choice(name=f"{label}", value=key) for key, label in FILTER_PRESETS.items()
    ]
)
async def musik_filter_cmd(interaction: discord.Interaction, jenis: app_commands.Choice[str]):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    ok = await apply_filter(player, jenis.value)
    if not ok:
        await interaction.response.send_message(
            "⚠️ Node Lavalink ini tidak mendukung filter audio.", ephemeral=True
        )
        return

    set_music_settings(interaction.guild.id, filter_name=jenis.value)
    await save_music_settings_to_disk()
    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message(
        f"🎛️ Filter audio: **{FILTER_PRESETS.get(jenis.value, jenis.name)}**", ephemeral=True
    )


@musik_group.command(name="jeda", description="Jeda pemutaran tanpa keluar dari voice channel")
async def musik_jeda_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    await player.pause(True)
    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message("⏸️ Musik dijeda. Lanjutkan dengan `/musik lanjut`.", ephemeral=True)


@musik_group.command(name="lanjut", description="Lanjutkan pemutaran yang sedang dijeda")
async def musik_lanjut_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    await player.pause(False)
    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message("▶️ Musik dilanjutkan.", ephemeral=True)


@musik_group.command(name="hentikan", description="Hentikan musik, kosongkan antrean, & keluarkan bot dari voice")
async def musik_hentikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    try:
        player.queue.clear()
        await player.stop()
        await player.disconnect()
    except Exception as exc:  # pragma: no cover - node mati
        logger.info("Gagal menghentikan musik: %s", exc)

    music.forget_announce_channel(interaction.guild.id)
    await close_panel(interaction.client, interaction.guild.id)
    await interaction.response.send_message(
        "⏹️ Musik dihentikan, antrean dikosongkan, & bot keluar dari voice channel.",
        ephemeral=True,
    )


@musik_group.command(name="volume", description="Atur volume pemutaran (1-150)")
@app_commands.describe(level="Volume baru dalam persen (1-150, default 60)")
async def musik_volume_cmd(interaction: discord.Interaction, level: int):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    value = max(1, min(150, int(level)))
    try:
        await player.set_volume(value)
    except Exception as exc:  # pragma: no cover - node mati
        await interaction.response.send_message(f"⚠️ Gagal mengubah volume: `{exc}`", ephemeral=True)
        return

    set_music_settings(interaction.guild.id, volume=value)
    await save_music_settings_to_disk()
    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    warning = "\n⚠️ Di atas 100% bisa menyebabkan distorsi suara." if value > 100 else ""
    await interaction.response.send_message(
        f"🔊 Volume diatur ke **{value}%**.{warning}\n*(disimpan sebagai volume default server ini)*",
        ephemeral=True,
    )


@musik_group.command(name="ulang", description="Atur mode pengulangan: mati, satu lagu, atau semua lagu")
@app_commands.describe(mode="Pilih mode pengulangan")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="🔁 Mati (putar sekali)", value="mati"),
        app_commands.Choice(name="🔂 Ulangi lagu ini", value="satu"),
        app_commands.Choice(name="🔁 Ulangi semua antrean", value="semua"),
    ]
)
async def musik_ulang_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    queue_mode = music.queue_mode_from_key(mode.value)
    player.queue.mode = queue_mode
    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message(
        f"🔁 Mode pengulangan: **{LOOP_MODES.get(mode.value, mode.name)}**", ephemeral=True
    )


@musik_group.command(name="acak", description="Acak urutan lagu di antrean")
async def musik_acak_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    if len(player.queue) < 2:
        await interaction.response.send_message(
            "⚠️ Antrean kurang dari 2 lagu, tidak ada yang bisa diacak.", ephemeral=True
        )
        return

    player.queue.shuffle()
    await send_or_update_panel(interaction.client, interaction.guild.id, view=MusicPlayerView())
    await interaction.response.send_message(
        f"🔀 **{len(player.queue)} lagu** di antrean berhasil diacak.", ephemeral=True
    )


@musik_group.command(name="panel", description="Kirim ulang panel pemutar ala Rythm di channel ini")
async def musik_panel_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    message = await send_or_update_panel(
        interaction.client,
        interaction.guild.id,
        channel=interaction.channel,
        force_new=True,
        view=MusicPlayerView(),
    )
    if message is None:
        await interaction.response.send_message(
            "⚠️ Panel tidak bisa dikirim. Pastikan bot punya izin **Kirim Pesan** & **Embed Links**.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        f"✅ Panel pemutar dikirim di {message.channel.mention}.", ephemeral=True
    )


@musik_group.command(name="pengaturan", description="Atur pengumuman Now Playing, role DJ, & volume default server")
@app_commands.describe(
    pengumuman="True untuk mengumumkan Now Playing otomatis di channel",
    role_dj="Role yang boleh mengontrol musik tanpa harus ikut voice channel",
    volume_default="Volume default saat bot bergabung (1-150)",
)
async def musik_pengaturan_cmd(
    interaction: discord.Interaction,
    pengumuman: bool | None = None,
    role_dj: discord.Role | None = None,
    volume_default: int | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    if pengumuman is None and role_dj is None and volume_default is None:
        cfg = get_music_settings(interaction.guild.id)
        dj = f"<@&{cfg['dj_role_id']}>" if cfg.get("dj_role_id") else "_belum diatur_"
        await interaction.response.send_message(
            f"🎛️ **Pengaturan Musik Server**\n"
            f"• **Status node:** {music_status()}\n"
            f"• **Volume default:** `{cfg['volume']}%`\n"
            f"• **Pengumuman Now Playing:** {'✅ Aktif' if cfg.get('announce', True) else '❌ Nonaktif'}\n"
            f"• **Role DJ:** {dj}\n"
            f"• **Batas antrean:** `{MUSIC_MAX_QUEUE}` lagu\n\n"
            f"Ubah dengan `/musik pengaturan pengumuman:True role_dj:@DJ volume_default:70`.",
            ephemeral=True,
        )
        return

    cfg = set_music_settings(
        interaction.guild.id,
        volume=volume_default,
        announce=pengumuman,
        dj_role_id=role_dj.id if role_dj else None,
    )
    await save_music_settings_to_disk()

    lines = []
    if pengumuman is not None:
        lines.append(f"• **Pengumuman Now Playing:** {'AKTIF' if pengumuman else 'NONAKTIF'}")
    if role_dj is not None:
        lines.append(f"• **Role DJ:** {role_dj.mention}")
    if volume_default is not None:
        lines.append(f"• **Volume default:** `{cfg['volume']}%`")
    await interaction.response.send_message(
        "🎛️ **Pengaturan musik diperbarui**\n" + "\n".join(lines), ephemeral=True
    )


@musik_group.command(name="status", description="Cek kesehatan node musik, antrean, & pengaturan server")
async def musik_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    player = get_player(interaction.guild)
    cfg = get_music_settings(interaction.guild.id)
    snap = node_snapshot()
    dj_role_id = cfg.get("dj_role_id")
    lines = [
        "🎵 **Status Musik**",
        f"• **Node Lavalink:** {music_status()}",
        f"• **Alamat node:** `{snap['uri'] or '—'}`",
        f"• **Voice channel:** {player.channel.mention if player and player.channel else '_belum bergabung_'}",
        f"• **Sedang diputar:** {track_title(player.current) if player and player.current else '_tidak ada_'}",
        f"• **Antrean:** `{len(player.queue) if player else 0}` lagu",
        f"• **Volume:** `{player.volume if player else cfg['volume']}%`",
        f"• **Filter audio:** `{FILTER_PRESETS.get(cfg.get('filter', 'off'), 'Mati')}`",
        f"• **Autoplay:** {'♾️ Aktif' if cfg.get('autoplay') else '➡️ Nonaktif'}",
        f"• **Pengumuman:** {'✅ Aktif' if cfg.get('announce', True) else '❌ Nonaktif'}",
        f"• **Channel pengumuman:** {f'<#{announce_channels[interaction.guild.id]}>' if interaction.guild.id in announce_channels else '_otomatis_'}",
        f"• **Role DJ:** {f'<@&{dj_role_id}>' if dj_role_id else '_belum diatur (opsional)_'}",
    ]

    # DJ hanya mengunci TOMBOL kontrol — memutar lagu tidak butuh role DJ.
    lines.append(
        "> Role DJ **tidak wajib untuk memutar lagu** — cukup masuk voice channel. "
        "DJ hanya untuk mengunci tombol kontrol (⏯️⏭️⏹️)."
    )
    if not snap["ready"]:
        lines.append("")
        lines.append(node_diagnosis())

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@musik_group.command(
    name="node",
    description="Diagnosa & sambung ulang node Lavalink tanpa restart bot (Admin)",
)
@app_commands.describe(sambung="True = paksa menyambung ulang node sekarang")
@app_commands.default_permissions(administrator=True)
async def musik_node_cmd(interaction: discord.Interaction, sambung: bool = False):
    """Menampilkan status teknis node & (opsional) memaksa reconnect."""
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    if not music.WAVELINK_AVAILABLE or not music.MUSIC_ENABLED:
        await interaction.response.send_message(MUSIC_SETUP_HINT, ephemeral=True)
        return

    if sambung:
        await interaction.response.defer(ephemeral=True)
        ok = await ensure_nodes_alive(interaction.client, force=True)
        snap = node_snapshot()
        head = "✅ **Node berhasil tersambung ulang.**" if ok else "⚠️ **Node masih belum tersambung.**"
    else:
        snap = node_snapshot()
        head = None

    rows = [
        f"• **Alamat:** `{snap['uri'] or '—'}`",
        f"• **Tersambung:** `{snap['connected']}` • **Menyambung:** `{snap['connecting']}` • **Terputus:** `{snap['disconnected']}`",
    ]
    for node in snap["nodes"]:
        rows.append(
            f"• `{node['identifier']}` → **{node['status']}** ({node['uri']}, {node['players']} player)"
        )
    if not snap["nodes"]:
        rows.append("• _Belum ada node terdaftar di Pool._")

    text = "🛰️ **Diagnosa Node Lavalink**\n" + "\n".join(rows)
    if head:
        text = f"{head}\n" + text
    if not snap["ready"]:
        text += "\n\n" + node_diagnosis()

    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


def register_music_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/musik` beserta listener event Lavalink (bila library tersedia)."""
    bot.tree.add_command(musik_group)

    if not music.WAVELINK_AVAILABLE:
        logger.warning("wavelink belum terpasang — command /musik hanya menampilkan panduan setup.")
        return

    @bot.event
    async def on_wavelink_node_ready(payload) -> None:
        node = getattr(payload, "node", None)
        logger.info(
            "✅ Node Lavalink siap: %s (%s) | sesi %s | %s player",
            getattr(node, "identifier", "?"),
            getattr(node, "uri", "?"),
            getattr(payload, "session_id", "?"),
            len(getattr(node, "players", {}) or {}),
        )

    @bot.event
    async def on_wavelink_node_closed(node, players) -> None:
        """Node terputus: beri peringatan di log + jadwalkan reconnect (tanpa loop baru)."""
        logger.warning(
            "⚠️ Node Lavalink terputus: %s (%s) | %s player terputus. "
            "Mencoba menyambung ulang otomatis…",
            getattr(node, "identifier", "?"),
            getattr(node, "uri", "?"),
            len(players or []),
        )
        try:
            await asyncio.sleep(3)
            await ensure_nodes_alive(bot, force=True)
        except Exception as exc:  # pragma: no cover - reconnect gagal
            logger.warning("Reconnect Lavalink gagal: %s", exc)

    @bot.event
    async def on_wavelink_track_start(payload) -> None:
        player = getattr(payload, "player", None)
        track = getattr(payload, "track", None)
        if player is None or track is None:
            return
        guild = getattr(player, "guild", None)
        if guild is None:
            return

        cfg = get_music_settings(guild.id)
        if not cfg.get("announce", True):
            return

        # Rythm-style: satu panel per server yang di-EDIT setiap ganti lagu.
        channel_id = announce_channels.get(guild.id) or (music_panels.get(guild.id) or {}).get("channel_id")
        channel = bot.get_channel(channel_id) if channel_id else None
        if channel is None and guild.id not in music_panels:
            return
        try:
            await send_or_update_panel(
                bot,
                guild.id,
                channel=channel,
                view=MusicPlayerView(),
            )
        except discord.HTTPException:
            pass

    @bot.event
    async def on_wavelink_track_exception(payload) -> None:
        player = getattr(payload, "player", None)
        track = getattr(payload, "track", None)
        logger.warning(
            "Lagu gagal diputar (%s): %s",
            track_title(track) if track else "?",
            getattr(payload, "exception", "unknown"),
        )
        guild = getattr(player, "guild", None)
        channel_id = announce_channels.get(guild.id) if guild else None
        channel = bot.get_channel(channel_id) if channel_id else None
        if channel is not None:
            try:
                await channel.send(
                    f"⚠️ Gagal memutar **{track_title(track)}** (sumber menolak/musik tidak tersedia). "
                    "Lagu dilewati otomatis.",
                )
            except discord.HTTPException:
                pass

    @bot.event
    async def on_wavelink_inactive_player(player) -> None:
        guild = getattr(player, "guild", None)
        channel_id = announce_channels.get(getattr(guild, "id", 0))
        channel = bot.get_channel(channel_id) if channel_id else None
        if channel is not None:
            try:
                await channel.send(
                    "👋 Tidak ada lagu & tidak ada aktivitas, bot keluar dari voice channel. "
                    "Panggil lagi dengan `/musik putar`."
                )
            except discord.HTTPException:
                pass
        if guild is not None:
            music.forget_announce_channel(guild.id)
            await close_panel(bot, guild.id)
        try:
            await player.disconnect()
        except Exception:  # pragma: no cover - sudah terputus
            pass
