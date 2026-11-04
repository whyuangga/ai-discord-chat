from discord.ext import commands

from cogs.agent_cog import agent_group, register_agent_cog, trigger_member_welcome
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
from cogs.events_cog import register_events_cog
from cogs.games_cog import game_group, register_games_cog
from cogs.server_cog import (
    autorole_group,
    fakta_group,
    keamanan_group,
    register_server_cog,
    serverstats_group,
)
from cogs.session_cog import register_session_cog, sesi_group
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
    register_events_cog(bot)


__all__ = [
    "agent_group",
    "autorole_group",
    "info_group",
    "ingatkan_group",
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
