"""Command `/bangun` — bangun struktur server dari 15 tema atau deskripsi AI.

Alur aman (tidak ada yang dibuat sebelum Admin menekan **Terapkan**):

```
/bangun tema        → pratinjau + tombol Terapkan/Batal
/bangun rancang     → AI menyusun struktur → pratinjau + tombol yang sama
/bangun terapkan    → eksekusi rencana terakhir yang masih menunggu
/bangun riwayat     → apa yang terakhir dibangun & apakah masih bisa dibongkar
/bangun bongkar     → hapus HANYA item yang tercatat dibuat /bangun
```

Ide dari **Instabot** (15 tema instan) dan **purpleGPT** (`/genserver`).
Pola registrasi mengikuti cog lain di repo ini: cukup `bot.tree.add_command(bangun_group)`.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands

import ai_handler
import server_builder as sb

logger = logging.getLogger("gemini_bot.bangun_cog")

ALASAN = "Bangun server via /bangun"

bangun_group = app_commands.Group(
    name="bangun", description="Bangun struktur server dari 15 tema atau deskripsi AI"
)


def _admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_channels or perms.manage_guild))


async def _tolak(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "🔒 Perintah ini khusus **Admin** (butuh *Manage Channels*).", ephemeral=True
    )


async def _simpan() -> None:
    try:
        await sb.save_to_disk()
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal menyimpan riwayat bangun: %s", exc)


async def _rancang_ai(prompt: str) -> str:
    """Satu panggilan Gemini sekali pakai (tanpa menyentuh memori percakapan)."""
    try:
        return await ai_handler.get_ai_response(0, prompt)
    finally:
        ai_handler.thread_chats.pop(0, None)


def _embed_pratinjau(snapshot: dict, sumber: str) -> discord.Embed:
    label = str((snapshot.get("meta") or {}).get("label") or "Rancangan")
    asal = "🤖 Gemini" if sumber == "ai" else f"🎨 tema `{sumber.split(':')[-1]}`"
    embed = discord.Embed(
        title=f"🏗️ Pratinjau — {label}",
        description=sb.ringkas(snapshot)[:4000],
        colour=discord.Colour.from_rgb(88, 101, 242),
    )
    embed.add_field(name="Sumber", value=asal, inline=True)
    embed.add_field(
        name="Jumlah", value=f"{len(snapshot.get('channels') or [])} channel", inline=True
    )
    embed.set_footer(text="Belum ada yang dibuat. Tekan Terapkan untuk membuatnya.")
    return embed


async def terapkan_rencana(guild, snapshot: dict, actor_id: int) -> tuple[dict, str]:
    """Terapkan rencana ke server, lupakan rencana tertunda, lalu simpan riwayat."""
    hasil, pesan = await sb.terapkan(guild, snapshot, actor_id=actor_id, alasan=ALASAN)
    logger.info("Bangun server %s: %s", getattr(guild, "id", 0), pesan)
    await _simpan()
    return hasil, pesan


class KonfirmasiBangun(discord.ui.View):
    """Dua tombol: buat sekarang, atau batalkan tanpa efek apa pun."""

    def __init__(self, gid: int, snapshot: dict, sumber: str):
        super().__init__(timeout=600)
        self.gid = int(gid)
        self.snapshot = snapshot
        self.sumber = sumber

    @discord.ui.button(label="Terapkan", style=discord.ButtonStyle.success, emoji="🏗️")
    async def terapkan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _admin(interaction):
            await _tolak(interaction)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        sb.lupakan_siap(self.gid)
        _hasil, pesan = await terapkan_rencana(
            interaction.guild, self.snapshot, interaction.user.id
        )
        self.stop()
        await interaction.followup.send(pesan, ephemeral=True)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def batal(self, interaction: discord.Interaction, button: discord.ui.Button):
        sb.lupakan_siap(self.gid)
        self.stop()
        await interaction.response.edit_message(
            content="❌ Dibatalkan — tidak ada yang dibuat.", embed=None, view=None
        )


async def siapkan(interaction: discord.Interaction, snapshot: dict, sumber: str) -> bool:
    """Validasi → simpan sebagai menunggu → tampilkan pratinjau + tombol."""
    ok, alasan = sb.validasi(snapshot)
    if not ok:
        await interaction.response.send_message(f"⚠️ {alasan}", ephemeral=True)
        return False
    gid = int(interaction.guild_id or 0)
    sb.simpan_siap(gid, snapshot, sumber=sumber)
    await interaction.response.send_message(
        embed=_embed_pratinjau(snapshot, sumber),
        view=KonfirmasiBangun(gid, snapshot, sumber),
        ephemeral=True,
    )
    return True


# ==============================================================================
# COMMAND
# ==============================================================================


@bangun_group.command(name="tema", description="Bangun server dari tema siap pakai (15 pilihan)")
@app_commands.describe(tema="Nama tema (ketik untuk mencari)")
async def bangun_tema(interaction: discord.Interaction, tema: str):
    if interaction.guild is None or not _admin(interaction):
        await _tolak(interaction)
        return
    kunci = sb.cari_tema(tema)
    if not kunci:
        daftar = ", ".join(item["id"] for item in sb.daftar_tema())
        await interaction.response.send_message(
            f"Tema `{tema}` tidak ada. Pilihan: {daftar}", ephemeral=True
        )
        return
    snapshot = sb.tema_ke_snapshot(kunci, nama_server=interaction.guild.name)
    await siapkan(interaction, snapshot, f"tema:{kunci}")


@bangun_tema.autocomplete("tema")
async def _tema_otomatis(interaction: discord.Interaction, current: str):
    sekarang = str(current or "").casefold()
    return [
        app_commands.Choice(name=item["label"][:100], value=item["id"])
        for item in sb.daftar_tema()
        if sekarang in item["label"].casefold() or sekarang in item["id"]
    ][:25]


@bangun_group.command(
    name="rancang", description="AI menyusun struktur server dari deskripsi bebasmu"
)
@app_commands.describe(deskripsi="Contoh: server komunitas fotografi dengan kelas pemula")
async def bangun_rancang(interaction: discord.Interaction, deskripsi: str):
    if interaction.guild is None or not _admin(interaction):
        await _tolak(interaction)
        return
    if len(str(deskripsi or "").strip()) < 10:
        await interaction.response.send_message(
            "Ceritakan sedikit lebih panjang (minimal 10 huruf) supaya AI bisa merancang.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    snapshot, sumber = await sb.rancang(deskripsi, ai_call=_rancang_ai)
    ok, alasan = sb.validasi(snapshot)
    if not ok:
        await interaction.followup.send(f"⚠️ {alasan}", ephemeral=True)
        return
    gid = int(interaction.guild_id or 0)
    sb.simpan_siap(gid, snapshot, sumber=sumber)
    catatan = None if sumber == "ai" else "_AI sedang tidak tersedia — memakai tema terdekat._"
    await interaction.followup.send(
        content=catatan,
        embed=_embed_pratinjau(snapshot, sumber),
        view=KonfirmasiBangun(gid, snapshot, sumber),
        ephemeral=True,
    )


@bangun_group.command(
    name="terapkan", description="Terapkan rencana terakhir yang menunggu konfirmasi"
)
async def bangun_terapkan(interaction: discord.Interaction):
    if interaction.guild is None or not _admin(interaction):
        await _tolak(interaction)
        return
    entri = sb.ambil_siap(int(interaction.guild_id or 0))
    if not entri:
        await interaction.response.send_message(
            "Belum ada rencana yang menunggu. Jalankan `/bangun tema` atau `/bangun rancang` dulu.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    sb.lupakan_siap(int(interaction.guild_id or 0))
    _hasil, pesan = await terapkan_rencana(
        interaction.guild, entri["snapshot"], interaction.user.id
    )
    await interaction.followup.send(pesan, ephemeral=True)


@bangun_group.command(name="riwayat", description="Lihat riwayat build & rollback yang tersedia")
async def bangun_riwayat(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    daftar = sb.daftar_riwayat(int(interaction.guild.id))
    data = daftar[-1] if daftar else None
    if not data:
        await interaction.response.send_message(
            "Belum ada catatan pembangunan di server ini.", ephemeral=True
        )
        return
    dibuat = data.get("dibuat") or {}
    embed = discord.Embed(
        title=f"📜 Terakhir dibangun — {data.get('label')}",
        colour=discord.Colour.blurple(),
    )
    embed.add_field(name="Role", value=str(len(dibuat.get("roles") or [])), inline=True)
    embed.add_field(name="Kategori", value=str(len(dibuat.get("categories") or [])), inline=True)
    embed.add_field(name="Channel", value=str(len(dibuat.get("channels") or [])), inline=True)
    contoh = ", ".join(f"`{x}`" for x in (dibuat.get("channels") or [])[:12]) or "-"
    embed.add_field(name="Channel dibuat", value=contoh[:1024], inline=False)
    sebelumnya = len(daftar) - 1
    footer = (
        f"Pakai /bangun bongkar untuk membongkar build terbaru. {sebelumnya} build sebelumnya tersimpan; bisa diulang."
        if sebelumnya else "Pakai /bangun bongkar untuk membongkar item build terbaru ini."
    )
    embed.set_footer(text=footer[:2048])
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bangun_group.command(name="bongkar", description="Hapus HANYA item yang dibuat /bangun")
async def bangun_bongkar(interaction: discord.Interaction):
    if interaction.guild is None or not _admin(interaction):
        await _tolak(interaction)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, pesan = await sb.bongkar(interaction.guild)
    if ok:
        await _simpan()
    await interaction.followup.send(pesan, ephemeral=True)


def register_bangun_cog(bot) -> None:
    """Daftarkan group `/bangun` ke tree bot."""
    bot.tree.add_command(bangun_group)


__all__ = ["bangun_group", "register_bangun_cog"]
