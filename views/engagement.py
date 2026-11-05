"""Engagement views — dipisah dari views.py agar berkas tidak membengkak."""

import discord
import engagement


class GiveawayJoinView(discord.ui.View):
    """Tombol persisten 🎉 untuk mengikuti/membatalkan giveaway (tahan restart bot)."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _refresh(self, interaction: discord.Interaction, cfg: dict) -> None:
        """Mengedit pesan giveaway agar jumlah peserta langsung terlihat."""
        try:
            await interaction.message.edit(
                embed=engagement.build_giveaway_embed(cfg, ended=bool(cfg.get("ended"))),
                view=GiveawayJoinView(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @discord.ui.button(label="Ikuti Giveaway", emoji="🎉", style=discord.ButtonStyle.success, custom_id="engagement:giveaway:join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("⚠️ Giveaway hanya berlaku di dalam server.", ephemeral=True)
            return

        role_ids = {
            getattr(role, "id", 0) for role in (getattr(interaction.user, "roles", None) or [])
        }
        status, cfg = engagement.join_giveaway(
            interaction.message.id, interaction.user.id, role_ids=role_ids
        )
        if status == "tidak_ada":
            await interaction.response.send_message(
                "⚠️ Data giveaway ini tidak ditemukan (mungkin bot baru restart). "
                "Minta Admin membuat giveaway baru.",
                ephemeral=True,
            )
            return
        if status == "ended":
            await interaction.response.send_message("⏹️ Giveaway ini sudah berakhir.", ephemeral=True)
            return
        if status == "duplikat":
            await interaction.response.send_message(
                "✅ Kamu **sudah terdaftar**. Semoga beruntung!", ephemeral=True
            )
            return
        if status == "syarat":
            await interaction.response.send_message(
                f"🔒 Giveaway ini hanya untuk pemilik <@&{cfg.get('role_id')}>.", ephemeral=True
            )
            return

        await engagement.save_engagement_to_disk()
        await self._refresh(interaction, cfg or {})
        await interaction.response.send_message(
            f"🎉 **Berhasil ikut!** Total peserta sekarang `{len(cfg.get('entries') or [])}` orang.",
            ephemeral=True,
        )

    @discord.ui.button(label="Batalkan", style=discord.ButtonStyle.secondary, custom_id="engagement:giveaway:leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("⚠️ Giveaway hanya berlaku di dalam server.", ephemeral=True)
            return

        status, cfg = engagement.leave_giveaway(interaction.message.id, interaction.user.id)
        if status == "tidak_ada":
            await interaction.response.send_message("⚠️ Data giveaway ini tidak ditemukan.", ephemeral=True)
            return
        if status == "ended":
            await interaction.response.send_message("⏹️ Giveaway ini sudah berakhir.", ephemeral=True)
            return
        if status == "tidak_terdaftar":
            await interaction.response.send_message(
                "ℹ️ Kamu memang belum terdaftar di giveaway ini.", ephemeral=True
            )
            return

        await engagement.save_engagement_to_disk()
        await self._refresh(interaction, cfg or {})
        await interaction.response.send_message(
            "👋 Pesertaan dibatalkan. Kamu bisa ikut lagi kapan saja sebelum waktu habis.",
            ephemeral=True,
        )


class SuggestionVoteView(discord.ui.View):
    """Tombol persisten 👍/👎 untuk kotak saran (tahan restart)."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _handle(self, interaction: discord.Interaction, choice: str) -> None:
        import suggestions

        if interaction.message is None:
            await interaction.response.send_message("⚠️ Pesan saran tidak ditemukan.", ephemeral=True)
            return

        status, item = suggestions.vote(interaction.message.id, interaction.user.id, choice)
        if status == "tidak_ada":
            await interaction.response.send_message(
                "⚠️ Data saran ini sudah tidak ada (mungkin bot baru restart atau saran dihapus).",
                ephemeral=True,
            )
            return
        if status == "duplikat":
            await interaction.response.send_message(
                f"✅ Kamu sudah memilih {'👍 setuju' if choice == 'up' else '👎 tidak setuju'}.",
                ephemeral=True,
            )
            return

        await suggestions.save_suggestions_to_disk()
        guild_id = interaction.guild.id if interaction.guild else None
        try:
            await interaction.message.edit(
                embed=suggestions.build_suggestion_embed(guild_id, item or {}),
                view=SuggestionVoteView(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        note = "🔁 Suaramu dipindahkan" if status == "berganti" else "✅ Suaramu tercatat"
        await interaction.response.send_message(
            f"{note}: {'👍 setuju' if choice == 'up' else '👎 tidak setuju'} "
            f"• total 👍 `{len((item or {}).get('up') or [])}` / 👎 `{len((item or {}).get('down') or [])}`",
            ephemeral=True,
        )

    @discord.ui.button(label="Setuju", emoji="👍", style=discord.ButtonStyle.success, custom_id="engagement:saran:up")
    async def up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "up")

    @discord.ui.button(label="Tidak Setuju", emoji="👎", style=discord.ButtonStyle.danger, custom_id="engagement:saran:down")
    async def down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "down")
