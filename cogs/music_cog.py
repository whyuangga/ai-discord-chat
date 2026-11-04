import logging

import discord
from discord import app_commands
from discord.ext import commands

import music
from music import (
    LOOP_MODES,
    MUSIC_SETUP_HINT,
    MusicUnavailable,
    announce_channels,
    build_now_playing_embed,
    build_queue_embed,
    build_search_embed,
    can_control,
    enqueue_tracks,
    ensure_player,
    format_duration,
    get_music_settings,
    get_player,
    loop_label_from_mode,
    music_status,
    play_first_if_idle,
    remember_announce_channel,
    save_music_settings_to_disk,
    search_tracks,
    set_music_settings,
    track_title,
)
from config import MUSIC_MAX_QUEUE

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
        await interaction.followup.send(f"⚠️ Gagal memutar lagu: `{exc}`", ephemeral=True)
        return

    remember_announce_channel(interaction.guild.id, interaction.channel_id)

    if playlist_name:
        await interaction.followup.send(
            f"📥 **Playlist `{playlist_name[:80]}`** dimasukkan — "
            f"`{added + (1 if started else 0)}` lagu ditambahkan"
            + (f", `{skipped}` dilewati karena antrean penuh." if skipped else "."),
            ephemeral=True,
        )
        return

    if started:
        embed = build_now_playing_embed(
            tracks[0],
            requester=interaction.user.display_name,
            queue_length=len(player.queue),
            volume=getattr(player, "volume", None),
            loop_label=loop_label_from_mode(getattr(player.queue, "mode", None)),
        )
        await interaction.followup.send(embed=embed)
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


@musik_group.command(name="antrean", description="Lihat daftar lagu yang menunggu diputar")
async def musik_antrean_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = get_player(interaction.guild)
    if player is None:
        await interaction.response.send_message(
            "⚠️ Belum ada musik yang diputar.", ephemeral=True
        )
        return

    tracks = list(player.queue)
    total = sum(int(getattr(t, "length", 0) or 0) for t in tracks)
    await interaction.response.send_message(
        embed=build_queue_embed(
            tracks,
            total_length=total,
            now_playing=getattr(player, "current", None),
        ),
        ephemeral=True,
    )


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

    embed = build_now_playing_embed(
        current,
        queue_length=len(player.queue),
        volume=getattr(player, "volume", None),
        paused=bool(getattr(player, "paused", False)),
        loop_label=loop_label_from_mode(getattr(player.queue, "mode", None)),
    )
    position = format_duration(getattr(player, "position", 0))
    length = "LIVE" if getattr(current, "is_stream", False) else format_duration(
        getattr(current, "length", 0)
    )
    embed.add_field(name="▶️ Progres", value=f"`{position} / {length}`", inline=False)
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

    await interaction.response.send_message(
        f"⏭️ Dilewati: **{track_title(skipped_track)}**" if skipped_track else "⏭️ Lagu dilewati.",
        ephemeral=True,
    )


@musik_group.command(name="jeda", description="Jeda pemutaran tanpa keluar dari voice channel")
async def musik_jeda_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    await player.pause(True)
    await interaction.response.send_message("⏸️ Musik dijeda. Lanjutkan dengan `/musik lanjut`.", ephemeral=True)


@musik_group.command(name="lanjut", description="Lanjutkan pemutaran yang sedang dijeda")
async def musik_lanjut_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    player = await _require_player(interaction)
    if player is None:
        return

    await player.pause(False)
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
    await interaction.response.send_message(
        f"🔀 **{len(player.queue)} lagu** di antrean berhasil diacak.", ephemeral=True
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
    lines = [
        "🎵 **Status Musik**",
        f"• **Node Lavalink:** {music_status()}",
        f"• **Voice channel:** {player.channel.mention if player and player.channel else '_belum bergabung_'}",
        f"• **Sedang diputar:** {track_title(player.current) if player and player.current else '_tidak ada_'}",
        f"• **Antrean:** `{len(player.queue) if player else 0}` lagu",
        f"• **Volume:** `{player.volume if player else cfg['volume']}%`",
        f"• **Pengumuman:** {'✅ Aktif' if cfg.get('announce', True) else '❌ Nonaktif'}",
        f"• **Channel pengumuman:** {f'<#{announce_channels[interaction.guild.id]}>' if interaction.guild.id in announce_channels else '_otomatis_'}",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


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
            "✅ Node Lavalink siap: %s (sesi %s)",
            getattr(node, "identifier", "?"),
            getattr(payload, "session_id", "?"),
        )

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
        channel_id = announce_channels.get(guild.id)
        channel = bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        try:
            await channel.send(
                embed=build_now_playing_embed(
                    track,
                    queue_length=len(getattr(player, "queue", [])),
                    volume=getattr(player, "volume", None),
                    loop_label=loop_label_from_mode(getattr(getattr(player, "queue", None), "mode", None)),
                )
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
        try:
            await player.disconnect()
        except Exception:  # pragma: no cover - sudah terputus
            pass
