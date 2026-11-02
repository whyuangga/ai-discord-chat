import base64
import json
import pytest
import discord

import config
import storage
import utils
import ai_handler
import community_agent
import views
import main as bot_main


class FakeMockResponse:
    def __init__(self, status: int, json_data=None, raw_bytes: bytes = b"", headers=None):
        self.status = status
        self._json_data = json_data
        self._raw_bytes = raw_bytes
        self.headers = headers or {}

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

    def get(self, url, timeout=None):
        self.get_calls.append({"url": url})
        return self.get_responses.pop(0)


@pytest.fixture(autouse=True)
def clean_storage_state(tmp_path, monkeypatch):
    sessions_path = tmp_path / "sessions.json"
    agent_cfg_path = tmp_path / "agent_config.json"
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "SESSIONS_FILE", sessions_path)
    monkeypatch.setattr(community_agent, "DATA_DIR", tmp_path)
    monkeypatch.setattr(community_agent, "AGENT_CONFIG_FILE", agent_cfg_path)
    storage.thread_chats.clear()
    storage.image_thread_settings.clear()
    storage._closing_threads.clear()
    community_agent.guild_agent_settings.clear()
    community_agent.chat_agent_channels.clear()
    community_agent.gallery_agent_channels.clear()
    community_agent.channel_histories.clear()
    ai_handler.clear_model_cooldowns()
    yield
    storage.thread_chats.clear()
    storage.image_thread_settings.clear()
    storage._closing_threads.clear()
    community_agent.guild_agent_settings.clear()
    community_agent.chat_agent_channels.clear()
    community_agent.gallery_agent_channels.clear()
    community_agent.channel_histories.clear()
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
    assert {"setup_panel", "reset", "model", "status"}.issubset(cmd_names)


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
    assert {"chat", "gallery", "persona", "sapa", "status"} == sub_names


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
        http_session=fake_http,
    )
    assert "sepi amat" in text
    assert community_agent.chat_agent_channels[5000]["consecutive_idle_pokes"] == 1


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



