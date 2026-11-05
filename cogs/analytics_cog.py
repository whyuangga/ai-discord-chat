"""Slash `/tumbuh` — statistik pertumbuhan server & papan pengundang (**0 kuota AI**).

Isi:
- `/tumbuh ringkas` — join, keluar, selisih, retensi, tren harian, & top inviter.
- `/tumbuh undang` — papan peringkat **Top Inviter** (siapa paling banyak mengundang).
- `/tumbuh status` — status pelacakan + apakah bot bisa membaca daftar invite.
- `/tumbuh atur` *(Admin)* — aktif/matikan, channel log join-keluar, & pelacakan invite.
- `/tumbuh sinkron` *(Admin)* — segarkan cache invite secara manual.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import growth_tracker
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.analytics_cog")

tumbuh_group = app_commands.Group(
    name="tumbuh",
    description="Statistik pertumbuhan server & papan pengundang member (0 kuota AI)",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms
        and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


@tumbuh_group.command(name="ringkas", description="Ringkasan pertumbuhan: join, keluar, retensi, & tren harian")
@app_commands.describe(hari="Berapa hari terakhir dianalisis (1–30)")
async def tumbuh_ringkas_cmd(interaction: discord.Interaction, hari: app_commands.Range[int, 1, 30] = 7):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    data = growth_tracker.stats(gid, int(hari))

    net = data["net"]
    arrow = "📈" if net > 0 else ("📉" if net < 0 else "➡️")
    spark = growth_tracker.build_sparkline(data["series"])
    member_count = getattr(interaction.guild, "member_count", 0) or 0

    lines = [
        f"{arrow} **{net:+d}** member bersih dalam `{data['days']}` hari",
        f"• Bergabung: `{data['joins']}` • Keluar: `{data['leaves']}`",
        f"• Retensi member terlacak: `{data['retention_pct']}%` "
        f"(`{data['stayed']}/{data['tracked']}` masih di server)",
        f"• Total member sekarang: `{member_count}`",
        f"• Tren join harian: {spark}",
    ]
    top = data["top_inviters"]
    if top:
        lines.append("\n**Top Pengundang:**")
        for inviter_id, joins, quick in top[:5]:
            extra = f" (⚠️ {quick} keluar cepat)" if quick else ""
            lines.append(f"• <@{inviter_id}> — `{joins}` undangan{extra}")
    else:
        lines.append("\n_Pelacakan invite belum mencatat siapa pun._")

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            f"🌱 Pertumbuhan {hari} Hari Terakhir",
            "\n".join(lines),
            footer="0 kuota AI • dihitung dari event server",
        ),
        ephemeral=True,
    )


@tumbuh_group.command(name="undang", description="Papan peringkat member yang paling banyak mengundang")
async def tumbuh_undang_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    rows = growth_tracker.invite_leaderboard(gid, limit=10)
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}

    if not rows:
        body = (
            "_Belum ada undangan tercatat._\n"
            "Pastikan bot punya izin **Manage Server** agar bisa membaca daftar invite, "
            "lalu jalankan `/tumbuh sinkron`."
        )
    else:
        body = "\n".join(
            f"{medals.get(idx, f'`{idx + 1}.`')} <@{uid}> — `{joins}` undangan "
            f"(keluar `{leaves}`" + (f", cepat `{quick}`" if quick else "") + ")"
            for idx, (uid, joins, leaves, quick) in enumerate(rows)
        )

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "info", "🎟️ Papan Pengundang", body),
        ephemeral=True,
    )


@tumbuh_group.command(name="status", description="Status pelacakan pertumbuhan & kemampuan baca invite")
async def tumbuh_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    cfg = growth_tracker.get_config(gid)
    data = growth_tracker.stats(gid, 7)

    me = getattr(interaction.guild, "me", None)
    perms = getattr(me, "guild_permissions", None)
    can_invites = bool(perms and getattr(perms, "manage_guild", False))

    lines = [
        f"• Pelacakan: {'✅ aktif' if cfg.get('enabled', True) else '⛔ nonaktif'}",
        f"• Lacak invite: {'✅' if cfg.get('track_invites', True) else '⛔'} "
        f"(`{data['invites_cached']}` kode terpantau)",
        "• Izin *Manage Server*: " + ("✅ ada" if can_invites else "⛔ belum — invite tidak bisa dibaca"),
        "• Channel log join/keluar: "
        + (f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_belum diatur_"),
        f"• Member terlacak: `{data['tracked']}` • retensi `{data['retention_pct']}%`",
    ]
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "info", "🌱 Status Pelacakan Pertumbuhan", "\n".join(lines)),
        ephemeral=True,
    )


@tumbuh_group.command(name="atur", description="Atur pelacakan pertumbuhan & channel log join/keluar (Admin)")
@app_commands.describe(
    aktif="True untuk melacak, False untuk berhenti (data lama tetap disimpan)",
    channel="Channel untuk log member join/keluar (kosongkan = tidak ada log)",
    lacak_invite="True untuk mendeteksi siapa yang mengundang member",
)
async def tumbuh_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool | None = None,
    channel: discord.TextChannel | None = None,
    lacak_invite: bool | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server*."),
            ephemeral=True,
        )
        return

    if aktif is not None or lacak_invite is not None or channel is not None:
        growth_tracker.set_config(
            gid,
            enabled=aktif,
            track_invites=lacak_invite,
            log_channel_id=channel.id if channel else None,
        )
        await growth_tracker.save_growth_to_disk()

    cfg = growth_tracker.get_config(gid)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Pengaturan Pertumbuhan",
            f"• Pelacakan: {'✅ aktif' if cfg.get('enabled', True) else '⛔ nonaktif'}\n"
            f"• Lacak invite: {'✅' if cfg.get('track_invites', True) else '⛔'}\n"
            "• Channel log: " + (f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_tidak ada_"),
        ),
        ephemeral=True,
    )


@tumbuh_group.command(name="sinkron", description="Segarkan cache daftar invite server (Admin)")
async def tumbuh_sinkron_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server*."),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    count = await growth_tracker.sync_invites(interaction.guild)
    if count:
        await growth_tracker.save_growth_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if count else "warn",
            "Cache invite disegarkan" if count else "Tidak bisa membaca invite",
            f"`{count}` kode invite terpantau."
            if count
            else "Bot belum punya izin **Manage Server**, jadi daftar invite tidak bisa dibaca. "
            "Beri izin itu ke role bot lalu coba lagi.",
        ),
        follow=True,
        ephemeral=True,
    )


def register_analytics_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/tumbuh` ke bot."""
    bot.tree.add_command(tumbuh_group)
