"""Bagian murni dashboard: konstanta halaman, anchor, auto-refresh, dan URL.

Semua isi berkas ini bebas dari `aiohttp` dan dari instance bot — bisa diuji
tanpa menyalakan server. Dipakai oleh `web_dashboard` (inti), `web_dashboard.rute`
(handler HTTP), dan `web_dashboard.tampilan` (perakitan HTML).
"""

from __future__ import annotations

import html
from urllib.parse import urlencode

import dashboard_admin


_ANCHOR_GRUP: dict[str, str] = {
    "inti": "p-inti",
    "tiket": "p-tiket",
    "sambutan": "p-welcome",
    "keamanan": "p-keamanan",
    "bantuan": "p-tiket",
    "konten": "p-konten",
}
_ANCHOR_BAGIAN: tuple[tuple[str, str], ...] = (
    ("sambutan.", "p-welcome"),
    ("pamit.", "p-goodbye"),
    ("boost.", "p-boost"),
)
def _anchor_aksi(aksi: str) -> str:
    """Panel tujuan setelah submit: halaman grup, bagian sambutan, atau kontrol cepat."""
    kunci = str(aksi or "").strip().lower()
    if kunci.startswith("set."):
        nama = kunci[len("set."):]
        for awalan, anchor in _ANCHOR_BAGIAN:
            if nama.startswith(awalan):
                return anchor
        return _ANCHOR_GRUP.get(HALAMAN_SETELAN.get(nama, ""), "p-inti")
    # Panel tampilan sambutan/perpisahan: kembali ke bagian yang bersangkutan.
    for awalan, anchor in _ANCHOR_BAGIAN:
        if kunci.startswith(awalan):
            return anchor
    # Aksi lain (sakelar level/ekonomi/pertumbuhan) ada di halaman Inti.
    return "p-kontrol"
def _anchor_konten(aksi: str) -> str:
    """Panel tujuan untuk aksi konten (buat/hapus/banner)."""
    kunci = str(aksi or "").strip().lower()
    if kunci.startswith(("banner.", "hapusbanner.")):
        return "p-konten"
    if kunci.startswith("hapus."):
        return "p-konten"
    if kunci.startswith("unggah."):
        return "p-banner"
    if kunci.startswith("inbox-"):
        return "p-form-inbox"
    if kunci.startswith("info-"):
        return "p-info"
    if kunci.startswith("voice-"):
        return "p-voice"
    if kunci.startswith("sosial-"):
        return "p-sosial"
    if kunci.startswith("curhat-"):
        return "p-curhat"
    if kunci.startswith("pantau-"):
        return "p-pantau"
    if kunci.startswith("stats-"):
        return "p-statistik"
    if kunci.startswith("tag-"):
        return "p-tag"
    if kunci.startswith("starboard-"):
        return "p-konten"
    return "p-buat"
def _teks_pesan(pesan: str) -> str:
    """Escape HTML lalu ubah `**tebal**` menjadi <b> (pesan bot memakai markdown)."""
    aman = html.escape(str(pesan or "").strip())
    bagian = aman.split("**")
    if len(bagian) < 3:
        return aman
    hasil = bagian[0]
    for urutan, potongan in enumerate(bagian[1:], start=1):
        hasil += (f"<b>{potongan}</b>" if urutan % 2 else potongan)
    return hasil
def _flash_box(pesan: str, ok: bool = True) -> str:
    """Kotak pesan setelah submit (pengganti halaman hasil terpisah)."""
    teks = str(pesan or "").strip()
    if not teks:
        return ""
    kelas = "flash" if ok else "flash galat"
    tanda = "✅" if ok else "⚠️"
    return f'<div class="{kelas}">{tanda} {_teks_pesan(teks)}</div>'
COOKIE_AUTO = "dash_auto"
COOKIE_AUTO_MAKS = 60 * 60 * 24 * 30   # 30 hari
def detik_auto(request, bawaan: int = 30) -> int:
    """Interval auto-refresh yang dipakai: cookie dulu, lalu `DASHBOARD_REFRESH_SEC`."""
    simpan = str(request.cookies.get(COOKIE_AUTO) or "").strip()
    if simpan.isdigit():
        return max(0, min(3600, int(simpan)))
    return max(0, min(3600, int(bawaan or 0)))
PILIHAN_AUTO: tuple[tuple[int, str], ...] = (
    (0, "⏸ Mati"),
    (60, "1 menit"),
    (600, "10 menit"),
    (1800, "30 menit"),
    (3600, "1 jam"),
)
FIELD_AUTO_MANUAL = "refresh_detik"
BATAS_AUTO = (0, 3600)
def detik_dari_kueri(kueri) -> str:
    """Nilai mentah auto-refresh dari query: kotak angka dulu, lalu dropdown.

    Hasilnya salah satu dari:
    - `"auto"` → ikut `DASHBOARD_REFRESH_SEC` (cookie dihapus),
    - `"manual"` → dropdown memilih “✏️ Isi sendiri…” tapi angkanya belum ada,
    - atau angka detik sebagai string (di luar 0–3600 dipotong, bukan ditolak,
      supaya tidak pernah ada form buntu).
    """
    bawah, atas = BATAS_AUTO
    manual = str(kueri.get(FIELD_AUTO_MANUAL) or "").strip()
    pilihan = str(kueri.get("refresh") or "").strip().lower()
    if manual.lstrip("+-").isdigit():
        return str(max(bawah, min(atas, int(manual))))
    if manual:
        # Ada isian tapi bukan angka → jangan ubah apa pun, tampilkan kotaknya lagi.
        return "manual"
    if pilihan in ("manual", "isi", "custom"):
        return "manual"
    if not pilihan or pilihan in ("auto", "bawaan", "env"):
        return "auto"
    if pilihan.lstrip("+-").isdigit():
        return str(max(bawah, min(atas, int(pilihan))))
    return "0"
def _label_auto(detik: int) -> str:
    """Label manusiawi untuk angka detik (mis. 45 → “45 detik”, 3600 → “1 jam”)."""
    for nilai, label in PILIHAN_AUTO:
        if nilai == detik:
            return label
    if detik >= 60 and detik % 60 == 0:
        menit = detik // 60
        return f"{menit} menit"
    return f"{detik} detik"
def form_auto(aksi: str, token: str = "", guild_id: int = 0,
              detik: int = 30, dipilih: str = "") -> str:
    """Pengatur “🔄 Auto-refresh” di header — **satu dropdown**, tanpa `.env`.

    Isi dropdown: `⏸ Mati` · `1 menit` · `10 menit` · `30 menit` · `1 jam` ·
    `✏️ Isi sendiri…` · `Ikut .env`. Pilih “Isi sendiri” lalu tekan **Set** →
    halaman dimuat ulang dengan kotak angka detik (0–3600) di dalam form yang
    sama, jadi header tetap ringkas dan angkanya tetap bebas.

    `dipilih` boleh `"auto"` (ikut `DASHBOARD_REFRESH_SEC`), `"manual"`, atau
    angka detik; angka di luar daftar otomatis tampil sebagai mode “Isi sendiri”
    dengan angkanya sudah terisi (pilihan aktif tidak pernah “hilang”).
    """
    if not str(aksi or "").strip():
        return ""
    angka_daftar = {str(nilai) for nilai, _ in PILIHAN_AUTO}
    dipilih = str(dipilih if str(dipilih or "").strip() else max(0, int(detik or 0))).lower()
    manual = ""
    if dipilih in ("manual", "isi", "custom"):
        pilih = "manual"
    elif dipilih.isdigit() and dipilih not in angka_daftar:
        pilih, manual = "manual", dipilih          # angka bebas → mode isi sendiri
    else:
        pilih = dipilih
    opsi = "".join(
        f'<option value="{nilai}"{" selected" if str(nilai) == pilih else ""}>{label}</option>'
        for nilai, label in PILIHAN_AUTO
    )
    opsi += f'<option value="manual"{" selected" if pilih == "manual" else ""}>✏️ Isi sendiri…</option>'
    opsi += f'<option value="auto"{" selected" if pilih == "auto" else ""}>Ikut .env</option>'
    kotak = ""
    if pilih == "manual":
        kotak = (
            f'<input type="number" name="{FIELD_AUTO_MANUAL}" id="input-auto"'
            f' min="{BATAS_AUTO[0]}" max="{BATAS_AUTO[1]}" step="5" inputmode="numeric"'
            f' value="{html.escape(manual, quote=True)}" placeholder="{max(0, int(detik or 0))}"'
            ' aria-label="Interval auto-refresh dalam detik"'
            ' title="Isi sendiri: detik, mis. 45" autofocus>'
            '<span class="muted satuan">detik</span>'
        )
    return (
        f'<form method="get" action="{html.escape(aksi, quote=True)}" class="pemilih-auto">'
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
        '<label for="pilih-auto">🔄 Auto-refresh</label>'
        '<select name="refresh" id="pilih-auto" aria-label="Interval auto-refresh">'
        f"{opsi}</select>"
        f"{kotak}"
        '<button type="submit">Set</button></form>'
    )
HALAMAN: tuple[dict, ...] = (
    {
        "slug": "",
        "menu": "📡 Ringkasan",
        "judul": "📡 Ringkasan",
        "keterangan": "Status bot, pemakaian AI, tren 7 hari, & papan peringkat.",
        "panel": ("p-status", "p-pemakaian", "p-jenis", "p-tren", "p-channel", "p-level"),
    },
    {
        "slug": "ai",
        "menu": "🤖 AI & Privasi",
        "judul": "🤖 AI & Privasi",
        "keterangan": "Buat gambar, atur kepribadian AI server, jalankan tes koneksi, dan ikuti jalur privasi mandiri.",
        "panel": ("p-gambar", "p-ai-settings", "p-privasi", "p-ai"),
    },
    {
        "slug": "sambutan",
        "menu": "👋 Sambutan & pamit",
        "judul": "👋 Sambutan & pamit",
        "keterangan": "Sambutan member baru, pesan perpisahan, dan ucapan boost — satu halaman.",
        "panel": ("p-sambutan",),
    },
    {
        "slug": "inti",
        "menu": "⚙️ Inti & level",
        "judul": "⚙️ Inti, level, & ekonomi",
        "keterangan": "Kontrol cepat + setelan level, ekonomi koin, pelacakan pertumbuhan, & prefix.",
        "panel": ("p-kontrol", "p-inti", "p-rank", "p-lencana"),
    },
    {
        "slug": "keamanan",
        "menu": "🛡️ Keamanan",
        "judul": "🛡️ Keamanan",
        "keterangan": "Anti-spam, anti-nuke, pengaman raid, verifikasi, & proteksi anti-phishing.",
        "panel": ("p-keamanan",),
    },
    {
        "slug": "moderasi",
        "menu": "🚨 Moderasi",
        "judul": "🚨 Moderasi",
        "keterangan": "Kasus moderasi, antrean laporan & banding, temp-ban, pencarian kasus, "
                      "dan statistik staf.",
        "panel": ("p-moderasi", "p-snipe"),
    },
    {
        "slug": "tiket",
        "menu": "🎫 Tiket & sapaan",
        "judul": "🎫 Tiket & sapaan harian",
        "keterangan": "Kotak masuk tiket, setelan tiket, & ucapan ulang tahun.",
        "panel": ("p-tiket",),
    },
    {
        "slug": "konten",
        "menu": "🧩 Konten & interaksi",
        "judul": "🧩 Konten & interaksi",
        "keterangan": "Fitur AI per channel, starboard, kotak saran, fakta harian, koran pagi, "
        "tag siap pakai, highlight kata kunci, & backup.",
        "panel": ("p-konten", "p-statistik"),
    },
    {
        "slug": "bangun",
        "menu": "🏗️ Bangun server",
        "judul": "🏗️ Bangun server",
        "keterangan": "Pilih tema 0 kuota AI atau rancang struktur dengan AI; tinjau sebelum menerapkan.",
        "panel": ("p-bangun",),
    },
    {
        "slug": "giveaway",
        "menu": "🎁 Giveaway",
        "judul": "🎁 Giveaway",
        "keterangan": "Buat, hentikan, & undi ulang giveaway; atur syarat berlapis & template.",
        "panel": ("p-giveaway",),
    },
    {
        "slug": "kirim",
        "menu": "✉️ Kirim",
        "judul": "✉️ Kirim pesan & banner",
        "keterangan": "Kirim pesan/embed, pratinjau dulu, dan unggah banner.",
        "panel": ("p-kirim", "p-banner"),
    },
    {
        "slug": "buat",
        "menu": "➕ Buat",
        "judul": "➕ Buat konten",
        "keterangan": "Pengumuman, tautan, panel, formulir, pemicu + daftar konten tersimpan "
        "& kotak masuk formulir.",
        "panel": ("p-buat", "p-form-inbox", "p-tersimpan"),
    },
    {
        "slug": "panel",
        "menu": "🎨 Panel",
        "judul": "🎨 Editor panel",
        "keterangan": "Tambah/hapus tombol & dropdown, segarkan panel, pasang gerbang verifikasi.",
        "panel": ("p-panel",),
    },
    {
        "slug": "ekspor",
        "menu": "📥 Ekspor",
        "judul": "📥 Ekspor & riwayat",
        "keterangan": "Unduh CSV (level, moderasi, tiket, pemakaian) & lihat riwayat perubahan.",
        "panel": ("p-ekspor", "p-riwayat"),
    },
)
HALAMAN_SLUG: dict[str, dict] = {h["slug"]: h for h in HALAMAN}
ANCHOR_HALAMAN: dict[str, str] = {
    anchor: h["slug"] for h in HALAMAN for anchor in h["panel"]
}
LEGACY_HALAMAN: dict[str, str] = {"uji": "ai", "setelan": "inti", "perpisahan": "sambutan",
                                  "boost": "sambutan"}

ANCHOR_HALAMAN.update({
    "p-kartu": "sambutan",
    "p-uji": "",
    "p-rank": "inti",
    "p-aturan": "keamanan",
    "p-honeypot": "keamanan",
    "p-tag": "konten",
    "p-pantau": "konten",
    "p-curhat": "konten",
    "p-sosial": "konten",
    "p-voice": "konten",
    "p-musik": "konten",
    "p-info": "konten",
    "p-form-inbox": "buat",
    "p-statistik": "konten",
    "p-setelan": "inti",
    "p-perpisahan": "sambutan",
    "p-boost": "sambutan",
    "p-welcome": "sambutan",
    "p-tampilan": "sambutan",
    "p-goodbye": "sambutan",
    "p-boost-slot": "sambutan",
})

SETELAN_SAMBUTAN: tuple[str, ...] = (
    "sambutan.channel", "sambutan.dm", "sambutan.kartu", "sambutan.persona",
    "sambutan.bahasa", "sambutan.arti",
)
SETELAN_PERPISAHAN: tuple[str, ...] = ("pamit.channel", "pamit.bahasa", "pamit.arti")
SETELAN_BOOST: tuple[str, ...] = ("boost.channel",)
GRUP_HALAMAN: dict[str, str] = {
    "inti": "inti",
    "sambutan": "sambutan",
    "keamanan": "keamanan",
    "bantuan": "tiket",
    "konten": "konten",
}
def fitur_grup(kunci_grup: str) -> tuple[str, ...]:
    """Daftar kunci setelan milik satu grup dashboard."""
    for grup in dashboard_admin.GRUP:
        if grup.get("kunci") == kunci_grup:
            return tuple(k for k in grup["fitur"] if k in dashboard_admin.FITUR)
    return ()
# Peta kunci setelan → slug halaman pemiliknya (dipakai form & anchor).
HALAMAN_SETELAN: dict[str, str] = {}
for _grup, _slug in GRUP_HALAMAN.items():
    for _kunci in fitur_grup(_grup):
        HALAMAN_SETELAN[_kunci] = _slug
for _kunci in SETELAN_SAMBUTAN + SETELAN_PERPISAHAN + SETELAN_BOOST:
    HALAMAN_SETELAN[_kunci] = "sambutan"
del _grup, _slug, _kunci

BAGIAN_SAMBUTAN: tuple[tuple[str, str, str, str], ...] = (
    ("welcome", "p-welcome", "👋 Sambutan member baru", "Dikirim saat ada member baru gabung."),
    ("goodbye", "p-goodbye", "👣 Pesan perpisahan", "Dikirim saat member keluar."),
    ("boost", "p-boost", "💎 Ucapan boost", "Dikirim saat member nge-boost server."),
)
KARTU_HALAMAN: dict[str, tuple[str, ...]] = {"sambutan": ("welcome", "goodbye", "boost")}
UJI_HALAMAN: dict[str, tuple[str, ...]] = {
    "": (),
    "ai": ("ai",),
    "buat": ("pengumuman", "formulir"),
    "panel": ("panel",),
    "tiket": ("tiket",),
    "konten": ("digest", "tag", "pantau", "curhat", "sosial", "statistik", "voice", "info"),
    "ekspor": ("ekspor",),
    "giveaway": ("giveaway",),
    "inti": ("kartu", "lencana"),
    "keamanan": ("honeypot", "verifikasi"),
    "moderasi": ("moderasi", "snipe"),
}
def _id_aman(nilai: object) -> int:
    """Angka dari form/URL tanpa pernah melempar `ValueError`."""
    try:
        return int(str(nilai).strip())
    except (TypeError, ValueError):
        return 0
def halaman_dari_path(path: str) -> str:
    """Slug halaman dari URL (`/` -> "", `/setelan` -> "setelan")."""
    slug = str(path or "").strip("/")
    return slug if slug in HALAMAN_SLUG else ""


def halaman_dari_anchor(anchor: str) -> str:
    """Halaman tempat sebuah panel (`p-tiket`, …) berada."""
    return ANCHOR_HALAMAN.get(str(anchor or "").strip(), "")


def url_halaman(slug: str, token: str = "", guild_id: int = 0) -> str:
    """Alamat satu halaman (server terbawa; token hanya bila memang diberikan).

    Sejak sesi memakai cookie, tautan internal dipanggil tanpa `token` sehingga
    parameter kosong (`?token=`) tidak pernah muncul di HTML maupun `Location:`.
    """
    dasar = f"/{slug}" if slug else "/"
    kueri: dict[str, object] = {}
    if str(token or "").strip():
        kueri["token"] = token
    kueri["guild"] = int(guild_id or 0)
    return f"{dasar}?{urlencode(kueri)}"


def render_menu(slug: str, token: str = "", guild_id: int = 0) -> str:
    """Menu utama: tautan antar-halaman, halaman aktif ditandai `aria-current`."""
    aktif = slug if slug in HALAMAN_SLUG else ""
    butir = []
    for halaman in HALAMAN:
        ini = halaman["slug"] == aktif
        tanda = ' aria-current="page"' if ini else ""
        tautan = html.escape(url_halaman(halaman["slug"], token, guild_id), quote=True)
        butir.append(f'<a href="{tautan}"{tanda}>{halaman["menu"]}</a>')
    return '<nav class="menu" aria-label="Halaman dashboard">' + "".join(butir) + "</nav>"
