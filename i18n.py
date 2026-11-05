"""i18n inti — Bahasa Indonesia & English untuk **teks kerangka** bot (**0 kuota AI**).

Yang diterjemahkan adalah teks yang dipakai berulang di seluruh fitur:

- tombol & kartu dialog konfirmasi (`Ya, lanjutkan` / `Batal`, dll.)
- kata status umum (`aktif`, `nonaktif`, `tersimpan`, `dibatalkan`)
- pesan izin (`Butuh izin Admin`)
- command `/bahasa` itu sendiri

Teks panjang penjelasan fitur (README/`/bantuan`) tetap Bahasa Indonesia agar konsisten
dengan dokumentasi. Semua diterjemahkan **lokal**, tanpa memanggil AI sama sekali.

Pengaturan bahasa bersifat **per server** (bukan per member) dan disimpan di
`data/i18n.json` — berkas kecil agar RAM Free Tier tetap aman.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from config import DATA_DIR, I18N_FILE

logger = logging.getLogger("gemini_bot.i18n")

_lock = asyncio.Lock()

DEFAULT_LANG = "id"

LANG_NAMES: dict[str, str] = {
    "id": "🇮🇩 Bahasa Indonesia",
    "en": "🇬🇧 English",
}

# Katalog teks inti. Kunci baru boleh ditambahkan; `id` wajib selalu ada.
TEXTS: dict[str, dict[str, str]] = {
    # --- Dialog konfirmasi ---
    "confirm.yes": {"id": "Ya, lanjutkan", "en": "Yes, continue"},
    "confirm.cancel": {"id": "Batal", "en": "Cancel"},
    "confirm.confirmed": {"id": "Dikonfirmasi", "en": "Confirmed"},
    "confirm.confirmed_detail": {"id": "Aksi dijalankan.", "en": "Action executed."},
    "confirm.cancelled": {"id": "Dibatalkan", "en": "Cancelled"},
    "confirm.cancelled_detail": {"id": "Tidak ada perubahan.", "en": "No changes were made."},
    "confirm.other_user": {
        "id": "⚠️ Dialog ini milik orang lain. Jalankan command sendiri untuk konfirmasi.",
        "en": "⚠️ This dialog belongs to someone else. Run the command yourself to confirm.",
    },
    # --- Status umum ---
    "status.on": {"id": "aktif", "en": "enabled"},
    "status.off": {"id": "nonaktif", "en": "disabled"},
    "status.saved": {"id": "Pengaturan disimpan", "en": "Settings saved"},
    "status.done": {"id": "Selesai", "en": "Done"},
    "status.info": {"id": "Informasi", "en": "Information"},
    "status.cancelled": {"id": "Dibatalkan", "en": "Cancelled"},
    # --- Izin & kesalahan umum ---
    "perm.admin": {
        "id": "Butuh izin Admin",
        "en": "Admin permission required",
    },
    "perm.admin_detail": {
        "id": "Hanya Admin / *Manage Server* yang bisa memakai command ini.",
        "en": "Only Admins / members with *Manage Server* can use this command.",
    },
    "error.guild_only": {
        "id": "Command ini hanya bisa dipakai di dalam server.",
        "en": "This command can only be used inside a server.",
    },
    "error.generic": {
        "id": "Terjadi kesalahan saat menjalankan aksi.",
        "en": "Something went wrong while running the action.",
    },
    # --- /bahasa ---
    "lang.current": {
        "id": "Bahasa server ini: **{lang}**",
        "en": "Server language: **{lang}**",
    },
    "lang.set": {
        "id": "Bahasa server diganti ke **{lang}**. Teks kerangka bot sekarang memakai bahasa itu.",
        "en": "Server language changed to **{lang}**. Framework texts now use that language.",
    },
    "lang.invalid": {
        "id": "Kode bahasa `{code}` tidak dikenal. Pilih: {options}.",
        "en": "Unknown language code `{code}`. Choose one of: {options}.",
    },
    "lang.only_framework": {
        "id": "Catatan: yang diterjemahkan adalah teks kerangka (tombol, status, izin, `/bahasa`). "
        "Penjelasan panjang fitur tetap Bahasa Indonesia.",
        "en": "Note: only framework texts are translated (buttons, status, permissions, `/bahasa`). "
        "Long feature descriptions stay in Indonesian.",
    },
}

# guild_id -> kode bahasa
guild_lang: dict[int, str] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def available_langs() -> dict[str, str]:
    return dict(LANG_NAMES)


def normalize_lang(code: str | None) -> str | None:
    """Menerima `id`, `en`, `id-ID`, `en-US`, `indonesia`, `english`."""
    raw = str(code or "").strip().lower().replace("_", "-")
    if not raw:
        return None
    base = raw.split("-", 1)[0]
    if base in LANG_NAMES:
        return base
    aliases = {
        "indonesia": "id",
        "ind": "id",
        "english": "en",
        "eng": "en",
        "us": "en",
        "uk": "en",
    }
    return aliases.get(raw) or aliases.get(base)


def get_lang(guild_id: int | None) -> str:
    """Bahasa aktif sebuah server (default `id`)."""
    if guild_id is None:
        return DEFAULT_LANG
    return guild_lang.get(_to_int(guild_id), DEFAULT_LANG)


def set_lang(guild_id: int, code: str) -> tuple[bool, str]:
    """Mengubah bahasa server. Mengembalikan `(ok, bahasa_hasil)`."""
    normalized = normalize_lang(code)
    if normalized is None:
        return False, get_lang(guild_id)
    gid = _to_int(guild_id)
    if gid <= 0:
        return False, DEFAULT_LANG
    guild_lang[gid] = normalized
    return True, normalized


def t(key: str, guild_id: int | None = None, **kwargs) -> str:
    """Menerjemahkan kunci teks inti. Jatuh ke `id` lalu ke kunci bila tidak ada."""
    lang = get_lang(guild_id)
    entry = TEXTS.get(key) or {}
    template = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):  # pragma: no cover - template salah
        return template


def lang_label(code: str) -> str:
    return LANG_NAMES.get(str(code or ""), str(code or "?"))


def describe_lang(guild_id: int | None) -> str:
    """Ringkasan bahasa aktif dalam bahasa itu sendiri."""
    return lang_label(get_lang(guild_id))


def translate_all(key: str) -> dict[str, str]:
    """Semua varian bahasa untuk satu kunci (berguna untuk tes/dokumentasi)."""
    return dict(TEXTS.get(key) or {})


# ==============================================================================
# SIMPAN / MUAT
# ==============================================================================
def load_lang_from_disk() -> int:
    guild_lang.clear()
    path = Path(I18N_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, code in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        normalized = normalize_lang(str(code))
        if gid and normalized:
            guild_lang[gid] = normalized
    return len(guild_lang)


async def save_lang_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(gid): code for gid, code in guild_lang.items() if code != DEFAULT_LANG}}
            tmp_file = Path(str(I18N_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, I18N_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan i18n.json: %s", exc)


def cleanup_i18n_runtime() -> int:
    """Membuang pengaturan bahasa yang sama dengan default (jaga data tetap kecil)."""
    removed = 0
    for gid, code in list(guild_lang.items()):
        if code == DEFAULT_LANG:
            guild_lang.pop(gid, None)
            removed += 1
    return removed
