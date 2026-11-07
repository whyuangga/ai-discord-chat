"""Panel dashboard `/bangun` — server-rendered, tanpa JavaScript.

Tema lokal tetap 0 kuota AI. Rencana (tema atau deskripsi AI) hanya disimpan sebagai
pratinjau; struktur Discord baru dibuat setelah operator menekan **Terapkan**. Rollback
hanya memanggil `server_builder.bongkar`, yang menghapus ID item tercatat `/bangun` secara berurutan.
"""

from __future__ import annotations

import html
import time

import server_builder as sb



def _esc(nilai: object) -> str:
    return html.escape(str(nilai or ""), quote=True)


def _field(gid: int, token: str, action: str) -> str:
    return (
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        f'<input type="hidden" name="guild" value="{int(gid or 0)}">'
        f'<input type="hidden" name="action" value="{_esc(action)}">'
    )


def _daftar_preview(snapshot: dict) -> str:
    """Pratinjau struktur dengan setiap nama di-escape (teks AI tidak jadi markup HTML)."""
    kategori = [str(x.get("name") or "") for x in (snapshot.get("categories") or [])]
    per_kategori: dict[str, list[str]] = {nama: [] for nama in kategori}
    for channel in snapshot.get("channels") or []:
        nama_kategori = str(channel.get("category") or "tanpa kategori")
        per_kategori.setdefault(nama_kategori, []).append(
            ("🔊 " if channel.get("type") == "voice" else "# ") + str(channel.get("name") or "")
        )
    bagian = []
    for nama, kanal in per_kategori.items():
        daftar = "".join(f"<li>{_esc(c)}</li>" for c in kanal[:40]) or "<li class=\"muted\">Belum ada channel</li>"
        bagian.append(f"<li><b>{_esc(nama)}</b><ul>{daftar}</ul></li>")
    roles = snapshot.get("roles") or []
    role_html = (
        "<p><b>Role:</b> " + ", ".join(f"<code>{_esc(x.get('name'))}</code>" for x in roles[:12]) + "</p>"
        if roles else "<p><b>Role:</b> tidak ada</p>"
    )
    return role_html + "<ul class=\"bangun-preview\">" + "".join(bagian) + "</ul>"


def render_bangun_block(bot, guild_id: int, token: str) -> str:
    """Panel tema, rancangan AI, konfirmasi, riwayat, dan bongkar aman."""
    gid = int(guild_id or 0)
    tema = sb.daftar_tema()
    opsi = "".join(
        f'<option value="{_esc(item["id"])}">{_esc(item["label"])}</option>' for item in tema
    )
    form_tema = (
        '<form method="post" action="/api/bangun" class="formgrid">'
        + _field(gid, token, "tema")
        + '<div class="medan"><label for="bangun-tema">Pilih tema siap pakai (0 kuota AI)</label>'
        f'<select id="bangun-tema" name="tema" required>{opsi}</select></div>'
        '<button type="submit">Pratinjau tema</button></form>'
    )
    form_ai = (
        '<form method="post" action="/api/bangun" class="formgrid">'
        + _field(gid, token, "rancang")
        + '<div class="medan"><label for="bangun-deskripsi">Deskripsikan server yang diinginkan (10–600 huruf)</label>'
        '<textarea id="bangun-deskripsi" name="deskripsi" minlength="10" maxlength="600" '
        'rows="4" required placeholder="Mis. komunitas fotografi, kelas pemula, galeri karya, dan sesi kritik mingguan"></textarea>'
        '</div><button type="submit">Rancang dengan AI</button></form>'
    )

    pending = sb.ambil_siap(gid)
    if pending and isinstance(pending.get("snapshot"), dict):
        snapshot = pending["snapshot"]
        ok, alasan = sb.validasi(snapshot)
        sumber = str(pending.get("sumber") or "rancangan")
        label = str((snapshot.get("meta") or {}).get("label") or "Rencana server")
        channel_count = len(snapshot.get("channels") or [])
        category_count = len(snapshot.get("categories") or [])
        role_count = len(snapshot.get("roles") or [])
        source_label = "Gemini" if sumber == "ai" else f"tema {sumber.split(':')[-1]}" if sumber.startswith("tema:") else sumber
        pending_html = (
            '<div class="subpanel" id="bangun-pratinjau"><h4>🔎 Pratinjau menunggu keputusan</h4>'
            f'<p><b>{_esc(label)}</b> · {_esc(source_label)} · {channel_count} channel · '
            f'{category_count} kategori · {role_count} role</p>'
            f'{_daftar_preview(snapshot)}'
        )
        if ok:
            pending_html += (
                '<p class="muted">Belum ada struktur yang dibuat. Tinjau pratinjau, lalu tekan '
                '<b>Terapkan</b> untuk mulai membuat item Discord.</p>'
                '<div class="baris-form">'
                '<form method="post" action="/api/bangun">'
                + _field(gid, token, "terapkan")
                + '<button type="submit">🏗️ Terapkan rencana ini</button></form>'
                '<form method="post" action="/api/bangun">'
                + _field(gid, token, "batal")
                + '<button type="submit" class="secondary">Batalkan pratinjau</button></form>'
                '</div>'
            )
        else:
            pending_html += f'<p class="galat">Rencana tidak valid: {_esc(alasan)}. Batalkan dan buat pratinjau baru.</p>'
        pending_html += "</div>"
    else:
        pending_html = '<p class="muted">Belum ada pratinjau yang menunggu. Memilih tema atau merancang dengan AI belum mengubah struktur server.</p>'

    daftar_riwayat = sb.daftar_riwayat(gid)
    if daftar_riwayat:
        riwayat = daftar_riwayat[-1]
        dibuat = riwayat.get("dibuat") or {}
        counts = [len(dibuat.get(k) or []) for k in ("roles", "categories", "channels")]
        waktu = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(riwayat.get("pada") or 0)))
        contoh = ", ".join(_esc(x) for x in (dibuat.get("channels") or [])[:8]) or "—"
        sebelumnya = list(reversed(daftar_riwayat[:-1]))
        if sebelumnya:
            daftar_sebelumnya = "<ul>" + "".join(
                "<li>"
                f"{_esc(item.get('label') or 'Rancangan')} · "
                f"{len((item.get('dibuat') or {}).get('roles') or [])} role · "
                f"{len((item.get('dibuat') or {}).get('categories') or [])} kategori · "
                f"{len((item.get('dibuat') or {}).get('channels') or [])} channel"
                "</li>"
                for item in sebelumnya[:10]
            ) + "</ul>"
        else:
            daftar_sebelumnya = '<p class="muted">Belum ada build sebelumnya.</p>'
        sejarah_html = (
            f'<p><b>Build terbaru — {_esc(riwayat.get("label") or "Rancangan")}</b> · {waktu} · '
            f'{counts[0]} role · {counts[1]} kategori · {counts[2]} channel</p>'
            f'<p class="muted">Contoh channel tercatat: {contoh}. '
            f'{len(sebelumnya)} build sebelumnya tersimpan.</p>'
            f'<details><summary>Build sebelumnya ({len(sebelumnya)})</summary>{daftar_sebelumnya}</details>'
            '<p class="muted">Rollback berurutan: bongkar build terbaru terlebih dahulu; setelah berhasil, '
            'build sebelumnya otomatis menjadi pilihan berikutnya.</p>'
            '<form method="post" action="/api/bangun" class="formgrid">'
            + _field(gid, token, "bongkar")
            + '<label class="centang"><input type="checkbox" name="konfirmasi" value="ya" required> '
            'Saya paham: hanya item yang tercatat dibuat oleh <code>/bangun</code> yang akan dihapus.</label>'
            '<button type="submit" class="danger">🧹 Bongkar build terbaru</button></form>'
        )
    else:
        sejarah_html = '<p class="muted">Belum ada riwayat pembangunan di server ini.</p>'

    return (
        '<div class="subpanel"><h3>🏗️ Bangun server</h3>'
        '<p class="muted">Mulai dari 15 tema lokal (0 kuota AI) atau minta Gemini merancang struktur. '
        'Tidak ada item yang dibuat sebelum tombol <b>Terapkan</b> ditekan. '
        'Pembangunan hanya menambah struktur; hak izin role tidak diubah.</p>'
        f'{form_tema}{form_ai}{pending_html}'
        '<div class="subpanel"><h4>📜 Riwayat &amp; rollback</h4>'
        '<p class="muted">Build dibongkar berurutan dari yang terbaru; '
        'item baru dicocokkan dengan ID Discord yang dicatat.</p>'
        f'{sejarah_html}</div></div>'
    )


def _guild(bot, guild_id: int):
    getter = getattr(bot, "get_guild", None)
    guild = getter(int(guild_id)) if callable(getter) else None
    if guild is None:
        guild = next(
            (g for g in (getattr(bot, "guilds", []) or []) if int(getattr(g, "id", 0) or 0) == int(guild_id)),
            None,
        )
    return guild


def _izin_bot(guild, *, butuh_role: bool) -> tuple[bool, str]:
    member = getattr(guild, "me", None)
    if member is None:
        return False, "Bot tidak dapat memverifikasi izinnya di server ini."
    izin = getattr(member, "guild_permissions", None)
    if izin is None:
        return False, "Izin bot tidak tersedia."
    if not bool(getattr(izin, "manage_channels", False)):
        return False, "Bot butuh izin **Manage Channels** untuk membuat/menghapus channel."
    if butuh_role and not bool(getattr(izin, "manage_roles", False)):
        return False, "Rencana ini mencakup role; bot butuh izin **Manage Roles**."
    return True, ""


async def _rancang_ai(guild_id: int, prompt: str) -> str:
    """Pakai generator command yang sama; hapus sesi sintetis setelah selesai."""
    import ai_handler

    thread_id = -time.time_ns()
    try:
        return await ai_handler.get_ai_response(thread_id, prompt, guild_id=guild_id)
    finally:
        ai_handler.thread_chats.pop(thread_id, None)
        try:
            await ai_handler.save_sessions_to_disk()
        except Exception:
            pass


async def proses_aksi(bot, guild_id: int, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi dashboard `/bangun`; hanya pemanggil HTTP ber-token yang memanggilnya."""
    gid = int(guild_id or 0)
    if gid <= 0:
        return False, "Pilih server Discord terlebih dahulu."
    aksi = str(payload.get("action") or payload.get("aksi") or "").strip().lower()
    guild = _guild(bot, gid)
    if guild is None:
        return False, "Bot tidak terhubung ke server yang dipilih."

    if aksi == "tema":
        key = sb.cari_tema(str(payload.get("tema") or ""))
        if not key:
            return False, "Tema tidak dikenali; pilih salah satu dari daftar."
        snapshot = sb.tema_ke_snapshot(key, nama_server=str(getattr(guild, "name", "")))
        sumber = f"tema:{key}"
    elif aksi == "rancang":
        deskripsi = " ".join(str(payload.get("deskripsi") or "").split())
        if len(deskripsi) < 10:
            return False, "Deskripsi minimal 10 huruf."
        if len(deskripsi) > 600:
            deskripsi = deskripsi[:600]
        snapshot, sumber = await sb.rancang(
            deskripsi,
            ai_call=lambda teks: _rancang_ai(gid, teks),
        )
        snapshot = sb.normalisasi(snapshot, label=str(getattr(guild, "name", "")))
    elif aksi == "batal":
        if sb.ambil_siap(gid) is None:
            return False, "Tidak ada pratinjau yang menunggu."
        sb.lupakan_siap(gid)
        return True, "Pratinjau dibatalkan — tidak ada yang dibuat."
    elif aksi == "terapkan":
        entri = sb.ambil_siap(gid)
        if not entri or not isinstance(entri.get("snapshot"), dict):
            return False, "Tidak ada pratinjau. Buat pratinjau tema atau AI terlebih dahulu."
        snapshot = sb.normalisasi(entri["snapshot"], label=str(getattr(guild, "name", "")))
        ok, alasan = sb.validasi(snapshot)
        if not ok:
            return False, f"Pratinjau ditolak saat validasi ulang: {alasan}"
        has_roles = bool(snapshot.get("roles"))
        boleh, pesan_izin = _izin_bot(guild, butuh_role=has_roles)
        if not boleh:
            return False, pesan_izin
        hasil, pesan = await sb.terapkan(
            guild, snapshot, actor_id=0, alasan="Bangun server via dashboard"
        )
        sb.lupakan_siap(gid)
        await sb.save_to_disk()
        dibuat = sum(int(hasil.get(k) or 0) for k in ("roles", "categories", "channels"))
        galat = hasil.get("errors") or []
        return dibuat > 0 or not galat, pesan
    elif aksi == "bongkar":
        if str(payload.get("konfirmasi") or "").strip().lower() != "ya":
            return False, "Centang konfirmasi rollback terlebih dahulu."
        riwayat = sb.riwayat.get(gid)
        if not riwayat:
            return False, "Belum ada riwayat pembangunan untuk dibongkar."
        tercatat = riwayat.get("dibuat") or {}
        boleh, pesan_izin = _izin_bot(
            guild, butuh_role=bool(tercatat.get("roles"))
        )
        if not boleh:
            return False, pesan_izin
        ok, pesan = await sb.bongkar(guild, gid=gid)
        if ok:
            await sb.save_to_disk()
        return ok, pesan
    else:
        return False, f"Aksi bangun `{aksi or '-'}` tidak dikenal."

    ok, alasan = sb.validasi(snapshot)
    if not ok:
        return False, alasan
    sb.simpan_siap(gid, snapshot, sumber=sumber)
    counts = (
        f"{len(snapshot.get('channels') or [])} channel, "
        f"{len(snapshot.get('categories') or [])} kategori, "
        f"{len(snapshot.get('roles') or [])} role"
    )
    asal = "Gemini" if sumber == "ai" else f"tema {sumber.split(':')[-1]}"
    return True, f"Pratinjau {asal} siap ({counts}). Belum ada item yang dibuat; tinjau lalu tekan Terapkan."


__all__ = ["proses_aksi", "render_bangun_block"]
