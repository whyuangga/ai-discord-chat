"""Kotak saran (`/saran`) — usulan member + voting tombol, tanpa AI/kuota.

Data di `data/suggestions.json`:
    guilds: {guild_id: {"channel_id": int|None}}
    items:  {guild_id: [ {id, author_id, text, message_id, status, up: [ids], down: [ids], ...} ]}

Aturan:
    - Satu member = satu suara (bisa berganti antara 👍 / 👎).
    - Maksimal 20 saran tersimpan per server; yang terbaru dipertahankan.
    - Status: `baru` → `diterima` / `ditolak` / `dikerjakan` (diubah staff).
"""

import asyncio
import json
import logging
import time

import discord

import ui_theme
from config import DATA_DIR

logger = logging.getLogger("gemini_bot.suggestions")

SUGGESTIONS_FILE = DATA_DIR / "suggestions.json"
MAX_ITEMS_PER_GUILD = 20
MAX_TEXT = 900

STATUSES: dict[str, dict] = {
    "baru": {"label": "Baru", "emoji": "🆕", "color": 0x9B59B6},
    "dikerjakan": {"label": "Sedang Dikerjakan", "emoji": "🛠️", "color": 0xF1C40F},
    "diterima": {"label": "Diterima", "emoji": "✅", "color": 0x2ECC71},
    "ditolak": {"label": "Ditolak", "emoji": "❌", "color": 0xE74C3C},
}

suggestion_settings: dict[int, dict] = {}
suggestion_items: dict[int, list[dict]] = {}
_by_message: dict[int, tuple[int, int]] = {}   # message_id -> (guild_id, suggestion_id)
_disk_lock = asyncio.Lock()


# ==============================================================================
# PENGATURAN
# ==============================================================================
def get_channel(guild_id: int) -> int | None:
    channel = (suggestion_settings.get(int(guild_id)) or {}).get("channel_id")
    return int(channel) if channel else None


def set_channel(guild_id: int, channel_id: int | None) -> int | None:
    if channel_id is None:
        suggestion_settings.pop(int(guild_id), None)
        return None
    suggestion_settings[int(guild_id)] = {"channel_id": int(channel_id)}
    return int(channel_id)


# ==============================================================================
# SARAN
# ==============================================================================
def _next_id(guild_id: int) -> int:
    items = suggestion_items.get(int(guild_id)) or []
    return max((int(item.get("id", 0)) for item in items), default=0) + 1


def add_suggestion(guild_id: int, author_id: int, text: str) -> dict:
    """Menyimpan saran baru (belum punya message_id sampai pesannya terkirim)."""
    cleaned = str(text or "").strip()
    if not cleaned:
        raise ValueError("Isi saran tidak boleh kosong.")

    item = {
        "id": _next_id(guild_id),
        "author_id": int(author_id),
        "text": cleaned[:MAX_TEXT],
        "message_id": 0,
        "status": "baru",
        "up": [],
        "down": [],
        "created_at": time.time(),
    }
    items = suggestion_items.setdefault(int(guild_id), [])
    items.append(item)
    if len(items) > MAX_ITEMS_PER_GUILD:
        dropped = items.pop(0)
        _by_message.pop(int(dropped.get("message_id") or 0), None)
    return item


def get_suggestion(guild_id: int, suggestion_id: int) -> dict | None:
    for item in suggestion_items.get(int(guild_id)) or []:
        if int(item.get("id", 0)) == int(suggestion_id):
            return item
    return None


def get_by_message(message_id: int) -> dict | None:
    mapping = _by_message.get(int(message_id))
    if mapping is None:
        return None
    return get_suggestion(mapping[0], mapping[1])


def bind_message(guild_id: int, suggestion_id: int, message_id: int) -> None:
    """Mengaitkan saran dengan ID pesan Discord-nya (untuk tombol persisten)."""
    item = get_suggestion(guild_id, suggestion_id)
    if item is None:
        return
    item["message_id"] = int(message_id)
    _by_message[int(message_id)] = (int(guild_id), int(suggestion_id))


def vote(message_id: int, user_id: int, choice: str) -> tuple[str, dict | None]:
    """Memberi/mengganti suara. Status: ok | baru | berganti | duplikat | tidak_ada."""
    item = get_by_message(message_id)
    if item is None:
        return "tidak_ada", None

    choice = "up" if str(choice).startswith("up") else "down"
    other = "down" if choice == "up" else "up"
    user_id = int(user_id)

    if user_id in item.get(choice, []):
        return "duplikat", item

    swapped = user_id in item.get(other, [])
    if swapped:
        item[other].remove(user_id)
    item.setdefault(choice, []).append(user_id)
    return ("berganti" if swapped else "baru"), item


def set_status(guild_id: int, suggestion_id: int, status: str) -> dict | None:
    item = get_suggestion(guild_id, suggestion_id)
    key = str(status or "").strip().lower()
    if item is None or key not in STATUSES:
        return None
    item["status"] = key
    return item


def delete_suggestion(guild_id: int, suggestion_id: int) -> bool:
    items = suggestion_items.get(int(guild_id)) or []
    for index, item in enumerate(items):
        if int(item.get("id", 0)) == int(suggestion_id):
            _by_message.pop(int(item.get("message_id") or 0), None)
            del items[index]
            return True
    return False


def list_suggestions(guild_id: int, *, status: str | None = None, limit: int = 10) -> list[dict]:
    items = list(reversed(suggestion_items.get(int(guild_id)) or []))
    if status:
        items = [item for item in items if item.get("status") == status]
    return items[: max(1, limit)]


def score(item: dict) -> int:
    return len(item.get("up") or []) - len(item.get("down") or [])


# ==============================================================================
# TAMPILAN
# ==============================================================================
def _bar(up: int, down: int) -> str:
    total = up + down
    if total == 0:
        return "░░░░░░░░░░"
    filled = round(10 * up / total)
    return "█" * filled + "░" * (10 - filled)


def build_suggestion_embed(guild_id: int | None, item: dict) -> discord.Embed:
    """Embed saran: status, isi, penulis, dan hasil voting."""
    status = STATUSES.get(str(item.get("status") or "baru"), STATUSES["baru"])
    up = len(item.get("up") or [])
    down = len(item.get("down") or [])
    author = f"<@{item.get('author_id')}>" if item.get("author_id") else "Anonim"
    embed = discord.Embed(
        title=f"{status['emoji']} Saran #{item.get('id')} — {status['label']}",
        description=str(item.get("text") or "")[:MAX_TEXT],
        colour=discord.Colour(status["color"]),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="👍 Setuju", value=f"`{up}`", inline=True)
    embed.add_field(name="👎 Tidak setuju", value=f"`{down}`", inline=True)
    embed.add_field(name="Selisih", value=f"`{score(item):+d}`", inline=True)
    embed.add_field(name="Dukungan", value=f"`{_bar(up, down)}` {up}/{up + down}", inline=False)
    embed.add_field(name="Pengusul", value=author, inline=True)
    ui_theme.apply_embed_theme(embed, guild_id, footer="Klik tombol di bawah untuk memilih")
    return embed


def mention_author(item: dict) -> str:
    return f"<@{item.get('author_id')}>" if item.get("author_id") else "-"


# ==============================================================================
# PENYIMPANAN
# ==============================================================================
def load_suggestions_from_disk() -> tuple[int, int]:
    """Memuat pengaturan channel & daftar saran dari data/suggestions.json."""
    if not SUGGESTIONS_FILE.exists():
        return 0, 0
    try:
        raw = json.loads(SUGGESTIONS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", SUGGESTIONS_FILE, exc)
        return 0, 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            channel_id = int(data["channel_id"])
        except (KeyError, TypeError, ValueError):
            continue
        suggestion_settings[int(gid_str)] = {"channel_id": channel_id}

    total = 0
    for gid_str, items in (raw.get("items") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        cleaned: list[dict] = []
        for item in items[-MAX_ITEMS_PER_GUILD:]:
            try:
                record = {
                    "id": int(item["id"]),
                    "author_id": int(item.get("author_id") or 0),
                    "text": str(item.get("text") or "")[:MAX_TEXT],
                    "message_id": int(item.get("message_id") or 0),
                    "status": str(item.get("status") or "baru"),
                    "up": [int(x) for x in (item.get("up") or [])],
                    "down": [int(x) for x in (item.get("down") or [])],
                    "created_at": float(item.get("created_at") or time.time()),
                }
            except (KeyError, TypeError, ValueError):
                continue
            cleaned.append(record)
            if record["message_id"]:
                _by_message[record["message_id"]] = (gid, record["id"])
        if cleaned:
            suggestion_items[gid] = cleaned
            total += len(cleaned)
    return len(suggestion_items), total


async def save_suggestions_to_disk() -> None:
    """Menyimpan pengaturan & saran secara atomik."""
    async with _disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(gid): data for gid, data in suggestion_settings.items()},
                "items": {str(gid): items for gid, items in suggestion_items.items()},
            }
            tmp = SUGGESTIONS_FILE.with_suffix(".json.tmp")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp.write_text, text, "utf-8")
            import os

            await asyncio.to_thread(os.replace, tmp, SUGGESTIONS_FILE)
        except Exception as exc:
            logger.warning("Gagal menyimpan suggestions.json: %s", exc)


def cleanup_suggestions_runtime(limit: int = 300) -> int:
    """Memangkas cache pemetaan pesan agar RAM tetap kecil."""
    removed = 0
    if len(_by_message) > limit * 4:
        for message_id in list(_by_message)[: len(_by_message) - limit * 4]:
            _by_message.pop(message_id, None)
            removed += 1
    return removed
