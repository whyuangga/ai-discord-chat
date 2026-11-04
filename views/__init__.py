"""Paket view UI Gemini AI Bot.

Semua nama lama tetap dapat diimpor lewat `from views import X`.
"""
from .session import (  # noqa: F401
    build_main_panel_embed,
    _sanitize_username_for_thread,
    _validate_target_channel,
    _get_user_active_threads,
    can_manage_session,
    close_and_recap_session,
    EndSessionView,
    ChatPersonaSwitchView,
    ImageSettingsView,
    AIModelSelectView,
    MainPanelControlView,
)
from .community import (  # noqa: F401
    _build_solved_disabled_view,
    VerificationGateView,
    ForumPostSolvedView,
)
from .tickets import (  # noqa: F401
    handle_ticket_open,
    TicketPanelView,
    TicketPanelFallbackView,
    send_ticket_panel,
    TicketActionsView,
)
from .engagement import (  # noqa: F401
    GiveawayJoinView,
)
from .music import (  # noqa: F401
    QueuePaginationView,
    MusicPlayerView,
    MUSIC_PANEL_ORDER,
    build_music_panel_view,
)
from .agent import (  # noqa: F401
    _build_channel_spotlight_summary,
    build_agent_status_embed,
    EditPersonaModal,
    AddServerInfoModal,
    build_faq_list_embed,
    ServerFaqManagerView,
    apply_agent_toggle,
    AgentAdminPanelView,
    AGENT_FEATURES,
    agent_feature_states,
    AgentPanelView,
)
from .help import (  # noqa: F401
    build_help_embed,
    HELP_CATEGORIES,
    help_select_options,
    HelpPanelView,
    HelpMenuView,
)

__all__ = [
    "AGENT_FEATURES",
    "AIModelSelectView",
    "AddServerInfoModal",
    "AgentAdminPanelView",
    "AgentPanelView",
    "ChatPersonaSwitchView",
    "EditPersonaModal",
    "EndSessionView",
    "ForumPostSolvedView",
    "GiveawayJoinView",
    "HELP_CATEGORIES",
    "HelpMenuView",
    "HelpPanelView",
    "ImageSettingsView",
    "MUSIC_PANEL_ORDER",
    "MainPanelControlView",
    "MusicPlayerView",
    "QueuePaginationView",
    "ServerFaqManagerView",
    "TicketActionsView",
    "TicketPanelFallbackView",
    "TicketPanelView",
    "VerificationGateView",
    "_build_channel_spotlight_summary",
    "_build_solved_disabled_view",
    "_get_user_active_threads",
    "_sanitize_username_for_thread",
    "_validate_target_channel",
    "agent_feature_states",
    "apply_agent_toggle",
    "build_agent_status_embed",
    "build_faq_list_embed",
    "build_help_embed",
    "build_main_panel_embed",
    "build_music_panel_view",
    "can_manage_session",
    "close_and_recap_session",
    "handle_ticket_open",
    "help_select_options",
    "send_ticket_panel",
]
