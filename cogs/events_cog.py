import logging
import platform
import discord
from discord.ext import commands

import ai_handler
from community_agent import (
    chat_agent_channels,
    digest_agent_guilds,
    goodbye_agent_guilds,
    gallery_agent_channels,
    generate_community_chat_reply,
    generate_gallery_comment,
    get_agent_channel_lock,
    record_human_channel_activity,
    remove_agent_thread_runtime,
    resolve_agent_channel_id,
    save_agent_config_to_disk,
    search_agent_channels,
    set_chat_channel_config,
    set_digest_config,
    set_gallery_channel_config,
    set_goodbye_config,
    set_search_channel_config,
    set_welcome_config,
    set_youtube_channel_config,
    should_agent_reply_in_chat,
    should_standalone_feature_reply,
    welcome_agent_guilds,
    youtube_agent_channels,
)
from community_tools import (
    handle_channel_delete as handle_community_channel_delete,
    handle_reaction_role,
    handle_starboard_reaction,
    maybe_refresh_sticky,
    save_community_tools_to_disk,
)
from antispam import (
    handle_channel_delete as handle_antispam_channel_delete,
    handle_member_join_guard,
    handle_spam_guard,
    save_antispam_to_disk,
)
from cogs.growth_cog import handle_message_xp
from levels import handle_channel_delete as handle_levels_channel_delete, save_levels_to_disk
from tickets import (
    handle_channel_delete as handle_tickets_channel_delete,
    handle_thread_delete as handle_tickets_thread_delete,
    save_tickets_to_disk,
)
from engagement import (
    handle_channel_delete as handle_engagement_channel_delete,
    match_auto_reply,
    save_engagement_to_disk,
)
from config import BOT_VERSION
from games import active_channel_games, cancel_channel_game, handle_active_game_guess
from storage import remove_thread_data, save_sessions_to_disk
from utils import select_best_forum_tags, split_discord_message
from views import ForumPostSolvedView
from cogs.agent_cog import trigger_member_boost, trigger_member_goodbye, trigger_member_welcome
from cogs.utility_cog import handle_message_tools
from cogs.helpers import get_memory_usage_mb
from cogs.session_cog import handle_private_session_message
from server_features import (
    apply_autorole_to_member,
    autorole_guilds,
    facts_guilds,
    handle_phishing_guard,
    save_server_features_to_disk,
    security_guilds,
    set_facts_config,
)

logger = logging.getLogger("gemini_bot.events")


def register_events_cog(bot: commands.Bot) -> None:
    """Mendaftarkan seluruh event listener Discord (startup, cleanup memori, sambutan, & perutean pesan)."""

    @bot.event
    async def on_ready():
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="Google Gemini AI ✨ | /bantuan",
            )
        )
        ram_mb = get_memory_usage_mb()
        logger.info(
            "✅ Bot v%s aktif sebagai %s (ID: %s) | Python %s | discord.py %s | RAM: %.1f MB",
            BOT_VERSION,
            bot.user,
            bot.user.id if bot.user else "-",
            platform.python_version(),
            discord.__version__,
            ram_mb,
        )
        if not ai_handler.is_gemini_key_configured():
            logger.warning("⚠️ GEMINI_API_KEY belum diisi! Isi di .env atau panel Variables Wispbyte.")

        # Simpan titik pulih identitas server untuk pemulihan Anti-Nuke
        try:
            import antinuke

            saved = 0
            for guild in getattr(bot, "guilds", []) or []:
                antinuke.snapshot_identity(guild)
                saved += 1
            if saved:
                await antinuke.save_antinuke_to_disk()
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Titik pulih identitas dilewati: %s", exc)

        # Pasang kembali panel menu persisten (tombol/dropdown buatan Admin)
        try:
            import menu_builder

            restored = menu_builder.register_menus(bot)
            if restored:
                logger.info("Panel menu interaktif dipulihkan: %d panel.", restored)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pemulihan panel menu dilewati: %s", exc)

        # Sinkronkan cache invite sekali saat start agar pelacakan pengundang akurat
        try:
            import growth_tracker

            total = 0
            for guild in getattr(bot, "guilds", []) or []:
                total += await growth_tracker.sync_invites(guild)
            if total:
                await growth_tracker.save_growth_to_disk()
            logger.info("Cache invite disinkronkan: %d kode terpantau.", total)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Sinkronisasi invite dilewati: %s", exc)

    @bot.event
    async def on_raw_thread_delete(payload: discord.RawThreadDeleteEvent):
        """Membersihkan sisa memori sesi privat, game aktif, & riwayat Forum/Thread saat thread dihapus."""
        tid = payload.thread_id
        cancel_channel_game(tid)
        remove_agent_thread_runtime(tid)
        if handle_tickets_thread_delete(tid):
            await save_tickets_to_disk()
            logger.info("Catatan tiket %s dibersihkan karena thread dihapus.", tid)
        if remove_thread_data(tid):
            await save_sessions_to_disk()
            logger.info("Data sesi privat dibersihkan karena thread %s dihapus.", tid)

    @bot.event
    async def on_guild_role_create(role: discord.Role):
        try:
            import audit_log

            await audit_log.log_role_change(bot, role.guild, "create", role)
        except Exception:  # pragma: no cover
            pass

    @bot.event
    async def on_guild_role_delete(role: discord.Role):
        try:
            import audit_log

            await audit_log.log_role_change(bot, role.guild, "delete", role)
        except Exception:  # pragma: no cover
            pass

    @bot.event
    async def on_guild_channel_create(channel: discord.abc.GuildChannel):
        try:
            import audit_log

            await audit_log.log_channel_change(bot, getattr(channel, "guild", None), "create", channel)
        except Exception:  # pragma: no cover
            pass

    @bot.event
    async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
        """Membersihkan konfigurasi AI Agent & game aktif jika channel publik dihapus dari server."""
        try:
            import audit_log

            await audit_log.log_channel_change(
                bot, getattr(channel, "guild", None), "delete", channel
            )
            if audit_log.handle_channel_delete(getattr(channel, "id", 0)):
                await audit_log.save_audit_to_disk()
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Audit log channel hapus dilewati: %s", exc)
        removed = False
        if channel.id in chat_agent_channels:
            set_chat_channel_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        if channel.id in gallery_agent_channels:
            set_gallery_channel_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        if channel.id in youtube_agent_channels:
            set_youtube_channel_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        if channel.id in search_agent_channels:
            set_search_channel_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        w_cfg = welcome_agent_guilds.get(channel.guild.id)
        if w_cfg and int(w_cfg.get("channel_id") or 0) == channel.id:
            set_welcome_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        d_cfg = digest_agent_guilds.get(channel.guild.id)
        if d_cfg and int(d_cfg.get("channel_id") or 0) == channel.id:
            set_digest_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        gb_cfg = goodbye_agent_guilds.get(channel.guild.id)
        if gb_cfg and int(gb_cfg.get("channel_id") or 0) == channel.id:
            set_goodbye_config(channel.guild.id, channel.id, enabled=False)
            removed = True
        f_cfg = facts_guilds.get(channel.guild.id)
        if f_cfg and int(f_cfg.get("channel_id") or 0) == channel.id:
            set_facts_config(channel.guild.id, channel.id, enabled=False)
            await save_server_features_to_disk()
        sec_cfg = security_guilds.get(channel.guild.id)
        if sec_cfg:
            if int(sec_cfg.get("log_channel_id") or 0) == channel.id:
                sec_cfg["log_channel_id"] = None
                await save_server_features_to_disk()
            if channel.id in (sec_cfg.get("channel_ids") or []):
                sec_cfg["channel_ids"] = [c for c in sec_cfg["channel_ids"] if c != channel.id]
                await save_server_features_to_disk()
        if handle_community_channel_delete(channel):
            await save_community_tools_to_disk()
        if handle_engagement_channel_delete(channel):
            await save_engagement_to_disk()
        if handle_antispam_channel_delete(channel):
            await save_antispam_to_disk()
        if handle_levels_channel_delete(channel):
            await save_levels_to_disk()
        if handle_tickets_channel_delete(channel):
            await save_tickets_to_disk()
        try:
            import raid_guard

            if raid_guard.handle_channel_delete(getattr(channel, "id", 0)):
                await raid_guard.save_raid_to_disk()
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pembersihan Raid Guard dilewati: %s", exc)
        try:
            import antinuke

            if antinuke.handle_channel_delete(getattr(channel, "id", 0)):
                await antinuke.save_antinuke_to_disk()
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pembersihan anti-nuke dilewati: %s", exc)
        try:
            import menu_builder

            if menu_builder.handle_channel_delete(getattr(channel, "id", 0)):
                await menu_builder.save_menus_to_disk()
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pembersihan panel menu dilewati: %s", exc)
        cancel_channel_game(channel.id)
        remove_agent_thread_runtime(channel.id)
        if removed:
            await save_agent_config_to_disk()

    @bot.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        """Menangani Reaction Role & Starboard saat sebuah emoji ditambahkan."""
        if payload.guild_id is None:
            return
        if bot.user is not None and payload.user_id == bot.user.id:
            return  # abaikan reaksi bot sendiri (mis. emoji panel reaction role)
        try:
            from cogs.translate_cog import handle_translate_reaction

            if await handle_translate_reaction(bot, payload):
                return  # reaksi bendera 🇮🇩/🇬🇧 untuk penerjemah
            if await handle_starboard_reaction(bot, payload, added=True):
                return
            await handle_reaction_role(bot, payload, added=True)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Reaction handler gagal: %s", exc)

    @bot.event
    async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
        """Mencabut role / menghapus sorotan saat emoji dilepas."""
        if payload.guild_id is None:
            return
        if bot.user is not None and payload.user_id == bot.user.id:
            return
        try:
            if await handle_starboard_reaction(bot, payload, added=False):
                return
            await handle_reaction_role(bot, payload, added=False)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Reaction handler gagal: %s", exc)

    @bot.event
    async def on_message_delete(message: discord.Message):
        """Mencatat pesan yang dihapus ke Audit Log (0 kuota AI)."""
        try:
            import audit_log

            await audit_log.log_message_delete(bot, message)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Audit log pesan hapus dilewati: %s", exc)

    @bot.event
    async def on_bulk_message_delete(messages):
        """Mencatat hapus massal (purge) ke Audit Log."""
        try:
            import audit_log

            await audit_log.log_bulk_delete(bot, messages)
        except Exception as exc:  # pragma: no cover
            logger.debug("Audit log hapus massal dilewati: %s", exc)

    @bot.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        """Mencatat pesan yang diedit ke Audit Log."""
        try:
            import audit_log

            await audit_log.log_message_edit(bot, before, after)
        except Exception as exc:  # pragma: no cover
            logger.debug("Audit log pesan edit dilewati: %s", exc)

    @bot.event
    async def on_audit_log_entry_create(entry):
        """Anti-Nuke: membaca Audit Log Discord untuk mendeteksi penghancuran server."""
        try:
            import antinuke

            await antinuke.handle_audit_entry(bot, entry)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Anti-Nuke melewati entri audit: %s", exc)

    @bot.event
    async def on_guild_join(guild):
        """Server baru: Slash Command langsung muncul & kirim checklist setup (0 kuota AI)."""
        fixed_commands = 0
        try:
            await bot.tree.sync(guild=discord.Object(id=guild.id))
            fixed_commands = len(getattr(bot.tree, "get_commands", lambda: [])())
        except Exception as exc:  # pragma: no cover - rate limit / izin
            logger.debug("Sinkronisasi command server baru dilewati: %s", exc)

        try:
            import ui_theme

            total = getattr(guild, "member_count", None) or len(getattr(guild, "members", []) or [])
            embed = ui_theme.status_embed(
                guild.id,
                "info",
                "👋 Terima kasih sudah mengundang bot ini!",
                "**Langkah cepat 5 menit** (semua opsional, bot sudah jalan tanpa ini):\n"
                "1. `/agent panel` — pilih channel AI Agent, welcome, & FAQ lewat tombol.\n"
                "2. `/level atur aktif:True` — XP chat & voice + role hadiah.\n"
                "3. `/tiket panel channel:#bantuan` — tiket bantuan berbasis thread.\n"
                "4. `/log channel channel:#bot-log` — audit log server (hapus/edit pesan, dll).\n"
                "5. `/tumbuh atur channel:#log-member` — statistik tumbuh & invite tracker "
                "(butuh izin *Manage Server*).\n\n"
                f"Server ini: **{guild.name}** (`{guild.id}`) • {total} member\n"
                "Bantuan lengkap: `/bantuan` • Cek kesehatan: `/status`",
                footer="0 kuota AI untuk semua fitur di atas • dashboard web opsional",
            )
            target = getattr(guild, "system_channel", None)
            if target is None:
                for channel in getattr(guild, "text_channels", []) or []:
                    perms = getattr(channel, "permissions_for", lambda _m: None)(guild.me)
                    if perms is not None and getattr(perms, "send_messages", False):
                        target = channel
                        break
            if target is not None:
                await target.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Checklist server baru dilewati: %s", exc)

        logger.info(
            "Bergabung ke server baru: %s (%s) • %s member • %d command disinkronkan.",
            getattr(guild, "name", "?"),
            getattr(guild, "id", "?"),
            getattr(guild, "member_count", "?"),
            fixed_commands,
        )

    @bot.event
    async def on_invite_create(invite):
        """Memperbarui cache invite agar pelacakan pengundang tetap akurat."""
        try:
            import growth_tracker

            growth_tracker.track_invite_create(getattr(getattr(invite, "guild", None), "id", 0), invite)
        except Exception as exc:  # pragma: no cover
            logger.debug("Cache invite (create) dilewati: %s", exc)

    @bot.event
    async def on_invite_delete(invite):
        try:
            import growth_tracker

            growth_tracker.track_invite_delete(getattr(getattr(invite, "guild", None), "id", 0), invite)
        except Exception as exc:  # pragma: no cover
            logger.debug("Cache invite (delete) dilewati: %s", exc)

    @bot.event
    async def on_member_join(member: discord.Member):
        """Menyambut member baru, memasang Auto Role, & mendeteksi lonjakan join (raid)."""
        # Raid Guard: deteksi lonjakan join & tahan Auto Role saat mode darurat
        raid_state = None
        try:
            import raid_guard

            raid_state = await raid_guard.handle_member_join(bot, member)
            if raid_state is not None:
                await raid_guard.save_raid_to_disk()
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Raid Guard join dilewati: %s", exc)

        skip_autorole = False
        try:
            import raid_guard

            skip_autorole = raid_guard.should_skip_autorole(member.guild.id)
        except Exception:  # pragma: no cover
            skip_autorole = False

        if (
            not skip_autorole
            and not getattr(member, "bot", False)
            and member.guild.id in autorole_guilds
        ):
            await apply_autorole_to_member(member)
        try:
            await handle_member_join_guard(bot, member)  # hanya melapor, tidak menendang
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Anti-Raid gagal memeriksa member join: %s", exc)

        # Pelacakan pertumbuhan: siapa pengundangnya + statistik join (0 kuota AI)
        try:
            import growth_tracker

            if growth_tracker.is_enabled(member.guild.id):
                inviter_id, code = await growth_tracker.detect_inviter(member.guild, member)
                growth_tracker.record_join(member.guild.id, member.id, inviter_id, code)
                await growth_tracker.save_growth_to_disk()
                await _send_growth_log(bot, member.guild, member, inviter_id, joined=True)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pelacakan pertumbuhan join dilewati: %s", exc)

        await trigger_member_welcome(bot, member.guild, member)

    @bot.event
    async def on_member_update(before: discord.Member, after: discord.Member):
        try:
            import audit_log

            await audit_log.log_member_update(bot, before, after)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Audit log member update dilewati: %s", exc)

        """Mendeteksi boost server baru & mengirim pesan terima kasih (jika diaktifkan)."""
        before_boost = getattr(before, "premium_since", None)
        after_boost = getattr(after, "premium_since", None)
        if after_boost is None or before_boost is not None:
            return
        try:
            await trigger_member_boost(bot, after.guild, after)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Pesan boost gagal dikirim: %s", exc)

    @bot.event
    async def on_voice_state_update(member, before, after):
        """Memulai/menghentikan hitungan XP voice (0 kuota AI)."""
        try:
            import voice_activity

            voice_activity.handle_voice_state(member, before, after, guild=getattr(member, "guild", None))
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pelacakan XP voice dilewati: %s", exc)
        try:
            import audit_log

            await audit_log.log_voice_change(bot, member, before, after)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Audit log voice dilewati: %s", exc)

    @bot.event
    async def on_member_remove(member: discord.Member):
        """Audit log member keluar + pesan perpisahan AI (jika aktif)."""
        try:
            import audit_log

            await audit_log.log_member_remove(bot, member)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Audit log member keluar dilewati: %s", exc)
        try:
            import growth_tracker

            if growth_tracker.is_enabled(member.guild.id):
                growth_tracker.record_leave(member.guild.id, member.id)
                await growth_tracker.save_growth_to_disk()
                await _send_growth_log(bot, member.guild, member, None, joined=False)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Pelacakan pertumbuhan keluar dilewati: %s", exc)

        await trigger_member_goodbye(bot, member.guild, member)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        # 0. Sticky message: turunkan ulang pesan petunjuk ke bawah channel
        if message.guild is not None and isinstance(message.channel, discord.TextChannel):
            try:
                await maybe_refresh_sticky(bot, message)
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Sticky message gagal diperbarui: %s", exc)

        # Tiket: catat aktivitas terakhir & respons pertama staf (SLA, 0 kuota AI)
        if message.guild is not None:
            try:
                import tickets as ticket_store

                if ticket_store.maybe_track_ticket_message(message):
                    await ticket_store.save_tickets_to_disk()
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.debug("Pencatatan tiket dilewati: %s", exc)

        # AFK (lepas status + beri tahu mentioner) & thread otomatis (0 kuota AI)
        if message.guild is not None:
            try:
                await handle_message_tools(message)
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Perkakas pesan (AFK/thread) gagal: %s", exc)

        # Auto-terjemahan per channel (opsional, default MATI agar kuota aman)
        if message.guild is not None:
            try:
                from cogs.translate_cog import maybe_auto_translate

                if await maybe_auto_translate(bot, message):
                    return
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Auto-terjemahan dilewati: %s", exc)

        # Cadangan Auto-Welcome lewat pesan System Join Discord (bekerja walau Server Members Intent belum aktif)
        if message.type == discord.MessageType.new_member and message.guild is not None:
            await trigger_member_welcome(bot, message.guild, message.author)
            return

        # Jalankan command prefix (seperti !setup_panel) tanpa memicu AI
        try:
            import prefixes as prefix_store

            is_prefix_cmd = prefix_store.is_prefix_command(
                message.content, getattr(message.guild, "id", None)
            )
        except Exception:  # pragma: no cover - jaring aman
            is_prefix_cmd = message.content.strip().startswith("!")
        if is_prefix_cmd:
            await bot.process_commands(message)
            return

        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        # 1. Rute Ruang Sesi Privat (Thread 'ai-' & 'draw-')
        if await handle_private_session_message(bot, message):
            return

        # 1B. Penjaga Anti-Phishing (berjalan di channel/thread publik sebelum fitur AI lain)
        if message.guild is not None:
            try:
                if await handle_phishing_guard(message):
                    return
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Anti-Phishing gagal memeriksa pesan: %s", exc)

        # 1B-2. Penjaga Anti-Spam ringan (mode default: hanya lapor ke channel log).
        #       Admin, staf, bot, & channel/role pengecualian selalu diabaikan sehingga
        #       obrolan antar-member tidak pernah terusik.
        if message.guild is not None:
            try:
                if await handle_spam_guard(message, bot=bot):
                    return
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Anti-Spam gagal memeriksa pesan: %s", exc)

        # 1C. XP Leveling (hanya channel/role yang diizinkan, ada jeda anti-farming)
        if message.guild is not None:
            try:
                await handle_message_xp(bot, message)
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Pemberian XP level gagal: %s", exc)

        # 1D. Balasan Otomatis berbasis kata kunci (khusus channel yang diaktifkan Admin).
        #     Dijalankan sebelum AI & hanya bila benar-benar cocok, sehingga obrolan
        #     antar-member tidak pernah terganggu (ada jeda aman per channel).
        if message.guild is not None:
            try:
                auto_reply = match_auto_reply(message.channel.id, message.content or "")
                if auto_reply:
                    await message.reply(
                        auto_reply[:1900],
                        mention_author=False,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    await save_engagement_to_disk()
                    return
            except (discord.Forbidden, discord.HTTPException):
                pass
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.warning("Auto-responder gagal: %s", exc)

        # 2. Rute AI Agent Komunitas di Text Channel, Channel Forum/Media, & Thread Publik
        if isinstance(message.channel, (discord.TextChannel, discord.Thread)) and bot.user is not None:
            cfg_cid, _, is_forum_post = resolve_agent_channel_id(message.channel)
            conv_id = message.channel.id
            is_starter_forum_post = bool(is_forum_post and message.id == conv_id)
            http_session = getattr(bot, "http_session", None)

            async def _safe_reply_or_send(
                content_chunk: str,
                prefer_reply: bool,
                *,
                view: discord.ui.View | None = None,
            ) -> None:
                send_kw: dict = {}
                if view is not None:
                    send_kw["view"] = view
                if prefer_reply:
                    try:
                        await message.reply(content_chunk, mention_author=False, **send_kw)
                        return
                    except discord.HTTPException:
                        pass
                await message.channel.send(content_chunk, **send_kw)

            async def _maybe_auto_tag_forum_starter() -> None:
                if not is_starter_forum_post or not isinstance(message.channel, discord.Thread):
                    return
                if getattr(message.channel, "applied_tags", None):
                    return
                parent = getattr(message.channel, "parent", None)
                avail_tags = getattr(parent, "available_tags", None) or []
                if not avail_tags:
                    return
                picked = select_best_forum_tags(message.channel.name, message.content or "", avail_tags)
                if picked:
                    try:
                        await message.channel.edit(applied_tags=picked)
                    except discord.HTTPException:
                        pass

            if cfg_cid is not None:
                if cfg_cid in chat_agent_channels and cfg_cid in gallery_agent_channels and message.attachments:
                    record_human_channel_activity(cfg_cid)

                # 2A. Gallery Auto-Comment (Foto, Gambar, & Video di Text Channel maupun Forum/Media Showcase)
                if cfg_cid in gallery_agent_channels and message.attachments:
                    lock = get_agent_channel_lock(conv_id)
                    async with lock:
                        async with message.channel.typing():
                            await _maybe_auto_tag_forum_starter()
                            comment_text, reaction_emoji = await generate_gallery_comment(
                                message,
                                bot.user,
                                http_session=http_session,
                            )
                            if comment_text:
                                if reaction_emoji:
                                    try:
                                        await message.add_reaction(reaction_emoji)
                                    except (discord.Forbidden, discord.HTTPException):
                                        pass
                                await _safe_reply_or_send(comment_text[:1900], True)
                                return

            # 2B. Mini-Game Tongkrongan Aktif
            if conv_id in active_channel_games:
                if cfg_cid is not None and cfg_cid in chat_agent_channels:
                    record_human_channel_activity(cfg_cid)
                if await handle_active_game_guess(message):
                    return

            if cfg_cid is not None:
                # 2C. Auto-Chat Komunitas & Postingan Forum Natural
                if cfg_cid in chat_agent_channels:
                    should_reply, use_reply_ref = should_agent_reply_in_chat(message, bot.user)
                    if should_reply:
                        lock = get_agent_channel_lock(conv_id)
                        async with lock:
                            async with message.channel.typing():
                                await _maybe_auto_tag_forum_starter()
                                reply_text = await generate_community_chat_reply(
                                    message,
                                    bot.user,
                                    http_session=http_session,
                                )
                                if reply_text:
                                    chunks = split_discord_message(reply_text)
                                    last_idx = len(chunks) - 1
                                    for idx, chunk in enumerate(chunks):
                                        solved_view = (
                                            ForumPostSolvedView()
                                            if (is_starter_forum_post and idx == last_idx)
                                            else None
                                        )
                                        await _safe_reply_or_send(
                                            chunk,
                                            idx == 0 and use_reply_ref,
                                            view=solved_view,
                                        )
                        return

                # 2D. Channel / Forum Khusus YouTube atau Pencarian Berita (Aktif walau tanpa /agent chat)
                elif cfg_cid in youtube_agent_channels or cfg_cid in search_agent_channels:
                    if should_standalone_feature_reply(message, bot.user):
                        lock = get_agent_channel_lock(conv_id)
                        async with lock:
                            async with message.channel.typing():
                                await _maybe_auto_tag_forum_starter()
                                reply_text = await generate_community_chat_reply(
                                    message,
                                    bot.user,
                                    http_session=http_session,
                                )
                                if reply_text:
                                    chunks = split_discord_message(reply_text)
                                    last_idx = len(chunks) - 1
                                    for idx, chunk in enumerate(chunks):
                                        solved_view = (
                                            ForumPostSolvedView()
                                            if (is_starter_forum_post and idx == last_idx)
                                            else None
                                        )
                                        await _safe_reply_or_send(
                                            chunk,
                                            idx == 0,
                                            view=solved_view,
                                        )
                        return

        await bot.process_commands(message)

async def _send_growth_log(bot, guild, member, inviter_id, *, joined: bool) -> None:
    """Mengirim log join/keluar ke channel yang diatur `/tumbuh atur` (opsional)."""
    try:
        import growth_tracker

        channel_id = (growth_tracker.get_config(guild.id) or {}).get("log_channel_id")
        if not channel_id:
            return
        channel = bot.get_channel(int(channel_id)) if callable(getattr(bot, "get_channel", None)) else None
        if channel is None:
            return
        if joined:
            lines = [f"📥 **{getattr(member, 'display_name', 'Member')}** bergabung."]
            if inviter_id:
                lines.append(f"Diundang oleh <@{int(inviter_id)}>.")
            created = getattr(member, "created_at", None)
            if created is not None:
                try:
                    age = max(0, int((discord.utils.utcnow() - created).total_seconds() // 86400))
                    lines.append(f"Umur akun: `{age}` hari" + (" ⚠️ baru" if age < 7 else ""))
                except Exception:  # pragma: no cover
                    pass
            color = discord.Color.green()
        else:
            lines = [f"📤 **{getattr(member, 'display_name', 'Member')}** keluar dari server."]
            color = discord.Color.orange()
        embed = discord.Embed(description="\n".join(lines), color=color)
        embed.set_footer(text="Pertumbuhan server • 0 kuota AI")
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Log pertumbuhan dilewati: %s", exc)
