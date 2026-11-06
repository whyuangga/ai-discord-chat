"""Penyusun HTML untuk panel admin dashboard (server-side, tanpa JavaScript).

Modul ini hanya **menggambar**: daftar setelan dari `dashboard_admin`, form
pengiriman embed/webhook, dan daftar konten yang bisa dihapus. Semua aksi tetap
dikirim ke `POST /api/aksi` atau `POST /api/kirim` yang memeriksa token.
"""

import html

import dashboard_admin

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
<form method="post" action="/api/kirim" class="formgrid">
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
  <button type="submit">Kirim sekarang</button>
</form>
<p class="muted">Kalau “Identitas webhook” diisi, pesan dikirim lewat webhook channel itu
(nama &amp; avatar boleh beda dari bot). Tombol link hanya dipakai saat mengirim sebagai bot.</p>
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
<form method="post" action="/api/konten" class="formgrid">
  {_hidden(guild_id, token, "buat.panel")}
  <div class="medan"><label for="pan-channel">Channel</label>
    <select name="channel" id="pan-channel">{opsi}</select></div>
  {_medan("Judul panel", "judul", place="Pusat Bantuan")}
  {_medan("Deskripsi", "isi", place="Pilih tombol di bawah…", jenis="textarea")}
  <button type="submit">Buat &amp; kirim panel</button>
</form>
<p class="muted">Tombol/role pada panel ditambahkan lewat <code>/menu tombol</code> di Discord.
Panel yang sudah terkirim bisa disegarkan dengan <code>/menu ubah</code>.</p></div>
"""


# ==============================================================================
# DAFTAR KONTEN (dengan tombol hapus)
# ==============================================================================
def _tabel_konten(judul: str, jenis: str, items: list[dict], token: str, guild_id: int) -> str:
    if not items:
        return f'<div class="subpanel"><h3>{_esc(judul)}</h3><div class="muted">Belum ada.</div></div>'
    baris = ""
    for item in items:
        aksi = f"hapus.{jenis}:{item.get('id')}"
        baris += (
            f'<tr><td><b>{_esc(item.get("judul"))}</b>'
            f'<div class="muted">{_esc(item.get("ringkas") or "")}</div></td>'
            f'<td><form method="post" action="/api/konten">{_hidden(guild_id, token, aksi)}'
            '<button type="submit" class="danger">Hapus</button></form></td></tr>'
        )
    return (
        f'<div class="subpanel"><h3>{_esc(judul)}</h3>'
        f"<table><tbody>{baris}</tbody></table></div>"
    )


def render_konten_block(guild_id: int, konten: dict, token: str) -> str:
    """Daftar pengumuman/tautan/panel/formulir/webhook + tombol hapus."""
    return "".join(
        [
            _tabel_konten("⏰ Pengumuman", "pengumuman", konten.get("pengumuman") or [], token, guild_id),
            _tabel_konten("🔗 Tautan embed", "tautan", konten.get("tautan") or [], token, guild_id),
            _tabel_konten("🧩 Panel", "panel", konten.get("panel") or [], token, guild_id),
            _tabel_konten("📝 Formulir", "formulir", konten.get("formulir") or [], token, guild_id),
            _tabel_konten("🪄 Webhook identitas", "webhook", konten.get("webhook") or [], token, guild_id),
        ]
    )



__all__ = [
    "kontrol_html",
    "opsi_untuk",
    "pilihan_channel",
    "pilihan_role",
    "render_audit_block",
    "render_buat_block",
    "render_konten_block",
    "render_kirim_block",
    "render_setelan_block",
]
