import asyncio
import io
import random
import discord
from discord import app_commands
from discord.ext import commands

import ai_handler
from config import ENABLE_IMAGE_FALLBACK
from games import (
    GAME_POINTS_BY_MODE,
    GAME_ROUND_TIMEOUT_SEC,
    WORD_CHAIN_MAX_TURNS,
    WORD_CHAIN_TURN_TIMEOUT_SEC,
    TextGuessControlView,
    TriviaButtonsView,
    WordChainControlView,
    active_channel_games,
    cancel_channel_game,
    finish_word_chain_round,
    generate_ai_game_question,
    get_guild_leaderboard,
    get_user_rank_info,
    reset_guild_scores,
    save_game_scores_to_disk,
    schedule_word_chain_timeout,
    scramble_word,
)
from cogs.helpers import enforce_member_cooldown, get_interaction_http_session


game_group = app_commands.Group(
    name="game",
    description="Mainkan 6 Mode Mini-Game Tongkrongan AI seru & kejar Papan Skor server!",
    guild_only=True,
)


async def _text_game_timeout_watcher(
    channel: discord.abc.Messageable,
    channel_id: int,
    state_ref: dict,
) -> None:
    """Mengungkap jawaban otomatis bila waktu tebak kata di chat habis tanpa pemenang."""
    try:
        await asyncio.sleep(GAME_ROUND_TIMEOUT_SEC)
    except asyncio.CancelledError:
        return

    current = active_channel_games.get(channel_id)
    if current is not state_ref:
        return

    active_channel_games.pop(channel_id, None)
    view_obj: discord.ui.View | None = state_ref.get("view")
    msg_obj: discord.Message | None = state_ref.get("message")
    if view_obj and msg_obj:
        for child in view_obj.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await msg_obj.edit(view=view_obj)
        except discord.HTTPException:
            pass

    try:
        await channel.send(
            f"⌛ **Waktu Habis!** Belum ada yang berhasil menebak dengan tepat.\n"
            f"🔑 Jawaban yang benar adalah: **`{state_ref['answer']}`**\n"
            f"*(Ketik `/game mulai` untuk mencoba tantangan baru!)*"
        )
    except discord.HTTPException:
        pass


@game_group.command(
    name="mulai",
    description="Mulai ronde Mini-Game AI di channel ini dan rebut poin klasemen!",
)
@app_commands.describe(jenis="Pilih mode permainan (kosongkan untuk mode acak kejutan!)")
@app_commands.choices(
    jenis=[
        app_commands.Choice(name="🎭 Tebak dari Emoji - +20 Poin", value="emoji"),
        app_commands.Choice(name="🖼️ Tebak Gambar AI - +25 Poin", value="image_guess"),
        app_commands.Choice(name="⛓️ Sambung Kata Indonesia - +5 Poin/Kata", value="word_chain"),
        app_commands.Choice(name="🧠 Kuis Trivia Cepat A/B/C/D - +15 Poin", value="trivia"),
        app_commands.Choice(name="🕵️ Tebak Kata Misteri - +20 Poin", value="riddle"),
        app_commands.Choice(name="🔀 Susun Huruf Acak - +15 Poin", value="scramble"),
    ]
)
async def slash_game_mulai(
    interaction: discord.Interaction,
    jenis: app_commands.Choice[str] | None = None,
):
    channel = interaction.channel
    if (
        not isinstance(channel, (discord.TextChannel, discord.Thread))
        or interaction.guild is None
        or (isinstance(channel, discord.Thread) and channel.name.startswith(("ai-", "draw-")))
    ):
        await interaction.response.send_message(
            "⚠️ Mini-Game hanya bisa dimainkan di Text Channel atau Thread publik server (bukan ruang sesi `ai-`/`draw-`).",
            ephemeral=True,
        )
        return

    if channel.id in active_channel_games:
        await interaction.response.send_message(
            "🎮 Masih ada ronde game yang sedang berlangsung di channel ini! Tebak dulu atau gunakan `/game stop`.",
            ephemeral=True,
        )
        return

    if not await enforce_member_cooldown(interaction, "game_mulai", cooldown_sec=5):
        return

    random_pool = ["emoji", "trivia", "riddle", "scramble", "word_chain"]
    if ENABLE_IMAGE_FALLBACK:
        random_pool.append("image_guess")
    chosen_mode = jenis.value if jenis else random.choice(random_pool)
    points = GAME_POINTS_BY_MODE.get(chosen_mode, 15)
    await interaction.response.defer()

    if channel.id in active_channel_games:
        await interaction.followup.send(
            "🎮 Ronde baru saja dimulai oleh member lain! Yuk ikut menebak di atas.",
            ephemeral=True,
        )
        return

    http_session = get_interaction_http_session(interaction)
    q_data = await generate_ai_game_question(
        chosen_mode,
        interaction.guild.id,
        http_session=http_session,
    )

    if chosen_mode == "word_chain":
        start_word = str(q_data.get("start_word") or "NUSANTARA").strip().upper()
        next_letter = start_word[-1]
        embed = discord.Embed(
            title=f"⛓️ SAMBUNG KATA INDONESIA — +{points} Poin / Kata!",
            description=(
                f"🏁 **Kata Pembuka:** ## `{start_word}`\n"
                f"👉 Ketik **1 kata Bahasa Indonesia** yang berawalan huruf **`{next_letter}`** langsung di chat!\n\n"
                f"📜 **Aturan Main:**\n"
                f"• Setiap kata valid berhadiah **+{points} Poin** (maksimal `{WORD_CHAIN_MAX_TURNS}` rantai kata).\n"
                f"• Tidak boleh mengulang kata yang sudah dipakai & batas waktu **`{WORD_CHAIN_TURN_TIMEOUT_SEC}` detik** per giliran!"
            ),
            color=discord.Color.teal(),
        )
        embed.set_footer(text=f"Dimulai oleh {interaction.user.display_name}")
        wc_view = WordChainControlView(channel.id, interaction.user.id)
        wc_state: dict = {
            "type": "word_chain",
            "guild_id": interaction.guild.id,
            "starter_id": interaction.user.id,
            "current_word": start_word,
            "answer": start_word,
            "used_words": {start_word.lower()},
            "chain_words": [start_word],
            "chain_count": 0,
            "points": points,
            "round_scores": {},
            "view": wc_view,
        }
        active_channel_games[channel.id] = wc_state
        sent_msg = await interaction.followup.send(embed=embed, view=wc_view, wait=True)
        wc_state["message"] = sent_msg
        schedule_word_chain_timeout(channel, channel.id)
        return

    if chosen_mode == "trivia":
        letters = ("A", "B", "C", "D")
        opt_lines = "\n".join(f"**{letters[i]}.** {q_data['options'][i]}" for i in range(4))
        embed = discord.Embed(
            title=f"🧠 KUIS TRIVIA CEPAT — Berhadiah +{points} Poin!",
            description=(
                f"❓ **{q_data['question']}**\n\n"
                f"{opt_lines}\n\n"
                f"⚡ *Klik tombol jawaban paling cepat di bawah! (1x kesempatan per orang, waktu {GAME_ROUND_TIMEOUT_SEC} detik)*"
            ),
            color=discord.Color.purple(),
        )
        embed.set_footer(text=f"Dimulai oleh {interaction.user.display_name}")
        view = TriviaButtonsView(channel.id, interaction.guild.id, q_data, points)
        active_channel_games[channel.id] = {
            "type": "trivia",
            "starter_id": interaction.user.id,
            "answer": q_data["options"][q_data["correct_index"]],
            "points": points,
            "view": view,
        }
        sent_msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = sent_msg
        active_channel_games[channel.id]["message"] = sent_msg
        return

    mystery_file: discord.File | None = None
    if chosen_mode == "image_guess":
        img_bytes = await ai_handler.generate_mystery_game_image_bytes(
            str(q_data.get("visual_prompt") or ""),
            http_session=http_session,
        )
        title = f"🖼️ TEBAK GAMBAR AI — Berhadiah +{points} Poin!"
        if img_bytes:
            mystery_file = discord.File(io.BytesIO(img_bytes), filename="misteri.png")
            desc = (
                f"🏷️ **Kategori:** `{q_data.get('category', 'Misteri Visual')}`\n\n"
                "👀 **Perhatikan gambar buatan AI di bawah ini baik-baik!**\n"
                f"💬 *Ketik tebakanmu langsung di chat sekarang! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
            )
        else:
            desc = (
                f"🏷️ **Kategori:** `{q_data.get('category', 'Misteri Visual')}`\n\n"
                f"🎨 **Petunjuk Adegan:** _{q_data.get('extra_hint') or 'Tebak objek populer sesuai kategori di atas!'}_\n\n"
                f"💬 *Ketik tebakanmu langsung di chat sekarang! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
            )
        color = discord.Color.magenta()
        aliases = q_data.get("aliases") or []
    elif chosen_mode == "emoji":
        title = f"🎭 TEBAK DARI EMOJI — Berhadiah +{points} Poin!"
        desc = (
            f"🏷️ **Kategori:** `{q_data.get('category', 'Populer')}`\n\n"
            f"# {q_data['clue_emojis']}\n\n"
            f"💬 *Ketik tebakanmu langsung di chat sekarang! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
        )
        color = discord.Color.gold()
        aliases = q_data.get("aliases") or []
    elif chosen_mode == "riddle":
        clues_fmt = "\n".join(f"**{i + 1}.** {c}" for i, c in enumerate(q_data["clues"]))
        title = f"🕵️ SIAPAKAH / APAKAH AKU? — Berhadiah +{points} Poin!"
        desc = (
            f"🏷️ **Kategori:** `{q_data.get('category', 'Misteri')}`\n\n"
            f"{clues_fmt}\n\n"
            f"💬 *Ketik jawabannya langsung di chat! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
        )
        color = discord.Color.dark_teal()
        aliases = q_data.get("aliases") or []
    else:  # scramble
        scrambled = scramble_word(str(q_data["answer"]))
        title = f"🔀 SUSUN HURUF ACAK — Berhadiah +{points} Poin!"
        desc = (
            f"🏷️ **Kategori:** `{q_data.get('category', 'Kata Umum')}`\n\n"
            f"🔤 Susun huruf berikut menjadi 1 kata yang benar:\n"
            f"## `{scrambled}`\n\n"
            f"💬 *Ketik kata yang benar langsung di chat! ({GAME_ROUND_TIMEOUT_SEC} detik)*"
        )
        color = discord.Color.blurple()
        aliases = []

    embed = discord.Embed(title=title, description=desc, color=color)
    if mystery_file is not None:
        embed.set_image(url="attachment://misteri.png")
    embed.set_footer(text=f"Dimulai oleh {interaction.user.display_name} • Klik tombol di bawah jika butuh bantuan")
    ctrl_view = TextGuessControlView(channel.id, interaction.user.id)
    state_obj: dict = {
        "type": chosen_mode,
        "starter_id": interaction.user.id,
        "answer": str(q_data["answer"]).strip(),
        "aliases": aliases,
        "extra_hint": q_data.get("extra_hint", ""),
        "points": points,
        "view": ctrl_view,
    }
    active_channel_games[channel.id] = state_obj
    send_kwargs: dict = {"embed": embed, "view": ctrl_view, "wait": True}
    if mystery_file is not None:
        send_kwargs["file"] = mystery_file
    sent_msg = await interaction.followup.send(**send_kwargs)
    state_obj["message"] = sent_msg
    state_obj["timeout_task"] = asyncio.create_task(
        _text_game_timeout_watcher(channel, channel.id, state_obj)
    )


@game_group.command(
    name="papan_skor",
    description="Lihat Top 10 Klasemen Papan Skor Mini-Game di server ini",
)
async def slash_game_leaderboard(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("⚠️ Hanya tersedia di dalam server.", ephemeral=True)
        return

    board = get_guild_leaderboard(interaction.guild.id, top_n=10)
    if not board:
        await interaction.response.send_message(
            "🏆 **Papan Skor masih kosong!**\nYuk jadilah juara pertama dengan mengetik `/game mulai`!",
            ephemeral=False,
        )
        return

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines: list[str] = []
    for idx, row in enumerate(board, start=1):
        badge = medals.get(idx, f"`#{idx}`")
        lines.append(
            f"{badge} <@{row['user_id']}> — **{row['points']} Poin** ({row['wins']}x menang)"
        )

    rank, my_pts, my_wins = get_user_rank_info(interaction.guild.id, interaction.user.id)
    embed = discord.Embed(
        title=f"🏆 Papan Skor Mini-Game — {interaction.guild.name}",
        description="\n".join(lines),
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    )
    if rank is not None:
        embed.set_footer(text=f"Posisi Anda: #{rank} • {my_pts} Poin ({my_wins}x menang)")
    else:
        embed.set_footer(text="Anda belum memiliki skor — ketik /game mulai untuk ikut bermain!")
    await interaction.response.send_message(embed=embed)


@game_group.command(
    name="stop",
    description="Hentikan ronde Mini-Game yang sedang berjalan di channel ini",
)
async def slash_game_stop(interaction: discord.Interaction):
    channel = interaction.channel
    if channel is None or channel.id not in active_channel_games:
        await interaction.response.send_message(
            "ℹ️ Tidak ada ronde Mini-Game yang sedang aktif di channel ini.",
            ephemeral=True,
        )
        return

    state = active_channel_games[channel.id]
    is_mod = isinstance(interaction.user, discord.Member) and (
        interaction.user.guild_permissions.administrator
        or interaction.user.guild_permissions.manage_messages
    )
    if interaction.user.id != state.get("starter_id") and not is_mod:
        await interaction.response.send_message(
            "⚠️ Hanya pemulai ronde ini atau Moderator yang dapat menghentikan permainan.",
            ephemeral=True,
        )
        return

    if state.get("type") == "word_chain":
        await interaction.response.send_message(
            f"🛑 Ronde Sambung Kata dihentikan oleh {interaction.user.mention}. Berikut rekap skornya:"
        )
        await finish_word_chain_round(
            channel,
            channel.id,
            reason_title=f"🏁 Sambung Kata Dihentikan oleh {interaction.user.display_name}",
        )
        return

    stopped = cancel_channel_game(channel.id) or state
    view_obj: discord.ui.View | None = stopped.get("view")
    msg_obj: discord.Message | None = stopped.get("message")
    if view_obj and msg_obj:
        for child in view_obj.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await msg_obj.edit(view=view_obj)
        except discord.HTTPException:
            pass

    await interaction.response.send_message(
        f"🛑 Ronde Mini-Game dihentikan oleh {interaction.user.mention}. "
        f"Jawaban dari soal tadi adalah: **`{stopped.get('answer', '-')}`**."
    )


@game_group.command(
    name="reset_skor",
    description="Reset seluruh Papan Skor Mini-Game server kembali ke 0 (Khusus Admin)",
)
async def slash_game_reset_skor(interaction: discord.Interaction):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("⚠️ Hanya tersedia di server.", ephemeral=True)
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "⚠️ Hanya **Administrator** server yang dapat mereset seluruh Papan Skor.",
            ephemeral=True,
        )
        return

    reset_guild_scores(interaction.guild.id)
    await save_game_scores_to_disk()
    await interaction.response.send_message(
        "🔄 **Papan Skor Mini-Game server berhasil direset ke 0!** Musim kompetisi baru dimulai!"
    )


def register_games_cog(bot: commands.Bot) -> None:
    """Mendaftarkan command grup `/game` ke bot."""
    bot.tree.add_command(game_group)
