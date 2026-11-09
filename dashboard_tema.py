"""Tema visual dashboard web — satu sumber warna & tipografi.

Dipakai oleh tiga halaman yang dirender bot:

* halaman utama dashboard  → :data:`CSS_HALAMAN`
* halaman pratinjau embed   → :data:`CSS_PRATINJAU`
* halaman hasil submit      → :data:`CSS_HASIL`

Palet resmi:

* latar  ``#0D0D0F``
* teks   ``#FFFFFF``
* font   **General Sans** (Fontshare) — dimuat lewat CSS API Fontshare,
  dengan font stack cadangan supaya tetap enak dibaca saat perangkat offline.

CSS di sini ditulis dengan **kurung kurawal tunggal** dan disuntikkan lewat
``str.format`` / f-string, jadi tidak perlu dobel kurawal seperti di template.
"""

# ---------------------------------------------------------------------------
# PALET
# ---------------------------------------------------------------------------
LATAR = "#0D0D0F"
TEKS = "#FFFFFF"

# ---------------------------------------------------------------------------
# TIPOGRAFI — General Sans (Fontshare)
# ---------------------------------------------------------------------------
# Fontshare menyajikan CSS + font dari CDN mereka; dengan `<link>` ini browser
# pengguna yang mengunduh fontnya (bot tidak perlu dependency Python baru).
FONT_LINK = (
    '<link rel="preconnect" href="https://api.fontshare.com">'
    '<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>'
    '<link rel="stylesheet" href="'
    "https://api.fontshare.com/v2/css?f[]=general-sans@400,500,600,700&amp;display=swap"
    '" crossorigin="anonymous">'
)

FONT_STACK = (
    "'General Sans', 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)
FONT_MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"

# Warna pendukung (diturunkan dari #0D0D0F + #FFFFFF)
GARIS = "rgba(255,255,255,.09)"
GARIS_KUAT = "rgba(255,255,255,.16)"
KARTU = "#131316"
KARTU_2 = "#17171B"
MEDAN = "#191920"
REDUP = "rgba(255,255,255,.62)"
REDUP_2 = "rgba(255,255,255,.44)"
AKSEN = "#8B7CFF"
BIRU = "#5865F2"
HIJAU = "#4ADE80"
KUNING = "#FBBF24"
MERAH = "#E5484D"

# ---------------------------------------------------------------------------
# CSS HALAMAN UTAMA
# ---------------------------------------------------------------------------
CSS_HALAMAN = f"""
  :root {{
    color-scheme: dark;
    --latar: {LATAR};
    --teks: {TEKS};
    --redup: {REDUP};
    --redup-2: {REDUP_2};
    --garis: {GARIS};
    --garis-kuat: {GARIS_KUAT};
    --kartu: {KARTU};
    --kartu-2: {KARTU_2};
    --medan: {MEDAN};
    --aksen: {AKSEN};
    --biru: {BIRU};
    --hijau: {HIJAU};
    --kuning: {KUNING};
    --merah: {MERAH};
    --radius: 16px;
  }}
  * {{ box-sizing: border-box; }}
  html {{ background: var(--latar); }}
  body {{
    margin: 0; padding: 22px 20px 40px;
    background: radial-gradient(ellipse at 82% -22%, rgba(139,124,255,.085), transparent 42%), var(--latar);
    color: var(--teks);
    font-family: {FONT_STACK};
    font-size: 14px; line-height: 1.55;
    -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    letter-spacing: .005em;
  }}
  ::selection {{ background: rgba(139,124,255,.35); color: #fff; }}
  h1 {{ font-size: 28px; font-weight: 600; margin: 0; letter-spacing: -.035em; line-height: 1.2; }}
  b, strong {{ font-weight: 600; }}
  a {{ color: #A99BFF; }}
  a:hover {{ color: #fff; }}
  code, kbd, pre {{ font-family: {FONT_MONO}; }}
  :focus-visible {{ outline: 2px solid var(--aksen); outline-offset: 3px; }}

  /* --- shell dashboard + navigasi (tanpa JavaScript) --- */
  .topbar {{
    position: sticky; top: 0; z-index: 20;
    margin: -22px -20px 24px; padding: 14px 20px 12px;
    background: rgba(13, 13, 15, .94);
    backdrop-filter: blur(16px) saturate(140%);
    border-bottom: 1px solid var(--garis);
  }}
  .brand-row {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
  .brand {{ display: flex; align-items: center; gap: 10px; min-width: 0; color: var(--teks); }}
  .brand-mark {{
    display: grid; place-items: center; flex: 0 0 34px; width: 34px; height: 34px;
    border-radius: 11px; color: #fff; font-size: 17px;
    background: linear-gradient(145deg, #A99BFF, #6758E8);
    box-shadow: 0 5px 18px rgba(139,124,255,.24);
  }}
  .brand-copy {{ display: grid; line-height: 1.15; }}
  .brand-name {{ font-size: 14px; font-weight: 600; letter-spacing: -.01em; }}
  .brand-caption {{ margin-top: 3px; color: var(--redup-2); font-size: 9px; font-weight: 600;
                    letter-spacing: .14em; text-transform: uppercase; }}
  .server-context {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin-top: 10px; }}
  .server-context-label {{ color: var(--aksen); font-size: 9px; font-weight: 600;
                           letter-spacing: .13em; text-transform: uppercase; }}
  .topbar .judul {{ color: var(--teks); font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }}
  .topbar .meta {{ color: var(--redup-2); font-size: 10.5px; }}
  .menu-btn {{
    margin-left: auto; display: none; cursor: pointer; user-select: none;
    padding: 8px 13px; border-radius: 10px; font-size: 13px; font-weight: 500;
    border: 1px solid var(--garis-kuat); background: var(--kartu-2); color: var(--teks);
  }}
  .nav-buka {{ position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }}
  #nav-buka:focus-visible + .brand-row .menu-btn {{ outline: 2px solid var(--aksen); outline-offset: 2px; }}
  nav.menu {{ display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }}
  .menu-kelompok {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
  .menu-kelompok-judul {{
    flex-basis: 100%; margin-bottom: 2px; color: rgba(255,255,255,.42);
    font-size: 10px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase;
  }}
  nav.menu a {{
    padding: 7px 12px; border-radius: 999px; text-decoration: none; white-space: nowrap;
    border: 1px solid transparent; background: rgba(255,255,255,.035);
    color: rgba(255,255,255,.78); font-size: 12.5px; font-weight: 500;
    transition: background .16s ease, color .16s ease, border-color .16s ease, transform .16s ease;
  }}
  nav.menu a:hover {{ background: rgba(255,255,255,.085); color: #fff; border-color: var(--garis-kuat); }}
  nav.menu a[aria-current="page"] {{
    background: rgba(139,124,255,.16); border-color: rgba(139,124,255,.45);
    color: #fff; font-weight: 600;
  }}
  .sidebar-controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin-top: 10px; }}
  .workspace {{ width: 100%; max-width: 1560px; margin: 0 auto; min-width: 0; }}
  .page-heading {{ margin: 4px 0 24px; }}
  .page-eyebrow {{ margin-bottom: 8px; color: var(--aksen); font-size: 10px; font-weight: 600;
                    letter-spacing: .15em; text-transform: uppercase; }}
  .keterangan-halaman {{ max-width: 780px; margin: 8px 0 0; color: var(--redup); font-size: 13px; }}
  .keterangan-halaman:empty {{ display: none; }}
  /* Daftar isi halaman: pintasan ke tiap bagian, menggantikan scroll panjang. */
  .daftar-isi {{
    margin: 0 0 22px; padding: 12px 14px; border: 1px solid var(--garis);
    border-radius: 12px; background: var(--kartu);
  }}
  .daftar-isi:empty {{ display: none; }}
  .daftar-isi-label {{
    display: block; margin-bottom: 9px; color: var(--redup);
    font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
  }}
  .daftar-isi-tautan {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .daftar-isi-tautan a {{
    padding: 5px 11px; border: 1px solid var(--garis); border-radius: 999px;
    color: var(--teks); font-size: 12.5px; text-decoration: none;
    background: var(--latar); transition: border-color .15s, color .15s;
  }}
  .daftar-isi-tautan a:hover {{
    border-color: var(--aksen); color: var(--aksen);
  }}
  .panel, .subpanel, section[id] {{ scroll-margin-top: 118px; }}

  /* --- pesan hasil aksi --- */
  .flash {{
    border-radius: 12px; padding: 11px 14px; margin: 0 0 16px; font-size: 13px;
    border: 1px solid rgba(74,222,128,.35); background: rgba(74,222,128,.09); color: #EAFFF1;
  }}
  .flash.galat {{ border-color: rgba(229,72,77,.4); background: rgba(229,72,77,.10); color: #FFEDED; }}

  .muted {{ color: var(--redup); font-size: 12px; }}

  /* --- saklar cepat --- */
  .kontrol {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0; }}
  .kontrol label {{ min-width: 190px; font-size: 13px; }}
  .kontrol select, .kontrol button {{
    padding: 7px 11px; border-radius: 9px; font-size: 13px; font-family: inherit;
    border: 1px solid var(--garis-kuat); background: var(--medan); color: var(--teks);
  }}
  .kontrol button {{ background: var(--biru); border-color: var(--biru); color: #fff; cursor: pointer; }}
  .kontrol button:hover {{ filter: brightness(1.1); }}

  /* --- kartu status --- */
  .grid {{
    display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    margin: 18px 0 26px;
  }}
  .card {{
    position: relative; overflow: hidden; min-height: 108px;
    background: linear-gradient(145deg, rgba(255,255,255,.045), rgba(255,255,255,.012)), var(--kartu);
    border: 1px solid var(--garis); border-radius: var(--radius);
    padding: 17px 18px; color: var(--redup); font-size: 11px; font-weight: 500;
    letter-spacing: .025em; box-shadow: 0 10px 28px rgba(0,0,0,.13);
    transition: transform .18s ease, border-color .18s ease, background .18s ease;
  }}
  .card::after {{
    content: ""; position: absolute; width: 92px; height: 92px; top: -52px; right: -34px;
    border-radius: 50%; background: rgba(139,124,255,.10); filter: blur(2px); pointer-events: none;
  }}
  .card:hover {{ transform: translateY(-2px); border-color: rgba(255,255,255,.16); }}
  .card b {{ display: block; position: relative; z-index: 1; font-size: 24px; line-height: 1.2;
             margin-top: 10px; color: var(--teks); letter-spacing: -.025em; }}
  .card b.ok {{ color: var(--hijau); }} .card b.warn {{ color: var(--kuning); }}

  /* --- panel --- */
  .panel {{
    background: linear-gradient(150deg, rgba(255,255,255,.035), rgba(255,255,255,.008)), var(--kartu);
    border: 1px solid var(--garis); border-radius: var(--radius);
    padding: 20px; margin-bottom: 16px; box-shadow: 0 14px 36px rgba(0,0,0,.12);
  }}
  .panel h2 {{
    font-size: 12.5px; font-weight: 600; margin: 0 0 12px;
    text-transform: uppercase; letter-spacing: .10em; color: var(--redup);
  }}
  .subpanel {{ margin: 16px 0 6px; }}
  .subpanel h3 {{ font-size: 13px; font-weight: 600; margin: 8px 0 4px; color: var(--teks); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td, th {{ text-align: left; padding: 7px 6px; border-bottom: 1px solid var(--garis); }}
  tr:last-child td, tr:last-child th {{ border-bottom: 0; }}
  th {{ color: var(--redup); font-weight: 500; }}
  td {{ color: var(--teks); }}
  .ok {{ color: var(--hijau); }} .warn {{ color: var(--kuning); }}

  /* --- formulir --- */
  .formgrid {{ display: grid; gap: 10px; margin: 8px 0 4px; }}
  .medan {{ display: grid; gap: 5px; }}
  .medan label {{ font-size: 12px; color: var(--redup); }}
  input[type=text], input[type=number], input[type=url], input[type=password], textarea {{
    width: 100%; padding: 9px 11px; border-radius: 9px; font-size: 13px;
    border: 1px solid var(--garis-kuat); background: var(--medan); color: var(--teks);
    font-family: inherit;
  }}
  input::placeholder, textarea::placeholder {{ color: var(--redup-2); }}
  input[type=text]:focus, input[type=number]:focus, input[type=url]:focus,
  input[type=password]:focus, textarea:focus, select:focus {{
    outline: 2px solid rgba(139,124,255,.55); outline-offset: 1px; border-color: var(--aksen);
  }}
  select {{
    padding: 8px 10px; border-radius: 9px; font-size: 13px; font-family: inherit;
    border: 1px solid var(--garis-kuat); background: var(--medan); color: var(--teks);
  }}
  textarea {{ resize: vertical; min-height: 90px; }}
  .formgrid button {{ justify-self: start; }}
  button {{
    font-family: inherit; cursor: pointer;
    padding: 8px 13px; border-radius: 9px; font-size: 13px; font-weight: 500;
    border: 1px solid var(--biru); background: var(--biru); color: #fff;
  }}
  button:hover {{ filter: brightness(1.1); }}
  button.danger {{ background: var(--merah); border-color: var(--merah); }}
  button.ghost {{ background: transparent; border-color: var(--garis-kuat); color: rgba(255,255,255,.82); }}
  button.ghost:hover {{ background: rgba(255,255,255,.07); color: #fff; }}

  td.aksi {{ display: flex; gap: 6px; flex-wrap: wrap; }}

  /* --- banner --- */
  .galeri {{
    display: grid; gap: 10px; margin-top: 12px;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }}
  .kartu-banner {{
    background: var(--kartu-2); border: 1px solid var(--garis); border-radius: 11px;
    padding: 9px; display: grid; gap: 6px;
  }}
  .kartu-banner img {{ width: 100%; height: 90px; object-fit: cover; border-radius: 7px; background: var(--latar); }}
  .kartu-banner code.kecil {{ font-size: 10px; color: var(--redup); overflow-wrap: anywhere; }}
  input[type=file] {{ width: 100%; font-size: 12px; color: rgba(255,255,255,.82); }}

  /* --- kartu sambutan (unggah gambar sendiri) --- */
  .kartu-sambutan {{
    display: grid; gap: 10px; margin: 12px 0 8px;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }}
  .kartu-sambutan.tunggal {{ grid-template-columns: 1fr; }}
  .kartu-sambutan.tunggal .kartu-slot img {{ height: 170px; }}
  .kartu-slot {{
    background: var(--kartu-2); border: 1px solid var(--garis); border-radius: 12px;
    padding: 12px; display: grid; gap: 8px; align-content: start;
  }}
  .kartu-slot h4 {{ margin: 0; font-size: 13px; font-weight: 600; }}
  .kartu-slot img {{ width: 100%; height: 120px; object-fit: cover; border-radius: 9px;
                     background: var(--latar); border: 1px solid var(--garis); }}
  .kartu-slot .kosong {{
    height: 120px; border-radius: 9px; border: 1px dashed var(--garis-kuat);
    display: grid; place-items: center; color: var(--redup-2); font-size: 12px;
  }}
  .kartu-slot form {{ margin: 0; }}
  .kartu-slot .medan label {{ font-size: 11.5px; }}

  /* --- Panel tampilan sambutan (Card / Embed / Text / Container) --- */
  .sambutan-tampilan {{
    border: 1px solid var(--garis); border-radius: 12px; padding: 12px;
    margin: 10px 0; background: var(--kartu-2);
  }}
  .sambutan-tampilan h4 {{ margin: 0 0 4px; font-size: 13.5px; font-weight: 600; }}
  .pemilih-mode {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px; margin: 10px 0;
  }}
  .pemilih-mode .pilihan-mode {{
    display: flex; align-items: center; justify-content: center; gap: 4px;
    padding: 9px 6px; font-size: 12px; font-weight: 600;
    background: var(--latar); color: var(--redup);
    border: 1px solid var(--garis); border-radius: 9px; cursor: pointer;
  }}
  .pemilih-mode .pilihan-mode:hover {{ color: var(--teks); border-color: var(--garis-kuat); }}
  .pemilih-mode .pilihan-mode.aktif {{
    background: var(--aksen); color: #fff; border-color: var(--aksen);
  }}
  .pratinjau-kotak {{
    border-radius: 12px; padding: 12px; margin: 8px 0 12px;
    background: var(--latar); border: 1px solid var(--garis);
  }}
  .pratinjau-label {{
    font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--redup-2); margin-bottom: 8px;
  }}
  .pratinjau-kotak p.muted {{ margin: 6px 0 0; }}
  .pratinjau-judul {{ font-weight: 700; font-size: 13.5px; margin-bottom: 4px; }}
  .pratinjau-baris {{ font-size: 12.5px; line-height: 1.5; white-space: pre-wrap; }}
  .pratinjau-kaki {{ font-size: 11px; color: var(--redup-2); margin-top: 8px; }}
  .pratinjau-teks {{
    background: var(--kartu-2); border-radius: 8px; padding: 10px;
    font-size: 12.5px; line-height: 1.5;
  }}
  .pratinjau-embed {{
    border-left: 3px solid var(--aksen); background: var(--kartu-2);
    border-radius: 6px; padding: 10px 12px;
  }}
  .pratinjau-container {{
    border: 1px solid var(--aksen); border-radius: 10px;
    background: var(--kartu-2); padding: 10px 12px;
  }}
  .pratinjau-kartu {{
    display: flex; gap: 12px; align-items: center;
    background: linear-gradient(135deg, rgba(235,69,158,.18), rgba(88,101,242,.18));
    border: 1px solid var(--garis-kuat); border-radius: 10px; padding: 12px;
  }}
  .pratinjau-avatar {{
    width: 52px; height: 52px; flex: 0 0 52px; border-radius: 50%;
    display: grid; place-items: center; font-weight: 700; font-size: 20px;
    background: var(--aksen); color: #fff;
  }}
  .pratinjau-nama {{ font-size: 12px; color: var(--redup); margin-bottom: 2px; }}
  .daftar-variabel {{
    margin: 8px 0 0; padding-left: 18px; font-size: 11.5px; color: var(--redup);
  }}
  .daftar-variabel code {{ font-size: 11px; }}
  /* Slot unggah gambar di dalam panel tampilan */
  .kartu-slot.banner-card {{
    margin: 4px 0 12px; border-style: dashed;
  }}
  .kartu-slot.banner-card h5 {{
    margin: 0; font-size: 12.5px; font-weight: 600; color: var(--teks);
  }}
  .kartu-slot.banner-card .muted {{ margin: 0; font-size: 11.5px; }}
  .sebaris {{ margin: 0; }}
  .sebaris button {{ margin-top: 6px; }}
  .lebar-penuh {{ grid-column: 1 / -1; }}
  .lebar-penuh textarea {{ width: 100%; font-family: inherit; }}

  /* --- kartu rank (PNG, perender yang sama dengan /level kartu) --- */
  .kartu-rank {{ display: grid; gap: 8px; margin: 10px 0; }}
  .kartu-rank img {{
    width: 100%; max-width: 560px; border-radius: 12px;
    border: 1px solid var(--garis); background: var(--latar);
  }}
  .lencana {{
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    font-size: 11.5px; font-weight: 600;
  }}
  .lencana.on {{ background: rgba(90, 200, 130, .16); color: #7ee2a8; }}
  .lencana.off {{ background: rgba(255,255,255,.08); color: var(--redup); }}

  /* --- tes fitur --- */
  .kepala-tes {{
    margin: 14px 0 6px; padding-top: 10px;
    border-top: 1px dashed var(--garis); font-size: 0.9rem;
  }}
  .uji-baris {{
    display: flex; gap: 12px; align-items: center; justify-content: space-between;
    flex-wrap: wrap; padding: 11px 0; border-bottom: 1px solid var(--garis);
  }}
  .uji-baris:last-of-type {{ border-bottom: 0; }}
  .uji-baris b {{ font-size: 13.5px; }}
  .uji-baris form {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
                     justify-content: flex-end; }}
  .uji-baris input[type=text] {{ width: 175px; padding: 7px 9px; font-size: 12.5px; }}
  .uji-baris select {{ max-width: 190px; padding: 7px 9px; font-size: 12.5px; }}
  /* --- pilih banyak channel (checkbox, tanpa JavaScript) --- */
  .label-setelan {{ font-size: 12.5px; font-weight: 500; margin-bottom: 6px; }}
  .channel-grid {{
    display: grid; gap: 4px 14px; width: 100%;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    max-height: 216px; overflow-y: auto; padding: 8px 10px;
    border: 1px solid var(--garis); border-radius: 10px; background: rgba(255,255,255,.02);
  }}
  .pilih-channel {{
    display: flex; align-items: center; gap: 7px; font-size: 12.5px;
    color: rgba(255,255,255,.86); padding: 3px 0; cursor: pointer;
  }}
  .pilih-channel input {{ accent-color: #8B7CFF; width: 15px; height: 15px; }}
  .pilih-channel.kosongkan {{ grid-column: 1 / -1; color: var(--redup); }}
  .uji-baris input[name="opsi_manual"] {{ width: 165px; }}
  @media (max-width: 620px) {{
    .uji-baris {{ align-items: stretch; }}
    .uji-baris form {{ justify-content: flex-start; }}
    .uji-baris input[type=text], .uji-baris select,
    .uji-baris input[name="opsi_manual"] {{ width: 100%; max-width: none; }}
  }}

  /* --- pemilih server & auto-refresh --- */
  .pemilih-server {{ display: flex; gap: 8px; align-items: center; margin: 8px 0 0; flex-wrap: wrap; }}
  .pemilih-server label {{ font-size: 12px; color: var(--redup); }}
  .pemilih-server button {{ cursor: pointer; }}

  .pemilih-auto {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 0; }}
  .pemilih-auto label {{ font-size: 12px; color: var(--redup); white-space: nowrap; }}
  .pemilih-auto select {{ min-width: 118px; }}
  .pemilih-auto input[type="number"] {{ width: 84px; }}
  .pemilih-auto .satuan {{ font-size: 12px; color: var(--redup-2); margin-left: -4px; }}
  .pemilih-auto button {{ cursor: pointer; padding: 7px 12px; }}
  .sidebar-controls .pemilih-server {{ margin: 0; }}

  /* --- grafik --- */
  .grafik {{ margin: 6px 0 10px; }}
  .grafik svg {{ width: 100%; height: 160px; }}

  .aksi-banner {{ display: grid; gap: 6px; margin-top: 8px; }}
  .kolom-formulir {{ display: grid; gap: 6px; }}
  .baris-kolom {{ display: grid; grid-template-columns: 1fr 110px auto; gap: 6px; align-items: center; }}
  .baris-kolom label.centang {{
    font-size: 12px; color: var(--redup); display: flex; gap: 5px; align-items: center; white-space: nowrap;
  }}

  details summary {{ cursor: pointer; margin: 6px 0; color: rgba(255,255,255,.82); }}

  /* --- tiket --- */
  .daftar-tiket {{ display: grid; gap: 10px; }}
  .tiket-baris {{
    background: var(--kartu-2); border: 1px solid var(--garis); border-radius: 11px;
    padding: 11px; display: grid; gap: 8px;
  }}
  form.tiket-form {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  form.tiket-form input[type=text] {{ flex: 1 1 150px; font-size: 12px; }}

  /* --- editor panel --- */
  .daftar-panel {{
    border: 1px solid var(--garis); border-radius: 11px; padding: 11px;
    background: #101013; margin-bottom: 10px;
  }}
  .daftar-panel h4 {{ margin: 2px 0 8px; font-size: 14px; font-weight: 600; }}
  .panel-item {{
    display: flex; gap: 8px; align-items: center; padding: 7px 0;
    border-bottom: 1px solid var(--garis);
  }}
  .panel-item:last-child {{ border-bottom: 0; }}
  .panel-item .nomor {{ min-width: 22px; color: var(--aksen); font-size: 12px; }}
  .panel-item > div {{ flex: 1; }}
  .panel-item form {{ margin: 0; }}
  .panel-item.dropdown {{
    background: var(--kartu-2); padding: 6px 9px; border-radius: 9px; margin-top: 6px;
    border-bottom: 0;
  }}
  form.tambah-item {{ display: grid; gap: 8px; margin: 8px 0; }}
  form.tambah-item .medan label {{ font-size: 12px; }}

  .kecil {{ font-size: 11px; }}

  /* --- ekspor --- */
  .ekspor {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  a.tombol-unduh {{
    display: inline-block; padding: 9px 13px; border-radius: 9px; text-decoration: none;
    font-size: 13px; font-weight: 500; background: var(--medan); color: var(--teks);
    border: 1px solid var(--garis-kuat); transition: background .15s ease, border-color .15s ease;
  }}
  a.tombol-unduh:hover {{ background: rgba(255,255,255,.10); color: #fff; border-color: rgba(255,255,255,.26); }}

  form.banner-form {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
  form.banner-form input[type=file] {{ width: auto; max-width: 190px; }}
  form.banner-form select {{ font-size: 12px; max-width: 210px; }}

  .riwayat {{ padding-left: 18px; font-size: 13px; }}
  .riwayat li {{ margin: 8px 0; }}
  footer {{ margin-top: 20px; color: var(--redup-2); }}

  /* --- sidebar desktop: navigasi vertikal ala dashboard analytics --- */
  @media (min-width: 821px) {{
    body {{ padding: 30px 34px 48px 286px; }}
    .topbar {{
      position: fixed; inset: 0 auto 0 0; z-index: 30; width: 252px; height: 100vh; height: 100dvh;
      margin: 0; padding: 20px 14px 14px; display: flex; flex-direction: column; gap: 14px;
      overflow: hidden; background: linear-gradient(180deg, #111115 0%, #0D0D0F 74%);
      border-right: 1px solid var(--garis); border-bottom: 0;
      box-shadow: 12px 0 36px rgba(0,0,0,.16); backdrop-filter: none;
    }}
    .brand-row {{ justify-content: flex-start; padding: 0 6px 16px; border-bottom: 1px solid var(--garis); }}
    .server-context {{ display: grid; gap: 4px; margin: 0; padding: 11px 12px;
                       border: 1px solid var(--garis); border-radius: 12px;
                       background: linear-gradient(135deg, rgba(255,255,255,.045), rgba(255,255,255,.012)); }}
    .server-context .judul {{ font-size: 13px; line-height: 1.4; }}
    .server-context .meta {{ font-size: 10px; line-height: 1.45; overflow-wrap: anywhere; }}
    nav.menu {{
      display: flex; flex: 1 1 auto; min-height: 0; flex-direction: column; flex-wrap: nowrap;
      gap: 10px; margin: 0; padding: 2px 3px 8px 0; overflow-y: auto; align-content: start;
      scrollbar-color: rgba(255,255,255,.18) transparent; scrollbar-width: thin;
    }}
    .menu-kelompok {{ flex-wrap: wrap; gap: 4px; }}
    nav.menu a {{
      display: flex; align-items: center; min-height: 39px; width: 100%; padding: 8px 11px;
      border: 1px solid transparent; border-radius: 10px; background: transparent;
      font-size: 12px; white-space: normal; line-height: 1.35;
    }}
    nav.menu a:hover {{ transform: translateX(2px); border-color: transparent; background: rgba(255,255,255,.07); }}
    nav.menu a[aria-current="page"] {{
      background: rgba(139,124,255,.15); border-color: rgba(139,124,255,.32);
      box-shadow: inset 2px 0 0 var(--aksen);
    }}
    .sidebar-controls {{
      display: grid; flex: 0 0 auto; gap: 11px; margin-top: auto; padding: 13px 2px 0;
      border-top: 1px solid var(--garis);
    }}
    .sidebar-controls .pemilih-server {{
      display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center; margin: 0;
    }}
    .sidebar-controls .pemilih-server label {{ grid-column: 1 / -1; }}
    .sidebar-controls .pemilih-server select {{ width: 100%; min-width: 0; }}
    .sidebar-controls .pemilih-server .muted {{ grid-column: 1 / -1; overflow-wrap: anywhere; }}
    .sidebar-controls .pemilih-auto {{
      display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center;
    }}
    .sidebar-controls .pemilih-auto label,
    .sidebar-controls .pemilih-auto select,
    .sidebar-controls .pemilih-auto button {{ grid-column: 1 / -1; }}
    .sidebar-controls .pemilih-auto select {{ width: 100%; min-width: 0; }}
    .sidebar-controls .pemilih-auto input[type="number"] {{ width: 100%; min-width: 0; }}
    .sidebar-controls .pemilih-auto .satuan {{ justify-self: start; }}
    .sidebar-controls .pemilih-auto button {{ width: 100%; }}
    .page-heading {{ margin: 3px 0 26px; }}
    .panel, .subpanel, section[id] {{ scroll-margin-top: 28px; }}
  }}

  /* --- navigasi seluler (checkbox CSS, tanpa JavaScript) --- */
  @media (max-width: 820px) {{
    .menu-btn {{ display: inline-block; }}
    .topbar {{ max-height: calc(100vh - 8px); overflow-y: auto; margin: -22px -20px 18px; padding: 12px 20px; }}
    .server-context {{ gap: 4px 8px; }}
    .server-context-label {{ display: none; }}
    .server-context .judul {{ font-size: 12.5px; }}
    .server-context .meta {{ margin-left: auto; }}
    nav.menu {{ display: none; flex-direction: column; flex-wrap: nowrap; gap: 4px;
                max-height: 42vh; overflow-y: auto; margin-top: 10px; padding-right: 2px; }}
    nav.menu a {{ padding: 10px 13px; border-radius: 10px; font-size: 14px; white-space: normal; }}
    #nav-buka:checked ~ nav.menu {{ display: flex; }}
    .sidebar-controls {{ padding-top: 10px; border-top: 1px solid var(--garis); }}
    .panel, .subpanel, section[id] {{ scroll-margin-top: 160px; }}
  }}
  @media (max-width: 620px) {{
    body {{ padding: 12px 12px 32px; font-size: 13.5px; }}
    h1 {{ font-size: 22px; }}
    .topbar {{ margin: -12px -12px 16px; padding: 12px; }}
    .brand-mark {{ flex-basis: 31px; width: 31px; height: 31px; border-radius: 10px; }}
    .brand-name {{ font-size: 13.5px; }}
    .server-context {{ margin-top: 8px; }}
    .server-context .meta {{ font-size: 9.5px; }}
    .page-heading {{ margin-bottom: 20px; }}
    .panel {{ padding: 14px; }}
    .card {{ min-height: 96px; padding: 13px 15px; }}
    .card b {{ font-size: 20px; }}
    .baris-kolom {{ grid-template-columns: 1fr; gap: 4px; }}
    .panel-item {{ flex-wrap: wrap; }}
    .tiket-form input[type=text] {{ flex: 1 1 100%; }}
    .ekspor a.tombol-unduh {{ flex: 1 1 45%; text-align: center; }}
    .kontrol label {{ min-width: 100%; }}
    table {{ font-size: 12px; }}
    td, th {{ padding: 6px 4px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
    .card:hover, nav.menu a:hover {{ transform: none; }}
  }}
"""

# ---------------------------------------------------------------------------
# CSS HALAMAN PRATINJAU EMBED
# ---------------------------------------------------------------------------
CSS_PRATINJAU = f"""
 body {{
    margin: 0; padding: 22px 20px 40px; background: {LATAR}; color: {TEKS};
    font-family: {FONT_STACK}; font-size: 14px; line-height: 1.55;
    -webkit-font-smoothing: antialiased;
 }}
 h1 {{ font-size: 19px; font-weight: 600; margin: 0 0 4px; letter-spacing: -.01em; }}
 .muted {{ color: {REDUP}; font-size: 12px; }}
 .p-pengirim {{ font-size: 13px; margin: 18px 0 6px; color: rgba(255,255,255,.82); }}
 .p-kartu {{
    background: #1B1B20; border-left: 4px solid var(--warna-kartu, {BIRU});
    border-radius: 8px; padding: 13px 15px; max-width: 520px;
    border-top: 1px solid {GARIS}; border-right: 1px solid {GARIS}; border-bottom: 1px solid {GARIS};
 }}
 .p-judul {{ font-weight: 600; margin-bottom: 6px; }}
 .p-isi {{ white-space: pre-wrap; font-size: 14px; line-height: 1.5; }}
 .p-gambar {{ width: 100%; border-radius: 8px; margin-top: 9px; }}
 .p-footer {{ font-size: 11px; color: {REDUP}; margin-top: 9px; }}
 .p-tombol {{
    margin-top: 10px; display: inline-block; background: #4E5058; color: #fff;
    padding: 6px 12px; border-radius: 5px; font-size: 13px;
 }}
 .p-peringatan {{
    margin: 16px 0; background: rgba(251,191,36,.10); border: 1px solid rgba(251,191,36,.35);
    border-radius: 10px; padding: 11px 13px; font-size: 13px; color: #FFF6E5;
 }}
 .p-peringatan ul {{ margin: 6px 0 0 18px; }}
 .aksi {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 20px; }}
 button, a.tombol {{
    padding: 9px 16px; border-radius: 9px; font-size: 14px; font-weight: 500;
    border: 1px solid {BIRU}; background: {BIRU}; color: #fff;
    text-decoration: none; cursor: pointer; font-family: inherit;
 }}
 button:hover, a.tombol:hover {{ filter: brightness(1.1); }}
 a.kembali {{ background: transparent; border-color: {GARIS_KUAT}; color: rgba(255,255,255,.82); }}
"""

# ---------------------------------------------------------------------------
# CSS HALAMAN HASIL (submit gagal)
# ---------------------------------------------------------------------------
CSS_HASIL = f"""
 body {{
    margin: 0; padding: 30px 22px; background: {LATAR}; color: {TEKS};
    font-family: {FONT_STACK}; line-height: 1.55; -webkit-font-smoothing: antialiased;
 }}
 h1 {{ font-size: 26px; margin: 0 0 10px; }}
 p {{ margin: 0 0 12px; }}
 a {{ color: #A99BFF; }}
 a:hover {{ color: #fff; }}
"""

