"""Slash `/log` — pengaturan **Audit Log** server (0 kuota AI).

Cukup satu channel tujuan; semua event penting server dicatat di sana.
Default NONAKTIF supaya server yang belum butuh tidak menambah beban apa pun.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import audit_log
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.audit_cog")

log_group = app_commands.Group(
    name="log",
    description="Audit log server: pesan dihapus/diedit, member, role, & channel (0 kuota AI)",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)

_CATEGORY_CHOICES = [
    app_commands.Choice(name=label, value=key) for key, label in audit_log.CATEGORIES.items()
]


@log_group.command(name="channel", description="Pasang channel tujuan audit log (aktifkan fitur)")
@app_commands.describe(channel="Channel teks tempat semua catatan aktivitas dikirim")
async def log_channel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.guild is None:
        return
    gid = interaction.guild.id

    perms = getattr(interaction.guild.me, "guild_permissions", None)
    if perms is not None:
        target_perms = channel.permissions_for(interaction.guild.me)
        if not (target_perms.send_messages and target_perms.embed_links):
            await ui_kit.send_status(
                interaction,
                embed=ui_theme.status_embed(
                    gid,
                    "warn",
                    "Izin kurang di channel itu",
                    f"Bot butuh **Send Messages** & **Embed Links** di {channel.mention}. "
                    "Perbaiki izin channel-nya lalu jalankan ulang perintah ini.",
                ),
                ephemeral=True,
            )
            return

    cfg = audit_log.set_log_channel(gid, channel.id)
    await audit_log.save_audit_to_disk()

    active = [label for key, label in audit_log.CATEGORIES.items() if cfg["categories"].get(key)]
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Audit Log aktif",
            f"Semua catatan dikirim ke {channel.mention}.\n\n"
            "**Kategori aktif:**\n" + "\n".join(f"• {label}" for label in active) +
            "\n\n-# Voice default mati karena paling ramai; nyalakan lewat `/log kategori`.",
        ),
        ephemeral=True,
    )


@log_group.command(name="status", description="Lihat channel log, kategori aktif, & channel yang diabaikan")
async def log_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    embed = audit_log.build_status_embed(interaction.guild.id)
    await ui_kit.send_status(interaction, embed=embed, ephemeral=True)


@log_group.command(name="kategori", description="Nyalakan/matikan satu jenis pencatatan")
@app_commands.describe(nama="Jenis aktivitas yang dicatat", aktif="True nyalakan, False matikan")
@app_commands.choices(nama=_CATEGORY_CHOICES)
async def log_kategori_cmd(
    interaction: discord.Interaction,
    nama: app_commands.Choice[str],
    aktif: bool = True,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not audit_log.is_enabled(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "warn",
                "Audit Log belum aktif",
                "Pasang dulu channel-nya: `/log channel channel:#bot-log`.",
            ),
            ephemeral=True,
        )
        return

    cfg = audit_log.set_category(gid, nama.value, aktif)
    await audit_log.save_audit_to_disk()
    label = audit_log.CATEGORIES.get(nama.value, nama.value)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if aktif else "info",
            "Kategori diperbarui",
            f"{'✅ Dicatat' if aktif else '⛔ Dihentikan'}: **{label}**"
            + ("" if cfg else "\n_Kategori tidak dikenal._"),
        ),
        ephemeral=True,
    )


@log_group.command(name="abaikan", description="Kecualikan sebuah channel dari audit log (mis. #bot-spam)")
@app_commands.describe(channel="Channel yang tidak ingin dicatat", aktif="True = abaikan, False = catat lagi")
async def log_abaikan_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool = True,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not audit_log.is_enabled(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "warn",
                "Audit Log belum aktif",
                "Pasang dulu channel-nya: `/log channel channel:#bot-log`.",
            ),
            ephemeral=True,
        )
        return

    cfg = audit_log.toggle_ignore_channel(gid, channel.id, ignore=aktif)
    await audit_log.save_audit_to_disk()
    ignored = cfg.get("ignore_channels") or []
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if aktif else "info",
            "Channel dikecualikan" if aktif else "Channel dicatat kembali",
            f"{channel.mention} {'tidak akan' if aktif else 'kembali'} dicatat di audit log.\n"
            f"**Total dikecualikan:** `{len(ignored)}` channel",
        ),
        ephemeral=True,
    )


@log_group.command(name="matikan", description="Matikan audit log server ini (konfigurasi dihapus)")
async def log_matikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    audit_log.set_log_channel(gid, None)
    await audit_log.save_audit_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "trash",
            "Audit Log dimatikan",
            "Bot berhenti mengirim catatan aktivitas. Pasang lagi kapan pun dengan "
            "`/log channel channel:#bot-log`.",
        ),
        ephemeral=True,
    )


def register_audit_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/log` ke bot."""
    bot.tree.add_command(log_group)
