"""Help views — dipisah dari views.py agar berkas tidak membengkak."""

import discord
from config import BOT_VERSION
import ui_kit


def build_help_embed(category: str = "overview") -> discord.Embed:
    """Menyusun Embed panduan `/bantuan` yang rapi & terstruktur sesuai kategori pilihan."""
    if category == "sesi":
        embed = discord.Embed(
            title="🔒 Ruang AI Privat, Multimodal & Gambar (`/sesi`)",
            description=(
                "Buka ruang konsultasi pribadi (`Private Thread`) yang rapi tanpa mengganggu chat umum:"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="💬 Ruang Chat Teks & Multimodal (`ai-...`)",
            value=(
                "• Klik tombol **💬 Chat AI** pada panel (dipasang Admin via `/sesi panel`).\n"
                "• Pilih **5 Mode Kepribadian:** *Asisten Utama, Respon Kilat, Pakar Koding, Penalaran & Riset,* atau *Teman Curhat*.\n"
                "• Kirim **Voice Note (`🎤`)**, dokumen **`.pdf`**, foto/screenshot error, file kode (`.py`, `.js`, dll), stiker, hingga link **YouTube & artikel web**!"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎨 Studio Generate & Edit Gambar (`draw-...`)",
            value=(
                "• Klik tombol **🎨 Generate Gambar AI** pada panel utama.\n"
                "• Pilih **7 Gaya Art** *(Anime, Cyberpunk, Realistis, 3D, Pixel Art, Lukisan)* & **5 Ukuran Rasio**.\n"
                "• Lampirkan foto + instruksi teks untuk mengedit gambar secara instan."
            ),
            inline=False,
        )
        embed.add_field(
            name="⌨️ Daftar Command `/sesi`",
            value=(
                "• `/sesi panel` *(Admin)* — Pasang panel tombol ruang AI di channel.\n"
                "• `/sesi model` — Ganti kepribadian Gemini di ruang chat aktif.\n"
                "• `/sesi reset` — Bersihkan riwayat memori / reset setelan gambar.\n"
                "• `/sesi tutup` — Akhiri sesi & kirim transkrip lengkap ke DM Anda."
            ),
            inline=False,
        )
    elif category == "tools":
        embed = discord.Embed(
            title="🔎 Ringkas Pintar, Cari Berita & Klik-Kanan Pesan",
            description="Alat bantu AI instan yang bisa dipakai langsung tanpa keluar dari obrolan:",
            color=discord.Color.teal(),
        )
        embed.add_field(
            name="📝 Perangkum Obrolan & Link (`/ringkas`)",
            value=(
                "• `/ringkas chat` — Rangkum inti 25–150 pesan terakhir di channel/thread agar tidak ketinggalan topik (TL;DR).\n"
                "• `/ringkas link` — Rangkum isi **video YouTube** (`watch` / `youtu.be` / `Shorts`) atau **artikel web**, lengkap dengan tanya-jawab isi video!"
            ),
            inline=False,
        )
        embed.add_field(
            name="🌐 Pencarian Fakta & Berita Hari Ini (`/cari`)",
            value=(
                "• `/cari pertanyaan:...` — Cek berita terkini, skor pertandingan, cuaca, rilis teknologi, atau fakta terbaru hari ini lengkap dengan tautan sumber."
            ),
            inline=False,
        )
        embed.add_field(
            name="📲 Menu Tekan-Tahan / Klik-Kanan Pesan (Tanpa Ketik!)",
            value=(
                "Tekan-tahan pesan siapa saja di HP *(atau Klik Kanan di PC)* ➔ **Apps**:\n"
                "• **`🌐 Terjemahkan ke Indonesia`** — Terjemahkan pesan bahasa asing secara natural.\n"
                "• **`/terjemah`** — Terjemahkan teks/pesan ke Indonesia/Inggris, atau pasang **reaksi bendera 🇮🇩/🇬🇧** "
                "di channel (0 kuota sampai diminta, hasil via DM).\n"
                "• **`💡 Jelaskan Pesan Ini`** — Bedah maksud istilah rumit, kode error, atau gambar.\n"
                "• **`🔍 Cek Fakta / Hoaks`** — Periksa kebenaran klaim/berita berantai dengan sumber web."
            ),
            inline=False,
        )
    elif category == "games":
        embed = discord.Embed(
            title="🎮 6 Mode Mini-Game Tongkrongan & Papan Skor (`/game`)",
            description="Seru-seruan bareng warga server dan kejar posisi juara di klasemen!",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🕹️ Pilihan Mode Permainan (`/game mulai`)",
            value=(
                "• **🎭 Tebak dari Emoji** (`+20 Poin`) — Tebak film, game, makanan, atau benda dari rangkaian emoji.\n"
                "• **🖼️ Tebak Gambar AI** (`+25 Poin`) — Tebak objek dari ilustrasi misterius buatan AI langsung di chat!\n"
                "• **⛓️ Sambung Kata Indonesia** (`+5 Poin/Kata`) — Adu cepat sambung kata dari huruf terakhir beramai-ramai!\n"
                "• **🧠 Kuis Trivia Cepat A/B/C/D** (`+15 Poin`) — Adu cepat klik tombol pilihan ganda.\n"
                "• **🕵️ Tebak Kata Misteri** (`+20 Poin`) — 3 petunjuk bertahap *Siapakah/Apakah Aku?*.\n"
                "• **🔀 Susun Huruf Acak** (`+15 Poin`) — Susun huruf teracak menjadi kata yang tepat."
            ),
            inline=False,
        )
        embed.add_field(
            name="🏆 Command Klasemen & Kontrol",
            value=(
                "• `/game mulai` — Mulai ronde (kosongkan `jenis` untuk mode kejutan acak!).\n"
                "• `/game papan_skor` — Lihat Top 10 juara server & peringkatmu.\n"
                "• `/game stop` — Hentikan ronde yang sedang berjalan.\n"
                "• `/game reset_skor` *(Admin)* — Reset klasemen untuk musim kompetisi baru."
            ),
            inline=False,
        )
    elif category == "server":
        embed = discord.Embed(
            title="🛠️ Fitur Server: Statistik, Auto Role, Fakta & Anti-Phishing",
            description="Perkakas pengelolaan server yang berjalan otomatis 24/7:",
            color=discord.Color.dark_teal(),
        )
        embed.add_field(
            name="📊 Statistik Server (`/serverstats`)",
            value=(
                "• `/serverstats lihat` — Kartu statistik lengkap: anggota, manusia/bot, boost, channel, role, emoji, & tanggal server dibuat.\n"
                "• `/serverstats otomatis` *(Admin)* — Membuat **Voice Channel penghitung** (👥 Total Member, 🙋 Manusia, 🤖 Bot, 🟢 Online, 💎 Boost) yang ter-update otomatis tiap ±10 menit.\n"
                "• `/serverstats ikon` *(Admin)* — Ganti/hapus emoji ikon tiap channel (isi `-` untuk tanpa ikon) & nama kategorinya.\n"
                "• `/serverstats tipe` *(Admin)* — Pilih jenis channel counter: `voice` 🔊, `text` #️⃣, `announcement` 📢, atau `stage` 🎤. Ikon di kiri nama channel mengikuti tipe ini."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎭 Role Otomatis (`/autorole`) *(Admin)*",
            value=(
                "• `/autorole atur role:@Member` — Member baru langsung mendapat role tanpa verifikasi manual (bisa sampai 3 role).\n"
                "• `/autorole status` — Cek daftar role & peringatan jika posisi role bot terlalu rendah.\n"
                "• `/autorole isi` — Berikan Auto Role ke member lama yang belum punya (maks. 150 member)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🌍 Fakta Unik Dunia (`/fakta`)",
            value=(
                "• `/fakta atur channel:#umum jadwal:08:00,12:00,16:00,20:00` — Rubrik **3–4 fakta menarik dari negara berbeda**, dikirim **4x sehari** (pagi, siang, sore, malam).\n"
                "• **Jadwal fleksibel:** Admin bebas mengubah slot kapan saja (1x, 2x, 3x, hingga 6x sehari).\n"
                "• `/fakta sekarang` — Kirim contoh fakta saat ini juga (tanpa mengubah jadwal).\n"
                "• `/fakta status` — Lihat seluruh slot, slot berikutnya, & slot yang sudah terkirim hari ini."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Anti-Phishing (`/keamanan`)",
            value=(
                "• `/keamanan phising` *(Admin)* — Aktifkan penjaga link: hapus link berbahaya + peringatan + catatan log moderator.\n"
                "• `/keamanan cek link:...` — Periksa keamanan link sebelum dibuka (bisa semua member).\n"
                "• Deteksi lokal gratis: tiruan brand (Discord/Steam/dll), punycode `xn--`, IP langsung, TLD berisiko, pemendek URL, & daftar hitam phishing."
            ),
            inline=False,
        )
        embed.add_field(
            name="🚨 Anti-Spam & Anti-Raid (`/keamanan spam`)",
            value=(
                "• `/keamanan spam aktif:True` — **mode awalnya hanya *lapor*** ke channel log, "
                "tidak ada pesan yang dihapus.\n"
                "• `/keamanan spam mode:hapus log_channel:#mod-log` — hapus pesan spam otomatis.\n"
                "• `/keamanan spam mode:timeout timeout_detik:600` — hapus + time-out sementara.\n"
                "• `/keamanan spam-status` — lihat ambang deteksi, pengecualian, & jumlah tindakan.\n"
                "• Deteksi lokal: banjir pesan, pesan berulang, mention massal, link beruntun, "
                "& HURUF KAPITAL (opsional). **Admin, staf, & role pengecualian tidak pernah diperiksa.**\n"
                "• **Anti-Raid:** lonjakan member join hanya memicu *peringatan* ke channel log — "
                "tidak pernah menendang atau mem-ban otomatis."
            ),
            inline=False,
        )
        embed.add_field(
            name="🧰 Perkakas Server (`/afk`, `/thread-otomatis`, `/lockdown`, `/backup`)",
            value=(
                "• `/afk atur alasan:sekolah` — mention kepadamu dijawab otomatis; status lepas saat kamu bicara.\n"
                "• `/thread-otomatis aktifkan arsip_menit:1440` *(Admin)* — tiap pesan baru dibuatkan thread.\n"
                "• `/lockdown aktif:True alasan:raid` *(Admin)* — kunci semua text channel; "
                "`aktif:False` membuka hanya channel yang dikunci bot.\n"
                "• `/backup struktur` *(Admin)* — unduh JSON role/kategori/channel/izin (baca-saja, tanpa isi pesan)."
            ),
            inline=False,
        )
    elif category == "komunitas":
        embed = discord.Embed(
            title="🧩 Fitur Komunitas Ringan (Gratis, Tanpa Kuota AI)",
            description=(
                "Semua fitur di bawah ini **default NONAKTIF** dan hanya aktif setelah Admin menyalakannya. "
                "Tidak memakai kuota Gemini sama sekali, jadi aman dipakai 24 jam."
            ),
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="🎭 Reaction Role (`/panel-role`)",
            value=(
                "• `/panel-role pasang channel:#ambil-role judul:Ambil Role role1:@Gamer emoji1:🎮` — member klik emoji untuk mengambil role sendiri.\n"
                "• `/panel-role tambah` & `/panel-role hapus` — kelola role pada panel yang sudah ada.\n"
                "• `/panel-role daftar` — lihat seluruh panel di server ini."
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Polling & Pengingat (`/poll`, `/ingatkan`)",
            value=(
                "• `/poll pertanyaan:... opsi:Jam 8, Jam 9, Jam 10` — polling native Discord, suara dihitung otomatis.\n"
                "• `/ingatkan pasang waktu:2j pesan:mabar` — bot mengingatkan kamu saat waktunya tiba (tahan restart).\n"
                "• `/ingatkan daftar` & `/ingatkan batal nomor:3` — kelola pengingat aktifmu."
            ),
            inline=False,
        )
        embed.add_field(
            name="⭐ Starboard (`/starboard`)",
            value=(
                "• `/starboard atur channel:#starboard batas:3` — pesan yang mendapat 3 bintang otomatis disalin ke channel sorotan.\n"
                "• `/starboard status` — lihat konfigurasi & jumlah pesan tersorot."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Verifikasi & Sticky (`/verifikasi`, `/sticky`)",
            value=(
                "• `/verifikasi pasang channel:#verifikasi role:@Member` — member baru klik **✅ Verifikasi Saya** untuk membuka akses.\n"
                "• `/sticky pasang isi:... channel:#umum` — pesan petunjuk yang otomatis tetap di bawah channel."
            ),
            inline=False,
        )
        embed.add_field(
            name="💡 Kotak Saran & 📝 Pembuat Embed (`/saran`, `/embed`)",
            value=(
                "• `/saran pasang channel:#saran` *(Admin)* lalu member memakai `/saran kirim teks:...`.\n"
                "• Saran tampil dengan tombol **👍/👎** (tahan restart), satu member satu suara.\n"
                "• `/saran status id:3 status:diterima` *(Staff)* — pengusul otomatis diberi tahu.\n"
                "• `/embed buat channel:#pengumuman` — formulir pengumuman; `/embed cepat` untuk kirim langsung.\n"
                "• Warna: `#9B59B6`, `ungu`, `biru`, `merah`, `hijau`, `emas`, `abu`. **0 kuota AI.**"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔔 Notifikasi Sosial (`/sosial`)",
            value=(
                "• `/sosial tambah platform:🎬 YouTube target:@NamaChannel channel:#info` — beri tahu warga "
                "tiap ada video baru (pakai RSS YouTube, **tanpa API key**).\n"
                "• `/sosial tambah platform:🟣 Twitch target:ninja channel:#live` — notifikasi saat streamer "
                "**mulai live** (butuh `TWITCH_CLIENT_ID` & `TWITCH_CLIENT_SECRET`).\n"
                "• `/sosial tambah platform:🎵 TikTok target:<URL feed RSS>` — TikTok tidak punya API feed "
                "gratis resmi, jadi dipakai jalur RSS.\n"
                "• `/sosial daftar`, `/sosial hapus id:...`, `/sosial tes id:...` — kelola & uji langganan.\n"
                "• `/sosial status` — cek kredensial Twitch & token (sekalian panduan mengisinya).\n"
                "• Semua pesan memakai template → **0 kuota AI**."
            ),
            inline=False,
        )
        embed.add_field(
            name="👤 Profil & Perawatan (`/info`, `/perawatan`)",
            value=(
                "• `/info user` & `/info server` — kartu profil member (umur akun & tanggal join) dan ringkasan server.\n"
                "• `/perawatan atur backup_channel:#bot-backup log_channel:#bot-log` — backup konfigurasi otomatis tiap 7 hari.\n"
                "• `/perawatan backup` — kirim berkas backup sekarang; `/perawatan status` — cek ukuran data & RAM."
            ),
            inline=False,
        )
    elif category == "growth":
        embed = discord.Embed(
            title="📈 Level & 🎟️ Tiket Dukungan",
            description=(
                "Dua fitur **retensi & pelayanan** yang berjalan **tanpa kuota Gemini** dan "
                "**default NONAKTIF** sampai Admin menyalakannya."
            ),
            color=discord.Color.teal(),
        )
        embed.add_field(
            name="📈 Leveling & XP (`/level`)",
            value=(
                "• `/level lihat [member]` — kartu level + progress bar XP.\n"
                "• `/level papan halaman:1` — papan peringkat 10 besar server.\n"
                "• `/level atur aktif:True jeda:60 xp_minimal:15 xp_maksimal:25` *(Admin)*.\n"
                "• `/level role level:5 role:@Aktif` *(Admin)* — hadiah role otomatis.\n"
                "• `/level status` — statistik & konfigurasi leveling.\n"
                "• XP dibatasi jeda (default 60 detik) & bisa dikecualikan per channel/role."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎟️ Tiket Dukungan (`/tiket`)",
            value=(
                "• `/tiket panel channel:#bantuan staff_role:@Staf log_channel:#log-tiket` *(Admin)*.\n"
                "• Member klik **🎟️ Buat Tiket** → bot membuat **private thread** "
                "(tidak memakai slot channel server).\n"
                "• Staf memakai tombol **🙋 Klaim** & **🔒 Tutup Tiket** di dalam thread.\n"
                "• `/tiket daftar` / `/tiket tambah member:@X` / `/tiket status` / `/tiket matikan`.\n"
                "• Transkrip `.txt` otomatis dikirim ke channel log saat tiket ditutup."
            ),
            inline=False,
        )
        embed.set_footer(text="Data: data/levels.json & data/tickets.json • tanpa database eksternal")
    elif category == "insights":
        embed = discord.Embed(
            title="📊 Hemat Kuota AI: Pemakaian, Rekap & FAQ",
            description=(
                "Tiga fitur yang membuat bot tetap pintar **tanpa menghabiskan kuota Gemini** "
                "gratisan. Semua perintah di bawah **tidak memanggil AI** (0 kuota)."
            ),
            color=discord.Color.dark_teal(),
        )
        embed.add_field(
            name="📊 Pemakaian AI (`/pemakaian`)",
            value=(
                "• `/pemakaian lihat` — operasi AI hari ini: jenis, member teraktif, channel tersibuk, "
                "**total token**, **kuota server**, & **penghematan** (FAQ lokal + cache jawaban).\n"
                "• `/pemakaian tren hari:7` — grafik tren harian (total vs cache hit).\n"
                "• `/pemakaian status` — ringkasan penghematan: cache rekap, FAQ lokal, & batas harian.\n"
                "• Contoh isi: `Chat 34`, `Cari 5`, `Rekap 2`, `Cache hit 12`, `Token 48.210`."
            ),
            inline=False,
        )
        embed.add_field(
            name="♻️ Rekap Channel Ber-cache (`/ringkas channel`)",
            value=(
                "• `/ringkas channel periode:6 jam terakhir` — rekap obrolan per rentang waktu.\n"
                "• Hasil disimpan **30 menit**; meminta ulang periode yang sama = **0 kuota** (dari cache).\n"
                "• Butuh rekap baru? Tambahkan `paksa:True` (baru memakai AI).\n"
                "• Periode: 1j, 3j, 6j, 12j, 24j, 7h • maksimal 400 pesan dianalisis "
                "(atur lewat `REKAP_MAX_MESSAGES`)."
            ),
            inline=False,
        )
        embed.add_field(
            name="📚 FAQ Server (`/faq`)",
            value=(
                "• `/faq tanya pertanyaan:...` — jawaban dicari **lokal** (tanpa AI) dari basis FAQ server.\n"
                "• `/faq daftar` — semua entri FAQ/Info server.\n"
                "• `/faq tambah topik:... isi:...` *(Admin)* — entri baru; ikut jadi konteks resmi AI.\n"
                "• `/faq hapus target:2` *(Admin)* — hapus berdasarkan nomor urut atau nama topik.\n"
                "• Jalur termurah: arahkan member bertanya info server lewat `/faq tanya` dulu."
            ),
            inline=False,
        )
        embed.add_field(
            name="💡 Urutan Hemat Kuota",
            value=(
                "1️⃣ `/faq tanya` (0 kuota) → 2️⃣ `/ringkas channel` berulang (cache, 0 kuota) → "
                "3️⃣ `/cari` & `/ringkas link` (1 panggilan) → 4️⃣ obrolan AI di ruang `/sesi` bila perlu.\n"
                "Admin bisa membatasi operasi AI per member per hari lewat variabel `.env` "
                "`AI_DAILY_CAP_PER_USER` (0 = tanpa batas; Admin server selalu dikecualikan)."
            ),
            inline=False,
        )
        embed.set_footer(text="Data: data/ai_usage.json (dipangkas otomatis) • tanpa database eksternal")
    elif category == "engagement":
        embed = discord.Embed(
            title="🎉 Giveaway, Ulang Tahun, Auto-Responder & Pengumuman",
            description=(
                "Fitur **keramaian server** yang berjalan **tanpa kuota Gemini** sama sekali "
                "(0 request AI). Semua default NONAKTIF sampai Admin menyalakannya."
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🎁 Giveaway (`/giveaway`)",
            value=(
                "• `/giveaway mulai hadiah:Nitro 1 Bulan durasi:2jam pemenang:3` — tombol **🎉 Ikuti Giveaway** "
                "dipasang otomatis.\n"
                "• `/giveaway akhiri id_pesan:...` — tutup lebih awal & umumkan pemenang.\n"
                "• `/giveaway reroll id_pesan:...` — undi ulang dari peserta yang belum menang.\n"
                "• `/giveaway daftar` — giveaway yang masih berjalan + riwayat pemenang.\n"
                "• Bisa dibatasi role: `syarat_role:@Booster`."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎂 Ulang Tahun (`/ultah`)",
            value=(
                "• `/ultah set tanggal:12-08` — daftarkan tanggal lahir (boleh `12/8/2000` atau `12 Agustus`).\n"
                "• `/ultah daftar bulan:8` — lihat daftar ulang tahun member.\n"
                "• `/ultah hapus` — hapus data sendiri kapan saja.\n"
                "• `/ultah atur channel:#umum jam:08:00` *(Admin)* — ucapan otomatis tiap hari."
            ),
            inline=False,
        )
        embed.add_field(
            name="🤖 Balasan Otomatis (`/jawab-otomatis`)",
            value=(
                "• `/jawab-otomatis tambah pemicu:cara daftar balasan:...` — bot menjawab saat kata kunci muncul.\n"
                "• `/jawab-otomatis daftar` / `hapus pemicu:...` — kelola aturan per channel.\n"
                "• `/jawab-otomatis atur aktif:False jeda:30` — matikan sementara & atur jeda aman.\n"
                "• Aman untuk obrolan: hanya aktif di channel yang dipilih, ada jeda antar-balasan."
            ),
            inline=False,
        )
        embed.add_field(
            name="📢 Pengumuman Terjadwal (`/pengumuman`)",
            value=(
                "• `/pengumuman tambah isi:... jadwal:08:00` — setiap hari.\n"
                "• `/pengumuman tambah isi:... jadwal:senin 19:00` — setiap minggu.\n"
                "• `/pengumuman tambah isi:... jadwal:sekali 31-12-2026 23:59` — sekali saja.\n"
                "• `/pengumuman daftar` / `hapus id:3` / `atur id:3 aktif:False` — kelola jadwal."
            ),
            inline=False,
        )
        embed.set_footer(text="Semua data disimpan lokal di data/engagement.json — tanpa database eksternal.")
    elif category == "musik":
        embed = discord.Embed(
            title="🎵 Streaming Musik 24/7 (`/musik`) — Lavalink",
            description=(
                "Putar lagu dari **YouTube, Spotify, SoundCloud, Apple Music**, dan lainnya tanpa membebani "
                "server bot (audio diproses node Lavalink, bukan CPU bot)."
            ),
            color=discord.Color.dark_purple(),
        )
        embed.add_field(
            name="▶️ Memutar Lagu",
            value=(
                "• `/musik putar query:judul lagu` — cari & langsung putar (bot join voice channel kamu).\n"
                "• `/musik putar query:https://youtu.be/xxxx` — tempel tautan YouTube/Spotify/playlist.\n"
                "• `/musik cari query:...` — lihat 5 hasil lalu pilih dari dropdown.\n"
                "• `/musik putar query:... berikutnya:True` — selalu antrekan tanpa memotong lagu berjalan."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎛️ Kontrol Pemutaran",
            value=(
                "• `/musik sekarang` — lagu aktif + progres bar & volume.\n"
                "• `/musik antrean halaman:2` — antrean berhalaman (◀ ▶), 10 lagu/halaman.\n"
                "• `/musik jeda` / `/musik lanjut` — jeda & lanjutkan.\n"
                "• `/musik lewati jumlah:2` — lewati lagu (bisa beberapa sekaligus).\n"
                "• `/musik sebelumnya` — putar lagi lagu sebelumnya dari riwayat.\n"
                "• `/musik seek posisi:1:30` — lompat ke menit/detik tertentu.\n"
                "• `/musik acak` — acak antrean, `/musik ulang mode:satu|semua|mati`.\n"
                "• `/musik volume level:70` — atur volume (disimpan sebagai default server).\n"
                "• `/musik hentikan` — stop, kosongkan antrean, & keluar dari voice."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎚️ Panel Ala Rythm + Efek Audio",
            value=(
                "• Panel pemutar **satu pesan** muncul otomatis saat memutar lagu: progress bar "
                "`▬▬🔘▬▬` yang bergerak tiap ±10 detik + **9 tombol** "
                "(⏯️ ⏭️ ⏮️ ⏹️ 📜 🔁 🔀 🔉 🔊).\n"
                "• `/musik panel` — kirim ulang panel bila pesan lamanya terhapus.\n"
                "• `/musik filter jenis:bassboost|nightcore|vaporwave|8d|karaoke|treble|off`.\n"
                "• `/musik autoplay aktif:True` — putar rekomendasi otomatis saat antrean habis.\n"
                "• Filter & autoplay **tersimpan per server** dan dipulihkan saat bot join lagi."
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Admin, Status & Diagnosa Node",
            value=(
                "• `/musik status` — kondisi **nyata** node Lavalink (✅ Tersambung / ⏳ Menyambung / "
                "⚠️ Belum tersambung), antrean, volume, & role DJ.\n"
                "• `/musik node sambung:True` *(Admin)* — diagnosa per node + **sambung ulang tanpa restart**.\n"
                "• `/musik pengaturan` — pengumuman Now Playing, role DJ, & volume default.\n"
                "• **Role DJ bukan syarat memutar lagu** — cukup masuk voice channel. DJ hanya mengunci "
                "tombol kontrol untuk member di luar VC.\n"
                "• Butuh **Lavalink v4** (`LAVALINK_URI` + `LAVALINK_PASSWORD`). Troubleshooting lengkap ada di README bagian F."
            ),
            inline=False,
        )
        embed.add_field(
            name="🔊 Voice Room Sementara (`/tempvoice`)",
            value=(
                "• Admin: buat voice channel **➕ Buat Voice**, lalu `/tempvoice atur hub:#➕ Buat Voice`.\n"
                "• Member masuk hub → langsung dapat room sendiri & jadi pemiliknya.\n"
                "• Pemilik room: `/tempvoice kunci`, `/tempvoice nama`, `/tempvoice limit`, `/tempvoice tendang`.\n"
                "• Room terhapus otomatis saat kosong (maks 30 room/server, aman restart)."
            ),
            inline=False,
        )
    elif category == "admin":
        embed = discord.Embed(
            title="⚙️ Panduan Admin & AI Komunitas (`/agent`)",
            description="Atur seluruh fitur AI per-channel maupun Forum secara fleksibel:",
            color=discord.Color.brand_green(),
        )
        embed.add_field(
            name="🎛️ Panel Klik-Tombol & Status",
            value=(
                "• **`/agent panel`** — **Paling Praktis!** Pilih channel/forum lewat dropdown lalu klik ON/OFF fitur, ubah persona, & kelola FAQ tanpa hafal command.\n"
                "• `/agent status` — Lihat ringkasan lengkap seluruh channel aktif & hitung mundur pemecah sepi.\n"
                "• **`/panel`** — Pantau semua modul (AI, Server, Komunitas, Musik, Kuota) dalam satu dashboard.\n"
                "• **`/tampilan atur`** — Kustomisasi warna aksen, emoji, kepadatan, thumbnail, & footer panel."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderasi Bercatatan (`/mod`)",
            value=(
                "• `/mod warn member:@x alasan:...` — peringatan tercatat; 3 warn dalam 30 hari → "
                "**timeout otomatis 1 jam** (bisa diatur).\n"
                "• `/mod timeout member:@x durasi:1h30m` • `/mod kick` • `/mod ban hapus_pesan_hari:1` • "
                "`/mod unban user_id:...`\n"
                "• `/mod purge jumlah:50 tipe:link` — hapus massal (semua/bot/link/gambar).\n"
                "• `/mod catatan member:@x` — riwayat kasus & jumlah peringatan aktif.\n"
                "• `/mod atur log_channel:#mod-log ambang_warn:3 durasi_auto:1h dm:True` — pengaturan."
            ),
            inline=False,
        )
        embed.add_field(
            name="🖼️ Sambutan Bergambar & Boost (`/agent banner`)",
            value=(
                "• `/agent banner gambar:<file> jenis:...` — unggah banner sambutan / perpisahan / boost "
                "(maks 8 MB, disimpan di `data/media/` agar tidak kedaluwarsa).\n"
                "• `/agent kartu mode:...` — tampilan sambutan: **teks**, **banner statis**, atau "
                "**kartu dinamis** (foto profil bulat + nama + jumlah member).\n"
                "• `/agent dm aktif:True` — kirim juga salinan sambutan lewat DM.\n"
                "• `/agent boost channel:#umum` — pesan terima kasih otomatis saat ada member nge-boost "
                "server (dukungan `{user}`, `{name}`, `{guild}`)."
            ),
            inline=False,
        )
        embed.add_field(
            name="📡 Pengaturan Fitur Per-Channel & Forum",
            value=(
                "• `/agent chat` — Auto-Chat natural, Pemecah Sepi otomatis, & penjawab **Forum Post** lengkap dengan **Auto-Tag** + tombol **`✅ Tandai Selesai`**.\n"
                "• `/agent gallery` — Komentar apresiasi visual otomatis pada foto/video karya warga.\n"
                "• `/agent youtube` & `/agent cari` — Aktifkan perangkum link & pencarian berita di channel/forum pilihan.\n"
                "• `/agent welcome` — Sambutan member baru dengan **persona khusus** (Hangat / Lucu / Santai / Normal) + kata sapaan Asia yang berganti-ganti.\n"
                "• `/agent goodbye` — Kartu perpisahan hangat saat member keluar, plus masa kebersamaan.\n"

                "• `/agent digest` — Kirim **Koran & Sapaan Pagi** terjadwal setiap hari.\n"
                "• `/agent info` & `/agent persona` — Simpan memori FAQ resmi server & gaya bahasa AI."
            ),
            inline=False,
        )
    else:
        embed = discord.Embed(
            title=f"📚 Pusat Panduan Bot Gemini AI (`v{BOT_VERSION}`)",
            description=(
                "Semua fitur telah disusun rapi agar mudah dipakai seluruh member maupun Admin.\n"
                "Pilih **kategori di menu dropdown bawah** untuk melihat detail lengkapnya!"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="⚡ AI, Server & Hiburan (30 Menu Utama)",
            value=(
                "**🤖 AI & Hiburan**\n"
                "• **`/sesi`** — Ruang privat AI: panel, ganti mode, reset, tutup sesi.\n"
                "• **`/ringkas`** — Rangkum obrolan (`chat`), per periode (`channel`), atau link/YouTube (`link`).\n"
                "• **`/cari`** — Cari berita, skor, cuaca, atau info terbaru hari ini.\n"
                "• **`/game`** — 6 mode Mini-Game Tongkrongan & Papan Skor.\n"
                "• **`/musik`** — streaming YouTube/Spotify via Lavalink (putar, antrean, volume, DJ).\n"
                "**🎨 Tampilan & Pusat Kontrol**\n"
                "• **`/panel`** — **Control Center**: kartu status semua modul + pindah tab lewat dropdown.\n"
                "• **`/tampilan`** *(Admin)* — ubah warna aksen, emoji, kepadatan, & branding panel server.\n"
                "**🛠️ Pengelolaan Server**\n"
                "• **`/agent`** *(Admin)* — Panel kontrol AI Agent, Welcome, Goodbye, Digest, & FAQ.\n"
                "• **`/serverstats`** — Statistik server + channel penghitung otomatis.\n"
                "• **`/autorole`**, **`/verifikasi`** *(Admin)* — Role otomatis & gerbang verifikasi.\n"
                "• **`/fakta`** — Fakta Unik Dunia 4x sehari (08/12/16/20).\n"
                "• **`/keamanan`** — Anti-phishing, anti-spam, & cek keamanan link."
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Retensi, Komunitas & Hemat Kuota (Gratis)",
            value=(
                "**📈 Retensi & Pelayanan**\n"
                "• **`/level`** — kartu level, papan peringkat, role hadiah, & XP voice.\n"
                "• **`/tiket`** — tiket bantuan lewat private thread + transkrip.\n"
                "**🎉 Keramaian Server**\n"
                "• **`/giveaway`** — undian berhadiah, **`/ultah`** — ucapan ulang tahun otomatis.\n"
                "• **`/jawab-otomatis`** — balasan kata kunci, **`/pengumuman`** — pengumuman terjadwal.\n"
                "**📊 Hemat Kuota AI**\n"
                "• **`/pemakaian`** — statistik operasi AI, token, kuota server, & penghematan cache.\n"
                "• **Dashboard web** — pantau status & `/pemakaian` dari browser (read-only, 0 kuota).\n"
                "• **`/agent keamanan`** — tingkat keamanan konten AI per server (longgar/normal/ketat).\n"
                "• **`/faq`** — jawaban info server **tanpa AI** (0 kuota) + kelola entri (Admin).\n"
                "• **`/terjemah`** — penerjemah hemat kuota (reaksi bendera 🇮🇩/🇬🇧).\n"
                "**🧩 Komunitas & Lain-lain**\n"
                "• **`/panel-role`**, **`/poll`**, **`/ingatkan`**, **`/starboard`**, **`/sticky`**.\n"
                "• **`/info`**, **`/perawatan`**, **`/status`**, **`/bantuan`**."
            ),
            inline=False,
        )
        embed.add_field(
            name="💡 Pintasan Favorit Tanpa Ketik Command",
            value=(
                "• **Tekan-Tahan / Klik-Kanan Pesan ➔ Apps:** `🌐 Terjemahkan`, `💡 Jelaskan`, `🔍 Cek Fakta`\n"
                "• **Panggil Nama Bot di Channel Aktif:** Tanya langsung, kirim Voice Note `🎤`, PDF, foto, atau link!"
            ),
            inline=False,
        )

    embed.set_footer(text=f"Gemini AI v{BOT_VERSION} • Pilih kategori pada menu di bawah untuk berpindah halaman")
    return embed
HELP_CATEGORIES: list[dict] = [
    {
        "value": "overview",
        "label": "Ringkasan & Daftar Command Utama",
        "emoji": "🏠",
        "description": "Gambaran cepat seluruh fitur & pintasan tanpa ketik",
    },
    {
        "value": "sesi",
        "label": "Ruang AI Privat, PDF, Voice Note & Gambar (/sesi)",
        "emoji": "🔒",
        "description": "Cara pakai ruang chat pribadi, multimodal, & studio gambar",
    },
    {
        "value": "tools",
        "label": "Ringkas Chat/Link, Cari Berita & Klik-Kanan Pesan",
        "emoji": "🔎",
        "description": "Panduan /ringkas chat, /ringkas link, /cari, & Cek Fakta",
    },
    {
        "value": "games",
        "label": "6 Mode Mini-Game Tongkrongan & Papan Skor (/game)",
        "emoji": "🎮",
        "description": "Tebak Gambar AI, Sambung Kata, Emoji, Trivia, & Klasemen",
    },
    {
        "value": "server",
        "label": "Fitur Server: Stats, Auto Role, Fakta & Anti-Phishing",
        "emoji": "🛠️",
        "description": "Panduan /serverstats, /autorole, /fakta, & /keamanan",
    },
    {
        "value": "growth",
        "label": "Level & XP serta Tiket Dukungan (/level, /tiket)",
        "emoji": "📈",
        "description": "Kartu level, papan peringkat, hadiah role, & tiket thread",
    },
    {
        "value": "insights",
        "label": "Hemat Kuota AI: Pemakaian, Rekap & FAQ (/pemakaian)",
        "emoji": "📊",
        "description": "Statistik pemakaian, rekap channel ber-cache, & FAQ lokal 0 kuota",
    },
    {
        "value": "engagement",
        "label": "Giveaway, Ulang Tahun, Auto-Responder & Pengumuman",
        "emoji": "🎉",
        "description": "Undian berhadiah, ucapan ultah otomatis, & pengumuman terjadwal",
    },
    {
        "value": "musik",
        "label": "Streaming Musik 24/7 (/musik & Lavalink)",
        "emoji": "🎵",
        "description": "Putar lagu YouTube/Spotify, antrean, volume, & role DJ",
    },
    {
        "value": "komunitas",
        "label": "Fitur Komunitas Ringan (Role, Poll, Starboard, Sticky)",
        "emoji": "🧩",
        "description": "Reaction role, poll, pengingat, starboard, verifikasi, & sticky",
    },
    {
        "value": "admin",
        "label": "Panel Admin, Forum Pintar & Komunitas (/agent)",
        "emoji": "⚙️",
        "description": "Pengaturan /agent panel, Auto-Chat, Galeri, Welcome, & FAQ",
    },
]
def help_select_options() -> list[discord.SelectOption]:
    """Opsi dropdown kategori panduan (dipakai panel V2 & menu klasik)."""
    return [
        discord.SelectOption(
            label=c["label"][:100],
            value=c["value"],
            emoji=c["emoji"],
            description=c["description"][:100],
        )
        for c in HELP_CATEGORIES
    ]
class HelpPanelView(ui_kit.ui.LayoutView):
    """Pusat panduan `/bantuan` bergaya kartu dengan dropdown kategori (Components V2)."""

    def __init__(self, requester_id: int, category: str = "overview", guild_id: int | None = None):
        super().__init__(timeout=300)
        self.requester_id = requester_id
        self.guild_id = guild_id
        self.category = category if category in {c["value"] for c in HELP_CATEGORIES} else "overview"
        self._build()

    def _build(self) -> None:
        self.clear_items()
        embed = build_help_embed(self.category)
        selector = ui_kit.select_menu(
            "help:category",
            "📂 Pilih kategori panduan yang ingin dilihat…",
            help_select_options(),
            callback=self.on_select,
        )
        self.add_item(
            ui_kit.embed_to_container(
                self.guild_id,
                embed,
                extra_children=[ui_kit.action_row(selector)],
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "💡 Ketik `/bantuan` untuk membuka menu panduan milik Anda sendiri.",
                ephemeral=True,
            )
            return False
        return True

    async def on_select(self, interaction: discord.Interaction) -> None:
        values = (interaction.data or {}).get("values") or ["overview"]
        self.category = str(values[0])
        self._build()
        await ui_kit.edit_panel(
            interaction, self, embed=build_help_embed(self.category)
        )
class HelpMenuView(discord.ui.View):
    """Dropdown navigasi interaktif untuk berpindah halaman panduan `/bantuan`."""

    def __init__(self, requester_id: int):
        super().__init__(timeout=300)
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "💡 Ketik `/bantuan` untuk membuka menu panduan milik Anda sendiri.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(
        placeholder="📂 Pilih kategori panduan yang ingin dilihat...",
        options=help_select_options(),
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        chosen = select.values[0]
        await interaction.response.edit_message(
            embed=build_help_embed(chosen),
            view=self,
        )
