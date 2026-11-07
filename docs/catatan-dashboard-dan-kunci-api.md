# 📌 Catatan Parkir: Dashboard Web, BYOK, & "Isi Sendiri API Key"

> **Status: BELUM DIPUTUSKAN** — catatan ini disimpan supaya diskusi tidak hilang.
> Belum ada form input rahasia yang ditambahkan ke dashboard. Keputusan menunggu owner.
>
> Terakhir diperbarui: v1.40.0-beta

> ℹ️ **Satu bagian sudah selesai tanpa perlu keputusan ini:** “Tahap 1 — status key
> (masked)” sudah ada di dashboard tanpa menyimpan rahasia apa pun — halaman
> `/` (Ringkasan) menampilkan status Gemini **aktif / belum ada key** dan punya tombol
> **Tes koneksi AI** (`uji.ai`) yang melaporkan key kosong, kuota, atau jaringan.
> Tidak ada API key yang pernah dikirim balik ke browser.

## 1. Pertanyaan yang muncul

> "Bot kan bisa diatur dari browser (dashboard). Bisa tidak kita akali: bikin dashboard bot,
> lalu **mereka sendiri** yang memasukkan API key dan environment variable-nya?"

Dari pertanyaan ini muncul dua hal berbeda yang sering tercampur:

1. **Mengatur fitur bot dari browser** → ini sudah ada (`web_dashboard.py` +
   `dashboard_admin.py`): **54 setelan dalam 11 halaman**, kirim embed/webhook, unggah
   banner & kartu sambutan, kotak masuk tiket, serta pengelolaan pengumuman, tautan, dan panel.
2. **Pengguna lain memasukkan rahasia sendiri** (token bot, API key) → ini fitur baru, dan
   sebagian **tidak mungkin** dilakukan.

## 2. Batas keras: apa yang bisa & tidak bisa

| Item | Bisa per server/member? | Catatan |
| :--- | :--- | :--- |
| **Bot token** (`DISCORD_TOKEN`) | ❌ **Tidak bisa** | 1 token = 1 identitas bot = 1 proses. "Mereka isi token sendiri" = mereka **menjalankan instance sendiri**, bukan fitur dashboard. |
| **Client secret OAuth2** | ❌ Tidak | Milik *application* Discord, satu untuk semua server. |
| **Gemini API key** | ✅ Bisa (BYOK) | Panggilan AI per guild bisa memakai key guild tersebut, fallback ke key operator. |
| **Lavalink host/password** | ⚠️ Praktisnya per proses | Bot ini memakai node global; per-guild hanya menambah kebingungan. |
| Channel/role/prefix/bahasa/toggle fitur | ✅ Sudah per guild | Sudah berjalan di versi sekarang. |
| **`DASHBOARD_TOKEN`** | ⚠️ Sekarang satu password global | Kalau dashboard dibuka untuk publik (banyak admin berbeda), harus naik ke **OAuth2 Discord** + cek *Manage Server*. |

## 3. Cara kerja bot besar yang punya dashboard (pola industri)

```
Browser ──HTTPS──► Dashboard (Node/Next.js) ──┐
                                              ├──► PostgreSQL (config per guild)
Discord ◄──WS──── Bot (Node/Python) ──────────┘
                            ▲
                     Redis pub/sub ("config guild X berubah")
```

- Dashboard **tidak** memanggil bot secara langsung; keduanya berbagi **database**.
- Login memakai **Discord OAuth2** (`identify` + `guilds`); dashboard hanya menampilkan server
  tempat user punya izin *Manage Server/Administrator*.
- Aksi dashboard = menulis baris konfigurasi. Bot menyimpan **cache di RAM** dan memperbaruinya
  lewat Redis pub/sub (atau polling) → berlaku tanpa restart.
- **`.env`/secrets tetap milik operator**, diisi di panel hosting — bukan form dashboard.
- API key AI biasanya dibiayai model langganan/premium, **bukan** BYOK. BYOK lazim hanya pada
  bot self-host.

## 4. Realitas stack proyek ini sekarang

```
Browser ──HTTPS──► aiohttp (di dalam proses bot) ──► data/*.json ──► fitur bot
Discord ◄──WS──── Bot (proses yang sama)
```

| Aspek | Pola industri (DB) | Proyek ini (JSON 1 proses) |
| :--- | :--- | :--- |
| Config sampai ke bot | DB + pub/sub atau poll | instan (satu memori) |
| RAM tambahan | Postgres/Redis: puluhan–ratusan MB | ±2–4 MB |
| Restart | dashboard tetap hidup | ikut restart |
| Login | OAuth2 (wajib, publik) | password token (cukup 1 operator) |
| Skala | ribuan server, multi-worker | puluhan–ratusan server, 1 worker |
| Biaya | VPS + DB terkelola | 0 (Free Tier) |

Batas Free Tier Wispbyte tetap: **1 proses, ~52 MB RAM, tanpa DB/Redis, butuh port allocation
+ domain HTTPS stabil** kalau dashboard mau dipakai dari luar.

## 5. Opsi yang dipertimbangkan (belum dipilih)

| Opsi | Isi | Effort | Risiko |
| :--- | :--- | :--- | :--- |
| **A1 — BYOK via slash command** | `/kunci ai isi:<key>` per guild, cek *Manage Server*, fallback ke key operator, `/kunci hapus` | Sedang | Rendah — Discord sudah mengautentikasi identitas & izin |
| **A2 — BYOK + dashboard OAuth2** | Login Discord di browser, isi key + atur fitur dari web | Besar | Sedang–tinggi — butuh OAuth, session, enkripsi at-rest, CSRF, domain HTTPS |
| **B — Satu bot per pelanggan (self-host)** | Tiap orang deploy instance sendiri, isi `.env` di panel hosting mereka; kita sediakan template + panduan | Kecil | Sangat rendah — kita tidak menyimpan rahasia siapa pun |
| **Tahap 1 — tab status key (masked)** | Dashboard hanya menampilkan status key operator (`...ab12`) + tombol tes koneksi | Kecil | Sangat rendah — tidak ada input rahasia |

### Urutan yang disarankan bila kelak dikerjakan
1. **Tab status key (masked)** → cepat, aman, langsung berguna untuk diagnosa.
2. **BYOK via slash command** (bukan form web) → Discord sudah memverifikasi izin, tidak perlu OAuth.
3. **OAuth2 + form web** → baru setelah ada domain HTTPS tetap & port allocation.

## 6. Risiko yang wajib disadari (kalau BYOK dikerjakan)

- Menyimpan key orang = menjadi **penjaga rahasia** mereka. Bocor = key disalahgunakan penuh
  (key Gemini tidak bisa dibatasi per fitur).
- Enkripsi at-rest butuh paket `cryptography` (+3–6 MB RAM). **Tanpa paket itu, hanya
  obfuscation — bukan enkripsi**, dan harus ditulis apa adanya di dokumentasi.
- Dashboard publik: wajib HTTPS, sesi (cookie), proteksi CSRF, rate limit, **jangan pernah**
  mengirim balik key penuh ke browser, jangan menulis key ke log, dan **kecualikan** dari
  ekspor analitik/webhook.
- `data/*.json` berisi rahasia **tidak boleh** ikut backup yang dikirim ke pihak lain
  (`/backup struktur` tidak menyertakan `data/`, jadi aman — ini tetap harus dijaga).

## 7. Prinsip yang tidak berubah apa pun keputusannya

- Free Tier: 1 proses, JSON storage, tanpa DB/Redis, RAM tetap kecil.
- **0 kuota AI** untuk UI, dashboard, dan alert.
- Tidak mengganggu obrolan normal di channel publik.
- Menu/tombol Discord tetap jalan penuh walau dashboard mati (dashboard hanya jalan pintas).

## 8. Yang masih menunggu jawaban owner

1. Model mana: **A1** (BYOK slash), **A2** (OAuth2 + dashboard), **B** (self-host per pelanggan),
   atau cukup **Tahap 1** (tab status key)?
2. Kalau BYOK: cukup **key Gemini saja**, atau plus pilihan model + batas harian per guild?
3. Apakah tersedia **domain HTTPS stabil + port allocation** di hosting? (prasyarat A2)
4. Boleh menambah dependency `cryptography` untuk enkripsi at-rest?

> Sampai ada jawaban, **jangan** menambahkan form input rahasia di dashboard.
