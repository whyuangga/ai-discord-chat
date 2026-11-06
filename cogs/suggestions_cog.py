"""Cog `/saran` (kotak saran + voting) & `/embed` (pembuat pengumuman cantik)."""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import link_embed
import message_template
import suggestions as sg
import webhook_identity
import ui_kit
import ui_theme
from views import SuggestionVoteView

logger = logging.getLogger("gemini_bot.suggestions_cog")

saran_group = app_commands.Group(
    name="saran",
    description="Kotak saran: member mengirim usulan, warga voting lewat tombol 👍/👎",
    guild_only=True,
)

embed_group = app_commands.Group(
    name="embed",
    description="Buat & kirim pengumuman berformat rapi tanpa perlu dashboard",
    guild_only=True,
)


def _is_staff(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild or perms.manage_messages))


def parse_color(value: str) -> discord.Colour:
    """Menerima `#RRGGBB`, `RRGGBB`, atau nama warna dasar."""
    text = str(value or "").strip().lstrip("#").lower()
    named = {
        "ungu": "9b59b6",
        "purple": "9b59b6",
        "biru": "3498db",
        "blue": "3498db",
        "merah": "e74c3c",
        "red": "e74c3c",
        "hijau": "2ecc71",
        "green": "2ecc71",
        "emas": "f1c40f",
        "gold": "f1c40f",
        "abu": "95a5a6",
        "gray": "95a5a6",
    }
    hex_value = named.get(text, text)
    if re.fullmatch(r"[0-9a-f]{6}", hex_value):
        return discord.Colour(int(hex_value, 16))
    return discord.Colour(0x9B59B6)


# ==============================================================================
# /saran
# ==============================================================================
@saran_group.command(name="pasang", description="(Admin) Tentukan channel tempat saran dikirim")
@app_commands.describe(channel="Channel khusus kotak saran", nonaktifkan="True untuk mematikan kotak saran")
async def saran_pasang_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    nonaktifkan: bool = False,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    if nonaktifkan:
        sg.set_channel(interaction.guild.id, None)
        await sg.save_suggestions_to_disk()
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                interaction.guild.id, "lock", "Kotak Saran Dimatikan", "Member tidak bisa lagi mengirim saran."
            ),
            ephemeral=True,
        )
        return

    if channel is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel:` dulu, mis. `/saran pasang channel:#saran`.", ephemeral=True
        )
        return

    sg.set_channel(interaction.guild.id, channel.id)
    await sg.save_suggestions_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Kotak Saran Aktif",
            f"Channel: {channel.mention}\n\n"
            "Member mengirim usulan dengan `/saran kirim teks:...`, lalu warga voting lewat tombol 👍/👎.",
        ),
        ephemeral=True,
    )


@saran_group.command(name="kirim", description="Kirim usulanmu ke kotak saran (bisa di-vote warga)")
@app_commands.describe(teks="Usulan atau ide kamu untuk server ini")
async def saran_kirim_cmd(interaction: discord.Interaction, teks: str):
    if interaction.guild is None:
        return

    channel_id = sg.get_channel(interaction.guild.id)
    if channel_id is None:
        await interaction.response.send_message(
            "ℹ️ Kotak saran belum diaktifkan. Minta Admin menjalankan `/saran pasang channel:#saran`.",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Channel kotak saran tidak ditemukan (mungkin dihapus). Minta Admin memasang ulang.",
            ephemeral=True,
        )
        return

    try:
        item = sg.add_suggestion(interaction.guild.id, interaction.user.id, teks)
    except ValueError as exc:
        await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        message = await channel.send(
            content=f"💡 Saran baru dari {interaction.user.mention}!",
            embed=sg.build_suggestion_embed(interaction.guild.id, item),
            view=SuggestionVoteView(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.followup.send(f"⚠️ Gagal mengirim saran: {exc}", ephemeral=True)
        return

    sg.bind_message(interaction.guild.id, item["id"], message.id)
    await sg.save_suggestions_to_disk()
    await ui_kit.send_status(
        interaction,
        follow=True,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            f"Saran #{item['id']} Terkirim",
            f"Usulanmu sudah tampil di {channel.mention}. Terima kasih sudah ikut membangun server! 💜",
        ),
        ephemeral=True,
    )


@saran_group.command(name="daftar", description="Lihat saran terbaru (bisa difilter status)")
@app_commands.describe(status="Filter status saran", jumlah="Berapa saran ditampilkan")
@app_commands.choices(
    status=[
        app_commands.Choice(name="🆕 Baru", value="baru"),
        app_commands.Choice(name="🛠️ Sedang dikerjakan", value="dikerjakan"),
        app_commands.Choice(name="✅ Diterima", value="diterima"),
        app_commands.Choice(name="❌ Ditolak", value="ditolak"),
    ]
)
async def saran_daftar_cmd(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] | None = None,
    jumlah: app_commands.Range[int, 1, 20] = 8,
):
    if interaction.guild is None:
        return
    items = sg.list_suggestions(
        interaction.guild.id, status=status.value if status else None, limit=int(jumlah)
    )
    if not items:
        await interaction.response.send_message("ℹ️ Belum ada saran tercatat.", ephemeral=True)
        return

    lines = []
    for item in items:
        meta = sg.STATUSES.get(str(item.get("status")), sg.STATUSES["baru"])
        lines.append(
            f"{meta['emoji']} **#{item['id']}** {str(item.get('text'))[:90]} — "
            f"👍 `{len(item.get('up') or [])}` 👎 `{len(item.get('down') or [])}`"
        )
    await interaction.response.send_message(
        embed=ui_theme.apply_embed_theme(
            discord.Embed(
                title="💡 Daftar Saran",
                description="\n".join(lines)[:4000],
            ),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


@saran_group.command(name="status", description="(Staff) Ubah status sebuah saran")
@app_commands.describe(id="Nomor saran", status="Status baru")
@app_commands.choices(
    status=[
        app_commands.Choice(name="🆕 Baru", value="baru"),
        app_commands.Choice(name="🛠️ Sedang dikerjakan", value="dikerjakan"),
        app_commands.Choice(name="✅ Diterima", value="diterima"),
        app_commands.Choice(name="❌ Ditolak", value="ditolak"),
    ]
)
async def saran_status_cmd(
    interaction: discord.Interaction,
    id: app_commands.Range[int, 1, 100000],
    status: app_commands.Choice[str],
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message("⚠️ Command ini khusus **staff**.", ephemeral=True)
        return

    item = sg.set_status(interaction.guild.id, int(id), status.value)
    if item is None:
        await interaction.response.send_message(f"⚠️ Saran `#{id}` tidak ditemukan.", ephemeral=True)
        return
    await sg.save_suggestions_to_disk()

    # Perbarui pesan aslinya agar badge status langsung berubah
    channel_id = sg.get_channel(interaction.guild.id)
    channel = interaction.guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel) and item.get("message_id"):
        try:
            message = await channel.fetch_message(int(item["message_id"]))
            await message.edit(
                embed=sg.build_suggestion_embed(interaction.guild.id, item),
                view=SuggestionVoteView(),
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        else:
            try:
                await channel.send(f"<@{item['author_id']}> saranmu **#{item['id']}** kini berstatus "
                                   f"**{sg.STATUSES[status.value]['label']}**!", delete_after=30)
            except (discord.Forbidden, discord.HTTPException):
                pass

    meta = sg.STATUSES[status.value]
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            f"Saran #{item['id']} — {meta['label']}",
            f"Status saran diperbarui menjadi **{meta['emoji']} {meta['label']}**.\n"
            f"• Pengusul: {sg.mention_author(item)}\n"
            f"• Skor voting: `{sg.score(item):+d}`",
        ),
        ephemeral=True,
    )


@saran_group.command(name="hapus", description="(Admin) Hapus saran beserta pesannya")
@app_commands.describe(id="Nomor saran yang dihapus")
async def saran_hapus_cmd(interaction: discord.Interaction, id: app_commands.Range[int, 1, 100000]):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild)):
        await interaction.response.send_message("⚠️ Hanya **Admin** yang bisa menghapus saran.", ephemeral=True)
        return

    item = sg.get_suggestion(interaction.guild.id, int(id))
    if item is None:
        await interaction.response.send_message(f"⚠️ Saran `#{id}` tidak ditemukan.", ephemeral=True)
        return

    channel_id = sg.get_channel(interaction.guild.id)
    channel = interaction.guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel) and item.get("message_id"):
        try:
            message = await channel.fetch_message(int(item["message_id"]))
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    sg.delete_suggestion(interaction.guild.id, int(id))
    await sg.save_suggestions_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id, "trash", "Saran Dihapus", f"Saran `#{id}` beserta pesannya sudah dihapus."
        ),
        ephemeral=True,
    )


# ==============================================================================
# /embed
# ==============================================================================
class EmbedBuilderModal(discord.ui.Modal, title="Buat Pesan Embed"):
    """Modal pengisian embed — hasilnya dikirim ke channel yang dipilih."""

    def __init__(self, channel: discord.TextChannel, color: discord.Colour):
        super().__init__()
        self.channel = channel
        self.color = color
        self.judul = discord.ui.TextInput(label="Judul", max_length=256, required=False)
        self.deskripsi = discord.ui.TextInput(
            label="Isi pesan", style=discord.TextStyle.paragraph, max_length=3500
        )
        self.gambar = discord.ui.TextInput(
            label="URL gambar/banner (opsional)", required=False, max_length=500
        )
        self.footer = discord.ui.TextInput(label="Footer (opsional)", required=False, max_length=200)
        for item in (self.judul, self.deskripsi, self.gambar, self.footer):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = {
            "member": getattr(interaction, "user", None),
            "guild": getattr(interaction, "guild", None),
            "channel": self.channel,
        }
        judul = message_template.render(str(self.judul or ""), **ctx)
        embed = discord.Embed(
            title=judul[:256] or None,
            description=message_template.render(str(self.deskripsi), **ctx)[:4000],
            colour=self.color,
        )
        image = str(self.gambar or "").strip()
        if image.startswith(("http://", "https://")):
            embed.set_image(url=image)
        footer = message_template.render(str(self.footer or ""), **ctx).strip()
        if footer:
            embed.set_footer(text=footer[:200])
        await self.channel.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Embed terkirim ke {self.channel.mention}.", ephemeral=True
        )


@embed_group.command(name="buat", description="Buat pengumuman embed lewat formulir lalu kirim ke channel")
@app_commands.describe(
    channel="Channel tujuan pengumuman",
    warna="Warna embed: #9B59B6, ungu, biru, merah, hijau, emas, atau abu",
)
async def embed_buat_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    warna: str = "#9B59B6",
):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild or perms.manage_messages)):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    colour = parse_color(warna)
    await interaction.response.send_modal(EmbedBuilderModal(channel, colour))


@embed_group.command(name="cepat", description="Kirim embed tanpa formulir (judul + isi langsung)")
@app_commands.describe(
    channel="Channel tujuan",
    judul="Judul pengumuman",
    isi="Isi pengumuman",
    warna="Warna: #9B59B6 / ungu / biru / merah / hijau / emas / abu",
    gambar="URL gambar banner (opsional)",
)
async def embed_cepat_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    judul: str,
    isi: str,
    warna: str = "#9B59B6",
    gambar: str | None = None,
):
    if interaction.guild is None:
        return
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (perms.administrator or perms.manage_guild or perms.manage_messages)):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    ctx = {"member": interaction.user, "guild": interaction.guild, "channel": channel}
    judul_teks = message_template.render(judul, **ctx)
    isi_teks = message_template.render(isi, **ctx)
    embed = discord.Embed(
        title=judul_teks[:256] or None, description=isi_teks[:4000], colour=parse_color(warna)
    )
    if gambar and gambar.startswith(("http://", "https://")):
        embed.set_image(url=gambar)
    ui_theme.apply_embed_theme(embed, interaction.guild.id, footer=interaction.guild.name)

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        await interaction.response.send_message(f"⚠️ Gagal mengirim embed: {exc}", ephemeral=True)
        return
    peringatan = message_template.check(f"{judul}\n{isi}", member=interaction.user)
    catatan = ("\n" + "\n".join(f"-# ⚠️ {p}" for p in peringatan)) if peringatan else ""
    await interaction.response.send_message(
        f"✅ Embed terkirim ke {channel.mention}.{catatan}", ephemeral=True
    )


@embed_group.command(
    name="sebagai",
    description="Kirim pesan dengan nama & avatar sendiri lewat webhook (butuh Manage Webhooks)",
)
@app_commands.describe(
    nama="Nama yang tampil di pesan, mis. `📢 Pengumuman Server`",
    isi="Isi pesan",
    channel="Channel tujuan (bawaan: channel ini)",
    judul="Judul bila ingin tampil sebagai embed (opsional)",
    avatar="URL avatar khusus untuk pesan ini (opsional)",
    warna="Warna embed: #9B59B6 / ungu / biru / merah / hijau (opsional)",
)
async def embed_sebagai_cmd(
    interaction: discord.Interaction,
    nama: str,
    isi: str,
    channel: discord.TextChannel | discord.Thread | None = None,
    judul: str | None = None,
    avatar: str | None = None,
    warna: str | None = None,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    target = channel or interaction.channel
    if target is None or not hasattr(target, "webhooks"):
        await interaction.response.send_message(
            "⚠️ Pilih channel teks atau thread sebagai tujuan.", ephemeral=True
        )
        return

    ctx = {"member": interaction.user, "guild": interaction.guild, "channel": target}
    ok_nama, nama_bersih = webhook_identity.valid_name(
        message_template.render(nama, **ctx)
    )
    if not ok_nama:
        await interaction.response.send_message(f"⚠️ {nama_bersih}", ephemeral=True)
        return
    ok_avatar, avatar_bersih = webhook_identity.valid_avatar(avatar)
    if not ok_avatar:
        await interaction.response.send_message(
            "⚠️ `avatar` harus URL `http://` atau `https://`.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    berhasil, keterangan = await webhook_identity.kirim_sebagai(
        target,
        nama=nama_bersih,
        isi=message_template.render(isi, **ctx),
        judul=message_template.render(judul, **ctx) if judul else None,
        avatar=avatar_bersih,
        warna=parse_color(warna) if warna else None,
    )
    if not berhasil:
        await interaction.followup.send(f"⚠️ {keterangan}", ephemeral=True)
        return

    await webhook_identity.save_to_disk()
    await interaction.followup.send(
        f"✅ Pesan terkirim ke {getattr(target, 'mention', 'channel')} dengan nama **{nama_bersih}**.\n"
        "-# Pesan dikirim lewat webhook, bukan sebagai bot — mention massal dinonaktifkan.",
        ephemeral=True,
    )


@embed_group.command(
    name="webhook",
    description="Cek / hapus webhook identitas kustom yang dipakai bot di sebuah channel",
)
@app_commands.describe(channel="Channel yang diperiksa", hapus="True untuk menghapus webhook-nya")
async def embed_webhook_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.Thread | None = None,
    hapus: bool = False,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    target = channel or interaction.channel
    if target is None or not hasattr(target, "webhooks"):
        await interaction.response.send_message("⚠️ Pilih channel teks atau thread.", ephemeral=True)
        return

    if hapus:
        await interaction.response.defer(ephemeral=True, thinking=True)
        berhasil, keterangan = await webhook_identity.hapus_webhook(target)
        if berhasil:
            await webhook_identity.save_to_disk()
            await interaction.followup.send(
                f"🧹 Webhook identitas di {getattr(target, 'mention', 'channel')} sudah dihapus. "
                "Bot akan membuat ulang saat `/embed sebagai` dipakai lagi.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"⚠️ {keterangan}", ephemeral=True)
        return

    webhook_id = webhook_identity.cached_webhook_id(target)
    await interaction.response.send_message(
        (
            f"🔗 Webhook identitas **aktif** di {getattr(target, 'mention', 'channel')} "
            f"(ID `{webhook_id}`).\n"
            "-# Hapus dengan `/embed webhook hapus:True` bila ingin bot berhenti memakainya."
        )
        if webhook_id
        else (
            f"ℹ️ Belum ada webhook identitas di {getattr(target, 'mention', 'channel')}. "
            "Bot membuatnya otomatis saat `/embed sebagai` pertama kali dipakai."
        ),
        ephemeral=True,
    )


@embed_group.command(
    name="variabel",
    description="Daftar variabel yang bisa dipakai di judul/isi embed (mis. {server.members})",
)
async def embed_variabel_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    kelompok = (
        ("👤 Member", message_template.MEMBER_TOKENS),
        ("🏠 Server", message_template.SERVER_TOKENS),
        ("💬 Channel", message_template.CHANNEL_TOKENS),
        ("⏰ Waktu", message_template.MISC_TOKENS),
        ("🔁 Alias lama", message_template.ALIAS_TOKENS),
    )
    embed = ui_theme.status_embed(
        interaction.guild.id,
        "info",
        "Variabel Pesan",
        "Tulis variabel di bawah ini pada judul/isi `/embed` atau `/pengumuman` — "
        "nilainya diisi otomatis saat pesan dikirim.",
    )
    for judul, tokens in kelompok:
        embed.add_field(
            name=judul,
            value="\n".join(message_template.help_lines(tokens))[:1024],
            inline=False,
        )
    embed.set_footer(text="Variabel tak dikenal dibiarkan apa adanya agar salah ketik terlihat.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# TAUTAN EMBED — /embed tautan (halaman /l/<kode> di situs Vercel)
# ==============================================================================
def _hex_warna(value: str | None) -> str:
    """Nama warna atau `#RRGGBB` → `rrggbb` (dipakai halaman `/l/<kode>`)."""
    if not value:
        return ""
    return format(parse_color(value).value & 0xFFFFFF, "06x")


tautan_group = app_commands.Group(
    name="tautan",
    description="Tautan yang tampil sebagai embed cantik di Discord (halaman /l/<kode>)",
)


@tautan_group.command(name="buat", description="Buat tautan embed: tampil cantik, klik = buka URL tujuan")
@app_commands.describe(
    judul="Judul yang muncul di embed",
    isi="Deskripsi singkat di embed (boleh beberapa baris)",
    url="URL tujuan saat tautan diklik (wajib http/https)",
    gambar="URL gambar besar di embed (opsional)",
    sampul="URL thumbnail kecil di kanan (opsional)",
    warna="Warna garis embed: ungu / biru / merah / hijau / emas / abu / 9B59B6",
    provider="Nama sumber yang tampil di embed (opsional)",
    situs="Nama situs (opsional, bawaan: nama server)",
)
async def tautan_buat_cmd(
    interaction: discord.Interaction,
    url: str,
    judul: str | None = None,
    isi: str | None = None,
    gambar: str | None = None,
    sampul: str | None = None,
    warna: str | None = None,
    provider: str | None = None,
    situs: str | None = None,
):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    record, galat = link_embed.create_link(
        interaction.guild.id,
        title=judul or "",
        description=isi or "",
        url=url,
        image=gambar or "",
        thumbnail=sampul or "",
        color=_hex_warna(warna),
        provider=provider or "",
        site=situs or interaction.guild.name,
        created_by=interaction.user.id,
    )
    if record is None:
        await interaction.response.send_message(
            "⚠️ Tautan belum bisa dibuat:\n" + "\n".join(f"• {g}" for g in galat)[:1500],
            ephemeral=True,
        )
        return

    await link_embed.save_to_disk()
    embed = ui_theme.status_embed(
        interaction.guild.id,
        "ok",
        "Tautan embed siap",
        f"**{record['title']}**\n```{record['url']}```\n"
        "Tempel tautan itu di pesan — Discord akan menampilkan embed dari halaman situs. "
        "Klik tautannya tetap membuka URL tujuan.",
        footer="Hapus dari daftar dengan /embed tautan hapus",
    )
    embed.add_field(
        name="Pratinjau isi",
        value=(
            f"**Judul:** {judul or '—'}\n"
            f"**Tujuan:** {url[:180]}\n"
            f"**Panjang URL:** {len(record['url'])} karakter"
        )[:1000],
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tautan_group.command(name="daftar", description="Lihat tautan embed yang pernah dibuat di server ini")
async def tautan_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    rows = link_embed.list_links(interaction.guild.id)
    if not rows:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                interaction.guild.id,
                "info",
                "Belum ada tautan embed",
                "Buat yang pertama: `/embed tautan url:https://situs.kamu judul:\"Panduan Server\"`.",
            ),
            ephemeral=True,
        )
        return

    baris = [
        f"**{record['title']}** (`{record['id']}`)\n-# {record['url']}"
        for record in rows
    ]
    info = link_embed.stats(interaction.guild.id)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "info",
            f"🔗 Tautan Embed ({info['total']}/{info['maks']})",
            "\n\n".join(baris)[:3800],
            footer="Tautan tetap hidup walau dihapus dari daftar — halaman ada di situs.",
        ),
        ephemeral=True,
    )


@tautan_group.command(name="hapus", description="Hapus tautan embed dari daftar server")
@app_commands.describe(tautan="ID (mis. l1a2b3c4) atau judul tautan")
async def tautan_hapus_cmd(interaction: discord.Interaction, tautan: str):
    if interaction.guild is None:
        return
    if not _is_staff(interaction):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **staff** (Manage Messages / Manage Server).", ephemeral=True
        )
        return

    record = link_embed.delete_link(interaction.guild.id, tautan)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                interaction.guild.id, "warn", "Tautan tidak ditemukan",
                "Lihat daftarnya lewat `/embed tautan daftar`.",
            ),
            ephemeral=True,
        )
        return

    await link_embed.save_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            interaction.guild.id,
            "ok",
            "Tautan dihapus dari daftar",
            f"**{record['title']}** tidak lagi muncul di `/embed tautan daftar`.\n"
            "-# Tautan lama tetap bisa dibuka; hapus pesannya bila ingin benar-benar hilang.",
        ),
        ephemeral=True,
    )


def register_suggestions_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/saran` & `/embed`."""
    embed_group.add_command(tautan_group)
    bot.tree.add_command(saran_group)
    bot.tree.add_command(embed_group)


__all__ = [
    "register_suggestions_cog",
    "saran_group",
    "embed_group",
    "tautan_group",
    "EmbedBuilderModal",
    "parse_color",
]
