"""Cog `/tempvoice` — voice room sementara ("Join to Create")."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import temp_voice as tv
import ui_theme

logger = logging.getLogger("gemini_bot.tempvoice_cog")

tempvoice_group = app_commands.Group(
    name="tempvoice",
    description="Voice room sementara: member masuk hub → dapat room sendiri, auto-hapus saat kosong",
    guild_only=True,
)


async def _reject_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id if interaction.guild else None,
            "error",
            "Butuh Izin Admin",
            "Pengaturan Temp Voice khusus **Admin / pengelola server**.",
        ),
        ephemeral=True,
    )


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


def _own_room(interaction: discord.Interaction) -> int | None:
    """ID voice channel tempat pemanggil berada (bila dia pemilik room)."""
    voice = getattr(getattr(interaction.user, "voice", None), "channel", None)
    if voice is None:
        return None
    if tv.is_owner(voice.id, interaction.user.id):
        return voice.id
    return None


@tempvoice_group.command(
    name="atur",
    description="(Admin) Jadikan sebuah voice channel sebagai pintu masuk pembuat room",
)
@app_commands.describe(
    hub="Voice channel yang dijadikan tombol '➕ Buat Voice'",
    aktif="True untuk mengaktifkan, False untuk mematikan",
    nama="Template nama room: {user} = nama member (contoh: '🔊 Room {user}')",
    limit="Batas jumlah orang per room (0 = tanpa batas)",
)
async def tempvoice_atur_cmd(
    interaction: discord.Interaction,
    hub: discord.VoiceChannel | None = None,
    aktif: bool = True,
    nama: str | None = None,
    limit: app_commands.Range[int, 0, 99] | None = None,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        return await _reject_admin(interaction)

    if not aktif:
        tv.set_hub(interaction.guild.id, 0, enabled=False)
        await tv.save_temp_voice_to_disk()
        await interaction.response.send_message(
            embed=ui_theme.status_embed(
                interaction.guild.id,
                "lock",
                "Temp Voice Dimatikan",
                "Room yang sudah ada akan dihapus otomatis saat kosong.",
            ),
            ephemeral=True,
        )
        return

    if hub is None:
        await interaction.response.send_message(
            "⚠️ Pilih `hub:` terlebih dahulu — buat voice channel baru (mis. **➕ Buat Voice**) "
            "lalu jalankan `/tempvoice atur hub:#➕ Buat Voice`.",
            ephemeral=True,
        )
        return

    config = tv.set_hub(interaction.guild.id, hub.id, name_template=nama, user_limit=limit)
    await tv.save_temp_voice_to_disk()

    body = (
        f"• **Hub:** {hub.mention}\n"
        f"• **Template nama:** `{config['name_template']}`\n"
        f"• **Batas slot:** `{config['user_limit'] or 'tanpa batas'}`\n\n"
        "Member yang masuk ke hub akan otomatis mendapat room sendiri. "
        "Pemilik room bisa memakai `/tempvoice kunci`, `/tempvoice nama`, `/tempvoice limit`, "
        "dan `/tempvoice tendang`. Room terhapus sendiri saat kosong."
    )
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🔊 Temp Voice Aktif", description=body), interaction.guild.id
        ),
        ephemeral=True,
    )


@tempvoice_group.command(name="status", description="Lihat konfigurasi hub & jumlah room aktif")
async def tempvoice_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    config = tv.get_config(interaction.guild.id)
    rooms = tv.rooms_of_guild(interaction.guild.id)
    if not config:
        await interaction.response.send_message(
            "ℹ️ **Temp Voice belum aktif.** Aktifkan dengan `/tempvoice atur hub:#➕ Buat Voice`.",
            ephemeral=True,
        )
        return

    lines = [
        f"• **Hub:** <#{config['hub_id']}>",
        f"• **Template nama:** `{config['name_template']}`",
        f"• **Batas slot:** `{config['user_limit'] or 'tanpa batas'}`",
        f"• **Room aktif sekarang:** `{len(rooms)}` / {tv.MAX_ROOMS_PER_GUILD}",
    ]
    for channel_id, room in list(rooms.items())[:8]:
        lock = "🔒" if room.get("locked") else "🔓"
        lines.append(f"  {lock} <#{channel_id}> — <@{room['owner_id']}>")
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🔊 Status Temp Voice", description="\n".join(lines)[:4000]),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


@tempvoice_group.command(name="kunci", description="Kunci room-mu (hanya yang diizinkan bisa masuk)")
@app_commands.describe(aktif="True untuk mengunci, False untuk membuka kembali")
async def tempvoice_kunci_cmd(interaction: discord.Interaction, aktif: bool = True):
    if interaction.guild is None:
        return
    channel_id = _own_room(interaction)
    if channel_id is None:
        await interaction.response.send_message(
            "⚠️ Kamu harus berada di **room sementara milikmu** untuk memakai ini.",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message("⚠️ Room tidak ditemukan.", ephemeral=True)
        return

    try:
        await channel.set_permissions(
            interaction.guild.default_role,
            connect=not aktif,
            reason="Temp Voice: kunci/buka room oleh pemilik",
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(f"⚠️ Gagal mengubah izin: {exc}", ephemeral=True)
        return

    tv.set_room_locked(channel_id, aktif)
    await tv.save_temp_voice_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "lock" if aktif else "ok",
            "Room Dikunci" if aktif else "Room Dibuka",
            f"{channel.mention} " + (
                "hanya bisa dimasuki member yang diizinkan." if aktif
                else "kembali terbuka untuk semua member."
            ),
        ),
        ephemeral=True,
    )


@tempvoice_group.command(name="nama", description="Ganti nama room-mu")
@app_commands.describe(nama="Nama baru room (maks 100 karakter)")
async def tempvoice_nama_cmd(interaction: discord.Interaction, nama: str):
    if interaction.guild is None:
        return
    channel_id = _own_room(interaction)
    if channel_id is None:
        await interaction.response.send_message(
            "⚠️ Kamu harus berada di **room sementara milikmu**.", ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message("⚠️ Room tidak ditemukan.", ephemeral=True)
        return

    new_name = tv.sanitize_room_name(nama)
    if not new_name:
        await interaction.response.send_message("⚠️ Nama tidak boleh kosong.", ephemeral=True)
        return

    try:
        await channel.edit(name=new_name, reason="Temp Voice: ganti nama oleh pemilik")
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(f"⚠️ Gagal mengganti nama: {exc}", ephemeral=True)
        return

    tv.set_room_name(channel_id, new_name)
    await tv.save_temp_voice_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id, "ok", "Nama Room Diubah", f"Sekarang: **{new_name}**"
        ),
        ephemeral=True,
    )


@tempvoice_group.command(name="limit", description="Batasi jumlah orang di room-mu")
@app_commands.describe(jumlah="0 = tanpa batas, maks 99")
async def tempvoice_limit_cmd(
    interaction: discord.Interaction, jumlah: app_commands.Range[int, 0, 99]
):
    if interaction.guild is None:
        return
    channel_id = _own_room(interaction)
    if channel_id is None:
        await interaction.response.send_message(
            "⚠️ Kamu harus berada di **room sementara milikmu**.", ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message("⚠️ Room tidak ditemukan.", ephemeral=True)
        return

    try:
        await channel.edit(user_limit=int(jumlah), reason="Temp Voice: batas slot oleh pemilik")
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(f"⚠️ Gagal mengubah batas: {exc}", ephemeral=True)
        return

    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Batas Slot Diubah",
            f"Room ini sekarang menampung **{jumlah or 'tanpa batas'}** orang.",
        ),
        ephemeral=True,
    )


@tempvoice_group.command(name="tendang", description="Keluarkan member dari room-mu")
@app_commands.describe(member="Member yang ingin dikeluarkan dari room")
async def tempvoice_tendang_cmd(interaction: discord.Interaction, member: discord.Member):
    if interaction.guild is None:
        return
    channel_id = _own_room(interaction)
    if channel_id is None:
        await interaction.response.send_message(
            "⚠️ Kamu harus berada di **room sementara milikmu**.", ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message("⚠️ Room tidak ditemukan.", ephemeral=True)
        return
    if member.id == interaction.user.id or getattr(member, "bot", False):
        await interaction.response.send_message("⚠️ Tidak bisa menendang diri sendiri/bot.", ephemeral=True)
        return

    try:
        await member.move_to(None, reason="Temp Voice: dikeluarkan pemilik room")
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(
            f"⚠️ Gagal mengeluarkan {member.mention}: {exc}", ephemeral=True
        )
        return

    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id, "ok", "Member Dikeluarkan", f"{member.mention} keluar dari room-mu."
        ),
        ephemeral=True,
    )


def register_tempvoice_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/tempvoice` + listener pembuatan room otomatis."""
    bot.tree.add_command(tempvoice_group)

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Membuat room saat member masuk hub & menghapusnya saat kosong."""
        if getattr(member, "bot", False) and before.channel == after.channel:
            return
        try:
            await tv.handle_voice_update(before, after, member)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Temp Voice gagal memproses perubahan voice: %s", exc)


__all__ = ["register_tempvoice_cog", "tempvoice_group"]
