"""Playlist musik **per member** — simpan lagu favorit lalu putar kapan saja (**0 kuota AI**).

Penyimpanan JSON ringan (`data/music_playlists.json`), aman untuk Free Tier:

- Maksimal **5 playlist per member** dan **50 lagu per playlist**.
- Maksimal **500 lagu per server** (jaga ukuran berkas & RAM tetap kecil).
- Lagu disimpan sebagai `{"title": ..., "query": ...}`; saat diputar, bot mencari ulang
  lewat Lavalink (tautan langsung tetap dipakai apa adanya).
- Nama playlist tidak peka huruf besar/kecil & tidak boleh dobel per member.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from config import DATA_DIR, MUSIC_PLAYLISTS_FILE

logger = logging.getLogger("gemini_bot.music_playlists")

_lock = asyncio.Lock()

MAX_PLAYLISTS_PER_MEMBER = 5
MAX_TRACKS_PER_PLAYLIST = 50
MAX_TRACKS_PER_GUILD = 500
MAX_NAME_LEN = 32

# guild_id -> user_id -> {nama_kunci: {"name": str, "tracks": [{"title","query"}], ...}}
guild_playlists: dict[int, dict[int, dict[str, dict]]] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _key(name: str) -> str:
    return " ".join(str(name or "").strip().split()).casefold()


def clean_name(name: str) -> tuple[str, str]:
    """Merapikan nama playlist. Mengembalikan `(nama, error)`."""
    pretty = " ".join(str(name or "").split())
    if not pretty:
        return "", "Nama playlist tidak boleh kosong."
    if len(pretty) > MAX_NAME_LEN:
        return "", f"Nama playlist maksimal **{MAX_NAME_LEN} karakter**."
    if _key(pretty) in {"semua", "all", "daftar", "list"}:
        return "", "Nama itu dipakai untuk kata kunci — pilih nama lain."
    return pretty, ""


# ==============================================================================
# BACA
# ==============================================================================
def member_playlists(guild_id: int, user_id: int) -> list[dict]:
    """Daftar playlist milik satu member (urut sesuai waktu dibuat)."""
    return list((guild_playlists.get(int(guild_id), {}).get(int(user_id), {})).values())


def get_playlist(guild_id: int, user_id: int, name: str) -> dict | None:
    return guild_playlists.get(int(guild_id), {}).get(int(user_id), {}).get(_key(name))


def guild_track_total(guild_id: int) -> int:
    total = 0
    for store in guild_playlists.get(int(guild_id), {}).values():
        for data in store.values():
            total += len(data.get("tracks") or [])
    return total


def _entry_from_track(track) -> dict | None:
    title = str(getattr(track, "title", "") or "").strip()
    query = str(getattr(track, "uri", "") or getattr(track, "url", "") or "").strip() or title
    if not title and not query:
        return None
    return {"title": (title or query)[:120], "query": query[:300]}


def tracks_from_queue(tracks, limit: int = MAX_TRACKS_PER_PLAYLIST) -> list[dict]:
    """Mengubah objek lagu (atau dict) menjadi entri playlist."""
    entries: list[dict] = []
    seen: set[str] = set()
    for track in list(tracks or [])[:limit]:
        if isinstance(track, dict):
            entry = {
                "title": str(track.get("title") or track.get("query") or "")[:120],
                "query": str(track.get("query") or track.get("title") or "")[:300],
            }
            if not entry["query"]:
                continue
        else:
            entry = _entry_from_track(track)
            if entry is None:
                continue
        fingerprint = entry["query"].casefold() or entry["title"].casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        entries.append(entry)
    return entries


# ==============================================================================
# TULIS
# ==============================================================================
def save_playlist(
    guild_id: int,
    user_id: int,
    name: str,
    entries: list[dict],
    *,
    replace: bool = True,
) -> tuple[bool, str]:
    """Menyimpan / memperbarui playlist milik member. `(ok, pesan)`."""
    gid, uid = int(guild_id), int(user_id)
    if gid <= 0 or uid <= 0:
        return False, "Server/member tidak dikenali."

    pretty, error = clean_name(name)
    if error:
        return False, error

    cleaned = tracks_from_queue(entries)
    if not cleaned and replace:
        return False, "Tidak ada lagu untuk disimpan."

    store = guild_playlists.setdefault(gid, {}).setdefault(uid, {})
    key = _key(pretty)
    existing = store.get(key)

    if existing is None:
        if len(store) >= MAX_PLAYLISTS_PER_MEMBER:
            return False, f"Kamu sudah punya **{MAX_PLAYLISTS_PER_MEMBER} playlist** (batas maksimal)."
        store[key] = {"name": pretty, "tracks": [], "created_at": 0, "updated_at": 0}
        existing = store[key]

    tracks = [] if replace else list(existing.get("tracks") or [])
    known = {str(t.get("query") or t.get("title") or "").casefold() for t in tracks}
    added = 0
    for entry in cleaned:
        fingerprint = entry["query"].casefold() or entry["title"].casefold()
        if fingerprint in known:
            continue
        if len(tracks) >= MAX_TRACKS_PER_PLAYLIST:
            break
        tracks.append(entry)
        known.add(fingerprint)
        added += 1

    other_total = guild_track_total(gid) - len(existing.get("tracks") or [])
    if other_total + len(tracks) > MAX_TRACKS_PER_GUILD:
        return False, (
            f"Server ini sudah menyimpan **{MAX_TRACKS_PER_GUILD} lagu** di playlist member. "
            "Hapus beberapa lagu dulu ya."
        )

    existing["tracks"] = tracks
    existing["updated_at"] = int(__import__("time").time())
    return True, (
        f"💾 Playlist **{pretty}** {'disimpan' if replace else 'diperbarui'} — "
        f"`{len(tracks)}` lagu" + (f" (`+{added}` baru)." if not replace else ".")
    )


def delete_playlist(guild_id: int, user_id: int, name: str) -> tuple[bool, str]:
    gid, uid = int(guild_id), int(user_id)
    store = guild_playlists.get(gid, {}).get(uid)
    if not store:
        return False, "Kamu belum punya playlist tersimpan."
    key = _key(name)
    data = store.pop(key, None)
    if data is None:
        return False, f"Playlist **{name[:MAX_NAME_LEN]}** tidak ditemukan."
    if not store:
        guild_playlists.get(gid, {}).pop(uid, None)
    return True, f"🗑️ Playlist **{data['name']}** (`{len(data.get('tracks') or [])}` lagu) dihapus."


def rename_playlist(guild_id: int, user_id: int, name: str, new_name: str) -> tuple[bool, str]:
    gid, uid = int(guild_id), int(user_id)
    store = guild_playlists.get(gid, {}).get(uid, {})
    data = store.get(_key(name))
    if data is None:
        return False, f"Playlist **{name[:MAX_NAME_LEN]}** tidak ditemukan."

    pretty, error = clean_name(new_name)
    if error:
        return False, error
    if _key(pretty) == _key(name):
        return False, "Nama baru sama dengan nama lama."
    if _key(pretty) in store:
        return False, f"Kamu sudah punya playlist bernama **{pretty}**."

    store.pop(_key(name), None)
    data["name"] = pretty
    store[_key(pretty)] = data
    return True, f"✏️ Playlist **{name[:MAX_NAME_LEN]}** diganti nama menjadi **{pretty}**."


def remove_track(guild_id: int, user_id: int, name: str, number: int) -> tuple[bool, str]:
    data = get_playlist(guild_id, user_id, name)
    if data is None:
        return False, f"Playlist **{name[:MAX_NAME_LEN]}** tidak ditemukan."
    tracks = data.get("tracks") or []
    index = int(number) - 1
    if index < 0 or index >= len(tracks):
        return False, f"Nomor harus antara **1** dan **{max(1, len(tracks))}**."
    removed = tracks.pop(index)
    if not tracks:
        return delete_playlist(guild_id, user_id, name)
    return True, f"➖ **{removed.get('title')}** dihapus dari **{data['name']}** (`{len(tracks)}` lagu tersisa)."


def clear_playlist(guild_id: int, user_id: int, name: str) -> tuple[bool, str]:
    data = get_playlist(guild_id, user_id, name)
    if data is None:
        return False, f"Playlist **{name[:MAX_NAME_LEN]}** tidak ditemukan."
    data["tracks"] = []
    return True, f"🧹 Semua lagu di **{data['name']}** dikosongkan."


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def load_playlists_from_disk() -> int:
    guild_playlists.clear()
    path = Path(MUSIC_PLAYLISTS_FILE)
    if not path.exists():
        return 0

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, users in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(users, dict):
            continue
        for uid_str, items in users.items():
            uid = _to_int(uid_str)
            if not uid or not isinstance(items, dict):
                continue
            store: dict[str, dict] = {}
            for key, data in items.items():
                if not isinstance(data, dict):
                    continue
                name = str(data.get("name") or key)[:MAX_NAME_LEN]
                tracks = tracks_from_queue(data.get("tracks") or [])
                if not tracks:
                    continue
                store[_key(name)] = {
                    "name": name,
                    "tracks": tracks[:MAX_TRACKS_PER_PLAYLIST],
                    "created_at": _to_int(data.get("created_at")),
                    "updated_at": _to_int(data.get("updated_at")),
                }
                if len(store) >= MAX_PLAYLISTS_PER_MEMBER:
                    break
            if store:
                guild_playlists.setdefault(gid, {})[uid] = store
    return sum(len(users) for users in guild_playlists.values())


async def save_playlists_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {
                    str(gid): {str(uid): store for uid, store in users.items()}
                    for gid, users in guild_playlists.items()
                    if users
                }
            }
            tmp_file = Path(str(MUSIC_PLAYLISTS_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, MUSIC_PLAYLISTS_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan music_playlists.json: %s", exc)


def cleanup_music_playlist_runtime() -> int:
    """Membuang playlist kosong & server tanpa member (jaga RAM tetap kecil)."""
    removed = 0
    for gid, users in list(guild_playlists.items()):
        for uid, store in list(users.items()):
            for key, data in list(store.items()):
                if not data.get("tracks"):
                    store.pop(key, None)
                    removed += 1
            if not store:
                users.pop(uid, None)
        if not users:
            guild_playlists.pop(gid, None)
    return removed
