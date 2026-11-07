"""Command Slash fitur engagement (Tier 2A) — semua **tanpa kuota Gemini**.

Grup command:
- `/giveaway`        — undian berhadiah dengan tombol persisten 🎉
- `/ultah`           — pendaftaran ulang tahun + pengumuman otomatis
- `/jawab-otomatis`  — balasan otomatis berbasis kata kunci per channel
- `/pengumuman`      — pengumuman terjadwal (harian / mingguan / sekali)
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import engagement
from config import (
    ANNOUNCEMENT_MAX_PER_GUILD,
    AUTO_REPLY_COOLDOWN_SEC,
    AUTO_REPLY_MAX_RULES,
    BOT_TIMEZONE,
    GIVEAWAY_HISTORY_MAX,
)
from utils import get_realtime_time_context
from views import GiveawayJoinView

logger = logging.getLogger("gemini_bot.engagement_cog")


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.",
        ephemeral=True,
    )


def _guild_timezone(guild_id: int) -> str:
    try:
        from community_agent import get_guild_settings

        return get_guild_settings(guild_id).get("timezone", BOT_TIMEZONE)
    except Exception:  # pragma: no cover - modul opsional
        return BOT_TIMEZONE


def _resolve_text_channel(interaction: discord.Interaction, channel):
    if channel is not None:
        return channel
    current = interaction.channel
    if current is None or isinstance(current, (discord.Thread, discord.DMChannel, discord.ForumChannel)):
        return None
    return current if hasattr(current, "send") else None


# ==============================================================================
# /giveaway
# ==============================================================================
giveaway_group = app_commands.Group(
    name="giveaway",
    description="Undian berhadiah dengan tombol 🎉 (tanpa kuota AI)",
    guild_only=True,
)


def _susun_syarat(
    guild_id: int,
    *,
    templat: str | None = None,
    role_ids: list[int] | None = None,
    level: int = 0,
    account_age_days: int = 0,
    bonus_role_id: int = 0,
    bobot_bonus: int = 1,
) -> tuple[dict, dict, dict]:
    """Gabungkan template/setelan dashboard dengan argumen command.

    Mengembalikan `(jumlah, syarat, bonus)` — `jumlah` berisi `winner_count`
    & `seconds`, siap dipakai `create_giveaway`.
    """
    tpl = engagement.get_giveaway_template(guild_id, templat) if templat else None
    if tpl:
        jumlah = {"winner_count": tpl["winner_count"], "seconds": tpl["seconds"]}
        syarat = dict(tpl["requirements"])
        bonus = dict(tpl["bonus_roles"])
    else:
        bawaan = engagement.default_giveaway_config(guild_id)
        jumlah = {"winner_count": bawaan["winner_count"], "seconds": bawaan["seconds"]}
        syarat = engagement.default_requirements(guild_id)
        bonus = engagement.default_bonus_roles(guild_id)

    for rid in role_ids or []:
        if rid and rid not in syarat["roles"]:
            syarat["roles"].append(int(rid))
    if level > 0:
        syarat["level"] = int(level)
    if account_age_days > 0:
        syarat["account_age_days"] = int(account_age_days)
    if bonus_role_id:
        bonus[str(int(bonus_role_id))] = max(1, min(5, int(bobot_bonus)))
    syarat = engagement.normalize_requirements(
        roles=syarat.get("roles"),
        level=syarat.get("level"),
        account_age_days=syarat.get("account_age_days"),
    )
    return jumlah, syarat, engagement.normalize_bonus_roles(bonus)


@giveaway_group.command(
    name="mulai", description="Mulai giveaway baru (bisa disyaratkan level/umur akun/role & bonus booster)"
)
@app_commands.describe(
    hadiah="Nama hadiah, misal: Nitro 1 Bulan / Saldo 50rb",
    durasi="Lama giveaway: 30m, 2 jam, 1j30m, 2 hari (kosong = ikut setelan dashboard)",
    pemenang="Berapa pemenang yang diundi (1-20, 0 = ikut setelan dashboard)",
    channel="Channel tempat giveaway dipasang (default: channel ini)",
    syarat_role="Role yang wajib dimiliki untuk ikut (opsional)",
    syarat_role_2="Role wajib kedua — harus dimiliki juga (opsional)",
    syarat_level="Level minimal peserta (0 = tanpa syarat level)",
    syarat_umur_akun="Umur akun Discord minimal dalam hari (0 = tanpa syarat)",
    role_bonus="Role yang menambah peluang menang (mis. Booster)",
    bobot_bonus="Tambahan peluang untuk pemilik role bonus (1-5)",
    templat="Nama template tersimpan untuk mengisi semua setelan otomatis",
)
async def giveaway_mulai_cmd(
    interaction: discord.Interaction,
    hadiah: str,
    durasi: str = "",
    pemenang: int = 0,
    channel: discord.TextChannel | None = None,
    syarat_role: discord.Role | None = None,
    syarat_role_2: discord.Role | None = None,
    syarat_level: int = 0,
    syarat_umur_akun: int = 0,
    role_bonus: discord.Role | None = None,
    bobot_bonus: int = 1,
    templat: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    prize = str(hadiah or "").strip()
    if not prize:
        await interaction.response.send_message("⚠️ Nama hadiah tidak boleh kosong.", ephemeral=True)
        return

    gid = interaction.guild.id
    if templat and engagement.get_giveaway_template(gid, templat) is None:
        await interaction.response.send_message(
            f"⚠️ Template `{templat}` belum ada. Lihat daftarnya di `/giveaway template-daftar`.",
            ephemeral=True,
        )
        return

    role_ids = [r.id for r in (syarat_role, syarat_role_2) if r is not None]
    jumlah, syarat, bonus = _susun_syarat(
        gid,
        templat=templat,
        role_ids=role_ids,
        level=max(0, int(syarat_level)),
        account_age_days=max(0, int(syarat_umur_akun)),
        bonus_role_id=role_bonus.id if role_bonus else 0,
        bobot_bonus=max(1, min(5, int(bobot_bonus))),
    )

    target_durasi = str(durasi or "").strip()
    seconds = engagement.parse_giveaway_duration(target_durasi) if target_durasi else jumlah["seconds"]
    if not seconds:
        await interaction.response.send_message(
            "⚠️ Format durasi tidak valid. Contoh: `30m`, `2 jam`, `1j30m`, `2 hari`.",
            ephemeral=True,
        )
        return
    if seconds < 60:
        await interaction.response.send_message(
            "⚠️ Minimal **1 menit** agar member sempat ikut.", ephemeral=True
        )
        return

    target = _resolve_text_channel(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih `channel` tempat giveaway dipasang.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    cfg = {
        "message_id": 0,
        "guild_id": gid,
        "channel_id": target.id,
        "prize": prize[:200],
        "host_id": interaction.user.id,
        "winner_count": max(1, min(20, int(pemenang) if int(pemenang) > 0 else jumlah["winner_count"])),
        "ends_at": 0.0,
        "ended": False,
        "role_id": syarat["roles"][0] if syarat["roles"] else None,
        "requirements": syarat,
        "bonus_roles": bonus,
        "entries": [],
        "winners": [],
    }
    ping = engagement.default_giveaway_config(gid).get("ping_everyone") and interaction.guild is not None
    try:
        message = await target.send(
            "@everyone 🎉 **Giveaway baru!**" if ping else None,
            embed=engagement.build_giveaway_embed(cfg),
            view=GiveawayJoinView(),
            allowed_mentions=discord.AllowedMentions(everyone=True) if ping else discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            f"⚠️ Gagal mengirim giveaway ke {target.mention}. Cek izin **Kirim Pesan** & **Embed Links**.",
            ephemeral=True,
        )
        return

    cfg = engagement.create_giveaway(
        guild_id=gid,
        channel_id=target.id,
        message_id=message.id,
        prize=prize,
        host_id=interaction.user.id,
        seconds=seconds,
        winner_count=int(cfg["winner_count"]),
        requirements=syarat,
        bonus_roles=bonus,
    )
    cfg["winners"] = []
    await engagement.save_engagement_to_disk()

    await interaction.followup.send(
        f"🎉 **Giveaway dimulai di {target.mention}!**\n"
        f"• Hadiah: **{cfg['prize']}**\n"
        f"• Pemenang: `{cfg['winner_count']}` orang\n"
        f"• Syarat: {engagement.requirement_summary(cfg)}\n"
        f"• Berakhir: {engagement.format_timestamp(cfg['ends_at'], 'R')}\n"
        f"• ID pesan: `{message.id}` — simpan untuk `/giveaway akhiri` / `reroll`.",
        ephemeral=True,
    )


@giveaway_group.command(name="peserta", description="Lihat peserta satu giveaway beserta peluang & syaratnya")
@app_commands.describe(id_pesan="ID pesan giveaway (atau tempel tautan pesannya)")
async def giveaway_peserta_cmd(interaction: discord.Interaction, id_pesan: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    message_id = _extract_message_id(id_pesan)
    cfg = engagement.giveaways.get(message_id) if message_id else None
    if cfg is None or cfg.get("guild_id") != interaction.guild.id:
        await interaction.response.send_message(
            "⚠️ Giveaway dengan ID itu tidak ditemukan di server ini.", ephemeral=True
        )
        return

    entries = cfg.get("entries") or []
    embed = discord.Embed(
        title="👥 Peserta Giveaway",
        color=discord.Color.gold(),
        description=(
            f"**{cfg.get('prize')}**\n"
            f"`{len(entries)}` peserta • syarat: {engagement.requirement_summary(cfg)}\n"
            f"Status: {'⏹️ selesai' if cfg.get('ended') else '⏳ berjalan'}"
        ),
    )
    urut = sorted(entries, key=lambda uid: -engagement._weight_of(cfg, uid))
    baris = [
        f"• <@{uid}> — peluang `{engagement._weight_of(cfg, uid)}×`" for uid in urut[:25]
    ]
    if baris:
        embed.add_field(name="Peserta (peluang terbesar di atas)", value="\n".join(baris)[:1024], inline=False)
    else:
        embed.add_field(name="Peserta", value="_Belum ada yang ikut._", inline=False)

    riwayat = engagement.giveaway_history(message_id)
    if riwayat:
        isi = []
        for item in riwayat[-5:]:
            who = ", ".join(f"<@{uid}>" for uid in (item.get("pemenang") or [])) or "_kosong_"
            pelaku = f"<@{item['oleh']}>" if item.get("oleh") else "otomatis"
            isi.append(
                f"• {engagement.format_timestamp(float(item.get('at') or 0), 'R')} — "
                f"{item.get('aksi')} oleh {pelaku} → {who}"
            )
        embed.add_field(name="🧾 Riwayat undian", value="\n".join(isi)[:1024], inline=False)

    embed.set_footer(text=f"Masih bisa diundi ulang: {engagement.reroll_pool_size(message_id)} peserta")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@giveaway_group.command(name="template-simpan", description="Simpan setelan giveaway jadi template yang bisa dipakai ulang")
@app_commands.describe(
    nama="Nama template (maksimal 40 karakter)",
    pemenang="Jumlah pemenang bawaan (1-20)",
    durasi="Durasi bawaan: 30m, 2 jam, 2 hari (default 1 jam)",
    syarat_role="Role wajib untuk ikut (opsional)",
    syarat_level="Level minimal peserta (0 = tanpa syarat)",
    syarat_umur_akun="Umur akun minimal dalam hari (0 = tanpa syarat)",
    role_bonus="Role yang menambah peluang (opsional)",
    bobot_bonus="Tambahan peluang untuk role bonus (1-5)",
)
async def giveaway_template_simpan_cmd(
    interaction: discord.Interaction,
    nama: str,
    pemenang: int = 1,
    durasi: str = "1 jam",
    syarat_role: discord.Role | None = None,
    syarat_level: int = 0,
    syarat_umur_akun: int = 0,
    role_bonus: discord.Role | None = None,
    bobot_bonus: int = 1,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    seconds = engagement.parse_giveaway_duration(durasi) or 3600
    if seconds < 60:
        await interaction.response.send_message("⚠️ Durasi minimal 1 menit.", ephemeral=True)
        return

    syarat = engagement.normalize_requirements(
        roles=[syarat_role.id] if syarat_role else [],
        level=max(0, int(syarat_level)),
        account_age_days=max(0, int(syarat_umur_akun)),
    )
    bonus = {str(role_bonus.id): max(1, min(5, int(bobot_bonus)))} if role_bonus else {}
    ok, pesan = engagement.save_giveaway_template(
        interaction.guild.id,
        nama,
        winner_count=max(1, min(20, int(pemenang))),
        seconds=seconds,
        requirements=syarat,
        bonus_roles=bonus,
    )
    if ok:
        await engagement.save_engagement_to_disk()
        pesan += (
            f"\nPakai dengan `/giveaway mulai hadiah:... templat:{nama}`.\n"
            f"Syarat: {engagement.requirement_summary({'requirements': syarat, 'bonus_roles': bonus})}"
        )
    await interaction.response.send_message(
        ("✅ " if ok else "⚠️ ") + pesan[:1500], ephemeral=True
    )


@giveaway_group.command(name="template-daftar", description="Lihat semua template giveaway di server ini")
async def giveaway_template_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    items = engagement.list_giveaway_templates(interaction.guild.id)
    if not items:
        await interaction.response.send_message(
            "ℹ️ Belum ada template. Simpan satu dengan `/giveaway template-simpan`.\n"
            "Template berguna untuk giveaway rutin (mis. “Nitro bulanan” dengan syarat level 5).",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🗂️ Template Giveaway",
        color=discord.Color.gold(),
        description=f"`{len(items)}` template tersimpan",
    )
    for tpl in items[:20]:
        embed.add_field(
            name=f"`{tpl['nama']}`",
            value=(
                f"{tpl['winner_count']} pemenang • {engagement.format_duration_short(tpl['seconds'])}\n"
                f"Syarat: {engagement.requirement_summary({'requirements': tpl['requirements'], 'bonus_roles': tpl['bonus_roles']})}"
            )[:1024],
            inline=False,
        )
    embed.set_footer(text="Pakai: /giveaway mulai hadiah:... templat:<nama>")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@giveaway_group.command(name="template-hapus", description="Hapus satu template giveaway")
@app_commands.describe(nama="Nama template yang ingin dihapus")
async def giveaway_template_hapus_cmd(interaction: discord.Interaction, nama: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if engagement.delete_giveaway_template(interaction.guild.id, nama):
        await engagement.save_engagement_to_disk()
        await interaction.response.send_message(f"🗑️ Template `{nama}` dihapus.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"⚠️ Template `{nama}` tidak ditemukan. Lihat `/giveaway template-daftar`.",
            ephemeral=True,
        )


@giveaway_group.command(name="akhiri", description="Tutup giveaway lebih awal & umumkan pemenang")
@app_commands.describe(id_pesan="ID pesan giveaway (atau tempel tautan pesannya)")
async def giveaway_akhiri_cmd(interaction: discord.Interaction, id_pesan: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    message_id = _extract_message_id(id_pesan)
    if message_id is None:
        await interaction.response.send_message("⚠️ ID/tautan pesan tidak valid.", ephemeral=True)
        return

    cfg = engagement.giveaways.get(message_id)
    if cfg is None or cfg.get("guild_id") != interaction.guild.id:
        await interaction.response.send_message(
            "⚠️ Giveaway dengan ID itu tidak ditemukan di server ini.", ephemeral=True
        )
        return
    if cfg.get("ended"):
        await interaction.response.send_message(
            "ℹ️ Giveaway ini sudah selesai. Gunakan `/giveaway reroll` untuk mengundi ulang.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    ended = engagement.end_giveaway(message_id)
    await engagement.save_engagement_to_disk()
    if ended is not None:
        await engagement._update_giveaway_message(interaction.client, ended)

    winners = (ended or {}).get("winners") or []
    if winners:
        await interaction.followup.send(
            "🎉 Giveaway ditutup. Pemenang: " + ", ".join(f"<@{uid}>" for uid in winners),
            ephemeral=False,
        )
    else:
        await interaction.followup.send(
            "🎉 Giveaway ditutup, tetapi **tidak ada peserta** yang bisa diundi.", ephemeral=True
        )


@giveaway_group.command(name="reroll", description="Undi ulang pemenang dari peserta yang belum menang")
@app_commands.describe(id_pesan="ID pesan giveaway (atau tempel tautan pesannya)")
async def giveaway_reroll_cmd(interaction: discord.Interaction, id_pesan: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    message_id = _extract_message_id(id_pesan)
    if message_id is None:
        await interaction.response.send_message("⚠️ ID/tautan pesan tidak valid.", ephemeral=True)
        return

    status, cfg = engagement.reroll_giveaway(message_id)
    if status == "tidak_ada" or cfg is None or cfg.get("guild_id") != interaction.guild.id:
        await interaction.response.send_message(
            "⚠️ Giveaway dengan ID itu tidak ditemukan di server ini.", ephemeral=True
        )
        return
    if status == "belum_selesai":
        await interaction.response.send_message(
            "⚠️ Giveaway masih berjalan. Tutup dulu dengan `/giveaway akhiri`.", ephemeral=True
        )
        return
    if status == "habis":
        await interaction.response.send_message(
            "ℹ️ Semua peserta sudah pernah menang, tidak ada kandidat baru.", ephemeral=True
        )
        return

    await engagement.save_engagement_to_disk()
    await engagement._update_giveaway_message(interaction.client, cfg)
    await interaction.response.send_message(
        "🔁 Pemenang baru: " + ", ".join(f"<@{uid}>" for uid in (cfg.get("winners") or [])),
        ephemeral=False,
    )


@giveaway_group.command(name="daftar", description="Lihat giveaway yang masih berjalan & riwayat terakhir")
async def giveaway_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    items = [g for g in engagement.giveaways.values() if g.get("guild_id") == interaction.guild.id]
    if not items:
        await interaction.response.send_message(
            "ℹ️ Belum ada giveaway di server ini. Mulai dengan `/giveaway mulai`.", ephemeral=True
        )
        return

    active = [g for g in items if not g.get("ended")]
    finished = sorted(
        [g for g in items if g.get("ended")],
        key=lambda g: float(g.get("ends_at") or 0),
        reverse=True,
    )[:GIVEAWAY_HISTORY_MAX]

    embed = discord.Embed(
        title="🎉 Daftar Giveaway",
        color=discord.Color.gold(),
        description=f"`{len(active)}` berjalan • `{len(finished)}` selesai",
    )
    if active:
        embed.add_field(
            name="⏳ Masih Berjalan",
            value="\n".join(
                f"• **{g['prize']}** — {len(g.get('entries') or [])} peserta — "
                f"berakhir {engagement.format_timestamp(float(g.get('ends_at') or 0), 'R')}"
                for g in active
            )[:1024],
            inline=False,
        )
    if finished:
        lines = []
        for g in finished[:10]:
            winners = g.get("winners") or []
            who = ", ".join(f"<@{uid}>" for uid in winners) if winners else "_tanpa pemenang_"
            lines.append(f"• **{g['prize']}** — {who}")
        embed.add_field(name="✅ Selesai", value="\n".join(lines)[:1024], inline=False)
    embed.set_footer(text="Tip: /giveaway mulai hadiah:... durasi:2jam pemenang:3")
    import ui_kit

    await ui_kit.send_panel(
        interaction,
        ui_kit.build_view(
            interaction.guild.id, ui_kit.embed_to_container(interaction.guild.id, embed)
        ),
        embed=embed,
        ephemeral=True,
    )


def _extract_message_id(raw: str | None) -> int | None:
    """Membaca ID pesan dari angka biasa maupun tautan Discord."""
    import re

    text = str(raw or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    found = re.findall(r"(\d{15,25})", text)
    return int(found[-1]) if found else None


# ==============================================================================
# /ultah
# ==============================================================================
ultah_group = app_commands.Group(
    name="ultah",
    description="Daftar ulang tahun member & ucapan otomatis (tanpa kuota AI)",
    guild_only=True,
)


@ultah_group.command(name="set", description="Daftarkan/perbarui tanggal lahirmu (hanya tanggal & bulan yang ditampilkan)")
@app_commands.describe(tanggal="Tanggal lahir: 12-08, 12/8/2000, atau 12 Agustus 1999")
async def ultah_set_cmd(interaction: discord.Interaction, tanggal: str):
    if interaction.guild is None:
        return

    parsed = engagement.parse_birthday_date(tanggal)
    if parsed is None:
        await interaction.response.send_message(
            "⚠️ Format tanggal tidak dikenali.\n"
            "Contoh: `12-08`, `12/8/2000`, `12 Agustus 1999`, `1 Januari`.",
            ephemeral=True,
        )
        return

    day, month, year = parsed
    engagement.set_birthday(interaction.guild.id, interaction.user.id, day, month, year)
    await engagement.save_engagement_to_disk()

    month_name = engagement._INDONESIAN_MONTHS[month - 1].capitalize()
    extra = f" (lahir {year})" if year else ""
    await interaction.response.send_message(
        f"🎂 Tersimpan! Ulang tahunmu **{day} {month_name}**{extra}.\n"
        "Bot akan mengucapkan otomatis di channel yang ditentukan Admin lewat `/ultah atur`.\n"
        f"Ganti kapan saja dengan `/ultah set`, atau hapus lewat `/ultah hapus`.",
        ephemeral=True,
    )


@ultah_group.command(name="hapus", description="Hapus data ulang tahunmu dari server ini")
async def ultah_hapus_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    removed = engagement.remove_birthday(interaction.guild.id, interaction.user.id)
    if removed:
        await engagement.save_engagement_to_disk()
        await interaction.response.send_message("🗑️ Data ulang tahunmu sudah dihapus.", ephemeral=True)
    else:
        await interaction.response.send_message(
            "ℹ️ Kamu belum mendaftarkan ulang tahun di server ini.", ephemeral=True
        )


@ultah_group.command(name="daftar", description="Lihat daftar ulang tahun member di server ini")
@app_commands.describe(bulan="Filter satu bulan (1-12), kosongkan untuk semua")
async def ultah_daftar_cmd(interaction: discord.Interaction, bulan: int | None = None):
    if interaction.guild is None:
        return
    if bulan is not None and not (1 <= bulan <= 12):
        await interaction.response.send_message("⚠️ Bulan harus 1-12.", ephemeral=True)
        return

    items = engagement.list_birthdays(interaction.guild.id, month=bulan)
    title = "🎂 Daftar Ulang Tahun"
    if not items:
        await interaction.response.send_message(
            f"{title}\n\nBelum ada data. Ajak member mendaftar dengan `/ultah set tanggal:12-08`.",
            ephemeral=True,
        )
        return

    lines = []
    for data in items[:80]:
        month_name = engagement._INDONESIAN_MONTHS[int(data["month"]) - 1].capitalize()
        lines.append(f"• `{int(data['day']):02d} {month_name}` — <@{data['user_id']}>")

    embed = discord.Embed(title=title, description="\n".join(lines)[:4000], color=discord.Color.magenta())
    embed.set_footer(text=f"Total {len(items)} member terdaftar • data hanya tanggal & bulan")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@ultah_group.command(name="atur", description="Tentukan channel & jam pengumuman ulang tahun otomatis")
@app_commands.describe(
    channel="Channel tempat ucapan dikirim (kosongkan untuk mematikan fitur)",
    jam="Jam pengumuman format HH:MM (default 08:00)",
)
async def ultah_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    jam: str = "08:00",
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if channel is None:
        removed = engagement.disable_birthday_channel(interaction.guild.id)
        if removed:
            await engagement.save_engagement_to_disk()
        await interaction.response.send_message(
            "🔕 Pengumuman ulang tahun **dimatikan**." if removed else "ℹ️ Fitur ini memang belum aktif.",
            ephemeral=True,
        )
        return

    from server_features import slot_to_minutes

    minutes = slot_to_minutes(jam)
    if minutes is None:
        await interaction.response.send_message(
            "⚠️ Format jam tidak valid. Contoh: `08:00`, `8`, `20:30`.", ephemeral=True
        )
        return

    hour, minute = divmod(minutes, 60)
    cfg = engagement.set_birthday_channel(interaction.guild.id, channel.id, hour, minute)
    await engagement.save_engagement_to_disk()
    tz_name = _guild_timezone(interaction.guild.id)
    tz_label = get_realtime_time_context(tz_name).get("tz_label", "WIB")
    await interaction.response.send_message(
        f"🎂 **Ucapan ulang tahun aktif** di {channel.mention} setiap hari pukul "
        f"`{cfg['hour']:02d}:{cfg['minute']:02d}` {tz_label}.\n"
        "Pastikan member sudah mendaftar dengan `/ultah set`.",
        ephemeral=True,
    )


# ==============================================================================
# /jawab-otomatis
# ==============================================================================
jawab_group = app_commands.Group(
    name="jawab-otomatis",
    description="Balasan otomatis berbasis kata kunci per channel (tanpa kuota AI)",
    guild_only=True,
)


@jawab_group.command(name="tambah", description="Tambahkan aturan balasan otomatis di channel ini")
@app_commands.describe(
    pemicu="Kata/frasa pemicu, misal: cara daftar",
    balasan="Isi balasan bot ketika pemicu muncul",
    persis="True bila harus sama persis (bukan sekadar mengandung kata pemicu)",
    channel="Channel/thread tujuan (default: channel ini)",
)
async def jawab_tambah_cmd(
    interaction: discord.Interaction,
    pemicu: str,
    balasan: str,
    persis: bool = False,
    channel: discord.TextChannel | discord.Thread | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = _resolve_text_channel(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih `channel` untuk aturan ini.", ephemeral=True)
        return

    trigger = str(pemicu or "").strip()
    if len(trigger) < 3:
        await interaction.response.send_message(
            "⚠️ Pemicu minimal **3 karakter** agar tidak memicu percakapan biasa.", ephemeral=True
        )
        return

    status, cfg = engagement.add_auto_reply(
        target.id,
        interaction.guild.id,
        trigger,
        balasan,
        mode="persis" if persis else "kata",
        max_rules=AUTO_REPLY_MAX_RULES,
    )
    if status == "kosong":
        await interaction.response.send_message("⚠️ Pemicu & balasan tidak boleh kosong.", ephemeral=True)
        return
    if status == "duplikat":
        await interaction.response.send_message(
            "ℹ️ Aturan dengan pemicu itu sudah ada. Hapus dulu dengan `/jawab-otomatis hapus`.",
            ephemeral=True,
        )
        return
    if status == "penuh":
        await interaction.response.send_message(
            f"⚠️ Batas **{AUTO_REPLY_MAX_RULES} aturan** per channel sudah tercapai.", ephemeral=True
        )
        return

    await engagement.save_engagement_to_disk()
    total = len((cfg or {}).get("rules") or [])
    await interaction.response.send_message(
        f"✅ Aturan ditambahkan di {target.mention}: **{trigger}** ➔ balasan tersimpan "
        f"(`{total}/{AUTO_REPLY_MAX_RULES}` aturan).\n"
        f"Jeda aman antar-balasan: `{AUTO_REPLY_COOLDOWN_SEC}` detik agar channel tidak dibanjiri.",
        ephemeral=True,
    )


@jawab_group.command(name="hapus", description="Hapus satu aturan balasan otomatis berdasarkan pemicunya")
@app_commands.describe(pemicu="Kata pemicu aturan yang ingin dihapus", channel="Channel aturan (default: channel ini)")
async def jawab_hapus_cmd(
    interaction: discord.Interaction,
    pemicu: str,
    channel: discord.TextChannel | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = _resolve_text_channel(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih channel.", ephemeral=True)
        return

    if not engagement.remove_auto_reply(target.id, pemicu):
        await interaction.response.send_message(
            f"⚠️ Tidak ada aturan dengan pemicu **{str(pemicu)[:80]}** di {target.mention}.",
            ephemeral=True,
        )
        return

    await engagement.save_engagement_to_disk()
    await interaction.response.send_message("🗑️ Aturan dihapus.", ephemeral=True)


@jawab_group.command(name="daftar", description="Lihat seluruh aturan balasan otomatis di channel ini")
@app_commands.describe(channel="Channel yang ingin dilihat (default: channel ini)")
async def jawab_daftar_cmd(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
    if interaction.guild is None:
        return
    target = _resolve_text_channel(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih channel.", ephemeral=True)
        return

    cfg = engagement.auto_reply_channels.get(target.id)
    if not cfg or not (cfg.get("rules") or []):
        await interaction.response.send_message(
            f"ℹ️ Belum ada aturan di {target.mention}. Tambah dengan `/jawab-otomatis tambah`.",
            ephemeral=True,
        )
        return

    status = "✅ aktif" if cfg.get("enabled", True) else "⛔ nonaktif"
    embed = discord.Embed(
        title="🤖 Balasan Otomatis",
        description=f"{target.mention} • {status} • jeda `{cfg.get('cooldown', 0)}` detik",
        color=discord.Color.teal(),
    )
    for idx, rule in enumerate(cfg["rules"][:20], start=1):
        mode = "persis" if rule.get("mode") == "persis" else "mengandung"
        embed.add_field(
            name=f"{idx}. {rule['trigger']} ({mode})",
            value=str(rule.get("reply") or "")[:300],
            inline=False,
        )
    embed.set_footer(text=f"Total {len(cfg['rules'])} aturan • maksimal {AUTO_REPLY_MAX_RULES} per channel")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@jawab_group.command(name="atur", description="Aktifkan/nonaktifkan balasan otomatis & atur jeda aman")
@app_commands.describe(
    channel="Channel yang diatur (default: channel ini)",
    aktif="False untuk mematikan tanpa menghapus aturan",
    jeda="Jeda minimum antar-balasan dalam detik (0-300)",
)
async def jawab_atur_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    aktif: bool = True,
    jeda: int | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = _resolve_text_channel(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih channel.", ephemeral=True)
        return

    engagement.set_auto_reply_config(
        target.id,
        interaction.guild.id,
        enabled=aktif,
        cooldown=int(jeda) if jeda is not None else None,
    )
    await engagement.save_engagement_to_disk()
    cfg = engagement.auto_reply_channels.get(target.id) or {}
    await interaction.response.send_message(
        f"{'✅ Aktif' if aktif else '⛔ Nonaktif'} di {target.mention} • "
        f"jeda `{cfg.get('cooldown', AUTO_REPLY_COOLDOWN_SEC)}` detik • "
        f"`{len(cfg.get('rules') or [])}` aturan.",
        ephemeral=True,
    )


# ==============================================================================
# /pengumuman
# ==============================================================================
pengumuman_group = app_commands.Group(
    name="pengumuman",
    description="Pengumuman terjadwal: harian, mingguan, sekali, atau berulang tiap N jam",
    guild_only=True,
)


@pengumuman_group.command(name="tambah", description="Jadwalkan pengumuman baru")
@app_commands.describe(
    isi="Isi pengumuman — boleh pakai variabel `{server.name}`, `{server.members}`, `{now_relative}`",
    jadwal=(
        "`08:00` (harian), `senin 19:00` (mingguan), "
        "`sekali 31-12-2026 23:59`, `setiap 3 jam` (berulang, min. 2 jam)"
    ),
    judul="Judul pengumuman (opsional)",
    channel="Channel/thread tujuan (default: channel ini)",
)
async def pengumuman_tambah_cmd(
    interaction: discord.Interaction,
    isi: str,
    jadwal: str,
    judul: str | None = None,
    channel: discord.TextChannel | discord.Thread | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    target = _resolve_text_channel(interaction, channel)
    if target is None:
        await interaction.response.send_message("⚠️ Pilih `channel` tujuan.", ephemeral=True)
        return

    spec = engagement.parse_announcement_schedule(jadwal)
    if spec is None:
        await interaction.response.send_message(
            "⚠️ Format jadwal tidak dikenali.\n"
            "• Harian: `08:00` atau `harian 08:00`\n"
            "• Mingguan: `senin 19:00` atau `mingguan sabtu 20:30`\n"
            "• Sekali: `sekali 31-12-2026 23:59`\n"
            "• Berulang: `setiap 3 jam` (minimal 2 jam, maksimal 168 jam)",
            ephemeral=True,
        )
        return

    tz_name = _guild_timezone(interaction.guild.id)
    status, cfg = engagement.add_announcement(
        interaction.guild.id,
        target.id,
        isi,
        spec,
        title=judul or "",
        created_by=interaction.user.id,
        tz_name=tz_name,
        max_items=ANNOUNCEMENT_MAX_PER_GUILD,
    )
    if status == "kosong":
        await interaction.response.send_message("⚠️ Isi pengumuman tidak boleh kosong.", ephemeral=True)
        return
    if status == "penuh":
        await interaction.response.send_message(
            f"⚠️ Batas **{ANNOUNCEMENT_MAX_PER_GUILD} pengumuman** per server sudah tercapai.",
            ephemeral=True,
        )
        return

    await engagement.save_engagement_to_disk()
    tz_label = get_realtime_time_context(tz_name).get("tz_label", "WIB")
    await interaction.response.send_message(
        f"📢 Pengumuman dijadwalkan di {target.mention}\n"
        f"• Jadwal: **{engagement.describe_announcement(cfg)}** ({tz_label})\n"
        f"• Kiriman pertama: {engagement.format_timestamp(cfg['next_run_at'], 'F')}\n"
        f"• ID: `{cfg['id']}` — hapus dengan `/pengumuman hapus id:{cfg['id']}`.",
        ephemeral=True,
    )


@pengumuman_group.command(name="daftar", description="Lihat seluruh pengumuman terjadwal di server ini")
async def pengumuman_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return

    items = engagement.list_announcements(interaction.guild.id)
    if not items:
        await interaction.response.send_message(
            "ℹ️ Belum ada pengumuman terjadwal. Tambah dengan `/pengumuman tambah`.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="📢 Pengumuman Terjadwal",
        color=discord.Color.blurple(),
        description=f"`{len(items)}` pengumuman tersimpan",
    )
    for cfg in items[:15]:
        status = "✅" if cfg.get("enabled") else "⛔"
        next_run = float(cfg.get("next_run_at") or 0)
        when = engagement.format_timestamp(next_run, "R") if next_run else "_selesai_"
        embed.add_field(
            name=f"{status} #{cfg['id']} • {engagement.describe_announcement(cfg)}",
            value=(
                f"<#{cfg['channel_id']}> • berikutnya {when}\n"
                f"> {str(cfg.get('content') or '')[:150]}"
            ),
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@pengumuman_group.command(name="hapus", description="Hapus pengumuman terjadwal berdasarkan ID")
@app_commands.describe(id="ID pengumuman (lihat di /pengumuman daftar)")
async def pengumuman_hapus_cmd(interaction: discord.Interaction, id: int):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not engagement.remove_announcement(int(id), guild_id=interaction.guild.id):
        await interaction.response.send_message(
            f"⚠️ Pengumuman dengan ID `{id}` tidak ditemukan di server ini.", ephemeral=True
        )
        return
    await engagement.save_engagement_to_disk()
    await interaction.response.send_message(f"🗑️ Pengumuman `#{id}` dihapus.", ephemeral=True)


@pengumuman_group.command(name="kirim", description="Kirim pengumuman sekarang juga (jadwal tidak berubah)")
@app_commands.describe(id="ID pengumuman (lihat di /pengumuman daftar)")
async def pengumuman_kirim_cmd(interaction: discord.Interaction, id: int):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    status, cfg = await engagement.send_announcement_now(
        interaction.client, int(id), guild_id=interaction.guild.id
    )
    if status == "tidak_ada":
        await interaction.followup.send(
            f"⚠️ Pengumuman dengan ID `{id}` tidak ditemukan di server ini.", ephemeral=True
        )
        return
    if status == "channel":
        await interaction.followup.send(
            f"⚠️ Gagal mengirim `#{id}` — channel tujuannya hilang atau bot tidak punya izin.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"📤 Pengumuman `#{id}` dikirim ke <#{cfg['channel_id']}>.\n"
        f"-# Jadwal berikutnya tetap: {engagement.format_timestamp(float(cfg['next_run_at'] or 0), 'R')}"
        if float(cfg.get("next_run_at") or 0)
        else f"📤 Pengumuman `#{id}` dikirim. Jadwal sekali-kirim sudah selesai.",
        ephemeral=True,
    )


@pengumuman_group.command(name="ubah", description="Ubah isi / judul / jadwal pengumuman tanpa menghapusnya")
@app_commands.describe(
    id="ID pengumuman",
    isi="Isi baru (boleh variabel `{server.name}`)",
    judul="Judul baru",
    jadwal=(
        "Jadwal baru: `08:00`, `senin 19:00`, `sekali 31-12-2026 23:59`, "
        "atau `setiap 3 jam`"
    ),
)
async def pengumuman_ubah_cmd(
    interaction: discord.Interaction,
    id: int,
    isi: str | None = None,
    judul: str | None = None,
    jadwal: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return
    if isi is None and judul is None and jadwal is None:
        await interaction.response.send_message(
            "⚠️ Isi minimal salah satu: `isi`, `judul`, atau `jadwal`.", ephemeral=True
        )
        return

    spec = None
    if jadwal is not None:
        spec = engagement.parse_announcement_schedule(jadwal)
        if spec is None:
            await interaction.response.send_message(
                "⚠️ Format jadwal tidak dikenali.\n"
                "• Harian: `08:00`\n• Mingguan: `senin 19:00`\n"
                "• Sekali: `sekali 31-12-2026 23:59`\n"
                "• Berulang: `setiap 3 jam` (minimal 2 jam)",
                ephemeral=True,
            )
            return

    status, cfg = engagement.update_announcement(
        int(id),
        guild_id=interaction.guild.id,
        content=isi,
        title=judul,
        spec=spec,
        tz_name=_guild_timezone(interaction.guild.id),
    )
    if status == "tidak_ada":
        await interaction.response.send_message(
            f"⚠️ Pengumuman dengan ID `{id}` tidak ditemukan di server ini.", ephemeral=True
        )
        return
    if status == "kosong":
        await interaction.response.send_message(
            "⚠️ Isi pengumuman tidak boleh kosong — pakai `/pengumuman hapus` bila ingin membuangnya.",
            ephemeral=True,
        )
        return

    await engagement.save_engagement_to_disk()
    keterangan = (
        f"\n• Jadwal: **{engagement.describe_announcement(cfg)}** "
        f"({get_realtime_time_context(_guild_timezone(interaction.guild.id)).get('tz_label', 'WIB')})"
        if spec is not None
        else ""
    )
    await interaction.response.send_message(
        f"✅ Pengumuman `#{id}` diperbarui.{keterangan}\n"
        f"> {str(cfg.get('content') or '')[:200]}",
        ephemeral=True,
    )


@pengumuman_group.command(name="atur", description="Aktifkan/nonaktifkan pengumuman tanpa menghapusnya")
@app_commands.describe(id="ID pengumuman", aktif="False untuk menjeda pengumuman")
async def pengumuman_atur_cmd(interaction: discord.Interaction, id: int, aktif: bool = True):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    if not engagement.set_announcement_enabled(
        int(id), aktif, tz_name=_guild_timezone(interaction.guild.id)
    ):
        await interaction.response.send_message(
            f"⚠️ Pengumuman dengan ID `{id}` tidak ditemukan.", ephemeral=True
        )
        return
    await engagement.save_engagement_to_disk()
    await interaction.response.send_message(
        f"{'✅ Pengumuman diaktifkan lagi' if aktif else '⏸️ Pengumuman dijeda'} (`#{id}`).",
        ephemeral=True,
    )


# ==============================================================================
# REGISTRASI
# ==============================================================================
def register_engagement_cog(bot: commands.Bot) -> None:
    """Mendaftarkan seluruh command engagement ke bot."""
    bot.tree.add_command(giveaway_group)
    bot.tree.add_command(ultah_group)
    bot.tree.add_command(jawab_group)
    bot.tree.add_command(pengumuman_group)
