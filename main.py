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

from ai_handler import (
    analyze_link_with_gemini,
    generate_image,
    get_ai_response,
    is_gemini_key_configured,
    search_web_with_gemini,
    summarize_channel_messages,
    transform_message_with_gemini,
)
from community_agent import (
    chat_agent_channels,
    format_idle_duration,
    gallery_agent_channels,
    generate_community_chat_reply,
    generate_gallery_comment,
    generate_idle_icebreaker,
    generate_welcome_greeting,
    get_agent_channel_lock,
    get_guild_settings,
    load_agent_config_from_disk,
    parse_idle_duration,
    record_human_channel_activity,
    run_idle_chat_check,
    save_agent_config_to_disk,
    set_chat_channel_config,
    set_gallery_channel_config,
    set_welcome_config,
    should_agent_reply_in_chat,
    should_process_member_welcome,
    welcome_agent_guilds,
)
from config import (
    AGENT_DEFAULT_IDLE_MINUTES,
    AGENT_MAX_IDLE_POKES,
    AI_MODELS,
    BOT_TIMEZONE,
    BOT_VERSION,
    DISCORD_BOT_TOKEN,
    DISCORD_GUILD_ID,
    GEMINI_DEFAULT_MODEL,
    GEMINI_FAST_MODEL,
    GEMINI_IMAGE_MODEL,
    GEMINI_PAID_IMAGE_ENABLED,
    GEMINI_REASONING_MODEL,
    GEMINI_SEARCH_MODEL,
    resolve_model_key,
)
from games import (
    GAME_POINTS_BY_MODE,
    GAME_ROUND_TIMEOUT_SEC,
    TextGuessControlView,
    TriviaButtonsView,
    active_channel_games,
    generate_ai_game_question,
    get_guild_leaderboard,
    get_user_rank_info,
    handle_active_game_guess,
    load_game_scores_from_disk,
    reset_guild_scores,
    save_game_scores_to_disk,
    scramble_word,
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
    extract_message_text_for_context,
    extract_social_media_and_stickers,
    get_realtime_time_context,
    has_voice_or_audio_attachment,
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
        intents.members = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at: float = time.time()

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        await self.login(token)
        try:
            await self.connect(reconnect=reconnect)
        except discord.PrivilegedIntentsRequired:
            if self.intents.members:
                logger.warning(
                    "ℹ️ Server Members Intent belum dicentang di Discord Developer Portal — "
                    "menyambung otomatis tanpa Members Intent (Auto-Welcome tetap bekerja lewat "
                    "pesan System Join Discord, atau centang Server Members Intent untuk semua channel)."
                )
                self._connection._intents.members = False
                await self.connect(reconnect=reconnect)
            else:
                raise

    async def setup_hook(self) -> None:
        # 1. Buat koneksi HTTP bersama agar cepat & hemat RAM
        self.http_session = aiohttp.ClientSession()

        # 2. Muat kembali sesi privat, konfigurasi AI Agent, & papan skor game dari disk
        loaded_chats, loaded_imgs = load_sessions_from_disk()
        loaded_agent_chats, loaded_galleries = load_agent_config_from_disk()
        loaded_score_guilds = load_game_scores_from_disk()
        logger.info(
            "Memori dimuat: %d chat privat, %d gambar, %d Auto-Chat, %d Galeri, %d papan skor server.",
            loaded_chats,
            loaded_imgs,
            loaded_agent_chats,
            loaded_galleries,
            loaded_score_guilds,
        )

        # 3. Daftarkan seluruh View persisten (sekali saja saat startup)
        self.add_view(MainPanelControlView())
        self.add_view(EndSessionView())
        self.add_view(ChatPersonaSwitchView())
        self.add_view(ImageSettingsView())

        # 4. Jalankan background watcher untuk fitur Pemecah Sepi Otomatis
        if not idle_chat_watcher.is_running():
            idle_chat_watcher.start()

        # 5. Sinkronisasi Slash Commands (tanpa duplikasi Guild vs Global)
        try:
            if DISCORD_GUILD_ID:
                guild_obj = discord.Object(id=DISCORD_GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced_guild = await self.tree.sync(guild=guild_obj)
                # Hapus salinan global lama agar command tidak muncul dobel di server tes
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                logger.info(
                    "Slash commands tersinkron instan ke Guild %s (%d command, bebas duplikat).",
                    DISCORD_GUILD_ID,
                    len(synced_guild),
                )
            else:
                synced_global = await self.tree.sync()
                logger.info("Global Slash commands tersinkron (%d command).", len(synced_global))
        except Exception as exc:
            logger.warning("Gagal sinkronisasi Slash Commands: %s", sanitize_error_message(exc))

    async def close(self) -> None:
        if idle_chat_watcher.is_running():
            idle_chat_watcher.cancel()
        await save_sessions_to_disk()
        await save_agent_config_to_disk()
        await save_game_scores_to_disk()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()


bot = GeminiDiscordBot()


@tasks.loop(seconds=15)
async def idle_chat_watcher():
    """Memantau channel Auto-Chat setiap 15 detik & membersihkan sesi kadaluarsa setiap 1 jam."""
    try:
        await run_idle_chat_check(bot, http_session=bot.http_session)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 240 == 0:
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
    w_cfg = welcome_agent_guilds.get(channel.guild.id)
    if w_cfg and int(w_cfg.get("channel_id") or 0) == channel.id:
        set_welcome_config(channel.guild.id, channel.id, enabled=False)
        removed = True
    active_channel_games.pop(channel.id, None)
    if removed:
        await save_agent_config_to_disk()


async def _trigger_member_welcome(
    guild: discord.Guild,
    member: discord.abc.User,
    *,
    force: bool = False,
) -> str | None:
    """Menjalankan sambutan member baru secara aman & bebas duplikat."""
    if getattr(member, "bot", False):
        return None

    w_cfg = welcome_agent_guilds.get(guild.id)
    if not w_cfg or not w_cfg.get("enabled"):
        return None

    target_ch = guild.get_channel(int(w_cfg["channel_id"]))
    if not isinstance(target_ch, discord.TextChannel):
        return None

    if not should_process_member_welcome(guild.id, member.id, force=force):
        return None

    bot_name = guild.me.display_name if guild.me else (bot.user.display_name if bot.user else "Teman")
    lock = get_agent_channel_lock(target_ch.id)
    async with lock:
        try:
            async with target_ch.typing():
                greeting = await generate_welcome_greeting(
                    guild.id,
                    member.display_name,
                    member.mention,
                    bot_name,
                    guild_name=guild.name,
                    member_count=getattr(guild, "member_count", None),
                    http_session=bot.http_session,
                )
                if greeting:
                    await target_ch.send(greeting[:1900])
                    return greeting
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Gagal mengirim pesan Auto-Welcome di %s: %s", target_ch.id, exc)
    return None


@bot.event
async def on_member_join(member: discord.Member):
    """Menyambut member baru secara otomatis menggunakan AI Agent (jika aktif)."""
    await _trigger_member_welcome(member.guild, member)


# ==============================================================================
# SLASH COMMAND GROUP: /agent (FITUR AI AGENT KOMUNITAS, PEMECAH SEPI, & GALERI)
# ==============================================================================
agent_group = app_commands.Group(
    name="agent",
    description="Pengaturan AI Agent Komunitas (Auto-Chat, Pemecah Sepi, & Auto-Komentar Galeri)",
    default_permissions=discord.Permissions(administrator=True),
    guild_only=True,
)


_MENIT_SEPI_PRESETS: list[tuple[str, str]] = [
    ("30 detik - Tes Kilat", "30 detik"),
    ("1 menit - Tes Cepat", "1"),
    ("5 menit", "5"),
    ("15 menit", "15"),
    ("30 menit - Rekomendasi", "30"),
    ("60 menit - 1 Jam", "60"),
    ("0 - Matikan Pemecah Sepi", "0"),
]


async def _menit_sepi_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    typed = (current or "").strip().lower()
    if not typed:
        return [app_commands.Choice(name=label, value=val) for label, val in _MENIT_SEPI_PRESETS]

    choices: list[app_commands.Choice[str]] = []
    parsed = parse_idle_duration(typed)
    if parsed is not None:
        _, human_label = parsed
        choices.append(app_commands.Choice(name=f"Gunakan: {human_label}", value=typed))

    for label, val in _MENIT_SEPI_PRESETS:
        if typed in label.lower() or typed in val.lower():
            if all(c.value != val for c in choices):
                choices.append(app_commands.Choice(name=label, value=val))
    return choices[:10]


@agent_group.command(
    name="chat",
    description="Aktifkan/atur AI Agent Auto-Chat & Pemecah Sepi otomatis di channel publik",
)
@app_commands.describe(
    channel="Channel teks tempat AI Agent ikut ngobrol",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    mode_balas="Cerdas & Natural (rekomendasi) atau Balas Semua Pesan",
    menit_sepi="Waktu sepi sebelum AI menyapa duluan (pilih dari daftar atau ketik misal: 1, 5, 30, 30 detik, 0)",
)
@app_commands.choices(
    mode_balas=[
        app_commands.Choice(name="Cerdas dan Natural - Rekomendasi", value="smart"),
        app_commands.Choice(name="Balas Semua Pesan Member", value="all"),
    ]
)
@app_commands.autocomplete(menit_sepi=_menit_sepi_autocomplete)
async def agent_chat_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    mode_balas: app_commands.Choice[str] | None = None,
    menit_sepi: str | None = None,
):
    if interaction.guild is None:
        return

    parsed = parse_idle_duration(menit_sepi)
    if parsed is None:
        await interaction.response.send_message(
            "⚠️ Format `menit_sepi` tidak dikenali. Ketik angka menit seperti `1`, `5`, `30`, `30 detik`, atau `0` untuk mematikan.",
            ephemeral=True,
        )
        return

    idle_secs, idle_human_label = parsed
    chosen_mode = mode_balas.value if mode_balas else "smart"
    cfg = set_chat_channel_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        reply_mode=chosen_mode,
        idle_seconds=idle_secs,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            f"🛑 **AI Agent Auto-Chat** telah **dinonaktifkan** di {channel.mention}.",
            ephemeral=True,
        )
        return

    idle_desc = (
        f"Aktif setiap **{idle_human_label}** sepi *(timer dimulai dari sekarang)*"
        if idle_secs > 0
        else "Nonaktif (`0`)"
    )
    mode_label = "Cerdas & Natural" if chosen_mode == "smart" else "Balas Semua Pesan"
    await interaction.response.send_message(
        f"✅ **AI Agent Auto-Chat aktif di {channel.mention}!**\n"
        f"• **Mode Balasan:** `{mode_label}`\n"
        f"• **Pemecah Sepi Otomatis:** {idle_desc}\n"
        f"• **Kemampuan:** Ngobrol santai ala manusia, dengar **Voice Note (🎤)**, baca **Stiker & Emoji**, dan paham **Jam Lokal Real-Time**.\n"
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
        manual_trigger=True,
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
    name="welcome",
    description="Aktifkan/atur AI Auto-Welcomer untuk menyambut member baru secara natural",
)
@app_commands.describe(
    channel="Channel tempat AI menyambut member baru (misal #welcome)",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    pesan_tambahan="Info opsional yang diselipkan santai (misal: Jangan lupa ambil role di #roles, atau isi - untuk hapus)",
    tes_sekarang="True untuk langsung mencoba contoh sambutan AI di channel tersebut sekarang",
)
async def agent_welcome_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    pesan_tambahan: str | None = None,
    tes_sekarang: bool = False,
):
    if interaction.guild is None:
        return

    cfg = set_welcome_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        extra_note=pesan_tambahan,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            f"🛑 **AI Auto-Welcomer** telah **dinonaktifkan** di server ini.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    intent_hint = ""
    if not bot.intents.members:
        intent_hint = (
            "\n💡 *Tips: Agar sambutan bekerja di channel mana pun (bukan hanya channel System Join Discord), "
            "aktifkan centang **Server Members Intent** di Discord Developer Portal lalu restart bot.*"
        )

    test_result_note = ""
    if tes_sekarang:
        sent_greeting = await _trigger_member_welcome(interaction.guild, interaction.user, force=True)
        if sent_greeting:
            test_result_note = f"\n🎉 **Tes sambutan berhasil dikirim ke {channel.mention}!**"
        else:
            test_result_note = f"\n⚠️ *Gagal mengirim tes sambutan ke {channel.mention} (cek izin kirim pesan bot & API key).*"

    extra_info = cfg.get("extra_note") or "(Tidak ada — murni sambutan santai)"
    await interaction.followup.send(
        f"👋 **AI Auto-Welcomer aktif di {channel.mention}!**\n"
        f"• Setiap ada member baru masuk server, AI akan menyapanya dengan kalimat bervariasi sesuai jam & tema server.\n"
        f"• **Pesan Tambahan:** `{extra_info}`"
        f"{test_result_note}{intent_hint}",
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

    now_ts = time.time()
    chat_lines: list[str] = []
    for cid, d in active_chats:
        idle_secs = int(
            d.get("idle_seconds")
            if d.get("idle_seconds") is not None
            else int(d.get("idle_minutes") or 0) * 60
        )
        if idle_secs <= 0:
            idle_info = "`Nonaktif`"
        elif int(d.get("consecutive_idle_pokes") or 0) >= AGENT_MAX_IDLE_POKES:
            idle_info = f"`{format_idle_duration(idle_secs)}` *(menunggu balasan warga)*"
        else:
            rem_sec = max(0, int(idle_secs - (now_ts - float(d.get("last_activity_at") or now_ts))))
            rem_label = f"{rem_sec} dtk" if rem_sec < 60 else f"{rem_sec // 60} mnt {rem_sec % 60} dtk"
            idle_info = f"`{format_idle_duration(idle_secs)}` *(sapa dlm ~{rem_label})*"
        chat_lines.append(f"• <#{cid}> — Mode: `{d['reply_mode']}` | Pemecah sepi: {idle_info}")
    if not chat_lines:
        chat_lines = ["*Belum ada channel Auto-Chat aktif (gunakan `/agent chat`)*"]

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
    w_cfg = welcome_agent_guilds.get(gid)
    if w_cfg and w_cfg.get("enabled"):
        w_note = f" | Info: `{w_cfg['extra_note']}`" if w_cfg.get("extra_note") else ""
        welcome_line = f"• Aktif di <#{w_cfg['channel_id']}>{w_note}"
    else:
        welcome_line = "*Belum aktif (gunakan `/agent welcome`)*"

    embed.add_field(name="💬 Channel Auto-Chat & Pemecah Sepi", value="\n".join(chat_lines), inline=False)
    embed.add_field(name="👋 Auto-Welcomer Member Baru", value=welcome_line, inline=False)
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
    name="ringkas",
    description="Rangkum inti obrolan terakhir di channel ini agar tidak ketinggalan topik (TL;DR)",
)
@app_commands.describe(
    jumlah="Berapa banyak pesan terakhir yang ingin dirangkum",
    channel="Channel yang ingin dirangkum (kosongkan untuk channel saat ini)",
    publik="False = hanya terlihat oleh Anda sendiri, True = tampilkan ke semua orang di channel",
)
@app_commands.choices(
    jumlah=[
        app_commands.Choice(name="25 Pesan Terakhir", value="25"),
        app_commands.Choice(name="50 Pesan Terakhir - Default", value="50"),
        app_commands.Choice(name="100 Pesan Terakhir", value="100"),
        app_commands.Choice(name="150 Pesan Terakhir", value="150"),
    ]
)
async def slash_ringkas(
    interaction: discord.Interaction,
    jumlah: app_commands.Choice[str] | None = None,
    channel: discord.TextChannel | None = None,
    publik: bool = False,
):
    target = channel or interaction.channel
    if not isinstance(target, (discord.TextChannel, discord.Thread)) or interaction.guild is None:
        await interaction.response.send_message(
            "⚠️ Command `/ringkas` hanya dapat digunakan di Text Channel atau Thread server.",
            ephemeral=True,
        )
        return

    # Validasi keamanan izin baca: member & bot wajib sama-sama berhak membaca riwayat channel tersebut
    if isinstance(interaction.user, discord.Member):
        user_perms = target.permissions_for(interaction.user)
        if not (user_perms.view_channel and user_perms.read_message_history):
            await interaction.response.send_message(
                f"⚠️ Anda tidak memiliki izin untuk membaca riwayat pesan di {target.mention}.",
                ephemeral=True,
            )
            return

    if interaction.guild.me is not None:
        bot_perms = target.permissions_for(interaction.guild.me)
        if not (bot_perms.view_channel and bot_perms.read_message_history):
            await interaction.response.send_message(
                f"⚠️ Bot belum memiliki izin `Read Message History` di {target.mention}.",
                ephemeral=True,
            )
            return

    limit_count = int(jumlah.value) if jumlah else 50
    await interaction.response.defer(ephemeral=not publik)

    g_cfg = get_guild_settings(interaction.guild.id)
    tz_name = g_cfg.get("timezone", BOT_TIMEZONE)

    collected_lines: list[str] = []
    try:
        async for msg in target.history(limit=limit_count + 20):
            if msg.type not in (discord.MessageType.default, discord.MessageType.reply):
                continue
            text = (msg.content or "").strip()
            extras: list[str] = []
            if has_voice_or_audio_attachment(msg):
                extras.append("[Voice Note/Audio]")
            elif msg.attachments:
                extras.append(f"[Lampiran: {', '.join(a.filename for a in msg.attachments[:2])}]")
            if getattr(msg, "stickers", None):
                extras.append(f"[Stiker: {msg.stickers[0].name}]")

            combined = " ".join(filter(None, [text, *extras])).strip()
            if not combined:
                continue
            # Lewati pesan embed sistem panel bot
            if msg.author.bot and msg.embeds and not text:
                continue

            author_tag = f"{msg.author.display_name} (Bot)" if msg.author.bot else msg.author.display_name
            collected_lines.append(f"[{author_tag}]: {combined[:400]}")
            if len(collected_lines) >= limit_count:
                break
    except Exception as exc:
        await interaction.followup.send(
            f"⚠️ Gagal mengambil riwayat pesan: `{sanitize_error_message(exc)}`",
            ephemeral=True,
        )
        return

    if len(collected_lines) < 2:
        await interaction.followup.send(
            f"ℹ️ Belum cukup obrolan teks di {target.mention} untuk dirangkum.",
            ephemeral=True,
        )
        return

    # Urutkan kronologis dari pesan paling awal ke paling baru
    collected_lines.reverse()
    summary_text, err_msg = await summarize_channel_messages(
        collected_lines,
        target.name,
        timezone_name=tz_name,
        http_session=bot.http_session,
    )

    if err_msg or not summary_text:
        await interaction.followup.send(err_msg or "⚠️ Gagal membuat ringkasan.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📝 Ringkasan {len(collected_lines)} Chat Terakhir di #{target.name}",
        description=summary_text[:3900],
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"Diminta oleh {interaction.user.display_name}")
    await interaction.followup.send(embed=embed, ephemeral=not publik)


# ==============================================================================
# FITUR 1: MENU TEKAN-TAHAN PESAN / KLIK KANAN (DISCORD CONTEXT MENU APPS)
# ==============================================================================
async def _run_message_context_action(
    interaction: discord.Interaction,
    message: discord.Message,
    action: str,
    embed_title: str,
    embed_color: discord.Color,
) -> None:
    await interaction.response.defer(ephemeral=True)

    msg_text = extract_message_text_for_context(message)
    media_parts, _, text_blocks, _ = await extract_message_attachments(
        message,
        http_session=bot.http_session,
    )
    if not media_parts and (getattr(message, "stickers", None) or "<:" in msg_text or "<a:" in msg_text):
        social_parts, _, _ = await extract_social_media_and_stickers(
            message,
            bot.http_session,
            include_video=False,
            include_audio=False,
        )
        media_parts.extend(social_parts)

    if not msg_text and not media_parts and not text_blocks:
        await interaction.followup.send(
            "ℹ️ Pesan tersebut tidak memiliki teks, lampiran gambar/kode, maupun Voice Note yang bisa diproses.",
            ephemeral=True,
        )
        return

    result_text, err_msg = await transform_message_with_gemini(
        action,
        msg_text,
        media_parts=media_parts or None,
        text_blocks=text_blocks or None,
        http_session=bot.http_session,
    )
    if err_msg or not result_text:
        await interaction.followup.send(err_msg or "⚠️ Gagal memproses pesan ini.", ephemeral=True)
        return

    embed = discord.Embed(
        title=embed_title,
        description=result_text[:3900],
        color=embed_color,
        timestamp=discord.utils.utcnow(),
    )
    preview_src = (message.content or "").strip()
    if preview_src:
        short_src = preview_src[:220] + ("…" if len(preview_src) > 220 else "")
        embed.add_field(
            name=f"💬 Pesan Asli ({message.author.display_name})",
            value=f"> {short_src.replace(chr(10), ' ')}\n[🔗 Lompat ke Pesan]({message.jump_url})",
            inline=False,
        )
    else:
        embed.add_field(
            name=f"📎 Sumber ({message.author.display_name})",
            value=f"[🔗 Lompat ke Pesan Asli]({message.jump_url})",
            inline=False,
        )
    embed.set_footer(text="Hanya terlihat oleh Anda • Gemini AI Context App")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.context_menu(name="🌐 Terjemahkan ke Indonesia")
async def context_translate_indonesia(interaction: discord.Interaction, message: discord.Message):
    await _run_message_context_action(
        interaction,
        message,
        action="translate_id",
        embed_title="🌐 Hasil Terjemahan ke Bahasa Indonesia",
        embed_color=discord.Color.teal(),
    )


@bot.tree.context_menu(name="💡 Jelaskan Pesan Ini")
async def context_explain_message(interaction: discord.Interaction, message: discord.Message):
    await _run_message_context_action(
        interaction,
        message,
        action="explain",
        embed_title="💡 Penjelasan Isi Pesan",
        embed_color=discord.Color.gold(),
    )


# ==============================================================================
# FITUR 2 & 3: PERANGKUM YOUTUBE/WEB (/ringkas_link) & GOOGLE SEARCH (/cari)
# ==============================================================================
@bot.tree.command(
    name="ringkas_link",
    description="Rangkum isi video YouTube atau artikel website secara instan tanpa perlu menonton/baca penuh",
)
@app_commands.describe(
    url="Tempel link video YouTube (watch/youtu.be/shorts) atau link halaman website",
    pertanyaan="Opsional: Tanya hal spesifik dari isi video/artikel tersebut",
    publik="False = hanya terlihat oleh Anda sendiri, True = tampilkan ke channel",
)
async def slash_ringkas_link(
    interaction: discord.Interaction,
    url: str,
    pertanyaan: str | None = None,
    publik: bool = False,
):
    await interaction.response.defer(ephemeral=not publik)
    tz_name = BOT_TIMEZONE
    if interaction.guild is not None:
        tz_name = get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)

    summary_text, err_msg = await analyze_link_with_gemini(
        url.strip(),
        question=pertanyaan,
        timezone_name=tz_name,
        http_session=bot.http_session,
    )
    if err_msg or not summary_text:
        await interaction.followup.send(err_msg or "⚠️ Gagal menganalisis link tersebut.", ephemeral=True)
        return

    is_yt = "youtu" in url.lower()
    embed = discord.Embed(
        title="🎬 Ringkasan Video YouTube" if is_yt else "🔗 Ringkasan Halaman Web",
        description=summary_text[:3900],
        color=discord.Color.red() if is_yt else discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="🔗 Tautan Sumber", value=url.strip()[:500], inline=False)
    if pertanyaan:
        embed.add_field(name="❓ Fokus Pertanyaan", value=pertanyaan[:300], inline=False)
    embed.set_footer(text=f"Diminta oleh {interaction.user.display_name}")
    await interaction.followup.send(embed=embed, ephemeral=not publik)


@bot.tree.command(
    name="cari",
    description="Cari informasi, berita, skor, harga, atau fakta terbaru hari ini via Google Search AI",
)
@app_commands.describe(
    pertanyaan="Apa informasi terbaru hari ini yang ingin Anda cari?",
    publik="False = hanya terlihat oleh Anda sendiri, True = tampilkan ke channel",
)
async def slash_cari(
    interaction: discord.Interaction,
    pertanyaan: str,
    publik: bool = False,
):
    await interaction.response.defer(ephemeral=not publik)
    tz_name = BOT_TIMEZONE
    if interaction.guild is not None:
        tz_name = get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)

    answer_text, err_msg = await search_web_with_gemini(
        pertanyaan,
        timezone_name=tz_name,
        http_session=bot.http_session,
    )
    if err_msg or not answer_text:
        await interaction.followup.send(err_msg or "⚠️ Gagal mencari informasi.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🔎 {pertanyaan[:230]}",
        description=answer_text[:3950],
        color=discord.Color.brand_green(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"Google Search Grounding • Diminta oleh {interaction.user.display_name}")
    await interaction.followup.send(embed=embed, ephemeral=not publik)


# ==============================================================================
# FITUR 4: MINI-GAME TONGKRONGAN AI (/game) + PAPAN SKOR SERVER
# ==============================================================================
game_group = app_commands.Group(
    name="game",
    description="Mainkan Mini-Game Tongkrongan AI seru bareng warga server & kejar Papan Skor!",
    guild_only=True,
)


async def _text_game_timeout_watcher(channel: discord.abc.Messageable, channel_id: int, state_ref: dict) -> None:
    """Mengungkap jawaban otomatis bila waktu tebak kata di chat habis tanpa pemenang."""
    try:
        await asyncio.sleep(GAME_ROUND_TIMEOUT_SEC)
    except asyncio.CancelledError:
        return

    current = active_channel_games.get(channel_id)
    if current is not state_ref:
        return

    active_channel_games.pop(channel_id, None)
    view_obj: discord.ui.View | None = state_ref.get("view")
    msg_obj: discord.Message | None = state_ref.get("message")
    if view_obj and msg_obj:
        for child in view_obj.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await msg_obj.edit(view=view_obj)
        except discord.HTTPException:
            pass

    try:
        await channel.send(
            f"⌛ **Waktu Habis!** Belum ada yang berhasil menebak dengan tepat.\n"
            f"🔑 Jawaban yang benar adalah: **`{state_ref['answer']}`**\n"
            f"*(Ketik `/game mulai` untuk mencoba tantangan baru!)*"
        )
    except discord.HTTPException:
        pass


@game_group.command(
    name="mulai",
    description="Mulai ronde Mini-Game AI di channel ini dan rebut poin klasemen!",
)
@app_commands.describe(jenis="Pilih mode permainan (kosongkan untuk mode acak kejutan!)")
@app_commands.choices(
    jenis=[
        app_commands.Choice(name="🎭 Tebak dari Emoji - +20 Poin", value="emoji"),
        app_commands.Choice(name="🧠 Kuis Trivia Cepat A/B/C/D - +15 Poin", value="trivia"),
        app_commands.Choice(name="🕵️ Tebak Kata Misteri - +20 Poin", value="riddle"),
        app_commands.Choice(name="🔀 Susun Huruf Acak - +15 Poin", value="scramble"),
    ]
)
async def slash_game_mulai(
    interaction: discord.Interaction,
    jenis: app_commands.Choice[str] | None = None,
):
    channel = interaction.channel
    if (
        not isinstance(channel, (discord.TextChannel, discord.Thread))
        or interaction.guild is None
        or (isinstance(channel, discord.Thread) and channel.name.startswith(("ai-", "draw-")))
    ):
        await interaction.response.send_message(
            "⚠️ Mini-Game hanya bisa dimainkan di Text Channel atau Thread publik server (bukan ruang sesi `ai-`/`draw-`).",
            ephemeral=True,
        )
        return

    if channel.id in active_channel_games:
        await interaction.response.send_message(
            "🎮 Masih ada ronde game yang sedang berlangsung di channel ini! Tebak dulu atau gunakan `/game stop`.",
            ephemeral=True,
        )
        return

    chosen_mode = jenis.value if jenis else random.choice(["emoji", "trivia", "riddle", "scramble"])
    points = GAME_POINTS_BY_MODE.get(chosen_mode, 15)
    await interaction.response.defer()

    # Cek ulang setelah defer agar tidak tabrakan bila 2 orang mengetik bersamaan
    if channel.id in active_channel_games:
        await interaction.followup.send(
            "🎮 Ronde baru saja dimulai oleh member lain! Yuk ikut menebak di atas.",
            ephemeral=True,
        )
        return

    q_data = await generate_ai_game_question(
        chosen_mode,
        interaction.guild.id,
        http_session=bot.http_session,
    )

    if chosen_mode == "trivia":
        letters = ("A", "B", "C", "D")
        opt_lines = "\n".join(f"**{letters[i]}.** {q_data['options'][i]}" for i in range(4))
        embed = discord.Embed(
            title=f"🧠 KUIS TRIVIA CEPAT — Berhadiah +{points} Poin!",
            description=(
                f"❓ **{q_data['question']}**\n\n"
                f"{opt_lines}\n\n"
                f"⚡ *Klik tombol jawaban paling cepat di bawah! (1x kesempatan per orang, waktu {GAME_ROUND_TIMEOUT_SEC} detik)*"
            ),
            color=discord.Color.purple(),
        )
        embed.set_footer(text=f"Dimulai oleh {interaction.user.display_name}")
        view = TriviaButtonsView(channel.id, interaction.guild.id, q_data, points)
        active_channel_games[channel.id] = {
            "type": "trivia",
            "starter_id": interaction.user.id,
            "answer": q_data["options"][q_data["correct_index"]],
            "points": points,
            "view": view,
        }
        sent_msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = sent_msg
        active_channel_games[channel.id]["message"] = sent_msg
        return

    if chosen_mode == "emoji":
        title = f"🎭 TEBAK DARI EMOJI — Berhadiah +{points} Poin!"
        desc = (
            f"🏷️ **Kategori:** `{q_data.get('category', 'Populer')}`\n\n"
            f"# {q_data['clue_emojis']}\n\n"
            f"💬 *Ketik tebakanmu langsung di chat sekarang! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
        )
        color = discord.Color.gold()
        aliases = q_data.get("aliases") or []
    elif chosen_mode == "riddle":
        clues_fmt = "\n".join(f"**{i + 1}.** {c}" for i, c in enumerate(q_data["clues"]))
        title = f"🕵️ SIAPAKAH / APAKAH AKU? — Berhadiah +{points} Poin!"
        desc = (
            f"🏷️ **Kategori:** `{q_data.get('category', 'Misteri')}`\n\n"
            f"{clues_fmt}\n\n"
            f"💬 *Ketik jawabannya langsung di chat! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
        )
        color = discord.Color.dark_teal()
        aliases = q_data.get("aliases") or []
    else:  # scramble
        scrambled = scramble_word(str(q_data["answer"]))
        title = f"🔀 SUSUN HURUF ACAK — Berhadiah +{points} Poin!"
        desc = (
            f"🏷️ **Kategori:** `{q_data.get('category', 'Kata Umum')}`\n\n"
            f"🔤 Susun huruf berikut menjadi 1 kata yang benar:\n"
            f"## `{scrambled}`\n\n"
            f"💬 *Ketik kata yang benar langsung di chat! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
        )
        color = discord.Color.blurple()
        aliases = []

    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text=f"Dimulai oleh {interaction.user.display_name} • Klik tombol di bawah jika butuh bantuan")
    ctrl_view = TextGuessControlView(channel.id, interaction.user.id)
    state_obj: dict = {
        "type": chosen_mode,
        "starter_id": interaction.user.id,
        "answer": str(q_data["answer"]).strip(),
        "aliases": aliases,
        "extra_hint": q_data.get("extra_hint", ""),
        "points": points,
        "view": ctrl_view,
    }
    active_channel_games[channel.id] = state_obj
    sent_msg = await interaction.followup.send(embed=embed, view=ctrl_view, wait=True)
    state_obj["message"] = sent_msg
    state_obj["timeout_task"] = asyncio.create_task(
        _text_game_timeout_watcher(channel, channel.id, state_obj)
    )


@game_group.command(
    name="papan_skor",
    description="Lihat Top 10 Klasemen Papan Skor Mini-Game di server ini",
)
async def slash_game_leaderboard(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("⚠️ Hanya tersedia di dalam server.", ephemeral=True)
        return

    board = get_guild_leaderboard(interaction.guild.id, top_n=10)
    if not board:
        await interaction.response.send_message(
            "🏆 **Papan Skor masih kosong!**\nYuk jadilah juara pertama dengan mengetik `/game mulai`!",
            ephemeral=False,
        )
        return

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines: list[str] = []
    for idx, row in enumerate(board, start=1):
        badge = medals.get(idx, f"`#{idx}`")
        lines.append(
            f"{badge} <@{row['user_id']}> — **{row['points']} Poin** ({row['wins']}x menang)"
        )

    rank, my_pts, my_wins = get_user_rank_info(interaction.guild.id, interaction.user.id)
    embed = discord.Embed(
        title=f"🏆 Papan Skor Mini-Game — {interaction.guild.name}",
        description="\n".join(lines),
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    )
    if rank is not None:
        embed.set_footer(text=f"Posisi Anda: #{rank} • {my_pts} Poin ({my_wins}x menang)")
    else:
        embed.set_footer(text="Anda belum memiliki skor — ketik /game mulai untuk ikut bermain!")
    await interaction.response.send_message(embed=embed)


@game_group.command(
    name="stop",
    description="Hentikan ronde Mini-Game yang sedang berjalan di channel ini",
)
async def slash_game_stop(interaction: discord.Interaction):
    channel = interaction.channel
    if channel is None or channel.id not in active_channel_games:
        await interaction.response.send_message(
            "ℹ️ Tidak ada ronde Mini-Game yang sedang aktif di channel ini.",
            ephemeral=True,
        )
        return

    state = active_channel_games[channel.id]
    is_mod = isinstance(interaction.user, discord.Member) and (
        interaction.user.guild_permissions.administrator
        or interaction.user.guild_permissions.manage_messages
    )
    if interaction.user.id != state.get("starter_id") and not is_mod:
        await interaction.response.send_message(
            "⚠️ Hanya pemulai ronde ini atau Moderator yang dapat menghentikan permainan.",
            ephemeral=True,
        )
        return

    active_channel_games.pop(channel.id, None)
    task = state.get("timeout_task")
    if task and not task.done():
        task.cancel()

    view_obj: discord.ui.View | None = state.get("view")
    msg_obj: discord.Message | None = state.get("message")
    if view_obj:
        if hasattr(view_obj, "finished"):
            view_obj.finished = True
        view_obj.stop()
        for child in view_obj.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if msg_obj:
            try:
                await msg_obj.edit(view=view_obj)
            except discord.HTTPException:
                pass

    await interaction.response.send_message(
        f"🛑 Ronde Mini-Game dihentikan oleh {interaction.user.mention}. "
        f"Jawaban dari soal tadi adalah: **`{state.get('answer', '-')}`**."
    )


@game_group.command(
    name="reset_skor",
    description="Reset seluruh Papan Skor Mini-Game server kembali ke 0 (Khusus Admin)",
)
async def slash_game_reset_skor(interaction: discord.Interaction):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("⚠️ Hanya tersedia di server.", ephemeral=True)
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "⚠️ Hanya **Administrator** server yang dapat mereset seluruh Papan Skor.",
            ephemeral=True,
        )
        return

    reset_guild_scores(interaction.guild.id)
    await save_game_scores_to_disk()
    await interaction.response.send_message(
        "🔄 **Papan Skor Mini-Game server berhasil direset ke 0!** Musim kompetisi baru dimulai!"
    )


bot.tree.add_command(game_group)


@bot.tree.command(
    name="bantuan",
    description="Panduan lengkap cara memakai seluruh fitur Gemini AI di server ini",
)
async def slash_bantuan(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"📚 Panduan Lengkap Fitur Gemini AI (v{BOT_VERSION})",
        description="Berikut daftar fitur pintar yang bisa langsung dipakai seluruh member:",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="1️⃣ Ruang Chat Privat, Vision, Voice Note & Gambar",
        value=(
            "• Klik tombol di panel `/setup_panel` untuk membuka ruang `ai-...` atau `draw-...`.\n"
            "• Kirim teks, **Voice Note (🎤)**, foto/screenshot error, file kode, atau link YouTube/Web!\n"
            "• Gunakan `/model` untuk ganti kepribadian & `/reset` untuk bersihkan memori."
        ),
        inline=False,
    )
    embed.add_field(
        name="2️⃣ Tekan-Tahan Pesan (Tanpa Ketik Command!)",
        value=(
            "• **Di HP:** Tekan & tahan pesan siapa saja ➔ pilih **Apps**.\n"
            "• **Di PC:** Klik kanan pesan ➔ pilih **Apps**.\n"
            "• Pilih **`🌐 Terjemahkan ke Indonesia`** atau **`💡 Jelaskan Pesan Ini`**!"
        ),
        inline=False,
    )
    embed.add_field(
        name="3️⃣ Ringkas Chat, YouTube, Web & Info Terbaru Hari Ini",
        value=(
            "• `/cari` — Cek berita, skor, cuaca, harga, atau info terbaru hari ini (Google Search).\n"
            "• `/ringkas_link` — Rangkum isi video YouTube atau artikel web dalam hitungan detik.\n"
            "• `/ringkas` — Rangkum 25–150 chat terakhir di channel agar tidak ketinggalan obrolan."
        ),
        inline=False,
    )
    embed.add_field(
        name="4️⃣ Mini-Game Tongkrongan & AI Agent Server",
        value=(
            "• `/game mulai` — Main Tebak Emoji, Kuis Trivia, Kata Misteri, & Acak Kata!\n"
            "• `/game papan_skor` — Cek Top 10 klasemen juara server (`/game stop` untuk akhiri ronde).\n"
            "• *Khusus Admin:* `/setup_panel` & `/agent` (`chat`, `gallery`, `welcome`, `persona`, `sapa`, `status`)."
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
        name="🌐 Agent & Game",
        value=(
            f"`{len(chat_agent_channels)}` chat | `{len(gallery_agent_channels)}` galeri | "
            f"`{len(active_channel_games)}` game"
        ),
        inline=True,
    )
    embed.add_field(name="🕒 Jam Server AI", value=f"`{time_ctx['clock']}` ({time_ctx['day_name']})", inline=False)
    img_engine_info = (
        f"`{GEMINI_IMAGE_MODEL}` (Paid)"
        if GEMINI_PAID_IMAGE_ENABLED
        else "`Flux AI` (Free Tier Instan)"
    )
    embed.add_field(
        name="♊ Model Aktif",
        value=(
            f"Utama: `{GEMINI_DEFAULT_MODEL}`\n"
            f"Kilat: `{GEMINI_FAST_MODEL}`\n"
            f"Koding/Riset: `{GEMINI_REASONING_MODEL}`\n"
            f"Live Search: `{GEMINI_SEARCH_MODEL}`\n"
            f"Gambar: {img_engine_info}"
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

    # Cadangan Auto-Welcome lewat pesan System Join Discord (bekerja walau Server Members Intent belum aktif!)
    if message.type == discord.MessageType.new_member and message.guild is not None:
        await _trigger_member_welcome(message.guild, message.author)
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
                include_audio=False,
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

        # 1C. Thread biasa (bukan ai-/draw-) yang sedang menjalankan Mini-Game
        if message.channel.id in active_channel_games:
            if await handle_active_game_guess(message):
                return

    # ==========================================================================
    # BAGIAN 2: AI AGENT KOMUNITAS DI CHANNEL PUBLIK (GALERI & AUTO-CHAT)
    # ==========================================================================
    if isinstance(message.channel, discord.TextChannel) and bot.user is not None:
        channel_id = message.channel.id

        # Catat aktivitas manusia lebih awal agar sapaan sepi tidak salah hitung jika channel juga dipakai Galeri
        if channel_id in chat_agent_channels and channel_id not in gallery_agent_channels:
            pass
        elif channel_id in chat_agent_channels and channel_id in gallery_agent_channels and message.attachments:
            record_human_channel_activity(channel_id)

        # 2A. GALLERY AUTO-COMMENT (Scan Foto, Gambar, & Video Klip Pendek)
        if channel_id in gallery_agent_channels and message.attachments:
            lock = get_agent_channel_lock(channel_id)
            async with lock:
                async with message.channel.typing():
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
                        await message.reply(comment_text[:1900], mention_author=False)
                        return

        # 2B. MINI-GAME TONGKRONGAN AKTIF (Tebak Emoji / Kata Misteri / Susun Huruf)
        if channel_id in active_channel_games:
            if channel_id in chat_agent_channels:
                record_human_channel_activity(channel_id)
            if await handle_active_game_guess(message):
                return

        # 2C. AUTO-CHAT KOMUNITAS NATURAL (Teks, Stiker, Emoji, Link, & Sapaan)
        if channel_id in chat_agent_channels:
            should_reply, use_reply_ref = should_agent_reply_in_chat(message, bot.user)
            if should_reply:
                lock = get_agent_channel_lock(channel_id)
                async with lock:
                    async with message.channel.typing():
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
