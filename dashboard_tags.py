"""Panel **Tags** di halaman Konten & interaksi (server-rendered, tanpa JavaScript).

Staf bisa membuat/mengubah/menghapus tag langsung dari HP, melihat tag mana yang
paling sering dipakai, dan mematikan fitur tag tanpa menghapus datanya.
"""

from __future__ import annotations

import dashboard_ui


def _ringkas(teks: object, panjang: int = 90) -> str:
    isi = " ".join(str(teks or "").split())
    return isi[:panjang] + ("…" if len(isi) > panjang else "")


def simpan_tag(guild_id: int, payload: dict) -> tuple[bool, str]:
    """Menyimpan tag dari form dashboard (buat bila baru, perbarui bila sudah ada)."""
    import tags

    nama = str(payload.get("nama") or "").strip()
    isi = str(payload.get("isi") or "").strip()
    kunci = tags.normalisasi(nama)
    if not kunci:
        return False, "Nama tag tidak boleh kosong."
    if len(isi) < 3:
        return False, "Isi tag terlalu pendek (minimal 3 huruf)."

    if tags.ambil(guild_id, kunci) is not None:
        kode, tag = tags.ubah(guild_id, kunci, isi)
    else:
        kode, tag = tags.tambah(guild_id, kunci, isi)
    if kode == "penuh":
        return False, f"Server sudah punya {tags.MAX_TAG_PER_GUILD} tag (batas maksimum)."
    if kode != "ok" or tag is None:
        return False, f"Tag `{kunci}` gagal disimpan ({kode})."
    return True, f"Tag `{tag['nama']}` disimpan. Panggil dengan `/tag lihat nama:{tag['nama']}`."


def render_tags_block(bot, guild_id: int, token: str) -> str:
    """Panel tag: statistik, form simpan, tabel tag + hapus, & sakelar aktif."""
    import tags

    gid = int(guild_id or 0)
    data = tags.statistik(gid)
    daftar = tags.daftar(gid, limit=50)
    lencana = (
        '<span class="lencana on">aktif</span>'
        if data["aktif"]
        else '<span class="lencana off">dimatikan</span>'
    )
    teratas = (
        " · paling dipakai: "
        + ", ".join(f"`{t['nama']}` ({t['dipakai']}×)" for t in data["teratas"] if t["dipakai"])
        if any(t["dipakai"] for t in data["teratas"])
        else ""
    )
    status = (
        f'<p class="muted">Status: {lencana} · <b>{data["total"]}</b>/{data["batas"]} tag · '
        f"total dipanggil <b>{data['dipakai']}</b>×{teratas}</p>"
    )

    sakelar = (
        '<form method="post" action="/api/konten" class="baris-form">'
        + dashboard_ui._hidden(gid, token, "tag-aktif:0" if data["aktif"] else "tag-aktif:1")
        + f'<button type="submit">{"Matikan fitur tag" if data["aktif"] else "Aktifkan fitur tag"}</button>'
        "</form>"
    )

    form = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "tag-simpan")
        + '<div class="medan"><label>Nama tag</label>'
        '<input type="text" name="nama" maxlength="32" placeholder="mis. aturan-server"></div>'
        '<div class="medan"><label>Isi tag (maks 1800 huruf)</label>'
        '<textarea name="isi" rows="4" maxlength="1800" '
        'placeholder="Teks yang dikirim saat member memanggil tag ini"></textarea></div>'
        '<button type="submit">Simpan tag</button></form>'
    )

    if not daftar:
        tabel = (
            '<p class="muted">Belum ada tag. Buat yang pertama lewat form di atas '
            "atau dengan <code>/tag buat</code> di Discord.</p>"
        )
    else:
        baris = []
        for tag in daftar:
            baris.append(
                "<tr>"
                f'<td><code>{dashboard_ui._esc(tag.get("nama"))}</code></td>'
                f'<td>{dashboard_ui._esc(_ringkas(tag.get("isi")))}</td>'
                f'<td>{int(tag.get("dipakai") or 0)}×</td>'
                "<td>"
                '<form method="post" action="/api/konten" class="baris-form">'
                + dashboard_ui._hidden(gid, token, f"tag-hapus:{tag.get('nama')}")
                + '<button type="submit" class="danger">Hapus</button></form>'
                "</td></tr>"
            )
        tabel = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>Nama</th><th>Isi</th><th>Dipakai</th><th></th></tr>"
            f"{''.join(baris)}</table></div>"
        )

    return (
        '<div class="subpanel" id="p-tag"><h3>🏷️ Tag jawaban siap pakai</h3>'
        '<p class="muted">Simpan jawaban sekali, panggil kapan saja dengan '
        "<code>/tag lihat nama:…</code>. <b>0 kuota AI</b> — isi tag tidak pernah dikirim "
        "ke Gemini, jadi aman untuk aturan, harga, & jadwal server.</p>"
        f"{status}{sakelar}{form}{tabel}</div>"
    )
