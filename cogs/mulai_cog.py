"""Slash `/mulai` — wizard pemasangan cepat untuk admin awam.

Tujuannya: admin baru cukup menjawab "mau pakai paket apa" + pilih channel/role,
tanpa perlu tahu nama command lain. Konfigurasi tetap ditulis lewat fungsi yang
sudah ada (`set_welcome_config`, `set_autorole_config`, `set_log_channel`).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import presets
import ui_kit
import ui_theme
from community_agent import save_agent_config_to_disk, set_welcome_config
from audit_log import set_log_channel
from server_features import save_server_features_to_disk, set_autorole_config

logger = logging.getLogger("gemini_bot.mulai_cog")

_PILIHAN = [
    app_commands.Choice(name=f"{p['emoji']} {p['label']}", value=p["key"])
    for p in presets.list_presets()
]


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


async def _tolak(interaction: discord.Interaction, gid: int) -> None:
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server* yang bisa menjalankan `/mulai`."
        ),
        ephemeral=True,
    )


@app_commands.command(name="mulai", description="Panduan pemasangan cepat: pilih paket, bot yang mengatur (Admin)")
@app_commands.describe(
    paket="Paket pengaturan yang ingin dipasang",
    channel_sambutan="Channel untuk menyambut member baru (opsional)",
    role_otomatis="Role yang otomatis diberikan ke member baru (opsional)",
    channel_log="Channel log moderasi (opsional)",
    pratinjau="True = hanya lihat rencananya, belum mengubah apa pun",
)
@app_commands.choices(paket=_PILIHAN)
@app_commands.guild_only()
async def mulai_cmd(
    interaction: discord.Interaction,
    paket: app_commands.Choice[str] | None = None,
    channel_sambutan: discord.TextChannel | None = None,
    role_otomatis: discord.Role | None = None,
    channel_log: discord.TextChannel | None = None,
    pratinjau: bool = False,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id

    if paket is None:
        baris = "\n\n".join(presets.ringkas(p) for p in presets.list_presets())
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "info", "Mulai dari mana?",
                f"{baris}\n\n**Langkah berikutnya:**\n"
                "`/mulai paket:🏡 Server Komunitas channel_sambutan:#sambutan "
                "role_otomatis:@Member channel_log:#log`\n"
                "-# Tambahkan `pratinjau:True` untuk melihat rencananya dulu tanpa mengubah apa pun.",
            ),
            ephemeral=True,
        )
        return

    if not _is_admin(interaction):
        await _tolak(interaction, gid)
        return

    preset = presets.get_preset(paket.value)
    if preset is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Paket tidak dikenal", "Pilih dari daftar `/mulai`."),
            ephemeral=True,
        )
        return

    rencana = presets.build_plan(
        preset,
        channel_sambutan=channel_sambutan,
        role_otomatis=role_otomatis,
        channel_log=channel_log,
    )
    ringkasan = "\n".join(("✅ " if r["siap"] else "⬜ ") + r["label"] for r in rencana)

    if pratinjau:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "info", f"Pratinjau: {preset['label']}", ringkasan[:3000],
                footer="Belum ada yang diubah. Jalankan tanpa pratinjau untuk memasang.",
            ),
            ephemeral=True,
        )
        return

    terpasang: list[str] = []
    dilewati: list[str] = []
    try:
        if "sambutan" in preset["fitur"]:
            if channel_sambutan is not None:
                set_welcome_config(gid, channel_sambutan.id, enabled=True)
                await save_agent_config_to_disk()
                terpasang.append(f"Sambutan di {channel_sambutan.mention}")
            else:
                dilewati.append("sambutan (channel belum dipilih)")

        if "autorole" in preset["fitur"]:
            if role_otomatis is not None:
                set_autorole_config(gid, [role_otomatis.id], enabled=True)
                await save_server_features_to_disk()
                terpasang.append(f"Auto role @{role_otomatis.name}")
            else:
                dilewati.append("auto role (role belum dipilih)")

        if "log" in preset["fitur"]:
            if channel_log is not None:
                set_log_channel(gid, channel_log.id)
                terpasang.append(f"Log moderasi di {channel_log.mention}")
            else:
                dilewati.append("log (channel belum dipilih)")
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Preset /mulai gagal: %s", exc)
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "error", "Sebagian pengaturan gagal dipasang",
                f"{exc.__class__.__name__}: coba lagi atau pasang manual lewat `/menu`.",
            ),
            ephemeral=True,
        )
        return

    if "pengumuman" in preset["fitur"]:
        dilewati.append("pengumuman terjadwal (atur isinya lewat `/pengumuman tambah`)")

    isi = "\n".join(f"✅ {t}" for t in terpasang) or "Belum ada yang terpasang."
    if dilewati:
        isi += "\n\n**Belum dipasang:**\n" + "\n".join(f"⬜ {d}" for d in dilewati)
    isi += "\n\n-# Ubah kapan saja dengan command yang sama, atau matikan fiturnya satu per satu."

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "ok", f"{preset['emoji']} {preset['label']} dipasang", isi[:3500]),
        ephemeral=True,
    )


def register_mulai_cog(bot: commands.Bot) -> None:
    """Daftarkan `/mulai` (dipanggil dari main.py)."""
    bot.tree.add_command(mulai_cmd)


__all__ = ["mulai_cmd", "register_mulai_cog"]
