import sys

import discord

import insights
from utils import check_user_cooldown


def get_memory_usage_mb() -> float:
    """Membaca pemakaian RAM proses saat ini (MB) untuk pemantauan di Wispbyte/Linux."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024, 1)
    except Exception:
        pass
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return round(usage / (1024 * 1024), 1)
        return round(usage / 1024, 1)
    except Exception:
        return 0.0


def is_interaction_admin(interaction: discord.Interaction) -> bool:
    """Memeriksa apakah pengguna pada Interaction memiliki izin Administrator server."""
    return isinstance(interaction.user, discord.Member) and bool(
        interaction.user.guild_permissions.administrator
    )


def get_interaction_http_session(interaction: discord.Interaction):
    """Mengambil aiohttp.ClientSession bersama dari interaction.client secara aman."""
    client = getattr(interaction, "client", None)
    return getattr(client, "http_session", None) if client is not None else None


async def enforce_member_cooldown(
    interaction: discord.Interaction,
    bucket: str,
    cooldown_sec: int | None = None,
) -> bool:
    """Memastikan member mematuhi jeda wajar antar pemakaian fitur berat.

    Admin server **bebas** dari jeda maupun batas harian AI agar tetap bisa mengurus server.
    """
    is_admin = is_interaction_admin(interaction)
    rem = check_user_cooldown(
        interaction.user.id,
        bucket,
        cooldown_sec,
        is_admin=is_admin,
    )
    if rem > 0:
        await interaction.response.send_message(
            f"⏳ Mohon tunggu **{rem} detik** lagi sebelum memakai fitur ini kembali *(proteksi kuota Free Tier)*.",
            ephemeral=True,
        )
        return False

    if is_admin:
        return True

    allowed, used, cap = insights.check_daily_cap(interaction.user.id)
    if not allowed:
        await interaction.response.send_message(
            f"🛑 Batas harian fitur AI tercapai: **{used}/{cap}** operasi per member per hari "
            f"*(menjaga kuota Free Tier tetap aman)*.\n"
            f"• Pakai **`/faq tanya`** untuk info server — **0 kuota**\n"
            f"• Pakai **`/ringkas channel`** berulang — hasil dalam cache **0 kuota**\n"
            f"• Coba lagi besok, atau minta Admin memperbesar `AI_DAILY_CAP_PER_USER`.",
            ephemeral=True,
        )
        return False
    return True


def resolve_public_feature_channel_id(
    channel: discord.abc.Messageable | None,
) -> tuple[int | None, bool]:
    """Mengembalikan `(effective_channel_id, is_private_session_or_dm)`.
    Jika berada di dalam ruang privat `ai-...`/`draw-...` atau DM, kembalikan `(None, True)`.
    Jika berada di dalam Thread/Postingan Forum publik, gunakan `parent_id` channel induknya.
    """
    if channel is None or isinstance(channel, discord.DMChannel):
        return None, True
    if isinstance(channel, discord.Thread):
        if (channel.name or "").startswith(("ai-", "draw-")):
            return None, True
        return getattr(channel, "parent_id", None) or channel.id, False
    return getattr(channel, "id", None), False
