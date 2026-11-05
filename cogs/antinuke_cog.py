"""Slash `/nuke` — Anti-Nuke: deteksi & tindak penghancuran server (**0 kuota AI**).

Isi:
- `/nuke status` — konfigurasi, ambang per aksi, izin bot, & pelanggaran terakhir.
- `/nuke atur` *(Admin)* — aktifkan, channel log, DM owner, aksi (lapor/cabut-role/timeout/kick/ban),
  durasi timeout, ambang, jendela waktu, & pemulihan identitas/webhook.
- `/nuke whitelist` *(Admin)* — daftar/tambah/hapus member & role yang tidak pernah ditindak.
- `/nuke uji` *(Admin)* — uji kering: lihat ambang & aksi yang akan dijalankan (tanpa menindak).
- `/nuke pulihkan` *(Admin)* — pulihkan nama/ikon server dari titik pulih terakhir.
- `/nuke matikan` *(Admin)* — hentikan pemantauan anti-nuke di server ini.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import antinuke
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.antinuke_cog")

nuke_group = app_commands.Group(
    name="nuke",
    description="Anti-Nuke: cegah penghapusan massal channel/role, ban massal, & webhook jahat (0 kuota AI)",
    guild_only=True,
)

_AKSI_CHOICES = [
    app_commands.Choice(name=f"{label}", value=key) for key, label in antinuke.PUNISH_CHOICES.items()
]

_THRESHOLD_CHOICES = [
    app_commands.Choice(
        name=f"{spec['emoji']} {spec['label']} (bawaan {spec['count']}/{spec['window']} dtk)",
        value=key,
    )
    for key, spec in antinuke.ACTIONS.items()
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
            gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server* yang bisa mengatur anti-nuke."
        ),
        ephemeral=True,
    )
    return False


def _can_read_audit(guild) -> bool:
    me = getattr(guild, "me", None)
    perms = getattr(me, "guild_permissions", None)
    return bool(perms and getattr(perms, "view_audit_log", False))


@nuke_group.command(name="status", description="Lihat status anti-nuke: ambang, aksi, whitelist, & pelanggaran terakhir")
async def nuke_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    cfg = antinuke.get_config(gid)
    can_audit = _can_read_audit(interaction.guild)

    # Simpan titik pulih identitas saat kondisi server normal
    if not (cfg.get("identity") or {}).get("name"):
        await antinuke.save_antinuke_to_disk()

    lines = [
        f"• Status: {'✅ aktif' if cfg.get('enabled') else '⛔ nonaktif'}",
        f"• Aksi saat terdeteksi: **{cfg.get('action')}** — "
        f"{antinuke.PUNISH_CHOICES.get(str(cfg.get('action')), '?')}",
        "• Channel log: " + (f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_channel sistem_"),
        f"• DM owner: {'✅' if cfg.get('dm_owner') else '⛔'} • "
        f"Pemulihan otomatis: {'✅' if cfg.get('restore') else '⛔'}",
        "• Izin *View Audit Log*: " + ("✅ ada" if can_audit else "⛔ **belum** — anti-nuke tidak bisa membaca audit log"),
        f"• Whitelist: `{len(cfg.get('whitelist_users') or [])}` member • `{len(cfg.get('whitelist_roles') or [])}` role",
    ]

    rows = []
    for key, spec in antinuke.ACTIONS.items():
        limit = cfg["thresholds"][key]
        rows.append(f"• {spec['emoji']} {spec['label']}: `{limit['count']}`× / `{limit['window']}` dtk")
    lines.append("\n**Ambang deteksi**\n" + "\n".join(rows))

    recent = antinuke.recent_violations(gid, 3)
    if recent:
        history = []
        for row in recent:
            stamp = f"<t:{int(row.get('at', 0))}:R>"
            history.append(
                f"• {stamp} <@{row.get('user_id')}> — {row.get('label')} "
                f"(`{row.get('count')}`×) → {row.get('taken')}"
            )
        lines.append("\n**Pelanggaran terakhir**\n" + "\n".join(history))
    else:
        lines.append("\n_Pelanggaran tercatat: belum ada._")

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "🛡️ Status Anti-Nuke",
            "\n".join(lines)[:3800],
            footer="0 kuota AI • owner, bot, & whitelist tidak pernah ditindak",
        ),
        ephemeral=True,
    )


@nuke_group.command(name="atur", description="Atur anti-nuke: aktif, channel log, aksi, ambang, & pemulihan (Admin)")
@app_commands.describe(
    aktif="True untuk memantau, False untuk berhenti",
    channel="Channel laporan anti-nuke",
    aksi="Tindakan otomatis ke pelaku saat ambang terlampaui",
    timeout_detik="Durasi timeout bila aksi = timeout (detik, maks 28 hari)",
    dm_owner="Kirim laporan juga ke DM owner server",
    pulihkan="Pulihkan nama/ikon server & hapus webhook pelaku otomatis",
    jenis_ambang="Jenis aksi yang ambangnya ingin diubah",
    ambang="Jumlah aksi dalam jendela waktu sebelum dianggap nuke",
    jendela_detik="Panjang jendela waktu (detik) untuk semua jenis aksi",
)
@app_commands.choices(aksi=_AKSI_CHOICES, jenis_ambang=_THRESHOLD_CHOICES)
async def nuke_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool | None = None,
    channel: discord.TextChannel | None = None,
    aksi: app_commands.Choice[str] | None = None,
    timeout_detik: app_commands.Range[int, 60, 2419200] | None = None,
    dm_owner: bool | None = None,
    pulihkan: bool | None = None,
    jenis_ambang: app_commands.Choice[str] | None = None,
    ambang: app_commands.Range[int, 1, 100] | None = None,
    jendela_detik: app_commands.Range[int, 10, 86400] | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    thresholds = None
    if jenis_ambang is not None and ambang is not None:
        thresholds = {jenis_ambang.value: int(ambang)}

    antinuke.set_config(
        gid,
        enabled=aktif,
        log_channel_id=channel.id if channel else None,
        action=aksi.value if aksi else None,
        timeout_sec=int(timeout_detik) if timeout_detik else None,
        dm_owner=dm_owner,
        restore=pulihkan,
        thresholds=thresholds,
        window=int(jendela_detik) if jendela_detik else None,
    )
    # Perbarui titik pulih identitas setiap kali Admin menyimpan pengaturan
    if interaction.guild is not None:
        antinuke.snapshot_identity(interaction.guild)
    await antinuke.save_antinuke_to_disk()

    cfg = antinuke.get_config(gid)
    warn = ""
    if cfg.get("enabled") and not _can_read_audit(interaction.guild):
        warn = (
            "\n\n⚠️ **Bot belum punya izin View Audit Log**, jadi deteksi belum bisa berjalan. "
            "Aktifkan izin itu pada role bot."
        )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if cfg.get("enabled") else "info",
            "Pengaturan Anti-Nuke disimpan",
            f"• Status: **{'aktif' if cfg.get('enabled') else 'nonaktif'}**\n"
            f"• Aksi: **{cfg.get('action')}** ({antinuke.PUNISH_CHOICES.get(str(cfg.get('action')), '?')})\n"
            f"• Timeout: `{cfg.get('timeout_sec')}` dtk • DM owner: {'✅' if cfg.get('dm_owner') else '⛔'}\n"
            f"• Pemulihan: {'✅' if cfg.get('restore') else '⛔'}\n"
            "• Channel log: " + (f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "_channel sistem_")
            + warn,
        ),
        ephemeral=True,
    )


@nuke_group.command(name="whitelist", description="Kelola member/role yang tidak pernah ditindak anti-nuke (Admin)")
@app_commands.describe(
    aksi="Lihat, tambah, atau hapus",
    member="Member yang dikecualikan",
    role="Role yang pemegangnya dikecualikan (mis. role Moderator)",
)
@app_commands.choices(
    aksi=[
        app_commands.Choice(name="Lihat daftar", value="lihat"),
        app_commands.Choice(name="Tambah", value="tambah"),
        app_commands.Choice(name="Hapus", value="hapus"),
    ]
)
async def nuke_whitelist_cmd(
    interaction: discord.Interaction,
    aksi: app_commands.Choice[str] | None = None,
    member: discord.Member | None = None,
    role: discord.Role | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    mode = aksi.value if aksi else "lihat"
    note = ""
    if mode in ("tambah", "hapus"):
        if member is None and role is None:
            await ui_kit.send_status(
                interaction,
                embed=ui_theme.status_embed(
                    gid, "warn", "Pilih target", "Sebutkan `member:` atau `role:` yang ingin diubah."
                ),
                ephemeral=True,
            )
            return
        if mode == "tambah":
            changed = antinuke.add_whitelist(gid, user_id=member.id if member else None,
                                             role_id=role.id if role else None)
            note = "Ditambahkan ke whitelist." if changed else "Sudah ada di whitelist."
        else:
            changed = antinuke.remove_whitelist(gid, user_id=member.id if member else None,
                                                role_id=role.id if role else None)
            note = "Dihapus dari whitelist." if changed else "Tidak ditemukan di whitelist."
        await antinuke.save_antinuke_to_disk()

    cfg = antinuke.get_config(gid)
    users = cfg.get("whitelist_users") or []
    roles = cfg.get("whitelist_roles") or []
    body = [
        "**Member**\n" + ("\n".join(f"• <@{uid}>" for uid in users) or "_belum ada_"),
        "**Role**\n" + ("\n".join(f"• <@&{rid}>" for rid in roles) or "_belum ada_"),
        "\n-# Owner server & bot ini selalu otomatis dikecualikan.",
    ]
    if note:
        body.insert(0, f"✅ {note}\n")
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(gid, "info", "🧾 Whitelist Anti-Nuke", "\n\n".join(body)[:3500]),
        ephemeral=True,
    )


@nuke_group.command(name="uji", description="Uji kering: lihat ambang & tindakan yang akan dijalankan (Admin)")
@app_commands.describe(jenis="Jenis aksi berisiko yang ingin diuji")
@app_commands.choices(jenis=_THRESHOLD_CHOICES)
async def nuke_uji_cmd(interaction: discord.Interaction, jenis: app_commands.Choice[str] | None = None):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    keys = [jenis.value] if jenis else list(antinuke.ACTIONS)
    rows = []
    for key in keys:
        data = antinuke.simulate(gid, key)
        rows.append(
            f"• {antinuke.ACTIONS[key]['emoji']} **{data['label']}** — "
            f"terdeteksi setelah `{data['limit']}` aksi dalam `{data['window']}` dtk → "
            f"tindakan **{data['action_mode']}**"
        )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "🧪 Uji Kering Anti-Nuke",
            "\n".join(rows)[:3500]
            + "\n\n-# Tidak ada tindakan yang dijalankan. Ubah dengan `/nuke atur`.",
        ),
        ephemeral=True,
    )


@nuke_group.command(name="pulihkan", description="Pulihkan nama & ikon server dari titik pulih terakhir (Admin)")
async def nuke_pulihkan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, message = await antinuke.restore_identity(interaction.client, interaction.guild)
    if ok:
        antinuke.snapshot_identity(interaction.guild)
        await antinuke.save_antinuke_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "ok" if ok else "warn", "Pemulihan identitas server", message
        ),
        follow=True,
        ephemeral=True,
    )


@nuke_group.command(name="matikan", description="Hentikan pemantauan anti-nuke di server ini (Admin)")
async def nuke_matikan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not await _guard(interaction, gid):
        return

    antinuke.set_config(gid, enabled=False)
    await antinuke.save_antinuke_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "Anti-Nuke dimatikan",
            "Pemantauan berhenti. Nyalakan lagi kapan saja dengan `/nuke atur aktif:True`.",
        ),
        ephemeral=True,
    )


def register_antinuke_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/nuke` ke bot."""
    bot.tree.add_command(nuke_group)
