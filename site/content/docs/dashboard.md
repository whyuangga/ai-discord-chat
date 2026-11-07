---
title: "J. Dashboard Web (DASHBOARD_TOKEN)"
description: "Dashboard web ringan di proses yang sama: pantau status dan kontrol fitur dari browser."
icon: "dashboard"
weight: 10
toc: true
---

Satu server web ringan (proses yang sama dengan bot) untuk memantau **dan** mengatur bot
tanpa membuka Discord: status, pemakaian AI, papan level, peta fitur, **56 setelan server
dalam 14 halaman** (satu grup fitur = satu halaman), **kirim embed/webhook**, unggah banner
& kartu sambutan, kotak masuk tiket, kendali giveaway, panel moderasi (antrean laporan &
banding), generator gambar & prompt AI server, petunjuk privasi mandiri, serta **24 tombol tes fitur**.
Template halaman depan ada di [README](../README.md#-dashboard-web-sekilas); rincian tiap
bagian ada di [Dashboard web (panel admin lengkap)](#dashboard-web-panel-admin-lengkap).

| Aspek | Detail |
| :--- | :--- |
| **Cara nyala** | Isi `DASHBOARD_TOKEN` (kata sandi acak) **dan** sediakan port (`DASHBOARD_PORT`, atau otomatis dari `SERVER_PORT`/`PORT` panel). Kosong = dashboard mati. |
| **Akses** | `http://<ip-server>:<port>/?token=<DASHBOARD_TOKEN>` — token juga bisa lewat header `X-Dashboard-Token` / `Authorization: Bearer` atau field tersembunyi pada form. |
| **Endpoint baca** | `/` (HTML), `/api/status`, `/api/pemakaian?guild=<id>`, `/api/level?guild=<id>`, `/api/kontrol?guild=<id>`, `/api/fitur?guild=<id>`, `/api/setelan?guild=<id>`, `/healthz` (tanpa token). |
| **Endpoint tulis** | Empat belas jalur `POST`, semuanya **wajib token**: `/api/aksi` (setelan), `/api/ai` (buat gambar atau simpan prompt server; prompt/gambar tidak masuk audit), `/api/kirim` (pesan/embed/webhook + pratinjau), `/api/konten` (buat/hapus konten), `/api/unggah` (banner & kartu), `/api/uji` (tes fitur), `/api/tiket` (balas/tutup tiket, panel tiket, topik, catatan staf), `/api/panel` (tombol/dropdown & verifikasi),
`/api/giveaway` (buat/hentikan/reroll giveaway, template, & setelan bawaan),
`/api/transkrip` (hapus arsip transkrip tiket),
`/api/keamanan` (penguji aturan anti-spam), `/api/lencana` (setelan lencana), `/api/bangun` (pratinjau tema/AI, terapkan, batal, bongkar tercatat),
`/api/moderasi` (setelan jalur laporan, status antrean, cari kasus, cabut temp-ban). Aksi lama (`level`, `ekonomi`, `tumbuh`, `antispam`, `antinuke`) tetap didukung. |
| **Endpoint unduh** | `/api/tren` (tren AI 7 hari), `/api/ekspor?jenis=…` (CSV level/moderasi/tiket/pemakaian), & `/api/transkrip?kode=…` (transkrip HTML satu tiket). |
| **Arsip transkrip** | Halaman `/transkrip` berisi kotak pencarian (dicari di **isi percakapan**, bukan cuma judul) + tautan buka/hapus. Tanpa JavaScript, tanpa login tambahan. |
| **Setelan** | **56 fitur** dalam 5 grup: inti/level/ekonomi, sambutan & pamit, keamanan, tiket & sapaan harian, konten & interaksi. |
| **Whitelist** | Hanya kunci yang terdaftar di `dashboard_admin.FITUR` yang bisa dijalankan — nama fungsi bebas tidak pernah dieksekusi. |
| **Mitigasi** | Halaman `/` tetap **GET-only** (POST ke `/` ditolak). Tidak ada `PUT`/`DELETE`/`PATCH`. Tombol Hapus hanya membuang satu item. Perubahan dicatat sebagai metadata di `data/dashboard_audit.json` dan log bot; prompt bebas serta isi gambar tidak direkam. |
| **Unggahan** | Banner/gambar bisa diunggah dari dashboard (`DASHBOARD_UPLOAD_MB`, bawaan 8 MB) ke `data/uploads/` lalu dipakai sebagai banner panel, gambar embed, atau lampiran webhook. |
| **Biaya** | Membuka/mengatur dashboard tidak memanggil AI; `/gambar` dan rancangan AI `/bangun` memakai kuota hanya saat diminta. ±2–4 MB RAM, tanpa dependency baru, tetap **1 proses**. |
| **Tanpa JS** | HTML dirender di server (semua form HTML biasa), `meta refresh` bawaan **30 detik** (`DASHBOARD_REFRESH_SEC`; `0` = mati) dan **bisa diatur sendiri lewat satu dropdown di header** tanpa restart → ringan dibuka dari HP. |

> ⚠️ Dashboard hanya bisa dibuka dari luar bila panel hosting memberi **port allocation**.
> Di Wispbyte cek tab **Network / Allocations**; bila tidak ada alokasi, dashboard otomatis
> tidak menyala dan bot tetap berjalan normal (tidak ada error).

## Dashboard web (panel admin lengkap)

Bot menjalankan satu halaman web di port privat (`DASHBOARD_PORT`, token di env) yang
memuat **status bot, pemakaian AI, papan level, peta fitur, dan pengaturan server** —
fitur dibagi ke **14 halaman** per grup, tanpa dependency baru dan tetap satu proses. AI hanya dipanggil secara eksplisit untuk gambar atau rancangan `/bangun`.

| Bagian | Isi |
| :--- | :--- |
| **Pemilih server** | dropdown server di pojok atas (muncul otomatis bila bot ada di lebih dari satu server) — tanpa login, cukup token |
| **Menu ☰ & navigasi** | header menempel di atas + menu pindah halaman (satu halaman per grup fitur); di HP menu berubah jadi **hamburger** (CSS murni, tanpa JavaScript) |
| **Status & pemakaian** | uptime, RAM, latensi, server/member, status Gemini, token masuk/keluar, cache hit, FAQ lokal |
| **Tren 7 hari** | grafik batang SVG (operasi AI & cache per hari) — dirender di server, tanpa JavaScript |
| **Peta fitur** | fitur apa yang sudah dipakai (panel, formulir, pengumuman, tautan, pemicu) + ✅/⬜ |
| **Kontrol Cepat** | sakelar level, ekonomi, & pertumbuhan dengan **tombol yang mengikuti keadaan** (“Nonaktifkan” saat aktif, “Aktifkan” saat mati) + mode anti-spam & aksi anti-nuke |
| **Setelan server** | **56 setelan** dalam 5 grup (lihat tabel di bawah) |
| **Kirim pesan & embed** | kirim pengumuman sekali jalan, atau lewat **identitas webhook** (nama & avatar sendiri), lengkap dengan **pratinjau sebelum kirim** |
| **Banner & gambar** | **unggah banner** (PNG/JPG/GIF/WEBP) lalu pakai untuk banner panel atau gambar embed, tanpa perlu URL publik |
| **Kartu sambutan** | **unggah sendiri** tiga gambar kartu (sambutan, pamit, boost) di halaman `/sambutan` — satu bagian per kartu; disimpan di `data/media/`, dikirim ulang sebagai lampiran jadi tidak kedaluwarsa |
| **Kartu rank** | Halaman `/inti` → panel **🖼️ Kartu rank (PNG)**: pratinjau `GET /api/rank.png` memakai perender yang **sama** dengan `/level kartu`, sakelar hidup/mati, warna aksen hex, unggah/hapus latar, & tombol tes render. |
| **Tes fitur** | tombol **Kirim tes** ada di halaman fiturnya (sambutan, perpisahan, boost, pengumuman, panel, tiket, giveaway, koran pagi, koneksi AI, ekspor). Subjek tes **tidak perlu ID**: kosongkan saja → bot memakai **pemilik server** |
| **Buat konten** | pengumuman terjadwal, tautan embed `/l/<kode>`, panel menu (+ langsung terkirim), **formulir (modal)**, **pemicu saat member bergabung** |
| **Konten tersimpan** | daftar pengumuman/tautan/panel/formulir/webhook + tombol **Hapus** |
| **Kotak masuk formulir** | panel *📬 Kotak masuk formulir*: semua jawaban formulir dikumpulkan sebagai **antrean** (nomor, formulir, pengirim, waktu, status **baru/selesai**) — jawaban bisa dibaca langsung, **tandai selesai**, **buka lagi**, atau **hapus**. Batas 200/server, dibersihkan otomatis setelah 30 hari. Jalur tulis: `POST /api/konten` (`inbox-selesai:<nomor>`, `inbox-buka:<nomor>`, `inbox-hapus:<nomor>`). |
| **AI & privasi** | halaman `/ai`: generator `/gambar` (prompt, channel, gaya, rasio, lampiran acuan opsional) + prompt kepribadian AI server. Lampiran divalidasi dan diproses di memori; prompt tidak dicatat di audit. Per-member memakai `/setelan-ai`; `/dataku` dan `/hapusdataku` tetap ephemeral dan hanya untuk pemilik akun. |
| **Bangun server** | halaman `/bangun`: pilih satu dari 15 tema (0 kuota AI) atau rancang dengan AI; tinjau pratinjau, tekan Terapkan secara eksplisit, lihat riwayat, dan bongkar hanya item tercatat |
| **Giveaway** | halaman `/giveaway`: buat giveaway dari HP (hadiah, channel, durasi, pemenang, level, umur akun, role bonus), **hentikan**, **undi ulang**, simpan/hapus **template**, dan atur **setelan bawaan** — semua memakai fungsi yang sama dengan command Discord |
| **Kotak masuk tiket** | daftar tiket aktif (umur, diam, status, SLA) + **balas** & **tutup** langsung dari web, plus **pasang panel tiket** |
| **Moderasi** | Halaman `/moderasi`: antrean **laporan member** & **banding** (ubah status + catatan), **setelan jalur laporan** (channel, cooldown, DM pelapor), daftar **temp-ban** dengan tombol cabut, **pencarian kasus** (nomor/ID/kata/jenis aksi), **statistik staf** 30 hari, & kasus terbaru |
| **Editor panel** | tambah/hapus **tombol** (role, tautan, perintah, alur, formulir) & **dropdown role** — panel di Discord langsung disegarkan |
| **Panel verifikasi** | pasang/matikan gerbang verifikasi (tombol sekali klik → role) tanpa command |
| **Ekspor CSV** | unduh data level, moderasi, tiket, & pemakaian AI langsung dari browser |
| **Riwayat perubahan** | 8 perubahan terakhir dari dashboard (siapa-waktu-nilai-hasil) |

### Tampilan (tema gelap + General Sans)

| Bagian | Nilai |
| :--- | :--- |
| **Latar** | `#0D0D0F` (hitam netral) — sama untuk halaman utama, halaman pratinjau embed, dan halaman hasil submit |
| **Warna teks** | `#FFFFFF`; teks sekunder memakai putih transparan (`rgba(255,255,255,.62)`) |
| **Font** | **General Sans** (Fontshare, bobot 400/500/600/700) dimuat lewat `api.fontshare.com`; cadangan `Inter` → `system-ui` → `Segoe UI` bila CDN tidak terjangkau |
| **Aksen** | ungu `#8B7CFF` (fokus, tautan), biru Discord `#5865F2` (tombol utama), hijau `#4ADE80` (berhasil), kuning `#FBBF24` (peringatan), merah `#E5484D` (tombol hapus/tutup) |
| **Bentuk** | kartu radius 14 px, garis `rgba(255,255,255,.09)`, tanpa gradien norak, tanpa JavaScript |
| **Aksesibilitas** | `color-scheme: dark`, outline fokus ungu 2 px pada input/select/tombol, `prefers-reduced-motion` mematikan transisi |

Semua warna & font tinggal di satu modul, `dashboard_tema.py` (`LATAR`, `TEKS`,
`FONT_STACK`, `CSS_HALAMAN`, `CSS_PRATINJAU`, `CSS_HASIL`) — mengganti tema cukup
mengubah satu berkas itu, tanpa menyentuh `web_dashboard.py` atau `dashboard_ui.py`.

### Satu grup fitur = satu halaman (menu ☰ di HP)

Dashboard tidak lagi satu halaman gulung panjang, dan **tidak ada halaman tes gabungan**.
Fitur yang saling berhubungan digabung dalam **satu halaman per grup**, jadi mengatur lalu
menguji satu kelompok fitur tidak perlu berpindah-pindah halaman.

| Halaman | Isi | Panel |
| :--- | :--- | :--- |
| `/` | Ringkasan: status, pemakaian AI, jenis operasi, tren 7 hari, channel teramai, papan level | 6 |
| `/ai` | Generator gambar + lampiran acuan, prompt server, privasi mandiri, **tes koneksi AI** | 4 |
| `/sambutan` | **sambutan + pamit + boost** jadi satu halaman: tiap bagian punya setelan, **gambar kartu**, & **tombol tes** sendiri (`#p-welcome`, `#p-goodbye`, `#p-boost`) | 1 |
| `/inti` | **Kontrol Cepat** + setelan grup **inti, level, & ekonomi** (prefix, kartu rank, lencana, koin harian, …) | 4 |
| `/keamanan` | setelan **anti-spam, anti-nuke, pengaman raid, verifikasi, & anti-phishing** | 1 |
| `/moderasi` | Antrean laporan/banding, pencarian kasus, temp-ban, statistik staf, snipe | 2 |
| `/tiket` | Kotak masuk tiket + pasang panel tiket + setelan **tiket & sapaan harian** + arsip + **tes panel tiket** | 1 |
| `/konten` | **Konten & interaksi** (Auto-Chat AI, starboard, saran, fakta harian, koran pagi, backup, …) + statistik & tes | 2 |
| `/bangun` | Tema lokal atau rancangan AI; pratinjau, Terapkan eksplisit, riwayat & bongkar item tercatat | 1 |
| `/giveaway` | Buat/hentikan/undi ulang giveaway, template, syarat & setelan bawaan | 1 |
| `/kirim` | Kirim pesan/embed + pratinjau, banner & unggahan | 2 |
| `/buat` | Buat pengumuman/tautan/panel/formulir/pemicu + konten tersimpan & kotak masuk formulir | 3 |
| `/panel` | Editor tombol & dropdown + gerbang verifikasi + **tes panel** | 1 |
| `/ekspor` | Ekspor CSV + riwayat perubahan + **tes ekspor** | 2 |

Aturan mainnya:

| Bagian | Perilaku |
| :--- | :--- |
| **Menu halaman** | 📡 Ringkasan · 🤖 AI & Privasi · 👋 Sambutan · ⚙️ Inti · 🛡️ Keamanan · 🚨 Moderasi · 🎫 Tiket · 🧩 Konten · 🏗️ Bangun · 🎁 Giveaway · ✉️ Kirim · ➕ Buat · 🎨 Panel · 📥 Ekspor; halaman aktif ditandai `aria-current="page"` (warna ungu) |
| **Token & server terbawa** | setiap tautan menu menyertakan `?token=…&guild=…`, jadi pindah halaman tidak pernah keluar sesi (tetap tanpa login) |
| **Hamburger di HP** | di layar ≤ 820 px menu dilipat jadi **☰ Menu**; buka/tutup lewat `<input type="checkbox">` + CSS, **tanpa JavaScript** (tetap bisa diakses keyboard) |
| **Header menempel** | bar atas (`position: sticky`) selalu terlihat: judul halaman + server, versi, waktu baca, & pemilih server |
| **Anchor tetap ada** | tiap panel & bagian masih punya `id` (`#p-welcome`, `#p-inti`, `#p-tiket`, …) + `scroll-margin-top`, jadi `…/sambutan#p-goodbye` bisa dipakai sebagai bookmark |
| **Bookmark lama** | `/setelan` → `/inti`, `/perpisahan` & `/boost` → `/sambutan`, `/uji` → `/ai` (semua `303`); anchor lama (`#p-setelan` → `/inti`, `#p-perpisahan` → `/sambutan`) ikut diarahkan; `/api/*` tidak berubah |

### Setelah menekan Simpan

Form memakai pola **POST → redirect (303) → GET**: setelah menyimpan, kamu kembali ke
**halaman asal** dan panel yang sama (`/kirim#p-banner`, `/inti#p-kontrol`, …) lalu
melihat kotak pesan ✅ berisi hasilnya — nilai barunya sudah
terbaca dari JSON, jadi tidak perlu klik “kembali” atau muat ulang. Kalau gagal pun kamu
tetap dikembalikan ke halaman fiturnya (`…?pesan=…&ok=0`) dengan kotak ⚠️ berisi alasannya —
tidak ada lagi halaman buntu tanpa jalan pulang.
Endpoint JSON (`Content-Type: application/json`) tetap menerima `200`/`400` + `{"ok": …}`
tanpa redirect.

> 🐞 **Perbaikan**: saklar **Level & XP** dulu kembali ke “Aktif” setelah disimpan jadi
> “Nonaktif”, karena pembacaan setelan memakai `get_level_config()` yang membuat konfigurasi
> default (`enabled: True`) dan `set_level_config(aktif=False)` menghapus konfigurasi.
> Sekarang dashboard memakai `peek_level_config()` (baca tanpa membuat config) dan
> `set_level_enabled()` (menyimpan `enabled: False` tanpa menghapus setelan XP/channel/season).

### Kartu sambutan sendiri (unggah dari dashboard)

Tiap bagian di halaman `/sambutan` punya slot unggahnya sendiri — **satu menu unggah,
di dalam bagian fiturnya**:

| Bagian di `/sambutan` | Slot | Dipakai saat | Berkas |
| :--- | :--- | :--- | :--- |
| `#p-welcome` | **Sambutan** | member baru bergabung (mode kartu *statis* / *dinamis*) | `data/media/welcome_<id>.png` |
| `#p-goodbye` | **Perpisahan** | member keluar (otomatis bila gambarnya ada) | `data/media/goodbye_<id>.png` |
| `#p-boost` | **Boost** | member nge-boost server | `data/media/boost_<id>.png` |

> Contoh gambar siap pakai (1024×420) bisa dibuat sendiri dengan AI image generator —
> gaya gelap `#0D0D0F` dengan aksen ungu/emas paling menyatu dengan kartu bot.

- Unggah: **PNG/JPG/GIF/WEBP**, maksimal 8 MB, isi berkas diperiksa lewat *magic bytes*
  (file `.exe` yang di-rename tetap ditolak). Gambar ditimpa per jenis, jadi tidak menumpuk.
- Pratinjau tampil langsung di dashboard (`/api/kartu/<jenis>?token=…`, wajib token).
- Tombol **Hapus kartu** mengembalikan bot ke tampilan teks/embed biasa.
- Pemilih **Tampilan kartu sambutan** ada di halaman `/sambutan` (satu tempat dengan kartunya). Ukuran gambar ideal **1024×420 px**.

### Bedanya “Kartu statis” dan “Kartu dinamis”

| Mode | Yang dikirim bot | Cocok untuk |
| :--- | :--- | :--- |
| 💬 **Teks saja** | pesan teks polos, tanpa gambar | server hemat kuota / tanpa gambar |
| 🖼️ **Kartu statis** | *embed*: gambar kartu yang kamu unggah dipakai apa adanya, plus **foto profil kecil** & teks sambutan | paling ringan — gambar dipakai ulang tanpa diolah |
| ✨ **Kartu dinamis** | bot **membuat gambar baru setiap kali** (Pillow): gambar kartu jadi latar, lalu ditimpa **foto profil bulat + nama member + “Member ke-N” + nama server** | server yang ingin tiap member dapat kartu bertuliskan namanya |

Ringkasnya: **statis = gambar buatanmu dikirim utuh**; **dinamis = gambar buatanmu dipakai
sebagai latar, lalu bot menambahkan nama & foto profil member**. Keduanya butuh gambar kartu
yang sudah diunggah — tanpa gambar, bot otomatis memakai mode teks.

### Uji fitur tanpa menunggu event (tombol di halaman fiturnya)

Tidak ada halaman tes gabungan: tombol **Kirim tes** ada di halaman fiturnya masing-masing.

| Halaman | Fitur | Subjek | Yang terjadi |
| :--- | :--- | :--- | :--- |
| `/sambutan` | 👋 Sambutan member baru | pemilik server (bisa diganti) | kirim contoh sambutan + sapaan asing (`force=True`, dedup dilewati) |
| `/sambutan` | 👣 Pesan perpisahan | pemilik server (bisa diganti) | kirim contoh kartu perpisahan |
| `/sambutan` | 💎 Ucapan boost | pemilik server (bisa diganti) | kirim contoh ucapan boost |
| `/buat` | ⏰ Pengumuman terjadwal | daftar pengumuman tersimpan | kirim satu pengumuman **sekarang** (jadwal aslinya tidak digeser) |
| `/panel` | 🧩 Panel menu | daftar panel tersimpan | segarkan panel di Discord supaya tombol/dropdown terbaru tampil |
| `/konten` | 📰 Koran pagi (digest) | — | buat contoh rubrik pagi; **tidak dikirim** ke channel |
| `/tiket` | 🎫 Panel tiket | channel | pasang ulang panel **Buka Tiket** di channel itu |
| `/` | 🤖 Koneksi AI (Gemini) | — | satu panggilan AI kecil; membuktikan API key, kuota, & jaringan sehat |
| `/ekspor` | 📥 Ekspor CSV | — | bangun CSV level; melaporkan jumlah baris data |

**Subjek tes tidak perlu ID.** Kolom *contoh atas nama* sudah terisi **👑 Pemilik server
(otomatis)** — tekan Kirim tes saja. Bisa juga pilih member lain dari dropdown, atau tempel
`@nama` / `<@id>` di kolom opsional. Akun bot sendiri **tidak pernah** dipakai sebagai
contoh (pemicu sambutan/perpisahan memang mengabaikan member bot).

Tes yang memakai AI (sambutan, perpisahan, boost, koran pagi, koneksi AI) memakan
**1 panggilan AI**; tes sambutan/boost/pengumuman/panel tiket mengirim pesan **sungguhan**
ke channel. Hasilnya tampil sebagai kotak ✅/⚠️ di **halaman fiturnya** (atau JSON bila
dipanggil sebagai API). Kalau gagal, alasannya spesifik: `GEMINI_API_KEY` kosong, channel
tujuan sudah dihapus, bot tidak punya izin **Kirim Pesan**, atau AI tidak menjawab.
Fitur ber-channel yang belum aktif menampilkan tombol **Atur dulu** alih-alih tombol tes.

### Beberapa channel untuk satu fitur

Setelan bertanda **channel** boleh diisi **lebih dari satu** — cukup centang di kotak
pilihan (tanpa JavaScript). Bot mengirim ke semua channel yang dicentang, dan satu channel
yang bermasalah tidak membatalkan pengiriman ke channel lain.

| Fitur | Bisa berapa channel |
| :--- | :--- |
| Channel sambutan · pesan pamit · ucapan boost | banyak |
| Channel pengumuman level (+ musim) | banyak |
| Log anti-spam · log anti-nuke · log tiket | banyak |
| Ucapan ulang tahun · backup otomatis | banyak |
| Auto-Chat AI · Galeri AI · Rangkum YouTube · Pencarian berita · Terjemahan otomatis | banyak (satu per channel) |
| **Koran pagi (digest)** · **Fakta harian** | **satu** (sengaja, sesuai permintaan) |
| Kategori tiket · kotak saran · gerbang verifikasi · starboard · log pertumbuhan | satu (satu kategori/pintu/papan, bukan siaran) |

Cara kerjanya: config menyimpan **daftar** (`channel_ids`, `log_channel_ids`, …) sekaligus
channel pertama di kunci lama (`channel_id`), jadi config lama di disk tetap terbaca tanpa
migrasi. Centang **🚫 Kosongkan** untuk mematikan fitur. Penjelasan teknis ada di modul
`channel_targets.py`.

### Setelan yang bisa diubah dari web (56 fitur)

| Grup | Fitur |
| :--- | :--- |
| 🧭 **Inti, level, & ekonomi** (10) | Level & XP, pengumuman naik level, channel pengumuman level, **kartu rank PNG**, **warna aksen kartu rank**, ekonomi koin, koin harian, pelacakan pertumbuhan, channel log pertumbuhan, prefix custom |
| 👋 **Sambutan & pamit** (10 — semuanya di halaman `/sambutan`, per bagian `#p-welcome`/`#p-goodbye`/`#p-boost`) | channel sambutan, sambutan via DM, kartu sambutan (mati/statis/dinamis), persona sambutan, **bahasa sapaan sambutan**, **latin & arti sapaan**, channel pamit, **bahasa kata perpisahan**, **latin & arti perpisahan**, channel ucapan boost |
| 🛡️ **Keamanan** (10) | mode anti-spam, deteksi huruf kapital, log anti-spam, aksi anti-nuke (+log), pengaman raid (+aksi), channel & role verifikasi, proteksi anti-phishing |
| 🎫 **Tiket & sapaan harian** (8) | sistem tiket, role staf, kategori, log, maksimal tiket terbuka, ping staf, rating tiket, channel ucapan ulang tahun |
| 🧩 **Konten & interaksi** (17) | starboard (+ambang & **warna embed**), **papan sorotan varian** (kelola di panel Konten), kotak saran, Auto-Chat AI, koran pagi, galeri AI, rangkum YouTube, pencarian berita, terjemahan otomatis, statistik server, fakta harian, channel backup, gaya bahasa AI, keamanan konten AI, jam tenang, zona waktu |

Pilih nilai di dropdown → **Simpan**. Perubahan langsung tersimpan ke JSON bot (tanpa
restart), dan setiap perubahan dicatat di `data/dashboard_audit.json` (maksimal 300 entri).

### Kirim embed & webhook

Form **Kirim pesan & embed** menerima: channel, judul, isi, warna, footer, gambar,
label+URL tombol, serta **identitas webhook** (nama & avatar). Kalau kolom identitas diisi,
pesan dikirim lewat webhook channel itu sehingga nama pengirim bisa berbeda dari bot —
praktis untuk "📢 Pengumuman Server". Isi boleh memakai variabel pesan
(`{server.name}`, `{now_long}`) yang diisi otomatis saat dikirim.

### Pratinjau sebelum kirim (seperti Discohook)

Form kirim punya dua tombol: **👀 Pratinjau dulu** dan **Kirim sekarang**.

| Tombol | Yang terjadi |
| :--- | :--- |
| **Pratinjau dulu** | bot merender embed mirip Discord (judul, isi, warna, gambar, footer, identitas webhook) + daftar **peringatan** — **tidak ada yang dikirim** |
| **Kirim sekarang** | dari halaman pratinjau, isian diteruskan apa adanya ke channel tujuan |

Yang diperiksa saat pratinjau (semuanya muncul sebagai daftar “Perlu diperiksa”):

- channel tujuan belum dipilih / bot tidak punya akses,
- judul & isi masih kosong, atau melebihi batas Discord (256 / 4000 karakter),
- warna tidak valid (`#5865F2` atau nama seperti `blurple`),
- **variabel tidak dikenal** seperti `{member.nama}` (ditampilkan apa adanya, jadi kelihatan),
- URL gambar/tombol bukan `http(s)`, tombol hanya terisi label atau hanya URL,
- tombol link dipakai bersamaan dengan identitas webhook (tidak didukung).

Pratinjau juga tersedia sebagai JSON untuk otomasi: kirim `pratinjau: true` ke `POST /api/kirim`
dengan header `Content-Type: application/json`.

### Unggah banner & gambar

Banner bisa diunggah langsung dari HP — tidak perlu hosting gambar atau URL publik.

| Langkah | Detail |
| :--- | :--- |
| **1. Unggah** | Panel **🖼️ Banner & gambar** → pilih berkas → **Unggah banner**. Berkas disimpan di `data/uploads/`. |
| **2. Pakai** | Di form **Kirim pesan & embed** atau **Panel menu**, pilih berkas di kolom *Unggah banner* **atau** pilih dari dropdown *banner tersimpan*. |
| **3. Hasil** | Embed memakai `attachment://<nama>` sehingga gambar ikut terkirim; panel menyimpan URL lampirannya sebagai `banner_url`. |
| **4. Panel lama** | Di daftar **Panel** (bagian *Konten tersimpan*), setiap panel yang sudah terkirim punya tombol **Ganti banner** dan **Hapus banner** — pesan aslinya langsung disunting, tanpa kirim ulang. |
| **Bersih-bersih** | Setiap banner di galeri punya tombol **Hapus** (kuota 20 berkas per server). |

Batasan & pengamanan:

- Format: **PNG, JPG, GIF, WEBP**. Isi berkas diperiksa lewat *magic bytes*, jadi file `.exe`
  yang diganti nama jadi `.png` tetap ditolak.
- Ukuran: `DASHBOARD_UPLOAD_MB` (bawaan **8 MB**, maksimal 25 MB). Batas body server
  menyesuaikan nilai ini — bukan 1 MB bawaan aiohttp.
- Nama berkas selalu dibuat ulang (`<guild>_<waktu>_<acak>.<ext>`), jadi aman dari path
  traversal dan tabrakan nama. Pratinjau hanya bisa dibuka dengan token pemilik server.
- **Ganti banner panel lama tidak menghapus pesannya**: bot menyunting pesan panel yang
  sama (`message.edit`) dengan lampiran baru, lalu memperbarui `banner_url` di
  `data/menus.json`. Tombol/dropdown yang sudah ada tetap berfungsi karena view didaftarkan
  ulang. Kalau Discord menolak komponen V2 (mis. klien lama), bot otomatis memakai versi
  embed klasik dengan banner yang sama. Tombol **Hapus banner** menghapus lampiran lama
  tanpa menyentuh isi panel.

### Kotak masuk tiket dari web

Panel **🎫 Kotak masuk tiket** menampilkan tiket yang belum selesai untuk server yang
sedang dipilih — jadi staf bisa menjawab tanpa membuka Discord di HP.

| Kolom | Arti |
| :--- | :--- |
| **#nomor** | nomor tiket (sama dengan nama thread `tiket-0001`) |
| **Status** | 🟢 terbuka · 🟡 diklaim (dengan ID staf) · ⏰ lewat SLA |
| **umur / diam** | sejak tiket dibuat / sejak pesan terakhir di thread |
| **Ringkasan** | jumlah aktif, diklaim, lewat SLA, dan rating rata-rata |

Setiap baris punya dua tombol:

| Tombol | Yang terjadi |
| :--- | :--- |
| **Balas** | kirim isi kolom teks ke thread tiket sebagai bot, atau sebagai **identitas webhook** bila kolom nama pengirim diisi (mis. “Tim Bantuan”). Respons staf pertama otomatis dicatat untuk hitungan SLA. |
| **Tutup** | tutup tiket: transkrip dibuat & dikirim ke channel log (bila diatur), thread dikunci + diarsipkan, status tersimpan di `data/tickets.json`. |

Tiket yang sudah selesai hilang dari daftar dan tidak bisa dibalas lagi — sama seperti
`/tiket tutup` di Discord.

Panel **Buat Tiket** juga bisa dipasang dari sini: buka
**🎟️ Pasang panel tiket (setara /tiket panel)** lalu pilih channel panel, role staf,
channel log transkrip, dan batas tiket per member. Tombol **Matikan sistem tiket**
menghentikan pembuatan tiket baru tanpa menghapus pesan panel lama. Member tetap membuka
tiketnya sendiri lewat tombol **Buat Tiket** di Discord — itu memang harus dari Discord.

### Formulir: kolom diisi lewat baris visual

Form **Buat formulir** sekarang menampilkan **5 baris kolom** siap pakai, bukan satu
kotak teks sintaks:

| Isian per baris | Fungsi |
| :--- | :--- |
| **Label kolom** | judul pertanyaan, mis. `Nama` |
| **pendek / paragraf** | `pendek` = satu baris, `paragraf` = jawaban panjang |
| **wajib** | centang = tidak boleh kosong |

Baris yang labelnya dikosongkan diabaikan. Mode lanjutan (`<details>`) tetap menyediakan
kolom teks bebas `Nama | Asal:panjang?` bagi yang lebih suka menulis sintaks — teks itu
hanya dipakai bila kelima baris visual kosong.

### Editor panel: tombol & dropdown tanpa Discord

Panel **🧩 Editor panel** memuat semua panel server beserta isinya, jadi aturan panel
tidak lagi harus lewat `/menu tombol-role`, `tombol-link`, `tombol-command`, `alur`, atau
`dropdown-role` di Discord.

| Bagian | Isi |
| :--- | :--- |
| **Isi panel** | daftar tombol (label · jenis · detail) lalu opsi dropdown, bernomor urut seperti tampil di Discord |
| **Hapus** | tombol **Hapus** per item — bisa juga lewat nomor urut, ID, atau label |
| **Tambah** | blok **➕ Tambah tombol / dropdown**: pilih *jenis* lalu isi kolom yang sesuai |

Jenis item yang bisa ditambah dari web:

| Jenis | Isian yang dipakai | Hasil |
| :--- | :--- | :--- |
| **peran** | Role, Label, Emoji, Gaya | tombol beri/cabut role (klik = dapat, klik lagi = lepas) |
| **tautan** | URL, Label, Emoji | tombol link (harus `http://` atau `https://`) |
| **perintah** | daftar perintah aman, Visibilitas | tombol yang menjalankan perintah info (`/serverstats`, `/level papan`, …) |
| **alur** | teks alur, mis. `+role:12 > pesan:Halo {member.mention}` | tombol yang menjalankan beberapa aksi sekaligus |
| **formulir** | daftar formulir | tombol yang membuka modal formulir |
| **dropdown** | Label (placeholder), Role 1–3, Eksklusif | satu dropdown role; *eksklusif* = hanya satu role boleh aktif |

Di bawah daftar panel ada blok **🛡️ Gerbang verifikasi** yang setara `/verifikasi pasang`:
pilih channel + role, isi catatan (opsional), lalu **Pasang panel verifikasi**. Statusnya
(aktif/nonaktif, channel, role) tampil di baris judul, dan tombol **Matikan verifikasi**
menghentikan pemberian role dari tombol lama.

Pengamanan editor panel sama dengan versi Discord: maksimal **5 tombol**, **5 dropdown**, **25 opsi**,
role harus **di bawah role bot** (dan bot punya *Manage Roles*), `@everyone`/role terkelola
ditolak, serta perintah berbahaya (`ban`, `purge`, `lockdown`, …) tidak ada di daftar.
Setelah ditambah/dihapus, panel yang sudah terkirim **langsung disunting** (`message.edit`)
sehingga tombol baru langsung bisa dipakai member.

### Ekspor CSV dari browser

Panel **📥 Ekspor CSV** menyediakan empat tombol unduh — sama dengan `/ekspor` di Discord,
tapi tanpa perlu menyimpan berkas dulu ke chat:

| Berkas | Isi |
| :--- | :--- |
| **📈 Level & XP** | peringkat member: level, XP, jumlah pesan, voice XP, prestige, aktivitas terakhir |
| **🛡️ Kasus moderasi** | semua kasus (aksi, alasan, durasi, moderator, waktu) — terbaru dulu |
| **🎟️ Tiket & rating** | nomor tiket, pemilik, status, waktu buka/tutup, respons pertama, rating |
| **📊 Pemakaian AI** | operasi AI & cache per hari |

CSV dibuat ulang setiap kali diunduh (tidak disimpan ke disk), memakai BOM UTF-8 supaya
angka & huruf non-ASCII tetap rapi di Excel, dan token tetap wajib — tautan unduhnya sudah
membawa token halaman.

### Keamanan bertingkat

| Lapis | Jaminan |
| :--- | :--- |
| **Token** | semua endpoint baca & tulis wajib token (`?token=`, `X-Dashboard-Token`, `Bearer`, atau field tersembunyi pada form HTML) |
| **Whitelist aksi** | 56 setelan di `dashboard_admin.FITUR` punya kunci yang terdaftar; aksi tak dikenal ditolak |
| **Tanpa PUT/DELETE/PATCH** | ada 14 jalur tulis `POST`, semuanya memeriksa token; data personal tetap memakai command Discord owner-only |
| **Tanpa hapus data massal** | tombol Hapus hanya membuang satu item (pesan lama di Discord tidak ikut terhapus) |
| **Jejak audit** | perubahan mencatat metadata, waktu, status, dan hasil; prompt bebas serta isi gambar tidak ditulis ke audit |
| **Bind privat** | default `DASHBOARD_HOST=0.0.0.0`, bisa diubah ke `127.0.0.1` + tunnel SSH |

### Endpoint

| Endpoint | Isi |
| :--- | :--- |
| `GET /` | halaman HTML lengkap (butuh token) |
| `GET /api/status` · `/api/pemakaian` · `/api/level` · `/api/kontrol` · `/api/fitur` | data JSON |
| `GET /api/setelan` | semua nilai setelan + ringkasan grup + riwayat |
| `GET /api/tren?hari=7` | tren operasi AI & cache per hari (JSON) |
| `POST /api/aksi` | ubah setelan: `action=set.<kunci>` atau sakelar cepat lama (token boleh lewat body form) |
| `POST /api/ai` | `action=gambar` (multipart: `prompt`, `channel_id`, `style`, `ratio`, `acuan` opsional) / `action=prompt-server` (`prompt_server`, maks 500 huruf); prompt/gambar tidak masuk audit |
| `POST /api/bangun` | tema/pratinjau AI, Terapkan eksplisit, batalkan, riwayat, dan bongkar item builder tercatat |
| `POST /api/kirim` | kirim pesan/embed; field `channel, judul, isi, warna, footer, gambar, identitas, avatar`; tambahkan `pratinjau=1` untuk pratinjau tanpa kirim |
| `POST /api/konten` | `action=buat.pengumuman` / `buat.tautan` / `buat.panel` / `buat.formulir` / `buat.pemicu` / `jeda.pengumuman:<id>` / `hapus.<jenis>:<id>` / `banner.panel:<id>` / `hapusbanner.panel:<id>` |
| `POST /api/unggah` | `action=unggah.simpan` (multipart, field `banner`) / `hapus.banner:<nama>` |
| `POST /api/uji` | tes fitur; subjek opsional dan tanpa ID memakai pemilik server |
| `GET /api/unggahan/<nama>?guild=<id>` | pratinjau banner tersimpan (wajib token) |
| `GET /api/tiket?guild=<id>` | daftar tiket aktif + statistik (JSON) |
| `POST /api/tiket` | balas/tutup tiket, pasang/matikan panel, kelola topik & catatan staf |
| `GET /api/panel?guild=<id>` | daftar panel + tombol/dropdown-nya (JSON) |
| `POST /api/panel` | tambah/hapus tombol atau dropdown, pasang/matikan verifikasi |
| `POST /api/keamanan` | setel honeypot dan uji aturan anti-spam tanpa menindak member |
| `POST /api/moderasi` | setelan jalur laporan, status antrean, cari kasus, cabut temp-ban |
| `POST /api/lencana` | atur lencana dan hadiah role server |
| `GET /api/giveaway` · `POST /api/giveaway` | daftar, buat/hentikan/undi ulang, template & setelan bawaan |
| `GET /api/transkrip` · `POST /api/transkrip` | cari/unduh arsip HTML atau hapus satu transkrip tiket |
| `GET /api/ekspor?jenis=<level\|moderasi\|tiket\|pemakaian>` | unduh CSV analitik server (wajib token) |
| `GET /healthz` | `ok` polos (tanpa token, untuk uptime monitor) |

### Yang tetap lebih enak di Discord

Dashboard mengatur **setelan**, **konten**, **panel**, **tiket**, **verifikasi**,
**generator gambar**, prompt AI server, dan **ekspor analitik server**. Ekspor/penghapusan
data personal bukan API operator: `/dataku` dan `/hapusdataku` hanya dilakukan member
yang menjalankan command di Discord (ephemeral + konfirmasi pemilik). Yang masih butuh
percakapan interaktif di Discord:

| Kebutuhan | Command |
| :--- | :--- |
| Menyusun ulang teks panel (judul/deskripsi) setelah tombol ada | `/menu ubah` *(tombol & dropdown sudah bisa dari dashboard)* |
| Mengundi (giveaway) — ambil pemenang, reroll | `/giveaway mulai`, `/giveaway pilih` |
| Moderasi, musik, permainan, AI chat | perintah masing-masing (bukan setelan) |

> 💡 **Auto-refresh**: **aktif sendiri** setiap **30 detik** — tidak perlu menyetel apa pun.
> Mau diubah? Di header ada **satu dropdown** `🔄 Auto-refresh` + tombol **Set**:
>
> | Pilihan | Arti |
> | :--- | :--- |
> | `⏸ Mati` | tanpa `meta refresh` — aman mengisi form panjang dari HP |
> | `1 menit` · `10 menit` · `30 menit` · `1 jam` | interval tetap |
> | `✏️ Isi sendiri…` | memunculkan **kotak angka detik** (`0`–`3600`, mis. `45`) tepat di sebelah dropdown |
> | `Ikut .env` | kembali mengikuti `DASHBOARD_REFRESH_SEC` |
>
> Angka bebas tidak “menghilang”: memilih `✏️ Isi sendiri…` lalu **Set** akan menampilkan
> kotak angkanya; mengisi `45` di URL (`…&refresh=45`) atau cookie juga otomatis membuka
> mode itu dengan angka yang sudah terisi. Di luar batas dipotong ke 0–3600 (bukan error),
> isian bukan angka tidak mengubah apa pun, dan nilai 1–4 detik tetap dirender 5 detik oleh
> `meta refresh`. Semua pilihan disimpan di cookie **30 hari** untuk **semua halaman**,
> **tanpa restart** dan tanpa menyentuh `.env`.
>
> ⚠️ Token dashboard berlaku **satu bot penuh** (bukan per server). Rahasiakan, dan ganti
> bila pernah ikut terlihat di tangkapan layar/percakapan.

### Menyalakan dashboard untuk instance sendiri (self-host)

Dashboard ini dirancang untuk **satu pemilik instance**, tanpa login OAuth — jadi setiap orang
yang memakai proyek ini menjalankan dashboard-nya sendiri dengan tokannya sendiri.

```bash
# 1. Buat token & tulis otomatis ke .env (buat DASHBOARD_PORT bila belum ada)
python tools/dashboard_token.py --tulis

# 2. Cek kesiapan konfigurasi (token, port, host, auto-refresh)
python tools/dashboard_token.py --periksa

# 3. Jalankan bot seperti biasa, lalu buka alamat yang dicetak
python main.py
```

| Langkah | Catatan |
| :--- | :--- |
| **Token** | 43 karakter acak, hanya huruf/angka/`_`/`-` → aman di `.env` dan URL |
| **Port** | di panel hosting biarkan `DASHBOARD_PORT=0`; di VPS/Termux isi angka (mis. `8080`) |
| **Alamat** | panel hosting: **IP node + port allocation** (bukan `0.0.0.0`) |
| **Akses** | `http://IP:PORT/?token=TOKEN` — atau lewat header `X-Dashboard-Token` |
| **Banyak server** | pakai dropdown **Server** di pojok atas halaman |
| **Keamanan** | `DASHBOARD_HOST=127.0.0.1` + SSH tunnel, atau Cloudflare Tunnel untuk HTTPS |
| **Auto-refresh** | bawaan **30 detik**; atur sendiri lewat satu dropdown di header (`Mati`/`1m`/`10m`/`30m`/`1 jam`/`✏️ Isi sendiri…`/`Ikut .env`), atau `DASHBOARD_REFRESH_SEC=0` untuk mati permanen |

> 💡 Karena tiap instance punya token sendiri, kamu **tidak perlu** membagikan token ke siapa pun.
> Pemakai lain menjalankan bot mereka sendiri dan membuat token mereka sendiri lewat perintah di atas.
