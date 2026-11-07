---
title: "E. Fitur Komunitas Ringan (/panel-role, /poll, /saran, /embed, /tempvoice)"
description: "Reaction role, polling, pengingat, starboard, verifikasi, sticky, temp voice, kotak saran."
icon: "groups"
weight: 5
toc: true
---

> 💡 Semua fitur di bagian ini **tidak memanggil Gemini sama sekali** (0 kuota, 0 biaya) dan **default NONAKTIF**.
> Server yang belum memakai fitur ini tidak mendapat beban tambahan apa pun (tanpa event listener berat, tanpa RAM ekstra).

## 1. 🎭 Reaction Role — Member Ambil Role Sendiri (`/panel-role`)
- **`/panel-role pasang channel:#ambil-role judul:Ambil Role role1:@Gamer emoji1:🎮 role2:@Artist emoji2:🎨`** — bot mengirim panel embed lalu memasang reaksi emoji secara otomatis (maks **3 role sekali pasang**).
- Warga cukup **klik emoji** untuk mendapatkan role, **klik lagi** untuk melepasnya. Tidak ada kuota, tidak ada tombol kedaluwarsa.
- **`/panel-role tambah pesan:<ID/link> emoji:🎵 role:@Musik`** — tambah role ke panel yang sudah ada.
- **`/panel-role hapus`**, **`/panel-role daftar`** — kelola & lihat semua panel.
- Posisi role diperiksa otomatis: role di atas role bot dilewati dengan peringatan jelas.

## 2. 📊 Polling Native Discord (`/poll`)
- **`/poll pertanyaan:"Mabar malam ini jam berapa?" opsi:"Jam 8, Jam 9, Jam 10" durasi_jam:24`**
- Memakai **Poll bawaan Discord**: hitung suara real-time, tampilan rapi, tidak bisa di-*double vote* — tanpa beban server sama sekali.
- Mendukung **multi-pilihan** (`multi:True`), **anonim/terbuka** (`anonim:True`), dan durasi **1–768 jam** (maks 32 hari).
- Maksimal **10 pilihan** (batas Discord); lebih dari itu dipotong otomatis dengan pemberitahuan.

## 3. ⏰ Pengingat Pribadi Tahan Restart (`/ingatkan`)
- **`/ingatkan pasang waktu:"2j" pesan:"Rapat pengurus"`** — bot menagih kamu saat waktunya tiba (di channel atau DM bila channel tak bisa diakses).
- Format waktu fleksibel: `10m`, `2j`, `1j30m`, `2 hari`, `45` (menit), bahkan `1 jam dan 15 menit`. Maksimal **365 hari**.
- **Tahan restart:** pengingat disimpan di `data/community_tools.json`, jadi tetap dikirim walau bot baru di-*restart*.
- **`/ingatkan daftar`** & **`/ingatkan batal nomor:3`** — kelola pengingat aktif (maks 15 per member).

## 4. ⭐ Starboard — Sorotan Pesan Populer (`/starboard`)
- **`/starboard atur channel:#starboard batas:3 emoji:⭐`** — pesan warga yang mendapat **3 reaksi bintang** otomatis disalin ke channel sorotan (embed cantik + tautan sumber).
- Bila reaksi turun di bawah batas, sorotannya **otomatis dihapus** agar starboard tetap rapi.
- Pesan bot dilewati, emoji bisa diganti bebas (`🔥`, `❤️`, dll.), dan **`/starboard status`** menampilkan semua papan + jumlah sorotan.

**Papan berlapis / varian (v1.40.0-beta):**

| Aspek | Detail |
| :--- | :--- |
| **Papan utama + varian** | Papan ⭐ tetap seperti biasa. Tambahkan **skullboard 💀**, **clownboard 🤡**, dll. dengan `/starboard varian tambah:Skull emoji:💀 batas:5 channel:#skull warna:#FF8A00`. Maksimal `STARBOARD_MAX_BOARD` = **4 papan** per server (termasuk papan utama). |
| **Mandiri** | Tiap papan punya emoji, ambang, channel, dan warna embed sendiri. Satu pesan bisa masuk ke **beberapa papan sekaligus**; entri sorotan disimpan per papan sehingga menghapus sorotan di satu papan tidak mengganggu papan lain. |
| **Channel kosong** | Bila channel papan tidak diisi, papan itu ikut channel papan utama. |
| **Angka ikut naik** | Saat reaksi bertambah, angka di pesan sorotan **diperbarui** (bukan mengirim ulang); turun di bawah ambang → sorotan papan itu dihapus. |
| **Anti-loop** | Pesan yang berada di channel papan mana pun tidak akan disorot lagi. |
| **Dashboard** | Halaman **🧩 Konten & interaksi** → panel *Papan sorotan (varian)*: daftar papan + tombol hapus, form tambah (nama, emoji, ambang, channel, warna), dan setelan **warna embed** papan utama. |

## 5. ✅ Gerbang Verifikasi Anti-Bot (`/verifikasi`)
- **`/verifikasi pasang channel:#verifikasi role:@Member`** — panel dengan tombol **✅ Verifikasi Saya**.
- Member baru klik sekali → langsung dapat role akses, tanpa perlu Admin menunggu. Cocok dipadukan dengan `/autorole`.
- **`/verifikasi status`** & **`/verifikasi matikan`** — pantau / matikan kapan saja.
- Tombol bersifat **persisten** (`custom_id`), jadi tetap berfungsi setelah bot restart.

## 6. 📌 Sticky Message — Petunjuk Selalu di Bawah (`/sticky`)
- **`/sticky pasang isi:"Baca #rules dulu sebelum chat!" channel:#umum judul:"📌 Aturan"`**
- Setiap ada obrolan baru, bot menurunkan ulang pesan petunjuk ke bawah channel (pesan lama dihapus).
- **Anti-spam:** jeda minimum **5 detik** per channel (`STICKY_MIN_INTERVAL_SEC`), jadi channel ramai tidak dibanjiri bot.
- **`/sticky lepas`** & **`/sticky status`** — cabut / lihat daftar channel sticky.

## 7. 👤 Kartu Profil & Server (`/info`)
- **`/info user member:@Warga`** — umur akun, tanggal bergabung, jumlah role, plus **peringatan keamanan** otomatis jika akun masih **< 7 hari** (indikasi akun raid).
- **`/info server`** — total member (manusia vs bot), online, boost, jumlah channel, status verifikasi & auto role, pemilik, dan tanggal server dibuat.

## 8. 🗂️ Perawatan: Backup Otomatis & Log Error (`/perawatan`)
- **`/perawatan atur backup_channel:#bot-backup log_channel:#bot-log`** — backup konfigurasi otomatis tiap **7 hari** (`BACKUP_INTERVAL_DAYS`) & laporan error masuk ke channel.
- **`/perawatan backup`** — kirim berkas ZIP berisi seluruh `data/*.json` saat itu juga (penyelamat saat Wispbyte rebuild bersih).
- **`/perawatan status`** — channel backup/log, waktu backup terakhir, ukuran arsip, & RAM bot.
- Error Slash Command maupun error event otomatis diringkas ke channel log (tanpa membocorkan API key — sudah disanitasi) dan jejaknya tampil di **`/status`**.

## 9. 💡 Kotak Saran (`/saran`) & 📝 Pembuat Embed (`/embed`)

**Kotak saran** — ala Carl-bot, tapi tanpa dashboard:

| Command | Siapa | Fungsi |
| :--- | :--- | :--- |
| `/saran pasang channel:#saran` | Admin | Tentukan channel kotak saran (`nonaktifkan:True` untuk mematikan) |
| `/saran kirim teks:...` | Semua | Kirim usulan → muncul sebagai embed dengan tombol **👍 / 👎** |
| `/saran daftar status:baru` | Semua | Lihat saran terbaru + skor voting |
| `/saran status id:3 status:diterima` | Staff | Ubah status (pesan asli ikut berubah) + memberi tahu pengusul |
| `/saran hapus id:3` | Admin | Hapus saran beserta pesannya |

- **Satu member satu suara**; memilih sisi lain akan **memindahkan** suara, bukan menambah.
- Tombol **tahan restart** (persistent view) — voting tetap jalan setelah bot restart.
- Status: 🆕 baru · 🛠️ dikerjakan · ✅ diterima · ❌ ditolak. Maks 20 saran tersimpan per server.

**Pembuat embed** — pengumuman cantik tanpa perlu tahu format:

| Command | Fungsi |
| :--- | :--- |
| `/embed buat channel:#pengumuman warna:ungu` | Buka **formulir** (judul, isi, URL banner, footer) → langsung terkirim |
| `/embed cepat channel:#x judul:"..." isi:"..."` | Kirim cepat tanpa formulir |
| `/embed variabel` | Daftar variabel `{member.mention}`, `{server.members}`, `{now_relative}`, … |
| `/embed sebagai nama:"📢 Pengumuman" isi:"..."` | Kirim dengan **nama & avatar sendiri** lewat webhook |
| `/embed webhook` | Cek / hapus webhook identitas yang dipakai bot |

Warna menerima `#9B59B6`, `ungu`, `biru`, `merah`, `hijau`, `emas`, `abu`. Hanya **staff** (Manage Messages/Server) yang bisa mengirim.

**Identitas kustom (webhook).** `/embed sebagai` mengirim pesan sebagai *siapa pun* pilihanmu
("📢 Pengumuman Server", "🎉 Tim Event") lengkap dengan avatar — ide dari Discohook. Bot membuat
satu webhook per channel lalu memakainya ulang (`data/webhooks.json`), jadi tidak membuat webhook
baru setiap kali. Butuh izin **Manage Webhooks**; mention massal dinonaktifkan agar tidak bisa
dipakai men-*ping* `@everyone` diam-diam. Tujuan bisa channel teks **atau thread**.

**Tautan embed (`/embed tautan`).** Ingin tautan yang tampil sebagai **embed cantik** di Discord
(judul, deskripsi, gambar) tetapi saat diklik membuka situsmu — persis *Link Embeds*-nya Discohook?
Bot membuat tautan ke halaman `/l/<kode>` di situs dokumentasi (Vercel) ini:

```text
/embed tautan url:https://situs.kamu/panduan judul:"Panduan Server" isi:"Semua aturan & tips" gambar:https://…/banner.png
→ https://ai-discord-chat-site.vercel.app/l/eyJ0IjoiUGFuZHVhbiBTZXJ2ZXIiLCJkIjoi…
```

- Halaman itu memuat tag `og:` (judul, deskripsi, gambar) sehingga Discord menampilkan embed, lalu
  **mengalihkan pengunjung** ke `url` tujuan lewat `<meta http-equiv="refresh">`.
- **Tanpa database**: seluruh isi embed dipaketkan ke dalam kode pada URL, jadi tautan lama tetap
  hidup walau bot mati dan tidak ada data yang tersimpan di server bot.
- Batasan: URL maksimal ±1.300 karakter (kode ≤1.200), jadi ringkas judul/isi — gambar memakai
  tautan, bukan unggahan. Maksimal **50 tautan** tercatat per server.
- `/embed tautan daftar` melihat yang sudah dibuat; `/embed tautan hapus` hanya menghapus catatan
  (halaman tetap bisa dibuka — hapus pesannya bila ingin benar-benar hilang).
- Alamat situs diatur lewat env `SITE_BASE_URL` (bawaan `https://ai-discord-chat-site.vercel.app`).
  Caranya: `site/api/l/[id].js` + rewrite `/l/:id` di `site/vercel.json` — keduanya sudah ada di repo,
  jadi cukup deploy `site/` seperti biasa. Kalau situs belum dideploy, tautan akan 404.

## 10. 🔊 Temp Voice: Voice Room Sementara (`/tempvoice`)

Cukup satu voice channel sebagai "tombol" pembuat room — konsep sama dengan ProBot/YAGPDB.

**Pemasangan (1 menit):**
1. Buat voice channel baru, misal **➕ Buat Voice**, di kategori yang kamu mau.
2. Jalankan `/tempvoice atur hub:#➕ Buat Voice`.
3. Selesai — member yang masuk ke channel itu langsung dipindahkan ke room pribadinya.

| Command | Siapa | Fungsi |
| :--- | :--- | :--- |
| `/tempvoice atur hub:#x nama:"🔊 Room {user}" limit:5` | Admin | Aktifkan hub & atur template nama/batas |
| `/tempvoice status` | Semua | Lihat hub & room yang sedang aktif |
| `/tempvoice kunci aktif:True` | Pemilik room | Kunci/buka room |
| `/tempvoice nama nama:Ngobrol Santai` | Pemilik room | Ganti nama room |
| `/tempvoice limit jumlah:4` | Pemilik room | Batasi jumlah orang (0 = bebas) |
| `/tempvoice tendang member:@x` | Pemilik room | Keluarkan orang dari room |

Detail penting:
- **Hemat kuota channel:** maksimal **30 room** per server, dihapus otomatis saat kosong (Discord membatasi 500 channel/server).
- **Aman restart:** daftar room di `data/temp_voice.json`; room yatim dibersihkan lewat penyapuan tiap 5 menit.
- **Tidak mengganggu musik:** listener hanya menyentuh channel hub & room yang dibuatnya sendiri.
- **0 kuota AI.**

## 11. 🏷️ Tag Jawaban Siap Pakai (`/tag`)

Jawaban yang paling sering ditanya staf (`aturan`, `harga`, `cara refund`) disimpan
sekali, lalu dipanggil kapan saja oleh siapa pun. **Tanpa AI sama sekali** — isi tag
tidak pernah dikirim ke Gemini, jadi 0 kuota dan tidak bisa "dikarang" model.

| Command | Fungsi |
| :--- | :--- |
| `/tag lihat nama:aturan` | Tampilkan isi tag (siapa pun boleh). Nama bisa dicari langsung dari dropdown. |
| `/tag daftar` | Daftar semua tag server + jumlah pemakaian. |
| `/tag cari kata:refund` | Cari tag lewat **nama atau isi** — berguna saat staf lupa nama tag-nya. |
| `/tag buat nama:aturan isi:…` | *(Staf)* Buat tag baru. |
| `/tag ubah nama:aturan isi:…` | *(Staf)* Perbarui isi tag. |
| `/tag hapus nama:aturan` | *(Staf)* Hapus tag. |

Detail penting:
- Nama tag **dinormalisasi** otomatis (`Aturan Server!` → `aturan-server`) supaya mudah dipanggil.
- Maksimal **100 tag/server**, isi maks **1.800 huruf** (batas embed), tanpa biaya kuota.
- Penghitung `dipakai` membantu melihat tag mana yang benar-benar berguna (dan mana yang usang).
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🏷️ Tag jawaban siap pakai* — tambah/perbarui, hapus per tag, lihat statistik pemakaian, dan **sakelar aktif/nonaktif** (data tetap tersimpan). Jalur tulis: `POST /api/konten` (`tag-simpan`, `tag-hapus:<nama>`, `tag-aktif:1|0`).
- Data di `data/tags.json`; tombol tes **Tag jawaban server** hanya menyimulasikan pencarian tanpa menaikkan penghitung.

## 12. 🏅 Lencana Bertingkat (`/lencana`)

Pencapaian yang **dihitung dari data yang sudah dicatat bot** (jumlah pesan, menit voice,
level, riwayat menang undian). Tidak ada pelacakan baru, tidak ada tabel tambahan, dan
**0 kuota AI**.

| Lencana | Tangga tingkat |
| :--- | :--- |
| 💬 Rajin Ngobrol | 50 · 250 · 1.000 · 5.000 · 15.000 pesan |
| 🎙️ Penghuni Voice | 60 · 300 · 1.200 · 5.000 menit voice |
| 📈 Pendaki Level | 5 · 10 · 25 · 50 level (prestise menambah 100) |
| 🎉 Hoki Undian | 1 · 3 · 10 kali menang undian |

| Command | Fungsi |
| :--- | :--- |
| `/lencana lihat [member]` | Lencana + bar progres + sisa menuju tingkat berikutnya. |
| `/lencana papan` | Papan lencana server (10 teratas, medali 🥇🥈🥉). |
| `/lencana periksa [member]` | *(Staf)* Segarkan lencana sekarang — berguna setelah impor data level. |
| `/lencana atur channel:… aktif:…` | *(Admin)* Channel pengumuman lencana & sakelar global. |
| `/lencana role kunci:… tingkat:… role:…` | *(Admin)* Role hadiah per tingkat (kosongkan `role` untuk menghapus). |

Detail penting:
- Pemeriksaan otomatis menempel di alur XP pesan & voice, jadi tidak ada pekerjaan latar
  tambahan dan tidak menambah beban CPU server Free Tier.
- Pemberian role hadiah **idempoten**: tingkat yang sudah diumumkan tidak diulang, dan
  pemberian lencana selalu aman walau bot restart (tersimpan di `data/achievements.json`).
- Maksimal **500 member terdata per server** (yang paling lama tidak aktif dikeluarkan lebih dulu).
- **Panel dashboard:** halaman **⚙️ Inti & level** → *🏅 Lencana bertingkat* — setelan channel
  pengumuman, sakelar aktif/nonaktif, pemasangan/penghapusan role hadiah per tingkat, tangga
  tingkat, dan papan lencana. Jalur tulis: `POST /api/lencana`
  (`lencana-setelan`, `lencana-role`, `lencana-hapus:<kunci>:<tingkat>`).
- Tombol tes **Lencana bertingkat** hanya menghitung progres (simulasi) — tidak memberi role
  dan tidak mengirim pengumuman.

## 13. 🔔 Highlight Kata Kunci (`/pantau`)

Member memilih kata kunci sendiri (mis. `open order`, nama barang, nama dirinya), lalu bot
mengirim **DM** berisi tautan pesan, penulis, channel, dan cuplikan singkat setiap kali kata
itu muncul di chat. Khas bot besar, tapi di sini **tanpa AI** dan **tanpa menyimpan isi pesan**.

| Command | Fungsi |
| :--- | :--- |
| `/pantau tambah kata:open order` | Pantau satu kata/frasa (maks **10** per member). |
| `/pantau hapus kata:open order` | Berhenti memantau satu kata. |
| `/pantau daftar` | Lihat kata kunci, channel & kata yang diabaikan, jumlah DM terkirim. |
| `/pantau abaikan channel:#umum` | Channel ini tidak memicu highlight untukmu. |
| `/pantau abaikan kata:spam` | Kata ini tidak memicu highlight untuk siapa pun. |
| `/pantau bersihkan` | Hapus semua setelan highlight milikmu (opt-out total). |
| `/pantau atur aktif:… abaikan_channel:…` | *(Admin)* Sakelar server & channel yang selalu diabaikan. |

Detail penting:
- **Pencocokan batas kata** (`bot` cocok di “bot itu”, tidak di “robot”), tidak peka huruf besar.
- **Anti-banjir:** jeda 5 menit untuk kata yang sama per member + maksimal **5 DM/menit**
  (bisa diturunkan dari dashboard). Satu pesan = maksimal satu DM per member.
- Penulis pesan tidak dikirimi DM untuk pesannya sendiri; DM yang ditutup member dilewati
  tanpa mengganggu chat.
- Tidak ada isi pesan yang ditulis ke disk — `data/highlights.json` hanya berisi kata kunci,
  daftar abaikan, dan penghitung.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🔔 Highlight kata kunci* — sakelar
  aktif, batas DM/menit, daftar channel yang diabaikan, daftar pelanggan + tombol hapus.
  Jalur tulis: `POST /api/konten` (`pantau-setelan`, `pantau-hapus:<user_id>`).
- Tombol tes **Highlight kata kunci** hanya menyimulasikan pencocokan kalimat contoh —
  tidak ada DM yang dikirim.

## 14. 💌 Curhat Anonim (`/curhat`)

Satu channel khusus untuk **curhat tanpa nama** ala bot besar. Pesan diposting bot dengan
nomor urut dan tanpa penulis; bot **tidak menyimpan isi curhat**. 0 kuota AI.

| Command | Fungsi |
| :--- | :--- |
| `/curhat kirim teks:…` | Kirim curhat anonim ke channel yang sudah diatur. |
| `/curhat atur channel:… aktif:… izinkan_link:… jeda_menit:…` | *(Admin)* Pilih channel, sakelar, izin tautan, jeda per orang. |
| `/curhat hapus nomor:…` | *(staf)* Hapus curhat yang melanggar + catatannya. |

Detail penting:
- **Batas:** 10–900 huruf, maksimal **3 curhat/jam** per penanda penulis, jeda bawaan **5 menit**.
- **Tautan** diblokir kecuali Admin mengizinkan (`izinkan_link`).
- Identitas penulis hanya disimpan sebagai **hash 12 huruf** (`sha256`) — cukup untuk
  menegakkan jeda, tapi tidak membocorkan siapa penulisnya.
- `data/confessions.json` hanya berisi setelan, **nomor**, `pesan_id`, `channel_id`, waktu,
  dan hash — **tanpa teks curhat**.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *💌 Curhat anonim* — channel,
  sakelar, izin tautan, jeda, daftar curhat terakhir (nomor + penanda hash) + tombol hapus
  catatan. Jalur tulis: `POST /api/konten` (`curhat-setelan`, `curhat-hapus:<nomor>`).
- Tombol tes **Curhat anonim** menjalankan validasi aturan pada kalimat contoh — tidak ada
  pesan yang diposting dan nomor tidak terpakai.

## 15. 🔗 Voice Linking (`/tempvoice tautkan`)

Ala bot besar: selama member berada di voice channel, bot memberi **role khusus** dan membuka
**channel teks privat** untuk voice itu. Keluar voice → akses dicabut otomatis. **0 kuota AI.**

| Command | Fungsi |
| :--- | :--- |
| `/tempvoice tautkan` | Lihat status voice linking (role, channel privat, jumlah channel). |
| `/tempvoice tautkan aktif:True role:@Warga Voice` | *(Admin)* Nyalakan & pilih role selama di voice. |
| `/tempvoice tautkan channel_privat:True kategori:#Voice` | *(Admin)* Buat channel teks privat per voice, di kategori tertentu. |
| `/tempvoice tautkan hapus_kosong:False` | *(Admin)* Biarkan channel privat tetap ada walau voice kosong. |

Cara kerja:
- Saat member **masuk** voice: role diberikan (hanya bila dia belum memilikinya) dan channel
  `⌨️-<nama voice>` dibuat/disiapkan. `@everyone` **tidak** bisa melihat; hanya member yang
  sedang di voice itu yang mendapat izin lihat + kirim.
- Saat member **keluar**: izinnya dicabut. Bila voice channel jadi kosong dan
  `hapus_kosong` menyala, channel privatnya dihapus. Pindah voice **tidak** mencabut role.
- Role yang **sudah dimiliki member sebelum masuk voice** tidak akan dicabut saat keluar —
  bot hanya mencabut role yang benar-benar ia berikan.
- Batas **40** channel privat per server. Butuh izin **Manage Roles** & **Manage Channels**.
- Satu listener voice dipakai bersama XP voice, audit log, dan Temp Voice (supaya tidak saling
  menimpa) — lihat `cogs/events_cog.py`.
- **Panel dashboard:** halaman **🧩 Konten & interaksi** → *🔗 Voice linking* — sakelar, role,
  channel privat, hapus-saat-kosong, kategori, daftar channel yang dikelola + tombol lepas.
  Jalur tulis: `POST /api/konten` (`voice-setelan`, `voice-lepas:<voice_id>`).
- Tombol tes **Voice linking** hanya memeriksa setelan & keberadaan role — tidak mengubah role
  atau channel siapa pun.
