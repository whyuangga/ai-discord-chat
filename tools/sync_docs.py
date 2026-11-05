"""Sinkronkan dokumentasi Markdown di `docs/` menjadi halaman situs Hugo (`site/`).

Sumber kebenaran tetap **`docs/fitur.md`** dan **`docs/command.md`** — supaya
tautan di README dan tampilan GitHub tidak berubah. Skrip ini menurunkannya
menjadi halaman-halaman kecil ber-*front matter* untuk tema Hextra.

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
CONTENT = SITE / "content"

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

SITE_TITLE = "AI Discord Chat — Dokumentasi"
SITE_DESC = (
    "Dokumentasi bot Discord modular berbasis Google Gemini: 52 command utama, "
    "satu proses, penyimpanan JSON, jalan di Free Tier."
)


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


def _front_matter(title: str, link_title: str, weight: int) -> str:
    safe_title = title.replace('"', "'")
    safe_link = link_title.replace('"', "'")
    return (
        "---\n"
        f'title: "{safe_title}"\n'
        f'linkTitle: "{safe_link}"\n'
        f"weight: {weight}\n"
        "---\n\n"
    )


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
                "body": _demote(body),
            }
        )
    return pages


def _index_md() -> str:
    return """---
title: AI Discord Chat & Community Agent
layout: hextra-home
---

<div class="hx:mt-6 hx:mb-6">
{{< hextra/hero-headline >}}
  Dokumentasi Bot Discord&nbsp;<br class="hx:sm:block hx:hidden" />berbasis Google Gemini
{{< /hextra/hero-headline >}}
</div>

<div class="hx:mb-12">
{{< hextra/hero-subtitle >}}
  52 command utama · satu proses · penyimpanan JSON · jalan di Free Tier (±53 MB RAM)
{{< /hextra/hero-subtitle >}}
</div>

<div class="hx:mb-6">
{{< hextra/hero-button text="Buka dokumentasi" link="docs" >}}
</div>

{{< hextra/feature-grid >}}
  {{< hextra/feature-card title="🔒 Ruang AI privat" subtitle="Private thread, 5 kepribadian, PDF, voice note, vision, generate gambar" link="docs/sesi" >}}
  {{< hextra/feature-card title="🌐 AI Agent publik" subtitle="Auto-chat dengan etika anti-nimbrung, digest pagi, welcome & goodbye" link="docs/agent" >}}
  {{< hextra/feature-card title="🎵 Musik 24/7" subtitle="Lavalink v4, panel ala Rythm, filter audio, playlist per member" link="docs/musik" >}}
  {{< hextra/feature-card title="🛡️ Keamanan" subtitle="Moderasi bercatatan, anti-spam, anti-nuke, raid guard otomatis" link="docs/keamanan" >}}
  {{< hextra/feature-card title="📈 Retensi" subtitle="Level & XP, musim, prestige, tiket thread dengan SLA & rating" link="docs/level" >}}
  {{< hextra/feature-card title="📊 Hemat kuota" subtitle="Statistik AI, cache jawaban, cap harian, 0 kuota untuk UI" link="docs/pemakaian" >}}
{{< /hextra/feature-grid >}}
"""


def _docs_index_md(pages: list[dict[str, object]]) -> str:
    lines = [
        "---",
        'title: "Dokumentasi"',
        'linkTitle: "Dokumentasi"',
        "weight: 0",
        "---",
        "",
        "Dokumentasi lengkap bot **AI Discord Chat & Community Agent** (`v1.40.0-beta`).",
        "Penjelasan tiap area fitur ada di bawah; referensi command di halaman terpisah.",
        "",
    ]
    for page in pages:
        lines.append(f"- [{page['title']}]({page['slug']}/)")
    lines += [
        "- [📋 Referensi Command & Tombol](command/)",
        "",
        "Butuh cara memasang (berkas `.env`, Developer Portal, deploy Wispbyte)? Semua ada di",
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
        .replace("](fitur.md)", "](../)")
    )
    return _front_matter("Referensi Command & Tombol", "📋 Referensi Command", 40) + body + "\n"


def generate() -> dict[str, str]:
    """Hasilkan semua berkas konten situs: {path relatif terhadap site/: isi}."""
    pages = fitur_pages()
    files: dict[str, str] = {
        "content/_index.md": _index_md(),
        "content/docs/_index.md": _docs_index_md(pages),
        "content/docs/command.md": _command_md(),
    }
    for page in pages:
        files[f"content/docs/{page['slug']}.md"] = (
            _front_matter(str(page["title"]), str(page["link_title"]), int(page["weight"]))
            + page["body"]
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
