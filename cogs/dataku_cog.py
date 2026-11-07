"""Command `/dataku` & `/hapusdataku` — privasi mandiri (ekspor & hapus data pribadi).

Terinspirasi purpleGPT (`/export_data` & `/delete_user_data`). Ekspor berbentuk lampiran
JSON, penghapusan memakai tombol konfirmasi agar tidak bisa terjadi karena salah ketik.
"""

from __future__ import annotations

import io
import json
import logging

import discord
from discord import app_commands

import user_data

logger = logging.getLogger("gemini_bot.dataku_cog")


class KonfirmasiHapus(discord.ui.View):
    """Dua tombol: hapus permanen atau batal."""

    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = int(user_id)

    @discord.ui.button(label="Hapus permanen", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def hapus(self, interaction: discord.Interaction, button: discord.ui.Button):
        if int(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Tombol ini bukan untukmu.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dihapus = user_data.hapus(self.user_id)
        await user_data.simpan_semua()
        self.stop()
        rincian = ", ".join(f"{nama} {jumlah}" for nama, jumlah in sorted(dihapus.items())) or "—"
        await interaction.followup.send(
            f"🗑️ Data pribadimu sudah dihapus.\nRincian: {rincian}", ephemeral=True
        )

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def batal(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="❌ Dibatalkan — tidak ada yang dihapus.", embed=None, view=None
        )


@app_commands.command(name="dataku", description="Ekspor semua data pribadimu sebagai berkas JSON")
async def dataku_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    data = user_data.kumpulkan(interaction.user.id)
    mentah = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if len(mentah) > 7 * 1024 * 1024:  # batas aman unggahan Discord
        data["modul"] = {k: {"jumlah": v.get("jumlah")} if isinstance(v, dict) else v
                         for k, v in (data.get("modul") or {}).items()}
        mentah = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    berkas = discord.File(io.BytesIO(mentah), filename=f"dataku-{interaction.user.id}.json")
    await interaction.followup.send(
        content="📦 Ini data pribadimu yang tersimpan di bot:\n"
        + user_data.ringkas(data)
        + "\n\n_Mau dihapus? Jalankan `/hapusdataku`._",
        file=berkas,
        ephemeral=True,
    )


@app_commands.command(name="hapusdataku", description="Hapus permanen semua data pribadimu di bot ini")
async def hapusdataku_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🗑️ Hapus semua data pribadimu?",
        description=(
            "Yang dihapus: **level/XP**, **saldo koin**, **lencana**, **kata kunci pantau**, "
            "**ulang tahun**, **skor game**, dan **kiriman formulir** milikmu.\n"
            "Tindakan ini **permanen** dan tidak bisa dibatalkan."
        ),
        colour=discord.Colour.dark_red(),
    )
    await interaction.response.send_message(
        embed=embed, view=KonfirmasiHapus(interaction.user.id), ephemeral=True
    )


def register_dataku_cog(bot) -> None:
    """Daftarkan `/dataku` & `/hapusdataku`."""
    bot.tree.add_command(dataku_cmd)
    bot.tree.add_command(hapusdataku_cmd)


__all__ = ["register_dataku_cog", "dataku_cmd", "hapusdataku_cmd"]
