"""Voice linking — role + channel teks privat selama member berada di voice.

Ala bot besar (Arclo): member yang masuk voice channel otomatis mendapat **role khusus**
dan bisa membaca/menulis di **channel teks privat** milik voice channel itu. Saat keluar
voice, aksesnya dicabut, dan channel privatnya dihapus bila sudah kosong.

Modul ini **0 kuota AI**, tanpa proses latar baru, dan **tidak menyimpan isi pesan** apa pun —
`data/voice_link.json` hanya berisi setelan server dan pasangan
`channel voice ↔ channel teks`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

from config import VOICE_LINK_FILE

logger = logging.getLogger("gemini_bot.voice_link")

MAX_LINK_PER_GUILD = 40        # maksimum channel teks privat per server
NAMA_CHANNEL_MAKS = 90         # batas aman nama channel Discord (100)
PREFIX_CHANNEL = "⌨️"

# guild_id -> {enabled, role_id, channel_privat, hapus_kosong, kategori_id}
link_config: dict[int, dict] = {}
# guild_id -> {voice_channel_id: {"text_id": int, "dibuat": ts}}
link_channels: dict[int, dict[int, dict]] = {}
# guild_id -> {user_id, ...} yang role-nya KITA berikan (supaya tidak mencabut role asli)
link_members: dict[int, set[int]] = {}


# ==============================================================================
# SETELAN
# ==============================================================================
def default_config() -> dict:
    return {
        "enabled": False,
        "role_id": None,
        "channel_privat": True,
        "hapus_kosong": True,
        "kategori_id": None,
    }


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def peek_config(guild_id: int) -> dict:
    """Setelan tanpa membuat entri baru (aman untuk dashboard/read-only)."""
    return {**default_config(), **dict(link_config.get(int(guild_id)) or {})}


def get_config(guild_id: int) -> dict:
    return link_config.setdefault(int(guild_id), default_config())


def set_config(
    guild_id: int,
    *,
    enabled: bool | None = None,
    role_id: int | None = None,
    channel_privat: bool | None = None,
    hapus_kosong: bool | None = None,
    kategori_id: int | None = None,
) -> dict:
    """Ubah setelan voice linking. Nilai `None` = biarkan seperti sebelumnya."""
    cfg = get_config(guild_id)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if role_id is not None:
        cfg["role_id"] = _to_int(role_id) or None
    if channel_privat is not None:
        cfg["channel_privat"] = bool(channel_privat)
    if hapus_kosong is not None:
        cfg["hapus_kosong"] = bool(hapus_kosong)
    if kategori_id is not None:
        cfg["kategori_id"] = _to_int(kategori_id) or None
    return cfg


def aktif(guild_id: int) -> bool:
    """Aktif bila dinyalakan **dan** punya minimal satu efek (role atau channel privat)."""
    cfg = peek_config(guild_id)
    return bool(cfg["enabled"] and (cfg["role_id"] or cfg["channel_privat"]))


# ==============================================================================
# ANGGOTA PENERIMA ROLE
# ==============================================================================
def tandai_role(guild_id: int, user_id: int) -> bool:
    """Catat bahwa role diberikan oleh bot. `False` bila sudah tercatat."""
    kumpulan = link_members.setdefault(int(guild_id), set())
    uid = int(user_id)
    if uid in kumpulan:
        return False
    kumpulan.add(uid)
    return True


def lepas_role(guild_id: int, user_id: int) -> bool:
    kumpulan = link_members.get(int(guild_id)) or set()
    uid = int(user_id)
    if uid not in kumpulan:
        return False
    kumpulan.discard(uid)
    return True


def anggota_berole(guild_id: int) -> set[int]:
    return set(link_members.get(int(guild_id)) or set())


# ==============================================================================
# CHANNEL PRIVAT
# ==============================================================================
_POLA_NAMA = re.compile(r"[^a-z0-9\-_ ]+")


def nama_channel(nama_voice: str) -> str:
    """Nama channel teks privat dari nama voice channel (`⌨️-<nama>`)."""
    dasar = _POLA_NAMA.sub("", str(nama_voice or "").lower()).strip()
    dasar = re.sub(r"[\s_]+", "-", dasar).strip("-")
    dasar = dasar or "voice"
    batas = NAMA_CHANNEL_MAKS - len(PREFIX_CHANNEL) - 1
    return f"{PREFIX_CHANNEL}-{dasar[:batas]}"


def link_untuk(guild_id: int, voice_id: int) -> int:
    data = (link_channels.get(int(guild_id)) or {}).get(int(voice_id)) or {}
    return _to_int(data.get("text_id"))


def catat_link(guild_id: int, voice_id: int, text_id: int) -> bool:
    """Simpan pasangan voice ↔ teks. `False` bila batas per server tercapai."""
    gid, vid, tid = int(guild_id), int(voice_id), int(text_id)
    kumpulan = link_channels.setdefault(gid, {})
    if vid not in kumpulan and len(kumpulan) >= MAX_LINK_PER_GUILD:
        return False
    kumpulan[vid] = {"text_id": tid, "dibuat": int(time.time())}
    return True


def hapus_link(guild_id: int, voice_id: int) -> bool:
    kumpulan = link_channels.get(int(guild_id)) or {}
    return kumpulan.pop(int(voice_id), None) is not None


def daftar_link(guild_id: int) -> list[dict]:
    """Daftar channel privat milik server (urut dari yang terlama)."""
    kumpulan = link_channels.get(int(guild_id)) or {}
    return [
        {"voice_id": vid, "text_id": _to_int(data.get("text_id")), "dibuat": data.get("dibuat", 0)}
        for vid, data in sorted(kumpulan.items(), key=lambda item: item[1].get("dibuat", 0))
    ]


def statistik(guild_id: int) -> dict:
    cfg = peek_config(guild_id)
    return {
        **cfg,
        "aktif": aktif(guild_id),
        "jumlah_channel": len(link_channels.get(int(guild_id)) or {}),
        "jumlah_berole": len(link_members.get(int(guild_id)) or set()),
        "maks_channel": MAX_LINK_PER_GUILD,
    }


# ==============================================================================
# ALUR EVENT
# ==============================================================================
async def handle_voice_state(member, before, after) -> list[str]:
    """Beri/cabut role & akses channel privat saat member masuk/keluar voice.

    Mengembalikan daftar aksi yang berhasil (dipakai tes & log); tidak pernah melempar
    exception ke listener utama.
    """
    guild = getattr(member, "guild", None)
    if guild is None:
        return []
    gid = int(getattr(guild, "id", 0) or 0)
    if not aktif(gid):
        return []

    cfg = peek_config(gid)
    masuk = getattr(after, "channel", None)
    keluar = getattr(before, "channel", None)
    pindah = masuk is not None and getattr(keluar, "id", None) != getattr(masuk, "id", None)
    aksi: list[str] = []

    if pindah and not getattr(member, "bot", False):
        if cfg["role_id"]:
            aksi.extend(await _beri_role(guild, member, cfg))
        if cfg["channel_privat"]:
            aksi.extend(await _sambungkan_channel(guild, member, masuk, cfg))

    if keluar is not None and getattr(keluar, "id", None) != getattr(masuk, "id", None):
        if cfg["role_id"] and masuk is None:
            aksi.extend(await _cabut_role(guild, member, cfg))
        if cfg["channel_privat"]:
            aksi.extend(await _lepaskan_channel(guild, member, keluar, cfg))

    if aksi:
        await save_voice_link_to_disk()
    return aksi


async def _beri_role(guild, member, cfg: dict) -> list[str]:
    role = None
    get_role = getattr(guild, "get_role", None)
    if callable(get_role):
        role = get_role(_to_int(cfg.get("role_id")))
    if role is None or getattr(member, "bot", False):
        return []
    dimiliki = {getattr(r, "id", 0) for r in (getattr(member, "roles", None) or [])}
    if _to_int(cfg.get("role_id")) in dimiliki:
        return []
    try:
        await member.add_roles(role, reason="Voice link: masuk voice")
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Voice link gagal memberi role: %s", exc)
        return []
    tandai_role(int(guild.id), int(member.id))
    return ["role_diberi"]


async def _cabut_role(guild, member, cfg: dict) -> list[str]:
    if not lepas_role(int(guild.id), int(member.id)):
        return []  # role-nya bukan dari kita (atau sudah dicabut manual)
    role = None
    get_role = getattr(guild, "get_role", None)
    if callable(get_role):
        role = get_role(_to_int(cfg.get("role_id")))
    if role is None:
        return []
    try:
        await member.remove_roles(role, reason="Voice link: keluar voice")
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Voice link gagal mencabut role: %s", exc)
        return []
    return ["role_dicabut"]


async def _pastikan_channel(guild, voice_channel, cfg: dict) -> tuple[int, str]:
    """Ambil/buat channel teks privat untuk satu voice channel → `(text_id, aksi)`."""
    vid = int(getattr(voice_channel, "id", 0) or 0)
    ada = link_untuk(int(guild.id), vid)
    teks = getattr(guild, "get_channel", lambda _cid: None)(ada) if ada else None
    if teks is not None:
        return ada, ""

    if len(link_channels.get(int(guild.id)) or {}) >= MAX_LINK_PER_GUILD:
        return 0, "batas_channel"

    nama = nama_channel(getattr(voice_channel, "name", ""))
    kategori = None
    get_channel = getattr(guild, "get_channel", None)
    if cfg.get("kategori_id") and callable(get_channel):
        kategori = get_channel(_to_int(cfg.get("kategori_id")))
    if kategori is None:
        kategori = getattr(voice_channel, "category", None)

    try:
        baru = await guild.create_text_channel(
            nama,
            category=kategori,
            reason="Voice link: channel privat untuk voice",
            overwrites=None,
        )
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Voice link gagal membuat channel privat: %s", exc)
        return 0, ""

    text_id = int(getattr(baru, "id", 0) or 0)
    if not text_id or not catat_link(int(guild.id), vid, text_id):
        return 0, ""
    try:  # sembunyikan dari semua orang, lalu izinkan yang di voice
        await baru.set_permissions(guild.default_role, view_channel=False)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Voice link gagal menutup channel: %s", exc)
    return text_id, "channel_dibuat"


async def _sambungkan_channel(guild, member, voice_channel, cfg: dict) -> list[str]:
    text_id, aksi = await _pastikan_channel(guild, voice_channel, cfg)
    if not text_id:
        return [aksi] if aksi else []
    teks = getattr(guild, "get_channel", lambda _cid: None)(text_id)
    if teks is None:
        return [aksi] if aksi else []
    try:
        await teks.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Voice link gagal membuka akses member: %s", exc)
        return [aksi] if aksi else []
    return [aksi, "akses_diberi"] if aksi else ["akses_diberi"]


async def _lepaskan_channel(guild, member, voice_channel, cfg: dict) -> list[str]:
    vid = int(getattr(voice_channel, "id", 0) or 0)
    text_id = link_untuk(int(guild.id), vid)
    if not text_id:
        return []
    teks = getattr(guild, "get_channel", lambda _cid: None)(text_id)
    aksi: list[str] = []
    if teks is not None:
        try:
            await teks.set_permissions(member, overwrite=None)
            aksi.append("akses_dicabut")
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.debug("Voice link gagal mencabut akses member: %s", exc)

    sisa = [m for m in getattr(voice_channel, "members", None) or [] if not getattr(m, "bot", False)]
    sisa = [m for m in sisa if getattr(m, "id", 0) != getattr(member, "id", 0)]
    if not sisa and cfg.get("hapus_kosong", True):
        if teks is not None:
            try:
                await teks.delete(reason="Voice link: voice kosong")
            except Exception as exc:  # pragma: no cover - jaring aman
                logger.debug("Voice link gagal menghapus channel privat: %s", exc)
                return aksi
        hapus_link(int(guild.id), vid)
        aksi.append("channel_dihapus")
    return aksi


# ==============================================================================
# PEMBERSIHAN & PENYIMPANAN
# ==============================================================================
def reset_runtime_state() -> None:
    """Kosongkan seluruh state di memori (dipakai tes)."""
    link_config.clear()
    link_channels.clear()
    link_members.clear()


def cleanup_voice_link_runtime(limit: int = 500) -> int:
    """Buang server tanpa setelan aktif & tanpa channel tercatat."""
    dibuang = 0
    for gid in list(link_config):
        if dibuang >= limit:
            break
        if not link_channels.get(gid) and not link_members.get(gid) and not peek_config(gid)["enabled"]:
            link_config.pop(gid, None)
            dibuang += 1
    for gid in list(link_channels):
        if not link_channels[gid]:
            link_channels.pop(gid, None)
    for gid in list(link_members):
        if not link_members[gid]:
            link_members.pop(gid, None)
    return dibuang


def load_voice_link_from_disk() -> tuple[int, int]:
    """Muat setelan + pasangan channel. `(jumlah server, jumlah channel)`. Gagal = (0, 0)."""
    try:
        raw = json.loads(VOICE_LINK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (0, 0)
    if not isinstance(raw, dict):
        return (0, 0)

    server = 0
    total = 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        if not str(gid_str).isdigit() or not isinstance(data, dict):
            continue
        gid = int(gid_str)
        cfg = default_config()
        sumber = data.get("config") or {}
        cfg["enabled"] = bool(sumber.get("enabled"))
        cfg["role_id"] = _to_int(sumber.get("role_id")) or None
        cfg["channel_privat"] = bool(sumber.get("channel_privat", True))
        cfg["hapus_kosong"] = bool(sumber.get("hapus_kosong", True))
        cfg["kategori_id"] = _to_int(sumber.get("kategori_id")) or None
        link_config[gid] = cfg

        for vid_str, item in (data.get("channels") or {}).items():
            if not str(vid_str).isdigit() or not isinstance(item, dict):
                continue
            text_id = _to_int(item.get("text_id"))
            if not text_id:
                continue
            link_channels.setdefault(gid, {})[int(vid_str)] = {
                "text_id": text_id,
                "dibuat": _to_int(item.get("dibuat")),
            }
            total += 1
        server += 1
    return (server, total)


async def save_voice_link_to_disk() -> None:
    """Tulis state ke `data/voice_link.json` (atomik, menunggu I/O tanpa memblokir bot)."""
    import asyncio

    data = {
        "guilds": {
            str(gid): {
                "config": cfg,
                "channels": {str(vid): item for vid, item in (link_channels.get(gid) or {}).items()},
            }
            for gid, cfg in link_config.items()
            if link_channels.get(gid) or cfg.get("enabled")
        }
    }
    teks = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def _tulis() -> None:
        try:
            VOICE_LINK_FILE.parent.mkdir(parents=True, exist_ok=True)
            sementara = VOICE_LINK_FILE.with_suffix(".tmp")
            sementara.write_text(teks, encoding="utf-8")
            os.replace(sementara, VOICE_LINK_FILE)
        except OSError:  # pragma: no cover - disk penuh/izin
            logger.exception("Gagal menyimpan voice link")

    await asyncio.to_thread(_tulis)


__all__ = [
    "MAX_LINK_PER_GUILD",
    "aktif",
    "anggota_berole",
    "catat_link",
    "cleanup_voice_link_runtime",
    "daftar_link",
    "default_config",
    "get_config",
    "handle_voice_state",
    "hapus_link",
    "lepas_role",
    "link_untuk",
    "load_voice_link_from_disk",
    "nama_channel",
    "peek_config",
    "reset_runtime_state",
    "save_voice_link_to_disk",
    "set_config",
    "statistik",
    "tandai_role",
]
