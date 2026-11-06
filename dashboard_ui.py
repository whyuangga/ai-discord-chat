"""Penyusun HTML untuk panel admin dashboard (server-side, tanpa JavaScript).

Modul ini hanya **menggambar**: daftar setelan dari `dashboard_admin`, form
pengiriman embed/webhook, dan daftar konten yang bisa dihapus. Semua aksi tetap
dikirim ke `POST /api/aksi` atau `POST /api/kirim` yang memeriksa token.
"""

import html

import dashboard_admin
import dashboard_tema
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


def render_kartu_block(guild_id: int, token: str) -> str:
    """Panel unggah kartu sambutan / perpisahan / boost (disimpan di `data/media/`)."""
    info = dashboard_unggah.kartu_info(guild_id)
    slot = ""
    for jenis in dashboard_unggah.JENIS_KARTU:
        data = info.get(jenis)
        label = dashboard_unggah.LABEL_KARTU[jenis]
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
        slot += (
            '<div class="kartu-slot">'
            f'<h4>{_esc(label.capitalize())}</h4>'
            f'{pratinjau}{keterangan}'
            '<form method="post" action="/api/unggah" class="formgrid" '
            'enctype="multipart/form-data">'
            f'{_hidden(guild_id, token, "kartu.simpan:" + jenis)}'
            f'{_medan_berkas("Gambar kartu (PNG/JPG/GIF/WEBP)", "banner")}'
            f'<button type="submit">Unggah kartu {_esc(label)}</button>'
            "</form>"
            f"{hapus}"
            "</div>"
        )

    mode = "statis"
    try:
        import community_agent

        mode = str(
            ((community_agent.welcome_agent_guilds or {}).get(int(guild_id or 0)) or {})
            .get("card_mode")
            or "mati"
        )
    except Exception:  # pragma: no cover - jaring aman
        mode = "statis"
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
        '<p class="muted">Kartu <b>perpisahan</b> &amp; <b>boost</b> otomatis dipakai bila '
        "gambarnya ada. Ukuran ideal 1024×420 px, maksimal "
        f"{dashboard_unggah.batas_mb()} MB.</p>"
    )
    return f'<div class="kartu-sambutan">{slot}</div>{pengaturan}'


def render_uji_block(bot, guild_id: int, token: str) -> str:
    """Panel tombol tes fitur — dikelompokkan per jenis fitur."""
    import dashboard_uji

    status = dashboard_uji.status_uji(guild_id)
    kanal = getattr(bot, "guilds", None) or []
    guild = bot.get_guild(int(guild_id or 0)) if callable(getattr(bot, "get_guild", None)) else None
    channel_opsi = ""
    for ch in list(getattr(guild, "text_channels", []) or [])[:60]:
        channel_opsi += f'<option value="{int(getattr(ch, "id", 0))}">#{_esc(getattr(ch, "name", "-"))}</option>'
    if not channel_opsi:
        channel_opsi = '<option value="0">(belum ada channel)</option>'
    _ = kanal

    grup_terlihat: list[str] = []
    baris_per_grup: dict[str, str] = {}
    for item in dashboard_uji.UJI:
        keadaan = status.get(item["kunci"]) or {}
        grup = keadaan.get("grup") or "Lainnya"
        aktif = bool(keadaan.get("aktif"))
        channel_id = int(keadaan.get("channel_id") or 0)
        if aktif and channel_id:
            getter = getattr(bot, "get_channel", None)
            ch = getter(channel_id) if callable(getter) else None
            nama_channel = f"<code>#{_esc(getattr(ch, 'name', ''))}</code>" if ch else f"<code>#{channel_id}</code>"
            lencana = f"✅ aktif → {nama_channel}"
        elif aktif:
            lencana = "✅ siap diuji"
        else:
            lencana = "⬜ belum aktif"

        kolom = keadaan.get("kolom") or ""
        if aktif:
            masukan = ""
            if kolom == "member":
                masukan = ('<input type="text" name="opsi" inputmode="numeric" '
                           'placeholder="ID member (opsional)">')
            elif kolom in ("id", "ref"):
                pilihan = keadaan.get("pilihan") or []
                if pilihan:
                    masukan = '<select name="opsi">' + "".join(
                        f'<option value="{_esc(v)}">{_esc(t)}</option>' for v, t in pilihan
                    ) + "</select>"
                else:
                    masukan = ('<input type="text" name="opsi" inputmode="numeric" '
                               'placeholder="Kosongkan = pilih otomatis">')
            elif kolom == "channel":
                masukan = f'<select name="opsi">{channel_opsi}</select>'
            tombol = (
                '<form method="post" action="/api/uji">'
                f'{_hidden(guild_id, token, "uji." + item["kunci"])}'
                f'{masukan}<button type="submit">Kirim tes</button></form>'
            )
        else:
            tombol = (
                '<a class="tombol-unduh" href="/setelan?token='
                f'{_esc(token)}&amp;guild={int(guild_id or 0)}#p-setelan">Atur di Setelan</a>'
            )

        if grup not in baris_per_grup:
            baris_per_grup[grup] = ""
            grup_terlihat.append(grup)
        baris_per_grup[grup] += (
            '<div class="uji-baris">'
            '<div>'
            f'<b>{item["emoji"]} {_esc(item["label"])}</b> '
            f'<span class="muted">{lencana}</span>'
            f'<div class="muted">{_esc(item["contoh"])}</div>'
            "</div>"
            f"{tombol}"
            "</div>"
        )

    isi = "".join(
        f'<div class="subpanel"><h3>{_esc(grup)}</h3>{baris_per_grup[grup]}</div>'
        for grup in grup_terlihat
    )
    catatan = (
        '<p class="muted">Sambutan, perpisahan, boost, koran pagi, dan koneksi AI memakai '
        "<b>1 panggilan AI</b> per tes. Tes sambutan/perpisahan/boost mengirim pesan "
        "sungguhan ke channel tujuan — member lain akan melihatnya. Sisi kanan memilih "
        "subjek: ID member, pengumuman/panel tersimpan, atau channel.</p>"
    )
    return isi + catatan


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
    if not items:
        return (
            ringkas
            + '<div class="muted">Tidak ada tiket aktif. Tiket baru muncul di sini setelah '
            "member menekan tombol <b>Buat Tiket</b> di panel.</div>"
            + pasang
        )

    baris = ""
    for item in items:
        tid = str(item.get("id"))
        sla = ' <span class="warn">⏰ lewat SLA</span>' if item.get("sla") else ""
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
            "</div>"
        )
    return ringkas + f'<div class="daftar-tiket">{baris}</div>' + pasang


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
    "render_guild_picker",
    "render_konten_block",
    "render_kirim_block",
    "render_pratinjau_html",
    "render_setelan_block",
    "render_tiket_block",
    "render_tren_svg",
]
