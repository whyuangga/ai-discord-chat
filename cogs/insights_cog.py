"""Command Tier 3 (hemat kuota AI): `/faq` dan `/pemakaian`.

- `/faq tanya` menjawab **tanpa AI sama sekali** (0 kuota) memakai basis FAQ server
  yang sama dengan yang dipakai `/agent panel`.
- `/pemakaian` menampilkan statistik pemakaian AI hari ini + tren beberapa hari,
  serta cache hit dari `/ringkas channel` (juga 0 kuota).
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import insights
import ui_kit
import ui_theme
from community_agent import (
    MAX_SERVER_KNOWLEDGE_ENTRIES,
    delete_server_knowledge,
    get_server_knowledge_entries,
    save_agent_config_to_disk,
    upsert_server_knowledge,
)
from config import AI_DAILY_CAP_PER_USER, AI_USAGE_KEEP_DAYS, REKAP_CACHE_TTL_SEC

logger = logging.getLogger("gemini_bot.insights_cog")


def _ensure_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


async def _reject_non_admin(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "⚠️ Command ini khusus **Admin / pengelola server**.",
        ephemeral=True,
    )


# ==============================================================================
# /faq — BASIS PENGETAHUAN SERVER (JAWABAN LOKAL, 0 KUOTA)
# ==============================================================================
faq_group = app_commands.Group(
    name="faq",
    description="Basis FAQ server: tanya, lihat, tambah, & hapus (jawaban tanpa kuota AI)",
    guild_only=True,
)


@faq_group.command(name="tanya", description="Cari jawaban dari FAQ server tanpa memakai kuota AI")
@app_commands.describe(pertanyaan="Pertanyaanmu, misal: 'bagaimana cara verifikasi?'")
async def faq_tanya_cmd(interaction: discord.Interaction, pertanyaan: str):
    if interaction.guild is None:
        return

    query = str(pertanyaan or "").strip()
    if len(query) < 3:
        await interaction.response.send_message(
            "⚠️ Tulis pertanyaan minimal 3 karakter.", ephemeral=True
        )
        return

    entries = get_server_knowledge_entries(interaction.guild.id)
    matches = insights.search_faq(entries, query)
    insights.record_ai_usage("faq_local", user_id=interaction.user.id, channel_id=interaction.channel_id, cache_hit=True)
    await insights.save_ai_usage_to_disk()

    embed = insights.build_faq_answer_embed(query, matches)
    embed.set_footer(
        text=(
            "Dijawab tanpa AI (0 kuota) • sumber: basis FAQ server"
            if matches
            else "Tidak memakai AI • minta Admin menambah FAQ lewat /faq tambah"
        )
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@faq_group.command(name="daftar", description="Lihat seluruh entri FAQ/Info server yang tersimpan")
async def faq_daftar_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    entries = get_server_knowledge_entries(interaction.guild.id)
    await interaction.response.send_message(
        embed=insights.build_faq_list_embed(entries, guild_name=interaction.guild.name),
        ephemeral=True,
    )


@faq_group.command(name="tambah", description="Tambah/perbarui entri FAQ server (ikut dipakai AI sebagai konteks)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    topik="Judul singkat, misal: Cara verifikasi",
    isi="Isi jawaban resmi (maks 500 karakter)",
)
async def faq_tambah_cmd(interaction: discord.Interaction, topik: str, isi: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    entry, status = upsert_server_knowledge(interaction.guild.id, topik, isi)
    if status == "empty":
        await interaction.response.send_message(
            "⚠️ Topik & isi tidak boleh kosong.", ephemeral=True
        )
        return
    if status == "full" or entry is None:
        await interaction.response.send_message(
            f"⚠️ Batas **{MAX_SERVER_KNOWLEDGE_ENTRIES} entri** sudah tercapai. "
            "Hapus salah satu dulu dengan `/faq hapus`.",
            ephemeral=True,
        )
        return

    await save_agent_config_to_disk()
    total = len(get_server_knowledge_entries(interaction.guild.id))
    await interaction.response.send_message(
        (
            f"✅ FAQ **diperbarui**: **{entry['topic']}**"
            if status == "updated"
            else f"✅ FAQ **ditambahkan**: **{entry['topic']}**"
        )
        + f"\n• Total entri: `{total}/{MAX_SERVER_KNOWLEDGE_ENTRIES}`\n"
        f"> Entri ini menjawab lewat `/faq tanya` **tanpa kuota AI**, dan juga dipakai "
        f"AI sebagai konteks resmi saat member bertanya.",
        ephemeral=True,
    )


@faq_group.command(name="hapus", description="Hapus entri FAQ berdasarkan nomor urut atau nama topik")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(target="Nomor urut (lihat /faq daftar) atau nama topik")
async def faq_hapus_cmd(interaction: discord.Interaction, target: str):
    if interaction.guild is None:
        return
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    removed = delete_server_knowledge(interaction.guild.id, target)
    if removed is None:
        await interaction.response.send_message(
            f"⚠️ Tidak menemukan FAQ dengan topik/nomor **{str(target)[:80]}**.", ephemeral=True
        )
        return

    await save_agent_config_to_disk()
    await interaction.response.send_message(
        f"🗑️ FAQ **{removed.get('topic', '-')}** dihapus. "
        f"Sisa `{len(get_server_knowledge_entries(interaction.guild.id))}` entri.",
        ephemeral=True,
    )


# ==============================================================================
# /pemakaian — STATISTIK PEMAKAIAN AI (0 KUOTA)
# ==============================================================================
pemakaian_group = app_commands.Group(
    name="pemakaian",
    description="Statistik pemakaian kuota AI bot (tanpa memanggil AI sama sekali)",
    guild_only=True,
)


def build_usage_panel(guild_id: int | None) -> discord.ui.LayoutView:
    """Panel pemakaian AI bergaya kartu (Components V2, 0 kuota AI)."""
    key = insights.today_key()
    bucket = insights.ai_usage.get(key) or insights._empty_bucket()
    total = int(bucket.get("total") or 0)
    hits = int(bucket.get("cache_hits") or 0)
    cap_text = (
        f"`{AI_DAILY_CAP_PER_USER}` operasi/hari per member"
        if AI_DAILY_CAP_PER_USER > 0
        else "_tanpa batas harian_"
    )
    kinds = insights._top_items(bucket.get("kinds") or {}, limit=8)
    users = insights._top_items(bucket.get("users") or {}, limit=5)
    channels = insights._top_items(bucket.get("channels") or {}, limit=5)

    header = ui_kit.text(
        ui_kit.title_line(
            guild_id,
            "insights",
            "Pemakaian AI Hari Ini",
            f"`{key}` • {cap_text}",
        )
    )
    hero = ui_kit.text(
        "\n".join(
            [
                ui_kit.status_line("Operasi AI", f"**{total}**", state="warn" if total > 200 else "on"),
                ui_kit.status_line("Cache hit (hemat kuota)", f"**{hits}**", state="on"),
                ui_kit.status_line("Efisiensi cache", ui_kit.progress_bar(hits, max(1, total)), state="on"),
            ]
        )
    )
    kind_text = (
        "\n".join(f"• {insights.AI_KIND_LABELS.get(n, n)}: **{c}**" for n, c in kinds)
        or "_belum ada pemakaian AI hari ini_"
    )
    people_text = "\n".join(f"• <@{uid}>: **{c}** operasi" for uid, c in users) or "_belum ada data member_"
    channel_text = "\n".join(f"• <#{cid}>: **{c}** operasi" for cid, c in channels) or "_belum ada data channel_"

    body = ui_kit.card(
        guild_id,
        header,
        ui_kit.sep(),
        hero,
        ui_kit.sep(),
        ui_kit.text(ui_kit.field_block("🧩 Jenis Operasi", kind_text.split("\n"))),
        ui_kit.text(ui_kit.field_block("👥 Member Paling Aktif", people_text.split("\n"))),
        ui_kit.text(ui_kit.field_block("📍 Channel Paling Ramai", channel_text.split("\n"))),
        ui_kit.sep(),
        ui_kit.action_row(
            ui_kit.button(
                "Tren 7 Hari",
                emoji="📈",
                custom_id="usage:trend",
                callback=_usage_trend_callback,
            ),
            ui_kit.button(
                "Dashboard",
                emoji=ui_theme.emoji(guild_id, "panel", "🛰️"),
                style=discord.ButtonStyle.primary,
                custom_id="usage:dashboard",
                callback=_usage_dashboard_callback,
            ),
        ),
        ui_kit.text(f"-# {ui_theme.footer_text(guild_id, 'Statistik dihitung lokal — tanpa memanggil Gemini') or 'Statistik lokal • 0 kuota'}"),
    )
    return ui_kit.build_view(guild_id, body, timeout=300)


async def _usage_trend_callback(interaction: discord.Interaction) -> None:
    days = max(1, min(int(AI_USAGE_KEEP_DAYS), 7))
    await interaction.response.edit_message(
        embed=insights.build_usage_history_embed(days),
        view=None,
    )


async def _usage_dashboard_callback(interaction: discord.Interaction) -> None:
    from cogs.panel_cog import dashboard_embed, make_dashboard

    if interaction.guild is None:
        await interaction.response.send_message(
            "ℹ️ Dashboard hanya tersedia di dalam server.", ephemeral=True
        )
        return
    await ui_kit.edit_panel(
        interaction,
        make_dashboard(interaction.guild, "insights", interaction.user.id),
        embed=dashboard_embed(interaction.guild, "insights"),
    )


@pemakaian_group.command(name="lihat", description="Pemakaian AI hari ini: jenis operasi, member, & channel tersibuk")
async def pemakaian_lihat_cmd(interaction: discord.Interaction):
    guild_id = interaction.guild.id if interaction.guild else None
    await ui_kit.send_panel(
        interaction,
        build_usage_panel(guild_id),
        embed=insights.build_usage_embed(),
        ephemeral=True,
    )


@pemakaian_group.command(name="tren", description="Tren pemakaian AI beberapa hari terakhir")
@app_commands.describe(hari=f"Berapa hari ditampilkan (1–{AI_USAGE_KEEP_DAYS})")
async def pemakaian_tren_cmd(interaction: discord.Interaction, hari: int = 7):
    days = max(1, min(int(AI_USAGE_KEEP_DAYS), int(hari)))
    await interaction.response.send_message(
        embed=insights.build_usage_history_embed(days), ephemeral=True
    )


@pemakaian_group.command(name="status", description="Ringkasan penghematan kuota: cache rekap, FAQ lokal, & batas harian")
async def pemakaian_status_cmd(interaction: discord.Interaction):
    bucket = insights.ai_usage.get(insights.today_key()) or {}
    total = int(bucket.get("total") or 0)
    hits = int(bucket.get("cache_hits") or 0)
    entries = len(get_server_knowledge_entries(interaction.guild.id)) if interaction.guild else 0
    saved = hits
    await interaction.response.send_message(
        f"♻️ **Ringkasan Hemat Kuota**\n"
        f"• **Operasi AI hari ini:** `{total}`\n"
        f"• **Cache hit (tanpa AI):** `{saved}` → menghemat `{saved}` panggilan\n"
        f"• **Batas harian per member:** "
        + (f"`{AI_DAILY_CAP_PER_USER}` operasi" if AI_DAILY_CAP_PER_USER > 0 else "_tanpa batas_")
        + f"\n• **Cache rekap `/ringkas channel`:** `{REKAP_CACHE_TTL_SEC // 60}` menit\n"
        f"• **FAQ lokal server:** `{entries}` entri (dijawab tanpa AI)\n"
        f"> Tips hemat: pakai `/ringkas channel` berulang (cache), `/faq tanya` untuk info server, "
        f"dan `/ringkas chat` hanya saat perlu.",
        ephemeral=True,
    )


@pemakaian_group.command(name="reset", description="Bersihkan catatan pemakaian AI hari ini & cache rekap (Admin)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(cache_rekap="True = sekalian kosongkan cache rekap channel")
async def pemakaian_reset_cmd(interaction: discord.Interaction, cache_rekap: bool = True):
    if not _ensure_admin(interaction):
        await _reject_non_admin(interaction)
        return

    removed_days = insights.reset_all_usage()
    removed_cache = insights.reset_rekap_cache() if cache_rekap else 0
    await insights.save_ai_usage_to_disk()

    await interaction.response.send_message(
        f"🧹 **Catatan pemakaian AI dibersihkan.**\n"
        f"• Hari terhapus: `{removed_days}`\n"
        f"• Cache rekap dikosongkan: `{removed_cache}` entri\n"
        f"> Statistik mulai dihitung ulang dari nol. Data tingkat server (FAQ, level, tiket) **tidak** tersentuh.",
        ephemeral=True,
    )


def register_insights_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command /faq & /pemakaian ke bot."""
    bot.tree.add_command(faq_group)
    bot.tree.add_command(pemakaian_group)
