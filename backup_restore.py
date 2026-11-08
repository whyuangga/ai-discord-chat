"""Pemulihan struktur server dari berkas backup `build_server_backup` (**0 kuota AI**).

Fitur ini **hanya menambah** — tidak pernah menghapus, memindahkan, atau menimpa
channel/role yang sudah ada. Aman dipakai setelah kecelakaan (anti-nuke, salah hapus).

Alur kerja
----------
1. `/backup pratinjau` — membaca berkas JSON lalu menampilkan **rencana** (dry-run):
   apa yang akan dibuat, apa yang sudah ada, apa yang dilewati.
2. `/backup pulihkan` — menjalankan rencana yang sama setelah Admin menekan konfirmasi.

Pengaman
--------
- Hanya item yang **belum ada** (dicocokkan dari nama & tipe) yang dibuat.
- Maksimal `MAX_CREATE_TOTAL` item per pemulihan agar tidak kena rate limit Discord.
- Jeda kecil antar pembuatan; kegagalan satu item tidak menghentikan item lain.
- Overwrite izin hanya diterapkan untuk **role yang namanya cocok**; overwrite per-member
  dilewati karena ID member berbeda di server lain.
"""

import asyncio
import inspect
import json
import logging

import discord

logger = logging.getLogger("gemini_bot.backup_restore")

MAX_CREATE_TOTAL = 30
CREATE_DELAY_SEC = 0.25
MAX_FILE_BYTES = 4 * 1024 * 1024

# Tipe channel yang didukung → fungsi pembuat di discord.Guild
CHANNEL_CREATORS = {
    "text": "create_text_channel",
    "voice": "create_voice_channel",
    "stage": "create_stage_channel",
    "news": "create_text_channel",      # announcement → text bila tidak didukung
    "announcement": "create_text_channel",
    "forum": "create_forum",
    "media": "create_forum",            # media channel adalah varian forum di Discord.py
}
SKIP_TYPES = {"thread", "category"}


# ==============================================================================
# PARSING & VALIDASI
# ==============================================================================
def parse_backup(raw: str | bytes) -> tuple[dict | None, str]:
    """Membaca & memvalidasi berkas backup. `(snapshot, "")` atau `(None, alasan)`."""
    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw or "")
    if not text.strip():
        return None, "Berkas kosong."
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"Bukan JSON yang valid (`{exc.msg}`)."

    if not isinstance(data, dict):
        return None, "Struktur berkas tidak dikenali."
    if "roles" not in data and "channels" not in data:
        return None, "Berkas ini bukan backup struktur server (tidak ada `roles`/`channels`)."

    meta = data.get("meta") or {}
    version = int(meta.get("version") or 1) if isinstance(meta, dict) else 1
    if version > 1:
        return None, f"Versi backup `{version}` lebih baru dari yang didukung bot ini (v1)."

    for key in ("roles", "categories", "channels"):
        if key in data and not isinstance(data[key], list):
            return None, f"Bagian `{key}` harus berupa daftar."

    return data, ""


def summarize(snapshot: dict) -> dict:
    """Ringkasan isi berkas backup."""
    meta = snapshot.get("meta") or {}
    return {
        "guild_name": str(meta.get("guild_name") or "-"),
        "guild_id": int(meta.get("guild_id") or 0),
        "generated_at": str(meta.get("generated_at") or "-"),
        "roles": len(snapshot.get("roles") or []),
        "categories": len(snapshot.get("categories") or []),
        "channels": len(snapshot.get("channels") or []),
    }


def _norm(name: object) -> str:
    return str(name or "").strip().casefold()


def _channel_type(entry: dict) -> str:
    """Normalisasi tipe channel dari backup (`text`, `voice`, `news`, …)."""
    raw = _norm(entry.get("type"))
    for key in ("text", "voice", "stage", "news", "announcement", "forum", "media", "category"):
        if raw == key or raw.endswith(key):
            return key
    return "text"


def _ordered_entries(entries) -> list[dict]:
    """Urutkan snapshot secara stabil; item tanpa posisi mempertahankan urutan file."""
    indexed = [(index, item) for index, item in enumerate(entries or []) if isinstance(item, dict)]

    def key(pair):
        index, item = pair
        try:
            position = int(item.get("position", index))
        except (TypeError, ValueError):
            position = index
        return position, index

    return [item for _index, item in sorted(indexed, key=key)]


def _supports_keyword(function, keyword: str) -> bool:
    """Periksa kemampuan versi discord.py tanpa memanggil API saat dry-run."""
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == keyword or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _forum_tags(raw_tags) -> list:
    """Bangun tag forum yang aman dipindah; emoji custom server lama sengaja diabaikan."""
    tags = []
    for raw in (raw_tags or [])[:20]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()[:20]
        if not name:
            continue
        emoji = str(raw.get("emoji") or "").strip()
        if emoji.startswith("<") and emoji.endswith(">"):
            emoji = ""  # ID emoji custom biasanya tidak tersedia di server tujuan.
        try:
            tags.append(
                discord.ForumTag(
                    name=name,
                    emoji=emoji or None,
                    moderated=bool(raw.get("moderated", False)),
                )
            )
        except (AttributeError, TypeError, ValueError):
            continue
    return tags


def _forum_enum(enum_type, raw):
    try:
        return enum_type(int(raw))
    except (TypeError, ValueError):
        return None


def _forum_settings(raw) -> dict:
    """Ambil setelan forum yang diketahui dan batasi data dari berkas backup."""
    if not isinstance(raw, dict):
        return {}
    settings = {}
    for key in (
        "default_auto_archive_duration",
        "default_thread_slowmode_delay",
        "default_sort_order",
        "default_layout",
    ):
        try:
            if raw.get(key) is not None:
                settings[key] = int(raw[key])
        except (TypeError, ValueError):
            continue
    emoji = str(raw.get("default_reaction_emoji") or "").strip()
    if emoji and not (emoji.startswith("<") and emoji.endswith(">")):
        settings["default_reaction_emoji"] = emoji[:100]
    tags = raw.get("available_tags") or []
    if isinstance(tags, list):
        settings["available_tags"] = [
            {
                "name": str(tag.get("name") or "").strip()[:20],
                "emoji": str(tag.get("emoji") or "").strip()[:100],
                "moderated": bool(tag.get("moderated", False)),
            }
            for tag in tags[:20]
            if isinstance(tag, dict) and str(tag.get("name") or "").strip()
        ]
    return settings


def _role_overwrites(entry: dict) -> list[dict]:
    return [
        item
        for item in (entry.get("overwrites") or [])
        if isinstance(item, dict) and _norm(item.get("target_type")) == "role"
    ]


# ==============================================================================
# RENCANA (DRY-RUN)
# ==============================================================================
def _rencana_role(plan: dict, snapshot: dict, existing_roles: set, *, buat_role: bool) -> None:
    """Tambahkan role baru ke rencana (yang sudah ada/dinonaktifkan dilewati)."""
    for role in _ordered_entries(snapshot.get("roles") or []):
        if not isinstance(role, dict):
            continue
        name = str(role.get("name") or "").strip()
        if not name:
            continue
        if _norm(name) in existing_roles:
            plan["already"]["roles"] += 1
            continue
        if not buat_role:
            plan["skipped"].append(f"role `{name}` (dinonaktifkan)")
            continue
        plan["roles"].append(
            {
                "name": name[:100],
                "permissions": int(role.get("permissions") or 0),
                "colour": int(role.get("colour") or role.get("color") or 0),
                "hoist": bool(role.get("hoist", False)),
                "mentionable": bool(role.get("mentionable", False)),
            }
        )


def _rencana_kategori(
    plan: dict, snapshot: dict, existing_categories: set, *, buat_kategori: bool
) -> None:
    """Tambahkan kategori baru ke rencana."""
    for category in _ordered_entries(snapshot.get("categories") or []):
        if not isinstance(category, dict):
            continue
        name = str(category.get("name") or "").strip()
        if not name:
            continue
        if _norm(name) in existing_categories:
            plan["already"]["categories"] += 1
            continue
        if not buat_kategori:
            plan["skipped"].append(f"kategori `{name}` (dinonaktifkan)")
            continue
        plan["categories"].append({"name": name[:100], "overwrites": _role_overwrites(category)})


def _peta_kategori(snapshot: dict) -> dict[int, str]:
    """Peta `id kategori -> nama` untuk memindahkan channel ke kategorinya."""
    category_by_id: dict[int, str] = {}
    for cat in snapshot.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        try:
            category_id = int(cat.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if category_id:
            category_by_id[category_id] = str(cat.get("name") or "").strip()
    return category_by_id


def _rencana_channel(
    guild, plan: dict, snapshot: dict, category_by_id: dict, *, buat_channel: bool
) -> None:
    """Tambahkan channel baru ke rencana (tipe tak didukung dilewati)."""
    for entry in _ordered_entries(snapshot.get("channels") or []):
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        kind = _channel_type(entry)
        if kind in SKIP_TYPES:
            plan["skipped"].append(f"channel `{name}` (tipe `{kind}` belum didukung)")
            continue
        if any(_norm(getattr(ch, "name", "")) == _norm(name) for ch in getattr(guild, "channels", []) or []):
            plan["already"]["channels"] += 1
            continue
        if not buat_channel:
            plan["skipped"].append(f"channel `{name}` (dinonaktifkan)")
            continue
        creator_name = CHANNEL_CREATORS.get(kind)
        creator = getattr(guild, creator_name, None) if creator_name else None
        if not callable(creator):
            plan["skipped"].append(f"channel `{name}` (tipe `{kind}` tidak tersedia di versi Discord.py ini)")
            continue
        if kind == "media" and not _supports_keyword(creator, "media"):
            plan["skipped"].append(
                f"channel `{name}` (media channel membutuhkan Discord.py 2.6 atau lebih baru)"
            )
            continue

        try:
            category_id = int(entry.get("category_id") or 0)
        except (TypeError, ValueError):
            category_id = 0
        category_name = category_by_id.get(category_id, "") or str(entry.get("category") or "").strip()
        plan["channels"].append(
            {
                "name": name[:100],
                "type": kind,
                "category": category_name,
                "topic": str(entry.get("topic") or "")[:1024] or None,
                "nsfw": bool(entry.get("nsfw", False)),
                "slowmode": max(0, int(entry.get("slowmode") or 0)),
                "bitrate": entry.get("bitrate"),
                "user_limit": max(0, int(entry.get("user_limit") or 0)),
                "forum": _forum_settings(entry.get("forum")),
                "overwrites": _role_overwrites(entry),
            }
        )


def _potong_batas(plan: dict) -> None:
    """Batasi jumlah item agar aman dari rate limit (role -> kategori -> channel)."""
    total = len(plan["roles"]) + len(plan["categories"]) + len(plan["channels"])
    plan["total"] = total
    if total > MAX_CREATE_TOTAL:
        # Potong agar aman dari rate limit (prioritas: role → kategori → channel)
        sisa = MAX_CREATE_TOTAL
        for key in ("roles", "categories", "channels"):
            plan[key] = plan[key][:sisa]
            sisa -= len(plan[key])
            if sisa <= 0:
                sisa = 0
        plan["skipped"].append(
            f"{total - MAX_CREATE_TOTAL} item lain (batas {MAX_CREATE_TOTAL} item per pemulihan)"
        )
        plan["total"] = MAX_CREATE_TOTAL


def build_plan(
    guild,
    snapshot: dict,
    *,
    buat_role: bool = True,
    buat_kategori: bool = True,
    buat_channel: bool = True,
) -> dict:
    """Menghitung apa yang perlu dibuat. Tidak mengubah server sama sekali."""
    existing_roles = {_norm(getattr(role, "name", "")) for role in getattr(guild, "roles", []) or []}
    existing_categories = {
        _norm(getattr(cat, "name", "")) for cat in getattr(guild, "categories", []) or []
    }
    existing_channels = set()
    for channel in getattr(guild, "channels", []) or []:
        if isinstance(channel, discord.CategoryChannel):
            continue
        existing_channels.add((_norm(getattr(channel, "name", "")), str(getattr(channel, "type", ""))))

    plan: dict = {
        "guild_id": int(getattr(guild, "id", 0)),
        "roles": [],
        "categories": [],
        "channels": [],
        "skipped": [],
        "already": {"roles": 0, "categories": 0, "channels": 0},
    }

    # 1. Role
    _rencana_role(plan, snapshot, existing_roles, buat_role=buat_role)

    # 2. Kategori; proses sesuai posisi sumber agar item baru berurutan.
    _rencana_kategori(plan, snapshot, existing_categories, buat_kategori=buat_kategori)

    # 3. Channel; proses sesuai posisi sumber agar urutan item baru tetap terjaga.
    _rencana_channel(
        guild, plan, snapshot, _peta_kategori(snapshot), buat_channel=buat_channel
    )

    _potong_batas(plan)
    return plan


def describe_plan(plan: dict, limit: int = 8) -> str:
    """Teks ringkas rencana untuk ditampilkan di Discord."""
    lines: list[str] = []
    for label, key in (("Role", "roles"), ("Kategori", "categories"), ("Channel", "channels")):
        items = plan.get(key) or []
        if not items:
            continue

        def format_item(item):
            name = f"`{item['name']}`"
            if key != "channels":
                return name
            kind = str(item.get("type") or "text")
            category = str(item.get("category") or "").strip()
            target = f" → `{category}`" if category else ""
            return f"{name} ({kind}{target})"

        names = ", ".join(format_item(item) for item in items[:limit])
        extra = f" … (+{len(items) - limit} lagi)" if len(items) > limit else ""
        lines.append(f"• **{label} baru ({len(items)}):** {names}{extra}")
    skipped = plan.get("skipped") or []
    if skipped:
        preview = ", ".join(skipped[:5]) + (" …" if len(skipped) > 5 else "")
        lines.append(f"• **Dilewati:** {preview}")
    already = plan.get("already") or {}
    lines.append(
        f"• **Sudah ada:** `{already.get('roles', 0)}` role • "
        f"`{already.get('categories', 0)}` kategori • `{already.get('channels', 0)}` channel"
    )
    return "\n".join(lines)


# ==============================================================================
# EKSEKUSI
# ==============================================================================
def _created_item(obj, fallback_name: str) -> dict:
    """Ringkas objek hasil API jadi `{id, name}` untuk rollback presisi."""
    raw_id = getattr(obj, "id", None)
    try:
        item_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        item_id = None
    return {
        "id": item_id,
        "name": str(getattr(obj, "name", fallback_name) or fallback_name)[:100],
    }


async def _buat_role_plan(
    guild, plan: dict, result: dict, role_map: dict, reason_text: str
) -> None:
    """Buat role dari rencana, catat kegagalan per item."""
    for item in plan.get("roles") or []:
        try:
            role = await guild.create_role(
                name=item["name"],
                permissions=discord.Permissions(int(item.get("permissions") or 0)),
                colour=discord.Colour(int(item.get("colour") or 0)),
                hoist=bool(item.get("hoist")),
                mentionable=bool(item.get("mentionable")),
                reason=reason_text,
            )
            role_map[_norm(item["name"])] = role
            result["roles"] += 1
            result["created"]["roles"].append(_created_item(role, item["name"]))
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            result["errors"].append(f"role `{item['name']}`: {type(exc).__name__}")
        await asyncio.sleep(CREATE_DELAY_SEC)


async def _buat_kategori_plan(
    guild, plan: dict, result: dict, category_map: dict, role_map: dict, reason_text: str
) -> None:
    """Buat kategori beserta izin per-role."""
    for item in plan.get("categories") or []:
        try:
            category = await guild.create_category(name=item["name"], reason=reason_text)
            category_map[_norm(item["name"])] = category
            result["categories"] += 1
            result["created"]["categories"].append(_created_item(category, item["name"]))
            result["overwrites"] += await _apply_overwrites(category, item.get("overwrites"), role_map)
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            result["errors"].append(f"kategori `{item['name']}`: {type(exc).__name__}")
        await asyncio.sleep(CREATE_DELAY_SEC)


def _siapkan_kwargs(
    item: dict,
    creator_name: str,
    kind: str,
    category_map: dict,
    result: dict,
    reason_text: str,
) -> dict | None:
    """Rakit argumen pembuatan channel; `None` bila kategori tujuan tidak ada."""
    kwargs: dict = {"name": item["name"], "reason": reason_text}
    category_name = str(item.get("category") or "").strip()
    category = category_map.get(_norm(category_name)) if category_name else None
    if category_name and category is None:
        result["errors"].append(
            f"channel `{item['name']}`: kategori `{category_name}` tidak tersedia"
        )
        return None
    if category is not None:
        kwargs["category"] = category

    if creator_name in ("create_text_channel", "create_forum"):
        if item.get("topic"):
            kwargs["topic"] = item["topic"]
        if item.get("nsfw"):
            kwargs["nsfw"] = True
        if int(item.get("slowmode") or 0) > 0:
            kwargs["slowmode_delay"] = min(int(item["slowmode"]), 21600)
    if creator_name == "create_forum":
        forum = _forum_settings(item.get("forum"))
        if kind == "media":
            kwargs["media"] = True
        archive_duration = forum.get("default_auto_archive_duration")
        if archive_duration in {60, 1440, 4320, 10080}:
            kwargs["default_auto_archive_duration"] = archive_duration
        thread_slowmode = forum.get("default_thread_slowmode_delay")
        if thread_slowmode is not None:
            kwargs["default_thread_slowmode_delay"] = max(0, min(thread_slowmode, 21600))
        sort_order = _forum_enum(discord.ForumOrderType, forum.get("default_sort_order"))
        if sort_order is not None:
            kwargs["default_sort_order"] = sort_order
        if kind != "media":
            layout = _forum_enum(discord.ForumLayoutType, forum.get("default_layout"))
            if layout is not None:
                kwargs["default_layout"] = layout
        reaction_emoji = forum.get("default_reaction_emoji")
        if reaction_emoji:
            kwargs["default_reaction_emoji"] = reaction_emoji
        tags = _forum_tags(forum.get("available_tags"))
        if tags:
            kwargs["available_tags"] = tags
    elif creator_name in ("create_voice_channel", "create_stage_channel"):
        if item.get("bitrate"):
            kwargs["bitrate"] = int(item["bitrate"])
        if int(item.get("user_limit") or 0) > 0:
            kwargs["user_limit"] = min(int(item["user_limit"]), 99)
    return kwargs

async def _buat_channel_plan(
    guild, plan: dict, result: dict, category_map: dict, role_map: dict, reason_text: str
) -> None:
    """Buat channel sesuai tipe, kategori, dan izin per-role."""
    for item in plan.get("channels") or []:
        kind = str(item.get("type") or "text")
        creator_name = CHANNEL_CREATORS.get(kind)
        creator = getattr(guild, creator_name, None) if creator_name else None
        if not callable(creator):
            result["errors"].append(f"channel `{item['name']}`: tipe `{kind}` tidak didukung")
            continue
        if kind == "media" and not _supports_keyword(creator, "media"):
            result["errors"].append(
                f"channel `{item['name']}`: media channel membutuhkan Discord.py 2.6 atau lebih baru"
            )
            continue

        kwargs = _siapkan_kwargs(item, creator_name, kind, category_map, result, reason_text)
        if kwargs is None:
            continue

        try:
            channel = await creator(**kwargs)
            result["channels"] += 1
            result["created"]["channels"].append(_created_item(channel, item["name"]))
            result["overwrites"] += await _apply_overwrites(
                channel, item.get("overwrites"), role_map
            )
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            result["errors"].append(f"channel `{item['name']}`: {type(exc).__name__}")
        await asyncio.sleep(CREATE_DELAY_SEC)


async def apply_plan(guild, plan: dict, *, actor_id: int = 0, reason: str = "Pemulihan backup") -> dict:
    """Menjalankan rencana. Tidak pernah menghapus apa pun."""
    result = {
        "roles": 0,
        "categories": 0,
        "channels": 0,
        "errors": [],
        "overwrites": 0,
        # Objek sukses yang dikembalikan API, untuk rollback berbasis ID yang presisi.
        "created": {"roles": [], "categories": [], "channels": []},
    }
    if not plan:
        return result
    reason_text = f"{reason} (oleh {actor_id})"[:400] if actor_id else reason[:400]

    # 1. Role -> peta nama ke objek (termasuk role lama, untuk overwrite)
    role_map = {
        _norm(getattr(r, "name", "")): r for r in getattr(guild, "roles", []) or []
    }
    await _buat_role_plan(guild, plan, result, role_map, reason_text)

    # 2. Kategori (beserta izin role)
    category_map = {
        _norm(getattr(c, "name", "")): c for c in getattr(guild, "categories", []) or []
    }
    await _buat_kategori_plan(
        guild, plan, result, category_map, role_map, reason_text
    )

    # 3. Channel
    await _buat_channel_plan(guild, plan, result, category_map, role_map, reason_text)

    return result


async def _apply_overwrites(target, overwrites, role_map: dict) -> int:
    """Menerapkan izin per-role (dicocokkan dari nama). Mengembalikan jumlah yang berhasil."""
    applied = 0
    for entry in overwrites or []:
        role = role_map.get(_norm(entry.get("target_name")))
        if role is None:
            continue
        try:
            await target.set_permissions(
                role,
                allow=discord.Permissions(int(entry.get("allow") or 0)),
                deny=discord.Permissions(int(entry.get("deny") or 0)),
                reason="Pemulihan backup (izin role)",
            )
            applied += 1
        except (discord.Forbidden, discord.HTTPException, TypeError):
            continue
    return applied


def describe_result(result: dict) -> str:
    """Teks ringkas hasil pemulihan."""
    lines = [
        f"• **Role dibuat:** `{result.get('roles', 0)}`",
        f"• **Kategori dibuat:** `{result.get('categories', 0)}`",
        f"• **Channel dibuat:** `{result.get('channels', 0)}`",
        f"• **Izin role diterapkan:** `{result.get('overwrites', 0)}`",
    ]
    errors = result.get("errors") or []
    if errors:
        preview = "\n".join(f"• {item}" for item in errors[:5])
        lines.append(f"\n⚠️ **Gagal ({len(errors)}):**\n{preview}" + ("\n…" if len(errors) > 5 else ""))
    return "\n".join(lines)
