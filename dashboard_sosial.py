"""Panel **Notifikasi sosial** di halaman Konten & interaksi — server-rendered, tanpa JS.

Menampilkan semua langganan (YouTube, Twitch, TikTok/RSSHub, **Reddit**, **RSS/Atom**),
form tambah langganan, dan tombol hapus per langganan. Jalur tulis: `POST /api/konten`
(`sosial-tambah`, `sosial-hapus:<id>`).
"""

from __future__ import annotations

import dashboard_ui


def _esc(nilai: object) -> str:
    return dashboard_ui._esc(str(nilai if nilai is not None else ""))


def _id(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def _opsi_channel(guild, terpilih: int) -> str:
    kanal = list(getattr(guild, "text_channels", []) or [])[:80]
    if not kanal:
        return '<option value="0">— belum ada channel teks —</option>'
    return "".join(
        '<option value="{0}"{1}>#{2}</option>'.format(
            int(getattr(ch, "id", 0)),
            " selected" if int(getattr(ch, "id", 0)) == int(terpilih or 0) else "",
            _esc(getattr(ch, "name", "-")),
        )
        for ch in kanal
    )


def _opsi_role(guild) -> str:
    roles = list(getattr(guild, "roles", []) or [])[:80]
    opsi = ['<option value="0">— tanpa mention role —</option>']
    for role in roles:
        rid = int(getattr(role, "id", 0) or 0)
        if not rid or getattr(role, "is_default", lambda: False)():
            continue
        opsi.append(f'<option value="{rid}">@{_esc(getattr(role, "name", "-"))}</option>')
    return "".join(opsi)


def render_sosial_block(bot, guild_id: int, token: str) -> str:
    """Panel notifikasi sosial untuk halaman 🧩 Konten & interaksi."""
    import social_notify as sn

    gid = int(guild_id or 0)
    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    subs = sn.get_subscriptions(gid)

    opsi_platform = "".join(
        f'<option value="{key}">{meta["emoji"]} {_esc(meta["label"])}</option>'
        for key, meta in sn.PLATFORMS.items()
    )
    form = (
        '<form method="post" action="/api/konten" class="formgrid">'
        + dashboard_ui._hidden(gid, token, "sosial-tambah")
        + f'<div class="medan"><label>Platform</label>'
        f'<select name="platform" id="sosial-platform">{opsi_platform}</select></div>'
        '<div class="medan"><label>Nama akun / URL feed</label>'
        '<input type="text" name="target" placeholder="UC… / ninja / r/indonesia / https://…/feed.xml" required></div>'
        f'<div class="medan"><label>Channel notifikasi</label>'
        f'<select name="channel_id" required>{_opsi_channel(guild, 0)}</select></div>'
        f'<div class="medan"><label>Mention role (opsional)</label>'
        f'<select name="role_id">{_opsi_role(guild)}</select></div>'
        '<button type="submit">Tambah langganan</button></form>'
    )

    petunjuk = " ".join(
        f'<br>**{meta["emoji"]} {_esc(meta["label"])}** — {_esc(meta["hint"])}'
        for meta in sn.PLATFORMS.values()
    )
    if subs:
        baris = "".join(
            "<tr>"
            f'<td>{sn.PLATFORMS.get(sub.get("platform"), {}).get("emoji", "🔔")} '
            f'{_esc(sn.PLATFORMS.get(sub.get("platform"), {}).get("label", sub.get("platform")))}</td>'
            f'<td><code>{_esc(sn.feed_url(str(sub.get("platform") or ""), str(sub.get("target") or "")))}</code></td>'
            f'<td>#{_esc(getattr(guild.get_channel(int(sub.get("channel_id") or 0)), "name", "-") if guild else "-")}</td>'
            f'<td>{len(sub.get("seen") or [])}</td>'
            "<td>"
            '<form method="post" action="/api/konten" class="baris-form">'
            + dashboard_ui._hidden(gid, token, f"sosial-hapus:{sub.get('id', '')}")
            + '<button type="submit" class="danger">Hapus</button></form>'
            "</td></tr>"
            for sub in subs
        )
        tabel = (
            '<div class="tabel-wrap"><table class="tabel">'
            "<tr><th>Platform</th><th>Target / feed</th><th>Channel</th><th>Jejak</th><th></th></tr>"
            f"{baris}</table></div>"
        )
    else:
        tabel = (
            '<p class="muted">Belum ada langganan. Tambah lewat form di atas atau '
            "`/sosial tambah` — bot memeriksa feed secara berkala (tanpa AI).</p>"
        )

    return (
        '<div class="subpanel" id="p-sosial"><h3>🔔 Notifikasi sosial</h3>'
        '<p class="muted">Pantau unggahan YouTube, live Twitch, feed TikTok/RSSHub, '
        "<b>subreddit Reddit</b>, & <b>RSS/Atom</b> situs apa pun. Pemeriksaan memakai HTTP "
        "biasa (0 kuota AI); polling pertama hanya menandai item lama supaya tidak spam.</p>"
        f'<p class="muted"><b>{len(subs)}</b> dari <b>{sn.MAX_SUBS_PER_GUILD}</b> langganan '
        f'terpakai · Twitch <b>{"siap" if sn.twitch_configured() else "belum dikonfigurasi"}</b>.'
        f"{petunjuk}</p>{form}<h4>Langganan aktif</h4>{tabel}</div>"
    )


# ==============================================================================
# AKSI POST (dipanggil dari `POST /api/konten`)
# ==============================================================================
async def aksi_sosial(gid: int, aksi: str, payload: dict) -> tuple[bool, str]:
    """Jalankan satu aksi panel notifikasi sosial → `(berhasil, pesan)`."""
    import social_notify as sn

    aksi = str(aksi or "").strip().lower()
    gid = int(gid or 0)

    if aksi == "sosial-tambah":
        platform = str(payload.get("platform") or "").strip().lower()
        target = str(payload.get("target") or "").strip()
        channel_id = _id(payload.get("channel_id"))
        role_id = _id(payload.get("role_id")) or None
        if not platform or platform not in sn.PLATFORMS:
            return False, "Pilih platform yang tersedia dulu."
        if not channel_id:
            return False, "Pilih channel notifikasi dulu."
        try:
            sub = sn.add_subscription(gid, platform, target, channel_id, role_id=role_id)
        except ValueError as galat:
            return False, str(galat)
        await sn.save_social_to_disk()
        return True, (
            f"Langganan **{sn.PLATFORMS.get(platform, {}).get('label', platform)}** "
            f"`{sn.feed_url(platform, sub.get('target', ''))}` ditambahkan ke <#{channel_id}>."
        )

    if aksi.startswith("sosial-hapus:"):
        sub_id = aksi.split(":", 1)[1].strip()
        sub = sn.find_subscription(gid, sub_id)
        if sub is None:
            return False, "Langganan itu sudah tidak ada."
        sn.remove_subscription(gid, sub_id)
        await sn.save_social_to_disk()
        return True, f"Langganan `{sn.feed_url(str(sub.get('platform') or ''), str(sub.get('target') or ''))}` dihapus."

    return False, f"Aksi notifikasi sosial `{aksi or '-'}` tidak dikenal."
