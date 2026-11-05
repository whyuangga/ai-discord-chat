---
title: "M. Tampilan Panel Components V2 (/panel, /tampilan)"
linkTitle: "M. Tampilan Panel Components V2"
weight: 13
---

Discord kini mendukung **Components V2** (`Container`, `Section`, `TextDisplay`, `Separator`,
`Thumbnail`, `Label`), jadi panel bot bisa tampil seperti dashboard web hosting: kartu berwarna
aksen, baris status, badge ON/OFF, dan navigasi tab — **tanpa kuota AI sama sekali**.

- **`/panel buka`** — **Control Center**. Satu pesan berisi kartu status + dropdown untuk berpindah tab:
  `🏠 Ringkasan`, `🤖 AI Agent`, `🛠️ Server`, `🧩 Komunitas`, `🎵 Musik`, `📊 Kuota & Level`.
  Tombol **🔄 Segarkan**, **🎨 Tampilan**, dan **🚪 Tutup** selalu tersedia.
- **`/tampilan atur`** *(Admin)* — editor branding server. Semua pilihan **langsung berefek**:
  - **warna aksen** (8 pilihan: ungu, biru, teal, hijau, oranye, merah, pink, abu-abu) → warna kartu V2,
    warna embed cadangan, dan emoji aksen di footer;
  - **gaya emoji** (standar/minimalis) → seluruh ikon panel;
  - **kepadatan** → *ringkas* menyembunyikan baris penjelas (`>`), *nyaman* menampilkan semuanya;
  - **thumbnail** → ikon server tampil sebagai `Section` + `Thumbnail` di kepala dashboard;
  - **gaya navigasi** → dropdown atau baris tombol tab;
  - **interval refresh panel musik** → 10 / 20 / 30 / 60 detik (watcher berdetak tiap 10 detik, jadi
    10 detik adalah resolusi paling segar dan menghemat rate limit Discord);
  - toggle **footer** dan **dialog konfirmasi** untuk aksi merusak.
- **`/tampilan pratinjau`** — lihat dashboard dengan tema yang sedang aktif sebelum disimpan rapi.
- **`/tampilan reset`** — kembalikan semua tampilan ke bawaan bot (memakai dialog konfirmasi).
- **`/pemakaian lihat`** — kini tampil sebagai kartu V2 dengan **progress bar** efisiensi cache.
- Tema disimpan **per server**; bila sebuah pilihan tidak diubah, bot memakai default
  (ungu • emoji standar • ringkas • thumbnail ikon • footer aktif • konfirmasi aktif • refresh 10 detik).

## Panel lain yang sudah memakai Components V2

| Command | Tampilan baru |
| :--- | :--- |
| `/status` | Kartu diagnostik: latensi, RAM, uptime, status AI/komunitas/musik + tombol **Muat Ulang** & **Control Center**. |
| `/agent panel` | Dua kartu: ringkasan channel target + **8 tombol toggle berwarna** (🟢 hijau = aktif, 🔴 merah = mati), dropdown channel, serta tombol Persona / Tambah FAQ / Kelola FAQ / Segarkan / Tutup. |
| `/tiket panel` | Panel "Pusat Bantuan" bergaya kartu dengan tombol **🎟️ Buat Tiket** (tetap menempel setelah bot restart). |
| `/musik antrean` | Antrean berhalaman sebagai kartu: judul, total durasi, tombol **◀ Sebelumnya / Berikutnya ▶ / Tutup**. |
| `/musik panel` & panel pemutar otomatis | Panel Rythm versi kartu: progress bar, volume, filter, autoplay, plus **9 tombol kontrol** dalam 2 baris (⏮ ⏯ ⏭ ⏹ 🔁 / 🔀 🔉 🔊 📜). |
| `/musik sekarang` | Kartu Now Playing bertema (progres, sumber, antrean, diminta oleh). |
| `/bantuan` | Pusat panduan sebagai kartu + **dropdown 11 kategori** yang langsung berganti halaman. Halaman depan kini memuat panel **🆕 Terbaru (v1.28 → v1.39)** berisi ringkasan fitur terbaru (`/raid`, `/nuke`, `/backup pulihkan`, `/level musim`, `/musik playlist`, `/tiket rating`, `/bahasa`, `/prefix`, `/analitik`, `/perawatan memori`) dan jumlah menu utama dihitung dari command yang benar-benar terdaftar. |
| `/agent status` | Ringkasan seluruh channel AI Agent sebagai kartu bertema. |
| `/giveaway daftar` | Daftar giveaway aktif & riwayat sebagai kartu. |
| `/pemakaian reset`, `/musik hentikan`, `/tampilan reset` | Dialog **konfirmasi bergaya kartu** sebelum aksi merusak (bisa dimatikan Admin lewat `/tampilan atur`). |

> **Soal ikon 🔊 di channel statistik:** ikon pengeras suara itu **ikon bawaan Discord untuk Voice
> Channel** — tidak bisa diganti lewat nama atau emoji. Ikon mengikuti **tipe channel**, jadi cara
> satu-satunya menggantinya adalah memilih tipe lain lewat **`/serverstats tipe`**:
>
> | Tipe | Ikon | Catatan |
> | :--- | :--- | :--- |
> | `voice` (bawaan) | 🔊 | paling lazim dipakai bot statistik |
> | `text` | #️⃣ | warga bisa melihat angka, **tidak bisa mengirim pesan** |
> | `announcement` | 📢 | mundur ke `text` bila server menolak channel pengumuman |
> | `stage` | 🎤 | mundur ke `voice` bila stage channel tidak diizinkan |
>
> Emoji di dalam **nama** channel (mis. `👥 Total Member: 12`) dan nama kategori tetap bisa diatur
> lewat `/serverstats ikon`.

## Batas Keras Discord yang Tidak Bisa Dilanggar

| Batas | Nilai |
| :--- | :--- |
| Baris tombol per pesan | maks 5 baris, 5 tombol per baris |
| Total komponen per pesan | ~40 komponen |
| Opsi pada dropdown | maks 25 opsi |
| Warna kartu | hanya pilihan aksen bawaan Discord (tidak bisa hex bebas) |
| Teks satu blok | maks 4000 karakter |

Tidak ada CSS, font kustom, animasi, atau gambar di dalam tombol — itu memang tidak didukung Discord.

## Kalau Server/Klien Tidak Mendukung V2

Bot otomatis **mundur ke embed klasik** (warna aksen tetap dipakai). Jadi tidak ada command yang
gagal hanya karena tampilan V2 ditolak klien. Data tema disimpan di **`data/ui_theme.json`** per server.

---
