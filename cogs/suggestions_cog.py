"""Cog `/saran` (kotak saran + voting) & `/embed` (pembuat pengumuman cantik)."""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import suggestions as sg
import ui_kit
import ui_theme
from views import SuggestionVoteView

logger = logging.getLogger("gemini_bot.suggestions_cog")

saran_group = app_commands.Group(
    name="saran",
    description="Kotak saran: member mengirim usulan, warga voting lewat tombol 👍/👎",
    guild_only=True,
)

embed_group = app_commands.Group(
    name="embed",
    description="Buat & kirim pengumuman berformat rapi tanpa perlu dashboard",
    guild_only=True,
)


def _is_staff(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild or perms.manage_messages))


def parse_color(value: str) -> discord.Colour:
    """Menerima `#RRGGBB`, `RRGGBB`, atau nama warna dasar."""
    text = str(value or "").strip().lstrip("#").lower()
    named = {
        "ungu": "9b59b6",
        "purple": "9b59b6",
        "biru": "3498db",
        "blue": "3498db",
        "merah": "e74c3c",
        "red": "e74c3c",
        "hijau": "2ecc71",
        "green": "2ecc71",
        "emas": "f1c40f",
        "gold": "f1c40f",
        "abu": "95a5a6",
        "gray": "95a5a6",
    }
    hex_value = named.get(text, text)
    if re.fullmatch(r"[0-9a-f]{6}", hex_value):
        return discord.Colour(int(hex_value, 16))
    return discord.Colour(0x9B59B6)


# ==============================================================================
# /saran
# ==============================================================================
@saran_group.command(name="pasang", description="(Admin) Tentukan channel tempat saran dikirim")
@app_commands.describe(channel="Channel khusus kotak saran", nonaktifkan="True untuk mematikan kotak saran")
async def saran_pasang_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    nonaktifkan: bool = False,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    if nonaktifkan:
        sg.set_channel(interaction.guild.id, None)
        await sg.save_suggestions_to_disk()
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                interaction.guild.id, "lock", "Kotak Saran Dimatikan", "Member tidak bisa lagi mengirim saran."
            ),
            ephemeral=True,
        )
        return

    if channel is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel:` dulu, mis. `/saran pasang channel:#saran`.", ephemeral=True
        )
        return

    sg.set_channel(interaction.guild.id, channel.id)
    await sg.save_suggestions_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Kotak Saran Aktif",
            f"Channel: {channel.mention}\n\n"
            "Member mengirim usulan dengan `/saran kirim teks:...`, lalu warga voting lewat tombol 👍/👎.",
        ),
        ephemeral=True,
    )


@saran_group.command(name="kirim", description="Kirim usulanmu ke kotak saran (bisa di-vote warga)")
@app_commands.describe(teks="Usulan atau ide kamu untuk server ini")
async def saran_kirim_cmd(interaction: discord.Interaction, teks: str):
    if interaction.guild is None:
        return

    channel_id = sg.get_channel(interaction.guild.id)
    if channel_id is None:
        await interaction.response.send_message(
            "ℹ️ Kotak saran belum diaktifkan. Minta Admin menjalankan `/saran pasang channel:#saran`.",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Channel kotak saran tidak ditemukan (mungkin dihapus). Minta Admin memasang ulang.",
            ephemeral=True,
        )
        return

    try:
        item = sg.add_suggestion(interaction.guild.id, interaction.user.id, teks)
    except ValueError as exc:
        await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        message = await channel.send(
            content=f"💡 Saran baru dari {interaction.user.mention}!",
            embed=sg.build_suggestion_embed(interaction.guild.id, item),
            view=SuggestionVoteView(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal mengirim saran: {exc}", ephemeral=True)
        return

    sg.bind_message(interaction.guild.id, item["id"], message.id)
    await sg.save_suggestions_to_disk()
    await ui_kit.send_status(
        interaction,
        follow=True,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            f"Saran #{item['id']} Terkirim",
            f"Usulanmu sudah tampil di {channel.mention}. Terima kasih sudah ikut membangun server! 💜",
        ),
        ephemeral=True,
    )


@saran_group.command(name="daftar", description="Lihat saran terbaru (bisa difilter status)")
@app_commands.describe(status="Filter status saran", jumlah="Berapa saran ditampilkan")
@app_commands.choices(
    status=[
        app_commands.Choice(name="🆕 Baru", value="baru"),
        app_commands.Choice(name="🛠️ Sedang dikerjakan", value="dikerjakan"),
        app_commands.Choice(name="✅ Diterima", value="diterima"),
        app_commands.Choice(name="❌ Ditolak", value="ditolak"),
    ]
)
async def saran_daftar_cmd(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] | None = None,
    jumlah: app_commands.Range[int, 1, 20] = 8,
):
    if interaction.guild is None:
        return
    items = sg.list_suggestions(
        interaction.guild.id, status=status.value if status else None, limit=int(jumlah)
    )
    if not items:
        await interaction.response.send_message("ℹ️ Belum ada saran tercatat.", ephemeral=True)
        return

    lines = []
    for item in items:
        meta = sg.STATUSES.get(str(item.get("status")), sg.STATUSES["baru"])
        lines.append(
            f"{meta['emoji']} **#{item['id']}** {str(item.get('text'))[:90]} — "
            f"👍 `{len(item.get('up') or [])}` 👎 `{len(item.get('down') or [])}`"
        )
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(
                title="💡 Daftar Saran",
                description="\n".join(lines)[:4000],
            ),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


@saran_group.command(name="status", description="(Staff) Ubah status sebuah saran")
@app_commands.describe(id="Nomor saran", status="Status baru")
@app_commands.choices(
    status=[
        app_commands.Choice(name="🆕 Baru", value="baru"),
        app_commands.Choice(name="🛠️ Sedang dikerjakan", value="dikerjakan"),
        app_commands.Choice(name="✅ Diterima", value="diterima"),
        app_commands.Choice(name="❌ Ditolak", value="ditolak"),
    ]
)
async def saran_status_cmd(
    interaction: discord.Interaction,
    id: app_commands.Range[int, 1, 100000],
    status: app_commands.Choice[str],
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message("⚠️ Command ini khusus **staff**.", ephemeral=True)
        return

    item = sg.set_status(interaction.guild.id, int(id), status.value)
    if item is None:
        await interaction.response.send_message(f"⚠️ Saran `#{id}` tidak ditemukan.", ephemeral=True)
        return
    await sg.save_suggestions_to_disk()

    # Perbarui pesan aslinya agar badge status langsung berubah
    channel_id = sg.get_channel(interaction.guild.id)
    channel = interaction.guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel) and item.get("message_id"):
        try:
            message = await channel.fetch_message(int(item["message_id"]))
            await message.edit(
                embed=sg.build_suggestion_embed(interaction.guild.id, item),
                view=SuggestionVoteView(),
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        else:
            try:
                await channel.send(f"<@{item['author_id']}> saranmu **#{item['id']}** kini berstatus "
                                   f"**{sg.STATUSES[status.value]['label']}**!", delete_after=30)
            except (discord.Forbidden, discord.HTTPException):
                pass

    meta = sg.STATUSES[status.value]
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            f"Saran #{item['id']} — {meta['label']}",
            f"Status saran diperbarui menjadi **{meta['emoji']} {meta['label']}**.\n"
            f"• Pengusul: {sg.mention_author(item)}\n"
            f"• Skor voting: `{sg.score(item):+d}`",
        ),
        ephemeral=True,
    )


@saran_group.command(name="hapus", description="(Admin) Hapus saran beserta pesannya")
@app_commands.describe(id="Nomor saran yang dihapus")
async def saran_hapus_cmd(interaction: discord.Interaction, id: app_commands.Range[int, 1, 100000]):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild)):
        await interaction.response.send_message("⚠️ Hanya **Admin** yang bisa menghapus saran.", ephemeral=True)
        return

    item = sg.get_suggestion(interaction.guild.id, int(id))
    if item is None:
        await interaction.response.send_message(f"⚠️ Saran `#{id}` tidak ditemukan.", ephemeral=True)
        return

    channel_id = sg.get_channel(interaction.guild.id)
    channel = interaction.guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel) and item.get("message_id"):
        try:
            message = await channel.fetch_message(int(item["message_id"]))
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    sg.delete_suggestion(interaction.guild.id, int(id))
    await sg.save_suggestions_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id, "trash", "Saran Dihapus", f"Saran `#{id}` beserta pesannya sudah dihapus."
        ),
        ephemeral=True,
    )


# ==============================================================================
# /embed
# ==============================================================================
class EmbedBuilderModal(discord.ui.Modal, title="Buat Pesan Embed"):
    """Modal pengisian embed — hasilnya dikirim ke channel yang dipilih."""

    def __init__(self, channel: discord.TextChannel, color: discord.Colour):
        super().__init__()
        self.channel = channel
        self.color = color
        self.judul = discord.ui.TextInput(label="Judul", max_length=256, required=False)
        self.deskripsi = discord.ui.TextInput(
            label="Isi pesan", style=discord.TextStyle.paragraph, max_length=3500
        )
        self.gambar = discord.ui.TextInput(
            label="URL gambar/banner (opsional)", required=False, max_length=500
        )
        self.footer = discord.ui.TextInput(label="Footer (opsional)", required=False, max_length=200)
        for item in (self.judul, self.deskripsi, self.gambar, self.footer):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=str(self.judul) or None,
            description=str(self.deskripsi)[:4000],
            colour=self.color,
        )
        image = str(self.gambar or "").strip()
        if image.startswith(("http://", "https://")):
            embed.set_image(url=image)
        footer = str(self.footer or "").strip()
        if footer:
            embed.set_footer(text=footer[:200])
        await self.channel.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Embed terkirim ke {self.channel.mention}.", ephemeral=True
        )


@embed_group.command(name="buat", description="Buat pengumuman embed lewat formulir lalu kirim ke channel")
@app_commands.describe(
    channel="Channel tujuan pengumuman",
    warna="Warna embed: #9B59B6, ungu, biru, merah, hijau, emas, atau abu",
)
async def embed_buat_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    warna: str = "#9B59B6",
):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild or perms.manage_messages)):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    colour = parse_color(warna)
    await interaction.response.send_modal(EmbedBuilderModal(channel, colour))


@embed_group.command(name="cepat", description="Kirim embed tanpa formulir (judul + isi langsung)")
@app_commands.describe(
    channel="Channel tujuan",
    judul="Judul pengumuman",
    isi="Isi pengumuman",
    warna="Warna: #9B59B6 / ungu / biru / merah / hijau / emas / abu",
    gambar="URL gambar banner (opsional)",
)
async def embed_cepat_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    judul: str,
    isi: str,
    warna: str = "#9B59B6",
    gambar: str | None = None,
):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild or perms.manage_messages)):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    embed = discord.Embed(
        title=judul[:256], description=isi[:4000], colour=parse_color(warna)
    )
    if gambar and gambar.startswith(("http://", "https://")):
        embed.set_image(url=gambar)
    ui_theme.apply_embed_theme(embed, interaction.guild.id, footer=interaction.guild.name)

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(f"⚠️ Gagal mengirim embed: {exc}", ephemeral=True)
        return
    await interaction.response.send_message(
        f"✅ Embed terkirim ke {channel.mention}.", ephemeral=True
    )


def register_suggestions_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/saran` & `/embed`."""
    bot.tree.add_command(saran_group)
    bot.tree.add_command(embed_group)


__all__ = ["register_suggestions_cog", "saran_group", "embed_group", "EmbedBuilderModal", "parse_color"]
