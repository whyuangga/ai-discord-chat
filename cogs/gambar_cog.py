"""Command `/gambar` — buat & edit gambar dari slash command (gaya purpleGPT `/draw` & `/edit`).

Tanpa dependency baru: memakai mesin `ai_handler.generate_image` yang sudah dipakai chat,
plus **5 rasio aspek** dan **3 belas gaya** bawaan. `/gambar edit` bisa memakai gambar lampiran
atau **gambar terakhir** yang dibuat di channel yang sama (tanpa unggah ulang).
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

import discord
from discord import app_commands

import ai_handler
import config
from utils import extract_message_attachments

logger = logging.getLogger("gemini_bot.gambar_cog")

JEDA_DETIK = 20
_terakhir: dict[int, tuple[dict, str]] = {}

RASIO = [
    app_commands.Choice(name=f"{meta['emoji']} {nama}", value=nama)
    for nama, meta in config.RATIO_OPTIONS.items()
]
GAYA = [
    app_commands.Choice(name=f"{meta['emoji']} {meta['label']}", value=nama)
    for nama, meta in config.STYLE_OPTIONS.items()
]

gambar_group = app_commands.Group(
    name="gambar", description="Buat atau edit gambar dengan AI (Gemini)"
)

_jeda: dict[int, float] = {}


def _sisa_jeda(user_id: int) -> int:
    sisa = _jeda.get(int(user_id), 0.0) + JEDA_DETIK - time.time()
    return max(0, int(sisa))


async def _part_dari_lampiran(lampiran: discord.Attachment | None) -> tuple[list[dict], str]:
    """Ubah lampiran jadi `inlineData` Gemini (format sama dengan chat)."""
    if lampiran is None:
        return [], ""
    try:
        palsu = SimpleNamespace(
            attachments=[lampiran], stickers=[], content="", mentions=[], embeds=[]
        )
        parts, nama, _teks, _peringatan = await extract_message_attachments(palsu)
        if parts:
            return parts[:1], (nama or [lampiran.filename])[0]
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal membaca lampiran gambar: %s", exc)
    return [], ""


async def _jawab_gambar(
    interaction: discord.Interaction,
    prompt: str,
    *,
    lampiran: discord.Attachment | None = None,
    edit: bool = False,
    rasio: str | None = None,
    gaya: str | None = None,
) -> None:
    sisa = _sisa_jeda(interaction.user.id)
    if sisa > 0:
        await interaction.response.send_message(
            f"⏳ Tunggu **{sisa} detik** lagi sebelum meminta gambar berikutnya.", ephemeral=True
        )
        return

    if rasio is None:
        try:
            import ai_user_settings

            rasio = ai_user_settings.rasio_bawaan(interaction.user.id) or None
        except Exception:  # pragma: no cover - jaring aman
            rasio = None

    parts, nama_acuan = await _part_dari_lampiran(lampiran)
    if edit and not parts:
        simpanan = _terakhir.get(int(interaction.channel_id or 0))
        if simpanan is None:
            await interaction.response.send_message(
                "Belum ada gambar di channel ini untuk diedit. Lampirkan gambar, atau jalankan "
                "`/gambar buat` dulu.",
                ephemeral=True,
            )
            return
        parts, nama_acuan = [simpanan[0]], simpanan[1]

    await interaction.response.defer(thinking=True)
    _jeda[int(interaction.user.id)] = time.time()

    engine, berkas, galat = await ai_handler.generate_image(
        int(interaction.channel_id or 0),
        prompt,
        reference_images=parts or None,
        style=gaya,
        ratio=rasio,
    )
    if berkas is None:
        _jeda.pop(int(interaction.user.id), None)
        await interaction.followup.send(
            f"⚠️ Gambar gagal dibuat: {galat or 'tidak ada detail.'}", ephemeral=True
        )
        return

    meta_rasio = config.RATIO_OPTIONS.get(rasio or "", {})
    keterangan = (
        f"🖼️ **{'Edit' if edit else 'Gambar baru'}** — `{prompt[:180]}`\n"
        f"⚙️ Rasio `{meta_rasio.get('aspect_ratio', 'setelan channel')}` · Gaya "
        f"`{gaya or 'setelan channel'}` · Mesin `{engine or '-'}`"
    )
    if edit and nama_acuan:
        keterangan += f"\n🧩 Acuan: `{nama_acuan[:60]}`"

    await interaction.followup.send(content=keterangan[:2000], file=berkas)

    # Simpan untuk `/gambar edit` berikutnya (hanya di memori, per channel).
    try:
        berkas.fp.seek(0)
        import base64

        data = base64.b64encode(berkas.fp.read()).decode("ascii")
        _terakhir[int(interaction.channel_id or 0)] = (
            {"inlineData": {"mimeType": "image/png", "data": data}},
            "gambar-terakhir.png",
        )
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Gagal menyimpan acuan gambar: %s", exc)


@gambar_group.command(name="buat", description="Buat gambar dari teks (opsional: gambar acuan)")
@app_commands.describe(
    prompt="Apa yang mau digambar",
    rasio="Rasio aspek gambar",
    gaya="Gaya artistik",
    acuan="Gambar referensi (opsional)",
)
@app_commands.choices(rasio=RASIO, gaya=GAYA)
async def gambar_buat(
    interaction: discord.Interaction,
    prompt: str,
    rasio: app_commands.Choice[str] | None = None,
    gaya: app_commands.Choice[str] | None = None,
    acuan: discord.Attachment | None = None,
):
    await _jawab_gambar(
        interaction,
        prompt,
        lampiran=acuan,
        rasio=rasio.value if rasio else None,
        gaya=gaya.value if gaya else None,
    )


@gambar_group.command(
    name="edit", description="Ubah gambar (pakai lampiran, atau gambar terakhir di channel ini)"
)
@app_commands.describe(prompt="Perubahan yang diinginkan", acuan="Gambar yang mau diubah (opsional)")
async def gambar_edit(
    interaction: discord.Interaction,
    prompt: str,
    acuan: discord.Attachment | None = None,
):
    await _jawab_gambar(interaction, prompt, lampiran=acuan, edit=True)


@gambar_group.command(name="pilihan", description="Lihat daftar rasio & gaya gambar yang tersedia")
async def gambar_pilihan(interaction: discord.Interaction):
    rasio = " · ".join(f"{m['emoji']} `{n}`" for n, m in config.RATIO_OPTIONS.items())
    gaya = " · ".join(f"{m['emoji']} `{n}`" for n, m in config.STYLE_OPTIONS.items())
    embed = discord.Embed(
        title="🎨 Pilihan gambar",
        description=f"**Rasio aspek**\n{rasio}\n\n**Gaya**\n{gaya}"[:4000],
        colour=discord.Colour.purple(),
    )
    embed.set_footer(text=f"Jeda {JEDA_DETIK} detik antar permintaan · kuota AI tetap dihitung")
    await interaction.response.send_message(embed=embed, ephemeral=True)


def register_gambar_cog(bot) -> None:
    """Daftarkan group `/gambar` ke tree bot."""
    bot.tree.add_command(gambar_group)


__all__ = ["gambar_group", "register_gambar_cog"]
