"""Halaman dashboard AI untuk `/gambar`, prompt server, dan privasi per member.

Tanpa JavaScript. Gambar hanya diposting setelah operator menekan tombol pada form;
berkas acuan diproses di memori dan tidak disimpan. Dashboard token adalah kredensial
operator tunggal, bukan identitas Discord member, jadi ekspor/hapus data pribadi tetap
hanya lewat command ephemeral `/dataku` dan konfirmasi `/hapusdataku`.
"""

from __future__ import annotations

import base64
import html
import math
import time

import ai_user_settings as aus
import config

JEDA_GAMBAR_DETIK = 20
_JEDA_GAMBAR: dict[int, float] = {}


def _esc(nilai: object) -> str:
    return html.escape(str(nilai or ""), quote=True)


def _hidden(gid: int, token: str, action: str) -> str:
    return (
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<input type="hidden" name="guild" value="{int(gid or 0)}">'
        f'<input type="hidden" name="action" value="{_esc(action)}">'
    )


def _guild(bot, gid: int):
    getter = getattr(bot, "get_guild", None)
    guild = getter(int(gid)) if callable(getter) else None
    if guild is None:
        guild = next(
            (g for g in (getattr(bot, "guilds", []) or []) if int(getattr(g, "id", 0) or 0) == int(gid)),
            None,
        )
    return guild


def render_gambar_block(bot, guild_id: int, token: str) -> str:
    """Form `/gambar` untuk membuat/mengedit gambar lalu mengirimnya ke channel pilihan."""
    gid = int(guild_id or 0)
    guild = _guild(bot, gid)
    channels = list(getattr(guild, "text_channels", []) or []) if guild else []
    options = '<option value="" disabled selected>Pilih channel tujuan</option>'
    options += "".join(
        f'<option value="{int(ch.id)}"># {_esc(getattr(ch, "name", "channel"))}</option>'
        for ch in channels
        if int(getattr(ch, "id", 0) or 0) > 0
    )
    styles = '<option value="">Ikuti setelan channel</option>' + "".join(
        f'<option value="{_esc(name)}">{_esc(meta["emoji"])} {_esc(meta["label"])}</option>'
        for name, meta in config.STYLE_OPTIONS.items()
    )
    ratios = '<option value="">Ikuti setelan channel</option>' + "".join(
        f'<option value="{_esc(name)}">{_esc(meta["emoji"])} {_esc(name)}</option>'
        for name, meta in config.RATIO_OPTIONS.items()
    )
    form = (
        '<form method="post" action="/api/ai" enctype="multipart/form-data" class="formgrid">'
        + _hidden(gid, token, "gambar")
        + '<div class="medan"><label for="gambar-channel">Channel tujuan</label>'
        f'<select id="gambar-channel" name="channel_id" required>{options}</select></div>'
        '<div class="medan"><label for="gambar-prompt">Prompt gambar</label>'
        '<textarea id="gambar-prompt" name="prompt" maxlength="800" rows="4" required '
        'placeholder="Mis. ilustrasi suasana senja di Surabaya, gaya poster film"></textarea></div>'
        '<div class="medan"><label for="gambar-style">Gaya</label>'
        f'<select id="gambar-style" name="style">{styles}</select></div>'
        '<div class="medan"><label for="gambar-ratio">Rasio</label>'
        f'<select id="gambar-ratio" name="ratio">{ratios}</select></div>'
        '<div class="medan"><label for="gambar-acuan">Gambar acuan (opsional)</label>'
        '<input id="gambar-acuan" type="file" name="acuan" accept="image/png,image/jpeg,image/webp,image/gif"></div>'
        '<button type="submit">🎨 Buat &amp; kirim gambar</button></form>'
    )
    return (
        '<div class="subpanel"><p class="muted">Hasil akan diposting ke channel yang dipilih. '
        f'Jeda dashboard: {JEDA_GAMBAR_DETIK} detik/server. Panggilan gambar memakai kuota AI; '
        'tema/stiker lokal tidak berlaku di sini. Gambar acuan untuk edit membutuhkan Gemini Paid Tier.</p>'
        f'{form}</div>'
    )


def render_prompt_server_block(guild_id: int, token: str) -> str:
    """Editor prompt kepribadian AI per server (sama dengan `/setelan-ai prompt-server`)."""
    gid = int(guild_id or 0)
    isi = aus.get_server_prompt(gid)
    return (
        '<div class="subpanel"><p class="muted">Kepribadian server menambah arahan gaya '
        'pada balasan AI di server ini. Maksimal 500 huruf; kosongkan lalu simpan untuk menghapus.</p>'
        '<form method="post" action="/api/ai" class="formgrid">'
        + _hidden(gid, token, "prompt-server")
        + '<div class="medan"><label for="ai-prompt-server">Prompt kepribadian server</label>'
        f'<textarea id="ai-prompt-server" name="prompt_server" maxlength="500" rows="4" '
        f'placeholder="Mis. ramah, ringkas, dan suka memberi contoh">{_esc(isi)}</textarea></div>'
        '<button type="submit">Simpan kepribadian AI server</button></form>'
        '<p class="muted">Preferensi pribadi (temperature, bahasa, panjang jawaban, rasio gambar) '
        'tetap diatur masing-masing member dengan <code>/setelan-ai atur</code>.</p></div>'
    )


def render_privasi_block() -> str:
    """Informasi jalur privasi mandiri yang tetap terikat pada identitas Discord member."""
    return (
        '<div class="subpanel"><p>Member dapat mengunduh atau menghapus datanya sendiri '
        'langsung di Discord:</p>'
        '<ul><li><code>/dataku</code> — ekspor data milik akun yang menjalankan command; '
        'balasan hanya terlihat olehnya.</li>'
        '<li><code>/hapusdataku</code> — minta penghapusan, lalu konfirmasi lewat tombol '
        'ephemeral milik akun tersebut.</li></ul>'
        '<p class="muted">Dashboard memakai satu token operator dan tidak mengetahui siapa '
        'yang sedang berada di browser. Karena itu dashboard tidak meminta ID member atau '
        'menampilkan data pribadi orang lain; ekspor/penghapusan tetap diverifikasi Discord.</p></div>'
    )


def _channel(guild, channel_id: int):
    text_channels = list(getattr(guild, "text_channels", []) or [])
    channel = next((ch for ch in text_channels if int(getattr(ch, "id", 0) or 0) == channel_id), None)
    if channel is None:
        getter = getattr(guild, "get_channel", None)
        channel = getter(channel_id) if callable(getter) else None
        if channel not in text_channels:
            return None
    return channel


def _reference(payload: dict) -> tuple[list[dict] | None, str]:
    """Baca gambar acuan multipart ke inlineData tervalidasi; tidak pernah ditulis ke disk."""
    field = payload.get("acuan")
    if field is None:
        return None, ""
    stream = getattr(field, "file", None)
    nama = str(getattr(field, "filename", "") or "acuan.png")
    if stream is None or not hasattr(stream, "read"):
        return None, "Lampiran gambar tidak terbaca."
    import dashboard_unggah

    try:
        stream.seek(0)
    except (AttributeError, OSError, ValueError):
        pass
    try:
        data = stream.read(dashboard_unggah.batas_byte() + 1)
    except Exception:
        return None, "Lampiran gambar gagal dibaca."
    if not isinstance(data, bytes):
        return None, "Lampiran gambar tidak valid."
    ekstensi, galat = dashboard_unggah.periksa(data, nama)
    if galat:
        return None, galat
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(ekstensi, "")
    if not mime:
        return None, "Format gambar acuan tidak didukung."
    return [{"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}}], ""


def _ingat_gambar(channel_id: int, berkas) -> None:
    """Berbagi hasil terakhir dengan `/gambar edit` (memori saja, tidak disimpan ke disk)."""
    try:
        import cogs.gambar_cog as gambar_cog

        berkas.fp.seek(0)
        data = base64.b64encode(berkas.fp.read()).decode("ascii")
        gambar_cog._terakhir[int(channel_id)] = (
            {"inlineData": {"mimeType": "image/png", "data": data}},
            "gambar-terakhir.png",
        )
        berkas.fp.seek(0)
    except Exception:  # pragma: no cover - best effort untuk fileobj yang sudah ditutup
        return


async def proses_aksi(bot, guild_id: int, payload: dict) -> tuple[bool, str]:
    """Jalankan pembuatan gambar atau simpan prompt server; token diverifikasi di router."""
    gid = int(guild_id or 0)
    if gid <= 0:
        return False, "Pilih server Discord terlebih dahulu."
    guild = _guild(bot, gid)
    if guild is None:
        return False, "Bot tidak terhubung ke server yang dipilih."
    action = str(payload.get("action") or payload.get("aksi") or "").strip().lower()

    if action == "prompt-server":
        prompt = str(payload.get("prompt_server") or "")
        if len(prompt) > aus.MAKS_PROMPT_SERVER:
            return False, f"Prompt server maksimal {aus.MAKS_PROMPT_SERVER} huruf."
        hasil = aus.set_server_prompt(gid, prompt, oleh=0)
        await aus.save_to_disk()
        return True, (
            f"Kepribadian AI server disimpan ({len(hasil)} huruf)." if hasil
            else "Kepribadian AI server dihapus; kembali ke setelan bawaan."
        )

    if action != "gambar":
        return False, "Aksi AI tidak dikenal."

    prompt = " ".join(str(payload.get("prompt") or "").split())
    if len(prompt) < 3:
        return False, "Prompt gambar minimal 3 huruf."
    if len(prompt) > 800:
        return False, "Prompt gambar maksimal 800 huruf."
    channel_id = _to_int(payload.get("channel_id"))
    channel = _channel(guild, channel_id)
    if channel is None:
        return False, "Pilih channel teks tujuan yang ada di server ini."

    style = str(payload.get("style") or "").strip()
    ratio = str(payload.get("ratio") or "").strip()
    if style and style not in config.STYLE_OPTIONS:
        return False, "Pilihan gaya gambar tidak valid."
    if ratio and ratio not in config.RATIO_OPTIONS:
        return False, "Pilihan rasio gambar tidak valid."

    terakhir = _JEDA_GAMBAR.get(gid)
    if terakhir is not None:
        sisa = terakhir + JEDA_GAMBAR_DETIK - time.monotonic()
        if sisa > 0:
            return False, (
                f"Tunggu {max(1, math.ceil(sisa))} detik sebelum permintaan gambar berikutnya di dashboard."
            )

    reference, galat = _reference(payload)
    if galat:
        return False, galat

    izin = None
    me = getattr(guild, "me", None)
    periksa_izin = getattr(channel, "permissions_for", None)
    if me is not None and callable(periksa_izin):
        izin = periksa_izin(me)
    if izin is not None and not bool(getattr(izin, "send_messages", False)):
        return False, "Bot tidak punya izin **Send Messages** di channel itu."
    if izin is not None and not bool(getattr(izin, "attach_files", False)):
        return False, "Bot tidak punya izin **Attach Files** di channel itu."

    _JEDA_GAMBAR[gid] = time.monotonic()
    import ai_handler

    engine, berkas, galat = await ai_handler.generate_image(
        channel_id,
        prompt,
        reference_images=reference,
        http_session=getattr(bot, "http_session", None),
        style=style or None,
        ratio=ratio or None,
    )
    if berkas is None:
        return False, f"Gambar gagal dibuat: {galat or 'tidak ada detail.'}"

    _ingat_gambar(channel_id, berkas)
    try:
        await channel.send(content=f"🎨 Gambar AI dari dashboard · `{_esc(engine or 'AI')}`", file=berkas)
    except Exception as exc:
        return False, f"Gambar berhasil dibuat, tetapi gagal dikirim ({type(exc).__name__})."
    return True, f"Gambar berhasil dikirim ke <#{channel_id}> ({engine or 'AI'})."


def _to_int(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def reset_state() -> None:
    """Kosongkan jeda dashboard (dipakai tes)."""
    _JEDA_GAMBAR.clear()


__all__ = [
    "proses_aksi",
    "render_gambar_block",
    "render_privasi_block",
    "render_prompt_server_block",
    "reset_state",
]
