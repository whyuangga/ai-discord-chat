"""Slash `/bahasa` — atur bahasa teks kerangka bot per server (**0 kuota AI**).

- `/bahasa lihat` — bahasa aktif, daftar pilihan, & contoh teks kerangka.
- `/bahasa atur <kode>` *(Admin)* — ganti ke `id` (Bahasa Indonesia) atau `en` (English).

Bahasa berlaku **per server** dan hanya untuk teks kerangka (tombol konfirmasi, kata status,
pesan izin, `/bahasa`). Penjelasan panjang fitur tetap Bahasa Indonesia.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import i18n
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.language_cog")

bahasa_group = app_commands.Group(
    name="bahasa",
    description="Atur bahasa teks kerangka bot untuk server ini: Indonesia atau English (0 kuota AI)",
    guild_only=True,
)

_KODE_CHOICES = [
    app_commands.Choice(name=label, value=code) for code, label in i18n.LANG_NAMES.items()
]


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms
        and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


@bahasa_group.command(name="lihat", description="Lihat bahasa aktif server ini & contoh teks yang diterjemahkan")
async def bahasa_lihat_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    current = i18n.get_lang(gid)

    preview = "\n".join(
        [
            f"• `{i18n.t('confirm.yes', gid)}` / `{i18n.t('confirm.cancel', gid)}` — tombol dialog",
            f"• `{i18n.t('confirm.confirmed', gid)}` • `{i18n.t('confirm.cancelled', gid)}` — hasil dialog",
            f"• `{i18n.t('status.on', gid)}` / `{i18n.t('status.off', gid)}` — kata status",
            f"• `{i18n.t('perm.admin', gid)}` — pesan izin",
            f"• `{i18n.t('lang.current', gid, lang=i18n.lang_label(current))}` — baris ini",
        ]
    )
    daftar = "\n".join(f"• `{code}` — {label}" for code, label in i18n.available_langs().items())
    body = (
        i18n.t("lang.current", gid, lang=i18n.lang_label(current))
        + "\n\n**Pilihan bahasa**\n"
        + daftar
        + "\n\n**Contoh teks kerangka**\n"
        + preview
        + "\n\n"
        + i18n.t("lang.only_framework", gid)
        + "\n\nGanti bahasa (Admin): `/bahasa atur kode:en`."
    )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "info", "🌐 Bahasa Server", body),
        ephemeral=True,
    )


@bahasa_group.command(name="atur", description="Ganti bahasa teks kerangka bot untuk server ini (Admin)")
@app_commands.describe(kode="Bahasa yang dipakai: id (Indonesia) atau en (English)")
@app_commands.choices(kode=_KODE_CHOICES)
async def bahasa_atur_cmd(interaction: discord.Interaction, kode: app_commands.Choice[str]):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "lock",
                i18n.t("perm.admin", gid),
                i18n.t("perm.admin_detail", gid),
            ),
            ephemeral=True,
        )
        return

    ok, lang = i18n.set_lang(gid, kode.value)
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "error",
                "🌐 Bahasa",
                i18n.t("lang.invalid", gid, code=kode.value, options=", ".join(i18n.available_langs())),
            ),
            ephemeral=True,
        )
        return

    await i18n.save_lang_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "🌐 " + i18n.t("status.saved", gid),
            i18n.t("lang.set", gid, lang=i18n.lang_label(lang)) + "\n\n" + i18n.t("lang.only_framework", gid),
        ),
        ephemeral=True,
    )
    logger.info("Bahasa server %s diganti ke %s oleh %s", gid, lang, interaction.user)


def register_language_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/bahasa` ke bot."""
    bot.tree.add_command(bahasa_group)
