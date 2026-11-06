"""Penyusun HTML untuk panel admin dashboard (server-side, tanpa JavaScript).

Modul ini hanya **menggambar**: daftar setelan dari `dashboard_admin`, form
pengiriman embed/webhook, dan daftar konten yang bisa dihapus. Semua aksi tetap
dikirim ke `POST /api/aksi` atau `POST /api/kirim` yang memeriksa token.
"""

import html

import dashboard_admin
import dashboard_unggah

# Kunci yang butuh daftar channel kategori (bukan channel teks biasa).
KUNCI_KATEGORI = {"tiket.kategori"}


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _guild_channels(bot, guild_id: int) -> list | None:
    """Daftar channel server dari cache bot (None bila tidak tersedia)."""
    getter = getattr(bot, "get_guild", None)
    if not callable(getter):
        return None
    guild = getter(int(guild_id or 0))
    if guild is None:
        return None
    channels = [c for c in (getattr(guild, "channels", []) or []) if c is not None]
    return channels


def _guild_roles(bot, guild_id: int) -> list | None:
    getter = getattr(bot, "get_guild", None)
    if not callable(getter):
        return None
    guild = getter(int(guild_id or 0))
    if guild is None:
        return None
    roles = [r for r in (getattr(guild, "roles", []) or []) if r is not None]
    return roles


def pilihan_channel(bot, guild_id: int, *, kategori_saja: bool = False) -> list[tuple[str, str]]:
    """Opsi dropdown channel: `[("0", "— tidak dipakai —"), ("123", "#umum")]`."""
    opsi: list[tuple[str, str]] = [("0", "— tidak dipakai —")]
    channels = _guild_channels(bot, guild_id) or []
    if not channels:
        return opsi
    kategori = [c for c in channels if getattr(c, "type", None) and str(getattr(c.type, "name", "")) == "category"]
    if kategori_saja:
        kandidat = kategori
    else:
        kandidat = [c for c in channels if c not in kategori]
    for ch in sorted(kandidat, key=lambda c: (getattr(c, "position", 0), getattr(c, "name", ""))):
        nama = f"# {getattr(ch, 'name', 'channel')}" if kategori_saja else f"# {getattr(ch, 'name', 'channel')}"
        opsi.append((str(getattr(ch, "id", 0)), nama))
    return opsi


def pilihan_role(bot, guild_id: int) -> list[tuple[str, str]]:
    """Opsi dropdown role: `[("0", "— tidak dipakai —"), ("456", "@Member")]`."""
    opsi: list[tuple[str, str]] = [("0", "— tidak dipakai —")]
    for role in sorted(_guild_roles(bot, guild_id) or [], key=lambda r: -int(getattr(r, "position", 0) or 0)):
        if getattr(role, "is_default", False):
            continue
        opsi.append((str(getattr(role, "id", 0)), f"@ {getattr(role, 'name', 'role')}"))
    return opsi


def opsi_untuk(kunci: str, bot, guild_id: int) -> list[tuple[str, str]]:
    """Opsi dropdown untuk satu kunci setelan."""
    fitur = dashboard_admin.FITUR.get(kunci) or {}
    jenis = fitur.get("jenis")
    if jenis == "saklar":
        return list(dashboard_admin.SAKLAR_OPSI)
    if jenis == "pilihan":
        return list(fitur.get("opsi") or ())
    if jenis == "channel":
        return pilihan_channel(bot, guild_id, kategori_saja=kunci in KUNCI_KATEGORI)
    if jenis == "role":
        return pilihan_role(bot, guild_id)
    return []


def _nama_channel(bot, guild_id: int, cid: str) -> str:
    for value, label in pilihan_channel(bot, guild_id)[1:]:
        if value == str(cid):
            return label
    return ""


def kontrol_html(kunci: str, nilai: str, bot, guild_id: int) -> str:
    """Kontrol input untuk satu setelan (select / number / text)."""
    fitur = dashboard_admin.FITUR.get(kunci) or {}
    jenis = fitur.get("jenis")
    nama = f"nilai-{_esc(kunci)}"
    if jenis in ("saklar", "pilihan", "channel", "role"):
        opsi = opsi_untuk(kunci, bot, guild_id)
        ada = {value for value, _ in opsi}
        potongan = "".join(
            f'<option value="{_esc(value)}"{" selected" if str(value) == str(nilai) else ""}>'
            f"{_esc(label)}</option>"
            for value, label in opsi
        )
        if str(nilai) and str(nilai) not in ada:
            potongan += f'<option value="{_esc(nilai)}" selected>ID {_esc(nilai)} (di luar server ini)</option>'
        return f'<select name="value" id="{nama}">{potongan}</select>'
    if jenis == "angka":
        return (
            f'<input type="number" name="value" id="{nama}" min="0" step="1" '
            f'value="{_esc(nilai)}">'
        )
    placeholder = "mis. !" if kunci == "prefix" else ""
    return (
        f'<input type="text" name="value" id="{nama}" maxlength="120" '
        f'value="{_esc(nilai)}" placeholder="{_esc(placeholder)}">'
    )


def _baris_setelan(kunci: str, nilai: str, bot, guild_id: int, token: str) -> str:
    fitur = dashboard_admin.FITUR.get(kunci) or {}
    label = _esc(fitur.get("label") or kunci)
    bantuan = str(fitur.get("bantuan") or "")
    if (fitur.get("jenis") == "channel") and str(nilai) not in ("", "0"):
        nama = _nama_channel(bot, guild_id, nilai)
        if nama:
            bantuan = f"Sedang: `{nama}`. {bantuan}".strip()
    catatan = f'<div class="muted">{_esc(bantuan)}</div>' if bantuan else ""
    hidden = (
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
        f'<input type="hidden" name="action" value="set.{_esc(kunci)}">'
    )
    return (
        f'<form method="post" action="/api/aksi" class="kontrol">'
        f"{hidden}<label for=\"nilai-{_esc(kunci)}\">{label}</label>"
        f'{kontrol_html(kunci, nilai, bot, guild_id)}'
        f'<button type="submit">Simpan</button></form>{catatan}'
    )


def render_setelan_block(values: dict, bot, guild_id: int, token: str) -> str:
    """Semua grup setelan (5 panel) siap ditempel ke halaman dashboard."""
    bagian: list[str] = []
    for grup in dashboard_admin.GRUP:
        baris = "".join(
            _baris_setelan(kunci, str(values.get(kunci, "")), bot, guild_id, token)
            for kunci in grup["fitur"]
            if kunci in dashboard_admin.FITUR
        )
        if not baris:
            continue
        bagian.append(
            f'<div class="subpanel"><h3>{_esc(grup["judul"])}</h3>'
            f'<p class="muted">{_esc(grup.get("keterangan") or "")}</p>{baris}</div>'
        )
    if not bagian:
        return '<div class="muted">Belum ada setelan yang bisa diatur.</div>'
    return "".join(bagian)


def render_audit_block(entries: list[dict]) -> str:
    """Riwayat perubahan terakhir (dari `dashboard_admin.audit_terakhir`)."""
    if not entries:
        return '<div class="muted">Belum ada perubahan dari dashboard.</div>'
    daftar: list[str] = []
    for item in entries:
        tanda = "✅" if item.get("ok") else "⚠️"
        daftar.append(
            f'<li>{tanda} <code>{_esc(item.get("aksi"))}</code> = '
            f'<code>{_esc(item.get("nilai"))}</code>'
            f'<div class="muted">{_esc(item.get("waktu"))} • {_esc(item.get("pesan"))}</div></li>'
        )
    return f'<ul class="riwayat">{"".join(daftar)}</ul>'

# ==============================================================================
# FORM KIRIM PESAN / EMBED (webhook & embed)
# ==============================================================================
def opsi_banner(guild_id: int) -> str:
    """Opsi dropdown banner tersimpan (kosong bila belum ada unggahan)."""
    items = dashboard_unggah.daftar(guild_id)
    if not items:
        return '<option value="">(belum ada banner tersimpan)</option>'
    return '<option value="">(tidak pakai banner tersimpan)</option>' + "".join(
        f'<option value="{_esc(item["nama"])}">{_esc(item["nama"])} · '
        f'{int(item["ukuran_kb"])} KB</option>'
        for item in items
    )


def _medan_berkas(label: str, nama: str = "banner") -> str:
    return (
        f'<div class="medan"><label for="{nama}">{_esc(label)}</label>'
        f'<input type="file" name="{nama}" id="{nama}" '
        'accept="image/png,image/jpeg,image/gif,image/webp"></div>'
    )


def _hidden(guild_id: int, token: str, action: str) -> str:
    return (
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
        f'<input type="hidden" name="action" value="{_esc(action)}">'
    )


def _medan(label: str, nama: str, *, place: str = "", nilai: str = "", jenis: str = "text") -> str:
    if jenis == "textarea":
        kontrol = (
            f'<textarea name="{nama}" rows="4" maxlength="3500" '
            f'placeholder="{_esc(place)}">{_esc(nilai)}</textarea>'
        )
    else:
        kontrol = (
            f'<input type="{jenis}" name="{nama}" maxlength="400" '
            f'value="{_esc(nilai)}" placeholder="{_esc(place)}">'
        )
    return f'<div class="medan"><label for="{nama}">{_esc(label)}</label>{kontrol}</div>'


def render_kirim_block(bot, guild_id: int, token: str) -> str:
    """Form kirim pesan/embed, termasuk opsi identitas webhook kustom."""
    opsi_channel = "".join(
        f'<option value="{_esc(value)}">{_esc(label)}</option>'
        for value, label in pilihan_channel(bot, guild_id)[1:]
    ) or '<option value="0">(bot belum di server mana pun)</option>'
    return f"""
<form method="post" action="/api/kirim" class="formgrid" enctype="multipart/form-data">
  {_hidden(guild_id, token, "kirim")}
  <div class="medan"><label for="k-channel">Channel tujuan</label>
    <select name="channel" id="k-channel">{opsi_channel}</select></div>
  {_medan("Judul embed", "judul", place="kosongkan untuk pesan teks biasa")}
  {_medan("Isi pesan", "isi", place="Boleh variabel: {server.name}, {now_long}", jenis="textarea")}
  {_medan("Warna", "warna", place="#5865F2 / blurple / merah")}
  {_medan("Footer", "footer", place="mis. Diperbarui otomatis")}
  {_medan("URL gambar", "gambar", place="https://… (opsional)", jenis="url")}
  {_medan("Label tombol link", "tombol_label", place="mis. Buka situs")}
  {_medan("URL tombol link", "tombol_url", place="https://…", jenis="url")}
  {_medan("Identitas webhook", "identitas", place="mis. 📢 Pengumuman Server (kosong = kirim sebagai bot)")}
  {_medan("Avatar webhook", "avatar", place="https://… (opsional)", jenis="url")}
  {_medan_berkas("Unggah banner/gambar (opsional)")}
  <div class="medan"><label for="k-banner-tersimpan">…atau pakai banner tersimpan</label>
    <select name="banner_tersimpan" id="k-banner-tersimpan">{opsi_banner(guild_id)}</select></div>
  <button type="submit" class="ghost" name="pratinjau" value="1">👀 Pratinjau dulu</button>
  <button type="submit">Kirim sekarang</button>
</form>
<p class="muted">Tombol <b>Pratinjau dulu</b> menampilkan hasilnya (termasuk peringatan variabel/warna)
tanpa mengirim apa pun. Kalau “Identitas webhook” diisi, pesan dikirim lewat webhook channel itu
(nama &amp; avatar boleh beda dari bot). Tombol link hanya dipakai saat mengirim sebagai bot.
Banner yang diunggah disimpan ke <code>data/uploads/</code> sehingga bisa dipakai lagi.</p>
"""


# ==============================================================================
# FORM BUAT KONTEN
# ==============================================================================
def render_buat_block(bot, guild_id: int, token: str) -> str:
    """Tiga form pembuat konten: pengumuman terjadwal, tautan embed, panel menu."""
    opsi = "".join(
        f'<option value="{_esc(value)}">{_esc(label)}</option>'
        for value, label in pilihan_channel(bot, guild_id)[1:]
    ) or '<option value="0">(belum ada channel)</option>'
    return f"""
<div class="subpanel"><h3>⏰ Pengumuman terjadwal</h3>
<form method="post" action="/api/konten" class="formgrid">
  {_hidden(guild_id, token, "buat.pengumuman")}
  <div class="medan"><label for="p-channel">Channel tujuan</label>
    <select name="channel" id="p-channel">{opsi}</select></div>
  {_medan("Judul", "judul", place="Pengumuman")}
  {_medan("Isi", "isi", place="Teks pengumuman…", jenis="textarea")}
  {_medan("Jadwal", "jadwal", place="08:00 · mingguan senin 19:00 · setiap 3 jam")}
  <button type="submit">Buat pengumuman</button>
</form></div>

<div class="subpanel"><h3>🔗 Tautan embed (/l/&lt;kode&gt;)</h3>
<form method="post" action="/api/konten" class="formgrid">
  {_hidden(guild_id, token, "buat.tautan")}
  {_medan("Judul", "judul", place="Nama tautan")}
  {_medan("Deskripsi", "isi", place="Ringkasan singkat", jenis="textarea")}
  {_medan("URL tujuan", "url", place="https://…", jenis="url")}
  {_medan("URL gambar", "gambar", place="https://… (opsional)", jenis="url")}
  {_medan("Warna", "warna", place="#5865F2")}
  <button type="submit">Buat tautan</button>
</form></div>

<div class="subpanel"><h3>🧩 Panel menu</h3>
<form method="post" action="/api/konten" class="formgrid" enctype="multipart/form-data">
  {_hidden(guild_id, token, "buat.panel")}
  <div class="medan"><label for="pan-channel">Channel</label>
    <select name="channel" id="pan-channel">{opsi}</select></div>
  {_medan("Judul panel", "judul", place="Pusat Bantuan")}
  {_medan("Deskripsi", "isi", place="Pilih tombol di bawah…", jenis="textarea")}
  {_medan_berkas("Banner panel (opsional)")}
  <div class="medan"><label for="pan-banner">…atau pakai banner tersimpan</label>
    <select name="banner_tersimpan" id="pan-banner">{opsi_banner(guild_id)}</select></div>
  <button type="submit">Buat &amp; kirim panel</button>
</form>
<p class="muted">Tombol/role pada panel ditambahkan lewat <code>/menu tombol</code> di Discord.
Panel yang sudah terkirim bisa disegarkan dengan <code>/menu ubah</code>.</p></div>

<div class="subpanel"><h3>📝 Formulir (modal)</h3>
<form method="post" action="/api/konten" class="formgrid">
  {_hidden(guild_id, token, "buat.formulir")}
  <div class="medan"><label for="f-channel">Channel tujuan jawaban (opsional)</label>
    <select name="channel" id="f-channel">{opsi}</select></div>
  {_medan("Nama formulir", "judul", place="Pendaftaran Event")}
  {_medan("Kolom", "kolom", place="Nama | Asal kota | Alasan:panjang?", jenis="textarea")}
  {_medan("Penjelasan singkat", "isi", place="Isi formulir lalu tekan kirim", jenis="textarea")}
  {_medan("Warna", "warna", place="#5865F2")}
  <button type="submit">Buat formulir</button>
</form>
<p class="muted">Pisahkan kolom dengan <code>|</code> atau baris baru (maksimal 4–5 kolom).
Tambahkan <code>:panjang</code> untuk jawaban panjang dan <code>?</code> bila tidak wajib —
contoh: <code>Nama | Umur | Alasan:panjang?</code>. Pasang sebagai tombol panel lewat
<code>/menu form tombol</code>.</p></div>

<div class="subpanel"><h3>🚪 Pemicu saat member bergabung</h3>
<form method="post" action="/api/konten" class="formgrid">
  {_hidden(guild_id, token, "buat.pemicu")}
  <div class="medan"><label for="pr-channel">Channel pesan/thread</label>
    <select name="channel" id="pr-channel">{opsi}</select></div>
  {_medan("Alur", "alur", place="+role:123 > umum:Selamat datang {member.mention} > thread:sambutan", jenis="textarea")}
  {_medan("Umur akun minimal (hari)", "umur_akun", place="0", jenis="number")}
  <button type="submit">Pasang pemicu</button>
</form>
<p class="muted">Sintaks alur sama dengan <code>/menu alur</code>: <code>+role:id</code>, <code>-role:id</code>,
<code>umum:teks</code>, <code>pesan:teks</code>, <code>thread:nama</code>, <code>hapus</code>.</p></div>
"""


# ==============================================================================
# DAFTAR KONTEN (dengan tombol hapus)
# ==============================================================================
def _form_banner_panel(menu_id: str, guild_id: int, token: str) -> str:
    """Form kecil: ganti/hapus banner panel yang sudah terkirim."""
    unggah = (
        '<form method="post" action="/api/konten" class="banner-form" '
        'enctype="multipart/form-data">'
        + _hidden(guild_id, token, "banner.panel:" + str(menu_id))
        + '<input type="file" name="banner" accept="image/png,image/jpeg,image/gif,image/webp">'
        f'<select name="banner_tersimpan">{opsi_banner(guild_id)}</select>'
        '<button type="submit" class="ghost">Ganti banner</button></form>'
    )
    hapus = (
        '<form method="post" action="/api/konten">'
        + _hidden(guild_id, token, "hapusbanner.panel:" + str(menu_id))
        + '<button type="submit" class="ghost">Hapus banner</button></form>'
    )
    return '<div class="aksi-banner">' + unggah + hapus + "</div>"


def _tabel_konten(judul: str, jenis: str, items: list[dict], token: str, guild_id: int) -> str:
    if not items:
        return f'<div class="subpanel"><h3>{_esc(judul)}</h3><div class="muted">Belum ada.</div></div>'
    baris = ""
    for item in items:
        aksi = f"hapus.{jenis}:{item.get('id')}"
        tombol_jeda = ""
        if jenis == "pengumuman" and "aktif" in item:
            label = "Jeda" if item.get("aktif") else "Aktifkan"
            aksi_jeda = "jeda.pengumuman:" + str(item.get("id"))
            tombol_jeda = (
                '<form method="post" action="/api/konten">'
                + _hidden(guild_id, token, aksi_jeda)
                + f'<button type="submit" class="ghost">{label}</button></form>'
            )
        extra = ""
        if jenis == "panel" and item.get("terkirim"):
            extra = _form_banner_panel(str(item.get("id")), guild_id, token)
        baris += (
            f'<tr><td><b>{_esc(item.get("judul"))}</b>'
            f'<div class="muted">{_esc(item.get("ringkas") or "")}</div>{extra}</td>'
            f'<td class="aksi">{tombol_jeda}'
            f'<form method="post" action="/api/konten">{_hidden(guild_id, token, aksi)}'
            '<button type="submit" class="danger">Hapus</button></form></td></tr>'
        )
    return (
        f'<div class="subpanel"><h3>{_esc(judul)}</h3>'
        f"<table><tbody>{baris}</tbody></table></div>"
    )


def render_banner_block(guild_id: int, token: str) -> str:
    """Panel unggah banner + galeri thumbnail dengan tombol hapus."""
    items = dashboard_unggah.daftar(guild_id)
    unggah = f"""
<form method="post" action="/api/unggah" class="formgrid" enctype="multipart/form-data">
  {_hidden(guild_id, token, "unggah.simpan")}
  {_medan_berkas("Berkas gambar (PNG/JPG/GIF/WEBP)")}
  <button type="submit">Unggah banner</button>
</form>
<p class="muted">Maksimal {dashboard_unggah.batas_mb()} MB per berkas, {dashboard_unggah.MAX_PER_GUILD}
banner per server. Semua berkas diperiksa isinya (bukan hanya ekstensi).</p>
"""
    if not items:
        return unggah + '<div class="muted">Belum ada banner tersimpan.</div>'
    kartu = ""
    for item in items:
        nama = item["nama"]
        # `guild` wajib ikut supaya pratinjau memakai server yang sama dengan halaman.
        url = (
            f"/api/unggahan/{_esc(nama)}?token={_esc(token)}&amp;guild={int(guild_id or 0)}"
        )
        kartu += (
            f'<div class="kartu-banner">'
            f'<img src="{url}" alt="{_esc(nama)}" loading="lazy">'
            f'<div class="muted">{int(item["ukuran_kb"])} KB · {_esc(item["dibuat"])}</div>'
            f'<code class="kecil">{_esc(nama)}</code>'
            f'<form method="post" action="/api/unggah">'
            f'{_hidden(guild_id, token, "hapus.banner:" + nama)}'
            '<button type="submit" class="danger">Hapus</button></form></div>'
        )
    return unggah + f'<div class="galeri">{kartu}</div>'


def render_konten_block(guild_id: int, konten: dict, token: str) -> str:
    """Daftar pengumuman/tautan/panel/formulir/webhook + tombol hapus."""
    return "".join(
        [
            _tabel_konten("⏰ Pengumuman", "pengumuman", konten.get("pengumuman") or [], token, guild_id),
            _tabel_konten("🔗 Tautan embed", "tautan", konten.get("tautan") or [], token, guild_id),
            _tabel_konten("🧩 Panel", "panel", konten.get("panel") or [], token, guild_id),
            _tabel_konten("📝 Formulir", "formulir", konten.get("formulir") or [], token, guild_id),
            _tabel_konten("🚪 Pemicu gabung", "pemicu", konten.get("pemicu") or [], token, guild_id),
            _tabel_konten("🪄 Webhook identitas", "webhook", konten.get("webhook") or [], token, guild_id),
        ]
    )

# ==============================================================================
# PEMILIH SERVER (tanpa login — cukup token pemilik instance)
# ==============================================================================
def daftar_server(bot) -> list[tuple[str, str]]:
    """Semua server tempat bot berada: `[(guild_id, nama)]`, urut nama."""
    daftar: list[tuple[str, str]] = []
    for guild in getattr(bot, "guilds", []) or []:
        try:
            daftar.append((str(int(getattr(guild, "id", 0))), str(getattr(guild, "name", "") or "-")))
        except Exception:  # pragma: no cover - jaring aman
            continue
    return sorted(daftar, key=lambda item: item[1].lower())


def render_guild_picker(bot, guild_id: int, token: str) -> str:
    """Dropdown pilih server (form GET biasa, tanpa JavaScript)."""
    daftar = daftar_server(bot)
    if not daftar:
        return '<div class="muted">Bot belum berada di server mana pun.</div>'
    if len(daftar) == 1:
        return f'<span class="muted">Server: <b>{_esc(daftar[0][1])}</b></span>'
    opsi = "".join(
        f'<option value="{_esc(gid)}"{" selected" if str(gid) == str(guild_id) else ""}>'
        f"{_esc(nama)}</option>"
        for gid, nama in daftar
    )
    return (
        '<form method="get" action="/" class="pemilih-server">'
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        '<label for="pilih-server">Server</label>'
        f'<select name="guild" id="pilih-server">{opsi}</select>'
        '<button type="submit">Buka</button></form>'
    )


# ==============================================================================
# GRAFIK TREN (SVG server-side, tanpa JavaScript)
# ==============================================================================
def render_tren_svg(rows: list[dict], *, judul: str = "Operasi AI", tinggi: int = 150) -> str:
    """Grafik batang sederhana dari `[{label, total, cache_hits}]`."""
    data = [row for row in (rows or []) if isinstance(row, dict)]
    if not data:
        return '<div class="muted">Belum ada data tren.</div>'
    puncak = max([max(int(r.get("total") or 0), int(r.get("cache_hits") or 0)) for r in data] + [1])
    lebar = 640
    padding_bawah = 26
    area = tinggi - padding_bawah
    lebar_bar = lebar / max(1, len(data))
    batang: list[str] = []
    for index, row in enumerate(data):
        total = int(row.get("total") or 0)
        cache = int(row.get("cache_hits") or 0)
        x = index * lebar_bar + 6
        w = max(6, lebar_bar - 18)
        h_total = max(0, round(total / puncak * (area - 14)))
        h_cache = max(0, round(cache / puncak * (area - 14)))
        y_total = area - h_total
        y_cache = area - h_cache
        belakang = ""
        if cache:
            belakang = (
                f'<rect x="{x + w / 2 - 3:.1f}" y="{y_cache}" width="6" height="{h_cache}" '
                'rx="3" fill="#58d68d" opacity="0.85"/>'
            )
        batang.append(
            belakang
            + f'<rect x="{x}" y="{y_total}" width="{w:.1f}" height="{h_total}" '
            'rx="4" fill="#5865f2"/>'
            + (f'<text x="{x + w / 2:.1f}" y="{y_total - 4}" class="nilai">{total}</text>'
               if total else "")
            + f'<text x="{x + w / 2:.1f}" y="{tinggi - 8}" class="sumbu">'
            f'{_esc(str(row.get("label") or ""))}</text>'
        )
    return (
        f'<div class="grafik"><div class="muted">{_esc(judul)} · puncak {puncak}/hari · '
        '<span style="color:#5865f2">■</span> operasi '
        '<span style="color:#58d68d">■</span> cache</div>'
        f'<svg viewBox="0 0 {lebar} {tinggi}" role="img" aria-label="Grafik {_esc(judul)}" '
        'preserveAspectRatio="none">'
        '<style>.grafik text{font-size:11px;fill:#8b90a3;font-family:system-ui,sans-serif}'
        '.grafik text.nilai{fill:#cbd0e0;font-size:10px}.grafik text.sumbu{text-anchor:middle}'
        '.grafik rect{x:0}</style>'
        f'<line x1="0" y1="{area}" x2="{lebar}" y2="{area}" stroke="#2a2f3d" stroke-width="1"/>'
        + "".join(batang)
        + "</svg></div>"
    )


# ==============================================================================
# PRATINJAU EMBED (sebelum dikirim)
# ==============================================================================
def _gaya_warna(hex_warna: str) -> str:
    teks = str(hex_warna or "").strip()
    if teks.startswith("#") and len(teks) in (4, 7):
        return _esc(teks)
    return "#5865f2"


def render_pratinjau_html(
    *,
    pratinjau: dict,
    token: str,
    guild_id: int,
    fields: dict,
    base: str = "",
) -> str:
    """Halaman pratinjau: tampilan mirip Discord + tombol “Kirim sekarang”.

    `fields` = isian form asli yang dikirim balik lewat input tersembunyi sehingga
    pengguna tidak perlu mengetik ulang.
    """
    data = pratinjau or {}
    warna = _gaya_warna(str(data.get("warna") or ""))
    identitas = str(data.get("identitas") or "").strip()
    judul = str(data.get("judul") or "").strip()
    isi = str(data.get("isi") or "").strip()
    footer = str(data.get("footer") or "").strip()
    gambar = str(data.get("gambar") or "").strip()
    tombol = str(data.get("tombol_label") or "").strip()
    tombol_url = str(data.get("tombol_url") or "").strip()

    bagian: list[str] = []
    if judul:
        bagian.append(f'<div class="p-judul">{_esc(judul)}</div>')
    if isi:
        bagian.append(f'<div class="p-isi">{_esc(isi)}</div>')
    if gambar:
        bagian.append(
            f'<img class="p-gambar" src="{_esc(gambar)}" alt="gambar embed">'
        )
    if footer:
        bagian.append(f'<div class="p-footer">{_esc(footer)}</div>')
    if tombol and tombol_url:
        bagian.append(
            f'<div class="p-tombol">{_esc(tombol)}</div>'
        )

    kartu = (
        f'<div class="p-kartu" style="border-left-color:{warna}">'
        + ("".join(bagian) or '<div class="muted">(kosong)</div>')
        + "</div>"
    )
    pengirim = (
        f'<div class="p-pengirim">{_esc(identitas)} <span class="muted">via webhook</span></div>'
        if identitas else '<div class="p-pengirim">Bot <span class="muted">via bot</span></div>'
    )
    peringatan = data.get("peringatan") or []
    blok_peringatan = ""
    if peringatan:
        butir = "".join(f"<li>{_esc(p)}</li>" for p in peringatan)
        blok_peringatan = f'<div class="p-peringatan"><b>Perlu diperiksa:</b><ul>{butir}</ul></div>'

    rahasia = "".join(
        f'<input type="hidden" name="{_esc(kunci)}" value="{_esc(nilai)}">'
        for kunci, nilai in (fields or {}).items()
    )
    tujuan = _esc(str(data.get("channel_label") or "channel"))

    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pratinjau embed — dashboard</title>
<style>
 body {{ margin:0; padding:20px; font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
        background:#0f1117; color:#e6e6f0; }}
 h1 {{ font-size:18px; margin:0 0 4px; }}
 .muted {{ color:#8b90a3; font-size:12px; }}
 .p-pengirim {{ font-size:13px; margin:18px 0 6px; color:#cbd0e0; }}
 .p-kartu {{ background:#2b2d31; border-left:4px solid #5865f2; border-radius:6px;
            padding:12px 14px; max-width:520px; }}
 .p-judul {{ font-weight:600; margin-bottom:6px; }}
 .p-isi {{ white-space:pre-wrap; font-size:14px; line-height:1.45; }}
 .p-gambar {{ width:100%; border-radius:6px; margin-top:8px; }}
 .p-footer {{ font-size:11px; color:#b5bac1; margin-top:8px; }}
 .p-tombol {{ margin-top:10px; display:inline-block; background:#4e5058; color:#fff;
             padding:6px 12px; border-radius:4px; font-size:13px; }}
 .p-peringatan {{ margin:14px 0; background:#3a2d17; border:1px solid #6b4d17;
                 border-radius:8px; padding:10px 12px; font-size:13px; }}
 .p-peringatan ul {{ margin:6px 0 0 18px; }}
 .aksi {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:18px; }}
 button, a.tombol {{ padding:9px 16px; border-radius:8px; border:1px solid #5865f2;
      background:#5865f2; color:#fff; font-size:14px; text-decoration:none; cursor:pointer; }}
 a.kembali {{ background:transparent; border-color:#3a4152; color:#cbd0e0; }}
</style></head><body>
<h1>👀 Pratinjau embed</h1>
<div class="muted">Tujuan: {tujuan} · belum ada yang dikirim</div>
{pengirim}
{kartu}
{blok_peringatan}
<form method="post" action="/api/kirim">
  {rahasia}
  <div class="aksi">
    <button type="submit">Kirim sekarang</button>
    <a class="tombol kembali" href="/?token={_esc(token)}&amp;guild={int(guild_id or 0)}">Kembali ubah</a>
  </div>
</form>
</body></html>"""



__all__ = [
    "daftar_server",
    "kontrol_html",
    "opsi_banner",
    "opsi_untuk",
    "pilihan_channel",
    "pilihan_role",
    "render_audit_block",
    "render_banner_block",
    "render_buat_block",
    "render_guild_picker",
    "render_konten_block",
    "render_kirim_block",
    "render_pratinjau_html",
    "render_setelan_block",
    "render_tren_svg",
]
