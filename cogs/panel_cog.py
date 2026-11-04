"""Control Center (`/panel`) & Editor Tampilan (`/tampilan`) — 0 kuota AI.

`/panel` adalah **dashboard** bergaya panel web hosting di dalam Discord:
kartu status per kategori, navigasi tab, dan tombol aksi cepat.

`/tampilan` membuat bot bisa di-*branding* per server: warna aksen, emoji pack,
kepadatan, thumbnail, footer, konfirmasi, hingga gaya navigasi.
"""

import logging
import time

import discord
from discord import app_commands, ui
from discord.ext import commands

import antispam
import community_agent
import community_tools
import engagement
import insights
import levels as levels_mod
import music
import server_features
import tickets as tickets_mod
import ui_kit
import ui_theme
from cogs.helpers import get_memory_usage_mb
from config import BOT_VERSION, REKAP_CACHE_TTL_SEC

logger = logging.getLogger("gemini_bot.panel_cog")

TABS: dict[str, dict] = {
    "overview": {"label": "Ringkasan", "emoji": "🏠", "desc": "Kesehatan bot & ringkasan semua modul"},
    "ai": {"label": "AI Agent", "emoji": "🤖", "desc": "Auto-Chat, Galeri, FAQ, welcome, digest"},
    "server": {"label": "Server", "emoji": "🛠️", "desc": "Stats, auto role, fakta, keamanan, anti-spam"},
    "community": {"label": "Komunitas", "emoji": "🧩", "desc": "Role, poll, pengingat, starboard, sticky, verifikasi"},
    "music": {"label": "Musik", "emoji": "🎵", "desc": "Node Lavalink, antrean, filter, autoplay"},
    "insights": {"label": "Kuota & Level", "emoji": "📊", "desc": "Pemakaian AI, cache, level, tiket"},
}


# ==============================================================================
# PENGUMPUL DATA (dipakai dashboard & embed cadangan)
# ==============================================================================
def _is_admin(member: discord.abc.User | discord.Member | None) -> bool:
    perms = getattr(member, "guild_permissions", None)
    return bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))


_PROCESS_START = time.time()


def _count_by_value(mapping: dict, guild_id: int, *, need_enabled: bool = False) -> int:
    """Hitung entri ber-`guild_id` di dalam value (peta ber-key channel/message)."""
    total = 0
    for value in mapping.values():
        if not isinstance(value, dict):
            continue
        if int(value.get("guild_id") or 0) != int(guild_id):
            continue
        if need_enabled and not value.get("enabled", True):
            continue
        total += 1
    return total


def _guild_cfg(mapping: dict, guild_id: int) -> dict:
    """Konfigurasi milik server (peta ber-key guild_id)."""
    cfg = mapping.get(int(guild_id))
    return cfg if isinstance(cfg, dict) else {}


def _open_tickets(guild_id: int) -> int:
    return sum(
        1
        for data in tickets_mod.tickets.values()
        if int(data.get("guild_id") or 0) == int(guild_id)
        and str(data.get("status") or "terbuka") in ("terbuka", "diklaim")
    )


def _music_state(snap: dict) -> tuple[str, str]:
    """`(label, state)` ramah dibaca untuk kondisi node Lavalink."""
    if not snap.get("configured"):
        return "belum dikonfigurasi", "off"
    if snap.get("ready"):
        return "tersambung", "on"
    if snap.get("connecting"):
        return "menyambung…", "warn"
    return "belum tersambung", "warn"


def _gather_themed(guild: discord.Guild, tab: str) -> tuple[str, list[str]]:
    """Ambil isi tab lalu terapkan setelan kepadatan server (`/tampilan atur`).

    Mode **ringkas** menyembunyikan baris penjelas (awalan `>`), mode **nyaman**
    menampilkan semuanya — jadi tombol kepadatan benar-benar mengubah tampilan.
    """
    title, lines = _gather(guild, tab)
    if ui_theme.is_compact(guild.id):
        lines = [ln for ln in lines if not ln.startswith("> ")]
    return title, lines


def _gather(guild: discord.Guild, tab: str) -> tuple[str, list[str]]:
    """Mengembalikan `(judul_kartu, daftar_baris)` untuk sebuah tab."""
    gid = guild.id

    if tab == "ai":
        chat_n = _count_by_value(community_agent.chat_agent_channels, gid)
        gallery_n = _count_by_value(community_agent.gallery_agent_channels, gid)
        yt_n = _count_by_value(community_agent.youtube_agent_channels, gid)
        search_n = _count_by_value(community_agent.search_agent_channels, gid)
        try:
            faq_n = len(community_agent.get_server_knowledge_entries(gid))
        except Exception:  # pragma: no cover - struktur data berbeda antar versi
            faq_n = 0
        welcome = bool(_guild_cfg(community_agent.welcome_agent_guilds, gid).get("channel_id"))
        goodbye = bool(_guild_cfg(community_agent.goodbye_agent_guilds, gid).get("channel_id"))
        digest = bool(_guild_cfg(community_agent.digest_agent_guilds, gid).get("channel_id"))
        today = insights.ai_usage.get(insights.today_key()) or {}
        lines = [
            ui_kit.status_line("Auto-Chat", f"`{chat_n}` channel", state="on" if chat_n else "off"),
            ui_kit.status_line("Komentator Galeri", f"`{gallery_n}` channel", state="on" if gallery_n else "off"),
            ui_kit.status_line("Rangkum YouTube / Link", f"`{yt_n}` channel", state="on" if yt_n else "off"),
            ui_kit.status_line("Pencarian /cari", f"`{search_n}` channel", state="on" if search_n else "off"),
            ui_kit.status_line("Sambutan member", "aktif" if welcome else "nonaktif", state="on" if welcome else "off"),
            ui_kit.status_line("Pesan perpisahan", "aktif" if goodbye else "nonaktif", state="on" if goodbye else "off"),
            ui_kit.status_line("Koran pagi (digest)", "aktif" if digest else "nonaktif", state="on" if digest else "off"),
            ui_kit.status_line("Basis FAQ server", f"`{faq_n}` entri", state="on" if faq_n else "idle"),
            "",
            f"_Operasi AI hari ini: **{int(today.get('total') or 0)}** • "
            f"cache hit: **{int(today.get('cache_hits') or 0)}**_",
        ]
        return "🤖 AI Agent & Otomasi", lines

    if tab == "server":
        stats_cfg = _guild_cfg(server_features.serverstats_guilds, gid)
        stats_on = bool(stats_cfg.get("enabled"))
        autorole = _guild_cfg(server_features.autorole_guilds, gid)
        autorole_on = bool(autorole.get("enabled") and autorole.get("role_ids"))
        facts = _guild_cfg(server_features.facts_guilds, gid)
        facts_on = bool(facts.get("enabled"))
        security = _guild_cfg(server_features.security_guilds, gid)
        phising_on = bool(security.get("enabled", True))
        spam = antispam.get_spam_config(gid)
        spam_on = bool(spam.get("enabled"))
        mode = str(spam.get("mode") or "lapor")
        lines = [
            ui_kit.status_line("Voice Stats", "aktif" if stats_on else "nonaktif", state="on" if stats_on else "off"),
            ui_kit.status_line(
                "Auto Role",
                f"`{len(autorole.get('role_ids') or [])}` role",
                state="on" if autorole_on else "off",
            ),
            ui_kit.status_line("Fakta Unik Dunia", "aktif" if facts_on else "nonaktif", state="on" if facts_on else "off"),
            ui_kit.status_line("Anti-Phishing", "aktif" if phising_on else "nonaktif", state="on" if phising_on else "off"),
            ui_kit.status_line("Anti-Spam", f"mode `{mode}`", state="on" if spam_on else "off"),
            ui_kit.status_line("Anggota server", f"`{guild.member_count or 0}`"),
            "",
            "> Anti-spam bawaan **mode lapor** — tidak menghapus apa pun tanpa izin Admin.",
        ]
        return "🛠️ Fitur Server & Keamanan", lines

    if tab == "community":
        panels = _count_by_value(community_tools.reaction_role_panels, gid)
        reminders = _count_by_value(community_tools.reminders, gid)
        starboard = _guild_cfg(community_tools.starboard_guilds, gid)
        starboard_on = bool(starboard.get("channel_id") or starboard.get("enabled"))
        sticky = _count_by_value(community_tools.sticky_channels, gid)
        verify = bool(_guild_cfg(community_tools.verification_guilds, gid).get("enabled"))
        giveaways = sum(
            1
            for g in engagement.giveaways.values()
            if int(g.get("guild_id") or 0) == gid and not g.get("ended")
        )
        birthdays = _count_by_value(engagement.birthdays, gid)
        autoreply = _count_by_value(engagement.auto_reply_channels, gid, need_enabled=True)
        announce = _count_by_value(engagement.announcements, gid)
        lines = [
            ui_kit.status_line("Panel Reaction Role", f"`{panels}` panel", state="on" if panels else "off"),
            ui_kit.status_line("Pengingat aktif", f"`{reminders}`", state="on" if reminders else "idle"),
            ui_kit.status_line("Starboard", "aktif" if starboard_on else "nonaktif", state="on" if starboard_on else "off"),
            ui_kit.status_line("Sticky message", f"`{sticky}` channel", state="on" if sticky else "off"),
            ui_kit.status_line("Gerbang verifikasi", "aktif" if verify else "nonaktif", state="on" if verify else "off"),
            ui_kit.status_line("Giveaway berjalan", f"`{giveaways}`", state="on" if giveaways else "idle"),
            ui_kit.status_line("Ulang tahun terdaftar", f"`{birthdays}` member", state="on" if birthdays else "idle"),
            ui_kit.status_line("Auto-Responder", f"`{autoreply}` channel", state="on" if autoreply else "off"),
            ui_kit.status_line("Pengumuman terjadwal", f"`{announce}`", state="on" if announce else "off"),
        ]
        return "🧩 Fitur Komunitas (0 kuota AI)", lines

    if tab == "music":
        snap = music.node_snapshot()
        cfg = music.get_music_settings(gid)
        dj = cfg.get("dj_role_id")
        node_value, node_state = _music_state(snap)
        players = sum(int(n.get("players") or 0) for n in snap.get("nodes") or [])
        lines = [
            ui_kit.status_line("Node Lavalink", f"{node_value} (`{snap.get('uri') or '—'}`)", state=node_state),
            ui_kit.status_line("Player aktif", f"`{players}`"),
            ui_kit.status_line("Volume default", f"`{cfg.get('volume')}%`"),
            ui_kit.status_line("Filter audio", f"`{cfg.get('filter', 'off')}`"),
            ui_kit.status_line(
                "Autoplay", "aktif" if cfg.get("autoplay") else "nonaktif",
                state="on" if cfg.get("autoplay") else "off",
            ),
            ui_kit.status_line("Role DJ", f"<@&{dj}>" if dj else "_belum diatur (opsional)_"),
            "> Role DJ **tidak wajib** untuk memutar lagu — cukup masuk voice channel.",
            "> Bila node belum tersambung, jalankan `/musik node` untuk diagnosa.",
        ]
        return "🎵 Streaming Musik (Lavalink)", lines

    if tab == "insights":
        today = insights.ai_usage.get(insights.today_key()) or {}
        kinds = sorted((today.get("kinds") or {}).items(), key=lambda kv: int(kv[1]), reverse=True)[:5]
        kind_lines = [f"• {insights.AI_KIND_LABELS.get(k, k)}: **{int(v)}**" for k, v in kinds]
        lvl_cfg = levels_mod.get_level_config(gid)
        member_levels = sum(1 for key in levels_mod.levels if str(key).startswith(f"{gid}:"))
        open_tickets = _open_tickets(gid)
        total_today = int(today.get("total") or 0)
        lines = [
            ui_kit.status_line(
                "Operasi AI hari ini", f"**{total_today}**", state="warn" if total_today > 200 else "on"
            ),
            ui_kit.status_line("Cache hit (hemat kuota)", f"**{int(today.get('cache_hits') or 0)}**", state="on"),
            ui_kit.status_line("Cache rekap channel", f"`{REKAP_CACHE_TTL_SEC // 60}` menit", state="on"),
            "",
            ui_kit.field_block("Jenis operasi terbanyak", kind_lines) or "_Belum ada operasi AI hari ini._",
            "",
            ui_kit.status_line(
                "Leveling", "aktif" if lvl_cfg.get("enabled") else "nonaktif",
                state="on" if lvl_cfg.get("enabled") else "off",
            ),
            ui_kit.status_line("Member terdata (level)", f"`{member_levels}`"),
            ui_kit.status_line("Tiket terbuka", f"`{open_tickets}`", state="on" if open_tickets else "idle"),
        ]
        return "📊 Kuota AI, Level & Tiket", lines

    # overview (default)
    ram = get_memory_usage_mb()
    uptime = max(0.0, time.time() - _PROCESS_START)
    ai_channels = _count_by_value(community_agent.chat_agent_channels, gid) + _count_by_value(
        community_agent.gallery_agent_channels, gid
    )
    spam_on = bool(antispam.get_spam_config(gid).get("enabled"))
    snap = music.node_snapshot()
    music_value, music_state = _music_state(snap)
    lvl_on = bool(levels_mod.get_level_config(gid).get("enabled"))
    open_tickets = _open_tickets(gid)
    today_total = int((insights.ai_usage.get(insights.today_key()) or {}).get("total") or 0)

    lines = [
        ui_kit.status_line("Versi bot", f"`v{BOT_VERSION}` • RAM `{ram} MB` • uptime `{ui_kit.human_uptime(uptime)}`"),
        ui_kit.status_line("Server", f"**{guild.name}** • `{guild.member_count or 0}` anggota"),
        "",
        ui_kit.status_line("AI Agent", f"`{ai_channels}` channel aktif", state="on" if ai_channels else "off"),
        ui_kit.status_line("Musik", music_value, state=music_state),
        ui_kit.status_line("Level & XP", "aktif" if lvl_on else "nonaktif", state="on" if lvl_on else "off"),
        ui_kit.status_line("Tiket terbuka", f"`{open_tickets}`", state="on" if open_tickets else "idle"),
        ui_kit.status_line("Anti-Spam", "aktif" if spam_on else "nonaktif", state="on" if spam_on else "off"),
        ui_kit.status_line(
            "Operasi AI hari ini", f"**{today_total}**", state="warn" if today_total > 200 else "on"
        ),
        "",
        f"-# Tema aktif: {ui_theme.theme_summary(gid)}",
    ]
    return "🏠 Ringkasan Sistem", lines


# ==============================================================================
# DASHBOARD
# ==============================================================================
def dashboard_embed(guild: discord.Guild, tab: str) -> discord.Embed:
    """Embed cadangan (dipakai bila Components V2 ditolak)."""
    title, lines = _gather_themed(guild, tab)
    body = "\n".join(ln for ln in lines if ln is not None)[:3800]
    embed = ui_kit.fallback_embed(
        guild.id,
        f"{ui_theme.emoji(guild.id, 'panel', '🛰️')} Control Center — {TABS.get(tab, TABS['overview'])['label']}",
        body,
        footer="Klik tab di bawah untuk berpindah halaman • /tampilan untuk ubah tema",
    )
    return ui_theme.apply_embed_theme(
        embed, guild.id, footer=f"tema: {ui_theme.theme_summary(guild.id)}"
    )


def make_dashboard(guild: discord.Guild, tab: str, requester_id: int) -> ui.LayoutView:
    """Membangun dashboard V2 untuk satu tab (dibuat ulang setiap pindah tab)."""
    gid = guild.id
    tab = tab if tab in TABS else "overview"
    title, lines = _gather_themed(guild, tab)
    view = ui_kit.build_view(gid, timeout=900)

    async def go(interaction: discord.Interaction, target: str) -> None:
        if interaction.guild is None:
            return
        new_view = make_dashboard(interaction.guild, target, requester_id)
        await ui_kit.edit_panel(interaction, new_view, embed=dashboard_embed(interaction.guild, target))

    async def on_tab(interaction: discord.Interaction) -> None:
        values = (interaction.data or {}).get("values") or [tab]
        await go(interaction, str(values[0]))

    async def on_refresh(interaction: discord.Interaction) -> None:
        await go(interaction, tab)

    async def on_theme(interaction: discord.Interaction) -> None:
        if not _is_admin(interaction.user):
            await interaction.response.send_message(
                "⚠️ Hanya **Admin / pengelola server** yang boleh mengubah tampilan.", ephemeral=True
            )
            return
        await ui_kit.edit_panel(
            interaction,
            make_theme_editor(interaction.guild, requester_id),
            embed=theme_embed(interaction.guild),
        )

    async def on_close(interaction: discord.Interaction) -> None:
        view.stop()
        await interaction.response.edit_message(
            view=ui_kit.build_view(
                gid,
                ui_kit.card(
                    gid,
                    ui_kit.text(f"### {ui_theme.emoji(gid, 'close', '🚪')} Panel ditutup\nBuka lagi dengan `/panel`."),
                ),
                timeout=None,
            )
        )

    icon = getattr(guild, "icon", None)
    header = ui_kit.header(
        gid,
        "panel",
        f"Control Center — {guild.name}",
        f"`v{BOT_VERSION}` • tab **{TABS[tab]['label']}** • {TABS[tab]['desc']}",
        thumbnail_url=getattr(icon, "url", None) if icon else None,
    )
    body = ui_kit.text("\n".join(ln for ln in lines if ln is not None))

    # Navigasi: dropdown (default) atau baris tombol sesuai tema
    nav_items = []
    if ui_theme.get_theme(gid)["nav"] == "tombol":
        tab_buttons = []
        for key, meta in TABS.items():
            tab_buttons.append(
                ui_kit.button(
                    f"{meta['emoji']} {meta['label']}",
                    style=discord.ButtonStyle.primary if key == tab else discord.ButtonStyle.secondary,
                    callback=(lambda ix, target=key: go(ix, target)),
                )
            )
        for start in range(0, len(tab_buttons), ui_kit.MAX_BUTTONS_PER_ROW):
            nav_items.append(ui_kit.action_row(*tab_buttons[start : start + ui_kit.MAX_BUTTONS_PER_ROW]))
    else:
        sel_tabs = ui_kit.select_menu(
            "panel:tab",
            "📂 Pilih kategori panel…",
            [
                ui_kit.option(f"{meta['emoji']} {meta['label']}", key, description=meta["desc"])
                for key, meta in TABS.items()
            ],
            callback=on_tab,
        )
        nav_items.append(ui_kit.action_row(sel_tabs))

    actions = ui_kit.action_row(
        ui_kit.button(
            "Segarkan",
            emoji=ui_theme.emoji(gid, "refresh", "🔄"),
            custom_id="panel:refresh",
            callback=on_refresh,
        ),
        ui_kit.button(
            "Tampilan",
            emoji=ui_theme.emoji(gid, "theme", "🎨"),
            custom_id="panel:theme",
            style=discord.ButtonStyle.primary,
            callback=on_theme,
        ),
        ui_kit.button(
            "Tutup",
            emoji=ui_theme.emoji(gid, "close", "🚪"),
            style=discord.ButtonStyle.danger,
            custom_id="panel:close",
            callback=on_close,
        ),
    )

    footer_line = ui_theme.footer_text(gid, "Pilih tab untuk berpindah • /tampilan untuk branding")
    children = [header, ui_kit.sep(), body, ui_kit.sep(), *nav_items, actions]
    if footer_line:
        children.append(ui_kit.text(f"-# {footer_line}"))

    view.add_item(ui_kit.card(gid, *children))
    return view


# ==============================================================================
# EDITOR TEMA (/tampilan)
# ==============================================================================
def theme_embed(guild: discord.Guild) -> discord.Embed:
    gid = guild.id
    theme = ui_theme.get_theme(gid)
    acc = ui_theme.ACCENTS[theme["accent"]]
    pack = ui_theme.EMOJI_PACKS[theme["emoji_pack"]]
    dens = ui_theme.DENSITIES[theme["density"]]
    emb = ui_kit.fallback_embed(
        gid,
        f"{ui_theme.emoji(gid, 'theme', '🎨')} Tampilan & Branding",
        (
            f"• Warna aksen: {acc['emoji']} **{acc['label']}**\n"
            f"• Emoji pack: {pack['emoji']} **{pack['label']}**\n"
            f"• Kepadatan: {dens['emoji']} **{dens['label']}**\n"
            f"• Thumbnail: **{ui_theme.THUMBNAIL_MODES[theme['thumbnail']]['label']}**\n"
            f"• Footer: {'aktif' if theme['footer'] else 'nonaktif'} • "
            f"Konfirmasi: {'aktif' if theme['confirm'] else 'nonaktif'}\n"
            f"• Navigasi: **{ui_theme.NAV_STYLES[theme['nav']]['label']}**\n"
            f"• Refresh panel: **{theme['refresh']} detik**"
        ),
        footer="Perubahan langsung tersimpan • /panel untuk melihat hasilnya",
    )
    return emb


def make_theme_editor(guild: discord.Guild, requester_id: int) -> ui.LayoutView:
    """Editor tema interaktif (semua perubahan langsung disimpan)."""
    gid = guild.id
    theme = ui_theme.get_theme(gid)
    view = ui_kit.build_view(gid, timeout=900)

    async def persist(interaction: discord.Interaction) -> None:
        await ui_theme.save_ui_themes_to_disk()
        new_view = make_theme_editor(interaction.guild, requester_id)
        await ui_kit.edit_panel(interaction, new_view, embed=theme_embed(interaction.guild))

    async def on_accent(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, accent=sel_accent.values[0])
        await persist(interaction)

    async def on_pack(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, emoji_pack=sel_pack.values[0])
        await persist(interaction)

    async def on_density(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, density=sel_density.values[0])
        await persist(interaction)

    async def on_thumb(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, thumbnail=sel_thumb.values[0])
        await persist(interaction)

    async def on_nav(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, nav=sel_nav.values[0])
        await persist(interaction)

    async def on_refresh(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, refresh=int(sel_refresh.values[0]))
        await persist(interaction)

    async def on_footer(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, footer=not ui_theme.get_theme(gid)["footer"])
        await persist(interaction)

    async def on_confirm(interaction: discord.Interaction) -> None:
        ui_theme.set_theme(gid, confirm=not ui_theme.get_theme(gid)["confirm"])
        await persist(interaction)

    async def on_reset(interaction: discord.Interaction) -> None:
        ui_theme.reset_theme(gid)
        await persist(interaction)

    async def on_preview(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=make_dashboard(interaction.guild, "overview", requester_id),
            ephemeral=True,
        )

    sel_accent = ui_kit.select_menu(
        "theme:accent",
        "🎨 Warna aksen panel…",
        [
            ui_kit.option(meta["label"], key, emoji=meta["emoji"], description="Warna kartu & embed")
            for key, meta in ui_theme.ACCENTS.items()
        ],
        callback=on_accent,
    )
    sel_pack = ui_kit.select_menu(
        "theme:emoji",
        "😀 Gaya emoji…",
        [ui_kit.option(m["label"], k, emoji=m["emoji"]) for k, m in ui_theme.EMOJI_PACKS.items()],
        callback=on_pack,
    )
    sel_density = ui_kit.select_menu(
        "theme:density",
        "🧾 Kepadatan informasi…",
        [ui_kit.option(m["label"], k, emoji=m["emoji"]) for k, m in ui_theme.DENSITIES.items()],
        callback=on_density,
    )
    sel_thumb = ui_kit.select_menu(
        "theme:thumb",
        "🖼️ Thumbnail panel…",
        [ui_kit.option(m["label"], k, emoji=m["emoji"]) for k, m in ui_theme.THUMBNAIL_MODES.items()],
        callback=on_thumb,
    )
    sel_nav = ui_kit.select_menu(
        "theme:nav",
        "📂 Gaya navigasi dashboard…",
        [ui_kit.option(m["label"], k, emoji=m["emoji"]) for k, m in ui_theme.NAV_STYLES.items()],
        callback=on_nav,
    )
    sel_refresh = ui_kit.select_menu(
        "theme:refresh",
        "⏱️ Interval refresh panel musik…",
        [ui_kit.option(label, str(value)) for value, label in ui_theme.REFRESH_CHOICES.items()],
        callback=on_refresh,
    )

    header = ui_kit.text(
        ui_kit.title_line(
            gid,
            "theme",
            "Tampilan & Branding",
            f"Berlaku untuk **seluruh panel** di {guild.name} • langsung tersimpan",
        )
    )
    current = ui_kit.text(
        "\n".join(
            [
                ui_kit.status_line("Warna aksen", ui_theme.ACCENTS[theme["accent"]]["label"],
                                   state="on"),
                ui_kit.status_line("Emoji pack", ui_theme.EMOJI_PACKS[theme["emoji_pack"]]["label"]),
                ui_kit.status_line("Kepadatan", ui_theme.DENSITIES[theme["density"]]["label"]),
                ui_kit.status_line("Thumbnail", ui_theme.THUMBNAIL_MODES[theme["thumbnail"]]["label"]),
                ui_kit.status_line("Navigasi", ui_theme.NAV_STYLES[theme["nav"]]["label"]),
                ui_kit.status_line("Refresh", f"`{theme['refresh']} detik`"),
            ]
        )
    )

    toggles = ui_kit.action_row(
        ui_kit.toggle_button(gid, "Footer", theme["footer"], custom_id="theme:footer", callback=on_footer),
        ui_kit.toggle_button(gid, "Konfirmasi", theme["confirm"], custom_id="theme:confirm", callback=on_confirm),
    )
    actions = ui_kit.action_row(
        ui_kit.button(
            "Pratinjau",
            emoji=ui_theme.emoji(gid, "preview", "👁️"),
            custom_id="theme:preview",
            callback=on_preview,
        ),
        ui_kit.button(
            "Reset",
            emoji=ui_theme.emoji(gid, "reset", "↺"),
            style=discord.ButtonStyle.danger,
            custom_id="theme:reset",
            callback=on_reset,
        ),
    )

    view.add_item(ui_kit.card(gid, header, ui_kit.sep(), current))
    view.add_item(
        ui_kit.card(
            gid,
            ui_kit.text("**🎨 Warna & Gaya**"),
            ui_kit.action_row(sel_accent),
            ui_kit.action_row(sel_pack),
            ui_kit.action_row(sel_density),
        )
    )
    view.add_item(
        ui_kit.card(
            gid,
            ui_kit.text("**⚙️ Perilaku Panel**"),
            ui_kit.action_row(sel_thumb),
            ui_kit.action_row(sel_nav),
            ui_kit.action_row(sel_refresh),
        )
    )
    view.add_item(
        ui_kit.card(
            gid,
            toggles,
            actions,
        )
    )
    return view


# ==============================================================================
# COMMAND
# ==============================================================================
panel_group = app_commands.Group(
    name="panel",
    description="Control Center: dashboard status & pengaturan semua fitur bot",
    guild_only=True,
)


@panel_group.command(name="buka", description="Buka dashboard Control Center (kartu status + navigasi tab)")
@app_commands.describe(tab="Halaman awal yang ingin dibuka")
@app_commands.choices(
    tab=[
        app_commands.Choice(name=f"{meta['emoji']} {meta['label']}", value=key)
        for key, meta in TABS.items()
    ]
)
async def panel_buka_cmd(interaction: discord.Interaction, tab: app_commands.Choice[str] | None = None):
    if interaction.guild is None:
        return
    target = tab.value if tab else "overview"
    view = make_dashboard(interaction.guild, target, interaction.user.id)
    await ui_kit.send_panel(
        interaction, view, embed=dashboard_embed(interaction.guild, target), ephemeral=True
    )


tampilan_group = app_commands.Group(
    name="tampilan",
    description="Ubah tema tampilan bot: warna aksen, emoji, kepadatan, & branding",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
)


@tampilan_group.command(name="atur", description="Buka editor tema tampilan (khusus Admin / pengelola server)")
async def tampilan_atur_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _is_admin(interaction.user):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return
    await ui_kit.send_panel(
        interaction,
        make_theme_editor(interaction.guild, interaction.user.id),
        embed=theme_embed(interaction.guild),
        ephemeral=True,
    )


@tampilan_group.command(name="pratinjau", description="Lihat dashboard dengan tema yang sedang aktif")
async def tampilan_pratinjau_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    await ui_kit.send_panel(
        interaction,
        make_dashboard(interaction.guild, "overview", interaction.user.id),
        embed=dashboard_embed(interaction.guild, "overview"),
        ephemeral=True,
    )


@tampilan_group.command(name="reset", description="Kembalikan tampilan ke bawaan bot (Admin)")
async def tampilan_reset_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not _is_admin(interaction.user):
        await interaction.response.send_message(
            "⚠️ Command ini khusus **Admin / pengelola server**.", ephemeral=True
        )
        return

    async def _do(ix: discord.Interaction) -> None:
        ui_theme.reset_theme(ix.guild.id if ix.guild else 0)
        await ui_theme.save_ui_themes_to_disk()
        await ix.response.edit_message(
            view=ui_kit.build_view(
                ix.guild.id if ix.guild else None,
                ui_kit.card(
                    ix.guild.id if ix.guild else None,
                    ui_kit.text(
                        f"### {ui_theme.emoji(ix.guild.id if ix.guild else None, 'ok', '✅')} Tema direset\n"
                        "Tampilan kembali ke bawaan bot."
                    ),
                ),
                timeout=None,
            )
        )

    view = ui_kit.ConfirmView(
        interaction.guild.id,
        title="Reset tema tampilan?",
        detail="Semua kustomisasi warna, emoji, & branding server ini akan dihapus.",
        confirm_label="Ya, reset",
        on_confirm=_do,
        author_id=interaction.user.id,
    )
    if not ui_theme.confirm_enabled(interaction.guild.id):
        ui_theme.reset_theme(interaction.guild.id)
        await ui_theme.save_ui_themes_to_disk()
        await interaction.response.send_message("✅ Tema server direset ke bawaan.", ephemeral=True)
        return
    await ui_kit.send_panel(
        interaction,
        view,
        embed=ui_kit.fallback_embed(
            interaction.guild.id,
            "⚠️ Reset tema tampilan?",
            "Semua kustomisasi warna, emoji, & branding server ini akan dihapus.",
        ),
        ephemeral=True,
    )


def register_panel_cog(bot: commands.Bot) -> None:
    """Mendaftarkan `/panel` & `/tampilan`."""
    bot.tree.add_command(panel_group)
    bot.tree.add_command(tampilan_group)
