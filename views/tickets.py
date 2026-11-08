"""Tickets views — dipisah dari views.py agar berkas tidak membengkak."""

import logging
import discord
import tickets
import ui_kit
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.views.tickets")


def _id(nilai: object) -> int:
    """Angka ID yang aman dari `None`/teks aneh."""
    try:
        return int(nilai)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _nilai_select(interaction) -> str:
    """Nilai dropdown yang dipilih (aman untuk interaksi tiruan di tes)."""
    data = getattr(interaction, "data", None)
    if isinstance(data, dict):
        values = data.get("values") or []
        if values:
            return str(values[0])
    return ""


def _slug(nama: str) -> str:
    """Nama topik → bagian nama thread (`Lapor Bug` → `lapor-bug`)."""
    bersih = "".join(ch if ch.isalnum() else "-" for ch in str(nama or "").lower())
    return "-".join(bagian for bagian in bersih.split("-") if bagian)[:30]


async def _buat_thread_tiket(channel, interaction, nama_topik: str):
    """Buat private thread tiket, fallback ke thread publik bila tidak diizinkan."""
    thread = None

    try:
        dasar_nama = f"tiket-{_slug(nama_topik)}-{interaction.user.name}" if nama_topik else f"tiket-{interaction.user.name}"
        thread = await channel.create_thread(
            name=dasar_nama[:90],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=1440,
            reason=f"Tiket dukungan dibuka oleh {interaction.user}",
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Gagal membuat private thread tiket: %s", sanitize_error_message(exc))
        try:  # Fallback: thread publik bila private thread tidak diizinkan
            thread = await channel.create_thread(
                name=dasar_nama[:90],
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440,
                reason="Tiket dukungan (fallback thread publik)",
            )
        except (discord.Forbidden, discord.HTTPException) as exc2:
            logger.warning("Gagal membuat thread tiket: %s", sanitize_error_message(exc2))
            thread = None

    return thread


async def _tambah_peserta_tiket(interaction, thread, cfg: dict, topik: dict | None) -> int | None:
    """Tambahkan pembuat tiket + staf ke thread; kembalikan id role staf."""
    try:
        await thread.add_user(interaction.user)
    except (discord.Forbidden, discord.HTTPException):
        pass

    # Topik boleh punya role staf sendiri; bila tidak, pakai role staf umum.
    staff_role_id = _id((topik or {}).get("staff_role_id")) or cfg.get("staff_role_id")
    if staff_role_id:
        role = interaction.guild.get_role(int(staff_role_id))
        for member in list(getattr(role, "members", []) or [])[:15]:
            if getattr(member, "bot", False):
                continue
            try:
                await thread.add_user(member)
            except (discord.Forbidden, discord.HTTPException):
                continue

    return staff_role_id


async def _kirim_pesan_tiket(
    interaction, thread, data: dict, staff_role_id, cfg: dict
) -> None:
    """Kirim pesan pembuka tiket dengan embed + tombol aksi."""
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


async def handle_ticket_open(interaction: discord.Interaction, topik: dict | None = None) -> None:
    """Logika bersama tombol "Buat Tiket" & dropdown topik (panel V2 maupun embed)."""
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
    nama_topik = str((topik or {}).get("nama") or "").strip()
    topic = f"Bantuan dari {interaction.user.display_name}"[:100]
    if nama_topik:
        topic = f"{nama_topik} — {interaction.user.display_name}"[:100]

    thread = await _buat_thread_tiket(channel, interaction, nama_topik)
    if thread is None:
        await interaction.followup.send(
            "⚠️ Bot tidak bisa membuat thread di channel ini. "
            "Pastikan izin **Create Private Threads** & **Send Messages in Threads** aktif.",
            ephemeral=True,
        )
        return

    staff_role_id = await _tambah_peserta_tiket(interaction, thread, cfg, topik)

    staff_role_id = _id((topik or {}).get("staff_role_id")) or cfg.get("staff_role_id")

    data = tickets.register_ticket(
        thread.id,
        interaction.guild.id,
        interaction.user.id,
        topic=topic,
        topik=nama_topik,
    )

    await tickets.save_tickets_to_disk()

    await _kirim_pesan_tiket(interaction, thread, data, staff_role_id, cfg)

    await interaction.followup.send(
        f"✅ Tiket dibuat: {thread.mention}\nStaf akan segera merespons di sana.",
        ephemeral=True,
    )
class TicketPanelView(ui_kit.ui.LayoutView):
    """Panel tiket persisten bergaya kartu (Components V2, tahan restart bot)."""

    def __init__(self, guild_id: int | None = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        daftar_topik = tickets.list_ticket_topics(guild_id) if guild_id else []
        baris = []
        if daftar_topik:
            opsi = [
                ui_kit.option(
                    f"{item.get('emoji') or ''} {item['nama']}".strip(),
                    item["nama"],
                    emoji=item.get("emoji") or None,
                    description=item.get("deskripsi") or None,
                )
                for item in daftar_topik
            ]
            baris.append(
                ui_kit.action_row(
                    ui_kit.select_menu(
                        "ticket:panel:topik",
                        "Pilih topik bantuan…",
                        opsi,
                        callback=self._pilih_topik,
                    )
                )
            )
            baris.append(
                ui_kit.action_row(
                    ui_kit.button(
                        "Topik lain",
                        emoji="🎟️",
                        style=discord.ButtonStyle.secondary,
                        custom_id="ticket:panel:open",
                        callback=handle_ticket_open,
                    )
                )
            )
        else:
            baris.append(
                ui_kit.action_row(
                    ui_kit.button(
                        "Buat Tiket",
                        emoji="🎟️",
                        style=discord.ButtonStyle.primary,
                        custom_id="ticket:panel:open",
                        callback=handle_ticket_open,
                    )
                )
            )
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
                *baris,
            )
        )

    async def _pilih_topik(self, interaction: discord.Interaction) -> None:
        """Member memilih satu topik dari dropdown → buat tiket dengan role staf topik itu."""
        nama = _nilai_select(interaction)
        topik = tickets.find_topic(self.guild_id or 0, nama) if self.guild_id else None
        await handle_ticket_open(interaction, topik=topik)
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
        status, closed = tickets.close_ticket(
            interaction.channel_id,
            interaction.user.id,
            reason="pembuat tiket" if is_owner else "staf",
        )
        if closed is None:
            await interaction.followup.send("⚠️ Tiket ini tidak tercatat lagi.", ephemeral=True)
            return

        await tickets.save_tickets_to_disk()
        text, filename = tickets.build_transcript(closed, messages)
        await tickets.send_transcript(interaction.client, closed, text, filename)
        # Kartu rating dikirim sebelum thread dikunci
        await send_rating_prompt(interaction.channel, interaction.guild_id, closed)

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


class TicketRatingView(ui_kit.ui.LayoutView):
    """Kartu rating bintang 1–5 setelah tiket ditutup (hanya pembuat tiket)."""

    def __init__(self, guild_id: int | None, thread_id: int, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.thread_id = int(thread_id)
        self.user_id = int(user_id)

        buttons = [
            ui_kit.button(
                f"{star}",
                emoji="⭐",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ticket:rate:{star}",
                callback=self._rate(star),
            )
            for star in range(1, 6)
        ]
        self.add_item(
            ui_kit.card(
                guild_id,
                ui_kit.text(
                    ui_kit.title_line(
                        guild_id,
                        "star",
                        "Bagaimana bantuan staf kami?",
                        "Tekan bintang: **1** = kurang, **5** = sangat puas. Penilaianmu membantu kami jadi lebih baik.",
                    )
                ),
                ui_kit.sep(),
                ui_kit.action_row(*buttons),
            )
        )

    def _rate(self, star: int):
        async def _callback(interaction: discord.Interaction) -> None:
            status, data = tickets.rate_ticket(self.thread_id, star, user_id=interaction.user.id)
            if status == "bukan_pemilik":
                await interaction.response.send_message(
                    "⚠️ Hanya **pembuat tiket** yang bisa memberi rating.", ephemeral=True
                )
                return
            if status == "sudah":
                await interaction.response.send_message(
                    f"🙏 Kamu sudah memberi rating **{int((data or {}).get('rating') or 0)}★** untuk tiket ini.",
                    ephemeral=True,
                )
                return
            if status == "belum_selesai":
                await interaction.response.send_message(
                    "ℹ️ Rating bisa diberikan setelah tiket ditutup.", ephemeral=True
                )
                return
            if status != "ok":
                await interaction.response.send_message(
                    "⚠️ Data tiket ini tidak ditemukan (mungkin bot baru restart).", ephemeral=True
                )
                return

            await tickets.save_tickets_to_disk()
            await interaction.response.send_message(
                f"⭐ Terima kasih! Rating **{star}★** untuk tiket "
                f"**#{int((data or {}).get('number') or 0):04d}** sudah tersimpan.",
                ephemeral=True,
            )
            try:
                await interaction.message.edit(
                    view=ui_kit.build_view(
                        self.guild_id,
                        ui_kit.card(
                            self.guild_id,
                            ui_kit.text(
                                ui_kit.title_line(
                                    self.guild_id,
                                    "ok",
                                    f"Rating diterima: {star}★",
                                    "Terima kasih atas penilaianmu — staf kami akan memakainya untuk perbaikan.",
                                )
                            ),
                        ),
                    )
                )
            except (discord.HTTPException, AttributeError):
                pass

        return _callback


async def send_rating_prompt(channel, guild_id: int, data: dict) -> bool:
    """Mengirim kartu rating bintang ke thread tiket yang baru ditutup."""
    cfg = tickets.get_ticket_config(guild_id)
    if not cfg.get("rating_aktif", True):
        return False
    user_id = int(data.get("user_id") or 0)
    if not user_id or not hasattr(channel, "send"):
        return False
    try:
        await channel.send(
            f"<@{user_id}>",
            view=TicketRatingView(guild_id, int(data.get("thread_id") or 0), user_id),
            allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=user_id)]),
        )
        return True
    except (discord.Forbidden, discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Gagal mengirim kartu rating tiket: %s", sanitize_error_message(exc))
        return False
