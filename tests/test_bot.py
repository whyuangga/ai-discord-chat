import base64
import json
import pytest
import discord

import config
import storage
import utils
import ai_handler
import community_agent
import games
import views
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
    storage.thread_chats.clear()
    storage.image_thread_settings.clear()
    storage._closing_threads.clear()
    community_agent.guild_agent_settings.clear()
    community_agent.chat_agent_channels.clear()
    community_agent.gallery_agent_channels.clear()
    community_agent.youtube_agent_channels.clear()
    community_agent.search_agent_channels.clear()
    community_agent.welcome_agent_guilds.clear()
    community_agent.digest_agent_guilds.clear()
    community_agent._recent_welcomed_members.clear()
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
    community_agent.digest_agent_guilds.clear()
    community_agent._recent_welcomed_members.clear()
    community_agent.channel_histories.clear()
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
    cmd_names = {cmd.name for cmd in bot_main.bot.tree.get_commands()}
    assert {"setup_panel", "reset", "model", "status", "ringkas"}.issubset(cmd_names)


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
    assert {"cari", "ringkas_link", "game", "bantuan"}.issubset(top_names)
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

    monkeypatch.setattr(bot_main, "analyze_link_with_gemini", _fake_analyze_link)
    monkeypatch.setattr(bot_main, "search_web_with_gemini", _fake_search_web)

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
    owner_ix = type(
        "Ix",
        (),
        {
            "channel": fake_thread,
            "user": _FakeUser(501, "PemilikPost"),
            "response": _FakeResp(),
            "followup": _FakeFollowup(),
            "message": None,
        },
    )()
    await btn.callback(owner_ix)
    assert owner_ix.response.deferred is True
    assert len(edited_calls) == 1
    assert edited_calls[0]["archived"] is True
    assert edited_calls[0]["name"] == "✅ Error login aplikasi"
    assert t_solved in edited_calls[0]["applied_tags"]
    assert btn.disabled is True


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
    status_emb = views.build_agent_status_embed(fake_guild)
    assert "v1.3.0-beta" in status_emb.title
    assert any("FAQ" in f.name for f in status_emb.fields)










