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
        "pemicu": "trigger_member_welcome",
        "cfg": "welcome_agent_guilds",
        "contoh": "Kirim contoh sambutan (sapaan bahasa asing + kalimat AI) ke channel sambutan.",
    },
    {
        "kunci": "goodbye",
        "label": "Pesan perpisahan",
        "emoji": "👣",
        "pemicu": "trigger_member_goodbye",
        "cfg": "goodbye_agent_guilds",
        "contoh": "Kirim contoh kartu perpisahan ke channel pamit.",
    },
    {
        "kunci": "boost",
        "label": "Ucapan boost server",
        "emoji": "💎",
        "pemicu": "trigger_member_boost",
        "cfg": "boost_agent_guilds",
        "contoh": "Kirim contoh ucapan terima kasih boost ke channel boost.",
    },
)

UJI_MAP: dict[str, dict] = {item["kunci"]: item for item in UJI}


def _to_int(nilai: object) -> int:
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def status_uji(guild_id: int) -> dict[str, dict]:
    """Status tiap fitur uji: `{kunci: {aktif, channel_id}}` (tanpa efek samping)."""
    import community_agent

    gid = _to_int(guild_id)
    hasil: dict[str, dict] = {}
    for item in UJI:
        peta = getattr(community_agent, item["cfg"], None) or {}
        cfg = peta.get(gid) or {}
        hasil[item["kunci"]] = {
            "aktif": bool(cfg.get("enabled")),
            "channel_id": _to_int(cfg.get("channel_id")),
            "label": item["label"],
        }
    return hasil


async def jalankan_uji(bot, guild_id: int, kunci: str, member=None) -> tuple[bool, str]:
    """Kirim satu contoh untuk fitur `kunci`. Kembalikan `(berhasil, pesan)`."""
    item = UJI_MAP.get(str(kunci or "").strip().lower())
    if item is None:
        return False, f"Fitur uji `{kunci or '-'}` tidak dikenal."
    gid = _to_int(guild_id)
    if gid <= 0:
        return False, "Server tidak dikenali."

    status = status_uji(gid).get(item["kunci"]) or {}
    if not status.get("aktif"):
        return False, (
            f"{item['label']} belum aktif — atur channel-nya dulu di halaman **Setelan**."
        )

    ambil_guild = getattr(bot, "get_guild", None)
    guild = ambil_guild(gid) if callable(ambil_guild) else None
    if guild is None:
        return False, "Server tidak ditemukan di cache bot."

    orang = member
    if orang is None:
        orang = getattr(bot, "user", None)
    if orang is None:
        return False, "Tidak ada member untuk dijadikan contoh."

    try:
        from cogs import agent_cog

        fungsi = getattr(agent_cog, item["pemicu"])
        hasil = await fungsi(bot, guild, orang, force=True)
    except TypeError:
        # `trigger_member_boost` tidak punya parameter `force`.
        try:
            hasil = await fungsi(bot, guild, orang)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Tes %s gagal: %s", item["kunci"], exc)
            return False, f"Tes gagal dijalankan ({type(exc).__name__})."
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Tes %s gagal: %s", item["kunci"], exc)
        return False, f"Tes gagal dijalankan ({type(exc).__name__})."

    channel_id = status.get("channel_id") or 0
    tujuan = f"<#{channel_id}>" if channel_id else "channel tujuan"
    if hasil:
        return True, f"Contoh {item['label'].lower()} terkirim ke {tujuan}."
    return False, (
        f"Tidak ada yang terkirim ke {tujuan} — cek izin **Kirim pesan** bot dan "
        "API key Gemini (fitur butuh 1 panggilan AI)."
    )


def cari_member(guild, nilai: str):
    """Member dari ID (opsional). `None` bila kosong/tidak ditemukan."""
    uid = _to_int(str(nilai or "").strip())
    if uid <= 0 or guild is None:
        return None
    for nama_fungsi in ("get_member", "get_member_named"):
        getter = getattr(guild, nama_fungsi, None)
        if callable(getter):
            try:
                hasil = getter(uid)
            except Exception:  # pragma: no cover - jaring aman
                hasil = None
            if hasil is not None:
                return hasil
    return None
