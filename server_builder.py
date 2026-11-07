"""Pembangun server instan — 15 tema siap pakai + perancang AI (0 kuota untuk tema).

Ide diambil dari **Instabot** (15 tema, server jadi dalam 2 detik) dan **purpleGPT**
(`/genserver`: jelaskan server impianmu, AI menyusun strukturnya).

Alur aman:

1. `/bangun tema` — pilih tema bawaan; bot hanya **menampilkan pratinjau**.
2. `/bangun rancang` — deskripsi bebas (mis. "server komunitas fotografi dengan kelas
   pemula") diubah AI menjadi struktur; bila AI gagal, jatuh ke tema terdekat.
3. `/bangun terapkan` — Admin menekan konfirmasi, bot baru membuat role/kategori/channel.

Pembuatan item memakai `backup_restore.build_plan` + `apply_plan` (kode yang sudah
teruji: hanya menambah, tidak pernah menghapus, maks 30 item/pemulihan, jeda rate limit).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import discord

from config import DATA_DIR

logger = logging.getLogger("gemini_bot.server_builder")

BUILDER_FILE = Path(DATA_DIR) / "server_builder.json"

MAKS_KATEGORI = 8
MAKS_CHANNEL = 40
MAKS_ROLE = 12
MAKS_HURUF_NAMA = 100

#: Tema bawaan. `kata` dipakai untuk menebak tema dari deskripsi bebas.
_TEMA_BAKU: dict[str, dict] = {
    "gaming": {
        "label": "Gaming / Esport", "emoji": "🎮",
        "kata": ("game", "gaming", "esport", "mabar", "ml", "valorant", "pubg"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan", "jadwal-mabar"], "voice": []},
            "💬 KOMUNITAS": {"text": ["umum", "cari-tim", "klip-epik", "perkenalan"], "voice": ["🔊 Mabar 1", "🔊 Mabar 2"]},
            "🏆 TURNAMEN": {"text": ["info-turnamen", "hasil", "jadwal"], "voice": ["🔊 Scrim"]},
        },
        "role": [("🎮 Player", 0x5865F2), ("🏆 Juara", 0xF1C40F), ("🎥 Streamer", 0x9B59B6)],
    },
    "komunitas": {
        "label": "Komunitas Umum", "emoji": "🌍",
        "kata": ("komunitas", "community", "ngobrol", "umum", "warga"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan", "faq"], "voice": []},
            "💬 OBROLAN": {"text": ["umum", "curhat-ringan", "perkenalan", "memes"], "voice": ["🔊 Ngobrol", "🔊 Santai"]},
            "🎉 EVENT": {"text": ["info-event", "usulan-event"], "voice": ["🔊 Event"]},
        },
        "role": [("👥 Member", 0x2ECC71), ("⭐ Aktif", 0xF39C12), ("🛡️ Staf", 0xE74C3C)],
    },
    "aesthetic": {
        "label": "Aesthetic / Minimalis", "emoji": "🕊️",
        "kata": ("aesthetic", "minimalis", "kalem", "estetik", "lofi"),
        "kategori": {
            "· info": {"text": ["announcements", "rules"], "voice": []},
            "· hangout": {"text": ["general", "daily", "playlist", "aesthetic"], "voice": ["· lounge", "· late night"]},
            "· archive": {"text": ["foto", "inspirasi"], "voice": []},
        },
        "role": [("member", 0xE8E6E3), ("vibes", 0xB8A6E2)],
    },
    "study": {
        "label": "Study / Belajar", "emoji": "📚",
        "kata": ("belajar", "study", "sekolah", "kuliah", "ujian", "tugas"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan-belajar", "sumber-belajar"], "voice": []},
            "📚 KELAS": {"text": ["tanya-jawab", "catatan", "tugas"], "voice": ["🔊 Kelas", "🔊 Belajar Bareng"]},
            "🎯 TARGET": {"text": ["target-harian", "pomodoro"], "voice": ["🔊 Fokus 25 menit"]},
        },
        "role": [("📚 Pelajar", 0x3498DB), ("🧑‍🏫 Pengajar", 0x8E44AD), ("✅ Fokus", 0x1ABC9C)],
    },
    "musik": {
        "label": "Musik", "emoji": "🎵",
        "kata": ("musik", "music", "band", "lagu", "gitar", "lofi"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan"], "voice": []},
            "🎵 MUSIK": {"text": ["rekomendasi", "request-lagu", "review"], "voice": ["🔊 Dengerin", "🔊 Jam Session"]},
            "💿 PROYEK": {"text": ["kolaborasi", "lirik", "feedback"], "voice": []},
        },
        "role": [("🎧 Pendengar", 0x1DB954), ("🎸 Musisi", 0xE67E22), ("🎤 Vokalis", 0xE91E63)],
    },
    "seni": {
        "label": "Seni & Desain", "emoji": "🎨",
        "kata": ("seni", "art", "desain", "gambar", "ilustrasi", "digital"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan"], "voice": []},
            "🎨 GALERI": {"text": ["karya-sendiri", "inspirasi", "kritik-saran"], "voice": []},
            "💬 STUDIO": {"text": ["umum", "komisi", "tools"], "voice": ["🔊 Studio", "🔊 Ngobrol"]},
        },
        "role": [("🎨 Seniman", 0xF1C40F), ("🖌️ Digital", 0x3498DB), ("📐 Desainer", 0x2ECC71)],
    },
    "teknologi": {
        "label": "Teknologi & Gadget", "emoji": "💻",
        "kata": ("teknologi", "tech", "gadget", "hardware", "pc", "linux"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan"], "voice": []},
            "💻 DISKUSI": {"text": ["umum", "hardware", "software", "tanya-teknis"], "voice": ["🔊 Diskusi"]},
            "🛠️ PROYEK": {"text": ["showcase", "bantuan"], "voice": []},
        },
        "role": [("💻 Tech", 0x3498DB), ("🛠️ Builder", 0xE67E22)],
    },
    "crypto": {
        "label": "Crypto & Trading", "emoji": "📈",
        "kata": ("crypto", "trading", "bitcoin", "saham", "investasi", "nft"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "disclaimer", "aturan"], "voice": []},
            "📈 PASAR": {"text": ["bitcoin", "altcoin", "analisa", "berita"], "voice": ["🔊 Market Talk"]},
            "🧠 EDUKASI": {"text": ["pemula", "istilah", "tanya-jawab"], "voice": []},
        },
        "role": [("📈 Trader", 0xF39C12), ("🧠 Analyst", 0x3498DB)],
    },
    "anime": {
        "label": "Anime & Manga", "emoji": "🌸",
        "kata": ("anime", "manga", "otaku", "waifu", "jepang"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan"], "voice": []},
            "🌸 KOMUNITAS": {"text": ["umum", "rekomendasi", "fanart", "perkenalan"], "voice": ["🔊 Nobar", "🔊 Ngobrol"]},
            "📺 MUSIM": {"text": ["seasonal", "spoiler", "review"], "voice": []},
        },
        "role": [("🌸 Otaku", 0xE91E63), ("📺 Nobar", 0x9B59B6)],
    },
    "roleplay": {
        "label": "Roleplay", "emoji": "🎭",
        "kata": ("roleplay", "rp", "cerita", "karakter", "fantasi"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan-rp", "lore"], "voice": []},
            "🎭 PERMAINAN": {"text": ["in-character", "out-of-character", "cari-partner"], "voice": ["🔊 Sesi RP"]},
            "📖 KARAKTER": {"text": ["lembar-karakter", "galeri"], "voice": []},
        },
        "role": [("🎭 Pemain", 0x9B59B6), ("📖 Narator", 0x2C3E50)],
    },
    "bisnis": {
        "label": "Bisnis & UMKM", "emoji": "💼",
        "kata": ("bisnis", "business", "umkm", "jualan", "usaha", "marketing"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan", "kontak"], "voice": []},
            "💼 DISKUSI": {"text": ["umum", "strategi", "tanya-jawab"], "voice": ["🔊 Meeting"]},
            "🛍️ PASAR": {"text": ["promo", "testimoni", "lowongan"], "voice": []},
        },
        "role": [("💼 Pebisnis", 0x34495E), ("🛍️ Penjual", 0xE67E22), ("🤝 Mitra", 0x16A085)],
    },
    "coding": {
        "label": "Coding & Dev", "emoji": "🧑‍💻",
        "kata": ("coding", "programming", "developer", "python", "javascript", "dev"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan", "roadmap"], "voice": []},
            "🧑‍💻 KODE": {"text": ["umum", "bantuan-kode", "code-review", "showcase"], "voice": ["🔊 Pair Programming"]},
            "🐛 PROYEK": {"text": ["bug", "ide-fitur", "rilis"], "voice": []},
        },
        "role": [("🧑‍💻 Dev", 0x2ECC71), ("🐛 Tester", 0xE67E22), ("📦 Maintainer", 0x3498DB)],
    },
    "kesehatan": {
        "label": "Kesehatan & Fitness", "emoji": "🏃",
        "kata": ("sehat", "fitness", "gym", "olahraga", "diet", "lari"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "aturan", "disclaimer"], "voice": []},
            "🏃 LATIHAN": {"text": ["jadwal", "progres", "tanya-jawab"], "voice": ["🔊 Workout Bareng"]},
            "🥗 GIZI": {"text": ["resep", "meal-prep"], "voice": []},
        },
        "role": [("🏃 Aktif", 0x27AE60), ("🥗 Nutrisi", 0xF1C40F)],
    },
    "keluarga": {
        "label": "Keluarga & Sahabat", "emoji": "🏡",
        "kata": ("keluarga", "family", "sahabat", "teman", "pribadi"),
        "kategori": {
            "🏡 RUMAH": {"text": ["pengumuman", "aturan-rumah"], "voice": ["🔊 Ruang Tamu", "🔊 Kamar"]},
            "📸 KENANGAN": {"text": ["foto-bersama", "ultah", "momen"], "voice": []},
        },
        "role": [("🏡 Keluarga", 0xF39C12), ("👑 Kepala Keluarga", 0xE74C3C)],
    },
    "startup": {
        "label": "Startup & Produk", "emoji": "🚀",
        "kata": ("startup", "produk", "saas", "founder", "mvp"),
        "kategori": {
            "📢 INFORMASI": {"text": ["pengumuman", "visi", "aturan"], "voice": []},
            "🚀 PRODUK": {"text": ["ide", "feedback", "roadmap"], "voice": ["🔊 Sprint"]},
            "👥 TIM": {"text": ["umum", "rekrutmen"], "voice": ["🔊 Standup"]},
        },
        "role": [("🚀 Founder", 0xE74C3C), ("🛠️ Tim", 0x3498DB), ("🧪 Beta Tester", 0x9B59B6)],
    },
}

#: Riwayat pembangunan per server (untuk `/bangun riwayat` & bongkar).
riwayat: dict[int, dict] = {}


def _norm(nama: object) -> str:
    return str(nama or "").strip().casefold()


def daftar_tema() -> list[dict]:
    """Daftar tema bawaan untuk autocomplete & pratinjau."""
    return [
        {"id": kunci, "label": f'{data["emoji"]} {data["label"]}', "emoji": data["emoji"]}
        for kunci, data in _TEMA_BAKU.items()
    ]


def cari_tema(kunci: str) -> str | None:
    """Cari id tema dari id/emoji/nama (toleran huruf besar & spasi)."""
    cari = _norm(kunci)
    if not cari:
        return None
    for kunci_tema, data in _TEMA_BAKU.items():
        pilihan = {_norm(kunci_tema), _norm(data["label"]), _norm(data["emoji"])}
        pilihan |= {_norm(data["label"].split("/")[0])}
        if cari in pilihan:
            return kunci_tema
    for kunci_tema, data in _TEMA_BAKU.items():
        if cari in _norm(data["label"]) or cari in _norm(kunci_tema):
            return kunci_tema
    return None


def tema_dari_deskripsi(deskripsi: str) -> str:
    """Tebak tema paling cocok dari kata kunci deskripsi (tanpa AI)."""
    teks = _norm(deskripsi)
    skor: dict[str, int] = {}
    for kunci, data in _TEMA_BAKU.items():
        skor[kunci] = sum(1 for kata in data["kata"] if kata in teks)
    terbaik = max(skor, key=lambda k: skor[k])
    return terbaik if skor[terbaik] > 0 else "komunitas"


def tema_ke_snapshot(kunci_tema: str, *, nama_server: str = "") -> dict:
    """Ubah tema menjadi format snapshot `backup_restore` (roles + categories + channels)."""
    data = _TEMA_BAKU[kunci_tema]
    roles = [
        {
            "name": nama[:MAKS_HURUF_NAMA],
            "permissions": 0,
            "colour": int(warna),
            "hoist": True,
            "mentionable": True,
        }
        for nama, warna in data.get("role") or []
    ]
    categories = [{"name": nama[:MAKS_HURUF_NAMA]} for nama in data["kategori"]]
    channels = []
    for nama_kategori, isi in data["kategori"].items():
        for nama in isi.get("text") or []:
            channels.append({"name": nama[:MAKS_HURUF_NAMA], "type": "text", "category": nama_kategori})
        for nama in isi.get("voice") or []:
            channels.append({"name": nama[:MAKS_HURUF_NAMA], "type": "voice", "category": nama_kategori})
    return {
        "meta": {
            "guild_name": nama_server or data["label"],
            "sumber": f"tema:{kunci_tema}",
            "label": data["label"],
        },
        "roles": roles,
        "categories": categories,
        "channels": channels,
    }


def validasi(snapshot: dict) -> tuple[bool, str]:
    """Pastikan struktur tidak melebihi batas aman Discord/rate limit."""
    if not isinstance(snapshot, dict):
        return False, "Struktur tidak dikenali."
    roles = snapshot.get("roles") or []
    kategori = snapshot.get("categories") or []
    channels = snapshot.get("channels") or []
    if not channels:
        return False, "Struktur tidak punya satu pun channel."
    if len(kategori) > MAKS_KATEGORI:
        return False, f"Terlalu banyak kategori ({len(kategori)} > {MAKS_KATEGORI})."
    if len(channels) > MAKS_CHANNEL:
        return False, f"Terlalu banyak channel ({len(channels)} > {MAKS_CHANNEL})."
    if len(roles) > MAKS_ROLE:
        return False, f"Terlalu banyak role ({len(roles)} > {MAKS_ROLE})."
    for item in channels:
        nama = str(item.get("name") or "").strip()
        if not nama:
            return False, "Ada channel tanpa nama."
        if item.get("type") not in ("text", "voice", "forum", "news", "stage"):
            return False, f"Tipe channel `{item.get('type')}` tidak didukung."
    return True, "Struktur valid."


def normalisasi(snapshot: dict, *, label: str = "") -> dict:
    """Rapikan nama & buang field asing supaya `apply_plan` tidak kaget."""
    hasil = {
        "meta": {
            "guild_name": str((snapshot.get("meta") or {}).get("guild_name") or label or "")[:MAKS_HURUF_NAMA],
            "sumber": str((snapshot.get("meta") or {}).get("sumber") or "ai")[:40],
            "label": str((snapshot.get("meta") or {}).get("label") or label or "Rancangan AI")[:60],
        },
        "roles": [],
        "categories": [],
        "channels": [],
    }
    for item in snapshot.get("roles") or []:
        nama = str(item.get("name") or "").strip()[:MAKS_HURUF_NAMA]
        if not nama:
            continue
        hasil["roles"].append(
            {
                "name": nama,
                "permissions": int(item.get("permissions") or 0),
                "colour": int(item.get("colour") or 0),
                "hoist": bool(item.get("hoist", True)),
                "mentionable": bool(item.get("mentionable", True)),
            }
        )
    nama_kategori = set()
    for item in snapshot.get("categories") or []:
        nama = str(item.get("name") or "").strip()[:MAKS_HURUF_NAMA]
        if not nama or _norm(nama) in nama_kategori:
            continue
        nama_kategori.add(_norm(nama))
        hasil["categories"].append({"name": nama})
    for item in snapshot.get("channels") or []:
        nama = str(item.get("name") or "").strip()[:MAKS_HURUF_NAMA]
        if not nama:
            continue
        jenis = str(item.get("type") or "text").lower()
        if jenis not in ("text", "voice", "forum", "news", "stage"):
            jenis = "text"
        entri = {"name": nama, "type": jenis}
        kategori = str(item.get("category") or "").strip()
        if kategori and _norm(kategori) in nama_kategori:
            entri["category"] = kategori[:MAKS_HURUF_NAMA]
        topik = str(item.get("topic") or "").strip()
        if topik and jenis == "text":
            entri["topic"] = topik[:1024]
        hasil["channels"].append(entri)
    return hasil


def ringkas(snapshot: dict) -> str:
    """Pratinjau teks ringkas: kategori → channel, plus role."""
    kategori: dict[str, list[str]] = {}
    for item in snapshot.get("channels") or []:
        kategori.setdefault(str(item.get("category") or "tanpa kategori"), []).append(
            f"{'🔊' if item.get('type') == 'voice' else '#'}{item.get('name')}"
        )
    baris = [
        f"**{nama}** — {', '.join(isi)}"
        for nama, isi in list(kategori.items())[:MAKS_KATEGORI]
    ]
    role = ", ".join(f"`{item.get('name')}`" for item in (snapshot.get("roles") or [])[:MAKS_ROLE])
    teks = "\n".join(baris) or "_tidak ada channel_"
    if role:
        teks += f"\n**Role:** {role}"
    jumlah = len(snapshot.get("channels") or [])
    return f"{teks}\n\n_{jumlah} channel · {len(snapshot.get('categories') or [])} kategori · {len(snapshot.get('roles') or [])} role._"


async def rancang(deskripsi: str, *, ai_call=None) -> tuple[dict, str]:
    """Buat struktur dari deskripsi bebas. `ai_call` = fungsi async(prompt) → teks JSON."""
    teks = str(deskripsi or "").strip()
    if ai_call is not None and teks:
        prompt = (
            "Susun struktur server Discord untuk deskripsi berikut:\n"
            f"{teks[:600]}\n\n"
            "Balas HANYA JSON: {\"roles\":[{\"name\":\"...\"}],"
            "\"categories\":[{\"name\":\"...\"}],"
            "\"channels\":[{\"name\":\"...\",\"type\":\"text|voice\",\"category\":\"...\"}]}\n"
            f"Maks {MAKS_KATEGORI} kategori, {MAKS_CHANNEL} channel, {MAKS_ROLE} role. "
            "Nama singkat, huruf kecil, tanpa emoji berlebih."
        )
        try:
            jawaban = await ai_call(prompt)
            data = json.loads(_ambil_json(str(jawaban or "")))
            snapshot = normalisasi(data, label="Rancangan AI")
            ok, _alasan = validasi(snapshot)
            if ok:
                return snapshot, "ai"
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Rancangan AI gagal, memakai tema: %s", exc)

    tema = tema_dari_deskripsi(teks)
    return tema_ke_snapshot(tema), f"tema:{tema}"


def _ambil_json(teks: str) -> str:
    """Ambil blok JSON pertama dari jawaban AI (kadang dibungkus ```json)."""
    mulai = teks.find("{")
    akhir = teks.rfind("}")
    if mulai == -1 or akhir <= mulai:
        return "{}"
    return teks[mulai : akhir + 1]


async def terapkan(guild, snapshot: dict, *, actor_id: int = 0, alasan: str = "Bangun server") -> tuple[dict, str]:
    """Buat role/kategori/channel sesuai rencana (memakai mesin `backup_restore`)."""
    import backup_restore

    plan = backup_restore.build_plan(guild, snapshot)
    hasil = await backup_restore.apply_plan(guild, plan, actor_id=actor_id, reason=alasan)
    gid = int(getattr(guild, "id", 0) or 0)
    riwayat[gid] = {
        "pada": time.time(),
        "label": (snapshot.get("meta") or {}).get("label") or "Rancangan",
        "oleh": int(actor_id or 0),
        "dibuat": {
            "roles": [item["name"] for item in (plan.get("roles") or [])],
            "categories": [item["name"] for item in (plan.get("categories") or [])],
            "channels": [item["name"] for item in (plan.get("channels") or [])],
        },
        "hasil": {k: int(v) for k, v in hasil.items() if isinstance(v, int)},
    }
    return hasil, ringkas_hasil(hasil)


def ringkas_hasil(hasil: dict) -> str:
    pesan = (
        f"✅ Dibuat **{hasil.get('roles', 0)} role**, **{hasil.get('categories', 0)} kategori**, "
        f"dan **{hasil.get('channels', 0)} channel**."
    )
    galat = hasil.get("errors") or []
    if galat:
        pesan += f"\n⚠️ {len(galat)} item dilewati: " + "; ".join(galat[:3])
    return pesan


async def bongkar(guild, *, gid: int | None = None) -> tuple[bool, str]:
    """Hapus item yang **dicatat** sebagai buatan `/bangun` (rollback aman)."""
    gid = int(gid if gid is not None else getattr(guild, "id", 0) or 0)
    data = riwayat.get(gid)
    if not data:
        return False, "Belum ada catatan pembangunan di server ini."
    dibuat = data.get("dibuat") or {}
    hapus = 0
    for nama in dibuat.get("channels") or []:
        channel = discord.utils.get(getattr(guild, "channels", []) or [], name=nama)
        if channel is not None:
            try:
                await channel.delete(reason="Batal /bangun")
                hapus += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
    for nama in dibuat.get("categories") or []:
        kategori = discord.utils.get(getattr(guild, "categories", []) or [], name=nama)
        if kategori is not None:
            try:
                await kategori.delete(reason="Batal /bangun")
                hapus += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
    for nama in dibuat.get("roles") or []:
        role = discord.utils.get(getattr(guild, "roles", []) or [], name=nama)
        if role is not None and not getattr(role, "is_default", lambda: False)():
            try:
                await role.delete(reason="Batal /bangun")
                hapus += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
    riwayat.pop(gid, None)
    return True, f"🧹 {hapus} item buatan `/bangun` dihapus."


# ==============================================================================
# SIMPAN / MUAT
# ==============================================================================


def reset_state() -> None:
    riwayat.clear()


def load_from_disk() -> int:
    """Muat riwayat pembangunan. Berkas rusak diabaikan."""
    riwayat.clear()
    path = Path(BUILDER_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            riwayat[int(gid_str)] = {
                "pada": float(data.get("pada") or 0.0),
                "label": str(data.get("label") or "Rancangan")[:60],
                "oleh": int(data.get("oleh") or 0),
                "dibuat": {
                    "roles": [str(x)[:100] for x in (data.get("dibuat") or {}).get("roles") or []],
                    "categories": [str(x)[:100] for x in (data.get("dibuat") or {}).get("categories") or []],
                    "channels": [str(x)[:100] for x in (data.get("dibuat") or {}).get("channels") or []],
                },
                "hasil": dict((data.get("hasil") or {})),
            }
        except (TypeError, ValueError):
            continue
    return len(riwayat)


async def save_to_disk() -> None:
    """Tulis riwayat pembangunan secara atomik."""
    path = Path(BUILDER_FILE)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        isi = {
            "versi": 1,
            "guilds": {str(gid): data for gid, data in riwayat.items()},
        }
        sementara = Path(str(path) + ".tmp")
        sementara.write_text(json.dumps(isi, ensure_ascii=False, indent=1), encoding="utf-8")
        sementara.replace(path)
    except OSError as exc:
        logger.warning("Gagal menyimpan %s: %s", path, exc)
