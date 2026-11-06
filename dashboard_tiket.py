"""Kotak masuk tiket dari dashboard web (tanpa login, cukup token pemilik bot).

Isi modul:

- `collect_tiket(guild_id)` — daftar tiket terbuka/diklaim + statistik ringkas.
- `balas(bot, guild_id, thread_id, teks, identitas="")` — kirim balasan staf ke thread
  tiket (sebagai bot, atau lewat identitas webhook supaya nama pengirim jelas).
- `tutup(bot, guild_id, thread_id)` — tutup tiket: transkrip, kunci + arsip thread,
  lalu simpan ke `data/tickets.json` (perilaku sama dengan `/tiket tutup`).

Semua fungsi mengembalikan `(berhasil, pesan)` berbahasa Indonesia dan **tidak**
memakai kuota AI.
"""

import logging
import time

logger = logging.getLogger("gemini_bot.dashboard_tiket")

STATUS_LABEL = {
    "terbuka": "🟢 Terbuka",
    "diklaim": "🟡 Diklaim",
    "selesai": "⚪ Selesai",
}
MAX_BALAS = 1800


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _umur(jam: float) -> str:
    menit = max(0, int(jam * 60))
    if menit < 60:
        return f"{menit} mnt"
    if menit < 60 * 48:
        return f"{menit // 60} jam"
    return f"{menit // (60 * 24)} hari"


def _milik_server(data: dict, guild_id: int) -> bool:
    return _to_int(data.get("guild_id")) == _to_int(guild_id)


def collect_tiket(guild_id: int, *, limit: int = 20) -> dict:
    """Daftar tiket yang belum selesai + statistik singkat untuk dashboard."""
    import tickets

    gid = _to_int(guild_id)
    sekarang = time.time()
    aktif: list[dict] = []
    try:
        semua = tickets.list_tickets(gid, limit=max(1, int(limit) * 3))
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Gagal membaca daftar tiket: %s", exc)
        semua = []

    for data in semua:
        if data.get("status") == "selesai":
            continue
        dibuat = float(data.get("created_at") or 0)
        aktivitas = float(data.get("last_activity") or dibuat)
        sla = 0
        try:
            sla = int((tickets.get_ticket_config(gid) or {}).get("sla_jam") or 0)
        except Exception:  # pragma: no cover
            sla = 0
        lewat_sla = bool(sla and not data.get("first_response_at") and (sekarang - dibuat) > sla * 3600)
        aktif.append(
            {
                "id": str(_to_int(data.get("thread_id"))),
                "nomor": f"#{_to_int(data.get('number')):04d}",
                "pemilik": str(_to_int(data.get("user_id"))),
                "topik": str(data.get("topic") or "")[:120],
                "status": str(data.get("status") or "terbuka"),
                "status_label": STATUS_LABEL.get(str(data.get("status")), "🟢 Terbuka"),
                "diklaim": str(_to_int(data.get("claimed_by"))) if data.get("claimed_by") else "",
                "umur": _umur((sekarang - dibuat) / 3600) if dibuat else "-",
                "diam": _umur((sekarang - aktivitas) / 3600) if aktivitas else "-",
                "sla": lewat_sla,
                "sla_jam": sla,
            }
        )
        if len(aktif) >= max(1, int(limit)):
            break

    statistik: dict = {"aktif": len(aktif), "diklaim": 0, "lewat_sla": 0, "rating": "-"}
    try:
        statistik["diklaim"] = sum(1 for item in aktif if item["diklaim"])
        statistik["lewat_sla"] = sum(1 for item in aktif if item["sla"])
        ringkas = tickets.rating_summary(gid) or {}
        rata = ringkas.get("rata") or ringkas.get("average") or 0
        jumlah = ringkas.get("jumlah") or ringkas.get("count") or 0
        statistik["rating"] = f"{float(rata):.1f} ★ ({int(jumlah)})" if jumlah else "-"
        cfg = tickets.get_ticket_config(gid)
        statistik["aktifkan"] = bool(cfg.get("enabled"))
        statistik["maks"] = int(cfg.get("max_open") or 0)
        statistik["sla_jam"] = int(cfg.get("sla_jam") or 0)
    except Exception:  # pragma: no cover - jaring aman
        pass
    return {"guild": gid, "items": aktif, "statistik": statistik}


async def _thread(bot, guild_id: int, thread_id: int):
    """Ambil thread tiket (cache dulu, lalu fetch) & pastikan milik server ini."""
    import discord

    tid = _to_int(thread_id)
    if tid <= 0:
        return None
    channel = None
    getter = getattr(bot, "get_channel", None)
    if callable(getter):
        channel = getter(tid)
    if channel is None:
        fetcher = getattr(bot, "fetch_channel", None)
        if callable(fetcher):
            try:
                channel = await fetcher(tid)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
    if channel is None:
        return None
    guild = getattr(channel, "guild", None)
    if guild is not None and _to_int(getattr(guild, "id", 0)) != _to_int(guild_id):
        return None
    return channel


async def balas(
    bot, guild_id: int, thread_id: int, teks: str, *, identitas: str = ""
) -> tuple[bool, str]:
    """Kirim balasan staf ke thread tiket. `identitas` = nama webhook (opsional)."""
    import discord

    import tickets
    import webhook_identity

    gid = _to_int(guild_id)
    data = tickets.get_ticket(_to_int(thread_id))
    if data is None or not _milik_server(data, gid):
        return False, "Tiket tidak ditemukan di server ini."
    if data.get("status") == "selesai":
        return False, "Tiket ini sudah ditutup — balasan tidak dikirim."

    isi = str(teks or "").strip()[:MAX_BALAS]
    if not isi:
        return False, "Teks balasan tidak boleh kosong."

    thread = await _thread(bot, gid, thread_id)
    if thread is None:
        return False, "Thread tiket tidak bisa diakses (mungkin sudah dihapus atau diarsip)."

    nomor = f"#{_to_int(data.get('number')):04d}"
    nama = str(identitas or "").strip()[:80]
    if nama:
        ok, pesan = await webhook_identity.kirim_sebagai(thread, nama=nama, isi=isi)
        if not ok:
            return False, pesan or "Gagal mengirim balasan lewat webhook."
    else:
        try:
            await thread.send(content=isi, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            return False, "Bot tidak punya izin menulis di thread tiket itu."
        except discord.HTTPException as exc:
            logger.warning("Balas tiket dari dashboard gagal: %s", exc)
            return False, "Discord menolak balasan itu (thread mungkin terkunci)."

    tickets.record_activity(_to_int(thread_id))
    try:
        tickets.record_first_response(_to_int(thread_id), 0)
    except Exception:  # pragma: no cover - jaring aman
        pass
    await tickets.save_tickets_to_disk()
    return True, f"Balasan terkirim ke tiket {nomor}."


async def tutup(bot, guild_id: int, thread_id: int) -> tuple[bool, str]:
    """Tutup tiket dari dashboard: transkrip → kunci & arsip thread → simpan."""
    import discord

    import tickets

    gid = _to_int(guild_id)
    data = tickets.get_ticket(_to_int(thread_id))
    if data is None or not _milik_server(data, gid):
        return False, "Tiket tidak ditemukan di server ini."
    if data.get("status") == "selesai":
        return False, "Tiket ini sudah ditutup sebelumnya."

    thread = await _thread(bot, gid, thread_id)
    if thread is None:
        return False, "Thread tiket tidak bisa diakses (mungkin sudah dihapus)."

    bot_id = _to_int(getattr(getattr(bot, "user", None), "id", 0))
    status, closed = tickets.close_ticket(
        _to_int(thread_id), bot_id, reason="dashboard"
    )
    if closed is None:
        return False, "Tiket gagal ditutup."
    await tickets.save_tickets_to_disk()

    nomor = f"#{_to_int(closed.get('number')):04d}"
    dikirim = False
    try:
        pesan = await tickets.collect_thread_messages(thread)
        teks, nama_berkas = tickets.build_transcript(closed, pesan)
        dikirim = await tickets.send_transcript(bot, closed, teks, nama_berkas)
    except Exception as exc:  # pragma: no cover - transkrip opsional
        logger.warning("Transkrip tiket dari dashboard gagal: %s", exc)

    try:
        await thread.edit(
            name=f"tiket-{_to_int(closed.get('number')):04d}-selesai"[:100],
            locked=True,
            archived=True,
            reason="Tiket ditutup lewat dashboard web",
        )
    except (discord.Forbidden, discord.HTTPException):
        pass

    return True, (
        f"Tiket {nomor} ditutup"
        + (" dan transkrip dikirim ke channel log." if dikirim else " (channel log transkrip belum diatur).")
    )


# ==============================================================================
# PANEL TIKET (setara /tiket panel, dari browser)
# ==============================================================================
async def _saluran(bot, guild_id: int, channel_id: int):
    """Cari channel server ini (cache dulu, lalu fetch) — `None` bila tidak ada."""
    return await _thread(bot, guild_id, channel_id)


async def pasang_panel(bot, guild_id: int, data: dict) -> tuple[bool, str]:
    """Pasang panel `Buat Tiket` di channel dari dashboard (setara `/tiket panel`)."""
    import tickets
    from views import send_ticket_panel

    gid = _to_int(guild_id)
    channel_id = _to_int((data or {}).get("channel"))
    if channel_id <= 0:
        return False, "Pilih channel tempat panel tiket dipasang."
    channel = await _saluran(bot, gid, channel_id)
    if channel is None:
        return False, "Channel itu tidak ditemukan di server ini."

    staf = _to_int((data or {}).get("staff_role")) or None
    log = _to_int((data or {}).get("log_channel")) or None
    maks = _to_int((data or {}).get("max_open")) or None
    cfg = tickets.set_ticket_config(
        gid,
        enabled=True,
        panel_channel_id=channel_id,
        staff_role_id=staf,
        log_channel_id=log,
        max_open=maks,
    )

    guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
    embed = tickets.build_panel_embed(
        str(getattr(guild, "name", "") or "")[:100],
        staff_role_id=cfg.get("staff_role_id"),
    )
    try:
        pesan = await send_ticket_panel(channel, gid, embed)
    except Exception as exc:
        logger.warning("Panel tiket dari dashboard gagal dikirim: %s", exc)
        return False, (
            "Pengaturan tiket tersimpan, tetapi Discord menolak panelnya "
            "(cek izin **Kirim Pesan** & **Embed Links**)."
        )

    tickets.set_ticket_config(gid, panel_message_id=_to_int(getattr(pesan, "id", 0)), enabled=True)
    await tickets.save_tickets_to_disk()

    acuan = str(getattr(channel, "mention", f"<#{channel_id}>"))
    staf_info = f"<@&{cfg['staff_role_id']}>" if cfg.get("staff_role_id") else "_belum diatur_"
    log_info = f"<#{log}>" if log else "_belum diatur_"
    return True, (
        f"🎟️ Panel tiket terpasang di {acuan}. "
        f"Role staf: {staf_info} · log transkrip: {log_info} · "
        f"maksimal {cfg.get('max_open')} tiket per member."
    )


async def matikan_tiket(guild_id: int) -> tuple[bool, str]:
    """Matikan sistem tiket: panel lama tidak lagi membuat tiket baru."""
    import tickets

    gid = _to_int(guild_id)
    try:
        cfg = tickets.get_ticket_config(gid) or {}
    except Exception:  # pragma: no cover - jaring aman
        cfg = {}
    if not cfg.get("enabled"):
        return False, "Sistem tiket memang sudah nonaktif."
    if not tickets.disable_tickets(gid):
        return False, "Sistem tiket gagal dinonaktifkan."
    await tickets.save_tickets_to_disk()
    return True, (
        "Sistem tiket dinonaktifkan. Panel lama tetap ada di Discord, tetapi tombolnya "
        "tidak lagi membuat tiket baru sampai panel dipasang ulang."
    )


__all__ = [
    "STATUS_LABEL",
    "balas",
    "collect_tiket",
    "matikan_tiket",
    "pasang_panel",
    "tutup",
]
