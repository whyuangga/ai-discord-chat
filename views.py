import asyncio
import io
import logging
import re
import time
import discord

from config import (
    AGENT_DEFAULT_IDLE_MINUTES,
    AGENT_MAX_IDLE_POKES,
    AI_MODELS,
    BOT_TIMEZONE,
    BOT_VERSION,
    DEFAULT_IMAGE_SETTINGS,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_READER,
    MAX_THREADS_PER_USER,
    RATIO_OPTIONS,
    STYLE_OPTIONS,
    resolve_model_key,
)
import engagement
import music
from community_tools import grant_verification_role
from community_agent import (
    GREETING_PERSONAS,
    STYLE_DESCRIPTIONS,
    chat_agent_channels,
    clear_server_knowledge,
    delete_server_knowledge,
    digest_agent_guilds,
    format_idle_duration,
    gallery_agent_channels,
    goodbye_agent_guilds,
    get_guild_search_channels,
    get_guild_settings,
    get_guild_youtube_channels,
    get_server_knowledge_entries,
    save_agent_config_to_disk,
    search_agent_channels,
    set_chat_channel_config,
    set_digest_config,
    set_gallery_channel_config,
    set_goodbye_config,
    set_search_channel_config,
    set_welcome_config,
    set_youtube_channel_config,
    upsert_server_knowledge,
    welcome_agent_guilds,
    youtube_agent_channels,
)
from server_features import (
    facts_guilds,
    format_facts_schedule,
    save_server_features_to_disk,
    security_guilds,
    set_facts_config,
)
from storage import (
    get_image_settings,
    image_thread_settings,
    init_image_session,
    init_thread_session,
    mark_thread_closing,
    remove_thread_data,
    reset_thread_history,
    save_sessions_to_disk,
    switch_thread_model,
    thread_chats,
    unmark_thread_closing,
)
from utils import (
    build_session_transcript,
    find_solved_forum_tag,
    get_realtime_time_context,
    sanitize_error_message,
)

logger = logging.getLogger("gemini_bot.views")

_TIMEZONE_ALIASES: dict[str, str] = {
    "wib": "Asia/Jakarta",
    "jakarta": "Asia/Jakarta",
    "asia/jakarta": "Asia/Jakarta",
    "wita": "Asia/Makassar",
    "makassar": "Asia/Makassar",
    "bali": "Asia/Makassar",
    "asia/makassar": "Asia/Makassar",
    "wit": "Asia/Jayapura",
    "jayapura": "Asia/Jayapura",
    "papua": "Asia/Jayapura",
    "asia/jayapura": "Asia/Jayapura",
}


def build_main_panel_embed() -> discord.Embed:
    """Membuat tampilan Embed modern & rapi untuk Panel Utama Ruang Privat AI."""
    embed = discord.Embed(
        title="✨ PANEL RUANG PRIVAT GOOGLE GEMINI AI",
        description=(
            "Selamat datang di pusat layanan pintar **Google Gemini AI**!\n"
            "Klik salah satu tombol di bawah untuk membuka **Ruang Privat (Private Thread)** khusus Anda:\n\n"
            "💬 **Ruang Chat AI, Vision, Voice Note, PDF & Live Web**\n"
            "> • Bebas pilih **5 Mode Kepribadian** (Asisten, Kilat, Koding, Riset, Curhat).\n"
            "> • **Multimodal Lengkap:** Kirim **Voice Note (`🎤`)**, dokumen **`.pdf`**, foto/screenshot error, file kode, atau link **YouTube / Web**.\n"
            "> • **Info Terkini:** Otomatis mencari berita & fakta terbaru saat ditanya topik hari ini.\n\n"
            "🎨 **Studio Generate & Edit Gambar AI**\n"
            "> • Buat ilustrasi berkualitas tinggi cukup dengan mengetik deskripsi.\n"
            "> • Bebas pilih **7 Gaya Art** & **5 Ukuran Rasio**, serta bisa edit gambar lampiran!\n\n"
            "⚡ **Fitur Pintas di Seluruh Server:**\n"
            "> • **Tekan-Tahan Pesan ➔ Apps:** `🌐 Terjemahkan`, `💡 Jelaskan`, & `🔍 Cek Fakta / Hoaks`\n"
            "> • `/ringkas chat` • `/ringkas link` • `/cari` • `/game mulai` • `/bantuan`"
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Gemini AI v{BOT_VERSION} • Privasi terjaga di ruang khusus milik Anda")
    return embed


def _sanitize_username_for_thread(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-")
    return cleaned[:24] or "member"


def _validate_target_channel(interaction: discord.Interaction) -> tuple[discord.TextChannel | None, str | None]:
    """Memastikan panel dijalankan di TextChannel dan bot memiliki izin membuat Private Thread."""
    channel = interaction.channel
    if isinstance(channel, discord.Thread) and isinstance(channel.parent, discord.TextChannel):
        channel = channel.parent

    if not isinstance(channel, discord.TextChannel) or interaction.guild is None:
        return None, "⚠️ Fitur ini hanya dapat digunakan di dalam Text Channel server Discord."

    bot_member = interaction.guild.me
    if bot_member is not None:
        perms = channel.permissions_for(bot_member)
        missing: list[str] = []
        if not perms.create_private_threads:
            missing.append("`Create Private Threads`")
        if not perms.send_messages_in_threads:
            missing.append("`Send Messages in Threads`")
        if not perms.read_message_history:
            missing.append("`Read Message History`")
        if missing:
            joined = ", ".join(missing)
            return None, (
                f"⚠️ Bot belum memiliki izin berikut di channel {channel.mention}: {joined}.\n"
                "Mohon minta Admin server mengaktifkan izin tersebut pada Role Bot."
            )

    return channel, None


def _get_user_active_threads(guild: discord.Guild, user_id: int) -> list[discord.Thread]:
    """Mencari daftar thread AI milik pengguna yang masih aktif di server ini."""
    active: list[discord.Thread] = []

    all_tracked: dict[int, int | None] = {}
    for tid, data in thread_chats.items():
        all_tracked[tid] = data.get("owner_id")
    for tid, data in image_thread_settings.items():
        all_tracked.setdefault(tid, data.get("owner_id"))

    for tid, owner_id in all_tracked.items():
        if owner_id != user_id:
            continue
        thread = guild.get_thread(tid)
        if thread is not None and not thread.archived:
            active.append(thread)

    return active


def can_manage_session(interaction: discord.Interaction, thread_id: int) -> bool:
    """Memeriksa apakah pengguna berhak mereset/mengakhiri sesi di thread ini."""
    owner_id = None
    if thread_id in thread_chats:
        owner_id = thread_chats[thread_id].get("owner_id")
    elif thread_id in image_thread_settings:
        owner_id = image_thread_settings[thread_id].get("owner_id")

    if owner_id is None or interaction.user.id == owner_id:
        return True

    if isinstance(interaction.user, discord.Member):
        perms = interaction.user.guild_permissions
        if perms.administrator or perms.manage_threads:
            return True

    return False


async def close_and_recap_session(interaction: discord.Interaction, channel: discord.Thread) -> None:
    """Menyusun transkrip sesi privat, mengirim rekap ke DM (atau fallback di thread), lalu menghapus thread."""
    if not can_manage_session(interaction, channel.id):
        await interaction.response.send_message(
            "⚠️ Hanya pemilik ruang sesi ini (atau Moderator) yang dapat mengakhiri sesi.",
            ephemeral=True,
        )
        return

    if not mark_thread_closing(channel.id):
        await interaction.response.send_message(
            "⏳ Sesi ini sudah dalam proses penutupan, mohon tunggu sebentar...",
            ephemeral=True,
        )
        return

    try:
        await interaction.response.send_message(
            "🧹 **Menyiapkan rekap obrolan & menutup ruang sesi...**",
            ephemeral=False,
        )

        bot_uid = interaction.client.user.id if interaction.client.user else 0
        embed, transcript_file = await build_session_transcript(channel, interaction.user, bot_uid)
        raw_transcript_bytes: bytes | None = None
        transcript_filename = "rekap-sesi.txt"
        if transcript_file is not None:
            transcript_filename = transcript_file.filename
            raw_transcript_bytes = transcript_file.fp.read()
            transcript_file.fp.seek(0)

        dm_sent = False
        try:
            if transcript_file is not None:
                await interaction.user.send(embed=embed, file=transcript_file)
            else:
                await interaction.user.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            logger.info("DM tertutup untuk user %s saat rekap sesi %s", interaction.user.id, channel.id)
        except Exception as exc:
            logger.warning("Gagal mengirim DM rekap: %s", sanitize_error_message(exc))

        remove_thread_data(channel.id)
        await save_sessions_to_disk()

        if not dm_sent:
            if raw_transcript_bytes is not None:
                fallback_file = discord.File(
                    io.BytesIO(raw_transcript_bytes),
                    filename=transcript_filename,
                )
                await channel.send(
                    content=(
                        f"⚠️ {interaction.user.mention} DM Anda tertutup, berikut file rekap sesi Anda. "
                        "Ruang ini akan dihapus otomatis dalam **10 detik**."
                    ),
                    file=fallback_file,
                )
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(2)
        else:
            await asyncio.sleep(2)

        await channel.delete(reason=f"Sesi AI diakhiri oleh {interaction.user}")

    except discord.NotFound:
        remove_thread_data(channel.id)
        await save_sessions_to_disk()
    except Exception as exc:
        unmark_thread_closing(channel.id)
        logger.error("Gagal menutup thread %s: %s", channel.id, sanitize_error_message(exc))


# ==============================================================================
# TOMBOL KONTROL SESI (RESET MEMORI & AKHIRI SESI + REKAP DM)
# ==============================================================================
class EndSessionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔄 Reset Sesi",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_reset_ai_session_v2",
    )
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread):
            await interaction.response.send_message("⚠️ Tombol ini hanya berlaku di dalam ruang sesi AI.", ephemeral=True)
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
                "🔄 **Memori percakapan telah dibersihkan!** Sekarang Anda bisa memulai topik baru dari nol.",
                ephemeral=False,
            )

    @discord.ui.button(
        label="🔴 Akhiri Sesi",
        style=discord.ButtonStyle.danger,
        custom_id="btn_end_ai_session_v2",
    )
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread):
            await interaction.response.send_message("⚠️ Tombol ini hanya berlaku di dalam ruang sesi AI.", ephemeral=True)
            return
        await close_and_recap_session(interaction, channel)


# ==============================================================================
# DROPDOWN GANTI MODE GEMINI DI DALAM RUANG CHAT (PERSISTEN)
# ==============================================================================
class ChatPersonaSwitchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="🎭 Ganti Mode / Kepribadian Gemini kapan saja...",
        custom_id="select_chat_persona_v2",
        options=[
            discord.SelectOption(
                label=info["short_label"],
                value=key,
                description=info["description"][:100],
                emoji=info["emoji"],
            )
            for key, info in AI_MODELS.items()
        ],
    )
    async def switch_persona(self, interaction: discord.Interaction, select: discord.ui.Select):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread):
            await interaction.response.send_message("⚠️ Menu ini hanya aktif di dalam ruang sesi AI.", ephemeral=True)
            return

        if not can_manage_session(interaction, channel.id):
            await interaction.response.send_message(
                "⚠️ Hanya pemilik ruang sesi ini yang dapat mengganti mode AI.",
                ephemeral=True,
            )
            return

        chosen_key = resolve_model_key(select.values[0])
        model_info = AI_MODELS[chosen_key]
        switch_thread_model(channel.id, chosen_key, owner_id=interaction.user.id)
        await save_sessions_to_disk()

        await interaction.response.send_message(
            f"✅ **Mode AI diubah menjadi:** **{model_info['name']}**\n"
            f"*(Riwayat obrolan sebelumnya tetap tersimpan)*",
            ephemeral=True,
        )


# ==============================================================================
# PENGATURAN GAMBAR (GAYA ART & RASIO UKURAN - PERSISTEN)
# ==============================================================================
class ImageSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="🎨 Pilih Gaya Art Gambar...",
        custom_id="select_image_style",
        options=[
            discord.SelectOption(label=meta["label"], value=style_key, emoji=meta["emoji"])
            for style_key, meta in STYLE_OPTIONS.items()
        ],
    )
    async def select_style(self, interaction: discord.Interaction, select: discord.ui.Select):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread):
            await interaction.response.send_message("⚠️ Menu ini hanya berlaku di ruang gambar AI.", ephemeral=True)
            return

        settings = get_image_settings(channel.id)
        settings["style"] = select.values[0]
        settings["updated_at"] = time.time()
        await save_sessions_to_disk()
        await interaction.response.send_message(
            f"✅ Gaya gambar diatur ke: **{settings['style']}** (Ukuran saat ini: `{settings['ratio']}`)",
            ephemeral=True,
        )

    @discord.ui.select(
        placeholder="📐 Pilih Ukuran Rasio Gambar...",
        custom_id="select_image_ratio",
        options=[
            discord.SelectOption(label=meta["label"], value=ratio_key, emoji=meta["emoji"])
            for ratio_key, meta in RATIO_OPTIONS.items()
        ],
    )
    async def select_ratio(self, interaction: discord.Interaction, select: discord.ui.Select):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread):
            await interaction.response.send_message("⚠️ Menu ini hanya berlaku di ruang gambar AI.", ephemeral=True)
            return

        settings = get_image_settings(channel.id)
        settings["ratio"] = select.values[0]
        settings["updated_at"] = time.time()
        await save_sessions_to_disk()
        await interaction.response.send_message(
            f"✅ Ukuran rasio gambar diatur ke: **{settings['ratio']}** (Gaya saat ini: `{settings['style']}`)",
            ephemeral=True,
        )


# ==============================================================================
# DROPDOWN PEMILIHAN AWAL SAAT MEMBUAT RUANG CHAT TEKS BARU
# ==============================================================================
class AIModelSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=90)

    @discord.ui.select(
        placeholder="🧠 Pilih Mode Google Gemini...",
        options=[
            discord.SelectOption(
                label=info["short_label"],
                value=key,
                description=info["description"][:100],
                emoji=info["emoji"],
            )
            for key, info in AI_MODELS.items()
        ],
    )
    async def select_model(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)

        target_channel, err_msg = _validate_target_channel(interaction)
        if target_channel is None:
            await interaction.followup.send(content=err_msg, ephemeral=True)
            return

        active_threads = _get_user_active_threads(interaction.guild, interaction.user.id)
        if len(active_threads) >= MAX_THREADS_PER_USER:
            mentions = ", ".join(t.mention for t in active_threads)
            await interaction.followup.send(
                content=(
                    f"⚠️ Anda sudah memiliki **{len(active_threads)}** ruang sesi aktif ({mentions}).\n"
                    "Silakan gunakan ruang tersebut atau klik **🔴 Akhiri Sesi** terlebih dahulu."
                ),
                ephemeral=True,
            )
            return

        chosen_key = resolve_model_key(select.values[0])
        model_info = AI_MODELS[chosen_key]
        safe_user = _sanitize_username_for_thread(interaction.user.name)
        thread_name = f"ai-{safe_user}"

        try:
            thread = await target_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=60,
                invitable=False,
                reason=f"Ruang Chat Gemini AI untuk {interaction.user}",
            )
            await thread.add_user(interaction.user)

            init_thread_session(thread.id, chosen_key, owner_id=interaction.user.id)
            await save_sessions_to_disk()

            select.disabled = True
            try:
                await interaction.edit_original_response(
                    content=f"✅ Ruang Chat (**{model_info['name']}**) berhasil dibuat: {thread.mention}",
                    view=self,
                )
            except Exception:
                await interaction.followup.send(
                    content=f"✅ Ruang Chat (**{model_info['name']}**) berhasil dibuat: {thread.mention}",
                    ephemeral=True,
                )

            await thread.send(
                content=(
                    f"👋 **Selamat Datang {interaction.user.mention}!**\n"
                    f"Ruang chat privat Anda siap menggunakan **{model_info['name']}**.\n"
                    f"• Ketik pertanyaan apa saja untuk mulai mengobrol.\n"
                    f"• 🎙️ **Multimodal:** Kirim **Voice Note (🎤)**, dokumen **`.pdf`**, foto/screenshot, file kode, atau link **YouTube/Web** langsung di sini!\n"
                    f"• Gunakan menu di bawah jika ingin berganti mode kepribadian di tengah obrolan:"
                ),
                view=ChatPersonaSwitchView(),
            )
            await thread.send(
                content="🔴 *Gunakan tombol di bawah untuk mereset memori atau mengakhiri sesi:*",
                view=EndSessionView(),
            )

        except Exception as exc:
            await interaction.followup.send(
                content=f"⚠️ Gagal membuat ruang chat: {sanitize_error_message(exc)}",
                ephemeral=True,
            )


# ==============================================================================
# PANEL UTAMA CONTROLLER (PERSISTEN)
# ==============================================================================
class MainPanelControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💬 Chat AI (Teks & Vision)",
        style=discord.ButtonStyle.success,
        custom_id="btn_create_text_ai_v2",
    )
    async def create_text_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        target_channel, err_msg = _validate_target_channel(interaction)
        if target_channel is None:
            await interaction.response.send_message(content=err_msg, ephemeral=True)
            return

        active_threads = _get_user_active_threads(interaction.guild, interaction.user.id)
        if len(active_threads) >= MAX_THREADS_PER_USER:
            mentions = ", ".join(t.mention for t in active_threads)
            await interaction.response.send_message(
                content=(
                    f"⚠️ Anda sudah memiliki **{len(active_threads)}** ruang sesi aktif ({mentions}).\n"
                    "Silakan lanjutkan di ruang tersebut atau akhiri salah satu sesi terlebih dahulu."
                ),
                ephemeral=True,
            )
            return

        select_view = AIModelSelectView()
        await interaction.response.send_message(
            content="🎭 **Pilih Mode Google Gemini yang ingin Anda ajak ngobrol:**",
            view=select_view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="🎨 Generate Gambar AI",
        style=discord.ButtonStyle.primary,
        custom_id="btn_create_image_ai_v2",
    )
    async def create_image_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        target_channel, err_msg = _validate_target_channel(interaction)
        if target_channel is None:
            await interaction.followup.send(content=err_msg, ephemeral=True)
            return

        active_threads = _get_user_active_threads(interaction.guild, interaction.user.id)
        if len(active_threads) >= MAX_THREADS_PER_USER:
            mentions = ", ".join(t.mention for t in active_threads)
            await interaction.followup.send(
                content=(
                    f"⚠️ Anda sudah memiliki **{len(active_threads)}** ruang sesi aktif ({mentions}).\n"
                    "Silakan lanjutkan di ruang tersebut atau akhiri salah satu sesi terlebih dahulu."
                ),
                ephemeral=True,
            )
            return

        safe_user = _sanitize_username_for_thread(interaction.user.name)
        thread_name = f"draw-{safe_user}"

        try:
            thread = await target_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=60,
                invitable=False,
                reason=f"Ruang Gambar Gemini AI untuk {interaction.user}",
            )
            await thread.add_user(interaction.user)

            init_image_session(thread.id, owner_id=interaction.user.id)
            await save_sessions_to_disk()

            await thread.send(
                content=(
                    f"🎨 **Selamat Datang {interaction.user.mention}!**\n"
                    f"Ini adalah ruang privat pembuatan & pengeditan gambar AI.\n"
                    f"• Ketik deskripsi gambar apa saja, dan AI akan langsung membuatkannya.\n"
                    f"• 💡 **Tips:** Anda juga bisa melampirkan gambar beserta instruksi untuk mengeditnya!\n"
                    f"• Pengaturan awal: Gaya `{DEFAULT_IMAGE_SETTINGS['style']}` | Ukuran `{DEFAULT_IMAGE_SETTINGS['ratio']}`.\n\n"
                    f"⚙️ *Gunakan menu dropdown di bawah untuk mengubah Gaya Art atau Ukuran Rasio:*"
                ),
                view=ImageSettingsView(),
            )
            await thread.send(
                content="🔴 *Gunakan tombol di bawah untuk mereset pengaturan atau mengakhiri sesi:*",
                view=EndSessionView(),
            )

            await interaction.followup.send(
                content=f"✅ Ruang Generate Gambar berhasil dibuat: {thread.mention}",
                ephemeral=True,
            )

        except Exception as exc:
            await interaction.followup.send(
                content=f"⚠️ Gagal membuat ruang gambar: {sanitize_error_message(exc)}",
                ephemeral=True,
            )


# ==============================================================================
# TOMBOL PERSISTEN FORUM POST: ✅ TANDAI SELESAI / TERJAWAB (AMAN SINGLETON!)
# ==============================================================================
def _build_solved_disabled_view() -> discord.ui.View:
    """Membuat View statis tombol nonaktif tanpa memutasi instance singleton ForumPostSolvedView."""
    done_view = discord.ui.View(timeout=None)
    done_view.add_item(
        discord.ui.Button(
            label="Diskusi Selesai",
            style=discord.ButtonStyle.success,
            emoji="✅",
            disabled=True,
        )
    )
    return done_view


class VerificationGateView(discord.ui.View):
    """Tombol persisten "Verifikasi Saya" untuk membuka akses channel member baru."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verifikasi Saya",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="community:verify_gate",
    )
    async def verify_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            await interaction.response.send_message(
                "⚠️ Tombol verifikasi hanya berlaku di dalam server.", ephemeral=True
            )
            return
        ok, message = await grant_verification_role(interaction.user, interaction.guild.id)
        await interaction.response.send_message(message, ephemeral=True)
        if ok:
            logger.info("Member %s lolos verifikasi di guild %s", interaction.user.id, interaction.guild.id)


class GiveawayJoinView(discord.ui.View):
    """Tombol persisten 🎉 untuk mengikuti/membatalkan giveaway (tahan restart bot)."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _refresh(self, interaction: discord.Interaction, cfg: dict) -> None:
        """Mengedit pesan giveaway agar jumlah peserta langsung terlihat."""
        try:
            await interaction.message.edit(
                embed=engagement.build_giveaway_embed(cfg, ended=bool(cfg.get("ended"))),
                view=GiveawayJoinView(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @discord.ui.button(label="Ikuti Giveaway", emoji="🎉", style=discord.ButtonStyle.success, custom_id="engagement:giveaway:join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("⚠️ Giveaway hanya berlaku di dalam server.", ephemeral=True)
            return

        role_ids = {
            getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])
        }
        status, cfg = engagement.join_giveaway(
            interaction.message.id, interaction.user.id, role_ids=role_ids
        )
        if status == "tidak_ada":
            await interaction.response.send_message(
                "⚠️ Data giveaway ini tidak ditemukan (mungkin bot baru restart). "
                "Minta Admin membuat giveaway baru.",
                ephemeral=True,
            )
            return
        if status == "ended":
            await interaction.response.send_message("⏹️ Giveaway ini sudah berakhir.", ephemeral=True)
            return
        if status == "duplikat":
            await interaction.response.send_message(
                "✅ Kamu **sudah terdaftar**. Semoga beruntung!", ephemeral=True
            )
            return
        if status == "syarat":
            await interaction.response.send_message(
                f"🔒 Giveaway ini hanya untuk pemilik <@&{cfg.get('role_id')}>.", ephemeral=True
            )
            return

        await engagement.save_engagement_to_disk()
        await self._refresh(interaction, cfg or {})
        await interaction.response.send_message(
            f"🎉 **Berhasil ikut!** Total peserta sekarang `{len(cfg.get('entries') or [])}` orang.",
            ephemeral=True,
        )

    @discord.ui.button(label="Batalkan", style=discord.ButtonStyle.secondary, custom_id="engagement:giveaway:leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("⚠️ Giveaway hanya berlaku di dalam server.", ephemeral=True)
            return

        status, cfg = engagement.leave_giveaway(interaction.message.id, interaction.user.id)
        if status == "tidak_ada":
            await interaction.response.send_message("⚠️ Data giveaway ini tidak ditemukan.", ephemeral=True)
            return
        if status == "ended":
            await interaction.response.send_message("⏹️ Giveaway ini sudah berakhir.", ephemeral=True)
            return
        if status == "tidak_terdaftar":
            await interaction.response.send_message(
                "ℹ️ Kamu memang belum terdaftar di giveaway ini.", ephemeral=True
            )
            return

        await engagement.save_engagement_to_disk()
        await self._refresh(interaction, cfg or {})
        await interaction.response.send_message(
            "👋 Pesertaan dibatalkan. Kamu bisa ikut lagi kapan saja sebelum waktu habis.",
            ephemeral=True,
        )


class QueuePaginationView(discord.ui.View):
    """Tombol ◀ ▶ untuk berpindah halaman antrean musik (berlaku 120 detik)."""

    def __init__(self, tracks: list, *, requester_id: int, page: int = 0, now_playing=None):
        super().__init__(timeout=120)
        self.tracks = tracks
        self.requester_id = requester_id
        self.page = page
        self.now_playing = now_playing
        self.total_length = sum(int(getattr(t, "length", 0) or 0) for t in tracks)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        _, page, total_pages = music.build_queue_page_embed(
            self.tracks,
            page=self.page,
            total_length=self.total_length,
            now_playing=self.now_playing,
        )
        self.page = page
        self.prev_btn.disabled = page <= 0
        self.next_btn.disabled = page >= total_pages - 1
        self.page_label.label = f"Halaman {page + 1}/{total_pages}"

    def _embed(self) -> discord.Embed:
        embed, page, _ = music.build_queue_page_embed(
            self.tracks,
            page=self.page,
            total_length=self.total_length,
            now_playing=self.now_playing,
        )
        self.page = page
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "💡 Jalankan `/musik antrean` sendiri untuk membuka daftar antreanmu.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="music:queue:prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Halaman 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="music:queue:page")
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="music:queue:next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self._embed(), view=self)


class MusicPlayerView(discord.ui.View):
    """Panel kontrol pemutar musik persisten ala Rythm (tombol selalu aktif walau bot restart)."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _player_or_warn(self, interaction: discord.Interaction):
        """Mengambil player aktif + memeriksa hak kontrol member."""
        player = music.get_player(interaction.guild)
        if player is None or getattr(player, "channel", None) is None:
            await interaction.response.send_message(
                "⚠️ Tidak ada musik yang sedang diputar. Mulai dengan `/musik putar`.", ephemeral=True
            )
            return None
        if not music.can_control(player, interaction.user):
            await interaction.response.send_message(
                "⚠️ Kamu harus berada di **voice channel yang sama** dengan bot "
                "(atau punya role DJ / izin Admin) untuk memakai tombol ini.",
                ephemeral=True,
            )
            return None
        return player

    async def _refresh(self, interaction: discord.Interaction) -> None:
        await music.send_or_update_panel(
            interaction.client,
            interaction.guild_id,
            view=MusicPlayerView(),
        )

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music:panel:pause")
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        await player.pause(not bool(getattr(player, "paused", False)))
        await self._refresh(interaction)
        await interaction.response.send_message(
            "⏸️ Musik dijeda." if player.paused else "▶️ Musik dilanjutkan.", ephemeral=True
        )

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music:panel:skip")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        if getattr(player, "current", None) is None and len(getattr(player, "queue", [])) == 0:
            await interaction.response.send_message("⚠️ Tidak ada lagu untuk dilewati.", ephemeral=True)
            return
        await player.skip(force=True)
        await self._refresh(interaction)
        await interaction.response.send_message("⏭️ Lagu dilewati.", ephemeral=True)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="music:panel:previous")
    async def previous_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        ok = await music.skip_previous(player)
        if not ok:
            await interaction.response.send_message(
                "⚠️ Belum ada riwayat lagu sebelumnya.", ephemeral=True
            )
            return
        await self._refresh(interaction)
        await interaction.response.send_message("⏮️ Kembali ke lagu sebelumnya.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music:panel:stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        try:
            player.queue.clear()
            await player.stop()
            await player.disconnect()
        except Exception:  # pragma: no cover - node mati
            pass
        await music.close_panel(interaction.client, interaction.guild_id)
        music.forget_announce_channel(interaction.guild_id)
        await interaction.response.send_message(
            "⏹️ Musik dihentikan & bot keluar dari voice channel.", ephemeral=True
        )

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="music:panel:queue")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music.get_player(interaction.guild)
        if player is None:
            await interaction.response.send_message("⚠️ Tidak ada musik yang diputar.", ephemeral=True)
            return
        tracks = list(player.queue)
        view = QueuePaginationView(
            tracks,
            requester_id=interaction.user.id,
            now_playing=getattr(player, "current", None),
        )
        await interaction.response.send_message(embed=view._embed(), view=view, ephemeral=True)

    @discord.ui.button(emoji="🔁", label="Loop", style=discord.ButtonStyle.secondary, custom_id="music:panel:loop")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        current_mode = getattr(getattr(player, "queue", None), "mode", None)
        next_key = {"normal": "satu", "loop": "semua", "loop_all": "mati"}.get(
            getattr(current_mode, "name", "normal"), "satu"
        )
        player.queue.mode = music.queue_mode_from_key(next_key)
        await self._refresh(interaction)
        await interaction.response.send_message(
            f"🔁 Mode pengulangan: **{music.LOOP_MODES[next_key]}**", ephemeral=True
        )

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="music:panel:shuffle")
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        if len(player.queue) < 2:
            await interaction.response.send_message(
                "⚠️ Antrean kurang dari 2 lagu, tidak ada yang bisa diacak.", ephemeral=True
            )
            return
        player.queue.shuffle()
        await self._refresh(interaction)
        await interaction.response.send_message("🔀 Antrean diacak.", ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="music:panel:vol_down")
    async def volume_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        new_volume = max(1, int(getattr(player, "volume", 60)) - 10)
        await player.set_volume(new_volume)
        music.set_music_settings(interaction.guild_id, volume=new_volume)
        await self._refresh(interaction)
        await interaction.response.send_message(f"🔉 Volume: **{new_volume}%**", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="music:panel:vol_up")
    async def volume_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        new_volume = min(150, int(getattr(player, "volume", 60)) + 10)
        await player.set_volume(new_volume)
        music.set_music_settings(interaction.guild_id, volume=new_volume)
        await self._refresh(interaction)
        await interaction.response.send_message(f"🔊 Volume: **{new_volume}%**", ephemeral=True)


class ForumPostSolvedView(discord.ui.View):
    """Tombol persisten pada Postingan Forum agar penanya/Moderator bisa menandai diskusi selesai."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Tandai Selesai",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="gemini_panel:forum_solved",
    )
    async def mark_solved_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread) and getattr(channel, "parent_id", None) is None:
            await interaction.response.send_message(
                "⚠️ Tombol ini hanya berfungsi di dalam Postingan Forum / Thread.",
                ephemeral=True,
            )
            return

        is_owner = getattr(channel, "owner_id", None) == interaction.user.id
        is_mod = isinstance(interaction.user, discord.Member) and (
            interaction.user.guild_permissions.administrator
            or interaction.user.guild_permissions.manage_threads
            or interaction.user.guild_permissions.manage_messages
        )
        if not is_owner and not is_mod:
            await interaction.response.send_message(
                "⚠️ Hanya **pembuat postingan ini** atau **Moderator** yang dapat menandai diskusi sebagai selesai.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            if interaction.message:
                await interaction.message.edit(view=_build_solved_disabled_view())
        except discord.HTTPException:
            pass

        cur_name = (channel.name or "").strip()
        new_name = cur_name if cur_name.startswith("✅") else f"✅ {cur_name}"[:100]

        parent = getattr(channel, "parent", None)
        avail_tags = getattr(parent, "available_tags", None) or []
        solved_tag = find_solved_forum_tag(avail_tags)
        current_tags = list(getattr(channel, "applied_tags", None) or [])
        if solved_tag is not None and solved_tag not in current_tags:
            current_tags = ([solved_tag] + current_tags)[:5]

        await interaction.followup.send(
            f"✅ Postingan ini telah ditandai **Selesai / Terjawab** oleh {interaction.user.mention}! "
            "Terima kasih sudah berdiskusi 🙌"
        )

        edit_kwargs: dict = {"archived": True}
        if new_name and new_name != cur_name:
            edit_kwargs["name"] = new_name
        if solved_tag is not None:
            edit_kwargs["applied_tags"] = current_tags

        try:
            await channel.edit(**edit_kwargs)
        except discord.HTTPException:
            try:
                if new_name != cur_name:
                    await channel.edit(name=new_name)
            except discord.HTTPException:
                pass


# ==============================================================================
# DASHBOARD STATUS TERPADU & PANEL KONTROL ADMIN INTERAKTIF (/agent status & /agent panel)
# ==============================================================================
def _build_channel_spotlight_summary(guild: discord.Guild, cid: int) -> str:
    """Merangkum status ON/OFF seluruh fitur pada 1 channel target yang sedang dipilih di panel."""
    ch_obj = guild.get_channel(cid)
    is_forum = isinstance(ch_obj, discord.ForumChannel)
    ch_type_lbl = "Forum / Media" if is_forum else "Text Channel"

    chat_on = bool(chat_agent_channels.get(cid, {}).get("enabled"))
    gal_on = bool(gallery_agent_channels.get(cid, {}).get("enabled"))
    yt_on = bool(youtube_agent_channels.get(cid, {}).get("enabled"))
    srch_on = bool(search_agent_channels.get(cid, {}).get("enabled"))

    w_cfg = welcome_agent_guilds.get(guild.id) or {}
    wel_on = bool(w_cfg.get("enabled") and int(w_cfg.get("channel_id") or 0) == cid)
    d_cfg = digest_agent_guilds.get(guild.id) or {}
    dig_on = bool(d_cfg.get("enabled") and int(d_cfg.get("channel_id") or 0) == cid)
    gb_cfg = goodbye_agent_guilds.get(guild.id) or {}
    gb_on = bool(gb_cfg.get("enabled") and int(gb_cfg.get("channel_id") or 0) == cid)
    f_cfg = facts_guilds.get(guild.id) or {}
    fak_on = bool(f_cfg.get("enabled") and int(f_cfg.get("channel_id") or 0) == cid)
    sec_cfg = security_guilds.get(guild.id) or {}
    sec_on = bool(
        sec_cfg.get("enabled")
        and (not sec_cfg.get("channel_ids") or cid in sec_cfg.get("channel_ids"))
    )

    b = lambda flag: "🟢 ON" if flag else "⚪ OFF"
    line1 = f"<#{cid}> *({ch_type_lbl})*\n"
    line2 = f"💬 Chat: `{b(chat_on)}` • 🎨 Galeri: `{b(gal_on)}` • ▶️ YouTube: `{b(yt_on)}` • 🌐 Cari: `{b(srch_on)}`"
    if is_forum:
        return line1 + line2 + f"\n🛡️ Anti-Phishing: `{b(sec_on)}`"
    line3 = (
        f"\n👋 Welcome: `{b(wel_on)}` • 👣 Goodbye: `{b(gb_on)}` • ☀️ Digest: `{b(dig_on)}`"
        f"\n🌍 Fakta Harian: `{b(fak_on)}` • 🛡️ Anti-Phishing: `{b(sec_on)}`"
    )
    return line1 + line2 + line3


def build_agent_status_embed(
    guild: discord.Guild,
    *,
    selected_channel_id: int | None = None,
    notice_banner: str | None = None,
) -> discord.Embed:
    """Embed ringkasan status terpadu untuk `/agent status` sekaligus `/agent panel`."""
    guild_id = guild.id
    cfg = get_guild_settings(guild_id)
    t_ctx = get_realtime_time_context(cfg.get("timezone", BOT_TIMEZONE))
    faq_entries = get_server_knowledge_entries(guild_id)
    now_ts = time.time()

    guild_chats = [
        (cid, cdata)
        for cid, cdata in chat_agent_channels.items()
        if cdata.get("guild_id") == guild_id and cdata.get("enabled")
    ]
    guild_galleries = [
        (cid, gdata)
        for cid, gdata in gallery_agent_channels.items()
        if gdata.get("guild_id") == guild_id and gdata.get("enabled")
    ]
    guild_yt = get_guild_youtube_channels(guild_id)
    guild_search = get_guild_search_channels(guild_id)

    chat_lines: list[str] = []
    for cid, cdata in guild_chats:
        ch_obj = guild.get_channel(cid)
        is_forum_ch = isinstance(ch_obj, discord.ForumChannel)
        idle_s = int(
            cdata.get("idle_seconds")
            if cdata.get("idle_seconds") is not None
            else int(cdata.get("idle_minutes") or 0) * 60
        )
        if is_forum_ch:
            idle_info = "`Mode Forum (Aktif di Postingan)`"
        elif idle_s <= 0:
            idle_info = "Pemecah Sepi: `Mati`"
        elif int(cdata.get("consecutive_idle_pokes") or 0) >= AGENT_MAX_IDLE_POKES:
            idle_info = f"`{format_idle_duration(idle_s)}` *(menunggu balasan warga)*"
        else:
            rem_sec = max(0, int(idle_s - (now_ts - float(cdata.get("last_activity_at") or now_ts))))
            rem_lbl = f"{rem_sec} dtk" if rem_sec < 60 else f"{rem_sec // 60} mnt {rem_sec % 60} dtk"
            idle_info = f"`{format_idle_duration(idle_s)}` *(sapa dlm ~{rem_lbl})*"
        chat_lines.append(f"• <#{cid}> — Mode `{cdata.get('reply_mode')}` | {idle_info}")

    gal_lines = [
        f"• <#{cid}> — Auto-Reaction: `{'ON' if gdata.get('auto_reaction', True) else 'OFF'}`"
        for cid, gdata in guild_galleries
    ]

    if not ENABLE_URL_READER:
        yt_text = "⛔ **Nonaktif Global di `.env`** (`ENABLE_URL_READER=false`)"
    elif guild_yt:
        yt_lines = [
            f"• <#{cid}> — Mode: `{'Otomatis Semua Link' if ydata.get('auto_in_chat') else 'Saat Dipanggil & /ringkas link'}`"
            for cid, ydata in guild_yt
        ]
        yt_text = "\n".join(yt_lines)
    else:
        yt_text = "_Belum ada channel (aktifkan via panel atau `/agent youtube`)_"

    if not ENABLE_GOOGLE_SEARCH:
        search_text = "⛔ **Nonaktif Global di `.env`** (`ENABLE_GOOGLE_SEARCH=false`)"
    elif guild_search:
        s_lines = [
            f"• <#{cid}> — `/cari`: `ON` | Auto di Chat: `{'ON' if sdata.get('auto_in_chat', True) else 'OFF'}`"
            for cid, sdata in guild_search
        ]
        search_text = "\n".join(s_lines)
    else:
        search_text = "_Belum ada channel (aktifkan via panel atau `/agent cari`)_"

    w_cfg = welcome_agent_guilds.get(guild_id)
    if w_cfg and w_cfg.get("enabled"):
        w_note = f" *(Info: {w_cfg['extra_note']})*" if w_cfg.get("extra_note") else ""
        persona_lbl = GREETING_PERSONAS.get(str(w_cfg.get("persona") or "hangat"), {}).get("label", "Hangat & Tulus")
        welcome_text = f"✅ Aktif di <#{w_cfg['channel_id']}> — Persona: `{persona_lbl}`{w_note}"
    else:
        welcome_text = "_Belum aktif_"

    gb_cfg = goodbye_agent_guilds.get(guild_id)
    if gb_cfg and gb_cfg.get("enabled"):
        gb_persona = GREETING_PERSONAS.get(str(gb_cfg.get("persona") or "hangat"), {}).get("label", "Hangat & Tulus")
        goodbye_text = f"✅ Aktif di <#{gb_cfg['channel_id']}> — Persona: `{gb_persona}`"
    else:
        goodbye_text = "_Belum aktif_"

    f_cfg = facts_guilds.get(guild_id)
    if f_cfg and f_cfg.get("enabled"):
        f_times = list(f_cfg.get("times") or [])
        facts_text = (
            f"✅ Aktif di <#{f_cfg['channel_id']}> — "
            f"{format_facts_schedule(f_times)} {t_ctx['tz_label']} *({len(f_times)}x sehari)*"
        )
    else:
        facts_text = "_Belum aktif_"

    sec_cfg = security_guilds.get(guild_id)
    if sec_cfg and sec_cfg.get("enabled"):
        sec_scope = (
            f"<#{sec_cfg['channel_ids'][0]}>" if sec_cfg.get("channel_ids") else "Seluruh Server"
        )
        security_text = (
            f"✅ Aktif ({sec_scope}) — Aksi: `{sec_cfg.get('action')}` | "
            f"Diblokir: `{sec_cfg.get('blocked', 0)}`"
        )
    else:
        security_text = "_Belum aktif_"

    d_cfg = digest_agent_guilds.get(guild_id)
    if d_cfg and d_cfg.get("enabled"):
        digest_text = (
            f"✅ Aktif di <#{d_cfg['channel_id']}> pukul **`{d_cfg['hour']:02d}:{d_cfg['minute']:02d} {t_ctx['tz_label']}`** "
            f"*(Topik: {d_cfg.get('topic')})*"
        )
    else:
        digest_text = "_Belum aktif_"

    desc_parts: list[str] = []
    if notice_banner:
        desc_parts.append(notice_banner)
    desc_parts.append(f"🕒 **Waktu Lokal Server:** `{t_ctx['summary']}`")

    bot_disp = guild.me.display_name if guild.me else "Bot"
    embed = discord.Embed(
        title=f"🤖 Dashboard AI Community Agent (`v{BOT_VERSION}`)",
        description="\n".join(desc_parts),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )

    if selected_channel_id is not None:
        embed.add_field(
            name="📍 Channel Target Terpilih di Panel",
            value=_build_channel_spotlight_summary(guild, selected_channel_id),
            inline=False,
        )

    embed.add_field(
        name="🎭 Persona & Memori FAQ Server",
        value=(
            f"• **Panggilan:** `{cfg.get('nickname') or bot_disp}` | **Gaya:** `{cfg.get('style_preset')}` | "
            f"**Jam Tenang (23-06):** `{'Aktif' if cfg.get('quiet_hours', True) else 'Nonaktif'}`\n"
            f"• **Konteks Server:** {cfg.get('custom_prompt') or '_(Default)_'}\n"
            f"• **Memori Info / FAQ Server (`/agent info`):** `{len(faq_entries)}/25 entri tersimpan`"
        ),
        inline=False,
    )
    embed.add_field(
        name="💬 Channel & Forum Auto-Chat",
        value="\n".join(chat_lines) if chat_lines else "_Belum ada channel aktif_",
        inline=False,
    )
    embed.add_field(
        name="🎨 Channel & Forum Galeri Karya",
        value="\n".join(gal_lines) if gal_lines else "_Belum ada channel aktif_",
        inline=False,
    )
    embed.add_field(
        name="▶️ Perangkum YouTube & Link Web",
        value=yt_text,
        inline=False,
    )
    embed.add_field(
        name="🌐 Pencarian Berita & Web Terkini",
        value=search_text,
        inline=False,
    )
    embed.add_field(
        name="👋 Sambutan Member & ☀️ Koran Pagi",
        value=(
            f"• **Welcome:** {welcome_text}\n"
            f"• **Goodbye:** {goodbye_text}\n"
            f"• **Morning Digest:** {digest_text}"
        ),
        inline=False,
    )
    embed.add_field(
        name="🌍 Fakta Harian & 🛡️ Anti-Phishing",
        value=f"• **Fakta Unik Dunia:** {facts_text}\n• **Anti-Phishing:** {security_text}",
        inline=False,
    )
    return embed


class EditPersonaModal(discord.ui.Modal, title="🎭 Ubah Kepribadian AI Server"):
    nickname_input = discord.ui.TextInput(
        label="Nama Panggilan Bot (ketik - untuk reset)",
        placeholder="Contoh: Bimo / Neko / Asisten",
        required=False,
        max_length=32,
    )
    style_input = discord.ui.TextInput(
        label="Gaya Bahasa (akrab / gaul / ramah)",
        placeholder="Ketik: akrab, gaul, atau ramah",
        default="akrab",
        required=True,
        max_length=12,
    )
    tz_input = discord.ui.TextInput(
        label="Zona Waktu (WIB / WITA / WIT)",
        placeholder="WIB, WITA, atau WIT",
        default="WIB",
        required=False,
        max_length=24,
    )
    prompt_input = discord.ui.TextInput(
        label="Konteks Komunitas (ketik - untuk reset)",
        style=discord.TextStyle.paragraph,
        placeholder="Contoh: Ini server komunitas developer indie & mabar Valorant Indonesia.",
        required=False,
        max_length=300,
    )

    def __init__(self, guild_id: int, selected_channel_id: int | None = None):
        super().__init__()
        self._selected_channel_id = selected_channel_id
        cfg = get_guild_settings(guild_id)
        self.nickname_input.default = cfg.get("nickname") or ""
        self.style_input.default = cfg.get("style_preset") or "akrab"
        cur_tz = cfg.get("timezone") or BOT_TIMEZONE
        tz_short = {"Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT"}.get(cur_tz, cur_tz)
        self.tz_input.default = tz_short
        self.prompt_input.default = cfg.get("custom_prompt") or ""

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        cfg = get_guild_settings(interaction.guild.id)
        raw_nick = self.nickname_input.value.strip()
        cfg["nickname"] = "" if raw_nick == "-" else raw_nick[:32]

        raw_style = self.style_input.value.strip().lower()
        if raw_style in STYLE_DESCRIPTIONS:
            cfg["style_preset"] = raw_style

        raw_tz = self.tz_input.value.strip().lower()
        if raw_tz in _TIMEZONE_ALIASES:
            cfg["timezone"] = _TIMEZONE_ALIASES[raw_tz]

        raw_prompt = self.prompt_input.value.strip()
        cfg["custom_prompt"] = "" if raw_prompt == "-" else raw_prompt[:300]

        await save_agent_config_to_disk()
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self._selected_channel_id,
                notice_banner="✅ **Persona & zona waktu AI Server berhasil diperbarui!**",
            )
        )


class AddServerInfoModal(discord.ui.Modal, title="📌 Tambah Memori Info / FAQ Server"):
    topic_input = discord.ui.TextInput(
        label="Topik / Kata Kunci FAQ",
        placeholder="Contoh: IP Server Minecraft / Rules / Jadwal Mabar",
        required=True,
        max_length=80,
    )
    content_input = discord.ui.TextInput(
        label="Isi Informasi Resmi Server",
        style=discord.TextStyle.paragraph,
        placeholder="Contoh: IP Minecraft play.contoh.id versi 1.21.4, buka 24 jam tanpa whitelist.",
        required=True,
        max_length=500,
    )

    def __init__(self, selected_channel_id: int | None = None):
        super().__init__()
        self._selected_channel_id = selected_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        item, status = upsert_server_knowledge(
            interaction.guild.id,
            self.topic_input.value,
            self.content_input.value,
        )
        if status == "full" or item is None:
            await interaction.response.send_message(
                "⚠️ Kapasitas FAQ Server sudah penuh (maksimal 25 entri). Klik **📋 Kelola FAQ** untuk menghapus entri lama.",
                ephemeral=True,
            )
            return
        await save_agent_config_to_disk()
        verb = "diperbarui" if status == "updated" else "ditambahkan"
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self._selected_channel_id,
                notice_banner=f"✅ **Info FAQ `{item['topic']}` berhasil {verb}!**",
            )
        )


def build_faq_list_embed(guild: discord.Guild, notice: str | None = None) -> discord.Embed:
    """Membuat tampilan daftar entri FAQ server yang rapi."""
    entries = get_server_knowledge_entries(guild.id)
    if not entries:
        desc = (
            "📭 **Memori Info & FAQ Server masih kosong.**\n\n"
            "Tambahkan info seperti *rules server, IP game, jadwal mabar,* atau *link penting* lewat tombol "
            "**➕ Tambah FAQ** di panel atau `/agent info aksi:Tambah`!"
        )
    else:
        lines = [
            f"**{idx}. `{item['topic']}`**\n> {item['content']}"
            for idx, item in enumerate(entries, start=1)
        ]
        desc = "\n\n".join(lines)[:3900]
    if notice:
        desc = f"{notice}\n\n{desc}"[:4050]

    embed = discord.Embed(
        title=f"📌 Memori Info & FAQ Resmi — {guild.name}",
        description=desc,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Total {len(entries)}/25 entri • Dipahami otomatis oleh AI di seluruh channel & sesi")
    return embed


class ServerFaqManagerView(discord.ui.View):
    """Panel mini interaktif untuk melihat & menghapus entri FAQ Server dengan 1 klik."""

    def __init__(self, admin_user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.admin_user_id = admin_user_id
        entries = get_server_knowledge_entries(guild_id)
        if entries:
            opts = [
                discord.SelectOption(
                    label=f"{idx}. {item['topic']}"[:100],
                    value=str(idx),
                    description=item["content"][:95],
                    emoji="🗑️",
                )
                for idx, item in enumerate(entries[:25], start=1)
            ]
            del_select = discord.ui.Select(
                placeholder="🗑️ Pilih entri FAQ yang ingin dihapus...",
                options=opts,
                row=0,
            )
            del_select.callback = self._delete_selected_callback
            self.add_item(del_select)

            clear_btn = discord.ui.Button(
                label="Hapus Semua FAQ",
                style=discord.ButtonStyle.danger,
                emoji="🧹",
                row=1,
            )
            clear_btn.callback = self._clear_all_callback
            self.add_item(clear_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message(
                "⚠️ Hanya Admin pembuka panel yang dapat mengelola FAQ ini.",
                ephemeral=True,
            )
            return False
        return True

    async def _delete_selected_callback(self, interaction: discord.Interaction):
        if interaction.guild is None or not interaction.data:
            return
        values = interaction.data.get("values") or []
        if not values:
            return
        removed = delete_server_knowledge(interaction.guild.id, values[0])
        await save_agent_config_to_disk()
        note = f"🗑️ Entri **`{removed['topic']}`** berhasil dihapus." if removed else "⚠️ Entri sudah tidak ada."
        fresh_view = ServerFaqManagerView(self.admin_user_id, interaction.guild.id)
        await interaction.response.edit_message(
            embed=build_faq_list_embed(interaction.guild, notice=note),
            view=fresh_view,
        )

    async def _clear_all_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        cnt = clear_server_knowledge(interaction.guild.id)
        await save_agent_config_to_disk()
        fresh_view = ServerFaqManagerView(self.admin_user_id, interaction.guild.id)
        await interaction.response.edit_message(
            embed=build_faq_list_embed(
                interaction.guild,
                notice=f"🧹 Seluruh memori FAQ (**{cnt} entri**) berhasil dibersihkan.",
            ),
            view=fresh_view,
        )


class AgentAdminPanelView(discord.ui.View):
    """Panel Kontrol Admin Interaktif (/agent panel) dengan Spotlight Channel, Toggle Mulus, & Pengelola FAQ."""

    def __init__(self, admin_user_id: int, default_channel_id: int | None = None):
        super().__init__(timeout=600)
        self.admin_user_id = admin_user_id
        self.selected_channel_id: int | None = default_channel_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message(
                "⚠️ Panel kontrol ini hanya dapat dioperasikan oleh Admin yang membukanya.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[
            discord.ChannelType.text,
            discord.ChannelType.news,
            discord.ChannelType.forum,
            discord.ChannelType.media,
        ],
        placeholder="1️⃣ Pilih Channel / Forum target yang ingin diatur...",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def pick_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.guild is None:
            return
        picked = select.values[0]
        self.selected_channel_id = picked.id
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=picked.id,
                notice_banner=f"📍 Channel target diubah ke <#{picked.id}>. Pilih menu **2️⃣** untuk ON/OFF fitur!",
            ),
            view=self,
        )

    @discord.ui.select(
        placeholder="2️⃣ Toggle ON / OFF fitur pada channel terpilih...",
        options=[
            discord.SelectOption(
                label="Toggle Auto-Chat Pintar (ON / OFF)",
                value="toggle_chat",
                emoji="💬",
                description="Aktifkan/matikan ngobrol otomatis & jawab Forum di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Komentator Galeri (ON / OFF)",
                value="toggle_gallery",
                emoji="🎨",
                description="Aktifkan/matikan apresiasi foto, video, & stiker di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Rangkum YouTube & Link (ON / OFF)",
                value="toggle_youtube",
                emoji="▶️",
                description="Aktifkan/matikan pembaca link YouTube & web di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Pencarian Berita /cari (ON / OFF)",
                value="toggle_search",
                emoji="🌐",
                description="Aktifkan/matikan fitur /cari & berita terkini di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Sambutan Member Baru (ON / OFF)",
                value="toggle_welcome",
                emoji="👋",
                description="Jadikan channel teks ini tempat menyapa member baru otomatis",
            ),
            discord.SelectOption(
                label="Toggle Koran Pagi 07:00 (ON / OFF)",
                value="toggle_digest",
                emoji="☀️",
                description="Kirim sapaan & rangkuman berita pagi harian pukul 07:00 di sini",
            ),
            discord.SelectOption(
                label="Toggle Pesan Perpisahan / Goodbye (ON / OFF)",
                value="toggle_goodbye",
                emoji="👣",
                description="Kirim kartu perpisahan AI saat member keluar dari server",
            ),
            discord.SelectOption(
                label="Toggle Fakta Unik Dunia (ON / OFF)",
                value="toggle_facts",
                emoji="🌍",
                description="Kirim 3–4 fakta unik dari berbagai negara sesuai jadwal multi-slot",
            ),
        ],
        row=1,
    )
    async def toggle_feature(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.guild is None:
            return
        cid = self.selected_channel_id
        if cid is None:
            await interaction.response.send_message(
                "⚠️ Pilih channel terlebih dahulu pada menu **1️⃣** di atas!",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        target_ch = interaction.guild.get_channel(cid)
        is_forum_like = isinstance(target_ch, discord.ForumChannel)
        action = select.values[0]
        banner = ""

        if action == "toggle_chat":
            new_state = not bool(chat_agent_channels.get(cid, {}).get("enabled"))
            set_chat_channel_config(
                guild_id,
                cid,
                enabled=new_state,
                reply_mode="smart",
                idle_minutes=0 if is_forum_like else AGENT_DEFAULT_IDLE_MINUTES,
            )
            banner = f"💬 **Auto-Chat** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
        elif action == "toggle_gallery":
            new_state = not bool(gallery_agent_channels.get(cid, {}).get("enabled"))
            set_gallery_channel_config(guild_id, cid, enabled=new_state, auto_reaction=True)
            banner = f"🎨 **Komentator Galeri** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
        elif action == "toggle_youtube":
            new_state = not bool(youtube_agent_channels.get(cid, {}).get("enabled"))
            set_youtube_channel_config(guild_id, cid, enabled=new_state, auto_in_chat=False)
            banner = f"▶️ **Rangkum YouTube & Link** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
        elif action == "toggle_search":
            new_state = not bool(search_agent_channels.get(cid, {}).get("enabled"))
            set_search_channel_config(guild_id, cid, enabled=new_state, auto_in_chat=True)
            banner = f"🌐 **Pencarian Berita (`/cari`)** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
        elif action == "toggle_welcome":
            if is_forum_like:
                await interaction.response.send_message(
                    "⚠️ Sambutan Member Baru hanya dapat dipasang pada **Text Channel** biasa (bukan Forum).",
                    ephemeral=True,
                )
                return
            w_cur = welcome_agent_guilds.get(guild_id)
            turn_on = not (w_cur and w_cur.get("enabled") and w_cur.get("channel_id") == cid)
            set_welcome_config(guild_id, cid, enabled=turn_on)
            banner = f"👋 **Auto-Welcomer** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
        elif action == "toggle_digest":
            if is_forum_like:
                await interaction.response.send_message(
                    "⚠️ Koran Pagi (Morning Digest) hanya dapat dikirim ke **Text Channel** biasa (bukan Forum).",
                    ephemeral=True,
                )
                return
            d_cur = digest_agent_guilds.get(guild_id)
            turn_on = not (d_cur and d_cur.get("enabled") and d_cur.get("channel_id") == cid)
            set_digest_config(guild_id, cid, enabled=turn_on, hour=7, minute=0)
            banner = f"☀️ **Koran Pagi 07:00** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
        elif action == "toggle_goodbye":
            if is_forum_like:
                await interaction.response.send_message(
                    "⚠️ Pesan Perpisahan (Goodbye) hanya dapat dipasang pada **Text Channel** biasa (bukan Forum).",
                    ephemeral=True,
                )
                return
            gb_cur = goodbye_agent_guilds.get(guild_id)
            turn_on = not (gb_cur and gb_cur.get("enabled") and gb_cur.get("channel_id") == cid)
            set_goodbye_config(guild_id, cid, enabled=turn_on)
            banner = f"👣 **Pesan Perpisahan (Goodbye)** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
        elif action == "toggle_facts":
            if is_forum_like:
                await interaction.response.send_message(
                    "⚠️ Fakta Unik Dunia hanya dapat dikirim ke **Text Channel** biasa (bukan Forum).",
                    ephemeral=True,
                )
                return
            f_cur = facts_guilds.get(guild_id)
            turn_on = not (f_cur and f_cur.get("enabled") and f_cur.get("channel_id") == cid)
            f_cfg_new = set_facts_config(guild_id, cid, enabled=turn_on)
            f_slots = format_facts_schedule((f_cfg_new or {}).get("times"))
            banner = (
                f"🌍 **Fakta Unik Dunia** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
                + (f"\n⏰ Jadwal aktif: {f_slots} *(ubah lewat `/fakta atur`)*" if turn_on else "")
            )

        await save_agent_config_to_disk()
        await save_server_features_to_disk()
        # Buat instance View segar dengan selected_channel_id yang sama agar dropdown reset & bisa diklik ulang langsung
        fresh_view = AgentAdminPanelView(self.admin_user_id, default_channel_id=cid)
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=cid,
                notice_banner=banner,
            ),
            view=fresh_view,
        )

    @discord.ui.button(label="Persona", style=discord.ButtonStyle.primary, emoji="🎭", row=2)
    async def edit_persona_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.send_modal(
            EditPersonaModal(interaction.guild.id, selected_channel_id=self.selected_channel_id)
        )

    @discord.ui.button(label="Tambah FAQ", style=discord.ButtonStyle.success, emoji="➕", row=2)
    async def add_faq_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AddServerInfoModal(selected_channel_id=self.selected_channel_id)
        )

    @discord.ui.button(label="Kelola FAQ", style=discord.ButtonStyle.secondary, emoji="📋", row=2)
    async def manage_faq_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.send_message(
            embed=build_faq_list_embed(interaction.guild),
            view=ServerFaqManagerView(interaction.user.id, interaction.guild.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Segarkan", style=discord.ButtonStyle.secondary, emoji="🔄", row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self.selected_channel_id,
            ),
            view=self,
        )


# ==============================================================================
# PUSAT PANDUAN INTERAKTIF BERKATEGORI (/bantuan)
# ==============================================================================
def build_help_embed(category: str = "overview") -> discord.Embed:
    """Menyusun Embed panduan `/bantuan` yang rapi & terstruktur sesuai kategori pilihan."""
    if category == "sesi":
        embed = discord.Embed(
            title="🔒 Ruang AI Privat, Multimodal & Gambar (`/sesi`)",
            description=(
                "Buka ruang konsultasi pribadi (`Private Thread`) yang rapi tanpa mengganggu chat umum:"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="💬 Ruang Chat Teks & Multimodal (`ai-...`)",
            value=(
                "• Klik tombol **💬 Chat AI** pada panel (dipasang Admin via `/sesi panel`).\n"
                "• Pilih **5 Mode Kepribadian:** *Asisten Utama, Respon Kilat, Pakar Koding, Penalaran & Riset,* atau *Teman Curhat*.\n"
                "• Kirim **Voice Note (`🎤`)**, dokumen **`.pdf`**, foto/screenshot error, file kode (`.py`, `.js`, dll), stiker, hingga link **YouTube & artikel web**!"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎨 Studio Generate & Edit Gambar (`draw-...`)",
            value=(
                "• Klik tombol **🎨 Generate Gambar AI** pada panel utama.\n"
                "• Pilih **7 Gaya Art** *(Anime, Cyberpunk, Realistis, 3D, Pixel Art, Lukisan)* & **5 Ukuran Rasio**.\n"
                "• Lampirkan foto + instruksi teks untuk mengedit gambar secara instan."
            ),
            inline=False,
        )
        embed.add_field(
            name="⌨️ Daftar Command `/sesi`",
            value=(
                "• `/sesi panel` *(Admin)* — Pasang panel tombol ruang AI di channel.\n"
                "• `/sesi model` — Ganti kepribadian Gemini di ruang chat aktif.\n"
                "• `/sesi reset` — Bersihkan riwayat memori / reset setelan gambar.\n"
                "• `/sesi tutup` — Akhiri sesi & kirim transkrip lengkap ke DM Anda."
            ),
            inline=False,
        )
    elif category == "tools":
        embed = discord.Embed(
            title="🔎 Ringkas Pintar, Cari Berita & Klik-Kanan Pesan",
            description="Alat bantu AI instan yang bisa dipakai langsung tanpa keluar dari obrolan:",
            color=discord.Color.teal(),
        )
        embed.add_field(
            name="📝 Perangkum Obrolan & Link (`/ringkas`)",
            value=(
                "• `/ringkas chat` — Rangkum inti 25–150 pesan terakhir di channel/thread agar tidak ketinggalan topik (TL;DR).\n"
                "• `/ringkas link` — Rangkum isi **video YouTube** (`watch` / `youtu.be` / `Shorts`) atau **artikel web**, lengkap dengan tanya-jawab isi video!"
            ),
            inline=False,
        )
        embed.add_field(
            name="🌐 Pencarian Fakta & Berita Hari Ini (`/cari`)",
            value=(
                "• `/cari pertanyaan:...` — Cek berita terkini, skor pertandingan, cuaca, rilis teknologi, atau fakta terbaru hari ini lengkap dengan tautan sumber."
            ),
            inline=False,
        )
        embed.add_field(
            name="📲 Menu Tekan-Tahan / Klik-Kanan Pesan (Tanpa Ketik!)",
            value=(
                "Tekan-tahan pesan siapa saja di HP *(atau Klik Kanan di PC)* ➔ **Apps**:\n"
                "• **`🌐 Terjemahkan ke Indonesia`** — Terjemahkan pesan bahasa asing secara natural.\n"
                "• **`💡 Jelaskan Pesan Ini`** — Bedah maksud istilah rumit, kode error, atau gambar.\n"
                "• **`🔍 Cek Fakta / Hoaks`** — Periksa kebenaran klaim/berita berantai dengan sumber web."
            ),
            inline=False,
        )
    elif category == "games":
        embed = discord.Embed(
            title="🎮 6 Mode Mini-Game Tongkrongan & Papan Skor (`/game`)",
            description="Seru-seruan bareng warga server dan kejar posisi juara di klasemen!",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🕹️ Pilihan Mode Permainan (`/game mulai`)",
            value=(
                "• **🎭 Tebak dari Emoji** (`+20 Poin`) — Tebak film, game, makanan, atau benda dari rangkaian emoji.\n"
                "• **🖼️ Tebak Gambar AI** (`+25 Poin`) — Tebak objek dari ilustrasi misterius buatan AI langsung di chat!\n"
                "• **⛓️ Sambung Kata Indonesia** (`+5 Poin/Kata`) — Adu cepat sambung kata dari huruf terakhir beramai-ramai!\n"
                "• **🧠 Kuis Trivia Cepat A/B/C/D** (`+15 Poin`) — Adu cepat klik tombol pilihan ganda.\n"
                "• **🕵️ Tebak Kata Misteri** (`+20 Poin`) — 3 petunjuk bertahap *Siapakah/Apakah Aku?*.\n"
                "• **🔀 Susun Huruf Acak** (`+15 Poin`) — Susun huruf teracak menjadi kata yang tepat."
            ),
            inline=False,
        )
        embed.add_field(
            name="🏆 Command Klasemen & Kontrol",
            value=(
                "• `/game mulai` — Mulai ronde (kosongkan `jenis` untuk mode kejutan acak!).\n"
                "• `/game papan_skor` — Lihat Top 10 juara server & peringkatmu.\n"
                "• `/game stop` — Hentikan ronde yang sedang berjalan.\n"
                "• `/game reset_skor` *(Admin)* — Reset klasemen untuk musim kompetisi baru."
            ),
            inline=False,
        )
    elif category == "server":
        embed = discord.Embed(
            title="🛠️ Fitur Server: Statistik, Auto Role, Fakta & Anti-Phishing",
            description="Perkakas pengelolaan server yang berjalan otomatis 24/7:",
            color=discord.Color.dark_teal(),
        )
        embed.add_field(
            name="📊 Statistik Server (`/serverstats`)",
            value=(
                "• `/serverstats lihat` — Kartu statistik lengkap: anggota, manusia/bot, boost, channel, role, emoji, & tanggal server dibuat.\n"
                "• `/serverstats otomatis` *(Admin)* — Membuat **Voice Channel penghitung** (👥 Total Member, 🙋 Manusia, 🤖 Bot, 🟢 Online, 💎 Boost) yang ter-update otomatis tiap ±10 menit."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎭 Role Otomatis (`/autorole`) *(Admin)*",
            value=(
                "• `/autorole atur role:@Member` — Member baru langsung mendapat role tanpa verifikasi manual (bisa sampai 3 role).\n"
                "• `/autorole status` — Cek daftar role & peringatan jika posisi role bot terlalu rendah.\n"
                "• `/autorole isi` — Berikan Auto Role ke member lama yang belum punya (maks. 150 member)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🌍 Fakta Unik Dunia (`/fakta`)",
            value=(
                "• `/fakta atur channel:#umum jadwal:08:00,12:00,16:00,20:00` — Rubrik **3–4 fakta menarik dari negara berbeda**, dikirim **4x sehari** (pagi, siang, sore, malam).\n"
                "• **Jadwal fleksibel:** Admin bebas mengubah slot kapan saja (1x, 2x, 3x, hingga 6x sehari).\n"
                "• `/fakta sekarang` — Kirim contoh fakta saat ini juga (tanpa mengubah jadwal).\n"
                "• `/fakta status` — Lihat seluruh slot, slot berikutnya, & slot yang sudah terkirim hari ini."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Anti-Phishing (`/keamanan`)",
            value=(
                "• `/keamanan phising` *(Admin)* — Aktifkan penjaga link: hapus link berbahaya + peringatan + catatan log moderator.\n"
                "• `/keamanan cek link:...` — Periksa keamanan link sebelum dibuka (bisa semua member).\n"
                "• Deteksi lokal gratis: tiruan brand (Discord/Steam/dll), punycode `xn--`, IP langsung, TLD berisiko, pemendek URL, & daftar hitam phishing."
            ),
            inline=False,
        )
        embed.add_field(
            name="🚨 Anti-Spam & Anti-Raid (`/keamanan spam`)",
            value=(
                "• `/keamanan spam aktif:True` — **mode awalnya hanya *lapor*** ke channel log, "
                "tidak ada pesan yang dihapus.\n"
                "• `/keamanan spam mode:hapus log_channel:#mod-log` — hapus pesan spam otomatis.\n"
                "• `/keamanan spam mode:timeout timeout_detik:600` — hapus + time-out sementara.\n"
                "• `/keamanan spam-status` — lihat ambang deteksi, pengecualian, & jumlah tindakan.\n"
                "• Deteksi lokal: banjir pesan, pesan berulang, mention massal, link beruntun, "
                "& HURUF KAPITAL (opsional). **Admin, staf, & role pengecualian tidak pernah diperiksa.**\n"
                "• **Anti-Raid:** lonjakan member join hanya memicu *peringatan* ke channel log — "
                "tidak pernah menendang atau mem-ban otomatis."
            ),
            inline=False,
        )
    elif category == "komunitas":
        embed = discord.Embed(
            title="🧩 Fitur Komunitas Ringan (Gratis, Tanpa Kuota AI)",
            description=(
                "Semua fitur di bawah ini **default NONAKTIF** dan hanya aktif setelah Admin menyalakannya. "
                "Tidak memakai kuota Gemini sama sekali, jadi aman dipakai 24 jam."
            ),
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="🎭 Reaction Role (`/panel-role`)",
            value=(
                "• `/panel-role pasang channel:#ambil-role judul:Ambil Role role1:@Gamer emoji1:🎮` — member klik emoji untuk mengambil role sendiri.\n"
                "• `/panel-role tambah` & `/panel-role hapus` — kelola role pada panel yang sudah ada.\n"
                "• `/panel-role daftar` — lihat seluruh panel di server ini."
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Polling & Pengingat (`/poll`, `/ingatkan`)",
            value=(
                "• `/poll pertanyaan:... opsi:Jam 8, Jam 9, Jam 10` — polling native Discord, suara dihitung otomatis.\n"
                "• `/ingatkan pasang waktu:2j pesan:mabar` — bot mengingatkan kamu saat waktunya tiba (tahan restart).\n"
                "• `/ingatkan daftar` & `/ingatkan batal nomor:3` — kelola pengingat aktifmu."
            ),
            inline=False,
        )
        embed.add_field(
            name="⭐ Starboard (`/starboard`)",
            value=(
                "• `/starboard atur channel:#starboard batas:3` — pesan yang mendapat 3 bintang otomatis disalin ke channel sorotan.\n"
                "• `/starboard status` — lihat konfigurasi & jumlah pesan tersorot."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Verifikasi & Sticky (`/verifikasi`, `/sticky`)",
            value=(
                "• `/verifikasi pasang channel:#verifikasi role:@Member` — member baru klik **✅ Verifikasi Saya** untuk membuka akses.\n"
                "• `/sticky pasang isi:... channel:#umum` — pesan petunjuk yang otomatis tetap di bawah channel."
            ),
            inline=False,
        )
        embed.add_field(
            name="👤 Profil & Perawatan (`/info`, `/perawatan`)",
            value=(
                "• `/info user` & `/info server` — kartu profil member (umur akun & tanggal join) dan ringkasan server.\n"
                "• `/perawatan atur backup_channel:#bot-backup log_channel:#bot-log` — backup konfigurasi otomatis tiap 7 hari.\n"
                "• `/perawatan backup` — kirim berkas backup sekarang; `/perawatan status` — cek ukuran data & RAM."
            ),
            inline=False,
        )
    elif category == "engagement":
        embed = discord.Embed(
            title="🎉 Giveaway, Ulang Tahun, Auto-Responder & Pengumuman",
            description=(
                "Fitur **keramaian server** yang berjalan **tanpa kuota Gemini** sama sekali "
                "(0 request AI). Semua default NONAKTIF sampai Admin menyalakannya."
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🎁 Giveaway (`/giveaway`)",
            value=(
                "• `/giveaway mulai hadiah:Nitro 1 Bulan durasi:2jam pemenang:3` — tombol **🎉 Ikuti Giveaway** "
                "dipasang otomatis.\n"
                "• `/giveaway akhiri id_pesan:...` — tutup lebih awal & umumkan pemenang.\n"
                "• `/giveaway reroll id_pesan:...` — undi ulang dari peserta yang belum menang.\n"
                "• `/giveaway daftar` — giveaway yang masih berjalan + riwayat pemenang.\n"
                "• Bisa dibatasi role: `syarat_role:@Booster`."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎂 Ulang Tahun (`/ultah`)",
            value=(
                "• `/ultah set tanggal:12-08` — daftarkan tanggal lahir (boleh `12/8/2000` atau `12 Agustus`).\n"
                "• `/ultah daftar bulan:8` — lihat daftar ulang tahun member.\n"
                "• `/ultah hapus` — hapus data sendiri kapan saja.\n"
                "• `/ultah atur channel:#umum jam:08:00` *(Admin)* — ucapan otomatis tiap hari."
            ),
            inline=False,
        )
        embed.add_field(
            name="🤖 Balasan Otomatis (`/jawab-otomatis`)",
            value=(
                "• `/jawab-otomatis tambah pemicu:cara daftar balasan:...` — bot menjawab saat kata kunci muncul.\n"
                "• `/jawab-otomatis daftar` / `hapus pemicu:...` — kelola aturan per channel.\n"
                "• `/jawab-otomatis atur aktif:False jeda:30` — matikan sementara & atur jeda aman.\n"
                "• Aman untuk obrolan: hanya aktif di channel yang dipilih, ada jeda antar-balasan."
            ),
            inline=False,
        )
        embed.add_field(
            name="📢 Pengumuman Terjadwal (`/pengumuman`)",
            value=(
                "• `/pengumuman tambah isi:... jadwal:08:00` — setiap hari.\n"
                "• `/pengumuman tambah isi:... jadwal:senin 19:00` — setiap minggu.\n"
                "• `/pengumuman tambah isi:... jadwal:sekali 31-12-2026 23:59` — sekali saja.\n"
                "• `/pengumuman daftar` / `hapus id:3` / `atur id:3 aktif:False` — kelola jadwal."
            ),
            inline=False,
        )
        embed.set_footer(text="Semua data disimpan lokal di data/engagement.json — tanpa database eksternal.")
    elif category == "musik":
        embed = discord.Embed(
            title="🎵 Streaming Musik 24/7 (`/musik`) — Lavalink",
            description=(
                "Putar lagu dari **YouTube, Spotify, SoundCloud, Apple Music**, dan lainnya tanpa membebani "
                "server bot (audio diproses node Lavalink, bukan CPU bot)."
            ),
            color=discord.Color.dark_purple(),
        )
        embed.add_field(
            name="▶️ Memutar Lagu",
            value=(
                "• `/musik putar query:judul lagu` — cari & langsung putar (bot join voice channel kamu).\n"
                "• `/musik putar query:https://youtu.be/xxxx` — tempel tautan YouTube/Spotify/playlist.\n"
                "• `/musik cari query:...` — lihat 5 hasil lalu pilih dari dropdown.\n"
                "• `/musik putar query:... berikutnya:True` — selalu antrekan tanpa memotong lagu berjalan."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎛️ Kontrol Pemutaran",
            value=(
                "• `/musik sekarang` — lagu aktif + progres bar & volume.\n"
                "• `/musik antrean halaman:2` — antrean berhalaman (◀ ▶), 10 lagu/halaman.\n"
                "• `/musik jeda` / `/musik lanjut` — jeda & lanjutkan.\n"
                "• `/musik lewati jumlah:2` — lewati lagu (bisa beberapa sekaligus).\n"
                "• `/musik sebelumnya` — putar lagi lagu sebelumnya dari riwayat.\n"
                "• `/musik seek posisi:1:30` — lompat ke menit/detik tertentu.\n"
                "• `/musik acak` — acak antrean, `/musik ulang mode:satu|semua|mati`.\n"
                "• `/musik volume level:70` — atur volume (disimpan sebagai default server).\n"
                "• `/musik hentikan` — stop, kosongkan antrean, & keluar dari voice."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎚️ Panel Ala Rythm + Efek Audio",
            value=(
                "• Panel pemutar **satu pesan** muncul otomatis saat memutar lagu: progress bar "
                "`▬▬🔘▬▬` yang bergerak tiap ±10 detik + **9 tombol** "
                "(⏯️ ⏭️ ⏮️ ⏹️ 📜 🔁 🔀 🔉 🔊).\n"
                "• `/musik panel` — kirim ulang panel bila pesan lamanya terhapus.\n"
                "• `/musik filter jenis:bassboost|nightcore|vaporwave|8d|karaoke|treble|off`.\n"
                "• `/musik autoplay aktif:True` — putar rekomendasi otomatis saat antrean habis.\n"
                "• Filter & autoplay **tersimpan per server** dan dipulihkan saat bot join lagi."
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Admin & Status",
            value=(
                "• `/musik pengaturan` — pengumuman Now Playing, role DJ, & volume default.\n"
                "• `/musik status` — cek node Lavalink, antrean, & pengaturan server.\n"
                "• Butuh **Lavalink v4** (`LAVALINK_URI` + `LAVALINK_PASSWORD`). Panduan lengkap ada di README bagian F."
            ),
            inline=False,
        )
    elif category == "admin":
        embed = discord.Embed(
            title="⚙️ Panduan Admin & AI Komunitas (`/agent`)",
            description="Atur seluruh fitur AI per-channel maupun Forum secara fleksibel:",
            color=discord.Color.brand_green(),
        )
        embed.add_field(
            name="🎛️ Panel Klik-Tombol & Status",
            value=(
                "• **`/agent panel`** — **Paling Praktis!** Pilih channel/forum lewat dropdown lalu klik ON/OFF fitur, ubah persona, & kelola FAQ tanpa hafal command.\n"
                "• `/agent status` — Lihat ringkasan lengkap seluruh channel aktif & hitung mundur pemecah sepi."
            ),
            inline=False,
        )
        embed.add_field(
            name="📡 Pengaturan Fitur Per-Channel & Forum",
            value=(
                "• `/agent chat` — Auto-Chat natural, Pemecah Sepi otomatis, & penjawab **Forum Post** lengkap dengan **Auto-Tag** + tombol **`✅ Tandai Selesai`**.\n"
                "• `/agent gallery` — Komentar apresiasi visual otomatis pada foto/video karya warga.\n"
                "• `/agent youtube` & `/agent cari` — Aktifkan perangkum link & pencarian berita di channel/forum pilihan.\n"
                "• `/agent welcome` — Sambutan member baru dengan **persona khusus** (Hangat / Lucu / Santai / Normal) + kata sapaan Asia yang berganti-ganti.\n"
                "• `/agent goodbye` — Kartu perpisahan hangat saat member keluar, plus masa kebersamaan.\n"
                "• `/agent digest` — Kirim **Koran & Sapaan Pagi** terjadwal setiap hari.\n"
                "• `/agent info` & `/agent persona` — Simpan memori FAQ resmi server & gaya bahasa AI."
            ),
            inline=False,
        )
    else:
        embed = discord.Embed(
            title=f"📚 Pusat Panduan Bot Gemini AI (`v{BOT_VERSION}`)",
            description=(
                "Semua fitur telah disusun rapi agar mudah dipakai seluruh member maupun Admin.\n"
                "Pilih **kategori di menu dropdown bawah** untuk melihat detail lengkapnya!"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="⚡ Daftar Slash Command Utama (24 Menu Ringkas)",
            value=(
                "**🤖 AI & Hiburan**\n"
                "• **`/sesi`** — Ruang privat AI: panel, ganti mode, reset, tutup sesi.\n"
                "• **`/ringkas`** — Rangkum obrolan channel (`chat`) atau link YouTube/Web (`link`).\n"
                "• **`/cari`** — Cari berita, skor, cuaca, atau info terbaru hari ini.\n"
                "• **`/game`** — 6 mode Mini-Game Tongkrongan & Papan Skor.\n"
                "**🛠️ Pengelolaan Server**\n"
                "• **`/agent`** *(Admin)* — Panel kontrol AI Agent, Welcome, Goodbye, Digest, & FAQ.\n"
                "• **`/serverstats`** — Statistik server + channel penghitung otomatis.\n"
                "• **`/autorole`**, **`/verifikasi`** *(Admin)* — Role otomatis & gerbang verifikasi member.\n"
                "• **`/fakta`** — Rubrik Fakta Unik Dunia 4x sehari (08/12/16/20).\n"
                "• **`/keamanan`** — Anti-phishing otomatis & cek keamanan link.\n"
                "**🧩 Komunitas Ringan (Gratis)**\n"
                "• **`/panel-role`** — Reaction role, **`/poll`** — polling, **`/ingatkan`** — pengingat.\n"
                "• **`/starboard`** — sorotan pesan populer, **`/sticky`** — pesan petunjuk menempel.\n"
                "• **`/info`** — profil member & server, **`/perawatan`** — backup & log error.\n"
                "**🎉 Keramaian Server (Gratis, Tanpa AI)**\n"
                "• **`/giveaway`** — undian berhadiah bertombol, **`/ultah`** — ucapan ulang tahun otomatis.\n"
                "• **`/jawab-otomatis`** — balasan kata kunci, **`/pengumuman`** — pengumuman terjadwal.\n"
                "**🎵 Hiburan Audio**\n"
                "• **`/musik`** — streaming YouTube/Spotify/SoundCloud via Lavalink (putar, antrean, volume, DJ).\n"
                "• **`/status`** & **`/bantuan`** — Cek kesehatan bot & buka panduan ini."
            ),
            inline=False,
        )
        embed.add_field(
            name="💡 Pintasan Favorit Tanpa Ketik Command",
            value=(
                "• **Tekan-Tahan / Klik-Kanan Pesan ➔ Apps:** `🌐 Terjemahkan`, `💡 Jelaskan`, `🔍 Cek Fakta`\n"
                "• **Panggil Nama Bot di Channel Aktif:** Tanya langsung, kirim Voice Note `🎤`, PDF, foto, atau link!"
            ),
            inline=False,
        )

    embed.set_footer(text=f"Gemini AI v{BOT_VERSION} • Pilih kategori pada menu di bawah untuk berpindah halaman")
    return embed


class HelpMenuView(discord.ui.View):
    """Dropdown navigasi interaktif untuk berpindah halaman panduan `/bantuan`."""

    def __init__(self, requester_id: int):
        super().__init__(timeout=300)
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "💡 Ketik `/bantuan` untuk membuka menu panduan milik Anda sendiri.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(
        placeholder="📂 Pilih kategori panduan yang ingin dilihat...",
        options=[
            discord.SelectOption(
                label="Ringkasan & Daftar Command Utama",
                value="overview",
                emoji="🏠",
                description="Gambaran cepat seluruh fitur & pintasan tanpa ketik",
            ),
            discord.SelectOption(
                label="Ruang AI Privat, PDF, Voice Note & Gambar (/sesi)",
                value="sesi",
                emoji="🔒",
                description="Cara pakai ruang chat pribadi, multimodal, & studio gambar",
            ),
            discord.SelectOption(
                label="Ringkas Chat/Link, Cari Berita & Klik-Kanan Pesan",
                value="tools",
                emoji="🔎",
                description="Panduan /ringkas chat, /ringkas link, /cari, & Cek Fakta",
            ),
            discord.SelectOption(
                label="6 Mode Mini-Game Tongkrongan & Papan Skor (/game)",
                value="games",
                emoji="🎮",
                description="Tebak Gambar AI, Sambung Kata, Emoji, Trivia, & Klasemen",
            ),
            discord.SelectOption(
                label="Fitur Server: Stats, Auto Role, Fakta & Anti-Phishing",
                value="server",
                emoji="🛠️",
                description="Panduan /serverstats, /autorole, /fakta, & /keamanan",
            ),
            discord.SelectOption(
                label="Giveaway, Ulang Tahun, Auto-Responder & Pengumuman",
                value="engagement",
                emoji="🎉",
                description="Undian berhadiah, ucapan ultah otomatis, & pengumuman terjadwal",
            ),
            discord.SelectOption(
                label="Streaming Musik 24/7 (/musik & Lavalink)",
                value="musik",
                emoji="🎵",
                description="Putar lagu YouTube/Spotify, antrean, volume, & role DJ",
            ),
            discord.SelectOption(
                label="Fitur Komunitas Ringan (Role, Poll, Starboard, Sticky)",
                value="komunitas",
                emoji="🧩",
                description="Reaction role, poll, pengingat, starboard, verifikasi, & sticky",
            ),
            discord.SelectOption(
                label="Panel Admin, Forum Pintar & Komunitas (/agent)",
                value="admin",
                emoji="⚙️",
                description="Pengaturan /agent panel, Auto-Chat, Galeri, Welcome, & FAQ",
            ),
        ],
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        chosen = select.values[0]
        await interaction.response.edit_message(
            embed=build_help_embed(chosen),
            view=self,
        )
