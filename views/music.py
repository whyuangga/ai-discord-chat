"""Music views — dipisah dari views.py agar berkas tidak membengkak."""

import logging

import discord
import music
import ui_kit

logger = logging.getLogger("gemini_bot.views.music")


class QueuePaginationView(ui_kit.ui.LayoutView):
    """Antrean musik berhalaman bergaya kartu (Components V2, berlaku 120 detik)."""

    def __init__(
        self,
        tracks: list,
        *,
        requester_id: int,
        page: int = 0,
        now_playing=None,
        guild_id: int | None = None,
    ):
        super().__init__(timeout=120)
        self.tracks = tracks
        self.requester_id = requester_id
        self.page = page
        self.now_playing = now_playing
        self.guild_id = guild_id
        self.total_length = sum(int(getattr(t, "length", 0) or 0) for t in tracks)
        self._build()

    # ------------------------------------------------------------------ data
    def _page(self) -> tuple[discord.Embed, int, int]:
        embed, page, total_pages = music.build_queue_page_embed(
            self.tracks,
            page=self.page,
            total_length=self.total_length,
            now_playing=self.now_playing,
        )
        self.page = page
        return embed, page, total_pages

    def _embed(self) -> discord.Embed:
        """Embed klasik (dipakai sebagai jalur cadangan & pengujian)."""
        embed, _, _ = self._page()
        return embed

    # ----------------------------------------------------------------- render
    def _build(self) -> None:
        self.clear_items()
        embed, page, total_pages = self._page()
        gid = self.guild_id
        header = ui_kit.text(
            ui_kit.title_line(
                gid,
                "music",
                "Antrean Musik",
                f"`{len(self.tracks)}` lagu • total `{music.format_duration(self.total_length)}` • "
                f"halaman `{page + 1}/{total_pages}`",
            )
        )
        body = ui_kit.text(f"{embed.description or '_Antrean kosong._'}"[:3900])
        buttons = ui_kit.action_row(
            ui_kit.button(
                "◀ Sebelumnya",
                custom_id="music:queue:prev",
                disabled=page <= 0,
                callback=self.on_prev,
            ),
            ui_kit.button(
                f"Halaman {page + 1}/{total_pages}",
                custom_id="music:queue:page",
                disabled=True,
                callback=self.on_page_label,
            ),
            ui_kit.button(
                "Berikutnya ▶",
                custom_id="music:queue:next",
                disabled=page >= total_pages - 1,
                callback=self.on_next,
            ),
            ui_kit.button(
                "Tutup",
                emoji="🚪",
                style=discord.ButtonStyle.danger,
                custom_id="music:queue:close",
                callback=self.on_close,
            ),
        )
        self.add_item(ui_kit.card(gid, header, ui_kit.sep(), body, buttons))

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "💡 Jalankan `/musik antrean` sendiri untuk membuka daftar antreanmu.", ephemeral=True
            )
            return False
        return True

    async def _edit(self, interaction: discord.Interaction) -> None:
        embed = self._embed()
        self._build()
        await ui_kit.edit_panel(interaction, self, embed=embed)

    async def on_prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        await self._edit(interaction)

    async def on_next(self, interaction: discord.Interaction) -> None:
        self.page += 1
        await self._edit(interaction)

    async def on_page_label(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

    async def on_close(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            view=ui_kit.build_view(
                self.guild_id,
                ui_kit.card(
                    self.guild_id,
                    ui_kit.text("### 🚪 Antrean ditutup\nBuka lagi dengan `/musik antrean`."),
                ),
                timeout=None,
            )
        )
class MusicPlayerView(discord.ui.View):
    """Panel kontrol pemutar musik persisten ala Rythm (tombol selalu aktif walau bot restart)."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _player_or_warn(self, interaction: discord.Interaction):
        """Mengambil player aktif + memeriksa hak kontrol member."""
        player = music.get_player(interaction.guild)
        if player is None or getattr(player, "channel", None) is None:
            await interaction.response.send_message(
                "⚠️ Tidak ada musik yang sedang diputar. Mulai dengan `/musik putar`.", ephemeral=True
            )
            return None
        if not music.can_control(player, interaction.user):
            await interaction.response.send_message(
                "⚠️ Kamu harus berada di **voice channel yang sama** dengan bot "
                "(atau punya role DJ / izin Admin) untuk memakai tombol ini.",
                ephemeral=True,
            )
            return None
        return player

    async def _refresh(self, interaction: discord.Interaction) -> None:
        await music.send_or_update_panel(
            interaction.client,
            interaction.guild_id,
            view=MusicPlayerView(),
        )

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music:panel:pause")
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        await player.pause(not bool(getattr(player, "paused", False)))
        await self._refresh(interaction)
        await interaction.response.send_message(
            "⏸️ Musik dijeda." if player.paused else "▶️ Musik dilanjutkan.", ephemeral=True
        )

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music:panel:skip")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        if getattr(player, "current", None) is None and len(getattr(player, "queue", [])) == 0:
            await interaction.response.send_message("⚠️ Tidak ada lagu untuk dilewati.", ephemeral=True)
            return
        await player.skip(force=True)
        await self._refresh(interaction)
        await interaction.response.send_message("⏭️ Lagu dilewati.", ephemeral=True)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="music:panel:previous")
    async def previous_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        ok = await music.skip_previous(player)
        if not ok:
            await interaction.response.send_message(
                "⚠️ Belum ada riwayat lagu sebelumnya.", ephemeral=True
            )
            return
        await self._refresh(interaction)
        await interaction.response.send_message("⏮️ Kembali ke lagu sebelumnya.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music:panel:stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        try:
            player.queue.clear()
            await player.stop()
            await player.disconnect()
        except Exception as exc:  # pragma: no cover - node mati
            logger.debug("Gagal menghentikan player: %s", exc)
        await music.close_panel(interaction.client, interaction.guild_id)
        music.forget_announce_channel(interaction.guild_id)
        await interaction.response.send_message(
            "⏹️ Musik dihentikan & bot keluar dari voice channel.", ephemeral=True
        )

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="music:panel:queue")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = music.get_player(interaction.guild)
        if player is None:
            await interaction.response.send_message("⚠️ Tidak ada musik yang diputar.", ephemeral=True)
            return
        tracks = list(player.queue)
        view = QueuePaginationView(
            tracks,
            requester_id=interaction.user.id,
            now_playing=getattr(player, "current", None),
        )
        await interaction.response.send_message(embed=view._embed(), view=view, ephemeral=True)

    @discord.ui.button(emoji="🔁", label="Loop", style=discord.ButtonStyle.secondary, custom_id="music:panel:loop")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        current_mode = getattr(getattr(player, "queue", None), "mode", None)
        next_key = {"normal": "satu", "loop": "semua", "loop_all": "mati"}.get(
            getattr(current_mode, "name", "normal"), "satu"
        )
        player.queue.mode = music.queue_mode_from_key(next_key)
        await self._refresh(interaction)
        await interaction.response.send_message(
            f"🔁 Mode pengulangan: **{music.LOOP_MODES[next_key]}**", ephemeral=True
        )

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="music:panel:shuffle")
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        if len(player.queue) < 2:
            await interaction.response.send_message(
                "⚠️ Antrean kurang dari 2 lagu, tidak ada yang bisa diacak.", ephemeral=True
            )
            return
        player.queue.shuffle()
        await self._refresh(interaction)
        await interaction.response.send_message("🔀 Antrean diacak.", ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="music:panel:vol_down")
    async def volume_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        new_volume = max(1, int(getattr(player, "volume", 60)) - 10)
        await player.set_volume(new_volume)
        music.set_music_settings(interaction.guild_id, volume=new_volume)
        await self._refresh(interaction)
        await interaction.response.send_message(f"🔉 Volume: **{new_volume}%**", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="music:panel:vol_up")
    async def volume_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await self._player_or_warn(interaction)
        if player is None:
            return
        new_volume = min(150, int(getattr(player, "volume", 60)) + 10)
        await player.set_volume(new_volume)
        music.set_music_settings(interaction.guild_id, volume=new_volume)
        await self._refresh(interaction)
        await interaction.response.send_message(f"🔊 Volume: **{new_volume}%**", ephemeral=True)
MUSIC_PANEL_ORDER: list[str] = [
    "music:panel:previous",
    "music:panel:pause",
    "music:panel:skip",
    "music:panel:stop",
    "music:panel:loop",
    "music:panel:shuffle",
    "music:panel:vol_down",
    "music:panel:vol_up",
    "music:panel:queue",
]
def build_music_panel_view(
    player,
    *,
    guild_id: int | None = None,
    filter_name: str | None = "off",
    autoplay: bool | None = None,
    hint: str | None = None,
):
    """Panel pemutar Rythm versi kartu (Components V2).

    Tombol diambil langsung dari `MusicPlayerView` (callback asli) lalu disusun
    ulang di dalam kartu, sehingga tidak ada logika tombol yang diduplikasi.
    """
    embed = music.build_player_embed(
        player, filter_name=filter_name, autoplay=autoplay, hint=hint
    )
    classic = MusicPlayerView()
    by_id = {item.custom_id: item for item in list(classic.children)}
    for item in list(classic.children):
        classic.remove_item(item)
    buttons = [by_id[cid] for cid in MUSIC_PANEL_ORDER if cid in by_id]
    if not buttons:  # pragma: no cover - jaga-jaga bila custom_id berubah
        return None
    rows = [ui_kit.action_row(*buttons[:5])]
    if buttons[5:]:
        rows.append(ui_kit.action_row(*buttons[5:10]))
    return ui_kit.build_view(
        guild_id,
        ui_kit.embed_to_container(guild_id, embed, extra_children=rows),
        timeout=None,
    )
