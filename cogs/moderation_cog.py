"""Cog `/mod` — moderasi bercatatan (warn, timeout, kick, ban, purge) ala Dyno/Carl-bot.

Semua aksi tercatat di `data/moderation.json` dan bisa dilihat lewat `/mod catatan`.
Auto-punish: setelah N `warn` (default 3 dalam 30 hari), bot otomatis memberi timeout
(default 60 menit) — bisa diatur lewat `/mod atur`.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import moderation as mod
import ui_theme

logger = logging.getLogger("gemini_bot.moderation_cog")

# Warna embed log per jenis aksi (membantu staff memindai channel log)
ACTION_COLORS: dict[str, int] = {
    "warn": 0xF1C40F,
    "timeout": 0xE67E22,
    "kick": 0x95A5A6,
    "ban": 0xE74C3C,
    "unban": 0x2ECC71,
    "unmute": 0x3498DB,
    "note": 0x9B59B6,
}

mod_group = app_commands.Group(
    name="mod",
    description="Moderasi bercatatan: peringatan, timeout, kick, ban, purge, & riwayat kasus",
    default_permissions=discord.Permissions(moderate_members=True),
    guild_only=True,
)


def _is_staff(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    if perms is None:
        return False
    return bool(
        getattr(perms, "administrator", False)
        or getattr(perms, "moderate_members", False)
        or getattr(perms, "kick_members", False)
        or getattr(perms, "ban_members", False)
        or getattr(perms, "manage_messages", False)
    )


async def _reject(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id if interaction.guild else None,
            "error",
            "Butuh Izin Staff",
            "Command ini khusus **staff** (butuh izin *Moderate Members* atau *Manage Messages*).",
        ),
        ephemeral=True,
    )


def _hierarchy_problem(guild: discord.Guild, target: discord.Member) -> str | None:
    """Mengembalikan alasan bila bot tidak boleh menindak member ini."""
    me = guild.me
    if me is None:
        return "Bot tidak berada di server ini."
    if target.id == guild.owner_id:
        return "Tidak bisa menindak **pemilik server**."
    if target.id == me.id:
        return "Tidak bisa menindak bot sendiri."
    if getattr(target, "guild_permissions", None) and target.guild_permissions.administrator:
        return f"{target.mention} adalah **Administrator** — cabut izinnya dulu bila memang perlu."
    if target.top_role >= me.top_role:
        return (
            f"Role {target.mention} lebih tinggi/sama dengan role bot. "
            "Naikkan posisi role bot di Server Settings → Roles."
        )
    return None


def _log_embed(guild: discord.Guild, case: dict, target: discord.abc.User, moderator: discord.abc.User) -> discord.Embed:
    meta = mod.ACTIONS.get(str(case.get("action")), {"emoji": "•", "label": "Aksi"})
    embed = discord.Embed(
        title=f"{meta['emoji']} {meta['label']} — kasus #{case['id']}",
        colour=discord.Colour(ACTION_COLORS.get(str(case.get("action")), 0x9B59B6)),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Member", value=f"{target} (`{target.id}`)", inline=True)
    embed.add_field(name="Moderator", value=f"{moderator}", inline=True)
    embed.add_field(name="Alasan", value=(case.get("reason") or "_tanpa alasan_")[:1024], inline=False)
    if case.get("duration_sec"):
        embed.add_field(name="Durasi", value=mod.format_duration(case["duration_sec"]), inline=True)
    ui_theme.apply_embed_theme(embed, guild.id, footer=f"Kasus #{case['id']} • {guild.name}")
    return embed


async def _announce(
    interaction: discord.Interaction,
    case: dict,
    target: discord.abc.User,
    *,
    extra: str = "",
) -> None:
    """Kirim DM ke member (opsional) + laporan ke channel log moderasi."""
    guild = interaction.guild
    if guild is None:
        return
    settings = mod.get_settings(guild.id)
    meta = mod.ACTIONS.get(str(case.get("action")), {"emoji": "•", "label": "Aksi"})

    if settings.get("dm_user", True) and not getattr(target, "bot", False):
        try:
            await target.send(
                f"{meta['emoji']} **{meta['label']}** di **{guild.name}**\n"
                f"Alasan: {case.get('reason') or 'tidak disebutkan'}"
                + (f"\nDurasi: {mod.format_duration(case.get('duration_sec'))}" if case.get("duration_sec") else "")
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    log_id = settings.get("log_channel")
    if log_id:
        channel = guild.get_channel(int(log_id))
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(
                    embed=_log_embed(guild, case, target, interaction.user),
                    content=extra or None,
                )
            except (discord.Forbidden, discord.HTTPException):
                logger.info("Tidak bisa mengirim log moderasi ke %s", log_id)


async def _apply_auto_punish(guild: discord.Guild, target: discord.Member) -> dict | None:
    """Memberi timeout otomatis bila ambang warn tercapai. `None` bila belum/tidak bisa."""
    escalate, minutes = mod.should_auto_punish(guild.id, target.id)
    if not escalate:
        return None
    problem = _hierarchy_problem(guild, target)
    if problem:
        return None
    try:
        await target.timeout(
            discord.utils.utcnow() + discord.timedelta(minutes=minutes),
            reason=f"Auto-punish: {mod.get_settings(guild.id)['warn_threshold']} peringatan aktif",
        )
    except (discord.Forbidden, discord.HTTPException):
        return None
    return mod.add_case(
        guild.id,
        target.id,
        guild.me.id if guild.me else 0,
        "timeout",
        f"Otomatis: {mod.get_settings(guild.id)['warn_threshold']} peringatan tercapai",
        duration_sec=minutes * 60,
    )


# ==============================================================================
# COMMAND
# ==============================================================================
@mod_group.command(name="warn", description="Beri peringatan resmi (tercatat) ke member")
@app_commands.describe(member="Member yang diperingatkan", alasan="Alasan peringatan")
async def mod_warn_cmd(interaction: discord.Interaction, member: discord.Member, alasan: str):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)
    problem = _hierarchy_problem(interaction.guild, member)
    if problem:
        await interaction.response.send_message(f"⚠️ {problem}", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("⚠️ Member ini bot.", ephemeral=True)
        return

    case = mod.add_case(interaction.guild.id, member.id, interaction.user.id, "warn", alasan)
    auto = await _apply_auto_punish(interaction.guild, member)
    await mod.save_moderation_to_disk()
    await _announce(interaction, case, member)

    total = mod.count_warns(interaction.guild.id, member.id)
    threshold = mod.get_settings(interaction.guild.id)["warn_threshold"]
    text = (
        f"⚠️ **Peringatan tercatat** — kasus `#{case['id']}`\n"
        f"• Member: {member.mention}\n"
        f"• Alasan: {alasan}\n"
        f"• Peringatan aktif: **{total}**"
    )
    if threshold:
        text += f" / {threshold} (auto-timeout)"
    if auto is not None:
        text += f"\n🔇 **Auto-punish:** timeout {mod.format_duration(auto['duration_sec'])} (kasus `#{auto['id']}`)"
    elif threshold and total >= threshold:
        text += "\n⚠️ Ambang tercapai, tetapi auto-timeout gagal (cek hierarki role bot)."

    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="⚠️ Peringatan", description=text[:4000]), interaction.guild.id
        ),
        ephemeral=True,
    )


@mod_group.command(name="timeout", description="Bisukan member sementara (timeout Discord native)")
@app_commands.describe(member="Member yang di-timeout", durasi="Contoh: 10m, 1h30m, 2d", alasan="Alasan")
async def mod_timeout_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    durasi: str = "10m",
    alasan: str = "Tidak disebutkan",
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)
    problem = _hierarchy_problem(interaction.guild, member)
    if problem:
        await interaction.response.send_message(f"⚠️ {problem}", ephemeral=True)
        return

    seconds = min(mod.parse_duration(durasi), 28 * 86400)
    try:
        await member.timeout(
            discord.utils.utcnow() + discord.timedelta(seconds=seconds), reason=alasan[:400]
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(
            f"⚠️ Gagal memberi timeout: {exc}", ephemeral=True
        )
        return

    case = mod.add_case(interaction.guild.id, member.id, interaction.user.id, "timeout", alasan, duration_sec=seconds)
    await mod.save_moderation_to_disk()
    await _announce(interaction, case, member)
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Timeout Diterapkan",
            f"{member.mention} dibisukan selama **{mod.format_duration(seconds)}**\n"
            f"• Alasan: {alasan}\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


@mod_group.command(name="kick", description="Keluarkan member dari server (bisa kembali lagi)")
@app_commands.describe(member="Member yang dikeluarkan", alasan="Alasan kick")
async def mod_kick_cmd(interaction: discord.Interaction, member: discord.Member, alasan: str = "Tidak disebutkan"):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)
    problem = _hierarchy_problem(interaction.guild, member)
    if problem:
        await interaction.response.send_message(f"⚠️ {problem}", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        await member.kick(reason=alasan[:400])
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal kick: {exc}", ephemeral=True)
        return

    case = mod.add_case(interaction.guild.id, member.id, interaction.user.id, "kick", alasan)
    await mod.save_moderation_to_disk()
    await _announce(interaction, case, member)
    await interaction.followup.send(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Member Dikeluarkan",
            f"**{member}** (`{member.id}`) di-kick.\n• Alasan: {alasan}\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


@mod_group.command(name="ban", description="Ban member (opsional hapus pesan beberapa hari terakhir)")
@app_commands.describe(
    member="Member (atau ID) yang diban",
    alasan="Alasan ban",
    hapus_pesan_hari="Hapus pesan N hari terakhir (0–7)",
)
async def mod_ban_cmd(
    interaction: discord.Interaction,
    member: discord.User,
    alasan: str = "Tidak disebutkan",
    hapus_pesan_hari: app_commands.Range[int, 0, 7] = 0,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    target_member = interaction.guild.get_member(member.id)
    if target_member is not None:
        problem = _hierarchy_problem(interaction.guild, target_member)
        if problem:
            await interaction.response.send_message(f"⚠️ {problem}", ephemeral=True)
            return

    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.guild.ban(
            member, reason=alasan[:400], delete_message_days=int(hapus_pesan_hari or 0)
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal ban: {exc}", ephemeral=True)
        return

    case = mod.add_case(interaction.guild.id, member.id, interaction.user.id, "ban", alasan)
    await mod.save_moderation_to_disk()
    await _announce(interaction, case, member)
    await interaction.followup.send(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Member Diban",
            f"**{member}** (`{member.id}`) diban.\n• Alasan: {alasan}\n• Kasus: `#{case['id']}`"
            + (f"\n• Pesan dihapus: {hapus_pesan_hari} hari terakhir" if hapus_pesan_hari else ""),
        ),
        ephemeral=True,
    )


@mod_group.command(name="unban", description="Cabut ban member berdasarkan ID")
@app_commands.describe(user_id="ID Discord member", alasan="Alasan pencabutan ban")
async def mod_unban_cmd(interaction: discord.Interaction, user_id: str, alasan: str = "Tidak disebutkan"):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    try:
        target_id = int(str(user_id).strip())
    except ValueError:
        await interaction.response.send_message("⚠️ ID tidak valid (harus angka).", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        user = await interaction.client.fetch_user(target_id)
        await interaction.guild.unban(user, reason=alasan[:400])
    except discord.NotFound:
        await interaction.followup.send("⚠️ Member itu tidak sedang diban.", ephemeral=True)
        return
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal unban: {exc}", ephemeral=True)
        return

    case = mod.add_case(interaction.guild.id, target_id, interaction.user.id, "unban", alasan)
    await mod.save_moderation_to_disk()
    await interaction.followup.send(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Ban Dicabut",
            f"**{user}** (`{user.id}`) sudah bisa bergabung lagi.\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


@mod_group.command(name="purge", description="Hapus banyak pesan sekaligus (bisa difilter)")
@app_commands.describe(
    jumlah="Berapa pesan terakhir yang diperiksa (1–100)",
    member="Hanya hapus pesan dari member ini (opsional)",
    tipe="Jenis pesan yang dihapus",
)
@app_commands.choices(
    tipe=[
        app_commands.Choice(name="🗑️ Semua pesan", value="semua"),
        app_commands.Choice(name="🤖 Hanya pesan bot", value="bot"),
        app_commands.Choice(name="🔗 Hanya pesan berisi link", value="link"),
        app_commands.Choice(name="🖼️ Hanya pesan bergambar/lampiran", value="gambar"),
    ]
)
async def mod_purge_cmd(
    interaction: discord.Interaction,
    jumlah: app_commands.Range[int, 1, 100] = 20,
    member: discord.Member | None = None,
    tipe: app_commands.Choice[str] | None = None,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    channel = interaction.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        await interaction.response.send_message(
            "⚠️ Purge hanya bisa di text channel atau thread.", ephemeral=True
        )
        return

    kind = tipe.value if tipe else "semua"

    def _check(message: discord.Message) -> bool:
        if member is not None and message.author.id != member.id:
            return False
        if kind == "bot":
            return message.author.bot
        if kind == "link":
            return "http://" in message.content or "https://" in message.content
        if kind == "gambar":
            return bool(message.attachments or message.embeds)
        return True

    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await channel.purge(limit=int(jumlah), check=_check, reason="Purge oleh staff")
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal menghapus pesan: {exc}", ephemeral=True)
        return

    case = mod.add_case(
        interaction.guild.id,
        member.id if member else 0,
        interaction.user.id,
        "note",
        f"Purge {len(deleted)} pesan di #{getattr(channel, 'name', channel.id)} (filter: {kind})",
    )
    await mod.save_moderation_to_disk()
    await interaction.followup.send(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "trash",
            "Pesan Dibersihkan",
            f"**{len(deleted)}** pesan dihapus dari {getattr(channel, 'mention', 'channel ini')}.\n"
            f"• Filter: `{kind}`" + (f"\n• Member: {member.mention}" if member else "")
            + f"\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


@mod_group.command(name="catatan", description="Lihat riwayat kasus seorang member")
@app_commands.describe(member="Member yang dicek (kosongkan untuk kasus terbaru server)", jumlah="Berapa kasus ditampilkan")
async def mod_catatan_cmd(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
    jumlah: app_commands.Range[int, 1, 20] = 8,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    cases = mod.list_cases(interaction.guild.id, member.id if member else None, limit=int(jumlah))
    settings = mod.get_settings(interaction.guild.id)
    header = (
        f"**Member:** {member.mention}" if member else "**Kasus terbaru server ini**"
    )
    if not cases:
        body = f"{header}\n\n_Belum ada kasus tercatat._"
    else:
        lines = [header]
        if member:
            lines.append(
                f"Peringatan aktif: **{mod.count_warns(interaction.guild.id, member.id)}** / "
                f"{settings['warn_threshold'] or '∞'} (jendela {settings['warn_window_days']} hari)"
            )
        lines.append("")
        lines.extend(mod.summarize_case(case) for case in cases)
        body = "\n".join(lines)

    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="📁 Riwayat Moderasi", description=body[:4000]),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


@mod_group.command(name="hapus", description="Hapus satu kasus dari catatan (mis. salah catat)")
@app_commands.describe(id="Nomor kasus (lihat /mod catatan)")
async def mod_hapus_cmd(interaction: discord.Interaction, id: app_commands.Range[int, 1, 1000000]):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild)):
        await interaction.response.send_message(
            "⚠️ Menghapus catatan hanya untuk **Admin**.", ephemeral=True
        )
        return

    removed = mod.delete_case(interaction.guild.id, int(id))
    await mod.save_moderation_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "trash" if removed else "warn",
            "Kasus Dihapus" if removed else "Kasus Tidak Ditemukan",
            f"Kasus `#{id}` sudah dihapus dari catatan." if removed
            else f"Tidak ada kasus dengan nomor `#{id}`.",
        ),
        ephemeral=True,
    )


@mod_group.command(name="atur", description="Atur channel log, ambang auto-punish, & DM member")
@app_commands.describe(
    log_channel="Channel untuk laporan setiap aksi moderasi",
    ambang_warn="Jumlah warn sebelum auto-timeout (0 = matikan)",
    durasi_auto="Durasi timeout otomatis, contoh 60m / 2h",
    jendela_hari="Warn dihitung dalam N hari terakhir",
    dm="Kirim DM ke member saat dikenai aksi",
    nonaktifkan_log="True untuk mematikan channel log",
)
async def mod_atur_cmd(
    interaction: discord.Interaction,
    log_channel: discord.TextChannel | None = None,
    ambang_warn: app_commands.Range[int, 0, 10] | None = None,
    durasi_auto: str | None = None,
    jendela_hari: app_commands.Range[int, 1, 365] | None = None,
    dm: bool | None = None,
    nonaktifkan_log: bool = False,
):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild)):
        await interaction.response.send_message(
            "⚠️ Pengaturan moderasi hanya untuk **Admin**.", ephemeral=True
        )
        return

    changes: dict = {}
    if log_channel is not None:
        changes["log_channel"] = log_channel.id
    if nonaktifkan_log:
        changes["log_channel"] = 0
    if ambang_warn is not None:
        changes["warn_threshold"] = int(ambang_warn)
    if durasi_auto:
        changes["auto_timeout_min"] = max(1, mod.parse_duration(durasi_auto) // 60)
    if jendela_hari is not None:
        changes["warn_window_days"] = int(jendela_hari)
    if dm is not None:
        changes["dm_user"] = dm

    settings = mod.set_settings(interaction.guild.id, **changes)
    await mod.save_moderation_to_disk()

    log_text = f"<#{settings['log_channel']}>" if settings.get("log_channel") else "_mati_"
    body = (
        f"• **Channel log:** {log_text}\n"
        f"• **Ambang auto-timeout:** `{settings['warn_threshold'] or 'nonaktif'}` warn\n"
        f"• **Durasi auto-timeout:** `{settings['auto_timeout_min']}` menit\n"
        f"• **Jendela hitung warn:** `{settings['warn_window_days']}` hari\n"
        f"• **DM ke member:** {'aktif' if settings['dm_user'] else 'mati'}\n\n"
        "💡 Contoh: `/mod atur ambang_warn:3 durasi_auto:1h log_channel:#mod-log`"
    )
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🛡️ Pengaturan Moderasi", description=body), interaction.guild.id
        ),
        ephemeral=True,
    )


def register_moderation_cog(bot: commands.Bot) -> None:
    """Mendaftarkan group `/mod` ke bot."""
    bot.tree.add_command(mod_group)


__all__ = ["mod_group", "register_moderation_cog"]
