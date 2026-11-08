"""Blok kontrol fitur (dropdown on/off) untuk halaman utama dashboard.

Murni presentasi: menerima `guild_id`, mengembalikan HTML. Tidak menyentuh
request maupun sesi.
"""

from __future__ import annotations

import html


LEVEL_OPTIONS = [("on", "Aktif"), ("off", "Nonaktif")]
FITUR_SEDERHANA = {
    "level": "Level & XP",
    "ekonomi": "Ekonomi koin",
    "tumbuh": "Pertumbuhan & invite",
}
def dashboard_controls(guild_id: int) -> dict:
    """Status ringkas fitur yang bisa dinyalakan/dimatikan dari dashboard."""
    import antinuke
    import antispam
    import economy
    import growth_tracker
    import levels

    gid = int(guild_id or 0)
    # Level dibaca lewat `is_leveling_active` (tidak membuat config default seperti
    # `get_level_config` — dulu itu membuat fitur menyala lagi setelah dimatikan).
    econ_cfg = economy.get_config(gid) if gid else {}
    growth_cfg = growth_tracker.get_config(gid) if gid else {}
    spam_cfg = antispam.get_spam_config(gid) if gid else {}
    nuke_cfg = antinuke.get_config(gid) if gid else {}

    return {
        "guild": gid,
        "level": "on" if levels.is_leveling_active(gid) else "off",
        "ekonomi": "on" if econ_cfg.get("enabled") else "off",
        "tumbuh": "on" if growth_cfg.get("enabled", True) else "off",
        "antispam": str(spam_cfg.get("mode")) if spam_cfg.get("enabled") else "off",
        "antinuke": str(nuke_cfg.get("action") or "lapor"),
    }
async def apply_dashboard_action(guild_id: int, action: str, value: str) -> tuple[bool, str]:
    """Menjalankan satu aksi tulis dari dashboard. `(berhasil, pesan)`."""
    import antinuke
    import antispam
    import economy
    import growth_tracker
    import levels

    gid = int(guild_id or 0)
    if not gid:
        return False, "Server tidak dikenali."
    act = str(action or "").strip().lower()
    val = str(value or "").strip().lower()

    # Panel tampilan sambutan & perpisahan (Card/Embed/Text/Container + template).
    if act.startswith(("sambutan.", "pamit.")):
        import dashboard_sambutan

        hasil = await dashboard_sambutan.aksi_sambutan(None, gid, action, value)
        if hasil is None:  # pragma: no cover - awalan sudah dijaga di atas
            return False, f"Aksi `{action}` tidak dikenal."
        return hasil

    if act == "level":
        if val not in ("on", "off"):
            return False, "Nilai level harus `on` atau `off`."
        setter = getattr(levels, "set_level_enabled", None)
        if callable(setter):
            setter(gid, val == "on")
        else:  # pragma: no cover - versi lama
            levels.set_level_config(gid, enabled=(val == "on"))
        await levels.save_levels_to_disk()
        return True, f"Level & XP sekarang **{'aktif' if val == 'on' else 'nonaktif'}**."

    if act == "ekonomi":
        if val not in ("on", "off"):
            return False, "Nilai ekonomi harus `on` atau `off`."
        economy.set_config(gid, aktif=(val == "on"))
        await economy.save_economy_to_disk()
        return True, f"Ekonomi koin sekarang **{'aktif' if val == 'on' else 'nonaktif'}**."

    if act == "tumbuh":
        if val not in ("on", "off"):
            return False, "Nilai pertumbuhan harus `on` atau `off`."
        growth_tracker.set_config(gid, enabled=(val == "on"))
        await growth_tracker.save_growth_to_disk()
        return True, f"Pelacakan pertumbuhan **{'aktif' if val == 'on' else 'nonaktif'}**."

    if act == "antispam":
        if val == "off":
            antispam.set_spam_config(gid, aktif=False)
            await antispam.save_antispam_to_disk()
            return True, "Anti-spam **dimatikan**."
        if val not in antispam.SPAM_MODES:
            return False, "Mode anti-spam tidak dikenal."
        antispam.set_spam_config(gid, mode=val)
        await antispam.save_antispam_to_disk()
        return True, f"Anti-spam aktif dengan mode **{val}**."

    if act == "antinuke":
        if val not in antinuke.PUNISH_CHOICES:
            return False, "Aksi anti-nuke tidak dikenal."
        antinuke.set_config(gid, action=val)
        await antinuke.save_antinuke_to_disk()
        return True, f"Anti-Nuke memakai aksi **{val}**."

    return False, f"Aksi `{act or '-'}` tidak didukung (hanya: level, ekonomi, tumbuh, antispam, antinuke)."
def render_controls_block(guild_id: int, token: str) -> str:
    """Saklar cepat: tombolnya mengikuti keadaan (Aktif → "Nonaktifkan")."""
    import antinuke
    import antispam

    state = dashboard_controls(guild_id)
    hidden = (
        f'<input type="hidden" name="token" value="{html.escape(token)}">'
        f'<input type="hidden" name="guild" value="{int(guild_id or 0)}">'
    )

    def _saklar(action: str, label: str, aktif: bool) -> str:
        """Satu tombol: label menyebut aksi berikutnya, bukan keadaan sekarang."""
        tujuan = "off" if aktif else "on"
        teks = "Nonaktifkan" if aktif else "Aktifkan"
        kelas = ' class="danger"' if aktif else ""
        tanda = "✅" if aktif else "⬜"
        return (
            f'<form method="post" action="/api/aksi" class="kontrol">'
            f'{hidden}<input type="hidden" name="action" value="{action}">'
            f'<input type="hidden" name="value" value="{tujuan}">'
            f'<label>{tanda} {html.escape(label)} '
            f'<span class="muted">({"aktif" if aktif else "nonaktif"})</span></label>'
            f'<button type="submit"{kelas}>{teks}</button></form>'
        )

    def _pilih(action: str, label: str, options: list[tuple[str, str]], current: str) -> str:
        opts = "".join(
            f'<option value="{html.escape(value)}"'
            + (" selected" if value == current else "")
            + f'>{html.escape(text)}</option>'
            for value, text in options
        )
        return (
            f'<form method="post" action="/api/aksi" class="kontrol">'
            f'{hidden}<input type="hidden" name="action" value="{action}">'
            f'<label>{html.escape(label)}</label>'
            f'<select name="value">{opts}</select>'
            f'<button type="submit">Simpan</button></form>'
        )

    sp_options = [("off", "Mati")] + [(key, key.capitalize()) for key in antispam.SPAM_MODES]
    nuke_options = [(key, key) for key in antinuke.PUNISH_CHOICES]

    return "".join(
        [
            _saklar("level", "📈 Level & XP", state["level"] == "on"),
            _saklar("ekonomi", "💰 Ekonomi koin", state["ekonomi"] == "on"),
            _saklar("tumbuh", "🌱 Pertumbuhan & invite", state["tumbuh"] == "on"),
            _pilih("antispam", "🚨 Anti-spam", sp_options, state["antispam"]),
            _pilih("antinuke", "🛡️ Anti-Nuke (aksi)", nuke_options, state["antinuke"]),
        ]
    )
