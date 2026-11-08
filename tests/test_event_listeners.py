"""Jaring regresi event listener Discord.

**Mengapa berkas ini ada.** Refactor besar (PR #20) mengubah 20 listener di
`cogs/events_cog.py` dari *closure* di dalam `register_events_cog(bot)`
(menangkap `bot` dari lingkup luar) menjadi fungsi tingkat modul berparameter
`(bot, ...)`. Gagal total di produksi:

    TypeError: on_ready() missing 1 required positional argument: 'bot'

Sebabnya: `bot.add_listener` menyimpan fungsi apa adanya ke `extra_events`,
dan `commands.Bot.dispatch` meneruskannya ke `Client._run_event` yang
menjalankan `await coro(*args, **kwargs)` — objek bot **tidak pernah**
disisipkan otomatis.

Tes di `test_bot.py` tidak menangkapnya karena memanggil handler secara manual
dengan `(bot, guild)`, yaitu mencocokkan konvensi yang salah sehingga justru
menyetujui bug-nya.

Berkas ini memakai `commands.Bot` **asli** discord.py dan memicu lewat jalur
`dispatch` yang sebenarnya, jadi kesalahan pengikatan argumen akan langsung
terlihat tanpa perlu menyalakan bot ke gateway.
"""

from __future__ import annotations

import asyncio
import inspect

import discord
import pytest
from discord.ext import commands

import cogs.events_cog as berita


# Jumlah argumen yang BENAR-BENAR dikirim discord.py untuk tiap event (objek
# `bot` TIDAK termasuk). Diambil dari dokumentasi event discord.py 2.7.
ARGUMEN_EVENT: dict[str, int] = {
    "on_ready": 0,
    "on_raw_thread_delete": 1,
    "on_guild_role_create": 1,
    "on_guild_role_delete": 1,
    "on_guild_channel_create": 1,
    "on_guild_channel_delete": 1,
    "on_raw_reaction_add": 1,
    "on_raw_reaction_remove": 1,
    "on_message_delete": 1,
    "on_bulk_message_delete": 1,
    "on_message_edit": 2,
    "on_audit_log_entry_create": 1,
    "on_guild_join": 1,
    "on_invite_create": 1,
    "on_invite_delete": 1,
    "on_member_join": 1,
    "on_member_update": 2,
    "on_voice_state_update": 3,
    "on_member_remove": 1,
    "on_message": 1,
}


def _bot_baru() -> commands.Bot:
    """`commands.Bot` asli dengan intent kosong (tanpa koneksi apa pun)."""
    return commands.Bot(command_prefix="!", intents=discord.Intents.none())


def test_semua_listener_terdaftar():
    """register_events_cog memasang seluruh 20 listener, tidak kurang."""
    bot = _bot_baru()
    berita.register_events_cog(bot)

    terdaftar = set(bot.extra_events)
    diharapkan = set(ARGUMEN_EVENT)
    assert terdaftar == diharapkan, (
        f"listener hilang: {sorted(diharapkan - terdaftar)}; "
        f"tak terduga: {sorted(terdaftar - diharapkan)}"
    )


def test_listener_bisa_dipanggil_tanpa_bot_eksplisit():
    """Inti regresi: listener harus menerima argumen EVENT saja.

    discord.py memanggil `coro(*args)` tanpa menyisipkan bot. Jika ada listener
    yang mewajibkan `bot` dari pemanggil, fungsi ini akan melempar TypeError
    persis seperti kegagalan produksi.
    """
    bot = _bot_baru()
    berita.register_events_cog(bot)

    gagal: list[str] = []
    for event, fns in bot.extra_events.items():
        jumlah = ARGUMEN_EVENT[event]
        for fn in fns:
            args = tuple(object() for _ in range(jumlah))
            try:
                hasil = fn(*args)
            except TypeError as exc:  # kesalahan pengikatan argumen
                gagal.append(f"{event}: {exc}")
                continue
            # Jangan dijalankan sungguhan (butuh gateway); cukup tutup coroutine.
            if inspect.iscoroutine(hasil):
                hasil.close()

    assert not gagal, "listener gagal diikat:\n  " + "\n  ".join(gagal)


def test_listener_punya_parameter_bot_posisional_pertama():
    """Listener tetap menerima `bot` sebagai parameter pertama.

    Ini menjaga konvensi modul: listener ditulis `(bot, ...)` dan *diikat* oleh
    `register_events_cog`, bukan menangkap `bot` dari lingkup luar (closure).
    """
    bot = _bot_baru()
    berita.register_events_cog(bot)

    salah: list[str] = []
    for event, fns in bot.extra_events.items():
        for fn in fns:
            asli = inspect.unwrap(fn)
            # pembungkus memakai functools.wraps -> __wrapped__ menunjuk aslinya
            params = list(inspect.signature(asli).parameters)
            if not params or params[0] != "bot":
                salah.append(f"{event}: parameter pertama {params[:1] or '(kosong)'}")

    assert not salah, "konvensi (bot, ...) dilanggar:\n  " + "\n  ".join(salah)


def test_jumlah_parameter_cocok_dengan_argumen_event():
    """Setelah `bot` terikat, sisa parameter harus sama dengan argumen event."""
    bot = _bot_baru()
    berita.register_events_cog(bot)

    timpang: list[str] = []
    for event, fns in bot.extra_events.items():
        for fn in fns:
            asli = inspect.unwrap(fn)
            params = list(inspect.signature(asli).parameters)
            sisa = [p for p in params if p != "bot"]
            diharapkan = ARGUMEN_EVENT[event]
            if len(sisa) != diharapkan:
                timpang.append(
                    f"{event}: {len(sisa)} parameter sisa ({sisa}) "
                    f"vs {diharapkan} argumen event"
                )

    assert not timpang, "jumlah parameter tidak cocok:\n  " + "\n  ".join(timpang)


@pytest.mark.asyncio
async def test_dispatch_menjalankan_on_ready_tanpa_typeerror():
    """Lewat jalur `dispatch` asli: on_ready tidak boleh TypeError.

    `dispatch` menjadwalkan task lewat event loop, jadi bot dibuat di dalam
    konteks async. `on_ready` memanggil `change_presence` yang butuh koneksi
    gateway — di tes itu akan melempar AttributeError, dan itu wajar. Yang
    TIDAK boleh terjadi adalah TypeError karena pengikatan argumen, yaitu
    kegagalan produksi yang ingin dicegah berkas ini.
    """
    bot = _bot_baru()
    # `dispatch` menjadwalkan task lewat `bot.loop`; secara normal loop baru
    # terpasang saat `bot.run()`. Di tes kita pasang loop yang sedang berjalan.
    bot.loop = asyncio.get_running_loop()
    berita.register_events_cog(bot)

    galat: list[BaseException] = []

    async def tangkap(event_method, *args, **kwargs):
        # override on_error supaya error event tidak ditelan diam-diam
        if args and isinstance(args[0], BaseException):
            galat.append(args[0])

    bot.on_error = tangkap  # type: ignore[method-assign]

    bot.dispatch("ready")
    await asyncio.sleep(0.05)  # beri kesempatan task dijadwalkan & selesai

    typeerror = [f"{e}" for e in galat if isinstance(e, TypeError)]
    assert not typeerror, f"TypeError saat dispatch on_ready: {typeerror}"
