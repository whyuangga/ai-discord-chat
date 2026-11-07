"""Command `/setelan-ai` — setelan AI per member + kepribadian AI per server.

Gaya purpleGPT (`/settings` & `/server_prompt`), versi kita: tanpa pilihan model, tanpa biaya
tambahan. Instruksi hanya teks tambahan pada prompt AI, jadi kuota tetap sama.
"""

from __future__ import annotations

import discord
from discord import app_commands

import ai_user_settings as aus
import config

PANJANG = [
    app_commands.Choice(name="✂️ Singkat (maks 3 kalimat)", value="singkat"),
    app_commands.Choice(name="⚖️ Normal", value="normal"),
    app_commands.Choice(name="📚 Detail (poin + contoh)", value="detail"),
]
RASIO = [
    app_commands.Choice(name=f"{meta['emoji']} {nama}", value=nama)
    for nama, meta in config.RATIO_OPTIONS.items()
]
TEMPERATUR = [
    app_commands.Choice(name="🤖 Ikuti bawaan model", value="bawaan"),
    app_commands.Choice(name="🧊 Konsisten (0,2)", value="konsisten"),
    app_commands.Choice(name="⚖️ Seimbang (0,7)", value="seimbang"),
    app_commands.Choice(name="✨ Kreatif (1,0)", value="kreatif"),
]
BAHASA = [
    app_commands.Choice(name="🌐 Otomatis (ikuti bahasa percakapan)", value="auto"),
    app_commands.Choice(name="🇮🇩 Bahasa Indonesia", value="id"),
    app_commands.Choice(name="🇬🇧 English", value="en"),
    app_commands.Choice(name="🇪🇸 Español", value="es"),
    app_commands.Choice(name="🇫🇷 Français", value="fr"),
    app_commands.Choice(name="🇯🇵 日本語", value="ja"),
    app_commands.Choice(name="🇰🇷 한국어", value="ko"),
    app_commands.Choice(name="🇵🇹 Português", value="pt"),
    app_commands.Choice(name="🇨🇳 中文", value="zh"),
]

setelan_ai_group = app_commands.Group(
    name="setelan-ai", description="Atur gaya jawaban AI untukmu (dan kepribadian AI server ini)"
)


def _admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


def _bahasa_label(kode: str) -> str:
    return BAHASA[kode] or "Otomatis (ikuti bahasa percakapan)"


def _temperature_label(kode: str) -> str:
    return next((c.name for c in TEMPERATUR if c.value == kode), "Ikuti bawaan model")


@setelan_ai_group.command(name="lihat", description="Lihat setelan AI-mu di server ini")
async def setelan_lihat(interaction: discord.Interaction):
    data = aus.get_user(interaction.user.id)
    server = aus.get_server_prompt(interaction.guild_id or 0)
    embed = discord.Embed(
        title="⚙️ Setelan AI-mu",
        colour=discord.Colour.purple(),
    )
    embed.add_field(name="Panjang jawaban", value=f"`{data['panjang']}`", inline=True)
    embed.add_field(name="Temperature", value=_temperature_label(data["temperatur"]), inline=True)
    embed.add_field(name="Bahasa balasan", value=_bahasa_label(data["bahasa"]), inline=True)
    embed.add_field(name="Rasio gambar", value=f"`{data['rasio'] or 'setelan channel'}`", inline=True)
    embed.add_field(
        name="Prompt pribadi",
        value=f"_{discord.utils.escape_markdown(data['prompt'])}_" if data["prompt"] else "_belum diatur_",
        inline=False,
    )
    embed.add_field(
        name="Kepribadian server",
        value=f"_{discord.utils.escape_markdown(server)}_" if server else "_belum diatur_",
        inline=False,
    )
    embed.set_footer(text="Ubah dengan /setelan-ai atur · reset dengan /setelan-ai reset")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@setelan_ai_group.command(
    name="atur", description="Atur gaya jawaban AI, bahasa, temperature, & rasio gambar"
)
@app_commands.describe(
    panjang="Seberapa panjang AI menjawab",
    prompt="Instruksi pribadi (maks 300 huruf), mis. 'pakai bahasa santai'",
    rasio="Rasio gambar bawaan untuk /gambar",
    temperatur="Lebih konsisten untuk fakta, lebih kreatif untuk ide",
    bahasa="Bahasa balasan yang kamu inginkan",
)
@app_commands.choices(panjang=PANJANG, rasio=RASIO, temperatur=TEMPERATUR, bahasa=BAHASA)
async def setelan_atur(
    interaction: discord.Interaction,
    panjang: app_commands.Choice[str] | None = None,
    prompt: str | None = None,
    rasio: app_commands.Choice[str] | None = None,
    temperatur: app_commands.Choice[str] | None = None,
    bahasa: app_commands.Choice[str] | None = None,
):
    data = aus.set_user(
        interaction.user.id,
        panjang=panjang.value if panjang else None,
        prompt=prompt,
        rasio=rasio.value if rasio else None,
        temperatur=temperatur.value if temperatur else None,
        bahasa=bahasa.value if bahasa else None,
    )
    await aus.save_to_disk()
    rincian = [f"panjang `{data['panjang']}`", f"bahasa **{_bahasa_label(data['bahasa'])}**"]
    rincian.append(f"temperature **{_temperature_label(data['temperatur'])}**")
    if data["prompt"]:
        rincian.append(f"prompt _{discord.utils.escape_markdown(data['prompt'][:80])}_")
    if data["rasio"]:
        rincian.append(f"rasio `{data['rasio']}`")
    await interaction.response.send_message(
        "✅ Setelan AI disimpan: " + ", ".join(rincian) + ".", ephemeral=True
    )


@setelan_ai_group.command(
    name="prompt-server", description="(Admin) Atur kepribadian AI untuk seluruh server"
)
@app_commands.describe(teks="Kepribadian/tone AI di server ini (kosongkan untuk menghapus)")
async def setelan_prompt_server(interaction: discord.Interaction, teks: str | None = None):
    if interaction.guild_id is None:
        return
    if not _admin(interaction):
        await interaction.response.send_message(
            "🔒 Hanya Admin yang bisa mengubah kepribadian AI server.", ephemeral=True
        )
        return
    hasil = aus.set_server_prompt(interaction.guild_id, teks or "", oleh=interaction.user.id)
    await aus.save_to_disk()
    if hasil:
        await interaction.response.send_message(
            f"🧠 Kepribadian AI server disimpan:\n> {discord.utils.escape_markdown(hasil[:400])}",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "🧠 Kepribadian AI server dihapus (kembali ke gaya bawaan).", ephemeral=True
        )


@setelan_ai_group.command(name="reset", description="Kembalikan setelan AI-mu ke bawaan")
async def setelan_reset(interaction: discord.Interaction):
    aus.reset_user(interaction.user.id)
    await aus.save_to_disk()
    await interaction.response.send_message(
        "♻️ Setelan AI-mu kembali ke bawaan (panjang *normal*, bahasa & temperature otomatis).",
        ephemeral=True,
    )


def register_setelan_ai_cog(bot) -> None:
    bot.tree.add_command(setelan_ai_group)


__all__ = ["register_setelan_ai_cog", "setelan_ai_group"]
