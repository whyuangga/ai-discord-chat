"""Setelan AI per member & "kepribadian" AI per server (gaya purpleGPT `/settings` & `/server_prompt`).

- **Per member:** panjang jawaban, temperature, bahasa balasan, rasio gambar, prompt pribadi (maks 300 huruf).
- **Per server:** satu prompt kepribadian yang ditempelkan ke semua balasan AI di server itu.

Semua disimpan di `data/ai_settings.json` (satu berkas, tanpa proses baru). Instruksi hanya
berupa teks tambahan pada prompt — kuota tidak bertambah dan model tidak berubah.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger("gemini_bot.ai_user_settings")

SETTINGS_FILE = Path(DATA_DIR) / "ai_settings.json"

MAKS_PROMPT = 300
MAKS_PROMPT_SERVER = 500
PANJANG: dict[str, str] = {
    "singkat": "Jawab sesingkat mungkin (maks 3 kalimat), langsung ke inti.",
    "normal": "",
    "detail": "Jawab lengkap dengan poin-poin, contoh singkat, dan kesimpulan.",
}
# None pada pilihan "bawaan" berarti gunakan temperature model yang sudah dipilih sesi.
TEMPERATUR: dict[str, float | None] = {
    "bawaan": None,
    "konsisten": 0.2,
    "seimbang": 0.7,
    "kreatif": 1.0,
}
# Pilihan balasan. `auto` mengikuti bahasa pertanyaan; nama kode disimpan stabil di JSON.
BAHASA: dict[str, str] = {
    "auto": "",
    "id": "Bahasa Indonesia",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "pt": "Português",
    "zh": "中文 (Chinese)",
}

users: dict[int, dict] = {}
servers: dict[int, dict] = {}


def _to_int(nilai: object) -> int:
    try:
        return int(str(nilai or "0").strip())
    except (TypeError, ValueError):
        return 0


def default_user() -> dict:
    return {
        "panjang": "normal",
        "prompt": "",
        "rasio": "",
        "temperatur": "bawaan",
        "bahasa": "auto",
    }


# ==============================================================================
# PER MEMBER
# ==============================================================================


def get_user(user_id: int) -> dict:
    """Setelan milik satu member (selalu lengkap, walau belum pernah mengatur)."""
    data = dict(default_user())
    data.update({k: v for k, v in (users.get(_to_int(user_id)) or {}).items() if k in data})
    if data["panjang"] not in PANJANG:
        data["panjang"] = "normal"
    if data["temperatur"] not in TEMPERATUR:
        data["temperatur"] = "bawaan"
    if data["bahasa"] not in BAHASA:
        data["bahasa"] = "auto"
    data["prompt"] = str(data["prompt"] or "")[:MAKS_PROMPT]
    data["rasio"] = str(data["rasio"] or "")[:40]
    return data


def set_user(
    user_id: int,
    *,
    panjang: str | None = None,
    prompt: str | None = None,
    rasio: str | None = None,
    temperatur: str | None = None,
    bahasa: str | None = None,
) -> dict:
    """Ubah setelan member. Nilai `None` = tidak diubah."""
    uid = _to_int(user_id)
    data = get_user(uid)
    if panjang is not None:
        data["panjang"] = panjang if panjang in PANJANG else "normal"
    if prompt is not None:
        data["prompt"] = str(prompt).strip()[:MAKS_PROMPT]
    if rasio is not None:
        data["rasio"] = str(rasio).strip()[:40]
    if temperatur is not None:
        data["temperatur"] = temperatur if temperatur in TEMPERATUR else "bawaan"
    if bahasa is not None:
        data["bahasa"] = bahasa if bahasa in BAHASA else "auto"
    if data == default_user():
        users.pop(uid, None)
    else:
        users[uid] = data
    return data


def reset_user(user_id: int) -> None:
    users.pop(_to_int(user_id), None)


def get_temperature(user_id: int | None) -> float | None:
    """Temperature override per member (`None` = ikuti bawaan model)."""
    if not user_id:
        return None
    value = TEMPERATUR.get(get_user(user_id)["temperatur"])
    return float(value) if value is not None else None


def language_instruction(user_id: int | None) -> str:
    """Instruksi bahasa yang ditetapkan member; kosong jika pilihannya `auto`."""
    if not user_id:
        return ""
    code = get_user(user_id)["bahasa"]
    language = BAHASA.get(code, "")
    if not language:
        return ""
    return (
        f"Preferensi bahasa balasan member ini: gunakan {language}. "
        "Tetap ikuti permintaan eksplisit pengguna untuk bahasa lain dan pertahankan nama, "
        "kutipan, sintaks kode, serta istilah asli bila relevan."
    )


# ==============================================================================
# PER SERVER
# ==============================================================================


def get_server_prompt(guild_id: int) -> str:
    return str((servers.get(_to_int(guild_id)) or {}).get("prompt") or "")


def set_server_prompt(guild_id: int, teks: str, *, oleh: int = 0) -> str:
    """Atur kepribadian AI satu server. Teks kosong = hapus."""
    gid = _to_int(guild_id)
    isi = " ".join(str(teks or "").split())[:MAKS_PROMPT_SERVER]
    if not isi:
        servers.pop(gid, None)
        return ""
    servers[gid] = {"prompt": isi, "oleh": _to_int(oleh)}
    return isi


def reset_server_prompt(guild_id: int) -> None:
    servers.pop(_to_int(guild_id), None)


# ==============================================================================
# PENGGABUNGAN UNTUK PROMPT AI
# ==============================================================================


def gabung_instruksi(user_id: int | None = None, guild_id: int | None = None) -> str:
    """Gabungkan instruksi member + server menjadi satu kalimat untuk prompt AI."""
    bagian: list[str] = []
    if user_id:
        data = get_user(user_id)
        if data["panjang"] in PANJANG and PANJANG[data["panjang"]]:
            bagian.append(PANJANG[data["panjang"]])
        if data["prompt"]:
            bagian.append(f"Preferensi member ini: {data['prompt']}")
        bahasa = language_instruction(user_id)
        if bahasa:
            bagian.append(bahasa)
    if guild_id:
        server = get_server_prompt(guild_id)
        if server:
            bagian.append(f"Kepribadian server: {server}")
    return " | ".join(bagian)[:900]


def rasio_bawaan(user_id: int | None) -> str:
    """Rasio gambar bawaan pilihan member ("" bila tidak diatur)."""
    if not user_id:
        return ""
    return str(get_user(user_id).get("rasio") or "")


def statistik() -> dict:
    """Ringkasan untuk dashboard/dokumentasi."""
    return {
        "member": len(users),
        "server": len(servers),
        "panjang": {k: sum(1 for v in users.values() if v.get("panjang") == k) for k in PANJANG},
        "rasio": sum(1 for v in users.values() if v.get("rasio")),
        "prompt_member": sum(1 for v in users.values() if v.get("prompt")),
        "temperatur": sum(1 for v in users.values() if v.get("temperatur") != "bawaan"),
        "bahasa": sum(1 for v in users.values() if v.get("bahasa") != "auto"),
    }


# ==============================================================================
# SIMPAN / MUAT
# ==============================================================================


def reset_state() -> None:
    users.clear()
    servers.clear()


def load_from_disk() -> tuple[int, int]:
    """Muat setelan member & server. Berkas rusak diabaikan."""
    users.clear()
    servers.clear()
    path = Path(SETTINGS_FILE)
    if not path.exists():
        return 0, 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, 0
    if not isinstance(raw, dict):
        return 0, 0

    for uid_str, nilai in (raw.get("users") or {}).items():
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            continue
        data = nilai if isinstance(nilai, dict) else {}
        isi = {
            "panjang": str(data.get("panjang") or "normal"),
            "prompt": str(data.get("prompt") or "")[:MAKS_PROMPT],
            "rasio": str(data.get("rasio") or "")[:40],
            "temperatur": str(data.get("temperatur") or "bawaan"),
            "bahasa": str(data.get("bahasa") or "auto"),
        }
        if isi["panjang"] not in PANJANG:
            isi["panjang"] = "normal"
        if isi["temperatur"] not in TEMPERATUR:
            isi["temperatur"] = "bawaan"
        if isi["bahasa"] not in BAHASA:
            isi["bahasa"] = "auto"
        if isi != default_user():
            users[uid] = isi

    for gid_str, nilai in (raw.get("servers") or {}).items():
        try:
            gid = int(gid_str)
        except (TypeError, ValueError):
            continue
        data = nilai if isinstance(nilai, dict) else {}
        teks = str(data.get("prompt") or "")[:MAKS_PROMPT_SERVER]
        if teks:
            servers[gid] = {"prompt": teks, "oleh": _to_int(data.get("oleh"))}
    return len(users), len(servers)


async def save_to_disk() -> None:
    """Tulis setelan secara atomik."""
    path = Path(SETTINGS_FILE)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        isi = {
            "versi": 1,
            "users": {str(uid): data for uid, data in users.items()},
            "servers": {str(gid): data for gid, data in servers.items()},
        }
        sementara = Path(str(path) + ".tmp")
        sementara.write_text(json.dumps(isi, ensure_ascii=False, indent=1), encoding="utf-8")
        sementara.replace(path)
    except OSError as exc:
        logger.warning("Gagal menyimpan %s: %s", path, exc)
