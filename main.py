import logging
import sys
import time
import aiohttp
import discord
from discord.ext import commands, tasks

from cogs import (
    agent_group,
    game_group,
    register_all_cogs,
    ringkas_chat_cmd,
    ringkas_group,
    ringkas_link_cmd,
    sesi_group,
    slash_bantuan,
    slash_cari,
    slash_status,
)
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
from games import load_game_scores_from_disk, save_game_scores_to_disk
from server_features import (
    load_server_features_from_disk,
    run_facts_check,
    run_serverstats_check,
    save_server_features_to_disk,
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

        # 3B. Laporkan error Slash Command ke channel log (bila Admin mengaturnya)
        self.tree.on_error = self._handle_app_command_error

        # 4. Jalankan background watcher untuk Pemecah Sepi, Morning Digest, & Pembersih RAM
        if not idle_chat_watcher.is_running():
            idle_chat_watcher.start()

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
        await save_sessions_to_disk()
        await save_agent_config_to_disk()
        await save_game_scores_to_disk()
        await save_server_features_to_disk()
        await save_community_tools_to_disk()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()


bot = GeminiDiscordBot()
register_all_cogs(bot)

# Alias kompatibilitas untuk pemanggilan langsung dari modul/pengujian
slash_ringkas = ringkas_chat_cmd
slash_ringkas_link = ringkas_link_cmd


@tasks.loop(seconds=15)
async def idle_chat_watcher():
    """Memantau Auto-Chat tiap 15 detik, Digest & Fakta Harian tiap 1 menit, Server Stats tiap 5 menit,
    serta pembersihan RAM & data kedaluwarsa tiap 1 jam."""
    try:
        await run_idle_chat_check(bot, http_session=bot.http_session)
        await run_reminder_check(bot)
        if idle_chat_watcher.current_loop % 4 == 0:
            await run_morning_digest_check(bot, http_session=bot.http_session)
            await run_facts_check(bot, http_session=bot.http_session)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 20 == 0:
            await run_serverstats_check(bot)
            await run_backup_check(bot)
        if idle_chat_watcher.current_loop > 0 and idle_chat_watcher.current_loop % 240 == 0:
            if cleanup_expired_sessions() > 0:
                await save_sessions_to_disk()
            cleanup_stale_agent_runtime()
            prune_expired_user_cooldowns()
    except Exception as exc:
        logger.warning("Error pada idle_chat_watcher: %s", sanitize_error_message(exc))


@idle_chat_watcher.before_loop
async def before_idle_chat_watcher():
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
