import time
import discord
from discord import app_commands
from discord.ext import commands

import ai_handler
from community_agent import (
    chat_agent_channels,
    gallery_agent_channels,
    get_guild_search_channels,
    get_guild_settings,
    get_guild_youtube_channels,
    is_search_enabled_in_channel,
    is_youtube_enabled_in_channel,
    search_agent_channels,
    youtube_agent_channels,
)
from config import (
    BOT_TIMEZONE,
    BOT_VERSION,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_READER,
    GEMINI_DEFAULT_MODEL,
    GEMINI_FAST_MODEL,
    GEMINI_IMAGE_MODEL,
    GEMINI_PAID_IMAGE_ENABLED,
    GEMINI_PAID_SEARCH_ENABLED,
    GEMINI_REASONING_MODEL,
    GEMINI_SEARCH_MODEL,
)
from community_tools import (
    get_last_error,
    reaction_role_panels,
    reminders,
    starboard_guilds,
    sticky_channels,
    verification_guilds,
)
from games import active_channel_games
from storage import image_thread_settings, thread_chats
from utils import (
    extract_message_attachments,
    extract_message_text_for_context,
    extract_social_media_and_stickers,
    get_realtime_time_context,
    has_voice_or_audio_attachment,
    sanitize_error_message,
)
from views import HelpMenuView, build_help_embed
from cogs.helpers import (
    enforce_member_cooldown,
    get_interaction_http_session,
    get_memory_usage_mb,
    resolve_public_feature_channel_id,
)


ringkas_group = app_commands.Group(
    name="ringkas",
    description="Rangkum obrolan channel (TL;DR), video YouTube, atau artikel web secara instan",
)


@ringkas_group.command(
    name="chat",
    description="Rangkum inti obrolan terakhir di channel/thread ini agar tidak ketinggalan topik",
)
@app_commands.describe(
    jumlah="Berapa banyak pesan terakhir yang ingin dirangkum",
    channel="Channel yang ingin dirangkum (kosongkan untuk channel saat ini)",
    publik="False = hanya terlihat oleh Anda sendiri, True = tampilkan ke channel",
)
@app_commands.choices(
    jumlah=[
        app_commands.Choice(name="25 Pesan Terakhir", value="25"),
        app_commands.Choice(name="50 Pesan Terakhir - Default", value="50"),
        app_commands.Choice(name="100 Pesan Terakhir", value="100"),
        app_commands.Choice(name="150 Pesan Terakhir", value="150"),
    ]
)
async def ringkas_chat_cmd(
    interaction: discord.Interaction,
    jumlah: app_commands.Choice[str] | None = None,
    channel: discord.TextChannel | None = None,
    publik: bool = False,
):
    target = channel or interaction.channel
    if not isinstance(target, (discord.TextChannel, discord.Thread)) or interaction.guild is None:
        await interaction.response.send_message(
            "⚠️ Command `/ringkas chat` hanya dapat digunakan di Text Channel atau Thread server.",
            ephemeral=True,
        )
        return

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

    if not await enforce_member_cooldown(interaction, "ringkas"):
        return

    limit_count = int(jumlah.value) if jumlah else 50
    await interaction.response.defer(ephemeral=not publik)

    g_cfg = get_guild_settings(interaction.guild.id)
    tz_name = g_cfg.get("timezone", BOT_TIMEZONE)
    http_session = get_interaction_http_session(interaction)

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

    collected_lines.reverse()
    summary_text, err_msg = await ai_handler.summarize_channel_messages(
        collected_lines,
        target.name,
        timezone_name=tz_name,
        http_session=http_session,
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


@ringkas_group.command(
    name="link",
    description="Rangkum isi video YouTube atau artikel website secara instan tanpa menonton penuh",
)
@app_commands.describe(
    url="Tempel link video YouTube (watch/youtu.be/shorts) atau link halaman website",
    pertanyaan="Opsional: Tanya hal spesifik dari isi video/artikel tersebut",
    publik="False = hanya terlihat oleh Anda sendiri, True = tampilkan ke channel",
)
async def ringkas_link_cmd(
    interaction: discord.Interaction,
    url: str,
    pertanyaan: str | None = None,
    publik: bool = False,
):
    eff_cid, is_priv = resolve_public_feature_channel_id(interaction.channel)
    if is_priv:
        if not ENABLE_URL_READER:
            await interaction.response.send_message(
                "🛑 Fitur pembaca link sedang dinonaktifkan pada konfigurasi bot.",
                ephemeral=True,
            )
            return
    elif not is_youtube_enabled_in_channel(eff_cid):
        active_yt = (
            [f"<#{cid}>" for cid, _ in get_guild_youtube_channels(interaction.guild.id)]
            if interaction.guild is not None
            else []
        )
        where_hint = (
            f"\n👉 Silakan gunakan di {', '.join(active_yt)} *(atau buka ruang privat AI)*."
            if active_yt
            else "\n👉 Admin dapat mengaktifkannya lewat `/agent panel` atau `/agent youtube` *(atau gunakan ruang privat AI)*."
        )
        await interaction.response.send_message(
            f"🛑 Fitur perangkum YouTube & link web **belum diaktifkan di channel ini**.{where_hint}",
            ephemeral=True,
        )
        return

    if not await enforce_member_cooldown(interaction, "ringkas_link"):
        return

    await interaction.response.defer(ephemeral=not publik)
    tz_name = BOT_TIMEZONE
    if interaction.guild is not None:
        tz_name = get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    http_session = get_interaction_http_session(interaction)

    summary_text, err_msg = await ai_handler.analyze_link_with_gemini(
        url.strip(),
        question=pertanyaan,
        timezone_name=tz_name,
        http_session=http_session,
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


@app_commands.command(
    name="cari",
    description="Cari informasi, berita, skor, harga, atau fakta terbaru hari ini secara live",
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
    eff_cid, is_priv = resolve_public_feature_channel_id(interaction.channel)
    if is_priv:
        if not ENABLE_GOOGLE_SEARCH:
            await interaction.response.send_message(
                "🛑 Fitur pencarian web sedang dinonaktifkan pada konfigurasi bot.",
                ephemeral=True,
            )
            return
    elif not is_search_enabled_in_channel(eff_cid, for_auto_chat=False):
        active_srch = (
            [f"<#{cid}>" for cid, _ in get_guild_search_channels(interaction.guild.id)]
            if interaction.guild is not None
            else []
        )
        where_hint = (
            f"\n👉 Silakan gunakan di {', '.join(active_srch)} *(atau buka ruang privat AI)*."
            if active_srch
            else "\n👉 Admin dapat mengaktifkannya lewat `/agent panel` atau `/agent cari` *(atau gunakan ruang privat AI)*."
        )
        await interaction.response.send_message(
            f"🛑 Fitur pencarian berita & web (`/cari`) **belum diaktifkan di channel ini**.{where_hint}",
            ephemeral=True,
        )
        return

    if not await enforce_member_cooldown(interaction, "cari"):
        return

    await interaction.response.defer(ephemeral=not publik)
    tz_name = BOT_TIMEZONE
    if interaction.guild is not None:
        tz_name = get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    http_session = get_interaction_http_session(interaction)

    answer_text, err_msg = await ai_handler.search_web_with_gemini(
        pertanyaan,
        timezone_name=tz_name,
        http_session=http_session,
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
    embed.set_footer(text=f"Live Web & News AI • Diminta oleh {interaction.user.display_name}")
    await interaction.followup.send(embed=embed, ephemeral=not publik)


@app_commands.command(
    name="bantuan",
    description="Buka pusat panduan interaktif cara memakai seluruh fitur Gemini AI di server ini",
)
async def slash_bantuan(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_help_embed("overview"),
        view=HelpMenuView(interaction.user.id),
        ephemeral=True,
    )


@app_commands.command(
    name="status",
    description="Lihat status koneksi bot, latensi, RAM, antrean AI, & kesehatan fitur",
)
@app_commands.describe(publik="True bila ingin menampilkan status ini ke seluruh channel")
async def slash_status(interaction: discord.Interaction, publik: bool = False):
    client = getattr(interaction, "client", None)
    started_at = float(getattr(client, "started_at", time.time()))
    uptime_sec = max(0, int(time.time() - started_at))
    hours, rem = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    raw_latency = float(getattr(client, "latency", 0.0) or 0.0)
    ping_ms = round(raw_latency * 1000) if raw_latency == raw_latency else 0
    ram_mb = get_memory_usage_mb()
    gemini_ready = "✅ Aktif" if ai_handler.is_gemini_key_configured() else "⚠️ Belum Diisi"
    tz_name = BOT_TIMEZONE
    if interaction.guild is not None:
        tz_name = get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    time_ctx = get_realtime_time_context(tz_name)

    embed = discord.Embed(
        title=f"📊 Diagnostik Bot Gemini AI (`v{BOT_VERSION}`)",
        color=discord.Color.green() if ai_handler.is_gemini_key_configured() else discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📡 Latensi Discord", value=f"`{ping_ms} ms`", inline=True)
    embed.add_field(name="💾 Pemakaian RAM", value=f"`{ram_mb} MB`", inline=True)
    embed.add_field(name="⏱️ Uptime", value=f"`{hours}j {minutes}m {seconds}d`", inline=True)
    embed.add_field(name="🔑 Gemini API Key", value=gemini_ready, inline=True)
    embed.add_field(
        name="🔒 Ruang Privat Aktif",
        value=f"`{len(thread_chats)}` chat | `{len(image_thread_settings)}` gambar",
        inline=True,
    )
    embed.add_field(
        name="🌐 Agent & Game",
        value=(
            f"`{len(chat_agent_channels)}` chat | `{len(gallery_agent_channels)}` galeri | "
            f"`{len(youtube_agent_channels)}` yt | `{len(search_agent_channels)}` cari | "
            f"`{len(active_channel_games)}` game"
        ),
        inline=True,
    )
    embed.add_field(
        name="🧩 Fitur Komunitas",
        value=(
            f"`{len(reaction_role_panels)}` panel role | `{len(reminders)}` pengingat | "
            f"`{len(starboard_guilds)}` starboard | `{len(sticky_channels)}` sticky | "
            f"`{len(verification_guilds)}` verifikasi"
        ),
        inline=False,
    )
    last_error = get_last_error()
    if last_error["at"]:
        error_text = (
            f"`{last_error['context']}` — {time.strftime('%d/%m %H:%M', time.localtime(last_error['at']))}\n"
            f"> {last_error['message'][:200]}"
        )
    else:
        error_text = "_Tidak ada error tercatat_"
    embed.add_field(name="🩺 Error Terakhir", value=error_text[:1024], inline=False)
    embed.add_field(name="🕒 Jam Lokal Server", value=f"`{time_ctx['clock']}` ({time_ctx['day_name']})", inline=False)
    img_engine_info = (
        f"`{GEMINI_IMAGE_MODEL}` (Paid)"
        if GEMINI_PAID_IMAGE_ENABLED
        else "`Flux AI` (Free Tier Instan)"
    )
    search_engine_info = (
        f"`{GEMINI_SEARCH_MODEL}` (Paid Grounding)"
        if GEMINI_PAID_SEARCH_ENABLED
        else "`Free Live Web + News RSS` (Free Tier)"
    )
    embed.add_field(
        name="♊ Mesin & Model Aktif",
        value=(
            f"• **Utama:** `{GEMINI_DEFAULT_MODEL}` | **Kilat:** `{GEMINI_FAST_MODEL}`\n"
            f"• **Koding & Riset:** `{GEMINI_REASONING_MODEL}`\n"
            f"• **Live Search:** {search_engine_info}\n"
            f"• **Generator Gambar:** {img_engine_info}"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=not publik)


async def _run_message_context_action(
    interaction: discord.Interaction,
    message: discord.Message,
    action: str,
    embed_title: str,
    embed_color: discord.Color,
) -> None:
    if not await enforce_member_cooldown(interaction, "context_menu", cooldown_sec=6):
        return
    await interaction.response.defer(ephemeral=True)

    http_session = get_interaction_http_session(interaction)
    msg_text = extract_message_text_for_context(message)
    media_parts, _, text_blocks, _ = await extract_message_attachments(
        message,
        http_session=http_session,
    )
    if not media_parts and (getattr(message, "stickers", None) or "<:" in msg_text or "<a:" in msg_text):
        social_parts, _, _ = await extract_social_media_and_stickers(
            message,
            http_session,
            include_video=False,
            include_audio=False,
        )
        media_parts.extend(social_parts)

    if not msg_text and not media_parts and not text_blocks:
        await interaction.followup.send(
            "ℹ️ Pesan tersebut tidak memiliki teks, lampiran gambar/PDF/kode, maupun Voice Note yang bisa diproses.",
            ephemeral=True,
        )
        return

    if action == "fact_check":
        tz_name = BOT_TIMEZONE
        if interaction.guild is not None:
            tz_name = get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
        result_text, err_msg = await ai_handler.fact_check_message_with_gemini(
            msg_text,
            media_parts=media_parts or None,
            text_blocks=text_blocks or None,
            timezone_name=tz_name,
            http_session=http_session,
        )
    else:
        result_text, err_msg = await ai_handler.transform_message_with_gemini(
            action,
            msg_text,
            media_parts=media_parts or None,
            text_blocks=text_blocks or None,
            http_session=http_session,
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


@app_commands.context_menu(name="🌐 Terjemahkan ke Indonesia")
async def context_translate_indonesia(interaction: discord.Interaction, message: discord.Message):
    await _run_message_context_action(
        interaction,
        message,
        action="translate_id",
        embed_title="🌐 Hasil Terjemahan ke Bahasa Indonesia",
        embed_color=discord.Color.teal(),
    )


@app_commands.context_menu(name="💡 Jelaskan Pesan Ini")
async def context_explain_message(interaction: discord.Interaction, message: discord.Message):
    await _run_message_context_action(
        interaction,
        message,
        action="explain",
        embed_title="💡 Penjelasan Isi Pesan",
        embed_color=discord.Color.gold(),
    )


@app_commands.context_menu(name="🔍 Cek Fakta / Hoaks")
async def context_fact_check_message(interaction: discord.Interaction, message: discord.Message):
    await _run_message_context_action(
        interaction,
        message,
        action="fact_check",
        embed_title="🔍 Pemeriksaan Fakta & Klaim",
        embed_color=discord.Color.orange(),
    )


def register_tools_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/ringkas` (chat & link), `/cari`, `/bantuan`, `/status`, serta 3 Context Menu."""
    bot.tree.add_command(ringkas_group)
    bot.tree.add_command(slash_cari)
    bot.tree.add_command(slash_bantuan)
    bot.tree.add_command(slash_status)
    bot.tree.add_command(context_translate_indonesia)
    bot.tree.add_command(context_explain_message)
    bot.tree.add_command(context_fact_check_message)
