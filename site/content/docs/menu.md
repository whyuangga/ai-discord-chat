---
title: "Q. Menu Builder & Self Roles v2 (/menu)"
description: "Menu builder dengan tombol role/link/command, self roles v2, dan visibilitas per item."
icon: "widgets"
weight: 17
toc: true
---

Bikin panel sendiri — mirip *Self Roles* milik bot Discohook, tapi isinya tidak harus role:
satu panel bisa memuat **tombol role, tombol link, dan tombol command** sekaligus. 0 kuota AI.

| Command | Fungsi |
| :--- | :--- |
| **`/menu buat judul:… [deskripsi] [banner] [banner_url] [channel]`** *(Admin)* | Membuat panel + mengirimnya ke channel |
| **`/menu tombol-role menu:… role:@Gamer [label] [emoji] [gaya]`** | Tombol role: klik = dapat, klik lagi = lepas |
| **`/menu tombol-link menu:… label:Support url:https://…`** | Tombol tautan (buka URL, tanpa aksi bot) |
| **`/menu tombol-command menu:… aksi:serverstats [visibilitas]`** | Tombol yang menjalankan command info |
| **`/menu dropdown-role menu:… role1:@A role2:@B [eksklusif]`** | Dropdown role (maks 25 role, bisa eksklusif) |
| **`/menu alur menu:… label:… aksi:…`** | Tombol yang menjalankan **alur aksi** berurutan (lihat di bawah) |
| **`/menu alur-bantuan`** | Panduan singkat menulis alur |
| **`/menu form buat nama:… kolom:… tujuan:#x`** | **Formulir (modal)** buatan sendiri: kolom bebas (lihat di bawah) |
| **`/menu form tombol form:… menu:… [label]`** | Pasang formulir sebagai tombol di panel |
| **`/menu form daftar`** / **`/menu form uji form:…`** | Lihat semua formulir / coba isi tanpa mengirim hasil |
| **`/menu hapus-item menu:… item:2`** *(Admin)* | Hapus tombol/opsi (nomor urut, ID, atau label) |
| **`/menu ubah menu:… judul:… deskripsi:…`** *(Admin)* | Ubah teks panel; pesan yang sudah terkirim ikut berubah |
| **`/menu ekspor menu:…`** *(Admin)* | Unduh panel sebagai JSON (backup / pindah server) |
| **`/menu impor berkas:…`** *(Admin)* | Buat panel baru dari JSON hasil ekspor |
| **`/menu kirim menu:… [channel]`** *(Admin)* | Kirim ulang panel ke channel lain |
| **`/menu daftar`** | Lihat semua panel beserta isinya |
| **`/menu hapus menu:…`** *(Admin)* | Hapus panel dari daftar bot |

## Alur aksi tombol (`/menu alur`)
Satu tombol bisa menjalankan **beberapa aksi berurutan** — ide yang dipinjam dari *flows* Discohook.
Langkah dipisah `>` dan teksnya boleh memakai variabel (`{member.mention}`, `{server.name}`):

```text
/menu alur menu:1 label:Buka Tiket aksi:+role:123456 > pesan:Halo {member.mention}, tiketmu siap! > thread:tiket-{member.name}
```

| Langkah | Arti |
| :--- | :--- |
| `role:<id>` | Toggle role (dapat bila belum punya, lepas bila sudah) |
| `+role:<id>` / `-role:<id>` | Tambah / lepas role |
| `syarat:<id>` | Berhenti diam-diam bila member **tidak** punya role itu |
| `pesan:<teks>` | Balasan pribadi (*ephemeral*) |
| `umum:<teks>` | Balasan yang terlihat semua orang |
| `thread:<nama>` | Buat thread publik di channel panel |
| `tunggu:<detik>` | Jeda (maks 15 detik) |
| `stop[:<teks>]` | Hentikan alur, opsional kirim alasan |
| `webhook:<nama>\|<teks>` | Kirim pesan sebagai **nama sendiri** lewat webhook (butuh *Manage Webhooks*) |
| `hapus` | Hapus balasan bot yang sudah dikirim alur ini (pasangan `umum:… > tunggu:5 > hapus`) |

Batas: **10 langkah** per tombol, 1000 karakter per pesan. Role tetap wajib di bawah role bot.

## Formulir (modal) buatan sendiri — `/menu form`
`/agent panel` punya modal dengan kolom tetap. Lewat `/menu form`, **Admin merancang sendiri**
isinya: sebut kolom yang diinginkan, pasang sebagai tombol, dan jawaban anggota dikirim rapi ke
channel pilihan — cocok untuk lamaran staff, laporan bug, atau pendaftaran event.

```text
/menu form buat nama:"Lamaran Staff" kolom:"Nama | Umur | Alasan:panjang?" tujuan:#lamaran
/menu form tombol form:"Lamaran Staff" menu:Pusat menu label:"📝 Daftar Staff"
```

| Tulis di `kolom` | Artinya |
| :--- | :--- |
| `Nama` | Kolom pendek, wajib diisi |
| `Nama?` | Kolom pendek, boleh kosong |
| `Alasan:panjang` | Kolom paragraf (bisa beberapa baris) |
| `Catatan:panjang?` | Paragraf, boleh kosong (urutan penanda bebas) |

- Kolom dipisah `|`; **maksimal 5** kolom — atau **4** bila memakai `penjelasan` (kalimat pengantar
  di dalam modal memakan satu slot).
- `hasil` mengatur bentuk pesan yang masuk ke channel, mis.
  `hasil:"**Nama:** {form.nama}
**Umur:** {form.umur}
**Alasan:** {form.alasan}"`.
  Kosongkan untuk daftar otomatis (`**Kolom**` lalu jawabannya).
- `{form.<kolom>}` diisi jawaban anggota; variabel biasa (`{member.mention}`, `{server.name}`,
  `{now_relative}`) tetap jalan.
- **Tanpa mention:** hasil dikirim dengan *mention* dimatikan, jadi jawaban anggota tidak bisa
  dipakai men-*ping* `@everyone`.
- Jawaban **tidak disimpan** bot — hanya diteruskan ke channel tujuan; yang dicatat cuma jumlahnya.
- `/menu form uji` menampilkan pratinjau hasil tanpa mengirim ke channel. Satu formulir per
  server dibatasi **20**, dan `/menu form hapus` ikut membersihkan tombolnya di panel.
- Berkas data: `data/forms.json`. Tombol formulir **tidak ikut** `/menu ekspor` (formulirnya
  terpisah) — pesan ekspor akan menyebutkan tombol mana yang dilewati.

## Variabel pesan
Judul/isi `/embed`, `/pengumuman`, `/menu`, dan teks alur bisa memakai variabel yang diisi saat
pesan dikirim: `{member.name}`, `{member.display_name}`, `{member.mention}`, `{member.created_relative}`,
`{server.name}`, `{server.members}`, `{server.boosts}`, `{channel.mention}`, `{now_relative}`, dll.
Daftar lengkap: `/embed variabel`. Variabel yang tidak dikenal dibiarkan apa adanya agar salah
ketik terlihat; variabel yang datanya tidak ada (mis. `{member.name}` di pengumuman terjadwal)
diganti kosong.

## Backup panel
`/menu ekspor` menghasilkan berkas JSON (`ai-discord-chat/panel` v1) berisi judul, deskripsi,
banner, tombol (role/link/command/alur), dan dropdown — tanpa ID guild/channel/pesan.
`/menu impor` memulihkannya sebagai panel baru di server mana pun; ID role tetap milik server
asal, jadi di server lain role perlu dibuat ulang sebelum tombolnya dipakai.

**Tautan bagikan (tanpa berkas).** `/menu bagikan` membuat kode ringkas dari panel itu dan
sebuah URL pratinjau `https://<situs>/p/<kode>` (halaman situs, lengkap dengan tag `og:` jadi
tampil rapi saat ditempel di Discord). Siapa pun bisa memasangnya dengan
`/menu impor kode:<tautan atau kode>` — menerima URL penuh, `ai-discord-chat/panel:<kode>`,
maupun kodenya saja. Tidak ada database: isi panel ikut di dalam kode.
Kode diringkas dengan **zlib + base64** (awalan `z.`), jadi panel berisi 20 tombol pun
masih muat (±430 karakter). Kode lama tanpa awalan tetap bisa diimpor. Batas kerasnya
1.500 karakter — panel yang lebih besar ditolak dengan saran memakai `/menu ekspor`.

## Tombol yang bisa menjalankan command
Klik tombol = bot menjalankan **command yang sama** atas nama **member yang mengklik**, jadi semua
cek izin tetap berlaku. Contoh isi panel "Pusat Info":

| Tombol | Menjalankan |
| :--- | :--- |
| 📊 Statistik | `/serverstats lihat` |
| 📈 Level Saya | `/level lihat` |
| 🌱 Pertumbuhan | `/tumbuh ringkas` |
| 💰 Saldo Koin | `/ekonomi saldo` |
| 🎟️ Daftar Tiket | `/tiket daftar` |
| 📋 Audit Log | `/log status` |
| 🔋 Pemakaian AI | `/pemakaian lihat` |
| 📖 Bantuan | `/bantuan` |

- **Visibilitas per tombol:** `auto` (ikut command), `ephemeral` (hanya yang klik), atau `publik`.
- **Whitelist** — hanya command informasi. `ban`, `purge`, `lockdown`, `backup`, `/mod`,
  `/ekonomi atur`, dll. **tidak bisa** dipasang sebagai tombol.

## Self Roles v2 lewat `/panel-role`
`/panel-role pasang` sekarang punya parameter **`gaya`**:

| Gaya | Tampilan |
| :--- | :--- |
| `reaksi` (bawaan) | Cara lama: klik emoji di bawah embed |
| `tombol` | Baris tombol role (maks 20) |
| `dropdown` | Satu menu pilihan role (maks 25) |
| `campuran` | **Banner + tombol + dropdown** — persis gaya Self Roles Discohook |

Tambah **`banner`** (unggah `.png/.jpg`) atau **`banner_url`** untuk gambar besar di atas panel.

**Target kirim:** panel bisa dikirim ke **channel teks**, **thread**, atau **forum channel**
(untuk forum, panel menjadi post baru dengan judul panel sebagai nama post).

## Batas & pengaman
| Hal | Nilai |
| :--- | :--- |
| Tombol per panel | 20 (5 tombol per baris) |
| Dropdown per panel | 2, maksimal 25 opsi masing-masing |
| Panel per server | 20 |
| Banner | PNG/JPG/WebP, maks 8 MB |
| Jeda klik role | 3 detik per member (anti spam-klik) |
| Role hadiah | wajib **di bawah** role bot & bot punya izin **Manage Roles** |
| Data | `data/menus.json` (panel persisten; tombol tetap hidup setelah restart) |
| Audit | setiap perubahan role tercatat di `/log` bila audit log aktif |

---
