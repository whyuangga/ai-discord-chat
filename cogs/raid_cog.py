"""Slash `/raid` — mode darurat otomatis saat server diserbu akun palsu (**0 kuota AI**).

- `/raid status` — apakah mode raid aktif, sisa waktu, ambang, & aksi.
- `/raid atur` *(Admin)* — aktifkan deteksi otomatis, ambang join, aksi, durasi, & channel log.
- `/raid mulai` *(Admin)* — nyalakan mode raid sekarang (manual) tanpa menunggu ambang.
- `/raid akhiri` *(Admin)* — akhiri lebih awal & kembalikan server seperti semula.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import raid_guard
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.raid_cog")

raid_group = app_commands.Group(
    name="raid",
    description="Mode darurat saat server diserbu akun palsu: tahan Auto Role, verifikasi, & lockdown (0 kuota AI)",
    guild_only=True,
)

_AKSI_CHOICES = [
    app_commands.Choice(name=label, value=key) for key, label in raid_guard.ACTIONS.items()
]


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms
        and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


async def _guard(interaction: discord.Interaction, gid: int) -> bool:
    if _is_admin(interaction):
        return True
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server* yang bisa memakai `/raid`."
        ),
        ephemeral=True,
    )
    return False


@raid_group.command(name="status", description="Cek apakah mode raid sedang aktif & lihat pengaturannya")
async def raid_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    cfg = raid_guard.get_config(gid)
    state = raid_guard.is_raid_active(gid)
    remaining = raid_guard.remaining_seconds(gid)

    if state:
        head = (
            f"🔴 **MODE RAID AKTIF** — sisa `{remaining // 60} menit {remaining % 60} detik`\n"
            f"• Aksi: {raid_guard.ACTIONS.get(str(state.get('action')), state.get('action'))}\n"
            f"• Alasan: {state.get('reason')}\n"
            f"• Dipicu: {state.get('by')} • member join tercatat: `{state.get('joins', 0)}`\n"
            f"• Lockdown: {'✅ aktif' if state.get('locked') else '⛔ tidak'}\n"
        )
    else:
        head = "🟢 Tidak ada mode raid aktif.\n"

    body = (
        head
        + "\n**Pengaturan**\n"
        f"• Deteksi otomatis: {'✅ aktif' if cfg.get('enabled') else '⛔ nonaktif'}\n"
        f"• Ambang: `{cfg.get('join_threshold')}` join dalam `{cfg.get('window_sec')}` detik\n"
        f"• Aksi: {raid_guard.ACTIONS.get(str(cfg.get('action')), cfg.get('action'))}\n"
        f"• Durasi: `{cfg.get('duration_min')}` menit\n"
        f"• Channel log: " + (f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_channel sistem_")
        + "\n• Channel verifikasi: "
        + (f"<#{cfg['verify_channel_id']}>" if cfg.get("verify_channel_id") else "_belum diatur_")
    )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "warn" if state else "info", "🚨 Status Raid Guard", body),
        ephemeral=True,
    )


@raid_group.command(name="atur", description="Atur deteksi raid otomatis: ambang, aksi, durasi, & channel (Admin)")
@app_commands.describe(
    aktif="True untuk mendeteksi lonjakan join otomatis",
    ambang="Jumlah join dalam jendela waktu sebelum mode raid menyala (2–100)",
    jendela_detik="Panjang jendela deteksi (10–3600 detik)",
    aksi="Tindakan saat mode raid menyala",
    durasi_menit="Berapa lama mode raid aktif sebelum berakhir sendiri (1–1440)",
    log_channel="Channel laporan mode raid",
    channel_verifikasi="Channel berisi panel verifikasi",
)
@app_commands.choices(aksi=_AKSI_CHOICES)
async def raid_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool | None = None,
    ambang: app_commands.Range[int, 2, 100] | None = None,
    jendela_detik: app_commands.Range[int, 10, 3600] | None = None,
    aksi: app_commands.Choice[str] | None = None,
    durasi_menit: app_commands.Range[int, 1, 1440] | None = None,
    log_channel: discord.TextChannel | None = None,
    channel_verifikasi: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    raid_guard.set_config(
        gid,
        enabled=aktif,
        action=aksi.value if aksi else None,
        join_threshold=int(ambang) if ambang else None,
        window_sec=int(jendela_detik) if jendela_detik else None,
        duration_min=int(durasi_menit) if durasi_menit else None,
        log_channel_id=log_channel.id if log_channel else None,
        verify_channel_id=channel_verifikasi.id if channel_verifikasi else None,
    )
    await raid_guard.save_raid_to_disk()

    cfg = raid_guard.get_config(gid)
    warn = ""
    if cfg.get("enabled") and cfg.get("action") == "verifikasi+lockdown":
        warn = (
            "\n\n⚠️ Aksi **verifikasi+lockdown** akan mengunci semua text channel saat raid. "
            "Pastikan bot punya izin **Manage Channels**."
        )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Pengaturan Raid Guard disimpan",
            f"• Deteksi otomatis: **{'aktif' if cfg.get('enabled') else 'nonaktif'}**\n"
            f"• Ambang: `{cfg.get('join_threshold')}` join / `{cfg.get('window_sec')}` dtk\n"
            f"• Aksi: {raid_guard.ACTIONS.get(str(cfg.get('action')), cfg.get('action'))}\n"
            f"• Durasi: `{cfg.get('duration_min')}` menit\n"
            f"• Log: " + (f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_channel sistem_")
            + warn,
        ),
        ephemeral=True,
    )


@raid_group.command(name="mulai", description="Nyalakan mode raid sekarang juga (Admin)")
@app_commands.describe(
    alasan="Alasan mode raid dinyalakan",
    aksi="Tindakan yang dijalankan (bawaan: sesuai pengaturan)",
    durasi_menit="Berapa lama mode aktif (bawaan: sesuai pengaturan)",
)
@app_commands.choices(aksi=_AKSI_CHOICES)
async def raid_mulai_cmd(
    interaction: discord.Interaction,
    alasan: str = "Dipicu manual oleh Admin",
    aksi: app_commands.Choice[str] | None = None,
    durasi_menit: app_commands.Range[int, 1, 1440] | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    if raid_guard.is_raid_active(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "info", "Mode raid sudah aktif",
                f"Sisa `{raid_guard.remaining_seconds(gid) // 60} menit`. Akhiri dengan `/raid akhiri` bila perlu.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await raid_guard.start(
        interaction.client,
        interaction.guild,
        reason=alasan,
        actor_id=interaction.user.id,
        duration_min=int(durasi_menit) if durasi_menit else None,
        action=aksi.value if aksi else None,
    )
    await raid_guard.save_raid_to_disk()
    state = result["state"]
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "warn",
            "🚨 Mode raid dinyalakan",
            f"Berakhir <t:{int(state['until'])}:R>.\n"
            + "\n".join(f"• {step}" for step in result["steps"]),
        ),
        follow=True,
        ephemeral=True,
    )


@raid_group.command(name="akhiri", description="Akhiri mode raid & kembalikan server seperti semula (Admin)")
async def raid_akhiri_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await raid_guard.end(interaction.client, interaction.guild, actor_id=interaction.user.id)
    await raid_guard.save_raid_to_disk()

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if result["ended"] else "info",
            "Mode raid berakhir" if result["ended"] else "Tidak ada mode raid aktif",
            "\n".join(f"• {step}" for step in result["steps"]),
        ),
        follow=True,
        ephemeral=True,
    )


def register_raid_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/raid` ke bot."""
    bot.tree.add_command(raid_group)
