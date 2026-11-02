import asyncio
import json
import logging
import os
import random
import re
import time
import aiohttp
import discord

from ai_handler import (
    FAST_TEXT_TIMEOUT,
    _borrow_session,
    _build_model_chain,
    _extract_text_from_gemini_response,
    build_thinking_config,
    get_gemini_keys_rotated,
    is_gemini_key_configured,
    mark_model_unhealthy,
)
from config import (
    DATA_DIR,
    GAME_SCORES_FILE,
    GEMINI_API_BASE,
    GEMINI_DEFAULT_MODEL,
    GEMINI_TEXT_FALLBACK_CHAIN,
)
from utils import sanitize_error_message

logger = logging.getLogger("gemini_bot.games")

# Papan skor per server: guild_id -> { user_id_str: {"name": str, "points": int, "wins": int} }
guild_game_scores: dict[int, dict[str, dict]] = {}

# Sesi game aktif per channel: channel_id -> dict state
active_channel_games: dict[int, dict] = {}

# Riwayat jawaban terakhir per server agar soal tidak monoton/berulang
_recent_game_answers: dict[int, list[str]] = {}

_scores_disk_lock = asyncio.Lock()

GAME_ROUND_TIMEOUT_SEC = 75

GAME_POINTS_BY_MODE: dict[str, int] = {
    "trivia": 15,
    "emoji": 20,
    "riddle": 20,
    "scramble": 15,
}

# Bank soal cadangan berkualitas jika API sedang sibuk
_FALLBACK_TRIVIA: list[dict] = [
    {
        "question": "Planet manakah di Tata Surya yang memiliki rotasi paling cepat (1 hari hanya sekitar 10 jam)?",
        "options": ["Mars", "Jupiter", "Saturnus", "Neptunus"],
        "correct_index": 1,
        "fun_fact": "Jupiter berotasi sekali setiap ~9 jam 55 menit meskipun ukurannya paling raksasa!",
    },
    {
        "question": "Bahasa pemrograman Python dinamai oleh pembuatnya (Guido van Rossum) berdasarkan apa?",
        "options": ["Ular Piton Asia", "Grup komedi Monty Python", "Mitologi Yunani kuno", "Singkatan proyek riset"],
        "correct_index": 1,
        "fun_fact": "Guido sedang membaca naskah acara komedi Inggris 'Monty Python's Flying Circus' saat menamai Python.",
    },
    {
        "question": "Pulau manakah yang merupakan pulau terluas yang sepenuhnya berada di wilayah Indonesia?",
        "options": ["Sumatra", "Sulawesi", "Jawa", "Halmahera"],
        "correct_index": 0,
        "fun_fact": "Kalimantan dan Papua lebih luas secara keseluruhan, tetapi wilayahnya dibagi dengan negara tetangga.",
    },
]

_FALLBACK_EMOJI: list[dict] = [
    {
        "clue_emojis": "🏴‍☠️👒🍖⛵🌊",
        "category": "Anime Populer",
        "answer": "One Piece",
        "aliases": ["onepiece", "luffy"],
        "extra_hint": "Petualangan bajak laut Topi Jerami mencari harta karun legendaris.",
    },
    {
        "clue_emojis": "🕷️🧑🏙️🕸️🔴",
        "category": "Film Superhero",
        "answer": "Spider-Man",
        "aliases": ["spiderman", "manusia laba laba", "peter parker"],
        "extra_hint": "Pahlawan Marvel yang bisa menembakkan jaring di gedung New York.",
    },
    {
        "clue_emojis": "⛏️🟩🧟‍♂️💎🏰",
        "category": "Video Game",
        "answer": "Minecraft",
        "aliases": ["mine craft"],
        "extra_hint": "Game kotak-kotak legendaris tempat menambang berlian dan menghindari Creeper.",
    },
]

_FALLBACK_RIDDLE: list[dict] = [
    {
        "clues": [
            "Aku selalu punya banyak 'gigi' berjejer rapi, tapi aku tidak pernah bisa menggigit atau makan.",
            "Orang-orang memakaiku hampir setiap pagi di depan cermin.",
            "Aku membantu merapikan sesuatu di atas kepalamu.",
        ],
        "category": "Benda Sehari-hari",
        "answer": "Sisir",
        "aliases": ["sisir rambut"],
        "extra_hint": "Dipakai untuk merapikan rambut kusut.",
    },
    {
        "clues": [
            "Semakin banyak kamu mengambil dariku, ukuranku justru semakin besar.",
            "Aku bisa ditemukan di tanah, jalanan, atau bahkan pakaian yang robek.",
            "Jika kamu tidak hati-hati melangkah, kamu bisa terperosok ke dalamku.",
        ],
        "category": "Teka-Teki Logika",
        "answer": "Lubang",
        "aliases": ["lobang"],
        "extra_hint": "Sesuatu yang digali di tanah.",
    },
]

_FALLBACK_SCRAMBLE: list[dict] = [
    {"answer": "MARTABAK", "category": "Kuliner Malam Favorit", "extra_hint": "Sering dibawa saat apel malam Minggu, ada manis & telur."},
    {"answer": "KOMPUTER", "category": "Teknologi", "extra_hint": "Alat elektronik untuk kerja, koding, dan main game."},
    {"answer": "NUSANTARA", "category": "Indonesia", "extra_hint": "Sebutan kepulauan Indonesia dari Sabang sampai Merauke."},
    {"answer": "BEGADANG", "category": "Kebiasaan Malam", "extra_hint": "Tidak tidur sampai larut malam atau subuh."},
]


def load_game_scores_from_disk() -> int:
    """Memuat papan skor mini-game dari data/game_scores.json."""
    if not GAME_SCORES_FILE.exists():
        return 0
    try:
        raw = json.loads(GAME_SCORES_FILE.read_text(encoding="utf-8"))
        for gid_str, users_map in (raw.get("guilds") or {}).items():
            gid = int(gid_str)
            cleaned_users: dict[str, dict] = {}
            for uid_str, udata in (users_map or {}).items():
                pts = int(udata.get("points") or 0)
                wins = int(udata.get("wins") or 0)
                if pts > 0 or wins > 0:
                    cleaned_users[str(uid_str)] = {
                        "name": str(udata.get("name") or "Member")[:40],
                        "points": pts,
                        "wins": wins,
                    }
            if cleaned_users:
                guild_game_scores[gid] = cleaned_users
        return len(guild_game_scores)
    except Exception as exc:
        logger.warning("Gagal memuat %s: %s", GAME_SCORES_FILE, exc)
        return 0


async def save_game_scores_to_disk() -> None:
    """Menyimpan papan skor ke data/game_scores.json secara atomik."""
    async with _scores_disk_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"guilds": {str(gid): umap for gid, umap in guild_game_scores.items()}}
            tmp_file = GAME_SCORES_FILE.with_suffix(".json.tmp")
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_file.write_text, serialized, "utf-8")
            await asyncio.to_thread(os.replace, tmp_file, GAME_SCORES_FILE)
        except Exception as exc:
            logger.error("Gagal menyimpan %s: %s", GAME_SCORES_FILE, exc)


def award_game_points(guild_id: int, user_id: int, display_name: str, points: int) -> tuple[int, int]:
    """Menambahkan poin kemenangan member dan mengembalikan (total_poin_baru, total_menang_baru)."""
    g_map = guild_game_scores.setdefault(int(guild_id), {})
    uid_key = str(int(user_id))
    entry = g_map.get(uid_key) or {"name": display_name[:40], "points": 0, "wins": 0}
    entry["name"] = display_name[:40]
    entry["points"] = int(entry.get("points") or 0) + int(points)
    entry["wins"] = int(entry.get("wins") or 0) + 1
    g_map[uid_key] = entry
    return entry["points"], entry["wins"]


def get_guild_leaderboard(guild_id: int, top_n: int = 10) -> list[dict]:
    """Mengembalikan daftar peringkat teratas di server berdasarkan poin lalu jumlah menang."""
    g_map = guild_game_scores.get(int(guild_id)) or {}
    items = [
        {"user_id": int(uid), "name": d["name"], "points": int(d["points"]), "wins": int(d["wins"])}
        for uid, d in g_map.items()
    ]
    items.sort(key=lambda x: (x["points"], x["wins"]), reverse=True)
    return items[:top_n]


def get_user_rank_info(guild_id: int, user_id: int) -> tuple[int | None, int, int]:
    """Mengembalikan (peringkat_1_based, total_poin, total_menang) milik seorang member."""
    full_board = get_guild_leaderboard(guild_id, top_n=10000)
    for idx, row in enumerate(full_board, start=1):
        if row["user_id"] == int(user_id):
            return idx, row["points"], row["wins"]
    return None, 0, 0


def reset_guild_scores(guild_id: int) -> None:
    guild_game_scores.pop(int(guild_id), None)


def normalize_guess_text(text: str) -> str:
    """Menyeragamkan teks tebakan (huruf kecil, tanpa simbol/tanda hubung ganda) agar pencocokan adil."""
    lowered = (text or "").lower().strip()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def is_matching_guess(user_text: str, valid_answers: list[str]) -> bool:
    """Mengecek apakah pesan member cocok dengan jawaban utama atau daftar alias."""
    norm_user = normalize_guess_text(user_text)
    if not norm_user or len(norm_user) > 80:
        return False

    compact_user = norm_user.replace(" ", "")
    for raw_ans in valid_answers:
        norm_ans = normalize_guess_text(raw_ans)
        if not norm_ans:
            continue
        compact_ans = norm_ans.replace(" ", "")
        if norm_user == norm_ans or compact_user == compact_ans:
            return True
        # Izinkan jika member menulis misal "jawabannya spiderman!" untuk kata >= 4 huruf
        if len(norm_ans) >= 4 and re.search(rf"\b{re.escape(norm_ans)}\b", norm_user):
            return True
    return False


def build_masked_word_hint(answer: str) -> str:
    """Membuat petunjuk huruf sebagian, contoh: 'Spider-Man' -> 'S _ _ d _ _ - M _ n'."""
    chars = list(answer.strip())
    alpha_indices = [i for i, ch in enumerate(chars) if ch.isalnum()]
    reveal_set: set[int] = set()
    if alpha_indices:
        reveal_set.add(alpha_indices[0])
        if len(alpha_indices) >= 5:
            reveal_set.add(alpha_indices[-1])
        if len(alpha_indices) >= 8:
            reveal_set.add(alpha_indices[len(alpha_indices) // 2])

    out: list[str] = []
    for idx, ch in enumerate(chars):
        if not ch.isalnum():
            out.append("  " if ch == " " else ch)
        elif idx in reveal_set:
            out.append(ch.upper())
        else:
            out.append("_")
    return " ".join(out)


def scramble_word(word: str) -> str:
    """Mengacak urutan huruf sebuah kata hingga dipastikan berbeda dari kata aslinya."""
    letters = list(word.upper().strip())
    if len(letters) <= 2:
        return " ".join(letters)
    for _ in range(12):
        shuffled = letters[:]
        random.shuffle(shuffled)
        if shuffled != letters:
            return " ".join(shuffled)
    return " ".join(reversed(letters))


def _record_recent_answer(guild_id: int, answer: str) -> None:
    arr = _recent_game_answers.setdefault(int(guild_id), [])
    arr.append(answer.strip())
    if len(arr) > 20:
        del arr[:-20]


def _extract_json_dict(raw_text: str) -> dict | None:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


async def generate_ai_game_question(
    mode: str,
    guild_id: int,
    *,
    http_session: aiohttp.ClientSession | None = None,
) -> dict:
    """Membuat soal mini-game baru secara dinamis menggunakan Gemini JSON (dilengkapi fallback lokal instan)."""
    avoid_list = _recent_game_answers.get(int(guild_id), [])[-15:]
    avoid_note = (
        f"\nJANGAN gunakan jawaban yang sudah pernah keluar ini: {', '.join(avoid_list)}."
        if avoid_list
        else ""
    )

    if mode == "trivia":
        prompt = (
            "Buat 1 soal kuis trivia seru berbahasa Indonesia (pilih topik acak: pengetahuan umum unik, sains populer, "
            "game populer, film/anime, teknologi, sejarah dunia/Indonesia, atau kuliner Nusantara).\n"
            "Balas HANYA dalam JSON murni dengan format:\n"
            '{"question": "...", "options": ["Pilihan A", "Pilihan B", "Pilihan C", "Pilihan D"], '
            '"correct_index": 0, "fun_fact": "1 kalimat fakta menarik singkat"}'
            f"{avoid_note}"
        )
    elif mode == "emoji":
        prompt = (
            "Buat 1 tebak-tebakan judul populer dari rangkaian 4–5 emoji kreatif (pilih kategori acak: Film terkenal, "
            "Video Game populer, Anime populer, Makanan khas Indonesia, atau Karakter ikonik).\n"
            "Balas HANYA dalam JSON murni dengan format:\n"
            '{"clue_emojis": "Emoji1Emoji2Emoji3Emoji4", "category": "...", "answer": "Judul Utama", '
            '"aliases": ["variasi ejaan 1", "variasi ejaan 2"], "extra_hint": "1 kalimat petunjuk tanpa menyebut jawaban"}'
            f"{avoid_note}"
        )
    elif mode == "riddle":
        prompt = (
            "Buat 1 permainan 'Siapakah/Apakah Aku?' berbahasa Indonesia dengan 3 petunjuk bertingkat yang cerdas dan seru "
            "(jawaban berupa 1–2 kata benda sehari-hari, hewan, profesi, tempat terkenal, atau makanan populer).\n"
            "Balas HANYA dalam JSON murni dengan format:\n"
            '{"clues": ["Petunjuk 1...", "Petunjuk 2...", "Petunjuk 3..."], "category": "...", '
            '"answer": "Kata Jawaban", "aliases": ["sinonim jika ada"], "extra_hint": "Petunjuk tambahan singkat"}'
            f"{avoid_note}"
        )
    else:  # scramble
        prompt = (
            "Pilih 1 kata benda/istilah populer Bahasa Indonesia (1 kata tunggal tanpa spasi, panjang 6–9 huruf, "
            "mudah dikenal anak tongkrongan Discord) untuk permainan susun huruf acak.\n"
            "Balas HANYA dalam JSON murni dengan format:\n"
            '{"answer": "KATAJAWABAN", "category": "...", "extra_hint": "1 kalimat petunjuk arti katanya"}'
            f"{avoid_note}"
        )

    if is_gemini_key_configured():
        active_keys = get_gemini_keys_rotated()
        models = _build_model_chain(GEMINI_DEFAULT_MODEL, GEMINI_TEXT_FALLBACK_CHAIN)
        async with _borrow_session(http_session, FAST_TEXT_TIMEOUT) as session:
            for idx, model_id in enumerate(models[:2]):
                gen_cfg: dict = {
                    "temperature": 0.9,
                    "maxOutputTokens": 1024,
                    "responseMimeType": "application/json",
                }
                t_cfg = build_thinking_config(model_id, "minimal")
                if t_cfg:
                    gen_cfg["thinkingConfig"] = t_cfg
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": gen_cfg,
                }
                url = f"{GEMINI_API_BASE}/{model_id}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": active_keys[idx % len(active_keys)],
                }
                try:
                    async with session.post(url, headers=headers, json=payload, timeout=FAST_TEXT_TIMEOUT) as resp:
                        data = await resp.json(content_type=None)
                        if resp.status == 200 and isinstance(data, dict):
                            raw_txt, _, _ = _extract_text_from_gemini_response(data)
                            parsed = _extract_json_dict(raw_txt or "") if raw_txt else None
                            if parsed and _validate_game_payload(mode, parsed):
                                ans_str = (
                                    parsed["options"][parsed["correct_index"]]
                                    if mode == "trivia"
                                    else str(parsed["answer"])
                                )
                                _record_recent_answer(guild_id, ans_str)
                                return parsed
                        elif resp.status in (500, 502, 503, 504):
                            mark_model_unhealthy(model_id)
                except Exception as exc:
                    logger.debug("Fallback game lokal karena API (%s): %s", model_id, sanitize_error_message(exc))

    # Fallback instan lokal jika API sedang sibuk
    if mode == "trivia":
        return random.choice(_FALLBACK_TRIVIA).copy()
    if mode == "emoji":
        return random.choice(_FALLBACK_EMOJI).copy()
    if mode == "riddle":
        return random.choice(_FALLBACK_RIDDLE).copy()
    return random.choice(_FALLBACK_SCRAMBLE).copy()


def _validate_game_payload(mode: str, data: dict) -> bool:
    if mode == "trivia":
        opts = data.get("options")
        c_idx = data.get("correct_index")
        return (
            bool(data.get("question"))
            and isinstance(opts, list)
            and len(opts) == 4
            and isinstance(c_idx, int)
            and 0 <= c_idx <= 3
        )
    if mode == "emoji":
        return bool(data.get("clue_emojis")) and bool(data.get("answer"))
    if mode == "riddle":
        clues = data.get("clues")
        return isinstance(clues, list) and len(clues) >= 2 and bool(data.get("answer"))
    if mode == "scramble":
        ans = str(data.get("answer") or "").strip()
        return ans.isalpha() and 4 <= len(ans) <= 14
    return False


# ==============================================================================
# KOMPONEN TOMBOL INTERAKTIF MINI-GAME DISCORD
# ==============================================================================
class TriviaButtonsView(discord.ui.View):
    """View 4 tombol pilihan ganda A/B/C/D untuk mode Kuis Trivia Cepat."""

    def __init__(self, channel_id: int, guild_id: int, q_data: dict, points: int):
        super().__init__(timeout=GAME_ROUND_TIMEOUT_SEC)
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.q_data = q_data
        self.points = points
        self.attempted_users: set[int] = set()
        self.finished = False
        self.message: discord.Message | None = None

        labels = ("A", "B", "C", "D")
        for idx, letter in enumerate(labels):
            btn = discord.ui.Button(
                label=f"{letter}. {str(q_data['options'][idx])[:70]}",
                style=discord.ButtonStyle.primary,
            )
            btn.callback = self._make_choice_callback(idx, letter)
            self.add_item(btn)

    def _make_choice_callback(self, choice_idx: int, letter: str):
        async def _callback(interaction: discord.Interaction):
            if self.finished:
                await interaction.response.send_message("⏳ Ronde kuis ini sudah selesai!", ephemeral=True)
                return

            if interaction.user.id in self.attempted_users:
                await interaction.response.send_message(
                    "⚠️ Kamu sudah menggunakan 1 kesempatan menebak di soal ini! Tunggu soal berikutnya ya.",
                    ephemeral=True,
                )
                return

            self.attempted_users.add(interaction.user.id)
            correct_idx = int(self.q_data["correct_index"])

            if choice_idx != correct_idx:
                await interaction.response.send_message(
                    f"❌ Pilihan **{letter}** belum tepat! Kesempatan beralih ke teman-teman lain.",
                    ephemeral=True,
                )
                return

            # JAWABAN BENAR!
            self.finished = True
            active_channel_games.pop(self.channel_id, None)
            self.stop()

            total_pts, total_wins = award_game_points(
                self.guild_id,
                interaction.user.id,
                interaction.user.display_name,
                self.points,
            )
            await save_game_scores_to_disk()

            for i, child in enumerate(self.children):
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
                    child.style = (
                        discord.ButtonStyle.success if i == correct_idx else discord.ButtonStyle.secondary
                    )

            ans_text = self.q_data["options"][correct_idx]
            fact = str(self.q_data.get("fun_fact") or "").strip()
            fact_line = f"\n💡 **Tahukah kamu?** {fact}" if fact else ""

            win_embed = discord.Embed(
                title="🏆 JAWABAN BENAR! — Kuis Trivia",
                description=(
                    f"❓ **Soal:** {self.q_data['question']}\n\n"
                    f"✅ **Jawaban:** **{letter}. {ans_text}**\n"
                    f"🎉 Pemenang tercepat: {interaction.user.mention} (**+{self.points} Poin**)\n"
                    f"🏅 Total Skor Kamu: **{total_pts} Poin** ({total_wins}x menang)"
                    f"{fact_line}"
                ),
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=win_embed, view=self)

        return _callback

    async def on_timeout(self) -> None:
        if self.finished:
            return
        self.finished = True
        active_channel_games.pop(self.channel_id, None)
        correct_idx = int(self.q_data["correct_index"])
        letters = ("A", "B", "C", "D")
        for i, child in enumerate(self.children):
            if isinstance(child, discord.ui.Button):
                child.disabled = True
                child.style = (
                    discord.ButtonStyle.success if i == correct_idx else discord.ButtonStyle.secondary
                )
        if self.message:
            try:
                exp_embed = discord.Embed(
                    title="⌛ Waktu Habis! — Kuis Trivia",
                    description=(
                        f"❓ **Soal:** {self.q_data['question']}\n\n"
                        f"🔑 **Jawaban yang benar:** **{letters[correct_idx]}. {self.q_data['options'][correct_idx]}**"
                    ),
                    color=discord.Color.orange(),
                )
                await self.message.edit(embed=exp_embed, view=self)
            except discord.HTTPException:
                pass


class TextGuessControlView(discord.ui.View):
    """Tombol Petunjuk & Menyerah untuk mode tebak ketik di chat (Emoji, Misteri, Acak Kata)."""

    def __init__(self, channel_id: int, starter_id: int):
        super().__init__(timeout=GAME_ROUND_TIMEOUT_SEC)
        self.channel_id = channel_id
        self.starter_id = starter_id

    @discord.ui.button(label="💡 Buka Petunjuk", style=discord.ButtonStyle.secondary)
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = active_channel_games.get(self.channel_id)
        if not state:
            await interaction.response.send_message("⏳ Permainan sudah berakhir.", ephemeral=True)
            return

        masked = build_masked_word_hint(state["answer"])
        extra = state.get("extra_hint") or "Perhatikan petunjuk di atas baik-baik!"
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            f"💡 **Petunjuk Tambahan:** {extra}\n🔤 **Pola Huruf:** `{masked}`",
            ephemeral=False,
        )

    @discord.ui.button(label="🏳️ Menyerah", style=discord.ButtonStyle.danger)
    async def giveup_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = active_channel_games.get(self.channel_id)
        if not state:
            await interaction.response.send_message("⏳ Permainan sudah berakhir.", ephemeral=True)
            return

        is_mod = isinstance(interaction.user, discord.Member) and (
            interaction.user.guild_permissions.administrator
            or interaction.user.guild_permissions.manage_messages
        )
        if interaction.user.id != self.starter_id and not is_mod:
            await interaction.response.send_message(
                "⚠️ Hanya pemulai ronde ini (atau Moderator) yang bisa mengklik Menyerah.",
                ephemeral=True,
            )
            return

        active_channel_games.pop(self.channel_id, None)
        task = state.get("timeout_task")
        if task and not task.done():
            task.cancel()

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            f"🏳️ Ronde dihentikan oleh {interaction.user.mention}! Jawaban yang benar adalah: **`{state['answer']}`**."
        )


async def handle_active_game_guess(message: discord.Message) -> bool:
    """Memeriksa apakah pesan teks di channel merupakan tebakan untuk Mini-Game yang sedang berlangsung.

    Returns:
        True jika pesan ditangani oleh sistem game (tebakan benar atau tebakan pendek selama ronde aktif),
        sehingga Auto-Chat tidak ikut menimpa/membocorkan jawaban.
    """
    state = active_channel_games.get(message.channel.id)
    if not state or state.get("type") == "trivia":
        return False

    content = (message.content or "").strip()
    if not content:
        return False

    valid_list = [state["answer"], *state.get("aliases", [])]
    if is_matching_guess(content, valid_list):
        active_channel_games.pop(message.channel.id, None)
        task = state.get("timeout_task")
        if task and not task.done():
            task.cancel()

        view_obj: discord.ui.View | None = state.get("view")
        msg_obj: discord.Message | None = state.get("message")
        if view_obj and msg_obj:
            for child in view_obj.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            try:
                await msg_obj.edit(view=view_obj)
            except discord.HTTPException:
                pass

        pts = int(state["points"])
        guild_id = message.guild.id if message.guild else 0
        total_pts, total_wins = award_game_points(
            guild_id,
            message.author.id,
            message.author.display_name,
            pts,
        )
        await save_game_scores_to_disk()

        embed = discord.Embed(
            title="🎉 TEBAKAN TEPAT!",
            description=(
                f"🏆 Pemenang: {message.author.mention} (**+{pts} Poin**)\n"
                f"✅ Jawaban: **`{state['answer']}`**\n"
                f"🏅 Total Skor Kamu: **{total_pts} Poin** ({total_wins}x menang)\n"
                f"*(Ketik `/game mulai` untuk lanjut ronde berikutnya atau `/game papan_skor` untuk cek klasemen!)*"
            ),
            color=discord.Color.green(),
        )
        await message.reply(embed=embed, mention_author=False)
        return True

    # Selama ronde tebak kata berjalan, tahan pemicu Auto-Chat untuk tebakan pendek (<= 5 kata)
    # supaya AI Agent tidak keceplosan membocorkan jawaban atau menyela tebakan warga
    if len(content.split()) <= 5 and not message.mentions:
        return True

    return False
