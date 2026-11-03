import logging
import discord
from discord import app_commands
from discord.ext import commands

from community_agent import (
    ASIAN_FAREWELLS,
    ASIAN_GREETINGS,
    GREETING_PERSONAS,
    clear_server_knowledge,
    delete_server_knowledge,
    generate_goodbye_message,
    generate_idle_icebreaker,
    generate_morning_digest,
    generate_welcome_greeting,
    goodbye_agent_guilds,
    set_goodbye_config,
    get_agent_channel_lock,
    get_guild_search_channels,
    get_guild_settings,
    get_guild_youtube_channels,
    parse_digest_time,
    parse_idle_duration,
    save_agent_config_to_disk,
    set_chat_channel_config,
    set_digest_config,
    set_gallery_channel_config,
    set_search_channel_config,
    set_welcome_config,
    set_youtube_channel_config,
    should_process_member_goodbye,
    should_process_member_welcome,
    upsert_server_knowledge,
    welcome_agent_guilds,
)
from config import BOT_TIMEZONE
from utils import get_realtime_time_context
from cogs.helpers import get_interaction_http_session
from views import (
    AgentAdminPanelView,
    ServerFaqManagerView,
    build_agent_status_embed,
    build_faq_list_embed,
)

logger = logging.getLogger("gemini_bot.agent_cog")


async def trigger_member_welcome(
    bot: discord.Client,
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

    bot_name = (
        guild.me.display_name
        if guild.me
        else (bot.user.display_name if bot.user else "Teman")
    )
    http_session = getattr(bot, "http_session", None)
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
                    http_session=http_session,
                )
                if greeting:
                    await target_ch.send(greeting[:1900])
                    return greeting
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Gagal mengirim pesan Auto-Welcome di %s: %s", target_ch.id, exc)
    return None


async def trigger_member_goodbye(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.abc.User,
    *,
    force: bool = False,
) -> str | None:
    """Mengirim pesan perpisahan AI saat member keluar dari server (bebas duplikat)."""
    if getattr(member, "bot", False):
        return None

    cfg = goodbye_agent_guilds.get(guild.id)
    if not cfg or not cfg.get("enabled"):
        return None

    target_ch = guild.get_channel(int(cfg["channel_id"]))
    if not isinstance(target_ch, discord.TextChannel):
        return None

    if not should_process_member_goodbye(guild.id, member.id, force=force):
        return None

    bot_name = (
        guild.me.display_name
        if guild.me
        else (bot.user.display_name if bot.user else "Teman")
    )

    days_in_server: int | None = None
    joined_at = getattr(member, "joined_at", None)
    if joined_at is not None:
        try:
            days_in_server = max(0, (discord.utils.utcnow() - joined_at).days)
        except (TypeError, AttributeError):
            days_in_server = None

    http_session = getattr(bot, "http_session", None)
    lock = get_agent_channel_lock(target_ch.id)
    async with lock:
        try:
            async with target_ch.typing():
                farewell = await generate_goodbye_message(
                    guild.id,
                    member.display_name,
                    member.mention,
                    bot_name,
                    guild_name=guild.name,
                    days_in_server=days_in_server,
                    http_session=http_session,
                )
                if not farewell:
                    return None

                embed = discord.Embed(
                    title="👋 Sampai Jumpa Lagi!",
                    description=farewell[:3900],
                    color=discord.Color.dark_grey(),
                    timestamp=discord.utils.utcnow(),
                )
                avatar = getattr(member, "display_avatar", None)
                avatar_url = getattr(avatar, "url", None)
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                if days_in_server:
                    embed.add_field(
                        name="📅 Masa Kebersamaan",
                        value=f"`{days_in_server} hari` bersama {guild.name}",
                        inline=True,
                    )
                embed.set_footer(text=f"Terima kasih sudah menjadi bagian dari {guild.name}")
                await target_ch.send(embed=embed)
                return farewell
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Gagal mengirim pesan Auto-Goodbye di %s: %s", target_ch.id, exc)
    return None


agent_group = app_commands.Group(
    name="agent",
    description="Pengaturan AI Agent Komunitas (Panel Admin, Auto-Chat, Galeri, Digest, & FAQ)",
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
    name="panel",
    description="Buka Panel Kontrol Interaktif klik-tombol untuk mengatur seluruh fitur AI",
)
async def agent_panel_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    default_cid: int | None = None
    if isinstance(interaction.channel, (discord.TextChannel, discord.ForumChannel)):
        default_cid = interaction.channel.id
    elif isinstance(interaction.channel, discord.Thread) and interaction.channel.parent_id:
        default_cid = interaction.channel.parent_id

    view = AgentAdminPanelView(interaction.user.id, default_channel_id=default_cid)
    await interaction.response.send_message(
        embed=build_agent_status_embed(interaction.guild, selected_channel_id=default_cid),
        view=view,
        ephemeral=True,
    )


@agent_group.command(
    name="status",
    description="Lihat ringkasan status seluruh channel Auto-Chat, Galeri, YouTube, Cari, & Digest",
)
async def agent_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    await interaction.response.send_message(
        embed=build_agent_status_embed(interaction.guild),
        ephemeral=True,
    )


@agent_group.command(
    name="chat",
    description="Aktifkan/atur AI Agent Auto-Chat di Text Channel maupun Channel Forum",
)
@app_commands.describe(
    channel="Pilih Text Channel atau Channel Forum tempat AI Agent ikut berdiskusi",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    mode_balas="Cerdas & Natural (rekomendasi) atau Balas Semua Pesan",
    menit_sepi="Waktu sepi sebelum AI menyapa duluan di Text Channel (misal: 1, 5, 30, 30 detik, 0)",
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
    channel: discord.TextChannel | discord.ForumChannel,
    aktif: bool,
    mode_balas: app_commands.Choice[str] | None = None,
    menit_sepi: str | None = None,
):
    if interaction.guild is None:
        return

    is_forum = isinstance(channel, discord.ForumChannel)
    parsed = (0, "Nonaktif (Channel Forum)") if is_forum else parse_idle_duration(menit_sepi)
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

    mode_label = "Cerdas & Natural" if chosen_mode == "smart" else "Balas Semua Pesan"
    if is_forum:
        await interaction.response.send_message(
            f"✅ **AI Agent Auto-Chat (Mode Forum) aktif di {channel.mention}!**\n"
            f"• **Mode Balasan:** `{mode_label}`\n"
            f"• **Otomasi Forum:** Postingan baru otomatis dijawab, diberi **Tag relevan**, & disertai tombol **`✅ Tandai Selesai`**!\n"
            f"• **Memori Terpisah:** Ingatan obrolan dijaga per postingan agar topik tidak tercampur.",
            ephemeral=True,
        )
        return

    idle_desc = (
        f"Aktif setiap **{idle_human_label}** sepi *(timer dimulai dari sekarang)*"
        if idle_secs > 0
        else "Nonaktif (`0`)"
    )
    await interaction.response.send_message(
        f"✅ **AI Agent Auto-Chat aktif di {channel.mention}!**\n"
        f"• **Mode Balasan:** `{mode_label}`\n"
        f"• **Pemecah Sepi Otomatis:** {idle_desc}\n"
        f"• **Multimodal:** Ngobrol natural, dengar **Voice Note (🎤)**, baca **PDF, Stiker & Emoji**, dan paham **Jam Lokal**.",
        ephemeral=True,
    )


@agent_group.command(
    name="gallery",
    description="Aktifkan/nonaktifkan AI Auto-Komentar Gambar & Video di channel/forum Galeri",
)
@app_commands.describe(
    channel="Pilih Text Channel atau Channel Forum/Media tempat member mengirim foto atau video",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    auto_reaction="Otomatis memberi reaksi emoji (✨/🔥/😍) pada postingan media",
)
async def agent_gallery_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
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
        f"• Setiap member mengirim **foto/gambar** atau **video pendek**, AI akan mengapresiasi isinya secara visual!\n"
        f"• **Auto-Reaction Emoji:** `{react_label}`",
        ephemeral=True,
    )


@agent_group.command(
    name="persona",
    description="Atur gaya bahasa, nama panggilan, zona waktu, & jam tenang AI Agent di server ini",
)
@app_commands.describe(
    gaya_bahasa="Pilih gaya bicara AI Agent saat berbaur di komunitas",
    nama_panggilan="Nama panggilan akrab AI (ketik - untuk reset ke nama bot)",
    zona_waktu="Zona waktu referensi saat AI menyebut jam atau menyapa",
    jam_tenang_malam="Tahan sapaan pemecah sepi otomatis saat warga tidur (23:00 - 06:00)",
    konteks_komunitas="Info opsional tentang server (ketik - untuk reset)",
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
@app_commands.describe(channel="Channel target (kosongkan untuk menyapa di channel/postingan ini)")
async def agent_sapa_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return

    target = channel or (
        interaction.channel
        if isinstance(interaction.channel, (discord.TextChannel, discord.Thread))
        else None
    )
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih Text Channel yang valid, atau jalankan langsung di dalam Postingan Forum / Thread.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    bot_name = interaction.guild.me.display_name if interaction.guild.me else "Teman"
    http_session = get_interaction_http_session(interaction)
    icebreaker = await generate_idle_icebreaker(
        target.id,
        interaction.guild.id,
        bot_name,
        idle_minutes_elapsed=30,
        manual_trigger=True,
        http_session=http_session,
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


def _persona_choices() -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=f"{data['emoji']} {data['label']}", value=key)
        for key, data in GREETING_PERSONAS.items()
    ]


def _language_choices(pool: tuple[dict, ...]) -> list[app_commands.Choice[str]]:
    seen: dict[str, str] = {}
    for item in pool:
        seen.setdefault(item["key"], item["lang"])
    choices = [app_commands.Choice(name="🌏 Acak semua bahasa (Rekomendasi)", value="auto")]
    choices.extend(
        app_commands.Choice(name=f"{lang}", value=key) for key, lang in seen.items()
    )
    return choices[:25]


@agent_group.command(
    name="welcome",
    description="Atur sambutan member baru: persona khusus + sapaan bahasa Asia yang berganti-ganti",
)
@app_commands.describe(
    channel="Channel tempat AI menyambut member baru (misal #welcome)",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    persona="Persona KHUSUS sambutan (terpisah dari persona Auto-Chat)",
    bahasa_sapaan="Bahasa kata sapaan pembuka (isi kalimat tetap Bahasa Indonesia)",
    pesan_tambahan="Info opsional yang diselipkan santai (atau ketik - untuk hapus)",
    tes_sekarang="True untuk langsung mencoba contoh sambutan AI di channel tersebut",
)
@app_commands.choices(
    persona=_persona_choices(),
    bahasa_sapaan=_language_choices(ASIAN_GREETINGS),
)
async def agent_welcome_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    persona: app_commands.Choice[str] | None = None,
    bahasa_sapaan: app_commands.Choice[str] | None = None,
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
        persona=persona.value if persona else None,
        hello_language=bahasa_sapaan.value if bahasa_sapaan else None,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            "🛑 **AI Auto-Welcomer** telah **dinonaktifkan** di server ini.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    intent_hint = ""
    client = getattr(interaction, "client", None)
    if client is not None and not getattr(getattr(client, "intents", None), "members", False):
        intent_hint = (
            "\n💡 *Tips: Aktifkan centang **Server Members Intent** di Discord Developer Portal "
            "agar sambutan bekerja di channel mana pun.*"
        )

    test_result_note = ""
    if tes_sekarang:
        sent_greeting = await trigger_member_welcome(
            interaction.client, interaction.guild, interaction.user, force=True
        )
        if sent_greeting:
            test_result_note = f"\n🎉 **Tes sambutan berhasil dikirim ke {channel.mention}!**"
        else:
            test_result_note = (
                f"\n⚠️ *Gagal mengirim tes sambutan ke {channel.mention} (cek izin kirim pesan bot & API key).*"
            )

    persona_data = GREETING_PERSONAS.get(cfg.get("persona", "hangat"), GREETING_PERSONAS["hangat"])
    lang_key = cfg.get("hello_language", "auto")
    lang_label = "Acak semua bahasa Asia Timur & Tenggara" if lang_key == "auto" else next(
        (item["lang"] for item in ASIAN_GREETINGS if item["key"] == lang_key), lang_key
    )
    extra_info = cfg.get("extra_note") or "(Tidak ada — murni sambutan santai)"

    await interaction.followup.send(
        f"👋 **AI Auto-Welcomer aktif di {channel.mention}!**\n"
        f"• **Persona Sambutan:** {persona_data['emoji']} **{persona_data['label']}** *(terpisah dari persona Auto-Chat)*\n"
        f"• **Bahasa Sapaan:** {lang_label} *(hanya kata 'halo/hai', sisanya Bahasa Indonesia)*\n"
        f"• **Pesan Tambahan:** `{extra_info}`\n"
        f"• **Anti-Bosan:** kalimat & sapaan berganti otomatis tiap member baru."
        f"{test_result_note}{intent_hint}",
        ephemeral=True,
    )


@agent_group.command(
    name="goodbye",
    description="Aktifkan pesan perpisahan AI untuk member yang keluar dari server",
)
@app_commands.describe(
    channel="Channel tempat AI mengucapkan perpisahan (misal #perpisahan)",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    persona="Persona KHUSUS perpisahan (terpisah dari persona Auto-Chat)",
    bahasa_sapaan="Bahasa kata perpisahan pembuka (isi kalimat tetap Bahasa Indonesia)",
    pesan_tambahan="Pesan tambahan yang diselipkan (atau ketik - untuk hapus)",
    tes_sekarang="True untuk langsung mencoba contoh perpisahan di channel tersebut",
)
@app_commands.choices(
    persona=_persona_choices(),
    bahasa_sapaan=_language_choices(ASIAN_FAREWELLS),
)
async def agent_goodbye_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    persona: app_commands.Choice[str] | None = None,
    bahasa_sapaan: app_commands.Choice[str] | None = None,
    pesan_tambahan: str | None = None,
    tes_sekarang: bool = False,
):
    if interaction.guild is None:
        return

    cfg = set_goodbye_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        extra_note=pesan_tambahan,
        persona=persona.value if persona else None,
        hello_language=bahasa_sapaan.value if bahasa_sapaan else None,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            "🛑 **AI Auto-Goodbye** telah **dinonaktifkan** di server ini.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    test_note = ""
    if tes_sekarang:
        sent_farewell = await trigger_member_goodbye(
            interaction.client, interaction.guild, interaction.user, force=True
        )
        if sent_farewell:
            test_note = f"\n🎉 **Tes perpisahan berhasil dikirim ke {channel.mention}!**"
        else:
            test_note = (
                f"\n⚠️ *Gagal mengirim tes perpisahan ke {channel.mention} (cek izin kirim pesan & API key).*"
            )

    persona_data = GREETING_PERSONAS.get(cfg.get("persona", "hangat"), GREETING_PERSONAS["hangat"])
    lang_key = cfg.get("hello_language", "auto")
    lang_label = "Acak semua bahasa Asia Timur & Tenggara" if lang_key == "auto" else next(
        (item["lang"] for item in ASIAN_FAREWELLS if item["key"] == lang_key), lang_key
    )
    extra_info = cfg.get("extra_note") or "(Tidak ada)"

    await interaction.followup.send(
        f"👋 **AI Auto-Goodbye aktif di {channel.mention}!**\n"
        f"• **Persona Perpisahan:** {persona_data['emoji']} **{persona_data['label']}**\n"
        f"• **Bahasa Perpisahan:** {lang_label}\n"
        f"• **Pesan Tambahan:** `{extra_info}`\n"
        f"• Setiap member yang keluar akan mendapat kartu perpisahan hangat berisi lama kebersamaan."
        f"{test_note}",
        ephemeral=True,
    )


@agent_group.command(
    name="youtube",
    description="Aktifkan/nonaktifkan perangkum link YouTube & Web di channel/forum pilihan",
)
@app_commands.describe(
    channel="Pilih Text Channel atau Channel Forum tempat perangkum link diaktifkan",
    aktif="True untuk mengaktifkan di channel/forum ini, False untuk mematikan",
    auto_di_channel="False (Default) = rangkum saat dipanggil / /ringkas link, True = semua link",
)
async def agent_youtube_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
    aktif: bool,
    auto_di_channel: bool = False,
):
    if interaction.guild is None:
        return

    cfg = set_youtube_channel_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        auto_in_chat=auto_di_channel,
    )
    await save_agent_config_to_disk()

    active_list = [f"<#{cid}>" for cid, _ in get_guild_youtube_channels(interaction.guild.id)]
    active_summary = ", ".join(active_list) if active_list else "*Belum ada channel aktif*"

    if not aktif or cfg is None:
        await interaction.response.send_message(
            f"🛑 **Perangkum YouTube & Link Web** telah **dinonaktifkan** di {channel.mention}.\n"
            f"• **Channel YouTube yang masih aktif:** {active_summary}",
            ephemeral=True,
        )
        return

    mode_info = (
        "✅ **Otomatis Baca Semua Link** *(setiap link YouTube/Web langsung dirangkum)*"
        if cfg["auto_in_chat"]
        else "🔕 **Saat Dipanggil & `/ringkas link` (Rekomendasi)** *(diam saat share link biasa, langsung merangkum saat nama bot dipanggil / pakai `/ringkas link`)*"
    )
    await interaction.response.send_message(
        f"🎬 **Perangkum YouTube & Link Web aktif di {channel.mention}!**\n"
        f"• **Mode di Channel Ini:** {mode_info}\n"
        f"• **Daftar Channel Aktif:** {active_summary}",
        ephemeral=True,
    )


@agent_group.command(
    name="cari",
    description="Aktifkan/nonaktifkan pencarian berita & web (/cari) di channel/forum pilihan",
)
@app_commands.describe(
    channel="Pilih Text Channel atau Channel Forum tempat fitur pencarian diaktifkan",
    aktif="True untuk mengaktifkan di channel/forum ini, False untuk mematikan",
    auto_di_chat="True (Default) = lewat /cari & panggil nama di chat, False = khusus /cari",
)
async def agent_cari_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
    aktif: bool,
    auto_di_chat: bool = True,
):
    if interaction.guild is None:
        return

    cfg = set_search_channel_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        auto_in_chat=auto_di_chat,
    )
    await save_agent_config_to_disk()

    active_list = [f"<#{cid}>" for cid, _ in get_guild_search_channels(interaction.guild.id)]
    active_summary = ", ".join(active_list) if active_list else "*Belum ada channel aktif*"

    if not aktif or cfg is None:
        await interaction.response.send_message(
            f"🛑 **Pencarian Berita & Web (`/cari`)** telah **dinonaktifkan** di {channel.mention}.\n"
            f"• **Channel Pencarian yang masih aktif:** {active_summary}",
            ephemeral=True,
        )
        return

    mode_info = (
        "✅ **`/cari` & Panggil Nama di Chat** *(member bisa ketik `/cari` maupun panggil nama bot langsung)*"
        if cfg["auto_in_chat"]
        else "🔎 **Khusus Command `/cari`** *(pencarian di channel ini hanya lewat `/cari`)*"
    )
    await interaction.response.send_message(
        f"🔎 **Pencarian Berita & Web aktif di {channel.mention}!**\n"
        f"• **Mode di Channel Ini:** {mode_info}\n"
        f"• **Daftar Channel Aktif:** {active_summary}",
        ephemeral=True,
    )


@agent_group.command(
    name="info",
    description="Kelola memori Info & FAQ resmi server agar AI hafal rules, IP, atau link server",
)
@app_commands.describe(
    aksi="Pilih aksi pengelolaan memori Info/FAQ server",
    topik="Judul/kata kunci info (atau nomor urut saat memilih Hapus 1 Info)",
    isi="Isi jawaban/informasi resmi yang wajib diingat AI (maks 500 karakter)",
)
@app_commands.choices(
    aksi=[
        app_commands.Choice(name="➕ Tambah / Perbarui Info", value="tambah"),
        app_commands.Choice(name="📋 Lihat & Kelola Info / FAQ", value="lihat"),
        app_commands.Choice(name="🗑️ Hapus 1 Info (Nomor / Topik)", value="hapus"),
        app_commands.Choice(name="🧹 Hapus Semua Info Server", value="reset"),
    ]
)
async def agent_info_cmd(
    interaction: discord.Interaction,
    aksi: app_commands.Choice[str],
    topik: str | None = None,
    isi: str | None = None,
):
    if interaction.guild is None:
        return

    gid = interaction.guild.id
    act = aksi.value

    if act == "lihat":
        await interaction.response.send_message(
            embed=build_faq_list_embed(interaction.guild),
            view=ServerFaqManagerView(interaction.user.id, gid),
            ephemeral=True,
        )
        return

    if act == "tambah":
        if not (topik and topik.strip()) or not (isi and isi.strip()):
            await interaction.response.send_message(
                "⚠️ Untuk menambah/memperbarui info, mohon isi kolom **`topik`** sekaligus **`isi`**.",
                ephemeral=True,
            )
            return
        item, status = upsert_server_knowledge(gid, topik, isi)
        if status == "full" or item is None:
            await interaction.response.send_message(
                "⚠️ Kapasitas memori FAQ Server sudah mencapai batas maksimal (**25 entri**). Hapus entri lama terlebih dahulu.",
                ephemeral=True,
            )
            return
        await save_agent_config_to_disk()
        verb = "diperbarui" if status == "updated" else "ditambahkan"
        await interaction.response.send_message(
            f"✅ Info server **`{item['topic']}`** berhasil **{verb}**!\n"
            f"> {item['content']}\n"
            "*(AI kini otomatis mengingat informasi ini saat menjawab pertanyaan warga)*",
            ephemeral=True,
        )
        return

    if act == "hapus":
        if not (topik and topik.strip()):
            await interaction.response.send_message(
                "⚠️ Ketik **nomor urut** (misal `1`) atau **nama topik** pada kolom `topik` untuk menghapus.",
                ephemeral=True,
            )
            return
        removed = delete_server_knowledge(gid, topik)
        if removed is None:
            await interaction.response.send_message(
                f"⚠️ Entri dengan nomor/topik **`{topik}`** tidak ditemukan. Cek daftar lewat `/agent info aksi:Lihat`.",
                ephemeral=True,
            )
            return
        await save_agent_config_to_disk()
        await interaction.response.send_message(
            f"🗑️ Entri **`{removed['topic']}`** berhasil dihapus dari memori server.",
            ephemeral=True,
        )
        return

    count = clear_server_knowledge(gid)
    await save_agent_config_to_disk()
    await interaction.response.send_message(
        f"🧹 Seluruh memori Info/FAQ server (**{count} entri**) telah dibersihkan.",
        ephemeral=True,
    )


@agent_group.command(
    name="digest",
    description="Atur pengiriman Koran & Sapaan Pagi otomatis setiap hari di channel pilihan",
)
@app_commands.describe(
    channel="Pilih Text Channel tempat AI mengirim sapaan & berita pagi harian",
    aktif="True untuk mengaktifkan jadwal harian, False untuk mematikan",
    jam="Jam kirim harian format HH:MM (contoh: 07:00 atau 06:30, default 07:00)",
    topik="Fokus topik berita pagi (kosongkan = berita Indonesia, tekno, & game)",
    tes_sekarang="True untuk langsung mencoba kirim contoh Koran Pagi sekarang juga",
)
async def agent_digest_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool,
    jam: str | None = None,
    topik: str | None = None,
    tes_sekarang: bool = False,
):
    if interaction.guild is None:
        return

    parsed_hm = parse_digest_time(jam)
    if parsed_hm is None:
        await interaction.response.send_message(
            "⚠️ Format `jam` tidak valid. Gunakan format 24-jam seperti `07:00`, `06:30`, atau `8`.",
            ephemeral=True,
        )
        return

    hour, minute = parsed_hm
    cfg = set_digest_config(
        interaction.guild.id,
        channel.id,
        enabled=aktif,
        hour=hour,
        minute=minute,
        topic=topik,
    )
    await save_agent_config_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            "🛑 **Koran & Sapaan Pagi Otomatis (Morning Digest)** telah **dinonaktifkan** di server ini.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    g_cfg = get_guild_settings(interaction.guild.id)
    t_ctx = get_realtime_time_context(g_cfg.get("timezone", BOT_TIMEZONE))
    http_session = get_interaction_http_session(interaction)

    test_note = ""
    if tes_sekarang:
        bot_name = interaction.guild.me.display_name if interaction.guild.me else "Teman"
        digest_text, err = await generate_morning_digest(
            interaction.guild.id,
            bot_name,
            http_session=http_session,
        )
        if digest_text and not err:
            d_embed = discord.Embed(
                title=f"☀️ Koran & Sapaan Pagi — {t_ctx['day_name']}, {t_ctx['date_str']}",
                description=digest_text[:4090],
                color=discord.Color.gold(),
            )
            d_embed.set_footer(text=f"Tes Kirim Langsung • Jadwal Harian {hour:02d}:{minute:02d} {t_ctx['tz_label']}")
            await channel.send(embed=d_embed)
            test_note = f"\n🎉 **Contoh Koran Pagi berhasil dikirim ke {channel.mention}!**"
        else:
            test_note = f"\n⚠️ *Gagal mengirim tes Koran Pagi: {err or 'Cek koneksi API'}*"

    await interaction.followup.send(
        f"☀️ **Morning Digest aktif di {channel.mention}!**\n"
        f"• **Jadwal Kirim Harian:** Setiap pukul **`{hour:02d}:{minute:02d} {t_ctx['tz_label']}`**\n"
        f"• **Topik Berita:** `{cfg['topic']}`"
        f"{test_note}",
        ephemeral=True,
    )


def register_agent_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command grup `/agent` ke bot."""
    bot.tree.add_command(agent_group)
