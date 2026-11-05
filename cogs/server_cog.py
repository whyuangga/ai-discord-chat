import logging

import discord
from discord import app_commands
from discord.ext import commands

from antispam import (
    SPAM_MODES,
    build_spam_status_embed,
    get_spam_config,
    save_antispam_to_disk,
    set_spam_config,
)
from cogs.helpers import get_interaction_http_session
from server_features import (
    PHISHING_ACTIONS,
    analyze_url_risk,
    backfill_autoroles,
    build_facts_embed,
    build_facts_fallback,
    build_serverstats_embed,
    describe_slot,
    facts_guilds,
    format_facts_schedule,
    generate_daily_facts,
    get_autorole_role_ids,
    next_facts_slot,
    parse_schedule_input,
    sent_slots_today,
    save_server_features_to_disk,
    serverstats_guilds,
    set_autorole_config,
    set_facts_config,
    set_security_config,
    STATS_CHANNEL_TYPES,
    reset_serverstats_appearance,
    set_serverstats_category_name,
    set_serverstats_channel_type,
    stats_channel_type,
    set_serverstats_config,
    set_serverstats_emojis,
    stats_emojis,
    update_serverstats_channels,
)
from utils import get_realtime_time_context
from config import BOT_TIMEZONE, FACTS_DEFAULT_TIMES, FACTS_MAX_SLOTS
from community_agent import get_guild_settings

logger = logging.getLogger("gemini_bot.server_cog")


def _ensure_admin(interaction: discord.Interaction) -> bool:
    user = interaction.user
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.",
        ephemeral=True,
    )


# ==============================================================================
# /serverstats — Kartu Statistik Server + Voice Channel Penghitung Otomatis
# ==============================================================================
serverstats_group = app_commands.Group(
    name="serverstats",
    description="Statistik server lengkap & Voice Channel penghitung otomatis ala bot serverstats",
    guild_only=True,
)


@serverstats_group.command(
    name="lihat",
    description="Tampilkan kartu statistik server: anggota, boost, channel, role, & emoji",
)
async def serverstats_lihat_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    await interaction.response.defer(ephemeral=True)
    presence_count = None
    client = getattr(interaction, "client", None)
    if client is not None:
        try:
            fresh = await client.fetch_guild(interaction.guild.id, with_counts=True)
            presence_count = getattr(fresh, "approximate_presence_count", None)
        except (discord.HTTPException, AttributeError):
            presence_count = None

    await interaction.followup.send(
        embed=build_serverstats_embed(interaction.guild, presence_count=presence_count),
        ephemeral=True,
    )


@serverstats_group.command(
    name="otomatis",
    description="Aktifkan/matikan Voice Channel statistik yang ter-update otomatis tiap 10 menit",
)
@app_commands.describe(aktif="True untuk membuat & memperbarui otomatis, False untuk mematikan")
async def serverstats_otomatis_cmd(interaction: discord.Interaction, aktif: bool = True):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not aktif:
        cfg = serverstats_guilds.pop(interaction.guild.id, None)
        await save_server_features_to_disk()
        note = ""
        if cfg and cfg.get("category_id"):
            note = (
                f"\n💡 Channel & kategori statistik yang sudah terlanjur dibuat tetap ada — "
                f"hapus manual <#{cfg.get('category_id')}> bila tidak diperlukan."
            )
        await interaction.response.send_message(
            f"🛑 **Server Stats Otomatis** dinonaktifkan.{note}", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    set_serverstats_config(interaction.guild.id, enabled=True)
    changed = await update_serverstats_channels(
        interaction.guild, force=True, bot=getattr(interaction, "client", None)
    )

    if changed == 0:
        await interaction.followup.send(
            "⚠️ Gagal membuat Voice Channel statistik. Pastikan bot punya izin **Manage Channels** "
            "dan posisi role bot berada di atas channel terkait.",
            ephemeral=True,
        )
        return

    kind_meta = STATS_CHANNEL_TYPES[stats_channel_type(interaction.guild.id)]
    await interaction.followup.send(
        f"📊 **Server Stats Otomatis aktif!**\n"
        f"• **{changed}** channel statistik dibuat/diperbarui di kategori `📊 Statistik Server`.\n"
        f"• Jenis channel: {kind_meta['emoji']} **{kind_meta['label']}** "
        f"*(ganti ikon channel lewat `/serverstats tipe`)*.\n"
        f"• Statistik akan **disinkronkan otomatis setiap ±10 menit** (aman dari rate limit Discord).\n"
        f"• Warga tidak bisa masuk ke channel penghitung tersebut.",
        ephemeral=True,
    )


@serverstats_group.command(
    name="ikon",
    description="Ganti emoji ikon tiap Voice Channel statistik (atau hapus ikonnya)",
)
@app_commands.describe(
    anggota="Emoji untuk channel Total Member (contoh: 👥)",
    manusia="Emoji untuk channel Manusia (contoh: 🧑)",
    bot="Emoji untuk channel Bot (contoh: 🤖)",
    online="Emoji untuk channel Online (contoh: 🟢)",
    boost="Emoji untuk channel Boost (contoh: 💎)",
    kategori="Nama kategori statistik (contoh: 📈 Statistik Server)",
    reset="True untuk mengembalikan semua ikon & nama kategori ke bawaan bot",
)
async def serverstats_ikon_cmd(
    interaction: discord.Interaction,
    anggota: str | None = None,
    manusia: str | None = None,
    bot: str | None = None,
    online: str | None = None,
    boost: str | None = None,
    kategori: str | None = None,
    reset: bool = False,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    guild_id = interaction.guild.id
    if reset:
        reset_serverstats_appearance(guild_id)
    else:
        set_serverstats_emojis(
            guild_id,
            {
                "members": anggota,
                "humans": manusia,
                "bots": bot,
                "online": online,
                "boosts": boost,
            },
        )
        if kategori is not None:
            set_serverstats_category_name(guild_id, kategori)

    await save_server_features_to_disk()
    await interaction.response.defer(ephemeral=True)

    changed = await update_serverstats_channels(
        interaction.guild, force=True, bot=getattr(interaction, "client", None)
    )

    emojis = stats_emojis(guild_id)
    lines = [
        f"• {emojis['members']} Total Member".replace("•  ", "• "),
        f"• {emojis['humans']} Manusia".replace("•  ", "• "),
        f"• {emojis['bots']} Bot".replace("•  ", "• "),
        f"• {emojis['online']} Online".replace("•  ", "• "),
        f"• {emojis['boosts']} Boost".replace("•  ", "• "),
    ]
    body = (
        "### 🎨 Ikon Server Stats\n"
        + "\n".join(lines)
        + f"\n\n`{changed}` channel diperbarui."
    )
    note = (
        "\n\n**Catatan:** ikon 🔊 di sisi kiri nama channel mengikuti **tipe channel**. "
        "Kalau ingin ikon lain (`#`, 📢, 🎤), ganti tipenya lewat `/serverstats tipe`. "
        "Yang diatur di sini adalah emoji di dalam nama channel dan nama kategorinya."
    )
    if not serverstats_guilds.get(guild_id, {}).get("enabled"):
        note = (
            "\n\n⚠️ Server Stats otomatis sedang **nonaktif**. Aktifkan dengan "
            "`/serverstats otomatis aktif:True` agar channel dibuat/diperbarui." + note
        )

    import ui_kit
    import ui_theme

    await ui_kit.follow_panel(
        interaction,
        ui_kit.build_view(
            guild_id,
            ui_kit.card(
                guild_id,
                ui_kit.text(body[:3900]),
                ui_kit.text(note[:1200]),
            ),
            timeout=None,
        ),
        embed=ui_theme.apply_embed_theme(
            discord.Embed(
                title="🎨 Ikon Server Stats",
                description=(body + note)[:4000],
                color=discord.Color.blurple(),
            ),
            guild_id,
            footer="Ikon voice channel tidak bisa diubah oleh bot",
        ),
        ephemeral=True,
    )


@serverstats_group.command(
    name="tipe",
    description="Pilih jenis channel counter (voice 🔊, text #, announcement 📢, stage 🎤)",
)
@app_commands.describe(
    channel="Jenis channel yang dipakai untuk counter statistik",
    aktif="True untuk langsung membuat/menerapkan (default), False hanya menyimpan pilihan",
)
@app_commands.choices(
    channel=[
        app_commands.Choice(name=f"{meta['emoji']} {meta['label']}", value=key)
        for key, meta in STATS_CHANNEL_TYPES.items()
    ]
)
async def serverstats_tipe_cmd(
    interaction: discord.Interaction,
    channel: app_commands.Choice[str],
    aktif: bool = True,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    guild_id = interaction.guild.id
    before = stats_channel_type(guild_id)
    chosen = set_serverstats_channel_type(guild_id, channel.value)
    await save_server_features_to_disk()

    if not aktif:
        await interaction.response.send_message(
            f"💾 Jenis channel counter disimpan: **{STATS_CHANNEL_TYPES[chosen]['label']}**.\n"
            "Jalankan `/serverstats otomatis aktif:True` untuk menerapkannya.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    enabled_now = bool(serverstats_guilds.get(guild_id, {}).get("enabled"))
    if not enabled_now:
        set_serverstats_config(guild_id, enabled=True)
        set_serverstats_channel_type(guild_id, chosen)
    changed = await update_serverstats_channels(
        interaction.guild, force=True, bot=getattr(interaction, "client", None)
    )

    meta = STATS_CHANNEL_TYPES[chosen]
    lines = [
        f"### {meta['emoji']} Jenis Channel Counter",
        f"• Sebelumnya: `{STATS_CHANNEL_TYPES.get(before, STATS_CHANNEL_TYPES['voice'])['label']}`",
        f"• Sekarang: **{meta['label']}**",
        f"• Channel dibuat/diperbarui: `{changed}`",
    ]
    if chosen == "voice":
        lines.append("\nIkon 🔊 adalah ikon bawaan Discord untuk *Voice Channel*.")
    else:
        lines.append(
            "\nCounter kini tampil sebagai channel bertipe "
            f"**{meta['label']}**, sehingga ikonnya berubah mengikuti tipe tersebut "
            "(bukan 🔊 lagi). Warga tetap bisa melihat angkanya, tapi **tidak bisa mengirim pesan**."
        )
    if changed == 0:
        lines.append(
            "\n⚠️ Tidak ada channel yang berubah. Pastikan bot punya izin **Manage Channels** "
            "dan posisi role bot di atas kategori statistik."
        )

    import ui_kit
    import ui_theme

    body = "\n".join(lines)[:3900]
    await ui_kit.follow_panel(
        interaction,
        ui_kit.build_view(guild_id, ui_kit.card(guild_id, ui_kit.text(body)), timeout=None),
        embed=ui_theme.apply_embed_theme(
            discord.Embed(
                title=f"{meta['emoji']} Jenis Channel Counter",
                description=body,
                color=discord.Color.blurple(),
            ),
            guild_id,
            footer="Ikon channel mengikuti TIPE channel, bukan isi nama",
        ),
        ephemeral=True,
    )


# ==============================================================================
# /autorole — Role Otomatis untuk Member Baru
# ==============================================================================
autorole_group = app_commands.Group(
    name="autorole",
    description="Berikan role otomatis ke setiap member baru yang bergabung",
    default_permissions=discord.Permissions(administrator=True),
    guild_only=True,
)


@autorole_group.command(
    name="atur",
    description="Atur 1–3 role yang otomatis diberikan ke member baru",
)
@app_commands.describe(
    role="Role utama yang otomatis diberikan ke member baru",
    role2="Role tambahan ke-2 (opsional)",
    role3="Role tambahan ke-3 (opsional)",
    aktif="True untuk mengaktifkan, False untuk mematikan Auto Role",
)
async def autorole_atur_cmd(
    interaction: discord.Interaction,
    role: discord.Role,
    role2: discord.Role | None = None,
    role3: discord.Role | None = None,
    aktif: bool = True,
):
    if interaction.guild is None:
        return

    if not aktif:
        set_autorole_config(interaction.guild.id, [], enabled=False)
        await save_server_features_to_disk()
        await interaction.response.send_message(
            "🛑 **Auto Role** telah dinonaktifkan di server ini.", ephemeral=True
        )
        return

    picked = [r for r in (role, role2, role3) if r is not None]
    invalid = [
        r.name
        for r in picked
        if getattr(r, "managed", False) or getattr(r, "is_default", lambda: False)()
    ]
    if invalid:
        await interaction.response.send_message(
            "⚠️ Role berikut tidak bisa dipakai Auto Role: "
            + ", ".join(f"`{n}`" for n in invalid)
            + " *(role bot integrasi / @everyone)*.",
            ephemeral=True,
        )
        return

    bot_member = interaction.guild.me
    if bot_member is not None:
        too_high = [r for r in picked if r >= bot_member.top_role]
        if too_high:
            await interaction.response.send_message(
                "⚠️ Posisi role bot harus **lebih tinggi** dari role yang mau diberikan: "
                + ", ".join(r.mention for r in too_high)
                + ".\nGeser role bot ke atas di **Server Settings ➔ Roles**.",
                ephemeral=True,
            )
            return

    cfg = set_autorole_config(interaction.guild.id, [r.id for r in picked], enabled=True)
    await save_server_features_to_disk()
    await interaction.response.send_message(
        f"✅ **Auto Role aktif!**\n"
        f"• Member baru otomatis mendapat: {', '.join(r.mention for r in picked)}\n"
        f"• Bot **tidak** mendapat role ini.\n"
        f"• Role yang di-*managed* server lain / `@everyone` otomatis dilewati.\n"
        f"• Total role Auto Role: `{len(cfg.get('role_ids') if cfg else [])}/{3}`",
        ephemeral=True,
    )


@autorole_group.command(
    name="status",
    description="Lihat daftar role otomatis & statusnya saat ini",
)
async def autorole_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    role_ids = get_autorole_role_ids(interaction.guild.id)
    if not role_ids:
        await interaction.response.send_message(
            "ℹ️ **Auto Role belum aktif.** Atur lewat `/autorole atur role:@NamaRole`.",
            ephemeral=True,
        )
        return

    lines = []
    for rid in role_ids:
        r = interaction.guild.get_role(rid)
        lines.append(f"• {r.mention}" if r else f"• ⚠️ Role `{rid}` tidak ditemukan (sudah dihapus?)")

    blocked = 0
    bot_member = interaction.guild.me
    if bot_member is not None:
        for rid in role_ids:
            r = interaction.guild.get_role(rid)
            if r is not None and r >= bot_member.top_role:
                blocked += 1

    await interaction.response.send_message(
        "🎭 **Status Auto Role**\n" + "\n".join(lines) +
        "\n\nSaat member baru bergabung, role ini otomatis terpasang tanpa perlu verifikasi manual."
        + (f"\n⚠️ **{blocked} role** berada di atas role bot sehingga gagal dipasang." if blocked else ""),
        ephemeral=True,
    )


@autorole_group.command(
    name="isi",
    description="Berikan Auto Role ke member lama yang belum memilikinya (maks. 150 member)",
)
async def autorole_isi_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    if not get_autorole_role_ids(interaction.guild.id):
        await interaction.response.send_message(
            "⚠️ Atur dulu role-nya lewat `/autorole atur role:@NamaRole`.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        changed, checked = await backfill_autoroles(interaction.guild, limit=150)
    except (discord.Forbidden, discord.HTTPException, AttributeError, TypeError):
        await interaction.followup.send(
            "⚠️ Gagal membaca daftar member. Pastikan **Server Members Intent** aktif di "
            "Discord Developer Portal dan bot punya izin **Manage Roles**.",
            ephemeral=True,
        )
        return

    if checked == 0:
        await interaction.followup.send(
            "ℹ️ Tidak ada member yang perlu diperiksa. Pastikan **Server Members Intent** aktif "
            "di Discord Developer Portal agar bot bisa membaca daftar member.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"✅ **Auto Role massal selesai!**\n"
        f"• Member diperiksa: `{checked}`\n"
        f"• Member yang baru diberi role: `{changed}`",
        ephemeral=True,
    )


# ==============================================================================
# /fakta — Rubrik Fakta Unik Dunia (Jadwal Multi-Slot)
# ==============================================================================
fakta_group = app_commands.Group(
    name="fakta",
    description="Rubrik Fakta Unik Dunia dengan jadwal multi-slot yang bisa diatur Admin",
    guild_only=True,
)

_FACTS_SCHEDULE_PRESETS: list[tuple[str, str]] = [
    ("4x sehari: 08:00, 12:00, 16:00, 20:00 (Default)", "08:00,12:00,16:00,20:00"),
    ("3x sehari: 08:00, 13:00, 20:00", "08:00,13:00,20:00"),
    ("2x sehari: 08:00, 20:00", "08:00,20:00"),
    ("2x sehari: 12:00, 19:00", "12:00,19:00"),
    ("1x sehari: 08:00", "08:00"),
    ("1x sehari: 19:00", "19:00"),
    ("3x sehari: 09:00, 15:00, 21:00", "09:00,15:00,21:00"),
]


async def _facts_schedule_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    typed = (current or "").strip().lower()
    if not typed:
        return [app_commands.Choice(name=label, value=value) for label, value in _FACTS_SCHEDULE_PRESETS]

    choices: list[app_commands.Choice[str]] = []
    parsed, error = parse_schedule_input(typed)
    if not error and parsed:
        preview = ", ".join(parsed)
        choices.append(
            app_commands.Choice(
                name=f"Pakai jadwal ini: {preview}"[:100],
                value=preview[:100],
            )
        )

    for label, value in _FACTS_SCHEDULE_PRESETS:
        if typed in label.lower() or typed in value:
            if all(choice.value != value for choice in choices):
                choices.append(app_commands.Choice(name=label[:100], value=value[:100]))
    return choices[:10]


@fakta_group.command(
    name="atur",
    description="Atur channel & jadwal multi-slot rubrik Fakta Unik Dunia (default 08/12/16/20)",
)
@app_commands.describe(
    channel="Channel tujuan fakta unik (kosongkan untuk memakai channel yang sudah tersimpan)",
    aktif="True untuk mengaktifkan jadwal, False untuk mematikan",
    jadwal=f"Slot jam dipisah koma, misal 08:00,12:00,16:00,20:00 (maks {FACTS_MAX_SLOTS} slot/hari)",
)
@app_commands.autocomplete(jadwal=_facts_schedule_autocomplete)
async def fakta_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    aktif: bool = True,
    jadwal: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    existing = facts_guilds.get(interaction.guild.id) or {}
    stored_channel_id = int(existing.get("channel_id") or 0)

    if not aktif:
        set_facts_config(interaction.guild.id, channel.id if channel else stored_channel_id, enabled=False)
        await save_server_features_to_disk()
        await interaction.response.send_message(
            "🛑 **Rubrik Fakta Unik Dunia** dinonaktifkan di server ini.\n"
            "> Jadwal yang tersimpan akan dipakai lagi saat diaktifkan kembali.",
            ephemeral=True,
        )
        return

    target = channel or (
        interaction.guild.get_channel(stored_channel_id) if stored_channel_id else None
    )
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel` tujuan terlebih dahulu, misalnya "
            "`/fakta atur channel:#umum jadwal:08:00,12:00,16:00,20:00`.",
            ephemeral=True,
        )
        return

    parsed_times: list[str] | None = None
    if jadwal and jadwal.strip():
        parsed_times, error = parse_schedule_input(jadwal)
        if error or not parsed_times:
            await interaction.response.send_message(
                f"⚠️ {error or 'Jadwal tidak valid.'}\n"
                "**Contoh format yang benar:**\n"
                "• `08:00,12:00,16:00,20:00` *(4x sehari — default)*\n"
                "• `8,12,16,20` *(format singkat)*\n"
                "• `08:00, 20:00` *(2x sehari)*\n"
                "• `09:00` *(1x sehari)*\n"
                f"Maksimal **{FACTS_MAX_SLOTS} slot** per hari.",
                ephemeral=True,
            )
            return
    else:
        # Tanpa parameter `jadwal`: pertahankan jadwal tersimpan (atau default untuk server baru).
        parsed_times = list(existing.get("times") or FACTS_DEFAULT_TIMES)

    cfg = set_facts_config(
        interaction.guild.id,
        target.id,
        enabled=True,
        times=parsed_times if jadwal and jadwal.strip() else None,
    )
    if cfg is None:
        # Server baru yang belum punya jadwal tersimpan -> pakai default.
        cfg = set_facts_config(interaction.guild.id, target.id, enabled=True, times=parsed_times)
    await save_server_features_to_disk()

    if cfg is None:
        await interaction.response.send_message(
            "⚠️ Gagal menyimpan jadwal. Coba lagi sebentar lagi.", ephemeral=True
        )
        return

    t_ctx = get_realtime_time_context(
        get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    )
    now_minutes = t_ctx["hour"] * 60 + t_ctx["minute"]
    next_slot = next_facts_slot(cfg["times"], now_minutes=now_minutes)
    next_text = (
        f"`{next_slot[0]}` {describe_slot(next_slot[0])} — sekitar **{next_slot[1]} menit** lagi"
        if next_slot
        else "belum ada slot"
    )

    await interaction.response.send_message(
        f"🧠 **Fakta Unik Dunia aktif di {target.mention}!**\n"
        f"• **Jadwal Harian:** {format_facts_schedule(cfg['times'])} {t_ctx['tz_label']}"
        f" *({len(cfg['times'])}x sehari)*\n"
        f"• **Slot Berikutnya:** {next_text}\n"
        f"• **Isi Tiap Slot:** 3–4 fakta menarik dari negara berbeda + sapaan sesuai suasana waktu.\n"
        f"• **Anti-Bosan:** fakta yang sudah pernah dikirim tidak akan diulang.\n"
        f"• Ubah jadwal kapan saja, contoh: `/fakta atur channel:#{target.name} jadwal:08:00,20:00`.",
        ephemeral=True,
    )


@fakta_group.command(
    name="sekarang",
    description="Kirim contoh rubrik Fakta Unik Dunia sekarang juga (tes manual)",
)
@app_commands.describe(channel="Channel tujuan (kosongkan untuk channel saat ini)")
async def fakta_sekarang_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = channel or (
        interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
    )
    if target is None:
        await interaction.response.send_message(
            "⚠️ Jalankan command ini di Text Channel atau pilih `channel`-nya.", ephemeral=True
        )
        return

    schedule_was_active = bool((facts_guilds.get(interaction.guild.id) or {}).get("enabled"))
    await interaction.response.defer(ephemeral=True)

    bot_name = (
        interaction.guild.me.display_name
        if interaction.guild.me
        else "Teman"
    )
    content, err = await generate_daily_facts(
        interaction.guild.id, bot_name, http_session=get_interaction_http_session(interaction)
    )
    used_fallback = False
    if not content:
        content = build_facts_fallback()
        used_fallback = True

    guild_cfg = get_guild_settings(interaction.guild.id)
    try:
        await target.send(embed=build_facts_embed(guild_cfg, content))
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim fakta ke {target.mention}. Cek izin **Send Messages** bot.",
            ephemeral=True,
        )
        return

    await save_server_features_to_disk()
    note = " *(memakai cadangan fakta offline karena Gemini sedang sibuk)*" if used_fallback else ""
    schedule_note = (
        "Jadwal harian tetap aktif (tes manual tidak mengubah slot jadwal)."
        if schedule_was_active
        else "Jadwal harian belum aktif — pasang dengan `/fakta atur channel:#nama-channel`."
    )
    await interaction.followup.send(
        f"✅ Contoh Fakta Unik Dunia terkirim ke {target.mention}!{note}\n{schedule_note}",
        ephemeral=True,
    )


@fakta_group.command(
    name="status",
    description="Lihat jadwal multi-slot, slot berikutnya, & status rubrik Fakta Unik Dunia",
)
async def fakta_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = facts_guilds.get(interaction.guild.id)
    if not cfg or not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Rubrik Fakta Unik Dunia belum aktif. Aktifkan dengan "
            f"`/fakta atur channel:#nama-channel jadwal:{','.join(FACTS_DEFAULT_TIMES)}`.",
            ephemeral=True,
        )
        return

    t_ctx = get_realtime_time_context(
        get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    )
    now_minutes = t_ctx["hour"] * 60 + t_ctx["minute"]
    times = cfg.get("times") or list(FACTS_DEFAULT_TIMES)
    sent_today = sent_slots_today(cfg, t_ctx["iso_date"])
    next_slot = next_facts_slot(times, now_minutes=now_minutes)

    sent_text = (
        ", ".join(f"`{slot}`" for slot in sent_today) if sent_today else "_belum ada_"
    )
    pending = [slot for slot in times if slot not in sent_today]
    pending_text = ", ".join(f"`{slot}`" for slot in pending) if pending else "_semua slot hari ini selesai_"
    next_text = (
        f"`{next_slot[0]}` ({describe_slot(next_slot[0])}) — **{next_slot[1]} menit** lagi"
        if next_slot
        else "_tidak ada_"
    )

    await interaction.response.send_message(
        f"🧠 **Status Rubrik Fakta Unik Dunia**\n"
        f"• **Channel:** <#{cfg['channel_id']}>\n"
        f"• **Jadwal Harian:** {format_facts_schedule(times)} {t_ctx['tz_label']} *({len(times)}x sehari)*\n"
        f"• **Sudah Terkirim Hari Ini:** {sent_text}\n"
        f"• **Slot Tersisa:** {pending_text}\n"
        f"• **Slot Berikutnya:** {next_text}\n"
        f"• **Waktu Sekarang:** `{t_ctx['clock']}`",
        ephemeral=True,
    )


# ==============================================================================
# /keamanan — Anti-Phishing Guard
# ==============================================================================
keamanan_group = app_commands.Group(
    name="keamanan",
    description="Proteksi anti-phishing otomatis & cek keamanan sebuah link",
    guild_only=True,
)


@keamanan_group.command(
    name="phising",
    description="Aktifkan/matikan penjaga anti-phishing otomatis di server atau channel tertentu",
)
@app_commands.describe(
    aktif="True untuk mengaktifkan proteksi, False untuk mematikan",
    aksi="Tindakan saat link berbahaya terdeteksi",
    channel="Batasi proteksi ke satu channel (kosongkan = seluruh server)",
    log_channel="Channel untuk mencatat setiap link berbahaya yang diblokir",
    ketat="True = link 'mencurigakan' (mis. pemendek URL) juga ditindak",
)
@app_commands.choices(
    aksi=[
        app_commands.Choice(name="Hapus link + beri peringatan (Rekomendasi)", value="hapus_peringat"),
        app_commands.Choice(name="Hapus link saja (senyap)", value="hapus"),
        app_commands.Choice(name="Peringatkan saja tanpa menghapus", value="peringatkan"),
    ]
)
async def keamanan_phising_cmd(
    interaction: discord.Interaction,
    aktif: bool = True,
    aksi: app_commands.Choice[str] | None = None,
    channel: discord.TextChannel | None = None,
    log_channel: discord.TextChannel | None = None,
    ketat: bool = False,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    action_value = aksi.value if aksi else "hapus_peringat"
    if action_value not in PHISHING_ACTIONS:
        action_value = "hapus_peringat"

    cfg = set_security_config(
        interaction.guild.id,
        enabled=aktif,
        action=action_value,
        log_channel_id=log_channel.id if log_channel else None,
        channel_ids=[channel.id] if channel else [],
        strict=ketat,
    )
    await save_server_features_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            "🛑 **Anti-Phishing Guard** dinonaktifkan. Link berbahaya tidak lagi dipindai.",
            ephemeral=True,
        )
        return

    scope = f"<#{cfg['channel_ids'][0]}>" if cfg.get("channel_ids") else "**seluruh server**"
    log_info = f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "*belum diatur*"
    strict_info = "✅ Aktif (mode ketat)" if cfg.get("strict") else "⚪ Nonaktif"
    await interaction.response.send_message(
        f"🛡️ **Anti-Phishing Guard aktif!**\n"
        f"• **Cakupan:** {scope}\n"
        f"• **Tindakan:** {PHISHING_ACTIONS[cfg['action']]}\n"
        f"• **Log Moderasi:** {log_info}\n"
        f"• **Mode Ketat:** {strict_info}\n"
        f"• **Link sudah diblokir:** `{cfg.get('blocked', 0)}`\n"
        f"> Deteksi berjalan lokal (tanpa API berbayar): tiruan brand, punycode, IP langsung, "
        f"TLD berisiko, pemendek URL, & daftar hitam phishing.",
        ephemeral=True,
    )


@keamanan_group.command(
    name="cek",
    description="Periksa keamanan sebuah link sebelum dibuka (bisa dipakai semua member)",
)
@app_commands.describe(link="Tempel link yang ingin diperiksa")
async def keamanan_cek_cmd(interaction: discord.Interaction, link: str):
    result = analyze_url_risk(link)
    color = {
        "aman": discord.Color.green(),
        "mencurigakan": discord.Color.orange(),
        "berbahaya": discord.Color.red(),
    }.get(result["verdict"], discord.Color.blurple())
    icon = {"aman": "✅", "mencurigakan": "⚠️", "berbahaya": "🚨"}.get(result["verdict"], "🔎")

    embed = discord.Embed(
        title=f"{icon} Hasil Pemeriksaan Link: {result['verdict'].title()}",
        description=f"**Link:** `{result['url'][:400]}`\n**Domain:** `{result['host']}`",
        color=color,
    )
    embed.add_field(
        name=f"📊 Skor Risiko: {result['score']}/100",
        value="\n".join(f"• {r}" for r in result["reasons"][:6])[:1024],
        inline=False,
    )
    embed.set_footer(text="Anti-Phishing Guard • Selalu cek ejaan domain sebelum login")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@keamanan_group.command(
    name="spam",
    description="Aktifkan penjaga anti-spam & anti-raid ringan (default hanya melapor)",
)
@app_commands.describe(
    aktif="True untuk menyalakan, False untuk mematikan penjaga spam",
    mode="Tindakan: lapor (aman) / hapus pesan / timeout member",
    log_channel="Channel untuk menerima laporan anti-spam & peringatan raid",
    ambang_banjir="Jumlah pesan dalam jendela waktu sebelum dianggap flood (3-30)",
    jendela="Jendela waktu (detik) untuk menghitung flood (3-120)",
    mention_maks="Batas mention dalam satu pesan (2-25)",
    link_maks="Batas jumlah link dalam satu pesan (1-10)",
    kapital="True untuk ikut menindak HURUF KAPITAL berlebihan (sering salah tuduh)",
    timeout_detik="Durasi time-out saat mode timeout (60-86400 detik)",
    kecualikan_channel="Channel yang tidak pernah diperiksa",
    kecualikan_role="Role yang tidak pernah diperiksa (mis. role staf)",
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="👀 Lapor ke log saja (aman, tanpa tindakan)", value="lapor"),
        app_commands.Choice(name="🧹 Hapus pesan + catat ke log", value="hapus"),
        app_commands.Choice(name="⏳ Hapus + time-out member sementara", value="timeout"),
    ]
)
async def keamanan_spam_cmd(
    interaction: discord.Interaction,
    aktif: bool = True,
    mode: app_commands.Choice[str] | None = None,
    log_channel: discord.TextChannel | None = None,
    ambang_banjir: app_commands.Range[int, 3, 30] | None = None,
    jendela: app_commands.Range[int, 3, 120] | None = None,
    mention_maks: app_commands.Range[int, 2, 25] | None = None,
    link_maks: app_commands.Range[int, 1, 10] | None = None,
    kapital: bool | None = None,
    timeout_detik: app_commands.Range[int, 60, 86400] | None = None,
    kecualikan_channel: discord.TextChannel | None = None,
    kecualikan_role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not aktif:
        cfg = set_spam_config(interaction.guild.id, aktif=False)
        await save_antispam_to_disk()
        await interaction.response.send_message(
            "🛑 **Penjaga Anti-Spam dimatikan.** Bot tidak lagi memeriksa pesan warga."
            if cfg is None
            else "ℹ️ Penjaga Anti-Spam memang belum aktif.",
            ephemeral=True,
        )
        return

    existing = get_spam_config(interaction.guild.id)
    changes: dict = {"aktif": True}
    if mode is not None:
        changes["mode"] = mode.value
    if log_channel is not None:
        changes["log_channel_id"] = log_channel.id
    if ambang_banjir is not None:
        changes["flood_count"] = int(ambang_banjir)
    if jendela is not None:
        changes["flood_window"] = int(jendela)
    if mention_maks is not None:
        changes["mention_limit"] = int(mention_maks)
    if link_maks is not None:
        changes["link_limit"] = int(link_maks)
    if kapital is not None:
        changes["caps_enabled"] = bool(kapital)
    if timeout_detik is not None:
        changes["timeout_sec"] = int(timeout_detik)
    if kecualikan_channel is not None:
        changes["exempt_channels"] = sorted(
            set(existing.get("exempt_channels") or []) | {kecualikan_channel.id}
        )
    if kecualikan_role is not None:
        changes["exempt_roles"] = sorted(
            set(existing.get("exempt_roles") or []) | {kecualikan_role.id}
        )

    cfg = set_spam_config(interaction.guild.id, **changes) or get_spam_config(interaction.guild.id)
    await save_antispam_to_disk()

    log_info = f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "*belum diatur*"
    warn = (
        "\n> ⚠️ **Mode lapor** hanya mencatat ke channel log — tidak ada pesan yang dihapus. "
        "Ubah ke `mode:hapus` setelah yakin."
        if cfg.get("mode") == "lapor"
        else ""
    )
    await interaction.response.send_message(
        f"🛡️ **Penjaga Anti-Spam aktif!**\n"
        f"• **Mode:** {SPAM_MODES.get(cfg['mode'], SPAM_MODES['lapor'])}\n"
        f"• **Log moderasi:** {log_info}\n"
        f"• **Flood:** `{cfg['flood_count']}` pesan / `{cfg['flood_window']}` detik\n"
        f"• **Mention massal:** `{cfg['mention_limit']}` • **Link:** `{cfg['link_limit']}`\n"
        f"• **Huruf kapital:** {'✅ aktif' if cfg.get('caps_enabled') else '⛔ nonaktif'}\n"
        f"• **Anti-Raid:** lapor otomatis (tidak menendang)\n"
        f"> Admin, pengurus, & role pengecualian **tidak pernah** diperiksa.{warn}",
        ephemeral=True,
    )


@keamanan_group.command(
    name="spam-status",
    description="Lihat konfigurasi & statistik penjaga anti-spam server ini",
)
async def keamanan_spam_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    await interaction.response.send_message(
        embed=build_spam_status_embed(interaction.guild.id, interaction.guild),
        ephemeral=True,
    )


def register_server_cog(bot: commands.Bot) -> None:
    """Mendaftarkan seluruh command fitur server ke bot."""
    bot.tree.add_command(serverstats_group)
    bot.tree.add_command(autorole_group)
    bot.tree.add_command(fakta_group)
    bot.tree.add_command(keamanan_group)
