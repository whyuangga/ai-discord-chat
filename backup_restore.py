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
}
SKIP_TYPES = {"forum", "media", "thread", "category"}


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


def _role_overwrites(entry: dict) -> list[dict]:
    return [
        item
        for item in (entry.get("overwrites") or [])
        if isinstance(item, dict) and _norm(item.get("target_type")) == "role"
    ]


# ==============================================================================
# RENCANA (DRY-RUN)
# ==============================================================================
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
    for role in snapshot.get("roles") or []:
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

    # 2. Kategori
    for category in snapshot.get("categories") or []:
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

    # Peta kategori untuk channel (nama → nama kategori di backup)
    category_by_id = {
        int(cat.get("id") or 0): str(cat.get("name") or "")
        for cat in (snapshot.get("categories") or [])
        if isinstance(cat, dict)
    }

    # 3. Channel
    for entry in snapshot.get("channels") or []:
        if not isinstance(entry, dict):
            continue
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

        category_name = category_by_id.get(int(entry.get("category_id") or 0), "")
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
                "overwrites": _role_overwrites(entry),
            }
        )

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
    return plan


def describe_plan(plan: dict, limit: int = 8) -> str:
    """Teks ringkas rencana untuk ditampilkan di Discord."""
    lines: list[str] = []
    for label, key in (("Role", "roles"), ("Kategori", "categories"), ("Channel", "channels")):
        items = plan.get(key) or []
        if not items:
            continue
        names = ", ".join(f"`{item['name']}`" for item in items[:limit])
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
async def apply_plan(guild, plan: dict, *, actor_id: int = 0, reason: str = "Pemulihan backup") -> dict:
    """Menjalankan rencana. Tidak pernah menghapus apa pun."""
    result = {"roles": 0, "categories": 0, "channels": 0, "errors": [], "overwrites": 0}
    if not plan:
        return result

    reason_text = f"{reason} (oleh {actor_id})"[:400] if actor_id else reason[:400]

    # 1. Role → peta nama ke objek (termasuk role lama, untuk overwrite)
    role_map = {_norm(getattr(r, "name", "")): r for r in getattr(guild, "roles", []) or []}
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
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            result["errors"].append(f"role `{item['name']}`: {type(exc).__name__}")
        await asyncio.sleep(CREATE_DELAY_SEC)

    # 2. Kategori (beserta izin role)
    category_map = {_norm(getattr(c, "name", "")): c for c in getattr(guild, "categories", []) or []}
    for item in plan.get("categories") or []:
        try:
            category = await guild.create_category(name=item["name"], reason=reason_text)
            category_map[_norm(item["name"])] = category
            result["categories"] += 1
            result["overwrites"] += await _apply_overwrites(category, item.get("overwrites"), role_map)
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            result["errors"].append(f"kategori `{item['name']}`: {type(exc).__name__}")
        await asyncio.sleep(CREATE_DELAY_SEC)

    # 3. Channel
    for item in plan.get("channels") or []:
        kind = str(item.get("type") or "text")
        creator_name = CHANNEL_CREATORS.get(kind, "create_text_channel")
        creator = getattr(guild, creator_name, None)
        if not callable(creator):
            result["errors"].append(f"channel `{item['name']}`: tipe `{kind}` tidak didukung")
            continue

        kwargs: dict = {"name": item["name"], "reason": reason_text}
        category = category_map.get(_norm(item.get("category")))
        if category is not None:
            kwargs["category"] = category

        if creator_name == "create_text_channel":
            if item.get("topic"):
                kwargs["topic"] = item["topic"]
            if item.get("nsfw"):
                kwargs["nsfw"] = True
            if int(item.get("slowmode") or 0) > 0:
                kwargs["slowmode_delay"] = min(int(item["slowmode"]), 21600)
        elif creator_name in ("create_voice_channel", "create_stage_channel"):
            if item.get("bitrate"):
                kwargs["bitrate"] = int(item["bitrate"])
            if int(item.get("user_limit") or 0) > 0:
                kwargs["user_limit"] = min(int(item["user_limit"]), 99)

        try:
            channel = await creator(**kwargs)
            result["channels"] += 1
            result["overwrites"] += await _apply_overwrites(channel, item.get("overwrites"), role_map)
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            result["errors"].append(f"channel `{item['name']}`: {type(exc).__name__}")
        await asyncio.sleep(CREATE_DELAY_SEC)

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
