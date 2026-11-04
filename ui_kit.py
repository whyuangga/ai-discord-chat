"""Komponen UI reusable berbasis **Components V2** (Container, Section, Separator).

Dipakai seluruh panel bot supaya tampilannya seragam & terasa seperti dashboard
web hosting di dalam Discord:

    ┌──────────────────────────────────────────┐
    │ 🛰️  Judul Panel                 [ikon]   │
    │ subjudul ringkas                         │
    ├──────────────────────────────────────────┤
    │ Status: 🟢 Online          [ tombol ]    │
    └──────────────────────────────────────────┘

Semua fungsi di sini **tidak memanggil AI** (0 kuota) dan tetap punya jalur
cadangan (embed klasik) bila server menolak pesan Components V2.
"""

import logging

import discord
from discord import ui

import ui_theme

logger = logging.getLogger("gemini_bot.ui_kit")

# Batas keras Discord
MAX_TEXT = 4000
MAX_COMPONENTS = 40
MAX_BUTTONS_PER_ROW = 5
MAX_SELECT_OPTIONS = 25


# ==============================================================================
# BLOK DASAR
# ==============================================================================
def text(content: str) -> ui.TextDisplay:
    """Blok teks Markdown (tanpa kotak embed)."""
    return ui.TextDisplay(str(content)[:MAX_TEXT])


def sep(*, big: bool = False) -> ui.Separator:
    """Garis pemisah kartu."""
    return ui.Separator(spacing=discord.SeparatorSpacing.large if big else discord.SeparatorSpacing.small)


def title_line(guild_id: int | None, icon_key: str, title: str, subtitle: str = "") -> str:
    """Judul bergaya `### 🛰️ Judul` + subjudul kecil."""
    icon = ui_theme.emoji(guild_id, icon_key, "")
    head = f"### {icon} {title}".strip()
    return f"{head}\n{subtitle}" if subtitle else head


def status_line(label: str, value: str, *, state: str | None = None) -> str:
    """Satu baris status `**Label** · value` dengan penanda ● berwarna."""
    if state == "on":
        mark = "🟢"
    elif state == "off":
        mark = "🔴"
    elif state == "warn":
        mark = "🟡"
    elif state == "idle":
        mark = "⚪"
    else:
        mark = ""
    prefix = f"{mark} " if mark else ""
    return f"{prefix}**{label}** · {value}"


def progress_bar(current: int | float, total: int | float, *, length: int = 14) -> str:
    """Progress bar `▬▬🔘▬▬` (dipakai panel musik & level)."""
    try:
        total = float(total or 0)
        current = float(current or 0)
    except (TypeError, ValueError):
        return "▬" * length
    if total <= 0:
        return "▬" * length
    ratio = max(0.0, min(1.0, current / total))
    filled = int(round(ratio * (length - 1)))
    return "▬" * filled + "🔘" + "▬" * max(0, length - 1 - filled)


def human_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}h {hours}j"
    if hours:
        return f"{hours}j {minutes}m"
    return f"{minutes}m"


# ==============================================================================
# KARTU & BARIS
# ==============================================================================
def card(
    guild_id: int | None,
    *children,
    accent: discord.Colour | None = None,
) -> ui.Container:
    """Kartu dengan warna aksen tema server."""
    container = ui.Container(accent_colour=accent or ui_theme.accent_color(guild_id))
    for child in children:
        if child is None:
            continue
        container.add_item(child)
    return container


def action_row(*children) -> ui.ActionRow:
    """Baris komponen (maks 5 tombol, atau 1 dropdown)."""
    return ui.ActionRow(*children)


def header(
    guild_id: int | None,
    icon_key: str,
    title: str,
    subtitle: str = "",
    *,
    thumbnail_url: str | None = None,
) -> ui.Section | ui.TextDisplay:
    """Bagian judul; memakai `Section` + thumbnail bila tema mengizinkan."""
    body = title_line(guild_id, icon_key, title, subtitle)
    if thumbnail_url and ui_theme.show_thumbnail(guild_id):
        return ui.Section(text(body), accessory=ui.Thumbnail(thumbnail_url))
    return text(body)


def field_block(label: str, lines: list[str]) -> str:
    """Blok `**Label**` + daftar baris (otomatis dibuang bila kosong)."""
    clean = [ln for ln in lines if ln]
    if not clean:
        return ""
    return "**" + label + "**\n" + "\n".join(clean)


def empty_hint(icon: str, message: str) -> str:
    return f"{icon} _{message}_"


# ==============================================================================
# TOMBOL & DROPDOWN
# ==============================================================================
def button(
    label: str,
    *,
    emoji: str | None = None,
    style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    custom_id: str | None = None,
    callback=None,
    disabled: bool = False,
    url: str | None = None,
) -> ui.Button:
    """Tombol siap pakai (callback boleh fungsi async apa pun)."""
    item = ui.Button(
        label=str(label)[:80],
        emoji=emoji,
        style=style,
        custom_id=custom_id,
        disabled=disabled,
        url=url,
    )
    if callback is not None and url is None:
        item.callback = callback  # type: ignore[assignment]
    return item


def toggle_button(
    guild_id: int | None,
    label: str,
    enabled: bool,
    *,
    custom_id: str,
    callback,
) -> ui.Button:
    """Tombol status: hijau saat ON, merah saat OFF (klik = ubah)."""
    return button(
        label,
        emoji=ui_theme.emoji(guild_id, "on" if enabled else "off", "●"),
        style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger,
        custom_id=custom_id,
        callback=callback,
    )


def select_menu(
    custom_id: str,
    placeholder: str,
    options: list[discord.SelectOption],
    *,
    callback,
    disabled: bool = False,
) -> ui.Select:
    item = ui.Select(
        custom_id=custom_id,
        placeholder=str(placeholder)[:150],
        options=options[:MAX_SELECT_OPTIONS],
        disabled=disabled,
    )
    item.callback = callback  # type: ignore[assignment]
    return item


def option(label: str, value: str, *, emoji: str | None = None, description: str | None = None) -> discord.SelectOption:
    return discord.SelectOption(
        label=str(label)[:100],
        value=str(value)[:100],
        emoji=emoji,
        description=(str(description)[:100] if description else None),
    )


# ==============================================================================
# KIRIM / EDIT DENGAN JALUR CADANGAN
# ==============================================================================
def build_view(guild_id: int | None, *items, timeout: float = 900.0) -> ui.LayoutView:
    """Menyusun `LayoutView` berisi kartu (V2)."""
    view = ui.LayoutView(timeout=timeout)
    for item in items:
        if item is None:
            continue
        view.add_item(item)
    return view


def fallback_embed(
    guild_id: int | None,
    title: str,
    description: str = "",
    *,
    fields: list[tuple[str, str]] | None = None,
    footer: str | None = None,
) -> discord.Embed:
    """Embed klasik untuk jalur cadangan (server/klien yang menolak V2)."""
    embed = discord.Embed(
        title=str(title)[:256],
        description=str(description)[:4096] or None,
        color=ui_theme.accent_color(guild_id),
    )
    for name, value in (fields or [])[:25]:
        embed.add_field(name=str(name)[:256], value=str(value)[:1024] or "—", inline=False)
    text = ui_theme.footer_text(guild_id, footer or "")
    if text:
        embed.set_footer(text=text[:2048])
    return embed


async def send_panel(
    interaction: discord.Interaction,
    view: ui.LayoutView,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
) -> bool:
    """Mengirim panel V2; bila ditolak, otomatis memakai embed klasik.

    Mengembalikan `True` bila berhasil sebagai Components V2.
    """
    try:
        await interaction.response.send_message(view=view, ephemeral=ephemeral)
        return True
    except (discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Panel V2 ditolak (%s) — memakai embed klasik.", exc)

    if embed is None:
        embed = fallback_embed(None, "Panel tidak dapat ditampilkan")
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    return False


async def edit_panel(
    interaction: discord.Interaction,
    view: ui.LayoutView,
    *,
    embed: discord.Embed | None = None,
) -> bool:
    """Mengedit pesan panel menjadi V2; gagal → edit dengan embed."""
    try:
        await interaction.response.edit_message(view=view)
        return True
    except (discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Edit panel V2 ditolak (%s) — memakai embed klasik.", exc)

    if embed is None:
        embed = fallback_embed(None, "Panel tidak dapat ditampilkan")
    await interaction.response.edit_message(embed=embed, view=None)
    return False


async def follow_panel(
    interaction: discord.Interaction,
    view: ui.LayoutView,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
) -> bool:
    """Seperti `send_panel` tetapi lewat `followup` (setelah `defer`)."""
    try:
        await interaction.followup.send(view=view, ephemeral=ephemeral)
        return True
    except (discord.HTTPException, TypeError, ValueError) as exc:
        logger.warning("Followup panel V2 ditolak (%s) — memakai embed klasik.", exc)

    if embed is None:
        embed = fallback_embed(None, "Panel tidak dapat ditampilkan")
    await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    return False


# ==============================================================================
# KONFIRMASI AKSI BERBAHAYA
# ==============================================================================
class ConfirmView(ui.LayoutView):
    """Dialog konfirmasi bergaya kartu (hijau = lanjut, merah = batal)."""

    def __init__(
        self,
        guild_id: int | None,
        *,
        title: str,
        detail: str,
        confirm_label: str = "Ya, lanjutkan",
        cancel_label: str = "Batal",
        on_confirm=None,
        on_cancel=None,
        author_id: int | None = None,
    ):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.result: bool | None = None
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self.author_id = author_id

        body = ui_theme.emoji(guild_id, "warn", "⚠️")
        container = card(
            guild_id,
            text(f"### {body} {title}\n{detail}"),
            sep(),
            action_row(
                button(
                    confirm_label,
                    emoji=ui_theme.emoji(guild_id, "ok", "✅"),
                    style=discord.ButtonStyle.success,
                    custom_id="confirm:yes",
                    callback=self._yes,
                ),
                button(
                    cancel_label,
                    emoji=ui_theme.emoji(guild_id, "close", "✖"),
                    style=discord.ButtonStyle.danger,
                    custom_id="confirm:no",
                    callback=self._no,
                ),
            ),
        )
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "⚠️ Dialog ini milik orang lain. Jalankan command sendiri untuk konfirmasi.",
                ephemeral=True,
            )
            return False
        return True

    async def _yes(self, interaction: discord.Interaction) -> None:
        self.result = True
        self.stop()
        if self._on_confirm is not None:
            await self._on_confirm(interaction)
            return
        await interaction.response.edit_message(
            view=build_view(
                self.guild_id,
                card(
                    self.guild_id,
                    text(f"### {ui_theme.emoji(self.guild_id, 'ok', '✅')} Dikonfirmasi\nAksi dijalankan."),
                ),
            )
        )

    async def _no(self, interaction: discord.Interaction) -> None:
        self.result = False
        self.stop()
        if self._on_cancel is not None:
            await self._on_cancel(interaction)
            return
        await interaction.response.edit_message(
            view=build_view(
                self.guild_id,
                card(
                    self.guild_id,
                    text(f"### {ui_theme.emoji(self.guild_id, 'close', '✖')} Dibatalkan\nTidak ada perubahan."),
                ),
            )
        )


async def ask_confirm(
    interaction: discord.Interaction,
    guild_id: int | None,
    *,
    title: str,
    detail: str,
    confirm_label: str = "Ya, lanjutkan",
) -> ConfirmView | None:
    """Mengirim dialog konfirmasi. `None` bila tema server mematikan konfirmasi."""
    if not ui_theme.confirm_enabled(guild_id):
        return None
    view = ConfirmView(
        guild_id,
        title=title,
        detail=detail,
        confirm_label=confirm_label,
        author_id=getattr(interaction.user, "id", None),
    )
    embed = fallback_embed(guild_id, f"⚠️ {title}", detail)
    await send_panel(interaction, view, embed=embed, ephemeral=True)
    return view
