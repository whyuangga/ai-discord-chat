"""Slash `/menu` — pembuat panel tombol & dropdown sendiri (role, link, command).

0 kuota AI. Semua aksi (beri role, jalankan command info) berjalan lokal.
"""

import io
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

import flows
import menu_builder
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.menu_cog")

menu_group = app_commands.Group(
    name="menu",
    description="Buat panel tombol/dropdown sendiri: role, link, & command (0 kuota AI)",
    guild_only=True,
)

_AKSI_CHOICES = [
    app_commands.Choice(name=f"{spec['emoji']} {spec['label']} — {spec['desc']}", value=key)
    for key, spec in menu_builder.SAFE_COMMANDS.items()
]

_GAYA_CHOICES = [
    app_commands.Choice(name="Abu-abu (bawaan)", value="abu"),
    app_commands.Choice(name="Biru", value="biru"),
    app_commands.Choice(name="Hijau", value="hijau"),
    app_commands.Choice(name="Merah", value="merah"),
]

_VIS_CHOICES = [
    app_commands.Choice(name="Ikuti command (bawaan)", value="auto"),
    app_commands.Choice(name="Hanya yang klik (ephemeral)", value="ephemeral"),
    app_commands.Choice(name="Tampil publik di channel", value="publik"),
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
            gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server* yang bisa mengatur menu."
        ),
        ephemeral=True,
    )
    return False


def _menu_or_error(interaction: discord.Interaction, gid: int, ref: str | None) -> dict | None:
    menu = menu_builder.get_menu(gid, ref)
    return menu


# ==============================================================================
# MEMBUAT & MENGIRIM PANEL
# ==============================================================================
@menu_group.command(name="buat", description="Buat panel menu baru & kirim ke channel (Admin)")
@app_commands.describe(
    judul="Judul panel, misal: Pusat Info Server",
    deskripsi="Penjelasan singkat (opsional) — boleh pakai variabel `{server.members}`",
    channel="Channel/thread/forum tujuan (bawaan: channel sekarang)",
    banner="Unggah gambar banner .png/.jpg (opsional)",
    banner_url="Atau tempel URL gambar banner (opsional)",
)
async def menu_buat_cmd(
    interaction: discord.Interaction,
    judul: str,
    deskripsi: str | None = None,
    channel: discord.TextChannel | discord.Thread | discord.ForumChannel | None = None,
    banner: discord.Attachment | None = None,
    banner_url: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    if banner is not None and not menu_builder.is_image_attachment(banner):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "error", "Banner tidak valid",
                "Unggah gambar **PNG/JPG/WebP** maksimal **8 MB**.",
            ),
            ephemeral=True,
        )
        return
    if banner_url and not str(banner_url).startswith(("http://", "https://")):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "URL banner tidak valid", "Harus diawali `http://` atau `https://`."),
            ephemeral=True,
        )
        return

    menu = menu_builder.create_menu(
        gid,
        judul,
        description=deskripsi or "",
        kind=menu_builder.MENU_KIND_MENU,
        banner_url=str(banner_url) if banner_url else None,
        channel_id=(channel or interaction.channel).id if (channel or interaction.channel) else None,
    )
    if menu is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Panel tidak bisa dibuat",
                f"Batas panel per server adalah **{menu_builder.MAX_MENUS_PER_GUILD}**. "
                "Hapus panel lama lewat `/menu hapus`.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    target = channel or interaction.channel

    file = None
    ref = None
    if banner is not None:
        try:
            data = await banner.read()
            file, ref = menu_builder.banner_file_from_attachment(banner, data)
        except (discord.HTTPException, AttributeError) as exc:
            logger.warning("Gagal membaca banner menu: %s", exc)

    message = await menu_builder.send_panel(interaction.client, menu, target, banner_file=file, banner_ref=ref)
    if message is None:
        menu_builder.delete_menu(gid, menu["id"])
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "error", "Gagal mengirim panel",
                f"Cek izin **Send Messages** & **Embed Links** di {getattr(target, 'mention', 'channel itu')}.",
            ),
            follow=True,
            ephemeral=True,
        )
        return

    await menu_builder.save_menus_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Panel menu dibuat",
            f"Panel **{menu['title']}** terkirim di {getattr(target, 'mention', 'channel')}.\n\n"
            "**Langkah berikutnya** (tambahkan isi panel):\n"
            f"• `/menu tombol-role menu:{menu['id']} role:@Gamer`\n"
            f"• `/menu tombol-link menu:{menu['id']} label:Support url:https://...`\n"
            f"• `/menu tombol-command menu:{menu['id']} aksi:serverstats`\n"
            f"• `/menu dropdown-role menu:{menu['id']} role1:@A role2:@B`\n\n"
            f"-# ID panel: `{menu['id']}` • hasil command bisa diatur *Hanya yang klik* atau *publik*.",
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="kirim", description="Kirim ulang panel ke channel (Admin)")
@app_commands.describe(menu="ID panel atau judulnya", channel="Channel tujuan (bawaan: channel sekarang)")
async def menu_kirim_cmd(
    interaction: discord.Interaction,
    menu: str,
    channel: discord.TextChannel | discord.Thread | discord.ForumChannel | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Lihat daftar lewat `/menu daftar`."),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    target = channel or interaction.channel
    message = await menu_builder.send_panel(interaction.client, record, target)
    if message is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Gagal mengirim panel", "Cek izin bot di channel itu."),
            follow=True,
            ephemeral=True,
        )
        return

    await menu_builder.save_menus_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Panel dikirim",
            f"**{record['title']}** sekarang tampil di {getattr(target, 'mention', 'channel')}.",
        ),
        follow=True,
        ephemeral=True,
    )


# ==============================================================================
# EKSPOR / IMPOR / UBAH PANEL
# ==============================================================================
@menu_group.command(name="ekspor", description="Unduh panel sebagai berkas JSON (backup / pindah server)")
@app_commands.describe(menu="ID panel atau judulnya")
async def menu_ekspor_cmd(interaction: discord.Interaction, menu: str):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Lihat daftar lewat `/menu daftar`."),
            ephemeral=True,
        )
        return

    data = menu_builder.export_menu(record)
    isi = json.dumps(data, ensure_ascii=False, indent=2)
    berkas = discord.File(
        io.BytesIO(isi.encode("utf-8")),
        filename=f"panel-{record['id']}.json",
    )
    jumlah = len(data["buttons"]) + sum(len(d.get("options", [])) for d in data["dropdowns"])
    await interaction.response.send_message(
        content=(
            f"📦 **{record['title']}** diekspor ({jumlah} item).\n"
            "-# Simpan berkasnya; pulihkan dengan `/menu impor`. ID role di dalamnya milik "
            "server ini — di server lain role harus dibuat ulang."
        ),
        file=berkas,
        ephemeral=True,
    )


@menu_group.command(name="impor", description="Buat panel dari berkas JSON hasil /menu ekspor (Admin)")
@app_commands.describe(
    berkas="Berkas .json hasil `/menu ekspor`",
    judul="Judul baru (opsional — bawaan: judul di berkas)",
)
async def menu_impor_cmd(
    interaction: discord.Interaction,
    berkas: discord.Attachment,
    judul: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    ukuran = int(getattr(berkas, "size", 0) or 0)
    if ukuran > menu_builder.MAX_IMPORT_BYTES:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Berkas terlalu besar",
                f"Maksimal **{menu_builder.MAX_IMPORT_BYTES // 1024} KB**.",
            ),
            ephemeral=True,
        )
        return

    try:
        mentah = await berkas.read()
        payload = json.loads(mentah.decode("utf-8"))
    except Exception:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Berkas tidak terbaca", "Pastikan berkas JSON hasil `/menu ekspor`."),
            ephemeral=True,
        )
        return

    record, galat = menu_builder.import_menu(gid, payload, title=judul)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "error", "Impor gagal", "\n".join(galat)[:1500] or "Berkas tidak berisi panel.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    catatan = ("\n-# ⚠️ " + "\n-# ⚠️ ".join(galat)) if galat else ""
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Panel diimpor",
            f"**{record['title']}** (`{record['id']}`) siap — "
            f"{len(record['buttons'])} tombol, {len(record['dropdowns'])} dropdown.\n"
            f"Kirim ke channel dengan `/menu kirim menu:{record['id']}`.{catatan}",
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="ubah", description="Ubah judul/deskripsi panel yang sudah terkirim (Admin)")
@app_commands.describe(
    menu="ID panel atau judulnya",
    judul="Judul baru",
    deskripsi="Deskripsi baru (boleh variabel, mis. `{server.members}`)",
)
async def menu_ubah_cmd(
    interaction: discord.Interaction,
    menu: str,
    judul: str | None = None,
    deskripsi: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Lihat daftar lewat `/menu daftar`."),
            ephemeral=True,
        )
        return
    if judul is None and deskripsi is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Tidak ada perubahan", "Isi `judul` dan/atau `deskripsi`."),
            ephemeral=True,
        )
        return

    galat = menu_builder.update_menu_text(record, title=judul, description=deskripsi)
    if galat:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Perubahan ditolak", "\n".join(galat)),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Panel diperbarui",
            f"**{record['title']}**\n"
            + ("Pesan panel yang sudah terkirim ikut berubah (tanpa kirim ulang)." if refreshed
               else "Gunakan `/menu kirim` untuk menampilkan versi barunya."),
        ),
        follow=True,
        ephemeral=True,
    )


# ==============================================================================
# MENAMBAH ITEM
# ==============================================================================
@menu_group.command(
    name="alur-bantuan",
    description="Panduan menulis alur aksi tombol (`+role:… > pesan:…`)",
)
async def menu_alur_bantuan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    embed = ui_theme.status_embed(
        gid,
        "info",
        "Alur Aksi Tombol",
        "Satu tombol bisa menjalankan beberapa aksi berurutan. Langkah dipisah `>`\n"
        "Contoh: `/menu alur menu:1 label:Buka Tiket aksi:+role:123 > pesan:Halo {member.mention}!`",
    )
    embed.add_field(name="Langkah yang tersedia", value="\n".join(flows.HELP_LINES)[:1024], inline=False)
    embed.add_field(
        name="Variabel",
        value="Semua teks bisa memakai `{member.mention}`, `{member.display_name}`, "
        "`{server.name}`, `{channel.mention}`, `{now_relative}`.",
        inline=False,
    )
    embed.add_field(
        name="Batasan",
        value=f"• Maksimal **{flows.MAX_STEPS} langkah** per tombol\n"
        f"• `tunggu` maksimal **{int(flows.MAX_WAIT_SECONDS)} detik**\n"
        "• Role harus di bawah role bot & bot punya izin *Manage Roles*",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@menu_group.command(name="alur", description="Tambah tombol yang menjalankan alur aksi (Admin)")
@app_commands.describe(
    aksi="Alur, mis. `+role:123 > pesan:Halo {member.mention} > thread:tiket`",
    menu="ID panel atau judulnya",
    label="Teks tombol",
    emoji="Emoji tombol (opsional)",
    gaya="Warna tombol",
)
@app_commands.choices(gaya=_GAYA_CHOICES)
async def menu_alur_cmd(
    interaction: discord.Interaction,
    aksi: str,
    menu: str | None = None,
    label: str | None = None,
    emoji: str | None = None,
    gaya: app_commands.Choice[str] | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Buat dulu lewat `/menu buat`."),
            ephemeral=True,
        )
        return

    langkah, galat = flows.parse(aksi)
    if galat:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "error", "Alur belum valid", "\n".join(f"• {g}" for g in galat)[:1500]
            ),
            ephemeral=True,
        )
        return

    # Role pada alur harus bisa diberikan bot
    for step in langkah:
        if step.get("action") in (
            flows.ACTION_ROLE_TOGGLE,
            flows.ACTION_ROLE_ADD,
            flows.ACTION_ROLE_REMOVE,
            flows.ACTION_REQUIRE_ROLE,
        ):
            role = interaction.guild.get_role(int(step["role_id"]))
            if role is None:
                await ui_kit.send_status(
                    interaction,
                    embed=ui_theme.status_embed(
                        gid, "warn", "Role tidak ditemukan",
                        f"`{step['role_id']}` bukan role di server ini.",
                    ),
                    ephemeral=True,
                )
                return
            if step["action"] == flows.ACTION_REQUIRE_ROLE:
                continue
            ok, reason = menu_builder.check_role_usable(interaction.guild, role.id)
            if not ok:
                await ui_kit.send_status(
                    interaction,
                    embed=ui_theme.status_embed(gid, "error", "Role tidak bisa dipakai", reason),
                    ephemeral=True,
                )
                return

    nama_tombol = (label or "").strip() or "Aksi"
    item = menu_builder.add_flow_button(
        record,
        nama_tombol,
        langkah,
        emoji=emoji,
        style=gaya.value if gaya else "biru",
    )
    if item is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Tombol tidak ditambahkan",
                f"Batas **{menu_builder.MAX_BUTTONS} tombol** per panel.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    ringkas = "\n".join(flows.describe(langkah))[:1000]
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Tombol alur ditambahkan",
            f"**{item['label']}**\n{ringkas}\n"
            + ("Panel langsung diperbarui." if refreshed else "Gunakan `/menu kirim` untuk menampilkan panel."),
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="tombol-role", description="Tambah tombol role (klik = ambil/lepas role) (Admin)")
@app_commands.describe(
    menu="ID panel atau judulnya",
    role="Role yang diberikan",
    label="Teks pada tombol (bawaan: nama role)",
    emoji="Emoji tombol (opsional)",
    gaya="Warna tombol",
)
@app_commands.choices(gaya=_GAYA_CHOICES)
async def menu_tombol_role_cmd(
    interaction: discord.Interaction,
    role: discord.Role,
    menu: str | None = None,
    label: str | None = None,
    emoji: str | None = None,
    gaya: app_commands.Choice[str] | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Panel tidak ditemukan",
                "Sebutkan `menu:` dengan ID/judul panel, atau buat dulu lewat `/menu buat`.",
            ),
            ephemeral=True,
        )
        return

    ok, reason = menu_builder.check_role_usable(interaction.guild, role.id)
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Role tidak bisa dipakai", reason),
            ephemeral=True,
        )
        return

    item = menu_builder.add_role_button(
        record,
        role.id,
        label or role.name,
        emoji=emoji,
        style=gaya.value if gaya else "abu",
    )
    if item is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Tombol tidak ditambahkan",
                f"Batas **{menu_builder.MAX_BUTTONS} tombol** per panel, atau role itu sudah ada di panel ini.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Tombol role ditambahkan",
            f"**{item['label']}** → {role.mention}\n"
            + ("Panel langsung diperbarui." if refreshed else "Gunakan `/menu kirim` untuk menampilkan panel."),
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="tombol-link", description="Tambah tombol tautan (mis. Support Server / Undang Bot) (Admin)")
@app_commands.describe(menu="ID panel atau judulnya", label="Teks tombol", url="Alamat lengkap (https://…)")
async def menu_tombol_link_cmd(
    interaction: discord.Interaction,
    label: str,
    url: str,
    menu: str | None = None,
    emoji: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Buat dulu lewat `/menu buat`."),
            ephemeral=True,
        )
        return

    item = menu_builder.add_link_button(record, label, url, emoji=emoji)
    if item is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Tautan tidak valid",
                f"URL harus diawali `http://` atau `https://`, dan panel maksimal **{menu_builder.MAX_BUTTONS} tombol**.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Tombol tautan ditambahkan",
            f"**{item['label']}** → {item['url']}\n"
            + ("Panel langsung diperbarui." if refreshed else "Gunakan `/menu kirim` untuk menampilkan panel."),
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="tombol-command", description="Tambah tombol yang menjalankan command info (Admin)")
@app_commands.describe(
    aksi="Command yang dijalankan saat tombol diklik",
    menu="ID panel atau judulnya",
    label="Teks tombol (bawaan: nama aksi)",
    emoji="Emoji tombol (opsional)",
    visibilitas="Hasil command hanya untuk pengklik, atau publik",
    gaya="Warna tombol",
)
@app_commands.choices(aksi=_AKSI_CHOICES, visibilitas=_VIS_CHOICES, gaya=_GAYA_CHOICES)
async def menu_tombol_command_cmd(
    interaction: discord.Interaction,
    aksi: app_commands.Choice[str],
    menu: str | None = None,
    label: str | None = None,
    emoji: str | None = None,
    visibilitas: app_commands.Choice[str] | None = None,
    gaya: app_commands.Choice[str] | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Buat dulu lewat `/menu buat`."),
            ephemeral=True,
        )
        return

    spec = menu_builder.SAFE_COMMANDS.get(aksi.value) or {}
    item = menu_builder.add_command_button(
        record,
        aksi.value,
        label=label or spec.get("label"),
        emoji=emoji or spec.get("emoji"),
        style=gaya.value if gaya else "biru",
        visibility=visibilitas.value if visibilitas else menu_builder.VIS_AUTO,
    )
    if item is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Tombol tidak ditambahkan",
                f"Aksi tidak diizinkan atau panel sudah mencapai **{menu_builder.MAX_BUTTONS} tombol**.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    vis_label = {
        menu_builder.VIS_AUTO: "ikut command",
        menu_builder.VIS_EPHEMERAL: "hanya yang klik",
        menu_builder.VIS_PUBLIK: "publik",
    }.get(item["visibility"], item["visibility"])
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Tombol command ditambahkan",
            f"**{item['label']}** menjalankan `{spec.get('desc', aksi.value)}` "
            f"(tampilan: **{vis_label}**).\n"
            + ("Panel langsung diperbarui." if refreshed else "Gunakan `/menu kirim` untuk menampilkan panel."),
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="dropdown-role", description="Tambah dropdown role (maks 25 role, bisa eksklusif) (Admin)")
@app_commands.describe(
    menu="ID panel atau judulnya",
    placeholder="Teks ajakan, misal: Pilih role minat kamu…",
    eksklusif="True = hanya boleh satu role dari dropdown ini (cocok untuk role usia)",
    role1="Role pertama", emoji1="Emoji role pertama (opsional)",
    role2="Role kedua (opsional)", emoji2="Emoji role kedua (opsional)",
    role3="Role ketiga (opsional)", emoji3="Emoji role ketiga (opsional)",
    role4="Role keempat (opsional)", emoji4="Emoji role keempat (opsional)",
    role5="Role kelima (opsional)", emoji5="Emoji role kelima (opsional)",
)
async def menu_dropdown_role_cmd(
    interaction: discord.Interaction,
    role1: discord.Role,
    menu: str | None = None,
    placeholder: str | None = None,
    eksklusif: bool = False,
    emoji1: str | None = None,
    role2: discord.Role | None = None,
    emoji2: str | None = None,
    role3: discord.Role | None = None,
    emoji3: str | None = None,
    role4: discord.Role | None = None,
    emoji4: str | None = None,
    role5: discord.Role | None = None,
    emoji5: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Buat dulu lewat `/menu buat`."),
            ephemeral=True,
        )
        return

    pairs = [(role1, emoji1), (role2, emoji2), (role3, emoji3), (role4, emoji4), (role5, emoji5)]
    options: list[dict] = []
    rejected: list[str] = []
    for role, emoji in pairs:
        if role is None:
            continue
        ok, _reason = menu_builder.check_role_usable(interaction.guild, role.id)
        if not ok:
            rejected.append(role.name)
            continue
        options.append({"role_id": role.id, "label": role.name, "emoji": emoji})

    if not options:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "error", "Tidak ada role valid",
                ("Ditolak: " + ", ".join(rejected)) if rejected else "Pilih minimal satu role.",
            ),
            ephemeral=True,
        )
        return

    dropdown = menu_builder.add_dropdown(
        record,
        placeholder or "Pilih role…",
        options,
        exclusive=bool(eksklusif),
    )
    if dropdown is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Dropdown tidak ditambahkan",
                f"Batas **{menu_builder.MAX_DROPDOWNS} dropdown** per panel.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    extra = f"\n⚠️ Dilewati (tidak bisa diberikan): {', '.join(rejected)}" if rejected else ""
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Dropdown role ditambahkan",
            f"**{len(dropdown['options'])} role** masuk ke dropdown "
            f"({'eksklusif — pilih satu' if dropdown['exclusive'] else 'bisa pilih bergantian'}).{extra}\n"
            + ("Panel langsung diperbarui." if refreshed else "Gunakan `/menu kirim` untuk menampilkan panel."),
        ),
        follow=True,
        ephemeral=True,
    )


# ==============================================================================
# KELOLA
# ==============================================================================
@menu_group.command(name="hapus-item", description="Hapus tombol/opsi dari panel (Admin)")
@app_commands.describe(menu="ID panel atau judulnya", item="Nomor urut, ID item, atau label tombol")
async def menu_hapus_item_cmd(interaction: discord.Interaction, item: str, menu: str | None = None):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Lihat `/menu daftar`."),
            ephemeral=True,
        )
        return

    removed = menu_builder.remove_item(record, item)
    if removed is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "warn", "Item tidak ditemukan",
                "Lihat nomor & label item lewat `/menu daftar`.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    await menu_builder.save_menus_to_disk()
    refreshed = await menu_builder.refresh_panel(interaction.client, record)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Item dihapus",
            f"**{removed}** sudah dihapus dari panel."
            + ("\nPanel langsung diperbarui." if refreshed else ""),
        ),
        follow=True,
        ephemeral=True,
    )


@menu_group.command(name="daftar", description="Lihat semua panel menu di server ini beserta isinya")
async def menu_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    rows = menu_builder.list_menus(gid)
    if not rows:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "info", "Belum ada panel",
                "Buat panel pertama dengan `/menu buat judul:Pusat Info`.",
            ),
            ephemeral=True,
        )
        return

    lines: list[str] = []
    for record in rows:
        lines.append(f"**{record['title']}** (`{record['id']}`)")
        index = 0
        for btn in record["buttons"]:
            index += 1
            detail = {
                menu_builder.KIND_ROLE: f"role <@&{btn.get('role_id')}>",
                menu_builder.KIND_LINK: btn.get("url"),
                menu_builder.KIND_COMMAND: menu_builder.SAFE_COMMANDS.get(
                    str(btn.get("command")), {}
                ).get("desc", btn.get("command")),
            }.get(btn.get("kind"), "")
            if btn.get("kind") == menu_builder.KIND_FLOW:
                detail = f"alur {len(btn.get('flow') or [])} langkah"
            lines.append(f"`{index}.` {btn.get('emoji') or '🔹'} {btn.get('label')} — {detail}")
        for dropdown in record["dropdowns"]:
            options = ", ".join(str(opt.get("label")) for opt in dropdown["options"])
            lines.append(
                f"-# dropdown: {dropdown.get('placeholder')} "
                f"({len(dropdown['options'])} opsi{', eksklusif' if dropdown.get('exclusive') else ''}) → {options}"
            )
        lines.append("")

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            f"🗂️ Panel Menu ({len(rows)})",
            "\n".join(lines)[:3800],
            footer="Klik tombol role = ambil/lepas role • tombol command = jalankan command info",
        ),
        ephemeral=True,
    )


@menu_group.command(name="hapus", description="Hapus panel dari daftar bot (pesan lama tidak dihapus) (Admin)")
@app_commands.describe(menu="ID panel atau judulnya")
async def menu_hapus_cmd(interaction: discord.Interaction, menu: str):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    record = _menu_or_error(interaction, gid, menu)
    if record is None or not menu_builder.delete_menu(gid, record["id"]):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Panel tidak ditemukan", "Lihat `/menu daftar`."),
            ephemeral=True,
        )
        return

    await menu_builder.save_menus_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok", "Panel dihapus dari bot",
            f"**{record['title']}** tidak lagi aktif. Pesan panel lama boleh kamu hapus manual di channel.",
        ),
        ephemeral=True,
    )


def register_menu_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/menu` ke bot."""
    bot.tree.add_command(menu_group)
