"""Command Slash Tier 2C: `/level` (Leveling & XP) dan `/tiket` (Tiket Dukungan).

Keduanya berjalan **tanpa kuota Gemini** dan default NONAKTIF sampai Admin
menyalakannya. Tiket dibuat sebagai **private thread** sehingga tidak memakan
slot channel server.
"""

import io
import logging

import discord
import channel_targets
from discord import app_commands
from discord.ext import commands

import economy
import levels
import rank_card
import tickets
import ui_kit
import ui_theme
import voice_activity
from config import (
    LEVELS_COOLDOWN_SEC,
    LEVELS_MAX_LEVEL,
    LEVELS_MAX_MEMBERS,
    TICKET_MAX_OPEN_PER_USER,
)
from views import send_rating_prompt, send_ticket_panel

logger = logging.getLogger("gemini_bot.growth_cog")


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.",
        ephemeral=True,
    )


# ==============================================================================
# /level — LEVELING & XP
# ==============================================================================
def filename_kartu(data: dict) -> str:
    """Nama berkas kartu rank (aman, tanpa karakter aneh)."""
    return f"kartu-rank-{int(data.get('user_id') or 0)}.png"


level_group = app_commands.Group(
    name="level",
    description="Level & XP member: lihat kartu level, papan peringkat, & atur hadiah role",
    guild_only=True,
)


@level_group.command(name="lihat", description="Lihat kartu level & XP kamu (atau member lain)")
@app_commands.describe(member="Member yang ingin dilihat (kosongkan untuk dirimu sendiri)")
async def level_lihat_cmd(interaction: discord.Interaction, member: discord.Member | None = None):
    if interaction.guild is None:
        return

    target = member or interaction.user
    cfg = levels.get_level_config(interaction.guild.id)
    if not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Fitur leveling belum aktif di server ini. "
            "Admin bisa menyalakannya dengan `/level atur aktif:True`.",
            ephemeral=True,
        )
        return

    data = levels.get_member_level(interaction.guild.id, target.id)
    await interaction.response.send_message(
        embed=levels.build_level_embed(target, data, cfg),
        ephemeral=True,
    )


@level_group.command(
    name="kartu",
    description="Kartu rank PNG (level, XP, peringkat) — dirender server, 0 kuota AI",
)
@app_commands.describe(
    member="Member yang ingin dibuatkan kartu (kosongkan untuk dirimu sendiri)",
    publik="True untuk mengirim kartu di channel, bukan hanya untukmu",
)
async def level_kartu_cmd(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
    publik: bool = False,
):
    if interaction.guild is None:
        return

    cfg = levels.get_level_config(interaction.guild.id)
    if not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Fitur leveling belum aktif di server ini. "
            "Admin bisa menyalakannya dengan `/level atur aktif:True`.",
            ephemeral=True,
        )
        return
    if not rank_card.kartu_aktif(interaction.guild.id):
        await interaction.response.send_message(
            "ℹ️ Kartu rank dimatikan di server ini (Admin: dashboard → **Inti & level** "
            "→ *Kartu rank*). Pakai `/level lihat` untuk versi teks.",
            ephemeral=True,
        )
        return

    target = member or interaction.user
    await interaction.response.defer(ephemeral=not publik)

    data = rank_card.data_kartu(
        interaction.guild.id,
        target.id,
        nama=getattr(target, "display_name", "") or getattr(target, "name", ""),
        guild_name=interaction.guild.name,
    )
    png = await rank_card.render_kartu(
        data, avatar_bytes=await rank_card.baca_avatar(target)
    )
    if not png:
        await interaction.followup.send(
            embed=levels.build_level_embed(target, data, cfg),
            ephemeral=not publik,
        )
        return

    embed = discord.Embed(
        title=f"🖼️ Kartu rank · {getattr(target, 'display_name', 'Member')}",
        description="\n".join(rank_card.baris_data(data)),
        color=ui_theme.accent_color(interaction.guild.id),
    )
    embed.set_image(url=f"attachment://{filename_kartu(data)}")
    embed.set_footer(text="Dirender di server bot · tanpa kuota AI")
    await interaction.followup.send(
        embed=embed,
        file=discord.File(io.BytesIO(png), filename=filename_kartu(data)),
        ephemeral=not publik,
    )


@level_group.command(name="papan", description="Papan peringkat level server (top member paling aktif)")
@app_commands.describe(halaman="Halaman papan peringkat (default 1)")
async def level_papan_cmd(interaction: discord.Interaction, halaman: int = 1):
    if interaction.guild is None:
        return

    cfg = levels.get_level_config(interaction.guild.id)
    if not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Fitur leveling belum aktif di server ini.", ephemeral=True
        )
        return

    page_size = 10
    rows, page, total_pages = levels.leaderboard(
        interaction.guild.id, limit=page_size, page=max(0, int(halaman) - 1)
    )
    total_members = sum(
        1 for key in levels.levels if key.startswith(f"{interaction.guild.id}:")
    )
    await interaction.response.send_message(
        embed=levels.build_leaderboard_embed(
            interaction.guild,
            rows,
            page=page,
            total_pages=total_pages,
            total_members=total_members,
            page_size=page_size,
        )
    )


@level_group.command(name="atur", description="Aktifkan leveling & atur XP, jeda, pengumuman, & channel abaikan")
@app_commands.describe(
    aktif="False untuk mematikan sistem level (data XP tetap tersimpan)",
    pengumuman="True untuk mengumumkan saat ada member naik level",
    channel_pengumuman="Channel khusus pengumuman naik level (kosongkan = balas di channel asal)",
    jeda="Jeda minimum antar XP per member dalam detik (0-3600)",
    xp_minimal="XP minimum per pesan (1-100)",
    xp_maksimal="XP maksimum per pesan (1-100)",
    abaikan_channel="Channel yang tidak memberikan XP (mis. #spam)",
    abaikan_role="Role yang tidak mendapatkan XP (mis. bot/role khusus)",
)
async def level_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool = True,
    pengumuman: bool | None = None,
    channel_pengumuman: discord.TextChannel | None = None,
    jeda: app_commands.Range[int, 0, 3600] | None = None,
    xp_minimal: app_commands.Range[int, 1, 100] | None = None,
    xp_maksimal: app_commands.Range[int, 1, 100] | None = None,
    abaikan_channel: discord.TextChannel | None = None,
    abaikan_role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not aktif:
        levels.disable_leveling(interaction.guild.id)
        await levels.save_levels_to_disk()
        await interaction.response.send_message(
            "🛑 **Sistem level dimatikan.** Data XP lama tetap tersimpan.",
            ephemeral=True,
        )
        return

    existing = levels.get_level_config(interaction.guild.id)
    changes: dict = {"aktif": True}
    if pengumuman is not None:
        changes["announce"] = bool(pengumuman)
    if channel_pengumuman is not None:
        changes["announce_channel_id"] = channel_pengumuman.id
    if jeda is not None:
        changes["cooldown"] = int(jeda)
    if xp_minimal is not None:
        changes["xp_min"] = int(xp_minimal)
    if xp_maksimal is not None:
        changes["xp_max"] = int(xp_maksimal)
    if abaikan_channel is not None:
        changes["ignore_channels"] = sorted(
            set(existing.get("ignore_channels") or []) | {abaikan_channel.id}
        )
    if abaikan_role is not None:
        changes["ignore_roles"] = sorted(
            set(existing.get("ignore_roles") or []) | {abaikan_role.id}
        )

    cfg = levels.set_level_config(interaction.guild.id, **changes) or levels.get_level_config(
        interaction.guild.id
    )
    await levels.save_levels_to_disk()

    announce_channel = cfg.get("announce_channel_id")
    await interaction.response.send_message(
        f"✅ **Sistem level aktif!**\n"
        f"• **XP per pesan:** `{cfg['xp_min']}–{cfg['xp_max']}`\n"
        f"• **Jeda per member:** `{cfg['cooldown']}` detik\n"
        f"• **Pengumuman naik level:** {'✅ aktif' if cfg.get('announce') else '⛔ nonaktif'}\n"
        f"• **Channel pengumuman:** {f'<#{announce_channel}>' if announce_channel else '_di channel asal_'}\n"
        f"• **Channel diabaikan:** `{len(cfg.get('ignore_channels') or [])}` • "
        f"**Role diabaikan:** `{len(cfg.get('ignore_roles') or [])}`\n"
        f"> Beri hadiah role dengan `/level role level:5 role:@Aktif`.",
        ephemeral=True,
    )


@level_group.command(name="role", description="Atur role hadiah yang otomatis diberikan saat member mencapai level tertentu")
@app_commands.describe(
    level="Level yang memicu pemberian role (1-100)",
    role="Role yang diberikan (kosongkan untuk menghapus hadiah level ini)",
)
async def level_role_cmd(
    interaction: discord.Interaction,
    level: app_commands.Range[int, 1, 100],
    role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    cfg = levels.set_level_role(interaction.guild.id, int(level), role.id if role else None)
    await levels.save_levels_to_disk()
    mapping = cfg.get("level_roles") or {}
    preview = ", ".join(
        f"L{v}→<@&{rid}>" for v, rid in sorted(mapping.items(), key=lambda kv: int(kv[0]))[:8]
    )
    await interaction.response.send_message(
        (
            f"🎁 Level **{int(level)}** kini memberi {role.mention}."
            if role
            else f"🗑️ Hadiah role untuk level **{int(level)}** dihapus."
        )
        + (f"\n**Peta hadiah saat ini:** {preview}" if preview else "\n_Belum ada hadiah role._"),
        ephemeral=True,
    )


@level_group.command(name="status", description="Lihat konfigurasi & statistik sistem level server ini")
async def level_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = levels.level_guilds.get(interaction.guild.id)
    if not cfg or not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ **Leveling NONAKTIF.** Aktifkan dengan `/level atur aktif:True`.",
            ephemeral=True,
        )
        return

    members = [key for key in levels.levels if key.startswith(f"{interaction.guild.id}:")]
    top_xp = max(
        (int(levels.levels[key].get("xp") or 0) for key in members), default=0
    )
    mapping = cfg.get("level_roles") or {}
    roles_preview = ", ".join(f"L{v}" for v in sorted(mapping, key=lambda v: int(v))[:10]) or "_belum ada_"
    await interaction.response.send_message(
        f"📈 **Sistem Level Aktif**\n"
        f"• **XP per pesan:** `{cfg['xp_min']}–{cfg['xp_max']}` (jeda `{cfg['cooldown']}` dtk)\n"
        f"• **Member terdata:** `{len(members)}` (maks `{LEVELS_MAX_MEMBERS}` per server)\n"
        f"• **XP tertinggi:** `{top_xp}`\n"
        f"• **Naik level total:** `{cfg.get('leveled_up', 0)}` kali\n"
        f"• **XP voice:** {'✅ aktif' if cfg.get('voice_enabled', True) else '⛔ nonaktif'} "
        f"(`{int(cfg.get('voice_xp_per_min') or 0)}` XP/menit, batas "
        + (f"`{int(cfg.get('voice_daily_cap_min') or 0)}` menit/hari)" if int(cfg.get('voice_daily_cap_min') or 0) else "_tanpa batas_)")
        + "\n"
        f"• **Pengumuman:** {'✅ aktif' if cfg.get('announce') else '⛔ nonaktif'}\n"
        f"• **Hadiah role:** {roles_preview}\n"
        f"• **Batas level:** `{LEVELS_MAX_LEVEL}` • **Jeda default:** `{LEVELS_COOLDOWN_SEC}` dtk",
        ephemeral=True,
    )


season_group = app_commands.Group(
    name="musim",
    description="Musim level: status musim berjalan & reset musim baru (0 kuota AI)",
    parent=level_group,
)


@level_group.command(
    name="prestise",
    description="Tukar level maksimummu menjadi 1× Prestige (XP kembali 0, trofi permanen)",
)
async def level_prestise_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    ok, reason = levels.can_prestige(gid, interaction.user.id)
    if not ok:
        await interaction.response.send_message(f"ℹ️ {reason}", ephemeral=True)
        return

    data = levels.get_member_level(gid, interaction.user.id)
    min_level = levels.prestige_min_level(gid)
    view = await ui_kit.ask_confirm(
        interaction,
        gid,
        title="Prestige sekarang?",
        detail=(
            f"Level **{data['level']}** dan **{data['xp']} XP** akan kembali ke **0** "
            f"(syukur: kamu dapat **1× Prestige** permanen).\n"
            f"Prestige saat ini: `{data['prestige']}×`.\n"
            f"XP hanya diberikan lagi setelah prestige — syarat level **{min_level}** tetap terpenuhi."
        ),
        confirm_label="Ya, tukar jadi Prestige",
    )
    if view is not None:
        await view.wait()
        if not view.result:
            return

    ok2, result = levels.apply_prestige(gid, interaction.user.id)
    if not ok2:
        message = f"ℹ️ {result.get('reason')}"
    else:
        await levels.save_levels_to_disk()
        message = (
            f"🌟 **Prestige {result['prestige']}×!** Levelmu kembali ke 0 dan XP direset. "
            "Trofi prestige tersimpan permanen di kartu level & papan peringkat."
        )

    if view is None:
        await interaction.response.send_message(message, ephemeral=True)
    else:
        try:
            await interaction.edit_original_response(
                embed=ui_theme.status_embed(gid, "ok" if ok2 else "info", "🌟 Prestige", message),
                view=None,
            )
        except discord.HTTPException:  # pragma: no cover
            pass


@season_group.command(name="status", description="Lihat musim level berjalan, sisa hari, & juara musim lalu")
async def level_musim_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    cfg = levels.get_level_config(gid)
    info = levels.season_info(gid)
    top = levels.season_top(gid, limit=5)

    lines = [
        f"🏁 **Musim {info['season']}** • berjalan `{info['days_elapsed']}` hari",
        (
            f"• Reset otomatis: setiap **{info['auto_hari']} hari** (sisa `{info['sisa_hari']}` hari)"
            if info["auto_hari"]
            else "• Reset otomatis: ⛔ nonaktif (Admin bisa `/level musim ulang`)"
        ),
        f"• Prestige: {'✅ aktif' if cfg.get('prestige_aktif', True) else '⛔ nonaktif'} "
        f"(syarat level `{levels.prestige_min_level(gid)}`)",
        f"• Total prestige server: `{cfg.get('prestige_count', 0)}`",
    ]
    if top:
        lines.append("")
        lines.append("**Peringkat sementara**")
        lines.extend(
            f"`{i}.` <@{row['user_id']}> — level `{row['level']}` (`{row['xp']}` XP)"
            for i, row in enumerate(top, start=1)
        )

    last = info["last"]
    if last:
        medals = ["🥇", "🥈", "🥉"]
        lines.append("")
        lines.append(f"**Juara Musim {last.get('season')}** (`{last.get('participants', 0)}` peserta)")
        for index, row in enumerate((last.get("top") or [])[:3]):
            lines.append(
                f"{medals[index]} <@{row['user_id']}> — level `{row.get('level', 0)}` "
                f"(`{row.get('xp', 0)}` XP)"
            )

    await interaction.response.send_message(
        embed=ui_theme.status_embed(
            gid, "info", "🏁 Musim Level", "\n".join(lines)[:3800]
        ),
        ephemeral=True,
    )


@season_group.command(
    name="ulang",
    description="Tutup musim sekarang & mulai musim baru (XP direset, prestige disimpan) — Admin",
)
@app_commands.describe(
    konfirmasi="Wajib True — reset XP seluruh member musim ini",
    reset_otomatis_hari="Aktifkan reset otomatis tiap N hari (0 = manual)",
)
async def level_musim_ulang_cmd(
    interaction: discord.Interaction,
    konfirmasi: bool = False,
    reset_otomatis_hari: app_commands.Range[int, 0, 365] | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    gid = interaction.guild.id
    if not konfirmasi:
        info = levels.season_info(gid)
        await interaction.response.send_message(
            f"⚠️ **Reset musim {info['season']}?** Semua XP member akan kembali ke 0 "
            "(prestige tetap tersimpan). Jalankan ulang dengan `konfirmasi:True`.",
            ephemeral=True,
        )
        return

    if reset_otomatis_hari is not None:
        levels.set_level_config(gid, season_auto_hari=int(reset_otomatis_hari))

    view = await ui_kit.ask_confirm(
        interaction,
        gid,
        title="Reset musim level sekarang?",
        detail=(
            "Semua XP & level member di musim ini akan direset. "
            "Juara musim ini disimpan sebagai riwayat, dan **prestige tetap permanen**."
        ),
        confirm_label="Ya, mulai musim baru",
    )
    if view is not None:
        await view.wait()
        if not view.result:
            return

    snapshot = levels.reset_season(gid, by_id=interaction.user.id)
    await levels.save_levels_to_disk()
    cfg = levels.get_level_config(gid)
    new_season = int(cfg.get("season") or 1)

    embed = levels.build_season_announce_embed(interaction.guild, snapshot, next_season=new_season)
    if view is None:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except discord.HTTPException:  # pragma: no cover
            pass

    # Umumkan ke channel pengumuman level bila diatur
    ids = channel_targets.daftar(cfg, "announce_channel_id")
    if ids and cfg.get("season_announce", True):

        async def _kirim(channel):
            await channel.send(
                embed=embed, allowed_mentions=discord.AllowedMentions.none()
            )

        await channel_targets.sebarkan(interaction.client, ids, _kirim)


@level_group.command(name="voice", description="Atur XP dari aktivitas voice channel (0 kuota AI)")
@app_commands.describe(
    aktif="True untuk menghitung XP voice, False untuk mematikan",
    xp_per_menit="XP yang didapat tiap 1 menit berada di voice (1–20)",
    batas_menit_harian="Batas menit per member per hari (0 = tanpa batas, 60–1440 disarankan)",
    abaikan_channel="Voice channel yang tidak dihitung (mis. AFK/room musik)",
)
async def level_voice_cmd(
    interaction: discord.Interaction,
    aktif: bool | None = None,
    xp_per_menit: app_commands.Range[int, 1, 20] | None = None,
    batas_menit_harian: app_commands.Range[int, 0, 1440] | None = None,
    abaikan_channel: discord.VoiceChannel | None = None,
):
    if interaction.guild is None:
        return

    gid = interaction.guild.id
    changes: dict = {}
    if aktif is not None:
        changes["voice_enabled"] = aktif
    if xp_per_menit is not None:
        changes["voice_xp_per_min"] = int(xp_per_menit)
    if batas_menit_harian is not None:
        changes["voice_daily_cap_min"] = int(batas_menit_harian)
    if abaikan_channel is not None:
        cfg_now = levels.get_level_config(gid)
        current = [int(c) for c in (cfg_now.get("voice_ignore_channels") or []) if int(c) != abaikan_channel.id]
        current.append(int(abaikan_channel.id))
        changes["voice_ignore_channels"] = current

    if changes:
        if not levels.is_leveling_active(gid):
            await ui_kit.send_status(
                interaction,
                embed=ui_theme.status_embed(
                    gid,
                    "warn",
                    "Leveling masih nonaktif",
                    "Aktifkan dulu sistem level dengan `/level atur aktif:True`, "
                    "baru pengaturan XP voice bisa dipakai.",
                ),
                ephemeral=True,
            )
            return
        levels.set_level_config(gid, **changes)
        await levels.save_levels_to_disk()

    cfg = levels.get_level_config(gid)
    state = "✅ aktif" if cfg.get("voice_enabled", True) else "⛔ nonaktif"
    cap = int(cfg.get("voice_daily_cap_min") or 0)
    ignored = ", ".join(f"<#{cid}>" for cid in (cfg.get("voice_ignore_channels") or [])) or "_tidak ada_"
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "🎙️ XP Voice",
            f"Status: **{state}**\n"
            f"• XP per menit: `{int(cfg.get('voice_xp_per_min') or 0)}`\n"
            f"• Batas harian: " + (f"`{cap}` menit/member" if cap else "_tanpa batas_") + "\n"
            f"• Channel diabaikan: {ignored}\n\n"
            "Hanya member yang benar-benar berada di voice (tidak self-mute/self-deaf, "
            "bukan channel AFK) yang dihitung. XP tetap memakai kurva level yang sama "
            "dan tercatat di `/level lihat`.",
        ),
        ephemeral=True,
    )


async def run_voice_xp_check(bot: commands.Bot) -> int:
    """Beri XP voice tiap menit & umumkan kenaikan level (0 kuota AI)."""
    awards = voice_activity.flush_voice_sessions()
    if not awards:
        return 0

    # Koin untuk menit voice (default NONAKTIF)
    try:
        earned = False
        for award in awards:
            if economy.earn_from_voice(
                award["guild_id"], award["user_id"], int(award["result"].get("minutes") or 0)
            ):
                earned = True
        if earned:
            await economy.save_economy_to_disk()
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Koin voice dilewati: %s", exc)

    global _voice_flush_since_save
    _voice_flush_since_save += 1
    level_up_awards = [a for a in awards if a["result"].get("level_up")]
    # Hemat I/O: simpan tiap 5 menit, atau langsung saat ada kenaikan level
    if level_up_awards or _voice_flush_since_save >= 5:
        _voice_flush_since_save = 0
        await levels.save_levels_to_disk()

    # Lencana voice: dicek untuk setiap sesi yang baru dicairkan (murah, tanpa I/O)
    try:
        from cogs.lencana_cog import proses_lencana

        for award in awards:
            guild = bot.get_guild(award["guild_id"]) if callable(getattr(bot, "get_guild", None)) else None
            member = guild.get_member(award["user_id"]) if guild is not None else None
            if member is not None:
                await proses_lencana(bot, guild, member, sumber="voice")
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Lencana voice dilewati: %s", exc)

    announced = 0
    for award in level_up_awards:
        guild = bot.get_guild(award["guild_id"]) if callable(getattr(bot, "get_guild", None)) else None
        if guild is None:
            continue
        member = guild.get_member(award["user_id"]) if callable(getattr(guild, "get_member", None)) else None
        result = award["result"]
        if result.get("role_id") and member is not None:
            await levels.apply_level_role(member, int(result["role_id"]))
        cfg = levels.get_level_config(award["guild_id"])
        if not cfg.get("announce"):
            continue
        target = None
        announce_id = cfg.get("announce_channel_id")
        if announce_id and callable(getattr(bot, "get_channel", None)):
            target = bot.get_channel(int(announce_id))
        if target is None:
            target = getattr(guild, "system_channel", None)
        if target is None:
            continue
        reward = f"\n🎁 Role baru: <@&{result['role_id']}>" if result.get("role_id") else ""
        try:
            await target.send(
                f"🎙️ <@{award['user_id']}> naik ke **level {result['level']}** "
                f"karena aktif di voice channel!{reward}",
                allowed_mentions=discord.AllowedMentions(users=True, roles=True),
            )
            announced += 1
        except (discord.Forbidden, discord.HTTPException):
            pass  # diabaikan (opsional)
    return announced


_voice_flush_since_save = 0


async def handle_message_xp(bot: commands.Bot, message) -> None:
    """Memberi XP untuk pesan biasa & mengumumkan kenaikan level (dipanggil dari events)."""
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    if guild is None or author is None or channel is None:
        return
    if getattr(author, "bot", False):
        return
    if not levels.is_leveling_active(guild.id):
        return

    role_ids = {getattr(role, "id", 0) for role in (getattr(author, "roles", None) or [])}
    # Koin ekonomi (default NONAKTIF) — 0 kuota AI
    try:
        if economy.is_active(guild.id):
            if economy.earn_from_message(
                guild.id, author.id, channel_id=getattr(channel, "id", 0), role_ids=role_ids
            ):
                await economy.save_economy_to_disk()
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Koin pesan dilewati: %s", exc)

    result = levels.add_message_xp(
        guild.id,
        author.id,
        channel_id=getattr(channel, "id", 0),
        role_ids=role_ids,
    )
    if result is None:
        return

    await levels.save_levels_to_disk()

    # Lencana (achievements) — dihitung dari data yang sudah tercatat, 0 kuota AI
    try:
        from cogs.lencana_cog import proses_lencana

        await proses_lencana(bot, guild, author, sumber="chat")
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Lencana pesan dilewati: %s", exc)

    if not result.get("level_up"):
        return

    cfg = levels.get_level_config(guild.id)
    if result.get("role_id"):
        await levels.apply_level_role(author, int(result["role_id"]))

    if not cfg.get("announce"):
        return

    target_channel = channel
    announce_id = cfg.get("announce_channel_id")
    if announce_id:
        get_channel = getattr(bot, "get_channel", None)
        if callable(get_channel):
            target_channel = get_channel(int(announce_id)) or channel

    reward = f"\n🎁 Role baru: <@&{result['role_id']}>" if result.get("role_id") else ""
    try:
        await target_channel.send(
            f"🎉 <@{author.id}> naik ke **level {result['level']}**!{reward}",
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
    except (discord.Forbidden, discord.HTTPException):
        pass  # diabaikan (opsional)


# ==============================================================================
# /tiket — TIKET DUKUNGAN
# ==============================================================================
tiket_group = app_commands.Group(
    name="tiket",
    description="Sistem tiket bantuan berbasis thread privat (tanpa kuota AI)",
    guild_only=True,
)


@tiket_group.command(name="panel", description="Pasang panel 'Buat Tiket' di sebuah channel bantuan")
@app_commands.describe(
    channel="Channel tempat panel tiket dipasang (default: channel ini)",
    staff_role="Role petugas yang diberi akses ke setiap tiket",
    log_channel="Channel untuk menerima transkrip tiket yang ditutup",
    max_open="Batas tiket aktif per member (1-10)",
)
async def tiket_panel_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    staff_role: discord.Role | None = None,
    log_channel: discord.TextChannel | None = None,
    max_open: app_commands.Range[int, 1, 10] | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = channel or interaction.channel
    if target is None or not hasattr(target, "send"):
        await interaction.response.send_message("⚠️ Pilih `channel` text channel untuk panel tiket.", ephemeral=True)
        return

    cfg = tickets.set_ticket_config(
        interaction.guild.id,
        enabled=True,
        panel_channel_id=target.id,
        staff_role_id=staff_role.id if staff_role else None,
        log_channel_id=log_channel.id if log_channel else None,
        max_open=int(max_open) if max_open else None,
    )
    await interaction.response.defer(ephemeral=True)

    try:
        message = await send_ticket_panel(
            target,
            interaction.guild.id,
            tickets.build_panel_embed(interaction.guild.name, staff_role_id=cfg.get("staff_role_id")),
        )
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim panel ke {target.mention}. Cek izin **Kirim Pesan** & **Embed Links**.",
            ephemeral=True,
        )
        return

    tickets.set_ticket_config(
        interaction.guild.id, panel_message_id=message.id, enabled=True
    )
    await tickets.save_tickets_to_disk()

    staff_info = f"<@&{cfg['staff_role_id']}>" if cfg.get("staff_role_id") else "_belum diatur_"
    log_info = f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_belum diatur_"
    await interaction.followup.send(
        f"🎟️ **Panel tiket aktif di {target.mention}!**\n"
        f"• **Role staf:** {staff_info}\n"
        f"• **Log transkrip:** {log_info}\n"
        f"• **Batas tiket per member:** `{cfg.get('max_open', TICKET_MAX_OPEN_PER_USER)}`\n"
        f"> Member klik **🎟️ Buat Tiket** → bot membuat **private thread** (tidak memakai slot channel).",
        ephemeral=True,
    )


@tiket_group.command(name="status", description="Lihat konfigurasi, statistik, & daftar tiket aktif")
async def tiket_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    await interaction.response.send_message(
        embed=tickets.build_ticket_status_embed(interaction.guild.id, interaction.guild),
        ephemeral=True,
    )


@tiket_group.command(name="tutup", description="Tutup tiket di thread ini & kirim transkrip ke channel log")
async def tiket_tutup_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    data = tickets.get_ticket(interaction.channel_id)
    if data is None:
        await interaction.response.send_message(
            "⚠️ Command ini hanya bisa dipakai **di dalam thread tiket**.", ephemeral=True
        )
        return

    perms = getattr(interaction.user, "guild_permissions", None)
    cfg = tickets.get_ticket_config(interaction.guild.id)
    roles = {getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])}
    is_staff = bool(
        perms
        and (
            getattr(perms, "administrator", False)
            or getattr(perms, "manage_threads", False)
            or getattr(perms, "manage_channels", False)
        )
    ) or (bool(cfg.get("staff_role_id")) and int(cfg["staff_role_id"]) in roles)
    if not is_staff and int(data.get("user_id") or 0) != interaction.user.id:
        await interaction.response.send_message(
            "⚠️ Hanya **pembuat tiket** atau **staf** yang bisa menutup tiket ini.", ephemeral=True
        )
        return

    await interaction.response.defer()
    messages = await tickets.collect_thread_messages(interaction.channel)
    reason = "pembuat tiket" if int(data.get("user_id") or 0) == interaction.user.id else "staf"
    status, closed = tickets.close_ticket(interaction.channel_id, interaction.user.id, reason=reason)
    if closed is None:
        await interaction.followup.send("ℹ️ Tiket ini sudah ditutup sebelumnya.", ephemeral=True)
        return

    await tickets.save_tickets_to_disk()
    text, filename = tickets.build_transcript(closed, messages)
    # Arsip HTML: bisa dibuka & dicari dari dashboard (tanpa JavaScript).
    try:
        import ticket_archive

        guild_name = getattr(interaction.guild, "name", "") or ""
        ticket_archive.simpan(closed, messages, guild_name=guild_name, teks=text)
    except Exception as exc:  # pragma: no cover - arsip opsional
        logger.debug("Efek samping opsional gagal: %s", exc)
    sent = await tickets.send_transcript(interaction.client, closed, text, filename)
    # Kartu rating bintang dikirim SEBELUM thread dikunci
    await send_rating_prompt(interaction.channel, interaction.guild.id, closed)

    try:
        await interaction.channel.edit(
            name=f"tiket-{int(closed.get('number') or 0):04d}-selesai"[:100],
            locked=True,
            archived=True,
            reason=f"Tiket ditutup lewat /tiket tutup oleh {interaction.user}",
        )
    except (discord.Forbidden, discord.HTTPException):
        pass  # diabaikan (opsional)

    await interaction.followup.send(
        f"🔒 Tiket **#{int(closed.get('number') or 0):04d}** ditutup."
        + (" Transkrip dikirim ke channel log." if sent else " (Channel log transkrip belum diatur.)")
    )


@tiket_group.command(name="tambah", description="Tambahkan member lain ke tiket ini (mis. saksi atau pihak terkait)")
@app_commands.describe(member="Member yang ingin ditambahkan ke thread tiket")
async def tiket_tambah_cmd(interaction: discord.Interaction, member: discord.Member):
    if interaction.guild is None:
        return
    data = tickets.get_ticket(interaction.channel_id)
    if data is None:
        await interaction.response.send_message(
            "⚠️ Command ini hanya bisa dipakai di dalam thread tiket.", ephemeral=True
        )
        return

    perms = getattr(interaction.user, "guild_permissions", None)
    cfg = tickets.get_ticket_config(interaction.guild.id)
    roles = {getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])}
    is_staff = bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_threads", False))) or (
        bool(cfg.get("staff_role_id")) and int(cfg["staff_role_id"]) in roles
    )
    if not is_staff:
        await interaction.response.send_message("⚠️ Hanya staf yang bisa menambah member.", ephemeral=True)
        return

    try:
        await interaction.channel.add_user(member)
    except (discord.Forbidden, discord.HTTPException):
        await interaction.response.send_message(
            "⚠️ Gagal menambahkan member. Pastikan bot punya izin **Manage Threads**.",
            ephemeral=True,
        )
        return

    tickets.add_user_to_ticket(interaction.channel_id, member.id)
    await tickets.save_tickets_to_disk()
    await interaction.response.send_message(
        f"➕ {member.mention} ditambahkan ke tiket ini.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


def _staf_tiket(interaction: discord.Interaction, cfg: dict) -> bool:
    """True bila pengguna adalah staf tiket (izin kelola thread/administrator atau role staf)."""
    perms = getattr(interaction.user, "guild_permissions", None)
    roles = {
        getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])
    }
    izin = bool(
        perms
        and (
            getattr(perms, "administrator", False)
            or getattr(perms, "manage_threads", False)
            or getattr(perms, "manage_channels", False)
        )
    )
    return izin or (bool(cfg.get("staff_role_id")) and int(cfg["staff_role_id"]) in roles)


@tiket_group.command(
    name="catat",
    description="Simpan catatan internal staf di tiket ini (hanya terlihat di dashboard)",
)
@app_commands.describe(teks=f"Isi catatan (maksimal {tickets.TICKET_NOTE_LEN} karakter)")
async def tiket_catat_cmd(interaction: discord.Interaction, teks: str):
    if interaction.guild is None:
        return
    data = tickets.get_ticket(interaction.channel_id)
    if data is None:
        await interaction.response.send_message(
            "⚠️ Command ini hanya bisa dipakai **di dalam thread tiket**.", ephemeral=True
        )
        return

    cfg = tickets.get_ticket_config(interaction.guild.id)
    if not _staf_tiket(interaction, cfg):
        await interaction.response.send_message(
            "⚠️ Catatan internal hanya bisa ditulis **staf**.", ephemeral=True
        )
        return

    status, data = tickets.add_note(interaction.channel_id, interaction.user.id, teks)
    if status == "kosong":
        await interaction.response.send_message("⚠️ Catatan tidak boleh kosong.", ephemeral=True)
        return
    if status == "penuh":
        await interaction.response.send_message(
            f"⚠️ Catatan tiket ini sudah penuh (maksimal {tickets.TICKET_NOTE_MAX}). "
            "Hapus satu dulu dengan `/tiket catatan hapus:<nomor>`.",
            ephemeral=True,
        )
        return

    await tickets.save_tickets_to_disk()
    jumlah = len((data or {}).get("notes") or [])
    await interaction.response.send_message(
        f"📝 Catatan internal tersimpan (`{jumlah}/{tickets.TICKET_NOTE_MAX}`). "
        "Member tidak melihat pesan ini — catatan hanya tampil di dashboard tiket.",
        ephemeral=True,
    )


@tiket_group.command(name="catatan", description="Lihat catatan internal staf pada tiket ini")
@app_commands.describe(hapus="Nomor catatan yang ingin dihapus (1 = paling lama)")
async def tiket_catatan_cmd(interaction: discord.Interaction, hapus: int = 0):
    if interaction.guild is None:
        return
    data = tickets.get_ticket(interaction.channel_id)
    if data is None:
        await interaction.response.send_message(
            "⚠️ Command ini hanya bisa dipakai **di dalam thread tiket**.", ephemeral=True
        )
        return

    cfg = tickets.get_ticket_config(interaction.guild.id)
    if not _staf_tiket(interaction, cfg):
        await interaction.response.send_message(
            "⚠️ Catatan internal hanya bisa dibaca **staf**.", ephemeral=True
        )
        return

    catatan = tickets.list_notes(interaction.channel_id)
    if hapus > 0:
        status, _ = tickets.remove_note(interaction.channel_id, hapus)
        if status != "ok":
            await interaction.response.send_message(
                f"⚠️ Catatan nomor `{hapus}` tidak ada (tersimpan `{len(catatan)}`).",
                ephemeral=True,
            )
            return
        await tickets.save_tickets_to_disk()
        catatan = tickets.list_notes(interaction.channel_id)
        await interaction.response.send_message(
            f"🗑️ Catatan nomor `{hapus}` dihapus. Sisa `{len(catatan)}`.",
            ephemeral=True,
        )
        return

    if not catatan:
        await interaction.response.send_message(
            "ℹ️ Belum ada catatan internal di tiket ini. "
            "Tambahkan dengan `/tiket catat teks:<isi>`.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"📝 Catatan internal tiket #{int(data.get('number') or 0):04d}",
        color=discord.Color.blurple(),
        description="Hanya staf yang melihat catatan ini — member tidak menerimanya.",
    )
    for nomor, item in enumerate(catatan, start=1):
        # Timestamp relatif milik Discord (<t:…:R>) — tanpa helper tambahan.
        waktu = f"<t:{int(float(item.get('at') or 0))}:R>"
        embed.add_field(
            name=f"{nomor}. <@{item.get('oleh')}> · {waktu}",
            value=str(item.get("teks") or "-")[:1024],
            inline=False,
        )
    embed.set_footer(
        text=f"{len(catatan)}/{tickets.TICKET_NOTE_MAX} catatan · hapus: /tiket catatan hapus:<nomor>"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tiket_group.command(name="daftar", description="Lihat tiket yang masih aktif di server ini")
@app_commands.describe(hanya_milikku="True untuk hanya menampilkan tiket yang kamu buat")
async def tiket_daftar_cmd(interaction: discord.Interaction, hanya_milikku: bool = False):
    if interaction.guild is None:
        return

    items = tickets.list_tickets(interaction.guild.id, limit=15)
    if hanya_milikku:
        items = [data for data in items if int(data.get("user_id") or 0) == interaction.user.id]
    active = [data for data in items if data.get("status") in ("terbuka", "diklaim")]
    if not active:
        await interaction.response.send_message(
            "ℹ️ Tidak ada tiket aktif. Buka lewat tombol **🎟️ Buat Tiket** di panel bantuan.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🎟️ Tiket Aktif",
        color=discord.Color.blurple(),
        description=f"`{len(active)}` tiket menunggu/ditangani",
    )
    for data in active[:10]:
        embed.add_field(
            name=f"#{int(data.get('number') or 0):04d} • {tickets.TICKET_STATUS.get(data.get('status'), '-')}",
            value=(
                f"<@{data['user_id']}> • <#{data['thread_id']}>\n"
                f"> {str(data.get('topic') or '_tanpa topik_')[:120]}"
            ),
            inline=False,
        )
    embed.set_footer(text="Staf: gunakan tombol 🙋 Klaim / 🔒 Tutup di dalam thread tiket")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tiket_group.command(
    name="atur",
    description="Atur rating bintang, batas SLA respons pertama, & auto-close tiket (Admin)",
)
@app_commands.describe(
    rating_aktif="Tampilkan kartu rating bintang setelah tiket ditutup",
    sla_jam="Batas jam respons staf pertama sebelum peringatan SLA (0 = nonaktif, maks 720)",
    auto_close_jam="Tutup otomatis tiket tanpa aktivitas setelah N jam (0 = nonaktif, maks 720)",
    channel_sla="Channel tujuan peringatan SLA (kosong = channel log/system)",
)
async def tiket_atur_cmd(
    interaction: discord.Interaction,
    rating_aktif: bool | None = None,
    sla_jam: app_commands.Range[int, 0, 720] | None = None,
    auto_close_jam: app_commands.Range[int, 0, 720] | None = None,
    channel_sla: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if all(value is None for value in (rating_aktif, sla_jam, auto_close_jam, channel_sla)):
        await interaction.response.send_message(
            "ℹ️ Tidak ada perubahan. Isi minimal satu parameter, contoh: "
            "`/tiket atur sla_jam:2 auto_close_jam:72`.",
            ephemeral=True,
        )
        return

    cfg = tickets.set_ticket_config(
        interaction.guild.id,
        rating_aktif=rating_aktif,
        sla_jam=int(sla_jam) if sla_jam is not None else None,
        auto_close_jam=int(auto_close_jam) if auto_close_jam is not None else None,
        sla_channel_id=channel_sla.id if channel_sla else None,
    )
    await tickets.save_tickets_to_disk()

    sla_channel_id = cfg.get("sla_channel_id")
    sla_channel_text = f"<#{sla_channel_id}>" if sla_channel_id else "_channel log/system_"
    await interaction.response.send_message(
        "⚙️ **Pengaturan tiket diperbarui**\n"
        f"• Rating bintang: **{'aktif' if cfg.get('rating_aktif') else 'nonaktif'}**\n"
        f"• SLA respons pertama: `{cfg.get('sla_jam')}` jam "
        f"({'⛔ nonaktif' if not int(cfg.get('sla_jam') or 0) else 'aktif'})\n"
        f"• Auto-close: `{cfg.get('auto_close_jam')}` jam tanpa aktivitas "
        f"({'⛔ nonaktif' if not int(cfg.get('auto_close_jam') or 0) else 'aktif'})\n"
        f"• Channel peringatan SLA: {sla_channel_text}",
        ephemeral=True,
    )


@tiket_group.command(name="rating", description="Lihat rata-rata rating bintang & statistik SLA tiket server")
async def tiket_rating_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    cfg = tickets.get_ticket_config(interaction.guild.id)
    summary = tickets.rating_summary(interaction.guild.id)
    sla = tickets.sla_stats(interaction.guild.id)

    stars = "".join(
        f"{'⭐' * star} `{summary['distribution'][star]}`\n"
        for star in (5, 4, 3, 2, 1)
        if summary["distribution"][star]
    ) or "_belum ada rating_"

    embed = discord.Embed(
        title="⭐ Rating & SLA Layanan Tiket",
        color=discord.Color.gold(),
    )
    embed.add_field(
        name="Rating",
        value=(
            f"• Rata-rata: **{summary['average']} / 5** (`{summary['count']}` penilaian)\n"
            f"• Tingkat penilaian: `{summary['response_rate']}%` dari tiket selesai"
        ),
        inline=False,
    )
    embed.add_field(name="Sebaran Bintang", value=stars[:1024], inline=False)
    embed.add_field(
        name="SLA Respons Pertama",
        value=(
            f"• Batas: `{cfg.get('sla_jam')}` jam "
            f"({'nonaktif' if not int(cfg.get('sla_jam') or 0) else 'aktif'})\n"
            f"• Sudah direspons: `{sla['responded']}` tiket (rata-rata `{sla['avg_minutes']}` menit)\n"
            f"• Menunggu respons: `{sla['pending']}` tiket\n"
            f"• Auto-close: `{cfg.get('auto_close_jam')}` jam • sudah menutup `{cfg.get('auto_closed', 0)}` tiket"
        ),
        inline=False,
    )
    embed.set_footer(text="Semua angka dihitung lokal dari data tiket — 0 kuota AI")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tiket_group.command(name="matikan", description="Matikan sistem tiket (panel lama tidak lagi membuat tiket baru)")
async def tiket_matikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    changed = tickets.disable_tickets(interaction.guild.id)
    await tickets.save_tickets_to_disk()
    await interaction.response.send_message(
        "🛑 **Sistem tiket dimatikan.** Thread tiket lama tetap bisa dibaca & ditutup."
        if changed
        else "ℹ️ Sistem tiket memang belum aktif.",
        ephemeral=True,
    )


@tiket_group.command(
    name="topik",
    description="Atur beberapa topik tiket; tiap topik bisa punya role staf sendiri",
)
@app_commands.describe(
    tambah="Nama topik baru (atau yang diperbarui). Kosongkan untuk melihat daftar.",
    hapus="Nama topik yang ingin dihapus",
    role="Role staf khusus untuk topik ini (opsional)",
    emoji="Emoji topik, mis. 🛒 (opsional)",
    deskripsi="Keterangan singkat yang tampil di dropdown (opsional)",
)
async def tiket_topik_cmd(
    interaction: discord.Interaction,
    tambah: str = "",
    hapus: str = "",
    role: discord.Role | None = None,
    emoji: str = "",
    deskripsi: str = "",
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    gid = interaction.guild.id
    if hapus:
        ok, pesan = tickets.remove_ticket_topic(gid, hapus)
        if ok:
            await tickets.save_tickets_to_disk()
        await interaction.response.send_message(
            ("🗑️ " if ok else "⚠️ ") + pesan, ephemeral=True
        )
        return

    if tambah:
        ok, pesan = tickets.add_ticket_topic(
            gid,
            tambah,
            emoji=emoji,
            staff_role_id=role.id if role else 0,
            deskripsi=deskripsi,
        )
        if ok:
            await tickets.save_tickets_to_disk()
            pesan += (
                f"\n• Role staf: {role.mention if role else '_ikut role staf umum_'}\n"
                f"• Total topik: `{len(tickets.list_ticket_topics(gid))}/"
                f"{tickets.TICKET_TOPIC_MAX}`\n"
                "Pasang ulang panel dengan `/tiket panel` agar dropdown topik muncul."
            )
        await interaction.response.send_message(
            ("✅ " if ok else "⚠️ ") + pesan[:1500], ephemeral=True
        )
        return

    daftar = tickets.list_ticket_topics(gid)
    if not daftar:
        await interaction.response.send_message(
            "ℹ️ Belum ada topik. Panel tiket memakai satu tombol **Buat Tiket** biasa.\n"
            "Tambah topik dengan `/tiket topik tambah:Pembelian role:@Kasir emoji:🛒`.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🧩 Topik panel tiket",
        color=discord.Color.blurple(),
        description=(
            f"`{len(daftar)}/{tickets.TICKET_TOPIC_MAX}` topik · member memilih topik dari "
            "dropdown di panel, lalu role staf topik itu yang diberi tahu."
        ),
    )
    for nomor, item in enumerate(daftar, start=1):
        role_id = int(item.get("staff_role_id") or 0)
        embed.add_field(
            name=f"{nomor}. {item.get('emoji') or '🎟️'} {item.get('nama')}",
            value=(
                (f"{item.get('deskripsi')}\n" if item.get("deskripsi") else "")
                + f"Staf: {f'<@&{role_id}>' if role_id else '_role staf umum'}"
            )[:1024],
            inline=False,
        )
    embed.set_footer(text="Hapus: /tiket topik hapus:<nama> · pasang ulang panel setelah berubah")
    await interaction.response.send_message(embed=embed, ephemeral=True)


def register_growth_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command /level & /tiket ke bot."""
    bot.tree.add_command(level_group)
    bot.tree.add_command(tiket_group)
