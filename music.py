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
import time
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
# guild_id -> channel_id tempat panel pemutar dikirim (runtime, tidak perlu persisten)
announce_channels: dict[int, int] = {}
# guild_id -> {"channel_id": int, "message_id": int, "updated_at": float} panel pemutar Rythm-style
music_panels: dict[int, dict] = {}

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
    "Setelah variabel diisi, restart bot. Panduan lengkap ada di **`docs/fitur.md` bagian F**."
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

FILTER_PRESETS: dict[str, str] = {
    "off": "🔇 Tanpa Filter",
    "bassboost": "🔊 Bass Boost",
    "nightcore": "🌙 Nightcore",
    "vaporwave": "🌊 Vaporwave",
    "8d": "🎧 8D Audio",
    "karaoke": "🎤 Karaoke",
    "treble": "✨ Treble Boost",
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
        "filter": "off",
        "autoplay": False,
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
                "filter": str(data.get("filter") or "off") if str(data.get("filter") or "off") in FILTER_PRESETS else "off",
                "autoplay": bool(data.get("autoplay", False)),
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
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan music_settings.json")


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
    filter_name: str | None = None,
    autoplay: bool | None = None,
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
    if filter_name is not None and str(filter_name) in FILTER_PRESETS:
        cfg["filter"] = str(filter_name)
    if autoplay is not None:
        cfg["autoplay"] = bool(autoplay)
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


# node_diagnosis() dipakai di beberapa tempat; import Enum dilakukan lazy agar aman
# ketika wavelink belum terpasang.
def _status_name(status: object) -> str:
    """Label status node (`CONNECTED`/`CONNECTING`/`DISCONNECTED`) tanpa bergantung pada Enum."""
    if status is None:
        return "UNKNOWN"
    return str(getattr(status, "name", status)).upper()


def node_snapshot() -> dict:
    """Kondisi node Lavalink **saat ini** (tanpa memanggil API apa pun).

    Mengembalikan dict: `library`, `configured`, `uri`, `nodes[]`, `connected`,
    `connecting`, `disconnected`, `ready`.
    """
    snapshot: dict = {
        "library": bool(WAVELINK_AVAILABLE),
        "configured": bool(MUSIC_ENABLED),
        "uri": normalize_lavalink_uri(LAVALINK_URI),
        "nodes": [],
        "connected": 0,
        "connecting": 0,
        "disconnected": 0,
        "ready": False,
    }
    if not WAVELINK_AVAILABLE:
        return snapshot

    try:
        pool_nodes = list(wavelink.Pool.nodes.values())
    except Exception:  # pragma: no cover - pool belum siap
        pool_nodes = []

    for node in pool_nodes:
        name = _status_name(getattr(node, "status", None))
        try:
            players = len(getattr(node, "players", {}) or {})
        except Exception:  # pragma: no cover - atribut internal berbeda antar versi
            players = 0
        snapshot["nodes"].append(
            {
                "identifier": str(getattr(node, "identifier", "?")),
                "uri": str(getattr(node, "uri", "?")),
                "status": name,
                "players": players,
            }
        )
        if name == "CONNECTED":
            snapshot["connected"] += 1
        elif name == "CONNECTING":
            snapshot["connecting"] += 1
        else:
            snapshot["disconnected"] += 1

    snapshot["ready"] = snapshot["connected"] > 0
    return snapshot


def node_diagnosis() -> str:
    """Penjelasan singkat kenapa node belum siap + langkah perbaikannya (Bahasa Indonesia)."""
    snap = node_snapshot()
    if not snap["library"]:
        return "Library `wavelink` belum terpasang — jalankan `pip install -r requirements.txt`."
    if not snap["configured"]:
        return "`LAVALINK_URI` & `LAVALINK_PASSWORD` belum diisi di Variables Wispbyte."
    if snap["ready"]:
        node = next((n for n in snap["nodes"] if n["status"] == "CONNECTED"), snap["nodes"][0])
        return (
            f"✅ Node `{node['identifier']}` tersambung ({node['uri']}, "
            f"{node['players']} player aktif)."
        )

    uri = snap["uri"] or "?"
    hints: list[str] = []
    if snap["connecting"]:
        hints.append(
            "node sudah menerima koneksi tetapi belum mengirim sinyal `ready` "
            "(biasanya node publik sedang kelebihan beban / baru restart)"
        )
    if uri.startswith("ws://") and uri.endswith(":443"):
        hints.append("port **443** tanpa awalan `wss://` sering gagal — tulis `wss://host:443`")
    if uri.startswith("wss://") and not uri.endswith(":443"):
        hints.append("`wss://` biasanya hanya untuk port **443**; untuk port lain pakai `host:port` tanpa awalan")
    if not snap["nodes"]:
        hints.append(
            "tidak ada node yang terdaftar di Pool → password salah, host/port keliru, "
            "atau koneksi keluar diblokir hosting"
        )
    if not hints:
        hints.append("node terdaftar tetapi berstatus DISCONNECTED → coba `/musik node sambung:True`")

    return (
        f"⚠️ **Lavalink belum tersambung** (`{uri}`).\n"
        "• Periksa: " + "; ".join(hints) + ".\n"
        "• Tes cepat di Console Wispbyte: "
        f"`curl -s -m 15 -H \"Authorization: password-node\" "
        f"{uri.replace('wss://', 'https://').replace('ws://', 'http://')}/v4/info`\n"
        "• Setelah `.env` diperbaiki → **Restart** bot, lalu cek `/musik status`."
    )


def music_status() -> str:
    """Ringkasan status musik untuk `/status` & `/musik status` (berbasis kondisi node nyata)."""
    if not WAVELINK_AVAILABLE:
        return "❗ Library `wavelink` belum terpasang"
    if not MUSIC_ENABLED:
        return "⛔ Belum dikonfigurasi (isi LAVALINK_URI & LAVALINK_PASSWORD)"

    snap = node_snapshot()
    if snap["ready"]:
        node = next((n for n in snap["nodes"] if n["status"] == "CONNECTED"), None) or {}
        return (
            f"✅ Tersambung — node `{node.get('identifier', '?')}` "
            f"({node.get('players', 0)} player)"
        )
    if snap["connecting"]:
        return "⏳ Node sedang menyambung (menunggu sinyal `ready` dari Lavalink)"
    if snap["nodes"]:
        return "⚠️ Node terdaftar tapi TIDAK tersambung (cek password, port, atau TLS)"
    return "⚠️ Belum tersambung — tidak ada node Lavalink aktif"


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
    """Menghubungkan bot ke seluruh node Lavalink. `False` bila gagal/tak dikonfigurasi.

    Catatan penting: `wavelink.Pool.connect` **tidak** melempar error saat password/port
    salah — kegagalan hanya muncul di log library. Karena itu setelah connect kita periksa
    sendiri status node lalu cetak diagnosa yang bisa ditindaklanjuti.
    """
    nodes = build_nodes()
    if not nodes:
        logger.info("Musik dilewati: LAVALINK_URI/LAVALINK_PASSWORD belum diisi.")
        return False

    target = getattr(nodes[0], "uri", LAVALINK_URI)
    logger.info("Menghubungkan ke Lavalink: %s", target)
    last_error = ""
    try:
        await wavelink.Pool.connect(nodes=nodes, client=client, cache_capacity=100)
    except Exception as exc:  # pragma: no cover - node mati
        last_error = sanitize_error_message(exc)
        logger.warning("Gagal terhubung ke Lavalink: %s", last_error)

    snap = node_snapshot()
    if snap["ready"]:
        node = next((n for n in snap["nodes"] if n["status"] == "CONNECTED"), None) or {}
        logger.info(
            "✅ Node Lavalink siap: %s (%s) | %s player",
            node.get("identifier", LAVALINK_NODE_NAME),
            target,
            node.get("players", 0),
        )
        return True

    if snap["nodes"]:
        logger.warning(
            "Node Lavalink %s terdaftar tetapi belum CONNECTED (status: %s). "
            "Menunggu sinyal 'ready'; bila berlanjut, periksa password/port/TLS.",
            target,
            ", ".join(f"{n['identifier']}={n['status']}" for n in snap["nodes"]),
        )
        return True

    logger.warning(
        "❌ Node Lavalink tidak terdaftar di Pool (%s). %s",
        target,
        last_error or "Periksa LAVALINK_PASSWORD, host/port, dan awalan wss:// untuk port 443.",
    )
    return False


_last_reconnect_at: float = 0.0
RECONNECT_COOLDOWN_SEC = 60


async def ensure_nodes_alive(client: discord.Client | None = None, *, force: bool = False) -> bool:
    """Memastikan minimal satu node CONNECTED; mencoba menyambung ulang bila perlu.

    Dipakai oleh watcher latar (tanpa loop baru) agar node publik yang restart
    otomatis pulih tanpa harus me-restart bot. Dibatasi `RECONNECT_COOLDOWN_SEC`
    supaya tidak membanjiri node dengan percobaan koneksi.
    """
    global _last_reconnect_at

    if not (WAVELINK_AVAILABLE and MUSIC_ENABLED):
        return False

    if node_snapshot()["ready"]:
        return True

    now = time.monotonic()
    if not force and (now - _last_reconnect_at) < RECONNECT_COOLDOWN_SEC:
        return False
    _last_reconnect_at = now

    try:
        pool_nodes = list(wavelink.Pool.nodes.values()) if WAVELINK_AVAILABLE else []
    except Exception:  # pragma: no cover - pool belum siap
        pool_nodes = []

    if not pool_nodes:
        if client is None:
            return False
        logger.info("Mencoba menyambung ulang node Lavalink (Pool kosong)…")
        return await connect_nodes(client)

    logger.info("Node Lavalink belum siap — mencoba menyambung ulang…")
    for node in pool_nodes:
        if _status_name(getattr(node, "status", None)) == "CONNECTED":
            continue
        try:
            await node.close()
        except Exception as exc:  # pragma: no cover - sudah tertutup
            logger.debug("Efek samping opsional gagal: %s", exc)
    try:
        await wavelink.Pool.reconnect()
    except Exception as exc:  # pragma: no cover - node mati
        logger.warning("Gagal menyambung ulang Lavalink: %s", sanitize_error_message(exc))
        return False
    return node_snapshot()["ready"]


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
    except (TypeError, AttributeError) as exc:  # pragma: no cover - extras tidak mendukung dict
        logger.debug("extras tidak mendukung dict: %s", exc)


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

    # Pra-cek: tanpa node CONNECTED, wavelink hanya melempar pesan teknis
    # "No nodes are currently assigned to the wavelink.Pool in a CONNECTED state".
    if not node_snapshot()["ready"]:
        await ensure_nodes_alive()
        if not node_snapshot()["ready"]:
            raise MusicUnavailable(
                "🎵 **Musik belum bisa diputar** — node Lavalink belum tersambung.\n"
                + node_diagnosis()
            )

    try:
        result = await wavelink.Playable.search(clean)
    except Exception as exc:
        detail = sanitize_error_message(exc)
        if "CONNECTED state" in detail or "Node" in detail:
            raise MusicUnavailable(
                "🎵 **Node musik terputus saat mencari lagu.**\n" + node_diagnosis()
            ) from exc
        raise MusicUnavailable(
            f"⚠️ Node musik tidak merespons: `{detail[:120]}`"
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
    except Exception as exc:  # pragma: no cover - node belum siap
        logger.debug("Efek samping opsional gagal: %s", exc)
    # Terapkan kembali filter audio & autoplay yang tersimpan untuk server ini
    saved_filter = settings.get("filter", "off")
    if saved_filter and saved_filter != "off":
        await apply_filter(player, saved_filter)
    if settings.get("autoplay"):
        set_autoplay(player, True)
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


# ==============================================================================
# PANEL PEMUTAR GAYA RYTHM (progress bar hidup + tombol kontrol)
# ==============================================================================
BAR_FILLED = "▬"
BAR_KNOB = "🔘"

_BASS_BANDS: dict[int, float] = {0: 0.3, 1: 0.25, 2: 0.2, 3: 0.12, 4: 0.08}
_TREBLE_BANDS: dict[int, float] = {10: 0.1, 11: 0.16, 12: 0.22, 13: 0.26, 14: 0.3}


def build_progress_bar(position_ms: int | float | None, length_ms: int | float | None, size: int = 14) -> str:
    """Progress bar ala Rythm: `▬▬▬🔘▬▬▬▬▬▬▬▬`."""
    total = max(0, int(length_ms or 0))
    position = max(0, int(position_ms or 0))
    ratio = 0.0 if total <= 0 else max(0.0, min(1.0, position / total))
    knob = max(0, min(size, int(round(ratio * size))))
    return f"{BAR_FILLED * knob}{BAR_KNOB}{BAR_FILLED * (size - knob)}"


def build_filters(kind: str | None):
    """Membangun objek `Filters` Lavalink untuk preset tertentu (`off` = reset)."""
    if not WAVELINK_AVAILABLE:
        return None
    filters = wavelink.Filters()
    preset = str(kind or "off").lower().strip()
    if preset == "bassboost":
        filters.equalizer.set(bands=[{"band": b, "gain": g} for b, g in _BASS_BANDS.items()])
    elif preset == "treble":
        filters.equalizer.set(bands=[{"band": b, "gain": g} for b, g in _TREBLE_BANDS.items()])
    elif preset == "nightcore":
        filters.timescale.set(speed=1.2, pitch=1.2, rate=1.0)
    elif preset == "vaporwave":
        filters.timescale.set(speed=0.85, pitch=0.85, rate=1.0)
    elif preset == "8d":
        filters.rotation.set(rotation_hz=0.2)
    elif preset == "karaoke":
        filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
    return filters


async def apply_filter(player, kind: str | None) -> bool:
    """Menerapkan preset filter ke player. `False` bila gagal/node tidak mendukung."""
    filters = build_filters(kind)
    if filters is None or player is None:
        return False
    try:
        await player.set_filters(filters)
        return True
    except Exception as exc:  # pragma: no cover - node lama tanpa filter
        logger.info("Gagal menerapkan filter %s: %s", kind, sanitize_error_message(exc))
        return False


def parse_seek(raw: str | None) -> int | None:
    """Membaca posisi lompat: `90`, `1:30`, atau `01:02:03` ➔ milidetik."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text) * 1000

    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in numbers):
        return None
    if len(numbers) == 2:
        minutes, seconds = numbers
        total = minutes * 60 + seconds
    else:
        hours, minutes, seconds = numbers
        total = hours * 3600 + minutes * 60 + seconds
    return total * 1000


def autoplay_label(enabled: bool) -> str:
    return "♾️ Autoplay" if enabled else "➡️ Autoplay mati"


def build_player_embed(
    player,
    *,
    track=None,
    filter_name: str | None = None,
    autoplay: bool | None = None,
    hint: str | None = None,
) -> discord.Embed:
    """Embed panel pemutar utama (progress bar + seluruh status dalam satu pesan)."""
    current = track if track is not None else getattr(player, "current", None)
    if current is None:
        return discord.Embed(
            title="⏹️ Tidak ada lagu yang diputar",
            description="Tambahkan lagu dengan `/musik putar query:judul lagu`.",
            color=discord.Color.dark_gray(),
        )

    paused = bool(getattr(player, "paused", False))
    is_stream = bool(getattr(current, "is_stream", False))
    position = max(0, _to_int(getattr(player, "position", 0)))
    length = max(0, _to_int(getattr(current, "length", 0)))
    queue_list = list(getattr(player, "queue", []) or [])
    queue_total = sum(_to_int(getattr(t, "length", 0)) for t in queue_list)
    preset = filter_name if filter_name in FILTER_PRESETS else "off"
    autoplay_on = bool(autoplay)

    if is_stream:
        progress_line = f"{BAR_KNOB}{BAR_FILLED * 13}\n`🔴 LIVE`"
    else:
        progress_line = (
            f"{build_progress_bar(position, length)}\n"
            f"`{format_duration(position)} / {format_duration(length)}`"
        )

    embed = discord.Embed(
        title=("⏸️ **Dijeda** — " if paused else "🎶 **Now Playing** — ") + track_title(current, 80),
        description=progress_line,
        color=discord.Color.dark_purple() if not paused else discord.Color.orange(),
        url=track_url(current),
    )
    author = str(getattr(current, "author", "") or "")
    if author:
        embed.add_field(name="🎤 Artis", value=author[:100], inline=True)
    embed.add_field(
        name="🎧 Diminta",
        value=str(track_requester_name(current))[:80],
        inline=True,
    )
    embed.add_field(
        name="📜 Antrean",
        value=f"`{len(queue_list)}` lagu • `{format_duration(queue_total)}`",
        inline=True,
    )
    embed.add_field(name="🔊 Volume", value=f"`{_to_int(getattr(player, 'volume', 0))}%`", inline=True)
    embed.add_field(
        name="🔁 Mode",
        value=loop_label_from_mode(getattr(getattr(player, "queue", None), "mode", None)),
        inline=True,
    )
    embed.add_field(name="🎛️ Filter", value=FILTER_PRESETS.get(preset, FILTER_PRESETS["off"]), inline=True)
    embed.add_field(name="♾️ Autoplay", value=autoplay_label(autoplay_on), inline=True)
    embed.add_field(name="📡 Sumber", value=source_label(current), inline=True)

    artwork = str(getattr(current, "artwork", "") or "")
    if artwork.startswith("http"):
        embed.set_thumbnail(url=artwork)
    embed.set_footer(text=(hint or "Panel pemutar • tombol di bawah untuk kontrol cepat")[:2048])
    return embed


def _panel_view():
    """Lazy import agar `music.py` tetap bisa diimpor lebih dulu daripada `views.py`."""
    try:
        from views import MusicPlayerView

        return MusicPlayerView()
    except Exception:  # pragma: no cover - saat unit test tanpa views
        return None


def _refresh_interval(guild_id: int) -> int:
    """Interval refresh panel musik milik server (fallback 10 detik bila tema gagal dibaca)."""
    try:
        from ui_theme import refresh_interval

        return max(5, int(refresh_interval(guild_id)))
    except Exception:  # pragma: no cover - tema belum siap
        return 10


def _v2_panel(player, guild_id: int, *, filter_name: str | None = "off", autoplay: bool | None = False):
    """Panel pemutar versi kartu (Components V2); `None` bila tidak tersedia."""
    try:
        from views import build_music_panel_view

        return build_music_panel_view(
            player,
            guild_id=guild_id,
            filter_name=filter_name,
            autoplay=autoplay,
        )
    except Exception:  # pragma: no cover - views belum siap
        return None


async def send_or_update_panel(
    bot: discord.Client,
    guild_id: int,
    *,
    channel=None,
    force_new: bool = False,
    view=None,
):
    """Mengirim panel pemutar baru atau **mengedit** panel lama (satu pesan per server)."""
    get_guild = getattr(bot, "get_guild", None)
    guild = get_guild(guild_id) if callable(get_guild) else None
    player = get_player(guild)
    if player is None or getattr(player, "channel", None) is None:
        await close_panel(bot, guild_id)
        return None

    settings = get_music_settings(guild_id)
    filter_name = settings.get("filter", "off")
    autoplay = bool(settings.get("autoplay", False))
    embed = build_player_embed(player, filter_name=filter_name, autoplay=autoplay)

    panel_view = view if view is not None else _panel_view()
    use_v2 = False
    if panel_view is None or type(panel_view).__name__ == "MusicPlayerView":
        v2_view = _v2_panel(player, guild_id, filter_name=filter_name, autoplay=autoplay)
        if v2_view is not None:
            panel_view = v2_view
            use_v2 = True
    panel = music_panels.get(guild_id)

    # Mode tampilan berubah (mis. setelah pembaruan versi) → panel lama diganti baru
    if panel and bool(panel.get("v2")) != use_v2:
        await close_panel(bot, guild_id)
        panel = None

    if panel and not force_new:
        get_channel = getattr(bot, "get_channel", None)
        target = get_channel(panel.get("channel_id")) if callable(get_channel) else None
        if target is not None:
            try:
                message = target.get_partial_message(int(panel["message_id"]))
                if use_v2:
                    await message.edit(view=panel_view)
                else:
                    await message.edit(embed=embed, view=panel_view)
                panel["updated_at"] = time.time()
                return message
            except discord.NotFound:
                music_panels.pop(guild_id, None)
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.debug("Gagal memperbarui panel musik: %s", sanitize_error_message(exc))
                return None

    get_channel = getattr(bot, "get_channel", None)
    target = channel
    if target is None and callable(get_channel):
        if panel:
            target = get_channel(int(panel.get("channel_id") or 0))
        if target is None:
            target = get_channel(announce_channels.get(guild_id, 0))
    if target is None:
        return None

    message = None
    if use_v2:
        try:
            message = await target.send(view=panel_view)
        except (discord.Forbidden, discord.HTTPException, TypeError, ValueError) as exc:
            logger.info(
                "Panel musik V2 ditolak (%s) — memakai embed klasik.",
                sanitize_error_message(exc),
            )
            use_v2 = False
            panel_view = _panel_view()
    if message is None:
        try:
            message = await target.send(embed=embed, view=panel_view)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.info("Gagal mengirim panel musik: %s", sanitize_error_message(exc))
            return None

    music_panels[guild_id] = {
        "channel_id": int(getattr(target, "id", 0)),
        "message_id": int(message.id),
        "updated_at": time.time(),
        "v2": use_v2,
    }
    remember_announce_channel(guild_id, getattr(target, "id", 0))
    return message


async def close_panel(bot: discord.Client, guild_id: int, *, delete: bool = True) -> bool:
    """Menutup panel pemutar (hapus pesan bila memungkinkan)."""
    panel = music_panels.pop(guild_id, None)
    if not panel:
        return False
    if not delete:
        return True
    get_channel = getattr(bot, "get_channel", None)
    channel = get_channel(int(panel.get("channel_id") or 0)) if callable(get_channel) else None
    if channel is None:
        return False
    try:
        await channel.get_partial_message(int(panel["message_id"])).delete()
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False


async def run_music_panel_check(bot: discord.Client) -> int:
    """Loop latar belakang: memperbarui progress bar panel pemutar tiap beberapa detik."""
    updated = 0
    for guild_id in list(music_panels.keys()):
        get_guild = getattr(bot, "get_guild", None)
        guild = get_guild(guild_id) if callable(get_guild) else None
        player = get_player(guild)
        if player is None or getattr(player, "channel", None) is None:
            await close_panel(bot, guild_id)
            continue
        if not get_music_settings(guild_id).get("announce", True):
            continue
        # Interval refresh diatur Admin lewat `/tampilan atur` (default 10 detik)
        panel_meta = music_panels.get(guild_id) or {}
        interval = _refresh_interval(guild_id)
        if time.time() - float(panel_meta.get("updated_at") or 0) < interval:
            continue
        if await send_or_update_panel(bot, guild_id):
            updated += 1
    return updated


# ==============================================================================
# ANTREAN BERPAGINASI (ala Rythm)
# ==============================================================================
QUEUE_PAGE_SIZE = 10


def build_queue_page_embed(
    tracks: list,
    *,
    page: int = 0,
    page_size: int = QUEUE_PAGE_SIZE,
    total_length: int = 0,
    now_playing=None,
) -> tuple[discord.Embed, int, int]:
    """Embed antrean berhalaman. Mengembalikan `(embed, halaman_aktif, total_halaman)`."""
    size = max(1, int(page_size))
    total_pages = max(1, (len(tracks) + size - 1) // size)
    current_page = max(0, min(total_pages - 1, int(page)))

    embed = discord.Embed(
        title="📜 Antrean Musik",
        color=discord.Color.blurple(),
        description=f"**{len(tracks)}** lagu • total `{format_duration(total_length)}`",
    )

    if not tracks:
        embed.description = "Antrean masih kosong. Tambahkan dengan `/musik putar`."
        return embed, 0, 1

    start = current_page * size
    lines = []
    for offset, track in enumerate(tracks[start : start + size], start=start + 1):
        length = "LIVE" if getattr(track, "is_stream", False) else format_duration(getattr(track, "length", 0))
        lines.append(
            f"`{offset}.` [{track_title(track, 55)}]({track_url(track) or 'https://discord.com'}) — `{length}`"
        )
    embed.add_field(
        name=f"Berikutnya (halaman {current_page + 1}/{total_pages})",
        value="\n".join(lines)[:1024],
        inline=False,
    )
    if now_playing is not None:
        embed.add_field(
            name="🎶 Sedang Diputar",
            value=f"[{track_title(now_playing, 60)}]({track_url(now_playing) or 'https://discord.com'})",
            inline=False,
        )
    embed.set_footer(text=f"Halaman {current_page + 1} dari {total_pages} • gunakan tombol ◀ ▶ untuk berpindah")
    return embed, current_page, total_pages


async def skip_previous(player) -> bool:
    """Memutar lagu sebelumnya dari riwayat antrean."""
    history = getattr(getattr(player, "queue", None), "history", None)
    if not history:
        return False
    try:
        previous = history[-1]
    except (IndexError, KeyError):
        return False
    if previous is None:
        return False
    try:
        if hasattr(history, "delete"):
            history.delete(-1)       # wavelink.Queue
        else:
            history.pop(-1)          # list biasa (unit test)
    except Exception as exc:  # pragma: no cover - history kosong
        logger.debug("Efek samping opsional gagal: %s", exc)
    await player.play(previous, add_history=False)
    return True


def set_autoplay(player, enabled: bool) -> bool:
    """Menyalakan/mematikan autoplay rekomendasi lagu (fitur asli Lavalink)."""
    if not WAVELINK_AVAILABLE or player is None:
        return False
    try:
        player.autoplay = wavelink.AutoPlayMode.enabled if enabled else wavelink.AutoPlayMode.disabled
        return True
    except Exception as exc:  # pragma: no cover - node lama
        logger.info("Gagal mengubah autoplay: %s", sanitize_error_message(exc))
        return False
