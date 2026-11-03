import asyncio
import logging
import re
import time
import discord

from config import (
    AGENT_DEFAULT_IDLE_MINUTES,
    AI_MODELS,
    BOT_VERSION,
    DEFAULT_IMAGE_SETTINGS,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_READER,
    MAX_THREADS_PER_USER,
    RATIO_OPTIONS,
    STYLE_OPTIONS,
    resolve_model_key,
)
from community_agent import (
    STYLE_DESCRIPTIONS,
    chat_agent_channels,
    digest_agent_guilds,
    format_idle_duration,
    gallery_agent_channels,
    get_guild_search_channels,
    get_guild_settings,
    get_guild_youtube_channels,
    get_server_knowledge_entries,
    save_agent_config_to_disk,
    search_agent_channels,
    set_chat_channel_config,
    set_digest_config,
    set_gallery_channel_config,
    set_search_channel_config,
    set_welcome_config,
    set_youtube_channel_config,
    upsert_server_knowledge,
    welcome_agent_guilds,
    youtube_agent_channels,
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


def build_main_panel_embed() -> discord.Embed:
    """Membuat tampilan Embed modern untuk Panel Utama AI."""
    embed = discord.Embed(
        title="✨ GEMINI AI AUTOMATION PANEL",
        description=(
            "Selamat datang di pusat layanan **Google Gemini AI**!\n"
            "Pilih jenis ruang privat yang ingin Anda buat melalui tombol di bawah ini:\n\n"
            "💬 **Chat AI, Vision, Voice Note, PDF, YouTube & Live Search**\n"
            "> • Bebas pilih 5 mode kepribadian Gemini terbaru (Asisten, Kilat, Koding, Riset, Curhat).\n"
            "> • **Multimodal Lengkap:** Kirim **Voice Note (🎤)**, dokumen **`.pdf`**, link **YouTube / web**, foto/screenshot error, atau file kode untuk dianalisis langsung!\n"
            "> • **Info Hari Ini:** Otomatis mencari berita & fakta terkini saat menanyakan topik terbaru.\n\n"
            "🎨 **Generate & Edit Gambar AI**\n"
            "> • Buat ilustrasi berkualitas tinggi cukup dengan mengetik deskripsi.\n"
            "> • Bebas atur **7 Gaya Art** & **5 Ukuran Rasio**, serta bisa edit gambar!\n\n"
            "⚡ **Fitur Pintas di Seluruh Server:**\n"
            "> • **Tekan-Tahan Pesan ➔ Apps:** `🌐 Terjemahkan ke Indonesia`, `💡 Jelaskan Pesan Ini`, & `🔍 Cek Fakta / Hoaks`\n"
            "> • `/cari` • `/ringkas_link` • `/ringkas` • `/game mulai` (6 Mode!) • `/bantuan`"
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Setiap sesi dibuat di ruang privat (Private Thread) khusus untuk Anda.")
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
    stale_ids: list[int] = []

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
        elif thread is None:
            # Cek apakah milik guild lain; jika bukan bagian guild ini biarkan, jangan hapus sembarangan
            pass

    for sid in stale_ids:
        remove_thread_data(sid)

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
                    import io

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

            # Nonaktifkan dropdown di pesan ephemeral agar tidak terklik dua kali
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
                    f"• 🎙️ **Voice Note, Vision & Kode:** Anda bisa mengirim **Pesan Suara (🎤)**, melampirkan **gambar/screenshot**, atau **file kode** langsung di sini!\n"
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
# TOMBOL PERSISTEN FORUM POST: ✅ TANDAI SELESAI / TERJAWAB
# ==============================================================================
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

        button.disabled = True
        button.label = "Diskusi Selesai"
        try:
            if interaction.message:
                await interaction.message.edit(view=self)
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
            # Jika gagal arsip/ubah tag karena izin terbatas, coba minimal ubah judul
            try:
                if new_name != cur_name:
                    await channel.edit(name=new_name)
            except discord.HTTPException:
                pass


# ==============================================================================
# DASHBOARD STATUS & PANEL KONTROL ADMIN INTERAKTIF (/agent status & /agent panel)
# ==============================================================================
def build_agent_status_embed(guild: discord.Guild) -> discord.Embed:
    """Menyusun Embed ringkasan status lengkap AI Community Agent untuk suatu server Discord."""
    guild_id = guild.id
    cfg = get_guild_settings(guild_id)
    t_ctx = get_realtime_time_context(cfg.get("timezone"))
    faq_entries = get_server_knowledge_entries(guild_id)

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

    chat_lines = []
    for cid, cdata in guild_chats:
        idle_s = int(cdata.get("idle_seconds", int(cdata.get("idle_minutes", 0)) * 60))
        idle_lbl = format_idle_duration(idle_s) if idle_s > 0 else "Mati"
        chat_lines.append(f"• <#{cid}> — Mode `{cdata.get('reply_mode')}`, Pemecah Sepi: `{idle_lbl}`")

    gal_lines = [
        f"• <#{cid}> — Auto-Reaction: `{'ON' if gdata.get('auto_reaction', True) else 'OFF'}`"
        for cid, gdata in guild_galleries
    ]

    if not ENABLE_URL_READER:
        yt_text = "⛔ **Nonaktif Global di `.env`** (`ENABLE_URL_READER=false`)"
    elif guild_yt:
        yt_lines = [
            f"• <#{cid}> — Auto-Rangkum: `{'ON' if ydata.get('auto_in_chat') else 'OFF (Panggil Bot / /ringkas_link)'}`"
            for cid, ydata in guild_yt
        ]
        yt_text = "\n".join(yt_lines)
    else:
        yt_text = "_Belum ada channel (aktifkan via panel di bawah atau `/agent youtube`)_"

    if not ENABLE_GOOGLE_SEARCH:
        search_text = "⛔ **Nonaktif Global di `.env`** (`ENABLE_GOOGLE_SEARCH=false`)"
    elif guild_search:
        s_lines = [
            f"• <#{cid}> — `/cari`: `ON` | Auto di Obrolan: `{'ON' if sdata.get('auto_in_chat', True) else 'OFF'}`"
            for cid, sdata in guild_search
        ]
        search_text = "\n".join(s_lines)
    else:
        search_text = "_Belum ada channel (aktifkan via panel di bawah atau `/agent cari`)_"

    w_cfg = welcome_agent_guilds.get(guild_id)
    if w_cfg and w_cfg.get("enabled"):
        w_note = f"\n• Info Diselipkan: _{w_cfg['extra_note']}_" if w_cfg.get("extra_note") else ""
        welcome_text = f"✅ Aktif di <#{w_cfg['channel_id']}>{w_note}"
    else:
        welcome_text = "_Belum diaktifkan_"

    d_cfg = digest_agent_guilds.get(guild_id)
    if d_cfg and d_cfg.get("enabled"):
        digest_text = (
            f"✅ Aktif di <#{d_cfg['channel_id']}> setiap **`{d_cfg['hour']:02d}:{d_cfg['minute']:02d}`** "
            f"({t_ctx['tz_label']})\n• Topik: _{d_cfg.get('topic')}_"
        )
    else:
        digest_text = "_Belum diaktifkan (gunakan `/agent digest` atau panel di bawah)_"

    bot_disp = guild.me.display_name if guild.me else "Bot"
    embed = discord.Embed(
        title=f"🤖 Status AI Community Agent (`v{BOT_VERSION}`)",
        description=f"🕒 **Waktu Bot Saat Ini:** {t_ctx['summary']}",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🎭 Persona & Memori FAQ Server",
        value=(
            f"• **Nama Panggilan:** `{cfg.get('nickname') or bot_disp}`\n"
            f"• **Gaya Bahasa:** `{cfg.get('style_preset')}` | **Tahu Jam Tidur:** `{'Ya' if cfg.get('quiet_hours', True) else 'Tidak'}`\n"
            f"• **Catatan Server:** {cfg.get('custom_prompt') or '_(Default)_'}\n"
            f"• **Memori Info / FAQ Server (`/agent info`):** `{len(faq_entries)} entri tersimpan`"
        ),
        inline=False,
    )
    embed.add_field(
        name="💬 Channel & Forum Auto-Chat",
        value="\n".join(chat_lines) if chat_lines else "_Belum ada channel_",
        inline=False,
    )
    embed.add_field(
        name="🎨 Channel & Forum Galeri Karya",
        value="\n".join(gal_lines) if gal_lines else "_Belum ada channel_",
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
        value=f"**Welcome:** {welcome_text}\n**Morning Digest:** {digest_text}",
        inline=False,
    )
    return embed


class EditPersonaModal(discord.ui.Modal, title="🎭 Ubah Kepribadian AI Server"):
    nickname_input = discord.ui.TextInput(
        label="Nama Panggilan Akrab Bot (kosongkan = default)",
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
    prompt_input = discord.ui.TextInput(
        label="Konteks Komunitas (kosongkan = hapus)",
        style=discord.TextStyle.paragraph,
        placeholder="Contoh: Ini server komunitas developer indie & mabar Valorant Indonesia.",
        required=False,
        max_length=350,
    )

    def __init__(self, guild_id: int):
        super().__init__()
        cfg = get_guild_settings(guild_id)
        self.nickname_input.default = cfg.get("nickname") or ""
        self.style_input.default = cfg.get("style_preset") or "akrab"
        self.prompt_input.default = cfg.get("custom_prompt") or ""

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        cfg = get_guild_settings(interaction.guild.id)
        cfg["nickname"] = self.nickname_input.value.strip()
        raw_style = self.style_input.value.strip().lower()
        if raw_style in STYLE_DESCRIPTIONS:
            cfg["style_preset"] = raw_style
        cfg["custom_prompt"] = self.prompt_input.value.strip()
        await save_agent_config_to_disk()
        await interaction.response.edit_message(embed=build_agent_status_embed(interaction.guild))


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
                "⚠️ Kapasitas FAQ Server sudah penuh (maksimal 25 entri). Hapus salah satu lewat `/agent info hapus`.",
                ephemeral=True,
            )
            return
        await save_agent_config_to_disk()
        await interaction.response.edit_message(embed=build_agent_status_embed(interaction.guild))


class AgentAdminPanelView(discord.ui.View):
    """Panel Kontrol Admin Interaktif (/agent panel) dengan ChannelSelect, Toggle Fitur, & Modal."""

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
        picked = select.values[0]
        self.selected_channel_id = picked.id
        await interaction.response.send_message(
            f"📍 Channel target dipilih: <#{picked.id}>. Sekarang pilih fitur di menu **2️⃣** untuk mengaktifkan/mematikannya!",
            ephemeral=True,
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

        if action == "toggle_chat":
            currently_on = bool(chat_agent_channels.get(cid, {}).get("enabled"))
            set_chat_channel_config(
                guild_id,
                cid,
                enabled=not currently_on,
                reply_mode="smart",
                idle_minutes=0 if is_forum_like else AGENT_DEFAULT_IDLE_MINUTES,
            )
        elif action == "toggle_gallery":
            currently_on = bool(gallery_agent_channels.get(cid, {}).get("enabled"))
            set_gallery_channel_config(guild_id, cid, enabled=not currently_on, auto_reaction=True)
        elif action == "toggle_youtube":
            currently_on = bool(youtube_agent_channels.get(cid, {}).get("enabled"))
            set_youtube_channel_config(guild_id, cid, enabled=not currently_on, auto_in_chat=False)
        elif action == "toggle_search":
            currently_on = bool(search_agent_channels.get(cid, {}).get("enabled"))
            set_search_channel_config(guild_id, cid, enabled=not currently_on, auto_in_chat=True)
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

        await save_agent_config_to_disk()
        await interaction.response.edit_message(embed=build_agent_status_embed(interaction.guild), view=self)

    @discord.ui.button(label="Ubah Persona", style=discord.ButtonStyle.primary, emoji="🎭", row=2)
    async def edit_persona_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.send_modal(EditPersonaModal(interaction.guild.id))

    @discord.ui.button(label="Tambah Info / FAQ", style=discord.ButtonStyle.success, emoji="📌", row=2)
    async def add_faq_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddServerInfoModal())

    @discord.ui.button(label="Segarkan Status", style=discord.ButtonStyle.secondary, emoji="🔄", row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.edit_message(embed=build_agent_status_embed(interaction.guild), view=self)

