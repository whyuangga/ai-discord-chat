"""Audit RAM ringan untuk Free Tier (**0 kuota AI, 0 dependency baru**).

Dipakai oleh `/perawatan memori` supaya pemilik bot bisa melihat **angka nyata** dari
hosting-nya sendiri (Wispbyte), bukan angka perkiraan dari dokumentasi.

Yang dilaporkan:
- **RAM proses** (RSS) dari `/proc/self/status` (fallback `resource`), dalam MB.
- **Ukuran folder `data/`** (JSON + media) — indikator beban penyimpanan.
- **Jumlah entri cache** yang tumbuh saat runtime, beserta batasnya masing-masing.
- **Tips** otomatis bila ada cache yang mendekati batas.

Semua fungsi di sini hanya **membaca** struktur data yang sudah ada di memori; tidak ada
pemanggilan jaringan, tidak ada penulisan berkas, dan tidak mengubah state apa pun.
"""

import logging
import os
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger("gemini_bot.memory_audit")

# Batas perkiraan untuk ditampilkan bersama angka nyata
CACHE_SPECS: list[dict] = [
    {
        "label": "XP & level member",
        "module": "levels",
        "attr": "levels",
        "cap": "500 member / server",
        "since": "v1.6",
    },
    {
        "label": "Tiket dukungan",
        "module": "tickets",
        "attr": "tickets",
        "cap": "200 tiket selesai (dipangkas)",
        "since": "v1.12",
    },
    {
        "label": "Kasus moderasi",
        "module": "moderation",
        "attr": "mod_cases",
        "cap": "200 kasus / server • 200 server",
        "since": "v1.10",
    },
    {
        "label": "Riwayat anti-nuke",
        "module": "antinuke",
        "attr": "violations",
        "cap": "20 kejadian / server",
        "since": "v1.27",
    },
    {
        "label": "Playlist musik",
        "module": "music_playlists",
        "attr": "guild_playlists",
        "cap": "500 lagu / server • 5 playlist / member",
        "since": "v1.32",
    },
    {
        "label": "Mode raid aktif",
        "module": "raid_guard",
        "attr": "raid_states",
        "cap": "1 status / server, kedaluwarsa otomatis",
        "since": "v1.31",
    },
    {
        "label": "Catatan join raid",
        "module": "raid_guard",
        "attr": "_recent_joins",
        "cap": "jendela 10–3600 detik, dibersihkan tiap 1 jam",
        "since": "v1.31",
    },
    {
        "label": "Bahasa server",
        "module": "i18n",
        "attr": "guild_lang",
        "cap": "1 entri kecil / server (default tidak disimpan)",
        "since": "v1.36",
    },
    {
        "label": "Prefix server",
        "module": "prefixes",
        "attr": "guild_prefixes",
        "cap": "1 entri kecil / server",
        "since": "v1.37",
    },
    {
        "label": "Konfigurasi ekspor analitik",
        "module": "analytics_export",
        "attr": "analytics_guilds",
        "cap": "1 entri kecil / server (kosong dibuang)",
        "since": "v1.38",
    },
    {
        "label": "Sesi chat privat",
        "module": "storage",
        "attr": "thread_chats",
        "cap": "kedaluwarsa SESSION_EXPIRE_DAYS",
        "since": "v1.0",
    },
    {
        "label": "Sesi gambar privat",
        "module": "storage",
        "attr": "image_thread_settings",
        "cap": "ikut dibersihkan bersama sesi",
        "since": "v1.2",
    },
    {
        "label": "Ekonomi koin",
        "module": "economy",
        "attr": "economy_guilds",
        "cap": "200 server (dipangkas)",
        "since": "v1.23",
    },
]


def rss_mb() -> float:
    """RAM proses saat ini (MB). Tidak pernah melempar exception."""
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception:  # pragma: no cover - non-Linux
        pass
    try:  # pragma: no cover - fallback macOS/BSD
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1024 * 1024) if peak > 10**6 else peak / 1024, 1)
    except Exception:
        return 0.0


def _resolve(module_name: str, attr: str):
    """Mengambil objek dari modul yang sudah dimuat (import lazy, tanpa efek samping)."""
    import importlib

    try:
        module = importlib.import_module(module_name)
    except Exception:  # pragma: no cover - modul opsional tidak ada
        return None
    return getattr(module, attr, None)


def _count_entries(value) -> int:
    """Menghitung entri sebuah cache secara aman."""
    if value is None:
        return 0
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 0


def cache_counts() -> list[dict]:
    """Jumlah entri tiap cache yang terdaftar di `CACHE_SPECS`."""
    hasil = []
    for spec in CACHE_SPECS:
        value = _resolve(spec["module"], spec["attr"])
        hasil.append(
            {
                "label": spec["label"],
                "module": spec["module"],
                "attr": spec["attr"],
                "cap": spec["cap"],
                "since": spec.get("since", ""),
                "entries": _count_entries(value),
                "available": value is not None,
            }
        )
    return hasil


def playlist_track_total() -> int:
    """Total lagu tersimpan di seluruh playlist (indikator beban terbesar)."""
    store = _resolve("music_playlists", "guild_playlists")
    if not isinstance(store, dict):
        return 0
    total = 0
    for users in store.values():
        for playlists in users.values():
            for data in playlists.values():
                total += len(data.get("tracks") or [])
    return total


def data_files() -> list[tuple[str, int]]:
    """Daftar berkas di folder `data/` beserta ukurannya (`(nama, byte)`), terbesar dulu."""
    root = Path(DATA_DIR)
    if not root.exists():
        return []
    hasil: list[tuple[str, int]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:  # pragma: no cover - berkas hilang
            continue
        hasil.append((str(path.relative_to(root)), size))
    hasil.sort(key=lambda item: item[1], reverse=True)
    return hasil


def data_dir_kb() -> float:
    """Total ukuran folder `data/` dalam KB."""
    return round(sum(size for _name, size in data_files()) / 1024, 1)


def snapshot() -> dict:
    """Ringkasan lengkap untuk ditampilkan / dites."""
    caches = cache_counts()
    files = data_files()
    return {
        "rss_mb": rss_mb(),
        "data_kb": round(sum(size for _n, size in files) / 1024, 1),
        "files": len(files),
        "biggest": [{"name": name, "kb": round(size / 1024, 1)} for name, size in files[:5]],
        "caches": caches,
        "total_entries": sum(item["entries"] for item in caches),
        "playlist_tracks": playlist_track_total(),
    }


def suggestions(snap: dict | None = None) -> list[str]:
    """Tips singkat berdasarkan isi snapshot (maks 4 baris)."""
    snap = snap or snapshot()
    tips: list[str] = []
    if snap["rss_mb"] >= 400:
        tips.append("RAM sudah tinggi: matikan fitur yang jarang dipakai (`/musik`, gambar dinamis).")
    elif snap["rss_mb"] >= 200:
        tips.append("Pantau RAM: hindari menyalakan gambar dinamis + musik + AI berat bersamaan.")
    if snap.get("playlist_tracks", 0) >= 2000:
        tips.append("Playlist member besar: minta member menghapus playlist lama (`/musik playlist hapus`).")
    if snap["data_kb"] >= 8192:
        tips.append("Folder `data/` > 8 MB: unduh backup lalu bersihkan berkas lama di panel hosting.")
    if any(item["module"] == "tickets" and item["entries"] > 150 for item in snap["caches"]):
        tips.append("Tiket selesai hampir penuh: transkrip lama otomatis dipangkas, tidak perlu tindakan.")
    if not tips:
        tips.append("Semua dalam batas sehat untuk Free Tier — tidak ada tindakan yang diperlukan.")
    return tips[:4]


def format_report(snap: dict | None = None) -> str:
    """Teks siap kirim untuk `/perawatan memori` (maks ±1800 karakter)."""
    snap = snap or snapshot()
    lines = [
        f"🧠 **RAM proses:** `{snap['rss_mb']}` MB",
        f"🗂️ **Folder `data/`:** `{snap['data_kb']}` KB (`{snap['files']}` berkas • "
        f"`{snap['total_entries']}` entri cache • `{snap['playlist_tracks']}` lagu playlist)",
    ]

    biggest = [item for item in snap["caches"] if item["entries"] > 0]
    biggest.sort(key=lambda item: item["entries"], reverse=True)
    if biggest:
        lines.append("")
        lines.append("**Cache terbesar**")
        for item in biggest[:6]:
            lines.append(f"• {item['label']}: `{item['entries']}` entri — batas {item['cap']}")

    if snap["biggest"]:
        lines.append("")
        lines.append("**Berkas `data/` terbesar**")
        for item in snap["biggest"]:
            lines.append(f"• `{item['name']}` — `{item['kb']}` KB")

    lines.append("")
    lines.append("**Saran**")
    lines.extend(f"• {tip}" for tip in suggestions(snap))
    return "\n".join(lines)[:1900]


def short_line() -> str:
    """Ringkasan satu baris (dipakai dashboard/status lain)."""
    snap = snapshot()
    return f"RAM `{snap['rss_mb']}` MB • data `{snap['data_kb']}` KB • `{snap['total_entries']}` entri cache"


def path_size_kb(path: str | os.PathLike) -> float:
    """Ukuran satu berkas/folder dalam KB (0 bila tidak ada)."""
    target = Path(path)
    if target.is_file():
        try:
            return round(target.stat().st_size / 1024, 1)
        except OSError:
            return 0.0
    if not target.exists():
        return 0.0
    total = 0
    for child in target.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return round(total / 1024, 1)
