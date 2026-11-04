"""Community views — dipisah dari views.py agar berkas tidak membengkak."""

import logging
import discord
from community_tools import grant_verification_role
from utils import find_solved_forum_tag

logger = logging.getLogger("gemini_bot.views.community")


# ==============================================================================
# TOMBOL PERSISTEN FORUM POST: ✅ TANDAI SELESAI / TERJAWAB (AMAN SINGLETON!)
# ==============================================================================
def _build_solved_disabled_view() -> discord.ui.View:
    """Membuat View statis tombol nonaktif tanpa memutasi instance singleton ForumPostSolvedView."""
    done_view = discord.ui.View(timeout=None)
    done_view.add_item(
        discord.ui.Button(
            label="Diskusi Selesai",
            style=discord.ButtonStyle.success,
            emoji="✅",
            disabled=True,
        )
    )
    return done_view
class VerificationGateView(discord.ui.View):
    """Tombol persisten "Verifikasi Saya" untuk membuka akses channel member baru."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verifikasi Saya",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="community:verify_gate",
    )
    async def verify_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            await interaction.response.send_message(
                "⚠️ Tombol verifikasi hanya berlaku di dalam server.", ephemeral=True
            )
            return
        ok, message = await grant_verification_role(interaction.user, interaction.guild.id)
        await interaction.response.send_message(message, ephemeral=True)
        if ok:
            logger.info("Member %s lolos verifikasi di guild %s", interaction.user.id, interaction.guild.id)
class ForumPostSolvedView(discord.ui.View):
    """Tombol persisten pada Postingan Forum agar penanya/Moderator bisa menandai diskusi selesai."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Tandai Selesai",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="gemini_panel:forum_solved",
    )
    async def mark_solved_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.Thread) and getattr(channel, "parent_id", None) is None:
            await interaction.response.send_message(
                "⚠️ Tombol ini hanya berfungsi di dalam Postingan Forum / Thread.",
                ephemeral=True,
            )
            return

        is_owner = getattr(channel, "owner_id", None) == interaction.user.id
        is_mod = isinstance(interaction.user, discord.Member) and (
            interaction.user.guild_permissions.administrator
            or interaction.user.guild_permissions.manage_threads
            or interaction.user.guild_permissions.manage_messages
        )
        if not is_owner and not is_mod:
            await interaction.response.send_message(
                "⚠️ Hanya **pembuat postingan ini** atau **Moderator** yang dapat menandai diskusi sebagai selesai.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            if interaction.message:
                await interaction.message.edit(view=_build_solved_disabled_view())
        except discord.HTTPException:
            pass

        cur_name = (channel.name or "").strip()
        new_name = cur_name if cur_name.startswith("✅") else f"✅ {cur_name}"[:100]

        parent = getattr(channel, "parent", None)
        avail_tags = getattr(parent, "available_tags", None) or []
        solved_tag = find_solved_forum_tag(avail_tags)
        current_tags = list(getattr(channel, "applied_tags", None) or [])
        if solved_tag is not None and solved_tag not in current_tags:
            current_tags = ([solved_tag] + current_tags)[:5]

        await interaction.followup.send(
            f"✅ Postingan ini telah ditandai **Selesai / Terjawab** oleh {interaction.user.mention}! "
            "Terima kasih sudah berdiskusi 🙌"
        )

        edit_kwargs: dict = {"archived": True}
        if new_name and new_name != cur_name:
            edit_kwargs["name"] = new_name
        if solved_tag is not None:
            edit_kwargs["applied_tags"] = current_tags

        try:
            await channel.edit(**edit_kwargs)
        except discord.HTTPException:
            try:
                if new_name != cur_name:
                    await channel.edit(name=new_name)
            except discord.HTTPException:
                pass
