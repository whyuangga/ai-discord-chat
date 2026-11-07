"""Cog `/snipe` — lihat pesan yang baru dihapus (`hapus`) & diubah (`edit`).

Khusus staf: grup ini memakai izin bawaan *Manage Messages* sehingga member biasa tidak
melihatnya. Data hanya di memori (tidak ada berkas baru), maksimal 5 pesan per channel.
"""

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

import snipe
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.snipe_cog")

snipe_group = app_commands.Group(
    name="snipe",
    description="Lihat pesan yang baru dihapus/diubah di channel ini (khusus staf)",
    guild_only=True,
    default_permissions=discord.Permissions(manage_messages=True),
)


def _waktu(nilai: float) -> str:
    selisih = max(0, int(time.time() - float(nilai or 0)))
    if selisih < 60:
        return f"{selisih} detik lalu"
    if selisih < 3600:
        return f"{selisih // 60} menit lalu"
    if selisih < 86400:
        return f"{selisih // 3600} jam lalu"
    return f"{selisih // 86400} hari lalu"


def _potong(teks: str, panjang: int = 300) -> str:
    rapi = " ".join(str(teks or "").split())
    if not rapi:
        return "*(tanpa teks)*"
    return rapi[:panjang] + ("…" if len(rapi) > panjang else "")


def _embed_hapus(entri: list[dict], nama_channel: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔎 Pesan terakhir yang dihapus — {nama_channel}",
        description="Data ini **hanya di memori**: hilang saat bot restart.",
        colour=discord.Colour(0xE74C3C),
    )
    for item in entri:
        lampiran = (
            f"\n📎 {', '.join(item['lampiran'])}" if item.get("lampiran") else ""
        )
        embed.add_field(
            name=f"{item['nama']} · {_waktu(item['waktu'])}",
            value=f"{_potong(item['isi'])}{lampiran}"[:1024],
            inline=False,
        )
    return embed


def _embed_edit(entri: list[dict], nama_channel: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"✏️ Pesan terakhir yang diubah — {nama_channel}",
        description="Data ini **hanya di memori**: hilang saat bot restart.",
        colour=discord.Colour(0xF1C40F),
    )
    for item in entri:
        embed.add_field(
            name=f"{item['nama']} · {_waktu(item['waktu'])}",
            value=(
                f"**Sebelum:** {_potong(item['isi'], 220)}\n"
                f"**Sesudah:** {_potong(item.get('sesudah') or '', 220)}"
            )[:1024],
            inline=False,
        )
    return embed


def _nama_channel(channel) -> str:
    return str(getattr(channel, "name", None) or "channel ini")


@snipe_group.command(name="hapus", description="Tampilkan pesan terakhir yang dihapus di channel ini")
@app_commands.describe(jumlah="Berapa pesan terakhir (1–5)")
async def snipe_hapus_cmd(
    interaction: discord.Interaction, jumlah: app_commands.Range[int, 1, snipe.MAX_PER_CHANNEL] = 1
):
    if interaction.guild is None:
        return
    entri = snipe.ambil_hapus(interaction.guild.id, getattr(interaction.channel, "id", 0), int(jumlah))
    if not entri:
        await interaction.response.send_message(
            "🔎 Belum ada pesan terhapus yang bisa ditampilkan di channel ini "
            "(atau fitur snipe dimatikan Admin).",
            ephemeral=True,
        )
        return
    embed = _embed_hapus(entri, _nama_channel(interaction.channel))
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(embed, interaction.guild.id), ephemeral=True
    )


@snipe_group.command(name="edit", description="Tampilkan pesan terakhir yang diubah di channel ini")
@app_commands.describe(jumlah="Berapa pesan terakhir (1–5)")
async def snipe_edit_cmd(
    interaction: discord.Interaction, jumlah: app_commands.Range[int, 1, snipe.MAX_PER_CHANNEL] = 1
):
    if interaction.guild is None:
        return
    entri = snipe.ambil_edit(interaction.guild.id, getattr(interaction.channel, "id", 0), int(jumlah))
    if not entri:
        await interaction.response.send_message(
            "✏️ Belum ada pesan yang diubah di channel ini "
            "(atau fitur edit-snipe dimatikan Admin).",
            ephemeral=True,
        )
        return
    embed = _embed_edit(entri, _nama_channel(interaction.channel))
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(embed, interaction.guild.id), ephemeral=True
    )


@snipe_group.command(name="atur", description="Nyalakan/matikan snipe & edit-snipe (Admin)")
@app_commands.describe(
    aktif="Nyalakan atau matikan seluruh fitur snipe",
    hapus="Catat pesan yang dihapus",
    edit="Catat pesan yang diubah",
)
async def snipe_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool = True,
    hapus: bool = True,
    edit: bool = True,
):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))):
        await interaction.response.send_message(
            "⚠️ Hanya **Admin / Manage Server** yang bisa mengatur snipe.", ephemeral=True
        )
        return
    snipe.set_config(interaction.guild.id, enabled=aktif, hapus=hapus, edit=edit)
    data = snipe.statistik(interaction.guild.id)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Setelan Snipe Disimpan",
            f"Snipe: **{'aktif' if data['aktif'] else 'nonaktif'}** · "
            f"hapus: **{'ya' if data['hapus'] else 'tidak'}** · "
            f"edit: **{'ya' if data['edit'] else 'tidak'}**\n"
            "Riwayat hanya disimpan di memori (hilang saat bot restart).",
        ),
        ephemeral=True,
    )


def register_snipe_cog(bot: commands.Bot) -> None:
    """Daftarkan grup `/snipe` ke bot."""
    bot.tree.add_command(snipe_group)


__all__ = ["snipe_group", "register_snipe_cog"]
