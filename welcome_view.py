"""Empat mode tampilan untuk **sambutan** & **perpisahan** — tanpa AI, 0 kuota.

Mode mengikuti gaya dashboard bot hosting:

| Mode | Bentuk pesan | Butuh gambar kartu? |
| :--- | :--- | :--- |
| `card` | kartu PNG (banner + avatar + nama), dikirim sebagai lampiran | ya |
| `embed` | embed Discord biasa (judul, deskripsi, thumbnail avatar, banner) | tidak |
| `text` | teks polos — satu-satunya mode yang bisa me-*ping* member | tidak |
| `container` | kartu Components V2 (Container bertema) | tidak |

Catatan penting: **mention hanya hidup di luar embed**. Di dalam embed, `@nama`
hanya teks biasa; karena itu `text` dan `container` memakai `content` (boleh
`{user_mention}`), sedangkan `card` & `embed` tidak.

Modul ini murni fungsi: tidak menyimpan state, tidak menyentuh jaringan. State
(`view_mode`) tetap ada di `community_agent` / `welcome_media`.
"""

from __future__ import annotations

import io

import discord

import ui_kit

# Urutan = urutan tombol di dashboard (Card, Embed, Text, Container).
VIEW_MODES: dict[str, dict] = {
    "card": {
        "label": "Card",
        "emoji": "🖼️",
        "butuh_gambar": True,
        "mention": False,
        "catatan": "Kartu PNG: banner + foto profil bulat + nama & jumlah member.",
    },
    "embed": {
        "label": "Embed",
        "emoji": "🧱",
        "butuh_gambar": False,
        "mention": False,
        "catatan": "Embed biru bertema server. Tidak bisa me-ping member.",
    },
    "text": {
        "label": "Text",
        "emoji": "📝",
        "butuh_gambar": False,
        "mention": True,
        "catatan": "Teks biasa — satu-satunya mode yang bisa me-ping member.",
    },
    "container": {
        "label": "Container",
        "emoji": "🗂️",
        "butuh_gambar": False,
        "mention": True,
        "catatan": "Kartu Components V2 bertema server (gaya panel baru Discord).",
    },
}

MODE_BAWAAN = "text"


def normalisasi_mode(nilai: object) -> str:
    """Kunci mode yang sah; `text` bila kosong/tidak dikenal.

    Nama mode lama (`mati`, `statis`, `dinamis`) tetap diterima agar data
    setelan yang sudah tersimpan tidak perlu migrasi manual.
    """
    kunci = str(nilai or "").strip().lower()
    if kunci in VIEW_MODES:
        return kunci
    # Kompatibilitas data lama: mati→teks, statis→embed, dinamis→card.
    return {"mati": "text", "statis": "embed", "dinamis": "card"}.get(kunci, MODE_BAWAAN)


def label(nilai: object) -> str:
    """Label manusiawi sebuah mode (`Embed`, `Text`, …)."""
    return VIEW_MODES[normalisasi_mode(nilai)]["label"]


def butuh_gambar(nilai: object) -> bool:
    """Apakah mode ini bergantung pada gambar kartu yang diunggah."""
    return bool(VIEW_MODES[normalisasi_mode(nilai)]["butuh_gambar"])


# ==============================================================================
# PENGGANTI VARIABEL (tanpa AI — hanya format teks)
# ==============================================================================
def isi_variabel(
    teks: str,
    *,
    member=None,
    guild=None,
    member_count: int | None = None,
    limit: int = 3900,
) -> str:
    """Ganti `{user}`, `{user_name}`, `{user_mention}`, `{server}`, `{count}`, `{member_count}`.

    Aman untuk data kosong: variabel yang tidak bisa diisi dibiarkan apa adanya
    agar Admin melihat sendiri bagian yang salah ketik.
    """
    nama = str(getattr(member, "display_name", "") or getattr(member, "name", "") or "")
    mention = str(getattr(member, "mention", "") or "")
    nama_server = str(getattr(guild, "name", "") or "")
    jumlah = member_count
    if jumlah is None:
        jumlah = getattr(guild, "member_count", 0) or 0

    hasil = str(teks or "")
    peta = {
        "{user_mention}": mention or nama,
        "{user_name}": nama,
        "{user}": nama,
        "{server}": nama_server,
        "{member_count}": str(int(jumlah or 0)),
        "{count}": str(int(jumlah or 0)),
    }
    for kunci, nilai in peta.items():
        if nilai:
            hasil = hasil.replace(kunci, nilai)
    return hasil[:limit]


def template_bawaan(kind: str = "welcome") -> str:
    """Template setelan bawaan untuk sambutan / perpisahan."""
    if kind == "goodbye":
        return "Sampai jumpa, **{user_name}**! Terima kasih sudah menjadi bagian dari **{server}**."
    return "Selamat datang **{user_mention}** di **{server}**! Kamu member ke-{member_count} 🎉"


# ==============================================================================
# PERENDER SETIAP MODE
# ==============================================================================
def _judul(kind: str) -> str:
    return "👣 Sampai Jumpa!" if kind == "goodbye" else "👋 Selamat Datang!"


def _warna(guild_id: int | None):
    """Warna aksen tema server, dengan jaring aman."""
    try:
        return ui_theme.accent_color(guild_id)
    except Exception:  # pragma: no cover - tema belum siap
        return discord.Color.blurple()


def buat_embed(
    *,
    guild_id: int | None,
    guild,
    member,
    teks: str,
    kind: str = "welcome",
    footer: str = "",
    banner_bytes: bytes | None = None,
    banner_url: str | None = None,
    ekstra: list[str] | None = None,
) -> discord.Embed:
    """Embed klasik untuk mode `embed` (dan jalur cadangan mode `card`)."""
    embed = discord.Embed(
        title=_judul(kind),
        description=str(teks or "")[:3900],
        color=_warna(guild_id),
        timestamp=discord.utils.utcnow(),
    )
    avatar = getattr(member, "display_avatar", None)
    avatar_url = getattr(avatar, "url", None)
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    if banner_url:
        embed.set_image(url=banner_url)
    if ekstra:
        embed.add_field(name="ℹ️ Info", value="\n".join(ekstra)[:1024], inline=False)
    nama_server = str(getattr(guild, "name", "") or "")
    embed.set_footer(text=(footer or nama_server or kind)[:100])
    return embed


def buat_kartu_v2(
    *,
    guild_id: int | None,
    guild,
    member,
    teks: str,
    kind: str = "welcome",
    banner_url: str | None = None,
    ekstra: list[str] | None = None,
):
    """Kartu Components V2 (Container bertema) untuk mode `container`.

    Mengembalikan `None` bila pustaka tidak mendukung Components V2, sehingga
    pemanggil bisa mundur ke embed.
    """
    try:
        avatar = getattr(getattr(member, "display_avatar", None), "url", None)
        kepala = ui_kit.header(
            guild_id,
            "welcome" if kind != "goodbye" else "goodbye",
            _judul(kind),
            thumbnail_url=avatar,
        )
        baris = [kepala, ui_kit.text(str(teks or "")[:3000])]
        if ekstra:
            baris.append(ui_kit.sep())
            baris.append(ui_kit.text("\n".join(ekstra)[:1000]))
        nama_server = str(getattr(guild, "name", "") or "")
        jumlah = int(getattr(guild, "member_count", 0) or 0)
        kaki = f"-# {nama_server}" + (f" • member ke-{jumlah}" if jumlah else "")
        baris.append(ui_kit.text(kaki[:200]))
        return ui_kit.build_view(
            guild_id,
            ui_kit.card(guild_id, *baris, accent=_warna(guild_id)),
            timeout=None,
        )
    except Exception:  # pragma: no cover - wavelink/discord lama
        return None


def payload(
    mode: str,
    *,
    guild_id: int | None,
    guild,
    member,
    teks: str,
    kind: str = "welcome",
    footer: str = "",
    banner_file: discord.File | None = None,
    banner_url: str | None = None,
    kartu_bytes: bytes | None = None,
    kartu_nama: str = "kartu.png",
    ekstra: list[str] | None = None,
) -> dict:
    """Susun argumen `channel.send(**payload)` sesuai mode tampilan.

    Urutan cadangan bila mode tidak bisa dipakai:

    - `card` tanpa gambar kartu → `embed`
    - `container` ditolak pustaka → `embed`
    - `embed` selalu bisa
    - `text` selalu bisa
    """
    mode = normalisasi_mode(mode)

    if mode == "text":
        return {"content": str(teks or "")[:1900]}

    if mode == "container":
        view = buat_kartu_v2(
            guild_id=guild_id,
            guild=guild,
            member=member,
            teks=teks,
            kind=kind,
            banner_url=banner_url,
            ekstra=ekstra,
        )
        if view is not None:
            isi = {"view": view}
            # Mention hanya hidup di `content` (di luar container), jadi kirim
            # mention sebagai baris pembuka bila templatenya memang memintanya —
            # baik masih berupa `{user_mention}` maupun sudah tersubstitusi.
            mention = str(getattr(member, "mention", "") or "")
            teks_str = str(teks or "")
            if mention and ("{user_mention}" in teks_str or mention in teks_str):
                isi["content"] = mention
            return isi
        mode = "embed"

    if mode == "card" and kartu_bytes:
        embed = buat_embed(
            guild_id=guild_id,
            guild=guild,
            member=member,
            teks=teks,
            kind=kind,
            footer=footer,
            banner_url=f"attachment://{kartu_nama}",
            ekstra=ekstra,
        )
        sumber = io.BytesIO(kartu_bytes) if isinstance(kartu_bytes, (bytes, bytearray)) else kartu_bytes
        return {
            "embed": embed,
            "file": discord.File(sumber, filename=kartu_nama),
        }

    # mode `embed`, atau `card` tanpa gambar kartu
    embed = buat_embed(
        guild_id=guild_id,
        guild=guild,
        member=member,
        teks=teks,
        kind=kind,
        footer=footer,
        banner_url=banner_url,
        ekstra=ekstra,
    )
    isi = {"embed": embed}
    if banner_file is not None:
        isi["file"] = banner_file
    return isi


# `ui_theme` diimpor di akhir agar modul ini tetap bisa diimpor lebih dulu
# oleh `ui_kit` (menghindari impor melingkar).
import ui_theme  # noqa: E402
