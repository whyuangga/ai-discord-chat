"""Kebijakan visibilitas command — mengurangi "kebisingan" daftar slash.

Masalah: 52 command utama + 236 subcommand = 288 entri, sehingga admin awam
kewalahan. Solusi paling murah: command yang jelas khusus pengelola server diberi
`default_member_permissions`, sehingga **member biasa tidak melihatnya sama sekali**
(Discord menyembunyikan command yang izinnya tidak dipenuhi).

Pemetaan di bawah sengaja konservatif — hanya command yang sudah memeriksa izin
Admin/Manage Server di dalam kodenya. Command umum (afk, level, ekonomi, musik,
cari, bantuan, status, saran, …) tetap terlihat semua orang.

Jalankan `python tools/command_audit.py` untuk melihat hasilnya.
"""

from __future__ import annotations

from discord import Permissions

# Butuh Administrator — command pengaturan server/keamanan.
ADMIN_ONLY: frozenset[str] = frozenset(
    {
        "analitik",
        "autorole",
        "backup",
        "bahasa",
        "fakta",
        "jawab-otomatis",
        "keamanan",
        "lockdown",
        "log",
        "menu",
        "nuke",
        "panel-role",
        "pengumuman",
        "perawatan",
        "raid",
        "serverstats",
        "sosial",
        "starboard",
        "sticky",
        "terjemah",
        "thread-otomatis",
        "verifikasi",
    }
)

# Cukup Manage Server — pengaturan ringan (prefix, kontrol panel).
MANAGE_GUILD_ONLY: frozenset[str] = frozenset({"prefix", "panel"})

# Command moderasi: butuh izin moderasi, tetap terlihat oleh moderator.
MODERATE_ONLY: frozenset[str] = frozenset({"mod"})

ADMIN_PERMS = Permissions(administrator=True)
MANAGE_PERMS = Permissions(manage_guild=True)
MOD_PERMS = Permissions(moderate_members=True)


def policy_for(name: str) -> Permissions | None:
    """Izin minimum untuk satu command utama; `None` = semua member boleh lihat."""
    bersih = str(name or "").strip().lower()
    if bersih in ADMIN_ONLY:
        return ADMIN_PERMS
    if bersih in MANAGE_GUILD_ONLY:
        return MANAGE_PERMS
    if bersih in MODERATE_ONLY:
        return MOD_PERMS
    return None


def _entries(command) -> int:
    return 1 + len(getattr(command, "commands", []) or [])


def apply(tree) -> dict:
    """Terapkan kebijakan ke seluruh command tree. Kembalikan ringkasan."""
    hasil = {"admin": 0, "manage": 0, "mod": 0, "entri_tersembunyi": 0}
    for command in tree.get_commands():
        perms = policy_for(getattr(command, "name", ""))
        if perms is None:
            continue
        command.default_member_permissions = perms
        if perms.administrator:
            hasil["admin"] += 1
        elif perms.manage_guild:
            hasil["manage"] += 1
        else:
            hasil["mod"] += 1
        hasil["entri_tersembunyi"] += _entries(command)
    return hasil


def audit(tree) -> dict:
    """Statistik permukaan command sebelum/sesudah kebijakan."""
    utama = list(tree.get_commands())
    sub = sum(len(getattr(c, "commands", []) or []) for c in utama)
    tersembunyi = sum(
        _entries(c)
        for c in utama
        if getattr(c, "default_member_permissions", None) is not None
    )
    total = len(utama) + sub
    return {
        "top_level": len(utama),
        "subcommand": sub,
        "total": total,
        "tersembunyi": tersembunyi,
        "terlihat_member": total - tersembunyi,
    }


__all__ = [
    "ADMIN_ONLY",
    "MANAGE_GUILD_ONLY",
    "MODERATE_ONLY",
    "apply",
    "audit",
    "policy_for",
]
