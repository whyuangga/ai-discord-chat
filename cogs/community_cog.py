import logging
import re
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import menu_builder
import ui_kit
import ui_theme
from cogs.helpers import get_memory_usage_mb
from community_tools import (
    add_reaction_role_option,
    add_reminder,
    build_backup_archive,
    build_sticky_embed,
    build_verification_embed,
    cancel_reminder,
    create_reaction_role_panel,
    delete_reaction_role_panel,
    format_duration_short,
    get_guild_reaction_panels,
    list_user_reminders,
    maintenance_guilds,
    parse_reminder_duration,
    reaction_role_panels,
    remove_reaction_role_option,
    remove_sticky_config,
    save_community_tools_to_disk,
    send_backup,
    set_maintenance_config,
    set_starboard_config,
    set_sticky_config,
    set_verification_config,
    starboard_guilds,
    sticky_channels,
    verification_guilds,
)
from server_features import autorole_guilds
from config import (
    BACKUP_INTERVAL_DAYS,
    BOT_VERSION,
    REMINDER_MAX_PER_USER,
    STARBOARD_DEFAULT_THRESHOLD,
    STARBOARD_EMOJI,
    STICKY_MIN_INTERVAL_SEC,
)

logger = logging.getLogger("gemini_bot.community_cog")

POLL = getattr(discord, "Poll", None)


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.",
        ephemeral=True,
    )


def _resolve_text_target(interaction: discord.Interaction, channel):
    """Menentukan channel tujuan teks: parameter eksplisit, atau channel tempat command dipanggil."""
    if channel is not None:
        return channel
    current = interaction.channel
    if current is None or isinstance(
        current, (discord.Thread, discord.DMChannel, discord.ForumChannel)
    ):
        return None
    return current if hasattr(current, "send") else None


def _parse_message_id(raw: str | None) -> int | None:
    """Membaca ID pesan dari angka biasa maupun tautan Discord."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    found = re.findall(r"(\d{15,25})", text)
    return int(found[-1]) if found else None


# ==============================================================================
# /poll — Polling Native Discord (Hitung Suara Otomatis)
# ==============================================================================
@app_commands.command(
    name="poll",
    description="Buat polling cepat dengan hitung suara otomatis (tanpa kuota AI)",
)
@app_commands.describe(
    pertanyaan="Pertanyaan polling, misal: Mabar malam ini jam berapa?",
    opsi="Pilihan dipisah koma, misal: Jam 8, Jam 9, Jam 10",
    durasi_jam="Berapa jam polling berlangsung (1–768, default 24)",
    multi="True bila member boleh memilih lebih dari satu opsi",
    anonim="True untuk menyembunyikan siapa yang memilih",
)
async def slash_poll(
    interaction: discord.Interaction,
    pertanyaan: str,
    opsi: str,
    durasi_jam: int = 24,
    multi: bool = False,
    anonim: bool = True,
):
    if POLL is None:
        await interaction.response.send_message(
            "⚠️ Fitur polling membutuhkan **discord.py 2.4+**. Perbarui dependensi bot.",
            ephemeral=True,
        )
        return

    answers = [item.strip() for item in re.split(r"[,;|/]", opsi) if item.strip()]
    if len(answers) < 2:
        await interaction.response.send_message(
            "⚠️ Minimal **2 pilihan**. Contoh: `/poll pertanyaan:Makan apa? opsi:Nasi, Mie, Ayam`",
            ephemeral=True,
        )
        return

    trimmed = answers[:10]
    hours = max(1, min(768, int(durasi_jam)))
    poll = POLL(question=pertanyaan[:300], duration=timedelta(hours=hours), multiple=bool(multi))
    for answer in trimmed:
        poll.add_answer(text=answer[:55])

    await interaction.response.send_message(poll=poll)
    if len(answers) > 10:
        await interaction.followup.send(
            f"ℹ️ Hanya **10 pilihan pertama** yang dipakai (batas Discord). {len(answers) - 10} pilihan lain dilewati.",
            ephemeral=True,
        )


# ==============================================================================
# /panel-role — Reaction Role
# ==============================================================================
panelrole_group = app_commands.Group(
    name="panel-role",
    description="Panel Reaction Role: member klik emoji untuk mengambil role sendiri",
    guild_only=True,
)



_SELF_ROLE_GAYA = [
    app_commands.Choice(name="Emoji reaction (bawaan lama)", value="reaksi"),
    app_commands.Choice(name="Tombol (klik = ambil/lepas role)", value="tombol"),
    app_commands.Choice(name="Dropdown (maks 25 role)", value="dropdown"),
    app_commands.Choice(name="Campuran (banner + tombol + dropdown)", value="campuran"),
]


async def _panelrole_v2(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    judul: str,
    deskripsi: str | None,
    pairs: list[tuple[discord.Role, str]],
    gaya: str,
    banner: discord.Attachment | None,
    banner_url: str | None,
) -> None:
    """Self Roles v2: panel tombol/dropdown memakai mesin `menu_builder` (0 kuota AI)."""
    guild = interaction.guild
    if guild is None:
        return

    usable: list[tuple[discord.Role, str]] = []
    rejected: list[str] = []
    for role, emoji in pairs:
        ok, reason = menu_builder.check_role_usable(guild, role.id)
        if ok:
            usable.append((role, emoji))
        else:
            rejected.append(f"{role.mention} ({reason})")
    if not usable:
        await interaction.response.send_message(
            "⚠️ Tidak ada role yang bisa diberikan bot:\n" + "\n".join(rejected[:5]),
            ephemeral=True,
        )
        return

    menu = menu_builder.create_menu(
        guild.id,
        judul,
        description=deskripsi or "Klik tombol atau pilih dari menu di bawah untuk mengambil / melepas role.",
        kind=menu_builder.MENU_KIND_ROLES,
        banner_url=str(banner_url) if banner_url else None,
        channel_id=channel.id,
    )
    if menu is None:
        await interaction.response.send_message(
            f"⚠️ Batas panel per server **{menu_builder.MAX_MENUS_PER_GUILD}** sudah tercapai. "
            "Hapus panel lama lewat `/menu hapus`.",
            ephemeral=True,
        )
        return

    if gaya in ("tombol", "campuran"):
        for role, emoji in usable:
            menu_builder.add_role_button(menu, role.id, role.name, emoji=emoji or None)
    if gaya in ("dropdown", "campuran"):
        menu_builder.add_dropdown(
            menu,
            "Pilih role kamu di sini…",
            [
                {"role_id": role.id, "label": role.name, "emoji": emoji or None}
                for role, emoji in usable
            ],
            exclusive=False,
            group=f"panel-{menu['id']}",
        )

    await interaction.response.defer(ephemeral=True, thinking=True)

    file = None
    ref = None
    if banner is not None and menu_builder.is_image_attachment(banner):
        try:
            data = await banner.read()
            file, ref = menu_builder.banner_file_from_attachment(banner, data)
        except (discord.HTTPException, AttributeError):
            file = None
    elif banner is not None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                guild.id, "warn", "Banner diabaikan", "Banner harus gambar PNG/JPG/WebP maksimal 8 MB."
            ),
            follow=True,
            ephemeral=True,
        )

    message = await menu_builder.send_panel(
        interaction.client, menu, channel, banner_file=file, banner_ref=ref
    )
    if message is None:
        menu_builder.delete_menu(guild.id, menu["id"])
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                guild.id, "error", "Gagal mengirim panel",
                f"Cek izin **Send Messages** & **Embed Links** di {channel.mention}.",
            ),
            follow=True,
            ephemeral=True,
        )
        return

    await menu_builder.save_menus_to_disk()
    note = f"\n⚠️ Dilewati: {'; '.join(rejected[:3])}" if rejected else ""
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            guild.id,
            "ok",
            "Panel Self Roles terpasang",
            f"Gaya **{gaya}** dengan **{len(usable)} role** di {channel.mention}.{note}\n"
            "Member kini bisa mengambil role dengan klik tombol atau memilih dari dropdown "
            "(klik lagi = role dilepas).\n"
            f"-# Panel ID `{menu['id']}` • tambah role: `/menu tombol-role menu:{menu['id']} role:@Role`",
        ),
        follow=True,
        ephemeral=True,
    )
    try:
        import audit_log

        await audit_log.log_event(
            interaction.client,
            guild,
            "role",
            "Panel self role dipasang",
            f"{len(usable)} role • gaya {gaya} • channel {channel.mention}",
        )
    except Exception:  # pragma: no cover - audit opsional
        pass


@panelrole_group.command(
    name="pasang",
    description="Pasang panel role (emoji reaction, tombol, dropdown, atau campuran + banner)",
)
@app_commands.describe(
    channel="Channel tempat panel role dipasang",
    judul="Judul panel, misal: Ambil Role Minat Kamu",
    deskripsi="Penjelasan singkat cara memakai panel (opsional)",
    role1="Role pertama yang bisa diambil member",
    emoji1="Emoji pemicu untuk role pertama, misal: 🎨",
    role2="Role kedua (opsional)",
    emoji2="Emoji pemicu untuk role kedua (opsional)",
    role3="Role ketiga (opsional)",
    emoji3="Emoji pemicu untuk role ketiga (opsional)",
    gaya="Bentuk panel: reaksi (lama), tombol, dropdown, atau campuran",
    banner="Unggah gambar banner .png/.jpg (opsional, untuk gaya selain reaksi)",
    banner_url="Atau tempel URL gambar banner (opsional)",
)
@app_commands.choices(gaya=_SELF_ROLE_GAYA)
async def panelrole_pasang_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    judul: str,
    role1: discord.Role,
    emoji1: str,
    deskripsi: str | None = None,
    role2: discord.Role | None = None,
    emoji2: str | None = None,
    role3: discord.Role | None = None,
    emoji3: str | None = None,
    gaya: app_commands.Choice[str] | None = None,
    banner: discord.Attachment | None = None,
    banner_url: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    pairs: list[tuple[discord.Role, str]] = [(role1, emoji1)]
    if role2 is not None and emoji2:
        pairs.append((role2, emoji2))
    if role3 is not None and emoji3:
        pairs.append((role3, emoji3))

    # Self Roles v2 (tombol/dropdown/campuran + banner) memakai mesin menu_builder
    if gaya is not None and gaya.value != "reaksi":
        await _panelrole_v2(interaction, channel, judul, deskripsi, pairs, gaya.value, banner, banner_url)
        return

    bot_member = interaction.guild.me
    ignored = [r.mention for r, _ in pairs if bot_member and r >= bot_member.top_role]
    usable = [(r, e) for r, e in pairs if not (bot_member and r >= bot_member.top_role)]
    if not usable:
        await interaction.response.send_message(
            "⚠️ Semua role berada **di atas role bot**, jadi tidak bisa diberikan. "
            "Pindahkan role bot ke atas role tersebut.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title=judul[:256],
        description=(
            (deskripsi or "Klik reaksi emoji di bawah pesan ini untuk mengambil atau melepas role.")
            + "\n\n"
            + "\n".join(f"{emoji} → {role.mention}" for role, emoji in usable)
        )[:4000],
        color=discord.Color.blurple(),
    ).set_footer(text="Reaction Role • klik emoji sekali lagi untuk melepas role")

    try:
        message = await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim panel ke {channel.mention}. Cek izin **Send Messages** bot.",
            ephemeral=True,
        )
        return

    create_reaction_role_panel(
        interaction.guild.id,
        channel.id,
        message.id,
        title=judul,
        description=deskripsi or "",
    )
    failed_emoji: list[str] = []
    for role, emoji in usable:
        add_reaction_role_option(message.id, emoji, role.id, role.name)
        try:
            await message.add_reaction(emoji)
        except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument):
            failed_emoji.append(emoji)
    await save_community_tools_to_disk()

    note = ""
    if ignored:
        note += f"\n⚠️ Dilewati (role di atas bot): {', '.join(ignored)}"
    if failed_emoji:
        note += f"\n⚠️ Emoji gagal dipasang: {', '.join(failed_emoji)}"
    await interaction.followup.send(
        f"✅ Panel role terpasang di {channel.mention} dengan **{len(usable)} role**.{note}\n"
        f"Tambah role lain dengan `/panel-role tambah pesan:{message.id} emoji:🎮 role:@Role`.",
        ephemeral=True,
    )


@panelrole_group.command(name="tambah", description="Tambah satu pasangan emoji ➔ role pada panel yang sudah ada")
@app_commands.describe(
    pesan="ID pesan panel atau tempel tautan pesannya",
    emoji="Emoji pemicu, misal: 🎮",
    role="Role yang diberikan saat emoji diklik",
)
async def panelrole_tambah_cmd(
    interaction: discord.Interaction,
    pesan: str,
    emoji: str,
    role: discord.Role,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    message_id = _parse_message_id(pesan)
    panel = reaction_role_panels.get(message_id or 0)
    if message_id is None or panel is None or panel.get("guild_id") != interaction.guild.id:
        await interaction.response.send_message(
            "⚠️ Panel tidak ditemukan. Gunakan ID pesan panel yang dibuat lewat `/panel-role pasang`.",
            ephemeral=True,
        )
        return

    if interaction.guild.me and role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            "⚠️ Role tersebut berada **di atas role bot** sehingga tidak bisa diberikan.",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(int(panel["channel_id"]))
    if channel is None:
        await interaction.response.send_message("⚠️ Channel panel sudah tidak ada.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        message = await channel.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        await interaction.followup.send("⚠️ Pesan panel tidak ditemukan di channel.", ephemeral=True)
        return

    if add_reaction_role_option(message_id, emoji, role.id, role.name) is None:
        await interaction.followup.send(
            "⚠️ Emoji atau role tersebut sudah ada di panel ini.", ephemeral=True
        )
        return

    try:
        await message.add_reaction(emoji)
    except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument):
        await interaction.followup.send(
            f"⚠️ Emoji `{emoji}` tidak valid atau bot tidak bisa memasangnya.", ephemeral=True
        )
        return

    await save_community_tools_to_disk()
    await interaction.followup.send(
        f"✅ {emoji} → {role.mention} ditambahkan ke panel.", ephemeral=True
    )


@panelrole_group.command(name="hapus", description="Hapus satu pasangan emoji ➔ role dari panel")
@app_commands.describe(pesan="ID pesan panel atau tautannya", emoji="Emoji yang ingin dihapus dari panel")
async def panelrole_hapus_cmd(interaction: discord.Interaction, pesan: str, emoji: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    message_id = _parse_message_id(pesan)
    panel = reaction_role_panels.get(message_id or 0)
    if message_id is None or panel is None or panel.get("guild_id") != interaction.guild.id:
        await interaction.response.send_message("⚠️ Panel tidak ditemukan.", ephemeral=True)
        return

    if remove_reaction_role_option(message_id, emoji) is None:
        await interaction.response.send_message(
            f"⚠️ Emoji `{emoji}` tidak ada pada panel ini.", ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(panel["channel_id"]))
    if channel is not None:
        try:
            message = await channel.fetch_message(message_id)
            await message.remove_reaction(emoji, interaction.guild.me)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    if not panel["options"]:
        delete_reaction_role_panel(message_id)
    await save_community_tools_to_disk()
    await interaction.response.send_message(
        f"✅ Emoji `{emoji}` dihapus dari panel.", ephemeral=True
    )


@panelrole_group.command(name="daftar", description="Lihat seluruh panel reaction role di server ini")
async def panelrole_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    panels = get_guild_reaction_panels(interaction.guild.id)
    if not panels:
        await interaction.response.send_message(
            "ℹ️ Belum ada panel reaction role. Buat dengan "
            "`/panel-role pasang channel:#ambil-role judul:Ambil Role role1:@Member emoji1:✅`.",
            ephemeral=True,
        )
        return

    lines = []
    for message_id, panel in panels[:10]:
        options = ", ".join(f"{opt['emoji']} <@&{opt['role_id']}>" for opt in panel["options"])
        lines.append(
            f"• **{panel['title']}** di <#{panel['channel_id']}> — {options or '_belum ada role_'}"
        )
    await interaction.response.send_message(
        "🎭 **Panel Reaction Role Server Ini**\n" + "\n".join(lines), ephemeral=True
    )


# ==============================================================================
# /ingatkan — Pengingat Pribadi
# ==============================================================================
ingatkan_group = app_commands.Group(
    name="ingatkan",
    description="Pengingat pribadi: bot mengingatkan kamu saat waktunya tiba",
    guild_only=True,
)


@ingatkan_group.command(name="pasang", description="Pasang pengingat baru, misal 2 jam lagi")
@app_commands.describe(
    waktu="Kapan diingatkan: 10m, 2j, 1j30m, 2 hari, atau 45 (menit)",
    pesan="Apa yang ingin diingatkan",
    channel="Channel tempat pengingat dikirim (default: channel ini)",
)
async def ingatkan_pasang_cmd(
    interaction: discord.Interaction,
    waktu: str,
    pesan: str,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return

    seconds = parse_reminder_duration(waktu)
    if seconds is None:
        await interaction.response.send_message(
            "⚠️ Format waktu belum dikenali.\n"
            "**Contoh:** `10m` (10 menit), `2j` (2 jam), `1j30m`, `2 hari`, atau `45` (menit).\n"
            "Batas maksimal **365 hari**.",
            ephemeral=True,
        )
        return

    target = _resolve_text_target(interaction, channel)
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel` tujuan pengingat (bukan thread/DM).", ephemeral=True
        )
        return

    reminder = add_reminder(
        interaction.guild.id, target.id, interaction.user.id, pesan, seconds
    )
    if reminder is None:
        await interaction.response.send_message(
            f"⚠️ Kamu sudah punya **{REMINDER_MAX_PER_USER} pengingat aktif** (batas maksimal). "
            "Batalkan salah satunya dengan `/ingatkan batal`.",
            ephemeral=True,
        )
        return

    await save_community_tools_to_disk()
    due_text = discord.utils.format_dt(
        discord.utils.utcnow() + timedelta(seconds=seconds), style="f"
    )
    await interaction.response.send_message(
        f"⏰ **Pengingat dipasang!**\n"
        f"• **Nomor:** `{reminder['id']}`\n"
        f"• **Waktu:** {due_text} ({format_duration_short(seconds)} lagi)\n"
        f"• **Pesan:** {pesan[:400]}\n"
        f"• **Tujuan:** {target.mention}",
        ephemeral=True,
    )


@ingatkan_group.command(name="daftar", description="Lihat daftar pengingat aktif milikmu")
async def ingatkan_daftar_cmd(interaction: discord.Interaction):
    items = list_user_reminders(interaction.user.id)
    if not items:
        await interaction.response.send_message(
            "ℹ️ Belum ada pengingat aktif. Buat dengan `/ingatkan pasang waktu:2j pesan:mabar`.",
            ephemeral=True,
        )
        return

    now = time.time()
    lines = [
        f"• `{item['id']}` — {item['text'][:60]} "
        f"*(dalam {format_duration_short(max(0, int(item['due_at'] - now)))})*"
        for item in items[:15]
    ]
    await interaction.response.send_message(
        "⏰ **Pengingat Aktif Kamu**\n" + "\n".join(lines), ephemeral=True
    )


@ingatkan_group.command(name="batal", description="Batalkan salah satu pengingat milikmu")
@app_commands.describe(nomor="Nomor pengingat yang ingin dibatalkan (lihat /ingatkan daftar)")
async def ingatkan_batal_cmd(interaction: discord.Interaction, nomor: int):
    if cancel_reminder(nomor, interaction.user.id):
        await save_community_tools_to_disk()
        await interaction.response.send_message(
            f"✅ Pengingat `{nomor}` dibatalkan.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "⚠️ Pengingat tidak ditemukan atau bukan milikmu.", ephemeral=True
    )


# ==============================================================================
# /starboard — Sorotan Pesan Populer
# ==============================================================================
starboard_group = app_commands.Group(
    name="starboard",
    description="Starboard: pesan yang banyak dapat bintang otomatis disalin ke channel sorotan",
    guild_only=True,
)


@starboard_group.command(name="atur", description="Atur channel sorotan, batas bintang, & emoji starboard")
@app_commands.describe(
    channel="Channel tujuan sorotan (misal #starboard)",
    batas="Jumlah reaksi minimal agar pesan disorot (default 3)",
    emoji="Emoji yang dipakai sebagai bintang (default ⭐)",
    aktif="False untuk mematikan starboard di server ini",
)
async def starboard_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    batas: int = STARBOARD_DEFAULT_THRESHOLD,
    emoji: str = STARBOARD_EMOJI,
    aktif: bool = True,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not aktif:
        set_starboard_config(interaction.guild.id, enabled=False)
        await save_community_tools_to_disk()
        await interaction.response.send_message(
            "🛑 **Starboard** dinonaktifkan di server ini.", ephemeral=True
        )
        return

    existing = starboard_guilds.get(interaction.guild.id) or {}
    target = channel or (
        interaction.guild.get_channel(int(existing.get("channel_id") or 0))
        if existing.get("channel_id")
        else None
    )
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel` tujuan sorotan terlebih dahulu.", ephemeral=True
        )
        return

    cfg = set_starboard_config(
        interaction.guild.id,
        channel_id=target.id,
        threshold=batas,
        emoji=emoji,
        enabled=True,
    )
    await save_community_tools_to_disk()
    await interaction.response.send_message(
        f"⭐ **Starboard aktif di {target.mention}!**\n"
        f"• **Batas bintang:** `{cfg['threshold']}` reaksi\n"
        f"• **Emoji:** {cfg['emoji']}\n"
        f"• Pesan warga yang mencapai batas akan otomatis disalin ke sana.",
        ephemeral=True,
    )


@starboard_group.command(name="status", description="Lihat status & statistik starboard server ini")
async def starboard_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = starboard_guilds.get(interaction.guild.id)
    if not cfg or not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Starboard belum aktif. Pasang dengan `/starboard atur channel:#starboard`.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"⭐ **Status Starboard**\n"
        f"• **Channel sorotan:** <#{cfg['channel_id']}>\n"
        f"• **Batas:** `{cfg['threshold']}` reaksi {cfg['emoji']}\n"
        f"• **Pesan tersorot:** `{len(cfg.get('entries') or {})}`\n"
        f"• Matikan dengan `/starboard atur aktif:False`.",
        ephemeral=True,
    )


# ==============================================================================
# /verifikasi — Gerbang Verifikasi Member
# ==============================================================================
verifikasi_group = app_commands.Group(
    name="verifikasi",
    description="Gerbang verifikasi: member klik tombol sekali untuk mendapat role akses",
    guild_only=True,
)


@verifikasi_group.command(name="pasang", description="Pasang tombol verifikasi & pilih role yang diberikan")
@app_commands.describe(
    channel="Channel tempat tombol verifikasi dipasang",
    role="Role yang otomatis diberikan setelah member verifikasi",
    catatan="Catatan tambahan di panel verifikasi (opsional)",
)
async def verifikasi_pasang_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
    catatan: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if role.is_default():
        await interaction.response.send_message(
            "⚠️ Role `@everyone` tidak bisa dipakai. Pilih role khusus (misal `Member`).",
            ephemeral=True,
        )
        return
    if interaction.guild.me and role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            "⚠️ Role tersebut berada **di atas role bot**. Pindahkan role bot ke atasnya dulu.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    embed = build_verification_embed(interaction.guild.name, role.name, catatan or "")
    try:
        from views import VerificationGateView

        message = await channel.send(embed=embed, view=VerificationGateView())
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim panel ke {channel.mention}. Cek izin **Send Messages** bot.",
            ephemeral=True,
        )
        return

    set_verification_config(
        interaction.guild.id,
        channel_id=channel.id,
        role_id=role.id,
        message_id=message.id,
        enabled=True,
    )
    await save_community_tools_to_disk()
    await interaction.followup.send(
        f"✅ **Gerbang verifikasi aktif** di {channel.mention}.\n"
        f"• Member baru klik tombol **Verifikasi Saya** → otomatis dapat {role.mention}.\n"
        f"• Cocok dipadukan dengan `/autorole` untuk role tambahan.",
        ephemeral=True,
    )


@verifikasi_group.command(name="status", description="Lihat status gerbang verifikasi server ini")
async def verifikasi_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = verification_guilds.get(interaction.guild.id)
    if not cfg or not cfg.get("enabled"):
        await interaction.response.send_message(
            "ℹ️ Gerbang verifikasi belum aktif. Pasang dengan "
            "`/verifikasi pasang channel:#verifikasi role:@Member`.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"✅ **Status Gerbang Verifikasi**\n"
        f"• **Channel:** <#{cfg['channel_id']}>\n"
        f"• **Role diberikan:** <@&{cfg['role_id']}>\n"
        f"• Matikan dengan `/verifikasi matikan`.",
        ephemeral=True,
    )


@verifikasi_group.command(name="matikan", description="Matikan gerbang verifikasi di server ini")
async def verifikasi_matikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    set_verification_config(interaction.guild.id, enabled=False)
    await save_community_tools_to_disk()
    await interaction.response.send_message(
        "🛑 Gerbang verifikasi dinonaktifkan. Tombol lama tidak akan memberi role lagi.",
        ephemeral=True,
    )


# ==============================================================================
# /sticky — Pesan Petunjuk yang Selalu di Bawah
# ==============================================================================
sticky_group = app_commands.Group(
    name="sticky",
    description="Sticky message: pesan petunjuk yang otomatis tetap di bawah channel",
    guild_only=True,
)


@sticky_group.command(name="pasang", description="Pasang pesan sticky di sebuah channel")
@app_commands.describe(
    isi="Isi pesan petunjuk (aturan, link penting, atau cara pakai bot)",
    channel="Channel tujuan (default: channel ini)",
    judul="Judul pesan sticky (opsional)",
)
async def sticky_pasang_cmd(
    interaction: discord.Interaction,
    isi: str,
    channel: discord.TextChannel | None = None,
    judul: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = _resolve_text_target(interaction, channel)
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel` tujuan pesan sticky.", ephemeral=True
        )
        return

    cfg = set_sticky_config(target.id, interaction.guild.id, isi, title=judul or "")
    if cfg is None:
        await interaction.response.send_message("⚠️ Isi pesan tidak boleh kosong.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        posted = await target.send(embed=build_sticky_embed(cfg))
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim pesan sticky ke {target.mention}. Cek izin bot.",
            ephemeral=True,
        )
        return

    cfg["last_message_id"] = posted.id
    await save_community_tools_to_disk()
    await interaction.followup.send(
        f"📌 **Sticky message aktif di {target.mention}.**\n"
        f"Pesan ini otomatis turun ke bawah setiap ada obrolan baru "
        f"(jeda aman {STICKY_MIN_INTERVAL_SEC} detik agar tidak spam).",
        ephemeral=True,
    )


@sticky_group.command(name="lepas", description="Hapus pesan sticky dari sebuah channel")
@app_commands.describe(channel="Channel yang sticky-nya ingin dilepas (default: channel ini)")
async def sticky_lepas_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = _resolve_text_target(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih channel terlebih dahulu.", ephemeral=True)
        return

    cfg = sticky_channels.get(target.id) or {}
    remove_sticky_config(target.id)
    await save_community_tools_to_disk()

    old_id = int(cfg.get("last_message_id") or 0)
    if old_id:
        try:
            await target.get_partial_message(old_id).delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    await interaction.response.send_message(
        f"✅ Sticky message di {target.mention} dilepas.", ephemeral=True
    )


@sticky_group.command(name="status", description="Lihat daftar channel dengan sticky message")
async def sticky_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    channels = [cid for cid, cfg in sticky_channels.items() if cfg.get("guild_id") == interaction.guild.id]
    if not channels:
        await interaction.response.send_message(
            "ℹ️ Belum ada sticky message. Pasang dengan `/sticky pasang isi:... channel:#umum`.",
            ephemeral=True,
        )
        return

    lines = [
        f"• <#{cid}> — {sticky_channels[cid]['content'][:70]}"
        for cid in channels[:15]
    ]
    await interaction.response.send_message(
        "📌 **Sticky Message Aktif**\n" + "\n".join(lines), ephemeral=True
    )


# ==============================================================================
# /info — Kartu Profil Member & Server
# ==============================================================================
info_group = app_commands.Group(
    name="info",
    description="Kartu profil member & informasi server (gratis, tanpa kuota AI)",
    guild_only=True,
)


@info_group.command(name="user", description="Lihat profil member: umur akun, tanggal join, & role")
@app_commands.describe(member="Member yang ingin dilihat (default: dirimu sendiri)")
async def info_user_cmd(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    if interaction.guild is None:
        return

    target = member or interaction.user
    if not isinstance(target, discord.Member):
        await interaction.response.send_message(
            "⚠️ Command ini hanya untuk member di dalam server.", ephemeral=True
        )
        return

    now = discord.utils.utcnow()
    account_days = max(0, (now - target.created_at).days)
    join_days = max(0, (now - target.joined_at).days) if target.joined_at else None

    embed = discord.Embed(
        title=f"👤 {target.display_name}",
        description=target.mention,
        color=target.color if target.color.value else discord.Color.blurple(),
        timestamp=now,
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(
        name="🆔 Identitas",
        value=(
            f"• **Username:** `{target.name}`\n"
            f"• **ID:** `{target.id}`\n"
            f"• **Bot:** {'Ya 🤖' if target.bot else 'Tidak'}"
        ),
        inline=False,
    )
    embed.add_field(
        name="📅 Umur Akun",
        value=f"`{account_days}` hari ({discord.utils.format_dt(target.created_at, 'D')})",
        inline=True,
    )
    if join_days is not None:
        embed.add_field(
            name="📥 Bergabung",
            value=f"`{join_days}` hari ({discord.utils.format_dt(target.joined_at, 'D')})",
            inline=True,
        )
    embed.add_field(
        name=f"🎭 Role ({len(target.roles) - 1})",
        value=(
            " ".join(r.mention for r in list(reversed(target.roles))[:12] if not r.is_default())
            or "_Belum punya role_"
        )[:1024],
        inline=False,
    )
    if account_days < 7:
        embed.add_field(
            name="⚠️ Catatan Keamanan",
            value="Akun masih **sangat baru** (< 7 hari). Waspadai bila mengirim link mencurigakan.",
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@info_group.command(name="server", description="Lihat ringkasan server: jumlah member, channel, & boost")
async def info_server_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return

    humans = sum(1 for m in guild.members if not m.bot)
    bots = len(guild.members) - humans
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    online = sum(
        1
        for m in guild.members
        if not m.bot and getattr(m, "status", discord.Status.offline) != discord.Status.offline
    )

    embed = discord.Embed(
        title=f"🏰 {guild.name}",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Member", value=f"`{humans}` manusia\n`{bots}` bot", inline=True)
    embed.add_field(name="🟢 Online", value=f"`{online}` member", inline=True)
    embed.add_field(name="💎 Boost", value=f"`{guild.premium_subscription_count}` boost", inline=True)
    embed.add_field(
        name="💬 Channel",
        value=f"`{text_channels}` teks | `{voice_channels}` voice | `{len(guild.categories)}` kategori",
        inline=True,
    )
    embed.add_field(
        name="🛡️ Keamanan",
        value=(
            f"• Verifikasi: {'✅ Aktif' if guild.id in verification_guilds else '❌ Belum'}\n"
            f"• Auto Role: {'✅ Aktif' if guild.id in autorole_guilds else '❌ Belum'}"
        ),
        inline=True,
    )
    owner = guild.owner.mention if guild.owner else "—"
    embed.add_field(name="👑 Pemilik", value=owner, inline=True)
    embed.set_footer(
        text=(
            f"ID: {guild.id} • Dibuat "
            f"{discord.utils.format_dt(guild.created_at, 'D')} • Bot v{BOT_VERSION}"
        )
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# /perawatan — Backup Otomatis & Log Error
# ==============================================================================
perawatan_group = app_commands.Group(
    name="perawatan",
    description="Perawatan bot: backup konfigurasi, channel log error, & status penyimpanan",
    guild_only=True,
)


@perawatan_group.command(name="backup", description="Kirim berkas backup konfigurasi bot sekarang juga")
@app_commands.describe(channel="Channel tujuan backup (default: channel backup yang tersimpan)")
async def perawatan_backup_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    cfg = maintenance_guilds.get(interaction.guild.id) or {}
    target = channel or (
        interaction.guild.get_channel(int(cfg.get("backup_channel_id") or 0))
        if cfg.get("backup_channel_id")
        else None
    )
    if target is None:
        await interaction.response.send_message(
            "⚠️ Pilih `channel` tujuan backup, atau atur defaultnya lewat "
            "`/perawatan atur backup_channel:#bot-backup`.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    ok, info = await send_backup(interaction.client, target)
    if not ok:
        await interaction.followup.send(info, ephemeral=True)
        return

    config = maintenance_guilds.get(interaction.guild.id)
    if config is None:
        config = set_maintenance_config(interaction.guild.id, backup_channel_id=target.id)
    config["last_backup_at"] = time.time()
    await save_community_tools_to_disk()
    await interaction.followup.send(
        f"✅ Backup terkirim ke {target.mention} sebagai `{info}`.\n"
        "Simpan berkas ini di luar Wispbyte agar aman saat server rebuild.",
        ephemeral=True,
    )


@perawatan_group.command(name="atur", description="Atur channel backup, channel log error, & backup otomatis")
@app_commands.describe(
    backup_channel="Channel tujuan backup otomatis berkala",
    log_channel="Channel tujuan laporan error bot",
    otomatis=f"True untuk backup otomatis tiap {BACKUP_INTERVAL_DAYS} hari",
)
async def perawatan_atur_cmd(
    interaction: discord.Interaction,
    backup_channel: discord.TextChannel | None = None,
    log_channel: discord.TextChannel | None = None,
    otomatis: bool | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if backup_channel is None and log_channel is None and otomatis is None:
        await interaction.response.send_message(
            "ℹ️ Tidak ada yang diubah. Contoh: "
            "`/perawatan atur backup_channel:#bot-backup log_channel:#bot-log otomatis:True`.",
            ephemeral=True,
        )
        return

    set_maintenance_config(
        interaction.guild.id,
        backup_channel_id=backup_channel.id if backup_channel else None,
        log_channel_id=log_channel.id if log_channel else None,
        auto_backup=otomatis if otomatis is not None else True,
    )
    await save_community_tools_to_disk()

    lines = []
    if backup_channel:
        lines.append(f"• **Backup channel:** {backup_channel.mention}")
    if log_channel:
        lines.append(f"• **Log error:** {log_channel.mention}")
    if otomatis is not None:
        lines.append(f"• **Backup otomatis:** {'AKTIF' if otomatis else 'NONAKTIF'}")
    await interaction.response.send_message(
        "🗂️ **Pengaturan perawatan diperbarui**\n" + "\n".join(lines), ephemeral=True
    )


@perawatan_group.command(name="status", description="Lihat status backup, log error, & ukuran data bot")
async def perawatan_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    cfg = maintenance_guilds.get(interaction.guild.id) or {}
    data, filename = build_backup_archive()
    size_kb = len(data) / 1024
    last_at = float(cfg.get("last_backup_at") or 0)
    last_text = (
        discord.utils.format_dt(datetime.fromtimestamp(last_at, tz=timezone.utc), style="R")
        if last_at
        else "_belum pernah_"
    )
    log_channel = f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_belum diatur_"
    backup_channel = (
        f"<#{cfg['backup_channel_id']}>" if cfg.get("backup_channel_id") else "_belum diatur_"
    )

    await interaction.response.send_message(
        f"🗂️ **Status Perawatan Bot**\n"
        f"• **Backup channel:** {backup_channel}\n"
        f"• **Backup otomatis:** {'AKTIF' if cfg.get('auto_backup') else 'NONAKTIF'} "
        f"(tiap {BACKUP_INTERVAL_DAYS} hari)\n"
        f"• **Backup terakhir:** {last_text}\n"
        f"• **Log error:** {log_channel}\n"
        f"• **Ukuran backup saat ini:** `{size_kb:.1f} KB` (`{filename}`)\n"
        f"• **RAM bot:** `{get_memory_usage_mb()} MB`",
        ephemeral=True,
    )


def register_community_cog(bot: commands.Bot) -> None:
    """Mendaftarkan seluruh command fitur komunitas ringan ke bot."""
    bot.tree.add_command(slash_poll)
    bot.tree.add_command(panelrole_group)
    bot.tree.add_command(ingatkan_group)
    bot.tree.add_command(starboard_group)
    bot.tree.add_command(verifikasi_group)
    bot.tree.add_command(sticky_group)
    bot.tree.add_command(info_group)
    bot.tree.add_command(perawatan_group)
