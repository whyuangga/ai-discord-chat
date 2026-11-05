"""Raid Guard — mode darurat otomatis saat server diserbu akun palsu (**0 kuota AI**).

Melengkapi anti-raid *lapor saja*: bila lonjakan join melewati ambang, bot bisa **otomatis**
menyalakan mode darurat selama N menit:

| Aksi | Efek saat mode raid aktif |
| :--- | :--- |
| `lapor` | Laporan ke channel log + DM owner saja (paling aman) |
| `verifikasi` *(bawaan)* | Berhenti memberi **Auto Role**, kirim pengingat verifikasi, & catat member yang masuk |
| `verifikasi+lockdown` | Semua di atas + **lockdown** semua text channel (otomatis dibuka kembali saat mode berakhir) |

Mode berakhir otomatis setelah durasi habis, atau manual lewat `/raid akhiri`.
Semua tindakan **reversible**: lockdown dibuka kembali & Auto Role kembali normal.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import discord

from config import DATA_DIR, RAID_FILE

logger = logging.getLogger("gemini_bot.raid_guard")

_lock = asyncio.Lock()

ACTIONS: dict[str, str] = {
    "lapor": "👀 Lapor saja (tanpa mengubah server)",
    "verifikasi": "🚦 Tahan Auto Role + minta verifikasi (bawaan)",
    "verifikasi+lockdown": "🔒 Tahan Auto Role + lockdown sementara",
}

raid_configs: dict[int, dict] = {}     # guild_id -> konfigurasi
raid_states: dict[int, dict] = {}      # guild_id -> mode raid aktif
_recent_joins: dict[int, list[float]] = {}
_alert_cooldown: dict[int, float] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def default_config() -> dict:
    return {
        "enabled": False,           # default NONAKTIF sampai Admin menyalakannya
        "join_threshold": 8,
        "window_sec": 60,
        "action": "verifikasi",
        "duration_min": 15,
        "log_channel_id": None,
        "verify_channel_id": None,
    }


def get_config(guild_id: int) -> dict:
    gid = int(guild_id)
    cfg = raid_configs.get(gid)
    if cfg is None:
        cfg = default_config()
        raid_configs[gid] = cfg
    else:
        for key, value in default_config().items():
            cfg.setdefault(key, value)
    return cfg


def is_enabled(guild_id: int) -> bool:
    cfg = raid_configs.get(int(guild_id))
    return bool(cfg and cfg.get("enabled"))


def set_config(guild_id: int, **changes) -> dict:
    cfg = get_config(guild_id)
    if changes.get("enabled") is not None:
        cfg["enabled"] = bool(changes["enabled"])
    if changes.get("action") in ACTIONS:
        cfg["action"] = str(changes["action"])
    for key in ("join_threshold", "window_sec", "duration_min"):
        if changes.get(key) is not None:
            cfg[key] = max(1, int(changes[key]))
    for key in ("log_channel_id", "verify_channel_id"):
        if key in changes and changes[key] is not None:
            cfg[key] = _to_int(changes[key]) or None
    cfg["join_threshold"] = min(max(2, _to_int(cfg["join_threshold"], 8)), 100)
    cfg["window_sec"] = min(max(10, _to_int(cfg["window_sec"], 60)), 3600)
    cfg["duration_min"] = min(max(1, _to_int(cfg["duration_min"], 15)), 1440)
    return cfg


def handle_channel_delete(channel_id: int) -> int:
    cid = _to_int(channel_id)
    changed = 0
    for cfg in raid_configs.values():
        for key in ("log_channel_id", "verify_channel_id"):
            if cfg.get(key) == cid:
                cfg[key] = None
                changed += 1
    return changed


# ==============================================================================
# DETEKSI
# ==============================================================================
def reset_runtime() -> None:
    _recent_joins.clear()
    _alert_cooldown.clear()


def register_join(guild_id: int, *, now: float | None = None) -> int:
    """Mencatat satu join & mengembalikan jumlah join di dalam jendela waktu."""
    gid = int(guild_id)
    cfg = get_config(gid)
    now_ts = time.time() if now is None else float(now)
    window = max(10, _to_int(cfg.get("window_sec"), 60))

    store = [ts for ts in _recent_joins.get(gid, []) if now_ts - ts <= window]
    store.append(now_ts)
    _recent_joins[gid] = store
    return len(store)


def is_raid_active(guild_id: int, *, now: float | None = None) -> dict | None:
    """Status mode raid (otomatis berakhir bila waktunya habis)."""
    gid = int(guild_id)
    state = raid_states.get(gid)
    if not state:
        return None
    now_ts = time.time() if now is None else float(now)
    if float(state.get("until") or 0) <= now_ts:
        return None
    return state


def should_skip_autorole(guild_id: int) -> bool:
    """Auto Role ditahan bila mode raid aktif & aksinya bukan `lapor`."""
    state = is_raid_active(guild_id)
    if not state:
        return False
    return state.get("action") in ("verifikasi", "verifikasi+lockdown")


def remaining_seconds(guild_id: int, *, now: float | None = None) -> int:
    state = is_raid_active(guild_id, now=now)
    if not state:
        return 0
    now_ts = time.time() if now is None else float(now)
    return max(0, int(float(state["until"]) - now_ts))


# ==============================================================================
# MULAI / AKHIRI
# ==============================================================================
async def start(
    bot,
    guild,
    *,
    reason: str = "Lonjakan member join",
    actor_id: int = 0,
    duration_min: int | None = None,
    action: str | None = None,
) -> dict:
    """Menyalakan mode raid. Mengembalikan ringkasan langkah yang dijalankan."""
    gid = _to_int(getattr(guild, "id", 0))
    cfg = get_config(gid)
    minutes = max(1, _to_int(duration_min or cfg.get("duration_min"), 15))
    mode = str(action or cfg.get("action") or "verifikasi")
    if mode not in ACTIONS:
        mode = "verifikasi"

    now_ts = time.time()
    state = {
        "started_at": now_ts,
        "until": now_ts + minutes * 60,
        "action": mode,
        "reason": str(reason)[:200],
        "by": "manual" if actor_id else "otomatis",
        "actor_id": _to_int(actor_id) or None,
        "locked": False,
        "joins": 0,
    }
    steps: list[str] = [f"Mode **{mode}** aktif selama **{minutes} menit**."]

    if mode == "verifikasi+lockdown":
        try:
            import server_tools as st

            ok, failed = await st.start_lockdown(guild, by_id=_to_int(actor_id) or 0, reason=reason)
            await st.save_server_tools_to_disk()
            state["locked"] = ok > 0
            steps.append(f"Lockdown: `{ok}` channel dikunci" + (f" (gagal `{failed}`)" if failed else ""))
        except Exception as exc:  # pragma: no cover - jaring aman
            steps.append(f"Lockdown gagal: `{type(exc).__name__}`")

    if mode in ("verifikasi", "verifikasi+lockdown"):
        steps.append("Auto Role ditahan & member baru diminta verifikasi.")

    raid_states[gid] = state
    await notify(bot, guild, build_alert_embed(guild, state, steps))
    logger.warning("Mode raid aktif di %s (%s) selama %d menit.", getattr(guild, "name", gid), mode, minutes)
    return {"state": state, "steps": steps}


async def end(bot, guild, *, actor_id: int = 0, reason: str = "Mode raid berakhir") -> dict:
    """Mengakhiri mode raid & mengembalikan server seperti semula."""
    gid = _to_int(getattr(guild, "id", 0))
    state = raid_states.pop(gid, None)
    if state is None:
        return {"ended": False, "steps": ["Tidak ada mode raid yang aktif."]}

    steps: list[str] = []
    if state.get("locked"):
        try:
            import server_tools as st

            restored = await st.stop_lockdown(guild)
            await st.save_server_tools_to_disk()
            steps.append(f"Lockdown dibuka: `{restored}` channel dipulihkan")
        except Exception as exc:  # pragma: no cover - jaring aman
            steps.append(f"Gagal membuka lockdown: `{type(exc).__name__}`")
    steps.append("Auto Role kembali normal. Member yang sudah terlanjur masuk tetap perlu verifikasi manual.")

    duration = int(time.time() - float(state.get("started_at") or time.time()))
    embed = discord.Embed(
        title="✅ Mode Raid Berakhir",
        description=(
            f"Durasi: `{duration // 60} menit {duration % 60} detik`\n"
            + "\n".join(f"• {line}" for line in steps)
        ),
        color=discord.Color.green(),
    )
    embed.set_footer(text="Raid Guard • 0 kuota AI • semua tindakan sudah dikembalikan")
    await notify(bot, guild, embed, force=True)
    logger.info("Mode raid di %s berakhir setelah %d detik.", getattr(guild, "name", gid), duration)
    return {"ended": True, "steps": steps}


async def tick(bot) -> list[int]:
    """Dipanggil berkala: mengakhiri mode raid yang sudah kedaluwarsa."""
    ended: list[int] = []
    now_ts = time.time()
    for gid, state in list(raid_states.items()):
        if float(state.get("until") or 0) > now_ts:
            continue
        guild = bot.get_guild(gid) if callable(getattr(bot, "get_guild", None)) else None
        if guild is None:
            raid_states.pop(gid, None)
            continue
        await end(bot, guild, reason="Durasi habis")
        ended.append(gid)
    return ended


async def handle_member_join(bot, member) -> dict | None:
    """Dipanggil dari `on_member_join`: deteksi & jalankan mode raid bila perlu."""
    guild = getattr(member, "guild", None)
    if guild is None or getattr(member, "bot", False):
        return None
    gid = _to_int(getattr(guild, "id", 0))
    if not gid:
        return None

    count = register_join(gid)
    cfg = get_config(gid)

    active = is_raid_active(gid)
    if active is not None:
        active["joins"] = _to_int(active.get("joins")) + 1
        if active.get("action") in ("verifikasi", "verifikasi+lockdown"):
            await _remind_verification(bot, guild, cfg, member)
        return active

    if not cfg.get("enabled"):
        return None
    if count < _to_int(cfg.get("join_threshold"), 8):
        return None

    # Anti spam laporan: maksimal sekali per 5 menit per server
    last_alert = _alert_cooldown.get(gid, 0.0)
    if time.time() - last_alert < 300:
        return None
    _alert_cooldown[gid] = time.time()

    result = await start(bot, guild, reason=f"`{count}` member join dalam `{cfg['window_sec']}` detik")
    state = result["state"]
    state["joins"] = count
    if state.get("action") in ("verifikasi", "verifikasi+lockdown"):
        # Member yang memicu deteksi juga diminta verifikasi
        await _remind_verification(bot, guild, cfg, member)
    return state


async def _remind_verification(bot, guild, cfg, member) -> None:
    """Pengingat verifikasi: DM singkat ke member baru & pesan di channel verifikasi."""
    try:
        await member.send(
            f"🚦 **{getattr(guild, 'name', 'Server')}** sedang dalam mode verifikasi darurat. "
            "Silakan buka channel verifikasi di server untuk membuka akses."
        )
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass

    channel_id = cfg.get("verify_channel_id")
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id)) if callable(getattr(bot, "get_channel", None)) else None
    if channel is None:
        return
    try:
        await channel.send(
            f"🚦 {getattr(member, 'mention', 'Member baru')} baru bergabung saat mode verifikasi aktif. "
            "Tekan tombol **Verifikasi Saya** di panel verifikasi untuk membuka akses.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException):
        pass


# ==============================================================================
# LAPORAN
# ==============================================================================
def build_alert_embed(guild, state: dict, steps: list[str]) -> discord.Embed:
    gid = _to_int(getattr(guild, "id", 0))
    cfg = get_config(gid)
    embed = discord.Embed(
        title="🚨 Mode Raid Diaktifkan",
        description=(
            f"**Alasan:** {state.get('reason')}\n"
            f"**Aksi:** {ACTIONS.get(str(state.get('action')), state.get('action'))}\n"
            f"**Durasi:** hingga <t:{int(state.get('until'))}:t> "
            f"(<t:{int(state.get('until'))}:R>)\n"
            f"**Dipicu oleh:** {state.get('by')}"
        ),
        color=discord.Color.orange(),
    )
    if steps:
        embed.add_field(name="Langkah", value="\n".join(f"• {line}" for line in steps)[:1024], inline=False)
    embed.add_field(
        name="Selama mode aktif",
        value=(
            f"• Auto Role ditahan: `{'ya' if cfg.get('action') != 'lapor' else 'tidak'}`\n"
            f"• Ambang deteksi: `{cfg.get('join_threshold')}` join / `{cfg.get('window_sec')}` dtk\n"
            "• Akhiri lebih awal: `/raid akhiri`"
        ),
        inline=False,
    )
    embed.set_footer(text="Raid Guard • 0 kuota AI • semua tindakan bisa dikembalikan")
    return embed


async def notify(bot, guild, embed: discord.Embed, *, force: bool = False) -> None:
    """Kirim laporan ke channel log raid (atau channel sistem) + DM owner."""
    gid = _to_int(getattr(guild, "id", 0))
    cfg = get_config(gid)
    channel = None
    channel_id = cfg.get("log_channel_id")
    if channel_id and callable(getattr(bot, "get_channel", None)):
        channel = bot.get_channel(int(channel_id))
    if channel is None:
        channel = getattr(guild, "system_channel", None)
    if channel is not None:
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            pass

    if not force:
        return
    try:
        owner = getattr(guild, "owner", None)
        if owner is None and callable(getattr(guild, "fetch_member", None)):
            owner = await guild.fetch_member(getattr(guild, "owner_id", 0))
        if owner is not None:
            await owner.send(embed=embed)
    except Exception as exc:  # pragma: no cover - DM tertutup
        logger.debug("DM owner raid guard gagal: %s", exc)


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def load_raid_from_disk() -> int:
    raid_configs.clear()
    raid_states.clear()
    reset_runtime()

    path = Path(RAID_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(data, dict):
            continue
        cfg = default_config()
        cfg["enabled"] = bool(data.get("enabled", False))
        cfg["action"] = data.get("action") if data.get("action") in ACTIONS else "verifikasi"
        cfg["join_threshold"] = max(2, _to_int(data.get("join_threshold"), 8))
        cfg["window_sec"] = max(10, _to_int(data.get("window_sec"), 60))
        cfg["duration_min"] = max(1, _to_int(data.get("duration_min"), 15))
        cfg["log_channel_id"] = _to_int(data.get("log_channel_id")) or None
        cfg["verify_channel_id"] = _to_int(data.get("verify_channel_id")) or None
        raid_configs[gid] = cfg

    for gid_str, data in (raw.get("states") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(data, dict):
            continue
        if float(data.get("until") or 0) <= time.time():
            continue
        raid_states[gid] = {
            "started_at": float(data.get("started_at") or time.time()),
            "until": float(data.get("until") or 0),
            "action": data.get("action") if data.get("action") in ACTIONS else "verifikasi",
            "reason": str(data.get("reason") or "dipulihkan setelah restart"),
            "by": str(data.get("by") or "otomatis"),
            "actor_id": _to_int(data.get("actor_id")) or None,
            "locked": bool(data.get("locked", False)),
            "joins": _to_int(data.get("joins")),
        }
    return len(raid_configs)


async def save_raid_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(gid): cfg for gid, cfg in raid_configs.items()},
                "states": {str(gid): state for gid, state in raid_states.items()},
            }
            tmp_file = Path(str(RAID_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, RAID_FILE)
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan raid.json: %s", exc)


def cleanup_raid_runtime() -> int:
    """Membuang catatan join & alert yang kedaluwarsa (jaga RAM tetap kecil)."""
    now_ts = time.time()
    removed = 0
    for gid, stamps in list(_recent_joins.items()):
        cfg = get_config(gid)
        window = max(10, _to_int(cfg.get("window_sec"), 60))
        fresh = [ts for ts in stamps if now_ts - ts <= window]
        if fresh:
            _recent_joins[gid] = fresh
        else:
            _recent_joins.pop(gid, None)
            removed += 1
    for gid, ts in list(_alert_cooldown.items()):
        if now_ts - float(ts) > 3600:
            _alert_cooldown.pop(gid, None)
    return removed
