"""Cog `/sosial` — notifikasi YouTube, Twitch, & TikTok/RSS (0 kuota AI)."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import social_notify as sn
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.social_cog")

sosial_group = app_commands.Group(
    name="sosial",
    description="Notifikasi otomatis YouTube, Twitch, & TikTok/RSS ke channel (0 kuota AI)",
    default_permissions=discord.Permissions(administrator=True),
    guild_only=True,
)


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
    )


def _platform_choices() -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=f"{meta['emoji']} {meta['label']}", value=key)
        for key, meta in sn.PLATFORMS.items()
    ]


@sosial_group.command(
    name="tambah",
    description="Pantau YouTube/Twitch/TikTok lalu kirim notifikasi otomatis ke channel",
)
@app_commands.describe(
    platform="Platform yang dipantau",
    target="YouTube: @handle/UC… • Twitch: login • TikTok/RSS: URL feed",
    channel="Channel tempat notifikasi dikirim",
    role="Role yang di-ping saat ada notifikasi (opsional)",
    pesan="Template kustom: {source} {title} {url} {game} (isi - untuk kembali ke bawaan)",
)
@app_commands.choices(platform=_platform_choices())
async def sosial_tambah_cmd(
    interaction: discord.Interaction,
    platform: app_commands.Choice[str],
    target: str,
    channel: discord.TextChannel,
    role: discord.Role | None = None,
    pesan: str | None = None,
):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        return await _reject_non_admin(interaction)

    if platform.value == "twitch" and not sn.twitch_configured():
        await interaction.response.send_message(
            "⚠️ **Twitch belum dikonfigurasi.** Isi `TWITCH_CLIENT_ID` & `TWITCH_CLIENT_SECRET` "
            "di variabel Wispbyte (aplikasi gratis dari https://dev.twitch.tv/console/apps), lalu restart.\n"
            "YouTube & TikTok/RSS tetap bisa dipakai tanpa kredensial.",
            ephemeral=True,
        )
        return

    try:
        sub = sn.add_subscription(
            interaction.guild.id,
            platform.value,
            target,
            channel.id,
            role_id=role.id if role else None,
            template=pesan,
        )
    except ValueError as exc:
        await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
        return

    await sn.save_social_to_disk()
    await interaction.response.defer(ephemeral=True)

    # Langsung cek sekali agar Admin tahu hasilnya (item lama tidak dikirim).
    note = "🕒 Pemeriksaan pertama menandai konten lama sebagai *sudah dilihat* agar channel tidak dibanjiri."
    try:
        session = interaction.client.http_session
        guild = interaction.guild
        posted = await sn.check_subscription(interaction.client, guild, sub, session)
        await sn.save_social_to_disk()
        if platform.value == "twitch":
            note = "🔴 Notifikasi dikirim saat streamer mulai live." if not posted else "🔴 Streamer sedang live — notifikasi sudah dikirim."
        elif posted:
            note = f"📨 Langsung mengirim **{posted}** notifikasi baru."
        else:
            note = "✅ Belum ada konten baru. Notifikasi muncul otomatis di pengecekan berikutnya (≤5 menit)."
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.info("Pemeriksaan awal gagal: %s", exc)

    meta = sn.PLATFORMS[platform.value]
    body = (
        f"### {meta['emoji']} Langganan Ditambahkan\n"
        f"• **Platform:** {meta['label']}\n"
        f"• **Target:** `{sub['target']}`\n"
        f"• **Channel:** <#{channel.id}>\n"
        f"• **Ping role:** {role.mention if role else '_tidak ada_'}\n"
        f"• **ID langganan:** `{sub['id']}`\n\n{note}"
    )
    await ui_kit.follow_panel(
        interaction,
        ui_kit.build_view(interaction.guild.id, ui_kit.card(interaction.guild.id, ui_kit.text(body)), timeout=None),
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🔔 Notifikasi Sosial", description=body), interaction.guild.id
        ),
        ephemeral=True,
    )


@sosial_group.command(name="daftar", description="Lihat semua langganan notifikasi di server ini")
async def sosial_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    subs = sn.get_subscriptions(interaction.guild.id)
    if not subs:
        await interaction.response.send_message(
            "ℹ️ Belum ada langganan. Tambahkan dengan `/sosial tambah`.\n"
            "Contoh: `/sosial tambah platform:🎬 YouTube target:@NamaChannel channel:#info`",
            ephemeral=True,
        )
        return

    lines = [sn.summarize_subscription(sub) for sub in subs]
    lines.append(
        f"\n_Pantau: id channel YouTube & feed RSS setiap ≤{sn.PLATFORM_INTERVAL['youtube'] // 60} menit, "
        f"Twitch setiap {sn.PLATFORM_INTERVAL['twitch'] // 60} menit • 0 kuota AI_"
    )
    body = "### 🔔 Langganan Notifikasi\n" + "\n".join(lines)[:3500]
    await ui_kit.follow_panel(
        interaction,
        ui_kit.build_view(interaction.guild.id, ui_kit.card(interaction.guild.id, ui_kit.text(body)), timeout=None),
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🔔 Langganan Notifikasi", description=body[:4000]), interaction.guild.id
        ),
        ephemeral=True,
    )


@sosial_group.command(
    name="status",
    description="Cek kesiapan notifikasi: kredensial Twitch, token, & jumlah langganan per platform",
)
async def sosial_status_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    await interaction.response.defer(ephemeral=True)

    try:
        info = await sn.diagnose(interaction.client.http_session)
    except Exception as exc:  # pragma: no cover - jaring aman
        await interaction.followup.send(f"⚠️ Gagal memeriksa status: {exc}", ephemeral=True)
        return

    if info["twitch_token_ok"]:
        twitch_line = "✅ Siap — kredensial valid & token berhasil diambil"
    elif info["twitch_configured"]:
        twitch_line = f"⚠️ Kredensial terisi, tetapi token gagal: {info['twitch_error']}"
    else:
        twitch_line = f"➖ Belum aktif — {info['twitch_error']}"

    counts = info["counts"]
    body = (
        "### 🔔 Status Notifikasi Sosial\n"
        f"• 🎬 **YouTube** — ✅ siap (RSS publik, tanpa kredensial) • langganan: `{counts.get('youtube', 0)}`\n"
        f"• 🟣 **Twitch** — {twitch_line} • langganan: `{counts.get('twitch', 0)}`\n"
        f"• 🎵 **TikTok/RSS** — ✅ siap (URL feed) • langganan: `{counts.get('tiktok', 0)}`\n"
        f"\n**Cara mengisi kredensial Twitch (sekali saja):**\n"
        "1. Buka https://dev.twitch.tv/console/apps → **Register Your Application**\n"
        "2. Nama bebas, *OAuth Redirect URLs*: `http://localhost`, *Category*: `Bot` → **Create**\n"
        "3. Salin **Client ID** → **New Secret** lalu salin **Client Secret**\n"
        "4. Wispbyte → tab **Variables/Startup** → tambahkan `TWITCH_CLIENT_ID` & `TWITCH_CLIENT_SECRET` → **Restart**\n"
        "5. Jalankan `/sosial status` lagi sampai muncul ✅, lalu uji `/sosial tes id:...`"
    )
    if info["total"] == 0:
        body += "\n\n_Belum ada langganan. Tambahkan dengan `/sosial tambah`._"

    await ui_kit.follow_panel(
        interaction,
        ui_kit.build_view(interaction.guild.id, ui_kit.card(interaction.guild.id, ui_kit.text(body)), timeout=None),
        embed=ui_theme.apply_embed_theme(
            discord.Embed(title="🔔 Status Notifikasi Sosial", description=body[:4000]),
            interaction.guild.id,
        ),
        ephemeral=True,
    )


@sosial_group.command(name="hapus", description="Hentikan pemantauan salah satu langganan")
@app_commands.describe(id="ID langganan (lihat di /sosial daftar)")
async def sosial_hapus_cmd(interaction: discord.Interaction, id: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        return await _reject_non_admin(interaction)

    sub = sn.find_subscription(interaction.guild.id, id)
    removed = sn.remove_subscription(interaction.guild.id, id)
    await sn.save_social_to_disk()
    await interaction.response.send_message(
        (
            f"🗑️ Langganan `{id}` (**{sub.get('target')}**) dihentikan."
            if removed
            else f"⚠️ Tidak ada langganan dengan ID `{id}`. Cek `/sosial daftar`."
        ),
        ephemeral=True,
    )


@sosial_group.command(name="tes", description="Kirim contoh notifikasi sekarang (uji tanpa menunggu jadwal)")
@app_commands.describe(id="ID langganan yang ingin diuji")
async def sosial_tes_cmd(interaction: discord.Interaction, id: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        return await _reject_non_admin(interaction)

    sub = sn.find_subscription(interaction.guild.id, id)
    if sub is None:
        await interaction.response.send_message(
            f"⚠️ Tidak ada langganan dengan ID `{id}`. Cek `/sosial daftar`.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    session = interaction.client.http_session
    try:
        posted = await sn.check_subscription(
            interaction.client, interaction.guild, sub, session, force=True
        )
    except Exception as exc:  # pragma: no cover - jaring aman
        await interaction.followup.send(f"⚠️ Gagal menguji langganan: {exc}", ephemeral=True)
        return
    await sn.save_social_to_disk()

    if posted:
        await interaction.followup.send(
            f"📨 Contoh notifikasi dikirim ke <#{sub['channel_id']}>.", ephemeral=True
        )
    else:
        hint = (
            "Pastikan `TWITCH_CLIENT_ID` & `TWITCH_CLIENT_SECRET` terisi dan streamer sedang live."
            if sub.get("platform") == "twitch"
            else "Pastikan feed bisa diakses bot (URL benar & tidak diblokir)."
        )
        await interaction.followup.send(f"⚠️ Tidak ada konten yang bisa dikirim. {hint}", ephemeral=True)


def register_social_cog(bot: commands.Bot) -> None:
    """Mendaftarkan group `/sosial` ke bot."""
    bot.tree.add_command(sosial_group)


__all__ = ["register_social_cog", "sosial_group"]
