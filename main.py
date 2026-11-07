import logging
import sys
import time
import aiohttp
import discord
from discord.ext import commands, tasks

from cogs import (
    register_all_cogs,
    ringkas_chat_cmd,
    ringkas_link_cmd,
    slash_cari,
)
from cogs.growth_cog import run_voice_xp_check
from voice_activity import reset_voice_sessions
from tickets import run_ticket_check
from levels import run_level_season_check
from analytics_export import (
    cleanup_analytics_runtime,
    load_analytics_from_disk,
    run_analytics_check,
    save_analytics_to_disk,
)
from prefixes import (
    cleanup_prefixes_runtime,
    load_prefixes_from_disk,
    prefixes_for,
    save_prefixes_to_disk,
)
from i18n import (
    cleanup_i18n_runtime,
    load_lang_from_disk,
    save_lang_to_disk,
)
from music_playlists import (
    cleanup_music_playlist_runtime,
    load_playlists_from_disk,
    save_playlists_to_disk,
)
from antinuke import refresh_freezes
from raid_guard import (
    cleanup_raid_runtime,
    load_raid_from_disk,
    save_raid_to_disk,
    tick as raid_tick,
)
from antinuke import (
    cleanup_antinuke_runtime,
    load_antinuke_from_disk,
    save_antinuke_to_disk,
)
from menu_builder import (
    cleanup_menu_runtime,
    load_menus_from_disk,
    save_menus_to_disk,
)
import command_policy
import flow_triggers
import link_embed
import modal_forms
import webhook_identity
from growth_tracker import (
    cleanup_growth_runtime,
    load_growth_from_disk,
    save_growth_to_disk,
)
from economy import (
    cleanup_economy_runtime,
    load_economy_from_disk,
    save_economy_to_disk,
)
from audit_log import (
    cleanup_audit_runtime,
    load_audit_from_disk,
    save_audit_to_disk,
)
from translate_tools import (
    cleanup_translate_runtime,
    load_translate_from_disk,
    save_translate_to_disk,
)
from web_dashboard import start_dashboard, stop_dashboard
from community_agent import (
    cleanup_stale_agent_runtime,
    load_agent_config_from_disk,
    run_idle_chat_check,
    run_morning_digest_check,
    save_agent_config_to_disk,
    search_agent_channels,
    youtube_agent_channels,
)
from community_tools import (
    load_community_tools_from_disk,
    record_last_error,
    report_error,
    run_backup_check,
    run_reminder_check,
    save_community_tools_to_disk,
)
from config import DISCORD_BOT_TOKEN, DISCORD_GUILD_ID
from ai_guard import cleanup_ai_guard_runtime
from ui_theme import cleanup_ui_runtime, load_ui_themes_from_disk, save_ui_themes_to_disk
from antispam import (
    cleanup_antispam_runtime,
    load_antispam_from_disk,
    save_antispam_to_disk,
)
from honeypot import load_honeypot_from_disk
from engagement import (
    cleanup_engagement_runtime,
    load_engagement_from_disk,
    run_engagement_check,
    save_engagement_to_disk,
)
from games import load_game_scores_from_disk, save_game_scores_to_disk
from insights import (
    cleanup_insights_runtime,
    load_ai_usage_from_disk,
    save_ai_usage_to_disk,
)
from levels import (
    cleanup_levels_runtime,
    load_levels_from_disk,
    save_levels_to_disk,
)
from music import (
    WAVELINK_AVAILABLE,
    cleanup_music_runtime,
    connect_nodes,
    ensure_nodes_alive,
    load_music_settings_from_disk,
    music_status,
    run_music_panel_check,
    save_music_settings_to_disk,
)
from server_tools import (
    cleanup_server_tools_runtime,
    load_server_tools_from_disk,
)
from suggestions import (
    cleanup_suggestions_runtime,
    load_suggestions_from_disk,
)
from temp_voice import (
    cleanup_temp_voice_runtime,
    load_temp_voice_from_disk,
    sweep_empty_rooms,
)
from moderation import (
    cleanup_moderation_runtime,
    load_moderation_from_disk,
)
from social_notify import (
    cleanup_social_runtime,
    load_social_from_disk,
    run_social_check,
    social_guilds,
    twitch_configured,
)
from server_features import (
    load_server_features_from_disk,
    run_facts_check,
    run_serverstats_check,
    save_server_features_to_disk,
)
from tickets import (
    cleanup_tickets_runtime,
    load_tickets_from_disk,
    save_tickets_to_disk,
)
from storage import (
    cleanup_expired_sessions,
    load_sessions_from_disk,
    save_sessions_to_disk,
)
from utils import prune_expired_user_cooldowns, sanitize_error_message
from views import (
    ChatPersonaSwitchView,
    EndSessionView,
    ForumPostSolvedView,
    ImageSettingsView,
    MainPanelControlView,
    SuggestionVoteView,
    GiveawayJoinView,
    MusicPlayerView,
    TicketActionsView,
    TicketPanelView,
    VerificationGateView,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gemini_bot")


class GeminiDiscordBot(commands.Bot):
    """Inti orkestrator bot Discord dengan arsitektur modular `cogs/` yang ringan untuk Wispbyte."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=self._resolve_prefix,
            intents=intents,
            help_command=None,
        )
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at: float = time.time()

    @staticmethod
    def _resolve_prefix(_bot, message) -> list[str]:
        """Prefix bawaan `!` + prefix khusus server (`/prefix atur`)."""
        guild = getattr(message, "guild", None)
        return prefixes_for(getattr(guild, "id", None))

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

    async def _handle_app_command_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Menangani error Slash Command: balas pengguna & kirim ringkasan ke channel log."""
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            try:
                await interaction.response.send_message(
                    f"⏳ Mohon tunggu **{error.retry_after:.0f} detik** lagi sebelum memakai fitur ini.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass
            return

        original = getattr(error, "original", error)
        logger.warning("Error Slash Command: %s", sanitize_error_message(original))
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⚠️ Terjadi kendala saat menjalankan command ini. Coba lagi sebentar lagi.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "⚠️ Terjadi kendala saat menjalankan command ini. Coba lagi sebentar lagi.",
                    ephemeral=True,
                )
        except discord.HTTPException:
            pass
        await report_error(
            self,
            context=f"/{getattr(interaction.command, 'qualified_name', 'command')}",
            exc=original,
            guild=interaction.guild,
        )

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        """Mencatat seluruh exception event Discord & melaporkannya ke channel log."""
        exc = sys.exc_info()[1]
        logger.exception("Error pada event %s", event_method)
        if exc is not None:
            record_last_error(f"event:{event_method}", exc)
            await report_error(self, context=f"event:{event_method}", exc=exc)

    async def setup_hook(self) -> None:
        # 1. Buat koneksi HTTP bersama agar cepat & hemat RAM
        self.http_session = aiohttp.ClientSession()

        # 2. Muat kembali sesi privat, konfigurasi AI Agent, & papan skor game dari disk
        loaded_chats, loaded_imgs = load_sessions_from_disk()
        loaded_agent_chats, loaded_galleries = load_agent_config_from_disk()
        loaded_score_guilds = load_game_scores_from_disk()
        loaded_stats, loaded_autorole, loaded_facts, loaded_security = load_server_features_from_disk()
        loaded_panels, loaded_reminders_count, loaded_starboard, loaded_sticky, loaded_verify = (
            load_community_tools_from_disk()
        )
        loaded_music = load_music_settings_from_disk()
        loaded_giveaways, loaded_birthdays, loaded_autoreply, loaded_announcements = (
            load_engagement_from_disk()
        )
        loaded_antispam = load_antispam_from_disk()
        loaded_honeypot = load_honeypot_from_disk()
        loaded_levels = load_levels_from_disk()
        loaded_tickets = load_tickets_from_disk()
        loaded_usage_days = load_ai_usage_from_disk()
        loaded_translate_guilds = load_translate_from_disk()
        loaded_audit_guilds = load_audit_from_disk()
        loaded_econ_guilds, loaded_econ_balances = load_economy_from_disk()
        loaded_growth_guilds = load_growth_from_disk()
        loaded_menus = load_menus_from_disk()
        loaded_webhooks = webhook_identity.load_from_disk()
        loaded_forms = modal_forms.load_from_disk()
        loaded_links = link_embed.load_from_disk()
        loaded_triggers = flow_triggers.load_from_disk()
        loaded_antinuke = load_antinuke_from_disk()
        loaded_raid = load_raid_from_disk()
        loaded_playlists = load_playlists_from_disk()
        loaded_langs = load_lang_from_disk()
        loaded_prefixes = load_prefixes_from_disk()
        loaded_analytics = load_analytics_from_disk()
        loaded_themes = load_ui_themes_from_disk()
        loaded_afk, loaded_threads = load_server_tools_from_disk()
        logger.info(
            "Perkakas server dimuat: %d status AFK, %d channel auto-thread.", loaded_afk, loaded_threads
        )
        loaded_saran_guilds, loaded_saran_items = load_suggestions_from_disk()
        logger.info(
            "Kotak saran dimuat: %d saran di %d server.", loaded_saran_items, loaded_saran_guilds
        )
        loaded_hub_guilds, loaded_rooms = load_temp_voice_from_disk()
        logger.info(
            "Temp Voice dimuat: %d server, %d room tersimpan.", loaded_hub_guilds, loaded_rooms
        )
        loaded_mod_guilds, loaded_mod_cases = load_moderation_from_disk()
        logger.info(
            "Moderasi dimuat: %d server, %d kasus tercatat.", loaded_mod_guilds, loaded_mod_cases
        )
        loaded_social_guilds = load_social_from_disk()
        logger.info(
            "Notifikasi sosial dimuat: %d server | Twitch: %s.",
            loaded_social_guilds,
            "siap (kredensial terisi)" if twitch_configured() else "belum dikonfigurasi (YouTube/RSS tetap jalan)",
        )
        if not twitch_configured():
            twitch_subs = sum(
                1
                for gid_data in social_guilds.values()
                for sub in (gid_data.get("subs") or [])
                if sub.get("platform") == "twitch"
            )
            if twitch_subs:
                logger.warning(
                    "⚠️ Ada %d langganan Twitch, tetapi TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET kosong. "
                    "Isi di tab Variables Wispbyte lalu restart, atau uji dengan /sosial status.",
                    twitch_subs,
                )
        logger.info(
            "Memori dimuat: %d chat privat, %d gambar, %d Auto-Chat, %d Galeri, %d YouTube, %d Cari, %d papan skor server.",
            loaded_chats,
            loaded_imgs,
            loaded_agent_chats,
            loaded_galleries,
            len(youtube_agent_channels),
            len(search_agent_channels),
            loaded_score_guilds,
        )
        logger.info(
            "Fitur server dimuat: %d Server Stats, %d Auto Role, %d Fakta Harian, %d Anti-Phishing.",
            loaded_stats,
            loaded_autorole,
            loaded_facts,
            loaded_security,
        )
        logger.info(
            "Musik dimuat: %d server dengan pengaturan tersimpan | %s",
            loaded_music,
            music_status(),
        )
        logger.info(
            "Fitur engagement dimuat: %d Giveaway, %d Ulang Tahun, %d Auto-Responder, %d Pengumuman Terjadwal.",
            loaded_giveaways,
            loaded_birthdays,
            loaded_autoreply,
            loaded_announcements,
        )
        logger.info("Anti-Spam & Anti-Raid dimuat: %d server aktif.", loaded_antispam)
        logger.info("Honeypot dimuat: %d server.", loaded_honeypot)
        logger.info(
            "Leveling & Tiket dimuat: %d server leveling, %d server tiket.",
            loaded_levels,
            loaded_tickets,
        )
        logger.info("Catatan pemakaian AI dimuat: %d hari terakhir.", loaded_usage_days)
        logger.info("Penerjemah dimuat: %d server dengan channel terpilih.", loaded_translate_guilds)
        logger.info("Audit log dimuat: %d server dengan channel log.", loaded_audit_guilds)
        logger.info(
            "Ekonomi dimuat: %d server, %d saldo member.", loaded_econ_guilds, loaded_econ_balances
        )
        logger.info("Pelacak pertumbuhan dimuat: %d server.", loaded_growth_guilds)
        logger.info("Panel menu dimuat: %d panel.", loaded_menus)
        logger.info("Webhook identitas dimuat: %d channel.", loaded_webhooks)
        logger.info("Formulir (modal) dimuat: %d formulir.", loaded_forms)
        logger.info("Tautan embed dimuat: %d tautan.", loaded_links)
        logger.info("Pemicu gabung dimuat: %d server.", loaded_triggers)
        logger.info("Anti-Nuke dimuat: %d server.", loaded_antinuke)
        logger.info("Raid Guard dimuat: %d server.", loaded_raid)
        logger.info("Playlist musik dimuat: %d member.", loaded_playlists)
        logger.info("Pengaturan bahasa dimuat: %d server.", loaded_langs)
        logger.info("Prefix khusus dimuat: %d server.", loaded_prefixes)
        logger.info("Ekspor analitik dimuat: %d server.", loaded_analytics)
        logger.info("Tema tampilan UI dimuat: %d server dengan kustomisasi.", loaded_themes)
        try:
            import welcome_media

            logger.info(
                "Media kustom (banner sambutan/boost) dimuat: %.2f MB di data/media | Pillow: %s",
                welcome_media.media_footprint_mb(),
                "tersedia" if welcome_media.pillow_available() else "tidak ada (kartu dinamis nonaktif)",
            )
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Gagal membaca folder media: %s", exc)
        logger.info(
            "Fitur komunitas dimuat: %d Panel Role, %d Pengingat, %d Starboard, %d Sticky, %d Verifikasi.",
            loaded_panels,
            loaded_reminders_count,
            loaded_starboard,
            loaded_sticky,
            loaded_verify,
        )

        # 3. Daftarkan seluruh View persisten (sekali saja saat startup)
        self.add_view(MainPanelControlView())
        self.add_view(EndSessionView())
        self.add_view(ChatPersonaSwitchView())
        self.add_view(ImageSettingsView())
        self.add_view(ForumPostSolvedView())
        self.add_view(VerificationGateView())
        self.add_view(MusicPlayerView())  # panel pemutar musik persisten (ala Rythm)
        self.add_view(GiveawayJoinView())  # tombol 🎉 giveaway tetap aktif setelah restart
        self.add_view(SuggestionVoteView())  # tombol 👍/👎 kotak saran
        self.add_view(TicketPanelView())   # panel "Buat Tiket"
        self.add_view(TicketActionsView())  # tombol klaim/tutup di dalam thread tiket

        # 3B. Hubungkan node musik Lavalink (dilewati otomatis bila belum dikonfigurasi)
        if WAVELINK_AVAILABLE:
            await connect_nodes(self)

        # 3C. Laporkan error Slash Command ke channel log (bila Admin mengaturnya)
        self.tree.on_error = self._handle_app_command_error

        # 3D. Nyalakan dashboard web read-only (hanya bila DASHBOARD_TOKEN & port tersedia)
        await start_dashboard(self)

        # 4. Jalankan background watcher untuk Pemecah Sepi, Morning Digest, & Pembersih RAM
        if not idle_chat_watcher.is_running():
            idle_chat_watcher.start()
        if WAVELINK_AVAILABLE and not music_panel_watcher.is_running():
            music_panel_watcher.start()

        # 5. Sinkronisasi Slash Commands (tanpa duplikasi Guild vs Global)
        try:
            if DISCORD_GUILD_ID:
                guild_obj = discord.Object(id=DISCORD_GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced_guild = await self.tree.sync(guild=guild_obj)
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                logger.info(
                    "Slash commands tersinkron instan ke Guild %s (%d command utama, bebas duplikat).",
                    DISCORD_GUILD_ID,
                    len(synced_guild),
                )
            else:
                synced_global = await self.tree.sync()
                logger.info("Global Slash commands tersinkron (%d command utama).", len(synced_global))
        except Exception as exc:
            logger.warning("Gagal sinkronisasi Slash Commands: %s", sanitize_error_message(exc))

    async def close(self) -> None:
        if idle_chat_watcher.is_running():
            idle_chat_watcher.cancel()
        if music_panel_watcher.is_running():
            music_panel_watcher.cancel()
        await save_sessions_to_disk()
        await save_agent_config_to_disk()
        await save_game_scores_to_disk()
        await save_server_features_to_disk()
        await save_community_tools_to_disk()
        await save_music_settings_to_disk()
        await save_engagement_to_disk()
        await save_antispam_to_disk()
        reset_voice_sessions()
        await save_levels_to_disk()
        await stop_dashboard()
        await save_tickets_to_disk()
        await save_ai_usage_to_disk()
        await save_translate_to_disk()
        await save_audit_to_disk()
        await save_economy_to_disk()
        await save_growth_to_disk()
        await save_menus_to_disk()
        await save_antinuke_to_disk()
        await save_raid_to_disk()
        await save_playlists_to_disk()
        await save_lang_to_disk()
        await save_prefixes_to_disk()
        await save_analytics_to_disk()
        await save_ui_themes_to_disk()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()


bot = GeminiDiscordBot()
register_all_cogs(bot)

# Sembunyikan command khusus pengelola dari member biasa (lihat command_policy.py).
_policy = command_policy.apply(bot.tree)

# Wizard pemasangan cepat untuk admin awam.
from cogs.mulai_cog import mulai_cmd  # noqa: E402

bot.tree.add_command(mulai_cmd)

# Alias kompatibilitas untuk pemanggilan langsung dari modul/pengujian
slash_ringkas = ringkas_chat_cmd
slash_ringkas_link = ringkas_link_cmd


@tasks.loop(seconds=15)
async def idle_chat_watcher():
    """Memantau Auto-Chat tiap 15 detik, Digest & Fakta Harian tiap 1 menit, Server Stats tiap 5 menit,
    serta pembersihan RAM & data kedaluwarsa tiap 1 jam."""
    try:
        await run_idle_chat_check(bot, http_session=bot.http_session)
        await raid_tick(bot)         # akhiri mode raid yang sudah kedaluwarsa
        await run_reminder_check(bot)
        await run_ticket_check(bot)  # peringatan SLA & auto-close tiket menganggur
        if idle_chat_watcher.current_loop % 4 == 0:
            await run_level_season_check(bot)  # reset musim level otomatis (bila diaktifkan)
        await run_engagement_check(bot)  # giveaway berakhir, ucapan ultah, pengumuman terjadwal
        if idle_chat_watcher.current_loop % 4 == 0:
            await run_morning_digest_check(bot, http_session=bot.http_session)
            await run_facts_check(bot, http_session=bot.http_session)
            await run_social_check(bot, http_session=bot.http_session)  # YouTube/Twitch/TikTok (0 kuota AI)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 4 == 0:
            # Node Lavalink publik sering restart: pulihkan otomatis tanpa restart bot.
            await ensure_nodes_alive(bot)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 4 == 0:
            # XP voice: beri XP untuk setiap menit penuh di voice channel (0 kuota AI)
            await run_voice_xp_check(bot)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 20 == 0:
            await run_serverstats_check(bot)
            await run_analytics_check(bot, session=bot.http_session)  # ekspor CSV ke webhook
            try:
                await sweep_empty_rooms(bot)  # bersihkan room Temp Voice yang kosong
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.debug("Pembersihan Temp Voice gagal: %s", exc)
            await run_backup_check(bot)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 240 == 0:
            if cleanup_expired_sessions() > 0:
                await save_sessions_to_disk()
            cleanup_stale_agent_runtime()
            cleanup_music_runtime()
            cleanup_engagement_runtime()
            cleanup_antispam_runtime()
            cleanup_levels_runtime()
            cleanup_tickets_runtime()
            cleanup_insights_runtime()
            cleanup_ai_guard_runtime()   # buang cache jawaban AI yang kedaluwarsa (hemat RAM)
            cleanup_translate_runtime()  # buang cache terjemahan & rate limit lama
            cleanup_audit_runtime()      # buang konfigurasi audit log tanpa channel
            cleanup_economy_runtime()    # bersihkan rate-limit transfer ekonomi
            cleanup_growth_runtime()     # pangkas data pertumbuhan lama
            cleanup_menu_runtime()       # bersihkan cooldown self role menu
            cleanup_antinuke_runtime()   # pangkas catatan kejadian anti-nuke
            await refresh_freezes(bot)   # cairkan mode beku anti-nuke yang kedaluwarsa
            cleanup_raid_runtime()       # buang catatan join raid yang kedaluwarsa
            cleanup_music_playlist_runtime()  # buang playlist kosong
            cleanup_i18n_runtime()            # buang bahasa default (hemat I/O)
            cleanup_prefixes_runtime()        # buang prefix yang sama dengan bawaan
            cleanup_analytics_runtime()       # buang konfigurasi ekspor kosong
            cleanup_ui_runtime()
            cleanup_social_runtime()
            cleanup_moderation_runtime()
            cleanup_temp_voice_runtime()
            cleanup_suggestions_runtime()
            cleanup_server_tools_runtime()
            await save_ai_usage_to_disk()
            prune_expired_user_cooldowns()
    except Exception as exc:
        logger.warning("Error pada idle_chat_watcher: %s", sanitize_error_message(exc))


@idle_chat_watcher.before_loop
async def before_idle_chat_watcher():
    await bot.wait_until_ready()


@tasks.loop(seconds=10)
async def music_panel_watcher():
    """Memperbarui progress bar panel pemutar musik (ala Rythm) tiap 10 detik."""
    try:
        await run_music_panel_check(bot)
    except Exception as exc:
        logger.warning("Error pada music_panel_watcher: %s", sanitize_error_message(exc))


@music_panel_watcher.before_loop
async def before_music_panel_watcher():
    await bot.wait_until_ready()


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
