"""Cog perkakas ringan: `/afk`, `/thread-otomatis`, `/lockdown`, & `/backup`."""

import io
import json
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

import server_tools as st
import ui_theme

logger = logging.getLogger("gemini_bot.utility_cog")

afk_group = app_commands.Group(
    name="afk", description="Tandai dirimu sedang AFK — warga lain otomatis diberi tahu", guild_only=True
)

thread_group = app_commands.Group(
    name="thread-otomatis",
    description="Buat thread otomatis untuk setiap pesan baru di channel tertentu",
    default_permissions=discord.Permissions(manage_threads=True),
    guild_only=True,
)

lockdown_group = app_commands.Group(
    name="lockdown",
    description="Kunci darurat: cabut izin kirim @everyone di semua text channel",
    default_permissions=discord.Permissions(administrator=True),
    guild_only=True,
)

backup_group = app_commands.Group(
    name="backup",
    description="Ekspor struktur server (role, kategori, channel, izin) ke berkas JSON",
    default_permissions=discord.Permissions(administrator=True),
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


# ==============================================================================
# AFK
# ==============================================================================
@afk_group.command(name="atur", description="Tandai dirimu AFK dengan alasan tertentu")
@app_commands.describe(alasan="Alasan AFK (mis. 'tidur', 'sekolah sampai jam 3')")
async def afk_atur_cmd(interaction: discord.Interaction, alasan: str = "tanpa alasan"):
    if interaction.guild is None:
        return
    entry = st.set_afk(interaction.guild.id, interaction.user.id, alasan)
    await st.save_server_tools_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "info",
            "Status AFK Aktif",
            f"Alasan: **{entry['reason']}**\n\n"
            "Warga yang menyebut namamu akan diberi tahu, dan status ini hilang otomatis "
            "begitu kamu bicara lagi.",
        ),
        ephemeral=True,
    )


@afk_group.command(name="daftar", description="Lihat member yang sedang AFK")
async def afk_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    items = st.afk_users.get(interaction.guild.id) or {}
    if not items:
        await interaction.response.send_message("ℹ️ Tidak ada member yang sedang AFK.", ephemeral=True)
        return

    lines = [
        f"• <@{uid}> — {entry['reason']} *({st.afk_since_text(entry)} lalu)*"
        for uid, entry in list(items.items())[:20]
    ]
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="😴 Daftar AFK", description="\n".join(lines)[:4000]),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


@afk_group.command(name="hapus", description="Hapus status AFK-mu lebih awal")
async def afk_hapus_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    removed = st.pop_afk(interaction.guild.id, interaction.user.id)
    if removed:
        await st.save_server_tools_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if removed else "info",
            "Status AFK Dihapus" if removed else "Kamu Tidak AFK",
            "Status AFK-mu sudah dilepas." if removed else "Tidak ada status AFK untuk dihapus.",
        ),
        ephemeral=True,
    )


# ==============================================================================
# THREAD OTOMATIS
# ==============================================================================
@thread_group.command(name="aktifkan", description="Buat thread otomatis untuk pesan baru di channel ini")
@app_commands.describe(channel="Channel yang dijadikan auto-thread", arsip_menit="Thread diarsip setelah N menit tidak aktif")
async def thread_aktifkan_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    arsip_menit: app_commands.Range[int, 60, 10080] = 1440,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        await interaction.response.send_message("⚠️ Pilih text channel yang valid.", ephemeral=True)
        return

    st.enable_auto_thread(interaction.guild.id, target.id, archive_minutes=int(arsip_menit))
    await st.save_server_tools_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Auto-Thread Aktif",
            f"Channel: {target.mention}\n"
            f"• Arsip otomatis setelah **{arsip_menit // 60} jam** tidak aktif\n"
            "• Setiap pesan baru akan dibuatkan thread",
        ),
        ephemeral=True,
    )


@thread_group.command(name="matikan", description="Hentikan thread otomatis di channel ini")
@app_commands.describe(channel="Channel yang dihentikan auto-thread-nya")
async def thread_matikan_cmd(
    interaction: discord.Interaction, channel: discord.TextChannel | None = None
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        await interaction.response.send_message("⚠️ Pilih text channel yang valid.", ephemeral=True)
        return

    removed = st.disable_auto_thread(interaction.guild.id, target.id)
    await st.save_server_tools_to_disk()
    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if removed else "info",
            "Auto-Thread Dimatikan" if removed else "Bukan Channel Auto-Thread",
            f"{target.mention} tidak lagi membuat thread otomatis." if removed
            else f"{target.mention} memang tidak diatur sebagai auto-thread.",
        ),
        ephemeral=True,
    )


@thread_group.command(name="status", description="Lihat daftar channel dengan thread otomatis")
async def thread_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    items = st.list_auto_threads(interaction.guild.id)
    if not items:
        await interaction.response.send_message("ℹ️ Belum ada channel auto-thread.", ephemeral=True)
        return
    lines = [
        f"• <#{cid}> — arsip setelah `{config['archive'] // 60}` jam"
        for cid, config in list(items.items())[:20]
    ]
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🧵 Auto-Thread", description="\n".join(lines)[:4000]),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


# ==============================================================================
# LOCKDOWN
# ==============================================================================
@lockdown_group.command(name="aktif", description="Kunci semua text channel (darurat) atau buka kembali")
@app_commands.describe(aktif="True = kunci semua channel, False = buka kembali", alasan="Alasan (wajib untuk audit)")
async def lockdown_aktif_cmd(
    interaction: discord.Interaction, aktif: bool = True, alasan: str = "darurat"
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Lockdown hanya untuk **Admin**.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    if aktif:
        locked, failed = await st.start_lockdown(interaction.guild, interaction.user.id, alasan)
        if locked == 0 and failed == 0:
            await interaction.followup.send(
                "ℹ️ Lockdown sudah aktif (atau semua channel sudah terkunci sebelumnya).", ephemeral=True
            )
            return
        await interaction.followup.send(
            embed=ui_theme.status_embed(
                interaction.guild.id,
                "lock",
                "Lockdown Aktif",
                f"**{locked}** text channel dikunci"
                + (f", **{failed}** gagal (cek izin bot)" if failed else "")
                + ".\n\nBuka kembali dengan `/lockdown aktif aktif:False`.",
                footer=f"Alasan: {alasan[:80]}",
            ),
            ephemeral=True,
        )
        return

    restored = await st.stop_lockdown(interaction.guild)
    await interaction.followup.send(
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if restored else "info",
            "Lockdown Dicabut" if restored else "Tidak Ada Lockdown",
            f"**{restored}** channel dibuka kembali." if restored
            else "Server ini tidak sedang dalam lockdown.",
        ),
        ephemeral=True,
    )


@lockdown_group.command(name="status", description="Cek apakah server sedang dalam lockdown")
async def lockdown_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    state = st.lockdown_active(interaction.guild.id)
    if not state:
        await interaction.response.send_message("🔓 Server **tidak** dalam lockdown.", ephemeral=True)
        return
    duration = int(time.time() - float(state.get("since") or 0))
    await interaction.response.send_message(
        f"🔒 **Lockdown aktif** sejak `{duration // 60}` menit lalu oleh <@{state.get('by')}>\n"
        f"• Channel terkunci: `{len(state.get('channels') or [])}`\n"
        f"• Alasan: {state.get('reason') or '-'}",
        ephemeral=True,
    )


# ==============================================================================
# BACKUP STRUKTUR SERVER
# ==============================================================================
def _role_payload(role: discord.Role) -> dict:
    return {
        "name": role.name,
        "permissions": role.permissions.value,
        "colour": role.colour.value,
        "hoist": role.hoist,
        "mentionable": role.mentionable,
        "position": role.position,
    }


def _overwrite_payload(channel: discord.abc.GuildChannel) -> list[dict]:
    payload = []
    for target, overwrite in channel.overwrites.items():
        allow, deny = overwrite.pair()
        payload.append(
            {
                "target_type": "role" if isinstance(target, discord.Role) else "member",
                "target_id": target.id,
                "target_name": getattr(target, "name", str(target)),
                "allow": allow.value,
                "deny": deny.value,
            }
        )
    return payload


def build_server_backup(guild: discord.Guild) -> dict:
    """Menyusun snapshot struktur server (tanpa pesan) — siap disimpan sebagai JSON."""
    categories = []
    for category in guild.categories:
        categories.append(
            {
                "id": category.id,
                "name": category.name,
                "position": category.position,
                "overwrites": _overwrite_payload(category),
            }
        )

    channels = []
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        entry = {
            "id": channel.id,
            "name": channel.name,
            "type": str(channel.type),
            "position": getattr(channel, "position", 0),
            "category_id": getattr(getattr(channel, "category", None), "id", None),
            "overwrites": _overwrite_payload(channel),
        }
        # Duck-typing: aman untuk semua jenis channel (termasuk tipe baru dari Discord)
        if hasattr(channel, "slowmode_delay"):
            entry["topic"] = getattr(channel, "topic", None)
            entry["nsfw"] = getattr(channel, "nsfw", False)
            entry["slowmode"] = getattr(channel, "slowmode_delay", 0)
        if hasattr(channel, "bitrate"):
            entry["bitrate"] = getattr(channel, "bitrate", None)
            entry["user_limit"] = getattr(channel, "user_limit", 0)
        channels.append(entry)

    return {
        "meta": {
            "generated_at": discord.utils.utcnow().isoformat(),
            "version": 1,
            "guild_id": guild.id,
            "guild_name": guild.name,
            "member_count": getattr(guild, "member_count", 0),
        },
        "roles": [_role_payload(role) for role in guild.roles if not role.is_default()],
        "categories": categories,
        "channels": sorted(channels, key=lambda item: item.get("position", 0)),
    }


@backup_group.command(name="struktur", description="Ekspor role, kategori, channel, & izin ke berkas JSON")
async def backup_struktur_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message("⚠️ Backup hanya untuk **Admin**.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    snapshot = build_server_backup(interaction.guild)
    raw = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"backup-struktur-{interaction.guild.id}.json"
    summary = (
        f"• **Role:** {len(snapshot['roles'])}\n"
        f"• **Kategori:** {len(snapshot['categories'])}\n"
        f"• **Channel:** {len(snapshot['channels'])}\n"
        f"• **Ukuran berkas:** {len(raw) / 1024:.1f} KB\n\n"
        "Simpan berkas ini di tempat aman (mis. channel `#bot-backup` atau Google Drive). "
        "Backup ini **tidak berisi pesan** dan bersifat **baca-saja** — bot tidak akan mengubah server "
        "dari berkas ini."
    )
    await interaction.followup.send(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🗄️ Backup Struktur Server", description=summary),
            interaction.guild.id,
        ),
        file=discord.File(io.BytesIO(raw), filename=filename),
        ephemeral=True,
    )


async def handle_message_tools(message: discord.Message) -> None:
    """Dipanggil dari listener `on_message`: bersihkan AFK & buat thread otomatis."""
    if message.guild is None or getattr(message.author, "bot", False):
        return

    guild_id = message.guild.id

    # 1. Penulis sedang AFK → status dilepas & beri tahu dia kembali
    if st.pop_afk(guild_id, message.author.id):
        await st.save_server_tools_to_disk()
        try:
            await message.channel.send(
                f"👋 Selamat datang kembali {message.author.mention}! Status AFK kamu sudah dihapus.",
                delete_after=8,
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    # 2. Ada member AFK yang disebut → beri tahu alasannya
    mentions = st.afk_mentions(guild_id, message.content)
    if mentions:
        lines = [
            f"😴 {mentioned} sedang AFK — {entry['reason']} *({st.afk_since_text(entry)} lalu)*"
            for mentioned, entry in mentions[:3]
        ]
        try:
            await message.reply("\n".join(lines)[:1900], mention_author=False, delete_after=90)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # 3. Auto-thread untuk channel yang diatur Admin
    config = st.auto_thread_config(guild_id, message.channel.id)
    if config and isinstance(message.channel, discord.TextChannel):
        if message.type in (discord.MessageType.default, discord.MessageType.reply):
            try:
                await message.create_thread(
                    name=st.thread_name_for(message),
                    auto_archive_duration=int(config.get("archive") or 1440),
                    reason="Auto-thread oleh bot",
                )
            except (discord.Forbidden, discord.HTTPException):
                logger.info("Tidak bisa membuat thread di %s", message.channel.id)


def register_utility_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/afk`, `/thread-otomatis`, `/lockdown`, & `/backup`."""
    bot.tree.add_command(afk_group)
    bot.tree.add_command(thread_group)
    bot.tree.add_command(lockdown_group)
    bot.tree.add_command(backup_group)


__all__ = [
    "handle_message_tools",
    "register_utility_cog",
    "afk_group",
    "thread_group",
    "lockdown_group",
    "backup_group",
    "build_server_backup",
]
