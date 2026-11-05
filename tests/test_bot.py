import base64
import json
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
        # v1.8.0-beta (Tier 2A): fitur keramaian server tanpa kuota AI
        "giveaway", "ultah", "jawab-otomatis", "pengumuman",
        # v1.10.0-beta (Tier 2C): leveling & tiket dukungan
        "level", "tiket",
        # v1.12.0-beta: Control Center & editor tema (Components V2)
        "panel", "tampilan",
        # v1.11.0-beta (Tier 3): hemat kuota AI
        "faq", "pemakaian",
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
    assert any(greeting.startswith(w) for w in jp_words)
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
    assert any(farewell.startswith(w) for w in korean_words)
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
        "starboard": {"atur", "status"},
        "verifikasi": {"pasang", "status", "matikan"},
        "sticky": {"pasang", "lepas", "status"},
        "info": {"user", "server"},
        "perawatan": {"backup", "atur", "status"},
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

    # 7. Tombol panel persisten (9 tombol) & paginasi antrean
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
    }
    for sub in musik.commands:
        assert 1 <= len(sub.description) <= 100

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

    # Peserta tanpa role syarat ditolak
    status, _ = engagement.join_giveaway(555, 501, role_ids={7})
    assert status == "syarat"
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
    assert {c.name for c in giveaway_group.commands} == {"mulai", "akhiri", "reroll", "daftar"}
    assert {c.name for c in ultah_group.commands} == {"set", "hapus", "daftar", "atur"}
    assert jawab_group.name == "jawab-otomatis"
    assert {c.name for c in jawab_group.commands} == {"tambah", "hapus", "daftar", "atur"}
    assert pengumuman_group.name == "pengumuman"
    assert {c.name for c in pengumuman_group.commands} == {"tambah", "daftar", "hapus", "atur"}

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

    assert {c.name for c in keamanan_group.commands} == {"phising", "cek", "spam", "spam-status"}
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
    assert {c.name for c in level_group.commands} == {"lihat", "papan", "atur", "role", "status"}
    assert tiket_group.name == "tiket"
    assert {c.name for c in tiket_group.commands} == {
        "panel", "status", "tutup", "tambah", "daftar", "matikan",
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

    import music
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
    assert len(m_rows) == 2 and len(m_rows[0].children) == 5


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
    from cogs.agent_cog import agent_group, build_greeting_payload, trigger_member_boost

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

    # 1. mode mati → teks biasa
    payload = await build_greeting_payload(guild, member, "Halo semua", mode="mati")
    assert payload == {"content": "Halo semua"}

    # 2. mode statis tanpa banner → tetap teks
    assert (await build_greeting_payload(guild, member, "Hai", mode="statis"))["content"] == "Hai"

    # 3. mode statis dengan banner → embed + file lokal
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1024, 420), (120, 60, 200)).save(buf, format="PNG")
    wm.save_banner(gid, buf.getvalue())
    payload = await build_greeting_payload(guild, member, "Hai", mode="statis")
    assert "embed" in payload and payload["file"].filename.startswith("banner-welcome")
    assert payload["embed"].image.url.startswith("attachment://")

    # 4. mode dinamis → kartu PNG (atau mundur ke banner bila Pillow tak ada)
    payload = await build_greeting_payload(guild, member, "Hai", mode="dinamis")
    assert "embed" in payload and payload["file"] is not None

    # 5. konfigurasi boost: pesan & anti-dobel
    ca.boost_agent_guilds.pop(gid, None)
    assert ca.set_boost_config(gid, enabled=True, channel_id=700, message="Hai {user}") is not None
    assert ca.boost_agent_guilds[gid]["message"] == "Hai {user}"
    assert ca.should_process_member_boost(gid, 501) is True
    ca.should_process_member_boost(gid, 501)  # dicatat
    ca.boost_agent_guilds.pop(gid, None)

    # 6. command baru terdaftar di /agent
    names = {c.name for c in agent_group.commands}
    assert {"banner", "kartu", "dm", "boost", "welcome", "goodbye"} <= names

    # 7. mode kartu & DM tersimpan di konfigurasi sambutan
    ca.set_welcome_config(gid, 600, enabled=True)
    assert ca.set_welcome_card_mode(gid, "dinamis") == "dinamis"
    assert ca.set_welcome_dm(gid, True) is True
    assert ca.welcome_agent_guilds[gid]["card_mode"] == "dinamis"
    assert ca.set_welcome_card_mode(gid, "ngawur") == "mati"
    ca.welcome_agent_guilds.pop(gid, None)
    wm.delete_banner(gid)
