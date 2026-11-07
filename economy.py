"""Ekonomi ringan server — koin dari chat & voice (**0 kuota AI**).

Fitur:
1. **Koin pasif** — dapat koin tiap pesan (dengan jeda) dan tiap menit di voice channel.
2. **Hadiah harian** — `/ekonomi harian` dengan bonus *streak* bila rajin mengklaim.
3. **Toko role** — Admin menaruh item (nama, harga, role). Member membeli → role otomatis diberikan.
4. **Transfer** — kirim koin ke member lain (dengan batas minimal & tanpa biaya).

Prinsip:
- **Default NONAKTIF** (`/ekonomi atur aktif:True`) supaya server yang tidak butuh tidak
  mendapat beban tambahan.
- Data disimpan di `data/economy.json` dengan penulisan atomik + pemangkasan member
  (hanya pemilik saldo terbesar yang disimpan, default 500/server).
- Tidak pernah menyentuh Gemini: murni aritmetika lokal.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from config import DATA_DIR, ECONOMY_FILE

logger = logging.getLogger("gemini_bot.economy")

_lock = asyncio.Lock()

MAX_MEMBERS = 500            # batas member tersimpan per server (hemat RAM/disk)
MAX_ITEMS = 20               # batas item toko per server
TRANSFER_MIN = 10            # minimal koin yang bisa ditransfer
TRANSFER_COOLDOWN_SEC = 5    # jeda antar-transfer per pengirim

economy_guilds: dict[int, dict] = {}     # guild_id -> konfigurasi
balances: dict[str, int] = {}            # "guild:user" -> koin
meta: dict[str, dict] = {}               # "guild:user" -> {last_earn, last_daily, streak}
shop: dict[int, dict[str, dict]] = {}    # guild_id -> {item_id: {...}}
_last_transfer: dict[str, float] = {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _key(guild_id: int, user_id: int) -> str:
    return f"{int(guild_id)}:{int(user_id)}"


def default_config() -> dict:
    return {
        "enabled": False,
        "currency": "koin",
        "emoji": "🪙",
        "per_message": 5,
        "cooldown": 60,
        "per_voice_min": 3,
        "daily_amount": 100,
        "daily_cooldown": 86400,
        "ignore_channels": [],
        "leveled_up": 0,
    }


def default_config_public() -> dict:
    """Salinan default agar pemanggil tidak mengubah konstanta modul."""
    return dict(default_config())


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def get_config(guild_id: int) -> dict:
    cfg = economy_guilds.get(int(guild_id))
    if cfg is None:
        cfg = default_config()
        economy_guilds[int(guild_id)] = cfg
    return cfg


def is_active(guild_id: int) -> bool:
    cfg = economy_guilds.get(int(guild_id))
    return bool(cfg and cfg.get("enabled"))


def set_config(guild_id: int, **changes) -> dict | None:
    """Mengubah konfigurasi ekonomi. `aktif=False` mematikan fitur (data saldo tetap)."""
    gid = int(guild_id)
    if changes.get("aktif") is False or changes.get("enabled") is False:
        cfg = economy_guilds.get(gid)
        if cfg:
            cfg["enabled"] = False
        return cfg

    cfg = get_config(gid)
    cfg["enabled"] = True
    if changes.get("mata_uang"):
        cfg["currency"] = str(changes["mata_uang"]).strip()[:20] or cfg["currency"]
    if changes.get("emoji"):
        cfg["emoji"] = str(changes["emoji"]).strip()[:16] or cfg["emoji"]
    for key, minimum in (
        ("per_message", 0),
        ("cooldown", 0),
        ("per_voice_min", 0),
        ("daily_amount", 0),
        ("daily_cooldown", 3600),
    ):
        if changes.get(key) is not None:
            cfg[key] = max(minimum, _to_int(changes[key], cfg.get(key, minimum)))
    return cfg


def is_channel_ignored(guild_id: int, channel_id: int) -> bool:
    cfg = economy_guilds.get(int(guild_id)) or {}
    return int(channel_id or 0) in {int(c) for c in (cfg.get("ignore_channels") or [])}


# ==============================================================================
# SALDO
# ==============================================================================
def balance(guild_id: int, user_id: int) -> int:
    return max(0, int(balances.get(_key(guild_id, user_id)) or 0))


def _entry(guild_id: int, user_id: int) -> dict:
    return meta.setdefault(_key(guild_id, user_id), {})


def add_coins(guild_id: int, user_id: int, amount: int, *, now: float | None = None) -> int:
    """Menambah (atau mengurangi, bila negatif) koin. Mengembalikan saldo terbaru."""
    key = _key(guild_id, user_id)
    current = max(0, int(balances.get(key) or 0))
    updated = max(0, current + int(amount))
    balances[key] = updated
    _entry(guild_id, user_id)["last_at"] = time.time() if now is None else float(now)
    return updated


def spend_coins(guild_id: int, user_id: int, amount: int) -> bool:
    """Mengurangi koin bila cukup. Mengembalikan True bila berhasil."""
    cost = max(0, int(amount))
    if cost <= 0:
        return False
    if balance(guild_id, user_id) < cost:
        return False
    add_coins(guild_id, user_id, -cost)
    return True


def earn_from_message(
    guild_id: int,
    user_id: int,
    *,
    channel_id: int = 0,
    role_ids: set[int] | None = None,
    now: float | None = None,
) -> int | None:
    """Memberi koin untuk satu pesan (dengan jeda). `None` bila tidak dapat jatah."""
    gid = int(guild_id)
    cfg = economy_guilds.get(gid)
    if not cfg or not cfg.get("enabled"):
        return None
    if channel_id and is_channel_ignored(gid, channel_id):
        return None
    amount = int(cfg.get("per_message") or 0)
    if amount <= 0:
        return None

    now_ts = time.time() if now is None else float(now)
    entry = _entry(gid, user_id)
    cooldown = int(cfg.get("cooldown") or 0)
    if cooldown and now_ts - float(entry.get("last_earn") or 0) < cooldown:
        return None
    entry["last_earn"] = now_ts
    return add_coins(gid, user_id, amount, now=now_ts)


def earn_from_voice(guild_id: int, user_id: int, minutes: int, *, now: float | None = None) -> int | None:
    """Memberi koin karena berada di voice channel selama `minutes` menit."""
    gid = int(guild_id)
    cfg = economy_guilds.get(gid)
    if not cfg or not cfg.get("enabled"):
        return None
    per_min = int(cfg.get("per_voice_min") or 0)
    whole = max(0, int(minutes))
    if per_min <= 0 or whole <= 0:
        return None
    return add_coins(gid, user_id, per_min * whole, now=now)


def claim_daily(guild_id: int, user_id: int, *, now: float | None = None) -> tuple[bool, int, int]:
    """Mengklaim hadiah harian. Mengembalikan `(berhasil, jumlah, streak_hari)`."""
    gid = int(guild_id)
    cfg = economy_guilds.get(gid)
    if not cfg or not cfg.get("enabled"):
        return False, 0, 0

    now_ts = time.time() if now is None else float(now)
    cooldown = max(3600, int(cfg.get("daily_cooldown") or 86400))
    entry = _entry(gid, user_id)
    last = float(entry.get("last_daily") or 0)
    if last and now_ts - last < cooldown:
        return False, 0, int(entry.get("daily_streak") or 0)

    # streak bertambah bila klaim berikutnya masih dalam 48 jam
    streak = int(entry.get("daily_streak") or 0)
    streak = streak + 1 if (last and now_ts - last <= cooldown * 2) else 1
    base = max(0, int(cfg.get("daily_amount") or 0))
    bonus = min(7, max(0, streak - 1)) * max(1, base // 10)   # bonus maksimal +70%
    amount = base + bonus

    entry["last_daily"] = now_ts
    entry["daily_streak"] = streak
    add_coins(gid, user_id, amount, now=now_ts)
    return True, amount, streak


def daily_ready_in(guild_id: int, user_id: int, *, now: float | None = None) -> int:
    """Sisa detik sampai hadiah harian bisa diklaim lagi (0 = siap)."""
    cfg = economy_guilds.get(int(guild_id)) or {}
    cooldown = max(3600, int(cfg.get("daily_cooldown") or 86400))
    last = float((meta.get(_key(guild_id, user_id)) or {}).get("last_daily") or 0)
    now_ts = time.time() if now is None else float(now)
    if not last:
        return 0
    return max(0, int(cooldown - (now_ts - last)))


def transfer(
    guild_id: int,
    from_user: int,
    to_user: int,
    amount: int,
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    """Memindahkan koin antar member. Mengembalikan `(berhasil, pesan)`."""
    gid = int(guild_id)
    if not is_active(gid):
        return False, "Ekonomi belum aktif di server ini."
    if int(from_user) == int(to_user):
        return False, "Tidak bisa transfer ke diri sendiri."
    value = _to_int(amount)
    if value < TRANSFER_MIN:
        return False, f"Minimal transfer `{TRANSFER_MIN}` koin."
    if balance(gid, from_user) < value:
        return False, "Saldo kamu tidak cukup."

    now_ts = time.time() if now is None else float(now)
    key = _key(gid, from_user)
    last = float(_last_transfer.get(key) or 0)
    if last and now_ts - last < TRANSFER_COOLDOWN_SEC:
        return False, f"Tunggu `{TRANSFER_COOLDOWN_SEC}` detik sebelum transfer lagi."
    _last_transfer[key] = now_ts

    add_coins(gid, from_user, -value, now=now_ts)
    add_coins(gid, to_user, value, now=now_ts)
    return True, f"Berhasil mengirim **{value}** koin."


def leaderboard(guild_id: int, *, limit: int = 10) -> list[tuple[int, int]]:
    """Papan kekayaan server `[(user_id, koin)]` terurut menurun."""
    gid = int(guild_id)
    rows: list[tuple[int, int]] = []
    for key, value in balances.items():
        try:
            gid_str, uid_str = key.split(":", 1)
        except ValueError:
            continue
        if int(gid_str) != gid:
            continue
        rows.append((int(uid_str), int(value)))
    rows.sort(key=lambda pair: pair[1], reverse=True)
    return rows[: max(1, int(limit))]


def net_worth(guild_id: int) -> int:
    return sum(value for _uid, value in leaderboard(guild_id, limit=10_000))


# ==============================================================================
# TOKO
# ==============================================================================
def items(guild_id: int) -> dict[str, dict]:
    return shop.setdefault(int(guild_id), {})


def add_item(
    guild_id: int,
    name: str,
    price: int,
    *,
    role_id: int | None = None,
    description: str = "",
) -> tuple[dict | None, str]:
    """Menambah item toko. Mengembalikan `(item, status)` dengan status:
    `added`, `updated`, `full`, atau `invalid`."""
    gid = int(guild_id)
    clean_name = " ".join(str(name or "").split())[:60]
    cost = max(1, _to_int(price))
    if not clean_name:
        return None, "invalid"

    bucket = items(gid)
    item_id = clean_name.lower()
    existing = bucket.get(item_id)
    if existing is None and len(bucket) >= MAX_ITEMS:
        return None, "full"

    # Bila role tidak disebut saat memperbarui item, hadiah role lama dipertahankan
    resolved_role = _to_int(role_id) or _to_int((existing or {}).get("role_id")) or None
    entry = {
        "id": item_id,
        "name": clean_name,
        "price": cost,
        "role_id": resolved_role,
        "description": str(description or "").strip()[:200],
        "created_at": time.time() if existing is None else existing.get("created_at", time.time()),
        "sold": int((existing or {}).get("sold") or 0),
    }
    bucket[item_id] = entry
    return entry, ("updated" if existing else "added")


def remove_item(guild_id: int, item_id: str) -> bool:
    return items(guild_id).pop(str(item_id or "").strip().lower(), None) is not None


def find_item(guild_id: int, query: str) -> dict | None:
    q = str(query or "").strip().lower()
    if not q:
        return None
    bucket = items(guild_id)
    if q in bucket:
        return bucket[q]
    for item in bucket.values():
        if item["name"].lower() == q or item["id"] == q:
            return item
    return None


def buy(guild_id: int, user_id: int, item_id: str) -> tuple[bool, str, int | None]:
    """Membeli item toko. Mengembalikan `(berhasil, pesan, role_id)`."""
    gid = int(guild_id)
    if not is_active(gid):
        return False, "Ekonomi belum aktif di server ini.", None

    item = find_item(gid, item_id)
    if item is None:
        return False, "Item tidak ditemukan di toko.", None
    price = max(1, int(item.get("price") or 0))
    if balance(gid, user_id) < price:
        return False, f"Koin kamu belum cukup (butuh **{price}**).", None

    if not spend_coins(gid, user_id, price):
        return False, "Pembelian gagal, coba lagi.", None
    item["sold"] = int(item.get("sold") or 0) + 1
    return True, f"Berhasil membeli **{item['name']}** seharga **{price}** koin.", item.get("role_id")


# ==============================================================================
# SIMPAN / MUAT / BERSIH-BERSIH
# ==============================================================================
def _prune() -> None:
    """Menyisakan member dengan saldo terbesar per server (hemat RAM/disk)."""
    per_guild: dict[int, list[tuple[str, int]]] = {}
    for key, value in balances.items():
        try:
            gid = int(key.split(":", 1)[0])
        except ValueError:
            continue
        per_guild.setdefault(gid, []).append((key, int(value)))

    for items_list in per_guild.values():
        if len(items_list) <= MAX_MEMBERS:
            continue
        items_list.sort(key=lambda pair: pair[1], reverse=True)
        for key, _value in items_list[MAX_MEMBERS:]:
            balances.pop(key, None)
            meta.pop(key, None)


def load_economy_from_disk() -> tuple[int, int]:
    """Memuat konfigurasi, saldo, & toko dari `data/economy.json`."""
    economy_guilds.clear()
    balances.clear()
    meta.clear()
    shop.clear()

    path = Path(ECONOMY_FILE)
    if not path.exists():
        return 0, 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0, 0

    for gid_str, data in (raw.get("guilds") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        cfg = default_config()
        cfg.update(
            {
                "enabled": bool((data or {}).get("enabled", False)),
                "currency": str((data or {}).get("currency") or cfg["currency"])[:20],
                "emoji": str((data or {}).get("emoji") or cfg["emoji"])[:16],
                "per_message": max(0, _to_int((data or {}).get("per_message"), cfg["per_message"])),
                "cooldown": max(0, _to_int((data or {}).get("cooldown"), cfg["cooldown"])),
                "per_voice_min": max(0, _to_int((data or {}).get("per_voice_min"), cfg["per_voice_min"])),
                "daily_amount": max(0, _to_int((data or {}).get("daily_amount"), cfg["daily_amount"])),
                "daily_cooldown": max(3600, _to_int((data or {}).get("daily_cooldown"), cfg["daily_cooldown"])),
                "ignore_channels": [
                    _to_int(c) for c in ((data or {}).get("ignore_channels") or []) if _to_int(c)
                ],
            }
        )
        economy_guilds[gid] = cfg

    for key, value in (raw.get("balances") or {}).items():
        try:
            gid_str, uid_str = str(key).split(":", 1)
            int(gid_str), int(uid_str)
        except (TypeError, ValueError):
            continue
        amount = _to_int(value)
        if amount > 0:
            balances[str(key)] = amount

    for key, data in (raw.get("meta") or {}).items():
        if not isinstance(data, dict):
            continue
        meta[key] = {
            "last_earn": float(data.get("last_earn") or 0),
            "last_daily": float(data.get("last_daily") or 0),
            "daily_streak": max(0, _to_int(data.get("daily_streak"))),
        }

    for gid_str, bucket in (raw.get("shop") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        clean: dict[str, dict] = {}
        for item_id, item in (bucket or {}).items():
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            clean[str(item_id)] = {
                "id": str(item_id),
                "name": name[:60],
                "price": max(1, _to_int(item.get("price"), 1)),
                "role_id": _to_int(item.get("role_id")) or None,
                "description": str(item.get("description") or "")[:200],
                "created_at": float(item.get("created_at") or 0),
                "sold": max(0, _to_int(item.get("sold"))),
            }
        shop[gid] = clean

    return len(economy_guilds), len(balances)


async def save_economy_to_disk() -> None:
    """Menyimpan seluruh data ekonomi secara atomik (setelah dipangkas)."""
    async with _lock:
        try:
            _prune()
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "guilds": {str(gid): cfg for gid, cfg in economy_guilds.items()},
                "balances": balances,
                "meta": meta,
                "shop": {str(gid): bucket for gid, bucket in shop.items() if bucket},
            }
            tmp_file = Path(str(ECONOMY_FILE) + ".tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, ECONOMY_FILE)
        except Exception:  # pragma: no cover - I/O gagal
            logger.exception("Gagal menyimpan economy.json")


def cleanup_economy_runtime(max_guilds: int = 200) -> int:
    """Membersihkan rate-limit transfer & server tanpa konfigurasi (hemat RAM)."""
    removed = 0
    _last_transfer.clear()
    while len(economy_guilds) > max_guilds:
        economy_guilds.pop(next(iter(economy_guilds)))
        removed += 1
    return removed


def format_coins(value: int, cfg: dict | None = None) -> str:
    """Format koin dengan emoji & nama mata uang server."""
    rules = cfg or {}
    emoji = rules.get("emoji") or "🪙"
    return f"{emoji} **{int(value):,}** {rules.get('currency') or 'koin'}"
