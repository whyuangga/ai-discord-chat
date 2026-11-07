"""Kendali giveaway dari dashboard web — buat, hentikan, reroll, & template.

Dashboard hanya memakai fungsi yang sudah dipakai command Discord
(`engagement.py`), jadi tidak ada jalur kedua yang bisa menyimpang: syarat,
bobot, dan riwayat tetap satu sumber.

Prinsip:

1. **Whitelist aksi** — hanya `buat`, `akhiri`, `reroll`, `template-hapus`,
   `template-simpan` yang dikenal; sisanya ditolak dengan pesan jelas.
2. **Tanpa dependency baru** — semua data dari `data/engagement.json`.
3. **Aman untuk HP** — satu form kecil per aksi, tanpa JavaScript.
"""

import logging

import engagement

logger = logging.getLogger("gemini_bot.dashboard_giveaway")

AKSI_DIKENAL: tuple[str, ...] = (
    "buat",
    "akhiri",
    "reroll",
    "template-simpan",
    "template-hapus",
    "simpan-bawaan",
)


def _to_int(nilai: object, bawaan: int = 0) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bawaan


def _ringkas(cfg: dict) -> dict:
    """Satu baris giveaway untuk tabel dashboard."""
    message_id = _to_int(cfg.get("message_id"))
    riwayat = engagement.giveaway_history(message_id)
    terakhir = riwayat[-1] if riwayat else {}
    return {
        "message_id": message_id,
        "hadiah": str(cfg.get("prize") or "-"),
        "peserta": len(cfg.get("entries") or []),
        "pemenang": [int(x) for x in (cfg.get("winners") or [])],
        "selesai": bool(cfg.get("ended")),
        "berakhir": float(cfg.get("ends_at") or 0),
        "syarat": engagement.requirement_summary(cfg),
        "sisa_undi": engagement.reroll_pool_size(message_id),
        "aksi_terakhir": str(terakhir.get("aksi") or ""),
        "pelaku_terakhir": _to_int(terakhir.get("oleh")),
    }


def collect(guild_id: int) -> dict:
    """Semua data giveaway satu server untuk halaman dashboard."""
    gid = _to_int(guild_id)
    aktif: list[dict] = []
    selesai: list[dict] = []
    for cfg in engagement.guild_giveaways(gid):
        item = _ringkas(cfg)
        (selesai if item["selesai"] else aktif).append(item)
    return {
        "aktif": aktif,
        "selesai": selesai[:8],
        "total_selesai": len(selesai),
        "template": engagement.list_giveaway_templates(gid),
        "bawaan": engagement.default_giveaway_config(gid),
    }


async def _selesaikan(bot, gid: int, message_id: int, aksi: str, aktor: int = 0) -> tuple[bool, str]:
    """Akhiri atau reroll satu giveaway lalu perbarui pesannya di Discord."""
    cfg = engagement.giveaways.get(int(message_id))
    if cfg is None or _to_int(cfg.get("guild_id")) != int(gid):
        return False, "Giveaway itu tidak ditemukan di server ini."

    if aksi == "akhiri":
        if cfg.get("ended"):
            return False, "Giveaway itu sudah selesai — pakai **Reroll** untuk mengundi ulang."
        hasil = engagement.end_giveaway(message_id, actor_id=aktor)
    else:
        if not cfg.get("ended"):
            return False, "Giveaway masih berjalan. Hentikan dulu, baru diundi ulang."
        status, hasil = engagement.reroll_giveaway(message_id, actor_id=aktor)
        if status == "habis":
            return False, "Tidak ada peserta yang bisa diundi ulang lagi."
        if status != "ok":
            return False, "Reroll tidak bisa dijalankan sekarang."

    if hasil is None:
        return False, "Giveaway gagal diproses."
    await engagement.save_engagement_to_disk()
    await engagement._update_giveaway_message(bot, hasil)
    pemenang = [int(x) for x in (hasil.get("winners") or [])]
    if not pemenang:
        return True, f"Giveaway **{hasil.get('prize')}** ditutup, tetapi tidak ada pemenang."
    siapa = ", ".join(f"<@{uid}>" for uid in pemenang)
    kata = "ditutup" if aksi == "akhiri" else "diundi ulang"
    return True, f"Giveaway **{hasil.get('prize')}** {kata}. Pemenang: {siapa}."


async def buat(bot, gid: int, payload: dict) -> tuple[bool, str]:
    """Buat giveaway baru langsung dari dashboard."""
    import discord
    from views import GiveawayJoinView

    hadiah = str(payload.get("hadiah") or "").strip()
    if not hadiah:
        return False, "Nama hadiah tidak boleh kosong."
    channel_id = _to_int(payload.get("channel"))
    if channel_id <= 0:
        return False, "Pilih channel tempat giveaway dipasang."
    ambil = getattr(bot, "get_channel", None)
    channel = ambil(channel_id) if callable(ambil) else None
    if channel is None or not hasattr(channel, "send"):
        return False, "Channel itu tidak ditemukan di cache bot (atau bukan channel teks)."

    menit = max(1, _to_int(payload.get("menit"), 60))
    pemenang = max(1, min(20, _to_int(payload.get("pemenang"), 1)))
    syarat = engagement.normalize_requirements(
        level=max(0, _to_int(payload.get("level"))),
        account_age_days=max(0, _to_int(payload.get("umur"))),
    )
    bonus = {}
    role_bonus = _to_int(payload.get("role_bonus"))
    if role_bonus:
        bonus[str(role_bonus)] = max(1, min(5, _to_int(payload.get("bobot"), 1)))

    cfg_awal = {
        "prize": hadiah[:200],
        "winner_count": pemenang,
        "requirements": syarat,
        "bonus_roles": engagement.normalize_bonus_roles(bonus),
        "entries": [],
    }
    try:
        pesan = await channel.send(
            embed=engagement.build_giveaway_embed(cfg_awal), view=GiveawayJoinView()
        )
    except (discord.Forbidden, discord.HTTPException):
        return False, f"Gagal mengirim giveaway ke <#{channel_id}>. Cek izin **Kirim Pesan** & **Embed Links**."

    cfg = engagement.create_giveaway(
        guild_id=gid,
        channel_id=channel_id,
        message_id=pesan.id,
        prize=hadiah,
        host_id=0,
        seconds=menit * 60,
        winner_count=pemenang,
        requirements=syarat,
        bonus_roles=bonus,
    )
    await engagement.save_engagement_to_disk()
    return True, (
        f"Giveaway **{cfg['prize']}** dipasang di <#{channel_id}> — "
        f"{engagement.requirement_summary(cfg)}, berakhir "
        f"{engagement.format_timestamp(cfg['ends_at'], 'R')}."
    )


async def aksi(bot, guild_id: int, nama: str, payload: dict | None = None) -> tuple[bool, str]:
    """Jalankan satu aksi dashboard. `(berhasil, pesan)`."""
    data = payload or {}
    gid = _to_int(guild_id)
    aksi_nama = str(nama or "").strip().lower()
    jenis, _, nilai = aksi_nama.partition(":")

    if jenis == "buat":
        return await buat(bot, gid, data)
    if jenis in ("akhiri", "reroll"):
        message_id = _to_int(nilai) or _to_int(data.get("message_id"))
        if message_id <= 0:
            return False, "ID pesan giveaway tidak valid."
        return await _selesaikan(bot, gid, message_id, jenis, aktor=_to_int(data.get("oleh")))
    if jenis == "template-hapus":
        target = str(data.get("nama") or nilai or "").strip()
        if not target:
            return False, "Nama template tidak boleh kosong."
        if not engagement.delete_giveaway_template(gid, target):
            return False, f"Template `{target}` tidak ditemukan."
        await engagement.save_engagement_to_disk()
        return True, f"Template `{target}` dihapus."
    if jenis == "template-simpan":
        ok, pesan = engagement.save_giveaway_template(
            gid,
            str(data.get("nama") or "").strip(),
            winner_count=_to_int(data.get("pemenang"), 1),
            seconds=max(60, _to_int(data.get("menit"), 60) * 60),
            requirements=engagement.normalize_requirements(
                level=max(0, _to_int(data.get("level"))),
                account_age_days=max(0, _to_int(data.get("umur"))),
            ),
            bonus_roles=({str(_to_int(data.get("role_bonus"))): _to_int(data.get("bobot"), 1)}
                         if _to_int(data.get("role_bonus")) else {}),
        )
        if ok:
            await engagement.save_engagement_to_disk()
        return ok, pesan
    if jenis == "simpan-bawaan":
        engagement.set_giveaway_defaults(
            gid,
            winner_count=_to_int(data.get("pemenang"), 1),
            seconds=max(60, _to_int(data.get("menit"), 60) * 60),
            level=max(0, _to_int(data.get("level"))),
            account_age_days=max(0, _to_int(data.get("umur"))),
            bonus_role_id=_to_int(data.get("role_bonus")),
            bonus_weight=max(1, _to_int(data.get("bobot"), 1)),
            ping_everyone=str(data.get("ping") or "").lower() in ("on", "1", "true", "ya"),
        )
        await engagement.save_engagement_to_disk()
        return True, "Setelan bawaan giveaway disimpan."

    return False, f"Aksi giveaway `{aksi_nama or '-'}` tidak dikenal."
