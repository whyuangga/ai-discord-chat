"""Cog `/tag` — jawaban siap pakai milik server (0 kuota AI).

Semua member boleh **memanggil** tag; hanya staf (Manage Messages / Manage Server /
Administrator) yang boleh membuat, mengubah, & menghapus.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import tags
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.tags_cog")

tag_group = app_commands.Group(
    name="tag",
    description="Tag jawaban siap pakai server (aturan, harga, jadwal, …) — 0 kuota AI",
    guild_only=True,
)


def _is_staff(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    if perms is None:
        return False
    return bool(
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_guild", False)
        or getattr(perms, "manage_messages", False)
    )


def _ringkas(tag: dict, panjang: int = 80) -> str:
    isi = " ".join(str(tag.get("isi") or "").split())
    return isi[:panjang] + ("…" if len(isi) > panjang else "")


def _embed_tag(guild_id: int, tag: dict, *, judul: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=judul or f"🏷️ /tag {tag.get('nama')}",
        description=str(tag.get("isi") or "")[:4000],
    )
    embed.set_footer(text=f"dipakai {int(tag.get('dipakai') or 0)}× · 0 kuota AI")
    return ui_theme.apply_embed_theme(embed, guild_id)


async def _nama_tag_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    gid = interaction.guild_id or 0
    hasil = tags.cari(gid, current or "", limit=25)
    return [
        app_commands.Choice(name=f"{t.get('nama')} — {_ringkas(t, 60)}"[:100], value=str(t.get("nama"))[:100])
        for t in hasil
    ]


# ==============================================================================
# MEMBACA (semua member)
# ==============================================================================
@tag_group.command(name="lihat", description="Tampilkan isi satu tag")
@app_commands.describe(nama="Nama tag (ketik untuk mencari)")
@app_commands.autocomplete(nama=_nama_tag_autocomplete)
async def tag_lihat_cmd(interaction: discord.Interaction, nama: str):
    if interaction.guild is None:
        return
    tag = tags.pakai(interaction.guild.id, nama)
    if tag is None:
        await interaction.response.send_message(
            f"⚠️ Tag `{nama}` tidak ada. Lihat daftarnya dengan `/tag daftar`.",
            ephemeral=True,
        )
        return
    await tags.save_tags_to_disk()
    await interaction.response.send_message(embed=_embed_tag(interaction.guild.id, tag))


@tag_group.command(name="daftar", description="Daftar semua tag server")
async def tag_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    data = tags.statistik(interaction.guild.id)
    daftar = tags.daftar(interaction.guild.id, limit=40)
    if not daftar:
        await interaction.response.send_message(
            "🏷️ Server ini belum punya tag. Staf bisa membuatnya dengan "
            "`/tag buat nama:aturan isi:...` atau dari dashboard.",
            ephemeral=True,
        )
        return
    baris = "\n".join(f"• **`{t.get('nama')}`** — {_ringkas(t, 70)}" for t in daftar)
    embed = ui_theme.apply_embed_theme(
        discord.Embed(
            title=f"🏷️ Tag server ({data['total']}/{data['batas']})",
            description=baris[:4000],
        ),
        interaction.guild.id,
    )
    embed.set_footer(text="Panggil dengan /tag lihat nama:<tag> · 0 kuota AI")
    await interaction.response.send_message(embed=embed)


@tag_group.command(name="cari", description="Cari tag berdasarkan nama atau isinya")
@app_commands.describe(kata="Kata yang dicari (mis. refund)")
async def tag_cari_cmd(interaction: discord.Interaction, kata: str):
    if interaction.guild is None:
        return
    hasil = tags.cari(interaction.guild.id, kata, limit=10)
    if not hasil:
        await interaction.response.send_message(
            f"🔍 Tidak ada tag yang cocok dengan **{kata}**.", ephemeral=True
        )
        return
    baris = "\n".join(f"• **`{t.get('nama')}`** — {_ringkas(t, 70)}" for t in hasil)
    embed = ui_theme.apply_embed_theme(
        discord.Embed(title=f"🔍 Tag yang cocok: {kata}", description=baris[:4000]),
        interaction.guild.id,
    )
    await interaction.response.send_message(embed=embed)


# ==============================================================================
# MENULIS (staf)
# ==============================================================================
@tag_group.command(name="buat", description="Buat tag baru (staf)")
@app_commands.describe(nama="Nama singkat tag", isi="Jawaban lengkap yang akan dikirim")
async def tag_buat_cmd(interaction: discord.Interaction, nama: str, isi: str):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **staf** (Manage Messages / Manage Server) yang bisa membuat tag.",
            ephemeral=True,
        )
        return

    kode, tag = tags.tambah(interaction.guild.id, nama, isi, oleh=interaction.user.id)
    pesan = {
        "nama_kosong": "⚠️ Nama tag tidak boleh kosong.",
        "isi_kosong": "⚠️ Isi tag tidak boleh kosong.",
        "penuh": f"⚠️ Server sudah punya {tags.MAX_TAG_PER_GUILD} tag (batas maksimum). "
                 "Hapus satu dulu dengan `/tag hapus`.",
        "sudah_ada": f"⚠️ Tag `{tags.normalisasi(nama)}` sudah ada. Gunakan `/tag ubah` "
                     "untuk memperbaruinya.",
    }
    if kode != "ok":
        await interaction.response.send_message(
            pesan.get(kode, "⚠️ Tag gagal disimpan."),
            ephemeral=(kode != "penuh"),
        )
        return

    await tags.save_tags_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Tag Dibuat",
            f"🏷️ **`{tag['nama']}`** siap dipakai.\n"
            f"Panggil dengan `/tag lihat nama:{tag['nama']}` atau ketik `/tag lihat`.",
        ),
        ephemeral=True,
    )


@tag_group.command(name="ubah", description="Perbarui isi tag yang sudah ada (staf)")
@app_commands.describe(nama="Nama tag", isi="Isi baru")
@app_commands.autocomplete(nama=_nama_tag_autocomplete)
async def tag_ubah_cmd(interaction: discord.Interaction, nama: str, isi: str):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **staf** yang bisa mengubah tag.", ephemeral=True
        )
        return

    kode, tag = tags.ubah(interaction.guild.id, nama, isi, oleh=interaction.user.id)
    if kode != "ok":
        pesan = (
            f"⚠️ Tag `{nama}` tidak ada — buat dulu dengan `/tag buat`."
            if kode == "tidak_ada"
            else "⚠️ Isi tag tidak boleh kosong."
        )
        await interaction.response.send_message(pesan, ephemeral=True)
        return

    await tags.save_tags_to_disk()
    await interaction.response.send_message(
        f"✅ Tag **`{tag['nama']}`** diperbarui.", ephemeral=True
    )


@tag_group.command(name="hapus", description="Hapus satu tag (staf)")
@app_commands.describe(nama="Nama tag yang dihapus")
@app_commands.autocomplete(nama=_nama_tag_autocomplete)
async def tag_hapus_cmd(interaction: discord.Interaction, nama: str):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Hanya **staf** yang bisa menghapus tag.", ephemeral=True
        )
        return

    ok = tags.hapus(interaction.guild.id, nama)
    if ok:
        await tags.save_tags_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "trash" if ok else "warn",
            "Tag Dihapus" if ok else "Tag Tidak Ditemukan",
            f"Tag `{tags.normalisasi(nama)}` sudah dihapus."
            if ok
            else f"Tidak ada tag bernama `{nama}`.",
        ),
        ephemeral=True,
    )


def register_tags_cog(bot: commands.Bot) -> None:
    """Mendaftarkan group `/tag` ke bot."""
    bot.tree.add_command(tag_group)


__all__ = ["register_tags_cog", "tag_group"]
