import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ya"}


def _env_time_slots(name: str, default: list[str], max_slots: int = 6) -> list[str]:
    """Membaca daftar slot jam dari `.env` (misal: "08:00,12:00,16:00,20:00" atau "8,12,16,20")."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return list(default)

    found: list[str] = []
    for chunk in re.split(r"[,;\s]+", raw):
        match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", chunk) or re.fullmatch(r"(\d{1,2})", chunk)
        if not match:
            continue
        groups = match.groups()
        hour = int(groups[0])
        minute = int(groups[1]) if len(groups) > 1 else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            found.append(f"{hour:02d}:{minute:02d}")

    cleaned = sorted(set(found))[:max_slots]
    return cleaned or list(default)


BOT_VERSION = "1.40.0-beta"

# ==============================================================================
# KREDENSIAL UTAMA (Mendukung nama variabel standar maupun template Wispbyte)
# ==============================================================================
DISCORD_BOT_TOKEN: str = (
    os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN") or ""
).strip()
GEMINI_API_KEY: str = (os.getenv("GEMINI_API_KEY") or "").strip()
DISCORD_GUILD_ID: int | None = _env_int("DISCORD_GUILD_ID", 0, minimum=0) or None


def parse_gemini_keys(raw_value: str) -> list[str]:
    """Mendukung 1 API key maupun multi-API key dipisahkan koma (rotasi otomatis saat 429)."""
    return [
        k.strip()
        for k in (raw_value or "").split(",")
        if k.strip() and not k.strip().startswith("masukkan_")
    ]


# ==============================================================================
# PENGATURAN MODEL GEMINI (OPTIMAL FREE TIER: CEPAT, STABIL, ANTI-503)
# ==============================================================================
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Default menggunakan gemini-3.5-flash-lite & gemini-3.1-flash-lite yang super cepat (~1 detik)
# dan stabil bebas antrean 503 di Free Tier Google AI Studio
GEMINI_DEFAULT_MODEL: str = (
    os.getenv("GEMINI_DEFAULT_MODEL") or "gemini-3.5-flash-lite"
).strip()
GEMINI_FAST_MODEL: str = (
    os.getenv("GEMINI_FAST_MODEL") or "gemini-3.1-flash-lite"
).strip()
GEMINI_REASONING_MODEL: str = (
    os.getenv("GEMINI_REASONING_MODEL") or "gemini-3.6-flash"
).strip()
GEMINI_IMAGE_MODEL: str = (
    os.getenv("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-lite-image"
).strip()

# Model khusus untuk Google Search Grounding (gemini-2.5-flash & 2.5-flash-lite mendukung 500 RPD GRATIS di Free Tier!)
GEMINI_SEARCH_MODEL: str = (
    os.getenv("GEMINI_SEARCH_MODEL") or "gemini-2.5-flash"
).strip()

# Rantai model cadangan berbeda (tanpa alias duplikat) jika salah satu model penuh/503
GEMINI_TEXT_FALLBACK_CHAIN: list[str] = [
    GEMINI_DEFAULT_MODEL,
    GEMINI_FAST_MODEL,
    GEMINI_REASONING_MODEL,
    "gemini-2.5-flash",
    "gemini-3.8-flash",
]

GEMINI_SEARCH_FALLBACK_CHAIN: list[str] = [
    GEMINI_SEARCH_MODEL,
    "gemini-2.5-flash-lite",
    GEMINI_DEFAULT_MODEL,
]

GEMINI_IMAGE_FALLBACK_CHAIN: list[str] = [
    GEMINI_IMAGE_MODEL,
    "gemini-nano-banana-2.1",
]

# Pada Free Tier, model gambar Nano Banana & tool Google Search berbayar dilewati langsung agar instan & bebas error kuota 0.
# Ubah GEMINI_PAID_IMAGE_ENABLED / GEMINI_PAID_SEARCH_ENABLED=true di .env hanya jika akun Google AI Studio Anda sudah Paid/Billing.
GEMINI_PAID_IMAGE_ENABLED: bool = _env_bool("GEMINI_PAID_IMAGE_ENABLED", False)
GEMINI_PAID_SEARCH_ENABLED: bool = _env_bool("GEMINI_PAID_SEARCH_ENABLED", False)
ENABLE_IMAGE_FALLBACK: bool = _env_bool("ENABLE_IMAGE_FALLBACK", True)
ENABLE_GOOGLE_SEARCH: bool = _env_bool("ENABLE_GOOGLE_SEARCH", True)
ENABLE_URL_READER: bool = _env_bool("ENABLE_URL_READER", True)

MAX_HISTORY_MESSAGES: int = _env_int("MAX_HISTORY_MESSAGES", 30, minimum=4)
MAX_THREADS_PER_USER: int = _env_int("MAX_THREADS_PER_USER", 3, minimum=1)
SESSION_EXPIRE_DAYS: int = _env_int("SESSION_EXPIRE_DAYS", 7, minimum=0)
MAX_CONCURRENT_MEDIA_TASKS: int = _env_int("MAX_CONCURRENT_MEDIA_TASKS", 2, minimum=1)

# Batas aman lampiran Vision, Audio/Voice Note, Video, Stiker & file kode (menjaga RAM tetap ringan di Wispbyte)
MAX_IMAGE_ATTACHMENT_BYTES: int = 8 * 1024 * 1024  # 8 MB per gambar
MAX_AUDIO_ATTACHMENT_BYTES: int = 12 * 1024 * 1024  # 12 MB per Voice Note / file audio
MAX_VIDEO_ATTACHMENT_BYTES: int = 15 * 1024 * 1024  # 15 MB per video klip pendek (Galeri)
MAX_PDF_ATTACHMENT_BYTES: int = 10 * 1024 * 1024  # 10 MB per dokumen PDF
MAX_STICKER_EMOJI_BYTES: int = 2 * 1024 * 1024  # 2 MB untuk stiker / custom emoji
MAX_IMAGES_PER_MESSAGE: int = 4
MAX_TEXT_ATTACHMENT_BYTES: int = 100 * 1024  # 100 KB per file teks/kode
MAX_WEBPAGE_FETCH_BYTES: int = 256 * 1024  # 256 KB batas aman pembaca halaman web

# Proteksi kuota Free Tier: jeda wajar per member pada command berat (Admin otomatis bebas jeda; 0 = nonaktif)
USER_COMMAND_COOLDOWN_SEC: int = _env_int("USER_COMMAND_COOLDOWN_SEC", 10, minimum=0)

# Pengaturan Default AI Community Agent (Auto-Chat, Pemecah Sepi, & Galeri)
BOT_TIMEZONE: str = (os.getenv("BOT_TIMEZONE") or "Asia/Jakarta").strip()
AGENT_DEFAULT_IDLE_MINUTES: int = _env_int("AGENT_DEFAULT_IDLE_MINUTES", 30, minimum=0)
AGENT_MAX_IDLE_POKES: int = _env_int("AGENT_MAX_IDLE_POKES", 1, minimum=1)
AGENT_CHANNEL_COOLDOWN_SEC: float = 3.0
AGENT_HISTORY_MESSAGES: int = _env_int("AGENT_HISTORY_MESSAGES", 20, minimum=4)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
AGENT_CONFIG_FILE = DATA_DIR / "agent_config.json"
GAME_SCORES_FILE = DATA_DIR / "game_scores.json"
SERVER_FEATURES_FILE = DATA_DIR / "server_features.json"
COMMUNITY_TOOLS_FILE = DATA_DIR / "community_tools.json"
MUSIC_SETTINGS_FILE = DATA_DIR / "music_settings.json"
ENGAGEMENT_FILE = DATA_DIR / "engagement.json"
ANTISPAM_FILE = DATA_DIR / "antispam.json"
LEVELS_FILE = DATA_DIR / "levels.json"
TRANSLATE_FILE = DATA_DIR / "translate.json"
AUDIT_FILE = DATA_DIR / "audit.json"
ECONOMY_FILE = DATA_DIR / "economy.json"
GROWTH_FILE = DATA_DIR / "growth.json"
MENU_FILE = DATA_DIR / "menus.json"
ANTINUKE_FILE = DATA_DIR / "antinuke.json"
RAID_FILE = DATA_DIR / "raid.json"
MUSIC_PLAYLISTS_FILE = DATA_DIR / "music_playlists.json"
I18N_FILE = DATA_DIR / "i18n.json"
PREFIX_FILE = DATA_DIR / "prefixes.json"
ANALYTICS_FILE = DATA_DIR / "analytics.json"
COMMAND_PREFIX = "!"
AI_USAGE_FILE = DATA_DIR / "ai_usage.json"
TICKETS_FILE = DATA_DIR / "tickets.json"
# Gambar kustom (banner sambutan/perpisahan/boost) — file biner, bukan JSON
MEDIA_DIR = DATA_DIR / "media"
SOCIAL_FILE = DATA_DIR / "social.json"
MODERATION_FILE = DATA_DIR / "moderation.json"
TEMP_VOICE_FILE = DATA_DIR / "temp_voice.json"
AFK_FILE = DATA_DIR / "afk.json"

# ==============================================================================
# FITUR SERVER (Server Stats, Auto Role, Fakta Harian, & Anti-Phishing)
# ==============================================================================
# Penjaga link phishing aktif secara default agar server aman sejak hari pertama.
ENABLE_PHISHING_GUARD: bool = _env_bool("ENABLE_PHISHING_GUARD", True)
# Interval pembaruan nama Voice Channel statistik (detik). Discord membatasi 2 rename / 10 menit per channel,
# jadi nilai minimum aman adalah 600 detik (10 menit).
SERVERSTATS_UPDATE_SEC: int = _env_int("SERVERSTATS_UPDATE_SEC", 600, minimum=600)
# Notifikasi sosial (YouTube/Twitch/TikTok). Twitch butuh aplikasi gratis dari dev.twitch.tv;
# YouTube & feed RSS tidak butuh kredensial apa pun. Biaya AI: 0 (pesan memakai template).
TWITCH_CLIENT_ID: str = (os.getenv("TWITCH_CLIENT_ID") or "").strip()
TWITCH_CLIENT_SECRET: str = (os.getenv("TWITCH_CLIENT_SECRET") or "").strip()
SOCIAL_CHECK_SEC: int = _env_int("SOCIAL_CHECK_SEC", 300, minimum=60)
# Jadwal default rubrik Fakta Unik Dunia: 4 slot per hari (pagi, siang, sore, malam).
# Bisa diubah kapan saja oleh Admin lewat Discord: /fakta atur channel:#umum jadwal:08:00,12:00,16:00,20:00
FACTS_MAX_SLOTS: int = min(8, _env_int("FACTS_MAX_SLOTS", 6, minimum=1))
FACTS_DEFAULT_TIMES: list[str] = _env_time_slots(
    "FACTS_DEFAULT_TIMES",
    ["08:00", "12:00", "16:00", "20:00"],
    max_slots=FACTS_MAX_SLOTS,
)
# Jumlah maksimal role yang otomatis diberikan saat member bergabung
AUTOROLE_MAX_ROLES: int = _env_int("AUTOROLE_MAX_ROLES", 3, minimum=1)

# ==============================================================================
# FITUR KOMUNITAS RINGAN (Reaction Role, Poll, Reminder, Starboard, Verifikasi, Sticky)
# ==============================================================================
# Semua fitur di bawah ini GRATIS (tanpa kuota Gemini) & default NONAKTIF sampai Admin menyalakannya.
STARBOARD_EMOJI: str = (os.getenv("STARBOARD_EMOJI") or "⭐").strip() or "⭐"
STARBOARD_DEFAULT_THRESHOLD: int = _env_int("STARBOARD_DEFAULT_THRESHOLD", 3, minimum=1)
REMINDER_MAX_PER_USER: int = _env_int("REMINDER_MAX_PER_USER", 15, minimum=1)
# Jeda minimum (detik) sebelum pesan sticky diturunkan ulang agar channel tidak dibanjiri bot
STICKY_MIN_INTERVAL_SEC: int = _env_int("STICKY_MIN_INTERVAL_SEC", 5, minimum=1)
# ==============================================================================
# HEMAT KUOTA AI (Tier 3) — rekap ber-cache, pemakaian, & FAQ lokal
# ==============================================================================
# Batas operasi AI per member per hari (0 = tanpa batas). Hanya menghitung
# operasi yang benar-benar memanggil Gemini; cache hit & FAQ lokal tidak dihitung.
AI_DAILY_CAP_PER_USER: int = _env_int("AI_DAILY_CAP_PER_USER", 0, minimum=0)
# Batas harian per SERVER (0 = tanpa batas). Melindungi kuota bersama Free Tier:
# satu member yang spam tidak bisa menghabiskan kuota seluruh server.
AI_DAILY_CAP_PER_GUILD: int = _env_int("AI_DAILY_CAP_PER_GUILD", 0, minimum=0)
# Cache jawaban untuk pertanyaan identik di channel yang sama (detik). 0 = matikan.
AI_REPLY_CACHE_TTL_SEC: int = _env_int("AI_REPLY_CACHE_TTL_SEC", 900, minimum=0)
AI_REPLY_CACHE_MAX: int = _env_int("AI_REPLY_CACHE_MAX", 200, minimum=10)
# Berapa hari catatan pemakaian disimpan (agar file JSON tetap kecil)
AI_USAGE_KEEP_DAYS: int = _env_int("AI_USAGE_KEEP_DAYS", 7, minimum=1)
# Cache hasil `/ringkas channel` (detik). 0 = cache dimatikan.
REKAP_CACHE_TTL_SEC: int = _env_int("REKAP_CACHE_TTL_SEC", 1800, minimum=0)
# Batas jumlah pesan yang dianalisis saat membuat rekap berperiode
REKAP_MAX_MESSAGES: int = _env_int("REKAP_MAX_MESSAGES", 400, minimum=20)

# ==============================================================================
# LEVELING & XP (Tier 2C) — default NONAKTIF
# ==============================================================================
# XP per pesan (acak antara min & max) + jeda per member agar tidak bisa dispam.
LEVELS_XP_MIN: int = _env_int("LEVELS_XP_MIN", 15, minimum=1)
LEVELS_XP_MAX: int = _env_int("LEVELS_XP_MAX", 25, minimum=1)
LEVELS_COOLDOWN_SEC: int = _env_int("LEVELS_COOLDOWN_SEC", 60, minimum=0)
# Batas atas level agar perhitungan tetap cepat & wajar
LEVELS_MAX_LEVEL: int = _env_int("LEVELS_MAX_LEVEL", 100, minimum=5)
# Jumlah member teratas yang disimpan per server (menjaga file JSON tetap kecil)
LEVELS_MAX_MEMBERS: int = _env_int("LEVELS_MAX_MEMBERS", 500, minimum=25)
# XP Voice: XP per menit berada di voice channel (0 kuota AI).
LEVELS_VOICE_XP_PER_MIN: int = _env_int("LEVELS_VOICE_XP_PER_MIN", 2, minimum=1)
# Batas menit voice yang dihitung per member per hari (0 = tanpa batas, tidak disarankan).
LEVELS_VOICE_DAILY_CAP_MIN: int = _env_int("LEVELS_VOICE_DAILY_CAP_MIN", 240, minimum=0)

# ==============================================================================
# DASHBOARD WEB READ-ONLY (status & /pemakaian) — default NONAKTIF
# ==============================================================================
# Port HTTP dashboard. Kosong/0 = coba ambil dari SERVER_PORT/PORT panel hosting.
# Dashboard hanya menyala bila DASHBOARD_TOKEN juga diisi.
DASHBOARD_PORT: int = _env_int("DASHBOARD_PORT", 0, minimum=0)
DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST") or "0.0.0.0"
# Token rahasia di URL (?token=...) — WAJIB diisi untuk mengaktifkan dashboard.
DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN") or ""
# Interval auto-refresh halaman (detik).
DASHBOARD_REFRESH_SEC: int = _env_int("DASHBOARD_REFRESH_SEC", 30, minimum=5)

# ==============================================================================
# SISTEM TIKET DUKUNGAN (Tier 2C) — default NONAKTIF
# ==============================================================================
# Tiket dibuat sebagai Private Thread (tidak memakan slot channel server).
TICKET_MAX_OPEN_PER_USER: int = _env_int("TICKET_MAX_OPEN_PER_USER", 2, minimum=1)
TICKET_MAX_TRANSCRIPT_LINES: int = _env_int("TICKET_MAX_TRANSCRIPT_LINES", 400, minimum=50)
TICKET_AUTO_CLOSE_HOURS: int = _env_int("TICKET_AUTO_CLOSE_HOURS", 0, minimum=0)

# ==============================================================================
# ANTI-SPAM & ANTI-RAID RINGAN (Tier 2B) — default LAPOR SAJA
# ==============================================================================
# Penjaga spam hanya aktif setelah Admin menyalakannya lewat /keamanan spam.
# Ambang di bawah adalah nilai awal & bisa diubah per server dari Discord.
SPAM_FLOOD_COUNT: int = _env_int("SPAM_FLOOD_COUNT", 6, minimum=3)
SPAM_FLOOD_WINDOW_SEC: int = _env_int("SPAM_FLOOD_WINDOW_SEC", 10, minimum=3)
SPAM_MENTION_LIMIT: int = _env_int("SPAM_MENTION_LIMIT", 6, minimum=2)
SPAM_LINK_LIMIT: int = _env_int("SPAM_LINK_LIMIT", 4, minimum=1)
# Huruf kapital berlebihan sengaja NONAKTIF secara bawaan (sering salah tuduh)
SPAM_CAPS_MIN_LENGTH: int = _env_int("SPAM_CAPS_MIN_LENGTH", 20, minimum=8)
# Durasi time-out maksimum saat mode "timeout" dipilih (detik, maks 1 hari)
SPAM_TIMEOUT_SEC: int = min(86400, _env_int("SPAM_TIMEOUT_SEC", 300, minimum=60))
# Deteksi raid: jumlah join dalam jendela waktu sebelum Admin diberi peringatan
SPAM_RAID_JOIN_COUNT: int = _env_int("SPAM_RAID_JOIN_COUNT", 8, minimum=3)
SPAM_RAID_WINDOW_SEC: int = _env_int("SPAM_RAID_WINDOW_SEC", 60, minimum=10)

# ==============================================================================
# FITUR ENGAGEMENT (Giveaway, Ulang Tahun, Auto-Responder, Pengumuman Terjadwal)
# ==============================================================================
# Semua fitur di bawah ini GRATIS (tanpa kuota Gemini) & default NONAKTIF.
# Batas jumlah aturan/pesan dibuat kecil agar file data/engagement.json tetap ringan.
AUTO_REPLY_MAX_RULES: int = _env_int("AUTO_REPLY_MAX_RULES", 25, minimum=1)
# Jeda aman (detik) agar auto-responder tidak pernah membanjiri channel
AUTO_REPLY_COOLDOWN_SEC: int = _env_int("AUTO_REPLY_COOLDOWN_SEC", 20, minimum=0)
# Batas pengumuman terjadwal per server
ANNOUNCEMENT_MAX_PER_GUILD: int = _env_int("ANNOUNCEMENT_MAX_PER_GUILD", 15, minimum=1)
# Batas giveaway selesai yang tetap disimpan (agar JSON tetap kecil)
GIVEAWAY_HISTORY_MAX: int = _env_int("GIVEAWAY_HISTORY_MAX", 25, minimum=1)

# Backup konfigurasi otomatis: interval hari (0 = matikan) & channel log error global
BACKUP_INTERVAL_DAYS: int = _env_int("BACKUP_INTERVAL_DAYS", 7, minimum=0)
BOT_LOG_CHANNEL_ID: int = _env_int("BOT_LOG_CHANNEL_ID", 0, minimum=0)

# ==============================================================================
# STREAMING MUSIK (LAVALINK v4 + WAVELINK — TANPA FFMPEG LOKAL)
# ==============================================================================
# Wispbyte tidak menyediakan FFmpeg/yt-dlp, jadi audio didelegasikan ke node Lavalink v4.
# Kosongkan `LAVALINK_URI` bila belum ingin memakai fitur musik (command /musik tetap muncul
# dan hanya menampilkan panduan setup, bot tetap ringan).
LAVALINK_URI: str = (os.getenv("LAVALINK_URI") or "").strip()
LAVALINK_PASSWORD: str = (os.getenv("LAVALINK_PASSWORD") or "").strip()
LAVALINK_NODE_NAME: str = (os.getenv("LAVALINK_NODE_NAME") or "utama").strip() or "utama"
# Fitur musik dianggap aktif hanya bila URI & password node sudah diisi
MUSIC_ENABLED: bool = bool(LAVALINK_URI and LAVALINK_PASSWORD)
# Volume default saat bot bergabung ke voice channel (1-150)
MUSIC_DEFAULT_VOLUME: int = min(150, _env_int("MUSIC_DEFAULT_VOLUME", 60, minimum=1))
# Batas jumlah lagu dalam antrean agar RAM tetap kecil
MUSIC_MAX_QUEUE: int = _env_int("MUSIC_MAX_QUEUE", 50, minimum=1)
# Putus otomatis dari voice channel setelah sekian detik tanpa lagu (hemat resource)
MUSIC_IDLE_DISCONNECT_SEC: int = _env_int("MUSIC_IDLE_DISCONNECT_SEC", 300, minimum=30)

# ==============================================================================
# DAFTAR MODE / PERSONA AI (MURNI GOOGLE GEMINI - RESPONS CEPAT)
# ==============================================================================
AI_MODELS: dict[str, dict] = {
    "gemini_flash": {
        "name": "♊ Gemini Flash (Asisten Utama)",
        "short_label": "Gemini Flash (Utama)",
        "description": "Asisten cerdas, cepat & serba bisa + analisis gambar (Vision)",
        "emoji": "♊",
        "model_id": GEMINI_DEFAULT_MODEL,
        "thinking_level": "low",
        "temperature": 0.7,
        "system_prompt": (
            "Kamu adalah AI Assistant berbasis Google Gemini di server Discord ini yang ramah, "
            "cerdas, dan sangat membantu. Jawablah dalam bahasa Indonesia yang santai, sopan, "
            "jelas, dan rapi menggunakan format Markdown Discord seperlunya. Jika pengguna "
            "melampirkan gambar atau file teks/kode, analisis isinya secara teliti dan akurat."
        ),
    },
    "gemini_fast": {
        "name": "⚡ Gemini Flash-Lite (Respon Kilat)",
        "short_label": "Gemini Flash-Lite (Kilat)",
        "description": "Respon instan < 1.5 detik & hemat kuota untuk tanya-jawab singkat",
        "emoji": "⚡",
        "model_id": GEMINI_FAST_MODEL,
        "thinking_level": "minimal",
        "temperature": 0.6,
        "system_prompt": (
            "Kamu adalah asisten AI Google Gemini berkecepatan tinggi. Jawablah setiap pertanyaan "
            "secara ringkas, padat, langsung ke inti (to-the-point), namun tetap ramah dalam bahasa Indonesia."
        ),
    },
    "gemini_coder": {
        "name": "💻 Gemini - Pakar Koding & Debug",
        "short_label": "Gemini Pakar Koding",
        "description": "Spesialis pemrograman, arsitektur kode & debug error",
        "emoji": "💻",
        "model_id": GEMINI_REASONING_MODEL,
        "thinking_level": "medium",
        "temperature": 0.3,
        "system_prompt": (
            "Kamu adalah Senior Software Engineer & AI spesialis pemrograman berbasis Google Gemini. "
            "Jawablah pertanyaan koding secara terstruktur, berikan contoh kode yang bersih, aman, "
            "dan modern menggunakan blok kode Markdown lengkap dengan penanda bahasa (misal ```python). "
            "Jelaskan akar masalah bug dan logika solusinya secara jelas dalam bahasa Indonesia."
        ),
    },
    "gemini_logic": {
        "name": "🧠 Gemini - Penalaran & Riset",
        "short_label": "Gemini Penalaran & Riset",
        "description": "Analisis mendalam, logika, matematika & pemecahan masalah",
        "emoji": "🧠",
        "model_id": GEMINI_REASONING_MODEL,
        "thinking_level": "medium",
        "temperature": 0.4,
        "system_prompt": (
            "Kamu adalah asisten riset dan analis logika berbasis Google Gemini. Uraikan permasalahan "
            "kompleks langkah demi langkah secara sistematis, objektif, akurat, dan terstruktur. "
            "Sangat unggul dalam penalaran logika, matematika, sains, dan perencanaan dalam bahasa Indonesia."
        ),
    },
    "gemini_curhat": {
        "name": "🛋️ Gemini - Teman Curhat",
        "short_label": "Gemini Teman Curhat",
        "description": "Empati tinggi, pendengar hangat, aman & suportif",
        "emoji": "🛋️",
        "model_id": GEMINI_DEFAULT_MODEL,
        "thinking_level": "minimal",
        "temperature": 0.85,
        "system_prompt": (
            "Kamu adalah Teman Curhat yang sangat empatik, hangat, pendengar yang baik, tidak menghakimi, "
            "dan suportif. Berikan respons yang menenangkan, memvalidasi perasaan pengguna, dan ramah "
            "layaknya sahabat dekat dalam bahasa Indonesia yang natural."
        ),
    },
}

# Pemetaan otomatis jika ada sesi lama yang masih memakai ID model versi terdahulu
LEGACY_MODEL_ALIASES: dict[str, str] = {
    "groq_llama70b": "gemini_logic",
    "groq_fast": "gemini_fast",
    "qwen_coder": "gemini_coder",
}


def resolve_model_key(model_key: str | None) -> str:
    if not model_key:
        return "gemini_flash"
    mapped = LEGACY_MODEL_ALIASES.get(model_key, model_key)
    return mapped if mapped in AI_MODELS else "gemini_flash"


# ==============================================================================
# DAFTAR GAYA ART & RASIO GAMBAR
# ==============================================================================
STYLE_OPTIONS: dict[str, dict[str, str]] = {
    "Biasa": {
        "label": "Biasa / Default",
        "emoji": "🖼️",
        "prompt": "",
    },
    "Anime": {
        "label": "Anime Style",
        "emoji": "⛩️",
        "prompt": ", anime style, highly detailed Japanese animation, vibrant colors, crisp lineart, studio anime aesthetic",
    },
    "Cyberpunk": {
        "label": "Cyberpunk Futuristic",
        "emoji": "🏙️",
        "prompt": ", cyberpunk style, neon lights, futuristic metropolis, highly detailed, dramatic cinematic lighting",
    },
    "Photorealistic": {
        "label": "Photorealistic (Foto Asli)",
        "emoji": "📸",
        "prompt": ", photorealistic, ultra realistic DSLR photography, natural lighting, sharp focus, 8k detail",
    },
    "3D Render": {
        "label": "3D Render (Pixar/Blender)",
        "emoji": "🧊",
        "prompt": ", 3d render style, blender 3d, pixar animation aesthetic, octane render, soft studio lighting",
    },
    "Pixel Art": {
        "label": "Pixel Art Retro",
        "emoji": "👾",
        "prompt": ", detailed 16-bit pixel art, retro game aesthetic, crisp pixels, vibrant palette",
    },
    "Watercolor": {
        "label": "Lukisan Cat Air (Watercolor)",
        "emoji": "🎨",
        "prompt": ", artistic watercolor painting on textured paper, soft brush strokes, dreamy pastel colors",
    },
}

STYLE_PROMPTS: dict[str, str] = {k: v["prompt"] for k, v in STYLE_OPTIONS.items()}

RATIO_OPTIONS: dict[str, dict] = {
    "1:1 (Persegi)": {
        "label": "1:1 (Persegi - Default)",
        "emoji": "⏹️",
        "aspect_ratio": "1:1",
        "dimensions": (1024, 1024),
    },
    "16:9 (Landscape)": {
        "label": "16:9 (Landscape / Banner)",
        "emoji": "🖼️",
        "aspect_ratio": "16:9",
        "dimensions": (1280, 720),
    },
    "9:16 (Portrait/Story)": {
        "label": "9:16 (Portrait / Story HP)",
        "emoji": "📱",
        "aspect_ratio": "9:16",
        "dimensions": (720, 1280),
    },
    "4:3 (Klasik)": {
        "label": "4:3 (Foto Klasik)",
        "emoji": "📺",
        "aspect_ratio": "4:3",
        "dimensions": (1152, 864),
    },
    "3:4 (Poster)": {
        "label": "3:4 (Poster / Potret)",
        "emoji": "📋",
        "aspect_ratio": "3:4",
        "dimensions": (864, 1152),
    },
}

RATIO_DIMENSIONS: dict[str, tuple[int, int]] = {
    k: v["dimensions"] for k, v in RATIO_OPTIONS.items()
}

DEFAULT_IMAGE_SETTINGS: dict[str, str] = {
    "style": "Biasa",
    "ratio": "1:1 (Persegi)",
}
