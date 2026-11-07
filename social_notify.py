"""Notifikasi sosial: YouTube, Twitch, TikTok/RSS — tanpa AI, tanpa biaya.

Filosofi biaya (Free Tier):
    - Pesan notifikasi memakai **template**, jadi **0 kuota Gemini**.
    - YouTube & feed RSS memakai **RSS publik** → tidak butuh API key sama sekali.
    - Twitch memakai Helix API dengan **Client Credentials** dari aplikasi gratis
      (dev.twitch.tv). Bila kredensial belum diisi, fitur Twitch otomatis dilewati
      tanpa error — fitur lain tetap jalan.
    - TikTok **tidak punya API gratis resmi** untuk feed, jadi dipakai jalur RSS
      (mis. instance RSSHub). Ini didokumentasikan terbuka, bukan dijanjikan manis.

Aturan anti-spam:
    - Saat langganan pertama kali dibuat, item yang sudah ada **ditandai sudah dilihat**
      dan **tidak** dikirim, supaya tidak membanjiri channel dengan video lama.
    - Twitch hanya dikirim saat status berubah offline → live (bukan tiap polling).
    - Maksimal `MAX_SEEN` id disimpan per langganan agar file JSON tetap kecil.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from xml.etree import ElementTree

import aiohttp
import discord

import ui_theme
from config import (
    DATA_DIR,
    SOCIAL_FILE,
    SOCIAL_CHECK_SEC,
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
)

logger = logging.getLogger("gemini_bot.social_notify")

PLATFORMS: dict[str, dict] = {
    "youtube": {
        "label": "YouTube (unggahan video)",
        "emoji": "🎬",
        "hint": "ID channel `UC...`, link channel, atau @handle",
        "template": "🎬 **{source}** baru saja mengunggah video baru!\n**{title}**\n{url}",
    },
    "twitch": {
        "label": "Twitch (mulai live)",
        "emoji": "🟣",
        "hint": "nama login Twitch, mis. `ninja`",
        "template": "🟣 **{source}** sedang LIVE! 🔴\n**{title}** — main *{game}*\n{url}",
    },
    "tiktok": {
        "label": "TikTok / feed RSS",
        "emoji": "🎵",
        "hint": "URL feed RSS (RSSHub) — TikTok tidak menyediakan API gratis resmi",
        "template": "🎵 **{source}** mengunggah video baru!\n**{title}**\n{url}",
    },
    "reddit": {
        "label": "Reddit (postingan baru subreddit)",
        "emoji": "👽",
        "hint": "nama subreddit (mis. `indonesia`, `r/indonesia`) atau link subreddit",
        "template": "👽 **{source}** — postingan baru di Reddit!\n**{title}**\n{url}",
    },
    "rss": {
        "label": "RSS / Atom (situs apa pun)",
        "emoji": "📰",
        "hint": "URL feed RSS/Atom (mis. `https://blog.contoh.com/feed.xml`)",
        "template": "📰 **{source}** — artikel baru!\n**{title}**\n{url}",
    },
}

MAX_SEEN = 25
MAX_SUBS_PER_GUILD = 12
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_HELIX_STREAMS = "https://api.twitch.tv/helix/streams"
YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
REDDIT_FEED_URL = "https://www.reddit.com/r/{sub}/new/.rss"
SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_+]{2,32}$")

# guild_id -> {"subs": [ ... ]}
social_guilds: dict[int, dict] = {}

# Pembatas frekuensi per platform (detik). Polling watcher bisa lebih cepat;
# fungsi cek hanya benar-benar memanggil jaringan bila jeda ini terlewati.
PLATFORM_INTERVAL: dict[str, int] = {
    "youtube": max(300, SOCIAL_CHECK_SEC),
    "twitch": 120,
    "tiktok": max(600, SOCIAL_CHECK_SEC),
    "reddit": max(600, SOCIAL_CHECK_SEC),
    "rss": max(600, SOCIAL_CHECK_SEC),
}
_last_checked: dict[tuple[int, str], float] = {}

_twitch_token: dict[str, float | str] = {"token": "", "expires_at": 0.0}


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def _new_sub_id(platform: str, target: str) -> str:
    digest = hashlib.sha1(f"{platform}:{target.lower()}".encode("utf-8")).hexdigest()
    return digest[:8]


def get_subscriptions(guild_id: int) -> list[dict]:
    """Daftar langganan notifikasi milik satu server."""
    return list((social_guilds.get(int(guild_id)) or {}).get("subs") or [])


def find_subscription(guild_id: int, sub_id: str) -> dict | None:
    sub_id = str(sub_id or "").strip().lower()
    for sub in get_subscriptions(guild_id):
        if sub.get("id") == sub_id:
            return sub
    return None


def normalize_subreddit(value: str) -> str:
    """`r/indonesia`, `indonesia`, atau link Reddit → nama subreddit (tanpa `r/`)."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "reddit.com" in text.lower():
        found = re.search(r"reddit\.com/r/([A-Za-z0-9_+]{2,32})", text, re.I)
        text = found.group(1) if found else ""
    text = text.lstrip("/")
    if text.lower().startswith("r/"):
        text = text[2:]
    text = text.strip("/")
    return text if SUBREDDIT_RE.match(text) else ""


def feed_url(platform: str, target: str) -> str:
    """URL feed yang benar-benar diambil untuk satu langganan."""
    if platform == "reddit":
        return REDDIT_FEED_URL.format(sub=normalize_subreddit(target))
    return str(target or "").strip()


def add_subscription(
    guild_id: int,
    platform: str,
    target: str,
    channel_id: int,
    *,
    role_id: int | None = None,
    template: str | None = None,
) -> dict:
    """Menambah langganan notifikasi. Melempar `ValueError` untuk input tidak valid."""
    key = str(platform or "").strip().lower()
    if key not in PLATFORMS:
        raise ValueError("Platform tidak dikenal. Pilih YouTube, Twitch, atau TikTok/RSS.")

    cleaned = str(target or "").strip()
    if not cleaned:
        raise ValueError("Nama akun / URL feed tidak boleh kosong.")
    if key == "twitch":
        cleaned = normalize_twitch_login(cleaned)
        if not cleaned:
            raise ValueError("Login Twitch tidak valid (huruf, angka, dan garis bawah).")
    if key == "reddit":
        cleaned = normalize_subreddit(cleaned)
        if not cleaned:
            raise ValueError("Nama subreddit tidak valid (huruf, angka, `_`, maks 32 huruf).")
    if key == "tiktok" and not cleaned.lower().startswith(("http://", "https://")):
        raise ValueError(
            "Untuk TikTok/RSS, tempelkan **URL feed** (mis. dari RSSHub). "
            "TikTok tidak menyediakan API feed gratis resmi."
        )
    if key == "rss" and not cleaned.lower().startswith(("http://", "https://")):
        raise ValueError("Untuk RSS/Atom, tempelkan **URL feed** lengkap (diawali `http`).")

    subs = social_guilds.setdefault(int(guild_id), {"subs": []})["subs"]
    if len(subs) >= MAX_SUBS_PER_GUILD:
        raise ValueError(f"Batas {MAX_SUBS_PER_GUILD} langganan per server sudah tercapai.")

    sub_id = _new_sub_id(key, cleaned)
    existing = find_subscription(guild_id, sub_id)
    if existing is not None:
        existing["channel_id"] = int(channel_id)
        existing["role_id"] = int(role_id) if role_id else None
        if template is not None:
            existing["template"] = _clean_template(template)
        return existing

    sub = {
        "id": sub_id,
        "platform": key,
        "target": cleaned,
        "channel_id": int(channel_id),
        "role_id": int(role_id) if role_id else None,
        "template": _clean_template(template) if template else "",
        "seen": [],
        "seeded": False,          # True setelah polling pertama (agar tidak spam video lama)
        "live": False,            # khusus Twitch: status live terakhir
        "created_at": time.time(),
    }
    subs.append(sub)
    return sub


def remove_subscription(guild_id: int, sub_id: str) -> bool:
    subs = (social_guilds.get(int(guild_id)) or {}).get("subs") or []
    sub = find_subscription(guild_id, sub_id)
    if sub is None:
        return False
    subs.remove(sub)
    if not subs:
        social_guilds.pop(int(guild_id), None)
    return True


def _clean_template(template: str) -> str:
    cleaned = str(template or "").strip()
    if cleaned == "-":
        return ""
    return cleaned[:400]


def cleanup_social_runtime(limit: int = 500) -> int:
    """Memangkas cache pembatas frekuensi agar RAM tidak menumpuk."""
    removed = 0
    if len(_last_checked) > limit:
        for key in list(_last_checked)[: len(_last_checked) - limit]:
            _last_checked.pop(key, None)
            removed += 1
    return removed


def twitch_configured() -> bool:
    return bool(TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET)


def load_social_from_disk() -> int:
    """Memuat langganan notifikasi dari data/social.json."""
    if not SOCIAL_FILE.exists():
        return 0
    try:
        raw = json.loads(SOCIAL_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", SOCIAL_FILE, exc)
        return 0

    loaded = 0
    for gid_str, gdata in (raw.get("guilds") or {}).items():
        try:
            subs = []
            for item in gdata.get("subs") or []:
                platform = str(item.get("platform") or "").lower()
                if platform not in PLATFORMS or not item.get("target"):
                    continue
                subs.append(
                    {
                        "id": str(item.get("id") or _new_sub_id(platform, item["target"])),
                        "platform": platform,
                        "target": str(item["target"])[:300],
                        "channel_id": int(item["channel_id"]),
                        "role_id": int(item["role_id"]) if item.get("role_id") else None,
                        "template": str(item.get("template") or "")[:400],
                        "seen": [str(x) for x in (item.get("seen") or [])][-MAX_SEEN:],
                        "seeded": bool(item.get("seeded", True)),
                        "live": bool(item.get("live", False)),
                        "created_at": float(item.get("created_at") or time.time()),
                    }
                )
            if subs:
                social_guilds[int(gid_str)] = {"subs": subs}
                loaded += 1
        except (KeyError, TypeError, ValueError):
            continue
    return loaded


async def save_social_to_disk() -> None:
    """Menyimpan langganan notifikasi secara atomik (aman saat restart Wispbyte)."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "guilds": {
                str(gid): {"subs": data.get("subs") or []} for gid, data in social_guilds.items()
            }
        }
        tmp = SOCIAL_FILE.with_suffix(".json.tmp")
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        await asyncio.to_thread(tmp.write_text, text, "utf-8")
        await asyncio.to_thread(SOCIAL_FILE.parent.mkdir, parents=True, exist_ok=True)
        import os

        await asyncio.to_thread(os.replace, tmp, SOCIAL_FILE)
    except Exception:
        logger.exception("Gagal menyimpan social.json")


# ==============================================================================
# PARSER (MURNI — mudah diuji tanpa jaringan)
# ==============================================================================
def normalize_twitch_login(value: str) -> str:
    """Mengubah URL/nama Twitch menjadi login bersih."""
    text = str(value or "").strip()
    text = re.sub(r"^https?://(www\.)?twitch\.tv/", "", text, flags=re.IGNORECASE)
    text = text.split("?")[0].strip("/")
    if "/" in text:
        text = text.split("/")[0]
    login = re.sub(r"[^A-Za-z0-9_]", "", text).lower()
    return login[:25]


def parse_atom_entries(xml_bytes: bytes) -> list[dict]:
    """Membaca feed YouTube (Atom) → daftar video terbaru."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    channel_title = ""
    node = root.find("atom:title", ns)
    if node is not None and node.text:
        channel_title = node.text.strip()

    entries: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        vid = entry.findtext("yt:videoId", default="", namespaces=ns)
        title = entry.findtext("atom:title", default="", namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)
        if not vid:
            continue
        entries.append(
            {
                "id": vid.strip(),
                "title": (title or "").strip() or "Video baru",
                "url": f"https://www.youtube.com/watch?v={vid.strip()}",
                "published": published.strip(),
                "source": channel_title,
                "thumbnail": f"https://i.ytimg.com/vi/{vid.strip()}/hqdefault.jpg",
            }
        )
    return entries


def parse_rss_items(xml_bytes: bytes) -> list[dict]:
    """Membaca feed RSS 2.0 umum (dipakai untuk TikTok/RSSHub)."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    channel = root.find("channel")
    source = (channel.findtext("title") if channel is not None else "") or ""
    items: list[dict] = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip() or "Postingan baru"
        guid = (item.findtext("guid") or link or title).strip()
        if not guid:
            continue
        items.append(
            {
                "id": hashlib.sha1(guid.encode("utf-8")).hexdigest()[:16],
                "title": title,
                "url": link,
                "published": (item.findtext("pubDate") or "").strip(),
                "source": source.strip(),
                "thumbnail": "",
            }
        )
    return items


def parse_reddit_feed(xml_bytes: bytes) -> list[dict]:
    """Membaca feed `.rss` Reddit (format Atom) → postingan terbaru.

    Reddit memakai Atom, bukan RSS 2.0, jadi `parse_rss_items` tidak cukup.
    """
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    source = ""
    node = root.find("atom:title", ns)
    if node is not None and node.text:
        source = node.text.strip()

    items: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        link_node = entry.find("atom:link", ns)
        link = (link_node.get("href") if link_node is not None else "") or ""
        entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        published = (
            entry.findtext("atom:updated", default="", namespaces=ns)
            or entry.findtext("atom:published", default="", namespaces=ns)
            or ""
        ).strip()
        if not (entry_id or link):
            continue
        items.append(
            {
                "id": hashlib.sha1((entry_id or link).encode("utf-8")).hexdigest()[:16],
                "title": title or "Postingan baru",
                "url": link,
                "published": published,
                "source": source,
                "thumbnail": "",
            }
        )
    return items


def parse_twitch_streams(payload: dict) -> list[dict]:
    """Membaca respons Helix `/streams` → daftar stream yang sedang live."""
    streams: list[dict] = []
    for item in (payload or {}).get("data") or []:
        login = str(item.get("user_login") or "").lower()
        if not login:
            continue
        streams.append(
            {
                "id": str(item.get("id") or f"{login}-{item.get('started_at', '')}"),
                "login": login,
                "title": str(item.get("title") or "Live sekarang"),
                "game": str(item.get("game_name") or "—"),
                "url": f"https://twitch.tv/{login}",
                "source": str(item.get("user_name") or login),
                "thumbnail": str(item.get("thumbnail_url") or "").replace("{width}", "640").replace(
                    "{height}", "360"
                ),
                "started_at": str(item.get("started_at") or ""),
            }
        )
    return streams


def resolve_youtube_channel_id(target: str) -> str | None:
    """Mengambil ID channel dari input pengguna bila bentuknya sudah jelas."""
    text = str(target or "").strip()
    direct = re.search(r"(UC[A-Za-z0-9_-]{22})", text)
    if direct:
        return direct.group(1)
    return None


YT_HANDLE_PATTERN = re.compile(r'"channelId":"(UC[A-Za-z0-9_-]{22})"')
YT_CANONICAL_PATTERN = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"')


def extract_youtube_channel_id(html: str) -> str | None:
    """Mengekstrak `UC...` dari halaman channel YouTube (handle / custom URL)."""
    text = str(html or "")
    for pattern in (YT_CANONICAL_PATTERN, YT_HANDLE_PATTERN):
        found = pattern.search(text)
        if found:
            return found.group(1)
    return None


# ==============================================================================
# JARINGAN
# ==============================================================================
async def fetch_text(session: aiohttp.ClientSession, url: str, *, headers: dict | None = None) -> bytes | None:
    """GET sederhana dengan batas waktu & tanpa melempar error ke pemanggil."""
    try:
        async with session.get(url, headers=headers or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                logger.info("HTTP %s untuk %s", resp.status, url)
                return None
            return await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.info("Gagal mengambil %s: %s", url, exc)
        return None


async def resolve_channel_id_remote(session: aiohttp.ClientSession, target: str) -> str | None:
    """Resolve @handle / URL channel YouTube menjadi `UC...` (butuh jaringan)."""
    direct = resolve_youtube_channel_id(target)
    if direct:
        return direct

    text = str(target or "").strip()
    if not text:
        return None
    if text.startswith("@"):
        url = f"https://www.youtube.com/{text}"
    elif text.lower().startswith(("http://", "https://")):
        url = text
    elif re.fullmatch(r"[A-Za-z0-9_.-]{3,60}", text):
        url = f"https://www.youtube.com/@{text}"
    else:
        return None

    body = await fetch_text(session, url, headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"})
    if not body:
        return None
    return extract_youtube_channel_id(body.decode("utf-8", errors="ignore"))


async def _twitch_app_token(session: aiohttp.ClientSession) -> str:
    """Token aplikasi Twitch (Client Credentials) — di-cache sampai kedaluwarsa."""
    now = time.time()
    cached = str(_twitch_token.get("token") or "")
    if cached and float(_twitch_token.get("expires_at") or 0) > now + 60:
        return cached
    if not twitch_configured():
        return ""

    try:
        async with session.post(
            TWITCH_TOKEN_URL,
            params={
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                logger.warning("Twitch token ditolak (HTTP %s) — periksa TWITCH_CLIENT_ID/SECRET.", resp.status)
                return ""
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.info("Gagal meminta token Twitch: %s", exc)
        return ""

    token = str(data.get("access_token") or "")
    _twitch_token["token"] = token
    _twitch_token["expires_at"] = now + float(data.get("expires_in") or 3600)
    return token


async def fetch_twitch_live(session: aiohttp.ClientSession, logins: list[str]) -> dict[str, dict]:
    """Mengembalikan `{login: stream}` untuk channel yang sedang live."""
    token = await _twitch_app_token(session)
    if not token or not logins:
        return {}

    params = [("user_login", login) for login in logins[:20]]
    try:
        async with session.get(
            TWITCH_HELIX_STREAMS,
            params=params,
            headers={"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                logger.info("Helix streams membalas HTTP %s", resp.status)
                return {}
            payload = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.info("Gagal mengambil status Twitch: %s", exc)
        return {}

    return {stream["login"]: stream for stream in parse_twitch_streams(payload)}


async def fetch_feed_items(session: aiohttp.ClientSession, sub: dict) -> list[dict]:
    """Mengambil item terbaru untuk satu langganan (YouTube/RSS)."""
    platform = sub.get("platform")
    if platform == "youtube":
        channel_id = sub.get("channel_id_resolved") or resolve_youtube_channel_id(sub.get("target", ""))
        if not channel_id:
            channel_id = await resolve_channel_id_remote(session, sub.get("target", ""))
            if channel_id:
                sub["channel_id_resolved"] = channel_id
        if not channel_id:
            return []
        body = await fetch_text(
            session,
            YOUTUBE_FEED_URL.format(cid=channel_id),
            headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"},
        )
        return parse_atom_entries(body) if body else []

    if platform == "reddit":
        body = await fetch_text(
            session,
            feed_url("reddit", str(sub.get("target") or "")),
            headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"},
        )
        if not body:
            return []
        return parse_reddit_feed(body) or parse_rss_items(body)

    body = await fetch_text(
        session,
        feed_url(str(platform or ""), str(sub.get("target") or "")),
        headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"},
    )
    return parse_rss_items(body) if body else []


# ==============================================================================
# PENGIRIMAN PESAN
# ==============================================================================
def build_notification_text(sub: dict, item: dict) -> str:
    """Menyusun teks notifikasi dari template (0 kuota AI)."""
    platform = sub.get("platform", "youtube")
    default = PLATFORMS.get(platform, {}).get("template", "{source}: {title} {url}")
    template = str(sub.get("template") or "").strip() or default
    source = str(item.get("source") or sub.get("target") or "").strip()
    text = (
        template.replace("{source}", source or "Channel")
        .replace("{channel}", source or "Channel")
        .replace("{title}", str(item.get("title") or "")[:300])
        .replace("{url}", str(item.get("url") or ""))
        .replace("{game}", str(item.get("game") or "—"))
    )
    return text[:1900]


async def _send_notification(bot, sub: dict, guild, item: dict) -> bool:
    channel = guild.get_channel(int(sub["channel_id"]))
    if channel is None or not hasattr(channel, "send"):
        logger.info("Channel notifikasi %s tidak ditemukan.", sub.get("channel_id"))
        return False

    text = build_notification_text(sub, item)
    if sub.get("role_id"):
        try:
            role = guild.get_role(int(sub["role_id"]))
        except (TypeError, ValueError):
            role = None
        if role is not None and not role.is_default():
            text = f"{role.mention} {text}"

    embed = discord.Embed(
        title=item.get("title", "")[:250] or "Update baru",
        url=str(item.get("url") or "") or None,
        description=text,
        color=ui_theme.accent_color(guild.id),
        timestamp=discord.utils.utcnow(),
    )
    if item.get("thumbnail"):
        embed.set_image(url=item["thumbnail"])
    ui_theme.apply_embed_theme(embed, guild.id, footer=f"{PLATFORMS.get(sub['platform'], {}).get('label', 'Notifikasi')}")

    try:
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal mengirim notifikasi sosial ke %s: %s", getattr(channel, "id", "?"), exc)
        return False


def _remember(sub: dict, item_id: str) -> None:
    seen = sub.setdefault("seen", [])
    if item_id in seen:
        return
    seen.append(item_id)
    del seen[:-MAX_SEEN]


# ==============================================================================
# PEMERIKSAAN RUTIN
# ==============================================================================
async def check_subscription(bot, guild, sub: dict, session: aiohttp.ClientSession, *, force: bool = False) -> int:
    """Memeriksa satu langganan & mengirim notifikasi item baru. `force` untuk `/sosial tes`."""
    platform = sub.get("platform")
    sent = 0
    seen = set(sub.get("seen") or [])

    if platform == "twitch":
        if not twitch_configured():
            return 0
        live = await fetch_twitch_live(session, [sub.get("target", "")])
        stream = live.get(str(sub.get("target") or "").lower())
        if stream is None:
            sub["live"] = False
            return 0
        if force or not sub.get("live"):
            sub["live"] = True
            sent = 1 if await _send_notification(bot, sub, guild, stream) else 0
        return sent

    items = await fetch_feed_items(session, sub)
    if not items:
        return 0

    if force:
        target = items[0]
        if await _send_notification(bot, sub, guild, target):
            _remember(sub, target["id"])
            sent = 1
        sub["seeded"] = True
        return sent

    if not sub.get("seeded"):
        # Polling pertama: tandai semua item lama sebagai "sudah dilihat" (anti-banjir).
        for item in items:
            _remember(sub, item["id"])
        sub["seeded"] = True
        return 0

    for item in reversed(items):          # kronologis: yang paling lama didahulukan
        if item["id"] in seen:
            continue
        if await _send_notification(bot, sub, guild, item):
            sent += 1
        _remember(sub, item["id"])
    return sent


async def diagnose(session: aiohttp.ClientSession | None = None) -> dict:
    """Pemeriksaan kesiapan: kredensial Twitch, token, & jumlah langganan per platform."""
    counts: dict[str, int] = {key: 0 for key in PLATFORMS}
    for data in social_guilds.values():
        for sub in data.get("subs") or []:
            platform = str(sub.get("platform") or "")
            if platform in counts:
                counts[platform] += 1

    result = {
        "twitch_configured": twitch_configured(),
        "twitch_token_ok": False,
        "twitch_error": "",
        "counts": counts,
        "total": sum(counts.values()),
    }
    if not twitch_configured():
        if counts.get("twitch"):
            result["twitch_error"] = (
                "Langganan Twitch ada, tetapi `TWITCH_CLIENT_ID`/`TWITCH_CLIENT_SECRET` belum diisi."
            )
        else:
            result["twitch_error"] = "Belum diisi (opsional selama tidak memakai Twitch)."
        return result

    own = session is None
    http = session or aiohttp.ClientSession()
    try:
        token = await _twitch_app_token(http)
        result["twitch_token_ok"] = bool(token)
        if not token:
            result["twitch_error"] = "Kredensial terisi tetapi token ditolak — periksa ulang Client ID/Secret."
    finally:
        if own:
            await http.close()
    return result


async def run_social_check(bot, http_session: aiohttp.ClientSession | None = None) -> int:
    """Loop latar belakang: memeriksa seluruh langganan dengan pembatas frekuensi."""
    if not social_guilds:
        return 0

    own_session = http_session is None
    session = http_session or aiohttp.ClientSession()
    now = time.time()
    sent = 0
    try:
        for gid, data in list(social_guilds.items()):
            guild = bot.get_guild(gid)
            if guild is None:
                continue
            for sub in list(data.get("subs") or []):
                platform = str(sub.get("platform") or "youtube")
                key = (gid, sub.get("id", ""))
                interval = PLATFORM_INTERVAL.get(platform, SOCIAL_CHECK_SEC)
                if now - float(_last_checked.get(key, 0.0)) < interval:
                    continue
                _last_checked[key] = now
                try:
                    sent += await check_subscription(bot, guild, sub, session)
                except Exception as exc:  # pragma: no cover - jaring aman
                    logger.warning("Notifikasi %s %s gagal: %s", platform, sub.get("target"), exc)
        if sent:
            await save_social_to_disk()
    finally:
        if own_session:
            await session.close()
    return sent


def summarize_subscription(sub: dict) -> str:
    """Satu baris ringkasan untuk `/sosial daftar`."""
    meta = PLATFORMS.get(sub.get("platform"), {})
    role = f" • ping <@&{sub['role_id']}>" if sub.get("role_id") else ""
    return (
        f"{meta.get('emoji', '•')} `{sub.get('id')}` **{sub.get('target')}** "
        f"→ <#{sub.get('channel_id')}>{role}"
    )


def relative_time(ts: float) -> str:
    """Waktu relatif singkat untuk status langganan."""
    try:
        delta = max(0, int(time.time() - float(ts)))
    except (TypeError, ValueError):
        return "-"
    if delta < 60:
        return f"{delta} detik lalu"
    if delta < 3600:
        return f"{delta // 60} menit lalu"
    if delta < 86400:
        return f"{delta // 3600} jam lalu"
    return f"{delta // 86400} hari lalu"


def iso_to_readable(value: str) -> str:
    """Mengubah timestamp ISO feed menjadi teks ringkas (WIB-agnostik)."""
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return text[:32]
    return parsed.strftime("%d %b %Y %H:%M UTC")
