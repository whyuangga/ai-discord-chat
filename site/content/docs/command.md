---
title: "Referensi Command & Tombol"
description: "52 command utama, subcommand, dan tombol panel."
icon: "terminal"
weight: 90
toc: true
---

Referensi lengkap **53 command utama** beserta subcommand dan tombol panel, disusun per area
fitur. Setiap entri bisa dipakai langsung di Discord (butuh izin sesuai kolom yang tertera).

- Kembali ke [README](https://github.com/whyuangga/ai-discord-chat#readme) · penjelasan tiap fitur ada di [dokumentasi fitur](../docs/).
- Prefix `!` tetap berfungsi untuk command lama; lihat [`/prefix`](prefix/).

---

## 1. Menu Tekan-Tahan Pesan / Klik Kanan (*Apps*)
| Menu Apps | Akses | Keterangan |
| :--- | :--- | :--- |
| **`🌐 Terjemahkan ke Indonesia`** | Semua Member | Tekan-tahan / klik kanan pesan siapa saja (teks, embed, gambar, PDF, atau Voice Note) untuk menerjemahkannya ke Bahasa Indonesia secara privat. |
| **`💡 Jelaskan Pesan Ini`** | Semua Member | Tekan-tahan / klik kanan pesan rumit, istilah asing, error koding, atau meme untuk mendapatkan penjelasan ringkas. |
| **`🔍 Cek Fakta / Hoaks`** | Semua Member | Tekan-tahan / klik kanan pesan klaim berita atau *screenshot* untuk memeriksa kebenaran faktanya secara objektif beserta tautan sumber berita. |

## 2. Slash & Prefix Commands Ruang Privat, Pintasan & Hiburan
| Command | Akses | Keterangan |
| :--- | :--- | :--- |
| `/sesi panel` atau `!setup_panel` | Administrator | Memasang Embed & tombol Panel Ruang Privat AI (Chat & Gambar) di channel saat ini. |
| `/sesi model` | Pemilik Ruang Sesi | Mengganti mode kepribadian Gemini (Utama, Kilat, Koding, Riset, Curhat) di ruang `ai-...`. |
| `/sesi reset` | Pemilik Sesi / Moderator | Menghapus memori obrolan di `ai-...` atau mereset setelan gambar di `draw-...`. |
| `/sesi tutup` | Pemilik Sesi / Moderator | Mengakhiri ruang sesi privat saat ini & mengirim rekap transkrip lengkap ke DM. |
| `/ringkas chat` | Semua Member | Merangkum `25`–`150` obrolan terakhir di channel/thread agar tidak ketinggalan topik (*TL;DR*). |
| `/ringkas link` | Semua Member | Merangkum isi video **YouTube** atau artikel website secara instan (bisa disertai pertanyaan). |
| `/cari` | Semua Member | Mencari berita, skor, cuaca, kurs, & fakta terbaru hari ini via **Live Web & News Search** gratis + sumber web. |
| `/game mulai` | Semua Member | Memulai ronde Mini-Game AI (`emoji`, `image_guess`, `word_chain`, `trivia`, `riddle`, `scramble`, atau acak kejutan). |
| `/game papan_skor` | Semua Member | Menampilkan Top 10 Klasemen Papan Skor Mini-Game server beserta peringkat Anda. |
| `/game stop` | Pemulai / Moderator | Menghentikan ronde Mini-Game yang sedang berjalan di channel saat ini. |
| `/game reset_skor` | Administrator | Mereset seluruh Papan Skor Mini-Game server kembali ke `0` untuk musim baru. |
| `/bantuan` | Semua Member | Membuka **Pusat Panduan Interaktif** dengan menu *dropdown* 11 kategori fitur + panel **🆕 Terbaru**. |
| `/status` | Semua Member | Menampilkan ping Discord, pemakaian RAM (MB), uptime, jam AI, model aktif, & jumlah sesi. |

## 3. Slash Commands Admin untuk AI Agent Komunitas (`/agent`)
| Command | Parameter Utama | Keterangan |
| :--- | :--- | :--- |
| `/agent panel` | — | Membuka **Panel Kontrol Admin Interaktif** (*Spotlight Channel*, toggle fitur klik langsung, form Modal Persona, & pengelola FAQ 1-klik). |
| `/agent info` | `aksi`, `topik`, `isi` | Mengelola **Memori Info & FAQ Resmi Server** (maks. 25 entri: rules, IP server, jadwal, link) agar AI selalu menjawab akurat. |
| `/agent digest` | `channel`, `aktif`, `jam`, `topik`, `tes_sekarang` | Mengaktifkan/mematikan jadwal pengiriman **Koran & Sapaan Pagi Otomatis** setiap hari di channel pilihan. |
| `/agent chat` | `channel`, `aktif`, `mode_balas`, `menit_sepi` | Mengaktifkan/mematikan Auto-Chat di Text Channel maupun **Channel Forum** (+ Pemecah Sepi di Text Channel). |
| `/agent welcome` | `channel`, `aktif`, `persona`, `bahasa_sapaan`, `pesan_tambahan`, `tes_sekarang` | Auto-Welcomer dengan **persona sambutan khusus** + **kata sapaan bahasa Asia** yang berganti-ganti. |
| `/agent banner` | `gambar`, `jenis`, `hapus` | *(Admin)* Unggah/hapus banner sambutan, perpisahan, atau boost (disimpan di `data/media/`). |
| `/agent kartu` | `mode` | *(Admin)* Tampilan sambutan: teks, banner statis, atau kartu dinamis (avatar + nama). |
| `/agent dm` | `aktif` | *(Admin)* Kirim salinan sambutan lewat DM ke member baru. |
| `/agent boost` | `channel`, `aktif`, `pesan` | *(Admin)* Pesan terima kasih otomatis saat ada member boost server. |
| `/sosial tambah` | `platform`, `target`, `channel`, `role`, `pesan` | *(Admin)* Pantau YouTube / Twitch / TikTok / **Reddit** / **RSS-Atom** lalu kirim notifikasi otomatis (0 kuota AI). |
| `/sosial daftar` | — | Lihat semua langganan notifikasi + ID-nya. |
| `/sosial hapus` | `id` | Hentikan pemantauan satu langganan. |
| `/sosial tes` | `id` | Kirim contoh notifikasi sekarang untuk memastikan konfigurasi benar. |
| `/sosial status` | — | Cek kesiapan: kredensial Twitch & token, plus jumlah langganan per platform + langkah pengisiannya. |
| `/mod warn` | `member`, `alasan` | *(Staff)* Peringatan tercatat + auto-timeout saat ambang tercapai. |
| `/mod timeout` | `member`, `durasi`, `alasan` | *(Staff)* Timeout native Discord. |
| `/mod kick` / `/mod ban` / `/mod unban` | `member`/`user_id`, `alasan` | *(Staff)* Tindakan disipliner, tercatat sebagai kasus. |
| `/mod purge` | `jumlah`, `member`, `tipe` | *(Staff)* Hapus pesan massal dengan filter. |
| `/mod tempban` | `member`, `durasi`, `alasan`, `hapus_pesan_hari` | *(Staff)* Ban sementara, dicabut otomatis saat durasi habis. |
| `/mod softban` | `member`, `alasan`, `hapus_pesan_hari` | *(Staff)* Ban + cabut langsung (pembersihan pesan tanpa hukuman permanen). |
| `/mod note` | `member`, `teks` | *(Staff)* Catatan internal staff, tanpa tindakan apa pun. |
| `/snipe hapus` / `/snipe edit` | `jumlah` | *(Staf)* Lihat pesan terakhir yang dihapus/diubah di channel (memori saja). |
| `/snipe atur` | `aktif`, `hapus`, `edit` | *(Admin)* Sakelar snipe & edit-snipe. |
| `/mod statistik` | `hari` | *(Staff)* Siapa menindak berapa banyak + temp-ban yang masih berjalan. |
| `/mod catatan` | `member`, `jumlah` | *(Staff)* Riwayat kasus + jumlah peringatan aktif. |
| `/mod antrean` | `status`, `jenis` | *(Staff)* Antrean laporan member & banding hukuman. |
| `/mod tindak` | `kode`, `status`, `catatan`, `cabut` | *(Staff)* Ubah status antrean; `cabut` mencabut hukuman dari banding yang diterima. |
| `/lapor` | `member`, `alasan`, `bukti` | **(Semua member)** Laporkan member ke staf — masuk antrean, bukan langsung hukuman. |
| `/banding` | `alasan`, `kasus` | **(Semua member)** Ajukan peninjauan hukuman (bisa dari DM bila sudah diban). |
| `/mod hapus` | `id` | *(Admin)* Hapus satu kasus dari catatan. |
| `/mod atur` | `log_channel`, `ambang_warn`, `durasi_auto`, `jendela_hari`, `dm` | *(Admin)* Pengaturan moderasi. |
| `/lencana lihat` | `member` | Lencana + progres seorang member (kosongkan = dirimu). |
| `/lencana papan` | — | Papan lencana server (10 teratas). |
| `/lencana periksa` | `member` | *(Staf)* Segarkan lencana sekarang tanpa menunggu aktivitas berikutnya. |
| `/lencana atur` | `channel`, `aktif` | *(Admin)* Channel pengumuman lencana & sakelar global. |
| `/lencana role` | `kunci`, `tingkat`, `role` | *(Admin)* Role hadiah per tingkat lencana (kosongkan `role` = hapus). |
| `/pantau tambah` | `kata` | Pantau kata/frasa → DM saat muncul di chat (maks 10/member). |
| `/pantau hapus` | `kata` | Berhenti memantau satu kata kunci. |
| `/pantau daftar` | — | Lihat kata kunci, daftar abaikan, & jumlah DM terkirim. |
| `/pantau abaikan` | `channel`, `kata` | Abaikan channel atau kata tertentu. |
| `/pantau bersihkan` | — | Hapus semua setelan highlight milikmu. |
| `/pantau atur` | `aktif`, `abaikan_channel` | *(Admin)* Sakelar server & channel yang selalu diabaikan. |
| `/curhat kirim` | `teks` | Kirim curhat anonim ke satu channel (10–900 huruf, maks 3/jam). |
| `/curhat atur` | `channel`, `aktif`, `izinkan_link`, `jeda_menit` | *(Admin)* Setelan channel, sakelar, izin tautan, & jeda per orang. |
| `/curhat hapus` | `nomor` | *(Staf)* Hapus satu curhat yang melanggar. |
| `/bangun tema` | `tema` | *(Admin)* Pratinjau struktur server dari salah satu **15 tema** (0 kuota AI) + tombol Terapkan/Batal. |
| `/bangun rancang` | `deskripsi` | *(Admin)* AI menyusun kategori/channel/role dari deskripsi bebas, lalu pratinjau. |
| `/bangun terapkan` | — | *(Admin)* Terapkan rencana terakhir yang menunggu konfirmasi. |
| `/bangun riwayat` | — | Lihat pembangunan terakhir di server ini. |
| `/bangun bongkar` | — | *(Admin)* Hapus hanya item yang tercatat dibuat `/bangun`. |
| `/gambar buat` | `prompt`, `rasio`, `gaya`, `acuan` | Buat gambar AI (5 rasio, belasan gaya); opsional gambar acuan. |
| `/gambar edit` | `prompt`, `acuan` | Ubah gambar lampiran **atau** gambar terakhir di channel itu. |
| `/gambar pilihan` | — | Daftar rasio & gaya yang tersedia. |
| `/dataku` | — | Ekspor data pribadimu sebagai lampiran JSON. |
| `/hapusdataku` | — | Hapus permanen data pribadimu (dengan tombol konfirmasi). |
| `/meme` | `teks_atas`, `teks_bawah`, `template` | Buat meme lokal (6 gaya), 0 kuota AI. |
| `/tag lihat` | `nama` | Tampilkan isi tag server (semua member). |
| `/tag daftar` / `/tag cari` | — / `kata` | Daftar semua tag / cari tag lewat nama atau isi. |
| `/tag buat` / `/tag ubah` / `/tag hapus` | `nama`, `isi` | *(Staf)* Kelola tag jawaban siap pakai (maks 100/server). |
| `/tempvoice atur` | `hub`, `aktif`, `nama`, `limit` | *(Admin)* Aktifkan voice room sementara (join-to-create). |
| `/tempvoice status` | — | Lihat hub & room sementara yang aktif. |
| `/tempvoice tautkan` | `aktif`, `role`, `channel_privat`, `hapus_kosong`, `kategori` | *(Admin)* Voice linking: role + channel teks privat selama member di voice. |
| `/kanal-info atur` | `channel`, `aktif`, `judul`, `warna`, `interval_menit` | *(Admin)* Channel aturan & info yang diperbarui otomatis. |
| `/kanal-info isi` | `teks` | *(Admin)* Tulis/ganti isi aturan & info (20–3500 huruf). |
| `/kanal-info segarkan` / `/kanal-info status` | — | *(Admin)* Terbitkan/perbarui pesan sekarang / lihat ringkasan setelan. |
| `/tempvoice kunci` / `nama` / `limit` / `tendang` | `aktif` / `nama` / `jumlah` / `member` | Pengaturan room oleh **pemilik room**. |
| `/saran pasang` | `channel`, `nonaktifkan` | *(Admin)* Tentukan channel kotak saran. |
| `/saran kirim` | `teks` | Kirim usulan dengan tombol voting 👍/👎. |
| `/saran daftar` | `status`, `jumlah` | Lihat saran terbaru + skor. |
| `/saran status` | `id`, `status` | *(Staff)* Ubah status saran (baru/dikerjakan/diterima/ditolak). |
| `/saran hapus` | `id` | *(Admin)* Hapus saran beserta pesannya. |
| `/embed buat` | `channel`, `warna` | *(Staff)* Buat pengumuman embed lewat formulir. |
| `/embed cepat` | `channel`, `judul`, `isi`, `warna`, `gambar` | *(Staff)* Kirim embed tanpa formulir. |
| `/embed variabel` | — | Daftar variabel `{member.mention}`, `{server.members}`, `{now_relative}`, … yang bisa dipakai di judul/isi. |
| `/embed sebagai` | `nama`, `isi`, `channel`, `judul`, `avatar`, `warna` | *(Staff)* Kirim pesan dengan nama & avatar sendiri lewat webhook (butuh *Manage Webhooks*). |
| `/embed webhook` | `channel`, `hapus` | *(Staff)* Cek atau hapus webhook identitas yang dipakai bot di channel itu. |
| `/embed tautan buat` | `url`, `judul`, `isi`, `gambar`, `sampul`, `warna`, `provider`, `situs` | *(Staff)* Buat tautan yang tampil sebagai embed (`/l/<kode>` di situs) dan mengarah ke `url`. |
| `/embed tautan daftar` | — | Lihat tautan embed yang pernah dibuat di server ini. |
| `/embed tautan hapus` | `tautan` | *(Staff)* Hapus tautan dari daftar server (halaman tetap hidup). |
| `/afk atur` / `daftar` / `hapus` | `alasan` | Tandai/lihat/hapus status AFK. |
| `/thread-otomatis aktifkan` | `channel`, `arsip_menit` | *(Admin)* Buat thread otomatis per pesan baru. |
| `/lockdown aktif` | `aktif`, `alasan` | *(Admin)* Kunci/buka semua text channel saat darurat. |
| `/backup struktur` | — | *(Admin)* Ekspor role/kategori/channel/izin ke berkas JSON. |
| `/agent goodbye` | `channel`, `aktif`, `persona`, `bahasa_sapaan`, `pesan_tambahan`, `tes_sekarang` | Mengaktifkan kartu perpisahan AI + masa kebersamaan untuk member yang keluar. |
| `/agent gallery` | `channel`, `aktif`, `auto_reaction` | Mengaktifkan/mematikan Auto-Komentar Foto & Video di Text Channel maupun **Forum/Media Showcase**. |
| `/agent youtube` | `channel`, `aktif`, `auto_di_channel` | Mengaktifkan/mematikan rangkum YouTube/Web (`/ringkas link` & baca link) pada satu/beberapa Text Channel atau **Channel Forum**. |
| `/agent cari` | `channel`, `aktif`, `auto_di_chat` | Mengaktifkan/mematikan pencarian berita/web (`/cari` & auto-search) pada satu/beberapa Text Channel atau **Channel Forum**. |
| `/agent persona` | `gaya_bahasa`, `nama_panggilan`, `zona_waktu`, `jam_tenang_malam`, `konteks_komunitas` | Mengubah nama akrab AI, gaya bicara (*Akrab / Gaul / Ramah*), zona waktu (*WIB/WITA/WIT*), Jam Tenang, & deskripsi komunitas. |
| `/agent sapa` | `channel` *(opsional)* | Memicu AI Agent langsung menyapa / memecah sepi detik ini juga (untuk tes instan). |
| `/agent status` | — | Melihat dashboard status AI Agent terpadu, daftar channel aktif, & sisa hitung mundur pemecah sepi. |

## 4. Slash Commands Fitur Server (`/serverstats`, `/autorole`, `/fakta`, `/keamanan`)
| Command | Parameter Utama | Keterangan |
| :--- | :--- | :--- |
| `/serverstats lihat` | — | Kartu statistik server: anggota, online, boost, channel, role, emoji, stiker, tanggal dibuat, & pemilik. |
| `/serverstats otomatis` | `aktif` | *(Admin)* Membuat/mematikan Voice Channel penghitung statistik yang diperbarui ±10 menit. |
| `/serverstats ikon` | `anggota`, `manusia`, `bot`, `online`, `boost`, `tiket`, `sosial`, `kategori`, `reset` | *(Admin)* Ganti atau hapus emoji ikon tiap channel statistik + nama kategori. Isi `-` untuk menghapus ikon. |
| `/serverstats tipe` | `channel`, `aktif` | *(Admin)* Pilih **jenis channel** counter: `voice` 🔊, `text` #️⃣, `announcement` 📢, atau `stage` 🎤 — ikon di kiri nama channel ikut berubah. |
| `/autorole atur` | `role`, `role2`, `role3`, `aktif` | *(Admin)* Atur 1–3 role otomatis untuk setiap member baru. |
| `/autorole status` | — | *(Admin)* Lihat role Auto Role aktif & peringatan hierarki role bot. |
| `/autorole isi` | — | *(Admin)* Berikan Auto Role ke member lama yang belum memilikinya (maks. 150). |
| `/fakta atur` | `channel`, `aktif`, `jadwal` | *(Admin)* Atur jadwal **multi-slot** 3–4 Fakta Unik Dunia (default `08:00,12:00,16:00,20:00`, maks 6 slot/hari). |
| `/fakta sekarang` | `channel` *(opsional)* | *(Admin)* Kirim contoh fakta saat ini juga (tanpa mengubah jadwal). |
| `/fakta status` | — | Lihat seluruh slot, slot berikutnya, & slot yang sudah terkirim hari ini. |
| `/keamanan phising` | `aktif`, `aksi`, `channel`, `log_channel`, `ketat` | *(Admin)* Anti-Phishing Guard: hapus link berbahaya + peringatan + log. |
| `/keamanan cek` | `link` | Periksa keamanan sebuah link (semua member). |
| `/keamanan spam` | `aktif`, `mode`, `log_channel`, `ambang_banjir`, `jendela`, `mention_maks`, `link_maks`, `kapital`, `timeout_detik`, `kecualikan_channel`, `kecualikan_role` | *(Admin)* Anti-spam & anti-raid, **mode bawaan `lapor`** (tanpa menghapus apa pun). |
| `/keamanan spam-status` | — | Lihat ambang deteksi, pengecualian, & statistik penjaga spam. |
| `/keamanan honeypot` | `channel`, `aksi`, `timeout_detik`, `log_channel`, `abaikan_staf`, `aktif` | *(Admin)* Channel jebakan (maks 3): lapor / hapus / timeout / kick / ban. Bawaan hanya **melapor**, staf & bot selalu aman. |

## 5. Slash Commands Fitur Komunitas Ringan (Gratis, Tanpa Kuota AI)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/panel-role pasang` | `channel`, `judul`, `role1`, `emoji1`, `deskripsi`, `role2`, `emoji2`, `role3`, `emoji3` | *(Admin)* Buat panel Reaction Role (maks 3 role sekali pasang). |
| `/panel-role tambah` / `hapus` | `pesan`, `emoji`, `role` | *(Admin)* Tambah / hapus role pada panel yang sudah ada. |
| `/panel-role daftar` | — | Lihat seluruh panel reaction role server. |
| `/poll` | `pertanyaan`, `opsi`, `durasi_jam`, `multi`, `anonim` | Buat polling native Discord (hitung suara otomatis). |
| `/ingatkan pasang` | `waktu`, `pesan`, `channel` | Pasang pengingat pribadi (`10m`, `2j`, `2 hari`, `1j30m`). |
| `/ingatkan daftar` / `batal` | `nomor` | Lihat / batalkan pengingat aktif. |
| `/starboard atur` | `channel`, `batas`, `emoji`, `aktif` | *(Admin)* Atur channel sorotan & ambang bintang. |
| `/starboard status` | — | Lihat semua papan sorotan & jumlah pesan tersorot. |
| `/starboard varian` | `tambah`, `emoji`, `batas`, `channel`, `warna`, `hapus` | *(Admin)* Papan sorotan tambahan (skullboard 💀, clownboard 🤡, …) dengan emoji, ambang, channel, & warna sendiri — maks 4 papan/server. |
| `/verifikasi pasang` | `channel`, `role`, `catatan`, `captcha` | *(Admin)* Pasang gerbang verifikasi + tombol **✅ Verifikasi Saya** (opsional: kode CAPTCHA). |
| `/verifikasi status` / `matikan` | — | Pantau / matikan gerbang verifikasi. |
| `/sticky pasang` | `isi`, `channel`, `judul` | *(Admin)* Pasang pesan petunjuk yang selalu di bawah channel. |
| `/sticky lepas` / `status` | `channel` | Lepas / lihat daftar sticky message. |
| `/info user` | `member` | Kartu profil member (umur akun, join, role, flag akun baru). |
| `/info server` | — | Ringkasan server (member, online, boost, channel, keamanan). |
| `/perawatan backup` | `channel` | *(Admin)* Kirim ZIP backup konfigurasi sekarang. |
| `/perawatan atur` | `backup_channel`, `log_channel`, `otomatis` | *(Admin)* Atur backup otomatis & channel log error. |
| `/perawatan status` | — | Status backup, log error, ukuran data, & RAM bot. |

## 6. Slash Commands Streaming Musik (`/musik`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/musik putar` | `query`, `berikutnya` | Putar lagu/playlist dari YouTube, Spotify, SoundCloud, atau link langsung. |
| `/musik cari` | `query` | Cari 5 lagu lalu pilih lewat dropdown (berlaku 60 detik). |
| `/musik antrean` | `halaman` | Lihat antrean berhalaman (10 lagu/halaman) + total durasi. |
| `/musik sekarang` | — | Lagu aktif, progress bar, volume, & mode pengulangan. |
| `/musik jeda` / `/musik lanjut` | — | Jeda / lanjutkan pemutaran. |
| `/musik lewati` | `jumlah` | Lewati 1–10 lagu. |
| `/musik sebelumnya` | — | Putar lagi lagu sebelumnya dari riwayat. |
| `/musik seek` | `posisi` | Lompat ke posisi tertentu (`95`, `1:30`, `01:02:03`). |
| `/musik filter` | `jenis` | Efek audio (bassboost/nightcore/vaporwave/8d/karaoke/treble/off). |
| `/musik autoplay` | `aktif` | Autoplay rekomendasi saat antrean habis. |
| `/musik panel` | — | Kirim ulang panel pemutar Rythm. |
| `/musik acak` | — | Acak urutan antrean. |
| `/musik ulang` | `mode` (`mati`/`satu`/`semua`) | Mode pengulangan. |
| `/musik volume` | `level` (1–150) | Volume + simpan sebagai default server. |
| `/musik hentikan` | — | Stop, kosongkan antrean, & keluar dari voice. |
| `/musik pengaturan` | `pengumuman`, `role_dj`, `volume_default` | *(Admin)* Pengumuman Now Playing, role DJ, volume default. |
| `/musik status` | — | Kesehatan node Lavalink & status pemutaran. |
| `/musik playlist` | `simpan`/`daftar`/`lihat`/`putar`/`hapus-lagu`/`ganti-nama`/`hapus` | Playlist pribadi per member (5 playlist × 50 lagu, tersimpan permanen). |

## 7. Slash Commands Keramaian Server (`/giveaway`, `/ultah`, `/jawab-otomatis`, `/pengumuman`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/giveaway mulai` | `hadiah`, `durasi`, `pemenang`, `channel`, `syarat_role` | *(Admin)* Pasang giveaway + tombol **🎉 Ikuti Giveaway**. |
| `/giveaway akhiri` | `id_pesan` | *(Admin)* Tutup lebih awal & umumkan pemenang. |
| `/giveaway reroll` | `id_pesan` | *(Admin)* Undi ulang dari peserta yang belum pernah menang. |
| `/giveaway daftar` | — | Giveaway berjalan + riwayat pemenang. |
| `/ultah set` | `tanggal` | Daftarkan tanggal lahir (`12-08`, `12/8/2000`, `12 Agustus`). |
| `/ultah hapus` | — | Hapus data ulang tahun sendiri. |
| `/ultah daftar` | `bulan` | Daftar ulang tahun member server. |
| `/ultah atur` | `channel`, `jam` | *(Admin)* Channel & jam ucapan otomatis (kosongkan `channel` = mati). |
| `/jawab-otomatis tambah` | `pemicu`, `balasan`, `persis`, `channel` | *(Admin)* Tambah aturan balasan kata kunci. |
| `/jawab-otomatis hapus` | `pemicu`, `channel` | *(Admin)* Hapus satu aturan. |
| `/jawab-otomatis daftar` | `channel` | Lihat aturan yang aktif + jeda aman. |
| `/jawab-otomatis atur` | `channel`, `aktif`, `jeda` | *(Admin)* Aktifkan/nonaktifkan & atur jeda (0–300 detik). |
| `/pengumuman tambah` | `isi`, `jadwal`, `judul`, `channel` | *(Admin)* Jadwalkan pengumuman (harian / mingguan / sekali) ke channel atau thread. |
| `/pengumuman daftar` | — | Lihat seluruh jadwal & kiriman berikutnya. |
| `/pengumuman hapus` | `id` | *(Admin)* Hapus pengumuman terjadwal. |
| `/pengumuman atur` | `id`, `aktif` | *(Admin)* Jeda atau aktifkan lagi tanpa menghapus. |
| `/pengumuman kirim` | `id` | *(Admin)* Kirim sekarang juga; jadwal berikutnya tidak berubah. |
| `/pengumuman ubah` | `id`, `isi`, `judul`, `jadwal` | *(Admin)* Ubah isi/judul/jadwal tanpa menghapus. |

## 8. Slash Commands Level & Tiket (`/level`, `/tiket`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/level lihat` | `member` | Kartu level + progress bar XP. |
| `/level kartu` | `member`, `publik` | **Kartu rank PNG** (level, XP, peringkat, prestise) dirender server — 0 kuota AI. |
| `/level papan` | `halaman` | Papan peringkat 10 besar server. |
| `/level atur` | `aktif`, `pengumuman`, `channel_pengumuman`, `jeda`, `xp_minimal`, `xp_maksimal`, `abaikan_channel`, `abaikan_role` | *(Admin)* Konfigurasi leveling. |
| `/level role` | `level`, `role` | *(Admin)* Hadiah role otomatis per level. |
| `/level voice` | `aktif`, `xp_per_menit`, `batas_menit_harian`, `abaikan_channel` | *(Admin)* XP dari voice channel (0 kuota AI). |
| `/level status` | — | Statistik & konfigurasi leveling. |
| `/level musim` | `status`/`ulang` (`konfirmasi`, `reset_otomatis_hari`) | Musim level: status & reset musim baru. |
| `/level prestise` | — | Tukar level maksimum jadi Prestige (XP→0, trofi permanen). |
| `/tiket panel` | `channel`, `staff_role`, `log_channel`, `max_open` | *(Admin)* Pasang panel **🎟️ Buat Tiket**. |
| `/tiket status` | — | Konfigurasi, statistik, & tiket aktif. |
| `/tiket daftar` | `hanya_milikku` | Daftar tiket aktif. |
| `/tiket tambah` | `member` | *(Staf)* Tambah member ke thread tiket. |
| `/tiket tutup` | — | Tutup tiket + kirim transkrip. |
| `/tiket atur` | `rating_aktif`, `sla_jam`, `auto_close_jam`, `channel_sla` | *(Admin)* Rating bintang, SLA respons pertama, & auto-close. |
| `/tiket rating` | — | Rata-rata rating bintang & statistik SLA. |
| `/tiket matikan` | — | *(Admin)* Matikan sistem tiket. |

## 9. Slash Commands Hemat Kuota AI (`/pemakaian`, `/ringkas channel`, `/faq`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/pemakaian lihat` | — | Pemakaian AI hari ini (per jenis, member teraktif, channel tersibuk). |
| `/pemakaian tren` | `hari` | Tren harian total operasi vs cache hit. |
| `/pemakaian status` | — | Ringkasan penghematan: cache hit, batas harian, TTL cache, entri FAQ. |
| `/pemakaian reset` | `cache_rekap` | *(Admin)* Bersihkan catatan pemakaian & cache rekap. |
| `/ringkas channel` | `periode`, `paksa`, `publik` | Rekap obrolan per periode (cache 30 menit = 0 kuota). |
| `/faq tanya` | `pertanyaan` | Jawaban lokal dari FAQ server — **0 kuota**. |
| `/faq daftar` | — | Daftar seluruh entri FAQ server. |
| `/faq tambah` | `topik`, `isi` | *(Admin)* Tambah/perbarui entri FAQ. |
| `/faq hapus` | `target` | *(Admin)* Hapus entri FAQ (nomor urut atau topik). |

---

## 10. Slash Commands Tampilan & Control Center (Components V2)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/panel buka` | `tab` | Dashboard Control Center: kartu status + navigasi tab + tombol Segarkan/Tampilan/Tutup. |
| `/tampilan atur` | — | *(Admin)* Editor tema: aksen, emoji, kepadatan, thumbnail, navigasi, refresh, footer, konfirmasi. |
| `/tampilan pratinjau` | — | Lihat dashboard dengan tema aktif (ephemeral). |
| `/tampilan reset` | — | *(Admin)* Kembalikan tema ke bawaan bot (dengan konfirmasi). |

---

## 11. Slash Commands Log, Ekonomi & Pertumbuhan (`/log`, `/ekonomi`, `/tumbuh`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/log channel` | `channel` | *(Admin)* Pasang channel audit log & aktifkan pencatatan. |
| `/log status` | — | *(Admin)* Channel, kategori aktif, & channel dikecualikan. |
| `/log kategori` | `nama`, `aktif` | *(Admin)* Nyalakan/matikan satu kategori (`pesan`/`member`/`role`/`channel`/`voice`). |
| `/log abaikan` | `channel` | *(Admin)* Kecualikan channel dari pencatatan. |
| `/log matikan` | — | *(Admin)* Hentikan audit log server. |
| `/ekonomi atur` | `aktif`, `koin_per_pesan`, `jeda`, `koin_per_menit_voice`, `hadiah_harian`, `mata_uang` | *(Admin)* Konfigurasi ekonomi (default **NONAKTIF**). |
| `/ekonomi saldo` | `member` | Saldo, peringkat, & status hadiah harian. |
| `/ekonomi harian` | — | Klaim hadiah harian + bonus streak. |
| `/ekonomi papan` | — | Papan peringkat kekayaan server. |
| `/ekonomi toko` | — | Daftar item toko. |
| `/ekonomi beli` | `item` | Beli item → role otomatis diberikan. |
| `/ekonomi transfer` | `member`, `jumlah` | Kirim koin (minimal 10, ada jeda anti-spam). |
| `/ekonomi tambah-item` | `nama`, `harga`, `role`, `deskripsi` | *(Admin)* Tambah/ubah item toko (maks 20). |
| `/ekonomi hapus-item` | `nama` | *(Admin)* Hapus item toko. |
| `/tumbuh ringkas` | `hari` | Join, keluar, retensi, tren harian, & top pengundang. |
| `/tumbuh undang` | — | Papan **Top Inviter**. |
| `/tumbuh status` | — | Status pelacakan & izin baca invite. |
| `/tumbuh atur` | `aktif`, `channel`, `lacak_invite` | *(Admin)* Atur pelacakan & channel log join-keluar. |
| `/tumbuh sinkron` | — | *(Admin)* Segarkan cache invite manual. |

---

> **Command pengelola disembunyikan otomatis.** Command yang jelas khusus Admin/Manage Server
> (`/menu`, `/antinuke`, `/backup`, `/raid`, `/log`, `/autorole`, …) diberi izin minimum sehingga
> **member biasa tidak melihatnya sama sekali** di daftar slash. Dari 288 entri, ±139 entri
> hanya muncul untuk pengelola — sisanya (±149) terlihat semua orang. Jalankan
> `python tools/command_audit.py` untuk melihat pembagiannya.

## 12. Slash Commands Menu Builder (`/menu`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/menu buat` | `judul`, `deskripsi`, `channel`, `banner`, `banner_url` | *(Admin)* Buat panel + kirim ke channel/thread/forum. |
| `/menu tombol-role` | `role`, `menu`, `label`, `emoji`, `gaya` | *(Admin)* Tombol role (toggle). |
| `/menu tombol-link` | `label`, `url`, `menu`, `emoji` | *(Admin)* Tombol tautan. |
| `/menu tombol-command` | `aksi`, `menu`, `label`, `emoji`, `visibilitas`, `gaya` | *(Admin)* Tombol yang menjalankan command info. |
| `/menu dropdown-role` | `role1`…`role5`, `menu`, `placeholder`, `eksklusif`, `emoji1`…`emoji5` | *(Admin)* Dropdown role. |
| `/menu alur` | `aksi`, `menu`, `label`, `emoji`, `gaya` | *(Admin)* Tombol yang menjalankan **alur aksi**: `+role:123 > pesan:Halo {member.mention} > thread:tiket`. |
| `/menu alur-bantuan` | — | Panduan menulis alur (`role`, `pesan`, `umum`, `thread`, `tunggu`, `stop`, `syarat`, `webhook`, `hapus`). |
| `/menu form buat` | `nama`, `kolom`, `tujuan`, `judul`, `penjelasan`, `hasil`, `warna` | *(Admin)* Buat **formulir (modal)** dengan kolom sendiri, mis. `kolom:"Nama \| Umur \| Alasan:panjang?"`. |
| `/menu form ubah` | `form`, `nama`, `judul`, `penjelasan`, `hasil`, `tujuan`, `kolom`, `warna` | *(Admin)* Ubah formulir (kirim `-` untuk mengosongkan penjelasan/hasil). |
| `/menu form tombol` | `form`, `menu`, `label`, `emoji`, `gaya` | *(Admin)* Pasang formulir sebagai tombol di panel. |
| `/menu form daftar` | — | Lihat semua formulir, kolom, tujuan, dan jumlah jawaban. |
| `/menu form uji` | `form` | *(Admin)* Coba isi formulir; hasilnya hanya pratinjau untukmu. |
| `/menu form hapus` | `form` | *(Admin)* Hapus formulir beserta tombolnya di panel. |
| `/menu pemicu tambah` | `aksi`, `channel`, `umur_akun` | *(Admin)* Alur yang jalan otomatis saat member baru bergabung. |
| `/menu pemicu daftar` | — | Lihat alur gabung yang aktif. |
| `/menu pemicu hapus` | — | *(Admin)* Matikan alur gabung. |
| `/menu hapus-item` | `item`, `menu` | *(Admin)* Hapus tombol/opsi. |
| `/menu ubah` | `menu`, `judul`, `deskripsi` | *(Admin)* Ubah teks panel yang sudah terkirim (pesan ikut berubah, tanpa kirim ulang). |
| `/menu ekspor` | `menu` | *(Admin)* Unduh panel sebagai berkas JSON (backup / pindah server). |
| `/menu bagikan` | `menu` | *(Admin)* Buat tautan bagikan panel: URL pratinjau `/​p/<kode>` di situs + kode impor. |
| `/menu impor` | `berkas`, `judul`, `kode` | *(Admin)* Buat panel baru dari berkas JSON `/menu ekspor` **atau** tautan/kode `/menu bagikan`. |
| `/menu kirim` | `menu`, `channel` | *(Admin)* Kirim ulang panel ke channel, thread, atau forum. |
| `/menu daftar` | — | Daftar panel & isinya. |
| `/menu hapus` | `menu` | *(Admin)* Hapus panel dari daftar bot. |

---

## 13. Slash Commands Anti-Nuke (`/nuke`)

| Command | Parameter | Fungsi |
| :--- | :--- | :--- |
| `/nuke status` | — | Status, ambang, izin bot, whitelist, & pelanggaran terakhir. |
| `/nuke atur` | `aktif`, `channel`, `aksi`, `timeout_detik`, `dm_owner`, `pulihkan`, `jenis_ambang`, `ambang`, `jendela_detik`, `keluarkan_bot` | *(Admin)* Konfigurasi anti-nuke. |
| `/nuke whitelist` | `aksi`, `member`, `role` | *(Admin)* Kecualikan member/role dari tindakan. |
| `/nuke uji` | `jenis` | *(Admin)* Uji kering ambang & tindakan. |
| `/nuke pulihkan` | — | *(Admin)* Pulihkan nama/ikon server. |
| `/nuke beku` | `durasi_menit`, `paksa_aksi` | *(Admin)* Mode beku: ambang 1 aksi selama N menit. |
| `/nuke cairkan` | — | *(Admin)* Akhiri mode beku lebih awal. |
| `/nuke matikan` | — | *(Admin)* Hentikan pemantauan. |
