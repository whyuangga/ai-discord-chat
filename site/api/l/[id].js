'use strict';

/**
 * Halaman tautan embed: `/l/<kode>`.
 *
 * Bot mengirim tautan berisi kode (JSON → base64url) yang dipaketkan di URL-nya.
 * Function ini mengubah kode menjadi halaman HTML bertag `og:` supaya Discord
 * menampilkan embed cantik (judul, deskripsi, gambar), lalu mengalihkan pengunjung
 * ke URL tujuan lewat `<meta http-equiv="refresh">`.
 *
 * Tidak ada database dan tidak ada data pribadi: seluruh isi embed ada di URL.
 * Diatur lewat rewrite di `vercel.json`: `/l/:id` → `/api/l/:id`.
 */

const MAX_CODE = 1200;

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

function parsePayload(code) {
  if (!code || typeof code !== 'string' || code.length > MAX_CODE) return null;
  if (!/^[A-Za-z0-9_-]+$/.test(code)) return null;

  let data;
  try {
    data = JSON.parse(decodeBase64Url(code));
  } catch (err) {
    return null;
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  if (Number(data.v) !== 1) return null;

  const payload = {
    title: tear(data.t, 200),
    description: tear(data.d, 600),
    url: httpOnly(tear(data.u, 500)),
    image: httpOnly(tear(data.i, 300)),
    thumbnail: httpOnly(tear(data.th, 300)),
    color: /^[0-9a-fA-F]{6}$/.test(tear(data.c, 6)) ? tear(data.c, 6).toLowerCase() : '',
    provider: tear(data.p, 60),
    site: tear(data.s, 60),
  };
  if (!payload.title && !payload.description) return null;
  return payload;
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

function renderRedirect(payload) {
  const judul = payload.title || payload.site || 'Tautan';
  const provider = payload.provider || payload.site || 'AI Discord Chat';
  const deskripsi = payload.description.replace(/\s+/g, ' ');
  const teksParagraf = payload.description
    .split(/\n{1,}/)
    .map((bagian) => `<p>${escapeHtml(bagian)}</p>`)
    .join('');

  const target = payload.url;
  const tombol = target
    ? `<a class="tombol" href="${escapeHtml(target)}" rel="nofollow noopener">Buka halaman →</a>`
    : '<p class="catatan">Tanpa URL tujuan — tautan ini hanya menampilkan embed.</p>';

  return `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(judul)}</title>
<meta name="robots" content="noindex">
${metaProperty('og:type', 'website')}
${metaProperty('og:site_name', provider)}
${metaProperty('og:title', payload.title || judul)}
${metaProperty('og:description', deskripsi)}
${metaProperty('og:image', payload.image)}
${metaProperty('og:image:alt', payload.title)}
<meta name="twitter:card" content="${payload.image ? 'summary_large_image' : 'summary'}">
${metaProperty('twitter:title', payload.title || judul)}
${metaProperty('twitter:description', deskripsi)}
${metaProperty('twitter:image', payload.image)}
${payload.color ? `<meta name="theme-color" content="#${payload.color}">` : ''}
${target ? `<meta http-equiv="refresh" content="0; url=${escapeHtml(target)}">` : ''}
<style>
:root { color-scheme: light dark; --aksen: #${payload.color || '9b59b6'}; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
  font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
  background: #0f1115; color: #e9e9ef; }
.kartu { width: min(640px, 100%); background: #171a21; border-radius: 16px; overflow: hidden;
  border: 1px solid rgba(255,255,255,.08); box-shadow: 0 24px 60px rgba(0,0,0,.45); }
.garis { height: 6px; background: var(--aksen); }
.isi { padding: 24px; }
h1 { margin: 0 0 12px; font-size: 1.4rem; line-height: 1.3; }
p { margin: 0 0 12px; line-height: 1.6; color: #c8c8d4; white-space: pre-wrap; }
.gambar { display: block; width: 100%; max-height: 320px; object-fit: cover; }
.tombol { display: inline-block; margin-top: 8px; padding: 12px 18px; border-radius: 10px;
  background: var(--aksen); color: #fff; text-decoration: none; font-weight: 600; }
.tombol:hover { filter: brightness(1.1); }
.catatan { font-size: .85rem; color: #8f8fa3; }
footer { padding: 14px 24px 22px; font-size: .8rem; color: #8f8fa3; }
</style>
</head>
<body>
<main class="kartu">
  <div class="garis"></div>
  ${payload.image ? `<img class="gambar" src="${escapeHtml(payload.image)}" alt="${escapeHtml(payload.title)}">` : ''}
  <div class="isi">
    <h1>${escapeHtml(payload.title || judul)}</h1>
    ${teksParagraf}
    ${tombol}
  </div>
  <footer>${escapeHtml(provider)} · dialihkan otomatis ke halaman tujuan</footer>
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
<title>Tautan tidak dikenal</title>
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
  <h1>🔗 Tautan tidak dikenal</h1>
  <p>Kode tautan ini rusak, tidak lengkap, atau memang tidak dibuat oleh bot.
  Minta tautan baru lewat command <code>/embed tautan</code>.</p>
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

  const payload = parsePayload(Array.isArray(kode) ? kode[0] : kode);

  if (!payload) {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=60');
    res.setHeader('X-Robots-Tag', 'noindex');
    res.end(renderNotFound());
    return;
  }

  res.statusCode = 200;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  // Isi embed tidak berubah (menempel di URL), jadi aman di-cache lama.
  res.setHeader('Cache-Control', 'public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800');
  res.setHeader('X-Robots-Tag', 'noindex');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.end(renderRedirect(payload));
};

module.exports.parsePayload = parsePayload;
module.exports.renderRedirect = renderRedirect;
module.exports.renderNotFound = renderNotFound;
