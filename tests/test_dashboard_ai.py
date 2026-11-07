"""Tes halaman AI dashboard: gambar, prompt server, & privasi owner-only."""

from __future__ import annotations

import base64
import io
import json
import socket
from types import SimpleNamespace

import aiohttp
import pytest

import ai_user_settings
import dashboard_admin
import dashboard_ai
import web_dashboard

GID = 781234
TOKEN = "tok-ai-dashboard"
CHANNEL_ID = 504
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    ai_user_settings.reset_state()
    dashboard_ai.reset_state()
    monkeypatch.setattr(ai_user_settings, "SETTINGS_FILE", tmp_path / "ai_settings.json")
    yield
    ai_user_settings.reset_state()
    dashboard_ai.reset_state()


class _Permissions:
    send_messages = True
    attach_files = True


class _Channel:
    def __init__(self, channel_id=CHANNEL_ID, name="gambar", *, allowed=True):
        self.id = channel_id
        self.name = name
        self.allowed = allowed
        self.sent = []

    def permissions_for(self, _member):
        return _Permissions() if self.allowed else SimpleNamespace(
            send_messages=False, attach_files=False
        )

    async def send(self, *, content, file):
        self.sent.append((content, file))
        return SimpleNamespace(id=99)


class _Guild:
    id = GID
    name = "Server AI"

    def __init__(self, channel=None):
        self.me = SimpleNamespace(id=99)
        self.text_channels = [channel] if channel else []

    def get_channel(self, channel_id):
        return next((c for c in self.text_channels if c.id == int(channel_id)), None)


class _Bot:
    def __init__(self, guild=None):
        self.guilds = [guild] if guild else []
        self.http_session = object()

    def get_guild(self, guild_id):
        return next((g for g in self.guilds if g.id == int(guild_id)), None)


class _Upload:
    def __init__(self, data: bytes, filename: str):
        self.file = io.BytesIO(data)
        self.filename = filename


def test_halaman_ai_memuat_panel_dan_form_tanpa_javascript():
    page = web_dashboard.render_dashboard_html(
        status={}, usage={}, levels={}, halaman="ai", token=TOKEN, guild_id=GID,
        gambar_block=dashboard_ai.render_gambar_block(
            _Bot(_Guild(_Channel(name="<script>umum</script>"))), GID, TOKEN
        ),
        ai_prompt_block=dashboard_ai.render_prompt_server_block(GID, TOKEN),
        ai_privasi_block=dashboard_ai.render_privasi_block(),
    )
    for anchor in ("p-gambar", "p-ai-settings", "p-privasi", "p-ai"):
        assert f'id="{anchor}"' in page
    assert 'action="/api/ai"' in page and 'enctype="multipart/form-data"' in page
    assert 'name="acuan"' in page and 'name="prompt_server"' in page
    assert "&lt;script&gt;umum&lt;/script&gt;" in page
    assert "<script>umum</script>" not in page
    assert "<script" not in page.lower() and "onclick" not in page.lower()
    assert "/dataku" in page and "/hapusdataku" in page
    # Token operator tidak bisa menyamar sebagai identitas member di form privasi.
    assert 'name="user_id"' not in page and 'name="member_id"' not in page


def test_editor_prompt_server_escape_nilai_dan_tidak_bocorkan_token_di_teks():
    ai_user_settings.set_server_prompt(GID, "Jawab <script>alert(1)</script>")
    html = dashboard_ai.render_prompt_server_block(GID, "<token>")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert 'value="&lt;token&gt;"' in html
    assert "maxlength=\"500\"" in html


def test_panel_gambar_mengikuti_channel_dan_pilihan_resmi():
    html = dashboard_ai.render_gambar_block(_Bot(_Guild(_Channel(name="studio"))), GID, TOKEN)
    assert f'value="{CHANNEL_ID}"' in html and "# studio" in html
    assert "Anime Style" in html and "Photorealistic" in html
    assert "16:9 (Landscape)" in html and "9:16 (Portrait/Story)" in html
    assert "Buat &amp; kirim gambar" in html
    assert "Gambar acuan untuk edit membutuhkan Gemini Paid Tier" in html


@pytest.mark.asyncio
async def test_prompt_server_disimpan_dan_bisa_dihapus():
    bot = _Bot(_Guild())
    teks = "  ramah   dan   gunakan contoh  "
    ok, pesan = await dashboard_ai.proses_aksi(
        bot, GID, {"action": "prompt-server", "prompt_server": teks}
    )
    assert ok and "disimpan" in pesan
    assert ai_user_settings.get_server_prompt(GID) == "ramah dan gunakan contoh"
    disk = json.loads(ai_user_settings.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert disk["servers"][str(GID)]["prompt"] == "ramah dan gunakan contoh"

    ok, pesan = await dashboard_ai.proses_aksi(
        bot, GID, {"action": "prompt-server", "prompt_server": "   "}
    )
    assert ok and "dihapus" in pesan
    assert ai_user_settings.get_server_prompt(GID) == ""


@pytest.mark.asyncio
async def test_prompt_server_menolak_prompt_terlalu_panjang():
    ok, pesan = await dashboard_ai.proses_aksi(
        _Bot(_Guild()), GID,
        {"action": "prompt-server", "prompt_server": "x" * (ai_user_settings.MAKS_PROMPT_SERVER + 1)},
    )
    assert not ok and "maksimal 500" in pesan
    assert not ai_user_settings.get_server_prompt(GID)

    # Token operator tidak dapat mengimpor/menghapus data member lewat ID.
    ok, pesan = await dashboard_ai.proses_aksi(
        _Bot(_Guild()), GID, {"action": "hapusdataku", "user_id": "987654321"}
    )
    assert not ok and "tidak dikenal" in pesan


@pytest.mark.asyncio
async def test_gambar_dibuat_dikirim_dan_dipakai_sebagai_acuan_edit(monkeypatch):
    import ai_handler
    from cogs import gambar_cog

    channel = _Channel()
    bot = _Bot(_Guild(channel))
    file = SimpleNamespace(fp=io.BytesIO(PNG), filename="hasil.png")
    calls = {}

    async def _generate(thread_id, prompt, **kwargs):
        calls.update(thread_id=thread_id, prompt=prompt, kwargs=kwargs)
        return "Mesin uji", file, None

    monkeypatch.setattr(ai_handler, "generate_image", _generate)
    ok, pesan = await dashboard_ai.proses_aksi(
        bot, GID, {
            "action": "gambar", "channel_id": str(CHANNEL_ID),
            "prompt": "  senja   di Surabaya  ", "style": "Anime",
            "ratio": "16:9 (Landscape)",
        },
    )
    assert ok and f"<#{CHANNEL_ID}>" in pesan
    assert calls["thread_id"] == CHANNEL_ID and calls["prompt"] == "senja di Surabaya"
    assert calls["kwargs"]["style"] == "Anime"
    assert calls["kwargs"]["ratio"] == "16:9 (Landscape)"
    assert calls["kwargs"]["reference_images"] is None
    assert calls["kwargs"]["http_session"] is bot.http_session
    assert len(channel.sent) == 1 and channel.sent[0][1] is file

    inline, filename = gambar_cog._terakhir[CHANNEL_ID]
    assert filename == "gambar-terakhir.png"
    assert base64.b64decode(inline["inlineData"]["data"]) == PNG


@pytest.mark.asyncio
async def test_gambar_acuan_validasi_mime_dan_tidak_disimpan(monkeypatch, tmp_path):
    import ai_handler
    import dashboard_unggah

    direktori_unggah = tmp_path / "uploads"
    monkeypatch.setattr(dashboard_unggah, "UPLOAD_DIR", direktori_unggah)
    channel = _Channel()
    bot = _Bot(_Guild(channel))
    file = SimpleNamespace(fp=io.BytesIO(PNG), filename="hasil.png")
    calls = {}

    async def _generate(_thread_id, _prompt, **kwargs):
        calls.update(kwargs)
        return "Mesin uji", file, None

    monkeypatch.setattr(ai_handler, "generate_image", _generate)
    ok, _ = await dashboard_ai.proses_aksi(
        bot, GID, {
            "action": "gambar", "channel_id": CHANNEL_ID,
            "prompt": "edit poster ini", "acuan": _Upload(PNG, "acuan.png"),
        },
    )
    assert ok
    assert base64.b64decode(calls["reference_images"][0]["inlineData"]["data"]) == PNG
    assert calls["reference_images"][0]["inlineData"]["mimeType"] == "image/png"
    assert not direktori_unggah.exists()


@pytest.mark.asyncio
async def test_gambar_menolak_acuan_palsu_channel_salah_dan_izin_kirim(monkeypatch):
    import ai_handler

    async def _unexpected(*_args, **_kwargs):
        pytest.fail("Generator tidak boleh dipanggil untuk input yang ditolak")

    monkeypatch.setattr(ai_handler, "generate_image", _unexpected)
    channel = _Channel(allowed=False)
    bot = _Bot(_Guild(channel))

    ok, pesan = await dashboard_ai.proses_aksi(
        bot, GID, {"action": "gambar", "channel_id": CHANNEL_ID, "prompt": "poster aman"},
    )
    assert not ok and "Send Messages" in pesan

    channel.allowed = True
    ok, pesan = await dashboard_ai.proses_aksi(
        bot, GID, {"action": "gambar", "channel_id": CHANNEL_ID, "prompt": "poster aman",
                   "acuan": _Upload(b"bukan gambar", "palsu.png")},
    )
    assert not ok and "bukan gambar" in pesan

    ok, pesan = await dashboard_ai.proses_aksi(
        bot, GID, {"action": "gambar", "channel_id": CHANNEL_ID + 1, "prompt": "poster aman"},
    )
    assert not ok and "channel teks" in pesan


@pytest.mark.asyncio
async def test_jeda_gambar_berlaku_per_server(monkeypatch):
    import ai_handler

    channel = _Channel()
    bot = _Bot(_Guild(channel))
    count = 0
    file = SimpleNamespace(fp=io.BytesIO(PNG), filename="hasil.png")

    async def _generate(*_args, **_kwargs):
        nonlocal count
        count += 1
        return "Mesin uji", file, None

    monkeypatch.setattr(ai_handler, "generate_image", _generate)
    payload = {"action": "gambar", "channel_id": CHANNEL_ID, "prompt": "poster taman kota"}
    ok, _ = await dashboard_ai.proses_aksi(bot, GID, payload)
    assert ok
    ok, pesan = await dashboard_ai.proses_aksi(bot, GID, payload)
    assert not ok and "Tunggu" in pesan and count == 1


async def test_endpoint_ai_memerlukan_token_dan_audit_tidak_menyimpan_prompt(monkeypatch, tmp_path):
    import ai_handler

    channel = _Channel()
    guild = _Guild(channel)
    bot = _Bot(guild)
    file = SimpleNamespace(fp=io.BytesIO(PNG), filename="hasil.png")

    async def _generate(*_args, **_kwargs):
        return "Mesin uji", file, None

    monkeypatch.setattr(ai_handler, "generate_image", _generate)
    monkeypatch.setattr(dashboard_admin, "AUDIT_FILE", tmp_path / "audit.json")
    dashboard_admin.reset_cache()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", TOKEN)

    assert await web_dashboard.start_dashboard(bot) is True
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            payload = {
                "guild": GID, "action": "prompt-server",
                "prompt_server": "TEKS-RAHASIA-UNTUK-TES",
            }
            async with session.post(f"http://127.0.0.1:{port}/api/ai", json=payload) as response:
                assert response.status == 401
            async with session.post(
                f"http://127.0.0.1:{port}/api/ai", json=payload,
                headers={"X-Dashboard-Token": TOKEN},
            ) as response:
                data = await response.json()
                assert response.status == 200 and data["ok"]
                assert "disimpan" in data["message"]
            async with session.post(
                f"http://127.0.0.1:{port}/api/ai",
                json={"guild": GID, "action": "gambar", "channel_id": CHANNEL_ID,
                      "prompt": "SENSITIVE_IMAGE_PROMPT"},
                headers={"X-Dashboard-Token": TOKEN},
            ) as response:
                data = await response.json()
                assert response.status == 200 and data["ok"]
    finally:
        await web_dashboard.stop_dashboard()
        dashboard_admin.reset_cache()

    audit = (tmp_path / "audit.json").read_text(encoding="utf-8")
    assert "ai.prompt-server" in audit and "ai.gambar" in audit
    assert "TEKS-RAHASIA-UNTUK-TES" not in audit
    assert "SENSITIVE_IMAGE_PROMPT" not in audit
    assert base64.b64encode(PNG).decode("ascii") not in audit
    assert ai_user_settings.get_server_prompt(GID) == "TEKS-RAHASIA-UNTUK-TES"
