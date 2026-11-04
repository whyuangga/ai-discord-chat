"""Streaming musik Discord via **Lavalink** (tanpa FFmpeg lokal).

Wispbyte hanya menjalankan satu proses Python tanpa FFmpeg/yt-dlp, sehingga
pemutaran audio didelegasikan ke **Lavalink v4** (node eksternal). Modul ini
memakai library `wavelink` sebagai klien Lavalink.

Fitur **default NONAKTIF**: bila `LAVALINK_URI`/`LAVALINK_PASSWORD` belum diisi,
seluruh command `/musik` tetap muncul tetapi menjawab dengan panduan setup —
bot tetap jalan normal tanpa error.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path

import discord

from config import (
    DATA_DIR,
    LAVALINK_NODE_NAME,
    LAVALINK_PASSWORD,
    LAVALINK_URI,
    MUSIC_DEFAULT_VOLUME,
    MUSIC_ENABLED,
    MUSIC_IDLE_DISCONNECT_SEC,
    MUSIC_MAX_QUEUE,
    MUSIC_SETTINGS_FILE,
)
from utils import sanitize_error_message

try:  # Library opsional: bot tetap hidup walau wavelink belum terpasang.
    import wavelink

    WAVELINK_AVAILABLE = True
except Exception:  # pragma: no cover - dependensi belum terpasang
    wavelink = None  # type: ignore[assignment]
    WAVELINK_AVAILABLE = False

logger = logging.getLogger("gemini_bot.music")

MUSIC_FILE: Path = MUSIC_SETTINGS_FILE
_music_lock = asyncio.Lock()

# guild_id -> {"volume": int, "announce": bool, "dj_role_id": int|None, "last_track": str}
music_guilds: dict[int, dict] = {}
# guild_id -> channel_id tempat "Now Playing" diumumkan (runtime, tidak perlu persisten)
announce_channels: dict[int, int] = {}

MUSIC_SETUP_HINT = (
    "🎵 **Fitur musik belum aktif.**\n"
    "Isi variabel berikut di panel **Variables Wispbyte** (atau `.env`):\n"
    "```\n"
    "LAVALINK_URI=nama-node:2333\n"
    "LAVALINK_PASSWORD=password-node\n"
    "```\n"
    "• `LAVALINK_URI` menerima `host:port`, `http(s)://…`, atau `ws(s)://…`\n"
    "• Butuh **Lavalink v4** (gratis). Wispbyte tidak menyediakan node musik, "
    "jadi pakai node publik gratis atau host Lavalink sendiri (Docker 1 baris).\n"
    "Setelah variabel diisi, restart bot. Panduan lengkap ada di **README bagian F**."
)

SOURCE_LABELS: dict[str, str] = {
    "youtube": "▶️ YouTube",
    "youtubemusic": "🎵 YouTube Music",
    "spotify": "🟢 Spotify",
    "soundcloud": "🟠 SoundCloud",
    "applemusic": "🍎 Apple Music",
    "deezer": "🎧 Deezer",
    "twitch": "🟣 Twitch",
    "bandcamp": "🔵 Bandcamp",
    "http": "🌐 Link Langsung",
    "local": "📁 Berkas Lokal",
}

LOOP_MODES: dict[str, str] = {
    "mati": "🔁 Mati (putar sekali)",
    "satu": "🔂 Ulangi Lagu Ini",
    "semua": "🔁 Ulangi Semua Antrean",
}


# ==============================================================================
# PERSISTENSI PENGATURAN MUSIK PER SERVER
# ==============================================================================
def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_music_settings() -> dict:
    return {
        "volume": MUSIC_DEFAULT_VOLUME,
        "announce": True,
        "dj_role_id": None,
        "last_track": "",
    }


def load_music_settings_from_disk() -> int:
    """Memuat pengaturan musik per server. Mengembalikan jumlah server yang dimuat."""
    music_guilds.clear()
    if not MUSIC_FILE.exists():
        return 0
    try:
        raw = json.loads(MUSIC_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", MUSIC_FILE, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            music_guilds[int(gid_str)] = {
                "volume": max(1, min(150, _to_int(data.get("volume"), MUSIC_DEFAULT_VOLUME))),
                "announce": bool(data.get("announce", True)),
                "dj_role_id": _to_int(data.get("dj_role_id")) or None,
                "last_track": str(data.get("last_track") or "")[:300],
            }
        except (TypeError, ValueError):
            continue
    return len(music_guilds)


async def save_music_settings_to_disk() -> None:
    """Menyimpan pengaturan musik secara atomik."""
    async with _music_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(k): v for k, v in music_guilds.items()}}
            tmp_file = MUSIC_FILE.with_suffix(".json.tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, MUSIC_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan music_settings.json: %s", sanitize_error_message(exc))


def get_music_settings(guild_id: int) -> dict:
    """Mengambil (atau membuat) pengaturan musik sebuah server."""
    cfg = music_guilds.get(guild_id)
    if cfg is None:
        cfg = default_music_settings()
        music_guilds[guild_id] = cfg
    return cfg


def set_music_settings(
    guild_id: int,
    *,
    volume: int | None = None,
    announce: bool | None = None,
    dj_role_id: object = None,
    last_track: str | None = None,
) -> dict:
    cfg = get_music_settings(guild_id)
    if volume is not None:
        cfg["volume"] = max(1, min(150, int(volume)))
    if announce is not None:
        cfg["announce"] = bool(announce)
    if dj_role_id is not None:
        cfg["dj_role_id"] = _to_int(dj_role_id) or None
    if last_track is not None:
        cfg["last_track"] = str(last_track)[:300]
    return cfg


# ==============================================================================
# KONEKSI NODE LAVALINK
# ==============================================================================
def normalize_lavalink_uri(raw_uri: str | None, *, secure: bool = False) -> str | None:
    """Merapikan URI Lavalink: `host:2333`, `http://host:port`, `ws://…` ➔ URI websocket."""
    text = str(raw_uri or "").strip()
    if not text:
        return None

    secure_flag = secure or text.lower().startswith(("https://", "wss://"))
    text = re.sub(r"(?i)^(https?|wss?)://", "", text).strip().rstrip("/")
    if not text:
        return None
    if not re.search(r":\d{2,5}$", text):
        text = f"{text}:2333"
    return f"{'wss' if secure_flag else 'ws'}://{text}"


def music_status() -> str:
    """Ringkasan status musik untuk `/status` & `/musik status`."""
    if not WAVELINK_AVAILABLE:
        return "❗ Library `wavelink` belum terpasang"
    if not MUSIC_ENABLED:
        return "⛔ Belum dikonfigurasi (isi LAVALINK_URI & LAVALINK_PASSWORD)"
    return "✅ Siap memutar musik"


def build_nodes() -> list:
    """Membuat daftar node Lavalink dari konfigurasi `.env`."""
    if not (WAVELINK_AVAILABLE and MUSIC_ENABLED):
        return []
    uri = normalize_lavalink_uri(LAVALINK_URI)
    if not uri:
        return []
    return [
        wavelink.Node(
            identifier=LAVALINK_NODE_NAME or "utama",
            uri=uri,
            password=LAVALINK_PASSWORD,
            inactive_player_timeout=MUSIC_IDLE_DISCONNECT_SEC,
            retries=3,
        )
    ]


async def connect_nodes(client: discord.Client) -> bool:
    """Menghubungkan bot ke seluruh node Lavalink. `False` bila gagal/tak dikonfigurasi."""
    nodes = build_nodes()
    if not nodes:
        logger.info("Musik dilewati: LAVALINK_URI/LAVALINK_PASSWORD belum diisi.")
        return False
    try:
        await wavelink.Pool.connect(nodes=nodes, client=client, cache_capacity=100)
        logger.info("Menghubungkan ke Lavalink: %s", nodes[0].uri)
        return True
    except Exception as exc:  # pragma: no cover - node mati
        logger.warning("Gagal terhubung ke Lavalink: %s", sanitize_error_message(exc))
        return False


def get_player(guild: discord.Guild | None):
    """Mengambil player wavelink yang sedang aktif di sebuah server (jika ada)."""
    if guild is None or not WAVELINK_AVAILABLE:
        return None
    voice_client = getattr(guild, "voice_client", None)
    if voice_client is not None and isinstance(voice_client, wavelink.Player):
        return voice_client
    return None


# ==============================================================================
# UTILITAS TAMPILAN
# ==============================================================================
def format_duration(ms: int | float | None) -> str:
    """Mengubah milidetik menjadi `m:ss` atau `h:mm:ss`."""
    if ms is None or ms <= 0:
        return "0:00"
    total = int(ms) // 1000
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def source_label(track) -> str:
    """Label sumber lagu (YouTube, Spotify, dsb.)."""
    source = str(getattr(track, "source", "") or "").lower()
    return SOURCE_LABELS.get(source, f"🎵 {source.title()}" if source else "🎵 Audio")


def track_url(track) -> str | None:
    uri = str(getattr(track, "uri", "") or "")
    return uri if uri.startswith("http") else None


def track_title(track, limit: int = 70) -> str:
    title = str(getattr(track, "title", "Tanpa judul") or "Tanpa judul")
    return title if len(title) <= limit else title[: limit - 1] + "…"


def track_requester_name(track) -> str:
    extras = getattr(track, "extras", None) or {}
    try:
        return str(extras.get("requester") or "—")
    except AttributeError:
        return str(getattr(extras, "requester", "—"))


def mark_requester(track, user: discord.abc.User) -> None:
    """Menyimpan nama peminta lagu pada track (muncul di Now Playing)."""
    extras = getattr(track, "extras", None)
    if extras is None:
        return
    try:
        extras["requester"] = getattr(user, "display_name", "Member")
        extras["requester_id"] = int(getattr(user, "id", 0))
    except (TypeError, AttributeError):  # pragma: no cover - extras tidak mendukung dict
        pass


def build_now_playing_embed(
    track,
    *,
    requester: str | None = None,
    queue_length: int = 0,
    volume: int | None = None,
    paused: bool = False,
    loop_label: str | None = None,
) -> discord.Embed:
    """Embed Now Playing yang dipakai saat memutar & `/musik sekarang`."""
    author = str(getattr(track, "author", "") or "")
    length = getattr(track, "length", 0) or 0
    is_stream = bool(getattr(track, "is_stream", False))
    duration = "🔴 LIVE" if is_stream else format_duration(length)

    embed = discord.Embed(
        title=("⏸️ " if paused else "🎶 ") + track_title(track, 100),
        description=f"**{author[:100]}**" if author else "",
        color=discord.Color.purple(),
        url=track_url(track),
    )
    embed.add_field(name="⏱️ Durasi", value=f"`{duration}`", inline=True)
    embed.add_field(name="🎧 Diminta oleh", value=str(requester or track_requester_name(track))[:80], inline=True)
    embed.add_field(name="📜 Antrean", value=f"`{queue_length}` lagu", inline=True)
    if volume is not None:
        embed.add_field(name="🔊 Volume", value=f"`{volume}%`", inline=True)
    if loop_label:
        embed.add_field(name="🔁 Mode", value=loop_label, inline=True)
    embed.add_field(name="📡 Sumber", value=source_label(track), inline=True)

    artwork = str(getattr(track, "artwork", "") or "")
    if artwork.startswith("http"):
        embed.set_thumbnail(url=artwork)
    embed.set_footer(text="Streaming via Lavalink • /musik bantuan untuk daftar command")
    return embed


def build_queue_embed(
    tracks: list,
    *,
    total_length: int = 0,
    limit: int = 10,
    now_playing=None,
) -> discord.Embed:
    """Embed daftar antrean (maks `limit` lagu per halaman)."""
    embed = discord.Embed(
        title="📜 Antrean Musik",
        color=discord.Color.blurple(),
        description=f"**{len(tracks)}** lagu • total `{format_duration(total_length)}`",
    )
    if not tracks:
        embed.description = "Antrean masih kosong. Tambahkan dengan `/musik putar`."
        return embed

    lines = []
    for idx, track in enumerate(tracks[:limit], start=1):
        length = "LIVE" if getattr(track, "is_stream", False) else format_duration(getattr(track, "length", 0))
        lines.append(f"`{idx}.` [{track_title(track, 55)}]({track_url(track) or 'https://discord.com'}) — `{length}`")
    embed.add_field(name="Berikutnya", value="\n".join(lines)[:1024], inline=False)
    if len(tracks) > limit:
        embed.set_footer(text=f"+{len(tracks) - limit} lagu lain di antrean")
    if now_playing is not None:
        embed.add_field(
            name="🎶 Sedang Diputar",
            value=f"[{track_title(now_playing, 60)}]({track_url(now_playing) or 'https://discord.com'})",
            inline=False,
        )
    return embed


def build_search_embed(query: str, tracks: list) -> discord.Embed:
    """Embed hasil pencarian `/musik cari`."""
    embed = discord.Embed(
        title=f"🔎 Hasil Pencarian: {query[:150]}",
        description=f"Ditemukan **{len(tracks)}** hasil. Pilih satu lagu pada menu di bawah.",
        color=discord.Color.teal(),
    )
    for idx, track in enumerate(tracks[:5], start=1):
        length = "LIVE" if getattr(track, "is_stream", False) else format_duration(getattr(track, "length", 0))
        embed.add_field(
            name=f"{idx}. {track_title(track, 70)}",
            value=f"{str(getattr(track, 'author', '') or '—')[:70]} • `{length}` • {source_label(track)}",
            inline=False,
        )
    embed.set_footer(text="Pilih lagu pada dropdown untuk memutar • berlaku 60 detik")
    return embed


def queue_mode_from_key(key: str | None):
    """Menerjemahkan pilihan `mati`/`satu`/`semua` menjadi `QueueMode` wavelink."""
    mapping = {"mati": "normal", "satu": "loop", "semua": "loop_all"}
    name = mapping.get(str(key or "").lower().strip(), "normal")
    if not WAVELINK_AVAILABLE:
        return None
    return getattr(wavelink.QueueMode, name)


def loop_label_from_mode(mode_value: object) -> str:
    """Label mode pengulangan dari `QueueMode` wavelink."""
    name = getattr(mode_value, "name", str(mode_value or "normal"))
    return {
        "normal": LOOP_MODES["mati"],
        "loop": LOOP_MODES["satu"],
        "loop_all": LOOP_MODES["semua"],
    }.get(str(name), LOOP_MODES["mati"])


# ==============================================================================
# PENCARIAN & PEMUTARAN
# ==============================================================================
class MusicUnavailable(Exception):
    """Dilempar saat fitur musik belum siap (tanpa node / library)."""


async def search_tracks(query: str) -> tuple[list, str | None]:
    """Mencari lagu/playlist lewat Lavalink. Mengembalikan `(tracks, nama_playlist)`."""
    if not WAVELINK_AVAILABLE or not MUSIC_ENABLED:
        raise MusicUnavailable(MUSIC_SETUP_HINT)

    clean = str(query or "").strip()
    if not clean:
        return [], None

    try:
        result = await wavelink.Playable.search(clean)
    except Exception as exc:
        raise MusicUnavailable(
            f"⚠️ Node musik tidak merespons: `{sanitize_error_message(exc)[:120]}`"
        ) from exc

    if not result:
        return [], None
    playlist_name = getattr(result, "name", None) if isinstance(result, wavelink.Playlist) else None
    tracks = list(result)
    return tracks, playlist_name


async def ensure_player(interaction: discord.Interaction):
    """Memastikan bot sudah berada di voice channel pengguna. `(player, pesan_error)`."""
    if not WAVELINK_AVAILABLE or not MUSIC_ENABLED:
        return None, MUSIC_SETUP_HINT

    guild = interaction.guild
    if guild is None:
        return None, "⚠️ Command musik hanya bisa dipakai di dalam server."

    voice_state = getattr(getattr(interaction, "user", None), "voice", None)
    target_channel = getattr(voice_state, "channel", None)
    if target_channel is None:
        return None, "⚠️ Masuk ke **voice channel** dulu, lalu jalankan command ini lagi."

    player = get_player(guild)
    if player is not None and getattr(player, "channel", None) is not None:
        if player.channel.id != getattr(target_channel, "id", None):
            return None, (
                f"⚠️ Bot sedang memutar musik di {player.channel.mention}. "
                "Masuk ke channel itu atau hentikan dulu dengan `/musik hentikan`."
            )
        return player, None

    try:
        player = await target_channel.connect(cls=wavelink.Player, self_deaf=True)
    except Exception as exc:  # pragma: no cover - izin voice kurang
        return None, (
            "⚠️ Gagal bergabung ke voice channel. Pastikan bot punya izin "
            f"**Connect** & **Speak**.\n`{sanitize_error_message(exc)[:120]}`"
        )

    settings = get_music_settings(guild.id)
    try:
        await player.set_volume(int(settings.get("volume") or MUSIC_DEFAULT_VOLUME))
    except Exception:  # pragma: no cover - node belum siap
        pass
    return player, None


async def enqueue_tracks(player, tracks: list, user: discord.abc.User) -> tuple[int, int]:
    """Menambahkan lagu ke antrean (dibatasi `MUSIC_MAX_QUEUE`). Mengembalikan `(ditambah, dilewati)`."""
    added = 0
    skipped = 0
    for track in tracks:
        if len(player.queue) >= MUSIC_MAX_QUEUE:
            skipped += 1
            continue
        mark_requester(track, user)
        await player.queue.put_wait(track)
        added += 1
    return added, skipped


async def play_first_if_idle(player, tracks: list, user: discord.abc.User) -> bool:
    """Memutar track pertama bila player sedang kosong. `True` bila langsung diputar."""
    if not tracks:
        return False
    if getattr(player, "current", None) is None:
        mark_requester(tracks[0], user)
        await player.play(tracks[0])
        return True
    return False


def can_control(player, member: discord.Member) -> bool:
    """Apakah member boleh mengontrol pemutaran (DJ role, admin, atau satu voice channel)."""
    if player is None:
        return False
    if getattr(member, "guild_permissions", None) and (
        member.guild_permissions.administrator or member.guild_permissions.manage_guild
    ):
        return True

    guild_id = getattr(getattr(player, "guild", None), "id", 0)
    dj_role_id = _to_int((music_guilds.get(guild_id) or {}).get("dj_role_id"))
    if dj_role_id and any(role.id == dj_role_id for role in getattr(member, "roles", [])):
        return True

    member_channel = getattr(getattr(member, "voice", None), "channel", None)
    player_channel = getattr(player, "channel", None)
    return bool(member_channel and player_channel and member_channel.id == player_channel.id)


def remember_announce_channel(guild_id: int, channel_id: int) -> None:
    announce_channels[int(guild_id)] = int(channel_id)


def forget_announce_channel(guild_id: int) -> None:
    announce_channels.pop(int(guild_id), None)


def cleanup_music_runtime() -> int:
    """Membersihkan channel pengumuman yang sudah tidak dipakai (hemat RAM)."""
    cleaned = 0
    for gid in list(announce_channels.keys()):
        if gid not in music_guilds:
            announce_channels.pop(gid, None)
            cleaned += 1
    return cleaned
