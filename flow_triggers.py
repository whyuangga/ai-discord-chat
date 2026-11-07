"""Pemicu alur di luar klik tombol — saat **member bergabung** (`/menu pemicu`).

Sisa ide dari *triggers* Discohook: alur tidak harus dimulai oleh klik tombol.
Admin memasang satu alur "gabung" per server; ketika ada member baru, bot
menjalankan langkah alur itu memakai channel yang ditentukan Admin.

Perbedaan dengan alur tombol (`flows.py`): tidak ada interaksi, jadi langkah yang
butuh balasan pribadi (`pesan`, `hapus`) dilewati. Yang berlaku:

| Langkah | Arti di pemicu |
| :--- | :--- |
| `role:` / `+role:` / `-role:` | Beri/lepas role untuk member baru |
| `syarat:<id>` | Berhenti bila member baru **tidak** punya role itu |
| `umum:<teks>` | Kirim pesan di channel pemicu |
| `webhook:<nama>\\|<teks>` | Kirim sebagai nama sendiri di channel pemicu |
| `thread:<nama>` | Buat thread sambutan di channel pemicu |
| `tunggu:<detik>` | Jeda (dibatasi 15 detik) |
| `stop[:<teks>]` | Hentikan alur |

Pengaman: `min_age_days` menolak akun yang terlalu baru (bawaan 0 = semua boleh),
jadi server yang kena raid tidak otomatis mengeksekusi alur untuk tiap akun baru.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import discord

import flows
import message_template
import webhook_identity
from config import DATA_DIR

logger = logging.getLogger("gemini_bot.flow_triggers")

FLOW_FILE = DATA_DIR / "flow_triggers.json"
TRIGGER_JOIN = "gabung"
MAX_MIN_AGE_DAYS = 365

triggers: dict[int, dict] = {}      # guild_id -> {steps, channel_id, min_age_days, created_by}
_lock = asyncio.Lock()


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def get_trigger(guild_id: int) -> dict | None:
    return triggers.get(_to_int(guild_id))


def set_trigger(
    guild_id: int,
    steps,
    *,
    channel_id: int,
    min_age_days: int = 0,
    created_by: int = 0,
) -> tuple[dict | None, list[str]]:
    """Pasang/ganti alur gabung. Kembalikan `(trigger, galat)`."""
    bersih = flows.sanitize_steps(steps)
    if not bersih:
        return None, ["Alur kosong atau tidak valid — cek `/menu alur-bantuan`."]
    if not _to_int(channel_id):
        return None, ["Channel pemicu wajib dipilih (untuk pesan/thread sambutan)."]
    data = {
        "steps": bersih,
        "channel_id": _to_int(channel_id),
        "min_age_days": min(MAX_MIN_AGE_DAYS, max(0, _to_int(min_age_days))),
        "created_by": _to_int(created_by),
        "created_at": time.time(),
    }
    triggers[_to_int(guild_id)] = data
    return data, []


def remove_trigger(guild_id: int) -> bool:
    return triggers.pop(_to_int(guild_id), None) is not None


def akun_cukup_tua(data: dict, member, *, now: float | None = None) -> bool:
    """True bila umur akun memenuhi syarat `min_age_days`."""
    minimal = _to_int(data.get("min_age_days"))
    if minimal <= 0:
        return True
    dibuat = getattr(member, "created_at", None)
    cap = getattr(dibuat, "timestamp", None)
    if not callable(cap):
        return True
    umur_hari = ((now or time.time()) - dibuat.timestamp()) / 86400
    return umur_hari >= minimal


def describe(data: dict | None) -> list[str]:
    if not data:
        return ["(belum ada pemicu gabung)"]
    baris = [
        f"📍 channel <#{data.get('channel_id')}>",
        f"🛡️ akun minimal {_to_int(data.get('min_age_days'))} hari",
    ]
    return baris + [f"• {b}" for b in flows.describe(data.get("steps") or [])]


async def run_join_flow(guild, member, data: dict) -> dict:
    """Jalankan alur gabung. Kembalikan ringkasan `{sent, roles, threads, errors}`."""
    hasil = {"sent": 0, "roles": [], "threads": [], "errors": []}
    channel = None
    getter = getattr(guild, "get_channel", None)
    if callable(getter):
        channel = getter(_to_int(data.get("channel_id")))
    if channel is None:
        fetch = getattr(guild, "fetch_channel", None)
        if callable(fetch):
            try:
                channel = await fetch(_to_int(data.get("channel_id")))
            except Exception:
                channel = None

    konteks = {"guild": guild, "member": member, "channel": channel}

    for step in flows.sanitize_steps(data.get("steps")):
        aksi = step["action"]

        if aksi == flows.ACTION_REQUIRE_ROLE:
            role = guild.get_role(step["role_id"])
            if role is None or role not in getattr(member, "roles", []):
                hasil["stopped"] = True
                return hasil
            continue

        if aksi in (flows.ACTION_ROLE_TOGGLE, flows.ACTION_ROLE_ADD, flows.ACTION_ROLE_REMOVE):
            role = guild.get_role(step["role_id"])
            if role is None:
                hasil["errors"].append(f"role {step['role_id']} tidak ada")
                continue
            punya = role in getattr(member, "roles", [])
            try:
                if aksi == flows.ACTION_ROLE_TOGGLE and punya:
                    await member.remove_roles(role, reason="Alur gabung")
                elif aksi in (flows.ACTION_ROLE_TOGGLE, flows.ACTION_ROLE_ADD) and not punya:
                    await member.add_roles(role, reason="Alur gabung")
                elif aksi == flows.ACTION_ROLE_REMOVE and punya:
                    await member.remove_roles(role, reason="Alur gabung")
                else:
                    continue
            except Exception as exc:
                hasil["errors"].append(f"gagal ubah role {step['role_id']}: {type(exc).__name__}")
                continue
            hasil["roles"].append(step["role_id"])
            continue

        if aksi in (flows.ACTION_SAY, flows.ACTION_STOP) and aksi == flows.ACTION_STOP:
            if step.get("text"):
                hasil["errors"].append("stop berisi teks (tidak ada balasan di pemicu)")
            hasil["stopped"] = True
            return hasil

        if channel is None:
            hasil["errors"].append("channel pemicu tidak ditemukan")
            return hasil

        if aksi == flows.ACTION_SAY:
            teks = message_template.render(str(step.get("text") or ""), **konteks)
            if teks.strip():
                try:
                    await channel.send(teks[:2000], allowed_mentions=discord.AllowedMentions.none())
                    hasil["sent"] += 1
                except (discord.Forbidden, discord.HTTPException) as exc:
                    hasil["errors"].append(f"gagal kirim: {type(exc).__name__}")
            continue

        if aksi == flows.ACTION_WEBHOOK:
            nama = message_template.render(str(step.get("name") or ""), **konteks)[:80]
            teks = message_template.render(str(step.get("text") or ""), **konteks)
            ok, ket = await webhook_identity.kirim_sebagai(channel, nama=nama or "Server", isi=teks)
            if ok:
                hasil["sent"] += 1
            else:
                hasil["errors"].append(f"webhook: {ket}")
            continue

        if aksi == flows.ACTION_THREAD:
            nama = message_template.render(str(step.get("name") or ""), **konteks)[:90]
            try:
                thread = await channel.create_thread(
                    name=nama or "sambutan",
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=1440,
                    reason="Alur gabung",
                )
                hasil["threads"].append(getattr(thread, "id", 0))
            except Exception as exc:
                hasil["errors"].append(f"gagal buat thread: {type(exc).__name__}")
            continue

        if aksi == flows.ACTION_WAIT:
            await asyncio.sleep(float(step.get("seconds") or 0))
            continue

    return hasil


async def handle_member_join(bot, member) -> dict | None:
    """Dipanggil listener `on_member_join`. `None` bila tidak ada pemicu."""
    guild = getattr(member, "guild", None)
    if guild is None or getattr(member, "bot", False):
        return None
    data = get_trigger(guild.id)
    if data is None or not akun_cukup_tua(data, member):
        return None
    try:
        return await run_join_flow(guild, member, data)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Alur gabung gagal untuk %s: %s", getattr(member, "id", "?"), exc)
        return None


# ------------------------------------------------------------------------------
# SIMPAN / MUAT
# ------------------------------------------------------------------------------
def load_from_disk() -> int:
    triggers.clear()
    path = Path(FLOW_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0
    for gid_str, data in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        langkah = flows.sanitize_steps((data or {}).get("steps"))
        if not gid or not langkah:
            continue
        triggers[gid] = {
            "steps": langkah,
            "channel_id": _to_int(data.get("channel_id")),
            "min_age_days": min(MAX_MIN_AGE_DAYS, max(0, _to_int(data.get("min_age_days")))),
            "created_by": _to_int(data.get("created_by")),
            "created_at": float(data.get("created_at") or 0),
        }
    return len(triggers)


async def save_to_disk() -> None:
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            isi = {"version": 1, "guilds": {str(g): v for g, v in triggers.items()}}
            sementara = Path(str(FLOW_FILE) + ".tmp")
            sementara.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding="utf-8")
            sementara.replace(Path(FLOW_FILE))
        except Exception:  # pragma: no cover
            logger.exception("Gagal menyimpan %s")
