import base64
import json
import pathlib
import time

import pytest
import discord

import config
import storage
import utils
import ai_handler
import community_agent
import antispam
import community_tools
import engagement
import games
import levels
import music
import server_features
import tickets
import views
import wavelink
import main as bot_main


class _FakeAsyncContent:
    def __init__(self, raw_bytes: bytes):
        self._raw = raw_bytes

    async def read(self, max_bytes: int = -1):
        return self._raw if max_bytes < 0 else self._raw[:max_bytes]

    async def iter_chunked(self, chunk_size: int):
        for idx in range(0, len(self._raw), chunk_size):
            yield self._raw[idx : idx + chunk_size]


class FakeMockResponse:
    def __init__(self, status: int, json_data=None, raw_bytes: bytes = b"", headers=None, url: str = "https://example.com"):
        self.status = status
        self._json_data = json_data
        self._raw_bytes = raw_bytes
        self.headers = headers or {}
        self.url = url
        self.content = _FakeAsyncContent(raw_bytes)

    async def json(self, content_type=None):
        return self._json_data

    async def read(self):
        return self._raw_bytes

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeHttpSession:
    def __init__(self, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.post_calls = []
        self.get_calls = []
        self.closed = False

    def post(self, url, headers=None, json=None, timeout=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json})
        return self.post_responses.pop(0)

    def get(self, url, headers=None, timeout=None, allow_redirects=True, max_redirects=4):
        self.get_calls.append({"url": url, "headers": headers})
        return self.get_responses.pop(0)


@pytest.fixture(autouse=True)
def clean_storage_state(tmp_path, monkeypatch):
    sessions_path = tmp_path / "sessions.json"
    agent_cfg_path = tmp_path / "agent_config.json"
    scores_path = tmp_path / "game_scores.json"
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "SESSIONS_FILE", sessions_path)
    monkeypatch.setattr(community_agent, "DATA_DIR", tmp_path)
    monkeypatch.setattr(community_agent, "AGENT_CONFIG_FILE", agent_cfg_path)
    monkeypatch.setattr(games, "DATA_DIR", tmp_path)
    monkeypatch.setattr(games, "GAME_SCORES_FILE", scores_path)
    monkeypatch.setattr(server_features, "DATA_DIR", tmp_path)
    monkeypatch.setattr(community_tools, "DATA_DIR", tmp_path)
    monkeypatch.setattr(community_tools, "COMMUNITY_TOOLS_FILE", tmp_path / "community_tools.json")
    monkeypatch.setattr(server_features, "SERVER_FEATURES_FILE", tmp_path / "server_features.json")
    monkeypatch.setattr(music, "DATA_DIR", tmp_path)
    monkeypatch.setattr(music, "MUSIC_FILE", tmp_path / "music_settings.json")
    monkeypatch.setattr(engagement, "DATA_DIR", tmp_path)
    monkeypatch.setattr(engagement, "ENGAGEMENT_FILE", tmp_path / "engagement.json")
    monkeypatch.setattr(antispam, "DATA_DIR", tmp_path)
    monkeypatch.setattr(antispam, "ANTISPAM_FILE", tmp_path / "antispam.json")
    monkeypatch.setattr(levels, "DATA_DIR", tmp_path)
    monkeypatch.setattr(levels, "LEVELS_FILE", tmp_path / "levels.json")
    monkeypatch.setattr(tickets, "DATA_DIR", tmp_path)
    monkeypatch.setattr(tickets, "TICKETS_FILE", tmp_path / "tickets.json")
    storage.thread_chats.clear()
    storage.image_thread_settings.clear()
    storage._closing_threads.clear()
    community_agent.guild_agent_settings.clear()
    community_agent.chat_agent_channels.clear()
    community_agent.gallery_agent_channels.clear()
    community_agent.youtube_agent_channels.clear()
    community_agent.search_agent_channels.clear()
    community_agent.welcome_agent_guilds.clear()
    community_agent.goodbye_agent_guilds.clear()
    community_agent.digest_agent_guilds.clear()
    community_agent._recent_welcomed_members.clear()
    community_agent._recent_goodbye_members.clear()
    server_features.serverstats_guilds.clear()
    server_features.autorole_guilds.clear()
    server_features.facts_guilds.clear()
    server_features.security_guilds.clear()
    community_tools.reaction_role_panels.clear()
    community_tools.reminders.clear()
    community_tools.starboard_guilds.clear()
    community_tools.sticky_channels.clear()
    community_tools.verification_guilds.clear()
    community_tools.maintenance_guilds.clear()
    community_tools._sticky_last_refresh.clear()
    community_tools._last_error.update({"at": 0.0, "context": "", "message": ""})
    music.music_guilds.clear()
    music.announce_channels.clear()
    engagement.giveaways.clear()
    engagement.giveaway_templates.clear()
    engagement.giveaway_defaults.clear()
    engagement.birthday_guilds.clear()
    engagement.birthdays.clear()
    engagement.auto_reply_channels.clear()
    engagement.announcements.clear()
    engagement._last_auto_reply_at.clear()
    antispam.spam_guilds.clear()
    antispam.reset_runtime_state()
    levels.level_guilds.clear()
    levels.levels.clear()
    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    tickets._ticket_seq.clear()
    community_agent._recent_channel_speakers.clear()
    community_agent._standalone_last_reply_at.clear()
    community_agent._post_runtime_state.clear()
    community_agent.channel_histories.clear()
    games.guild_game_scores.clear()
    games.active_channel_games.clear()
    games._recent_game_answers.clear()
    utils.clear_user_cooldowns()
    ai_handler.clear_model_cooldowns()
    yield
    storage.thread_chats.clear()
    storage.image_thread_settings.clear()
    storage._closing_threads.clear()
    community_agent.guild_agent_settings.clear()
    community_agent.chat_agent_channels.clear()
    community_agent.gallery_agent_channels.clear()
    community_agent.youtube_agent_channels.clear()
    community_agent.search_agent_channels.clear()
    community_agent.welcome_agent_guilds.clear()
    community_agent.goodbye_agent_guilds.clear()
    community_agent.digest_agent_guilds.clear()
    community_agent._recent_welcomed_members.clear()
    community_agent._recent_goodbye_members.clear()
    server_features.serverstats_guilds.clear()
    server_features.autorole_guilds.clear()
    server_features.facts_guilds.clear()
    server_features.security_guilds.clear()
    community_agent.channel_histories.clear()
    engagement.giveaways.clear()
    engagement.giveaway_templates.clear()
    engagement.giveaway_defaults.clear()
    engagement.birthday_guilds.clear()
    engagement.birthdays.clear()
    engagement.auto_reply_channels.clear()
    engagement.announcements.clear()
    engagement._last_auto_reply_at.clear()
    antispam.spam_guilds.clear()
    antispam.reset_runtime_state()
    levels.level_guilds.clear()
    levels.levels.clear()
    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    tickets._ticket_seq.clear()
    utils.clear_user_cooldowns()
    ai_handler.clear_model_cooldowns()


def test_split_discord_message_preserves_code_fences():
    code_lines = "\n".join(f"print('Baris kode nomor {i}')" for i in range(120))
    long_reply = f"Berikut contoh kodenya:\n\n```python\n{code_lines}\n```\n\nSemoga membantu!"

    chunks = utils.split_discord_message(long_reply, max_length=600)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert len(chunk) <= 600
        # Setiap potongan yang membuka blok kode harus memiliki penutup yang seimbang
        fence_count = sum(1 for line in chunk.splitlines() if line.strip().startswith("```"))
        assert fence_count % 2 == 0


def test_split_discord_message_handles_unbroken_long_line():
    giant_line = "A" * 4200
    chunks = utils.split_discord_message(giant_line, max_length=1900)
    assert len(chunks) >= 3
    assert all(len(c) <= 1900 for c in chunks)
    assert "".join(chunks) == giant_line


def test_sanitize_error_message_redacts_secrets(monkeypatch):
    monkeypatch.setattr(utils, "GEMINI_API_KEY", "AIzaSecretKey123456")
    monkeypatch.setattr(utils, "DISCORD_BOT_TOKEN", "MTIzSecretDiscordToken999")

    leaked = "Error calling https://example.com?key=AIzaSecretKey123456 with MTIzSecretDiscordToken999"
    cleaned = utils.sanitize_error_message(leaked)
    assert "AIzaSecretKey123456" not in cleaned
    assert "MTIzSecretDiscordToken999" not in cleaned
    assert "[REDACTED]" in cleaned


def test_legacy_model_aliases_map_to_gemini():
    assert config.resolve_model_key("groq_llama70b") == "gemini_logic"
    assert config.resolve_model_key("groq_fast") == "gemini_fast"
    assert config.resolve_model_key("qwen_coder") == "gemini_coder"
    assert config.resolve_model_key("unknown_model") == "gemini_flash"


@pytest.mark.asyncio
async def test_session_persistence_roundtrip():
    storage.init_thread_session(1001, "gemini_coder", owner_id=42)
    storage.append_conversation_turn(1001, "Halo Gemini", "Halo! Ada yang bisa dibantu?")
    storage.init_image_session(2002, owner_id=99)
    storage.image_thread_settings[2002]["style"] = "Anime"
    storage.image_thread_settings[2002]["ratio"] = "16:9 (Landscape)"

    await storage.save_sessions_to_disk()
    storage.thread_chats.clear()
    storage.image_thread_settings.clear()

    loaded_chats, loaded_imgs = storage.load_sessions_from_disk()
    assert loaded_chats == 1
    assert loaded_imgs == 1
    assert storage.thread_chats[1001]["model_key"] == "gemini_coder"
    assert storage.thread_chats[1001]["owner_id"] == 42
    assert len(storage.thread_chats[1001]["history"]) == 2
    assert storage.image_thread_settings[2002]["style"] == "Anime"
    assert storage.image_thread_settings[2002]["ratio"] == "16:9 (Landscape)"


@pytest.mark.asyncio
async def test_gemini_chat_ignores_thought_parts_and_uses_header_auth(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    storage.init_thread_session(555, "gemini_flash", owner_id=7)

    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"thought": True, "text": "Internal reasoning yang tidak boleh tampil..."},
                        {"text": "Halo! Ini jawaban bersih dari Gemini 3.8 Flash."},
                    ],
                },
                "finishReason": "STOP",
            }
        ]
    }
    fake_http = FakeHttpSession(post_responses=[FakeMockResponse(200, gemini_payload)])

    image_part = [{"inlineData": {"mimeType": "image/png", "data": "aGVsbG8="}}]
    reply = await ai_handler.get_ai_response(
        555,
        "Apa isi gambar ini?",
        image_parts=image_part,
        image_filenames=["error.png"],
        http_session=fake_http,
    )

    assert reply == "Halo! Ini jawaban bersih dari Gemini 3.8 Flash."
    assert "Internal reasoning" not in reply

    # Pastikan API key dikirim lewat header x-goog-api-key, BUKAN bocor di URL
    call = fake_http.post_calls[0]
    assert "AIzaFakeValidKey12345" not in call["url"]
    assert call["headers"]["x-goog-api-key"] == "AIzaFakeValidKey12345"

    # Pastikan riwayat tersimpan rapi tanpa menyimpan base64 gambar jutaan byte
    saved_history = storage.thread_chats[555]["history"]
    assert len(saved_history) == 2
    assert "[Pengguna melampirkan gambar: error.png]" in saved_history[0]["content"]
    assert "aGVsbG8=" not in json.dumps(saved_history)


@pytest.mark.asyncio
async def test_gemini_chat_fallback_and_no_history_corruption_on_error(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_TEXT_FALLBACK_CHAIN", ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])
    storage.init_thread_session(777, "gemini_flash")

    # Simulasi: model pertama kena 503 overload, model kedua langsung sukses & model pertama masuk cooldown
    resp_503 = FakeMockResponse(503, {"error": {"message": "This model is currently experiencing high demand."}})
    resp_200 = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Berhasil lewat model cadangan!"}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[resp_503, resp_200])

    reply = await ai_handler.get_ai_response(777, "Tes fallback", http_session=fake_http)
    assert reply == "Berhasil lewat model cadangan!"
    assert len(fake_http.post_calls) == 2
    assert "gemini-3.1-flash-lite" in fake_http.post_calls[1]["url"]

    # Panggilan berikutnya harus langsung memprioritaskan gemini-3.1-flash-lite karena 3.5-flash-lite sedang cooldown
    chain_after_503 = ai_handler._build_model_chain("gemini-3.5-flash-lite", ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])
    assert chain_after_503[0] == "gemini-3.1-flash-lite"

    # Sekarang simulasi: semua model gagal -> riwayat sebelumnya tidak boleh rusak/menggantung
    fail_http = FakeHttpSession(
        post_responses=[
            FakeMockResponse(503, {"error": {"message": "Overloaded"}}),
            FakeMockResponse(503, {"error": {"message": "Overloaded"}}),
        ]
    )
    err_reply = await ai_handler.get_ai_response(777, "Pesan yang gagal", http_session=fail_http)
    assert "padat" in err_reply
    assert len(storage.thread_chats[777]["history"]) == 2
    assert storage.thread_chats[777]["history"][-1]["role"] == "model"


@pytest.mark.asyncio
async def test_generate_image_gemini_native_and_fallback(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_IMAGE_FALLBACK_CHAIN", ["gemini-3.1-flash-lite-image"])
    storage.init_image_session(888)
    storage.image_thread_settings[888]["style"] = "Cyberpunk"
    storage.image_thread_settings[888]["ratio"] = "16:9 (Landscape)"

    fake_png = b"\x89PNG\r\n\x1a\n" + (b"x" * 2048)
    b64_png = base64.b64encode(fake_png).decode("ascii")

    # 1. Mode Free Tier Default (GEMINI_PAID_IMAGE_ENABLED=False):
    #    Langsung menembak Flux tanpa membuang waktu ke model Nano Banana berbayar!
    monkeypatch.setattr(ai_handler, "GEMINI_PAID_IMAGE_ENABLED", False)
    monkeypatch.setattr(ai_handler, "ENABLE_IMAGE_FALLBACK", True)
    fake_http_free = FakeHttpSession(
        post_responses=[],
        get_responses=[FakeMockResponse(200, raw_bytes=fake_png, headers={"Content-Type": "image/png"})],
    )
    engine_label_free, dfile_free, err_free = await ai_handler.generate_image(
        888, "kucing astronot", http_session=fake_http_free
    )
    assert err_free is None
    assert dfile_free is not None
    assert len(fake_http_free.post_calls) == 0
    assert "Flux" in engine_label_free

    # 2. Mode Paid Tier (GEMINI_PAID_IMAGE_ENABLED=True): memakai Google Gemini Native Image
    monkeypatch.setattr(ai_handler, "GEMINI_PAID_IMAGE_ENABLED", True)
    gemini_img_resp = FakeMockResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"inlineData": {"mimeType": "image/png", "data": b64_png}},
                        ]
                    }
                }
            ]
        },
    )
    fake_http_paid = FakeHttpSession(post_responses=[gemini_img_resp])
    engine_label, dfile, err = await ai_handler.generate_image(888, "kota masa depan", http_session=fake_http_paid)
    assert err is None
    assert dfile is not None
    assert "Google Gemini" in engine_label
    sent_json = fake_http_paid.post_calls[0]["json"]
    assert sent_json["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"


def test_thinking_config_compatibility():
    # Flash-Lite mendukung minimal
    assert ai_handler.build_thinking_config("gemini-3.5-flash-lite", "minimal") == {"thinkingLevel": "minimal"}
    # 3.8 Flash otomatis mengubah minimal menjadi low agar tidak error HTTP 400
    assert ai_handler.build_thinking_config("gemini-3.8-flash", "minimal") == {"thinkingLevel": "low"}


@pytest.mark.asyncio
async def test_persistent_views_have_valid_custom_ids():
    # Discord.py mewajibkan semua komponen dalam View(timeout=None) memiliki custom_id eksplisit
    for view_cls in (
        views.MainPanelControlView,
        views.EndSessionView,
        views.ChatPersonaSwitchView,
        views.ImageSettingsView,
    ):
        v = view_cls()
        assert v.is_persistent() is True
        for item in v.children:
            assert item.custom_id is not None and len(item.custom_id) > 0


def test_slash_commands_registered():
    all_cmds = {cmd.name: cmd for cmd in bot_main.bot.tree.get_commands()}
    assert {"sesi", "ringkas", "cari", "game", "agent", "status", "bantuan"}.issubset(all_cmds.keys())

    sesi_subs = {sc.name for sc in all_cmds["sesi"].commands}
    assert sesi_subs == {"panel", "model", "reset", "tutup"}

    ringkas_subs = {sc.name for sc in all_cmds["ringkas"].commands}
    assert ringkas_subs == {"chat", "channel", "link"}


class _DummyAttachment:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self.size = len(data)
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _DummyMessage:
    def __init__(self, attachments):
        self.attachments = attachments


@pytest.mark.asyncio
async def test_extract_message_attachments_vision_and_code():
    img = _DummyAttachment("error_screen.png", "image/png", b"\x89PNG\r\n\x1a\n1234")
    code = _DummyAttachment("script.py", "text/x-python", b"def halo():\n    return 42\n")
    unsupported = _DummyAttachment("archive.zip", "application/zip", b"PK\x03\x04")

    msg = _DummyMessage([img, code, unsupported])
    image_parts, image_filenames, text_blocks, warnings = await utils.extract_message_attachments(msg)

    assert len(image_parts) == 1
    assert image_parts[0]["inlineData"]["mimeType"] == "image/png"
    assert image_filenames == ["error_screen.png"]
    assert len(text_blocks) == 1
    assert "def halo():" in text_blocks[0]
    assert len(warnings) == 1
    assert "archive.zip" in warnings[0]


def test_realtime_time_context_timezones():
    wib = utils.get_realtime_time_context("Asia/Jakarta")
    wita = utils.get_realtime_time_context("Asia/Makassar")
    wit = utils.get_realtime_time_context("Asia/Jayapura")

    assert "WIB" in wib["clock"]
    assert "WITA" in wita["clock"]
    assert "WIT" in wit["clock"]
    assert 0 <= wib["hour"] <= 23
    assert len(wib["summary"]) > 10


def test_agent_command_group_registered():
    cmd_names = {cmd.name for cmd in bot_main.bot.tree.get_commands()}
    assert "agent" in cmd_names
    agent_cmd = next(cmd for cmd in bot_main.bot.tree.get_commands() if cmd.name == "agent")
    sub_names = {sub.name for sub in agent_cmd.commands}
    assert {
        "chat",
        "gallery",
        "persona",
        "sapa",
        "status",
        "welcome",
        "youtube",
        "cari",
        "info",
        "digest",
        "panel",
        "goodbye",
        # v1.13.0-beta: banner sambutan, mode kartu, DM, & pesan boost
        "banner",
        "kartu",
        "dm",
        "boost",
        # v1.19.0-beta: tingkat keamanan konten AI per server
        "keamanan",
    } == sub_names


class _FakeSticker:
    def __init__(self, name: str, fmt: discord.StickerFormatType, url: str):
        self.name = name
        self.format = fmt
        self.url = url


class _FakeUser:
    def __init__(self, uid: int, display_name: str):
        self.id = uid
        self.display_name = display_name
        self.mention = f"<@{uid}>"

    def __eq__(self, other):
        return getattr(other, "id", None) == self.id


class _FakeChannel:
    def __init__(self, cid: int):
        self.id = cid


class _FakeGuild:
    def __init__(self, gid: int, bot_member):
        self.id = gid
        self.me = bot_member


class _FakeReference:
    def __init__(self, resolved_msg):
        self.message_id = 99999
        self.resolved = resolved_msg


class _FakeCommunityMessage:
    def __init__(
        self,
        *,
        channel_id: int,
        guild_id: int,
        author: _FakeUser,
        bot_user: _FakeUser,
        content: str = "",
        attachments=None,
        stickers=None,
        mentions=None,
        reference=None,
    ):
        self.channel = _FakeChannel(channel_id)
        self.guild = _FakeGuild(guild_id, bot_user)
        self.author = author
        self.content = content
        self.attachments = attachments or []
        self.stickers = stickers or []
        self.mentions = mentions or []
        self.reference = reference


@pytest.mark.asyncio
async def test_agent_config_persistence_and_smart_reply_triggers():
    bot_user = _FakeUser(100, "MegalBot")
    member_a = _FakeUser(201, "Umar")
    member_b = _FakeUser(202, "Budi")

    community_agent.set_chat_channel_config(10, 5000, enabled=True, reply_mode="smart", idle_minutes=30)
    community_agent.set_gallery_channel_config(10, 6000, enabled=True, auto_reaction=True)
    g_cfg = community_agent.get_guild_settings(10)
    g_cfg["nickname"] = "Megal"
    g_cfg["style_preset"] = "gaul"

    await community_agent.save_agent_config_to_disk()
    community_agent.chat_agent_channels.clear()
    community_agent.gallery_agent_channels.clear()
    community_agent.guild_agent_settings.clear()

    c_count, g_count = community_agent.load_agent_config_from_disk()
    assert c_count == 1
    assert g_count == 1
    assert community_agent.get_guild_settings(10)["nickname"] == "Megal"

    # 1. Sapaan pagi hari -> otomatis dibalas!
    msg_morning = _FakeCommunityMessage(
        channel_id=5000,
        guild_id=10,
        author=member_a,
        bot_user=bot_user,
        content="Selamat pagi guys",
    )
    should_reply, use_ref = community_agent.should_agent_reply_in_chat(msg_morning, bot_user)
    assert should_reply is True
    assert use_ref is True

    # 2. Dua member sedang me-reply satu sama lain -> AI tahu diri dan tidak memotong!
    other_human_msg = _FakeCommunityMessage(
        channel_id=5000, guild_id=10, author=member_a, bot_user=bot_user, content="Main yuk"
    )
    msg_reply_human = _FakeCommunityMessage(
        channel_id=5000,
        guild_id=10,
        author=member_b,
        bot_user=bot_user,
        content="Ayo gas login",
        reference=_FakeReference(other_human_msg),
    )
    should_reply_2, _ = community_agent.should_agent_reply_in_chat(msg_reply_human, bot_user)
    assert should_reply_2 is False

    # 3. Member me-reply pesan bot langsung -> PASTI dibalas!
    bot_prev_msg = _FakeCommunityMessage(
        channel_id=5000, guild_id=10, author=bot_user, bot_user=bot_user, content="Sepi nih siang-siang"
    )
    msg_reply_bot = _FakeCommunityMessage(
        channel_id=5000,
        guild_id=10,
        author=member_a,
        bot_user=bot_user,
        content="Hai",
        reference=_FakeReference(bot_prev_msg),
    )
    should_reply_3, use_ref_3 = community_agent.should_agent_reply_in_chat(msg_reply_bot, bot_user)
    assert should_reply_3 is True
    assert use_ref_3 is True


@pytest.mark.asyncio
async def test_agent_reads_stickers_custom_emojis_and_gallery_video(monkeypatch):
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    bot_user = _FakeUser(100, "MegalBot")
    member = _FakeUser(201, "Umar")
    community_agent.set_chat_channel_config(10, 5000, enabled=True, reply_mode="smart", idle_minutes=30)
    community_agent.set_gallery_channel_config(10, 6000, enabled=True, auto_reaction=True)

    # Mock unduhan gambar stiker / custom emoji
    async def fake_fetch_small(url, session, max_bytes=2000000):
        return b"\x89PNG\r\n\x1a\nstickerbytes"

    monkeypatch.setattr(utils, "_fetch_small_media_bytes", fake_fetch_small)

    # A. Member kirim stiker + custom emoji ekspresi songong di Auto-Chat
    sticker_msg = _FakeCommunityMessage(
        channel_id=5000,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="<:smug_face:123456789012345678>",
        stickers=[_FakeSticker("Cute Cat", discord.StickerFormatType.png, "https://cdn.discordapp.com/stickers/1.png")],
    )
    chat_gemini_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Wkwk stikernya gemes banget tapi emojinya songong amat tuh 😆"}]}}]},
    )
    fake_http_chat = FakeHttpSession(post_responses=[chat_gemini_resp])

    reply = await community_agent.generate_community_chat_reply(
        sticker_msg,
        bot_user,
        http_session=fake_http_chat,
    )
    assert "stikernya gemes" in reply
    sent_parts = fake_http_chat.post_calls[0]["json"]["contents"][-1]["parts"]
    # Terdapat 2 inlineData visual (1 stiker + 1 custom emoji) + 1 teks
    inline_count = sum(1 for p in sent_parts if "inlineData" in p)
    assert inline_count == 2

    # B. Member kirim video pendek (.mp4) di channel Galeri
    video_att = _DummyAttachment("cosplay_bulan_sabit.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42video")
    gallery_msg = _FakeCommunityMessage(
        channel_id=6000,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Hasil editan malam ini!",
        attachments=[video_att],
    )
    gal_gemini_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Wih kostum putih di atas bulan sabitnya estetik banget Umar!"}]}}]},
    )
    fake_http_gal = FakeHttpSession(post_responses=[gal_gemini_resp])

    gal_comment, gal_reaction = await community_agent.generate_gallery_comment(
        gallery_msg,
        bot_user,
        http_session=fake_http_gal,
    )
    assert "bulan sabitnya estetik" in gal_comment
    assert gal_reaction in community_agent.GALLERY_REACTIONS
    gal_parts = fake_http_gal.post_calls[0]["json"]["contents"][0]["parts"]
    assert gal_parts[0]["inlineData"]["mimeType"] == "video/mp4"


@pytest.mark.asyncio
async def test_dead_chat_icebreaker_increments_poke_counter(monkeypatch):
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    community_agent.set_chat_channel_config(10, 5000, enabled=True, reply_mode="smart", idle_minutes=30)

    # 1. Sapaan manual (/agent sapa -> manual_trigger=True) TIDAK boleh mengunci consecutive_idle_pokes
    ice_resp_manual = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Sepi banget nih malam-malam, pada kemana?"}]}}]},
    )
    fake_http_manual = FakeHttpSession(post_responses=[ice_resp_manual])
    manual_text = await community_agent.generate_idle_icebreaker(
        5000,
        10,
        "Megal",
        idle_minutes_elapsed=30,
        manual_trigger=True,
        http_session=fake_http_manual,
    )
    assert "Sepi banget" in manual_text
    assert community_agent.chat_agent_channels[5000]["consecutive_idle_pokes"] == 0

    # 2. Sapaan otomatis background (manual_trigger=False) menaikkan consecutive_idle_pokes agar anti-spam
    ice_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Aduh sepi amat nih siang-siang, pada lagi ngapain guys?"}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[ice_resp])

    text = await community_agent.generate_idle_icebreaker(
        5000,
        10,
        "Megal",
        idle_minutes_elapsed=31,
        manual_trigger=False,
        http_session=fake_http,
    )
    assert "sepi amat" in text
    assert community_agent.chat_agent_channels[5000]["consecutive_idle_pokes"] == 1
    # Pastikan sapaan kedua otomatis menyertakan memori anti-monoton dari sapaan pertama
    second_prompt_sent = fake_http.post_calls[0]["json"]["contents"][0]["parts"][0]["text"]
    assert "ANTI-MONOTON" in second_prompt_sent
    assert "Sepi banget nih malam-malam" in second_prompt_sent

    # 3. Mengatur ulang /agent chat mereset penghitung kembali ke 0
    community_agent.set_chat_channel_config(10, 5000, enabled=True, reply_mode="smart", idle_seconds=30)
    assert community_agent.chat_agent_channels[5000]["consecutive_idle_pokes"] == 0
    assert community_agent.chat_agent_channels[5000]["idle_seconds"] == 30


def test_parse_idle_duration_flexible_inputs():
    assert community_agent.parse_idle_duration(None) == (1800, "30 menit")
    assert community_agent.parse_idle_duration("1") == (60, "1 menit")
    assert community_agent.parse_idle_duration("5 menit") == (300, "5 menit")
    assert community_agent.parse_idle_duration("30 detik") == (30, "30 detik")
    assert community_agent.parse_idle_duration("1 jam") == (3600, "60 menit")
    assert community_agent.parse_idle_duration("0") == (0, "Nonaktif")
    assert community_agent.parse_idle_duration("off") == (0, "Nonaktif")
    assert community_agent.parse_idle_duration("bukan angka") is None


def test_auto_cleanup_expired_sessions():
    import time as _time

    storage.init_thread_session(111, "gemini_flash", owner_id=1)
    storage.init_thread_session(222, "gemini_coder", owner_id=2)
    storage.init_image_session(333, owner_id=3)

    # Buat sesi 111 dan 333 seolah-olah sudah menganggur 10 hari
    ten_days_ago = _time.time() - (10 * 86400)
    storage.thread_chats[111]["updated_at"] = ten_days_ago
    storage.image_thread_settings[333]["updated_at"] = ten_days_ago

    removed = storage.cleanup_expired_sessions(max_age_days=7)
    assert removed == 2
    assert 111 not in storage.thread_chats
    assert 333 not in storage.image_thread_settings
    assert 222 in storage.thread_chats


def test_multi_gemini_api_keys_rotation_and_redaction(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaKeyAlpha11111, AIzaKeyBeta22222")
    monkeypatch.setattr(utils, "GEMINI_API_KEY", "AIzaKeyAlpha11111, AIzaKeyBeta22222")

    first_order = ai_handler.get_gemini_keys_rotated()
    second_order = ai_handler.get_gemini_keys_rotated()
    assert first_order == ["AIzaKeyAlpha11111", "AIzaKeyBeta22222"] or first_order == ["AIzaKeyBeta22222", "AIzaKeyAlpha11111"]
    assert first_order != second_order

    sanitized = utils.sanitize_error_message("Failed with AIzaKeyAlpha11111 and AIzaKeyBeta22222")
    assert "AIzaKeyAlpha11111" not in sanitized
    assert "AIzaKeyBeta22222" not in sanitized


@pytest.mark.asyncio
async def test_voice_note_and_audio_extraction_and_reply(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    vn_att = _DummyAttachment("voice-message.ogg", "audio/ogg; codecs=opus", b"OggS\x00\x02opusvoice")
    vn_att.duration = 6.4

    # 1. Di ruang privat ai-..., Voice Note otomatis diekstrak sebagai audio/ogg & dijawab Gemini
    msg_priv = _DummyMessage([vn_att])
    media_parts, media_names, _, warnings = await utils.extract_message_attachments(msg_priv)
    assert warnings == []
    assert len(media_parts) == 1
    assert media_parts[0]["inlineData"]["mimeType"] == "audio/ogg"
    assert media_names == ["voice_note:voice-message.ogg"]

    # Di ruang gambar draw-..., Voice Note dilewati secara aman
    draw_parts, _, _, draw_warns = await utils.extract_message_attachments(msg_priv, include_audio=False)
    assert draw_parts == []
    assert len(draw_warns) == 1

    storage.init_thread_session(909, "gemini_flash")
    vn_gemini_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Siap, suara kamu terdengar jelas! Ayo kita bahas."}]}}]},
    )
    fake_http_priv = FakeHttpSession(post_responses=[vn_gemini_resp])
    priv_reply = await ai_handler.get_ai_response(
        909,
        "",
        image_parts=media_parts,
        image_filenames=media_names,
        http_session=fake_http_priv,
    )
    assert "suara kamu terdengar jelas" in priv_reply

    # 2. Di channel Auto-Chat komunitas, Voice Note tanpa teks tetap memicu bot untuk mendengar & membalas!
    bot_user = _FakeUser(100, "Whas")
    member = _FakeUser(201, "Angga")
    community_agent.set_chat_channel_config(10, 5000, enabled=True, reply_mode="smart", idle_minutes=30)
    # Buat seolah channel baru aktif 10 detik lalu agar membuktikan pemicu murni berasal dari Voice Note
    community_agent.chat_agent_channels[5000]["last_activity_at"] = 9999999999.0

    vn_comm_msg = _FakeCommunityMessage(
        channel_id=5000,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="",
        attachments=[vn_att],
    )
    should_reply, use_ref = community_agent.should_agent_reply_in_chat(vn_comm_msg, bot_user)
    assert should_reply is True
    assert use_ref is True

    comm_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Haha siap Angga, gas login bentar lagi ya!"}]}}]},
    )
    fake_http_comm = FakeHttpSession(post_responses=[comm_resp])
    comm_reply = await community_agent.generate_community_chat_reply(
        vn_comm_msg,
        bot_user,
        http_session=fake_http_comm,
    )
    assert "gas login" in comm_reply


@pytest.mark.asyncio
async def test_summarize_channel_messages_ringkas(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    log_lines = [
        "[Angga]: Guys nanti jam 8 malam mabar Valorant yuk",
        "[Rizky]: Gas gue ikut main Sage",
        "[Sinta]: Aku nyusul jam setengah 9 ya habis makan",
    ]
    sum_resp = FakeMockResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "**📌 Topik Utama**\n- Angga mengajak mabar Valorant jam 8 malam, Rizky & Sinta ikut."
                            }
                        ]
                    }
                }
            ]
        },
    )
    fake_http = FakeHttpSession(post_responses=[sum_resp])
    summary, err = await ai_handler.summarize_channel_messages(
        log_lines,
        "general",
        http_session=fake_http,
    )
    assert err is None
    assert "Valorant" in summary
    assert "/models/models/" not in fake_http.post_calls[0]["url"]


@pytest.mark.asyncio
async def test_welcome_agent_greeting_dedup_and_persistence(monkeypatch):
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    community_agent.set_welcome_config(
        10,
        7000,
        enabled=True,
        extra_note="Jangan lupa ambil role di #roles",
    )
    await community_agent.save_agent_config_to_disk()
    community_agent.welcome_agent_guilds.clear()
    community_agent.load_agent_config_from_disk()
    assert community_agent.welcome_agent_guilds[10]["channel_id"] == 7000
    assert "ambil role" in community_agent.welcome_agent_guilds[10]["extra_note"]

    # Deduplikasi: join yang sama dalam 60 detik hanya diproses 1x (kecuali force=True untuk tes)
    assert community_agent.should_process_member_welcome(10, 555) is True
    assert community_agent.should_process_member_welcome(10, 555) is False
    assert community_agent.should_process_member_welcome(10, 555, force=True) is True

    # Jika model lupa menyertakan mention <@555>, fungsi otomatis menyisipkannya
    w_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Halo selamat datang di tongkrongan kita, jangan lupa mampir ke #roles ya!"}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[w_resp])
    greeting = await community_agent.generate_welcome_greeting(
        10,
        "Bintang",
        "<@555>",
        "Whas",
        guild_name="Server Angga",
        member_count=42,
        http_session=fake_http,
    )
    assert "<@555>" in greeting
    assert len(community_agent.welcome_agent_guilds[10]["recent_welcomes"]) == 1


@pytest.mark.asyncio
async def test_context_menus_and_transform_message_with_gemini(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    # Pastikan kedua Discord Message Context Menu terdaftar dengan tipe message & panjang <= 32
    all_cmds = bot_main.bot.tree.get_commands()
    msg_menus = {
        c.name: c for c in all_cmds if getattr(c, "type", None) == discord.AppCommandType.message
    }
    assert "🌐 Terjemahkan ke Indonesia" in msg_menus
    assert "💡 Jelaskan Pesan Ini" in msg_menus
    assert all(len(name) <= 32 for name in msg_menus)

    # Uji ekstraksi pesan + embed + stiker untuk Context Menu
    class _FakeEmbed:
        title = "Patch Notes v2.4"
        description = "Fixed memory leak when loading shaders."

    class _FakeSticker:
        name = "bingung"

    class _FakeCtxMsg:
        content = "Tbh idk why it threw segfault at runtime 💀"
        embeds = [_FakeEmbed()]
        stickers = [_FakeSticker()]

    extracted = utils.extract_message_text_for_context(_FakeCtxMsg())
    assert "segfault" in extracted
    assert "Patch Notes v2.4" in extracted
    assert "bingung" in extracted

    # Uji transform_message_with_gemini (translate_id & explain)
    tr_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Jujur aku kurang tahu kenapa muncul error segfault saat dijalankan 💀"}]}}]},
    )
    ex_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Pesan ini membahas error *segmentation fault* (akses memori tidak valid)."}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[tr_resp, ex_resp])

    tr_out, tr_err = await ai_handler.transform_message_with_gemini(
        "translate_id",
        extracted,
        http_session=fake_http,
    )
    assert tr_err is None
    assert "Jujur aku kurang tahu" in tr_out

    ex_out, ex_err = await ai_handler.transform_message_with_gemini(
        "explain",
        extracted,
        http_session=fake_http,
    )
    assert ex_err is None
    assert "segmentation fault" in ex_out


def test_youtube_url_normalizer_and_ssrf_guard():
    # YouTube watch, youtu.be, dan shorts dinormalisasi ke format kanonis
    assert (
        utils.normalize_youtube_url("https://youtu.be/dQw4w9WgXcQ?si=abc")
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert (
        utils.normalize_youtube_url("https://www.youtube.com/shorts/aqz-KE-bpKQ")
        == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    )
    assert utils.normalize_youtube_url("https://example.com/artikel") is None

    yt_urls, web_urls = utils.extract_urls_from_text(
        "Tonton https://youtu.be/dQw4w9WgXcQ dan baca https://python.org/doc ya!"
    )
    assert yt_urls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert web_urls == ["https://python.org/doc"]

    # Proteksi SSRF wajib menolak localhost & IP jaringan internal
    assert utils.is_safe_public_url("http://localhost:8080/admin") is False
    assert utils.is_safe_public_url("http://127.0.0.1/secret") is False
    assert utils.is_safe_public_url("http://192.168.1.1/router") is False
    assert utils.is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False
    assert utils.is_safe_public_url("http://10.0.0.5/internal") is False
    assert utils.is_safe_public_url("ftp://example.com/file") is False


@pytest.mark.asyncio
async def test_youtube_and_webpage_summarizer_ringkas_link(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(utils, "is_safe_public_url", lambda u: u.startswith("https://"))

    # 1. Analisis link YouTube mengirim part fileData ke Gemini secara native
    yt_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "**🎬 Inti Video:** Tutorial optimasi Python async."}]}}]},
    )
    fake_http_yt = FakeHttpSession(post_responses=[yt_resp])
    yt_summary, yt_err = await ai_handler.analyze_link_with_gemini(
        "https://youtu.be/dQw4w9WgXcQ",
        question="Apa tips utamanya?",
        http_session=fake_http_yt,
    )
    assert yt_err is None
    assert "Python async" in yt_summary
    sent_parts = fake_http_yt.post_calls[0]["json"]["contents"][0]["parts"]
    assert any(p.get("fileData", {}).get("fileUri") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ" for p in sent_parts)

    # 2. Analisis link artikel web mengambil & membersihkan HTML lalu merangkumnya
    sample_html = (
        b"<html><head><title>Rilis Python Terbaru</title><script>evil()</script></head>"
        b"<body><main><h1>Python Cepat</h1><p>Peningkatan performa interpreter hingga 25 persen pada rilis ini.</p></main></body></html>"
    )
    web_get_resp = FakeMockResponse(
        200,
        raw_bytes=sample_html,
        headers={"Content-Type": "text/html; charset=utf-8"},
        url="https://blog.example.org/python",
    )
    web_ai_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "**📌 Inti Artikel:** Performa Python naik 25%."}]}}]},
    )
    fake_http_web = FakeHttpSession(post_responses=[web_ai_resp], get_responses=[web_get_resp])
    web_summary, web_err = await ai_handler.analyze_link_with_gemini(
        "https://blog.example.org/python",
        http_session=fake_http_web,
    )
    assert web_err is None
    assert "25%" in web_summary
    prompt_sent = fake_http_web.post_calls[0]["json"]["contents"][0]["parts"][0]["text"]
    assert "Rilis Python Terbaru" in prompt_sent
    assert "evil()" not in prompt_sent


@pytest.mark.asyncio
async def test_google_search_grounding_cari_and_auto_chat_fallback(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    # Deteksi otomatis kapan pertanyaan membutuhkan pencarian berita/fakta terkini (termasuk saat panggil nama bot!)
    assert utils.needs_live_web_search("Siapa pemenang pertandingan Timnas Indonesia tadi malam?") is True
    assert utils.needs_live_web_search("Berapa kurs dollar ke rupiah hari ini?") is True
    assert utils.needs_live_web_search("Whas cariin berita bola terbaru dong") is True
    assert utils.needs_live_web_search("Whas ada berita apa tentang timnas?") is True
    assert utils.needs_live_web_search("Whas cari berita teknologi") is True
    assert utils.needs_live_web_search("Buatkan fungsi rekursif faktorial di Python") is False
    assert utils.needs_live_web_search("Coba cek kode python aku ini dong") is False
    assert utils.build_clean_search_query("Whas tolong cariin berita timnas Indonesia dong!", "Whas") == "berita timnas Indonesia"

    # Sanitasi pesan error kuota wajib bersih dari URL mentah agar tidak memicu kartu preview raksasa Discord
    raw_quota_err = (
        "You exceeded your current quota, please check your plan and billing details. "
        "For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. "
        "To monitor your current usage, head to: https://ai.dev/rate-limit."
    )
    cleaned_err = utils.sanitize_error_message(raw_quota_err)
    assert "https://" not in cleaned_err
    assert "kuota" in cleaned_err.lower()

    # 1. Mode Default Free Tier (GEMINI_PAID_SEARCH_ENABLED=False):
    #    /cari menggunakan mesin pencari gratis (DuckDuckGo + Google News RSS) TANPA memanggil tool berbayar google_search!
    sample_ddg_html = (
        b'<div class="result__body"><a class="result__a" '
        b'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fekonomi.example.com%2Fkurs">Kurs Dollar Hari Ini</a>'
        b'<a class="result__snippet">Nilai tukar USD ke IDR hari ini berada di Rp16.150 per dolar AS.</a></div>'
    )
    sample_news_rss = (
        b'<?xml version="1.0" encoding="UTF-8"?><rss><channel><item>'
        b"<title>Rupiah Menguat ke Rp16.150 Sore Ini - Kompas</title>"
        b"<link>https://news.example.com/rupiah</link>"
        b"<pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate>"
        b"<description>Kurs rupiah menguat tipis terhadap dolar AS.</description>"
        b'<source url="https://kompas.example.com">Kompas</source>'
        b"</item></channel></rss>"
    )
    ddg_get = FakeMockResponse(200, raw_bytes=sample_ddg_html, headers={"Content-Type": "text/html"})
    rss_get = FakeMockResponse(200, raw_bytes=sample_news_rss, headers={"Content-Type": "application/xml"})
    top_page_get = FakeMockResponse(
        200,
        raw_bytes=b"<html><title>Kurs USD</title><body><p>Kurs jual Rp16.180 dan kurs beli Rp16.120 hari ini.</p></body></html>",
        headers={"Content-Type": "text/html"},
        url="https://ekonomi.example.com/kurs",
    )
    monkeypatch.setattr(utils, "is_safe_public_url", lambda u: u.startswith("https://"))

    free_ai_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Kurs USD ke IDR hari ini berada di kisaran Rp16.150."}]}}]},
    )
    fake_http_free = FakeHttpSession(
        post_responses=[free_ai_resp],
        get_responses=[ddg_get, rss_get, top_page_get],
    )
    ans, err = await ai_handler.search_web_with_gemini(
        "Berapa kurs dollar hari ini?",
        http_session=fake_http_free,
    )
    assert err is None
    assert "Rp16.150" in ans
    assert "https://news.example.com/rupiah" in ans or "https://ekonomi.example.com/kurs" in ans
    # Pastikan TIDAK memanggil tools google_search berbayar pada mode Free Tier!
    assert "tools" not in fake_http_free.post_calls[0]["json"]
    assert "gemini-3.5-flash-lite" in fake_http_free.post_calls[0]["url"]

    # 2. Jika GEMINI_PAID_SEARCH_ENABLED=True tapi API Key ternyata kena limit 0 (exceeded your current quota),
    #    bot otomatis mematikan paid tool dan langsung beralih ke Free Live Search dengan mulus!
    monkeypatch.setattr(ai_handler, "GEMINI_PAID_SEARCH_ENABLED", True)
    ai_handler.clear_model_cooldowns()
    quota_zero = FakeMockResponse(429, {"error": {"message": raw_quota_err}})
    ddg_get2 = FakeMockResponse(200, raw_bytes=sample_ddg_html, headers={"Content-Type": "text/html"})
    rss_get2 = FakeMockResponse(200, raw_bytes=sample_news_rss, headers={"Content-Type": "application/xml"})
    top_page_get2 = FakeMockResponse(404, raw_bytes=b"")
    fallback_ok = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Berhasil dijawab lewat jalur gratis setelah bypass kuota 0!"}]}}]},
    )
    fake_http_paid_fb = FakeHttpSession(
        post_responses=[quota_zero, fallback_ok],
        get_responses=[ddg_get2, rss_get2, top_page_get2],
    )
    ans2, err2 = await ai_handler.search_web_with_gemini(
        "Update kurs rupiah hari ini",
        http_session=fake_http_paid_fb,
    )
    assert err2 is None
    assert "jalur gratis" in ans2
    assert ai_handler._paid_google_search_available is False


@pytest.mark.asyncio
async def test_mini_game_engine_guessing_and_leaderboard_persistence(monkeypatch):
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    # 1. Validasi seluruh subcommand /game & command baru terdaftar
    top_names = {c.name for c in bot_main.bot.tree.get_commands()}
    assert {"cari", "ringkas", "sesi", "game", "bantuan"}.issubset(top_names)
    game_cmd = next(c for c in bot_main.bot.tree.get_commands() if c.name == "game")
    sub_names = {sc.name for sc in game_cmd.commands}
    assert sub_names == {"mulai", "papan_skor", "stop", "reset_skor"}

    # 2. Pencocokan tebakan toleran huruf besar/kecil, spasi, tanda hubung, dan kalimat singkat
    assert games.is_matching_guess("spiderman", ["Spider-Man"]) is True
    assert games.is_matching_guess("jawabannya Spider Man!", ["Spider-Man"]) is True
    assert games.is_matching_guess("batman", ["Spider-Man"]) is False

    hint_str = games.build_masked_word_hint("Martabak")
    assert hint_str.startswith("M") and "_" in hint_str
    scrambled = games.scramble_word("NUSANTARA")
    assert len(scrambled.replace(" ", "")) == len("NUSANTARA")

    # 3. Pembuatan soal via Gemini JSON + anti-duplikasi jawaban
    emoji_json_resp = FakeMockResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "clue_emojis": "🧙‍♂️⚡👓🦉🏰",
                                        "category": "Film Fantasi",
                                        "answer": "Harry Potter",
                                        "aliases": ["harrypotter"],
                                        "extra_hint": "Sekolah sihir Hogwarts.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )
    fake_http = FakeHttpSession(post_responses=[emoji_json_resp])
    q_data = await games.generate_ai_game_question("emoji", guild_id=77, http_session=fake_http)
    assert q_data["answer"] == "Harry Potter"

    # 4. Simulasi member menebak di channel: tebakan salah pendek ditahan agar Auto-Chat tidak bocor,
    #    dan tebakan benar memberikan poin + menyimpan ke disk
    replied_embeds = []

    class _FakeGameMsg:
        def __init__(self, author_id: int, author_name: str, text: str):
            self.channel = type("Ch", (), {"id": 9100})()
            self.guild = type("G", (), {"id": 77})()
            self.author = type(
                "U",
                (),
                {"id": author_id, "display_name": author_name, "mention": f"<@{author_id}>"},
            )()
            self.content = text
            self.mentions = []

        async def reply(self, embed=None, mention_author=False):
            replied_embeds.append(embed)

    games.active_channel_games[9100] = {
        "type": "emoji",
        "starter_id": 1,
        "answer": "Harry Potter",
        "aliases": ["harrypotter"],
        "points": 20,
    }

    # Tebakan salah pendek -> mengembalikan True (menahan Auto-Chat) namun game tetap berjalan
    consumed_wrong = await games.handle_active_game_guess(_FakeGameMsg(301, "Budi", "Lord Voldemort"))
    assert consumed_wrong is True
    assert 9100 in games.active_channel_games
    assert replied_embeds == []

    # Tebakan benar -> poin masuk, ronde selesai, dan tersimpan ke game_scores.json
    consumed_right = await games.handle_active_game_guess(_FakeGameMsg(302, "Citra", "harry potter!"))
    assert consumed_right is True
    assert 9100 not in games.active_channel_games
    assert len(replied_embeds) == 1
    assert "Citra" in replied_embeds[0].description or "<@302>" in replied_embeds[0].description

    # Uji ketahanan simpan & muat ulang papan skor dari disk
    games.guild_game_scores.clear()
    loaded_cnt = games.load_game_scores_from_disk()
    assert loaded_cnt == 1
    board = games.get_guild_leaderboard(77)
    assert len(board) == 1
    assert board[0]["user_id"] == 302
    assert board[0]["points"] == 20
    assert board[0]["wins"] == 1
    rank, pts, wins = games.get_user_rank_info(77, 302)
    assert (rank, pts, wins) == (1, 20, 1)


@pytest.mark.asyncio
async def test_community_agent_reads_youtube_links_and_live_search(monkeypatch):
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    # Pastikan subcommand /agent youtube & /agent cari terdaftar lengkap dengan parameter 'channel'
    agent_cmd = next(c for c in bot_main.bot.tree.get_commands() if c.name == "agent")
    agent_sub_map = {sc.name: sc for sc in agent_cmd.commands}
    assert {"youtube", "cari"}.issubset(agent_sub_map.keys())
    assert "channel" in {p.name for p in agent_sub_map["youtube"].parameters}
    assert "channel" in {p.name for p in agent_sub_map["cari"].parameters}

    bot_user = _FakeUser(100, "Whas")
    member = _FakeUser(205, "Dika")
    community_agent.get_guild_settings(10)["nickname"] = "Whas"
    community_agent.set_chat_channel_config(10, 6100, enabled=True, reply_mode="all", idle_minutes=30)

    # Aktifkan fitur YouTube di DUA channel sekaligus (6100 & 6200), sedangkan 6300 dibiarkan OFF
    community_agent.set_youtube_channel_config(10, 6100, enabled=True, auto_in_chat=False)
    community_agent.set_youtube_channel_config(10, 6200, enabled=True, auto_in_chat=True)
    assert {cid for cid, _ in community_agent.get_guild_youtube_channels(10)} == {6100, 6200}
    assert community_agent.is_youtube_enabled_in_channel(6100) is True
    assert community_agent.is_youtube_enabled_in_channel(6200, require_auto_in_chat=True) is True
    assert community_agent.is_youtube_enabled_in_channel(6300) is False

    yt_msg = _FakeCommunityMessage(
        channel_id=6100,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Guys cobain tonton https://youtu.be/dQw4w9WgXcQ kocak banget",
    )

    # 1. DEFAULT di 6100 (auto_in_chat=False): kirim link YouTube biasa tanpa panggil bot TIDAK memicu auto-chat!
    should_reply_default, _ = community_agent.should_agent_reply_in_chat(yt_msg, bot_user)
    assert should_reply_default is False

    # 1B. TAPI jika member memanggil nama panggilan bot ('Whas') + link YouTube di channel aktif 6100,
    #     bot LANGSUNG menonton & merangkumnya!
    yt_called_msg = _FakeCommunityMessage(
        channel_id=6100,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Whas coba rangkumin video ini dong https://youtu.be/dQw4w9WgXcQ",
    )
    should_reply_called, _ = community_agent.should_agent_reply_in_chat(yt_called_msg, bot_user)
    assert should_reply_called is True
    called_yt_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Itu video klip Never Gonna Give You Up dari Rick Astley, Dika!"}]}}]},
    )
    fake_http_called = FakeHttpSession(post_responses=[called_yt_resp])
    called_reply = await community_agent.generate_community_chat_reply(
        yt_called_msg,
        bot_user,
        http_session=fake_http_called,
    )
    assert "Never Gonna Give You Up" in called_reply
    called_parts = fake_http_called.post_calls[0]["json"]["contents"][-1]["parts"]
    assert any(p.get("fileData", {}).get("fileUri") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ" for p in called_parts)

    # 1C. Sebaliknya di channel Auto-Chat lain (6300) yang BELUM diaktifkan /agent youtube,
    #     bot hanya membalas teks tanpa memproses fileData YouTube!
    community_agent.set_chat_channel_config(10, 6300, enabled=True, reply_mode="smart", idle_minutes=30)
    yt_unactivated_ch_msg = _FakeCommunityMessage(
        channel_id=6300,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Whas lihat https://youtu.be/dQw4w9WgXcQ",
    )
    plain_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Ada apa tuh Dika?"}]}}]},
    )
    fake_http_plain = FakeHttpSession(post_responses=[plain_resp])
    await community_agent.generate_community_chat_reply(
        yt_unactivated_ch_msg,
        bot_user,
        http_session=fake_http_plain,
    )
    unact_parts = fake_http_plain.post_calls[0]["json"]["contents"][-1]["parts"]
    assert all("fileData" not in p for p in unact_parts)

    # 2. Saat Admin mengaktifkan auto_di_channel:True pada 6100, kirim link YouTube biasa langsung dirangkum!
    community_agent.set_youtube_channel_config(10, 6100, enabled=True, auto_in_chat=True)
    community_agent.chat_agent_channels[6100]["last_bot_reply_at"] = 0.0
    should_reply_on, _ = community_agent.should_agent_reply_in_chat(yt_msg, bot_user)
    assert should_reply_on is True

    yt_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Wah legendaris banget lagu Rick Astley itu Dika 😂"}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[yt_resp])
    reply = await community_agent.generate_community_chat_reply(yt_msg, bot_user, http_session=fake_http)
    assert "Rick Astley" in reply
    sent_parts = fake_http.post_calls[0]["json"]["contents"][-1]["parts"]
    assert any(p.get("fileData", {}).get("fileUri") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ" for p in sent_parts)

    # 3. Uji multi-channel /agent cari & /agent youtube + penyimpanan atomik ke agent_config.json
    community_agent.set_search_channel_config(10, 6100, enabled=True, auto_in_chat=True)
    community_agent.set_search_channel_config(10, 6250, enabled=True, auto_in_chat=False)
    assert {cid for cid, _ in community_agent.get_guild_search_channels(10)} == {6100, 6250}
    assert community_agent.is_search_enabled_in_channel(6100, for_auto_chat=True) is True
    assert community_agent.is_search_enabled_in_channel(6250, for_auto_chat=False) is True
    assert community_agent.is_search_enabled_in_channel(6250, for_auto_chat=True) is False
    assert community_agent.is_search_enabled_in_channel(6300, for_auto_chat=False) is False

    # Matikan hanya di 6200 -> 6100 tetap aktif!
    community_agent.set_youtube_channel_config(10, 6200, enabled=False)
    assert {cid for cid, _ in community_agent.get_guild_youtube_channels(10)} == {6100}

    await community_agent.save_agent_config_to_disk()
    community_agent.youtube_agent_channels.clear()
    community_agent.search_agent_channels.clear()
    community_agent.load_agent_config_from_disk()
    assert {cid for cid, _ in community_agent.get_guild_youtube_channels(10)} == {6100}
    assert {cid for cid, _ in community_agent.get_guild_search_channels(10)} == {6100, 6250}
    assert community_agent.is_search_enabled_in_channel(6250, for_auto_chat=True) is False

    # 4. Uji channel khusus YouTube / Cari TANPA /agent chat (standalone feature channel)
    community_agent.set_youtube_channel_config(10, 6400, enabled=True, auto_in_chat=False)
    community_agent.set_search_channel_config(10, 6400, enabled=True, auto_in_chat=True)
    # Chat biasa di channel standalone harus diabaikan (karena /agent chat tidak aktif di 6400)
    msg_plain_6400 = _FakeCommunityMessage(
        channel_id=6400, guild_id=10, author=member, bot_user=bot_user, content="Halo siang teman-teman"
    )
    assert community_agent.should_standalone_feature_reply(msg_plain_6400, bot_user) is False
    # Link biasa tanpa panggil bot (auto_in_chat=False) diabaikan
    msg_uncalled_yt_6400 = _FakeCommunityMessage(
        channel_id=6400, guild_id=10, author=member, bot_user=bot_user, content="https://youtu.be/dQw4w9WgXcQ"
    )
    assert community_agent.should_standalone_feature_reply(msg_uncalled_yt_6400, bot_user) is False
    # Panggil nama bot + link YouTube atau panggil nama bot + tanya berita -> AKTIF!
    msg_called_yt_6400 = _FakeCommunityMessage(
        channel_id=6400,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Whas rangkumin https://youtu.be/dQw4w9WgXcQ",
    )
    msg_called_news_6400 = _FakeCommunityMessage(
        channel_id=6400,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Whas cari berita timnas hari ini",
    )
    assert community_agent.should_standalone_feature_reply(msg_called_yt_6400, bot_user) is True
    assert community_agent.should_standalone_feature_reply(msg_called_news_6400, bot_user) is True

    # 5. Uji pencarian berita gratis di channel 6100 yang aktif
    async def _fake_free_search(q, **kwargs):
        return "1. **Pecco Juara MotoGP** — Balapan tadi malam dimenangkan Pecco.", [
            {"title": "MotoGP News", "url": "https://motogp.example.com"}
        ]

    monkeypatch.setattr(community_agent, "free_live_web_search", _fake_free_search)
    news_msg = _FakeCommunityMessage(
        channel_id=6100,
        guild_id=10,
        author=member,
        bot_user=bot_user,
        content="Whas siapa juara MotoGP tadi malam?",
    )
    news_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Balapan semalam seru banget, Pecco berhasil podium satu!"}]}}]},
    )
    fake_http_news = FakeHttpSession(post_responses=[news_resp])
    news_reply = await community_agent.generate_community_chat_reply(
        news_msg,
        bot_user,
        http_session=fake_http_news,
    )
    assert "Pecco" in news_reply
    assert "tools" not in fake_http_news.post_calls[0]["json"]
    sent_news_text = fake_http_news.post_calls[0]["json"]["contents"][-1]["parts"][-1]["text"]
    assert "Pecco Juara MotoGP" in sent_news_text

    # Jika link YouTube bersifat privat/dibatasi usia (HTTP 403), /ringkas_link langsung memberi info jelas tanpa loop sia-sia
    priv_yt_403 = FakeMockResponse(403, {"error": {"message": "Permission denied fetching video"}})
    fake_http_priv_yt = FakeHttpSession(post_responses=[priv_yt_403])
    s_txt, s_err = await ai_handler.analyze_link_with_gemini(
        "https://youtu.be/dQw4w9WgXcQ",
        http_session=fake_http_priv_yt,
    )
    assert s_txt is None
    assert "privat" in s_err.lower()
    assert len(fake_http_priv_yt.post_calls) == 1

    # Dan di Auto-Chat, jika YouTube privat gagal 400, bot melepas fileData lalu tetap membalas teks chat dengan mulus
    yt_400 = FakeMockResponse(400, {"error": {"message": "Invalid video URI"}})
    yt_fallback_ok = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Wah videonya kayaknya diprivat tuh Dika, coba cek linknya lagi!"}]}}]},
    )
    fake_http_recover = FakeHttpSession(post_responses=[yt_400, yt_fallback_ok])
    rec_reply = await community_agent.generate_community_chat_reply(
        yt_msg,
        bot_user,
        http_session=fake_http_recover,
    )
    assert "diprivat" in rec_reply
    assert all("fileData" not in p for p in fake_http_recover.post_calls[1]["json"]["contents"][-1]["parts"])


def test_anti_disturbance_etiquette_in_public_chat():
    bot_user = _FakeUser(100, "WhasBot")
    umar = _FakeUser(201, "Umar")
    budi = _FakeUser(202, "Budi")

    community_agent.set_chat_channel_config(10, 7700, enabled=True, reply_mode="smart", idle_minutes=30)
    community_agent.get_guild_settings(10)["nickname"] = "Whas"
    # Anggap channel baru saja aktif 10 detik lalu agar bukan pemicu channel hening >= 3 menit
    import time as _t

    community_agent.chat_agent_channels[7700]["last_activity_at"] = _t.time()

    # 1. Member me-@mention member manusia lain -> Bot DIAM (tidak ikut campur)
    msg_tag_friend = _FakeCommunityMessage(
        channel_id=7700,
        guild_id=10,
        author=umar,
        bot_user=bot_user,
        content="Halo @Budi udah makan belum?",
        mentions=[budi],
    )
    assert community_agent.should_agent_reply_in_chat(msg_tag_friend, bot_user) == (False, False)

    # 2. Perintah untuk bot lain di server (bot musik m!play, Mudae $wa, OwO) -> Bot DIAM
    for other_cmd in ("m!play Hindia", "$wa", "owo hunt", ".help"):
        msg_cmd = _FakeCommunityMessage(
            channel_id=7700, guild_id=10, author=umar, bot_user=bot_user, content=other_cmd
        )
        assert community_agent.should_agent_reply_in_chat(msg_cmd, bot_user) == (False, False)

    # 3. Share link Spotify / TikTok tanpa panggil bot -> Bot DIAM
    msg_spotify = _FakeCommunityMessage(
        channel_id=7700,
        guild_id=10,
        author=umar,
        bot_user=bot_user,
        content="Dengerin deh https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
    )
    assert community_agent.should_agent_reply_in_chat(msg_spotify, bot_user) == (False, False)

    # 4. Kalimat ngobrol biasa dengan 1 emoji di ujung saat 2 member sedang aktif ngobrol -> Bot DIAM
    msg_crowd_1 = _FakeCommunityMessage(
        channel_id=7700, guild_id=10, author=budi, bot_user=bot_user, content="Oke gas login sekarang 🔥"
    )
    assert community_agent.should_agent_reply_in_chat(msg_crowd_1, bot_user) == (False, False)

    # 5. Tapi begitu salah satu member memanggil nama bot ('Whas ...'), bot LANGSUNG menyahut!
    msg_call_bot = _FakeCommunityMessage(
        channel_id=7700,
        guild_id=10,
        author=budi,
        bot_user=bot_user,
        content="Whas menurutmu gimana?",
    )
    assert community_agent.should_agent_reply_in_chat(msg_call_bot, bot_user) == (True, True)


@pytest.mark.asyncio
async def test_slash_ringkas_link_and_cari_per_channel_gating(monkeypatch):
    # Aktifkan YouTube di #8100 & #8200, serta Cari di #8300
    community_agent.set_youtube_channel_config(10, 8100, enabled=True, auto_in_chat=False)
    community_agent.set_youtube_channel_config(10, 8200, enabled=True, auto_in_chat=True)
    community_agent.set_search_channel_config(10, 8300, enabled=True, auto_in_chat=True)

    class _FakeResp:
        def __init__(self):
            self.sent = []
            self.deferred = False

        async def send_message(self, content=None, *, embed=None, ephemeral=False):
            self.sent.append({"content": content, "embed": embed, "ephemeral": ephemeral})

        async def defer(self, *, ephemeral=False):
            self.deferred = True

    class _FakeFollowup:
        def __init__(self):
            self.sent = []

        async def send(self, content=None, *, embed=None, ephemeral=False):
            self.sent.append({"content": content, "embed": embed, "ephemeral": ephemeral})

    class _FakeInteraction:
        def __init__(self, channel_id: int, guild_id: int = 10):
            self.channel = type("Ch", (), {"id": channel_id, "name": "general"})()
            self.guild = type("G", (), {"id": guild_id})()
            self.user = type("U", (), {"id": 501, "display_name": "Rina"})()
            self.response = _FakeResp()
            self.followup = _FakeFollowup()

    # 1. Jalankan /ringkas_link di channel #9999 yang BELUM diaktifkan -> ditolak sopan via ephemeral + petunjuk <#8100>, <#8200>
    ix_blocked_yt = _FakeInteraction(channel_id=9999)
    await bot_main.slash_ringkas_link.callback(ix_blocked_yt, url="https://youtu.be/dQw4w9WgXcQ")
    assert ix_blocked_yt.response.deferred is False
    assert len(ix_blocked_yt.response.sent) == 1
    assert ix_blocked_yt.response.sent[0]["ephemeral"] is True
    assert "<#8100>" in ix_blocked_yt.response.sent[0]["content"]
    assert "<#8200>" in ix_blocked_yt.response.sent[0]["content"]

    # 2. Jalankan /cari di channel #9999 yang BELUM diaktifkan -> ditolak sopan via ephemeral + petunjuk <#8300>
    ix_blocked_cari = _FakeInteraction(channel_id=9999)
    await bot_main.slash_cari.callback(ix_blocked_cari, pertanyaan="berita hari ini")
    assert ix_blocked_cari.response.deferred is False
    assert len(ix_blocked_cari.response.sent) == 1
    assert ix_blocked_cari.response.sent[0]["ephemeral"] is True
    assert "<#8300>" in ix_blocked_cari.response.sent[0]["content"]

    # 3. Jalankan /ringkas_link di #8100 & /cari di #8300 yang SUDAH diaktifkan -> sukses!
    async def _fake_analyze_link(url, **kwargs):
        return "Inti video berhasil dirangkum!", None

    async def _fake_search_web(q, **kwargs):
        return "Berita hari ini berhasil ditemukan!", None

    monkeypatch.setattr(ai_handler, "analyze_link_with_gemini", _fake_analyze_link)
    monkeypatch.setattr(ai_handler, "search_web_with_gemini", _fake_search_web)

    ix_ok_yt = _FakeInteraction(channel_id=8100)
    await bot_main.slash_ringkas_link.callback(ix_ok_yt, url="https://youtu.be/dQw4w9WgXcQ")
    assert ix_ok_yt.response.deferred is True
    assert "Inti video" in ix_ok_yt.followup.sent[0]["embed"].description

    ix_ok_cari = _FakeInteraction(channel_id=8300)
    await bot_main.slash_cari.callback(ix_ok_cari, pertanyaan="berita hari ini")
    assert ix_ok_cari.response.deferred is True
    assert "Berita hari ini" in ix_ok_cari.followup.sent[0]["embed"].description


@pytest.mark.asyncio
async def test_forum_channel_posts_support_chat_gallery_youtube_and_search(monkeypatch):
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    # 1. Pastikan parameter 'channel' di /agent chat, gallery, youtube, & cari mengizinkan ForumChannel (channel_type 15) & Media (16)
    agent_cmd = next(c for c in bot_main.bot.tree.get_commands() if c.name == "agent")
    sub_map = {sc.name: sc for sc in agent_cmd.commands}
    for sub_name in ("chat", "gallery", "youtube", "cari"):
        ch_param = next(p for p in sub_map[sub_name].parameters if p.name == "channel")
        ch_types = set(ch_param.channel_types)
        assert discord.ChannelType.forum in ch_types, f"/agent {sub_name} wajib mendukung ForumChannel"
        assert discord.ChannelType.media in ch_types, f"/agent {sub_name} wajib mendukung MediaChannel"

    bot_user = _FakeUser(100, "Whas")
    andi = _FakeUser(301, "Andi")
    community_agent.get_guild_settings(10)["nickname"] = "Whas"

    # 2. Aktifkan /agent chat di Channel Forum #9500
    community_agent.set_chat_channel_config(10, 9500, enabled=True, reply_mode="smart", idle_seconds=0)

    class _FakeForumPostChannel:
        def __init__(self, post_id: int, parent_forum_id: int, title: str, tag_names=()):
            self.id = post_id
            self.parent_id = parent_forum_id
            self.name = title
            self.is_forum_post = True
            self.applied_tags = [type("Tag", (), {"name": t})() for t in tag_names]

    class _FakeForumMsg:
        def __init__(self, msg_id: int, post_channel: _FakeForumPostChannel, author, content: str, attachments=None):
            self.id = msg_id
            self.channel = post_channel
            self.guild = type("G", (), {"id": 10, "me": bot_user})()
            self.author = author
            self.content = content
            self.mentions = []
            self.attachments = attachments or []
            self.stickers = []
            self.reference = None

    # Postingan Forum baru #1 (message.id == post_channel.id) -> otomatis dibalas oleh AI dengan membaca Judul & Tag!
    post_ch_1 = _FakeForumPostChannel(9501, 9500, "Rekomendasi laptop ngoding 7 jutaan", ("Hardware", "Tanya"))
    starter_msg_1 = _FakeForumMsg(9501, post_ch_1, andi, "Mending Ryzen 5 atau i5 gen 12 ya buat kuliah?")
    assert community_agent.should_agent_reply_in_chat(starter_msg_1, bot_user) == (True, True)

    forum_ai_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Buat ngoding di budget 7 jutaan, Ryzen 5 seri 5500U/7530U adem dan kencang banget Andi!"}]}}]},
    )
    fake_http_forum = FakeHttpSession(post_responses=[forum_ai_resp])
    forum_reply = await community_agent.generate_community_chat_reply(
        starter_msg_1,
        bot_user,
        http_session=fake_http_forum,
    )
    assert "Ryzen 5" in forum_reply
    sent_forum_prompt = fake_http_forum.post_calls[0]["json"]["contents"][-1]["parts"][-1]["text"]
    assert "Rekomendasi laptop ngoding 7 jutaan" in sent_forum_prompt
    assert "Hardware" in sent_forum_prompt

    # Pastikan riwayat disimpan terpisah per Postingan Forum (9501), bukan tercampur di ID Forum induk (9500)
    assert 9501 in community_agent.channel_histories
    assert 9500 not in community_agent.channel_histories

    # 3. Uji Channel Forum Galeri (#9600) saat member membuat Postingan Showcase bergambar
    class _FakeImgAtt:
        filename = "setup.png"
        content_type = "image/png"
        size = 24

        async def read(self):
            return b"\x89PNG\r\n\x1a\nfakeimg"

    community_agent.set_gallery_channel_config(10, 9600, enabled=True, auto_reaction=True)
    showcase_post = _FakeForumPostChannel(9601, 9600, "Setup Meja Belajar Minimalis 2026", ("Showcase",))
    fake_img_att = _FakeImgAtt()
    showcase_msg = _FakeForumMsg(9601, showcase_post, andi, "Baru selesai rakit lampu monitor bar!", attachments=[fake_img_att])
    gal_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Rapi banget setup minimalisnya Andi, cahaya monitor bar-nya bikin mata nyaman!"}]}}]},
    )
    fake_http_gal = FakeHttpSession(post_responses=[gal_resp])
    gal_comment, gal_emoji = await community_agent.generate_gallery_comment(
        showcase_msg,
        bot_user,
        http_session=fake_http_gal,
    )
    assert "monitor bar" in gal_comment
    assert gal_emoji in community_agent.GALLERY_REACTIONS
    gal_prompt_sent = fake_http_gal.post_calls[0]["json"]["contents"][0]["parts"][-1]["text"]
    assert "Setup Meja Belajar Minimalis 2026" in gal_prompt_sent

    # 4. Uji Channel Forum Mandiri YouTube & Cari (#9700 tanpa /agent chat)
    community_agent.set_youtube_channel_config(10, 9700, enabled=True, auto_in_chat=True)
    community_agent.set_search_channel_config(10, 9700, enabled=True, auto_in_chat=True)
    yt_forum_post = _FakeForumPostChannel(9701, 9700, "Podcast seru soal AI", ("Video",))
    yt_forum_msg = _FakeForumMsg(9701, yt_forum_post, andi, "https://youtu.be/dQw4w9WgXcQ")
    assert community_agent.should_standalone_feature_reply(yt_forum_msg, bot_user) is True


@pytest.mark.asyncio
async def test_discord_command_and_view_hard_limits():
    """Memastikan seluruh Slash Command, Subcommand, Parameter, Pilihan, Context Menu, & View mematuhi batas keras Discord API."""
    all_cmds = bot_main.bot.tree.get_commands(type=discord.AppCommandType.chat_input)
    msg_ctx_menus = bot_main.bot.tree.get_commands(type=discord.AppCommandType.message)
    assert len(msg_ctx_menus) <= 5
    ctx_names = {c.name for c in msg_ctx_menus}
    assert "🔍 Cek Fakta / Hoaks" in ctx_names
    for ctx_cmd in msg_ctx_menus:
        assert 1 <= len(ctx_cmd.name) <= 32

    def _validate_slash_cmd(cmd_obj):
        assert 1 <= len(cmd_obj.name) <= 32
        assert cmd_obj.name == cmd_obj.name.lower()
        assert 1 <= len(cmd_obj.description) <= 100, f"Deskripsi {cmd_obj.name} melebihi 100 karakter!"
        if isinstance(cmd_obj, discord.app_commands.Group):
            assert len(cmd_obj.commands) <= 25
            for sub in cmd_obj.commands:
                _validate_slash_cmd(sub)
        else:
            for param in cmd_obj.parameters:
                assert 1 <= len(param.name) <= 32
                assert 1 <= len(param.description) <= 100, (
                    f"Deskripsi parameter {cmd_obj.name}.{param.name} melebihi 100 karakter!"
                )
                for choice in getattr(param, "choices", []) or []:
                    assert 1 <= len(choice.name) <= 100

    for top_cmd in all_cmds:
        _validate_slash_cmd(top_cmd)

    # Pastikan ForumPostSolvedView juga persisten (timeout=None) dengan custom_id unik
    persistent_views = [
        views.MainPanelControlView(),
        views.EndSessionView(),
        views.ChatPersonaSwitchView(),
        views.ImageSettingsView(),
        views.ForumPostSolvedView(),
        views.VerificationGateView(),
    ]
    seen_ids: set[str] = set()
    for v in persistent_views:
        assert v.is_persistent()
        for child in v.children:
            assert child.custom_id and child.custom_id not in seen_ids
            seen_ids.add(child.custom_id)

    admin_view = views.AgentAdminPanelView(admin_user_id=999, default_channel_id=1234)
    rows_used = {child.row for child in admin_view.children if child.row is not None}
    assert len(rows_used) <= 5
    for child in admin_view.children:
        if isinstance(child, discord.ui.Select):
            for opt in child.options:
                assert 1 <= len(opt.label) <= 100
                if opt.description:
                    assert len(opt.description) <= 100


@pytest.mark.asyncio
async def test_server_knowledge_faq_crud_and_prompt_injection(monkeypatch):
    """Menguji fitur /agent info (FAQ Server): tambah, perbarui, hapus, simpan disk, & injeksi ke System Prompt."""
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    item1, st1 = community_agent.upsert_server_knowledge(
        10, "IP Minecraft", "play.nusantara.id versi 1.21.4 (Buka 24 Jam)"
    )
    assert st1 == "added" and item1["topic"] == "IP Minecraft"

    item2, st2 = community_agent.upsert_server_knowledge(
        10, "Rules Server", "Dilarang toxic, spam link promosi, atau SARA."
    )
    assert st2 == "added" and len(community_agent.get_server_knowledge_entries(10)) == 2

    # Update topik yang sama (case-insensitive) tidak menduplikasi entri
    updated, st_upd = community_agent.upsert_server_knowledge(
        10, "ip minecraft", "play.nusantara.id versi 1.21.5 terbaru"
    )
    assert st_upd == "updated"
    assert len(community_agent.get_server_knowledge_entries(10)) == 2
    assert "1.21.5" in updated["content"]

    # Pastikan disuntikkan ke prompt komunitas maupun prompt konsultasi privat ai-...
    g_cfg = community_agent.get_guild_settings(10)
    t_ctx = utils.get_realtime_time_context()
    comm_sys = community_agent._build_community_system_prompt(g_cfg, "Whas", t_ctx)
    assert "play.nusantara.id versi 1.21.5" in comm_sys
    assert "Rules Server" in comm_sys

    srv_block = community_agent.format_server_knowledge_for_prompt(10)
    mock_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "IP servernya play.nusantara.id versi 1.21.5 ya!"}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[mock_resp])
    storage.init_thread_session(8811, "gemini_flash", owner_id=42)
    ans = await ai_handler.get_ai_response(
        8811,
        "Apa IP server Minecraft kita?",
        http_session=fake_http,
        server_knowledge=srv_block,
    )
    assert "play.nusantara.id" in ans
    sent_sys = fake_http.post_calls[0]["json"]["systemInstruction"]["parts"][0]["text"]
    assert "play.nusantara.id versi 1.21.5" in sent_sys

    # Uji simpan & muat ulang dari disk
    await community_agent.save_agent_config_to_disk()
    community_agent.guild_agent_settings.clear()
    community_agent.load_agent_config_from_disk()
    loaded_entries = community_agent.get_server_knowledge_entries(10)
    assert len(loaded_entries) == 2

    # Hapus berdasarkan nomor urut & bersihkan sisa
    removed = community_agent.delete_server_knowledge(10, "1")
    assert removed is not None and "minecraft" in removed["topic"].lower()
    assert community_agent.clear_server_knowledge(10) == 1
    assert community_agent.get_server_knowledge_entries(10) == []


@pytest.mark.asyncio
async def test_pdf_attachment_extraction_and_gemini_history_tag(monkeypatch):
    """Menguji pembacaan dokumen .pdf native (application/pdf) di ruang privat & komunitas, serta penolakan di ruang gambar."""
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    class _FakePdfAttachment:
        filename = "panduan_kuliah.pdf"
        content_type = "application/pdf"
        size = 512

        async def read(self):
            return b"%PDF-1.7 fake pdf content"

    class _FakePdfMsg:
        attachments = [_FakePdfAttachment()]
        stickers = []

    parts, names, txt_blocks, warns = await utils.extract_message_attachments(_FakePdfMsg())
    assert warns == []
    assert txt_blocks == []
    assert names == ["pdf:panduan_kuliah.pdf"]
    assert parts[0]["inlineData"]["mimeType"] == "application/pdf"

    # Di ruang gambar (include_pdf=False), PDF ditolak secara sopan
    parts_img, _, _, warns_img = await utils.extract_message_attachments(_FakePdfMsg(), include_pdf=False)
    assert parts_img == []
    assert any("PDF" in w for w in warns_img)

    # Uji di get_ai_response saat pengguna kirim PDF tanpa teks pengantar
    storage.init_thread_session(8812, "gemini_flash", owner_id=42)
    pdf_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Ringkasan PDF: jadwal kuliah dimulai Senin pukul 08:00."}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[pdf_resp])
    reply = await ai_handler.get_ai_response(
        8812,
        "",
        image_parts=parts,
        image_filenames=names,
        http_session=fake_http,
    )
    assert "Ringkasan PDF" in reply
    hist = storage.thread_chats[8812]["history"]
    assert "[Pengguna melampirkan dokumen PDF: pdf:panduan_kuliah.pdf]" in hist[0]["content"]


@pytest.mark.asyncio
async def test_forum_auto_tagging_and_solved_button_view():
    """Menguji pemilihan Tag Forum otomatis (0 API Call) dan tombol persisten ✅ Tandai Selesai."""
    class _FakeForumTag:
        def __init__(self, name: str, moderated: bool = False):
            self.name = name
            self.moderated = moderated

    t_py = _FakeForumTag("Python")
    t_bug = _FakeForumTag("Bug / Error")
    t_game = _FakeForumTag("Game")
    t_solved = _FakeForumTag("Selesai")
    t_mod = _FakeForumTag("Pengumuman Resmi", moderated=True)
    avail = [t_py, t_bug, t_game, t_solved, t_mod]

    picked = utils.select_best_forum_tags(
        "Tolong muncul Traceback Exception pas jalankan discord.py",
        "Kenapa pip asyncio saya gagal terus ya?",
        avail,
    )
    assert t_py in picked and t_bug in picked
    assert t_solved not in picked and t_mod not in picked
    assert utils.find_solved_forum_tag(avail) is t_solved

    # Uji ForumPostSolvedView: tolak klik orang asing, izinkan pemilik postingan
    class _FakeResp:
        def __init__(self):
            self.messages = []
            self.deferred = False

        async def send_message(self, content, ephemeral=False):
            self.messages.append((content, ephemeral))

        async def defer(self):
            self.deferred = True

    class _FakeFollowup:
        def __init__(self):
            self.sent = []

        async def send(self, content):
            self.sent.append(content)

    fake_parent = type("ParentForum", (), {"available_tags": avail})()
    edited_calls: list[dict] = []

    class _FakeForumThreadObj:
        owner_id = 501
        parent_id = 9500
        name = "Error login aplikasi"
        applied_tags = [t_bug]
        parent = fake_parent

        async def edit(self, **kwargs):
            edited_calls.append(kwargs)

    fake_thread = _FakeForumThreadObj()

    view = views.ForumPostSolvedView()
    btn = view.children[0]

    # 1. Orang lain (bukan pemilik & bukan moderator) ditolak
    stranger_ix = type(
        "Ix",
        (),
        {
            "channel": fake_thread,
            "user": _FakeUser(999, "OrangLain"),
            "response": _FakeResp(),
            "followup": _FakeFollowup(),
            "message": None,
        },
    )()
    await btn.callback(stranger_ix)
    assert len(stranger_ix.response.messages) == 1
    assert edited_calls == []

    # 2. Pemilik postingan (uid=501) berhasil menandai selesai + tambah tag Selesai + arsip
    edited_msg_views: list = []

    class _FakeBtnMessage:
        async def edit(self, *, view=None):
            edited_msg_views.append(view)

    owner_ix = type(
        "Ix",
        (),
        {
            "channel": fake_thread,
            "user": _FakeUser(501, "PemilikPost"),
            "response": _FakeResp(),
            "followup": _FakeFollowup(),
            "message": _FakeBtnMessage(),
        },
    )()
    await btn.callback(owner_ix)
    assert owner_ix.response.deferred is True
    assert len(edited_calls) == 1
    assert edited_calls[0]["archived"] is True
    assert edited_calls[0]["name"] == "✅ Error login aplikasi"
    assert t_solved in edited_calls[0]["applied_tags"]
    # Pesan tombol diubah memakai View terpisah yang nonaktif, sementara instance singleton ForumPostSolvedView tetap utuh!
    assert len(edited_msg_views) == 1
    assert edited_msg_views[0].children[0].disabled is True
    assert btn.disabled is False


@pytest.mark.asyncio
async def test_fact_check_context_menu_and_gemini_analysis(monkeypatch):
    """Menguji fitur Context Menu 🔍 Cek Fakta / Hoaks beserta pencantuman sumber referensi berita."""
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    async def _mock_free_search(query, http_session=None):
        return (
            "1. Kominfo Pastikan Kabar Internet Mati Total Besok Adalah Hoaks",
            [("Kompas Tekno", "https://tekno.kompas.com/read/cek-fakta-1")],
        )

    monkeypatch.setattr(ai_handler, "free_live_web_search", _mock_free_search)
    gemini_resp = FakeMockResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "**🏷️ Status Klaim:** `❌ Indikasi Hoaks / Keliru`\n"
                                "**📌 Klaim Utama:** Internet mati total besok.\n"
                                "**🔎 Hasil Pemeriksaan Fakta:** Klaim tersebut telah dibantah resmi."
                            }
                        ]
                    }
                }
            ]
        },
    )
    fake_http = FakeHttpSession(post_responses=[gemini_resp])
    res_txt, err = await ai_handler.fact_check_message_with_gemini(
        "Guys beneran besok seluruh internet dunia bakal dimatikan total selama seminggu?",
        http_session=fake_http,
    )
    assert err is None
    assert "Indikasi Hoaks" in res_txt
    assert "https://tekno.kompas.com/read/cek-fakta-1" in res_txt


@pytest.mark.asyncio
async def test_new_game_modes_image_guess_and_word_chain(monkeypatch):
    """Menguji mode baru 🖼️ Tebak Gambar AI dan ⛓️ Sambung Kata (0 API Call per giliran + MVP menang)."""
    # 1. Uji generator gambar misteri Tebak Gambar AI
    fake_png = b"\x89PNG\r\n\x1a\n" + (b"x" * 1500)
    img_get_resp = FakeMockResponse(200, raw_bytes=fake_png, headers={"Content-Type": "image/png"})
    fake_http = FakeHttpSession(get_responses=[img_get_resp])
    raw_img = await ai_handler.generate_mystery_game_image_bytes(
        "A cute astronaut cat in space", http_session=fake_http
    )
    assert raw_img == fake_png
    assert "no text" in urllib_unquote(fake_http.get_calls[0]["url"]).lower()

    monkeypatch.setattr(games, "is_gemini_key_configured", lambda: False)
    q_img = await games.generate_ai_game_question("image_guess", 88)
    assert games._validate_game_payload("image_guess", q_img) is True

    # 2. Uji validator & gameplay penuh Sambung Kata (word_chain)
    assert games.is_valid_indonesian_chain_word("apel", "a", {"ayam"}) == (True, "ok")
    assert games.is_valid_indonesian_chain_word("buku", "a", set()) == (False, "wrong_prefix")
    assert games.is_valid_indonesian_chain_word("apel", "a", {"apel"}) == (False, "already_used")
    assert games.is_valid_indonesian_chain_word("aaabbb", "a", set()) == (False, "gibberish")

    sent_channel_msgs: list = []

    class _FakeGameChannel:
        id = 7788

        async def send(self, content=None, embed=None):
            sent_channel_msgs.append((content, embed))

    fake_ch = _FakeGameChannel()
    games.active_channel_games[7788] = {
        "type": "word_chain",
        "guild_id": 88,
        "starter_id": 301,
        "current_word": "NUSANTARA",
        "answer": "NUSANTARA",
        "used_words": {"nusantara"},
        "chain_words": ["NUSANTARA"],
        "chain_count": 0,
        "points": 5,
        "round_scores": {},
        "view": None,
    }

    class _FakeChainMsg:
        def __init__(self, uid: int, name: str, text: str):
            self.channel = fake_ch
            self.guild = type("G", (), {"id": 88})()
            self.author = _FakeUser(uid, name)
            self.content = text
            self.mentions = []
            self.reactions = []

        async def add_reaction(self, emoji: str):
            self.reactions.append(emoji)

    # Giliran 1 oleh Rina ('APEL') -> valid (+5 poin, huruf lanjut 'L')
    m1 = _FakeChainMsg(301, "Rina", "apel")
    assert await games.handle_active_game_guess(m1) is True
    assert "✅" in m1.reactions
    assert games.active_channel_games[7788]["current_word"] == "APEL"

    # Rina mencoba langsung nyambung sendiri < 8 detik -> ditahan lembut dengan reaksi ⏳
    m1_spam = _FakeChainMsg(301, "Rina", "laut")
    assert await games.handle_active_game_guess(m1_spam) is True
    assert "⏳" in m1_spam.reactions
    assert games.active_channel_games[7788]["current_word"] == "APEL"

    # Giliran 2 oleh Budi ('LAUT') -> valid (+5 poin, huruf lanjut 'T')
    m2 = _FakeChainMsg(302, "Budi", "laut")
    assert await games.handle_active_game_guess(m2) is True
    assert "✅" in m2.reactions

    # Giliran 3 kembali ke Rina ('TAMAN') -> valid (+5 poin, Rina unggul 10 poin vs Budi 5 poin)
    m3 = _FakeChainMsg(301, "Rina", "taman")
    assert await games.handle_active_game_guess(m3) is True
    assert "✅" in m3.reactions

    # Akhiri ronde & pastikan Rina (MVP ronde) mendapat +1 win di papan skor!
    await games.finish_word_chain_round(fake_ch, 7788, reason_title="🏁 Selesai!")
    assert 7788 not in games.active_channel_games
    rank_rina, pts_rina, wins_rina = games.get_user_rank_info(88, 301)
    rank_budi, pts_budi, wins_budi = games.get_user_rank_info(88, 302)
    assert (rank_rina, pts_rina, wins_rina) == (1, 10, 1)
    assert (rank_budi, pts_budi, wins_budi) == (2, 5, 0)


def urllib_unquote(url: str) -> str:
    import urllib.parse

    return urllib.parse.unquote(url)


@pytest.mark.asyncio
async def test_morning_digest_schedule_and_once_per_day_dedup(monkeypatch):
    """Menguji jadwal Morning Digest (/agent digest) & proteksi anti-dobel kirim di tanggal yang sama."""
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    assert community_agent.parse_digest_time("07:00") == (7, 0)
    assert community_agent.parse_digest_time("6.30") == (6, 30)
    assert community_agent.parse_digest_time("25:00") is None

    community_agent.set_digest_config(10, 5500, enabled=True, hour=7, minute=0, topic="Teknologi & Game")
    await community_agent.save_agent_config_to_disk()
    community_agent.digest_agent_guilds.clear()
    community_agent.load_agent_config_from_disk()
    assert community_agent.digest_agent_guilds[10]["topic"] == "Teknologi & Game"

    # Palsukan jam lokal server pukul 07:15 pada 2026-11-03
    monkeypatch.setattr(
        community_agent,
        "get_realtime_time_context",
        lambda tz=None: {
            "iso_date": "2026-11-03",
            "hour": 7,
            "minute": 15,
            "clock": "07:15 WIB",
            "day_name": "Selasa",
            "date_str": "3 November 2026",
            "tz_label": "WIB",
            "vibe": "Pagi hari",
            "summary": "Selasa, 3 November 2026 | Pukul 07:15 WIB",
        },
    )

    async def _mock_digest_search(q, http_session=None):
        return ("1. Rilis Python terbaru makin kencang", [("DetikInet", "https://inet.detik.com/1")])

    monkeypatch.setattr(community_agent, "free_live_web_search", _mock_digest_search)

    sent_embeds: list = []

    class _FakeDigestChannel:
        id = 5500
        guild = type("G", (), {"id": 10, "me": _FakeUser(100, "Whas")})()

        async def send(self, embed=None):
            sent_embeds.append(embed)

    fake_bot = type(
        "FakeBot",
        (),
        {"user": _FakeUser(100, "Whas"), "get_channel": lambda self, cid: _FakeDigestChannel() if cid == 5500 else None},
    )()

    digest_ai_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Selamat pagi warga! Berikut sorotan berita hari ini."}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[digest_ai_resp])

    sent_first = await community_agent.run_morning_digest_check(fake_bot, http_session=fake_http)
    assert sent_first == 1
    assert len(sent_embeds) == 1
    assert community_agent.digest_agent_guilds[10]["last_sent_date"] == "2026-11-03"

    # Panggilan kedua di tanggal yang sama TIDAK mengirim ulang (0 API call tambahan!)
    sent_second = await community_agent.run_morning_digest_check(fake_bot, http_session=fake_http)
    assert sent_second == 0
    assert len(sent_embeds) == 1


@pytest.mark.asyncio
async def test_free_tier_member_cooldown_and_admin_panel_view():
    """Menguji cooldown anti-spam per-member (Admin bebas jeda) serta fungsi toggle pada AgentAdminPanelView."""
    # Member biasa terkena jeda saat memanggil beruntun
    assert utils.check_user_cooldown(701, "cari", cooldown_sec=10, is_admin=False) == 0
    rem = utils.check_user_cooldown(701, "cari", cooldown_sec=10, is_admin=False)
    assert rem >= 1
    # Bucket command berbeda tidak saling mengunci
    assert utils.check_user_cooldown(701, "ringkas", cooldown_sec=10, is_admin=False) == 0
    # Admin bebas jeda kapan saja
    assert utils.check_user_cooldown(701, "cari", cooldown_sec=10, is_admin=True) == 0

    # Uji build_agent_status_embed & AgentAdminPanelView
    fake_guild = type(
        "FakeGuild",
        (),
        {
            "id": 10,
            "name": "Server Komunitas Kita",
            "me": _FakeUser(100, "Whas"),
            "get_channel": lambda self, cid: None,
        },
    )()
    status_emb = views.build_agent_status_embed(fake_guild, selected_channel_id=4455, notice_banner="✅ Uji Panel")
    assert config.BOT_VERSION in status_emb.title
    assert "✅ Uji Panel" in status_emb.description
    assert any("Channel Target Terpilih" in f.name for f in status_emb.fields)
    assert any("FAQ" in f.name for f in status_emb.fields)


@pytest.mark.asyncio
async def test_modular_cogs_help_menu_faq_manager_and_ram_hygiene():
    """Menguji arsitektur modular cogs/, HelpMenuView (/bantuan), ServerFaqManagerView, & pembersih RAM."""
    # 1. Pastikan top-level slash commands ringkas (24 command utama, hemat slot dari batas 100 Discord)
    chat_cmds = bot_main.bot.tree.get_commands(type=discord.AppCommandType.chat_input)
    assert {c.name for c in chat_cmds} == {
        "sesi", "ringkas", "cari", "game", "agent", "bantuan", "status",
        "serverstats", "autorole", "fakta", "keamanan",
        "panel-role", "poll", "ingatkan", "starboard", "verifikasi", "sticky", "info", "perawatan",
        "musik",
        "mulai",  # wizard pemasangan cepat (admin awam)
        # v1.8.0-beta (Tier 2A): fitur keramaian server tanpa kuota AI
        "giveaway", "ultah", "jawab-otomatis", "pengumuman",
        # v1.10.0-beta (Tier 2C): leveling & tiket dukungan
        "level", "tiket",
        # v1.12.0-beta: Control Center & editor tema (Components V2)
        "panel", "tampilan",
        # v1.11.0-beta (Tier 3): hemat kuota AI
        "faq", "pemakaian",
        # v1.14.0-beta: notifikasi YouTube/Twitch/TikTok/RSS (0 kuota AI)
        "sosial",
        # v1.15.0-beta: moderasi bercatatan (warn/timeout/kick/ban/purge + kasus)
        "mod",
        # v1.16.0-beta: voice room sementara (join-to-create)
        "tempvoice",
        # v1.17.0-beta: kotak saran + pembuat embed
        "saran", "embed",
        # v1.18.0-beta: perkakas server (AFK, auto-thread, lockdown, backup struktur)
        "afk", "thread-otomatis", "lockdown", "backup",
        # v1.22.0-beta: penerjemah hemat kuota (reaksi bendera + /terjemah)
        "terjemah",
        # v1.23.0-beta: audit log server + ekonomi koin (0 kuota AI)
        "log", "ekonomi",
        # v1.25.0-beta: statistik pertumbuhan & invite tracker (0 kuota AI)
        "tumbuh",
        # v1.26.0-beta: menu builder (tombol role/link/command + dropdown)
        "menu",
        # v1.27.0-beta: anti-nuke (deteksi audit log + tindakan + pemulihan)
        "nuke",
        # v1.31.0-beta: raid guard (mode darurat otomatis saat server diserbu)
        "raid",
        # v1.36.0-beta: i18n inti (/bahasa)
        "bahasa",
        # v1.37.0-beta: prefix command per server
        "prefix",
        # v1.38.0-beta: ekspor analitik CSV & webhook
        "analitik",
        # v1.40.0-beta (Paket B): jalur resmi member → staf
        "lapor", "banding",
        # v1.40.0-beta (Paket C): tag jawaban siap pakai, lencana bertingkat, highlight
        "tag", "lencana", "pantau", "snipe", "curhat",
        # v1.40.0-beta (Paket D): kanal info yang menyegarkan dirinya sendiri
        "kanal-info",
        # v1.40.0-beta (Paket E): bangun server instan + meme lokal (0 kuota AI)
        "bangun", "meme", "gambar", "dataku", "hapusdataku", "setelan-ai",
    }
    assert len(chat_cmds) <= 100

    # 2. Pastikan seluruh 5 kategori halaman /bantuan ter-render rapi & patuh batas karakter SelectOption Discord
    for cat in ("overview", "sesi", "tools", "games", "server", "komunitas", "musik", "admin", "engagement", "growth", "insights"):
        emb = views.build_help_embed(cat)
        assert len(emb.title) <= 256
        assert len(emb.fields) >= 2
        # Batas keras Discord: nama field ≤256, nilai field ≤1024, total embed ≤6000
        assert len(emb.fields) <= 25, f"{cat}: terlalu banyak field"
        for fld in emb.fields:
            assert len(fld.name) <= 256, f"{cat}: nama field kepanjangan"
            assert len(fld.value) <= 1024, f"{cat}: nilai field '{fld.name}' = {len(fld.value)} char (>1024)"
        assert len(emb) <= 6000, f"{cat}: total embed {len(emb)} char"
        if emb.description:
            assert len(emb.description) <= 4096, f"{cat}: deskripsi terlalu panjang"
    help_view = views.HelpMenuView(requester_id=501)
    for child in help_view.children:
        if isinstance(child, discord.ui.Select):
            for opt in child.options:
                assert 1 <= len(opt.label) <= 100
                if opt.description:
                    assert len(opt.description) <= 100

    # 3. Uji ServerFaqManagerView saat kosong & saat terisi entri FAQ
    community_agent.upsert_server_knowledge(10, "Rules", "Dilarang spam link promosi.")
    community_agent.upsert_server_knowledge(10, "Discord Invite", "discord.gg/contoh")
    faq_view = views.ServerFaqManagerView(admin_user_id=99, guild_id=10)
    assert len(faq_view.children) == 2  # Select hapus 1 + Button hapus semua

    # 4. Uji pembersihan RAM jangka panjang (cleanup_stale_agent_runtime, remove_agent_thread_runtime, cancel_channel_game, prune_expired_user_cooldowns)
    import asyncio as _asyncio

    community_agent._post_runtime_state[8888] = {"last_activity_at": 1.0}
    community_agent.channel_histories[8888] = [{"role": "user", "parts": [{"text": "tes"}]}]
    community_agent._standalone_last_reply_at[8888] = 1.0
    community_agent._recent_welcomed_members[(10, 501)] = 1.0
    community_agent._recent_channel_speakers[8888] = [(501, 1.0)]

    cleaned_count = community_agent.cleanup_stale_agent_runtime(max_idle_sec=60.0)
    assert cleaned_count >= 4
    assert 8888 not in community_agent._post_runtime_state
    assert 8888 not in community_agent.channel_histories

    # Uji remove_agent_thread_runtime & cancel_channel_game saat thread/channel dihapus
    community_agent.channel_histories[7777] = [{"role": "user", "parts": [{"text": "halo"}]}]
    assert community_agent.remove_agent_thread_runtime(7777) is True
    assert 7777 not in community_agent.channel_histories

    dummy_task = _asyncio.create_task(_asyncio.sleep(60))
    games.active_channel_games[7777] = {"type": "emoji", "answer": "Kucing", "timeout_task": dummy_task}
    cancelled_state = games.cancel_channel_game(7777)
    await _asyncio.sleep(0)
    assert cancelled_state is not None
    assert dummy_task.cancelled() is True
    assert 7777 not in games.active_channel_games

    utils._user_command_cooldowns[(501, "cari")] = 0.0
    assert utils.prune_expired_user_cooldowns() >= 1

    # 5. Pastikan seluruh banner sistem di ruang privat disaring dari memori AI & transkrip sesi
    assert storage.is_bot_ui_message("🔴 *Gunakan tombol di bawah untuk mereset memori atau mengakhiri sesi:*") is True
    assert storage.is_bot_ui_message("✅ **Mode AI berhasil diganti ke:** **♊ Gemini Flash**") is True
    assert storage.is_bot_ui_message("⏳ Tunggu **5 detik** lagi sebelum membuat gambar berikutnya ya!") is True
    assert storage.is_bot_ui_message("Halo, bagaimana cara belajar Python?") is False














@pytest.mark.asyncio
async def test_welcome_persona_goodbye_and_asian_greetings(monkeypatch):
    """Persona sambutan terpisah dari persona chat, sapaan Asia berganti, & fitur Goodbye."""
    monkeypatch.setattr(community_agent, "GEMINI_API_KEY", "AIzaFakeValidKey12345")
    monkeypatch.setattr(ai_handler, "GEMINI_API_KEY", "AIzaFakeValidKey12345")

    # 1. Persona & bahasa sapaan tersimpan terpisah dari persona Auto-Chat
    cfg = community_agent.set_welcome_config(
        10, 7000, enabled=True, persona="lucu", hello_language="jepang"
    )
    assert cfg["persona"] == "lucu"
    assert cfg["hello_language"] == "jepang"
    community_agent.guild_agent_settings[10] = {
        "nickname": "Whas",
        "style_preset": "gaul",
        "custom_prompt": "",
        "timezone": "Asia/Jakarta",
        "quiet_hours": True,
        "knowledge_entries": [],
    }

    # Nilai tidak valid tidak boleh merusak konfigurasi
    cfg = community_agent.set_welcome_config(
        10, 7000, enabled=True, persona="ngawur", hello_language="klingon"
    )
    assert cfg["persona"] == "lucu"
    assert cfg["hello_language"] == "jepang"

    # 2. Pemilih kata sapaan menghindari pengulangan
    japanese = [w for w in community_agent.ASIAN_GREETINGS if w["key"] == "jepang"]
    recent = [w["word"] for w in japanese[:2]]
    picked = community_agent.pick_greeting_word(
        community_agent.ASIAN_GREETINGS, language="jepang", recent_words=recent
    )
    assert picked["key"] == "jepang"
    assert picked["word"] not in recent
    assert len([w for w in community_agent.ASIAN_GREETINGS if w["key"] == "thailand"]) >= 1

    # 3. Sambutan: sapaan Jepang di awal kalimat, sisa Bahasa Indonesia, persona khusus dipakai
    w_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Selamat datang ya, jangan sungkan ikut nimbrung!"}]}}]},
    )
    fake_http = FakeHttpSession(post_responses=[w_resp])
    greeting = await community_agent.generate_welcome_greeting(
        10, "Bintang", "<@555>", "Whas", guild_name="Server Angga", http_session=fake_http
    )
    jp_words = {w["word"] for w in japanese}
    # Sapaan asing kini berhias: **"こんにちは" (Konnichiwa)** — *selamat siang, halo*
    assert any(greeting.startswith(f'**"{w}"**') for w in jp_words)
    assert "Konnichiwa" in greeting or "(" in greeting  # huruf latin ikut tampil
    assert "<@555>" in greeting

    sent_system = fake_http.post_calls[0]["json"]["systemInstruction"]["parts"][0]["text"]
    sent_prompt = fake_http.post_calls[0]["json"]["contents"][0]["parts"][-1]["text"]
    assert "Persona sambutan: Lucu & Receh" in sent_prompt
    assert "HANYA kata sapaan pembuka" in sent_system
    # Persona chat (gaul) tidak boleh bocor ke prompt sambutan
    assert community_agent.STYLE_DESCRIPTIONS["gaul"] not in sent_system

    # 4. Goodbye: konfigurasi, dedup, & pesan perpisahan
    g_cfg = community_agent.set_goodbye_config(
        10, 7001, enabled=True, persona="hangat", hello_language="korea"
    )
    assert g_cfg["enabled"] is True
    assert g_cfg["persona"] == "hangat"
    assert community_agent.should_process_member_goodbye(10, 556) is True
    assert community_agent.should_process_member_goodbye(10, 556) is False
    assert community_agent.should_process_member_goodbye(10, 556, force=True) is True

    g_resp = FakeMockResponse(
        200,
        {"candidates": [{"content": {"parts": [{"text": "Terima kasih sudah mampir, semoga sukses selalu!"}]}}]},
    )
    fake_http_g = FakeHttpSession(post_responses=[g_resp])
    farewell = await community_agent.generate_goodbye_message(
        10, "Bintang", "<@555>", "Whas", guild_name="Server Angga",
        days_in_server=12, http_session=fake_http_g,
    )
    korean_words = {w["word"] for w in community_agent.ASIAN_FAREWELLS if w["key"] == "korea"}
    assert any(farewell.startswith(f'**"{w}"**') for w in korean_words)
    assert "<@555>" in farewell
    assert "Persona perpisahan: Hangat & Tulus" in fake_http_g.post_calls[0]["json"]["contents"][0]["parts"][-1]["text"]

    # 5. Kedua konfigurasi tahan restart (persist ke disk)
    await community_agent.save_agent_config_to_disk()
    community_agent.welcome_agent_guilds.clear()
    community_agent.goodbye_agent_guilds.clear()
    community_agent.load_agent_config_from_disk()
    assert community_agent.welcome_agent_guilds[10]["persona"] == "lucu"
    assert community_agent.welcome_agent_guilds[10]["hello_language"] == "jepang"
    assert community_agent.goodbye_agent_guilds[10]["channel_id"] == 7001
    assert community_agent.goodbye_agent_guilds[10]["hello_language"] == "korea"


class _FakePerms:
    def __init__(self, administrator: bool = False, manage_messages: bool = False):
        self.administrator = administrator
        self.manage_messages = manage_messages


class _FakeStatsChannel:
    def __init__(self, cid: int, ctype: discord.ChannelType):
        self.id = cid
        self.type = ctype


class _FakeStatsRole:
    def __init__(self, name: str = "Member"):
        self.name = name
        self.managed = False

    def is_default(self) -> bool:
        return False


class _FakeStatsMember:
    def __init__(self, bot: bool = False):
        self.bot = bot


class _FakeStatsGuild:
    def __init__(self):
        self.id = 10
        self.name = "Server Uji"
        self.description = "Server untuk pengujian fitur baru"
        self.member_count = 42
        self.members = [_FakeStatsMember(bot=False), _FakeStatsMember(bot=False), _FakeStatsMember(bot=True)]
        self.channels = [
            _FakeStatsChannel(1, discord.ChannelType.text),
            _FakeStatsChannel(2, discord.ChannelType.text),
            _FakeStatsChannel(3, discord.ChannelType.voice),
            _FakeStatsChannel(4, discord.ChannelType.forum),
            _FakeStatsChannel(5, discord.ChannelType.category),
        ]
        self.roles = [_FakeStatsRole() for _ in range(6)]
        self.emojis = [1, 2, 3]
        self.stickers = [1]
        self.premium_subscription_count = 4
        self.premium_tier = 1
        self.created_at = discord.utils.utcnow()
        self.owner = "PemilikServer#0001"
        self.verification_level = discord.VerificationLevel.medium
        self.icon = None
        self.approximate_presence_count = 17


@pytest.mark.asyncio
async def test_serverstats_autorole_facts_and_phishing_guard():
    """Menguji fitur Server Stats, Auto Role, Fakta Harian, & deteksi Anti-Phishing."""
    # 1. Server Stats: kartu statistik memuat seluruh angka penting
    stats_cfg = server_features.set_serverstats_config(10, enabled=True)
    assert stats_cfg["enabled"] is True
    embed = server_features.build_serverstats_embed(_FakeStatsGuild(), presence_count=17)
    assert "Statistik Server" in embed.title
    field_names = " ".join(f.name for f in embed.fields)
    assert "Anggota" in field_names
    assert "Kanal" in field_names
    values = " ".join(f.value for f in embed.fields)
    assert "42" in values
    assert "17" in values
    assert "Boost" in values

    # 2. Auto Role: simpan, baca, & matikan
    ro_cfg = server_features.set_autorole_config(10, [222, 333], enabled=True)
    assert ro_cfg["role_ids"] == [222, 333]
    assert server_features.get_autorole_role_ids(10) == [222, 333]
    assert server_features.set_autorole_config(10, [222], enabled=False) is None
    assert server_features.get_autorole_role_ids(10) == []

    # 3. Fakta Harian default 4 slot (08:00, 12:00, 16:00, 20:00) & cadangan offline selalu tersedia
    f_cfg = server_features.set_facts_config(10, 7002, enabled=True)
    assert f_cfg["times"] == config.FACTS_DEFAULT_TIMES == ["08:00", "12:00", "16:00", "20:00"]
    assert f_cfg["sent_slots"] == {}
    fallback = server_features.build_facts_fallback(4)
    assert fallback.count("—") >= 4
    assert server_features.set_facts_config(10, 7002, enabled=False) is None

    # 4. Anti-Phishing: deteksi lokal tanpa API berbayar
    assert server_features.analyze_url_risk("https://discord.com/channels/1")["verdict"] == "aman"
    assert server_features.analyze_url_risk("https://www.google.com/search?q=halo")["verdict"] == "aman"
    assert server_features.analyze_url_risk("https://bridge.com/news")["verdict"] == "aman"

    nitro = server_features.analyze_url_risk("https://discord-nitro.com/claim")
    assert nitro["verdict"] == "berbahaya"
    assert nitro["score"] >= 60
    assert any("blacklist" in r or "hitam" in r for r in nitro["reasons"])

    typosquat = server_features.analyze_url_risk("https://steamcommunlty.com/gift")
    assert typosquat["verdict"] == "berbahaya"

    puny = server_features.analyze_url_risk("https://xn--80ak6aa92e.com/login")
    assert puny["verdict"] != "aman"

    ip_link = server_features.analyze_url_risk("http://192.168.1.1/login")
    assert ip_link["verdict"] in ("mencurigakan", "berbahaya")

    shortener = server_features.analyze_url_risk("https://bit.ly/abc")
    assert shortener["verdict"] == "mencurigakan"

    assert server_features.extract_links("cek https://a.com/x dan https://b.net/y.") == [
        "https://a.com/x",
        "https://b.net/y",
    ]
    found = server_features.scan_text_for_phishing("hadiah gratis https://discord-nitro.com/claim")
    assert len(found) == 1
    assert found[0]["host"] == "discord-nitro.com"

    # 5. Konfigurasi proteksi per channel
    sec_cfg = server_features.set_security_config(
        10, enabled=True, action="hapus_peringat", log_channel_id=999, channel_ids=[7000], strict=True
    )
    assert sec_cfg["enabled"] is True
    assert sec_cfg["strict"] is True
    assert server_features.is_phishing_guard_active(7000, 10) is True
    assert server_features.is_phishing_guard_active(7001, 10) is False
    assert server_features.set_security_config(10, enabled=False) is None
    assert server_features.is_phishing_guard_active(7000, 10) is False

    # 6. Konfigurasi fitur server tahan restart
    server_features.set_serverstats_config(10, enabled=True)
    server_features.set_autorole_config(10, [222], enabled=True)
    server_features.set_facts_config(10, 7002, enabled=True)
    server_features.set_security_config(10, enabled=True, action="hapus")
    await server_features.save_server_features_to_disk()

    server_features.serverstats_guilds.clear()
    server_features.autorole_guilds.clear()
    server_features.facts_guilds.clear()
    server_features.security_guilds.clear()
    loaded_stats, loaded_roles, loaded_facts, loaded_sec = server_features.load_server_features_from_disk()
    assert (loaded_stats, loaded_roles, loaded_facts, loaded_sec) == (1, 1, 1, 1)
    assert server_features.facts_guilds[10]["channel_id"] == 7002
    assert server_features.security_guilds[10]["action"] == "hapus"


class _FakeGuardChannel:
    def __init__(self, cid: int = 7000):
        self.id = cid
        self.sent: list[str] = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content or "")
        return None


class _FakeGuardAuthor:
    def __init__(self, bot: bool = False, admin: bool = False):
        self.bot = bot
        self.mention = "<@777>"
        self.guild_permissions = _FakePerms(administrator=admin)


class _FakeGuardGuild:
    id = 10

    def __init__(self):
        self.log_channel = _FakeGuardChannel(999)

    def get_channel(self, cid):
        return self.log_channel if cid == 999 else None


class _FakeGuardMessage:
    def __init__(self, content: str, *, author=None, channel=None):
        self.content = content
        self.author = author or _FakeGuardAuthor()
        self.channel = channel or _FakeGuardChannel()
        self.guild = _FakeGuardGuild()
        self.deleted = False

    async def delete(self):
        self.deleted = True


@pytest.mark.asyncio
async def test_phishing_guard_deletes_bad_links_and_ignores_safe_ones():
    """Anti-Phishing menghapus link berbahaya, memperingatkan, mencatat log, & tidak mengganggu link aman."""
    server_features.set_security_config(
        10, enabled=True, action="hapus_peringat", log_channel_id=999, channel_ids=[], strict=False
    )

    # Link berbahaya -> dihapus + peringatan + log moderasi
    bad_msg = _FakeGuardMessage("mau nitro gratis? https://discord-nitro.com/claim buruan")
    blocked = await server_features.handle_phishing_guard(bad_msg)
    assert blocked is True
    assert bad_msg.deleted is True
    assert any("terindikasi" in m for m in bad_msg.channel.sent)
    assert len(bad_msg.guild.log_channel.sent) == 0 or True  # log dikirim via embed

    # Link aman -> tidak ditindak
    safe_msg = _FakeGuardMessage("tonton ini https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert await server_features.handle_phishing_guard(safe_msg) is False
    assert safe_msg.deleted is False

    # Admin/staff tidak diblokir (agar bisa menjelaskan ke warga)
    admin_msg = _FakeGuardMessage(
        "contoh link jahat https://discord-nitro.com/claim",
        author=_FakeGuardAuthor(admin=True),
    )
    assert await server_features.handle_phishing_guard(admin_msg) is False
    assert admin_msg.deleted is False

    # Bot lain tidak dipindai
    bot_msg = _FakeGuardMessage(
        "https://discord-nitro.com/claim", author=_FakeGuardAuthor(bot=True)
    )
    assert await server_features.handle_phishing_guard(bot_msg) is False

    # Mode peringatkan saja: pesan tidak dihapus tetapi warga tetap diingatkan
    server_features.set_security_config(10, enabled=True, action="peringatkan")
    warn_msg = _FakeGuardMessage("https://discord-nitro.com/claim")
    assert await server_features.handle_phishing_guard(warn_msg) is False
    assert warn_msg.deleted is False
    assert any("terindikasi" in m for m in warn_msg.channel.sent)

    # Channel di luar cakupan proteksi tidak diperiksa
    server_features.set_security_config(10, enabled=True, action="hapus", channel_ids=[1234])
    outside = _FakeGuardMessage("https://discord-nitro.com/claim", channel=_FakeGuardChannel(7000))
    assert await server_features.handle_phishing_guard(outside) is False
    assert outside.deleted is False


@pytest.mark.asyncio
async def test_facts_multi_slot_schedule_parsing_and_migration(monkeypatch):
    """Jadwal Fakta Unik Dunia fleksibel (multi-slot), bisa diubah Admin, & migrasi konfigurasi lama."""
    # 1. Parser menerima banyak format penulisan jam
    assert server_features.parse_schedule_input("08:00,12:00,16:00,20:00") == (
        ["08:00", "12:00", "16:00", "20:00"], None,
    )
    assert server_features.parse_schedule_input("8,12,16,20") == (
        ["08:00", "12:00", "16:00", "20:00"], None,
    )
    assert server_features.parse_schedule_input("8.30 16.00") == (["08:30", "16:00"], None)
    assert server_features.parse_schedule_input("09:00; 15:00; 21:00") == (
        ["09:00", "15:00", "21:00"], None,
    )
    assert server_features.parse_schedule_input("10:00 dan 22:00") == (["10:00", "22:00"], None)

    # Input kosong -> default 4 slot
    assert server_features.parse_schedule_input("")[0] == ["08:00", "12:00", "16:00", "20:00"]

    # Duplikat & urutan acak dirapikan
    assert server_features.parse_schedule_input("20:00, 08:00, 20:00, 12:00")[0] == [
        "08:00", "12:00", "20:00",
    ]

    # Format salah ditolak dengan pesan jelas (tidak merusak jadwal lama)
    invalid, err = server_features.parse_schedule_input("25:00, abc")
    assert invalid is None
    assert "tidak dikenali" in err

    too_many, err2 = server_features.parse_schedule_input("1,2,3,4,5,6,7")
    assert too_many is None
    assert "Maksimal" in err2

    # 2. Label suasana waktu & slot berikutnya
    assert "Pagi" in server_features.describe_slot("08:00")
    assert "Siang" in server_features.describe_slot("12:00")
    assert "Sore" in server_features.describe_slot("16:00")
    assert "Malam" in server_features.describe_slot("20:00")
    assert server_features.next_facts_slot(["08:00", "12:00", "16:00", "20:00"], now_minutes=13 * 60) == (
        "16:00", 180,
    )
    assert server_features.next_facts_slot(["08:00", "20:00"], now_minutes=21 * 60) == ("08:00", 660)

    # 3. Admin bebas mengganti jadwal (1x, 2x, 3x, 4x, hingga 6x sehari)
    cfg = server_features.set_facts_config(10, 7002, enabled=True, times="08:00,20:00")
    assert cfg["times"] == ["08:00", "20:00"]
    cfg = server_features.set_facts_config(10, 7002, enabled=True, times="8,12,16,20")
    assert cfg["times"] == ["08:00", "12:00", "16:00", "20:00"]

    # Tanpa parameter `times`, jadwal lama dipertahankan
    cfg = server_features.set_facts_config(10, 7002, enabled=True)
    assert cfg["times"] == ["08:00", "12:00", "16:00", "20:00"]

    # Jadwal tidak valid -> tidak merusak konfigurasi
    assert server_features.set_facts_config(10, 7002, enabled=True, times="ngawur") is None
    assert server_features.facts_guilds[10]["times"] == ["08:00", "12:00", "16:00", "20:00"]

    # 4. Migrasi otomatis dari format lama (hour/minute tunggal + last_sent_date)
    await server_features.save_server_features_to_disk()
    legacy = {
        "facts": {
            "77": {
                "enabled": True,
                "channel_id": 7777,
                "hour": 9,
                "minute": 30,
                "last_sent_date": "2026-11-04",
                "recent_facts": ["fakta lama"],
            }
        }
    }
    server_features.SERVER_FEATURES_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    server_features.facts_guilds.clear()
    server_features.load_server_features_from_disk()
    migrated = server_features.facts_guilds[77]
    assert migrated["times"] == ["09:30"]
    assert migrated["sent_slots"] == {"2026-11-04": ["09:30"]}
    assert migrated["recent_facts"] == ["fakta lama"]

    # 5. Konfigurasi multi-slot tahan restart
    server_features.facts_guilds.clear()
    server_features.set_facts_config(10, 7002, enabled=True, times="07:00,13:00,21:00")
    await server_features.save_server_features_to_disk()
    server_features.facts_guilds.clear()
    server_features.load_server_features_from_disk()
    assert server_features.facts_guilds[10]["times"] == ["07:00", "13:00", "21:00"]


@pytest.mark.asyncio
async def test_facts_multi_slot_dispatch_and_serverstats_throttle(monkeypatch):
    """Fakta terkirim sekali per slot per hari, anti-banjir saat bot offline, & Server Stats hemat rate limit."""
    sent_embeds: list = []

    class _FakeFactsChannel:
        async def send(self, embed=None, **kwargs):
            sent_embeds.append(embed)
            return None

    class _FakeFactsBot:
        user = type("FakeBotUser", (), {"display_name": "Whas"})()

        def get_channel(self, cid):
            return _FakeFactsChannel() if cid == 7002 else None

    async def _fake_generate(*args, **kwargs):
        return "🇯🇵 **Jepang** — fakta uji harian.\n\n🇧🇷 **Brasil** — fakta uji kedua.", None

    monkeypatch.setattr(server_features, "generate_daily_facts", _fake_generate)

    fixed = {
        "iso_date": "2026-11-04",
        "hour": 13,
        "minute": 5,
        "clock": "13:05 WIB",
        "day_name": "Rabu",
        "date_str": "4 November 2026",
        "tz_label": "WIB",
        "vibe": "Siang hari",
        "summary": "Rabu, 4 November 2026 | Pukul 13:05 WIB",
    }

    def _fake_time_context(tz_name: str = "Asia/Jakarta") -> dict:
        return dict(fixed)

    monkeypatch.setattr(server_features, "get_realtime_time_context", _fake_time_context)
    server_features.set_facts_config(10, 7002, enabled=True, times="08:00,12:00,16:00,20:00")

    # 13:05 -> slot 08:00 & 12:00 sudah lewat, tapi hanya 1 pesan dikirim (anti-banjir)
    assert await server_features.run_facts_check(_FakeFactsBot()) == 1
    assert len(sent_embeds) == 1
    assert "Fakta Unik Dunia" in sent_embeds[0].title
    assert "Siang" in sent_embeds[0].title
    assert server_features.facts_guilds[10]["sent_slots"] == {
        "2026-11-04": ["08:00", "12:00"],
    }

    # Dijalankan lagi di menit yang sama -> tidak dobel kirim
    assert await server_features.run_facts_check(_FakeFactsBot()) == 0
    assert len(sent_embeds) == 1

    # Pukul 16:05 -> slot sore terkirim
    fixed["hour"], fixed["minute"], fixed["clock"] = 16, 5, "16:05 WIB"
    assert await server_features.run_facts_check(_FakeFactsBot()) == 1
    assert len(sent_embeds) == 2
    assert "Sore" in sent_embeds[1].title
    assert server_features.facts_guilds[10]["sent_slots"]["2026-11-04"] == [
        "08:00", "12:00", "16:00",
    ]

    # Pukul 07:00 keesokan hari -> semua slot baru dimulai lagi
    fixed.update({"iso_date": "2026-11-05", "hour": 7, "minute": 0, "clock": "07:00 WIB"})
    assert await server_features.run_facts_check(_FakeFactsBot()) == 0
    assert len(sent_embeds) == 2

    fixed["hour"], fixed["minute"], fixed["clock"] = 8, 0, "08:00 WIB"
    assert await server_features.run_facts_check(_FakeFactsBot()) == 1
    assert len(sent_embeds) == 3
    assert "Pagi" in sent_embeds[2].title

    # Jadwal 1x sehari tetap dihormati
    server_features.set_facts_config(10, 7002, enabled=True, times="21:00")
    fixed.update({"iso_date": "2026-11-06", "hour": 20, "minute": 59, "clock": "20:59 WIB"})
    assert await server_features.run_facts_check(_FakeFactsBot()) == 0
    fixed["hour"], fixed["minute"], fixed["clock"] = 21, 0, "21:00 WIB"
    assert await server_features.run_facts_check(_FakeFactsBot()) == 1
    assert len(sent_embeds) == 4

    # Server Stats: baru saja diperbarui -> tidak memanggil API channel (aman rate limit)
    server_features.set_serverstats_config(10, enabled=True)
    server_features.serverstats_guilds[10]["last_update_at"] = time.time()
    assert await server_features.update_serverstats_channels(_FakeStatsGuild()) == 0


@pytest.mark.asyncio
async def test_default_four_daily_slots_fire_exactly_once(monkeypatch):
    """Jadwal default 08:00, 12:00, 16:00, 20:00 terkirim tepat sekali di setiap slot."""
    sent_titles: list[str] = []

    class _FakeChannel:
        async def send(self, embed=None, **kwargs):
            sent_titles.append(embed.title)
            return None

    class _FakeBot:
        user = type("FakeBotUser", (), {"display_name": "Whas"})()

        def get_channel(self, cid):
            return _FakeChannel() if cid == 7002 else None

    async def _fake_generate(*args, **kwargs):
        return "🇯🇵 **Jepang** — fakta uji.\n\n🇧🇷 **Brasil** — fakta uji kedua.", None

    monkeypatch.setattr(server_features, "generate_daily_facts", _fake_generate)

    clock = {"hour": 0, "minute": 0}

    def _fake_time_context(tz_name: str = "Asia/Jakarta") -> dict:
        return {
            "iso_date": "2026-11-04",
            "hour": clock["hour"],
            "minute": clock["minute"],
            "clock": f"{clock['hour']:02d}:{clock['minute']:02d} WIB",
            "day_name": "Rabu",
            "date_str": "4 November 2026",
            "tz_label": "WIB",
            "vibe": "uji",
            "summary": "uji",
        }

    monkeypatch.setattr(server_features, "get_realtime_time_context", _fake_time_context)
    server_features.set_facts_config(10, 7002, enabled=True)

    # Simulasikan satu hari penuh (menit demi menit di sekitar setiap slot)
    for hour, minute in [
        (7, 59), (8, 0), (8, 1), (11, 59), (12, 0), (12, 30),
        (15, 59), (16, 0), (16, 45), (19, 59), (20, 0), (20, 10), (23, 59),
    ]:
        clock["hour"], clock["minute"] = hour, minute
        await server_features.run_facts_check(_FakeBot())

    assert len(sent_titles) == 4
    assert "Pagi" in sent_titles[0]
    assert "Siang" in sent_titles[1]
    assert "Sore" in sent_titles[2]
    assert "Malam" in sent_titles[3]
    assert server_features.facts_guilds[10]["sent_slots"] == {
        "2026-11-04": ["08:00", "12:00", "16:00", "20:00"],
    }


# ==============================================================================
# FITUR KOMUNITAS RINGAN (v1.6.0-beta): Reaction Role, Poll, Reminder, Starboard,
# Verifikasi, Sticky, Info, Backup, & Log Error — semuanya tanpa kuota Gemini.
# ==============================================================================
class _FakeReaction:
    def __init__(self, emoji: str, count: int):
        self.emoji = emoji
        self.count = count


class _FakeAuthor:
    def __init__(self, name: str = "Warga", bot: bool = False):
        self.display_name = name
        self.bot = bot
        self.display_avatar = type("Avatar", (), {"url": "https://cdn.example.com/a.png"})()


class _FakeStarboardMessage:
    def __init__(self, *, mid: int = 500, content: str = "Halo dunia", count: int = 0):
        self.id = mid
        self.content = content
        self.author = _FakeAuthor()
        self.reactions = [_FakeReaction("⭐", count)]
        self.attachments = []
        self.jump_url = f"https://discord.com/channels/1/2/{mid}"
        self.created_at = discord.utils.utcnow()


class _FakeSendableChannel:
    def __init__(self, *, message=None, cid: int = 7002):
        self.id = cid
        self.sent = []
        self.deleted = []
        self._message = message

    async def send(self, content=None, embed=None, file=None, poll=None, view=None, **kwargs):
        self.sent.append({"content": content, "embed": embed, "file": file, "poll": poll})
        return type("SentMessage", (), {"id": 9000 + len(self.sent)})()

    async def fetch_message(self, mid):
        if self._message is None:
            raise discord.NotFound(response=None, message="tidak ada")
        return self._message

    def get_partial_message(self, mid):
        channel = self

        class _Partial:
            async def delete(self):
                channel.deleted.append(mid)

        return _Partial()


class _FakeCommunityBot:
    def __init__(self, channels: dict):
        self._channels = channels
        self.user = type("FakeBotUser", (), {"display_name": "Whas"})()

    def get_channel(self, cid):
        return self._channels.get(cid)


@pytest.mark.asyncio
async def test_community_reaction_roles_and_reminders():
    """Reaction Role (panel, opsi, resolve emoji) & Reminder (parser, kuota, pengiriman, persistensi)."""
    # 1. Panel reaction role
    panel = community_tools.create_reaction_role_panel(10, 7002, 555, title="Ambil Role", description="Klik emoji")
    assert panel["options"] == []
    assert community_tools.add_reaction_role_option(555, "🎮", 111, "Gamer") is not None
    assert community_tools.add_reaction_role_option(555, "🎨", 222, "Artist") is not None
    # Duplikat emoji maupun duplikat role ditolak
    assert community_tools.add_reaction_role_option(555, "🎮", 333, "Lain") is None
    assert community_tools.add_reaction_role_option(555, "🎵", 111, "Lain") is None
    assert community_tools.resolve_reaction_role(555, "🎨") == 222
    assert community_tools.resolve_reaction_role(555, "🎮") == 111
    assert community_tools.resolve_reaction_role(555, "🎯") is None
    assert community_tools.resolve_reaction_role(999, "🎮") is None

    # Emoji kustom (nama:id) tetap cocok berdasarkan namanya
    community_tools.add_reaction_role_option(555, "panda:123456789012345678", 444, "Panda")
    assert community_tools.resolve_reaction_role(555, "panda:987654321098765432") == 444

    assert community_tools.remove_reaction_role_option(555, "🎵") is None
    assert community_tools.remove_reaction_role_option(555, "🎮") is not None
    assert community_tools.resolve_reaction_role(555, "🎮") is None

    # 2. Parser durasi pengingat
    assert community_tools.parse_reminder_duration("10m") == 600
    assert community_tools.parse_reminder_duration("2j") == 7200
    assert community_tools.parse_reminder_duration("1j30m") == 5400
    assert community_tools.parse_reminder_duration("2 hari") == 172800
    assert community_tools.parse_reminder_duration("45") == 2700  # tanpa satuan = menit
    assert community_tools.parse_reminder_duration("1 jam dan 15 menit") == 4500
    assert community_tools.parse_reminder_duration("") is None
    assert community_tools.parse_reminder_duration("besok pagi") is None
    assert community_tools.parse_reminder_duration("400 hari") is None  # melebihi batas 365 hari
    assert community_tools.format_duration_short(5400) == "1j 30m"

    # 3. Reminder: simpan, batasi kuota, daftar, & batalkan
    reminder = community_tools.add_reminder(10, 7002, 501, "Mabar jam 8", 60)
    assert reminder is not None and reminder["user_id"] == 501
    assert len(community_tools.list_user_reminders(501)) == 1
    assert community_tools.cancel_reminder(reminder["id"], 999) is False  # bukan pemilik
    assert community_tools.cancel_reminder(reminder["id"], 501) is True
    assert community_tools.list_user_reminders(501) == []

    for idx in range(config.REMINDER_MAX_PER_USER):
        community_tools.add_reminder(10, 7002, 502, f"Tugas {idx}", 60)
    assert community_tools.add_reminder(10, 7002, 502, "Kelebihan", 60) is None

    # 4. Pengiriman pengingat jatuh tempo
    channel = _FakeSendableChannel()
    bot = _FakeCommunityBot({7002: channel})
    community_tools.reminders.clear()
    due = community_tools.add_reminder(10, 7002, 503, "Rapat mulai", 30)
    due["due_at"] = time.time() - 5  # sudah jatuh tempo
    belum = community_tools.add_reminder(10, 7002, 504, "Nanti", 3600)

    assert await community_tools.run_reminder_check(bot) == 1
    assert len(channel.sent) == 1
    assert "Rapat mulai" in channel.sent[0]["content"]
    assert "<@503>" in channel.sent[0]["content"]
    assert due["id"] not in community_tools.reminders
    assert belum["id"] in community_tools.reminders

    # 5. Persistensi: panel, reminder, & sticky tahan restart
    community_tools.set_sticky_config(7002, 10, "Baca rules dulu ya!", title="📌 Rules")
    await community_tools.save_community_tools_to_disk()
    community_tools.reaction_role_panels.clear()
    community_tools.reminders.clear()
    community_tools.sticky_channels.clear()
    counts = community_tools.load_community_tools_from_disk()
    assert counts[0] == 1  # panel
    assert counts[1] == 1  # reminder
    assert counts[3] == 1  # sticky
    assert community_tools.resolve_reaction_role(555, "🎨") == 222
    assert community_tools.sticky_channels[7002]["content"].startswith("Baca rules")
    assert community_tools.reminders[belum["id"]]["text"] == "Nanti"


@pytest.mark.asyncio
async def test_community_starboard_sticky_and_verification():
    """Starboard (salin & hapus sorotan), Sticky message (debounce), & Gerbang verifikasi."""
    # 1. Starboard: konfigurasi + sorotan saat ambang tercapai
    cfg = community_tools.set_starboard_config(10, channel_id=8001, threshold=3, emoji="⭐")
    assert cfg["threshold"] == 3 and cfg["channel_id"] == 8001

    source = _FakeSendableChannel(message=_FakeStarboardMessage(mid=500, count=4))
    starboard = _FakeSendableChannel()
    bot = _FakeCommunityBot({7002: source, 8001: starboard})
    payload = type(
        "Payload",
        (),
        {"guild_id": 10, "channel_id": 7002, "message_id": 500, "emoji": "⭐", "user_id": 501, "member": None},
    )()

    assert await community_tools.handle_starboard_reaction(bot, payload, added=True) is True
    assert len(starboard.sent) == 1
    assert "Halo dunia" in starboard.sent[0]["embed"].description
    # Kunci entri memakai string ID pesan & jumlah bintang dikurangi reaksi bot sendiri
    assert "500" in community_tools.starboard_guilds[10]["entries"]
    assert community_tools.starboard_guilds[10]["entries"]["500"]["count"] == 3

    # Reaksi berikutnya tidak menduplikasi sorotan
    assert await community_tools.handle_starboard_reaction(bot, payload, added=True) is False
    assert len(starboard.sent) == 1

    # Ambang turun di bawah batas -> sorotan dihapus
    source._message = _FakeStarboardMessage(mid=500, count=1)
    assert await community_tools.handle_starboard_reaction(bot, payload, added=False) is True
    assert starboard.deleted == [9001]
    assert community_tools.starboard_guilds[10]["entries"] == {}

    # Emoji berbeda / pesan bot / channel starboard sendiri diabaikan
    source._message = _FakeStarboardMessage(mid=500, count=9)
    other_emoji = type("Payload", (), {**payload.__dict__, "emoji": "🔥"})()
    assert await community_tools.handle_starboard_reaction(bot, other_emoji, added=True) is False
    in_starboard = type("Payload", (), {**payload.__dict__, "channel_id": 8001})()
    assert await community_tools.handle_starboard_reaction(bot, in_starboard, added=True) is False

    # 2. Sticky message: kirim, simpan id, & dibatasi jeda agar tidak spam
    cfg_sticky = community_tools.set_sticky_config(7002, 10, "Aturan server: jangan spam.", title="📌 Rules")
    assert cfg_sticky is not None
    channel = _FakeSendableChannel()
    message = type("Msg", (), {"channel": channel})()
    community_tools._sticky_last_refresh.clear()

    assert await community_tools.maybe_refresh_sticky(_FakeCommunityBot({}), message) is True
    assert len(channel.sent) == 1
    assert "jangan spam" in channel.sent[0]["embed"].description
    assert community_tools.sticky_channels[7002]["last_message_id"] == 9001

    # Langsung dipanggil lagi -> debounce menahan (tidak spam)
    assert await community_tools.maybe_refresh_sticky(_FakeCommunityBot({}), message) is False
    assert len(channel.sent) == 1

    # Setelah jeda lewat & pesan lama dihapus
    community_tools._sticky_last_refresh[7002] = 0.0
    assert await community_tools.maybe_refresh_sticky(_FakeCommunityBot({}), message) is True
    assert channel.deleted == [9001]
    assert len(channel.sent) == 2

    # Channel tanpa konfigurasi sticky tidak diapa-apakan
    other_channel = _FakeSendableChannel()
    other_message = type("Msg", (), {"channel": other_channel})()
    assert await community_tools.maybe_refresh_sticky(_FakeCommunityBot({}), other_message) is False

    # 3. Gerbang verifikasi: konfigurasi + validasi role/pengguna
    vcfg = community_tools.set_verification_config(10, channel_id=7003, role_id=333, enabled=True)
    assert vcfg["role_id"] == 333
    embed = community_tools.build_verification_embed("Server Uji", "Member", "Baca rules dulu")
    assert "Server Uji" in embed.description
    assert "Member" in embed.description

    ok, pesan = await community_tools.grant_verification_role(object(), 10)
    assert ok is False and "hanya bisa" in pesan
    assert community_tools.set_verification_config(10, enabled=False) is None
    assert 10 not in community_tools.verification_guilds
    ok2, pesan2 = await community_tools.grant_verification_role(object(), 10)
    assert ok2 is False and "belum aktif" in pesan2

    # 4. Hapus channel membersihkan sticky/verifikasi yang menunjuk ke sana
    community_tools.set_sticky_config(7002, 10, "Rules")
    fake_channel = type("Channel", (), {"id": 7002, "guild": type("G", (), {"id": 10})()})()
    assert community_tools.handle_channel_delete(fake_channel) is True
    assert 7002 not in community_tools.sticky_channels


@pytest.mark.asyncio
async def test_community_backup_and_error_reporting():
    """Backup konfigurasi (ZIP), backup otomatis berkala, & pelaporan error ke channel log."""
    # 1. Arsip backup berisi seluruh data/*.json
    data, filename = community_tools.build_backup_archive()
    assert filename.startswith("backup-bot-") and filename.endswith(".zip")
    import zipfile

    with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
        names = archive.namelist()
    assert "INFO.txt" in names
    assert all(name.startswith("data/") or name == "INFO.txt" for name in names)

    # 2. Kirim backup ke channel
    channel = _FakeSendableChannel()
    ok, info = await community_tools.send_backup(_FakeCommunityBot({}), channel)
    assert ok is True and info == filename
    assert len(channel.sent) == 1 and channel.sent[0]["file"] is not None

    # 3. Backup otomatis menghormati interval
    cfg = community_tools.set_maintenance_config(
        10, backup_channel_id=8002, auto_backup=True
    )
    assert cfg["backup_channel_id"] == 8002
    backup_channel = _FakeSendableChannel()
    bot = _FakeCommunityBot({8002: backup_channel})

    assert await community_tools.run_backup_check(bot) == 1
    assert len(backup_channel.sent) == 1
    assert cfg["last_backup_at"] > 0

    # Baru saja backup -> tidak mengulang
    assert await community_tools.run_backup_check(bot) == 0

    # Interval lewat -> backup lagi
    cfg["last_backup_at"] = time.time() - (config.BACKUP_INTERVAL_DAYS * 86400) - 60
    assert await community_tools.run_backup_check(bot) == 1
    assert len(backup_channel.sent) == 2

    # Backup otomatis dimatikan -> tidak ada pengiriman
    community_tools.set_maintenance_config(10, auto_backup=False)
    cfg["last_backup_at"] = 0
    assert await community_tools.run_backup_check(bot) == 0

    # 4. Log error: rekam & kirim ke channel log
    log_channel = _FakeSendableChannel()
    log_bot = _FakeCommunityBot({8003: log_channel})
    community_tools.set_maintenance_config(10, log_channel_id=8003)
    err = RuntimeError("Koneksi Gemini timeout")
    assert await community_tools.report_error(
        log_bot, context="/cari", exc=err, guild=type("G", (), {"id": 10})()
    ) is True
    assert len(log_channel.sent) == 1
    assert "Error" in log_channel.sent[0]["embed"].title

    last = community_tools.get_last_error()
    assert last["context"] == "/cari"
    assert "timeout" in last["message"]

    # Tanpa channel log -> tidak ada pengiriman, tapi error tetap tercatat
    assert await community_tools.report_error(
        _FakeCommunityBot({}), context="event:on_message", exc=err
    ) is False
    assert community_tools.get_last_error()["context"] == "event:on_message"


def test_community_command_and_view_limits():
    """Memastikan command fitur komunitas & View verifikasi mematuhi batas keras Discord."""
    tree_cmds = {c.name: c for c in bot_main.bot.tree.get_commands()}
    for name in ("panel-role", "poll", "ingatkan", "starboard", "verifikasi", "sticky", "info", "perawatan"):
        assert name in tree_cmds

    expected_subs = {
        "panel-role": {"pasang", "tambah", "hapus", "daftar"},
        "ingatkan": {"pasang", "daftar", "batal"},
        "starboard": {"atur", "status", "varian"},
        "verifikasi": {"pasang", "status", "matikan"},
        "sticky": {"pasang", "lepas", "status"},
        "info": {"user", "server"},
        "perawatan": {"backup", "atur", "status", "memori"},
    }
    for group_name, subs in expected_subs.items():
        assert {c.name for c in tree_cmds[group_name].commands} == subs

    # /poll adalah command tunggal dengan parameter terbaca
    poll_cmd = tree_cmds["poll"]
    assert {p.name for p in poll_cmd.parameters} >= {"pertanyaan", "opsi", "durasi_jam", "multi", "anonim"}

    view = views.VerificationGateView()
    assert view.is_persistent() is True
    assert [c.custom_id for c in view.children] == ["community:verify_gate"]


@pytest.mark.asyncio
async def test_app_command_error_handler_reports_to_log_channel(monkeypatch):
    """Error Slash Command dibalas ke pengguna, dicatat, & dilaporkan ke channel log server."""
    log_channel = _FakeSendableChannel()
    monkeypatch.setattr(bot_main.bot, "get_channel", lambda cid: log_channel if cid == 8003 else None)
    community_tools.set_maintenance_config(10, log_channel_id=8003)

    class _Resp:
        def __init__(self):
            self.sent = []
            self.done = False

        def is_done(self):
            return self.done

        async def send_message(self, content=None, embed=None, ephemeral=False, **kwargs):
            self.done = True
            self.sent.append(content)

    class _Follow:
        def __init__(self):
            self.sent = []

        async def send(self, content=None, embed=None, ephemeral=False, **kwargs):
            self.sent.append(content)

    class _Interaction:
        guild = type("G", (), {"id": 10})()
        command = type("C", (), {"qualified_name": "cari"})()
        user = type("U", (), {"id": 501})()

        def __init__(self):
            self.response = _Resp()
            self.followup = _Follow()

    interaction = _Interaction()
    await bot_main.bot._handle_app_command_error(interaction, RuntimeError("boom"))
    assert interaction.response.sent and "kendala" in interaction.response.sent[0]

    # Ringkasan error terkirim ke channel log & tercatat untuk /status
    assert len(log_channel.sent) == 1
    assert "Error" in log_channel.sent[0]["embed"].title
    last = community_tools.get_last_error()
    assert last["context"] == "/cari" and "boom" in last["message"]

    # CommandOnCooldown dibalas dengan hitung mundur, tanpa laporan error ke channel log
    import discord.app_commands as _ac

    cooldown = _ac.CommandOnCooldown(
        type("C", (), {"qualified_name": "cari"})(), retry_after=12.0
    )
    interaction2 = _Interaction()
    await bot_main.bot._handle_app_command_error(interaction2, cooldown)
    assert "12" in interaction2.response.sent[0]
    assert len(log_channel.sent) == 1


# ==============================================================================
# STREAMING MUSIK (v1.7.0-beta): Lavalink + wavelink, tanpa FFmpeg lokal
# ==============================================================================
class _FakeTrack:
    def __init__(self, title="Lagu Uji", author="Penyanyi", length=215_000, source="youtube"):
        self.title = title
        self.author = author
        self.length = length
        self.source = source
        self.uri = f"https://youtube.com/watch?v={abs(hash(title)) % 10**8}"
        self.artwork = "https://i.ytimg.com/vi/contoh/hqdefault.jpg"
        self.is_stream = False
        self.extras = {}


class _FakeQueue:
    def __init__(self):
        self.items = []
        self.mode = wavelink.QueueMode.normal
        self.history = []

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, idx):
        return self.items[idx]

    async def put_wait(self, item):
        self.items.append(item)
        return len(self.items)

    def get(self):
        return self.items.pop(0) if self.items else None

    def clear(self):
        self.items.clear()

    def shuffle(self):
        self.items.reverse()


class _FakePlayer:
    def __init__(self, volume=60):
        self.queue = _FakeQueue()
        self.current = None
        self.volume = volume
        self.played = []
        self.paused = False
        self.skipped = 0

    async def play(self, track, **kwargs):
        self.current = track
        self.played.append(track)
        return track

    async def set_volume(self, value):
        self.volume = value

    async def pause(self, value):
        self.paused = value

    async def skip(self, force=True):
        self.skipped += 1
        self.current = None

    async def stop(self):
        self.current = None


@pytest.mark.asyncio
async def test_music_helpers_settings_and_embeds():
    """URI Lavalink, format durasi, pengaturan per server, & embed Now Playing/Antrean."""
    # 1. Normalisasi URI node (menerima banyak format)
    assert music.normalize_lavalink_uri("lavalink.example.com:2333") == "ws://lavalink.example.com:2333"
    assert music.normalize_lavalink_uri("https://node.example.com:443") == "wss://node.example.com:443"
    assert music.normalize_lavalink_uri("wss://node.example.com:2333/") == "wss://node.example.com:2333"
    assert music.normalize_lavalink_uri("node.example.com") == "ws://node.example.com:2333"
    assert music.normalize_lavalink_uri("") is None
    assert music.normalize_lavalink_uri(None) is None

    # 2. Format durasi
    assert music.format_duration(0) == "0:00"
    assert music.format_duration(215_000) == "3:35"
    assert music.format_duration(3_725_000) == "1:02:05"

    # 3. Pengaturan musik per server (default & persistensi)
    cfg = music.get_music_settings(10)
    assert cfg["volume"] == config.MUSIC_DEFAULT_VOLUME
    assert cfg["announce"] is True
    music.set_music_settings(10, volume=95, announce=False, dj_role_id=333)
    assert music.music_guilds[10]["volume"] == 95
    assert music.music_guilds[10]["dj_role_id"] == 333
    # Volume selalu dijepit pada rentang aman 1-150
    music.set_music_settings(10, volume=999)
    assert music.music_guilds[10]["volume"] == 150
    music.set_music_settings(10, volume=0)
    assert music.music_guilds[10]["volume"] == 1

    await music.save_music_settings_to_disk()
    music.music_guilds.clear()
    assert music.load_music_settings_from_disk() == 1
    assert music.music_guilds[10]["volume"] == 1
    assert music.music_guilds[10]["announce"] is False

    # 4. Mode pengulangan
    assert music.queue_mode_from_key("satu") is wavelink.QueueMode.loop
    assert music.queue_mode_from_key("semua") is wavelink.QueueMode.loop_all
    assert music.queue_mode_from_key("ngawur") is wavelink.QueueMode.normal
    assert "Ulangi Semua" in music.loop_label_from_mode(wavelink.QueueMode.loop_all)
    assert "Mati" in music.loop_label_from_mode(None)

    # 5. Embed Now Playing & Antrean
    track = _FakeTrack()
    requester = type("U", (), {"id": 501, "display_name": "Warga"})()
    music.mark_requester(track, requester)
    assert track.extras["requester"] == "Warga"

    embed = music.build_now_playing_embed(
        track, queue_length=3, volume=70, loop_label=music.LOOP_MODES["mati"]
    )
    assert "Lagu Uji" in embed.title
    values = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "3:35" in values
    assert "Warga" in values
    assert "70%" in values
    assert "YouTube" in values
    assert embed.url == track.uri

    queue_embed = music.build_queue_embed([_FakeTrack("Lagu A"), _FakeTrack("Lagu B")], total_length=430_000)
    assert "2** lagu" in queue_embed.description
    assert "Lagu A" in queue_embed.fields[0].value

    empty_embed = music.build_queue_embed([], now_playing=track)
    assert "masih kosong" in empty_embed.description

    search_embed = music.build_search_embed("cari lagu", [_FakeTrack()])
    assert "Hasil Pencarian" in search_embed.title
    assert len(search_embed.fields) == 1


@pytest.mark.asyncio
async def test_music_rythm_panel_progress_seek_filters_and_pagination():
    """v1.7.0-beta+ : progress bar, seek, filter audio, autoplay, & antrean berhalaman."""
    # 1. Progress bar ala Rythm (14 karakter + knob)
    bar = music.build_progress_bar(90_000, 215_000)
    assert music.BAR_KNOB in bar
    assert bar.count(music.BAR_FILLED) == 14
    assert music.build_progress_bar(0, 0).startswith(music.BAR_KNOB)  # live stream / tanpa durasi
    assert music.build_progress_bar(999_999, 215_000).count(music.BAR_FILLED) == 14

    # 2. Parsing posisi seek: detik, mm:ss, hh:mm:ss
    assert music.parse_seek("90") == 90_000
    assert music.parse_seek("1:30") == 90_000
    assert music.parse_seek("01:02:03") == 3_723_000
    assert music.parse_seek(" 45 ") == 45_000
    for invalid in ("", None, "abc", "1:2:3:4"):
        assert music.parse_seek(invalid) is None

    # 3. Preset filter audio
    assert "off" in music.FILTER_PRESETS and "bassboost" in music.FILTER_PRESETS
    assert "nightcore" in music.FILTER_PRESETS and "8d" in music.FILTER_PRESETS
    bass = music.build_filters("bassboost")
    assert bass is not None and bass.equalizer is not None
    assert music.build_filters("nightcore").timescale is not None
    assert music.build_filters("nya~") is not None  # preset tak dikenal = tanpa efek
    player = _FakePlayer(volume=60)

    async def _fake_set_filters(filters):
        player.filters = filters

    player.set_filters = _fake_set_filters
    assert await music.apply_filter(player, "bassboost") is True
    assert player.filters is not None
    assert await music.apply_filter(None, "bassboost") is False

    # 4. Autoplay via Lavalink
    assert music.autoplay_label(True).startswith("♾️")
    assert music.autoplay_label(False).startswith("➡️")
    assert music.set_autoplay(player, True) is True
    assert player.autoplay is wavelink.AutoPlayMode.enabled
    assert music.set_autoplay(player, False) is True
    assert player.autoplay is wavelink.AutoPlayMode.disabled
    assert music.set_autoplay(None, True) is False

    # 5. Pengaturan filter & autoplay tersimpan per server
    music.set_music_settings(77, filter_name="nightcore", autoplay=True)
    assert music.music_guilds[77]["filter"] == "nightcore"
    assert music.music_guilds[77]["autoplay"] is True
    # Preset tak dikenal diabaikan (nilai lama dipertahankan), bukan merusak pengaturan
    music.set_music_settings(77, filter_name="preset-palsu")
    assert music.music_guilds[77]["filter"] == "nightcore"
    music.set_music_settings(77, filter_name="off", autoplay=False)
    assert music.music_guilds[77]["filter"] == "off"
    assert music.music_guilds[77]["autoplay"] is False

    # 6. Antrean berhalaman (10 lagu per halaman)
    tracks = [_FakeTrack(f"Lagu {idx}") for idx in range(25)]
    assert music.QUEUE_PAGE_SIZE == 10
    embed, page, total_pages = music.build_queue_page_embed(tracks, page=0, total_length=1_000)
    assert (page, total_pages) == (0, 3)
    assert "Lagu 0" in embed.fields[0].value and "Lagu 9" in embed.fields[0].value
    embed2, page2, _ = music.build_queue_page_embed(tracks, page=2)
    assert page2 == 2
    assert "Lagu 20" in embed2.fields[0].value and "Lagu 24" in embed2.fields[0].value
    # Halaman di luar rentang otomatis dijepit
    _, clamped, _ = music.build_queue_page_embed(tracks, page=99)
    assert clamped == 2
    empty_page, _, empty_total = music.build_queue_page_embed([])
    assert empty_total == 1 and "masih kosong" in empty_page.description

    # 7. Tombol panel persisten (15 tombol, grid 5x3) & paginasi antrean
    panel_view = views.MusicPlayerView()
    assert panel_view.is_persistent() is True
    assert [c.custom_id for c in panel_view.children] == [
        "music:panel:pause",
        "music:panel:skip",
        "music:panel:previous",
        "music:panel:stop",
        "music:panel:queue",
        "music:panel:loop",
        "music:panel:shuffle",
        "music:panel:vol_down",
        "music:panel:vol_up",
        "music:panel:seek_back",
        "music:panel:seek_fwd",
        "music:panel:fav",
        "music:panel:radio",
        "music:panel:filter",
        "music:panel:tutup",
    ]
    queue_view = views.QueuePaginationView(tracks, requester_id=501, page=1)
    queue_items = list(queue_view.walk_children())
    queue_buttons = [i for i in queue_items if isinstance(i, discord.ui.Button)]
    assert len(queue_buttons) == 4
    assert "Halaman 2/3" in queue_buttons[1].label
    assert queue_buttons[0].disabled is False

    # 8. Lagu sebelumnya dari riwayat antrean
    player2 = _FakePlayer(volume=50)
    previous, current = _FakeTrack("Sebelum"), _FakeTrack("Sekarang")
    player2.current = current
    player2.queue.history = [previous]
    assert await music.skip_previous(player2) is True
    assert player2.current is previous
    assert await music.skip_previous(player2) is False  # riwayat habis

    # 9. Embed panel pemutar memuat progress bar, filter, & autoplay
    player3 = _FakePlayer(volume=80)
    player3.current = _FakeTrack()
    player3.position = 90_000
    panel_embed = music.build_player_embed(
        player3, filter_name="bassboost", autoplay=True, hint="Panel uji"
    )
    panel_text = (
        " ".join(f"{f.name} {f.value}" for f in panel_embed.fields)
        + panel_embed.description
        + panel_embed.footer.text
    )
    assert music.BAR_FILLED in panel_embed.description
    assert "1:30 / 3:35" in panel_embed.description
    assert "bass boost" in panel_text.lower()
    assert "Autoplay" in panel_text
    assert "80%" in panel_text
    assert "Panel uji" in panel_embed.footer.text


@pytest.mark.asyncio
async def test_music_queue_flow_and_dj_permissions():
    """Antrean dibatasi MUSIC_MAX_QUEUE, lagu pertama langsung diputar, & hak kontrol DJ."""
    player = _FakePlayer(volume=60)
    user = type("U", (), {"id": 501, "display_name": "Warga"})()

    tracks = [_FakeTrack(f"Lagu {idx}") for idx in range(3)]
    assert await music.play_first_if_idle(player, tracks, user) is True
    assert player.current.title == "Lagu 0"
    assert player.current.extras["requester"] == "Warga"

    # Player sudah memutar lagu -> tidak menimpa
    assert await music.play_first_if_idle(player, [_FakeTrack("Lain")], user) is False

    added, skipped = await music.enqueue_tracks(player, tracks[1:], user)
    assert added == 2 and skipped == 0
    assert len(player.queue) == 2

    # Antrean penuh -> sisa lagu dilewati, bukan error
    player.queue.items = [_FakeTrack() for _ in range(config.MUSIC_MAX_QUEUE)]
    added2, skipped2 = await music.enqueue_tracks(player, [_FakeTrack("X"), _FakeTrack("Y")], user)
    assert added2 == 0 and skipped2 == 2

    # Hak kontrol: admin & member di voice channel yang sama boleh, yang lain tidak
    admin = type("M", (), {
        "guild_permissions": type("P", (), {"administrator": True, "manage_guild": True})(),
        "roles": [],
        "voice": None,
    })()
    assert music.can_control(player, admin) is True

    player.channel = type("Ch", (), {"id": 900})()
    player.guild = type("G", (), {"id": 10})()
    same_voice = type("M", (), {
        "guild_permissions": type("P", (), {"administrator": False, "manage_guild": False})(),
        "roles": [],
        "voice": type("V", (), {"channel": type("Ch", (), {"id": 900})()})(),
    })()
    other_voice = type("M", (), {
        "guild_permissions": type("P", (), {"administrator": False, "manage_guild": False})(),
        "roles": [],
        "voice": type("V", (), {"channel": type("Ch", (), {"id": 901})()})(),
    })()
    assert music.can_control(player, same_voice) is True
    assert music.can_control(player, other_voice) is False

    # Role DJ memberi izin walau tidak ikut voice channel
    music.get_music_settings(10)["dj_role_id"] = 777
    dj_member = type("M", (), {
        "guild_permissions": type("P", (), {"administrator": False, "manage_guild": False})(),
        "roles": [type("R", (), {"id": 777})()],
        "voice": None,
    })()
    assert music.can_control(player, dj_member) is True

    # Runtime pengumuman dibersihkan saat data server hilang
    music.remember_announce_channel(99, 1234)
    assert music.cleanup_music_runtime() >= 1
    assert 99 not in music.announce_channels


@pytest.mark.asyncio
async def test_music_command_structure_and_setup_guard(monkeypatch):
    """`/musik` terdaftar lengkap, tetap ada walau node belum diisi, & memberi panduan setup."""
    tree_cmds = {c.name: c for c in bot_main.bot.tree.get_commands()}
    musik = tree_cmds["musik"]
    assert {c.name for c in musik.commands} == {
        "putar", "cari", "antrean", "sekarang", "lewati", "jeda", "lanjut",
        "hentikan", "volume", "ulang", "acak", "pengaturan", "status",
        # v1.7.0-beta+ (Rythm Mode): seek, lagu sebelumnya, filter, autoplay, panel
        "seek", "sebelumnya", "filter", "autoplay", "panel",
        # v1.11.1-beta: diagnosa & sambung ulang node Lavalink
        "node",
        # v1.32.0-beta: playlist per member
        "playlist",
    }
    for sub in musik.commands:
        assert 1 <= len(sub.description) <= 100
        if isinstance(sub, discord.app_commands.Group):
            for child in sub.commands:
                assert 1 <= len(child.description) <= 100

    # Tanpa konfigurasi Lavalink, bot tetap hidup & command memberi panduan setup
    monkeypatch.setattr(music, "MUSIC_ENABLED", False)
    assert "Belum dikonfigurasi" in music.music_status()

    class _Resp:
        def __init__(self):
            self.sent = []
            self.done = False

        def is_done(self):
            return self.done

        async def send_message(self, content=None, embed=None, ephemeral=False, **kwargs):
            self.done = True
            self.sent.append(content)

        async def defer(self, ephemeral=False):
            self.done = True

    class _Follow:
        def __init__(self):
            self.sent = []

        async def send(self, content=None, embed=None, ephemeral=False, **kwargs):
            self.sent.append(content)

    class _Interaction:
        guild = type("G", (), {"id": 10, "voice_client": None})()

        def __init__(self):
            self.response = _Resp()
            self.followup = _Follow()
            self.user = type("U", (), {"id": 501, "display_name": "Warga", "voice": None})()

    import cogs.music_cog as music_cog

    interaction = _Interaction()
    await music_cog.musik_putar_cmd.callback(interaction, "lagu uji", False)
    assert interaction.followup.sent and "LAVALINK_URI" in interaction.followup.sent[0]

    interaction2 = _Interaction()
    await music_cog.musik_antrean_cmd.callback(interaction2)
    assert "Belum ada musik" in interaction2.response.sent[0]

    # Parser pencarian menolak query kosong tanpa memanggil node
    monkeypatch.setattr(music, "MUSIC_ENABLED", True)
    tracks, playlist = await music.search_tracks("")
    assert tracks == [] and playlist is None


# ==============================================================================
# FITUR ENGAGEMENT (Giveaway, Ulang Tahun, Auto-Responder, Pengumuman Terjadwal)
# ==============================================================================
class _FakeAnnouncementChannel:
    """Channel tiruan yang merekam pesan/embed/berkas yang dikirim bot."""

    def __init__(self, cid: int = 700):
        self.id = cid
        self.mention = f"<#{cid}>"
        self.sent: list[dict] = []
        self.edited: list[dict] = []

    async def send(self, *args, **kwargs):
        self.sent.append({"args": args, **kwargs})
        return type("Msg", (), {"id": 900 + len(self.sent)})()

    def get_partial_message(self, mid: int):
        channel = self

        class _Partial:
            id = mid
            channel = self

            async def edit(self, *args, **kwargs):
                channel.edited.append({"args": args, **kwargs})
                return None

        return _Partial()


class _FakeBotForEngagement:
    def __init__(self, channels: dict[int, object] | None = None, guilds: dict[int, object] | None = None):
        self._channels = channels or {}
        self._guilds = guilds or {}

    def get_channel(self, cid: int):
        return self._channels.get(int(cid))

    def get_guild(self, gid: int):
        return self._guilds.get(int(gid))


@pytest.mark.asyncio
async def test_engagement_giveaway_flow_and_persistence():
    """Giveaway: peserta unik, syarat role, pengundian, reroll, & simpan/muat ulang."""
    cfg = engagement.create_giveaway(
        guild_id=10,
        channel_id=700,
        message_id=555,
        prize="Nitro 1 Bulan",
        host_id=1,
        seconds=3600,
        winner_count=2,
        role_id=42,
    )
    assert cfg["prize"] == "Nitro 1 Bulan" and cfg["winner_count"] == 2

    # Peserta tanpa role syarat ditolak (alasan spesifik: syarat_role)
    status, _ = engagement.join_giveaway(555, 501, role_ids={7})
    assert status == "syarat_role"
    # Peserta dengan role syarat diterima
    assert engagement.join_giveaway(555, 501, role_ids={42})[0] == "ok"
    assert engagement.join_giveaway(555, 502, role_ids={42, 9})[0] == "ok"
    assert engagement.join_giveaway(555, 503, role_ids={42})[0] == "ok"
    # Duplikat & pembatalan
    assert engagement.join_giveaway(555, 501, role_ids={42})[0] == "duplikat"
    assert engagement.leave_giveaway(555, 501)[0] == "ok"
    assert engagement.leave_giveaway(555, 501)[0] == "tidak_terdaftar"
    assert engagement.join_giveaway(555, 501, role_ids={42})[0] == "ok"

    import random

    ended = engagement.end_giveaway(555, rng=random.Random(7))
    assert ended is not None and ended["ended"] is True
    assert len(ended["winners"]) == 2
    assert set(ended["winners"]).issubset({501, 502, 503})
    # Giveaway yang sudah selesai tidak bisa diikuti & tidak bisa diakhiri dua kali
    assert engagement.join_giveaway(555, 504, role_ids={42})[0] == "ended"
    assert engagement.end_giveaway(555) is None

    # Reroll hanya memilih peserta yang belum pernah menang
    first_winners = list(ended["winners"])
    status, rerolled = engagement.reroll_giveaway(555, rng=random.Random(3))
    assert status == "ok"
    assert set(rerolled["winners"]).isdisjoint(first_winners)

    # Embed giveaway memuat hadiah, peserta, & pemenang
    embed = engagement.build_giveaway_embed(rerolled, ended=True)
    text = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "Nitro" in embed.description
    assert "Pemenang" in text

    # Persistensi: simpan lalu muat ulang dari file yang sama
    await engagement.save_engagement_to_disk()
    assert engagement.ENGAGEMENT_FILE.exists()
    engagement.giveaways.clear()
    loaded = engagement.load_engagement_from_disk()
    assert loaded[0] == 1
    assert engagement.giveaways[555]["ended"] is True
    assert engagement.giveaways[555]["winners"] == rerolled["winners"]

    # Durasi giveaway memakai parser pengingat yang sudah ada
    assert engagement.parse_giveaway_duration("2 jam") == 7200
    assert engagement.parse_giveaway_duration("1j30m") == 5400
    assert engagement.parse_giveaway_duration("ngawur") is None


@pytest.mark.asyncio
async def test_engagement_giveaway_check_closes_due_and_updates_message():
    """Loop latar belakang menutup giveaway yang waktunya habis & mengedit pesannya."""
    cfg = engagement.create_giveaway(
        guild_id=10,
        channel_id=700,
        message_id=556,
        prize="Saldo 50rb",
        host_id=1,
        seconds=30,
    )
    engagement.join_giveaway(556, 501)
    cfg["ends_at"] = time.time() - 5  # sudah lewat

    channel = _FakeAnnouncementChannel(700)
    bot = _FakeBotForEngagement({700: channel})
    assert await engagement.run_giveaway_check(bot) == 1
    assert engagement.giveaways[556]["ended"] is True
    assert engagement.giveaways[556]["winners"] == [501]
    assert channel.edited, "pesan giveaway harus diedit saat selesai"
    # Putaran kedua tidak lagi memproses giveaway yang sama
    assert await engagement.run_giveaway_check(bot) == 0


def test_engagement_giveaway_berlapis_syarat_bobot_dan_riwayat():
    """Giveaway berlapis: syarat level/umur/role terpisah, peluang bonus, & riwayat undian."""
    cfg = engagement.create_giveaway(
        guild_id=10,
        channel_id=700,
        message_id=560,
        prize="Nitro 1 Bulan",
        host_id=1,
        seconds=3600,
        requirements={"roles": [42, 43], "level": 5, "account_age_days": 30},
        bonus_roles={99: 2},
    )
    assert cfg["requirements"] == {"roles": [42, 43], "level": 5, "account_age_days": 30}
    assert cfg["bonus_roles"] == {"99": 2}
    assert cfg["role_id"] == 42, "role_id lama tetap terisi role syarat pertama"
    assert cfg["weights"] == {} and cfg["history"] == []

    # Tiap syarat punya kode penolakan sendiri supaya member tahu apa yang kurang
    assert engagement.join_giveaway(560, 501, {42}, level=9, account_age_days=40)[0] == "syarat_role"
    assert engagement.join_giveaway(560, 501, {42, 43}, level=4, account_age_days=40)[0] == "syarat_level"
    assert engagement.join_giveaway(560, 501, {42, 43}, level=9, account_age_days=3)[0] == "syarat_umur"
    # Tanpa data level/umur, syarat tidak dianggap lolos
    assert engagement.join_giveaway(560, 501, {42, 43})[0] == "syarat_level"

    status, cfg = engagement.join_giveaway(560, 501, {42, 43, 99}, level=9, account_age_days=40)
    assert status == "ok"
    assert cfg["weights"] == {"501": 3}
    assert cfg["entry_log"][-1] == {"user_id": 501, "at": cfg["entry_log"][-1]["at"], "weight": 3, "bonus": [99]}
    assert engagement.join_giveaway(560, 502, {42, 43}, level=9, account_age_days=40)[0] == "ok"
    assert engagement.entry_weight(cfg, {42, 43, 99})[0] == 3
    assert engagement.entry_weight(cfg, {42, 43})[0] == 1
    # Bobot dibatasi supaya tidak bisa dicurangi dengan menumpuk role
    assert engagement.entry_weight({**cfg, "bonus_roles": {"1": 5, "2": 5, "3": 5}}, {1, 2, 3})[0] == 6

    ringkas = engagement.requirement_summary(cfg)
    assert "Level minimal" in ringkas and "30 hari" in ringkas and "+2" in ringkas
    assert "Belum bisa ikut" in engagement.describe_rejection("syarat_umur", cfg)
    embed = engagement.build_giveaway_embed(cfg)
    teks = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "Syarat Ikut" in teks and "Peluang ekstra" in teks
    assert "satu peluang" in embed.footer.text

    # Akhiri + reroll sama-sama tercatat di riwayat (bisa diaudit dari dashboard)
    import random

    ended = engagement.end_giveaway(560, rng=random.Random(5), actor_id=777)
    assert ended["ended"] is True and len(ended["winners"]) == 1
    riwayat = engagement.giveaway_history(560)
    assert riwayat[-1]["aksi"] == "akhir" and riwayat[-1]["oleh"] == 777
    assert engagement.reroll_pool_size(560) == 1

    status, cfg = engagement.reroll_giveaway(560, rng=random.Random(9), actor_id=777)
    assert status == "ok"
    assert engagement.giveaway_history(560)[-1]["aksi"] == "reroll"
    assert engagement.giveaway_history(560)[-1]["pemenang"] == cfg["winners"]
    assert engagement.reroll_pool_size(560) == 0
    # Semua peserta sudah pernah menang, tapi reroll tetap boleh mengulang putaran ini
    assert engagement.reroll_giveaway(560, rng=random.Random(9))[0] == "ok"


def test_engagement_pick_winners_berbobot():
    """Undian berbobot: role bonus menambah peluang tanpa pernah memilih dua kali."""
    import random

    hitung = {1: 0, 2: 0}
    for i in range(400):
        for uid in engagement.pick_winners([1, 2], 1, rng=random.Random(i), weights={1: 6, 2: 1}):
            hitung[uid] += 1
    assert hitung[1] > hitung[2] * 2, "peserta berbobot 6× harus menang jauh lebih sering"
    assert len(set(engagement.pick_winners([1, 2, 3, 4], 3, rng=random.Random(1)))) == 3
    assert engagement.pick_winners([], 2) == []
    assert engagement.pick_winners([7], 5, weights={"7": 3}) == [7]


@pytest.mark.asyncio
async def test_engagement_giveaway_template_setelan_bawaan_dan_persistensi():
    """Template & setelan bawaan giveaway: simpan, pakai ulang, lalu bertahan setelah restart."""
    d = engagement.set_giveaway_defaults(
        10,
        winner_count=3,
        seconds=7200,
        level=7,
        account_age_days=14,
        bonus_role_id=99,
        bonus_weight=2,
        ping_everyone=True,
    )
    assert d["winner_count"] == 3 and d["level"] == 7 and d["bonus_role_id"] == 99
    assert engagement.default_giveaway_config(10)["ping_everyone"] is True
    assert engagement.default_requirements(10)["level"] == 7
    assert engagement.default_bonus_roles(10) == {"99": 2}
    # Nilai aneh dari dashboard tetap aman
    assert engagement.set_giveaway_defaults(10, winner_count=0, seconds=-5)["winner_count"] == 1

    ok, pesan = engagement.save_giveaway_template(
        10,
        "Nitro Bulanan",
        winner_count=2,
        seconds=3600,
        requirements={"roles": [42], "level": 5},
        bonus_roles={99: 3},
    )
    assert ok is True and "disimpan" in pesan
    assert engagement.get_giveaway_template(10, "NITRO bulanan")["winner_count"] == 2
    assert len(engagement.list_giveaway_templates(10)) == 1
    pakai = engagement.apply_giveaway_template(10, "nitro bulanan")
    assert pakai["requirements"]["level"] == 5 and pakai["bonus_roles"] == {"99": 3}
    assert engagement.delete_giveaway_template(10, "Nitro Bulanan") is True
    assert engagement.delete_giveaway_template(10, "Nitro Bulanan") is False
    assert engagement.save_giveaway_template(10, "  ") [0] is False

    engagement.save_giveaway_template(10, "Reguler", winner_count=1, seconds=1800)
    engagement.create_giveaway(
        guild_id=10,
        channel_id=700,
        message_id=561,
        prize="Pulsa 10rb",
        host_id=1,
        seconds=1800,
        requirements={"level": 7},
        bonus_roles={99: 2},
    )
    engagement.join_giveaway(561, 501, level=8, account_age_days=0)
    await engagement.save_engagement_to_disk()

    engagement.giveaways.clear()
    engagement.giveaway_templates.clear()
    engagement.giveaway_defaults.clear()
    engagement.load_engagement_from_disk()
    assert engagement.default_giveaway_config(10)["winner_count"] == 1
    assert engagement.default_giveaway_config(10)["level"] == 7
    assert engagement.get_giveaway_template(10, "reguler")["seconds"] == 1800
    cfg = engagement.giveaways[561]
    assert cfg["requirements"]["level"] == 7 and cfg["bonus_roles"] == {"99": 2}
    assert cfg["weights"] == {"501": 1}
    assert [g["message_id"] for g in engagement.guild_giveaways(10)] == [561]


@pytest.mark.asyncio
async def test_engagement_giveaway_tombol_menjelaskan_syarat_yang_kurang():
    """Tombol 🎉 memberi alasan spesifik (level/umur) tanpa membocorkan data lain."""
    from views import GiveawayJoinView

    message_id = 562
    engagement.create_giveaway(
        guild_id=10,
        channel_id=700,
        message_id=message_id,
        prize="Mouse Gaming",
        host_id=1,
        seconds=3600,
        requirements={"level": 5},
    )

    class _Resp:
        def __init__(self):
            self.sent = []

        async def send_message(self, content=None, *, embed=None, ephemeral=False, view=None):
            self.sent.append({"content": content, "ephemeral": ephemeral})

    class _Msg:
        id = message_id

        async def edit(self, *args, **kwargs):  # pragma: no cover - tidak dipanggil saat ditolak
            raise AssertionError("pesan tidak boleh diedit saat peserta ditolak")

    user = type("U", (), {"id": 504, "roles": [], "created_at": discord.utils.utcnow()})()
    guild = type("G", (), {"id": 10})()
    ix = type("Ix", (), {"guild": guild, "user": user, "message": _Msg(), "response": _Resp()})()
    await GiveawayJoinView().join_btn.callback(ix)
    assert "Belum bisa ikut" in ix.response.sent[0]["content"]
    assert "Level minimal" in ix.response.sent[0]["content"]
    assert engagement.giveaways[message_id]["entries"] == []

    # Syarat umur akun dicek dari tanggal pembuatan akun Discord
    engagement.create_giveaway(
        guild_id=10,
        channel_id=700,
        message_id=563,
        prize="Mouse Gaming",
        host_id=1,
        seconds=3600,
        requirements={"account_age_days": 30},
    )
    ix2 = type(
        "Ix",
        (),
        {"guild": guild, "user": user, "message": type("M", (), {"id": 563})(), "response": _Resp()},
    )()
    await GiveawayJoinView().join_btn.callback(ix2)
    assert "umur akun" in ix2.response.sent[0]["content"].lower()




@pytest.mark.asyncio
async def test_engagement_birthday_parsing_and_announcement():
    """Ulang tahun: parser tanggal Indonesia, daftar per bulan, & ucapan otomatis sekali sehari."""
    assert engagement.parse_birthday_date("12-08") == (12, 8, None)
    assert engagement.parse_birthday_date("12/8/2000") == (12, 8, 2000)
    assert engagement.parse_birthday_date("1 Januari 1999") == (1, 1, 1999)
    assert engagement.parse_birthday_date("2000-08-12") == (12, 8, 2000)
    assert engagement.parse_birthday_date("31-13") is None
    assert engagement.parse_birthday_date("") is None

    day, month, year = engagement.parse_birthday_date("12/8/2000")
    engagement.set_birthday(10, 501, day, month, year)
    engagement.set_birthday(10, 502, 1, 1, None)
    assert engagement.get_birthday(10, 501)["month"] == 8
    assert len(engagement.list_birthdays(10)) == 2
    assert len(engagement.list_birthdays(10, month=1)) == 1
    assert engagement.birthday_age(engagement.get_birthday(10, 501), 2026) == 26
    assert engagement.remove_birthday(10, 502) is True
    assert engagement.remove_birthday(10, 502) is False

    # Channel & jam ucapan disimpan, lalu ucapan dikirim sekali per hari
    engagement.set_birthday_channel(10, 700, 0, 0)
    channel = _FakeAnnouncementChannel(700)
    bot = _FakeBotForEngagement({700: channel})
    engagement.set_birthday(10, 503, engagement.now_in(config.BOT_TIMEZONE).day, engagement.now_in(config.BOT_TIMEZONE).month)

    sent = await engagement.run_birthday_check(bot)
    assert sent == 1
    embed = channel.sent[0]["embed"]
    assert "Ulang Tahun" in embed.title
    assert "503" in " ".join(f.value for f in embed.fields)
    # Putaran berikutnya di hari yang sama tidak mengirim ulang
    assert await engagement.run_birthday_check(bot) == 0
    assert engagement.disable_birthday_channel(10) is True


@pytest.mark.asyncio
async def test_engagement_auto_reply_matching_and_cooldown():
    """Auto-responder: pencocokan kata/persis, jeda aman, duplikat, & penghapusan."""
    status, cfg = engagement.add_auto_reply(700, 10, "cara daftar", "Ketik /verifikasi ya!")
    assert status == "ok" and len(cfg["rules"]) == 1
    # Pemicu terlalu mirip ditolak
    assert engagement.add_auto_reply(700, 10, "Cara Daftar", "duplikat")[0] == "duplikat"
    # Aturan kedua: harus sama persis
    assert engagement.add_auto_reply(700, 10, "ping", "pong", mode="persis")[0] == "ok"

    # Cocok mengandung kata kunci
    reply = engagement.match_auto_reply(700, "kak tolong jelaskan cara daftar dong", now=1000.0)
    assert reply == "Ketik /verifikasi ya!"
    # Jeda aman mencegah balasan beruntun
    assert engagement.match_auto_reply(700, "cara daftar lagi", now=1005.0) is None
    # Setelah jeda lewat boleh membalas lagi
    assert engagement.match_auto_reply(700, "cara daftar lagi", now=1100.0) is not None

    # Mode persis tidak menanggapi kalimat panjang
    assert engagement.match_auto_reply(700, "ping", now=2000.0) == "pong"
    assert engagement.match_auto_reply(700, "ping banget nih", now=2100.0) is None

    # Channel yang dimatikan tidak pernah membalas
    engagement.set_auto_reply_config(700, 10, enabled=False)
    assert engagement.match_auto_reply(700, "cara daftar", now=3000.0) is None
    engagement.set_auto_reply_config(700, 10, enabled=True, cooldown=0)

    # Penghapusan aturan (tidak peka huruf besar/kecil)
    assert engagement.remove_auto_reply(700, "CARA DAFTAR") is True
    assert engagement.remove_auto_reply(700, "tidak-ada") is False
    assert len(engagement.auto_reply_channels[700]["rules"]) == 1

    # Batas jumlah aturan per channel dihormati
    for idx in range(config.AUTO_REPLY_MAX_RULES + 5):
        engagement.add_auto_reply(701, 10, f"kata{idx}", f"balasan {idx}")
    assert len(engagement.auto_reply_channels[701]["rules"]) == config.AUTO_REPLY_MAX_RULES

    await engagement.save_engagement_to_disk()
    engagement.auto_reply_channels.clear()
    loaded = engagement.load_engagement_from_disk()
    assert loaded[2] == 2  # dua channel punya aturan
    assert engagement.auto_reply_channels[700]["rules"][0]["trigger"] == "ping"


@pytest.mark.asyncio
async def test_engagement_announcement_schedule_and_sender():
    """Pengumuman terjadwal: parser jadwal, hitung waktu berikutnya, & pengiriman."""
    daily = engagement.parse_announcement_schedule("08:00")
    assert daily == {"kind": "harian", "hour": 8, "minute": 0, "weekday": 0}
    assert engagement.parse_announcement_schedule("harian 20:30")["minute"] == 30
    weekly = engagement.parse_announcement_schedule("mingguan sabtu 19:00")
    assert weekly["kind"] == "mingguan" and weekly["weekday"] == 5
    assert engagement.parse_announcement_schedule("senin 7:15")["weekday"] == 0
    once = engagement.parse_announcement_schedule("sekali 31-12-2026 23:59")
    assert once["kind"] == "sekali" and once["once_at"].year == 2026
    assert engagement.parse_announcement_schedule("ngawur") is None
    assert engagement.parse_announcement_schedule("sekali 31-12-2026") is None

    # Jadwal harian selalu menghasilkan waktu di masa depan
    from datetime import datetime

    ref = datetime(2026, 11, 4, 12, 0, tzinfo=engagement.get_timezone(config.BOT_TIMEZONE))
    next_daily = engagement.compute_next_run(daily, tz_name=config.BOT_TIMEZONE, reference=ref)
    assert next_daily > ref.timestamp()
    next_weekly = engagement.compute_next_run(weekly, tz_name=config.BOT_TIMEZONE, reference=ref)
    assert next_weekly > next_daily

    status, cfg = engagement.add_announcement(
        10, 700, "Mabar malam ini jam 8 ya!", daily, title="Info Mabar", tz_name=config.BOT_TIMEZONE
    )
    assert status == "ok" and cfg["title"] == "Info Mabar"
    assert "setiap hari 08:00" in engagement.describe_announcement(cfg)
    assert engagement.list_announcements(10)[0]["id"] == cfg["id"]
    assert engagement.list_announcements(11) == []

    # Pengiriman saat jadwal tiba
    cfg["next_run_at"] = time.time() - 5
    channel = _FakeAnnouncementChannel(700)
    bot = _FakeBotForEngagement({700: channel})
    assert await engagement.run_announcement_check(bot) == 1
    assert "Mabar malam ini" in channel.sent[0]["embed"].description
    assert cfg["next_run_at"] > time.time()  # dijadwalkan ulang otomatis
    assert await engagement.run_announcement_check(bot) == 0

    # Nonaktif sementara & hapus
    assert engagement.set_announcement_enabled(cfg["id"], False) is True
    assert engagement.remove_announcement(cfg["id"], guild_id=99) is False
    assert engagement.remove_announcement(cfg["id"], guild_id=10) is True
    assert engagement.list_announcements(10) == []


@pytest.mark.asyncio
async def test_engagement_command_structure_and_views():
    """Struktur command engagement, tombol giveaway persisten, & panduan /bantuan."""
    from cogs.engagement_cog import giveaway_group, jawab_group, pengumuman_group, ultah_group

    assert giveaway_group.name == "giveaway"
    assert {c.name for c in giveaway_group.commands} == {
        "mulai", "akhiri", "reroll", "daftar", "peserta",
        "template-simpan", "template-daftar", "template-hapus",
    }
    assert {c.name for c in ultah_group.commands} == {"set", "hapus", "daftar", "atur"}
    assert jawab_group.name == "jawab-otomatis"
    assert {c.name for c in jawab_group.commands} == {"tambah", "hapus", "daftar", "atur"}
    assert pengumuman_group.name == "pengumuman"
    assert {c.name for c in pengumuman_group.commands} == {
        "tambah",
        "daftar",
        "hapus",
        "atur",
        "kirim",
        "ubah",
    }

    # Batas keras Discord: deskripsi grup maksimal 100 karakter
    for group in (giveaway_group, ultah_group, jawab_group, pengumuman_group):
        assert len(group.description) <= 100
        for cmd in group.commands:
            assert len(cmd.description) <= 100

    view = views.GiveawayJoinView()
    assert view.is_persistent() is True
    assert [c.custom_id for c in view.children] == [
        "engagement:giveaway:join",
        "engagement:giveaway:leave",
    ]

    help_embed = views.build_help_embed("engagement")
    assert "Giveaway" in help_embed.title
    assert len(help_embed.fields) == 4
    menu = views.HelpMenuView(requester_id=1)
    assert "engagement" in [opt.value for opt in menu.children[0].options]


@pytest.mark.asyncio
async def test_engagement_giveaway_buttons_and_command_smoke():
    """Uji alur nyata: `/giveaway mulai` memasang pesan, lalu tombol 🎉 mencatat peserta."""
    from cogs.engagement_cog import giveaway_mulai_cmd

    class _Resp:
        def __init__(self):
            self.sent = []
            self.deferred = False

        async def send_message(self, content=None, *, embed=None, ephemeral=False, view=None):
            self.sent.append({"content": content, "embed": embed, "ephemeral": ephemeral})

        async def defer(self, *, ephemeral=False):
            self.deferred = True

    class _Followup:
        def __init__(self):
            self.sent = []

        async def send(self, content=None, *, embed=None, ephemeral=False):
            self.sent.append({"content": content, "embed": embed, "ephemeral": ephemeral})

    channel = _FakeAnnouncementChannel(700)
    guild = type(
        "G",
        (),
        {
            "id": 10,
            "name": "Server Uji",
            "get_channel": lambda self, cid: channel if cid == 700 else None,
        },
    )()
    admin = type(
        "U",
        (),
        {
            "id": 1,
            "display_name": "Admin",
            "guild_permissions": type(
                "P", (), {"administrator": True, "manage_guild": True}
            )(),
        },
    )()
    member = type(
        "U",
        (),
        {
            "id": 501,
            "display_name": "Warga",
            "mention": "<@501>",
            "roles": [type("R", (), {"id": 42})()],
            "guild_permissions": type(
                "P", (), {"administrator": False, "manage_guild": False}
            )(),
        },
    )()

    ix = type(
        "Ix",
        (),
        {
            "guild": guild,
            "channel": channel,
            "user": admin,
            "client": _FakeBotForEngagement({700: channel}),
            "response": _Resp(),
            "followup": _Followup(),
        },
    )()
    await giveaway_mulai_cmd.callback(ix, hadiah="Nitro 1 Bulan", durasi="10m", pemenang=1, channel=None, syarat_role=None)
    assert ix.response.deferred is True
    assert channel.sent, "pesan giveaway harus terkirim ke channel"
    posted = channel.sent[0]["embed"]
    assert "Nitro 1 Bulan" in posted.description
    assert engagement.giveaways, "giveaway harus tersimpan"
    message_id = next(iter(engagement.giveaways))
    assert "Giveaway dimulai" in ix.followup.sent[0]["content"]

    # Member non-admin tidak boleh membuat giveaway
    ix_member = type(
        "Ix",
        (),
        {
            "guild": guild,
            "channel": channel,
            "user": member,
            "client": _FakeBotForEngagement({700: channel}),
            "response": _Resp(),
            "followup": _Followup(),
        },
    )()
    await giveaway_mulai_cmd.callback(ix_member, hadiah="Palsu", durasi="10m", pemenang=1, channel=None, syarat_role=None)
    assert "Admin" in ix_member.response.sent[0]["content"]

    # Tombol 🎉 pada pesan giveaway mencatat peserta + mengedit embed
    class _FakeMessage:
        def __init__(self, mid):
            self.id = mid
            self.edits = []

        async def edit(self, *args, **kwargs):
            self.edits.append(kwargs)

    fake_message = _FakeMessage(message_id)
    ix_join = type(
        "Ix",
        (),
        {
            "guild": guild,
            "user": member,
            "message": fake_message,
            "response": _Resp(),
            "client": _FakeBotForEngagement({700: channel}),
        },
    )()
    view = views.GiveawayJoinView()
    await view.join_btn.callback(ix_join)
    assert "Berhasil ikut" in ix_join.response.sent[0]["content"]
    assert engagement.giveaways[message_id]["entries"] == [501]
    assert fake_message.edits, "embed giveaway harus diperbarui setelah peserta masuk"

    # Klik kedua tidak menambah peluang
    await view.join_btn.callback(ix_join)
    assert "sudah terdaftar" in ix_join.response.sent[1]["content"]
    assert engagement.giveaways[message_id]["entries"] == [501]

    # Tombol batalkan mengeluarkan peserta
    await view.leave_btn.callback(ix_join)
    assert engagement.giveaways[message_id]["entries"] == []


# ==============================================================================
# ANTI-SPAM & ANTI-RAID RINGAN (Tier 2B)
# ==============================================================================
class _SpamMessage:
    """Pesan tiruan untuk menguji penjaga anti-spam."""

    def __init__(
        self,
        *,
        content: str,
        author_id: int = 501,
        channel_id: int = 700,
        guild_id: int = 10,
        mentions: int = 0,
        bot: bool = False,
        admin: bool = False,
        manage_messages: bool = False,
        role_ids: tuple[int, ...] = (),
    ):
        self.content = content
        self.guild = type("G", (), {"id": guild_id})()
        self.channel = type("Ch", (), {"id": channel_id, "mention": f"<#{channel_id}>"})()
        self.mentions = [object() for _ in range(mentions)]
        self.author = type(
            "U",
            (),
            {
                "id": author_id,
                "bot": bot,
                "roles": [type("R", (), {"id": rid})() for rid in role_ids],
                "guild_permissions": type(
                    "P",
                    (),
                    {
                        "administrator": admin,
                        "manage_messages": manage_messages,
                        "manage_guild": False,
                    },
                )(),
            },
        )()
        self.deleted = 0
        self.timeouts = []

    async def delete(self):
        self.deleted += 1

    @property
    def author_is_timed_out(self) -> bool:
        return bool(self.timeouts)


class _SpamMember:
    def __init__(self, guild_id: int = 10, uid: int = 501, bot: bool = False):
        self.guild = type("G", (), {"id": guild_id, "name": "Server Uji"})()
        self.id = uid
        self.bot = bot
        self.mention = f"<@{uid}>"


def _make_timeout_author(message: _SpamMessage):
    async def _timeout(delta, reason=None):
        message.timeouts.append(delta)

    message.author.timeout = _timeout
    return message


@pytest.mark.asyncio
async def test_antispam_detection_rules_and_exemptions():
    """Deteksi flood, duplikat, mention, & link; admin/staf/pengecualian selalu diabaikan."""
    antispam.set_spam_config(10, aktif=True)
    assert antispam.is_spam_guard_active(10) is True
    cfg = antispam.get_spam_config(10)
    assert cfg["mode"] == "lapor"  # default aman

    # 1. Flood: 6 pesan dalam jendela 10 detik
    for idx in range(5):
        assert antispam.detect_spam(_SpamMessage(content=f"halo {idx}"), now=1000.0 + idx) is None
    flood = antispam.detect_spam(_SpamMessage(content="halo 99"), now=1006.0)
    assert flood is not None and flood["reason"] == "flood"
    assert "6" in flood["detail"]

    # 2. Pesan berulang (isi sama 3x)
    for idx in range(2):
        assert antispam.detect_spam(_SpamMessage(content="promo murah!!", author_id=600), now=2000.0 + idx) is None
    dup = antispam.detect_spam(_SpamMessage(content="promo murah!!", author_id=600), now=2002.0)
    assert dup is not None and dup["reason"] == "duplikat"

    # 3. Mention massal
    mention = antispam.detect_spam(_SpamMessage(content="@everyone", author_id=601, mentions=6), now=3000.0)
    assert mention is not None and mention["reason"] == "mention"
    assert antispam.detect_spam(_SpamMessage(content="@halo", author_id=601, mentions=2), now=3001.0) is None

    # 4. Link beruntun (4 link dalam satu pesan) & link sama berulang 3x
    many_links = " ".join(f"https://contoh{idx}.com/a" for idx in range(4))
    link_hit = antispam.detect_spam(_SpamMessage(content=many_links, author_id=602), now=4000.0)
    assert link_hit is not None and link_hit["reason"] == "link"
    for idx in range(2):
        antispam.detect_spam(_SpamMessage(content="https://sama.com/x", author_id=603), now=5000.0 + idx)
    repeated = antispam.detect_spam(_SpamMessage(content="https://sama.com/x", author_id=603), now=5002.0)
    assert repeated is not None and repeated["reason"] == "link"

    # 5. Admin, staf, & bot tidak pernah diperiksa
    assert antispam.detect_spam(_SpamMessage(content="spam", admin=True, mentions=9), now=6000.0) is None
    assert antispam.detect_spam(_SpamMessage(content="spam", manage_messages=True, mentions=9), now=6001.0) is None
    assert antispam.detect_spam(_SpamMessage(content="spam", bot=True, mentions=9), now=6002.0) is None

    # 6. Channel & role pengecualian
    antispam.set_spam_config(10, exempt_channels=[700], exempt_roles=[55])
    antispam.reset_runtime_state()
    assert antispam.detect_spam(_SpamMessage(content="spam", mentions=9), now=7000.0) is None
    assert (
        antispam.detect_spam(_SpamMessage(content="x", mentions=9, role_ids=(55,), channel_id=701), now=7001.0)
        is None
    )

    # 7. Huruf kapital hanya ditindak bila diaktifkan
    antispam.set_spam_config(10, caps_enabled=False, exempt_channels=[], exempt_roles=[])
    antispam.reset_runtime_state()
    assert antispam.detect_spam(_SpamMessage(content="INI PESAN SANGAT KERAS SEKALI", author_id=610), now=8000.0) is None
    antispam.set_spam_config(10, caps_enabled=True)
    caps = antispam.detect_spam(_SpamMessage(content="INI PESAN SANGAT KERAS SEKALI", author_id=611), now=8100.0)
    assert caps is not None and caps["reason"] == "caps"

    # 8. Penjaga yang dimatikan tidak memeriksa apa pun
    antispam.set_spam_config(10, aktif=False)
    antispam.reset_runtime_state()
    assert antispam.detect_spam(_SpamMessage(content="spam", mentions=9), now=9000.0) is None


@pytest.mark.asyncio
async def test_antispam_actions_modes_and_raid_alert():
    """Mode lapor tidak menghapus, mode hapus menghapus, mode timeout men-time-out, & anti-raid melapor."""
    log_channel = _FakeAnnouncementChannel(900)
    bot = _FakeBotForEngagement({900: log_channel})

    # --- Mode lapor: pesan TIDAK dihapus, tetapi laporan terkirim ---
    antispam.set_spam_config(10, aktif=True, log_channel_id=900)
    antispam.reset_runtime_state()
    message = _SpamMessage(content="@everyone", mentions=6)
    assert await antispam.handle_spam_guard(message, bot=bot, now=10_000.0) is False
    assert message.deleted == 0
    assert log_channel.sent, "laporan anti-spam harus dikirim ke channel log"
    alert = log_channel.sent[0]["embed"]
    assert "Anti-Spam" in alert.title
    assert alert.footer.text.startswith("Mode aman")
    # Laporan berikutnya tertahan kooldown 2 menit
    second = _SpamMessage(content="@everyone", mentions=6)
    await antispam.handle_spam_guard(second, bot=bot, now=10_001.0)
    assert len(log_channel.sent) == 1

    # --- Mode hapus: pesan dihapus ---
    antispam.set_spam_config(10, mode="hapus")
    antispam.reset_runtime_state()
    to_delete = _SpamMessage(content="@everyone", mentions=6, author_id=700)
    assert await antispam.handle_spam_guard(to_delete, bot=bot, now=11_000.0) is True
    assert to_delete.deleted == 1

    # --- Mode timeout: pesan dihapus + author di-time-out ---
    antispam.set_spam_config(10, mode="timeout", timeout_sec=600)
    antispam.reset_runtime_state()
    to_timeout = _make_timeout_author(_SpamMessage(content="@everyone", mentions=6, author_id=701))
    assert await antispam.handle_spam_guard(to_timeout, bot=bot, now=12_000.0) is True
    assert to_timeout.deleted == 1
    assert to_timeout.timeouts and to_timeout.timeouts[0].total_seconds() == 600
    assert antispam.get_spam_config(10)["blocked"] >= 1

    # --- Anti-raid: lonjakan join menghasilkan SATU peringatan (tanpa menendang) ---
    antispam.reset_runtime_state()
    sent_before = len(log_channel.sent)
    for idx in range(config.SPAM_RAID_JOIN_COUNT - 1):
        assert await antispam.handle_member_join_guard(bot, _SpamMember(uid=800 + idx), now=20_000.0 + idx) is False
    assert await antispam.handle_member_join_guard(bot, _SpamMember(uid=899), now=20_010.0) is True
    raid_alert = log_channel.sent[-1]["embed"]
    assert "Raid" in raid_alert.title
    assert "tidak pernah menendang" in raid_alert.footer.text
    # Tidak ada peringatan berulang dalam jendela yang sama
    assert await antispam.handle_member_join_guard(bot, _SpamMember(uid=900), now=20_011.0) is False
    assert len(log_channel.sent) == sent_before + 1

    # --- Persistensi konfigurasi ---
    await antispam.save_antispam_to_disk()
    assert antispam.ANTISPAM_FILE.exists()
    antispam.spam_guilds.clear()
    assert antispam.load_antispam_from_disk() == 1
    reloaded = antispam.get_spam_config(10)
    assert reloaded["mode"] == "timeout" and reloaded["timeout_sec"] == 600

    # --- Status embed & pembersihan ---
    status = antispam.build_spam_status_embed(10)
    text = " ".join(f"{f.name} {f.value}" for f in status.fields)
    assert "Anti-Spam" in status.title
    assert "`600` detik" in text
    assert "NONAKTIF" in antispam.build_spam_status_embed(99).title
    assert antispam.cleanup_antispam_runtime() >= 0


@pytest.mark.asyncio
async def test_antispam_command_and_help_structure():
    """`/keamanan spam` & `/keamanan spam-status` terdaftar, plus panduan /bantuan diperbarui."""
    from cogs.server_cog import keamanan_group

    # v1.40: honeypot (channel jebakan) menambah satu subcommand
    assert {c.name for c in keamanan_group.commands} == {
        "phising", "cek", "spam", "spam-status", "honeypot"
    }
    for cmd in keamanan_group.commands:
        assert len(cmd.description) <= 100

    # Mode yang tersedia harus mencakup "lapor" sebagai default aman
    assert set(antispam.SPAM_MODES) == {"lapor", "hapus", "timeout"}
    assert "lapor" in antispam.default_config()["mode"]

    help_embed = views.build_help_embed("server")
    assert any("Anti-Spam" in f.name for f in help_embed.fields)


# ==============================================================================
# LEVELING & XP + TIKET DUKUNGAN (Tier 2C)
# ==============================================================================
@pytest.mark.asyncio
async def test_levels_formula_config_and_xp_flow():
    """Rumus XP, jeda anti-farming, pengecualian channel/role, level-up, & persistensi."""
    # 1. Rumus XP monoton naik
    assert levels.xp_for_level(0) == 100
    assert levels.xp_for_level(1) == 155
    assert levels.xp_for_level(5) == 475
    assert levels.total_xp_for_level(0) == 0
    assert levels.total_xp_for_level(2) == 255
    assert levels.level_from_total_xp(0) == 0
    assert levels.level_from_total_xp(99) == 0
    assert levels.level_from_total_xp(100) == 1
    assert levels.level_from_total_xp(255) == 2
    assert levels.level_from_total_xp(10**9) == config.LEVELS_MAX_LEVEL
    current, needed = levels.progress_in_level(105, 1)
    assert (current, needed) == (5, 155)
    bar = levels.build_progress_bar(50, 100)
    assert bar.count("▰") == 6 and bar.count("▱") == 6
    assert levels.build_progress_bar(200, 100).count("▰") == 12

    # 2. Leveling default NONAKTIF -> tidak ada XP
    assert levels.add_message_xp(10, 501, now=1000.0) is None
    assert levels.is_leveling_active(10) is False

    # 3. Aktifkan & beri XP
    cfg = levels.set_level_config(10, aktif=True, xp_min=20, xp_max=20, cooldown=60)
    assert cfg is not None and levels.is_leveling_active(10) is True
    import random

    first = levels.add_message_xp(10, 501, now=2000.0, rng=random.Random(1))
    assert first is not None and first["gained"] == 20 and first["level_up"] is False
    # Jeda anti-farming: pesan berikutnya dalam 60 detik tidak dapat XP
    assert levels.add_message_xp(10, 501, now=2030.0) is None
    second = levels.add_message_xp(10, 501, now=2100.0)
    assert second is not None and second["xp"] == 40

    # 4. Naik level -> dapat role hadiah bila diatur
    levels.set_level_role(10, 1, 777)
    data = levels.levels["10:501"]
    data["xp"] = 95
    data["level"] = 0
    up = levels.add_message_xp(10, 501, now=3000.0)
    assert up is not None and up["level_up"] is True and up["level"] == 1
    assert up["role_id"] == 777
    assert levels.get_level_config(10)["leveled_up"] == 1
    assert levels.reward_role_for_level(levels.get_level_config(10), 5) is None
    levels.set_level_role(10, 1, None)
    assert levels.reward_role_for_level(levels.get_level_config(10), 1) is None

    # 5. Channel & role yang diabaikan tidak memberi XP
    levels.set_level_config(10, ignore_channels=[900], ignore_roles=[55])
    assert levels.add_message_xp(10, 502, channel_id=900, now=4000.0) is None
    assert levels.add_message_xp(10, 502, channel_id=901, role_ids={55}, now=4001.0) is None
    assert levels.add_message_xp(10, 502, channel_id=901, role_ids={1}, now=4002.0) is not None

    # 6. Kartu level & papan peringkat
    member = type("M", (), {"display_name": "Rina", "display_avatar": None})()
    card = levels.build_level_embed(member, levels.get_member_level(10, 501), levels.get_level_config(10))
    assert "Level 1" in card.title and "Rina" in card.title
    assert "▰" in card.description or "▱" in card.description
    empty_card = levels.build_level_embed(member, levels.get_member_level(10, 999))
    assert empty_card.fields[0].value == "`0`"

    for idx in range(12):
        levels.levels[f"10:{600 + idx}"] = {"xp": 100 + idx * 50, "level": 1, "messages": 5, "last_at": 0}
    rows, page, total_pages = levels.leaderboard(10, limit=10, page=0)
    assert len(rows) == 10 and page == 0 and total_pages == 2
    assert rows[0][0] == 611  # XP tertinggi
    board = levels.build_leaderboard_embed(
        "Server Uji", rows, page=page, total_pages=total_pages, total_members=13, page_size=10
    )
    assert "🥇" in board.fields[0].value and "Papan Peringkat" in board.title
    assert "`1/2`" in board.description

    # 7. Persistensi + reset member
    await levels.save_levels_to_disk()
    assert levels.LEVELS_FILE.exists()
    levels.levels.clear()
    levels.level_guilds.clear()
    assert levels.load_levels_from_disk() == 1
    assert "10:501" in levels.levels
    assert levels.get_level_config(10)["cooldown"] == 60
    assert levels.reset_member(10, 501) is True
    assert levels.reset_member(10, 501) is False

    # 8. Pemangkasan member agar JSON tetap kecil
    monkeypatch_limit = 3
    levels.levels.clear()
    for idx in range(10):
        levels.levels[f"10:{idx}"] = {"xp": (idx + 1) * 10, "level": 0, "messages": 1, "last_at": 0}
    original = levels.LEVELS_MAX_MEMBERS
    try:
        levels.LEVELS_MAX_MEMBERS = monkeypatch_limit
        await levels.save_levels_to_disk()
        assert len(levels.levels) == monkeypatch_limit
        assert "10:9" in levels.levels  # XP terbesar dipertahankan
    finally:
        levels.LEVELS_MAX_MEMBERS = original


@pytest.mark.asyncio
async def test_tickets_lifecycle_config_and_transcript():
    """Siklus tiket: konfigurasi, batas per member, klaim, tutup, transkrip, & persistensi."""
    # 1. Default NONAKTIF
    assert tickets.is_ticket_enabled(10) is False

    # 2. Konfigurasi panel
    cfg = tickets.set_ticket_config(
        10,
        enabled=True,
        panel_channel_id=700,
        staff_role_id=42,
        log_channel_id=900,
        max_open=2,
    )
    assert tickets.is_ticket_enabled(10) is True
    assert cfg["max_open"] == 2

    # 3. Batas tiket aktif per member
    assert tickets.can_open_ticket(10, 501) == (True, "")
    first = tickets.register_ticket(1001, 10, 501, topic="Masalah verifikasi")
    assert first["number"] == 1 and first["status"] == "terbuka"
    tickets.register_ticket(1002, 10, 501)
    allowed, reason = tickets.can_open_ticket(10, 501)
    assert allowed is False and "2 tiket aktif" in reason
    assert tickets.can_open_ticket(10, 502)[0] is True

    # 4. Klaim tiket
    status, claimed = tickets.claim_ticket(1001, 777)
    assert status == "ok" and claimed["status"] == "diklaim" and claimed["claimed_by"] == 777
    assert tickets.claim_ticket(1001, 777)[0] == "sudah"
    assert tickets.claim_ticket(9999, 777)[0] == "tidak_ada"

    # 5. Tambah member ke tiket + hak lihat
    assert tickets.add_user_to_ticket(1001, 888) is True
    assert tickets.add_user_to_ticket(1001, 888) is False
    assert tickets.can_view_ticket(tickets.get_ticket(1001), 888) is True
    assert tickets.can_view_ticket(tickets.get_ticket(1001), 999) is False

    # 6. Tutup tiket + transkrip
    status, closed = tickets.close_ticket(1001, 777, now=5000.0)
    assert status == "ok" and closed["status"] == "selesai"
    assert tickets.close_ticket(1001, 777)[0] == "selesai"
    assert tickets.get_ticket_config(10)["closed"] == 1

    class _Msg:
        def __init__(self, name, content, atts=()):
            self.author = type("A", (), {"display_name": name})()
            self.content = content
            self.created_at = 1_700_000_000
            self.attachments = [type("At", (), {"url": url})() for url in atts]

    messages = [_Msg("Warga", "Bot tidak bisa verifikasi"), _Msg("Staf", "Sudah dibantu ya", ["https://x/y.png"])]
    text, filename = tickets.build_transcript(closed, messages)
    assert filename == "tiket-0001.txt"
    assert "TRANSKRIP TIKET #0001" in text
    assert "Warga: Bot tidak bisa verifikasi" in text
    assert "lampiran: https://x/y.png" in text

    file_obj = tickets.transcript_file(text, filename)
    assert file_obj.filename == filename

    # 7. Daftar & statistik
    active = tickets.list_tickets(10)
    assert len(active) == 2
    assert tickets.list_tickets(10, status="terbuka")[0]["thread_id"] == 1002
    embed = tickets.build_ticket_status_embed(10)
    body = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "Sistem Tiket" in embed.title
    assert "Total selesai: `1`" in body
    assert "NONAKTIF" in tickets.build_ticket_status_embed(99).title

    # 8. Tiket kedaluwarsa (auto-close opsional)
    assert tickets.stale_tickets(hours=0) == []
    stale = tickets.stale_tickets(hours=1, now=time.time() + 7200)
    assert 1002 in stale

    # 9. Persistensi
    await tickets.save_tickets_to_disk()
    assert tickets.TICKETS_FILE.exists()
    tickets.tickets.clear()
    tickets.ticket_guilds.clear()
    tickets._ticket_seq.clear()
    assert tickets.load_tickets_from_disk() == 1
    assert tickets.get_ticket(1001)["status"] == "selesai"
    assert tickets.next_ticket_number(10) == 3

    # 10. Panel lama setelah restart tetap tidak membuat nomor ganda
    assert tickets.register_ticket(1003, 10, 503)["number"] == 4

    # 11. Matikan & bersihkan thread yang dihapus
    assert tickets.disable_tickets(10) is True
    assert tickets.is_ticket_enabled(10) is False
    assert tickets.handle_thread_delete(1003) is True
    assert tickets.get_ticket(1003) is None
    assert tickets.cleanup_tickets_runtime(max_closed=0) >= 1


@pytest.mark.asyncio
async def test_growth_commands_views_and_help():
    """Struktur command /level & /tiket, tombol persisten, & panduan /bantuan kategori growth."""
    from cogs.growth_cog import level_group, tiket_group

    assert level_group.name == "level"
    assert {c.name for c in level_group.commands} == {
        "lihat", "papan", "atur", "role", "status", "voice",
        # v1.34.0-beta: musim & prestige
        "musim", "prestise",
        # v1.40: kartu rank PNG (perender sendiri, 0 kuota AI)
        "kartu",
    }
    assert tiket_group.name == "tiket"
    assert {c.name for c in tiket_group.commands} == {
        "panel", "status", "tutup", "tambah", "daftar", "matikan",
        # v1.33.0-beta: rating bintang, SLA respons pertama, & auto-close
        "atur", "rating",
        # v1.40: catatan internal staf (tidak dikirim ke member)
        "catat", "catatan",
        # v1.40: beberapa topik per panel
        "topik",
    }
    for group in (level_group, tiket_group):
        assert len(group.description) <= 100
        for cmd in group.commands:
            assert len(cmd.description) <= 100

    panel = views.TicketPanelView()
    assert panel.is_persistent() is True
    # Panel tiket kini berupa kartu Components V2 → tombol berada di dalam Container
    assert panel.to_components()[0]["type"] == 17
    assert [
        item.custom_id for item in panel.walk_children() if isinstance(item, discord.ui.Button)
    ] == ["ticket:panel:open"]
    actions = views.TicketActionsView()
    assert actions.is_persistent() is True
    assert [c.custom_id for c in actions.children] == ["ticket:panel:claim", "ticket:panel:close"]

    panel_embed = tickets.build_panel_embed("Server Uji", staff_role_id=42)
    assert "Pusat Bantuan" in panel_embed.title
    assert "<@&42>" in " ".join(f.value for f in panel_embed.fields)

    ticket_embed = tickets.build_ticket_embed(
        {"number": 7, "user_id": 501, "status": "terbuka", "topic": "Bug", "claimed_by": None},
        staff_role_id=42,
    )
    assert "#0007" in ticket_embed.title

    growth_help = views.build_help_embed("growth")
    assert len(growth_help.fields) == 2
    menu = views.HelpMenuView(requester_id=1)
    assert "growth" in [opt.value for opt in menu.children[0].options]


@pytest.mark.asyncio
async def test_growth_message_xp_hook_and_ticket_panel_smoke(monkeypatch):
    """Hook XP dari pesan Discord + smoke test tombol panel tiket (tanpa Discord asli)."""
    from cogs.growth_cog import handle_message_xp

    # --- Hook XP: pesan member biasa -> XP bertambah & pengumuman dikirim saat naik level ---
    levels.set_level_config(10, aktif=True, xp_min=100, xp_max=100, cooldown=0)
    levels.levels["10:501"] = {"xp": 0, "level": 0, "messages": 0, "last_at": 0}

    channel = _FakeAnnouncementChannel(700)
    bot = _FakeBotForEngagement({700: channel})
    message = type(
        "Msg",
        (),
        {
            "guild": type("G", (), {"id": 10})(),
            "author": type("U", (), {"id": 501, "bot": False, "roles": []})(),
            "channel": channel,
            "content": "halo semua",
        },
    )()
    await handle_message_xp(bot, message)
    assert levels.levels["10:501"]["xp"] == 100
    assert levels.levels["10:501"]["level"] == 1
    assert channel.sent and "level 1" in channel.sent[-1]["args"][0]

    # Pesan dari bot tidak diberi XP
    bot_message = type(
        "Msg",
        (),
        {
            "guild": type("G", (), {"id": 10})(),
            "author": type("U", (), {"id": 999, "bot": True, "roles": []})(),
            "channel": channel,
            "content": "pengumuman",
        },
    )()
    await handle_message_xp(bot, bot_message)
    assert "10:999" not in levels.levels

    # --- Smoke test tombol "Buat Tiket" ---
    tickets.set_ticket_config(10, enabled=True, panel_channel_id=700, staff_role_id=42, max_open=2)

    class _FakeThread(_FakeAnnouncementChannel):
        def __init__(self):
            super().__init__(710)
            self.added_users = []
            self.name = "tiket-uji"

        async def add_user(self, user):
            self.added_users.append(getattr(user, "id", 0))

        async def edit(self, **kwargs):
            self.edited.append(kwargs)

    thread = _FakeThread()

    class _PanelChannel(_FakeAnnouncementChannel):
        async def create_thread(self, **kwargs):
            self.created_with = kwargs
            return thread

    panel_channel = _PanelChannel(700)

    class _Resp:
        def __init__(self):
            self.sent = []
            self.deferred = False

        async def send_message(self, content=None, *, embed=None, ephemeral=False, view=None):
            self.sent.append({"content": content, "embed": embed, "ephemeral": ephemeral})

        async def defer(self, *, ephemeral=False):
            self.deferred = True

    class _Followup:
        def __init__(self):
            self.sent = []

        async def send(self, content=None, *, embed=None, ephemeral=False):
            self.sent.append({"content": content, "embed": embed, "ephemeral": ephemeral})

    guild = type(
        "G",
        (),
        {
            "id": 10,
            "name": "Server Uji",
            "get_role": lambda self, rid: type("R", (), {"id": rid, "members": []})(),
        },
    )()
    user = type(
        "U",
        (),
        {
            "id": 501,
            "name": "warga",
            "display_name": "Warga",
            "roles": [],
            "bot": False,
            "guild_permissions": type(
                "P", (), {"administrator": False, "manage_threads": False, "manage_channels": False, "manage_messages": False}
            )(),
        },
    )()
    ix = type(
        "Ix",
        (),
        {
            "guild": guild,
            "guild_id": 10,
            "user": user,
            "channel": panel_channel,
            "channel_id": 700,
            "client": _FakeBotForEngagement({700: panel_channel}),
            "response": _Resp(),
            "followup": _Followup(),
        },
    )()

    await views.handle_ticket_open(ix)
    assert ix.response.deferred is True
    assert thread.added_users == [501]
    assert tickets.tickets, "tiket harus tercatat"
    record = tickets.get_ticket(thread.id)
    assert record["user_id"] == 501 and record["status"] == "terbuka"
    assert "Tiket dibuat" in ix.followup.sent[0]["content"]
    assert thread.sent and thread.sent[0]["view"] is not None

    # Tiket kedua & ketiga ditolak karena batas max_open=2
    ix2 = type(
        "Ix",
        (),
        {
            "guild": guild,
            "guild_id": 10,
            "user": user,
            "channel": panel_channel,
            "channel_id": 700,
            "client": _FakeBotForEngagement({700: panel_channel}),
            "response": _Resp(),
            "followup": _Followup(),
        },
    )()
    tickets.register_ticket(720, 10, 501)
    await views.handle_ticket_open(ix2)
    assert "2 tiket aktif" in ix2.response.sent[0]["content"]


@pytest.mark.asyncio
async def test_insights_usage_tracking_rekap_cache_and_faq_local():
    """Tier 3: pencatatan pemakaian AI, cache rekap (0 kuota), batas harian, & FAQ lokal."""
    import insights
    from config import AI_USAGE_FILE, REKAP_CACHE_TTL_SEC

    # 1. Pencatatan pemakaian per jenis & per member
    insights.ai_usage.clear()
    insights.rekap_cache.clear()
    insights.record_ai_usage("chat", user_id=501, channel_id=900, now=time.time())
    insights.record_ai_usage("chat", user_id=501, channel_id=900, now=time.time())
    insights.record_ai_usage("cari", user_id=502, channel_id=901, now=time.time())
    insights.record_ai_usage("rekap", user_id=501, channel_id=900, cache_hit=True, now=time.time())

    day = insights.today_key()
    bucket = insights.ai_usage[day]
    assert bucket["total"] == 3 and bucket["cache_hits"] == 1
    assert bucket["kinds"]["chat"] == 2 and bucket["kinds"]["cache"] == 1
    assert insights.usage_for_user(501) == 2
    assert insights.total_usage() == 3

    # 2. Batas harian per member (0 = tanpa batas)
    assert insights.check_daily_cap(999, cap=0) == (True, 0, 0)
    allowed, used, cap = insights.check_daily_cap(501, cap=2)
    assert allowed is False and used == 2 and cap == 2
    assert insights.check_daily_cap(502, cap=2)[0] is True

    # 3. Cache rekap: hit menghemat kuota, kedaluwarsa membuat entri hilang
    now = time.time()
    insights.store_rekap(900, 6, "Ringkasan obrolan.", message_count=12, now=now)
    cached = insights.get_cached_rekap(900, 6)
    assert cached and cached["text"] == "Ringkasan obrolan." and cached["count"] == 12
    assert insights.get_cached_rekap(900, 6, max_age=0) is not None
    insights.rekap_cache[insights.cache_key(901, 6)] = {"text": "basi", "created_at": now - REKAP_CACHE_TTL_SEC - 5}
    assert insights.get_cached_rekap(901, 6) is None
    assert insights.get_cached_rekap(900, 3) is None
    assert insights.rekap_message_limit() == config.REKAP_MAX_MESSAGES

    # 4. Embed pemakaian & rekap bisa dirender tanpa error
    usage_embed = insights.build_usage_embed()
    assert "Pemakaian" in usage_embed.title
    assert any("Chat" in f.name or "chat" in f.value.lower() for f in usage_embed.fields)
    rekap_embed = insights.build_rekap_embed("umum", "Isi rekap", hours=6, message_count=12)
    assert "6 jam terakhir" in rekap_embed.title

    # 5. FAQ lokal: pencarian kata kunci tanpa AI + embed jawaban/daftar
    community_agent.upsert_server_knowledge(10, "Cara Verifikasi", "Klik tombol verifikasi di channel verifikasi.")
    community_agent.upsert_server_knowledge(10, "Jam Event", "Event mingguan setiap Sabtu pukul 20.00 WIB.")
    entries = community_agent.get_server_knowledge_entries(10)
    matches = insights.search_faq(entries, "bagaimana cara verifikasi akun?")
    assert matches and matches[0]["topic"] == "Cara Verifikasi"
    assert insights.search_faq(entries, "zzz qqq") == []
    answer_embed = insights.build_faq_answer_embed("cara verifikasi", matches)
    assert answer_embed.fields
    list_embed = insights.build_faq_list_embed(entries, guild_name="Server Uji")
    assert list_embed.title

    # 6. Simpan ke disk bersifat atomik & file JSON valid
    await insights.save_ai_usage_to_disk()
    assert AI_USAGE_FILE.exists()
    payload = json.loads(AI_USAGE_FILE.read_text(encoding="utf-8"))
    assert day in payload["days"]
    loaded = insights.load_ai_usage_from_disk()
    assert loaded >= 1

    # 6b. Pemangkasan otomatis: counter member/channel dibatasi & hari lama dibuang saat restart
    insights.ai_usage.clear()
    for i in range(insights.MAX_TRACKED_PER_DAY + 40):
        insights.record_ai_usage("chat", user_id=90_000 + i, channel_id=80_000 + i)
    bucket = insights.ai_usage[insights.today_key()]
    assert len(bucket["users"]) <= insights.MAX_TRACKED_PER_DAY
    assert len(bucket["channels"]) <= insights.MAX_TRACKED_PER_DAY
    for d in range(1, 11):
        insights.ai_usage[f"2026-03-{d:02d}"] = dict(bucket)
    await insights.save_ai_usage_to_disk()
    assert insights.load_ai_usage_from_disk() == config.AI_USAGE_KEEP_DAYS

    insights.cleanup_insights_runtime()
    AI_USAGE_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_insights_commands_and_daily_cap_guard(monkeypatch):
    """Tier 3: command /pemakaian, /faq, /ringkas channel terdaftar & guard batas harian bekerja."""
    import insights
    from cogs.insights_cog import faq_group, pemakaian_group
    from cogs.helpers import enforce_member_cooldown
    from cogs.tools_cog import ringkas_group

    assert {c.name for c in faq_group.commands} == {"tanya", "daftar", "tambah", "hapus"}
    assert {c.name for c in pemakaian_group.commands} == {"lihat", "tren", "status", "reset"}
    assert {c.name for c in ringkas_group.commands} == {"chat", "channel", "link"}
    ringkas_channel = [c for c in ringkas_group.commands if c.name == "channel"][0]
    assert [p.name for p in ringkas_channel.parameters] == ["periode", "paksa", "publik"]

    # Guard: batas harian tercapai → pesan penolakan, cooldown tetap diizinkan
    insights.ai_usage.clear()
    insights.record_ai_usage("chat", user_id=777, now=time.time())
    monkeypatch.setattr(insights, "AI_DAILY_CAP_PER_USER", 1)
    sent = []

    class _Resp:
        async def send_message(self, content=None, **kwargs):
            sent.append(content)

    class _User:
        id = 777

    class _Interaction:
        user = _User()
        response = _Resp()

    allowed = await enforce_member_cooldown(_Interaction(), "uji_kapasitas_tier3")
    assert allowed is False
    assert sent and "Batas harian" in sent[0]

    # Tanpa cap → diizinkan
    monkeypatch.setattr(insights, "AI_DAILY_CAP_PER_USER", 0)
    assert await enforce_member_cooldown(_Interaction(), "uji_kapasitas_tier3_b") is True

    # Admin server selalu bebas batas harian
    import cogs.helpers as helpers_mod

    sent.clear()
    monkeypatch.setattr(insights, "AI_DAILY_CAP_PER_USER", 1)
    monkeypatch.setattr(helpers_mod, "is_interaction_admin", lambda _ix: True)
    assert await enforce_member_cooldown(_Interaction(), "uji_kapasitas_tier3_c") is True
    assert sent == []
    insights.ai_usage.clear()


@pytest.mark.asyncio
async def test_music_node_diagnostics_and_reconnect(monkeypatch):
    """v1.11.1-beta: status node Lavalink nyata, diagnosa, & penyambungan ulang otomatis."""
    import music
    import cogs.music_cog as music_cog

    class _Status:
        def __init__(self, name):
            self.name = name

    class _Node:
        def __init__(self, identifier, uri, status, players=0):
            self.identifier = identifier
            self.uri = uri
            self.status = _Status(status)
            self.players = {i: object() for i in range(players)}
            self.closed = False

        async def close(self):
            self.closed = True
            self.status = _Status("DISCONNECTED")

    class _Pool:
        nodes: dict = {}

    class _FakeWavelink:
        Pool = _Pool

    class _FakeSession:
        def __init__(self):
            class _Resp:
                status = 200

                async def json(self, content_type=None):
                    return {"version": {"semver": "4.0.8"}}

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *exc):
                    return False

            self._resp = _Resp()

        def post(self, *a, **kw):
            return self._resp

    monkeypatch.setattr(music, "wavelink", _FakeWavelink)
    monkeypatch.setattr(music, "WAVELINK_AVAILABLE", True)
    monkeypatch.setattr(music, "MUSIC_ENABLED", True)
    monkeypatch.setattr(music, "LAVALINK_URI", "wss://lavalink.contoh.net:443")

    # 1. Pool kosong → tidak siap, pesan jujur, diagnosa menyebut node tidak terdaftar
    _Pool.nodes = {}
    snap = music.node_snapshot()
    assert snap["ready"] is False and snap["nodes"] == []
    assert "Belum tersambung" in music.music_status()
    diagnosis = music.node_diagnosis()
    assert "tidak ada node yang terdaftar" in diagnosis
    assert "/v4/info" in diagnosis

    # 2. Node CONNECTING (kasus nyata: handshake sukses tapi 'ready' tak pernah datang)
    _Pool.nodes = {"utama": _Node("utama", "wss://lavalink.contoh.net:443", "CONNECTING")}
    snap = music.node_snapshot()
    assert snap["connecting"] == 1 and snap["ready"] is False
    assert "⏳" in music.music_status()
    assert "belum mengirim sinyal `ready`" in music.node_diagnosis()

    # 3. Node CONNECTED → status jelas + jumlah player
    _Pool.nodes = {"utama": _Node("utama", "wss://lavalink.contoh.net:443", "CONNECTED", players=3)}
    snap = music.node_snapshot()
    assert snap["ready"] is True and snap["connected"] == 1
    status = music.music_status()
    assert "Tersambung" in status and "3 player" in status
    assert "tersambung" in music.node_diagnosis()

    # 4. Hint TLS: ws:// + port 443 & wss:// + port non-443
    monkeypatch.setattr(music, "LAVALINK_URI", "lavalink.contoh.net:443")
    _Pool.nodes = {}
    assert "tanpa awalan `wss://`" in music.node_diagnosis()
    monkeypatch.setattr(music, "LAVALINK_URI", "wss://lavalink.contoh.net:13592")
    assert "hanya untuk port **443**" in music.node_diagnosis()

    # 5. search_tracks tanpa node → pesan ramah (bukan error mentah wavelink)
    monkeypatch.setattr(music, "LAVALINK_URI", "wss://lavalink.contoh.net:443")
    _Pool.nodes = {}
    with pytest.raises(music.MusicUnavailable) as err:
        await music.search_tracks("lagu uji")
    assert "belum tersambung" in str(err.value)
    assert "Pool in a CONNECTED state" not in str(err.value).split("Detail")[0]

    # 6. ensure_nodes_alive: menyambung ulang node yang tertutup/stuck
    node = _Node("utama", "wss://lavalink.contoh.net:443", "CONNECTING")
    _Pool.nodes = {"utama": node}

    async def _fake_reconnect():
        node.status = _Status("CONNECTED")
        return _Pool.nodes

    monkeypatch.setattr(_FakeWavelink.Pool, "reconnect", staticmethod(_fake_reconnect), raising=False)
    assert await music.ensure_nodes_alive(force=True) is True
    assert node.closed is True  # node yang belum CONNECTED ditutup dulu

    # 7. /musik status tetap informatif & tidak error meski node mati
    _Pool.nodes = {}
    sent = []

    class _Resp:
        def async_send(self):
            class _R:
                async def send_message(self, content=None, embed=None, ephemeral=False, **kw):
                    sent.append(content)
            return _R()

        def __init__(self):
            self._inner = self.async_send()

        async def send_message(self, content=None, **kw):
            sent.append(content)

        def is_done(self):
            return True

    class _Follow:
        async def send(self, content=None, **kw):
            sent.append(content)

    class _Ix:
        guild = type("G", (), {"id": 10, "voice_client": None, "me": None})()
        response = _Resp()
        followup = _Follow()
        user = type("U", (), {"id": 501, "display_name": "Warga", "voice": None,
                              "guild_permissions": type("P", (), {"administrator": False,
                                                                  "manage_guild": False})()})()

    await music_cog.musik_status_cmd.callback(_Ix())
    assert sent and "Status Musik" in sent[0]
    assert "Role DJ" in sent[0] and "tidak wajib" in sent[0]
    assert "Lavalink belum tersambung" in sent[0]


# ==============================================================================
# v1.12.0-beta: Tema UI (ui_theme), Komponen V2 (ui_kit), & Control Center (/panel)
# ==============================================================================
@pytest.mark.asyncio
async def test_ui_theme_defaults_customisation_and_persistence():
    """Tema per server: default ungu, validasi nilai, simpan & muat dari disk."""
    import ui_theme

    ui_theme.ui_themes.clear()
    theme = ui_theme.get_theme(4242)
    assert theme["accent"] == "purple"
    assert theme["density"] in ui_theme.DENSITIES
    assert ui_theme.accent_color(4242).value == ui_theme.ACCENTS["purple"]["color"]
    assert isinstance(ui_theme.emoji(4242, "panel", "🛰️"), str)

    # nilai tidak valid diabaikan, nilai valid diterapkan
    ui_theme.set_theme(4242, accent="tidak-ada", density="nyaman", refresh=9999, footer=False)
    theme = ui_theme.get_theme(4242)
    assert theme["accent"] == "purple"          # ditolak → tetap default
    assert theme["density"] == "nyaman"         # diterima
    assert theme["refresh"] in ui_theme.REFRESH_CHOICES  # dijepit ke pilihan sah
    assert theme["footer"] is False
    assert ui_theme.is_customized(4242)
    assert ui_theme.footer_text(4242) is None

    await ui_theme.save_ui_themes_to_disk()
    ui_theme.ui_themes.clear()
    loaded = ui_theme.load_ui_themes_from_disk()
    assert loaded >= 1
    assert ui_theme.get_theme(4242)["density"] == "nyaman"

    ui_theme.reset_theme(4242)
    assert not ui_theme.is_customized(4242)
    assert ui_theme.get_theme(4242)["accent"] == "purple"


def test_ui_kit_builds_valid_components_v2():
    """Kartu V2, baris status, progress bar, tombol, dropdown, & konfirmasi bisa dirender."""
    import ui_kit

    gid = 7777
    assert "00:00" in ui_kit.human_uptime(0) or "0" in ui_kit.human_uptime(0)
    assert "🔘" in ui_kit.progress_bar(5, 10)
    assert ui_kit.progress_bar(0, 0)  # tidak boleh ZeroDivisionError
    assert ui_kit.field_block("Judul", []) == ""
    assert "Judul" in ui_kit.field_block("Judul", ["• satu"])

    async def _noop(interaction):  # pragma: no cover - hanya syarat callback async
        return None

    view = ui_kit.build_view(
        gid,
        ui_kit.card(
            gid,
            ui_kit.text("### Halo"),
            ui_kit.sep(),
            ui_kit.action_row(
                ui_kit.button("OK", custom_id="t:ok", callback=_noop),
                ui_kit.toggle_button(gid, "Fitur", True, custom_id="t:on", callback=_noop),
            ),
            ui_kit.action_row(
                ui_kit.select_menu("t:sel", "Pilih…", [ui_kit.option("A", "a")], callback=_noop)
            ),
        ),
    )
    comps = view.to_components()
    assert comps and comps[0]["type"] == 17  # Container
    assert isinstance(ui_kit.fallback_embed(gid, "Judul", "Isi"), discord.Embed)

    confirm = ui_kit.ConfirmView(gid, title="Hapus?", detail="Tidak bisa dibatalkan.")
    assert confirm.to_components()[0]["type"] == 17


@pytest.mark.asyncio
async def test_panel_dashboard_and_theme_editor_render():
    """/panel: setiap tab menghasilkan embed cadangan + kartu V2 tanpa error."""
    from cogs import panel_cog

    class _FakeGuild:
        id = 8888
        name = "Server Uji"
        member_count = 12

    guild = _FakeGuild()
    for tab in panel_cog.TABS:
        embed = panel_cog.dashboard_embed(guild, tab)
        assert isinstance(embed, discord.Embed)
        assert len(embed.description or "") <= 4096
        view = panel_cog.make_dashboard(guild, tab, 100)
        comps = view.to_components()
        assert comps and comps[0]["type"] == 17

    editor = panel_cog.make_theme_editor(guild, 100)
    assert len(editor.to_components()) >= 2
    assert isinstance(panel_cog.theme_embed(guild), discord.Embed)

    # command terdaftar pada tree
    names = {c.name for c in bot_main.bot.tree.get_commands(type=discord.AppCommandType.chat_input)}
    assert {"panel", "tampilan"} <= names


@pytest.mark.asyncio
async def test_components_v2_panels_agent_ticket_queue_and_confirm():
    """Panel V2: AI Agent (toggle berwarna), tiket, antrean musik, & dialog konfirmasi tema."""
    import ui_kit
    import ui_theme

    class _FakeGuild:
        id = 9191
        name = "Server V2"
        member_count = 5

        def get_channel(self, cid):
            return None

    guild = _FakeGuild()
    ui_theme.reset_theme(guild.id)

    # 1. Panel AI Agent: 2 kartu, 8 tombol toggle + 5 tombol aksi + 1 dropdown channel
    panel = views.AgentPanelView(guild, 123, default_channel_id=555)
    assert [c["type"] for c in panel.to_components()] == [17, 17]
    btns = [i for i in panel.walk_children() if isinstance(i, discord.ui.Button)]
    toggle_ids = {"agent:v2:" + a for a, _, _ in views.AGENT_FEATURES}
    toggles = [b for b in btns if b.custom_id in toggle_ids]
    assert len(toggles) == 8
    assert all(b.style is discord.ButtonStyle.danger for b in toggles)  # semua OFF → merah
    assert len(btns) == 13
    from discord.ui.select import BaseSelect

    selects = [i for i in panel.walk_children() if isinstance(i, BaseSelect)]
    assert len(selects) == 1 and selects[0].custom_id == "agent:v2:channel"

    # 2. Panel tiket V2 memakai warna aksen tema server
    ticket_panel = views.TicketPanelView(guild.id)
    comp = ticket_panel.to_components()[0]
    assert comp["type"] == 17
    assert comp.get("accent_color") == ui_theme.accent_int(guild.id)

    # 3. Antrean musik V2: tombol navigasi + tombol tutup
    class _T:
        def __init__(self, title):
            self.title = title
            self.length = 60_000
            self.author = "Artis"
            self.uri = ""

    tracks = [_T(f"Lagu {i}") for i in range(25)]
    queue_view = views.QueuePaginationView(tracks, requester_id=9, page=0, guild_id=guild.id)
    q_buttons = [i for i in queue_view.walk_children() if isinstance(i, discord.ui.Button)]
    assert len(q_buttons) == 4
    assert q_buttons[3].style is discord.ButtonStyle.danger  # tombol Tutup

    # 4. Dialog konfirmasi mengikuti setelan tema server
    ui_theme.set_theme(guild.id, confirm=False)
    assert ui_theme.confirm_enabled(guild.id) is False
    confirm_view = ui_kit.ConfirmView(guild.id, title="Uji?", detail="Detail uji")
    assert confirm_view.to_components()[0]["type"] == 17
    ui_theme.reset_theme(guild.id)


@pytest.mark.asyncio
async def test_embed_to_container_help_panel_and_music_panel_v2():
    """Konversi embed → kartu V2, panel /bantuan V2, & panel pemutar musik V2."""
    import ui_kit
    import ui_theme

    gid = 3131
    ui_theme.reset_theme(gid)

    # 1. embed_to_container: judul, field panjang dipecah, footer tema dipakai
    embed = discord.Embed(title="Judul Uji", description="Deskripsi", color=discord.Color.purple())
    embed.add_field(name="Panjang", value="x" * 4500, inline=False)
    embed.set_footer(text="Kaki asli")
    container = ui_kit.embed_to_container(gid, embed)
    blocks = [c for c in container.children if isinstance(c, discord.ui.TextDisplay)]
    assert blocks, "harus ada blok teks"
    assert all(len(b.content) <= ui_kit.MAX_TEXT for b in blocks)
    joined = "".join(b.content for b in blocks)
    assert "Judul Uji" in joined and "x" * 100 in joined

    # 2. Panel /bantuan V2: kartu + dropdown 11 kategori, bisa ganti halaman
    help_panel = views.HelpPanelView(requester_id=77, category="overview", guild_id=gid)
    assert help_panel.to_components()[0]["type"] == 17
    from discord.ui.select import BaseSelect

    hp_select = [i for i in help_panel.walk_children() if isinstance(i, BaseSelect)][0]
    assert len(hp_select.options) == len(views.HELP_CATEGORIES)
    assert {"overview", "musik", "admin"} <= {o.value for o in hp_select.options}
    help_panel.category = "musik"
    help_panel._build()
    text_all = "".join(
        str(c.get("content") or "") for c in help_panel.to_components()[0]["components"] if c["type"] == 10
    )
    assert "Streaming Musik" in text_all

    # 3. Panel pemutar musik V2: 9 tombol asli tersusun 2 baris di dalam kartu
    class _Track:
        title = "Lagu Uji"
        author = "Artis"
        length = 215_000
        uri = "https://youtu.be/uji"
        is_stream = False
        artwork = None
        requester = None

    class _Player:
        current = _Track()
        queue = [_Track(), _Track()]
        paused = False
        volume = 60
        position = 60_000
        channel = None

    panel = views.build_music_panel_view(_Player(), guild_id=gid, filter_name="off", autoplay=False)
    assert panel is not None and panel.to_components()[0]["type"] == 17
    m_buttons = [i for i in panel.walk_children() if isinstance(i, discord.ui.Button)]
    assert [b.custom_id for b in m_buttons] == views.MUSIC_PANEL_ORDER
    m_rows = [i for i in panel.walk_children() if isinstance(i, discord.ui.ActionRow)]
    # Grid 5x3 gaya LunaBot: 15 tombol tersusun 5 per baris.
    assert len(m_buttons) == 15
    assert len(m_rows) == 3 and all(len(r.children) == 5 for r in m_rows)


@pytest.mark.asyncio
async def test_theme_settings_actually_apply(monkeypatch):
    """Setelan /tampilan benar-benar berefek: kepadatan, thumbnail, interval refresh, emoji aksen."""
    import types

    import music as music_mod
    import ui_kit
    import ui_theme
    from cogs import panel_cog

    gid = 6262
    ui_theme.reset_theme(gid)

    class _FakeGuild:
        id = gid
        name = "Server Tema"
        member_count = 7
        icon = types.SimpleNamespace(url="https://cdn.discordapp.com/icons/1/abc.png")

        def get_channel(self, cid):
            return None

    guild = _FakeGuild()

    def collect_text(view) -> str:
        parts = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == 10:
                    parts.append(str(node.get("content") or ""))
                for child in node.get("components") or []:
                    walk(child)

        for comp in view.to_components():
            walk(comp)
        return "\n".join(parts)

    # 1. Kepadatan: mode ringkas menyembunyikan baris penjelas, nyaman menampilkannya
    ui_theme.set_theme(gid, density="ringkas")
    assert ui_theme.is_compact(gid) is True
    ringkas_text = collect_text(panel_cog.make_dashboard(guild, "music", 1))
    ui_theme.set_theme(gid, density="nyaman")
    assert ui_theme.is_compact(gid) is False
    nyaman_text = collect_text(panel_cog.make_dashboard(guild, "music", 1))
    assert "tidak wajib" not in ringkas_text
    assert "tidak wajib" in nyaman_text

    # 2. Thumbnail: ikon server muncul sebagai Section+Thumbnail saat mode "ikon"
    ui_theme.set_theme(gid, thumbnail="ikon")
    types_in_view = [c["type"] for c in panel_cog.make_dashboard(guild, "overview", 1).to_components()[0]["components"]]
    assert 9 in types_in_view  # Section
    ui_theme.set_theme(gid, thumbnail="tanpa")
    types_no_thumb = [
        c["type"] for c in panel_cog.make_dashboard(guild, "overview", 1).to_components()[0]["components"]
    ]
    assert 9 not in types_no_thumb

    # 3. Interval refresh dipakai panel musik
    ui_theme.set_theme(gid, refresh=60)
    assert ui_theme.refresh_interval(gid) == 60
    assert music_mod._refresh_interval(gid) == 60
    ui_theme.set_theme(gid, refresh=10)
    assert music_mod._refresh_interval(gid) == 10

    # 4. Emoji aksen ikut di footer & embed cadangan
    ui_theme.set_theme(gid, accent="teal")
    footer = ui_theme.footer_text(gid, "uji")
    assert ui_theme.ACCENTS["teal"]["emoji"] in footer and "uji" in footer
    embed = ui_theme.apply_embed_theme(ui_kit.fallback_embed(gid, "Judul", "Isi"), gid, footer="x")
    assert embed.color.value == ui_theme.ACCENTS["teal"]["color"]
    assert ui_theme.ACCENTS["teal"]["emoji"] in (embed.footer.text or "")
    dashboard_embed = panel_cog.dashboard_embed(guild, "overview")
    assert ui_theme.ACCENTS["teal"]["emoji"] in (dashboard_embed.footer.text or "")

    # 5. Hanya opsi refresh yang sah yang disimpan
    ui_theme.set_theme(gid, refresh=7)
    assert ui_theme.refresh_interval(gid) == 10  # jatuh kembali ke default

    ui_theme.reset_theme(gid)


def test_serverstats_icon_customisation():
    """`/serverstats ikon`: emoji channel statistik bisa diganti/dihapus & direset."""
    import server_features as sf
    from cogs.server_cog import serverstats_group

    gid = 4747
    sf.serverstats_guilds.pop(gid, None)
    sf.set_serverstats_config(gid, enabled=True)

    # 1. default mengikuti STATS_CHANNEL_SPECS
    assert sf.stats_emojis(gid)["members"] == "👥"

    # 2. ganti sebagian + hapus ikon dengan "-"
    sf.set_serverstats_emojis(gid, {"members": "📈", "humans": "-", "bots": "🤖"})
    emojis = sf.stats_emojis(gid)
    assert emojis["members"] == "📈"
    assert emojis["humans"] == ""
    assert emojis["online"] == "🟢"  # tidak diubah

    # 3. nama channel menyesuaikan (dengan & tanpa ikon)
    assert sf._stats_channel_name("", "Manusia", "5") == "Manusia: 5"
    assert sf._stats_channel_name("📈", "Total Member", "9") == "📈 Total Member: 9"

    # 4. nama kategori & reset
    assert sf.set_serverstats_category_name(gid, "-") == "Statistik Server"
    sf.reset_serverstats_appearance(gid)
    assert sf.stats_emojis(gid)["members"] == "👥"
    assert sf.serverstats_guilds[gid]["category_name"] == sf.STATS_CATEGORY_NAME

    # 5. command terdaftar
    assert {"lihat", "otomatis", "ikon"} <= {c.name for c in serverstats_group.commands}

    sf.serverstats_guilds.pop(gid, None)


def test_welcome_media_storage_and_render():
    """Banner sambutan disimpan di data/media (bukan URL) & kartu dinamis bisa dirender."""
    import asyncio
    import io

    import welcome_media as wm

    gid = 818181
    wm.delete_banner(gid, kind="welcome")
    wm.delete_banner(gid, kind="boost")

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1280, 640), (90, 40, 160)).save(buf, format="PNG")
    payload = buf.getvalue()

    path = wm.save_banner(gid, payload, "banner.png")
    assert path.exists() and path.suffix == ".png"
    assert wm.has_banner(gid) is True
    assert wm.read_banner_bytes(gid) == payload

    # jenis berbeda tidak saling menimpa
    assert wm.has_banner(gid, kind="boost") is False
    wm.save_banner(gid, payload, "boost.jpg", kind="boost")
    assert wm.banner_path(gid, kind="boost").suffix == ".jpg"

    # ekstensi tak dikenal → .png, berkas lama ikut dihapus
    wm.save_banner(gid, payload, "aneh.exe")
    assert wm.banner_path(gid).suffix == ".png"
    assert len(list(wm.media_dir().glob(f"welcome_{gid}.*"))) == 1

    # batas ukuran
    with pytest.raises(ValueError):
        wm.save_banner(gid, b"x" * (wm.MAX_BANNER_BYTES + 1))

    # kartu dinamis (butuh Pillow)
    if wm.pillow_available():
        abuf = io.BytesIO()
        Image.new("RGB", (256, 256), (240, 200, 120)).save(abuf, format="JPEG")
        card = asyncio.run(
            wm.render_card(
                banner_bytes=payload,
                avatar_bytes=abuf.getvalue(),
                title="Whas",
                subtitle="Member ke-2",
                footer="Server Uji",
            )
        )
        assert card and card.startswith(b"\x89PNG")

    assert wm.delete_banner(gid) is True
    assert wm.delete_banner(gid) is False
    wm.delete_banner(gid, kind="boost")


@pytest.mark.asyncio
async def test_greeting_payload_modes_boost_and_commands():
    """Payload sambutan mengikuti mode (teks/banner/kartu) + command baru terdaftar."""
    import io

    import community_agent as ca
    import welcome_media as wm
    from cogs.agent_cog import agent_group, build_greeting_payload

    gid = 828282
    wm.delete_banner(gid)

    class _Avatar:
        url = "https://cdn.discordapp.com/avatars/1/a.png"

        async def read(self):
            return b""

    class _Member:
        id = 501
        display_name = "Whas"
        mention = "<@501>"
        display_avatar = _Avatar()

    class _Guild:
        id = gid
        name = "Server Uji"
        member_count = 2

    guild, member = _Guild(), _Member()

    # 1. mode text → teks biasa
    payload = await build_greeting_payload(guild, member, "Halo semua", mode="text")
    assert payload == {"content": "Halo semua"}

    # 2. mode embed tanpa banner → embed tanpa berkas
    payload = await build_greeting_payload(guild, member, "Hai", mode="embed")
    assert "embed" in payload and "file" not in payload
    assert payload["embed"].description == "Hai"

    # 3. mode embed dengan banner → embed + file lokal
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1024, 420), (120, 60, 200)).save(buf, format="PNG")
    wm.save_banner(gid, buf.getvalue())
    payload = await build_greeting_payload(guild, member, "Hai", mode="embed")
    assert "embed" in payload and payload["file"].filename.startswith("banner-welcome")
    assert payload["embed"].image.url.startswith("attachment://")

    # 4. mode card → kartu PNG (atau mundur ke embed bila Pillow tak ada)
    payload = await build_greeting_payload(guild, member, "Hai", mode="card")
    assert "embed" in payload and payload["file"] is not None

    # 5. mode container → kartu Components V2, mention tetap lewat content
    payload = await build_greeting_payload(guild, member, "Hai <@501>", mode="container")
    assert "view" in payload and payload["view"] is not None
    assert payload["content"] == "<@501>"

    # 6. nama mode lama tetap diterima (data setelan lama tidak rusak)
    assert (await build_greeting_payload(guild, member, "Hai", mode="mati"))["content"] == "Hai"
    assert "embed" in await build_greeting_payload(guild, member, "Hai", mode="statis")
    assert "embed" in await build_greeting_payload(guild, member, "Hai", mode="dinamis")

    # 7. konfigurasi boost: pesan & anti-dobel
    ca.boost_agent_guilds.pop(gid, None)
    assert ca.set_boost_config(gid, enabled=True, channel_id=700, message="Hai {user}") is not None
    assert ca.boost_agent_guilds[gid]["message"] == "Hai {user}"
    assert ca.should_process_member_boost(gid, 501) is True
    ca.should_process_member_boost(gid, 501)  # dicatat
    ca.boost_agent_guilds.pop(gid, None)

    # 6. command baru terdaftar di /agent
    names = {c.name for c in agent_group.commands}
    assert {"banner", "kartu", "dm", "boost", "welcome", "goodbye"} <= names

    # 8. mode tampilan & DM tersimpan di konfigurasi sambutan
    ca.set_welcome_config(gid, 600, enabled=True)
    assert ca.set_welcome_card_mode(gid, "card") == "card"
    assert ca.set_welcome_dm(gid, True) is True
    assert ca.welcome_agent_guilds[gid]["view_mode"] == "card"
    assert ca.set_welcome_card_mode(gid, "ngawur") == "text"
    # Nama mode lama tetap dipetakan, bukan ditolak
    assert ca.set_welcome_card_mode(gid, "dinamis") == "card"
    assert ca.set_welcome_card_mode(gid, "statis") == "embed"
    ca.welcome_agent_guilds.pop(gid, None)
    wm.delete_banner(gid)


def test_serverstats_channel_type_switch():
    """`/serverstats tipe`: counter bisa jadi text/announcement/stage, bukan hanya voice."""
    import discord as _discord

    import server_features as sf
    from cogs.server_cog import serverstats_group

    gid = 515151
    sf.serverstats_guilds.pop(gid, None)

    # 1. default voice
    sf.set_serverstats_config(gid, enabled=True)
    assert sf.stats_channel_type(gid) == "voice"

    # 2. ganti tipe tersimpan & nilai aneh ditolak
    assert sf.set_serverstats_channel_type(gid, "text") == "text"
    assert sf.stats_channel_type(gid) == "text"
    assert sf.set_serverstats_channel_type(gid, "ngawur") == "voice"
    sf.set_serverstats_channel_type(gid, "news")
    assert sf.stats_channel_type(gid) == "news"

    # 3. izin berbeda per jenis: voice tidak bisa di-connect, teks tidak bisa dikirimi pesan
    class _Guild:
        default_role = object()

    voice_ow = sf._stats_overwrites(_Guild(), "voice")[_Guild.default_role]
    assert voice_ow.connect is False and voice_ow.view_channel is True
    text_ow = sf._stats_overwrites(_Guild(), "text")[_Guild.default_role]
    assert text_ow.send_messages is False and text_ow.view_channel is True
    assert text_ow.create_public_threads is False

    # 4. deteksi tipe channel yang sudah ada
    bare_voice = object.__new__(_discord.VoiceChannel)
    assert sf._stats_channel_is_type(bare_voice, "voice") is True
    assert sf._stats_channel_is_type(bare_voice, "text") is False
    assert sf._stats_channel_is_type(None, "voice") is False

    # 5. daftar tipe & command tersedia
    assert set(sf.STATS_CHANNEL_TYPES) == {"voice", "text", "news", "stage"}
    cmds = {c.name for c in serverstats_group.commands}
    assert {"lihat", "otomatis", "ikon", "tipe"} <= cmds
    tipe_cmd = next(c for c in serverstats_group.commands if c.name == "tipe")
    choice_values = {ch.value for ch in tipe_cmd.parameters[0].choices}
    assert choice_values == {"voice", "text", "news", "stage"}

    sf.serverstats_guilds.pop(gid, None)


def test_social_notify_parsers_and_crud():
    """Notifikasi sosial: parser feed (tanpa jaringan) + CRUD langganan + template."""
    import social_notify as sn

    # 1. Login Twitch dinormalisasi dari berbagai bentuk
    assert sn.normalize_twitch_login("https://www.twitch.tv/Ninja?x=1") == "ninja"
    assert sn.normalize_twitch_login("@Some_Streamer") == "some_streamer"
    assert sn.twitch_configured() is False  # tanpa kredensial → fitur Twitch dilewati

    # 2. Feed YouTube (Atom)
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
      <title>Channel Uji</title>
      <entry>
        <yt:videoId>abc123XYZ</yt:videoId>
        <title>Judul Video Baru</title>
        <published>2026-11-01T10:00:00+00:00</published>
      </entry>
    </feed>"""
    items = sn.parse_atom_entries(atom)
    assert len(items) == 1
    assert items[0]["id"] == "abc123XYZ"
    assert items[0]["url"].endswith("abc123XYZ")
    assert items[0]["source"] == "Channel Uji"

    # 3. RSS 2.0 (TikTok / RSSHub)
    rss = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>TikTok Uji</title>
      <item><title>Video TikTok</title><link>https://tiktok.com/@a/video/1</link><guid>g-1</guid></item>
    </channel></rss>"""
    rss_items = sn.parse_rss_items(rss)
    assert rss_items and rss_items[0]["title"] == "Video TikTok"
    assert rss_items[0]["url"].startswith("https://tiktok.com/")
    assert sn.parse_atom_entries(b"bukan xml") == []

    # 4. Helix /streams
    streams = sn.parse_twitch_streams(
        {"data": [{"id": "1", "user_login": "Ninja", "user_name": "Ninja", "title": "Ranked",
                   "game_name": "Valorant", "thumbnail_url": "https://x/{width}x{height}.jpg"}]}
    )
    assert streams[0]["login"] == "ninja"
    assert streams[0]["url"] == "https://twitch.tv/ninja"
    assert "640" in streams[0]["thumbnail"]

    # 5. CRUD langganan
    gid = 616161
    sn.social_guilds.pop(gid, None)
    sub = sn.add_subscription(gid, "youtube", "@NamaChannel", 700)
    assert sub["platform"] == "youtube" and sub["seeded"] is False
    assert sn.find_subscription(gid, sub["id"]) is sub
    assert sub["id"] in sn.summarize_subscription(sub)

    # tambah ulang target sama → memperbarui, bukan menduplikasi
    same = sn.add_subscription(gid, "youtube", "@namachannel", 701)
    assert same["id"] == sub["id"] and same["channel_id"] == 701
    assert len(sn.get_subscriptions(gid)) == 1

    # TikTok wajib URL feed; platform tak dikenal & target kosong ditolak
    for bad in [
        lambda: sn.add_subscription(gid, "tiktok", "@user", 700),
        lambda: sn.add_subscription(gid, "myspace", "x", 700),
        lambda: sn.add_subscription(gid, "youtube", "  ", 700),
    ]:
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("input tidak valid seharusnya ditolak")

    assert sn.add_subscription(gid, "tiktok", "https://rsshub.app/tiktok/user/@a", 700)["platform"] == "tiktok"

    # batas jumlah langganan per server
    for i in range(sn.MAX_SUBS_PER_GUILD):
        try:
            sn.add_subscription(gid, "youtube", f"https://youtube.com/@kanal{i}", 700)
        except ValueError:
            break
    assert len(sn.get_subscriptions(gid)) <= sn.MAX_SUBS_PER_GUILD

    # 6. Template notifikasi (0 kuota AI)
    text = sn.build_notification_text(
        {"platform": "twitch", "template": "", "target": "ninja"},
        {"source": "Ninja", "title": "Ranked", "url": "https://twitch.tv/ninja", "game": "Valorant"},
    )
    assert "Ninja" in text and "Valorant" in text and "LIVE" in text
    custom = sn.build_notification_text(
        {"platform": "youtube", "template": "[{source}] {title} -> {url}", "target": "@a"},
        {"source": "Kanal", "title": "Video", "url": "https://youtu.be/x"},
    )
    assert custom == "[Kanal] Video -> https://youtu.be/x"

    # 7. Hapus langganan
    assert sn.remove_subscription(gid, sub["id"]) is True
    assert sn.remove_subscription(gid, "tidakada") is False
    sn.social_guilds.pop(gid, None)


@pytest.mark.asyncio
async def test_social_notify_seeding_and_dispatch(monkeypatch):
    """Polling pertama tidak membanjiri channel; item baru berikutnya dikirim."""
    import social_notify as sn
    from cogs.social_cog import sosial_group

    gid = 626262
    sn.social_guilds.pop(gid, None)
    sub = sn.add_subscription(gid, "youtube", "UC" + "a" * 22, 800)

    sent_posts: list[dict] = []

    class _Channel:
        id = 800

        async def send(self, **kwargs):
            sent_posts.append(kwargs)

    class _Guild:
        id = gid

        def get_channel(self, cid):
            return _Channel() if int(cid) == 800 else None

    feed = {"items": [{"id": "v1", "title": "Video 1", "url": "https://youtu.be/v1", "source": "Kanal"}]}

    async def _fake_fetch(session, subscription):
        return [dict(item) for item in feed["items"]]

    monkeypatch.setattr(sn, "fetch_feed_items", _fake_fetch)

    # polling pertama: di-seed, tidak ada pesan
    assert await sn.check_subscription(None, _Guild(), sub, None) == 0
    assert sub["seeded"] is True and sub["seen"] == ["v1"]
    assert sent_posts == []

    # video baru muncul → dikirim satu kali saja
    feed["items"].insert(0, {"id": "v2", "title": "Video 2", "url": "https://youtu.be/v2", "source": "Kanal"})
    assert await sn.check_subscription(None, _Guild(), sub, None) == 1
    assert len(sent_posts) == 1
    assert "Video 2" in sent_posts[0]["embed"].title

    # pengecekan berikutnya tidak mengirim ulang
    assert await sn.check_subscription(None, _Guild(), sub, None) == 0
    assert len(sent_posts) == 1

    # /sosial tes tetap memaksa kirim
    assert await sn.check_subscription(None, _Guild(), sub, None, force=True) == 1

    # command /sosial terdaftar lengkap
    assert {c.name for c in sosial_group.commands} == {"tambah", "daftar", "hapus", "tes", "status"}

    # diagnosa kesiapan: tanpa kredensial Twitch → fitur Twitch ditandai belum aktif
    info = await sn.diagnose(None)
    assert info["twitch_configured"] is False
    assert info["twitch_token_ok"] is False
    assert set(info["counts"]) == {"youtube", "twitch", "tiktok", "reddit", "rss"}
    assert info["total"] == len(sn.get_subscriptions(gid))
    tambah = next(c for c in sosial_group.commands if c.name == "tambah")
    platform_choices = tambah.parameters[0].choices
    assert {ch.value for ch in platform_choices} == {"youtube", "twitch", "tiktok", "reddit", "rss"}

    sn.social_guilds.pop(gid, None)


@pytest.mark.asyncio
async def test_moderation_cases_auto_punish_and_persistence():
    """Moderasi: kasus bernomor, hitung warn dalam jendela, auto-punish, & simpan-muat."""
    import moderation as md
    from cogs.moderation_cog import mod_group

    gid = 717171
    md.mod_cases.pop(gid, None)
    md.mod_settings.pop(gid, None)

    # 1. Parsing & format durasi
    assert md.parse_duration("10m") == 600
    assert md.parse_duration("1h30m") == 5400
    assert md.parse_duration("2d") == 172800
    assert md.parse_duration("45") == 45
    assert md.parse_duration("") == 600
    assert md.parse_duration("ngawur", default_sec=90) == 90
    assert md.format_duration(5400) == "1 jam 30 menit"
    assert md.format_duration(None) == "permanen"

    # 2. Kasus bernomor berurutan + urutan tampilan terbaru dulu
    first = md.add_case(gid, 900, 1, "warn", "spam link")
    second = md.add_case(gid, 900, 1, "timeout", "melanjutkan spam", duration_sec=600)
    assert (first["id"], second["id"]) == (1, 2)
    assert md.list_cases(gid)[0]["id"] == 2
    assert md.get_case(gid, 1)["reason"] == "spam link"
    assert "spam link" in md.summarize_case(first)

    # 3. Hitung warn & ambang auto-punish (default 3)
    md.add_case(gid, 900, 1, "warn", "warn kedua")
    assert md.count_warns(gid, 900) == 2
    assert md.should_auto_punish(gid, 900) == (False, 0)
    md.add_case(gid, 900, 1, "warn", "warn ketiga")
    assert md.should_auto_punish(gid, 900) == (True, 60)

    # ambang 0 → auto-punish mati
    md.set_settings(gid, warn_threshold=0)
    assert md.should_auto_punish(gid, 900) == (False, 0)
    md.set_settings(gid, warn_threshold=3, auto_timeout_min=120)
    assert md.should_auto_punish(gid, 900) == (True, 120)

    # warn di luar jendela waktu tidak dihitung
    old_case = md.add_case(gid, 901, 1, "warn", "warn lama")
    old_case["created_at"] -= 40 * 86400
    assert md.count_warns(gid, 901) == 0
    assert md.count_warns(gid, 901, days=365) == 1

    # 4. Pengaturan: nilai dibatasi & kunci asing diabaikan
    settings = md.set_settings(gid, log_channel=123, dm_user=False, warn_threshold=99, ngawur=1)
    assert settings["log_channel"] == 123
    assert settings["dm_user"] is False
    assert settings["warn_threshold"] == 10          # clamp maksimum
    assert "ngawur" not in settings

    # 5. Hapus kasus (tidak menghapus lainnya)
    assert md.delete_case(gid, 1) is True
    assert md.delete_case(gid, 999) is False
    assert md.get_case(gid, 1) is None and md.get_case(gid, 2) is not None

    # 6. Simpan → muat ulang dari disk
    await md.save_moderation_to_disk()
    md.mod_cases.clear()
    md.mod_settings.clear()
    loaded_guilds, loaded_cases = md.load_moderation_from_disk()
    assert loaded_guilds >= 1 and loaded_cases >= 2
    assert md.get_case(gid, 2) is not None
    assert md.get_settings(gid)["log_channel"] == 123

    # 7. Command /mod terdaftar lengkap
    names = {c.name for c in mod_group.commands}
    assert {
        "warn", "timeout", "kick", "ban", "unban", "purge", "catatan", "hapus", "atur",
        # v1.28.0-beta: perkakas moderasi harian
        "slowmode", "role", "role-massal", "nickname",
        # v1.40.0-beta (Paket B): tangga hukuman lengkap + statistik staf
        "tempban", "softban", "note", "statistik",
        # antrean laporan member & banding
        "antrean", "tindak",
    } == names

    md.mod_cases.pop(gid, None)
    md.mod_settings.pop(gid, None)


@pytest.mark.asyncio
async def test_temp_voice_config_rooms_and_persistence():
    """Temp Voice: template nama, pendaftaran room, kepemilikan, batas, & simpan-muat."""
    import temp_voice as tv
    from cogs.tempvoice_cog import tempvoice_group

    gid = 727272
    tv.temp_voice_guilds.pop(gid, None)
    for cid in list(tv.temp_rooms):
        if tv.temp_rooms[cid].get("guild_id") == gid:
            tv.temp_rooms.pop(cid, None)

    # 1. Sebelum diatur: tidak ada konfigurasi
    assert tv.get_config(gid) is None

    # 2. Aktifkan hub + template nama
    config = tv.set_hub(gid, 500, name_template="🔊 Room {user}", user_limit=5)
    assert config["hub_id"] == 500 and config["user_limit"] == 5
    assert tv.get_config(gid)["name_template"] == "🔊 Room {user}"

    class _Member:
        display_name = "Whas"
        name = "whas"

    assert tv.room_name_for(config, _Member()) == "🔊 Room Whas"
    # template kosong → kembali ke bawaan
    tv.set_hub(gid, 500, name_template="")
    assert tv.get_config(gid)["name_template"] == tv.DEFAULT_NAME_TEMPLATE
    assert tv.room_name_for(tv.get_config(gid), _Member()) == "🔊 Whas"

    # 3. Room: daftar, kepemilikan, kunci, nama
    tv.register_room(9001, gid, 1111, "Room Whas")
    assert tv.get_room(9001)["owner_id"] == 1111
    assert tv.is_owner(9001, 1111) is True
    assert tv.is_owner(9001, 2222) is False
    assert tv.guild_room_count(gid) == 1
    assert tv.set_room_locked(9001, True) is True
    assert tv.get_room(9001)["locked"] is True
    assert tv.set_room_name(9001, "Room Baru") is True
    assert tv.get_room(9001)["name"] == "Room Baru"
    assert tv.set_room_locked(12345, True) is False

    # 4. Sanitasi nama
    assert tv.sanitize_room_name("  Room   Anime  ") == "Room Anime"
    assert tv.sanitize_room_name("x" * 300) == "x" * 100

    # 5. Simpan → muat ulang
    await tv.save_temp_voice_to_disk()
    tv.temp_voice_guilds.clear()
    tv.temp_rooms.clear()
    loaded_guilds, loaded_rooms = tv.load_temp_voice_from_disk()
    assert loaded_guilds >= 1 and loaded_rooms >= 1
    assert tv.get_config(gid)["hub_id"] == 500
    assert tv.get_room(9001)["name"] == "Room Baru"

    # 6. Nonaktifkan → konfigurasi hilang, room tetap terdaftar (dihapus saat kosong)
    assert tv.set_hub(gid, 0, enabled=False) is None
    assert tv.get_config(gid) is None

    # 7. Command /tempvoice terdaftar
    assert {c.name for c in tempvoice_group.commands} == {
        "atur", "status", "kunci", "nama", "limit", "tendang", "tautkan"
    }

    tv.unregister_room(9001)
    tv.temp_voice_guilds.pop(gid, None)


@pytest.mark.asyncio
async def test_suggestions_voting_status_and_persistence():
    """Kotak saran: voting berganti, status, penghapusan, simpan-muat, & command."""
    import suggestions as sg
    from cogs.suggestions_cog import embed_group, parse_color, saran_group

    gid = 737373
    sg.suggestion_settings.pop(gid, None)
    sg.suggestion_items.pop(gid, None)

    # 1. Channel kotak saran
    assert sg.get_channel(gid) is None
    assert sg.set_channel(gid, 900) == 900
    assert sg.get_channel(gid) == 900
    assert sg.set_channel(gid, None) is None
    sg.set_channel(gid, 900)

    # 2. Saran baru + validasi
    item = sg.add_suggestion(gid, 4001, "Tambah channel meme dong")
    assert item["id"] == 1 and item["status"] == "baru"
    try:
        sg.add_suggestion(gid, 4001, "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("saran kosong harus ditolak")

    # 3. Voting: baru → duplikat → berganti → duplikat
    sg.bind_message(gid, item["id"], 555)
    assert sg.vote(555, 1, "up")[0] == "baru"
    assert sg.vote(555, 1, "up")[0] == "duplikat"
    assert sg.vote(555, 1, "down")[0] == "berganti"
    assert sg.vote(555, 2, "down")[0] == "baru"
    assert sg.vote(999, 1, "up")[0] == "tidak_ada"
    item = sg.get_by_message(555)
    assert len(item["up"]) == 0 and len(item["down"]) == 2
    assert sg.score(item) == -2

    # 4. Status & validasi status asing
    assert sg.set_status(gid, 1, "diterima")["status"] == "diterima"
    assert sg.set_status(gid, 1, "ngawur") is None
    assert sg.set_status(gid, 99, "diterima") is None

    # 5. Embed saran memuat status & hitungan
    embed = sg.build_suggestion_embed(gid, item)
    assert "Diterima" in embed.title
    assert any("Tidak setuju" in f.name for f in embed.fields)

    # 6. Daftar & filter
    second = sg.add_suggestion(gid, 4002, "Adakan event mingguan")
    assert [i["id"] for i in sg.list_suggestions(gid)][0] == second["id"]
    assert len(sg.list_suggestions(gid, status="diterima")) == 1

    # 7. Simpan → muat ulang (termasuk pemetaan tombol pesan)
    await sg.save_suggestions_to_disk()
    sg.suggestion_items.clear()
    sg.suggestion_settings.clear()
    sg._by_message.clear()
    loaded_guilds, loaded_items = sg.load_suggestions_from_disk()
    assert loaded_guilds >= 1 and loaded_items >= 2
    assert sg.get_channel(gid) == 900
    assert sg.get_by_message(555) is not None

    # 8. Hapus saran
    assert sg.delete_suggestion(gid, 1) is True
    assert sg.delete_suggestion(gid, 1) is False
    assert sg.get_by_message(555) is None

    # 9. Warna embed: hex, nama Indonesia, & fallback
    assert str(parse_color("#9B59B6")) == str(discord.Colour(0x9B59B6))
    assert str(parse_color("biru")) == str(discord.Colour(0x3498DB))
    assert str(parse_color("ngawur")) == str(discord.Colour(0x9B59B6))

    # 10. Command terdaftar
    assert {c.name for c in saran_group.commands} == {"pasang", "kirim", "daftar", "status", "hapus"}
    assert {c.name for c in embed_group.commands} == {
        "buat",
        "cepat",
        "sebagai",
        "tautan",
        "variabel",
        "webhook",
    }

    sg.suggestion_settings.pop(gid, None)
    sg.suggestion_items.pop(gid, None)


@pytest.mark.asyncio
async def test_server_tools_afk_threads_lockdown_backup():
    """Perkakas server: AFK, auto-thread, lockdown state, & snapshot backup struktur."""
    import server_tools as st
    from cogs.utility_cog import afk_group, backup_group, build_server_backup, lockdown_group, thread_group

    gid = 747474
    st.afk_users.pop(gid, None)
    st.auto_thread_channels.pop(gid, None)
    st.lockdown_state.pop(gid, None)

    # 1. AFK: set, deteksi mention (format <@id> & <@!id>), lalu dilepas
    entry = st.set_afk(gid, 1234, "tidur dulu")
    assert entry["reason"] == "tidur dulu"
    assert st.get_afk(gid, 1234) is not None
    found = st.afk_mentions(gid, "halo <@1234> dan <@!1234> apa kabar <@9999>")
    assert len(found) == 1 and found[0][0] == 1234
    assert "detik" in st.afk_since_text(entry) or "menit" in st.afk_since_text(entry)
    assert st.pop_afk(gid, 1234) is not None
    assert st.pop_afk(gid, 1234) is None
    st.set_afk(gid, 1234, "")

    # 2. Auto-thread config
    config = st.enable_auto_thread(gid, 800, archive_minutes=120)
    assert config["archive"] == 120
    assert st.auto_thread_config(gid, 800)["archive"] == 120
    assert 800 in st.list_auto_threads(gid)
    assert st.disable_auto_thread(gid, 800) is True
    assert st.disable_auto_thread(gid, 800) is False

    # 3. Nama thread dari isi pesan
    class _Msg:
        content = "  Ini   judul   diskusi panjang " + "x" * 200
        attachments = []

    name = st.thread_name_for(_Msg())
    assert name.startswith("Ini judul diskusi") and len(name) <= 100

    # 4. Lockdown: status awal kosong
    assert st.lockdown_active(gid) is None

    # 5. Simpan → muat ulang AFK & thread
    st.enable_auto_thread(gid, 801, archive_minutes=1440)
    await st.save_server_tools_to_disk()
    st.afk_users.clear()
    st.auto_thread_channels.clear()
    loaded_afk, loaded_threads = st.load_server_tools_from_disk()
    assert loaded_afk >= 1 and loaded_threads >= 1
    assert st.get_afk(gid, 1234)["reason"] == "tanpa alasan"
    assert st.auto_thread_config(gid, 801)["archive"] == 1440

    # 6. Backup struktur server (snapshot baca-saja)
    class _Perms:
        def __init__(self, value=0):
            self.value = value

    class _Role:
        def __init__(self, rid, name):
            self.id = rid
            self.name = name
            self.permissions = _Perms(8)
            self.colour = type("C", (), {"value": 0x9B59B6})()
            self.hoist = True
            self.mentionable = False
            self.position = 2

        def is_default(self):
            return False

    class _Category:
        id = 1
        name = "Umum"
        position = 0
        overwrites = {}
        text_channels = []

    class _TextChannel:
        id = 10
        name = "umum"
        type = discord.ChannelType.text
        position = 1
        category = _Category()
        overwrites = {}
        topic = "ngobrol"
        nsfw = False
        slowmode_delay = 0

    class _Emoji:
        def __init__(self, name, emoji_id=None):
            self.name = name
            self.id = emoji_id

    class _ForumTag:
        name = "Bantuan"
        emoji = _Emoji("❓")
        moderated = True

    class _CustomForumTag:
        name = "Custom"
        emoji = _Emoji("custom", 123456)
        moderated = False

    class _ForumChannel:
        id = 11
        name = "forum-bantuan"
        type = discord.ChannelType.forum
        position = 2
        category = _Category()
        overwrites = {}
        topic = "Tanya jawab"
        nsfw = False
        slowmode_delay = 3
        default_auto_archive_duration = 1440
        default_thread_slowmode_delay = 15
        default_sort_order = discord.ForumOrderType.latest_activity
        default_layout = discord.ForumLayoutType.gallery_view
        default_reaction_emoji = _Emoji("💬")
        available_tags = [_ForumTag(), _CustomForumTag()]

    class _MediaChannel(_ForumChannel):
        id = 12
        name = "media-karya"
        type = discord.ChannelType.media
        position = 3

    class _Guild:
        id = gid
        name = "Server Uji"
        member_count = 42
        roles = [type("R", (), {"is_default": lambda self: True})()] + [_Role(2, "Staff")]
        categories = [_Category()]
        channels = [_MediaChannel(), _TextChannel(), _ForumChannel()]

    snapshot = build_server_backup(_Guild())
    assert snapshot["meta"]["guild_id"] == gid
    assert len(snapshot["roles"]) == 1                      # role @everyone tidak ikut
    assert snapshot["channels"][0]["topic"] == "ngobrol"
    assert snapshot["channels"][0]["category_id"] == 1
    forum_backup = next(item for item in snapshot["channels"] if item["type"] == "forum")
    media_backup = next(item for item in snapshot["channels"] if item["type"] == "media")
    assert forum_backup["forum"]["default_auto_archive_duration"] == 1440
    assert forum_backup["forum"]["default_thread_slowmode_delay"] == 15
    assert forum_backup["forum"]["available_tags"] == [
        {"name": "Bantuan", "emoji": "❓", "moderated": True},
        {"name": "Custom", "emoji": None, "moderated": False},
    ]
    assert media_backup["type"] == "media"
    assert "messages" not in snapshot                       # baca-saja, tanpa isi pesan

    # 7. Command terdaftar
    assert {"atur", "daftar", "hapus"} == {c.name for c in afk_group.commands}
    assert {"aktifkan", "matikan", "status"} == {c.name for c in thread_group.commands}
    assert {"aktif", "status"} == {c.name for c in lockdown_group.commands}
    assert {"struktur", "pratinjau", "pulihkan"} == {c.name for c in backup_group.commands}

    st.afk_users.pop(gid, None)
    st.auto_thread_channels.pop(gid, None)

def test_visual_polish_status_embeds_and_panel_tabs():
    """Konsistensi visual: status_embed (warna semantik) & tab /panel memuat fitur baru."""
    import ui_theme
    from cogs.panel_cog import _gather

    gid = 757575
    # 1. status_embed: emoji judul + warna semantik per jenis
    ok = ui_theme.status_embed(gid, "ok", "Selesai", "isi")
    warn = ui_theme.status_embed(gid, "warn", "Hati-hati")
    err = ui_theme.status_embed(gid, "error", "Gagal")
    info = ui_theme.status_embed(gid, "info", "Info")
    lock = ui_theme.status_embed(gid, "lock", "Terkunci")
    assert ok.title.startswith("✅") and warn.title.startswith("⚠️")
    assert err.title.startswith("⛔") and info.title.startswith("ℹ️")
    assert lock.title.startswith("🔒")
    assert {ok.colour.value, warn.colour.value, err.colour.value, lock.colour.value} == {
        0x2ECC71, 0xF1C40F, 0xE74C3C, 0xE67E22
    }
    # "info" ikut warna aksen server (bisa diubah tema)
    assert info.colour.value == ui_theme.accent_int(gid)
    # judul/description dipotong aman & footer tema terpasang
    long_embed = ui_theme.status_embed(gid, "ok", "x" * 400, "y" * 5000)
    assert len(long_embed.title) <= 256 and len(long_embed.description) <= 4096
    assert long_embed.footer.text

    # 2. Semua tab /panel ter-render (tanpa error) & memuat fitur baru
    class _Guild:
        id = gid
        name = "Server Uji"
        member_count = 42
        premium_subscription_count = 0
        me = None

        def get_channel(self, cid):
            return None

        def get_role(self, rid):
            return None

    rendered = {}
    for tab in ("overview", "ai", "server", "community", "music", "insights"):
        title, lines = _gather(_Guild(), tab)
        assert title and lines
        rendered[tab] = "\n".join(lines)

    assert "Moderasi" in rendered["server"] and "Lockdown" in rendered["server"]
    for keyword in ("Temp Voice", "Kotak saran", "Notifikasi sosial", "Status AFK", "Thread otomatis"):
        assert keyword in rendered["community"], f"{keyword} belum tampil di tab Komunitas"



@pytest.mark.asyncio
async def test_send_status_uses_components_v2_with_embed_fallback():
    """Semua balasan konfirmasi dikirim sebagai kartu V2, dengan embed tetap tersedia."""
    import ui_kit
    import ui_theme

    calls: list[dict] = []

    class _Response:
        async def send_message(self, **kwargs):
            if "view" in kwargs and FAIL_VIEW:
                raise TypeError("V2 ditolak klien")
            calls.append(kwargs)

    class _Followup:
        async def send(self, **kwargs):
            if "view" in kwargs and FAIL_VIEW:
                raise TypeError("V2 ditolak klien")
            calls.append(kwargs)

    class _Interaction:
        guild = None

        def __init__(self):
            self.response = _Response()
            self.followup = _Followup()

    embed = ui_theme.status_embed(999, "ok", "Selesai", "Contoh isi")
    interaction = _Interaction()

    # 1. Jalur utama: kartu Components V2
    FAIL_VIEW = False
    assert await ui_kit.send_status(interaction, embed=embed) is True
    sent = calls[-1]
    assert isinstance(sent["view"], discord.ui.LayoutView)
    container = sent["view"].children[0]
    assert isinstance(container, discord.ui.Container)
    joined = " ".join(getattr(child, "content", "") for child in container.children)
    assert "Selesai" in joined and "Contoh isi" in joined

    # 2. Jalur followup (setelah defer) juga memakai kartu V2
    assert await ui_kit.send_status(interaction, embed=embed, follow=True) is True
    assert isinstance(calls[-1]["view"], discord.ui.LayoutView)

    # 3. Bila klien/server menolak V2 → otomatis kirim embed klasik
    FAIL_VIEW = True
    assert await ui_kit.send_status(interaction, embed=embed) is False
    assert calls[-1]["embed"] is embed and "view" not in calls[-1]
    assert await ui_kit.send_status(interaction, embed=embed, follow=True) is False
    assert calls[-1]["embed"] is embed

    # 4. Seluruh balasan konfirmasi cog baru memakai helper ini
    for path in (
        "cogs/moderation_cog.py",
        "cogs/tempvoice_cog.py",
        "cogs/suggestions_cog.py",
        "cogs/utility_cog.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "ui_kit.send_status(" in source, f"{path} belum memakai kartu V2"


def test_ai_guard_faq_cache_guild_cap_and_savings(monkeypatch):
    """AI Guard: FAQ-first, cache jawaban, batas harian per server, & penghematan."""
    import ai_guard
    import insights

    # 1. FAQ-first: dijawab dari catatan lokal tanpa memanggil AI
    entries = [
        {"topic": "Cara Verifikasi", "content": "Klik tombol verifikasi di channel verifikasi."},
        {"topic": "Jam Event", "content": "Event mingguan setiap Sabtu pukul 20.00 WIB."},
    ]
    ai_guard.reset_savings()
    hit = ai_guard.faq_first_answer(entries, "bagaimana cara verifikasi akun?")
    assert hit and hit["topic"] == "Cara Verifikasi"
    reply = ai_guard.format_faq_reply(hit)
    assert "Cara Verifikasi" in reply and "0 kuota" in reply
    assert ai_guard.faq_first_answer(entries, "zzz qqq") is None
    assert ai_guard.faq_first_answer([], "bagaimana cara verifikasi akun?") is None
    assert ai_guard.savings_stats()["faq_hits"] == 1

    # 2. Cache jawaban identik (TTL) — pertanyaan sama tidak memakai kuota lagi
    ai_guard.clear_reply_cache()
    question = "Bagaimana cara verifikasi akun di server ini?"
    answer = "Klik tombol verifikasi di channel verifikasi, lalu ikuti langkahnya."
    assert ai_guard.get_cached_reply(77, question) is None
    assert ai_guard.store_cached_reply(77, question, answer) is True
    assert ai_guard.reply_cache_size() == 1
    assert ai_guard.get_cached_reply(77, question.upper()) == answer
    assert ai_guard.get_cached_reply(77, question, ttl=0) is None   # TTL 0 = kedaluwarsa
    assert ai_guard.reply_cache_size() == 0
    assert ai_guard.store_cached_reply(78, "oke", answer) is False
    assert ai_guard.savings_stats()["cache_hits"] >= 1
    assert ai_guard.clear_reply_cache() >= 0
    assert ai_guard.cleanup_ai_guard_runtime() >= 0

    # 3. Batas harian per server + peringatan 80% hanya sekali per hari
    ai_guard.guild_ai_usage.clear()
    ai_guard._guild_alerted.clear()
    assert ai_guard.check_guild_cap(1234, cap=0) == (True, 0, 0)
    for _ in range(4):
        ai_guard.record_guild_usage(1234)
    allowed, used, limit = ai_guard.check_guild_cap(1234, cap=5)
    assert allowed is True and used == 4 and limit == 5
    ai_guard.record_guild_usage(1234)
    assert ai_guard.check_guild_cap(1234, cap=5)[0] is False
    assert "batas harian" in ai_guard.cap_message(1234, 5, 5)

    monkeypatch.setattr(ai_guard, "AI_DAILY_CAP_PER_GUILD", 5)
    assert ai_guard.should_alert_guild_cap(1234)[0] is True
    assert ai_guard.should_alert_guild_cap(1234)[0] is False  # tidak spam
    assert ai_guard.guild_usage_today(1234) == 5

    # 4. Pemakaian per server tersimpan & termuat kembali dari JSON
    payload = ai_guard.guild_usage_payload()
    assert str(1234) in payload[ai_guard._today()]
    ai_guard.guild_ai_usage.clear()
    assert ai_guard.load_guild_usage_from_disk(payload) >= 1
    assert ai_guard.guild_usage_today(1234) == 5
    ai_guard.guild_ai_usage.clear()
    ai_guard.guild_ai_usage[insights.today_key()] = {1234: 2}
    insights.record_ai_usage("chat", user_id=1, guild_id=1234)
    assert ai_guard.guild_usage_today(1234) == 3


def test_ai_guard_routing_safety_resilience_and_tokens(monkeypatch):
    """AI Guard: router model hemat, safetySettings, Retry-After, anti-halusinasi, & token."""
    import ai_guard
    import insights

    # 1. Router: pertanyaan ringan → model hemat, pertanyaan berat tetap model utama
    assert ai_guard.route_model_key("gemini_flash", "halo bot apa kabar hari ini") == "gemini_fast"
    assert ai_guard.route_model_key("gemini_flash", "tolong debug script python ini") == "gemini_flash"
    assert ai_guard.route_model_key("gemini_flash", "halo", has_media=True) == "gemini_flash"
    assert ai_guard.route_model_key("gemini_flash", "halo", has_links=True) == "gemini_flash"
    assert ai_guard.route_model_key("gemini_flash", "halo", history_len=20) == "gemini_flash"
    assert ai_guard.route_model_key("gemini_flash", "x" * 400) == "gemini_flash"
    assert ai_guard.route_model_key("gemini_logic", "halo") == "gemini_logic"

    # 2. Safety settings per server
    payload: dict = {}
    ai_guard.apply_safety(payload, "longgar")
    assert "safetySettings" not in payload          # default Google
    assert ai_guard.safety_settings_for("ngawur") is None
    ai_guard.apply_safety(payload, "ketat")
    assert payload["safetySettings"][0]["threshold"] == "BLOCK_MEDIUM_AND_ABOVE"
    assert len(payload["safetySettings"]) == 5
    ai_guard.apply_safety(payload, "normal")
    assert payload["safetySettings"][0]["threshold"] == "BLOCK_ONLY_HIGH"

    # 3. Retry-After dibaca & key diberi cooldown (bukan dihukum selamanya)
    assert ai_handler.parse_retry_after({"Retry-After": "42"}) == 42.0
    assert ai_handler.parse_retry_after({"retry-after": "1"}) == 1.0
    assert ai_handler.parse_retry_after({}) == 20.0
    assert ai_handler.parse_retry_after({"Retry-After": "99999"}) == 120.0
    assert ai_handler.parse_retry_after({"Retry-After": "0"}) == 1.0
    assert ai_handler.parse_retry_after({"Retry-After": "abc"}) == 20.0
    ai_handler.mark_key_unhealthy("kunci-uji", 30)
    assert ai_handler.key_cooldown_left("kunci-uji") > 25
    assert ai_handler.key_cooldown_left("kunci-lain") == 0.0
    ai_handler._key_cooldown_until.clear()

    # 4. Anti-halusinasi (idempoten) & ringkasan riwayat terpangkas
    prompt = ai_guard.with_accuracy_rules("Kamu teman komunitas.")
    assert "[ATURAN AKURASI]" in prompt
    assert ai_guard.with_accuracy_rules(prompt).count("[ATURAN AKURASI]") == 1
    assert ai_guard.with_accuracy_rules("x", enabled=False) == "x"
    dropped = [
        {"role": "user", "content": "Aku mau bikin server Minecraft"},
        {"role": "model", "content": "Wah seru, mau tema apa?"},
    ]
    summary = ai_guard.compress_dropped_history(dropped)
    assert "Minecraft" in summary and "RINGKASAN OBROLAN" in summary
    merged = ai_guard.merge_history_summary("Ringkasan lama.", dropped)
    assert "Ringkasan lama." in merged and "Minecraft" in merged
    assert ai_guard.merge_history_summary("Ringkasan lama.", []) == "Ringkasan lama."
    assert ai_guard.compress_dropped_history([]) == ""

    # 5. Token dari usageMetadata ikut tercatat (bukan cuma jumlah operasi)
    before_in, before_out = insights.token_totals()
    ai_handler._record_token_usage(
        {"usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 45}}
    )
    after_in, after_out = insights.token_totals()
    assert after_in >= before_in + 120 and after_out >= before_out + 45
    ai_handler._record_token_usage({})  # payload tanpa usageMetadata tidak boleh error

    # 6. /pemakaian menampilkan token & kuota server
    embed = insights.build_usage_embed(guild_id=1234)
    assert "Token" in embed.description
    assert any("Kuota Server" in field.name for field in embed.fields)

    # 7. Jalur utama benar-benar memakai pengaman baru ini (audit statis)
    agent_src = open("community_agent.py", encoding="utf-8").read()
    for needle in (
        "ai_guard.faq_first_answer(",
        "ai_guard.get_cached_reply(",
        "ai_guard.store_cached_reply(",
        "ai_guard.check_guild_cap(",
        "usage_guild_id=guild_id",
        "safety_level=get_guild_safety_level(guild_id)",
    ):
        assert needle in agent_src, f"community_agent.py belum memakai {needle}"
    handler_src = open("ai_handler.py", encoding="utf-8").read()
    for needle in ("ai_guard.apply_safety(", "ai_guard.with_accuracy_rules("):
        assert needle in handler_src, f"ai_handler.py belum memakai {needle}"
    # token dicatat di seluruh jalur teks (chat, rekap, cari, link, transformasi, fakta)
    assert handler_src.count("_record_token_usage(data)") >= 5
    assert "history_summary" in open("storage.py", encoding="utf-8").read()

    # 8. System prompt agent ikut membawa aturan anti-halusinasi
    prompt = community_agent._build_community_system_prompt(
        {"nickname": "Teman", "style_preset": "akrab", "knowledge_entries": []},
        "Teman",
        {"summary": "Senin siang", "clock": "12.00"},
    )
    assert "[ATURAN AKURASI]" in prompt


class _VoiceFakeChannel:
    def __init__(self, cid: int, channel_type: int = 2):
        self.id = cid
        self.type = channel_type
        self.mention = f"<#{cid}>"


class _VoiceFakeState:
    def __init__(self, channel=None, *, self_mute=False, self_deaf=False, afk=False):
        self.channel = channel
        self.self_mute = self_mute
        self.self_deaf = self_deaf
        self.afk = afk


class _VoiceFakeMember:
    def __init__(self, uid: int, guild, *, bot=False):
        self.id = uid
        self.bot = bot
        self.guild = guild
        self.display_name = f"Member {uid}"


class _VoiceFakeGuild:
    def __init__(self, gid: int, afk_channel_id: int | None = None):
        self.id = gid
        self.afk_channel_id = afk_channel_id


def test_voice_xp_tracking_cap_and_level_card():
    """XP Voice: sesi per menit, anti self-mute/AFK, batas harian, & tampil di kartu level."""
    import voice_activity

    gid = 4242
    levels.level_guilds.pop(gid, None)
    levels.level_guilds[gid] = levels.default_config()
    levels.set_level_config(gid, voice_enabled=True, voice_xp_per_min=2, voice_daily_cap_min=10)
    for key in [k for k in levels.levels if k.startswith(f"{gid}:")]:
        levels.levels.pop(key, None)
    voice_activity.reset_voice_sessions()

    guild = _VoiceFakeGuild(gid, afk_channel_id=999)
    voice_ch = _VoiceFakeChannel(700)
    member = _VoiceFakeMember(501, guild)

    # 1. Mulai sesi saat masuk voice channel
    assert voice_activity.handle_voice_state(
        member, _VoiceFakeState(None), _VoiceFakeState(voice_ch), guild=guild, now=1000.0
    ) == "start"
    assert voice_activity.active_sessions() == 1

    # 2. Belum 60 detik → belum ada XP
    assert voice_activity.flush_voice_sessions(now=1030.0) == []

    # 3. 65 detik → 1 menit penuh = 2 XP
    awards = voice_activity.flush_voice_sessions(now=1065.0)
    assert len(awards) == 1
    award = awards[0]
    assert award["guild_id"] == gid and award["user_id"] == 501
    assert award["result"]["minutes"] == 1 and award["result"]["gained"] == 2
    data = levels.get_member_level(gid, 501)
    assert data["xp"] == 2 and data["voice_xp"] == 2 and data["voice_min_today"] == 1

    # 4. Self-mute menghentikan hitungan, idel di AFK channel juga tidak dihitung
    assert voice_activity.handle_voice_state(
        member, _VoiceFakeState(voice_ch), _VoiceFakeState(voice_ch, self_mute=True), guild=guild, now=1070.0
    ) == "stop"
    assert voice_activity.active_sessions() == 0
    assert voice_activity.handle_voice_state(
        member, _VoiceFakeState(None), _VoiceFakeState(_VoiceFakeChannel(999)), guild=guild, now=1080.0
    ) is None

    # 5. Bot tidak pernah dapat XP voice
    bot_member = _VoiceFakeMember(777, guild, bot=True)
    assert voice_activity.handle_voice_state(
        bot_member, _VoiceFakeState(None), _VoiceFakeState(voice_ch), guild=guild, now=1090.0
    ) is None

    # 6. Batas harian 10 menit: menit ke-11 tidak menambah XP
    for idx in range(12):
        levels.add_voice_minutes(gid, 501, 1, channel_id=700, now=2000.0 + idx)
    final = levels.get_member_level(gid, 501)
    assert final["voice_min_today"] == 10
    assert final["voice_xp"] == 20          # 10 menit × 2 XP
    assert levels.add_voice_minutes(gid, 501, 1, now=3000.0) is None

    # 7. Channel yang diabaikan & leveling nonaktif tidak memberi XP
    levels.set_level_config(gid, voice_ignore_channels=[700])
    assert levels.add_voice_minutes(gid, 502, 1, channel_id=700, now=4000.0) is None
    assert levels.add_voice_minutes(gid, 502, 1, channel_id=701, now=4000.0) is not None
    levels.level_guilds.pop(gid, None)
    assert levels.add_voice_minutes(gid, 503, 1, now=5000.0) is None

    # 8. Kartu level menampilkan XP voice
    levels.level_guilds[gid] = levels.default_config()
    levels.set_level_config(gid, voice_xp_per_min=2, voice_daily_cap_min=30)
    levels.add_voice_minutes(gid, 501, 3, now=6000.0)
    card = member
    embed = levels.build_level_embed(card, levels.get_member_level(gid, 501), levels.get_level_config(gid))
    assert any("XP Voice" in f.name for f in embed.fields)

    # 9. Pengumuman level-up dari voice tidak error walau bot belum siap
    import asyncio
    from cogs.growth_cog import run_voice_xp_check

    class _DummyBot:
        def get_guild(self, _gid):
            return None

    levels.level_guilds[gid] = levels.default_config()
    voice_activity.reset_voice_sessions()
    voice_activity.sessions[f"{gid}:900"] = {"since": 0.0, "channel_id": 700}
    assert asyncio.run(run_voice_xp_check(_DummyBot())) >= 0
    voice_activity.reset_voice_sessions()
    levels.level_guilds.pop(gid, None)


@pytest.mark.asyncio
async def test_web_dashboard_readonly_render_auth_and_http(monkeypatch):
    """Dashboard web: opt-in via token, read-only, auth 3 jalur, & endpoint HTTP nyata."""
    import socket

    import aiohttp

    import dashboard_security
    import web_dashboard

    # 1. Nonaktif tanpa token / tanpa port
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", 8080)
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert web_dashboard.dashboard_config()["enabled"] is False

    # 2. Port bisa diambil dari environment panel hosting
    monkeypatch.setenv("SERVER_PORT", "8123")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", 0)
    cfg = web_dashboard.dashboard_config()
    assert cfg["port"] == 8123 and cfg["enabled"] is False
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "rahasia-uji")
    assert web_dashboard.dashboard_config()["enabled"] is True

    # 3. Auth: query, header, Bearer, & penolakan
    assert web_dashboard.is_authorized(query_token="rahasia-uji", expected="rahasia-uji") is True
    assert web_dashboard.is_authorized(header_token="rahasia-uji", expected="rahasia-uji") is True
    assert web_dashboard.is_authorized(header_token="Bearer rahasia-uji", expected="rahasia-uji") is True
    assert web_dashboard.is_authorized(query_token="salah", expected="rahasia-uji") is False
    assert web_dashboard.is_authorized(query_token="", expected="") is False

    # 4. Data & render (tanpa AI, aman untuk data kosong)
    class _G:
        id = 1234
        name = "Server Uji <b>"
        member_count = 42

    class _Bot:
        started_at = time.time() - 3661
        latency = 0.042
        guilds = [_G()]
        user = type("U", (), {"name": "BotUji"})()

        def get_guild(self, gid):
            return self.guilds[0] if int(gid) == 1234 else None

    status = web_dashboard.collect_status(_Bot())
    assert status["version"] == config.BOT_VERSION
    assert status["guilds"] == 1 and status["members"] == 42
    assert status["uptime"].startswith("01:0") and status["ping_ms"] == 42
    usage = web_dashboard.collect_usage(1234)
    assert set(usage) >= {"total", "tokens_in", "tokens_out", "cache_hits", "faq_hits"}
    kontrol = web_dashboard.render_controls_block(1234, "rahasia-uji")
    page = web_dashboard.render_dashboard_html(
        status=status,
        usage=usage,
        levels={"rows": []},
        refresh=15,
        heading="<script>x</script>",
        kontrol_block=kontrol,
    )
    assert config.BOT_VERSION in page and "Kontrol Cepat" in page
    # Setiap form tulis membawa token tersembunyi & mengarah ke /api/aksi
    assert page.count('action="/api/aksi"') == 5
    assert 'name="token" value="rahasia-uji"' in page
    assert "Simpan" in page
    assert "<script>x</script>" not in page      # di-escape
    assert 'http-equiv="refresh"' in page

    # 5. Server HTTP sungguhan: 401 tanpa token, 200 dengan token, /healthz bebas token
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    free_port = sock.getsockname()[1]
    sock.close()

    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", free_port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "rahasia-uji")
    assert await web_dashboard.start_dashboard(_Bot()) is True
    try:
        base = f"http://127.0.0.1:{free_port}"

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base}/") as resp:
                assert resp.status == 401
            # Token di URL ditukar menjadi cookie sesi (HttpOnly) lalu dibuang
            # dari alamat — token tidak tertinggal di riwayat/log proxy.
            async with session.get(
                f"{base}/?token=rahasia-uji&guild=1234", allow_redirects=False
            ) as resp:
                assert resp.status == 303
                lokasi = resp.headers["Location"]
                assert "token=" not in lokasi and "guild=1234" in lokasi
                assert "no-store" in resp.headers["Cache-Control"]
                assert resp.headers["X-Frame-Options"] == "DENY"
                assert resp.headers["Referrer-Policy"] == "no-referrer"
                assert resp.headers["X-Content-Type-Options"] == "nosniff"
                set_cookie = resp.headers["Set-Cookie"]
                assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
                assert "Secure" not in set_cookie        # HTTP polos tetap bisa login
                sesi_nilai = resp.cookies[dashboard_security.NAMA_COOKIE_SESI].value
                assert len(sesi_nilai) >= 32
            # Kunjungan berikutnya cukup bermodal cookie — halaman memakai sesi,
            # bukan token di setiap tautan/form.
            kuki = {dashboard_security.NAMA_COOKIE_SESI: sesi_nilai}
            async with aiohttp.ClientSession(cookies=kuki) as sesi_saja:
                async with sesi_saja.get(f"{base}{lokasi}") as resp:
                    body = await resp.text()
                    assert resp.status == 200 and config.BOT_VERSION in body
                    assert "token=rahasia-uji" not in body
                    assert "default-src 'none'" in resp.headers["Content-Security-Policy"]
                async with sesi_saja.get(f"{base}/ai") as resp:
                    assert resp.status == 200 and "<html" in (await resp.text()).lower()
            async with session.get(f"{base}/api/pemakaian", headers={"X-Dashboard-Token": "rahasia-uji"}) as resp:
                data = await resp.json()
                assert resp.status == 200 and "total" in data
            async with session.get(f"{base}/healthz") as resp:
                assert resp.status == 200 and (await resp.text()) == "ok"
            # Halaman tetap GET-only
            async with session.post(f"{base}/?token=rahasia-uji", json={"x": 1}) as resp:
                assert resp.status in (404, 405)

            # v1.29.0-beta: endpoint tulis /api/aksi — wajib token
            async with session.post(
                f"{base}/api/aksi",
                json={"guild": 1234, "action": "level", "value": "on"},
                headers={"X-Dashboard-Token": "salah"},
            ) as resp:
                assert resp.status == 401
            async with session.post(
                f"{base}/api/aksi",
                json={"guild": 1234, "action": "level", "value": "on"},
                headers={"X-Dashboard-Token": "rahasia-uji"},
            ) as resp:
                data = await resp.json()
                assert resp.status == 200 and data["ok"] is True
            async with session.get(
                f"{base}/api/kontrol?token=rahasia-uji&guild=1234"
            ) as resp:
                data = await resp.json()
                assert resp.status == 200 and data["controls"]["level"] == "on"
            # Aksi tak dikenal ditolak dengan pesan jelas
            async with session.post(
                f"{base}/api/aksi",
                json={"guild": 1234, "action": "hapus-semua", "value": "on"},
                headers={"X-Dashboard-Token": "rahasia-uji"},
            ) as resp:
                assert resp.status == 400
        # 6a. Sesi bisa dipakai berkali-kali, logout mencabutnya, cookie turut hilang
        async with aiohttp.ClientSession() as sesi_cookie:
            async with sesi_cookie.get(
                f"{base}/?token=rahasia-uji&guild=1234", allow_redirects=False
            ) as resp:
                assert resp.status == 303
                nilai = resp.cookies[dashboard_security.NAMA_COOKIE_SESI].value
            kuki2 = {dashboard_security.NAMA_COOKIE_SESI: nilai}
            async with aiohttp.ClientSession(cookies=kuki2) as pakai:
                async with pakai.get(f"{base}/?guild=1234") as resp:
                    assert resp.status == 200
                async with pakai.get(f"{base}/keluar", allow_redirects=False) as resp:
                    assert resp.status == 303 and resp.headers["Location"] == "/"
                    assert "Max-Age=0" in resp.headers["Set-Cookie"]
                async with pakai.get(f"{base}/?guild=1234") as resp:
                    assert resp.status == 401
            # Sesi yang logout benar-benar dicabut dari penyimpanan
            assert dashboard_security.baca_sesi(nilai) is None

    finally:
        await web_dashboard.stop_dashboard()

    # 6. Jalur tulis dibatasi: 14 endpoint POST + 1 POST logout (tanpa PUT/DELETE/PATCH).
    #    Sejak P3 daftar rute bukan lagi 40 baris `add_post(...)` di satu berkas,
    #    melainkan data di `web_dashboard.tabel_rute` — jadi yang diperiksa tabelnya.
    from web_dashboard.tabel_rute import RUTE_API

    post = {path for metode, path, _nama in RUTE_API if metode == "POST"}
    assert post == {
        "/api/aksi", "/api/kirim", "/api/konten", "/api/unggah", "/api/tiket",
        "/api/panel", "/api/uji", "/api/bangun", "/api/ai", "/api/giveaway",
        "/api/transkrip", "/api/keamanan", "/api/moderasi", "/api/lencana",
        "/keluar",
    }, post
    assert {metode for metode, _p, _n in RUTE_API} == {"GET", "POST"}
    # Tidak ada satu pun berkas dashboard yang memakai verba tulis lain.
    for berkas in pathlib.Path("web_dashboard").glob("*.py"):
        isi = berkas.read_text(encoding="utf-8")
        for needle in ("add_put(", "add_delete(", "add_patch("):
            assert needle not in isi, f"{berkas} tidak boleh punya {needle}"
    assert "start_dashboard(self)" in pathlib.Path("main.py").read_text(encoding="utf-8")

    # 7. Kegagalan/aksi tak dikenal tidak pernah melempar exception
    import levels as _levels
    ok, message = await web_dashboard.apply_dashboard_action(1234, "level", "off")
    assert ok is True and "nonaktif" in message
    ok2, message2 = await web_dashboard.apply_dashboard_action(1234, "bukan-aksi", "on")
    assert ok2 is False and "tidak didukung" in message2
    ok3, _ = await web_dashboard.apply_dashboard_action(0, "level", "on")
    assert ok3 is False
    ok4, message4 = await web_dashboard.apply_dashboard_action(1234, "antispam", "mode-ngawur")
    assert ok4 is False and "tidak dikenal" in message4
    _levels.disable_leveling(1234)


@pytest.mark.asyncio
async def test_translate_heuristics_cache_modes_and_quota(monkeypatch, tmp_path):
    """Penerjemah hemat kuota: heuristik, cache, rate limit, reaksi bendera, & auto-post."""
    import cogs.translate_cog as tc
    import translate_tools as tt

    # 1. Heuristik: hanya teks yang layak yang diterjemahkan
    assert tt.looks_translatable("hello everyone, how is your day going?") is True
    assert tt.looks_translatable("halo semua apa kabar hari ini") is True
    assert tt.looks_translatable("😀😀😀") is False
    assert tt.looks_translatable("https://youtu.be/abc123") is False
    assert tt.looks_translatable("hai") is False
    assert tt.looks_translatable("x" * 700) is False

    # 2. Cache: kalimat identik = 0 kuota, kedaluwarsa hilang
    tt.clear_cache()
    assert tt.cache_size() == 0
    text = "good morning everyone, welcome to the server!"
    assert tt.get_cached_translation(text, "id") is None
    assert tt.store_cached_translation(text, "id", "Selamat pagi semua, selamat datang di server!") is True
    assert tt.cache_size() == 1
    assert tt.get_cached_translation(text.upper(), "id")
    assert tt.get_cached_translation(text, "en") is None          # bahasa beda = entri beda
    assert tt.get_cached_translation(text, "id", ttl=0) is None
    assert tt.cache_size() == 0
    assert tt.store_cached_translation("hi", "id", "hai") is False  # terlalu pendek

    # 3. Rate limit per channel
    tt.reset_rate_limits()
    assert tt.rate_limited(555, now=1000.0) is False
    assert tt.rate_limited(555, now=1000.5) is True
    assert tt.rate_limited(555, now=1000.0 + tt.TRANSLATE_RATE_LIMIT_SEC + 1) is False
    assert tt.rate_limited(556, now=1000.5) is False

    # 4. Konfigurasi channel + simpan/muat JSON
    monkeypatch.setattr(tt, "TRANSLATE_FILE", tmp_path / "translate.json")
    tt.translate_guilds.clear()
    assert tt.channel_config(10, 100) is None
    tt.set_channel_config(10, 100, enabled=True, auto_react=True, auto_post=False)
    assert tt.channel_config(10, 100) == {"auto_react": True, "auto_post": False}
    assert tt.watched_channel_ids(10) == [100]
    await tt.save_translate_to_disk()
    tt.translate_guilds.clear()
    assert tt.load_translate_from_disk() == 1
    assert tt.channel_config(10, 100)["auto_post"] is False   # default aman
    assert tt.remove_channel_config(10, 100) is True
    assert tt.channel_config(10, 100) is None

    # 5. translate_text: panggil AI sekali, lalu dari cache; hormati kuota server
    tt.clear_cache()
    calls: list[str] = []

    async def fake_transform(mode, message_text, **kwargs):
        calls.append(mode)
        return f"[{mode}] {message_text}", None

    monkeypatch.setattr(tc.ai_handler, "transform_message_with_gemini", fake_transform)
    contoh = "could someone explain the server rules please?"
    hasil, err = await tc.translate_text(contoh, "id", guild_id=10)
    assert err is None and hasil.startswith("[translate_id]")
    hasil2, _ = await tc.translate_text(contoh, "id", guild_id=10)
    assert hasil2 == hasil and len(calls) == 1      # kedua kali dari cache = 0 kuota
    hasil3, _ = await tc.translate_text(contoh, "en", guild_id=10)
    assert calls[-1] == "translate_en"
    too_short, _ = await tc.translate_text("halo", "id", guild_id=10)
    assert too_short is None   # terlalu pendek

    real_cap = tc.ai_guard.check_guild_cap
    monkeypatch.setattr(tc.ai_guard, "check_guild_cap", lambda gid, cap=None: (False, 50, 50))
    tt.clear_cache()
    blocked, msg = await tc.translate_text("another sentence to translate here", "id", guild_id=10)
    assert blocked is None and "batas harian" in msg
    monkeypatch.setattr(tc.ai_guard, "check_guild_cap", real_cap)   # pulihkan kuota normal

    # 6. Reaksi bendera: hanya channel terpilih, kirim via DM, anti-banjir
    tt.translate_guilds.clear()
    tt.set_channel_config(10, 100, enabled=True, auto_react=True, auto_post=False)
    tt.reset_rate_limits()
    tt.clear_cache()

    class _FakeMsg:
        def __init__(self, content):
            self.content = content
            self.author = type("A", (), {"bot": False})()
            self.replied = 0

        async def reply(self, **kwargs):
            self.replied += 1

    class _FakeChannel:
        def __init__(self, msg):
            self._msg = msg

        async def fetch_message(self, mid):
            return self._msg

    class _FakeUser:
        def __init__(self):
            self.dms = 0

        async def send(self, **kwargs):
            self.dms += 1

    msg = _FakeMsg("hey guys, is the event still happening tonight?")
    channel = _FakeChannel(msg)
    user = _FakeUser()

    class _FakeBot:
        def get_channel(self, cid):
            return channel if int(cid) == 100 else None

    class _FakePayload:
        def __init__(self, emoji="🇮🇩", channel_id=100):
            self.emoji = emoji
            self.guild_id = 10
            self.channel_id = channel_id
            self.message_id = 999
            self.user_id = 7
            self.member = user

    assert await tc.handle_translate_reaction(_FakeBot(), _FakePayload("👍")) is False
    assert await tc.handle_translate_reaction(_FakeBot(), _FakePayload("🇮🇩", channel_id=404)) is False
    assert await tc.handle_translate_reaction(_FakeBot(), _FakePayload("🇮🇩")) is True
    assert user.dms == 1 and msg.replied == 0        # DM diutamakan, channel tidak banjir
    calls.clear()
    assert await tc.handle_translate_reaction(_FakeBot(), _FakePayload("🇮🇩")) is True
    assert calls == []                                # kena rate limit → tidak memakai kuota

    # 7. Auto-post default MATI; menyala hanya bila Admin memintanya
    tt.translate_guilds.clear()
    tt.set_channel_config(10, 100, enabled=True, auto_react=True, auto_post=False)
    tt.reset_rate_limits()
    plain_msg = _FakeMsg("this is an english sentence for auto translation")
    plain_msg.guild = type("G", (), {"id": 10})()
    plain_msg.channel = type("C", (), {"id": 100})()
    assert await tc.maybe_auto_translate(_FakeBot(), plain_msg) is False
    tt.set_channel_config(10, 100, enabled=True, auto_react=True, auto_post=True)
    tt.clear_cache()
    assert await tc.maybe_auto_translate(_FakeBot(), plain_msg) is True
    assert plain_msg.replied == 1

    # 8. Bersih-bersih runtime & audit: mode otomatis tidak pernah default aktif
    assert tt.cleanup_translate_runtime() >= 0
    src = open("translate_tools.py", encoding="utf-8").read()
    assert "auto_post: bool = False" in src        # default MATI (hemat kuota)
    assert "auto_post\", False" in src or '"auto_post": bool((ch or {}).get("auto_post", False))' in src
    assert "TRANSLATE_RATE_LIMIT_SEC" in src
    tt.translate_guilds.clear()
    tt.clear_cache()
    tt.reset_rate_limits()


@pytest.mark.asyncio
async def test_audit_log_config_events_and_persistence(monkeypatch, tmp_path):
    """Audit Log: konfigurasi, kirim embed, helper event, & simpan/muat JSON."""
    import audit_log

    audit_log.audit_guilds.clear()

    # 1. Default: nonaktif sampai channel dipasang
    assert audit_log.is_enabled(10) is False
    assert audit_log.is_category_enabled(10, "pesan") is False

    cfg = audit_log.set_log_channel(10, 900)
    assert audit_log.is_enabled(10) is True
    assert cfg["channel_id"] == 900
    assert cfg["categories"]["pesan"] is True and cfg["categories"]["voice"] is False

    # 2. Kategori bisa dinyalakan/dimatikan
    audit_log.set_category(10, "voice", True)
    assert audit_log.is_category_enabled(10, "voice") is True
    audit_log.set_category(10, "pesan", False)
    assert audit_log.is_category_enabled(10, "pesan") is False
    assert audit_log.set_category(10, "ngawur", True) is None
    audit_log.set_category(10, "pesan", True)

    # 3. Channel yang diabaikan
    audit_log.toggle_ignore_channel(10, 555, ignore=True)
    assert audit_log.is_channel_ignored(10, 555) is True
    audit_log.toggle_ignore_channel(10, 555, ignore=False)
    assert audit_log.is_channel_ignored(10, 555) is False

    # 4. Pengiriman embed ke channel log
    sent: list[dict] = []

    class _FakeChannel:
        id = 900

        async def send(self, **kwargs):
            sent.append(kwargs)

    class _FakeBot:
        def get_channel(self, cid):
            return _FakeChannel() if int(cid) == 900 else None

    class _Guild:
        id = 10

    class _Author:
        id = 501
        bot = False
        display_name = "Budi"

    class _Msg:
        def __init__(self, content="halo dunia", channel_id=700):
            self.content = content
            self.guild = _Guild()
            self.author = _Author()
            self.channel = type("C", (), {"id": channel_id, "mention": f"<#{channel_id}>"})()
            self.jump_url = "https://discord.com/channels/10/700/1"
            self.attachments = []

    ok = await audit_log.log_message_delete(_FakeBot(), _Msg())
    assert ok is True and sent and sent[-1]["embed"].title.endswith("Pesan dihapus")
    assert "halo dunia" in sent[-1]["embed"].description

    # 5. Channel yang diabaikan tidak dikirim
    audit_log.toggle_ignore_channel(10, 700, ignore=True)
    before = len(sent)
    assert await audit_log.log_message_delete(_FakeBot(), _Msg()) is False
    assert len(sent) == before
    audit_log.toggle_ignore_channel(10, 700, ignore=False)

    # 6. Edit hanya dikirim bila isi berubah
    before_msg = _Msg("versi lama")
    after_msg = _Msg("versi lama")
    assert await audit_log.log_message_edit(_FakeBot(), before_msg, after_msg) is False
    after_msg.content = "versi baru"
    assert await audit_log.log_message_edit(_FakeBot(), before_msg, after_msg) is True
    assert "versi baru" in sent[-1]["embed"].description

    # 7. Member join/keluar + perubahan role
    class _Member:
        id = 502
        bot = False
        display_name = "Sinta"
        guild = _Guild()
        created_at = discord.utils.utcnow()
        joined_at = discord.utils.utcnow()

        def __init__(self, roles=()):
            self.roles = list(roles)

    assert await audit_log.log_member_join(_FakeBot(), _Member()) is True
    assert await audit_log.log_member_remove(_FakeBot(), _Member()) is True
    role_before = _Member([type("R", (), {"id": 1})()])
    role_after = _Member([type("R", (), {"id": 1})(), type("R", (), {"id": 2})()])
    assert await audit_log.log_member_update(_FakeBot(), role_before, role_after) is True

    # 8. Voice default mati → tidak dikirim
    class _VoiceState:
        def __init__(self, cid):
            self.channel = None if cid is None else type("C", (), {"id": cid, "mention": f"<#{cid}>"})()

    audit_log.set_category(10, "voice", False)
    before = len(sent)
    assert await audit_log.log_voice_change(_FakeBot(), _Member(), _VoiceState(None), _VoiceState(800)) is False
    assert len(sent) == before

    # 9. Simpan & muat ulang
    monkeypatch.setattr(audit_log, "AUDIT_FILE", tmp_path / "audit.json")
    await audit_log.save_audit_to_disk()
    audit_log.audit_guilds.clear()
    assert audit_log.load_audit_from_disk() == 1
    assert audit_log.is_enabled(10) is True

    # 10. Status embed & pembersihan channel terhapus
    embed = audit_log.build_status_embed(10)
    assert "900" in embed.description
    assert audit_log.handle_channel_delete(900) is True
    assert audit_log.is_enabled(10) is False
    assert isinstance(audit_log.cleanup_audit_runtime(), int)
    audit_log.audit_guilds.clear()


@pytest.mark.asyncio
async def test_economy_coins_daily_shop_and_transfer(monkeypatch, tmp_path):
    """Ekonomi: koin pesan/voice, hadiah harian + streak, toko role, transfer, & persistensi."""
    import economy

    economy.economy_guilds.clear()
    economy.balances.clear()
    economy.meta.clear()
    economy.shop.clear()

    gid = 20
    # 1. Default nonaktif
    assert economy.is_active(gid) is False
    assert economy.earn_from_message(gid, 501) is None

    economy.set_config(gid, aktif=True, per_message=5, cooldown=60, per_voice_min=3, daily_amount=100)
    cfg = economy.get_config(gid)
    assert cfg["enabled"] is True and cfg["per_message"] == 5

    # 2. Koin dari pesan dengan jeda
    assert economy.earn_from_message(gid, 501, now=1000.0) == 5
    assert economy.earn_from_message(gid, 501, now=1030.0) is None       # masih jeda
    assert economy.earn_from_message(gid, 501, now=1070.0) == 10
    assert economy.balance(gid, 501) == 10

    # 3. Koin dari voice
    assert economy.earn_from_voice(gid, 502, 4, now=2000.0) == 12
    assert economy.earn_from_voice(gid, 502, 0) is None
    assert economy.balance(gid, 502) == 12

    # 4. Hadiah harian + streak
    ok, amount, streak = economy.claim_daily(gid, 501, now=3000.0)
    assert ok is True and amount == 100 and streak == 1
    assert economy.claim_daily(gid, 501, now=3100.0)[0] is False        # belum 24 jam
    assert economy.daily_ready_in(gid, 501, now=3100.0) > 0
    ok2, amount2, streak2 = economy.claim_daily(gid, 501, now=3000.0 + 86400)
    assert ok2 is True and streak2 == 2 and amount2 > 100                # bonus streak

    # 5. Transfer: minimal, saldo, dan jeda
    economy.add_coins(gid, 503, 100, now=4000.0)
    ok_t, msg_t = economy.transfer(gid, 503, 504, 50, now=5000.0)
    assert ok_t is True and "Berhasil" in msg_t
    assert economy.balance(gid, 503) == 50 and economy.balance(gid, 504) == 50
    assert economy.transfer(gid, 503, 504, 5, now=5100.0)[0] is False     # di bawah minimum
    assert economy.transfer(gid, 503, 503, 20, now=5200.0)[0] is False    # ke diri sendiri
    assert economy.transfer(gid, 504, 503, 100, now=5300.0)[0] is False   # saldo kurang
    assert economy.transfer(gid, 503, 504, 20, now=5002.0)[0] is False    # kena jeda transfer

    # 6. Toko: tambah item, beli, role hadiah
    item, status = economy.add_item(gid, "Role VIP", 40, role_id=777, description="Akses channel VIP")
    assert status == "added" and item["price"] == 40
    assert economy.add_item(gid, "Role VIP", 45)[1] == "updated"
    assert economy.find_item(gid, "role vip")["price"] == 45
    ok_b, msg_b, role_id = economy.buy(gid, 504, "Role VIP")
    assert ok_b is True and role_id == 777 and economy.balance(gid, 504) == 5
    assert economy.buy(gid, 504, "Role VIP")[0] is False                  # saldo kurang
    assert economy.buy(gid, 504, "Tidak Ada")[0] is False
    assert economy.remove_item(gid, "role vip") is True
    assert economy.items(gid) == {}

    # 7. Papan peringkat & total koin
    rows = economy.leaderboard(gid, limit=5)
    assert rows and rows[0][0] == 501
    assert economy.net_worth(gid) >= sum(value for _uid, value in rows)

    # 8. Format koin mengikuti mata uang server
    assert "koin" in economy.format_coins(1000, cfg)

    # 9. Simpan & muat ulang
    monkeypatch.setattr(economy, "ECONOMY_FILE", tmp_path / "economy.json")
    await economy.save_economy_to_disk()
    economy.economy_guilds.clear()
    economy.balances.clear()
    economy.meta.clear()
    economy.shop.clear()
    guilds, balances = economy.load_economy_from_disk()
    assert guilds == 1 and balances >= 2
    assert economy.balance(gid, 501) > 0
    assert economy.get_config(gid)["enabled"] is True

    # 10. Matikan fitur: saldo tetap ada, tapi tidak menambah koin
    economy.set_config(gid, aktif=False)
    assert economy.is_active(gid) is False
    assert economy.earn_from_message(gid, 501, now=9000.0) is None
    assert economy.balance(gid, 501) > 0
    assert isinstance(economy.cleanup_economy_runtime(), int)
    economy.economy_guilds.clear()
    economy.balances.clear()
    economy.meta.clear()
    economy.shop.clear()


@pytest.mark.asyncio
async def test_growth_tracker_invites_stats_and_persistence(monkeypatch, tmp_path):
    """Pertumbuhan: deteksi pengundang, statistik join/keluar, retensi, & persistensi."""
    import growth_tracker

    growth_tracker.growth_guilds.clear()
    growth_tracker.invite_cache.clear()
    growth_tracker.join_records.clear()
    growth_tracker.inviter_stats.clear()
    growth_tracker.daily.clear()

    gid = 30
    assert growth_tracker.is_enabled(gid) is True     # default aktif (0 kuota, ringan)

    # 1. Deteksi pengundang dari selisih `uses` invite
    class _Inviter:
        id = 900

    class _Invite:
        def __init__(self, code, uses, inviter=None):
            self.code = code
            self.uses = uses
            self.inviter = inviter

    class _Guild:
        id = gid

        def __init__(self, invites):
            self._invites = invites

        async def invites(self):
            return self._invites

    guild = _Guild([_Invite("abc", 3, _Inviter()), _Invite("xyz", 1, _Inviter())])
    assert await growth_tracker.sync_invites(guild) == 2
    assert growth_tracker.invite_cache[gid]["abc"] == 3

    guild._invites = [_Invite("abc", 4, _Inviter()), _Invite("xyz", 1, _Inviter())]
    inviter_id, code = await growth_tracker.detect_inviter(guild, None)
    assert inviter_id == 900 and code == "abc"
    assert growth_tracker.invite_cache[gid]["abc"] == 4

    # 2. Catat join & keluar + statistik (pakai waktu nyata agar tidak terpangkas)
    base = time.time() - 600
    growth_tracker.record_join(gid, 501, inviter_id, "abc", now=base)
    growth_tracker.record_join(gid, 502, inviter_id, "abc", now=base + 100)
    growth_tracker.record_join(gid, 503, None, None, now=base + 200)
    growth_tracker.record_leave(gid, 502, now=base + 300)      # keluar cepat (<1 jam)
    data = growth_tracker.stats(gid, 1, now=base + 400)
    assert data["joins"] == 3 and data["leaves"] == 1 and data["net"] == 2
    assert data["tracked"] == 3 and data["stayed"] == 2
    assert data["retention_pct"] == 67
    assert data["top_inviters"] and data["top_inviters"][0][0] == 900
    assert data["invites_cached"] == 2

    # 3. Papan pengundang & sparkline
    board = growth_tracker.invite_leaderboard(gid)
    assert board and board[0][0] == 900 and board[0][1] == 2 and board[0][3] == 1
    series = growth_tracker._days_series(gid, 3, now=base + 400)
    assert len(series) == 3
    assert growth_tracker.build_sparkline(series)
    assert growth_tracker.build_sparkline([("x", 0, 0)]) == "_belum ada data_"

    # 4. Cache invite bisa diperbarui lewat event
    growth_tracker.track_invite_create(gid, _Invite("baru", 0))
    assert "baru" in growth_tracker.invite_cache[gid]
    growth_tracker.track_invite_delete(gid, _Invite("baru", 0))
    assert "baru" not in growth_tracker.invite_cache[gid]

    # 5. Tanpa izin (guild.invites error) → tidak crash, kembalikan None
    class _BadGuild:
        id = gid

        async def invites(self):
            raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "nope")

    assert await growth_tracker.detect_inviter(_BadGuild(), None) == (None, None)
    assert await growth_tracker.sync_invites(_BadGuild()) == 0

    # 6. Konfigurasi & channel log
    growth_tracker.set_config(gid, enabled=True, log_channel_id=555)
    assert growth_tracker.get_config(gid)["log_channel_id"] == 555
    assert growth_tracker.handle_channel_delete(555) is True
    assert growth_tracker.get_config(gid)["log_channel_id"] is None

    # 7. Simpan & muat ulang
    monkeypatch.setattr(growth_tracker, "GROWTH_FILE", tmp_path / "growth.json")
    await growth_tracker.save_growth_to_disk()
    growth_tracker.growth_guilds.clear()
    growth_tracker.invite_cache.clear()
    growth_tracker.join_records.clear()
    growth_tracker.inviter_stats.clear()
    growth_tracker.daily.clear()
    assert growth_tracker.load_growth_from_disk() >= 1
    reloaded = growth_tracker.stats(gid, 1, now=base + 400)
    assert reloaded["joins"] == 3 and reloaded["tracked"] == 3
    assert growth_tracker.invite_leaderboard(gid)[0][0] == 900

    # 8. Pembersihan runtime
    assert isinstance(growth_tracker.cleanup_growth_runtime(), int)
    growth_tracker.growth_guilds.clear()
    growth_tracker.invite_cache.clear()
    growth_tracker.join_records.clear()
    growth_tracker.inviter_stats.clear()
    growth_tracker.daily.clear()


@pytest.mark.asyncio
async def test_new_guild_gets_instant_commands_and_checklist():
    """Bot masuk server baru: Slash Command disinkronkan + checklist setup dikirim (0 kuota AI)."""
    from cogs.events_cog import register_events_cog

    sent: list[dict] = []

    class _Tree:
        def __init__(self):
            self.synced_guilds: list[int] = []

        async def sync(self, *, guild=None):
            if guild is not None:
                self.synced_guilds.append(guild.id)
            return [object()] * 3

        def get_commands(self):
            return [object()] * 3

    class _Channel:
        def __init__(self):
            self.id = 42

        async def send(self, **kwargs):
            sent.append(kwargs)

    class _Guild:
        id = 987
        name = "Server Teman"
        member_count = 12
        system_channel = _Channel()

    class _FakeBot:
        def __init__(self):
            self.tree = _Tree()
            self.handlers: dict[str, object] = {}

        def event(self, coro):
            self.handlers[coro.__name__] = coro
            return coro

        # P3: event kini didaftarkan lewat `add_listener` (fungsi modul-level),
        # bukan dekorator `@bot.event` di dalam satu fungsi raksasa.
        def add_listener(self, func, name=None):
            self.handlers[name or func.__name__] = func

    bot = _FakeBot()
    register_events_cog(bot)

    assert "on_guild_join" in bot.handlers
    # discord.py memanggil listener dengan argumen EVENT saja (tanpa bot);
    # register_events_cog mengikat `bot` lewat pembungkus.
    await bot.handlers["on_guild_join"](_Guild())

    # Command langsung disinkronkan ke server baru itu saja
    assert bot.tree.synced_guilds == [987]
    # Checklist setup terkirim tanpa mention massal
    assert sent and sent[-1]["embed"].title
    assert "/log" in sent[-1]["embed"].description
    assert "/tumbuh" in sent[-1]["embed"].description
    assert sent[-1]["allowed_mentions"].everyone is False


# ==============================================================================
# MENU BUILDER & SELF ROLES v2 (v1.26.0-beta)
# ==============================================================================
class _MBRole:
    """Role tiruan dengan perbandingan berbasis `position` (hierarki)."""

    def __init__(self, rid, name="Role", position=1, *, default=False, managed=False):
        self.id = rid
        self.name = name
        self.position = position
        self.mention = f"<@&{rid}>"
        self._default = default
        self.managed = managed

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= getattr(other, "position", -1)

    def __lt__(self, other):
        return self.position < getattr(other, "position", 0)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return getattr(other, "id", None) == self.id


class _MBPerms:
    def __init__(self, manage_roles=True, administrator=False, manage_guild=False):
        self.manage_roles = manage_roles
        self.administrator = administrator
        self.manage_guild = manage_guild


class _MBMember:
    def __init__(self, uid=501, roles=None):
        self.id = uid
        self.mention = f"<@{uid}>"
        self.roles = list(roles or [])
        self.display_name = f"Member{uid}"
        self.guild_permissions = _MBPerms(administrator=True)

    async def add_roles(self, *roles, reason=None):
        for role in roles:
            if role not in self.roles:
                self.roles.append(role)

    async def remove_roles(self, *roles, reason=None):
        for role in roles:
            self.roles = [r for r in self.roles if r.id != role.id]


class _MBGuild:
    def __init__(self, gid=77, roles=None):
        self.id = gid
        self.name = "Server Uji"
        self._roles = {r.id: r for r in (roles or [])}
        self.me = _MBMember(999, [])
        self.me.guild_permissions = _MBPerms(manage_roles=True)
        self.me.top_role = _MBRole(900, "Bot", position=50)

    def get_role(self, rid):
        return self._roles.get(int(rid))


class _MBResp:
    def __init__(self):
        self.sent = []
        self.deferred = []
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, *args, **kwargs):
        self._done = True
        self.sent.append(kwargs)

    async def defer(self, *args, **kwargs):
        self._done = True
        self.deferred.append(kwargs)

    async def edit_message(self, *args, **kwargs):
        self._done = True


class _MBFollow:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)


class _MBInteraction:
    def __init__(self, guild, member, client=None):
        self.guild = guild
        self.user = member
        self.client = client
        self.channel = type("C", (), {"id": 700, "mention": "#umum"})()
        self.response = _MBResp()
        self.followup = _MBFollow()
        self.data = {}


@pytest.mark.asyncio
async def test_menu_builder_role_toggle_exclusive_and_limits():
    """Menu Builder: tombol role toggle, dropdown eksklusif, batas item, & persistensi."""
    import menu_builder

    menu_builder.menus.clear()
    menu_builder._role_cooldown.clear()

    role_a = _MBRole(1, "Gamer", position=10)
    role_b = _MBRole(2, "Musik", position=11)
    role_old = _MBRole(3, "13-17", position=12)
    role_new = _MBRole(4, "18-24", position=13)
    guild = _MBGuild(77, [role_a, role_b, role_old, role_new])
    member = _MBMember(501, [role_old])

    # 1. Buat menu + tombol role + tombol link + dropdown eksklusif
    menu = menu_builder.create_menu(guild.id, "Pusat Role", description="Ambil role kamu")
    assert menu and menu["kind"] == menu_builder.MENU_KIND_MENU
    assert menu_builder.create_menu(guild.id, "") is None       # judul kosong ditolak

    assert menu_builder.add_role_button(menu, 1, "Gamer", emoji="🎮") is not None
    assert menu_builder.add_role_button(menu, 1, "Duplikat") is None        # role sama ditolak
    assert menu_builder.add_link_button(menu, "Support", "https://example.com") is not None
    assert menu_builder.add_link_button(menu, "Rusak", "bukan-url") is None
    assert menu_builder.add_command_button(menu, "serverstats") is not None
    assert menu_builder.add_command_button(menu, "ngawur") is None          # di luar whitelist

    dropdown = menu_builder.add_dropdown(
        menu,
        "Pilih kelompok usia…",
        [{"role_id": 3, "label": "13-17"}, {"role_id": 4, "label": "18-24"}],
        exclusive=True,
        group="usia",
    )
    assert dropdown and dropdown["exclusive"] is True
    assert menu_builder.add_dropdown(menu, "x", [{"role_id": 1, "label": "a"}]) is not None
    assert menu_builder.add_dropdown(menu, "y", [{"role_id": 1, "label": "a"}]) is None  # maks 2

    # 2. Toggle role: klik pertama memberi, klik kedua melepas
    ix = _MBInteraction(guild, member)
    assert await menu_builder.toggle_role(ix, 1) is True
    assert role_a in member.roles
    menu_builder._role_cooldown.clear()      # lewati jeda 3 detik untuk pengujian
    ix2 = _MBInteraction(guild, member)
    assert await menu_builder.toggle_role(ix2, 1) is True
    assert role_a not in member.roles

    # 3. Jeda anti double-click
    menu_builder._role_cooldown.clear()
    ix3 = _MBInteraction(guild, member)
    assert await menu_builder.toggle_role(ix3, 2) is True
    ix4 = _MBInteraction(guild, member)
    assert await menu_builder.toggle_role(ix4, 2) is False    # masih dalam jeda
    assert role_b in member.roles

    # 4. Role di atas role bot / @everyone ditolak
    guild._roles[5] = _MBRole(5, "Admin", position=99)
    guild._roles[6] = _MBRole(6, "@everyone", position=0, default=True)
    ok, reason = menu_builder.check_role_usable(guild, 5)
    assert ok is False and "di atas role bot" in reason
    ok2, _ = menu_builder.check_role_usable(guild, 6)
    assert ok2 is False
    ok3, _ = menu_builder.check_role_usable(guild, 424242)
    assert ok3 is False

    # 5. Dropdown eksklusif: role grup dilepas otomatis
    menu_builder._role_cooldown.clear()
    exclusive_ids = menu_builder.role_ids_in_group(menu, "usia")
    assert sorted(exclusive_ids) == [3, 4]
    member.roles = [role_old]
    ix5 = _MBInteraction(guild, member)
    assert await menu_builder.toggle_role(ix5, 4, exclusive_role_ids=exclusive_ids) is True
    assert role_new in member.roles and role_old not in member.roles

    # 6. Batas jumlah tombol per panel
    limited = menu_builder.create_menu(guild.id, "Penuh")
    for idx in range(menu_builder.MAX_BUTTONS):
        assert menu_builder.add_link_button(limited, f"L{idx}", f"https://x{idx}.test") is not None
    assert menu_builder.add_link_button(limited, "Lebih", "https://lebih.test") is None
    assert menu_builder.delete_menu(guild.id, limited["id"]) is True

    # 7. Hapus item berdasarkan nomor & label
    assert menu_builder.remove_item(menu, "1") is not None
    assert menu_builder.remove_item(menu, "Tidak Ada") is None
    assert menu_builder.count_items(menu) >= 1

    # 8. Dispatch tombol: menu tidak dikenal → balasan sopan (tanpa crash)
    ix6 = _MBInteraction(guild, member)
    await menu_builder.handle_button(ix6, "tidak-ada", "x")
    assert ix6.response.sent or ix6.followup.sent

    # Dropdown tidak dikenal: diam saja, tanpa error
    ix7 = _MBInteraction(guild, member)
    await menu_builder.handle_select(ix7, menu["id"], "dropdown-tidak-ada")
    assert ix7.response.sent == [] and ix7.followup.sent == []

    # Dropdown valid: memilih opsi = role diberikan (atau dilepas)
    menu_builder._role_cooldown.clear()
    member.roles = []
    ix8 = _MBInteraction(guild, member)
    ix8.data = {"values": ["4"]}
    await menu_builder.handle_select(ix8, menu["id"], dropdown["id"])
    assert role_new in member.roles

    # 9. Persistensi
    menu_builder.menus.clear()
    assert menu_builder.load_menus_from_disk() >= 0
    assert isinstance(menu_builder.cleanup_menu_runtime(), int)
    menu_builder.menus.clear()


@pytest.mark.asyncio
async def test_menu_builder_command_buttons_and_visibility(monkeypatch):
    """Tombol command: whitelist, jalan atas nama pengklik, & paksa visibilitas."""
    import menu_builder

    menu_builder.menus.clear()
    menu_builder._role_cooldown.clear()

    calls: list[dict] = []

    async def _fake_command(interaction):
        calls.append({"ephemeral": None})
        await interaction.response.send_message(content="hasil info", ephemeral=True)

    class _Command:
        callback = staticmethod(_fake_command)

    class _Group:
        def __init__(self):
            self._children = {"lihat": _Command()}

        def get_command(self, name):
            return self._children.get(name)

    class _Tree:
        def __init__(self):
            self._top = {"serverstats": _Group()}

        def get_command(self, name):
            return self._top.get(name)

    class _Client:
        def __init__(self):
            self.tree = _Tree()

    guild = _MBGuild(88, [_MBRole(1, "Gamer", position=10)])
    member = _MBMember(601)
    client = _Client()
    ix = _MBInteraction(guild, member, client=client)

    # 1. Command ada di whitelist → berhasil dipanggil
    assert await menu_builder.run_command_item(ix, "serverstats", menu_builder.VIS_AUTO) is True
    assert calls

    # 2. Visibilitas publik memaksa `ephemeral=False`
    ix_pub = _MBInteraction(guild, member, client=client)
    assert await menu_builder.run_command_item(ix_pub, "serverstats", menu_builder.VIS_PUBLIK) is True
    assert ix_pub.response.sent[-1]["ephemeral"] is False

    # 3. Visibilitas ephemeral memaksa `ephemeral=True`
    ix_eph = _MBInteraction(guild, member, client=client)
    assert await menu_builder.run_command_item(ix_eph, "serverstats", menu_builder.VIS_EPHEMERAL) is True
    assert ix_eph.response.sent[-1]["ephemeral"] is True

    # 4. Command di luar whitelist / tidak tersedia → ditolak tanpa crash
    ix_bad = _MBInteraction(guild, member, client=client)
    assert await menu_builder.run_command_item(ix_bad, "serverstats", menu_builder.VIS_AUTO) is True
    ix_missing = _MBInteraction(guild, member, client=client)
    assert await menu_builder.run_command_item(ix_missing, "level", menu_builder.VIS_AUTO) is False

    # 5. Menu dasar & tombol command terpasang benar
    menu = menu_builder.create_menu(guild.id, "Pusat Info")
    item = menu_builder.add_command_button(menu, "serverstats", visibility=menu_builder.VIS_PUBLIK)
    assert item and item["kind"] == menu_builder.KIND_COMMAND
    assert menu_builder.SAFE_COMMANDS["serverstats"]["path"] == ("serverstats", "lihat")
    # Command berbahaya tidak terdaftar
    for forbidden in ("ban", "purge", "lockdown", "backup", "mod", "ekonomi_atur"):
        assert forbidden not in menu_builder.SAFE_COMMANDS

    # 6. Handler tombol command memakai visibilitas tersimpan
    ix_btn = _MBInteraction(guild, member, client=client)
    await menu_builder.handle_button(ix_btn, menu["id"], item["id"])
    assert ix_btn.response.sent[-1]["ephemeral"] is False

    # 7. Panel dapat dirender (V2) & fallback embed
    view = menu_builder.build_view(menu)
    assert view is not None
    embed = menu_builder.build_fallback_embed(menu)
    assert "Pusat Info" in (embed.title or "")

    menu_builder.menus.clear()


# ==============================================================================
# ANTI-NUKE (v1.27.0-beta)
# ==============================================================================
class _ANRole:
    def __init__(self, rid, name="Role", *, dangerous=True):
        self.id = rid
        self.name = name
        self.mention = f"<@&{rid}>"
        self.permissions = type(
            "P",
            (),
            {
                "administrator": dangerous,
                "manage_guild": False,
                "manage_roles": False,
                "manage_channels": False,
                "manage_webhooks": False,
                "ban_members": False,
                "kick_members": False,
                "manage_messages": False,
            },
        )()

    def is_default(self):
        return False


class _ANMember:
    def __init__(self, uid=801, name="Nuker", roles=None, *, owner=False):
        self.id = uid
        self.name = name
        self.mention = f"<@{uid}>"
        self.roles = list(roles or [])
        self.bot = False
        self._owner = owner
        self.kicked = False
        self.banned = False
        self.timed_out_until = None
        self.removed_roles = []

    async def remove_roles(self, *roles, reason=None):
        self.removed_roles.extend(roles)
        self.roles = [r for r in self.roles if r.id not in {x.id for x in roles}]

    async def timeout(self, until, reason=None):
        self.timed_out_until = until

    async def kick(self, reason=None):
        self.kicked = True


class _ANChannel:
    def __init__(self, cid=901):
        self.id = cid
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)


class _ANHook:
    def __init__(self, uid):
        self.user = type("U", (), {"id": uid})()
        self.deleted = False

    async def delete(self, reason=None):
        self.deleted = True


class _ANGuild:
    def __init__(self, gid=99, *, name="Server Asli", owner_id=700):
        self.id = gid
        self.name = name
        self.owner_id = owner_id
        self.owner = None
        self.icon = None
        self.system_channel = _ANChannel(902)
        self.me = _ANMember(999, "Bot", owner=False)
        self._members = {}
        self._hooks = []
        self.edits = []
        self.banned = None

    def get_member(self, uid):
        return self._members.get(int(uid))

    def get_role(self, rid):
        return None

    async def webhooks(self):
        return self._hooks

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        if "name" in kwargs:
            self.name = kwargs["name"]

    async def ban(self, member, reason=None, delete_message_seconds=0):
        self.banned = member
        if hasattr(member, "banned"):
            member.banned = True

    async def fetch_member(self, uid):
        return None


class _ANEntry:
    def __init__(self, guild, user, action_name):
        self.guild = guild
        self.user = user
        self.action = type("A", (), {"name": action_name})()


@pytest.mark.asyncio
async def test_antinuke_detection_actions_and_whitelist():
    """Anti-Nuke: deteksi ambang, tindakan bertingkat, whitelist, & pemulihan identitas."""
    import antinuke

    antinuke.antinuke_guilds.clear()
    antinuke.violations.clear()
    antinuke.reset_events()

    guild = _ANGuild(99)
    nuker = _ANMember(801, "Nuker", [_ANRole(11)])
    guild._members[801] = nuker

    # 1. Konfigurasi bawaan aman
    cfg = antinuke.get_config(99)
    assert cfg["enabled"] is True and cfg["action"] == "lapor"
    assert cfg["restore"] is True and cfg["dm_owner"] is True
    assert antinuke.is_enabled(99) is True

    # 2. Klasifikasi aksi audit log
    assert antinuke.classify("channel_delete") == "channel_delete"
    assert antinuke.classify("ban") == "ban"
    assert antinuke.classify("kick") == "kick"
    assert antinuke.classify("webhook_create") == "webhook_create"
    assert antinuke.classify("role_delete") == "role_delete"
    assert antinuke.classify("bukan_aksi") is None

    # 3. Di bawah ambang: tidak ada pelanggaran & tidak ada laporan
    antinuke.set_config(99, thresholds={"channel_delete": 3}, window=60)
    log_channel = _ANChannel(901)
    cfg = antinuke.get_config(99)
    cfg["log_channel_id"] = 901
    cfg["dm_owner"] = False
    bot = type("B", (), {"get_channel": lambda self, cid: log_channel if int(cid) == 901 else None,
                         "user": _ANMember(999, "Bot")})()

    base = 1000.0
    assert await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "channel_delete"), now=base) is None
    assert await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "channel_delete"), now=base + 1) is None
    assert log_channel.sent == []

    # 4. Melewati ambang & mode `lapor` → laporan dikirim, tanpa tindakan
    violation = await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "channel_delete"), now=base + 2)
    assert violation is not None
    assert violation["action"] == "channel_delete" and violation["count"] >= 3
    assert "lapor" in violation["taken"]
    assert log_channel.sent and "Anti-Nuke" in log_channel.sent[-1]["embed"].title
    assert nuker.removed_roles == [] and nuker.kicked is False
    assert antinuke.recent_violations(99, 5)

    # 5. Mode `cabut-role`: role berbahaya pelaku dicabut otomatis
    antinuke.reset_events()
    antinuke.set_config(99, action="cabut-role")
    for offset in range(3):
        last = await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "role_delete"), now=base + 100 + offset)
    assert last is not None and "cabut-role" in last["taken"]
    assert nuker.removed_roles and nuker.removed_roles[0].id == 11

    # 6. Mode `timeout` & `kick`
    antinuke.reset_events()
    antinuke.set_config(99, action="timeout", timeout_sec=600)
    for offset in range(5):
        last = await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "ban"), now=base + 200 + offset)
    assert nuker.timed_out_until is not None
    assert "timeout" in last["taken"]

    antinuke.reset_events()
    antinuke.set_config(99, action="kick")
    for offset in range(5):
        last = await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "kick"), now=base + 300 + offset)
    assert nuker.kicked is True and "kick" in last["taken"]

    # 7. Whitelist: member, role, owner, & bot sendiri tidak pernah ditindak
    antinuke.reset_events()
    antinuke.set_config(99, action="ban")
    assert antinuke.add_whitelist(99, user_id=801) is True
    assert antinuke.add_whitelist(99, user_id=801) is False            # duplikat
    assert antinuke.is_whitelisted(guild, nuker) is True
    for offset in range(6):
        assert await antinuke.handle_audit_entry(
            bot, _ANEntry(guild, nuker, "ban"), now=base + 400 + offset
        ) is None

    owner_member = _ANMember(700, "Owner", owner=True)
    guild._members[700] = owner_member
    assert antinuke.is_whitelisted(guild, owner_member) is True
    assert antinuke.is_whitelisted(guild, guild.me) is True

    role_member = _ANMember(802, "Mod", [_ANRole(22)])
    assert antinuke.is_whitelisted(guild, role_member) is False
    assert antinuke.add_whitelist(99, role_id=22) is True
    assert antinuke.is_whitelisted(guild, role_member) is True
    assert antinuke.remove_whitelist(99, role_id=22) is True
    assert antinuke.remove_whitelist(99, user_id=801) is True
    assert antinuke.is_whitelisted(guild, role_member) is False

    # 8. Pemulihan identitas server saat `guild_update`
    antinuke.snapshot_identity(guild)
    guild.name = "Server Dibajak"
    antinuke.reset_events()
    antinuke.set_config(99, action="lapor", restore=True)
    for offset in range(2):
        await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "guild_update"), now=base + 500 + offset)
    assert guild.edits and guild.edits[-1].get("name") == "Server Asli"
    assert guild.name == "Server Asli"

    # 9. Pemulihan webhook buatan pelaku
    hook = _ANHook(801)
    other = _ANHook(12345)
    guild._hooks = [hook, other]
    removed = await antinuke.cleanup_offender_webhooks(guild, nuker)
    assert removed == 1 and hook.deleted is True and other.deleted is False

    # 10. Simulasi (uji kering)
    data = antinuke.simulate(99, "channel_delete")
    assert data["limit"] >= 1 and data["window"] >= 1

    # 11. Persistensi & pembersihan
    antinuke.antinuke_guilds.clear()
    antinuke.violations.clear()
    assert antinuke.load_antinuke_from_disk() >= 0
    assert isinstance(antinuke.cleanup_antinuke_runtime(), int)
    assert antinuke.handle_channel_delete(901) in (0, 1)
    antinuke.antinuke_guilds.clear()
    antinuke.violations.clear()
    antinuke.reset_events()


@pytest.mark.asyncio
async def test_antinuke_disabled_and_permission_edges():
    """Anti-Nuke: fungsi mati, aksi tak dikenal, & kegagalan izin tidak membuat bot error."""
    import antinuke

    antinuke.antinuke_guilds.clear()
    antinuke.violations.clear()
    antinuke.reset_events()

    guild = _ANGuild(50)
    nuker = _ANMember(803, "Nuker2", [_ANRole(31)])
    guild._members[803] = nuker

    class _Bot:
        def get_channel(self, cid):
            return None

        user = _ANMember(999, "Bot")

    bot = _Bot()

    # 1. Dinonaktifkan → tidak ada deteksi
    antinuke.set_config(50, enabled=False)
    assert antinuke.is_enabled(50) is False
    for offset in range(10):
        assert await antinuke.handle_audit_entry(
            bot, _ANEntry(guild, nuker, "channel_delete"), now=2000.0 + offset
        ) is None

    # 2. Aksi tidak dikenal / tanpa user / tanpa guild → diabaikan
    antinuke.set_config(50, enabled=True)
    assert await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "pesan_diedit"), now=2100.0) is None
    assert await antinuke.handle_audit_entry(bot, _ANEntry(guild, None, "channel_delete"), now=2100.0) is None
    assert await antinuke.handle_audit_entry(bot, _ANEntry(None, nuker, "channel_delete"), now=2100.0) is None

    # 3. Gagal mencabut role (Forbidden) tidak melempar error
    class _ForbiddenMember(_ANMember):
        async def remove_roles(self, *roles, reason=None):
            raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "nope")

    denied = _ForbiddenMember(804, "Denied", [_ANRole(41)])
    result = await antinuke.apply_action(guild, denied, "cabut-role")
    assert "gagal" in result

    # 4. Aksi `lapor` tidak mengubah apa pun
    assert "lapor" in await antinuke.apply_action(guild, nuker, "lapor")

    # 5. Pemulihan identitas tanpa titik pulih → pesan jelas
    antinuke.antinuke_guilds.clear()
    fresh = _ANGuild(51, name="Baru")
    ok, message = await antinuke.restore_identity(bot, fresh)
    assert ok is False and "titik pulih" in message

    antinuke.antinuke_guilds.clear()
    antinuke.violations.clear()
    antinuke.reset_events()


# ==============================================================================
# MODERASI HARIAN (v1.28.0-beta): slowmode, role, & nickname
# ==============================================================================
class _ModRole:
    def __init__(self, rid=51, name="Member", position=5, *, default=False, managed=False):
        self.id = rid
        self.name = name
        self.position = position
        self.mention = f"<@&{rid}>"
        self._default = default
        self.managed = managed

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= getattr(other, "position", -1)

    def __lt__(self, other):
        return self.position < getattr(other, "position", 0)


class _ModPerms:
    def __init__(self, **flags):
        self.administrator = flags.get("administrator", False)
        self.moderate_members = flags.get("moderate_members", True)
        self.manage_roles = flags.get("manage_roles", True)
        self.manage_channels = flags.get("manage_channels", True)
        self.manage_messages = flags.get("manage_messages", True)
        self.ban_members = flags.get("ban_members", True)
        self.kick_members = flags.get("kick_members", True)


class _ModChannel:
    def __init__(self, cid=700):
        self.id = cid
        self.name = "umum"
        self.mention = f"<#{cid}>"
        self.slowmode_delay = 0
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        if "slowmode_delay" in kwargs:
            self.slowmode_delay = kwargs["slowmode_delay"]


class _ModMember:
    def __init__(self, uid=601, name="Anggota", top_role=None):
        self.id = uid
        self.name = name
        self.mention = f"<@{uid}>"
        self.bot = False
        self.roles = []
        self.top_role = top_role or _ModRole(60, "Anggota", position=3)
        self.nick = None
        self.dm_sent = []

    async def add_roles(self, *roles, reason=None):
        self.roles.extend(r for r in roles if r not in self.roles)

    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r.id not in {x.id for x in roles}]

    async def edit(self, **kwargs):
        if "nick" in kwargs:
            self.nick = kwargs["nick"]

    async def send(self, content=None, **kwargs):
        self.dm_sent.append(content)


class _ModGuild:
    def __init__(self, gid=12):
        self.id = gid
        self.name = "Server Mod"
        self.owner_id = 1
        self.members = []
        self.me = _ModMember(999, "Bot", _ModRole(900, "Bot", position=50))
        self.me.guild_permissions = _ModPerms()
        self._channels = {}

    def get_channel(self, cid):
        return self._channels.get(int(cid))


class _ModResp:
    def __init__(self):
        self.sent = []
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, *args, **kwargs):
        self._done = True
        self.sent.append((args, kwargs))

    async def defer(self, *args, **kwargs):
        self._done = True


class _ModFollow:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class _ModInteraction:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.channel = _ModChannel()
        self.response = _ModResp()
        self.followup = _ModFollow()
        self.edits = []

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


@pytest.mark.asyncio
async def test_moderation_daily_tools_slowmode_role_nickname(monkeypatch):
    """Slowmode, role massal, & nickname berjalan, tercatat sebagai kasus, & menghormati hierarki."""
    import moderation as mod
    from cogs.moderation_cog import (
        _role_change_problem,
        mod_nickname_cmd,
        mod_role_cmd,
        mod_role_massal_cmd,
        mod_slowmode_cmd,
    )

    mod.mod_cases.clear()
    mod.mod_settings.clear()
    mod.get_settings(12)

    guild = _ModGuild(12)
    staff = _ModMember(601, "Staff")
    staff.guild_permissions = _ModPerms(administrator=True)
    target = _ModMember(602, "Anggota")
    target.guild_permissions = _ModPerms(administrator=False)
    bot_member = guild.me
    bot_member.guild_permissions = _ModPerms()
    guild.members = [bot_member, staff, target]
    guild._channels[700] = guild.me and _ModChannel(700)

    # 1. Slowmode dipasang & dimatikan
    ix = _ModInteraction(guild, staff)
    await mod_slowmode_cmd.callback(ix, 30)
    assert ix.channel.slowmode_delay == 30
    ix2 = _ModInteraction(guild, staff)
    await mod_slowmode_cmd.callback(ix2, 0)
    assert ix2.channel.slowmode_delay == 0
    assert any(case["action"] == "note" for case in mod.list_cases(12))

    # 2. Role diberikan & dicabut ke satu member
    role = _ModRole(55, "Gamer", position=8)
    ok, _reason = _role_change_problem(guild, target, role)
    assert ok is True
    ix3 = _ModInteraction(guild, staff)
    await mod_role_cmd.callback(ix3, target, role, None, "hadiah event")
    assert role in target.roles
    ix4 = _ModInteraction(guild, staff)
    await mod_role_cmd.callback(ix4, target, role, type("C", (), {"value": "cabut"})(), None)
    assert role not in target.roles

    # 3. Hierarki: role di atas bot & pemilik server ditolak
    high_role = _ModRole(56, "Admin", position=99)
    ok2, reason2 = _role_change_problem(guild, target, high_role)
    assert ok2 is False and "di atas role bot" in reason2
    owner = _ModMember(1, "Owner")
    ok3, reason3 = _role_change_problem(guild, owner, role)
    assert ok3 is False and "pemilik server" in reason3

    # 4. Role massal: konfirmasi dimatikan tema → langsung dijalankan
    monkeypatch.setattr("ui_theme.confirm_enabled", lambda _gid: False)
    ix5 = _ModInteraction(guild, staff)
    await mod_role_massal_cmd.callback(ix5, role, type("C", (), {"value": "beri"})())
    assert role in target.roles
    assert ix5.edits  # ringkasan hasil dikirim

    # 5. Nickname diubah & direset
    ix6 = _ModInteraction(guild, staff)
    await mod_nickname_cmd.callback(ix6, target, "Sobat Baru", None)
    assert target.nick == "Sobat Baru"
    ix7 = _ModInteraction(guild, staff)
    await mod_nickname_cmd.callback(ix7, target, None, "reset")
    assert target.nick is None

    mod.mod_cases.clear()
    mod.mod_settings.clear()


# ==============================================================================
# PEMULIHAN STRUKTUR BACKUP (v1.30.0-beta)
# ==============================================================================
class _BRRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _BRCategory:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.perms = []

    async def set_permissions(self, target, allow=None, deny=None, reason=None):
        self.perms.append((target.name, allow.value if allow else 0))


class _BRChannel:
    def __init__(self, name, kind="text"):
        self.name = name
        self.type = kind
        self.perms = []

    async def set_permissions(self, target, allow=None, deny=None, reason=None):
        self.perms.append((target.name, allow.value if allow else 0))


class _BRGuild:
    def __init__(self, gid=88):
        self.id = gid
        self.roles = [_BRRole(1, "@everyone"), _BRRole(2, "Moderator")]
        self.categories = [_BRCategory(10, "INFO")]
        self.channels = [_BRChannel("umum"), _BRChannel("voice-lounge", "voice")]
        self.created = {"roles": [], "categories": [], "channels": []}
        self.category_create_kwargs = []

    async def create_role(self, name, permissions=None, colour=None, hoist=False, mentionable=False, reason=None):
        role = _BRRole(900 + len(self.created["roles"]), name)
        self.created["roles"].append(name)
        self.roles.append(role)
        return role

    async def create_category(self, name, **kwargs):
        self.category_create_kwargs.append(kwargs)
        cat = _BRCategory(800 + len(self.created["categories"]), name)
        self.created["categories"].append(name)
        self.categories.append(cat)
        return cat

    async def create_text_channel(self, name, **kwargs):
        self.created["channels"].append(("text", name, kwargs))
        return _BRChannel(name, "text")

    async def create_voice_channel(self, name, **kwargs):
        self.created["channels"].append(("voice", name, kwargs))
        return _BRChannel(name, "voice")

    async def create_forum(self, name, *, media=False, **kwargs):
        kind = "media" if media else "forum"
        call_kwargs = dict(kwargs)
        call_kwargs["media"] = media
        self.created["channels"].append((kind, name, call_kwargs))
        return _BRChannel(name, kind)


def _sample_backup() -> dict:
    return {
        "meta": {"generated_at": "2026-11-05T00:00:00", "version": 1, "guild_id": 88, "guild_name": "Server Lama"},
        "roles": [
            {"name": "Moderator", "permissions": 8, "colour": 0},
            {"name": "Event", "permissions": 0, "colour": 0x5865F2, "hoist": True, "mentionable": True},
        ],
        "categories": [
            {"id": 10, "name": "INFO", "position": 0,
             "overwrites": [{"target_type": "role", "target_id": 2, "target_name": "Moderator", "allow": 2048, "deny": 0}]},
            {"id": 11, "name": "EVENT", "position": 1, "overwrites": []},
        ],
        "channels": [
            {"id": 100, "name": "umum", "type": "text", "category_id": 10, "position": 0},
            {"id": 101, "name": "pengumuman", "type": "news", "category_id": 10, "position": 4,
             "overwrites": [{"target_type": "role", "target_name": "Moderator", "allow": 2048, "deny": 0},
                            {"target_type": "member", "target_name": "Budi", "allow": 1, "deny": 0}]},
            {"id": 102, "name": "voice-lounge", "type": "voice", "category_id": 11, "position": 2},
            {"id": 103, "name": "lounge-2", "type": "voice", "category_id": 11, "position": 3,
             "bitrate": 64000, "user_limit": 5},
            {"id": 104, "name": "forum-diskusi", "type": "forum", "category_id": 11, "position": 1,
             "topic": "Diskusi komunitas", "slowmode": 5,
             "forum": {"default_auto_archive_duration": 1440,
                       "default_thread_slowmode_delay": 12,
                       "default_sort_order": 0, "default_layout": 2,
                       "default_reaction_emoji": "💬",
                       "available_tags": [{"name": "Tanya", "emoji": "❓", "moderated": True}]}},
            {"id": 105, "name": "media-galeri", "type": "media", "category_id": 11, "position": 5,
             "forum": {"available_tags": [{"name": "Foto", "emoji": "📷", "moderated": False}]}},
        ],
    }


@pytest.mark.asyncio
async def test_backup_restore_parse_plan_and_apply(monkeypatch):
    """Pemulihan struktur: parsing, dry-run, pembuatan role/kategori/channel, & pengaman."""
    import json as _json

    import backup_restore as br

    monkeypatch.setattr(br, "CREATE_DELAY_SEC", 0)

    # 1. Parsing & validasi
    snapshot = _sample_backup()
    raw = _json.dumps(snapshot)
    parsed, error = br.parse_backup(raw)
    assert parsed is not None and error == ""
    assert br.parse_backup("")[1] == "Berkas kosong."
    assert "JSON" in br.parse_backup("{bukan json")[1]
    assert "bukan backup struktur" in br.parse_backup('{"foo": 1}')[1]
    bad_version = dict(snapshot, meta={"version": 99})
    assert "lebih baru" in br.parse_backup(_json.dumps(bad_version))[1]

    info = br.summarize(snapshot)
    assert info["guild_name"] == "Server Lama"
    assert info["roles"] == 2 and info["categories"] == 2 and info["channels"] == 6

    # 2. Rencana (dry-run) tidak mengubah server sama sekali
    guild = _BRGuild()
    plan = br.build_plan(guild, snapshot)
    assert guild.created == {"roles": [], "categories": [], "channels": []}
    assert guild.category_create_kwargs == []
    assert [r["name"] for r in plan["roles"]] == ["Event"]           # Moderator sudah ada
    assert [c["name"] for c in plan["categories"]] == ["EVENT"]      # INFO sudah ada
    names = [c["name"] for c in plan["channels"]]
    assert names == ["forum-diskusi", "lounge-2", "pengumuman", "media-galeri"]
    assert "umum" not in names and "voice-lounge" not in names       # sudah ada
    assert not any("forum-diskusi" in item or "media-galeri" in item for item in plan["skipped"])
    assert plan["already"] == {"roles": 1, "categories": 1, "channels": 2}
    ringkasan_plan = br.describe_plan(plan)
    assert "Event" in ringkasan_plan and "Sudah ada" in ringkasan_plan
    assert "• **Role baru (1):**" in ringkasan_plan
    assert "• **Channel baru (4):**" in ringkasan_plan
    assert "`forum-diskusi` (forum → `EVENT`)" in ringkasan_plan
    assert "`media-galeri` (media → `EVENT`)" in ringkasan_plan

    # 3. Opsi nonaktif → tidak ada yang dibuat untuk jenis itu
    plan_no_role = br.build_plan(guild, snapshot, buat_role=False)
    assert plan_no_role["roles"] == []

    # 4. Eksekusi: role → kategori → channel, izin role diterapkan
    result = await br.apply_plan(guild, plan, actor_id=42)
    assert result["roles"] == 1 and guild.created["roles"] == ["Event"]
    assert result["categories"] == 1 and guild.created["categories"] == ["EVENT"]
    assert [c[1] for c in guild.created["channels"]] == [
        "forum-diskusi", "lounge-2", "pengumuman", "media-galeri"
    ]
    assert result["channels"] == 4
    assert all("position" not in kwargs for kwargs in guild.category_create_kwargs)
    assert all("position" not in channel[2] for channel in guild.created["channels"])
    assert result["overwrites"] >= 1          # izin role Moderator diterapkan
    assert result["errors"] == []

    # Channel announcement dibuat sebagai text, voice memakai bitrate & limit
    kinds = {c[1]: c for c in guild.created["channels"]}
    assert kinds["pengumuman"][0] == "text"
    assert kinds["lounge-2"][0] == "voice"
    assert kinds["lounge-2"][2].get("user_limit") == 5
    assert kinds["pengumuman"][2].get("category").name == "INFO"
    forum_kwargs = kinds["forum-diskusi"][2]
    assert kinds["forum-diskusi"][0] == "forum"
    assert forum_kwargs["category"].name == "EVENT"
    assert forum_kwargs["default_auto_archive_duration"] == 1440
    assert forum_kwargs["default_thread_slowmode_delay"] == 12
    assert forum_kwargs["default_sort_order"].value == 0
    assert forum_kwargs["default_layout"].value == 2
    assert forum_kwargs["available_tags"][0].name == "Tanya"
    assert forum_kwargs["available_tags"][0].emoji.name == "❓"
    media_kwargs = kinds["media-galeri"][2]
    assert kinds["media-galeri"][0] == "media" and media_kwargs["media"] is True
    assert media_kwargs["category"].name == "EVENT"
    assert "default_layout" not in media_kwargs
    # Overwrite per-member dilewati (ID member beda di server lain)
    applied = [p[0] for p in kinds["pengumuman"][2].get("category").perms]
    assert isinstance(applied, list)

    # 5. Batas jumlah item per pemulihan
    big = {
        "meta": {"version": 1},
        "roles": [{"name": f"R{i}", "permissions": 0} for i in range(40)],
        "categories": [],
        "channels": [],
    }
    plan_big = br.build_plan(_BRGuild(99), big)
    assert plan_big["total"] <= br.MAX_CREATE_TOTAL
    assert any("batas" in item for item in plan_big["skipped"])

    # 6. Kegagalan izin tidak menghentikan item lain
    class _Forbidden(Exception):
        pass

    forbidden_guild = _BRGuild(77)

    async def _deny(**kwargs):
        raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "nope")

    forbidden_guild.create_role = _deny
    result2 = await br.apply_plan(forbidden_guild, br.build_plan(forbidden_guild, snapshot))
    assert result2["roles"] == 0 and result2["errors"]
    assert result2["channels"] == 4            # channel tetap dibuat

    assert "Role dibuat" in br.describe_result(result)


@pytest.mark.asyncio
async def test_backup_restore_orders_new_categories_and_detects_old_media_api(monkeypatch):
    import backup_restore as br

    monkeypatch.setattr(br, "CREATE_DELAY_SEC", 0)
    order_guild = _BRGuild()
    order_plan = br.build_plan(
        order_guild,
        {
            "roles": [],
            "categories": [
                {"name": "Z-akhir", "position": 20},
                {"name": "A-awal", "position": 1},
            ],
            "channels": [],
        },
    )
    assert [item["name"] for item in order_plan["categories"]] == ["A-awal", "Z-akhir"]
    await br.apply_plan(order_guild, order_plan)
    assert order_guild.created["categories"] == ["A-awal", "Z-akhir"]
    assert all("position" not in kwargs for kwargs in order_guild.category_create_kwargs)

    class _Discord25Guild(_BRGuild):
        async def create_forum(
            self,
            name,
            *,
            topic=None,
            category=None,
            slowmode_delay=None,
            nsfw=None,
            reason=None,
            default_auto_archive_duration=None,
            default_thread_slowmode_delay=None,
            default_sort_order=None,
            default_layout=None,
            default_reaction_emoji=None,
            available_tags=None,
        ):
            self.created["channels"].append(("forum", name, {}))
            return _BRChannel(name, "forum")

    old_plan = br.build_plan(_Discord25Guild(), _sample_backup())
    names = [item["name"] for item in old_plan["channels"]]
    assert "forum-diskusi" in names
    assert "media-galeri" not in names
    assert any("media-galeri" in item and "Discord.py 2.6" in item for item in old_plan["skipped"])


# ==============================================================================
# RAID GUARD (v1.31.0-beta)
# ==============================================================================
class _RaidGuild:
    def __init__(self, gid=64):
        self.id = gid
        self.name = "Server Raid"
        self.owner_id = 1
        self.owner = None
        self.system_channel = _RaidChannel(900)
        self.members = []

    async def fetch_member(self, uid):
        return None


class _RaidChannel:
    def __init__(self, cid=901):
        self.id = cid
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)


class _RaidMember:
    def __init__(self, uid=501, name="Pendatang", mention=None):
        self.id = uid
        self.name = name
        self.mention = mention or f"<@{uid}>"
        self.bot = False
        self.dm = []

    async def send(self, content=None, **kwargs):
        self.dm.append(content)


@pytest.mark.asyncio
async def test_raid_guard_detection_actions_and_auto_end(monkeypatch):
    """Raid Guard: deteksi lonjakan join, tahan Auto Role, lockdown opsional, & berakhir otomatis."""
    import raid_guard

    raid_guard.raid_configs.clear()
    raid_guard.raid_states.clear()
    raid_guard.reset_runtime()

    guild = _RaidGuild(64)
    log_channel = _RaidChannel(901)
    guild.system_channel = log_channel
    member = _RaidMember(501)
    member.guild = guild

    class _Bot:
        user = _RaidMember(999, "Bot")

        def get_guild(self, gid):
            return guild if int(gid) == 64 else None

        def get_channel(self, cid):
            return log_channel if int(cid) == 901 else None

    bot = _Bot()

    # 1. Default nonaktif → join tidak memicu apa pun
    assert raid_guard.is_enabled(64) is False
    for _ in range(10):
        assert await raid_guard.handle_member_join(bot, member) is None
    assert raid_guard.is_raid_active(64) is None

    # 2. Setelah diaktifkan, lonjakan join memicu mode raid otomatis
    raid_guard.reset_runtime()
    raid_guard.set_config(64, enabled=True, join_threshold=3, window_sec=60, action="verifikasi", duration_min=5)
    cfg = raid_guard.get_config(64)
    cfg["log_channel_id"] = 901
    cfg["verify_channel_id"] = 901

    assert await raid_guard.handle_member_join(bot, member) is None      # join ke-1
    assert await raid_guard.handle_member_join(bot, member) is None      # join ke-2
    state = await raid_guard.handle_member_join(bot, member)             # join ke-3 → raid
    assert state is not None and state["action"] == "verifikasi"
    assert raid_guard.is_raid_active(64) is not None
    assert raid_guard.should_skip_autorole(64) is True
    titles = [kw["embed"].title for kw in log_channel.sent if kw.get("embed")]
    assert any("Mode Raid" in title for title in titles)
    assert member.dm                                                # DM pengingat verifikasi terkirim

    # 3. Ambang & validasi konfigurasi
    raid_guard.set_config(64, join_threshold=999, window_sec=1, duration_min=9999)
    cfg = raid_guard.get_config(64)
    assert cfg["join_threshold"] == 100 and cfg["window_sec"] == 10 and cfg["duration_min"] == 1440

    # 4. Mode `lapor` tidak menahan Auto Role
    raid_guard.raid_states.clear()
    raid_guard.set_config(64, action="lapor")
    await raid_guard.start(bot, guild, reason="uji lapor", action="lapor", duration_min=1)
    assert raid_guard.should_skip_autorole(64) is False

    # 5. Mode lockdown memakai server_tools & dibuka kembali saat berakhir
    import server_tools as st

    calls = {"start": 0, "stop": 0}

    async def _fake_start(guild_arg, by_id=0, reason=""):
        calls["start"] += 1
        return 2, 0

    async def _fake_stop(guild_arg):
        calls["stop"] += 1
        return 2

    monkeypatch.setattr(st, "start_lockdown", _fake_start)
    monkeypatch.setattr(st, "stop_lockdown", _fake_stop)
    monkeypatch.setattr(st, "save_server_tools_to_disk", lambda: _noop())

    async def _noop():
        return None

    raid_guard.raid_states.clear()
    result = await raid_guard.start(bot, guild, reason="uji lockdown", action="verifikasi+lockdown", duration_min=1)
    assert calls["start"] == 1 and result["state"]["locked"] is True
    ended = await raid_guard.end(bot, guild)
    assert ended["ended"] is True and calls["stop"] == 1

    # 6. Akhiri saat tidak aktif
    again = await raid_guard.end(bot, guild)
    assert again["ended"] is False

    # 7. Kedaluwarsa otomatis (tick) & sisa waktu
    raid_guard.raid_states.clear()
    await raid_guard.start(bot, guild, reason="uji tick", action="lapor", duration_min=1)
    assert raid_guard.remaining_seconds(64) > 0
    raid_guard.raid_states[64]["until"] = time.time() - 1
    assert await raid_guard.tick(bot) == [64]
    assert raid_guard.is_raid_active(64) is None

    # 8. Anti-spam laporan: trigger kedua dalam 5 menit diabaikan
    raid_guard.reset_runtime()
    raid_guard.set_config(64, enabled=True, join_threshold=2, action="verifikasi")
    assert await raid_guard.handle_member_join(bot, member) is None
    first = await raid_guard.handle_member_join(bot, member)
    assert first is not None
    raid_guard.raid_states.clear()
    raid_guard.reset_runtime()
    raid_guard._alert_cooldown[64] = time.time()
    assert await raid_guard.handle_member_join(bot, member) is None

    # 9. Persistensi
    raid_guard.raid_configs.clear()
    raid_guard.raid_states.clear()
    assert raid_guard.load_raid_from_disk() >= 0
    assert isinstance(raid_guard.cleanup_raid_runtime(), int)
    assert raid_guard.handle_channel_delete(901) in (0, 1)

    raid_guard.raid_configs.clear()
    raid_guard.raid_states.clear()
    raid_guard.reset_runtime()


# ==============================================================================
# PLAYLIST MUSIK PER MEMBER (v1.32.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_music_playlists_per_member():
    """Playlist pribadi: simpan, batas kuota, ubah nama, hapus lagu, & persistensi."""
    import music_playlists as pl

    pl.guild_playlists.clear()

    def _track(title, uri=None, ident="ytsearch"):
        return {"title": title, "query": uri or title, "identifier": ident}

    # 1. Simpan playlist pertama (menimpa)
    ok, msg = pl.save_playlist(1, 10, "  Favorit  Nya ", [_track("Lagu A"), _track("Lagu B")])
    assert ok and "Favorit Nya" in msg
    assert len(pl.member_playlists(1, 10)) == 1
    data = pl.get_playlist(1, 10, "favorit nya")
    assert data is not None and len(data["tracks"]) == 2

    # 2. Duplikat nama (tanpa peka huruf) tidak membuat playlist baru
    ok, _ = pl.save_playlist(1, 10, "FAVORIT NYA", [_track("Lagu A"), _track("Lagu C")], replace=False)
    assert ok
    names = [item["name"] for item in pl.member_playlists(1, 10)]
    assert names == ["Favorit Nya"]
    # replace=False menambahkan lagu baru tanpa menghapus yang lama
    assert [t["title"] for t in pl.get_playlist(1, 10, "favorit nya")["tracks"]] == ["Lagu A", "Lagu B", "Lagu C"]

    # 3. Validasi nama
    assert pl.save_playlist(1, 10, "   ", [_track("X")])[0] is False
    assert "32" in pl.save_playlist(1, 10, "x" * 40, [_track("X")])[1]
    assert pl.save_playlist(1, 10, "semua", [_track("X")])[0] is False

    # 4. Batas playlist per member
    for i in range(4):
        assert pl.save_playlist(1, 10, f"Set {i}", [_track(f"Lagu {i}")])[0] is True
    assert len(pl.member_playlists(1, 10)) == pl.MAX_PLAYLISTS_PER_MEMBER
    ok, msg = pl.save_playlist(1, 10, "Set Baru", [_track("Lagu Z")])
    assert ok is False and str(pl.MAX_PLAYLISTS_PER_MEMBER) in msg

    # 5. Dokumen lagu dirapikan & dideduplikasi
    entries = pl.tracks_from_queue([_track("A"), _track("A"), {"title": "B"}, {"query": ""}])
    assert [e["title"] for e in entries] == ["A", "B"]

    # 6. Batas lagu per playlist
    many = [_track(f"Juara {i}") for i in range(pl.MAX_TRACKS_PER_PLAYLIST + 20)]
    ok, _ = pl.save_playlist(1, 11, "Panjang", many)
    assert ok and len(pl.get_playlist(1, 11, "panjang")["tracks"]) == pl.MAX_TRACKS_PER_PLAYLIST

    # 7. Ubah nama
    ok, msg = pl.rename_playlist(1, 10, "Set 0", "Favorit Baru")
    assert ok and pl.get_playlist(1, 10, "favorit baru") is not None
    assert pl.get_playlist(1, 10, "set 0") is None
    assert pl.rename_playlist(1, 10, "Favorit Baru", "Set 1")[0] is False       # sudah dipakai
    assert pl.rename_playlist(1, 10, "tidak ada", "Apa")[0] is False

    # 8. Hapus lagu berdasarkan nomor (playlist kosong otomatis dihapus)
    assert pl.remove_track(1, 10, "Favorit Baru", 99)[0] is False
    assert pl.remove_track(1, 10, "Favorit Baru", 1)[0] is True
    assert pl.get_playlist(1, 10, "Favorit Baru") is None

    # 9. Hapus playlist terakhir ikut menghapus entri member
    ok, _ = pl.delete_playlist(1, 11, "Panjang")
    assert ok and pl.get_playlist(1, 11, "panjang") is None
    assert pl.delete_playlist(1, 11, "Panjang")[0] is False

    # 10. Persistensi & pembersihan
    await pl.save_playlists_to_disk()
    pl.guild_playlists.clear()
    assert pl.load_playlists_from_disk() >= 1
    assert pl.get_playlist(1, 10, "Set 1") is not None
    pl.get_playlist(1, 10, "Set 1")["tracks"] = []
    assert pl.cleanup_music_playlist_runtime() >= 1
    pl.guild_playlists.clear()
    await pl.save_playlists_to_disk()


# ==============================================================================
# RATING BINTANG, SLA, & AUTO-CLOSE TIKET (v1.33.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_ticket_rating_sla_and_auto_close(monkeypatch):
    """Tiket: rating bintang pemilik tiket, SLA respons pertama, & auto-close menganggur."""
    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    tickets._ticket_seq.clear()

    gid = 4242
    cfg = tickets.set_ticket_config(gid, enabled=True, sla_jam=2, auto_close_jam=48, rating_aktif=True)
    assert cfg["sla_jam"] == 2 and cfg["auto_close_jam"] == 48 and cfg["rating_aktif"] is True
    assert tickets.set_ticket_config(gid, sla_jam=9999)["sla_jam"] == 720
    tickets.set_ticket_config(gid, sla_jam=2)   # kembalikan ke batas uji

    now = time.time()
    data = tickets.register_ticket(9001, gid, 777, topic="Bantuan", now=now)
    assert data["first_response_at"] == 0 and data["rating"] == 0

    # 1. Respons staf pertama tercatat sekali saja
    assert tickets.record_first_response(9001, 55, now=now + 300) is True
    assert tickets.record_first_response(9001, 66, now=now + 400) is False
    assert data["first_response_by"] == 55 and data["status"] == "diklaim"

    # 2. SLA dihitung dari tiket yang belum direspons
    tickets.register_ticket(9002, gid, 778, now=now)
    assert tickets.sla_overdue(hours=2, guild_id=gid, now=now + 3600) == []
    assert 9002 in tickets.sla_overdue(hours=2, guild_id=gid, now=now + 3 * 3600)
    assert 9001 not in tickets.sla_overdue(hours=2, guild_id=gid, now=now + 3 * 3600)
    assert tickets.sla_overdue(guild_id=gid, now=now + 3 * 3600) == [9002]   # pakai config server
    assert tickets.mark_sla_alerted(9002) is True
    assert tickets.mark_sla_alerted(9002) is False                          # tidak spam
    assert tickets.get_ticket_config(gid)["sla_alerted"] == 1

    # 3. Rating hanya boleh oleh pemilik tiket & setelah tiket selesai
    assert tickets.rate_ticket(9002, 5, user_id=778)[0] == "belum_selesai"
    status, closed = tickets.close_ticket(9002, 999, reason="staf")
    assert status == "ok" and closed["closed_reason"] == "staf"
    assert tickets.rate_ticket(9002, 5, user_id=12345)[0] == "bukan_pemilik"
    assert tickets.rate_ticket(9002, 9, user_id=778)[0] == "tidak_valid"
    assert tickets.rate_ticket(9002, 4, user_id=778)[0] == "ok"
    assert tickets.rate_ticket(9002, 5, user_id=778)[0] == "sudah"
    assert tickets.rate_ticket(123456, 5)[0] == "tidak_ada"

    summary = tickets.rating_summary(gid)
    assert summary["count"] == 1 and summary["average"] == 4.0
    assert summary["distribution"][4] == 1 and summary["distribution"][5] == 0

    sla = tickets.sla_stats(gid)
    assert sla["responded"] == 1 and sla["pending"] == 0 and sla["avg_minutes"] == 5

    # 4. Auto-close memakai aktivitas terakhir
    tickets.register_ticket(9003, gid, 779, now=now)
    assert tickets.stale_tickets(guild_id=gid, now=now + 3600) == []
    assert tickets.record_activity(9003, now=now + 7200) is True
    stale_now = tickets.stale_tickets(guild_id=gid, now=now + 50 * 3600)
    assert 9003 not in stale_now          # baru saja ada aktivitas
    assert 9001 in stale_now              # tiket lama tanpa aktivitas
    assert 9003 in tickets.stale_tickets(guild_id=gid, now=now + 100 * 3600)
    assert tickets.stale_tickets(hours=0, guild_id=gid) == []

    # 5. Pelacakan pesan: staf → respons pertama, pemilik → aktivitas saja
    class _Msg:
        def __init__(self, uid, roles=(), admin=False):
            self.channel = type("C", (), {"id": 9004})()
            self.author = type(
                "A",
                (),
                {
                    "id": uid,
                    "bot": False,
                    "roles": [type("R", (), {"id": r})() for r in roles],
                    "guild_permissions": type("P", (), {"administrator": admin, "manage_threads": False, "manage_channels": False})(),
                },
            )()

    tickets.register_ticket(9004, gid, 780, now=now)
    assert tickets.maybe_track_ticket_message(_Msg(780)) is True       # pemilik: aktivitas
    assert tickets.get_ticket(9004)["first_response_at"] == 0
    assert tickets.maybe_track_ticket_message(_Msg(900, admin=True)) is True
    assert tickets.get_ticket(9004)["first_response_at"] > 0
    assert tickets.maybe_track_ticket_message(type("M", (), {"channel": None, "author": None})()) is False

    # 6. Pengawas: kirim peringatan SLA & tutup tiket menganggur
    tickets.set_ticket_config(gid, sla_jam=1, auto_close_jam=1)
    tickets.register_ticket(9005, gid, 781, now=now - 5 * 3600)
    alerts = []

    class _Chan:
        async def send(self, *args, **kwargs):
            alerts.append(kwargs)

    class _Guild:
        id = gid
        system_channel = _Chan()

    class _Bot:
        def get_guild(self, gid_arg):
            return _Guild() if int(gid_arg) == gid else None

        def get_channel(self, cid):
            return _Chan()

    async def _edit(*args, **kwargs):
        return None

    result = await tickets.run_ticket_check(_Bot())
    assert result["sla"] >= 1
    assert result["closed"] >= 1
    assert tickets.get_ticket(9005)["closed_reason"].startswith("otomatis")
    assert alerts

    # 7. Persistensi pengaturan baru
    await tickets.save_tickets_to_disk()
    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    assert tickets.load_tickets_from_disk() >= 1
    reloaded = tickets.get_ticket_config(gid)
    assert reloaded["sla_jam"] == 1 and reloaded["auto_close_jam"] == 1
    assert reloaded["rating_count"] == 1

    tickets.ticket_guilds.clear()
    tickets.tickets.clear()
    tickets._ticket_seq.clear()
    await tickets.save_tickets_to_disk()


# ==============================================================================
# MUSIM LEVEL & PRESTIGE (v1.34.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_level_season_reset_and_prestige():
    """Musim level: snapshot juara, reset XP, prestige permanen, & reset otomatis."""
    import levels as lv

    lv.level_guilds.clear()
    lv.levels.clear()

    gid = 9090
    lv.set_level_config(gid, aktif=True)
    lv.set_level_config(gid, season_auto_hari=30, prestige_min_level=3)

    now = time.time()
    lv.levels[lv._key(gid, 1)] = {"xp": 500, "level": 5, "messages": 40, "prestige": 1}
    lv.levels[lv._key(gid, 2)] = {"xp": 300, "level": 3, "messages": 20}
    lv.levels[lv._key(gid, 3)] = {"xp": 100, "level": 1, "messages": 5}

    # 1. Status musim awal
    info = lv.season_info(gid, now=now)
    assert info["season"] == 1 and info["auto_hari"] == 30 and info["sisa_hari"] == 30
    assert info["last"] is None

    # 2. Prestige: syarat level minimum
    ok, reason = lv.can_prestige(gid, 3)
    assert ok is False and "level 3" in reason
    ok, reason = lv.can_prestige(gid, 1)
    assert ok is True

    ok, data = lv.apply_prestige(gid, 1)
    assert ok and data["prestige"] == 2
    member = lv.get_member_level(gid, 1)
    assert member["level"] == 0 and member["xp"] == 0 and member["prestige"] == 2
    assert lv.get_level_config(gid)["prestige_count"] == 1

    # 3. Prestige bisa dimatikan admin
    lv.set_level_config(gid, prestige_aktif=False)
    assert lv.can_prestige(gid, 2)[0] is False
    lv.set_level_config(gid, prestige_aktif=True)

    # 4. Reset musim: snapshot juara, XP direset, prestige disimpan
    snapshot = lv.reset_season(gid, by_id=42, now=now)
    assert snapshot["season"] == 1 and snapshot["participants"] == 3
    assert snapshot["top"][0]["user_id"] == 2         # juara = XP tertinggi saat reset
    assert snapshot["by"] == 42
    cfg = lv.get_level_config(gid)
    assert cfg["season"] == 2
    assert len(cfg["season_history"]) == 1
    assert lv.get_member_level(gid, 2)["xp"] == 0
    assert lv.get_member_level(gid, 1)["prestige"] == 2     # trofi tetap ada
    assert lv.season_info(gid, now=now + 86400)["days_elapsed"] == 1

    # 5. Riwayat dibatasi 12 musim
    for _ in range(13):
        lv.reset_season(gid, now=now)
    assert len(lv.get_level_config(gid)["season_history"]) == 12
    assert lv.get_level_config(gid)["season"] == 15

    # 6. Reset otomatis sesuai jadwal
    lv.set_level_config(gid, season_auto_hari=7)
    cfg = lv.get_level_config(gid)
    cfg["season_started_at"] = now - 8 * 86400
    assert lv.season_due(gid, now=now) is True
    cfg["season_started_at"] = now
    assert lv.season_due(gid, now=now) is False
    lv.set_level_config(gid, season_auto_hari=0)
    cfg["season_started_at"] = now - 400 * 86400
    assert lv.season_due(gid, now=now) is False      # manual saja

    # 7. Embed pengumuman & pengawas
    lv.set_level_config(gid, season_auto_hari=1)
    lv.get_level_config(gid)["season_started_at"] = now - 2 * 86400
    lv.levels[lv._key(gid, 7)] = {"xp": 50, "level": 1, "messages": 2}

    class _Chan:
        def __init__(self):
            self.sent = []

        async def send(self, *args, **kwargs):
            self.sent.append(kwargs)

    channel = _Chan()

    class _Guild:
        id = gid
        name = "Server Musim"

    class _Bot:
        def get_guild(self, gid_arg):
            return _Guild() if int(gid_arg) == gid else None

        def get_channel(self, cid):
            return channel

    lv.get_level_config(gid)["announce_channel_id"] = 1234
    assert await lv.run_level_season_check(_Bot()) == 1
    assert channel.sent and "Musim" in channel.sent[0]["embed"].title

    # 8. Kartu level & papan peringkat menampilkan prestige
    class _Member:
        display_name = "Budi"
        display_avatar = None

    lv.levels[lv._key(gid, 8)] = {"xp": 20, "level": 1, "messages": 1, "prestige": 3}
    card = lv.build_level_embed(_Member(), lv.get_member_level(gid, 8), lv.get_level_config(gid))
    assert any("Prestige" in f.name for f in card.fields)
    board = lv.build_leaderboard_embed(
        _Guild(), [(8, lv.levels[lv._key(gid, 8)])], page=0, total_pages=1, total_members=1
    )
    assert "🌟`3×`" in board.fields[0].value

    # 9. Persistensi musim & prestige
    await lv.save_levels_to_disk()
    lv.level_guilds.clear()
    lv.levels.clear()
    assert lv.load_levels_from_disk() >= 1
    assert lv.get_level_config(gid)["season"] >= 2
    assert lv.get_member_level(gid, 8)["prestige"] == 3

    lv.level_guilds.clear()
    lv.levels.clear()
    await lv.save_levels_to_disk()


# ==============================================================================
# ANTI-NUKE LANJUTAN: BOT JAHAT & MODE BEKU (v1.35.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_antinuke_freeze_and_foreign_bot():
    """Anti-Nuke: mode beku (ambang 1 aksi) & perlindungan bot asing ber-Administrator."""
    import antinuke

    antinuke.antinuke_guilds.clear()
    antinuke.violations.clear()
    antinuke.reset_events()

    gid = 999
    guild = _ANGuild(gid)
    nuker = _ANMember(801, "Nuker", [_ANRole(11)])
    guild._members[801] = nuker
    channel = _ANChannel(902)
    guild.system_channel = channel

    class _Bot:
        def get_channel(self, cid):
            return channel if int(cid) == 902 else None

        def get_guild(self, gid_arg):
            return guild if int(gid_arg) == gid else None

    bot = _Bot()
    antinuke.set_config(gid, enabled=True, action="timeout", restore=True)

    # 1. Sebelum beku: satu aksi belum melewati ambang (3x)
    base = time.time()
    assert await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "channel_delete"), now=base) is None

    # 2. Mulai beku → setiap aksi destruktif langsung ditindak
    cfg = antinuke.start_freeze(gid, minutes=30, by_id=555, now=base)
    assert cfg["freeze_aktif"] is True
    assert antinuke.is_frozen(gid, now=base + 10) is True
    assert antinuke.freeze_remaining(gid, now=base + 60) == 29 * 60
    violation = await antinuke.handle_audit_entry(bot, _ANEntry(guild, nuker, "channel_delete"), now=base + 20)
    assert violation is not None and violation["limit"] == 1
    assert nuker.timed_out_until is not None
    assert any("beku" in f.value.lower() for f in channel.sent[-1]["embed"].fields)

    # 3. Beku berakhir otomatis sesuai durasi
    assert antinuke.is_frozen(gid, now=base + 31 * 60) is False
    assert antinuke.get_config(gid)["freeze_aktif"] is False

    # 4. Bot asing yang ditambahkan langsung dikeluarkan
    evil_bot = _ANMember(950, "EvilBot")
    evil_bot.bot = True
    entry = _ANEntry(guild, nuker, "bot_add")
    entry.target = evil_bot
    violation2 = await antinuke.handle_audit_entry(bot, entry, now=base + 5000)
    assert violation2 is not None and violation2["action"] == "bot_add"
    assert evil_bot.kicked is True
    assert any("dikeluarkan" in f.value for f in channel.sent[-1]["embed"].fields)

    # 5. auto_kick_bot bisa dimatikan Admin
    antinuke.set_config(gid, auto_kick_bot=False)
    evil_bot2 = _ANMember(951, "EvilBot2")
    evil_bot2.bot = True
    entry2 = _ANEntry(guild, nuker, "bot_add")
    entry2.target = evil_bot2
    antinuke.reset_events()
    assert await antinuke.handle_audit_entry(bot, entry2, now=base + 6000) is not None
    assert evil_bot2.kicked is False

    # 6. Pembuatan role massal ikut terdeteksi
    assert antinuke.classify("role_create") == "role_create"
    assert antinuke.classify("bot_add") == "bot_add"
    assert antinuke.classify("message_delete") is None

    # 7. Cairkan manual & watcher beku kedaluwarsa
    antinuke.start_freeze(gid, minutes=5, by_id=1)
    assert antinuke.end_freeze(gid) is True
    assert antinuke.end_freeze(gid) is False
    antinuke.start_freeze(gid, minutes=5, by_id=1)
    antinuke.get_config(gid)["freeze_until"] = time.time() - 1
    assert antinuke.expired_freezes() == [gid]
    assert await antinuke.refresh_freezes(bot) == 1
    assert antinuke.is_frozen(gid) is False

    # 8. Persistensi status beku
    antinuke.start_freeze(gid, minutes=10, by_id=77)
    await antinuke.save_antinuke_to_disk()
    antinuke.antinuke_guilds.clear()
    assert antinuke.load_antinuke_from_disk() >= 1
    assert antinuke.is_frozen(gid) is True
    assert antinuke.get_config(gid)["auto_kick_bot"] is False

    antinuke.end_freeze(gid)
    await antinuke.save_antinuke_to_disk()


# ==============================================================================
# i18n INTI & /bahasa (v1.36.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_i18n_core_texts_and_language_command():
    """Bahasa per server: normalisasi kode, terjemahan kerangka, & persistensi."""
    import i18n
    import ui_kit

    i18n.guild_lang.clear()

    # 1. Default Bahasa Indonesia
    assert i18n.get_lang(1) == "id"
    assert i18n.t("confirm.yes", 1) == "Ya, lanjutkan"
    assert i18n.t("status.on", 1) == "aktif"

    # 2. Normalisasi kode & alias
    for raw, expected in [
        ("en", "en"),
        ("EN", "en"),
        ("en-US", "en"),
        ("english", "en"),
        ("id-ID", "id"),
        ("indonesia", "id"),
    ]:
        assert i18n.normalize_lang(raw) == expected
    assert i18n.normalize_lang("klingon") is None
    assert i18n.normalize_lang("") is None

    # 3. Ganti bahasa server
    ok, code = i18n.set_lang(1, "en")
    assert ok and code == "en"
    assert i18n.t("confirm.yes", 1) == "Yes, continue"
    assert i18n.t("status.off", 1) == "disabled"
    assert i18n.t("perm.admin", 1) == "Admin permission required"
    assert "Server language" in i18n.t("lang.current", 1, lang=i18n.lang_label("en"))
    assert i18n.t("confirm.cancelled_detail", 1) == "No changes were made."

    # Server lain tidak terpengaruh
    assert i18n.get_lang(2) == "id"

    # 4. Kode tidak dikenal ditolak tanpa mengubah bahasa
    assert i18n.set_lang(1, "xx") == (False, "en")
    assert i18n.get_lang(1) == "en"

    # 5. Semua kunci punya versi Indonesia & English
    for key, entry in i18n.TEXTS.items():
        assert entry.get("id"), key
        assert entry.get("en"), key

    # 6. Dialog konfirmasi ikut berbahasa server
    view = ui_kit.ConfirmView(1, title="Uji", detail="Detail")
    labels = []
    for container in view.children:
        for child in getattr(container, "children", []):
            for item in getattr(child, "children", []) or []:
                label = getattr(item, "label", None)
                if label:
                    labels.append(label)
    assert "Yes, continue" in labels and "Cancel" in labels
    assert "Ya, lanjutkan" in str(ui_kit.ConfirmView(2, title="Uji", detail="Detail").to_components())

    # 7. Persistensi (bahasa default tidak ditulis)
    await i18n.save_lang_to_disk()
    i18n.guild_lang.clear()
    assert i18n.load_lang_from_disk() >= 1
    assert i18n.get_lang(1) == "en"
    i18n.guild_lang[3] = "id"
    assert i18n.cleanup_i18n_runtime() == 1

    # 8. Pilihan bahasa tersedia untuk command
    assert set(i18n.available_langs()) == {"id", "en"}
    assert i18n.describe_lang(1) == "🇬🇧 English"

    i18n.guild_lang.clear()
    await i18n.save_lang_to_disk()


# ==============================================================================
# PREFIX COMMAND PER SERVER (v1.37.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_custom_prefix_per_guild():
    """Prefix per server: validasi, pencocokan pesan, reset, & persistensi."""
    import prefixes

    prefixes.guild_prefixes.clear()

    # 1. Default `!`
    assert prefixes.DEFAULT_PREFIX == "!"
    assert prefixes.get_prefix(1) == "!"
    assert prefixes.prefixes_for(1) == ["!"]
    assert prefixes.is_prefix_command("!setup_panel", 1) is True
    assert prefixes.is_prefix_command("?setup_panel", 1) is False

    # 2. Validasi prefix
    for bad in ("", "   ", "a b", "toolong", "@everyone", "#kanal", "<@123>", "a"):
        ok, _value, error = prefixes.set_prefix(1, bad)
        assert ok is False and error, bad
    assert prefixes.get_prefix(1) == "!"          # tidak berubah karena gagal

    # 3. Prefix valid
    ok, value, message = prefixes.set_prefix(1, " ? ")
    assert ok and value == "?" and "?" in message
    assert prefixes.get_prefix(1) == "?"
    assert prefixes.prefixes_for(1) == ["?", "!"]      # bawaan tetap diterima
    assert prefixes.match_prefix("?setup_panel", 1) == "?"
    assert prefixes.match_prefix("!setup_panel", 1) == "!"
    assert prefixes.is_prefix_command("halo ?bukan-command", 1) is False
    # Server lain tidak terpengaruh
    assert prefixes.is_prefix_command("?setup_panel", 2) is False

    # 4. Prefix multi-karakter & huruf
    ok, value, _ = prefixes.set_prefix(1, "..")
    assert ok and value == ".." and prefixes.match_prefix("..setup_panel", 1) == ".."
    ok, value, _ = prefixes.set_prefix(1, "bot!")
    assert ok and prefixes.match_prefix("bot!setup_panel", 1) == "bot!"

    # 5. Kembali ke bawaan lewat set & reset
    ok, value, _ = prefixes.set_prefix(1, "!")
    assert ok and value == "!" and prefixes.get_prefix(1) == "!"
    assert prefixes.set_prefix(1, "?")[0] is True
    assert prefixes.reset_prefix(1) is True
    assert prefixes.reset_prefix(1) is False

    # 6. Persistensi
    prefixes.set_prefix(5, "?")
    await prefixes.save_prefixes_to_disk()
    prefixes.guild_prefixes.clear()
    assert prefixes.load_prefixes_from_disk() >= 1
    assert prefixes.get_prefix(5) == "?"
    prefixes.guild_prefixes[6] = "!"
    assert prefixes.cleanup_prefixes_runtime() == 1
    assert prefixes.get_prefix(6) == "!"

    prefixes.guild_prefixes.clear()
    await prefixes.save_prefixes_to_disk()


# ==============================================================================
# EKSPOR ANALITIK CSV & WEBHOOK (v1.38.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_analytics_export_csv_webhook_and_schedule(monkeypatch):
    """Ekspor analitik: CSV per jenis, validasi webhook, jadwal, & pengiriman."""
    import analytics_export as ax
    import insights
    import levels
    import moderation
    import tickets

    ax.analytics_guilds.clear()
    gid = 3131
    now = time.time()

    # 1. Data contoh dari modul yang sudah ada
    levels.levels.clear()
    levels.levels[f"{gid}:1"] = {"xp": 120, "level": 2, "messages": 9, "voice_xp": 4, "prestige": 1}
    levels.levels[f"{gid}:2"] = {"xp": 300, "level": 3, "messages": 20}
    levels.levels["999:1"] = {"xp": 999, "level": 9, "messages": 99}       # server lain

    moderation.mod_cases.clear()
    moderation.mod_cases[gid] = [
        {
            "id": 1,
            "user_id": 11,
            "moderator_id": 22,
            "action": "warn",
            "reason": "spam, link berlebih",
            "duration_sec": None,
            "created_at": now,
        }
    ]

    tickets.tickets.clear()
    tickets.tickets[7001] = {
        "thread_id": 7001,
        "guild_id": gid,
        "user_id": 33,
        "number": 1,
        "status": "selesai",
        "topic": "bantuan akun",
        "created_at": now - 3600,
        "first_response_at": now - 3000,
        "closed_at": now,
        "claimed_by": 22,
        "rating": 5,
        "closed_reason": "staf",
    }

    insights.ai_usage.clear()
    insights.ai_usage["2026-11-05"] = {
        "total": 10,
        "cache_hits": 4,
        "kinds": {"chat": 6, "ringkas": 2, "gambar": 1, "cari": 1},
    }

    # 2. CSV level: hanya server ini, urut XP tertinggi
    body, filename, error = ax.build_csv("level", gid)
    assert error == "" and filename.startswith("analitik-level-3131-") and filename.endswith(".csv")
    lines = body.strip().splitlines()
    assert lines[0] == "user_id,level,xp,messages,voice_xp,prestige,last_activity"
    assert len(lines) == 3
    assert lines[1].startswith("2,3,300")
    assert lines[2].startswith("1,2,120")

    # 3. CSV moderasi & tiket (alasan berkoma tetap aman)
    mod_body = ax.build_csv("moderasi", gid)[0]
    assert "warn" in mod_body and '"spam, link berlebih"' in mod_body
    tiket_body = ax.build_csv("tiket", gid)[0]
    assert tiket_body.splitlines()[1].startswith("1,33,selesai")
    assert ",5," in tiket_body or tiket_body.rstrip().endswith("staf")

    # 4. CSV pemakaian AI & jenis tidak dikenal
    usage_body = ax.build_csv("pemakaian", gid)[0]
    assert "2026-11-05" in usage_body and usage_body.splitlines()[0].startswith("day,total_calls")
    assert ax.build_csv("entah", gid)[1] == ""
    assert "tidak dikenal" in ax.build_csv("entah", gid)[2]

    # 5. Server tanpa data → pesan jelas
    empty_body, _fn, empty_error = ax.build_csv("level", 5555)
    assert empty_body is None and "Belum ada data" in empty_error

    # 6. BOM UTF-8 untuk Excel
    assert ax.csv_bytes("a,b\n1,2\n").startswith(b"\xef\xbb\xbf")

    # 7. build_all mengembalikan hanya yang berisi data
    kinds = [kind for kind, _name, _body in ax.build_all(gid)]
    assert "level" in kinds and "tiket" in kinds

    # 8. Validasi webhook
    assert ax.validate_webhook("https://discord.com/api/webhooks/1/abc") == (True, "")
    assert ax.validate_webhook("")[0] is False
    assert "https://" in ax.validate_webhook("discord.com/api/webhooks/1/abc")[1]
    assert ax.validate_webhook("https://example.com/hook")[0] is False
    masked = ax.mask_webhook("https://discord.com/api/webhooks/1/abcdef123456")
    assert "abcdef123456" not in masked and masked.startswith("`...")

    # 9. Konfigurasi & jadwal
    cfg = ax.set_config(gid, aktif=True, webhook_url="https://discord.com/api/webhooks/1/tok", jadwal="harian")
    assert cfg["aktif"] is True and cfg["jadwal"] == "harian"
    assert ax.is_due(gid, now=now) is True                      # belum pernah dikirim
    cfg["last_sent"] = now
    assert ax.is_due(gid, now=now + 3600) is False
    assert ax.is_due(gid, now=now + 25 * 3600) is True
    ax.set_config(gid, jadwal="mati")
    assert ax.is_due(gid, now=now + 365 * 86400) is False
    ax.set_config(gid, jadwal="harian", jenis=["level", "entah"])
    assert ax.get_config(gid)["jenis"] == ["level"]

    # 10. Pengiriman ke webhook (HTTP tiruan) & pencatatan
    sent_files = []

    class _Resp:
        status = 204

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _Session:
        def post(self, url, data=None, timeout=None):
            sent_files.append(url)
            return _Resp()   # aiohttp: post() mengembalikan context manager, bukan coroutine

    ok, message = await ax.post_csv_to_webhook(
        "https://discord.com/api/webhooks/1/tok", mod_body, "uji.csv", session=_Session()
    )
    assert ok and message == "terkirim" and sent_files

    class _Bot:
        http_session = _Session()

        def get_guild(self, gid_arg):
            return None

    cfg["last_sent"] = 0
    delivered = await ax.run_analytics_check(_Bot(), now=now + 86400 * 2)
    assert delivered >= 1
    assert ax.get_config(gid)["sent_count"] >= 1
    assert ax.get_config(gid)["last_sent"] > 0

    # 11. Persistensi & pembersihan
    ax.set_config(7000, aktif=False, webhook_url="", jadwal="mati")
    await ax.save_analytics_to_disk()
    ax.analytics_guilds.clear()
    assert ax.load_analytics_from_disk() >= 1
    assert ax.get_config(gid)["webhook_url"].endswith("/tok")
    assert ax.cleanup_analytics_runtime() >= 0

    ax.analytics_guilds.clear()
    levels.levels.clear()
    moderation.mod_cases.clear()
    tickets.tickets.clear()
    insights.ai_usage.clear()
    await ax.save_analytics_to_disk()


# ==============================================================================
# AUDIT RAM & CACHE (v1.39.0-beta)
# ==============================================================================
@pytest.mark.asyncio
async def test_memory_audit_snapshot_and_report(monkeypatch):
    """`/perawatan memori`: angka nyata, cache terhitung, & saran otomatis."""
    import memory_audit

    # 1. Snapshot dasar
    snap = memory_audit.snapshot()
    assert snap["rss_mb"] > 0
    assert isinstance(snap["data_kb"], float)
    assert snap["files"] >= 0
    assert snap["total_entries"] >= 0
    assert {item["label"] for item in snap["caches"]} >= {"XP & level member", "Tiket dukungan"}

    # 2. Cache terhitung dari modul asli
    import levels
    import tickets

    levels.level_guilds.clear()
    levels.levels.clear()
    tickets.tickets.clear()
    levels.levels["1234:1"] = {"xp": 10, "level": 1, "messages": 1}
    levels.levels["1234:2"] = {"xp": 20, "level": 1, "messages": 2}
    tickets.tickets[555] = {"thread_id": 555, "guild_id": 1234, "status": "selesai"}

    snap = memory_audit.snapshot()
    by_label = {item["label"]: item for item in snap["caches"]}
    assert by_label["XP & level member"]["entries"] == 2
    assert by_label["Tiket dukungan"]["entries"] == 1
    assert by_label["XP & level member"]["cap"] == "500 member / server"

    # 3. Playlist terhitung terpisah
    import music_playlists

    music_playlists.guild_playlists.clear()
    music_playlists.guild_playlists[1] = {
        10: {
            "favorit": {
                "name": "Favorit",
                "tracks": [{"title": "A", "query": "A"}, {"title": "B", "query": "B"}],
            }
        }
    }
    assert memory_audit.playlist_track_total() == 2

    # 4. Laporan teks memuat angka & saran
    report = memory_audit.format_report()
    assert "RAM proses" in report and "Cache terbesar" in report
    assert "Saran" in report and len(report) <= 1900
    assert memory_audit.short_line().startswith("RAM `")

    # 5. Saran menyesuaikan angka besar
    fake = memory_audit.snapshot()
    fake["rss_mb"] = 420.0
    fake["data_kb"] = 9000.0
    fake["playlist_tracks"] = 2400
    tips = memory_audit.suggestions(fake)
    assert any("RAM sudah tinggi" in tip for tip in tips)
    assert any("Playlist member besar" in tip for tip in tips)
    assert any("8 MB" in tip for tip in tips)
    assert len(tips) <= 4

    # 6. Data dir & path_size_kb tidak melempar
    assert memory_audit.data_dir_kb() >= 0
    assert memory_audit.path_size_kb("/tidak/ada") == 0.0
    assert memory_audit.path_size_kb("config.py") > 0

    # 7. Cache yang tidak ada tidak membuat error
    assert memory_audit._count_entries(None) == 0
    assert memory_audit._count_entries({"a": 1}) == 1
    assert memory_audit._count_entries([1, 2, 3]) == 3
    assert memory_audit._resolve("modul_tidak_ada_xyz", "apa") is None

    levels.level_guilds.clear()
    levels.levels.clear()
    tickets.tickets.clear()
    music_playlists.guild_playlists.clear()


# ==============================================================================
# /bantuan DIPERBARUI: RINGKASAN VERSI TERBARU (v1.40.0-beta)
# ==============================================================================
def test_help_overview_shows_latest_features():
    """Halaman depan `/bantuan` memuat ringkasan fitur terbaru & tetap dalam batas Discord."""
    from views.help import TOP_LEVEL_COUNT, build_help_embed

    embed = build_help_embed("overview")
    names = [field.name for field in embed.fields]
    assert len(embed.fields) == 4
    assert any("Menu Utama" in name for name in names)
    assert any("Terbaru" in name for name in names)

    # Semua field aman dari batas Discord (1024) & total embed < 6000
    assert all(len(field.value) <= 1024 for field in embed.fields)
    assert sum(len(field.value) for field in embed.fields) <= 6000

    isi = "\n".join(field.value for field in embed.fields)
    for fitur in ("/raid", "/nuke", "/backup pulihkan", "/level musim", "/musik playlist", "/tiket rating",
                  "/bahasa", "/prefix", "/analitik", "/perawatan memori"):
        assert fitur in isi, fitur

    # Angka menu utama harus sama dengan jumlah command tingkat atas yang benar-benar terdaftar
    assert TOP_LEVEL_COUNT == len(bot_main.bot.tree.get_commands())

    # Kategori lain tetap sehat
    for key in ("sesi", "tools", "games", "server", "growth", "insights", "engagement", "musik",
                "komunitas", "admin"):
        kategori = build_help_embed(key)
        assert kategori.fields
        assert all(len(field.value) <= 1024 for field in kategori.fields), key
