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
| **`/menu hapus-item menu:… item:2`** *(Admin)* | Hapus tombol/opsi (nomor urut, ID, atau label) |
| **`/menu kirim menu:… [channel]`** *(Admin)* | Kirim ulang panel ke channel lain |
| **`/menu daftar`** | Lihat semua panel beserta isinya |
| **`/menu hapus menu:…`** *(Admin)* | Hapus panel dari daftar bot |

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
