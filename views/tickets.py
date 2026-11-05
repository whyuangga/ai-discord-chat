"""Tickets views — dipisah dari views.py agar berkas tidak membengkak."""

import logging
import discord
import tickets
import ui_kit
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.views.tickets")


async def handle_ticket_open(interaction: discord.Interaction) -> None:
    """Logika bersama tombol "Buat Tiket" (dipakai panel V2 maupun versi embed)."""
    if interaction.guild is None:
        await interaction.response.send_message("⚠️ Tiket hanya bisa dibuat di dalam server.", ephemeral=True)
        return

    allowed, reason = tickets.can_open_ticket(interaction.guild.id, interaction.user.id)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    cfg = tickets.get_ticket_config(interaction.guild.id)
    channel = interaction.channel
    if channel is None or not hasattr(channel, "create_thread"):
        await interaction.response.send_message(
            "⚠️ Panel tiket harus dipasang di **text channel** agar bisa membuat thread.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    topic = f"Bantuan dari {interaction.user.display_name}"[:100]
    thread = None
    try:
        thread = await channel.create_thread(
            name=f"tiket-{interaction.user.name}"[:90],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=1440,
            reason=f"Tiket dukungan dibuka oleh {interaction.user}",
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal membuat private thread tiket: %s", sanitize_error_message(exc))
        try:  # Fallback: thread publik bila private thread tidak diizinkan
            thread = await channel.create_thread(
                name=f"tiket-{interaction.user.name}"[:90],
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440,
                reason="Tiket dukungan (fallback thread publik)",
            )
        except (discord.Forbidden, discord.HTTPException) as exc2:
            logger.warning("Gagal membuat thread tiket: %s", sanitize_error_message(exc2))
            thread = None

    if thread is None:
        await interaction.followup.send(
            "⚠️ Bot tidak bisa membuat thread di channel ini. "
            "Pastikan izin **Create Private Threads** & **Send Messages in Threads** aktif.",
            ephemeral=True,
        )
        return

    # Tambahkan pembuat tiket (+ staf) ke private thread
    try:
        await thread.add_user(interaction.user)
    except (discord.Forbidden, discord.HTTPException):
        pass
    staff_role_id = cfg.get("staff_role_id")
    if staff_role_id:
        role = interaction.guild.get_role(int(staff_role_id))
        for member in list(getattr(role, "members", []) or [])[:15]:
            if getattr(member, "bot", False):
                continue
            try:
                await thread.add_user(member)
            except (discord.Forbidden, discord.HTTPException):
                continue

    data = tickets.register_ticket(
        thread.id,
        interaction.guild.id,
        interaction.user.id,
        topic=topic,
    )
    await tickets.save_tickets_to_disk()

    mention = f"<@&{staff_role_id}> " if staff_role_id and cfg.get("ping_staff", True) else ""
    try:
        await thread.send(
            content=f"{mention}<@{interaction.user.id}> tiketmu sudah dibuat.",
            embed=tickets.build_ticket_embed(data, staff_role_id=staff_role_id),
            view=TicketActionsView(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
    except (discord.Forbidden, discord.HTTPException):
        pass

    await interaction.followup.send(
        f"✅ Tiket dibuat: {thread.mention}\nStaf akan segera merespons di sana.",
        ephemeral=True,
    )
class TicketPanelView(ui_kit.ui.LayoutView):
    """Panel tiket persisten bergaya kartu (Components V2, tahan restart bot)."""

    def __init__(self, guild_id: int | None = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(
            ui_kit.card(
                guild_id,
                ui_kit.text(
                    ui_kit.title_line(
                        guild_id,
                        "ticket",
                        "Pusat Bantuan Server",
                        "Butuh bantuan staf? Tekan tombol di bawah — tiket dibuat sebagai **private thread**.",
                    )
                ),
                ui_kit.sep(),
                ui_kit.text(
                    "**Cara kerja**\n"
                    "• Klik **🎟️ Buat Tiket** → thread privat otomatis dibuat.\n"
                    "• Tulis pertanyaanmu di thread; staf terkait akan diberi tahu.\n"
                    "• Setelah selesai, staf menutup tiket dan transkrip bisa disimpan."
                ),
                ui_kit.action_row(
                    ui_kit.button(
                        "Buat Tiket",
                        emoji="🎟️",
                        style=discord.ButtonStyle.primary,
                        custom_id="ticket:panel:open",
                        callback=handle_ticket_open,
                    )
                ),
            )
        )
class TicketPanelFallbackView(discord.ui.View):
    """Versi klasik tombol tiket (dipakai bila klien menolak Components V2)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Buat Tiket",
        emoji="🎟️",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:panel:open",
    )
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_open(interaction)
async def send_ticket_panel(channel, guild_id: int | None, embed: discord.Embed):
    """Kirim panel tiket V2 ke channel; bila ditolak, pakai embed klasik."""
    try:
        return await channel.send(view=TicketPanelView(guild_id))
    except (discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Panel tiket V2 ditolak (%s) — memakai embed klasik.", exc)
    return await channel.send(embed=embed, view=TicketPanelFallbackView())
class TicketActionsView(discord.ui.View):
    """Tombol tutup & klaim tiket di dalam thread (persisten)."""

    def __init__(self):
        super().__init__(timeout=None)

    @staticmethod
    def _is_staff(member) -> bool:
        perms = getattr(member, "guild_permissions", None)
        if perms is not None and (
            getattr(perms, "administrator", False)
            or getattr(perms, "manage_threads", False)
            or getattr(perms, "manage_channels", False)
        ):
            return True
        return False

    async def _staff_or_warn(self, interaction: discord.Interaction, data: dict) -> bool:
        cfg = tickets.get_ticket_config(interaction.guild_id)
        staff_role_id = cfg.get("staff_role_id")
        is_staff = self._is_staff(interaction.user)
        if not is_staff and staff_role_id:
            roles = {getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])}
            is_staff = int(staff_role_id) in roles
        if not is_staff:
            await interaction.response.send_message(
                "⚠️ Tombol ini khusus **staf** (role petugas atau Moderator).",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Klaim", emoji="🙋", style=discord.ButtonStyle.secondary, custom_id="ticket:panel:claim")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = tickets.get_ticket(interaction.channel_id)
        if data is None:
            await interaction.response.send_message(
                "⚠️ Data tiket ini tidak ditemukan (mungkin bot baru restart).",
                ephemeral=True,
            )
            return
        if not await self._staff_or_warn(interaction, data):
            return

        status, updated = tickets.claim_ticket(interaction.channel_id, interaction.user.id)
        if status == "selesai" or updated is None:
            await interaction.response.send_message("⏹️ Tiket ini sudah selesai.", ephemeral=True)
            return
        if status == "sudah":
            await interaction.response.send_message(
                "ℹ️ Kamu sudah menangani tiket ini.", ephemeral=True
            )
            return

        await tickets.save_tickets_to_disk()
        try:
            await interaction.channel.edit(
                name=f"tiket-{updated.get('number', 0):04d}-ditangani",
                reason=f"Diklaim oleh {interaction.user}",
            )
        except (discord.Forbidden, discord.HTTPException):
            pass
        await interaction.response.send_message(
            f"🙋 Tiket **#{int(updated.get('number') or 0):04d}** diklaim oleh {interaction.user.mention}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Tutup Tiket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:panel:close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = tickets.get_ticket(interaction.channel_id)
        if data is None:
            await interaction.response.send_message(
                "⚠️ Data tiket ini tidak ditemukan.", ephemeral=True
            )
            return

        cfg = tickets.get_ticket_config(interaction.guild_id)
        staff_role_id = cfg.get("staff_role_id")
        roles = {getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])}
        is_owner = int(data.get("user_id") or 0) == interaction.user.id
        is_staff = self._is_staff(interaction.user) or (
            bool(staff_role_id) and int(staff_role_id) in roles
        )
        if not is_owner and not is_staff:
            await interaction.response.send_message(
                "⚠️ Hanya **pembuat tiket** atau **staf** yang bisa menutup tiket ini.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        messages = await tickets.collect_thread_messages(interaction.channel)
        status, closed = tickets.close_ticket(interaction.channel_id, interaction.user.id)
        if closed is None:
            await interaction.followup.send("⚠️ Tiket ini tidak tercatat lagi.", ephemeral=True)
            return

        await tickets.save_tickets_to_disk()
        text, filename = tickets.build_transcript(closed, messages)
        await tickets.send_transcript(interaction.client, closed, text, filename)

        try:
            await interaction.channel.edit(
                name=f"tiket-{int(closed.get('number') or 0):04d}-selesai"[:100],
                locked=True,
                archived=True,
                reason=f"Tiket ditutup oleh {interaction.user}",
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(
            f"🔒 Tiket **#{int(closed.get('number') or 0):04d}** ditutup oleh {interaction.user.mention}. "
            "Transkrip sudah dikirim ke channel log (bila diatur).",
            allowed_mentions=discord.AllowedMentions.none(),
        )
