"""Mesin variabel pesan (*template*) — `{member.name}`, `{server.members}`, `{now_relative}`.

Dipakai `/embed`, `/pengumuman`, `/menu`, dan pesan alur tombol supaya admin tidak perlu
mengetik data yang berubah-ubah secara manual.

Sintaks: `{kelompok.token}`, contoh:

    Halo {member.mention}, kamu member ke-{server.members} di {server.name}!

Aturan:
- Token yang **dikenal** tetapi datanya tidak tersedia (mis. `{member.name}` di pengumuman
  terjadwal yang tidak punya konteks member) diganti **string kosong** — jangan sampai
  teks mentah `{member.name}` bocor ke channel.
- Token yang **tidak dikenal** dibiarkan apa adanya supaya salah ketik kelihatan, dan bisa
  dideteksi lewat :func:`unknown_tokens` saat admin membuat pesan.
- Alias lama `{user}`, `{name}`, `{guild}` tetap didukung agar pesan boost yang sudah ada
  tidak berubah perilakunya.

Modul ini murni (tanpa I/O, tanpa state) sehingga mudah diuji.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

TOKEN_RE = re.compile(r"\{([A-Za-z_]+(?:\.[A-Za-z_]+)*)\}")

MAX_RENDER_LENGTH = 4000


@dataclass
class Context:
    """Konteks data untuk merender variabel."""

    member: Any = None
    guild: Any = None
    channel: Any = None
    now: float = field(default_factory=time.time)


# ------------------------------------------------------------------------------
# DAFTAR VARIABEL (dipakai juga oleh `/embed variabel` dan validasi)
# ------------------------------------------------------------------------------
MEMBER_TOKENS: tuple[tuple[str, str], ...] = (
    ("member.name", "Nama pengguna (username)"),
    ("member.display_name", "Nama tampilan di server"),
    ("member.mention", "Mention, mis. @budi"),
    ("member.id", "ID pengguna"),
    ("member.avatar_url", "URL avatar"),
    ("member.created", "Tanggal akun dibuat"),
    ("member.created_relative", "Umur akun, mis. 3 tahun lalu"),
    ("member.created_long", "Tanggal akun dibuat (lengkap)"),
    ("member.joined", "Tanggal bergabung ke server"),
    ("member.joined_relative", "Sejak kapan bergabung"),
    ("member.joined_long", "Tanggal bergabung (lengkap)"),
    ("member.role_count", "Jumlah role yang dimiliki"),
    ("member.bot", "`Ya` bila akun bot, `Tidak` bila manusia"),
)

SERVER_TOKENS: tuple[tuple[str, str], ...] = (
    ("server.name", "Nama server"),
    ("server.id", "ID server"),
    ("server.members", "Jumlah member"),
    ("server.boosts", "Jumlah boost"),
    ("server.roles", "Jumlah role"),
    ("server.icon_url", "URL ikon server"),
    ("server.owner", "Mention pemilik server"),
    ("server.created", "Tanggal server dibuat"),
    ("server.created_relative", "Umur server"),
    ("server.created_long", "Tanggal server dibuat (lengkap)"),
)

CHANNEL_TOKENS: tuple[tuple[str, str], ...] = (
    ("channel.name", "Nama channel"),
    ("channel.mention", "Mention channel"),
    ("channel.id", "ID channel"),
)

MISC_TOKENS: tuple[tuple[str, str], ...] = (
    ("now", "Waktu sekarang"),
    ("now_relative", "Waktu sekarang (relatif, mis. dalam 2 menit)"),
    ("now_long", "Waktu sekarang (lengkap)"),
)

ALIAS_TOKENS: tuple[tuple[str, str], ...] = (
    ("user", "Alias lama dari `{member.mention}`"),
    ("name", "Alias lama dari `{member.display_name}`"),
    ("guild", "Alias lama dari `{server.name}`"),
)

ALL_TOKENS: tuple[tuple[str, str], ...] = (
    MEMBER_TOKENS + SERVER_TOKENS + CHANNEL_TOKENS + MISC_TOKENS + ALIAS_TOKENS
)

KNOWN_TOKENS: frozenset[str] = frozenset(name for name, _ in ALL_TOKENS)

# Alias lama (dipakai pesan boost sebelum mesin variabel ada).
ALIAS_MAP: dict[str, str] = {
    "user": "member.mention",
    "name": "member.display_name",
    "guild": "server.name",
}


# ------------------------------------------------------------------------------
# PEMBANTU
# ------------------------------------------------------------------------------
def _timestamp(value: Any) -> float | None:
    """Ambil epoch dari datetime/objek Discord; `None` bila tidak ada."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    for attr in ("timestamp", "created_at", "joined_at"):
        getter = getattr(value, attr, None)
        if isinstance(getter, (int, float)):
            return float(getter)
        if isinstance(getter, datetime):
            return getter.timestamp()
    if isinstance(value, datetime):
        return value.timestamp()
    return None


def _fmt_ts(epoch: float | None, style: str) -> str:
    """Format timestamp Discord `<t:...:X>`; kosong bila tidak ada data."""
    if epoch is None:
        return ""
    return f"<t:{int(epoch)}:{style}>"


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _member_value(token: str, member: Any) -> str:
    if member is None:
        return ""
    if token == "member.name":
        return _str(getattr(member, "name", None))
    if token == "member.display_name":
        return _str(getattr(member, "display_name", None) or getattr(member, "name", None))
    if token == "member.mention":
        return _str(getattr(member, "mention", None))
    if token == "member.id":
        return _str(getattr(member, "id", None))
    if token == "member.avatar_url":
        url = getattr(getattr(member, "display_avatar", None), "url", None)
        return _str(url)
    if token == "member.created":
        return _fmt_ts(_timestamp(getattr(member, "created_at", None)), "f")
    if token == "member.created_relative":
        return _fmt_ts(_timestamp(getattr(member, "created_at", None)), "R")
    if token == "member.created_long":
        return _fmt_ts(_timestamp(getattr(member, "created_at", None)), "F")
    if token == "member.joined":
        return _fmt_ts(_timestamp(getattr(member, "joined_at", None)), "f")
    if token == "member.joined_relative":
        return _fmt_ts(_timestamp(getattr(member, "joined_at", None)), "R")
    if token == "member.joined_long":
        return _fmt_ts(_timestamp(getattr(member, "joined_at", None)), "F")
    if token == "member.role_count":
        roles = getattr(member, "roles", None)
        try:
            count = len(roles) if roles is not None else 0
        except TypeError:  # pragma: no cover - objek aneh
            count = 0
        # role @everyone selalu ikut terhitung di discord.py
        return str(max(count - 1, 0))
    if token == "member.bot":
        return "Ya" if getattr(member, "bot", False) else "Tidak"
    return ""


def _guild_value(token: str, guild: Any) -> str:
    if guild is None:
        return ""
    if token == "server.name":
        return _str(getattr(guild, "name", None))
    if token == "server.id":
        return _str(getattr(guild, "id", None))
    if token == "server.members":
        return _str(getattr(guild, "member_count", None))
    if token == "server.boosts":
        return _str(getattr(guild, "premium_subscription_count", None))
    if token == "server.roles":
        roles = getattr(guild, "roles", None)
        try:
            return str(len(roles) if roles is not None else 0)
        except TypeError:  # pragma: no cover
            return "0"
    if token == "server.icon_url":
        icon = getattr(guild, "icon", None)
        url = getattr(icon, "url", None)
        return _str(url) if url else ""
    if token == "server.owner":
        return _str(getattr(guild, "owner", None) and getattr(guild.owner, "mention", None))
    if token == "server.created":
        return _fmt_ts(_timestamp(getattr(guild, "created_at", None)), "f")
    if token == "server.created_relative":
        return _fmt_ts(_timestamp(getattr(guild, "created_at", None)), "R")
    if token == "server.created_long":
        return _fmt_ts(_timestamp(getattr(guild, "created_at", None)), "F")
    return ""


def _channel_value(token: str, channel: Any) -> str:
    if channel is None:
        return ""
    if token == "channel.name":
        return _str(getattr(channel, "name", None))
    if token == "channel.mention":
        return _str(getattr(channel, "mention", None))
    if token == "channel.id":
        return _str(getattr(channel, "id", None))
    return ""


def resolve(token: str, ctx: Context) -> str | None:
    """Nilai untuk satu token; `None` bila token tidak dikenal."""
    name = token.lower()
    # alias lama lebih dulu, lalu baru dikirim ke kelompoknya
    name = ALIAS_MAP.get(name, name)

    if name in ("now", "now_relative", "now_long"):
        style = {"now": "f", "now_relative": "R", "now_long": "F"}[name]
        epoch = float(ctx.now or time.time())
        return _fmt_ts(epoch, style)
    if name.startswith("member."):
        if name not in KNOWN_TOKENS:
            return None
        return _member_value(name, ctx.member)
    if name.startswith("server."):
        if name not in KNOWN_TOKENS:
            return None
        return _guild_value(name, ctx.guild)
    if name.startswith("channel."):
        if name not in KNOWN_TOKENS:
            return None
        return _channel_value(name, ctx.channel)
    return ""


def render(
    text: str,
    *,
    member: Any = None,
    guild: Any = None,
    channel: Any = None,
    now: float | None = None,
    keep_unknown: bool = True,
    limit: int = MAX_RENDER_LENGTH,
) -> str:
    """Ganti seluruh variabel pada `text`. Aman untuk teks kosong/None."""
    if not text:
        return ""
    ctx = Context(member=member, guild=guild, channel=channel, now=now or time.time())

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        value = resolve(token, ctx)
        if value is None:
            return match.group(0) if keep_unknown else ""
        return value

    hasil = TOKEN_RE.sub(_sub, str(text))
    return hasil[:limit]


def unknown_tokens(text: str) -> list[str]:
    """Daftar variabel yang tidak dikenal (untuk validasi saat admin mengisi form)."""
    if not text:
        return []
    hasil: list[str] = []
    for match in TOKEN_RE.finditer(str(text)):
        token = match.group(1)
        if token.lower() not in KNOWN_TOKENS:
            hasil.append(match.group(0))
    return hasil


def used_tokens(text: str) -> list[str]:
    """Token yang muncul di teks (tanpa duplikat, urut kemunculan)."""
    if not text:
        return []
    seen: list[str] = []
    for match in TOKEN_RE.finditer(str(text)):
        token = match.group(1).lower()
        if token not in seen:
            seen.append(token)
    return seen


def help_lines(entries: Iterable[tuple[str, str]] = ALL_TOKENS) -> list[str]:
    """Baris bantuan `{token}` — `deskripsi` untuk ditampilkan di Discord."""
    return [f"`{{{name}}}` — {desc}" for name, desc in entries]


def check(text: str, member: Any = None, guild: Any = None) -> list[str]:
    """Peringatan ramah untuk admin: token tak dikenal atau data yang belum ada."""
    warnings: list[str] = []
    tak_dikenal = unknown_tokens(text)
    if tak_dikenal:
        warnings.append("Variabel tidak dikenal: " + ", ".join(f"`{t}`" for t in tak_dikenal))
    for token in used_tokens(text):
        if token in ("user", "name") or token.startswith("member."):
            if member is None and token not in ("member.bot",):
                warnings.append(
                    f"`{{{token}}}` butuh konteks member — di pesan terjadwal akan diganti kosong."
                )
                break
    return warnings


__all__ = [
    "ALL_TOKENS",
    "CHANNEL_TOKENS",
    "Context",
    "KNOWN_TOKENS",
    "MEMBER_TOKENS",
    "MISC_TOKENS",
    "SERVER_TOKENS",
    "check",
    "help_lines",
    "render",
    "resolve",
    "unknown_tokens",
    "used_tokens",
]
