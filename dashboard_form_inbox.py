"""Panel **Kotak masuk formulir** di halaman Buat konten — server-rendered, tanpa JS.

Semua jawaban `/menu form` (modal) masuk ke antrean ini, jadi staf bisa meninjaunya dari
dashboard tanpa bergantung pada channel tujuan. Jalur tulis: `POST /api/konten`
(`inbox-selesai:<nomor>`, `inbox-buka:<nomor>`, `inbox-hapus:<nomor>`).
"""

from __future__ import annotations

import time

import dashboard_ui


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _waktu(nilai: float) -> str:
    try:
        return time.strftime("%d %b %H:%M", time.localtime(float(nilai or 0)))
    except (OSError, ValueError):
        return "-"


def render_inbox_block(bot, guild_id: int, token: str) -> str:
    """Panel antrean submission formulir."""
    import modal_forms

    gid = int(guild_id or 0)
    data = modal_forms.statistik_inbox(gid)
    daftar = modal_forms.daftar_submission(gid, limit=15)

    if daftar:
        kartu = []
        for entri in daftar:
            nomor = int(entri.get("nomor") or 0)
            selesai = entri.get("status") == modal_forms.STATUS_SELESAI
            lencana = (
                '<span class="lencana ok">selesai</span>'
                if selesai
                else '<span class="lencana baru">baru</span>'
            )
            jawaban = "".join(
                f'<div class="medan-jawaban"><b>{dashboard_ui._esc(label)}</b>'
                f'<div class="muted">{dashboard_ui._esc(isi) or "<i>(kosong)</i>"}</div></div>'
                for label, isi in (entri.get("nilai") or {}).items()
            )
            if selesai:
                tombol_status = (
                    '<form method="post" action="/api/konten" class="baris-form">'
                    + dashboard_ui._hidden(gid, token, f"inbox-buka:{nomor}")
                    + '<button type="submit">Buka lagi</button></form>'
                )
            else:
                tombol_status = (
                    '<form method="post" action="/api/konten" class="baris-form">'
                    + dashboard_ui._hidden(gid, token, f"inbox-selesai:{nomor}")
                    + '<button type="submit">Tandai selesai</button></form>'
                )
            kartu.append(
                '<details class="kartu-inbox">'
                f'<summary>#{nomor} · <b>{dashboard_ui._esc(entri.get("form_nama"))}</b> · '
                f'{dashboard_ui._esc(entri.get("user_nama") or "member")} · '
                f'{_waktu(entri.get("dibuat"))} {lencana}</summary>'
                f'<div class="isi-inbox">{jawaban}</div>'
                '<div class="baris-aksi">'
                f"{tombol_status}"
                '<form method="post" action="/api/konten" class="baris-form">'
                + dashboard_ui._hidden(gid, token, f"inbox-hapus:{nomor}")
                + '<button type="submit" class="danger">Hapus</button></form>'
                "</div></details>"
            )
        isi = "".join(kartu)
    else:
        isi = (
            '<p class="muted">Belum ada jawaban formulir. Setiap kali member mengirim formulir '
            "lewat tombol panel, jawabannya muncul di sini.</p>"
        )

    status = (
        f'<p class="muted"><b>{data["baru"]}</b> baru · <b>{data["selesai"]}</b> selesai · '
        f'{data["total"]}/{data["maks"]} tersimpan'
        + (f" · terakhir {_waktu(data['terakhir'])}" if data["terakhir"] else "")
        + ".</p>"
    )
    if data["baru"]:
        status += (
            f'<p class="muted">🔔 Ada <b>{data["baru"]}</b> jawaban yang belum ditinjau.</p>'
        )

    return (
        '<div class="subpanel" id="p-form-inbox"><h3>📬 Kotak masuk formulir</h3>'
        '<p class="muted">Semua jawaban formulir (modal) disimpan sebagai antrean, jadi staf bisa '
        "meninjaunya dari HP tanpa membuka channel tujuan. Jawaban lebih tua dari "
        f"<b>{modal_forms.ANTREAN_SIMPAN_HARI} hari</b> dibersihkan otomatis.</p>"
        f"{status}{isi}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_inbox(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi kotak masuk → `(berhasil, pesan)`."""
    import modal_forms

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi.startswith("inbox-selesai:") or aksi.startswith("inbox-buka:"):
        nomor = _id(aksi.split(":", 1)[1])
        selesai = aksi.startswith("inbox-selesai:")
        if not modal_forms.tandai_submission(gid, nomor, selesai=selesai):
            return False, f"Submission #{nomor} tidak ditemukan."
        await modal_forms.save_to_disk()
        return True, (
            f"Submission #{nomor} ditandai **selesai**."
            if selesai
            else f"Submission #{nomor} dibuka kembali (**baru**)."
        )

    if aksi.startswith("inbox-hapus:"):
        nomor = _id(aksi.split(":", 1)[1])
        if not modal_forms.hapus_submission(gid, nomor):
            return False, f"Submission #{nomor} tidak ditemukan."
        await modal_forms.save_to_disk()
        return True, f"Submission #{nomor} dihapus dari antrean."

    return False, f"Aksi kotak masuk `{aksi or '-'}` tidak dikenal."
