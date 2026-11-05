"""Agent views — dipisah dari views.py agar berkas tidak membengkak."""

import time
import discord
from config import (
    AGENT_DEFAULT_IDLE_MINUTES,
    AGENT_MAX_IDLE_POKES,
    BOT_TIMEZONE,
    BOT_VERSION,
    ENABLE_GOOGLE_SEARCH,
    ENABLE_URL_READER,
)
import ui_kit
import ui_theme
from discord import ui
from community_agent import (
    GREETING_PERSONAS,
    STYLE_DESCRIPTIONS,
    chat_agent_channels,
    clear_server_knowledge,
    delete_server_knowledge,
    digest_agent_guilds,
    format_idle_duration,
    gallery_agent_channels,
    goodbye_agent_guilds,
    get_guild_search_channels,
    get_guild_settings,
    get_guild_youtube_channels,
    get_server_knowledge_entries,
    save_agent_config_to_disk,
    search_agent_channels,
    set_chat_channel_config,
    set_digest_config,
    set_gallery_channel_config,
    set_goodbye_config,
    set_search_channel_config,
    set_welcome_config,
    set_youtube_channel_config,
    upsert_server_knowledge,
    welcome_agent_guilds,
    youtube_agent_channels,
)
from server_features import (
    facts_guilds,
    format_facts_schedule,
    save_server_features_to_disk,
    security_guilds,
    set_facts_config,
)
from utils import get_realtime_time_context

_TIMEZONE_ALIASES: dict[str, str] = {
    "wib": "Asia/Jakarta",
    "jakarta": "Asia/Jakarta",
    "asia/jakarta": "Asia/Jakarta",
    "wita": "Asia/Makassar",
    "makassar": "Asia/Makassar",
    "bali": "Asia/Makassar",
    "asia/makassar": "Asia/Makassar",
    "wit": "Asia/Jayapura",
    "jayapura": "Asia/Jayapura",
    "papua": "Asia/Jayapura",
    "asia/jayapura": "Asia/Jayapura",
}


# ==============================================================================
# DASHBOARD STATUS TERPADU & PANEL KONTROL ADMIN INTERAKTIF (/agent status & /agent panel)
# ==============================================================================
def _build_channel_spotlight_summary(guild: discord.Guild, cid: int) -> str:
    """Merangkum status ON/OFF seluruh fitur pada 1 channel target yang sedang dipilih di panel."""
    ch_obj = guild.get_channel(cid)
    is_forum = isinstance(ch_obj, discord.ForumChannel)
    ch_type_lbl = "Forum / Media" if is_forum else "Text Channel"

    chat_on = bool(chat_agent_channels.get(cid, {}).get("enabled"))
    gal_on = bool(gallery_agent_channels.get(cid, {}).get("enabled"))
    yt_on = bool(youtube_agent_channels.get(cid, {}).get("enabled"))
    srch_on = bool(search_agent_channels.get(cid, {}).get("enabled"))

    w_cfg = welcome_agent_guilds.get(guild.id) or {}
    wel_on = bool(w_cfg.get("enabled") and int(w_cfg.get("channel_id") or 0) == cid)
    d_cfg = digest_agent_guilds.get(guild.id) or {}
    dig_on = bool(d_cfg.get("enabled") and int(d_cfg.get("channel_id") or 0) == cid)
    gb_cfg = goodbye_agent_guilds.get(guild.id) or {}
    gb_on = bool(gb_cfg.get("enabled") and int(gb_cfg.get("channel_id") or 0) == cid)
    f_cfg = facts_guilds.get(guild.id) or {}
    fak_on = bool(f_cfg.get("enabled") and int(f_cfg.get("channel_id") or 0) == cid)
    sec_cfg = security_guilds.get(guild.id) or {}
    sec_on = bool(
        sec_cfg.get("enabled")
        and (not sec_cfg.get("channel_ids") or cid in sec_cfg.get("channel_ids"))
    )

    b = lambda flag: "🟢 ON" if flag else "⚪ OFF"
    line1 = f"<#{cid}> *({ch_type_lbl})*\n"
    line2 = f"💬 Chat: `{b(chat_on)}` • 🎨 Galeri: `{b(gal_on)}` • ▶️ YouTube: `{b(yt_on)}` • 🌐 Cari: `{b(srch_on)}`"
    if is_forum:
        return line1 + line2 + f"\n🛡️ Anti-Phishing: `{b(sec_on)}`"
    line3 = (
        f"\n👋 Welcome: `{b(wel_on)}` • 👣 Goodbye: `{b(gb_on)}` • ☀️ Digest: `{b(dig_on)}`"
        f"\n🌍 Fakta Harian: `{b(fak_on)}` • 🛡️ Anti-Phishing: `{b(sec_on)}`"
    )
    return line1 + line2 + line3
def build_agent_status_embed(
    guild: discord.Guild,
    *,
    selected_channel_id: int | None = None,
    notice_banner: str | None = None,
) -> discord.Embed:
    """Embed ringkasan status terpadu untuk `/agent status` sekaligus `/agent panel`."""
    guild_id = guild.id
    cfg = get_guild_settings(guild_id)
    t_ctx = get_realtime_time_context(cfg.get("timezone", BOT_TIMEZONE))
    faq_entries = get_server_knowledge_entries(guild_id)
    now_ts = time.time()

    guild_chats = [
        (cid, cdata)
        for cid, cdata in chat_agent_channels.items()
        if cdata.get("guild_id") == guild_id and cdata.get("enabled")
    ]
    guild_galleries = [
        (cid, gdata)
        for cid, gdata in gallery_agent_channels.items()
        if gdata.get("guild_id") == guild_id and gdata.get("enabled")
    ]
    guild_yt = get_guild_youtube_channels(guild_id)
    guild_search = get_guild_search_channels(guild_id)

    chat_lines: list[str] = []
    for cid, cdata in guild_chats:
        ch_obj = guild.get_channel(cid)
        is_forum_ch = isinstance(ch_obj, discord.ForumChannel)
        idle_s = int(
            cdata.get("idle_seconds")
            if cdata.get("idle_seconds") is not None
            else int(cdata.get("idle_minutes") or 0) * 60
        )
        if is_forum_ch:
            idle_info = "`Mode Forum (Aktif di Postingan)`"
        elif idle_s <= 0:
            idle_info = "Pemecah Sepi: `Mati`"
        elif int(cdata.get("consecutive_idle_pokes") or 0) >= AGENT_MAX_IDLE_POKES:
            idle_info = f"`{format_idle_duration(idle_s)}` *(menunggu balasan warga)*"
        else:
            rem_sec = max(0, int(idle_s - (now_ts - float(cdata.get("last_activity_at") or now_ts))))
            rem_lbl = f"{rem_sec} dtk" if rem_sec < 60 else f"{rem_sec // 60} mnt {rem_sec % 60} dtk"
            idle_info = f"`{format_idle_duration(idle_s)}` *(sapa dlm ~{rem_lbl})*"
        chat_lines.append(f"• <#{cid}> — Mode `{cdata.get('reply_mode')}` | {idle_info}")

    gal_lines = [
        f"• <#{cid}> — Auto-Reaction: `{'ON' if gdata.get('auto_reaction', True) else 'OFF'}`"
        for cid, gdata in guild_galleries
    ]

    if not ENABLE_URL_READER:
        yt_text = "⛔ **Nonaktif Global di `.env`** (`ENABLE_URL_READER=false`)"
    elif guild_yt:
        yt_lines = [
            f"• <#{cid}> — Mode: `{'Otomatis Semua Link' if ydata.get('auto_in_chat') else 'Saat Dipanggil & /ringkas link'}`"
            for cid, ydata in guild_yt
        ]
        yt_text = "\n".join(yt_lines)
    else:
        yt_text = "_Belum ada channel (aktifkan via panel atau `/agent youtube`)_"

    if not ENABLE_GOOGLE_SEARCH:
        search_text = "⛔ **Nonaktif Global di `.env`** (`ENABLE_GOOGLE_SEARCH=false`)"
    elif guild_search:
        s_lines = [
            f"• <#{cid}> — `/cari`: `ON` | Auto di Chat: `{'ON' if sdata.get('auto_in_chat', True) else 'OFF'}`"
            for cid, sdata in guild_search
        ]
        search_text = "\n".join(s_lines)
    else:
        search_text = "_Belum ada channel (aktifkan via panel atau `/agent cari`)_"

    w_cfg = welcome_agent_guilds.get(guild_id)
    if w_cfg and w_cfg.get("enabled"):
        w_note = f" *(Info: {w_cfg['extra_note']})*" if w_cfg.get("extra_note") else ""
        persona_lbl = GREETING_PERSONAS.get(str(w_cfg.get("persona") or "hangat"), {}).get("label", "Hangat & Tulus")
        card_mode = str(w_cfg.get("card_mode") or "mati")
        card_lbl = {"mati": "teks", "statis": "banner", "dinamis": "kartu"}.get(card_mode, "teks")
        dm_lbl = " • DM ✅" if w_cfg.get("dm") else ""
        welcome_text = (
            f"✅ Aktif di <#{w_cfg['channel_id']}> — Persona: `{persona_lbl}` "
            f"• Tampilan: `{card_lbl}`{dm_lbl}{w_note}"
        )
    else:
        welcome_text = "_Belum aktif_"

    gb_cfg = goodbye_agent_guilds.get(guild_id)
    if gb_cfg and gb_cfg.get("enabled"):
        gb_persona = GREETING_PERSONAS.get(str(gb_cfg.get("persona") or "hangat"), {}).get("label", "Hangat & Tulus")
        goodbye_text = f"✅ Aktif di <#{gb_cfg['channel_id']}> — Persona: `{gb_persona}`"
    else:
        goodbye_text = "_Belum aktif_"

    f_cfg = facts_guilds.get(guild_id)
    if f_cfg and f_cfg.get("enabled"):
        f_times = list(f_cfg.get("times") or [])
        facts_text = (
            f"✅ Aktif di <#{f_cfg['channel_id']}> — "
            f"{format_facts_schedule(f_times)} {t_ctx['tz_label']} *({len(f_times)}x sehari)*"
        )
    else:
        facts_text = "_Belum aktif_"

    sec_cfg = security_guilds.get(guild_id)
    if sec_cfg and sec_cfg.get("enabled"):
        sec_scope = (
            f"<#{sec_cfg['channel_ids'][0]}>" if sec_cfg.get("channel_ids") else "Seluruh Server"
        )
        security_text = (
            f"✅ Aktif ({sec_scope}) — Aksi: `{sec_cfg.get('action')}` | "
            f"Diblokir: `{sec_cfg.get('blocked', 0)}`"
        )
    else:
        security_text = "_Belum aktif_"

    d_cfg = digest_agent_guilds.get(guild_id)
    if d_cfg and d_cfg.get("enabled"):
        digest_text = (
            f"✅ Aktif di <#{d_cfg['channel_id']}> pukul **`{d_cfg['hour']:02d}:{d_cfg['minute']:02d} {t_ctx['tz_label']}`** "
            f"*(Topik: {d_cfg.get('topic')})*"
        )
    else:
        digest_text = "_Belum aktif_"

    desc_parts: list[str] = []
    if notice_banner:
        desc_parts.append(notice_banner)
    desc_parts.append(f"🕒 **Waktu Lokal Server:** `{t_ctx['summary']}`")

    bot_disp = guild.me.display_name if guild.me else "Bot"
    embed = discord.Embed(
        title=f"🤖 Dashboard AI Community Agent (`v{BOT_VERSION}`)",
        description="\n".join(desc_parts),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )

    if selected_channel_id is not None:
        embed.add_field(
            name="📍 Channel Target Terpilih di Panel",
            value=_build_channel_spotlight_summary(guild, selected_channel_id),
            inline=False,
        )

    embed.add_field(
        name="🎭 Persona & Memori FAQ Server",
        value=(
            f"• **Panggilan:** `{cfg.get('nickname') or bot_disp}` | **Gaya:** `{cfg.get('style_preset')}` | "
            f"**Jam Tenang (23-06):** `{'Aktif' if cfg.get('quiet_hours', True) else 'Nonaktif'}`\n"
            f"• **Konteks Server:** {cfg.get('custom_prompt') or '_(Default)_'}\n"
            f"• **Memori Info / FAQ Server (`/agent info`):** `{len(faq_entries)}/25 entri tersimpan`"
        ),
        inline=False,
    )
    embed.add_field(
        name="💬 Channel & Forum Auto-Chat",
        value="\n".join(chat_lines) if chat_lines else "_Belum ada channel aktif_",
        inline=False,
    )
    embed.add_field(
        name="🎨 Channel & Forum Galeri Karya",
        value="\n".join(gal_lines) if gal_lines else "_Belum ada channel aktif_",
        inline=False,
    )
    embed.add_field(
        name="▶️ Perangkum YouTube & Link Web",
        value=yt_text,
        inline=False,
    )
    embed.add_field(
        name="🌐 Pencarian Berita & Web Terkini",
        value=search_text,
        inline=False,
    )
    embed.add_field(
        name="👋 Sambutan Member & ☀️ Koran Pagi",
        value=(
            f"• **Welcome:** {welcome_text}\n"
            f"• **Goodbye:** {goodbye_text}\n"
            f"• **Morning Digest:** {digest_text}"
        ),
        inline=False,
    )
    embed.add_field(
        name="🌍 Fakta Harian & 🛡️ Anti-Phishing",
        value=f"• **Fakta Unik Dunia:** {facts_text}\n• **Anti-Phishing:** {security_text}",
        inline=False,
    )
    return embed
class EditPersonaModal(discord.ui.Modal, title="🎭 Ubah Kepribadian AI Server"):
    nickname_input = discord.ui.TextInput(
        label="Nama Panggilan Bot (ketik - untuk reset)",
        placeholder="Contoh: Bimo / Neko / Asisten",
        required=False,
        max_length=32,
    )
    style_input = discord.ui.TextInput(
        label="Gaya Bahasa (akrab / gaul / ramah)",
        placeholder="Ketik: akrab, gaul, atau ramah",
        default="akrab",
        required=True,
        max_length=12,
    )
    tz_input = discord.ui.TextInput(
        label="Zona Waktu (WIB / WITA / WIT)",
        placeholder="WIB, WITA, atau WIT",
        default="WIB",
        required=False,
        max_length=24,
    )
    prompt_input = discord.ui.TextInput(
        label="Konteks Komunitas (ketik - untuk reset)",
        style=discord.TextStyle.paragraph,
        placeholder="Contoh: Ini server komunitas developer indie & mabar Valorant Indonesia.",
        required=False,
        max_length=300,
    )

    def __init__(self, guild_id: int, selected_channel_id: int | None = None):
        super().__init__()
        self._selected_channel_id = selected_channel_id
        cfg = get_guild_settings(guild_id)
        self.nickname_input.default = cfg.get("nickname") or ""
        self.style_input.default = cfg.get("style_preset") or "akrab"
        cur_tz = cfg.get("timezone") or BOT_TIMEZONE
        tz_short = {"Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT"}.get(cur_tz, cur_tz)
        self.tz_input.default = tz_short
        self.prompt_input.default = cfg.get("custom_prompt") or ""

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        cfg = get_guild_settings(interaction.guild.id)
        raw_nick = self.nickname_input.value.strip()
        cfg["nickname"] = "" if raw_nick == "-" else raw_nick[:32]

        raw_style = self.style_input.value.strip().lower()
        if raw_style in STYLE_DESCRIPTIONS:
            cfg["style_preset"] = raw_style

        raw_tz = self.tz_input.value.strip().lower()
        if raw_tz in _TIMEZONE_ALIASES:
            cfg["timezone"] = _TIMEZONE_ALIASES[raw_tz]

        raw_prompt = self.prompt_input.value.strip()
        cfg["custom_prompt"] = "" if raw_prompt == "-" else raw_prompt[:300]

        await save_agent_config_to_disk()
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self._selected_channel_id,
                notice_banner="✅ **Persona & zona waktu AI Server berhasil diperbarui!**",
            )
        )
class AddServerInfoModal(discord.ui.Modal, title="📌 Tambah Memori Info / FAQ Server"):
    topic_input = discord.ui.TextInput(
        label="Topik / Kata Kunci FAQ",
        placeholder="Contoh: IP Server Minecraft / Rules / Jadwal Mabar",
        required=True,
        max_length=80,
    )
    content_input = discord.ui.TextInput(
        label="Isi Informasi Resmi Server",
        style=discord.TextStyle.paragraph,
        placeholder="Contoh: IP Minecraft play.contoh.id versi 1.21.4, buka 24 jam tanpa whitelist.",
        required=True,
        max_length=500,
    )

    def __init__(self, selected_channel_id: int | None = None):
        super().__init__()
        self._selected_channel_id = selected_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        item, status = upsert_server_knowledge(
            interaction.guild.id,
            self.topic_input.value,
            self.content_input.value,
        )
        if status == "full" or item is None:
            await interaction.response.send_message(
                "⚠️ Kapasitas FAQ Server sudah penuh (maksimal 25 entri). Klik **📋 Kelola FAQ** untuk menghapus entri lama.",
                ephemeral=True,
            )
            return
        await save_agent_config_to_disk()
        verb = "diperbarui" if status == "updated" else "ditambahkan"
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self._selected_channel_id,
                notice_banner=f"✅ **Info FAQ `{item['topic']}` berhasil {verb}!**",
            )
        )
def build_faq_list_embed(guild: discord.Guild, notice: str | None = None) -> discord.Embed:
    """Membuat tampilan daftar entri FAQ server yang rapi."""
    entries = get_server_knowledge_entries(guild.id)
    if not entries:
        desc = (
            "📭 **Memori Info & FAQ Server masih kosong.**\n\n"
            "Tambahkan info seperti *rules server, IP game, jadwal mabar,* atau *link penting* lewat tombol "
            "**➕ Tambah FAQ** di panel atau `/agent info aksi:Tambah`!"
        )
    else:
        lines = [
            f"**{idx}. `{item['topic']}`**\n> {item['content']}"
            for idx, item in enumerate(entries, start=1)
        ]
        desc = "\n\n".join(lines)[:3900]
    if notice:
        desc = f"{notice}\n\n{desc}"[:4050]

    embed = discord.Embed(
        title=f"📌 Memori Info & FAQ Resmi — {guild.name}",
        description=desc,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Total {len(entries)}/25 entri • Dipahami otomatis oleh AI di seluruh channel & sesi")
    return embed
class ServerFaqManagerView(discord.ui.View):
    """Panel mini interaktif untuk melihat & menghapus entri FAQ Server dengan 1 klik."""

    def __init__(self, admin_user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.admin_user_id = admin_user_id
        entries = get_server_knowledge_entries(guild_id)
        if entries:
            opts = [
                discord.SelectOption(
                    label=f"{idx}. {item['topic']}"[:100],
                    value=str(idx),
                    description=item["content"][:95],
                    emoji="🗑️",
                )
                for idx, item in enumerate(entries[:25], start=1)
            ]
            del_select = discord.ui.Select(
                placeholder="🗑️ Pilih entri FAQ yang ingin dihapus...",
                options=opts,
                row=0,
            )
            del_select.callback = self._delete_selected_callback
            self.add_item(del_select)

            clear_btn = discord.ui.Button(
                label="Hapus Semua FAQ",
                style=discord.ButtonStyle.danger,
                emoji="🧹",
                row=1,
            )
            clear_btn.callback = self._clear_all_callback
            self.add_item(clear_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message(
                "⚠️ Hanya Admin pembuka panel yang dapat mengelola FAQ ini.",
                ephemeral=True,
            )
            return False
        return True

    async def _delete_selected_callback(self, interaction: discord.Interaction):
        if interaction.guild is None or not interaction.data:
            return
        values = interaction.data.get("values") or []
        if not values:
            return
        removed = delete_server_knowledge(interaction.guild.id, values[0])
        await save_agent_config_to_disk()
        note = f"🗑️ Entri **`{removed['topic']}`** berhasil dihapus." if removed else "⚠️ Entri sudah tidak ada."
        fresh_view = ServerFaqManagerView(self.admin_user_id, interaction.guild.id)
        await interaction.response.edit_message(
            embed=build_faq_list_embed(interaction.guild, notice=note),
            view=fresh_view,
        )

    async def _clear_all_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        cnt = clear_server_knowledge(interaction.guild.id)
        await save_agent_config_to_disk()
        fresh_view = ServerFaqManagerView(self.admin_user_id, interaction.guild.id)
        await interaction.response.edit_message(
            embed=build_faq_list_embed(
                interaction.guild,
                notice=f"🧹 Seluruh memori FAQ (**{cnt} entri**) berhasil dibersihkan.",
            ),
            view=fresh_view,
        )
async def apply_agent_toggle(interaction: discord.Interaction, cid: int, action: str) -> str | None:
    """Menyalakan/mematikan satu fitur AI Agent pada channel tertentu (0 kuota AI).

    Mengembalikan teks banner perubahan, atau `None` bila aksi ditolak
    (pesan peringatan sudah dikirim ke pengguna).
    """
    if interaction.guild is None:
        return None
    target_ch = interaction.guild.get_channel(cid)
    is_forum_like = isinstance(target_ch, discord.ForumChannel)
    banner = ""
    guild_id = interaction.guild.id

    if action == "toggle_chat":
        new_state = not bool(chat_agent_channels.get(cid, {}).get("enabled"))
        set_chat_channel_config(
            guild_id,
            cid,
            enabled=new_state,
            reply_mode="smart",
            idle_minutes=0 if is_forum_like else AGENT_DEFAULT_IDLE_MINUTES,
        )
        banner = f"💬 **Auto-Chat** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
    elif action == "toggle_gallery":
        new_state = not bool(gallery_agent_channels.get(cid, {}).get("enabled"))
        set_gallery_channel_config(guild_id, cid, enabled=new_state, auto_reaction=True)
        banner = f"🎨 **Komentator Galeri** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
    elif action == "toggle_youtube":
        new_state = not bool(youtube_agent_channels.get(cid, {}).get("enabled"))
        set_youtube_channel_config(guild_id, cid, enabled=new_state, auto_in_chat=False)
        banner = f"▶️ **Rangkum YouTube & Link** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
    elif action == "toggle_search":
        new_state = not bool(search_agent_channels.get(cid, {}).get("enabled"))
        set_search_channel_config(guild_id, cid, enabled=new_state, auto_in_chat=True)
        banner = f"🌐 **Pencarian Berita (`/cari`)** di <#{cid}> ➔ **{'AKTIF' if new_state else 'NONAKTIF'}**"
    elif action == "toggle_welcome":
        if is_forum_like:
            await interaction.response.send_message(
                "⚠️ Sambutan Member Baru hanya dapat dipasang pada **Text Channel** biasa (bukan Forum).",
                ephemeral=True,
            )
            return
        w_cur = welcome_agent_guilds.get(guild_id)
        turn_on = not (w_cur and w_cur.get("enabled") and w_cur.get("channel_id") == cid)
        set_welcome_config(guild_id, cid, enabled=turn_on)
        banner = f"👋 **Auto-Welcomer** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
    elif action == "toggle_digest":
        if is_forum_like:
            await interaction.response.send_message(
                "⚠️ Koran Pagi (Morning Digest) hanya dapat dikirim ke **Text Channel** biasa (bukan Forum).",
                ephemeral=True,
            )
            return
        d_cur = digest_agent_guilds.get(guild_id)
        turn_on = not (d_cur and d_cur.get("enabled") and d_cur.get("channel_id") == cid)
        set_digest_config(guild_id, cid, enabled=turn_on, hour=7, minute=0)
        banner = f"☀️ **Koran Pagi 07:00** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
    elif action == "toggle_goodbye":
        if is_forum_like:
            await interaction.response.send_message(
                "⚠️ Pesan Perpisahan (Goodbye) hanya dapat dipasang pada **Text Channel** biasa (bukan Forum).",
                ephemeral=True,
            )
            return
        gb_cur = goodbye_agent_guilds.get(guild_id)
        turn_on = not (gb_cur and gb_cur.get("enabled") and gb_cur.get("channel_id") == cid)
        set_goodbye_config(guild_id, cid, enabled=turn_on)
        banner = f"👣 **Pesan Perpisahan (Goodbye)** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
    elif action == "toggle_facts":
        if is_forum_like:
            await interaction.response.send_message(
                "⚠️ Fakta Unik Dunia hanya dapat dikirim ke **Text Channel** biasa (bukan Forum).",
                ephemeral=True,
            )
            return
        f_cur = facts_guilds.get(guild_id)
        turn_on = not (f_cur and f_cur.get("enabled") and f_cur.get("channel_id") == cid)
        f_cfg_new = set_facts_config(guild_id, cid, enabled=turn_on)
        f_slots = format_facts_schedule((f_cfg_new or {}).get("times"))
        banner = (
            f"🌍 **Fakta Unik Dunia** di <#{cid}> ➔ **{'AKTIF' if turn_on else 'NONAKTIF'}**"
            + (f"\n⏰ Jadwal aktif: {f_slots} *(ubah lewat `/fakta atur`)*" if turn_on else "")
        )


    return banner
class AgentAdminPanelView(discord.ui.View):
    """Panel Kontrol Admin Interaktif (/agent panel) dengan Spotlight Channel, Toggle Mulus, & Pengelola FAQ."""

    def __init__(self, admin_user_id: int, default_channel_id: int | None = None):
        super().__init__(timeout=600)
        self.admin_user_id = admin_user_id
        self.selected_channel_id: int | None = default_channel_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message(
                "⚠️ Panel kontrol ini hanya dapat dioperasikan oleh Admin yang membukanya.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[
            discord.ChannelType.text,
            discord.ChannelType.news,
            discord.ChannelType.forum,
            discord.ChannelType.media,
        ],
        placeholder="1️⃣ Pilih Channel / Forum target yang ingin diatur...",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def pick_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.guild is None:
            return
        picked = select.values[0]
        self.selected_channel_id = picked.id
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=picked.id,
                notice_banner=f"📍 Channel target diubah ke <#{picked.id}>. Pilih menu **2️⃣** untuk ON/OFF fitur!",
            ),
            view=self,
        )

    @discord.ui.select(
        placeholder="2️⃣ Toggle ON / OFF fitur pada channel terpilih...",
        options=[
            discord.SelectOption(
                label="Toggle Auto-Chat Pintar (ON / OFF)",
                value="toggle_chat",
                emoji="💬",
                description="Aktifkan/matikan ngobrol otomatis & jawab Forum di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Komentator Galeri (ON / OFF)",
                value="toggle_gallery",
                emoji="🎨",
                description="Aktifkan/matikan apresiasi foto, video, & stiker di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Rangkum YouTube & Link (ON / OFF)",
                value="toggle_youtube",
                emoji="▶️",
                description="Aktifkan/matikan pembaca link YouTube & web di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Pencarian Berita /cari (ON / OFF)",
                value="toggle_search",
                emoji="🌐",
                description="Aktifkan/matikan fitur /cari & berita terkini di channel ini",
            ),
            discord.SelectOption(
                label="Toggle Sambutan Member Baru (ON / OFF)",
                value="toggle_welcome",
                emoji="👋",
                description="Jadikan channel teks ini tempat menyapa member baru otomatis",
            ),
            discord.SelectOption(
                label="Toggle Koran Pagi 07:00 (ON / OFF)",
                value="toggle_digest",
                emoji="☀️",
                description="Kirim sapaan & rangkuman berita pagi harian pukul 07:00 di sini",
            ),
            discord.SelectOption(
                label="Toggle Pesan Perpisahan / Goodbye (ON / OFF)",
                value="toggle_goodbye",
                emoji="👣",
                description="Kirim kartu perpisahan AI saat member keluar dari server",
            ),
            discord.SelectOption(
                label="Toggle Fakta Unik Dunia (ON / OFF)",
                value="toggle_facts",
                emoji="🌍",
                description="Kirim 3–4 fakta unik dari berbagai negara sesuai jadwal multi-slot",
            ),
        ],
        row=1,
    )
    async def toggle_feature(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.guild is None:
            return
        cid = self.selected_channel_id
        if cid is None:
            await interaction.response.send_message(
                "⚠️ Pilih channel terlebih dahulu pada menu **1️⃣** di atas!",
                ephemeral=True,
            )
            return

        banner = await apply_agent_toggle(interaction, cid, select.values[0])
        if banner is None:
            return
        await save_agent_config_to_disk()
        await save_server_features_to_disk()
        # Buat instance View segar agar dropdown reset & bisa diklik ulang langsung
        fresh_view = AgentAdminPanelView(self.admin_user_id, default_channel_id=cid)
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=cid,
                notice_banner=banner,
            ),
            view=fresh_view,
        )

    @discord.ui.button(label="Persona", style=discord.ButtonStyle.primary, emoji="🎭", row=2)
    async def edit_persona_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.send_modal(
            EditPersonaModal(interaction.guild.id, selected_channel_id=self.selected_channel_id)
        )

    @discord.ui.button(label="Tambah FAQ", style=discord.ButtonStyle.success, emoji="➕", row=2)
    async def add_faq_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AddServerInfoModal(selected_channel_id=self.selected_channel_id)
        )

    @discord.ui.button(label="Kelola FAQ", style=discord.ButtonStyle.secondary, emoji="📋", row=2)
    async def manage_faq_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.send_message(
            embed=build_faq_list_embed(interaction.guild),
            view=ServerFaqManagerView(interaction.user.id, interaction.guild.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Segarkan", style=discord.ButtonStyle.secondary, emoji="🔄", row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        await interaction.response.edit_message(
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self.selected_channel_id,
            ),
            view=self,
        )
# ==============================================================================
# PUSAT PANDUAN INTERAKTIF BERKATEGORI (/bantuan)
# ==============================================================================
# ==============================================================================
# PANEL KONTROL AI AGENT v2 (Components V2, kartu toggle hijau/merah)
# ==============================================================================
AGENT_FEATURES: list[tuple[str, str, str]] = [
    ("toggle_chat", "Auto-Chat", "💬"),
    ("toggle_gallery", "Galeri", "🎨"),
    ("toggle_youtube", "YouTube", "▶️"),
    ("toggle_search", "Cari", "🌐"),
    ("toggle_welcome", "Welcome", "👋"),
    ("toggle_digest", "Digest", "☀️"),
    ("toggle_goodbye", "Goodbye", "👣"),
    ("toggle_facts", "Fakta", "🌍"),
]
def agent_feature_states(guild_id: int, cid: int | None) -> dict[str, bool]:
    """Status ON/OFF 8 fitur AI Agent pada satu channel (0 kuota AI)."""
    if not cid:
        return {action: False for action, _, _ in AGENT_FEATURES}
    w_cfg = welcome_agent_guilds.get(guild_id) or {}
    d_cfg = digest_agent_guilds.get(guild_id) or {}
    gb_cfg = goodbye_agent_guilds.get(guild_id) or {}
    f_cfg = facts_guilds.get(guild_id) or {}

    def _at(cfg: dict) -> bool:
        return bool(cfg.get("enabled") and int(cfg.get("channel_id") or 0) == int(cid))

    return {
        "toggle_chat": bool(chat_agent_channels.get(cid, {}).get("enabled")),
        "toggle_gallery": bool(gallery_agent_channels.get(cid, {}).get("enabled")),
        "toggle_youtube": bool(youtube_agent_channels.get(cid, {}).get("enabled")),
        "toggle_search": bool(search_agent_channels.get(cid, {}).get("enabled")),
        "toggle_welcome": _at(w_cfg),
        "toggle_digest": _at(d_cfg),
        "toggle_goodbye": _at(gb_cfg),
        "toggle_facts": _at(f_cfg),
    }
class AgentPanelView(ui_kit.ui.LayoutView):
    """Panel Kontrol AI Agent bergaya dashboard: kartu status + tombol toggle berwarna."""

    def __init__(self, guild: discord.Guild, admin_user_id: int, default_channel_id: int | None = None):
        super().__init__(timeout=600)
        self.guild_id = guild.id
        self.admin_user_id = admin_user_id
        self.selected_channel_id = default_channel_id
        self.notice = ""
        self._build()

    # ---------------------------------------------------------------- helpers
    def _status_text(self) -> str:
        cid = self.selected_channel_id
        if cid is None:
            return "_Belum ada channel dipilih — pilih lewat dropdown di bawah._"
        states = agent_feature_states(self.guild_id, cid)
        lines = [
            ui_kit.status_line(
                f"{emoji} {label}",
                "AKTIF" if states[action] else "nonaktif",
                state="on" if states[action] else "off",
            )
            for action, label, emoji in AGENT_FEATURES
        ]
        return f"**Channel target:** <#{cid}>\n" + "\n".join(lines)

    def _build(self) -> None:
        self.clear_items()
        gid = self.guild_id
        cid = self.selected_channel_id

        header = ui_kit.card(
            gid,
            ui_kit.text(
                ui_kit.title_line(
                    gid,
                    "agent",
                    "Panel Kontrol AI Agent",
                    "Pilih channel target, lalu tekan tombol fitur untuk **ON / OFF** (hijau = aktif, merah = mati).",
                )
            ),
            *( [ui_kit.text(f"> {self.notice}")] if self.notice else [] ),
            ui_kit.sep(),
            ui_kit.text(self._status_text()),
        )

        channel_select = ui.ChannelSelect(
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.forum,
                discord.ChannelType.media,
            ],
            placeholder="1️⃣ Pilih channel / forum target…",
            min_values=1,
            max_values=1,
            custom_id="agent:v2:channel",
        )
        if cid:
            channel_select.placeholder = "1️⃣ Ganti channel target…"[:150]
        channel_select.callback = self.on_pick_channel

        states = agent_feature_states(gid, cid)
        toggle_buttons = [
            ui_kit.toggle_button(
                gid,
                label,
                states[action],
                custom_id=f"agent:v2:{action}",
                callback=(lambda ix, a=action: self.on_toggle(ix, a)),
            )
            for action, label, emoji in AGENT_FEATURES
        ]
        for btn, (_, label, emoji) in zip(toggle_buttons, AGENT_FEATURES):
            btn.emoji = emoji
            btn.label = label[:80]

        controls = ui_kit.card(
            gid,
            ui_kit.text("**⚙️ Pengaturan Cepat**"),
            ui_kit.action_row(channel_select),
            ui_kit.action_row(*toggle_buttons[:4]),
            ui_kit.action_row(*toggle_buttons[4:]),
            ui_kit.action_row(
                ui_kit.button(
                    "Persona",
                    emoji="🎭",
                    style=discord.ButtonStyle.primary,
                    custom_id="agent:v2:persona",
                    callback=self.on_persona,
                ),
                ui_kit.button(
                    "Tambah FAQ",
                    emoji="➕",
                    style=discord.ButtonStyle.success,
                    custom_id="agent:v2:addfaq",
                    callback=self.on_add_faq,
                ),
                ui_kit.button(
                    "Kelola FAQ",
                    emoji="📋",
                    custom_id="agent:v2:faq",
                    callback=self.on_manage_faq,
                ),
                ui_kit.button(
                    "Segarkan",
                    emoji="🔄",
                    custom_id="agent:v2:refresh",
                    callback=self.on_refresh,
                ),
                ui_kit.button(
                    "Tutup",
                    emoji="🚪",
                    style=discord.ButtonStyle.danger,
                    custom_id="agent:v2:close",
                    callback=self.on_close,
                ),
            ),
        )
        self.add_item(header)
        self.add_item(controls)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self._build()
        await ui_kit.edit_panel(
            interaction,
            self,
            embed=build_agent_status_embed(
                interaction.guild,
                selected_channel_id=self.selected_channel_id,
                notice_banner=self.notice or None,
            )
            if interaction.guild
            else None,
        )

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message(
                "⚠️ Panel kontrol ini hanya dapat dioperasikan oleh Admin yang membukanya.",
                ephemeral=True,
            )
            return False
        return True

    async def on_pick_channel(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        picked = interaction.data.get("values", [None])[0] if interaction.data else None
        if not picked:
            return
        self.selected_channel_id = int(picked)
        self.notice = f"📍 Channel target diubah ke <#{picked}>. Tekan tombol fitur untuk ON/OFF."
        await self._refresh(interaction)

    async def on_toggle(self, interaction: discord.Interaction, action: str) -> None:
        if interaction.guild is None:
            return
        cid = self.selected_channel_id
        if cid is None:
            await interaction.response.send_message(
                "⚠️ Pilih channel terlebih dahulu lewat dropdown **1️⃣**.", ephemeral=True
            )
            return
        banner = await apply_agent_toggle(interaction, cid, action)
        if banner is None:
            return
        await save_agent_config_to_disk()
        await save_server_features_to_disk()
        self.notice = banner
        await self._refresh(interaction)

    async def on_persona(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await interaction.response.send_modal(
            EditPersonaModal(interaction.guild.id, selected_channel_id=self.selected_channel_id)
        )

    async def on_add_faq(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            AddServerInfoModal(selected_channel_id=self.selected_channel_id)
        )

    async def on_manage_faq(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await interaction.response.send_message(
            embed=build_faq_list_embed(interaction.guild),
            view=ServerFaqManagerView(interaction.user.id, interaction.guild.id),
            ephemeral=True,
        )

    async def on_refresh(self, interaction: discord.Interaction) -> None:
        self.notice = ""
        await self._refresh(interaction)

    async def on_close(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            view=ui_kit.build_view(
                self.guild_id,
                ui_kit.card(
                    self.guild_id,
                    ui_kit.text(
                        f"### {ui_theme.emoji(self.guild_id, 'close', '🚪')} Panel ditutup\n"
                        "Buka lagi dengan `/agent panel`."
                    ),
                ),
                timeout=None,
            )
        )
