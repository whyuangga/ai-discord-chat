"""Cog `/pantau` — highlight kata kunci → DM (0 kuota AI).

Member mendaftarkan kata kunci (maks 10), lalu setiap kali kata itu muncul di chat
server, bot mengirim **DM** berisi tautan pesan, penulis, dan cuplikan singkat.
Pesan **tidak** disimpan ke disk; hanya penghitung yang dicatat.
"""

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

import highlights
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.highlights_cog")

pantau_group = app_commands.Group(
    name="pantau",
    description="Highlight kata kunci → DM saat kata itu muncul di chat — 0 kuota AI",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


def _embed_dm(pesan: discord.Message, kata: str) -> discord.Embed:
    """Kartu ringkas yang dikirim ke DM — tanpa menyimpan isi pesan."""
    cuplikan = highlights.cuplikan(pesan.content, kata)
    embed = discord.Embed(
        title=f"🔔 Kata kunci `{kata}` muncul",
        description=f"{cuplikan[:highlights.PANJANG_CUPLIKAN + 40] or '*(tanpa teks)*'}",
        url=getattr(pesan, "jump_url", None) or None,
        colour=discord.Colour(0x5865F2),
    )
    embed.add_field(name="Penulis", value=getattr(pesan.author, "mention", f"`{getattr(pesan.author, 'id', 0)}`"), inline=True)
    kanal = getattr(pesan.channel, "mention", None) or f"`{getattr(pesan.channel, 'id', 0)}`"
    embed.add_field(name="Channel", value=str(kanal), inline=True)
    embed.add_field(
        name="Server", value=str(getattr(getattr(pesan, "guild", None), "name", "-"))[:100], inline=True
    )
    embed.set_footer(text="Pantau kata kunci · balas /pantau untuk berhenti")
    return embed


async def kirim_highlight(bot, pesan) -> int:
    """Kirim DM untuk satu pesan → jumlah DM terkirim (dipakai juga oleh tes)."""
    guild = getattr(pesan, "guild", None)
    author = getattr(pesan, "author", None)
    if guild is None or author is None or getattr(author, "bot", False):
        return 0
    teks = getattr(pesan, "content", "") or ""
    if len(teks) < 2:
        return 0

    daftar = highlights.cocok(guild.id, teks, channel_id=getattr(pesan.channel, "id", 0))
    terkirim = 0
    for baris in daftar:
        uid = int(baris["user_id"])
        if uid == int(getattr(author, "id", 0)):
            continue  # tidak perlu memberi tahu orang tentang pesannya sendiri
        if not highlights.boleh_kirim(guild.id, uid):
            continue
        target = guild.get_member(uid) if callable(getattr(guild, "get_member", None)) else None
        if target is None:
            continue
        try:
            await target.send(embed=_embed_dm(pesan, baris["kata"]))
        except (discord.Forbidden, discord.HTTPException):
            continue  # DM ditutup → lewati tanpa mengganggu chat
        highlights.catat_terkirim(guild.id, uid, baris["kata"])
        terkirim += 1
    if terkirim:
        await highlights.save_highlights_to_disk()
    return terkirim


# ==============================================================================
# COMMAND
# ==============================================================================
@pantau_group.command(name="tambah", description="Pantau satu kata kunci (kamu akan dapat DM)")
@app_commands.describe(kata="Kata atau frasa yang mau dipantau, mis. 'open order'")
async def pantau_tambah_cmd(interaction: discord.Interaction, kata: str):
    if interaction.guild is None:
        return
    ok, pesan = highlights.tambah_kata(interaction.guild.id, interaction.user.id, kata)
    if ok:
        await highlights.save_highlights_to_disk()
    await interaction.response.send_message(
        ("✅ " if ok else "⚠️ ") + pesan, ephemeral=True
    )


@pantau_group.command(name="hapus", description="Berhenti memantau satu kata kunci")
@app_commands.describe(kata="Kata kunci yang ingin dihapus")
async def pantau_hapus_cmd(interaction: discord.Interaction, kata: str):
    if interaction.guild is None:
        return
    ok, pesan = highlights.hapus_kata(interaction.guild.id, interaction.user.id, kata)
    if ok:
        await highlights.save_highlights_to_disk()
    await interaction.response.send_message(("✅ " if ok else "⚠️ ") + pesan, ephemeral=True)


@pantau_group.command(name="daftar", description="Lihat kata kunci yang kamu pantau")
async def pantau_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    kata = highlights.daftar_kata(interaction.guild.id, interaction.user.id)
    if not kata:
        await interaction.response.send_message(
            "🔔 Belum ada kata kunci. Tambahkan dengan `/pantau tambah kata:open order`.\n"
            "Kamu akan dapat **DM** setiap kali kata itu muncul di chat server ini.",
            ephemeral=True,
        )
        return
    data = (highlights.hl_members.get(interaction.guild.id) or {}).get(interaction.user.id, {})
    baris = [f"• `{satu}`" for satu in kata]
    abaikan_channel = data.get("abaikan_channel") or []
    abaikan_kata = data.get("abaikan_kata") or []
    embed = discord.Embed(
        title="🔔 Kata kunci yang kamu pantau",
        description="\n".join(baris)[:4000],
        colour=discord.Colour(0x5865F2),
    )
    if abaikan_channel:
        embed.add_field(
            name="Channel diabaikan",
            value=" ".join(f"<#{cid}>" for cid in abaikan_channel)[:1024],
            inline=False,
        )
    if abaikan_kata:
        embed.add_field(
            name="Kata diabaikan",
            value=", ".join(f"`{k}`" for k in abaikan_kata)[:1024],
            inline=False,
        )
    embed.set_footer(text=f"{data.get('hit', 0)} DM terkirim · maks {highlights.MAX_KATA_PER_MEMBER} kata kunci")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@pantau_group.command(name="abaikan", description="Abaikan satu channel atau satu kata")
@app_commands.describe(channel="Channel yang tidak memicu highlight", kata="Kata yang tidak memicu highlight")
async def pantau_abaikan_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    kata: str | None = None,
):
    if interaction.guild is None:
        return
    if channel is None and not kata:
        await interaction.response.send_message(
            "⚠️ Pilih salah satu: `channel` atau `kata`.", ephemeral=True
        )
        return
    ok, pesan = highlights.tambah_abaikan(
        interaction.guild.id,
        interaction.user.id,
        channel_id=getattr(channel, "id", None),
        kata=kata,
    )
    if ok:
        await highlights.save_highlights_to_disk()
    await interaction.response.send_message(("✅ " if ok else "⚠️ ") + pesan, ephemeral=True)


@pantau_group.command(name="bersihkan", description="Hapus semua kata kunci & abaikan milikmu")
async def pantau_bersihkan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    terhapus = highlights.bersihkan(interaction.guild.id, interaction.user.id)
    if terhapus:
        await highlights.save_highlights_to_disk()
    await interaction.response.send_message(
        "🧹 Semua setelan highlight-mu dihapus." if terhapus else "ℹ️ Kamu memang belum punya setelan highlight.",
        ephemeral=True,
    )


@pantau_group.command(name="atur", description="Atur highlight server: aktif & channel yang diabaikan (Admin)")
@app_commands.describe(aktif="Nyalakan/matikan fitur highlight", abaikan_channel="Channel yang tidak memicu highlight")
async def pantau_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool = True,
    abaikan_channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **Admin / Manage Server** yang bisa mengatur fitur ini.", ephemeral=True
        )
        return
    cfg = highlights.get_config(interaction.guild.id)
    daftar = list(cfg.get("abaikan_channel") or [])
    if abaikan_channel is not None:
        cid = int(abaikan_channel.id)
        if cid in daftar:
            daftar.remove(cid)
        else:
            daftar.append(cid)
    highlights.set_config(interaction.guild.id, enabled=aktif, abaikan_channel=daftar)
    await highlights.save_highlights_to_disk()
    data = highlights.statistik(interaction.guild.id)
    abaikan = " ".join(f"<#{cid}>" for cid in data["abaikan_channel"]) or "tidak ada"
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Setelan Highlight Disimpan",
            f"Fitur **{'aktif' if data['aktif'] else 'nonaktif'}** · "
            f"pelanggan: **{data['pelanggan']}** · kata kunci: **{data['total_kata']}**\n"
            f"Channel diabaikan: {abaikan}",
        ),
        ephemeral=True,
    )


# ==============================================================================
# LISTENER (dipanggil dari `cogs/events_cog.on_message`)
# ==============================================================================
_terakhir: dict[int, float] = {}


async def maybe_highlight(bot, message) -> int:
    """Periksa satu pesan (maks 1×/detik/server) → jumlah DM terkirim."""
    guild = getattr(message, "guild", None)
    if guild is None:
        return 0
    sekarang = time.time()
    if sekarang - _terakhir.get(int(guild.id), 0) < 1:
        return 0
    _terakhir[int(guild.id)] = sekarang
    return await kirim_highlight(bot, message)


def register_highlights_cog(bot: commands.Bot) -> None:
    """Daftarkan grup `/pantau` ke bot (listener memakai `maybe_highlight`)."""
    bot.tree.add_command(pantau_group)


__all__ = ["pantau_group", "kirim_highlight", "maybe_highlight", "register_highlights_cog"]
