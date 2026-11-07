"""Cog `/lencana` — achievements bertingkat dari data yang sudah dicatat (0 kuota AI).

Member bisa melihat progres sendiri, semua orang bisa melihat papan lencana, dan
staf menentukan role hadiah per tingkat. Fungsi `proses_lencana()` dipanggil dari
alur XP pesan & voice supaya lencana baru langsung diberi tanpa pekerjaan latar
tambahan.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import achievements
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.lencana_cog")

lencana_group = app_commands.Group(
    name="lencana",
    description="Lencana bertingkat (ngobrol, voice, level, undian) — 0 kuota AI",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


def _bar(persen: int) -> str:
    """Bar progres 10 kotak (tanpa emoji, aman untuk semua font)."""
    penuh = max(0, min(10, int(persen) // 10))
    return "▰" * penuh + "▱" * (10 - penuh)


def _baris_progres(progres: list[dict]) -> list[str]:
    baris = []
    for item in progres:
        bintang = "⭐" * item["tingkat"] + "☆" * (item["maks"] - item["tingkat"])
        if item["berikut"] is None:
            lanjut = "maksimum"
        else:
            lanjut = f"{item['nilai']:,} / {item['berikut']:,} {item['satuan']}"
        baris.append(
            f"{item['emoji']} **{item['label']}** {bintang}\n"
            f"   `{_bar(item['persen'])}` {item['persen']}% · {lanjut}"
        )
    return baris


def _embed_progres(member, progres: list[dict], total: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏅 Lencana {member.display_name}",
        description="\n".join(_baris_progres(progres))[:4000],
    )
    embed.set_footer(text=f"{total} tingkat terkumpul · 0 kuota AI")
    return embed


# ==============================================================================
# PEMBERIAN LENCANA (dipanggil dari alur XP)
# ==============================================================================
async def proses_lencana(
    bot,
    guild: discord.Guild | None,
    member,
    *,
    sumber: str = "",
) -> list[dict]:
    """Cek & berikan lencana baru untuk satu member. Aman dipanggil sesering apa pun."""
    if guild is None or member is None or getattr(member, "bot", False):
        return []
    try:
        baru = achievements.cek_member(guild.id, member.id)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Cek lencana dilewati: %s", exc)
        return []
    if not baru:
        return []

    for item in baru:
        role_id = int(item.get("role_id") or 0)
        if not role_id:
            continue
        role = guild.get_role(role_id) if callable(getattr(guild, "get_role", None)) else None
        if role is None:
            continue
        try:
            await member.add_roles(role, reason=f"Lencana {item['label']} tingkat {item['tingkat']}")
        except (discord.Forbidden, discord.HTTPException):
            logger.info("Tidak bisa memberi role lencana %s ke %s", role_id, member.id)

    await achievements.save_achievements_to_disk()

    cfg = achievements.peek_config(guild.id)
    channel = None
    if cfg.get("channel_id"):
        getter = getattr(bot, "get_channel", None) if bot is not None else None
        if callable(getter):
            channel = getter(int(cfg["channel_id"]))
    if channel is None:
        return baru

    for item in baru:
        bintang = "⭐" * item["tingkat"]
        tambahan = f"\n🎁 <@&{item['role_id']}>" if item.get("role_id") else ""
        try:
            await channel.send(
                f"🏅 <@{member.id}> membuka lencana **{item['emoji']} {item['label']}** "
                f"tingkat **{item['tingkat']}/{item['maks']}** {bintang} "
                f"({item['ambang']:,} {item['satuan']}){tambahan}",
                allowed_mentions=discord.AllowedMentions(users=True, roles=True),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass
    return baru


# ==============================================================================
# COMMAND
# ==============================================================================
@lencana_group.command(name="lihat", description="Lihat lencana & progres seorang member")
@app_commands.describe(member="Member yang dilihat (kosongkan untuk dirimu)")
async def lencana_lihat_cmd(interaction: discord.Interaction, member: discord.Member | None = None):
    if interaction.guild is None:
        return
    target = member or interaction.user
    progres = achievements.progres(interaction.guild.id, target.id)
    total = sum(item["tingkat"] for item in progres)
    embed = _embed_progres(target, progres, total)
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(embed, interaction.guild.id)
    )


@lencana_group.command(name="papan", description="Papan lencana server (tingkat terbanyak)")
async def lencana_papan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    daftar = achievements.papan(interaction.guild.id, limit=10)
    if not daftar:
        await interaction.response.send_message(
            "🏅 Belum ada lencana yang tercatat. Lencana muncul otomatis saat member "
            "aktif ngobrol, ikut voice, naik level, atau menang undian.",
            ephemeral=True,
        )
        return
    medali = ("🥇", "🥈", "🥉")
    baris = [
        f"{medali[idx] if idx < 3 else f'`{idx + 1}.`'} <@{row['user_id']}> — "
        f"**{row['total']} tingkat**"
        for idx, row in enumerate(daftar)
    ]
    embed = ui_theme.apply_embed_theme(
        discord.Embed(title="🏅 Papan Lencana", description="\n".join(baris)[:4000]),
        interaction.guild.id,
    )
    await interaction.response.send_message(embed=embed)


@lencana_group.command(name="periksa", description="Segarkan lencana seorang member sekarang (staf)")
@app_commands.describe(member="Member yang diperiksa (kosongkan untuk dirimu)")
async def lencana_periksa_cmd(interaction: discord.Interaction, member: discord.Member | None = None):
    if interaction.guild is None:
        return
    target = member or interaction.user
    bot = getattr(interaction, "client", None) or getattr(interaction, "bot", None)
    baru = await proses_lencana(bot, interaction.guild, target)
    if not baru:
        await interaction.response.send_message(
            f"ℹ️ Tidak ada lencana baru untuk **{target.display_name}** "
            "(progresnya belum melewati tingkat berikutnya).",
            ephemeral=True,
        )
        return
    baris = "\n".join(
        f"{item['emoji']} **{item['label']}** tingkat {item['tingkat']}/{item['maks']}"
        for item in baru
    )
    await interaction.response.send_message(
        f"✅ {len(baru)} lencana diberikan ke **{target.display_name}**:\n{baris}",
        ephemeral=True,
    )


@lencana_group.command(name="atur", description="Atur channel pengumuman & status lencana (Admin)")
@app_commands.describe(channel="Channel pengumuman lencana (kosongkan = tanpa pengumuman)", aktif="Nyalakan/matikan lencana")
async def lencana_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    aktif: bool = True,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **Admin / Manage Server** yang bisa mengatur lencana.", ephemeral=True
        )
        return

    achievements.set_config(
        interaction.guild.id,
        enabled=aktif,
        channel_id=getattr(channel, "id", None) if channel is not None else None,
    )
    await achievements.save_achievements_to_disk()
    data = achievements.statistik(interaction.guild.id)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Setelan Lencana Disimpan",
            f"Lencana {'**aktif**' if data['aktif'] else '**nonaktif**'} · "
            f"pengumuman: {channel.mention if channel else 'tanpa pengumuman'}\n"
            f"Role hadiah terpasang: **{data['hadiah_role']}**",
        ),
        ephemeral=True,
    )


@lencana_group.command(name="role", description="Pasang/hapus role hadiah untuk satu tingkat lencana (Admin)")
@app_commands.describe(
    kunci="Lencana",
    tingkat="Tingkat lencana (1 = pertama)",
    role="Role hadiah (kosongkan untuk menghapus)",
)
@app_commands.choices(
    kunci=[
        app_commands.Choice(name=f"{item['emoji']} {item['label']}", value=item["kunci"])
        for item in achievements.ACHIEVEMENTS
    ]
)
async def lencana_role_cmd(
    interaction: discord.Interaction,
    kunci: app_commands.Choice[str],
    tingkat: app_commands.Range[int, 1, 5],
    role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    if not _is_admin(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **Admin / Manage Server** yang bisa mengatur role hadiah.", ephemeral=True
        )
        return
    ok, pesan = achievements.set_reward(
        interaction.guild.id, kunci.value, int(tingkat), getattr(role, "id", None)
    )
    if ok:
        await achievements.save_achievements_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok" if ok else "warn",
            "Role Hadiah Lencana" if ok else "Gagal Menyimpan",
            pesan,
        ),
        ephemeral=True,
    )


def register_lencana_cog(bot: commands.Bot) -> None:
    """Mendaftarkan group `/lencana` ke bot."""
    bot.tree.add_command(lencana_group)


__all__ = ["lencana_group", "proses_lencana", "register_lencana_cog"]
