"""Tombol **tes fitur** di dashboard: kirim satu contoh nyata tanpa menunggu event.

Yang bisa diuji sekarang adalah fitur yang punya pemicu sendiri:

| Kunci | Fungsi | Yang dikirim |
| :--- | :--- | :--- |
| `welcome` | `cogs.agent_cog.trigger_member_welcome` | kartu/teks sambutan member baru |
| `goodbye` | `cogs.agent_cog.trigger_member_goodbye` | kartu pesan perpisahan |
| `boost` | `cogs.agent_cog.trigger_member_boost` | ucapan terima kasih boost |

Tes memakai `force=True` (melewati deduplikasi) dan **subject** bisa dipilih: member
server lewat ID, atau bot sendiri bila kosong. Kuota AI tetap 1 panggilan per tes.
"""

import logging

logger = logging.getLogger("gemini_bot.dashboard_uji")

UJI: tuple[dict, ...] = (
    {
        "kunci": "welcome",
        "label": "Sambutan member baru",
        "emoji": "👋",
        "grup": "Sambutan & pamit",
        "cfg": "welcome_agent_guilds",
        "kolom": "member",
        "contoh": "Kirim contoh sambutan (sapaan bahasa asing + kalimat AI) ke channel sambutan.",
    },
    {
        "kunci": "goodbye",
        "label": "Pesan perpisahan",
        "emoji": "👣",
        "grup": "Sambutan & pamit",
        "cfg": "goodbye_agent_guilds",
        "kolom": "member",
        "contoh": "Kirim contoh kartu perpisahan ke channel pamit.",
    },
    {
        "kunci": "boost",
        "label": "Ucapan boost server",
        "emoji": "💎",
        "grup": "Sambutan & pamit",
        "cfg": "boost_agent_guilds",
        "kolom": "member",
        "contoh": "Kirim contoh ucapan terima kasih boost ke channel boost.",
    },
    {
        "kunci": "pengumuman",
        "label": "Pengumuman terjadwal",
        "emoji": "⏰",
        "grup": "Konten & interaksi",
        "cfg": "",
        "kolom": "id",
        "contoh": "Kirim sekarang satu pengumuman tersimpan (jadwalnya tidak digeser).",
    },
    {
        "kunci": "panel",
        "label": "Panel menu",
        "emoji": "🧩",
        "grup": "Konten & interaksi",
        "cfg": "",
        "kolom": "ref",
        "contoh": "Segarkan panel di Discord supaya tombol & dropdown terbaru langsung tampil.",
    },
    {
        "kunci": "digest",
        "label": "Koran pagi (digest)",
        "emoji": "📰",
        "grup": "Konten & interaksi",
        "cfg": "digest_agent_guilds",
        "kolom": "",
        "contoh": "Buat contoh rubrik koran pagi (1 panggilan AI, tidak dikirim ke channel).",
    },
    {
        "kunci": "tiket",
        "label": "Panel tiket",
        "emoji": "🎫",
        "grup": "Tiket & layanan",
        "cfg": "",
        "kolom": "channel",
        "contoh": "Pasang ulang panel Buka Tiket di channel yang dipilih.",
    },
    {
        "kunci": "ai",
        "label": "Koneksi AI (Gemini)",
        "emoji": "🤖",
        "grup": "Diagnostik",
        "cfg": "",
        "kolom": "",
        "contoh": "Panggil AI sekali untuk memastikan API key, kuota, dan jaringan sehat.",
    },
    {
        "kunci": "ekspor",
        "label": "Ekspor CSV",
        "emoji": "📥",
        "grup": "Diagnostik",
        "cfg": "",
        "kolom": "",
        "contoh": "Bangun CSV level hari ini untuk memastikan data & header rapi.",
    },
)

UJI_MAP: dict[str, dict] = {item["kunci"]: item for item in UJI}


def _to_int(nilai: object) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def status_uji(guild_id: int) -> dict[str, dict]:
    """Status tiap fitur uji: `{kunci: {aktif, channel_id, label, grup, pilihan}}`."""
    import community_agent

    gid = _to_int(guild_id)
    hasil: dict[str, dict] = {}
    for item in UJI:
        cfg_nama = item.get("cfg") or ""
        if cfg_nama:
            peta = getattr(community_agent, cfg_nama, None) or {}
            cfg = peta.get(gid) or {}
            aktif = bool(cfg.get("enabled"))
            channel_id = _to_int(cfg.get("channel_id"))
        else:
            aktif, channel_id = True, 0
        hasil[item["kunci"]] = {
            "aktif": aktif,
            "channel_id": channel_id,
            "label": item["label"],
            "grup": item.get("grup") or "Lainnya",
            "kolom": item.get("kolom") or "",
            "pilihan": pilihan_uji(gid, item["kunci"]) if item.get("kolom") in ("id", "ref") else [],
        }
    return hasil


def pilihan_uji(guild_id: int, kunci: str) -> list[tuple[str, str]]:
    """Daftar pilihan untuk kolom `id`/`ref` (pengumuman & panel tersimpan)."""
    gid = _to_int(guild_id)
    if kunci == "pengumuman":
        try:
            import engagement

            return [
                (str(aid), f"#{aid} · {str(cfg.get('title') or 'Pengumuman')[:40]}")
                for aid, cfg in sorted((engagement.announcements or {}).items())
                if _to_int(cfg.get("guild_id")) == gid
            ]
        except Exception:  # pragma: no cover - jaring aman
            return []
    if kunci == "panel":
        try:
            import menu_builder

            return [
                (str(m.get("id") or ""), str(m.get("title") or "Panel")[:40])
                for m in menu_builder.list_menus(gid)
            ]
        except Exception:  # pragma: no cover - jaring aman
            return []
    return []


async def _uji_agent(bot, guild, orang, kunci: str) -> tuple[bool, str]:
    """Tes sambutan/perpisahan/boost lewat pemicu aslinya."""
    from cogs import agent_cog

    pemicu = {
        "welcome": "trigger_member_welcome",
        "goodbye": "trigger_member_goodbye",
        "boost": "trigger_member_boost",
    }[kunci]
    fungsi = getattr(agent_cog, pemicu)
    try:
        hasil = await fungsi(bot, guild, orang, force=True)
    except TypeError:
        hasil = await fungsi(bot, guild, orang)
    return bool(hasil), "terkirim" if hasil else "kosong"


async def _uji_pengumuman(bot, gid: int, nilai: str) -> tuple[bool, str]:
    import engagement

    daftar = [
        aid for aid, cfg in (engagement.announcements or {}).items()
        if _to_int(cfg.get("guild_id")) == gid
    ]
    aid = _to_int(nilai) or (daftar[0] if daftar else 0)
    if not aid:
        return False, "Belum ada pengumuman tersimpan — buat dulu di halaman **Buat**."
    status, cfg = await engagement.send_announcement_now(bot, aid, guild_id=gid)
    if status == "ok":
        return True, f"Pengumuman #{aid} terkirim ke <#{_to_int(cfg.get('channel_id'))}>."
    if status == "channel":
        return False, (
            f"Pengumuman #{aid} gagal dikirim — channel tujuan hilang atau bot tidak punya izin."
        )
    return False, f"Pengumuman #{aid} tidak ditemukan di server ini."


async def _uji_panel(bot, gid: int, nilai: str) -> tuple[bool, str]:
    import menu_builder

    menus = menu_builder.list_menus(gid)
    if not menus:
        return False, "Belum ada panel tersimpan — buat dulu di halaman **Buat**."
    menu = next((m for m in menus if str(m.get("id")) == str(nilai).strip()), menus[0])
    if not menu.get("message_id"):
        return False, (
            f"Panel **{menu.get('title') or '-'}** belum terpasang di Discord — "
            "pasang dulu dari halaman **Buat**."
        )
    if await menu_builder.refresh_panel(bot, menu):
        return True, f"Panel **{menu.get('title') or '-'}** disegarkan di Discord."
    return False, "Panel gagal disegarkan (pesan panel sudah dihapus atau tanpa izin)."


async def _uji_digest(bot, gid: int) -> tuple[bool, str]:
    import community_agent

    nama = str(getattr(getattr(bot, "user", None), "display_name", "") or "Bot")
    teks, galat = await community_agent.generate_morning_digest(gid, nama)
    if teks:
        ringkas = " ".join(str(teks).split())[:180]
        return True, f"Contoh koran pagi siap (tidak dikirim): “{ringkas}…”"
    return False, galat or "Koran pagi gagal dibuat."


async def _uji_tiket(bot, gid: int, nilai: str) -> tuple[bool, str]:
    import dashboard_tiket

    cid = _to_int(nilai)
    if cid <= 0:
        return False, "Pilih channel tempat panel tiket dipasang."
    return await dashboard_tiket.pasang_panel(bot, gid, {"channel": cid})


async def _uji_ai(gid: int) -> tuple[bool, str]:
    import community_agent

    jawab = await community_agent._call_gemini_agent(
        "Kamu asisten uji. Jawab sangat singkat.",
        [{"role": "user", "parts": [{"text": "Balas satu kata: siap"}]}],
        temperature=0.0,
        max_tokens=24,
        thinking_level="minimal",
        has_media=False,
        usage_kind="tes",
        usage_guild_id=gid,
    )
    if jawab:
        return True, f"AI menjawab “{' '.join(str(jawab).split())[:60]}” — koneksi sehat."
    return False, "AI tidak menjawab — cek `GEMINI_API_KEY`, kuota, atau jaringan."


def _uji_ekspor(gid: int) -> tuple[bool, str]:
    import analytics_export

    isi, nama, galat = analytics_export.build_csv("level", gid)
    if isi is None:
        return False, galat or "Ekspor CSV gagal dibuat."
    baris = max(0, len(isi.strip().splitlines()) - 1)
    return True, f"CSV `{nama}` siap: {baris} baris data."


async def jalankan_uji(bot, guild_id: int, kunci: str, member=None, opsi: str = "") -> tuple[bool, str]:
    """Kirim satu contoh untuk fitur `kunci`. Kembalikan `(berhasil, pesan)`."""
    kunci = str(kunci or "").strip().lower().removeprefix("uji.")
    item = UJI_MAP.get(kunci)
    if item is None:
        return False, f"Fitur uji `{kunci or '-'}` tidak dikenal."
    gid = _to_int(guild_id)
    if gid <= 0:
        return False, "Server tidak dikenali."

    status = status_uji(gid).get(kunci) or {}
    if item.get("cfg") and not status.get("aktif"):
        return False, (
            f"{item['label']} belum aktif — atur channel-nya dulu di halaman **Setelan**."
        )

    ambil_guild = getattr(bot, "get_guild", None)
    guild = ambil_guild(gid) if callable(ambil_guild) else None
    if guild is None and kunci not in ("ai", "ekspor"):
        return False, "Server tidak ditemukan di cache bot."

    try:
        if kunci in ("welcome", "goodbye", "boost"):
            orang = member or getattr(bot, "user", None)
            if orang is None:
                return False, "Tidak ada member untuk dijadikan contoh."
            ok, _ = await _uji_agent(bot, guild, orang, kunci)
            tujuan = f"<#{status.get('channel_id')}>" if status.get("channel_id") else "channel tujuan"
            if ok:
                return True, f"Contoh {item['label'].lower()} terkirim ke {tujuan}."
            return False, (
                f"Tidak ada yang terkirim ke {tujuan} — cek izin **Kirim pesan** bot dan "
                "API key Gemini (fitur butuh 1 panggilan AI)."
            )
        if kunci == "pengumuman":
            return await _uji_pengumuman(bot, gid, opsi)
        if kunci == "panel":
            return await _uji_panel(bot, gid, opsi)
        if kunci == "digest":
            return await _uji_digest(bot, gid)
        if kunci == "tiket":
            return await _uji_tiket(bot, gid, opsi)
        if kunci == "ai":
            return await _uji_ai(gid)
        if kunci == "ekspor":
            return _uji_ekspor(gid)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Tes %s gagal: %s", kunci, exc)
        return False, f"Tes gagal dijalankan ({type(exc).__name__})."
    return False, f"Fitur uji `{kunci}` belum punya pelaksana."


def cari_member(guild, nilai: str):
    """Member dari ID (opsional). `None` bila kosong/tidak ditemukan."""
    uid = _to_int(str(nilai or "").strip())
    if uid <= 0 or guild is None:
        return None
    getter = getattr(guild, "get_member", None)
    if callable(getter):
        try:
            hasil = getter(uid)
        except Exception:  # pragma: no cover - jaring aman
            hasil = None
        if hasil is not None:
            return hasil
    return None
