---
title: "G. Fitur Keramaian Server (/giveaway, /ultah, /jawab-otomatis, /pengumuman)"
description: "Giveaway dengan tombol ikut, ulang tahun, balasan otomatis, dan pengumuman terjadwal."
icon: "celebration"
weight: 7
toc: true
---

> 💡 **Empat fitur ini benar-benar 0 kuota Gemini.** Tidak ada satu pun permintaan AI, semuanya
> berjalan lokal memakai `data/engagement.json`. Cocok untuk server yang kuota AI-nya ingin
> dihemat untuk obrolan & ringkasan saja.

## 1. Giveaway (`/giveaway`)

| Command | Fungsi |
| :--- | :--- |
| **`/giveaway mulai hadiah:<teks> durasi:2jam pemenang:3`** | Pasang giveaway + tombol **🎉 Ikuti Giveaway** (peserta otomatis dicatat). |
| **`/giveaway mulai ... syarat_role:@Booster`** | Batasi peserta hanya pemilik role tertentu. |
| **`/giveaway akhiri id_pesan:<ID>`** | Tutup lebih awal & umumkan pemenang. ID pesan dikirim saat giveaway dibuat. |
| **`/giveaway reroll id_pesan:<ID>`** | Undi ulang dari peserta yang belum pernah menang. |
| **`/giveaway daftar`** | Giveaway yang masih berjalan + riwayat pemenang terakhir. |

- **Format durasi fleksibel:** `30m`, `2 jam`, `1j30m`, `2 hari`, `45` (menit). Minimal 1 menit.
- **Tahan restart:** tombol memakai `custom_id` persisten, jadi peserta tetap bisa klik setelah bot restart.
- Satu akun = satu peluang (klik berulang tidak menambah peluang); peserta bisa membatalkan sendiri.
- Giveaway yang waktunya habis ditutup otomatis oleh loop latar belakang (maksimal ±15 detik setelah waktunya).

## 2. Ulang Tahun (`/ultah`)

| Command | Fungsi |
| :--- | :--- |
| **`/ultah set tanggal:12-08`** | Daftarkan/perbarui tanggal lahir. Menerima `12-08`, `12/8/2000`, `12 Agustus 1999`, `1 Januari`. |
| **`/ultah daftar bulan:8`** | Lihat daftar ulang tahun member (opsional filter satu bulan). |
| **`/ultah hapus`** | Hapus data sendiri kapan saja. |
| **`/ultah atur channel:#umum jam:08:00`** *(Admin)* | Channel & jam ucapan otomatis. Kosongkan `channel` untuk mematikan. |

- Yang disimpan hanya **tanggal & bulan** (tahun opsional untuk menghitung umur). Tidak ada data lain.
- Ucapan dikirim **sekali per hari** pada jam yang diatur, mengikuti zona waktu server (`/agent` persona/timezone).

## 3. Balasan Otomatis (`/jawab-otomatis`)

| Command | Fungsi |
| :--- | :--- |
| **`/jawab-otomatis tambah pemicu:cara daftar balasan:Ketik /verifikasi`** | Bot menjawab saat kata kunci muncul. |
| **`/jawab-otomatis tambah pemicu:ping balasan:pong persis:True`** | Hanya menanggapi bila pesannya **sama persis**. |
| **`/jawab-otomatis daftar`** / **`hapus pemicu:...`** | Lihat & hapus aturan di channel tersebut. |
| **`/jawab-otomatis atur aktif:False jeda:30`** | Jeda/matikan tanpa menghapus aturan. |

- **Aman untuk obrolan:** hanya aktif di channel yang dipilih Admin, minimal pemicu 3 karakter,
  dan ada **jeda aman** (default 20 detik) agar bot tidak pernah membanjiri channel.
- Maksimal `AUTO_REPLY_MAX_RULES` (default 25) aturan per channel.

## 4. Pengumuman Terjadwal (`/pengumuman`)

| Command | Fungsi |
| :--- | :--- |
| **`/pengumuman tambah isi:... jadwal:08:00`** | Setiap hari pukul 08:00 (waktu server). |
| **`/pengumuman tambah isi:... jadwal:senin 19:00`** | Setiap minggu (nama hari Indonesia). |
| **`/pengumuman tambah isi:... jadwal:sekali 31-12-2026 23:59`** | Satu kali saja, lalu otomatis nonaktif. |
| **`/pengumuman daftar`** / **`hapus id:3`** / **`atur id:3 aktif:False`** | Kelola jadwal tanpa menghapus isi. |
| **`/pengumuman kirim id:3`** | Kirim **sekarang** tanpa menunggu jadwal — jadwal berikutnya tidak digeser. |
| **`/pengumuman ubah id:3 isi:... judul:... jadwal:...`** | Ubah isi/judul/jadwal tanpa menghapus; jadwal baru langsung dihitung. |

- Format jadwal ringkas: `08:00`, `harian 20:30`, `senin 19:00`, `mingguan sabtu 20:30`, `sekali 31-12-2026 23:59`.
- **Berulang tiap interval:** `setiap 3 jam`, `tiap 90 menit`, `interval 8 jam` — minimal **2 jam**
  (batas aman agar tidak dianggap spam), maksimal **168 jam** (seminggu). Jadwal dihitung dari
  waktu pemasangan, dan kalau bot sempat mati lama, semua jadwal yang terlewat **dilewati** —
  hanya satu kiriman berikutnya yang diambil, jadi pengumuman tidak menumpuk.
- Isi pengumuman boleh memakai variabel (`{server.name}`, `{server.members}`, `{now_relative}`) yang diisi **saat dikirim**.
- Tujuan boleh **thread** (bukan hanya channel teks). Pengumuman ulang tahun juga ikut mendukung thread.
- Pengumuman **sekali** otomatis dinonaktifkan setelah terkirim sehingga tidak pernah dobel.
- Batas `ANNOUNCEMENT_MAX_PER_GUILD` (default 15) pengumuman per server.

---
