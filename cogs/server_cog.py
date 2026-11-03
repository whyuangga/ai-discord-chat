import logging

import discord
from discord import app_commands
from discord.ext import commands

from community_agent import parse_digest_time
from cogs.helpers import get_interaction_http_session
from server_features import (
    PHISHING_ACTIONS,
    analyze_url_risk,
    backfill_autoroles,
    build_facts_embed,
    build_facts_fallback,
    build_serverstats_embed,
    facts_guilds,
    generate_daily_facts,
    get_autorole_role_ids,
    save_server_features_to_disk,
    serverstats_guilds,
    set_autorole_config,
    set_facts_config,
    set_security_config,
    set_serverstats_config,
    update_serverstats_channels,
)
from utils import get_realtime_time_context
from config import BOT_TIMEZONE, FACTS_DEFAULT_HOUR, FACTS_DEFAULT_MINUTE
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

    await interaction.followup.send(
        f"📊 **Server Stats Otomatis aktif!**\n"
        f"• **{changed} Voice Channel** statistik dibuat/diperbarui di kategori `📊 Statistik Server`.\n"
        f"• Statistik akan **disinkronkan otomatis setiap ±10 menit** (aman dari rate limit Discord).\n"
        f"• Warga tidak bisa masuk ke channel penghitung tersebut.",
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
        f"\n\nSaat member baru bergabung, role ini otomatis terpasang tanpa perlu verifikasi manual."
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
# /fakta — Rubrik Fakta Unik Dunia Harian (08:00)
# ==============================================================================
fakta_group = app_commands.Group(
    name="fakta",
    description="Rubrik Fakta Unik Dunia otomatis setiap pagi pukul 08:00",
    guild_only=True,
)


@fakta_group.command(
    name="atur",
    description="Atur channel & jam pengiriman rubrik Fakta Unik Dunia harian",
)
@app_commands.describe(
    channel="Channel tujuan pengiriman fakta unik harian",
    aktif="True untuk mengaktifkan jadwal, False untuk mematikan",
    jam="Jam kirim format HH:MM (default 08:00)",
)
async def fakta_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool = True,
    jam: str | None = "08:00",
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    parsed = parse_digest_time(jam) or (FACTS_DEFAULT_HOUR, FACTS_DEFAULT_MINUTE)
    hour, minute = parsed

    cfg = set_facts_config(
        interaction.guild.id, channel.id, enabled=aktif, hour=hour, minute=minute
    )
    await save_server_features_to_disk()

    if not aktif or cfg is None:
        await interaction.response.send_message(
            "🛑 **Rubrik Fakta Unik Dunia** dinonaktifkan di server ini.", ephemeral=True
        )
        return

    t_ctx = get_realtime_time_context(
        get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    )
    await interaction.response.send_message(
        f"🧠 **Fakta Unik Dunia aktif di {channel.mention}!**\n"
        f"• **Jadwal:** setiap hari pukul **`{cfg['hour']:02d}:{cfg['minute']:02d} {t_ctx['tz_label']}`**\n"
        f"• **Isi:** 3–4 fakta menarik dari negara berbeda (bendera + nama negara).\n"
        f"• **Anti-bosan:** fakta hari sebelumnya tidak akan diulang.\n"
        f"• Minta contoh sekarang dengan `/fakta sekarang`.",
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
        "Jadwal harian tetap aktif."
        if schedule_was_active
        else "Jadwal harian belum aktif — pasang dengan `/fakta atur channel:#nama-channel jam:08:00`."
    )
    await interaction.followup.send(
        f"✅ Contoh Fakta Unik Dunia terkirim ke {target.mention}!{note}\n{schedule_note}",
        ephemeral=True,
    )


@fakta_group.command(
    name="status",
    description="Lihat status & jadwal rubrik Fakta Unik Dunia server ini",
)
async def fakta_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = facts_guilds.get(interaction.guild.id)
    if not cfg or not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Rubrik Fakta Unik Dunia belum aktif. Aktifkan dengan `/fakta atur channel:#nama-channel`.",
            ephemeral=True,
        )
        return

    t_ctx = get_realtime_time_context(
        get_guild_settings(interaction.guild.id).get("timezone", BOT_TIMEZONE)
    )
    await interaction.response.send_message(
        f"🧠 **Rubrik Fakta Unik Dunia**\n"
        f"• **Channel:** <#{cfg['channel_id']}>\n"
        f"• **Jadwal:** setiap hari pukul **`{cfg['hour']:02d}:{cfg['minute']:02d} {t_ctx['tz_label']}`**\n"
        f"• **Terakhir terkirim:** `{cfg.get('last_sent_date') or 'belum pernah'}`",
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


def register_server_cog(bot: commands.Bot) -> None:
    """Mendaftarkan seluruh command fitur server ke bot."""
    bot.tree.add_command(serverstats_group)
    bot.tree.add_command(autorole_group)
    bot.tree.add_command(fakta_group)
    bot.tree.add_command(keamanan_group)
