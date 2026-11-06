"""Preset pemasangan cepat — dipakai `/mulai` supaya admin awam tidak perlu tahu nama command.

Satu preset = daftar fitur yang biasanyanya dinyalakan bersama, mis. "Server Komunitas"
menyalakan sambutan + auto role + log + pengumuman. Modul ini murni (tanpa I/O) agar
mudah diuji; penerapannya ada di `cogs/mulai_cog.py`.
"""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "komunitas": {
        "label": "Server Komunitas",
        "emoji": "🏡",
        "desc": "Sambutan ramah, auto role, log moderasi, dan pengumuman terjadwal.",
        "butuh": ["channel_sambutan", "role_otomatis", "channel_log"],
        "fitur": ["sambutan", "autorole", "log", "pengumuman"],
    },
    "gaming": {
        "label": "Server Gaming",
        "emoji": "🎮",
        "desc": "Auto role buat pemain, sambutan singkat, dan pengumuman event.",
        "butuh": ["role_otomatis", "channel_sambutan"],
        "fitur": ["autorole", "sambutan", "pengumuman"],
    },
    "sekolah": {
        "label": "Server Sekolah / Kelas",
        "emoji": "🎓",
        "desc": "Sambutan rapi, auto role kelas, dan log moderasi untuk guru/admin.",
        "butuh": ["channel_sambutan", "role_otomatis", "channel_log"],
        "fitur": ["sambutan", "autorole", "log"],
    },
}


def list_presets() -> list[dict]:
    return [{"key": key, **data} for key, data in PRESETS.items()]


def get_preset(key: str | None) -> dict | None:
    return PRESETS.get(str(key or "").strip().lower())


def build_plan(preset: dict, *, channel_sambutan=None, role_otomatis=None, channel_log=None) -> list[dict]:
    """Rencana langkah: apa yang akan dijalankan, mana yang dilewati karena belum dipilih."""
    pilihan = {
        "channel_sambutan": channel_sambutan,
        "role_otomatis": role_otomatis,
        "channel_log": channel_log,
    }
    rencana: list[dict] = []
    if "sambutan" in preset["fitur"]:
        rencana.append(
            {
                "aksi": "sambutan",
                "siap": bool(pilihan["channel_sambutan"]),
                "label": "Sambutan member baru → "
                + (f"<#{getattr(pilihan['channel_sambutan'], 'id', '')}>" if pilihan["channel_sambutan"] else "channel belum dipilih"),
            }
        )
    if "autorole" in preset["fitur"]:
        rencana.append(
            {
                "aksi": "autorole",
                "siap": bool(pilihan["role_otomatis"]),
                "label": "Auto role → "
                + (f"@{getattr(pilihan['role_otomatis'], 'name', '')}" if pilihan["role_otomatis"] else "role belum dipilih"),
            }
        )
    if "log" in preset["fitur"]:
        rencana.append(
            {
                "aksi": "log",
                "siap": bool(pilihan["channel_log"]),
                "label": "Log moderasi → "
                + (f"<#{getattr(pilihan['channel_log'], 'id', '')}>" if pilihan["channel_log"] else "channel belum dipilih"),
            }
        )
    if "pengumuman" in preset["fitur"]:
        rencana.append({"aksi": "pengumuman", "siap": True, "label": "Pengumuman terjadwal → siap dipakai"})
    return rencana


def ringkas(preset: dict) -> str:
    return f"{preset['emoji']} **{preset['label']}** — {preset['desc']}"


__all__ = ["PRESETS", "build_plan", "get_preset", "list_presets", "ringkas"]
