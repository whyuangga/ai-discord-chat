"""Panel **tampilan** sambutan & perpisahan — server-rendered, tanpa JS.

Menggantikan panel unggah "kartu sambutan" lama. Admin memilih salah satu dari
empat mode (Card / Embed / Text / Container), mengisi template teks dengan
variabel, lalu melihat **pratinjau langsung** bentuk pesannya.

Jalur tulis: `POST /api/aksi` dengan aksi `sambutan.tampilan` /
`sambutan.template` (dan padanan `pamit.*` untuk perpisahan).

0 kuota AI — modul ini hanya menyusun HTML dari setelan tersimpan.
"""

from __future__ import annotations

import dashboard_ui
import welcome_view

# (jenis, label bagian, judul panel, warna aksen pratinjau)
BAGIAN: tuple[tuple[str, str, str, str], ...] = (
    ("welcome", "sambutan", "👋 Sambutan member baru", "#5865f2"),
    ("goodbye", "perpisahan", "👣 Pesan perpisahan", "#4f545c"),
)

_VARIABEL = (
    ("{user_mention}", "mention member — **hanya jalan di mode Text & Container**"),
    ("{user_name}", "nama tampilan member"),
    ("{server}", "nama server"),
    ("{member_count}", "jumlah member saat ini"),
)


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _cfg(kind: str, guild_id: int) -> dict:
    """Setelan sambutan/perpisahan yang tersimpan (dict kosong bila belum ada)."""
    import community_agent

    pool = (
        community_agent.goodbye_agent_guilds
        if kind == "goodbye"
        else community_agent.welcome_agent_guilds
    )
    return dict((pool or {}).get(int(guild_id or 0)) or {})


def _mode_aktif(kind: str, cfg: dict) -> str:
    """Mode tersimpan; perpisahan lama (tanpa kunci) memakai `embed`."""
    bawaan = "embed" if kind == "goodbye" else "text"
    return welcome_view.normalisasi_mode(cfg.get("view_mode") or bawaan)


def _tombol_mode(kind: str, aktif: str) -> str:
    """Deretan tombol pilihan mode (Card / Embed / Text / Container)."""
    tombol = []
    for kunci, info in welcome_view.VIEW_MODES.items():
        kelas = "pilihan-mode aktif" if kunci == aktif else "pilihan-mode"
        tekan = ' aria-pressed="true"' if kunci == aktif else ""
        tombol.append(
            f'<button type="submit" name="value" value="{kunci}" class="{kelas}"{tekan}>'
            f'{info["emoji"]} {info["label"]}</button>'
        )
    return "".join(tombol)


def _pratinjau(
    *,
    kind: str,
    mode: str,
    teks: str,
    nama_server: str,
    nama_member: str,
    jumlah: int,
) -> str:
    """Pratinjau HTML bentuk pesan untuk mode terpilih.

    Ini tiruan tampilan Discord — bukan gambar; tujuannya agar Admin langsung
    tahu bedanya Card / Embed / Text / Container sebelum menyimpan.
    """
    info = welcome_view.VIEW_MODES.get(mode) or welcome_view.VIEW_MODES["text"]
    label = f'{info["emoji"]} {info["label"]}'
    catatan = (
        '<p class="muted">Mention member <b>tetap jalan</b> di mode ini.</p>'
        if info["mention"]
        else '<p class="muted">Di mode ini mention tampil sebagai teks — '
        "<b>tidak</b> me-ping member.</p>"
    )

    if mode == "text":
        isi = (
            '<div class="pratinjau-teks">'
            f"{dashboard_ui._esc(teks)}"
            "</div>"
        )
    elif mode == "container":
        isi = (
            '<div class="pratinjau-container">'
            f'<div class="pratinjau-judul">{dashboard_ui._esc(_judul(kind))}</div>'
            f'<div class="pratinjau-baris">{dashboard_ui._esc(teks)}</div>'
            f'<div class="pratinjau-kaki">-# {dashboard_ui._esc(nama_server)}'
            f" • member ke-{jumlah}</div>"
            "</div>"
        )
    elif mode == "card":
        inisial = dashboard_ui._esc((nama_member or "?")[:1].upper())
        isi = (
            '<div class="pratinjau-kartu">'
            f'<div class="pratinjau-avatar">{inisial}</div>'
            '<div class="pratinjau-isi">'
            f'<div class="pratinjau-judul">{dashboard_ui._esc(_judul(kind))}</div>'
            f'<div class="pratinjau-nama">{dashboard_ui._esc(nama_member)}</div>'
            f'<div class="pratinjau-baris">{dashboard_ui._esc(teks)}</div>'
            "</div></div>"
            '<p class="muted">Pratinjau kasar — kartu asli (PNG) dirender dengan foto '
            "profil asli & banner yang diunggah lewat <code>/agent banner</code>.</p>"
        )
    else:  # embed
        isi = (
            '<div class="pratinjau-embed">'
            f'<div class="pratinjau-judul">{dashboard_ui._esc(_judul(kind))}</div>'
            f'<div class="pratinjau-baris">{dashboard_ui._esc(teks)}</div>'
            f'<div class="pratinjau-kaki">{dashboard_ui._esc(nama_server)}</div>'
            "</div>"
        )

    peringatan = ""
    if info["butuh_gambar"]:
        peringatan = (
            '<p class="muted">⚠️ Mode <b>Card</b> butuh gambar kartu. Bila belum ada, '
            "bot otomatis mengirim Embed.</p>"
        )
    return (
        f'<div class="pratinjau-kotak"><div class="pratinjau-label">Pratinjau · {label}</div>'
        f"{isi}{catatan}{peringatan}</div>"
    )


def _judul(kind: str) -> str:
    return "👣 Sampai Jumpa!" if kind == "goodbye" else "👋 Selamat Datang!"


def _slot_banner(kind: str, gid: int, token: str) -> str:
    """Unggah / hapus gambar kartu untuk mode **Card**.

    Hanya ditampilkan untuk sambutan & perpisahan — mode Card memakai gambar ini
    sebagai latar kartu PNG. Pratinjau memakai `/api/kartu/<jenis>` yang butuh
    sesi (cookie), bukan token di URL.
    """
    import dashboard_unggah

    info = dashboard_unggah.kartu_info(gid).get(kind)
    if info:
        url = f"/api/kartu/{kind}?guild={int(gid)}"
        pratinjau = (
            f'<img src="{url}" alt="{dashboard_ui._esc(info["nama"])}" loading="lazy">'
            f'<div class="muted">{int(info["ukuran_kb"])} KB · {dashboard_ui._esc(info["dibuat"])}</div>'
        )
        hapus = (
            '<form method="post" action="/api/unggah" class="sebaris">'
            + dashboard_ui._hidden(gid, token, f"kartu.hapus:{kind}")
            + '<button type="submit" class="danger">Hapus gambar</button></form>'
        )
    else:
        pratinjau = (
            '<div class="kosong">Belum ada gambar</div>'
            '<div class="muted">Tanpa gambar, mode Card otomatis mengirim Embed.</div>'
        )
        hapus = ""

    return (
        '<div class="kartu-slot banner-card">'
        "<h5>🖼️ Gambar kartu (untuk mode Card)</h5>"
        f"{pratinjau}"
        '<form method="post" action="/api/unggah" class="formgrid" '
        'enctype="multipart/form-data">'
        + dashboard_ui._hidden(gid, token, f"kartu.simpan:{kind}")
        + dashboard_ui._medan_berkas("Gambar kartu (PNG/JPG/GIF/WEBP)", "banner")
        + '<button type="submit">Unggah gambar</button></form>'
        + f"{hapus}"
        '<p class="muted">Ukuran ideal <b>1024×420 px</b>, maksimal '
        f"{dashboard_unggah.batas_mb()} MB. Disimpan di server bot, jadi tidak "
        "kedaluwarsa seperti tautan CDN Discord.</p>"
        "</div>"
    )


def render_tampilan_block(bot, guild_id: int, token: str, *, hanya: tuple[str, ...] | None = None) -> str:
    """Panel tampilan sambutan/perpisahan untuk halaman 👋 Sambutan & pamit."""
    gid = int(guild_id or 0)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    nama_server = str(getattr(guild, "name", "") or "Server Ini")
    jumlah = int(getattr(guild, "member_count", 0) or 0) or 3

    bagian = ""
    for kind, kunci, judul, _warna in BAGIAN:
        if hanya is not None and kind not in hanya:
            continue
        cfg = _cfg(kind, gid)
        aktif = _mode_aktif(kind, cfg)
        template = str(cfg.get("template") or "") or welcome_view.template_bawaan(kind)
        teks_contoh = welcome_view.isi_variabel(
            template,
            member=_AnggotaContoh(nama_server),
            guild=guild,
            member_count=jumlah,
        )

        opsi_var = "".join(
            f"<li><code>{dashboard_ui._esc(nama)}</code> — {ket}</li>"
            for nama, ket in _VARIABEL
        )
        form = (
            '<form method="post" action="/api/aksi" class="formgrid">'
            + dashboard_ui._hidden(gid, token, f"{'pamit' if kind == 'goodbye' else 'sambutan'}.template")
            + '<div class="medan lebar-penuh"><label>Template teks</label>'
            f'<textarea name="value" rows="4" maxlength="1500">{dashboard_ui._esc(template)}</textarea>'
            "</div>"
            '<button type="submit">Simpan template</button></form>'
        )
        form_mode = (
            '<form method="post" action="/api/aksi" class="pemilih-mode">'
            + dashboard_ui._hidden(gid, token, f"{'pamit' if kind == 'goodbye' else 'sambutan'}.tampilan")
            + _tombol_mode(kind, aktif)
            + "</form>"
        )
        pratinjau = _pratinjau(
            kind=kind,
            mode=aktif,
            teks=teks_contoh,
            nama_server=nama_server,
            nama_member="Anggota Baru",
            jumlah=jumlah,
        )

        bagian += (
            f'<div class="sambutan-tampilan" id="p-{kunci}-tampilan">'
            f"<h4>{judul}</h4>"
            '<p class="muted">Pilih tampilan, isi template, lalu simpan. '
            "Pratinjau di bawah langsung menunjukkan bentuk pesannya.</p>"
            f"{form_mode}{pratinjau}{_slot_banner(kind, gid, token)}{form}"
            f'<ul class="daftar-variabel">{opsi_var}</ul>'
            "</div>"
        )

    if not bagian:
        return ""
    return (
        '<div class="subpanel" id="p-tampilan"><h3>🎨 Tampilan pesan</h3>'
        '<p class="muted">Empat mode siap pakai: <b>Card</b> (kartu PNG), <b>Embed</b>, '
        "<b>Text</b>, dan <b>Container</b> (Components V2). Tidak perlu AI — 0 kuota.</p>"
        f"{bagian}</div>"
    )


class _AnggotaContoh:
    """Anggota palsu untuk mengisi pratinjau (tanpa menyentuh Discord)."""

    def __init__(self, nama_server: str = ""):
        self.display_name = "Anggota Baru"
        self.name = self.display_name
        self.mention = "@Anggota Baru"
        self.display_avatar = None


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/aksi`)
# ==============================================================================
async def aksi_sambutan(bot, gid: int, aksi: str, nilai: str) -> tuple[bool, str] | None:
    """Simpan mode tampilan atau template. `None` bila aksi bukan milik panel ini."""
    aksi = str(aksi or "").strip().lower()
    if not (aksi.startswith("sambutan.") or aksi.startswith("pamit.")):
        return None

    import community_agent
    import welcome_media

    gid = int(gid or 0)
    kind = "goodbye" if aksi.startswith("pamit.") else "welcome"
    perintah, _, sisa = aksi.partition(".")
    label = "perpisahan" if kind == "goodbye" else "sambutan"

    if sisa == "tampilan":
        mode = welcome_view.normalisasi_mode(nilai)
        if kind == "goodbye":
            community_agent.set_goodbye_view_mode(gid, mode)
        else:
            cfg = (community_agent.welcome_agent_guilds or {}).get(gid)
            if cfg is None:
                return False, "Atur channel sambutan lebih dulu sebelum memilih tampilan."
            community_agent.set_welcome_card_mode(gid, mode)
        await community_agent.save_agent_config_to_disk()
        catatan = ""
        if welcome_view.butuh_gambar(mode) and not welcome_media.has_banner(gid):
            catatan = " Kartu belum diunggah, jadi bot akan mengirim Embed sampai gambarnya ada."
        return True, f"Tampilan {label} disimpan: **{welcome_view.label(mode)}**.{catatan}"

    if sisa == "template":
        cfg = (
            community_agent.goodbye_agent_guilds
            if kind == "goodbye"
            else community_agent.welcome_agent_guilds
        ).get(gid)
        if cfg is None:
            return False, f"Atur channel {label} lebih dulu sebelum mengisi template."
        isi = community_agent.set_template_greeting(gid, kind, nilai)
        await community_agent.save_agent_config_to_disk()
        if not isi:
            return True, f"Template {label} dikosongkan — bot memakai template bawaan."
        return True, f"Template {label} disimpan ({len(isi)} karakter)."

    return False, f"Aksi {label} `{sisa or '-'}` tidak dikenal."
