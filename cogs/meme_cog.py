"""Command `/meme` — buat meme lokal dengan Pillow. **0 kuota AI**, tanpa jaringan."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

import meme_maker

logger = logging.getLogger("gemini_bot.meme_cog")

PILIHAN = [app_commands.Choice(name=item["label"][:100], value=item["id"])
           for item in meme_maker.daftar_template()]


@app_commands.command(name="meme", description="Buat meme dari teks (0 kuota AI, langsung jadi)")
@app_commands.describe(
    teks_atas="Teks bagian atas",
    teks_bawah="Teks bagian bawah",
    template="Gaya meme (default: klasik)",
)
@app_commands.choices(template=PILIHAN)
async def meme_cmd(
    interaction: discord.Interaction,
    teks_atas: str | None = None,
    teks_bawah: str | None = None,
    template: app_commands.Choice[str] | None = None,
):
    kunci = template.value if template is not None else "klasik"
    buffer, galat = meme_maker.buat_meme(teks_atas or "", teks_bawah or "", template=kunci)
    if buffer is None:
        await interaction.response.send_message(f"⚠️ {galat}", ephemeral=True)
        return

    nama = f"meme-{kunci}.png"
    berkas = discord.File(buffer, filename=nama)
    await interaction.response.send_message(
        content=f"🖼️ Meme gaya **{meme_maker.TEMPLATE[kunci]['label']}** — dibuat lokal, tanpa AI.",
        file=berkas,
    )


def register_meme_cog(bot) -> None:
    """Daftarkan `/meme` ke tree bot."""
    bot.tree.add_command(meme_cmd)


__all__ = ["meme_cmd", "register_meme_cog"]
