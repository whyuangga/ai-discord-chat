"""Formulir (modal) buatan Admin — ide dari *modal* & *flows* di Discohook.

`/agent panel` sudah memakai modal, tetapi bentuknya tetap (judul, isi, gambar,
footer). Modul ini membuat **modal bebas rancangan Admin**: sebutkan kolom yang
diinginkan, tempel ke tombol panel, lalu setiap anggota yang mengklik tombol
mendapat formulir rapi dan jawabannya dikirim ke channel tujuan.

Contoh::

    /menu form buat nama:"Lamaran Staff" field:"Nama | Umur | Alasan:panjang"
        tujuan:#lamaran hasil:"**Nama:** {form.nama}\\n**Umur:** {form.umur}"
    /menu form tombol form:"Lamaran Staff" menu:panel label:"📝 Daftar Staff"

Sintaks kolom (dipisah `|` atau baris baru):

| Tulis | Artinya |
| :--- | :--- |
| `Nama` | Kolom pendek, wajib diisi |
| `Nama?` | Kolom pendek, boleh dikosongkan |
| `Alasan:panjang` | Kolom paragraf (beberapa baris) |
| `Catatan:panjang?` | Paragraf, boleh kosong (urutan penanda bebas) |

Keamanan & batas:
- Hasil dikirim dengan *mention* dimatikan, jadi jawaban anggota tidak bisa
  dipakai men-*ping* `@everyone`.
- Maksimal **5 kolom** (batas Discord) dan **20 formulir** per server.
- Jawaban disimpan terhitung (`responses`) tapi **isi jawaban tidak disimpan** —
  bot hanya meneruskannya ke channel tujuan, tidak menyimpan data pribadi.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from pathlib import Path

import discord
from discord import ui

import message_template
from config import DATA_DIR, FORMS_FILE

logger = logging.getLogger("gemini_bot.modal_forms")

_lock = asyncio.Lock()

# ------------------------------------------------------------------------------
# BATAS & KONSTANTA
# ------------------------------------------------------------------------------
MAX_FIELDS = 5                 # batas Discord: 5 komponen dalam satu modal
MAX_FIELDS_WITH_INTRO = 4      # bila memakai kalimat pengantar (1 slot terpakai)
MAX_FORMS_PER_GUILD = 20
MAX_NAME = 80
MAX_MODAL_TITLE = 45           # batas Discord untuk judul modal
MAX_LABEL = 45                 # batas Discord untuk label kolom
MAX_PLACEHOLDER = 100
MAX_FIELD_LENGTH = 1000        # panjang jawaban yang diterima per kolom
MAX_RESULT_TEXT = 3800         # sisakan ruang untuk embed description (4096)
COOLDOWN_SEC = 10.0

# Antrean submission (kotak masuk dashboard)
MAKS_ANTREAN = 200             # submission tersimpan per server
ANTREAN_SIMPAN_HARI = 30       # entri lebih tua dibersihkan otomatis
MAKS_JAWABAN_SIMPAN = 1000     # panjang jawaban yang disimpan di antrean
STATUS_BARU = "baru"
STATUS_SELESAI = "selesai"

STYLE_SHORT = "pendek"
STYLE_LONG = "panjang"

WARNA_NAMA = {
    "ungu": 0x9B59B6,
    "biru": 0x3498DB,
    "merah": 0xE74C3C,
    "hijau": 0x2ECC71,
    "emas": 0xF1C40F,
    "abu": 0x95A5A6,
}

FORM_TOKEN_RE = re.compile(r"\{form\.([A-Za-z0-9_]+)\}")

# ------------------------------------------------------------------------------
# STATE
# ------------------------------------------------------------------------------
forms: dict[int, dict[str, dict]] = {}     # guild_id -> form_id -> form
_cooldown: dict[str, float] = {}           # "guild:form:user" -> timestamp
# guild_id -> {nomor: submission}  (antrean kotak masuk dashboard)
form_inbox: dict[int, dict[int, dict]] = {}
_inbox_seq: dict[int, int] = {}            # nomor terakhir per server


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _now() -> float:
    return time.time()


def new_form_id() -> str:
    return "f" + secrets.token_hex(4)


def parse_color(value: str | None) -> discord.Colour | None:
    """`#RRGGBB`, `RRGGBB`, atau nama warna dasar → `discord.Colour`."""
    teks = str(value or "").strip().lstrip("#").lower()
    if not teks:
        return None
    if teks in WARNA_NAMA:
        return discord.Colour(WARNA_NAMA[teks])
    if re.fullmatch(r"[0-9a-f]{6}", teks):
        return discord.Colour(int(teks, 16))
    return None


def max_fields(description: str | None) -> int:
    """Jumlah kolom yang muat: pengantar modal memakan satu slot."""
    return MAX_FIELDS_WITH_INTRO if str(description or "").strip() else MAX_FIELDS


def _slug(text: str, fallback: str) -> str:
    bersih = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return (bersih or fallback)[:24]


# ------------------------------------------------------------------------------
# CRUD FORMULIR
# ------------------------------------------------------------------------------
def get_form(guild_id: int, ref: str | None) -> dict | None:
    """Cari formulir lewat ID atau namanya (tidak peka huruf besar/kecil)."""
    bucket = forms.get(_to_int(guild_id)) or {}
    if not bucket:
        return None
    if ref:
        bersih = str(ref).strip()
        if bersih in bucket:
            return bucket[bersih]
        kecil = bersih.casefold()
        for form in bucket.values():
            if str(form.get("name", "")).casefold() == kecil:
                return form
    return None


def list_forms(guild_id: int) -> list[dict]:
    bucket = forms.get(_to_int(guild_id)) or {}
    return sorted(bucket.values(), key=lambda f: float(f.get("created_at") or 0))


def parse_fields(text: str) -> tuple[list[dict], list[str]]:
    """Ubah `Nama | Umur | Alasan:panjang?` menjadi daftar kolom. Kembalikan `(kolom, galat)`."""
    galat: list[str] = []
    mentah = [bagian for bagian in re.split(r"[|\n]", str(text or "")) if bagian.strip()]
    if not mentah:
        return [], ["Isi minimal satu kolom, mis. `Nama | Umur | Alasan:panjang`."]
    if len(mentah) > MAX_FIELDS:
        galat.append(f"Hanya {MAX_FIELDS} kolom pertama yang dipakai (batas Discord).")

    kolom: list[dict] = []
    dipakai: set[str] = set()
    for index, bagian in enumerate(mentah[:MAX_FIELDS], start=1):
        sisa = bagian.strip()
        style = STYLE_SHORT
        required = True
        # Penanda boleh berurutan bebas di ujung label
        while sisa:
            if sisa.endswith("?"):
                required = False
                sisa = sisa[:-1].strip()
                continue
            cocok = re.search(r":\s*(panjang|paragraf|long|pendek|singkat|short)\s*$", sisa, re.I)
            if cocok:
                style = (
                    STYLE_LONG
                    if cocok.group(1).lower() in ("panjang", "paragraf", "long")
                    else STYLE_SHORT
                )
                sisa = sisa[: cocok.start()].strip()
                continue
            break
        label = sisa[:MAX_LABEL]
        if not label:
            continue
        field_id = _slug(label, f"kolom{index}")
        dasar = field_id
        nomor = 2
        while field_id in dipakai:
            field_id = f"{dasar}_{nomor}"
            nomor += 1
        dipakai.add(field_id)
        kolom.append(
            {
                "id": field_id,
                "label": label,
                "style": style,
                "required": required,
                "max_length": 400 if style == STYLE_LONG else 200,
            }
        )
    if not kolom:
        galat.append("Semua kolom kosong setelah dibersihkan.")
    return kolom, galat


def create_form(
    guild_id: int,
    name: str,
    fields_text: str,
    *,
    title: str | None = None,
    description: str = "",
    result_text: str = "",
    channel_id: int | None = None,
    color: str | None = None,
) -> tuple[dict | None, list[str]]:
    """Buat formulir baru. Kembalikan `(form, galat)`; `form` = `None` bila gagal total."""
    gid = _to_int(guild_id)
    bucket = forms.setdefault(gid, {})
    bersih_nama = str(name or "").strip()[:MAX_NAME]
    if not bersih_nama:
        return None, ["Nama formulir tidak boleh kosong."]
    if len(bucket) >= MAX_FORMS_PER_GUILD:
        return None, [f"Kuota formulir server penuh (maksimal {MAX_FORMS_PER_GUILD})."]
    if get_form(gid, bersih_nama) is not None:
        return None, [f"Sudah ada formulir bernama “{bersih_nama}”."]

    kolom, galat = parse_fields(fields_text)
    if not kolom:
        return None, galat or ["Kolom formulir tidak valid."]
    if len(kolom) > max_fields(description):
        return None, [
            f"Penjelasan formulir memakai satu slot modal, jadi maksimal **{MAX_FIELDS_WITH_INTRO} kolom**. "
            "Hapus `deskripsi` atau kurangi kolomnya."
        ]

    form_id = new_form_id()
    while form_id in bucket:
        form_id = new_form_id()

    form = {
        "id": form_id,
        "guild_id": gid,
        "name": bersih_nama,
        "title": (str(title).strip()[:MAX_MODAL_TITLE] if title else bersih_nama[:MAX_MODAL_TITLE]),
        "description": str(description or "").strip()[:2000],
        "result_text": str(result_text or "").strip()[:MAX_RESULT_TEXT],
        "channel_id": _to_int(channel_id) or None,
        "color": (str(color).strip().lower()[:20] if color else None),
        "fields": kolom,
        "responses": 0,
        "created_at": _now(),
    }
    bucket[form_id] = form
    return form, galat


def update_form(form: dict, **changes) -> list[str]:
    """Ubah sebagian isi formulir (`name`, `title`, `description`, `result_text`,
    `channel_id`, `color`, `fields`)."""
    galat: list[str] = []
    if "name" in changes and changes["name"]:
        nama = str(changes["name"]).strip()[:MAX_NAME]
        lain = get_form(form.get("guild_id", 0), nama)
        if lain is not None and lain is not form:
            galat.append(f"Nama “{nama}” sudah dipakai formulir lain.")
        elif nama:
            form["name"] = nama
    if "title" in changes and changes["title"]:
        form["title"] = str(changes["title"]).strip()[:MAX_MODAL_TITLE]
    if "description" in changes and changes["description"] is not None:
        baru_deskripsi = str(changes["description"]).strip()[:2000]
        if len(form.get("fields") or []) > max_fields(baru_deskripsi):
            galat.append(
                f"Penjelasan formulir memakai satu slot modal — maksimal "
                f"**{MAX_FIELDS_WITH_INTRO} kolom**. Kurangi kolom dulu."
            )
        else:
            form["description"] = baru_deskripsi
    if "result_text" in changes and changes["result_text"] is not None:
        form["result_text"] = str(changes["result_text"]).strip()[:MAX_RESULT_TEXT]
    if "channel_id" in changes and changes["channel_id"]:
        form["channel_id"] = _to_int(changes["channel_id"]) or None
    if "color" in changes and changes["color"] is not None:
        form["color"] = (str(changes["color"]).strip().lower()[:20] or None)
    if "fields" in changes and changes["fields"]:
        kolom, pesan = parse_fields(str(changes["fields"]))
        galat.extend(pesan)
        if kolom and len(kolom) > max_fields(form.get("description")):
            galat.append(
                f"Formulir ini punya kalimat pengantar, jadi maksimal "
                f"**{MAX_FIELDS_WITH_INTRO} kolom**."
            )
        elif kolom:
            form["fields"] = kolom
    return galat


def delete_form(guild_id: int, form_id: str) -> bool:
    bucket = forms.get(_to_int(guild_id)) or {}
    return bucket.pop(str(form_id), None) is not None


def stats(guild_id: int) -> dict:
    bucket = forms.get(_to_int(guild_id)) or {}
    return {
        "total": len(bucket),
        "responses": sum(_to_int(f.get("responses")) for f in bucket.values()),
        "maks": MAX_FORMS_PER_GUILD,
    }


# ------------------------------------------------------------------------------
# RENDER HASIL
# ------------------------------------------------------------------------------
def format_answers(form: dict, values: dict[str, str]) -> str:
    """Teks hasil otomatis: satu blok per kolom (dipakai bila admin tidak mengisi `hasil`)."""
    baris: list[str] = []
    for kolom in form.get("fields", []):
        isi = str(values.get(kolom["id"]) or "").strip() or "—"
        baris.append(f"**{kolom.get('label')}**\n{isi}")
    return "\n\n".join(baris)[:MAX_RESULT_TEXT]


def render_result(form: dict, values: dict[str, str], *, member=None, guild=None, channel=None) -> str:
    """Isi template `hasil` — `{form.<kolom>}` dulu, baru variabel biasa."""
    teks = str(form.get("result_text") or "").strip()
    if not teks:
        return format_answers(form, values)

    def _sub(cocok: re.Match[str]) -> str:
        kunci = cocok.group(1)
        if kunci in values:
            return str(values[kunci])
        kecil = {k.lower(): v for k, v in values.items()}
        return str(kecil.get(kunci.lower(), "") or "")

    hasil = FORM_TOKEN_RE.sub(_sub, teks)
    hasil = message_template.render(hasil, member=member, guild=guild, channel=channel)
    return hasil[:MAX_RESULT_TEXT]


def result_embed(form: dict, values: dict[str, str], *, member=None, guild=None) -> discord.Embed:
    """Embed hasil yang dikirim ke channel tujuan."""
    judul = message_template.render(
        str(form.get("title") or form.get("name") or "Formulir"), member=member, guild=guild
    )
    embed = discord.Embed(
        title=f"📩 {judul[:240]}",
        description=render_result(form, values, member=member, guild=guild),
        colour=parse_color(form.get("color")) or discord.Colour(0x9B59B6),
    )
    nama = getattr(member, "display_name", None) or getattr(member, "name", None) or "Anggota"
    embed.set_footer(text=f"{form.get('name') or 'Formulir'} • dikirim oleh {nama}"[:2048])
    return embed


def preview_embed(form: dict, values: dict[str, str], *, member=None, guild=None) -> discord.Embed:
    """Pratinjau hasil (dipakai `/menu form uji`) — diberi tanda jelas."""
    embed = result_embed(form, values, member=member, guild=guild)
    embed.title = f"🔍 Pratinjau — {embed.title or ''}"[:256]
    embed.set_footer(text="Pratinjau saja: pesan ini tidak dikirim ke channel tujuan.")
    return embed


# ------------------------------------------------------------------------------
# MODAL
# ------------------------------------------------------------------------------
class FormModal(ui.Modal):
    """Modal berisi kolom buatan Admin; hasilnya diteruskan ke channel tujuan."""

    def __init__(self, form: dict, *, member=None, guild=None, uji: bool = False):
        super().__init__(title=str(form.get("title") or form.get("name") or "Formulir")[:MAX_MODAL_TITLE])
        self.form = form
        self.member = member
        self.guild = guild
        self.uji = uji
        self.inputs: dict[str, ui.TextInput] = {}

        # Modal V2: penjelasan (TextDisplay) + kolom yang dibungkus Label.
        if form.get("description"):
            self.add_item(ui.TextDisplay(str(form["description"])[:2000]))

        for kolom in (form.get("fields") or [])[: max_fields(form.get("description"))]:
            item = ui.TextInput(
                style=(
                    discord.TextStyle.paragraph
                    if kolom.get("style") == STYLE_LONG
                    else discord.TextStyle.short
                ),
                required=bool(kolom.get("required", True)),
                max_length=min(MAX_FIELD_LENGTH, _to_int(kolom.get("max_length"), 200) or 200),
            )
            self.add_item(
                ui.Label(text=str(kolom.get("label") or "Jawaban")[:MAX_LABEL], component=item)
            )
            self.inputs[str(kolom.get("id"))] = item

    def values(self) -> dict[str, str]:
        return {fid: str(getattr(item, "value", "") or "") for fid, item in self.inputs.items()}

    async def on_submit(self, interaction: discord.Interaction):
        await submit_form(interaction, self.form, self.values(), uji=self.uji)


def cooldown_left(guild_id: int, form_id: str, user_id: int) -> float:
    sisa = _cooldown.get(f"{_to_int(guild_id)}:{form_id}:{_to_int(user_id)}", 0.0) + COOLDOWN_SEC
    return max(0.0, sisa - _now())


def _mark_cooldown(guild_id: int, form_id: str, user_id: int) -> None:
    _cooldown[f"{_to_int(guild_id)}:{form_id}:{_to_int(user_id)}"] = _now()


# ------------------------------------------------------------------------------
# ANTREAN SUBMISSION (KOTAK MASUK DASHBOARD)
# ------------------------------------------------------------------------------
def _rapikan_nilai(values: dict | None, form: dict | None = None) -> dict[str, str]:
    """Jawaban modal memakai id kolom; di antrean kita tampilkan labelnya."""
    peta = {
        str(kolom.get("id") or ""): str(kolom.get("label") or "")
        for kolom in (form or {}).get("fields") or []
        if isinstance(kolom, dict)
    }
    hasil: dict[str, str] = {}
    for kunci, isi in list((values or {}).items())[:MAX_FIELDS]:
        mentah = str(kunci or "").strip()
        nama = (peta.get(mentah) or mentah).strip()[:MAX_LABEL] or "Jawaban"
        hasil[nama] = str(isi or "").strip()[:MAKS_JAWABAN_SIMPAN]
    return hasil


def catat_submission(
    guild_id: int,
    form: dict,
    *,
    user_id: int = 0,
    user_nama: str = "",
    values: dict | None = None,
    sekarang: float | None = None,
) -> dict:
    """Simpan satu jawaban formulir ke antrean dashboard. Mengembalikan entri barunya."""
    gid = _to_int(guild_id)
    if not gid:
        return {}
    kumpulan = form_inbox.setdefault(gid, {})
    nomor = int(_inbox_seq.get(gid, 0)) + 1
    _inbox_seq[gid] = nomor

    entri = {
        "nomor": nomor,
        "form_id": str(form.get("id") or ""),
        "form_nama": str(form.get("name") or "Formulir")[:MAX_NAME],
        "user_id": _to_int(user_id),
        "user_nama": str(user_nama or "")[:100],
        "dibuat": sekarang if sekarang is not None else _now(),
        "nilai": _rapikan_nilai(values, form),
        "status": STATUS_BARU,
        "oleh": 0,
        "pada": 0.0,
    }
    kumpulan[nomor] = entri

    # buang yang paling tua bila melebihi batas
    while len(kumpulan) > MAKS_ANTREAN:
        tertua = min(kumpulan, key=lambda n: kumpulan[n].get("dibuat", 0))
        kumpulan.pop(tertua, None)
    return entri


def daftar_submission(
    guild_id: int, *, status: str | None = None, limit: int = 50
) -> list[dict]:
    """Submission terbaru lebih dulu; `status` = "baru" / "selesai" (opsional)."""
    kumpulan = form_inbox.get(_to_int(guild_id)) or {}
    hasil = [dict(entri) for entri in kumpulan.values()]
    if status:
        hasil = [entri for entri in hasil if entri.get("status") == status]
    hasil.sort(key=lambda entri: entri.get("dibuat", 0), reverse=True)
    return hasil[: max(1, int(limit))]


def ambil_submission(guild_id: int, nomor: int) -> dict | None:
    return (form_inbox.get(_to_int(guild_id)) or {}).get(_to_int(nomor))


def tandai_submission(
    guild_id: int, nomor: int, *, selesai: bool = True, oleh: int = 0, sekarang: float | None = None
) -> bool:
    entri = (form_inbox.get(_to_int(guild_id)) or {}).get(_to_int(nomor))
    if entri is None:
        return False
    entri["status"] = STATUS_SELESAI if selesai else STATUS_BARU
    entri["oleh"] = _to_int(oleh) if selesai else 0
    entri["pada"] = (sekarang if sekarang is not None else _now()) if selesai else 0.0
    return True


def hapus_submission(guild_id: int, nomor: int) -> bool:
    kumpulan = form_inbox.get(_to_int(guild_id)) or {}
    return kumpulan.pop(_to_int(nomor), None) is not None


def statistik_inbox(guild_id: int) -> dict:
    kumpulan = form_inbox.get(_to_int(guild_id)) or {}
    baru = sum(1 for entri in kumpulan.values() if entri.get("status") == STATUS_BARU)
    return {
        "total": len(kumpulan),
        "baru": baru,
        "selesai": len(kumpulan) - baru,
        "terakhir": max((entri.get("dibuat", 0) for entri in kumpulan.values()), default=0),
        "maks": MAKS_ANTREAN,
    }


def cleanup_inbox_runtime(limit: int = 500, *, sekarang: float | None = None) -> int:
    """Buang submission yang lebih tua dari `ANTREAN_SIMPAN_HARI` (hemat disk)."""
    kini = sekarang if sekarang is not None else _now()
    batas = kini - ANTREAN_SIMPAN_HARI * 86400
    dibuang = 0
    for gid in list(form_inbox):
        kumpulan = form_inbox[gid]
        for nomor in list(kumpulan):
            if dibuang >= limit:
                break
            if float((kumpulan.get(nomor) or {}).get("dibuat") or 0) < batas:
                kumpulan.pop(nomor, None)
                dibuang += 1
        if not kumpulan:
            form_inbox.pop(gid, None)
    return dibuang


def reset_inbox_state() -> None:
    form_inbox.clear()
    _inbox_seq.clear()


def cleanup_runtime() -> int:
    """Bersihkan catatan cooldown yang sudah kedaluwarsa."""
    batas = _now() - COOLDOWN_SEC
    kedaluwarsa = [k for k, v in _cooldown.items() if v < batas]
    for key in kedaluwarsa:
        _cooldown.pop(key, None)
    return len(kedaluwarsa)


async def open_form_modal(
    interaction: discord.Interaction,
    form: dict | None,
    *,
    uji: bool = False,
) -> bool:
    """Kirim modal formulir ke pengklik tombol. `False` bila formulir sudah tidak ada."""
    if form is None:
        await interaction.response.send_message(
            "⚠️ Formulir tombol ini sudah dihapus Admin. Pakai `/menu form daftar` untuk melihat yang aktif.",
            ephemeral=True,
        )
        return False

    guild = getattr(interaction, "guild", None)
    member = getattr(interaction, "user", None)
    sisa = cooldown_left(getattr(guild, "id", 0), str(form.get("id")), getattr(member, "id", 0))
    if sisa > 0:
        await interaction.response.send_message(
            f"⏳ Tunggu **{sisa:.0f} detik** lagi sebelum mengisi formulir ini.",
            ephemeral=True,
        )
        return False

    modal = FormModal(form, member=member, guild=guild, uji=uji)
    await interaction.response.send_modal(modal)
    return True


async def _resolve_channel(bot, channel_id: int):
    getter = getattr(bot, "get_channel", None)
    channel = getter(_to_int(channel_id)) if callable(getter) else None
    if channel is not None:
        return channel
    fetcher = getattr(bot, "fetch_channel", None)
    if callable(fetcher):
        try:
            return await fetcher(_to_int(channel_id))
        except Exception:  # pragma: no cover - jaring aman (NotFound/Forbidden/HTTP)
            return None
    return None


async def submit_form(
    interaction: discord.Interaction,
    form: dict,
    values: dict[str, str],
    *,
    uji: bool = False,
) -> bool:
    """Kirim jawaban ke channel tujuan (atau tampilkan pratinjau bila `uji`)."""
    guild = getattr(interaction, "guild", None)
    member = getattr(interaction, "user", None)
    _mark_cooldown(getattr(guild, "id", 0), str(form.get("id")), getattr(member, "id", 0))

    if uji:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(
            embed=preview_embed(form, values, member=member, guild=guild), ephemeral=True
        )
        return True

    catat_submission(
        getattr(guild, "id", 0),
        form,
        user_id=getattr(member, "id", 0),
        user_nama=str(getattr(member, "display_name", "") or getattr(member, "name", "")),
        values=values,
    )
    await save_to_disk()  # jawaban langsung aman di disk, bukan hanya di memori

    channel = None
    if form.get("channel_id"):
        channel = await _resolve_channel(interaction.client, form["channel_id"])
    if channel is None:
        await interaction.response.send_message(
            "⚠️ Channel tujuan formulir tidak ditemukan (mungkin dihapus). "
            "Minta Admin memperbaikinya lewat `/menu form ubah`.",
            ephemeral=True,
        )
        return False

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await channel.send(
            embed=result_embed(form, values, member=member, guild=guild),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Formulir %s gagal dikirim: %s", form.get("id"), exc)
        await interaction.followup.send(
            "⚠️ Hasil formulir gagal dikirim (bot tidak punya izin di channel tujuan). "
            "Coba lagi atau hubungi Admin.",
            ephemeral=True,
        )
        return False

    form["responses"] = _to_int(form.get("responses")) + 1
    await save_to_disk()
    await interaction.followup.send(
        f"✅ Terima kasih, **{getattr(member, 'display_name', 'kamu')}**! "
        f"Jawabanmu sudah dikirim ke {getattr(channel, 'mention', 'channel tujuan')}.",
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return True


# ------------------------------------------------------------------------------
# SIMPAN / MUAT
# ------------------------------------------------------------------------------
def _form_payload(form: dict) -> dict:
    return {
        "id": form.get("id"),
        "name": form.get("name"),
        "title": form.get("title"),
        "description": form.get("description"),
        "result_text": form.get("result_text"),
        "channel_id": form.get("channel_id"),
        "color": form.get("color"),
        "fields": form.get("fields", []),
        "responses": form.get("responses", 0),
        "created_at": form.get("created_at"),
    }


def _sanitize_fields(fields) -> list[dict]:
    """Kolom dari disk: bangun ulang dengan batas aman (jangan percaya JSON)."""
    hasil: list[dict] = []
    dipakai: set[str] = set()
    for index, kolom in enumerate(fields or [], start=1):
        if not isinstance(kolom, dict) or len(hasil) >= MAX_FIELDS:
            continue
        label = str(kolom.get("label") or "").strip()[:MAX_LABEL]
        if not label:
            continue
        field_id = _slug(str(kolom.get("id") or label), f"kolom{index}")
        dasar = field_id
        nomor = 2
        while field_id in dipakai:
            field_id = f"{dasar}_{nomor}"
            nomor += 1
        dipakai.add(field_id)
        style = STYLE_LONG if kolom.get("style") == STYLE_LONG else STYLE_SHORT
        hasil.append(
            {
                "id": field_id,
                "label": label,
                "style": style,
                "required": bool(kolom.get("required", True)),
                "max_length": min(
                    MAX_FIELD_LENGTH,
                    _to_int(kolom.get("max_length"), 400 if style == STYLE_LONG else 200) or 200,
                ),
            }
        )
    return hasil


def load_from_disk() -> int:
    """Muat formulir dari `data/forms.json`. Kembalikan jumlah formulir terbaca."""
    forms.clear()
    _cooldown.clear()

    path = Path(FORMS_FILE)
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - berkas rusak
        logger.warning("Gagal memuat %s: %s", path, exc)
        return 0

    reset_inbox_state()
    for gid_str, kumpulan in (raw.get("inbox") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(kumpulan, dict):
            continue
        for nomor_str, entri in kumpulan.items():
            if not isinstance(entri, dict):
                continue
            nomor = _to_int(nomor_str)
            if not nomor:
                continue
            form_inbox.setdefault(gid, {})[nomor] = {
                "nomor": nomor,
                "form_id": str(entri.get("form_id") or ""),
                "form_nama": str(entri.get("form_nama") or "Formulir")[:MAX_NAME],
                "user_id": _to_int(entri.get("user_id")),
                "user_nama": str(entri.get("user_nama") or "")[:100],
                "dibuat": float(entri.get("dibuat") or 0),
                "nilai": _rapikan_nilai(entri.get("nilai")),
                "status": STATUS_SELESAI if entri.get("status") == STATUS_SELESAI else STATUS_BARU,
                "oleh": _to_int(entri.get("oleh")),
                "pada": float(entri.get("pada") or 0),
            }
            _inbox_seq[gid] = max(int(_inbox_seq.get(gid, 0)), nomor)

    total = 0
    for gid_str, bucket in (raw.get("guilds") or {}).items():
        gid = _to_int(gid_str)
        if not gid or not isinstance(bucket, dict):
            continue
        for form_id, data in bucket.items():
            if not isinstance(data, dict):
                continue
            kolom = _sanitize_fields(data.get("fields"))
            if not kolom:
                continue  # formulir tanpa kolom tidak bisa dipakai
            forms.setdefault(gid, {})[str(form_id)] = {
                "id": str(data.get("id") or form_id),
                "guild_id": gid,
                "name": str(data.get("name") or "Formulir")[:MAX_NAME],
                "title": str(data.get("title") or data.get("name") or "Formulir")[:MAX_MODAL_TITLE],
                "description": str(data.get("description") or "")[:2000],
                "result_text": str(data.get("result_text") or "")[:MAX_RESULT_TEXT],
                "channel_id": _to_int(data.get("channel_id")) or None,
                "color": (str(data.get("color"))[:20] if data.get("color") else None),
                "fields": kolom,
                "responses": _to_int(data.get("responses")),
                "created_at": float(data.get("created_at") or 0),
            }
            total += 1
    return total


async def save_to_disk() -> None:
    """Simpan seluruh formulir ke `data/forms.json` (atomik)."""
    async with _lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            isi = {
                "version": 1,
                "guilds": {
                    str(gid): {fid: _form_payload(form) for fid, form in bucket.items()}
                    for gid, bucket in forms.items()
                },
                "inbox": {
                    str(gid): {str(nomor): entri for nomor, entri in kumpulan.items()}
                    for gid, kumpulan in form_inbox.items()
                    if kumpulan
                },
            }
            sementara = Path(str(FORMS_FILE) + ".tmp")
            sementara.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding="utf-8")
            sementara.replace(Path(FORMS_FILE))
        except Exception:  # pragma: no cover - IO jarang gagal
            logger.exception("Gagal menyimpan %s")


__all__ = [
    "FormModal",
    "MAX_FIELDS",
    "MAX_FORMS_PER_GUILD",
    "cleanup_runtime",
    "cooldown_left",
    "create_form",
    "delete_form",
    "format_answers",
    "forms",
    "get_form",
    "list_forms",
    "load_from_disk",
    "new_form_id",
    "open_form_modal",
    "parse_color",
    "parse_fields",
    "preview_embed",
    "render_result",
    "result_embed",
    "save_to_disk",
    "stats",
    "submit_form",
    "update_form",
]
