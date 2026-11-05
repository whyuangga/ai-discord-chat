"""Slash `/ekonomi` — koin server, hadiah harian, toko role, & transfer (0 kuota AI).

Semua angka dihitung lokal dari aktivitas chat & voice; tidak ada panggilan Gemini.
Fitur **default NONAKTIF** sampai Admin menjalankan `/ekonomi atur aktif:True`.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import economy
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.economy_cog")

ekonomi_group = app_commands.Group(
    name="ekonomi",
    description="Koin server: saldo, hadiah harian, toko role, & transfer (0 kuota AI)",
    guild_only=True,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(
        perms
        and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))
    )


# ==============================================================================
# MEMBER
# ==============================================================================
@ekonomi_group.command(name="saldo", description="Lihat saldo koin kamu (atau member lain)")
@app_commands.describe(member="Member yang ingin dilihat saldonya")
async def ekonomi_saldo_cmd(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not economy.is_active(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "warn",
                "Ekonomi belum aktif",
                "Admin bisa menyalakannya dengan `/ekonomi atur aktif:True`.",
            ),
            ephemeral=True,
        )
        return

    target = member or interaction.user
    cfg = economy.get_config(gid)
    saldo = economy.balance(gid, target.id)
    rank = next(
        (idx + 1 for idx, (uid, _v) in enumerate(economy.leaderboard(gid, limit=10_000)) if uid == target.id),
        None,
    )
    siap = economy.daily_ready_in(gid, target.id) if target.id == interaction.user.id else 0
    lines = [
        economy.format_coins(saldo, cfg),
        "• Peringkat: " + (f"`#{rank}`" if rank else "_belum masuk papan_"),
    ]
    if target.id == interaction.user.id:
        lines.append(
            "• Hadiah harian: "
            + ("**siap diklaim** (`/ekonomi harian`)" if siap == 0 else f"tersedia lagi dalam `{siap // 3600}j {siap % 3600 // 60}m`")
        )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid, "info", f"💰 Saldo {target.display_name}", "\n".join(lines)
        ),
        ephemeral=True,
    )


@ekonomi_group.command(name="papan", description="Papan peringkat member paling kaya di server")
async def ekonomi_papan_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not economy.is_active(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Ekonomi belum aktif", "`/ekonomi atur aktif:True`."),
            ephemeral=True,
        )
        return

    cfg = economy.get_config(gid)
    rows = economy.leaderboard(gid, limit=10)
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    body = (
        "\n".join(
            f"{medals.get(idx, f'`{idx + 1}.`')} <@{uid}> — {economy.format_coins(value, cfg)}"
            for idx, (uid, value) in enumerate(rows)
        )
        or "_Belum ada member yang punya koin._"
    )
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "🏦 Papan Kekayaan Server",
            body + f"\n\n-# Total koin beredar: `{economy.net_worth(gid):,}`",
        ),
        ephemeral=True,
    )


@ekonomi_group.command(name="harian", description="Klaim hadiah koin harian (bonus makin rajin klaim)")
async def ekonomi_harian_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not economy.is_active(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Ekonomi belum aktif", "`/ekonomi atur aktif:True`."),
            ephemeral=True,
        )
        return

    ok, amount, streak = economy.claim_daily(gid, interaction.user.id)
    cfg = economy.get_config(gid)
    if not ok:
        sisa = economy.daily_ready_in(gid, interaction.user.id)
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "info",
                "Hadiah harian sudah diklaim",
                f"Kamu sudah mengambil hadiah hari ini (streak `{streak}` hari).\n"
                f"Tersedia lagi dalam `{sisa // 3600}j {sisa % 3600 // 60}m`.",
            ),
            ephemeral=True,
        )
        return

    await economy.save_economy_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Hadiah harian diterima",
            f"Kamu mendapat {economy.format_coins(amount, cfg)}!\n"
            f"• Streak: `{streak}` hari (bonus naik tiap hari berturut-turut)\n"
            f"• Saldo sekarang: {economy.format_coins(economy.balance(gid, interaction.user.id), cfg)}",
        ),
        ephemeral=True,
    )


@ekonomi_group.command(name="toko", description="Lihat item toko server (role yang bisa dibeli dengan koin)")
async def ekonomi_toko_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not economy.is_active(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Ekonomi belum aktif", "`/ekonomi atur aktif:True`."),
            ephemeral=True,
        )
        return

    cfg = economy.get_config(gid)
    bucket = economy.items(gid)
    if not bucket:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "info",
                "Toko masih kosong",
                "Admin bisa menambah item dengan `/ekonomi tambah-item nama:... harga:... role:@...`.",
            ),
            ephemeral=True,
        )
        return

    lines = []
    for item in sorted(bucket.values(), key=lambda it: int(it.get("price") or 0)):
        role = f" → <@&{item['role_id']}>" if item.get("role_id") else ""
        desc = f" — {item['description']}" if item.get("description") else ""
        lines.append(f"• **{item['name']}** — {economy.format_coins(int(item['price']), cfg)}{role}{desc}")
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "🛒 Toko Server",
            "\n".join(lines)[:3500] + "\n\n-# Beli dengan `/ekonomi beli item:<nama>`",
        ),
        ephemeral=True,
    )


@ekonomi_group.command(name="beli", description="Beli item toko dengan koin kamu")
@app_commands.describe(item="Nama item yang ingin dibeli (lihat /ekonomi toko)")
async def ekonomi_beli_cmd(interaction: discord.Interaction, item: str):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not economy.is_active(gid):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "warn", "Ekonomi belum aktif", "`/ekonomi atur aktif:True`."),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, message, role_id = economy.buy(gid, interaction.user.id, item)
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Pembelian gagal", message),
            follow=True,
            ephemeral=True,
        )
        return

    await economy.save_economy_to_disk()
    granted = ""
    if role_id:
        role = interaction.guild.get_role(int(role_id))
        if role is not None:
            try:
                await interaction.user.add_roles(role, reason="Pembelian item toko koin")
                granted = f"\nRole {role.mention} sudah ditambahkan ke akunmu."
            except (discord.Forbidden, discord.HTTPException):
                granted = "\n⚠️ Bot tidak punya izin memberi role itu — hubungi Admin."
        else:
            granted = "\n⚠️ Role hadiah sudah dihapus dari server."

    cfg = economy.get_config(gid)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Pembelian berhasil",
            f"{message}{granted}\nSisa saldo: {economy.format_coins(economy.balance(gid, interaction.user.id), cfg)}",
        ),
        follow=True,
        ephemeral=True,
    )


@ekonomi_group.command(name="transfer", description="Kirim koin ke member lain")
@app_commands.describe(member="Penerima koin", jumlah="Jumlah koin yang dikirim")
async def ekonomi_transfer_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    jumlah: app_commands.Range[int, 10, 1_000_000],
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    ok, message = economy.transfer(gid, interaction.user.id, member.id, int(jumlah))
    if not ok:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Transfer gagal", message),
            ephemeral=True,
        )
        return

    await economy.save_economy_to_disk()
    cfg = economy.get_config(gid)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Transfer berhasil",
            f"{message}\n"
            f"Penerima: {member.mention}\n"
            f"Saldo kamu: {economy.format_coins(economy.balance(gid, interaction.user.id), cfg)}",
        ),
        ephemeral=True,
    )


# ==============================================================================
# ADMIN
# ==============================================================================
@ekonomi_group.command(name="atur", description="Aktifkan & atur ekonomi server (Admin)")
@app_commands.describe(
    aktif="True untuk mengaktifkan ekonomi, False untuk mematikan",
    koin_per_pesan="Koin yang didapat tiap pesan (0 = matikan)",
    jeda="Jeda antar-pesan yang menghasilkan koin (detik)",
    koin_per_menit_voice="Koin per menit berada di voice channel",
    hadiah_harian="Jumlah koin hadiah harian",
    mata_uang="Nama mata uang (mis. koin, emas, kredit)",
)
async def ekonomi_atur_cmd(
    interaction: discord.Interaction,
    aktif: bool | None = None,
    koin_per_pesan: app_commands.Range[int, 0, 100] | None = None,
    jeda: app_commands.Range[int, 0, 3600] | None = None,
    koin_per_menit_voice: app_commands.Range[int, 0, 100] | None = None,
    hadiah_harian: app_commands.Range[int, 0, 100000] | None = None,
    mata_uang: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server*."
            ),
            ephemeral=True,
        )
        return

    changes = {
        "aktif": aktif,
        "per_message": koin_per_pesan,
        "cooldown": jeda,
        "per_voice_min": koin_per_menit_voice,
        "daily_amount": hadiah_harian,
        "mata_uang": mata_uang,
    }
    if any(v is not None for v in changes.values()):
        economy.set_config(gid, **changes)
        await economy.save_economy_to_disk()

    cfg = economy.get_config(gid)
    state = "✅ aktif" if cfg.get("enabled") else "⛔ nonaktif"
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if cfg.get("enabled") else "info",
            "Pengaturan Ekonomi",
            f"Status: **{state}**\n"
            f"• Koin per pesan: `{cfg['per_message']}` (jeda `{cfg['cooldown']}` dtk)\n"
            f"• Koin per menit voice: `{cfg['per_voice_min']}`\n"
            f"• Hadiah harian: `{cfg['daily_amount']}` (streak bonus s.d. +70%)\n"
            f"• Mata uang: {cfg['emoji']} `{cfg['currency']}`",
        ),
        ephemeral=True,
    )


@ekonomi_group.command(name="tambah-item", description="Tambah/ubah item toko (Admin)")
@app_commands.describe(
    nama="Nama item yang dilihat member",
    harga="Harga dalam koin",
    role="Role yang otomatis diberikan saat item dibeli",
    deskripsi="Keterangan singkat (opsional)",
)
async def ekonomi_tambah_item_cmd(
    interaction: discord.Interaction,
    nama: str,
    harga: app_commands.Range[int, 1, 10_000_000],
    role: discord.Role | None = None,
    deskripsi: str | None = None,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server*."),
            ephemeral=True,
        )
        return

    item, status = economy.add_item(
        gid, nama, int(harga), role_id=role.id if role else None, description=deskripsi or ""
    )
    if item is None:
        reason = (
            f"Toko sudah mencapai batas `{economy.MAX_ITEMS}` item."
            if status == "full"
            else "Nama item tidak valid."
        )
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Item gagal ditambahkan", reason),
            ephemeral=True,
        )
        return

    await economy.save_economy_to_disk()
    cfg = economy.get_config(gid)
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Item toko disimpan" if status == "added" else "Item toko diperbarui",
            f"**{item['name']}** — {economy.format_coins(item['price'], cfg)}"
            + (f"\nHadiah role: <@&{item['role_id']}>" if item.get("role_id") else "")
            + (f"\n_{item['description']}_" if item.get("description") else ""),
        ),
        ephemeral=True,
    )


@ekonomi_group.command(name="hapus-item", description="Hapus item toko (Admin)")
@app_commands.describe(nama="Nama item yang dihapus")
async def ekonomi_hapus_item_cmd(interaction: discord.Interaction, nama: str):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    if not _is_admin(interaction):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server*."),
            ephemeral=True,
        )
        return

    item = economy.find_item(gid, nama)
    removed = economy.remove_item(gid, item["id"]) if item else False
    if removed:
        await economy.save_economy_to_disk()
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok" if removed else "info",
            "Item dihapus" if removed else "Item tidak ditemukan",
            f"**{item['name']}** sudah dihapus dari toko." if removed and item else "Periksa nama item lewat `/ekonomi toko`.",
        ),
        ephemeral=True,
    )


def register_economy_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/ekonomi` ke bot."""
    bot.tree.add_command(ekonomi_group)
