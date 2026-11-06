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

Batas: **10 langkah** per tombol, 1000 karakter per pesan. Role tetap wajib di bawah role bot.

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
