from discord.ext import commands

from cogs.agent_cog import agent_group, register_agent_cog, trigger_member_welcome
from cogs.antinuke_cog import nuke_group, register_antinuke_cog
from cogs.audit_cog import log_group, register_audit_cog
from cogs.analytics_cog import register_analytics_cog, tumbuh_group
from cogs.economy_cog import ekonomi_group, register_economy_cog
from cogs.community_cog import (
    info_group,
    ingatkan_group,
    panelrole_group,
    perawatan_group,
    register_community_cog,
    slash_poll,
    starboard_group,
    sticky_group,
    verifikasi_group,
)
from cogs.engagement_cog import (
    giveaway_group,
    jawab_group,
    pengumuman_group,
    register_engagement_cog,
    ultah_group,
)
from cogs.growth_cog import level_group, register_growth_cog, tiket_group
from cogs.insights_cog import (
    faq_group,
    pemakaian_group,
    register_insights_cog,
)
from cogs.events_cog import register_events_cog
from cogs.games_cog import game_group, register_games_cog
from cogs.menu_cog import menu_group, register_menu_cog
from cogs.confessions_cog import curhat_group, register_confessions_cog
from cogs.info_channel_cog import kanal_info_group, register_info_channel_cog
from cogs.highlights_cog import pantau_group, register_highlights_cog
from cogs.snipe_cog import register_snipe_cog, snipe_group
from cogs.lencana_cog import lencana_group, register_lencana_cog
from cogs.moderation_cog import banding_cmd, lapor_cmd, mod_group, register_moderation_cog
from cogs.raid_cog import raid_group, register_raid_cog
from cogs.language_cog import bahasa_group, register_language_cog
from cogs.prefix_cog import prefix_group, register_prefix_cog
from cogs.export_cog import analitik_group, register_export_cog
from cogs.music_cog import musik_group, register_music_cog
from cogs.panel_cog import panel_group, register_panel_cog, tampilan_group
from cogs.server_cog import (
    autorole_group,
    fakta_group,
    keamanan_group,
    register_server_cog,
    serverstats_group,
)
from cogs.session_cog import register_session_cog, sesi_group
from cogs.suggestions_cog import (
    embed_group,
    register_suggestions_cog,
    saran_group,
)
from cogs.social_cog import register_social_cog, sosial_group
from cogs.tags_cog import register_tags_cog, tag_group
from cogs.tempvoice_cog import register_tempvoice_cog, tempvoice_group
from cogs.translate_cog import register_translate_cog, terjemah_group
from cogs.utility_cog import (
    afk_group,
    backup_group,
    lockdown_group,
    register_utility_cog,
    thread_group,
)
from cogs.tools_cog import (
    context_explain_message,
    context_fact_check_message,
    context_translate_indonesia,
    register_tools_cog,
    ringkas_chat_cmd,
    ringkas_group,
    ringkas_link_cmd,
    slash_bantuan,
    slash_cari,
    slash_status,
)


def register_all_cogs(bot: commands.Bot) -> None:
    """Mendaftarkan seluruh modul fitur (Cogs) secara rapi & sinkron ke instance bot."""
    register_session_cog(bot)
    register_tools_cog(bot)
    register_agent_cog(bot)
    register_games_cog(bot)
    register_server_cog(bot)
    register_community_cog(bot)
    register_engagement_cog(bot)
    register_growth_cog(bot)
    register_insights_cog(bot)
    register_translate_cog(bot)
    register_audit_cog(bot)
    register_economy_cog(bot)
    register_analytics_cog(bot)
    register_menu_cog(bot)
    register_antinuke_cog(bot)
    register_raid_cog(bot)
    register_language_cog(bot)
    register_prefix_cog(bot)
    register_export_cog(bot)
    register_music_cog(bot)
    register_moderation_cog(bot)
    register_tags_cog(bot)
    register_lencana_cog(bot)
    register_highlights_cog(bot)
    register_snipe_cog(bot)
    register_confessions_cog(bot)
    register_info_channel_cog(bot)
    register_tempvoice_cog(bot)
    register_suggestions_cog(bot)
    register_utility_cog(bot)
    register_panel_cog(bot)
    register_social_cog(bot)
    register_events_cog(bot)


__all__ = [
    "agent_group",
    "mod_group",
    "tag_group",
    "lencana_group",
    "pantau_group",
    "snipe_group",
    "curhat_group",
    "kanal_info_group",
    "lapor_cmd",
    "banding_cmd",
    "tempvoice_group",
    "saran_group",
    "embed_group",
    "afk_group",
    "thread_group",
    "lockdown_group",
    "backup_group",
    "sosial_group",
    "giveaway_group",
    "faq_group",
    "pemakaian_group",
    "level_group",
    "tiket_group",
    "jawab_group",
    "pengumuman_group",
    "ultah_group",
    "autorole_group",
    "info_group",
    "ingatkan_group",
    "musik_group",
    "panel_group",
    "tampilan_group",
    "panelrole_group",
    "perawatan_group",
    "slash_poll",
    "starboard_group",
    "sticky_group",
    "verifikasi_group",
    "fakta_group",
    "keamanan_group",
    "serverstats_group",
    "context_explain_message",
    "context_fact_check_message",
    "context_translate_indonesia",
    "game_group",
    "register_all_cogs",
    "ringkas_chat_cmd",
    "ringkas_group",
    "ringkas_link_cmd",
    "sesi_group",
    "slash_bantuan",
    "slash_cari",
    "slash_status",
    "trigger_member_welcome",
]
