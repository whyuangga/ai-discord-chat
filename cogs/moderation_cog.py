"""Cog `/mod` — moderasi bercatatan (warn, timeout, kick, ban, purge) ala Dyno/Carl-bot.

Semua aksi tercatat di `data/moderation.json` dan bisa dilihat lewat `/mod catatan`.
Auto-punish: setelah N `warn` (default 3 dalam 30 hari), bot otomatis memberi timeout
(default 60 menit) — bisa diatur lewat `/mod atur`.
"""

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

import moderation as mod
import ui_kit
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
    "tempban": 0xE67E22,
    "softban": 0x1ABC9C,
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
    await ui_kit.send_status(
        interaction,
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
    await ui_kit.send_status(
        interaction,
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
    await ui_kit.send_status(
        interaction,
        follow=True,
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
    await ui_kit.send_status(
        interaction,
        follow=True,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Member Diban",
            f"**{member}** (`{member.id}`) diban.\n• Alasan: {alasan}\n• Kasus: `#{case['id']}`"
            + (f"\n• Pesan dihapus: {hapus_pesan_hari} hari terakhir" if hapus_pesan_hari else ""),
        ),
        ephemeral=True,
    )


@mod_group.command(
    name="tempban", description="Ban sementara — dicabut otomatis saat durasi habis"
)
@app_commands.describe(
    member="Member (atau ID) yang diban sementara",
    durasi="Contoh: 1h, 12j, 2d, 1j30m",
    alasan="Alasan temp-ban",
    hapus_pesan_hari="Hapus pesan N hari terakhir (0–7)",
)
async def mod_tempban_cmd(
    interaction: discord.Interaction,
    member: discord.User,
    durasi: str = "1d",
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

    seconds = min(max(mod.parse_duration(durasi, default_sec=86400), 60), 365 * 86400)
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.guild.ban(
            member, reason=f"Temp-ban {mod.format_duration(seconds)}: {alasan}"[:400],
            delete_message_days=int(hapus_pesan_hari or 0),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal temp-ban: {exc}", ephemeral=True)
        return

    until = time.time() + seconds
    case = mod.add_case(
        interaction.guild.id, member.id, interaction.user.id, "tempban", alasan,
        duration_sec=seconds, expires_at=until,
    )
    mod.add_tempban(
        interaction.guild.id, member.id, case_id=case["id"], until=until,
        oleh=interaction.user.id, reason=alasan,
    )
    await mod.save_moderation_to_disk()
    await _announce(interaction, case, member)
    await ui_kit.send_status(
        interaction,
        follow=True,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Temp-ban Diterapkan",
            f"**{member}** (`{member.id}`) diban selama **{mod.format_duration(seconds)}** "
            f"dan akan **dicabut otomatis** <t:{int(until)}:R>.\n"
            f"• Alasan: {alasan}\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


@mod_group.command(
    name="softban", description="Softban — hapus pesan member lalu cabut ban-nya saat itu juga"
)
@app_commands.describe(
    member="Member (atau ID) yang di-softban",
    alasan="Alasan softban",
    hapus_pesan_hari="Hapus pesan N hari terakhir (0–7)",
)
async def mod_softban_cmd(
    interaction: discord.Interaction,
    member: discord.User,
    alasan: str = "Tidak disebutkan",
    hapus_pesan_hari: app_commands.Range[int, 0, 7] = 7,
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
            member, reason=f"Softban: {alasan}"[:400],
            delete_message_days=int(hapus_pesan_hari or 0),
        )
        await interaction.guild.unban(
            discord.Object(id=member.id), reason="Softban: ban dicabut (pembersihan pesan)"
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal softban: {exc}", ephemeral=True)
        return

    case = mod.add_case(interaction.guild.id, member.id, interaction.user.id, "softban", alasan)
    await mod.save_moderation_to_disk()
    await _announce(
        interaction, case, member,
        extra="🧹 Softban: ban sudah dicabut, member **boleh bergabung lagi**.",
    )
    await ui_kit.send_status(
        interaction,
        follow=True,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Softban Selesai",
            f"**{member}** (`{member.id}`) ditendang sebagai ban lalu **langsung dicabut** "
            f"— pesan {hapus_pesan_hari} hari terakhir ikut dihapus.\n"
            f"• Alasan: {alasan}\n• Kasus: `#{case['id']}`",
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
    await ui_kit.send_status(
        interaction,
        follow=True,
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
    await ui_kit.send_status(
        interaction,
        follow=True,
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
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "trash" if removed else "warn",
            "Kasus Dihapus" if removed else "Kasus Tidak Ditemukan",
            f"Kasus `#{id}` sudah dihapus dari catatan." if removed
            else f"Tidak ada kasus dengan nomor `#{id}`.",
        ),
        ephemeral=True,
    )


@mod_group.command(
    name="note", description="Tulis catatan internal staff tentang seorang member (tanpa hukuman)"
)
@app_commands.describe(member="Member yang dicatat", teks="Isi catatan (hanya staff yang bisa lihat)")
async def mod_note_cmd(interaction: discord.Interaction, member: discord.Member, teks: str):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    case = mod.add_case(interaction.guild.id, member.id, interaction.user.id, "note", teks)
    await mod.save_moderation_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Catatan Staff Disimpan",
            f"Catatan `#{case['id']}` untuk {member.mention} tersimpan.\n"
            "Member **tidak** diberi tahu & **tidak** dihukum — catatan hanya muncul di "
            "`/mod catatan` dan dashboard.",
        ),
        ephemeral=True,
    )


@mod_group.command(name="statistik", description="Statistik moderasi: siapa menindak berapa banyak")
@app_commands.describe(hari="Batasi ke N hari terakhir (0 = semua)")
async def mod_statistik_cmd(
    interaction: discord.Interaction,
    hari: app_commands.Range[int, 0, 365] = 30,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    data = mod.staff_stats(interaction.guild.id, days=int(hari) or None, limit=10)
    if not data["total"]:
        body = (
            f"_Belum ada tindakan moderasi dalam {hari} hari terakhir._"
            if hari else "_Belum ada tindakan moderasi tercatat._"
        )
    else:
        lines = [
            f"**{data['total']} tindakan**"
            + (f" dalam **{hari} hari** terakhir" if hari else " sepanjang waktu"),
            "",
        ]
        for nomor, orang in enumerate(data["moderator"], start=1):
            nama = "🤖 otomatis" if orang["moderator_id"] == 0 else f"<@{orang['moderator_id']}>"
            rincian = " · ".join(
                f"{mod.ACTIONS.get(a, {}).get('emoji', '•')}{n}" for a, n in orang["per_aksi"].items()
            )
            lines.append(f"`{nomor}.` {nama} — **{orang['total']}** ({rincian})")
        lines.append("")
        lines.append(
            "Per jenis aksi: "
            + " · ".join(f"{a}: {n}" for a, n in sorted(data["per_aksi"].items()))
        )
        body = "\n".join(lines)

    embed = ui_theme.apply_embed_theme(
        discord.Embed(title="📊 Statistik Moderasi", description=body[:4000]),
        interaction.guild.id,
    )
    if mod.list_tempbans(interaction.guild.id):
        embed.add_field(
            name="⏳ Temp-ban aktif",
            value="\n".join(
                f"`#{e['case_id']}` <@{e['user_id']}> — berakhir <t:{int(e['until'])}:R>"
                for e in mod.list_tempbans(interaction.guild.id)[:8]
            )[:1024],
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


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



# ==============================================================================
# v1.28.0-beta — PERKAKAS MODERASI HARIAN (slowmode, role, nickname)
# ==============================================================================
@mod_group.command(name="slowmode", description="Atur mode lambat (slowmode) supaya channel tidak banjir")
@app_commands.describe(
    detik="Jeda antar-pesan dalam detik (0 = matikan, maks 21600 = 6 jam)",
    channel="Channel yang diatur (bawaan: channel ini)",
    alasan="Alasan perubahan (opsional)",
)
async def mod_slowmode_cmd(
    interaction: discord.Interaction,
    detik: app_commands.Range[int, 0, 21600],
    channel: discord.TextChannel | None = None,
    alasan: str | None = None,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    target = channel or interaction.channel
    # TextChannel punya `slowmode_delay`; voice/stage tidak.
    if not isinstance(target, discord.TextChannel) and not hasattr(target, "slowmode_delay"):
        await interaction.response.send_message(
            "⚠️ Slowmode hanya berlaku di **text channel** (bukan voice/thread).", ephemeral=True
        )
        return

    me = interaction.guild.me
    perms = getattr(me, "guild_permissions", None) if me else None
    if perms is None or not perms.manage_channels:
        await interaction.response.send_message(
            "⚠️ Bot butuh izin **Manage Channels** untuk mengatur slowmode.", ephemeral=True
        )
        return

    try:
        await target.edit(
            slowmode_delay=int(detik),
            reason=(alasan or f"Slowmode oleh {interaction.user}")[:400],
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(
            f"⚠️ Gagal mengubah slowmode: `{type(exc).__name__}`", ephemeral=True
        )
        return

    case = mod.add_case(
        interaction.guild.id,
        0,
        interaction.user.id,
        "note",
        f"Slowmode {target.name} → {int(detik)} dtk" + (f" ({alasan})" if alasan else ""),
    )
    await mod.save_moderation_to_disk()

    if int(detik) == 0:
        judul, isi = "Slowmode dimatikan", f"{target.mention} kembali normal (tanpa jeda)."
    else:
        menit = int(detik) // 60
        panjang = f"{menit} menit" if menit else f"{int(detik)} detik"
        judul, isi = "Slowmode dipasang", f"{target.mention} — jeda **{panjang}** antar-pesan."
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id, "ok", judul, isi + f"\n• Kasus: `#{case['id']}`"
        ),
        ephemeral=True,
    )


@mod_group.command(name="role", description="Beri atau cabut satu role dari seorang member")
@app_commands.describe(
    member="Member yang diubah",
    role="Role yang diberikan/dicabut",
    aksi="Beri atau cabut role",
    alasan="Alasan perubahan (opsional)",
)
@app_commands.choices(
    aksi=[
        app_commands.Choice(name="➕ Beri role", value="beri"),
        app_commands.Choice(name="➖ Cabut role", value="cabut"),
    ]
)
async def mod_role_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    aksi: app_commands.Choice[str] | None = None,
    alasan: str | None = None,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    mode = aksi.value if aksi else "beri"
    ok, reason = _role_change_problem(interaction.guild, member, role)
    if not ok:
        await interaction.response.send_message(f"⚠️ {reason}", ephemeral=True)
        return

    try:
        if mode == "beri":
            await member.add_roles(role, reason=(alasan or f"oleh {interaction.user}")[:400])
        else:
            await member.remove_roles(role, reason=(alasan or f"oleh {interaction.user}")[:400])
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(
            f"⚠️ Gagal mengubah role: `{type(exc).__name__}`", ephemeral=True
        )
        return

    case = mod.add_case(
        interaction.guild.id,
        member.id,
        interaction.user.id,
        "note",
        f"{'Beri' if mode == 'beri' else 'Cabut'} role {role.name}" + (f" — {alasan}" if alasan else ""),
    )
    await mod.save_moderation_to_disk()
    await _announce(interaction, case, member)

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Role diperbarui",
            f"{'✅ Ditambahkan' if mode == 'beri' else '🗑️ Dicabut'}: {role.mention}\n"
            f"• Member: {member.mention}\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


@mod_group.command(name="role-massal", description="Beri/cabut satu role ke banyak member sekaligus (dengan konfirmasi)")
@app_commands.describe(
    role="Role yang diberikan/dicabut",
    aksi="Beri atau cabut role",
    filter_role="Hanya member yang punya role ini (opsional)",
    batas="Maksimal member diproses (1–100)",
)
@app_commands.choices(
    aksi=[
        app_commands.Choice(name="➕ Beri ke semua", value="beri"),
        app_commands.Choice(name="➖ Cabut dari semua", value="cabut"),
    ]
)
async def mod_role_massal_cmd(
    interaction: discord.Interaction,
    role: discord.Role,
    aksi: app_commands.Choice[str],
    filter_role: discord.Role | None = None,
    batas: app_commands.Range[int, 1, 100] = 50,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    guild = interaction.guild
    me = guild.me
    if me is None or role >= me.top_role:
        await interaction.response.send_message(
            "⚠️ Posisi role itu **di atas role bot**. Pindahkan role bot lebih tinggi.", ephemeral=True
        )
        return
    if role.is_default() or role.managed:
        await interaction.response.send_message(
            "⚠️ Role `@everyone` atau role yang dikelola integrasi tidak bisa diubah massal.", ephemeral=True
        )
        return

    mode = aksi.value
    targets: list[discord.Member] = []
    for member in guild.members:
        if member.bot or member.id == guild.owner_id or member.id == me.id:
            continue
        if filter_role is not None and filter_role not in member.roles:
            continue
        has_role = role in member.roles
        if (mode == "beri" and has_role) or (mode == "cabut" and not has_role):
            continue
        targets.append(member)
        if len(targets) >= int(batas):
            break

    if not targets:
        await interaction.response.send_message(
            "ℹ️ Tidak ada member yang perlu diubah (semua sudah sesuai).", ephemeral=True
        )
        return

    daftar = ", ".join(m.mention for m in targets[:10]) + ("…" if len(targets) > 10 else "")

    async def _run() -> None:
        berhasil, gagal = 0, 0
        for member in targets:
            try:
                if mode == "beri":
                    await member.add_roles(role, reason="Role massal oleh staff")
                else:
                    await member.remove_roles(role, reason="Role massal oleh staff")
                berhasil += 1
            except (discord.Forbidden, discord.HTTPException):
                gagal += 1

        case = mod.add_case(
            guild.id,
            0,
            interaction.user.id,
            "note",
            f"Role massal {'+' if mode == 'beri' else '-'}{role.name}: {berhasil} berhasil, {gagal} gagal",
        )
        await mod.save_moderation_to_disk()
        await interaction.edit_original_response(
            embed=ui_theme.status_embed(
                guild.id,
                "ok" if berhasil else "warn",
                "Role massal selesai",
                f"{'✅ Diberi' if mode == 'beri' else '🗑️ Dicabut'}: {role.mention}\n"
                f"• Berhasil: **{berhasil}** • Gagal: **{gagal}**\n• Kasus: `#{case['id']}`",
            )
        )

    view = await ui_kit.ask_confirm(
        interaction,
        guild.id,
        title="Konfirmasi role massal",
        detail=(
            f"Akan **{'memberi' if mode == 'beri' else 'mencabut'}** role {role.mention} "
            f"ke **{len(targets)} member**:\n{daftar}\n\nLanjutkan?"
        ),
        confirm_label="Ya, jalankan",
        on_confirm=_run,
    )
    if view is None:  # tema server mematikan konfirmasi → langsung jalankan
        await interaction.response.defer(ephemeral=True)
        await _run()


@mod_group.command(name="nickname", description="Ubah atau reset nama panggilan (nickname) member")
@app_commands.describe(member="Member yang diubah", nama="Nama baru (kosongkan untuk reset)", alasan="Alasan (opsional)")
async def mod_nickname_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    nama: str | None = None,
    alasan: str | None = None,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        return await _reject(interaction)

    guild = interaction.guild
    me = guild.me
    if me is None or (member.id != me.id and member.top_role >= me.top_role):
        await interaction.response.send_message(
            "⚠️ Member ini punya role lebih tinggi/sama dengan bot, jadi nickname-nya tidak bisa diubah.",
            ephemeral=True,
        )
        return

    clean = (nama or "").strip()[:32] or None
    try:
        await member.edit(nick=clean, reason=(alasan or f"oleh {interaction.user}")[:400])
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(
            f"⚠️ Gagal mengubah nickname: `{type(exc).__name__}`", ephemeral=True
        )
        return

    case = mod.add_case(
        guild.id,
        member.id,
        interaction.user.id,
        "note",
        (f"Nickname → {clean}" if clean else "Nickname direset") + (f" ({alasan})" if alasan else ""),
    )
    await mod.save_moderation_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            guild.id,
            "ok",
            "Nickname diperbarui",
            f"• Member: {member.mention}\n"
            f"• Nama baru: **{clean or 'direset ke nama asli'}**\n• Kasus: `#{case['id']}`",
        ),
        ephemeral=True,
    )


def _role_change_problem(guild: discord.Guild, member: discord.Member, role: discord.Role) -> tuple[bool, str]:
    """Memastikan bot boleh mengubah role member ini."""
    me = guild.me
    if me is None:
        return False, "Bot tidak berada di server ini."
    perms = getattr(me, "guild_permissions", None)
    if perms is None or not perms.manage_roles:
        return False, "Bot butuh izin **Manage Roles**."
    if role.is_default():
        return False, "Role `@everyone` tidak bisa diubah."
    if role.managed:
        return False, "Role ini dikelola integrasi/bot lain."
    if role >= me.top_role:
        return False, "Posisi role itu **di atas role bot**."
    if member.id == guild.owner_id:
        return False, "Tidak bisa mengubah role **pemilik server**."
    if member.top_role >= me.top_role and member.id != me.id:
        return False, f"{member.mention} punya role lebih tinggi/sama dengan bot."
    return True, ""


def register_moderation_cog(bot: commands.Bot) -> None:
    """Mendaftarkan group `/mod` ke bot."""
    bot.tree.add_command(mod_group)


__all__ = ["mod_group", "register_moderation_cog"]
