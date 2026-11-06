'use strict';

/**
 * Halaman pratinjau panel: `/p/<kode>`.
 *
 * Kode berasal dari `/menu bagikan` (JSON ekspor panel → base64url). Halaman ini
 * menampilkan isi panel (judul, deskripsi, tombol, dropdown) sebagai pratinjau
 * plus kode impor, dan memberi tag `og:` supaya tautannya tampil rapi saat
 * dibagikan di Discord.
 *
 * Sama seperti `/l/<kode>`: tanpa database, seluruh isi ada di URL.
 * Rewrite di `vercel.json`: `/p/:id` → `/api/p/:id`.
 */

const MAX_CODE = 1500;
const MAX_BUTTONS = 25;
const MAX_OPTIONS = 25;

const KIND_LABEL = {
  role: 'Role',
  link: 'Tautan',
  command: 'Command',
  flow: 'Alur aksi',
  form: 'Formulir',
};

function decodeBase64Url(code) {
  const b64 = String(code).replace(/-/g, '+').replace(/_/g, '/');
  const padding = '='.repeat((4 - (b64.length % 4)) % 4);
  return Buffer.from(b64 + padding, 'base64').toString('utf8');
}

function tear(value, limit) {
  return typeof value === 'string' ? value.trim().slice(0, limit) : '';
}

function httpOnly(value) {
  return /^https?:\/\//i.test(value) ? value : '';
}

function parsePanel(code) {
  if (!code || typeof code !== 'string' || code.length > MAX_CODE) return null;
  if (!/^[A-Za-z0-9_-]+$/.test(code)) return null;

  let data;
  try {
    data = JSON.parse(decodeBase64Url(code));
  } catch (err) {
    return null;
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  if (data.format && data.format !== 'ai-discord-chat/panel') return null;
  if (Number(data.version || 1) > 1) return null;

  const buttons = (Array.isArray(data.buttons) ? data.buttons : [])
    .slice(0, MAX_BUTTONS)
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      label: tear(item.label, 80) || 'Tombol',
      emoji: tear(item.emoji, 24),
      kind: KIND_LABEL[tear(item.kind, 20)] || 'Tombol',
      detail:
        item.kind === 'link'
          ? httpOnly(tear(item.url, 300))
          : tear(item.command || item.group || '', 60),
      steps: Array.isArray(item.flow) ? item.flow.length : 0,
    }));

  const dropdowns = (Array.isArray(data.dropdowns) ? data.dropdowns : [])
    .slice(0, 5)
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      placeholder: tear(item.placeholder, 150) || 'Pilih…',
      exclusive: Boolean(item.exclusive),
      options: (Array.isArray(item.options) ? item.options : [])
        .slice(0, MAX_OPTIONS)
        .map((opt) => tear(opt && opt.label, 100))
        .filter(Boolean),
    }));

  const title = tear(data.title, 120);
  if (!title && !buttons.length && !dropdowns.length) return null;

  return {
    title: title || 'Panel',
    description: tear(data.description, 1500),
    banner: httpOnly(tear(data.banner_url, 400)),
    buttons,
    dropdowns,
  };
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function metaProperty(property, content) {
  if (!content) return '';
  return `<meta property="${property}" content="${escapeHtml(content)}">`;
}

function renderButtons(panel) {
  if (!panel.buttons.length) return '';
  const baris = panel.buttons
    .map((btn) => {
      const detail = btn.kind === 'Alur aksi' && btn.steps
        ? `${btn.kind} · ${btn.steps} langkah`
        : btn.detail
          ? `${btn.kind} · ${btn.detail}`
          : btn.kind;
      return `<li><span class="emoji">${escapeHtml(btn.emoji || '🔹')}</span>
        <span><strong>${escapeHtml(btn.label)}</strong>
        <em>${escapeHtml(detail)}</em></span></li>`;
    })
    .join('');
  return `<ul class="tombol-daftar">${baris}</ul>`;
}

function renderDropdowns(panel) {
  if (!panel.dropdowns.length) return '';
  const baris = panel.dropdowns
    .map(
      (dd) =>
        `<li><strong>${escapeHtml(dd.placeholder)}</strong>${
          dd.exclusive ? ' (eksklusif)' : ''
        } — ${escapeHtml(dd.options.join(', '))}</li>`
    )
    .join('');
  return `<h2>Dropdown</h2><ul class="daftar">${baris}</ul>`;
}

function renderPanel(panel, kode) {
  const deskripsi = panel.description.replace(/\s+/g, ' ');
  const paragraf = panel.description
    .split(/\n{1,}/)
    .map((bagian) => `<p>${escapeHtml(bagian)}</p>`)
    .join('');
  const jumlah =
    panel.buttons.length +
    panel.dropdowns.reduce((total, dd) => total + dd.options.length, 0);

  return `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(panel.title)} — Panel AI Discord Chat</title>
<meta name="robots" content="noindex">
${metaProperty('og:type', 'article')}
${metaProperty('og:site_name', 'AI Discord Chat')}
${metaProperty('og:title', panel.title)}
${metaProperty('og:description', deskripsi || 'Panel tombol untuk server Discord.')}
${metaProperty('og:image', panel.banner)}
<meta name="twitter:card" content="${panel.banner ? 'summary_large_image' : 'summary'}">
${metaProperty('twitter:title', panel.title)}
${metaProperty('twitter:description', deskripsi || 'Panel tombol untuk server Discord.')}
${metaProperty('twitter:image', panel.banner)}
<meta name="theme-color" content="#9b59b6">
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
  font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
  background: #0f1115; color: #e9e9ef; }
.kartu { width: min(720px, 100%); background: #171a21; border-radius: 16px; overflow: hidden;
  border: 1px solid rgba(255,255,255,.08); box-shadow: 0 24px 60px rgba(0,0,0,.45); }
.garis { height: 6px; background: #9b59b6; }
.isi { padding: 24px; }
h1 { margin: 0 0 12px; font-size: 1.4rem; line-height: 1.3; }
h2 { margin: 22px 0 8px; font-size: .85rem; text-transform: uppercase; letter-spacing: .08em;
  color: #8f8fa3; }
p { margin: 0 0 12px; line-height: 1.6; color: #c8c8d4; white-space: pre-wrap; }
.banner { display: block; width: 100%; max-height: 300px; object-fit: cover; }
.tombol-daftar, .daftar { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.tombol-daftar li { display: flex; gap: 10px; align-items: baseline; padding: 10px 12px;
  background: #20242e; border-radius: 10px; font-size: .95rem; }
.tombol-daftar em { color: #9a9aad; font-style: normal; font-size: .82rem; margin-left: 6px; }
.emoji { font-size: 1.05rem; }
.daftar li { padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,.06); color: #c8c8d4;
  font-size: .9rem; }
pre { margin: 8px 0 0; padding: 12px; background: #0b0d11; border-radius: 10px;
  overflow-x: auto; font-size: .78rem; color: #b9b9cc; white-space: pre-wrap; word-break: break-all; }
.catatan { font-size: .82rem; color: #8f8fa3; }
footer { padding: 14px 24px 22px; font-size: .8rem; color: #8f8fa3; }
</style>
</head>
<body>
<main class="kartu">
  <div class="garis"></div>
  ${panel.banner ? `<img class="banner" src="${escapeHtml(panel.banner)}" alt="">` : ''}
  <div class="isi">
    <h1>${escapeHtml(panel.title)}</h1>
    ${paragraf}
    <h2>Tombol</h2>
    ${renderButtons(panel) || '<p class="catatan">Panel ini tidak punya tombol.</p>'}
    ${renderDropdowns(panel)}
    <h2>Impor ke servermu</h2>
    <p class="catatan">Jalankan command ini di servermu (harus Admin / Manage Server):</p>
    <pre>/menu impor kode:${escapeHtml(kode)}</pre>
    <p class="catatan">Atau pakai kode di bawah — sama isinya:</p>
    <pre>ai-discord-chat/panel:${escapeHtml(kode)}</pre>
  </div>
  <footer>${jumlah} item · dibuat dengan AI Discord Chat · formulir &amp; ID role tidak ikut dibagikan</footer>
</main>
</body>
</html>
`;
}

function renderNotFound() {
  return `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tautan panel tidak dikenal</title>
<meta name="robots" content="noindex">
<style>
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
  font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif; background: #0f1115;
  color: #e9e9ef; text-align: center; }
.kotak { max-width: 460px; }
h1 { font-size: 1.3rem; }
p { color: #a3a3b5; line-height: 1.6; }
a { color: #b07ce0; }
</style>
</head>
<body>
<div class="kotak">
  <h1>🧩 Tautan panel tidak dikenal</h1>
  <p>Kodenya rusak, tidak lengkap, atau panelnya terlalu besar untuk dibagikan lewat tautan.
  Minta tautan baru lewat command <code>/menu bagikan</code> — atau berkas JSON lewat
  <code>/menu ekspor</code>.</p>
  <p><a href="/docs/">Lihat dokumentasi</a></p>
</div>
</body>
</html>
`;
}

module.exports = function handler(req, res) {
  const kode = req && req.query ? req.query.id : '';

  if (req && req.method === 'HEAD') {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end();
    return;
  }

  const panel = parsePanel(Array.isArray(kode) ? kode[0] : kode);

  if (!panel) {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=60');
    res.setHeader('X-Robots-Tag', 'noindex');
    res.end(renderNotFound());
    return;
  }

  res.statusCode = 200;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800');
  res.setHeader('X-Robots-Tag', 'noindex');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.end(renderPanel(panel, Array.isArray(kode) ? kode[0] : kode));
};

module.exports.parsePanel = parsePanel;
module.exports.renderPanel = renderPanel;
module.exports.renderNotFound = renderNotFound;
