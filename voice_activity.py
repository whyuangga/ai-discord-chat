"""XP Voice — menghitung waktu member di voice channel (0 kuota AI).

Modul ini hanya menyimpan **sesi runtime** (jam mulai + channel). Setiap kali
dipanggil, `flush_voice_sessions()` memberi XP untuk **menit penuh** yang sudah
berlalu lewat `levels.add_voice_minutes()`, lalu menggeser jam mulai sehingga
sisa detik tidak hilang.

Prinsip anti-eksploit:
1. Member yang **self-mute / self-deaf** tidak dihitung.
2. Channel **AFK** server & **voice channel yang diabaikan** tidak dihitung.
3. XP dihitung **per menit berada di voice**, bukan per join → tidak bisa spam join-leave.
4. Ada **batas menit per hari** per member (`voice_daily_cap_min`), jadi tidak bisa
   "idle 24 jam" untuk mengejar level.

Sesi sengaja **tidak** disimpan ke disk: bila bot restart, sesi dihitung ulang dari
awal sehingga tidak ada XP "hantu" dari jam yang tidak benar-benar dijalani.
"""

import logging
import time

import levels

logger = logging.getLogger("gemini_bot.voice_activity")

# Memberi XP tiap 60 detik; loop pemanggil berjalan tiap 15 detik jadi aman.
VOICE_FLUSH_INTERVAL_SEC = 60

# discord.ChannelType.voice = 2, stage_voice = 13 (dipakai sebagai int agar mudah dites)
_VOICE_CHANNEL_TYPES = {2, 13}

sessions: dict[str, dict] = {}   # "guild:user" -> {"since": float, "channel_id": int}


def _key(guild_id: int, user_id: int) -> str:
    return f"{int(guild_id)}:{int(user_id)}"


def _channel_type_id(channel) -> int:
    """Ambil tipe channel sebagai int (aman untuk objek tiruan pada pengujian)."""
    raw = getattr(channel, "type", None)
    if isinstance(raw, int):
        return raw
    value = getattr(raw, "value", None)
    if isinstance(value, int):
        return value
    return -1


def is_countable_voice(state, guild=None, cfg: dict | None = None) -> bool:
    """True bila member pada `state` layak dihitung mendapat XP voice."""
    channel = getattr(state, "channel", None)
    if channel is None:
        return False
    if _channel_type_id(channel) not in _VOICE_CHANNEL_TYPES:
        return False
    if getattr(state, "self_mute", False) or getattr(state, "self_deaf", False):
        return False
    if getattr(state, "afk", False):
        return False

    rules = cfg if cfg is not None else levels.get_level_config(getattr(guild, "id", 0) or 0)
    if rules.get("voice_ignore_afk", True):
        afk_id = getattr(guild, "afk_channel_id", None) if guild is not None else None
        if afk_id and getattr(channel, "id", None) == afk_id:
            return False
    ignored = {int(c) for c in (rules.get("voice_ignore_channels") or [])}
    if ignored and getattr(channel, "id", 0) in ignored:
        return False
    return True


def handle_voice_state(member, before, after, *, guild=None, now: float | None = None) -> str | None:
    """Mulai/hentikan sesi voice untuk seorang member.

    Mengembalikan `"start"`, `"stop"`, atau `None` (tidak ada perubahan berarti).
    """
    if member is None or getattr(member, "bot", False):
        return None

    guild = guild if guild is not None else getattr(member, "guild", None)
    guild_id = int(getattr(guild, "id", 0) or 0)
    user_id = int(getattr(member, "id", 0) or 0)
    if not guild_id or not user_id:
        return None

    cfg = levels.get_level_config(guild_id)
    if not cfg.get("enabled") or not cfg.get("voice_enabled", True):
        sessions.pop(_key(guild_id, user_id), None)
        return None

    before_ch = getattr(before, "channel", None)
    after_ch = getattr(after, "channel", None)
    now_ts = time.time() if now is None else float(now)
    key = _key(guild_id, user_id)

    if is_countable_voice(after, guild, cfg):
        if key not in sessions:
            sessions[key] = {
                "since": now_ts,
                "channel_id": int(getattr(after_ch, "id", 0) or 0),
            }
            return "start"
        # Pindah channel voice: cukup perbarui channel acuannya
        sessions[key]["channel_id"] = int(getattr(after_ch, "id", 0) or 0)
        return None

    if key in sessions or before_ch is not None:
        removed = sessions.pop(key, None)
        return "stop" if removed is not None else None
    return None


def flush_voice_sessions(*, now: float | None = None) -> list[dict]:
    """Beri XP untuk menit penuh pada semua sesi aktif.

    Mengembalikan daftar `{guild_id, user_id, channel_id, result}` untuk sesi yang
    benar-benar mendapat XP (dipakai untuk pengumuman kenaikan level).
    """
    now_ts = time.time() if now is None else float(now)
    awards: list[dict] = []

    for key, session in list(sessions.items()):
        try:
            gid_str, uid_str = key.split(":", 1)
            guild_id, user_id = int(gid_str), int(uid_str)
        except (TypeError, ValueError):  # pragma: no cover - kunci rusak
            sessions.pop(key, None)
            continue

        since = float(session.get("since") or now_ts)
        elapsed = now_ts - since
        whole_minutes = int(elapsed // 60)
        if whole_minutes < 1:
            continue

        # Geser jam mulai sebesar menit penuh; sisa detik tetap dihitung nanti
        session["since"] = since + whole_minutes * 60
        result = levels.add_voice_minutes(
            guild_id,
            user_id,
            whole_minutes,
            channel_id=int(session.get("channel_id") or 0),
            now=now_ts,
        )
        if result:
            awards.append(
                {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "channel_id": int(session.get("channel_id") or 0),
                    "result": result,
                }
            )
    return awards


def active_sessions() -> int:
    """Jumlah sesi voice yang sedang dilacak."""
    return len(sessions)


def reset_voice_sessions() -> int:
    """Membuang semua sesi (mis. saat bot shutdown). Mengembalikan jumlah yang dibuang."""
    count = len(sessions)
    sessions.clear()
    return count
