"""Cog `/curhat` — curhat anonim ke satu channel (0 kuota AI).

Member mengirim lewat `/curhat kirim`, bot memposting **tanpa nama** dengan nomor urut.
Admin menentukan channel, jeda, & boleh-tidaknya tautan; staf bisa menghapus satu curhat
bila isinya melanggar.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import confessions
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.confessions_cog")

curhat_group = app_commands.Group(
    name="curhat",
    description="Kirim curhat anonim ke channel khusus (0 kuota AI)",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


def _is_staff(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    if perms is None:
        return False
    return bool(
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_guild", False)
        or getattr(perms, "manage_messages", False)
    )


def _warna(nilai: str) -> discord.Colour:
    try:
        return discord.Colour(int(str(nilai or "").lstrip("#"), 16))
    except (TypeError, ValueError):
        return discord.Colour(0x5865F2)


def embed_curhat(nomor: int, teks: str, warna: str = "#5865F2") -> discord.Embed:
    """Kartu curhat anonim (tanpa nama penulis, tanpa mention)."""
    embed = discord.Embed(
        title=f"💌 Curhat #{nomor}",
        description=str(teks or "")[:4000],
        colour=_warna(warna),
    )
    embed.set_footer(text="Anonim · bukan pengganti bantuan profesional")
    return embed


@curhat_group.command(name="kirim", description="Kirim curhat anonim ke channel curhat")
@app_commands.describe(teks="Isi curhat (tanpa nama, tanpa mention)")
async def curhat_kirim_cmd(interaction: discord.Interaction, teks: str):
    if interaction.guild is None:
        return
    boleh, pesan = confessions.validasi(interaction.guild.id, interaction.user.id, teks)
    if not boleh:
        await interaction.response.send_message(f"⚠️ {pesan}", ephemeral=True)
        return

    cfg = confessions.peek_config(interaction.guild.id)
    channel = interaction.guild.get_channel(int(cfg.get("channel_id") or 0))
    if channel is None or not callable(getattr(channel, "send", None)):
        await interaction.response.send_message(
            "⚠️ Channel curhat tidak ditemukan. Minta Admin menjalankan `/curhat atur` lagi.",
            ephemeral=True,
        )
        return

    nomor = int(confessions.statistik(interaction.guild.id)["nomor_terakhir"]) + 1
    embed = embed_curhat(nomor, teks, str(cfg.get("warna") or "#5865F2"))
    try:
        terkirim = await channel.send(
            embed=ui_theme.apply_embed_theme(embed, interaction.guild.id),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException):
        await interaction.response.send_message(
            "⚠️ Bot tidak bisa mengirim ke channel curhat (cek izin *Send Messages*).",
            ephemeral=True,
        )
        return

    confessions.catat(
        interaction.guild.id,
        penulis_hash=confessions.hash_penulis(interaction.guild.id, interaction.user.id),
        pesan_id=getattr(terkirim, "id", 0),
        channel_id=getattr(channel, "id", 0),
    )
    await confessions.save_confessions_to_disk()
    await interaction.response.send_message(
        f"✅ Curhat **#{nomor}** terkirim anonim ke {channel.mention}.",
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@curhat_group.command(name="atur", description="Atur channel, jeda, & tautan curhat (Admin)")
@app_commands.describe(
    channel="Channel tempat curhat anonim diposting",
    aktif="Nyalakan/matikan fitur curhat",
    izinkan_link="Bolehkan tautan di dalam curhat",
    jeda_menit="Jeda antar-curhat per orang (menit)",
)
async def curhat_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    aktif: bool = True,
    izinkan_link: bool = False,
    jeda_menit: app_commands.Range[int, 1, 1440] = 5,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **Admin / Manage Server** yang bisa mengatur curhat.", ephemeral=True
        )
        return
    confessions.set_config(
        interaction.guild.id,
        enabled=aktif,
        channel_id=getattr(channel, "id", None) if channel is not None else None,
        izinkan_link=izinkan_link,
        cooldown_sec=int(jeda_menit) * 60,
    )
    await confessions.save_confessions_to_disk()
    data = confessions.statistik(interaction.guild.id)
    tujuan = f"<#{data['channel_id']}>" if data["channel_id"] else "belum diatur"
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Setelan Curhat Disimpan",
            f"Fitur **{'aktif' if data['aktif'] else 'nonaktif'}** · channel {tujuan}\n"
            f"Jeda **{data['cooldown_sec'] // 60} menit** · tautan "
            f"{'diizinkan' if data['izinkan_link'] else 'dilarang'}\n"
            "Isi curhat tidak disimpan ke disk — hanya nomor & hash penulis.",
        ),
        ephemeral=True,
    )


@curhat_group.command(name="hapus", description="Hapus satu curhat yang melanggar (staf)")
@app_commands.describe(nomor="Nomor curhat yang ingin dihapus")
async def curhat_hapus_cmd(
    interaction: discord.Interaction, nomor: app_commands.Range[int, 1, 1000000]
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **staf** yang bisa menghapus curhat.", ephemeral=True
        )
        return
    data = confessions.ambil(interaction.guild.id, int(nomor))
    if data is None:
        await interaction.response.send_message(
            f"ℹ️ Curhat #{nomor} tidak ada di catatan bot.", ephemeral=True
        )
        return

    terhapus = False
    channel = interaction.guild.get_channel(int(data.get("channel_id") or 0))
    if channel is not None and int(data.get("pesan_id") or 0):
        try:
            pesan = await channel.fetch_message(int(data["pesan_id"]))
            await pesan.delete()
            terhapus = True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            terhapus = False

    confessions.hapus(interaction.guild.id, int(nomor))
    await confessions.save_confessions_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if terhapus else "warn",
            "Curhat Dihapus" if terhapus else "Catatan Dihapus",
            (
                f"Curhat #{nomor} dihapus dari channel."
                if terhapus
                else f"Pesan #{nomor} tidak bisa dihapus (sudah hilang/tanpa izin); catatannya dibersihkan."
            ),
        ),
        ephemeral=True,
    )


def register_confessions_cog(bot: commands.Bot) -> None:
    """Daftarkan grup `/curhat` ke bot."""
    bot.tree.add_command(curhat_group)


__all__ = ["curhat_group", "embed_curhat", "register_confessions_cog"]
