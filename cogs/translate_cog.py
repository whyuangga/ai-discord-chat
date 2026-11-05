"""Slash `/terjemah` + **reaksi bendera** — penerjemah hemat kuota.

Tiga cara pakai (semua memakai cache, jadi kalimat berulang = **0 kuota**):

1. **Reaksi bendera** (paling hemat, disarankan): Admin memilih channel lewat
   `/terjemah channel`, bot memasang reaksi 🇮🇩/🇬🇧 di pesan warga. Terjemahan
   **baru dibuat ketika ada yang mengklik** reaksi itu (dikirim via DM agar channel
   tidak banjir), lalu disimpan di cache.
2. **`/terjemah teks` & `/terjemah pesan`**: manual, kapan pun dibutuhkan.
3. **Auto-post per channel** (opsional, **default mati**): setiap pesan diterjemahkan
   otomatis. Ini satu-satunya mode yang benar-benar boros kuota, jadi dibatasi
   rate limit 3 detik/channel + batas `AI_DAILY_CAP_PER_GUILD`.

Semua jalur menghormati batas kuota server (`ai_guard`) dan tercatat di `/pemakaian`.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import ai_guard
import ai_handler
import insights
import translate_tools
import ui_kit
import ui_theme

logger = logging.getLogger("gemini_bot.translate_cog")

terjemah_group = app_commands.Group(
    name="terjemah",
    description="Terjemahkan teks/pesan atau aktifkan reaksi bendera di channel (hemat kuota AI)",
    guild_only=True,
    default_permissions=discord.Permissions(send_messages=True),
)

_TARGET_CHOICES = [
    app_commands.Choice(name="🇮🇩 Indonesia", value="id"),
    app_commands.Choice(name="🇬🇧 English", value="en"),
]


def _mode_for(target: str) -> str:
    return "translate_en" if str(target) == "en" else "translate_id"


def _label(target: str) -> str:
    return "English" if str(target) == "en" else "Indonesia"


async def translate_text(text: str, target: str = "id", *, guild_id: int = 0) -> tuple[str | None, str | None]:
    """Menerjemahkan teks dengan cache lebih dulu, lalu memanggil Gemini bila perlu.

    Mengembalikan `(hasil, pesan_error)`.
    """
    raw = str(text or "").strip()
    if not translate_tools.looks_translatable(raw):
        return None, (
            "⚠️ Teks terlalu pendek / kosong / hanya berisi link-emoji. "
            "Kirim minimal 8 karakter berupa kata untuk diterjemahkan."
        )

    cached = translate_tools.get_cached_translation(raw, target)
    if cached:
        try:
            insights.record_ai_usage("terjemah", guild_id=int(guild_id or 0), cache_hit=True)
        except Exception:  # pragma: no cover - statistik tidak boleh menggagalkan
            pass
        return cached, None

    allowed, used, limit = ai_guard.check_guild_cap(int(guild_id or 0))
    if not allowed:
        return None, ai_guard.cap_message(int(guild_id or 0), used, limit)

    result, err = await ai_handler.transform_message_with_gemini(_mode_for(target), raw)
    if not result:
        return None, err or "⚠️ Gagal menerjemahkan pesan ini, coba lagi sebentar."

    translate_tools.store_cached_translation(raw, target, result)
    try:
        insights.record_ai_usage("terjemah", guild_id=int(guild_id or 0))
    except Exception:  # pragma: no cover
        pass
    return result, None


def _translation_embed(guild_id: int, source: str, result: str, target: str) -> discord.Embed:
    clipped = str(source or "").strip()
    if len(clipped) > 240:
        clipped = clipped[:237] + "…"
    return ui_theme.status_embed(
        guild_id,
        "info",
        f"🌐 Terjemahan {_label(target)}",
        f"> {clipped}\n\n{str(result or '')[:3500]}",
        footer="Diterjemahkan AI • kalimat serupa dijawab dari cache (0 kuota)",
    )


@terjemah_group.command(name="teks", description="Terjemahkan teks yang kamu tulis langsung di sini")
@app_commands.describe(teks="Teks yang ingin diterjemahkan", ke="Bahasa tujuan terjemahan")
@app_commands.choices(ke=_TARGET_CHOICES)
async def terjemah_teks_cmd(
    interaction: discord.Interaction,
    teks: str,
    ke: app_commands.Choice[str] | None = None,
):
    gid = interaction.guild.id if interaction.guild else 0
    target = ke.value if ke else "id"
    await interaction.response.defer(ephemeral=True, thinking=True)
    result, err = await translate_text(teks, target, guild_id=gid)
    if not result:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Terjemahan gagal", err or "Tidak ada hasil."),
            follow=True,
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        embed=_translation_embed(gid, teks, result, target), ephemeral=True
    )


def _parse_message_id(raw: str) -> int:
    """Menerima ID polos atau tautan pesan Discord lalu mengembalikan ID-nya."""
    text = str(raw or "").strip()
    if text.isdigit():
        return int(text)
    # https://discord.com/channels/<guild>/<channel>/<message>
    candidate = text.split("?")[0].rstrip("/").split("/")[-1]
    return int(candidate) if candidate.isdigit() else 0


@terjemah_group.command(
    name="pesan",
    description="Terjemahkan pesan tertentu via ID/tautan (klik kanan pesan → Copy Message Link)",
)
@app_commands.describe(
    pesan_id="ID atau tautan pesan Discord yang ingin diterjemahkan",
    ke="Bahasa tujuan terjemahan",
    channel="Channel tempat pesan itu berada (kosong = channel ini)",
)
@app_commands.choices(ke=_TARGET_CHOICES)
async def terjemah_pesan_cmd(
    interaction: discord.Interaction,
    pesan_id: str,
    ke: app_commands.Choice[str] | None = None,
    channel: discord.TextChannel | None = None,
):
    gid = interaction.guild.id if interaction.guild else 0
    target = ke.value if ke else "id"
    mid = _parse_message_id(pesan_id)
    target_channel = channel or interaction.channel

    if not mid or target_channel is None:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "warn",
                "ID pesan tidak valid",
                "Klik kanan pesan → **Copy Message Link**, lalu tempel ke parameter `pesan_id`.",
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        pesan = await target_channel.fetch_message(mid)
    except Exception:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "error",
                "Pesan tidak ditemukan",
                "Pastikan ID/tautannya benar, pesannya masih ada, dan bot punya izin membaca channel itu.",
            ),
            follow=True,
            ephemeral=True,
        )
        return

    text = (pesan.content or "").strip()
    if not text:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "warn",
                "Pesan tanpa teks",
                "Pesan itu tidak berisi teks yang bisa diterjemahkan (mungkin hanya lampiran/embed).",
            ),
            follow=True,
            ephemeral=True,
        )
        return

    result, err = await translate_text(text, target, guild_id=gid)
    if not result:
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(gid, "error", "Terjemahan gagal", err or "Tidak ada hasil."),
            follow=True,
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        embed=_translation_embed(gid, text, result, target), ephemeral=True
    )


@terjemah_group.command(
    name="channel",
    description="Aktifkan reaksi bendera (dan/atau auto-terjemahan) pada satu channel — Admin",
)
@app_commands.describe(
    channel="Channel tempat warga ngobrol lintas bahasa",
    aktif="False untuk melepas channel ini dari penerjemah",
    reaksi="Tempel reaksi 🇮🇩/🇬🇧 di tiap pesan (0 kuota sampai ada yang mengklik)",
    auto="Terjemahkan otomatis setiap pesan (BOROS kuota — gunakan hanya di channel kecil)",
)
async def terjemah_channel_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    aktif: bool = True,
    reaksi: bool = True,
    auto: bool = False,
):
    if interaction.guild is None:
        return
    gid = interaction.guild.id
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))):
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid, "lock", "Butuh izin Admin", "Hanya Admin / *Manage Server* yang bisa mengatur channel penerjemah."
            ),
            ephemeral=True,
        )
        return

    if not aktif:
        removed = translate_tools.remove_channel_config(gid, channel.id)
        await translate_tools.save_translate_to_disk()
        await ui_kit.send_status(
            interaction,
            embed=ui_theme.status_embed(
                gid,
                "ok" if removed else "info",
                "Penerjemah dilepas",
                (
                    f"{channel.mention} tidak lagi memakai reaksi bendera maupun auto-terjemahan."
                    if removed
                    else f"{channel.mention} memang belum terdaftar di penerjemah."
                ),
            ),
            ephemeral=True,
        )
        return

    translate_tools.set_channel_config(
        gid, channel.id, enabled=True, auto_react=reaksi, auto_post=auto
    )
    await translate_tools.save_translate_to_disk()

    mode_lines = []
    if reaksi:
        mode_lines.append("🇮🇩/🇬🇧 **reaksi bendera** aktif (0 kuota sampai ada yang mengklik)")
    if auto:
        mode_lines.append(
            "⚠️ **auto-terjemahan aktif** — setiap pesan layak akan diterjemahkan "
            f"(rate limit {translate_tools.TRANSLATE_RATE_LIMIT_SEC} detik + batas kuota server)"
        )
    if not mode_lines:
        mode_lines.append("channel terdaftar, tetapi belum ada mode yang diaktifkan")

    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "ok",
            "Penerjemah channel diperbarui",
            f"Channel: {channel.mention}\n" + "\n".join(f"• {line}" for line in mode_lines),
        ),
        ephemeral=True,
    )


@terjemah_group.command(name="status", description="Lihat channel penerjemah, ukuran cache, & sisa kuota AI server")
async def terjemah_status_cmd(interaction: discord.Interaction):
    gid = interaction.guild.id if interaction.guild else 0
    channels = translate_tools.watched_channel_ids(gid)
    channel_lines = []
    for cid in channels[:10]:
        cfg = translate_tools.channel_config(gid, cid) or {}
        flags = []
        if cfg.get("auto_react", True):
            flags.append("reaksi")
        if cfg.get("auto_post"):
            flags.append("auto")
        channel_lines.append(f"• <#{cid}> — {', '.join(flags) or 'pasif'}")
    if not channel_lines:
        channel_lines.append("_belum ada channel yang diatur_")

    _ok, used, limit = ai_guard.check_guild_cap(int(gid or 0))
    quota = f"`{used}` / `{limit}` operasi" if limit else f"`{used}` operasi (tanpa batas)"
    await ui_kit.send_status(
        interaction,
        embed=ui_theme.status_embed(
            gid,
            "info",
            "🌐 Status Penerjemah",
            "\n".join(channel_lines)
            + f"\n\n**Cache terjemahan:** `{translate_tools.cache_size()}` kalimat "
            f"(umur {translate_tools.TRANSLATE_CACHE_TTL_SEC // 3600} jam → 0 kuota)\n"
            f"**Kuota AI server hari ini:** {quota}\n\n"
            "Cara pakai terhemat: warga bereaksi 🇮🇩/🇬🇧 di pesan, terjemahan dikirim via DM.",
        ),
        ephemeral=True,
    )


# ==============================================================================
# HOOK DARI EVENTS (dipanggil events_cog agar tidak ada event ganda)
# ==============================================================================
async def handle_translate_reaction(bot, payload) -> bool:
    """Menangani reaksi bendera 🇮🇩/🇬🇧. Mengembalikan True bila reaksi ini milik penerjemah."""
    emoji = str(getattr(payload, "emoji", "") or "")
    target = translate_tools.FLAG_TARGETS.get(emoji)
    guild_id = getattr(payload, "guild_id", None)
    if not target or guild_id is None:
        return False

    channel_id = int(getattr(payload, "channel_id", 0) or 0)
    cfg = translate_tools.channel_config(int(guild_id), channel_id)
    if not cfg or not cfg.get("auto_react", True):
        return False

    channel = bot.get_channel(channel_id) if callable(getattr(bot, "get_channel", None)) else None
    fetch_message = getattr(channel, "fetch_message", None)
    if not callable(fetch_message):
        return False

    try:
        message = await fetch_message(int(getattr(payload, "message_id", 0) or 0))
    except Exception:  # pragma: no cover - pesan terhapus/tanpa izin
        return False

    if getattr(getattr(message, "author", None), "bot", False):
        return False
    text = str(getattr(message, "content", "") or "").strip()
    if not translate_tools.looks_translatable(text):
        return False
    if translate_tools.rate_limited(channel_id):
        # Channel baru saja diterjemahkan: reaksi tetap dianggap milik penerjemah,
        # tetapi TIDAK memanggil AI (hemat kuota) dan tidak diteruskan ke fitur lain.
        return True

    result, _err = await translate_text(text, target, guild_id=int(guild_id))
    if not result:
        return True   # reaksi tetap dianggap milik penerjemah (mis. kuota habis)

    embed = _translation_embed(int(guild_id), text, result, target)

    # 1) Utamakan DM agar channel tidak banjir
    user = getattr(payload, "member", None)
    if user is None and callable(getattr(bot, "fetch_user", None)):
        try:
            user = await bot.fetch_user(int(getattr(payload, "user_id", 0) or 0))
        except Exception:
            user = None
    if user is not None:
        try:
            await user.send(embed=embed)
            return True
        except Exception:
            pass

    # 2) Cadangan: balas pesan aslinya tanpa mention
    reply = getattr(message, "reply", None)
    if callable(reply):
        try:
            await reply(
                embed=embed,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:  # pragma: no cover - jaring aman
            pass
    return True


async def maybe_auto_translate(bot, message) -> bool:
    """Auto-terjemahan per channel (default mati). Mengembalikan True bila mengirim hasil."""
    guild = getattr(message, "guild", None)
    if guild is None or getattr(getattr(message, "author", None), "bot", False):
        return False

    channel_id = int(getattr(getattr(message, "channel", None), "id", 0) or 0)
    cfg = translate_tools.channel_config(int(guild.id), channel_id)
    if not cfg or not cfg.get("auto_post"):
        return False

    text = str(getattr(message, "content", "") or "").strip()
    if not translate_tools.looks_translatable(text):
        return False
    if translate_tools.rate_limited(channel_id):
        return False

    result, _err = await translate_text(text, "id", guild_id=int(guild.id))
    if not result:
        return False

    reply = getattr(message, "reply", None)
    if callable(reply):
        try:
            await reply(
                embed=_translation_embed(int(guild.id), text, result, "id"),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True
        except Exception:  # pragma: no cover - jaring aman
            return False
    return False


def register_translate_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command `/terjemah` ke bot."""
    bot.tree.add_command(terjemah_group)
