"""Slash `/prefix` — atur prefix command teks per server (**0 kuota AI**).

Slash command tidak terpengaruh; ini hanya untuk command berbasis prefix seperti `!setup_panel`.
- `/prefix lihat` — prefix aktif (khusus server + bawaan).
- `/prefix atur <prefix>` *(Admin)* — ganti prefix server (1–5 karakter).
- `/prefix reset` *(Admin)* — kembalikan ke prefix bawaan.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import i18n
import prefixes
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.prefix_cog")

prefix_group = app_commands.Group(
    name="prefix",
    description="Atur prefix command teks (!setup_panel, dll.) untuk server ini (0 kuota AI)",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms
        and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


@prefix_group.command(name="lihat", description="Lihat prefix command yang aktif di server ini")
async def prefix_lihat_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    custom = prefixes.get_prefix(gid)
    daftar = "\n".join(f"• `{p}` — contoh: `{p}setup_panel`" for p in prefixes.prefixes_for(gid))
    body = (
        f"Prefix khusus server: **`{custom}`**"
        + (" _(bawaan)_" if custom == prefixes.DEFAULT_PREFIX else "")
        + "\n\n**Prefix yang diterima**\n"
        + daftar
        + "\n\nSlash command (`/...`) tidak terpengaruh pengaturan ini."
        + "\nGanti prefix (Admin): `/prefix atur prefix:?`."
    )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "info", f"{prefixes.DEFAULT_PREFIX} Prefix Command", body),
        ephemeral=True,
    )


@prefix_group.command(name="atur", description="Ganti prefix command teks server ini (Admin)")
@app_commands.describe(prefix="Prefix baru, 1–5 karakter (contoh: !, ?, .., bot!)")
async def prefix_atur_cmd(interaction: discord.Interaction, prefix: str):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "lock", i18n.t("perm.admin", gid), i18n.t("perm.admin_detail", gid)
            ),
            ephemeral=True,
        )
        return

    ok, value, message = prefixes.set_prefix(gid, prefix)
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Prefix tidak valid", message),
            ephemeral=True,
        )
        return

    await prefixes.save_prefixes_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            i18n.t("status.saved", gid),
            f"{message}\n\n**Contoh pemakaian:** `{value}setup_panel`\n"
            f"Prefix bawaan **`{prefixes.DEFAULT_PREFIX}`** tetap diterima sebagai cadangan.",
        ),
        ephemeral=True,
    )
    logger.info("Prefix server %s diganti ke %r oleh %s", gid, value, interaction.user)


@prefix_group.command(name="reset", description="Kembalikan prefix command ke bawaan (Admin)")
async def prefix_reset_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "lock", i18n.t("perm.admin", gid), i18n.t("perm.admin_detail", gid)
            ),
            ephemeral=True,
        )
        return

    changed = prefixes.reset_prefix(gid)
    await prefixes.save_prefixes_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if changed else "info",
            "Prefix direset",
            (
                f"Prefix kembali ke bawaan **`{prefixes.DEFAULT_PREFIX}`**."
                if changed
                else f"Server ini memang sudah memakai prefix bawaan **`{prefixes.DEFAULT_PREFIX}`**."
            ),
        ),
        ephemeral=True,
    )


def register_prefix_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/prefix` ke bot."""
    bot.tree.add_command(prefix_group)
