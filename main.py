import asyncio
import logging
import platform
import random
import sys
import time
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from ai_handler import generate_image, get_ai_response, is_gemini_key_configured
from community_agent import (
    chat_agent_channels,
    gallery_agent_channels,
    generate_community_chat_reply,
    generate_gallery_comment,
    generate_idle_icebreaker,
    get_agent_channel_lock,
    get_guild_settings,
    load_agent_config_from_disk,
    run_idle_chat_check,
    save_agent_config_to_disk,
    set_chat_channel_config,
    set_gallery_channel_config,
    should_agent_reply_in_chat,
)
from config import (
    AGENT_DEFAULT_IDLE_MINUTES,
    AI_MODELS,
    BOT_TIMEZONE,
    BOT_VERSION,
    DISCORD_BOT_TOKEN,
    DISCORD_GUILD_ID,
    GEMINI_DEFAULT_MODEL,
    GEMINI_FAST_MODEL,
    GEMINI_IMAGE_MODEL,
    resolve_model_key,
)
from storage import (
    cleanup_expired_sessions,
    get_image_settings,
    get_thread_lock,
    image_thread_settings,
    init_image_session,
    load_sessions_from_disk,
    remove_thread_data,
    reset_thread_history,
    save_sessions_to_disk,
    switch_thread_model,
    thread_chats,
)
from utils import (
    extract_message_attachments,
    get_realtime_time_context,
    sanitize_error_message,
    split_discord_message,
)
from views import (
    ChatPersonaSwitchView,
    EndSessionView,
    ImageSettingsView,
    MainPanelControlView,
    build_main_panel_embed,
    can_manage_session,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gemini_bot")


def _get_memory_usage_mb() -> float:
    """Membaca pemakaian RAM proses saat ini (MB) untuk pemantauan di Wispbyte/Linux."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024, 1)
    except Exception:
        pass
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return round(usage / (1024 * 1024), 1)
        return round(usage / 1024, 1)
    except Exception:
        return 0.0


class GeminiDiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at: float = time.time()

    async def setup_hook(self) -> None:
        # 1. Buat koneksi HTTP bersama agar cepat & hemat RAM
        self.http_session = aiohttp.ClientSession()

        # 2. Muat kembali sesi privat & konfigurasi AI Agent Komunitas dari disk
        loaded_chats, loaded_imgs = load_sessions_from_disk()
        loaded_agent_chats, loaded_galleries = load_agent_config_from_disk()
        logger.info(
            "Memori dimuat: %d ruang chat privat, %d ruang gambar, %d channel Auto-Chat, %d channel Galeri.",
            loaded_chats,
            loaded_imgs,
            loaded_agent_chats,
            loaded_galleries,
        )

        # 3. Daftarkan seluruh View persisten (sekali saja saat startup)
        self.add_view(MainPanelControlView())
        self.add_view(EndSessionView())
        self.add_view(ChatPersonaSwitchView())
        self.add_view(ImageSettingsView())

        # 4. Jalankan background watcher untuk fitur Pemecah Sepi Otomatis
        if not idle_chat_watcher.is_running():
            idle_chat_watcher.start()

        # 5. Sinkronisasi Slash Commands (/setup_panel, /agent ..., /model, /reset, /status)
        try:
            if DISCORD_GUILD_ID:
                guild_obj = discord.Object(id=DISCORD_GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced_guild = await self.tree.sync(guild=guild_obj)
                logger.info(
                    "Slash commands tersinkron instan ke Guild %s (%d command).",
                    DISCORD_GUILD_ID,
                    len(synced_guild),
                )
            synced_global = await self.tree.sync()
            logger.info("Global Slash commands tersinkron (%d command).", len(synced_global))
        except Exception as exc:
            logger.warning("Gagal sinkronisasi Slash Commands: %s", sanitize_error_message(exc))

    async def close(self) -> None:
        if idle_chat_watcher.is_running():
            idle_chat_watcher.cancel()
        await save_sessions_to_disk()
        await save_agent_config_to_disk()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()


bot = GeminiDiscordBot()


@tasks.loop(minutes=1)
async def idle_chat_watcher():
    """Memantau channel Auto-Chat setiap 1 menit & membersihkan sesi kadaluarsa setiap 1 jam."""
    try:
        await run_idle_chat_check(bot, http_session=bot.http_session)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 60 == 0:
            if cleanup_expired_sessions() > 0:
                await save_sessions_to_disk()
    except Exception as exc:
        logger.warning("Error pada idle_chat_watcher: %s", sanitize_error_message(exc))


@idle_chat_watcher.before_loop
async def before_idle_chat_watcher():
    await bot.wait_until_ready()


# ==============================================================================
# EVENTS UTAMA
# ==============================================================================
@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name="Google Gemini AI ✨",
        )
    )
    ram_mb = _get_memory_usage_mb()
    logger.info(
        "✅ Bot v%s aktif sebagai %s (ID: %s) | Python %s | discord.py %s | RAM: %.1f MB",
        BOT_VERSION,
        bot.user,
        bot.user.id if bot.user else "-",
        platform.python_version(),
        discord.__version__,
        ram_mb,
    )
    if not is_gemini_key_configured():
        logger.warning("⚠️ GEMINI_API_KEY belum diisi! Isi di .env atau panel Variables Wispbyte.")


@bot.event
async def on_raw_thread_delete(payload: discord.RawThreadDeleteEvent):
    """Membersihkan sisa memori secara otomatis jika thread dihapus manual oleh Admin/User."""
    if remove_thread_data(payload.thread_id):
        await save_sessions_to_disk()
        logger.info("Data sesi dibersihkan karena thread %s dihapus.", payload.thread_id)


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    """Membersihkan konfigurasi AI Agent jika channel publik dihapus dari server."""
    removed = False
    if channel.id in chat_agent_channels:
        set_chat_channel_config(channel.guild.id, channel.id, enabled=False)
        removed = True
    if channel.id in gallery_agent_channels:
        set_gallery_channel_config(channel.guild.id, channel.id, enabled=False)
        removed = True
    if removed:
        await save_agent_config_to_disk()


# ==============================================================================
# SLASH COMMAND GROUP: /agent (FITUR AI AGENT KOMUNITAS, PEMECAH SEPI, & GALERI)
# ==============================================================================
agent_group = app_commands.Group(
    name="agent",
    description="Pengaturan AI Agent Komunitas (Auto-Chat, Pemecah Sepi, & Auto-Komentar Galeri)",
    default_permissions=discord.Permissions(administrator=True),
    guild_only=True,
)


@agent_group.command(
    name="chat",
    description="Aktifkan/atur AI Agent Auto-Chat & Pemecah Sepi otomatis di channel publik",
)
@app_commands.describe(
    channel="Channel teks tempat AI Agent ikut ngobrol",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    mode_balas="Cerdas & Natural (rekomendasi) atau Balas Semua Pesan",
    menit_sepi="Berapa menit channel sepi sebelum AI menyapa duluan (isi 0 untuk mematikan)",
)
@app_commands.choices(
    mode_balas=[
        app_commands.Choice(name="Cerdas & Natural ala Manusia (Rekomendasi)", value="smart"),
        app_commands.Choice(name="Balas Semua Pesan Member", value="all"),
    ]
)
async def agent_chat_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    mode_balas: app_commands.Choice[str] | None = None,
    menit_sepi: app_commands.Range[int, 0, 720] = AGENT_DEFAULT_IDLE_MINUTES,
):
    if interaction.guild is None:
        return

    chosen_mode = mode_balas.value if mode_balas else "smart"
    cfg = set_chat_channel_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        reply_mode=chosen_mode,
        idle_minutes=menit_sepi,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            f"🛑 **AI Agent Auto-Chat** telah **dinonaktifkan** di {channel.mention}.",
            ephemeral=True,
        )
        return

    idle_desc = f"Aktif setiap **{menit_sepi} menit** sepi" if menit_sepi > 0 else "Nonaktif (`0` menit)"
    mode_label = "Cerdas & Natural" if chosen_mode == "smart" else "Balas Semua Pesan"
    await interaction.response.send_message(
        f"✅ **AI Agent Auto-Chat aktif di {channel.mention}!**\n"
        f"• **Mode Balasan:** `{mode_label}`\n"
        f"• **Pemecah Sepi Otomatis:** {idle_desc}\n"
        f"• **Kemampuan:** Ngobrol santai ala manusia, baca **Stiker & Emoji**, dan paham **Jam Lokal Real-Time**.\n"
        f"*(Gunakan `/agent sapa` jika ingin mengetes sapaan pemecah sepi sekarang juga!)*",
        ephemeral=True,
    )


@agent_group.command(
    name="gallery",
    description="Aktifkan/nonaktifkan AI Auto-Komentar Gambar & Video di channel Galeri/Media",
)
@app_commands.describe(
    channel="Channel galeri/media/showcase tempat member mengirim foto atau video",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    auto_reaction="Otomatis memberi reaksi emoji (✨/🔥/😍) pada postingan media",
)
async def agent_gallery_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    auto_reaction: bool = True,
):
    if interaction.guild is None:
        return

    cfg = set_gallery_channel_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        auto_reaction=auto_reaction,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            f"🛑 **Gallery Auto-Comment** telah **dinonaktifkan** di {channel.mention}.",
            ephemeral=True,
        )
        return

    react_label = "Aktif" if auto_reaction else "Nonaktif"
    await interaction.response.send_message(
        f"📸 **Gallery Auto-Comment aktif di {channel.mention}!**\n"
        f"• Setiap member mengirim **foto/gambar** atau **video pendek**, AI akan men-scan isinya secara visual dan membalas komentar yang nyambung!\n"
        f"• **Auto-Reaction Emoji:** `{react_label}`",
        ephemeral=True,
    )


@agent_group.command(
    name="persona",
    description="Atur gaya bahasa, nama panggilan, zona waktu, & jam tenang AI Agent di server ini",
)
@app_commands.describe(
    gaya_bahasa="Pilih gaya bicara AI Agent saat berbaur di komunitas",
    nama_panggilan="Nama panggilan akrab AI (kosongkan untuk memakai nama bot di server)",
    zona_waktu="Zona waktu referensi saat AI menyebut jam atau menyapa",
    jam_tenang_malam="Tahan sapaan pemecah sepi otomatis saat warga tidur (23:00 - 06:00)",
    konteks_komunitas="Info opsional tentang server (misal: Komunitas mabar Roblox & nongkrong santai)",
)
@app_commands.choices(
    gaya_bahasa=[
        app_commands.Choice(name="Santai & Akrab (Aku/Kamu - Default)", value="akrab"),
        app_commands.Choice(name="Gaul Tongkrongan Discord (Gue/Lu)", value="gaul"),
        app_commands.Choice(name="Ramah, Hangat & Sopan", value="ramah"),
    ],
    zona_waktu=[
        app_commands.Choice(name="WIB - Waktu Indonesia Barat (Asia/Jakarta)", value="Asia/Jakarta"),
        app_commands.Choice(name="WITA - Waktu Indonesia Tengah (Asia/Makassar)", value="Asia/Makassar"),
        app_commands.Choice(name="WIT - Waktu Indonesia Timur (Asia/Jayapura)", value="Asia/Jayapura"),
    ],
)
async def agent_persona_cmd(
    interaction: discord.Interaction,
    gaya_bahasa: app_commands.Choice[str] | None = None,
    nama_panggilan: str | None = None,
    zona_waktu: app_commands.Choice[str] | None = None,
    jam_tenang_malam: bool | None = None,
    konteks_komunitas: str | None = None,
):
    if interaction.guild is None:
        return

    g_cfg = get_guild_settings(interaction.guild.id)
    if gaya_bahasa is not None:
        g_cfg["style_preset"] = gaya_bahasa.value
    if nama_panggilan is not None:
        g_cfg["nickname"] = "" if nama_panggilan.strip() == "-" else nama_panggilan.strip()[:32]
    if zona_waktu is not None:
        g_cfg["timezone"] = zona_waktu.value
    if jam_tenang_malam is not None:
        g_cfg["quiet_hours"] = jam_tenang_malam
    if konteks_komunitas is not None:
        g_cfg["custom_prompt"] = "" if konteks_komunitas.strip() == "-" else konteks_komunitas.strip()[:300]

    await save_agent_config_to_disk()
    time_ctx = get_realtime_time_context(g_cfg["timezone"])
    shown_nick = g_cfg["nickname"] or (interaction.guild.me.display_name if interaction.guild.me else "Default Bot")

    await interaction.response.send_message(
        f"🎭 **Kepribadian AI Agent Komunitas berhasil diperbarui!**\n"
        f"• **Nama Panggilan:** `{shown_nick}`\n"
        f"• **Gaya Bahasa:** `{g_cfg['style_preset']}`\n"
        f"• **Waktu Lokal Sekarang:** `{time_ctx['clock']}` ({time_ctx['day_name']})\n"
        f"• **Jam Tenang Malam (23:00-06:00):** `{'Aktif' if g_cfg['quiet_hours'] else 'Nonaktif'}`\n"
        f"• **Konteks Komunitas:** `{g_cfg['custom_prompt'] or '(Default)'}`",
        ephemeral=True,
    )


@agent_group.command(
    name="sapa",
    description="Minta AI Agent langsung menyapa / memecah sepi sekarang juga di channel pilihan",
)
@app_commands.describe(channel="Channel target (kosongkan untuk menyapa di channel ini)")
async def agent_sapa_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return

    target = channel or (interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None)
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih Text Channel yang valid.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    bot_name = interaction.guild.me.display_name if interaction.guild.me else "Teman"
    icebreaker = await generate_idle_icebreaker(
        target.id,
        interaction.guild.id,
        bot_name,
        idle_minutes_elapsed=30,
        http_session=bot.http_session,
    )
    if not icebreaker:
        await interaction.followup.send(
            "⚠️ Gagal membuat sapaan. Pastikan `GEMINI_API_KEY` aktif dan valid.",
            ephemeral=True,
        )
        return

    await target.send(icebreaker)
    await interaction.followup.send(
        f"✅ AI Agent berhasil menyapa warga di {target.mention}!",
        ephemeral=True,
    )


@agent_group.command(
    name="status",
    description="Lihat daftar channel Auto-Chat, Pemecah Sepi, & Galeri yang aktif di server ini",
)
async def agent_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    gid = interaction.guild.id
    g_cfg = get_guild_settings(gid)
    time_ctx = get_realtime_time_context(g_cfg.get("timezone", BOT_TIMEZONE))
    shown_nick = g_cfg["nickname"] or (interaction.guild.me.display_name if interaction.guild.me else "Default Bot")

    active_chats = [
        (cid, cdata)
        for cid, cdata in chat_agent_channels.items()
        if cdata.get("guild_id") == gid and cdata.get("enabled")
    ]
    active_galleries = [
        (cid, gdata)
        for cid, gdata in gallery_agent_channels.items()
        if gdata.get("guild_id") == gid and gdata.get("enabled")
    ]

    chat_lines = [
        f"• <#{cid}> — Mode: `{d['reply_mode']}` | Pemecah sepi: `{d['idle_minutes']} mnt`"
        for cid, d in active_chats
    ] or ["*Belum ada channel Auto-Chat aktif (gunakan `/agent chat`)*"]

    gallery_lines = [
        f"• <#{cid}> — Auto-Reaction: `{'Ya' if d.get('auto_reaction', True) else 'Tidak'}`"
        for cid, d in active_galleries
    ] or ["*Belum ada channel Galeri aktif (gunakan `/agent gallery`)*"]

    embed = discord.Embed(
        title="🤖 Status AI Agent & Otomasi Komunitas",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="🎭 Profil & Waktu",
        value=(
            f"**Panggilan:** `{shown_nick}` | **Gaya:** `{g_cfg['style_preset']}`\n"
            f"**Waktu Lokal:** `{time_ctx['summary']}`\n"
            f"**Jam Tenang Malam:** `{'Aktif (23:00-06:00)' if g_cfg.get('quiet_hours', True) else 'Nonaktif'}`"
        ),
        inline=False,
    )
    embed.add_field(name="💬 Channel Auto-Chat & Pemecah Sepi", value="\n".join(chat_lines), inline=False)
    embed.add_field(name="📸 Channel Auto-Komentar Galeri (Foto & Video)", value="\n".join(gallery_lines), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


bot.tree.add_command(agent_group)


# ==============================================================================
# SLASH COMMANDS PANEL RUANG PRIVAT & UTILITAS
# ==============================================================================
@bot.tree.command(
    name="setup_panel",
    description="Pasang Panel Kontrol Utama Google Gemini AI di channel ini (Khusus Admin)",
)
@app_commands.default_permissions(administrator=True)
async def slash_setup_panel(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Jalankan `/setup_panel` di dalam Text Channel server biasa (bukan di dalam Thread/DM).",
            ephemeral=True,
        )
        return

    await interaction.channel.send(
        embed=build_main_panel_embed(),
        view=MainPanelControlView(),
    )
    await interaction.response.send_message(
        "✅ **Panel Gemini AI** berhasil dipasang di channel ini!",
        ephemeral=True,
    )


@bot.command(name="setup_panel")
@commands.has_permissions(administrator=True)
async def prefix_setup_panel(ctx: commands.Context):
    """Kompatibilitas command lama `!setup_panel`."""
    await ctx.send(
        embed=build_main_panel_embed(),
        view=MainPanelControlView(),
    )
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass


@prefix_setup_panel.error
async def prefix_setup_panel_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⚠️ Hanya **Administrator** yang dapat menjalankan `!setup_panel`.", delete_after=8)


@bot.tree.command(
    name="reset",
    description="Bersihkan memori percakapan atau reset pengaturan di ruang sesi AI saat ini",
)
async def slash_reset(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.Thread) or not (
        channel.name.startswith("ai-") or channel.name.startswith("draw-")
    ):
        await interaction.response.send_message(
            "⚠️ Command `/reset` hanya bisa dijalankan di dalam ruang privat AI (`ai-...` atau `draw-...`).",
            ephemeral=True,
        )
        return

    if not can_manage_session(interaction, channel.id):
        await interaction.response.send_message(
            "⚠️ Hanya pemilik ruang sesi ini (atau Moderator) yang dapat mereset sesi.",
            ephemeral=True,
        )
        return

    if channel.name.startswith("draw-"):
        init_image_session(channel.id, owner_id=interaction.user.id)
        await save_sessions_to_disk()
        await interaction.response.send_message(
            "🔄 **Pengaturan gambar berhasil direset ke awal:** Gaya `Biasa` | Ukuran `1:1 (Persegi)`.",
            ephemeral=True,
        )
    else:
        reset_thread_history(channel.id)
        await save_sessions_to_disk()
        await interaction.response.send_message(
            "🔄 **Memori percakapan telah dibersihkan!** Silakan mulai topik baru.",
        )


@bot.tree.command(
    name="model",
    description="Ganti mode/kepribadian Google Gemini di ruang chat saat ini",
)
@app_commands.describe(mode="Pilih mode kepribadian Gemini yang ingin digunakan")
@app_commands.choices(
    mode=[
        app_commands.Choice(name=info["name"], value=key)
        for key, info in AI_MODELS.items()
    ]
)
async def slash_model(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    channel = interaction.channel
    if not isinstance(channel, discord.Thread) or not channel.name.startswith("ai-"):
        await interaction.response.send_message(
            "⚠️ Command `/model` hanya bisa digunakan di dalam ruang chat teks (`ai-...`).",
            ephemeral=True,
        )
        return

    if not can_manage_session(interaction, channel.id):
        await interaction.response.send_message(
            "⚠️ Hanya pemilik ruang sesi ini yang dapat mengganti mode AI.",
            ephemeral=True,
        )
        return

    chosen_key = resolve_model_key(mode.value)
    model_info = AI_MODELS[chosen_key]
    switch_thread_model(channel.id, chosen_key, owner_id=interaction.user.id)
    await save_sessions_to_disk()

    await interaction.response.send_message(
        f"✅ **Mode AI berhasil diganti ke:** **{model_info['name']}**",
    )


@bot.tree.command(
    name="status",
    description="Lihat status koneksi bot, latensi, pemakaian RAM, dan sesi Gemini aktif",
)
async def slash_status(interaction: discord.Interaction):
    uptime_sec = int(time.time() - bot.started_at)
    hours, rem = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    ping_ms = round(bot.latency * 1000)
    ram_mb = _get_memory_usage_mb()
    gemini_ready = "✅ Aktif" if is_gemini_key_configured() else "⚠️ Belum Diisi"
    time_ctx = get_realtime_time_context()

    embed = discord.Embed(
        title=f"📊 Status Bot Gemini AI (v{BOT_VERSION})",
        color=discord.Color.green() if is_gemini_key_configured() else discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📡 Latensi Discord", value=f"`{ping_ms} ms`", inline=True)
    embed.add_field(name="💾 Pemakaian RAM", value=f"`{ram_mb} MB`", inline=True)
    embed.add_field(name="⏱️ Uptime", value=f"`{hours}j {minutes}m {seconds}d`", inline=True)
    embed.add_field(name="🔑 Gemini API Key", value=gemini_ready, inline=True)
    embed.add_field(
        name="🔒 Ruang Privat",
        value=f"`{len(thread_chats)}` chat | `{len(image_thread_settings)}` gambar",
        inline=True,
    )
    embed.add_field(
        name="🌐 AI Agent Publik",
        value=f"`{len(chat_agent_channels)}` chat | `{len(gallery_agent_channels)}` galeri",
        inline=True,
    )
    embed.add_field(name="🕒 Jam Server AI", value=f"`{time_ctx['clock']}` ({time_ctx['day_name']})", inline=False)
    embed.add_field(
        name="♊ Model Gemini",
        value=(
            f"Utama: `{GEMINI_DEFAULT_MODEL}`\n"
            f"Kilat: `{GEMINI_FAST_MODEL}`\n"
            f"Gambar: `{GEMINI_IMAGE_MODEL}`"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# HANDLER PESAN OTOMATIS (RUANG PRIVAT, GALERI MEDIA, & AUTO-CHAT KOMUNITAS)
# ==============================================================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Jalankan command prefix (seperti !setup_panel) tanpa memicu AI
    if message.content.strip().startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if message.type not in (discord.MessageType.default, discord.MessageType.reply):
        return

    # ==========================================================================
    # BAGIAN 1: RUANG SESI PRIVAT (Thread 'ai-' & 'draw-')
    # ==========================================================================
    if isinstance(message.channel, discord.Thread):
        channel_name = message.channel.name

        # 1A. RUANG CHAT TEKS, VISION, STIKER & FILE KODE (Thread 'ai-')
        if channel_name.startswith("ai-"):
            prompt = message.content.strip()
            image_parts, image_filenames, text_blocks, warnings = await extract_message_attachments(
                message,
                http_session=bot.http_session,
            )

            if not prompt and not image_parts and not text_blocks:
                if warnings:
                    await message.channel.send("⚠️ " + "\n⚠️ ".join(warnings))
                return

            lock = get_thread_lock(message.channel.id)
            async with lock:
                async with message.channel.typing():
                    try:
                        reply_text = await get_ai_response(
                            message.channel.id,
                            prompt,
                            image_parts=image_parts,
                            image_filenames=image_filenames,
                            text_blocks=text_blocks,
                            http_session=bot.http_session,
                            thread=message.channel,
                            bot_user_id=bot.user.id if bot.user else None,
                        )

                        if warnings:
                            warn_banner = "\n".join(f"⚠️ *{w}*" for w in warnings)
                            reply_text = f"{warn_banner}\n\n{reply_text}"

                        for chunk in split_discord_message(reply_text):
                            await message.channel.send(chunk)

                    except Exception as exc:
                        await message.channel.send(
                            f"⚠️ Terjadi kesalahan saat memproses pesan: `{sanitize_error_message(exc)}`"
                        )
            return

        # 1B. RUANG GENERATE & EDIT GAMBAR AI (Thread 'draw-')
        if channel_name.startswith("draw-"):
            prompt = message.content.strip()
            image_parts, _, _, warnings = await extract_message_attachments(
                message,
                http_session=bot.http_session,
            )

            if not prompt and not image_parts:
                if warnings:
                    await message.channel.send("⚠️ " + "\n⚠️ ".join(warnings))
                return

            display_prompt = prompt or "Edit gambar lampiran"
            settings = get_image_settings(message.channel.id)
            status_msg = await message.channel.send(
                f"🎨 **Memproses gambar [{settings['style']} | {settings['ratio']}] untuk:** *\"{display_prompt[:150]}\"*..."
            )

            lock = get_thread_lock(message.channel.id)
            async with lock:
                async with message.channel.typing():
                    try:
                        engine_label, picture, err_detail = await generate_image(
                            message.channel.id,
                            prompt,
                            reference_images=image_parts or None,
                            http_session=bot.http_session,
                        )

                        if picture is not None:
                            try:
                                await status_msg.delete()
                            except discord.HTTPException:
                                pass

                            caption = (
                                f"🖼️ **Hasil Gambar:** `{display_prompt[:200]}`\n"
                                f"⚙️ **Gaya:** `{settings['style']}` | **Rasio:** `{settings['ratio']}` | "
                                f"**Mesin:** `{engine_label}`\n"
                                f"👤 Diminta oleh {message.author.mention}"
                            )
                            await message.channel.send(content=caption, file=picture)
                        else:
                            await status_msg.edit(
                                content=(
                                    "⚠️ **Gagal membuat gambar.**\n"
                                    f"Detail: `{err_detail or 'Layanan tidak merespons'}`"
                                )
                            )
                    except Exception as exc:
                        await status_msg.edit(
                            content=f"⚠️ Terjadi kesalahan: `{sanitize_error_message(exc)}`"
                        )
            return

    # ==========================================================================
    # BAGIAN 2: AI AGENT KOMUNITAS DI CHANNEL PUBLIK (GALERI & AUTO-CHAT)
    # ==========================================================================
    if isinstance(message.channel, discord.TextChannel) and bot.user is not None:
        channel_id = message.channel.id

        # 2A. GALLERY AUTO-COMMENT (Scan Foto, Gambar, & Video Klip Pendek)
        if channel_id in gallery_agent_channels and message.attachments:
            lock = get_agent_channel_lock(channel_id)
            async with lock:
                comment_text, reaction_emoji = await generate_gallery_comment(
                    message,
                    bot.user,
                    http_session=bot.http_session,
                )
                if comment_text:
                    if reaction_emoji:
                        try:
                            await message.add_reaction(reaction_emoji)
                        except (discord.Forbidden, discord.HTTPException):
                            pass

                    async with message.channel.typing():
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                        await message.reply(comment_text[:1900], mention_author=False)
                    return

        # 2B. AUTO-CHAT KOMUNITAS NATURAL (Teks, Stiker, Emoji, & Sapaan)
        if channel_id in chat_agent_channels:
            should_reply, use_reply_ref = should_agent_reply_in_chat(message, bot.user)
            if should_reply:
                lock = get_agent_channel_lock(channel_id)
                async with lock:
                    async with message.channel.typing():
                        await asyncio.sleep(random.uniform(1.0, 2.2))
                        reply_text = await generate_community_chat_reply(
                            message,
                            bot.user,
                            http_session=bot.http_session,
                        )
                        if reply_text:
                            chunks = split_discord_message(reply_text)
                            for idx, chunk in enumerate(chunks):
                                if idx == 0 and use_reply_ref:
                                    await message.reply(chunk, mention_author=False)
                                else:
                                    await message.channel.send(chunk)
                return

    await bot.process_commands(message)


# ==============================================================================
# ENTRYPOINT UTAMA (STARTUP FILE DI WISPBYTE: main.py)
# ==============================================================================
def main() -> None:
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN.startswith("masukkan_"):
        logger.error(
            "❌ DISCORD_BOT_TOKEN belum diatur! "
            "Buat file .env dari .env.example atau isi DISCORD_BOT_TOKEN pada tab Startup/Variables di Wispbyte."
        )
        sys.exit(1)

    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
