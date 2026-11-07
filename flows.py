r"""Alur aksi tombol (*flows*) — satu tombol bisa menjalankan beberapa aksi berurutan.

Ide ini dipinjam dari **Discohook** (`flows`): tombol tidak hanya memberi role, tapi juga
bisa mengirim pesan, membuat thread, menunggu, dan berhenti bila syarat tidak terpenuhi —
semua tanpa AI dan tanpa dependency baru.

Sintaks ringkas (dipakai `/menu alur`), langkah dipisah `>`:

    +role:123456789 > pesan:Halo {member.mention}, tiketmu siap! > thread:tiket-{member.name}

| Langkah | Arti |
| :--- | :--- |
| `role:<id>` | Toggle role (dapat bila belum punya, lepas bila sudah) |
| `+role:<id>` | Tambah role |
| `-role:<id>` | Lepas role |
| `syarat:<id>` | Berhenti diam-diam bila member **tidak** punya role tersebut |
| `pesan:<teks>` | Kirim pesan **hanya untuk pengklik** (*ephemeral*) |
| `umum:<teks>` | Kirim pesan yang terlihat semua orang di channel |
| `thread:<nama>` | Buat thread publik di channel panel |
| `tunggu:<detik>` | Jeda (maksimal 15 detik) |
| `stop[:<teks>]` | Hentikan alur, opsional kirim alasan |
| `webhook:<nama>\|<teks>` | Kirim pesan sebagai **nama sendiri** (identitas webhook) |
| `hapus` | Hapus pesan balasan bot yang sudah terkirim di alur ini |

Teks boleh memakai variabel dari :mod:`message_template` (`{member.mention}`,
`{server.name}`, …). Batas: 10 langkah per alur, 1000 karakter teks per pesan.

Modul ini dipisah dari :mod:`menu_builder` supaya bisa diuji tanpa Discord:
:func:`parse` dan :func:`describe` murni, sedangkan :func:`run_flow` memakai objek
`Interaction` (bisa diganti tiruan saat tes).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

import message_template

logger = logging.getLogger("gemini_bot.flows")

MAX_STEPS = 10
MAX_TEXT = 1000
MAX_THREAD_NAME = 90
MAX_WAIT_SECONDS = 15.0
SEPARATOR = ">"

ACTION_ROLE_TOGGLE = "role_toggle"
ACTION_ROLE_ADD = "role_add"
ACTION_ROLE_REMOVE = "role_remove"
ACTION_SAY = "say"
ACTION_THREAD = "thread"
ACTION_WAIT = "wait"
ACTION_STOP = "stop"
ACTION_REQUIRE_ROLE = "require_role"
ACTION_WEBHOOK = "webhook"
ACTION_DELETE = "delete"

VALID_ACTIONS = frozenset(
    {
        ACTION_ROLE_TOGGLE,
        ACTION_ROLE_ADD,
        ACTION_ROLE_REMOVE,
        ACTION_SAY,
        ACTION_THREAD,
        ACTION_WAIT,
        ACTION_STOP,
        ACTION_REQUIRE_ROLE,
        ACTION_WEBHOOK,
        ACTION_DELETE,
    }
)

_PREFIX = {
    "role": ACTION_ROLE_TOGGLE,
    "+role": ACTION_ROLE_ADD,
    "-role": ACTION_ROLE_REMOVE,
    "syarat": ACTION_REQUIRE_ROLE,
    "pesan": ACTION_SAY,
    "umum": ACTION_SAY,
    "thread": ACTION_THREAD,
    "tunggu": ACTION_WAIT,
    "stop": ACTION_STOP,
    "webhook": ACTION_WEBHOOK,
    "hapus": ACTION_DELETE,
}

HELP_LINES: tuple[str, ...] = (
    "`role:<id>` — toggle role (dapat/lepas)",
    "`+role:<id>` / `-role:<id>` — tambah / lepas role",
    "`syarat:<id>` — berhenti bila member tidak punya role itu",
    "`pesan:<teks>` — balasan pribadi (ephemeral)",
    "`umum:<teks>` — balasan terlihat semua orang",
    "`thread:<nama>` — buat thread publik di channel panel",
    "`tunggu:<detik>` — jeda, maksimal 15 detik",
    "`stop[:<teks>]` — hentikan alur (opsional kirim alasan)",
    "`webhook:<nama>|<teks>` — kirim pesan sebagai nama sendiri",
    "`hapus` — hapus balasan bot yang sudah dikirim alur ini",
)


# ------------------------------------------------------------------------------
# PARSER (murni)
# ------------------------------------------------------------------------------
def split_steps(text: str) -> list[str]:
    """Memisah langkah pada `>`, menghormati `\\>` sebagai karakter biasa."""
    if not text:
        return []
    hasil: list[str] = []
    buffer: list[str] = []
    i = 0
    raw = str(text)
    while i < len(raw):
        char = raw[i]
        if char == "\\" and i + 1 < len(raw) and raw[i + 1] == SEPARATOR:
            buffer.append(SEPARATOR)
            i += 2
            continue
        if char == SEPARATOR:
            hasil.append("".join(buffer))
            buffer = []
            i += 1
            continue
        buffer.append(char)
        i += 1
    hasil.append("".join(buffer))
    return hasil


def _role_id(value: str) -> int:
    bersih = value.strip().strip("<@&>")
    return int(bersih) if bersih.isdigit() else 0


def parse(text: str) -> tuple[list[dict], list[str]]:
    """Ubah teks alur menjadi daftar langkah. Kembalikan `(langkah, galat)`."""
    langkah: list[dict] = []
    galat: list[str] = []

    mentah = [bagian.strip() for bagian in split_steps(text)]
    mentah = [bagian for bagian in mentah if bagian]
    if not mentah:
        return [], ["Alur masih kosong. Contoh: `+role:123 > pesan:Halo {member.mention}`"]
    if len(mentah) > MAX_STEPS:
        return [], [f"Terlalu banyak langkah ({len(mentah)}), maksimal {MAX_STEPS}."]

    for posisi, bagian in enumerate(mentah, start=1):
        nama, _, argumen = bagian.partition(":")
        nama = nama.strip().lower()
        argumen = argumen.strip()
        aksi = _PREFIX.get(nama)
        if aksi is None:
            galat.append(f"Langkah {posisi}: `{nama}` tidak dikenal — cek `/menu alur-bantuan`.")
            continue

        if aksi in (ACTION_ROLE_TOGGLE, ACTION_ROLE_ADD, ACTION_ROLE_REMOVE, ACTION_REQUIRE_ROLE):
            role_id = _role_id(argumen)
            if not role_id:
                galat.append(f"Langkah {posisi}: `{nama}` butuh ID role angka, mis. `{nama}:123456789`.")
                continue
            langkah.append({"action": aksi, "role_id": role_id})
            continue

        if aksi == ACTION_SAY:
            if not argumen:
                galat.append(f"Langkah {posisi}: `{nama}` butuh teks pesan.")
                continue
            langkah.append(
                {
                    "action": ACTION_SAY,
                    "text": argumen[:MAX_TEXT],
                    "ephemeral": nama == "pesan",
                }
            )
            continue

        if aksi == ACTION_THREAD:
            if not argumen:
                galat.append(f"Langkah {posisi}: `thread` butuh nama thread.")
                continue
            langkah.append({"action": ACTION_THREAD, "name": argumen[:MAX_THREAD_NAME]})
            continue

        if aksi == ACTION_WAIT:
            try:
                detik = float(argumen.replace(",", "."))
            except ValueError:
                galat.append(f"Langkah {posisi}: `tunggu` butuh angka detik, mis. `tunggu:3`.")
                continue
            if detik <= 0 or detik > MAX_WAIT_SECONDS:
                galat.append(f"Langkah {posisi}: `tunggu` harus antara 1–{int(MAX_WAIT_SECONDS)} detik.")
                continue
            langkah.append({"action": ACTION_WAIT, "seconds": round(detik, 2)})
            continue

        if aksi == ACTION_STOP:
            langkah.append({"action": ACTION_STOP, "text": argumen[:MAX_TEXT]})
            continue

        if aksi == ACTION_WEBHOOK:
            identitas, _, teks = argumen.partition("|")
            identitas = identitas.strip()[:80]
            teks = teks.strip()
            if not identitas or not teks:
                galat.append(
                    f"Langkah {posisi}: `webhook` butuh format `webhook:<nama>|<teks>`."
                )
                continue
            langkah.append(
                {"action": ACTION_WEBHOOK, "name": identitas, "text": teks[:MAX_TEXT]}
            )
            continue

        if aksi == ACTION_DELETE:
            langkah.append({"action": ACTION_DELETE})
            continue

    return langkah, galat


def sanitize_steps(steps: Any) -> list[dict]:
    """Validasi langkah yang dimuat dari disk (jangan percaya berkas JSON)."""
    if not isinstance(steps, list):
        return []
    bersih: list[dict] = []
    for step in steps[:MAX_STEPS]:
        if not isinstance(step, dict):
            continue
        aksi = str(step.get("action") or "")
        if aksi not in VALID_ACTIONS:
            continue
        if aksi in (ACTION_ROLE_TOGGLE, ACTION_ROLE_ADD, ACTION_ROLE_REMOVE, ACTION_REQUIRE_ROLE):
            role_id = int(step.get("role_id") or 0)
            if role_id <= 0:
                continue
            bersih.append({"action": aksi, "role_id": role_id})
        elif aksi == ACTION_SAY:
            teks = str(step.get("text") or "")[:MAX_TEXT]
            if not teks:
                continue
            bersih.append({"action": aksi, "text": teks, "ephemeral": bool(step.get("ephemeral", True))})
        elif aksi == ACTION_THREAD:
            nama = str(step.get("name") or "")[:MAX_THREAD_NAME]
            if not nama:
                continue
            bersih.append({"action": aksi, "name": nama})
        elif aksi == ACTION_WAIT:
            try:
                detik = float(step.get("seconds") or 0)
            except (TypeError, ValueError):
                continue
            if not 0 < detik <= MAX_WAIT_SECONDS:
                continue
            bersih.append({"action": aksi, "seconds": round(detik, 2)})
        elif aksi == ACTION_STOP:
            bersih.append({"action": aksi, "text": str(step.get("text") or "")[:MAX_TEXT]})
        elif aksi == ACTION_WEBHOOK:
            nama = str(step.get("name") or "")[:80].strip()
            teks = str(step.get("text") or "")[:MAX_TEXT].strip()
            if not nama or not teks:
                continue
            bersih.append({"action": aksi, "name": nama, "text": teks})
        elif aksi == ACTION_DELETE:
            bersih.append({"action": aksi})
    return bersih


def to_text(steps: list[dict]) -> str:
    """Kebalikan :func:`parse` — untuk menampilkan alur yang tersimpan."""
    bagian: list[str] = []
    for step in steps:
        aksi = step.get("action")
        if aksi == ACTION_ROLE_TOGGLE:
            bagian.append(f"role:{step.get('role_id')}")
        elif aksi == ACTION_ROLE_ADD:
            bagian.append(f"+role:{step.get('role_id')}")
        elif aksi == ACTION_ROLE_REMOVE:
            bagian.append(f"-role:{step.get('role_id')}")
        elif aksi == ACTION_REQUIRE_ROLE:
            bagian.append(f"syarat:{step.get('role_id')}")
        elif aksi == ACTION_SAY:
            nama = "pesan" if step.get("ephemeral", True) else "umum"
            bagian.append(f"{nama}:{step.get('text')}")
        elif aksi == ACTION_THREAD:
            bagian.append(f"thread:{step.get('name')}")
        elif aksi == ACTION_WAIT:
            bagian.append(f"tunggu:{step.get('seconds')}")
        elif aksi == ACTION_STOP:
            teks = step.get("text")
            bagian.append(f"stop:{teks}" if teks else "stop")
        elif aksi == ACTION_WEBHOOK:
            bagian.append(f"webhook:{step.get('name')}|{step.get('text')}")
        elif aksi == ACTION_DELETE:
            bagian.append("hapus")
    return " > ".join(bagian)


def describe(steps: list[dict], role_names: dict[int, str] | None = None) -> list[str]:
    """Ringkasan ramah untuk `/menu daftar`."""
    names = role_names or {}
    baris: list[str] = []
    for step in steps:
        aksi = step.get("action")
        if aksi == ACTION_ROLE_TOGGLE:
            baris.append(f"🔁 toggle @{names.get(step['role_id'], step['role_id'])}")
        elif aksi == ACTION_ROLE_ADD:
            baris.append(f"➕ beri @{names.get(step['role_id'], step['role_id'])}")
        elif aksi == ACTION_ROLE_REMOVE:
            baris.append(f"➖ lepas @{names.get(step['role_id'], step['role_id'])}")
        elif aksi == ACTION_REQUIRE_ROLE:
            baris.append(f"❓ hanya untuk @{names.get(step['role_id'], step['role_id'])}")
        elif aksi == ACTION_SAY:
            mata = "🔒" if step.get("ephemeral", True) else "📣"
            baris.append(f"{mata} {str(step.get('text'))[:60]}")
        elif aksi == ACTION_THREAD:
            baris.append(f"🧵 thread “{step.get('name')}”")
        elif aksi == ACTION_WAIT:
            baris.append(f"⏳ tunggu {step.get('seconds')} dtk")
        elif aksi == ACTION_STOP:
            suffix = f": {str(step.get('text'))[:40]}" if step.get("text") else ""
            baris.append(f"⏹ stop{suffix}")
        elif aksi == ACTION_WEBHOOK:
            baris.append(f"🎭 kirim sebagai “{step.get('name')}”: {str(step.get('text'))[:40]}")
        elif aksi == ACTION_DELETE:
            baris.append("🗑️ hapus balasan bot")
    return baris or ["(alur kosong)"]


# ------------------------------------------------------------------------------
# PENJALAN (butuh objek Interaction)
# ------------------------------------------------------------------------------
class FlowResult(dict):
    """Ringkasan hasil penjalanan — mudah diperiksa di tes."""

    @property
    def sent(self) -> int:
        return int(self.get("sent", 0))

    @property
    def stopped(self) -> bool:
        return bool(self.get("stopped"))


async def _kirim(interaction, teks: str, *, ephemeral: bool, sudah_balas: bool) -> bool:
    """Kirim balasan pertama lewat `response`, sisanya lewat `followup`."""
    try:
        if not sudah_balas and not interaction.response.is_done():
            await interaction.response.send_message(teks[:2000], ephemeral=ephemeral)
        else:
            await interaction.followup.send(teks[:2000], ephemeral=ephemeral)
        return True
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.debug("Alur gagal mengirim pesan: %s", exc)
        return False


async def _aksi_ubah_role(
    interaction, guild, member, aksi: str, step: dict, hasil: dict, sudah_balas: bool
) -> bool:
    """Tambah/hapus/toggle role sesuai langkah; kembalikan `sudah_balas`."""
    if guild is None or member is None:
        hasil["errors"].append("tanpa konteks server")
        return sudah_balas
    role_id = step["role_id"]
    role = guild.get_role(role_id)
    if role is None:
        hasil["errors"].append(f"role {role_id} tidak ada")
        return sudah_balas
    import menu_builder  # impor lambat: menu_builder juga memakai modul ini

    boleh, alasan = menu_builder.check_role_usable(guild, role_id)
    if not boleh:
        await _kirim(interaction, f"⚠️ {alasan}", ephemeral=True, sudah_balas=sudah_balas)
        sudah_balas = True
        hasil["errors"].append(f"role {role_id} ditolak")
        return sudah_balas

    punya = role in getattr(member, "roles", [])
    try:
        if aksi == ACTION_ROLE_TOGGLE and punya:
            await member.remove_roles(role, reason="Alur menu")
        elif aksi == ACTION_ROLE_TOGGLE:
            await member.add_roles(role, reason="Alur menu")
        elif aksi == ACTION_ROLE_ADD and not punya:
            await member.add_roles(role, reason="Alur menu")
        elif aksi == ACTION_ROLE_REMOVE and punya:
            await member.remove_roles(role, reason="Alur menu")
        else:
            return sudah_balas
    except Exception as exc:
        hasil["errors"].append(f"gagal ubah role {role_id}: {type(exc).__name__}")
        return sudah_balas
    hasil["roles"].append(role_id)
    return sudah_balas


async def _aksi_thread(
    channel, step: dict, hasil: dict, konteks: dict
) -> None:
    """Buat thread diskusi publik untuk langkah `thread`."""
    nama = message_template.render(str(step.get("name") or ""), **konteks)[:MAX_THREAD_NAME]
    if channel is None or not hasattr(channel, "create_thread"):
        hasil["errors"].append("channel tidak mendukung thread")
        return
    try:
        thread = await channel.create_thread(
            name=(nama or "diskusi")[:MAX_THREAD_NAME],
            type=discord.ChannelType.public_thread,
            auto_archive_duration=1440,
            reason="Alur menu",
        )
    except Exception as exc:
        hasil["errors"].append(f"gagal buat thread: {type(exc).__name__}")
        return
    hasil["threads"].append(getattr(thread, "id", 0))
    return


async def _aksi_webhook(
    channel, step: dict, hasil: dict, konteks: dict
) -> None:
    """Kirim pesan lewat webhook server untuk langkah `webhook`."""
    import webhook_identity  # impor lambat: modul ini memakai data & izin channel

    nama = message_template.render(str(step.get("name") or ""), **konteks)[:80]
    teks = message_template.render(str(step.get("text") or ""), **konteks)
    if not teks.strip() or channel is None:
        hasil["errors"].append("webhook butuh channel teks")
        return
    ok, keterangan = await webhook_identity.kirim_sebagai(
        channel, nama=nama or "Server", isi=teks
    )
    if not ok:
        hasil["errors"].append(f"webhook ditolak: {keterangan}")
        hasil["sent"] += 0
        return
    hasil["sent"] += 1
    return


async def run_flow(interaction, steps: list[dict], *, guild=None, member=None, channel=None) -> FlowResult:
    """Jalankan langkah alur atas nama member yang mengklik tombol."""
    langkah = sanitize_steps(steps)
    hasil = FlowResult(sent=0, roles=[], threads=[], stopped=False, errors=[])
    guild = guild if guild is not None else getattr(interaction, "guild", None)
    member = member if member is not None else getattr(interaction, "user", None)
    channel = channel if channel is not None else getattr(interaction, "channel", None)

    if not langkah:
        hasil["errors"].append("alur kosong")
        return hasil

    butuh_defer = any(step["action"] in (ACTION_WAIT, ACTION_THREAD) for step in langkah)
    if butuh_defer and not interaction.response.is_done():
        try:
            await interaction.response.defer(ephemeral=False, thinking=True)
        except Exception as exc:  # pragma: no cover
            logger.debug("Defer alur dilewati: %s", exc)

    sudah_balas = bool(interaction.response.is_done())
    konteks = {"guild": guild, "member": member, "channel": channel}

    for step in langkah:
        aksi = step["action"]

        if aksi == ACTION_REQUIRE_ROLE:
            role = guild.get_role(step["role_id"]) if guild is not None else None
            punya = role is not None and role in getattr(member, "roles", [])
            if role is None or not punya:
                hasil["stopped"] = True
                return hasil
            continue

        if aksi in (ACTION_ROLE_TOGGLE, ACTION_ROLE_ADD, ACTION_ROLE_REMOVE):
            sudah_balas = await _aksi_ubah_role(
                interaction, guild, member, aksi, step, hasil, sudah_balas
            )
            continue

        if aksi == ACTION_SAY:
            teks = message_template.render(str(step.get("text") or ""), **konteks)
            if not teks.strip():
                continue
            await _kirim(
                interaction,
                teks,
                ephemeral=bool(step.get("ephemeral", True)),
                sudah_balas=sudah_balas,
            )
            sudah_balas = True
            hasil["sent"] += 1
            continue

        if aksi == ACTION_THREAD:
            await _aksi_thread(channel, step, hasil, konteks)
            continue

        if aksi == ACTION_WAIT:
            await asyncio.sleep(float(step.get("seconds") or 0))
            continue

        if aksi == ACTION_WEBHOOK:
            await _aksi_webhook(channel, step, hasil, konteks)
            continue

        if aksi == ACTION_DELETE:
            try:
                pesan = await interaction.original_response()
                await pesan.delete()
            except Exception as exc:  # pragma: no cover - pesan sudah hilang
                logger.debug("Alur gagal menghapus balasan: %s", exc)
                hasil["errors"].append("balasan tidak bisa dihapus")
            continue

        if aksi == ACTION_STOP:
            teks = message_template.render(str(step.get("text") or ""), **konteks)
            if teks.strip():
                await _kirim(interaction, teks, ephemeral=True, sudah_balas=sudah_balas)
                sudah_balas = True
                hasil["sent"] += 1
            hasil["stopped"] = True
            return hasil

    return hasil


__all__ = [
    "ACTION_ROLE_ADD",
    "ACTION_ROLE_REMOVE",
    "ACTION_ROLE_TOGGLE",
    "ACTION_REQUIRE_ROLE",
    "ACTION_DELETE",
    "ACTION_SAY",
    "ACTION_STOP",
    "ACTION_WEBHOOK",
    "ACTION_THREAD",
    "ACTION_WAIT",
    "FlowResult",
    "HELP_LINES",
    "MAX_STEPS",
    "describe",
    "parse",
    "run_flow",
    "sanitize_steps",
    "split_steps",
    "to_text",
]
