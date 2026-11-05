"""Slash `/analitik` — ekspor data server ke CSV & kirim otomatis ke webhook (**0 kuota AI**).

- `/analitik ekspor <jenis>` *(Admin)* — unduh CSV (level/moderasi/tiket/pemakaian).
- `/analitik webhook <url> [jadwal]` *(Admin)* — kirim CSV otomatis ke webhook Discord.
- `/analitik status` — ringkasan pengaturan, jumlah data, & kapan terakhir dikirim.
- `/analitik matikan` *(Admin)* — hentikan ekspor otomatis (URL webhook dihapus).
"""

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

import analytics_export as exporter
import i18n
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.analytics_cog")

analitik_group = app_commands.Group(
    name="analitik",
    description="Ekspor analitik server ke CSV & kirim otomatis ke webhook (0 kuota AI)",
    guild_only=True,
)

_JENIS_CHOICES = [
    app_commands.Choice(name=label, value=key) for key, label in exporter.KINDS.items()
]
_JADWAL_CHOICES = [
    app_commands.Choice(name=label, value=key) for key, label in exporter.JADWAL.items()
]


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms
        and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


async def _reject(interaction: discord.Interaction, gid: int) -> None:
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "lock", i18n.t("perm.admin", gid), i18n.t("perm.admin_detail", gid)
        ),
        ephemeral=True,
    )


def _count_rows(guild_id: int) -> dict[str, int]:
    import insights
    import levels
    import moderation
    import tickets

    xp_rows = sum(1 for key in levels.levels if str(key).startswith(f"{int(guild_id)}:"))
    ticket_rows = sum(
        1 for data in tickets.tickets.values() if int(data.get("guild_id") or 0) == int(guild_id)
    )
    return {
        "level": xp_rows,
        "moderasi": len(moderation.mod_cases.get(int(guild_id)) or []),
        "tiket": ticket_rows,
        "pemakaian": len(insights.ai_usage),
    }


@analitik_group.command(name="ekspor", description="Unduh analitik server sebagai berkas CSV (Admin)")
@app_commands.describe(jenis="Jenis data yang diekspor")
@app_commands.choices(jenis=_JENIS_CHOICES)
async def analitik_ekspor_cmd(interaction: discord.Interaction, jenis: app_commands.Choice[str]):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await _reject(interaction, gid)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    body, filename, error = exporter.build_csv(jenis.value, gid)
    if not body:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "info", "📄 Ekspor CSV", error),
            follow=True,
            ephemeral=True,
        )
        return

    file = discord.File(io.BytesIO(exporter.csv_bytes(body)), filename=filename)
    rows = max(0, body.count("\n") - 1)
    await interaction.followup.send(
        f"📄 **{exporter.KINDS[jenis.value]}** — `{rows}` baris\n"
        "Buka dengan Excel/Google Sheets (UTF-8, pemisah koma).",
        file=file,
        ephemeral=True,
    )
    logger.info("Ekspor CSV %s (%d baris) oleh %s di %s", jenis.value, rows, interaction.user, gid)



@analitik_group.command(name="webhook", description="Kirim CSV otomatis ke webhook Discord (Admin)")
@app_commands.describe(
    url="URL webhook Discord tujuan (Server Settings → Integrations → Webhooks)",
    jadwal="Seberapa sering CSV dikirim",
    jenis="Jenis data yang dikirim (kosongkan untuk semua)",
)
@app_commands.choices(jadwal=_JADWAL_CHOICES, jenis=_JENIS_CHOICES)
async def analitik_webhook_cmd(
    interaction: discord.Interaction,
    url: str,
    jadwal: app_commands.Choice[str] | None = None,
    jenis: app_commands.Choice[str] | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await _reject(interaction, gid)
        return

    ok, error = exporter.validate_webhook(url)
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "URL webhook tidak valid", error),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    cfg = exporter.set_config(
        gid,
        aktif=True,
        webhook_url=url,
        jadwal=jadwal.value if jadwal else "harian",
        jenis=[jenis.value] if jenis else list(exporter.KINDS),
    )
    # Uji kirim sekali agar Admin tahu URL benar
    body, filename, build_error = exporter.build_csv(cfg["jenis"][0], gid)
    test_note = "Uji kirim: belum ada data untuk dikirim."
    if body:
        sent, message = await exporter.post_csv_to_webhook(
            url, body, filename, session=getattr(interaction.client, "http_session", None)
        )
        test_note = "✅ Uji kirim berhasil." if sent else f"⚠️ Uji kirim gagal: {message}"

    await exporter.save_analytics_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if body else "info",
            "📊 Ekspor Webhook aktif",
            f"• Webhook: {exporter.mask_webhook(url)}\n"
            f"• Jadwal: **{exporter.JADWAL.get(cfg['jadwal'], cfg['jadwal'])}**\n"
            f"• Data: {', '.join('`' + k + '`' for k in cfg['jenis'])}\n"
            f"• {test_note}\n\n"
            "CSV dikirim sebagai lampiran; URL webhook disimpan lokal di `data/analytics.json`.",
        ),
        follow=True,
        ephemeral=True,
    )


@analitik_group.command(name="status", description="Lihat pengaturan ekspor & jumlah data yang tersedia")
async def analitik_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    cfg = exporter.get_config(gid)
    counts = _count_rows(gid)
    rows = "\n".join(
        f"• {exporter.KINDS[key]} — `{counts.get(key, 0)}` baris" for key in exporter.KINDS
    )
    last = int(float(cfg.get("last_sent") or 0))
    body = (
        f"• Status: **{'aktif' if cfg.get('aktif') else 'nonaktif'}**\n"
        f"• Webhook: {exporter.mask_webhook(cfg.get('webhook_url'))}\n"
        f"• Jadwal: **{exporter.JADWAL.get(str(cfg.get('jadwal')), 'mati')}**\n"
        f"• Terakhir dikirim: " + (f"<t:{last}:R>" if last else "_belum pernah_") + "\n"
        f"• Total berkas terkirim: `{cfg.get('sent_count', 0)}`\n\n"
        f"**Data tersedia**\n{rows}\n\n"
        "Unduh manual: `/analitik ekspor jenis:level`."
    )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "info", "📊 Analitik & Ekspor", body),
        ephemeral=True,
    )


@analitik_group.command(name="matikan", description="Hentikan ekspor otomatis & hapus URL webhook (Admin)")
async def analitik_matikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await _reject(interaction, gid)
        return

    cfg = exporter.set_config(gid, aktif=False, webhook_url="", jadwal="mati")
    await exporter.save_analytics_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Ekspor otomatis dihentikan",
            f"URL webhook dihapus dari penyimpanan (sekarang: {exporter.mask_webhook(cfg.get('webhook_url'))}).\n"
            "Ekspor manual `/analitik ekspor` tetap bisa dipakai.",
        ),
        ephemeral=True,
    )


def register_export_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/analitik` ke bot."""
    bot.tree.add_command(analitik_group)
