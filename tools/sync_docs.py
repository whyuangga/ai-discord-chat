"""Sinkronkan dokumentasi Markdown di `docs/` menjadi halaman situs Hugo (`site/`).

Sumber kebenaran tetap **`docs/fitur.md`** dan **`docs/command.md`** — supaya
tautan di README dan tampilan GitHub tidak berubah. Skrip ini menurunkannya
menjadi halaman-halaman kecil ber-*front matter* untuk tema **Lotus Docs**.

Pakai:

    python3 tools/sync_docs.py          # tulis ulang site/content/
    python3 tools/sync_docs.py --check  # hanya periksa (exit 1 bila belum sinkron)

Uji otomatis `tests/test_docs_site.py` memakai `--check` supaya hasil generate
tidak pernah tertinggal dari sumbernya.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = ROOT / "site"

# Slug URL per bagian fitur (dipakai sebagai nama berkas & alamat halaman).
SLUGS = {
    "A": "sesi",
    "B": "agent",
    "C": "keamanan",
    "D": "serverstats",
    "E": "panel-role",
    "F": "musik",
    "G": "giveaway",
    "H": "keamanan-spam",
    "I": "level",
    "J": "dashboard",
    "K": "terjemah",
    "L": "pemakaian",
    "M": "tampilan",
    "N": "log",
    "O": "ekonomi",
    "P": "tumbuh",
    "Q": "menu",
    "R": "nuke",
    "S": "raid",
    "T": "bahasa",
    "U": "prefix",
    "V": "analitik",
    "W": "perawatan",
}

# Ikon sidebar Lotus Docs (Material Symbols).
ICONS = {
    "A": "forum",
    "B": "smart_toy",
    "C": "shield",
    "D": "dns",
    "E": "groups",
    "F": "music_note",
    "G": "celebration",
    "H": "gpp_maybe",
    "I": "military_tech",
    "J": "dashboard",
    "K": "translate",
    "L": "savings",
    "M": "palette",
    "N": "receipt_long",
    "O": "paid",
    "P": "trending_up",
    "Q": "widgets",
    "R": "security",
    "S": "crisis_alert",
    "T": "language",
    "U": "terminal",
    "V": "analytics",
    "W": "memory",
}

# Ringkasan satu baris per bagian (tampil di bawah judul & di kartu navigasi).
DESCRIPTIONS = {
    "A": "Private thread AI per member: 5 kepribadian, PDF, voice note, vision, dan generate gambar.",
    "B": "Auto-chat dengan etika anti-nimbrung, pemecah sepi, galeri, welcome/goodbye, digest & FAQ.",
    "C": "Moderasi bercatatan, raid guard, perkakas server, pemulihan struktur, sampai anti-503.",
    "D": "Channel statistik otomatis, auto role, fakta 4x sehari, dan anti-phishing tanpa API berbayar.",
    "E": "Reaction role, polling, pengingat, starboard, verifikasi, sticky, temp voice, kotak saran.",
    "F": "Lavalink v4 gratis: panel ala Rythm, filter audio, autoplay, role DJ, dan playlist per member.",
    "G": "Giveaway dengan tombol ikut, ulang tahun, balasan otomatis, dan pengumuman terjadwal.",
    "H": "Deteksi spam, link, dan lonjakan join — bawaan mode lapor saja, staff dikecualikan.",
    "I": "XP pesan & voice, role hadiah, musim dan prestige; tiket thread dengan SLA & rating bintang.",
    "J": "Dashboard web ringan di proses yang sama: pantau status dan kontrol fitur dari browser.",
    "K": "Terjemahan ter-cache lewat command, reaksi bendera, atau menu tekan-tahan pesan.",
    "L": "Statistik pemakaian AI, cache rekap channel, FAQ lokal, dan cap harian per member/server.",
    "M": "Panel bergaya web hosting dengan Components V2: tema, aksen, emoji, kepadatan, footer.",
    "N": "Catatan pesan, member, role, dan channel beserta aksi moderasinya di satu channel log.",
    "O": "Koin harian, toko role, transfer, dan papan peringkat — semua lokal tanpa kuota AI.",
    "P": "Ringkasan pertumbuhan server, invite tracker, dan retensi member baru.",
    "Q": "Menu builder dengan tombol role/link/command, self roles v2, dan visibilitas per item.",
    "R": "Anti-nuke: deteksi penghapusan massal, bot asing, mode beku, dan pemulihan ringan.",
    "S": "Mode darurat otomatis saat lonjakan join: tahan auto role, verifikasi, lockdown sementara.",
    "T": "Antarmuka ID/EN untuk dialog konfirmasi, kata status, dan pesan izin (0 kuota AI).",
    "U": "Prefix teks per server; prefix `!` lama tetap berfungsi dan tidak pernah dihapus.",
    "V": "Ekspor CSV level, moderasi, tiket, dan pemakaian AI, plus kirim ke webhook Discord.",
    "W": "Audit RAM, ukuran folder data, cache terbesar beserta batasnya, dan saran otomatis.",
}


def _demote(block: str) -> str:
    """Turunkan heading satu tingkat (### -> ##, #### -> ###) agar hierarki rapi."""
    out = []
    fence = False
    for line in block.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and re.match(r"^#{3,6} ", line):
            line = line[1:]
        out.append(line)
    return "\n".join(out)


def _short(title: str) -> str:
    """Judul ringkas untuk sidebar."""
    t = title.replace("`", "").replace("**", "")
    t = re.sub(r"^Fitur ", "", t)
    t = re.split(r" \((?:`|/|\*\*|DASHBOARD)", t)[0]
    t = re.split(r" — ", t)[0].strip()
    return t.rstrip(",").strip()


def _fm(**fields: object) -> str:
    """Front matter TOML sederhana (Lotus Docs memakai title/description/icon/weight)."""
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        else:
            safe = str(value).replace('"', "'")
            lines.append(f'{key}: "{safe}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def fitur_pages() -> list[dict[str, object]]:
    """Pecah docs/fitur.md menjadi 23 halaman (A–W)."""
    text = (DOCS / "fitur.md").read_text(encoding="utf-8")
    chunks = re.split(r"(?m)^(?=## [A-W]\. )", text)
    pages: list[dict[str, object]] = []
    for chunk in chunks:
        match = re.match(r"^## ([A-W])\. (.+)\n", chunk)
        if not match:
            continue
        letter, title = match.group(1), match.group(2).strip()
        body = chunk.split("\n", 1)[1].strip("\n")
        pages.append(
            {
                "letter": letter,
                "weight": len(pages) + 1,
                "title": f"{letter}. {title.replace('`', '')}",
                "link_title": f"{letter}. {_short(title)}",
                "slug": SLUGS[letter],
                "icon": ICONS[letter],
                "description": DESCRIPTIONS[letter],
                "body": _demote(body),
            }
        )
    return pages


def _docs_index_md(pages: list[dict[str, object]]) -> str:
    lines = [
        _fm(
            title="Dokumentasi",
            description="Penjelasan lengkap 23 area fitur bot AI Discord Chat.",
            icon="menu_book",
            weight=1,
        ),
        "Dokumentasi bot **AI Discord Chat & Community Agent** (`v1.40.0-beta`). "
        "Setiap area fitur punya halamannya sendiri — pilih dari sidebar atau daftar berikut.",
        "",
    ]
    for page in pages:
        lines.append(f"- [{page['title']}]({page['slug']}/)")
    lines += [
        "- [📋 Referensi Command & Tombol](command/)",
        "",
        "Butuh cara memasang (berkas `.env`, Developer Portal, deploy Wispbyte)? Semua ada di "
        "[README](https://github.com/whyuangga/ai-discord-chat#readme).",
        "",
    ]
    return "\n".join(lines)


def _command_md() -> str:
    text = (DOCS / "command.md").read_text(encoding="utf-8")
    body = text.split("\n", 1)[1].strip("\n")
    body = (
        body.replace("](../README.md)", "](https://github.com/whyuangga/ai-discord-chat#readme)")
        .replace("](fitur.md#u-prefix-command-per-server-prefix)", "](prefix/)")
        .replace("](fitur.md)", "](../docs/)")
    )
    return (
        _fm(
            title="Referensi Command & Tombol",
            description="52 command utama, subcommand, dan tombol panel.",
            icon="terminal",
            weight=90,
            toc=True,
        )
        + body
        + "\n"
    )


def generate() -> dict[str, str]:
    """Hasilkan semua berkas konten situs: {path relatif terhadap site/: isi}."""
    pages = fitur_pages()
    files: dict[str, str] = {"content/docs/_index.md": _docs_index_md(pages),
                             "content/docs/command.md": _command_md()}
    for page in pages:
        files[f"content/docs/{page['slug']}.md"] = (
            _fm(
                title=page["title"],
                description=page["description"],
                icon=page["icon"],
                weight=page["weight"],
                toc=True,
            )
            + str(page["body"])
            + "\n"
        )
    return files


def write() -> list[Path]:
    written = []
    for rel, content in generate().items():
        target = SITE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
            written.append(target)
    return written


def check() -> list[str]:
    stale = []
    for rel, content in generate().items():
        target = SITE / rel
        if not target.exists():
            stale.append(f"hilang: site/{rel}")
        elif target.read_text(encoding="utf-8") != content:
            stale.append(f"beda: site/{rel}")
    return stale


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--check" in args:
        stale = check()
        if stale:
            print("Konten situs belum sinkron dengan docs/:")
            for item in stale:
                print(" -", item)
            print("Jalankan: python3 tools/sync_docs.py")
            return 1
        print("Konten situs sinkron dengan docs/ ✔")
        return 0
    written = write()
    print(f"{len(written)} berkas diperbarui di site/content/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
