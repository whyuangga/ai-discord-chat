import discord
from discord import app_commands
from discord.ext import commands

import ai_handler
import insights
from community_agent import format_server_knowledge_for_prompt
from config import (
    AI_MODELS,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_READER,
    resolve_model_key,
)
from storage import (
    get_image_settings,
    get_thread_lock,
    init_image_session,
    reset_thread_history,
    save_sessions_to_disk,
    switch_thread_model,
)
from utils import (
    check_user_cooldown,
    extract_message_attachments,
    sanitize_error_message,
    split_discord_message,
)
from views import (
    MainPanelControlView,
    build_main_panel_embed,
    can_manage_session,
    close_and_recap_session,
)
from cogs.helpers import is_interaction_admin


sesi_group = app_commands.Group(
    name="sesi",
    description="Kelola Ruang Privat Gemini AI (pasang panel, ganti mode, reset, & tutup sesi)",
    guild_only=True,
)


@sesi_group.command(
    name="panel",
    description="Pasang Panel Kontrol Ruang Privat Google Gemini AI di channel ini (Khusus Admin)",
)
async def sesi_panel_cmd(interaction: discord.Interaction):
    if not is_interaction_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **Administrator** server yang dapat memasang Panel Utama AI.",
            ephemeral=True,
        )
        return

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Jalankan `/sesi panel` di dalam Text Channel server biasa (bukan di dalam Thread/DM).",
            ephemeral=True,
        )
        return

    await interaction.channel.send(
        embed=build_main_panel_embed(),
        view=MainPanelControlView(),
    )
    await interaction.response.send_message(
        "✅ **Panel Ruang Privat Gemini AI** berhasil dipasang di channel ini!",
        ephemeral=True,
    )


@sesi_group.command(
    name="model",
    description="Ganti mode kepribadian Google Gemini di ruang chat privat saat ini",
)
@app_commands.describe(mode="Pilih mode kepribadian Gemini yang ingin digunakan")
@app_commands.choices(
    mode=[
        app_commands.Choice(name=info["name"], value=key)
        for key, info in AI_MODELS.items()
    ]
)
async def sesi_model_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    channel = interaction.channel
    if not isinstance(channel, discord.Thread) or not channel.name.startswith("ai-"):
        await interaction.response.send_message(
            "⚠️ Command `/sesi model` hanya bisa digunakan di dalam ruang chat teks (`ai-...`).",
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


@sesi_group.command(
    name="reset",
    description="Bersihkan memori obrolan atau reset setelan gambar di ruang sesi AI saat ini",
)
async def sesi_reset_cmd(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.Thread) or not (
        channel.name.startswith("ai-") or channel.name.startswith("draw-")
    ):
        await interaction.response.send_message(
            "⚠️ Command `/sesi reset` hanya bisa dijalankan di dalam ruang privat AI (`ai-...` atau `draw-...`).",
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


@sesi_group.command(
    name="tutup",
    description="Akhiri sesi privat AI saat ini dan kirim rekap transkrip ke DM Anda",
)
async def sesi_tutup_cmd(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.Thread) or not (
        channel.name.startswith("ai-") or channel.name.startswith("draw-")
    ):
        await interaction.response.send_message(
            "⚠️ Command `/sesi tutup` hanya bisa dijalankan di dalam ruang privat AI (`ai-...` atau `draw-...`).",
            ephemeral=True,
        )
        return

    await close_and_recap_session(interaction, channel)


async def handle_private_session_message(bot: commands.Bot, message: discord.Message) -> bool:
    """Memproses pesan di ruang sesi privat (`ai-...` & `draw-...`).
    Mengembalikan `True` jika pesan ditangani di ruang privat, `False` jika bukan ruang privat.
    """
    if not isinstance(message.channel, discord.Thread):
        return False

    channel_name = message.channel.name or ""
    http_session = getattr(bot, "http_session", None)

    # 1A. RUANG CHAT TEKS, VISION, PDF, VOICE NOTE, STIKER & FILE KODE (Thread 'ai-')
    if channel_name.startswith("ai-"):
        prompt = message.content.strip()
        image_parts, image_filenames, text_blocks, warnings = await extract_message_attachments(
            message,
            http_session=http_session,
        )

        if not prompt and not image_parts and not text_blocks:
            if warnings:
                await message.channel.send("⚠️ " + "\n⚠️ ".join(warnings))
            return True

        lock = get_thread_lock(message.channel.id)
        async with lock:
            async with message.channel.typing():
                try:
                    srv_knowledge = format_server_knowledge_for_prompt(
                        message.guild.id if message.guild else None
                    )
                    insights.record_ai_usage(
                        "chat",
                        user_id=message.author.id,
                        channel_id=message.channel.id,
                    )
                    reply_text = await ai_handler.get_ai_response(
                        message.channel.id,
                        prompt,
                        image_parts=image_parts,
                        image_filenames=image_filenames,
                        text_blocks=text_blocks,
                        allow_url_reader=ENABLE_URL_READER,
                        allow_web_search=ENABLE_GOOGLE_SEARCH,
                        http_session=http_session,
                        thread=message.channel,
                        bot_user_id=bot.user.id if bot.user else None,
                        server_knowledge=srv_knowledge,
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
        return True

    # 1B. RUANG GENERATE & EDIT GAMBAR AI (Thread 'draw-')
    if channel_name.startswith("draw-"):
        prompt = message.content.strip()
        image_parts, _, _, warnings = await extract_message_attachments(
            message,
            http_session=http_session,
            include_audio=False,
            include_pdf=False,
        )

        if not prompt and not image_parts:
            if warnings:
                await message.channel.send("⚠️ " + "\n⚠️ ".join(warnings))
            return True

        is_adm = isinstance(message.author, discord.Member) and bool(
            message.author.guild_permissions.administrator
        )
        rem_cd = check_user_cooldown(message.author.id, "draw_image", 8, is_admin=is_adm)
        if rem_cd > 0:
            await message.channel.send(
                f"⏳ Tunggu **{rem_cd} detik** lagi sebelum membuat gambar berikutnya ya!"
            )
            return True

        display_prompt = prompt or "Edit gambar lampiran"
        settings = get_image_settings(message.channel.id)
        status_msg = await message.channel.send(
            f"🎨 **Memproses gambar [{settings['style']} | {settings['ratio']}] untuk:** *\"{display_prompt[:150]}\"*..."
        )

        lock = get_thread_lock(message.channel.id)
        async with lock:
            async with message.channel.typing():
                try:
                    insights.record_ai_usage(
                        "galeri",
                        user_id=message.author.id,
                        channel_id=message.channel.id,
                    )
                    engine_label, picture, err_detail = await ai_handler.generate_image(
                        message.channel.id,
                        prompt,
                        reference_images=image_parts or None,
                        http_session=http_session,
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
        return True

    return False


def register_session_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command grup `/sesi` dan kompatibilitas `!setup_panel` ke bot."""
    bot.tree.add_command(sesi_group)

    @bot.command(name="setup_panel")
    @commands.has_permissions(administrator=True)
    async def prefix_setup_panel(ctx: commands.Context):
        """Kompatibilitas command prefix `!setup_panel`."""
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
