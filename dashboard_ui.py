"""Penyusun HTML untuk panel admin dashboard (server-side, tanpa JavaScript).

Modul ini hanya **menggambar**: daftar setelan dari `dashboard_admin`, form
pengiriman embed/webhook, dan daftar konten yang bisa dihapus. Semua aksi tetap
dikirim ke `POST /api/aksi` atau `POST /api/kirim` yang memeriksa token.
"""

import html

import dashboard_admin
import channel_targets
import dashboard_tema
import dashboard_unggah
import tickets

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


def _opsi_html(daftar: list[tuple[str, str]], terpilih: str = "") -> str:
    """Rangkai `<option>` dari pasangan `(nilai, label)`."""
    hasil = ""
    for nilai, label in daftar:
        pilih = " selected" if str(nilai) == str(terpilih) else ""
        hasil += f'<option value="{_esc(nilai)}"{pilih}>{_esc(label)}</option>'
    return hasil


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
    if jenis == "channels":
        terpilih = {str(cid) for cid in channel_targets.parse(nilai)}
        kotak = "".join(
            '<label class="pilih-channel">'
            f'<input type="checkbox" name="value" value="{_esc(value)}"'
            f'{" checked" if str(value) in terpilih else ""}>'
            f"<span>{_esc(label)}</span></label>"
            for value, label in pilihan_channel(bot, guild_id)
            if str(value) != "0"
        )
        if not kotak:
            kotak = '<div class="muted">Belum ada channel yang bisa dipilih.</div>'
        # Channel yang tersimpan tapi sudah tidak ada di server tetap ditampilkan
        # (dan dicentang) supaya admin bisa melepasnya.
        tersedia = {str(value) for value, _ in pilihan_channel(bot, guild_id)}
        for cid in sorted(terpilih - tersedia):
            kotak += (
                '<label class="pilih-channel">'
                f'<input type="checkbox" name="value" value="{_esc(cid)}" checked>'
                f"<span>ID {_esc(cid)} (di luar server ini)</span></label>"
            )
        kosong = (
            '<label class="pilih-channel kosongkan">'
            '<input type="checkbox" name="value" value="0">'
            "<span>🚫 Kosongkan (matikan fitur)</span></label>"
        )
        return f'<div class="channel-grid" id="{nama}">{kotak}{kosong}</div>'
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
    if fitur.get("jenis") == "channels":
        jumlah = len(channel_targets.parse(nilai))
        bantuan = (
            f"Boleh pilih lebih dari satu channel ({jumlah} dipilih). {bantuan}"
            if jumlah
            else f"Belum ada channel dipilih. {bantuan}"
        ).strip()
    catatan = f'<div class="muted">{_esc(bantuan)}</div>' if bantuan else ""
    hidden = (
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
        f'<input type="hidden" name="action" value="set.{_esc(kunci)}">'
    )
    judul = (
        f'<div class="label-setelan">{label}</div>'
        if fitur.get("jenis") == "channels"
        else f"<label for=\"nilai-{_esc(kunci)}\">{label}</label>"
    )
    return (
        f'<form method="post" action="/api/aksi" class="kontrol">'
        f"{hidden}{judul}"
        f'{kontrol_html(kunci, nilai, bot, guild_id)}'
        f'<button type="submit">Simpan</button></form>{catatan}'
    )


def render_setelan_block(
    values: dict,
    bot,
    guild_id: int,
    token: str,
    *,
    hanya: tuple[str, ...] | None = None,
    kecuali_grup: tuple[str, ...] = (),
) -> str:
    """Grup setelan siap ditempel ke halaman dashboard.

    `hanya` membatasi ke beberapa kunci saja (dipakai halaman fitur seperti
    Sambutan/Perpisahan/Boost). `kecuali_grup` membuang grup yang sudah punya
    halaman sendiri supaya tidak tampil dua kali.
    """
    if hanya is not None:
        baris = "".join(
            _baris_setelan(kunci, str(values.get(kunci, "")), bot, guild_id, token)
            for kunci in hanya
            if kunci in dashboard_admin.FITUR
        )
        if not baris:
            return '<div class="muted">Belum ada setelan yang bisa diatur.</div>'
        # Tanpa pembungkus: pemanggil sudah menaruhnya di subpanel + <h3>.
        return baris
    bagian: list[str] = []
    for grup in dashboard_admin.GRUP:
        if grup.get("kunci") in kecuali_grup:
            continue
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


def _baris_kolom(jumlah: int = 5) -> str:
    """Baris visual kolom formulir: label, jenis, & centang wajib."""
    baris = ""
    for nomor in range(1, jumlah + 1):
        baris += (
            f'<div class="baris-kolom">'
            f'<input type="text" name="kolom_label_{nomor}" maxlength="45" '
            f'placeholder="Label kolom {nomor}">'
            f'<select name="kolom_jenis_{nomor}">'
            f'<option value="pendek">pendek</option>'
            f'<option value="panjang">paragraf</option></select>'
            f'<label class="centang"><input type="checkbox" name="kolom_wajib_{nomor}" '
            f'value="on" checked> wajib</label></div>'
        )
    return f'<div class="kolom-formulir">{baris}</div>'


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
  {_baris_kolom(5)}
  {_medan("Penjelasan singkat", "isi", place="Isi formulir lalu tekan kirim", jenis="textarea")}
  {_medan("Warna", "warna", place="#5865F2")}
  <details><summary class="muted">Mode lanjutan (tulis kolom sebagai teks)</summary>
    {_medan("Kolom", "kolom", place="Nama | Asal kota | Alasan:panjang?", jenis="textarea")}
  </details>
  <button type="submit">Buat formulir</button>
</form>
<p class="muted">Isi label kolom (maksimal 5). Pilih <b>paragraf</b> untuk jawaban panjang, dan
hilangkan centang <b>wajib</b> bila boleh dikosongkan. Mode lanjutan hanya dipakai bila semua
baris di atas kosong. Pasang formulir sebagai tombol panel lewat <code>/menu form tombol</code>.</p></div>

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


def _slot_kartu(
    guild_id: int,
    token: str,
    jenis: str,
    data: dict | None,
    label: str,
    tampilkan_judul: bool,
) -> str:
    """HTML satu slot kartu (pratinjau, form unggah, dan tombol hapus)."""
    if data:
        url = f"/api/kartu/{jenis}?token={_esc(token)}&amp;guild={int(guild_id or 0)}"
        pratinjau = f'<img src="{url}" alt="{_esc(data["nama"])}" loading="lazy">'
        keterangan = (
            f'<div class="muted">{int(data["ukuran_kb"])} KB · {_esc(data["dibuat"])}</div>'
            f'<code class="kecil">{_esc(data["nama"])}</code>'
        )
        hapus = (
            '<form method="post" action="/api/unggah">'
            f'{_hidden(guild_id, token, "kartu.hapus:" + jenis)}'
            '<button type="submit" class="danger">Hapus kartu</button></form>'
        )
    else:
        pratinjau = '<div class="kosong">Belum ada gambar</div>'
        keterangan = '<div class="muted">Bot memakai tampilan teks/embed biasa.</div>'
        hapus = ""

    judul = f"<h4>{_esc(label.capitalize())}</h4>" if tampilkan_judul else ""
    return (
        '<div class="kartu-slot">'
        f"{judul}{pratinjau}{keterangan}"
        '<form method="post" action="/api/unggah" class="formgrid" '
        'enctype="multipart/form-data">'
        f'{_hidden(guild_id, token, "kartu.simpan:" + jenis)}'
        f'{_medan_berkas("Gambar kartu (PNG/JPG/GIF/WEBP)", "banner")}'
        f'<button type="submit">Unggah kartu {_esc(label)}</button>'
        "</form>"
        f"{hapus}"
        "</div>"
    )


def _mode_kartu_sambutan(guild_id: int) -> str:
    """Mode tampilan kartu sambutan tersimpan (mati/statis/dinamis)."""
    try:
        import community_agent

        return str(
            ((community_agent.welcome_agent_guilds or {}).get(int(guild_id or 0)) or {})
            .get("card_mode")
            or "mati"
        )
    except Exception:  # pragma: no cover - jaring aman
        return "statis"


def render_kartu_block(
    guild_id: int,
    token: str,
    hanya: tuple[str, ...] | None = None,
) -> str:
    """Panel unggah kartu (disimpan di `data/media/`).

    `hanya` membatasi ke satu slot — halaman Sambutan hanya menampilkan kartu
    sambutan, halaman Perpisahan hanya kartu perpisahan, dan seterusnya.
    """
    info = dashboard_unggah.kartu_info(guild_id)
    jenis_dipakai = tuple(
        j
        for j in dashboard_unggah.JENIS_KARTU
        if (j in dashboard_unggah.KARTU_AGEN if hanya is None else j in hanya)
    )
    if not jenis_dipakai:
        return ""
    slot = ""
    for jenis in jenis_dipakai:
        slot += _slot_kartu(
            guild_id,
            token,
            jenis,
            info.get(jenis),
            dashboard_unggah.LABEL_KARTU[jenis],
            len(jenis_dipakai) > 1,
        )
    catatan_ukuran = (
        '<p class="muted">Ukuran ideal <b>1024×420 px</b>, maksimal '
        f"{dashboard_unggah.batas_mb()} MB (PNG/JPG/GIF/WEBP). Gambar disimpan di server bot, "
        "jadi tidak pernah kedaluwarsa seperti tautan CDN Discord.</p>"
    )

    if "welcome" not in jenis_dipakai:
        return f'<div class="kartu-sambutan tunggal">{slot}</div>' + catatan_ukuran

    mode = _mode_kartu_sambutan(guild_id)
    opsi = "".join(
        f'<option value="{nilai}"{" selected" if nilai == mode else ""}>{teks}</option>'
        for nilai, teks in (("mati", "💬 Teks saja"), ("statis", "🖼️ Kartu statis"),
                            ("dinamis", "✨ Kartu dinamis"))
    )
    pengaturan = (
        '<form method="post" action="/api/aksi" class="kontrol">'
        f'{_hidden(guild_id, token, "set.sambutan.kartu")}'
        '<label for="mode-kartu">Tampilan kartu sambutan</label>'
        f'<select name="value" id="mode-kartu">{opsi}</select>'
        '<button type="submit">Simpan mode</button></form>'
        '<p class="muted"><b>Teks saja</b> = pesan polos. <b>Kartu statis</b> = gambarmu '
        "dikirim apa adanya di dalam embed (+ foto profil kecil). <b>Kartu dinamis</b> = "
        "gambarmu jadi latar, lalu bot menambahkan foto profil bulat, nama member, dan "
        "“Member ke-N” di atasnya. Butuh gambar kartu yang sudah diunggah.</p>"
    )
    return f'<div class="kartu-sambutan">{slot}</div>{pengaturan}{catatan_ukuran}'


def render_honeypot_block(bot, guild_id: int, token: str) -> str:
    """Panel honeypot: pilih channel jebakan, tindakan, log, & statistik tangkapan."""
    import honeypot

    gid = int(guild_id or 0)
    data = honeypot.status(gid)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    kanal = list(getattr(guild, "text_channels", []) or [])[:80]
    opsi_jebakan = "".join(
        f'<option value="{int(getattr(ch, "id", 0))}"'
        f'{" selected" if int(getattr(ch, "id", 0)) in data["channel_ids"] else ""}>'
        f'#{_esc(getattr(ch, "name", "-"))}</option>'
        for ch in kanal
    ) or '<option value="0">(belum ada channel)</option>'
    opsi_log = '<option value="0">— tanpa log —</option>' + "".join(
        f'<option value="{int(getattr(ch, "id", 0))}"'
        f'{" selected" if int(getattr(ch, "id", 0)) == data["log_channel_id"] else ""}>'
        f'#{_esc(getattr(ch, "name", "-"))}</option>'
        for ch in kanal
    )
    opsi_aksi = "".join(
        f'<option value="{kunci}"{" selected" if kunci == data["aksi"] else ""}>'
        f"{_esc(teks)}</option>"
        for kunci, teks in honeypot.AKSI_HONEYPOT.items()
    )
    terakhir = data.get("terakhir") or {}
    jejak = (
        f'<p class="muted">Tangkapan terakhir: <b>{int(terakhir.get("user_id") or 0)}</b> di '
        f'channel <code>{int(terakhir.get("channel_id") or 0)}</code> · '
        f'aksi <code>{_esc(terakhir.get("aksi"))}</code></p>'
        if terakhir
        else ""
    )
    daftar = ", ".join(f"<code>#{cid}</code>" for cid in data["channel_ids"]) or "belum ada"
    lencana = (
        '<span class="lencana on">aktif</span>'
        if data["aktif"]
        else '<span class="lencana off">nonaktif</span>'
    )
    form = (
        '<form method="post" action="/api/keamanan" class="formgrid">'
        + _hidden(gid, token, "honeypot-simpan")
        + '<div class="medan"><label>Channel jebakan</label>'
        f'<select name="channel_id">{opsi_jebakan}</select></div>'
        f'<div class="medan"><label>Tindakan</label><select name="aksi">{opsi_aksi}</select></div>'
        '<div class="medan"><label>Lama time-out (detik, 60–86400)</label>'
        f'<input type="number" name="timeout_sec" min="60" max="86400" value="{int(data["timeout_sec"])}"></div>'
        f'<div class="medan"><label>Channel log</label><select name="log_channel_id">{opsi_log}</select></div>'
        '<div class="medan"><label>Abaikan staf</label><select name="abaikan_staf">'
        f'<option value="1"{" selected" if data["abaikan_staf"] else ""}>Ya — staf aman (disarankan)</option>'
        f'<option value="0"{" selected" if not data["abaikan_staf"] else ""}>Tidak — semua orang kena</option>'
        "</select></div>"
        '<button type="submit">Simpan honeypot</button></form>'
    )
    tombol_hapus = ""
    if data["aktif"] or data["channel_ids"]:
        tombol_hapus = (
            '<form method="post" action="/api/keamanan">'
            + _hidden(gid, token, "honeypot-hapus")
            + '<button type="submit" class="danger">Matikan &amp; hapus setelan</button></form>'
        )
    return (
        '<div class="subpanel" id="p-honeypot"><h3>🪤 Honeypot (channel jebakan)</h3>'
        '<p class="muted">Buat channel yang <b>tidak boleh dipakai siapa pun</b> (mis. '
        "<code>#promo-gratis</code>). Warga asli membaca aturan dan menjauh; skrip spam &amp; "
        "self-bot justru langsung menulis di sana. Pesan pertama sudah cukup jadi bukti — "
        "tanpa ambang dan tanpa salah tuduh.</p>"
        f'<p class="muted">Status: {lencana} · channel jebakan: {daftar} · tindakan '
        f'<b>{_esc(data["label_aksi"])}</b> · total tertangkap <b>{data["tangkap"]}</b> '
        f'· maks {data["batas_channel"]} channel</p>{jejak}{form}{tombol_hapus}</div>'
    )


def render_aturan_block(guild_id: int, token: str, data: dict) -> str:
    """Penguji aturan + statistik per aturan di halaman Keamanan."""
    import antispam

    gid = int(guild_id or 0)
    stat = data.get("statistik") or {}
    uji = data.get("uji") or None
    mode = str(stat.get("mode") or "lapor")
    label_mode = {
        "lapor": "👀 lapor saja",
        "hapus": "🧹 hapus pesan",
        "timeout": "⏳ hapus + time-out",
    }.get(mode, antispam.SPAM_MODES.get(mode, mode))

    baris_stat = ""
    for item in stat.get("aturan") or []:
        baris_stat += (
            f'<tr><td>{_esc(item.get("label"))}</td>'
            f'<td class="angka">{int(item.get("hari_ini") or 0)}</td>'
            f'<td class="angka">{int(item.get("total") or 0)}</td></tr>'
        )
    tabel_stat = (
        '<table><thead><tr><th>Aturan</th><th class="angka">Hari ini</th>'
        f'<th class="angka">Total</th></tr></thead><tbody>{baris_stat}</tbody></table>'
        if baris_stat
        else '<div class="muted">Belum ada statistik.</div>'
    )

    hasil = ""
    if uji:
        baris_uji = ""
        kena = set(uji.get("kena") or [])
        for item in uji.get("aturan") or []:
            tanda = "⚠️" if item.get("kena") else ("✅" if item.get("aktif") else "⏸️")
            status = (
                "<b>kena</b>"
                if item.get("kena")
                else ("aman" if item.get("aktif") else "nonaktif")
            )
            baris_uji += (
                f'<tr><td>{tanda} {_esc(item.get("label"))}</td>'
                f'<td>{status}</td>'
                f'<td class="muted">{_esc(item.get("detail"))}</td></tr>'
            )
        ringkas = (
            f"⚠️ <b>{len(kena)} aturan kena</b>: "
            + ", ".join(sorted(kena))
            if kena
            else "✅ <b>Tidak ada aturan yang kena</b> untuk teks ini."
        )
        contoh = _esc(str(uji.get("teks") or ""))[:400]
        hasil = (
            '<div class="subpanel"><h3>Hasil uji terakhir</h3>'
            f'<p>{ringkas} · simulasi dikirim <b>{int(uji.get("ulang") or 1)}×</b> · '
            f'mode tindakan sekarang: <b>{_esc(label_mode)}</b></p>'
            f'<p class="muted">Teks: <code>{contoh}</code></p>'
            '<table><thead><tr><th>Aturan</th><th>Status</th><th>Detail</th></tr></thead>'
            f"<tbody>{baris_uji}</tbody></table>"
            '<p class="muted">Penguji tidak menghapus pesan, tidak me-time-out siapa pun, '
            "dan tidak mengubah riwayat anti-spam.</p></div>"
        )

    form = (
        '<form method="post" action="/api/keamanan" class="formgrid">'
        + _hidden(gid, token, "uji-aturan")
        + '<div class="medan lebar"><label>Contoh pesan untuk diuji</label>'
        '<textarea name="teks" rows="4" maxlength="2000" required '
        'placeholder="Tempel isi pesan di sini (boleh berisi mention, link, CAPS, dsb.)">'
        "</textarea></div>"
        '<div class="medan"><label>Dibayangkan dikirim berapa kali</label>'
        '<input type="number" name="ulang" min="1" max="50" value="1"></div>'
        '<button type="submit">Uji sekarang (tanpa tindakan)</button></form>'
    )
    return (
        '<div class="subpanel" id="p-aturan"><h3>🧪 Penguji aturan &amp; statistik</h3>'
        '<p class="muted">Tempel teks, lihat aturan mana yang kena — <b>tanpa</b> '
        "menghapus pesan atau menghukum siapa pun. Angka “hari ini” menunjukkan aturan "
        "yang paling sering menangkap spam di server ini.</p>"
        f'<p class="muted">Status penjaga spam: '
        f'<b>{"aktif" if stat.get("aktif") else "nonaktif"}</b> · mode tindakan '
        f"<b>{_esc(label_mode)}</b> · total tertangkap <b>{int(stat.get('blocked') or 0)}</b> "
        f"· tanggal <code>{_esc(stat.get('hari') or '-')}</code></p>"
        f"{form}{hasil}"
        f'<div class="subpanel"><h3>Statistik per aturan</h3>{tabel_stat}</div>'
        "</div>"
    )


def render_starboard_block(bot, guild_id: int, token: str) -> str:
    """Pengelola papan sorotan (utama + varian) di halaman Konten & interaksi."""
    import community_tools

    gid = int(guild_id or 0)
    daftar = community_tools.list_starboard_boards(gid)
    opsi_channel = '<option value="0">— ikut channel papan utama —</option>'
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    for ch in list(getattr(guild, "text_channels", []) or [])[:80]:
        opsi_channel += (
            f'<option value="{int(getattr(ch, "id", 0))}">'
            f'#{_esc(getattr(ch, "name", "-"))}</option>'
        )

    if daftar:
        baris = ""
        for papan in daftar:
            lencana = (
                '<span class="lencana on">utama</span>'
                if papan.get("utama")
                else '<span class="lencana off">varian</span>'
            )
            hapus = ""
            if not papan.get("utama"):
                hapus = (
                    '<form method="post" action="/api/konten">'
                    + _hidden(gid, token, "starboard-hapus:" + str(papan.get("kunci")))
                    + '<button type="submit" class="danger">Hapus</button></form>'
                )
            warna = f" · warna `{_esc(papan.get('warna'))}`" if papan.get("warna") else ""
            baris += (
                '<div class="uji-baris"><div>'
                f'<b>{_esc(papan.get("emoji"))} {_esc(papan.get("nama"))}</b> {lencana}'
                f'<div class="muted">≥ {int(papan.get("threshold") or 0)} reaksi · '
                f'channel <code>{int(papan.get("channel_id") or 0)}</code> · '
                f'{int(papan.get("jumlah") or 0)} sorotan{warna}</div>'
                "</div>" + hapus + "</div>"
            )
        isi = f'<div class="daftar-papan">{baris}</div>'
    else:
        isi = (
            '<div class="muted">Starboard belum aktif. Pilih <b>Channel starboard</b> di '
            "setelan grup ini dulu, lalu tambahkan papan varian.</div>"
        )

    form = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + _hidden(gid, token, "starboard-tambah")
        + '<div class="medan"><label>Nama papan</label>'
        '<input type="text" name="nama" maxlength="40" placeholder="Skull" required></div>'
        '<div class="medan"><label>Emoji</label>'
        '<input type="text" name="emoji" maxlength="8" placeholder="💀"></div>'
        '<div class="medan"><label>Ambang reaksi</label>'
        '<input type="number" name="batas" min="1" max="50" placeholder="5"></div>'
        f'<div class="medan"><label>Channel papan</label>'
        f'<select name="channel_id">{opsi_channel}</select></div>'
        '<div class="medan"><label>Warna embed (hex)</label>'
        '<input type="text" name="warna" maxlength="7" placeholder="#FF8A00"></div>'
        "<button type=\"submit\">Simpan papan</button></form>"
    )
    return (
        '<div class="subpanel"><h3>🧩 Papan sorotan (varian)</h3>'
        '<p class="muted">Papan utama ⭐ jalan seperti biasa. Varian (mis. skullboard 💀, '
        "clownboard 🤡) punya emoji, ambang, channel, dan warna sendiri — semuanya bisa "
        f"hidup bersamaan, maksimal <b>{community_tools.STARBOARD_MAX_BOARD}</b> papan "
        "per server termasuk papan utama.</p>"
        f"{isi}{form}</div>"
    )


def render_kartu_rank_block(bot, guild_id: int, token: str) -> str:
    """Panel kartu rank PNG: pratinjau dari perender asli + latar unggahan + tes.

    Pratinjau memakai `GET /api/rank.png`, yaitu **fungsi render yang sama** dengan
    `/level kartu` — jadi yang terlihat di HP sama dengan yang dikirim bot.
    """
    import levels
    import rank_card

    gid = int(guild_id or 0)
    cfg = levels.peek_level_config(gid) or {}
    aktif = bool(cfg.get("kartu_aktif", True))
    warna = rank_card.hex_warna(cfg.get("kartu_warna"))
    latar = "gambar unggahan" if rank_card.ada_latar(gid) else "gradasi warna aksen"

    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    pemilik = int(getattr(guild, "owner_id", 0) or 0) if guild is not None else 0
    kueri = f"token={_esc(token)}&amp;guild={gid}"
    if pemilik:
        kueri += f"&amp;member={pemilik}"
    url = f"/api/rank.png?{kueri}"

    lencana = (
        '<span class="lencana on">aktif</span>' if aktif
        else '<span class="lencana off">mati</span>'
    )
    pratinjau = (
        f'<div class="kartu-rank"><img src="{url}" alt="Pratinjau kartu rank" '
        'loading="lazy">'
        '<div class="aksi-banner">'
        f'<a class="tombol-unduh" href="{url}&amp;unduh=1">Buka / unduh PNG</a></div>'
        "</div>"
        '<p class="muted">Pratinjau di atas dibuat oleh <b>perender yang sama</b> dengan '
        "`/level kartu` — bukan gambar contoh. Kartu dirender di server bot (Pillow), "
        "jadi <b>0 kuota AI</b>.</p>"
    )
    if not aktif:
        pratinjau = (
            '<div class="muted">Kartu rank sedang <b>dimatikan</b> — `/level kartu` akan '
            "menjawab dengan versi teks. Nyalakan lewat sakelar <b>Kartu rank PNG</b> "
            "di halaman ini.</div>"
        ) + pratinjau

    keterangan = (
        '<p class="muted">Status: '
        f"{lencana} · warna aksen: <code>{_esc(warna or 'ikut tema server')}</code> · "
        f"latar: {_esc(latar)}. Ukuran {rank_card.KARTU_UKURAN[0]}×"
        f"{rank_card.KARTU_UKURAN[1]} px.</p>"
    )
    unggah = render_kartu_block(gid, token, hanya=("rank",))
    tes = render_uji_block(bot, gid, token, hanya=("kartu",))
    return pratinjau + keterangan + unggah + (
        f'<div class="subpanel"><h3>🧪 Tes kartu rank</h3>{tes}</div>' if tes else ""
    )


def _opsi_channel_uji(guild) -> str:
    """Daftar `<option>` channel teks untuk kolom tes."""
    channel_opsi = ""
    for ch in list(getattr(guild, "text_channels", []) or [])[:60]:
        channel_opsi += f'<option value="{int(getattr(ch, "id", 0))}">#{_esc(getattr(ch, "name", "-"))}</option>'
    if not channel_opsi:
        channel_opsi = '<option value="0">(belum ada channel)</option>'
    return channel_opsi


def _opsi_orang_uji(dashboard_uji, guild) -> str:
    """Daftar `<option>` subjek tes, diawali pilihan "pemilik server".

    Tanpa ID apa pun, bot memakai pemilik server.
    """
    # Opsi default selalu ada: tanpa ID apa pun, bot memakai pemilik server.
    nama_pemilik = dashboard_uji.nama_pemilik(guild)
    label_pemilik = "👑 Pemilik server (otomatis)"
    if nama_pemilik:
        label_pemilik += f" · {nama_pemilik}"
    orang_opsi = f'<option value="">{_esc(label_pemilik)}</option>' + "".join(
        f'<option value="{_esc(uid)}">{_esc(nama)}</option>'
        for uid, nama in dashboard_uji.pilihan_subjek(guild, sertakan_pemilik=False)
    )
    return orang_opsi


def _masukan_uji(keadaan: dict, orang_opsi: str, channel_opsi: str) -> str:
    """Kolom masukan sesuai jenis tes (`member`, `id`/`ref`, atau `channel`)."""
    kolom = keadaan.get("kolom") or ""
    masukan = ""
    if kolom == "member":
        masukan = (
            f'<select name="opsi" aria-label="Contoh atas nama">{orang_opsi}</select>'
            '<input type="text" name="opsi_manual" placeholder="atau tempel @nama /'
            ' &lt;@id&gt; (opsional)">'
        )
    elif kolom in ("id", "ref"):
        pilihan = keadaan.get("pilihan") or []
        if pilihan:
            masukan = '<select name="opsi">' + "".join(
                f'<option value="{_esc(v)}">{_esc(t)}</option>' for v, t in pilihan
            ) + "</select>"
        else:
            masukan = (
                '<input type="text" name="opsi_manual" '
                'placeholder="Kosongkan = pilih otomatis">'
            )
    elif kolom == "channel":
        masukan = f'<select name="opsi">{channel_opsi}</select>'
    return masukan


def _tombol_kirim_uji(guild_id: int, token: str, item: dict, masukan: str) -> str:
    """Form tombol "Kirim tes" (hanya untuk fitur yang sudah aktif)."""
    tombol = (
        '<form method="post" action="/api/uji">'
        f'{_hidden(guild_id, token, "uji." + item["kunci"])}'
        f'{masukan}<button type="submit">Kirim tes</button></form>'
    )
    return tombol


def _tombol_atur_uji(dashboard_uji, guild_id: int, token: str, item: dict) -> str:
    """Tautan "Atur dulu" ke halaman pengaturan fitur."""
    jalur = _JALUR_FITUR.get(item["kunci"], "/")
    anchor = dashboard_uji.ANCHOR_UJI.get(item["kunci"], "p-kontrol")
    tombol = (
        '<a class="tombol-unduh" href="'
        f'{_esc(jalur)}?token={_esc(token)}&amp;guild={int(guild_id or 0)}'
        f'#{_esc(anchor)}">Atur dulu</a>'
    )
    return tombol


def render_uji_block(
    bot,
    guild_id: int,
    token: str,
    hanya: tuple[str, ...] | None = None,
) -> str:
    """Tombol tes fitur. `hanya` membatasi ke fitur milik halaman ini."""
    import dashboard_uji

    status = dashboard_uji.status_uji(guild_id)
    guild = bot.get_guild(int(guild_id or 0)) if callable(getattr(bot, "get_guild", None)) else None
    channel_opsi = _opsi_channel_uji(guild)
    orang_opsi = _opsi_orang_uji(dashboard_uji, guild)

    dipakai = tuple(
        item for item in dashboard_uji.UJI
        if hanya is None or item["kunci"] in hanya
    )
    if not dipakai:
        return ""

    grup_terlihat: list[str] = []
    baris_per_grup: dict[str, str] = {}
    for item in dipakai:
        keadaan = status.get(item["kunci"]) or {}
        grup = keadaan.get("grup") or "Lainnya"
        aktif = bool(keadaan.get("aktif"))
        channel_id = int(keadaan.get("channel_id") or 0)
        if aktif and channel_id:
            getter = getattr(bot, "get_channel", None)
            ch = getter(channel_id) if callable(getter) else None
            nama_channel = (
                f"<code>#{_esc(getattr(ch, 'name', ''))}</code>"
                if ch
                else f"<code>#{channel_id}</code>"
            )
            lencana = f"✅ aktif → {nama_channel}"
        elif aktif:
            lencana = "✅ siap diuji"
        else:
            lencana = "⬜ belum aktif"

        if aktif:
            tombol = _tombol_kirim_uji(
                guild_id, token, item, _masukan_uji(keadaan, orang_opsi, channel_opsi)
            )
        else:
            tombol = _tombol_atur_uji(dashboard_uji, guild_id, token, item)

        if grup not in baris_per_grup:
            baris_per_grup[grup] = ""
            grup_terlihat.append(grup)
        baris_per_grup[grup] += (
            '<div class="uji-baris">'
            "<div>"
            f'<b>{item["emoji"]} {_esc(item["label"])}</b> '
            f'<span class="muted">{lencana}</span>'
            f'<div class="muted">{_esc(item["contoh"])}</div>'
            "</div>"
            f"{tombol}"
            "</div>"
        )

    if len(dipakai) == 1:
        isi = next(iter(baris_per_grup.values()))
    else:
        isi = "".join(
            f'<div class="subpanel"><h3>{_esc(grup)}</h3>{baris_per_grup[grup]}</div>'
            for grup in grup_terlihat
        )
    return isi + (
        '<p class="muted">Kolom <b>contoh atas nama</b> boleh dibiarkan — bot memakai '
        "pemilik server. Koran pagi, koneksi AI, dan sambutan memakai <b>1 panggilan AI</b> "
        "per tes; sambutan/perpisahan/boost mengirim pesan sungguhan ke channel tujuan.</p>"
    )


# Halaman tempat setelan sebuah fitur uji diatur (tautan “Atur dulu”).
_JALUR_FITUR: dict[str, str] = {
    "welcome": "/sambutan",
    "goodbye": "/sambutan",
    "boost": "/sambutan",
    "pengumuman": "/buat",
    "panel": "/panel",
    "digest": "/konten",
    "tiket": "/tiket",
    "giveaway": "/giveaway",
    "kartu": "/inti",
    "ai": "/",
    "ekspor": "/ekspor",
}


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


def render_guild_picker(bot, guild_id: int, token: str, halaman: str = "") -> str:
    """Dropdown pilih server (form GET biasa, tanpa JavaScript).

    `halaman` membuat pemilihan server tetap berada di halaman yang sedang dibuka.
    """
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
        f'<form method="get" action="/{_esc(halaman)}" class="pemilih-server">'
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
        '<style>.grafik text{font-size:11px;fill:rgba(255,255,255,.62);'
        'font-family:' + dashboard_tema.FONT_STACK + '}'
        '.grafik text.nilai{fill:#FFFFFF;font-size:10px}.grafik text.sumbu{text-anchor:middle}'
        '.grafik rect{x:0}</style>'
        f'<line x1="0" y1="{area}" x2="{lebar}" y2="{area}" stroke="rgba(255,255,255,.14)" stroke-width="1"/>'
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
{dashboard_tema.FONT_LINK}
<style>{dashboard_tema.CSS_PRATINJAU}</style></head><body>
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


# ==============================================================================
# KOTAK MASUK TIKET
# ==============================================================================
# ==============================================================================
# EDITOR PANEL (tombol & dropdown tanpa Discord)
# ==============================================================================
def _form_tambah_item(bot, guild_id: int, token: str, menu_id: str) -> str:
    """Form satu baris untuk menambah tombol/dropdown ke sebuah panel."""
    import dashboard_panel

    jenis = "".join(
        f'<option value="{_esc(kunci)}">{_esc(kunci)}</option>'
        for kunci in dashboard_panel.JENIS_ITEM
    )
    perintah = _opsi_html(dashboard_panel.daftar_perintah())
    formulir = ""
    try:
        import modal_forms

        formulir = _opsi_html(
            [(str(f.get("id")), str(f.get("title") or f.get("id")))
             for f in modal_forms.list_forms(int(guild_id or 0))]
        )
    except Exception:  # pragma: no cover - jaring aman
        formulir = ""
    if not formulir:
        formulir = '<option value="">(belum ada formulir)</option>'
    role = _opsi_html(pilihan_role(bot, guild_id)[1:])
    role_lain = _opsi_html(pilihan_role(bot, guild_id))
    return f"""
<form method="post" action="/api/panel" class="tambah-item">
  {_hidden(guild_id, token, "tambah:" + str(menu_id))}
  <div class="medan"><label>Jenis item</label>
    <select name="jenis">{jenis}</select></div>
  {_medan("Label tombol", "label", place="Gamer / Buka situs / Statistik")}
  {_medan("Emoji", "emoji", place="🎮 (opsional)")}
  <div class="medan"><label>Gaya tombol</label>
    <select name="gaya">
      <option value="biru">biru</option><option value="abu">abu</option>
      <option value="hijau">hijau</option><option value="merah">merah</option>
    </select></div>
  <div class="medan"><label>Role (peran / dropdown)</label>
    <select name="role">{role}</select></div>
  <div class="medan"><label>Role tambahan (dropdown)</label>
    <select name="role2">{role_lain}</select></div>
  <div class="medan"><label>Role ke-3 (dropdown)</label>
    <select name="role3">{role_lain}</select></div>
  {_medan("URL (tautan)", "url", place="https://contoh.id")}
  <div class="medan"><label>Perintah (perintah)</label>
    <select name="perintah">{perintah}</select></div>
  <div class="medan"><label>Formulir (formulir)</label>
    <select name="formulir">{formulir}</select></div>
  {_medan("Alur (alur)", "alur", place="+role:123 > pesan:Halo {member.mention}")}
  <div class="medan"><label>Visibilitas perintah</label>
    <select name="visibilitas">
      <option value="auto">auto</option><option value="publik">publik</option>
      <option value="ephemeral">hanya pengklik</option>
    </select></div>
  <label class="centang"><input type="checkbox" name="eksklusif" value="on"> dropdown eksklusif (satu role saja)</label>
  <button type="submit">Tambah ke panel</button>
</form>
<p class="muted">Isi hanya kolom yang sesuai dengan <b>jenis</b> yang dipilih: <b>peran</b> pakai Role,
<b>tautan</b> pakai URL, <b>perintah</b> pakai daftar perintah, <b>alur</b> pakai teks alur,
<b>formulir</b> pakai daftar formulir, <b>dropdown</b> pakai Role 1–3 + Label (placeholder).</p>
"""


def _baris_item(panel_id: str, guild_id: int, token: str, nomor: int, item: dict) -> str:
    return (
        f'<div class="panel-item"><span class="nomor">{nomor}</span>'
        f'<div><b>{_esc(item.get("label"))}</b> '
        f'<span class="muted">· {_esc(item.get("jenis"))}</span>'
        f'<div class="muted kecil">{_esc(item.get("detail"))}</div></div>'
        '<form method="post" action="/api/panel">'
        + _hidden(guild_id, token, f"hapus:{panel_id}:{item.get('ref')}")
        + '<button type="submit" class="danger">Hapus</button></form></div>'
    )


def _form_verifikasi(bot, guild_id: int, token: str, status: dict) -> str:
    """Form pasang/matikan gerbang verifikasi (setara `/verifikasi pasang`)."""
    channel = _opsi_html(pilihan_channel(bot, guild_id))
    role = _opsi_html(pilihan_role(bot, guild_id)[1:])
    aktif = bool((status or {}).get("aktif"))
    ringkas = (
        f"🛡️ Gerbang verifikasi: <b>{'aktif' if aktif else 'nonaktif'}</b>"
        + (
            f' · channel <code>{_esc(status.get("channel"))}</code> · '
            f'role <code>{_esc(status.get("role"))}</code>'
            if aktif
            else ""
        )
    )
    matikan = ""
    if aktif:
        matikan = (
            '<form method="post" action="/api/panel" class="tiket-form">'
            + _hidden(guild_id, token, "verifikasi:matikan")
            + '<button type="submit" class="danger">Matikan verifikasi</button></form>'
        )
    return f"""
<div class="subpanel"><h3>{ringkas}</h3>
<details><summary class="muted">🛡️ Pasang panel verifikasi (setara /verifikasi pasang)</summary>
<form method="post" action="/api/panel" class="formgrid">
  {_hidden(guild_id, token, "verifikasi")}
  <div class="medan"><label>Channel panel</label>
    <select name="channel">{channel}</select></div>
  <div class="medan"><label>Role setelah verifikasi</label>
    <select name="role">{role}</select></div>
  {_medan("Catatan tambahan", "catatan", place="Baca aturan dulu ya (opsional)")}
  <button type="submit">Pasang panel verifikasi</button>
</form>
{matikan}
<p class="muted">Member menekan tombol <b>Verifikasi Saya</b> sekali → langsung mendapat role
tersebut. Padukan dengan auto-role untuk role tambahan.</p>
</details></div>
"""


def render_ekspor_block(guild_id: int, token: str) -> str:
    """Tautan unduh CSV analitik (level, moderasi, tiket, pemakaian AI)."""
    tombol = ""
    for kunci, label in (
        ("level", "📈 Level & XP"),
        ("moderasi", "🛡️ Kasus moderasi"),
        ("tiket", "🎟️ Tiket & rating"),
        ("pemakaian", "📊 Pemakaian AI"),
    ):
        url = f"/api/ekspor?jenis={kunci}&amp;guild={int(guild_id or 0)}&amp;token={_esc(token)}"
        tombol += f'<a class="tombol-unduh" href="{url}">{_esc(label)}</a>'
    return (
        '<p class="muted">Unduh data server sebagai CSV (bisa dibuka di Excel/Sheets):</p>'
        f'<div class="ekspor">{tombol}</div>'
        '<p class="muted">CSV dibuat ulang setiap kali diunduh — tidak ada data yang disimpan '
        "ke disk dan tidak memakai kuota AI.</p>"
    )


def render_panel_block(bot, guild_id: int, data: dict, token: str) -> str:
    """Daftar panel + isi tombol/dropdown + form tambah/hapus item."""
    paket = data or {}
    panel = paket.get("items") or []
    stat = paket.get("statistik") or {}
    ringkas = (
        f'<p class="muted">🧩 Panel: <b>{int(stat.get("panel") or 0)}</b> · '
        f'tombol: {int(stat.get("tombol") or 0)} · dropdown: {int(stat.get("dropdown") or 0)}</p>'
    )
    if not panel:
        return (
            ringkas
            + '<div class="muted">Belum ada panel. Buat dulu di bagian <b>Buat konten</b> '
            "(panel menu), lalu tombol/dropdown-nya bisa diatur di sini.</div>"
            + _form_verifikasi(bot, guild_id, token, paket.get("verifikasi") or {})
        )

    isi = ""
    for grup in panel:
        pid = str(grup.get("id"))
        nomor = 1
        baris = ""
        for item in grup.get("tombol") or []:
            baris += _baris_item(pid, guild_id, token, nomor, item)
            nomor += 1
        for dropdown in grup.get("dropdown") or []:
            baris += (
                f'<div class="panel-item dropdown"><span class="nomor">▾</span>'
                f'<div><b>{_esc(dropdown.get("label"))}</b>'
                f'<span class="muted"> · dropdown · {_esc(dropdown.get("ringkas"))}</span></div></div>'
            )
            for opsi in dropdown.get("opsi") or []:
                baris += _baris_item(pid, guild_id, token, nomor, opsi)
                nomor += 1
        if not baris:
            baris = '<div class="muted">Panel ini belum punya tombol. Tambahkan di bawah.</div>'
        kirim = "sudah terkirim" if grup.get("terkirim") else "belum terkirim"
        isi += (
            f'<div class="daftar-panel"><h4>🧩 {_esc(grup.get("judul"))} '
            f'<span class="muted">· {int(grup.get("jumlah") or 0)} item · {kirim}</span></h4>'
            + (f'<p class="muted">{_esc(grup.get("deskripsi"))}</p>' if grup.get("deskripsi") else "")
            + baris
            + '<details><summary class="muted">➕ Tambah tombol / dropdown</summary>'
            + _form_tambah_item(bot, guild_id, token, pid)
            + "</details></div>"
        )
    return ringkas + isi + _form_verifikasi(bot, guild_id, token, paket.get("verifikasi") or {})


# ==============================================================================
# KOTAK MASUK TIKET
# ==============================================================================
def _form_panel_tiket(bot, guild_id: int, token: str) -> str:
    """Form pasang panel tiket (setara `/tiket panel`) + tombol matikan."""
    channel = _opsi_html(pilihan_channel(bot, guild_id))
    role = _opsi_html(pilihan_role(bot, guild_id))
    return f"""
<details><summary class="muted">🎟️ Pasang panel tiket (setara /tiket panel)</summary>
<form method="post" action="/api/tiket" class="formgrid">
  {_hidden(guild_id, token, "panel")}
  <div class="medan"><label>Channel panel</label>
    <select name="channel">{channel}</select></div>
  <div class="medan"><label>Role staf</label>
    <select name="staff_role">{role}</select></div>
  <div class="medan"><label>Channel log transkrip</label>
    <select name="log_channel">{channel}</select></div>
  <div class="medan"><label>Maksimal tiket per member</label>
    <input type="number" name="max_open" min="1" max="10" value="2"></div>
  <button type="submit">Pasang panel tiket</button>
</form>
<form method="post" action="/api/tiket" class="tiket-form">
  {_hidden(guild_id, token, "matikan")}
  <button type="submit" class="danger">Matikan sistem tiket</button>
</form>
<p class="muted">Panel dikirim ke channel yang dipilih; member menekan tombol
<b>Buat Tiket</b> untuk membuka thread privat.</p>
</details>
"""


def _blok_topik_tiket(paket: dict, stat: dict, token: str, guild_id: int, role_opsi: str) -> str:
    """Detail daftar topik + form tambah topik; kosong bila tiket nonaktif."""
    topik = paket.get("topik") or []

    def _baris_topik(item: dict) -> str:
        role_id = int(item.get("staff_role_id") or 0)
        staf = f"role `{role_id}`" if role_id else "role staf umum"
        return (
            '<div class="tiket-baris"><div>'
            f'<b>{_esc(str(item.get("emoji") or "🎟️") + " " + str(item.get("nama") or "-"))}</b>'
            f'<div class="muted">{_esc(item.get("deskripsi") or "tanpa keterangan")} · staf: {_esc(staf)}</div>'
            "</div>"
            '<form method="post" action="/api/tiket">'
            + _hidden(guild_id, token, "topik-hapus")
            + f'<input type="hidden" name="nama" value="{_esc(item.get("nama"))}">'
            '<button type="submit" class="danger">Hapus</button></form></div>'
        )

    # Saat sistem tiket dimatikan, jangan tampilkan jalur tulis apa pun.
    blok_topik = "" if not stat.get("aktifkan", True) else (
        '<details><summary class="muted">🧩 Topik panel tiket '
        f"({len(topik)}/{tickets.TICKET_TOPIC_MAX})"
        "</summary>"
        '<p class="muted">Tanpa topik, panel memakai satu tombol <b>Buat Tiket</b>. Dengan topik, '
        "member memilih dari dropdown dan role staf topik itu yang diberi tahu. Pasang ulang panel "
        "setelah mengubah daftar.</p>"
        + (
            f'<div class="daftar-tiket">{"".join(_baris_topik(t) for t in topik)}</div>'
            if topik
            else '<div class="muted">Belum ada topik.</div>'
        )
        + '<form method="post" action="/api/tiket" class="formgrid">'
        + _hidden(guild_id, token, "topik-tambah")
        + '<div class="medan"><label>Nama topik</label>'
        '<input type="text" name="nama" maxlength="40" placeholder="Pembelian" required></div>'
        '<div class="medan"><label>Emoji</label>'
        '<input type="text" name="emoji" maxlength="8" placeholder="🛒"></div>'
        f'<div class="medan"><label>Role staf topik</label><select name="role_id">{role_opsi}</select></div>'
        '<div class="medan"><label>Keterangan (tampil di dropdown)</label>'
        '<input type="text" name="deskripsi" maxlength="100" placeholder="Beli / kirim barang"></div>'
        '<button type="submit">Simpan topik</button></form></details>'
    )
    return blok_topik


def _daftar_tiket_aktif(items: list, guild_id: int, token: str) -> str:
    """Daftar tiket aktif: info ringkas, form balas, tombol tutup & catatan."""
    baris = ""
    for item in items:
        tid = str(item.get("id"))
        sla = ' <span class="warn">⏰ lewat SLA</span>' if item.get("sla") else ""
        catatan = item.get("catatan") or []
        isi_catatan = "".join(
            '<div style="display:flex;gap:8px;justify-content:space-between;align-items:flex-start;'
            'border-left:3px solid var(--aksen,#8B7CFF);padding:4px 0 4px 8px;margin:4px 0">'
            f'<div style="font-size:.84rem">{_esc(note.get("waktu"))} · '
            f'<b>{"dashboard" if str(note.get("oleh") or "0") in ("0", "") else "@" + str(note.get("oleh"))}</b>'
            f'<br>{_esc(note.get("teks"))}</div>'
            '<form method="post" action="/api/tiket">'
            + _hidden(guild_id, token, f"catatan-hapus:{tid}:{nomor}")
            + '<button type="submit" class="danger" title="Hapus catatan">×</button></form></div>'
            for nomor, note in enumerate(catatan, start=1)
        )
        blok_catatan = (
            '<details><summary class="muted">📝 Catatan staf '
            f"({len(catatan)})</summary>"
            + (
                f'<div style="margin:6px 0">{isi_catatan}</div>'
                if catatan
                else '<div class="muted">Belum ada catatan internal.</div>'
            )
            + '<form method="post" action="/api/tiket" class="tiket-form">'
            + _hidden(guild_id, token, f"catat:{tid}")
            + '<input type="text" name="teks" maxlength="500" '
            'placeholder="Catatan internal (member tidak melihatnya)…">'
            '<button type="submit" class="ghost">Simpan catatan</button></form></details>'
        )
        baris += (
            f'<div class="tiket-baris">'
            f'<div><b>{_esc(item.get("nomor"))}</b> {_esc(item.get("status_label"))}{sla}'
            f'<div class="muted">Pemilik <code>{_esc(item.get("pemilik"))}</code> · '
            f'umur {_esc(item.get("umur"))} · diam {_esc(item.get("diam"))}'
            + (f' · diklaim <code>{_esc(item.get("diklaim"))}</code>' if item.get("diklaim") else "")
            + (f'<br>{_esc(item.get("topik"))}' if item.get("topik") else "")
            + "</div></div>"
            '<form method="post" action="/api/tiket" class="tiket-form">'
            + _hidden(guild_id, token, "balas:" + tid)
            + '<input type="text" name="teks" maxlength="1800" placeholder="Balas sebagai bot…">'
            '<input type="text" name="identitas" maxlength="80" placeholder="nama pengirim (opsional)">'
            '<button type="submit" class="ghost">Balas</button></form>'
            '<form method="post" action="/api/tiket">'
            + _hidden(guild_id, token, "tutup:" + tid)
            + '<button type="submit" class="danger">Tutup</button></form>'
            + blok_catatan
            + "</div>"
        )
    return baris


def render_tiket_block(guild_id: int, data: dict, token: str, bot=None) -> str:
    """Kotak masuk tiket: ringkasan + daftar tiket aktif + form balas/tutup."""
    paket = data or {}
    items = paket.get("items") or []
    stat = paket.get("statistik") or {}
    ringkas = (
        f'<p class="muted">🔢 Aktif: <b>{int(stat.get("aktif") or 0)}</b> · '
        f'diklaim: {int(stat.get("diklaim") or 0)} · '
        f'lewat SLA: {int(stat.get("lewat_sla") or 0)} · '
        f'rating: {_esc(stat.get("rating") or "-")}'
        + ("" if stat.get("aktifkan", True) else " · ⛔ Sistem tiket nonaktif")
        + "</p>"
    )
    pasang = _form_panel_tiket(bot, guild_id, token) if bot is not None else ""

    role_opsi = (
        _opsi_html(pilihan_role(bot, guild_id)) if bot is not None else '<option value="0">—</option>'
    )
    blok_topik = _blok_topik_tiket(paket, stat, token, guild_id, role_opsi)
    if not items:
        return (
            ringkas
            + '<div class="muted">Tidak ada tiket aktif. Tiket baru muncul di sini setelah '
            "member menekan tombol <b>Buat Tiket</b> di panel.</div>"
            + pasang
            + blok_topik
        )
    baris = _daftar_tiket_aktif(items, guild_id, token)
    return ringkas + f'<div class="daftar-tiket">{baris}</div>' + pasang + blok_topik


def _opsi_dari(opsi: list[tuple[str, str]], terpilih: str = "") -> str:
    return "".join(
        f'<option value="{_esc(str(nilai))}"{" selected" if str(nilai) == str(terpilih) else ""}>'
        f"{_esc(str(teks))}</option>"
        for nilai, teks in opsi
    )


def _gv_form_buat(gid: int, token: str, channel_opsi: str, role_opsi_bonus: str, bawaan: dict) -> str:
    """Formulir "buat giveaway" (setara `/giveaway mulai`)."""
    form_buat = (
        '<details><summary class="muted">➕ Buat giveaway dari sini (setara /giveaway mulai)</summary>'
        '<form method="post" action="/api/giveaway" class="formgrid">'
        + _hidden(gid, token, "buat")
        + '<div class="medan"><label>Hadiah</label>'
        '<input type="text" name="hadiah" maxlength="200" placeholder="Nitro 1 Bulan" required></div>'
        f'<div class="medan"><label>Channel</label><select name="channel">{channel_opsi}</select></div>'
        '<div class="medan"><label>Durasi (menit)</label>'
        f'<input type="number" name="menit" min="1" max="43200" value="{int(bawaan.get("seconds") or 3600) // 60}"></div>'
        '<div class="medan"><label>Jumlah pemenang</label>'
        f'<input type="number" name="pemenang" min="1" max="20" value="{int(bawaan.get("winner_count") or 1)}"></div>'
        '<div class="medan"><label>Syarat level minimal (0 = tanpa)</label>'
        f'<input type="number" name="level" min="0" max="500" value="{int(bawaan.get("level") or 0)}"></div>'
        '<div class="medan"><label>Syarat umur akun (hari, 0 = tanpa)</label>'
        f'<input type="number" name="umur" min="0" max="3650" value="{int(bawaan.get("account_age_days") or 0)}"></div>'
        f'<div class="medan"><label>Role bonus (peluang ekstra)</label>'
        f'<select name="role_bonus">{role_opsi_bonus}</select></div>'
        '<div class="medan"><label>Tambahan peluang (1–5)</label>'
        f'<input type="number" name="bobot" min="1" max="5" value="{int(bawaan.get("bonus_weight") or 1)}"></div>'
        '<button type="submit">Pasang giveaway</button></form></details>'
    )
    return form_buat


def _gv_daftar_aktif(aktif: list, gid: int, token: str) -> str:
    """Daftar giveaway yang masih berjalan, lengkap tombol Hentikan."""
    if aktif:
        baris = ""
        for item in aktif:
            baris += (
                '<div class="tiket-baris"><div>'
                f'<b>{_esc(item.get("hadiah"))}</b> · {int(item.get("peserta") or 0)} peserta'
                f'<div class="muted">{_esc(item.get("syarat"))} · berakhir '
                f'{_esc(_waktu_relatif(item.get("berakhir")))}</div></div>'
                '<form method="post" action="/api/giveaway">'
                + _hidden(gid, token, f"akhiri:{int(item.get('message_id') or 0)}")
                + '<button type="submit" class="danger">Hentikan</button></form></div>'
            )
        daftar_aktif = f'<div class="daftar-tiket">{baris}</div>'
    else:
        daftar_aktif = (
            '<div class="muted">Belum ada giveaway berjalan. Buat dari formulir di atas '
            "atau lewat <code>/giveaway mulai</code>.</div>"
        )
    return daftar_aktif


def _gv_daftar_selesai(selesai: list, gid: int, token: str) -> str:
    """Daftar giveaway selesai + tombol reroll bila masih ada sisa undi."""
    if selesai:
        baris = ""
        for item in selesai:
            pemenang = ", ".join(f"<@{uid}>" for uid in (item.get("pemenang") or [])) or "_tanpa pemenang_"
            sisa = int(item.get("sisa_undi") or 0)
            tombol = (
                '<form method="post" action="/api/giveaway">'
                + _hidden(gid, token, f"reroll:{int(item.get('message_id') or 0)}")
                + f'<button type="submit" class="ghost">Reroll ({sisa})</button></form>'
                if sisa
                else '<span class="muted">semua peserta sudah menang</span>'
            )
            baris += (
                '<div class="tiket-baris"><div>'
                f'<b>{_esc(item.get("hadiah"))}</b> · {pemenang}'
                f'<div class="muted">{_esc(item.get("syarat"))} · {int(item.get("peserta") or 0)} peserta</div>'
                f"</div>{tombol}</div>"
            )
        daftar_selesai = f'<div class="daftar-tiket">{baris}</div>'
    else:
        daftar_selesai = '<div class="muted">Belum ada giveaway yang selesai.</div>'
    return daftar_selesai


def _gv_daftar_template(template: list, gid: int, token: str) -> str:
    """Daftar template giveaway beserta tombol Hapus."""
    if template:
        baris = "".join(
            '<div class="tiket-baris"><div>'
            f'<b>{_esc(tpl.get("nama"))}</b>'
            f'<div class="muted">{int(tpl.get("winner_count") or 1)} pemenang · '
            f'{int(tpl.get("seconds") or 0) // 60} menit · '
            f'{_esc(_ringkas_syarat(tpl))}</div></div>'
            '<form method="post" action="/api/giveaway">'
            + _hidden(gid, token, "template-hapus")
            + f'<input type="hidden" name="nama" value="{_esc(tpl.get("nama"))}">'
            '<button type="submit" class="danger">Hapus</button></form></div>'
            for tpl in template[:20]
        )
        daftar_template = f'<div class="daftar-tiket">{baris}</div>'
    else:
        daftar_template = (
            '<div class="muted">Belum ada template. Template berguna untuk giveaway rutin '
            "(mis. “Nitro bulanan” dengan syarat level 5).</div>"
        )
    return daftar_template


def _gv_form_template(gid: int, token: str, role_opsi: str) -> str:
    """Formulir simpan template giveaway baru."""
    form_template = (
        '<details><summary class="muted">🗂️ Simpan template baru</summary>'
        '<form method="post" action="/api/giveaway" class="formgrid">'
        + _hidden(gid, token, "template-simpan")
        + '<div class="medan"><label>Nama template</label>'
        '<input type="text" name="nama" maxlength="40" placeholder="Nitro bulanan"></div>'
        '<div class="medan"><label>Durasi (menit)</label>'
        '<input type="number" name="menit" min="1" max="43200" value="60"></div>'
        '<div class="medan"><label>Jumlah pemenang</label>'
        '<input type="number" name="pemenang" min="1" max="20" value="1"></div>'
        '<div class="medan"><label>Level minimal (0 = tanpa)</label>'
        '<input type="number" name="level" min="0" max="500" value="0"></div>'
        '<div class="medan"><label>Umur akun (hari, 0 = tanpa)</label>'
        '<input type="number" name="umur" min="0" max="3650" value="0"></div>'
        f'<div class="medan"><label>Role bonus</label><select name="role_bonus">{role_opsi}</select></div>'
        '<div class="medan"><label>Tambahan peluang (1–5)</label>'
        '<input type="number" name="bobot" min="1" max="5" value="1"></div>'
        '<button type="submit">Simpan template</button></form></details>'
    )
    return form_template


def _gv_opsi_ping(bawaan: dict) -> str:
    """Pilihan dropdown untuk ping `@everyone` saat giveaway dipasang."""
    ping_opsi = _opsi_dari(
        (("off", "Tidak ping"), ("on", "Ping @everyone")),
        "on" if bawaan.get("ping_everyone") else "off",
    )
    return ping_opsi


def _gv_form_bawaan(gid: int, token: str, role_opsi_bonus: str, ping_opsi: str, bawaan: dict) -> str:
    """Formulir setelan bawaan giveaway baru."""
    form_bawaan = (
        '<details open><summary class="muted">⚙️ Setelan bawaan giveaway baru</summary>'
        '<p class="muted">Dipakai saat <code>/giveaway mulai</code> tanpa argumen, dan '
        "sebagai nilai awal formulir di atas.</p>"
        '<form method="post" action="/api/giveaway" class="formgrid">'
        + _hidden(gid, token, "simpan-bawaan")
        + '<div class="medan"><label>Durasi bawaan (menit)</label>'
        f'<input type="number" name="menit" min="1" max="43200" value="{int(bawaan.get("seconds") or 3600) // 60}"></div>'
        '<div class="medan"><label>Jumlah pemenang bawaan</label>'
        f'<input type="number" name="pemenang" min="1" max="20" value="{int(bawaan.get("winner_count") or 1)}"></div>'
        '<div class="medan"><label>Level minimal bawaan</label>'
        f'<input type="number" name="level" min="0" max="500" value="{int(bawaan.get("level") or 0)}"></div>'
        '<div class="medan"><label>Umur akun bawaan (hari)</label>'
        f'<input type="number" name="umur" min="0" max="3650" value="{int(bawaan.get("account_age_days") or 0)}"></div>'
        f'<div class="medan"><label>Role bonus bawaan</label><select name="role_bonus">{role_opsi_bonus}</select></div>'
        '<div class="medan"><label>Tambahan peluang bawaan</label>'
        f'<input type="number" name="bobot" min="1" max="5" value="{int(bawaan.get("bonus_weight") or 1)}"></div>'
        f'<div class="medan"><label>Saat giveaway dipasang</label><select name="ping">{ping_opsi}</select></div>'
        '<button type="submit">Simpan setelan bawaan</button></form></details>'
    )
    return form_bawaan


def render_giveaway_block(
    guild_id: int, data: dict, token: str, bot=None
) -> str:
    """Halaman giveaway: buat, hentikan, reroll, template, & setelan bawaan.

    Semua tombol memakai form biasa (tanpa JavaScript) dan hanya memanggil aksi
    yang ada di whitelist `dashboard_giveaway.AKSI_DIKENAL`.
    """
    paket = data or {}
    aktif = paket.get("aktif") or []
    selesai = paket.get("selesai") or []
    template = paket.get("template") or []
    bawaan = paket.get("bawaan") or {}
    gid = int(guild_id or 0)

    ringkas = (
        f'<p class="muted">🎁 Berjalan: <b>{len(aktif)}</b> · '
        f"selesai: {int(paket.get('total_selesai') or 0)} · "
        f"template: {len(template)}</p>"
    )

    channel_opsi = _opsi_dari(pilihan_channel(bot, gid)) if bot is not None else '<option value="0">—</option>'
    role_opsi = _opsi_dari(pilihan_role(bot, gid)) if bot is not None else '<option value="0">—</option>'
    role_opsi_bonus = _opsi_dari(
        pilihan_role(bot, gid), str(int(bawaan.get("bonus_role_id") or 0))
    ) if bot is not None else '<option value="0">—</option>'

    form_buat = _gv_form_buat(gid, token, channel_opsi, role_opsi_bonus, bawaan)
    daftar_aktif = _gv_daftar_aktif(aktif, gid, token)
    daftar_selesai = _gv_daftar_selesai(selesai, gid, token)
    daftar_template = _gv_daftar_template(template, gid, token)
    form_template = _gv_form_template(gid, token, role_opsi)
    ping_opsi = _gv_opsi_ping(bawaan)
    form_bawaan = _gv_form_bawaan(gid, token, role_opsi_bonus, ping_opsi, bawaan)

    return (
        ringkas
        + form_buat
        + '<div class="subpanel"><h3>🎉 Giveaway berjalan</h3>' + daftar_aktif + "</div>"
        + '<div class="subpanel"><h3>✅ Selesai (terbaru)</h3>' + daftar_selesai + "</div>"
        + '<div class="subpanel"><h3>🗂️ Template</h3>' + daftar_template + form_template + "</div>"
        + '<div class="subpanel"><h3>⚙️ Setelan</h3>' + form_bawaan + "</div>"
    )


def _ringkas_syarat(tpl: dict) -> str:
    """Ringkasan syarat satu template tanpa memerlukan modul engagement."""
    bagian: list[str] = []
    level = int(tpl.get("requirements", {}).get("level") or 0) if isinstance(tpl.get("requirements"), dict) else 0
    if level:
        bagian.append(f"level ≥ {level}")
    hari = int(tpl.get("requirements", {}).get("account_age_days") or 0) if isinstance(tpl.get("requirements"), dict) else 0
    if hari:
        bagian.append(f"akun ≥ {hari} hari")
    roles = tpl.get("requirements", {}).get("roles") if isinstance(tpl.get("requirements"), dict) else None
    if roles:
        bagian.append(f"{len(roles)} role wajib")
    bonus = tpl.get("bonus_roles") or {}
    if bonus:
        bagian.append(f"{len(bonus)} role bonus")
    return " · ".join(bagian) if bagian else "tanpa syarat"


def _waktu_relatif(epoch: object) -> str:
    """Teks sisa waktu sederhana tanpa JavaScript (`2j 15m`)."""
    import time as _time

    try:
        sisa = int(float(epoch or 0) - _time.time())
    except (TypeError, ValueError):
        return "-"
    if sisa <= 0:
        return "segera ditutup"
    jam, sisa = divmod(sisa, 3600)
    menit = sisa // 60
    if jam >= 24:
        return f"{jam // 24} hari {jam % 24} jam lagi"
    if jam:
        return f"{jam} jam {menit} menit lagi"
    return f"{menit} menit lagi"


def render_arsip_block(guild_id: int, token: str, stat: dict, terbaru: list[dict]) -> str:
    """Blok arsip transkrip di halaman tiket: pencarian + arsip terbaru."""
    stat = stat or {}
    items = terbaru or []
    gid = int(guild_id or 0)
    retensi_hari = int(stat.get("retensi_hari") or 0)
    retensi = f"hapus setelah {retensi_hari} hari" if retensi_hari else "tanpa batas umur"

    if items:
        baris = "".join(
            '<div class="tiket-baris"><div>'
            f'<b>#{_esc(item.get("kode"))}</b> — {_esc(item.get("topik") or "-")}'
            f'<div class="muted">{int(item.get("jumlah_pesan") or 0)} pesan · ditutup '
            f"{_esc(_waktu_arsip(item.get('ditutup')))}</div></div>"
            f'<a class="tombol ghost" href="/api/transkrip?token={_esc(token)}&amp;guild={gid}'
            f'&amp;kode={_esc(item.get("kode"))}" target="_blank" rel="noreferrer">Buka</a></div>'
            for item in items[:5]
        )
        daftar = f'<div class="daftar-tiket">{baris}</div>'
    else:
        daftar = (
            '<div class="muted">Belum ada transkrip tersimpan. Arsip dibuat otomatis '
            "setiap kali tiket ditutup (lewat command, dashboard, atau auto-close).</div>"
        )

    form = (
        '<form method="get" action="/transkrip" class="formgrid">'
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<input type="hidden" name="guild" value="{gid}">'
        '<div class="medan"><label>Cari di isi percakapan</label>'
        '<input type="text" name="q" maxlength="80" placeholder="mis. nitro, refund, bug"></div>'
        '<button type="submit">Cari transkrip</button></form>'
    )
    ringkas = (
        f'<p class="muted">📚 Tersimpan <b>{int(stat.get("jumlah") or 0)}</b> transkrip '
        f'({_esc(stat.get("ukuran_kb") or 0)} KB) · arsip terakhir: '
        f'{_esc(stat.get("terakhir") or "-")} · batas {int(stat.get("maksimal") or 0)} per server · '
        f'{_esc(retensi)}</p>'
    )
    return (
        ringkas
        + form
        + f'<p class="muted"><a href="/transkrip?token={_esc(token)}&amp;guild={gid}">'
        "Buka arsip lengkap →</a></p>"
        + daftar
    )


def _waktu_arsip(nilai: object) -> str:
    """Waktu arsip yang aman untuk nilai kosong/rusak."""
    import time as _time

    try:
        return _time.strftime("%Y-%m-%d %H:%M", _time.localtime(float(nilai or 0)))
    except (TypeError, ValueError, OSError):
        return "-"


def _daftar_arsip_html(daftar: list[dict], kueri: str, token: str, gid: int) -> str:
    """Baris hasil pencarian arsip, atau pesan kosong bila tak ada yang cocok."""
    if daftar:
        return "".join(
            '<div class="hasil"><div>'
            f'<b>#{_esc(item.get("kode"))}</b> — {_esc(item.get("topik") or "-")}'
            f'<div class="redup">Pembuat <code>{_esc(item.get("user_id") or "-")}</code> · '
            f'{int(item.get("jumlah_pesan") or 0)} pesan · ditutup '
            f"{_esc(_waktu_arsip(item.get('ditutup')))}</div>"
            + (f'<div class="cuplikan">…{_esc(item.get("cuplikan"))}…</div>'
               if item.get("cuplikan") else "")
            + "</div>"
            f'<div class="aksi"><a class="tombol" href="/api/transkrip?token={_esc(token)}'
            f'&amp;guild={gid}&amp;kode={_esc(item.get("kode"))}" target="_blank" '
            'rel="noreferrer">Buka</a>'
            '<form method="post" action="/api/transkrip">'
            f'<input type="hidden" name="token" value="{_esc(token)}">'
            f'<input type="hidden" name="guild" value="{gid}">'
            '<input type="hidden" name="action" value="hapus">'
            f'<input type="hidden" name="kode" value="{_esc(item.get("kode"))}">'
            '<button type="submit" class="danger">Hapus</button></form></div></div>'
            for item in daftar
        )
    else:
        return (
            f'<p class="redup">Tidak ada arsip yang cocok dengan '
            f"<b>{_esc(kueri)}</b>.</p>" if kueri
            else '<p class="redup">Belum ada transkrip tersimpan di server ini.</p>'
        )


def render_halaman_arsip(
    guild_id: int,
    token: str,
    *,
    kata: str = "",
    hasil: list[dict] | None = None,
    stat: dict | None = None,
    nama_server: str = "",
) -> str:
    """Halaman mandiri `/transkrip`: pencarian arsip + daftar hasil (tanpa JS)."""
    import dashboard_tema as tema


    gid = int(guild_id or 0)
    daftar = hasil or []
    stat = stat or {}
    retensi_hari = int(stat.get("retensi_hari") or 0)
    retensi = f"hapus setelah {retensi_hari} hari" if retensi_hari else "tanpa batas umur"
    kueri = str(kata or "").strip()
    baris = _daftar_arsip_html(daftar, kueri, token, gid)
    kembali = f"/tiket?token={_esc(token)}&amp;guild={gid}"

    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arsip transkrip tiket — dashboard</title>
{tema.FONT_LINK}
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 18px 16px 48px; background: {tema.LATAR}; color: {tema.TEKS};
         font-family: {tema.FONT_STACK}; line-height: 1.55; }}
  main {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 4px; }}
  .redup {{ color: {tema.REDUP}; }}
  a {{ color: {tema.AKSEN}; }}
  code {{ font-family: {tema.FONT_MONO}; }}
  form.cari {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 14px 0; }}
  form.cari input[type=text] {{ flex: 1 1 220px; padding: 11px 12px; border-radius: 10px;
      border: 1px solid {tema.GARIS_KUAT}; background: {tema.MEDAN}; color: {tema.TEKS};
      font: inherit; }}
  button, .tombol {{ padding: 10px 14px; border-radius: 10px; border: 1px solid {tema.GARIS_KUAT};
      background: {tema.KARTU_2}; color: {tema.TEKS}; font: inherit; cursor: pointer;
      text-decoration: none; display: inline-block; }}
  button.danger {{ border-color: {tema.MERAH}; color: {tema.MERAH}; }}
  .hasil {{ display: flex; gap: 12px; justify-content: space-between; align-items: flex-start;
      background: {tema.KARTU}; border: 1px solid {tema.GARIS}; border-radius: 14px;
      padding: 12px 14px; margin: 10px 0; }}
  .hasil .aksi {{ display: flex; gap: 8px; align-items: center; }}
  .cuplikan {{ margin-top: 6px; font-size: .86rem; color: {tema.REDUP};
      border-left: 3px solid {tema.AKSEN}; padding-left: 8px; white-space: pre-wrap; }}
  @media (max-width: 520px) {{ .hasil {{ flex-direction: column; }} }}
</style></head>
<body><main>
<p><a href="{kembali}">← Kembali ke tiket</a></p>
<h1>📚 Arsip transkrip tiket</h1>
<p class="redup">{_esc(nama_server or "")} · tersimpan <b>{int(stat.get("jumlah") or 0)}</b> transkrip
({_esc(stat.get("ukuran_kb") or 0)} KB) · batas {int(stat.get("maksimal") or 0)} per server · {_esc(retensi)}.</p>
<form method="get" action="/transkrip" class="cari">
  <input type="hidden" name="token" value="{_esc(token)}">
  <input type="hidden" name="guild" value="{gid}">
  <input type="text" name="q" maxlength="80" value="{_esc(kueri)}"
         placeholder="Cari isi percakapan, mis. nitro / refund / bug">
  <button type="submit">Cari</button>
</form>
{baris}
</main></body></html>
"""


__all__ = [
    "daftar_server",
    "render_panel_block",
    "kontrol_html",
    "opsi_banner",
    "opsi_untuk",
    "pilihan_channel",
    "pilihan_role",
    "render_audit_block",
    "render_banner_block",
    "render_buat_block",
    "render_ekspor_block",
    "render_arsip_block",
    "render_giveaway_block",
    "render_halaman_arsip",
    "render_guild_picker",
    "render_konten_block",
    "render_kirim_block",
    "render_pratinjau_html",
    "render_setelan_block",
    "render_tiket_block",
    "render_tren_svg",
]
