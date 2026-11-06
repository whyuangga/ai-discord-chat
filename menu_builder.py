"""Menu Builder & Self Roles v2 — tombol/dropdown untuk **role, link, & command**.

Fitur ini membuat panel interaktif buatan Admin sendiri (0 kuota AI):

| Jenis item | Contoh | Aksi saat diklik |
| :--- | :--- | :--- |
| **Role** | `🎮 Gamer` | Member mendapat role; klik lagi = role dilepas (*toggle*) |
| **Link** | `🔗 Support Server` | Membuka URL (tanpa aksi bot) |
| **Command** | `📊 Statistik` | Menjalankan command aman, mis. `/serverstats lihat` |

Semua panel **persisten**: `custom_id` disimpan di `data/menus.json`, jadi tombol tetap
hidup setelah bot restart (`bot.add_view` saat `on_ready`).

Keamanan:
- Aksi dijalankan atas nama **member yang mengklik** → cek izin Admin/staff tetap berlaku.
- Command hanya boleh dari **whitelist** `SAFE_COMMANDS` (read-only/informasi). Command
  berbahaya (`ban`, `purge`, `lockdown`, `backup`, `/ekonomi atur`, …) tidak bisa dipasang.
- Role hadiah wajib **di bawah** role bot & bot punya izin *Manage Roles*.
"""

import asyncio
import base64
import io
import json
import logging
import os
import secrets
import time
import zlib
from pathlib import Path

import discord
from discord import ui

import flows
import message_template
import modal_forms
import ui_kit
import ui_theme
from config import DATA_DIR, MENU_FILE, SITE_BASE_URL

logger = logging.getLogger("gemini_bot.menu_builder")

_lock = asyncio.Lock()

# ------------------------------------------------------------------------------
# BATAS & KONSTANTA
# ------------------------------------------------------------------------------
KIND_ROLE = "role"
KIND_LINK = "link"
KIND_COMMAND = "command"
KIND_FLOW = "flow"      # tombol dengan alur aksi (lihat flows.py)
KIND_FORM = "form"      # tombol yang membuka formulir/modal (lihat modal_forms.py)

VIS_AUTO = "auto"          # ikuti keputusan command (bawaan)
VIS_PUBLIK = "publik"      # paksa tampil di channel
VIS_EPHEMERAL = "ephemeral"  # paksa hanya terlihat oleh pengklik

MENU_KIND_MENU = "menu"    # /menu (bebas: role + link + command)
MENU_KIND_ROLES = "roles"  # /panel-role (khusus self roles)

MAX_BUTTONS = 20           # 4 baris × 5 tombol
MAX_DROPDOWNS = 2
MAX_OPTIONS = 25
MAX_TITLE = 120
MAX_DESCRIPTION = 1500
MAX_MENUS_PER_GUILD = 20
ROLE_COOLDOWN_SEC = 3.0
MAX_BANNER_BYTES = 8 * 1024 * 1024

BUTTON_STYLES = {
    "biru": discord.ButtonStyle.primary,
    "abu": discord.ButtonStyle.secondary,
    "hijau": discord.ButtonStyle.success,
    "merah": discord.ButtonStyle.danger,
}

# Whitelist command yang boleh dipakai tombol. Hanya yang aman/informasi.
SAFE_COMMANDS: dict[str, dict] = {
    "serverstats": {"label": "Statistik Server", "emoji": "📊", "path": ("serverstats", "lihat"),
                    "desc": "/serverstats lihat"},
    "level": {"label": "Level Saya", "emoji": "📈", "path": ("level", "lihat"), "desc": "/level lihat"},
    "level_papan": {"label": "Papan Level", "emoji": "🏆", "path": ("level", "papan"),
                    "desc": "/level papan"},
    "tumbuh": {"label": "Pertumbuhan", "emoji": "🌱", "path": ("tumbuh", "ringkas"),
               "desc": "/tumbuh ringkas"},
    "tumbuh_undang": {"label": "Top Inviter", "emoji": "🎟️", "path": ("tumbuh", "undang"),
                      "desc": "/tumbuh undang"},
    "ekonomi_saldo": {"label": "Saldo Koin", "emoji": "💰", "path": ("ekonomi", "saldo"),
                      "desc": "/ekonomi saldo"},
    "ekonomi_papan": {"label": "Papan Koin", "emoji": "🏦", "path": ("ekonomi", "papan"),
                      "desc": "/ekonomi papan"},
    "ekonomi_toko": {"label": "Toko Server", "emoji": "🛒", "path": ("ekonomi", "toko"),
                     "desc": "/ekonomi toko"},
    "tiket": {"label": "Daftar Tiket", "emoji": "🎟️", "path": ("tiket", "daftar"),
              "desc": "/tiket daftar"},
    "log_status": {"label": "Status Audit Log", "emoji": "📋", "path": ("log", "status"),
                   "desc": "/log status"},
    "pemakaian": {"label": "Pemakaian AI", "emoji": "🔋", "path": ("pemakaian", "lihat"),
                  "desc": "/pemakaian lihat"},
    "musik_sekarang": {"label": "Lagu Sekarang", "emoji": "🎵", "path": ("musik", "sekarang"),
                       "desc": "/musik sekarang"},
    "game_papan": {"label": "Papan Skor Game", "emoji": "🕹️", "path": ("game", "papan_skor"),
                   "desc": "/game papan_skor"},
    "faq": {"label": "Daftar FAQ", "emoji": "❓", "path": ("faq", "daftar"), "desc": "/faq daftar"},
    "bantuan": {"label": "Pusat Bantuan", "emoji": "📖", "path": ("bantuan",), "desc": "/bantuan"},
    "status": {"label": "Status Bot", "emoji": "🩺", "path": ("status",), "desc": "/status"},
}

# ------------------------------------------------------------------------------
# STATE
# ------------------------------------------------------------------------------
menus: dict[int, dict[str, dict]] = {}      # guild_id -> menu_id -> menu
_role_cooldown: dict[str, float] = {}       # "guild:user" -> timestamp terakhir


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def new_menu_id() -> str:
    return "m" + secrets.token_hex(4)


def _now() -> float:
    return time.time()


# ==============================================================================
# CRUD MENU
# ==============================================================================
def get_menu(guild_id: int, ref: str | None) -> dict | None:
    """Cari menu berdasarkan ID atau judul (tidak peka huruf besar/kecil)."""
    bucket = menus.get(int(guild_id)) or {}
    if not bucket:
        return None
    if ref:
        clean = str(ref).strip()
        if clean in bucket:
            return bucket[clean]
        lowered = clean.casefold()
        for menu in bucket.values():
            if str(menu.get("title", "")).casefold() == lowered:
                return menu
    return None


def list_menus(guild_id: int) -> list[dict]:
    bucket = menus.get(int(guild_id)) or {}
    return sorted(bucket.values(), key=lambda m: float(m.get("created_at") or 0))


def create_menu(
    guild_id: int,
    title: str,
    *,
    description: str = "",
    kind: str = MENU_KIND_MENU,
    banner_url: str | None = None,
    channel_id: int | None = None,
) -> dict | None:
    """Membuat panel baru. `None` bila kuota panel server sudah penuh/judul kosong."""
    gid = int(guild_id)
    bucket = menus.setdefault(gid, {})
    if len(bucket) >= MAX_MENUS_PER_GUILD:
        return None
    clean_title = str(title or "").strip()[:MAX_TITLE]
    if not clean_title:
        return None

    menu_id = new_menu_id()
    while menu_id in bucket:
        menu_id = new_menu_id()

    menu = {
        "id": menu_id,
        "guild_id": gid,
        "channel_id": _to_int(channel_id) or None,
        "message_id": None,
        "title": clean_title,
        "description": str(description or "").strip()[:MAX_DESCRIPTION],
        "banner_url": (str(banner_url).strip()[:400] if banner_url else None),
        "kind": kind if kind in (MENU_KIND_MENU, MENU_KIND_ROLES) else MENU_KIND_MENU,
        "buttons": [],
        "dropdowns": [],
        "created_at": _now(),
    }
    bucket[menu_id] = menu
    return menu


# ------------------------------------------------------------------------------
# EKSPOR / IMPOR (backup & pindah server)
# ------------------------------------------------------------------------------
EXPORT_FORMAT = "ai-discord-chat/panel"
EXPORT_VERSION = 1
MAX_IMPORT_BYTES = 256 * 1024

# Tautan bagikan: panel → kode base64url → halaman `SITE_BASE_URL/p/<kode>`.
SHARE_PREFIX = "ai-discord-chat/panel:"
MAX_SHARE_CODE = 1500     # batas agar URL masih nyaman di Discord
SHARE_ZLIB_PREFIX = "z."  # penanda kode terkompresi (kode lama tanpa awalan tetap terbaca)
MAX_SHARE_RAW = 64 * 1024  # batas hasil dekompresi (jaga-jaga kode "bom")


def export_menu(menu: dict) -> dict:
    """Payload portabel untuk satu panel — tanpa ID guild/channel/pesan."""
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "title": menu.get("title"),
        "description": menu.get("description"),
        "banner_url": menu.get("banner_url"),
        "buttons": [
            {k: v for k, v in item.items() if k != "id"} for item in menu.get("buttons", [])
        ],
        "dropdowns": [
            {
                "placeholder": dropdown.get("placeholder"),
                "exclusive": bool(dropdown.get("exclusive")),
                "group": dropdown.get("group"),
                "options": [
                    {k: v for k, v in opt.items() if k != "id"}
                    for opt in dropdown.get("options", [])
                ],
            }
            for dropdown in menu.get("dropdowns", [])
        ],
    }


# ------------------------------------------------------------------------------
# TAUTAN BAGIKAN (kode / URL, tanpa berkas)
# ------------------------------------------------------------------------------
def encode_share(menu: dict) -> tuple[str, list[str]]:
    """Panel → kode bagikan base64url. `("", galat)` bila panelnya terlalu besar."""
    teks = json.dumps(export_menu(menu), ensure_ascii=False, separators=(",", ":"))
    kode = base64.urlsafe_b64encode(zlib.compress(teks.encode("utf-8"), 9)).decode("ascii")
    kode = SHARE_ZLIB_PREFIX + kode.rstrip("=")
    if len(kode) > MAX_SHARE_CODE:
        return "", [
            f"Panel ini terlalu besar untuk tautan bagikan ({len(kode)} dari "
            f"{MAX_SHARE_CODE} karakter). Ringkas teks/tombolnya atau pakai `/menu ekspor` "
            "(berkas JSON)."
        ]
    return kode, []


def share_url(kode: str, base: str | None = None) -> str:
    """URL halaman pratinjau panel di situs dokumentasi."""
    akar = str(base or SITE_BASE_URL).rstrip("/")
    return f"{akar}/p/{kode}"


def extract_share_code(text: str) -> str:
    """Ambil kode dari URL `/p/<kode>`, kode berawalan `ai-discord-chat/panel:`, atau kode polos."""
    bersih = str(text or "").strip()
    if "/p/" in bersih:
        bersih = bersih.split("/p/", 1)[1]
    bersih = bersih.split("#", 1)[0].split("?", 1)[0].strip()
    if bersih.startswith(SHARE_PREFIX):
        bersih = bersih[len(SHARE_PREFIX):]
    return bersih.strip("/ ")


def decode_share(text: str) -> tuple[dict | None, list[str]]:
    """Kode/URL bagikan → payload siap `import_menu`. Kembalikan `(payload, galat)`."""
    kode = extract_share_code(text)
    if not kode:
        return None, ["Tautan bagikan kosong. Tempel kode dari `/menu bagikan`."]
    if len(kode) > MAX_SHARE_CODE:
        return None, [f"Kode terlalu panjang (maksimal {MAX_SHARE_CODE} karakter)."]
    terkompresi = kode.startswith(SHARE_ZLIB_PREFIX)
    if terkompresi:
        kode = kode[len(SHARE_ZLIB_PREFIX):]
    padding = "=" * (-len(kode) % 4)
    try:
        mentah = base64.urlsafe_b64decode(kode + padding)
        if terkompresi:
            mentah = zlib.decompressobj().decompress(mentah, MAX_SHARE_RAW)
        payload = json.loads(mentah.decode("utf-8"))
    except Exception:
        return None, ["Kode tidak bisa dibaca — pastikan menyalin seluruh tautannya."]
    if not isinstance(payload, dict):
        return None, ["Kode bukan ekspor panel bot ini."]
    return payload, []


def import_menu(
    guild_id: int,
    payload: dict,
    *,
    title: str | None = None,
) -> tuple[dict | None, list[str]]:
    """Buat panel dari payload ekspor. Kembalikan `(menu, galat)`."""
    galat: list[str] = []
    if not isinstance(payload, dict):
        return None, ["Isi berkas bukan objek JSON."]
    if str(payload.get("format") or "").strip() not in ("", EXPORT_FORMAT):
        return None, ["Berkas ini bukan ekspor panel bot ini."]
    versi = _to_int(payload.get("version") or EXPORT_VERSION)
    if versi > EXPORT_VERSION:
        return None, [f"Versi ekspor {versi} lebih baru dari yang didukung bot ({EXPORT_VERSION})."]

    tombol_masuk = payload.get("buttons") or []
    dropdown_masuk = payload.get("dropdowns") or []
    if not isinstance(tombol_masuk, list) or not isinstance(dropdown_masuk, list):
        return None, ["Bagian `buttons`/`dropdowns` harus berupa daftar."]

    menu = create_menu(
        guild_id,
        (title or payload.get("title") or "Panel Impor"),
        description=str(payload.get("description") or "")[:MAX_DESCRIPTION],
        banner_url=(str(payload.get("banner_url"))[:400] if payload.get("banner_url") else None),
    )
    if menu is None:
        return None, [f"Kuota panel server penuh (maksimal {MAX_MENUS_PER_GUILD}) atau judul kosong."]

    for item in tombol_masuk[:MAX_BUTTONS]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        label = str(item.get("label") or "")[:80]
        style = str(item.get("style") or "abu")
        emoji = item.get("emoji") or None
        if kind == KIND_ROLE:
            role_id = _to_int(item.get("role_id"))
            if not role_id:
                galat.append(f"Tombol role “{label}” dilewati (ID role tidak ada).")
                continue
            menu["buttons"].append(
                {
                    "id": _new_item_id(menu),
                    "kind": KIND_ROLE,
                    "label": label or "Role",
                    "emoji": emoji,
                    "style": style if style in BUTTON_STYLES else "abu",
                    "role_id": role_id,
                    "group": (str(item.get("group"))[:40] if item.get("group") else None),
                }
            )
        elif kind == KIND_LINK:
            url = str(item.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                galat.append(f"Tombol tautan “{label}” dilewati (URL tidak valid).")
                continue
            menu["buttons"].append(
                {
                    "id": _new_item_id(menu),
                    "kind": KIND_LINK,
                    "label": label or "Buka",
                    "emoji": emoji,
                    "url": url[:400],
                }
            )
        elif kind == KIND_COMMAND:
            key = str(item.get("command") or "")
            spec = SAFE_COMMANDS.get(key)
            if spec is None:
                galat.append(f"Tombol command “{label}” dilewati (command tidak ada di daftar aman).")
                continue
            menu["buttons"].append(
                {
                    "id": _new_item_id(menu),
                    "kind": KIND_COMMAND,
                    "label": (label or spec["label"])[:80],
                    "emoji": emoji or spec.get("emoji"),
                    "style": style if style in BUTTON_STYLES else "biru",
                    "command": key,
                    "visibility": str(item.get("visibility") or VIS_AUTO),
                }
            )
        elif kind == KIND_FLOW:
            langkah = flows.sanitize_steps(item.get("flow"))
            if not langkah:
                galat.append(f"Tombol alur “{label}” dilewati (alur kosong/tidak valid).")
                continue
            menu["buttons"].append(
                {
                    "id": _new_item_id(menu),
                    "kind": KIND_FLOW,
                    "label": label or "Aksi",
                    "emoji": emoji,
                    "style": style if style in BUTTON_STYLES else "biru",
                    "flow": langkah,
                }
            )
        elif kind == KIND_FORM:
            galat.append(
                f"Tombol formulir “{label}” dilewati — formulir tidak ikut diekspor. "
                "Buat ulang lewat `/menu form buat`."
            )

    for dropdown in dropdown_masuk[:MAX_DROPDOWNS]:
        if not isinstance(dropdown, dict):
            continue
        opsi: list[dict] = []
        for opt in (dropdown.get("options") or [])[:MAX_OPTIONS]:
            if not isinstance(opt, dict):
                continue
            role_id = _to_int(opt.get("role_id"))
            if not role_id:
                continue
            opsi.append(
                {
                    "id": _new_item_id(menu),
                    "kind": KIND_ROLE,
                    "role_id": role_id,
                    "label": str(opt.get("label") or "Role")[:100],
                    "emoji": opt.get("emoji") or None,
                    "description": (str(opt.get("description") or "")[:100] or None),
                }
            )
        if not opsi:
            continue
        menu["dropdowns"].append(
            {
                "id": "d" + secrets.token_hex(3),
                "placeholder": str(dropdown.get("placeholder") or "Pilih role…")[:150],
                "exclusive": bool(dropdown.get("exclusive")),
                "group": str(dropdown.get("group") or "dropdown")[:40],
                "options": opsi,
            }
        )

    if not menu["buttons"] and not menu["dropdowns"]:
        delete_menu(guild_id, menu["id"])
        galat.append("Tidak ada tombol/dropdown yang bisa dipulihkan dari berkas itu.")
        return None, galat

    return menu, galat


def update_menu_text(
    menu: dict,
    *,
    title: str | None = None,
    description: str | None = None,
) -> list[str]:
    """Ubah judul/deskripsi panel yang sudah terkirim (tanpa kirim ulang)."""
    galat: list[str] = []
    if title is not None:
        bersih = str(title).strip()[:MAX_TITLE]
        if not bersih:
            galat.append("Judul tidak boleh kosong.")
        else:
            menu["title"] = bersih
    if description is not None:
        menu["description"] = str(description).strip()[:MAX_DESCRIPTION]
    return galat


def delete_menu(guild_id: int, menu_id: str) -> bool:
    bucket = menus.get(int(guild_id)) or {}
    return bucket.pop(str(menu_id), None) is not None


def set_banner(menu: dict, url: str | None) -> None:
    menu["banner_url"] = (str(url).strip()[:400] if url else None)


def _new_item_id(menu: dict) -> str:
    existing = {str(item.get("id")) for item in menu["buttons"]}
    for option in menu["dropdowns"]:
        existing.update(str(opt.get("id")) for opt in option.get("options", []))
    while True:
        candidate = "i" + secrets.token_hex(3)
        if candidate not in existing:
            return candidate


def count_items(menu: dict) -> int:
    return len(menu["buttons"]) + sum(len(d.get("options", [])) for d in menu["dropdowns"])


def role_ids_in_group(menu: dict, group: str) -> list[int]:
    """Semua `role_id` pada grup tertentu (tombol + dropdown)."""
    if not group:
        return []
    ids: list[int] = []
    for item in menu["buttons"]:
        if item.get("kind") == KIND_ROLE and item.get("group") == group:
            ids.append(_to_int(item.get("role_id")))
    for dropdown in menu["dropdowns"]:
        if dropdown.get("group") != group:
            continue
        for option in dropdown.get("options", []):
            if option.get("kind") == KIND_ROLE:
                ids.append(_to_int(option.get("role_id")))
    return [rid for rid in ids if rid]


def add_role_button(
    menu: dict,
    role_id: int,
    label: str,
    *,
    emoji: str | None = None,
    style: str = "abu",
    group: str | None = None,
) -> dict | None:
    if len(menu["buttons"]) >= MAX_BUTTONS:
        return None
    if any(item.get("kind") == KIND_ROLE and _to_int(item.get("role_id")) == _to_int(role_id)
           for item in menu["buttons"]):
        return None
    item = {
        "id": _new_item_id(menu),
        "kind": KIND_ROLE,
        "label": str(label or "")[:80] or "Role",
        "emoji": emoji or None,
        "style": style if style in BUTTON_STYLES else "abu",
        "role_id": _to_int(role_id),
        "group": (str(group)[:40] if group else None),
    }
    menu["buttons"].append(item)
    return item


def add_link_button(menu: dict, label: str, url: str, *, emoji: str | None = None) -> dict | None:
    if len(menu["buttons"]) >= MAX_BUTTONS:
        return None
    clean_url = str(url or "").strip()
    if not clean_url.startswith(("http://", "https://")):
        return None
    item = {
        "id": _new_item_id(menu),
        "kind": KIND_LINK,
        "label": (str(label or "").strip() or "Buka")[:80],
        "emoji": emoji or None,
        "url": clean_url[:400],
    }
    menu["buttons"].append(item)
    return item


def add_command_button(
    menu: dict,
    command_key: str,
    *,
    label: str | None = None,
    emoji: str | None = None,
    style: str = "biru",
    visibility: str = VIS_AUTO,
) -> dict | None:
    spec = SAFE_COMMANDS.get(str(command_key))
    if spec is None or len(menu["buttons"]) >= MAX_BUTTONS:
        return None
    item = {
        "id": _new_item_id(menu),
        "kind": KIND_COMMAND,
        "label": (label or spec["label"])[:80],
        "emoji": emoji or spec.get("emoji"),
        "style": style if style in BUTTON_STYLES else "biru",
        "command": str(command_key),
        "visibility": visibility if visibility in (VIS_AUTO, VIS_PUBLIK, VIS_EPHEMERAL) else VIS_AUTO,
    }
    menu["buttons"].append(item)
    return item


def add_flow_button(
    menu: dict,
    label: str,
    steps: list[dict],
    *,
    emoji: str | None = None,
    style: str = "biru",
) -> dict | None:
    """Tombol yang menjalankan alur aksi (lihat `flows.py`)."""
    if len(menu["buttons"]) >= MAX_BUTTONS:
        return None
    bersih = flows.sanitize_steps(steps)
    if not bersih:
        return None
    item = {
        "id": _new_item_id(menu),
        "kind": KIND_FLOW,
        "label": (str(label or "Aksi")[:80] or "Aksi"),
        "emoji": emoji or "⚡",
        "style": style if style in BUTTON_STYLES else "biru",
        "flow": bersih,
    }
    menu["buttons"].append(item)
    return item


def add_form_button(
    menu: dict,
    form: dict,
    *,
    label: str | None = None,
    emoji: str | None = None,
    style: str = "biru",
) -> dict | None:
    """Tombol yang membuka formulir (modal) buatan Admin — lihat `modal_forms.py`."""
    if len(menu["buttons"]) >= MAX_BUTTONS or not isinstance(form, dict):
        return None
    label = (str(label or "").strip() or str(form.get("name") or "Formulir"))[:80]
    item = {
        "id": _new_item_id(menu),
        "kind": KIND_FORM,
        "label": label,
        "emoji": emoji or "📝",
        "style": style if style in BUTTON_STYLES else "biru",
        "form_id": str(form.get("id")),
    }
    menu["buttons"].append(item)
    return item


def add_dropdown(
    menu: dict,
    placeholder: str,
    options: list[dict],
    *,
    exclusive: bool = False,
    group: str | None = None,
) -> dict | None:
    """Menambah dropdown. `options` = daftar `{role_id,label,emoji?}` (role)."""
    if len(menu["dropdowns"]) >= MAX_DROPDOWNS or not options:
        return None
    prepared: list[dict] = []
    for opt in options[:MAX_OPTIONS]:
        role_id = _to_int(opt.get("role_id"))
        if not role_id:
            continue
        prepared.append(
            {
                "id": _new_item_id(menu),
                "kind": KIND_ROLE,
                "role_id": role_id,
                "label": str(opt.get("label") or "Role")[:100],
                "emoji": opt.get("emoji") or None,
                "description": str(opt.get("description") or "")[:100] or None,
            }
        )
    if not prepared:
        return None
    dropdown = {
        "id": "d" + secrets.token_hex(3),
        "placeholder": (str(placeholder or "Pilih role…"))[:150],
        "exclusive": bool(exclusive),
        "group": (str(group)[:40] if group else "dropdown"),
        "options": prepared,
    }
    menu["dropdowns"].append(dropdown)
    return dropdown


def remove_item(menu: dict, ref: str) -> str | None:
    """Menghapus item tombol/opsi dropdown. Mengembalikan label yang dihapus."""
    clean = str(ref or "").strip()
    if not clean:
        return None

    # 1. Nomor urut (1..N) mengikuti urutan tampilan: tombol dulu, lalu opsi dropdown
    if clean.isdigit():
        index = int(clean) - 1
        if 0 <= index < len(menu["buttons"]):
            return menu["buttons"].pop(index).get("label")
        offset = index - len(menu["buttons"])
        for dropdown in menu["dropdowns"]:
            if 0 <= offset < len(dropdown["options"]):
                return dropdown["options"].pop(offset).get("label")
            offset -= len(dropdown["options"])
        return None

    # 2. ID item
    for item in list(menu["buttons"]):
        if item.get("id") == clean:
            menu["buttons"].remove(item)
            return item.get("label")
    for dropdown in menu["dropdowns"]:
        for option in list(dropdown["options"]):
            if option.get("id") == clean:
                dropdown["options"].remove(option)
                return option.get("label")
    # 3. Label
    lowered = clean.casefold()
    for item in list(menu["buttons"]):
        if str(item.get("label", "")).casefold() == lowered:
            menu["buttons"].remove(item)
            return item.get("label")
    for dropdown in menu["dropdowns"]:
        for option in list(dropdown["options"]):
            if str(option.get("label", "")).casefold() == lowered:
                dropdown["options"].remove(option)
                return option.get("label")
    return None


def handle_channel_delete(channel_id: int) -> int:
    """Melepas referensi channel yang sudah dihapus."""
    cid = _to_int(channel_id)
    changed = 0
    for bucket in menus.values():
        for menu in bucket.values():
            if menu.get("channel_id") == cid:
                menu["channel_id"] = None
                menu["message_id"] = None
                changed += 1
    return changed


def stats(guild_id: int) -> dict:
    rows = list_menus(guild_id)
    return {
        "menus": len(rows),
        "buttons": sum(len(m["buttons"]) for m in rows),
        "dropdowns": sum(len(m["dropdowns"]) for m in rows),
        "roles": sum(
            1
            for m in rows
            for item in m["buttons"]
            if item.get("kind") == KIND_ROLE
        ) + sum(
            len(d["options"]) for m in rows for d in m["dropdowns"]
        ),
    }


# ==============================================================================
# VALIDASI
# ==============================================================================
def check_role_usable(guild, role_id: int) -> tuple[bool, str]:
    """Memastikan role bisa diberikan bot (hierarki, @everyone, role terkelola)."""
    role = guild.get_role(_to_int(role_id)) if callable(getattr(guild, "get_role", None)) else None
    if role is None:
        return False, "Role sudah tidak ada di server ini."
    if getattr(role, "is_default", lambda: False)():
        return False, "Role `@everyone` tidak bisa dipakai untuk self role."
    if getattr(role, "managed", False):
        return False, "Role ini dikelola bot/integrasi lain sehingga tidak bisa diberikan manual."
    me = getattr(guild, "me", None)
    perms = getattr(me, "guild_permissions", None)
    if perms is not None and not getattr(perms, "manage_roles", False):
        return False, "Bot belum punya izin **Manage Roles**."
    top = getattr(me, "top_role", None) if me is not None else None
    if top is not None and role >= top:
        return False, "Posisi role itu **di atas role bot**. Pindahkan role bot lebih tinggi."
    return True, ""


def _cooldown_left(guild_id: int, user_id: int) -> float:
    key = f"{int(guild_id)}:{int(user_id)}"
    last = _role_cooldown.get(key)
    if not last:
        return 0.0
    left = ROLE_COOLDOWN_SEC - (_now() - float(last))
    return max(0.0, left)


def _mark_cooldown(guild_id: int, user_id: int) -> None:
    _role_cooldown[f"{int(guild_id)}:{int(user_id)}"] = _now()


# ==============================================================================
# EKSEKUSI: ROLE, LINK, COMMAND
# ==============================================================================
async def _reply(interaction: discord.Interaction, guild_id: int | None, kind: str,
                 title: str, message: str) -> None:
    embed = ui_theme.status_embed(guild_id, kind, title, message)
    try:
        if interaction.response.is_done():
            await ui_kit.send_status(interaction, embed=embed, follow=True, ephemeral=True)
        else:
            await ui_kit.send_status(interaction, embed=embed, ephemeral=True)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Balasan menu gagal dikirim: %s", exc)


async def toggle_role(
    interaction: discord.Interaction,
    role_id: int,
    *,
    exclusive_role_ids: list[int] | None = None,
) -> bool:
    """Member klik role: dapat bila belum punya, lepas bila sudah (toggle)."""
    guild = getattr(interaction, "guild", None)
    member = getattr(interaction, "user", None)
    if guild is None or member is None:
        return False

    ok, reason = check_role_usable(guild, role_id)
    if not ok:
        await _reply(interaction, guild.id, "error", "Role tidak bisa diberikan", reason)
        return False

    left = _cooldown_left(guild.id, member.id)
    if left > 0:
        await _reply(
            interaction,
            guild.id,
            "warn",
            "Sabar sedikit",
            f"Tunggu `{left:.0f}` detik lagi sebelum mengganti role lagi.",
        )
        return False

    role = guild.get_role(_to_int(role_id))
    has_role = role in getattr(member, "roles", [])
    try:
        if has_role:
            await member.remove_roles(role, reason="Self role (menu)")
        else:
            await member.add_roles(role, reason="Self role (menu)")
    except (discord.Forbidden, discord.HTTPException) as exc:
        await _reply(
            interaction,
            guild.id,
            "error",
            "Gagal mengubah role",
            f"Discord menolak permintaan: `{type(exc).__name__}`. "
            "Pastikan posisi role bot di atas role tersebut.",
        )
        return False

    _mark_cooldown(guild.id, member.id)

    # Mode eksklusif: lepas role lain di grup yang sama
    released: list[str] = []
    if exclusive_role_ids and not has_role:
        others = [
            guild.get_role(_to_int(rid))
            for rid in exclusive_role_ids
            if _to_int(rid) != _to_int(role_id)
        ]
        removable = [r for r in others if r is not None and r in getattr(member, "roles", [])]
        if removable:
            try:
                await member.remove_roles(*removable, reason="Self role eksklusif (menu)")
                released = [r.mention for r in removable]
            except (discord.Forbidden, discord.HTTPException):
                pass

    try:
        import audit_log

        await audit_log.log_event(
            interaction.client,
            guild,
            "role",
            "🎭 Self role dilepas" if has_role else "🎭 Self role diberikan",
            f"{getattr(member, 'mention', member)} — **{role.name}**",
        )
    except Exception:  # pragma: no cover - audit opsional
        pass

    extra = f"\nRole lain dilepas: {', '.join(released)}" if released else ""
    await _reply(
        interaction,
        guild.id,
        "ok",
        "Role dilepas" if has_role else "Role diberikan",
        f"**{role.name}** {'dilepas dari' if has_role else 'ditambahkan ke'} akunmu.{extra}\n"
        "-# Klik lagi untuk membatalkan pilihanmu.",
    )
    return True


# ------------------------------------------------------------------------------
# PENJALAN COMMAND (dengan kontrol visibilitas)
# ------------------------------------------------------------------------------
class _ForcedResponse:
    """Membungkus `interaction.response` & memaksa nilai `ephemeral`."""

    def __init__(self, response, ephemeral: bool):
        self._response = response
        self._ephemeral = ephemeral

    async def send_message(self, *args, **kwargs):
        kwargs["ephemeral"] = self._ephemeral
        return await self._response.send_message(*args, **kwargs)

    async def defer(self, *args, **kwargs):
        kwargs["ephemeral"] = self._ephemeral
        return await self._response.defer(*args, **kwargs)

    async def edit_message(self, *args, **kwargs):
        return await self._response.edit_message(*args, **kwargs)

    def is_done(self) -> bool:
        return bool(self._response.is_done())

    def __getattr__(self, item):
        return getattr(self._response, item)


class _ForcedFollowup:
    def __init__(self, followup, ephemeral: bool):
        self._followup = followup
        self._ephemeral = ephemeral

    async def send(self, *args, **kwargs):
        kwargs["ephemeral"] = self._ephemeral
        return await self._followup.send(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._followup, item)


class ForcedInteraction:
    """Proxy interaction: semua atribut asli diteruskan, hanya visibilitas dipaksa."""

    def __init__(self, interaction: discord.Interaction, ephemeral: bool):
        object.__setattr__(self, "_inner", interaction)
        object.__setattr__(self, "response", _ForcedResponse(interaction.response, ephemeral))
        object.__setattr__(self, "followup", _ForcedFollowup(interaction.followup, ephemeral))

    def __getattr__(self, item):
        return getattr(object.__getattribute__(self, "_inner"), item)

    def __setattr__(self, key, value):  # pragma: no cover - atribut proxy
        setattr(object.__getattribute__(self, "_inner"), key, value)


def resolve_command(bot, path: tuple[str, ...]):
    """Mengambil objek command dari tree bot berdasarkan jalur (`serverstats`, `lihat`)."""
    tree = getattr(bot, "tree", None)
    if tree is None or not path:
        return None
    command = tree.get_command(path[0])
    if command is None:
        return None
    for part in path[1:]:
        getter = getattr(command, "get_command", None)
        command = getter(part) if callable(getter) else None
        if command is None:
            return None
    return command


async def run_command_item(interaction: discord.Interaction, key: str, visibility: str) -> bool:
    """Menjalankan command whitelist atas nama pengklik."""
    spec = SAFE_COMMANDS.get(str(key))
    if spec is None:
        await _reply(
            interaction,
            getattr(getattr(interaction, "guild", None), "id", None),
            "error",
            "Command tidak diizinkan",
            "Tombol ini memakai command yang tidak ada di daftar aman.",
        )
        return False

    command = resolve_command(interaction.client, spec["path"])
    if command is None:
        await _reply(
            interaction,
            getattr(getattr(interaction, "guild", None), "id", None),
            "warn",
            "Command tidak tersedia",
            f"`{spec['desc']}` tidak aktif di server ini.",
        )
        return False

    target = interaction
    if visibility == VIS_PUBLIK:
        target = ForcedInteraction(interaction, ephemeral=False)
    elif visibility == VIS_EPHEMERAL:
        target = ForcedInteraction(interaction, ephemeral=True)

    try:
        await command.callback(target)
        return True
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Command menu %s gagal: %s", spec["desc"], exc)
        await _reply(
            interaction,
            getattr(getattr(interaction, "guild", None), "id", None),
            "error",
            "Menu gagal menjalankan command",
            f"`{spec['desc']}` mengalami kendala. Coba lagi sebentar lagi.",
        )
        return False


# ==============================================================================
# HANDLER INTERAKSI (callback tombol & dropdown)
# ==============================================================================
async def handle_button(interaction: discord.Interaction, menu_id: str, item_id: str) -> None:
    guild = getattr(interaction, "guild", None)
    if guild is None:
        return
    menu = get_menu(guild.id, menu_id)
    if menu is None:
        await _reply(interaction, guild.id, "warn", "Panel sudah tidak aktif",
                     "Admin dapat membuat panel baru lewat `/menu buat`.")
        return

    item = next((b for b in menu["buttons"] if b.get("id") == item_id), None)
    if item is None:
        await _reply(interaction, guild.id, "warn", "Tombol sudah dihapus",
                     "Panel ini baru saja diperbarui Admin.")
        return

    kind = item.get("kind")
    if kind == KIND_ROLE:
        await toggle_role(interaction, _to_int(item.get("role_id")))
        return
    if kind == KIND_COMMAND:
        await run_command_item(interaction, str(item.get("command")), str(item.get("visibility") or VIS_AUTO))
        return
    if kind == KIND_FLOW:
        await flows.run_flow(interaction, item.get("flow") or [], guild=guild, member=interaction.user)
        return
    if kind == KIND_FORM:
        await modal_forms.open_form_modal(
            interaction, modal_forms.get_form(guild.id, str(item.get("form_id") or ""))
        )
        return


async def handle_select(interaction: discord.Interaction, menu_id: str, dropdown_id: str) -> None:
    guild = getattr(interaction, "guild", None)
    if guild is None:
        return
    menu = get_menu(guild.id, menu_id)
    if menu is None:
        return
    dropdown = next((d for d in menu["dropdowns"] if d.get("id") == dropdown_id), None)
    if dropdown is None:
        return

    data = getattr(interaction, "data", None) or {}
    values = data.get("values") or []
    role_id = _to_int(values[0]) if values else 0
    if not role_id:
        return
    exclusive_ids = (
        role_ids_in_group(menu, str(dropdown.get("group") or ""))
        if dropdown.get("exclusive")
        else None
    )
    await toggle_role(interaction, role_id, exclusive_role_ids=exclusive_ids)


# ==============================================================================
# RENDER PANEL (Components V2)
# ==============================================================================
def _item_button(menu: dict, item: dict) -> ui.Button:
    kind = item.get("kind")
    if kind == KIND_LINK:
        return ui.Button(
            label=str(item.get("label"))[:80],
            emoji=item.get("emoji") or None,
            style=discord.ButtonStyle.link,
            url=str(item.get("url")),
        )
    button = ui.Button(
        label=str(item.get("label"))[:80],
        emoji=item.get("emoji") or None,
        style=BUTTON_STYLES.get(str(item.get("style") or "abu"), discord.ButtonStyle.secondary),
        custom_id=f"mb:{menu['id']}:{item['id']}",
    )

    async def callback(interaction: discord.Interaction) -> None:
        await handle_button(interaction, str(menu["id"]), str(item["id"]))

    button.callback = callback  # type: ignore[assignment]
    return button


def build_panel_items(
    menu: dict,
    *,
    banner_override: str | None = None,
    guild=None,
) -> list:
    """Menyusun daftar komponen (container + action rows) untuk sebuah menu.

    `guild` dipakai untuk mengisi variabel seperti `{server.members}` pada judul/deskripsi.
    """
    guild_id = _to_int(menu.get("guild_id")) or None
    container = ui.Container(accent_colour=ui_theme.accent_color(guild_id))

    judul = message_template.render(str(menu.get("title") or "Menu"), guild=guild)
    deskripsi = message_template.render(str(menu.get("description") or ""), guild=guild)
    head = f"# {judul}"
    if deskripsi:
        head += f"\n{deskripsi}"
    container.add_item(ui.TextDisplay(head[:4000]))

    banner = banner_override or menu.get("banner_url")
    if banner:
        container.add_item(ui.MediaGallery(ui.MediaGalleryItem(media=banner)))

    role_lines = [
        f"• {item.get('emoji') or '🔹'} **{item.get('label')}** — klik untuk ambil/lepas"
        for item in menu["buttons"]
        if item.get("kind") == KIND_ROLE
    ]
    if role_lines:
        container.add_item(ui.TextDisplay("\n".join(role_lines)[:4000]))

    items: list = [container]

    buttons = list(menu["buttons"])
    for start in range(0, len(buttons), ui_kit.MAX_BUTTONS_PER_ROW):
        chunk = buttons[start:start + ui_kit.MAX_BUTTONS_PER_ROW]
        items.append(ui.ActionRow(*[_item_button(menu, item) for item in chunk]))

    for dropdown in menu["dropdowns"]:
        options = [
            discord.SelectOption(
                label=str(opt.get("label"))[:100],
                value=str(opt.get("role_id")),
                emoji=opt.get("emoji") or None,
                description=(str(opt.get("description"))[:100] if opt.get("description") else None),
            )
            for opt in dropdown["options"][:ui_kit.MAX_SELECT_OPTIONS]
        ]
        if not options:
            continue
        select = ui.Select(
            custom_id=f"mb:{menu['id']}:{dropdown['id']}",
            placeholder=str(dropdown.get("placeholder") or "Pilih role…")[:150],
            options=options,
            max_values=1,
        )

        async def callback(interaction: discord.Interaction, dropdown_id: str = str(dropdown["id"])) -> None:
            await handle_select(interaction, str(menu["id"]), dropdown_id)

        select.callback = callback  # type: ignore[assignment]
        items.append(ui.ActionRow(select))

    return items


def build_view(menu: dict, *, banner_override: str | None = None, guild=None) -> ui.LayoutView:
    """`LayoutView` persisten (timeout=None) untuk sebuah menu."""
    view = ui.LayoutView(timeout=None)
    for item in build_panel_items(menu, banner_override=banner_override, guild=guild):
        view.add_item(item)
    return view


def build_fallback_embed(menu: dict) -> discord.Embed:
    """Embed klasik bila klien menolak Components V2."""
    guild_id = _to_int(menu.get("guild_id")) or None
    lines = []
    for item in menu["buttons"]:
        if item.get("kind") == KIND_LINK:
            lines.append(f"• [{item.get('label')}]({item.get('url')})")
        else:
            lines.append(f"• {item.get('emoji') or '🔹'} **{item.get('label')}**")
    for dropdown in menu["dropdowns"]:
        for option in dropdown["options"]:
            lines.append(f"• {option.get('emoji') or '🔹'} **{option.get('label')}**")
    return ui_kit.fallback_embed(
        guild_id,
        menu.get("title") or "Menu",
        (menu.get("description") or "") + ("\n\n" + "\n".join(lines) if lines else ""),
        footer="Panel interaktif tidak didukung klien ini — buka Discord terbaru.",
    )


def is_forum_channel(channel) -> bool:
    """Channel forum (butuh `create_thread`, bukan `send`)."""
    forum_cls = getattr(discord, "ForumChannel", None)
    return bool(forum_cls is not None and isinstance(channel, forum_cls))


async def send_panel(
    bot,
    menu: dict,
    channel,
    *,
    banner_file: discord.File | None = None,
    banner_ref: str | None = None,
) -> discord.Message | None:
    """Mengirim panel menu ke channel, thread, atau forum & menyimpan `message_id`."""
    guild = getattr(channel, "guild", None)
    view = build_view(menu, banner_override=banner_ref, guild=guild)
    if is_forum_channel(channel):
        # Forum: panel menjadi post baru (judul panel = nama post)
        nama_post = message_template.render(str(menu.get("title") or "Panel"), guild=guild)[:100]
        try:
            kwargs: dict = {"name": nama_post or "Panel", "view": view}
            if banner_file is not None:
                kwargs["file"] = banner_file
            hasil = await channel.create_thread(**kwargs)
        except (discord.HTTPException, TypeError, ValueError) as exc:
            logger.warning("Panel V2 ke forum ditolak (%s) — memakai embed klasik.", exc)
            try:
                hasil = await channel.create_thread(
                    name=nama_post or "Panel",
                    content=(menu.get("description") or "Panel")[:2000],
                    embed=build_fallback_embed(menu),
                )
            except (discord.Forbidden, discord.HTTPException):
                return None
        thread = getattr(hasil, "thread", None)
        message = getattr(hasil, "message", None)
        menu["channel_id"] = getattr(thread, "id", None) or getattr(channel, "id", None)
        menu["message_id"] = getattr(message, "id", None)
        try:
            bot.add_view(view, message_id=menu["message_id"])
        except Exception as exc:  # pragma: no cover - depends on client state
            logger.debug("Pendaftaran view forum dilewati: %s", exc)
        return message

    try:
        if banner_file is not None:
            message = await channel.send(view=view, file=banner_file)
        else:
            message = await channel.send(view=view)
    except (discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Panel V2 menu ditolak (%s) — memakai embed klasik.", exc)
        try:
            message = await channel.send(embed=build_fallback_embed(menu))
        except (discord.Forbidden, discord.HTTPException):
            return None

    menu["channel_id"] = getattr(channel, "id", None)
    menu["message_id"] = getattr(message, "id", None)

    attachments = getattr(message, "attachments", None) or []
    if banner_file is not None and attachments:
        try:
            menu["banner_url"] = str(attachments[0].url)[:400]
        except Exception:  # pragma: no cover
            pass

    try:
        bot.add_view(view, message_id=menu["message_id"])
    except Exception as exc:  # pragma: no cover - depends on client state
        logger.debug("Pendaftaran view menu dilewati: %s", exc)
    return message


async def refresh_panel(bot, menu: dict) -> bool:
    """Menyegarkan pesan panel yang sudah terkirim setelah item ditambah/dihapus."""
    guild = bot.get_guild(_to_int(menu.get("guild_id"))) if callable(getattr(bot, "get_guild", None)) else None
    if guild is None or not menu.get("message_id"):
        return False
    channel = None
    getter = getattr(bot, "get_channel", None)
    if callable(getter) and menu.get("channel_id"):
        channel = getter(int(menu["channel_id"]))
    if channel is None and menu.get("channel_id"):
        # thread/forum post biasanya tidak ada di cache
        fetcher = getattr(bot, "fetch_channel", None)
        if callable(fetcher):
            try:
                channel = await fetcher(int(menu["channel_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                channel = None
    if channel is None:
        return False
    try:
        message = await channel.fetch_message(int(menu["message_id"]))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
        return False

    view = build_view(menu, guild=guild)
    try:
        await message.edit(view=view)
    except (discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Refresh panel menu gagal (%s) — memakai embed klasik.", exc)
        try:
            await message.edit(view=None, embed=build_fallback_embed(menu))
        except (discord.Forbidden, discord.HTTPException):
            return False
    try:
        bot.add_view(view, message_id=int(menu["message_id"]))
    except Exception:  # pragma: no cover
        pass
    return True


def register_menus(bot) -> int:
    """Memasang kembali semua panel persisten saat bot siap (tahan restart)."""
    total = 0
    for bucket in menus.values():
        for menu in bucket.values():
            if not menu.get("buttons") and not menu.get("dropdowns"):
                continue
            try:
                guild = None
                getter = getattr(bot, "get_guild", None)
                if callable(getter) and menu.get("guild_id"):
                    guild = getter(int(menu["guild_id"]))
                view = build_view(menu, guild=guild)
                if menu.get("message_id"):
                    bot.add_view(view, message_id=int(menu["message_id"]))
                else:
                    bot.add_view(view)
                total += 1
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.debug("Menu %s gagal didaftarkan: %s", menu.get("id"), exc)
    return total


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def _menu_payload(menu: dict) -> dict:
    return {
        "id": menu.get("id"),
        "channel_id": menu.get("channel_id"),
        "message_id": menu.get("message_id"),
        "title": menu.get("title"),
        "description": menu.get("description"),
        "banner_url": menu.get("banner_url"),
        "kind": menu.get("kind", MENU_KIND_MENU),
        "buttons": menu.get("buttons", []),
        "dropdowns": menu.get("dropdowns", []),
        "created_at": menu.get("created_at"),
    }


def _sanitize_buttons(buttons) -> list[dict]:
    """Tombol dari disk: alur aksi divalidasi ulang (jangan percaya JSON)."""
    hasil: list[dict] = []
    for tombol in buttons or []:
        if not isinstance(tombol, dict):
            continue
        if tombol.get("kind") == KIND_FLOW:
            langkah = flows.sanitize_steps(tombol.get("flow"))
            if not langkah:
                continue
            tombol = {**tombol, "flow": langkah}
        if tombol.get("kind") == KIND_FORM and not str(tombol.get("form_id") or "").strip():
            continue  # tombol formulir tanpa rujukan tidak bisa dijalankan
        hasil.append(tombol)
    return hasil


def load_menus_from_disk() -> int:
    """Memuat panel dari `data/menus.json`."""
    menus.clear()
    _role_cooldown.clear()

    path = Path(MENU_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    total = 0
    for gid_str, bucket in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(bucket, dict):
            continue
        for menu_id, data in bucket.items():
            if not isinstance(data, dict):
                continue
            menus.setdefault(gid, {})[str(menu_id)] = {
                "id": str(data.get("id") or menu_id),
                "guild_id": gid,
                "channel_id": _to_int(data.get("channel_id")) or None,
                "message_id": _to_int(data.get("message_id")) or None,
                "title": str(data.get("title") or "Menu")[:MAX_TITLE],
                "description": str(data.get("description") or "")[:MAX_DESCRIPTION],
                "banner_url": (str(data.get("banner_url"))[:400] if data.get("banner_url") else None),
                "kind": str(data.get("kind") or MENU_KIND_MENU),
                "buttons": _sanitize_buttons(data.get("buttons")),
                "dropdowns": [d for d in (data.get("dropdowns") or []) if isinstance(d, dict)],
                "created_at": float(data.get("created_at") or 0),
            }
            total += 1
    return total


async def save_menus_to_disk() -> None:
    """Menyimpan semua panel ke `data/menus.json` (atomik)."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {
                    str(gid): {mid: _menu_payload(menu) for mid, menu in bucket.items()}
                    for gid, bucket in menus.items()
                    if bucket
                }
            }
            tmp_file = Path(str(MENU_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, MENU_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan menus.json: %s", exc)


def cleanup_menu_runtime() -> int:
    """Membersihkan catatan cooldown role yang sudah kedaluwarsa."""
    now = _now()
    stale = [key for key, ts in _role_cooldown.items() if now - float(ts) > 300]
    for key in stale:
        _role_cooldown.pop(key, None)
    return len(stale)


def banner_file_from_attachment(attachment, data: bytes) -> tuple[discord.File | None, str | None]:
    """Menyiapkan `discord.File` + referensi `attachment://` untuk banner unggahan."""
    filename = str(getattr(attachment, "filename", "banner.png") or "banner.png")
    ext = Path(filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        ext = ".png"
    safe_name = f"banner{ext}"
    return discord.File(io.BytesIO(data), filename=safe_name), f"attachment://{safe_name}"


def is_image_attachment(attachment) -> bool:
    """Cek apakah lampiran berupa gambar & ukurannya wajar."""
    content_type = str(getattr(attachment, "content_type", "") or "")
    filename = str(getattr(attachment, "filename", "") or "").lower()
    size = _to_int(getattr(attachment, "size", 0))
    looks_image = content_type.startswith("image/") or filename.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif")
    )
    return looks_image and 0 < size <= MAX_BANNER_BYTES
