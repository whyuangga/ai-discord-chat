"""Command Slash Tier 2C: `/level` (Leveling & XP) dan `/tiket` (Tiket Dukungan).

Keduanya berjalan **tanpa kuota Gemini** dan default NONAKTIF sampai Admin
menyalakannya. Tiket dibuat sebagai **private thread** sehingga tidak memakan
slot channel server.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import levels
import tickets
from config import (
    LEVELS_COOLDOWN_SEC,
    LEVELS_MAX_LEVEL,
    LEVELS_MAX_MEMBERS,
    TICKET_MAX_OPEN_PER_USER,
)
from views import send_ticket_panel

logger = logging.getLogger("gemini_bot.growth_cog")


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.",
        ephemeral=True,
    )


# ==============================================================================
# /level — LEVELING & XP
# ==============================================================================
level_group = app_commands.Group(
    name="level",
    description="Level & XP member: lihat kartu level, papan peringkat, & atur hadiah role",
    guild_only=True,
)


@level_group.command(name="lihat", description="Lihat kartu level & XP kamu (atau member lain)")
@app_commands.describe(member="Member yang ingin dilihat (kosongkan untuk dirimu sendiri)")
async def level_lihat_cmd(interaction: discord.Interaction, member: discord.Member | None = None):
    if interaction.guild is None:
        return

    target = member or interaction.user
    cfg = levels.get_level_config(interaction.guild.id)
    if not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Fitur leveling belum aktif di server ini. "
            "Admin bisa menyalakannya dengan `/level atur aktif:True`.",
            ephemeral=True,
        )
        return

    data = levels.get_member_level(interaction.guild.id, target.id)
    await interaction.response.send_message(
        embed=levels.build_level_embed(target, data, cfg),
        ephemeral=True,
    )


@level_group.command(name="papan", description="Papan peringkat level server (top member paling aktif)")
@app_commands.describe(halaman="Halaman papan peringkat (default 1)")
async def level_papan_cmd(interaction: discord.Interaction, halaman: int = 1):
    if interaction.guild is None:
        return

    cfg = levels.get_level_config(interaction.guild.id)
    if not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Fitur leveling belum aktif di server ini.", ephemeral=True
        )
        return

    page_size = 10
    rows, page, total_pages = levels.leaderboard(
        interaction.guild.id, limit=page_size, page=max(0, int(halaman) - 1)
    )
    total_members = sum(
        1 for key in levels.levels if key.startswith(f"{interaction.guild.id}:")
    )
    await interaction.response.send_message(
        embed=levels.build_leaderboard_embed(
            interaction.guild,
            rows,
            page=page,
            total_pages=total_pages,
            total_members=total_members,
            page_size=page_size,
        )
    )


@level_group.command(name="atur", description="Aktifkan leveling & atur XP, jeda, pengumuman, & channel abaikan")
@app_commands.describe(
    aktif="False untuk mematikan sistem level (data XP tetap tersimpan)",
    pengumuman="True untuk mengumumkan saat ada member naik level",
    channel_pengumuman="Channel khusus pengumuman naik level (kosongkan = balas di channel asal)",
    jeda="Jeda minimum antar XP per member dalam detik (0-3600)",
    xp_minimal="XP minimum per pesan (1-100)",
    xp_maksimal="XP maksimum per pesan (1-100)",
    abaikan_channel="Channel yang tidak memberikan XP (mis. #spam)",
    abaikan_role="Role yang tidak mendapatkan XP (mis. bot/role khusus)",
)
async def level_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool = True,
    pengumuman: bool | None = None,
    channel_pengumuman: discord.TextChannel | None = None,
    jeda: app_commands.Range[int, 0, 3600] | None = None,
    xp_minimal: app_commands.Range[int, 1, 100] | None = None,
    xp_maksimal: app_commands.Range[int, 1, 100] | None = None,
    abaikan_channel: discord.TextChannel | None = None,
    abaikan_role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not aktif:
        levels.disable_leveling(interaction.guild.id)
        await levels.save_levels_to_disk()
        await interaction.response.send_message(
            "🛑 **Sistem level dimatikan.** Data XP lama tetap tersimpan.",
            ephemeral=True,
        )
        return

    existing = levels.get_level_config(interaction.guild.id)
    changes: dict = {"aktif": True}
    if pengumuman is not None:
        changes["announce"] = bool(pengumuman)
    if channel_pengumuman is not None:
        changes["announce_channel_id"] = channel_pengumuman.id
    if jeda is not None:
        changes["cooldown"] = int(jeda)
    if xp_minimal is not None:
        changes["xp_min"] = int(xp_minimal)
    if xp_maksimal is not None:
        changes["xp_max"] = int(xp_maksimal)
    if abaikan_channel is not None:
        changes["ignore_channels"] = sorted(
            set(existing.get("ignore_channels") or []) | {abaikan_channel.id}
        )
    if abaikan_role is not None:
        changes["ignore_roles"] = sorted(
            set(existing.get("ignore_roles") or []) | {abaikan_role.id}
        )

    cfg = levels.set_level_config(interaction.guild.id, **changes) or levels.get_level_config(
        interaction.guild.id
    )
    await levels.save_levels_to_disk()

    announce_channel = cfg.get("announce_channel_id")
    await interaction.response.send_message(
        f"✅ **Sistem level aktif!**\n"
        f"• **XP per pesan:** `{cfg['xp_min']}–{cfg['xp_max']}`\n"
        f"• **Jeda per member:** `{cfg['cooldown']}` detik\n"
        f"• **Pengumuman naik level:** {'✅ aktif' if cfg.get('announce') else '⛔ nonaktif'}\n"
        f"• **Channel pengumuman:** {f'<#{announce_channel}>' if announce_channel else '_di channel asal_'}\n"
        f"• **Channel diabaikan:** `{len(cfg.get('ignore_channels') or [])}` • "
        f"**Role diabaikan:** `{len(cfg.get('ignore_roles') or [])}`\n"
        f"> Beri hadiah role dengan `/level role level:5 role:@Aktif`.",
        ephemeral=True,
    )


@level_group.command(name="role", description="Atur role hadiah yang otomatis diberikan saat member mencapai level tertentu")
@app_commands.describe(
    level="Level yang memicu pemberian role (1-100)",
    role="Role yang diberikan (kosongkan untuk menghapus hadiah level ini)",
)
async def level_role_cmd(
    interaction: discord.Interaction,
    level: app_commands.Range[int, 1, 100],
    role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    cfg = levels.set_level_role(interaction.guild.id, int(level), role.id if role else None)
    await levels.save_levels_to_disk()
    mapping = cfg.get("level_roles") or {}
    preview = ", ".join(
        f"L{v}→<@&{rid}>" for v, rid in sorted(mapping.items(), key=lambda kv: int(kv[0]))[:8]
    )
    await interaction.response.send_message(
        (
            f"🎁 Level **{int(level)}** kini memberi {role.mention}."
            if role
            else f"🗑️ Hadiah role untuk level **{int(level)}** dihapus."
        )
        + (f"\n**Peta hadiah saat ini:** {preview}" if preview else "\n_Belum ada hadiah role._"),
        ephemeral=True,
    )


@level_group.command(name="status", description="Lihat konfigurasi & statistik sistem level server ini")
async def level_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = levels.level_guilds.get(interaction.guild.id)
    if not cfg or not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ **Leveling NONAKTIF.** Aktifkan dengan `/level atur aktif:True`.",
            ephemeral=True,
        )
        return

    members = [key for key in levels.levels if key.startswith(f"{interaction.guild.id}:")]
    top_xp = max(
        (int(levels.levels[key].get("xp") or 0) for key in members), default=0
    )
    mapping = cfg.get("level_roles") or {}
    roles_preview = ", ".join(f"L{v}" for v in sorted(mapping, key=lambda v: int(v))[:10]) or "_belum ada_"
    await interaction.response.send_message(
        f"📈 **Sistem Level Aktif**\n"
        f"• **XP per pesan:** `{cfg['xp_min']}–{cfg['xp_max']}` (jeda `{cfg['cooldown']}` dtk)\n"
        f"• **Member terdata:** `{len(members)}` (maks `{LEVELS_MAX_MEMBERS}` per server)\n"
        f"• **XP tertinggi:** `{top_xp}`\n"
        f"• **Naik level total:** `{cfg.get('leveled_up', 0)}` kali\n"
        f"• **Pengumuman:** {'✅ aktif' if cfg.get('announce') else '⛔ nonaktif'}\n"
        f"• **Hadiah role:** {roles_preview}\n"
        f"• **Batas level:** `{LEVELS_MAX_LEVEL}` • **Jeda default:** `{LEVELS_COOLDOWN_SEC}` dtk",
        ephemeral=True,
    )


async def handle_message_xp(bot: commands.Bot, message) -> None:
    """Memberi XP untuk pesan biasa & mengumumkan kenaikan level (dipanggil dari events)."""
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    if guild is None or author is None or channel is None:
        return
    if getattr(author, "bot", False):
        return
    if not levels.is_leveling_active(guild.id):
        return

    role_ids = {getattr(role, "id", 0) for role in (getattr(author, "roles", None) or [])}
    result = levels.add_message_xp(
        guild.id,
        author.id,
        channel_id=getattr(channel, "id", 0),
        role_ids=role_ids,
    )
    if result is None:
        return

    await levels.save_levels_to_disk()
    if not result.get("level_up"):
        return

    cfg = levels.get_level_config(guild.id)
    if result.get("role_id"):
        await levels.apply_level_role(author, int(result["role_id"]))

    if not cfg.get("announce"):
        return

    target_channel = channel
    announce_id = cfg.get("announce_channel_id")
    if announce_id:
        get_channel = getattr(bot, "get_channel", None)
        if callable(get_channel):
            target_channel = get_channel(int(announce_id)) or channel

    reward = f"\n🎁 Role baru: <@&{result['role_id']}>" if result.get("role_id") else ""
    try:
        await target_channel.send(
            f"🎉 <@{author.id}> naik ke **level {result['level']}**!{reward}",
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
    except (discord.Forbidden, discord.HTTPException):
        pass


# ==============================================================================
# /tiket — TIKET DUKUNGAN
# ==============================================================================
tiket_group = app_commands.Group(
    name="tiket",
    description="Sistem tiket bantuan berbasis thread privat (tanpa kuota AI)",
    guild_only=True,
)


@tiket_group.command(name="panel", description="Pasang panel 'Buat Tiket' di sebuah channel bantuan")
@app_commands.describe(
    channel="Channel tempat panel tiket dipasang (default: channel ini)",
    staff_role="Role petugas yang diberi akses ke setiap tiket",
    log_channel="Channel untuk menerima transkrip tiket yang ditutup",
    max_open="Batas tiket aktif per member (1-10)",
)
async def tiket_panel_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    staff_role: discord.Role | None = None,
    log_channel: discord.TextChannel | None = None,
    max_open: app_commands.Range[int, 1, 10] | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = channel or interaction.channel
    if target is None or not hasattr(target, "send"):
        await interaction.response.send_message("⚠️ Pilih `channel` text channel untuk panel tiket.", ephemeral=True)
        return

    cfg = tickets.set_ticket_config(
        interaction.guild.id,
        enabled=True,
        panel_channel_id=target.id,
        staff_role_id=staff_role.id if staff_role else None,
        log_channel_id=log_channel.id if log_channel else None,
        max_open=int(max_open) if max_open else None,
    )
    await interaction.response.defer(ephemeral=True)

    try:
        message = await send_ticket_panel(
            target,
            interaction.guild.id,
            tickets.build_panel_embed(interaction.guild.name, staff_role_id=cfg.get("staff_role_id")),
        )
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim panel ke {target.mention}. Cek izin **Kirim Pesan** & **Embed Links**.",
            ephemeral=True,
        )
        return

    tickets.set_ticket_config(
        interaction.guild.id, panel_message_id=message.id, enabled=True
    )
    await tickets.save_tickets_to_disk()

    staff_info = f"<@&{cfg['staff_role_id']}>" if cfg.get("staff_role_id") else "_belum diatur_"
    log_info = f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_belum diatur_"
    await interaction.followup.send(
        f"🎟️ **Panel tiket aktif di {target.mention}!**\n"
        f"• **Role staf:** {staff_info}\n"
        f"• **Log transkrip:** {log_info}\n"
        f"• **Batas tiket per member:** `{cfg.get('max_open', TICKET_MAX_OPEN_PER_USER)}`\n"
        f"> Member klik **🎟️ Buat Tiket** → bot membuat **private thread** (tidak memakai slot channel).",
        ephemeral=True,
    )


@tiket_group.command(name="status", description="Lihat konfigurasi, statistik, & daftar tiket aktif")
async def tiket_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    await interaction.response.send_message(
        embed=tickets.build_ticket_status_embed(interaction.guild.id, interaction.guild),
        ephemeral=True,
    )


@tiket_group.command(name="tutup", description="Tutup tiket di thread ini & kirim transkrip ke channel log")
async def tiket_tutup_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    data = tickets.get_ticket(interaction.channel_id)
    if data is None:
        await interaction.response.send_message(
            "⚠️ Command ini hanya bisa dipakai **di dalam thread tiket**.", ephemeral=True
        )
        return

    perms = getattr(interaction.user, "guild_permissions", None)
    cfg = tickets.get_ticket_config(interaction.guild.id)
    roles = {getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])}
    is_staff = bool(
        perms
        and (
            getattr(perms, "administrator", False)
            or getattr(perms, "manage_threads", False)
            or getattr(perms, "manage_channels", False)
        )
    ) or (bool(cfg.get("staff_role_id")) and int(cfg["staff_role_id"]) in roles)
    if not is_staff and int(data.get("user_id") or 0) != interaction.user.id:
        await interaction.response.send_message(
            "⚠️ Hanya **pembuat tiket** atau **staf** yang bisa menutup tiket ini.", ephemeral=True
        )
        return

    await interaction.response.defer()
    messages = await tickets.collect_thread_messages(interaction.channel)
    status, closed = tickets.close_ticket(interaction.channel_id, interaction.user.id)
    if closed is None:
        await interaction.followup.send("ℹ️ Tiket ini sudah ditutup sebelumnya.", ephemeral=True)
        return

    await tickets.save_tickets_to_disk()
    text, filename = tickets.build_transcript(closed, messages)
    sent = await tickets.send_transcript(interaction.client, closed, text, filename)

    try:
        await interaction.channel.edit(
            name=f"tiket-{int(closed.get('number') or 0):04d}-selesai"[:100],
            locked=True,
            archived=True,
            reason=f"Tiket ditutup lewat /tiket tutup oleh {interaction.user}",
        )
    except (discord.Forbidden, discord.HTTPException):
        pass

    await interaction.followup.send(
        f"🔒 Tiket **#{int(closed.get('number') or 0):04d}** ditutup."
        + (" Transkrip dikirim ke channel log." if sent else " (Channel log transkrip belum diatur.)")
    )


@tiket_group.command(name="tambah", description="Tambahkan member lain ke tiket ini (mis. saksi atau pihak terkait)")
@app_commands.describe(member="Member yang ingin ditambahkan ke thread tiket")
async def tiket_tambah_cmd(interaction: discord.Interaction, member: discord.Member):
    if interaction.guild is None:
        return
    data = tickets.get_ticket(interaction.channel_id)
    if data is None:
        await interaction.response.send_message(
            "⚠️ Command ini hanya bisa dipakai di dalam thread tiket.", ephemeral=True
        )
        return

    perms = getattr(interaction.user, "guild_permissions", None)
    cfg = tickets.get_ticket_config(interaction.guild.id)
    roles = {getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])}
    is_staff = bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_threads", False))) or (
        bool(cfg.get("staff_role_id")) and int(cfg["staff_role_id"]) in roles
    )
    if not is_staff:
        await interaction.response.send_message("⚠️ Hanya staf yang bisa menambah member.", ephemeral=True)
        return

    try:
        await interaction.channel.add_user(member)
    except (discord.Forbidden, discord.HTTPException):
        await interaction.response.send_message(
            "⚠️ Gagal menambahkan member. Pastikan bot punya izin **Manage Threads**.",
            ephemeral=True,
        )
        return

    tickets.add_user_to_ticket(interaction.channel_id, member.id)
    await tickets.save_tickets_to_disk()
    await interaction.response.send_message(
        f"➕ {member.mention} ditambahkan ke tiket ini.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@tiket_group.command(name="daftar", description="Lihat tiket yang masih aktif di server ini")
@app_commands.describe(hanya_milikku="True untuk hanya menampilkan tiket yang kamu buat")
async def tiket_daftar_cmd(interaction: discord.Interaction, hanya_milikku: bool = False):
    if interaction.guild is None:
        return

    items = tickets.list_tickets(interaction.guild.id, limit=15)
    if hanya_milikku:
        items = [data for data in items if int(data.get("user_id") or 0) == interaction.user.id]
    active = [data for data in items if data.get("status") in ("terbuka", "diklaim")]
    if not active:
        await interaction.response.send_message(
            "ℹ️ Tidak ada tiket aktif. Buka lewat tombol **🎟️ Buat Tiket** di panel bantuan.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🎟️ Tiket Aktif",
        color=discord.Color.blurple(),
        description=f"`{len(active)}` tiket menunggu/ditangani",
    )
    for data in active[:10]:
        embed.add_field(
            name=f"#{int(data.get('number') or 0):04d} • {tickets.TICKET_STATUS.get(data.get('status'), '-')}",
            value=(
                f"<@{data['user_id']}> • <#{data['thread_id']}>\n"
                f"> {str(data.get('topic') or '_tanpa topik_')[:120]}"
            ),
            inline=False,
        )
    embed.set_footer(text="Staf: gunakan tombol 🙋 Klaim / 🔒 Tutup di dalam thread tiket")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tiket_group.command(name="matikan", description="Matikan sistem tiket (panel lama tidak lagi membuat tiket baru)")
async def tiket_matikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    changed = tickets.disable_tickets(interaction.guild.id)
    await tickets.save_tickets_to_disk()
    await interaction.response.send_message(
        "🛑 **Sistem tiket dimatikan.** Thread tiket lama tetap bisa dibaca & ditutup."
        if changed
        else "ℹ️ Sistem tiket memang belum aktif.",
        ephemeral=True,
    )


def register_growth_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command /level & /tiket ke bot."""
    bot.tree.add_command(level_group)
    bot.tree.add_command(tiket_group)
