import asyncio
import logging
import re
import time
import discord

from config import (
    AI_MODELS,
    DEFAULT_IMAGE_SETTINGS,
    MAX_THREADS_PER_USER,
    RATIO_OPTIONS,
    STYLE_OPTIONS,
    resolve_model_key,
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
from utils import build_session_transcript, sanitize_error_message

logger = logging.getLogger("gemini_bot.views")


def build_main_panel_embed() -> discord.Embed:
    """Membuat tampilan Embed modern untuk Panel Utama AI."""
    embed = discord.Embed(
        title="✨ GEMINI AI AUTOMATION PANEL",
        description=(
            "Selamat datang di pusat layanan **Google Gemini AI**!\n"
            "Pilih jenis ruang privat yang ingin Anda buat melalui tombol di bawah ini:\n\n"
            "💬 **Chat AI, Vision & Koding**\n"
            "> • Bebas pilih 5 mode kepribadian Gemini terbaru (Asisten, Kilat, Koding, Riset, Curhat).\n"
            "> • **Mendukung Vision & File:** Kirim foto/screenshot error atau file kode (`.py`, `.js`, `.txt`, dll) untuk dianalisis langsung!\n"
            "> • Bisa ganti mode kapan saja & memori tahan restart.\n\n"
            "🎨 **Generate & Edit Gambar AI**\n"
            "> • Buat ilustrasi berkualitas tinggi cukup dengan mengetik deskripsi.\n"
            "> • Bebas atur **7 Gaya Art** & **5 Ukuran Rasio**.\n"
            "> • Lampirkan gambar + instruksi teks untuk mengedit gambar!"
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
                    f"• 📷 **Vision & Kode:** Anda juga bisa melampirkan **gambar/screenshot** atau **file kode** langsung di sini!\n"
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
