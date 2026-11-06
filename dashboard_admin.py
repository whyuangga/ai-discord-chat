"""Setelan server yang bisa diubah dari dashboard web — **satu sumber kebenaran**.

Modul ini adalah "kamus aksi" dashboard: setiap fitur yang boleh diubah dari web
didaftarkan di sini (label, jenis kontrol, pembaca nilai, & penyimpan nilai).
Halaman HTML hanya menggambar daftar ini, dan `POST /api/aksi` hanya menjalankan
kunci yang ada di daftar — jadi tidak ada jalur untuk memanggil fungsi sembarang.

Prinsip:

1. **Whitelist** — kunci di luar `FITUR` selalu ditolak.
2. **Tanpa dependency baru & tanpa kuota AI** — hanya membaca/menulis JSON lokal.
3. **Jejak audit** — setiap perubahan dicatat ke `data/dashboard_audit.json`
   (maksimal 300 entri terakhir) berisi waktu, kunci, nilai, & hasilnya.
4. **Aman untuk tes** — semua pembacaan dibungkus `try/except`; server tanpa data
   tetap menampilkan nilai bawaan.

Jenis kontrol (`jenis`):

| Jenis | Kontrol di halaman |
| :--- | :--- |
| `saklar` | dropdown Aktif / Nonaktif |
| `pilihan` | dropdown dari `opsi` |
| `channel` | dropdown channel server (`0` = tidak dipakai) |
| `role` | dropdown role server (`0` = tidak dipakai) |
| `teks` | kotak teks pendek |
| `angka` | kotak angka |
"""

import asyncio
import importlib
import json
import logging
import time
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger("gemini_bot.dashboard_admin")

AUDIT_FILE = Path(DATA_DIR) / "dashboard_audit.json"
MAX_AUDIT = 300
_audit_lock = asyncio.Lock()
_audit_cache: list[dict] | None = None

SAKLAR_OPSI = (("on", "Aktif"), ("off", "Nonaktif"))


# ==============================================================================
# NILAI BAWAAN & PEMBANTU
# ==============================================================================
def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _mod(nama: str):
    return importlib.import_module(nama)


def _cfg(nama: str, guild_id: int, getter: str = "get_config") -> dict:
    """Baca konfigurasi modul dengan jaring aman (selalu dict)."""
    try:
        data = getattr(_mod(nama), getter)(int(guild_id))
        return dict(data or {})
    except Exception:  # pragma: no cover - jaring aman
        return {}


def _saklar_dari(nama: str, key: str = "enabled", bawaan: bool = False, *, getter: str = "get_config"):
    """Pembaca nilai untuk fitur yang punya kunci boolean di konfigurasinya."""

    def baca(guild_id: int) -> str:
        cfg = _cfg(nama, guild_id, getter)
        nilai = cfg.get(key)
        if nilai is None:
            nilai = bawaan
        return "on" if nilai else "off"

    return baca


def _channel_dari(nama: str, key: str = "channel_id", getter: str = "get_config"):
    def baca(guild_id: int) -> str:
        return str(_to_int(_cfg(nama, guild_id, getter).get(key)))

    return baca


def _channel_terpilih(peta: dict, guild_id: int, key: str = "guild_id") -> int:
    """Channel pertama di sebuah `dict[channel_id, cfg]` yang milik guild ini."""
    for cid, cfg in (peta or {}).items():
        if _to_int((cfg or {}).get(key)) == int(guild_id):
            return _to_int(cid)
    return 0


def _pesan(label: str, aktif: bool) -> tuple[bool, str]:
    return True, f"{label} sekarang **{'aktif' if aktif else 'nonaktif'}**."


def _hapus_keterangan(label: str, nilai: str) -> tuple[bool, str]:
    return True, f"{label} dikosongkan ({nilai})."


# ==============================================================================
# FITUR: SAKELAR SEDERHANA (enabled=True/False)
# ==============================================================================
def _set_saklar(nama: str, label: str, *, key: str = "enabled", getter: str = "set_config"):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        mod = _mod(nama)
        setter = getattr(mod, getter)
        setter(int(guild_id), **{key: nilai == "on"})
        return _pesan(label, nilai == "on")

    return simpan


# ==============================================================================
# FITUR: KANAL (0 = tidak dipakai)
# ==============================================================================
def _set_kanal_sederhana(nama: str, label: str, *, key: str, getter: str = "set_config"):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        cid = _to_int(nilai)
        setter = getattr(_mod(nama), getter)
        if cid <= 0:
            setter(int(guild_id), **{key: None})
            return _hapus_keterangan(label, "tidak ada channel")
        setter(int(guild_id), **{key: cid})
        return True, f"{label} diatur ke channel `{cid}`."

    return simpan


# ==============================================================================
# FITUR: LEVEL & EKONOMI
# ==============================================================================
def _baca_level(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        return str(_cfg("levels", guild_id, "get_level_config").get(key, bawaan))

    return baca


def _set_level_flag(key: str, label: str):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        _mod("levels").set_level_config(int(guild_id), **{key: nilai == "on"})
        return _pesan(label, nilai == "on")

    return simpan


def _set_level_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    _mod("levels").set_level_config(int(guild_id), announce_channel_id=cid or None)
    if cid <= 0:
        return _hapus_keterangan("Channel pengumuman level", "pakai channel terakhir")
    return True, f"Pengumuman naik level dikirim ke channel `{cid}`."


def _baca_ekonomi(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        return str(_cfg("economy", guild_id).get(key, bawaan))

    return baca


def _set_ekonomi_key(key: str, label: str):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        angka = _to_int(nilai)
        if angka <= 0:
            return False, "Nilai harus bilangan bulat lebih dari 0."
        _mod("economy").set_config(int(guild_id), **{key: angka})
        return True, f"{label} diset ke **{angka}**."

    return simpan


# ==============================================================================
# FITUR: SAMBUTAN, PAMIT, BOOST
# ==============================================================================
def _baca_sambutan(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        cfg = (_mod("community_agent").welcome_agent_guilds or {}).get(int(guild_id)) or {}
        return str(cfg.get(key, bawaan))

    return baca


def _set_sambutan_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    ca = _mod("community_agent")
    if cid <= 0:
        ca.set_welcome_config(int(guild_id), 0, enabled=False)
        return _hapus_keterangan("Sambutan member baru", "dimatikan")
    ca.set_welcome_config(int(guild_id), cid, enabled=True)
    return True, f"Sambutan member baru dikirim ke channel `{cid}`."


def _baca_sambutan_dm(guild_id: int) -> str:
    cfg = (_mod("community_agent").welcome_agent_guilds or {}).get(int(guild_id)) or {}
    return "on" if cfg.get("dm") else "off"


def _set_sambutan_dm(guild_id: int, nilai: str) -> tuple[bool, str]:
    ok = _mod("community_agent").set_welcome_dm(int(guild_id), nilai == "on")
    if not ok:
        return False, "Atur channel sambutan lebih dulu sebelum menyalakan DM."
    return _pesan("Sambutan via DM", nilai == "on")


def _set_sambutan_kartu(guild_id: int, nilai: str) -> tuple[bool, str]:
    mode = _mod("community_agent").set_welcome_card_mode(int(guild_id), nilai)
    if not (_mod("community_agent").welcome_agent_guilds or {}).get(int(guild_id)):
        return False, "Atur channel sambutan lebih dulu sebelum memilih kartu."
    return True, f"Kartu sambutan diset ke **{mode}**."


def _set_sambutan_persona(guild_id: int, nilai: str) -> tuple[bool, str]:
    ca = _mod("community_agent")
    cfg = (ca.welcome_agent_guilds or {}).get(int(guild_id)) or {}
    cid = _to_int(cfg.get("channel_id"))
    if cid <= 0:
        return False, "Atur channel sambutan lebih dulu."
    ca.set_welcome_config(int(guild_id), cid, enabled=True, persona=nilai)
    return True, f"Persona sambutan diset ke **{nilai}**."


def _baca_pamit(key: str = "channel_id"):
    def baca(guild_id: int) -> str:
        cfg = (_mod("community_agent").goodbye_agent_guilds or {}).get(int(guild_id)) or {}
        return str(_to_int(cfg.get(key)))

    return baca


def _set_pamit_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    ca = _mod("community_agent")
    if cid <= 0:
        ca.set_goodbye_config(int(guild_id), 0, enabled=False)
        return _hapus_keterangan("Pesan pamit", "dimatikan")
    ca.set_goodbye_config(int(guild_id), cid, enabled=True)
    return True, f"Pesan pamit dikirim ke channel `{cid}`."


def _baca_boost(key: str = "channel_id"):
    def baca(guild_id: int) -> str:
        cfg = (_mod("community_agent").boost_agent_guilds or {}).get(int(guild_id)) or {}
        return str(_to_int(cfg.get(key)))

    return baca


def _set_boost_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    ca = _mod("community_agent")
    if cid <= 0:
        ca.set_boost_config(int(guild_id), enabled=False)
        return _hapus_keterangan("Pesan boost", "dimatikan")
    ca.set_boost_config(int(guild_id), enabled=True, channel_id=cid)
    return True, f"Ucapan boost dikirim ke channel `{cid}`."


# ==============================================================================
# FITUR: AGENT AI (gaya, keamanan, jam tenang, zona waktu)
# ==============================================================================
def _baca_agent(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        return str(_mod("community_agent").get_guild_settings(int(guild_id)).get(key, bawaan))

    return baca


def _baca_agent_saklar(key: str, bawaan: bool = True):
    def baca(guild_id: int) -> str:
        nilai = _mod("community_agent").get_guild_settings(int(guild_id)).get(key, bawaan)
        return "on" if nilai else "off"

    return baca


def _set_agent_teks(key: str, label: str, validasi=None):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        bersih = nilai.strip()[:180]
        if validasi is not None:
            galat = validasi(bersih)
            if galat:
                return False, galat
        _mod("community_agent").get_guild_settings(int(guild_id))[key] = bersih
        return True, f"{label} diset ke **{bersih}**."

    return simpan


def _set_agent_saklar(key: str, label: str):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        _mod("community_agent").get_guild_settings(int(guild_id))[key] = nilai == "on"
        return _pesan(label, nilai == "on")

    return simpan


def _set_agent_gaya(guild_id: int, nilai: str) -> tuple[bool, str]:
    ca = _mod("community_agent")
    if nilai not in ca.STYLE_DESCRIPTIONS:
        return False, "Gaya bahasa tidak dikenal."
    ca.get_guild_settings(int(guild_id))["style_preset"] = nilai
    return True, f"Gaya bahasa Auto-Chat diset ke **{nilai}**."


def _set_agent_keamanan(guild_id: int, nilai: str) -> tuple[bool, str]:
    hasil = _mod("community_agent").set_guild_safety_level(int(guild_id), nilai)
    return True, f"Tingkat keamanan konten AI: **{hasil}**."


def _cek_zona(nilai: str) -> str | None:
    if not nilai:
        return "Zona waktu tidak boleh kosong (contoh: `Asia/Jakarta`)."
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(nilai)
    except Exception:
        return "Zona waktu tidak dikenal. Contoh yang benar: `Asia/Jakarta`, `Asia/Makassar`."
    return None


# ==============================================================================
# FITUR: KEAMANAN
# ==============================================================================
def _baca_antispam(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        cfg = _cfg("antispam", guild_id, "get_spam_config")
        if key == "mode" and not cfg.get("enabled"):
            return "off"
        return str(cfg.get(key, bawaan))

    return baca


def _set_antispam_mode(guild_id: int, nilai: str) -> tuple[bool, str]:
    mod = _mod("antispam")
    if nilai == "off":
        mod.set_spam_config(int(guild_id), enabled=False)
        return True, "Anti-spam **dimatikan**."
    if nilai not in mod.SPAM_MODES:
        return False, "Mode anti-spam tidak dikenal."
    mod.set_spam_config(int(guild_id), enabled=True, mode=nilai)
    return True, f"Anti-spam aktif dengan mode **{nilai}**."


def _baca_antispam_caps(guild_id: int) -> str:
    return "on" if _cfg("antispam", guild_id, "get_spam_config").get("caps_enabled") else "off"


def _set_antispam_caps(guild_id: int, nilai: str) -> tuple[bool, str]:
    _mod("antispam").set_spam_config(int(guild_id), caps_enabled=nilai == "on")
    return _pesan("Deteksi HURUF KAPITAL berlebihan", nilai == "on")


def _set_antispam_log(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    _mod("antispam").set_spam_config(int(guild_id), log_channel_id=cid or None)
    if cid <= 0:
        return _hapus_keterangan("Log anti-spam", "dimatikan")
    return True, f"Log anti-spam dikirim ke channel `{cid}`."


def _baca_antinuke(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        return str(_cfg("antinuke", guild_id).get(key, bawaan))

    return baca


def _set_antinuke_aksi(guild_id: int, nilai: str) -> tuple[bool, str]:
    mod = _mod("antinuke")
    if nilai not in mod.PUNISH_CHOICES:
        return False, "Aksi anti-nuke tidak dikenal."
    mod.set_config(int(guild_id), action=nilai)
    return True, f"Anti-Nuke memakai aksi **{nilai}**."


def _set_antinuke_log(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    _mod("antinuke").set_log_channel(int(guild_id), cid or None)
    if cid <= 0:
        return _hapus_keterangan("Log anti-nuke", "dimatikan")
    return True, f"Log anti-nuke dikirim ke channel `{cid}`."


def _baca_raid(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        return str(_cfg("raid_guard", guild_id).get(key, bawaan))

    return baca


def _set_raid_aktif(guild_id: int, nilai: str) -> tuple[bool, str]:
    _mod("raid_guard").set_config(int(guild_id), enabled=nilai == "on")
    return _pesan("Pengaman raid", nilai == "on")


def _set_raid_aksi(guild_id: int, nilai: str) -> tuple[bool, str]:
    mod = _mod("raid_guard")
    if nilai not in mod.ACTIONS:
        return False, "Aksi raid tidak dikenal."
    mod.set_config(int(guild_id), action=nilai)
    return True, f"Aksi saat raid: **{nilai}**."


def _baca_verifikasi(key: str):
    def baca(guild_id: int) -> str:
        cfg = (_mod("community_tools").verification_guilds or {}).get(int(guild_id)) or {}
        return str(_to_int(cfg.get(key)))

    return baca


def _set_verifikasi_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    mod = _mod("community_tools")
    if cid <= 0:
        mod.set_verification_config(int(guild_id), enabled=False)
        return _hapus_keterangan("Gerbang verifikasi", "dimatikan")
    mod.set_verification_config(int(guild_id), channel_id=cid, enabled=True)
    return True, f"Gerbang verifikasi dipasang di channel `{cid}`."


def _set_verifikasi_role(guild_id: int, nilai: str) -> tuple[bool, str]:
    rid = _to_int(nilai)
    mod = _mod("community_tools")
    cfg = (mod.verification_guilds or {}).get(int(guild_id)) or {}
    if not cfg.get("channel_id"):
        return False, "Atur channel verifikasi lebih dulu."
    if rid <= 0:
        return False, "Pilih role yang diberikan setelah verifikasi."
    mod.set_verification_config(int(guild_id), role_id=rid)
    return True, f"Role setelah verifikasi: `{rid}`."


def _baca_security(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        cfg = (_mod("server_features").security_guilds or {}).get(int(guild_id)) or {}
        if key == "enabled":
            return "on" if cfg.get("enabled") else "off"
        return str(cfg.get(key, bawaan))

    return baca


def _set_security_aktif(guild_id: int, nilai: str) -> tuple[bool, str]:
    _mod("server_features").set_security_config(int(guild_id), enabled=nilai == "on")
    return _pesan("Proteksi anti-phishing", nilai == "on")


# ==============================================================================
# FITUR: TIKET, ULANG TAHUN
# ==============================================================================
def _baca_tiket(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        cfg = _cfg("tickets", guild_id, "get_ticket_config")
        if key == "enabled":
            return "on" if cfg.get("enabled") else "off"
        return str(cfg.get(key) if cfg.get(key) is not None else bawaan or 0)

    return baca


def _set_tiket(perubahan: dict, label: str, *, aktif: bool | None = None):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        kwargs = dict(perubahan)
        _mod("tickets").set_ticket_config(int(guild_id), **kwargs)
        return True, f"{label} tersimpan."

    return simpan


def _set_tiket_aktif(guild_id: int, nilai: str) -> tuple[bool, str]:
    _mod("tickets").set_ticket_config(int(guild_id), enabled=nilai == "on")
    return _pesan("Sistem tiket", nilai == "on")


def _baca_tiket_flag(key: str, bawaan: bool = True):
    def baca(guild_id: int) -> str:
        cfg = _cfg("tickets", guild_id, "get_ticket_config")
        return "on" if cfg.get(key, bawaan) else "off"

    return baca


def _set_tiket_flag(key: str, label: str):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        _mod("tickets").set_ticket_config(int(guild_id), **{key: nilai == "on"})
        return _pesan(label, nilai == "on")

    return simpan


def _set_tiket_angka(key: str, label: str):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        angka = _to_int(nilai)
        if angka < 0:
            return False, "Nilai tidak boleh negatif."
        _mod("tickets").set_ticket_config(int(guild_id), **{key: angka})
        return True, f"{label} diset ke **{angka}**."

    return simpan


def _set_tiket_id(key: str, label: str):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        angka = _to_int(nilai)
        # `0` (bukan None) supaya set_ticket_config benar-benar mengosongkan nilai.
        _mod("tickets").set_ticket_config(int(guild_id), **{key: angka})
        if angka <= 0:
            return _hapus_keterangan(label, "dikosongkan")
        return True, f"{label} diset ke `{angka}`."

    return simpan


def _baca_ultah(key: str = "channel_id"):
    def baca(guild_id: int) -> str:
        cfg = (_mod("engagement").birthday_guilds or {}).get(int(guild_id)) or {}
        return str(_to_int(cfg.get(key)))

    return baca


def _set_ultah_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    mod = _mod("engagement")
    if cid <= 0:
        mod.disable_birthday_channel(int(guild_id))
        return _hapus_keterangan("Ucapan ulang tahun", "dimatikan")
    mod.set_birthday_channel(int(guild_id), cid)
    return True, f"Ucapan ulang tahun dikirim ke channel `{cid}`."


# ==============================================================================
# FITUR: KONTEN & INTERAKSI
# ==============================================================================
def _baca_starboard(key: str):
    def baca(guild_id: int) -> str:
        cfg = (_mod("community_tools").starboard_guilds or {}).get(int(guild_id)) or {}
        if key == "enabled":
            return "on" if cfg.get("channel_id") else "off"
        return str(_to_int(cfg.get(key)))

    return baca


def _set_starboard_channel(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    mod = _mod("community_tools")
    if cid <= 0:
        mod.set_starboard_config(int(guild_id), enabled=False)
        return _hapus_keterangan("Starboard", "dimatikan")
    mod.set_starboard_config(int(guild_id), channel_id=cid, enabled=True)
    return True, f"Starboard memakai channel `{cid}`."


def _baca_starboard_ambang(guild_id: int) -> str:
    cfg = (_mod("community_tools").starboard_guilds or {}).get(int(guild_id)) or {}
    return str(_to_int(cfg.get("threshold") or 3))


def _set_starboard_ambang(guild_id: int, nilai: str) -> tuple[bool, str]:
    angka = _to_int(nilai)
    if angka < 1 or angka > 25:
        return False, "Ambang starboard harus 1–25 bintang."
    _mod("community_tools").set_starboard_config(int(guild_id), threshold=angka)
    return True, f"Ambang starboard diset ke **{angka}** bintang."


def _baca_saran(guild_id: int) -> str:
    return str(_to_int(_mod("suggestions").get_channel(int(guild_id))))


def _set_saran(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    _mod("suggestions").set_channel(int(guild_id), cid or None)
    if cid <= 0:
        return _hapus_keterangan("Channel saran", "dikosongkan")
    return True, f"Kotak saran dipasang di channel `{cid}`."


def _baca_agent_channel(nama_peta: str):
    def baca(guild_id: int) -> str:
        peta = getattr(_mod("community_agent"), nama_peta, {}) or {}
        return str(_channel_terpilih(peta, guild_id))

    return baca


def _set_agent_channel(setter: str, label: str, peta: str, **extra):
    def simpan(guild_id: int, nilai: str) -> tuple[bool, str]:
        ca = _mod("community_agent")
        peta_dict = getattr(ca, peta, {}) or {}
        lama = _channel_terpilih(peta_dict, guild_id)
        cid = _to_int(nilai)
        fungsi = getattr(ca, setter)
        if lama and lama != cid:
            fungsi(int(guild_id), lama, enabled=False)
        if cid <= 0:
            return _hapus_keterangan(label, "dimatikan")
        fungsi(int(guild_id), cid, enabled=True, **extra)
        return True, f"{label} aktif di channel `{cid}`."

    return simpan


def _baca_digest(guild_id: int) -> str:
    cfg = (_mod("community_agent").digest_agent_guilds or {}).get(int(guild_id)) or {}
    return str(_to_int(cfg.get("channel_id")))


def _set_digest(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    ca = _mod("community_agent")
    if cid <= 0:
        ca.set_digest_config(int(guild_id), 0, enabled=False)
        return _hapus_keterangan("Koran pagi (digest)", "dimatikan")
    ca.set_digest_config(int(guild_id), cid, enabled=True)
    return True, f"Koran pagi dikirim ke channel `{cid}`."


def _baca_terjemah(guild_id: int) -> str:
    cfg = _mod("translate_tools").get_guild_config(int(guild_id))
    channels = cfg.get("channels") or {}
    for cid in channels:
        return str(_to_int(cid))
    return "0"


def _set_terjemah(guild_id: int, nilai: str) -> tuple[bool, str]:
    mod = _mod("translate_tools")
    cid = _to_int(nilai)
    lama = _to_int(_baca_terjemah(guild_id))
    if lama and lama != cid:
        mod.set_channel_config(int(guild_id), lama, enabled=False)
    if cid <= 0:
        return _hapus_keterangan("Terjemahan otomatis", "dimatikan")
    mod.set_channel_config(int(guild_id), cid, enabled=True)
    return True, f"Terjemahan otomatis aktif di channel `{cid}`."


def _baca_serverstats(guild_id: int) -> str:
    cfg = (_mod("server_features").serverstats_guilds or {}).get(int(guild_id)) or {}
    return "on" if cfg.get("enabled") else "off"


def _set_serverstats(guild_id: int, nilai: str) -> tuple[bool, str]:
    _mod("server_features").set_serverstats_config(int(guild_id), enabled=nilai == "on")
    return _pesan("Statistik server (voice)", nilai == "on")


def _baca_fakta(guild_id: int) -> str:
    cfg = (_mod("server_features").facts_guilds or {}).get(int(guild_id)) or {}
    return str(_to_int(cfg.get("channel_id")))


def _set_fakta(guild_id: int, nilai: str) -> tuple[bool, str]:
    mod = _mod("server_features")
    cid = _to_int(nilai)
    if cid <= 0:
        mod.set_facts_config(int(guild_id), 0, enabled=False)
        return _hapus_keterangan("Fakta harian", "dimatikan")
    mod.set_facts_config(int(guild_id), cid, enabled=True)
    return True, f"Fakta harian dikirim ke channel `{cid}`."


def _baca_backup(guild_id: int) -> str:
    cfg = (_mod("community_tools").maintenance_guilds or {}).get(int(guild_id)) or {}
    return str(_to_int(cfg.get("backup_channel_id")))


def _set_backup(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    _mod("community_tools").set_maintenance_config(int(guild_id), backup_channel_id=cid or None)
    if cid <= 0:
        return _hapus_keterangan("Channel backup", "dikosongkan")
    return True, f"Backup otomatis dikirim ke channel `{cid}`."


def _baca_prefix(guild_id: int) -> str:
    return str(_mod("prefixes").get_prefix(int(guild_id)) or "")


def _set_prefix(guild_id: int, nilai: str) -> tuple[bool, str]:
    ok, _bersih, pesan = _mod("prefixes").set_prefix(int(guild_id), nilai)
    if not ok:
        return False, pesan
    return True, pesan


def _baca_tumbuh(key: str, bawaan=None):
    def baca(guild_id: int) -> str:
        cfg = _cfg("growth_tracker", guild_id)
        return str(cfg.get(key, bawaan))

    return baca


def _set_tumbuh_log(guild_id: int, nilai: str) -> tuple[bool, str]:
    cid = _to_int(nilai)
    _mod("growth_tracker").set_log_channel(int(guild_id), cid or None)
    if cid <= 0:
        return _hapus_keterangan("Log pertumbuhan", "dimatikan")
    return True, f"Log pertumbuhan dikirim ke channel `{cid}`."


# ==============================================================================
# DEFINISI FITUR & GRUP
# ==============================================================================
def _f(kunci, label, jenis, nilai, simpan, modul, *, opsi=None, bantuan=""):
    return {
        "kunci": kunci,
        "label": label,
        "jenis": jenis,
        "nilai": nilai,
        "simpan": simpan,
        "modul": modul,
        "opsi": opsi or (),
        "bantuan": bantuan,
    }


FITUR_LIST = [
    # --- Inti & angka ---------------------------------------------------------
    _f("level.aktif", "Level & XP", "saklar",
       lambda g: "on" if _mod("levels").is_leveling_active(int(g)) else "off",
       _set_level_flag("enabled", "Level & XP"), "levels"),
    _f("level.pengumuman", "Pengumuman naik level", "saklar",
       lambda g: "on" if _cfg("levels", g, "get_level_config").get("announce", True) else "off",
       _set_level_flag("announce", "Pengumuman naik level"), "levels"),
    _f("level.channel", "Channel pengumuman level", "channel",
       lambda g: str(_to_int(_cfg("levels", g, "get_level_config").get("announce_channel_id"))),
       _set_level_channel, "levels"),
    _f("ekonomi.aktif", "Ekonomi koin", "saklar", _saklar_dari("economy"), _set_saklar("economy", "Ekonomi koin"), "economy"),
    _f("ekonomi.harian", "Koin harian (/harian)", "angka", _baca_ekonomi("daily_amount", 100),
       _set_ekonomi_key("daily_amount", "Koin harian"), "economy"),
    _f("tumbuh.aktif", "Pelacakan pertumbuhan", "saklar", _saklar_dari("growth_tracker"),
       _set_saklar("growth_tracker", "Pelacakan pertumbuhan"), "growth_tracker"),
    _f("tumbuh.channel", "Channel log pertumbuhan", "channel",
       lambda g: str(_to_int(_cfg("growth_tracker", g).get("log_channel_id"))),
       _set_tumbuh_log, "growth_tracker"),
    _f("prefix", "Prefix custom (teks)", "teks", _baca_prefix, _set_prefix, "prefixes",
       bantuan="Kosongkan untuk kembali ke prefix bawaan."),
    # --- Sambutan & pamit ----------------------------------------------------
    _f("sambutan.channel", "Channel sambutan", "channel", _baca_sambutan("channel_id", 0),
       _set_sambutan_channel, "community_agent"),
    _f("sambutan.dm", "Sambutan via DM", "saklar", _baca_sambutan_dm,
       _set_sambutan_dm, "community_agent"),
    _f("sambutan.kartu", "Kartu sambutan", "pilihan", _baca_sambutan("card_mode", "mati"),
       _set_sambutan_kartu, "community_agent",
       opsi=(("mati", "Mati"), ("statis", "Statis"), ("dinamis", "Dinamis"))),
    _f("sambutan.persona", "Persona sambutan", "pilihan", _baca_sambutan("persona", "hangat"),
       _set_sambutan_persona, "community_agent",
       opsi=(("hangat", "🤗 Hangat"), ("lucu", "😄 Lucu"), ("santai", "😎 Santai"),
             ("normal", "🙂 Normal"))),
    _f("pamit.channel", "Channel pesan pamit", "channel", _baca_pamit(), _set_pamit_channel,
       "community_agent"),
    _f("boost.channel", "Channel ucapan boost", "channel", _baca_boost(), _set_boost_channel,
       "community_agent"),
    # --- Keamanan -----------------------------------------------------------
    _f("antispam.mode", "Mode anti-spam", "pilihan", _baca_antispam("mode", "lapor"),
       _set_antispam_mode, "antispam",
       opsi=(("off", "Mati"), ("lapor", "Lapor"), ("hapus", "Hapus pesan"),
             ("timeout", "Timeout member"))),
    _f("antispam.caps", "Deteksi HURUF KAPITAL", "saklar", _baca_antispam_caps,
       _set_antispam_caps, "antispam"),
    _f("antispam.log", "Log anti-spam", "channel",
       lambda g: str(_to_int(_cfg("antispam", g, "get_spam_config").get("log_channel_id"))),
       _set_antispam_log, "antispam"),
    _f("antinuke.aksi", "Aksi anti-nuke", "pilihan", _baca_antinuke("action", "lapor"),
       _set_antinuke_aksi, "antinuke",
       opsi=(("lapor", "Lapor"), ("cabut-role", "Cabut role"), ("timeout", "Timeout"),
             ("kick", "Kick"), ("ban", "Ban"))),
    _f("antinuke.log", "Log anti-nuke", "channel",
       lambda g: str(_to_int(_cfg("antinuke", g).get("log_channel_id"))),
       _set_antinuke_log, "antinuke"),
    _f("raid.aktif", "Pengaman raid", "saklar", _saklar_dari("raid_guard"),
       _set_raid_aktif, "raid_guard"),
    _f("raid.aksi", "Aksi saat raid", "pilihan", _baca_raid("action", "verifikasi"),
       _set_raid_aksi, "raid_guard",
       opsi=(("lapor", "Lapor saja"), ("verifikasi", "Tahan auto-role"),
             ("verifikasi+lockdown", "Tahan + lockdown"))),
    _f("verifikasi.channel", "Channel verifikasi", "channel", _baca_verifikasi("channel_id"),
       _set_verifikasi_channel, "community_tools"),
    _f("verifikasi.role", "Role setelah verifikasi", "role", _baca_verifikasi("role_id"),
       _set_verifikasi_role, "community_tools"),
    _f("keamanan.aktif", "Proteksi anti-phishing", "saklar", _baca_security("enabled"),
       _set_security_aktif, "server_features"),
    # --- Tiket & sapaan harian ---------------------------------------------
    _f("tiket.aktif", "Sistem tiket", "saklar", _baca_tiket("enabled"), _set_tiket_aktif, "tickets"),
    _f("tiket.staff", "Role staf tiket", "role", _baca_tiket("staff_role_id"),
       _set_tiket_id("staff_role_id", "Role staf tiket"), "tickets"),
    _f("tiket.kategori", "Kategori tiket", "channel", _baca_tiket("category_id"),
       _set_tiket_id("category_id", "Kategori tiket"), "tickets"),
    _f("tiket.log", "Log tiket", "channel", _baca_tiket("log_channel_id"),
       _set_tiket_id("log_channel_id", "Log tiket"), "tickets"),
    _f("tiket.maks", "Maksimal tiket terbuka", "angka", _baca_tiket("max_open", 2),
       _set_tiket_angka("max_open", "Maksimal tiket terbuka"), "tickets"),
    _f("tiket.ping", "Ping staf saat tiket dibuka", "saklar", _baca_tiket_flag("ping_staff"),
       _set_tiket_flag("ping_staff", "Ping staf"), "tickets"),
    _f("tiket.rating", "Rating setelah tiket ditutup", "saklar", _baca_tiket_flag("rating_aktif"),
       _set_tiket_flag("rating_aktif", "Rating tiket"), "tickets"),
    _f("ultah.channel", "Channel ucapan ulang tahun", "channel", _baca_ultah(),
       _set_ultah_channel, "engagement"),
    # --- Konten & interaksi -------------------------------------------------
    _f("starboard.channel", "Channel starboard", "channel", _baca_starboard("channel_id"),
       _set_starboard_channel, "community_tools"),
    _f("starboard.ambang", "Ambang bintang starboard", "angka", _baca_starboard_ambang,
       _set_starboard_ambang, "community_tools"),
    _f("saran.channel", "Channel kotak saran", "channel", _baca_saran, _set_saran,
       "suggestions"),
    _f("chat.channel", "Channel Auto-Chat AI", "channel",
       _baca_agent_channel("chat_agent_channels"), _set_agent_channel(
           "set_chat_channel_config", "Auto-Chat AI", "chat_agent_channels"), "community_agent"),
    _f("digest.channel", "Channel koran pagi", "channel", _baca_digest, _set_digest,
       "community_agent"),
    _f("galeri.channel", "Channel galeri AI", "channel",
       _baca_agent_channel("gallery_agent_channels"), _set_agent_channel(
           "set_gallery_channel_config", "Galeri AI", "gallery_agent_channels"),
       "community_agent"),
    _f("youtube.channel", "Channel rangkum YouTube", "channel",
       _baca_agent_channel("youtube_agent_channels"), _set_agent_channel(
           "set_youtube_channel_config", "Rangkum YouTube", "youtube_agent_channels"),
       "community_agent"),
    _f("cari.channel", "Channel pencarian berita", "channel",
       _baca_agent_channel("search_agent_channels"), _set_agent_channel(
           "set_search_channel_config", "Pencarian berita", "search_agent_channels"),
       "community_agent"),
    _f("terjemah.channel", "Channel terjemahan otomatis", "channel", _baca_terjemah,
       _set_terjemah, "translate_tools"),
    _f("statistik.aktif", "Statistik server (voice)", "saklar", _baca_serverstats,
       _set_serverstats, "server_features"),
    _f("fakta.channel", "Channel fakta harian", "channel", _baca_fakta, _set_fakta,
       "server_features"),
    _f("backup.channel", "Channel backup otomatis", "channel", _baca_backup, _set_backup,
       "community_tools"),
    # --- Agen AI ------------------------------------------------------------
    _f("agent.gaya", "Gaya bahasa Auto-Chat", "pilihan", _baca_agent("style_preset", "akrab"),
       _set_agent_gaya, "community_agent",
       opsi=(("akrab", "Akrab"), ("gaul", "Gaul"), ("ramah", "Ramah & sopan")),
       bantuan="Hanya untuk Auto-Chat AI; persona sambutan diatur terpisah."),
    _f("agent.keamanan", "Tingkat keamanan konten AI", "pilihan", _baca_agent("safety_level", "longgar"),
       _set_agent_keamanan, "community_agent",
       opsi=(("longgar", "Longgar"), ("normal", "Normal"), ("ketat", "Ketat"))),
    _f("agent.tenang", "Jam tenang (tanpa balasan malam)", "saklar", _baca_agent_saklar("quiet_hours"),
       _set_agent_saklar("quiet_hours", "Jam tenang"), "community_agent"),
    _f("agent.zona", "Zona waktu bot", "teks", _baca_agent("timezone", "Asia/Jakarta"),
       _set_agent_teks("timezone", "Zona waktu", validasi=_cek_zona), "community_agent",
       bantuan="Contoh: `Asia/Jakarta`, `Asia/Makassar`, `Asia/Jayapura`."),
]

FITUR: dict[str, dict] = {item["kunci"]: item for item in FITUR_LIST}

GRUP: tuple[dict, ...] = (
    {
        "kunci": "inti",
        "judul": "🧭 Inti, level, & ekonomi",
        "keterangan": "Sakelar fitur utama. Angka bawaan aman untuk server kecil.",
        "fitur": ("level.aktif", "level.pengumuman", "level.channel", "ekonomi.aktif",
                  "ekonomi.harian", "tumbuh.aktif", "tumbuh.channel", "prefix"),
    },
    {
        "kunci": "sambutan",
        "judul": "👋 Sambutan & pamit",
        "keterangan": "Pilih channel; pilih “— tidak dipakai —” untuk mematikan.",
        "fitur": ("sambutan.channel", "sambutan.dm", "sambutan.kartu", "sambutan.persona",
                  "pamit.channel", "boost.channel"),
    },
    {
        "kunci": "keamanan",
        "judul": "🛡️ Keamanan",
        "keterangan": "Mode “Lapor” hanya mencatat — paling aman untuk memulai.",
        "fitur": ("antispam.mode", "antispam.caps", "antispam.log", "antinuke.aksi",
                  "antinuke.log", "raid.aktif", "raid.aksi", "verifikasi.channel",
                  "verifikasi.role", "keamanan.aktif"),
    },
    {
        "kunci": "bantuan",
        "judul": "🎫 Tiket & sapaan harian",
        "keterangan": "Setelah menyalakan tiket, kirim panelnya lewat /tiket panel di Discord.",
        "fitur": ("tiket.aktif", "tiket.staff", "tiket.kategori", "tiket.log", "tiket.maks",
                  "tiket.ping", "tiket.rating", "ultah.channel"),
    },
    {
        "kunci": "konten",
        "judul": "🧩 Konten & interaksi",
        "keterangan": "Fitur AI per channel & utilitas server.",
        "fitur": ("starboard.channel", "starboard.ambang", "saran.channel", "chat.channel",
                  "digest.channel", "galeri.channel", "youtube.channel", "cari.channel",
                  "terjemah.channel", "statistik.aktif", "fakta.channel", "backup.channel",
                  "agent.gaya", "agent.keamanan", "agent.tenang", "agent.zona"),
    },
)

# Modul → fungsi simpan (dipanggil setelah perubahan berhasil).
_SIMPAN_MODUL = {
    "levels": ("levels", "save_levels_to_disk"),
    "economy": ("economy", "save_economy_to_disk"),
    "growth_tracker": ("growth_tracker", "save_growth_to_disk"),
    "prefixes": ("prefixes", "save_prefixes_to_disk"),
    "community_agent": ("community_agent", "save_agent_config_to_disk"),
    "antispam": ("antispam", "save_antispam_to_disk"),
    "antinuke": ("antinuke", "save_antinuke_to_disk"),
    "raid_guard": ("raid_guard", "save_raid_to_disk"),
    "community_tools": ("community_tools", "save_community_tools_to_disk"),
    "server_features": ("server_features", "save_server_features_to_disk"),
    "tickets": ("tickets", "save_tickets_to_disk"),
    "engagement": ("engagement", "save_engagement_to_disk"),
    "suggestions": ("suggestions", "save_suggestions_to_disk"),
    "translate_tools": ("translate_tools", "save_translate_to_disk"),
}


# ==============================================================================
# BACA & TULIS
# ==============================================================================
def read_values(guild_id: int) -> dict[str, str]:
    """Nilai semua fitur untuk satu server (aman bila modul belum siap)."""
    hasil: dict[str, str] = {}
    for kunci, fitur in FITUR.items():
        try:
            hasil[kunci] = str(fitur["nilai"](int(guild_id)))
        except Exception:  # pragma: no cover - jaring aman
            hasil[kunci] = ""
    return hasil


def normalisasi(kunci: str, nilai: str) -> str:
    """Rapikan masukan form (trim, huruf kecil untuk saklar/pilihan)."""
    teks = str(nilai or "").strip()
    fitur = FITUR.get(kunci) or {}
    if fitur.get("jenis") in ("saklar", "pilihan"):
        teks = teks.lower()
    if fitur.get("jenis") == "saklar":
        if teks in ("1", "true", "ya", "aktif", "on"):
            teks = "on"
        elif teks in ("0", "false", "tidak", "nonaktif", "off"):
            teks = "off"
    return teks


async def _simpan_modul(nama_modul: str) -> None:
    pasangan = _SIMPAN_MODUL.get(nama_modul)
    if not pasangan:
        return
    try:
        mod = _mod(pasangan[0])
        await getattr(mod, pasangan[1])()
    except Exception as exc:  # pragma: no cover - IO jarang gagal
        logger.warning("Gagal menyimpan modul %s: %s", nama_modul, exc)


async def apply(guild_id: int, kunci: str, nilai: str) -> tuple[bool, str]:
    """Jalankan satu perubahan setelan dari dashboard. `(berhasil, pesan)`."""
    gid = _to_int(guild_id)
    if gid <= 0:
        return False, "Server tidak dikenali."
    key = str(kunci or "").strip().lower()
    fitur = FITUR.get(key)
    if fitur is None:
        pesan = f"Setelan `{key or '-'}` tidak dikenal."
        await audit_append(gid, key, nilai, ok=False, pesan=pesan)
        return False, pesan
    if fitur["jenis"] == "pilihan" and fitur["opsi"]:
        pilihan = {v for v, _ in fitur["opsi"]}
        if nilai not in pilihan:
            pesan = f"Nilai `{nilai}` tidak termasuk pilihan yang tersedia."
            await audit_append(gid, key, nilai, ok=False, pesan=pesan)
            return False, pesan

    try:
        hasil = fitur["simpan"](gid, nilai)
        if asyncio.iscoroutine(hasil):
            hasil = await hasil
        ok, pesan = hasil
    except Exception as exc:
        logger.warning("Dashboard gagal menerapkan %s=%s: %s", key, nilai, exc)
        ok, pesan = False, f"Gagal menyimpan ({type(exc).__name__})."
    if ok:
        await _simpan_modul(fitur["modul"])
    await audit_append(gid, key, nilai, ok=ok, pesan=pesan)
    return ok, pesan


# ==============================================================================
# AUDIT
# ==============================================================================
def _muat_audit() -> list[dict]:
    global _audit_cache
    if _audit_cache is not None:
        return _audit_cache
    data: list[dict] = []
    try:
        if Path(AUDIT_FILE).exists():
            raw = json.loads(Path(AUDIT_FILE).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw = raw.get("items") or []
            for item in raw if isinstance(raw, list) else []:
                if isinstance(item, dict):
                    data.append(item)
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Audit dashboard tidak terbaca: %s", exc)
    _audit_cache = data[-MAX_AUDIT:]
    return _audit_cache


def reset_cache() -> None:
    """Kosongkan cache audit (dipakai tes & setelah impor backup)."""
    global _audit_cache
    _audit_cache = None


async def audit_append(guild_id: int, aksi: str, nilai: str, *, ok: bool, pesan: str) -> None:
    """Catat satu perubahan ke `data/dashboard_audit.json` (maks. `MAX_AUDIT`)."""
    item = {
        "waktu": time.strftime("%Y-%m-%d %H:%M:%S"),
        "guild": _to_int(guild_id),
        "aksi": str(aksi)[:64],
        "nilai": str(nilai)[:200],
        "ok": bool(ok),
        "pesan": str(pesan)[:300],
    }
    async with _audit_lock:
        data = _muat_audit()
        data.append(item)
        del data[:-MAX_AUDIT]
        try:
            Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
            sementara = Path(str(AUDIT_FILE) + ".tmp")
            sementara.write_text(
                json.dumps({"version": 1, "items": data}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            sementara.replace(Path(AUDIT_FILE))
        except Exception as exc:  # pragma: no cover - IO jarang gagal
            logger.warning("Gagal menyimpan audit dashboard: %s", exc)


def audit_terakhir(guild_id: int = 0, *, limit: int = 8) -> list[dict]:
    """Entri audit terbaru (terbaru lebih dulu), opsional per server."""
    data = _muat_audit()
    if guild_id:
        data = [item for item in data if _to_int(item.get("guild")) == _to_int(guild_id)]
    return list(reversed(data))[: max(1, int(limit))]


def ringkasan() -> dict:
    """Ringkasan untuk `/api/setelan`: jumlah fitur & grup."""
    return {
        "fitur": len(FITUR),
        "grup": [
            {"kunci": g["kunci"], "judul": g["judul"], "jumlah": len(g["fitur"])}
            for g in GRUP
        ],
    }


__all__ = [
    "FITUR",
    "FITUR_LIST",
    "GRUP",
    "SAKLAR_OPSI",
    "apply",
    "audit_append",
    "audit_terakhir",
    "normalisasi",
    "read_values",
    "reset_cache",
    "ringkasan",
]
