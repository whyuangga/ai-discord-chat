"""Cog `/kanal-info` — channel aturan & info yang menyegarkan dirinya sendiri."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import info_channel as ic
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.info_channel_cog")

kanal_info_group = app_commands.Group(
    name="kanal-info",
    description="Channel aturan & info yang diperbarui otomatis (0 kuota AI)",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


async def _tolak_admin(interaction: discord.Interaction) -> None:
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id if interaction.guild else None,
            "error",
            "Butuh Izin Admin",
            "Pengaturan channel info khusus **Admin / pengelola server**.",
        ),
        ephemeral=True,
    )


def _bot_of(interaction: discord.Interaction):
    """Bot dari interaction (aman untuk objek uji yang hanya punya `client`)."""
    client = getattr(interaction, "client", None)
    return client if client is not None else getattr(interaction, "bot", None)


def _kanal_teks(data: dict) -> str:
    channel_id = data.get("channel_id")
    return f"<#{channel_id}>" if channel_id else "belum dipilih"


@kanal_info_group.command(
    name="atur",
    description="(Admin) Pilih channel info, sakelar, judul, warna, & jeda penyegaran",
)
@app_commands.describe(
    channel="Channel baca-saja tempat pesan info diterbitkan",
    aktif="Nyalakan/matikan penyegaran otomatis",
    judul="Judul embed (bawaan: ℹ️ Informasi Server)",
    warna="Warna embed, contoh #5865F2",
    interval_menit="Seberapa sering pesan dicek masih ada (5–1440 menit)",
)
async def info_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    aktif: bool | None = None,
    judul: str | None = None,
    warna: str | None = None,
    interval_menit: app_commands.Range[int, ic.INTERVAL_MIN, ic.INTERVAL_MAKS] | None = None,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        return await _tolak_admin(interaction)

    ic.set_config(
        interaction.guild.id,
        enabled=aktif,
        channel_id=getattr(channel, "id", None),
        judul=judul,
        warna=warna,
        interval_menit=interval_menit,
    )
    status = "nonaktif"
    if ic.aktif(interaction.guild.id):
        status = await ic.segarkan(_bot_of(interaction), interaction.guild.id)
    await ic.save_info_channel_to_disk()

    data = ic.statistik(interaction.guild.id)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if data["aktif"] else "info",
            "ℹ️ Channel Info Disimpan",
            f"• **Status:** {'aktif' if data['aktif'] else 'nonaktif'}\n"
            f"• **Channel:** {_kanal_teks(data)}\n"
            f"• **Judul:** {data['judul']}\n"
            f"• **Interval cek:** {data['interval_menit']} menit\n"
            f"• **Panjang isi:** {data['panjang_isi']} huruf\n"
            f"• **Penyegaran:** {status}",
        ),
        ephemeral=True,
    )


@kanal_info_group.command(name="isi", description="(Admin) Tulis/ganti isi aturan & info yang ditampilkan")
@app_commands.describe(teks="Isi pesan (boleh multi-baris, 20–3500 huruf)")
async def info_isi_cmd(interaction: discord.Interaction, teks: str):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        return await _tolak_admin(interaction)

    ok, pesan = ic.set_isi(interaction.guild.id, teks)
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(interaction.guild.id, "error", "Isi Ditolak", pesan),
            ephemeral=True,
        )
        return

    await ic.save_info_channel_to_disk()
    status = "tersimpan (channel belum aktif)"
    if ic.aktif(interaction.guild.id):
        status = await ic.segarkan(_bot_of(interaction), interaction.guild.id)
    data = ic.statistik(interaction.guild.id)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if data["aktif"] else "info",
            "ℹ️ Isi Channel Info Diperbarui",
            f"{pesan}\n\n• **Panjang:** {data['panjang_isi']} huruf\n"
            f"• **Pesan di channel:** {status}\n"
            + (
                ""
                if data["aktif"]
                else "ℹ️ Aktifkan dulu lewat `/kanal-info atur channel:#info aktif:True`."
            ),
        ),
        ephemeral=True,
    )


@kanal_info_group.command(name="segarkan", description="(Admin) Terbitkan/perbarui pesan info sekarang juga")
async def info_segarkan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        return await _tolak_admin(interaction)

    status = await ic.segarkan(_bot_of(interaction), interaction.guild.id)
    pesan = {
        "dibuat": "Pesan info diterbitkan.",
        "diperbarui": "Pesan info diperbarui.",
        "sama": "Pesan info sudah paling baru.",
        "nonaktif": "Channel info belum aktif — isi dulu isinya & pilih channel.",
        "gagal": "Channel tidak ditemukan atau bot tidak punya izin kirim/edit.",
    }.get(status, status)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if status in ("dibuat", "diperbarui", "sama") else "warn",
            "ℹ️ Segarkan Channel Info",
            pesan,
        ),
        ephemeral=True,
    )


@kanal_info_group.command(name="status", description="Lihat ringkasan setelan channel info")
async def info_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    data = ic.statistik(interaction.guild.id)
    isi = data["isi"] or "_(belum diisi)_"
    cuplikan = (isi[:200] + "…") if len(isi) > 200 else isi
    lines = [
        f"• **Status:** {'aktif' if data['aktif'] else 'nonaktif'}",
        f"• **Channel:** {_kanal_teks(data)}",
        f"• **Judul:** {data['judul']}",
        f"• **Interval cek:** {data['interval_menit']} menit",
        f"• **Panjang isi:** {data['panjang_isi']} huruf",
        f"• **Pesan terpasang:** {'ya' if data['pesan_id'] else 'belum'}",
    ]
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(
                title="ℹ️ Status Channel Info",
                description="\n".join(lines) + f"\n\n**Cuplikan isi:**\n{cuplikan}",
            ),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


def register_info_channel_cog(bot: commands.Bot) -> None:
    """Daftarkan grup `/kanal-info` ke bot."""
    bot.tree.add_command(kanal_info_group)


__all__ = ["kanal_info_group", "register_info_channel_cog"]
